# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Decompose an L0 evidence directory into per-segment latency percentiles.

Reads the sanitized correlated JSONL emitted by the L0 measurement envelope
(browser.jsonl plus l0-gateway/l0-runtime/l0-agent shards), joins the
milestones of each round by ``correlation_id`` and reports p50/p95/max for
every consecutive segment of the speech-end-to-first-audio critical path.

This is a read-only diagnostic over already collected evidence. It retains no
audio, text or credentials and has no product authority. Wall-clock
``observed_at`` timestamps are used because the segments cross processes; the
sub-millisecond error of one shared machine clock is negligible against the
measured segments.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from bisect import bisect_right
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# Consecutive critical-path segments: (label, from_milestone, to_milestone).
CHAIN: tuple[tuple[str, str, str], ...] = (
    ("provider_eot -> browser_eot_receipt", "provider_eot", "browser_eot_receipt"),
    ("browser_eot_receipt -> capture_stopped", "browser_eot_receipt", "capture_stopped"),
    ("capture_stopped -> last_frame_sent", "capture_stopped", "last_frame_sent"),
    ("last_frame_sent -> last_frame_acked", "last_frame_sent", "last_frame_acked"),
    ("last_frame_acked -> uplink_closed", "last_frame_acked", "uplink_closed"),
    ("uplink_closed -> stt_final_available", "uplink_closed", "stt_final_available"),
    ("stt_final_available -> committed_submit_accepted", "stt_final_available", "committed_submit_accepted"),
    ("committed_submit_accepted -> agent_request_start", "committed_submit_accepted", "agent_request_start"),
    ("agent_request_start -> first_delta", "agent_request_start", "first_delta"),
    ("first_delta -> first_stable_speakable_sentence", "first_delta", "first_stable_speakable_sentence"),
    ("first_stable_speakable_sentence -> chat_final", "first_stable_speakable_sentence", "chat_final"),
    ("chat_final -> tts_request", "chat_final", "tts_request"),
    ("tts_request -> provider_first_audio", "tts_request", "provider_first_audio"),
    ("provider_first_audio -> downlink_ticket", "provider_first_audio", "downlink_ticket"),
    ("downlink_ticket -> browser_first_frame", "downlink_ticket", "browser_first_frame"),
    ("browser_first_frame -> webaudio_first_frame_scheduled", "browser_first_frame", "webaudio_first_frame_scheduled"),
    ("webaudio_first_frame_scheduled -> webaudio_actually_started", "webaudio_first_frame_scheduled", "webaudio_actually_started"),
)

# Cross-check anchors that overlap the chain or run in parallel with it.
ANCHORS: tuple[tuple[str, str, str], ...] = (
    ("provider_eot -> stt_final_available", "provider_eot", "stt_final_available"),
    ("provider_eot -> committed_submit_accepted", "provider_eot", "committed_submit_accepted"),
    ("agent_request_start -> chat_final", "agent_request_start", "chat_final"),
    ("chat_final -> successor_capture_ready", "chat_final", "successor_capture_ready"),
    ("chat_final -> webaudio_actually_started", "chat_final", "webaudio_actually_started"),
    ("provider_eot -> webaudio_actually_started", "provider_eot", "webaudio_actually_started"),
    ("provider_eot -> playout_completed", "provider_eot", "playout_completed"),
)


def _parse_when(value: str) -> float:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000.0


def _load_events(evidence_dir: Path) -> list[tuple[float, str]]:
    """All (wall-clock ms, milestone) observations across every shard."""
    events: list[tuple[float, str]] = []
    shards = sorted(
        [evidence_dir / "browser.jsonl"]
        + list(evidence_dir.glob("l0-gateway-*.jsonl"))
        + list(evidence_dir.glob("l0-runtime-*.jsonl"))
        + list(evidence_dir.glob("l0-agent-*.jsonl"))
    )
    for shard in shards:
        if not shard.is_file():
            continue
        with shard.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                milestone = record.get("milestone")
                observation = record.get("observation") or {}
                observed_at = observation.get("observed_at")
                if not milestone or not observed_at:
                    continue
                events.append((_parse_when(observed_at), milestone))
    events.sort(key=lambda item: item[0])
    return events


