# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import psutil
import pytest


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "live_voice" / "s8_readiness.py"
SPEC = importlib.util.spec_from_file_location("s8_readiness", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
s8 = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = s8
SPEC.loader.exec_module(s8)


def _run(cwd: Path, *argv: str) -> str:
    completed = subprocess.run(
        argv,
        cwd=cwd,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        shell=False,
    )
    return completed.stdout.strip()


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


@dataclass
class Context:
    repo: Path
    fixture: Path
    data: Path
    report_path: Path
    handoff_path: Path
    effect_plan_path: Path
    product_binding_path: Path
    product_trace_path: Path
    trace_manifest_path: Path
    trace_record_path: Path
    report: dict[str, object]
    handoff: dict[str, object]
    env: dict[str, str]
    session_id: str


def _rewrite_bound_files(context: Context) -> None:
    _write_json(context.report_path, context.report)
    context.handoff["candidate_head"] = context.report["candidate"]["head"]
    context.handoff["comparison_base"] = context.report["candidate"]["comparison_base"]
    context.handoff["s7_report_sha256"] = s8._sha256_bytes(
        context.report_path.read_bytes()
    )
    context.handoff["runtime_declaration_sha256"] = s8._runtime_declaration_sha(
        context.report["runtime_declaration"]
    )
    _write_json(context.handoff_path, context.handoff)


def _context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Context:
    tmp_path.mkdir(parents=True, exist_ok=True)
    repo = tmp_path / "candidate"
    remote = tmp_path / "candidate-remote.git"
    private = tmp_path / "operator-private"
    repo.mkdir()
    private.mkdir()
    _run(repo, "git", "init", "--initial-branch=main")
    (repo / "pyproject.toml").write_text(
        "[project]\nname='fixture'\n", encoding="utf-8"
    )
    _run(repo, "git", "add", "pyproject.toml")
    _run(
        repo,
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
    _run(repo, "git", "remote", "add", "origin", str(remote))
    _run(repo, "git", "push", "-u", "origin", "main")
    head = _run(repo, "git", "rev-parse", "HEAD")

    session_id = "s8-unit-session"
    fixture = tmp_path / "live-voice-s8-fixture-unit"
    fixture_ref = s8.init_fixture(
        repo=repo, root=fixture, session_id=session_id, execute=True
    )
    data = tmp_path / "isolated-runtime"
    data.mkdir()
    store = data / "formal_tasks.sqlite3"
    store.write_bytes(b"sqlite-fixture")
    origin = "https://voice.private.test"
    labels = {
        "agent_provider": "jiuwenswarm",
        "browser": "Chrome-151.0.7922.137",
        "operating_system": "Windows-11-build-10.0.26100",
        "origin": s8._private_origin_ref(origin),
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
    flags = {"FLAG_ACTIVE": "true", "FLAG_UNSET": "unset"}
    runtime = {
        "candidate_head": head,
        "comparison_base": head,
        "feature_flags": flags,
        "runtime_labels": labels,
    }
    report: dict[str, object] = {
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
                "pyproject.toml": s8._sha256_file(repo / "pyproject.toml").removeprefix(
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
        "checks": [
            {"check_id": check_id, "category": "real-path", "status": "VERIFY"}
            for check_id in sorted(s8.REQUIRED_REAL_CHECKS)
        ],
    }
    report_path = private / "s7-report.json"
    _write_json(report_path, report)
    handoff: dict[str, object] = {
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
    handoff_path = private / "handoff.json"
    _write_json(handoff_path, handoff)
    env = {
        "FLAG_ACTIVE": "true",
        **{
            env_name: labels[label]
            for label, env_name in s8.RUNTIME_ENV_BY_LABEL.items()
        },
        "S7_PRIVATE_ORIGIN": origin,
        "LIVE_VOICE_SPEECH_API_KEY": "private-speech-value",
        "JIUWENSWARM_LIVE_VOICE_P3_AUTH_TOKEN": "private-task-value",
        "JIUWENSWARM_DATA_DIR": str(data),
        "S8_TASK_STORE_PATH": str(store),
        "S8_DISPOSABLE_PROJECT_ROOT": str(fixture),
        "S8_PRODUCT_SESSION_ID": "product-session-unit",
        "AGENT_SERVER_PORT": "18092",
        "WEB_PORT": "19000",
        "GATEWAY_PORT": "19001",
        "FRONTEND_PORT": "5173",
    }
    effect_plan_path = private / "fixture-effect-plan.json"
    effect_plan = s8.plan_fixture_effect(
        repo=repo,
        session_id=session_id,
        expected_changed_paths=[],
        env=env,
    )
    _write_json(effect_plan_path, effect_plan)
    product_binding_path = private / "product-binding.json"
    _write_json(
        product_binding_path,
        {
            "schema_version": s8.PRODUCT_BINDING_SCHEMA,
            "session_id": session_id,
            "product_session_ref": s8._product_context_ref(
                "session", env["S8_PRODUCT_SESSION_ID"]
            ),
            "correlations": {
                scope: f"product-correlation-{scope}" for scope in s8._TRACE_SCOPE_RULES
            },
        },
    )
    product_trace_path = private / "product-trace.json"
    trace_manifest_path = private / "trace-manifest.json"
    trace_record_path = private / "trace-session-source.json"
    monkeypatch.setattr(
        s8.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (s8.socket.AF_INET, s8.socket.SOCK_STREAM, 6, "", ("10.20.30.40", 443))
        ],
    )
    monkeypatch.setattr(s8, "_validate_private_route", lambda _origin: None)
    monkeypatch.setattr(
        s8,
        "_capture_service_processes",
        lambda _env, **_kwargs: [
            {
                "service": service,
                "port": int(env[env_name]),
                "pid": 90_000_000 + index,
                "process_ref": "process_ref:sha256-" + str(index) * 64,
                "candidate_head": head,
            }
            for index, (service, env_name) in enumerate(
                s8.SERVICE_PORT_ENV.items(), start=1
            )
        ],
    )
    return Context(
        repo=repo,
        fixture=fixture,
        data=data,
        report_path=report_path,
        handoff_path=handoff_path,
        effect_plan_path=effect_plan_path,
        product_binding_path=product_binding_path,
        product_trace_path=product_trace_path,
        trace_manifest_path=trace_manifest_path,
        trace_record_path=trace_record_path,
        report=report,
        handoff=handoff,
        env=env,
        session_id=session_id,
    )


def _preflight(context: Context, monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    monkeypatch.setattr(s8, "_port_open", lambda *_args, **_kwargs: True)
    return s8.run_preflight(
        repo=context.repo,
        s7_report_path=context.report_path,
        handoff_path=context.handoff_path,
        session_id=context.session_id,
        env=context.env,
    )


def _product_observation(scope: str, sequence: int) -> dict[str, object]:
    event_name, segment_name, sources, route_classes = s8._TRACE_SCOPE_RULES[scope]
    route_class = sorted(route_classes)[0]
    route_reason = {
        "fallback": "ROUTE_FALLBACK",
        "unsupported": "UNSUPPORTED_CAPABILITY",
    }.get(route_class)
    source_component = sorted(sources)[0]
    observation: dict[str, object] = {
        "schema_version": "live-voice.observability.v1",
        "event_id": f"event-{scope}",
        "event_name": event_name,
        "segment_name": segment_name,
        "observed_at": f"2026-08-13T12:00:{sequence:02d}Z",
        "monotonic_ms": float(sequence),
        "binding": {
            "correlation_id": f"product-correlation-{scope}",
            "interaction_id": f"interaction-{scope}",
            "turn_id": f"turn-{scope}",
            "response_id": f"response-{scope}",
            "response_generation": 0,
            "round_id": f"round-{scope}",
            "task_id": f"task-{scope}",
            "attempt_id": f"attempt-{scope}",
        },
        "route": {
            "implementation_class": route_class,
            "owner_module": source_component,
            "capability_provider": (
                "jiuwenswarm-agent" if route_class == "formal" else None
            ),
            "contract_version": (
                "live-voice.contract.v2" if route_class == "formal" else None
            ),
            "reason_code": route_reason,
        },
        "source_component": source_component,
        "source_event_id": None,
        "source_record_id": f"work-{scope}",
        "source_occurred_at": None,
        "source_seq": sequence,
        "state": None,
        "outcome": None,
        "reason_code": None,
        "error_code": None,
        "duration_ms": None,
        "queue_depth": None,
        "queue_capacity": None,
        "cancel_scope": None,
    }
    if event_name == "segment.completed":
        observation.update(state="terminal", outcome="completed", duration_ms=1.0)
    elif event_name == "speech.capture_state":
        observation["state"] = "active"
    elif event_name == "cancel.terminal":
        observation.update(
            outcome="cancelled",
            reason_code="CANCEL_TERMINAL",
            cancel_scope=(
                "playback.stop"
                if segment_name == "speech.playout"
                else "response.cancel"
            ),
        )
    elif event_name == "task.dispatch_outbox_observed":
        observation["state"] = "pending"
    elif event_name == "task.state_observed":
        observation.update(
            source_event_id=f"source-event-{scope}",
            source_record_id=None,
            source_occurred_at=f"2026-08-13T12:00:{sequence:02d}Z",
            state="terminal",
            outcome="completed",
        )
    elif event_name == "degradation.activated":
        observation["reason_code"] = "DEGRADED"
    elif event_name == "segment.failed":
        observation.update(
            state="failed",
            outcome="failed",
            reason_code="TASK_FAILURE",
            error_code="INTERNAL",
            duration_ms=1.0,
        )
    elif event_name == "speech.playout_state":
        observation["state"] = "stopped"
    return observation


def _complete_record(context: Context, record: dict[str, object]) -> dict[str, object]:
    required_by_scope: dict[str, set[str]] = {}
    for check_id, kinds in s8._OBSERVATION_IDENTITIES.items():
        if kinds:
            required_by_scope.setdefault(
                s8._OBSERVATION_SCOPES[check_id], set()
            ).update(kinds)
    product_trace = {
        "schema_version": s8.PRODUCT_TRACE_SCHEMA,
        "candidate_head": record["candidate_head"],
        "runtime_declaration_sha256": record["runtime_declaration_sha256"],
        "session_id": record["session_id"],
        "product_session_id": context.env["S8_PRODUCT_SESSION_ID"],
        "records": [
            {
                "scope": scope,
                "observation": _product_observation(
                    scope, s8._SCOPE_START_SEQUENCE[scope]
                ),
            }
            for scope, _kinds in sorted(
                required_by_scope.items(),
                key=lambda item: s8._SCOPE_START_SEQUENCE[item[0]],
            )
        ],
    }
    _write_json(context.trace_record_path, record)
    _write_json(context.product_trace_path, product_trace)
    manifest = s8.capture_trace_manifest(
        repo=context.repo,
        s7_report_path=context.report_path,
        handoff_path=context.handoff_path,
        product_binding_path=context.product_binding_path,
        record_path=context.trace_record_path,
        product_trace_path=context.product_trace_path,
    )
    _write_json(context.trace_manifest_path, manifest)
    identities = manifest["identities"]
    assert isinstance(identities, dict)
    pairs: set[tuple[str, str]] = set()
    for sequence, (check_id, kinds) in enumerate(
        s8._OBSERVATION_IDENTITIES.items(), start=1
    ):
        scope = s8._OBSERVATION_SCOPES[check_id]
        bindings: dict[str, str] = {}
        for kind in kinds:
            alias = f"{scope}.{kind}"
            bindings[kind] = alias
        record["observations"][check_id] = {
            "sequence": sequence,
            "status": "PASS",
            "observer": "USER",
            "reason_code": "USER_OBSERVED",
            "identity_bindings": bindings,
        }
        if "task" in bindings and "attempt" in bindings:
            pairs.add(
                (
                    str(identities[bindings["task"]]["ref"]),
                    str(identities[bindings["attempt"]]["ref"]),
                )
            )
    record["identities"] = identities
    record["task_settle"] = [
        {
            "task_ref": task_ref,
            "attempt_ref": attempt_ref,
            "terminal_state": "completed",
            "outbox_state": "settled",
            "owner_state": "released",
            "lease_state": "released",
        }
        for task_ref, attempt_ref in sorted(pairs)
    ]
    record["decision"] = {
        "outcome": "PASS",
        "decided_by": "USER",
        "reason_codes": ["USER_ACCEPTED_COMPLETE_SHOWCASE"],
    }
    return record


def _record(context: Context, monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    fake_processes = [
        {
            "service": service,
            "port": int(context.env[env_name]),
            "pid": 90_000_000 + index,
            "process_ref": "process_ref:sha256-" + str(index) * 64,
            "candidate_head": context.report["candidate"]["head"],
        }
        for index, (service, env_name) in enumerate(
            s8.SERVICE_PORT_ENV.items(), start=1
        )
    ]
    monkeypatch.setattr(s8, "_port_open", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        s8, "_capture_service_processes", lambda _env, **_kwargs: fake_processes
    )
    record = s8.init_session_record(
        repo=context.repo,
        s7_report_path=context.report_path,
        handoff_path=context.handoff_path,
        effect_plan_path=context.effect_plan_path,
        product_binding_path=context.product_binding_path,
        session_id=context.session_id,
        env=context.env,
    )
    _write_json(context.trace_record_path, record)
    _write_json(
        context.product_trace_path,
        {
            "schema_version": s8.PRODUCT_TRACE_SCHEMA,
            "candidate_head": record["candidate_head"],
            "runtime_declaration_sha256": record["runtime_declaration_sha256"],
            "session_id": record["session_id"],
            "product_session_id": context.env["S8_PRODUCT_SESSION_ID"],
            "records": [],
        },
    )
    _write_json(
        context.trace_manifest_path,
        s8.capture_trace_manifest(
            repo=context.repo,
            s7_report_path=context.report_path,
            handoff_path=context.handoff_path,
            product_binding_path=context.product_binding_path,
            record_path=context.trace_record_path,
            product_trace_path=context.product_trace_path,
        ),
    )
    return record


def test_exact_candidate_preflight_is_verify_only_and_redacts_private_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path, monkeypatch)
    result = _preflight(context, monkeypatch)

    assert result["status"] == "AUTOMATED_PREFLIGHT_VERIFIED"
    assert result["not_alpha_acceptance"] is True
    rendered = json.dumps(result)
    assert context.env["LIVE_VOICE_SPEECH_API_KEY"] not in rendered
    assert str(context.fixture) not in rendered
    assert "S8-02.COMPLETE_HUMAN_SHOWCASE" in result["operator_required"]


def test_handoff_draft_is_bound_but_cannot_enter_a3(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path, monkeypatch)
    draft = s8.draft_handoff(repo=context.repo, s7_report_path=context.report_path)
    assert draft["candidate_head"] == context.report["candidate"]["head"]
    assert draft["s7_03_review"] == "BLOCKED"
    assert draft["s7_04_status"] == "NOT_FROZEN"
    _write_json(context.handoff_path, draft)
    result = _preflight(context, monkeypatch)
    assert result["status"] == "BLOCKED"
    assert result["checks"][-1]["reason"] == "S7_HANDOFF_NOT_FROZEN"


def test_resource_refs_are_sanitized_and_bound_to_owned_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path, monkeypatch)
    refs = s8.resource_refs(
        repo=context.repo, session_id=context.session_id, env=context.env
    )
    rendered = json.dumps(refs)
    assert refs["project_fixture"].endswith(":no_remote")
    assert str(context.fixture) not in rendered
    assert str(context.data) not in rendered


def test_wrong_head_and_dirty_worktree_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path, monkeypatch)
    (context.repo / "next.txt").write_text("next\n", encoding="utf-8")
    _run(context.repo, "git", "add", "next.txt")
    _run(
        context.repo,
        "git",
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test.invalid",
        "commit",
        "-m",
        "next",
    )
    result = _preflight(context, monkeypatch)
    assert result["status"] == "BLOCKED"
    assert result["checks"][-1]["reason"] == "CANDIDATE_IDENTITY_MISMATCH"

    _run(context.repo, "git", "reset", "--hard", context.report["candidate"]["head"])
    (context.repo / "dirty.txt").write_text("dirty\n", encoding="utf-8")
    result = _preflight(context, monkeypatch)
    assert result["status"] == "BLOCKED"
    assert result["checks"][-1]["reason"] == "CANDIDATE_IDENTITY_MISMATCH"


def test_candidate_change_after_check_is_detected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path, monkeypatch)
    monkeypatch.setattr(s8, "_port_open", lambda *_args, **_kwargs: True)
    original = s8._candidate_snapshot
    calls = 0

    def changing(repo: Path, candidate: dict[str, object]) -> dict[str, object]:
        nonlocal calls
        calls += 1
        value = original(repo, candidate)
        if calls == 2:
            value = {**value, "head": "f" * 40}
        return value

    monkeypatch.setattr(s8, "_candidate_snapshot", changing)
    result = s8.run_preflight(
        repo=context.repo,
        s7_report_path=context.report_path,
        handoff_path=context.handoff_path,
        session_id=context.session_id,
        env=context.env,
    )
    assert result["status"] == "BLOCKED"
    assert result["checks"][-1]["reason"] == "CANDIDATE_CHANGED_AFTER_CHECK"


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("automation_status", "NOT_RUN", "S7_AUTOMATION_INCOMPLETE"),
        ("real_path_status", "PARTIAL", "S7_REAL_PATH_INCOMPLETE"),
        ("s7_readiness", "PARTIAL_AUTOMATION_ONLY", "S7_READINESS_INCOMPLETE"),
    ],
)
def test_incomplete_s7_status_never_enters_a3(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: str,
    reason: str,
) -> None:
    context = _context(tmp_path, monkeypatch)
    context.report[field] = value
    _rewrite_bound_files(context)
    result = _preflight(context, monkeypatch)
    assert result["status"] == "BLOCKED"
    assert result["checks"][-1]["reason"] == reason


