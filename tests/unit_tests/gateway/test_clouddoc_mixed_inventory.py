"""The mixed inventory a person ordinarily holds (matrix §S, hardened 2026-09-07):
some documents only the team's service identity reaches, some only the person
does, some both. Three documents, one of each, across the four paths: chat
resolution, the panel listing, notices, and the receipts ledger.
"""

from __future__ import annotations

import json

import pytest

from jiuwenswarm.agents.harness.common.tools.clouddoc.clouddoc_tools import CloudDocToolkit
from jiuwenswarm.agents.harness.common.tools.clouddoc.provider import (
    AgentIdentity,
    DocCapabilities,
    DocComment,
    DocSnapshot,
    DocSummary,
    EditResult,
)
from jiuwenswarm.agents.harness.common.tools.clouddoc.receipts import ReceiptStore
from jiuwenswarm.agents.harness.common.tools.clouddoc.routing import RoutingProvider
from jiuwenswarm.gateway.clouddoc.comment_watcher import WatcherConfig
from jiuwenswarm.gateway.clouddoc.connections import CloudDocConnections
from jiuwenswarm.gateway.clouddoc.cursor_store import CloudDocStore
from jiuwenswarm.gateway.clouddoc.notices import NoticeStore
from jiuwenswarm.gateway.clouddoc.panel import CloudDocPanel
from jiuwenswarm.gateway.clouddoc.triggers import TriggerConfig

ME, BOT = "ou_me", "ou_bot"
S, P, B = "doc-service-only", "doc-personal-only", "doc-both"


class Clock:
    t = 1_000.0

    def __call__(self):
        return self.t


class Fake:
    def __init__(self, *, personal: bool, address: str, docs: list[str]):
        self.personal, self.identity_address, self.docs = personal, address, list(docs)
        self.comments: dict[str, list[DocComment]] = {}
        self.replies: list = []
        self.edits: list = []
        self.receipt_sink = None
        self.receipt_meta = None
        self.caps = DocCapabilities(
            can_read=True, can_edit=True, can_comment=True, can_resolve=False,
            has_revision_control=False, max_quote_chars=128,
        )

    @property
    def kind(self):
        return "feishu"

    def parse_doc_ref(self, s):
        return s.strip()

    def doc_url(self, d, kind=""):
        return f"https://x/{d}"

    async def self_identity(self):
        return AgentIdentity(display_name="张三" if self.personal else "bot", address=self.identity_address)

    async def capabilities(self, d):
        return self.caps

    async def sharing_posture(self, d):
        return []

    async def title(self, d):
        return {S: "只有服务", P: "只有我", B: "两边都有"}.get(d, d)

    async def doc_kind(self, d):
        return "document"

    async def read(self, d):
        return DocSnapshot(doc_id=d, kind="document", revision_id="r", text="hello world")

    async def list_comments(self, d, *, include_resolved=False):
        return list(self.comments.get(d, []))

    async def list_accessible_documents(self):
        return [DocSummary(doc_id=d, title=f"t-{d}", can_edit=True, kind="document") for d in self.docs]

    async def list_shared_unsupported(self):
        return []

    async def reply_comment(self, d, cid, content):
        self.replies.append((d, cid, content))
        return "r1"

    async def update_reply(self, d, cid, rid, content):
        raise AssertionError("must not be reached")

    async def delete_reply(self, d, cid, rid):
        raise AssertionError("must not be reached")

    async def edit_batch(self, d, pairs, *, required_revision_id=None, window=None, highlight=False):
        self.edits.append((d, list(pairs), dict(self.receipt_meta or {})))
        rid = None
        if self.receipt_sink is not None:
            rid = self.receipt_sink.begin(
                d, [{"old": o, "new": n} for o, n in pairs], highlight=False,
                executor=str((self.receipt_meta or {}).get("executor") or ""),
                source=str((self.receipt_meta or {}).get("source") or ""),
            )
            self.receipt_sink.commit(rid, revision_after="r2")
        return EditResult("applied", new_revision_id="r2", receipt_id=rid)


def C(cid, content, *, author=("ou_x", "小王"), mentioned=(), me=ME):
    aid, name = author
    return DocComment(
        comment_id=cid, author_is_self=(aid == me), author_display_name=name,
        created_time="2026-01-01T00:00:00Z", content=content, quoted_text="q",
        resolved=False, mentioned_addresses=tuple(mentioned),
    )


# ------------------------------------------------------------ chat resolution


def _routed(choice):
    svc = Fake(personal=False, address=BOT, docs=[S, B])
    me = Fake(personal=True, address=ME, docs=[P, B])
    docs = {"svc.json": [S, B], "me.json": [P, B]}
    return svc, me, RoutingProvider([("svc.json", svc), ("me.json", me)], lambda cf: docs[cf], choice)


