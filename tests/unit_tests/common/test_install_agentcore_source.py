"""Exercise source reconstruction and the explicit uninstall/install boundary."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from jiuwenswarm.common.agentcore_source import AgentCoreSourceError, verify_source
from tests.unit_tests.common.test_agentcore_source import checkout, git


SPEC = importlib.util.spec_from_file_location(
    "install_agentcore_source", Path(__file__).resolve().parents[3] / "scripts/install_agentcore_source.py"
)
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


def test_reconstructs_exact_tree_with_crlf_patch_and_new_files(checkout, tmp_path):
    repo, upstream = checkout
    spec = json.loads((repo / "scripts/sdk_patches/agentcore-source.json").read_text())
    (upstream / "module.py").write_text("VALUE = 2\n", encoding="utf-8", newline="\n")
    (upstream / "new_module.py").write_text("VALUE = 3\n", encoding="utf-8", newline="\n")
    git(upstream, "add", "module.py", "new_module.py")
    spec.update(upstream=str(upstream), source_tree=git(upstream, "write-tree"), patches=["changes.patch"])
    patch = git(upstream, "diff", "--cached", "--binary") + "\n"
    consumer = tmp_path / "consumer"
    patches = consumer / "scripts/sdk_patches"
    patches.mkdir(parents=True)
    (patches / "agentcore-source.json").write_text(json.dumps(spec), encoding="utf-8")
    (patches / "changes.patch").write_bytes(patch.replace("\n", "\r\n").encode())

    source = installer.prepare_source(consumer)
    assert verify_source(consumer) == source
    assert (source / "module.py").read_text() == "VALUE = 2\n"
    assert (source / "new_module.py").read_text() == "VALUE = 3\n"
    head = git(source, "rev-parse", "HEAD")
    assert installer.prepare_source(consumer) == source
    assert git(source, "rev-parse", "HEAD") == head
    (source / "module.py").write_text("retained local work\n")
    with pytest.raises(AgentCoreSourceError):
        installer.prepare_source(consumer)
    assert (source / "module.py").read_text() == "retained local work\n"


@pytest.mark.parametrize("valid_source", [True, False])
def test_uninstall_precedes_source_install_only_after_source_validation(tmp_path, monkeypatch, valid_source):
    source = tmp_path / "source"
    calls = []
    def prepare(repo, repository=None):
        if not valid_source:
            raise AgentCoreSourceError("unreviewed tree")
        return source
    monkeypatch.setattr(installer, "prepare_source", prepare)
    monkeypatch.setattr(installer.shutil, "which", lambda name: "uv")
    monkeypatch.setattr(installer.subprocess, "run", lambda cmd, **kwargs: calls.append(cmd))
    monkeypatch.setattr(installer.sys, "argv", ["install_agentcore_source.py"])
    if not valid_source:
        with pytest.raises(AgentCoreSourceError):
            installer.main()
        assert calls == []
        return
    installer.main()
    assert calls == [
        ["uv", "pip", "uninstall", "--python", installer.sys.executable, "openjiuwen"],
        ["uv", "pip", "install", "--python", installer.sys.executable, "--no-deps", "--editable", str(source)],
        [installer.sys.executable, str(installer.REPO / "scripts/install_agentcore_source.py"), "--check"],
    ]
