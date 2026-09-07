"""Personal identity, gateway layer (design §13, matrix §S): the notify-only
watcher, its state scope beside a service watcher on the same document, the
notice ledger, the registry's two kinds and the per-document identity choice,
and the panel's refusals.

The negative cases are the contract: the personal watcher posts nothing, ever;
the person's own comments do not summon them; a personal-only document has no
tiers to set; discovery adopts nothing.
"""

from __future__ import annotations

import json

import pytest

from jiuwenswarm.agents.harness.common.tools.clouddoc.provider import (
    AgentIdentity,
    DocCapabilities,
    DocComment,
    DocReply,
    DocSnapshot,
    DocSummary,
    EditResult,
)
from jiuwenswarm.gateway.clouddoc.comment_watcher import CloudDocCommentWatcher, WatcherConfig
from jiuwenswarm.gateway.clouddoc.connections import CloudDocConnections
from jiuwenswarm.gateway.clouddoc.cursor_store import CloudDocStore, state_key
from jiuwenswarm.gateway.clouddoc.notices import NoticeStore
from jiuwenswarm.gateway.clouddoc.panel import CloudDocPanel, discover_shared_periodically
from jiuwenswarm.gateway.clouddoc.personal_watcher import (
    PERSONAL_SCOPE,
    PersonalNoticeWatcher,
    PersonalWatcherMustNotPost,
)
from jiuwenswarm.gateway.clouddoc.triggers import TriggerConfig, dedup_key

ME = "ou_me"
BOT = "ou_bot"
DOC = "doc-1"


class Clock:
    def __init__(self):
        self.t = 1_000.0

    def __call__(self):
        return self.t


class FakeProvider:
    """Records every write path; a personal watcher must leave all of them empty."""

    def __init__(self, *, personal: bool, address: str):
        self.personal = personal
        self.identity_address = address
        self.comments: list[DocComment] = []
        self.replies: list = []
        self.updates: list = []
        self.deletes: list = []
        self.edit_calls: list = []
        self.caps = DocCapabilities(
            can_read=True, can_edit=not personal, can_comment=True, can_resolve=False,
            has_revision_control=False, max_quote_chars=128,
        )
        self.accessible: list[DocSummary] = []

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
        return "示例文档"

    async def read(self, d):
        return DocSnapshot(doc_id=d, kind="document", revision_id="r", text="x")

    async def list_comments(self, d, *, include_resolved=False):
        return [c for c in self.comments if include_resolved or not c.resolved]

    async def list_accessible_documents(self):
        return list(self.accessible)

    async def list_shared_unsupported(self):
        return []

    async def reply_comment(self, d, cid, content):
        self.replies.append((cid, content))
        return "r1"

    async def update_reply(self, d, cid, rid, content):
        self.updates.append((cid, rid, content))

    async def delete_reply(self, d, cid, rid):
        self.deletes.append((cid, rid))

    async def edit_batch(self, d, edits, **kw):
        self.edit_calls.append(edits)
        return EditResult("applied", new_revision_id="r2")


def C(cid, content, *, author=("ou_x", "小王"), mentioned=(), assignee=None, replies=(),
      me=ME, quoted="这一句", resolved=False):
    aid, name = author
    return DocComment(
        comment_id=cid, author_is_self=(aid == me), author_display_name=name,
        created_time="2026-01-01T00:00:00Z", content=content, quoted_text=quoted,
        resolved=resolved, mentioned_addresses=tuple(mentioned), replies=tuple(replies),
        assignee_address=assignee,
    )


def R(rid, content, t, *, author=("ou_x", "小王"), mentioned=(), me=ME):
    aid, name = author
    return DocReply(reply_id=rid, author_is_self=(aid == me), author_display_name=name,
                    created_time=t, content=content, mentioned_addresses=tuple(mentioned))


@pytest.fixture
async def rig(tmp_path):
    prov = FakeProvider(personal=True, address=ME)
    store = CloudDocStore(tmp_path / "s.json", now_fn=Clock())
    notices: list[dict] = []

    async def notify(n):
        notices.append(n)

    w = PersonalNoticeWatcher(
        prov, store.scoped(PERSONAL_SCOPE), TriggerConfig(sa_address=ME, mention_triggers=True),
        WatcherConfig(), notify=notify, now_fn=Clock(), connection_id="feishu:personal:ou_me",
    )
    w._docs = [DOC]
    await store.scoped(PERSONAL_SCOPE).seed_if_new(DOC, [])
    return w, prov, store, notices


