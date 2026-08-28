#!/usr/bin/env python3
"""Compare the version-controlled skills against the ones the service loads.

Custom skills live in ``local_skills/<name>/`` in this repository and are synced
to the agent workspace at ``~/.jiuwenswarm/agent/workspace/skills/<name>/``, which
is what the running service actually reads. The working practice is to edit in the
workspace first, so a skill can be exercised immediately, and to sync back to git
afterwards. The failure this check exists to catch is the forgotten sync-back.

Comparing the workspace against the deployed baseline alone produces false alarms:
a skill whose changes are already committed on an unpromoted branch looks exactly
like a pile of uncommitted live edits. This check therefore falls back to searching
every local branch before it calls anything drift, and names the branch it found.

Usage
-----
    python3 local_scripts/check_skill_drift.py [--baseline REF] [--workspace DIR]
                                         [--verbose]

Options
    --baseline REF    Ref treated as the deployed position. Default: local/deployed.
    --workspace DIR   Workspace skills directory. Default:
                      ~/.jiuwenswarm/agent/workspace/skills
    --verbose         List the individual differing files under each skill.

Exit status
    0   Every skill is either identical to the baseline, or differs from it but
        matches a local branch (in-flight work, not drift).
    1   At least one skill needs a sync-back: it differs from the baseline and
        from every local branch, or it exists on only one of the two sides.
    2   The check could not run (bad ref, missing workspace, not a work tree).

The check is read-only. It writes nothing, opens no network connection, and does
not talk to the running service, so it is safe to run at any time and to use as a
gate in front of a sync.

Scope
    Only the operator's own skills are considered. The workspace also holds
    builtin and skillnet-installed skills, which do not belong in this repository;
    they are listed as skipped rather than reported as missing. The skill roster
    comes from the workspace's skills_state.json where available, unioned with what
    is present in git and on disk.

Comparison
    File contents only, by git blob hash. File modes are not compared. Build and
    editor debris -- ``__pycache__/``, ``*.pyc`` and the ``*.bak-<timestamp>`` files
    the operator leaves beside an edited skill -- is excluded from the comparison
    and reported separately, so it is visible without being counted as drift.
    Only local branches are searched; remote-tracking refs are not.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

SKILL_ROOT = "local_skills"
STATE_FILE = "skills_state.json"

# Files that live beside a skill without being part of it.
NOISE_DIRS = {"__pycache__"}
NOISE_SUFFIXES = (".pyc", ".pyo")
NOISE_INFIX = ".bak-"

# Verdicts, and whether each one should fail the run.
CLEAN = "clean"
IN_FLIGHT = "in-flight"
DRIFTED = "drifted"
UNTRACKED = "untracked"
NOT_INSTALLED = "not-installed"
BRANCH_ONLY = "branch-only"
GHOST = "ghost"

FAILING = {DRIFTED, UNTRACKED, NOT_INSTALLED}


class CheckError(Exception):
    """The check cannot produce a meaningful answer."""


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise CheckError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def is_noise(relative: str) -> bool:
    parts = relative.split("/")
    if any(part in NOISE_DIRS for part in parts):
        return True
    name = parts[-1]
    return name.endswith(NOISE_SUFFIXES) or NOISE_INFIX in name


def read_tree(repo: Path, ref: str) -> dict[str, dict[str, str]]:
    """Map skill name -> {path within the skill: blob hash} for one ref."""
    try:
        listing = git(repo, "ls-tree", "-r", ref, "--", f"{SKILL_ROOT}/")
    except CheckError:
        return {}
    skills: dict[str, dict[str, str]] = {}
    for line in listing.splitlines():
        if not line.strip():
            continue
        meta, _, path = line.partition("\t")
        fields = meta.split()
        if len(fields) < 3:
            continue
        blob = fields[2]
        remainder = path[len(SKILL_ROOT) + 1 :]
        skill, _, relative = remainder.partition("/")
        if not skill or not relative or is_noise(relative):
            continue
        skills.setdefault(skill, {})[relative] = blob
    return skills


def hash_file(repo: Path, path: Path) -> str:
    return git(repo, "hash-object", "--", str(path)).strip()


def read_workspace(repo: Path, root: Path) -> tuple[dict[str, dict[str, str]], dict[str, list[str]]]:
    """Map skill name -> {path: blob hash}, plus the noise found under each skill."""
    skills: dict[str, dict[str, str]] = {}
    noise: dict[str, list[str]] = {}
    for entry in sorted(root.iterdir()):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        files: dict[str, str] = {}
        junk: list[str] = []
        for path in sorted(entry.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(entry).as_posix()
            if is_noise(relative):
                junk.append(relative)
            else:
                files[relative] = hash_file(repo, path)
        skills[entry.name] = files
        if junk:
            noise[entry.name] = junk
    return skills, noise


def read_state(root: Path) -> tuple[set[str], dict[str, str]]:
    """Return the operator's own skill names, and the foreign ones with their source."""
    state_path = root / STATE_FILE
    if not state_path.is_file():
        return set(), {}
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set(), {}
    own: set[str] = set()
    foreign: dict[str, str] = {}
    for record in state.get("local_skills") or []:
        if not isinstance(record, dict):
            continue
        name = record.get("name")
        if not name:
            continue
        if record.get("source") == "local":
            own.add(name)
        else:
            foreign[name] = str(record.get("source") or "unknown")
    for record in state.get("installed_plugins") or []:
        if isinstance(record, dict) and record.get("name"):
            foreign.setdefault(record["name"], str(record.get("source") or "unknown"))
    return own, foreign


