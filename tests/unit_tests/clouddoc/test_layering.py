"""Imports inside ``jiuwenswarm.clouddoc`` go one way only.

The order, bottom to top: providers (base, kinds, textmap, formats, then the
platforms, then factory and routing); the write rails, receipts, the work-mode
file, authority and state; tools; watch; panel; host. A module may import from its own layer or
below. Only ``host`` and ``settings`` may import the agent runtime or the gateway;
``jiuwenswarm.common`` is open to all. The rest of the package must not know which
program runs it.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[3] / "jiuwenswarm" / "clouddoc"
PKG = "jiuwenswarm.clouddoc."

LAYERS = {
    "wording": 0, "settings": 0,
    "providers": 1,
    "edits": 2, "receipts": 2, "workmode": 2, "authority": 2, "state": 2,
    "tools": 3,
    "watch": 4,
    "panel": 5,
    "host": 6,
}
PROVIDER_SUBLAYERS = {"base": 0, "kinds": 0, "textmap": 0, "formats": 0, "google": 1, "feishu": 1, "factory": 2, "routing": 2}
# The agent runtime and the gateway. ``jiuwenswarm.common`` is the shared utility
# layer (configuration helpers, message schema) and is open to every module.
HOST_PREFIXES = ("jiuwenswarm.server", "jiuwenswarm.gateway", "jiuwenswarm.agents", "jiuwenswarm.runtime", "jiuwenswarm.extensions", "openjiuwen")
MAY_IMPORT_HOST = ("settings", "host")


def _modules():
    for path in sorted(ROOT.rglob("*.py")):
        rel = path.relative_to(ROOT).with_suffix("").as_posix().replace("/", ".")
        if rel.endswith("__init__"):
            rel = rel[: -len(".__init__")] or "__init__"
        yield rel, path


def _imports(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            yield node.module
        elif isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name


def _layer(rel):
    return LAYERS.get(rel.split(".")[0])


def _provider_sublayer(rel):
    parts = rel.split(".")
    return PROVIDER_SUBLAYERS.get(parts[1]) if parts[0] == "providers" and len(parts) > 1 else None


@pytest.mark.parametrize("rel, path", [m for m in _modules() if m[0] != "__init__"])
def test_a_module_imports_only_from_its_layer_or_below(rel, path):
    mine = _layer(rel)
    assert mine is not None, f"{rel}: not assigned to a layer in this test"
    for mod in _imports(path):
        if mod.startswith(PKG):
            target = mod[len(PKG):]
            theirs = _layer(target)
            assert theirs is not None, f"{rel} imports {mod}, which has no layer"
            assert theirs <= mine, f"{rel} (layer {mine}) imports upward from {target} (layer {theirs})"
            if mine == theirs == LAYERS["providers"]:
                a, b = _provider_sublayer(rel), _provider_sublayer(target)
                if a is not None and b is not None:
                    assert b <= a, f"{rel} imports upward within providers from {target}"
        elif mod.startswith(HOST_PREFIXES):
            assert rel.split(".")[0] in MAY_IMPORT_HOST, f"{rel} imports the host application ({mod}); only settings and host may"
