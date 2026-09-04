# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Bounded lifecycle owner for one official OpenAI Realtime WebSocket.

This module owns transport negotiation, Provider-event replay identity, client
event sequencing, and unique socket finalization.  It deliberately has no Live
Voice Runtime, Agent, Tool, Task, media, presentation, or history authority.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import math
import unicodedata
from collections import OrderedDict, deque
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol
from urllib.parse import urlencode, urlparse, urlunparse


MAX_REALTIME_WIRE_MESSAGE_BYTES = 1_048_576
# The close frame is sent before this WebSocket-library timeout starts.  Keep
# it below the Speech adapter's 50 ms cleanup-attempt budget so an ordinary
# peer that does not acknowledge close cannot turn a successful stream into an
# indefinitely retained cleanup.
REALTIME_SOCKET_CLOSE_TIMEOUT_SECONDS = 0.025
_MAX_SAFE_LABEL_CHARS = 256
_MAX_SAFE_LABEL_UTF8_BYTES = 1_024
_MAX_API_KEY_CHARS = 4_096
_MAX_PROVIDER_EVENTS = 65_536
_MAX_SOCKET_CLEANUP_RESOURCES = 32
_MAX_SOCKET_CLOSE_TOMBSTONES = 4_096


class OpenAIRealtimeSessionError(RuntimeError):
    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


class RealtimeSocket(Protocol):
    async def send(self, message: str) -> None: ...

    async def recv(self) -> str | bytes: ...

    async def close(self) -> None: ...


RealtimeSocketFactory = Callable[
    [str, Mapping[str, str], float], Awaitable[RealtimeSocket]
]


@dataclass(frozen=True, slots=True)
class RealtimeTransport:
    """One allocated Realtime socket without product-level authority."""

    socket: RealtimeSocket = field(repr=False)

    async def send(self, message: str) -> None:
        await self.socket.send(message)

    async def recv(self) -> str | bytes:
        return await self.socket.recv()


@dataclass(frozen=True, slots=True)
class RealtimeSocketCleanupSnapshot:
    retained_task_count: int
    failed_resource_count: int
    incomplete_kinds: tuple[str, ...]

    @property
    def clean(self) -> bool:
        return self.retained_task_count == self.failed_resource_count == 0


@dataclass(frozen=True, slots=True)
class _CleanupOutcome:
    succeeded: bool
    process_control: BaseException | None = field(default=None, repr=False)


@dataclass(frozen=True, slots=True)
class _SocketCleanupEntry:
    key: int
    socket: RealtimeSocket = field(repr=False)


