"""Per-file production symbol delta between two revisions.

Usage: python symbol_delta.py BASE HEAD [PATH ...]
Python: top-level class/def, one-level Class.method and UPPER constants (ast).
TypeScript: export declarations (regex). Output is physical LOC and +/- symbols per file.
"""
from __future__ import annotations

import ast
import re
import sys

from _common import git, show

TS_RE = re.compile(
    r"^export\s+(?:default\s+)?(?:async\s+)?"
    r"(?:function\*?|class|const|let|var|type|interface|enum|abstract class)\s+([A-Za-z_$][\w$]*)",
    re.M,
)


def py_symbols(text: str) -> set[str]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return set()
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
        elif isinstance(node, ast.ClassDef):
            names.add(node.name)
            for member in node.body:
                if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    names.add(f"{node.name}.{member.name}")
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.isupper():
                    names.add(target.id)
    return names


def symbols(text: str, path: str) -> set[str]:
    if path.endswith(".py"):
        return py_symbols(text)
    if path.endswith((".ts", ".tsx")):
        return set(TS_RE.findall(text))
    return set()


def main() -> None:
    base, head, *paths = sys.argv[1:]
    paths = paths or ["jiuwenswarm", "packages", "scripts/live_voice"]
    total_added = total_removed = 0
    for line in git("diff", "--name-status", "-M", f"{base}..{head}", "--", *paths).splitlines():
        parts = line.split("\t")
        status = parts[0]
        old, new = (parts[1], parts[2]) if status.startswith("R") else (parts[1], parts[1])
        if not new.endswith((".py", ".ts", ".tsx")):
            continue
        before = show(base, old) if status != "A" else ""
        after = show(head, new) if status != "D" else ""
        added = sorted(symbols(after, new) - symbols(before, old))
        removed = sorted(symbols(before, old) - symbols(after, new))
        total_added += len(added)
        total_removed += len(removed)
        print(f"{status}\t{new}\tLOC {len(before.splitlines())}->{len(after.splitlines())}"
              f"\t+sym {len(added)} -sym {len(removed)}")
        if added:
            print("   +", ", ".join(added))
        if removed:
            print("   -", ", ".join(removed))
    print(f"TOTAL +sym {total_added} -sym {total_removed}")


if __name__ == "__main__":
    main()