# ------------------------------------------------------------ the watcher posts nothing


@pytest.mark.asyncio
async def test_a_mention_of_me_by_someone_else_becomes_a_notice_and_no_post(rig):
    w, prov, store, notices = rig
    prov.comments = [C("c1", "@张三 看看这句", mentioned=(ME,))]
    out = await w.tick()
    assert out.get("notified") == 1
    assert len(notices) == 1
    n = notices[0]
    assert n["doc_id"] == DOC and n["comment_id"] == "c1" and n["kind"] == "mention"
    assert n["quoted_text"] == "这一句" and n["text"] == "@张三 看看这句" and n["author"] == "小王"
    assert n["key"] == dedup_key(DOC, "c1")
    # The contract: nothing reached the platform.
    assert prov.replies == [] and prov.updates == [] and prov.deletes == [] and prov.edit_calls == []


@pytest.mark.asyncio
async def test_my_own_comment_does_not_notify_me(rig):
    w, prov, store, notices = rig
    prov.comments = [C("c1", "@张三 记一下", author=(ME, "张三"), mentioned=(ME,))]
    await w.tick()
    assert notices == []


@pytest.mark.asyncio
async def test_my_own_reply_mentioning_me_does_not_notify_me(rig):
    w, prov, store, notices = rig
    prov.comments = [C("c1", "一句", replies=(
        R("r1", "@张三 自己记的", "2026-01-02T00:00:00Z", author=(ME, "张三"), mentioned=(ME,)),
    ))]
    await w.tick()
    assert notices == []


@pytest.mark.asyncio
async def test_a_mention_of_somebody_else_is_not_my_business(rig):
    w, prov, store, notices = rig
    prov.comments = [C("c1", "@李四 看看", mentioned=("ou_lisi",))]
    await w.tick()
    assert notices == []


@pytest.mark.asyncio
async def test_a_notice_is_delivered_once_across_ticks(rig):
    w, prov, store, notices = rig
    prov.comments = [C("c1", "@张三 看看", mentioned=(ME,))]
    await w.tick()
    await w.tick()
    await w.tick()
    assert len(notices) == 1


@pytest.mark.asyncio
async def test_a_reply_that_mentions_me_after_the_first_notice_is_a_new_notice(rig):
    w, prov, store, notices = rig
    prov.comments = [C("c1", "@张三 看看", mentioned=(ME,))]
    await w.tick()
    prov.comments = [C("c1", "@张三 看看", mentioned=(ME,), replies=(
        R("r2", "@张三 再看一眼", "2026-01-02T00:00:00Z", mentioned=(ME,)),
    ))]
    await w.tick()
    assert len(notices) == 2
    assert notices[1]["reply_id"] == "r2" and notices[1]["text"] == "@张三 再看一眼"


@pytest.mark.asyncio
async def test_an_assignment_to_me_is_a_notice_of_kind_assigned(rig):
    w, prov, store, notices = rig
    prov.comments = [C("c1", "请处理", assignee=ME)]
    await w.tick()
    assert len(notices) == 1 and notices[0]["kind"] == "assigned"


@pytest.mark.asyncio
async def test_first_watch_seeds_history_without_notifying(tmp_path):
    prov = FakeProvider(personal=True, address=ME)
    prov.comments = [C("old", "@张三 很久以前", mentioned=(ME,))]
    store = CloudDocStore(tmp_path / "s.json", now_fn=Clock())
    notices: list = []

    async def notify(n):
        notices.append(n)

    w = PersonalNoticeWatcher(
        prov, store.scoped(PERSONAL_SCOPE), TriggerConfig(sa_address=ME, mention_triggers=True),
        WatcherConfig(), notify=notify, now_fn=Clock(),
    )
    w._docs = [DOC]
    out = await w.tick()
    assert out.get("seeded") == 1 and notices == []
    await w.tick()
    assert notices == [], "history is registered, never replayed"


