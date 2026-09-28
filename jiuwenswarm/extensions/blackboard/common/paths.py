"""Where Blackboard keeps its files: ``<data root>/blackboard``."""

from __future__ import annotations

from pathlib import Path


def blackboard_dir(root: Path | None = None) -> Path:
    if root is None:
        from jiuwenswarm.common.utils import get_root_dir

        root = get_root_dir()
    return Path(root) / "blackboard"


def host_dir(base: Path) -> Path:
    return base / "host"


def client_dir(base: Path) -> Path:
    return base / "client"