@pytest.mark.asyncio
async def test_chat_resolution_covers_all_three_reaches():
    choices = {}
    svc, me, r = _routed(lambda d: choices.get(d, "service"))
    assert r.owner(S) is svc and r.reach(S) == "service"
    assert r.owner(P) is me and r.reach(P) == "personal"
    assert r.owner(B) is svc and r.reach(B) == "both", "both: service by default"
    choices[B] = "personal"
    assert r.owner(B) is me
    assert r.reach("nobody-has-this") == ""

    kit = CloudDocToolkit(r, watched_docs=lambda: [S, B, P, B])   # both specs list B
    out = await kit.list_documents()
    rows = {d["doc_id"]: d for d in out["documents"]}
    assert [d["doc_id"] for d in out["documents"]] == [S, B, P], "each document once, in adoption order"
    assert (rows[S]["identity"], rows[S]["reach"]) == ("service", "service")
    assert (rows[P]["identity"], rows[P]["reach"]) == ("personal", "personal")
    assert (rows[B]["identity"], rows[B]["reach"]) == ("personal", "both")
    assert rows[B]["title"] == "t-doc-both", "the listing's title wins; the per-doc probe fills gaps only"
    # A link resolves to the executing identity as well.
    kit._read_docs.add(B)
    assert kit._executor_for(B) == "chat:ou_me"
    choices.pop(B)
    assert kit._executor_for(B) == "chat"


# ------------------------------------------------------------ panel, notices, receipts


@pytest.fixture
def kit(tmp_path):
    store = CloudDocStore(tmp_path / "state.json", now_fn=Clock())
    providers: dict[str, Fake] = {}
    choices: dict[str, str] = {}

    def factory(path: str) -> Fake:
        body = json.loads(open(path).read())
        personal = body.get("kind") == "personal"
        p = Fake(personal=personal, address=ME if personal else BOT, docs=[P, B] if personal else [S, B])
        providers["me" if personal else "svc"] = p
        return p

    dispatched: list = []

    async def dispatch(doc_id, cid, meta):
        dispatched.append((doc_id, cid))
        return "ok"

    reg = CloudDocConnections(
        store=store, dispatcher=dispatch, watcher_cfg=WatcherConfig(),
        base_trigger_cfg=TriggerConfig(sa_address=""), provider_factory=factory,
        now_fn=Clock(), notice_store=NoticeStore(tmp_path / "n.json", now_fn=Clock()),
        choice_of=lambda d: choices.get(d, "service"),
    )
    svc = tmp_path / "svc.json"; svc.write_text(json.dumps({"app_id": "cli_x", "app_secret": "s", "bot_open_id": BOT}))
    me = tmp_path / "me.json"; me.write_text(json.dumps({"kind": "personal", "brand": "feishu", "open_id": ME, "name": "张三"}))
    cfg = tmp_path / "config.yaml"; cfg.write_text("clouddoc:\n  enabled: true\n  documents: []\n")

    class K:
        pass

    k = K()
    k.reg, k.store, k.panel, k.cfg, k.tmp = reg, store, CloudDocPanel(reg, config_path=cfg), cfg, tmp_path
    k.svc, k.me, k.providers, k.choices, k.dispatched = str(svc), str(me), providers, choices, dispatched
    return k


async def _inventory(kit):
    s = await kit.reg.add(kit.svc, [S, B])
    p = await kit.reg.add(kit.me, [P, B])
    return s, p


@pytest.mark.asyncio
async def test_panel_lists_the_union_once_with_reach_and_identity(kit):
    s, p = await _inventory(kit)
    rows = {r["doc_id"]: r for r in await kit.panel.list_docs()}
    assert sorted(rows) == sorted([S, P, B]), "the union, each document once"
    assert rows[S]["reach"] == "service" and rows[S]["identity"] == "service"
    assert rows[S]["connections"] == {"service": s.id} and rows[S]["notices"] == 0
    assert rows[P]["reach"] == "personal" and rows[P]["identity"] == "personal"
    assert rows[P]["connections"] == {"personal": p.id}
    assert rows[B]["reach"] == "both" and rows[B]["identity"] == "service"
    assert rows[B]["connections"] == {"service": s.id, "personal": p.id}
    assert rows[B]["connection_id"] == s.id
    assert set(rows[B]["status_by"]) == {"service", "personal"}
    # Health is judged per identity: the person losing access to B does not
    # change the service row's verdict, and the row's headline follows the
    # executing identity.
    await kit.reg.store_for(p).note_permanent_failure(B, "no_read_access")
    rows = {r["doc_id"]: r for r in await kit.panel.list_docs()}
    assert rows[B]["status"] == "ok" and rows[B]["status_by"]["personal"] == "frozen"
    kit.choices[B] = "personal"
    rows = {r["doc_id"]: r for r in await kit.panel.list_docs()}
    assert rows[B]["identity"] == "personal" and rows[B]["connection_id"] == p.id
    assert rows[B]["status"] == "frozen"
    await kit.reg.stop_all()


