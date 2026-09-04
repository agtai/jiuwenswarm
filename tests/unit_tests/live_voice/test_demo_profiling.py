"""Contract tests for passive rehearsal timing and offline diagnosis."""
import asyncio
import json

import pytest

from jiuwenswarm.common import live_voice_audio_diagnostics as sink
from jiuwenswarm.common import live_voice_profiling as profile
from scripts.live_voice import analyze_demo_profile as report


@pytest.fixture
def records(monkeypatch):
    result = []
    monkeypatch.setattr(profile, "record_audio_diagnostic", lambda event, **fields: result.append((event, fields)))
    return result


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["return", "reject", "timeout", "cancel", "error"])
async def test_one_call_preserves_result_error_cancel_and_no_payload(records, outcome):
    calls = []
    result = {"ok": outcome != "reject", "content": "PRIVATE_CONTENT"}
    errors = {"timeout": TimeoutError("PRIVATE_TIMEOUT"), "cancel": asyncio.CancelledError(), "error": ValueError("PRIVATE_ERROR")}

    @profile.profiled("test.call", "request")
    async def call(request):
        calls.append(request)
        if outcome in errors:
            raise errors[outcome]
        return result

    request = {"session_id": "session-a", "request_id": "request-a", "token": "PRIVATE_KEY", "query": "PRIVATE_PROMPT"}
    if outcome in errors:
        with pytest.raises(type(errors[outcome])) as caught:
            await call(request)
        assert caught.value is errors[outcome]
    else:
        assert await call(request) is result
    assert calls == [request]
    assert len(records) == 2
    assert records[0][0] == "profile_span_started"
    assert records[-1][1]["outcome"] == {"return": "returned", "reject": "rejected", "error": "failed", "cancel": "cancelled"}.get(outcome, outcome)
    assert records[-1][1]["duration_ms"] >= 0
    assert "PRIVATE" not in repr(records)
    assert profile.current_profile_fields() == {}


@pytest.mark.asyncio
async def test_nested_concurrent_context_and_thread_propagation(records):
    entered = asyncio.Event()

    @profile.profiled("child", "request")
    async def child(request):
        await entered.wait()
        return await asyncio.to_thread(lambda: dict(profile.current_profile_fields()))

    @profile.profiled("parent", "request")
    async def parent(request):
        return await child(request)

    tasks = [asyncio.create_task(parent({"session_id": name, "request_id": name})) for name in ["a", "b"]]
    entered.set()
    a, b = await asyncio.gather(*tasks)
    assert a["session_id"] == "a" and b["session_id"] == "b"
    assert a["span_id"] != b["span_id"] and a["parent_span_id"] != b["parent_span_id"]
    assert profile.current_profile_fields() == {}
    for name in ["a", "b"]:
        local = [fields for _, fields in records if fields.get("session_id") == name]
        parent_id = next(fields["span_id"] for fields in local if fields["stage"] == "parent")
        assert all(fields["parent_span_id"] == parent_id for fields in local if fields["stage"] == "child")


@pytest.mark.asyncio
async def test_observer_failure_hostile_getter_and_media_identity_cannot_change_call(monkeypatch):
    monkeypatch.setattr(profile, "record_audio_diagnostic", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("sink")))
    class Hostile:
        @property
        def session_id(self):
            raise ValueError("PRIVATE")

    calls = []
    @profile.profiled("test", "request")
    async def call(request):
        calls.append(request)
        return request
    value = Hostile()
    assert await call(value) is value
    assert calls == [value] and profile.current_profile_fields() == {}
    ref = type("RecognitionStreamRef", (), {"session_id": "media-a", "capture": {"capture_id": "capture-a"}})()
    assert profile.identity_fields({"scope": {"session_id": "chat-a"}, "ref": ref}) == {
        "session_id": "chat-a", "media_session_id": "media-a", "capture_id": "capture-a"}


def row(event, seq, time_ms, clock="process-a", **fields):
    return report.sanitize_record({"event": event, "sequence": seq, "clock_id": clock,
        "monotonic_ms": time_ms, "observed_at": "2026-09-04T16:00:00.000Z", "fields": fields})


