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
    recorded_case: Path | None = None,
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
    from jiuwenswarm.server.live_voice.production_task_intent import (
        AuthenticatedTaskFact, AttemptState, TaskAuthorityRead, TaskState,
        TerminalOutcome,
    )
    from jiuwenswarm.server.live_voice.task_semantics import (
        TaskSemanticContext,
        TaskSemanticResolver,
    )
    from jiuwenswarm.server.runtime.agent_adapter.interface_deep import (
        build_model_from_entry,
    )

    logging.disable(logging.CRITICAL)  # Test report owns the non-secret evidence.
    observed_responses = []
    from tests.support.live_voice.semantic_constraint_oracles import (
        CONTRARY_EFFECTS,
        EQUIPMENT_CONSTRAINTS,
        FLIGHT_CONSTRAINTS,
        assert_constraint_patterns,
    )

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
        (
            "same-problem-independent-work",
            "在同一设备项目里另外新建一个独立的后台任务，叫设备培训材料。只整理使用培训说明，保存为培训说明.md；不要承接设备更换比较，也不要修改先前提案。",
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
    recorded_bytes = recorded_case.read_bytes() if recorded_case else None
    recorded = json.loads(recorded_bytes) if recorded_bytes is not None else None
    recorded_sha256 = (
        hashlib.sha256(recorded_bytes).hexdigest()
        if recorded_bytes is not None
        else None
    )
    if recorded:
        cases.append(
            (
                recorded["case"],
                recorded["input"]["commit"]["text"],
                recorded["expected"]["route"],
                recorded["expected"]["operation"],
            )
        )
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
        if recorded and case_id == recorded["case"]:
            entry["recorded_expected"] = recorded["expected"]
            entry["recorded_case_sha256"] = recorded_sha256
            entry["required_constraint_patterns"] = dict(FLIGHT_CONSTRAINTS)
            entry["forbidden_constraint_patterns"] = dict(CONTRARY_EFFECTS)
        elif case_id == "detailed-proposal-acceptance":
            entry["required_constraint_patterns"] = dict(EQUIPMENT_CONSTRAINTS)
            entry["forbidden_constraint_patterns"] = dict(CONTRARY_EFFECTS)
        started = time.monotonic()
        response_start = len(observed_responses)
        try:
            context = TaskSemanticContext(
                TaskAuthorityRead(scope, "no-task-facts", ()),
                scope.session_id,
                pending=(pending_offer,)
                if case_id
                in {
                    "detailed-proposal-acceptance",
                    "independent-new-objective",
                    "same-problem-independent-work",
                }
                else (),
            )
            if recorded and case_id == recorded["case"]:
                commit = TurnCommit.from_dict(recorded["input"]["commit"])
                captured = recorded["input"]["context"]
                context = TaskSemanticContext(
                    TaskAuthorityRead(
                        commit.scope, captured["authority_fingerprint"], tuple(
                            AuthenticatedTaskFact(**{
                                **fact,
                                "state": TaskState(fact["state"]),
                                "outcome": TerminalOutcome(fact["outcome"]) if fact["outcome"] else None,
                                "attempt_state": AttemptState(fact["attempt_state"]),
                                "attempt_outcome": TerminalOutcome(fact["attempt_outcome"]) if fact["attempt_outcome"] else None,
                                "supported_operations": frozenset(fact["supported_operations"]),
                            }) for fact in captured["tasks"]
                        ),
                    ),
                    captured["conversation_id"],
                    tuple(captured["history"]),
                    tuple(captured["pending"]),
                )
                entry["recorded_input"] = recorded["input"]
            decision = await TaskSemanticResolver(catalog).resolve(
                commit, context, analysis=analysis
            )
            entry["analysis"] = analysis
            entry.update(
                route=decision.route,
                operation=decision.proposal.operation,
                arguments=dict(decision.proposal.arguments),
                provenance=decision.origin_context_binding,
                reference_id=decision.reference_id,
                continuation_action=decision.continuation_action,
                requirement_source_ids=decision.frozen_record()["body"]["output"].get("requirement_source_ids", []),
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
                entry["constraint_checks"] = assert_constraint_patterns(
                    instruction, EQUIPMENT_CONSTRAINTS
                )
            if case_id == "independent-new-objective":
                assert (
                    decision.reference_id is None
                    and decision.continuation_action is None
                )
                assert "garden-review.md" in decision.proposal.arguments["instruction"]
                assert not entry["requirement_source_ids"]
            if case_id == "same-problem-independent-work":
                assert (
                    decision.reference_id is None
                    and decision.continuation_action is None
                )
                assert decision.proposal.arguments["name"] == "设备培训材料"
                assert not entry["requirement_source_ids"]
                assert "培训说明.md" in decision.proposal.arguments["instruction"]
            if recorded and case_id == recorded["case"]:
                expected = recorded["expected"]
                inherited_source = expected.get("requirement_source_id")
                if not (inherited_source and inherited_source in entry["requirement_source_ids"]):
                    assert decision.reference_id == expected["reference_id"]
                    assert decision.continuation_action == expected["continuation_action"]
                assert decision.proposal.arguments["name"] == expected["name"]
                assert all(
                    value in decision.proposal.arguments["instruction"]
                    for value in expected["instruction_contains"]
                )
                entry["constraint_checks"] = assert_constraint_patterns(
                    decision.proposal.arguments["instruction"], FLIGHT_CONSTRAINTS
                )
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
            "tests/support/live_voice/semantic_constraint_oracles.py",
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
    parser.add_argument(
        "--recorded-case",
        type=Path,
        help="Test-only recorded semantic input with read-only task facts and predeclared expectations; no executor",
    )
    args = parser.parse_args()
    raise SystemExit(
        asyncio.run(
            probe(
                args.config_dir.resolve(),
                args.output_dir.resolve(),
                args.reasoning_effort,
                args.cases,
                args.recorded_case,
            )
        )
    )
