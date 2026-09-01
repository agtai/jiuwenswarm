# Copyright (c) Huawei Technologies Co., Ltd. 2025. All rights reserved.

"""AgentServerClient - Gateway 与 AgentServer 的 WebSocket 客户端."""

from __future__ import annotations

import logging
import asyncio
import hashlib
import json
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Any, AsyncIterator
from urllib.parse import urlsplit

from websockets.exceptions import ConnectionClosed, PayloadTooBig

from jiuwenswarm.common.e2a.constants import E2A_WIRE_SERVER_PUSH_KEY
from jiuwenswarm.common.e2a.models import E2AEnvelope
from jiuwenswarm.common.e2a.wire_codec import (
    parse_agent_server_wire_chunk,
    parse_agent_server_wire_unary,
)
from jiuwenswarm.common.schema.agent import AgentResponse, AgentResponseChunk
from jiuwenswarm.common.ws_limits import AGENT_WS_MAX_MESSAGE_BYTES
from jiuwenswarm.common.ws_diagnostics import (
    describe_ws_exception,
    describe_ws_peer,
    format_ws_diagnostics,
)


logger = logging.getLogger(__name__)
_STREAM_TRAILING_MESSAGE_GRACE_SECONDS = 0.7
AGENT_REQUEST_TIMEOUT_SECONDS: float = 600.0
_UNARY_REQUEST_TIMEOUT_SECONDS = AGENT_REQUEST_TIMEOUT_SECONDS
_DISCONNECT_CLOSE_TIMEOUT_SECONDS = 6.0
_DISCONNECT_TASK_SETTLE_TIMEOUT_SECONDS = 1.0
_LOG_REDACTED_KEYS = frozenset({"auth_token"})


class _ReceiverFailure:
    def __init__(self, exc: BaseException) -> None:
        self.exc = exc


def _wire_request_id_key(request_id: Any) -> str:
    """与 AgentServer 回包 ``request_id`` 对齐：统一为 str，避免 JSON 数字/字符串导致队列键不一致。"""
    if request_id is None:
        return ""
    return str(request_id)


def _redact_log_secrets(data: Any) -> Any:
    """Return a log-only copy with formal-route credentials removed."""
    if isinstance(data, dict):
        return {
            key: "[REDACTED]"
            if str(key).lower() in _LOG_REDACTED_KEYS
            else _redact_log_secrets(value)
            for key, value in data.items()
        }
    if isinstance(data, list):
        return [_redact_log_secrets(value) for value in data]
    if isinstance(data, tuple):
        return tuple(_redact_log_secrets(value) for value in data)
    return data


