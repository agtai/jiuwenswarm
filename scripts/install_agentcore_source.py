"""Prepare and install the reviewed AgentCore source; never overwrite a checkout.

Run with the project's Python. --prepare-only bootstraps source before uv sync;
--check verifies source and installation without changing either.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from jiuwenswarm.common.agentcore_source import (  # noqa: E402
    AgentCoreSourceError, source_spec, verify_installed_source, verify_source,
)


def prepare_source(repo: Path, repository: str | None = None) -> Path:
    source = repo / ".deps/agent-core"
    if source.exists():
        return verify_source(repo)
    spec = source_spec(repo)
    source.mkdir(parents=True)

    def git(*args: str, **kwargs):
        return subprocess.run(["git", "-C", str(source), "-c", "core.autocrlf=false", *args],
                              check=True, **kwargs)

    git("init", "--initial-branch=codex/live-voice-unified")
    git("fetch", "--depth=1", repository or spec["upstream"], spec["base_commit"])
    git("checkout", "-B", "codex/live-voice-unified", "FETCH_HEAD")
    for name in spec["patches"]:
        patch = (repo / "scripts/sdk_patches" / name).read_bytes().replace(b"\r\n", b"\n")
        git("apply", "--unidiff-zero", "--check", "-", input=patch)
        git("apply", "--unidiff-zero", "--index", "-", input=patch)
    tree = subprocess.check_output(["git", "-C", str(source), "write-tree"], text=True).strip()
    if tree != spec["source_tree"]:
        raise AgentCoreSourceError("Prepared source does not match the reviewed content tree; checkout retained")
    # Reconstruction is a tool-generated local commit, not a claim that a
    # deployer's Git identity authored the upstream code or carried patches.
    git("-c", "user.name=JiuwenSwarm source installer", "-c", "user.email=source-installer@localhost",
        "-c", "commit.gpgsign=false", "commit", "-m", "build: reconstruct reviewed JiuwenSwarm AgentCore source")
    return verify_source(repo)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--prepare-only", action="store_true")
    modes.add_argument("--check", action="store_true")
    parser.add_argument("--repository", help="Optional Git mirror containing the pinned commit")
    args = parser.parse_args()
    if args.check:
        print(verify_installed_source(REPO))
        return
    source = prepare_source(REPO, args.repository)
    if not args.prepare_only:
        uv = shutil.which("uv")
        if uv is None:
            parser.error("uv is required for source installation")
        # Explicitly retire the old distribution after source validation. If
        # installation fails, retain source and fail; never fall back to a wheel.
        subprocess.run([uv, "pip", "uninstall", "--python", sys.executable, "openjiuwen"], check=True)
        subprocess.run([uv, "pip", "install", "--python", sys.executable, "--no-deps",
                        "--editable", str(source)], check=True)
        # A newly installed editable finder is activated by a fresh interpreter,
        # not by the already-running installer. Check the same launch environment.
        subprocess.run([sys.executable, str(REPO / "scripts/install_agentcore_source.py"), "--check"],
                       cwd=REPO, check=True)
    print(source)


if __name__ == "__main__":
    main()
