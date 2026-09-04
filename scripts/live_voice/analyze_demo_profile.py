"""Offline, content-free rehearsal report. Reads diagnostics, never raw log text.

Run with --latest [--browser exported.json] or repeat --log for retained logs.
No network, Provider calls, business mutations, or dependency installation.
"""
from __future__ import annotations

import argparse
import heapq
import json
import math
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jiuwenswarm.common.live_voice_audio_diagnostics import _IDS, _LABELS, _TOKENS, _VALUES  # noqa: E402

MAX_RECORDS = 200_000
MAX_LINE = 64 * 1024
MAX_BROWSER_BYTES = 32 * 1024 * 1024
TOKEN = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")
BROWSER_VALUES = frozenset({
    "operation_generation", "pending_frames", "pending_bytes", "socket_buffered_bytes", "frame_age_ms", "tick_delay_ms",
    "rms_peak", "energy_frames", "startup_lead_ms", "buffer_ahead_ms", "schedule_gap_ms", "scheduled_sources",
    "stopped_sources", "failed_sources", "long_task_ms", "seq", "provider_speech_started", "eot_pending",
    "eot_delivered", "handler_present", "playout_pending", "rotation_in_flight", "attached", "closed",
    "callback_current", "capture_ready", "echo_cancellation", "noise_suppression", "auto_gain_control",
    "output_latency_ms", "base_latency_ms",
})
JOIN_IDS = {"request_id", "capture_id", "response_id", "media_session_id", "correlation_id",
            "interaction_id", "task_id", "attempt_id", "commit_id", "operation_id", "execution_session_id"}


def sanitize_record(value):
    if not isinstance(value, dict) or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", str(value.get("event", ""))):
        return None
    mono = value.get("monotonic_ms")
    if type(mono) not in {int, float} or not math.isfinite(mono) or mono < 0:
        return None
    stamp = value.get("observed_at")
    if not isinstance(stamp, str) or len(stamp) > 40:
        return None
    try:
        parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return None
        wall_ms = parsed.timestamp() * 1000
    except (ValueError, OverflowError):
        return None
    raw_fields = value.get("fields", {})
    if not isinstance(raw_fields, dict):
        return None
    fields = {}
    for key, field in raw_fields.items():
        if key in _IDS | _TOKENS and isinstance(field, str) and TOKEN.fullmatch(field):
            fields[key] = field
        elif key in _VALUES | BROWSER_VALUES and (field is None or type(field) is bool or
              type(field) in {int, float} and math.isfinite(field)):
            fields[key] = field
        elif key in _LABELS and isinstance(field, str) and field in _LABELS[key]:
            fields[key] = field
        elif key in {"status", "reason", "direction", "context_state"} and isinstance(field, str) and TOKEN.fullmatch(field):
            fields[key] = field
    clock = value.get("clock_id")
    clock = clock if isinstance(clock, str) and TOKEN.fullmatch(clock) else None
    sequence = value.get("sequence")
    dropped = value.get("dropped_records", 0)
    return {"event": value["event"], "observed_at": stamp, "wall_ms": wall_ms,
            "monotonic_ms": mono, "clock_id": clock,
            "sequence": sequence if type(sequence) is int and sequence >= 0 else None,
            "dropped_records": dropped if type(dropped) is int and dropped >= 0 else 0,
            "fields": fields}