class RealtimeSocketCleanupOwner:
    """Bound, retain, and deduplicate socket close attempts for one owner."""

    def __init__(
        self,
        *,
        attempt_timeout_seconds: float = 0.05,
        close_timeout_seconds: float = 0.1,
        max_incomplete_resources: int = _MAX_SOCKET_CLEANUP_RESOURCES,
    ) -> None:
        self._attempt_timeout_seconds = _bounded_timeout(
            attempt_timeout_seconds,
            field_name="attempt_timeout_seconds",
            maximum=5.0,
        )
        self._close_timeout_seconds = _bounded_timeout(
            close_timeout_seconds,
            field_name="close_timeout_seconds",
            maximum=5.0,
        )
        if (
            type(max_incomplete_resources) is not int
            or not 0 < max_incomplete_resources <= 4_096
        ):
            raise ValueError("max_incomplete_resources must be an integer in [1, 4096]")
        self._max_incomplete_resources = max_incomplete_resources
        self._tasks: dict[asyncio.Task[_CleanupOutcome], _SocketCleanupEntry] = {}
        self._by_key: dict[int, asyncio.Task[_CleanupOutcome]] = {}
        self._attempt_results: dict[
            asyncio.Task[_CleanupOutcome], asyncio.Future[bool]
        ] = {}
        self._attempt_deadlines: dict[asyncio.Task[_CleanupOutcome], float] = {}
        self._failed: dict[int, _SocketCleanupEntry] = {}
        self._succeeded: OrderedDict[int, RealtimeSocket] = OrderedDict()
        self._process_controls: deque[BaseException] = deque(
            maxlen=max_incomplete_resources
        )

    def snapshot(self) -> RealtimeSocketCleanupSnapshot:
        self._prune()
        return RealtimeSocketCleanupSnapshot(
            retained_task_count=len(self._tasks),
            failed_resource_count=len(self._failed),
            incomplete_kinds=tuple(
                "socket" for _ in range(len(self._tasks) + len(self._failed))
            ),
        )

    def require_capacity(self, *, reserved_resources: int = 0) -> None:
        if type(reserved_resources) is not int or reserved_resources < 0:
            raise ValueError("reserved_resources must be a non-negative integer")
        snapshot = self.snapshot()
        if (
            snapshot.retained_task_count
            + snapshot.failed_resource_count
            + reserved_resources
            > self._max_incomplete_resources
        ):
            raise OpenAIRealtimeSessionError(
                "REALTIME_SOCKET_CLEANUP_CAPACITY",
                "Realtime socket cleanup capacity is exhausted",
            )

    async def close_socket(self, socket: RealtimeSocket) -> bool:
        self._prune()
        self._raise_process_control()
        key = id(socket)
        succeeded = self._succeeded.get(key)
        if succeeded is socket:
            self._succeeded.move_to_end(key)
            return True
        task = self._by_key.get(key)
        if task is not None:
            entry = self._tasks.get(task)
            if entry is None or entry.socket is not socket:
                return False
            return await self._await_shared_attempt(task)
        entry = self._failed.get(key)
        if entry is not None:
            if entry.socket is not socket:
                return False
            del self._failed[key]
        else:
            entry = _SocketCleanupEntry(key, socket)
        if len(self._tasks) + len(self._failed) >= self._max_incomplete_resources:
            return False
        task = asyncio.create_task(_await_socket_close(socket))
        self._track_attempt(task, entry)
        return await self._await_shared_attempt(task)

    async def close(self) -> RealtimeSocketCleanupSnapshot:
        self._prune()
        for entry in tuple(self._failed.values()):
            if len(self._tasks) >= self._max_incomplete_resources:
                break
            self._failed.pop(entry.key, None)
            task = asyncio.create_task(_await_socket_close(entry.socket))
            self._track_attempt(task, entry)
        tasks = tuple(self._tasks)
        if tasks:
            _, pending = await asyncio.wait(
                tasks,
                timeout=self._close_timeout_seconds,
            )
            for task in pending:
                task.cancel()
        self._prune()
        self._raise_process_control()
        return self.snapshot()

    def _track_attempt(
        self,
        task: asyncio.Task[_CleanupOutcome],
        entry: _SocketCleanupEntry,
    ) -> None:
        loop = asyncio.get_running_loop()
        self._tasks[task] = entry
        self._by_key[entry.key] = task
        self._attempt_results[task] = loop.create_future()
        self._attempt_deadlines[task] = loop.time() + self._attempt_timeout_seconds
        task.add_done_callback(self._release)

    async def _await_shared_attempt(
        self,
        task: asyncio.Task[_CleanupOutcome],
    ) -> bool:
        result = self._attempt_results.get(task)
        deadline = self._attempt_deadlines.get(task)
        if result is None or deadline is None:
            return False
        try:
            remaining = max(0.0, deadline - asyncio.get_running_loop().time())
            done, _ = await asyncio.wait({result}, timeout=remaining)
        except asyncio.CancelledError:
            raise
        if result not in done and not result.done():
            result.set_result(False)
        self._prune()
        self._raise_process_control()
        return result.result()

    def _prune(self) -> None:
        for task in tuple(self._tasks):
            if task.done():
                self._release(task)

    def _release(self, task: asyncio.Task[_CleanupOutcome]) -> None:
        entry = self._tasks.pop(task, None)
        if entry is None:
            return
        result = self._attempt_results.pop(task, None)
        self._attempt_deadlines.pop(task, None)
        if self._by_key.get(entry.key) is task:
            del self._by_key[entry.key]
        if task.cancelled():
            if result is not None and not result.done():
                result.set_result(False)
            self._failed[entry.key] = entry
            return
        outcome = task.result()
        if result is not None and not result.done():
            result.set_result(outcome.succeeded)
        if outcome.process_control is not None:
            self._process_controls.append(outcome.process_control)
        if outcome.succeeded:
            self._succeeded[entry.key] = entry.socket
            self._succeeded.move_to_end(entry.key)
            while len(self._succeeded) > _MAX_SOCKET_CLOSE_TOMBSTONES:
                self._succeeded.popitem(last=False)
        else:
            self._failed[entry.key] = entry

    def _raise_process_control(self) -> None:
        if self._process_controls:
            raise self._process_controls.popleft() from None


