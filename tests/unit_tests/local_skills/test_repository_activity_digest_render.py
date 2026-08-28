"""Unit tests for the repository-activity-digest report renderer.

The renderer exists because a freely composed report varied day to day and
invented its own numbers. These tests pin the two properties that buy back:
every count comes from the run, and nothing a caller supplies can put a
filesystem path, an unlabelled conclusion or an unlinked claim into the channel.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_SKILL = (
    Path(__file__).resolve().parents[3]
    / "local_skills"
    / "repository-activity-digest"
)
_SCRIPT = _SKILL / "scripts" / "render_report.py"


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("render_report_under_test", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def renderer() -> ModuleType:
    return _load_module()


def _activity(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "repository": "example/repo",
        "generated_at_utc": "2026-08-14T06:00:20.909922Z",
        "windows": {
            "daily": {
                "requested_hours": 24.0,
                "start_utc": "2026-08-13T06:00:06Z",
                "end_utc": "2026-08-14T06:00:20Z",
                "catch_up_from_state": True,
            },
            "seven_day": {"start_utc": "2026-08-07T06:00:20Z"},
            "history": {"days": 30.0, "start_utc": "2026-07-15T06:00:20Z"},
        },
        "coverage": {"warnings": []},
        "window_counts": {
            "daily": {"issues_created": 122, "commits": 31},
            "seven_day": {"issues_created": 296, "commits": 106},
            "history": {"issues_created": 533, "commits": 532},
        },
        "state": {
            "written": True,
            "last_success_utc": "2026-08-14T06:00:20.909922Z",
        },
    }
    payload.update(overrides)
    return payload


def _findings(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "tldr": [{"severity": "critical", "text": "A thing broke"}],
        "significant_changes": [
            {
                "title": "A change",
                "text": "It landed",
                "evidence": [{"label": "PR #1", "url": "https://example.com/pull/1"}],
            }
        ],
    }
    payload.update(overrides)
    return payload


# Every section the report has, in the order it has them. This is the whole
# contract of the renderer's shape: two runs differ in what their sections say
# and never in which sections they have.
_SECTIONS = (
    "*TL;DR*",
    "*Significant Changes*",
    "*Risks and Blockers*",
    "*Recommended Actions*",
    "*Activity in numbers*",
    "*Trend Signals*",
    "*Missing Capabilities*",
    "*Opportunities for Our Team*",
    "*Evidence Gaps*",
    "*Reporting Shortfalls*",
)

# One entry in each of the optional keys, so a report with everything filled in
# can be compared against one with nothing filled in.
_FULL_FINDINGS: dict[str, Any] = {
    "risks": [{"severity": "critical", "text": "CI is red on main"}],
    "actions": [{"text": "Unblock the release"}],
    "trends": [
        {
            "theme": "Tools",
            "direction": "rising",
            "text": "More tool work",
            "confidence": "high",
            "evidence": [{"label": "#2", "url": "https://example.com/issues/2"}],
        }
    ],
    "missing_capabilities": {"explicit": [{"text": "No Windows runner"}]},
    "opportunities": [{"title": "A thing", "kind": "Systems engineering"}],
    "evidence_gaps": {"unknown": [{"text": "Adoption is unmeasured"}]},
}


def _headings(text: str) -> tuple[str, ...]:
    """Return the section headings the report actually has, in order."""
    return tuple(line for line in text.splitlines() if line in _SECTIONS)


class TestCountsComeFromTheRun:
    """The measured half of the report is not writable by the caller."""

    def test_table_reports_the_runs_own_counts(self, renderer: ModuleType) -> None:
        text = renderer.render(_activity(), _findings())
        assert "| Issues opened | 122 | 296 | 533 |" in text
        assert "| Commits | 31 | 106 | 532 |" in text

    def test_findings_cannot_introduce_a_count(self, renderer: ModuleType) -> None:
        # A trend signal is where per-theme figures were invented. There is no
        # field for one, so a caller that supplies it changes nothing.
        findings = _findings(
            trends=[
                {
                    "theme": "Tools",
                    "direction": "rising",
                    "text": "More reports",
                    "confidence": "high",
                    "daily": 71,
                    "seven_day": 0,
                    "evidence": [{"label": "#2", "url": "https://example.com/issues/2"}],
                }
            ]
        )
        text = renderer.render(_activity(), findings)
        assert "*Tools* — ↑ Rising" in text
        assert "71" not in text
        assert "7d: 0" not in text

    def test_a_capped_endpoint_leaves_wider_windows_uncounted(
        self, renderer: ModuleType
    ) -> None:
        # A truncated seven-day count equals its daily count exactly, which reads
        # as a quiet week rather than as missing data.
        activity = _activity(
            coverage={
                "warnings": [
                    "issues: pagination stopped at 10 pages before the requested "
                    "history boundary"
                ]
            }
        )
        text = renderer.render(activity, _findings())
        assert "| Issues opened | 122 | n/a | n/a |" in text
        assert "| Commits | 31 | 106 | 532 |" in text
        assert "Coverage: issues: pagination stopped" in text


class TestNothingLeaksIntoTheChannel:
    def test_a_path_in_a_finding_is_refused(self, renderer: ModuleType) -> None:
        findings = _findings(
            tldr=[{"text": "Report at /home/someone/workspace/projects/report.md"}]
        )
        with pytest.raises(renderer.RenderError, match="filesystem path"):
            renderer.render(_activity(), findings)

    def test_the_rendered_report_names_no_file(self, renderer: ModuleType) -> None:
        text = renderer.render(_activity(), _findings())
        # The renderer's own detector is the guarantee; asserting on "/" would
        # catch "example/repo" and every https:// evidence link instead.
        renderer._reject_paths(text, where="test")
        assert "raw_output" not in text
        assert "state_file" not in text

    def test_an_evidence_label_cannot_carry_link_syntax(
        self, renderer: ModuleType
    ) -> None:
        # The caption is decoration and the url is the reference, so the url
        # takes the caption's place rather than the reference being lost.
        findings = _findings(
            significant_changes=[
                {
                    "title": "A change",
                    "text": "It landed",
                    "evidence": [
                        {"label": "PR|#1", "url": "https://example.com/pull/1"}
                    ],
                }
            ]
        )
        text = renderer.render(_activity(), findings)
        assert "PR|#1" not in text
        assert (
            "<https://example.com/pull/1|https://example.com/pull/1>" in text
        )
        assert "an evidence label contained link syntax" in text

    def test_an_unfollowable_evidence_url_is_dropped_not_published(
        self, renderer: ModuleType
    ) -> None:
        # A `file://` reference is the case the path detector cannot see, because
        # it only recognises a path that starts a word. Dropped here, it never
        # reaches the assembled text for the detector to miss.
        findings = _findings(
            significant_changes=[
                {
                    "title": "A change",
                    "text": "It landed",
                    "evidence": [{"label": "the dump", "url": "file:///home/x/y.json"}],
                }
            ]
        )
        text = renderer.render(_activity(), findings)
        assert "file://" not in text and "/home/x" not in text
        assert "No evidence link" in text


class TestTheShapeDoesNotDriftBetweenRuns:
    def test_the_title_carries_no_deployment_name(self, renderer: ModuleType) -> None:
        text = renderer.render(_activity(), _findings())
        assert text.startswith("*Repository intelligence — example/repo — 2026-08-14*")
        titled = renderer.render(_activity(), _findings(), title="Morning brief")
        assert titled.startswith("*Morning brief — example/repo — 2026-08-14*")

    def test_sections_and_marker_are_fixed(self, renderer: ModuleType) -> None:
        text = renderer.render(_activity(), _findings())
        positions = [text.index(item) for item in _SECTIONS]
        assert positions == sorted(positions)
        assert text.count(renderer._THREAD_MARKER) == 1

    def test_empty_sections_say_so_rather_than_vanishing(
        self, renderer: ModuleType
    ) -> None:
        # Findings holding only the two required keys still produce every
        # section. A section that disappears cannot be told apart from one
        # nobody filled in, and the reader never learns it was considered.
        text = renderer.render(_activity(), _findings())
        assert "*Risks and Blockers*\n• None identified in this window." in text
        assert (
            "*Recommended Actions*\n• None; nothing in this window calls for one."
            in text
        )
        assert (
            "*Trend Signals*\n• None; no theme moved enough this window to state "
            "a direction." in text
        )
        assert "*Missing Capabilities*\n• None identified in this window." in text
        assert (
            "*Opportunities for Our Team*\n• None identified in this window." in text
        )
        assert "*Evidence Gaps*\n• None recorded for this window." in text
        assert (
            "*Reporting Shortfalls*\n• None; every item in this report met the "
            "reporting rules." in text
        )

    def test_the_section_set_does_not_depend_on_what_was_filled_in(
        self, renderer: ModuleType
    ) -> None:
        # The observed failure: consecutive runs over a window whose measured
        # counts were unchanged dropped and restored three sections, because
        # each was rendered only when its key happened to be populated. What
        # differs between two reports has to be what the runs found.
        quiet = renderer.render(_activity(), _findings())
        busy = renderer.render(_activity(), _findings(**_FULL_FINDINGS))
        assert _headings(quiet) == _headings(busy) == _SECTIONS

    def test_rendering_is_deterministic(self, renderer: ModuleType) -> None:
        first = renderer.render(_activity(), _findings())
        second = renderer.render(_activity(), _findings())
        assert first == second

    def test_the_section_set_is_the_same_when_something_fell_short(
        self, renderer: ModuleType
    ) -> None:
        # A shortfall changes what a section says and never which sections exist.
        clean = renderer.render(_activity(), _findings())
        short = renderer.render(
            _activity(),
            _findings(significant_changes=[{"title": "A change", "text": "It landed"}]),
        )
        assert _headings(clean) == _headings(short) == _SECTIONS


class TestTheGlossExplainsRatherThanRepeats:
    """``(original: …)`` is a claim that the two wordings differ.

    It was firing on every entry that carried an ``original`` at all, including
    the majority where the field held a copy of ``text`` — so most delivered
    reports asserted a difference between a sentence and itself.
    """

    def test_an_original_that_repeats_the_text_is_dropped(
        self, renderer: ModuleType
    ) -> None:
        sentence = "Architectural consolidation is underway."
        findings = _findings(tldr=[{"text": sentence, "original": sentence}])
        text = renderer.render(_activity(), findings)
        assert f"• 🟢 {sentence}" in text
        assert "original:" not in text

    def test_spacing_and_case_alone_are_not_a_difference(
        self, renderer: ModuleType
    ) -> None:
        findings = _findings(
            tldr=[
                {
                    "text": "High volume of pull request activity.",
                    "original": "high  volume of pull request   activity.",
                }
            ]
        )
        assert "original:" not in renderer.render(_activity(), findings)

    def test_a_source_wording_that_differs_is_kept(self, renderer: ModuleType) -> None:
        findings = _findings(
            tldr=[
                {
                    "text": "The standalone web image was made runnable.",
                    "original": "fix(docker): make standalone web image runnable",
                }
            ]
        )
        text = renderer.render(_activity(), findings)
        assert "(original: fix(docker): make standalone web image runnable)" in text

    def test_a_rendered_chinese_source_keeps_its_own_gloss(
        self, renderer: ModuleType
    ) -> None:
        findings = _findings(
            tldr=[
                {
                    "text": "A tool-call deduplication cache was added.",
                    "original": "新增工具调用去重缓存",
                }
            ]
        )
        text = renderer.render(_activity(), findings)
        assert "A tool-call deduplication cache was added. (原文：新增工具调用去重缓存)" in text

    def test_untranslated_source_reaches_the_language_gate_unglossed(
        self, renderer: ModuleType
    ) -> None:
        # Text copied into both fields was never rendered into the output
        # language. Printing it as its own gloss made the line look translated
        # and the gate pass it; dropping the copy leaves the gate to say what
        # actually happened.
        findings = _findings(
            tldr=[{"text": "新增工具调用去重缓存", "original": "新增工具调用去重缓存"}]
        )
        text = renderer.render(_activity(), findings)
        assert "原文" not in text
        assert any(
            "UNGLOSSED" in problem for problem in renderer._check_language(text, "en")
        )


class TestAFindingsFileInTheWrongShape:
    """A file sharing no key with the schema needs different advice from an
    incomplete one, and the difference decides whether the run recovers."""

    def test_an_invented_schema_is_named_as_one(self, renderer: ModuleType) -> None:
        # Observed verbatim: a flat `findings` array with `links` and its own
        # severity vocabulary. Reported as "tldr is required", the run rewrote
        # nothing and published a report it composed itself.
        invented = {
            "repository": "example/repo",
            "generated_at_utc": "2026-08-14T11:34:03Z",
            "findings": [{"id": "a", "label": "Fact", "text": "x", "links": []}],
        }
        with pytest.raises(renderer.RenderError) as caught:
            renderer.render(_activity(), invented)
        message = str(caught.value)
        assert "not in this schema" in message
        assert "significant_changes" in message and "evidence_gaps" in message
        assert "findings, generated_at_utc, repository" in message

    def test_a_merely_incomplete_file_keeps_its_own_error(
        self, renderer: ModuleType
    ) -> None:
        # One recognised key is enough to prove the shape is right, so the
        # specific complaint stays specific.
        with pytest.raises(renderer.RenderError, match="tldr"):
            renderer.render(_activity(), {"significant_changes": []})

    def test_one_recognised_key_does_not_excuse_the_content_beside_it(
        self, renderer: ModuleType
    ) -> None:
        # Observed twice in production. The file puts its whole content under
        # `findings` and happens to carry `trends` too. One recognised key was
        # enough to pass the shape test, so the run was told only that `tldr`
        # wanted a bullet -- it rewrote the same shape seven times, never
        # learning that its findings array was being dropped unread, and
        # published a report it composed itself. A key the renderer does not
        # read is harmless for a scalar and is the entire failure for a
        # populated list or object.
        half_recognised = {
            "trends": [],
            "findings": [{"id": "a", "text": "x"}],
        }
        with pytest.raises(renderer.RenderError) as caught:
            renderer.render(_activity(), half_recognised)
        message = str(caught.value)
        assert "findings" in message, "the ignored key has to be named"

    def test_a_scalar_the_writer_kept_for_itself_is_not_an_error(
        self, renderer: ModuleType
    ) -> None:
        # The converse, so the rule above cannot be tightened into refusing
        # every unrecognised key: a timestamp or a repository name alongside a
        # correct document is not content going unread.
        with pytest.raises(renderer.RenderError, match="tldr"):
            renderer.render(
                _activity(),
                {
                    "generated_at_utc": "2026-08-14T11:34:03Z",
                    "repository": "example/repo",
                    "significant_changes": [],
                },
            )


class TestOnePathInsteadOfThree:
    """Every long path the caller retypes is one it can mangle, and a mangled
    command is retried unchanged and takes the run with it."""

    def test_a_run_directory_supplies_all_three_paths(
        self, renderer: ModuleType, tmp_path: Any
    ) -> None:
        activity_file = tmp_path / "raw.json"
        activity_file.write_text(json.dumps(_activity()), encoding="utf-8")
        run_dir = tmp_path / "state.run"
        run_dir.mkdir()
        (run_dir / "run.json").write_text(
            json.dumps({"raw_output": str(activity_file)}), encoding="utf-8"
        )
        (run_dir / "findings.json").write_text(
            json.dumps(_findings()), encoding="utf-8"
        )
        assert renderer.main(["--run-dir", str(run_dir)]) == 0
        assert "*TL;DR*" in (run_dir / "report.md").read_text(encoding="utf-8")

    def test_a_run_directory_without_a_manifest_says_which_file_is_missing(
        self, renderer: ModuleType, tmp_path: Any
    ) -> None:
        run_dir = tmp_path / "state.run"
        run_dir.mkdir()
        assert renderer.main(["--run-dir", str(run_dir)]) == 2

    def test_the_explicit_flags_still_work(
        self, renderer: ModuleType, tmp_path: Any
    ) -> None:
        activity_file = tmp_path / "raw.json"
        activity_file.write_text(json.dumps(_activity()), encoding="utf-8")
        findings_file = tmp_path / "f.json"
        findings_file.write_text(json.dumps(_findings()), encoding="utf-8")
        assert (
            renderer.main(
                ["--activity", str(activity_file), "--findings", str(findings_file)]
            )
            == 0
        )

    def test_neither_form_given_is_refused(self, renderer: ModuleType) -> None:
        assert renderer.main([]) == 2


class TestTruncationReachesTheReader:
    """The report promises to state what was left out, and the value must arrive.

    Both reference files say the renderer supplies the truncation lines, so the
    writer does not state them. It read the value from a key the fetcher wrote
    only into its stdout summary, never into the file being rendered, so it
    always found nothing and printed nothing -- and a report that omits the line
    reads exactly like a run that omitted nothing.
    """

    def test_a_truncated_list_is_stated(self, renderer: ModuleType) -> None:
        activity = _activity(
            truncated={"daily_pull_requests": {"shown": 8, "total": 61}}
        )
        text = renderer.render(activity, _findings())
        assert "• Coverage: daily pull requests shows 8 of 61." in text

    def test_an_uncapped_run_states_no_truncation(self, renderer: ModuleType) -> None:
        text = renderer.render(_activity(truncated={}), _findings())
        assert "shows" not in text

    def test_items_left_uninspected_are_stated(self, renderer: ModuleType) -> None:
        # The deep-read sample is capped by --detail-limit. On a busy day the
        # remainder is most of the window, and a reader told nothing about it
        # takes the inspected handful for everything that was examined.
        activity = _activity(
            coverage={"warnings": [], "daily_detail_candidates_omitted": 483}
        )
        text = renderer.render(activity, _findings())
        assert "483 further item(s)" in text

    def test_nothing_omitted_says_nothing(self, renderer: ModuleType) -> None:
        activity = _activity(
            coverage={"warnings": [], "daily_detail_candidates_omitted": 0}
        )
        assert "further item(s)" not in renderer.render(activity, _findings())

    def test_a_truncation_line_survives_empty_findings_gaps(
        self, renderer: ModuleType
    ) -> None:
        # The run's own limits are appended to the writer's gaps, so they cannot
        # be dropped by leaving the section out.
        activity = _activity(
            truncated={"daily_commits": {"shown": 8, "total": 31}}
        )
        text = renderer.render(activity, _findings())
        assert "daily commits shows 8 of 31." in text
        assert "None recorded for this window." not in text


class TestFindingsOnTheCommand:
    """Findings passed inline cannot be rendered before they exist.

    A separate write-then-render pair has a window between the two, and a run
    that entered it called the renderer against a file it had not written yet.
    The error names a missing file, which reads like a path problem, and the
    fix attempted is another path -- a loop that ends the run.
    """

    def _stdin(self, monkeypatch: Any, tmp_path: Any, text: str) -> None:
        # A heredoc is a real file on a real descriptor, so the test uses one:
        # the detection deliberately turns on the kind of descriptor stdin is.
        source = tmp_path / "stdin"
        source.write_text(text, encoding="utf-8")
        monkeypatch.setattr(sys, "stdin", source.open("r", encoding="utf-8"))

    def test_findings_are_read_from_the_command(
        self, renderer: ModuleType, tmp_path: Any, monkeypatch: Any
    ) -> None:
        activity_file = tmp_path / "raw.json"
        activity_file.write_text(json.dumps(_activity()), encoding="utf-8")
        self._stdin(monkeypatch, tmp_path, json.dumps(_findings()))

        assert (
            renderer.main(
                ["--activity", str(activity_file), "--findings", "-"]
            )
            == 0
        )

    def test_a_heredoc_needs_no_flag(
        self, renderer: ModuleType, tmp_path: Any, monkeypatch: Any
    ) -> None:
        run_dir = tmp_path / "state.run"
        run_dir.mkdir()
        activity_file = tmp_path / "raw.json"
        activity_file.write_text(json.dumps(_activity()), encoding="utf-8")
        (run_dir / "run.json").write_text(
            json.dumps({"raw_output": str(activity_file)}), encoding="utf-8"
        )
        self._stdin(monkeypatch, tmp_path, json.dumps(_findings()))

        # No findings.json was ever written, and the render still succeeds.
        assert renderer.main(["--run-dir", str(run_dir)]) == 0
        assert not (run_dir / "findings.json").exists()

    def test_inline_findings_beat_a_stale_file(
        self, renderer: ModuleType, tmp_path: Any, monkeypatch: Any, capsys: Any
    ) -> None:
        run_dir = tmp_path / "state.run"
        run_dir.mkdir()
        activity_file = tmp_path / "raw.json"
        activity_file.write_text(json.dumps(_activity()), encoding="utf-8")
        (run_dir / "run.json").write_text(
            json.dumps({"raw_output": str(activity_file)}), encoding="utf-8"
        )
        (run_dir / "findings.json").write_text(
            json.dumps(_findings(tldr=[{"text": "From the file"}])), encoding="utf-8"
        )
        self._stdin(
            monkeypatch,
            tmp_path,
            json.dumps(_findings(tldr=[{"text": "From the command"}])),
        )

        assert renderer.main(["--run-dir", str(run_dir)]) == 0
        text = capsys.readouterr().out
        assert "From the command" in text
        assert "From the file" not in text

    def test_an_empty_heredoc_says_what_was_expected(
        self, renderer: ModuleType, tmp_path: Any, monkeypatch: Any, capsys: Any
    ) -> None:
        activity_file = tmp_path / "raw.json"
        activity_file.write_text(json.dumps(_activity()), encoding="utf-8")
        self._stdin(monkeypatch, tmp_path, "   \n")

        assert (
            renderer.main(["--activity", str(activity_file), "--findings", "-"]) == 2
        )
        assert "carried nothing" in capsys.readouterr().err

    def test_a_missing_findings_file_names_the_inline_form(
        self, renderer: ModuleType, tmp_path: Any, capsys: Any
    ) -> None:
        # This is the message a run reads after calling the renderer too early.
        # "No such file or directory" sends it looking for a path problem it
        # does not have; naming the form that cannot be too early does not.
        run_dir = tmp_path / "state.run"
        run_dir.mkdir()
        activity_file = tmp_path / "raw.json"
        activity_file.write_text(json.dumps(_activity()), encoding="utf-8")
        (run_dir / "run.json").write_text(
            json.dumps({"raw_output": str(activity_file)}), encoding="utf-8"
        )

        assert renderer.main(["--run-dir", str(run_dir)]) == 2
        error = capsys.readouterr().err
        assert "no findings" in error
        assert "--findings - <<" in error

    def test_malformed_inline_findings_are_named_as_such(
        self, renderer: ModuleType, tmp_path: Any, monkeypatch: Any, capsys: Any
    ) -> None:
        activity_file = tmp_path / "raw.json"
        activity_file.write_text(json.dumps(_activity()), encoding="utf-8")
        self._stdin(monkeypatch, tmp_path, "{not json")

        assert (
            renderer.main(["--activity", str(activity_file), "--findings", "-"]) == 2
        )
        assert "given on stdin are not JSON" in capsys.readouterr().err


class TestTheRunRecord:
    def test_daily_drift_is_not_reported_as_a_missed_window(
        self, renderer: ModuleType
    ) -> None:
        # Consecutive runs never start at the same second, so the fetcher's
        # catch-up flag is set every day. Reported as-is it would appear in every
        # report and teach its reader to skip the line that matters.
        text = renderer.render(_activity(), _findings())
        assert "Window widened" not in text

    def test_a_real_catch_up_is_reported(self, renderer: ModuleType) -> None:
        activity = _activity()
        activity["windows"]["daily"]["start_utc"] = "2026-08-12T06:00:06Z"
        text = renderer.render(activity, _findings())
        assert "Window widened by 24.0h" in text

    def test_an_unwritten_watermark_is_reported(self, renderer: ModuleType) -> None:
        activity = _activity(
            state={"written": False, "reason": "no --state-file given"}
        )
        text = renderer.render(activity, _findings())
        assert "Run not recorded: no --state-file given." in text

    def test_activity_that_is_not_a_run_is_refused(self, renderer: ModuleType) -> None:
        with pytest.raises(renderer.RenderError, match="not a fetcher run"):
            renderer.render({"repository": "example/repo"}, _findings())


class TestTheSkillCarriesNoDeploymentContext:
    """Nothing the Skill ships may assume this deployment or this project's history.

    A guard rather than a review note: every one of these has been shipped by
    hand at least once, and each is invisible until a reader on another
    deployment hits it.
    """

    FILES = sorted(
        path
        for path in _SKILL.rglob("*")
        if path.is_file() and path.suffix in {".py", ".md", ".yaml"}
    )

    @pytest.mark.parametrize("banned", ["/home/", "~/.jiuwenswarm/agent", "C0B", "T0BKJQBQ"])
    def test_no_host_path_or_channel_id(self, banned: str) -> None:
        offenders = [
            path.name
            for path in self.FILES
            if banned in path.read_text(encoding="utf-8")
        ]
        assert offenders == [], f"{banned!r} appears in {offenders}"

    @pytest.mark.parametrize(
        "banned", ["openJiuwen-ai/jiuwenswarm", "jiuwenswarm-daily-intel"]
    )
    def test_no_deployment_repository_or_channel_name(self, banned: str) -> None:
        offenders = [
            path.name
            for path in self.FILES
            if banned in path.read_text(encoding="utf-8")
        ]
        assert offenders == [], f"{banned!r} appears in {offenders}"

    def test_scripts_name_no_design_document_or_roadmap(self) -> None:
        # A skill's own scripts are read by operators of other deployments. A
        # roadmap word or a design-doc reference is meaningless to them and
        # cannot be resolved from anything they have.
        banned = ("v1 ", "v2 ", "deferred", "roadmap", "design doc", "see the design")
        offenders: list[str] = []
        for path in self.FILES:
            if path.suffix != ".py":
                continue
            lowered = path.read_text(encoding="utf-8").lower()
            offenders += [f"{path.name}: {word}" for word in banned if word in lowered]
        assert offenders == []


class TestAContentShortfallIsPublishedRatherThanRefused:
    """A weak item costs its own line, never the whole report.

    Observed in production: a significant change arrived without an evidence
    link, the render refused with a clear and specific message, and the run
    reissued the identical command twenty-nine times before the host ended it —
    delivering nothing, over one unlinked sentence. Refusing also happens to be
    the documented precondition for the other failure, where a run decides the
    renderer cannot be satisfied and composes its own report instead. The rule
    stays and stops being fatal: the shortfall is published where the reader
    meets the claim, and listed in a section the findings cannot write to.
    """

    def _render(self, renderer: ModuleType, **findings: Any) -> tuple[str, list[str]]:
        collected = renderer._Shortfalls()
        text = renderer.render(_activity(), _findings(**findings), shortfalls=collected)
        return text, collected.items

    def test_a_missing_evidence_link_is_published_and_marked(
        self, renderer: ModuleType
    ) -> None:
        text, noted = self._render(
            renderer,
            significant_changes=[{"title": "A change", "text": "It landed"}],
        )
        # The claim itself still reaches the reader, and so does the fact that
        # nothing backs it.
        assert "1. *A change*" in text
        assert "⚠️ No evidence link — this conclusion is unverified." in text
        assert noted == [
            "significant change 1: no evidence link; every important conclusion "
            "carries one, and this one is published without it"
        ]
        assert "*Reporting Shortfalls*" in text
        assert "significant change 1: no evidence link" in text

    def test_a_trend_signal_without_evidence_is_published_and_marked(
        self, renderer: ModuleType
    ) -> None:
        text, noted = self._render(
            renderer,
            trends=[
                {
                    "theme": "Tools",
                    "direction": "rising",
                    "text": "More tool work",
                    "confidence": "high",
                }
            ],
        )
        assert "*Tools* — ↑ Rising" in text
        assert "⚠️ No evidence link" in text
        assert any("trend 'Tools'" in item for item in noted)

    def test_an_evidence_entry_without_a_url_is_dropped_and_named(
        self, renderer: ModuleType
    ) -> None:
        text, noted = self._render(
            renderer,
            significant_changes=[
                {
                    "title": "A change",
                    "text": "It landed",
                    "evidence": [
                        {"label": "PR #1"},
                        {"label": "PR #2", "url": "https://example.com/pull/2"},
                    ],
                }
            ],
        )
        # The one reference that can be followed survives; the other is named.
        assert "<https://example.com/pull/2|PR #2>" in text
        assert "PR #1" not in text
        assert noted == [
            "significant change 1: an evidence reference carries no url and was "
            "dropped"
        ]

    def test_an_unknown_severity_renders_unrated_rather_than_defaulted(
        self, renderer: ModuleType
    ) -> None:
        # Falling back to the default would print a green mark beside an item its
        # writer called urgent — a wrong answer that looks like a measured one.
        text, noted = self._render(renderer, tldr=[{"severity": "urgent", "text": "x"}])
        assert "• ⚠️ x" in text
        assert "🟢 x" not in text
        assert noted == [
            "TL;DR bullet 1: severity is not one of critical, major, stable; the "
            "item is published unrated"
        ]

    def test_an_unknown_risk_severity_keeps_the_risk(
        self, renderer: ModuleType
    ) -> None:
        text, noted = self._render(
            renderer, risks=[{"severity": "blocker", "text": "CI is red on main"}]
        )
        assert "• ⚠️ *Unrated* — CI is red on main" in text
        assert any("risk 1: severity" in item for item in noted)

    def test_an_unknown_label_renders_as_unlabelled(self, renderer: ModuleType) -> None:
        text, noted = self._render(
            renderer,
            significant_changes=[
                {
                    "title": "A change",
                    "label": "observation",
                    "text": "It landed",
                    "evidence": [{"label": "#1", "url": "https://example.com/pull/1"}],
                }
            ],
        )
        assert "[⚠️ UNLABELLED] It landed" in text
        assert any("significant change 1: label" in item for item in noted)

    def test_an_untitled_change_renders_a_placeholder_not_a_blank_line(
        self, renderer: ModuleType
    ) -> None:
        # An empty heading reads as a rendering fault and tells the reader
        # nothing; the body and evidence below it are the substance and survive.
        text, noted = self._render(
            renderer,
            significant_changes=[
                {
                    "text": "It landed",
                    "evidence": [{"label": "#1", "url": "https://example.com/pull/1"}],
                }
            ],
        )
        assert "1. ⚠️ *(untitled)*" in text
        assert "1. **" not in text
        assert "[FACT] It landed" in text
        assert noted == ["significant change 1: no title; the item is published untitled"]

    def test_a_trend_signal_missing_its_parts_is_published(
        self, renderer: ModuleType
    ) -> None:
        text, noted = self._render(
            renderer,
            trends=[
                {
                    "text": "Something moved",
                    "direction": "surging",
                    "confidence": "certain",
                    "evidence": [{"label": "#2", "url": "https://example.com/issues/2"}],
                }
            ],
        )
        assert "⚠️ *(theme not stated)*" in text
        assert "⚠️ Direction not stated" in text
        assert "Confidence: ⚠️ not stated" in text
        assert len(noted) == 3
        assert all(item.startswith("trend signal 1:") for item in noted)

    def test_an_inference_without_a_confidence_is_published(
        self, renderer: ModuleType
    ) -> None:
        text, noted = self._render(
            renderer,
            missing_capabilities={"inferred": [{"text": "No Windows runner"}]},
        )
        assert "*Inferred (⚠️ confidence not stated)* — No Windows runner" in text
        assert noted == [
            "inferred missing capability 1: confidence is not High, Medium or "
            "Low; the inference is published without one"
        ]

    def test_an_opportunity_names_only_the_field_it_is_missing(
        self, renderer: ModuleType
    ) -> None:
        # A note naming both when only one is absent sends its reader looking for
        # a second problem that is not there.
        text, noted = self._render(
            renderer, opportunities=[{"title": "A thing"}]
        )
        assert "1. *A thing* — ⚠️ kind not stated" in text
        assert noted == ["opportunity 1: no kind; the item is published unclassified"]

    def test_an_over_budget_brief_is_delivered_rather_than_refused(
        self, renderer: ModuleType
    ) -> None:
        # Every section is still there; the only consequence is that the host
        # chooses the split point. Refusing traded that for no report at all.
        text, noted = self._render(
            renderer, tldr=[{"text": "x " * renderer._BRIEF_BUDGET}]
        )
        assert _headings(text) == _SECTIONS
        assert any(item.startswith("the channel brief:") for item in noted)
        assert "over the 2800 budget" in text


class TestTheWarningCannotBeSilenced:
    """A check a run can turn off is the same as no check."""

    def test_the_findings_have_no_key_that_writes_the_section(
        self, renderer: ModuleType
    ) -> None:
        # There is no field for it, and a key invented for one is caught as
        # content the renderer does not read rather than quietly ignored.
        assert "reporting_shortfalls" not in renderer._FINDINGS_KEYS
        with pytest.raises(renderer.RenderError) as caught:
            renderer.render(
                _activity(),
                _findings(reporting_shortfalls=[{"text": "nothing to report"}]),
            )
        assert "reporting_shortfalls" in str(caught.value)

    def test_a_writers_evidence_gaps_do_not_absorb_a_shortfall(
        self, renderer: ModuleType
    ) -> None:
        # The two sections answer different questions: a gap says what the run
        # could not establish about the repository, a shortfall says what this
        # report failed to state properly. Filed together, an unlinked
        # conclusion would read as an evidence limitation, which is the one
        # excuse it must not have.
        text = renderer.render(
            _activity(),
            _findings(
                significant_changes=[{"title": "A change", "text": "It landed"}],
                evidence_gaps={"known": [{"text": "Adoption is unmeasured"}]},
            ),
        )
        gaps = text.index("*Evidence Gaps*")
        shortfalls = text.index("*Reporting Shortfalls*")
        assert gaps < shortfalls
        assert "no evidence link" not in text[gaps:shortfalls]

    def test_a_shortfall_does_not_fail_the_command(
        self, renderer: ModuleType, tmp_path: Any, capsys: Any
    ) -> None:
        # The exit status is what decides whether the run treats the render as
        # something to repeat. A finished report exits 0.
        activity_file = tmp_path / "raw.json"
        activity_file.write_text(json.dumps(_activity()), encoding="utf-8")
        findings_file = tmp_path / "f.json"
        findings_file.write_text(
            json.dumps(
                _findings(
                    significant_changes=[{"title": "A change", "text": "It landed"}]
                )
            ),
            encoding="utf-8",
        )
        code = renderer.main(
            ["--activity", str(activity_file), "--findings", str(findings_file)]
        )
        assert code == 0
        captured = capsys.readouterr()
        assert "⚠️ No evidence link" in captured.out
        assert "reporting shortfall: significant change 1" in captured.err
        assert "1 reporting shortfall(s)" in captured.err


class TestWhatStillRefuses:
    """Structural problems keep refusing: there is nothing worth rendering.

    The difference from a shortfall is whether a reader would be served by the
    result. A report missing one evidence link is worth delivering; a report with
    no judgement in it, or one whose findings were never read, is not — it is a
    finished-looking document that is empty or wrong, which is worse than an
    error the run can act on.
    """

    def test_no_tldr_bullets_at_all_is_refused(self, renderer: ModuleType) -> None:
        with pytest.raises(renderer.RenderError, match="tldr"):
            renderer.render(_activity(), _findings(tldr=[]))

    def test_no_significant_changes_at_all_is_refused(
        self, renderer: ModuleType
    ) -> None:
        with pytest.raises(renderer.RenderError, match="significant_changes"):
            renderer.render(_activity(), _findings(significant_changes=[]))

    def test_a_path_is_still_refused_rather_than_marked(
        self, renderer: ModuleType
    ) -> None:
        # Publishing it with a warning would still publish it, and the disclosure
        # is what the check is for. The check also runs on the assembled text, so
        # there is no single item to attribute the shortfall to.
        findings = _findings(
            significant_changes=[
                {
                    "title": "A change",
                    "text": "Written to /home/someone/workspace/report.md",
                    "evidence": [{"label": "#1", "url": "https://example.com/pull/1"}],
                }
            ]
        )
        with pytest.raises(renderer.RenderError, match="filesystem path"):
            renderer.render(_activity(), findings)

    def test_activity_that_is_not_a_run_is_still_refused(
        self, renderer: ModuleType
    ) -> None:
        # Every number in the report is read from that file. Without it there is
        # no measured half, and the half that is left is the one that cannot be
        # checked.
        with pytest.raises(renderer.RenderError, match="not a fetcher run"):
            renderer.render({"windows": {}}, _findings())


class TestAnItemWithNothingToSay:
    """Every line is a mark, a heading or a bracket followed by the writer's
    sentence, so an entry with no sentence renders as punctuation and nothing
    else — which reads as a rendering fault rather than as a missing finding."""

    @pytest.mark.parametrize(
        "key, where",
        [
            ("tldr", "TL;DR bullet 1"),
            ("risks", "risk 1"),
            ("actions", "action 1"),
        ],
    )
    def test_an_entry_with_no_text_says_so(
        self, renderer: ModuleType, key: str, where: str
    ) -> None:
        collected = renderer._Shortfalls()
        text = renderer.render(
            _activity(), _findings(**{key: [{}]}), shortfalls=collected
        )
        assert "⚠️ (nothing stated)" in text
        assert f"{where}: no text; the item is published with nothing to say" in (
            collected.items
        )

    def test_a_change_with_no_text_keeps_its_title_and_evidence(
        self, renderer: ModuleType
    ) -> None:
        text = renderer.render(
            _activity(),
            _findings(
                significant_changes=[
                    {
                        "title": "A change",
                        "evidence": [
                            {"label": "#1", "url": "https://example.com/pull/1"}
                        ],
                    }
                ]
            ),
        )
        assert "1. *A change*" in text
        assert "[FACT] ⚠️ (nothing stated)" in text
        assert "<https://example.com/pull/1|#1>" in text


class TestContentUnderAKeyNobodyReadsIsNamed:
    """Content that arrives under an unread name is reported, never re-read.

    Observed live: a significant change carried its evidence as `link`, where the
    schema calls the field `evidence`. Nothing read it, so the item rendered
    "No evidence link — this conclusion is unverified" — a statement that is
    false in the direction that hurts. The evidence existed and had been
    gathered; the reader was told a verified conclusion was unbacked, and the
    writer was told to add a link it had already added. The one mark that exists
    to catch the mistake pointed away from its cause, which is why this is worse
    than a link that is genuinely absent.

    The top-level shape check refuses a findings file that hides content under an
    unrecognised top-level key, for exactly this reason, and never looked inside
    an item. These pin the same guarantee one level down, and the rule that goes
    with it: the misplaced value is named and left where it is. Reading it would
    make `link` a second name for `evidence`, and two names for one field is how
    this survived — once the link prints, the report looks finished and only the
    writer's own diligence ever moves it.
    """

    def _render(self, renderer: ModuleType, **findings: Any) -> tuple[str, list[str]]:
        collected = renderer._Shortfalls()
        text = renderer.render(_activity(), _findings(**findings), shortfalls=collected)
        return text, collected.items

    def test_a_url_under_an_unread_key_is_not_reported_as_no_evidence(
        self, renderer: ModuleType
    ) -> None:
        text, noted = self._render(
            renderer,
            significant_changes=[
                {
                    "title": "A change",
                    "text": "It landed",
                    "link": "https://example.com/pull/1",
                }
            ],
        )
        assert "⚠️ No evidence link — this conclusion is unverified." not in text, (
            "the conclusion is not unverified; its evidence arrived under a name "
            "nothing reads, and saying otherwise sends both readers away from the "
            "cause"
        )
        assert (
            "⚠️ Evidence not published — a url arrived under `link`, not "
            "`evidence`." in text
        )
        assert any("a url arrived under `link`" in item for item in noted)

    def test_the_misplaced_url_is_named_but_never_rendered(
        self, renderer: ModuleType
    ) -> None:
        # Salvage was considered and refused. A url under an unread key need not
        # be evidence for the sentence beside it, so publishing one under
        # "Evidence:" would assert a backing nobody claimed — one false statement
        # traded for another — and accepting the name at all entrenches it.
        text, _noted = self._render(
            renderer,
            significant_changes=[
                {
                    "title": "A change",
                    "text": "It landed",
                    "link": "https://example.com/pull/1",
                }
            ],
        )
        assert "<https://example.com/pull/1" not in text
        assert "Evidence: " not in text.split("*Risks and Blockers*")[0]

    def test_a_reference_carrying_its_url_under_another_key_says_so(
        self, renderer: ModuleType
    ) -> None:
        text, noted = self._render(
            renderer,
            significant_changes=[
                {
                    "title": "A change",
                    "text": "It landed",
                    "evidence": [{"label": "PR #1", "link": "https://example.com/1"}],
                }
            ],
        )
        assert "⚠️ No evidence link" not in text
        assert (
            "⚠️ Evidence not published — a reference carried its url under "
            "`link`, not `url`." in text
        )
        assert any("rather than `url`" in item for item in noted)

    def test_a_genuinely_absent_link_keeps_its_own_diagnosis(
        self, renderer: ModuleType
    ) -> None:
        # The converse, so the correction above cannot swallow the case it was
        # carved out of: nothing on this item holds a url, and the mark that says
        # the conclusion is unverified is then simply true.
        text, noted = self._render(
            renderer,
            significant_changes=[
                {"title": "A change", "text": "It landed", "issue": "#1"}
            ],
        )
        assert "⚠️ No evidence link — this conclusion is unverified." in text
        assert any("no evidence link" in item for item in noted)

    @pytest.mark.parametrize(
        "findings, where, key",
        [
            ({"tldr": [{"text": "x", "note": "kept"}]}, "TL;DR bullet 1", "note"),
            (
                {"risks": [{"severity": "major", "text": "x", "owner": "someone"}]},
                "risk 1",
                "owner",
            ),
            ({"actions": [{"do": "the thing"}]}, "action 1", "do"),
            (
                {
                    "trends": [
                        {
                            "theme": "Tools",
                            "direction": "rising",
                            "text": "x",
                            "confidence": "high",
                            "evidence": [
                                {"label": "#2", "url": "https://example.com/2"}
                            ],
                            "delta": "+12",
                        }
                    ]
                },
                "trend 'Tools'",
                "delta",
            ),
            (
                {"opportunities": [{"title": "A thing", "kind": "K", "text": "x"}]},
                "opportunity 1",
                "text",
            ),
            (
                {"missing_capabilities": {"explicit": [{"text": "x", "why": "y"}]}},
                "explicit missing capability 1",
                "why",
            ),
            (
                {"evidence_gaps": {"known": [{"text": "x", "source": "y"}]}},
                "known evidence gap 1",
                "source",
            ),
        ],
    )
    def test_every_item_reports_a_populated_key_it_does_not_read(
        self, renderer: ModuleType, findings: dict[str, Any], where: str, key: str
    ) -> None:
        # The structural half, and the half that catches the next one: no field
        # name is special-cased, so whatever a writer invents next is reported in
        # the run that invents it rather than dropped in silence.
        _text, noted = self._render(renderer, **findings)
        assert any(
            item.startswith(f"{where}: carries content under") and f"`{key}`" in item
            for item in noted
        ), noted

    def test_a_scalar_on_an_item_is_content_unlike_one_at_the_top_level(
        self, renderer: ModuleType
    ) -> None:
        # The top-level check ignores a stray scalar, because up there the
        # content lives in eight lists and objects and a scalar beside them is a
        # note the writer kept for itself. On an item the scalar *is* the content
        # — a title, a sentence, a url — so the distinction does not carry down
        # and a bare string under an unread name is reported.
        _text, noted = self._render(
            renderer,
            significant_changes=[
                {
                    "title": "A change",
                    "summary": "It landed",
                    "evidence": [{"label": "#1", "url": "https://example.com/1"}],
                }
            ],
        )
        assert any("`summary`" in item for item in noted)

    def test_a_group_name_nobody_reads_is_not_published_as_none_found(
        self, renderer: ModuleType
    ) -> None:
        # Worse than a dropped item: the section renders "None identified in this
        # window.", which is not silence but a false statement about the run.
        text, noted = self._render(
            renderer, missing_capabilities={"assumed": [{"text": "No Windows runner"}]}
        )
        assert "• None identified in this window." in text
        assert any(
            item.startswith("missing capabilities: carries content under")
            and "`assumed`" in item
            for item in noted
        ), noted

    def test_an_unreadable_key_name_is_counted_rather_than_published(
        self, renderer: ModuleType
    ) -> None:
        # A key name is caller text and the shortfall section publishes none. A
        # name that could be a path would otherwise make a content-quality
        # problem refuse the whole report on the path check.
        text, noted = self._render(
            renderer,
            significant_changes=[
                {
                    "title": "A change",
                    "text": "It landed",
                    "/etc/passwd /home/someone": "x",
                    "evidence": [{"label": "#1", "url": "https://example.com/1"}],
                }
            ],
        )
        assert "/etc/passwd" not in text
        assert any(
            "1 further key(s) whose names cannot be printed" in item for item in noted
        ), noted

    def test_a_dropped_key_never_makes_the_report_refuse(
        self, renderer: ModuleType
    ) -> None:
        # A mislabelled field is content quality: the report is deliverable, and
        # the classification the rest of this file keeps must not be reopened
        # here.
        collected = renderer._Shortfalls()
        text = renderer.render(
            _activity(),
            _findings(
                significant_changes=[
                    {"title": "A change", "link": "https://example.com/1"}
                ],
                risks=["a bare string"],
                missing_capabilities=[{"text": "not an object of groups"}],
            ),
            shortfalls=collected,
        )
        assert "*Reporting Shortfalls*" in text
        assert len(collected) >= 3

    def test_more_than_one_misplaced_url_reads_as_more_than_one(
        self, renderer: ModuleType
    ) -> None:
        # Seen live: an item carried both `highlights` and a bare `url`. The
        # line is delivered to a reader, so it agrees in number.
        text, _noted = self._render(
            renderer,
            significant_changes=[
                {
                    "title": "A change",
                    "text": "It landed",
                    "url": "https://example.com/pull/1",
                    "highlights": ["see https://example.com/pull/2"],
                }
            ],
        )
        assert (
            "⚠️ Evidence not published — urls arrived under `highlights`, `url`, "
            "not `evidence`." in text
        )

    def test_a_bare_url_in_place_of_a_reference_is_named_as_one(
        self, renderer: ModuleType
    ) -> None:
        text, noted = self._render(
            renderer,
            significant_changes=[
                {
                    "title": "A change",
                    "text": "It landed",
                    "evidence": ["https://example.com/pull/1"],
                }
            ],
        )
        assert "⚠️ No evidence link" not in text
        assert (
            "⚠️ Evidence not published — a reference carried a url in a form "
            "this report does not read." in text
        )
        assert noted == [
            "significant change 1: an evidence reference is a bare value rather "
            "than an object with `label` and `url`, and was dropped"
        ], noted


def _a_change() -> dict[str, Any]:
    """One complete significant change, for tests whose subject is another section.

    The window these tests render is not quiet, so an empty ``significant_changes``
    refuses before anything else is reached.
    """
    return {
        "title": "A real change",
        "text": "It really landed",
        "evidence": [{"label": "PR #1", "url": "https://example.com/pull/1"}],
    }


def _a_trend(*, direction: str = "rising", confidence: str = "high") -> dict[str, Any]:
    """One complete trend signal, with the two closed fields open to the caller."""
    return {
        "theme": "A theme",
        "direction": direction,
        "text": "It moved",
        "confidence": confidence,
        "evidence": [{"label": "PR #1", "url": "https://example.com/pull/1"}],
    }


def _template() -> dict[str, Any]:
    """Return the findings template the fetch prints, from the fetch itself.

    Loaded rather than copied: the examples are the thing under test, and a copy
    here would go on passing after the template stopped matching it.
    """
    script = _SKILL / "scripts" / "fetch_repository_activity.py"
    spec = importlib.util.spec_from_file_location("fetch_for_template", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module._findings_template()


class TestAnExampleNeverBecomesAFinding:
    """The template's examples are droppable, and dropping them is all that happens.

    Shipping worked examples is what makes an item's field names visible to a
    writer who never opens the schema reference. It is also this skill's worst
    documented failure re-enacted -- figures copied out of a template and
    published as measured -- unless nothing copied out of it can be published.
    The item-level unread-key check does not help: an example sits under a key
    the renderer does read, so it passes every other check.
    """

    def _render(
        self, renderer: ModuleType, **findings: Any
    ) -> tuple[str, list[str]]:
        shortfalls = renderer._Shortfalls()
        text = renderer.render(_activity(), findings, shortfalls=shortfalls)
        return text, shortfalls.items

    def test_the_template_copied_unfilled_renders_nothing(
        self, renderer: ModuleType
    ) -> None:
        # Every entry is dropped, which empties tldr, which is the refusal that
        # already existed and already says the right thing. No rule of its own.
        with pytest.raises(renderer.RenderError, match="tldr"):
            renderer.render(_activity(), _template())

    def test_a_leftover_example_is_dropped_and_the_real_items_survive(
        self, renderer: ModuleType
    ) -> None:
        # Refusing here would lose three real findings over one stray entry --
        # the trade this renderer already made once and reversed.
        text, noted = self._render(
            renderer,
            tldr=[{"text": "Something moved"}],
            significant_changes=[
                {
                    "title": "A real change",
                    "text": "It really landed",
                    "evidence": [{"label": "PR #1", "url": "https://example.com/pull/1"}],
                },
                _template()["significant_changes"][0],
            ],
        )
        assert "A real change" in text
        assert renderer._PLACEHOLDER not in text
        assert (
            "significant_changes: 1 entry was still the template's example text "
            "and was not published." in " ".join(noted)
        )

    def test_the_drop_is_published_rather_than_only_logged(
        self, renderer: ModuleType
    ) -> None:
        text, _noted = self._render(
            renderer,
            tldr=[{"text": "Something moved"}, _template()["tldr"][0]],
            significant_changes=[
                {
                    "title": "A real change",
                    "text": "It really landed",
                    "evidence": [{"label": "PR #1", "url": "https://example.com/pull/1"}],
                }
            ],
        )
        assert "*Reporting Shortfalls*" in text
        assert "tldr: 1 entry was still the template's example text" in text

    def test_an_example_evidence_reference_does_not_cost_the_item(
        self, renderer: ModuleType
    ) -> None:
        # The sentence is the writer's whatever they left attached to it, so the
        # reference is dropped one level down and the item keeps the existing
        # missing-evidence mark.
        text, noted = self._render(
            renderer,
            tldr=[{"text": "Something moved"}],
            significant_changes=[
                {
                    "title": "A real change",
                    "text": "It really landed",
                    "evidence": _template()["significant_changes"][0]["evidence"],
                }
            ],
        )
        assert "A real change" in text
        assert "⚠️ No evidence link" in text
        assert (
            "significant_changes: 1 evidence reference was still the template's "
            "example link and was dropped" in " ".join(noted)
        )

    def test_a_marked_value_never_reaches_the_rendered_text(
        self, renderer: ModuleType
    ) -> None:
        # The backstop, for a marker that arrives somewhere the schema does not
        # define and the per-entry drop therefore never sees. A refusal here is
        # consistent with the drop, not in tension with it: there is no entry to
        # drop and so no honest report to publish around it.
        findings = _findings(tldr={"text": f"{renderer._PLACEHOLDER} — a thing"})
        with pytest.raises(renderer.RenderError, match=renderer._PLACEHOLDER):
            renderer.render(_activity(), findings)

    def test_a_kept_vocabulary_word_rates_the_item_rather_than_dropping_it(
        self, renderer: ModuleType
    ) -> None:
        # The other half of the marker decision, and the half that is easy to get
        # backwards. A closed field's example is a real word carrying no marker,
        # so a writer who states their own claim and leaves the shipped rating
        # alone gets the rating, not a vanished finding. Marking those values
        # instead would discard the whole entry -- the marker is read across an
        # entry, not a value -- which is a heavier loss than the unrated item the
        # lists exist to prevent.
        example = _template()["risks"][0]
        text, noted = self._render(
            renderer,
            tldr=[{"text": "Something moved"}],
            significant_changes=[_a_change()],
            risks=[{"severity": example["severity"], "text": "A real risk"}],
        )
        assert "A real risk" in text
        assert f"*{example['severity'].title()}*" in text
        assert "severity is not one of" not in " ".join(noted)
        assert "risks: 1 entry was still the template's example text" not in " ".join(
            noted
        )

    def test_every_word_the_template_teaches_is_a_word_the_renderer_takes(
        self, renderer: ModuleType
    ) -> None:
        # The lists are shipped in the template because runs read the template
        # and not the schema reference, so a word in them that the renderer then
        # refuses would be worse than shipping no list at all. Every word is
        # rendered rather than compared to the constant it came from: the words
        # and the checks that read them are in one file but not one place, and it
        # is the check that decides what a report says.
        cases: tuple[tuple[Any, str, Any], ...] = (
            (
                renderer._SEVERITY_MARKS,
                "severity is not one of",
                lambda word: {"risks": [{"severity": word, "text": "A real risk"}]},
            ),
            (
                renderer._LABELS,
                "label is not one of",
                lambda word: {"significant_changes": [{**_a_change(), "label": word}]},
            ),
            (
                renderer._DIRECTION_MARKS,
                "direction is not one of",
                lambda word: {"trends": [_a_trend(direction=word)]},
            ),
            (
                renderer._CONFIDENCE,
                "confidence is not",
                lambda word: {"trends": [_a_trend(confidence=word)]},
            ),
        )
        for words, complaint, build in cases:
            for word in words:
                findings: dict[str, Any] = {
                    "tldr": [{"text": "Something moved"}],
                    "significant_changes": [_a_change()],
                }
                findings.update(build(word))
                _text, noted = self._render(renderer, **findings)
                assert complaint not in " ".join(noted), (complaint, word)


class TestAQuietWindowMayHaveNoSignificantChange:
    """Empty is accepted from the run's counts, never from the findings.

    Refusing an empty section on a genuinely quiet window left a writer two ways
    out -- invent a change, or fail the render -- and a failed render is the
    documented precondition for both the retry loop and for a report composed
    outside this script. Gating on the measurement separates "nothing happened",
    which is a report, from "nothing was written", which is an empty one.
    """

    def _quiet(self) -> dict[str, Any]:
        zeros = dict.fromkeys(
            (
                "issues_created",
                "issues_updated",
                "pull_requests_created",
                "pull_requests_updated",
                "merged_events",
                "closed_events",
                "commits",
                "releases",
            ),
            0,
        )
        return _activity(
            window_counts={"daily": zeros, "seven_day": zeros, "history": zeros}
        )

    def test_a_measured_quiet_window_renders_the_section_as_earned(
        self, renderer: ModuleType
    ) -> None:
        text = renderer.render(self._quiet(), _findings(significant_changes=[]))
        assert "*Significant Changes*" in text
        assert (
            "• None; this run measured no issue, pull request, commit or "
            "release activity in the window, so there was no change to weigh."
            in text
        )

    def test_the_reader_can_check_the_claim_in_the_same_message(
        self, renderer: ModuleType
    ) -> None:
        # The rule is "every row of the activity table reads zero for the
        # window", and the table is in the same message, so the emptiness is
        # verifiable rather than asserted.
        text = renderer.render(self._quiet(), _findings(significant_changes=[]))
        for measure, _key, _endpoint in renderer._MEASURES:
            assert f"| {measure} | 0 |" in text

    def test_a_busy_window_still_refuses_and_names_what_it_counted(
        self, renderer: ModuleType
    ) -> None:
        with pytest.raises(renderer.RenderError) as caught:
            renderer.render(_activity(), _findings(significant_changes=[]))
        message = str(caught.value)
        assert "not quiet" in message
        assert "issues opened 122" in message
        assert "commits 31" in message

    def test_one_measured_change_is_enough_to_make_a_window_busy(
        self, renderer: ModuleType
    ) -> None:
        # The boundary is zero rather than a threshold. A window with any
        # measured change offers a truthful item to write; only a window with
        # none leaves invention as the way out.
        activity = self._quiet()
        activity["window_counts"]["daily"]["commits"] = 1
        with pytest.raises(renderer.RenderError, match="commits 1"):
            renderer.render(activity, _findings(significant_changes=[]))

    def test_counts_that_were_never_taken_are_not_a_quiet_window(
        self, renderer: ModuleType
    ) -> None:
        # ``_count`` reads an absent key as 0, so a fetch that wrote no counts
        # would otherwise look like the quietest window there has ever been.
        with pytest.raises(renderer.RenderError, match="no window counts"):
            renderer.render(
                _activity(window_counts={}), _findings(significant_changes=[])
            )

    def test_a_partial_count_map_is_not_a_quiet_window(
        self, renderer: ModuleType
    ) -> None:
        activity = self._quiet()
        del activity["window_counts"]["daily"]["commits"]
        with pytest.raises(renderer.RenderError, match="significant_changes"):
            renderer.render(activity, _findings(significant_changes=[]))

    def test_tldr_is_still_required_on_a_quiet_window(
        self, renderer: ModuleType
    ) -> None:
        # A quiet window can honestly have no significant change; it cannot
        # honestly have no judgement. "Nothing moved" is the judgement and is one
        # line, and without it the channel message carries no statement at all.
        with pytest.raises(renderer.RenderError, match="tldr"):
            renderer.render(
                self._quiet(), _findings(tldr=[], significant_changes=[])
            )