def _load_rounds(evidence_dir: Path) -> dict[str, dict[str, float]]:
    """Bucket milestones into rounds by temporal position.

    The uplink and downlink legs of one round carry different correlation ids,
    so a correlation join fragments the chain. The L0 ordinary-Chrome batch
    runs rounds strictly one at a time, which makes ``provider_eot`` an exact
    round boundary: every observation between one ``provider_eot`` and the
    next belongs to the earlier round. Milestones observed before the first
    ``provider_eot`` (the warm-up preamble) are dropped, and only the first
    occurrence of a milestone inside one round is kept.
    """
    events = _load_events(evidence_dir)
    # Capture settlement (last frame sent/ACKed, capture stop) begins a few
    # tens of milliseconds BEFORE the provider_eot observation, so the round
    # boundary sits 500 ms ahead of each provider_eot rather than exactly on
    # it; otherwise those milestones land in the previous round's bucket.
    boundaries = [when - 500.0 for when, milestone in events if milestone == "provider_eot"]
    rounds: dict[str, dict[str, float]] = defaultdict(dict)
    for when, milestone in events:
        round_index = bisect_right(boundaries, when) - 1
        if round_index < 0:
            continue
        timeline = rounds[f"round-{round_index:03d}"]
        if milestone not in timeline:
            timeline[milestone] = when
    return rounds


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return math.nan
    rank = fraction * (len(ordered) - 1)
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return ordered[low]
    return ordered[low] + (ordered[high] - ordered[low]) * (rank - low)


def _report(
    title: str,
    spans: tuple[tuple[str, str, str], ...],
    rounds: list[dict[str, float]],
) -> list[dict[str, object]]:
    lines: list[dict[str, object]] = []
    print(f"\n## {title}")
    print(f"| segment | n | p50 ms | p95 ms | max ms |")
    print(f"|---|---:|---:|---:|---:|")
    for label, start, end in spans:
        durations = [
            timeline[end] - timeline[start]
            for timeline in rounds
            if start in timeline and end in timeline
        ]
        if not durations:
            print(f"| {label} | 0 | - | - | - |")
            lines.append({"segment": label, "n": 0})
            continue
        p50 = _percentile(durations, 0.50)
        p95 = _percentile(durations, 0.95)
        peak = max(durations)
        print(
            f"| {label} | {len(durations)} | {p50:.1f} | {p95:.1f} | {peak:.1f} |"
        )
        lines.append(
            {
                "segment": label,
                "n": len(durations),
                "p50_ms": round(p50, 1),
                "p95_ms": round(p95, 1),
                "max_ms": round(peak, 1),
            }
        )
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--evidence-directory",
        required=True,
        type=Path,
        help="L0 evidence directory containing browser.jsonl and l0-*.jsonl shards",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=None,
        help="Optional path for the machine-readable summary",
    )
    args = parser.parse_args()
    evidence_dir = args.evidence_directory
    if not evidence_dir.is_dir():
        print(f"evidence directory not found: {evidence_dir}", file=sys.stderr)
        return 2

    rounds = _load_rounds(evidence_dir)
    complete = [
        timeline
        for timeline in rounds.values()
        if "provider_eot" in timeline and "webaudio_actually_started" in timeline
    ]
    first_audio = [t for t in complete if "barge_in" not in t]
    barge = [t for t in complete if "barge_in" in t]
    print(f"# L0 segment breakdown: {evidence_dir.name}")
    print(
        f"rounds with full first-audio chain: {len(complete)} "
        f"(first_audio={len(first_audio)}, barge_in={len(barge)})"
    )

    summary = {
        "evidence_directory": evidence_dir.name,
        "rounds_complete": len(complete),
        "rounds_first_audio": len(first_audio),
        "rounds_barge_in": len(barge),
        "chain_all_rounds": _report(
            "Consecutive critical-path segments (all complete rounds)", CHAIN, complete
        ),
        "anchors_all_rounds": _report(
            "Cross-check anchors (all complete rounds)", ANCHORS, complete
        ),
    }
    if first_audio and barge:
        summary["chain_first_audio_only"] = _report(
            "Consecutive critical-path segments (first-audio rounds only)",
            CHAIN,
            first_audio,
        )
    if args.json_output is not None:
        args.json_output.write_text(
            json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"\nJSON summary written: {args.json_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
