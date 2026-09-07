"""Per-file symbol inventory of the dedicated LiveVoice production files with production-caller counts.

Usage: python symbol_inventory.py --rev HEAD --out live-voice/LIVEVOICE_DESIGN_SIMPLIFICATION_INVENTORY_2026-09-07.md [--json OUT]

For every dedicated LiveVoice production file (module bucketing as in module_buckets.py) the script
lists the top-level symbols (Python: classes, functions, module constants; TypeScript: exports) with
their physical LOC, a kind (value / owner / exception / function / constant / export) and the number
of *other* production files that import the module and mention the symbol. "Production" means every
tracked file under ``jiuwenswarm`` that is not a test. Counting is static and name-based, so a symbol
mentioned through re-exports or dynamic access is undercounted; treat ``callers = 0`` as "verify by
grep before deleting", not as proof.
"""
from __future__ import annotations

import argparse
import ast
import io
import json
import os
import re
import sys
import warnings
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from module_buckets import EXTRA, RULES  # noqa: E402
from _common import SHARED_HOSTS, git, show  # noqa: E402

OWNER_RX = re.compile(r"Owner|Authority|Lease|Registry|Runtime|Adapter|Route|Journal|Ledger|Store|Core|Fence|Resolver|Arbiter|Bridge|Harness|Collector|Exporter|Session|Handle|Service|Gate|Engine|Loop", re.I)


def is_value_class(node: ast.ClassDef) -> bool:
    decos = [ast.unparse(d) for d in node.decorator_list]
    bases = [ast.unparse(b) for b in node.bases]
    return any("dataclass" in d for d in decos) or any(re.search(r"Enum|NamedTuple|TypedDict|Protocol", b) for b in bases)


def py_symbols(text: str) -> list[dict]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        tree = ast.parse(text)
    out = []
    for n in tree.body:
        if isinstance(n, ast.ClassDef):
            kind = "value" if is_value_class(n) else ("exception" if any(re.search(r"Exception|Error", ast.unparse(b)) for b in n.bases) else ("owner" if OWNER_RX.search(n.name) else "class"))
            out.append({"name": n.name, "kind": kind, "loc": n.end_lineno - n.lineno + 1, "public": not n.name.startswith("_")})
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.append({"name": n.name, "kind": "function", "loc": n.end_lineno - n.lineno + 1, "public": not n.name.startswith("_")})
        elif isinstance(n, (ast.Assign, ast.AnnAssign)):
            targets = [t.id for t in getattr(n, "targets", []) if isinstance(t, ast.Name)] if isinstance(n, ast.Assign) else ([n.target.id] if isinstance(n.target, ast.Name) else [])
            for t in targets:
                if t.isupper() or t.startswith("_") is False and t[:1].isupper():
                    out.append({"name": t, "kind": "constant", "loc": n.end_lineno - n.lineno + 1, "public": not t.startswith("_")})
    return out


TS_EXPORT_RX = re.compile(r"^export\s+(?:default\s+)?(?:async\s+)?(?:abstract\s+)?(function|const|let|class|interface|type|enum)\s+([A-Za-z_$][\w$]*)", re.M)


def ts_symbols(text: str) -> list[dict]:
    lines = text.splitlines()
    out = []
    for m in TS_EXPORT_RX.finditer(text):
        start = text.count("\n", 0, m.start())
        depth = 0
        end = start
        opened = False
        for j in range(start, min(len(lines), start + 2000)):
            depth += lines[j].count("{") - lines[j].count("}")
            if "{" in lines[j]:
                opened = True
            if opened and depth <= 0:
                end = j
                break
            if not opened and lines[j].rstrip().endswith(";"):
                end = j
                break
        kind = {"interface": "type", "type": "type", "enum": "type", "class": "class", "function": "function", "const": "const", "let": "const"}[m.group(1)]
        out.append({"name": m.group(2), "kind": kind, "loc": end - start + 1, "public": True})
    return out


