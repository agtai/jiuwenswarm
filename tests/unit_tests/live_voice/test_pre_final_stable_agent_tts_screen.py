from __future__ import annotations

import json
from pathlib import Path

import pytest

from jiuwenswarm.common.schema.agent import AgentResponseChunk
from scripts.live_voice import pre_final_stable_agent_tts_screen as screen


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


class _Tts:
    def __init__(self, delay_ms: float) -> None:
        self.delay_ms = delay_ms
        self.requests: list[bytes] = []

    async def measure_first_pcm(
        self, *, response_ref, unit_id, text_utf8, dispatched_at
    ):
        self.requests.append(text_utf8)
        return screen.TtsTiming(0.0, self.delay_ms)


EVENTS = (
    ("chat.delta", "Paris is the capital. "),
    ("chat.delta", "It is in France."),
    ("chat.final", "Paris is the capital. It is in France."),
)
WORKLOAD = screen.Workload("medium", "private prompt")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("arm", "expected_first_pcm_ms"),
    (("A1", 2200.0), ("B", 1200.0), ("A2", 2200.0)),
)
async def test_arm_starts_one_tts_at_candidate_or_final(
    arm: str,
    expected_first_pcm_ms: float,
) -> None:
    tts = _Tts(800.0)
    attempt = await screen.measure_attempt(
        _Facade(EVENTS),
        WORKLOAD,
        arm,
        0,
        tts=tts,
        monotonic=_Clock((10.0, 10.4, 11.4)),
    )

    assert attempt.outcome == "completed"
    assert attempt.agent_to_first_pcm_ms == pytest.approx(expected_first_pcm_ms)
    assert attempt.candidate_to_final_ms == pytest.approx(1000.0)
    assert attempt.tts_request_to_first_pcm_ms == pytest.approx(800.0)
    assert attempt.tts_dispatch_to_request_ms == pytest.approx(0.0)
    assert attempt.prefix_exact is True
    assert attempt.authorized_agent_calls == 1
    assert attempt.authorized_tts_calls == 1
    assert len(tts.requests) == 1
    assert "private" not in json.dumps(attempt.to_dict())


def test_reducer_accepts_material_a_b_a_gain_with_stable_controls() -> None:
    attempts = []
    for arm, first_pcm in (("A1", 3000.0), ("B", 1500.0), ("A2", 3100.0)):
        for workload in ("medium", "long"):
            for index in range(5):
                attempts.append(
                    screen.Attempt.completed(
                        arm=arm,
                        workload_id=workload,
                        attempt_index=index,
                        agent_to_candidate_ms=700.0,
                        candidate_to_final_ms=1600.0,
                        agent_to_final_ms=2300.0,
                        tts_dispatch_to_request_ms=0.0,
                        tts_request_to_first_pcm_ms=700.0,
                        agent_to_first_pcm_ms=first_pcm,
                    )
                )

    report = screen.build_report(
        mode="run",
        git_commit="a" * 40,
        agent_core_commit="b" * 40,
        attempts=tuple(attempts),
    )

    assert report["status"] == "PASS"
    assert report["decision"] == "CANDIDATE_ACCEPTED"
    assert report["summaries"]["medium"]["gain_vs_interpolated_control_ms"] == pytest.approx(1550.0)


