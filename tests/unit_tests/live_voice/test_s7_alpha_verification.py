# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path
from types import ModuleType

import pytest


def _load_module() -> ModuleType:
    source = (
        Path(__file__).resolve().parents[3]
        / "scripts"
        / "live_voice"
        / "s7_alpha_verification.py"
    )
    spec = importlib.util.spec_from_file_location("s7_alpha_verification", source)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


s7 = _load_module()

_PRIVATE_ORIGIN = "https://voice.private.internal"
_PRIVATE_ORIGIN_REF = (
    "private_origin_ref:sha256-"
    + hashlib.sha256(_PRIVATE_ORIGIN.encode("ascii")).hexdigest()
)


class _AsciiSink(io.StringIO):
    @property
    def encoding(self) -> str:
        return "ascii"


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ("git", *args),
        cwd=repo,
        check=True,
        stdout=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    return completed.stdout.strip()


def _candidate_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "candidate"
    repo.mkdir()
    _git(repo, "init", "-b", "candidate")
    _git(repo, "config", "user.email", "s7@example.invalid")
    _git(repo, "config", "user.name", "S7 Test")
    inputs = {
        "pyproject.toml": "[project]\nname='candidate'\n",
        "uv.lock": "version = 1\n",
        "jiuwenswarm/channels/web/frontend/package.json": json.dumps(
            {
                "scripts": {
                    "test:live-voice-one": "node --test",
                    "test:speech-recognition-lifecycle": (
                        "node --test tests/speechRecognitionLifecycle.test.mjs"
                    ),
                    "test:tts-output-ownership": (
                        "node --test tests/ttsOutputOwnership.test.mjs"
                    ),
                    "test:chat-store-streaming": (
                        "node --test tests/chatStoreStreaming.test.mjs"
                    ),
                    "build": "tsc",
                }
            }
        ),
        "jiuwenswarm/channels/web/frontend/package-lock.json": "{}\n",
        "jiuwenswarm/channels/web/frontend/tests/speechRecognitionLifecycle.test.mjs": "// compatibility\n",
        "jiuwenswarm/channels/web/frontend/tests/ttsOutputOwnership.test.mjs": "// compatibility\n",
        "jiuwenswarm/channels/web/frontend/tests/chatStoreStreaming.test.mjs": "// compatibility\n",
        "scripts/live_voice/probe.py": (
            "import json, os\n"
            "print('S7_SANITIZED_RESULT ' + json.dumps({"
            "'candidate_head': os.environ['S7_CANDIDATE_HEAD'], "
            "'check_id': os.environ['S7_CHECK_ID'], "
            "'sample_count': 1, 'failure_count': 0, "
            "'p50_ms': 1, 'p95_ms': 2, "
            "'zero_forbidden_effects': True, 'outcome': 'PASS'}))\n"
        ),
    }
    for entrypoint, _required_env in s7.CANONICAL_REAL_PROBES.values():
        inputs[entrypoint] = "raise SystemExit(0)\n"
    for relative, content in inputs.items():
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "candidate")
    return repo, _git(repo, "rev-parse", "HEAD")


def test_candidate_identity_requires_clean_worktree_and_records_dependency_hashes(
    tmp_path: Path,
) -> None:
    repo, head = _candidate_repo(tmp_path)

    identity = s7.collect_candidate_identity(
        repo,
        comparison_base=head,
        allow_no_upstream=True,
    )

    assert identity.head == head
    assert identity.branch == "candidate"
    assert identity.upstream is None
    assert set(identity.dependency_sha256) == set(s7.DEPENDENCY_INPUTS)
    assert all(len(value) == 64 for value in identity.dependency_sha256.values())
    assert identity.generated_artifact_state == {
        "policy": "generated-output-excluded-from-candidate",
        "tracked_count": "0",
        "tracked_sha256": hashlib.sha256(b"").hexdigest(),
    }

    (repo / "untracked.txt").write_text("dirty", encoding="utf-8")
    with pytest.raises(s7.VerificationError, match="not clean"):
        s7.collect_candidate_identity(
            repo,
            comparison_base=head,
            allow_no_upstream=True,
        )


def test_candidate_identity_rejects_ignored_dotenv(tmp_path: Path) -> None:
    repo, _ = _candidate_repo(tmp_path)
    (repo / ".gitignore").write_text(".env\n", encoding="utf-8")
    _git(repo, "add", ".gitignore")
    _git(repo, "commit", "-m", "ignore private environment")
    head = _git(repo, "rev-parse", "HEAD")
    (repo / ".env").write_text("PRIVATE_VALUE=present\n", encoding="utf-8")

    with pytest.raises(s7.VerificationError, match="ignored dotenv"):
        s7.collect_candidate_identity(
            repo,
            comparison_base=head,
            allow_no_upstream=True,
        )


