"""The refusals that stop a run recording something it should not.

Every gate here exists because the enforcement it replaces was a sentence in
SKILL.md that a run declined to act on. So each test asserts the same two
things: the command refuses, and the profile is left in a state the next run can
still reason about.

Covered:

- `record-run` after a refused `add`. The refusal writes nothing, which leaves
  the profile indistinguishable from one that never ran, and stamping it anyway
  gave the next run a one-day window that dropped everything the digest covered.
- A suppression marker that contradicts the link check's receipt. `duplicate_of`
  and `reason` exempt an item from both gates on the grounds that no reader saw
  it; the receipt is built from the digest's own links, so it settles whether
  that is true.
- Working files inside the skill directory. That path is shared by every run and
  replaced by a deploy, and a link check has already validated one run's digest
  against another run's file.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SKILL = (
    Path(__file__).resolve().parents[3] / "local_skills" / "ai-news-monitor"
)
LEDGER = SKILL / "scripts" / "ledger.py"
CHECK_LINKS = SKILL / "scripts" / "check_links.py"


def run(script: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True,
        text=True,
        timeout=60,
    )


@pytest.fixture
def store(tmp_path: Path) -> Path:
    return tmp_path / "store"


def ledger(store: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return run(LEDGER, "--profile", "test", "--home", str(store), *args)


def last_run(store: Path) -> str:
    return ledger(store, "since").stdout.strip()


def state(store: Path) -> dict:
    """The profile's state file, or {} before anything has written one."""
    path = store / "test" / "state.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


@pytest.fixture
def published(tmp_path: Path) -> Path:
    """An item that claims to have been shown to a reader."""
    path = tmp_path / "reported.json"
    path.write_text(
        json.dumps(
            [{"url": "https://vendor.test/a", "title": "A post", "date": "2026-08-10"}]
        ),
        encoding="utf-8",
    )
    return path


@pytest.fixture
def receipt(tmp_path: Path) -> Path:
    """A receipt vouching for the URL the digest cited.

    Produced by running the check, never assembled here. A receipt is the output
    of a check; a test that writes its own would be asserting against a schema
    nothing emits — which is exactly the move `add` now refuses, and the move a
    real run made when its check came back empty.
    """
    digest = tmp_path / "digest.md"
    digest.write_text(
        "### A post\n- **URL:** https://vendor.test/a\n", encoding="utf-8"
    )
    retrieved = tmp_path / "retrieved-urls.txt"
    retrieved.write_text("https://vendor.test/a\n", encoding="utf-8")

    r = run(
        CHECK_LINKS, str(digest), "--retrieved", str(retrieved), "--offline", "--json"
    )
    assert r.returncode == 0, r.stderr

    path = tmp_path / "link-check.json"
    path.write_text(r.stdout, encoding="utf-8")
    return path


# --------------------------------------------------------------- record-run


def test_record_run_refuses_after_a_refused_add(store: Path, published: Path) -> None:
    """The sequence that corrupted the next run's window."""
    refused = ledger(store, "add", "--input", str(published))
    assert refused.returncode == 1
    assert last_run(store) == "never"

    r = ledger(store, "record-run")

    assert r.returncode == 1, r.stdout
    assert "refused" in r.stderr
    assert last_run(store) == "never", "the clock moved over an unrecorded digest"


def test_record_run_stamps_a_profile_that_simply_reported_nothing(store: Path) -> None:
    """The case it is for: no refusal outstanding, so the window advances."""
    r = ledger(store, "record-run")

    assert r.returncode == 0, r.stderr
    assert last_run(store) != "never"


def test_a_successful_add_clears_the_refusal(store: Path, published: Path, tmp_path: Path) -> None:
    """Recovery is an `add`, whether the items are fixed or suppressed."""
    ledger(store, "add", "--input", str(published))

    suppressed = tmp_path / "suppressed.json"
    suppressed.write_text(
        json.dumps(
            [
                {
                    "url": "https://vendor.test/a",
                    "title": "A post",
                    "date": "2026-08-10",
                    "reason": "not going out after all",
                }
            ]
        ),
        encoding="utf-8",
    )
    assert ledger(store, "add", "--input", str(suppressed)).returncode == 0

    assert ledger(store, "record-run").returncode == 0