async def _await_socket_close(socket: RealtimeSocket) -> _CleanupOutcome:
    try:
        await socket.close()
    except asyncio.CancelledError:
        raise
    except (KeyboardInterrupt, SystemExit, GeneratorExit) as exc:
        return _CleanupOutcome(False, process_control=exc)
    except Exception:
        return _CleanupOutcome(False)
    return _CleanupOutcome(True)


class RealtimeSessionState(StrEnum):
    NEW = "new"
    OPENING = "opening"
    OPEN = "open"
    FAILED = "failed"
    CLOSING = "closing"
    CLOSED = "closed"


@dataclass(frozen=True, slots=True)
class RealtimeSessionSnapshot:
    state: RealtimeSessionState
    provider_session_id: str | None = field(repr=False)
    provider_event_count: int
    client_event_count: int
    primary_error_reason: str | None
    close_error_reason: str | None
    close_complete: bool


@dataclass(frozen=True, slots=True)
class OpenAIRealtimeEvent:
    event_type: str
    event_id: str
    _canonical_bytes: bytes = field(repr=False)

    def to_dict(self) -> dict[str, object]:
        value = json.loads(self._canonical_bytes)
        assert type(value) is dict
        return value


@dataclass(frozen=True, slots=True)
class OpenAIRealtimeSessionConfig:
    api_key: str = field(repr=False)
    model: str
    api_base: str = "https://api.openai.com/v1"
    connect_timeout_seconds: float = 5.0
    operation_timeout_seconds: float = 30.0
    close_timeout_seconds: float = REALTIME_SOCKET_CLOSE_TIMEOUT_SECONDS
    max_provider_events: int = 4_096

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "api_base", validate_official_openai_api_base(self.api_base)
        )
        _required_secret(self.api_key)
        _safe_label(self.model, "model")
        _bounded_timeout(
            self.connect_timeout_seconds,
            field_name="connect_timeout_seconds",
            maximum=30.0,
        )
        _bounded_timeout(
            self.operation_timeout_seconds,
            field_name="operation_timeout_seconds",
            maximum=300.0,
        )
        _bounded_timeout(
            self.close_timeout_seconds,
            field_name="close_timeout_seconds",
            maximum=5.0,
        )
        if (
            type(self.max_provider_events) is not int
            or not 2 <= self.max_provider_events <= _MAX_PROVIDER_EVENTS
        ):
            raise ValueError("max_provider_events must be an integer in [2, 65536]")


def validate_official_openai_api_base(value: object) -> str:
    if type(value) is not str or not value.strip():
        raise ValueError("official OpenAI API base is required")
    parsed = urlparse(value)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "api.openai.com"
        or parsed.port not in {None, 443}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path.rstrip("/") != "/v1"
    ):
        raise ValueError("Realtime requires the official OpenAI HTTPS API base")
    return "https://api.openai.com/v1"


def official_realtime_url(
    api_base: object,
    *,
    model: object | None = None,
    intent: object | None = None,
) -> str:
    """Build one official Realtime URL with exactly one activation selector."""

    base = validate_official_openai_api_base(api_base)
    if (model is None) == (intent is None):
        raise ValueError("Realtime URL requires exactly one of model or intent")
    if model is not None:
        query = {"model": _safe_label(model, "model")}
    else:
        if intent != "transcription":
            raise ValueError("Realtime intent must be the exact transcription value")
        query = {"intent": "transcription"}
    parsed = urlparse(base)
    path = f"{parsed.path.rstrip('/')}/realtime"
    return urlunparse(("wss", parsed.netloc, path, "", urlencode(query), ""))