def test_report_pairs_only_exact_clock_span_or_tool_and_retains_unfinished():
    rows = [row("profile_span_started", 1, 100, span_id="a", stage="semantic.resolve"),
            row("profile_span_settled", 2, 115, span_id="a", stage="semantic.resolve", duration_ms=15, outcome="returned"),
            row("profile_span_started", 3, 110, span_id="open", stage="synthesis.first_audio"),
            row("profile_span_settled", 4, 2, clock="process-b", span_id="open", stage="synthesis.first_audio", duration_ms=2, outcome="failed"),
            row("tool_boundary", 5, 120, tool_call_id="tool-b", request_id="r", milestone="chat.tool_call"),
            row("tool_boundary", 6, 140, tool_call_id="tool-b", request_id="r", milestone="chat.tool_result", outcome="complete"),
            row("tool_boundary", 7, 150, tool_call_id="missing", request_id="r", milestone="chat.tool_result")]
    result = report.build_report(rows)
    assert any(span["state"] == "open_or_truncated" and span["duration_ms"] is None for span in result["spans"])
    assert len([span for span in result["spans"] if span["state"] == "start_missing"]) == 2
    assert next(span for span in result["spans"] if span["stage"] == "tool.unknown" and span["state"] == "complete")["duration_ms"] == 20
    assert result["coverage"]["Browser playback"] == 0
    assert len(result["failures"]) == 1
    assert report.chrome_trace(result)["traceEvents"]


def test_import_privacy_dedup_unknown_clock_retention_and_html_injection(tmp_path):
    value = {"event": "capture_progress", "sequence": 1, "clock_id": "browser-a", "monotonic_ms": 10,
             "observed_at": "2026-09-04T16:00:00Z", "fields": {"session_id": "s", "pcm": "PRIVATE_PCM", "prompt": "PRIVATE_PROMPT", "stage": "<script>PRIVATE</script>"}}
    log = tmp_path / "service.log"
    log.write_text("PRIVATE_FULL_LOG\nlive_voice_audio_diagnostic " + json.dumps(value) + "\n", encoding="utf-8")
    browser = tmp_path / "browser.json"
    browser.write_text(json.dumps({"records": [value], "overwritten_pages": 1}), encoding="utf-8")
    rows, warnings, retention = report.load_records([log], [browser])
    assert len(rows) == 1 and "PRIVATE" not in repr(rows)
    assert warnings and retention[0]["overwritten_pages"] == 1
    assert report.select_session(rows, "foreign") == []
    built = report.build_report(rows, ["</script><script>alert(1)</script>"])
    page = report.render_html(built)
    assert "</script><script>alert(1)" not in page
    assert "textContent" in page
    assert report.main(["--log", str(log), "--browser", str(browser), "--output", str(tmp_path / "out")]) == 0
    assert (tmp_path / "out/profile.html").is_file()


def test_session_join_keeps_explicit_foreign_session_out():
    rows = [row("opened", 1, 1, session_id="a", request_id="r"),
            row("opened", 2, 2, request_id="r", capture_id="c"),
            row("opened", 3, 3, capture_id="c"),
            row("opened", 4, 4, session_id="b", request_id="r")]
    assert len(report.select_session(rows, "a")) == 3


def test_synthesis_response_identity_survives_session_filter_without_unit_guessing():
    from jiuwenswarm.common.schema.live_voice_contract_v2 import ResponseRef
    from jiuwenswarm.server.live_voice.streaming_speech import SynthesisStreamRef

    ref_a = SynthesisStreamRef("stream-a", 1, ResponseRef("interaction-a", "response-a", 1), "unit", 0)
    ref_b = SynthesisStreamRef("stream-b", 1, ResponseRef("interaction-b", "response-b", 1), "unit", 0)
    ids_a = profile.identity_fields({"ref": ref_a, "spoken_text": "PRIVATE"})
    ids_b = profile.identity_fields({"ref": ref_b})
    assert ids_a["response_id"] == "response-a"
    assert ids_a["interaction_id"] == "interaction-a"
    assert "PRIVATE" not in repr(ids_a)
    rows = [row("playout", 1, 1, session_id="a", response_id="response-a"),
            row("profile_span_started", 2, 2, stage="synthesis.begin", span_id="span-a", **ids_a),
            row("profile_span_settled", 3, 3, stage="synthesis.begin", span_id="span-a", duration_ms=1, **ids_a),
            row("profile_span_started", 4, 4, stage="synthesis.begin", span_id="span-b", **ids_b)]
    selected = report.select_session(rows, "a")
    assert len(selected) == 3
    assert report.build_report(selected)["coverage"]["Synthesis / first audio"] == 2
    assert all(r["fields"].get("response_id") != "response-b" for r in selected)


