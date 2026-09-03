# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Attribute server-side model calls to each driver round from runtime logs.

The driver only sees the route from outside. To split the Agent segment into
Live Voice's own semantic-resolution call, the main Agent model call and the
spoken second revision, this script joins each round's submit/final window
(from ``rounds.jsonl``) with the LLM call log (``llm.log``:
``llm_call_start`` / ``llm_call_end`` / ``llm_call_error``) and the Agent server
log (``[E2A][in] ... unified.submit`` and ``chunk sent ... event_type=chat.final``).

Model calls are classified by order and streaming flag within the window:
the first non-stream call after submit is the semantic resolution, the first
streaming call is the main Agent request, later non-stream calls before the
final chunk are revisions/authorization checks. Content is never read.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path

LOCAL_TZ = timezone(timedelta(hours=2))
E2A_IN = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}) .*\[E2A\]\[in\] request_id=(\S+) .*method=live_voice\.composition\.unified\.submit")
CHUNK_FINAL = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}) .*chunk sent: request_id=(\S+) .*event_type=chat\.final")
SPOKEN_FAIL = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}) .*live_voice_spoken_revision_failed")


def _local_ms(stamp: str) -> float:
    return datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S.%f").replace(tzinfo=LOCAL_TZ).timestamp() * 1000.0


def _iso_ms(stamp: str) -> float:
    return datetime.fromisoformat(stamp).timestamp() * 1000.0


def load_llm_calls(path: Path) -> list[dict]:
    calls: list[dict] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if "| INFO |" not in line and "| ERROR |" not in line and "| WARNING |" not in line:
                continue
            brace = line.find("{")
            if brace < 0:
                continue
            try:
                record = json.loads(line[brace:])
            except json.JSONDecodeError:
                continue
            event = record.get("event_type")
            if event not in {"llm_call_start", "llm_call_end", "llm_call_error"}:
                continue
            metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
            calls.append({"event": event, "ms": _iso_ms(record["timestamp"]), "stream": bool(record.get("is_stream")), "model": record.get("model_name"), "client": str(metadata.get("client_name") or ""), "meta_keys": sorted(metadata.keys())})
    calls.sort(key=lambda c: c["ms"])
    return calls


def pair_calls(calls: list[dict]) -> list[dict]:
    """Pair each start with the next end/error of the same stream flag."""
    paired: list[dict] = []
    open_calls: list[dict] = []
    for call in calls:
        if call["event"] == "llm_call_start":
            open_calls.append(call)
            continue
        for index, start in enumerate(open_calls):
            if start["stream"] == call["stream"] and (not call["client"] or call["client"] == start["client"]):
                paired.append({"start": start["ms"], "end": call["ms"], "stream": start["stream"], "ok": call["event"] == "llm_call_end", "model": start["model"], "client": start["client"], "meta_keys": start["meta_keys"]})
                del open_calls[index]
                break
    for start in open_calls:
        paired.append({"start": start["ms"], "end": None, "stream": start["stream"], "ok": None, "model": start["model"], "client": start["client"], "meta_keys": start["meta_keys"]})
    paired.sort(key=lambda p: p["start"])
    return paired


def load_agent_anchors(path: Path) -> dict[str, list[float]]:
    anchors: dict[str, list[float]] = {"submit_in": [], "chat_final_sent": [], "spoken_revision_failed": []}
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            m = E2A_IN.match(line)
            if m:
                anchors["submit_in"].append(_local_ms(m.group(1)))
                continue
            m = CHUNK_FINAL.match(line)
            if m:
                anchors["chat_final_sent"].append(_local_ms(m.group(1)))
                continue
            m = SPOKEN_FAIL.match(line)
            if m:
                anchors["spoken_revision_failed"].append(_local_ms(m.group(1)))
    return anchors


def _in(values: list[float], lo: float, hi: float) -> list[float]:
    return [v for v in values if lo <= v <= hi]


