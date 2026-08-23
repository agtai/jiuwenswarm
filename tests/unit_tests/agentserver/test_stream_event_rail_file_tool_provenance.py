import json
from dataclasses import asdict
from types import SimpleNamespace

import pytest
from openjiuwen.core.session.stream import OutputSchema
from openjiuwen.core.single_agent.rail.base import ToolCallInputs

from jiuwenswarm.agents.harness.common.rails.stream_event_rail import (
    JiuSwarmStreamEventRail,
)
from jiuwenswarm.server.live_voice.project_code_executor import (
    _closed_direct_stream_observation,
)
from jiuwenswarm.server.runtime.agent_adapter.interface_deep import (
    JiuWenSwarmDeepAdapter,
)
from scripts.live_voice.p3_wave2_real_evidence_validator import observation_counts


class _StreamSession:
    def __init__(self) -> None:
        self.chunks = []

    async def write_stream(self, chunk) -> None:
        self.chunks.append(chunk)


class _DetailedResult(dict):
    def __init__(self, value: dict[str, object], detailed_output: object) -> None:
        super().__init__(value)
        self.detailed_output = detailed_output


def _tool_context(
    session: _StreamSession,
    *,
    result: object,
    exception: BaseException | None = None,
    tool_name: str = "write_file",
):
    tool_call = SimpleNamespace(
        id="call-write-1",
        name=tool_name,
        arguments={"path": "PRIVATE_PATH_SENTINEL"},
    )
    force_finish_requests = []
    return SimpleNamespace(
        session=session,
        inputs=ToolCallInputs(
            tool_call=tool_call,
            tool_name=tool_name,
            tool_args=dict(tool_call.arguments),
            tool_result=result,
        ),
        extra={},
        exception=exception,
        request_force_finish=force_finish_requests.append,
        force_finish_requests=force_finish_requests,
    )


def _direct_observations(chunks: list[object]) -> list[object]:
    observations = []
    for chunk in chunks:
        parsed = JiuWenSwarmDeepAdapter._parse_stream_chunk(chunk)
        if not isinstance(parsed, dict) or parsed.get("event_type") not in {
            "chat.tool_call",
            "chat.tool_result",
        }:
            continue
        observation = _closed_direct_stream_observation(
            parsed,
            task_ref="task-1",
            attempt_ref="attempt-1",
            run_ref="run-1",
            sequence=len(observations) + 1,
            stream_kind="initial",
            observed_at="2026-08-20T12:00:00Z",
        )
        assert observation is not None
        observations.append(observation)
    return observations


@pytest.mark.asyncio
async def test_normal_file_tool_callback_produces_content_free_success_pair() -> None:
    private_result = "PRIVATE_RESULT_SENTINEL: file written"
    rail = JiuSwarmStreamEventRail()
    session = _StreamSession()
    ctx = _tool_context(session, result=private_result)

    await rail.before_tool_call(ctx)
    await rail.after_tool_call(ctx)

    observations = _direct_observations(session.chunks)
    closed = [asdict(item) for item in observations]
    assert observation_counts(closed) == {
        "observations": 2,
        "tool_calls": 1,
        "tool_results": 1,
        "paired_file_tools": 1,
        "write_edit_pairs": 1,
        "unknown_observations": 0,
        "sequence_gaps": 0,
        "unpaired_observations": 0,
    }
    assert observations[0].tool_name_digest == observations[1].tool_name_digest
    assert observations[0].call_id_digest == observations[1].call_id_digest
    assert private_result not in repr(observations)
    assert "PRIVATE_PATH_SENTINEL" not in repr(observations)
    assert private_result not in json.dumps(closed)
    assert "PRIVATE_PATH_SENTINEL" not in json.dumps(closed)


@pytest.mark.parametrize(
    "success_result",
    [
        pytest.param({"success": True}, id="boolean-success-true"),
        pytest.param({"success": 1}, id="numeric-success-one"),
        pytest.param({"success": "1"}, id="string-success-one"),
        pytest.param({"is_error": False}, id="boolean-is-error-false"),
        pytest.param({"is_error": 0}, id="numeric-is-error-zero"),
        pytest.param({"isError": "0"}, id="string-is-error-zero"),
    ],
)
@pytest.mark.asyncio
async def test_supported_structured_success_markers_keep_callback_success(
    success_result: object,
) -> None:
    rail = JiuSwarmStreamEventRail()
    session = _StreamSession()
    ctx = _tool_context(session, result=success_result)

    await rail.before_tool_call(ctx)
    await rail.after_tool_call(ctx)

    observations = _direct_observations(session.chunks)
    counts = observation_counts([asdict(item) for item in observations])
    assert observations[-1].result_status == "success"
    assert counts["write_edit_pairs"] == 1


