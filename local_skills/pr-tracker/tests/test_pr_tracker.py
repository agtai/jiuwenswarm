"""Tests for the parts of the skill that are decidable without a network.

Everything here is pure logic over dictionaries and files: identity, the store
round-trip, the delta engine, rotation, the multi-link fan-out, and the pairing
collapse. Nothing dials GitHub or GitCode -- the network clients are deliberately
kept out of the tested surface, because a test that needs a tracker to be up
fails for reasons that have nothing to do with the code.

Run:
    python3 -m pytest <skill>/tests -q
"""

from __future__ import annotations

import ast
import json
import re
import sys
import threading
import time
from datetime import timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import pr_tracker as pt

WHEN = "2026-08-12T09:00:00Z"
GITHUB_PR = "https://github.com/openJiuwen-ai/jiuwenswarm/pull/2724"
GITCODE_MR = "https://gitcode.com/openJiuwen/jiuwenswarm/merge_requests/4717"

# The pairing for the two links above, as a deployment would configure it. It is
# built here rather than imported from the script because the script no longer
# knows any repository: every pairing below is one this file states.
PAIRED = pt.Repositories.from_config(
    {"openJiuwen-ai/jiuwenswarm": {"gitcode": "openJiuwen/jiuwenswarm"}}, []
)


def link(url: str) -> pt.ParsedLink:
    parsed = pt.canonicalise(url)
    assert parsed is not None
    return parsed


def register(ledger: pt.Ledger, url: str, *, ts: str = "1786514497.123456", via: str = "url"):
    return pt.upsert_registration(
        ledger,
        link(url),
        via=via,
        slack_ts=ts,
        permalink="https://example.slack.com/archives/C0BPLSPHHDZ/p1786514497123456",
        author="U123",
        when=WHEN,
    )


# ------------------------------------------------------------------- identity


@pytest.mark.parametrize(
    "url,key",
    [
        (GITHUB_PR, "github/openjiuwen-ai/jiuwenswarm#pr2724"),
        (f"{GITHUB_PR}/files", "github/openjiuwen-ai/jiuwenswarm#pr2724"),
        (f"{GITHUB_PR}/commits", "github/openjiuwen-ai/jiuwenswarm#pr2724"),
        (f"{GITHUB_PR}#issuecomment-99", "github/openjiuwen-ai/jiuwenswarm#pr2724"),
        (f"{GITHUB_PR}/?utm=slack", "github/openjiuwen-ai/jiuwenswarm#pr2724"),
        ("HTTPS://GitHub.com/openJiuwen-ai/jiuwenswarm/pull/2724", "github/openjiuwen-ai/jiuwenswarm#pr2724"),
        ("https://www.github.com/o/r/issues/12", "github/o/r#issue12"),
        (GITCODE_MR, "gitcode/openjiuwen/jiuwenswarm#mr4717"),
        (
            "https://gitcode.com/openJiuwen/jiuwenswarm/-/merge_requests/4717",
            "gitcode/openjiuwen/jiuwenswarm#mr4717",
        ),
        (
            "https://api.gitcode.com/api/v5/repos/openJiuwen/jiuwenswarm/pulls/4717",
            "gitcode/openjiuwen/jiuwenswarm#mr4717",
        ),
    ],
)
def test_canonical_url_reduces_to_one_key(url, key):
    assert link(url).key == key


def test_trailing_punctuation_does_not_become_part_of_the_url():
    assert link(f"{GITHUB_PR}.").url == GITHUB_PR
    assert link(f"{GITHUB_PR},").number == 2724


def test_untrackable_url_gets_a_stable_other_key():
    first = link("https://example.com/blog/post")
    second = link("https://example.com/blog/post")
    assert first.kind == "other"
    assert first.key == second.key
    assert first.key.startswith("other/")


def test_a_repository_url_is_not_an_item():
    assert link("https://github.com/openJiuwen-ai/jiuwenswarm").kind == "other"
    assert link("https://github.com/openJiuwen-ai/jiuwenswarm/pull/abc").kind == "other"


# ------------------------------------------------------- multi-link fan-out


def test_one_message_with_several_links_fans_out_to_several_items():
    """The link trigger fires once per message however many links it carries."""
    text = (
        "Two of these need eyes: https://github.com/o/r/pull/1 and "
        "<https://github.com/o/r/issues/2|the issue>, context in "
        "https://example.com/rfc"
    )
    found = pt.links_in_text(text)
    assert [item.key for item in found] == [
        "github/o/r#pr1",
        "github/o/r#issue2",
        found[2].key,
    ]
    assert found[2].kind == "other"


def test_two_spellings_of_one_item_in_one_message_are_one_row_two_sources():
    ledger = pt.Ledger(path=Path("unused"), rows=[])
    text = f"{GITHUB_PR} and also {GITHUB_PR}/files"
    found = pt.links_in_text(text)
    assert len(found) == 1, "identity collapses before the store is touched"
    for item in pt.HTTP_URL_RE.findall(text):
        pt.upsert_registration(
            ledger,
            link(item),
            via="url",
            slack_ts="1786514497.123456",
            permalink=None,
            author=None,
            when=WHEN,
        )
    assert len(ledger.rows) == 1
    assert len(ledger.rows[0]["sources"]) == 2, "one entry per (slack_ts, url)"


def test_sources_dedupe_on_ts_and_url_not_on_ts_alone():
    ledger = pt.Ledger(path=Path("unused"), rows=[])
    register(ledger, "https://github.com/o/r/pull/1", ts="111.1")
    register(ledger, "https://github.com/o/r/pull/2", ts="111.1")
    assert len(ledger.rows) == 2, "message_ts is provenance, never identity"
    register(ledger, "https://github.com/o/r/pull/1", ts="111.1")
    assert len(ledger.rows[0]["sources"]) == 1


# --------------------------------------------------------- upsert and revival


def test_reposting_a_link_upserts_rather_than_duplicating():
    """The first remedy for a missed link: reposting must not duplicate."""
    ledger = pt.Ledger(path=Path("unused"), rows=[])
    _, first = register(ledger, GITHUB_PR, ts="111.1")
    row, second = register(ledger, f"{GITHUB_PR}/files", ts="222.2", via="operator")
    assert (first, second) == ("registered", "updated")
    assert len(ledger.rows) == 1
    assert [entry["via"] for entry in row["sources"]] == ["url", "operator"]
    assert row["first_seen_utc"] == pt.slack_ts_to_utc("111.1")


def test_reposting_a_retired_item_revives_it_with_its_history():
    ledger = pt.Ledger(path=Path("unused"), rows=[])
    row, _ = register(ledger, GITHUB_PR)
    row["lifecycle"] = "retired"
    row["retired_at_utc"] = WHEN
    revived, outcome = register(ledger, GITHUB_PR, ts="999.9")
    assert outcome == "reopened"
    assert revived["lifecycle"] == "active"
    assert revived["reopen_count"] == 1
    assert revived["first_seen_utc"] == pt.slack_ts_to_utc("1786514497.123456")


# ------------------------------------------------------- GitHub/GitCode pair


def test_github_and_gitcode_links_collapse_to_one_row_once_paired():
    """The pair the github-pr-<N> branch convention exists to catch."""
    ledger = pt.Ledger(path=Path("unused"), rows=[])
    register(ledger, GITHUB_PR, ts="111.1")
    register(ledger, GITCODE_MR, ts="111.1")
    assert len(ledger.rows) == 2, "not pairable from the URLs alone"

    github_row = ledger.rows[0]
    github_row["mr_iid"] = 4717  # what the refresh phase discovers

    pairing = pt.pairing_from_rows(ledger.rows)
    assert pairing == {"gitcode/openjiuwen/jiuwenswarm#mr4717": github_row["key"]}
    merged = pt.coalesce_pairs(ledger, pairing)

    assert merged == [("gitcode/openjiuwen/jiuwenswarm#mr4717", github_row["key"])]
    assert len(ledger.rows) == 1
    survivor = ledger.rows[0]
    assert survivor["key"] == "github/openjiuwen-ai/jiuwenswarm#pr2724"
    assert "gitcode/openjiuwen/jiuwenswarm#mr4717" in survivor["aliases"]
    assert len(survivor["sources"]) == 2, "both spellings survive the merge"


def test_the_gitcode_alias_routes_a_later_repost_to_the_surviving_row():
    ledger = pt.Ledger(path=Path("unused"), rows=[])
    register(ledger, GITHUB_PR, ts="111.1")
    register(ledger, GITCODE_MR, ts="111.1")
    ledger.rows[0]["mr_iid"] = 4717
    pt.coalesce_pairs(ledger, pt.pairing_from_rows(ledger.rows))
    register(ledger, GITCODE_MR, ts="333.3")
    assert len(ledger.rows) == 1


def test_a_gitcode_only_row_is_rekeyed_by_its_source_branch():
    """The one pairing step that cannot work without configuration.

    A source branch names a number and nothing else; only the configured pairing
    says which repository that number belongs to, and only the configured key
    says how its owner capitalises it.
    """
    ledger = pt.Ledger(path=Path("unused"), rows=[])
    row, _ = register(ledger, GITCODE_MR)
    row["mr_source_branch"] = "github-pr-2724"
    pt.coalesce_pairs(ledger, pt.pairing_from_rows(ledger.rows, PAIRED), PAIRED)
    assert ledger.rows[0]["key"] == "github/openjiuwen-ai/jiuwenswarm#pr2724"
    assert ledger.rows[0]["url"] == GITHUB_PR
    assert ledger.rows[0]["repo"] == "openJiuwen-ai/jiuwenswarm", "the owner's own case"
    assert ledger.rows[0]["tracker"] == "github"


def test_an_unpaired_repository_leaves_a_gitcode_row_where_it_is():
    """Absent from configuration is a supported state, not a fault.

    A wrong pairing reports another project's merge as this one's, so a
    repository nobody has confirmed a pairing for is tracked on the first
    tracker alone and its merge requests keep their own identity.
    """
    ledger = pt.Ledger(path=Path("unused"), rows=[])
    row, _ = register(ledger, GITCODE_MR)
    row["mr_source_branch"] = "github-pr-2724"
    assert pt.pairing_from_rows(ledger.rows, pt.Repositories()) == {}
    assert ledger.rows[0]["key"] == "gitcode/openjiuwen/jiuwenswarm#mr4717"


def test_an_unpaired_gitcode_row_keeps_its_own_key():
    ledger = pt.Ledger(path=Path("unused"), rows=[])
    register(ledger, GITCODE_MR)
    assert pt.pairing_from_rows(ledger.rows) == {}
    assert ledger.rows[0]["key"] == "gitcode/openjiuwen/jiuwenswarm#mr4717"


# ------------------------------------------------------------ store handling


def test_schema_round_trip(tmp_path):
    path = tmp_path / "C0BPLSPHHDZ.jsonl"
    ledger = pt.Ledger.load(path)
    assert ledger.existed is False
    register(ledger, GITHUB_PR)
    register(ledger, "https://github.com/o/r/issues/5")
    ledger.write()

    reloaded = pt.Ledger.load(path)
    assert reloaded.existed is True
    assert [row["key"] for row in reloaded.rows] == [row["key"] for row in ledger.rows]
    assert reloaded.rows[0] == ledger.rows[0]
    assert path.read_text(encoding="utf-8").count("\n") == 2


def test_a_corrupt_line_is_skipped_kept_verbatim_and_reported(tmp_path):
    path = tmp_path / "store.jsonl"
    good = json.dumps({"key": "github/o/r#pr1", "url": GITHUB_PR, "lifecycle": "active"})
    path.write_text(f"{good}\n{{not json at all\n", encoding="utf-8")
    ledger = pt.Ledger.load(path)
    assert [row["key"] for row in ledger.rows] == ["github/o/r#pr1"]
    assert ledger.corrupt == [(2, "{not json at all")]
    ledger.write()
    assert "{not json at all" in path.read_text(encoding="utf-8")


def test_sidecars_derive_from_the_ledger_stem():
    path = Path("/srv/state/skills/pr-tracker/C0BPLSPHHDZ.jsonl")
    assert pt.runs_path(path).name == "C0BPLSPHHDZ.runs.json"
    assert pt.lock_path(path).name == "C0BPLSPHHDZ.jsonl.lock"


def test_owner_mismatch_stops_the_run():
    with pytest.raises(SystemExit) as error:
        pt.check_owner({"channel_id": "C_OTHER"}, "C0BPLSPHHDZ")
    assert "C_OTHER" in str(error.value)
    pt.check_owner({}, "C0BPLSPHHDZ")  # a fresh store adopts the channel


def test_state_file_inside_the_skill_directory_is_refused():
    inside = pt.SKILL_DIR / "state" / "C0BPLSPHHDZ.jsonl"
    with pytest.raises(SystemExit) as error:
        pt.reject_path_in_skill_dir(inside, "--state-file")
    assert "skill directory" in str(error.value)
    pt.reject_path_in_skill_dir("/tmp/elsewhere.jsonl", "--state-file")


# ------------------------------------------------------------- default paths


