#!/usr/bin/env python3
"""Find things that are written and never read: dead calls, dead keys, dead fields.

The recurring defect in this codebase is not a wrong line. It is a right-looking line
that nothing reaches. Three review rounds turned up, among others:

* ``CloudDocCommentWatcher._apply`` -- forty-seven lines of the most dangerous logic in
  the feature (it writes to a shared document), with no caller. It had been retired and
  left in the tree, and nothing in the code said so.
* ``ReceiptStore.pending`` -- documented as feeding a startup sweep that did not exist.
  Four tests called it; production never did, so every crash-window receipt stayed
  unadjudicated and the file grew without bound.
* ``has_revision_control`` and three sibling capability flags -- measured, declared,
  asserted in tests, read by nothing. Reasoning that leaned on them ("declare it false
  and admission tightens") leaned on air.
* an i18n key added in the same session as this script's first draft, used nowhere.

None of these is visible to coverage, which reports a line as covered when a *test*
executed it. They are all visible to a caller search, which is what this does.

Findings are candidates, not verdicts: an entry point, a protocol method or a field
serialised for a person to read is legitimately callerless. The point is that each one
should be a decision somebody made rather than something nobody noticed.

Usage:
    python scripts/reachability_probe.py jiuwenswarm/gateway/clouddoc
    python scripts/reachability_probe.py <path> --i18n <locale.json> --ui <dir>
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
from pathlib import Path

# Callable from outside by contract rather than by name, so a missing caller says
# nothing. Dunders, and the async/context-manager protocols.
_PROTOCOL = re.compile(r"^__\w+__$|^(setUp|tearDown)$")


def _sources(root: Path) -> list[Path]:
    return [p for p in root.rglob("*.py") if "__pycache__" not in p.parts]


def _grep_count(name: str, paths: list[str]) -> int:
    """How many times a name appears across paths, definitions excluded.

    Text search rather than a call graph: Python's dynamic dispatch means a real call
    graph needs type inference, and the failure mode of this cruder tool -- reporting
    something that is in fact reached -- is a minute of reading, while the failure mode
    of missing one is what these rounds have been finding.
    """
    if not paths:
        return 0
    proc = subprocess.run(
        ["grep", "-rn", "--include=*.py", f"\\b{name}\\b", *paths],
        capture_output=True, text=True,
    )
    hits = [
        line for line in proc.stdout.splitlines()
        if not re.search(rf"(def|class)\s+{re.escape(name)}\b", line)
    ]
    return len(hits)


def private_methods_without_callers(root: Path, extra: list[str]) -> list[str]:
    """Private methods (`_name`) that nothing calls, anywhere."""
    out: list[str] = []
    search = [str(root), *extra]
    for path in _sources(root):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            name = node.name
            if not name.startswith("_") or _PROTOCOL.match(name):
                continue
            if _grep_count(name, search) == 0:
                out.append(f"{path}:{node.lineno} {name}() 没有任何调用方")
    return out


def public_api_used_only_by_tests(
    root: Path, tests: list[str], prod: list[str]
) -> list[str]:
    """Public functions and methods that only the tests call.

    ``pending`` is the case this exists for: a green test suite around a function that
    production never reaches reads as coverage of a working feature.
    """
    out: list[str] = []
    for path in _sources(root):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            name = node.name
            if name.startswith("_"):
                continue
            # **The whole production tree, not just this package.** Searching only the
            # root reported ``ReceiptStore.commit`` as test-only, when its callers are
            # the providers one package over -- a tool that cries wolf on its most
            # obvious cases is one nobody runs twice.
            in_prod = _grep_count(name, prod)
            if in_prod:
                continue
            if _grep_count(name, tests) > 0:
                out.append(
                    f"{path}:{node.lineno} {name}() 只被测试调用，生产代码从不调用它"
                )
    return out


def unused_i18n_keys(locale: Path, ui_dirs: list[str]) -> list[str]:
    """Translation keys defined and never referenced by the UI."""
    data = json.loads(locale.read_text(encoding="utf-8"))
    keys: list[str] = []

    def walk(node, prefix=""):
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, f"{prefix}{k}." if not isinstance(v, str) else f"{prefix}{k}")
        elif isinstance(node, str) and prefix:
            keys.append(prefix)

    walk(data)
    if not ui_dirs:
        return []
    proc = subprocess.run(
        ["grep", "-rho", "-E", r"[a-zA-Z0-9_.]+", *ui_dirs], capture_output=True, text=True
    )
    seen = set(proc.stdout.split())
    return [f"{locale}: 键 {k} 定义了但界面从未引用" for k in keys if k not in seen]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("root")
    ap.add_argument("--tests", default="tests")
    ap.add_argument("--also-search", nargs="*", default=["jiuwenswarm"],
                    help="paths a caller could live in besides the root")
    ap.add_argument("--i18n", default="")
    ap.add_argument("--ui", nargs="*", default=[])
    args = ap.parse_args()

    root = Path(args.root)
    findings: list[str] = []
    findings += private_methods_without_callers(root, args.also_search)
    findings += public_api_used_only_by_tests(root, [args.tests], args.also_search)
    if args.i18n:
        findings += unused_i18n_keys(Path(args.i18n), args.ui)

    for f in findings:
        print(f"  {f}")
    print(f"\n{len(findings)} 处「写了但没人走」的候选")
    if findings:
        print("每一条都可能是合理的（入口、协议方法、给人读的序列化字段）——"
              "要的是它是有人做过的决定，而不是没人注意到。")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