# ------------------------------------------------------------- suppressions


def test_a_suppression_the_digest_cited_is_refused(
    store: Path, receipt: Path, tmp_path: Path
) -> None:
    """Relabelling a published item does not make it one nobody saw."""
    laundered = tmp_path / "laundered.json"
    laundered.write_text(
        json.dumps(
            [
                {
                    "url": "https://vendor.test/a",
                    "title": "A post",
                    "date": "2026-08-10",
                    "reason": "relabelled to get past the refusal",
                }
            ]
        ),
        encoding="utf-8",
    )

    r = ledger(store, "add", "--input", str(laundered), "--verified", str(receipt))

    assert r.returncode == 1, r.stdout
    assert "cited in the checked digest" in r.stderr
    assert last_run(store) == "never"


def test_an_out_of_window_suppression_still_records(
    store: Path, receipt: Path, tmp_path: Path
) -> None:
    """The recipe the exemption exists for, which the check must not disturb.

    A stale story recorded with `reason` is what stops it costing a judgement
    call every week. Its URL is not in the receipt, because it is not in the
    digest -- which is exactly the difference the check reads.
    """
    mixed = tmp_path / "mixed.json"
    mixed.write_text(
        json.dumps(
            [
                {"url": "https://vendor.test/a", "title": "A post", "date": "2026-08-10"},
                {
                    "url": "https://vendor.test/old",
                    "title": "Settled weeks ago",
                    "date": "2020-01-01",
                    "reason": "out of window: disclosed long before this window",
                },
            ]
        ),
        encoding="utf-8",
    )

    r = ledger(
        store, "add", "--input", str(mixed), "--verified", str(receipt),
        "--window-start", "2026-08-04", "--window-end", "2026-08-11",
    )

    assert r.returncode == 0, r.stderr
    status = json.loads(ledger(store, "status").stdout)
    assert (status["items_published"], status["items_suppressed"]) == (1, 1)


# ----------------------------------------------------------------- the receipt


def test_a_receipt_in_a_foreign_schema_is_refused_by_name(
    store: Path, published: Path, tmp_path: Path
) -> None:
    """The refusal that printed a URL and then nothing.

    A run hand-wrote a receipt with `status` where `verdict` belongs. Every
    lookup returned the empty string, which is not a usable verdict, so `add`
    refused correctly — and printed each URL followed by a bare colon. The
    refusal was right and unreadable, so the run went looking for a fault in its
    items rather than in its receipt.
    """
    fake = tmp_path / "link-check.json"
    fake.write_text(
        json.dumps(
            {
                "tool": "check_links",
                "receipt_version": 1,
                "files": [{"name": "digest.md", "sha256": "0" * 64}],
                "provenance_checked": True,
                "results": [{"url": "https://vendor.test/a", "status": "ok"}],
            }
        ),
        encoding="utf-8",
    )

    r = ledger(store, "add", "--input", str(published), "--verified", str(fake))

    assert r.returncode == 1, r.stdout
    assert "no verdict this ledger recognises" in r.stderr
    assert "status" in r.stderr, "the message must name the keys it did find"
    # The failure is the receipt, not the item: nothing here judges the link.
    assert "provenance not established" not in r.stderr
    assert last_run(store) == "never"


def test_a_receipt_that_does_not_identify_itself_is_refused(
    store: Path, published: Path, tmp_path: Path
) -> None:
    """Well-formed verdicts are not enough; the file must be a check's output."""
    typed = tmp_path / "link-check.json"
    typed.write_text(
        json.dumps(
            {
                "provenance_checked": True,
                "results": [
                    {"url": "https://vendor.test/a", "verdict": "OK", "detail": "200"}
                ],
            }
        ),
        encoding="utf-8",
    )

    r = ledger(store, "add", "--input", str(published), "--verified", str(typed))

    assert r.returncode == 1, r.stdout
    assert "does not identify itself" in r.stderr
    assert last_run(store) == "never"


