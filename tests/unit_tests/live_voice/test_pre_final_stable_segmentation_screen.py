from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from jiuwenswarm.common.schema.agent import AgentResponseChunk
from scripts.live_voice import pre_final_stable_segmentation_screen as screen


class _Facade:
    def __init__(
        self,
        events: tuple[tuple[str, str], ...],
        *,
        block: bool = False,
        wrong_request: bool = False,
    ) -> None:
        self.events = events
        self.block = block
        self.wrong_request = wrong_request
        self.started = asyncio.Event()
        self.closed = asyncio.Event()

    def supports_formal_live_voice(self) -> bool:
        return True

    async def process_formal_live_voice_stream(self, execution):
        if self.block:
            self.started.set()
            try:
                await asyncio.Event().wait()
            finally:
                self.closed.set()
        for index, (event_type, content) in enumerate(self.events):
            yield AgentResponseChunk(
                request_id=(
                    "foreign-request"
                    if self.wrong_request and index == 0
                    else execution.request_id
                ),
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
async def test_post_candidate_long_delta_tail_does_not_exhaust_policy_events() -> None:
    tail = tuple(("chat.delta", "x") for _ in range(300))
    final = f"Paris is the capital. More follows.{''.join('x' for _ in range(300))}"
    attempt = await screen.measure_attempt(
        _Facade(
            (
                ("chat.delta", "Paris is the capital. "),
                ("chat.delta", "More follows."),
                *tail,
                ("chat.final", final),
            )
        ),
        WORKLOAD,
        0,
        monotonic=_Clock((10.0, 10.4, 10.9)),
    )

    assert attempt.outcome == "completed"
    assert attempt.reconciliation_disposition == "exact_prefix"
    assert attempt.candidate_to_final_ms == pytest.approx(500.0)


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
    assert attempt.reason == "AGENT_STREAM_TIMED_OUT"
    assert attempt.terminal_outcome == "cancelled"
    assert attempt.agent_to_candidate_ms is None
    assert attempt.candidate_to_final_ms is None
    assert attempt.agent_to_final_ms is None


@pytest.mark.asyncio
async def test_external_process_cancellation_is_not_swallowed() -> None:
    facade = _Facade((), block=True)
    task = asyncio.create_task(
        screen.measure_attempt(facade, WORKLOAD, 0, timeout_seconds=10)
    )
    await asyncio.wait_for(facade.started.wait(), timeout=1)

    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.wait_for(facade.closed.wait(), timeout=1)


@pytest.mark.asyncio
async def test_foreign_chunk_identity_fails_closed_at_harness_boundary() -> None:
    attempt = await screen.measure_attempt(
        _Facade(
            (
                ("chat.delta", "Paris is the capital. "),
                ("chat.delta", "More follows."),
                ("chat.final", "Paris is the capital. More follows."),
            ),
            wrong_request=True,
        ),
        WORKLOAD,
        0,
        monotonic=_Clock((10.0,)),
    )

    assert attempt.outcome == "failed"
    assert attempt.terminal_outcome == "failed"
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
    assert report["decision"] == "READY_FOR_TTS_SCREEN"
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
        screen.validate_source(tmp_path, "a" * 40, "c" * 40, output)

    answers = iter(("a" * 40, "dirty"))
    monkeypatch.setattr(screen, "_git", lambda *_args: next(answers))
    with pytest.raises(ValueError, match="clean source"):
        screen.validate_source(tmp_path, "a" * 40, "c" * 40, output)

    answers = iter(("a" * 40, ""))
    monkeypatch.setattr(screen, "_git", lambda *_args: next(answers))
    monkeypatch.setattr(screen, "_installed_agent_core_commit", lambda: "b" * 40)
    with pytest.raises(ValueError, match="Agent-Core commit"):
        screen.validate_source(tmp_path, "a" * 40, "c" * 40, output)

    output.touch()
    with pytest.raises(FileExistsError):
        screen.validate_source(tmp_path, "a" * 40, "c" * 40, output)


def test_run_report_requires_the_exact_medium_long_slot_population() -> None:
    repeated_medium = tuple(
        screen.Attempt.completed("medium", index, 400.0, 800.0, 1200.0)
        for index in range(10)
    )

    report = screen.build_report(
        mode="run",
        git_commit="a" * 40,
        agent_core_commit="b" * 40,
        attempts=repeated_medium,
    )

    assert report["status"] == "FAIL"
    assert report["decision"] == "INTEGRITY_FAILED"


@pytest.mark.asyncio
async def test_population_retains_every_slot_after_an_attempt_failure() -> None:
    seen: list[tuple[str, int]] = []

    async def fake_measure(_facade, workload, attempt_index):
        seen.append((workload.workload_id, attempt_index))
        if workload.workload_id == "medium" and attempt_index == 0:
            return screen.Attempt.failed(
                workload.workload_id, attempt_index, "CONTROLLED_FAILURE"
            )
        return screen.Attempt.completed(
            workload.workload_id, attempt_index, 400.0, 800.0, 1200.0
        )

    attempts = await screen.collect_attempts(
        object(), screen.WORKLOADS, 5, measure=fake_measure
    )

    assert seen == [
        *(("medium", index) for index in range(5)),
        *(("long", index) for index in range(5)),
    ]
    assert len(attempts) == 10
    assert attempts[0].outcome == "failed"
    assert all(attempt.outcome == "completed" for attempt in attempts[1:])


@pytest.mark.parametrize(
    "process_control",
    (asyncio.CancelledError(), KeyboardInterrupt(), SystemExit(2)),
)
def test_cli_does_not_convert_process_control(
    monkeypatch: pytest.MonkeyPatch,
    process_control: BaseException,
) -> None:
    args = SimpleNamespace(
        command="smoke",
        project_dir="/project",
        output="/output",
        git_commit="a" * 40,
        agent_core_commit="b" * 40,
    )

    class _Parser:
        @staticmethod
        def parse_args():
            return args

    async def raise_process_control(_args):
        raise process_control

    monkeypatch.setattr(screen, "_parser", lambda: _Parser())
    monkeypatch.setattr(screen, "_run", raise_process_control)

    with pytest.raises(type(process_control)):
        screen.main()
