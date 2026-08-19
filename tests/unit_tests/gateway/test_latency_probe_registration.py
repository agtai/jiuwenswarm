# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from jiuwenswarm.gateway.channel_manager.base import RobotMessageRouter
from jiuwenswarm.gateway.channel_manager.web import app_web_handlers
from jiuwenswarm.gateway.channel_manager.web.app_web_handlers import (
    WebHandlersBindParams,
    _register_web_handlers,
)
from jiuwenswarm.gateway.channel_manager.web.web_connect import (
    WebChannel,
    WebChannelConfig,
)
from jiuwenswarm.gateway.live_voice.latency_probe_registration import (
    LATENCY_PROBE_BATCH_METHOD,
    register_latency_probe_rpc_handler,
)
from jiuwenswarm.gateway.routing.keys import AgentRef, RoutingKey
from jiuwenswarm.server.live_voice.latency_probe import (
    LATENCY_PROBE_ENABLED_ENV,
    LATENCY_PROBE_OUTPUT_ROOT_ENV,
    LATENCY_PROBE_RUN_CONFIG_ENV,
    LatencyBatch,
    LatencyProbeBatchWriter,
    LatencyProbeRuntime,
    LatencyProbeWriteResult,
    load_latency_run_config,
)


def _run_payload() -> dict[str, object]:
    return {
        "schema_version": "live-voice.latency-run.v0",
        "run_id": "run-20260819-task3",
        "git_commit": "a" * 40,
        "source_state": "clean",
        "environment_profile": "dev-wsl-browser",
        "browser_family_and_version": "chromium-139",
        "browser_os_class": "windows",
        "gateway_runtime_class": "wsl-python",
        "agent_runtime_class": "linux-python",
        "stt_provider_and_model": "openai-gpt-4o-transcribe",
        "tts_provider_and_model": "openai-gpt-4o-mini-tts",
        "audio_format": "pcm16-24000hz-mono",
        "vad_configuration": "provider-server-vad",
        "playout_configuration": "webaudio-default",
        "allowlisted_feature_flags": {"formal_route": True},
        "cold_or_warm": "warm",
        "input_case_ids": ["short-greeting-v1", "tool-weather-v1"],
        "profile_ids": [
            "dialogue_no_tool",
            "dialogue_with_tool",
            "task_create",
            "task_status",
            "task_cancel",
        ],
        "intended_attempts": 5,
        "required_successes": 5,
        "experiment": None,
    }


@pytest.fixture
def run_config(tmp_path: Path):
    path = tmp_path / "run.json"
    path.write_text(json.dumps(_run_payload()), encoding="utf-8")
    return load_latency_run_config(path)


def _mark(
    *,
    run_id: str = "run-20260819-task3",
    profile_id: str = "dialogue_no_tool",
    input_case_id: str = "short-greeting-v1",
    round_index: int = 0,
    source_instance_id: str = "browser-source-1",
    correlation_id: str = "correlation-1",
) -> dict[str, object]:
    return {
        "schema_version": "live-voice.latency-probe.v0",
        "run_id": run_id,
        "profile_id": profile_id,
        "input_case_id": input_case_id,
        "round_index": round_index,
        "source_instance_id": source_instance_id,
        "mark_index": 0,
        "component": "browser",
        "clock_domain_id": "browser-performance-1",
        "point": "browser.eot_received",
        "monotonic_ms": 10.0,
        "uncertainty_ms": None,
        "outcome": "observed",
        "reason_code": None,
        "correlation_id": correlation_id,
        "interaction_id": "interaction-1",
        "activation_id": None,
        "activation_generation": None,
        "turn_id": None,
        "response_id": None,
        "response_generation": None,
        "task_id": None,
    }


def _batch_dict(
    *,
    batch_id: str = "browser-batch-0",
    run_id: str = "run-20260819-task3",
    profile_id: str = "dialogue_no_tool",
    input_case_id: str = "short-greeting-v1",
    round_index: int = 0,
    source_instance_id: str = "browser-source-1",
    correlation_id: str = "correlation-1",
) -> dict[str, object]:
    return {
        "schema_version": "live-voice.latency-batch.v0",
        "batch_id": batch_id,
        "run_id": run_id,
        "profile_id": profile_id,
        "input_case_id": input_case_id,
        "round_index": round_index,
        "source_instance_id": source_instance_id,
        "component": "browser",
        "phase": "browser_round",
        "terminal_outcome": "completed",
        "marks": [
            _mark(
                run_id=run_id,
                profile_id=profile_id,
                input_case_id=input_case_id,
                round_index=round_index,
                source_instance_id=source_instance_id,
                correlation_id=correlation_id,
            )
        ],
    }