def test_a_receipt_naming_no_files_is_refused(
    store: Path, published: Path, receipt: Path, tmp_path: Path
) -> None:
    """A receipt says which digest it read, or it vouches for nothing."""
    stripped = json.loads(receipt.read_text(encoding="utf-8"))
    del stripped["files"]
    path = tmp_path / "stripped.json"
    path.write_text(json.dumps(stripped), encoding="utf-8")

    r = ledger(store, "add", "--input", str(published), "--verified", str(path))

    assert r.returncode == 1, r.stdout
    assert "names no files" in r.stderr


def test_a_real_receipt_records_the_run(
    store: Path, published: Path, receipt: Path
) -> None:
    """The gate must still pass what the check actually wrote."""
    r = ledger(
        store, "add", "--input", str(published), "--verified", str(receipt),
        "--window-start", "2026-08-04", "--window-end", "2026-08-11",
    )

    assert r.returncode == 0, r.stderr
    assert last_run(store) != "never"


# --------------------------------------------- a verdict versus a broken gate


def test_a_missing_receipt_file_does_not_latch_a_refusal(
    store: Path, published: Path, tmp_path: Path
) -> None:
    """The run that recorded a provenance verdict over a dropped shell redirect.

    `check_links.py` was run without `> link-check.json`, so it printed the
    receipt to the terminal and left no file behind, exiting zero. `add` was
    handed the path anyway. The read failed, and a blanket `except SystemExit`
    latched `refused_at` as though the gate had judged two items unverifiable.

    Nothing had judged anything. The marker then blocked `record-run` on every
    later run, so a week with no news could not stamp, `last_run` stopped
    advancing, and the window stopped narrowing.
    """
    missing = tmp_path / "link-check.json"
    assert not missing.exists()

    r = ledger(store, "add", "--input", str(published), "--verified", str(missing))

    assert r.returncode == 1, r.stdout
    assert str(missing) in r.stderr, "the message must name the file"
    assert "no such file" in r.stderr.lower(), "and say what was wrong with it"
    # The items were never assessed, so nothing is recorded about them.
    assert "refused_at" not in state(store)
    assert last_run(store) == "never"

    # The consequence that made it expensive: a quiet run could no longer stamp.
    assert ledger(store, "record-run").returncode == 0


