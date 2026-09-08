"""Source provenance must not be inferred from a matching package version."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from jiuwenswarm.common import agentcore_source as sdk


def git(source, *args):
    return subprocess.check_output(
        ["git", "-C", str(source), "-c", "core.autocrlf=false", "-c", "commit.gpgsign=false",
         "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", *args], text=True,
    ).strip()


@pytest.fixture
def checkout(tmp_path, monkeypatch):
    source = tmp_path / ".deps/agent-core"
    source.mkdir(parents=True)
    git(source, "init")
    (source / "module.py").write_text("VALUE = 1\n", encoding="utf-8", newline="\n")
    git(source, "add", "module.py")
    git(source, "commit", "-m", "fixture source")
    base = git(source, "rev-parse", "HEAD")
    manifest = tmp_path / "scripts/sdk_patches/agentcore-source.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"base_commit": base, "source_tree": git(source, "rev-parse", "HEAD^{tree}"),
                                    "version": sdk.SDK_VERSION}), encoding="utf-8")
    monkeypatch.setattr(sdk, "SDK_BASE", base)
    return tmp_path, source


def installed(monkeypatch, source, *, editable=True, version=None):
    direct = json.dumps({"url": source.as_uri(), "dir_info": {"editable": editable}})
    dist = SimpleNamespace(version=version or sdk.SDK_VERSION, read_text=lambda name: direct)
    monkeypatch.setattr(sdk.metadata, "distribution", lambda package: dist)
    monkeypatch.setattr(sdk, "find_spec", lambda name: SimpleNamespace(origin=str(source / "openjiuwen/__init__.py")))
    monkeypatch.delitem(sys.modules, "openjiuwen", raising=False)


def test_source_and_editable_installation_match(checkout, monkeypatch):
    repo, source = checkout
    installed(monkeypatch, source)
    assert sdk.verify_installed_source(repo) == source


@pytest.mark.parametrize("mismatch", ["wheel", "other_checkout", "other_version"])
def test_matching_version_cannot_substitute_for_source_origin(checkout, monkeypatch, mismatch):
    repo, source = checkout
    installed(monkeypatch, repo / "elsewhere" if mismatch == "other_checkout" else source,
              editable=mismatch != "wheel", version="0.1.16" if mismatch == "other_version" else None)
    with pytest.raises(sdk.AgentCoreSourceError):
        sdk.verify_installed_source(repo)


@pytest.mark.parametrize("committed", [False, True])
def test_changed_content_is_rejected_even_with_original_install_metadata(checkout, monkeypatch, committed):
    repo, source = checkout
    installed(monkeypatch, source)
    (source / "module.py").write_text("VALUE = 2\n", encoding="utf-8")
    if committed:
        git(source, "add", "module.py")
        git(source, "commit", "-m", "unreviewed change")
    with pytest.raises(sdk.AgentCoreSourceError):
        sdk.verify_installed_source(repo)


def test_missing_installation_does_not_pass_source_check_alone(checkout, monkeypatch):
    repo, _ = checkout
    def missing(package):
        raise sdk.metadata.PackageNotFoundError(package)
    monkeypatch.setattr(sdk.metadata, "distribution", missing)
    with pytest.raises(sdk.AgentCoreSourceError, match="metadata"):
        sdk.verify_installed_source(repo)


def test_untracked_runtime_code_is_not_part_of_reviewed_source(checkout):
    repo, source = checkout
    (source / "extra_module.py").write_text("VALUE = 3\n", encoding="utf-8")
    with pytest.raises(sdk.AgentCoreSourceError, match="uncommitted"):
        sdk.verify_source(repo)


@pytest.mark.parametrize("loaded", [False, True])
def test_import_shadowing_cannot_pass_matching_distribution_metadata(checkout, monkeypatch, loaded):
    repo, source = checkout
    installed(monkeypatch, source)
    other = str(repo / "other/openjiuwen/__init__.py")
    if loaded:
        monkeypatch.setitem(sys.modules, "openjiuwen", SimpleNamespace(__file__=other))
    else:
        monkeypatch.setattr(sdk, "find_spec", lambda name: SimpleNamespace(origin=other))
    with pytest.raises(sdk.AgentCoreSourceError, match="import resolves"):
        sdk.verify_installed_source(repo)


def test_missing_source_has_actionable_failure(checkout):
    repo, source = checkout
    source.rename(source.with_name("retained-source"))
    with pytest.raises(sdk.AgentCoreSourceError, match="install_agentcore_source"):
        sdk.verify_source(repo)