def local_branches(repo: Path, baseline: str) -> list[str]:
    listing = git(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads/")
    baseline_sha = git(repo, "rev-parse", baseline).strip()
    names = []
    for name in listing.split():
        if git(repo, "rev-parse", name).strip() == baseline_sha:
            continue
        names.append(name)
    return names


def classify(
    skill: str,
    workspace: dict[str, str] | None,
    baseline: dict[str, str] | None,
    branch_trees: dict[str, dict[str, dict[str, str]]],
) -> tuple[str, list[str]]:
    if not workspace and not baseline:
        # Nothing on either side. It may still exist on a feature branch, in which
        # case it is simply work that has not been installed yet -- not a ghost.
        matches = sorted(b for b, t in branch_trees.items() if skill in t)
        return (BRANCH_ONLY, matches) if matches else (GHOST, [])
    if workspace and not baseline:
        matches = sorted(b for b, t in branch_trees.items() if t.get(skill) == workspace)
        return (IN_FLIGHT, matches) if matches else (UNTRACKED, [])
    if baseline and not workspace:
        return NOT_INSTALLED, []
    if workspace == baseline:
        return CLEAN, []
    matches = sorted(b for b, t in branch_trees.items() if t.get(skill) == workspace)
    return (IN_FLIGHT, matches) if matches else (DRIFTED, [])


def describe(skill: str, workspace: dict[str, str] | None, baseline: dict[str, str] | None) -> list[str]:
    workspace = workspace or {}
    baseline = baseline or {}
    lines = []
    for name in sorted(set(workspace) | set(baseline)):
        if name not in baseline:
            lines.append(f"only in workspace: {name}")
        elif name not in workspace:
            lines.append(f"only in git:       {name}")
        elif workspace[name] != baseline[name]:
            lines.append(f"contents differ:   {name}")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare local_skills/ against the live agent workspace.",
    )
    parser.add_argument("--baseline", default="local/deployed", help="deployed ref (default: local/deployed)")
    parser.add_argument(
        "--workspace",
        default=str(Path.home() / ".jiuwenswarm/agent/workspace/skills"),
        help="workspace skills directory",
    )
    parser.add_argument("--verbose", action="store_true", help="list differing files per skill")
    args = parser.parse_args(argv)

    repo = Path(__file__).resolve().parent.parent
    workspace_root = Path(os.path.expanduser(args.workspace))

    try:
        git(repo, "rev-parse", "--git-dir")
        baseline_sha = git(repo, "rev-parse", args.baseline).strip()
    except CheckError as exc:
        print(f"cannot run: {exc}", file=sys.stderr)
        return 2
    if not workspace_root.is_dir():
        print(f"cannot run: workspace not found at {workspace_root}", file=sys.stderr)
        return 2

    try:
        baseline_trees = read_tree(repo, args.baseline)
        workspace_trees, noise = read_workspace(repo, workspace_root)
        branches = local_branches(repo, args.baseline)
        branch_trees = {name: read_tree(repo, name) for name in branches}
    except CheckError as exc:
        print(f"cannot run: {exc}", file=sys.stderr)
        return 2

    own, foreign = read_state(workspace_root)
    tracked = set(baseline_trees) | {s for t in branch_trees.values() for s in t}
    considered = sorted((own | tracked | set(workspace_trees)) - set(foreign))

    print(f"repository: {repo}")
    print(f"baseline:   {args.baseline} ({baseline_sha[:9]})")
    print(f"workspace:  {workspace_root}")
    print(f"branches searched: {len(branches)} local")
    print()

    failures = 0
    for skill in considered:
        in_workspace = workspace_trees.get(skill)
        in_baseline = baseline_trees.get(skill)
        verdict, matches = classify(skill, in_workspace, in_baseline, branch_trees)

        if verdict == CLEAN:
            note = f"identical to {args.baseline} ({len(in_baseline)} files)"
        elif verdict == IN_FLIGHT:
            where = "absent from" if not in_baseline else "differs from"
            note = (
                f"{where} {args.baseline}, matches branch: {', '.join(matches)}"
                " -- in-flight work, not drift"
            )
        elif verdict == DRIFTED:
            note = f"differs from {args.baseline} and from every local branch -- needs sync-back"
        elif verdict == UNTRACKED:
            note = f"in the workspace, absent from git entirely ({len(in_workspace)} files) -- needs importing"
        elif verdict == NOT_INSTALLED:
            note = f"in git, absent from the workspace ({len(in_baseline)} files) -- never installed"
        elif verdict == BRANCH_ONLY:
            note = (
                f"absent from {args.baseline} and from the workspace,"
                f" present on branch: {', '.join(matches)} -- not installed yet"
            )
        else:
            note = "registered in skills_state.json but present neither in git nor in the workspace"

        marker = "FAIL" if verdict in FAILING else "ok  "
        print(f"{marker} {skill}: {note}")
        if args.verbose and verdict in (DRIFTED, IN_FLIGHT):
            for line in describe(skill, in_workspace, in_baseline):
                print(f"       {line}")
        if verdict in FAILING:
            failures += 1

    if noise:
        print()
        print("ignored as build or editor debris, not counted as drift:")
        for skill in sorted(noise):
            for relative in noise[skill]:
                print(f"  {skill}/{relative}")

    if foreign:
        print()
        print("skipped, not this repository's to carry:")
        for name in sorted(foreign):
            print(f"  {name} (source: {foreign[name]})")

    print()
    if failures:
        print(f"{failures} skill(s) need attention")
    else:
        print("no drift: every skill is either at the baseline or on a local branch")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
