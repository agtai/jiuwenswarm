"""Shared IM bots and connected IM accounts: who makes bots, link codes, reading on behalf of a
connected person and nothing else, revocation, rate limits, and reference text for agents."""

from __future__ import annotations

from pathlib import Path

from jiuwenswarm.extensions.blackboard.common import protocol as p
from jiuwenswarm.extensions.blackboard.common.errors import FORBIDDEN, RATE_LIMITED, BlackboardError
from jiuwenswarm.extensions.blackboard.common.tokens import normalize_link_code
import pytest

from jiuwenswarm.extensions.blackboard.common.ids import new_id
from jiuwenswarm.extensions.blackboard.host.api.ratelimit import RateLimiter
from jiuwenswarm.extensions.blackboard.host.store import references
from jiuwenswarm.extensions.blackboard.tests.backend.support import rpc


async def _team(host):
    """Alice runs the host (the operator) with a workspace Bob belongs to, and Carol, in no workspace."""
    alice = await host.operator("Alice")
    token = await host.rotate_token(alice.id)
    _, created = await rpc(host.base, p.WORKSPACE_CREATE, {"name": "launch", "title": "Launch"}, token)
    workspace_id = created["payload"]["workspace"]["id"]
    people = {}
    for name, into in (("Bob", workspace_id), ("Carol", None)):
        if into:
            _, invite = await rpc(host.base, p.INVITE_CREATE, {"workspace_id": into, "role": "viewer"}, token)
            code = invite["payload"]["invite"]["code"]
        else:
            _, other = await rpc(host.base, p.WORKSPACE_CREATE, {"name": f"only-{name.lower()}", "title": "Other"}, token)
            _, invite = await rpc(host.base, p.INVITE_CREATE, {"workspace_id": other["payload"]["workspace"]["id"], "role": "viewer"}, token)
            code = invite["payload"]["invite"]["code"]
        _, joined = await rpc(host.base, p.INVITE_ACCEPT, {"code": code, "display_name": name})
        people[name] = joined["payload"]["token"]
    return token, workspace_id, people


def _as(bot_token: str, identity: str | None = None) -> dict:
    return {"token": bot_token, "headers": {p.ON_BEHALF_HEADER: identity} if identity else {}}


async def test_only_the_operator_makes_and_revokes_bots(host):
    alice, _, people = await _team(host)
    status, made = await rpc(host.base, p.BOT_CREATE, {"name": "Team bot"}, alice)
    assert status == 200 and made["payload"]["token"].startswith("bbb_")
    assert made["payload"]["link"] == f"{host.base}{p.BOT_PATH}#{made['payload']['token']}"
    _, listed = await rpc(host.base, p.BOT_LIST, {}, alice)
    assert [b["name"] for b in listed["payload"]["bots"]] == ["Team bot"]
    _, denied = await rpc(host.base, p.BOT_CREATE, {"name": "Mine"}, people["Bob"])
    assert denied["error"]["code"] == FORBIDDEN

    _, me = await rpc(host.base, p.BOT_WHOAMI, {}, made["payload"]["token"])
    assert me["payload"]["bot"]["name"] == "Team bot"
    # A member's token is not a bot's.
    assert (await rpc(host.base, p.BOT_WHOAMI, {}, alice))[0] == 403

    await rpc(host.base, p.BOT_REVOKE, {"bot_id": made["payload"]["bot"]["id"]}, alice)
    status, revoked = await rpc(host.base, p.BOT_WHOAMI, {}, made["payload"]["token"])
    assert status == 401 and "revoked" in revoked["error"]["message"]


