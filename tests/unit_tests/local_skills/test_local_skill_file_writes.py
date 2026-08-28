"""A skill that asks for a file must say the file is written with the file-write tool.

Two scheduled runs died on the same mechanism in two days, in two different
skills. Both skills said *that* a file had to exist and *where* it went, and
neither said *how* to make it. Both runs reached for a shell heredoc, got the
quoting or the line continuation wrong, and reissued the identical command until
the host's loop guard ended the turn:

* One was told to write a JSON list of news candidates. A title containing an
  apostrophe -- "MCP's 2026 Roadmap" -- closed the single-quoted string early, a
  parenthesis in a later title then parsed as shell syntax, and four successive
  strategies failed on variations of the same thing: the quoted argument, a 500KB
  inline argument the kernel refused as ``Argument list too long``, a
  ``$(cat <<EOF ...)`` that broke on the same apostrophe, and a heredoc whose
  continuation put ``&&`` at the start of a line. The last of those was retried
  nine times unchanged.
* The other redirected a heredoc into the run directory that the very same
  command line empties on entry.

The common cause is not the shell. It is that the text being written is arbitrary
-- titles, URLs and prose taken off the open web, PR titles from a tracker -- so
it eventually contains an apostrophe, a quote or a parenthesis, and the failure
is in the quoting rather than in the data. That is why retrying cannot work, and
why a run retries anyway: nothing in the error names a different way to write the
file.

So the guard checks for the rule *and its reason*. A bare prohibition gets edited
out by the next person tidying the prose; a rule that carries why it exists
survives, and a model that reads the reason can tell which of its options is the
one being ruled out. The list of files below is written by hand rather than
discovered, because "this paragraph tells the model to write a file" is not
something a pattern can decide -- and a hand-written list that names a file which
has since moved fails loudly rather than scanning nothing.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SKILLS = Path(__file__).resolve().parents[3] / "local_skills"
LEDGER = SKILLS / "ai-news-monitor" / "scripts" / "ledger.py"

# Every shipped document that tells the model to produce a file, and the write it
# is on this list for. Adding a skill that asks for a file means adding it here.
FILE_WRITE_SITES = {
    "ai-news-monitor/SKILL.md": "candidates.json, retrieved-urls.txt, digest.md, reported.json",
    "repository-activity-digest/SKILL.md": "a filter script, and findings.json",
    "pr-tracker/references/store-schema.md": "fixing the JSONL store by hand",
}

# The rule, and the reason that keeps the rule alive. Split so a failure says
# which half went missing: dropping the reason is the likelier edit, and it is
# the half that makes the rule survive the next one.
RULE_PHRASES = ("file-write tool", "heredoc")
REASON_PHRASES = ("apostrophe", "quoting")

ADVICE = (
    "Where a skill tells the model to write a file, say that the file is written "
    "with the file-write tool -- `write_file`, or `edit_file` to amend one -- and "
    "not with a shell heredoc or a `>` redirect of the model's own text.\n"
    "Give the reason in the same breath: the text being written is arbitrary, so "
    "it eventually contains an apostrophe, a quote or a parenthesis, which ends "
    "the shell's quoting early and turns the rest of the file into shell syntax; "
    "the fault is in the quoting rather than in the data, so the same command "
    "line fails identically however often it is retried.\n"
    "This has now ended two scheduled runs in two days, in two different skills. "
    "A bare prohibition does not survive editing -- keep the reason attached."
)


@pytest.mark.parametrize("relative", sorted(FILE_WRITE_SITES))
def test_each_document_that_asks_for_a_file_says_which_tool_writes_it(relative: str) -> None:
    path = SKILLS / relative
    assert path.is_file(), f"{relative} no longer exists; this guard is scanning nothing"
    text = path.read_text(encoding="utf-8")

    missing = [phrase for phrase in RULE_PHRASES + REASON_PHRASES if phrase not in text]
    assert not missing, "\n".join(
        [f"{relative} never says {phrase!r}" for phrase in missing]
        + ["", f"It asks the model to write: {FILE_WRITE_SITES[relative]}", "", ADVICE]
    )


def test_the_guard_reads_more_than_one_skill() -> None:
    """One skill is how this spread the first time: it was fixed in the one that failed."""
    skills = {relative.split("/")[0] for relative in FILE_WRITE_SITES}
    assert len(skills) >= 3, f"a guard over one skill leaves the pattern live elsewhere: {skills}"


# ------------------------------------------------------- the file that was not written


def run_ledger(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(LEDGER), *args],
        capture_output=True,
        text=True,
        timeout=60,
    )


@pytest.fixture
def store(tmp_path: Path) -> Path:
    """A scratch store, so no test can touch a real ledger or move a watermark."""
    return tmp_path / "store"


@pytest.mark.parametrize("subcommand", ["new", "add"])
def test_a_missing_input_file_is_refused_with_the_remedy(
    store: Path, tmp_path: Path, subcommand: str
) -> None:
    """`--input` at a path nothing wrote used to raise a bare FileNotFoundError.

    A traceback says a path was absent. It does not say the file was this run's
    own to write, and it does not say which tool writes it -- so the run that
    cost this read it as noise and reissued the command that had failed to create
    the file. The message has to carry the whole answer.
    """
    missing = tmp_path / "candidates.json"
    result = run_ledger(
        "--home", str(store), "--profile", "scratch",
        subcommand, "--input", str(missing),
    )

    assert result.returncode != 0
    assert "Traceback" not in result.stderr, result.stderr
    assert "FileNotFoundError" not in result.stderr, result.stderr

    message = result.stderr
    assert str(missing) in message, "the message must name the path it could not read"
    assert "does not exist" in message
    assert "write it" in message.lower(), "the remedy is to write the file first"
    assert "file-write tool" in message, "a remedy the model cannot act on gets retried verbatim"
    assert "heredoc" in message, "the message must rule out the way the failing runs reached for"


def test_a_directory_passed_as_input_says_to_name_the_file_inside_it(
    store: Path, tmp_path: Path
) -> None:
    """`<run>` and `<run>/candidates.json` are one tab apart in the prose."""
    result = run_ledger(
        "--home", str(store), "--profile", "scratch",
        "new", "--input", str(tmp_path),
    )

    assert result.returncode != 0
    assert "Traceback" not in result.stderr, result.stderr
    assert "is a directory" in result.stderr
    assert "Name the JSON file inside it" in result.stderr


def test_the_refusal_does_not_create_the_store_it_was_pointed_at(
    store: Path, tmp_path: Path
) -> None:
    """Refusing early must not leave a half-made profile a later run reads as real."""
    run_ledger(
        "--home", str(store), "--profile", "scratch",
        "new", "--input", str(tmp_path / "nothing.json"),
    )

    assert not (store / "scratch" / "ledger.jsonl").exists()


def test_a_readable_input_file_still_loads(store: Path, tmp_path: Path) -> None:
    """The new refusals must not stand between a real file and the command."""
    items = tmp_path / "candidates.json"
    items.write_text(
        '[{"url": "https://vendor.test/a", "title": "MCP\'s 2026 Roadmap (part 1)"}]',
        encoding="utf-8",
    )

    result = run_ledger(
        "--home", str(store), "--profile", "scratch",
        "new", "--input", str(items),
    )

    assert result.returncode == 0, result.stderr
    assert "vendor.test/a" in result.stdout
