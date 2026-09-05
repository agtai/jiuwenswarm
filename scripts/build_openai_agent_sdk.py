"""Build the pinned SDK metadata repair for the OpenAI Responses Agent.

Creates its own fresh checkout; never edits site-packages or an existing SDK
checkout. Install the resulting wheel explicitly with --no-deps (see README).
"""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys

BASE = "94e10cb6102c36fe78a64547957c0def97299273"
REPO = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True, help="New, empty build checkout")
    parser.add_argument("--wheel-dir", type=Path, required=True)
    args = parser.parse_args()
    source = args.source_dir.resolve()
    output = args.wheel_dir.resolve()
    if source.exists() and any(source.iterdir()):
        parser.error("source-dir must be empty; existing work is never overwritten")
    source.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)

    def git(*arguments):
        return subprocess.check_output(["git", "-C", str(source), *arguments])

    git("init")
    git("config", "core.autocrlf", "false")
    git("fetch", "--depth=1", "https://gitcode.com/openJiuwen/agent-core.git", BASE)
    git("checkout", "--detach", "FETCH_HEAD")
    if git("rev-parse", "HEAD").decode().strip() != BASE:
        raise RuntimeError("SDK source identity mismatch")
    patch = REPO / "scripts/sdk_patches/openjiuwen-responses-metadata.patch"
    git("apply", "--unidiff-zero", "--check", str(patch))
    git("apply", "--unidiff-zero", str(patch))
    subprocess.run([sys.executable, "-c", "import setuptools.build_meta as b, sys; b.build_wheel(sys.argv[1])",
                    str(output)], cwd=source, check=True)
    wheel = output / "openjiuwen-0.1.16+jiuwenswarm.responses2-py3-none-any.whl"
    if not wheel.is_file():
        raise RuntimeError("Expected SDK wheel was not produced")
    print(wheel)


if __name__ == "__main__":
    main()