async def test_a_bot_reads_as_the_connected_person_and_only_reads(host):
    alice, workspace_id, people = await _team(host)
    _, made = await rpc(host.base, p.BOT_CREATE, {"name": "Team bot"}, alice)
    bot = made["payload"]["token"]

    # Before connecting, the bot can only say how to connect.
    _, unknown = await rpc(host.base, p.DOC_LIST, {"workspace_id": workspace_id}, **_as(bot, "slack:U_BOB"))
    assert unknown["error"]["code"] == "not_linked" and "Connect" in unknown["error"]["message"]
    _, nobody = await rpc(host.base, p.DOC_LIST, {"workspace_id": workspace_id}, **_as(bot))
    assert nobody["error"]["code"] == "not_linked"

    _, code = await rpc(host.base, p.IDENTITY_LINK_CODE, {}, people["Bob"])
    typed = code["payload"]["code"].lower().replace("-", " ")
    _, linked = await rpc(host.base, p.IDENTITY_LINK, {"code": typed, "platform": "slack", "external_id": "U_BOB", "display_name": "bob"}, bot)
    assert linked["payload"]["user"]["display_name"] == "Bob" and linked["payload"]["replaced"] is False
    _, again = await rpc(host.base, p.IDENTITY_LINK, {"code": typed, "platform": "slack", "external_id": "U_BOB"}, bot)
    assert again["error"]["code"] == "expired"
    # A member cannot connect accounts; only a bot can.
    assert (await rpc(host.base, p.IDENTITY_LINK, {"code": "X", "platform": "slack", "external_id": "U"}, people["Bob"]))[0] == 403

    _, docs = await rpc(host.base, p.DOC_LIST, {"workspace_id": workspace_id}, **_as(bot, "slack:U_BOB"))
    assert docs["ok"], docs
    _, me = await rpc(host.base, p.ME, {}, **_as(bot, "slack:U_BOB"))
    assert me["payload"]["display_name"] == "Bob"
    for method, params in ((p.DOC_CREATE, {"workspace_id": workspace_id, "title": "X"}), (p.IDENTITY_LINK_CODE, {}), (p.CHAT_POST, {"workspace_id": workspace_id, "body": "hi"})):
        status, refused = await rpc(host.base, method, params, **_as(bot, "slack:U_BOB"))
        assert (status, refused["error"]["code"]) == (403, FORBIDDEN), method

    _, identities = await rpc(host.base, p.IDENTITY_LIST, {}, people["Bob"])
    assert identities["payload"]["identities"] == [
        {"platform": "slack", "external_id": "U_BOB", "display_name": "bob", "linked_at": identities["payload"]["identities"][0]["linked_at"]}
    ]

    # The same IM account connected with Carol's code now reads as Carol, who is not in the workspace.
    _, carol_code = await rpc(host.base, p.IDENTITY_LINK_CODE, {}, people["Carol"])
    _, moved = await rpc(host.base, p.IDENTITY_LINK, {"code": carol_code["payload"]["code"], "platform": "slack", "external_id": "U_BOB"}, bot)
    assert moved["payload"]["replaced"] is True
    _, as_carol = await rpc(host.base, p.DOC_LIST, {"workspace_id": workspace_id}, **_as(bot, "slack:U_BOB"))
    assert as_carol["error"]["code"] == "not_member"
    assert (await rpc(host.base, p.IDENTITY_LIST, {}, people["Bob"]))[1]["payload"]["identities"] == []

    await rpc(host.base, p.IDENTITY_UNLINK, {"platform": "slack", "external_id": "U_BOB"}, people["Carol"])
    _, gone = await rpc(host.base, p.ME, {}, **_as(bot, "slack:U_BOB"))
    assert gone["error"]["code"] == "not_linked"


async def test_link_codes_expire_and_only_the_newest_works(host):
    alice, _, people = await _team(host)
    _, made = await rpc(host.base, p.BOT_CREATE, {"name": "Team bot"}, alice)
    bot = made["payload"]["token"]
    _, first = await rpc(host.base, p.IDENTITY_LINK_CODE, {}, people["Bob"])
    _, second = await rpc(host.base, p.IDENTITY_LINK_CODE, {}, people["Bob"])
    link = {"platform": "feishu", "external_id": "ou_1"}
    assert (await rpc(host.base, p.IDENTITY_LINK, {"code": first["payload"]["code"], **link}, bot))[1]["error"]["code"] == "expired"
    await host.store.transact(lambda c: c.execute("UPDATE im_link_codes SET expires_at = '2000-01-01T00:00:00.000Z'"))
    assert (await rpc(host.base, p.IDENTITY_LINK, {"code": second["payload"]["code"], **link}, bot))[1]["error"]["code"] == "expired"
    assert normalize_link_code("ab cd-ef gh") == "ABCD-EFGH"


