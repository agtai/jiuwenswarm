# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from jiuwenswarm.server.live_voice.w2_automated_report import (
    W2AutomatedReportError,
    create_w2_automated_report,
    main,
    summarize_w2_junit_results,
)
from jiuwenswarm.server.live_voice.w2_evidence_exporter import (
    W2EvidenceExporterError,
)


_CANDIDATE_SHA = "a" * 40


def _junit(
    *cases: str,
    failures: int = 0,
    errors: int = 0,
    skipped: int = 0,
) -> bytes:
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        "<testsuites>"
        f'<testsuite name="pytest" errors="{errors}" failures="{failures}" '
        f'skipped="{skipped}" tests="{len(cases)}" time="0.001">'
        + "".join(cases)
        + "</testsuite></testsuites>"
    ).encode()


def _case(name: str, result: str = "") -> str:
    return (
        f'<testcase classname="tests.live_voice.test_gate" name="{name}" '
        f'time="0.001">{result}</testcase>'
    )


def _tracked_test_file(repository: Path, source: str) -> Path:
    repository.mkdir(parents=True, exist_ok=True)
    test_file = repository / "test_cli_suite.py"
    test_file.write_text(source, encoding="utf-8")
    for command in (
        ("git", "init", "-q"),
        ("git", "config", "user.email", "w2-report@example.invalid"),
        ("git", "config", "user.name", "W2 Report Test"),
        ("git", "add", "--", test_file.name),
        ("git", "commit", "-q", "-m", "test fixture"),
    ):
        subprocess.run(
            command,
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    return test_file


def test_real_pytest_junit_creates_canonical_deterministic_report(
    tmp_path: Path,
) -> None:
    test_file = tmp_path / "test_actual_junit.py"
    junit_file = tmp_path / "pytest.xml"
    test_file.write_text(
        "def test_one():\n    assert True\n\ndef test_two():\n    assert 2 + 2 == 4\n",
        encoding="utf-8",
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-o",
            "addopts=",
            f"--junitxml={junit_file}",
            str(test_file),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr

    junit = junit_file.read_bytes()
    summary = summarize_w2_junit_results((junit,))
    assert summary.document_count == 1
    assert summary.suite_count == 1
    assert summary.testcase_count == 2
    assert summary.testcase_ids == tuple(sorted(summary.testcase_ids))

    first = create_w2_automated_report(
        candidate_sha=_CANDIDATE_SHA,
        suite_id="gate1-automated",
        passed_subjects=(
            "automated:gate1-automated",
            "verification:affected_python_passed",
            "review:gate1",
        ),
        junit_documents=(junit,),
    )
    second = create_w2_automated_report(
        candidate_sha=_CANDIDATE_SHA,
        suite_id="gate1-automated",
        passed_subjects=(
            "review:gate1",
            "automated:gate1-automated",
            "verification:affected_python_passed",
        ),
        junit_documents=(junit,),
    )
    assert first == second
    assert first.endswith(b"\n")
    assert json.loads(first) == {
        "schema": "live-voice.w2-automated-report.v2",
        "candidate_sha": _CANDIDATE_SHA,
        "suite_id": "gate1-automated",
        "passed_subjects": [
            "automated:gate1-automated",
            "review:gate1",
            "verification:affected_python_passed",
        ],
    }


@pytest.mark.parametrize(
    ("result", "failures", "errors", "skipped"),
    (
        ("<failure>boom</failure>", 1, 0, 0),
        ("<error>boom</error>", 0, 1, 0),
        ('<skipped type="pytest.skip">why</skipped>', 0, 0, 1),
    ),
)
def test_failed_error_or_skipped_junit_cannot_mint_report(
    result: str,
    failures: int,
    errors: int,
    skipped: int,
) -> None:
    junit = _junit(
        _case("test_result", result),
        failures=failures,
        errors=errors,
        skipped=skipped,
    )
    with pytest.raises(W2AutomatedReportError, match="not a closed pass"):
        create_w2_automated_report(
            candidate_sha=_CANDIDATE_SHA,
            suite_id="suite-1",
            passed_subjects=("automated:suite-1",),
            junit_documents=(junit,),
        )


@pytest.mark.parametrize(
    ("junit", "message"),
    (
        (
            _junit(_case("test_one"), failures=1),
            "declared failures count",
        ),
        (
            _junit(_case("test_one", "<rerun>old failure</rerun>")),
            "flaky/rerun",
        ),
        (
            b'<!DOCTYPE testsuite [<!ENTITY x "pass">]>'
            b'<testsuite tests="0" failures="0" errors="0" skipped="0"/>',
            "DTD/entity",
        ),
        (
            b'<testsuite tests="1" failures="0" errors="0" skipped="0">'
            b'<testcase classname="tests.live_voice.test_gate"/></testsuite>',
            "must have a name",
        ),
        (
            b'<testsuite tests="0" failures="0" errors="0" skipped="0"/>',
            "must contain a testcase",
        ),
        (
            b'<testsuite tests="1" failures="0" errors="0" skipped="0">'
            b'<testcase classname="tests.live_voice.test_gate" name="test_one" '
            b'status="skipped"/></testsuite>',
            "unsupported attributes",
        ),
        (
            b'<testsuite tests="1" failures="0" errors="0" skipped="0">'
            b'<testcase classname="tests.live_voice.test_gate" name="test_one" '
            b'result="failed"/></testsuite>',
            "unsupported attributes",
        ),
        (
            b'<testsuite tests="1" failures="0" errors="0" skipped="0">'
            b'<properties><property name="flaky" value="true"/></properties>'
            b'<testcase classname="tests.live_voice.test_gate" name="test_one"/>'
            b"</testsuite>",
            "unsupported tag 'properties'",
        ),
        (
            b'<testsuite tests="1" failures="0" errors="0" skipped="0">'
            b"<system-out>RERUN then PASSED</system-out>"
            b'<testcase classname="tests.live_voice.test_gate" name="test_one"/>'
            b"</testsuite>",
            "unsupported tag 'system-out'",
        ),
        (
            (
                '<?xml version="1.0" encoding="utf-16"?>'
                '<!DOCTYPE testsuite [<!ENTITY rerun "RERUN FAILED">]>'
                '<testsuite tests="1" failures="0" errors="0" skipped="0">'
                '<testcase classname="tests.live_voice.test_gate" '
                'name="test_one">&rerun;</testcase></testsuite>'
            ).encode("utf-16"),
            "strict UTF-8",
        ),
        (
            b'<testsuite tests="1" failures="0" errors="0" skipped="0">'
            b'<testcase classname="tests.live_voice.test_gate" name="test_one">'
            b"RERUN FAILED OUTPUT</testcase></testsuite>",
            "non-whitespace mixed text",
        ),
        (
            b'<testsuite tests="1" failures="0" errors="0" skipped="0">'
            b"<!-- hidden rerun --><testcase "
            b'classname="tests.live_voice.test_gate" name="test_one"/>'
            b"</testsuite>",
            "comments are not accepted",
        ),
        (
            b'<testsuite tests="1" failures="0" errors="0" skipped="0">'
            b"<?rerun failed?><testcase "
            b'classname="tests.live_voice.test_gate" name="test_one"/>'
            b"</testsuite>",
            "processing instructions are not accepted",
        ),
    ),
)
def test_malformed_or_untrustworthy_junit_fails_closed(
    junit: bytes,
    message: str,
) -> None:
    with pytest.raises(W2AutomatedReportError, match=message):
        summarize_w2_junit_results((junit,))


def test_duplicate_testcase_across_documents_is_rejected_as_possible_rerun() -> None:
    junit = _junit(_case("test_one"))
    with pytest.raises(W2AutomatedReportError, match="duplicate testcase"):
        summarize_w2_junit_results((junit, junit))


def test_deeply_nested_junit_fails_closed_before_python_recursion() -> None:
    nested = _case("test_one")
    for _ in range(65):
        nested = (
            '<testsuite tests="1" failures="0" errors="0" skipped="0">'
            + nested
            + "</testsuite>"
        )
    with pytest.raises(W2AutomatedReportError, match="nesting exceeds"):
        summarize_w2_junit_results((nested.encode(),))


def test_candidate_subject_and_ledger_bindings_fail_closed() -> None:
    junit = _junit(_case("test_one"))
    with pytest.raises(W2AutomatedReportError, match="full lowercase Git SHA"):
        create_w2_automated_report(
            candidate_sha="A" * 40,
            suite_id="suite-1",
            passed_subjects=("automated:suite-1",),
            junit_documents=(junit,),
        )
    with pytest.raises(W2AutomatedReportError, match="exact automated suite"):
        create_w2_automated_report(
            candidate_sha=_CANDIDATE_SHA,
            suite_id="suite-1",
            passed_subjects=("review:gate1",),
            junit_documents=(junit,),
        )
    with pytest.raises(W2AutomatedReportError, match="duplicates"):
        create_w2_automated_report(
            candidate_sha=_CANDIDATE_SHA,
            suite_id="suite-1",
            passed_subjects=("automated:suite-1", "automated:suite-1"),
            junit_documents=(junit,),
        )
    with pytest.raises(W2AutomatedReportError, match="runtime ledger"):
        create_w2_automated_report(
            candidate_sha=_CANDIDATE_SHA,
            suite_id="suite-1",
            passed_subjects=("automated:suite-1", "ledger:p2.agent_bridge"),
            junit_documents=(junit,),
        )


def test_cli_writes_only_stdout_after_candidate_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    test_file = _tracked_test_file(
        tmp_path,
        "import os\n\n"
        "def test_one():\n"
        "    assert os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] == '1'\n"
        "    assert os.environ['PYTEST_PLUGINS'] == ''\n"
        "    assert os.environ['PYTEST_ADDOPTS'] == ''\n"
        "    assert os.environ['PYTHONPATH'] == os.getcwd()\n",
    )
    observed: list[dict[str, object]] = []

    def verify(**kwargs: object) -> str:
        observed.append(kwargs)
        return _CANDIDATE_SHA

    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.w2_automated_report."
        "verify_w2_candidate_checkout",
        verify,
    )
    assert (
        main(
            [
                "--candidate-sha",
                _CANDIDATE_SHA,
                "--suite-id",
                "gate1-automated",
                "--subject",
                "automated:gate1-automated",
                "--subject",
                "review:gate1",
                "--pytest-target",
                test_file.name,
                "--repository",
                str(tmp_path),
            ]
        )
        == 0
    )
    captured = capsys.readouterr()
    assert json.loads(captured.out)["passed_subjects"] == [
        "automated:gate1-automated",
        "review:gate1",
    ]
    assert captured.err == ""
    assert observed == [
        {
            "repository_path": tmp_path,
            "candidate_sha": _CANDIDATE_SHA,
            "bind_loaded_source": True,
        },
        {
            "repository_path": tmp_path,
            "candidate_sha": _CANDIDATE_SHA,
            "bind_loaded_source": True,
        },
    ]
    assert {path.name for path in tmp_path.iterdir()} == {".git", test_file.name}


def test_cli_failure_emits_no_partial_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    test_file = _tracked_test_file(
        tmp_path,
        "def test_one():\n    assert False\n",
    )
    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.w2_automated_report."
        "verify_w2_candidate_checkout",
        lambda **_: _CANDIDATE_SHA,
    )
    assert (
        main(
            [
                "--candidate-sha",
                _CANDIDATE_SHA,
                "--suite-id",
                "gate1-automated",
                "--subject",
                "automated:gate1-automated",
                "--subject",
                "review:gate1",
                "--pytest-target",
                test_file.name,
                "--repository",
                str(tmp_path),
            ]
        )
        == 2
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "W2_AUTOMATED_REPORT_ERROR" in captured.err


def test_cli_rejects_foreign_target_before_pytest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repository = tmp_path / "candidate"
    _tracked_test_file(repository, "def test_candidate():\n    assert True\n")
    foreign = tmp_path / "foreign_test.py"
    foreign.write_text("def test_one():\n    assert True\n", encoding="utf-8")
    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.w2_automated_report."
        "verify_w2_candidate_checkout",
        lambda **_: _CANDIDATE_SHA,
    )
    assert (
        main(
            [
                "--candidate-sha",
                _CANDIDATE_SHA,
                "--suite-id",
                "gate1-automated",
                "--subject",
                "automated:gate1-automated",
                "--pytest-target",
                str(foreign),
                "--repository",
                str(repository),
            ]
        )
        == 2
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "inside the candidate repository" in captured.err


def test_cli_rejects_ignored_untracked_target_inside_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repository = tmp_path / "candidate"
    _tracked_test_file(repository, "def test_candidate():\n    assert True\n")
    ignore = repository / ".gitignore"
    ignore.write_text("ignored/\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "--", ignore.name],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    subprocess.run(
        ["git", "commit", "-q", "-m", "ignore test scratch"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    ignored = repository / "ignored" / "test_fake_pass.py"
    ignored.parent.mkdir()
    ignored.write_text("def test_fake():\n    assert True\n", encoding="utf-8")
    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.w2_automated_report."
        "verify_w2_candidate_checkout",
        lambda **_: _CANDIDATE_SHA,
    )
    assert (
        main(
            [
                "--candidate-sha",
                _CANDIDATE_SHA,
                "--suite-id",
                "gate1-automated",
                "--subject",
                "automated:gate1-automated",
                "--pytest-target",
                str(ignored),
                "--repository",
                str(repository),
            ]
        )
        == 2
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "exact tracked candidate file" in captured.err


def test_cli_revalidates_candidate_after_pytest_before_stdout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    test_file = _tracked_test_file(
        tmp_path,
        "def test_one():\n    assert True\n",
    )
    calls = 0

    def verify(**_: object) -> str:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ValueError("candidate became dirty")
        return _CANDIDATE_SHA

    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.w2_automated_report."
        "verify_w2_candidate_checkout",
        verify,
    )
    assert (
        main(
            [
                "--candidate-sha",
                _CANDIDATE_SHA,
                "--suite-id",
                "gate1-automated",
                "--subject",
                "automated:gate1-automated",
                "--pytest-target",
                test_file.name,
                "--repository",
                str(tmp_path),
            ]
        )
        == 2
    )
    captured = capsys.readouterr()
    assert calls == 2
    assert captured.out == ""
    assert "candidate became dirty" in captured.err


def test_cli_candidate_verifier_error_is_contract_exit_without_traceback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    test_file = _tracked_test_file(
        tmp_path,
        "def test_one():\n    assert True\n",
    )
    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.w2_automated_report."
        "verify_w2_candidate_checkout",
        lambda **_: (_ for _ in ()).throw(
            W2EvidenceExporterError("candidate checkout must be clean")
        ),
    )
    assert (
        main(
            [
                "--candidate-sha",
                _CANDIDATE_SHA,
                "--suite-id",
                "gate1-automated",
                "--subject",
                "automated:gate1-automated",
                "--pytest-target",
                test_file.name,
                "--repository",
                str(tmp_path),
            ]
        )
        == 2
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "candidate checkout must be clean" in captured.err
