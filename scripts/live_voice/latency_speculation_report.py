# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Summarize speculative dialogue candidates from a swarm log.

Reads the content-free ``live_voice_speculation_*`` lines the Runtime and
Registry write and reports how many candidates started, were attached or
were discarded (by reason), how far ahead of the admitted round the first
chunk was, and a best-effort token cost of discarded candidates taken from
the ``llm_call_end`` usage that falls inside each candidate's window.
Nothing here reads message content.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

_LINE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}) .*live_voice_speculation_(\w+) (.*)$")
_KV = re.compile(r"(\w+)=([^\s]+)")
_USAGE = re.compile(r"(?:completion_tokens|output_tokens)=(\d+)")


def _stamp(text: str) -> float:
    return datetime.strptime(text, "%Y-%m-%d %H:%M:%S.%f").timestamp()


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = fraction * (len(ordered) - 1)
    low, high = int(rank), min(int(rank) + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (rank - low)


def summarize(log: Path) -> dict:
    events: list[tuple[float, str, dict[str, str]]] = []
    llm_ends: list[tuple[float, int | None]] = []
    for line in log.open(encoding="utf-8", errors="ignore"):
        match = _LINE.match(line)
        if match:
            events.append((_stamp(match.group(1)), match.group(2), dict(_KV.findall(match.group(3)))))
            continue
        if "llm_call_end" in line and "| {" in line:
            try:
                payload = json.loads(line.split("| ", 4)[-1])
            except (ValueError, IndexError):
                continue
            stamp = datetime.fromisoformat(payload["timestamp"]).timestamp()
            usage = _USAGE.search(json.dumps(payload.get("metadata")) if payload.get("metadata") else "")
            llm_ends.append((stamp, int(usage.group(1)) if usage else None))
    started: dict[str, float] = {}
    attached = 0
    leads: list[float] = []
    discarded = Counter()
    discarded_elapsed: list[float] = []
    discarded_tokens: list[int] = []
    unknown_cost = 0
    skipped = Counter()
    for stamp, kind, fields in events:
        request = fields.get("request_id", "?")
        if kind == "started":
            started[request] = stamp
        elif kind == "attached":
            attached += 1
            lead = fields.get("first_chunk_lead_ms")
            if lead not in (None, "n/a"):
                leads.append(float(lead))
        elif kind == "discarded":
            reason = fields.get("reason", "?")
            discarded[reason] += 1
            elapsed = float(fields.get("elapsed_ms", "0"))
            discarded_elapsed.append(elapsed)
            begin = started.get(request, stamp - elapsed / 1000.0)
            tokens = [usage for end, usage in llm_ends if begin <= end <= stamp + 0.5]
            known = [t for t in tokens if t is not None]
            if known:
                discarded_tokens.append(sum(known))
            else:
                unknown_cost += 1
        elif kind == "skipped":
            skipped[fields.get("reason", "?")] += 1
    return {
        "started": len(started),
        "attached": attached,
        "first_chunk_lead_ms_p50": _percentile(leads, 0.5),
        "first_chunk_lead_ms_p95": _percentile(leads, 0.95),
        "discarded": dict(discarded),
        "discarded_elapsed_ms_p50": _percentile(discarded_elapsed, 0.5),
        "discarded_completion_tokens_total": sum(discarded_tokens),
        "discarded_with_unknown_cost": unknown_cost,
        "skipped": dict(skipped),
        "llm_call_ends_seen": len(llm_ends),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", required=True, type=Path, help="swarm-*.log of the measured deployment")
    parser.add_argument("--json-output", type=Path, default=None)
    args = parser.parse_args()
    summary = summarize(args.log)
    text = json.dumps(summary, ensure_ascii=False, indent=2)
    print(text)
    if args.json_output is not None:
        args.json_output.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