def load_records(logs, browsers):
    records, warnings = [], []
    retention = []
    rejected = 0
    seen = set()

    def add(value):
        nonlocal rejected
        record = sanitize_record(value)
        if record is None:
            rejected += 1
            return
        if len(records) >= MAX_RECORDS:
            return
        key = (record["clock_id"], record["sequence"])
        if key[0] and key[1] is not None:
            if key in seen:
                return
            seen.add(key)
        records.append(record)

    for path in logs:
        with Path(path).open(encoding="utf-8", errors="replace") as stream:
            while True:
                line = stream.readline(MAX_LINE + 1)
                if not line:
                    break
                if len(line) > MAX_LINE:
                    while line and not line.endswith("\n"):
                        line = stream.readline(MAX_LINE + 1)
                    rejected += 1
                    continue
                marker = "live_voice_audio_diagnostic "
                if marker not in line:
                    continue
                try:
                    add(json.loads(line.split(marker, 1)[1].strip()))
                except (ValueError, TypeError):
                    rejected += 1
    for path in browsers:
        path = Path(path)
        if path.stat().st_size > MAX_BROWSER_BYTES:
            raise ValueError("Browser diagnostic export exceeds the 32 MiB import bound")
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        if isinstance(value, dict):
            retention.append({key: value[key] for key in ("memory_overwrites", "overwritten_pages", "storage_failures")
                              if type(value.get(key)) is int and value[key] >= 0})
            value = value.get("records", [])
        if not isinstance(value, list):
            raise ValueError("Expected a browser diagnostic bundle or record array")
        for item in value[:MAX_RECORDS]:
            add(item)
    if not browsers:
        warnings.append("Browser export absent: browser capture, RPC, playback and interruption coverage is incomplete.")
    if rejected:
        warnings.append(f"Discarded {rejected} malformed/oversize diagnostic records or log lines.")
    if len(records) >= MAX_RECORDS:
        warnings.append("Record import reached its bound; this report is truncated.")
    if any(record["clock_id"] is None for record in records):
        warnings.append("Legacy records lack a clock domain; no durations are inferred between them.")
    if any(item.get("overwritten_pages", 0) or item.get("storage_failures", 0) for item in retention):
        warnings.append("Browser storage was overwritten or unavailable; inspect retention counters before treating absence as evidence.")
    if any(record["dropped_records"] for record in records):
        warnings.append("Backend sink reports dropped records; gaps are not zero-duration steps.")
    sequences = defaultdict(set)
    for record in records:
        if record["clock_id"] and record["sequence"] is not None:
            sequences[record["clock_id"]].add(record["sequence"])
    gaps = sum(max(values) - min(values) + 1 - len(values) for values in sequences.values())
    if gaps:
        warnings.append(f"{gaps} sequence positions absent inside imported clock ranges; inspect missing evidence.")
    return records, warnings, retention


def select_session(records, session):
    if session is None:
        return records
    selected = {index for index, record in enumerate(records) if record["fields"].get("session_id") == session}
    # Joins use exact existing identities, never content similarity or nearest time.
    for _ in range(8):
        keys = {(key, value) for index in selected for key, value in records[index]["fields"].items() if key in JOIN_IDS}
        more = {index for index, record in enumerate(records)
                if record["fields"].get("session_id") in {None, session}
                and any((key, value) in keys for key, value in record["fields"].items() if key in JOIN_IDS)}
        if more <= selected:
            break
        selected |= more
    return [record for index, record in enumerate(records) if index in selected]