@pytest.mark.asyncio
async def test_discovery_marks_what_the_service_identity_already_holds(kit):
    s, p = await _inventory(kit)
    kit.providers["me"].docs = [S, P, B, "doc-new"]
    out = await kit.panel.sync_shared_docs(p.id)
    by = {c["doc_id"]: c for c in out["candidates"]}
    assert by[S]["adopted_by"] == "service" and by[S]["adopted"] is False
    assert by[P]["adopted_by"] == "personal" and by[P]["adopted"] is True
    assert by[B]["adopted_by"] == "both" and by[B]["adopted"] is True
    assert by["doc-new"]["adopted_by"] == "" and by["doc-new"]["adopted"] is False
    # Ticking the service-held one makes it reachable both ways: still one row.
    await kit.panel.adopt_docs(p.id, [S])
    rows = {r["doc_id"]: r for r in await kit.panel.list_docs()}
    assert len(rows) == 3 and rows[S]["reach"] == "both"
    await kit.reg.stop_all()


@pytest.mark.asyncio
async def test_notices_go_only_where_the_person_reaches_and_never_post(kit):
    s, p = await _inventory(kit)
    pushed: list = []

    async def push(event, payload):
        pushed.append(payload)

    kit.panel.bind_notifier(push)
    svc, me = kit.providers["svc"], kit.providers["me"]
    # Seed every document first (first watch registers, never replays).
    await s.watcher.tick()
    await p.watcher.tick()
    # One comment summoning both identities on the shared document, one mention
    # of the person on the service-only document (where the person has no
    # watcher), one mention of the bot on the personal-only document.
    both = C("c-b", "@张三 @bot 看看", mentioned=(ME, BOT))
    svc.comments = {S: [C("c-s", "@张三 你看", mentioned=(ME,))], B: [both]}
    me.comments = {P: [C("c-p", "@bot 你看", mentioned=(BOT,))], B: [both]}
    await s.watcher.tick()
    await p.watcher.tick()
    assert kit.dispatched == [(B, "c-b")], "the service watcher answers the bot's summons only"
    assert [(n["doc_id"], n["comment_id"]) for n in pushed] == [(B, "c-b")], (
        "the person is told about B; nobody reaches S for them, and P had no mention of them"
    )
    assert me.replies == [] and me.edits == [], "a personal watcher never posts"
    rows = {r["doc_id"]: r for r in await kit.panel.list_docs()}
    assert rows[B]["notices"] == 1 and rows[S]["notices"] == 0 and rows[P]["notices"] == 0
    await kit.reg.stop_all()


@pytest.mark.asyncio
async def test_receipts_on_a_shared_document_show_both_executing_identities(kit, tmp_path):
    s, p = await _inventory(kit)
    ledger = ReceiptStore(tmp_path / "r.json", now_fn=Clock())
    svc, me = kit.providers["svc"], kit.providers["me"]
    svc.receipt_sink = me.receipt_sink = ledger
    for prov in (svc, me):
        kit_ = CloudDocToolkit(prov, watched_docs=lambda: [B], ask_channel=False, harness_mode="direct")
        kit_._read_docs.add(B)
        out = await kit_.batch_edit(B, edits=[{"old_string": "hello", "new_string": "hi"}])
        assert out["ok"] is True, out
    rows = ledger.list_for(B)
    assert sorted(r["executor"] for r in rows) == ["chat", "chat:ou_me"], (
        "the ledger holds both identities' writes on one document, each naming who executed"
    )
    # The audit view aggregates the same ledger and lists both executors.
    class Reg:
        def get(self, d):
            return None

        def usage_summary(self, d):
            return {"dispatches": 0, "denials": {}}

    kit.reg._watch_registry = Reg()
    import jiuwenswarm.gateway.clouddoc.panel as panel_mod
    real = panel_mod.ReceiptStore if hasattr(panel_mod, "ReceiptStore") else None
    from jiuwenswarm.agents.harness.common.tools.clouddoc import receipts as receipts_mod
    orig = receipts_mod.ReceiptStore.__init__

    def patched(self_, path=None, **kw):
        orig(self_, tmp_path / "r.json", **kw)

    receipts_mod.ReceiptStore.__init__ = patched
    try:
        usage = await kit.panel.watch_usage(B)
    finally:
        receipts_mod.ReceiptStore.__init__ = orig
    assert usage["used"]["executors"] == ["chat", "chat:ou_me"]
    await kit.reg.stop_all()