def _mutate(receipt: Path, tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / f"{name}.json"
    path.write_text(body, encoding="utf-8")
    return path


@pytest.mark.parametrize(
    "name, build",
    [
        ("unparseable", lambda d: "{ this is not json"),
        ("a bare list of results", lambda d: json.dumps(d["results"])),
        ("some other tool's output", lambda d: json.dumps({**d, "tool": "curl"})),
        ("a version this ledger cannot read", lambda d: json.dumps({**d, "receipt_version": 99})),
        ("no files", lambda d: json.dumps({k: v for k, v in d.items() if k != "files"})),
        ("a files entry with no sha256", lambda d: json.dumps({**d, "files": [{"name": "digest.md"}]})),
        ("a check run without --retrieved", lambda d: json.dumps({**d, "provenance_checked": False})),
        (
            "a verdict this ledger does not know",
            lambda d: json.dumps({**d, "results": [{**d["results"][0], "verdict": "PROBABLY"}]}),
        ),
    ],
)
def test_an_unreadable_receipt_does_not_latch_a_refusal(
    store: Path, published: Path, receipt: Path, tmp_path: Path, name: str, build
) -> None:
    """Every way a receipt can be unusable is a broken gate, not a verdict.

    These all failed the same way as the missing file, for the same reason: the
    gate could not read what it was given, so it said nothing about the items —
    and the blanket catch wrote a verdict on them regardless. The script's own
    messages already draw this distinction ("a malformed receipt, not a bad
    link"); the state it left did not.
    """
    good = json.loads(receipt.read_text(encoding="utf-8"))
    path = _mutate(receipt, tmp_path, name.replace(" ", "-"), build(good))

    r = ledger(store, "add", "--input", str(published), "--verified", str(path))

    assert r.returncode == 1, r.stdout
    assert str(path) in r.stderr, "the message must name the file it could not use"
    assert "refused_at" not in state(store), f"{name} latched a provenance verdict"
    assert last_run(store) == "never"
    assert ledger(store, "record-run").returncode == 0


def test_an_unusable_window_flag_does_not_latch_a_refusal(
    store: Path, published: Path, receipt: Path
) -> None:
    """`resolve_window` runs inside the same guard, and it also has usage errors."""
    r = ledger(
        store, "add", "--input", str(published), "--verified", str(receipt),
        "--window-start", "last tuesday",
    )

    assert r.returncode == 1, r.stdout
    assert "is not a date" in r.stderr
    assert "refused_at" not in state(store)
    assert ledger(store, "record-run").returncode == 0


def test_a_receipt_inside_the_skill_directory_does_not_latch_a_refusal(
    skill_copy: Path, store: Path, published: Path
) -> None:
    """The working-file guard fires inside the gate too, and judges no item."""
    stray = skill_copy / "candidates" / "link-check.json"
    stray.write_text("{}", encoding="utf-8")

    r = run(
        skill_copy / "scripts" / "ledger.py",
        "--profile", "test", "--home", str(store),
        "add", "--input", str(published), "--verified", str(stray),
    )

    assert r.returncode == 1, r.stdout
    assert "inside the skill directory" in r.stderr
    assert "refused_at" not in state(store)


def _no_receipt(published: Path, receipt: Path, tmp_path: Path) -> list[str]:
    return ["add", "--input", str(published)]


def _unvouched_url(published: Path, receipt: Path, tmp_path: Path) -> list[str]:
    path = tmp_path / "unvouched.json"
    path.write_text(
        json.dumps(
            [{"url": "https://vendor.test/never-checked", "title": "X", "date": "2026-08-10"}]
        ),
        encoding="utf-8",
    )
    return ["add", "--input", str(path), "--verified", str(receipt)]


def _out_of_window(published: Path, receipt: Path, tmp_path: Path) -> list[str]:
    return [
        "add", "--input", str(published), "--verified", str(receipt),
        "--window-start", "2026-08-11", "--window-end", "2026-08-12",
    ]


def _contradicted_suppression(published: Path, receipt: Path, tmp_path: Path) -> list[str]:
    path = tmp_path / "laundered.json"
    path.write_text(
        json.dumps(
            [
                {
                    "url": "https://vendor.test/a",
                    "title": "A post",
                    "date": "2026-08-10",
                    "reason": "relabelled to get past the refusal",
                }
            ]
        ),
        encoding="utf-8",
    )
    return ["add", "--input", str(path), "--verified", str(receipt)]


@pytest.mark.parametrize(
    "case",
    [_no_receipt, _unvouched_url, _out_of_window, _contradicted_suppression],
    ids=["nothing vouches for it", "url not in the receipt", "out of window", "cited suppression"],
)
def test_a_gate_verdict_still_latches(
    store: Path, published: Path, receipt: Path, tmp_path: Path, case
) -> None:
    """The four sites that judge items must go on blocking `record-run`.

    Narrowing what `add` catches is only safe if it still catches these. Each
    one assessed the items and found them wanting, which is the case the marker
    exists for: the run produced a digest and recorded none of it, and stamping
    over that gives the next run a one-day window.
    """
    r = ledger(store, *case(published, receipt, tmp_path))

    assert r.returncode == 1, r.stdout
    assert state(store).get("refused_at"), "a real refusal stopped being remembered"
    assert last_run(store) == "never"

    stamped = ledger(store, "record-run")
    assert stamped.returncode == 1, stamped.stdout
    assert "refused" in stamped.stderr


# ------------------------------------------------------------- the whole gate


def test_a_bare_url_digest_records_and_narrows_the_next_window(
    store: Path, tmp_path: Path
) -> None:
    """Check, record, and a following run that sees a shorter window.

    The failure this reproduces end to end: a digest citing bare URLs passed a
    check that had found nothing, every item was refused, `last_run` never
    moved, and the next run swept the same seven days again.
    """
    digest = tmp_path / "digest.md"
    digest.write_text(
        "### A post\n- **URL:** https://vendor.test/a\n"
        "### Another\n- **URL:** https://vendor.test/b\n",
        encoding="utf-8",
    )
    retrieved = tmp_path / "retrieved-urls.txt"
    retrieved.write_text("https://vendor.test/a\nhttps://vendor.test/b\n", encoding="utf-8")
    reported = tmp_path / "reported.json"
    reported.write_text(
        json.dumps(
            [
                {"url": "https://vendor.test/a", "title": "A post", "date": "2026-08-10"},
                {"url": "https://vendor.test/b", "title": "Another", "date": "2026-08-10"},
            ]
        ),
        encoding="utf-8",
    )

    check = run(
        CHECK_LINKS, str(digest), "--retrieved", str(retrieved), "--offline", "--json"
    )
    assert check.returncode == 0, check.stderr
    link_check = tmp_path / "link-check.json"
    link_check.write_text(check.stdout, encoding="utf-8")

    recorded = ledger(
        store, "add", "--input", str(reported), "--verified", str(link_check),
        "--window-start", "2026-08-04", "--window-end", "2026-08-11",
    )
    assert recorded.returncode == 0, recorded.stderr

    stamped = last_run(store)
    assert stamped != "never"

    # The following run: the window now starts at the stamp, and the items this
    # digest carried are already known.
    following = ledger(store, "new", "--input", str(reported), "--verbose")
    assert following.returncode == 0, following.stderr
    assert json.loads(following.stdout)["new"] == []
    assert "from this profile's last run" in following.stderr

    # And a quiet run after that still advances the clock. The stamps are ISO
    # UTC to the second, so two calls in the same second compare equal — what
    # matters is that it never goes backwards and never returns to `never`.
    assert ledger(store, "record-run").returncode == 0
    assert last_run(store) >= stamped


# ------------------------------------------------------- the skill directory


@pytest.fixture
def skill_copy(tmp_path: Path) -> Path:
    """A copy of the skill, so a test can put files inside it safely."""
    dest = tmp_path / "skill"
    shutil.copytree(SKILL, dest)
    (dest / "candidates").mkdir()
    return dest


def test_ledger_refuses_an_input_inside_the_skill_directory(
    skill_copy: Path, store: Path
) -> None:
    stray = skill_copy / "candidates" / "candidates.json"
    stray.write_text(json.dumps([{"url": "https://vendor.test/a"}]), encoding="utf-8")

    r = run(
        skill_copy / "scripts" / "ledger.py",
        "--profile", "test", "--home", str(store), "new", "--input", str(stray),
    )

    assert r.returncode == 1, r.stdout
    assert "inside the skill directory" in r.stderr


def test_check_links_refuses_a_digest_inside_the_skill_directory(
    skill_copy: Path,
) -> None:
    """The exact layout behind the wrong-digest failure."""
    digest = skill_copy / "candidates" / "digest.md"
    digest.write_text("[A post](https://vendor.test/a)\n", encoding="utf-8")
    retrieved = skill_copy / "candidates" / "retrieved-urls.txt"
    retrieved.write_text("https://vendor.test/a\n", encoding="utf-8")

    r = run(
        skill_copy / "scripts" / "check_links.py",
        str(digest), "--retrieved", str(retrieved), "--offline", "--json",
    )

    assert r.returncode == 2, r.stdout
    assert "inside the skill directory" in r.stderr
    assert str(digest) in r.stderr and str(retrieved) in r.stderr


def test_the_same_files_outside_the_skill_directory_are_fine(
    skill_copy: Path, tmp_path: Path
) -> None:
    """The guard must not fire on the documented per-run directory."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    digest = run_dir / "digest.md"
    digest.write_text("[A post](https://vendor.test/a)\n", encoding="utf-8")
    retrieved = run_dir / "retrieved-urls.txt"
    retrieved.write_text("https://vendor.test/a\n", encoding="utf-8")

    r = run(
        skill_copy / "scripts" / "check_links.py",
        str(digest), "--retrieved", str(retrieved), "--offline", "--json",
    )

    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["results"][0]["verdict"] == "OK"