@pytest.mark.parametrize("value", ["TRUE", "yes", "", "false"])
def test_active_flag_requires_exact_raw_true(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    context = _context(tmp_path, monkeypatch)
    context.env["FLAG_ACTIVE"] = value
    result = _preflight(context, monkeypatch)
    assert result["status"] == "BLOCKED"
    assert result["checks"][-1]["reason"] == "FEATURE_FLAG_MISMATCH"


def test_unset_flag_means_variable_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path, monkeypatch)
    context.env["FLAG_UNSET"] = ""
    result = _preflight(context, monkeypatch)
    assert result["status"] == "BLOCKED"
    assert result["checks"][-1]["reason"] == "FEATURE_FLAG_MISMATCH"


def test_missing_environment_is_content_free_and_secret_is_not_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path, monkeypatch)
    secret = context.env.pop("LIVE_VOICE_SPEECH_API_KEY")
    result = _preflight(context, monkeypatch)
    rendered = json.dumps(result)
    assert result["status"] == "BLOCKED"
    assert result["checks"][-1]["reason"] == "REQUIRED_PRIVATE_INPUT_MISSING"
    assert secret not in rendered
    assert "LIVE_VOICE_SPEECH_API_KEY" not in rendered


def test_private_runtime_label_and_public_origin_are_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path, monkeypatch)
    private_label = str(tmp_path / "private-browser-profile")
    context.report["runtime_declaration"]["runtime_labels"]["browser"] = private_label
    context.env["S8_BROWSER_LABEL"] = private_label
    _rewrite_bound_files(context)
    result = _preflight(context, monkeypatch)
    assert result["checks"][-1]["reason"] == "S7_RUNTIME_LABEL_PRIVATE"

    context = _context(tmp_path / "public", monkeypatch)
    public_origin = "https://public.example.com"
    labels = context.report["runtime_declaration"]["runtime_labels"]
    labels["origin"] = s8._private_origin_ref(public_origin)
    context.env["S7_PRIVATE_ORIGIN"] = public_origin
    monkeypatch.setattr(
        s8.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (s8.socket.AF_INET, s8.socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))
        ],
    )
    _rewrite_bound_files(context)
    result = _preflight(context, monkeypatch)
    assert result["checks"][-1]["reason"] == "PUBLIC_ORIGIN_REJECTED"