async def default_realtime_socket_factory(
    url: str, headers: Mapping[str, str], timeout_seconds: float,
    *, connection_factory: object | None = None,
) -> RealtimeSocket:
    import websockets

    kwargs: dict[str, object] = {
        "open_timeout": timeout_seconds,
        "close_timeout": REALTIME_SOCKET_CLOSE_TIMEOUT_SECONDS,
        "max_size": MAX_REALTIME_WIRE_MESSAGE_BYTES,
        "compression": None,
    }
    parameter = (
        "additional_headers"
        if "additional_headers" in inspect.signature(websockets.connect).parameters
        else "extra_headers"
    )
    kwargs[parameter] = dict(headers)
    # Optional passive observer; older supported websockets keeps its old path.
    if connection_factory is not None and "create_connection" in inspect.signature(websockets.connect).parameters:
        kwargs["create_connection"] = connection_factory
    return await websockets.connect(url, **kwargs)


@dataclass(frozen=True, slots=True)
class _SocketCloseResult:
    complete: bool
    error_reason: str | None = None
    process_control: BaseException | None = field(default=None, repr=False)


class _UniqueSocketFinalizer:
    """Retain exactly one close task even when callers spend their wait budget."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._task: asyncio.Task[BaseException | None] | None = None

    async def close(
        self, socket: RealtimeSocket, *, timeout_seconds: float
    ) -> _SocketCloseResult:
        async with self._lock:
            task = self._task
            if task is None:
                task = asyncio.create_task(_close_socket(socket))
                self._task = task
        done, _ = await asyncio.wait({task}, timeout=timeout_seconds)
        if task not in done:
            return _SocketCloseResult(complete=False)
        failure = task.result()
        if failure is None:
            return _SocketCloseResult(complete=True)
        if _is_process_control(failure):
            return _SocketCloseResult(complete=True, process_control=failure)
        return _SocketCloseResult(
            complete=True,
            error_reason="REALTIME_TRANSPORT_CLOSE_FAILED",
        )


async def _close_socket(socket: RealtimeSocket) -> BaseException | None:
    try:
        await socket.close()
    except BaseException as exc:
        return exc
    return None


class OpenAIRealtimeSession:
    """The unique owner of one bounded Realtime WebSocket lifecycle."""

    def __init__(
        self,
        config: OpenAIRealtimeSessionConfig,
        *,
        socket_factory: RealtimeSocketFactory | None = None,
    ) -> None:
        if not isinstance(config, OpenAIRealtimeSessionConfig):
            raise TypeError("config must be OpenAIRealtimeSessionConfig")
        self._config = config
        self._socket_factory = socket_factory or default_realtime_socket_factory
        self._state = RealtimeSessionState.NEW
        self._state_lock = asyncio.Lock()
        self._send_lock = asyncio.Lock()
        self._receive_lock = asyncio.Lock()
        self._socket: RealtimeSocket | None = None
        self._finalizer = _UniqueSocketFinalizer()
        self._provider_session_id: str | None = None
        self._provider_events: OrderedDict[
            str, tuple[bytes, OpenAIRealtimeEvent]
        ] = OrderedDict()
        self._client_event_count = 0
        self._primary_error_reason: str | None = None
        self._close_error_reason: str | None = None
        self._close_complete = False

    async def open(self, *, session_update: Mapping[str, object]) -> None:
        async with self._state_lock:
            if self._state is not RealtimeSessionState.NEW:
                error = OpenAIRealtimeSessionError(
                    "REALTIME_STATE_INVALID",
                    "Realtime session can only be opened once",
                )
                self._record_primary_locked(error.reason)
                raise error
            self._state = RealtimeSessionState.OPENING
        try:
            update = _client_payload(session_update, field_name="session_update")
        except OpenAIRealtimeSessionError as exc:
            failure = exc.with_traceback(None)
            session_update = {}
            await self._record_primary(failure.reason)
            async with self._state_lock:
                self._state = RealtimeSessionState.CLOSED
                self._close_complete = True
            raise failure from None

        url = official_realtime_url(
            self._config.api_base,
            model=self._config.model,
        )
        try:
            socket, connect_failure = await _connect_socket(
                self._socket_factory,
                url=url,
                config=self._config,
                timeout_seconds=self._config.connect_timeout_seconds,
            )
        except asyncio.CancelledError:
            async with self._state_lock:
                self._state = RealtimeSessionState.CLOSED
                self._close_complete = True
            raise
        except (KeyboardInterrupt, SystemExit, GeneratorExit):
            async with self._state_lock:
                self._state = RealtimeSessionState.CLOSED
                self._close_complete = True
            raise
        if connect_failure is not None:
            error = OpenAIRealtimeSessionError(
                connect_failure,
                (
                    "Realtime Provider connect timed out"
                    if connect_failure == "REALTIME_PROVIDER_TIMEOUT"
                    else "Realtime Provider connect failed"
                ),
            )
            await self._record_primary(error.reason)
            async with self._state_lock:
                self._state = RealtimeSessionState.CLOSED
                self._close_complete = True
            session_update = {}
            update = {}
            raise error from None
        assert socket is not None
        self._socket = socket

        try:
            created = await self._receive_event_internal(allow_opening=True)
            provider_session_id = _negotiated_session_id(
                created,
                expected_type="session.created",
                expected_session_id=None,
            )
            self._provider_session_id = provider_session_id
            await self._send_event_internal(
                "session.update",
                {"session": update},
                allow_opening=True,
            )
            updated = await self._receive_event_internal(allow_opening=True)
            _negotiated_session_id(
                updated,
                expected_type="session.updated",
                expected_session_id=provider_session_id,
            )
        except asyncio.CancelledError:
            await self._close_after_open_failure()
            raise
        except (KeyboardInterrupt, SystemExit, GeneratorExit):
            await self._close_after_open_failure()
            raise
        except OpenAIRealtimeSessionError as exc:
            failure = exc.with_traceback(None)
            session_update = {}
            update = {}
            created = None
            updated = None
            provider_session_id = None
            await self._record_primary(failure.reason)
            await self._close_after_open_failure()
            raise failure from None
        except Exception:
            error = OpenAIRealtimeSessionError(
                "REALTIME_SESSION_NEGOTIATION_FAILED",
                "Realtime session negotiation failed",
            )
            await self._record_primary(error.reason)
            await self._close_after_open_failure()
            raise error from None

        async with self._state_lock:
            if self._state is RealtimeSessionState.OPENING:
                self._state = RealtimeSessionState.OPEN

    async def send_event(self, event_type: str, payload: Mapping[str, object]) -> str:
        result: str | None = None
        failure: BaseException | None = None
        try:
            result = await self._send_event_internal(
                event_type,
                payload,
                allow_opening=False,
            )
        except BaseException as exc:
            failure = exc.with_traceback(None)
        event_type = ""
        payload = {}
        if failure is not None:
            raise failure from None
        assert result is not None
        return result

    async def receive_event(self) -> OpenAIRealtimeEvent:
        return await self._receive_event_internal(allow_opening=False)

    async def close(self) -> RealtimeSessionSnapshot:
        async with self._state_lock:
            if self._state is RealtimeSessionState.CLOSED:
                return self.snapshot()
            socket = self._socket
            if socket is None:
                self._state = RealtimeSessionState.CLOSED
                self._close_complete = True
                return self.snapshot()
            self._state = RealtimeSessionState.CLOSING
        result = await self._finalizer.close(
            socket,
            timeout_seconds=self._config.close_timeout_seconds,
        )
        async with self._state_lock:
            if result.error_reason is not None and self._close_error_reason is None:
                self._close_error_reason = result.error_reason
            self._close_complete = result.complete
            self._state = (
                RealtimeSessionState.CLOSED
                if result.complete
                else RealtimeSessionState.CLOSING
            )
            snapshot = self.snapshot()
        if result.process_control is not None:
            raise result.process_control from None
        return snapshot

    def snapshot(self) -> RealtimeSessionSnapshot:
        return RealtimeSessionSnapshot(
            state=self._state,
            provider_session_id=self._provider_session_id,
            provider_event_count=len(self._provider_events),
            client_event_count=self._client_event_count,
            primary_error_reason=self._primary_error_reason,
            close_error_reason=self._close_error_reason,
            close_complete=self._close_complete,
        )

    async def _send_event_internal(
        self,
        event_type: str,
        payload: Mapping[str, object],
        *,
        allow_opening: bool,
    ) -> str:
        try:
            parsed_type = _safe_label(event_type, "event_type")
            parsed_payload = _client_payload(payload, field_name="event payload")
            if "type" in parsed_payload or "event_id" in parsed_payload:
                raise OpenAIRealtimeSessionError(
                    "REALTIME_CLIENT_EVENT_NOT_CLOSED",
                    "client event payload cannot replace envelope fields",
                )
        except OpenAIRealtimeSessionError as exc:
            await self._record_primary(exc.reason)
            raise exc from None
        except ValueError:
            error = OpenAIRealtimeSessionError(
                "REALTIME_CLIENT_EVENT_INVALID",
                "client event type is invalid",
            )
            await self._record_primary(error.reason)
            raise error from None

        async with self._send_lock:
            socket = await self._require_socket(allow_opening=allow_opening)
            next_count = self._client_event_count + 1
            event_id = f"client_event_{next_count:08d}"
            wire = _encode_client_event(
                {"type": parsed_type, "event_id": event_id, **parsed_payload}
            )
            try:
                await asyncio.wait_for(
                    socket.send(wire),
                    timeout=self._config.operation_timeout_seconds,
                )
            except asyncio.CancelledError:
                raise
            except (KeyboardInterrupt, SystemExit, GeneratorExit):
                raise
            except (TimeoutError, asyncio.TimeoutError):
                error = OpenAIRealtimeSessionError(
                    "REALTIME_PROVIDER_TIMEOUT",
                    "Realtime Provider send timed out",
                )
                await self._record_primary(error.reason)
                raise error from None
            except Exception:
                error = OpenAIRealtimeSessionError(
                    "REALTIME_TRANSPORT_SEND_FAILED",
                    "Realtime Provider send failed",
                )
                await self._record_primary(error.reason)
                raise error from None
            self._client_event_count = next_count
            return event_id

    async def _receive_event_internal(
        self, *, allow_opening: bool
    ) -> OpenAIRealtimeEvent:
        async with self._receive_lock:
            socket = await self._require_socket(allow_opening=allow_opening)
            wire: str | bytes | None = None
            while wire is None:
                try:
                    wire = await asyncio.wait_for(
                        socket.recv(),
                        timeout=self._config.operation_timeout_seconds,
                    )
                except asyncio.CancelledError:
                    raise
                except (KeyboardInterrupt, SystemExit, GeneratorExit):
                    raise
                except (TimeoutError, asyncio.TimeoutError):
                    if not allow_opening and await self._can_wait_for_provider(socket):
                        continue
                    error = OpenAIRealtimeSessionError(
                        "REALTIME_PROVIDER_TIMEOUT",
                        "Realtime Provider receive timed out",
                    )
                    await self._record_primary(error.reason)
                    raise error from None
                except Exception:
                    error = OpenAIRealtimeSessionError(
                        "REALTIME_TRANSPORT_RECEIVE_FAILED",
                        "Realtime Provider receive failed",
                    )
                    await self._record_primary(error.reason)
                    raise error from None
            event, protocol_reason = _decode_provider_event(wire)
            wire = None
            if protocol_reason is not None:
                error = OpenAIRealtimeSessionError(
                    protocol_reason,
                    "Realtime Provider message violated the bounded protocol",
                )
                await self._record_primary(error.reason)
                raise error from None
            assert event is not None
            retained, ledger_reason = await self._retain_provider_event(event)
            event = None
            if ledger_reason is not None:
                error = OpenAIRealtimeSessionError(
                    ledger_reason,
                    (
                        "Provider event identity cannot change its meaning"
                        if ledger_reason == "REALTIME_PROVIDER_EVENT_CONFLICT"
                        else "bounded Provider event ledger is full"
                    ),
                )
                await self._record_primary(error.reason)
                raise error from None
            assert retained is not None
            return retained

    async def _can_wait_for_provider(self, socket: RealtimeSocket) -> bool:
        async with self._state_lock:
            return self._state is RealtimeSessionState.OPEN and self._socket is socket

    async def _retain_provider_event(
        self, event: OpenAIRealtimeEvent
    ) -> tuple[OpenAIRealtimeEvent | None, str | None]:
        async with self._state_lock:
            existing = self._provider_events.get(event.event_id)
            if existing is not None:
                canonical, retained = existing
                if canonical == event._canonical_bytes:
                    self._provider_events.move_to_end(event.event_id)
                    return retained, None
                self._state = RealtimeSessionState.FAILED
                return None, "REALTIME_PROVIDER_EVENT_CONFLICT"
            if len(self._provider_events) >= self._config.max_provider_events:
                self._provider_events.popitem(last=False)
            self._provider_events[event.event_id] = (
                event._canonical_bytes,
                event,
            )
            return event, None

    async def _require_socket(self, *, allow_opening: bool) -> RealtimeSocket:
        async with self._state_lock:
            allowed = {RealtimeSessionState.OPEN}
            if allow_opening:
                allowed.add(RealtimeSessionState.OPENING)
            if self._state not in allowed or self._socket is None:
                error = OpenAIRealtimeSessionError(
                    "REALTIME_STATE_INVALID",
                    "Realtime operation is not valid in the current state",
                )
                self._record_primary_locked(error.reason)
                raise error
            return self._socket

    async def _record_primary(self, reason: str) -> None:
        async with self._state_lock:
            self._record_primary_locked(reason)

    def _record_primary_locked(self, reason: str) -> None:
        if self._primary_error_reason is None:
            self._primary_error_reason = reason

    async def _close_after_open_failure(self) -> None:
        async with self._state_lock:
            socket = self._socket
            if socket is None:
                self._state = RealtimeSessionState.CLOSED
                self._close_complete = True
                return
            self._state = RealtimeSessionState.CLOSING
        result = await self._finalizer.close(
            socket,
            timeout_seconds=self._config.close_timeout_seconds,
        )
        async with self._state_lock:
            if result.error_reason is not None and self._close_error_reason is None:
                self._close_error_reason = result.error_reason
            self._close_complete = result.complete
            self._state = (
                RealtimeSessionState.CLOSED
                if result.complete
                else RealtimeSessionState.CLOSING
            )
        if result.process_control is not None:
            raise result.process_control from None


async def _connect_socket(
    factory: RealtimeSocketFactory,
    *,
    url: str,
    config: OpenAIRealtimeSessionConfig,
    timeout_seconds: float,
) -> tuple[RealtimeSocket | None, str | None]:
    headers: Mapping[str, str] = {"Authorization": f"Bearer {config.api_key}"}
    failure_reason: str | None = None
    socket: RealtimeSocket | None = None
    try:
        socket = await asyncio.wait_for(
            factory(url, headers, timeout_seconds),
            timeout=timeout_seconds,
        )
    except asyncio.CancelledError:
        raise
    except (KeyboardInterrupt, SystemExit, GeneratorExit):
        raise
    except (TimeoutError, asyncio.TimeoutError):
        failure_reason = "REALTIME_PROVIDER_TIMEOUT"
    except Exception:
        failure_reason = "REALTIME_CONNECT_FAILED"
    finally:
        headers = {}
    if failure_reason is None and socket is None:
        failure_reason = "REALTIME_CONNECT_FAILED"
    return socket, failure_reason


def _client_payload(value: object, *, field_name: str) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise OpenAIRealtimeSessionError(
            "REALTIME_CLIENT_EVENT_INVALID",
            f"{field_name} must be a JSON object",
        )
    result: dict[str, object] = {}
    for key, item in value.items():
        if type(key) is not str or key in result:
            raise OpenAIRealtimeSessionError(
                "REALTIME_CLIENT_EVENT_INVALID",
                f"{field_name} keys must be unique strings",
            )
        result[key] = item
    try:
        encoded = json.dumps(
            result,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError):
        raise OpenAIRealtimeSessionError(
            "REALTIME_CLIENT_EVENT_INVALID",
            f"{field_name} must contain bounded JSON values",
        ) from None
    if len(encoded) > MAX_REALTIME_WIRE_MESSAGE_BYTES:
        raise OpenAIRealtimeSessionError(
            "REALTIME_CLIENT_EVENT_TOO_LARGE",
            f"{field_name} exceeds the Realtime wire bound",
        )
    decoded = json.loads(encoded)
    assert type(decoded) is dict
    return decoded


def _encode_client_event(value: Mapping[str, object]) -> str:
    try:
        wire = json.dumps(
            dict(value),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        size = len(wire.encode("utf-8"))
    except (TypeError, ValueError, UnicodeEncodeError):
        raise OpenAIRealtimeSessionError(
            "REALTIME_CLIENT_EVENT_INVALID",
            "client event must contain JSON values",
        ) from None
    if size > MAX_REALTIME_WIRE_MESSAGE_BYTES:
        raise OpenAIRealtimeSessionError(
            "REALTIME_CLIENT_EVENT_TOO_LARGE",
            "client event exceeds the Realtime wire bound",
        )
    return wire


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _decode_provider_event(
    wire: object,
) -> tuple[OpenAIRealtimeEvent | None, str | None]:
    if type(wire) is not str:
        return None, "REALTIME_PROVIDER_MESSAGE_NOT_TEXT"
    try:
        encoded = wire.encode("utf-8")
    except UnicodeEncodeError:
        return None, "REALTIME_PROVIDER_MESSAGE_INVALID"
    if len(encoded) > MAX_REALTIME_WIRE_MESSAGE_BYTES:
        return None, "REALTIME_PROVIDER_MESSAGE_TOO_LARGE"
    try:
        value = json.loads(wire, object_pairs_hook=_unique_json_object)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None, "REALTIME_PROVIDER_MESSAGE_INVALID"
    if type(value) is not dict:
        return None, "REALTIME_PROVIDER_MESSAGE_INVALID"
    try:
        event_type = _safe_label(value.get("type"), "type")
        event_id = _safe_label(value.get("event_id"), "event_id")
        canonical = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError):
        return None, "REALTIME_PROVIDER_MESSAGE_INVALID"
    return OpenAIRealtimeEvent(event_type, event_id, canonical), None


def _negotiated_session_id(
    event: OpenAIRealtimeEvent,
    *,
    expected_type: str,
    expected_session_id: str | None,
) -> str:
    if event.event_type != expected_type:
        raise OpenAIRealtimeSessionError(
            "REALTIME_SESSION_NEGOTIATION_FAILED",
            "Realtime Provider returned an unexpected negotiation event",
        )
    value = event.to_dict().get("session")
    if not isinstance(value, Mapping):
        raise OpenAIRealtimeSessionError(
            "REALTIME_SESSION_NEGOTIATION_FAILED",
            "Realtime Provider omitted the negotiated session",
        )
    try:
        session_id = _safe_label(value.get("id"), "session.id")
    except ValueError:
        raise OpenAIRealtimeSessionError(
            "REALTIME_SESSION_NEGOTIATION_FAILED",
            "Realtime Provider returned an invalid session identity",
        ) from None
    if expected_session_id is not None and session_id != expected_session_id:
        raise OpenAIRealtimeSessionError(
            "REALTIME_SESSION_NEGOTIATION_FAILED",
            "Realtime Provider changed the negotiated session identity",
        )
    return session_id


def _safe_label(value: object, field_name: str) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > _MAX_SAFE_LABEL_CHARS
        or any(
            unicodedata.category(character) in {"Cc", "Cf", "Zl", "Zp"}
            for character in value
        )
    ):
        raise ValueError(f"{field_name} must be a bounded single-line value")
    try:
        size = len(value.encode("utf-8"))
    except UnicodeEncodeError:
        raise ValueError(f"{field_name} must contain valid Unicode") from None
    if size > _MAX_SAFE_LABEL_UTF8_BYTES:
        raise ValueError(f"{field_name} exceeds its UTF-8 bound")
    return value


def _required_secret(value: object) -> None:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > _MAX_API_KEY_CHARS
        or any(character in value for character in ("\r", "\n", "\x00"))
    ):
        raise ValueError("API key must be non-empty, bounded, and single-line")


def _bounded_timeout(value: object, *, field_name: str, maximum: float) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not 0 < value <= maximum
    ):
        raise ValueError(f"{field_name} must be finite and in (0, {maximum}]")
    return float(value)


def _is_process_control(value: BaseException) -> bool:
    return isinstance(value, (KeyboardInterrupt, SystemExit, GeneratorExit))


__all__ = [
    "MAX_REALTIME_WIRE_MESSAGE_BYTES",
    "REALTIME_SOCKET_CLOSE_TIMEOUT_SECONDS",
    "OpenAIRealtimeEvent",
    "OpenAIRealtimeSession",
    "OpenAIRealtimeSessionConfig",
    "OpenAIRealtimeSessionError",
    "RealtimeSessionSnapshot",
    "RealtimeSessionState",
    "RealtimeSocket",
    "RealtimeSocketCleanupOwner",
    "RealtimeSocketCleanupSnapshot",
    "RealtimeSocketFactory",
    "RealtimeTransport",
    "default_realtime_socket_factory",
    "official_realtime_url",
    "validate_official_openai_api_base",
]