def attribute(round_record: dict, calls: list[dict], anchors: dict[str, list[float]]) -> dict:
    t = round_record.get("t") or {}
    sent_key = "submit_sent" if "submit_sent" in t else "submitted"
    if sent_key not in t or "final_notification" not in t:
        return {"skipped": "round has no submit/final window"}
    lo, hi = t[sent_key] - 500.0, t["final_notification"] + 500.0
    window = [c for c in calls if lo <= c["start"] <= hi]
    submit_in = _in(anchors["submit_in"], lo, hi)
    final_sent = _in(anchors["chat_final_sent"], lo, hi)
    revision_failed = _in(anchors["spoken_revision_failed"], lo, hi)
    out: dict = {"llm_calls": len(window), "llm_calls_stream": sum(1 for c in window if c["stream"]), "llm_calls_nonstream": sum(1 for c in window if not c["stream"]), "llm_calls_failed": sum(1 for c in window if c["ok"] is False), "spoken_revision_failed": len(revision_failed), "calls": [[c["client"], "stream" if c["stream"] else "unary", round(c["end"] - c["start"], 1) if c["end"] is not None else None, round(c["start"] - t[sent_key], 1)] for c in window]}
    submit_ms = submit_in[0] if submit_in else t[sent_key]
    final_ms = final_sent[-1] if final_sent else t["final_notification"]
    # llm.log reliably records llm_call_start but rarely llm_call_end, so every
    # duration below is derived from consecutive START offsets: the calls on
    # this route are serial, so a call lasts until the next call starts (or
    # until the final chunk is sent for the last one).
    ordered = sorted((c for c in window if c["start"] >= submit_ms - 200), key=lambda c: c["start"])
    starts = [c["start"] for c in ordered] + [final_ms]
    unary_before_main: list[dict] = []
    main_index = None
    for index, c in enumerate(ordered):
        if c["stream"]:
            main_index = index
            break
        unary_before_main.append(c)
    if unary_before_main:
        out["submit->semantic_start"] = round(unary_before_main[0]["start"] - submit_ms, 1)
        out["semantic_calls_before_main"] = len(unary_before_main)
        out["semantic_ms(until main start)"] = round(starts[len(unary_before_main)] - unary_before_main[0]["start"], 1)
    if main_index is not None:
        main = ordered[main_index]
        out["main_model_start_after_submit"] = round(main["start"] - submit_ms, 1)
        after = ordered[main_index + 1 :]
        out["post_main_calls"] = [["stream" if c["stream"] else "unary", round(c["start"] - main["start"], 1)] for c in after]
        if after:
            out["main_model_ms(until next call)"] = round(after[0]["start"] - main["start"], 1)
            out["post_main_ms(until final_sent)"] = round(final_ms - after[0]["start"], 1)
        else:
            out["main_model_ms(until final_sent)"] = round(final_ms - main["start"], 1)
    out["submit->final_sent(server)"] = round(final_ms - submit_ms, 1)
    out["meta_keys_sample"] = window[0]["meta_keys"] if window else []
    return out


def _stats(values: list[float]) -> dict:
    values = sorted(values)
    n = len(values)

    def pct(f: float) -> float:
        if n == 1:
            return values[0]
        rank = f * (n - 1)
        lo, hi = int(rank), min(int(rank) + 1, n - 1)
        return values[lo] + (values[hi] - values[lo]) * (rank - lo)

    return {"n": n, "mean": round(statistics.fmean(values), 1), "p50": round(pct(0.5), 1), "p99": round(pct(0.99), 1), "max": round(values[-1], 1)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rounds", required=True, type=Path, help="rounds.jsonl written by latency_baseline_driver.py")
    parser.add_argument("--llm-log", required=True, type=Path)
    parser.add_argument("--agent-log", required=True, type=Path)
    parser.add_argument("--json-output", type=Path, default=None)
    args = parser.parse_args()
    calls = pair_calls(load_llm_calls(args.llm_log))
    anchors = load_agent_anchors(args.agent_log)
    rounds = [json.loads(line) for line in args.rounds.read_text(encoding="utf-8").splitlines() if line.strip()]
    per_round = []
    for r in rounds:
        a = attribute(r, calls, anchors)
        per_round.append({"scenario": r["scenario"], "round": r["round"], "failures": r.get("failures", []), **a})
    by_scenario: dict[str, dict] = {}
    keys = ["submit->semantic_start", "semantic_ms(until main start)", "main_model_start_after_submit", "main_model_ms(until next call)", "main_model_ms(until final_sent)", "post_main_ms(until final_sent)", "submit->final_sent(server)"]
    for scenario in sorted({r["scenario"] for r in per_round}):
        rows = [r for r in per_round if r["scenario"] == scenario and not r["failures"] and "skipped" not in r]
        by_scenario[scenario] = {k: _stats([r[k] for r in rows if k in r]) for k in keys if any(k in r for r in rows)}
        by_scenario[scenario]["llm_calls_per_round"] = _stats([r["llm_calls"] for r in rows]) if rows else None
        by_scenario[scenario]["revision_timeouts"] = sum(r.get("spoken_revision_failed", 0) for r in rows)
    print("=== per-round attribution ===")
    for r in per_round:
        print(json.dumps(r, ensure_ascii=False))
    print("\n=== per-scenario (ms) ===")
    for scenario, item in by_scenario.items():
        print(f"\n## {scenario}")
        for k, st in item.items():
            print(f"  {k:44} {st}")
    if args.json_output is not None:
        args.json_output.write_text(json.dumps({"per_round": per_round, "by_scenario": by_scenario}, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
