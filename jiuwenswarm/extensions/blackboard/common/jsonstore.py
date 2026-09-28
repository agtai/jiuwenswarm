"""A small JSON file shared by the Gateway and the AgentServer processes.

Writes take a portalocker file lock (other process) and an asyncio lock (same
process), then replace the file atomically, so readers never see half a file.
"""

from __future__ import annotations

import asyncio
import copy
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Callable

import portalocker


def _replace_with_retry(src: Path, dst: Path, attempts: int = 10) -> None:
    # On Windows the replace fails while another process has the target open.
    for attempt in range(attempts):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(0.01 * (attempt + 1))


class JsonStore:
    def __init__(self, path: Path, default: Callable[[], dict[str, Any]]) -> None:
        self.path = Path(path)
        self._default = default
        self._lock = asyncio.Lock()

    def read(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return self._default()
        except (OSError, json.JSONDecodeError):
            return self._default()
        return data if isinstance(data, dict) else self._default()

    async def update(self, mutator: Callable[[dict[str, Any]], Any]) -> Any:
        """Run ``mutator(data)`` on a copy under both locks and write the result.

        Returns whatever the mutator returns.
        """
        async with self._lock:
            return await asyncio.to_thread(self._update_locked, mutator)

    def _update_locked(self, mutator: Callable[[dict[str, Any]], Any]) -> Any:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with portalocker.Lock(str(self.path.with_suffix(".lock")), timeout=10):
            data = copy.deepcopy(self.read())
            result = mutator(data)
            tmp = self.path.with_name(f"{self.path.name}.{uuid.uuid4().hex}.tmp")
            tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            try:
                _replace_with_retry(tmp, self.path)
            finally:
                tmp.unlink(missing_ok=True)
            return result
