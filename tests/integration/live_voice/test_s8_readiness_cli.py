# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "live_voice" / "s8_readiness.py"
SPEC = importlib.util.spec_from_file_location("s8_readiness_cli_integration", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
s8 = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = s8
SPEC.loader.exec_module(s8)


def _run(cwd: Path, *argv: str, env: dict[str, str] | None = None) -> str:
    completed = subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        shell=False,
        timeout=30,
    )
    return completed.stdout.strip()


def _invoke(
    cwd: Path, *argv: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        shell=False,
        timeout=30,
    )


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _valid_s7_checks(head: str, runtime: dict[str, object]) -> list[dict[str, object]]:
    checks = [
        {
            "check_id": check_id,
            "category": "automation",
            "status": "PASS",
            "duration_ms": 1,
            "exit_code": 0,
            "reason": None,
            "details": {},
            "command": ["test:automation"],
            "cwd": ".",
        }
        for check_id in sorted(s8.REQUIRED_AUTOMATION_CHECKS)
    ]
    production_build = next(
        item for item in checks if item["check_id"] == "frontend-production-build"
    )
    production_build["details"] = {
        "vite_modules": 1,
        "artifact_schema": s8._FRONTEND_BUILD_SCHEMA,
        "artifact_file_count": 1,
        "artifact_total_bytes": 16,
        "artifact_manifest_sha256": "sha256:" + "a" * 64,
        "artifact_entrypoint_sha256": "sha256:" + "b" * 64,
    }
    candidate_after = next(
        item for item in checks if item["check_id"] == "candidate-identity-after-run"
    )
    candidate_after["details"] = {
        "head_unchanged": True,
        "upstream_unchanged": True,
        "dependencies_unchanged": True,
        "frontend_build_unchanged": True,
        "clean": True,
    }
    runtime_sha = s8._runtime_declaration_sha(runtime)
    checks.extend(
        {
            "check_id": check_id,
            "category": "real-path",
            "status": "VERIFY",
            "duration_ms": 1,
            "exit_code": 0,
            "reason": None,
            "details": {
                "probe_candidate_head": head,
                "probe_check_id": check_id,
                "probe_failure_count": 0,
                "probe_outcome": "PASS",
                "probe_runtime_declaration_sha256": runtime_sha,
                "probe_sample_count": 1,
                "probe_zero_forbidden_effects": True,
                "sanitized_result_count": 1,
                **(
                    {
                        "probe_p50_ms": 1.0,
                        "probe_p95_ms": 2.0,
                        "probe_max_ms": 3.0,
                    }
                    if check_id in s8.REAL_LATENCY_CHECKS
                    else {}
                ),
            },
            "command": ["test:real-probe"],
            "cwd": ".",
        }
        for check_id in sorted(s8.REQUIRED_REAL_CHECKS)
    )
    return checks