def test_wrong_fixture_or_remote_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path, monkeypatch)
    _run(context.fixture, "git", "remote", "add", "origin", str(tmp_path / "remote"))
    result = _preflight(context, monkeypatch)
    assert result["status"] == "BLOCKED"
    assert result["checks"][-1]["reason"] == "FIXTURE_NOT_DISPOSABLE_NO_REMOTE"


def test_port_occupancy_without_private_connection_ack_is_blocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path, monkeypatch)
    monkeypatch.setattr(s8, "_port_open", lambda *_args, **_kwargs: True)

    def no_ack(_origin: str) -> None:
        raise s8.ReadinessError("PRIVATE_ROUTE_CONNECTION_ACK_MISSING")

    monkeypatch.setattr(s8, "_validate_private_route", no_ack)
    result = s8.run_preflight(
        repo=context.repo,
        s7_report_path=context.report_path,
        handoff_path=context.handoff_path,
        session_id=context.session_id,
        env=context.env,
    )

    assert result["status"] == "BLOCKED"
    assert result["checks"][-1]["reason"] == "PRIVATE_ROUTE_CONNECTION_ACK_MISSING"


def test_private_route_rejects_connect_src_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Response:
        status = 200

        def read(self, _size: int) -> bytes:
            return b"ok"

        def getheader(self, name: str, default: str = "") -> str:
            if name == "Content-Security-Policy":
                return "default-src 'self'; connect-src 'none'"
            return default

    class Connection:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def request(self, *_args: object, **_kwargs: object) -> None:
            pass

        def getresponse(self) -> Response:
            return Response()

        def close(self) -> None:
            pass

    monkeypatch.setattr(s8.http.client, "HTTPSConnection", Connection)

    with pytest.raises(
        s8.ReadinessError, match="PRIVATE_ROUTE_SECURITY_HEADERS_INVALID"
    ):
        s8._validate_private_route("https://voice.private.test")