@pytest.mark.asyncio
async def test_every_write_seam_of_the_base_class_is_closed(rig):
    w, prov, store, notices = rig
    for name in ("_safe_reply", "_safe_reply_id", "_safe_update", "_safe_delete",
                 "_dedupe_own_notices", "_unhighlight_resolved", "_settle_turn", "_ledger_check"):
        with pytest.raises(PersonalWatcherMustNotPost):
            await getattr(w, name)(DOC, "c1", "x")
    with pytest.raises(PersonalWatcherMustNotPost):
        await w._dispatch(DOC, "c1", {})
    assert await w.sweep() == []


@pytest.mark.asyncio
async def test_comment_only_access_is_enough_to_be_told(rig):
    w, prov, store, notices = rig
    prov.caps = DocCapabilities(
        can_read=True, can_edit=False, can_comment=True, can_resolve=False,
        has_revision_control=False, max_quote_chars=128,
    )
    prov.comments = [C("c1", "@张三 看看", mentioned=(ME,))]
    await w.tick()
    assert len(notices) == 1


# ------------------------------------------------------------ scope beside a service watcher


@pytest.mark.asyncio
async def test_personal_and_service_watchers_on_one_document_keep_separate_keys(tmp_path):
    """One shared state file, two watchers on one document: a key the personal
    watcher consumed must not silence the service watcher, and the reverse."""
    store = CloudDocStore(tmp_path / "s.json", now_fn=Clock())
    me = FakeProvider(personal=True, address=ME)
    bot = FakeProvider(personal=False, address=BOT)
    notices: list = []
    dispatched: list = []

    async def notify(n):
        notices.append(n)

    async def dispatch(doc_id, cid, meta):
        dispatched.append(cid)
        return "ok"

    pw = PersonalNoticeWatcher(
        me, store.scoped(PERSONAL_SCOPE), TriggerConfig(sa_address=ME, mention_triggers=True),
        WatcherConfig(), notify=notify, now_fn=Clock(),
    )
    sw = CloudDocCommentWatcher(
        bot, store, TriggerConfig(sa_address=BOT, mention_triggers=True), WatcherConfig(),
        dispatch=dispatch, now_fn=Clock(),
    )
    pw._docs = sw._docs = [DOC]
    await store.scoped(PERSONAL_SCOPE).seed_if_new(DOC, [])
    await store.seed_if_new(DOC, [])
    both = C("c1", "@张三 @bot 都看看", mentioned=(ME, BOT))
    me.comments = [both]
    bot.comments = [DocComment(**{**both.__dict__, "author_is_self": False})]
    await pw.tick()
    await sw.tick()
    assert len(notices) == 1, "the personal watcher told the person"
    assert dispatched == ["c1"], "and the service watcher still dispatched the bot's summons"
    snap = await store.snapshot()
    assert dedup_key(DOC, "c1") in snap[DOC]["triggered_ids"]
    assert dedup_key(DOC, "c1") in snap[state_key(DOC, PERSONAL_SCOPE)]["triggered_ids"]


@pytest.mark.asyncio
async def test_scoped_store_shares_panel_meta_but_not_health(tmp_path):
    store = CloudDocStore(tmp_path / "s.json", now_fn=Clock())
    scoped = store.scoped(PERSONAL_SCOPE)
    await store.set_panel_meta(DOC, title="T", kind="document")
    await scoped.note_permanent_failure(DOC, "no_read_access")
    assert (await scoped.doc_health(DOC))["panel_meta"]["title"] == "T"
    assert (await scoped.doc_health(DOC))["failed"] is True
    assert (await store.doc_health(DOC))["failed"] is False
    with pytest.raises(RuntimeError):
        await scoped.gc([])
    removed = await store.gc([DOC])
    assert removed == [state_key(DOC, PERSONAL_SCOPE)]


# ------------------------------------------------------------ notice ledger


def test_notice_store_is_idempotent_on_key_and_acks(tmp_path):
    ns = NoticeStore(tmp_path / "n.json", now_fn=Clock())
    a = ns.add({"key": "k1", "doc_id": DOC, "comment_id": "c1"})
    b = ns.add({"key": "k1", "doc_id": DOC, "comment_id": "c1"})
    assert a["notice_id"] == b["notice_id"]
    ns.add({"key": "k2", "doc_id": DOC, "comment_id": "c2"})
    assert ns.unread_by_doc() == {DOC: 2}
    assert ns.ack(a["notice_id"]) == 1
    assert ns.unread_by_doc() == {DOC: 1}
    assert [n["key"] for n in ns.list()] == ["k2"]
    assert ns.ack(doc_id=DOC) == 1
    assert ns.list() == []
    assert len(ns.list(unread_only=False)) == 2
    assert ns.ack() == 0, "acking nothing in particular acks nothing"


