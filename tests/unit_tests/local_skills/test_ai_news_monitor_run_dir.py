"""The run's scratch directory: derived from the store, emptied when the run starts.

Working files used to go in a directory the run made with `mktemp -d`. That
failed twice for two separate reasons, and both are covered here because a fix
for either alone leaves the other:

- **Unrecoverable.** Every command of a run is its own shell, so the variable
  holding a random directory is gone by the next command and the name cannot be
  worked out again. Deriving the directory from the store means any step
  recomputes it from `--home` and `--profile`, which the prompt supplies anyway.
- **Leftovers.** Where the working directory is shared, a file a failed run left
  behind is found by the next run and taken for its own — and the failed run is
  precisely the one that leaves files behind, because it never reaches a cleanup
  step. So the directory is emptied on entry, not on exit.

The split between `start-run` and `status` is the part most likely to be
"simplified" later, so it is asserted rather than only explained: `status` is
read-only, it is the command a run repeats to check its own work, and README
suggests running it after `add`. Had it also cleared the directory, that check
would delete the digest between recording it and delivering it.

The refusal messages are covered too. Both scripts refuse a working file inside
the skill directory and then say what to type instead, and that text is an
instruction the model acts on: while it read `RUN=$(mktemp -d)`, the scripts were
teaching the defect they were built to stop.
"""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parents[3] / "local_skills" / "ai-news-monitor"
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


def ledger(store: Path, *args: str, profile: str = "test") -> subprocess.CompletedProcess[str]:
    return run(LEDGER, "--profile", profile, "--home", str(store), *args)


def start_run(store: Path, profile: str = "test") -> Path:
    result = ledger(store, "start-run", profile=profile)
    assert result.returncode == 0, result.stderr
    return Path(result.stdout.strip())


def test_the_run_directory_is_derived_from_the_store(store: Path) -> None:
    """The path a step re-derives instead of remembering.

    Asserted as a literal rather than by calling `run_dir_for`, because the
    property that matters is that a caller holding only `--home` and `--profile`
    can write the path down without help.
    """
    assert start_run(store) == store / "test.run"


def test_the_directory_exists_and_names_this_run_s_files(store: Path) -> None:
    run_dir = start_run(store)
    assert run_dir.is_dir()
    manifest = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert manifest["run_dir"] == str(run_dir)
    assert manifest["store"] == str(store / "test")
    # Absolute, so a step copies the path rather than joining it to a long store
    # path by hand — a mistyped path fails, gets retried unchanged, and takes the
    # run with it.
    assert manifest["files"]["digest.md"] == str(run_dir / "digest.md")
    assert manifest["files"]["link-check.json"] == str(run_dir / "link-check.json")


def test_a_second_run_does_not_inherit_the_first_one_s_files(store: Path) -> None:
    """Emptied on entry. The leftover that misleads is a failed run's."""
    first = start_run(store)
    (first / "digest.md").write_text("last week's digest", encoding="utf-8")
    (first / "nested").mkdir()

    second = start_run(store)

    assert second == first
    assert not (second / "digest.md").exists()
    assert not (second / "nested").exists()
    assert (second / "run.json").exists()


def test_status_reports_the_directory_without_touching_it(store: Path) -> None:
    """The reason `start-run` is a command of its own.

    `status` is read-only and is run repeatedly, including after `add` to confirm
    the recording landed. Clearing from there would delete the digest between
    recording it and delivering it.
    """
    run_dir = start_run(store)
    (run_dir / "digest.md").write_text("this run's digest", encoding="utf-8")

    result = ledger(store, "status")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["run_dir"] == str(run_dir)
    assert (run_dir / "digest.md").read_text(encoding="utf-8") == "this run's digest"


def test_status_names_the_directory_before_any_run_has_made_one(store: Path) -> None:
    """Derived, so it can be named before it exists — and still not created."""
    result = ledger(store, "status")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["run_dir"] == str(store / "test.run")
    assert not (store / "test.run").exists()


def test_profiles_that_share_a_prefix_do_not_share_a_directory(store: Path) -> None:
    """A profile name may contain a dot, so the suffix is appended, not replaced.

    Replacing it would give `weekly.work` and `weekly.personal` one `weekly.run`
    between them, which is the shared-directory failure this whole scheme exists
    to remove, reintroduced by a one-character choice.
    """
    a = start_run(store, profile="weekly.work")
    b = start_run(store, profile="weekly.personal")
    assert a != b
    assert {a.name, b.name} == {"weekly.work.run", "weekly.personal.run"}


