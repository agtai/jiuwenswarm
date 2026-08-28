"""Unit tests for the repository-activity-digest fetcher script."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_SCRIPT = (
    Path(__file__).resolve().parents[3]
    / "local_skills"
    / "repository-activity-digest"
    / "scripts"
    / "fetch_repository_activity.py"
)


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "fetch_repository_activity_under_test", _SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _renderer() -> ModuleType:
    """Load the renderer, so what it accepts is read from it rather than copied.

    The two scripts are edited apart and neither imports the other, so every
    constant the fetcher holds a second copy of -- the placeholder marker, the
    closed vocabularies -- is checked against this module rather than against a
    restatement in the test. A restatement would go on passing after the two
    files disagreed, which is the whole failure it is here to catch.
    """
    spec = importlib.util.spec_from_file_location(
        "render_report_under_fetcher_test", _SCRIPT.parent / "render_report.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _closed_fields(template: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Pair every closed field with the template item that states it.

    Which item carries which field is the one thing here that cannot be read off
    a constant, so it is written once and both vocabulary tests share it.
    """
    return [
        ("severity", template["tldr"][0]),
        ("severity", template["risks"][0]),
        ("label", template["significant_changes"][0]),
        ("direction", template["trends"][0]),
        ("confidence", template["trends"][0]),
        ("confidence", template["missing_capabilities"]["inferred"][0]),
    ]


@pytest.fixture(scope="module")
def fetcher() -> ModuleType:
    return _load_module()


def test_self_test_passes(fetcher: ModuleType) -> None:
    fetcher._self_test()