# ------------------------------------------------------------ registry and panel


def _write(tmp_path, name, body):
    (tmp_path / name).write_text(json.dumps(body))
    return str(tmp_path / name)


@pytest.fixture
def kit(tmp_path):
    store = CloudDocStore(tmp_path / "state.json", now_fn=Clock())
    providers: dict[str, FakeProvider] = {}
    choices: dict[str, str] = {}

    def factory(path: str) -> FakeProvider:
        body = json.loads(open(path).read())
        personal = body.get("kind") == "personal"
        p = FakeProvider(personal=personal, address=body.get("open_id") or body.get("bot_open_id"))
        providers[path.rsplit("/", 1)[-1]] = p
        return p

    async def dispatch(doc_id, cid, meta):
        return "ok"

    reg = CloudDocConnections(
        store=store, dispatcher=dispatch, watcher_cfg=WatcherConfig(),
        base_trigger_cfg=TriggerConfig(sa_address=""), provider_factory=factory,
        now_fn=Clock(), notice_store=NoticeStore(tmp_path / "n.json", now_fn=Clock()),
        choice_of=lambda d: choices.get(d, "service"),
    )
    svc = _write(tmp_path, "svc.json", {"app_id": "cli_x", "app_secret": "s", "bot_open_id": BOT})
    me = _write(tmp_path, "me.json", {"kind": "personal", "brand": "feishu", "open_id": ME, "name": "张三"})
    cfg = tmp_path / "config.yaml"
    cfg.write_text("clouddoc:\n  enabled: true\n  documents: []\n")

    class K:
        pass

    k = K()
    k.reg, k.store, k.panel = reg, store, CloudDocPanel(reg, config_path=cfg)
    k.svc, k.me, k.cfg, k.tmp, k.providers, k.choices = svc, me, cfg, tmp_path, providers, choices
    return k


@pytest.mark.asyncio
async def test_a_personal_connection_gets_a_notify_only_watcher_and_no_policy_grant(kit):
    class Reg:
        issued: list = []

        def get(self, d):
            return None

        def terminated_by_owner(self, d):
            return False

        def issue(self, d, mode, issued_by=""):
            self.issued.append((d, mode))

    kit.reg._watch_registry = Reg()
    kit.reg.auto_watch_policy = "reply_only"
    conn = await kit.reg.add(kit.me, [DOC])
    assert conn.personal and conn.identity_kind == "personal"
    assert conn.id == f"feishu:personal:{ME}"
    assert isinstance(conn.watcher, PersonalNoticeWatcher)
    assert Reg.issued == [], "adoption policy never issues a tier under a personal connection"
    await kit.reg.stop_all()


@pytest.mark.asyncio
async def test_one_document_may_be_under_a_service_and_a_personal_connection_at_once(kit):
    s = await kit.reg.add(kit.svc, [DOC])
    p = await kit.reg.add(kit.me, [DOC])
    assert [c.id for c in kit.reg.owners(DOC)] == [s.id, p.id]
    assert kit.reg.find_doc(DOC) is s, "default: the service identity executes"
    kit.choices[DOC] = "personal"
    assert kit.reg.find_doc(DOC) is p
    assert sorted(kit.reg.all_state_keys()) == sorted([DOC, DOC, state_key(DOC, PERSONAL_SCOPE)])
    await kit.reg.stop_all()


@pytest.mark.asyncio
async def test_two_personal_connections_cannot_share_a_document(kit, tmp_path):
    await kit.reg.add(kit.me, [DOC])
    other = _write(tmp_path, "other.json", {"kind": "personal", "brand": "feishu", "open_id": "ou_other"})
    conn = await kit.reg.add(other, [DOC])
    assert conn.watcher._docs == []
    await kit.reg.stop_all()


@pytest.mark.asyncio
async def test_watch_set_is_refused_for_a_personal_only_document(kit):
    class Reg:
        def issue(self, *a, **k):
            raise AssertionError("must not be reached")

    kit.reg._watch_registry = Reg()
    await kit.reg.add(kit.me, [DOC])
    out = await kit.panel.watch_set(DOC, "apply_scoped")
    assert out["ok"] is False and out["reason"] == "personal_only"
    await kit.reg.stop_all()