def test_listener_process_outside_candidate_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_capture = s8._capture_service_processes
    context = _context(tmp_path, monkeypatch)
    monkeypatch.setattr(s8, "_capture_service_processes", real_capture)
    listeners = [
        SimpleNamespace(
            status="LISTEN", laddr=SimpleNamespace(port=int(context.env[name])), pid=42
        )
        for name in s8.SERVICE_PORT_ENV.values()
    ]
    monkeypatch.setattr(psutil, "net_connections", lambda **_kwargs: listeners)

    class OutsideProcess:
        def __init__(self, _pid: int) -> None:
            pass

        def cwd(self) -> str:
            return str(tmp_path)

    monkeypatch.setattr(psutil, "Process", OutsideProcess)
    with pytest.raises(s8.ReadinessError, match="SERVICE_PROCESS_OUTSIDE_CANDIDATE"):
        s8._capture_service_processes(
            context.env,
            repo=context.repo,
            candidate_head=str(context.report["candidate"]["head"]),
        )


def test_arbitrary_cli_argv_is_rejected_without_echo(
    capsys: pytest.CaptureFixture[str],
) -> None:
    parser = s8._build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["preflight", "--run-arbitrary", "private-shell-value"])
    captured = capsys.readouterr()
    assert "private-shell-value" not in captured.err
    assert "CLI_ARGUMENT_INVALID" in captured.err


