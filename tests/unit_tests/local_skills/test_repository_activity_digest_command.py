"""Unit tests for the repository-activity-digest single entry point.

The state file is the one path a scheduled run is handed. Everything else it
used to type was copied by hand out of the previous command's output, and a
copied path can lose a character: the command then fails for a reason nothing in
it shows, gets reissued unchanged, and the reissue ends the run -- with a
directory near the caller's home created rather than refused on the way.
Deriving the run directory from the state file removes that surface, and these
tests hold the derivation and the aliases that keep older commands working.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_SCRIPTS = (
    Path(__file__).resolve().parents[3]
    / "local_skills"
    / "repository-activity-digest"
    / "scripts"
)


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def digest() -> ModuleType:
    return _load("digest_under_test", _SCRIPTS / "digest.py")


def _activity() -> dict[str, Any]:
    return {
        "repository": "example/repo",
        "generated_at_utc": "2026-08-14T06:00:20Z",
        "windows": {
            "daily": {
                "requested_hours": 24.0,
                "start_utc": "2026-08-13T06:00:06Z",
                "end_utc": "2026-08-14T06:00:20Z",
            },
            "history": {"days": 30.0},
        },
        "coverage": {"warnings": []},
        "window_counts": {"daily": {"commits": 3}},
        "state": {"written": True, "last_success_utc": "2026-08-14T06:00:20Z"},
    }


def _findings() -> dict[str, Any]:
    return {
        "tldr": [{"severity": "stable", "text": "A quiet window"}],
        "significant_changes": [
            {
                "title": "A change",
                "text": "It landed",
                "evidence": [{"label": "PR #1", "url": "https://example.com/pull/1"}],
            }
        ],
    }


def _run_directory(tmp_path: Path, *, with_findings: bool = True) -> Path:
    """Build what a fetch leaves behind, anchored to a state file."""
    state_file = tmp_path / "state" / "digest.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text("{}", encoding="utf-8")
    activity = tmp_path / "state" / "raw.json"
    activity.write_text(json.dumps(_activity()), encoding="utf-8")
    run_dir = state_file.parent / "digest.run"
    run_dir.mkdir()
    (run_dir / "run.json").write_text(
        json.dumps({"raw_output": str(activity)}), encoding="utf-8"
    )
    if with_findings:
        (run_dir / "findings.json").write_text(
            json.dumps(_findings()), encoding="utf-8"
        )
    return state_file


class TestTheStateFileIsTheOnlyPath:
    def test_render_derives_the_run_directory(
        self, digest: ModuleType, tmp_path: Path
    ) -> None:
        state_file = _run_directory(tmp_path)

        assert digest.main(["render", "--state-file", str(state_file)]) == 0
        report = state_file.parent / "digest.run" / "report.md"
        assert "*TL;DR*" in report.read_text(encoding="utf-8")

    def test_the_derivation_matches_the_one_the_fetch_used(
        self, digest: ModuleType, tmp_path: Path
    ) -> None:
        # Two derivations that agree by coincidence would come apart the first
        # time either moved, so render asks the fetcher for the answer.
        fetcher = _load(
            "fetch_for_derivation_check", _SCRIPTS / "fetch_repository_activity.py"
        )
        state_file = tmp_path / "state" / "digest.json"

        assert fetcher.run_dir_for(state_file) == state_file.parent / "digest.run"

    def test_render_before_a_fetch_says_which_step_is_missing(
        self, digest: ModuleType, tmp_path: Path, capsys: Any
    ) -> None:
        state_file = tmp_path / "state" / "digest.json"
        state_file.parent.mkdir(parents=True)

        assert digest.main(["render", "--state-file", str(state_file)]) == 2
        assert "no run directory" in capsys.readouterr().err

    def test_a_relative_state_file_resolves_as_the_fetch_resolves_it(
        self,
        digest: ModuleType,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: Any,
    ) -> None:
        # A relative state file is anchored to the data directory, not to the
        # working directory, and both halves of the run must anchor it alike.
        monkeypatch.setenv("JIUWENSWARM_DATA_DIR", str(tmp_path / "data"))
        anchor = (
            tmp_path / "data" / "agent" / "workspace" / "projects" / "memory"
        )
        anchor.mkdir(parents=True)
        activity = anchor / "raw.json"
        activity.write_text(json.dumps(_activity()), encoding="utf-8")
        run_dir = anchor / "state.run"
        run_dir.mkdir()
        (run_dir / "run.json").write_text(
            json.dumps({"raw_output": str(activity)}), encoding="utf-8"
        )
        (run_dir / "findings.json").write_text(
            json.dumps(_findings()), encoding="utf-8"
        )

        assert digest.main(["render", "--state-file", "memory/state.json"]) == 0
        assert "*TL;DR*" in capsys.readouterr().out


class TestNothingInFlightBreaks:
    """The older commands stay valid: a run mid-flight is not a run to break."""

    def test_run_dir_still_works_on_its_own(
        self, digest: ModuleType, tmp_path: Path
    ) -> None:
        state_file = _run_directory(tmp_path)
        run_dir = state_file.parent / "digest.run"

        assert digest.main(["render", "--run-dir", str(run_dir)]) == 0

    def test_an_explicit_run_dir_wins_over_the_derived_one(
        self, digest: ModuleType, tmp_path: Path
    ) -> None:
        state_file = _run_directory(tmp_path)
        elsewhere = tmp_path / "elsewhere.run"
        elsewhere.mkdir()
        activity = tmp_path / "other-raw.json"
        activity.write_text(json.dumps(_activity()), encoding="utf-8")
        (elsewhere / "run.json").write_text(
            json.dumps({"raw_output": str(activity)}), encoding="utf-8"
        )
        (elsewhere / "findings.json").write_text(
            json.dumps(_findings()), encoding="utf-8"
        )

        assert (
            digest.main(
                [
                    "render",
                    "--state-file",
                    str(state_file),
                    "--run-dir",
                    str(elsewhere),
                ]
            )
            == 0
        )
        assert (elsewhere / "report.md").is_file()
        assert not (state_file.parent / "digest.run" / "report.md").exists()

    def test_activity_and_findings_still_work(
        self, digest: ModuleType, tmp_path: Path
    ) -> None:
        activity = tmp_path / "raw.json"
        activity.write_text(json.dumps(_activity()), encoding="utf-8")
        findings = tmp_path / "f.json"
        findings.write_text(json.dumps(_findings()), encoding="utf-8")

        assert (
            digest.main(
                [
                    "render",
                    "--activity",
                    str(activity),
                    "--findings",
                    str(findings),
                ]
            )
            == 0
        )

    def test_findings_arrive_on_the_command(
        self, digest: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        state_file = _run_directory(tmp_path, with_findings=False)
        source = tmp_path / "stdin"
        source.write_text(json.dumps(_findings()), encoding="utf-8")
        monkeypatch.setattr(sys, "stdin", source.open("r", encoding="utf-8"))

        assert (
            digest.main(
                ["render", "--state-file", str(state_file), "--findings", "-"]
            )
            == 0
        )


class TestDispatch:
    def test_fetch_forwards_every_option_it_was_given(
        self, digest: ModuleType, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: list[list[str]] = []

        class _Fetcher:
            @staticmethod
            def main() -> int:
                seen.append(list(sys.argv))
                return 0

        monkeypatch.setattr(digest, "_sibling", lambda name: _Fetcher)

        assert digest.main(["fetch", "--repo", "example/repo", "--hours", "24"]) == 0
        assert seen[0][1:] == ["--repo", "example/repo", "--hours", "24"]

    def test_an_unknown_command_is_named(
        self, digest: ModuleType, capsys: Any
    ) -> None:
        assert digest.main(["report"]) == 2
        assert "unknown command" in capsys.readouterr().err

    def test_no_command_prints_the_usage(
        self, digest: ModuleType, capsys: Any
    ) -> None:
        assert digest.main([]) == 2
        assert "digest.py fetch" in capsys.readouterr().out

    @pytest.mark.parametrize("form", ["--state-file={path}", "--state-file"])
    def test_both_spellings_of_the_option_are_taken(
        self, digest: ModuleType, tmp_path: Path, form: str
    ) -> None:
        state_file = _run_directory(tmp_path)
        argv = ["render"]
        if "=" in form:
            argv.append(form.format(path=state_file))
        else:
            argv += [form, str(state_file)]

        assert digest.main(argv) == 0