@pytest.mark.parametrize("duration,counter", [(0.13812345678, 12), (13812345678.0, 13812345678),
                                              (123456789012345678.0, 2**53 - 1)])
def test_diagnostic_numbers_remain_json_through_actual_sensitive_log_filter(monkeypatch, duration, counter):
    import logging
    from jiuwenswarm.common.utils import SensitiveDataFilter

    captured = []
    monkeypatch.setattr(sink, "_WORKER", object())
    monkeypatch.setattr(sink._QUEUE, "put_nowait", captured.append)
    monkeypatch.setattr(sink.time, "perf_counter", lambda: 13812345.678)
    monkeypatch.setattr(sink, "_SEQUENCE", iter([counter]))
    monkeypatch.setattr(sink, "_DROPPED", counter)
    sink.record_audio_diagnostic("profile_span_settled", duration_ms=duration,
                                 phase_ms=1.13912345678, frame_count=counter, speech_started=True,
                                 transcript="PRIVATE", api_key="PRIVATE")
    record = logging.LogRecord("diagnostics", logging.INFO, __file__, 1,
                               "live_voice_audio_diagnostic %s", (captured[0],), None)
    assert SensitiveDataFilter().filter(record)
    message = record.getMessage()
    assert "PRIVATE" not in message
    parsed = json.loads(message.split("live_voice_audio_diagnostic ", 1)[1])
    assert parsed["fields"] == {"duration_ms": round(duration, 3), "phase_ms": 1.139,
                                "frame_count": counter, "speech_started": True}
    assert parsed["monotonic_ms"] == 13812345678
    imported = report.sanitize_record(parsed)
    assert imported["sequence"] == counter
    assert imported["dropped_records"] == counter
    assert type(imported["sequence"]) is int


def test_numeric_encoding_never_rewrites_quoted_ids_or_escaped_content(tmp_path):
    value = {"fields": {"request_id": "request-13812345678", "quoted": '"13812345678"',
                        "frame_count": 13812345678, "duration_ms": -13812345678.125}}
    encoded = sink._encode_record(value)
    assert json.loads(encoded) == value
    assert '"request-13812345678"' in encoded
    assert report._counter(True, None) is None
    assert report._counter(1.5, None) is None
    assert report._counter(float("inf"), None) is None
    assert report._counter(10**1000, None) is None
    raw = {"event": "profile_span_settled", "sequence": 10**1000, "dropped_records": 10**1000,
           "clock_id": "python-a", "monotonic_ms": 1, "observed_at": "2026-09-04T16:00:00Z", "fields": {}}
    log = tmp_path / "oversized-counter.log"
    log.write_text("live_voice_audio_diagnostic " + json.dumps(raw) + "\n", encoding="utf-8")
    imported, _, _ = report.load_records([log], [])
    assert len(imported) == 1 and imported[0]["sequence"] is None
    assert imported[0]["dropped_records"] == 0


def test_existing_sink_inherits_only_safe_scope_and_never_error_text(monkeypatch):
    captured = []
    monkeypatch.setattr(sink, "_WORKER", object())
    monkeypatch.setattr(sink._QUEUE, "put_nowait", lambda value: captured.append(json.loads(value)))
    with profile.ProfileSpan("speech.test", session_id="a"):
        sink.record_audio_diagnostic("wire_observed", transcript="PRIVATE", frame_count=2)
    assert captured and "PRIVATE" not in repr(captured)
    assert all(item["clock_id"] and item["sequence"] for item in captured)
    assert all(item["fields"]["session_id"] == "a" for item in captured)