def test_session_rejects_stale_identity_and_fake_human_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path, monkeypatch)
    record = _complete_record(context, _record(context, monkeypatch))
    s8._validate_session_record(
        record, trace_identities=record["identities"], final=True
    )

    stale = copy.deepcopy(record)
    stale["observations"]["S8-02.P1.CRITICAL_COMMIT"]["identity_bindings"][
        "response"
    ] = "missing.response"
    with pytest.raises(s8.ReadinessError, match="STALE_OBSERVATION_IDENTITY"):
        s8._validate_session_record(
            stale, trace_identities=record["identities"], final=True
        )

    fake = copy.deepcopy(record)
    fake["observations"]["S8-02.P1.HEARD_PLAYOUT"]["observer"] = "AUTOMATION"
    with pytest.raises(
        s8.ReadinessError, match="HUMAN_OBSERVATION_CANNOT_BE_AUTOMATED"
    ):
        s8._validate_session_record(
            fake, trace_identities=record["identities"], final=True
        )


def test_session_enforces_scoped_identities_and_complete_task_settlement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path, monkeypatch)
    record = _complete_record(context, _record(context, monkeypatch))
    structured = record["observations"]["S8-02.P3.STRUCTURED_CREATE_GET_LIST"][
        "identity_bindings"
    ]
    natural = record["observations"]["S8-02.P3.NATURAL_CREATE"]["identity_bindings"]
    assert structured["task"] != natural["task"]
    s8._validate_session_record(
        record, trace_identities=record["identities"], final=True
    )

    wrong_scope = copy.deepcopy(record)
    wrong_scope["observations"]["S8-02.P3.NATURAL_CREATE"]["identity_bindings"][
        "task"
    ] = structured["task"]
    with pytest.raises(s8.ReadinessError, match="STALE_OBSERVATION_IDENTITY"):
        s8._validate_session_record(
            wrong_scope, trace_identities=record["identities"], final=True
        )

    unsettled = copy.deepcopy(record)
    unsettled["task_settle"] = unsettled["task_settle"][:-1]
    with pytest.raises(s8.ReadinessError, match="SESSION_TASK_SETTLE_REQUIRED"):
        s8._validate_session_record(
            unsettled, trace_identities=record["identities"], final=True
        )


def test_bound_product_trace_is_required_and_raw_ids_are_not_persisted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path, monkeypatch)
    record = _complete_record(context, _record(context, monkeypatch))
    record_path = context.report_path.parent / "trace-bound-session.json"
    _write_json(record_path, record)

    loaded, _handoff, _runtime, identities = s8._load_bound_session(
        repo=context.repo,
        s7_report_path=context.report_path,
        handoff_path=context.handoff_path,
        effect_plan_path=context.effect_plan_path,
        product_binding_path=context.product_binding_path,
        product_trace_path=context.product_trace_path,
        trace_manifest_path=context.trace_manifest_path,
        record_path=record_path,
        final=True,
    )
    assert loaded["identities"] == identities
    rendered_manifest = context.trace_manifest_path.read_text(encoding="utf-8")
    assert "work-" not in rendered_manifest
    assert "source_record_id" not in rendered_manifest
    assert all(
        isinstance(item["source_sequence"], int) and item["source_sequence"] >= 0
        for item in identities.values()
    )

    tampered = copy.deepcopy(record)
    alias = next(
        name
        for name, item in tampered["identities"].items()
        if item["kind"] == "response"
    )
    kind = tampered["identities"][alias]["kind"]
    tampered["identities"][alias]["ref"] = f"{kind}_ref:sha256-" + "f" * 64
    _write_json(record_path, tampered)
    with pytest.raises(s8.ReadinessError, match="SESSION_TRACE_IDENTITY_MISMATCH"):
        s8._load_bound_session(
            repo=context.repo,
            s7_report_path=context.report_path,
            handoff_path=context.handoff_path,
            effect_plan_path=context.effect_plan_path,
            product_binding_path=context.product_binding_path,
            product_trace_path=context.product_trace_path,
            trace_manifest_path=context.trace_manifest_path,
            record_path=record_path,
            final=True,
        )