async def test_agents_and_bots_are_held_to_calls_per_minute(host):
    alice, workspace_id, people = await _team(host)
    host.ctx.limits = RateLimiter(clock=lambda: 100.0)
    agent = {p.AGENT_HEADER: "1"}
    for _ in range(60):
        assert (await rpc(host.base, p.DOC_LIST, {"workspace_id": workspace_id}, people["Bob"], headers=agent))[1]["ok"]
    status, limited = await rpc(host.base, p.DOC_LIST, {"workspace_id": workspace_id}, people["Bob"], headers=agent)
    assert (status, limited["error"]["code"]) == (429, RATE_LIMITED)
    # The browser's own calls (no agent header) are not counted.
    assert (await rpc(host.base, p.DOC_LIST, {"workspace_id": workspace_id}, people["Bob"]))[1]["ok"]

    limiter = RateLimiter(clock=lambda: 0.0)
    for _ in range(3):
        limiter.check("k", 3)
    with pytest.raises(BlackboardError) as caught:
        limiter.check("k", 3)
    assert caught.value.details["retry_after"] == 61
    later = RateLimiter(clock=iter([0.0, 0.0, 61.0]).__next__)
    later.check("k", 2)
    later.check("k", 2)
    later.check("k", 2)  # the first two fell out of the window


# ---- reference text ----

def _minimal_pdf(text: str) -> bytes:
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for i, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


NOTES = "# Notes\n\nShip on Friday.\n"


async def test_reference_text_for_agents(world, tmp_path):
    import docx

    alice, _ = await world.user("Alice")
    vera, _ = await world.user("Vera")
    workspace_id = await world.workspace(alice)
    await world.add(workspace_id, vera, "viewer")

    document = docx.Document()
    document.add_paragraph("Risks: quality.")
    table = document.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text, table.rows[0].cells[1].text = "Owner", "Bob"
    docx_path = tmp_path / "plan.docx"
    document.save(docx_path)
    samples = {
        "notes.md": ("text/markdown", NOTES.encode()),
        "plan.docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", docx_path.read_bytes()),
        "brief.pdf": ("application/pdf", _minimal_pdf("Launch in October")),
        "logo.png": ("image/png", b"\x89PNG\r\n\x1a\n"),
        "data.bin": ("application/octet-stream", b"\x00\x01"),
    }
    ids = {}
    for name, (mime, data) in samples.items():
        reference_id = new_id("r")
        stored = f"{workspace_id}/{reference_id}{Path(name).suffix}"
        target = world.ctx.files_dir / stored
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        await world.store.transact(
            lambda c, reference_id=reference_id, name=name, mime=mime, stored=stored, data=data: references.create(
                c, reference_id=reference_id, workspace_id=workspace_id, kind="file", name=name, mime=mime,
                size=len(data), stored_path=stored, note="", uploaded_by=alice.id,
            )
        )
        ids[name] = reference_id

    read = lambda name: world.call(vera, p.REFERENCE_READ, reference_id=ids[name])  # noqa: E731
    notes = await read("notes.md")
    assert (notes["kind"], notes["text"], notes["truncated"]) == ("text", NOTES, False)
    word = await read("plan.docx")
    assert "Risks: quality." in word["text"] and "Owner | Bob" in word["text"]
    pdf = await read("brief.pdf")
    assert "Launch in October" in pdf["text"]
    for name in ("logo.png", "data.bin"):
        refused = await world.fails(vera, p.REFERENCE_READ, reference_id=ids[name])
        assert refused.code == "unsupported_reference", name
    outsider, _ = await world.user("Mallory")
    assert (await world.fails(outsider, p.REFERENCE_READ, reference_id=ids["notes.md"])).code == "not_member"