@pytest.mark.asyncio
async def test_file_tool_callback_exception_never_produces_success_pair() -> None:
    private_exception = "PRIVATE_EXCEPTION_SENTINEL"
    rail = JiuSwarmStreamEventRail()
    session = _StreamSession()
    ctx = _tool_context(
        session,
        result="no authoritative result",
        exception=RuntimeError(private_exception),
    )

    await rail.before_tool_call(ctx)
    await rail.after_tool_call(ctx)

    observations = _direct_observations(session.chunks)
    assert observations[-1].result_status == "error"
    assert (
        observation_counts([asdict(item) for item in observations])["write_edit_pairs"]
        == 0
    )
    assert private_exception not in repr(observations)


@pytest.mark.asyncio
async def test_explicit_file_tool_failure_never_produces_success_pair() -> None:
    private_error = "PRIVATE_FAILURE_SENTINEL"
    rail = JiuSwarmStreamEventRail()
    session = _StreamSession()
    ctx = _tool_context(
        session,
        result={"success": False, "error": private_error},
    )

    await rail.before_tool_call(ctx)
    await rail.after_tool_call(ctx)

    observations = _direct_observations(session.chunks)
    counts = observation_counts([asdict(item) for item in observations])
    assert observations[-1].result_status == "error"
    assert counts["paired_file_tools"] == 1
    assert counts["write_edit_pairs"] == 0
    assert counts["unknown_observations"] == 0
    assert private_error not in repr(observations)


@pytest.mark.asyncio
async def test_structured_failure_overrides_conflicting_success_signal() -> None:
    rail = JiuSwarmStreamEventRail()
    session = _StreamSession()
    ctx = _tool_context(
        session,
        result={"success": True, "status": "failed"},
    )

    await rail.before_tool_call(ctx)
    await rail.after_tool_call(ctx)

    observations = _direct_observations(session.chunks)
    assert observations[-1].result_status == "error"
    assert (
        observation_counts([asdict(item) for item in observations])["write_edit_pairs"]
        == 0
    )


@pytest.mark.parametrize(
    "failure_result",
    [
        pytest.param({"success": 0}, id="numeric-success-zero"),
        pytest.param({"success": "0"}, id="string-success-zero"),
        pytest.param({"success": 2}, id="invalid-numeric-success-two"),
        pytest.param({"success": float("nan")}, id="invalid-numeric-success-nan"),
        pytest.param({"is_error": 1}, id="numeric-is-error-one"),
        pytest.param({"isError": "1"}, id="string-is-error-one"),
        pytest.param({"is_error": "maybe"}, id="invalid-is-error-string"),
        pytest.param({"status": "pending"}, id="invalid-status-pending"),
        pytest.param({"status": "unknown"}, id="invalid-status-unknown"),
        pytest.param({"exit_code": "bad"}, id="invalid-exit-code"),
        *[
            pytest.param({"status": status}, id=f"status-{status}")
            for status in (
                "error",
                "failed",
                "failure",
                "rejected",
                "cancelled",
                "canceled",
                "interrupted",
                "skipped",
                "permission_denied",
                "denied",
                "aborted",
                "timeout",
            )
        ],
        pytest.param(
            {"error": "PRIVATE_STRUCTURED_ERROR_SENTINEL"},
            id="nonempty-error",
        ),
        pytest.param(
            _DetailedResult(
                {"status": "failed"},
                detailed_output={"success": True},
            ),
            id="outer-failure-with-detailed-success",
        ),
        pytest.param(
            {
                "data": {
                    "result": {
                        "items": [
                            {"success": True},
                            {"status": "cancelled"},
                        ]
                    }
                }
            },
            id="deep-failure-after-success",
        ),
    ],
)
@pytest.mark.asyncio
async def test_every_explicit_structured_failure_blocks_file_tool_success(
    failure_result: object,
) -> None:
    rail = JiuSwarmStreamEventRail()
    session = _StreamSession()
    ctx = _tool_context(session, result=failure_result)

    await rail.before_tool_call(ctx)
    await rail.after_tool_call(ctx)

    observations = _direct_observations(session.chunks)
    counts = observation_counts([asdict(item) for item in observations])
    assert observations[-1].result_status == "error"
    assert counts["paired_file_tools"] == 1
    assert counts["write_edit_pairs"] == 0
    assert "PRIVATE_STRUCTURED_ERROR_SENTINEL" not in repr(observations)