class _FakeChannel:
    def __init__(self) -> None:
        self.channel_id = "web"
        self.handlers: dict[str, Any] = {}
        self.responses: list[dict[str, object]] = []
        self.connect_handler: Any = None
        self.disconnect_handler: Any = None

    def register_method(self, method: str, handler: Any) -> None:
        self.handlers[method] = handler

    def on_connect(self, handler: Any) -> None:
        self.connect_handler = handler

    def on_disconnect(self, handler: Any) -> None:
        self.disconnect_handler = handler

    def _registered_session_for_websocket(
        self,
        _ws: Any,
        claimed_session_id: object,
    ) -> str:
        return claimed_session_id if isinstance(claimed_session_id, str) else ""

    async def send_response(
        self,
        ws: Any,
        req_id: str,
        *,
        ok: bool,
        payload: dict[str, object] | None = None,
        error: str | None = None,
        code: str | None = None,
    ) -> bool:
        self.responses.append(
            {
                "ws": ws,
                "id": req_id,
                "ok": ok,
                "payload": payload,
                "error": error,
                "code": code,
            }
        )
        return True


def _runtime(tmp_path: Path, run_config: Any) -> LatencyProbeRuntime:
    return LatencyProbeRuntime(
        run_config,
        "gateway",
        LatencyProbeBatchWriter(
            tmp_path / "probe-output",
            run_config,
            "gateway",
            mode="gateway_with_browser",
        ),
    )


def _payload(response: dict[str, object]) -> dict[str, object]:
    payload = response["payload"]
    assert isinstance(payload, dict)
    assert set(payload) == {"status", "batch_id", "reason_code"}
    return payload


async def _close_bootstrap_owners(channel: _FakeChannel) -> None:
    closed: set[int] = set()
    for attribute in (
        "live_voice_streaming_synthesis_owner",
        "live_voice_streaming_speech_owner",
        "live_voice_owned_speech_service",
    ):
        owner = getattr(channel, attribute, None)
        if owner is not None and id(owner) not in closed:
            closed.add(id(owner))
            await owner.close()


