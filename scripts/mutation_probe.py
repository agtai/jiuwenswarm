#!/usr/bin/env python3
"""Ask of every guard in a module: if this were wrong, would a test notice?

Coverage answers a different question -- was this line executed -- and the two come
apart exactly where it matters. Measured on this repo's cloud-document code, the gateway
package sits at 87-99% line coverage, and three review rounds still found twenty-three
defects in it. Six of those coverage could have caught. The rest were invisible to it:

* a test existed, passed, and asserted the wrong thing (a contract test that checked a
  method was a coroutine under a name promising it refused; a fake provider with no
  receipt sink, certifying that an unattended write works without an audit record)
* the defect was an **absence** -- a parameter never passed, a field written and read by
  nobody, a function with tests and no production caller. ``ReceiptStore.pending`` had
  100% line coverage from four tests and was called from nowhere, so the crash window it
  documents was never adjudicated.

Mutation testing asks the question that separates those: break something on purpose, and
see whether the suite goes red. A mutant that survives is a line no test is actually
checking, whatever the coverage report says.

**Why not mutmut.** It is installed and it works; it is also whole-suite-per-mutant, and
this repo's collection alone costs several seconds, which puts a full run in the hours.
This runs a targeted set instead: the operators below are the shapes the defects in this
codebase have actually taken, and each mutant runs only the tests mapped to its module.
The point is a number you will re-run, not a complete one you run once.

Usage:
    python scripts/mutation_probe.py jiuwenswarm/gateway/clouddoc
    python scripts/mutation_probe.py <path> --jobs 8 --limit 50
"""

from __future__ import annotations

import argparse
import ast
import concurrent.futures
import random
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

# Operators, in the order they earn their keep on this codebase.
#
# Guard removal comes first because that is what the real defects looked like: a range
# rail that refuses a formula cell, a write that refuses without a receipt sink, a sweep
# that skips receipts too young to be dead. Each is one ``if``, and each was either
# missing or unchecked.
_COMPARISONS = {
    ast.Eq: "!=", ast.NotEq: "==",
    ast.Lt: ">=", ast.GtE: "<", ast.Gt: "<=", ast.LtE: ">",
    ast.Is: "is not", ast.IsNot: "is",
    ast.In: "not in", ast.NotIn: "in",
}


@dataclass(frozen=True)
class Mutant:
    path: Path
    line: int
    kind: str
    original: str
    replacement: str
    start: int      # byte offset into the source
    end: int

    @property
    def label(self) -> str:
        return f"{self.path}:{self.line} [{self.kind}] {self.original[:60]!r} -> {self.replacement}"


def _offset(lines: list[int], lineno: int, col: int) -> int:
    return lines[lineno - 1] + col


def _line_starts(src: str) -> list[int]:
    out, pos = [0], 0
    for ch in src:
        pos += 1
        if ch == "\n":
            out.append(pos)
        # A file is indexed by character offset, not byte offset: the sources here are
        # UTF-8 with Chinese comments throughout, and mixing the two units silently
        # corrupts the mutant instead of failing.
    return out


def _skip_guard(node: ast.If) -> bool:
    """Guards whose mutation says nothing about the tests."""
    test = node.test
    if isinstance(test, ast.Name) and test.id == "TYPE_CHECKING":
        return True
    if isinstance(test, ast.Compare):
        left = test.left
        if isinstance(left, ast.Name) and left.id == "__name__":
            return True
    return False


def collect(path: Path) -> list[Mutant]:
    src = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    starts = _line_starts(src)
    out: list[Mutant] = []

    def seg(node: ast.AST) -> tuple[int, int, str]:
        a = _offset(starts, node.lineno, node.col_offset)
        b = _offset(starts, node.end_lineno, node.end_col_offset)
        return a, b, src[a:b]

    # Booleans passed as keyword arguments are excluded. Measured on this package they
    # are almost all equivalent mutants -- flipping ``exist_ok=True`` or
    # ``ensure_ascii=False`` changes an implementation detail that no test should be
    # pinning -- and a survivor list padded with them is a list nobody reads.
    kwarg_bools: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, bool):
                    kwarg_bools.add(id(kw.value))

    for node in ast.walk(tree):
        # 1. Guard removal / forcing. The single highest-value operator here.
        if isinstance(node, ast.If) and not _skip_guard(node):
            a, b, text = seg(node.test)
            for repl in ("False", "True"):
                if text.strip() == repl:
                    continue
                out.append(Mutant(path, node.test.lineno, "guard", text, repl, a, b))

        # 2. Comparison flip. Off-by-one and inverted-condition defects.
        elif isinstance(node, ast.Compare) and len(node.ops) == 1:
            op = type(node.ops[0])
            if op in _COMPARISONS:
                left_a, _, _ = seg(node.left)
                _, right_b, _ = seg(node.comparators[0])
                _, _, whole = seg(node)
                a2, b2, op_text = left_a, right_b, whole
                new = f"{seg(node.left)[2]} {_COMPARISONS[op]} {seg(node.comparators[0])[2]}"
                out.append(Mutant(path, node.lineno, "compare", op_text, new, a2, b2))

        # 3. Boolean constant flip. Catches a default that nothing pins.
        elif (
            isinstance(node, ast.Constant)
            and isinstance(node.value, bool)
            and id(node) not in kwarg_bools
        ):
            a, b, text = seg(node)
            out.append(
                Mutant(path, node.lineno, "bool", text, str(not node.value), a, b)
            )

    return out


