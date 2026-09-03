"""Two bounded real-Executor checks; not an audio or complete-product Gate.

Reuse the isolated runtime/project setup and production confirmation helper.
No Provider configuration is copied, no old result is changed, and no task
decision or artifact is injected into the Agent. Business facts stay test-only.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

from scripts.live_voice.semantic_audio_runtime import prepare


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


async def run(options):
    root = options.output.resolve()
    env, source = prepare(root, options.config.resolve(), [18202, 19202, 19203, 6182], "cascade")
    os.environ.update(env)
    os.environ["JIUWENSWARM_LIVE_VOICE_P3_RECONCILE_SECONDS"] = "0.25"

    from jiuwenswarm.common.schema.live_voice_contract_v2 import Assurance, ScopeRef
    from jiuwenswarm.server.agent_ws_server import AgentWebSocketServer
    from jiuwenswarm.server.live_voice.p3_authenticated_composition import create_p3_composition_from_environment
    from jiuwenswarm.server.live_voice.p3_confirmation import BoundedP3ConfirmationOwner
    from jiuwenswarm.server.live_voice.p3_model_resolution import ServerModelCatalogResolver
    from jiuwenswarm.server.live_voice.p3_product_confirmation import ProductP3ConfirmationForwarder
    from jiuwenswarm.server.runtime.agent_manager import AgentManager
    from jiuwenswarm.server.runtime.session.project_store import find_or_create_code_project_for_dir
    from jiuwenswarm.server.runtime.session.session_metadata import init_session_metadata
    from scripts.live_voice.p3_wave2_real_evidence_producer import _confirmed_mutation

    original = json.loads(options.recorded_journey.read_text(encoding="utf-8"))
    recorded = original["cases"][1]["after"]["tasks"][0]
    flight_instruction = json.loads(recorded["spec_json"])["instruction"]
    second = root / "maintenance-project"
    second.mkdir()
    (second / "facts.json").write_text(json.dumps({
        "planning_start": "2026-09-04T12:05", "resource_window_ends": "2026-09-04T12:30",
        "resource_window_fixed": True, "mandatory_validation_buffer_minutes": 10,
        "options": {"A": {"work_minutes": 20, "cost": 640}, "B": {"work_minutes": 15, "cost": 900}},
        "cost_preference": "minimize cost among feasible options",
        "external_actions_authorized": False,
    }, indent=2), encoding="utf-8")
    for args in (("init",), ("config", "core.autocrlf", "false"), ("add", "facts.json"),
                 ("-c", "user.name=Local Test", "-c", "user.email=test@invalid", "commit", "-m", "Add test facts")):
        subprocess.run(["git", "-C", str(second), *args], check=True, capture_output=True)
    project = find_or_create_code_project_for_dir(str(second))
    assert project is not None
    os.environ["JIUWENSWARM_LIVE_VOICE_P3_PROJECT_IDS"] = f"{source['project_id']},{project.project_id}"
    cases = [
        ("recorded-flight", Path(source["project"]), source["project_id"], flight_instruction),
        ("maintenance", second, project.project_id,
         "读取 facts.json，按其中指定的计划开始时刻选择可行且成本最低的维护方案。资源窗口固定，"
         "完整验证缓冲必须计入，不执行维护、采购或消息发送。结果保存为 `maintenance.json`："
         "selected_option 为 A、B 或 null，options 按 A/B 分别记录 feasible 布尔值与 finish 时间(HH:MM)。"
         "另保存一份计算说明，文件的字面名称就是《资源.md》，其中的两个书名号确实是文件名字符。"),
    ]
    for label, path, project_id, _ in cases:
        init_session_metadata(session_id=f"quality-{label}", channel_id="web",
                              user_id=env["JIUWENSWARM_LIVE_VOICE_P3_PRINCIPAL_ID"], mode="code",
                              project_dir=str(path), project_id=project_id, work_mode="code")
    manager = AgentManager()
    owner = BoundedP3ConfirmationOwner(root / "confirmations.sqlite3", enabled=True)
    forwarder = ProductP3ConfirmationForwarder(owner)
    composition = create_p3_composition_from_environment(
        agent_manager=manager,
        model_resolver=ServerModelCatalogResolver(
            catalog_reader=AgentWebSocketServer._live_voice_p3_model_catalog,
            model_builder=AgentWebSocketServer._build_live_voice_p3_model),
        confirmation_verifier=forwarder,
    )
    assert composition is not None
    report = {"boundary": "real background Task and artifact quality", "audio": False,
              "recorded_input_sha256": digest(options.recorded_journey),
              "source_manifest_sha256": digest(root / "source.json"), "cases": []}
    deadline = time.monotonic() + 600

    async def check(case):
        label, path, project_id, instruction = case
        result = {"case": label, "status": "FAIL", "project": str(path)}
        source_file = path / ("资料.md" if label == "recorded-flight" else "facts.json")
        before = digest(source_file)
        try:
            stamp = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
            created = await _confirmed_mutation(
                composition=composition, confirmation_owner=owner, confirmation_forwarder=forwarder,
                operation="task.create", request_id=f"quality-create-{label}",
                session_id=f"quality-{label}", run_id=label, deadline=deadline,
                params={"auth_token": env["JIUWENSWARM_LIVE_VOICE_P3_AUTH_TOKEN"],
                        "session_id": f"quality-{label}", "command_id": f"quality-command-{label}",
                        "issued_at": stamp, "correlation_id": f"quality-correlation-{label}",
                        "name": label, "instruction": instruction, "source": "structured"})
            task_id = created["task_id"]
            scope = ScopeRef(env["JIUWENSWARM_LIVE_VOICE_P3_PRINCIPAL_ID"], project_id,
                             f"quality-{label}", Assurance.AUTHENTICATED)
            while True:
                task = composition._core.store.get_task(task_id, scope)
                if task.state.value == "terminal":
                    break
                if time.monotonic() > deadline:
                    raise TimeoutError("real task deadline")
                await asyncio.sleep(1)
            result.update(task_id=task_id, attempt_id=task.attempt_id, outcome=task.outcome.value)
            assert task.outcome.value == "completed"
            assert task.spec.instruction == instruction, "Task spec was changed"
            _, sealed, _ = composition._core.store.task_result(task_id, scope)
            assert sealed is not None
            result["artifacts"] = [a.to_dict() for a in sealed.artifacts]
            for artifact in sealed.artifacts:
                actual = (path / artifact.relative_path).resolve()
                assert actual.is_relative_to(path.resolve()) and digest(actual) == artifact.sha256
            assert digest(source_file) == before
            if label == "recorded-flight":
                assert {a.relative_path for a in sealed.artifacts} == {"出行方案.md"}
                result["business_review"] = "requires reading the actual report for feasibility"
            else:
                assert {a.relative_path for a in sealed.artifacts} == {"maintenance.json", "《资源.md》"}
                actual = json.loads((path / "maintenance.json").read_text(encoding="utf-8"))
                assert actual["selected_option"] == "B", actual
                assert actual["options"]["A"] == {"feasible": False, "finish": "12:35"}, actual
                assert actual["options"]["B"] == {"feasible": True, "finish": "12:30"}, actual
                result["business_review"] = "PASS: violation rejected, exact boundary accepted, literal path preserved"
            result["status"] = "PASS"
        except Exception as error:
            result["error"] = f"{type(error).__name__}: {error}"
        report["cases"].append(result)
        (root / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False), flush=True)

    try:
        await composition.start()
        await asyncio.gather(*(check(case) for case in cases))
    finally:
        await composition.stop()
        report["owned_workers_stopped"] = not composition._core.executor.has_live_workers
        report["configuration_unchanged"] = all(digest(options.config / name) == source[key] for name, key in (
            ("config.yaml", "configuration_sha256"), (".env", "configuration_env_sha256")))
        (root / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if all(c["status"] == "PASS" for c in report["cases"]) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--recorded-journey", required=True, type=Path)
    raise SystemExit(asyncio.run(run(parser.parse_args())))