@pytest.mark.parametrize("malformed_kind", ["cycle", "too-deep", "too-many-nodes"])
@pytest.mark.asyncio
async def test_malformed_structured_outcomes_fail_closed_without_recursion(
    malformed_kind: str,
) -> None:
    if malformed_kind == "cycle":
        malformed_result: dict[str, object] = {}
        malformed_result["wrapper"] = malformed_result
    elif malformed_kind == "too-deep":
        malformed_result = {"value": "ordinary callback output"}
        for _ in range(128):
            malformed_result = {"wrapper": malformed_result}
    else:
        malformed_result = {
            "items": [{"value": index} for index in range(5000)],
        }

    rail = JiuSwarmStreamEventRail()
    session = _StreamSession()
    ctx = _tool_context(session, result=malformed_result)

    await rail.before_tool_call(ctx)
    await rail.after_tool_call(ctx)

    observations = _direct_observations(session.chunks)
    counts = observation_counts([asdict(item) for item in observations])
    assert observations[-1].result_status == "error"
    assert counts["paired_file_tools"] == 1
    assert counts["write_edit_pairs"] == 0


@pytest.mark.parametrize(
    ("result", "exception"),
    [
        pytest.param(
            {
                "status": "permission_denied",
                "direct_display": True,
                "content": "PRIVATE_FAILED_DISPLAY_SENTINEL",
            },
            None,
            id="structured-failure",
        ),
        pytest.param(
            {
                "success": True,
                "direct_display": True,
                "content": "PRIVATE_EXCEPTION_DISPLAY_SENTINEL",
            },
            RuntimeError("PRIVATE_CALLBACK_EXCEPTION_SENTINEL"),
            id="callback-exception",
        ),
    ],
)
@pytest.mark.asyncio
async def test_failed_symphony_callback_never_requests_force_finish(
    result: object,
    exception: BaseException | None,
) -> None:
    rail = JiuSwarmStreamEventRail()
    session = _StreamSession()
    ctx = _tool_context(
        session,
        result=result,
        exception=exception,
        tool_name="symphony_compose_graph",
    )

    await rail.before_tool_call(ctx)
    await rail.after_tool_call(ctx)

    observations = _direct_observations(session.chunks)
    assert observations[-1].result_status == "error"
    assert ctx.force_finish_requests == []
    assert "PRIVATE_FAILED_DISPLAY_SENTINEL" not in repr(observations)
    assert "PRIVATE_EXCEPTION_DISPLAY_SENTINEL" not in repr(observations)
    assert "PRIVATE_CALLBACK_EXCEPTION_SENTINEL" not in repr(observations)


def test_raw_result_text_without_callback_authority_remains_unknown() -> None:
    private_result = "PRIVATE_RAW_SENTINEL: success: True"
    raw = OutputSchema(
        type="tool_result",
        index=0,
        payload={
            "tool_result": {
                "tool_name": "write_file",
                "tool_call_id": "call-write-1",
                "result": private_result,
            }
        },
    )

    observations = _direct_observations([raw])

    assert observations[0].file_tool_kind == "write"
    assert observations[0].result_status == "unknown"
    assert private_result not in repr(observations)


def test_malformed_tool_identity_remains_unknown_and_content_free() -> None:
    private_result = "PRIVATE_MALFORMED_SENTINEL"
    raw = OutputSchema(
        type="tool_result",
        index=0,
        payload={
            "tool_result": {
                "tool_name": ["write_file"],
                "tool_call_id": None,
                "result": private_result,
                "success": True,
            }
        },
    )

    observations = _direct_observations([raw])
    counts = observation_counts([asdict(observations[0])])

    assert observations[0].file_tool_kind == "unknown"
    assert counts["unknown_observations"] == 1
    assert counts["write_edit_pairs"] == 0
    assert private_result not in repr(observations)
