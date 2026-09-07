"""Per-module design anatomy of LiveVoice at a revision: value types, guards, owners, codecs, exceptions.

Usage: python anatomy_modules.py --rev HEAD --json OUT
Buckets reuse module_buckets.RULES / EXTRA / SHARED_HOSTS (filename rules).
"""
from __future__ import annotations

import argparse
import ast
import io
import json
import re
import sys
import tokenize
import warnings
from collections import defaultdict

sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
from module_buckets import EXTRA, RULES  # noqa: E402
from _common import SHARED_HOSTS, git, show  # noqa: E402

OWNER_RX = re.compile(r"Owner|Authority|Lease|Registry|Runtime|Adapter|Route|Journal|Ledger|Store|Core|Fence|Resolver|Arbiter|Bridge|Harness|Collector|Exporter|Session|Handle", re.I)


def is_value_class(node: ast.ClassDef) -> bool:
    decos = [ast.unparse(d) for d in node.decorator_list]
    bases = [ast.unparse(b) for b in node.bases]
    return any("dataclass" in d for d in decos) or any(re.search(r"Enum|NamedTuple|TypedDict|Protocol", b) for b in bases)


def py_anatomy(text: str) -> dict:
    a = defaultdict(int)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        tree = ast.parse(text)
    lines = text.splitlines()
    a["loc"] = len(lines)
    a["blank"] = sum(1 for l in lines if not l.strip())
    try:
        a["comment"] = sum(1 for tok in tokenize.generate_tokens(io.StringIO(text).readline) if tok.type == tokenize.COMMENT)
    except Exception:
        pass
    classes = []
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and n.body and isinstance(n.body[0], ast.Expr) \
                and isinstance(getattr(n.body[0], "value", None), ast.Constant) and isinstance(n.body[0].value.value, str):
            a["docstring"] += n.body[0].end_lineno - n.body[0].lineno + 1
        if isinstance(n, ast.Raise):
            a["raise"] += 1
        if isinstance(n, ast.If) and n.body and isinstance(n.body[-1], ast.Raise) and not n.orelse:
            a["guard_loc"] += n.end_lineno - n.lineno + 1
        if isinstance(n, ast.ClassDef):
            span = n.end_lineno - n.lineno + 1
            kind = "value" if is_value_class(n) else ("exception" if any(re.search(r"Exception|Error", ast.unparse(b)) for b in n.bases) else ("owner" if OWNER_RX.search(n.name) else "other"))
            classes.append((n.name, span, kind))
            a["classes"] += 1
            a[f"{kind}_classes"] += 1
            a[f"{kind}_loc"] += span
            for m in n.body:
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    a["methods"] += 1
                    ml = m.end_lineno - m.lineno + 1
                    if m.name == "__post_init__":
                        a["post_init_loc"] += ml
                    if re.search(r"snapshot|to_dict|from_dict|as_dict|to_json|from_json|to_payload|from_payload|encode|decode|serialize|canonical", m.name):
                        a["codec_loc"] += ml
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            a["functions"] += 1
    a["_classes"] = classes
    return a


def ts_anatomy(text: str) -> dict:
    a = defaultdict(int)
    lines = text.splitlines()
    a["loc"] = len(lines)
    a["blank"] = sum(1 for l in lines if not l.strip())
    a["comment"] = sum(1 for l in lines if l.strip().startswith(("//", "/*", "*")))
    a["throw"] = sum(1 for l in lines if re.search(r"\bthrow\b", l))
    a["exports"] = sum(1 for l in lines if re.match(r"^export\s+(async\s+)?(function|const|class|interface|type|enum)\b", l))
    a["type_decls"] = sum(1 for l in lines if re.match(r"^(export\s+)?(interface|type|enum)\b", l))
    depth = 0
    inside = False
    for l in lines:
        s = l.strip()
        if not inside and re.match(r"^(export\s+)?(declare\s+)?(interface|type|enum)\b", s) and s.endswith("{"):
            inside, depth = True, 0
        if inside:
            a["type_decl_loc"] += 1
            depth += s.count("{") - s.count("}")
            if depth <= 0:
                inside = False
    return a


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rev", default="HEAD")
    ap.add_argument("--json")
    ap.add_argument("--top", type=int, default=30)
    args = ap.parse_args()
    tracked = git("ls-tree", "-r", "--name-only", args.rev, "jiuwenswarm").splitlines()
    files = [f for f in tracked
             if (re.search(r"live_voice|live-voice|LiveVoice", f) or any(f.endswith(e) for e in EXTRA))
             and "/tests/" not in f and ".test." not in f and f.endswith((".py", ".ts", ".tsx", ".js"))
             and not any(s in f for s in SHARED_HOSTS)]
    modules: dict = defaultdict(lambda: defaultdict(int))
    per_file = []
    for f in files:
        module = next((m for m, rx in RULES if re.search(rx, f)), "?? unassigned")
        text = show(args.rev, f)
        a = py_anatomy(text) if f.endswith(".py") else ts_anatomy(text)
        classes = a.pop("_classes", [])
        per_file.append((a["loc"], f, module, dict(a), classes))
        m = modules[module]
        m["files"] += 1
        for k, v in a.items():
            m[k] += v
    keys = ["files", "loc", "classes", "value_classes", "value_loc", "owner_classes", "owner_loc", "exception_classes", "guard_loc", "raise", "post_init_loc", "codec_loc", "docstring", "throw", "type_decl_loc", "exports"]
    print(f"{'module':<38}" + "".join(f"{k:>10}" for k in keys[1:]))
    tot = defaultdict(int)
    for name in sorted(modules):
        m = modules[name]
        print(f"{name:<38}" + "".join(f"{m[k]:>10,}" for k in keys[1:]))
        for k in keys:
            tot[k] += m[k]
    print(f"{'TOTAL':<38}" + "".join(f"{tot[k]:>10,}" for k in keys[1:]))
    print("\n== largest files: classes by kind ==")
    for loc, f, module, a, classes in sorted(per_file, reverse=True)[: args.top]:
        short = f.split("jiuwenswarm/", 1)[-1]
        if f.endswith(".py"):
            kinds = defaultdict(int)
            for _, span, kind in classes:
                kinds[kind] += span
            print(f"{loc:6,} {module[:2]} {short}  classes {a.get('classes',0)} (value {a.get('value_classes',0)}/{a.get('value_loc',0)}, owner {a.get('owner_classes',0)}/{a.get('owner_loc',0)}, exc {a.get('exception_classes',0)}) guard {a.get('guard_loc',0)} raise {a.get('raise',0)} post_init {a.get('post_init_loc', 0)} codec {a.get('codec_loc', 0)}")
        else:
            print(f"{loc:6,} {module[:2]} {short}  throw {a.get('throw',0)} exports {a.get('exports',0)} type-decl LOC {a.get('type_decl_loc',0)}")
    if args.json:
        payload = {"modules": {k: dict(v) for k, v in modules.items()}, "files": [{"loc": loc, "path": f, "module": module, "anatomy": a, "classes": classes} for loc, f, module, a, classes in per_file]}
        io.open(args.json, "w", encoding="utf-8").write(json.dumps(payload, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