def _tests_for(path: Path, fallback: str) -> list[str]:
    """The test files that speak to this module, or the fallback selector.

    Narrow on purpose: a mutant that runs the whole suite costs four minutes, and the
    mapped subset costs seconds. A mutant whose module has no matching test file runs the
    fallback, so nothing is skipped for want of a naming convention.
    """
    stem = path.stem
    roots = [Path("tests/unit_tests"), Path("tests/agents")]
    hits: list[str] = []

    # A module and its tests do not always share a name, and guessing wrong costs the
    # whole fallback suite per mutant. Aliases are cheap to add and each one turns a
    # sixteen-second run into a three-second one.
    aliases = {
        "comment_watcher": ("watcher",),
        "cursor_store": ("store",),
        "clouddoc_tools": ("toolkit", "authz", "apply_direct"),
        "turn_prompt": ("thread_prompt", "conventions"),
        "watch_registry": ("watch_registry", "watch_gate"),
        "panel": ("panel", "revert"),
        "google_provider": ("clouddoc_provider",),
        "google_formats": ("clouddoc_formats",),
        "feishu_formats": ("clouddoc_formats", "feishu_provider"),
        "textmap": ("clouddoc_formats",),
        "provider": ("provider_contract", "clouddoc_provider"),
    }
    patterns = [stem, stem.replace("_", "")] + list(aliases.get(stem, ()))

    # Matches are kept only if they also name the package. Without that, "store" pulls in
    # every test_*store*.py in the tree and "watcher" finds the git diff watcher: extra
    # tests cannot hide a survivor, but they turn a three-second mutant into a minute and
    # make a full run something nobody waits for.
    package = path.parent.name
    for root in roots:
        if not root.exists():
            continue
        for pat in patterns:
            for candidate in root.rglob(f"test_*{pat}*.py"):
                name = candidate.name
                if package not in name and pat not in (stem, stem.replace("_", "")):
                    continue
                if package not in name and package not in str(candidate.parent):
                    continue
                if str(candidate) not in hits:
                    hits.append(str(candidate))
    return hits or ["-k", fallback]


# pytest's exit codes, and why only one of them means the mutant died.
#
# The first version of this file read "non-zero" as a kill. It also passed --timeout,
# which needs a plugin this repo does not install, so **every run exited 4 -- a usage
# error -- and every mutant was scored as killed**. It reported 727 mutants and a 100%
# score without having executed a single test, and that number was believed twice before
# an 80%-covered module scoring 100% finally looked wrong enough to check.
#
# So the mapping is explicit. Only "tests ran and something failed" is a kill; a suite
# that could not start has judged nothing.
_EXIT = {
    0: "survived",   # everything passed: nothing noticed the mutation
    1: "killed",     # a test failed: something noticed
    2: "error",      # interrupted
    3: "error",      # internal error
    4: "error",      # usage error -- the suite never ran
    5: "error",      # no tests collected -- nothing was asked
}


def _verdict(code: int) -> str:
    return _EXIT.get(code, "error")


def baseline_ok(files: list[Path], fallback: str, timeout: int) -> tuple[bool, str]:
    """Run the mapped tests unmutated, and require them to pass.

    Without this the run cannot mean anything: if the suite is already red, or cannot
    start, every mutant looks killed and the score reads 100%. A mutation runner has to
    prove it can tell the two apart before it reports on anything, which is the check the
    first version of this file did not have and needed most.
    """
    seen: list[str] = []
    for f in files:
        for arg in _tests_for(f, fallback):
            if arg not in seen:
                seen.append(arg)
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--no-cov", "-q", *seen],
        capture_output=True, text=True, timeout=timeout,
    )
    if proc.returncode == 0:
        return True, ""
    tail = (proc.stdout or proc.stderr).strip().splitlines()[-3:]
    return False, f"exit {proc.returncode}: " + " / ".join(t.strip() for t in tail)


