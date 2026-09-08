"""Verify the source dependency used by a JiuwenSwarm source checkout.

The Git tree identifies content independently of local commit timestamps. This
is a deployment preflight, not an authority grant to execute user work.
"""
from __future__ import annotations

from importlib import metadata
from importlib.util import find_spec
import json
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlsplit
from urllib.request import url2pathname

from jiuwenswarm.common.openai_responses_dependency import SDK_BASE, SDK_VERSION


class AgentCoreSourceError(RuntimeError):
    """The installed dependency cannot be tied to the pinned source."""


def source_spec(repo: Path) -> dict:
    try:
        spec = json.loads((repo / "scripts/sdk_patches/agentcore-source.json").read_text(encoding="utf-8"))
        matches = spec["base_commit"] == SDK_BASE and spec["version"] == SDK_VERSION
        if not isinstance(spec["source_tree"], str) or len(spec["source_tree"]) != 40:
            raise ValueError("invalid source tree")
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise AgentCoreSourceError("AgentCore source manifest is missing or invalid") from error
    if not matches:
        raise AgentCoreSourceError("AgentCore source manifest and dependency constants disagree")
    return spec


def git_output(source: Path, *args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(source), "-c", "core.autocrlf=false", *args],
            stderr=subprocess.PIPE, text=True, encoding="utf-8",
        ).strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise AgentCoreSourceError("AgentCore source Git verification failed") from error


def verify_source(repo: Path) -> Path:
    """Require the reviewed content tree and a clean, pinned-base descendant."""
    spec = source_spec(repo)
    source = (repo / ".deps/agent-core").resolve()
    if not (source / ".git").exists():
        raise AgentCoreSourceError("AgentCore source is missing; run scripts/install_agentcore_source.py")
    if git_output(source, "rev-parse", "HEAD^{tree}") != spec["source_tree"]:
        raise AgentCoreSourceError("AgentCore source tree differs from the reviewed source manifest")
    git_output(source, "merge-base", "--is-ancestor", spec["base_commit"], "HEAD")
    if git_output(source, "status", "--porcelain", "--untracked-files=normal"):
        raise AgentCoreSourceError("AgentCore has uncommitted changes; review and pin them before launch")
    return source


def verify_installed_source(repo: Path) -> Path:
    """Check the current interpreter's editable origin as well as package version."""
    source = verify_source(repo)
    try:
        dist = metadata.distribution("openjiuwen")
        direct = json.loads(dist.read_text("direct_url.json") or "{}")
        url = urlsplit(direct.get("url", ""))
        origin = Path(url2pathname(url.path)).resolve()
        if (dist.version != SDK_VERSION or direct.get("dir_info", {}).get("editable") is not True
                or url.scheme != "file" or url.netloc not in ("", "localhost") or origin != source):
            raise AgentCoreSourceError("AgentCore must be installed editable from this checkout's pinned source")
        expected = source / "openjiuwen/__init__.py"
        module_spec = find_spec("openjiuwen")
        loaded = sys.modules.get("openjiuwen")
        if (module_spec is None or not module_spec.origin or Path(module_spec.origin).resolve() != expected
                or (loaded is not None and Path(getattr(loaded, "__file__", "")).resolve() != expected)):
            raise AgentCoreSourceError("AgentCore import resolves outside the pinned source; check PYTHONPATH and old installs")
    except (metadata.PackageNotFoundError, ValueError, TypeError, AttributeError) as error:
        raise AgentCoreSourceError("AgentCore source installation metadata is missing or invalid") from error
    return source