def test_trace_manifest_rejects_product_trace_changed_after_capture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path, monkeypatch)
    record = _complete_record(context, _record(context, monkeypatch))
    record_path = context.report_path.parent / "stale-trace-session.json"
    _write_json(record_path, record)
    trace = json.loads(context.product_trace_path.read_text(encoding="utf-8"))
    trace["records"][-1]["observation"]["source_seq"] += 1
    _write_json(context.product_trace_path, trace)

    with pytest.raises(s8.ReadinessError, match="TRACE_MANIFEST_BINDING_MISMATCH"):
        s8._load_bound_session(
            repo=context.repo,
            s7_report_path=context.report_path,
            handoff_path=context.handoff_path,
            effect_plan_path=context.effect_plan_path,
            product_binding_path=context.product_binding_path,
            product_trace_path=context.product_trace_path,
            trace_manifest_path=context.trace_manifest_path,
            record_path=record_path,
            final=True,
        )

    trace["records"][-1]["observation"]["monotonic_ms"] = trace["records"][-2][
        "observation"
    ]["monotonic_ms"]
    _write_json(context.product_trace_path, trace)
    with pytest.raises(s8.ReadinessError, match="PRODUCT_TRACE_RECORD_ORDER_INVALID"):
        s8.capture_trace_manifest(
            repo=context.repo,
            s7_report_path=context.report_path,
            handoff_path=context.handoff_path,
            product_binding_path=context.product_binding_path,
            record_path=context.trace_record_path,
            product_trace_path=context.product_trace_path,
        )


def test_trace_manifest_rejects_observation_from_another_product_correlation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path, monkeypatch)
    record = _record(context, monkeypatch)
    scope = "text_tool_smoke"
    observation = _product_observation(scope, s8._SCOPE_START_SEQUENCE[scope])
    assert observation["event_name"] == s8._TRACE_SCOPE_RULES[scope][0]
    assert observation["segment_name"] == s8._TRACE_SCOPE_RULES[scope][1]
    observation["binding"]["correlation_id"] = "stale-product-correlation"
    _write_json(
        context.product_trace_path,
        {
            "schema_version": s8.PRODUCT_TRACE_SCHEMA,
            "candidate_head": record["candidate_head"],
            "runtime_declaration_sha256": record["runtime_declaration_sha256"],
            "session_id": record["session_id"],
            "product_session_id": context.env["S8_PRODUCT_SESSION_ID"],
            "records": [{"scope": scope, "observation": observation}],
        },
    )

    with pytest.raises(s8.ReadinessError, match="PRODUCT_TRACE_CORRELATION_MISMATCH"):
        s8.capture_trace_manifest(
            repo=context.repo,
            s7_report_path=context.report_path,
            handoff_path=context.handoff_path,
            product_binding_path=context.product_binding_path,
            record_path=context.trace_record_path,
            product_trace_path=context.product_trace_path,
        )


def test_session_rejects_reused_pre_action_scope_correlation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path, monkeypatch)
    binding = json.loads(context.product_binding_path.read_text(encoding="utf-8"))
    values = binding["correlations"]
    values["p3.natural"] = values["p3.structured"]
    _write_json(context.product_binding_path, binding)

    with pytest.raises(s8.ReadinessError, match="PRODUCT_SCOPE_CORRELATIONS_REUSED"):
        _record(context, monkeypatch)

    rebound = _context(tmp_path / "record", monkeypatch)
    record = _record(rebound, monkeypatch)
    first_scope = next(iter(record["product_scope_correlation_refs"]))
    record["product_scope_correlation_refs"][first_scope] = (
        "product_correlation_ref:sha256-" + "f" * 64
    )
    _write_json(rebound.trace_record_path, record)
    with pytest.raises(s8.ReadinessError, match="SESSION_PRODUCT_BINDING_MISMATCH"):
        s8.capture_trace_manifest(
            repo=rebound.repo,
            s7_report_path=rebound.report_path,
            handoff_path=rebound.handoff_path,
            product_binding_path=rebound.product_binding_path,
            record_path=rebound.trace_record_path,
            product_trace_path=rebound.product_trace_path,
        )


def test_trace_manifest_rejects_observation_relabelled_to_another_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path, monkeypatch)
    record = _record(context, monkeypatch)
    claimed_scope = "p3.structured"
    original_scope = "p3.natural"
    observation = _product_observation(
        original_scope, s8._SCOPE_START_SEQUENCE[claimed_scope]
    )
    _write_json(
        context.product_trace_path,
        {
            "schema_version": s8.PRODUCT_TRACE_SCHEMA,
            "candidate_head": record["candidate_head"],
            "runtime_declaration_sha256": record["runtime_declaration_sha256"],
            "session_id": record["session_id"],
            "product_session_id": context.env["S8_PRODUCT_SESSION_ID"],
            "records": [{"scope": claimed_scope, "observation": observation}],
        },
    )

    with pytest.raises(
        s8.ReadinessError, match="PRODUCT_TRACE_SCOPE_SEMANTICS_MISMATCH"
    ):
        s8.capture_trace_manifest(
            repo=context.repo,
            s7_report_path=context.report_path,
            handoff_path=context.handoff_path,
            product_binding_path=context.product_binding_path,
            record_path=context.trace_record_path,
            product_trace_path=context.product_trace_path,
        )