def run_one(m: Mutant, fallback: str, timeout: int) -> tuple[Mutant, str]:
    """Apply, run, restore. Returns the mutant and one of killed/survived/error."""
    src = m.path.read_text(encoding="utf-8")
    mutated = src[: m.start] + m.replacement + src[m.end :]
    if mutated == src:
        return m, "noop"
    backup = tempfile.NamedTemporaryFile(
        "w", delete=False, encoding="utf-8", suffix=".bak"
    )
    backup.write(src)
    backup.close()
    try:
        m.path.write_text(mutated, encoding="utf-8")
        args = _tests_for(m.path, fallback)
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "--no-cov", "-q", "-x", *args],
            capture_output=True, text=True, timeout=timeout,
        )
        return m, _verdict(proc.returncode)
    except subprocess.TimeoutExpired:
        # A mutant that hangs the suite is killed by definition -- something noticed.
        return m, "killed"
    finally:
        m.path.write_text(Path(backup.name).read_text(encoding="utf-8"), encoding="utf-8")
        Path(backup.name).unlink(missing_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("target", help="file or directory to mutate")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0, help="sample at most N mutants")
    ap.add_argument("--seed", type=int, default=0, help="sampling seed, for a repeatable run")
    ap.add_argument("--kinds", default="guard,compare,bool")
    ap.add_argument("--fallback", default="clouddoc or feishu",
                    help="pytest -k selector for modules with no matching test file")
    ap.add_argument("--timeout", type=int, default=300)
    args = ap.parse_args()

    target = Path(args.target)
    files = sorted(target.rglob("*.py")) if target.is_dir() else [target]
    files = [f for f in files if f.name != "__init__.py"]

    kinds = set(args.kinds.split(","))
    mutants = [m for f in files for m in collect(f) if m.kind in kinds]
    total_found = len(mutants)
    if args.limit and len(mutants) > args.limit:
        # Sampled, and said so: a partial run that reads as a full one is the reporting
        # failure this whole exercise is about.
        random.Random(args.seed).shuffle(mutants)
        mutants = mutants[: args.limit]

    print("checking the baseline: the mapped tests must pass before any mutant means anything")
    ok, why = baseline_ok(files, args.fallback, args.timeout)
    if not ok:
        print(f"BASELINE FAILED -- {why}")
        print("Every mutant would score as killed against a suite that cannot run clean.")
        return 2
    print("baseline green\n")

    print(f"{total_found} mutants found; running {len(mutants)} with {args.jobs} workers")
    print("(mutants touch the working tree one at a time -- do not edit these files while it runs)\n")

    survived: list[Mutant] = []
    counts = {"killed": 0, "survived": 0, "error": 0, "noop": 0}
    # Serial by necessity: each mutant edits the file in place, so two at once would
    # write over each other. The jobs flag partitions by file instead.
    by_file: dict[Path, list[Mutant]] = {}
    for m in mutants:
        by_file.setdefault(m.path, []).append(m)

    def run_file(items: list[Mutant]) -> list[tuple[Mutant, str]]:
        return [run_one(m, args.fallback, args.timeout) for m in items]

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for batch in pool.map(run_file, by_file.values()):
            for m, verdict in batch:
                counts[verdict] = counts.get(verdict, 0) + 1
                if verdict == "survived":
                    survived.append(m)
                    print(f"  SURVIVED  {m.label}")

    judged = counts["killed"] + counts["survived"]
    score = (counts["killed"] / judged * 100) if judged else 0.0
    print(f"\nkilled {counts['killed']}  survived {counts['survived']}  "
          f"error {counts['error']}  -> mutation score {score:.0f}%")
    if counts["error"]:
        # Said out loud rather than folded into the score: an errored mutant was not
        # judged, and a score computed as though it had been is the failure this tool
        # exists to find, committed by the tool.
        print(f"{counts['error']} mutant(s) could not be judged -- the suite did not run "
              "for them, and they are excluded from the score above.")
    if survived:
        print("\nEach line above is a place where the code could be wrong and the suite "
              "would stay green.")
    return 1 if survived else 0


if __name__ == "__main__":
    raise SystemExit(main())
