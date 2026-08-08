# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Create one canonical W2 automated report from closed JUnit results.

The report generator has no product authority and does not sign artifacts.  It
only converts complete, passing JUnit result documents into the closed schema
accepted by :mod:`w2_demo_gate`.  The CLI binds that conversion to the clean
Git checkout which loaded this module and writes the report to stdout only.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from xml.etree import ElementTree

from jiuwenswarm.server.live_voice.w2_demo_gate import (
    MAX_W2_EVIDENCE_IDS,
    W2LedgerItem,
)
from jiuwenswarm.server.live_voice.w2_evidence_exporter import (
    W2EvidenceExporterError,
    verify_w2_candidate_checkout,
)


AUTOMATED_REPORT_SCHEMA = "live-voice.w2-automated-report.v2"
MAX_JUNIT_DOCUMENTS = 64
MAX_JUNIT_DOCUMENT_BYTES = 16 * 1024 * 1024
MAX_JUNIT_TESTCASES = 100_000
MAX_JUNIT_SUITE_DEPTH = 64
PYTEST_TIMEOUT_SECONDS = 15 * 60
_MAX_LABEL_CHARACTERS = 256
_MAX_LABEL_UTF8_BYTES = 1_024
_SENSITIVE_MARKER = re.compile(
    r"(?:^|[._:@-])(?:api[-_]?key|access[-_]?token|authorization|bearer|password|"
    r"passwd|secret|credential|transcript|raw[-_]?audio|audio[-_]?bytes|"
    r"data[-_]?base64)(?:$|[=._:@-])",
    re.IGNORECASE,
)
_INTEGER = re.compile(r"0|[1-9][0-9]*")
_CASE_RESULT_TAGS = frozenset({"failure", "error", "skipped"})
_FLAKY_TAGS = frozenset(
    {"rerun", "flakyFailure", "flakyError", "rerunFailure", "rerunError"}
)
_TESTSUITES_ATTRIBUTES = frozenset({"name"})
_TESTSUITE_ATTRIBUTES = frozenset(
    {
        "name",
        "errors",
        "failures",
        "skipped",
        "tests",
        "time",
        "timestamp",
        "hostname",
        "disabled",
    }
)
_TESTCASE_ATTRIBUTES = frozenset({"classname", "name", "time"})


class W2AutomatedReportError(ValueError):
    """Raised when JUnit input cannot prove a closed passing test suite."""


@dataclass(frozen=True, slots=True)
class W2JUnitSummary:
    """Deterministic facts derived from one or more JUnit documents."""

    document_count: int
    suite_count: int
    testcase_count: int
    testcase_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _SuiteCounts:
    tests: int
    failures: int
    errors: int
    skipped: int
    suites: int
    testcase_ids: tuple[str, ...]


def _opaque_label(value: object, field: str) -> str:
    if type(value) is not str or not value or len(value) > _MAX_LABEL_CHARACTERS:
        raise W2AutomatedReportError(f"{field} must be non-empty bounded text")
    try:
        encoded = value.encode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise W2AutomatedReportError(f"{field} must be valid UTF-8 text") from exc
    if len(encoded) > _MAX_LABEL_UTF8_BYTES:
        raise W2AutomatedReportError(f"{field} exceeds the UTF-8 byte limit")
    if any(character.isspace() for character in value):
        raise W2AutomatedReportError(f"{field} must be an opaque label")
    if _SENSITIVE_MARKER.search(value) is not None:
        raise W2AutomatedReportError(f"{field} contains a sensitive marker")
    return value


def _local_tag(element: ElementTree.Element) -> str:
    if type(element.tag) is not str:
        raise W2AutomatedReportError(
            "JUnit comments and processing instructions are not accepted"
        )
    if element.tag.startswith("{"):
        raise W2AutomatedReportError("JUnit XML namespaces are not accepted")
    return element.tag


def _closed_attributes(
    element: ElementTree.Element,
    allowed: frozenset[str],
    field: str,
) -> None:
    unknown = set(element.attrib) - allowed
    if unknown:
        raise W2AutomatedReportError(
            f"{field} contains unsupported attributes: {sorted(unknown)!r}"
        )


