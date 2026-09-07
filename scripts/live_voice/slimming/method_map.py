"""Method map of the giant LiveVoice owner classes with production-caller counts.

Usage: python method_map.py --rev HEAD [--json OUT] [--out MD]

For each listed class the script prints every method with its physical LOC, whether it is public,
and how many *other* production files call ``.<method>(`` (static, name-based, so a common method
name such as ``close`` is over-counted; use the caller list to confirm). The map is the input for the
execution cards of the Task-store, registry, media-registration, executor, runtime and P3 packages.
"""
from __future__ import annotations

import argparse
import ast
import io
import json
import os
import re
import sys
import warnings

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import git, show  # noqa: E402

TARGETS = {
    "jiuwenswarm/server/live_voice/task_store.py": "SqliteTaskStore",
    "jiuwenswarm/server/live_voice/product_composition_registry.py": "AgentServerProductCompositionRegistry",
    "jiuwenswarm/gateway/live_voice/dedicated_media_registration.py": "DedicatedMediaProductRegistry",
    "jiuwenswarm/server/live_voice/project_code_executor.py": "DirectProjectCodeExecutorAdapter",
    "jiuwenswarm/server/live_voice/agent_conversation_runtime.py": "AgentConversationRuntime",
    "jiuwenswarm/server/live_voice/p3_authenticated_composition.py": "P3AuthenticatedComposition",
    "jiuwenswarm/server/live_voice/persistent_task_core.py": "PersistentTaskCore",
    "jiuwenswarm/server/live_voice/conversation_runtime_loop.py": "ConversationRuntimeLoop",
    "jiuwenswarm/server/live_voice/progress_notification_arbiter.py": "ProgressNotificationArbiter",
    "jiuwenswarm/server/live_voice/task_progress_return.py": "TaskProgressReturnBridge",
    "jiuwenswarm/server/live_voice/unified_committed_input.py": "SqliteUnifiedCommittedInputJournal",
    "jiuwenswarm/server/live_voice/streaming_speech.py": "StreamingSpeechConformance",
    "jiuwenswarm/server/live_voice/openai_streaming_speech.py": "OpenAIStreamingSpeechProvider",
    "jiuwenswarm/server/live_voice/batch_speech.py": "FormalBatchSpeechService",
    "jiuwenswarm/gateway/live_voice/streaming_synthesis_route.py": "StreamingSynthesisRouteOwner",
    "jiuwenswarm/gateway/live_voice/streaming_speech_route.py": "StreamingRecognitionRouteOwner",
    "jiuwenswarm/server/live_voice/task_event_subscription.py": "TaskEventSubscription",
    "jiuwenswarm/server/live_voice/presentation_ledger.py": "PresentationLedger",
    "jiuwenswarm/server/live_voice/jiuwenswarm_round_harness.py": "JiuWenSwarmRoundHarness",
    "jiuwenswarm/server/live_voice/agent_bridge_runtime.py": "AgentBridgeRuntime",
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rev", default="HEAD")
    ap.add_argument("--json")
    ap.add_argument("--out")
    args = ap.parse_args()
    tracked = [f for f in git("ls-tree", "-r", "--name-only", args.rev, "jiuwenswarm").splitlines()
               if f.endswith(".py") and "/tests/" not in f]
    texts = {f: show(args.rev, f) for f in tracked}
    result = {}
    md = ["# LiveVoice 巨型 owner 类的方法图（自动生成）", "", f"> 由 `scripts/live_voice/slimming/method_map.py --rev {args.rev}` 生成；`callers` 是其他生产文件里 `.方法名(` 的出现文件数（同名方法会高估）。", ""]
    for path, cls in TARGETS.items():
        text = texts.get(path)
        if text is None:
            continue
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            tree = ast.parse(text)
        node = next((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls), None)
        if node is None:
            continue
        rows = []
        for m in node.body:
            if not isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            loc = m.end_lineno - m.lineno + 1
            public = not m.name.startswith("_")
            callers = []
            if public and m.name not in {"close", "start", "snapshot", "stats", "health", "export"}:
                rx = re.compile(r"\.%s\(" % re.escape(m.name))
                callers = [f.split("jiuwenswarm/", 1)[-1] for f in tracked if f != path and rx.search(texts[f])]
            internal = max(0, len(re.findall(r"\b%s\b" % re.escape(m.name), text)) - 1)
            rows.append({"name": m.name, "loc": loc, "public": public, "callers": len(callers), "caller_names": callers[:3], "internal": internal, "async": isinstance(m, ast.AsyncFunctionDef)})
        result[cls] = {"path": path.split("jiuwenswarm/", 1)[-1], "class_loc": node.end_lineno - node.lineno + 1, "methods": rows}
        pub = [r for r in rows if r["public"]]
        md += [f"## `{cls}`（`{result[cls]['path']}`，{result[cls]['class_loc']:,} 行，{len(rows)} 个方法，其中公开 {len(pub)} 个）", "",
               "| 方法 | 行 | 公开 | callers | 文件内引用 | 调用方示例 |", "|---|---:|---|---:|---:|---|"]
        for r in sorted(rows, key=lambda r: -r["loc"]):
            md.append(f"| `{r['name']}` | {r['loc']} | {'是' if r['public'] else ''} | {r['callers'] if r['public'] else ''} | {r['internal']} | {', '.join(r['caller_names'])} |")
        md.append("")
    if args.json:
        io.open(args.json, "w", encoding="utf-8").write(json.dumps(result, ensure_ascii=False, indent=1))
    text = "\n".join(md) + "\n"
    if args.out:
        io.open(args.out, "w", encoding="utf-8", newline="\n").write(text)
        print("written", args.out, len(md), "lines")
    else:
        print(text[:3000])


if __name__ == "__main__":
    main()