@pytest.mark.asyncio
async def test_feature_off_registers_nothing_and_allocates_no_probe_runtime_or_files(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "feature-off-output"
    monkeypatch.setenv(LATENCY_PROBE_ENABLED_ENV, "0")
    monkeypatch.setenv(LATENCY_PROBE_RUN_CONFIG_ENV, str(tmp_path / "missing.json"))
    monkeypatch.setenv(LATENCY_PROBE_OUTPUT_ROOT_ENV, str(output_root))
    channel = _FakeChannel()

    _register_web_handlers(WebHandlersBindParams(channel=channel))

    assert channel.live_voice_latency_probe_runtime is None
    assert LATENCY_PROBE_BATCH_METHOD not in channel.handlers
    assert output_root.exists() is False
    await _close_bootstrap_owners(channel)


@pytest.mark.asyncio
async def test_bootstrap_publishes_one_reusable_gateway_runtime_and_real_browser_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "run.json"
    config_path.write_text(json.dumps(_run_payload()), encoding="utf-8")
    output_root = tmp_path / "probe-output"
    monkeypatch.setenv(LATENCY_PROBE_ENABLED_ENV, "1")
    monkeypatch.setenv(LATENCY_PROBE_RUN_CONFIG_ENV, str(config_path))
    monkeypatch.setenv(LATENCY_PROBE_OUTPUT_ROOT_ENV, str(output_root))
    factory_calls = 0
    real_factory = app_web_handlers.create_latency_probe_runtime_from_environment

    def counted_factory(component: str) -> LatencyProbeRuntime | None:
        nonlocal factory_calls
        factory_calls += 1
        return real_factory(component)

    monkeypatch.setattr(
        app_web_handlers,
        "create_latency_probe_runtime_from_environment",
        counted_factory,
    )
    channel = _FakeChannel()

    _register_web_handlers(WebHandlersBindParams(channel=channel))
    runtime = channel.live_voice_latency_probe_runtime
    await channel.handlers[LATENCY_PROBE_BATCH_METHOD](
        "ws",
        "request-1",
        {"session_id": "session-1", "batch": _batch_dict()},
        "session-1",
    )

    assert factory_calls == 1
    assert isinstance(runtime, LatencyProbeRuntime)
    assert runtime is channel.live_voice_latency_probe_runtime
    assert _payload(channel.responses[-1]) == {
        "status": "written",
        "batch_id": "browser-batch-0",
        "reason_code": None,
    }
    lines = (output_root / runtime.run_config.run_id / "browser.jsonl").read_text(
        encoding="utf-8"
    ).splitlines()
    assert lines == [
        json.dumps(_batch_dict(), ensure_ascii=False, separators=(",", ":"))
    ]
    await _close_bootstrap_owners(channel)


@pytest.mark.asyncio
async def test_handler_persists_once_retries_idempotently_and_fences_round_order(
    tmp_path: Path,
    run_config: Any,
) -> None:
    channel = _FakeChannel()
    runtime = _runtime(tmp_path, run_config)
    register_latency_probe_rpc_handler(channel, runtime)
    handler = channel.handlers[LATENCY_PROBE_BATCH_METHOD]
    first = {"session_id": "session-1", "batch": _batch_dict()}

    await handler("ws", "first", first, "session-1")
    await handler("ws", "retry", first, "session-1")
    await handler(
        "ws",
        "conflict",
        {
            "session_id": "session-1",
            "batch": _batch_dict(batch_id="different-batch-0", correlation_id="corr-2"),
        },
        "session-1",
    )
    await handler(
        "ws",
        "gap",
        {
            "session_id": "session-1",
            "batch": _batch_dict(
                batch_id="browser-batch-2", round_index=2, source_instance_id="source-2"
            ),
        },
        "session-1",
    )
    await handler(
        "ws",
        "next",
        {
            "session_id": "session-1",
            "batch": _batch_dict(
                batch_id="browser-batch-1", round_index=1, source_instance_id="source-1"
            ),
        },
        "session-1",
    )

    assert [_payload(item)["status"] for item in channel.responses] == [
        "written",
        "idempotent",
        "rejected",
        "rejected",
        "written",
    ]
    assert _payload(channel.responses[2])["reason_code"] == "BATCH_CONFLICT"
    assert _payload(channel.responses[3])["reason_code"] == "SEQUENCE_GAP"
    output = tmp_path / "probe-output" / run_config.run_id / "browser.jsonl"
    assert len(output.read_text(encoding="utf-8").splitlines()) == 2


@pytest.mark.asyncio
async def test_handler_rejects_closed_identity_bounds_and_private_inputs_without_writes(
    tmp_path: Path,
    run_config: Any,
) -> None:
    channel = _FakeChannel()
    register_latency_probe_rpc_handler(channel, _runtime(tmp_path, run_config))
    handler = channel.handlers[LATENCY_PROBE_BATCH_METHOD]
    oversized = _batch_dict(batch_id="oversized")
    oversized["marks"] = [_mark()] * 65
    cases = [
        (
            {"session_id": "session-1", "batch": _batch_dict(), "text": "PRIVATE"},
            "session-1",
        ),
        ({"session_id": "session-other", "batch": _batch_dict()}, "session-1"),
        (
            {
                "session_id": "session-1",
                "batch": _batch_dict(run_id="different-run"),
            },
            "session-1",
        ),
        ({"session_id": "session-1", "batch": oversized}, "session-1"),
        (
            {
                "session_id": "session-1",
                "batch": _batch_dict(correlation_id="PRIVATE_SENTINEL"),
            },
            "session-1",
        ),
        (
            {
                "session_id": "session-1",
                "batch": {**_batch_dict(), "raw_text": "MALFORMED_PRIVATE_SENTINEL"},
            },
            "session-1",
        ),
    ]

    for index, (params, dispatcher_session) in enumerate(cases):
        await handler("ws", f"negative-{index}", params, dispatcher_session)
        assert _payload(channel.responses[-1])["status"] == "rejected"

    assert (tmp_path / "probe-output" / run_config.run_id / "browser.jsonl").exists() is False


@pytest.mark.asyncio
async def test_session_identity_is_isolated_and_first_round_must_be_zero(
    tmp_path: Path,
    run_config: Any,
) -> None:
    channel = _FakeChannel()
    register_latency_probe_rpc_handler(channel, _runtime(tmp_path, run_config))
    handler = channel.handlers[LATENCY_PROBE_BATCH_METHOD]

    await handler(
        "ws",
        "session-a-zero",
        {"session_id": "session-a", "batch": _batch_dict(batch_id="a-0")},
        "session-a",
    )
    await handler(
        "ws",
        "session-b-gap",
        {
            "session_id": "session-b",
            "batch": _batch_dict(batch_id="b-1", round_index=1),
        },
        "session-b",
    )
    await handler(
        "ws",
        "session-b-zero",
        {
            "session_id": "session-b",
            "batch": _batch_dict(
                batch_id="b-0",
                profile_id="task_status",
                input_case_id="tool-weather-v1",
            ),
        },
        "session-b",
    )
    await handler(
        "ws",
        "session-a-wrong-profile",
        {
            "session_id": "session-a",
            "batch": _batch_dict(
                batch_id="a-1",
                profile_id="task_status",
                round_index=1,
            ),
        },
        "session-a",
    )
    await handler(
        "ws",
        "session-a-wrong-input-case",
        {
            "session_id": "session-a",
            "batch": _batch_dict(
                batch_id="a-1-other-case",
                input_case_id="tool-weather-v1",
                round_index=1,
            ),
        },
        "session-a",
    )

    assert [_payload(item)["reason_code"] for item in channel.responses] == [
        None,
        "SEQUENCE_GAP",
        None,
        "IDENTITY_MISMATCH",
        "IDENTITY_MISMATCH",
    ]


@pytest.mark.asyncio
async def test_all_declared_round_digests_remain_idempotent_and_range_is_closed(
    tmp_path: Path,
) -> None:
    payload = _run_payload()
    payload["intended_attempts"] = 256
    config_path = tmp_path / "run-256.json"
    config_path.write_text(json.dumps(payload), encoding="utf-8")
    run_config = load_latency_run_config(config_path)
    channel = _FakeChannel()
    register_latency_probe_rpc_handler(channel, _runtime(tmp_path, run_config))
    handler = channel.handlers[LATENCY_PROBE_BATCH_METHOD]

    for round_index in range(256):
        await handler(
            "ws",
            f"round-{round_index}",
            {
                "session_id": "session-256",
                "batch": _batch_dict(
                    batch_id=f"batch-{round_index}",
                    round_index=round_index,
                    source_instance_id=f"source-{round_index}",
                ),
            },
            "session-256",
        )
        assert _payload(channel.responses[-1])["status"] == "written"

    await handler(
        "ws",
        "retry-round-zero",
        {
            "session_id": "session-256",
            "batch": _batch_dict(
                batch_id="batch-0",
                round_index=0,
                source_instance_id="source-0",
            ),
        },
        "session-256",
    )
    await handler(
        "ws",
        "out-of-range",
        {
            "session_id": "session-256",
            "batch": _batch_dict(
                batch_id="batch-256",
                round_index=256,
                source_instance_id="source-256",
            ),
        },
        "session-256",
    )

    assert _payload(channel.responses[-2]) == {
        "status": "idempotent",
        "batch_id": "batch-0",
        "reason_code": None,
    }
    assert _payload(channel.responses[-1]) == {
        "status": "rejected",
        "batch_id": "batch-256",
        "reason_code": "SEQUENCE_GAP",
    }
    output = tmp_path / "probe-output" / run_config.run_id / "browser.jsonl"
    assert len(output.read_text(encoding="utf-8").splitlines()) == 256


class _FailOnceWriter:
    def __init__(self, delegate: LatencyProbeBatchWriter) -> None:
        self.delegate = delegate
        self.calls = 0

    def write(self, batch: LatencyBatch) -> LatencyProbeWriteResult:
        self.calls += 1
        if self.calls == 1:
            return LatencyProbeWriteResult("failed", batch.batch_id, "EXPORT_FAILED")
        return self.delegate.write(batch)


class _FailOnSecondWriter:
    def __init__(self, delegate: LatencyProbeBatchWriter) -> None:
        self.delegate = delegate
        self.calls = 0

    def write(self, batch: LatencyBatch) -> LatencyProbeWriteResult:
        self.calls += 1
        if self.calls > 1:
            raise OSError("receipt was evicted")
        return self.delegate.write(batch)


class _RaiseWriter:
    def __init__(self, failure: BaseException) -> None:
        self.failure = failure

    def write(self, _batch: LatencyBatch) -> LatencyProbeWriteResult:
        raise self.failure


class _ResponseFailureChannel(_FakeChannel):
    def __init__(self, failure: BaseException) -> None:
        super().__init__()
        self.failure: BaseException | None = failure

    async def send_response(
        self,
        ws: Any,
        req_id: str,
        *,
        ok: bool,
        payload: dict[str, object] | None = None,
        error: str | None = None,
        code: str | None = None,
    ) -> bool:
        if self.failure is not None:
            failure = self.failure
            self.failure = None
            raise failure
        return await super().send_response(
            ws,
            req_id,
            ok=ok,
            payload=payload,
            error=error,
            code=code,
        )


class _ReceiptChannel(_FakeChannel):
    def __init__(self, receipts: list[bool]) -> None:
        super().__init__()
        self.receipts = receipts

    async def send_response(
        self,
        ws: Any,
        req_id: str,
        *,
        ok: bool,
        payload: dict[str, object] | None = None,
        error: str | None = None,
        code: str | None = None,
    ) -> bool:
        await super().send_response(
            ws,
            req_id,
            ok=ok,
            payload=payload,
            error=error,
            code=code,
        )
        return self.receipts.pop(0)


@pytest.mark.asyncio
async def test_writer_fault_does_not_advance_session_and_retry_persists_once(
    tmp_path: Path,
    run_config: Any,
) -> None:
    real_writer = LatencyProbeBatchWriter(
        tmp_path / "probe-output",
        run_config,
        "gateway",
        mode="gateway_with_browser",
    )
    writer = _FailOnceWriter(real_writer)
    runtime = LatencyProbeRuntime(run_config, "gateway", writer)  # type: ignore[arg-type]
    channel = _FakeChannel()
    register_latency_probe_rpc_handler(channel, runtime)
    handler = channel.handlers[LATENCY_PROBE_BATCH_METHOD]
    params = {"session_id": "session-1", "batch": _batch_dict()}

    await handler("ws", "fault", params, "session-1")
    await handler("ws", "retry", params, "session-1")

    assert [_payload(item) for item in channel.responses] == [
        {
            "status": "failed",
            "batch_id": "browser-batch-0",
            "reason_code": "EXPORT_FAILED",
        },
        {
            "status": "written",
            "batch_id": "browser-batch-0",
            "reason_code": None,
        },
    ]
    output = tmp_path / "probe-output" / run_config.run_id / "browser.jsonl"
    assert len(output.read_text(encoding="utf-8").splitlines()) == 1


@pytest.mark.asyncio
async def test_identical_retry_uses_accepted_session_receipt_without_rewriting(
    tmp_path: Path,
    run_config: Any,
) -> None:
    real_writer = LatencyProbeBatchWriter(
        tmp_path / "probe-output",
        run_config,
        "gateway",
        mode="gateway_with_browser",
    )
    writer = _FailOnSecondWriter(real_writer)
    runtime = LatencyProbeRuntime(run_config, "gateway", writer)  # type: ignore[arg-type]
    channel = _FakeChannel()
    register_latency_probe_rpc_handler(channel, runtime)
    params = {"session_id": "session-1", "batch": _batch_dict()}

    await channel.handlers[LATENCY_PROBE_BATCH_METHOD](
        "ws", "first", params, "session-1"
    )
    await channel.handlers[LATENCY_PROBE_BATCH_METHOD](
        "ws", "retry", params, "session-1"
    )

    assert writer.calls == 1
    assert [_payload(item)["status"] for item in channel.responses] == [
        "written",
        "idempotent",
    ]


@pytest.mark.asyncio
async def test_handler_contains_ordinary_writer_fault_but_not_process_control(
    run_config: Any,
) -> None:
    channel = _FakeChannel()
    ordinary = LatencyProbeRuntime(run_config, "gateway", _RaiseWriter(OSError("private")))  # type: ignore[arg-type]
    register_latency_probe_rpc_handler(channel, ordinary)

    await channel.handlers[LATENCY_PROBE_BATCH_METHOD](
        "ws",
        "ordinary",
        {"session_id": "session-1", "batch": _batch_dict()},
        "session-1",
    )

    assert _payload(channel.responses[-1]) == {
        "status": "failed",
        "batch_id": "browser-batch-0",
        "reason_code": "EXPORT_FAILED",
    }

    process_control = LatencyProbeRuntime(
        run_config,
        "gateway",
        _RaiseWriter(KeyboardInterrupt()),  # type: ignore[arg-type]
    )
    other_channel = _FakeChannel()
    register_latency_probe_rpc_handler(other_channel, process_control)
    with pytest.raises(KeyboardInterrupt):
        await other_channel.handlers[LATENCY_PROBE_BATCH_METHOD](
            "ws",
            "process-control",
            {"session_id": "session-1", "batch": _batch_dict()},
            "session-1",
        )


@pytest.mark.asyncio
async def test_ordinary_send_failure_is_contained_without_confirming_round_state(
    tmp_path: Path,
    run_config: Any,
) -> None:
    channel = _ResponseFailureChannel(OSError("PRIVATE_SEND_FAILURE"))
    register_latency_probe_rpc_handler(channel, _runtime(tmp_path, run_config))
    handler = channel.handlers[LATENCY_PROBE_BATCH_METHOD]

    await handler(
        "ws",
        "lost-response",
        {"session_id": "session-1", "batch": _batch_dict()},
        "session-1",
    )
    await handler(
        "ws",
        "unconfirmed-successor",
        {
            "session_id": "session-1",
            "batch": _batch_dict(batch_id="round-1", round_index=1),
        },
        "session-1",
    )
    await handler(
        "ws",
        "retry-round-zero",
        {"session_id": "session-1", "batch": _batch_dict()},
        "session-1",
    )

    assert [_payload(response) for response in channel.responses] == [
        {
            "status": "rejected",
            "batch_id": "round-1",
            "reason_code": "SEQUENCE_GAP",
        },
        {
            "status": "idempotent",
            "batch_id": "browser-batch-0",
            "reason_code": None,
        },
    ]
    output = tmp_path / "probe-output" / run_config.run_id / "browser.jsonl"
    assert len(output.read_text(encoding="utf-8").splitlines()) == 1
    assert "PRIVATE_SEND_FAILURE" not in repr(channel.responses)


@pytest.mark.asyncio
async def test_false_enqueue_receipt_does_not_confirm_round_state(
    tmp_path: Path,
    run_config: Any,
) -> None:
    channel = _ReceiptChannel([False, True, True])
    register_latency_probe_rpc_handler(channel, _runtime(tmp_path, run_config))
    handler = channel.handlers[LATENCY_PROBE_BATCH_METHOD]

    await handler(
        "ws",
        "dropped-round-zero",
        {"session_id": "session-1", "batch": _batch_dict()},
        "session-1",
    )
    await handler(
        "ws",
        "unconfirmed-successor",
        {
            "session_id": "session-1",
            "batch": _batch_dict(batch_id="round-1", round_index=1),
        },
        "session-1",
    )
    await handler(
        "ws",
        "retry-round-zero",
        {"session_id": "session-1", "batch": _batch_dict()},
        "session-1",
    )

    assert [_payload(response) for response in channel.responses] == [
        {
            "status": "written",
            "batch_id": "browser-batch-0",
            "reason_code": None,
        },
        {
            "status": "rejected",
            "batch_id": "round-1",
            "reason_code": "SEQUENCE_GAP",
        },
        {
            "status": "idempotent",
            "batch_id": "browser-batch-0",
            "reason_code": None,
        },
    ]
    output = tmp_path / "probe-output" / run_config.run_id / "browser.jsonl"
    assert len(output.read_text(encoding="utf-8").splitlines()) == 1


@pytest.mark.parametrize("failure", [KeyboardInterrupt(), SystemExit(19)])
@pytest.mark.asyncio
async def test_send_process_control_escapes_without_confirming_round_state(
    tmp_path: Path,
    run_config: Any,
    failure: BaseException,
) -> None:
    channel = _ResponseFailureChannel(failure)
    register_latency_probe_rpc_handler(channel, _runtime(tmp_path, run_config))
    handler = channel.handlers[LATENCY_PROBE_BATCH_METHOD]

    with pytest.raises(type(failure)):
        await handler(
            "ws",
            "process-control",
            {"session_id": "session-1", "batch": _batch_dict()},
            "session-1",
        )
    await handler(
        "ws",
        "unconfirmed-successor",
        {
            "session_id": "session-1",
            "batch": _batch_dict(batch_id="round-1", round_index=1),
        },
        "session-1",
    )

    assert _payload(channel.responses[-1]) == {
        "status": "rejected",
        "batch_id": "round-1",
        "reason_code": "SEQUENCE_GAP",
    }


class _EffectOwnerSpy:
    def __init__(self, name: str) -> None:
        self.name = name
        self.calls = 0

    def invoke(self, _value: object = None) -> None:
        self.calls += 1


class _MediaRegistrySpy(_EffectOwnerSpy):
    def __init__(self) -> None:
        super().__init__("media")
        self.registry = {"voice": "unchanged", "task": "unchanged"}

    def observe_agent_response(self, value: object, **_kwargs: object) -> None:
        self.invoke(value)
        self.registry["voice"] = "mutated"


class _AgentCallbackSpy:
    def __init__(self, agent: _EffectOwnerSpy) -> None:
        self.agent = agent

    def __call__(self, message: object) -> bool:
        self.agent.invoke(message)
        return False


@pytest.mark.asyncio
async def test_every_local_dispatch_outcome_has_zero_real_gateway_effects(
    tmp_path: Path,
    run_config: Any,
) -> None:
    channels: list[tuple[WebChannel, object]] = []

    async def build_boundary(
        runtime: LatencyProbeRuntime | None,
    ) -> tuple[
        WebChannel,
        object,
        list[dict[str, object]],
        dict[str, _EffectOwnerSpy],
        _MediaRegistrySpy,
        _EffectOwnerSpy,
        dict[RoutingKey, tuple[object, ...]],
    ]:
        channel = WebChannel(WebChannelConfig(enabled=True), RobotMessageRouter())
        owners = {
            name: _EffectOwnerSpy(name)
            for name in ("speech", "agent")
        }
        media = _MediaRegistrySpy()
        file_processing = _EffectOwnerSpy("file_processing")
        channel.live_voice_media_registry = media
        channel.live_voice_speech_service = owners["speech"]
        channel.on_message(_AgentCallbackSpy(owners["agent"]))
        register_latency_probe_rpc_handler(channel, runtime)
        ws = SimpleNamespace(closed=False, remote_address=("127.0.0.1", 12345))
        await channel.register_ws(
            ws,
            RoutingKey(
                user_id="user-1",
                channel_id="web",
                app_id="default",
                agent_ref=AgentRef(mode="agent", id="default"),
                session_id="registered-session",
            ),
        )
        responses: list[dict[str, object]] = []

        async def capture_response(
            _ws: Any,
            req_id: str,
            *,
            ok: bool,
            payload: dict[str, object] | None = None,
            error: str | None = None,
            code: str | None = None,
        ) -> bool:
            responses.append(
                {"id": req_id, "ok": ok, "payload": payload, "error": error, "code": code}
            )
            return True

        async def forbidden_file_processing(
            params: dict[str, Any],
        ) -> dict[str, Any]:
            file_processing.invoke(params)
            return params

        channel.send_response = capture_response  # type: ignore[method-assign]
        channel._process_files = forbidden_file_processing  # type: ignore[method-assign]
        routing_snapshot = {
            key: tuple(clients) for key, clients in channel._clients_by_key.items()
        }
        channels.append((channel, ws))
        return (
            channel,
            ws,
            responses,
            owners,
            media,
            file_processing,
            routing_snapshot,
        )

    async def dispatch(
        channel: WebChannel,
        ws: object,
        request_id: str,
        params: object,
    ) -> None:
        await channel._handle_raw_message(
            ws,
            json.dumps(
                {
                    "type": "req",
                    "id": request_id,
                    "method": LATENCY_PROBE_BATCH_METHOD,
                    "params": params,
                }
            ),
            {},
        )

    def assert_zero_effects(
        channel: WebChannel,
        owners: dict[str, _EffectOwnerSpy],
        media: _MediaRegistrySpy,
        registry_snapshot: dict[str, str],
        file_processing: _EffectOwnerSpy,
        routing_snapshot: dict[RoutingKey, tuple[object, ...]],
    ) -> None:
        assert media.calls == 0
        assert owners["speech"].calls == 0
        assert owners["agent"].calls == 0
        assert media.registry == registry_snapshot
        assert file_processing.calls == 0
        assert channel._clients_by_key == {
            key: list(clients) for key, clients in routing_snapshot.items()
        }
        assert channel._ws_sessions == {}

    try:
        (
            enabled,
            enabled_ws,
            enabled_responses,
            enabled_owners,
            enabled_media,
            enabled_file_processing,
            enabled_routing,
        ) = await build_boundary(_runtime(tmp_path, run_config))
        enabled_registry = dict(enabled_media.registry)
        await dispatch(
            enabled,
            enabled_ws,
            "positive",
            {"session_id": "registered-session", "batch": _batch_dict()},
        )
        assert _payload(enabled_responses[-1])["status"] == "written"
        assert_zero_effects(
            enabled,
            enabled_owners,
            enabled_media,
            enabled_registry,
            enabled_file_processing,
            enabled_routing,
        )

        oversized = _batch_dict(batch_id="oversized")
        oversized["marks"] = [_mark()] * 65
        negative_cases = (
            (
                "unknown-envelope",
                {
                    "session_id": "registered-session",
                    "batch": _batch_dict(),
                    "text": "PRIVATE",
                },
            ),
            (
                "wrong-session",
                {"session_id": "client-chosen", "batch": _batch_dict()},
            ),
            (
                "wrong-run",
                {
                    "session_id": "registered-session",
                    "batch": _batch_dict(run_id="different-run"),
                },
            ),
            (
                "oversized",
                {"session_id": "registered-session", "batch": oversized},
            ),
            (
                "private",
                {
                    "session_id": "registered-session",
                    "batch": _batch_dict(correlation_id="PRIVATE_SENTINEL"),
                },
            ),
            (
                "gap",
                {
                    "session_id": "registered-session",
                    "batch": _batch_dict(batch_id="gap-2", round_index=2),
                },
            ),
            (
                "round-conflict",
                {
                    "session_id": "registered-session",
                    "batch": _batch_dict(
                        batch_id="conflict-0",
                        correlation_id="conflict-correlation",
                    ),
                },
            ),
        )
        for request_id, params in negative_cases:
            await dispatch(enabled, enabled_ws, request_id, params)
            assert _payload(enabled_responses[-1])["status"] == "rejected"
            assert_zero_effects(
                enabled,
                enabled_owners,
                enabled_media,
                enabled_registry,
                enabled_file_processing,
                enabled_routing,
            )

        (
            disabled,
            disabled_ws,
            disabled_responses,
            disabled_owners,
            disabled_media,
            disabled_file_processing,
            disabled_routing,
        ) = await build_boundary(None)
        disabled_registry = dict(disabled_media.registry)
        await dispatch(
            disabled,
            disabled_ws,
            "feature-off",
            {"session_id": "registered-session", "batch": _batch_dict()},
        )
        assert disabled_responses[-1]["ok"] is False
        assert disabled_responses[-1]["code"] == "METHOD_NOT_FOUND"
        assert_zero_effects(
            disabled,
            disabled_owners,
            disabled_media,
            disabled_registry,
            disabled_file_processing,
            disabled_routing,
        )

        fault_runtime = LatencyProbeRuntime(
            run_config,
            "gateway",
            _RaiseWriter(OSError("private-writer-fault")),  # type: ignore[arg-type]
        )
        (
            faulted,
            faulted_ws,
            faulted_responses,
            faulted_owners,
            faulted_media,
            faulted_file_processing,
            faulted_routing,
        ) = await build_boundary(fault_runtime)
        faulted_registry = dict(faulted_media.registry)
        await dispatch(
            faulted,
            faulted_ws,
            "writer-fault",
            {
                "session_id": "registered-session",
                "batch": _batch_dict(batch_id="fault-batch"),
            },
        )
        assert _payload(faulted_responses[-1]) == {
            "status": "failed",
            "batch_id": "fault-batch",
            "reason_code": "EXPORT_FAILED",
        }
        assert_zero_effects(
            faulted,
            faulted_owners,
            faulted_media,
            faulted_registry,
            faulted_file_processing,
            faulted_routing,
        )
    finally:
        for channel, ws in channels:
            await channel.unregister_ws(ws)


@pytest.mark.asyncio
async def test_dispatch_authorizes_only_a_session_pre_registered_for_the_websocket(
    tmp_path: Path,
    run_config: Any,
) -> None:
    channel = WebChannel(WebChannelConfig(enabled=True), RobotMessageRouter())
    register_latency_probe_rpc_handler(channel, _runtime(tmp_path, run_config))
    ws = SimpleNamespace(closed=False, remote_address=("127.0.0.1", 12345))
    await channel.register_ws(
        ws,
        RoutingKey(
            user_id="user-1",
            channel_id="web",
            app_id="default",
            agent_ref=AgentRef(mode="agent", id="default"),
            session_id="registered-session",
        ),
    )
    registered_snapshot = {
        key: tuple(clients) for key, clients in channel._clients_by_key.items()
    }
    responses: list[dict[str, object]] = []
    file_processing_calls = 0
    agent_callback_calls = 0

    async def capture_response(
        _ws: Any,
        req_id: str,
        *,
        ok: bool,
        payload: dict[str, object] | None = None,
        error: str | None = None,
        code: str | None = None,
    ) -> bool:
        responses.append(
            {"id": req_id, "ok": ok, "payload": payload, "error": error, "code": code}
        )
        return True

    async def forbidden_file_processing(params: dict[str, Any]) -> dict[str, Any]:
        nonlocal file_processing_calls
        file_processing_calls += 1
        return params

    def forbidden_agent_callback(_message: object) -> bool:
        nonlocal agent_callback_calls
        agent_callback_calls += 1
        return False

    channel.send_response = capture_response  # type: ignore[method-assign]
    channel._process_files = forbidden_file_processing  # type: ignore[method-assign]
    channel.on_message(forbidden_agent_callback)
    try:
        await channel._handle_raw_message(
            ws,
            json.dumps(
                {
                    "type": "req",
                    "id": "registered",
                    "method": LATENCY_PROBE_BATCH_METHOD,
                    "params": {
                        "session_id": "registered-session",
                        "batch": _batch_dict(),
                    },
                }
            ),
            {},
        )
        await channel._handle_raw_message(
            ws,
            json.dumps(
                {
                    "type": "req",
                    "id": "chosen-by-client",
                    "method": LATENCY_PROBE_BATCH_METHOD,
                    "params": {
                        "session_id": "client-chosen-session",
                        "batch": _batch_dict(
                            batch_id="client-chosen-batch",
                            source_instance_id="client-chosen-source",
                        ),
                    },
                }
            ),
            {},
        )

        assert _payload(responses[0]) == {
            "status": "written",
            "batch_id": "browser-batch-0",
            "reason_code": None,
        }
        assert _payload(responses[1])["status"] == "rejected"
        assert _payload(responses[1])["reason_code"] == "IDENTITY_MISMATCH"
        assert channel._clients_by_key == {
            key: list(clients) for key, clients in registered_snapshot.items()
        }
        assert channel._ws_sessions == {}
        assert file_processing_calls == 0
        assert agent_callback_calls == 0
    finally:
        await channel.unregister_ws(ws)


@pytest.mark.asyncio
async def test_waiting_dispatch_revalidates_authority_after_disconnect(
    tmp_path: Path,
    run_config: Any,
) -> None:
    channel = WebChannel(WebChannelConfig(enabled=True), RobotMessageRouter())
    register_latency_probe_rpc_handler(channel, _runtime(tmp_path, run_config))
    ws = SimpleNamespace(closed=False, remote_address=("127.0.0.1", 12345))
    await channel.register_ws(
        ws,
        RoutingKey(
            user_id="user-1",
            channel_id="web",
            app_id="default",
            agent_ref=AgentRef(mode="agent", id="default"),
            session_id="registered-session",
        ),
    )
    first_send_entered = asyncio.Event()
    release_first_send = asyncio.Event()
    second_outer_resolution = asyncio.Event()
    responses: list[dict[str, object]] = []
    second_request_task: asyncio.Task[None] | None = None
    original_resolver = channel._registered_session_for_websocket

    def observed_resolver(target_ws: Any, claimed_session_id: object) -> str:
        resolved = original_resolver(target_ws, claimed_session_id)
        if asyncio.current_task() is second_request_task:
            second_outer_resolution.set()
        return resolved

    async def controlled_response(
        _ws: Any,
        req_id: str,
        *,
        ok: bool,
        payload: dict[str, object] | None = None,
        error: str | None = None,
        code: str | None = None,
    ) -> bool:
        if req_id == "first":
            first_send_entered.set()
            await release_first_send.wait()
        responses.append(
            {"id": req_id, "ok": ok, "payload": payload, "error": error, "code": code}
        )
        return True

    channel._registered_session_for_websocket = observed_resolver  # type: ignore[method-assign]
    channel.send_response = controlled_response  # type: ignore[method-assign]

    def request(request_id: str, batch: dict[str, object]) -> str:
        return json.dumps(
            {
                "type": "req",
                "id": request_id,
                "method": LATENCY_PROBE_BATCH_METHOD,
                "params": {
                    "session_id": "registered-session",
                    "batch": batch,
                },
            }
        )

    first_request_task = asyncio.create_task(
        channel._handle_raw_message(ws, request("first", _batch_dict()), {})
    )
    disconnected = False
    try:
        await asyncio.wait_for(first_send_entered.wait(), timeout=1.0)
        second_request_task = asyncio.create_task(
            channel._handle_raw_message(
                ws,
                request(
                    "second",
                    _batch_dict(batch_id="round-1", round_index=1),
                ),
                {},
            )
        )
        await asyncio.wait_for(second_outer_resolution.wait(), timeout=1.0)

        await channel.unregister_ws(ws)
        disconnected = True
        assert channel._clients_by_key == {}

        release_first_send.set()
        await asyncio.gather(first_request_task, second_request_task)

        output = tmp_path / "probe-output" / run_config.run_id / "browser.jsonl"
        assert len(output.read_text(encoding="utf-8").splitlines()) == 1
        assert [_payload(response) for response in responses] == [
            {
                "status": "written",
                "batch_id": "browser-batch-0",
                "reason_code": None,
            },
            {
                "status": "rejected",
                "batch_id": "",
                "reason_code": "IDENTITY_MISMATCH",
            },
        ]
    finally:
        release_first_send.set()
        if second_request_task is not None:
            await asyncio.gather(
                first_request_task,
                second_request_task,
                return_exceptions=True,
            )
        else:
            await asyncio.gather(first_request_task, return_exceptions=True)
        if not disconnected:
            await channel.unregister_ws(ws)


def test_registration_ignores_non_runtime_objects() -> None:
    channel = _FakeChannel()

    register_latency_probe_rpc_handler(channel, None)
    register_latency_probe_rpc_handler(channel, SimpleNamespace(writer=object()))  # type: ignore[arg-type]

    assert channel.handlers == {}