def _closed_mixed_text(element: ElementTree.Element, field: str) -> None:
    if element.text is not None and not element.text.isspace():
        raise W2AutomatedReportError(f"{field} contains non-whitespace mixed text")
    if any(child.tail is not None and not child.tail.isspace() for child in element):
        raise W2AutomatedReportError(f"{field} contains non-whitespace mixed text")


def _counter(element: ElementTree.Element, field: str) -> int:
    raw = element.attrib.get(field)
    if raw is None or _INTEGER.fullmatch(raw) is None:
        raise W2AutomatedReportError(
            f"JUnit testsuite {field} must be a non-negative integer"
        )
    value = int(raw)
    if value > MAX_JUNIT_TESTCASES:
        raise W2AutomatedReportError(f"JUnit testsuite {field} exceeds the limit")
    return value


def _optional_counter(element: ElementTree.Element, field: str) -> int | None:
    raw = element.attrib.get(field)
    if raw is None:
        return None
    if _INTEGER.fullmatch(raw) is None:
        raise W2AutomatedReportError(
            f"JUnit aggregate {field} must be a non-negative integer"
        )
    value = int(raw)
    if value > MAX_JUNIT_TESTCASES:
        raise W2AutomatedReportError(f"JUnit aggregate {field} exceeds the limit")
    return value


def _testcase_identity(element: ElementTree.Element) -> str:
    classname = element.attrib.get("classname", "")
    name = element.attrib.get("name")
    if not name:
        raise W2AutomatedReportError("every JUnit testcase must have a name")
    # Pytest emits an empty classname for test modules outside its resolved
    # rootdir.  This is still a real xunit2 result, so retain an explicit
    # sentinel rather than rejecting it or silently dropping identity.
    identity = f"{classname or '<root>'}::{name}"
    if len(identity) > 4_096 or any(character in identity for character in "\r\n\0"):
        raise W2AutomatedReportError("JUnit testcase identity is invalid")
    return identity


def _parse_testcase(element: ElementTree.Element) -> _SuiteCounts:
    _closed_attributes(element, _TESTCASE_ATTRIBUTES, "JUnit testcase")
    _closed_mixed_text(element, "JUnit testcase")
    identity = _testcase_identity(element)
    result_tags: list[str] = []
    for child in element:
        tag = _local_tag(child)
        if tag in _FLAKY_TAGS:
            raise W2AutomatedReportError(
                f"JUnit testcase {identity} contains a flaky/rerun result"
            )
        if tag in _CASE_RESULT_TAGS:
            result_tags.append(tag)
        else:
            raise W2AutomatedReportError(
                f"JUnit testcase {identity} contains unsupported result tag {tag!r}"
            )
    if len(result_tags) > 1:
        raise W2AutomatedReportError(
            f"JUnit testcase {identity} contains contradictory results"
        )
    result = result_tags[0] if result_tags else None
    return _SuiteCounts(
        tests=1,
        failures=int(result == "failure"),
        errors=int(result == "error"),
        skipped=int(result == "skipped"),
        suites=0,
        testcase_ids=(identity,),
    )


def _assert_declared_counts(
    element: ElementTree.Element,
    actual: _SuiteCounts,
    *,
    aggregate: bool,
) -> None:
    for field in ("tests", "failures", "errors", "skipped"):
        declared = (
            _optional_counter(element, field) if aggregate else _counter(element, field)
        )
        if declared is not None and declared != getattr(actual, field):
            raise W2AutomatedReportError(
                f"JUnit declared {field} count does not match testcase results"
            )
    disabled = _optional_counter(element, "disabled")
    if disabled not in {None, 0}:
        raise W2AutomatedReportError("disabled JUnit tests are not accepted")


