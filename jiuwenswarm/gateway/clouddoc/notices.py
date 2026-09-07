"""The notice ledger for personal connections (design §13, matrix S.3).

A personal connection's watcher does one thing with a comment that summons the
person -- an @ of them, or a task assigned to them, written by somebody else: it
tells the person, inside their own swarm. It never answers in the document. This
file is where those notices live between the tick that found them and the person
reading them: the Docs panel draws a badge per document from it, the chat shows
one system message per notice, and "handle it" opens the workbench with the
comment in hand.

Storage follows the other guardrail ledgers: one JSON file under the workspace
config dir, portalocker-guarded, bounded (the oldest read notices fall off past
the cap; unread ones stay).
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any, Callable

import portalocker

logger = logging.getLogger(__name__)

_LOCK_TIMEOUT_S = 10.0
DEFAULT_MAX_NOTICES = 200


def get_notices_path() -> Path:
    from jiuwenswarm.agents.harness.common.tools.clouddoc.deployment import (
        workspace_dir as get_user_workspace_dir,
    )

    return get_user_workspace_dir() / "config" / "clouddoc-notices.json"


class NoticeStore:
    def __init__(
        self,
        path: Path | None = None,
        *,
        now_fn: Callable[[], float] = time.time,
        max_notices: int = DEFAULT_MAX_NOTICES,
    ) -> None:
        self._path = path or get_notices_path()
        self._now = now_fn
        self._max = int(max_notices)

    def _load(self) -> dict:
        if not self._path.is_file():
            return {"version": 1, "notices": {}}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            logger.exception("[clouddoc] notice store unreadable; treating as empty")
            return {"version": 1, "notices": {}}
        if not isinstance(data, dict):
            return {"version": 1, "notices": {}}
        data.setdefault("notices", {})
        return data

    def _mutate(self, fn: Callable[[dict], Any]) -> Any:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        lock = self._path.with_suffix(self._path.suffix + ".lock")
        with portalocker.Lock(str(lock), timeout=_LOCK_TIMEOUT_S):
            data = self._load()
            out = fn(data)
            rows = data["notices"]
            if len(rows) > self._max:
                aged = sorted(
                    (r for r in rows.values() if r.get("read")),
                    key=lambda r: r.get("ts", 0),
                )
                for r in aged[: len(rows) - self._max]:
                    rows.pop(r["notice_id"], None)
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self._path)
        return out

    # ---------------------------------------------------------------- writes

    def add(self, notice: dict) -> dict:
        """Record one notice and return it with its id and timestamp filled in.

        Idempotent on ``key``: the watcher's dedup key is the notice's identity, so
        a tick that re-finds a trigger whose mark was lost does not double the badge.
        """
        key = str(notice.get("key") or "")

        def fn(data: dict) -> dict:
            if key:
                for r in data["notices"].values():
                    if r.get("key") == key:
                        return dict(r)
            nid = uuid.uuid4().hex[:12]
            row = {**notice, "notice_id": nid, "ts": self._now(), "read": False}
            data["notices"][nid] = row
            return dict(row)

        return self._mutate(fn)

    def ack(self, notice_id: str | None = None, *, doc_id: str | None = None) -> int:
        """Mark one notice read, or every notice of a document. Returns how many."""

        def fn(data: dict) -> int:
            n = 0
            for r in data["notices"].values():
                if notice_id and r.get("notice_id") != notice_id:
                    continue
                if doc_id and r.get("doc_id") != doc_id:
                    continue
                if not notice_id and not doc_id:
                    continue
                if not r.get("read"):
                    r["read"] = True
                    r["read_at"] = self._now()
                    n += 1
            return n

        return self._mutate(fn)

    # ---------------------------------------------------------------- reads

    def list(self, *, unread_only: bool = True, limit: int = 100) -> list[dict]:
        rows = [
            dict(r) for r in self._load()["notices"].values()
            if not unread_only or not r.get("read")
        ]
        rows.sort(key=lambda r: r.get("ts", 0), reverse=True)
        return rows[: int(limit)]

    def unread_by_doc(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for r in self._load()["notices"].values():
            if not r.get("read"):
                d = str(r.get("doc_id") or "")
                out[d] = out.get(d, 0) + 1
        return out
