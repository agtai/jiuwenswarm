# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

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

    async def send_response(
        self,
        ws: Any,
        req_id: str,
        *,
        ok: bool,
        payload: dict[str, object] | None = None,
        error: str | None = None,
        code: str | None = None,
    ) -> None:
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
async def test_real_web_dispatch_is_local_only_feature_on_and_feature_off(
    tmp_path: Path,
    run_config: Any,
) -> None:
    effects = {
        name: 0
        for name in (
            "media",
            "speech",
            "agent",
            "tool",
            "task",
            "presentation",
            "history",
            "ack",
            "next_turn",
        )
    }
    product_registry = {"voice": "unchanged", "task": "unchanged"}
    registry_snapshot = dict(product_registry)

    def forbidden_product_callback(_message: object) -> bool:
        for name in effects:
            effects[name] += 1
        product_registry["voice"] = "mutated"
        return False

    async def exercise(channel: WebChannel, request_id: str, params: object) -> list[dict[str, object]]:
        responses: list[dict[str, object]] = []

        async def capture_response(
            _ws: Any,
            req_id: str,
            *,
            ok: bool,
            payload: dict[str, object] | None = None,
            error: str | None = None,
            code: str | None = None,
        ) -> None:
            responses.append(
                {"id": req_id, "ok": ok, "payload": payload, "error": error, "code": code}
            )

        channel.send_response = capture_response  # type: ignore[method-assign]
        ws = SimpleNamespace(closed=False, remote_address=("127.0.0.1", 12345))
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
        return responses

    enabled = WebChannel(WebChannelConfig(enabled=True), RobotMessageRouter())
    enabled.on_message(forbidden_product_callback)
    register_latency_probe_rpc_handler(enabled, _runtime(tmp_path, run_config))

    async def forbidden_file_processing(params: dict[str, Any]) -> dict[str, Any]:
        effects["media"] += 1
        return params

    enabled._process_files = forbidden_file_processing  # type: ignore[method-assign]
    success = await exercise(
        enabled,
        "enabled",
        {"session_id": "session-1", "batch": _batch_dict()},
    )
    negative = await exercise(
        enabled,
        "negative",
        {"session_id": "session-1", "batch": {**_batch_dict(), "text": "PRIVATE"}},
    )

    disabled = WebChannel(WebChannelConfig(enabled=True), RobotMessageRouter())
    disabled.on_message(forbidden_product_callback)
    register_latency_probe_rpc_handler(disabled, None)
    disabled._process_files = forbidden_file_processing  # type: ignore[method-assign]
    feature_off = await exercise(
        disabled,
        "feature-off",
        {"session_id": "session-1", "batch": _batch_dict()},
    )

    faulted = WebChannel(WebChannelConfig(enabled=True), RobotMessageRouter())
    faulted.on_message(forbidden_product_callback)
    faulted._process_files = forbidden_file_processing  # type: ignore[method-assign]
    register_latency_probe_rpc_handler(
        faulted,
        LatencyProbeRuntime(
            run_config,
            "gateway",
            _RaiseWriter(OSError("private-writer-fault")),  # type: ignore[arg-type]
        ),
    )
    writer_fault = await exercise(
        faulted,
        "writer-fault",
        {"session_id": "session-1", "batch": _batch_dict(batch_id="fault-batch")},
    )

    assert success[0]["ok"] is True
    assert _payload(success[0])["status"] == "written"
    assert negative[0]["ok"] is True
    assert _payload(negative[0])["status"] == "rejected"
    assert feature_off == [
        {
            "id": "feature-off",
            "ok": False,
            "payload": None,
            "error": f"unknown method: {LATENCY_PROBE_BATCH_METHOD}",
            "code": "METHOD_NOT_FOUND",
        }
    ]
    assert _payload(writer_fault[0]) == {
        "status": "failed",
        "batch_id": "fault-batch",
        "reason_code": "EXPORT_FAILED",
    }
    assert enabled._ws_sessions == {}
    assert disabled._ws_sessions == {}
    assert faulted._ws_sessions == {}
    assert effects == {name: 0 for name in effects}
    assert product_registry == registry_snapshot


def test_registration_ignores_non_runtime_objects() -> None:
    channel = _FakeChannel()

    register_latency_probe_rpc_handler(channel, None)
    register_latency_probe_rpc_handler(channel, SimpleNamespace(writer=object()))  # type: ignore[arg-type]

    assert channel.handlers == {}