def _parse_testsuite(
    element: ElementTree.Element,
    *,
    depth: int = 1,
) -> _SuiteCounts:
    if _local_tag(element) != "testsuite":
        raise W2AutomatedReportError("expected one JUnit testsuite")
    _closed_attributes(element, _TESTSUITE_ATTRIBUTES, "JUnit testsuite")
    _closed_mixed_text(element, "JUnit testsuite")
    if depth > MAX_JUNIT_SUITE_DEPTH:
        raise W2AutomatedReportError("JUnit testsuite nesting exceeds the limit")
    tests = failures = errors = skipped = suites = 0
    testcase_ids: list[str] = []
    for child in element:
        tag = _local_tag(child)
        if tag == "testcase":
            parsed = _parse_testcase(child)
        elif tag == "testsuite":
            parsed = _parse_testsuite(child, depth=depth + 1)
        else:
            raise W2AutomatedReportError(
                f"JUnit testsuite contains unsupported tag {tag!r}"
            )
        tests += parsed.tests
        failures += parsed.failures
        errors += parsed.errors
        skipped += parsed.skipped
        suites += parsed.suites
        testcase_ids.extend(parsed.testcase_ids)
    actual = _SuiteCounts(
        tests=tests,
        failures=failures,
        errors=errors,
        skipped=skipped,
        suites=suites + 1,
        testcase_ids=tuple(testcase_ids),
    )
    _assert_declared_counts(element, actual, aggregate=False)
    if actual.tests == 0:
        raise W2AutomatedReportError("every JUnit testsuite must contain a testcase")
    return actual


def _parse_document(content: bytes) -> _SuiteCounts:
    if type(content) is not bytes or not content:
        raise W2AutomatedReportError("JUnit input must be non-empty bytes")
    if len(content) > MAX_JUNIT_DOCUMENT_BYTES:
        raise W2AutomatedReportError("JUnit input exceeds the byte limit")
    try:
        text = content.decode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise W2AutomatedReportError("JUnit input must be strict UTF-8 XML") from exc
    if "\0" in text:
        raise W2AutomatedReportError("JUnit input must be strict UTF-8 XML")
    inspection = text.removeprefix("\ufeff")
    if inspection.startswith("<?xml"):
        declaration_end = inspection.find("?>")
        if declaration_end < 0:
            raise W2AutomatedReportError("JUnit XML declaration is not closed")
        inspection = inspection[declaration_end + 2 :]
    lowered = inspection.lower()
    if "<!doctype" in lowered or "<!entity" in lowered:
        raise W2AutomatedReportError("JUnit DTD/entity declarations are not accepted")
    if "<!--" in inspection:
        raise W2AutomatedReportError("JUnit comments are not accepted")
    if "<?" in inspection:
        raise W2AutomatedReportError("JUnit processing instructions are not accepted")
    try:
        root = ElementTree.fromstring(
            content,
            parser=ElementTree.XMLParser(
                target=ElementTree.TreeBuilder(insert_comments=True, insert_pis=True)
            ),
        )
    except (ElementTree.ParseError, ValueError) as exc:
        raise W2AutomatedReportError("JUnit input is not valid XML") from exc
    root_tag = _local_tag(root)
    if root_tag == "testsuite":
        return _parse_testsuite(root)
    if root_tag != "testsuites":
        raise W2AutomatedReportError("JUnit root must be testsuite or testsuites")
    _closed_attributes(root, _TESTSUITES_ATTRIBUTES, "JUnit testsuites")
    _closed_mixed_text(root, "JUnit testsuites")
    tests = failures = errors = skipped = suites = 0
    testcase_ids: list[str] = []
    for child in root:
        tag = _local_tag(child)
        if tag == "testsuite":
            parsed = _parse_testsuite(child)
        else:
            raise W2AutomatedReportError(
                f"JUnit testsuites contains unsupported tag {tag!r}"
            )
        tests += parsed.tests
        failures += parsed.failures
        errors += parsed.errors
        skipped += parsed.skipped
        suites += parsed.suites
        testcase_ids.extend(parsed.testcase_ids)
    if suites == 0:
        raise W2AutomatedReportError("JUnit document contains no testsuite")
    actual = _SuiteCounts(
        tests=tests,
        failures=failures,
        errors=errors,
        skipped=skipped,
        suites=suites,
        testcase_ids=tuple(testcase_ids),
    )
    _assert_declared_counts(root, actual, aggregate=True)
    return actual


