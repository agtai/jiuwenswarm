"""No skill under ``local_skills/`` may make its scratch directory with ``mktemp``.

The pattern has cost three runs across two skills. The reason it fails is not a
style preference and it is not specific to one skill, which is why the guard is
here rather than inside any one of them:

* **Each command of a run executes in its own shell.** A directory made by
  ``mktemp -d`` in one command cannot be named by the next: the variable holding
  it is gone, and the name was random, so nothing can work the path out again. A
  file written by one step and read by another therefore has nowhere to live.
* **The working directory can be shared between runs.** Where it is one flat
  directory rather than one per session, a file a failed run left behind is found
  by an unrelated later run and taken for its own -- and a failed run is exactly
  the one that leaves files behind, because it never reaches a cleanup step.

What to do instead: derive the directory from a path the caller already supplies,
usually the state file, so every step of the run recomputes the same path; and
empty it when the run starts rather than when it ends.

The guard forbids *invocation*, not the word. Skills explain in prose why they do
not use ``mktemp``, and a guard that failed on the explanation would fail on
precisely the skills that got this right. A mention belongs inside backticks; a
line that would actually run the command does not.

Out of scope on purpose: ``tempfile.mkdtemp`` is the same defect in Python, and
``tempfile.NamedTemporaryFile(dir=...)`` next to a real destination is a correct
atomic-write idiom that must not be confused with it. Neither is checked here.

The second guard below covers the cost of the first one's answer. Emptying the
scratch directory when the run starts is what keeps a failed run's leftovers out
of its successor, and it is also what destroys a write that is still in flight:
a command line that empties the directory and redirects into it at once has the
shell create the file before the command runs, the command delete it a moment
later, and the write land in a file with no name. Nothing fails at the time, and
the run only finds out when reading the file back reports that it is missing --
which is what a mistyped path reports too. So every skill that empties a
directory must first establish that nothing is writing into it. The guard is
here, and not in any one skill, for the same reason as the first: the pattern is
shared, so a fix applied to the skill that happened to fail leaves it live
everywhere else.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

SKILLS = Path(__file__).resolve().parents[3] / "local_skills"

# Files worth reading: the prose a skill ships, the scripts it ships, and the
# data files in between. Discovered by extension rather than listed, so a
# reference or a script added later is covered without anyone remembering this.
SUFFIXES = {".md", ".py", ".sh", ".json", ".yaml", ".yml", ".txt"}

INVOCATIONS = (
    # `RUN=$(mktemp -d)`, and every other command substitution.
    re.compile(r"\$\(\s*mktemp\b"),
    # The legacy spelling of the same thing, RUN=`mktemp -d`. Flagged only in
    # assignment position, because a backticked `mktemp -d` on its own is how
    # both prose and a docstring quote the command they are arguing against.
    re.compile(r"=\s*`\s*mktemp\b"),
    # `mktemp` run as a command in its own right: at the start of a line, after
    # a shell prompt, or after a separator. A prose mention is never here,
    # because the opening backtick sits between the line start and the word.
    re.compile(r"(?:^|[;&|])\s*\$?\s*mktemp\b"),
)

ADVICE = (
    "Do not make a scratch directory with mktemp. Each command of a run is a "
    "fresh shell, so the variable holding a random directory is gone by the next "
    "command and the path cannot be worked out again; and where the working "
    "directory is shared between runs, a failed run's leftovers become the next "
    "run's inputs.\n"
    "Derive the directory from a path the caller already supplies -- the state "
    "file -- so every step recomputes it, and empty it when the run starts "
    "rather than when it ends. pr-tracker's run_dir_for() and "
    "repository-activity-digest's run_dir_for() are both this.\n"
    "The word itself is fine in prose: write it inside backticks."
)


def shipped_files() -> list[Path]:
    return sorted(
        path
        for path in SKILLS.rglob("*")
        if path.is_file()
        and path.suffix in SUFFIXES
        and "__pycache__" not in path.parts
    )


def invocations_in(text: str) -> list[tuple[int, str]]:
    """(line number, line) for every line that would actually run ``mktemp``."""
    return [
        (lineno, line)
        for lineno, line in enumerate(text.splitlines(), start=1)
        if any(pattern.search(line) for pattern in INVOCATIONS)
    ]


def test_no_local_skill_invokes_mktemp():
    offences = []
    for path in shipped_files():
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:  # pragma: no cover - no such file ships today
            continue
        for lineno, line in invocations_in(text):
            relative = path.relative_to(SKILLS)
            offences.append(f"{relative}:{lineno}: {line.strip()}")
    assert not offences, "\n".join([*offences, "", ADVICE])


def test_the_guard_reads_the_skills_it_is_meant_to():
    """A scan that found nothing passes for the wrong reason.

    The directory has been renamed once and the tests have been moved once, so
    the thing most likely to break this guard is not a skill reintroducing the
    pattern -- it is this file quietly scanning an empty list.
    """
    assert SKILLS.is_dir(), SKILLS
    skills = sorted(path.name for path in SKILLS.iterdir() if path.is_dir())
    assert len(skills) >= 2, f"one skill is how the pattern spread last time: {skills}"

    files = shipped_files()
    assert len(files) > 10, files
    suffixes = {path.suffix for path in files}
    assert {".md", ".py"} <= suffixes, f"prose and scripts, both: {sorted(suffixes)}"
    covered = {path.relative_to(SKILLS).parts[0] for path in files}
    assert covered == set(skills), f"every skill, not just one: {sorted(covered)}"


def test_the_guard_separates_an_invocation_from_a_mention():
    """The half that is easy to get wrong.

    A substring check on the word fails on the skills that already do this
    correctly, because each of them says in prose why it does not use `mktemp`.
    The benign cases below are shipped lines, not invented ones.
    """
    for hazard in (
        "RUN=$(mktemp -d)",
        'RUN=$(mktemp -d) && echo "$RUN"',
        "     RUN=$(mktemp -d)",
        "  work=$( mktemp -d )",
        "RUN=`mktemp -d`",
        "mktemp -d",
        "  mktemp -d > /tmp/where",
        "cd /somewhere && mktemp -d",
        "$ mktemp -d",
        'print("  RUN=$(mktemp -d)\\n")',
    ):
        assert invocations_in(hazard), hazard
    for benign in (
        "- **Each bash call is a fresh shell.** A directory made by `mktemp -d`",
        "    `mktemp -d` directory is unrecoverable the moment the command that",
        "Not in the skill directory, for the reason just given. Not in a `mktemp -d`",
        "by the first command with `mktemp -d` cannot be named by the second.",
        "the next install. And not a `mktemp -d`, for two reasons that both cost",
        "mktemp_note = 'why this is not used'",
    ):
        assert not invocations_in(benign), benign


GUARD = "names_held_open_in"

WIPE_ADVICE = (
    "A directory emptied while something is writing into it destroys that write "
    "in silence. Before deleting a scratch directory, ask whether any live "
    f"process holds an entry of it open -- that is what {GUARD}() is for -- and "
    "refuse rather than delete when one does.\n"
    "Refuse; do not move the delete to the end of the run. Clearing on entry is "
    "what keeps a failed run's leftovers out of the next run, because a failed "
    "run never reaches a cleanup step.\n"
    "Do not decide it by timestamp either. A leftover written a second ago is "
    "still a leftover and still has to go; only an open descriptor tells a "
    "leftover apart from a write in flight.\n"
    "The refusal must say what to do instead, not only what is wrong. A "
    "rejection nothing can act on is reissued unchanged until a host stops the "
    "run."
)


def python_files() -> list[Path]:
    return [path for path in shipped_files() if path.suffix == ".py"]


def calls_in(function: ast.AST) -> list[tuple[int, str]]:
    """(line, called name) for every call in a function body, innermost name only."""
    found = []
    for node in ast.walk(function):
        if not isinstance(node, ast.Call):
            continue
        target = node.func
        name = target.attr if isinstance(target, ast.Attribute) else getattr(target, "id", None)
        if name:
            found.append((node.lineno, name))
    return sorted(found)


def functions_that_empty_a_directory() -> list[tuple[Path, ast.AST]]:
    found = []
    for path in python_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):  # pragma: no cover - would fail elsewhere
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if any(name == "rmtree" for _, name in calls_in(node)):
                found.append((path, node))
    return found


def test_every_scratch_directory_wipe_first_checks_for_a_write_in_flight():
    offences = []
    for path, function in functions_that_empty_a_directory():
        calls = calls_in(function)
        wipe = min(line for line, name in calls if name == "rmtree")
        guards = [line for line, name in calls if name == GUARD]
        if not guards or min(guards) > wipe:
            offences.append(
                f"{path.relative_to(SKILLS)}:{wipe}: {function.name}() empties a "
                f"directory without asking whether anything is writing into it"
            )
    assert not offences, "\n".join([*offences, "", WIPE_ADVICE])


def test_the_refusal_each_skill_prints_says_what_to_do_instead():
    """The message is the only thing its reader has, so it carries the whole answer.

    A rejection that states the problem and stops is reissued verbatim, because
    nothing in it names a different command to run. Each skill therefore names
    its own command, says to run it on its own, and says why running it again
    unchanged cannot work.
    """
    missing = []
    for path, function in functions_that_empty_a_directory():
        source = ast.get_source_segment(path.read_text(encoding="utf-8"), function) or ""
        for phrase in ("on its own", "cannot help", "same command line"):
            if phrase not in source:
                missing.append(f"{path.relative_to(SKILLS)}: {function.name}() never says {phrase!r}")
    assert not missing, "\n".join([*missing, "", WIPE_ADVICE])


def test_the_wipe_guard_reads_the_skills_it_is_meant_to():
    """A scan that found no directory wipes would pass for the wrong reason."""
    found = functions_that_empty_a_directory()
    skills = {path.relative_to(SKILLS).parts[0] for path, _ in found}
    assert len(skills) >= 3, f"one skill is how the pattern spread last time: {sorted(skills)}"
    for path, _ in found:
        text = path.read_text(encoding="utf-8")
        assert f"def {GUARD}(" in text, f"{path.relative_to(SKILLS)} defines no {GUARD}()"


def skills_with_a_run_directory() -> list[Path]:
    """Skill directories whose scripts empty a directory of their own.

    Rediscovered here rather than shared with the guards above, so this check
    and the guard it accompanies can each be removed without taking the other
    with it.
    """
    return sorted(
        {
            path.parents[1]
            for path in shipped_files()
            if path.suffix == ".py" and "rmtree(" in path.read_text(encoding="utf-8")
        }
    )


def test_every_skill_that_empties_a_directory_says_so_in_its_own_prose():
    """A refusal is a poor place to learn this, so the prose says it first.

    A run only reaches the refusal after spending the command being refused, and
    on the skill this cost, that command is most of the run. The instruction has
    to arrive in the file the skill is read from, where it introduces its run
    directory: the directory is emptied when the run starts, so nothing may be
    written into it on the same command line.
    """
    skills = skills_with_a_run_directory()
    assert len(skills) >= 3, f"a scan that found nothing passes wrongly: {skills}"

    missing = []
    for skill in skills:
        prose = skill / "SKILL.md"
        if not prose.is_file():
            missing.append(f"{skill.name}: no SKILL.md to say it in")
            continue
        text = prose.read_text(encoding="utf-8")
        for phrase in ("same command line", "empties"):
            if phrase not in text:
                missing.append(f"{skill.name}/SKILL.md never says {phrase!r}")
    assert not missing, "\n".join(
        [
            *missing,
            "",
            "A scratch directory emptied at the start of a run is not somewhere "
            "the command that empties it may be told to write. Say so where the "
            "skill introduces the directory: that it is emptied when the run "
            "starts, and that nothing may be redirected into it on the same "
            "command line, because the shell creates that file before the "
            "command runs and the command deletes it while it is still being "
            "written.",
        ]
    )
