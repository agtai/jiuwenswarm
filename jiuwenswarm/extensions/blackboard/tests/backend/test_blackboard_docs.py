"""Document methods against a stand-in document service, plus one run against the real one."""

from __future__ import annotations

from jiuwenswarm.extensions.blackboard.common import protocol as p
from jiuwenswarm.extensions.blackboard.common.errors import CONFLICT, UNAVAILABLE
from jiuwenswarm.extensions.blackboard.common.tokens import verify_doc_token
from jiuwenswarm.extensions.blackboard.tests.backend.support import rpc


async def _workspace(world):
    alice, _ = await world.user("Alice")
    bob, _ = await world.user("Bob")
    workspace_id = await world.workspace(alice)
    await world.add(workspace_id, bob, "editor")
    return alice, bob, workspace_id


async def test_every_workspace_gets_a_pinned_instructions_document(world):
    alice, _, workspace_id = await _workspace(world)
    await world.doc(alice, workspace_id, "Zebra")
    listed = (await world.call(alice, p.DOC_LIST, workspace_id=workspace_id))["docs"]
    assert [d["title"] for d in listed] == ["Instructions", "Zebra"]
    assert listed[0]["is_instructions"] and listed[0]["is_pinned"]
    assert "What agents must not change" in world.ctx.docs.docs[listed[0]["id"]]

    error = await world.fails(alice, p.DOC_ARCHIVE, doc_id=listed[0]["id"])
    assert error.code == CONFLICT
    await world.call(alice, p.DOC_SET_INSTRUCTIONS, doc_id=listed[1]["id"])
    await world.call(alice, p.DOC_ARCHIVE, doc_id=listed[0]["id"])
    listed = (await world.call(alice, p.DOC_LIST, workspace_id=workspace_id))["docs"]
    assert [(d["title"], d["is_instructions"]) for d in listed] == [("Zebra", True)]


async def test_tokens_carry_the_role_and_archived_workspaces_open_read_only(world):
    alice, bob, workspace_id = await _workspace(world)
    doc_id = await world.doc(alice, workspace_id)
    token = await world.call(bob, p.DOC_TOKEN, doc_id=doc_id)
    claims = verify_doc_token(token["token"], world.ctx.secrets.doc_secret)
    assert claims["role"] == "editor" and claims["doc"] == doc_id and claims["uid"] == bob.id
    assert claims["exp"] - claims["iat"] == token["expires_in"]

    await world.call(alice, p.WORKSPACE_ARCHIVE, workspace_id=workspace_id)
    token = await world.call(bob, p.DOC_TOKEN, doc_id=doc_id)
    assert token["role"] == "viewer" and token["frozen"] is True
    assert (await world.fails(bob, p.DOC_RENAME, doc_id=doc_id, title="New")).code == CONFLICT


async def test_access_changes_reach_the_document_service(world):
    alice, bob, workspace_id = await _workspace(world)
    doc_id = await world.doc(alice, workspace_id)
    docs = world.ctx.docs

    await world.call(alice, p.MEMBER_SET_ROLE, workspace_id=workspace_id, user_id=bob.id, role="viewer")
    await world.call(alice, p.MEMBER_REMOVE, workspace_id=workspace_id, user_id=bob.id)
    rechecks = [extra for d, extra in docs.named("recheck") if d == doc_id]
    assert rechecks == [
        {"user_id": bob.id, "role": "viewer", "revoke": False},
        {"user_id": bob.id, "role": None, "revoke": True},
    ]

    (world.ctx.files_dir / workspace_id).mkdir(parents=True)
    await world.call(alice, p.WORKSPACE_ARCHIVE, workspace_id=workspace_id)
    await world.call(alice, p.WORKSPACE_DELETE, workspace_id=workspace_id)
    assert doc_id not in docs.docs and len(docs.named("delete")) == 2  # with the instructions document
    assert not (world.ctx.files_dir / workspace_id).exists()


async def test_without_the_service_documents_wait_but_the_workspace_works(world):
    world.ctx.docs.running = False
    alice, _, workspace_id = await _workspace(world)
    listed = await world.call(alice, p.DOC_LIST, workspace_id=workspace_id)
    assert listed["docs"] == [] and listed["docservice"]["status"] == "stopped"
    assert (await world.fails(alice, p.DOC_CREATE, workspace_id=workspace_id, title="Plan")).code == UNAVAILABLE

    world.ctx.docs.running = True
    listed = await world.call(alice, p.DOC_LIST, workspace_id=workspace_id)
    assert [d["title"] for d in listed["docs"]] == ["Instructions"]


async def test_the_real_document_service(real_docservice, host):
    assert await host.docs.wait_ready(20), host.docs.status()
    operator = await host.operator("Alice")
    token = await host.rotate_token(operator.id)
    _, created = await rpc(host.base, p.WORKSPACE_CREATE, {"name": "launch", "title": "Launch"}, token)
    workspace_id = created["payload"]["workspace"]["id"]

    _, made = await rpc(host.base, p.DOC_CREATE, {"workspace_id": workspace_id, "title": "Plan", "markdown": "# Plan\n\nShip it.\n"}, token)
    doc_id = made["payload"]["doc"]["id"]
    _, read = await rpc(host.base, p.DOC_READ, {"doc_id": doc_id}, token)
    assert "<!-- block:" in read["payload"]["markdown"] and "Ship it." in read["payload"]["markdown"]

    _, imported = await rpc(host.base, p.DOC_IMPORT_MARKDOWN, {"doc_id": doc_id, "markdown": "Replaced.\n"}, token)
    assert imported["ok"], imported
    _, read = await rpc(host.base, p.DOC_READ, {"doc_id": doc_id}, token)
    assert "Replaced." in read["payload"]["markdown"] and "Ship it." not in read["payload"]["markdown"]

    _, listed = await rpc(host.base, p.DOC_LIST, {"workspace_id": workspace_id}, token)
    assert [d["title"] for d in listed["payload"]["docs"]] == ["Instructions", "Plan"]
    assert listed["payload"]["docservice"]["status"] == "running"