@pytest.mark.asyncio
async def test_prefix_rewrite_after_candidate_tts_fails_without_timings() -> None:
    tts = _Tts(800.0)
    attempt = await screen.measure_attempt(
        _Facade(
            (
                ("chat.delta", "Paris is the capital. "),
                ("chat.delta", "More follows."),
                ("chat.final", "Lyon is the capital. More follows."),
            )
        ),
        WORKLOAD,
        "B",
        0,
        tts=tts,
        monotonic=_Clock((10.0, 10.4, 11.4)),
    )

    assert attempt.outcome == "failed"
    assert attempt.reason == "PREFIX_RECONCILIATION_FAILED"
    assert attempt.agent_to_first_pcm_ms is None
    assert attempt.tts_request_to_first_pcm_ms is None
    assert attempt.authorized_tts_calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("arm", "expected_tts_calls", "expected_reason"),
    (
        ("A1", 1, "AGENT_TIMING_INCOMPLETE"),
        ("B", 0, "TTS_REQUEST_MISSING"),
        ("A2", 1, "AGENT_TIMING_INCOMPLETE"),
    ),
)
async def test_no_candidate_preserves_arm_specific_tts_budget(
    arm: str,
    expected_tts_calls: int,
    expected_reason: str,
) -> None:
    tts = _Tts(800.0)
    attempt = await screen.measure_attempt(
        _Facade(
            (
                ("chat.delta", "Paris is the capital."),
                ("chat.final", "Paris is the capital."),
            )
        ),
        WORKLOAD,
        arm,
        0,
        tts=tts,
        monotonic=_Clock((10.0, 11.0)),
    )

    assert attempt.outcome == "failed"
    assert attempt.reason == expected_reason
    assert attempt.authorized_tts_calls == expected_tts_calls
    assert len(tts.requests) == expected_tts_calls
    assert attempt.agent_to_first_pcm_ms is None


@pytest.mark.asyncio
async def test_pilot_retains_all_six_slots_after_failure() -> None:
    seen: list[tuple[str, str, int]] = []

    async def fake_measure(_facade, workload, arm, index, *, tts):
        seen.append((arm, workload.workload_id, index))
        if len(seen) == 1:
            return screen.Attempt.failed(
                arm=arm,
                workload_id=workload.workload_id,
                attempt_index=index,
                reason="CONTROLLED_FAILURE",
            )
        return screen.Attempt.completed(
            arm=arm,
            workload_id=workload.workload_id,
            attempt_index=index,
            agent_to_candidate_ms=700.0,
            candidate_to_final_ms=1600.0,
            agent_to_final_ms=2300.0,
            tts_dispatch_to_request_ms=0.0,
            tts_request_to_first_pcm_ms=700.0,
            agent_to_first_pcm_ms=3000.0 if arm != "B" else 1500.0,
        )

    attempts = await screen.collect_attempts(
        object(), mode="pilot", tts_factory=lambda: object(), measure=fake_measure
    )

    assert len(attempts) == 6
    assert seen == [
        (arm, workload, 0)
        for arm in screen.ARMS
        for workload in ("medium", "long")
    ]


def test_report_is_private_exclusive_and_mode_600(tmp_path: Path) -> None:
    attempts = []
    for arm, first_pcm in (("A1", 3000.0), ("B", 1500.0), ("A2", 3100.0)):
        for workload in ("medium", "long"):
            attempts.append(
                screen.Attempt.completed(
                    arm=arm,
                    workload_id=workload,
                    attempt_index=0,
                    agent_to_candidate_ms=700.0,
                    candidate_to_final_ms=1600.0,
                    agent_to_final_ms=2300.0,
                    tts_dispatch_to_request_ms=0.0,
                    tts_request_to_first_pcm_ms=700.0,
                    agent_to_first_pcm_ms=first_pcm,
                )
            )
    report = screen.build_report(
        mode="pilot",
        git_commit="a" * 40,
        agent_core_commit="b" * 40,
        attempts=tuple(attempts),
    )
    output = tmp_path / "result.json"

    screen.prefix_screen.write_report(output, report)
    serialized = output.read_text(encoding="utf-8")

    assert report["status"] == "PASS"
    assert report["decision"] == "PILOT_PASS"
    assert report["summaries"]["medium"]["arms"]["A1"]["agent_to_candidate_p50_ms"] == pytest.approx(700.0)
    assert report["summaries"]["long"]["arms"]["A2"]["candidate_to_final_p95_nearest_rank_ms"] == pytest.approx(1600.0)
    assert output.stat().st_mode & 0o777 == 0o600
    assert "private" not in serialized
    assert "prompt" not in serialized
    assert "content" not in serialized
    with pytest.raises(FileExistsError):
        screen.prefix_screen.write_report(output, report)