def test_http_model_tool_boundaries_and_backward_wall_clock_are_not_mispaired():
    rows = [row("model_stream_started", 1, 10, model_call_id="m1", request_id="r"),
            row("model_stream_settled", 2, 50, model_call_id="m1", request_id="r", duration_ms=40, first_output_ms=8, outcome="complete"),
            row("batch_http_phase", 3, 55, operation_id="op", http_phase="receive_response_headers", outcome="started"),
            row("batch_http_phase", 4, 75, operation_id="op", http_phase="receive_response_headers", outcome="failed", phase_ms=20),
            row("tool_boundary", 5, 80, request_id="r", tool_call_id="t", milestone="chat.tool_call"),
            row("tool_boundary", 6, 85, request_id="r", tool_call_id="t", milestone="chat.tool_call"),
            row("tool_boundary", 7, 90, request_id="r", tool_call_id="t", milestone="chat.tool_result", outcome="complete")]
    rows[0]["wall_ms"] += 1000  # Clock correction must not reverse the pair.
    result = report.build_report(rows)
    assert next(s for s in result["spans"] if s["stage"] == "model.stream")["duration_ms"] == 40
    assert next(s for s in result["spans"] if s["stage"] == "http.receive_response_headers")["duration_ms"] == 20
    assert any(s["state"] == "duplicate_start" and s["duration_ms"] is None for s in result["spans"])
    assert result["failures"]
    trace = report.chrome_trace(result)["traceEvents"]
    assert all(type(event["pid"]) is int and type(event["tid"]) is int for event in trace)
    for index, left in enumerate(trace):
        if left["ph"] != "X":
            continue
        for right in trace[index + 1:]:
            if right["ph"] == "X" and (left["pid"], left["tid"]) == (right["pid"], right["tid"]):
                assert left["ts"] + left["dur"] <= right["ts"]


def test_stable_error_reason_and_tool_ids_without_private_data(records):
    from jiuwenswarm.server.live_voice.formal_task_models import ErrorCode, FormalTaskViolation
    error = FormalTaskViolation("SEMANTIC_PROVIDER_TIMEOUT", "PRIVATE_ERROR", ErrorCode.TIMEOUT)
    fields = profile.error_fields(error)
    assert fields["error_reason"] == "SEMANTIC_PROVIDER_TIMEOUT"
    assert "PRIVATE" not in repr(fields)
    for payload in [{"event_type": "chat.tool_call", "tool_call": {"tool_call_id": "t", "tool_name": "read_file", "arguments": "PRIVATE"}},
                    {"event_type": "chat.tool_result", "tool_call_id": "t", "tool_name": "read_file", "success": False, "content": "PRIVATE"}]:
        profile.profile_tool_event(payload, request_id="r")
    assert len(records) == 2 and all(f["tool_call_id"] == "t" for _, f in records)
    assert records[-1][1]["outcome"] == "failed" and "PRIVATE" not in repr(records)


def test_cli_missing_file_has_actionable_error_not_traceback(capsys):
    with pytest.raises(SystemExit) as failed:
        report.main(["--log", "missing-rehearsal-log-for-test.log"])
    assert failed.value.code == 2
    output = capsys.readouterr().err
    assert "check --log/--browser paths" in output and "Traceback" not in output


