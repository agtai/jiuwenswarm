"""Unit tests for the repository-activity-digest output-language check."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

_SCRIPT = (
    Path(__file__).resolve().parents[3]
    / "local_skills"
    / "repository-activity-digest"
    / "scripts"
    / "check_report_language.py"
)


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "check_report_language_under_test", _SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def checker() -> ModuleType:
    return _load_module()


def _verdicts(checker: ModuleType, text: str, language: str = "en") -> list[str]:
    expected = checker._LANGUAGE_SCRIPTS[language]
    return [str(finding["verdict"]) for finding in checker.check(text, expected)]


def test_report_in_the_output_language_is_clean(checker: ModuleType) -> None:
    report = (
        "*JiuwenSwarm Daily Intelligence — 2026-08-11*\n"
        "• 🔴 *High Bug Density* — critical bugs in `team` and `code` modes.\n"
        "   [FACT] Improved connection handling during disconnects.\n"
        "   Evidence: <https://github.com/owner/name/pull/2694|PR #2694>\n"
        "• *Feature Development* — → Stable\n"
    )
    assert _verdicts(checker, report) == []


def test_pasted_source_title_is_reported(checker: ModuleType) -> None:
    report = "   [FACT] [Bug]: 点击取消任务后，后台还在执行\n"
    assert _verdicts(checker, report) == ["UNGLOSSED"]


def test_rendering_with_the_original_in_parentheses_passes(checker: ModuleType) -> None:
    report = (
        "   [FACT] Cancelling a task leaves it running in the background\n"
        "          (原文：点击取消任务后，后台还在执行)\n"
    )
    # The parenthetical wraps onto its own continuation line, which is the
    # format working correctly: the rendering that licenses it is the line
    # above, in the same block.
    assert _verdicts(checker, report) == []

    inline = (
        "   [FACT] Cancelling a task leaves it running in the background "
        "(原文：点击取消任务后，后台还在执行)\n"
    )
    assert _verdicts(checker, inline) == []


def test_original_ahead_of_its_rendering_is_reported(checker: ModuleType) -> None:
    report = "• (原文：点击取消任务后) the task keeps running in the background\n"
    assert _verdicts(checker, report) == ["LEADS"]


def test_a_blank_line_ends_the_block_that_licenses_a_gloss(
    checker: ModuleType,
) -> None:
    report = (
        "   [FACT] Cancelling a task leaves it running in the background\n"
        "\n"
        "          (原文：点击取消任务后，后台还在执行)\n"
    )
    assert _verdicts(checker, report) == ["LEADS"]


def test_url_targets_are_not_prose(checker: ModuleType) -> None:
    report = "   Evidence: <https://example.invalid/文档/1403|#1403>\n"
    assert _verdicts(checker, report) == []

    markdown = "   Evidence: [#1403](https://example.invalid/文档/1403)\n"
    assert _verdicts(checker, markdown) == []


def test_emoji_arrows_and_dashes_carry_no_language(checker: ModuleType) -> None:
    report = "• 🔴 *Bug Reporting* — ↑ Rising · Confidence: High\n"
    assert _verdicts(checker, report) == []


def test_the_same_text_is_clean_when_that_is_the_output_language(
    checker: ModuleType,
) -> None:
    report = "   [FACT] [Bug]: 点击取消任务后，后台还在执行\n"
    assert _verdicts(checker, report, language="zh") == []


def test_latin_names_survive_a_non_latin_output_language(checker: ModuleType) -> None:
    report = "   [FACT] JiuwenSwarm 的 dev-stable 分支已合入\n"
    assert _verdicts(checker, report, language="zh") == []


def test_a_run_is_reported_once_across_its_own_punctuation(
    checker: ModuleType,
) -> None:
    expected = checker._LANGUAGE_SCRIPTS["en"]
    findings = checker.check("   [FACT] 定时任务缺少运行状态、结果归属和完成反馈\n", expected)
    assert len(findings) == 1
    assert findings[0]["text"] == "定时任务缺少运行状态、结果归属和完成反馈"


def test_explicit_language_wins_over_the_installation(
    checker: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = tmp_path / "config"
    config.mkdir()
    (config / "config.yaml").write_text("preferred_language: zh\n", encoding="utf-8")
    monkeypatch.setenv("JIUWENSWARM_HOME", str(tmp_path))

    assert checker.resolve_language(None) == ("zh", str(config / "config.yaml"))
    assert checker.resolve_language("en") == ("en", "--language")


def test_english_is_the_last_resort(
    checker: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("JIUWENSWARM_HOME", str(tmp_path))
    assert checker.resolve_language(None) == ("en", "default")


def test_an_unrecognised_language_does_not_block_a_report(
    checker: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("JIUWENSWARM_HOME", str(tmp_path))
    report = tmp_path / "report.md"
    report.write_text("   [FACT] [Bug]: 点击取消任务后\n", encoding="utf-8")

    assert checker.main([str(report), "--language", "xx"]) == 0
    assert checker.main([str(report), "--language", "en"]) == 1


def test_a_missing_report_is_an_invocation_error(
    checker: ModuleType, tmp_path: Path
) -> None:
    assert checker.main([str(tmp_path / "absent.md")]) == 2
