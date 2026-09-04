"""The library boundary, pinned (§25.5, B0's acceptance criterion).

The clouddoc package is on its way to the standalone mandate-mcp repository, and
the extraction is a move rather than a rewrite exactly as long as these hold. A
new import that breaks one of them is not a style problem -- it is a weld to the
host that someone will have to cut again later, under worse conditions.
"""

from __future__ import annotations

import re
from pathlib import Path

PKG = Path("jiuwenswarm/agents/harness/common/tools/clouddoc")

# The two documented exceptions, each a *lazy default* a constructor can override:
# the IC-3 grant checker (cut ③) and the deployment seam (cut ④). Everything else
# in the package must not know the host exists.
ALLOWED = {
    ("clouddoc_tools.py", "jiuwenswarm.gateway.clouddoc.watch_registry"),
    ("deployment.py", "jiuwenswarm.common.config"),
    ("deployment.py", "jiuwenswarm.common.utils"),
}


def _imports(path: Path) -> set[str]:
    src = path.read_text(encoding="utf-8")
    return set(re.findall(
        r"(?:from|import)\s+(jiuwenswarm\.gateway[\w.]*|jiuwenswarm\.common[\w.]*|openjiuwen[\w.]*)",
        src,
    ))


def test_the_library_layer_stays_host_free():
    offences = []
    for f in sorted(PKG.glob("*.py")):
        for mod in _imports(f):
            if mod.startswith("openjiuwen"):
                offences.append(f"{f.name}: {mod} (host framework)")
                continue
            if any(f.name == fn and mod.startswith(allowed) for fn, allowed in ALLOWED):
                continue
            kind = "reverse import" if mod.startswith("jiuwenswarm.gateway") else "deployment leak"
            offences.append(f"{f.name}: {mod} ({kind})")
    assert not offences, "库层出现宿主焊点：\n" + "\n".join(offences)


def test_the_bridge_lives_outside_the_package():
    """openjiuwen translation is jiuwenswarm's own adapter and stays behind at
    extraction; inside the package it would defeat the point of cut ①."""
    bridge = Path("jiuwenswarm/agents/harness/common/tools/clouddoc_bridge.py")
    assert bridge.exists()
    assert "openjiuwen" in bridge.read_text(encoding="utf-8")
    assert not (PKG / "clouddoc_bridge.py").exists()
