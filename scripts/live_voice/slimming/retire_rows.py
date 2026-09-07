"""Revalidate manifest rows on a revision and scan retire candidates for callers.

Usage: python retire_rows.py --manifest PATH|REV:PATH --rev REV [--base REV] [--code CONSOLIDATE_RETIRE]
For every row whose path changed since --base (every row when --base is omitted) check that each
stable symbol still appears in the file at --rev. For whole-file rows of --code, scan production and
test importers with exact module boundaries (TypeScript imports may carry .js/.ts suffixes).
"""
from __future__ import annotations

import argparse
import os
import re

from _common import git, manifest_rows, read_manifest, show, symbol_names


def importers(rev: str, path: str, files: list[str], cache: dict) -> list[str]:
    base = os.path.splitext(os.path.basename(path))[0]
    if path.endswith(".py"):
        module = path[:-3].replace("/", ".")
        pattern = re.compile(
            r"(^\s*from\s+" + re.escape(module) + r"\s+import|^\s*import\s+" + re.escape(module) + r"\b"
            r"|from\s+\.\s*import\s+[^\n]*\b" + re.escape(base) + r"\b|from\s+\.\s*" + re.escape(base) + r"\s+import)",
            re.M,
        )
    else:
        quote = "['\"]"
        pattern = re.compile(
            r"from\s+" + quote + r"[^'\"]*/" + re.escape(base) + r"(\.js|\.ts|\.tsx)?" + quote
            + r"|import\(" + quote + r"[^'\"]*/" + re.escape(base) + r"(\.js|\.ts)?" + quote
        )
    hits = []
    for f in files:
        if f == path:
            continue
        if f not in cache:
            cache[f] = show(rev, f)
        if pattern.search(cache[f]):
            hits.append(f)
    return hits


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--rev", required=True)
    ap.add_argument("--base")
    ap.add_argument("--code", default="CONSOLIDATE_RETIRE")
    args = ap.parse_args()
    index, rows = manifest_rows(read_manifest(args.manifest))
    if args.base:
        changed = set(git("diff", "--name-only", f"{args.base}..{args.rev}", "--", "jiuwenswarm", "packages").splitlines())
    else:
        changed = {r["path"] for r in rows}
    checked = present = 0
    missing: list[tuple] = []
    texts: dict = {}
    for row in rows:
        if row["path"] not in changed:
            continue
        if row["path"] not in texts:
            texts[row["path"]] = show(args.rev, row["path"])
        text = texts[row["path"]]
        for name in symbol_names(row["symbols"]):
            checked += 1
            comps = [c for c in re.split(r"[.:#]+", name) if c]
            if text and all(re.search(r"\b" + re.escape(c) + r"\b", text) for c in comps):
                present += 1
            else:
                missing.append((row["id"], row["code"], row["path"].split("/")[-1], name, "FILE DELETED" if not text else ""))
    print(f"stable symbols checked {checked}, present {present}, missing {len(missing)}")
    for m in missing:
        print("   MISSING", *m)
    tracked = git("ls-tree", "-r", "--name-only", args.rev, "jiuwenswarm", "tests").splitlines()
    prod = [f for f in tracked if f.endswith((".py", ".ts", ".tsx", ".js", ".mjs")) and f.startswith("jiuwenswarm/")
            and "/tests/" not in f and not os.path.basename(f).startswith("test_") and ".test." not in f]
    tests = [f for f in tracked if f.endswith((".py", ".mjs", ".ts", ".js")) and ("/tests/" in f or f.startswith("tests/"))]
    whole = [p for p, meta in index.items() if meta["codes"] and all(c == args.code for c in meta["codes"])]
    print(f"\nwhole-file {args.code} paths: {len(whole)}")
    cache: dict = {}
    for p in whole:
        text = show(args.rev, p)
        if not text:
            print(f"   deleted  {p}")
            continue
        prod_hits = importers(args.rev, p, prod, cache)
        test_hits = importers(args.rev, p, tests, cache)
        names = [os.path.basename(x) for x in prod_hits][:4]
        print(f"   {len(text.splitlines()):6d} {p.split('/')[-1]:<48} prod={len(prod_hits)} {names} tests={len(test_hits)}")


if __name__ == "__main__":
    main()