def summarize_w2_junit_results(
    junit_documents: Sequence[bytes],
) -> W2JUnitSummary:
    """Validate complete JUnit documents and return their deterministic facts."""

    if (
        isinstance(junit_documents, (bytes, bytearray, str))
        or not isinstance(junit_documents, Sequence)
        or not junit_documents
        or len(junit_documents) > MAX_JUNIT_DOCUMENTS
    ):
        raise W2AutomatedReportError(
            f"JUnit input must contain 1 to {MAX_JUNIT_DOCUMENTS} documents"
        )
    tests = failures = errors = skipped = suites = 0
    testcase_ids: list[str] = []
    for content in junit_documents:
        parsed = _parse_document(content)
        tests += parsed.tests
        failures += parsed.failures
        errors += parsed.errors
        skipped += parsed.skipped
        suites += parsed.suites
        testcase_ids.extend(parsed.testcase_ids)
        if tests > MAX_JUNIT_TESTCASES:
            raise W2AutomatedReportError("JUnit testcase total exceeds the limit")
    if tests == 0:
        raise W2AutomatedReportError("JUnit input contains no testcases")
    if failures or errors or skipped:
        raise W2AutomatedReportError(
            "JUnit input is not a closed pass "
            f"(failures={failures}, errors={errors}, skipped={skipped})"
        )
    if len(set(testcase_ids)) != len(testcase_ids):
        raise W2AutomatedReportError(
            "JUnit inputs contain duplicate testcase identities or reruns"
        )
    return W2JUnitSummary(
        document_count=len(junit_documents),
        suite_count=suites,
        testcase_count=tests,
        testcase_ids=tuple(sorted(testcase_ids)),
    )