def test_default_state_file_uses_xdg_when_set(monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", "/xdg/state")
    assert pt.default_state_file("C0BPLSPHHDZ") == Path(
        "/xdg/state/pr-tracker/C0BPLSPHHDZ.jsonl"
    )


def test_default_state_file_falls_back_when_xdg_is_unset(monkeypatch, tmp_path):
    """The branch this host actually exercises: XDG_STATE_HOME is unset here."""
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    assert pt.default_state_file("C0BPLSPHHDZ") == (
        tmp_path / ".local/state/pr-tracker/C0BPLSPHHDZ.jsonl"
    )


def test_an_empty_xdg_variable_is_treated_as_unset(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_STATE_HOME", "   ")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    assert pt.default_state_file("C0BPLSPHHDZ").is_relative_to(tmp_path / ".local/state")


def test_state_file_expands_the_data_dir_variable(monkeypatch):
    monkeypatch.setenv("JIUWENSWARM_DATA_DIR", "/srv/example/data")
    path, notes = pt.resolve_state_file(
        "$JIUWENSWARM_DATA_DIR/agent/workspace/state/skills/"
        "pr-tracker/C0BPLSPHHDZ.jsonl",
        "C0BPLSPHHDZ",
    )
    assert path == Path(
        "/srv/example/data/agent/workspace/state/skills/"
        "pr-tracker/C0BPLSPHHDZ.jsonl"
    )
    assert notes == []


def test_an_unset_variable_in_the_state_path_is_a_hard_stop(monkeypatch):
    monkeypatch.delenv("NOT_SET_ANYWHERE", raising=False)
    with pytest.raises(SystemExit):
        pt.resolve_state_file("$NOT_SET_ANYWHERE/store.jsonl", "C0BPLSPHHDZ")


def test_a_missing_state_file_flag_says_it_guessed():
    _, notes = pt.resolve_state_file(None, "C0BPLSPHHDZ")
    assert notes and "XDG default" in notes[0]


# -------------------------------------------------------------------- status


@pytest.mark.parametrize(
    "facts,expected",
    [
        ({}, "registered"),
        ({"cla_ok": False}, "cla_pending"),
        ({"cla_ok": True, "ci_verdict": "running"}, "ci_running"),
        ({"cla_ok": True, "ci_verdict": "fail"}, "ci_failed"),
        ({"cla_ok": True, "ci_verdict": "pass"}, "awaiting_review"),
        ({"cla_ok": True, "ci_verdict": "pass", "lgtm_count": 1}, "lgtm_partial"),
        ({"approved": True, "lgtm_count": 2}, "approved"),
        ({"approved": True, "mr_state": "merged"}, "landed"),
        ({"mr_state": "closed"}, "closed"),
        ({"gh_state": "closed"}, "closed"),
        ({"gone": True}, "gone"),
    ],
)
def test_derive_status(facts, expected):
    row = {"kind": "pull_request", **facts}
    assert pt.derive_status(row) == expected


def test_a_merged_mr_lands_even_while_the_github_pr_is_open():
    """The line a model summarising by hand cannot produce."""
    row = {"kind": "pull_request", "gh_state": "open", "mr_state": "merged"}
    assert pt.derive_status(row) == "landed"


def test_labels_become_facts():
    facts = pt.labels_to_facts(
        [
            "github-mirror",
            "sig/jiuwenswarm",
            "openJiuwen-cla/yes",
            "ci-successful",
            "lgtm-douran",
            "lgtm-alan_cheng",
            "needs-something-new",
        ]
    )
    assert facts["cla_ok"] is True
    assert facts["approved"] is False
    assert facts["lgtm_count"] == 2
    assert facts["ci_verdict"] == "pass"
    assert facts["unknown_labels"] == ["needs-something-new"]


# --------------------------------------------------------------------- delta


def base_row(**facts):
    row = {
        "key": "github/o/r#pr1",
        "kind": "pull_request",
        "lifecycle": "active",
        "refresh_ok": True,
        "observed_through_utc": WHEN,
        "cla_ok": True,
        "ci_verdict": "pass",
        "lgtm_count": 0,
        "comment_count": 3,
        "head_sha": "aaa",
        "conflicted": False,
        "reported_status": "awaiting_review",
        "reported_cla_ok": True,
        "reported_ci_verdict": "pass",
        "reported_lgtm_count": 0,
        "reported_comment_count": 3,
        "reported_head_sha": "aaa",
        "reported_conflicted": False,
        "reported_approved": False,
    }
    row.update(facts)
    return row


def test_no_change_produces_no_delta():
    assert pt.compute_delta(base_row()) == []


def test_becoming_conflicted_is_reported_once():
    row = base_row(conflicted=True)
    kinds = [kind for kind, _ in pt.compute_delta(row)]
    assert "conflicted" in kinds
    row["reported_conflicted"] = True
    assert [kind for kind, _ in pt.compute_delta(row)] == []


def test_ci_going_red_carries_the_hint():
    row = base_row(
        ci_verdict="fail",
        ci_failure_hint="matches_known_flake",
        ci_flake_signatures=["example.com ResourceWarning"],
    )
    changes = pt.compute_delta(row)
    assert changes[0][0] == "ci_red"
    assert "retrigger" in changes[0][1]


def test_an_unclassifiable_failure_says_so():
    row = base_row(ci_verdict="fail", ci_failure_hint="unclassified")
    assert "could not classify" in pt.compute_delta(row)[0][1]


def test_lgtm_progress_is_a_change_even_though_merge_stays_blocked():
    changes = dict(pt.compute_delta(base_row(lgtm_count=1)))
    assert changes["lgtm"] == "lgtm 0 -> 1"


def test_impact_ranking_puts_landed_first_and_a_push_last():
    landed = pt.compute_delta(base_row(mr_state="merged"))
    push = pt.compute_delta(base_row(head_sha="bbb"))
    comments = pt.compute_delta(base_row(comment_count=5))
    assert pt.rank_of(landed) < pt.rank_of(comments) < pt.rank_of(push)


def test_a_failed_refresh_reports_nothing_for_that_item():
    """A failed refresh must not be rendered as "nothing changed"."""
    assert pt.compute_delta(base_row(refresh_ok=False, conflicted=True)) == []


def test_an_untracked_row_never_reports():
    assert pt.compute_delta(base_row(lifecycle="ignored", conflicted=True)) == []


def test_a_dismissed_approval_is_reported():
    """Branch protection drops a stale approval on every push; that is news."""
    changes = dict(pt.compute_delta(base_row(approved=False, reported_approved=True)))
    assert changes["approved"] == "approval dismissed"


def test_ci_catching_up_with_the_head_is_reported():
    changes = dict(pt.compute_delta(base_row(stale_ci=False, reported_stale_ci=True)))
    assert "caught up" in changes["stale_ci"]


# ------------------------------------------------------- the mirror is closed

# `reported_*` is only ever written by a receipt, and a receipt only covers rows
# that appeared in a report. So a field that can differ from its mirror without
# producing a delta never gets mirrored: it sticks, and whether the *next*
# transition on that field is reported comes down to whether some unrelated
# delta happened to launder the mirror in between. These tests close that hole
# for every mirrored field at once, so a field added later cannot reopen it.

BOOKKEEPING = {"observed_through_utc", "last_mentioned_run"}
KEY = "github/o/r#pr1"


def mirrored_fields(row=None):
    """The fields a receipt copies forward -- discovered, never listed here.

    Read off `build_receipt` rather than off `REPORTED_FIELDS`, because the
    receipt writes four mirrors that are not in that tuple.
    """
    row = row or base_row()
    entry = pt.build_receipt([KEY], {KEY: row}, WHEN, 1)[KEY]
    return sorted(
        name[len("reported_") :]
        for name in entry
        if name.startswith("reported_") and name not in BOOKKEEPING
    )


# (current facts, mirror facts, expectation). The expectation is `True` when the
# divergence must produce a delta, or the reason it is deliberately silent.
MIRROR_PROBES: dict[str, list[tuple[dict, dict, object]]] = {
    "approved": [
        ({"approved": True}, {"reported_approved": False}, True),
        ({"approved": False}, {"reported_approved": True}, True),
    ],
    "conflicted": [
        ({"conflicted": True}, {"reported_conflicted": False}, True),
        ({"conflicted": False}, {"reported_conflicted": True}, True),
    ],
    "stale_ci": [
        ({"stale_ci": True}, {"reported_stale_ci": False}, True),
        ({"stale_ci": False}, {"reported_stale_ci": True}, True),
    ],
    "lgtm_count": [
        ({"lgtm_count": 1}, {"reported_lgtm_count": 0}, True),
        ({"lgtm_count": 0}, {"reported_lgtm_count": 1}, True),
    ],
    "cla_ok": [
        ({"cla_ok": False}, {"reported_cla_ok": True}, True),
        ({"cla_ok": True}, {"reported_cla_ok": False}, True),
        (
            {"cla_ok": None},
            {"reported_cla_ok": True},
            "an unknown CLA state is not news. The mirror keeps the last value "
            "the reader was told, so any later known value still differs from it",
        ),
        (
            {"cla_ok": True},
            {"reported_cla_ok": None},
            "nothing has been reported yet, so there is no change to report",
        ),
    ],
    "ci_verdict": [
        ({"ci_verdict": "fail"}, {"reported_ci_verdict": "pass"}, True),
        ({"ci_verdict": "pass"}, {"reported_ci_verdict": "fail"}, True),
        ({"ci_verdict": "running"}, {"reported_ci_verdict": "pass"}, True),
        ({"ci_verdict": "pass"}, {"reported_ci_verdict": None}, True),
        (
            {"ci_verdict": None},
            {"reported_ci_verdict": "pass"},
            "no CI label means the state is unknown, which is not news. The "
            "mirror keeps the last value the reader was told, so any later "
            "verdict still differs from it",
        ),
    ],
    "ci_failure_hint": [
        (
            {"ci_verdict": "fail", "ci_failure_hint": "unrelated_to_known_flake"},
            {"reported_ci_verdict": "fail", "reported_ci_failure_hint": "matches_known_flake"},
            True,
        ),
        (
            {"ci_verdict": "fail", "ci_failure_hint": "matches_known_flake"},
            {"reported_ci_verdict": "fail", "reported_ci_failure_hint": "unrelated_to_known_flake"},
            True,
        ),
        (
            {"ci_verdict": "pass", "ci_failure_hint": None},
            {"reported_ci_verdict": "pass", "reported_ci_failure_hint": "matches_known_flake"},
            "the hint only qualifies a failure. With CI not failing there is no "
            "failure to describe, and a later failure the reader was not already "
            "told about differs in the verdict, the hint, or both",
        ),
    ],
    "comment_count": [
        ({"comment_count": 4}, {"reported_comment_count": 3}, True),
        (
            {"comment_count": 2},
            {"reported_comment_count": 3},
            "a deleted comment is not news. The mirror is a high-water mark, a "
            "deliberate trade that also holds back a comment posted after a "
            "deletion until the count passes the old peak",
        ),
    ],
    "head_sha": [
        ({"head_sha": "bbb"}, {"reported_head_sha": "aaa"}, True),
        ({"head_sha": "aaa"}, {"reported_head_sha": "bbb"}, True),
        (
            {"head_sha": None},
            {"reported_head_sha": "aaa"},
            "a refresh that returned no head sha is not a push",
        ),
        (
            {"head_sha": "aaa"},
            {"reported_head_sha": None},
            "nothing has been reported yet, so the first head sha is not a push",
        ),
    ],
    "status": [
        ({"mr_state": "merged"}, {"reported_status": "awaiting_review"}, True),
        ({"gh_state": "closed"}, {"reported_status": "awaiting_review"}, True),
        ({"gone": True}, {"reported_status": "awaiting_review"}, True),
    ],
}


def test_every_mirrored_field_is_probed():
    """A new `reported_*` field must arrive with probes, or this fails.

    The point of the guard is that it cannot be satisfied by silence: adding a
    mirror without saying how it becomes a delta is the defect itself.
    """
    assert set(mirrored_fields()) == set(MIRROR_PROBES)


@pytest.mark.parametrize(
    ("field", "current", "mirror", "expected"),
    [
        (field, current, mirror, expected)
        for field, probes in sorted(MIRROR_PROBES.items())
        for current, mirror, expected in probes
    ],
)
def test_a_mirrored_field_cannot_diverge_without_a_delta(field, current, mirror, expected):
    changes = pt.compute_delta(base_row(**current, **mirror))
    if expected is True:
        assert changes, f"{field} can differ from its mirror without producing a delta"
    else:
        assert not changes, f"{field} produced a delta the exemption says it should not"


# Fields whose cycle is deliberately not closed, and why.
CYCLE_EXEMPT = {
    "comment_count": "the high-water mark never moves down, by design",
    "status": "the terminal statuses do not revert; the lifecycle rotation owns "
    "the way back, and it commits a receipt of its own",
    "ci_failure_hint": "meaningful only behind a failing verdict, whose own "
    "cycle carries it",
}
CYCLES = {
    "approved": (True, False),
    "conflicted": (True, False),
    "stale_ci": (True, False),
    "lgtm_count": (1, 0),
    "cla_ok": (False, True),
    "ci_verdict": ("fail", "pass"),
    "head_sha": ("bbb", "aaa"),
}


def cycle(field, there, back):
    """Flip a field there and back twice, committing exactly what a run would.

    A receipt is only built for a row that the report named, so a step that
    produces no delta commits nothing -- which is the whole mechanism under
    test, reproduced rather than described.
    """
    row = base_row(**{field: back})
    ledger = pt.Ledger(path=Path("unused"), rows=[row])
    pt.apply_receipt(ledger, pt.build_receipt([KEY], {KEY: row}, WHEN, 1), WHEN)
    fired = []
    for index, value in enumerate((there, back, there, back), start=2):
        row[field] = value
        changes = pt.compute_delta(row)
        fired.append(bool(changes))
        if changes:
            pt.apply_receipt(ledger, pt.build_receipt([KEY], {KEY: row}, WHEN, index), WHEN)
    return fired


def test_every_cycled_field_is_named():
    assert set(CYCLES) | set(CYCLE_EXEMPT) == set(MIRROR_PROBES)


@pytest.mark.parametrize(("field", "values"), sorted(CYCLES.items()))
def test_a_change_reported_once_can_be_reported_again(field, values):
    """The bug this guards: report a change, revert it, and the revert is
    silent, so nothing commits, so the mirror keeps the old value and the same
    change can never be reported a second time."""
    assert cycle(field, *values) == [True, True, True, True]


# --------------------------------------------------------- watermark commit


def test_the_delta_survives_a_run_that_never_delivered():
    """At-least-once: an uncommitted report repeats rather than being lost."""
    ledger = pt.Ledger(path=Path("unused"), rows=[base_row(conflicted=True)])
    rows_by_key = {row["key"]: row for row in ledger.rows}
    receipt = pt.build_receipt(["github/o/r#pr1"], rows_by_key, WHEN, 1)
    # Delivery fails, so `commit` never runs.
    assert pt.compute_delta(ledger.rows[0]) != []
    # Next run delivers and commits.
    pt.apply_receipt(ledger, receipt, WHEN)
    assert pt.compute_delta(ledger.rows[0]) == []
    assert ledger.rows[0]["observed_through_utc"] == WHEN
    assert ledger.rows[0]["last_mentioned_run"] == 1


def test_a_receipt_skips_an_item_that_failed_to_refresh():
    rows = {"github/o/r#pr1": base_row(refresh_ok=False)}
    assert pt.build_receipt(["github/o/r#pr1"], rows, WHEN, 1) == {}


def test_a_missed_run_widens_the_delta_without_a_special_case():
    row = base_row(lgtm_count=2, comment_count=9, conflicted=True)
    kinds = {kind for kind, _ in pt.compute_delta(row)}
    assert {"conflicted", "lgtm", "comments"} <= kinds


# ------------------------------------------------------------------ rotation


def test_rotation_names_an_item_once_then_retires_it():
    row = base_row(mr_state="merged", lifecycle="terminal_pending")
    assert pt.apply_rotation(row, WHEN) == "retired"
    assert row["lifecycle"] == "retired"
    assert row["retired_at_utc"] == WHEN
    assert pt.apply_rotation(row, WHEN) is None


def test_a_terminal_item_enters_terminal_pending_from_active():
    row = base_row(mr_state="merged")
    assert pt.apply_rotation(row, WHEN) == "terminal_pending"
    assert row["terminal_observed_utc"] == WHEN


def test_a_retired_item_seen_open_again_is_revived_not_recreated():
    row = base_row(lifecycle="retired", retired_at_utc=WHEN, mr_state="opened")
    assert pt.apply_rotation(row, "2026-08-13T09:00:00Z") == "reopened"
    assert row["lifecycle"] == "active"
    assert row["reopen_count"] == 1
    assert row["retired_at_utc"] is None


def test_terminal_is_decided_gitcode_first():
    """Our GitHub PRs close for reasons unrelated to whether the change landed."""
    assert pt.is_terminal(base_row(gh_state="closed", mr_iid=4717, mr_state="opened")) is False
    assert pt.is_terminal(base_row(gh_state="open", mr_state="merged")) is True
    assert pt.is_terminal(base_row(gh_state="closed")) is True  # no MR known


def test_absence_is_never_terminal():
    assert pt.is_terminal(base_row(gone=True, gh_state="open")) is False


def test_resurfacing_counts_runs_not_days():
    row = base_row(ci_verdict="fail", last_mentioned_run=3, reported_ci_verdict="fail")
    assert pt.should_resurface(row, run_index=10, every=7) is True
    assert pt.should_resurface(row, run_index=9, every=7) is False
    assert pt.should_resurface(base_row(last_mentioned_run=3), 99, 7) is False


# -------------------------------------------------------------- CI classifier


SIGNATURES = [
    {
        "name": "example.com ResourceWarning",
        "all_of": ["PytestUnraisableExceptionWarning", "ResourceWarning", "example.com"],
    }
]


def test_the_known_flake_matches_on_signature_not_on_test_name():
    failing = [
        {
            "testId": "tests/test_totally_unrelated.py::test_a",
            "longrepr": "PytestUnraisableExceptionWarning: ResourceWarning: unclosed "
            "socket ... https://example.com",
        }
    ]
    hint, matched = pt.classify_ci_failure(failing, SIGNATURES)
    assert hint == "matches_known_flake"
    assert matched == ["example.com ResourceWarning"]


def test_one_unmatched_failure_makes_the_whole_run_unrelated():
    failing = [
        {"longrepr": "PytestUnraisableExceptionWarning ResourceWarning example.com"},
        {"longrepr": "AssertionError: assert 1 == 2"},
    ]
    hint, _ = pt.classify_ci_failure(failing, SIGNATURES)
    assert hint == "unrelated_to_known_flake"


def test_no_report_is_unclassified_never_a_flake():
    assert pt.classify_ci_failure([], SIGNATURES) == ("unclassified", [])
    assert pt.parse_pytest_html("<html>nothing here</html>") == []


def test_the_shipped_signature_file_parses():
    signatures, notes = pt.load_flake_signatures(None)
    assert signatures and all("all_of" in entry for entry in signatures)
    assert notes == [], "the shipped file has nothing to complain about"


def test_a_named_signature_file_that_is_not_there_stops_the_run(tmp_path):
    """The defect: an explicitly named input that was never read, silently.

    Losing the signatures does not look like anything. Every failing build becomes
    `unclassified`, which is a real verdict meaning "matches nothing recorded", so
    the report is identical whether the signatures were consulted and missed or
    never loaded. Nothing names a path by accident, so a named path that is absent
    is a caller error rather than a configuration.
    """
    with pytest.raises(SystemExit) as refusal:
        pt.load_flake_signatures(tmp_path / "not-here.json")
    message = str(refusal.value)
    assert "does not exist" in message
    assert "matching nothing recorded" in message, "it says what the silence looks like"


def test_a_signature_file_that_exists_and_cannot_be_parsed_stops_the_run(tmp_path):
    """Absent can be a choice; malformed never is -- the rule already used here.

    Checked through the default as well as through the flag, because a file that
    is there and broken is a broken file whoever named it.
    """
    broken = tmp_path / "signatures.json"
    broken.write_text("{not json at all", encoding="utf-8")
    with pytest.raises(SystemExit) as refusal:
        pt.load_flake_signatures(broken)
    assert "cannot be" in str(refusal.value)

    shaped_wrong = tmp_path / "shaped-wrong.json"
    shaped_wrong.write_text('{"flakes": []}', encoding="utf-8")
    with pytest.raises(SystemExit) as refusal:
        pt.load_flake_signatures(shaped_wrong)
    assert "not a list" in str(refusal.value)


def test_a_file_that_parses_and_matches_nothing_is_reported_rather_than_dropped(tmp_path):
    """The same failure one level down: entries that can never fire.

    A signature with no `all_of` is matched against nothing, so a file whose
    entries have lost that key parses perfectly and classifies exactly as little
    as an absent one. It is not fatal -- the file is readable and an empty
    signature set is a legitimate thing to configure -- but it cannot be silent.
    """
    thin = tmp_path / "signatures.json"
    thin.write_text(
        json.dumps({"signatures": [{"name": "no needles"}, {"all_of": ["real"]}]}),
        encoding="utf-8",
    )
    signatures, notes = pt.load_flake_signatures(thin)
    assert [entry["all_of"] for entry in signatures] == [["real"]]
    assert any("can never match anything" in note for note in notes)

    empty = tmp_path / "empty.json"
    empty.write_text('{"signatures": []}', encoding="utf-8")
    signatures, notes = pt.load_flake_signatures(empty)
    assert signatures == [], "an explicitly empty set is allowed"
    assert any("no usable signature" in note for note in notes), "and still stated"


def test_a_report_says_on_stderr_that_it_classified_against_nothing(
    tmp_path, monkeypatch, capsys
):
    """The note has to reach the run, not just the loader.

    A signature set that cannot classify anything changes what every CI verdict in
    the report is able to say, so it travels with the run's other notes rather
    than being known only inside the function that found it.
    """
    monkeypatch.setenv("GITHUB_TOKEN", "not-a-real-token")
    empty = tmp_path / "signatures.json"
    empty.write_text('{"signatures": []}', encoding="utf-8")
    store = tmp_path / "C0BPLSPHHDZ.jsonl"
    assert track(store, channel="C0BPLSPHHDZ") == 0
    capsys.readouterr()
    assert pt.main(report_against(store, "--flake-signatures", str(empty))) == 0
    assert "no usable signature" in capsys.readouterr().err


# ------------------------------------------------------------------ rendering


def header_texts(text):
    """The mrkdwn text of the report's two opening context blocks.

    The header is always the first ```blockkit fence in a rendered report --
    `render_report_header` runs before the carousel is ever appended -- so the
    first fence in the text is always the header's, never the carousel's.
    """
    match = re.search(r"```blockkit\n(.*?)\n```", text, re.S)
    assert match, "no ```blockkit fence in the text"
    payload = json.loads(match.group(1))
    assert [block["type"] for block in payload["blocks"]] == ["context", "context"]
    return [block["elements"][0]["text"] for block in payload["blocks"]]


def context(**overrides):
    base = dict(
        state_file=Path("/srv/state/skills/pr-tracker/C0BPLSPHHDZ.jsonl"),
        row_count=12,
        tracked=12,
        since=pt.parse_utc("2026-08-12T08:00:00Z"),
        generated=pt.parse_utc("2026-08-12T12:00:00Z"),
        run_id="manual-1",
        channel="C0BPLSPHHDZ",
        repo_filter=None,
        full=False,
        warnings=[],
        coverage=[],
        store_created=False,
    )
    base.update(overrides)
    return pt.ReportContext(**base)


def test_the_report_names_the_store_without_publishing_its_path():
    """The only guard against the two prompts naming different stores.

    It has to identify the store and it is posted to a channel, so it names the
    store rather than locating it. A path is input, supplied by the prompt; it is
    not something a reader of the report can act on.
    """
    text = pt.render_report(context(), [], [], [], [], None, [])
    assert "Store: C0BPLSPHHDZ.jsonl (12 rows)" in text
    assert "/srv/state" not in text, "the store path is input, never output"
    assert "Registration: link trigger only" in text
    assert "12 tracked" in text


def test_the_first_context_block_carries_no_provenance():
    """The brief answers "what happened", and nothing else.

    Which store was read and how an item gets into it are both true and both
    useless to a skimmer, and they used to be the two longest bits of the
    line. They are in the thread, where a reader diagnosing a wrong report
    already is.
    """
    when, _what = header_texts(pt.render_report(context(), [], [], [], [], None, []))
    assert when == ":clock3: 2026-08-12 12:00 · 12 tracked (since 2026-08-12)"
    assert "store" not in when and "registration" not in when


def test_a_repo_filter_stays_on_the_first_context_block():
    """It changes what is being counted rather than saying where the count came from."""
    when, _what = header_texts(
        pt.render_report(context(repo_filter="o/r"), [], [], [], [], None, [])
    )
    assert when == ":clock3: 2026-08-12 12:00 · 12 tracked · repo: o/r (since 2026-08-12)"


def test_no_rendered_report_carries_the_store_path():
    for ctx in (context(), context(row_count=0, tracked=0, store_created=True)):
        text = pt.render_report(ctx, [], [], [], [], None, [])
        assert "/srv" not in text
        assert "C0BPLSPHHDZ.jsonl" in text


def test_nothing_changed_still_posts_a_line():
    _when, what = header_texts(pt.render_report(context(), [], [], [], [], None, []))
    assert what == ":arrows_counterclockwise: No changes"


def test_an_empty_store_is_never_silent_about_being_empty():
    text = pt.render_report(
        context(row_count=0, tracked=0, store_created=True), [], [], [], [], None, []
    )
    assert "did not exist and was created by this run" in text
    assert "(0 rows)" in text


def test_the_coverage_line_warns_about_the_downtime_gap_without_a_version():
    """The warning is the point; the roadmap it came from is nobody else's."""
    text = pt.render_report(context(), [], [], [], [], None, [])
    coverage = text.split("*Coverage and gaps*", 1)[1]
    assert "while it was down" in coverage
    assert "posted again" in coverage
    assert "a quiet week" in text.lower()
    assert not re.search(r"\bv[12]\b", coverage)


TABLE_HEADER = "| Item | Author | What changed | Status | Title | See also |"


def cells(row_line):
    """The cells of one rendered row.

    Split on ``" | "`` rather than on the bare pipe: the Item cell holds a
    ``<url|label>`` link whose own pipe carries no spaces, and splitting on that
    shifts every column after it.
    """
    body = row_line.strip().removeprefix("|").removesuffix("|")
    return [cell.strip() for cell in body.split(" | ")]


def test_item_sections_render_as_a_table_at_any_size():
    """One row is a table too.

    An earlier threshold rendered fewer than four changes as bullets. Most real
    reports are below it, so the bullet form was what a reader actually saw --
    and it put the deltas last, after a title long enough to push them off the
    line.
    """
    for count in (1, 3, 9):
        rows = [
            (base_row(key=f"github/o/r#pr{n}", number=n, repo="o/r", url=f"u{n}",
                      title_source=f"t{n}", conflicted=True), [("conflicted", "now conflicted")])
            for n in range(1, count + 1)
        ]
        text = pt.render_report(context(), [], rows, [], [], None, [])
        assert TABLE_HEADER in text, count
        assert "\n- <u1|" not in text, f"{count} rows still rendered a bullet"


def test_the_delta_column_precedes_the_title():
    """What changed is why the row is here, so it is read before the title."""
    rows = [(base_row(url="u1", number=1, repo="o/r", title_source="t1",
                      conflicted=True), [("conflicted", "now conflicted")])]
    header = pt.render_change_table(rows).splitlines()[0]
    assert header.index("What changed") < header.index("Title")


def test_the_author_sits_beside_the_item_it_belongs_to():
    """Item and author are "whose is this"; the columns after them are the news."""
    rows = [(base_row(url="u1", number=1, repo="o/r", title_source="t1",
                      author_login="chaimaerachdi"), [])]
    table = pt.render_change_table(rows)
    header, _delimiter, body = table.splitlines()
    assert header == TABLE_HEADER
    assert header.index("Item") < header.index("Author") < header.index("What changed")
    assert cells(body)[1] == "chaimaerachdi"


def test_an_app_account_keeps_the_suffix_that_says_it_is_one():
    """The login as the tracker gives it, so a bot is legible and unambiguous.

    Stripping ``[bot]`` produces a string that is a different, possibly real,
    account, and loses the one thing the column is being read for on those rows.
    It was measured before it was kept: on a store half of whose rows are an
    app's, the suffix is about two percent of the table budget.
    """
    rows = [(base_row(url="u1", number=1, repo="o/r", title_source="t1",
                      author_login="openjiuwen-sync-bot[bot]"), [])]
    assert "| openjiuwen-sync-bot[bot] |" in pt.render_change_table(rows)


def test_an_item_with_no_author_cannot_read_as_one():
    """A link that is neither PR nor issue has no author, and says so.

    The em dash is what every other empty cell prints and is not a login any
    tracker can issue, so the absence cannot be mistaken for a name.
    """
    rows = [(base_row(key="other/abc", kind="other", url="https://example.test/x",
                      number=None, repo="", title_source=None,
                      author_login=None), [])]
    body = pt.render_change_table(rows).splitlines()[2]
    assert cells(body)[1] == "—"


def test_the_roster_carries_the_author_column_too():
    """Every section rendering rows renders the same six columns."""
    roster = [base_row(key="github/o/r#pr9", number=9, repo="o/r", url="u9",
                       title_source="t9", author_login="renanalmd")]
    text = pt.render_report(context(full=True), [], [], [], [], roster, [])
    assert text.count(TABLE_HEADER) == 1
    assert "| renanalmd |" in text


def test_the_item_cell_names_one_tracker_and_not_the_paired_code():
    """The link has one destination, so the cell names one item.

    The paired identifier was a lookup key for a tracker the reader is not in,
    carried on half the rows and unchanged from run to run.
    """
    row = base_row(url="u1", number=1, repo="o/r", title_source="t1",
                   tracker="github", mr_iid=4683, author_login="renanalmd")
    table = pt.render_change_table([(row, [])])
    assert "MR !" not in table and "4683" not in table
    assert cells(table.splitlines()[2])[0] == "<u1|r #1>"


def test_a_landed_change_still_says_where_it_landed():
    """What the pairing meant is in Status and the delta, not in the Item cell.

    This is why dropping the code loses nothing a reader acts on: the row that
    lands through the other tracker still announces it.
    """
    row = base_row(url="u1", number=1, repo="o/r", title_source="t1",
                   mr_iid=4683, mr_state="merged", reported_status="approved")
    assert pt.derive_status(row) == "landed"
    assert ("landed", "landed on GitCode") in pt.compute_delta(row)


def test_table_cells_use_the_link_form_slack_will_render():
    """A table cell is linkified only for ``<url|label>``.

    Markdown link syntax reaches the channel as literal text: the label, the
    brackets and the raw URL all visible in one cell.
    """
    rows = [(base_row(url="https://example.test/pr/1", number=1, repo="o/r",
                      title_source="t1"), [])]
    table = pt.render_change_table(rows)
    assert "<https://example.test/pr/1|" in table
    assert "](https://example.test/pr/1)" not in table


def test_every_item_section_is_a_table():
    row = base_row(url="u1", number=1, repo="o/r", title_source="t1")
    for position in range(4):
        args = [[], [], [], []]
        args[position] = [(row, [])] if position == 1 else [row]
        text = pt.render_report(context(), args[0], args[1], args[2], args[3], None, [])
        assert text.count(TABLE_HEADER) == 1, position


def test_merge_state_status_is_a_footnote_and_never_a_row():
    """Named as a condition, not as this deployment's merge process.

    The footnote used to say the gate was "a `/approve` on GitCode", which is
    true of the repositories tracked here and of nothing else. What a reader
    anywhere needs is why the field is constant, not whose convention made it so.
    """
    text = pt.render_report(context(), [], [], [], [], None, [])
    assert text.count("BLOCKED") == 1
    assert "where a repository's merge gate is not GitHub's own" in text
    assert "/approve" not in text


# ------------------------------------------------------- the brief and thread

MARKER = "<!-- jiuwenswarm:slack-thread-details -->"


def messages(text):
    """The delivered messages, the way a host that honours every marker splits them.

    Each marker is a boundary. Empty pieces are filtered here as well as by the
    report, so that this helper still describes a host honouring every marker
    literally rather than assuming the report never writes one it should not.
    The first element is the channel message and the rest are its replies.
    """
    return [piece.strip() for piece in text.split(MARKER) if piece.strip()]


def split_report(text):
    """The root message and everything threaded under it, joined back together.

    The reading a host that splits on the first marker only still gets, and the
    one most of these tests want: they are about which side of the brief a
    section falls on, not about which reply it lands in.
    """
    root, body = text.split(MARKER, 1)
    return root.strip(), body.replace(MARKER, "").strip()


def populated_report(**ctx):
    rows = [
        base_row(key=f"github/o/r#pr{n}", number=n, repo="o/r", url=f"u{n}",
                 title_source=f"t{n}")
        for n in range(1, 6)
    ]
    return pt.render_report(
        context(**ctx),
        [rows[0]],
        [(rows[1], [("conflicted", "now conflicted")]), (rows[2], [("ci", "CI failed")])],
        [rows[3]],
        [rows[4]],
        None,
        [],
    )


def test_no_table_is_left_in_the_root_message():
    """The channel gets the brief; every table is a reply to it.

    This is the same split *Detail* has always used, moved up rather than
    duplicated -- so the assertion is on the marker's position and not on a
    second mechanism existing.
    """
    root, body = split_report(populated_report())
    assert "|" not in root, "a table reached the channel instead of the thread"
    for section in ("*Newly tracked*", "*Changed*", "*Still waiting*",
                    "*Closed and landed*", "*Detail*", "*Coverage and gaps*",
                    "*Source and registration*"):
        assert section in body, section
        assert section not in root, section


def test_the_brief_tallies_the_sections_in_section_order():
    """Counts, so the second context block reads top to bottom against the
    tables in the thread."""
    root, _ = split_report(populated_report())
    _when, what = header_texts(root)
    assert what == ":arrows_counterclockwise: 1 newly tracked · 2 changed · 1 still waiting · 1 closed and landed"


def test_an_empty_section_is_left_out_of_the_tally():
    rows = [base_row(key="github/o/r#pr1", number=1, repo="o/r", url="u1", title_source="t1")]
    root, _ = split_report(pt.render_report(context(), rows, [], [], [], None, []))
    _when, what = header_texts(root)
    assert what == ":arrows_counterclockwise: 1 newly tracked"


def test_the_quiet_run_keeps_its_no_changes_reading_instead_of_a_tally():
    """The one case that already read as a TL;DR; the tally is its busy twin."""
    root, body = split_report(pt.render_report(context(), [], [], [], [], None, []))
    when, what = header_texts(root)
    assert what == ":arrows_counterclockwise: No changes"
    assert "12 tracked" in when and "·" in when, "the first context block is untouched"
    assert "*Detail*" in body


def test_a_full_roster_is_tallied_and_delivered_in_the_thread():
    roster = [
        base_row(key=f"github/o/r#pr{n}", number=n, repo="o/r", url=f"u{n}", title_source=f"t{n}")
        for n in range(1, 4)
    ]
    root, body = split_report(
        pt.render_report(context(full=True), [], [], [], [], roster, [])
    )
    _when, what = header_texts(root)
    assert what == ":arrows_counterclockwise: 3 on the roster"
    assert "*Roster*" in body and "*Roster*" not in root


def test_a_full_run_over_an_empty_store_still_says_so():
    """--full used to suppress the "no changes" reading and then render no roster."""
    root, _ = split_report(
        pt.render_report(context(row_count=0, tracked=0, full=True), [], [], [], [], [], [])
    )
    when, what = header_texts(root)
    assert "0 tracked" in when
    assert what == ":arrows_counterclockwise: No changes"


def test_neither_side_of_the_split_is_ever_empty():
    """An empty side makes the connector fall back to one flat message."""
    for text in (populated_report(), pt.render_report(context(), [], [], [], [], None, [])):
        root, body = split_report(text)
        assert root and body


# --------------------------------------------- the per-repository carousel


def repo_row(repo, **overrides):
    overrides.setdefault("number", 1)
    return base_row(key=f"github/{repo}#pr{overrides['number']}", repo=repo, **overrides)


def test_compute_repository_summaries_at_one_repository():
    """One tracked repository: every count folds into its single card."""
    rows = [repo_row("o/r", number=n) for n in (1, 2, 3)]
    newly = [rows[0]]
    changed = [(rows[1], [("conflicted", "now conflicted")])]
    terminal = [repo_row("o/r", number=4, lifecycle="terminal_pending", merged_at=WHEN)]
    summaries = pt.compute_repository_summaries(
        rows + terminal, newly, changed, terminal, pt.Repositories(), None
    )
    assert summaries == [
        {"slug": "o/r", "tracked": 3, "new": 1, "changed": 1, "merged": 1, "closed": 0}
    ]


def test_compute_repository_summaries_at_several_repositories():
    """Two repositories: a card's counts come only from its own rows.

    Behaves the same way whether the store tracks one repository or several --
    nothing here is written assuming a particular count of them.
    """
    rows_a = [repo_row("o/a", number=n) for n in (1, 2)]
    rows_b = [repo_row("o/b", number=n) for n in (1, 2, 3)]
    closed_b = repo_row("o/b", number=9, lifecycle="terminal_pending", gh_state="closed")
    summaries = pt.compute_repository_summaries(
        rows_a + rows_b + [closed_b],
        [rows_a[0]],
        [(rows_b[0], [("ci", "CI failed")])],
        [closed_b],
        pt.Repositories(),
        None,
    )
    by_slug = {summary["slug"]: summary for summary in summaries}
    assert set(by_slug) == {"o/a", "o/b"}
    assert by_slug["o/a"] == {
        "slug": "o/a", "tracked": 2, "new": 1, "changed": 0, "merged": 0, "closed": 0
    }
    assert by_slug["o/b"] == {
        "slug": "o/b", "tracked": 3, "new": 0, "changed": 1, "merged": 0, "closed": 1
    }


def test_compute_repository_summaries_includes_a_configured_repository_with_nothing_yet():
    """Configured before anything registers -- the same rule `known_repositories` uses."""
    repositories = pt.Repositories.from_config({"o/new": {}}, [])
    summaries = pt.compute_repository_summaries([], [], [], [], repositories, None)
    assert summaries == [
        {"slug": "o/new", "tracked": 0, "new": 0, "changed": 0, "merged": 0, "closed": 0}
    ]


def test_compute_repository_summaries_uses_the_configured_capitalisation():
    repositories = pt.Repositories.from_config({"OpenJiuwen-AI/JiuwenSwarm": {}}, [])
    rows = [repo_row("openjiuwen-ai/jiuwenswarm", number=1)]
    summaries = pt.compute_repository_summaries(rows, [], [], [], repositories, None)
    assert summaries[0]["slug"] == "OpenJiuwen-AI/JiuwenSwarm"


def test_compute_repository_summaries_respects_the_repo_filter():
    """A card for a repository this run never looked at reads as a quiet one --
    the same failure `resolve_repo_filter` exists to head off elsewhere -- so
    `--repo` narrows the card set exactly as it narrows the rest of the run."""
    rows = [repo_row("o/a", number=1), repo_row("o/b", number=1)]
    summaries = pt.compute_repository_summaries(rows, [], [], [], pt.Repositories(), "o/a")
    assert [summary["slug"] for summary in summaries] == ["o/a"]


def test_compute_repository_summaries_an_unmatched_filter_yields_no_cards():
    rows = [repo_row("o/a", number=1)]
    summaries = pt.compute_repository_summaries(
        rows, [], [], [], pt.Repositories(), "o/does-not-exist"
    )
    assert summaries == []


def carousel_fence(text):
    """The ```blockkit fence in *text*, parsed back to JSON."""
    match = re.search(r"```blockkit\n(.*?)\n```", text, re.S)
    assert match, "no ```blockkit fence in the text"
    return json.loads(match.group(1))


def test_render_repository_carousel_is_none_with_nothing_to_show():
    assert pt.render_repository_carousel([]) is None


def test_render_repository_carousel_emits_valid_block_kit():
    """The documented shape: a `blocks` array holding one `carousel` of `card`s."""
    summaries = [
        {"slug": "o/a", "tracked": 12, "new": 1, "changed": 3, "merged": 2, "closed": 0},
    ]
    payload = carousel_fence(pt.render_repository_carousel(summaries))
    assert list(payload.keys()) == ["blocks"]
    block = payload["blocks"][0]
    assert block["type"] == "carousel"
    assert 1 <= len(block["elements"]) <= 10
    card = block["elements"][0]
    assert card["type"] == "card"
    # At least one of hero_image/title/actions/body is required; this shape
    # carries exactly title, body and the icon, and nothing that makes it
    # interactive.
    assert set(card) == {"type", "title", "body", "slack_icon"}
    assert card["title"]["type"] == "mrkdwn"
    assert card["body"]["type"] == "mrkdwn"


def test_render_repository_carousel_every_card_carries_the_same_icon():
    """Every repository card gets the same `slack_icon` -- it marks the card
    as *a repository card*, it does not distinguish one repository from
    another. `code` was chosen over `cube`, `folder` and `archive` as the
    most literal, least ambiguous reading of "source repository" at card
    size."""
    summaries = [
        {"slug": f"o/repo{n}", "tracked": n, "new": 0, "changed": 0, "merged": 0,
         "closed": 0}
        for n in range(4)
    ]
    cards = carousel_fence(pt.render_repository_carousel(summaries))["blocks"][0]["elements"]
    assert len(cards) == 4
    for card in cards:
        assert card["slack_icon"] == {"type": "icon", "name": "code"}
        assert "icon" not in card, "slack_icon and icon are mutually exclusive"


def test_render_repository_carousel_no_card_carries_a_button():
    """Cards are display-only: an interactive element posts back to the app,
    and this deployment's buttons now carry real permission approvals."""
    summaries = [
        {"slug": "o/a", "tracked": 1, "new": 0, "changed": 0, "merged": 0, "closed": 0}
    ]
    for card in carousel_fence(pt.render_repository_carousel(summaries))["blocks"][0]["elements"]:
        assert "actions" not in card


def test_render_repository_carousel_title_links_the_repository():
    """The link lives in `title`, which renders `<url|label>`, rather than on a button."""
    summaries = [
        {"slug": "openJiuwen-ai/jiuwenswarm", "tracked": 1, "new": 0, "changed": 0,
         "merged": 0, "closed": 0}
    ]
    card = carousel_fence(pt.render_repository_carousel(summaries))["blocks"][0]["elements"][0]
    assert card["title"]["text"] == (
        "<https://github.com/openJiuwen-ai/jiuwenswarm|openJiuwen-ai/jiuwenswarm>"
    )


def test_render_repository_carousel_drops_zero_categories_and_states_a_quiet_one():
    quiet = {"slug": "o/a", "tracked": 5, "new": 0, "changed": 0, "merged": 0, "closed": 0}
    busy = {"slug": "o/b", "tracked": 5, "new": 2, "changed": 0, "merged": 1, "closed": 0}
    cards = carousel_fence(pt.render_repository_carousel([quiet, busy]))["blocks"][0]["elements"]
    bodies = {card["title"]["text"]: card["body"]["text"] for card in cards}
    assert bodies["<https://github.com/o/a|o/a>"] == "5 tracked · no changes"
    assert bodies["<https://github.com/o/b|o/b>"] == "5 tracked · 2 new · 1 merged"


def test_render_repository_carousel_body_fits_the_limit_at_realistic_counts():
    """Realistic, not pathological -- hundreds tracked, dozens moved -- and it
    fits with room to spare, which is why no elaborate drop-priority scheme is
    needed for it: see `_fit_card_body` for the one that is."""
    summaries = [
        {"slug": "openJiuwen-ai/jiuwenswarm", "tracked": 480, "new": 9, "changed": 12,
         "merged": 240, "closed": 60},
        {"slug": "openJiuwen-ai/agent-core", "tracked": 1200, "new": 45, "changed": 88,
         "merged": 900, "closed": 300},
    ]
    for card in carousel_fence(pt.render_repository_carousel(summaries))["blocks"][0]["elements"]:
        assert len(card["body"]["text"]) <= pt.CARD_BODY_CHARACTERS
        assert len(card["title"]["text"]) <= 150


def test_render_repository_carousel_caps_at_ten_keeping_the_busiest():
    """Block Kit's own ceiling on a carousel. Past it, the repositories with
    something to report this run outrank the quiet ones; survivors still
    display in the store's own alphabetical order."""
    summaries = sorted(
        [
            {"slug": f"o/quiet{n}", "tracked": 1, "new": 0, "changed": 0, "merged": 0,
             "closed": 0}
            for n in range(8)
        ]
        + [
            {"slug": f"o/busy{n}", "tracked": 1, "new": 1, "changed": 0, "merged": 0,
             "closed": 0}
            for n in range(4)
        ],
        key=lambda summary: summary["slug"],
    )
    cards = carousel_fence(pt.render_repository_carousel(summaries))["blocks"][0]["elements"]
    assert len(cards) == 10
    kept = [card["title"]["text"] for card in cards]
    for n in range(4):
        assert any(f"o/busy{n}" in title for title in kept)
    assert not any("o/quiet6" in title or "o/quiet7" in title for title in kept)
    assert kept == sorted(kept), "the cap changes who survives, not the display order"


def test_fit_card_body_returns_the_join_when_it_already_fits():
    assert pt._fit_card_body(["12 tracked", "3 new"]) == "12 tracked · 3 new"


def test_fit_card_body_drops_the_least_important_parts_first():
    result = pt._fit_card_body(["1 tracked", "22 new", "33 changed"], limit=25)
    assert result == "1 tracked · 22 new"


def test_fit_card_body_truncates_a_single_part_too_long_to_drop():
    result = pt._fit_card_body(["x" * 300], limit=50)
    assert len(result) == 50
    assert result.endswith("…")


# --------------------------------------------------- the two-block header


def test_render_report_header_at_realistic_counts():
    """The exact shape asked for: when this ran, then what it found."""
    ctx = context(
        tracked=66,
        since=pt.parse_utc("2026-08-13T00:00:00Z"),
        generated=pt.parse_utc("2026-08-19T14:32:00Z"),
    )
    payload = carousel_fence(
        pt.render_report_header(ctx, [1, 2, 3], [1, 2], [], [], None)
    )
    when, what = (block["elements"][0]["text"] for block in payload["blocks"])
    assert when == ":clock3: 2026-08-19 14:32 · 66 tracked (since 2026-08-13)"
    assert what == ":arrows_counterclockwise: 3 newly tracked · 2 changed"


def test_render_report_header_at_zero_reads_cleanly():
    """No new items and no changes is the common quiet day, and it is named
    outright rather than left to join zero parts into an empty string."""
    payload = carousel_fence(pt.render_report_header(context(), [], [], [], [], None))
    when, what = (block["elements"][0]["text"] for block in payload["blocks"])
    assert what == ":arrows_counterclockwise: No changes"
    assert when, "the first block is never empty, quiet run or not"


def test_the_run_timestamp_carries_a_time_and_since_carries_a_date_only():
    """The two timestamp rules this header exists to fix: both halves of when
    this ran, only the date of how far back it reaches."""
    ctx = context(
        since=pt.parse_utc("2026-08-13T09:41:00Z"),
        generated=pt.parse_utc("2026-08-19T14:32:07Z"),
    )
    payload = carousel_fence(pt.render_report_header(ctx, [], [], [], [], None))
    when = payload["blocks"][0]["elements"][0]["text"]
    assert "2026-08-19" in when and "14:32" in when, "the run's own date and time"
    assert "2026-08-13" in when, "since, as a date"
    assert "09:41" not in when, "since carries no clock time"


def test_both_root_posts_produce_the_same_header_structure():
    """The deltas report and the --full roster share `render_report_header`,
    so both produce the same two-block, one-element-per-block shape."""
    deltas = carousel_fence(pt.render_report_header(context(full=False), [], [], [], [], None))
    roster = carousel_fence(pt.render_report_header(context(full=True), [], [], [], [], []))
    for payload in (deltas, roster):
        assert [block["type"] for block in payload["blocks"]] == ["context", "context"]
        assert [len(block["elements"]) for block in payload["blocks"]] == [1, 1]


def test_the_context_element_budget_is_never_approached():
    """One text element per block carries any number of facts, composed with
    ``" · "`` inside the string -- never one element per fact, which is what
    would spend a `context` block's ten-element ceiling on separators."""
    fence = pt.render_report_header(
        context(full=True),
        list(range(9)), list(range(8)), list(range(7)), list(range(6)),
        list(range(500)),
    )
    payload = carousel_fence(fence)
    for block in payload["blocks"]:
        assert len(block["elements"]) == 1
        assert len(block["elements"]) <= 10


def carousel_context(**overrides):
    overrides.setdefault(
        "repository_summaries",
        [{"slug": "o/r", "tracked": 5, "new": 1, "changed": 0, "merged": 0, "closed": 0}],
    )
    return context(**overrides)


def test_render_report_adds_the_carousel_without_touching_the_existing_header():
    """An addition to the brief, not a replacement for its two context blocks.

    The existing header reads exactly as it did before this landed -- the
    carousel is new content below it, never a rewrite of what was there.
    """
    root, _ = split_report(pt.render_report(carousel_context(), [], [], [], [], None, []))
    when, what = header_texts(root)
    assert when == ":clock3: 2026-08-12 12:00 · 12 tracked (since 2026-08-12)"
    assert what == ":arrows_counterclockwise: No changes"
    header_index = root.index("```blockkit")
    carousel_index = root.index('"type": "carousel"')
    assert header_index < carousel_index, "the header reads first, the carousel follows it"


def test_render_report_omits_the_carousel_with_nothing_to_summarise():
    """The header fence is always there; only the carousel is conditional."""
    root, _ = split_report(pt.render_report(context(), [], [], [], [], None, []))
    assert root.count("```blockkit") == 1, "the header fence, and no carousel fence"
    assert '"type": "carousel"' not in root


def test_render_report_keeps_the_carousel_in_the_root_message():
    """The carousel belongs to the channel post, not to a threaded reply."""
    root, body = split_report(pt.render_report(carousel_context(), [], [], [], [], None, []))
    assert '"type": "carousel"' in root
    assert '"type": "carousel"' not in body


def test_the_deltas_report_and_the_full_roster_share_one_carousel_construction():
    """Both root posts get the carousel, built once and used from both.

    `render_report` never branches on `context.full` to decide whether the
    carousel is built -- it always renders `context.repository_summaries` the
    same way -- so a deltas run and a `--full` roster run over the same
    summaries produce byte-identical fences. The header fence is excluded from
    this comparison on purpose: `context.full` can change what the header's
    second block says (a roster count may join the tally), so only the
    carousel fence is expected to match byte for byte.
    """
    deltas = pt.render_report(carousel_context(full=False), [], [], [], [], None, [])
    roster = pt.render_report(carousel_context(full=True), [], [], [], [], [], [])
    fences = re.compile(r"```blockkit\n.*?\n```", re.S)
    deltas_fence = next(f for f in fences.findall(deltas) if '"type": "carousel"' in f)
    roster_fence = next(f for f in fences.findall(roster) if '"type": "carousel"' in f)
    assert deltas_fence == roster_fence


# ------------------------------------------------- one message per boundary


def roster_report(**ctx):
    """A ``--full`` run: delta tables and a roster, the widest shape rendered."""
    rows = [
        base_row(key=f"github/o/r#pr{n}", number=n, repo="o/r", url=f"u{n}",
                 title_source=f"t{n}")
        for n in range(1, 9)
    ]
    return pt.render_report(
        context(full=True, **ctx),
        [rows[0]],
        [(rows[1], [("conflicted", "now conflicted")]), (rows[2], [("ci", "CI failed")])],
        [rows[3]],
        [rows[4]],
        rows[5:],
        [],
    )


def test_a_busy_run_is_a_brief_then_the_tables_then_the_prose():
    """Three messages, in the order the reader wants them.

    The tables are what the thread was opened for, so they arrive first; the
    prose that explains them is reference and follows. It is also a Block Kit
    budget of its own, so prose that could never render as a table spends none
    of the tables'.
    """
    brief, tables, prose = messages(populated_report())
    assert brief.startswith("```blockkit")
    assert tables.startswith("*Newly tracked*") and "|" in tables
    assert "|" not in prose
    assert prose.splitlines()[0] == "*Detail*"
    for section in ("*Detail*", "*Coverage and gaps*", "*Source and registration*"):
        assert section in prose, section
        assert section not in tables, section


def test_the_prose_sections_are_in_their_stated_order():
    """What the rows mean, then what is missing from them, then where they came from."""
    prose = messages(populated_report())[-1]
    assert (
        prose.index("*Detail*")
        < prose.index("*Coverage and gaps*")
        < prose.index("*Source and registration*")
    )


def test_a_quiet_run_delivers_two_messages_and_no_empty_one():
    """No table section means nothing between the boundaries, and no blank reply."""
    brief, prose = messages(pt.render_report(context(), [], [], [], [], None, []))
    _when, what = header_texts(brief)
    assert what == ":arrows_counterclockwise: No changes"
    assert prose.startswith("*Detail*")


def test_the_report_is_correct_on_a_host_that_splits_once():
    """The degradation to design for: every section survives, in the same order.

    A host that strips every marker after the first delivers the brief and one
    reply. That reply is the tables, the roster and then the prose -- the same
    reading, two messages fewer -- so nothing is lost but the extra budgets.
    """
    root, body = split_report(roster_report())
    assert root.startswith("```blockkit")
    assert body.startswith("*Newly tracked*")
    assert (
        body.index("*Closed and landed*")
        < body.index("*Roster*")
        < body.index("*Detail*")
        < body.index("*Source and registration*")
    )


def test_a_full_run_delivers_the_roster_as_a_message_of_its_own():
    """Four messages: the brief, the deltas, the roster, the prose.

    The roster is the section whose length nobody chose -- it is as long as the
    roster is, grows with every registration and shrinks only when items retire
    -- so it is what reaches a Block Kit limit first. Sharing a message with the
    delta tables made the two ceilings one and a breach took both formattings
    down together. Its own boundary is its own budget.
    """
    brief, tables, roster, prose = messages(roster_report())
    assert brief.startswith("```blockkit")
    assert tables.startswith("*Newly tracked*")
    assert roster.startswith("*Roster*")
    assert prose.startswith("*Detail*")
    for section in ("*Newly tracked*", "*Changed*", "*Still waiting*",
                    "*Closed and landed*"):
        assert section in tables, section
        assert section not in roster, section
    assert "*Roster*" not in tables
    assert "|" in roster and "|" in tables and "|" not in prose


def test_the_roster_is_tallied_in_the_brief_it_is_no_longer_delivered_with():
    """Which message a section lands in is transport; the tally is reading order.

    Dropping the roster's count because the roster moved would have a --full run
    announce less than it delivers.
    """
    brief = messages(roster_report())[0]
    _when, what = header_texts(brief)
    assert what == (
        ":arrows_counterclockwise: 1 newly tracked · 2 changed · 1 still waiting · "
        "1 closed and landed · 3 on the roster"
    )


def test_a_run_with_no_roster_does_not_gain_an_empty_message():
    """A boundary is written only where a message follows it.

    Without --full there is nothing between the roster's boundary and the next,
    so no boundary is written there at all: a daily report stays at three
    messages and a quiet one at two. Relying on a host to drop the empty piece
    would make the report's correctness a property of the connector, and the
    report is the thing that knows which of its sections are empty.
    """
    assert populated_report().count(MARKER) == 2
    assert roster_report().count(MARKER) == 3

    assert len(messages(populated_report())) == 3
    assert len(messages(pt.render_report(context(), [], [], [], [], None, []))) == 2
    # --full over a store with nothing on the roster is the same case: the
    # section is omitted when empty, so the marker is what is left.
    assert len(
        messages(pt.render_report(context(full=True), [], [], [], [], [], []))
    ) == 2


# ------------------------------------------------------- paging the roster


def roster_of(count, title="a representative pull request title"):
    return [
        base_row(key=f"github/o/r#pr{n}", number=n, repo="o/r",
                 url=f"https://example.test/pr/{n}", title_source=title,
                 author_login="a-contributor")
        for n in range(count)
    ]


def roster_messages(rows):
    """The messages a --full run over *rows* delivers."""
    return messages(pt.render_report(context(full=True), [], [], [], [], rows, []))


def test_a_roster_that_fits_one_message_is_not_numbered():
    """A list of one page says so by not claiming to be part of anything.

    Numbering it would tell a reader a second message exists and send them
    looking for one.
    """
    assert len(pt.paginate_roster(roster_of(10))) == 1
    roster = roster_messages(roster_of(10))[1]
    assert roster.startswith("*Roster*")
    assert "(1/1)" not in roster


def test_a_long_roster_becomes_several_labelled_messages():
    """One page per message, each its own Block Kit budget, each numbered.

    The label is what makes a missing page visible: "2/3" arriving without "3/3"
    is a delivery that failed, and unlabelled pages would read as a shorter
    roster instead.
    """
    rows = roster_of(200)
    pages = pt.paginate_roster(rows)
    assert len(pages) > 1
    parts = roster_messages(rows)
    roster_parts = [p for p in parts if p.startswith("*Roster")]
    assert len(roster_parts) == len(pages)
    for index, part in enumerate(roster_parts, 1):
        assert part.startswith(f"*Roster ({index}/{len(pages)})*")
        assert part.count(TABLE_HEADER) == 1
    # Every row is delivered exactly once: paging splits, it does not sample.
    assert sum(len(page) for page in pages) == len(rows)
    assert [row for page in pages for row in page] == rows


def test_a_page_breaks_on_width_and_not_on_a_row_count():
    """The same row count pages differently, and the two caps bind separately.

    A fixed break would be wrong for the wide case or wasteful for the narrow
    one, which is why the rule accumulates width. The two limits are on
    different axes and both are real: narrow rows run out of rows first, wide
    rows run out of characters first, and neither sees the other coming.
    """
    narrow = pt.paginate_roster(roster_of(120, title="short"))
    wide = pt.paginate_roster(roster_of(120, title="w" * 60))
    assert len(narrow[0]) > len(wide[0]), "a wider row must fit fewer to a page"

    # Narrow rows reach the row cap with characters to spare.
    assert len(narrow[0]) == pt.ROSTER_PAGE_ROWS
    assert pt.table_characters(narrow[0]) < pt.ROSTER_PAGE_CHARACTERS

    # Wide rows reach the character budget while still short of the row cap.
    assert len(wide[0]) < pt.ROSTER_PAGE_ROWS
    assert pt.table_characters(wide[0]) <= pt.ROSTER_PAGE_CHARACTERS


def test_a_page_stays_inside_the_budget_the_host_counts():
    """The accumulator charges a row exactly what the renderer prints for it.

    Measuring an estimate beside a renderer that prints something else is how a
    page silently breaches; this pins the two together.
    """
    for rows in (roster_of(200), roster_of(200, title="w" * 60), roster_of(3)):
        for page in pt.paginate_roster(rows):
            assert pt.table_characters(page) <= pt.ROSTER_PAGE_CHARACTERS
            assert len(page) <= pt.ROSTER_PAGE_ROWS
            # The characters charged are the characters rendered, header row
            # included and link destinations excluded.
            rendered = pt.render_change_table([(row, []) for row in page])
            shown = 0
            for line in rendered.splitlines():
                if set(line.strip()) <= set("| -"):
                    continue  # the delimiter row, which carries no text
                for cell in cells(line):
                    inner = cell.split("|", 1)[-1].rstrip(">") if cell.startswith("<") else cell
                    shown += len(inner)
            assert shown == pt.table_characters(page)


def test_a_single_row_wider_than_a_page_still_gets_one():
    """It cannot be split, and a page that breaches beats a row that vanishes."""
    huge = base_row(key="github/o/r#pr1", number=1, repo="o/r", url="u1",
                    title_source="t", author_login="x")
    huge["closes"] = ["o/r#" + "9" * 4000]
    pages = pt.paginate_roster([huge])
    assert len(pages) == 1 and pages[0] == [huge]


def test_a_roster_too_long_to_page_is_stated_rather_than_listed():
    """Past a point, paging is mechanically fine and useless.

    The count is still given, so nothing is hidden; what is withheld is a list
    nobody could scan, and the way to get one back is named.
    """
    rows = roster_of(4000)
    assert len(pt.paginate_roster(rows)) > pt.ROSTER_MAX_PAGES
    parts = roster_messages(rows)
    roster_parts = [p for p in parts if p.startswith("*Roster")]
    assert len(roster_parts) == 1
    assert TABLE_HEADER not in roster_parts[0]
    assert "4000 items on the roster" in roster_parts[0]
    assert "--repo owner/name" in roster_parts[0]


def test_the_whole_report_shape_holds_at_every_roster_size():
    """Quiet 2, ordinary 3, --full one page 4, --full paged 3 + pages."""
    assert len(messages(pt.render_report(context(), [], [], [], [], None, []))) == 2
    assert len(messages(populated_report())) == 3

    single = roster_of(5)
    assert len(pt.paginate_roster(single)) == 1
    assert len(messages(pt.render_report(
        context(full=True), [], [(single[0], [("ci", "CI failed")])], [], [],
        single, []))) == 4

    many = roster_of(200)
    pages = pt.paginate_roster(many)
    assert len(pages) == 3
    assert len(messages(pt.render_report(
        context(full=True), [], [(many[0], [("ci", "CI failed")])], [], [],
        many, []))) == 3 + len(pages)


def test_paging_adds_a_marker_per_extra_page_and_none_without_a_roster():
    """The boundary count follows the pages, and an absent roster adds none."""
    assert populated_report().count(MARKER) == 2
    # A --full run with a roster and no deltas: the delta piece is empty and
    # writes no boundary, so the roster's and the prose's are the two left.
    assert pt.render_report(
        context(full=True), [], [], [], [], roster_of(5), []
    ).count(MARKER) == 2
    text = pt.render_report(context(full=True), [], [], [], [], roster_of(200), [])
    assert text.count(MARKER) == 2 + len(pt.paginate_roster(roster_of(200))) - 1


def test_a_report_with_no_tables_at_all_writes_one_boundary(tmp_path):
    """The run that produced three in a row: every table section empty.

    Correct as text and a description of a delivery nobody wants -- two blank
    replies on any host that honours a boundary literally. The brief and the
    prose are the only two pieces there are, so there is exactly one boundary
    between them.
    """
    text = pt.render_report(context(), [], [], [], [], None, [])
    assert text.count(MARKER) == 1
    assert MARKER + "\n\n" + MARKER not in text
    assert len(messages(text)) == 2


def test_no_boundary_is_written_with_nothing_but_blank_lines_after_it():
    """Whitespace is not content: the check is on what renders, not on length."""
    pieces = pt.render_report(context(full=True), [], [], [], [], [], []).split(MARKER)
    assert all(piece.strip() for piece in pieces[1:])


def test_the_brief_keeps_its_place_even_with_nothing_to_report():
    """The first piece is the channel message; a report with no root has nowhere
    to thread."""
    text = pt.render_report(context(), [], [], [], [], None, [])
    assert text.startswith("```blockkit")
    assert text.index("```blockkit") < text.index(MARKER)


def test_a_foreign_title_is_carried_into_the_thread_detail():
    row = base_row(url="u", number=1, repo="o/r", title_source="解决中断续跑从头开始问题")
    text = pt.render_report(context(), [], [], [], [], None, [row])
    assert "source title: 解决中断续跑从头开始问题" in text
    assert pt.contains_foreign_script("解决中断") is True
    assert pt.contains_foreign_script("fix resume from checkpoint") is False


# ----------------------------------------------------------------- end to end


def test_track_then_report_delta_then_commit_over_a_real_file(tmp_path, monkeypatch):
    """The whole register-report-commit loop, network stubbed, over a real store."""
    store = tmp_path / "C0BPLSPHHDZ.jsonl"
    exit_code = pt.main(
        [
            "track",
            "--state-file", str(store),
            "--channel", "C0BPLSPHHDZ",
            "--slack-ts", "1786514497.123456",
            "--message-text", f"please look at {GITHUB_PR} and {GITCODE_MR}",
        ]
    )
    assert exit_code == 0
    ledger = pt.Ledger.load(store)
    assert len(ledger.rows) == 2
    assert pt.read_runs(pt.runs_path(store))["channel_id"] == "C0BPLSPHHDZ"

    # Stand in for the refresh phase: the GitHub side learns its MR iid.
    ledger.rows[0].update(
        {
            "refresh_ok": True,
            "mr_iid": 4717,
            "title_source": "fix: resume from checkpoint",
            "cla_ok": True,
            "ci_verdict": "fail",
            "ci_failure_hint": "unrelated_to_known_flake",
            "ci_failing_test_count": 2,
            "comment_count": 4,
            "head_sha": "abc",
            "observed_through_utc": WHEN,
            "reported_status": "awaiting_review",
            "reported_ci_verdict": "pass",
            "reported_comment_count": 4,
            "reported_head_sha": "abc",
        }
    )
    pt.coalesce_pairs(ledger, pt.pairing_from_rows(ledger.rows))
    ledger.write()
    assert len(pt.Ledger.load(store).rows) == 1

    row = pt.Ledger.load(store).rows[0]
    changes = pt.compute_delta(row)
    assert [kind for kind, _ in changes] == ["ci_red"]

    receipt = pt.build_receipt([row["key"]], {row["key"]: row}, WHEN, 1)
    runs = pt.read_runs(pt.runs_path(store))
    runs.setdefault("streams", {})["all"] = {
        "pending": {"run_id": "manual-1", "run_cutoff_utc": WHEN, "receipt": receipt}
    }
    pt.write_runs(pt.runs_path(store), runs)

    assert pt.main(
        ["commit", "--state-file", str(store), "--channel", "C0BPLSPHHDZ", "--run-id", "manual-1"]
    ) == 0
    committed = pt.Ledger.load(store).rows[0]
    assert pt.compute_delta(committed) == []
    bookkeeping = pt.read_runs(pt.runs_path(store))["streams"]["all"]
    assert bookkeeping["last_completed_run_id"] == "manual-1"
    assert bookkeeping["pending"] is None


def test_committing_the_same_run_twice_is_a_no_op(tmp_path):
    store = tmp_path / "s.jsonl"
    pt.main(["track", "--state-file", str(store), "--channel", "C", "--url", GITHUB_PR])
    runs = pt.read_runs(pt.runs_path(store))
    runs["streams"] = {"all": {"pending": {"run_id": "r1", "run_cutoff_utc": WHEN, "receipt": {}}}}
    pt.write_runs(pt.runs_path(store), runs)
    assert pt.main(["commit", "--state-file", str(store), "--channel", "C", "--run-id", "r1"]) == 0
    assert pt.main(["commit", "--state-file", str(store), "--channel", "C", "--run-id", "r1"]) == 0


# ------------------------------------------------- report --commit-after


def seeded_report(tmp_path, monkeypatch, capsys=None):
    """One registered item and a stubbed refresh, ready for a `report` run.

    The network is replaced wholesale: these tests are about what the run does
    to the watermark, and a refresh that reached GitHub would decide it. Pass
    `capsys` to drop the registration's own output, so a test can assert on
    exactly what the `report` run wrote.
    """
    store = tmp_path / "C0BPLSPHHDZ.jsonl"
    assert pt.main(
        ["track", "--state-file", str(store), "--channel", "C0BPLSPHHDZ", "--url", GITHUB_PR]
    ) == 0
    monkeypatch.setenv("GITHUB_TOKEN", "not-a-real-token")

    def stub_refresh(row, **kwargs):
        row.update(
            {
                "refresh_ok": True,
                "title_source": "fix: resume from checkpoint",
                "state": "open",
                "ci_verdict": "fail",
                "head_sha": "abc",
                "comment_count": 1,
            }
        )

    monkeypatch.setattr(pt, "refresh_row", stub_refresh)
    if capsys is not None:
        capsys.readouterr()
    return store


def bookkeeping_of(store):
    return pt.read_runs(pt.runs_path(store)).get("streams", {}).get("all", {})


def only_row(store):
    return pt.Ledger.load(store).rows[0]


def report_argv(store, *extra):
    return [
        "report",
        "--state-file", str(store),
        "--channel", "C0BPLSPHHDZ",
        "--run-id", "cron-1",
        *extra,
    ]


def test_commit_after_advances_the_watermark_in_one_invocation(tmp_path, monkeypatch, capsys):
    """The whole point: no second command, so nothing to retype and mistype."""
    store = seeded_report(tmp_path, monkeypatch, capsys)
    assert pt.main(report_argv(store, "--commit-after")) == 0

    book = bookkeeping_of(store)
    assert book["last_completed_run_id"] == "cron-1"
    assert book["pending"] is None
    assert pt.read_runs(pt.runs_path(store))["completed_runs"] == 1
    assert only_row(store)["observed_through_utc"] is not None

    captured = capsys.readouterr()
    assert captured.out.startswith("```blockkit"), "stdout is still just the report"
    # The epilogue is the thing being removed: a command printed to be copied.
    assert "Not yet committed" not in captured.err
    assert " commit --state-file" not in captured.err


def test_commit_after_reports_the_commit_as_json_on_stderr(tmp_path, monkeypatch, capsys):
    """stdout is the report, so the machine-readable receipt goes to stderr."""
    store = seeded_report(tmp_path, monkeypatch, capsys)
    assert pt.main(report_argv(store, "--commit-after")) == 0
    err = capsys.readouterr().err
    payload = json.loads(err[err.index("{"):err.rindex("}") + 1])
    assert payload["committed"] == "cron-1"
    assert payload["items"] == [only_row(store)["key"]]
    assert payload["store"] == "C0BPLSPHHDZ.jsonl"


def test_without_commit_after_the_run_is_exactly_as_before(tmp_path, monkeypatch, capsys):
    """The manual path is untouched: pending receipt, epilogue, no watermark."""
    store = seeded_report(tmp_path, monkeypatch, capsys)
    assert pt.main(report_argv(store)) == 0

    book = bookkeeping_of(store)
    assert book["pending"]["run_id"] == "cron-1"
    assert "last_completed_run_id" not in book
    assert only_row(store).get("observed_through_utc") is None

    err = capsys.readouterr().err
    assert "Not yet committed" in err
    assert " commit --state-file" in err
    assert "--run-id cron-1" in err


# -------------------------------------- what a narrowed run may decide about

OTHER_REPO_PR = "https://github.com/openJiuwen-ai/agent-core/pull/497"


def two_repository_store(tmp_path, monkeypatch, capsys):
    """One row in each of two repositories, and a refresh that records itself."""
    store = tmp_path / "C0BPLSPHHDZ.jsonl"
    for url in (GITHUB_PR, OTHER_REPO_PR):
        assert pt.main(
            ["track", "--state-file", str(store), "--channel", "C0BPLSPHHDZ", "--url", url]
        ) == 0
    monkeypatch.setenv("GITHUB_TOKEN", "not-a-real-token")

    refreshed_rows = []

    def stub_refresh(row, **kwargs):
        refreshed_rows.append(row["key"])
        row.update({"refresh_ok": True, "title_source": "fix: resume", "head_sha": "abc"})

    monkeypatch.setattr(pt, "refresh_row", stub_refresh)
    capsys.readouterr()
    return store, refreshed_rows


def test_a_narrowed_run_never_stamps_a_row_it_did_not_refresh(tmp_path, monkeypatch, capsys):
    """`--repo` narrows what a run refreshes, so it must narrow what it decides.

    `refresh_ok` is what the *last* run to touch a row left behind. A row from
    another repository still carries a true one from a run that is over, so
    stamping it terminal here promotes it on stored facts -- and the commit that
    follows retires it having never reported it. The item leaves the store's
    attention without any reader having been told it landed.
    """
    store, refreshed_rows = two_repository_store(tmp_path, monkeypatch, capsys)
    ledger = pt.Ledger.load(store)
    other = next(row for row in ledger.rows if row["repo"] == "openJiuwen-ai/agent-core")
    other.update({"refresh_ok": True, "gh_state": "closed", "observed_through_utc": WHEN})
    ledger.write()

    assert pt.main(report_argv(store, "--repo", "openJiuwen-ai/jiuwenswarm")) == 0
    assert refreshed_rows == ["github/openjiuwen-ai/jiuwenswarm#pr2724"]

    after = {row["key"]: row for row in pt.Ledger.load(store).rows}
    stayed = after["github/openjiuwen-ai/agent-core#pr497"]
    assert stayed["lifecycle"] == "active", "a row this run never looked at"
    assert "terminal_observed_utc" not in stayed


def test_a_run_that_reaches_a_row_still_stamps_it(tmp_path, monkeypatch, capsys):
    """The narrowing above must not cost the ordinary case its stamping."""
    store, _ = two_repository_store(tmp_path, monkeypatch, capsys)

    def stub_refresh(row, **kwargs):
        row.update({"refresh_ok": True, "gh_state": "closed", "head_sha": "abc"})

    monkeypatch.setattr(pt, "refresh_row", stub_refresh)
    assert pt.main(report_argv(store, "--repo", "openJiuwen-ai/jiuwenswarm")) == 0
    after = {row["key"]: row for row in pt.Ledger.load(store).rows}
    assert after["github/openjiuwen-ai/jiuwenswarm#pr2724"]["lifecycle"] == "terminal_pending"


def test_a_reported_terminal_item_stops_costing_the_run_anything(tmp_path, monkeypatch, capsys):
    """The bound on the whole design: the refresh set must not grow forever.

    Every saving inside the refresh is worth nothing if a store only ever gains
    rows to refresh, so the path out has to be one an ordinary run takes rather
    than one an operator has to remember. An item that landed is stamped by the
    run that saw it land, reported once by that run, and retired by that run's
    commit -- and a retired row is outside the set the next run refreshes, so it
    costs nothing from then on.
    """
    store = tmp_path / "C0BPLSPHHDZ.jsonl"
    assert pt.main(
        ["track", "--state-file", str(store), "--channel", "C0BPLSPHHDZ", "--url", GITHUB_PR]
    ) == 0
    monkeypatch.setenv("GITHUB_TOKEN", "not-a-real-token")
    refreshed_rows = []

    def landed(row, **kwargs):
        refreshed_rows.append(row["key"])
        row.update(
            {"refresh_ok": True, "title_source": "fix: resume", "head_sha": "abc",
             "mr_iid": 4717, "mr_state": "merged", "merged_at": WHEN}
        )

    monkeypatch.setattr(pt, "refresh_row", landed)
    capsys.readouterr()

    def lifecycles():
        return {row["lifecycle"] for row in pt.Ledger.load(store).rows}

    assert pt.main(report_argv(store)) == 0
    assert refreshed_rows == [only_row(store)["key"]]
    assert lifecycles() == {"terminal_pending"}, "stamped by the run that saw it land"

    refreshed_rows.clear()
    assert pt.main(report_argv(store, "--run-id", "cron-2", "--commit-after")) == 0
    assert len(refreshed_rows) == 1, "terminal_pending is still refreshed: it can reopen"
    assert lifecycles() == {"retired"}, "retired by the commit of the run that reported it"

    refreshed_rows.clear()
    assert pt.main(report_argv(store, "--run-id", "cron-3", "--commit-after")) == 0
    assert refreshed_rows == [], "a retired item is never refreshed again"


# ----------------------------------------- the ceiling the tracker enforces


def test_the_second_tracker_is_paced_below_the_ceiling_it_enforces():
    """Its limit is per user and per minute, and it publishes it nowhere.

    There is no rate-limit header on the way to the wall and no Retry-After at
    it -- the threshold appears only in the text of the refusal. So the count
    is kept on this side, and a run that would break it waits rather than
    spending an item to discover it again.
    """
    rate = pt.RequestRate(3, 60.0)
    assert [rate.wait() for _ in range(3)] == [True, True, True]
    assert rate.wait(deadline=time.monotonic() + 0.1) is False, "it would have to wait"


def test_a_refusal_spends_the_window_rather_than_one_request():
    """A refusal means the count on this side is wrong, not that it is one short.

    Another run sharing the address, or a ceiling narrower than the configured
    one, and either way the next caller walks into the same wall. Filling the
    window makes it wait the wall out instead.
    """
    rate = pt.RequestRate(5, 60.0)
    assert rate.wait() is True
    rate.penalise()
    assert rate.wait(deadline=time.monotonic() + 0.1) is False


def test_a_refused_request_is_retried_before_it_becomes_the_row_s_error(monkeypatch):
    """One retry, not a series: the window is a minute and a run has a budget."""
    replies = [(429, b'{"error_code":429}'), (200, b'{"state":"open"}')]
    monkeypatch.setattr(pt, "http_get", lambda url, headers, timeout=30: replies.pop(0))
    # A window measured in milliseconds rather than the minute the tracker
    # enforces: the retry really does wait the window out, and the test spends
    # that window rather than mocking the wait away.
    monkeypatch.setattr(pt, "gitcode_rate", pt.RequestRate(50, 0.05))
    assert pt.gitcode_json("https://tracker.test/repos/o/p/pulls/1") == {"state": "open"}
    assert replies == []


def test_a_second_refusal_is_reported_as_what_it_is(monkeypatch):
    """Named as the tracker's ceiling, and as one no credential raises.

    A run that reports `HTTP 429` alone sends a reader looking for a token to
    set. There is none: the threshold is per user, an anonymous caller is one
    user, and everything reading the tracker from one address shares it.
    """
    monkeypatch.setattr(
        pt, "http_get", lambda url, headers, timeout=30: (429, b'{"error_code":429}')
    )
    monkeypatch.setattr(pt, "gitcode_rate", pt.RequestRate(50, 0.05))
    with pytest.raises(RuntimeError) as refused:
        pt.gitcode_json("https://tracker.test/repos/o/p/pulls/1")
    assert "429" in str(refused.value)
    assert "per user" in str(refused.value)
    assert "not raised by any credential" in str(refused.value)


def test_waiting_out_the_ceiling_never_runs_past_the_run_s_budget(monkeypatch):
    """The run's own bound outranks this one.

    A worker that slept through the caller's timeout would lose the report, the
    receipt and the diagnosis together -- which is the failure the budget exists
    to prevent, arriving by a new route.
    """
    spent = pt.RequestRate(1, 60.0)
    assert spent.wait() is True
    monkeypatch.setattr(pt, "gitcode_rate", spent)
    with pytest.raises(RuntimeError) as stopped:
        pt.gitcode_json("https://tracker.test/repos/o/p/pulls/1", time.monotonic() - 1)
    assert "refresh budget" in str(stopped.value)


# ------------------------------- what a run that did not reach a row may say


def test_an_item_whose_refresh_failed_is_not_announced(tmp_path, monkeypatch, capsys):
    """Announced without being stamped is announced again, and again, forever.

    `build_receipt` drops a row whose refresh failed, so naming it in a section
    moves nothing: `observed_through_utc` stays unset, the item stays *newly
    tracked*, and the next run announces it again. A tracker refusing for an
    hour therefore produces the same item in every report of that hour, which
    reads as an item that keeps being registered.
    """
    store = tmp_path / "C0BPLSPHHDZ.jsonl"
    assert pt.main(
        ["track", "--state-file", str(store), "--channel", "C0BPLSPHHDZ", "--url", GITHUB_PR]
    ) == 0
    monkeypatch.setenv("GITHUB_TOKEN", "not-a-real-token")

    def refused(row, **kwargs):
        row.update({"refresh_ok": False, "refresh_error": "gitcode: HTTP 429"})

    monkeypatch.setattr(pt, "refresh_row", refused)
    capsys.readouterr()
    assert pt.main(report_argv(store, "--commit-after")) == 0

    out = capsys.readouterr().out
    assert "#2724" not in out, "it is not named on facts this run could not establish"
    assert "1 item(s) failed to refresh" in out
    assert only_row(store).get("observed_through_utc") is None, "nothing was stamped"


def test_the_roster_lists_only_what_the_run_established(tmp_path, monkeypatch, capsys):
    """`--full` renders the same claim about every row at once, so it obeys it.

    A row the run never reached renders on the roster as a status and an empty
    change column, which reads as an item in a known state with nothing to say
    -- printed directly beneath the line saying those items are left out
    because their stored state is not current. Both cannot be true.
    """
    store = tmp_path / "C0BPLSPHHDZ.jsonl"
    for url in (GITHUB_PR, "https://github.com/openJiuwen-ai/agent-core/pull/497"):
        assert pt.main(
            ["track", "--state-file", str(store), "--channel", "C0BPLSPHHDZ", "--url", url]
        ) == 0
    monkeypatch.setenv("GITHUB_TOKEN", "not-a-real-token")

    def refresh(row, **kwargs):
        if row["repo"] == "openJiuwen-ai/agent-core":
            row.update({"refresh_ok": False, "refresh_error": "gitcode: HTTP 429"})
        else:
            row.update({"refresh_ok": True, "title_source": "fix: resume", "head_sha": "abc"})

    monkeypatch.setattr(pt, "refresh_row", refresh)
    capsys.readouterr()
    assert pt.main(report_argv(store, "--full")) == 0

    out = capsys.readouterr().out
    assert "1 on the roster" in out
    assert "agent-core#497" not in out and "/agent-core/pull/497" not in out
    assert "1 item(s) failed to refresh" in out


def test_an_unknown_label_shared_by_many_rows_is_one_bullet(tmp_path, monkeypatch, capsys):
    """One label across a backlog is one fact about the tracker's label set.

    A label applied to every open item produced one bullet per row -- 34
    identical lines, most of a report's length, for one label. The rows
    sharing a label are named together in the bullet the label earns, not one
    each.
    """
    store = tmp_path / "C0BPLSPHHDZ.jsonl"
    urls = (
        GITHUB_PR,
        "https://github.com/openJiuwen-ai/agent-core/pull/497",
    )
    for url in urls:
        assert pt.main(
            ["track", "--state-file", str(store), "--channel", "C0BPLSPHHDZ", "--url", url]
        ) == 0
    monkeypatch.setenv("GITHUB_TOKEN", "not-a-real-token")

    def refresh(row, **kwargs):
        row.update({
            "refresh_ok": True,
            "title_source": "fix: resume",
            "head_sha": "abc",
            "unknown_labels": ["stat/needs-squash"],
        })

    monkeypatch.setattr(pt, "refresh_row", refresh)
    capsys.readouterr()
    assert pt.main(report_argv(store, "--commit-after")) == 0

    out = capsys.readouterr().out
    assert out.count("Unknown label `stat/needs-squash`") == 1, "one bullet, not one per row"
    assert "jiuwenswarm #2724" in out and "agent-core #497" in out, (
        "both rows are still named, together"
    )


def test_an_unknown_label_on_a_row_that_failed_to_refresh_is_not_announced(
    tmp_path, monkeypatch, capsys
):
    """The label loop reads off the same set every other section reports from.

    It used to iterate every active row rather than `reported_rows`, so on a
    partial run it could name a row's label after the report just said that
    row was omitted because its state was not current.
    """
    store = tmp_path / "C0BPLSPHHDZ.jsonl"
    for url in (GITHUB_PR, "https://github.com/openJiuwen-ai/agent-core/pull/497"):
        assert pt.main(
            ["track", "--state-file", str(store), "--channel", "C0BPLSPHHDZ", "--url", url]
        ) == 0
    monkeypatch.setenv("GITHUB_TOKEN", "not-a-real-token")

    def refresh(row, **kwargs):
        if row["repo"] == "openJiuwen-ai/agent-core":
            row.update({
                "refresh_ok": False,
                "refresh_error": "gitcode: HTTP 429",
                "unknown_labels": ["stat/needs-squash"],
            })
        else:
            row.update({
                "refresh_ok": True,
                "title_source": "fix: resume",
                "head_sha": "abc",
                "unknown_labels": ["stat/needs-squash"],
            })

    monkeypatch.setattr(pt, "refresh_row", refresh)
    capsys.readouterr()
    assert pt.main(report_argv(store, "--commit-after")) == 0

    out = capsys.readouterr().out
    assert "agent-core #497" not in out and "/agent-core/pull/497" not in out, (
        "not named on facts this run could not establish"
    )
    assert "jiuwenswarm #2724" in out
    assert "1 item(s) failed to refresh" in out


# ------------------------------------------------- the refresh budget


class Clock:
    """A monotonic clock the test moves by hand.

    The budget is wall-clock by construction, and a test that spent real
    seconds proving it would be slow, flaky, or both. Everything else `time`
    offers is delegated, so this substitutes for the module rather than
    standing in for one function of it.
    """

    def __init__(self, *ticks):
        self.ticks = list(ticks)

    def monotonic(self):
        return self.ticks.pop(0) if len(self.ticks) > 1 else self.ticks[0]

    def __getattr__(self, name):
        return getattr(time, name)


def test_rows_are_refreshed_at_the_same_time_rather_than_one_after_another():
    """The bound that makes a run of any size finish.

    A barrier is the whole proof: four rows can only reach it together if four
    are in flight together, and a serial refresh deadlocks until the timeout.
    Nothing here measures a duration, so nothing here is flaky on a loaded box.
    """
    barrier = threading.Barrier(4, timeout=10)
    rows = [{"key": f"k{n}"} for n in range(4)]

    def refresh(row):
        barrier.wait()
        row["seen"] = True

    unreached = pt.refresh_within_budget(rows, refresh, workers=4, deadline=None)
    assert unreached == []
    assert all(row["seen"] for row in rows)


def test_a_spent_budget_leaves_the_rows_it_never_started_alone():
    """Untouched, and named. The caller cannot report what it has not refreshed."""
    rows = [{"key": f"k{n}"} for n in range(3)]
    refreshed = []

    def refresh(row):
        refreshed.append(row["key"])

    unreached = pt.refresh_within_budget(
        rows, refresh, workers=1, deadline=time.monotonic() - 1
    )
    assert refreshed == []
    assert unreached == rows


def test_a_row_already_in_flight_is_allowed_to_finish():
    """Half an item's facts written into the store would be worse than a slow run."""
    rows = [{"key": "k0"}, {"key": "k1"}]
    started = time.monotonic()

    def refresh(row):
        row["seen"] = True

    # The first row starts inside the budget and the second does not.
    pt.time = Clock(started, started + 100)
    try:
        unreached = pt.refresh_within_budget(
            rows, refresh, workers=1, deadline=started + 10
        )
    finally:
        pt.time = time
    assert rows[0]["seen"] is True
    assert unreached == [rows[1]]
    assert "seen" not in rows[1]


def test_pairing_discovery_stops_at_the_budget_instead_of_paging_on():
    """The one loop inside a single row that can run for minutes by itself.

    Without a bound reaching into it, a row already in flight overshoots the
    run's budget by its whole paging cost rather than by one request, and that
    is the difference between finishing inside a caller's timeout and not.
    """
    row = {"number": 7, "head_sha": "abc"}
    with pytest.raises(RuntimeError) as stopped:
        pt.discover_pairing(row, "https://tracker.test/repos/o/p", 6,
                            time.monotonic() - 1)
    assert "refresh budget" in str(stopped.value)
    assert "not absent" in str(stopped.value), "an absence nobody established"


def test_a_stopped_pairing_search_is_not_recorded_as_no_pairing(monkeypatch):
    """`pairing: none` is a fact about the tracker; a spent budget is not one.

    Written into the store, an unestablished absence is believed by every run
    after the one that invented it, and the item's merge request never shows up
    again.
    """
    row = {"kind": "pull_request", "tracker": "github", "repo": "o/r", "number": 7}
    monkeypatch.setattr(pt, "fetch_github_facts", lambda *a, **k: {})
    pt.refresh_row(
        row,
        token="t",
        github_api="https://api.test",
        gitcode_api="https://tracker.test",
        gitcode_project_override="o/p",
        max_pages=6,
        signatures=[],
        fetch_artifact=False,
        deadline=time.monotonic() - 1,
    )
    assert row.get("pairing") != "none"
    assert row["refresh_ok"] is False
    assert "refresh budget" in row["refresh_error"]


# ------------------------------------------- the absence that was written down


def refreshed(row, monkeypatch, *, repositories=None, gitcode=None, **kwargs):
    """Refresh one row with both trackers replaced, and hand back the requests.

    Everything about a pairing is decided from what the second tracker returns,
    so these tests state the responses and count the requests. A test that
    asserts on a count is asserting on cost, which is the whole subject here.
    """
    seen = []

    def stub_gitcode(url, deadline=None):
        seen.append(url)
        return (gitcode or (lambda _: []))(url)

    monkeypatch.setattr(pt, "fetch_github_facts", lambda *a, **k: {})
    monkeypatch.setattr(pt, "gitcode_json", stub_gitcode)
    pt.refresh_row(
        row,
        token="t",
        github_api="https://api.test",
        gitcode_api="https://tracker.test",
        gitcode_project_override=None,
        max_pages=6,
        signatures=[],
        fetch_artifact=False,
        repositories=repositories if repositories is not None else PAIRED,
        **kwargs,
    )
    return seen


def unpaired_row(**extra):
    row = {
        "kind": "pull_request",
        "tracker": "github",
        "repo": "openJiuwen-ai/jiuwenswarm",
        "number": 2724,
        "lifecycle": "active",
    }
    row.update(extra)
    return row


def hours_ago(hours):
    return pt.format_utc(pt.now_utc() - timedelta(hours=hours))


def test_an_established_absence_is_read_back_rather_than_established_again(monkeypatch):
    """The whole listing, on every run, forever -- for an item that has no mirror.

    Establishing the absence costs every page of the second tracker's listing.
    Writing that finding into the row and never reading it back means paying it
    again on the next run, and on every run after that, for as long as the item
    is tracked.
    """
    row = unpaired_row(
        pairing="none",
        pairing_project="openJiuwen/jiuwenswarm",
        pairing_checked_utc=hours_ago(1),
    )
    seen = refreshed(row, monkeypatch)
    assert seen == [], "the second tracker was not asked anything"
    assert row["pairing"] == "none"
    assert row["refresh_ok"] is True


def test_an_established_absence_is_established_again_once_it_has_aged_out(monkeypatch):
    """The premise that cannot be checked, only aged out.

    The mirror is created some time after the pull request opens, so an absence
    is true of the moment it was established and of nothing later. Kept, it
    would hide the one event the pairing search exists to catch.
    """
    row = unpaired_row(
        pairing="none",
        pairing_project="openJiuwen/jiuwenswarm",
        pairing_checked_utc=hours_ago(pt.DEFAULT_PAIRING_RECHECK_HOURS + 1),
    )
    seen = refreshed(
        row,
        monkeypatch,
        gitcode=lambda url: (
            [{"source_branch": "github-pr-2724", "iid": 4717, "head": {"sha": "abc"}}]
            if "/pulls?" in url
            else {"state": "open", "html_url": "https://tracker.test/mr/4717"}
        ),
    )
    assert any("/pulls?" in url for url in seen), "it searched again"
    assert row["mr_iid"] == 4717
    assert row["pairing"] == "github-pr-branch"


def test_an_absence_established_against_another_project_is_not_read_back(monkeypatch):
    """A repository re-pointed at another project has an absence about elsewhere.

    The pairing is configuration. A finding made against the project the
    repository used to name says nothing at all about the one it names now, and
    reading it back would be the conclusion outliving its premise.
    """
    row = unpaired_row(
        pairing="none",
        pairing_project="openJiuwen/somewhere-else",
        pairing_checked_utc=hours_ago(1),
    )
    seen = refreshed(row, monkeypatch)
    assert any("/pulls?" in url for url in seen), "it searched the project now configured"
    assert row["pairing_project"] == "openJiuwen/jiuwenswarm"


def test_an_undated_absence_is_established_again_rather_than_believed(monkeypatch):
    """A store written before findings were dated upgrades itself by re-checking."""
    row = unpaired_row(pairing="none")
    seen = refreshed(row, monkeypatch)
    assert any("/pulls?" in url for url in seen)
    assert pt.parse_utc(row["pairing_checked_utc"]) is not None
    assert row["pairing_project"] == "openJiuwen/jiuwenswarm"


def test_an_unmapped_pairing_is_re_evaluated_when_the_configuration_gains_one(monkeypatch):
    """`unmapped` is a fact about the configuration, not about the item.

    It is recorded so a reader is told the decision state is unavailable rather
    than invented -- and it must stop being recorded on the first run after the
    configuration gains the mapping, without anybody editing the store.
    """
    row = unpaired_row(pairing="unmapped")
    refreshed(
        row,
        monkeypatch,
        gitcode=lambda url: (
            [{"source_branch": "github-pr-2724", "iid": 4717, "head": {"sha": "abc"}}]
            if "/pulls?" in url
            else {"state": "open", "html_url": "https://tracker.test/mr/4717"}
        ),
    )
    assert row["pairing"] == "github-pr-branch"
    assert row["mr_iid"] == 4717


def test_an_unmapped_pairing_carries_no_dated_finding_to_read_back(monkeypatch):
    """The two are kept apart on purpose.

    A dated finding is read back and would suppress the re-evaluation above, so
    `unmapped` never acquires one -- including on a row that had one before the
    repository lost its mapping.
    """
    row = unpaired_row(
        pairing="none",
        pairing_project="openJiuwen/jiuwenswarm",
        pairing_checked_utc=hours_ago(1),
    )
    refreshed(row, monkeypatch, repositories=pt.Repositories.from_config({}, []))
    assert row["pairing"] == "unmapped"
    assert "pairing_checked_utc" not in row
    assert "pairing_project" not in row


# -------------------------------------- one listing instead of one row's worth


def listing_page(iids, *, first_number=2700):
    return [
        {
            "iid": iid,
            "number": iid,
            "source_branch": f"github-pr-{first_number + offset}",
            "head": {"sha": f"sha{iid}"},
            "state": "open",
            "html_url": f"https://tracker.test/mr/{iid}",
            "labels": [],
        }
        for offset, iid in enumerate(iids)
    ]


def test_a_listing_answers_every_row_of_a_project_without_a_request_each(monkeypatch):
    """The second tracker's cost stops scaling with the store.

    Its listing carries the whole merge request -- state, merge date, head sha,
    labels, mergeable -- a hundred at a time, so a run that reads it once
    answers every row of that project from it. Reading `pulls/<iid>` per row is
    the same facts at one request each, and that is the per-row cost this
    removes.
    """
    rows = [unpaired_row(number=2700 + n, mr_iid=4700 + n) for n in range(15)]
    seen = []

    def stub_gitcode(url, deadline=None):
        seen.append(url)
        assert "/pulls/" not in url, "no row was fetched on its own"
        return listing_page(range(4700, 4715))

    monkeypatch.setattr(pt, "gitcode_json", stub_gitcode)
    listings = pt.read_project_listings(
        rows,
        gitcode_api="https://tracker.test",
        repositories=PAIRED,
        project_override=None,
        max_pages=6,
        recheck_hours=6,
        workers=1,
    )
    assert len(seen) == 1, "one page for fifteen rows"
    listing = listings["openJiuwen/jiuwenswarm"]
    for row in rows:
        assert listing.entry_for(row["mr_iid"]) is not None


def test_a_listing_is_not_read_when_too_few_rows_wait_on_it(monkeypatch):
    """A page costs about two merge requests, so one row can never pay for one.

    Without this a small store pays a large store's fixed cost, which is the
    obvious way an improvement for the many becomes a regression for the few.
    """
    monkeypatch.setattr(
        pt, "gitcode_json", lambda url, deadline=None: pytest.fail(f"the listing was read: {url}")
    )
    listings = pt.read_project_listings(
        [unpaired_row(mr_iid=4717)],
        gitcode_api="https://tracker.test",
        repositories=PAIRED,
        project_override=None,
        max_pages=6,
        recheck_hours=6,
        workers=1,
    )
    assert listings["openJiuwen/jiuwenswarm"].pages_read == 0


def test_a_listing_worth_less_than_it_costs_is_not_read(monkeypatch):
    """Three items are not worth six pages, whatever those pages might hold.

    The pages still unread have a price, and it is compared with the rows they
    could answer before each one. A store too small for the listing to pay keeps
    exactly the behaviour it had.
    """
    rows = [unpaired_row(number=2700 + n, mr_iid=4000 + n) for n in range(3)]
    monkeypatch.setattr(
        pt, "gitcode_json", lambda url, deadline=None: pytest.fail(f"the listing was read: {url}")
    )
    listing = pt.read_project_listing(
        "openJiuwen/jiuwenswarm", "https://tracker.test", 6, rows
    )
    assert listing.pages_read == 0
    assert listing.exhausted is False


def test_a_page_that_answered_nothing_does_not_stop_the_listing(monkeypatch):
    """Pages do not get less productive as they go, and a rule may not assume it.

    Measured against a real project, a page answering nothing is routinely
    followed by one answering fifteen: the listing is ordered by creation across
    every merge request, not only the mirrored ones, so the rows being looked
    for are spread rather than front-loaded. A rule that stopped on a
    disappointing page stopped before most of the store.
    """
    rows = [unpaired_row(number=2700 + n, mr_iid=4000 + n) for n in range(30)]
    served = [
        listing_page([9000, 9001]),
        listing_page(range(4000, 4018)),
        listing_page(range(4018, 4030)),
    ]
    monkeypatch.setattr(pt, "gitcode_json", lambda url, deadline=None: served.pop(0))
    listing = pt.read_project_listing(
        "openJiuwen/jiuwenswarm", "https://tracker.test", 6, rows
    )
    assert listing.pages_read == 3
    assert listing.pending_reads(rows, 6) == 0, "every row answered from the listing"


def test_a_pairing_still_unknown_is_worth_the_whole_listing(monkeypatch):
    """It costs the whole listing by itself, so it is priced as what it is.

    A row whose pairing has never been established pages the listing on its own
    if this phase does not. Pricing it at one read would stop the listing early
    and hand it that private paging back, which is the cost being removed.
    """
    monkeypatch.setattr(pt, "gitcode_json", lambda url, deadline=None: listing_page([9000]))
    listing = pt.read_project_listing(
        "openJiuwen/jiuwenswarm", "https://tracker.test", 6, [unpaired_row()]
    )
    assert listing.pages_read == 6
    assert listing.exhausted is True, "read to the end, so its absence means something"


def test_a_listing_read_to_its_end_is_evidence_of_absence(monkeypatch):
    """Absence from a listing means something only once the listing is complete."""
    rows = [unpaired_row(number=n) for n in (2724, 2725)]
    monkeypatch.setattr(pt, "gitcode_json", lambda url, deadline=None: [])
    listing = pt.read_project_listing(
        "openJiuwen/jiuwenswarm", "https://tracker.test", 6, rows
    )
    assert listing.exhausted is True

    row = unpaired_row()
    monkeypatch.setattr(pt, "fetch_github_facts", lambda *a, **k: {})
    monkeypatch.setattr(
        pt, "gitcode_json", lambda url, deadline=None: pytest.fail("it searched again anyway")
    )
    facts = pt.fetch_gitcode_facts(
        row, "openJiuwen/jiuwenswarm", "https://tracker.test", 6, listing=listing
    )
    assert facts["pairing"] == "none"
    assert pt.parse_utc(facts["pairing_checked_utc"]) is not None


def test_a_listing_that_stopped_early_is_not_evidence_of_absence(monkeypatch):
    """Same rule the per-row search already follows, for the same reason.

    A listing cut short by the budget has pages nobody read, and those pages
    might hold the merge request. Concluding absence from it would write a
    finding nobody established into the store, where every later run believes it.
    """
    listing = pt.ProjectListing("openJiuwen/jiuwenswarm", "https://tracker.test", 6)
    listing.ingest(listing_page([4700]))
    assert listing.exhausted is False

    searched = []
    monkeypatch.setattr(
        pt, "gitcode_json", lambda url, deadline=None: searched.append(url) or []
    )
    facts = pt.fetch_gitcode_facts(
        unpaired_row(), "openJiuwen/jiuwenswarm", "https://tracker.test", 6, listing=listing
    )
    assert searched, "the row fell back to the search it would have done anyway"
    assert facts["pairing"] == "none"


def test_a_row_the_listing_cannot_answer_is_still_fetched_on_its_own(monkeypatch):
    """The listing is an optimisation, never a narrowing of what is reported."""
    listing = pt.ProjectListing("openJiuwen/jiuwenswarm", "https://tracker.test", 6)
    listing.ingest(listing_page([4700]))
    fetched = []

    def stub_gitcode(url, deadline=None):
        fetched.append(url)
        return {"state": "merged", "merged_at": "2026-08-12T09:00:00Z", "labels": []}

    monkeypatch.setattr(pt, "gitcode_json", stub_gitcode)
    facts = pt.fetch_gitcode_facts(
        unpaired_row(mr_iid=9999),
        "openJiuwen/jiuwenswarm",
        "https://tracker.test",
        6,
        listing=listing,
    )
    assert fetched == ["https://tracker.test/repos/openJiuwen/jiuwenswarm/pulls/9999"]
    assert facts["mr_state"] == "merged"


def test_a_listing_that_cannot_be_read_costs_the_run_nothing_but_speed(monkeypatch):
    """A tracker that is down degrades this to the old cost, not to a lost run."""

    def stub_gitcode(url, deadline=None):
        raise RuntimeError("GitCode API returned HTTP 503")

    monkeypatch.setattr(pt, "gitcode_json", stub_gitcode)
    listing = pt.read_project_listing(
        "openJiuwen/jiuwenswarm",
        "https://tracker.test",
        6,
        [unpaired_row(number=n) for n in (2724, 2725)],
    )
    assert listing.exhausted is False, "nothing may be concluded from it"
    assert "503" in (listing.error or "")


def budgeted_store(tmp_path, monkeypatch, capsys):
    """Three registered items and a refresh that only ever reaches the first."""
    store = tmp_path / "C0BPLSPHHDZ.jsonl"
    urls = [
        "https://github.com/openJiuwen-ai/jiuwenswarm/pull/2724",
        "https://github.com/openJiuwen-ai/jiuwenswarm/pull/2725",
        "https://github.com/openJiuwen-ai/jiuwenswarm/pull/2726",
    ]
    assert pt.main(
        ["track", "--state-file", str(store), "--channel", "C0BPLSPHHDZ",
         *sum((["--url", url] for url in urls), [])]
    ) == 0
    monkeypatch.setenv("GITHUB_TOKEN", "not-a-real-token")

    def stub_refresh(row, **kwargs):
        row.update({"refresh_ok": True, "title_source": "fix: resume", "head_sha": "abc"})

    monkeypatch.setattr(pt, "refresh_row", stub_refresh)
    # The run's own clock reading, then one per row: the first row is inside the
    # budget and the two after it are not.
    monkeypatch.setattr(pt, "time", Clock(0.0, 1.0, 999.0, 999.0))
    capsys.readouterr()
    return store


def test_a_partial_run_says_so_in_the_channel_message(tmp_path, monkeypatch, capsys):
    """Above the fold, because a short report and a quiet week read identically."""
    store = budgeted_store(tmp_path, monkeypatch, capsys)
    assert pt.main(report_argv(store, "--max-seconds", "60")) == 0
    root, body = split_report(capsys.readouterr().out)
    assert "*Partial run:* 2 of 3 tracked items were not refreshed" in root
    assert "60s" in root
    assert "2 tracked item(s) were not refreshed" in body
    assert "not a quiet week" in body


def test_a_partial_run_does_not_consume_the_window_of_what_it_skipped(
    tmp_path, monkeypatch, capsys
):
    """The one thing a partial run must never do: report an item it never read."""
    store = budgeted_store(tmp_path, monkeypatch, capsys)
    assert pt.main(report_argv(store, "--max-seconds", "60", "--commit-after")) == 0
    reported = [
        row.get("observed_through_utc") is not None for row in pt.Ledger.load(store).rows
    ]
    assert reported.count(True) == 1, "an unrefreshed row was stamped as reported"
    assert reported.count(False) == 2


def test_a_partial_run_says_on_stderr_that_reissuing_it_changes_nothing(
    tmp_path, monkeypatch, capsys
):
    """The retry the timeout provoked burned the whole turn; the run says not to."""
    store = budgeted_store(tmp_path, monkeypatch, capsys)
    assert pt.main(report_argv(store, "--max-seconds", "60")) == 0
    err = capsys.readouterr().err
    assert "PARTIAL: 2 of 3" in err
    assert "Reissuing this command unchanged" in err
    assert "--refresh-workers" in err


def test_a_run_inside_its_budget_says_nothing_about_one(tmp_path, monkeypatch, capsys):
    """The bound is a backstop; a report that finished reads exactly as before."""
    store = seeded_report(tmp_path, monkeypatch, capsys)
    assert pt.main(report_argv(store)) == 0
    captured = capsys.readouterr()
    assert "Partial run" not in captured.out
    assert "were not refreshed" not in captured.out
    assert "PARTIAL" not in captured.err


def test_the_budget_default_leaves_room_under_a_caller_s_timeout():
    """A number, not a comment: the point of the default is that it is small."""
    assert pt.DEFAULT_REFRESH_BUDGET_SECONDS <= 300
    assert pt.DEFAULT_REFRESH_WORKERS > 1


def test_the_run_directory_is_derived_from_the_store_and_nothing_else():
    """A pure derivation, so any step of a run can reach it from the one path it has.

    Beside the store rather than under it: the store is a file, and the prompt
    that names the store has therefore named this too without saying so.
    """
    assert pt.run_dir_for(Path("/state/pr-tracker/C0BPLSPHHDZ.jsonl")) == Path(
        "/state/pr-tracker/C0BPLSPHHDZ.run"
    )
    assert pt.run_dir_for(Path("/state/pr-tracker/C0BPLSPHHDZ.jsonl")).parent == Path(
        "/state/pr-tracker"
    ), "the same directory as the ledger, the lock and the configuration"


def test_the_report_is_written_into_the_run_directory_without_being_told_where(
    tmp_path, monkeypatch, capsys
):
    """No --output, and still a file: the path is derived, so nobody has to pass it.

    This is the whole fix. The report is produced by one command, checked by the
    next and read by the third, and each of those is a fresh shell -- so a scratch
    directory the first one invents cannot be named by the second.
    """
    store = seeded_report(tmp_path, monkeypatch, capsys)
    assert pt.main(report_argv(store)) == 0

    report = pt.run_dir_for(store) / "report.md"
    assert report.is_file(), "written without --output"
    captured = capsys.readouterr()
    assert report.read_text(encoding="utf-8") == captured.out, "the same report"
    # Printed, because a path a later step rebuilds by hand is one it mistypes.
    assert str(report) in captured.err


def test_an_explicit_output_still_wins(tmp_path, monkeypatch, capsys):
    """The derived path is a default, not a policy: a caller may still name one."""
    store = seeded_report(tmp_path, monkeypatch, capsys)
    named = tmp_path / "somewhere-else.md"
    assert pt.main(report_argv(store, "--output", str(named))) == 0
    assert named.is_file()
    assert not (pt.run_dir_for(store) / "report.md").exists(), "one file, not two"
    assert str(named) in capsys.readouterr().err


def test_the_run_directory_is_emptied_at_the_start_of_the_run(
    tmp_path, monkeypatch, capsys
):
    store = seeded_report(tmp_path, monkeypatch, capsys)
    stale = pt.run_dir_for(store) / "report.md"
    stale.parent.mkdir(parents=True, exist_ok=True)
    stale.write_text("yesterday's report", encoding="utf-8")

    assert pt.main(report_argv(store)) == 0
    assert "yesterday" not in stale.read_text(encoding="utf-8")


def test_the_run_directory_is_emptied_even_by_a_run_that_then_fails(
    tmp_path, monkeypatch, capsys
):
    """The reason it is cleared on entry rather than on exit.

    A run that dies never reaches a cleanup step, and it is the dead run whose
    leftovers mislead the next one: a stale `report.md` beside the store is
    indistinguishable from the report this run was supposed to write, so the
    language check passes on it and the reply repeats a report nobody produced.
    """
    store = seeded_report(tmp_path, monkeypatch, capsys)
    stale = pt.run_dir_for(store) / "report.md"
    stale.parent.mkdir(parents=True, exist_ok=True)
    stale.write_text("yesterday's report", encoding="utf-8")

    def explode(*args, **kwargs):
        raise RuntimeError("rendering blew up")

    monkeypatch.setattr(pt, "render_report", explode)
    with pytest.raises(RuntimeError):
        pt.main(report_argv(store))
    assert not stale.exists(), "the failed run left nothing for the next one to find"


def test_a_write_into_the_run_directory_stops_the_run_rather_than_being_destroyed(
    tmp_path,
):
    """Emptying on entry used to destroy a write that was still in flight.

    A command line that empties the directory and writes into it at once --
    `report ... | some-filter > <run>/extract.json` -- has the shell create
    `extract.json` while it sets the pipeline up, before the script runs a line.
    The script then empties the directory underneath it and the filter's output
    lands, seconds later, in a file that no longer has a name. Nothing fails at
    the time; the run finds out when reading the file back says it is not there,
    which is also what a mistyped path says.

    Refusing keeps the entry-time clear, which is the part that must not move: a
    run that fails never reaches a cleanup step, so a leftover has to go before
    the run rather than after it.
    """
    store = tmp_path / "channel.jsonl"
    run_dir = pt.run_dir_for(store)
    run_dir.mkdir(parents=True)

    with (run_dir / "extract.json").open("w", encoding="utf-8"):
        with pytest.raises(SystemExit) as refusal:
            pt.prepare_run_dir(store)

    message = str(refusal.value)
    assert "extract.json" in message, "which file"
    assert "report" in message, "which command to reissue"
    assert "on its own" in message, "how to reissue it"
    assert "cannot help" in message, "why reissuing it unchanged will not do"
    assert "--output" in message, "where a report may legitimately be sent"
    assert (run_dir / "extract.json").exists(), "refused, not deleted mid-write"


def test_a_leftover_is_still_deleted_however_recently_it_was_written(tmp_path):
    """Age is not the test and must not become one.

    A stale `report.md` a failed run left a second ago is still the leftover
    that gets checked and replied with. What separates it from a write in
    flight is not when it was written but whether anything still holds it open.
    """
    store = tmp_path / "channel.jsonl"
    run_dir = pt.run_dir_for(store)
    run_dir.mkdir(parents=True)
    (run_dir / "report.md").write_text("yesterday's report", encoding="utf-8")

    assert pt.prepare_run_dir(store) == run_dir
    assert not (run_dir / "report.md").exists()


def test_the_guard_is_silent_on_a_directory_nothing_is_writing_to(tmp_path):
    store = tmp_path / "channel.jsonl"
    run_dir = pt.run_dir_for(store)
    run_dir.mkdir(parents=True)
    (run_dir / "report.md").write_text("closed again", encoding="utf-8")

    assert pt.names_held_open_in(run_dir) == []


def test_a_report_run_refuses_before_it_refreshes_anything(
    tmp_path, monkeypatch, capsys
):
    """The refusal has to land before the network work, not after it.

    A refresh is the expensive half of a run. A guard that fired after it would
    still have cost the run everything it was trying to save.
    """
    store = seeded_report(tmp_path, monkeypatch, capsys)
    run_dir = pt.run_dir_for(store)
    run_dir.mkdir(parents=True, exist_ok=True)

    def unreachable(*args, **kwargs):
        raise AssertionError("the run refreshed before it checked the directory")

    monkeypatch.setattr(pt, "render_report", unreachable)
    with (run_dir / "full_output.json").open("w", encoding="utf-8"):
        with pytest.raises(SystemExit) as refusal:
            pt.main(report_argv(store))

    assert "full_output.json" in str(refusal.value)


def test_a_report_that_cannot_be_written_does_not_commit(tmp_path, monkeypatch, capsys):
    """The report file is how the caller delivers. No file, no delivery, no commit."""
    store = seeded_report(tmp_path, monkeypatch)
    unwritable = tmp_path / "no-such-directory" / "report.md"
    with pytest.raises(SystemExit) as failure:
        pt.main(report_argv(store, "--commit-after", "--output", str(unwritable)))
    assert "Nothing was committed" in str(failure.value)

    book = bookkeeping_of(store)
    assert "last_completed_run_id" not in book
    assert book["pending"]["run_id"] == "cron-1", "left pending for the next run"
    assert only_row(store).get("observed_through_utc") is None


def test_a_failed_render_does_not_commit(tmp_path, monkeypatch):
    """A run that never produced a report has nothing to have delivered."""
    store = seeded_report(tmp_path, monkeypatch)

    def explode(*args, **kwargs):
        raise RuntimeError("rendering blew up")

    monkeypatch.setattr(pt, "render_report", explode)
    with pytest.raises(RuntimeError):
        pt.main(report_argv(store, "--commit-after"))

    book = bookkeeping_of(store)
    assert "last_completed_run_id" not in book
    assert not book.get("pending"), "the receipt is written after the render"
    assert only_row(store).get("observed_through_utc") is None


def test_commit_after_is_off_unless_asked_for(tmp_path, monkeypatch):
    """Opt-in. A caller that does not name the flag keeps the late commit."""
    store = seeded_report(tmp_path, monkeypatch)
    args = pt.build_parser().parse_args(report_argv(store))
    assert args.commit_after is False


# ------------------------------------------- a missing store is not an empty one
#
# The failure being guarded: a scheduled roster ran with a store path whose
# leading environment variable had been assigned an empty value in the same
# command, so `$VAR/agent/…` expanded to `/agent/…`. That directory does not
# exist, the store was not found, and the run rendered a complete, well-formed,
# entirely false report -- "0 tracked, none changed yet" -- and exited 0, while
# the real store sat elsewhere holding every row. Nothing in the output said
# anything was wrong, because nothing was wrong with the *report*; what was wrong
# was that it described a file nobody meant to read.
#
# Two checks close it, at two different points, and both are needed: the second
# catches a path that lost an expansion, and the first catches every other way a
# path can be wrong.


def report_against(path, *extra):
    return ["report", "--state-file", str(path), "--channel", "C0BPLSPHHDZ", *extra]


def test_report_refuses_a_store_that_does_not_exist(tmp_path, capsys):
    missing = tmp_path / "state" / "skills" / "pr-tracker" / "C0BPLSPHHDZ.jsonl"
    with pytest.raises(SystemExit) as refusal:
        pt.main(report_against(missing))
    message = str(refusal.value)
    assert "does not exist" in message
    assert "no report was produced" in message
    assert capsys.readouterr().out == "", "no report reached stdout"


def test_a_refused_report_leaves_nothing_behind_at_the_wrong_path(tmp_path):
    """It stops before the lock, the runs sidecar and the store itself.

    A run that scattered a `.runs.json` and a `.lock` into whatever directory a
    mistyped path named would make the mistake look established the next time
    somebody went looking.
    """
    directory = tmp_path / "state"
    directory.mkdir()
    missing = directory / "C0BPLSPHHDZ.jsonl"
    with pytest.raises(SystemExit):
        pt.main(report_against(missing))
    assert list(directory.iterdir()) == []


def test_the_refusal_names_a_path_that_has_lost_an_expansion(tmp_path):
    """The message that would have identified this morning's cause on its own.

    A path whose directory does not exist either did not merely name the wrong
    file: it never pointed anywhere. Saying so, and saying what that looks like,
    is the difference between a reply someone can act on and one that sends them
    to the store to check whether the rows are still there.
    """
    with pytest.raises(SystemExit) as refusal:
        pt.main(report_against(tmp_path / "gone" / "away" / "C0BPLSPHHDZ.jsonl"))
    message = str(refusal.value)
    assert "never pointed anywhere" in message
    assert "expanded to nothing" in message


def test_the_refusal_says_so_when_the_channel_is_evidently_set_up(tmp_path):
    """A sidecar beside the store proves the channel exists, so the store should.

    This is the *diagnosis*, not the gate. It cannot be the gate: a path that
    lost part of itself has no sidecar beside it either, which is exactly the
    case that has to fail.
    """
    missing = tmp_path / "C0BPLSPHHDZ.jsonl"
    pt.config_path(missing).write_text("{}", encoding="utf-8")
    with pytest.raises(SystemExit) as refusal:
        pt.main(report_against(missing))
    message = str(refusal.value)
    assert ".config.json" in message
    assert "supposed to exist" in message


def test_a_wrong_path_and_a_new_channel_are_not_distinguishable(tmp_path):
    """Which is the whole reason the gate is a flag rather than a heuristic."""
    bare = tmp_path / "C0BPLSPHHDZ.jsonl"
    with pytest.raises(SystemExit) as refusal:
        pt.main(report_against(bare))
    assert "nothing has ever been registered here" in str(refusal.value)


def test_the_flag_is_the_only_way_to_report_against_a_missing_store(
    tmp_path, monkeypatch, capsys
):
    """The escape hatch works, states itself on stderr, and is opt-in."""
    monkeypatch.setenv("GITHUB_TOKEN", "not-a-real-token")
    missing = tmp_path / "C0BPLSPHHDZ.jsonl"
    assert pt.main(report_against(missing, "--allow-missing-store")) == 0
    captured = capsys.readouterr()
    assert captured.out.startswith("```blockkit")
    assert "--allow-missing-store was given" in captured.err
    assert missing.exists(), "the run creates the store it was allowed to miss"
    assert pt.build_parser().parse_args(report_against(missing)).allow_missing_store is False


def test_a_genuinely_new_channel_becomes_reportable_by_registering(
    tmp_path, monkeypatch, capsys
):
    """The tension the gate has to leave intact.

    A channel with no store is not shut out and needs no flag: registering
    creates the store, and a report before the first registration had nothing to
    say anyway. `watch` is checked as well as `track` because either may be the
    first thing a new channel runs.
    """
    monkeypatch.setenv("GITHUB_TOKEN", "not-a-real-token")
    for first in ("track", "watch"):
        store = tmp_path / f"{first}-C0BPLSPHHDZ.jsonl"
        with pytest.raises(SystemExit):
            pt.main(report_against(store))
        if first == "track":
            assert track(store, channel="C0BPLSPHHDZ") == 0
        else:
            monkeypatch.setattr(
                pt,
                "search_watch_target",
                lambda target, *a, **k: (
                    [link(GITHUB_PR)],
                    {"author": target.login, "repo": target.repo},
                ),
            )
            pt.main(
                [
                    "watch",
                    "--state-file", str(store),
                    "--channel", "C0BPLSPHHDZ",
                    "--author", "someone",
                    "--repo", "owner/name",
                ]
            )
        capsys.readouterr()
        assert store.exists(), f"{first} creates the store"
        assert pt.main(report_against(store)) == 0, f"reportable after {first}"
        capsys.readouterr()


def test_a_state_path_whose_variable_is_set_but_empty_is_a_hard_stop(monkeypatch):
    """The silent case: set-but-empty leaves no dollar sign to catch.

    Distinct from an unset variable, which `expandvars` leaves alone and the
    existing check refuses. Here expansion succeeds and produces a path that has
    kept its shape and lost its root.
    """
    monkeypatch.setenv("SET_TO_NOTHING", "")
    with pytest.raises(SystemExit) as refusal:
        pt.resolve_state_file("$SET_TO_NOTHING/state/C0BPLSPHHDZ.jsonl", "C0BPLSPHHDZ")
    message = str(refusal.value)
    assert "SET_TO_NOTHING" in message, "the variable to stop assigning is named"
    assert "holds nothing" in message
    assert "never export" in message.lower() or "Do not export" in message


@pytest.mark.parametrize(
    "written",
    ["$EMPTIED/x.jsonl", "${EMPTIED}/x.jsonl", "/a/$EMPTIED/x.jsonl"],
)
def test_every_spelling_of_the_reference_is_seen(monkeypatch, written):
    monkeypatch.setenv("EMPTIED", "   ")
    assert pt.emptied_variables(written) == ["EMPTIED"]


def test_a_variable_holding_a_real_value_is_not_complained_about(monkeypatch):
    monkeypatch.setenv("FULL", "/srv/example")
    monkeypatch.delenv("ABSENT", raising=False)
    assert pt.emptied_variables("$FULL/x.jsonl") == []
    assert pt.emptied_variables("$ABSENT/x.jsonl") == [], "unset is the other check"
    assert pt.emptied_variables("/no/variables/here.jsonl") == []


def test_this_mornings_invocation_now_fails_loudly(tmp_path, monkeypatch, capsys):
    """End to end, as the run actually arrived: an emptied variable and a report.

    One assertion matters more than the others -- that stdout is empty. The
    defect was never a wrong exit code on its own; it was a rendered report
    delivered to a channel. Nothing that reaches stdout can be delivered.
    """
    monkeypatch.setenv("DATA_DIR_FOR_TEST", "")
    monkeypatch.setenv("GITHUB_TOKEN", "not-a-real-token")
    with pytest.raises(SystemExit) as refusal:
        pt.main(
            [
                "report",
                "--state-file",
                "$DATA_DIR_FOR_TEST/agent/workspace/state/skills/"
                "pr-tracker/C0BPLSPHHDZ.jsonl",
                "--channel", "C0BPLSPHHDZ",
                "--commit-after",
            ]
        )
    captured = capsys.readouterr()
    assert captured.out == "", "nothing renderable was produced"
    assert "0 tracked" not in captured.out + captured.err
    assert "DATA_DIR_FOR_TEST" in str(refusal.value)


def test_track_reports_an_all_untrackable_message_once(tmp_path, capsys):
    store = tmp_path / "s.jsonl"
    pt.main(
        [
            "track",
            "--state-file", str(store),
            "--channel", "C",
            "--message-text", "worth a read: https://example.com/a and https://example.com/b",
        ]
    )
    result = json.loads(capsys.readouterr().out)
    assert len(result["not_trackable"]) == 2
    assert result["skipped_incidental"] == []
    rows = pt.Ledger.load(store).rows
    assert all(row["lifecycle"] == "ignored" for row in rows), "kept as a dedupe key"


def test_track_skips_incidental_urls_when_something_real_was_registered(tmp_path, capsys):
    store = tmp_path / "s.jsonl"
    pt.main(
        [
            "track",
            "--state-file", str(store),
            "--channel", "C",
            "--message-text", f"{GITHUB_PR} — background at https://example.com/rfc",
        ]
    )
    result = json.loads(capsys.readouterr().out)
    assert result["skipped_incidental"] == ["https://example.com/rfc"]
    assert result["not_trackable"] == []
    assert len(result["registered"]) == 1


def test_track_unregisters_by_url_or_key(tmp_path, capsys):
    store = tmp_path / "s.jsonl"
    pt.main(["track", "--state-file", str(store), "--channel", "C", "--url", GITHUB_PR])
    pt.main(
        [
            "track", "--state-file", str(store), "--channel", "C",
            "--unregister", f"{GITHUB_PR}/files",
        ]
    )
    capsys.readouterr()
    assert pt.Ledger.load(store).rows[0]["lifecycle"] == "ignored"


def test_track_refuses_a_store_belonging_to_another_channel(tmp_path):
    store = tmp_path / "s.jsonl"
    pt.main(["track", "--state-file", str(store), "--channel", "C_ONE", "--url", GITHUB_PR])
    with pytest.raises(SystemExit):
        pt.main(["track", "--state-file", str(store), "--channel", "C_TWO", "--url", GITHUB_PR])


def test_track_makes_no_network_call(tmp_path, monkeypatch):
    """`track` must be fast enough to run inside a link-trigger turn."""

    def explode(*args, **kwargs):
        raise AssertionError("track reached the network")

    monkeypatch.setattr(pt, "http_get", explode)
    monkeypatch.setattr(pt.urllib.request, "urlopen", explode)
    store = tmp_path / "s.jsonl"
    assert pt.main(
        ["track", "--state-file", str(store), "--channel", "C", "--url", GITHUB_PR]
    ) == 0


def test_a_missing_github_token_is_a_hard_stop(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    with pytest.raises(SystemExit) as error:
        pt.resolve_token("GITHUB_TOKEN")
    assert "anonymous" in str(error.value)


def test_the_token_is_read_from_the_named_variable_and_never_echoed(monkeypatch, capsys):
    monkeypatch.setenv("SOME_OTHER_TOKEN", "s3cret-value")
    assert pt.resolve_token("SOME_OTHER_TOKEN") == "s3cret-value"
    assert "s3cret-value" not in capsys.readouterr().out


# ------------------------------------------------- Slack provenance, validated

# The value a live run actually wrote into five rows on 2026-08-13: the run's own
# date, rendered as a human-readable local-time clock reading in UTC+8, eight
# hours ahead of the run. It came from the current date injected into the system
# prompt, which is why it looks so plausible and why a format check catches it
# where a sanity-check on the date would not.
FABRICATED_TS = "2026-08-13 17:28:52"
REAL_TS = "1786613308.937139"


def track(store, *extra, channel="C"):
    return pt.main(
        ["track", "--state-file", str(store), "--channel", channel, "--url", GITHUB_PR, *extra]
    )


@pytest.mark.parametrize(
    "value",
    [
        FABRICATED_TS,
        "2026-08-13T17:28:52Z",
        "1786613308",  # no fraction: an epoch, not a message id
        "1786613308.93713",  # five digits
        "1786613308.9371390",  # seven digits
        "178661330.937139",  # nine-digit epoch
        "1786613308,937139",
        " 1786613308.937139",
        "1786613308.937139 ",
        "p1786613308937139",
        "",
        "now",
    ],
)
def test_a_value_that_is_not_a_slack_ts_is_refused(value):
    assert pt.check_slack_ts(value) is not None


@pytest.mark.parametrize("value", [REAL_TS, "1358878749.000002", "1786514497.123456"])
def test_a_real_slack_ts_passes(value):
    assert pt.check_slack_ts(value) is None


def test_a_correctly_shaped_ts_outside_the_plausible_range_is_still_refused():
    """The regex alone would pass these; the range check is what catches them."""
    assert "before Slack existed" in (pt.check_slack_ts("1000000000.000000") or "")
    ahead = pt.now_utc() + pt.timedelta(hours=8)
    assert "in the future" in (pt.check_slack_ts(f"{ahead.timestamp():.6f}") or "")


def test_a_few_seconds_of_clock_skew_is_not_treated_as_a_fabrication():
    soon = pt.now_utc() + pt.timedelta(seconds=30)
    assert pt.check_slack_ts(f"{soon.timestamp():.6f}") is None


def test_the_fabricated_ts_is_not_stored_and_the_item_still_registers(tmp_path, capsys):
    """The whole defect: the value must not survive, the registration must.

    Refusing the run instead would break every registration in a channel whose
    prompt asks for a ts the caller cannot obtain, which is the situation that
    produced the bad value in the first place.
    """
    store = tmp_path / "s.jsonl"
    assert track(store, "--slack-ts", FABRICATED_TS) == 0
    captured = capsys.readouterr()
    result = json.loads(captured.out)

    assert [entry["key"] for entry in result["registered"]] == [
        "github/openjiuwen-ai/jiuwenswarm#pr2724"
    ]
    rejected = result["rejected_provenance"]
    assert [entry["flag"] for entry in rejected] == ["--slack-ts"]
    assert rejected[0]["value"] == FABRICATED_TS
    assert "1786613308.937139" in rejected[0]["expected"], "the message names the shape"
    assert FABRICATED_TS in captured.err, "and the refusal is not only in the JSON"

    source = pt.Ledger.load(store).rows[0]["sources"][0]
    assert source["slack_ts"] is None, "a refused value is never provenance"
    assert source["slack_ts_rejected"] == FABRICATED_TS


def test_a_real_ts_is_stored_verbatim_and_dates_the_row(tmp_path, capsys):
    store = tmp_path / "s.jsonl"
    assert track(store, "--slack-ts", REAL_TS) == 0
    assert json.loads(capsys.readouterr().out)["rejected_provenance"] == []
    row = pt.Ledger.load(store).rows[0]
    assert row["sources"][0]["slack_ts"] == REAL_TS
    assert "slack_ts_rejected" not in row["sources"][0]
    assert row["first_seen_utc"] == pt.slack_ts_to_utc(REAL_TS)


def test_omitting_the_ts_registers_a_row_that_audits_clean(tmp_path, capsys):
    """The documented fallback -- omit rather than guess -- stays a good path."""
    store = tmp_path / "s.jsonl"
    assert track(store) == 0
    assert json.loads(capsys.readouterr().out)["rejected_provenance"] == []
    source = pt.Ledger.load(store).rows[0]["sources"][0]
    assert source["slack_ts"] is None
    assert "slack_ts_rejected" not in source
    assert pt.main(["audit", "--state-file", str(store), "--channel", "C"]) == 0


def test_a_refused_ts_leaves_the_row_shaped_exactly_like_an_omitted_one(tmp_path, capsys):
    """Two fabrications of one repost must not become two distinct sources.

    This is the dedupe half of the defect: `sources[]` collapses on
    `(slack_ts, url)`, so two invented timestamps for the same link used to claim
    two separate messages. With both refused they are one entry, which is what an
    omitted flag would have produced.
    """
    store = tmp_path / "s.jsonl"
    track(store, "--slack-ts", FABRICATED_TS)
    track(store, "--slack-ts", "2026-08-13 19:02:11")
    capsys.readouterr()
    assert len(pt.Ledger.load(store).rows[0]["sources"]) == 1


def test_a_permalink_that_is_not_slacks_is_refused_and_the_item_registers(tmp_path, capsys):
    store = tmp_path / "s.jsonl"
    assert track(store, "--slack-permalink", "https://example.com/archives/C/p1") == 0
    result = json.loads(capsys.readouterr().out)
    assert [entry["flag"] for entry in result["rejected_provenance"]] == ["--slack-permalink"]
    row = pt.Ledger.load(store).rows[0]
    assert row["slack_permalink"] is None
    assert len(result["registered"]) == 1


def test_a_real_permalink_is_kept(tmp_path, capsys):
    store = tmp_path / "s.jsonl"
    link_url = "https://example.slack.com/archives/C0BPLSPHHDZ/p1786613308937139"
    assert track(store, "--slack-permalink", link_url) == 0
    capsys.readouterr()
    assert pt.Ledger.load(store).rows[0]["slack_permalink"] == link_url


def test_the_permalink_is_not_cross_checked_against_the_ts():
    """A permalink to a threaded reply legitimately disagrees with a parent ts."""
    assert pt.check_slack_permalink(
        "https://example.slack.com/archives/C0BPLSPHHDZ/p1111111111000000"
    ) is None


def test_the_author_is_never_refused(tmp_path, capsys):
    """No shape separates a real display name from an invented one (deliberate)."""
    store = tmp_path / "s.jsonl"
    assert track(store, "--slack-author", "definitely not a user id") == 0
    result = json.loads(capsys.readouterr().out)
    assert result["rejected_provenance"] == []
    assert pt.Ledger.load(store).rows[0]["slack_author"] == "definitely not a user id"


def test_audit_finds_rows_written_before_the_check_existed(tmp_path, capsys):
    """The five live rows: detectable, and reported without being touched."""
    store = tmp_path / "s.jsonl"
    track(store)
    capsys.readouterr()
    ledger = pt.Ledger.load(store)
    ledger.rows[0]["sources"][0]["slack_ts"] = FABRICATED_TS
    ledger.write()
    before = store.read_bytes()
    alongside = sorted(path.name for path in tmp_path.iterdir())

    assert pt.main(["audit", "--state-file", str(store), "--channel", "C"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert [entry["slack_ts"] for entry in report["malformed_slack_ts"]] == [FABRICATED_TS]
    assert report["malformed_slack_ts"][0]["key"] == "github/openjiuwen-ai/jiuwenswarm#pr2724"
    assert "unregister" in report["malformed_remedy"], "a path out, not a migration"

    assert store.read_bytes() == before, "audit is read-only"
    assert sorted(path.name for path in tmp_path.iterdir()) == alongside, "and writes nothing"


def test_audit_reports_a_refusal_separately_from_a_stored_bad_value(tmp_path, capsys):
    store = tmp_path / "s.jsonl"
    track(store, "--slack-ts", FABRICATED_TS)
    capsys.readouterr()
    assert pt.main(["audit", "--state-file", str(store), "--channel", "C"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["malformed_slack_ts"] == [], "nothing bad reached the store"
    assert [entry["slack_ts_rejected"] for entry in report["refused_slack_ts"]] == [
        FABRICATED_TS
    ]
    assert "--slack-ts" in report["refused_remedy"], "the fault is upstream of the store"


def audit(store, channel="C"):
    return ["audit", "--state-file", str(store), "--channel", channel]


def test_audit_never_creates_a_store_it_was_pointed_at_by_mistake(tmp_path, capsys):
    """The read-only promise, over the path most likely to break it.

    An absent store is where a command is most tempted to bring one into
    existence, and the check that it does not has to cover the whole directory
    rather than the store alone: the sidecars are the files that appear without
    anybody asking. Nothing may be created, so the directory stays exactly as
    empty as it was -- no store, no `.runs.json`, and not even a `.lock`.
    """
    missing = tmp_path / "nope.jsonl"
    assert pt.main(audit(missing)) == 2
    capsys.readouterr()
    assert sorted(path.name for path in tmp_path.iterdir()) == [], "audit creates nothing"
    assert not missing.exists()


def test_audit_over_a_store_that_is_not_there_is_not_a_clean_audit(tmp_path, capsys):
    """The defect: a gate cannot tell a clean store from one it never opened.

    Both halves are asserted, because either alone leaves the failure usable. The
    exit code is what a shell reads, and 2 rather than 1 so that "nothing was
    read" stays distinct from "something was found". The JSON is what a human
    reads, and it must not contain a findings key: an empty list of malformed
    entries is a clean verdict to every reader there is.
    """
    missing = tmp_path / "C0BPLSPHHDZ.jsonl"
    assert pt.main(audit(missing)) == 2, "not 0, and not the code a finding uses"
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert result["store_exists"] is False
    assert result["audited"] is False, "the output says which of the two happened"
    for absent in ("rows", "malformed_slack_ts", "refused_slack_ts"):
        assert absent not in result, f"{absent} would read as a finding of nothing"
    assert "nothing was audited" in captured.err, "a caller discarding stdout still sees it"


def test_an_empty_store_is_audited_and_reported_clean(tmp_path, capsys):
    """The other side of the distinction: present and clean is a real result.

    A store that exists and holds nothing was read, so it audits clean and exits
    0. This is what the absent case must not look like, and the two are compared
    field by field rather than trusted to differ.
    """
    empty = tmp_path / "C0BPLSPHHDZ.jsonl"
    empty.write_text("", encoding="utf-8")
    assert pt.main(audit(empty)) == 0
    result = json.loads(capsys.readouterr().out)
    assert (result["store_exists"], result["audited"], result["rows"]) == (True, True, 0)
    assert result["malformed_slack_ts"] == [], "read, and found nothing"


def test_a_new_channel_becomes_auditable_by_registering_and_needs_no_flag(
    tmp_path, capsys
):
    """The genuinely-new channel, and why it gets no escape hatch.

    `report` has `--allow-missing-store` because a report over an empty store is
    an artefact someone may want delivered. A clean audit over a file that was
    never opened is not an artefact at all, so there is nothing for a flag to
    authorise -- and a new channel does not need one, because registering creates
    the store, exactly as it does for a report.
    """
    store = tmp_path / "C0BPLSPHHDZ.jsonl"
    assert pt.main(audit(store)) == 2
    assert track(store, channel="C0BPLSPHHDZ") == 0
    capsys.readouterr()
    assert pt.main(audit(store)) == 0, "auditable once something is registered"
    assert json.loads(capsys.readouterr().out)["rows"] == 1
    with pytest.raises(SystemExit):
        pt.build_parser().parse_args(audit(store) + ["--allow-missing-store"])


def test_both_commands_say_the_same_thing_about_one_absent_path(tmp_path):
    """The diagnosis is shared, so the two cannot drift over the same path.

    What is around an absent store is the same evidence whichever command found
    it missing, and it is the sentence that identifies the real cause. Each of
    the three cases is checked through both commands.
    """
    cases = (
        (tmp_path / "gone" / "away" / "C0BPLSPHHDZ.jsonl", "never pointed anywhere"),
        (tmp_path / "sidecar" / "C0BPLSPHHDZ.jsonl", "supposed to exist"),
        (tmp_path / "bare" / "C0BPLSPHHDZ.jsonl", "nothing has ever been registered"),
    )
    (tmp_path / "sidecar").mkdir()
    (tmp_path / "bare").mkdir()
    pt.config_path(cases[1][0]).write_text("{}", encoding="utf-8")
    for store, phrase in cases:
        assert phrase in pt.describe_absent_store(store), store.parent.name
        with pytest.raises(SystemExit) as refusal:
            pt.refuse_absent_store(store, False)
        assert phrase in str(refusal.value), "report says it"


def test_an_emptied_variable_stops_an_audit_as_it_stops_a_report(monkeypatch, tmp_path):
    """The other half of the same failure, already shared and checked here too.

    The path is resolved by one function for every subcommand, so the set-but-empty
    refusal covers `audit` without anything being added to it. That is asserted
    rather than assumed, since it is the exact invocation that produced the silent
    `store_exists: false` in the first place.
    """
    monkeypatch.setenv("SET_TO_NOTHING", "")
    with pytest.raises(SystemExit) as refusal:
        pt.main(audit("$SET_TO_NOTHING/state/C0BPLSPHHDZ.jsonl", "C0BPLSPHHDZ"))
    assert "SET_TO_NOTHING" in str(refusal.value)
    assert sorted(path.name for path in tmp_path.iterdir()) == []


# ------------------------------------------------------- output stays portable


LEAK_PATTERNS = (
    # a host's home directory: a username and this deployment's layout
    (re.compile(r"/(?:home|Users)/[A-Za-z0-9._-]+/"), "an absolute home-directory path"),
    # a release number the reader cannot see a roadmap for
    (re.compile(r"\bv[12]\b"), "a bare version token"),
    # a document that does not ship with the skill
    (re.compile(r"design section", re.IGNORECASE), "a design-document citation"),
)


def emitted_strings():
    """Every string literal in the script that is not a docstring.

    Docstrings and comments are exempt on purpose: they explain implementation
    choices to whoever reads the source and never reach stdout, stderr, a
    rendered report or a JSON field. The module docstring's first line is the
    exception -- argparse prints it as the CLI description -- so it is included.
    """
    source = (Path(pt.__file__)).read_text(encoding="utf-8")
    tree = ast.parse(source)
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", None)
            if body and isinstance(body[0], ast.Expr):
                value = body[0].value
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    docstrings.add(id(value))
    found = [
        (node.lineno, node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    ]
    found.append((1, (pt.__doc__ or "").splitlines()[0]))
    return found


def test_no_user_facing_string_carries_this_deployments_context():
    """A skill's output must not carry the context of the people who built it.

    Narrow on purpose: a home-directory path, `v1`/`v2` standing alone, and a
    citation of a design document nobody outside this repository can read. It
    does not fire on any word that merely contains "v1".
    """
    offences = [
        f"pr_tracker.py:{lineno}: {complaint}: {text!r}"
        for lineno, text in emitted_strings()
        for pattern, complaint in LEAK_PATTERNS
        if pattern.search(text)
    ]
    assert not offences, "\n".join(offences)


def test_the_leak_guard_catches_what_it_claims_to():
    hits = {
        complaint
        for sample in (
            "store: /home/someone/.state/x.jsonl",
            "registration is by link trigger only in v1",
            "see design section 8.2",
        )
        for pattern, complaint in LEAK_PATTERNS
        if pattern.search(sample)
    }
    assert len(hits) == 3, hits
    for benign in ("ipv1addr", "the v1000 runner", "revision", "/home is a directory"):
        assert not any(pattern.search(benign) for pattern, _ in LEAK_PATTERNS), benign


# ----------------------------------------------- the prose stays portable too
#
# The guard above walks the script's AST, so SKILL.md and references/ had no
# protection at all and drifted: the header line, the registration section and
# half of *Rules* came to state one Slack connector's mechanisms -- its trigger
# name, its config keys, its metadata fields -- as though they were properties
# of the skill. A reader on another host cannot act on any of them, and cannot
# tell which parts of the document still apply to them.
#
# Two files are exempt from the mechanism rule and only from it, because they
# are where host-specific text is supposed to live: prompts.md must name a real
# channel and a real store path or it is not a prompt, and host-notes.md exists
# precisely to hold one host's behaviour under a heading that says so.

SKILL_ROOT = Path(pt.__file__).resolve().parent.parent
MECHANISM_EXEMPT = frozenset({"references/prompts.md", "references/host-notes.md"})

DOC_LEAK_PATTERNS = LEAK_PATTERNS + (
    # A command printed for someone to run, naming an interpreter that is absent
    # on hosts shipping only `python3`. It fires only where what follows looks
    # like an argument -- a flag, a quote, a variable, a path -- so that prose
    # about python, and `python 3.11`, and an absolute path to an interpreter,
    # all stay quiet.
    (
        re.compile(r"""(?<![\w./-])python (?=[-"'$/~<]|(?!\d)\S*[./]\S*)"""),
        "a bare `python` invocation",
    ),
)

# A repository this deployment tracks, written as the owner/name slug that
# configuration now carries. Same class as a channel id, and forbidden for the
# same reason: which repositories exist, and how each is paired with the second
# tracker, is one deployment's answer, and a skill that states it cannot be
# installed anywhere else. Matched on the owner and the slash so that the label
# namespace the second tracker uses, which is an organisation-wide vocabulary
# rather than a repository, stays out of it.
TRACKED_REPOSITORY = (
    re.compile(r"\bopenjiuwen(?:-ai)?/[\w.-]+", re.IGNORECASE),
    "a repository this deployment tracks",
)

# The link trigger is absent from this table, and cannot be added to it: the
# word one host names that trigger with is the same word the skill uses for a
# link everywhere else, so no pattern can tell a leak from ordinary prose. The
# rule still holds -- name the shape of the constraint, not one host's word for
# it -- it just has no automatic guard here.
HOST_MECHANISMS = (
    (re.compile(r"\bblockkit_tables\b"), "one host's config key"),
    (re.compile(r"\bJIUWENSWARM_DATA_DIR\b"), "one host's environment variable"),
    (re.compile(r"\bslack_message_ts\b"), "one host's internal metadata field"),
    TRACKED_REPOSITORY,
)


def shipped_docs():
    """Every prose file the skill ships, discovered rather than listed.

    Discovery is the point: a reference added later is covered without anyone
    remembering to extend a list here.
    """
    found = [SKILL_ROOT / "SKILL.md"] + sorted((SKILL_ROOT / "references").iterdir())
    return [path for path in found if path.is_file()]


def prose_lines(text):
    """(lineno, line) for lines outside ``` fenced blocks.

    Fences are exempt from the mechanism rule alone: a command is a command, and
    `--via url` is a flag value rather than a claim about the world.
    """
    out = []
    fenced = False
    for lineno, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if not fenced:
            out.append((lineno, line))
    return out


def test_the_shipped_prose_carries_no_host_context():
    """Rules that hold for every shipped file, fenced commands included."""
    docs = shipped_docs()
    assert len(docs) >= 5, [path.name for path in docs]
    offences = [
        f"{path.relative_to(SKILL_ROOT)}:{lineno}: {complaint}: {line.strip()!r}"
        for path in docs
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        for pattern, complaint in DOC_LEAK_PATTERNS
        if pattern.search(line)
    ]
    assert not offences, "\n".join(offences)


def test_only_the_host_specific_files_name_this_hosts_mechanisms():
    """Everywhere else, name the shape of the constraint, not this host's word
    for it: "the trigger the host offers for links posted in a channel", not the
    config key that turns it on."""
    for name in MECHANISM_EXEMPT:
        assert (SKILL_ROOT / name).is_file(), f"{name} is exempt but does not exist"
    offences = [
        f"{path.relative_to(SKILL_ROOT)}:{lineno}: {complaint}: {line.strip()!r}"
        for path in shipped_docs()
        if str(path.relative_to(SKILL_ROOT)) not in MECHANISM_EXEMPT
        for lineno, line in prose_lines(path.read_text(encoding="utf-8"))
        for pattern, complaint in HOST_MECHANISMS
        if pattern.search(line)
    ]
    assert not offences, "\n".join(offences)


def test_no_repository_of_any_deployment_is_named_in_the_skill():
    """Adding a repository must be an edit to configuration, never to the skill.

    Stricter than the guards above in both directions, because a repository name
    is not prose that a reader can discount: the script is checked whole --
    comments and docstrings included, since a pairing written down in a comment
    is still a pairing the skill carries -- and the shipped documents are checked
    inside their fenced examples too, since an example naming a real repository
    is exactly how one gets copied into the next deployment's file.
    """
    pattern, complaint = TRACKED_REPOSITORY
    checked = [Path(pt.__file__)] + [
        path
        for path in shipped_docs()
        if str(path.relative_to(SKILL_ROOT)) not in MECHANISM_EXEMPT
    ]
    offences = [
        f"{path.name}:{lineno}: {complaint}: {line.strip()!r}"
        for path in checked
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if pattern.search(line)
    ]
    assert not offences, "\n".join(offences)


def test_the_repository_guard_separates_a_slug_from_a_shared_vocabulary():
    """It must fire on the thing that moved and stay silent on what did not.

    The label namespace belongs to the whole forge rather than to any one
    repository, and the renderer marker is not a repository at all. A guard that
    fired on either would be deleted rather than obeyed.
    """
    pattern, _ = TRACKED_REPOSITORY
    for slug in ("openJiuwen-ai/jiuwenswarm", "openJiuwen/agent-core", "openjiuwen/x"):
        assert pattern.search(slug), slug
    for benign in ("openJiuwen-cla/yes", "sig/some-group", "owner/name"):
        assert not pattern.search(benign), benign


DOC_GUARD_MUST_FIRE = (
    ("store: /home/someone/state/x.jsonl", "an absolute home-directory path"),
    ("the v1 store format", "a bare version token"),
    ("as set out in design section 8.2", "a design-document citation"),
    ("run python scripts/pr_tracker.py track", "a bare `python` invocation"),
    ("python …/pr_tracker.py report", "a bare `python` invocation"),
    ("python -m pytest tests", "a bare `python` invocation"),
)

MECHANISM_GUARD_MUST_FIRE = (
    "Block Kit tables must be enabled (blockkit_tables: auto).",
    "$JIUWENSWARM_DATA_DIR/agent/workspace/state",
    "the gateway keeps slack_message_ts in its request metadata",
    "the pairing for openJiuwen-ai/jiuwenswarm is openJiuwen/jiuwenswarm",
)

# A guard that fires on ordinary prose gets deleted rather than obeyed, so the
# wording the rewrite actually uses is pinned as explicitly as the leaks are.
DOC_GUARD_MUST_NOT_FIRE = (
    "Registration: link trigger only",
    "Registration happens through whatever trigger the host offers for links.",
    "The trigger may fire once per message and may not see edits.",
    "python3 scripts/pr_tracker.py report --commit-after",
    "/usr/bin/python -m pytest tests",
    "Python 3.9 or newer is required.",
    "needs python 3.9 or newer",
    "the python interpreter the host provides",
    "~/.local/state/pr-tracker/<channel>.jsonl",
    "/home is a directory",
    "ipv1addr",
    "the v1000 runner",
    "revision",
    "a design decision recorded in section 4",
    "the openJiuwen-cla/yes label means the agreement is signed",
    "labels under sig/ name the group, not the repository",
    '"repositories": {"owner/name": {"gitcode": "namespace/project"}}',
    "the automatic linker resolves it",
    "an auto-linking host",
    "CPython and PyPy both work",
)


@pytest.mark.parametrize("sample,complaint", DOC_GUARD_MUST_FIRE)
def test_the_doc_guard_fires_on_a_real_leak(sample, complaint):
    hits = {name for pattern, name in DOC_LEAK_PATTERNS if pattern.search(sample)}
    assert complaint in hits, hits


@pytest.mark.parametrize("sample", MECHANISM_GUARD_MUST_FIRE)
def test_the_mechanism_guard_fires_on_a_host_mechanism(sample):
    assert any(pattern.search(sample) for pattern, _ in HOST_MECHANISMS), sample


@pytest.mark.parametrize("sample", DOC_GUARD_MUST_NOT_FIRE)
def test_neither_guard_fires_on_legitimate_prose(sample):
    offences = [
        complaint
        for pattern, complaint in DOC_LEAK_PATTERNS + HOST_MECHANISMS
        if pattern.search(sample)
    ]
    assert not offences, f"{sample!r} tripped {offences}"


def test_no_emitted_string_names_a_host_mechanism_as_a_fact():
    """One host's name for a mechanism is not a fact about the skill.

    A report header naming the config key that enables a route is read by
    someone whose host has no such key and cannot be acted on. What the report
    prints for a route is the reader-facing phrase in REGISTRATION_ROUTES, and
    the key beside it never leaves the store.
    """
    offences = [
        f"pr_tracker.py:{lineno}: {complaint}: {text!r}"
        for lineno, text in emitted_strings()
        for pattern, complaint in HOST_MECHANISMS
        if pattern.search(text)
    ]
    assert not offences, "\n".join(offences)


def test_track_does_not_echo_the_store_path_into_its_own_output(tmp_path, capsys):
    """The path is input. It arrives on the command line and stops there.

    `track` runs inside a channel-facing turn, so everything it prints is a
    candidate for being quoted into the channel by the model that ran it.
    """
    store = tmp_path / "C0BPLSPHHDZ.jsonl"
    assert track(store) == 0
    captured = capsys.readouterr()
    for stream in (captured.out, captured.err):
        assert str(tmp_path) not in stream
    assert json.loads(captured.out)["store"] == "C0BPLSPHHDZ.jsonl"



def test_no_emitted_command_names_a_bare_python():
    """Commands the caller is told to run verbatim must be runnable as printed.

    The commit epilogue printed a bare ``python``. A host with only ``python3``
    on PATH ran it as instructed and got ``/bin/sh: python: not found``, exit
    127 -- so the run was never committed and the same items re-reported on
    every tick. The instruction to substitute nothing is what makes the
    printed text load-bearing.
    """
    source = Path(pt.__file__).read_text()
    offenders = [
        line.strip()
        for line in source.splitlines()
        if re.search(r'["\s]python (?![3\w])', line) and "sys.executable" not in line
    ]
    assert not offenders, offenders
    assert "sys.executable" in source


def test_only_declared_closing_links_are_captured():
    """A mention is not a claim.

    GitHub closes an issue on merge only for its own keywords, so matching
    exactly those keeps the column to links the author declared. Every other
    cross-reference in a body is a mention, and that is where false positives
    would come from.
    """
    body = (
        "Fixes #123 and resolves openJiuwen-ai/agent-core#45.\n"
        "See #999 for context, related to #888, cf #777.\n"
        "Closes https://github.com/o/r/issues/7\n"
    )
    refs = pt.declared_closes(body, "openJiuwen-ai/jiuwenswarm")
    assert refs == [
        "openJiuwen-ai/jiuwenswarm#123",
        "openJiuwen-ai/agent-core#45",
        "o/r#7",
    ]
    for mention in ("#999", "#888", "#777"):
        assert mention not in " ".join(refs)


def test_a_bare_number_resolves_against_the_items_own_repo():
    assert pt.declared_closes("fixes #4", "o/r") == ["o/r#4"]


def test_the_same_issue_named_twice_appears_once():
    assert pt.declared_closes("Fixes #4, closes #4", "o/r") == ["o/r#4"]


def test_see_also_shows_nothing_rather_than_guessing():
    """An empty cell means the item declared none, not that none exist."""
    row = base_row(url="u1", number=1, repo="o/r", title_source="t1")
    table = pt.render_change_table([(row, [])])
    assert "| See also |" in table.splitlines()[0]
    assert table.splitlines()[2].rstrip().endswith("| — |")


def test_see_also_caps_the_list_and_counts_the_rest():
    row = base_row(url="u1", number=1, repo="o/r", title_source="t1",
                   closes=[f"o/r#{n}" for n in range(1, 6)])
    cell = pt.render_change_table([(row, [])]).splitlines()[2]
    assert "o/r#1, o/r#2, o/r#3 +2" in cell


# --------------------------------------------------------------- author watch


WATCH_STORE_ROWS = "openJiuwen-ai/jiuwenswarm"


PAIRED_PROJECT = "a-namespace/a-project"
CONFIGURED_REPOSITORIES = {WATCH_STORE_ROWS: {"gitcode": PAIRED_PROJECT}}


def watch_store(tmp_path, *, rows=(), runs=None):
    """A store, its runs sidecar, and the derived configuration path."""
    state = tmp_path / "C0BPLSPHHDZ.jsonl"
    state.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    if runs is not None:
        pt.runs_path(state).write_text(
            json.dumps(runs, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return state, pt.config_path(state)


def write_config(path, watch, *, repositories=None):
    """The configuration a watch test needs: a repository, and who to watch.

    The repositories are stated because the watch has no other source of them:
    with none configured the run has nothing to search, which is its own test
    below rather than the precondition of every other one.
    """
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "repositories": (
                    CONFIGURED_REPOSITORIES if repositories is None else repositories
                ),
                "watch": watch,
            }
        ),
        encoding="utf-8",
    )


def search_result(*numbers, kind="pull_request", repo=WATCH_STORE_ROWS):
    segment = "pull" if kind == "pull_request" else "issues"
    return {
        "total_count": len(numbers),
        "incomplete_results": False,
        "items": [
            {
                "html_url": f"https://github.com/{repo}/{segment}/{number}",
                **({"pull_request": {}} if kind == "pull_request" else {}),
            }
            for number in numbers
        ],
    }


def fake_search(responses, *, calls=None):
    """A stand-in for the search endpoint, keyed by a substring of the query."""

    def search(query, token, api_base, *, page=1, per_page=100):
        if calls is not None:
            calls.append(query)
        for needle, response in responses.items():
            if needle in query:
                if isinstance(response, Exception):
                    raise response
                return (response if page == 1 else search_result()), {}
        return search_result(), {}

    return search


def run_watch(monkeypatch, argv, responses, *, calls=None):
    monkeypatch.setenv("GITHUB_TOKEN", "x")
    monkeypatch.setattr(pt, "github_search", fake_search(responses, calls=calls))
    return pt.main(argv)


# ----------------------------------------------- where the configuration lives


def test_the_configuration_derives_from_the_store_and_adds_no_second_path():
    """One path in the prompt, three files beside it.

    A second `--config` flag would add another long absolute literal to every
    command line that already carries one, and a retyped path is a mistyped
    path. Derivation adds no literal and stays recoverable from the store name
    at any point.
    """
    state = Path("/srv/state/skills/pr-tracker/C0BPLSPHHDZ.jsonl")
    assert pt.config_path(state).name == "C0BPLSPHHDZ.config.json"
    assert pt.config_path(state).parent == state.parent
    assert pt.config_path(state) != pt.runs_path(state) != pt.lock_path(state)


def test_a_configuration_outside_the_skill_is_where_an_edited_file_belongs():
    """It is derived from the store, and a store inside the skill is refused."""
    with pytest.raises(SystemExit):
        pt.resolve_state_file(str(pt.SKILL_DIR / "watch.jsonl"), "C0B")


def test_no_configuration_is_a_clean_no_op_not_an_error(tmp_path, monkeypatch, capsys):
    """A channel that watches nobody is a configuration, not a fault."""
    state, list_file = watch_store(tmp_path)
    assert not list_file.exists()
    code = run_watch(
        monkeypatch, ["watch", "--state-file", str(state), "--channel", "C0B"], {}
    )
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert code == 0
    assert result["configured"] is False
    assert result["repositories_configured"] == []
    assert result["registered"] == []
    assert ".config.json" in captured.err, "it says how the file is named"
    assert not pt.runs_path(state).exists()


def test_an_unreadable_configuration_stops_rather_than_watching_nobody(tmp_path, monkeypatch):
    """Watching nobody and failing to read whom to watch look identical after."""
    state, list_file = watch_store(tmp_path)
    list_file.write_text('{"authors": [', encoding="utf-8")
    with pytest.raises(SystemExit) as error:
        run_watch(
            monkeypatch, ["watch", "--state-file", str(state), "--channel", "C0B"], {}
        )
    assert "not valid JSON" in str(error.value)
    assert "C0BPLSPHHDZ.config.json" in str(error.value)


def test_a_bare_list_configuration_is_refused_with_the_shape_it_should_have(tmp_path):
    """A bare list cannot gain a setting later without rewriting every file."""
    _, list_file = watch_store(tmp_path)
    list_file.write_text('["someone"]', encoding="utf-8")
    with pytest.raises(SystemExit) as error:
        pt.load_config(list_file)
    assert "bare list" in str(error.value)
    assert '"authors"' in str(error.value)
    assert '"repositories"' in str(error.value)


def test_an_unknown_configuration_key_is_noted_and_not_rejected(tmp_path):
    """A newer file on an older script still watches the authors it names."""
    _, list_file = watch_store(tmp_path)
    write_config(list_file, {"authors": ["a"], "_note": "ignored", "future_key": 1})
    config, notes = pt.load_config(list_file)
    assert config["watch"]["authors"] == ["a"]
    assert any("future_key" in note for note in notes)
    assert not any("_note" in note for note in notes), "underscore keys are notes"


def test_the_no_configuration_note_names_the_exact_file_it_looked_for(
    tmp_path, monkeypatch, capsys
):
    """No config file exists: the note must name the one file it looked for.

    A message that says a store has no configuration without naming the exact
    file it checked for is not actionable -- the operator holding an editor
    cannot tell what to create. `config_path` derives one name from the store;
    that is now the only file this loader ever looks for, and it has to appear
    verbatim.
    """
    state, list_file = watch_store(tmp_path)
    assert not list_file.exists()
    code = run_watch(
        monkeypatch, ["watch", "--state-file", str(state), "--channel", "C0B"], {}
    )
    captured = capsys.readouterr()
    assert code == 0
    assert pt.config_path(state).name in captured.err


# ------------------------------------------------- the repositories themselves


def repositories(raw, notes=None):
    return pt.Repositories.from_config(raw, [] if notes is None else notes)


def test_a_repository_with_no_properties_is_tracked_on_one_tracker_alone():
    """The state the pairing comment has always described, now expressible.

    It is configured -- the watch defaults to it and its capitalisation is
    known -- and it simply has no second tracker, which the refresh handles by
    fetching nothing from one.
    """
    configured = repositories({"o/plain": {}, "o/paired": {"gitcode": "n/p"}})
    assert configured.slugs == ["o/paired", "o/plain"]
    assert configured.gitcode_for("o/plain") is None
    assert configured.gitcode_for("o/paired") == "n/p"
    assert pt.gitcode_project_for("o/plain", None, configured) is None


def test_a_repository_absent_from_the_configuration_still_resolves():
    """Absent is not an error anywhere: no pairing, and the slug stands."""
    configured = repositories({"o/known": {"gitcode": "n/p"}})
    assert pt.gitcode_project_for("o/other", None, configured) is None
    assert configured.display("Some/Other") == "Some/Other"
    assert configured.github_for_gitcode("n/other") is None


def test_a_null_value_means_the_same_as_an_empty_one():
    assert repositories({"o/r": None}).slugs == ["o/r"]


def test_the_lookup_is_case_insensitive_and_gives_back_the_configured_case():
    """Identity keys are lowercased and posted links are not, so both arrive."""
    configured = repositories({"Owner/Name": {"gitcode": "Namespace/Project"}})
    assert configured.display("owner/name") == "Owner/Name"
    assert configured.gitcode_for("OWNER/NAME") == "Namespace/Project"
    assert configured.github_for_gitcode("namespace/project") == "owner/name"


def test_the_override_beats_the_configuration_for_one_run():
    """How a pairing is checked before anybody writes it down."""
    configured = repositories({"o/r": {"gitcode": "n/p"}})
    assert pt.gitcode_project_for("o/r", "n/other", configured) == "n/other"


def test_two_repositories_may_not_share_one_project():
    """The misconfiguration that reports fiction rather than failing.

    Each would be told the other's merges, and both reports would look right.
    """
    with pytest.raises(SystemExit) as error:
        repositories({"o/one": {"gitcode": "n/p"}, "o/two": {"gitcode": "N/P"}})
    assert "o/one" in str(error.value) and "o/two" in str(error.value)


def test_one_repository_may_not_be_named_twice_in_two_capitalisations():
    with pytest.raises(SystemExit) as error:
        repositories({"Owner/Name": {}, "owner/name": {}})
    assert "twice" in str(error.value)


@pytest.mark.parametrize(
    "raw",
    [
        ["o/r"],
        {"not-a-slug": {}},
        {"o/r/extra": {}},
        {"o/r": ["gitcode"]},
        {"o/r": {"gitcode": "no-slash"}},
    ],
)
def test_a_malformed_repositories_block_is_refused(raw):
    with pytest.raises(SystemExit):
        repositories(raw)


def test_an_unknown_repository_property_is_noted_and_not_rejected():
    notes = []
    configured = repositories({"o/r": {"gitcode": "n/p", "future": 1, "_why": "x"}}, notes)
    assert configured.gitcode_for("o/r") == "n/p"
    assert any("future" in note for note in notes)
    assert not any("_why" in note for note in notes)


# ------------------------------------------------------- planning the searches


def test_a_watch_entry_may_be_a_login_or_an_object(tmp_path):
    targets, _, _ = pt.plan_watch_targets(
        {"authors": ["one", {"login": "two", "kinds": ["issue"]}]},
        cli_authors=None,
        cli_repos=None,
        cli_kinds=None,
        cli_state=None,
        default_repos=["o/r"],
    )
    assert [target.login for target in targets] == ["one", "two"]
    assert targets[0].kinds == ("pull_request", "issue")
    assert targets[1].kinds == ("issue",)


def test_a_disabled_entry_is_reported_rather_than_dropped_silently(tmp_path):
    targets, disabled, _ = pt.plan_watch_targets(
        {"authors": ["one", {"login": "two", "enabled": False}]},
        cli_authors=None, cli_repos=None, cli_kinds=None, cli_state=None,
        default_repos=["o/r"],
    )
    assert [target.login for target in targets] == ["one"]
    assert disabled == ["two"]


def test_the_watch_fans_out_across_every_repository(tmp_path):
    targets, _, _ = pt.plan_watch_targets(
        {"authors": ["one"], "repos": ["o/a", "o/b"]},
        cli_authors=None, cli_repos=None, cli_kinds=None, cli_state=None,
        default_repos=["ignored/because-configured"],
    )
    assert [target.repo for target in targets] == ["o/a", "o/b"]


def test_the_default_repositories_are_the_configured_ones():
    """Not the whole organisation, and not a list the script carries.

    Every configured repository, in the capitalisation it was configured in, so
    that adding one to the watch is the same edit as adding one to be tracked.
    """
    repositories = pt.Repositories.from_config(
        {"o/b": {}, "o/A": {"gitcode": "n/a"}}, []
    )
    targets, _, _ = pt.plan_watch_targets(
        {"authors": ["one"]},
        cli_authors=None, cli_repos=None, cli_kinds=None, cli_state=None,
        default_repos=repositories.slugs,
    )
    assert [target.repo for target in targets] == ["o/A", "o/b"]


def test_repos_and_authors_stay_separate_axes_and_cross_by_default():
    """Every author in every repository, unless an author says otherwise.

    The two axes are independent on purpose: the common case is a team watched
    across everything it works on, and per-author scoping is already expressible
    without a second structure, by giving that author its own `repos`.
    """
    targets, _, _ = pt.plan_watch_targets(
        {"authors": ["everywhere", {"login": "narrow", "repos": ["o/b"]}]},
        cli_authors=None, cli_repos=None, cli_kinds=None, cli_state=None,
        default_repos=["o/a", "o/b"],
    )
    assert [(t.login, t.repo) for t in targets] == [
        ("everywhere", "o/a"),
        ("everywhere", "o/b"),
        ("narrow", "o/b"),
    ]


def test_an_author_flag_replaces_the_list_rather_than_adding_to_it():
    """A one-off never has to edit the operator's file, and never sweeps it."""
    targets, _, notes = pt.plan_watch_targets(
        {"authors": ["configured"]},
        cli_authors=["just-this-one"], cli_repos=None, cli_kinds=None,
        cli_state=None, default_repos=["o/r"],
    )
    assert [target.login for target in targets] == ["just-this-one"]
    assert any("--author" in note for note in notes)


def test_a_watch_with_no_repository_is_refused_rather_than_searching_everything():
    with pytest.raises(SystemExit) as error:
        pt.plan_watch_targets(
            {"authors": ["one"]},
            cli_authors=None, cli_repos=None, cli_kinds=None, cli_state=None,
            default_repos=[],
        )
    assert "not a search of everything" in str(error.value)


def test_a_leading_at_sign_on_a_login_is_tolerated():
    targets, _, _ = pt.plan_watch_targets(
        {"authors": ["@someone"]},
        cli_authors=None, cli_repos=None, cli_kinds=None, cli_state=None,
        default_repos=["o/r"],
    )
    assert targets[0].login == "someone"


# ------------------------------------------------------------- the two sweeps


def target(login="who", repo="o/r", kinds=("pull_request", "issue"), state="all"):
    return pt.WatchTarget(login=login, repo=repo, kinds=kinds, state=state)


def test_the_open_sweep_has_no_date_floor_at_all():
    """Live work is what a watch is for, and a months-old open PR is live."""
    sweeps = dict(pt.build_search_queries(target(), "2026-08-07"))
    assert "is:open" in sweeps["open"]
    assert "closed:" not in sweeps["open"] and "created:" not in sweeps["open"]
    assert "updated:" not in sweeps["open"]


def test_the_closed_sweep_is_floored_on_when_the_item_closed():
    """Not on when it was last touched: a year-old PR with a fresh comment has
    no delta left to report and would arrive needing immediate retirement."""
    sweeps = dict(pt.build_search_queries(target(), "2026-08-07"))
    assert "is:closed closed:>=2026-08-07" in sweeps["closed"]
    assert "updated:" not in sweeps["closed"]


def test_asking_for_open_only_drops_the_closed_sweep_entirely():
    assert [name for name, _ in pt.build_search_queries(target(state="open"), "2026-08-07")] == ["open"]


def test_both_kinds_cost_one_request_rather_than_two():
    """The endpoint returns issues and pull requests together."""
    for _, query in pt.build_search_queries(target(), None):
        assert "is:pr" not in query and "is:issue" not in query


def test_narrowing_to_one_kind_says_so_in_the_query():
    sweeps = dict(pt.build_search_queries(target(kinds=("pull_request",)), None))
    assert "is:pr" in sweeps["open"]
    sweeps = dict(pt.build_search_queries(target(kinds=("issue",)), None))
    assert "is:issue" in sweeps["open"]


@pytest.mark.parametrize(
    "value,expected",
    [(None, "2026-08-07"), (7, "2026-08-07"), ("7d", "2026-08-07"),
     ("2026-01-01", "2026-01-01"), ("all", None), (0, None)],
)
def test_the_closed_window_accepts_days_a_date_or_all(value, expected):
    now = pt.parse_utc("2026-08-14T06:00:00Z")
    assert pt.watch_closed_since(value, None, now=now) == expected


def test_a_window_that_is_not_a_window_is_refused():
    with pytest.raises(SystemExit):
        pt.watch_closed_since("last tuesday", None, now=pt.now_utc())


# ------------------------------------------- the property the watch must hold


FROZEN_RUNS = {
    "schema_version": 1,
    "channel_id": "C0B",
    "completed_runs": 12,
    "streams": {
        "all": {
            "last_completed_run_utc": "2026-08-13T06:00:07Z",
            "last_completed_run_id": "cron-1",
            "last_attempt_utc": "2026-08-13T06:00:02Z",
            "pending": None,
            "consecutive_failures": 0,
        }
    },
}


def test_the_watch_registers_without_moving_the_watermark(tmp_path, monkeypatch, capsys):
    """The one property this command exists to keep.

    Both scheduled jobs share the stream `all`, so a registering run that
    advanced the watermark would consume the delta before the report that was
    meant to deliver it ever ran -- and the report would then have nothing to
    say and no way to know it had been robbed.
    """
    state, list_file = watch_store(tmp_path, runs=FROZEN_RUNS)
    write_config(list_file, {"authors": ["someone"]})
    before = pt.runs_path(state).read_bytes()

    code = run_watch(
        monkeypatch,
        ["watch", "--state-file", str(state), "--channel", "C0B",
         "--repo", WATCH_STORE_ROWS],
        {"is:open": search_result(2724, 2725)},
    )
    result = json.loads(capsys.readouterr().out)

    assert code == 0
    assert len(result["registered"]) == 2, "it did register something"
    assert pt.runs_path(state).read_bytes() == before, (
        "the runs sidecar is byte-identical: no watermark, no receipt, no attempt"
    )
    runs = json.loads(pt.runs_path(state).read_text(encoding="utf-8"))
    assert runs["completed_runs"] == 12
    assert runs["streams"]["all"]["last_completed_run_utc"] == "2026-08-13T06:00:07Z"
    assert runs["streams"]["all"]["pending"] is None
    rows = [json.loads(line) for line in state.read_text(encoding="utf-8").splitlines()]
    assert all(row["observed_through_utc"] is None for row in rows), (
        "nothing has been reported to anyone yet"
    )


def test_the_watch_never_writes_the_runs_sidecar_by_any_path():
    """A source-level guard, because the behavioural test can only prove the
    paths it happens to walk. `cmd_watch` must not so much as name the writers."""
    source = ast.parse(Path(pt.__file__).read_text(encoding="utf-8"))
    watch = next(
        node for node in ast.walk(source)
        if isinstance(node, ast.FunctionDef) and node.name == "cmd_watch"
    )
    called = {
        node.func.id
        for node in ast.walk(watch)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    forbidden = {"write_runs", "build_receipt", "apply_receipt", "commit_pending",
                 "commit_receipt_json", "refresh_row"}
    assert not (called & forbidden), sorted(called & forbidden)
    assert "read_runs" in called, "it still checks the store's owner"


def test_a_second_watch_run_registers_nothing_new(tmp_path, monkeypatch, capsys):
    """Registering is an upsert on the identity key, so a re-run is free."""
    state, list_file = watch_store(tmp_path, runs=FROZEN_RUNS)
    write_config(list_file, {"authors": ["someone"]})
    argv = ["watch", "--state-file", str(state), "--channel", "C0B",
            "--repo", WATCH_STORE_ROWS]
    responses = {"is:open": search_result(2724, 2725)}

    run_watch(monkeypatch, argv, responses)
    first = json.loads(capsys.readouterr().out)
    run_watch(monkeypatch, argv, responses)
    second = json.loads(capsys.readouterr().out)

    assert len(first["registered"]) == 2 and first["already_tracked"] == []
    assert second["registered"] == [] and len(second["already_tracked"]) == 2
    assert second["rows_after"] == first["rows_after"] == 2


def test_the_store_never_grows_a_duplicate_row_for_one_item(tmp_path, monkeypatch, capsys):
    state, list_file = watch_store(tmp_path, runs=FROZEN_RUNS)
    write_config(list_file, {"authors": ["someone"]})
    for _ in range(3):
        run_watch(
            monkeypatch,
            ["watch", "--state-file", str(state), "--channel", "C0B",
             "--repo", WATCH_STORE_ROWS],
            {"is:open": search_result(2724)},
        )
        capsys.readouterr()
    keys = [json.loads(line)["key"] for line in state.read_text(encoding="utf-8").splitlines()]
    assert keys == ["github/openjiuwen-ai/jiuwenswarm#pr2724"]


# ------------------------------------------------- what the store gets told


def test_a_watched_row_records_the_route_and_the_login_it_came_from(tmp_path, monkeypatch, capsys):
    state, list_file = watch_store(tmp_path, runs=FROZEN_RUNS)
    write_config(list_file, {"authors": ["someone"]})
    run_watch(
        monkeypatch,
        ["watch", "--state-file", str(state), "--channel", "C0B",
         "--repo", WATCH_STORE_ROWS],
        {"is:open": search_result(2724)},
    )
    capsys.readouterr()
    row = json.loads(state.read_text(encoding="utf-8").splitlines()[0])
    assert row["sources"] == [
        {"via": "author_watch", "slack_ts": None, "url": row["url"],
         "at": row["sources"][0]["at"], "watch_author": "someone"}
    ]
    assert row["lifecycle"] == "active"


def test_two_routes_to_one_item_are_two_sources_not_one(tmp_path):
    """An item the watch found and someone also posted a link to arrived twice.

    Both are true, and without the route in the dedupe key they collapse
    whenever neither carries a message id -- which is most registrations.
    """
    ledger = pt.Ledger(path=Path("x"), rows=[], existed=True)
    pt.upsert_registration(ledger, link(GITHUB_PR), via="author_watch", slack_ts=None,
                           permalink=None, author=None, when=WHEN, watch_author="who")
    pt.upsert_registration(ledger, link(GITHUB_PR), via="url", slack_ts=None,
                           permalink=None, author=None, when=WHEN)
    assert len(ledger.rows) == 1
    assert [source["via"] for source in ledger.rows[0]["sources"]] == [
        "author_watch", "url"
    ]


def test_one_route_twice_is_still_one_source(tmp_path):
    ledger = pt.Ledger(path=Path("x"), rows=[], existed=True)
    for _ in range(2):
        pt.upsert_registration(ledger, link(GITHUB_PR), via="author_watch",
                               slack_ts=None, permalink=None, author=None,
                               when=WHEN, watch_author="who")
    assert len(ledger.rows[0]["sources"]) == 1


# ------------------------------------------------------- the watch's reply card


def test_render_watch_card_is_a_standalone_card_not_a_carousel():
    """One event, not one entity in a set: no carousel wrapper, no `elements`."""
    payload = carousel_fence(pt.render_watch_card(
        registered_count=0, tracked_count=0, repo_count=0, author_count=0
    ))
    assert len(payload["blocks"]) == 1
    block = payload["blocks"][0]
    assert block["type"] == "card"
    assert "elements" not in block


def test_render_watch_card_text_fields_are_objects_not_bare_strings():
    """Slack's own docs type these as `String`; a bare string is rejected with
    `invalid_blocks: must provide an object` -- confirmed against a live
    workspace. `title`, `body` and `subtext` must all be `mrkdwn` text objects."""
    block = carousel_fence(pt.render_watch_card(
        registered_count=2, tracked_count=10, repo_count=3, author_count=4
    ))["blocks"][0]
    for field in ("title", "body", "subtext"):
        assert isinstance(block[field], dict), f"{field} must be an object, not a bare string"
        assert block[field]["type"] == "mrkdwn"
        assert isinstance(block[field]["text"], str)


def test_render_watch_card_icon_is_eye_open_and_exclusive_with_icon():
    block = carousel_fence(pt.render_watch_card(
        registered_count=1, tracked_count=1, repo_count=1, author_count=1
    ))["blocks"][0]
    assert block["slack_icon"] == {"type": "icon", "name": "eye-open"}
    assert "icon" not in block, "slack_icon and icon are mutually exclusive"


def test_render_watch_card_zero_form_reads_no_new_items():
    block = carousel_fence(pt.render_watch_card(
        registered_count=0, tracked_count=12, repo_count=2, author_count=3
    ))["blocks"][0]
    assert block["body"]["text"] == "no new items"


def test_render_watch_card_non_zero_form_reads_n_new_items():
    block = carousel_fence(pt.render_watch_card(
        registered_count=7, tracked_count=12, repo_count=2, author_count=3
    ))["blocks"][0]
    assert block["body"]["text"] == "7 new items"


def test_render_watch_card_body_never_names_the_standing_counts():
    """`body` is only the count that changes day to day; `tracked`, `repo` and
    `author` counts are standing context and belong in `subtext`, not `body`,
    so a reader's eye lands on what moved rather than on numbers that rarely
    do."""
    block = carousel_fence(pt.render_watch_card(
        registered_count=0, tracked_count=99, repo_count=5, author_count=6
    ))["blocks"][0]
    assert "99" not in block["body"]["text"]
    assert "tracked" not in block["body"]["text"]


def test_render_watch_card_subtext_states_tracked_repo_and_author_counts():
    block = carousel_fence(pt.render_watch_card(
        registered_count=0, tracked_count=5, repo_count=1, author_count=1
    ))["blocks"][0]
    assert block["subtext"]["text"] == "5 tracked · 1 repo · 1 author"

    block = carousel_fence(pt.render_watch_card(
        registered_count=0, tracked_count=5, repo_count=2, author_count=2
    ))["blocks"][0]
    assert block["subtext"]["text"] == "5 tracked · 2 repos · 2 authors"


def test_watch_json_carries_a_reply_card_matching_this_runs_counts(tmp_path, monkeypatch, capsys):
    """`watch`'s own JSON, not a model composing the reply from a prompt
    instruction: everything about the shape is fully determined by this run's
    count and configuration."""
    state, list_file = watch_store(tmp_path)
    write_config(list_file, {"authors": ["alice", "bob"]})
    code = run_watch(
        monkeypatch,
        ["watch", "--state-file", str(state), "--channel", "C0B"],
        {"author:alice": search_result(101, 102, 103), "author:bob": search_result()},
    )
    result = json.loads(capsys.readouterr().out)
    assert code == 0
    assert len(result["registered"]) == 3

    block = carousel_fence(result["card"])["blocks"][0]
    assert block["type"] == "card"
    assert block["title"] == {"type": "mrkdwn", "text": "Author watch", "verbatim": False}
    assert block["body"]["text"] == "3 new items"
    # Fresh store: nothing was tracked before this run, so all three
    # registrations are what "3 tracked" counts. One configured repository,
    # two watched authors.
    assert block["subtext"]["text"] == "3 tracked · 1 repo · 2 authors"
    assert block["slack_icon"] == {"type": "icon", "name": "eye-open"}


def test_watch_json_zero_form_card_still_names_who_and_where_it_watched(tmp_path, monkeypatch, capsys):
    """The zero case is the one seen most mornings: it must read as cleanly as
    the non-zero one and must not go blank on the standing context either."""
    state, list_file = watch_store(tmp_path)
    write_config(list_file, {"authors": ["alice", "bob"]})
    run_watch(
        monkeypatch,
        ["watch", "--state-file", str(state), "--channel", "C0B"],
        {"author:alice": search_result(), "author:bob": search_result()},
    )
    result = json.loads(capsys.readouterr().out)
    assert result["registered"] == []

    block = carousel_fence(result["card"])["blocks"][0]
    assert block["body"]["text"] == "no new items"
    assert block["subtext"]["text"] == "0 tracked · 1 repo · 2 authors"


def test_watch_dry_run_carries_no_reply_card(tmp_path, monkeypatch, capsys):
    """`--dry-run` is the operator's own pre-flight read of
    `would_register_count`, never a run whose reply is sent anywhere -- so it
    gets no `card` to relay."""
    state, list_file = watch_store(tmp_path)
    write_config(list_file, {"authors": ["alice"]})
    run_watch(
        monkeypatch,
        ["watch", "--state-file", str(state), "--channel", "C0B", "--dry-run"],
        {"author:alice": search_result(101)},
    )
    result = json.loads(capsys.readouterr().out)
    assert result["would_register_count"] == 1
    assert "card" not in result


# --------------------------------------------------------- the first sighting


def test_a_login_this_store_has_never_seen_gets_the_open_sweep_only(
    tmp_path, monkeypatch, capsys
):
    """A landing from before the channel started watching is not news.

    An item already terminal when first seen has no delta to report and no
    lifecycle to run: it would arrive needing immediate retirement.
    """
    state, list_file = watch_store(tmp_path, runs=FROZEN_RUNS)
    write_config(list_file, {"authors": ["newcomer"]})
    calls = []
    run_watch(
        monkeypatch,
        ["watch", "--state-file", str(state), "--channel", "C0B",
         "--repo", WATCH_STORE_ROWS],
        {"is:open": search_result(2724)},
        calls=calls,
    )
    result = json.loads(capsys.readouterr().out)
    assert result["authors_first_seen"], "it says the login was new to this store"
    assert all("is:closed" not in query for query in calls), calls
    assert result["authors_searched"][0]["first_sight"] is True


def test_once_the_store_has_seen_an_author_the_closed_sweep_runs(
    tmp_path, monkeypatch, capsys
):
    """Steady state is what catches an item opened and landed between runs."""
    state, list_file = watch_store(tmp_path, runs=FROZEN_RUNS)
    write_config(list_file, {"authors": ["known"]})
    argv = ["watch", "--state-file", str(state), "--channel", "C0B",
            "--repo", WATCH_STORE_ROWS]
    run_watch(monkeypatch, argv, {"is:open": search_result(2724)})
    capsys.readouterr()

    calls = []
    run_watch(monkeypatch, argv, {"is:open": search_result(2724)}, calls=calls)
    result = json.loads(capsys.readouterr().out)
    assert any("is:closed" in query for query in calls), calls
    assert any("closed:>=" in query for query in calls), calls
    assert result["authors_first_seen"] == []


def test_a_row_refreshed_with_an_author_counts_as_having_seen_them():
    """An item tracked by link is still evidence the channel has seen the author."""
    assert pt.logins_already_watched([{"author_login": "Someone"}]) == {"someone"}
    assert pt.logins_already_watched(
        [{"sources": [{"via": "author_watch", "watch_author": "Other"}]}]
    ) == {"other"}
    assert pt.logins_already_watched([{"sources": [{"via": "url"}]}]) == set()


# ------------------------------------------------------------ failure modes


def test_an_unsearchable_login_is_never_folded_into_no_results(
    tmp_path, monkeypatch, capsys
):
    """An unknown login and a quiet week are indistinguishable in a total.

    A machine account addressed by its bare name, a renamed login and a typo all
    come back the same way, and every one of them silently registers nothing.
    """
    state, list_file = watch_store(tmp_path, runs=FROZEN_RUNS)
    write_config(list_file, {"authors": ["ghost", "real"]})
    monkeypatch.setenv("GITHUB_TOKEN", "x")

    def search(query, token, api_base, *, page=1, per_page=100):
        if "author:ghost" in query:
            raise pt.SearchRefused("the listed users cannot be searched")
        return (search_result(2724) if page == 1 and "is:open" in query else search_result()), {}

    monkeypatch.setattr(pt, "github_search", search)
    code = pt.main(["watch", "--state-file", str(state), "--channel", "C0B",
                    "--repo", WATCH_STORE_ROWS])
    captured = capsys.readouterr()
    result = json.loads(captured.out)

    assert code == 1, "a list that needs fixing is a failure, not a quiet run"
    assert [entry["author"] for entry in result["authors_unsearchable"]] == ["ghost"]
    assert len(result["registered"]) == 1, "the searchable author still registered"
    assert "ghost" in captured.err and "not the same as having opened nothing" in captured.err


def test_a_rate_limit_keeps_what_it_found_and_names_who_was_missed(
    tmp_path, monkeypatch, capsys
):
    """The search budget is a minute-long window, far tighter than the core API."""
    state, list_file = watch_store(tmp_path, runs=FROZEN_RUNS)
    write_config(list_file, {"authors": ["first", "second"]})
    monkeypatch.setenv("GITHUB_TOKEN", "x")

    def search(query, token, api_base, *, page=1, per_page=100):
        if "author:second" in query:
            raise pt.SearchRateLimited("rate limit exceeded", reset_epoch=None)
        return (search_result(2724) if "is:open" in query else search_result()), {}

    monkeypatch.setattr(pt, "github_search", search)
    code = pt.main(["watch", "--state-file", str(state), "--channel", "C0B",
                    "--repo", WATCH_STORE_ROWS])
    captured = capsys.readouterr()
    result = json.loads(captured.out)

    assert code == 1
    assert len(result["registered"]) == 1, "what was found before the wall is kept"
    assert result["authors_not_reached"] == ["second in openJiuwen-ai/jiuwenswarm"]
    assert "rate_limited" in result
    assert pt.runs_path(state).read_text(encoding="utf-8"), "still no watermark move"
    runs = json.loads(pt.runs_path(state).read_text(encoding="utf-8"))
    assert runs["completed_runs"] == 12


def test_a_rate_limit_that_refills_soon_is_waited_out_once(monkeypatch):
    """The window is a minute, so waiting beats abandoning half the authors."""
    slept = []
    calls = {"n": 0}
    reset = pt.now_utc().timestamp() + 5

    def search(query, token, api_base, *, page=1, per_page=100):
        calls["n"] += 1
        if calls["n"] == 1:
            raise pt.SearchRateLimited("rate limit", reset_epoch=reset)
        return search_result(2724), {}

    monkeypatch.setattr(pt, "github_search", search)
    found, outcome = pt.search_watch_target(
        target(state="open"), None, token="x", api_base="https://api",
        max_results=100, sleeper=slept.append,
    )
    assert len(slept) == 1 and 0 < slept[0] <= pt.GITHUB_SEARCH_MAX_WAIT_SECONDS
    assert len(found) == 1


def test_a_second_rate_limit_in_one_pass_is_raised_rather_than_slept_through(monkeypatch):
    """A budget this run does not fit inside is the caller's to know about.

    Sleeping through a second wall would strand the caller instead of telling
    it, and a scheduled run has a turn to finish inside.
    """
    reset = pt.now_utc().timestamp() + 5

    def always_limited(query, token, api_base, *, page=1, per_page=100):
        raise pt.SearchRateLimited("rate limit", reset_epoch=reset)

    monkeypatch.setattr(pt, "github_search", always_limited)
    slept = []
    with pytest.raises(pt.SearchRateLimited):
        pt.search_watch_target(
            target(state="open"), None, token="x", api_base="https://api",
            max_results=100, sleeper=slept.append,
        )
    assert len(slept) == 1, "it waits exactly once, then gives up"


def test_a_result_cut_short_says_it_was_cut(monkeypatch):
    """A partial answer that looks complete is the one wrong this store cannot
    detect later."""
    monkeypatch.setattr(
        pt, "github_search",
        lambda *a, **k: ({"total_count": 500, "incomplete_results": False,
                          "items": search_result(*range(1, 4))["items"]}, {}),
    )
    _, outcome = pt.search_watch_target(
        target(state="open"), None, token="x", api_base="https://api", max_results=2,
    )
    assert outcome["truncated"] is True
    assert outcome["found"] == 2


# --------------------------------------------- seeing the volume before it lands


def test_a_dry_run_says_what_would_register_and_writes_nothing(
    tmp_path, monkeypatch, capsys
):
    """A first run's volume is visible before it is committed, not after."""
    state, list_file = watch_store(tmp_path, runs=FROZEN_RUNS)
    write_config(list_file, {"authors": ["someone"]})
    before = state.read_bytes()
    code = run_watch(
        monkeypatch,
        ["watch", "--state-file", str(state), "--channel", "C0B",
         "--repo", WATCH_STORE_ROWS, "--dry-run"],
        {"is:open": search_result(2724, 2725)},
    )
    result = json.loads(capsys.readouterr().out)
    assert code == 0
    assert result["would_register_count"] == 2
    assert result["rows_before"] == 0 and result["rows_after"] == 2
    assert state.read_bytes() == before, "nothing was written"


def test_the_cap_declines_visibly_rather_than_truncating_silently(
    tmp_path, monkeypatch, capsys
):
    """A cap nobody can see the effect of is worse than no cap at all."""
    state, list_file = watch_store(tmp_path, runs=FROZEN_RUNS)
    write_config(list_file, {"authors": ["someone"]})
    code = run_watch(
        monkeypatch,
        ["watch", "--state-file", str(state), "--channel", "C0B",
         "--repo", WATCH_STORE_ROWS, "--max-new", "1"],
        {"is:open": search_result(2724, 2725)},
    )
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert code == 1, "declining items is a failure to report, not a quiet success"
    assert len(result["registered"]) == 1
    assert len(result["declined_over_cap"]) == 1
    assert "2725" in result["declined_over_cap"][0]
    assert "are not lost" in captured.err


# ------------------------------------------- what the report says about routes


def watched_row(**overrides):
    row = base_row(url="u1", number=1, repo="o/r", title_source="t1")
    row["sources"] = [{"via": "author_watch", "slack_ts": None, "url": "u1",
                       "at": WHEN, "watch_author": "who"}]
    row.update(overrides)
    return row


def test_a_store_with_no_watch_still_says_link_trigger_only():
    """The line describes this store, so it must not claim a route never used."""
    text = pt.render_report(context(), [], [], [], [], None, [])
    assert "Registration: link trigger only" in text


def test_a_watched_store_says_so_in_source_and_registration():
    """`Registration: link trigger only` becomes a lie the first time a watch
    runs, and that line exists precisely so a misconfigured store is visible."""
    text = pt.render_report(
        context(routes=("url", "author_watch")), [], [], [], [], None, []
    )
    section = text.split("*Source and registration*", 1)[1]
    assert "author watch" in section and "link is posted" in section
    assert "link trigger only" not in section
    assert "author_watch" not in text, "the store's vocabulary is not the reader's"


def test_the_newly_tracked_table_says_how_each_item_arrived():
    """"Twelve newly tracked" reads differently depending on whether twelve
    people asked or one sweep swept."""
    text = pt.render_report(context(routes=("author_watch",)), [watched_row()], [], [], [], None, [])
    table = text.split("*Newly tracked*", 1)[1]
    assert "author watch" in table


def test_the_route_is_not_repeated_on_every_later_run():
    """By the time an item is in *Changed*, how it arrived is settled history."""
    row = watched_row()
    text = pt.render_report(
        context(routes=("author_watch",)), [], [(row, [("conflicted", "went conflicted")])],
        [], [], None, [],
    )
    changed = text.split("*Changed*", 1)[1].split("<!--", 1)[0]
    assert "author watch" not in changed


def test_a_watched_store_says_what_the_watch_does_not_cover():
    text = pt.render_report(context(routes=("author_watch",)), [], [], [], [], None, [])
    coverage = text.split("*Coverage and gaps*", 1)[1]
    assert "nobody else" in coverage
    assert "closed before the watch first saw its author" in coverage


def test_an_author_watch_only_store_does_not_describe_the_link_trigger():
    """The coverage bullet must not name a route the registration line denies.

    On an author-watch-only store the registration line reads ``Registration:
    author watch only``. The coverage bullet above it used to describe the
    link trigger unconditionally, which is a route this store never ran --
    the two sections of the same report disagreeing about how items got in.
    """
    text = pt.render_report(context(routes=("author_watch",)), [], [], [], [], None, [])
    coverage = text.split("*Coverage and gaps*", 1)[1].split("*Source and registration*", 1)[0]
    assert "link trigger" not in coverage
    assert "Registration: author watch only" in text


def test_a_watch_alongside_the_link_trigger_still_describes_both():
    text = pt.render_report(
        context(routes=("author_watch", "url")), [], [], [], [], None, []
    )
    coverage = text.split("*Coverage and gaps*", 1)[1].split("*Source and registration*", 1)[0]
    assert "link trigger" in coverage
    assert "Registration: author watch and link posted" in text


def test_the_routes_line_is_read_off_the_store_not_off_the_configuration():
    """A watch that is configured and never ran does not get to say it did."""
    assert pt.store_routes([watched_row()]) == ["author_watch"]
    assert pt.store_routes([base_row(url="u", number=1, repo="o/r", sources=[
        {"via": "url"}])]) == ["url"]
    assert pt.store_routes([]) == []


# ------------------------------- the scheduler descriptions stay inside the cap
#
# A scheduler description is the one piece of text in this skill that is capped
# and, on at least one host, **dropped without an error when it exceeds the cap**
# -- so a description that grew by a sentence stops being installed at all and
# the job runs on whatever it had before. It is also the first thing a model
# reads, which makes it the place where the environment variable is either left
# alone or established, and establishing it has now broken a report.
#
# The descriptions live in a scheduler's own configuration, which is not in this
# repository, so what is guarded here is the copy `prompts.md` ships: it is what
# an operator pastes, and a hazard removed from a running job but left in the
# document comes back the next time somebody installs a channel.

SCHEDULER_DESCRIPTION_CAP = 500
SCHEDULER_MARKER = "<!-- scheduler-description -->"


def scheduler_descriptions():
    """(line number, text, the prose line introducing it) per marked block.

    Marked explicitly rather than inferred: `prompts.md` also carries the two
    long report prompts in `text` fences, and those are not capped by anything.

    The introducing line is the nearest non-empty line above the marker, and it
    is the only place a character count is read from. A count stated *after* a
    block cannot be attributed to it without ambiguity -- the next block's
    introduction sits there too.
    """
    lines = (SKILL_ROOT / "references" / "prompts.md").read_text(encoding="utf-8").splitlines()
    found = []
    index = 0
    while index < len(lines):
        if lines[index].strip() == SCHEDULER_MARKER:
            assert lines[index + 1].startswith("```"), "the marker precedes a fence"
            end = index + 2
            while end < len(lines) and not lines[end].startswith("```"):
                end += 1
            above = next(
                (lines[n] for n in range(index - 1, -1, -1) if lines[n].strip()), ""
            )
            found.append((index + 1, "\n".join(lines[index + 2:end]), above))
            index = end
        index += 1
    return found


def test_every_shipped_scheduler_description_fits_the_cap():
    descriptions = scheduler_descriptions()
    assert len(descriptions) >= 5, "the deltas, the rosters and the watch"
    too_long = [
        f"prompts.md:{lineno}: {len(text)} characters"
        for lineno, text, _ in descriptions
        if len(text) > SCHEDULER_DESCRIPTION_CAP
    ]
    assert not too_long, "\n".join(too_long)


def test_a_stated_character_count_is_the_real_one():
    """The counts in the prose are load-bearing: an operator budgets against them.

    Every description states its own, because they differ by the length of the
    channel name and a count copied from the block above is how one of them
    quietly stops being true.
    """
    wrong = []
    for lineno, text, above in scheduler_descriptions():
        claimed = re.search(r"(?:\bis|,)\s+(\d{3}) characters\b", above)
        if claimed is None:
            wrong.append(f"prompts.md:{lineno}: no character count stated above it")
        elif int(claimed.group(1)) != len(text):
            wrong.append(
                f"prompts.md:{lineno}: says {claimed.group(1)}, is {len(text)}"
            )
    assert not wrong, "\n".join(wrong)


def test_no_shipped_prompt_establishes_the_variable_it_is_written_in_terms_of():
    """The second half of this morning's failure, guarded where it was written.

    `export VAR=` produced an empty value, so `$VAR/agent/…` became `/agent/…`
    and the store was not found. Nothing in a prompt here ever needs to assign
    the variable -- it is set by whatever runs the command -- and each command is
    a fresh shell anyway, so an assignment could not survive to the next one even
    if it were right.
    """
    assignment = re.compile(r"(?:^|[;&|]\s*|\bexport\s+)([A-Z][A-Z0-9_]*)=")
    offences = []
    for path in shipped_docs():
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for name in assignment.findall(line):
                if name == "GITHUB_TOKEN":
                    continue  # a credential, named where a host sets one

                offences.append(f"{path.name}:{lineno}: assigns {name}: {line.strip()!r}")
    assert not offences, "\n".join(offences)


def test_every_scheduler_description_says_the_variable_is_already_set():
    """Each one has to carry it. A model reads one description, not all five."""
    missing = [
        f"prompts.md:{lineno}"
        for lineno, text, _ in scheduler_descriptions()
        if "$" in text
        and not ("already set" in text and "never export" in text.lower())
    ]
    assert not missing, missing


def test_the_assignment_guard_fires_on_what_broke_this_morning():
    """Including the form it actually arrived in: an assignment to nothing."""
    guard = test_no_shipped_prompt_establishes_the_variable_it_is_written_in_terms_of
    pattern = re.compile(r"(?:^|[;&|]\s*|\bexport\s+)([A-Z][A-Z0-9_]*)=")
    for hazard in (
        "export JIUWENSWARM_DATA_DIR=",
        "export JIUWENSWARM_DATA_DIR=/somewhere",
        "JIUWENSWARM_DATA_DIR=/somewhere python3 x.py",
        "cd /tmp; S=$JIUWENSWARM_DATA_DIR/agent",
    ):
        assert pattern.findall(hazard), hazard
    for benign in (
        "--state-file \"$JIUWENSWARM_DATA_DIR/agent/workspace\"",
        "read it as key=value",
        "--kind pull_request",
    ):
        assert not pattern.findall(benign), benign
    assert guard is not None


# --------------------------------------------------------- the --repo filter


def configured_store(tmp_path, monkeypatch, capsys):
    """A store with one registered item and a repository configuration beside it."""
    store = tmp_path / "C0BPLSPHHDZ.jsonl"
    assert pt.main(
        ["track", "--state-file", str(store), "--channel", "C0BPLSPHHDZ", "--url", GITHUB_PR]
    ) == 0
    pt.config_path(store).write_text(
        json.dumps(
            {
                "schema_version": 1,
                "repositories": {
                    "openJiuwen-ai/jiuwenswarm": {"gitcode": "openJiuwen/jiuwenswarm"},
                    "openJiuwen-ai/agent-core": {"gitcode": "openJiuwen/agent-core"},
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("GITHUB_TOKEN", "not-a-real-token")

    def stub_refresh(row, **kwargs):
        row.update({"refresh_ok": True, "title_source": "fix: resume", "head_sha": "abc"})

    monkeypatch.setattr(pt, "refresh_row", stub_refresh)
    capsys.readouterr()
    return store


def test_a_repo_matching_nothing_is_refused_rather_than_reported_as_quiet(
    tmp_path, monkeypatch, capsys
):
    """The failure this guards is a complete, plausible, entirely false report.

    The filter is exact, so a value naming no repository drops every row and
    renders a store full of open work as a channel with nothing to say -- which
    is precisely what a real quiet week renders as. The value that provoked this
    was a channel's name, invented rather than read off the configuration.
    """
    store = configured_store(tmp_path, monkeypatch, capsys)
    with pytest.raises(SystemExit) as refusal:
        pt.main(report_argv(store, "--repo", "open-jiuwen-repo"))
    message = str(refusal.value)
    assert "matches no repository" in message
    assert "openJiuwen-ai/jiuwenswarm" in message, "the refusal names what there is"
    assert "openJiuwen-ai/agent-core" in message
    assert "not a channel name" in message


def test_the_refusal_leaves_no_stream_behind_for_the_watermark_to_restart_from(
    tmp_path, monkeypatch, capsys
):
    """The second cost of an invented filter: a stream with no history.

    `--repo` names the watermark stream as well as the filter, so a value that
    matched nothing also opened a stream of its own -- and the report then said
    `since the first run` on a channel that had been reporting for weeks.
    """
    store = configured_store(tmp_path, monkeypatch, capsys)
    assert pt.main(report_argv(store, "--commit-after")) == 0
    capsys.readouterr()
    with pytest.raises(SystemExit):
        pt.main(report_argv(store, "--repo", "open-jiuwen-repo", "--run-id", "cron-2"))
    assert list(pt.read_runs(pt.runs_path(store))["streams"]) == ["all"]


def test_a_configured_repository_reports_exactly_as_before(tmp_path, monkeypatch, capsys):
    """The refusal is about values naming nothing; a real one is untouched."""
    store = configured_store(tmp_path, monkeypatch, capsys)
    assert pt.main(report_argv(store, "--repo", "openJiuwen-ai/jiuwenswarm")) == 0
    out = capsys.readouterr().out
    assert "repo: openJiuwen-ai/jiuwenswarm" in out
    assert "1 newly tracked" in out


def test_a_repository_a_row_names_is_accepted_without_being_configured(
    tmp_path, monkeypatch, capsys
):
    """A row can outlive the configuration entry it arrived under."""
    store = tmp_path / "C0BPLSPHHDZ.jsonl"
    assert pt.main(
        ["track", "--state-file", str(store), "--channel", "C0BPLSPHHDZ", "--url", GITHUB_PR]
    ) == 0
    monkeypatch.setenv("GITHUB_TOKEN", "not-a-real-token")
    monkeypatch.setattr(pt, "refresh_row", lambda row, **kwargs: row.update({"refresh_ok": True}))
    capsys.readouterr()
    assert pt.main(report_argv(store, "--repo", "openJiuwen-ai/jiuwenswarm")) == 0


def test_the_filter_is_rewritten_to_the_spelling_the_store_uses(
    tmp_path, monkeypatch, capsys
):
    """One name downstream, whatever case the caller typed, so the stream is stable."""
    store = configured_store(tmp_path, monkeypatch, capsys)
    assert pt.main(report_argv(store, "--repo", "OPENJIUWEN-AI/JIUWENSWARM")) == 0
    assert "repo: openJiuwen-ai/jiuwenswarm" in capsys.readouterr().out


def test_a_store_naming_no_repository_says_that_rather_than_listing_nothing(
    tmp_path, monkeypatch, capsys
):
    store = tmp_path / "C0BPLSPHHDZ.jsonl"
    store.write_text("", encoding="utf-8")
    monkeypatch.setenv("GITHUB_TOKEN", "not-a-real-token")
    with pytest.raises(SystemExit) as refusal:
        pt.main(report_argv(store, "--repo", "open-jiuwen-repo"))
    assert "no repository configured and no row naming one" in str(refusal.value)


# ------------------------------------------- the schema document is load-bearing
#
# `references/store-schema.md` is the only place a caller can learn what is in a
# row, and a caller who cannot learn it invents it. That is not a hypothetical:
# a question about how many tracked items had merged was answered by a `grep`
# for a `status` field this store has never had, which matched nothing and
# printed a `0` indistinguishable from a real count. The field that records a
# merge, `gh_merged_at`, appeared nowhere in the document at the time.
#
# So the document is tested like code. The guard below reads the field names out
# of it and fails when one of them is no longer a field the script writes --
# whether it was renamed, dropped, or was never real.

SCHEMA_DOC = SKILL_ROOT / "references" / "store-schema.md"


def documented_fields():
    """Every row field `store-schema.md` names, read out of the document.

    Two shapes, because the document uses two. The identity table names fields
    in its first column; the tracker-fact and reported-mirror paragraphs name
    them in a run of backticked words. Both are parsed rather than transcribed
    into a list here -- a list in this file would be a third place to keep in
    step, and the drift it is meant to catch would hide in it.
    """
    text = SCHEMA_DOC.read_text(encoding="utf-8")
    found = set()
    for heading in ("**Tracker facts**", "**Reported mirror**"):
        start = text.index(heading)
        end = text.index("\n\n", start)
        found |= set(re.findall(r"`([a-z][a-z0-9_]*)`", text[start:end]))
    for line in text.splitlines():
        if not line.startswith("| `"):
            continue
        first = line.split("|")[1]
        found |= set(re.findall(r"`([a-z][a-z0-9_]*)(?:\[\])?`", first))
    return found


def script_string_constants():
    """Every string literal in the script, which is where a field name lives."""
    tree = ast.parse(Path(pt.__file__).read_text(encoding="utf-8"))
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }


def test_the_schema_document_names_at_least_the_row_fields_it_used_to():
    """A floor on the parse, so a document that stopped matching fails loudly.

    Without it a change to the document's shape makes the guard below vacuous:
    it would find no fields, check none of them, and pass.
    """
    fields = documented_fields()
    assert len(fields) >= 40, sorted(fields)
    for expected in ("key", "url", "lifecycle", "gh_state", "gh_merged_at"):
        assert expected in fields, f"{expected} is no longer documented"


def test_every_field_the_schema_documents_is_one_the_script_writes():
    """The guard proper: a documented field that left the store fails here.

    A field name in the document and nowhere in the script is a promise to a
    reader that nothing keeps -- and a reader who acts on it writes a filter
    that matches nothing and reads the empty result as an answer.
    """
    constants = script_string_constants()
    missing = sorted(field for field in documented_fields() if field not in constants)
    assert not missing, (
        "store-schema.md documents fields the script never writes: "
        + ", ".join(missing)
    )


def test_the_documentation_guard_fires_on_a_field_that_disappeared():
    """It must fail when a documented name is gone, not merely pass today."""
    assert "no_such_field_at_all" not in script_string_constants()
    assert "gh_merged_at" in script_string_constants()


def test_the_merge_marker_and_the_states_it_is_confused_with_are_explained():
    """The three state-ish fields need more than a mention in a list.

    Each is easy to read as the other two, and the failure mode is silent: a
    count over the wrong one returns a number rather than an error.
    """
    text = SCHEMA_DOC.read_text(encoding="utf-8")
    for field in ("gh_merged_at", "gh_state", "merged_at", "lifecycle"):
        assert f"| `{field}`" in text or f"`{field}`," in text, field
    section = text[text.index("## The three fields that look like") :]
    section = section[: section.index("\n## ", 1)]
    for field in ("gh_state", "gh_merged_at", "merged_at", "lifecycle"):
        assert field in section, f"{field} is not explained beside the others"
    assert "never" in section and "closed" in section, (
        "the section must say that the tracker's state never holds 'merged'"
    )
    assert "--merged" in section, "it must say how to count merges instead"


def test_every_column_of_the_registration_table_reads_a_documented_field():
    """The table's promise is that the store already holds all nine columns.

    If a column read a field the schema does not document, the column would be
    the only record of it -- and the next reader would be back to guessing.
    """
    fields = documented_fields()
    for name, field in pt.REGISTRATION_COLUMNS:
        assert field in fields, f"column {name} reads undocumented field {field}"


def test_nothing_in_the_script_shells_out_to_a_tracker():
    """Registration and rendering never call a tracker CLI, so the table is free.

    The nine columns exist in the store; a run that shelled out for them would
    fetch what it was already holding, and would do it inside the turn a link
    trigger started.
    """
    source = Path(pt.__file__).read_text(encoding="utf-8")
    for forbidden in ("import subprocess", "subprocess.", "os.system", "gh pr view"):
        assert forbidden not in source, forbidden


# ------------------------------------------------- what merged, and what did not


def fact_row(**facts):
    """A row a refresh has touched, with whatever facts the test cares about."""
    row = {
        "key": "github/owner/name#pr1",
        "url": "https://github.com/owner/name/pull/1",
        "kind": "pull_request",
        "tracker": "github",
        "repo": "owner/name",
        "number": 1,
        "lifecycle": "active",
        "last_refresh_utc": WHEN,
        "refresh_ok": True,
    }
    row.update(facts)
    return row


def test_a_pull_request_merged_on_the_first_tracker_counts_as_merged():
    """`gh_merged_at` is the marker, and the state field is closed beside it."""
    row = fact_row(gh_state="closed", gh_merged_at="2026-08-06T06:18:13Z")
    assert pt.is_merged(row)
    assert pt.tracker_state(row) == "merged"


def test_closed_without_the_marker_is_not_merged():
    """The distinction the state field cannot make on its own."""
    row = fact_row(gh_state="closed", gh_merged_at=None)
    assert not pt.is_merged(row)
    assert pt.tracker_state(row) == "closed"


def test_the_second_trackers_merge_counts_too():
    for facts in ({"merged_at": WHEN}, {"mr_state": "merged"}):
        row = fact_row(gh_state="open", **facts)
        assert pt.is_merged(row), facts
        assert pt.tracker_state(row) == "merged"


def test_a_row_no_run_has_refreshed_has_no_state_rather_than_an_open_one():
    """Absent is not `open` and not `unmerged`; it is nobody having looked."""
    row = {"key": "k", "kind": "pull_request", "lifecycle": "active"}
    assert not pt.is_refreshed(row)
    assert not pt.is_merged(row)
    assert pt.tracker_state(row) == pt.CELL_NEVER_REFRESHED


def test_a_refreshed_row_the_tracker_said_nothing_about_reads_unknown():
    """The other way a cell can be empty, and it is a different fact."""
    assert pt.tracker_state(fact_row(gh_state=None)) == pt.CELL_UNKNOWN
    assert pt.CELL_UNKNOWN != pt.CELL_NEVER_REFRESHED


def test_a_draft_and_a_vanished_item_read_as_themselves():
    assert pt.tracker_state(fact_row(gh_state="open", draft=True)) == "draft"
    assert pt.tracker_state(fact_row(gh_state="open", gone=True)) == "gone"


def test_the_state_cell_never_carries_this_skills_own_vocabulary():
    """`registered`, `active` and `ignored` are facts about the tracking.

    A *State* column carrying one of them is the exact failure the column was
    specified to prevent, and it is the failure a model reaches for when the
    store has not told it anything else.
    """
    rows = [
        {"key": "a", "kind": "pull_request", "lifecycle": "active"},
        fact_row(gh_state="open", lifecycle="ignored"),
        fact_row(gh_state="closed", lifecycle="retired", gh_merged_at=WHEN),
    ]
    for row in rows:
        assert pt.tracker_state(row) not in {"registered", "active", "ignored", "retired"}


# --------------------------------------------------- the nine-column table


def test_the_table_has_the_nine_columns_in_the_stated_order():
    header = [name for name, _ in pt.REGISTRATION_COLUMNS]
    assert header == [
        "URL", "Tracker", "Repository", "Number", "Title", "Author", "State",
        "Created", "Last activity",
    ]
    rendered = pt.render_registration_table([fact_row()])
    assert rendered.splitlines()[0] == "| " + " | ".join(header) + " |"


def test_every_cell_comes_from_the_store():
    row = fact_row(
        title_rendered="a title",
        author_login="someone",
        gh_state="open",
        created_at="2026-08-01T00:00:00Z",
        last_activity_utc="2026-08-02T00:00:00Z",
    )
    assert pt.registration_cells(row) == (
        "https://github.com/owner/name/pull/1",
        "GitHub",
        "owner/name",
        "1",
        "a title",
        "someone",
        "open",
        "2026-08-01T00:00:00Z",
        "2026-08-02T00:00:00Z",
    )


def test_a_merged_item_shows_merged_although_the_state_field_says_closed():
    """The column is what a reader expects the tracker to mean by *State*."""
    row = fact_row(gh_state="closed", gh_merged_at=WHEN, title_rendered="t")
    assert pt.registration_cells(row)[6] == "merged"


def test_a_title_carrying_a_pipe_does_not_invent_a_tenth_column():
    """Titles are arbitrary text from a tracker, and one pipe ends the table."""
    row = fact_row(title_rendered="fix: a | b", author_login="x")
    rendered = pt.render_registration_table([row])
    body = rendered.splitlines()[2]
    header = rendered.splitlines()[0]
    cells = re.split(r"(?<!\\)\|", body)
    assert len(cells) == len(re.split(r"(?<!\\)\|", header))
    assert "\\|" in body, "the pipe survives, escaped, rather than being dropped"


def test_a_title_spanning_lines_stays_on_one_row():
    row = fact_row(title_rendered="first\nsecond")
    assert pt.registration_cells(row)[4] == "first second"


def test_a_very_long_title_is_cut_rather_than_pushing_the_row_off_the_side():
    row = fact_row(title_rendered="x" * 300)
    cell = pt.registration_cells(row)[4]
    assert len(cell) == pt.TABLE_TITLE_LIMIT
    assert cell.endswith("…")


def test_a_freshly_registered_row_says_which_kind_of_empty_each_cell_is():
    """Identity is known, the tracker facts are not, and the row says which.

    This is the shape of the url trigger's reply, so it is the case that has to
    read correctly: four columns filled from the registration and five saying
    that nobody has looked yet -- not blank, and not `unknown`, which would
    claim a tracker was asked.
    """
    row = {
        "key": "github/owner/name#pr7",
        "url": "https://github.com/owner/name/pull/7",
        "kind": "pull_request",
        "tracker": "github",
        "repo": "owner/name",
        "number": 7,
        "lifecycle": "active",
    }
    cells = pt.registration_cells(row)
    assert cells[:4] == ("https://github.com/owner/name/pull/7", "GitHub", "owner/name", "7")
    assert all(cell == pt.CELL_NEVER_REFRESHED for cell in cells[4:])


def test_the_second_tracker_is_named_as_itself():
    row = fact_row(tracker="gitcode", repo="group/project", number=9)
    assert pt.registration_cells(row)[1] == "GitCode"


def test_no_rows_renders_no_table_at_all():
    """An empty table is a header claiming a set that is not there."""
    assert pt.render_registration_table([]) == ""


# ----------------------------------------------- track --render-table


def track_argv(store, *extra):
    return [
        "track", "--state-file", str(store), "--channel", "C0BPLSPHHDZ", *extra
    ]


def test_render_table_prints_the_reply_under_the_json(tmp_path, capsys):
    store = tmp_path / "C0BPLSPHHDZ.jsonl"
    assert pt.main(track_argv(store, "--render-table", "--url", GITHUB_PR)) == 0
    out = capsys.readouterr().out
    # The JSON stays exactly where callers already read it, and the table comes
    # after it, so a caller told to reply with the table has one block to copy.
    document, table = out.split("\n}\n", 1)
    assert json.loads(document + "\n}")["rows"] == 1
    assert "| URL | Tracker | Repository | Number |" in table
    assert GITHUB_PR in table
    assert pt.CELL_NEVER_REFRESHED in table


def test_render_table_says_the_empty_cells_fill_themselves(tmp_path, capsys):
    """The instruction not to look them up sits beside the cells, not in a prompt."""
    store = tmp_path / "C0BPLSPHHDZ.jsonl"
    assert pt.main(track_argv(store, "--render-table", "--url", GITHUB_PR)) == 0
    out = capsys.readouterr().out
    assert "next report run" in out
    assert "Do not look them up" in out


def test_render_table_prints_no_table_for_links_that_are_not_trackable(tmp_path, capsys):
    """A table is the statement that these items are tracked, so there is none.

    Enforced here rather than asked for in a prompt: a rule a prompt merely
    states is one a reader can talk itself out of when the reply looks bare.
    """
    store = tmp_path / "C0BPLSPHHDZ.jsonl"
    assert pt.main(
        track_argv(store, "--render-table", "--url", "https://example.com/an-article")
    ) == 0
    out = capsys.readouterr().out
    assert "| URL |" not in out
    assert "not tracked: no pull request or issue link" in out
    assert "https://example.com/an-article" in out


def test_render_table_covers_only_what_this_run_registered(tmp_path, capsys):
    """The reply is about this message, not about the whole store."""
    store = tmp_path / "C0BPLSPHHDZ.jsonl"
    assert pt.main(track_argv(store, "--url", GITHUB_PR)) == 0
    capsys.readouterr()
    other = "https://github.com/owner/name/pull/4242"
    assert pt.main(track_argv(store, "--render-table", "--url", other)) == 0
    out = capsys.readouterr().out
    table = out[out.index("| URL |") :]
    assert other in table
    assert GITHUB_PR not in table


def test_without_the_flag_track_prints_exactly_what_it_always_did(tmp_path, capsys):
    store = tmp_path / "C0BPLSPHHDZ.jsonl"
    assert pt.main(track_argv(store, "--url", GITHUB_PR)) == 0
    out = capsys.readouterr().out
    assert "| URL |" not in out
    assert json.loads(out)["rows"] == 1


# ------------------------------------------------------------------ query


def stocked_store(tmp_path):
    """A store shaped like a real one: merged, closed, open and unrefreshed."""
    store = tmp_path / "C0BPLSPHHDZ.jsonl"
    rows = [
        fact_row(
            key="github/owner/name#pr1",
            url="https://github.com/owner/name/pull/1",
            number=1,
            gh_state="closed",
            gh_merged_at="2026-08-06T06:18:13Z",
            lifecycle="retired",
            title_rendered="the one that landed",
            author_login="someone",
        ),
        fact_row(
            key="github/owner/name#pr2",
            url="https://github.com/owner/name/pull/2",
            number=2,
            gh_state="closed",
            gh_merged_at=None,
            lifecycle="retired",
            title_rendered="the one that did not",
        ),
        fact_row(
            key="github/owner/name#pr3",
            url="https://github.com/owner/name/pull/3",
            number=3,
            gh_state="open",
            title_rendered="still going",
        ),
        fact_row(
            key="github/other/repo#issue9",
            url="https://github.com/other/repo/issues/9",
            number=9,
            kind="issue",
            repo="other/repo",
            gh_state="open",
            lifecycle="ignored",
            title_rendered="an issue nobody wants reported",
        ),
        {
            "key": "github/owner/name#pr4",
            "url": "https://github.com/owner/name/pull/4",
            "kind": "pull_request",
            "tracker": "github",
            "repo": "owner/name",
            "number": 4,
            "lifecycle": "active",
        },
    ]
    store.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8"
    )
    return store


def query_argv(store, *extra):
    return ["query", "--state-file", str(store), "--channel", "C0BPLSPHHDZ", *extra]


def test_how_many_have_merged_is_one_command_with_no_field_to_guess_at(tmp_path, capsys):
    """The question that made this necessary, answered without a field name."""
    store = stocked_store(tmp_path)
    assert pt.main(query_argv(store)) == 0
    out = capsys.readouterr().out
    assert "merged      1" in out
    assert "5 row(s) read" in out


def test_the_grep_that_failed_still_finds_nothing_and_query_finds_the_answer(tmp_path, capsys):
    """The regression, stated as the two answers side by side.

    No row of any real store matches `"status": "merged"`, because there is no
    `status` field. A caller counting that way gets `0`, and `0` looks like an
    answer. The point of the verb is that the same question asked of it cannot
    come back that way.
    """
    store = stocked_store(tmp_path)
    text = store.read_text(encoding="utf-8")
    assert '"status"' not in text
    assert '"gh_state": "merged"' not in text
    assert pt.main(query_argv(store, "--merged", "--format", "count")) == 0
    out = capsys.readouterr().out
    assert out.splitlines()[0] == "1"


def test_a_count_carries_the_store_and_the_row_count_under_it(tmp_path, capsys):
    """What makes a number checkable, and the only thing that separates
    "nothing matched" from "nothing was read"."""
    store = stocked_store(tmp_path)
    assert pt.main(query_argv(store, "--merged", "--format", "count")) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "1"
    assert "C0BPLSPHHDZ.jsonl" in lines[1]
    assert "5 row(s) read" in lines[1]
    assert "--merged" in lines[1], "the filter that produced it, echoed"


def test_a_store_that_is_not_there_is_refused_rather_than_counted(tmp_path, capsys):
    """Exit 2, `audit`'s code: nothing read is never printed as an answer of zero."""
    missing = tmp_path / "gone" / "C0BPLSPHHDZ.jsonl"
    assert pt.main(query_argv(missing, "--format", "count")) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "does not exist" in captured.err
    assert "not an answer of zero" in captured.err
    assert not missing.exists(), "it must not create the store it was pointed at"
    assert not missing.parent.exists(), "nor the directory a bad path named"


def test_the_refusal_points_at_the_prompt_rather_than_at_a_search(tmp_path, capsys):
    """The failure this replaces ended in a path retyped four ways in a loop."""
    assert pt.main(query_argv(tmp_path / "nowhere" / "C0BPLSPHHDZ.jsonl")) == 2
    err = capsys.readouterr().err
    assert "rather than searching for the file" in err


def test_nothing_matching_says_so_and_is_not_the_same_as_nothing_read(tmp_path, capsys):
    store = stocked_store(tmp_path)
    assert pt.main(query_argv(store, "--status", "cla_pending", "--format", "table")) == 0
    out = capsys.readouterr().out
    assert "0 matched" in out
    assert "5 row(s) read" in out
    assert "not a missing file" in out


def test_each_filter_narrows_by_the_field_it_is_named_after(tmp_path, capsys):
    store = stocked_store(tmp_path)
    for flag, value, expected in (
        ("--lifecycle", "ignored", 1),
        ("--lifecycle", "retired", 2),
        ("--gh-state", "open", 2),
        ("--kind", "issue", 1),
        ("--repo", "other/repo", 1),
    ):
        capsys.readouterr()
        assert pt.main(query_argv(store, flag, value, "--format", "count")) == 0
        assert capsys.readouterr().out.splitlines()[0] == str(expected), (flag, value)


def test_unmerged_is_the_complement_of_merged(tmp_path, capsys):
    store = stocked_store(tmp_path)
    counts = []
    for flag in ("--merged", "--unmerged"):
        capsys.readouterr()
        assert pt.main(query_argv(store, flag, "--format", "count")) == 0
        counts.append(int(capsys.readouterr().out.splitlines()[0]))
    assert sum(counts) == 5


def test_a_repeated_filter_widens_it(tmp_path, capsys):
    store = stocked_store(tmp_path)
    assert pt.main(
        query_argv(store, "--lifecycle", "retired", "--lifecycle", "ignored",
                   "--format", "count")
    ) == 0
    assert capsys.readouterr().out.splitlines()[0] == "3"


def test_the_census_separates_the_trackers_state_from_this_skills(tmp_path, capsys):
    """The two are one line apart, so each must say which it is."""
    store = stocked_store(tmp_path)
    assert pt.main(query_argv(store)) == 0
    out = capsys.readouterr().out
    assert "gh_state" in out and "the tracker's own state" in out
    assert "lifecycle" in out and "this skill's tracking state" in out
    assert "never 'merged'" in out


def test_the_census_says_when_rows_have_no_facts_yet(tmp_path, capsys):
    store = stocked_store(tmp_path)
    assert pt.main(query_argv(store)) == 0
    out = capsys.readouterr().out
    assert "never been refreshed" in out
    assert "absent rather than false" in out


def test_the_table_format_renders_the_same_nine_columns(tmp_path, capsys):
    store = stocked_store(tmp_path)
    assert pt.main(query_argv(store, "--merged", "--format", "table")) == 0
    out = capsys.readouterr().out
    assert "| URL | Tracker | Repository | Number |" in out
    assert "the one that landed" in out
    assert "the one that did not" not in out


def test_the_table_says_how_many_rows_it_left_out(tmp_path, capsys):
    store = stocked_store(tmp_path)
    assert pt.main(query_argv(store, "--format", "table", "--limit", "2")) == 0
    out = capsys.readouterr().out
    assert "3 further matched row(s) are not shown" in out
    assert "--limit" in out


def test_the_json_format_carries_the_provenance_too(tmp_path, capsys):
    store = stocked_store(tmp_path)
    assert pt.main(query_argv(store, "--format", "json")) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["store"] == "C0BPLSPHHDZ.jsonl"
    assert payload["rows_read"] == 5
    assert payload["merged"] == 1
    assert len(payload["items"]) == 5
    landed = next(item for item in payload["items"] if item["number"] == 1)
    assert landed["merged"] is True
    assert landed["gh_state"] == "closed", "the raw field, unaltered"


def test_query_writes_nothing_at_all(tmp_path, capsys):
    """Read-only in the strong sense: no rewrite, no sidecar, no lock file."""
    store = stocked_store(tmp_path)
    before = store.read_bytes()
    existing = {path.name for path in tmp_path.iterdir()}
    for extra in (("--format", "count"), ("--format", "table"), ("--format", "json"), ()):
        assert pt.main(query_argv(store, *extra)) == 0
    capsys.readouterr()
    assert store.read_bytes() == before
    assert {path.name for path in tmp_path.iterdir()} == existing


def test_query_refuses_a_store_belonging_to_another_channel(tmp_path, capsys):
    """The check that catches a right-looking path for the wrong channel."""
    store = stocked_store(tmp_path)
    pt.write_runs(pt.runs_path(store), {"schema_version": 1, "channel_id": "C0OTHER"})
    with pytest.raises(SystemExit) as refusal:
        pt.main(query_argv(store))
    assert "belongs to channel C0OTHER" in str(refusal.value)


def test_an_unparseable_line_is_reported_rather_than_counted_quietly(tmp_path, capsys):
    store = stocked_store(tmp_path)
    with store.open("a", encoding="utf-8") as handle:
        handle.write("{not json at all\n")
    assert pt.main(query_argv(store, "--format", "count")) == 0
    captured = capsys.readouterr()
    assert captured.out.splitlines()[0] == "5"
    assert "unparseable ledger line(s) at 6" in captured.err