def module_key(path: str) -> str:
    if path.endswith(".py"):
        return path[:-3].replace("/", ".")
    return re.sub(r"\.(ts|tsx|js)$", "", path.rsplit("/", 1)[-1])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rev", default="HEAD")
    ap.add_argument("--out")
    ap.add_argument("--json")
    args = ap.parse_args()
    tracked = [f for f in git("ls-tree", "-r", "--name-only", args.rev, "jiuwenswarm").splitlines()
               if f.endswith((".py", ".ts", ".tsx", ".js")) and "/tests/" not in f and ".test." not in f and "node_modules" not in f]
    texts = {f: show(args.rev, f) for f in tracked}
    dedicated = [f for f in tracked
                 if (re.search(r"live_voice|live-voice|LiveVoice", f) or any(f.endswith(e) for e in EXTRA))
                 and not any(s in f for s in SHARED_HOSTS)]
    # importer index: which production files import which module key
    importers: dict[str, list[str]] = defaultdict(list)
    for f, text in texts.items():
        for d in dedicated:
            if d == f:
                continue
            key = module_key(d)
            if d.endswith(".py"):
                short = key.rsplit(".", 1)[-1]
                if re.search(r"(from\s+[\w.]*\b%s\b\s+import|import\s+[\w.]*\b%s\b)" % (re.escape(short), re.escape(short)), text):
                    importers[d].append(f)
            else:
                if re.search(r"from\s+['\"][^'\"]*/%s(\.js)?['\"]" % re.escape(key), text):
                    importers[d].append(f)
    modules: dict[str, list] = defaultdict(list)
    payload = []
    for d in dedicated:
        module = next((m for m, rx in RULES if re.search(rx, d)), "?? unassigned")
        text = texts[d]
        syms = py_symbols(text) if d.endswith(".py") else ts_symbols(text)
        users = importers.get(d, [])
        for s in syms:
            callers = [u for u in users if re.search(r"\b%s\b" % re.escape(s["name"]), texts[u])]
            s["callers"] = len(callers)
            s["caller_names"] = [c.split("jiuwenswarm/", 1)[-1] for c in callers[:3]]
            # mentions inside the defining file beyond the definition itself (factories, same-file use)
            s["internal"] = max(0, len(re.findall(r"\b%s\b" % re.escape(s["name"]), text)) - 1)
        entry = {"path": d.split("jiuwenswarm/", 1)[-1], "module": module, "loc": len(text.splitlines()), "importers": len(users), "symbols": syms}
        modules[module].append(entry)
        payload.append(entry)
    if args.json:
        io.open(args.json, "w", encoding="utf-8").write(json.dumps(payload, ensure_ascii=False, indent=1))
    lines = ["# LiveVoice 设计简化：逐文件 symbol 清单（自动生成）", "",
             f"> 由 `scripts/live_voice/slimming/symbol_inventory.py --rev {args.rev}` 生成；口径见脚本 docstring。",
             "> `callers` 是导入该模块并提及该 symbol 的**其他生产文件**数；`文件内引用` 是定义之外在本文件内的提及次数（工厂、同文件使用）。两者都为 0 才是静态无引用，删除前仍需 grep 复核。",
             "> 每个文件按 symbol 行数降序，最多列前 40 个。", ""]
    for module in sorted(modules):
        files = sorted(modules[module], key=lambda e: -e["loc"])
        total = sum(e["loc"] for e in files)
        lines += [f"## {module}（{len(files)} 文件，{total:,} 行）", ""]
        for e in files:
            zero = sum(1 for s in e["symbols"] if s["callers"] == 0 and s["internal"] == 0 and s["public"])
            lines += [f"### `{e['path']}`（{e['loc']:,} 行；被 {e['importers']} 个生产文件导入；{len(e['symbols'])} 个顶层 symbol，其中 {zero} 个公开 symbol 在其他生产文件与本文件内都无引用）", "",
                      "| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |", "|---|---|---:|---:|---:|---|"]
            for s in sorted(e["symbols"], key=lambda s: -s["loc"])[:40]:
                lines.append(f"| `{s['name']}` | {s['kind']} | {s['loc']} | {s['callers']} | {s['internal']} | {', '.join(s['caller_names'])} |")
            lines.append("")
    text = "\n".join(lines) + "\n"
    if args.out:
        io.open(args.out, "w", encoding="utf-8", newline="\n").write(text)
        print("written", args.out, len(lines), "lines")
    else:
        print(text[:4000])


if __name__ == "__main__":
    main()