def build_report(records, warnings=(), retention=()):
    records = sorted(records, key=lambda row: (row["wall_ms"], row["monotonic_ms"]))
    starts, spans, failures, boundaries = {}, [], [], {}

    def boundary(key, stage, row, started, duration_field=None):
        if started:
            if key in boundaries:
                prior = boundaries[key]
                spans.append({"stage": stage, "start": prior, "fields": prior["fields"],
                              "duration_ms": None, "state": "duplicate_start"})
            boundaries[key] = row
            return
        start = boundaries.pop(key, None)
        fields = {**(start["fields"] if start else {}), **row["fields"]}
        measured = fields.get(duration_field) if duration_field else None
        if type(measured) not in {int, float} or measured < 0:
            measured = row["monotonic_ms"] - start["monotonic_ms"] if start else None
        spans.append({"stage": stage, "start": start or row, "end": row, "fields": fields,
                      "duration_ms": measured if measured is not None and measured >= 0 else None,
                      "state": fields.get("outcome", "unknown") if start else "start_missing"})

    # Pair within monotonic domains even if the machine wall clock jumps.
    for row in sorted(records, key=lambda r: (r["clock_id"] or "", r["monotonic_ms"], r["sequence"] or 0)):
        fields = row["fields"]
        key = (row["clock_id"], fields.get("span_id"))
        if row["event"] == "profile_span_started" and all(key):
            # Reused/corrupt span IDs are visible, not silently re-paired.
            if key in starts:
                spans.append({**starts[key], "state": "duplicate_start", "duration_ms": None})
            starts[key] = {"stage": fields.get("stage", "unknown"), "start": row, "fields": fields}
        elif row["event"] == "profile_span_settled" and all(key):
            start = starts.pop(key, None)
            duration = fields.get("duration_ms")
            duration = duration if type(duration) in {int, float} and math.isfinite(duration) and duration >= 0 else None
            if start and row["monotonic_ms"] < start["start"]["monotonic_ms"]:
                duration = None
            spans.append({"stage": fields.get("stage", "unknown"), "start": start["start"] if start else row,
                          "end": row, "fields": {**(start["fields"] if start else {}), **fields},
                          "duration_ms": duration, "state": fields.get("outcome", "unknown") if start else "start_missing"})
        if row["event"] == "tool_boundary" and row["clock_id"] and fields.get("tool_call_id"):
            tool_key = ("tool", row["clock_id"], fields.get("request_id"), fields["tool_call_id"])
            if fields.get("milestone") in {"chat.tool_call", "chat.tool_result"}:
                boundary(tool_key, "tool." + fields.get("tool_name", "unknown"), row,
                         fields["milestone"] == "chat.tool_call")
        if row["event"] in {"model_stream_started", "model_stream_settled"} and row["clock_id"] and fields.get("model_call_id"):
            boundary(("model", row["clock_id"], fields["model_call_id"]), "model.stream", row,
                     row["event"] == "model_stream_started", "duration_ms")
        if row["event"] == "batch_http_phase" and row["clock_id"] and (fields.get("operation_id") or fields.get("span_id")):
            phase = fields.get("http_phase", "unknown")
            boundary(("http", row["clock_id"], fields.get("operation_id") or fields["span_id"], phase),
                     "http." + phase, row, fields.get("outcome") == "started", "phase_ms")
        if (fields.get("outcome") in {"failed", "rejected", "timeout", "cancelled", "fallback"}
            or fields.get("status") in {"failed", "error", "rejected", "timeout", "cancelled", "fallback"}
            or fields.get("milestone") in {"fallback", "failed", "cancelled", "timeout", "chat.error"}) or any(
            word in row["event"] for word in ("failed", "timeout", "deadline", "rejected", "browser_error", "unhandled_rejection")
        ):
            failures.append(row)
    spans.extend({**value, "duration_ms": None, "state": "open_or_truncated"} for value in starts.values())
    for key, row in boundaries.items():
        fields = row["fields"]
        stage = {"tool": "tool." + fields.get("tool_name", "unknown"),
                 "model": "model.stream", "http": "http." + fields.get("http_phase", "unknown")}[key[0]]
        spans.append({"stage": stage, "start": row, "fields": fields, "duration_ms": None, "state": "open_or_truncated"})
    spans.sort(key=lambda span: (span["start"]["wall_ms"], span["start"]["monotonic_ms"]))
    grouped = defaultdict(list)
    for span in spans:
        if span["duration_ms"] is not None:
            grouped[span["stage"]].append(span["duration_ms"])
    aggregates = []
    for stage, values in grouped.items():
        values.sort()
        aggregates.append({"stage": stage, "count": len(values), "p50_ms": values[math.ceil(len(values) * .5) - 1],
                           "p95_ms": values[math.ceil(len(values) * .95) - 1], "max_ms": max(values)})
    coverage_rules = {
        "Browser capture/startup": ("capture_",), "Media / upload / EOT": ("gateway_", "adapter_", "socket_", "media_"),
        "Recognition / fallback": ("recognition.", "batch_"), "Semantic decision": ("semantic.",),
        "Agent / model": ("agent.", "formal_model_", "model.", "model_stream_", "task_model_"), "Tools": ("tool_boundary",),
        "Spoken revision": ("agent.spoken_revision",), "Synthesis / first audio": ("synthesis.", "synthesis_"),
        "Browser playback": ("playout_", "webaudio_",), "Task execution": ("executor.",),
        "Notification / ACK": ("notification.", "rpc.notification", "rpc.presentation"),
        "Interruption / recovery": ("barge_in", "rpc.barge", "rpc.interrupt", "p1_stop"),
        "Browser RPC": ("browser.rpc",),
    }
    coverage = {}
    for name, prefixes in coverage_rules.items():
        coverage[name] = sum(any(str(value).startswith(prefixes) for value in
            (row["event"], row["fields"].get("stage", ""), row["fields"].get("milestone", ""))) for row in records)
    return {"format": "live-voice.profile-report.v1", "record_count": len(records),
            "warnings": list(warnings), "browser_retention": list(retention),
            "notes": ["Durations use one clock domain. Wall-clock ordering across processes/tabs is approximate.",
                      "Nested/overlapping spans must not be added. Returned means the call returned, not business success.",
                      "Open spans can mean ongoing work or missing tail records. Unobserved branches are not automatically defects.",
                      "Scheduling/ACK is not proof of physical audibility. Provider/network internals require their own evidence."],
            "coverage": coverage, "spans": spans, "failures": failures,
            "stages": sorted(aggregates, key=lambda row: row["max_ms"], reverse=True),
            "records": records, "clock_domains": dict(Counter(row["clock_id"] or "unknown" for row in records))}


