"""Version history and export on the host: roles, names, restore rules, export files and links, and
the document service's announcement of new versions."""

from __future__ import annotations

import asyncio
import json
import os
import time
from urllib.parse import parse_qs, urlparse

import httpx

from jiuwenswarm.extensions.blackboard.common import protocol as p
from jiuwenswarm.extensions.blackboard.common.errors import BUSY, CONFLICT, FORBIDDEN, INVALID
from jiuwenswarm.extensions.blackboard.host.api import history
from jiuwenswarm.extensions.blackboard.host.store import decisions, docs, mandates
from jiuwenswarm.extensions.blackboard.tests.backend.support import rpc


async def _scene(world):
    alice, _ = await world.user("Alice")
    bob, _ = await world.user("Bob")
    vera, _ = await world.user("Vera")
    workspace_id = await world.workspace(alice)
    await world.add(workspace_id, bob, "editor")
    await world.add(workspace_id, vera, "viewer")
    doc_id = await world.doc(alice, workspace_id, title="Plan")
    return alice, bob, vera, workspace_id, doc_id


async def test_the_history_names_authors_and_what_agent_runs_were_asked(world):
    alice, bob, vera, workspace_id, doc_id = await _scene(world)
    mandate_id = await world.mandate(bob, workspace_id, instruction="Tighten the plan")
    world.ctx.docs.add_version(doc_id, "created", [{"id": alice.id, "kind": "person"}])
    world.ctx.docs.add_version(doc_id, "agent_turn", [{"id": bob.id, "kind": "agent"}], mandateId=mandate_id)

    listed = await world.call(vera, p.HISTORY_LIST, doc_id=doc_id)
    newest, oldest = listed["versions"]
    assert (newest["reason"], newest["authors"], newest["mandate_instruction"]) == (
        "agent_turn",
        [{"id": bob.id, "kind": "agent", "name": "Bob"}],
        "Tighten the plan",
    )
    assert (oldest["reason"], oldest["authors"][0]["name"], oldest["mandate_id"]) == ("created", "Alice", None)
    assert listed["has_more"] is False

    got = await world.call(vera, p.HISTORY_GET, doc_id=doc_id, version_id=newest["id"])
    assert got["doc"] == {"type": "doc", "content": []} and got["version"]["id"] == newest["id"]
    markdown = await world.call(vera, p.HISTORY_GET, doc_id=doc_id, version_id=newest["id"], format="markdown")
    assert markdown["markdown"].startswith("# ")
    diff = await world.call(vera, p.HISTORY_DIFF, doc_id=doc_id, to=newest["id"])
    assert diff["blocks"][0] == {
        "id": "b1",
        "type": "paragraph",
        "status": "changed",
        "markdown": "new",
        "inline": [{"op": "ins", "text": "new"}],
        "pending": True,
        "was_pending": False,
    }

    outsider, _ = await world.user("Mallory")
    assert (await world.fails(outsider, p.HISTORY_LIST, doc_id=doc_id)).code in ("not_member", FORBIDDEN)
    assert (await world.fails(vera, p.HISTORY_GET, doc_id=doc_id, version_id="../x")).code == INVALID


async def test_editors_save_and_restore_versions_but_not_while_an_agent_writes(world):
    alice, bob, vera, workspace_id, doc_id = await _scene(world)
    first = world.ctx.docs.add_version(doc_id, "created", [{"id": alice.id, "kind": "person"}])

    saved = await world.call(bob, p.HISTORY_SAVE, doc_id=doc_id, label="Before  review")
    assert (saved["version"]["reason"], saved["version"]["label"], saved["version"]["authors"][0]["name"]) == ("manual", "Before review", "Bob")
    assert (await world.fails(vera, p.HISTORY_SAVE, doc_id=doc_id)).code == FORBIDDEN
    assert (await world.fails(vera, p.HISTORY_RESTORE, doc_id=doc_id, version_id=first["id"])).code == FORBIDDEN

    mandate_id = await world.mandate(alice, workspace_id)
    await world.store.transact(lambda c: mandates.try_lock(c, doc_id, mandate_id))
    assert (await world.fails(bob, p.HISTORY_RESTORE, doc_id=doc_id, version_id=first["id"])).code == BUSY
    await world.store.transact(lambda c: mandates.release_locks(c, mandate_id))

    restored = await world.call(bob, p.HISTORY_RESTORE, doc_id=doc_id, version_id=first["id"])
    assert (restored["version"]["reason"], restored["version"]["restored_from"]) == ("restore", first["id"])
    assert ("restore", doc_id, {"version_id": first["id"], "author": {"id": bob.id, "kind": "person"}}) in world.ctx.docs.calls
    assert p.EV_SUGGESTIONS_CHANGED in world.hub.events()

    await world.store.transact(lambda c: docs.archive(c, doc_id))
    assert (await world.fails(bob, p.HISTORY_RESTORE, doc_id=doc_id, version_id=first["id"])).code == CONFLICT


