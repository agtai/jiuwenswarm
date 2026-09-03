"""Read-only real configured-model probe. NOT browser/Task/audio acceptance.

Run with --config-dir pointing at existing private configuration and --output-dir
at a disposable evidence directory. Credentials are read in place, never copied.
Fixed inputs/oracles live here in test tooling, never in the production resolver.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path


async def probe(
    config_dir: Path,
    output_dir: Path,
    reasoning_effort: str | None = None,
    selected_cases=None,
) -> int:
    from dotenv import load_dotenv

    load_dotenv(config_dir / ".env", override=False)
    os.environ["JIUWENSWARM_DATA_DIR"] = str(output_dir / "runtime")
    from jiuwenswarm.common.config import _read_with_retry, get_default_models
    from jiuwenswarm.common.schema.live_voice_contract_v2 import (
        Assurance,
        ScopeRef,
        TurnCommit,
    )
    from jiuwenswarm.server.live_voice.p3_model_resolution import (
        ServerModelCatalogResolver,
    )
    from jiuwenswarm.server.live_voice.production_task_intent import TaskAuthorityRead
    from jiuwenswarm.server.live_voice.task_semantics import (
        TaskSemanticContext,
        TaskSemanticResolver,
    )
    from jiuwenswarm.server.runtime.agent_adapter.interface_deep import (
        build_model_from_entry,
    )

    logging.disable(logging.CRITICAL)  # Test report owns the non-secret evidence.
    observed_responses = []

    class ObservedModel:
        def __init__(self, model):
            self.model = model

        async def invoke(self, **kwargs):
            if reasoning_effort is not None:
                kwargs = {**kwargs, "reasoning_effort": reasoning_effort}
            response = await self.model.invoke(**kwargs)
            observed_responses.append(
                {
                    "content": response.content,
                    "tool_calls": bool(getattr(response, "tool_calls", None)),
                }
            )
            return response

    catalog = ServerModelCatalogResolver(
        catalog_reader=lambda: get_default_models(
            _read_with_retry(config_dir / "config.yaml")
        ),
        model_builder=lambda client, config: ObservedModel(
            build_model_from_entry(client, config)
        ),
    )
    scope = ScopeRef(
        "probe-subject",
        "probe-no-executor",
        "probe-conversation",
        Assurance.AUTHENTICATED,
    )
    cases = [
        (
            "analysis",
            "先读取项目资料并分析设备现状，暂时不要创建后台任务。",
            "dialogue",
            None,
        ),
        (
            "direct-zh",
            "请新建一个后台任务，叫设备清点，读取设备资料并把检查报告保存为 inventory-review.md。不要购买设备，新增支出上限1500元。",
            "task",
            "task.create",
        ),
        (
            "direct-en",
            "Start background work named Garden review: read the planting notes, compare watering needs and save garden-review.md. Do not order supplies.",
            "task",
            "task.create",
        ),
        ("missing-proposal", "你就在后台处理吧。", "clarification", None),
        ("negation", "不要取消任何任务，也不要新建任务。", "dialogue", None),
        ("ambiguous-cancel", "帮我取消那个任务。", "clarification", None),
        (
            "offered-work-not-execution",
            "请先分析资料，不要现在创建后台任务。",
            "proposal",
            "task.create",
            "已根据资料比较可行的交通组合，今晚到达比明早出发更稳妥。是否要我帮你把预订优先级和操作步骤整理成清单？",
        ),
        (
            "generic-help-not-proposal",
            "请分析资料。",
            "dialogue",
            None,
            "资料已经阅读。如有其他问题，随时告诉我。",
        ),
        (
            "detailed-proposal-acceptance",
            "那就在后台处理吧，任务叫设备清点。比较资料里的每种更换组合，可靠性最重要，新增支出不要超过1500元。把核对表和建议保存为设备建议.md，不要采购或发送消息。",
            "task",
            "task.create",
        ),
        (
            "independent-new-objective",
            "Start a separate background task named Garden review. Read the planting notes and write watering advice to garden-review.md. Do not purchase anything.",
            "task",
            "task.create",
        ),
    ]
    pending_offer = {
        "id": "probe-offered-audit",
        "version": 1,
        "kind": "proposal",
        "operation": "task.create",
        "target": None,
        "target_kind": None,
        "arguments": {
            "name": "设备维护比较",
            "instruction": "读取设备资料，比较机房设备更换方案，优先保证连续服务且维护期间不停止备份。仅整理建议，不实际购买或安装。",
        },
        "source_id": "probe-analysis-offer",
    }
    if selected_cases:
        if set(selected_cases) - {case[0] for case in cases}:
            raise ValueError("unknown probe case")
        cases = [case for case in cases if case[0] in selected_cases]
    results = []
    for case in cases:
        case_id, text, route, operation = case[:4]
        analysis = (
            {"source_id": f"probe-analysis-{case_id}", "text": case[4]}
            if len(case) > 4
            else None
        )
        commit = TurnCommit.from_dict(
            {
                "contract_version": "live-voice.contract.v2",
                "commit_id": f"probe-{case_id}",
                "turn_id": f"probe-turn-{case_id}",
                "interaction_id": "probe-interaction",
                "text": text,
                "hypothesis_provenance": {"provider": "test-tool-text-only"},
                "scope": scope.to_dict(),
                "context_refs": [],
                "committed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            }
        )
        entry = {
            "case": case_id,
            "input": text,
            "input_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "expected_route": route,
            "expected_operation": operation,
            "status": "FAIL",
        }
        started = time.monotonic()
        response_start = len(observed_responses)
        try:
            context = TaskSemanticContext(
                TaskAuthorityRead(scope, "no-task-facts", ()),
                scope.session_id,
                pending=(pending_offer,)
                if case_id
                in {"detailed-proposal-acceptance", "independent-new-objective"}
                else (),
            )
            decision = await TaskSemanticResolver(catalog).resolve(
                commit, context, analysis=analysis
            )
            entry["analysis"] = analysis
            entry.update(
                route=decision.route,
                operation=decision.proposal.operation,
                arguments=dict(decision.proposal.arguments),
                provenance=decision.origin_context_binding,
            )
            assert decision.route == route and decision.proposal.operation == operation
            if case_id == "direct-zh":
                instruction = decision.proposal.arguments["instruction"]
                assert "inventory-review.md" in instruction
                assert "1500" in instruction or "一千五" in instruction
                assert "不" in instruction
            if case_id == "direct-en":
                assert "garden-review.md" in decision.proposal.arguments["instruction"]
            if case_id == "detailed-proposal-acceptance":
                assert decision.reference_id == pending_offer["id"]
                assert decision.continuation_action == "accept_proposal"
                instruction = decision.proposal.arguments["instruction"]
                assert "备份" in instruction and (
                    "1500" in instruction or "一千五" in instruction
                )
                assert "设备建议.md" in instruction
            if case_id == "independent-new-objective":
                assert (
                    decision.reference_id is None
                    and decision.continuation_action is None
                )
                assert "garden-review.md" in decision.proposal.arguments["instruction"]
            entry["status"] = "PASS"
        except Exception as error:
            entry.update(
                failure_class=type(error).__name__,
                reason=getattr(error, "reason", "ASSERTION_OR_PROVIDER_FAILURE"),
            )
        entry["elapsed_seconds"] = round(time.monotonic() - started, 3)
        entry["actual_model_responses"] = observed_responses[response_start:]
        results.append(entry)
        print(
            json.dumps({k: entry[k] for k in ("case", "status", "elapsed_seconds")}),
            flush=True,
        )
    source = subprocess.run(
        ["git", "rev-parse", "HEAD"], text=True, capture_output=True, check=True
    ).stdout.strip()
    diff = subprocess.run(
        ["git", "diff", "--binary", "HEAD"], capture_output=True, check=True
    ).stdout
    report = {
        "boundary": "real-model-only; no actual microphone, Task, Tool or output audio",
        "head": source,
        "dirty_diff_sha256": hashlib.sha256(diff).hexdigest(),
        "diagnostic_reasoning_effort": reasoning_effort,
        "attempts": results,
    }
    root = Path(__file__).resolve().parents[2]
    report["source_sha256"] = {
        name: hashlib.sha256((root / name).read_bytes()).hexdigest()
        for name in (
            "scripts/live_voice/semantic_model_probe.py",
            "jiuwenswarm/server/live_voice/task_semantics.py",
            "jiuwenswarm/server/live_voice/p3_model_resolution.py",
            "jiuwenswarm/common/reasoning_injector.py",
            "jiuwenswarm/common/live_voice_operation_budgets.py",
        )
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / (
        "model-probe-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f") + ".json"
    )
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(str(report_path), flush=True)
    return 0 if all(entry["status"] == "PASS" for entry in results) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--reasoning-effort",
        choices=["low"],
        help="Diagnostic per-call trial only; never writes configured settings",
    )
    parser.add_argument(
        "--cases",
        nargs="+",
        help="Run selected fixed cases; report never claims unexecuted cases",
    )
    args = parser.parse_args()
    raise SystemExit(
        asyncio.run(
            probe(
                args.config_dir.resolve(),
                args.output_dir.resolve(),
                args.reasoning_effort,
                args.cases,
            )
        )
    )
