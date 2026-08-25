from __future__ import annotations

import json
from pathlib import Path

import pytest

from jiuwenswarm.common.schema.agent import AgentResponseChunk
from scripts.live_voice import agent_first_delta_benchmark as runner


class _Facade:
    def __init__(self, events: tuple[tuple[str, str], ...]) -> None:
        self.events = events

    def supports_formal_live_voice(self) -> bool:
        return True

    async def process_formal_live_voice_stream(self, execution):
        for event_type, content in self.events:
            yield AgentResponseChunk(
                request_id=execution.request_id,
                channel_id=execution.channel_id,
                payload={"event_type": event_type, "content": content},
                is_complete=event_type == "chat.final",
            )


class _Clock:
    def __init__(self, values: tuple[float, ...]) -> None:
        self.values = iter(values)

    def __call__(self) -> float:
        return next(self.values)


@pytest.mark.asyncio
async def test_attempt_measures_first_visible_delta_and_final_without_content() -> None:
    attempt = await runner.measure_attempt(
        _Facade(
            (
                ("chat.reasoning", "private reasoning"),
                ("chat.delta", "  "),
                ("chat.delta", "private first delta"),
                ("chat.delta", "private second delta"),
                ("chat.final", "private final"),
            )
        ),
        runner.Workload("short", "private prompt"),
        0,
        monotonic=_Clock((10.0, 10.4, 10.7)),
    )

    assert attempt.outcome == "completed"
    assert attempt.agent_to_first_delta_ms == pytest.approx(400.0)
    assert attempt.first_delta_to_final_ms == pytest.approx(300.0)
    assert attempt.agent_to_final_ms == pytest.approx(700.0)
    assert attempt.delta_count == 2
    assert "private" not in json.dumps(attempt.to_dict())


@pytest.mark.asyncio
async def test_attempt_failure_before_delta_has_no_attractive_timing() -> None:
    attempt = await runner.measure_attempt(
        _Facade((("chat.error", "private failure"),)),
        runner.Workload("short", "private prompt"),
        0,
        monotonic=_Clock((10.0,)),
    )

    assert attempt.outcome == "failed"
    assert attempt.agent_to_first_delta_ms is None
    assert attempt.first_delta_to_final_ms is None
    assert attempt.agent_to_final_ms is None
    assert attempt.forbidden_effects == runner.ZERO_FORBIDDEN_EFFECTS


def test_report_is_private_exclusive_and_mode_600(tmp_path: Path) -> None:
    output = tmp_path / "report.json"
    attempt = runner.Attempt.completed("short", 0, 100.0, 20.0, 120.0, 1)
    report = runner.build_report(
        mode="smoke",
        git_commit="a" * 40,
        agent_core_commit="b" * 40,
        attempts=(attempt,),
    )

    runner.write_report(output, report)
    serialized = output.read_text(encoding="utf-8")
    assert output.stat().st_mode & 0o777 == 0o600
    assert "prompt" not in serialized
    assert "content" not in serialized
    with pytest.raises(FileExistsError):
        runner.write_report(output, report)