def test_trace_scope_product_discriminators_are_mutually_exclusive() -> None:
    discriminators = [
        (event_name, segment_name)
        for event_name, segment_name, _sources, _routes in s8._TRACE_SCOPE_RULES.values()
    ]
    assert len(discriminators) == len(set(discriminators))


def test_pass_rejects_all_not_applicable_human_journey(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path, monkeypatch)
    record = _complete_record(context, _record(context, monkeypatch))
    for observation in record["observations"].values():
        observation["status"] = "NOT_APPLICABLE"
        observation["reason_code"] = "USER_MARKED_NOT_APPLICABLE"
        observation["identity_bindings"] = {
            kind: "" for kind in observation["identity_bindings"]
        }
    record["identities"] = {}
    record["task_settle"] = []
    with pytest.raises(s8.ReadinessError, match="SESSION_PASS_REQUIREMENTS_INCOMPLETE"):
        s8._validate_session_record(
            record, trace_identities=record["identities"], final=True
        )


def test_malformed_or_incomplete_decision_record_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path, monkeypatch)
    record = _complete_record(context, _record(context, monkeypatch))
    record["observations"]["S8-02.P2.MULTI_TURN"]["status"] = "BLOCKED"
    with pytest.raises(s8.ReadinessError, match="SESSION_PASS_REQUIREMENTS_INCOMPLETE"):
        s8._validate_session_record(
            record, trace_identities=record["identities"], final=True
        )

    malformed = copy.deepcopy(record)
    del malformed["decision"]
    with pytest.raises(s8.ReadinessError, match="SESSION_RECORD_FIELDS_INVALID"):
        s8._validate_session_record(
            malformed, trace_identities=record["identities"], final=True
        )

    wrong_type = copy.deepcopy(record)
    wrong_type["observations"]["S8-02.P2.MULTI_TURN"]["status"] = []
    with pytest.raises(s8.ReadinessError, match="SESSION_OBSERVATION_STATUS_INVALID"):
        s8._validate_session_record(
            wrong_type, trace_identities=record["identities"], final=True
        )


def test_bounded_process_timeout_and_cancel_clean_descendants(tmp_path: Path) -> None:
    child = tmp_path / "child.py"
    child.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
    parent = tmp_path / "parent.py"
    parent.write_text(
        "import subprocess,sys,time\n"
        "p=subprocess.Popen([sys.executable,sys.argv[1]])\n"
        "print(p.pid,flush=True)\n"
        "time.sleep(30)\n",
        encoding="utf-8",
    )
    timed = s8._run_bounded_process(
        (sys.executable, str(parent), str(child)), cwd=tmp_path, timeout_seconds=2
    )
    assert timed.timed_out is True
    child_pid = int(timed.output.strip())
    deadline = time.monotonic() + 5
    while psutil.pid_exists(child_pid) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not psutil.pid_exists(child_pid)

    cancel = threading.Event()
    timer = threading.Timer(0.2, cancel.set)
    timer.start()
    try:
        cancelled = s8._run_bounded_process(
            (sys.executable, "-c", "import time; time.sleep(30)"),
            cwd=tmp_path,
            timeout_seconds=10,
            cancel_event=cancel,
        )
    finally:
        timer.cancel()
    assert cancelled.cancelled is True


def test_bounded_process_success_still_cleans_descendants(tmp_path: Path) -> None:
    child = tmp_path / "successful_child.py"
    child.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
    parent = tmp_path / "successful_parent.py"
    parent.write_text(
        "import subprocess,sys\n"
        "p=subprocess.Popen([sys.executable,sys.argv[1]])\n"
        "print(p.pid,flush=True)\n",
        encoding="utf-8",
    )

    result = s8._run_bounded_process(
        (sys.executable, str(parent), str(child)), cwd=tmp_path, timeout_seconds=5
    )

    assert result.exit_code == 0
    child_pid = int(result.output.strip())
    deadline = time.monotonic() + 5
    while psutil.pid_exists(child_pid) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not psutil.pid_exists(child_pid)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows atomic containment")
def test_windows_process_is_suspended_before_job_assignment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    observed_statuses: list[str] = []
    original = s8._create_windows_kill_job

    def inspect_then_assign(process: subprocess.Popen[bytes]) -> object | None:
        observed_statuses.append(psutil.Process(process.pid).status())
        return original(process)

    monkeypatch.setattr(s8, "_create_windows_kill_job", inspect_then_assign)
    result = s8._run_bounded_process(
        (sys.executable, "-c", "print('contained')"),
        cwd=tmp_path,
        timeout_seconds=5,
    )

    assert result.exit_code == 0
    assert observed_statuses == [psutil.STATUS_STOPPED]


