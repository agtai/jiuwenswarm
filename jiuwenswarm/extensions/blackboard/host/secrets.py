"""Host secrets, generated on first start and kept next to the host's data."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from jiuwenswarm.extensions.blackboard.common.tokens import new_secret


@dataclass(frozen=True)
class HostSecrets:
    # Signs document and file tokens; the document service verifies them (milestone 3).
    doc_secret: str
    # Shared by the host and its document service for internal calls.
    api_secret: str


def load_or_create(path: Path) -> HostSecrets:
    data: dict = {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}
    changed = False
    for key in ("doc_secret", "api_secret"):
        if not isinstance(data.get(key), str) or not data[key]:
            data[key] = new_secret()
            changed = True
    if changed:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    return HostSecrets(doc_secret=data["doc_secret"], api_secret=data["api_secret"])