def test_fixture_cli_round_trip_is_external_sanitized_and_read_only(
    tmp_path: Path,
) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    _run(candidate, "git", "init", "--initial-branch=main")
    (candidate / "README.md").write_text("candidate\n", encoding="utf-8")
    _run(candidate, "git", "add", "README.md")
    _run(
        candidate,
        "git",
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test.invalid",
        "commit",
        "-m",
        "initial",
    )

    data = tmp_path / "isolated-runtime"
    data.mkdir()
    fixture = tmp_path / "live-voice-s8-fixture-cli"
    session_id = "s8-cli-round-trip"
    command = (sys.executable, str(SCRIPT), "--repo", str(candidate))

    scope_file = tmp_path / "operator-private-scope-correlations.json"
    scope_result = _run(
        ROOT,
        *command,
        "init-scope-correlations",
        "--session-id",
        session_id,
        "--output",
        str(scope_file),
        env={**os.environ, "S8_PRODUCT_SESSION_ID": "product-session-cli"},
    )
    scope_binding = json.loads(scope_file.read_text(encoding="utf-8"))
    scope_values = scope_binding["correlations"]
    assert scope_result == "S8_PRIVATE_SCOPE_CORRELATIONS_CREATED"
    assert scope_binding["schema_version"] == s8.PRODUCT_BINDING_SCHEMA
    assert scope_binding["product_session_ref"].startswith("product_session_ref:")
    assert set(scope_values) == set(s8._TRACE_SCOPE_RULES)
    assert len(set(scope_values.values())) == len(scope_values)
    assert not any(value in scope_result for value in scope_values.values())

    created = _run(
        ROOT,
        *command,
        "init-fixture",
        "--root",
        str(fixture),
        "--session-id",
        session_id,
        "--execute",
    )
    assert created.startswith("S8_FIXTURE_CREATED disposable_git_ref:sha256-")
    assert str(fixture) not in created
    assert _run(fixture, "git", "remote") == ""

    env = {
        **os.environ,
        "JIUWENSWARM_DATA_DIR": str(data),
        "S8_DISPOSABLE_PROJECT_ROOT": str(fixture),
    }
    refs = json.loads(
        _run(
            ROOT,
            *command,
            "resource-refs",
            "--session-id",
            session_id,
            env=env,
        )
    )
    assert refs["data_fixture"].startswith("data_ref:sha256-")
    assert refs["project_fixture"].endswith(":no_remote")
    assert str(tmp_path) not in json.dumps(refs)

    effect_plan = tmp_path / "operator-private-effect-plan.json"
    planned = _run(
        ROOT,
        *command,
        "plan-fixture-effect",
        "--session-id",
        session_id,
        "--expected-path",
        "created.txt",
        "--output",
        str(effect_plan),
        env=env,
    )
    assert planned == "S8_FIXTURE_EFFECT_PLAN_CREATED"
    plan_payload = json.loads(effect_plan.read_text(encoding="utf-8"))
    assert plan_payload["expected_changed_paths"] == ["created.txt"]

    initial = json.loads(
        _run(
            ROOT,
            *command,
            "fixture-effect",
            "--session-id",
            session_id,
            env=env,
        )
    )
    assert initial["observed_changed_paths"] == []

    (fixture / "created.txt").write_text("showcase effect\n", encoding="utf-8")
    changed = json.loads(
        _run(
            ROOT,
            *command,
            "fixture-effect",
            "--session-id",
            session_id,
            env=env,
        )
    )
    assert changed["observed_changed_paths"] == ["created.txt"]
    assert changed["diff_sha256"] != initial["diff_sha256"]
    assert _run(candidate, "git", "status", "--porcelain=v1") == ""


