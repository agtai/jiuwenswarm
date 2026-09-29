"""Health and metrics: what /blackboard/health reports and the summary line in the log."""

from __future__ import annotations

import logging

import httpx

from jiuwenswarm.extensions.blackboard.common import protocol as p
from jiuwenswarm.extensions.blackboard.common.errors import BlackboardError
from jiuwenswarm.extensions.blackboard.host.api.ops import log_metrics
from jiuwenswarm.extensions.blackboard.tests.backend.test_blackboard_host_api import Listener


async def test_health_counts_members_runs_and_waiting(host):
    alice = await host.operator("Alice")
    token = await host.rotate_token(alice.id)
    listener = await Listener.connect(host, token)
    try:
        async with httpx.AsyncClient() as client:
            health = (await client.get(f"{host.base}{p.HEALTH_PATH}")).json()
    finally:
        await listener.close()
    assert health["ok"] is True and health["members_connected"] == 1
    assert (health["runs"], health["queue_depth"]) == ({}, 0)
    assert "open_documents" in health["docservice"] and "pdf_export" in health["docservice"]


async def test_metrics_summarise_runs_and_edit_batches(world):
    alice, _ = await world.user("Alice")
    workspace_id = await world.workspace(alice)
    doc_id = await world.doc(alice, workspace_id)
    ops = [{"op": "replace", "block_id": "b1", "digest": "d0", "markdown": "New text."}]
    await world.call(alice, p.EDIT, doc_id=doc_id, ops=ops, session_id="s1", turn_id="t1")
    await world.call(alice, p.EDIT, doc_id=doc_id, ops=ops, session_id="s1", turn_id="t1")
    world.ctx.docs.edit_error = BlackboardError("stale", "the block changed")
    await world.fails(alice, p.EDIT, doc_id=doc_id, ops=ops, session_id="s1", turn_id="t1")
    running = await world.mandate(alice, workspace_id, status="running")
    assert running

    # Other tests change the blackboard logger's propagation, so listen on the module's logger itself.
    logger = logging.getLogger("jiuwenswarm.extensions.blackboard.host.api.ops")
    lines: list[str] = []
    handler = logging.Handler()
    handler.emit = lambda record: lines.append(record.getMessage())  # type: ignore[method-assign]
    level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        data = await log_metrics(world.ctx, "2000-01-01T00:00:00.000+00:00")
    finally:
        logger.removeHandler(handler)
        logger.setLevel(level)
    assert data["edit_batches_applied"] == 2 and data["edit_batches_refused"] == {"stale": 1}
    assert data["runs_active"]["running"] >= 1
    assert any(line.startswith("blackboard: metrics since") for line in lines)