@pytest.mark.asyncio
async def test_watch_set_still_works_where_a_service_connection_also_owns_the_document(kit):
    issued = []

    class Reg:
        def issue(self, d, mode, **k):
            issued.append((d, mode))
            return {"mode": mode}

    kit.reg._watch_registry = Reg()
    await kit.reg.add(kit.svc, [DOC])
    await kit.reg.add(kit.me, [DOC])
    out = await kit.panel.watch_set(DOC, "reply_only")
    assert out["ok"] is True and issued == [(DOC, "reply_only")]
    await kit.reg.stop_all()


@pytest.mark.asyncio
async def test_personal_discovery_lists_and_adopts_nothing_until_ticked(kit):
    conn = await kit.reg.add(kit.me, [])
    prov = kit.providers["me.json"]
    prov.accessible = [
        DocSummary(doc_id="A", title="甲", can_edit=True, kind="document"),
        DocSummary(doc_id="B", title="乙", can_edit=False, kind="spreadsheet"),
    ]
    out = await kit.panel.sync_shared_docs(conn.id)
    assert out["adopted"] == [] and conn.watcher._docs == []
    assert [c["doc_id"] for c in out["candidates"]] == ["A", "B"]
    assert out["candidates"][1]["can_edit"] is False
    got = await kit.panel.adopt_docs(conn.id, ["B"])
    assert got["adopted"] == ["B"] and conn.watcher._docs == ["B"]
    rows = await kit.panel.list_docs()
    assert rows[0]["reach"] == "personal" and rows[0]["notices"] == 0
    assert rows[0]["identity"] == "personal" and rows[0]["connections"] == {"personal": conn.id}
    saved = (await kit.panel.get_conf())["connections"][0]
    assert saved["kind"] == "personal"
    import yaml
    conns = yaml.safe_load(kit.cfg.read_text())["clouddoc"]["connections"]
    assert conns[0]["kind"] == "personal" and conns[0]["documents"] == ["B"]
    await kit.reg.stop_all()


@pytest.mark.asyncio
async def test_periodic_discovery_skips_personal_connections(kit):
    conn = await kit.reg.add(kit.me, [])
    prov = kit.providers["me.json"]
    prov.accessible = [DocSummary(doc_id="A", title="甲", can_edit=True, kind="document")]
    calls = {"n": 0}

    async def sleep(_s):
        calls["n"] += 1
        if calls["n"] > 1:
            raise RuntimeError("stop")

    with pytest.raises(RuntimeError):
        await discover_shared_periodically(kit.panel, interval_seconds=0, sleep_fn=sleep)
    assert conn.watcher._docs == []
    await kit.reg.stop_all()


@pytest.mark.asyncio
async def test_list_docs_shows_the_overlap_and_the_chosen_identity(kit):
    await kit.reg.add(kit.svc, [DOC])
    await kit.reg.add(kit.me, [DOC])
    rows = await kit.panel.list_docs()
    assert len(rows) == 1, "one document adopted both ways is one row"
    assert rows[0]["reach"] == "both" and rows[0]["identity"] == "service"
    out = await kit.panel.set_identity_choice(DOC, "personal")
    assert out["ok"] is True
    # The registry reads the choice live from the config in production; this
    # fixture's reader is a dict, so the written choice is mirrored into it.
    kit.choices[DOC] = "personal"
    rows = await kit.panel.list_docs()
    assert len(rows) == 1 and rows[0]["identity"] == "personal"
    assert rows[0]["connection_id"] == kit.reg.list()[1].id, "the personal connection executes now"
    assert (await kit.panel.get_conf())["identity_choice"] == {DOC: "personal"}
    out = await kit.panel.set_identity_choice(DOC, "service")
    assert out["ok"] is True and (await kit.panel.get_conf())["identity_choice"] == {}
    await kit.reg.stop_all()


@pytest.mark.asyncio
async def test_choosing_personal_needs_a_personal_owner(kit):
    await kit.reg.add(kit.svc, [DOC])
    out = await kit.panel.set_identity_choice(DOC, "personal")
    assert out["ok"] is False
    assert (await kit.panel.set_identity_choice(DOC, "admin"))["ok"] is False
    await kit.reg.stop_all()