def test_automation_plan_discovers_frontend_scripts_and_keeps_asyncio_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = Path(__file__).resolve().parents[3]
    base = _git(repo, "rev-parse", "HEAD")
    monkeypatch.setattr(s7, "_changed_files", lambda *_args, **_kwargs: ("changed.py",))

    specs = s7.build_automation_specs(repo, comparison_base=base)

    frontend = [
        spec for spec in specs if spec.check_id.startswith("frontend-live-voice-")
    ]
    compatibility = {
        spec.argv[-1]
        for spec in specs
        if spec.argv[-1] in s7.REQUIRED_FRONTEND_COMPAT_SCRIPTS
    }
    package = json.loads(
        (repo / "jiuwenswarm/channels/web/frontend/package.json").read_text(
            encoding="utf-8"
        )
    )
    expected = {
        name for name in package["scripts"] if name.startswith("test:live-voice-")
    }
    assert frontend
    assert compatibility == set(s7.REQUIRED_FRONTEND_COMPAT_SCRIPTS)
    assert {
        f"test:{spec.check_id.removeprefix('frontend-')}" for spec in frontend
    } == expected
    alpha = next(spec for spec in specs if spec.check_id == "backend-alpha-matrix")
    regressions = next(
        spec for spec in specs if spec.check_id == "backend-related-regressions"
    )
    assert "--asyncio-mode=auto" in alpha.argv
    assert "--asyncio-mode=auto" in regressions.argv
    assert "addopts=" not in alpha.argv
    assert "addopts=" not in regressions.argv
    assert "ignore::SyntaxWarning" in alpha.argv
    assert "ignore::SyntaxWarning" in regressions.argv
    assert set(s7.BACKEND_REGRESSION_PATHS).issubset(regressions.argv)
    assert set(s7.LATEST_S6_SOURCE_INVENTORY)
    assert set(s7.LATEST_S6_REGRESSION_INVENTORY)
    assert not any(
        path in regressions.argv
        for path in (
            "tests/unit_tests/agentserver",
            "tests/unit_tests/gateway",
            "tests/unit_tests/channel",
            "tests/unit_tests/auto_harness",
            "tests/unit_tests/server",
        )
    )
    assert all(spec.real_path is False for spec in specs)
    assert any(spec.check_id == "python-lock-synchronized" for spec in specs)
    consistency = next(
        spec for spec in specs if spec.check_id == "python-environment-consistency"
    )
    assert consistency.argv == ("uv", "pip", "check")
    ruff = next(spec for spec in specs if spec.check_id == "changed-python-ruff")
    assert "W605" in ruff.argv
    assert "F821" not in ruff.argv
    assert "--ignore" not in ruff.argv
    assert set(s7.CHANGED_PYTHON_RUFF_WAIVERS).issubset(ruff.argv)
    formatting = next(
        spec for spec in specs if spec.check_id == "s7-owned-python-format"
    )
    assert set(s7.S7_OWNED_PYTHON_PATHS).issubset(formatting.argv)
    assert "jiuwenswarm/channels/web/app_web.py" not in formatting.argv


def test_s7_cli_requires_the_frozen_full_comparison_base() -> None:
    s7.require_s7_comparison_base(s7.S7_COMPARISON_BASE)
    with pytest.raises(s7.VerificationError, match="frozen full SHA"):
        s7.require_s7_comparison_base(s7.S7_COMPARISON_BASE[:12])