@pytest.mark.asyncio
@pytest.mark.parametrize("ending", ["complete", "failure", "early_close"])
async def test_private_task_model_preserves_stream_and_foreign_task_close(records, ending):
    from types import SimpleNamespace
    from jiuwenswarm.server.runtime.agent_adapter.formal_model_diagnostics import observe_private_task_model
    calls, closed = [], []
    chunk = object()
    failure = RuntimeError("PRIVATE")
    class Client:
        async def invoke(self, *args, **kwargs):
            calls.append((args, kwargs))
            return chunk

        async def stream(self, *args, **kwargs):
            calls.append((args, kwargs))
            try:
                yield chunk
                if ending == "failure":
                    raise failure
            finally:
                closed.append(True)

    original = Client()
    model = SimpleNamespace(_client=original)
    # Dedicated Code adapters are also used outside Live Voice; stay silent there.
    observe_private_task_model(model, request_id="r", session_id="formal-task-a")
    assert model._client is original
    with profile.ProfileSpan("executor.run_attempt", task_id="task-a"):
        observe_private_task_model(model, request_id="r", session_id="formal-task-a")
        first = model._client
        observe_private_task_model(model, request_id="r", session_id="formal-task-a")
        assert model._client is first
        assert await model._client.invoke("PRIVATE") is chunk
        stream = model._client.stream("PRIVATE")
        assert await anext(stream) is chunk
    if ending == "early_close":
        with profile.ProfileSpan("unrelated", task_id="task-b", session_id="foreign-only", operation_id="foreign-operation"):
            await asyncio.create_task(stream.aclose())
    elif ending == "failure":
        with pytest.raises(RuntimeError) as caught:
            await anext(stream)
        assert caught.value is failure
    else:
        with pytest.raises(StopAsyncIteration):
            await anext(stream)
    assert len(calls) == 2 and closed == [True]
    settled = [fields for event, fields in records if event == "model_stream_settled"]
    assert len(settled) == 1 and settled[0]["task_id"] == "task-a"
    assert "foreign" not in repr(settled)
    assert settled[0]["outcome"] == {"early_close": "cancelled", "failure": "failed", "complete": "complete"}[ending]
    assert settled[0]["chunk_count"] == 1 and "PRIVATE" not in repr(records)
    assert settled[0]["max_chunk_gap_ms"] == 0  # First-output wait has its own field.
    with profile.ProfileSpan("executor.adjust", task_id="task-a"):
        observe_private_task_model(model, request_id="r2", session_id="formal-task-a")
    assert model._client._client is original  # No stacking across adjustment requests.


def test_snapshot_event_bypasses_the_actual_sink_context_merge(monkeypatch):
    captured = []
    monkeypatch.setattr(sink, "_WORKER", object())
    monkeypatch.setattr(sink._QUEUE, "put_nowait", lambda value: captured.append(json.loads(value)))
    with profile.ProfileSpan("foreign", session_id="foreign-only", operation_id="foreign-operation"):
        profile.profile_snapshot_event("model_stream_settled", {"task_id": "origin"}, outcome="cancelled")
    event = next(row for row in captured if row["event"] == "model_stream_settled")
    assert event["fields"] == {"task_id": "origin", "outcome": "cancelled"}


@pytest.mark.asyncio
async def test_shared_agent_rpc_is_silent_without_live_voice_context(records):
    calls = []
    @profile.profiled("gateway.agent_rpc", "envelope", require_context=True)
    async def send(envelope):
        calls.append(envelope)
        return envelope
    ordinary = {"request_id": "heartbeat"}
    assert await send(ordinary) is ordinary
    assert records == []
    with profile.ProfileSpan("agent.round", session_id="voice"):
        assert await send({"request_id": "voice-request"}) == {"request_id": "voice-request"}
    assert len(calls) == 2
    assert len([f for _, f in records if f.get("stage") == "gateway.agent_rpc"]) == 2


def test_nested_registry_rejection_preserves_only_structured_breadcrumbs(records):
    from jiuwenswarm.server.live_voice.product_composition_registry import P3RouteResult
    result = P3RouteResult(False, {"error": {"code": "STALE", "reason": "STALE_ACTIVATION", "message": "PRIVATE", "details": {"secret": "PRIVATE"}}})
    with profile.ProfileSpan("rpc.activation") as span:
        assert span.result(result) is result
    assert records[-1][1]["outcome"] == "rejected"
    assert records[-1][1]["error_code"] == "STALE"
    assert records[-1][1]["error_reason"] == "STALE_ACTIVATION"
    assert "PRIVATE" not in repr(records)


def test_report_includes_state_failures_and_fallback_milestones():
    rows = [row("capture_state", 1, 1, status="failed", reason="AUDIO_WORKLET_FAILED"),
            row("playout_state", 2, 2, status="failed", reason="PLAYOUT_FAILED"),
            row("runtime_milestone", 3, 3, milestone="fallback"),
            row("capture_state", 4, 4, status="active"),
            row("p1_status", 5, 5, status="cleanup_pending")]
    assert report.build_report(rows)["failures"] == rows[:3]