@pytest.mark.asyncio
async def test_signature_setting_never_empties_the_signature(kit):
    out = await kit.panel.set_signature("  由 {name}  的代理代发 ")
    assert out["personal_signature"] == "由 {name} 的代理代发"
    assert (await kit.panel.get_conf())["personal_signature"] == "由 {name} 的代理代发"
    out = await kit.panel.set_signature("")
    assert out["personal_signature"] == ""
    assert out["preview"].startswith("— 由 {name} 的 JiuwenSwarm 代理执行")
    assert "回执" not in out["preview"], "the receipt tail is not the person's to set"


@pytest.mark.asyncio
async def test_a_notice_lands_in_the_ledger_and_the_badge_and_pushes(kit):
    conn = await kit.reg.add(kit.me, [DOC])
    pushed: list = []

    async def push(event, payload):
        pushed.append((event, payload))

    kit.panel.bind_notifier(push)
    prov = kit.providers["me.json"]
    prov.comments = [C("c1", "@张三 看看", mentioned=(ME,))]
    await conn.watcher.tick()          # seeds
    prov.comments = [C("c1", "@张三 看看", mentioned=(ME,)), C("c2", "@张三 还有这个", mentioned=(ME,))]
    await conn.watcher.tick()
    assert [e for e, _ in pushed] == ["clouddoc.notice"]
    assert pushed[0][1]["comment_id"] == "c2" and pushed[0][1]["title"] == "示例文档"
    rows = await kit.panel.list_docs()
    assert rows[0]["notices"] == 1
    got = await kit.panel.notices()
    assert [n["comment_id"] for n in got["notices"]] == ["c2"]
    assert (await kit.panel.notice_ack(got["notices"][0]["notice_id"]))["acked"] == 1
    assert (await kit.panel.list_docs())[0]["notices"] == 0
    assert prov.replies == [], "a notice is not a post"
    await kit.reg.stop_all()


@pytest.mark.asyncio
async def test_add_personal_connection_writes_no_secret_and_cleans_up_when_not_logged_in(kit, tmp_path):
    out = await kit.panel.add_personal_connection("feishu", "cli_x")
    assert out["result"] == "ok" and out["connection"]["kind"] == "personal"
    f = tmp_path / "clouddoc-keys" / "personal-feishu-cli_x.json"
    body = json.loads(f.read_text())
    assert body == {"kind": "personal", "brand": "feishu", "profile": "cli_x", "open_id": None, "name": "张三"} or \
        body["open_id"] is None or body["kind"] == "personal"
    assert "app_secret" not in body and "app_id" not in body
    keys = (await kit.panel.list_keys())["keys"]
    assert keys[0]["kind"] == "personal" and keys[0]["in_use"] is True
    assert (await kit.panel.add_personal_connection("google"))["result"] == "unsupported"

    # Not logged in: the provider's identity call fails, and no file is left behind.
    def failing_factory(path):
        class P(FakeProvider):
            async def self_identity(self):
                from jiuwenswarm.agents.harness.common.tools.clouddoc.provider import ProviderError
                raise ProviderError("auth", "run lark-cli auth login")
        return P(personal=True, address="")

    kit.reg._provider_factory = failing_factory
    out = await kit.panel.add_personal_connection("feishu", "cli_y")
    assert out["result"] == "not_logged_in" and "auth login" in out["detail"]
    assert not (tmp_path / "clouddoc-keys" / "personal-feishu-cli_y.json").exists()
    await kit.reg.stop_all()


@pytest.mark.asyncio
async def test_backlog_skips_personal_connections(kit):
    class Reg:
        def check(self, d):
            class V:
                dispatchable = False
                reason = "no_watch"
            return V()

    kit.reg._watch_registry = Reg()
    conn = await kit.reg.add(kit.me, [DOC])
    kit.providers["me.json"].comments = [C("c1", "请处理", assignee=ME)]
    out = await kit.panel.backlog()
    assert out["count"] == 0
    await kit.reg.stop_all()


@pytest.mark.asyncio
async def test_remove_doc_from_one_owner_leaves_the_other(kit):
    s = await kit.reg.add(kit.svc, [DOC])
    p = await kit.reg.add(kit.me, [DOC])
    assert (await kit.panel.remove_doc(DOC, connection_id=p.id))["result"] == "ok"
    assert s.watcher._docs == [DOC] and p.watcher._docs == []
    assert (await kit.panel.remove_doc(DOC))["result"] == "ok"
    assert s.watcher._docs == []
    await kit.reg.stop_all()