def test_cleanup_dry_run_has_zero_effect_and_execute_deletes_exact_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path, monkeypatch)
    _write_json(
        context.effect_plan_path,
        s8.plan_fixture_effect(
            repo=context.repo,
            session_id=context.session_id,
            expected_changed_paths=["created.txt"],
            env=context.env,
        ),
    )
    record = _complete_record(context, _record(context, monkeypatch))
    (context.fixture / "created.txt").write_text(
        "created by showcase\n", encoding="utf-8"
    )
    effect = s8.inspect_fixture_effect(
        repo=context.repo, session_id=context.session_id, env=context.env
    )
    record["project_effect"]["diff_sha256"] = effect["diff_sha256"]
    assert effect["observed_changed_paths"] == ["created.txt"]
    record_path = context.report_path.parent / "session.json"
    _write_json(record_path, record)
    monkeypatch.setattr(s8, "_port_open", lambda *_args, **_kwargs: False)

    report = s8.run_cleanup(
        repo=context.repo,
        s7_report_path=context.report_path,
        handoff_path=context.handoff_path,
        effect_plan_path=context.effect_plan_path,
        product_binding_path=context.product_binding_path,
        product_trace_path=context.product_trace_path,
        trace_manifest_path=context.trace_manifest_path,
        record_path=record_path,
        env=context.env,
        execute=False,
    )
    assert report["fixture_action"] == "DRY_RUN_PRESERVED"
    assert context.fixture.is_dir()

    record["project_effect"]["cleanup_action"] = "DELETE"
    _write_json(record_path, record)
    report = s8.run_cleanup(
        repo=context.repo,
        s7_report_path=context.report_path,
        handoff_path=context.handoff_path,
        effect_plan_path=context.effect_plan_path,
        product_binding_path=context.product_binding_path,
        product_trace_path=context.product_trace_path,
        trace_manifest_path=context.trace_manifest_path,
        record_path=record_path,
        env=context.env,
        execute=True,
    )
    assert report["fixture_action"] == "DELETED"
    assert not context.fixture.exists()


def test_cleanup_rejects_handoff_changed_after_session_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path, monkeypatch)
    record = _complete_record(context, _record(context, monkeypatch))
    record_path = context.report_path.parent / "session.json"
    _write_json(record_path, record)
    context.handoff["known_deviation_ids"] = ["S7-DEVIATION-AFTER-SESSION"]
    _write_json(context.handoff_path, context.handoff)
    monkeypatch.setattr(s8, "_port_open", lambda *_args, **_kwargs: False)

    with pytest.raises(s8.ReadinessError, match="SESSION_HANDOFF_BINDING_MISMATCH"):
        s8.run_cleanup(
            repo=context.repo,
            s7_report_path=context.report_path,
            handoff_path=context.handoff_path,
            effect_plan_path=context.effect_plan_path,
            product_binding_path=context.product_binding_path,
            product_trace_path=context.product_trace_path,
            trace_manifest_path=context.trace_manifest_path,
            record_path=record_path,
            env=context.env,
            execute=False,
        )


def test_cleanup_rejects_post_hoc_unexpected_fixture_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path, monkeypatch)
    record = _complete_record(context, _record(context, monkeypatch))
    (context.fixture / "surprise.txt").write_text("unexpected\n", encoding="utf-8")
    observed = s8.inspect_fixture_effect(
        repo=context.repo, session_id=context.session_id, env=context.env
    )
    record["project_effect"]["diff_sha256"] = observed["diff_sha256"]
    record_path = context.report_path.parent / "unexpected-session.json"
    _write_json(record_path, record)
    monkeypatch.setattr(s8, "_port_open", lambda *_args, **_kwargs: False)

    with pytest.raises(s8.ReadinessError, match="FIXTURE_EFFECT_MISMATCH"):
        s8.run_cleanup(
            repo=context.repo,
            s7_report_path=context.report_path,
            handoff_path=context.handoff_path,
            effect_plan_path=context.effect_plan_path,
            product_binding_path=context.product_binding_path,
            product_trace_path=context.product_trace_path,
            trace_manifest_path=context.trace_manifest_path,
            record_path=record_path,
            env=context.env,
            execute=False,
        )


def test_blocked_session_can_cleanup_before_planned_effect_occurs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path, monkeypatch)
    _write_json(
        context.effect_plan_path,
        s8.plan_fixture_effect(
            repo=context.repo,
            session_id=context.session_id,
            expected_changed_paths=["planned.txt"],
            env=context.env,
        ),
    )
    record = _record(context, monkeypatch)
    record_path = context.report_path.parent / "blocked-session.json"
    _write_json(record_path, record)
    monkeypatch.setattr(s8, "_port_open", lambda *_args, **_kwargs: False)

    report = s8.run_cleanup(
        repo=context.repo,
        s7_report_path=context.report_path,
        handoff_path=context.handoff_path,
        effect_plan_path=context.effect_plan_path,
        product_binding_path=context.product_binding_path,
        product_trace_path=context.product_trace_path,
        trace_manifest_path=context.trace_manifest_path,
        record_path=record_path,
        env=context.env,
        execute=False,
    )

    assert report["status"] == "CLEANUP_VERIFIED"
    assert report["fixture_action"] == "DRY_RUN_PRESERVED"


def test_session_initialization_revalidates_frozen_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path, monkeypatch)
    context.env["S8_EXECUTOR"] = "mismatched-executor"

    with pytest.raises(s8.ReadinessError, match="RUNTIME_ROUTE_MISMATCH"):
        _record(context, monkeypatch)


def test_destructive_targets_inside_candidate_or_home_are_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path, monkeypatch)
    with pytest.raises(s8.ReadinessError, match="FIXTURE_TARGET_REJECTED"):
        s8.init_fixture(
            repo=context.repo,
            root=context.repo / "live-voice-s8-fixture-escape",
            session_id=context.session_id,
            execute=True,
        )
    with pytest.raises(s8.ReadinessError, match="FIXTURE_TARGET_REJECTED"):
        s8.init_fixture(
            repo=context.repo,
            root=Path.home(),
            session_id=context.session_id,
            execute=True,
        )


def test_report_and_session_inputs_must_stay_outside_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path, monkeypatch)
    inside = context.repo / "private.json"
    _write_json(inside, context.report)
    with pytest.raises(s8.ReadinessError, match="PRIVATE_FILE_INSIDE_CANDIDATE"):
        s8._load_json(inside, context.repo, s8.S7_REPORT_SCHEMA)
