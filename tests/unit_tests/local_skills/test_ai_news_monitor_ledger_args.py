"""`--profile` and `--home` are accepted on either side of the subcommand.

Registered only on the top-level parser, they read as global options but
argparse rejected them after the subcommand with a bare "unrecognized
arguments", naming no position that would work. Every documented example writes
the subcommand first, so putting the flag after it is the natural guess.

A run hit this on `new --profile test`, retried four times, and then recovered by
dropping `--profile` rather than moving it -- which succeeded, and wrote to the
`default` store instead of the one it had been asked for. Silently addressing the
wrong ledger is worse than the error, since the ledger decides what a later run
suppresses as already reported.

These tests therefore assert both halves: the invocation now succeeds, and the
store it writes is the one named.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[3]
    / "local_skills"
    / "ai-news-monitor"
    / "scripts"
    / "ledger.py"
)


@pytest.fixture
def store(tmp_path: Path) -> Path:
    """An isolated store root, so no test touches real ledger state."""
    return tmp_path / "store"


@pytest.fixture
def items(tmp_path: Path) -> Path:
    """One item, recorded as a suppression.

    These tests are about where `--profile` and `--home` may appear, not about
    the gates. `add` refuses to record a *published* item without the link
    check's receipt, so a published item here would make every one of them fail
    on a condition none of them is asking about. An item carrying `reason` needs
    no receipt — it was never shown to a reader — which keeps the subject of the
    test the flag position.
    """
    path = tmp_path / "candidates.json"
    path.write_text(
        json.dumps(
            [
                {
                    "url": "https://vendor.test/a",
                    "title": "A post",
                    "beat": "inference",
                    "reason": "out of window: settled before this window opened",
                }
            ]
        ),
        encoding="utf-8",
    )
    return path


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_profile_after_subcommand_is_accepted(store: Path, items: Path) -> None:
    """The exact invocation that failed."""
    r = run("new", "--input", str(items), "--profile", "test", "--home", str(store))

    assert r.returncode == 0, r.stderr
    assert "unrecognized arguments" not in r.stderr


def test_profile_after_subcommand_writes_the_named_store(
    store: Path, items: Path
) -> None:
    """The half that matters: not merely accepted, but addressed correctly."""
    r = run(
        "add", "--input", str(items), "--profile", "test", "--home", str(store),
        "--window", "7d",
    )

    assert r.returncode == 0, r.stderr
    assert (store / "test" / "ledger.jsonl").exists()
    # The failure mode this replaces: succeeding against the wrong ledger.
    assert not (store / "default").exists()


def test_profile_before_subcommand_still_works(store: Path, items: Path) -> None:
    r = run(
        "--profile", "test", "--home", str(store), "add", "--input", str(items)
    )

    assert r.returncode == 0, r.stderr
    assert (store / "test" / "ledger.jsonl").exists()


def test_omitting_profile_still_means_default(store: Path, items: Path) -> None:
    """Suppressed subparser defaults must not disturb the resolved value."""
    r = run("add", "--input", str(items), "--home", str(store))

    assert r.returncode == 0, r.stderr
    assert (store / "default" / "ledger.jsonl").exists()


@pytest.mark.parametrize(
    "argv",
    [
        ("status",),
        ("since",),
        ("record-run",),
        ("recent",),
        ("config",),
    ],
)
def test_every_subcommand_takes_the_flags_after_it(
    store: Path, argv: tuple[str, ...]
) -> None:
    """A fix on only the subcommand that happened to fail would leave the trap."""
    r = run(*argv, "--profile", "test", "--home", str(store))

    assert r.returncode == 0, r.stderr
    assert "unrecognized arguments" not in r.stderr


def test_forget_takes_the_flags_after_it(store: Path, items: Path) -> None:
    run("add", "--input", str(items), "--profile", "test", "--home", str(store))

    r = run(
        "forget", "--url", "https://vendor.test/a", "--profile", "test",
        "--home", str(store),
    )

    assert r.returncode == 0, r.stderr


def test_status_reports_the_store_it_used(store: Path) -> None:
    """Whichever position was used, the resolved profile is visible."""
    r = run("status", "--profile", "test", "--home", str(store))

    assert json.loads(r.stdout)["profile"] == "test"


def test_the_later_flag_wins_when_given_twice(store: Path, items: Path) -> None:
    """Defined behaviour rather than an argparse accident."""
    r = run(
        "--profile", "before", "--home", str(store),
        "add", "--input", str(items), "--profile", "after",
    )

    assert r.returncode == 0, r.stderr
    assert (store / "after" / "ledger.jsonl").exists()
    assert not (store / "before").exists()


def test_an_unknown_flag_is_still_rejected(store: Path, items: Path) -> None:
    """Accepting the globals late must not turn the parser permissive."""
    r = run("add", "--input", str(items), "--home", str(store), "--nonsense", "x")

    assert r.returncode == 2


# ------------------------------------------------- the examples that get copied


SKILL_MD = SCRIPT.parent.parent / "SKILL.md"


def documented_ledger_commands() -> list[str]:
    """Every `ledger.py` invocation in a runnable block of SKILL.md.

    Only fenced blocks: those are what a run copies. Prose mentions the flags in
    passing to explain where they may sit, and are not commands.
    """
    commands: list[str] = []
    in_block = False
    current = ""
    for line in SKILL_MD.read_text(encoding="utf-8").splitlines():
        if line.startswith("```"):
            in_block = line.strip() != "```"
            continue
        if not in_block:
            continue
        current = f"{current} {line.strip()}" if current else line.strip()
        if current.endswith("\\"):
            current = current[:-1]
            continue
        if "ledger.py" in current:
            commands.append(" ".join(current.split()))
        current = ""
    return commands


def test_skill_md_documents_ledger_commands() -> None:
    """A guard that asserts nothing unless the examples are still there."""
    assert len(documented_ledger_commands()) >= 8


@pytest.mark.parametrize("command", documented_ledger_commands())
def test_every_documented_command_addresses_a_store_and_a_profile(command: str) -> None:
    """The examples are the instruction that actually gets followed.

    A scheduled run was told which store to use in its own invocation and still
    wrote to the default, because it copied the worked examples and they carried
    only `--profile`. Prose does not out-argue a command someone can paste, so
    the flag belongs in every example rather than in a paragraph above them.
    """
    assert "--home" in command, command
    assert "--profile" in command, command
