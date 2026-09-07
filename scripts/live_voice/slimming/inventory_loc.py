"""Recompute the attributable production inventory against the atomic manifest.

Usage: python inventory_loc.py --manifest PATH|REV:PATH --base REV --head REV
Reports dedicated whole-file LOC at both revisions, deleted and new production paths, modified
inventoried paths and shared-host whole-file drift (shared segments are not re-attributed here).
"""
from __future__ import annotations

import argparse

from _common import git, is_shared, manifest_rows, read_manifest, show

PRODUCTION_ROOTS = ("jiuwenswarm", "packages")


def loc(rev: str, path: str) -> int:
    return len(show(rev, path).splitlines())


def exists(rev: str, path: str) -> bool:
    return bool(git("ls-tree", "--name-only", rev, "--", path).strip())


def is_production(path: str) -> bool:
    return (path.startswith(PRODUCTION_ROOTS) and "/tests/" not in path and ".test." not in path
            and path.endswith((".py", ".ts", ".tsx", ".js")))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--base", required=True)
    ap.add_argument("--head", required=True)
    args = ap.parse_args()
    index, _rows = manifest_rows(read_manifest(args.manifest))
    dedicated = [p for p in index if not is_shared(p)]
    shared = [p for p in index if is_shared(p)]
    changed: dict[str, str] = {}
    for line in git("diff", "--name-status", "-M", f"{args.base}..{args.head}", "--", *PRODUCTION_ROOTS).splitlines():
        parts = line.split("\t")
        changed[parts[-1]] = parts[0]
    ded_base = sum(loc(args.base, p) for p in dedicated)
    ded_head = sum(loc(args.head, p) for p in dedicated)
    deleted = [p for p in dedicated if not exists(args.head, p)]
    new_paths = sorted(p for p, st in changed.items() if st == "A" and p not in index and is_production(p))
    new_loc = sum(loc(args.head, p) for p in new_paths)
    modified = sorted(p for p, st in changed.items() if p in index and st != "D")
    print(f"manifest paths {len(index)} (dedicated {len(dedicated)}, shared {len(shared)})")
    print(f"dedicated whole-file LOC: {args.base} {ded_base:,} -> {args.head} {ded_head:,}")
    print(f"deleted inventoried paths at {args.head}: {len(deleted)}")
    for p in deleted:
        print(f"   {p}")
    print(f"new production paths outside the manifest: {len(new_paths)} files, {new_loc:,} LOC")
    for p in new_paths:
        print(f"   {loc(args.head, p):6d} {p}")
    print(f"dedicated total at {args.head}: {ded_head + new_loc:,} (= {ded_head:,} + {new_loc:,})")
    print(f"modified inventoried paths: {len(modified)}")
    drift = [(p, loc(args.base, p), loc(args.head, p)) for p in shared]
    drift = [d for d in drift if d[1] != d[2]]
    print(f"shared-host whole-file drift (segments not re-attributed): {len(drift)} files")
    for p, b, h in drift:
        print(f"   {b} -> {h} {p}")


if __name__ == "__main__":
    main()
