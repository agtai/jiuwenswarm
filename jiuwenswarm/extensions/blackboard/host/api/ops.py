"""Health and metrics (milestone 8): what the host reports at ``/blackboard/health`` and in the
settings dialog, and a summary line in blackboard.log every ten minutes. Counts only, no names."""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
from collections import Counter
from typing import Any

from jiuwenswarm.extensions.blackboard.common.errors import BlackboardError
from jiuwenswarm.extensions.blackboard.host.api.context import HostContext
from jiuwenswarm.extensions.blackboard.host.store import mandates

logger = logging.getLogger(__name__)

METRICS_INTERVAL_S = 600.0
_HEALTH_TIMEOUT_S = 3.0


def _active_runs(conn: sqlite3.Connection) -> dict[str, int]:
    placeholders = ",".join("?" * len(mandates.ACTIVE))
    rows = conn.execute(
        f"SELECT status, COUNT(*) AS n FROM mandates WHERE status IN ({placeholders}) GROUP BY status", tuple(mandates.ACTIVE)
    ).fetchall()
    return {r["status"]: r["n"] for r in rows}


async def health(ctx: HostContext) -> dict[str, Any]:
    live: dict[str, Any] = {}
    if ctx.docs is not None and ctx.docs.running:
        try:
            live = await asyncio.wait_for(ctx.doc_client().health(), _HEALTH_TIMEOUT_S)
        except (BlackboardError, asyncio.TimeoutError):
            live = {}
    runs = await ctx.store.read(_active_runs)
    return {
        "ok": True,
        "version": ctx.version,
        "host_uid": ctx.host_uid,
        "docservice": {
            **ctx.docservice_status(),
            "open_documents": live.get("openDocuments"),
            "connections": live.get("connections"),
            "pdf_export": live.get("pdf"),
        },
        "members_connected": ctx.hub.connection_count,
        "runs": runs,
        # Agent runs waiting for a document: comment tasks queued behind another, and edits waiting
        # for a lock.
        "queue_depth": runs.get("queued", 0) + ctx.lock_waits.waiting(),
    }


def summary(conn: sqlite3.Connection, since: str) -> dict[str, Any]:
    finished = conn.execute("SELECT status, COUNT(*) AS n FROM mandates WHERE finished_at >= ? GROUP BY status", (since,)).fetchall()
    receipts = conn.execute("SELECT status, error FROM receipts WHERE created_at >= ?", (since,)).fetchall()
    refused: Counter[str] = Counter()
    for row in receipts:
        if row["status"] == "aborted":
            try:
                refused[str(json.loads(row["error"] or "{}").get("code") or "unknown")] += 1
            except ValueError:
                refused["unknown"] += 1
    average = conn.execute(
        "SELECT AVG((julianday(finished_at) - julianday(COALESCE(started_at, created_at))) * 86400) AS s"
        " FROM mandates WHERE finished_at >= ?",
        (since,),
    ).fetchone()["s"]
    return {
        "runs_finished": {r["status"]: r["n"] for r in finished},
        "runs_active": _active_runs(conn),
        "edit_batches_applied": sum(1 for r in receipts if r["status"] == "applied"),
        "edit_batches_refused": dict(refused),
        "average_run_s": round(average, 1) if average is not None else None,
    }


async def log_metrics(ctx: HostContext, since: str) -> dict[str, Any]:
    data = await ctx.store.read(lambda c: summary(c, since))
    logger.info("blackboard: metrics since %s: %s", since, json.dumps(data, sort_keys=True))
    return data