def chrome_trace(report):
    events = []
    clocks = {clock: index + 1 for index, clock in enumerate(report["clock_domains"])}
    lanes = defaultdict(list)
    lane_counts = Counter()
    for clock, pid in clocks.items():
        events.append({"name": "process_name", "ph": "M", "pid": pid, "tid": 0, "args": {"name": clock}})
    for span in sorted(report["spans"], key=lambda s: s["start"]["wall_ms"]):
        start = span["start"]
        clock = start["clock_id"] or "unknown"
        pid = clocks[clock]
        duration = span["duration_ms"] if span["state"] != "start_missing" else None
        # Concurrent async spans are not synchronous call-stack nesting. Assign
        # non-overlapping numeric lanes so trace importers retain every span.
        if lanes[pid] and lanes[pid][0][0] <= start["wall_ms"]:
            _, lane = heapq.heappop(lanes[pid])
        else:
            lane_counts[pid] += 1
            lane = lane_counts[pid]
        heapq.heappush(lanes[pid], (start["wall_ms"] + (duration or 0), lane))
        common = {"name": span["stage"], "cat": "live-voice", "pid": pid, "tid": lane,
                  "ts": start["wall_ms"] * 1000, "args": {**span["fields"], "observation_state": span["state"]}}
        if duration is None:
            events.append({**common, "ph": "i", "s": "t"})
        else:
            events.append({**common, "ph": "X", "dur": duration * 1000})
    return {"traceEvents": events, "displayTimeUnit": "ms"}