class TestPathResolution:
    """A relative path must name one file regardless of the working directory."""

    def test_relative_path_uses_data_dir_anchor(
        self, fetcher: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        data_dir = tmp_path / "data"
        monkeypatch.setenv("JIUWENSWARM_DATA_DIR", str(data_dir))
        expected = (
            data_dir / "agent" / "workspace" / "projects" / "memory" / "state.json"
        )

        resolved = fetcher._resolve_output_path(Path("memory/state.json"))

        assert resolved == expected.resolve()

    def test_resolution_is_independent_of_cwd(
        self, fetcher: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("JIUWENSWARM_DATA_DIR", str(tmp_path / "data"))
        first_cwd = tmp_path / "cwd-one"
        second_cwd = tmp_path / "cwd-two" / "nested"
        first_cwd.mkdir(parents=True)
        second_cwd.mkdir(parents=True)

        monkeypatch.chdir(first_cwd)
        first = fetcher._resolve_output_path(Path("memory/state.json"))
        monkeypatch.chdir(second_cwd)
        second = fetcher._resolve_output_path(Path("memory/state.json"))

        assert first == second

    def test_absolute_path_is_left_alone(
        self, fetcher: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("JIUWENSWARM_DATA_DIR", str(tmp_path / "data"))
        target = tmp_path / "elsewhere" / "state.json"

        assert fetcher._resolve_output_path(target) == target.resolve()

    def test_relative_data_dir_is_ignored(
        self, fetcher: ModuleType, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("JIUWENSWARM_DATA_DIR", "relative/not/absolute")

        assert fetcher._runtime_data_dir().is_absolute()

    def test_missing_path_stays_missing(self, fetcher: ModuleType) -> None:
        assert fetcher._resolve_output_path(None) is None


_NOW = "2026-08-10T06:00:00Z"
_EARLIER = "2026-08-10T01:00:00Z"
_OLD = "2026-07-20T01:00:00Z"


def _issue(number: int, *, is_pull: bool, updated_at: str) -> dict[str, Any]:
    record: dict[str, Any] = {
        "number": number,
        "title": f"Item {number}",
        "html_url": f"https://example.invalid/repo/issues/{number}",
        "state": "open",
        "user": {"login": f"author{number % 7}"},
        "author_association": "MEMBER",
        "labels": [{"name": "area/core"}, {"name": "kind/bug"}],
        "comments": number % 11,
        "created_at": _OLD,
        "updated_at": updated_at,
        "body": "b" * 4000,
    }
    if is_pull:
        record["pull_request"] = {"url": f"https://api.invalid/pulls/{number}"}
        record["draft"] = False
    return record


def _api_responses(*, daily_items: int) -> dict[str, Any]:
    issues = [
        _issue(number, is_pull=number % 2 == 0, updated_at=_EARLIER)
        for number in range(1, daily_items + 1)
    ]
    issues += [
        _issue(number, is_pull=False, updated_at=_OLD)
        for number in range(daily_items + 1, daily_items + 6)
    ]
    return {
        "issues": issues,
        "issue_events": [
            {
                "id": 1000 + index,
                "event": "closed" if index % 2 else "reopened",
                "created_at": _EARLIER,
                "actor": {"login": "maintainer"},
                "issue": {
                    "number": index,
                    "title": f"Item {index}",
                    "html_url": f"https://example.invalid/repo/issues/{index}",
                },
            }
            for index in range(1, 25)
        ],
        "events": [
            {
                "id": str(2000 + index),
                "type": "PullRequestReviewEvent",
                "created_at": _EARLIER,
                "actor": {"login": "reviewer"},
                "payload": {
                    "action": "created",
                    "review": {"state": "approved", "body": "r" * 3000},
                    "pull_request": {
                        "number": index,
                        "title": f"Item {index}",
                        "html_url": f"https://example.invalid/repo/pull/{index}",
                        "state": "open",
                    },
                },
            }
            for index in range(1, 12)
        ],
        "commits": [
            {
                "sha": f"{index:040x}",
                "html_url": f"https://example.invalid/repo/commit/{index:040x}",
                "author": {"login": f"author{index % 5}"},
                "committer": {"login": "committer"},
                "commit": {
                    "message": f"fix: change {index}\n\n" + "d" * 4000,
                    "author": {"name": "A", "date": _EARLIER},
                    "committer": {"name": "A", "date": _EARLIER},
                },
                "parents": [{"sha": "p1"}],
            }
            for index in range(1, 20)
        ],
        "releases": [
            {
                "id": 5,
                "tag_name": "v1.2.3",
                "name": "v1.2.3",
                "html_url": "https://example.invalid/repo/releases/v1.2.3",
                "author": {"login": "releaser"},
                "created_at": _EARLIER,
                "published_at": _EARLIER,
                "body": "n" * 4000,
            }
        ],
        "stale": [
            _issue(900 + index, is_pull=False, updated_at=_OLD) for index in range(30)
        ],
    }


def _make_request_stub(responses: dict[str, Any]):
    def _request(url: str, token: str) -> Any:
        if "page=2" in url:
            return []
        if "/issues/events" in url:
            return responses["issue_events"]
        if "/comments" in url or "/reviews" in url or "/files" in url:
            return []
        if "/check-runs" in url:
            return {"check_runs": []}
        if "/pulls/" in url:
            return {"merged": False, "head": {"sha": "abc"}, "base": {"ref": "main"}}
        if "/events" in url:
            return responses["events"]
        if "/commits" in url:
            return responses["commits"]
        if "/releases" in url:
            return responses["releases"]
        if "state=open" in url:
            return responses["stale"]
        if "/issues" in url:
            return responses["issues"]
        raise AssertionError(f"unexpected request: {url}")

    return _request


def _run(
    fetcher: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    *,
    data_dir: Path,
    extra_args: list[str] | None = None,
    daily_items: int = 60,
) -> tuple[dict[str, Any], str]:
    monkeypatch.setenv("JIUWENSWARM_DATA_DIR", str(data_dir))
    responses = _api_responses(daily_items=daily_items)
    monkeypatch.setattr(fetcher, "_request_json", _make_request_stub(responses))
    argv = [
        "fetch_repository_activity.py",
        "--repo",
        "example/repo",
        "--until",
        _NOW,
        "--state-file",
        "memory/state.json",
    ]
    argv.extend(extra_args or [])
    monkeypatch.setattr(sys, "argv", argv)

    assert fetcher.main() == 0

    stdout = capsys.readouterr().out
    return json.loads(stdout), stdout


class TestStdoutSummary:
    """stdout must fit a model context and name the files it wrote."""

    def test_stdout_is_far_smaller_than_the_raw_structure(
        self,
        fetcher: ModuleType,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        summary, stdout = _run(fetcher, monkeypatch, capsys, data_dir=tmp_path)
        raw_path = Path(summary["paths"]["raw_output"])

        assert raw_path.is_file()
        assert len(stdout.encode("utf-8")) < 40_000
        assert len(stdout.encode("utf-8")) * 4 < raw_path.stat().st_size

    def test_paths_are_absolute_and_reported(
        self,
        fetcher: ModuleType,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        summary, _ = _run(fetcher, monkeypatch, capsys, data_dir=tmp_path)
        paths = summary["paths"]

        assert Path(paths["raw_output"]).is_absolute()
        assert Path(paths["state_file"]).is_absolute()
        assert Path(paths["state_file"]) == (
            tmp_path / "agent" / "workspace" / "projects" / "memory" / "state.json"
        )
        assert Path(paths["state_file"]).is_file()
        assert paths["raw_output_bytes"] > 0

    def test_raw_output_keeps_every_record(
        self,
        fetcher: ModuleType,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        summary, _ = _run(fetcher, monkeypatch, capsys, data_dir=tmp_path)
        raw = json.loads(Path(summary["paths"]["raw_output"]).read_text("utf-8"))

        shown = summary["daily_activity"]
        assert len(shown["pull_requests"]) < len(raw["daily_activity"]["pull_requests"])
        assert shown["counts"]["pull_requests"] == len(
            raw["daily_activity"]["pull_requests"]
        )
        assert raw["trend"]["issues"]
        assert raw["paths"]["raw_output"] == summary["paths"]["raw_output"]

    def test_truncation_is_declared(
        self,
        fetcher: ModuleType,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        summary, _ = _run(fetcher, monkeypatch, capsys, data_dir=tmp_path)
        truncated = summary["truncated"]["daily_pull_requests"]

        assert truncated["shown"] < truncated["total"]
        assert truncated["shown"] == len(summary["daily_activity"]["pull_requests"])

    def test_sections_the_report_format_requires_are_present(
        self,
        fetcher: ModuleType,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        summary, _ = _run(fetcher, monkeypatch, capsys, data_dir=tmp_path)

        for section in (
            "windows",
            "coverage",
            "window_counts",
            "health_samples",
            "daily_activity",
            "highlights",
            "trend",
            "stale_open_sample",
        ):
            assert summary[section], f"missing evidence section: {section}"
        for window in ("daily", "seven_day", "history"):
            assert summary["window_counts"][window]["issues_updated"] >= 0
        assert summary["daily_activity"]["issues"][0]["url"]
        assert summary["trend"]["top_labels"]
        assert summary["highlights"][0]["number"]

    def test_state_watermark_is_reported(
        self,
        fetcher: ModuleType,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        summary, _ = _run(fetcher, monkeypatch, capsys, data_dir=tmp_path)

        assert summary["state"]["written"] is True
        assert summary["state"]["previous_last_success_utc"] == ""
        assert summary["state"]["last_success_utc"] == _NOW

    def test_explicit_raw_output_path_is_honoured(
        self,
        fetcher: ModuleType,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        target = tmp_path / "elsewhere" / "raw.json"
        summary, _ = _run(
            fetcher,
            monkeypatch,
            capsys,
            data_dir=tmp_path,
            extra_args=["--raw-output", str(target)],
        )

        assert summary["paths"]["raw_output"] == str(target.resolve())
        assert target.is_file()

    def test_summary_limit_bounds_the_lists(
        self,
        fetcher: ModuleType,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        summary, _ = _run(
            fetcher,
            monkeypatch,
            capsys,
            data_dir=tmp_path,
            extra_args=["--summary-limit", "3"],
        )

        assert len(summary["daily_activity"]["pull_requests"]) == 3
        assert len(summary["stale_open_sample"]) == 3


def _mapping_keys(node: Any, prefix: str = "") -> set[str]:
    """Every mapping key in a document, as a dotted path.

    Lists are not entered. Records inside them are deliberately trimmed on
    stdout and complete in the raw file, and that difference is the design; what
    must not differ is the shape a filter is written against.
    """
    keys: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            path = f"{prefix}{key}"
            keys.add(path)
            keys |= _mapping_keys(value, f"{path}.")
    return keys


def _covered(path: str, declared: Any) -> bool:
    return any(path == name or path.startswith(f"{name}.") for name in declared)


class TestStdoutAndTheRawFileAreOneSchema:
    """A name read on stdout must mean the same thing in the file it points at.

    This is the failure that has no error to read. A filter written against a
    name stdout showed and the raw file does not carry matches nothing, returns
    an empty result and exits 0 -- so there is nothing to correct, the command
    gets varied and reissued, and the run is killed for repeating itself. Every
    divergence below was shipped at least once.
    """

    def test_every_name_on_stdout_exists_in_the_raw_file(
        self,
        fetcher: ModuleType,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        summary, _ = _run(fetcher, monkeypatch, capsys, data_dir=tmp_path)
        raw = json.loads(Path(summary["paths"]["raw_output"]).read_text("utf-8"))

        divergent = {
            path
            for path in _mapping_keys(summary) - _mapping_keys(raw)
            if not _covered(path, fetcher._SUMMARY_ONLY_KEYS)
        }

        assert divergent == set(), (
            "these names appear on stdout and not in the raw file, so a filter "
            f"written from stdout finds nothing: {sorted(divergent)}"
        )

    def test_the_summary_only_exemptions_are_real_and_declared(
        self,
        fetcher: ModuleType,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # An exemption is how the check above gets weakened without anyone
        # noticing, so each one has to name a key stdout really has and the raw
        # file really lacks. One that is stale, or one added to hide a genuine
        # divergence in a key that does exist in both, fails here.
        summary, _ = _run(fetcher, monkeypatch, capsys, data_dir=tmp_path)
        raw = json.loads(Path(summary["paths"]["raw_output"]).read_text("utf-8"))
        declared = set(fetcher._SUMMARY_ONLY_KEYS)

        assert declared <= _mapping_keys(summary)
        assert declared & _mapping_keys(raw) == set()

    @pytest.mark.parametrize(
        "name", ["highlights", "truncated", "trend", "daily_activity"]
    )
    def test_the_names_the_incident_filtered_on_are_in_both(
        self,
        fetcher: ModuleType,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        name: str,
    ) -> None:
        # `trend_context` in the file against `trend` on stdout; `highlights`
        # and `truncated` on stdout and nowhere else. Each returned {} from the
        # raw file, with exit 0 and no message.
        summary, _ = _run(fetcher, monkeypatch, capsys, data_dir=tmp_path)
        raw = json.loads(Path(summary["paths"]["raw_output"]).read_text("utf-8"))

        assert summary[name], f"stdout has no {name}"
        assert raw.get(name), f"the raw file has no {name}"

    def test_the_old_name_is_gone_rather_than_kept_beside_the_new_one(
        self,
        fetcher: ModuleType,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        summary, _ = _run(fetcher, monkeypatch, capsys, data_dir=tmp_path)
        raw = json.loads(Path(summary["paths"]["raw_output"]).read_text("utf-8"))

        assert "trend_context" not in raw

    def test_the_raw_file_keeps_the_records_the_summary_only_counts(
        self,
        fetcher: ModuleType,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # Unification must widen stdout's names into the raw file, never narrow
        # the raw file to stdout's extracts.
        summary, _ = _run(fetcher, monkeypatch, capsys, data_dir=tmp_path)
        raw = json.loads(Path(summary["paths"]["raw_output"]).read_text("utf-8"))

        assert len(raw["daily_activity"]["notable_events"]) > len(
            summary["daily_activity"]["notable_events"]
        )
        assert len(raw["trend"]["issues"]) > len(summary["daily_activity"]["issues"])
        assert raw["daily_activity"]["counts"]["pull_requests"] == len(
            raw["daily_activity"]["pull_requests"]
        )

    def test_deriving_twice_counts_the_same_thing(self, fetcher: ModuleType) -> None:
        # The derived fields are written into the payload the summary is then
        # built from, so the derivation runs over its own output. A count of the
        # counts is not a count of anything.
        payload = {
            "daily_activity": {
                "issues": [{"kind": "issue", "number": 1}],
                "pull_requests": [],
                "issue_events": [{"event": "closed"}],
                "repository_events": [],
                "commits": [],
                "releases": [],
            },
            "trend": {"issues": [{"kind": "issue", "number": 1}], "commits": []},
        }

        fetcher._augment_payload(payload, limit=8, excerpt_limit=120)
        first = json.dumps(payload, sort_keys=True)
        fetcher._augment_payload(payload, limit=8, excerpt_limit=120)

        assert json.dumps(payload, sort_keys=True) == first
        assert payload["daily_activity"]["counts"] == {
            "issues": 1,
            "pull_requests": 0,
            "issue_events": 1,
            "repository_events": 0,
            "commits": 0,
            "releases": 0,
        }

    def test_the_summary_is_kept_beside_the_file_it_describes(
        self,
        fetcher: ModuleType,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # A filter is written from names that were read. Re-reading them beats
        # reproducing them from whatever part of stdout is still in view.
        summary, _ = _run(fetcher, monkeypatch, capsys, data_dir=tmp_path)
        stored = Path(summary["paths"]["summary"])

        assert stored.is_file()
        assert json.loads(stored.read_text("utf-8")) == summary
        assert stored.parent == Path(summary["paths"]["run_dir"])


class TestTheFindingsShapeIsHandedOver:
    """The renderer's envelope is printed, not left to be looked up.

    The dominant render failure was an invented wrapper around the whole
    findings document, retried byte-identically because the error named a
    missing key rather than the shape that was wanted. The runs that read the
    schema reference first did not make it; a skeleton on stdout is the same
    information in a place that cannot go unopened.
    """

    def test_stdout_carries_the_whole_envelope(
        self,
        fetcher: ModuleType,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        summary, _ = _run(fetcher, monkeypatch, capsys, data_dir=tmp_path)

        assert set(summary["template"]) == {
            "tldr",
            "significant_changes",
            "risks",
            "actions",
            "trends",
            "missing_capabilities",
            "opportunities",
            "evidence_gaps",
        }

    def test_every_key_carries_a_worked_example(
        self,
        fetcher: ModuleType,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # Empty arrays named the eight sections and never named a field inside
        # one, so a writer still had to guess an item's own keys -- and the guess
        # was observed live as a whole invented vocabulary, dropped in silence.
        summary, _ = _run(fetcher, monkeypatch, capsys, data_dir=tmp_path)

        for key, value in summary["template"].items():
            groups = [value] if isinstance(value, list) else list(value.values())
            assert groups, key
            for group in groups:
                assert group, key

    def test_every_example_entry_is_marked_so_it_can_be_dropped(
        self,
        fetcher: ModuleType,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # The examples are only safe to ship because none of them can be
        # published, and the renderer drops a whole entry rather than a field --
        # so the property that has to hold is that *every entry* carries the
        # marker somewhere, not merely that some of its values do. An example
        # whose every value happened to be a vocabulary word would be an example
        # nothing could remove.
        summary, _ = _run(fetcher, monkeypatch, capsys, data_dir=tmp_path)
        marker = fetcher._FINDINGS_PLACEHOLDER

        def entries(value: Any) -> list[Any]:
            if isinstance(value, list):
                return value
            return [entry for group in value.values() for entry in group]

        for key, value in summary["template"].items():
            for entry in entries(value):
                assert marker in json.dumps(entry, ensure_ascii=False), key

    def test_the_marker_is_the_one_the_renderer_refuses(
        self,
        fetcher: ModuleType,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # The two files are edited apart. A marker that drifted would leave the
        # examples publishable and nothing would say so: they would simply start
        # rendering as findings.
        module = _renderer()

        assert fetcher._FINDINGS_PLACEHOLDER == module._PLACEHOLDER

    def test_stdout_says_an_example_is_not_a_finding(
        self,
        fetcher: ModuleType,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        summary, _ = _run(fetcher, monkeypatch, capsys, data_dir=tmp_path)
        notes = " ".join(summary["notes"])

        assert fetcher._FINDINGS_PLACEHOLDER in notes
        assert "is not a finding" in notes

    def test_the_template_is_what_the_renderer_reads(
        self,
        fetcher: ModuleType,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # The two files are edited apart, so the skeleton is checked against the
        # renderer's own list of keys rather than against a copy of it.
        summary, _ = _run(fetcher, monkeypatch, capsys, data_dir=tmp_path)
        module = _renderer()

        assert set(summary["template"]) == set(module._FINDINGS_KEYS)

    def test_the_vocabularies_are_the_renderers_own(
        self,
        fetcher: ModuleType,
    ) -> None:
        # The same argument as the marker check above, one level down. Naming
        # every field stopped runs inventing field names and left them guessing
        # values -- a `medium` severity, from an example reading `stable` -- so
        # the accepted words are now taught here. Teaching them is only safe if
        # they are the renderer's words: a list that drifted would put a value
        # the renderer refuses into the one artefact runs reliably read, which
        # is worse than teaching no list at all, and nothing else would say so.
        module = _renderer()

        assert fetcher._FINDINGS_VOCABULARIES == {
            "severity": tuple(module._SEVERITY_MARKS),
            "label": tuple(module._LABELS),
            "direction": tuple(module._DIRECTION_MARKS),
            "confidence": tuple(module._CONFIDENCE),
        }

    def test_no_other_field_has_become_a_closed_vocabulary(
        self,
        fetcher: ModuleType,
    ) -> None:
        # The previous test pins the four lists that are taught. This one pins
        # that there are four. stdout tells a writer, in the same breath, that an
        # opportunity's kind, effort and risk are free text and are printed as
        # written; if a later change closes one of them, that sentence turns
        # wrong in the same silent way a drifted list would, and a template that
        # teaches nothing about the new field puts a run straight back to
        # guessing. Found by shape rather than by name, so a vocabulary added
        # under any name at all trips it.
        module = _renderer()
        closed = sorted(
            tuple(value)
            for name, value in vars(module).items()
            if not name.startswith("__")
            and isinstance(value, dict)
            and value
            and all(
                isinstance(key, str) and isinstance(word, str)
                for key, word in value.items()
            )
        )

        assert closed == sorted(
            tuple(words) for words in fetcher._FINDINGS_VOCABULARIES.values()
        )

    def test_every_closed_field_shows_the_whole_list_beside_it(
        self,
        fetcher: ModuleType,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # One legal example does not show a closed set: that is exactly what was
        # shipped, and runs guessed a neighbouring word from it. The list has to
        # be readable from the item the value sits on, not only from a reference
        # nothing opens.
        summary, _ = _run(fetcher, monkeypatch, capsys, data_dir=tmp_path)

        for field, entry in _closed_fields(summary["template"]):
            shown = json.dumps(entry, ensure_ascii=False)
            for word in fetcher._FINDINGS_VOCABULARIES[field]:
                assert word in shown, (field, word)

    def test_a_closed_fields_example_is_a_real_word_and_is_not_marked(
        self,
        fetcher: ModuleType,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # The crux of shipping the lists. Marking these values would force a
        # writer to replace the one thing they cannot guess, and would cost more
        # than the rating: the renderer reads a whole entry for the marker, so a
        # marker left on a severity discards the finding around it. Left legal, a
        # copied word is a conservative default on a claim its writer did write.
        summary, _ = _run(fetcher, monkeypatch, capsys, data_dir=tmp_path)

        for field, entry in _closed_fields(summary["template"]):
            assert entry[field] in fetcher._FINDINGS_VOCABULARIES[field]
            assert fetcher._FINDINGS_PLACEHOLDER not in entry[field]

    def test_stdout_names_every_accepted_word(
        self,
        fetcher: ModuleType,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        summary, _ = _run(fetcher, monkeypatch, capsys, data_dir=tmp_path)
        notes = " ".join(summary["notes"])

        for field, words in fetcher._FINDINGS_VOCABULARIES.items():
            assert field in notes
            for word in words:
                assert word in notes, (field, word)

    def test_stdout_says_the_template_takes_no_wrapper(
        self,
        fetcher: ModuleType,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        summary, _ = _run(fetcher, monkeypatch, capsys, data_dir=tmp_path)
        notes = " ".join(summary["notes"])

        assert "template" in notes
        assert "wrapped around" in notes


class TestRecordTrimming:
    """Records carry the fields the report formats cite and nothing else."""

    def test_issue_keeps_the_cited_fields(self, fetcher: ModuleType) -> None:
        compact = fetcher._compact_issue(
            _issue(7, is_pull=True, updated_at=_EARLIER), "updated"
        )

        for field in (
            "kind",
            "number",
            "title",
            "url",
            "state",
            "author",
            "labels",
            "created_at",
            "updated_at",
            "activity_at",
        ):
            assert field in compact

    def test_long_bodies_are_bounded(self, fetcher: ModuleType) -> None:
        compact = fetcher._compact_issue(
            _issue(7, is_pull=False, updated_at=_EARLIER), "updated"
        )

        assert len(compact["body_excerpt"]) <= fetcher._BODY_LIMIT + 1

    def test_empty_fields_are_omitted(self, fetcher: ModuleType) -> None:
        raw = _issue(7, is_pull=False, updated_at=_EARLIER)
        raw["body"] = ""
        raw["author_association"] = ""

        compact = fetcher._compact_issue(raw, "updated")

        assert "closed_at" not in compact
        assert "state_reason" not in compact
        assert "body_excerpt" not in compact
        assert "author_association" not in compact

    def test_changed_files_drop_the_blob_link(
        self,
        fetcher: ModuleType,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        summary, _ = _run(fetcher, monkeypatch, capsys, data_dir=tmp_path)
        raw = json.loads(Path(summary["paths"]["raw_output"]).read_text("utf-8"))
        detailed = [
            item
            for item in raw["daily_activity"]["pull_requests"]
            if isinstance(item.get("details"), dict)
        ]

        assert detailed
        for item in detailed:
            for file in item["details"].get("files", []):
                assert "blob_url" not in file

    def test_trimming_shrinks_the_raw_structure(self, fetcher: ModuleType) -> None:
        raw_event = {
            "id": 1,
            "type": "PushEvent",
            "created_at": _EARLIER,
            "actor": {"login": "someone"},
            "payload": {"ref": "refs/heads/main", "size": 2},
        }

        compact = fetcher._compact_repo_event(raw_event)

        assert compact["ref"] == "refs/heads/main"
        assert "review_body_excerpt" not in compact
        assert "release_url" not in compact


class TestTheRunDirectoryIsNotAnOutputTarget:
    """The run directory is emptied by the fetch, so nothing may write into it there.

    The directory is cleared on entry, and that timing is deliberate: a run that
    fails never reaches a cleanup step, so leftovers have to go before the run
    starts rather than after it ends. The cost of that timing was a command line
    that empties the directory and writes into it at once --

        digest.py fetch ... | some-filter > <run directory>/extract.json

    -- where the shell creates `extract.json` while it sets the pipeline up, the
    fetch deletes the directory underneath it, and the filter's output lands
    seconds later in a file with no name. Nothing fails at the time. The run
    finds out much later, when reading the file back reports that it is not
    there, and a path that is not there reads like a path that was mistyped.

    So the clear now refuses when the directory is being written to, rather than
    moving to exit and losing the property the entry-time clear is for.
    """

    def _run_dir(self, fetcher: ModuleType, tmp_path: Path) -> Path:
        run_dir = fetcher.run_dir_for(tmp_path / "state.json")
        run_dir.mkdir(parents=True)
        return run_dir

    def test_a_file_a_live_process_holds_open_stops_the_fetch(
        self, fetcher: ModuleType, tmp_path: Path
    ) -> None:
        run_dir = self._run_dir(fetcher, tmp_path)
        with (run_dir / "template.json").open("w", encoding="utf-8"):
            with pytest.raises(SystemExit) as refusal:
                fetcher._prepare_run_dir(tmp_path / "state.json", tmp_path / "raw.json")

        assert "template.json" in str(refusal.value)
        assert (run_dir / "template.json").exists(), "refused, not deleted mid-write"

    def test_the_refusal_says_what_to_do_instead(
        self, fetcher: ModuleType, tmp_path: Path
    ) -> None:
        """A rejection nothing can act on is reissued unchanged until a host stops the run.

        That is the whole cost of this failure mode: the first message the run
        saw said only that a file was missing, which is true of a mistyped path
        too, so the run went looking for a path problem it did not have.
        """
        run_dir = self._run_dir(fetcher, tmp_path)
        with (run_dir / "template.json").open("w", encoding="utf-8"):
            with pytest.raises(SystemExit) as refusal:
                fetcher._prepare_run_dir(tmp_path / "state.json", tmp_path / "raw.json")

        message = str(refusal.value)
        assert "stdout" in message, "what to read instead"
        assert "summary.json" in message, "where the same document is on disk"
        assert "on its own" in message, "how to reissue the command"
        assert "cannot help" in message, "why reissuing it unchanged will not do"

    def test_a_leftover_nothing_is_writing_is_still_deleted(
        self, fetcher: ModuleType, tmp_path: Path
    ) -> None:
        """The property the entry-time clear exists for, unchanged by the guard.

        A file a failed run left behind is what a later run finds and follows
        instead of its own workflow, and it is indistinguishable from one this
        run wrote. Age is not what tells it apart from a write in flight --
        whether anything still holds it open is.
        """
        run_dir = self._run_dir(fetcher, tmp_path)
        (run_dir / "findings.json").write_text("yesterday's", encoding="utf-8")
        (run_dir / "nested").mkdir()

        prepared = fetcher._prepare_run_dir(
            tmp_path / "state.json", tmp_path / "raw.json"
        )

        assert prepared == run_dir
        assert not (run_dir / "findings.json").exists()
        assert not (run_dir / "nested").exists()
        assert (run_dir / "run.json").is_file()

    def test_a_normal_fetch_is_untouched_by_the_guard(
        self,
        fetcher: ModuleType,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The summary the documented flow reads is exactly what it was."""
        summary, _ = _run(fetcher, monkeypatch, capsys, data_dir=tmp_path)

        assert summary["ok"] is True
        assert Path(summary["paths"]["run_dir"]).is_dir()
        assert Path(summary["paths"]["summary"]).is_file()
        assert summary["template"]

    def test_an_untouched_directory_reports_nothing_held(
        self, fetcher: ModuleType, tmp_path: Path
    ) -> None:
        run_dir = self._run_dir(fetcher, tmp_path)
        (run_dir / "findings.json").write_text("closed again", encoding="utf-8")

        assert fetcher.names_held_open_in(run_dir) == []

    def test_a_held_file_deeper_down_is_named_by_its_top_level_entry(
        self, fetcher: ModuleType, tmp_path: Path
    ) -> None:
        """What the caller has to remove is the entry, not the descendant.

        The directory is emptied wholesale, so a write anywhere under it is
        destroyed and the name worth printing is the one that would be deleted.
        """
        run_dir = self._run_dir(fetcher, tmp_path)
        (run_dir / "dump").mkdir()
        with (run_dir / "dump" / "raw_data.json").open("w", encoding="utf-8"):
            assert fetcher.names_held_open_in(run_dir) == ["dump"]


class TestStdoutSaysItIsTheAnswer:
    """The guidance that has to arrive at the moment of use, not before it.

    SKILL.md is read once, at the start; stdout is what is in front of the
    reader when it decides what to do with the fetch's output. So the two things
    most easily forgotten between the two -- that this document is the whole
    answer, and that the run directory is not somewhere to redirect into -- are
    stated on stdout as well.
    """

    def test_stdout_says_nothing_has_to_be_extracted_from_it(
        self,
        fetcher: ModuleType,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        summary, _ = _run(fetcher, monkeypatch, capsys, data_dir=tmp_path)
        notes = " ".join(summary["notes"])

        assert "the answer, not a pointer to one" in notes
        assert "extracted from it" in notes

    def test_stdout_names_the_command_line_that_destroys_a_write(
        self,
        fetcher: ModuleType,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        summary, _ = _run(fetcher, monkeypatch, capsys, data_dir=tmp_path)
        notes = " ".join(summary["notes"])

        assert "same command line as the fetch" in notes
        assert "paths.summary" in notes, "where the same document already is"

    def test_stdout_says_an_invented_file_name_is_read_by_nothing(
        self,
        fetcher: ModuleType,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """`template` and `paths` are keys of this document, not files beside it.

        The names that get invented are invented out of the document's own keys,
        so the correction has to say where those keys already are.
        """
        summary, _ = _run(fetcher, monkeypatch, capsys, data_dir=tmp_path)
        notes = " ".join(summary["notes"])

        assert "template.json" in notes
        assert "keys of this document" in notes