def create_w2_automated_report(
    *,
    candidate_sha: str,
    suite_id: str,
    passed_subjects: Sequence[str],
    junit_documents: Sequence[bytes],
) -> bytes:
    """Return canonical report bytes only when all JUnit inputs fully pass."""

    if re.fullmatch(r"[0-9a-f]{40}", candidate_sha) is None:
        raise W2AutomatedReportError("candidate_sha must be a full lowercase Git SHA")
    suite_id = _opaque_label(suite_id, "suite_id")
    if (
        isinstance(passed_subjects, (bytes, bytearray, str))
        or not isinstance(passed_subjects, Sequence)
        or not passed_subjects
        or len(passed_subjects) > MAX_W2_EVIDENCE_IDS
    ):
        raise W2AutomatedReportError(
            f"passed_subjects must contain 1 to {MAX_W2_EVIDENCE_IDS} labels"
        )
    subjects = tuple(
        sorted(_opaque_label(subject, "passed subject") for subject in passed_subjects)
    )
    if len(set(subjects)) != len(subjects):
        raise W2AutomatedReportError("passed_subjects must not contain duplicates")
    if f"automated:{suite_id}" not in subjects:
        raise W2AutomatedReportError(
            "passed_subjects must include the exact automated suite binding"
        )
    forbidden_ledger_subjects = {
        subject
        for subject in subjects
        if subject.startswith("ledger:")
        and subject != f"ledger:{W2LedgerItem.CROSS_FLAG_OFF.value}"
    }
    if forbidden_ledger_subjects:
        raise W2AutomatedReportError(
            "automated reports cannot claim runtime ledger behavior"
        )
    summarize_w2_junit_results(junit_documents)
    payload = {
        "schema": AUTOMATED_REPORT_SCHEMA,
        "candidate_sha": candidate_sha,
        "suite_id": suite_id,
        "passed_subjects": list(subjects),
    }
    return (
        json.dumps(
            payload,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )


def _pytest_target(repository: Path, raw_target: object) -> str:
    target = str(raw_target or "")
    if (
        not target
        or target.startswith("-")
        or len(target) > 4_096
        or any(character in target for character in "\r\n\0")
    ):
        raise W2AutomatedReportError("pytest target is invalid")
    path_text = target.split("::", maxsplit=1)[0]
    selector = target[len(path_text) :]
    target_path = Path(path_text)
    if not target_path.is_absolute():
        target_path = repository / target_path
    resolved = target_path.resolve()
    if not resolved.is_relative_to(repository) or not resolved.is_file():
        raise W2AutomatedReportError(
            "pytest target must be one file inside the candidate repository"
        )
    relative = resolved.relative_to(repository)
    git_path = relative.as_posix()
    try:
        subprocess.run(
            [
                "git",
                "-C",
                str(repository),
                "ls-files",
                "--error-unmatch",
                "--",
                git_path,
            ],
            check=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
        subprocess.run(
            ["git", "-C", str(repository), "cat-file", "-e", f"HEAD:{git_path}"],
            check=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise W2AutomatedReportError(
            "pytest target must be an exact tracked candidate file"
        ) from exc
    return f"{git_path}{selector}"


def _run_candidate_pytest(
    *,
    repository: Path,
    targets: Sequence[str],
) -> bytes:
    if not targets or len(targets) > MAX_JUNIT_DOCUMENTS:
        raise W2AutomatedReportError(
            f"pytest requires 1 to {MAX_JUNIT_DOCUMENTS} exact targets"
        )
    exact_targets = tuple(_pytest_target(repository, target) for target in targets)
    pytest_environment = dict(os.environ)
    pytest_environment.update(
        {
            "PYTHONPATH": str(repository),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTEST_ADDOPTS": "",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            "PYTEST_PLUGINS": "",
        }
    )
    try:
        with tempfile.TemporaryDirectory(prefix="jiuwenswarm-w2-junit-") as directory:
            junit_path = Path(directory) / "pytest.xml"
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "-q",
                    "--tb=no",
                    "-p",
                    "no:cacheprovider",
                    "-p",
                    "no:rerunfailures",
                    "-p",
                    "pytest_asyncio.plugin",
                    "-p",
                    "anyio.pytest_plugin",
                    "-o",
                    "addopts=",
                    "-o",
                    "junit_family=xunit2",
                    "-o",
                    "junit_logging=no",
                    f"--junitxml={junit_path}",
                    *exact_targets,
                ],
                cwd=repository,
                env=pytest_environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=PYTEST_TIMEOUT_SECONDS,
            )
            if completed.returncode != 0:
                raise W2AutomatedReportError(
                    f"pytest did not pass (exit_code={completed.returncode})"
                )
            if not junit_path.is_file():
                raise W2AutomatedReportError("pytest did not create its JUnit result")
            size = junit_path.stat().st_size
            if size <= 0 or size > MAX_JUNIT_DOCUMENT_BYTES:
                raise W2AutomatedReportError("pytest JUnit result size is invalid")
            return junit_path.read_bytes()
    except subprocess.TimeoutExpired as exc:
        raise W2AutomatedReportError("pytest exceeded the bounded timeout") from exc
    except OSError as exc:
        raise W2AutomatedReportError(
            "pytest JUnit result could not be collected"
        ) from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m jiuwenswarm.server.live_voice.w2_automated_report",
        description="Generate one canonical W2 automated report on stdout.",
    )
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--suite-id", required=True)
    parser.add_argument("--subject", action="append", required=True)
    parser.add_argument(
        "--pytest-target",
        action="append",
        required=True,
        help="exact tracked candidate test file or node id",
    )
    parser.add_argument(
        "--repository",
        type=Path,
        default=Path.cwd(),
        help="candidate repository (default: current directory)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point; no report bytes are written unless every check passes."""

    args = _parser().parse_args(argv)
    try:
        repository = args.repository.resolve()
        verify_w2_candidate_checkout(
            repository_path=repository,
            candidate_sha=args.candidate_sha,
            bind_loaded_source=True,
        )
        junit = _run_candidate_pytest(
            repository=repository,
            targets=args.pytest_target,
        )
        # Tests are executable candidate code and may write into the checkout.
        # Revalidate after the run so such effects cannot receive a clean
        # candidate claim.
        verify_w2_candidate_checkout(
            repository_path=repository,
            candidate_sha=args.candidate_sha,
            bind_loaded_source=True,
        )
        report = create_w2_automated_report(
            candidate_sha=args.candidate_sha,
            suite_id=args.suite_id,
            passed_subjects=args.subject,
            junit_documents=(junit,),
        )
    except (OSError, ValueError, W2EvidenceExporterError) as exc:
        print(f"W2_AUTOMATED_REPORT_ERROR: {exc}", file=sys.stderr)
        return 2
    sys.stdout.buffer.write(report)
    sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "AUTOMATED_REPORT_SCHEMA",
    "MAX_JUNIT_DOCUMENT_BYTES",
    "MAX_JUNIT_DOCUMENTS",
    "MAX_JUNIT_SUITE_DEPTH",
    "MAX_JUNIT_TESTCASES",
    "PYTEST_TIMEOUT_SECONDS",
    "W2AutomatedReportError",
    "W2JUnitSummary",
    "create_w2_automated_report",
    "main",
    "summarize_w2_junit_results",
]