def render_html(report):
    # JSON is base64-free text in a non-executable element. Escape '<' so no
    # imported value can terminate the element; all rendering uses textContent.
    data = json.dumps(report, ensure_ascii=True).replace("<", "\\u003c").replace("&", "\\u0026")
    return '''<!doctype html><html lang="zh"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Live Voice Demo Profile</title><style>
body{font:14px system-ui;margin:32px;background:#f6f7f9;color:#182230}h1{font-size:26px}h2{margin-top:30px}input{padding:10px;width:min(720px,90%)}
table{border-collapse:collapse;width:100%;background:white}th,td{text-align:left;padding:8px;border-bottom:1px solid #dde2e9;vertical-align:top}th{position:sticky;top:0;background:#e9edf3}
code{font-size:12px;overflow-wrap:anywhere}.warning{padding:10px;background:#fff0d5;margin:8px 0}.muted{color:#536173}.bar{height:5px;background:#2767a7;margin-top:5px}details{margin:12px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere}button{padding:8px;margin:8px}#timeline{max-height:650px;overflow:auto}
</style><h1>Live Voice · Demo 性能与故障报告</h1><p id="summary"></p><div id="warnings"></div><details open><summary>读数边界</summary><ul id="notes"></ul></details>
<label>筛选 Session / capture / request / response / Task / 阶段：<br><input id="filter" placeholder="输入关联 ID 或阶段名"></label><button id="errors">只看失败 / 取消 / 未结束</button>
<h2>链路覆盖</h2><p class="muted">未观测可能是本轮未触发，也可能缺少记录；不会记作 0 ms。</p><table id="coverage"></table>
<h2>最慢阶段</h2><p class="muted">含嵌套、并行与等待时间；请勿将各行简单相加。</p><table id="stages"></table>
<h2>调用时间线</h2><p id="render-limit" class="muted"></p><div id="timeline"><table id="spans"></table></div><h2>错误与取消定位</h2><div id="failures"></div>
<details><summary>全部诊断事件（包括队列、HTTP、VAD 和模型首输出）</summary><pre id="events"></pre></details>
<script type="application/json" id="data">''' + data + r'''</script><script>
const r=JSON.parse(document.getElementById('data').textContent);const el=id=>document.getElementById(id);
const fmt=n=>n==null?'未测得':Number(n).toFixed(2)+' ms';let onlyErrors=false;
const text=(tag,value)=>{const n=document.createElement(tag);n.textContent=String(value);return n};
const table=(id,heads,rows)=>{const t=el(id);t.replaceChildren();const h=document.createElement('tr');heads.forEach(v=>h.append(text('th',v)));t.append(h);rows.forEach(row=>{const tr=document.createElement('tr');row.forEach(v=>tr.append(text('td',v)));t.append(tr)})};
el('summary').textContent=`${r.record_count} 条事件 · ${Object.keys(r.clock_domains).length} 个时钟域 · ${r.failures.length} 条错误/取消/回退记录`;
r.warnings.forEach(v=>{const n=text('div',v);n.className='warning';el('warnings').append(n)});r.notes.forEach(v=>el('notes').append(text('li',v)));
table('coverage',['环节','记录数'],Object.entries(r.coverage).map(([k,v])=>[k,v||'未观测']));
table('stages',['阶段','次数','P50','P95','最大'],r.stages.map(s=>[s.stage,s.count,fmt(s.p50_ms),fmt(s.p95_ms),fmt(s.max_ms)]));
function render(){const q=el('filter').value.toLowerCase();const match=v=>JSON.stringify(v).toLowerCase().includes(q);
const spans=r.spans.filter(match).filter(s=>!onlyErrors||!['returned','complete'].includes(s.state));
el('render-limit').textContent=`匹配 ${spans.length} 个步骤；页面最多显示前 1000 个步骤/错误、2000 条事件。请按 ID 缩小范围，完整记录见 profile.json。`;
table('spans',['时间 / 时钟域','阶段','耗时 / 结果','关联'],spans.slice(0,1000).map(s=>[s.start.observed_at+'\n'+s.start.clock_id,s.stage,fmt(s.duration_ms)+' · '+s.state,JSON.stringify(s.fields)]));
el('failures').replaceChildren();r.failures.filter(match).slice(0,1000).forEach(f=>{const d=document.createElement('details');d.append(text('summary',f.observed_at+' · '+f.event+' · '+(f.fields.stage||f.fields.rpc_method||'')));d.append(text('pre',JSON.stringify(f.fields,null,2)));el('failures').append(d)});
el('events').textContent=r.records.filter(match).slice(0,2000).map(v=>JSON.stringify(v)).join('\n');}
el('filter').addEventListener('input',render);el('errors').addEventListener('click',()=>{onlyErrors=!onlyErrors;el('errors').textContent=onlyErrors?'显示全部步骤':'只看失败 / 取消 / 未结束';render()});render();
</script></html>'''


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", action="append", default=[], type=Path)
    parser.add_argument("--browser", action="append", default=[], type=Path)
    parser.add_argument("--latest", action="store_true", help="Read the managed service's current log")
    parser.add_argument("--session")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    logs = list(args.log)
    if args.latest:
        state_path = ROOT / "logs/debug_service.json"
        if not state_path.is_file():
            parser.error("No managed service manifest; start the controlled Demo or pass --log PATH.")
        try:
            state = json.loads(state_path.read_text(encoding="utf-8-sig"))
            logs.append(Path(state["log_file"]))
        except (OSError, ValueError, KeyError, TypeError):
            parser.error("Invalid managed service manifest; pass --log PATH for the rehearsal log.")
    if not logs and not args.browser:
        parser.error("Provide --latest, --log or --browser")
    try:
        records, warnings, retention = load_records(logs, args.browser)
    except (OSError, ValueError, TypeError):
        parser.error("Cannot read a diagnostic input; check --log/--browser paths and JSON format.")
    selected = select_session(records, args.session)
    if not selected:
        warnings.append("No matching diagnostic records. Check source version, log selection and session identity.")
    report = build_report(selected, warnings, retention)
    output = args.output or ROOT / "logs" / ("live-voice-profile-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
    output.mkdir(parents=True, exist_ok=True)
    for name, value in (("profile.json", report), ("trace.json", chrome_trace(report))):
        (output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "profile.html").write_text(render_html(report), encoding="utf-8")
    print(f"{len(selected)} diagnostic records; {len(report['spans'])} spans; {len(report['failures'])} failure/cancel/fallback records")
    print(output / "profile.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
