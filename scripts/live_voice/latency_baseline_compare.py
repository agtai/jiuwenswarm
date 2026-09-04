# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Compare two latency_baseline_driver runs segment by segment.

Reads each run's rounds.jsonl (driver-side timings) and split.final.json
(server-side model-call attribution, if present) and prints per-scenario
before/after tables with mean, p50 and p99 plus the absolute p50 delta.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path

SEGMENTS = [
    ("speech_end->eot(VAD)", "闭嘴→EOT"),
    ("uplink_settled->recognized(STT final)", "STT final"),
    ("submit_rpc_roundtrip(semantic resolve inside)", "submit RPC(语义在内)"),
    ("submitted->first_delta", "submit→首 delta"),
    ("submitted->final_notification", "submit→chat.final"),
    ("final->synthesis_returned(TTS first chunk)", "TTS 首块"),
    ("TOTAL speech_end->downlink_first_frame", "TOTAL 说完→下行首帧"),
]
SPLIT_KEYS = [
    ("semantic_ms(until main start)", "语义模型调用"),
    ("main_model_ms(until next call)", "主模型(到下一次调用)"),
    ("main_model_ms(until final_sent)", "主模型(到 final)"),
    ("post_main_ms(until final_sent)", "主模型后→final(修订等)"),
]


def _stats(values: list[float]) -> dict[str, float]:
    if not values:
        return {"n": 0, "mean": math.nan, "p50": math.nan, "p99": math.nan}
    ordered = sorted(values)
    n = len(ordered)

    def pct(fraction: float) -> float:
        if n == 1:
            return ordered[0]
        rank = fraction * (n - 1)
        low, high = int(rank), min(int(rank) + 1, n - 1)
        return ordered[low] + (ordered[high] - ordered[low]) * (rank - low)

    return {"n": n, "mean": statistics.fmean(ordered), "p50": pct(0.5), "p99": pct(0.99)}


def load_run(directory: Path) -> tuple[dict[str, dict[str, dict]], dict[str, dict], dict[str, int]]:
    rows = [json.loads(line) for line in (directory / "rounds.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    order = ["short", "medium", "long", "tool", "task", "clarify"]
    scenarios = sorted({r["scenario"] for r in rows}, key=lambda name: (order.index(name) if name in order else len(order), name))
    segments: dict[str, dict[str, dict]] = {}
    failures: dict[str, int] = {}
    for scenario in scenarios:
        ok = [r for r in rows if r["scenario"] == scenario and not r["failures"]]
        failures[scenario] = sum(1 for r in rows if r["scenario"] == scenario and r["failures"])
        segments[scenario] = {key: _stats([r["segments"][key] for r in ok if r["segments"].get(key) is not None]) for key, _ in SEGMENTS}
        segments[scenario]["answer_chars"] = _stats([r["answer_chars"] for r in ok])
    split_path = directory / "split.final.json"
    split: dict[str, dict] = {}
    if split_path.is_file():
        split = json.loads(split_path.read_text(encoding="utf-8")).get("by_scenario", {})
    return segments, split, failures


def _fmt(value: float) -> str:
    return "—" if value is None or (isinstance(value, float) and math.isnan(value)) else f"{value:,.0f}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", required=True, type=Path)
    parser.add_argument("--after", required=True, type=Path)
    parser.add_argument("--markdown-output", type=Path, default=None)
    args = parser.parse_args()
    before, before_split, before_fail = load_run(args.before)
    after, after_split, after_fail = load_run(args.after)
    lines: list[str] = []
    lines.append(f"before: {args.before.name}    after: {args.after.name}\n")
    lines.append("## 总用时 TOTAL 说完→下行首帧（ms）\n")
    lines.append("| 档 | before mean | before p50 | before p99 | after mean | after p50 | after p99 | Δp50 | 成功/失败(after) |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---|")
    total_key = "TOTAL speech_end->downlink_first_frame"
    for scenario in before:
        b = before[scenario][total_key]
        a = after.get(scenario, {}).get(total_key, _stats([]))
        delta = a["p50"] - b["p50"] if a["n"] and b["n"] else math.nan
        lines.append(f"| {scenario} | {_fmt(b['mean'])} | {_fmt(b['p50'])} | {_fmt(b['p99'])} | {_fmt(a['mean'])} | {_fmt(a['p50'])} | {_fmt(a['p99'])} | {_fmt(delta)} | {a['n']}/{after_fail.get(scenario, 0)} |")
    lines.append("")
    for scenario in before:
        lines.append(f"## {scenario}（p50 ms，before → after，Δ）— 答案字数 {_fmt(before[scenario]['answer_chars']['mean'])} → {_fmt(after.get(scenario, {}).get('answer_chars', _stats([]))['mean'])}\n")
        lines.append("| 段 | before p50 | after p50 | Δ | before p99 | after p99 |")
        lines.append("|---|---:|---:|---:|---:|---:|")
        for key, label in SEGMENTS:
            b = before[scenario][key]
            a = after.get(scenario, {}).get(key, _stats([]))
            delta = a["p50"] - b["p50"] if a["n"] and b["n"] else math.nan
            lines.append(f"| {label} | {_fmt(b['p50'])} | {_fmt(a['p50'])} | {_fmt(delta)} | {_fmt(b['p99'])} | {_fmt(a['p99'])} |")
        for key, label in SPLIT_KEYS:
            b = before_split.get(scenario, {}).get(key)
            a = after_split.get(scenario, {}).get(key)
            if not b and not a:
                continue
            bp = b["p50"] if b else math.nan
            ap = a["p50"] if a else math.nan
            delta = ap - bp if b and a else math.nan
            lines.append(f"| {label}（日志切分） | {_fmt(bp)} | {_fmt(ap)} | {_fmt(delta)} | {_fmt(b['p99'] if b else math.nan)} | {_fmt(a['p99'] if a else math.nan)} |")
        b_to = before_split.get(scenario, {}).get("revision_timeouts")
        a_to = after_split.get(scenario, {}).get("revision_timeouts")
        b_calls = before_split.get(scenario, {}).get("llm_calls_per_round", {}).get("p50") if before_split else None
        a_calls = after_split.get(scenario, {}).get("llm_calls_per_round", {}).get("p50") if after_split else None
        lines.append(f"\n修订超时次数 {b_to} → {a_to}；每轮模型调用数 p50 {b_calls} → {a_calls}\n")
    text = "\n".join(lines)
    print(text)
    if args.markdown_output is not None:
        args.markdown_output.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