def test_frontend_script_discovery_requires_every_tracked_live_voice_test(
    tmp_path: Path,
) -> None:
    repo, _ = _candidate_repo(tmp_path)
    missing_test = (
        repo
        / "jiuwenswarm"
        / "channels"
        / "web"
        / "frontend"
        / "tests"
        / "liveVoiceMissing.test.mjs"
    )
    missing_test.parent.mkdir(parents=True, exist_ok=True)
    missing_test.write_text("// tracked automatic test\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "add uncovered test")

    with pytest.raises(s7.VerificationError, match="exact tracked automatic test set"):
        s7._frontend_scripts(repo)


def _real_config() -> dict[str, object]:
    return {
        "schema_version": s7.REAL_CONFIG_SCHEMA_VERSION,
        "checks": [
            {
                "id": check_id,
                "argv": ["<python>", s7.CANONICAL_REAL_PROBES[check_id][0]],
                "required_env": sorted(s7.CANONICAL_REAL_PROBES[check_id][1]),
            }
            for check_id in sorted(s7.REQUIRED_REAL_CHECKS)
        ],
    }


def test_real_config_is_complete_and_rejects_private_values(tmp_path: Path) -> None:
    repo, _ = _candidate_repo(tmp_path)
    config = _real_config()
    path = tmp_path / "real.json"
    path.write_text(json.dumps(config), encoding="utf-8")

    specs = s7.load_real_check_specs(path, repo)

    assert {spec.check_id for spec in specs} == s7.REQUIRED_REAL_CHECKS
    assert all(spec.real_path for spec in specs)

    checks = config["checks"]
    assert isinstance(checks, list)
    checks[0]["argv"] = [
        "<python>",
        "scripts/live_voice/probe.py",
        "sk-" + "this-must-not-be-stored",
    ]
    path.write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(s7.VerificationError, match="secret-shaped"):
        s7.load_real_check_specs(path, repo)

    config = _real_config()
    checks = config["checks"]
    assert isinstance(checks, list)
    checks[0]["argv"].append("opaquePrivateValue123")
    path.write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(s7.VerificationError, match="positional probe arguments"):
        s7.load_real_check_specs(path, repo)

    config = _real_config()
    checks = config["checks"]
    assert isinstance(checks, list)
    checks[0]["argv"] = ["<python>", "scripts/live_voice/probe.py"]
    path.write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(s7.VerificationError, match="canonical candidate-owned"):
        s7.load_real_check_specs(path, repo)

    config = _real_config()
    checks = config["checks"]
    assert isinstance(checks, list)
    checks[0]["required_env"] = []
    path.write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(s7.VerificationError, match="exact canonical environment"):
        s7.load_real_check_specs(path, repo)


def test_real_config_rejects_arbitrary_commands_placeholders_and_absolute_cwd(
    tmp_path: Path,
) -> None:
    repo, _ = _candidate_repo(tmp_path)
    path = tmp_path / "real.json"
    config = _real_config()
    checks = config["checks"]
    assert isinstance(checks, list)

    checks[0]["argv"] = ["<python>", "-c", "raise SystemExit(0)"]
    path.write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(s7.VerificationError, match="scripts/live_voice"):
        s7.load_real_check_specs(path, repo)

    config = _real_config()
    checks = config["checks"]
    assert isinstance(checks, list)
    checks[0]["argv"].append("${S7_PRIVATE_FIXTURE}")
    checks[0]["required_env"] = ["S7_PRIVATE_FIXTURE"]
    path.write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(s7.VerificationError, match="cannot interpolate"):
        s7.load_real_check_specs(path, repo)

    config = _real_config()
    checks = config["checks"]
    assert isinstance(checks, list)
    checks[0]["cwd"] = str(repo.resolve())
    path.write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(s7.VerificationError, match="repository-relative"):
        s7.load_real_check_specs(path, repo)


def test_real_check_blocks_without_required_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, head = _candidate_repo(tmp_path)
    spec = s7.CheckSpec(
        check_id="speech-media",
        category="real-path",
        argv=("<python>", "scripts/live_voice/probe.py"),
        required_env=("S7_TEST_PRIVATE_INPUT",),
        real_path=True,
    )
    monkeypatch.delenv("S7_TEST_PRIVATE_INPUT", raising=False)

    result = s7.run_check(
        spec,
        repo=repo,
        env=os.environ,
        timeout_seconds=5,
        candidate_head=head,
    )

    assert result.status is s7.CheckStatus.BLOCKED
    assert result.exit_code is None
    assert "S7_TEST_PRIVATE_INPUT" in result.reason
    assert result.command[-1] == "scripts/live_voice/probe.py"


def test_command_output_summary_records_counts_and_sanitized_probe_metrics(
    tmp_path: Path,
) -> None:
    repo, head = _candidate_repo(tmp_path)
    probe_output = "S7_SANITIZED_RESULT " + json.dumps(
        {
            "candidate_head": head,
            "check_id": "speech-media",
            "sample_count": 5,
            "failure_count": 0,
            "p50_ms": 12.5,
            "p95_ms": 25.0,
            "max_ms": 30.0,
            "zero_forbidden_effects": True,
            "outcome": "PASS",
        }
    )
    spec = s7.CheckSpec(
        check_id="speech-media",
        category="real-path",
        argv=(
            "<python>",
            "-c",
            f"print('8 passed, 1 skipped'); print({probe_output!r})",
        ),
        real_path=True,
    )

    result = s7.run_check(
        spec,
        repo=repo,
        env=os.environ,
        timeout_seconds=5,
        candidate_head=head,
    )

    assert result.status is s7.CheckStatus.VERIFY
    assert result.details == {
        "probe_candidate_head": head,
        "probe_check_id": "speech-media",
        "probe_sample_count": 5,
        "probe_failure_count": 0,
        "probe_p50_ms": 12.5,
        "probe_p95_ms": 25.0,
        "probe_max_ms": 30.0,
        "probe_zero_forbidden_effects": True,
        "probe_outcome": "PASS",
        "sanitized_result_count": 1,
    }
    assert result.command[0] == "<python>"

    contradictory = dict(result.details)
    contradictory["probe_max_ms"] = 20.0
    assert not s7._real_probe_contract_valid("speech-media", head, contradictory)


def test_real_probe_summary_must_bind_runtime_declaration(tmp_path: Path) -> None:
    repo, head = _candidate_repo(tmp_path)
    expected_runtime = "sha256:" + ("a" * 64)
    other_runtime = "sha256:" + ("b" * 64)
    probe_output = "S7_SANITIZED_RESULT " + json.dumps(
        {
            "candidate_head": head,
            "runtime_declaration_sha256": other_runtime,
            "check_id": "speech-media",
            "sample_count": 5,
            "failure_count": 0,
            "p50_ms": 12.5,
            "p95_ms": 25.0,
            "zero_forbidden_effects": True,
            "outcome": "PASS",
        }
    )
    spec = s7.CheckSpec(
        check_id="speech-media",
        category="real-path",
        argv=("<python>", "-c", f"print({probe_output!r})"),
        real_path=True,
    )

    result = s7.run_check(
        spec,
        repo=repo,
        env=os.environ,
        timeout_seconds=5,
        candidate_head=head,
        runtime_declaration_sha256=expected_runtime,
    )

    assert result.status is s7.CheckStatus.FAIL
    assert result.details["probe_runtime_declaration_sha256"] == other_runtime


def test_failure_summary_redacts_private_identifiers() -> None:
    private_failure = "FAILED test_private[" + "C:" + "\\Users\\person\\fixture]"
    credential_failure = "FAILED test_secret[token" + "=private]"

    details = s7._summarize_output(
        private_failure + "\n" + credential_failure,
        include_test_details=True,
    )

    assert details["failure_ids_redacted"] == 2
    assert "failure_ids" not in details


def test_automatic_output_is_safe_for_windows_legacy_console(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sink = _AsciiSink()
    monkeypatch.setattr(s7.sys, "stdout", sink)

    s7._echo_automatic_output("passed ✔")

    assert sink.getvalue() == "passed \\u2714\n"


def test_real_probe_cannot_pass_on_exit_code_alone(tmp_path: Path) -> None:
    repo, head = _candidate_repo(tmp_path)
    spec = s7.CheckSpec(
        check_id="privacy",
        category="real-path",
        argv=("<python>", "-c", "raise SystemExit(0)"),
        real_path=True,
    )

    result = s7.run_check(
        spec,
        repo=repo,
        env=os.environ,
        timeout_seconds=5,
        candidate_head=head,
    )

    assert result.status is s7.CheckStatus.FAIL
    assert "sanitized result contract" in result.reason


def test_truncated_real_output_cannot_verify(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, head = _candidate_repo(tmp_path)
    monkeypatch.setattr(s7, "_MAX_CAPTURE_BYTES", 512)
    probe_output = "S7_SANITIZED_RESULT " + json.dumps(
        {
            "candidate_head": head,
            "check_id": "privacy",
            "sample_count": 1,
            "failure_count": 0,
            "zero_forbidden_effects": True,
            "outcome": "PASS",
        }
    )
    spec = s7.CheckSpec(
        check_id="privacy",
        category="real-path",
        argv=("<python>", "-c", f"print('x' * 2048); print({probe_output!r})"),
        real_path=True,
    )

    result = s7.run_check(
        spec,
        repo=repo,
        env=os.environ,
        timeout_seconds=5,
        candidate_head=head,
    )

    assert result.status is s7.CheckStatus.FAIL
    assert result.details["output_truncated"] is True


def test_frontend_command_cannot_pass_without_tap_tests(tmp_path: Path) -> None:
    repo, head = _candidate_repo(tmp_path)
    spec = s7.CheckSpec(
        check_id="frontend-live-voice-fake",
        category="frontend-test",
        argv=("<python>", "-c", "print('ok')"),
    )

    result = s7.run_check(
        spec,
        repo=repo,
        env=os.environ,
        timeout_seconds=5,
        candidate_head=head,
    )

    assert result.status is s7.CheckStatus.FAIL
    assert "summary contract" in result.reason


def test_frontend_build_cannot_pass_without_vite_compilation(tmp_path: Path) -> None:
    repo, head = _candidate_repo(tmp_path)
    spec = s7.CheckSpec(
        check_id="frontend-production-build",
        category="frontend",
        argv=("<python>", "-c", "print('build skipped')"),
    )

    result = s7.run_check(
        spec,
        repo=repo,
        env=os.environ,
        timeout_seconds=5,
        candidate_head=head,
    )

    assert result.status is s7.CheckStatus.FAIL
    assert "summary contract" in result.reason


def test_backend_command_cannot_pass_with_all_tests_skipped(tmp_path: Path) -> None:
    repo, head = _candidate_repo(tmp_path)
    spec = s7.CheckSpec(
        check_id="backend-fake",
        category="backend",
        argv=("<python>", "-c", "print('5 skipped')"),
    )

    result = s7.run_check(
        spec,
        repo=repo,
        env=os.environ,
        timeout_seconds=5,
        candidate_head=head,
    )

    assert result.status is s7.CheckStatus.FAIL
    assert "summary contract" in result.reason


def test_timeout_terminates_descendant_process(tmp_path: Path) -> None:
    repo, head = _candidate_repo(tmp_path)
    marker = tmp_path / "descendant-finished.txt"
    child_code = (
        "import time; from pathlib import Path; time.sleep(0.8); "
        f"Path({str(marker)!r}).write_text('unexpected', encoding='utf-8')"
    )
    parent_code = (
        "import subprocess, sys, time; "
        f"subprocess.Popen([sys.executable, '-c', {child_code!r}]); "
        "time.sleep(10)"
    )
    spec = s7.CheckSpec(
        check_id="timeout-tree",
        category="source",
        argv=("<python>", "-c", parent_code),
    )

    result = s7.run_check(
        spec,
        repo=repo,
        env=os.environ,
        timeout_seconds=0.2,
        candidate_head=head,
    )
    time.sleep(1.0)

    assert result.status is s7.CheckStatus.FAIL
    assert "process tree" in result.reason
    assert not marker.exists()


def test_successful_command_also_terminates_descendant_process(tmp_path: Path) -> None:
    repo, head = _candidate_repo(tmp_path)
    marker = tmp_path / "successful-descendant-finished.txt"
    child_code = (
        "import time; from pathlib import Path; time.sleep(0.8); "
        f"Path({str(marker)!r}).write_text('unexpected', encoding='utf-8')"
    )
    parent_code = (
        "import subprocess, sys; "
        f"subprocess.Popen([sys.executable, '-c', {child_code!r}])"
    )
    spec = s7.CheckSpec(
        check_id="successful-tree",
        category="source",
        argv=("<python>", "-c", parent_code),
    )

    result = s7.run_check(
        spec,
        repo=repo,
        env=os.environ,
        timeout_seconds=5,
        candidate_head=head,
    )
    time.sleep(1.0)

    assert result.status is s7.CheckStatus.PASS
    assert not marker.exists()


def _runtime_payload(head: str) -> dict[str, object]:
    return {
        "schema_version": s7.CANDIDATE_RUNTIME_SCHEMA_VERSION,
        "candidate_head": head,
        "comparison_base": head,
        "feature_flags": dict(s7.CANDIDATE_FEATURE_FLAG_VALUES),
        "runtime_labels": {
            "agent_provider": "jiuwenswarm",
            "browser": "Chrome-139.0.7258.67",
            "operating_system": "Windows-11-build-26100.4946",
            "origin": _PRIVATE_ORIGIN_REF,
            "input_device": "device_ref:sha256-1111111111111111",
            "output_device": "device_ref:sha256-2222222222222222",
            "network_profile": "network_ref:sha256-3333333333333333",
            "speech_provider": "openai",
            "speech_api_origin": "https://api.openai.com/v1",
            "speech_fallback": "streaming-w2-batch-browser-text",
            "stt_model": "gpt-4o-mini-transcribe-2025-12-15",
            "tts_model": "gpt-4o-mini-tts-2025-12-15",
            "tts_voice": "marin",
            "executor": "DirectProjectCodeExecutorAdapter",
            "project_fixture": "disposable_git_ref:sha256-4444444444444444:no_remote",
            "data_fixture": "data_ref:sha256-5555555555555555",
            "deployment_topology": "private-same-origin-https-wss",
        },
    }


def test_candidate_runtime_binds_head_flags_and_d078_labels(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, head = _candidate_repo(tmp_path)
    identity = s7.collect_candidate_identity(
        repo, comparison_base=head, allow_no_upstream=True
    )
    monkeypatch.setenv("S7_PRIVATE_ORIGIN", _PRIVATE_ORIGIN)
    for name, value in s7.CANDIDATE_FEATURE_FLAG_VALUES.items():
        if value == "unset":
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    path = tmp_path / "candidate-runtime.json"
    path.write_text(json.dumps(_runtime_payload(head)), encoding="utf-8")

    declaration = s7.load_candidate_runtime(
        path, repo=repo, identity=identity, env=os.environ
    )

    assert declaration.candidate_head == head
    assert declaration.runtime_labels["tts_voice"] == "marin"
    runtime_sha = s7.candidate_runtime_sha256(declaration)
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", runtime_sha)

    monkeypatch.setenv("S7_PRIVATE_ORIGIN", "https://live-voice.localhost")
    with pytest.raises(s7.VerificationError, match="private HTTPS FQDN"):
        s7.load_candidate_runtime(path, repo=repo, identity=identity, env=os.environ)
    monkeypatch.setenv("S7_PRIVATE_ORIGIN", _PRIVATE_ORIGIN)

    wrong_origin = _runtime_payload(head)
    wrong_labels = wrong_origin["runtime_labels"]
    assert isinstance(wrong_labels, dict)
    wrong_labels["origin"] = "private_origin_ref:sha256-" + ("f" * 64)
    path.write_text(json.dumps(wrong_origin), encoding="utf-8")
    with pytest.raises(s7.VerificationError, match="does not match"):
        s7.load_candidate_runtime(path, repo=repo, identity=identity, env=os.environ)

    payload = _runtime_payload(head)
    labels = payload["runtime_labels"]
    assert isinstance(labels, dict)
    labels["speech_api_origin"] = "https://example.invalid/v1"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(s7.VerificationError, match="violates D-078"):
        s7.load_candidate_runtime(path, repo=repo, identity=identity, env=os.environ)

    disabled = _runtime_payload(head)
    flags = disabled["feature_flags"]
    assert isinstance(flags, dict)
    for name in s7.REQUIRED_FEATURE_FLAGS:
        flags[name] = "unset"
        monkeypatch.delenv(name, raising=False)
    path.write_text(json.dumps(disabled), encoding="utf-8")
    with pytest.raises(s7.VerificationError, match="accepted candidate profile"):
        s7.load_candidate_runtime(path, repo=repo, identity=identity, env=os.environ)

    exact = _runtime_payload(head)
    for name, value in s7.CANDIDATE_FEATURE_FLAG_VALUES.items():
        if value == "unset":
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    active_flag = next(
        name
        for name, value in s7.CANDIDATE_FEATURE_FLAG_VALUES.items()
        if value == "true"
    )
    for noncanonical in ("1", "yes", "on", "TRUE", " true "):
        monkeypatch.setenv(active_flag, noncanonical)
        path.write_text(json.dumps(exact), encoding="utf-8")
        with pytest.raises(s7.VerificationError, match="exact process value"):
            s7.load_candidate_runtime(
                path, repo=repo, identity=identity, env=os.environ
            )
    monkeypatch.setenv(active_flag, "true")
    unset_flag = next(
        name
        for name, value in s7.CANDIDATE_FEATURE_FLAG_VALUES.items()
        if value == "unset"
    )
    for present_false_value in ("", " "):
        monkeypatch.setenv(unset_flag, present_false_value)
        with pytest.raises(s7.VerificationError, match="exact process value"):
            s7.load_candidate_runtime(
                path, repo=repo, identity=identity, env=os.environ
            )


@pytest.mark.parametrize(
    "private_label",
    (
        "token=private-value",
        "api_key=private-value",
        "Bearer private-token-value",
        "eyJheader.payloadpart.signaturepart",
    ),
)
def test_candidate_runtime_rejects_credential_shaped_labels(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    private_label: str,
) -> None:
    repo, head = _candidate_repo(tmp_path)
    identity = s7.collect_candidate_identity(
        repo, comparison_base=head, allow_no_upstream=True
    )
    monkeypatch.setenv("S7_PRIVATE_ORIGIN", _PRIVATE_ORIGIN)
    for name, value in s7.CANDIDATE_FEATURE_FLAG_VALUES.items():
        if value == "unset":
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    payload = _runtime_payload(head)
    labels = payload["runtime_labels"]
    assert isinstance(labels, dict)
    labels["project_fixture"] = private_label
    path = tmp_path / "candidate-runtime-private.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(s7.VerificationError, match="private material"):
        s7.load_candidate_runtime(path, repo=repo, identity=identity, env=os.environ)


@pytest.mark.parametrize(
    ("label", "value"),
    (
        ("browser", "Chrome"),
        ("operating_system", "Windows"),
        ("input_device", "default-microphone"),
        ("network_profile", "unknown"),
        ("project_fixture", "fixture"),
        ("data_fixture", "temporary-data"),
        ("origin", "https://example.com"),
    ),
)
def test_candidate_runtime_rejects_placeholder_or_public_labels(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    label: str,
    value: str,
) -> None:
    repo, head = _candidate_repo(tmp_path)
    identity = s7.collect_candidate_identity(
        repo, comparison_base=head, allow_no_upstream=True
    )
    monkeypatch.setenv("S7_PRIVATE_ORIGIN", _PRIVATE_ORIGIN)
    for name, flag_value in s7.CANDIDATE_FEATURE_FLAG_VALUES.items():
        if flag_value == "unset":
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, flag_value)
    payload = _runtime_payload(head)
    labels = payload["runtime_labels"]
    assert isinstance(labels, dict)
    labels[label] = value
    path = tmp_path / "candidate-runtime-placeholder.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(s7.VerificationError):
        s7.load_candidate_runtime(path, repo=repo, identity=identity, env=os.environ)


def test_real_child_environment_is_minimal(tmp_path: Path) -> None:
    repo, head = _candidate_repo(tmp_path)
    spec = s7.CheckSpec(
        check_id="privacy",
        category="real-path",
        argv=("<python>", "scripts/live_voice/probe.py"),
        required_env=("S7_REQUIRED",),
        real_path=True,
    )
    child = s7._child_env(
        spec,
        {
            "PATH": os.environ.get("PATH", ""),
            "S7_REQUIRED": "private",
            "JIUWENSWARM_LIVE_VOICE_PRODUCT_P2_ENABLED": "true",
            "UNRELATED": "drop",
        },
        candidate_head=head,
        runtime_declaration_sha256="sha256:" + ("c" * 64),
    )

    assert child["S7_REQUIRED"] == "private"
    assert child["S7_CANDIDATE_HEAD"] == head
    assert child["S7_CHECK_ID"] == "privacy"
    assert child["S7_RUNTIME_DECLARATION_SHA256"] == "sha256:" + ("c" * 64)
    assert child["JIUWENSWARM_LIVE_VOICE_PRODUCT_P2_ENABLED"] == "true"
    assert "UNRELATED" not in child

    automatic = s7._child_env(
        s7.CheckSpec(check_id="automatic", category="source", argv=("git",)),
        {
            "PATH": os.environ.get("PATH", ""),
            "LIVE_VOICE_SPEECH_API_KEY": "private",
            "JIUWENSWARM_LIVE_VOICE_P3_AUTH_TOKEN": "private",
            "JIUWENSWARM_LIVE_VOICE_PRODUCT_P2_ENABLED": "true",
        },
        candidate_head=head,
    )
    assert automatic["JIUWENSWARM_LIVE_VOICE_PRODUCT_P2_ENABLED"] == "true"
    assert "LIVE_VOICE_SPEECH_API_KEY" not in automatic
    assert "JIUWENSWARM_LIVE_VOICE_P3_AUTH_TOKEN" not in automatic


def test_report_never_calls_automation_only_an_s7_pass(tmp_path: Path) -> None:
    repo, head = _candidate_repo(tmp_path)
    identity = s7.collect_candidate_identity(
        repo,
        comparison_base=head,
        allow_no_upstream=True,
    )
    report = s7.build_report(
        identity=identity,
        results=(
            s7.CheckResult(
                check_id="automatic",
                category="backend",
                status=s7.CheckStatus.PASS,
                duration_ms=1,
                exit_code=0,
            ),
        ),
    )

    assert report.automation_status is s7.CheckStatus.PASS
    assert report.real_path_status is s7.CheckStatus.NOT_RUN
    assert report.s7_readiness == "PARTIAL_AUTOMATION_ONLY"
    assert report.not_a_gate is True
    assert s7.report_exit_code(report) == 3


def test_selected_check_marker_prevents_ready_status(tmp_path: Path) -> None:
    repo, head = _candidate_repo(tmp_path)
    identity = s7.collect_candidate_identity(
        repo,
        comparison_base=head,
        allow_no_upstream=True,
    )
    results = [
        s7.CheckResult(
            check_id="automatic",
            category="backend",
            status=s7.CheckStatus.PASS,
            duration_ms=1,
        ),
        s7.CheckResult(
            check_id="selected-check-filter",
            category="source",
            status=s7.CheckStatus.NOT_RUN,
            duration_ms=0,
        ),
    ]
    results.extend(
        s7.CheckResult(
            check_id=check_id,
            category="real-path",
            status=s7.CheckStatus.VERIFY,
            duration_ms=1,
        )
        for check_id in s7.REQUIRED_REAL_CHECKS
    )

    report = s7.build_report(identity=identity, results=results)

    assert report.automation_status is s7.CheckStatus.NOT_RUN
    assert report.real_path_status is s7.CheckStatus.VERIFY
    assert report.s7_readiness == "PARTIAL_AUTOMATION_ONLY"


def test_verified_real_results_need_runtime_record_and_allow_only_review_readiness(
    tmp_path: Path,
) -> None:
    repo, head = _candidate_repo(tmp_path)
    identity = s7.collect_candidate_identity(
        repo, comparison_base=head, allow_no_upstream=True
    )
    identity = replace(
        identity,
        upstream="origin/candidate",
        upstream_head=head,
        ahead=0,
        behind=0,
    )
    runtime_labels = _runtime_payload(head)["runtime_labels"]
    assert isinstance(runtime_labels, dict)
    runtime = s7.CandidateRuntimeDeclaration(
        candidate_head=head,
        comparison_base=head,
        feature_flags=dict(s7.CANDIDATE_FEATURE_FLAG_VALUES),
        runtime_labels=runtime_labels,
    )
    results = [
        s7.CheckResult(
            check_id="automatic",
            category="backend",
            status=s7.CheckStatus.PASS,
            duration_ms=1,
        )
    ]
    results.extend(
        s7.CheckResult(
            check_id=check_id,
            category="real-path",
            status=s7.CheckStatus.VERIFY,
            duration_ms=1,
        )
        for check_id in s7.REQUIRED_REAL_CHECKS
    )

    without_runtime = s7.build_report(identity=identity, results=results)
    with_runtime = s7.build_report(
        identity=identity, results=results, runtime_declaration=runtime
    )

    assert without_runtime.s7_readiness == "PARTIAL_AUTOMATION_ONLY"
    assert with_runtime.real_path_status is s7.CheckStatus.VERIFY
    assert with_runtime.s7_readiness == "READY_FOR_S7_CUMULATIVE_REVIEW"
    assert s7.report_exit_code(with_runtime) == 0
    assert s7.report_exit_code(replace(with_runtime, s7_readiness="FAIL")) == 1
    assert s7.report_exit_code(replace(with_runtime, s7_readiness="BLOCKED")) == 2


def test_run_requires_candidate_local_locked_python(tmp_path: Path) -> None:
    repo, _ = _candidate_repo(tmp_path)

    with pytest.raises(s7.VerificationError, match="uv run --frozen"):
        s7.require_project_python(repo)


def test_report_must_stay_outside_source_worktree(tmp_path: Path) -> None:
    repo, head = _candidate_repo(tmp_path)
    identity = s7.collect_candidate_identity(
        repo,
        comparison_base=head,
        allow_no_upstream=True,
    )
    report = s7.build_report(identity=identity, results=())

    with pytest.raises(s7.VerificationError, match="outside"):
        s7.write_report(report, repo / "report.json", repo)

    output = tmp_path / "report.json"
    s7.write_report(report, output, repo)
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["not_a_gate"] is True
    assert str(repo) not in output.read_text(encoding="utf-8")


def test_post_run_identity_detects_candidate_mutation(tmp_path: Path) -> None:
    repo, head = _candidate_repo(tmp_path)
    identity = s7.collect_candidate_identity(
        repo,
        comparison_base=head,
        allow_no_upstream=True,
    )
    (repo / "uv.lock").write_text("changed\n", encoding="utf-8")

    result = s7.inspect_candidate_after_run(repo, identity)

    assert result.status is s7.CheckStatus.FAIL
    assert "identity changed" in result.reason


def test_source_hygiene_rejects_machine_paths_secrets_and_raw_media(
    tmp_path: Path,
) -> None:
    repo, base = _candidate_repo(tmp_path)
    (repo / "private.txt").write_text(
        "C:"
        + "\\Users\\someone\\private and /"
        + "home/alice/private and "
        + "sk-"
        + "testvalue123456789012345",
        encoding="utf-8",
    )
    (repo / "sample.wav").write_bytes(b"not audio")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "unsafe")

    result = s7.inspect_source_hygiene(repo, base)

    assert result.status is s7.CheckStatus.FAIL
    assert result.details["suspect_added_lines"] == 1
    assert result.details["raw_media_files"] == 1


def test_source_hygiene_allows_web_routes_regex_literals_and_jsx(
    tmp_path: Path,
) -> None:
    repo, base = _candidate_repo(tmp_path)
    (repo / "safe.tsx").write_text(
        "const route = '/ws/live-voice/media';\n"
        "const normalized = value.replace(/-/g, '_');\n"
        "const node = <Component />;\n"
        "const taskId = 'task-progress-terminal';\n"
        "const schema = 'live-voice.formal-task-intent-recovery.v2';\n",
        encoding="utf-8",
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "safe source")

    result = s7.inspect_source_hygiene(repo, base)

    assert result.status is s7.CheckStatus.PASS
    assert result.details["suspect_added_lines"] == 0
    assert result.details["raw_media_files"] == 0