def test_starting_a_run_records_nothing(store: Path) -> None:
    """Scratch and history are separate: restarting scratch un-reports nothing."""
    start_run(store)
    assert ledger(store, "since").stdout.strip() == "never"
    assert not (store / "test" / "ledger.jsonl").exists()
    assert json.loads(ledger(store, "status").stdout)["runs"] == 0


@pytest.mark.parametrize("script", [LEDGER, CHECK_LINKS], ids=["ledger", "check_links"])
def test_the_refusal_teaches_the_derived_directory(script: Path, store: Path) -> None:
    """What the scripts print is an instruction, and it used to teach the defect.

    Both refuse a working file inside the skill directory and then say where one
    belongs. That text is the skill's most load-bearing guidance about scratch,
    because it arrives at the moment the model is already fixing a path.
    """
    stray = str(SKILL / "digest.md")
    if script == LEDGER:
        result = ledger(store, "new", "--input", stray)
    else:
        result = run(script, stray, "--offline")

    assert result.returncode != 0
    message = result.stdout + result.stderr
    assert "start-run" in message
    assert "`.run`" in message
    assert "mktemp" not in message


def in_a_shell(command: str) -> subprocess.CompletedProcess[str]:
    """Run a command line through a real shell.

    The failure below is a property of how a shell builds a pipeline, not of
    anything Python does, so it is reproduced in a shell rather than imitated.
    """
    return subprocess.run(
        command, shell=True, capture_output=True, text=True, timeout=60
    )


def start_run_command(store: Path, profile: str = "test") -> str:
    return " ".join(
        shlex.quote(part)
        for part in (
            sys.executable,
            str(LEDGER),
            "--profile",
            profile,
            "--home",
            str(store),
            "start-run",
        )
    )


def test_a_redirect_into_the_directory_on_the_same_command_line_is_refused(
    store: Path,
) -> None:
    """The shape that destroys a write in flight, and why nothing notices.

    `start-run > <run>/extract.json` reads as saving the command's output. The
    shell creates `extract.json` while it is setting the redirect up, before the
    script has run a line; the script then empties the directory; and the write
    lands in a file that no longer has a name. Nothing fails at the time, and
    the run finds out only when reading the file back says it is not there --
    which is also what a mistyped path says, so the run goes looking for the
    wrong problem.
    """
    run_dir = start_run(store)
    target = run_dir / "extract.json"

    result = in_a_shell(f"{start_run_command(store)} > {shlex.quote(str(target))}")

    assert result.returncode != 0
    assert "extract.json" in result.stderr
    assert target.exists(), "refused rather than deleted while being written"


def test_a_pipeline_writing_into_the_directory_is_refused_too(store: Path) -> None:
    """The same mistake wearing a filter, which is how it usually arrives.

    The redirect belongs to the last command of the pipeline, so the descriptor
    is held by a different process than the one emptying the directory. Time
    cannot tell that apart from a leftover; an open descriptor can.
    """
    run_dir = start_run(store)
    target = run_dir / "template.json"

    result = in_a_shell(
        f"{start_run_command(store)} | cat > {shlex.quote(str(target))}"
    )

    assert "template.json" in result.stderr
    assert target.exists()


def test_the_refusal_says_what_to_do_instead(store: Path) -> None:
    """A rejection nothing can act on is reissued unchanged until a host ends the run.

    Everything the reader needs is in the message, because the message is the
    only thing the reader has at that point.
    """
    run_dir = start_run(store)
    target = run_dir / "extract.json"

    result = in_a_shell(f"{start_run_command(store)} > {shlex.quote(str(target))}")

    assert "start-run" in result.stderr, "which command to reissue"
    assert "on its own" in result.stderr, "how to reissue it"
    assert "cannot help" in result.stderr, "why reissuing it unchanged will not do"
    assert "after `start-run` has returned" in result.stderr, "when a file may be written"


def test_a_closed_leftover_is_still_deleted_however_recent_it_is(store: Path) -> None:
    """Age is not the test, and must not become one.

    A file a failed run left a second ago is still a leftover, and deleting it
    is the entire reason the directory is emptied on entry rather than on exit.
    Only a descriptor still open separates it from a write in flight.
    """
    run_dir = start_run(store)
    (run_dir / "digest.md").write_text("written a moment ago", encoding="utf-8")

    assert start_run(store) == run_dir
    assert not (run_dir / "digest.md").exists()
    assert (run_dir / "run.json").is_file()