def _to_json(data: Any) -> str:
    """将任意对象序列化为日志友好的 JSON 字符串."""
    sanitized = _redact_log_secrets(data)
    try:
        return json.dumps(
            sanitized,
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
    except Exception:
        return repr(sanitized)


def _build_ws_origin(uri: str) -> str | None:
    """将 ws/wss URI 转为标准浏览器 Origin。"""
    try:
        parsed = urlsplit(uri)
    except ValueError:
        return None

    if not parsed.netloc:
        return None

    scheme = "https" if parsed.scheme == "wss" else "http"
    return f"{scheme}://{parsed.netloc}"


class AgentServerClient(ABC):
    """AgentServer WebSocket 客户端接口."""

    @abstractmethod
    async def connect(self, uri: str) -> None:
        """建立与 AgentServer 的 WebSocket 连接."""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """断开连接."""
        ...

    @abstractmethod
    def set_or_update_server_config(
        self,
        *,
        config: dict[str, Any],
        env: dict[str, str] | None = None,
    ) -> None:
        """缓存或更新服务端配置快照，供自定义 client 后续使用."""
        ...

    @abstractmethod
    async def send_request(self, envelope: E2AEnvelope) -> AgentResponse:
        """发送 E2A 信封，等待完整响应."""
        ...

    @abstractmethod
    async def send_request_stream(
        self, envelope: E2AEnvelope
    ) -> AsyncIterator[AgentResponseChunk]:
        """发送 E2A 信封，流式接收响应."""
        ...


def _e2a_to_wire(envelope: E2AEnvelope) -> dict[str, Any]:
    """E2AEnvelope → WebSocket JSON（与 AgentServer from_dict 对齐）。"""
    return envelope.to_dict()


def _unary_replay_fingerprint(payload: dict[str, Any]) -> str:
    """Hash stable request semantics, excluding Gateway-owned delivery metadata."""
    stable_payload = dict(payload)
    stable_payload.pop("timestamp", None)

    provenance = payload.get("provenance")
    if isinstance(provenance, dict):
        stable_payload["provenance"] = {
            key: value for key, value in provenance.items() if key != "converted_at"
        }

    channel_context = payload.get("channel_context")
    if isinstance(channel_context, dict):
        # A browser reconnect receives a new physical WebSocket delivery id.
        # MessageHandler binds each coalesced result back to its own request
        # metadata, so ws_id must not change the AgentServer operation identity.
        stable_payload["channel_context"] = {
            key: value for key, value in channel_context.items() if key != "ws_id"
        }

    canonical_payload = json.dumps(
        stable_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical_payload).hexdigest()


class WebSocketAgentServerClient(AgentServerClient):
    """
    基于 websockets 的 AgentServer WebSocket 客户端实现。

    协议约定：
    - 发送：JSON 对象为 E2AEnvelope.to_dict()（含 protocol_version、method、channel、params、is_stream 等）。
    - 接收（非流式）：一条 **E2AResponse** 线 JSON（或过渡期 legacy AgentResponse 形），解析为 AgentResponse。
    - 接收（流式）：多条 E2AResponse 线 JSON（或 legacy chunk），解析为 AgentResponseChunk。
    """

    def __init__(
        self, *, ping_interval: float | None = 30.0, ping_timeout: float | None = 300.0
    ) -> None:
        self._uri: str | None = None
        self._ws: Any = None
        self._connection_generation = 0
        self._lock = asyncio.Lock()
        self._reconnect_lock = asyncio.Lock()
        self._lifecycle_lock = asyncio.Lock()
        self._ping_interval = ping_interval
        self._ping_timeout = ping_timeout
        self._server_ready: bool = False
        # 消息分发机制：根据 request_id 路由到对应队列
        self._message_queues: dict[str, asyncio.Queue] = {}
        self._unary_operations: dict[
            str, tuple[str, Any, int, asyncio.Task[AgentResponse]]
        ] = {}
        self._queue_lock = asyncio.Lock()  # 保护队列操作的锁
        self._cancelled_request_ids: dict[str, object] = {}
        self._receiver_task: asyncio.Task | None = None
        self._running = False
        self._disconnecting = False
        # AgentServer send_push：旁路投递，勿进入与 request_id 绑定的 RPC 等待队列
        self._on_server_push: Callable[[dict[str, Any]], Awaitable[None]] | None = None

    def set_server_push_handler(
        self, handler: Callable[[dict[str, Any]], Awaitable[None]] | None
    ) -> None:
        """注册 Agent 主动推送处理回调（metadata 含 ``E2A_WIRE_SERVER_PUSH_KEY`` 的帧）。"""
        self._on_server_push = handler

    def _diagnostic_state(self, ws: Any | None = None) -> dict[str, Any]:
        target_ws = self._ws if ws is None else ws
        return {
            "uri": self._uri,
            "running": self._running,
            "server_ready": self._server_ready,
            "pending_requests": len(self._message_queues),
            "cancelled_requests": len(self._cancelled_request_ids),
            "ping_interval": self._ping_interval,
            "ping_timeout": self._ping_timeout,
            **describe_ws_peer(target_ws),
        }

    def set_or_update_server_config(
        self,
        *,
        config: dict[str, Any],
        env: dict[str, str] | None = None,
    ) -> None:
        """默认 WebSocket client 不处理服务端配置缓存，留给扩展 client 自行实现."""
        return None

    @property
    def server_ready(self) -> bool:
        """AgentServer 是否已发送 connection.ack 确认就绪."""
        return self._server_ready

    async def connect(self, uri: str) -> None:
        async with self._lifecycle_lock:
            if self._ws is not None:
                await self._run_disconnect_cleanup()
            try:
                await self._connect_transport(uri)
            except BaseException:
                await self._run_disconnect_cleanup()
                raise

    async def _connect_transport(self, uri: str) -> None:
        logger.info("[WebSocketAgentServerClient] 正在连接: %s", uri)
        self._uri = uri
        self._server_ready = False
        origin = _build_ws_origin(uri)
        try:
            from websockets.legacy.client import connect as legacy_connect

            connect_fn = legacy_connect
        except ImportError:
            import websockets

            connect_fn = websockets.connect
        self._ws = await connect_fn(
            uri,
            origin=origin,
            ping_interval=self._ping_interval,
            ping_timeout=self._ping_timeout,
            close_timeout=5.0,
            max_size=AGENT_WS_MAX_MESSAGE_BYTES,
        )
        self._connection_generation += 1
        logger.info("[WebSocketAgentServerClient] 已连接: %s", uri)

        # 读取 AgentServer 的 connection.ack 事件
        try:
            raw = await asyncio.wait_for(self._ws.recv(), timeout=5.0)
            logger.info("[WebSocketAgentServerClient] connect 首帧(raw): %s", raw)
            data = json.loads(raw)
            logger.info(
                "[WebSocketAgentServerClient] connect 首帧(parsed): %s", _to_json(data)
            )
            if data.get("type") == "event" and data.get("event") == "connection.ack":
                self._server_ready = True
                logger.info(
                    "[WebSocketAgentServerClient] 收到 connection.ack，AgentServer 已就绪"
                )
            else:
                logger.warning(
                    "[WebSocketAgentServerClient] 首帧非 connection.ack: %s",
                    data.get("type"),
                )
        except asyncio.TimeoutError:
            logger.warning("[WebSocketAgentServerClient] 等待 connection.ack 超时")
        except Exception as e:
            logger.warning(
                "[WebSocketAgentServerClient] 读取 connection.ack 失败: %s", e
            )

        # 启动消息接收和分发任务
        self._running = True
        self._receiver_task = asyncio.create_task(self._message_receiver_loop())
        logger.info("[WebSocketAgentServerClient] 消息接收任务已启动")

    async def _message_receiver_loop(self) -> None:
        """后台任务：从 WebSocket 接收消息并根据 request_id 分发到对应队列."""
        try:
            while self._running and self._ws is not None:
                try:
                    raw = await self._ws.recv()
                    data = json.loads(raw)
                    meta = data.get("metadata")
                    if isinstance(meta, dict) and meta.get(E2A_WIRE_SERVER_PUSH_KEY):
                        if self._on_server_push is not None:
                            asyncio.create_task(self._on_server_push(data))
                        else:
                            logger.warning(
                                "[WebSocketAgentServerClient] 收到 server_push 但未注册 handler，已丢弃: "
                                "request_id=%s",
                                data.get("request_id"),
                            )
                        continue
                    request_id = _wire_request_id_key(data.get("request_id"))

                    # 使用锁保护队列访问，避免竞态条件
                    async with self._queue_lock:
                        # 检查是否是已取消的请求，静默丢弃消息。
                        # 不放宽为"rid 已有新 queue 就放行"——_drain_and_remove_queue
                        # 删 queue 后会保留 _cancelled_request_ids 标记 2s，若在此窗口内
                        # 新请求复用同 rid 并建新 queue，放行旧请求的残余响应会串进新请求
                        # 的 queue，导致新请求拿到错误响应（响应串线，比超时更危险）。
                        # 完整 unary 响应不创建取消标记；流式结束或未完成的 unary
                        # 仍保留残余隔离，不能因同 rid 出现新 queue 而绕过。
                        if request_id in self._cancelled_request_ids:
                            logger.debug(
                                "[WebSocketAgentServerClient] 收到已取消请求的残余消息，已丢弃: request_id=%s",
                                request_id,
                            )
                            continue

                        if request_id and request_id in self._message_queues:
                            await self._message_queues[request_id].put(data)
                        else:
                            # 没有对应的队列（非预期情况）——可能是 E2A 编解码导致
                            # request_id 不匹配，此时 send_request 会等满 600s 超时。
                            # 提升为 warning 让问题可见，便于排查"到点没推送"类故障。
                            logger.warning(
                                "[WebSocketAgentServerClient] 收到无目标队列的消息（等待方将超时）: request_id=%s",
                                request_id,
                            )
                except asyncio.CancelledError:
                    break
                except PayloadTooBig as e:
                    logger.error(
                        "[WebSocketAgentServerClient] AgentServer 消息超过 WebSocket 限制: %s",
                        format_ws_diagnostics(
                            self._diagnostic_state(),
                            describe_ws_exception(e),
                        ),
                    )
                    await self._stop_receiver_after_fatal_error(e)
                    break
                except ConnectionClosed as e:
                    logger.info(
                        "[WebSocketAgentServerClient] AgentServer WebSocket 已关闭: %s",
                        format_ws_diagnostics(
                            self._diagnostic_state(),
                            describe_ws_exception(e),
                        ),
                    )
                    await self._stop_receiver_after_fatal_error(e)
                    break
                except Exception as e:
                    logger.exception(
                        "[WebSocketAgentServerClient] 消息接收循环异常: %s",
                        format_ws_diagnostics(
                            self._diagnostic_state(),
                            describe_ws_exception(e),
                        ),
                    )
                    await asyncio.sleep(0.1)  # 避免快速循环
        finally:
            logger.info("[WebSocketAgentServerClient] 消息接收任务已停止")

    async def _stop_receiver_after_fatal_error(self, exc: BaseException) -> None:
        detail = format_ws_diagnostics(
            self._diagnostic_state(),
            describe_ws_exception(exc),
        )
        self._running = False
        self._server_ready = False
        self._ws = None
        failure = _ReceiverFailure(exc)
        async with self._queue_lock:
            for queue in self._message_queues.values():
                queue.put_nowait(failure)
        logger.info(
            "[WebSocketAgentServerClient] 接收任务已停止并通知等待队列: %s", detail
        )

    async def disconnect(self) -> None:
        async with self._lifecycle_lock:
            await self._run_disconnect_cleanup()

    async def _run_disconnect_cleanup(self) -> None:
        cleanup = asyncio.create_task(
            self._disconnect_impl(),
            name="agent-server-disconnect-cleanup",
        )
        cancellation: asyncio.CancelledError | None = None
        while not cleanup.done():
            try:
                await asyncio.shield(cleanup)
            except asyncio.CancelledError as exc:
                if cancellation is None:
                    cancellation = exc
        cleanup.result()
        if cancellation is not None:
            raise cancellation

    async def _disconnect_impl(self) -> None:
        self._disconnecting = True
        ws = self._ws
        try:
            # Detach lifecycle state first so requests fail closed while the
            # old transport and retained operations are being settled.
            self._running = False
            self._ws = None
            self._uri = None
            self._server_ready = False
            receiver_task = self._receiver_task
            self._receiver_task = None
            if receiver_task is not None and not receiver_task.done():
                receiver_task.cancel()
                try:
                    await receiver_task
                except asyncio.CancelledError:
                    pass
                except Exception as exc:
                    logger.warning(
                        "AgentServer receiver stopped with an error during disconnect: %s",
                        describe_ws_exception(exc),
                    )

            disconnect_failure = _ReceiverFailure(
                ConnectionError("AgentServer client disconnected")
            )
            async with self._queue_lock:
                retained_tasks = [
                    task for _, _, _, task in self._unary_operations.values()
                ]
                for queue in self._message_queues.values():
                    queue.put_nowait(disconnect_failure)

            # A retained owner may be blocked inside ws.send(), before it can
            # read the injected queue failure. Close the transport first.
            if ws is not None:
                try:
                    await asyncio.wait_for(
                        ws.close(), timeout=_DISCONNECT_CLOSE_TIMEOUT_SECONDS
                    )
                except Exception as exc:
                    logger.warning(
                        "关闭 AgentServer WebSocket 时异常: %s",
                        format_ws_diagnostics(
                            self._diagnostic_state(ws),
                            describe_ws_exception(exc),
                        ),
                    )

            if retained_tasks:
                _, pending = await asyncio.wait(
                    retained_tasks,
                    timeout=_DISCONNECT_TASK_SETTLE_TIMEOUT_SECONDS,
                )
                for task in pending:
                    task.cancel()
                await asyncio.gather(*retained_tasks, return_exceptions=True)

            async with self._queue_lock:
                self._message_queues.clear()
                self._unary_operations.clear()
                self._cancelled_request_ids.clear()
        finally:
            self._disconnecting = False

        if ws is not None:
            logger.info("[WebSocketAgentServerClient] 已断开")

    def _ensure_connected(self) -> None:
        if self._ws is None:
            raise RuntimeError("未连接 AgentServer，请先调用 connect(uri)")

    async def _ensure_connected_for_request(self) -> tuple[Any, int]:
        if self._ws is not None:
            return self._ws, self._connection_generation
        uri = self._uri
        if not uri:
            raise RuntimeError("未连接 AgentServer，请先调用 connect(uri)")
        async with self._reconnect_lock:
            if self._ws is not None:
                return self._ws, self._connection_generation
            async with self._lifecycle_lock:
                if self._ws is not None:
                    return self._ws, self._connection_generation
                if self._uri != uri:
                    raise RuntimeError("AgentServer WebSocket connection closed")
                logger.info(
                    "[WebSocketAgentServerClient] WebSocket 已断开，准备按需重连: %s",
                    format_ws_diagnostics(self._diagnostic_state(), uri=uri),
                )
                try:
                    await self._connect_transport(uri)
                except BaseException:
                    await self._run_disconnect_cleanup()
                    raise
                if self._ws is None:
                    raise RuntimeError("AgentServer WebSocket connection closed")
                return self._ws, self._connection_generation

    def _connection_matches(self, expected_ws: Any, expected_generation: int) -> bool:
        return (
            self._ws is expected_ws
            and self._connection_generation == expected_generation
        )

    async def _send_wire_payload(
        self,
        payload: dict[str, Any],
        *,
        expected_ws: Any,
        expected_generation: int,
    ) -> None:
        if not self._connection_matches(expected_ws, expected_generation):
            raise RuntimeError("AgentServer WebSocket connection closed")
        try:
            await expected_ws.send(json.dumps(payload, ensure_ascii=False))
        except (ConnectionClosed, OSError) as exc:
            logger.info(
                "[WebSocketAgentServerClient] AgentServer WebSocket 发送失败，连接将重置: %s",
                format_ws_diagnostics(
                    self._diagnostic_state(expected_ws),
                    describe_ws_exception(exc),
                    request_id=_wire_request_id_key(payload.get("request_id")),
                    channel=payload.get("channel"),
                    method=payload.get("method"),
                ),
            )
            if self._connection_matches(expected_ws, expected_generation):
                await self._stop_receiver_after_fatal_error(exc)
            raise RuntimeError("AgentServer WebSocket connection closed") from exc

    async def send_request(self, envelope: E2AEnvelope) -> AgentResponse:
        (
            connection_ws,
            connection_generation,
        ) = await self._ensure_connected_for_request()
        # 非流式 API 必须与 AgentServer 的 unary 路径一致；忽略信封上误带的 is_stream=True。
        envelope.is_stream = False
        rid = _wire_request_id_key(envelope.request_id)
        payload = _e2a_to_wire(envelope)
        fingerprint = _unary_replay_fingerprint(payload)
        logger.info(
            "[E2A][out][nostream] request_id=%s channel=%s method=%s is_stream=%s",
            rid,
            envelope.channel,
            envelope.method,
            envelope.is_stream,
        )

        async with self._queue_lock:
            if not self._connection_matches(
                connection_ws,
                connection_generation,
            ):
                raise RuntimeError("AgentServer WebSocket connection closed")
            retained = self._unary_operations.get(rid)
            if retained is not None:
                (
                    retained_fingerprint,
                    retained_ws,
                    retained_generation,
                    task,
                ) = retained
                if (
                    retained_ws is not connection_ws
                    or retained_generation != connection_generation
                ):
                    raise RuntimeError("AgentServer WebSocket connection closed")
                if retained_fingerprint != fingerprint:
                    raise RuntimeError(
                        "WebSocketAgentServerClient: duplicate in-flight "
                        f"request_id={rid!r} changed its unary payload"
                    )
                logger.info(
                    "[WebSocketAgentServerClient] coalescing exact in-flight "
                    "unary replay: request_id=%s",
                    rid,
                )
            else:
                if rid in self._message_queues:
                    raise RuntimeError(
                        "WebSocketAgentServerClient: duplicate in-flight "
                        f"request_id={rid!r}; refusing to mix unary and stream waiters"
                    )
                task = asyncio.create_task(
                    self._run_retained_unary(
                        rid,
                        payload,
                        connection_ws,
                        connection_generation,
                    ),
                    name=f"agent-server-unary:{rid}",
                )
                self._unary_operations[rid] = (
                    fingerprint,
                    connection_ws,
                    connection_generation,
                    task,
                )

        return await asyncio.shield(task)

    async def _run_retained_unary(
        self,
        rid: str,
        payload: dict[str, Any],
        connection_ws: Any,
        connection_generation: int,
    ) -> AgentResponse:
        task = asyncio.current_task()
        try:
            return await self._send_unary_once(
                rid,
                payload,
                connection_ws,
                connection_generation,
            )
        except asyncio.CancelledError as exc:
            if self._disconnecting:
                raise RuntimeError("AgentServer WebSocket connection closed") from exc
            raise
        finally:
            async with self._queue_lock:
                retained = self._unary_operations.get(rid)
                if retained is not None and retained[3] is task:
                    del self._unary_operations[rid]

    async def _send_unary_once(
        self,
        rid: str,
        payload: dict[str, Any],
        connection_ws: Any,
        connection_generation: int,
    ) -> AgentResponse:
        queue = asyncio.Queue()
        async with self._queue_lock:
            if not self._connection_matches(
                connection_ws,
                connection_generation,
            ):
                raise RuntimeError("AgentServer WebSocket connection closed")
            if rid in self._message_queues:
                raise RuntimeError(
                    f"WebSocketAgentServerClient: duplicate in-flight request_id={rid!r}; "
                    "refusing to register queue (would mis-route responses, e.g. stream chunks to unary waiters)."
                )
            self._message_queues[rid] = queue

        unary_completed = False
        try:
            # 发送请求
            async with self._lock:
                await self._send_wire_payload(
                    payload,
                    expected_ws=connection_ws,
                    expected_generation=connection_generation,
                )

            try:
                data = await asyncio.wait_for(
                    queue.get(), timeout=_UNARY_REQUEST_TIMEOUT_SECONDS
                )
                if isinstance(data, _ReceiverFailure):
                    raise RuntimeError(
                        "AgentServer WebSocket connection closed"
                    ) from data.exc
            except asyncio.TimeoutError as e:
                logger.warning(
                    "[WebSocketAgentServerClient] 非流式请求超时: request_id=%s timeout=%ss",
                    rid,
                    _UNARY_REQUEST_TIMEOUT_SECONDS,
                )
                raise RuntimeError(
                    f"AgentServer 非流式请求超时 (request_id={rid}, timeout={_UNARY_REQUEST_TIMEOUT_SECONDS}s)"
                ) from e
            resp = parse_agent_server_wire_unary(data)
            unary_completed = True
            return resp
        finally:
            # A parsed unary response (including application rejection) ends the
            # operation. Quarantining that ID drops an immediate exact replay's
            # response, which P2 needs to reauthorize a new media owner.
            await self._drain_and_remove_queue(
                rid, queue, quarantine=not unary_completed
            )

    async def send_request_stream(
        self, envelope: E2AEnvelope
    ) -> AsyncIterator[AgentResponseChunk]:
        (
            connection_ws,
            connection_generation,
        ) = await self._ensure_connected_for_request()
        envelope.is_stream = True
        rid = _wire_request_id_key(envelope.request_id)
        logger.info(
            "[E2A][out][stream] request_id=%s channel=%s method=%s is_stream=%s",
            rid,
            envelope.channel,
            envelope.method,
            envelope.is_stream,
        )
        logger.debug(
            "[WebSocketAgentServerClient] 发送请求(流式) E2A: %s",
            _to_json(envelope.to_dict()),
        )

        # 创建该请求的消息队列
        queue = asyncio.Queue()
        async with self._queue_lock:
            if not self._connection_matches(
                connection_ws,
                connection_generation,
            ):
                raise RuntimeError("AgentServer WebSocket connection closed")
            if rid in self._message_queues or rid in self._unary_operations:
                raise RuntimeError(
                    f"WebSocketAgentServerClient: duplicate in-flight request_id={rid!r}; "
                    "refusing to register queue (would mis-route responses, e.g. stream chunks to unary waiters)."
                )
            self._message_queues[rid] = queue

        try:
            # 发送请求
            async with self._lock:
                payload = _e2a_to_wire(envelope)
                logger.info(
                    "[WebSocketAgentServerClient] 发送请求(流式) payload: %s",
                    _to_json(payload),
                )
                await self._send_wire_payload(
                    payload,
                    expected_ws=connection_ws,
                    expected_generation=connection_generation,
                )

            # 从队列中接收流式响应
            chunk_count = 0
            saw_complete = False
            while True:
                if saw_complete:
                    try:
                        data = await asyncio.wait_for(
                            queue.get(),
                            timeout=_STREAM_TRAILING_MESSAGE_GRACE_SECONDS,
                        )
                    except asyncio.TimeoutError:
                        break
                else:
                    data = await queue.get()
                if isinstance(data, _ReceiverFailure):
                    raise RuntimeError(
                        "AgentServer WebSocket connection closed"
                    ) from data.exc
                chunk = parse_agent_server_wire_chunk(data)
                chunk_count += 1
                if chunk_count <= 3:
                    _pl = getattr(chunk, "payload", None) or {}
                    _et = _pl.get("event_type", "") if isinstance(_pl, dict) else ""
                    logger.info(
                        "[WebSocketAgentServerClient] stream chunk received:"
                        " request_id=%s seq=%s event_type=%s",
                        rid,
                        chunk_count,
                        _et,
                    )
                yield chunk
                if chunk.is_complete:
                    saw_complete = True
            logger.info(
                "[WebSocketAgentServerClient] 流式响应结束: request_id=%s 共 %s 个 chunk",
                rid,
                chunk_count,
            )
        except asyncio.CancelledError:
            logger.info(
                "[WebSocketAgentServerClient] 流式接收被取消: request_id=%s", rid
            )
            raise
        finally:
            # 清理队列
            await self._drain_and_remove_queue(rid, queue)

    async def _drain_and_remove_queue(
        self,
        rid: str,
        expected_queue: asyncio.Queue,
        *,
        quarantine: bool = True,
    ) -> None:
        """Drain one owned queue and remove its registration only on identity match.

        A replaced same-id registration belongs to a different connection owner
        and must remain untouched. Only a fully parsed unary response may skip
        residual quarantine; stream cleanup and incomplete unary keep the fence.
        """
        async with self._queue_lock:
            queue = self._message_queues.get(rid)
            owns_registration = queue is expected_queue
            cancellation_token = None
            if owns_registration:
                if quarantine:
                    # Mark before deleting so residual frames cannot be routed
                    # to a later same-id owner on this connection.
                    cancellation_token = object()
                    self._cancelled_request_ids[rid] = cancellation_token
                del self._message_queues[rid]

            # Always drain only the caller-owned queue. A generator from an old
            # connection may close after a same-id queue is registered on a new
            # generation and must never delete or drain that replacement.
            drained_count = 0
            while True:
                try:
                    expected_queue.get_nowait()
                    drained_count += 1
                except asyncio.QueueEmpty:
                    break
            logger.debug(
                "[WebSocketAgentServerClient] 队列已清空并移除: request_id=%s 清理消息数=%d",
                rid,
                drained_count,
            )
            if cancellation_token is not None:
                asyncio.create_task(
                    self._delayed_cleanup_cancelled_request_id(
                        rid,
                        cancellation_token,
                    )
                )

    async def _delayed_cleanup_cancelled_request_id(
        self,
        rid: str,
        cancellation_token: object,
    ) -> None:
        """延迟清理已取消的 request_id 标记.

        等待一段时间后清理，确保 AgentServer 的残余消息能够被静默丢弃而不打印日志。
        """
        # 等待足够时间让 AgentServer 的残余消息被接收和丢弃
        await asyncio.sleep(2.0)  # 2秒应该足够
        async with self._queue_lock:
            if self._cancelled_request_ids.get(rid) is not cancellation_token:
                return
            del self._cancelled_request_ids[rid]
            logger.debug(
                "[WebSocketAgentServerClient] 已取消标记已清理: request_id=%s",
                rid,
            )


# ---------------------------------------------------------------------------
# Mock AgentServer（协议兼容，供示例或测试使用）
# ---------------------------------------------------------------------------


async def mock_agent_server_handler(ws: Any) -> None:
    """
    协议兼容的 Mock AgentServer：按 is_stream 回 E2AResponse 线 JSON（与生产 AgentServer 一致）。
    """
    import websockets

    from jiuwenswarm.common.e2a.wire_codec import (
        encode_agent_chunk_for_wire,
        encode_agent_response_for_wire,
    )

    try:
        while True:
            raw = await ws.recv()
            data = json.loads(raw)
            req_id = data.get("request_id", "")
            ch_id = data.get("channel") or data.get("channel_id", "")
            params = data.get("params", {})
            is_stream = data.get("is_stream", False)
            params_str = (
                json.dumps(params, ensure_ascii=False)
                if isinstance(params, dict)
                else str(params)
            )

            if is_stream:
                for i, part in enumerate(["流式-1 ", "流式-2 ", "流式-3(完)"]):
                    chunk = AgentResponseChunk(
                        request_id=req_id,
                        channel_id=ch_id,
                        payload={"content": part},
                        is_complete=i == 2,
                    )
                    wire = encode_agent_chunk_for_wire(
                        chunk, response_id=req_id, sequence=i
                    )
                    await ws.send(json.dumps(wire, ensure_ascii=False))
            else:
                meta = data.get("metadata") or data.get("channel_context")
                if meta is not None and not isinstance(meta, dict):
                    meta = None
                resp = AgentResponse(
                    request_id=req_id,
                    channel_id=ch_id,
                    ok=True,
                    payload={"content": f"Echo: {params_str}"},
                    metadata=dict(meta) if isinstance(meta, dict) else None,
                )
                wire = encode_agent_response_for_wire(resp, response_id=req_id)
                await ws.send(json.dumps(wire, ensure_ascii=False))
    except websockets.exceptions.ConnectionClosed:
        pass
    except Exception as e:
        logger.exception("[MockAgentServer] 处理异常: %s", e)


async def run_mock_agent_server(
    host: str = "127.0.0.1",
    port: int = 8000,
) -> Any:
    """
    启动 Mock AgentServer（使用 mock_agent_server_handler），监听 host:port。
    返回 Server，调用方需在结束时 server.close(); await server.wait_closed()。
    websockets 14+ 使用 legacy.server.serve，与 legacy 客户端一致，避免 InvalidMessage。
    """
    try:
        from websockets.legacy.server import serve as legacy_serve

        server = await legacy_serve(mock_agent_server_handler, host, port)
    except ImportError:
        import websockets

        server = await websockets.serve(mock_agent_server_handler, host, port)
    logger.info("[MockAgentServer] 已启动: ws://%s:%s", host, port)
    return server


# ---------------------------------------------------------------------------
# 自验证：内存 Mock 服务端 + main
# ---------------------------------------------------------------------------


async def _run_verification() -> None:
    """用内存 Mock 服务端验证 WebSocketAgentServerClient 的 connect/send_request/send_request_stream."""
    from jiuwenswarm.common.e2a.gateway_normalize import e2a_from_agent_fields

    port = 18765
    uri = f"ws://127.0.0.1:{port}"
    server = await run_mock_agent_server("127.0.0.1", port)
    logger.info("[main] Mock AgentServer 已启动: %s", uri)

    client = WebSocketAgentServerClient()
    try:
        await client.connect(uri)

        # 1. 非流式请求
        req1 = e2a_from_agent_fields(
            request_id="req-1",
            channel_id="ch-1",
            session_id="sess-1",
            params={"message": "你好"},
        )
        resp1 = await client.send_request(req1)
        assert resp1.request_id == "req-1"
        assert resp1.ok is True
        assert "Echo:" in str(resp1.payload)
        logger.info("[main] 非流式验证通过: payload=%s", resp1.payload)

        # 2. 流式请求
        req2 = e2a_from_agent_fields(
            request_id="req-2",
            channel_id="ch-1",
            session_id="sess-1",
            params={"message": "流式测试"},
        )
        chunks = []
        async for ch in client.send_request_stream(req2):
            chunks.append(ch)
        assert len(chunks) == 3
        assert chunks[-1].is_complete
        full_content = "".join(
            c.payload.get("content", "") for c in chunks if c.payload
        )
        logger.info(
            "[main] 流式验证通过: 共 %s 个 chunk, 拼接内容=%r",
            len(chunks),
            full_content,
        )
    finally:
        await client.disconnect()
        server.close()
        await server.wait_closed()
    logger.info("[main] 验证完成，功能正常")


def main() -> None:
    """入口：配置日志并运行自验证."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s.%(msecs)03d %(name)s %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    asyncio.run(_run_verification())


if __name__ == "__main__":
    main()