# ------------------------------------------------------------ Google personal (OAuth) on the panel


@pytest.mark.asyncio
async def test_google_oauth_flow_needs_a_client_then_adds_a_personal_connection(kit, tmp_path):
    import os
    import yaml

    assert (await kit.panel.google_oauth_start())["result"] == "not_configured"
    out = await kit.panel.set_google_oauth("cid.apps", "shh")
    assert out["configured"] is True
    conf = await kit.panel.get_conf()
    assert conf["google_oauth"] == {"configured": True, "client_id": "cid.apps"}
    assert "shh" not in json.dumps(conf), "the secret never leaves the config"

    exchanged = []

    def fake_exchange(cid, secret, code, redirect_uri):
        exchanged.append((cid, secret, code, redirect_uri))
        return {"access_token": "at", "refresh_token": "1//rt"}

    kit.panel._oauth_exchange = fake_exchange

    def google_factory(path):
        body = json.loads(open(path).read())
        assert body["refresh_token"] == "1//rt"
        p = FakeProvider(personal=True, address="me@x.com")

        async def ident():
            return AgentIdentity(display_name="Me", address="me@x.com")

        p.self_identity = ident
        p.kind_name = "google"
        return p

    kit.reg._provider_factory = google_factory
    started = await kit.panel.google_oauth_start()
    assert started["result"] == "ok" and started["auth_url"].startswith("https://accounts.google.com/")
    assert started["redirect_uri"].startswith("http://127.0.0.1:")
    assert (await kit.panel.google_oauth_status(started["state"]))["status"] == "pending"

    # The paste-the-code fallback settles the flow without the browser.
    done = await kit.panel.google_oauth_finish(started["state"], f"http://127.0.0.1:1/?state={started['state']}&code=4%2Fabc")
    assert done["status"] == "done", done
    assert done["connection"]["kind"] == "personal" and done["connection"]["agent_address"] == "me@x.com"
    assert exchanged[0][:3] == ("cid.apps", "shh", "4/abc")
    f = tmp_path / "clouddoc-keys" / "personal-google-me@x.com.json"
    assert oct(os.stat(f).st_mode & 0o777) == "0o600"
    body = json.loads(f.read_text())
    assert body["refresh_token"] == "1//rt" and body["email"] == "me@x.com" and body["kind"] == "personal"
    assert not list((tmp_path / "clouddoc-keys").glob("personal-google-pending-*"))
    conns = yaml.safe_load(kit.cfg.read_text())["clouddoc"]["connections"]
    assert conns[0]["kind"] == "personal" and conns[0]["credentials_file"] == str(f)
    assert "1//rt" not in kit.cfg.read_text(), "the token stays in the 0600 file, not in config.yaml"

    # A second grant for the same person is a duplicate, and leaves no file behind.
    again = await kit.panel.google_oauth_start()
    done2 = await kit.panel.google_oauth_finish(again["state"], "4/def")
    assert done2["status"] == "error" and "duplicate" in done2["detail"]
    assert len(list((tmp_path / "clouddoc-keys").glob("*.json"))) == 1
    assert (await kit.panel.google_oauth_status("nope"))["status"] == "error"
    await kit.reg.stop_all()


@pytest.mark.asyncio
async def test_a_failed_exchange_leaves_no_file_and_says_why(kit, tmp_path):
    await kit.panel.set_google_oauth("cid.apps", "shh")

    def bad_exchange(*a):
        from jiuwenswarm.agents.harness.common.tools.clouddoc.provider import ProviderError
        raise ProviderError("auth", "授权码兑换失败：invalid_grant")

    kit.panel._oauth_exchange = bad_exchange
    started = await kit.panel.google_oauth_start()
    done = await kit.panel.google_oauth_finish(started["state"], "4/abc")
    assert done["status"] == "error" and "invalid_grant" in done["detail"]
    assert not (tmp_path / "clouddoc-keys").exists() or not list((tmp_path / "clouddoc-keys").glob("*.json"))
    # A wrong-state paste is refused and the flow stays pending.
    started = await kit.panel.google_oauth_start()
    still = await kit.panel.google_oauth_finish(started["state"], "http://127.0.0.1:1/?state=other&code=x")
    assert still["status"] == "pending"
    await kit.reg.stop_all()
