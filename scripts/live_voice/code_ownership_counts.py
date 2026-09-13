"""Reproducible production ownership accounting against the integration baselines.

Physical lines include comments/blanks. Existing-file totals are reported
separately from additions: a modified pre-existing module is not all new code.
Run from the Host repository; the SDK is its sibling agent-core checkout.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import subprocess
from pathlib import Path

HOST_BASE = "8c7bfecdf0cc7607b07763fe687e08bf24f6ab83"
SDK_BASE = "b5f189ba1054a338d8fa3e009b13053776340e44"
EXTENSIONS = {".py", ".js", ".jsx", ".ts", ".tsx", ".css", ".scss", ".vue", ".html"}


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args])


def production(path, prefix):
    parts = Path(path).parts
    return path.startswith(prefix) and Path(path).suffix in EXTENSIONS and not any(
        part in {"node_modules", "dist", "tests", "__pycache__"} for part in parts
    ) and not any(mark in path for mark in (".test.", ".spec."))


def owner(path, sdk):
    if sdk:
        return "agentcore"
    normalized = path.lower().replace("-", "_")
    voice = any(part in normalized for part in (
        "/channels/live_voice/", "/gateway/live_voice/", "/common/live_voice",
        "/livevoice", "/live_voice",
    ))
    # Shared schema types and Host runtime services retain application ownership.
    if "/common/schema/" in normalized or "/server/runtime/" in normalized:
        voice = False
    return "voice" if voice else "jiuwenswarm"


def count_repository(root, baseline, sdk=False):
    changed = set(git(root, "diff", "--name-only", "--no-renames", baseline).decode().splitlines())
    changed.update(git(root, "ls-files", "--others", "--exclude-standard").decode().splitlines())
    rows = []
    for path in sorted(changed):
        if not production(path, "openjiuwen/" if sdk else "jiuwenswarm/"):
            continue
        exists = subprocess.run(["git", "-C", str(root), "cat-file", "-e", f"{baseline}:{path}"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
        old = git(root, "show", f"{baseline}:{path}") if exists else b""
        current = (root/path).read_bytes() if (root/path).is_file() else b""
        before, after = old.splitlines(), current.splitlines()
        added = removed = 0
        for tag, a, b, c, d in difflib.SequenceMatcher(None, before, after, autojunk=False).get_opcodes():
            if tag != "equal":
                added += d-c
                removed += b-a
        rows.append(dict(path=path, owner=owner(path, sdk), new_file=not exists,
                         current_lines=len(after), baseline_lines=len(before),
                         added_lines=added, removed_lines=removed, net_lines=len(after)-len(before),
                         sha256=hashlib.sha256(current).hexdigest()))
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    host = Path(__file__).resolve().parents[2]
    rows = count_repository(host, HOST_BASE) + count_repository(host.parent/"agent-core", SDK_BASE, True)
    totals = {}
    for group in ("voice", "jiuwenswarm", "agentcore"):
        entries = [row for row in rows if row["owner"] == group]
        totals[group] = {key: sum(row[key] for row in entries) for key in
                         ("current_lines", "baseline_lines", "added_lines", "removed_lines", "net_lines")}
        totals[group]["new_file_lines"] = sum(row["current_lines"] for row in entries if row["new_file"])
        totals[group]["current_files"] = sum(row["current_lines"] > 0 for row in entries)
    result = dict(stage=args.stage, host_baseline=HOST_BASE, sdk_baseline=SDK_BASE,
                  line_metric="physical; comments/blanks included; tests/docs/config/binaries excluded",
                  attribution="changed production files against official compatible baselines; modified-file totals are not all additions",
                  totals=totals, files=rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    print(json.dumps(totals, indent=2))


if __name__ == "__main__":
    main()
