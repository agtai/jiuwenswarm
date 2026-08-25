from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from jiuwenswarm.common.schema.agent import AgentResponseChunk
from scripts.live_voice import pre_final_stable_segmentation_screen as screen


class _Facade:
    def __init__(
        self,
        events: tuple[tuple[str, str], ...],
        *,
        block: bool = False,
    ) -> None:
        self.events = events
        self.block = block

    def supports_formal_live_voice(self) -> bool:
        return True

    async def process_formal_live_voice_stream(self, execution):
        if self.block:
            await asyncio.Event().wait()
        for event_type, content in self.events:
            yield AgentResponseChunk(
                request_id=execution.request_id,
                channel_id=execution.channel_id,
                payload={"event_type": event_type, "content": content},
                is_complete=event_type == "chat.final",
            )


class _Clock:
    def __init__(self, values: tuple[float, ...]) -> None:
        self._values = iter(values)

    def __call__(self) -> float:
        return next(self._values)


WORKLOAD = screen.Workload("medium", "private prompt")


@pytest.mark.asyncio
async def test_exact_prefix_waits_for_lookahead_and_retains_ordered_timings() -> None:
    attempt = await screen.measure_attempt(
        _Facade(
            (
                ("chat.delta", "Paris is the capital. "),
                ("chat.delta", "It is in France."),
                ("chat.final", "Paris is the capital. It is in France."),
            )
        ),
        WORKLOAD,
        0,
        monotonic=_Clock((10.0, 10.4, 10.9)),
    )

    assert attempt.outcome == "completed"
    assert attempt.agent_to_candidate_ms == pytest.approx(400.0)
    assert attempt.candidate_to_final_ms == pytest.approx(500.0)
    assert attempt.agent_to_final_ms == pytest.approx(900.0)
    assert attempt.reconciliation_disposition == "exact_prefix"
    assert "private" not in json.dumps(attempt.to_dict())


@pytest.mark.asyncio
async def test_first_delta_with_terminal_punctuation_is_not_a_candidate() -> None:
    attempt = await screen.measure_attempt(
        _Facade(
            (
                ("chat.delta", "Paris is the capital."),
                ("chat.final", "Paris is the capital."),
            )
        ),
        WORKLOAD,
        0,
        monotonic=_Clock((10.0, 10.5)),
    )

    assert attempt.outcome == "failed"
    assert attempt.reason == "NO_STABLE_CANDIDATE"
    assert attempt.agent_to_candidate_ms is None
    assert attempt.candidate_to_final_ms is None
    assert attempt.agent_to_final_ms is None


@pytest.mark.asyncio
async def test_final_rewrite_fails_closed_without_attractive_timing() -> None:
    attempt = await screen.measure_attempt(
        _Facade(
            (
                ("chat.delta", "Paris is the capital. "),
                ("chat.delta", "More follows."),
                ("chat.final", "Lyon is the capital. More follows."),
            )
        ),
        WORKLOAD,
        0,
        monotonic=_Clock((10.0, 10.4, 10.9)),
    )

    assert attempt.outcome == "failed"
    assert attempt.reason == "PREFIX_RECONCILIATION_FAILED"
    assert attempt.reconciliation_disposition == "rewrite_after_commit"
    assert attempt.agent_to_candidate_ms is None
    assert attempt.candidate_to_final_ms is None
    assert attempt.agent_to_final_ms is None


@pytest.mark.asyncio
@pytest.mark.parametrize("event_type", ("chat.tool_call", "chat.tool_result", "chat.error"))
async def test_forbidden_or_error_events_fail_closed(event_type: str) -> None:
    attempt = await screen.measure_attempt(
        _Facade(((event_type, "private payload"),)),
        WORKLOAD,
        0,
        monotonic=_Clock((10.0,)),
    )

    assert attempt.outcome == "failed"
    assert attempt.agent_to_candidate_ms is None
    assert attempt.candidate_to_final_ms is None
    assert attempt.agent_to_final_ms is None
    assert attempt.forbidden_effects == screen.ZERO_FORBIDDEN_EFFECTS


@pytest.mark.asyncio
async def test_timeout_fails_closed_and_cleans_up() -> None:
    attempt = await screen.measure_attempt(
        _Facade((), block=True),
        WORKLOAD,
        0,
        timeout_seconds=0.001,
    )

    assert attempt.outcome == "failed"
    assert attempt.reason == "AGENT_STREAM_FAILED_OR_TIMED_OUT"
    assert attempt.agent_to_candidate_ms is None
    assert attempt.candidate_to_final_ms is None
    assert attempt.agent_to_final_ms is None


def test_report_is_private_exclusive_and_mode_600(tmp_path: Path) -> None:
    output = tmp_path / "report.json"
    attempt = screen.Attempt.completed("medium", 0, 400.0, 800.0, 1200.0)
    report = screen.build_report(
        mode="smoke",
        git_commit="a" * 40,
        agent_core_commit="b" * 40,
        attempts=(attempt,),
    )

    screen.write_report(output, report)
    serialized = output.read_text(encoding="utf-8")
    assert report["status"] == "PASS"
    assert report["summaries"]["medium"]["materiality_pass"] is True
    assert output.stat().st_mode & 0o777 == 0o600
    assert "private" not in serialized
    assert "prompt" not in serialized
    assert "content" not in serialized
    with pytest.raises(FileExistsError):
        screen.write_report(output, report)


def test_source_validation_rejects_mismatch_dirty_and_existing_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output = tmp_path / "report.json"
    answers = iter(("b" * 40, ""))
    monkeypatch.setattr(screen, "_git", lambda *_args: next(answers))
    with pytest.raises(ValueError, match="does not match"):
        screen.validate_source(tmp_path, "a" * 40, output)

    answers = iter(("a" * 40, "dirty"))
    monkeypatch.setattr(screen, "_git", lambda *_args: next(answers))
    with pytest.raises(ValueError, match="clean source"):
        screen.validate_source(tmp_path, "a" * 40, output)

    output.touch()
    with pytest.raises(FileExistsError):
        screen.validate_source(tmp_path, "a" * 40, output)
