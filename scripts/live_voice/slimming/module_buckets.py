"""Bucket every dedicated LiveVoice production file into the 18 planning modules.

Usage: python module_buckets.py --rev REV [--json OUT]
The rules are filename heuristics for coarse planning comparisons, not the manifest's per-symbol
ownership. Native files are reported separately. Non-behaviour lines are blank, comment and docstring.
"""
from __future__ import annotations

import argparse
import ast
import io
import json
import re
import tokenize
from collections import defaultdict

from _common import SHARED_HOSTS, git, show

EXTRA = (
    "ChatPanel/L0OrdinaryChromeBatchPanel.tsx", "ChatPanel/useProductVoiceSessionStart.ts",
    "ToolPanel/RecentTasksPanel.tsx", "agent_adapter/formal_model_diagnostics.py",
    "agent_adapter/formal_tool_gate.py", "server/live_voice_agent_carrier.py",
)
RULES = [
    ("NATIVE (excluded)", r"native_|openai_realtime"),
    ("18 Test/reference in prod", r"fake_verticals|executor_port|conversationRuntimeReplica|fakeP1Vertical|webLifecycleObservationRecorder|formalTaskResultRoute|realtime_media\.py|product_p2_readiness|demo_fixture"),
    ("17 Legacy/compat", r"useLiveVoiceDemo|liveVoiceCore\.ts|liveVoiceMessageGate|liveVoiceStreamingSpeech|liveVoiceTurnLifecycle|integratedP1Route|browserSpeechRecognitionAdapter|browserSpeechSynthesisAdapter|liveVoiceTask(Adapter|Bridge|Client|Monitor)|LiveVoiceDemoBar"),
    ("15 Observability", r"(?i)observab|profil|diagnos|latency_measurement|telemetry|sli_window|alpha_benchmark|alpha_privacy|l0Measurement|l0OrdinaryChromeBatch|L0OrdinaryChromeBatchPanel|RouteTelemetry|deployment_(observer|preflight)"),
    ("16 Schema/protocol", r"common/schema/live_voice_contract|liveVoiceContractV2|productCompositionContract|speech_rpc|live_voice_capture_limits|live_voice_operation_budgets"),
    ("08 Task Store", r"live_voice/task_store\.py"),
    ("09 Project executor", r"project_code_executor"),
    ("10 Checkpoint/effect", r"durability_"),
    ("07 Task domain/control", r"formal_task_models|persistent_task_core|task_core\.py|task_admission|executor_(capab|profile)|task_command|attempt"),
    ("11 Task event/progress", r"task_progress|progress_notification|task_event|productTextProgress|product_p3_text_adapter|task_presentation|TaskProgress"),
    ("12 Presentation/history", r"presentation_ledger|formal_history_writer|taskPresentationView|task_control_presentation|generation_store|p2_response_generation"),
    ("04 Committed input/product authority", r"unified_committed_input|task_semantics|semantic_continuity|production_task|voice_task|critical_token|p3_confirmation|p3_product_confirmation|product_authority|p3_model_resolution|p3_production_intent|unifiedCommittedInputOwner|p3_authenticated"),
    ("05 Conversation Runtime", r"conversation_runtime|agent_conversation|speculative_dialogue|interaction_engine"),
    ("06 Agent bridge", r"agent_bridge|round_harness|jiuwenswarm_agent_adapter|formal_live_voice\.py|formal_tool_gate|formal_model|live_voice_agent_carrier"),
    ("03 Speech provider", r"batch_speech|streaming_speech\.py|openai_streaming_speech|speech_"),
    ("02 Web/Gateway media transport", r"gateway/live_voice/|browserDedicatedMediaRoute|browserGatewayMediaTransport|gatewayBatchSpeechClient|realtimeMedia|dedicatedMedia"),
    ("01 Browser Audio Edge", r"browserAudioIO|audioPort|liveVoiceCaptureProcessor|productP1VoiceRoute|browserLiveVoiceOwnership|browserAudioDeviceSelection|deviceSelection|playout|audioDiagnostic"),
    ("13 Formal Web/UI", r"LiveVoiceIntegratedRoutePanel|RecentTasksPanel|formalP3TaskExperience|formalTaskControlLeaf|formalTaskIntentRoute|integratedWebRouteShell|productWebActivation|productP2ActivationJournal|useProductVoiceSessionStart|createLiveVoiceConversation|liveVoiceTaskStore|productP3|ProductP3|formalP3|taskNotification"),
    ("14 Composition/config", r"product_composition_registry|product_p2_interaction_adapter|composition|declaration|featureFlags|configuration|registry|catalog|__init__"),
]


def non_behaviour(path: str, text: str) -> tuple[int, int, int, int]:
    lines = text.splitlines()
    blank = sum(1 for l in lines if not l.strip())
    if path.endswith(".py"):
        comment = doc = 0
        try:
            comment = sum(1 for tok in tokenize.generate_tokens(io.StringIO(text).readline) if tok.type == tokenize.COMMENT)
        except Exception:
            pass
        try:
            for node in ast.walk(ast.parse(text)):
                if (isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body
                        and isinstance(node.body[0], ast.Expr) and isinstance(getattr(node.body[0], "value", None), ast.Constant)
                        and isinstance(node.body[0].value.value, str)):
                    doc += node.body[0].end_lineno - node.body[0].lineno + 1
        except Exception:
            pass
        return len(lines), blank, comment, doc
    comment = sum(1 for l in lines if l.strip().startswith(("//", "/*", "*")))
    return len(lines), blank, comment, 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rev", default="HEAD")
    ap.add_argument("--json")
    args = ap.parse_args()
    tracked = git("ls-tree", "-r", "--name-only", args.rev, "jiuwenswarm").splitlines()
    files = [f for f in tracked
             if (re.search(r"live_voice|live-voice|LiveVoice", f) or any(f.endswith(e) for e in EXTRA))
             and "/tests/" not in f and ".test." not in f and f.endswith((".py", ".ts", ".tsx", ".js"))
             and not any(s in f for s in SHARED_HOSTS)]
    buckets: dict = defaultdict(lambda: {"files": [], "loc": 0, "blank": 0, "comment": 0, "doc": 0})
    for f in files:
        n, b, c, d = non_behaviour(f, show(args.rev, f))
        module = next((m for m, rx in RULES if re.search(rx, f)), "?? unassigned")
        bucket = buckets[module]
        bucket["files"].append((n, f))
        bucket["loc"] += n
        bucket["blank"] += b
        bucket["comment"] += c
        bucket["doc"] += d
    total_files = total_loc = total_nb = 0
    print(f"{'module':<40}{'files':>6}{'LOC':>9}{'nonbeh%':>9}")
    for m in sorted(buckets):
        bucket = buckets[m]
        nb = bucket["blank"] + bucket["comment"] + bucket["doc"]
        total_files += len(bucket["files"])
        total_loc += bucket["loc"]
        total_nb += nb
        print(f"{m:<40}{len(bucket['files']):>6}{bucket['loc']:>9,}{100 * nb / bucket['loc']:>8.0f}%")
    print(f"{'TOTAL':<40}{total_files:>6}{total_loc:>9,}{100 * total_nb / total_loc:>8.0f}%")
    if "?? unassigned" in buckets:
        print("unassigned:", sorted(buckets["?? unassigned"]["files"], reverse=True))
    if args.json:
        payload = {m: {"loc": b["loc"], "files": sorted(b["files"], reverse=True)} for m, b in buckets.items()}
        io.open(args.json, "w", encoding="utf-8").write(json.dumps(payload, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