def test_bound_cli_paths_validate_and_fail_closed_without_private_runtime(
    tmp_path: Path,
) -> None:
    candidate = tmp_path / "candidate"
    remote = tmp_path / "candidate-remote.git"
    private = tmp_path / "operator-private"
    data = tmp_path / "isolated-runtime"
    candidate.mkdir()
    private.mkdir()
    data.mkdir()
    store = data / "formal_tasks.sqlite3"
    store.write_bytes(b"sqlite-fixture")
    _run(candidate, "git", "init", "--initial-branch=main")
    (candidate / "README.md").write_text("candidate\n", encoding="utf-8")
    _run(candidate, "git", "add", "README.md")
    _run(
        candidate,
        "git",
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test.invalid",
        "commit",
        "-m",
        "initial",
    )
    _run(tmp_path, "git", "init", "--bare", str(remote))
    _run(candidate, "git", "remote", "add", "origin", str(remote))
    _run(candidate, "git", "push", "-u", "origin", "main")
    head = _run(candidate, "git", "rev-parse", "HEAD")
    session_id = "s8-cli-bound-session"
    fixture = tmp_path / "live-voice-s8-fixture-bound-cli"
    command = (sys.executable, str(SCRIPT), "--repo", str(candidate))
    created = _run(
        ROOT,
        *command,
        "init-fixture",
        "--root",
        str(fixture),
        "--session-id",
        session_id,
        "--execute",
    )
    fixture_ref = created.removeprefix("S8_FIXTURE_CREATED ")
    labels = {
        "agent_provider": "jiuwenswarm",
        "browser": "Chrome-151.0.7922.137",
        "operating_system": "Windows-11-build-10.0.26100",
        "origin": s8._private_origin_ref("https://voice.private.test"),
        "input_device": "device_ref:sha256-" + "1" * 32,
        "output_device": "device_ref:sha256-" + "2" * 32,
        "network_profile": "network_ref:sha256-" + "3" * 32,
        "speech_provider": "openai",
        "speech_api_origin": "https://api.openai.com/v1",
        "speech_fallback": "streaming-w2-batch-browser-text",
        "stt_model": "gpt-4o-mini-transcribe-2025-12-15",
        "tts_model": "gpt-4o-mini-tts-2025-12-15",
        "tts_voice": "marin",
        "executor": "DirectProjectCodeExecutorAdapter",
        "project_fixture": fixture_ref,
        "data_fixture": s8._path_ref("data", data),
        "deployment_topology": "private-same-origin-https-wss",
    }
    runtime = {
        "candidate_head": head,
        "comparison_base": head,
        "feature_flags": {"FLAG_UNSET": "unset"},
        "runtime_labels": labels,
    }
    report = {
        "schema_version": s8.S7_REPORT_SCHEMA,
        "generated_at": "2026-08-13T12:00:00+00:00",
        "not_a_gate": True,
        "candidate": {
            "head": head,
            "branch": "main",
            "comparison_base": head,
            "upstream": "origin/main",
            "upstream_head": head,
            "ahead": 0,
            "behind": 0,
            "clean": True,
            "dependency_sha256": {
                "README.md": s8._sha256_file(candidate / "README.md").removeprefix(
                    "sha256:"
                )
            },
            "generated_artifact_state": {
                "policy": "generated-output-excluded-from-candidate",
                "tracked_count": "0",
                "tracked_sha256": hashlib.sha256(b"").hexdigest(),
            },
            "python": "3.13.14",
            "node": "v24.6.0",
            "npm": "11.5.1",
            "uv": "uv 0.8.8",
            "platform": "Windows-11",
        },
        "runtime_declaration": runtime,
        "automation_status": "PASS",
        "real_path_status": "VERIFY",
        "s7_readiness": "READY_FOR_S7_CUMULATIVE_REVIEW",
        "checks": _valid_s7_checks(head, runtime),
    }
    report_path = private / "s7-report.json"
    handoff_path = private / "s7-handoff.json"
    _write_json(report_path, report)
    handoff = {
        "schema_version": s8.S7_HANDOFF_SCHEMA,
        "candidate_head": head,
        "comparison_base": head,
        "s7_report_sha256": s8._sha256_bytes(report_path.read_bytes()),
        "runtime_declaration_sha256": s8._runtime_declaration_sha(runtime),
        "s7_03_review": "PASS",
        "s7_04_status": "FROZEN_FOR_A3",
        "known_deviation_ids": [],
        "reused_human_observation_ids": [],
    }
    _write_json(handoff_path, handoff)
    effect_plan_path = private / "fixture-effect-plan.json"
    fixture_env = {
        **os.environ,
        "S8_DISPOSABLE_PROJECT_ROOT": str(fixture),
    }
    assert (
        _run(
            ROOT,
            *command,
            "plan-fixture-effect",
            "--session-id",
            session_id,
            "--output",
            str(effect_plan_path),
            env=fixture_env,
        )
        == "S8_FIXTURE_EFFECT_PLAN_CREATED"
    )
    product_trace_path = private / "product-trace.json"
    trace_manifest_path = private / "trace-manifest.json"
    product_session_id = "product-session-cli"
    product_binding_path = private / "product-binding.json"
    assert (
        _run(
            ROOT,
            *command,
            "init-scope-correlations",
            "--session-id",
            session_id,
            "--output",
            str(product_binding_path),
            env={**os.environ, "S8_PRODUCT_SESSION_ID": product_session_id},
        )
        == "S8_PRIVATE_SCOPE_CORRELATIONS_CREATED"
    )
    product_binding = json.loads(product_binding_path.read_text(encoding="utf-8"))
    product_correlations = product_binding["correlations"]
    product_scope_correlation_refs = {
        scope: s8._product_context_ref("correlation", value)
        for scope, value in product_correlations.items()
    }
    assert product_binding["product_session_ref"] == s8._product_context_ref(
        "session", product_session_id
    )
    _write_json(
        product_trace_path,
        {
            "schema_version": s8.PRODUCT_TRACE_SCHEMA,
            "candidate_head": head,
            "runtime_declaration_sha256": handoff["runtime_declaration_sha256"],
            "session_id": session_id,
            "product_session_id": product_session_id,
            "records": [],
        },
    )
    effect_plan = json.loads(effect_plan_path.read_text(encoding="utf-8"))
    observed_effect = s8.inspect_fixture_effect(
        repo=candidate, session_id=session_id, env=fixture_env
    )
    record = {
        "schema_version": s8.SESSION_SCHEMA,
        "not_acceptance_authority": True,
        "session_id": session_id,
        "candidate_head": head,
        "runtime_declaration_sha256": handoff["runtime_declaration_sha256"],
        "s7_handoff_sha256": s8._canonical_json_sha(handoff),
        "fixture_effect_plan_sha256": s8._sha256_bytes(effect_plan_path.read_bytes()),
        "product_binding_sha256": s8._sha256_bytes(product_binding_path.read_bytes()),
        "product_session_ref": s8._product_context_ref("session", product_session_id),
        "product_scope_correlation_refs": product_scope_correlation_refs,
        "identities": {},
        "observations": s8._new_observations(),
        "processes": [
            {
                "service": service,
                "port": port,
                "pid": 90_100_000 + index,
                "process_ref": "process_ref:sha256-" + str(index) * 64,
                "candidate_head": head,
            }
            for index, (service, port) in enumerate(
                {
                    "agentserver": 18092,
                    "webchannel": 19000,
                    "gateway": 19001,
                    s8.PRIVATE_PROXY_SERVICE: s8.PRIVATE_PROXY_PORT,
                }.items(),
                start=1,
            )
        ],
        "project_effect": {
            "fixture_ref": fixture_ref,
            "base_head": effect_plan["base_head"],
            "expected_changed_paths": [],
            "diff_sha256": observed_effect["diff_sha256"],
            "cleanup_action": "PRESERVE",
        },
        "task_settle": [],
        "private_artifacts": [],
        "decision": {
            "outcome": "BLOCKED",
            "decided_by": "USER",
            "reason_codes": ["USER_OBSERVATION_REQUIRED"],
        },
    }
    record_path = private / "session.json"
    _write_json(record_path, record)
    assert (
        _run(
            ROOT,
            *command,
            "capture-trace",
            "--s7-report",
            str(report_path),
            "--handoff",
            str(handoff_path),
            "--product-binding",
            str(product_binding_path),
            "--record",
            str(record_path),
            "--product-trace",
            str(product_trace_path),
            "--output",
            str(trace_manifest_path),
        )
        == "S8_TRACE_MANIFEST_CAPTURED"
    )
    bound_args = (
        "--s7-report",
        str(report_path),
        "--handoff",
        str(handoff_path),
        "--effect-plan",
        str(effect_plan_path),
        "--product-binding",
        str(product_binding_path),
        "--product-trace",
        str(product_trace_path),
        "--trace-manifest",
        str(trace_manifest_path),
        "--record",
        str(record_path),
    )
    validated = _invoke(ROOT, *command, "validate-session", *bound_args)
    assert validated.returncode == 0
    assert validated.stdout.strip() == "S8_SESSION_RECORD_VALID"

    preflight_report = private / "preflight.json"
    preflight = _invoke(
        ROOT,
        *command,
        "preflight",
        "--session-id",
        session_id,
        "--s7-report",
        str(report_path),
        "--handoff",
        str(handoff_path),
        "--report",
        str(preflight_report),
    )
    assert preflight.returncode == 2
    assert preflight.stdout.strip() == "S8_PREFLIGHT_BLOCKED"
    assert json.loads(preflight_report.read_text(encoding="utf-8"))["status"] == (
        "BLOCKED"
    )
    session_output = private / "must-not-exist.json"
    initialized = _invoke(
        ROOT,
        *command,
        "init-session",
        "--session-id",
        session_id,
        "--s7-report",
        str(report_path),
        "--handoff",
        str(handoff_path),
        "--effect-plan",
        str(effect_plan_path),
        "--product-binding",
        str(product_binding_path),
        "--output",
        str(session_output),
    )
    assert initialized.returncode == 2
    assert initialized.stderr.strip() == "S8_READINESS_BLOCKED RUNTIME_ROUTE_MISMATCH"
    assert not session_output.exists()
    cleanup_report = private / "cleanup.json"
    cleaned = _invoke(
        ROOT,
        *command,
        "cleanup",
        *bound_args,
        "--report",
        str(cleanup_report),
    )
    assert cleaned.returncode == 2
    assert cleaned.stderr.strip() == "S8_READINESS_BLOCKED RUNTIME_ROUTE_MISMATCH"
    assert not cleanup_report.exists()

    secret = "private-shell-value-never-echo"
    rejected = _invoke(
        ROOT,
        *command,
        "preflight",
        "--run-arbitrary",
        secret,
    )
    assert rejected.returncode == 2
    assert secret not in rejected.stdout + rejected.stderr
    rendered_private = "".join(
        path.read_text(encoding="utf-8") for path in private.iterdir() if path.is_file()
    )
    assert secret not in rendered_private
    assert str(tmp_path) not in rendered_private