async def test_an_agent_edit_keeps_the_version_it_made_on_its_receipt(world):
    alice, _, _, workspace_id, doc_id = await _scene(world)
    result = await world.call(alice, p.EDIT, doc_id=doc_id, session_id="sess-1", turn_id="t1", ops=[{"op": "replace", "block_id": "b1", "digest": "d0", "markdown": "x"}])
    receipt = await world.store.read(lambda c: mandates.get_receipt(c, result["receipt_id"]))
    assert receipt.version_id == f"v1_{doc_id}"
    # Deciding a suggestion tells the service who decided, for their next version.
    [suggestion] = result["suggestion_ids"]
    await world.call(alice, p.SUGGESTION_DECIDE, doc_id=doc_id, suggestion_ids=[suggestion], action="accept")
    assert world.ctx.docs.named("decide")[-1][1]["actor"] == alice.id


async def test_export_writes_a_file_behind_a_short_lived_link_with_the_decisions_about_the_doc(world):
    alice, bob, vera, workspace_id, doc_id = await _scene(world)
    other_doc = await world.doc(alice, workspace_id, title="Other")
    run = await world.mandate(bob, workspace_id)

    def answered(conn, question: str, about: str | None, mandate_id: str) -> None:
        decision = decisions.create(
            conn, workspace_id=workspace_id, mandate_id=mandate_id, requester_id=bob.id, question=question,
            options=[{"label": "Quality"}, {"label": "Budget"}], recommended=None, doc_id=about,
        )
        decisions.propose(conn, decision.id, {"option": 0}, alice.id)
        decisions.accept(conn, decision.id, bob.id)

    other_run = await world.mandate(bob, workspace_id)
    await world.store.transact(lambda c: answered(c, "About the plan?", doc_id, run))
    await world.store.transact(lambda c: answered(c, "About the other doc?", other_doc, other_run))
    # A run that changed the plan: its question counts even without naming the document.
    changed = await world.mandate(bob, workspace_id)
    await world.store.transact(lambda c: answered(c, "Asked while editing?", None, changed))

    def applied_receipt(conn) -> None:
        receipt = mandates.add_receipt(conn, mandate_id=changed, doc_id=doc_id, ops=[], note="")
        mandates.finish_receipt(conn, receipt.id, applied=True)

    await world.store.transact(applied_receipt)

    plain = await world.call(vera, p.DOC_EXPORT, doc_id=doc_id, format="md")
    assert world.ctx.docs.named("export")[-1][1]["decisions"] == []
    exported = await world.call(vera, p.DOC_EXPORT, doc_id=doc_id, format="docx", include_decisions=True)
    sent = world.ctx.docs.named("export")[-1][1]
    assert (sent["format"], sent["title"]) == ("docx", "Plan")
    assert [d["question"] for d in sent["decisions"]] == ["About the plan?", "Asked while editing?"]
    assert sent["decisions"][0] == {"question": "About the plan?", "answer": "Quality", "answeredBy": "Alice", "acceptedBy": "Bob"}
    assert (exported["file_name"], plain["file_name"]) == ("Plan.docx", "Plan.md")

    url = urlparse(exported["url"])
    assert url.path.startswith(p.EXPORT_PATH)
    export_id = url.path.rsplit("/", 1)[1]
    token = parse_qs(url.query)["t"][0]
    response = await history.download_export(world.ctx, export_id, token)
    assert response.status_code == 200 and str(response.path).endswith("Plan.docx")
    assert open(response.path, "rb").read() == b"docx:Plan:2"
    assert (await history.download_export(world.ctx, urlparse(plain["url"]).path.rsplit("/", 1)[1], token)).status_code == 401
    assert (await history.download_export(world.ctx, export_id, token + "x")).status_code == 401

    # Someone who left the workspace cannot use a link they still hold.
    await world.call(alice, p.MEMBER_REMOVE, workspace_id=workspace_id, user_id=vera.id)
    assert (await history.download_export(world.ctx, export_id, token)).status_code == 403

    assert (await world.fails(alice, p.DOC_EXPORT, doc_id=doc_id, format="odt")).code == INVALID


async def test_exports_older_than_a_day_are_removed_with_the_next_export(world):
    alice, _, _, _, doc_id = await _scene(world)
    await world.call(alice, p.DOC_EXPORT, doc_id=doc_id, format="md")
    [old] = list(world.ctx.exports_dir.iterdir())
    past = time.time() - history.EXPORT_KEEP_S - 60
    os.utime(old, (past, past))
    await world.call(alice, p.DOC_EXPORT, doc_id=doc_id, format="md")
    kept = list(world.ctx.exports_dir.iterdir())
    assert old not in kept and len(kept) == 1


async def test_the_document_service_announces_versions_to_the_workspace(host):
    operator = await host.operator("Alice")
    token = await host.rotate_token(operator.id)
    _, created = await rpc(host.base, p.WORKSPACE_CREATE, {"name": "launch", "title": "Launch"}, token)
    workspace_id = created["payload"]["workspace"]["id"]
    await host.store.transact(lambda c: docs.create(c, doc_id="d_plan", workspace_id=workspace_id, title="Plan", created_by=operator.id))
    published = []

    async def record(event, payload, **kwargs):
        published.append((event, payload, kwargs.get("workspace_id")))

    host.ctx.hub.publish = record
    version = {"id": "v1", "docId": "d_plan", "createdAt": "2026-09-29T10:00:00Z", "reason": "idle", "authors": [{"id": operator.id, "kind": "person"}], "size": 10}
    async with httpx.AsyncClient() as client:
        url = host.base + p.VERSIONS_HOOK_PATH
        assert (await client.post(url, content=json.dumps(version), headers={"X-BB-Secret": "wrong"})).status_code == 401
        ok = await client.post(url, content=json.dumps(version), headers={"X-BB-Secret": host.ctx.secrets.api_secret})
        assert ok.status_code == 200
        missing = await client.post(url, content=json.dumps({**version, "docId": "d_gone"}), headers={"X-BB-Secret": host.ctx.secrets.api_secret})
        assert missing.status_code == 404
    [(event, payload, to)] = published
    assert (event, to, payload["doc_id"]) == (p.EV_DOC_VERSIONS, workspace_id, "d_plan")
    assert payload["version"]["authors"] == [{"id": operator.id, "kind": "person", "name": "Alice"}]


async def test_history_and_export_with_the_real_document_service(real_docservice, host):
    assert await host.docs.wait_ready(20), host.docs.status()
    operator = await host.operator("Alice")
    token = await host.rotate_token(operator.id)
    _, created = await rpc(host.base, p.WORKSPACE_CREATE, {"name": "launch", "title": "Launch"}, token)
    workspace_id = created["payload"]["workspace"]["id"]
    published = []
    real_publish = host.ctx.hub.publish

    async def record(event, payload, **kwargs):
        published.append((event, payload))
        await real_publish(event, payload, **kwargs)

    host.ctx.hub.publish = record
    _, made = await rpc(host.base, p.DOC_CREATE, {"workspace_id": workspace_id, "title": "Plan", "markdown": "# Plan\n\nShip it.\n"}, token)
    doc_id = made["payload"]["doc"]["id"]
    await rpc(host.base, p.DOC_IMPORT_MARKDOWN, {"doc_id": doc_id, "markdown": "# Plan\n\nShip it on Friday.\n"}, token)

    _, listed = await rpc(host.base, p.HISTORY_LIST, {"doc_id": doc_id}, token)
    versions = listed["payload"]["versions"]
    assert [v["reason"] for v in versions] == ["import", "created"]
    assert versions[0]["authors"] == [{"id": operator.id, "kind": "person", "name": "Alice"}]
    _, diff = await rpc(host.base, p.HISTORY_DIFF, {"doc_id": doc_id, "to": versions[0]["id"]}, token)
    assert [b["status"] for b in diff["payload"]["blocks"]].count("added") >= 1

    # The service announced both versions to the host, which told the workspace.
    for _ in range(50):
        if sum(1 for event, _ in published if event == p.EV_DOC_VERSIONS) >= 2:
            break
        await asyncio.sleep(0.1)
    assert sum(1 for event, _ in published if event == p.EV_DOC_VERSIONS) >= 2

    _, exported = await rpc(host.base, p.DOC_EXPORT, {"doc_id": doc_id, "format": "md"}, token)
    async with httpx.AsyncClient() as client:
        response = await client.get(exported["payload"]["url"])
    assert response.status_code == 200 and "Ship it on Friday." in response.text
    assert 'filename="Plan.md"' in response.headers["content-disposition"]
