"""The Docs panel service layer -- panel.py and connections.py.

The panel holds no state, so everything here tests **whether the composition is
right**: whether an action lands in all three places -- the registry's memory, the
state file, config.yaml -- and whether classification agrees with the admission check.
"""

import asyncio
import json
from dataclasses import replace

import pytest

from jiuwenswarm.common.config import dump_yaml_round_trip, load_yaml_round_trip
import yaml

from jiuwenswarm.agents.harness.common.tools.clouddoc.provider import (
    AgentIdentity,
    DocComment,
    DocCapabilities,
    DocSummary,
    ProviderError,
)
from jiuwenswarm.gateway.clouddoc.comment_watcher import WatcherConfig
from jiuwenswarm.gateway.clouddoc.connections import (
    CloudDocConnections,
    read_connection_specs,
)
from jiuwenswarm.gateway.clouddoc.cursor_store import CloudDocStore
from jiuwenswarm.gateway.clouddoc.panel import CloudDocPanel
from jiuwenswarm.gateway.clouddoc.triggers import TriggerConfig

SA = "co-scribe@x.iam.gserviceaccount.com"
SA2 = "scribe-b@y.iam.gserviceaccount.com"
DOC = "1AAAABBBBCCCCDDDDEEEEFFFFGGGGHHHHIIIIJJJJKKK"
DOC2 = "2BBBBCCCCDDDDEEEEFFFFGGGGHHHHIIIIJJJJKKKLLL"


class Clock:
    def __init__(self):
        self.t = 1_000.0

    def __call__(self):
        return self.t


def _comment(cid: str, body: str, *, assignee: str = "", resolved: bool = False):
    """One comment as the provider would report it, for the backlog view."""
    return DocComment(
        comment_id=cid, author_is_self=False, author_display_name="someone",
        created_time="2026-01-01T00:00:00Z", content=body, quoted_text="",
        resolved=resolved, assignee_address=assignee or None,
    )


class PanelFakeProvider:
    """The panel uses a narrow slice of a provider: parse, capabilities, title,
    self_identity, doc_url.

    The address is derived from the credentials filename, since the registry builds a
    provider per key -- in these tests one filename is one identity.
    """

    def doc_url(self, doc_id, kind=""):
        # A link is the platform's to build, so the panel asks rather than templating
        # one. Present here because a provider missing it took the panel down.
        return f"https://example.test/{kind or 'doc'}/{doc_id}"

    def __init__(self, credentials_file: str):
        self.credentials_file = credentials_file
        self.address = {"k1.json": SA, "k2.json": SA2}.get(
            credentials_file.rsplit("/", 1)[-1], f"{credentials_file.rsplit('/', 1)[-1]}@fake"
        )
        self.caps = DocCapabilities(
            can_read=True, can_edit=True, can_comment=True, can_resolve=True,
            has_revision_control=True, max_quote_chars=418,
        )
        self.doc_title = "示例文档"
        self.cap_calls = 0
        self.accessible: list = []          # 共享给这个账号的文档

    @property
    def kind(self):
        return "fake"

    async def list_shared_unsupported(self):
        return list(getattr(self, "unsupported", []))

    async def list_accessible_documents(self):
        return list(self.accessible)

    def parse_doc_ref(self, url_or_id):
        if "docs.google.com" in url_or_id:
            return url_or_id.split("/d/")[1].split("/")[0]
        if len(url_or_id) > 20:
            return url_or_id
        raise ProviderError("invalid", f"无法解析 {url_or_id!r}")

    async def self_identity(self):
        return AgentIdentity(display_name=self.address, address=self.address)

    async def capabilities(self, doc_ref):
        self.cap_calls += 1
        if isinstance(self.caps, Exception):
            raise self.caps
        return self.caps

    async def title(self, doc_ref):
        return self.doc_title

    async def list_comments(self, doc_ref, *, include_resolved=False):
        # The backlog view reads assignments; nothing else in the panel does, so the
        # list stays empty unless a test sets it.
        return list(getattr(self, "comments", []))


@pytest.fixture
def kit(tmp_path):
    """A panel already holding one connection (k1.json to a service account). The key file
    genuinely exists under tmp."""
    store = CloudDocStore(tmp_path / "state.json", now_fn=Clock())
    providers: dict[str, PanelFakeProvider] = {}

    def factory(path: str) -> PanelFakeProvider:
        providers[path.rsplit("/", 1)[-1]] = p = PanelFakeProvider(path)
        return p

    async def dispatch(doc_id, comment_id, metadata):
        return "ok"

    reg = CloudDocConnections(
        store=store,
        dispatcher=dispatch,
        watcher_cfg=WatcherConfig(),
        base_trigger_cfg=TriggerConfig(sa_address=""),
        provider_factory=factory,
        now_fn=Clock(),
    )
    for name in ("k1.json", "k2.json"):
        (tmp_path / name).write_text(json.dumps({"client_email": name}))
    cfg = tmp_path / "config.yaml"
    cfg.write_text("clouddoc:\n  enabled: true\n  documents: []\n")
    panel = CloudDocPanel(reg, config_path=cfg)

    class Kit:
        pass

    k = Kit()
    k.panel, k.reg, k.store, k.cfg, k.tmp = panel, reg, store, cfg, tmp_path
    k.providers = providers
    return k


async def _with_conn1(k):
    await k.reg.add(str(k.tmp / "k1.json"))
    return k.providers["k1.json"]


def _yaml_connections(cfg):
    return (yaml.safe_load(cfg.read_text()).get("clouddoc") or {}).get("connections")


# ------------------------------------------------------------------ document actions


@pytest.mark.asyncio
async def test_add_doc_lands_in_all_three_places(kit):
    """A successful add lands in all three: the watcher's memory, config.yaml, and the
    title cache."""
    await _with_conn1(kit)
    out = await kit.panel.add_doc(f"https://docs.google.com/document/d/{DOC}/edit?tab=t.0")
    assert out["result"] == "ok"
    assert DOC in kit.reg.list()[0].watcher._docs
    assert _yaml_connections(kit.cfg)[0]["documents"] == [DOC]
    rows = await kit.panel.list_docs()
    assert rows[0]["title"] == "示例文档"
    assert rows[0]["status"] == "ok"
    assert rows[0]["connection_id"] == kit.reg.list()[0].id


@pytest.mark.asyncio
async def test_comment_only_doc_is_refused_not_added(kit):
    """Comment-only access is refused, the same verdict admission reaches."""
    prov = await _with_conn1(kit)
    prov.caps = replace(prov.caps, can_edit=False, has_revision_control=False)
    out = await kit.panel.add_doc(DOC)
    assert out["result"] == "comment_only"
    assert kit.reg.all_docs() == []


@pytest.mark.asyncio
async def test_unshared_and_transient_are_distinguished(kit):
    prov = await _with_conn1(kit)
    prov.caps = ProviderError("forbidden", "not shared")
    assert (await kit.panel.add_doc(DOC))["result"] == "not_shared"
    prov.caps = ProviderError("rate_limited", "429")
    assert (await kit.panel.add_doc(DOC))["result"] == "unknown"


@pytest.mark.asyncio
async def test_remove_doc_clears_memory_config_and_state(kit):
    await _with_conn1(kit)
    await kit.panel.add_doc(DOC)
    await kit.store.mark_triggered(DOC, ["clouddoc:x:y:-"])
    assert (await kit.panel.remove_doc(DOC))["result"] == "ok"
    assert kit.reg.all_docs() == []
    assert _yaml_connections(kit.cfg)[0]["documents"] == []
    assert not (await kit.store.doc_health(DOC))["failed"]


@pytest.mark.asyncio
async def test_update_doc_thaws_a_fixed_document(kit):
    await _with_conn1(kit)
    await kit.panel.add_doc(DOC)
    await kit.store.note_permanent_failure(DOC, "comment_only_access")
    assert (await kit.panel.list_docs())[0]["status"] == "comment_only"
    assert (await kit.panel.update_doc(DOC))["result"] == "ok"
    assert (await kit.panel.list_docs())[0]["status"] == "ok"
    assert not await kit.store.is_frozen(DOC, 0.0)


@pytest.mark.asyncio
async def test_update_doc_does_not_thaw_on_transient_error(kit):
    prov = await _with_conn1(kit)
    await kit.panel.add_doc(DOC)
    await kit.store.note_permanent_failure(DOC, "comment_only_access")
    prov.caps = ProviderError("rate_limited", "429")
    assert (await kit.panel.update_doc(DOC))["result"] == "unknown"
    assert await kit.store.is_frozen(DOC, 0.0), "瞬态错误期间判决必须保持"


@pytest.mark.asyncio
async def test_list_docs_burns_no_quota(kit):
    prov = await _with_conn1(kit)
    await kit.panel.add_doc(DOC)
    before = prov.cap_calls
    for _ in range(5):
        await kit.panel.list_docs()
        await kit.panel.get_conf()
    assert prov.cap_calls == before, "list_docs/get_conf 打了实时 API"


@pytest.mark.asyncio
async def test_config_comments_survive_persistence(kit):
    """A round-trip write must preserve the comments in a user's config -- those are their
    own operational notes."""
    await _with_conn1(kit)
    kit.cfg.write_text(
        "clouddoc:\n"
        "  enabled: true\n"
        "  # 我的备忘：这里只放生产文档\n"
        "  documents: []\n"
    )
    await kit.panel.add_doc(DOC)
    assert "我的备忘" in kit.cfg.read_text()


# ------------------------------------------------------------------ connection actions


@pytest.mark.asyncio
async def test_add_connection_persists_and_hot_starts(kit):
    """Adding a connection lands in the registry and config.yaml together, and the watcher
    starts immediately."""
    await _with_conn1(kit)
    out = await kit.panel.add_connection(credentials_path=str(kit.tmp / "k2.json"))
    assert out["result"] == "ok"
    assert out["connection"]["agent_address"] == SA2
    assert out["connection"]["health"] == "idle"
    assert len(kit.reg.list()) == 2
    conns = _yaml_connections(kit.cfg)
    assert [c["credentials_file"].rsplit("/", 1)[-1] for c in conns] == ["k1.json", "k2.json"]
    # Hot start: the watcher task is already running
    assert kit.reg.list()[1].watcher._task is not None
    await kit.reg.stop_all()


@pytest.mark.asyncio
async def test_duplicate_address_is_refused(kit):
    """The same account twice means two watchers polling under one identity and every
    mention answered twice. Refused."""
    await _with_conn1(kit)
    out = await kit.panel.add_connection(credentials_path=str(kit.tmp / "k1.json"))
    assert out["result"] == "duplicate"
    assert len(kit.reg.list()) == 1


@pytest.mark.asyncio
async def test_missing_or_broken_key_is_refused(kit):
    await _with_conn1(kit)
    out = await kit.panel.add_connection(credentials_path=str(kit.tmp / "nope.json"))
    assert out["result"] == "invalid_key"
    out = await kit.panel.add_connection(credentials_json="not json at all")
    assert out["result"] == "invalid_key"
    out = await kit.panel.add_connection(credentials_json='{"no_email": 1}')
    assert out["result"] == "invalid_key"
    assert len(kit.reg.list()) == 1


@pytest.mark.asyncio
async def test_uploaded_key_lands_with_0600(kit):
    """An uploaded private key is written to its own file with owner-only permissions, and
    never into config.yaml."""
    await _with_conn1(kit)
    body = json.dumps({"client_email": "k2.json"})
    out = await kit.panel.add_connection(credentials_json=body, filename="team-b")
    assert out["result"] == "ok"
    path = kit.tmp / "clouddoc-keys" / "team-b.json"
    assert path.read_text() == body
    assert oct(path.stat().st_mode & 0o777) == "0o600"
    assert body not in kit.cfg.read_text(), "私钥内容绝不能进 config.yaml"
    await kit.reg.stop_all()


@pytest.mark.asyncio
async def test_remove_connection_stops_watcher_and_persists(kit):
    await _with_conn1(kit)
    out = await kit.panel.add_connection(credentials_path=str(kit.tmp / "k2.json"))
    conn_id = out["connection"]["id"]
    await kit.panel.add_doc(DOC, connection_id=conn_id)

    removed = await kit.panel.remove_connection(conn_id)
    assert removed["result"] == "ok"
    assert len(kit.reg.list()) == 1
    assert kit.reg.all_docs() == []
    assert len(_yaml_connections(kit.cfg)) == 1
    # Its documents' state is collected
    assert not (await kit.store.doc_health(DOC))["failed"]


@pytest.mark.asyncio
async def test_doc_is_unique_across_connections(kit):
    """A document belongs to one connection. State and sessions are keyed by doc_id, so two
    identities on one document overwrite each other and every mention is answered
    twice."""
    await _with_conn1(kit)
    out2 = await kit.panel.add_connection(credentials_path=str(kit.tmp / "k2.json"))
    await kit.panel.add_doc(DOC)                       # 归第一个连接
    dup = await kit.panel.add_doc(DOC, connection_id=out2["connection"]["id"])
    assert dup["result"] == "exists"
    assert dup["connection_id"] == kit.reg.list()[0].id
    await kit.reg.stop_all()


# ------------------------------------------------------------------ config reading


def test_legacy_single_connection_config_still_reads():
    """The old top-level credentials_file and documents form folds into a one-element list,
    so a deployed config needs no edit."""
    legacy = {"credentials_file": "/k.json", "documents": ["a", "b"]}
    assert read_connection_specs(legacy) == [
        {"credentials_file": "/k.json", "documents": ["a", "b"]}
    ]
    new = {"connections": [{"credentials_file": "/k2.json", "documents": []}]}
    assert read_connection_specs(new) == [{"credentials_file": "/k2.json", "documents": []}]
    assert read_connection_specs({}) == []


@pytest.mark.asyncio
async def test_persist_upgrades_legacy_keys(kit):
    """The panel's first write upgrades the old keys into a connections list, leaving no
    second source of truth."""
    await _with_conn1(kit)
    kit.cfg.write_text(
        "clouddoc:\n  enabled: true\n  credentials_file: /old.json\n  documents: [x]\n"
    )
    await kit.panel.add_doc(DOC)
    data = yaml.safe_load(kit.cfg.read_text())["clouddoc"]
    assert "connections" in data
    assert "credentials_file" not in data
    assert "documents" not in data


# ------------------------------------------------------------------ connection health


@pytest.mark.asyncio
async def test_connection_health_aggregates_document_facts(kit):
    """A connection's light must be driven by facts. Four states: idle -- no documents is
    not health -- then ok, down and attention."""
    await _with_conn1(kit)
    conf = await kit.panel.get_conf()
    assert conf["connections"][0]["health"] == "idle"

    await kit.panel.add_doc(DOC)
    assert (await kit.panel.get_conf())["connections"][0]["health"] == "ok"

    await kit.store.note_permanent_failure(DOC, "comment_only_access")
    assert (await kit.panel.get_conf())["connections"][0]["health"] == "down"

    await kit.panel.add_doc(DOC2)   # 一好一坏
    assert (await kit.panel.get_conf())["connections"][0]["health"] == "attention"


# ------------------------------------------------------------------ cross-connection uniqueness


@pytest.mark.asyncio
async def test_startup_also_enforces_document_uniqueness(kit):
    """Uniqueness is enforced in **the registry**, not the panel.

    panel.add_doc is one of two entrances; the other is reading config at startup. A
    hand-edited or copied config that puts one document under two connections gets two
    watchers on it -- every mention answered twice, and with state keyed by doc_id the
    two overwrite each other. Putting the guard only on the UI path locks one door of
    two.
    """
    await kit.reg.add(str(kit.tmp / "k1.json"), [DOC, DOC2])
    await kit.reg.add(str(kit.tmp / "k2.json"), [DOC, "3CCCDDDDEEEEFFFFGGGGHHHHIIIIJJJJKKKLLLMMM"])

    first, second = kit.reg.list()
    assert DOC in first.watcher._docs
    assert DOC not in second.watcher._docs, "重复文档必须被第二个连接丢弃"
    assert "3CCCDDDDEEEEFFFFGGGGHHHHIIIIJJJJKKKLLLMMM" in second.watcher._docs, "非重复的不受影响"
    assert sorted(kit.reg.all_docs()) == sorted({DOC, DOC2, "3CCCDDDDEEEEFFFFGGGGHHHHIIIIJJJJKKKLLLMMM"})


@pytest.mark.asyncio
async def test_starting_up_does_not_delete_the_other_connections_state(kit):
    """State collection is absolute, so only the layer that knows every document may ask
    for it.

    ``gc`` keeps exactly the documents it is handed and deletes the rest. A watcher knows
    only its own, and calling it from there deleted every other connection's dedup keys,
    sessions and seeded flag on every start. The documents then
    re-seeded, marking everything currently outstanding as handled -- so a comment
    written between the last poll and a restart was swallowed without a trace.

    It read as ordinary housekeeping in the log: two connections, two lines of "collected
    1 document", each one deleting the other's.
    """
    await kit.reg.add(str(kit.tmp / "k2.json"), [DOC2])
    await kit.reg.add(str(kit.tmp / "k3.json"), ["3CCCDDDDEEEEFFFFGGGGHHHHIIIIJJJJKKKLLLMMM"])
    store = kit.reg.store
    await store.mark_triggered(DOC2, ["处理过的评论"])
    await store.mark_triggered("3CCCDDDDEEEEFFFFGGGGHHHHIIIIJJJJKKKLLLMMM", ["clouddoc:3CCCDDDDEEEEFFFFGGGGHHHHIIIIJJJJKKKLLLMMM:c9:-"])
    await store.mark_triggered("已从配置里移除的文档", ["旧键"])

    await kit.reg.start_all()

    snap = await store.snapshot()
    assert snap.get(DOC2, {}).get("triggered_ids"), "第二个连接的去重键被删了"
    assert (snap.get("3CCCDDDDEEEEFFFFGGGGHHHHIIIIJJJJKKKLLLMMM", {}).get("triggered_ids")), \
        "第三个连接的去重键被删了"
    assert "已从配置里移除的文档" not in snap, "不再纳管的文档应当被回收"


@pytest.mark.asyncio
async def test_a_document_added_before_startup_survives_startup(kit):
    """The document list has one owner: the watcher.

    ``start`` used to take the list and overwrite ``_docs`` with it, so anything the
    panel had added beforehand was dropped the moment the gateway started polling --
    and ``all_docs`` reported one source or the other depending on a flag.
    """
    await _with_conn1(kit)
    await kit.panel.add_doc(DOC)
    assert DOC in kit.reg.all_docs()

    await kit.reg.start_all()
    assert DOC in kit.reg.all_docs(), "启动把启动前加的文档丢了"


@pytest.mark.asyncio
async def test_sharing_a_document_is_what_puts_it_under_management(kit):
    """Sharing is the decision. The panel does not ask for a second one.

    What makes that safe is the trigger model: an adopted document costs a poll and
    nothing else until somebody assigns a comment to the agent. So adoption buys
    visibility, and the part that spends tokens stays a separate deliberate act.
    """
    from jiuwenswarm.agents.harness.common.tools.clouddoc.provider import DocSummary

    prov = await _with_conn1(kit)
    prov.accessible = [
        DocSummary(doc_id=DOC, title="已经在盯的", can_edit=True),
        DocSummary(doc_id=DOC2, title="刚共享进来的", can_edit=True),
    ]
    await kit.panel.add_doc(DOC)

    out = await kit.panel.sync_shared_docs()
    assert [d["doc_id"] for d in out["adopted"]] == [DOC2], "新共享的没被自动纳管"
    assert DOC2 in kit.reg.all_docs()
    # Persisted, or it lasts until the next restart and the user re-shares in confusion.
    assert DOC2 in _yaml_connections(kit.cfg)[0]["documents"]

    again = await kit.panel.sync_shared_docs()
    assert again["adopted"] == [], "第二次不该重复纳管"


@pytest.mark.asyncio
async def test_a_comment_only_share_is_reported_not_adopted(kit):
    """Admission refuses comment-only documents, so adopting one buys a broken entry.

    Reporting it is worth more than either adopting or hiding: the person made a
    specific mistake in the share dialog, and it has a specific fix.
    """
    from jiuwenswarm.agents.harness.common.tools.clouddoc.provider import DocSummary

    prov = await _with_conn1(kit)
    prov.accessible = [DocSummary(doc_id=DOC2, title="只给了评论权的", can_edit=False)]

    out = await kit.panel.sync_shared_docs()
    assert out["adopted"] == []
    assert DOC2 not in kit.reg.all_docs(), "仅评论权的被纳管了，准入随后必然拒绝它"
    assert [d["doc_id"] for d in out["needs_editor"]] == [DOC2], "藏起来只会让人以为共享没生效"


@pytest.mark.asyncio
async def test_adoption_failing_does_not_break_the_panel(kit):
    """It runs on every panel open. A provider that cannot list must not take it down."""
    from jiuwenswarm.agents.harness.common.tools.clouddoc.provider import ProviderError

    async def boom():
        raise ProviderError("forbidden", "Drive API has not been enabled")

    prov = await _with_conn1(kit)
    prov.list_accessible_documents = boom
    out = await kit.panel.sync_shared_docs()
    assert out["result"] == "unknown" and out["adopted"] == [] and out["needs_editor"] == []


@pytest.mark.asyncio
async def test_persist_goes_through_the_cross_process_mutex(kit, monkeypatch):
    """Writing config must go through update_config rather than a load and dump of its own.

    A single write is atomic, through a temporary file and a rename, but **the
    read-modify-write around it is not**: while the gateway saves a document list the
    agentserver may be writing permissions config, each process reads the old version
    and writes the whole file back, and whichever lands second erases the other. The
    product's update_config holds a threading lock and a portalocker file lock, built
    for exactly this pair.
    """
    from jiuwenswarm.gateway.clouddoc import panel as panel_mod

    seen: list[str] = []

    def _spy(mutator, **kw):
        """Record the call and apply the mutator **to the test's own file**.

        It must not delegate to the real ``update_config``: that function resolves the
        global config path itself, so calling it here rewrites the developer's live
        ``~/.jiuwenswarm/config/config.yaml`` with this test's fixture connection. That
        happened -- monkeypatching ``panel_mod.CONFIG_YAML_PATH`` only changes which
        branch the panel takes, not where update_config writes.

        The claim under test is "the panel goes through update_config", which a spy
        proves. Whether update_config itself locks correctly is the product's own
        contract, tested elsewhere.
        """
        seen.append("locked")
        data = load_yaml_round_trip(kit.cfg)
        dump_yaml_round_trip(kit.cfg, mutator(data if isinstance(data, dict) else {}))

    monkeypatch.setattr(panel_mod, "update_config", _spy)
    # Make the panel believe it is writing the global config path
    monkeypatch.setattr(panel_mod, "CONFIG_YAML_PATH", kit.cfg)
    kit.panel._config_path = kit.cfg

    await kit.reg.add(str(kit.tmp / "k1.json"))
    await kit.panel.add_doc(DOC)
    assert seen == ["locked"], "写配置绕过了跨进程互斥"


# ------------------------------------------------------------------ wiring integrity


def test_gateway_wiring_has_no_unbound_names():
    """The gateway's startup and shutdown paths must reference no unbound names.

    What happened: the multi-connection refactor renamed ``clouddoc_watcher`` to
    ``clouddoc_connections`` and missed one spot in the shutdown block --
    ``await clouddoc_watcher[0].stop()``. Being on the **shutdown path**, it never fires
    during normal operation and raises NameError only as the process exits, by which
    point nobody is usually reading the log.

    A missed rename of this kind cannot be caught by running tests, since the path is
    not covered; only reading the structure finds it.
    """
    import ast
    import pathlib

    src = pathlib.Path(
        __file__
    ).parents[3].joinpath("jiuwenswarm/gateway/app_gateway.py").read_text()
    tree = ast.parse(src)

    checked = 0
    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        bound = {
            t.id
            for n in ast.walk(func)
            if isinstance(n, (ast.Assign, ast.AnnAssign, ast.For, ast.AsyncFor))
            for t in ([n.target] if hasattr(n, "target") and n.target else getattr(n, "targets", []))
            if isinstance(t, ast.Name)
        }
        bound |= {a.arg for a in func.args.args + func.args.kwonlyargs}
        bound |= {
            n.name or n.asname
            for stmt in ast.walk(func)
            if isinstance(stmt, (ast.Import, ast.ImportFrom))
            for n in stmt.names
        }
        used = {
            n.id for n in ast.walk(func)
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
            and n.id.startswith("clouddoc")
        }
        if not used:
            continue
        checked += 1
        assert used <= bound, (
            f"{func.name} 引用了未绑定的名字 {sorted(used - bound)}——"
            "多半是一次没改干净的重命名，且只会在该分支被执行时才炸"
        )
    assert checked, "没有找到引用 clouddoc 名字的函数，这条检查需要重写"


# ------------------------------------------------------- getting off the ground


@pytest.mark.asyncio
async def test_adding_the_first_connection_turns_the_feature_on(kit):
    """The panel is the only switch. Nothing in the UI sets ``clouddoc.enabled``.

    Without this the whole configuration flow works right up until the next restart,
    and then goes quiet: the key is in config.yaml, the documents are listed, and the
    startup path skips all of it because the feature reads as off.
    """
    kit.cfg.write_text("clouddoc:\n  enabled: false\n")
    await _with_conn1(kit)
    await kit.panel.add_connection(credentials_path=str(kit.tmp / "k2.json"))

    section = yaml.safe_load(kit.cfg.read_text())["clouddoc"]
    assert section["enabled"] is True, "加了连接却没开启功能，重启后整套配置静默失效"


@pytest.mark.asyncio
async def test_a_registry_configured_off_answers_the_panel_but_does_not_poll(tmp_path):
    """Off must mean "do not poll", not "do not answer" -- those got conflated, and the
    conflation is what made a fresh install impossible to configure from the UI.

    The panel still has to work, because adding a connection is how it gets turned on.
    """
    store = CloudDocStore(tmp_path / "state.json", now_fn=Clock())
    (tmp_path / "k1.json").write_text(json.dumps({"client_email": "k1.json"}))

    async def dispatch(doc_id, comment_id, metadata):
        return "ok"

    reg = CloudDocConnections(
        store=store, dispatcher=dispatch, watcher_cfg=WatcherConfig(),
        base_trigger_cfg=TriggerConfig(sa_address=""),
        provider_factory=lambda p: PanelFakeProvider(p), now_fn=Clock(),
        enabled=False,
    )
    conn = await reg.add(str(tmp_path / "k1.json"), [DOC])
    await reg.start_all()
    assert conn.watcher._task is None, "功能已关闭却仍在轮询"

    cfg = tmp_path / "config.yaml"
    cfg.write_text("clouddoc:\n  enabled: false\n")
    panel = CloudDocPanel(reg, config_path=cfg)
    out = await panel.get_conf()
    assert len(out["connections"]) == 1, "关闭状态下面板答不出连接，就没法从界面开启"


@pytest.mark.asyncio
async def test_sync_reports_shared_but_unsupported_files(kit):
    """A shared spreadsheet must not vanish: the user cannot tell "unsupported" apart
    from "the share failed" unless the panel says so."""
    prov = await _with_conn1(kit)
    prov.unsupported = [{"title": "Budget 2026", "kind": "spreadsheet"}]
    out = await kit.panel.sync_shared_docs()
    assert out["unsupported"] == [{"title": "Budget 2026", "kind": "spreadsheet"}]


@pytest.mark.asyncio
async def test_unsupported_listing_failure_loses_the_notice_not_the_panel(kit):
    prov = await _with_conn1(kit)

    async def boom():
        raise RuntimeError("discovery down")
    prov.list_shared_unsupported = boom
    out = await kit.panel.sync_shared_docs()
    assert out["result"] == "ok"
    assert out["unsupported"] == []


@pytest.mark.asyncio
async def test_list_keys_reports_files_and_usage(kit):
    """Only files under clouddoc-keys/ are listed -- a path-mode connection pointing
    elsewhere is not a stored key. A stored key referenced by a connection is in_use."""
    keys = kit.cfg.parent / "clouddoc-keys"
    keys.mkdir(exist_ok=True)
    (keys / "old.json").write_text('{"client_email": "a@x.iam"}')
    (keys / "active.json").write_text('{"client_email": "b@x.iam"}')
    await kit.reg.add(str(keys / "active.json"))
    out = await kit.panel.list_keys()
    by_name = {k["filename"]: k for k in out["keys"]}
    assert by_name["old.json"]["client_email"] == "a@x.iam"
    assert by_name["old.json"]["in_use"] is False
    assert by_name["active.json"]["in_use"] is True


@pytest.mark.asyncio
async def test_delete_key_refuses_in_use_and_path_tricks(kit):
    keys = kit.cfg.parent / "clouddoc-keys"
    keys.mkdir(exist_ok=True)
    (keys / "spare.json").write_text("{}")
    (keys / "active.json").write_text('{"client_email": "b@x.iam"}')
    await kit.reg.add(str(keys / "active.json"))
    assert (await kit.panel.delete_key("active.json"))["result"] == "in_use"
    # A separator anywhere is refused outright -- otherwise this is arbitrary delete.
    assert (await kit.panel.delete_key("../config.yaml"))["result"] == "bad_name"
    assert (await kit.panel.delete_key("a/b.json"))["result"] == "bad_name"
    out = await kit.panel.delete_key("spare.json")
    assert out["result"] == "ok"
    assert not (keys / "spare.json").exists()
    assert (keys / "active.json").exists()


# ------------------------------------------------- periodic discovery of shared docs


class _Ticker:
    """A sleep that yields control, counts rounds, and stops the loop after N of them.

    The loop under test is infinite by design, so the test ends it the way the gateway
    does -- by cancelling -- rather than by giving the loop an exit condition it would
    not have in production.
    """

    def __init__(self, rounds: int) -> None:
        self.rounds = rounds
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)
        if len(self.calls) > self.rounds:
            raise asyncio.CancelledError
        await asyncio.sleep(0)


async def test_discovery_adopts_without_the_panel_being_opened(kit):
    """The point of the loop: a document shared with the account is adopted with nobody
    opening the Docs panel, which is what a chat-only deployment needs."""
    from jiuwenswarm.gateway.clouddoc.panel import discover_shared_periodically

    prov = await _with_conn1(kit)
    prov.accessible = [DocSummary(doc_id=DOC, title="共享进来的", can_edit=True)]
    assert kit.reg.all_docs() == []

    tick = _Ticker(rounds=1)
    with pytest.raises(asyncio.CancelledError):
        await discover_shared_periodically(kit.panel, interval_seconds=300, sleep_fn=tick)

    assert DOC in kit.reg.all_docs(), "定期发现应当在无人打开面板时纳管"
    assert _yaml_connections(kit.cfg)[0]["documents"] == [DOC], "纳管须落盘,重启后仍在"


async def test_discovery_leaves_the_tier_to_the_adoption_policy(kit):
    """Adoption is not a grant. With the default policy a discovered document is watched
    and nothing else -- no turn can be dispatched against it until someone grants one."""
    from jiuwenswarm.gateway.clouddoc.panel import discover_shared_periodically

    prov = await _with_conn1(kit)
    prov.accessible = [DocSummary(doc_id=DOC, title="共享进来的", can_edit=True)]

    tick = _Ticker(rounds=1)
    with pytest.raises(asyncio.CancelledError):
        await discover_shared_periodically(kit.panel, interval_seconds=300, sleep_fn=tick)

    registry = kit.reg._watch_registry
    assert registry is None or registry.get(DOC) is None, "默认策略下发现不得自动签发档位"


async def test_discovery_refuses_comment_only_like_admission_does(kit):
    """A comment-only share is reported, not adopted. Admission would refuse it anyway,
    and an entry that silently never works is worse than saying which document and why."""
    from jiuwenswarm.gateway.clouddoc.panel import discover_shared_periodically

    prov = await _with_conn1(kit)
    prov.accessible = [DocSummary(doc_id=DOC, title="只给了评论权", can_edit=False)]

    tick = _Ticker(rounds=1)
    with pytest.raises(asyncio.CancelledError):
        await discover_shared_periodically(kit.panel, interval_seconds=300, sleep_fn=tick)

    assert kit.reg.all_docs() == [], "仅评论权的文档不得被纳管"


async def test_discovery_survives_a_failing_round(kit):
    """Discovery is a convenience running in the process that also polls comments. A
    provider that fails must cost one round, not the loop."""
    from jiuwenswarm.gateway.clouddoc.panel import discover_shared_periodically

    prov = await _with_conn1(kit)

    calls = {"n": 0}

    async def flaky():
        calls["n"] += 1
        if calls["n"] == 1:
            raise ProviderError("unknown", "Drive 暂时不可用")
        return [DocSummary(doc_id=DOC, title="第二轮才拿到", can_edit=True)]

    prov.list_accessible_documents = flaky

    tick = _Ticker(rounds=2)
    with pytest.raises(asyncio.CancelledError):
        await discover_shared_periodically(kit.panel, interval_seconds=300, sleep_fn=tick)

    assert calls["n"] == 2, "第一轮失败后循环必须继续"
    assert DOC in kit.reg.all_docs()


async def test_discovery_waits_before_its_first_round(kit):
    """Startup already adopts through the registry; a round fired at t=0 would spend a
    full Drive listing per connection on work just done."""
    from jiuwenswarm.gateway.clouddoc.panel import discover_shared_periodically

    prov = await _with_conn1(kit)
    prov.accessible = [DocSummary(doc_id=DOC, title="共享进来的", can_edit=True)]

    tick = _Ticker(rounds=0)
    with pytest.raises(asyncio.CancelledError):
        await discover_shared_periodically(kit.panel, interval_seconds=300, sleep_fn=tick)

    assert tick.calls == [300], "必须先等一个间隔再发现"
    assert kit.reg.all_docs() == []


@pytest.mark.asyncio
async def test_the_backlog_view_returns_rows_rather_than_raising(kit):
    """It raised on its first line, from the first commit onwards.

    ``self_identity`` answers with an AgentIdentity and the code called ``.lower()`` on
    it, so every request to this view failed with an AttributeError -- and no test ever
    called the method, so nothing said so until someone opened the panel.

    What it lists is work assigned to the agent that the gate will not dispatch: pointing
    at it is the whole purpose, and a view that always errors points at nothing."""
    # The backlog view asks the watch registry which documents are dispatchable, so a
    # test that exercises it has to wire one -- production does this in connections.
    from jiuwenswarm.gateway.clouddoc.watch_registry import WatchRegistry

    kit.reg._watch_registry = WatchRegistry(path=kit.cfg.parent / "watch.json")
    prov = await _with_conn1(kit)
    prov.comments = [
        _comment("c1", "请改这段", assignee=prov.address),
        _comment("c2", "这条是别人的", assignee="someone@else.test"),
    ]
    kit.reg.list()[0].watcher.watch(DOC)
    # Suspended, so nothing is dispatchable and everything assigned to us is backlog.
    kit.panel._registry().issue(DOC, mode="apply_scoped")
    kit.panel._registry().suspend(DOC)

    out = await kit.panel.backlog()
    assert isinstance(out.get("items"), list)
    ids = [row["comment_id"] for row in out["items"]]
    assert "c1" in ids, "指派给本 agent 的未派发工作必须出现在积压里"
    assert "c2" not in ids, "指派给别人的不是我们的积压"


@pytest.mark.asyncio
async def test_a_connection_without_an_address_is_skipped_not_matched(kit):
    """With no address there is nothing to compare an assignee against, and a blank
    would either match every comment or none. Saying nothing beats saying something
    wrong."""
    # The backlog view asks the watch registry which documents are dispatchable, so a
    # test that exercises it has to wire one -- production does this in connections.
    from jiuwenswarm.gateway.clouddoc.watch_registry import WatchRegistry

    kit.reg._watch_registry = WatchRegistry(path=kit.cfg.parent / "watch.json")
    prov = await _with_conn1(kit)
    prov.address = ""
    kit.reg.list()[0].watcher.watch(DOC)
    prov.comments = [_comment("c1", "请改这段", assignee="")]
    kit.panel._registry().issue(DOC, mode="apply_scoped")
    kit.panel._registry().suspend(DOC)
    out = await kit.panel.backlog()
    assert out["items"] == []


@pytest.mark.asyncio
async def test_list_docs_heals_a_missing_title_once(kit):
    """A document adopted before titles were recorded showed its id prefix
    forever; the panel now asks the provider once and caches the answer, the
    same self-heal the kind field already had."""
    prov = await _with_conn1(kit)
    prov.doc_title = ""  # adoption records nothing, the legacy state
    await kit.panel.add_doc(DOC)

    prov.doc_title = "治愈后的标题"
    rows = await kit.panel.list_docs()
    assert next(r for r in rows if r["doc_id"] == DOC)["title"] == "治愈后的标题"

    prov.doc_title = "不应再被读到"
    rows2 = await kit.panel.list_docs()
    assert next(r for r in rows2 if r["doc_id"] == DOC)["title"] == "治愈后的标题", (
        "标题应已缓存,不再询问 provider"
    )


@pytest.mark.asyncio
async def test_set_model_validates_like_cron_and_persists_deployment_wide(kit, monkeypatch):
    """§25.3: the model is wiring, set once for the deployment. The name goes through
    the cron validator so only a key the agentserver can resolve lands in the config,
    and an empty name restores the default."""
    import jiuwenswarm.gateway.cron.models as cron_models

    def fake_validate(raw):
        value = str(raw or "").strip()
        if not value:
            return None
        if value in ("gemma", "Gemma4-26B"):
            return "Gemma4-26B"
        raise ValueError(f"Unknown model {value!r}")

    monkeypatch.setattr(cron_models, "validate_cron_model", fake_validate)

    out = await kit.panel.set_model("gemma")
    assert out == {"ok": True, "model_name": "Gemma4-26B"}, "别名须落成规范名"
    assert load_yaml_round_trip(kit.cfg)["clouddoc"]["model_name"] == "Gemma4-26B"
    assert (await kit.panel.get_conf())["model_name"] == "Gemma4-26B"

    out = await kit.panel.set_model("nope")
    assert out["ok"] is False and "Unknown model" in out["detail"]
    assert load_yaml_round_trip(kit.cfg)["clouddoc"]["model_name"] == "Gemma4-26B", (
        "未知模型不得写入配置"
    )

    out = await kit.panel.set_model("")
    assert out == {"ok": True, "model_name": ""}
    assert (await kit.panel.get_conf())["model_name"] == ""


@pytest.mark.asyncio
async def test_every_connection_takes_the_mention_as_its_summons(kit):
    """§16.14: the mention is a pointer edge and carries no authority, so the
    assignment gate adds no safety. Measured cost of keeping it on Google (2026-09-02):
    a person @-ed twice and read "assign it to me", then silence."""
    conn = await kit.reg.add(str(kit.tmp / "k1.json"))
    assert conn.watcher._tcfg.mention_triggers is True


@pytest.mark.asyncio
async def test_add_connection_accepts_a_feishu_app_key(kit):
    """A Feishu app is an id and a secret, no client_email. The panel used to refuse
    it with "missing client_email", so the only way to connect Feishu was editing
    config.yaml by hand."""
    body = json.dumps({"app_id": "cli_abc123", "app_secret": "s3cr3t", "brand": "feishu"})
    out = await kit.panel.add_connection(credentials_json=body)
    assert out["result"] == "ok", out
    path = kit.tmp / "clouddoc-keys" / "cli_abc123.json"
    assert path.is_file() and json.loads(path.read_text())["app_id"] == "cli_abc123"

    # An id without a secret is not a key either.
    out = await kit.panel.add_connection(credentials_json=json.dumps({"app_id": "cli_x"}))
    assert out["result"] == "invalid_key"


@pytest.mark.asyncio
async def test_list_keys_names_a_feishu_key_by_its_app_id(kit):
    keys = kit.tmp / "clouddoc-keys"
    keys.mkdir()
    (keys / "fs.json").write_text('{"app_id": "cli_abc", "app_secret": "x"}')
    (keys / "g.json").write_text('{"client_email": "a@x.iam"}')
    out = await kit.panel.list_keys()
    by_name = {r["filename"]: r for r in out["keys"]}
    assert by_name["fs.json"]["address"] == "cli_abc"
    assert by_name["fs.json"]["client_email"] == ""
    assert by_name["g.json"]["address"] == "a@x.iam"


@pytest.mark.asyncio
async def test_removing_a_connection_revokes_the_mandates_signed_under_it(kit):
    """The connection is the mandator's authority for that account (D3). Before this,
    removing it only stopped the watcher: the mandate stayed live in the registry
    and a later re-adoption resumed unattended dispatch under an account the owner
    had disconnected. Now each mandate is revoked and journaled with the reason."""
    from jiuwenswarm.gateway.clouddoc.watch_registry import WatchRegistry

    registry = WatchRegistry(path=kit.cfg.parent / "watch.json")
    kit.reg._watch_registry = registry
    await _with_conn1(kit)
    conn = kit.reg.list()[0]
    conn.watcher.watch(DOC)
    registry.issue(DOC, mode="apply_scoped")
    assert registry.get(DOC) is not None

    await kit.panel.remove_connection(conn.id)

    entry = registry.get(DOC)
    assert entry is not None and entry.get("revoked") is True, "值守随连接一起终止，条目留碑"
    assert registry.check(DOC).reason == "no_watch"
    assert not registry.is_write_live(DOC)
    tail = registry.audit_tail(10)
    assert any(r.get("event") == "revoke" and r.get("doc_id") == DOC
               and r.get("reason") == "connection_removed" for r in tail), tail
    assert registry.terminated_by_owner(DOC), "留碑：策略签发不得复活"


@pytest.mark.asyncio
async def test_removing_a_document_revokes_its_mandate(kit):
    """The document-level twin of the connection case: a mandate must not outlive
    the document it was signed for, or a later re-adoption finds it still live."""
    from jiuwenswarm.gateway.clouddoc.watch_registry import WatchRegistry

    registry = WatchRegistry(path=kit.cfg.parent / "watch.json")
    kit.reg._watch_registry = registry
    await _with_conn1(kit)
    out = await kit.panel.add_doc(DOC)
    assert out["result"] == "ok"
    registry.issue(DOC, mode="apply_scoped")
    assert registry.is_write_live(DOC)

    out = await kit.panel.remove_doc(DOC)
    assert out["result"] == "ok"

    entry = registry.get(DOC)
    assert entry is not None and entry.get("revoked") is True
    assert registry.check(DOC).reason == "no_watch"
    assert not registry.is_write_live(DOC), "文档移除后在途写入必须被拦截"
    tail = registry.audit_tail(10)
    assert any(r.get("event") == "revoke" and r.get("doc_id") == DOC
               and r.get("reason") == "document_removed" for r in tail), tail


@pytest.mark.asyncio
async def test_add_doc_applies_the_adoption_policy(kit):
    """The policy tier lands when the document is registered, not at the next
    restart: a link pasted into the panel gets the same treatment as a document
    listed in the config when the connection was built."""
    from jiuwenswarm.gateway.clouddoc.watch_registry import WatchRegistry

    registry = WatchRegistry(path=kit.cfg.parent / "watch.json")
    kit.reg._watch_registry = registry
    kit.reg.auto_watch_policy = "reply_only"
    await _with_conn1(kit)
    out = await kit.panel.add_doc(DOC)
    assert out["result"] == "ok"
    entry = registry.get(DOC)
    assert entry is not None and entry["mode"] == "reply_only"
    assert entry["issued_by"] == "policy"
    assert registry.check(DOC).dispatchable


@pytest.mark.asyncio
async def test_discovery_applies_the_adoption_policy(kit):
    """Same rule on the discovery path: a shared document adopted at run time gets
    the policy tier at adoption."""
    from jiuwenswarm.gateway.clouddoc.watch_registry import WatchRegistry

    registry = WatchRegistry(path=kit.cfg.parent / "watch.json")
    kit.reg._watch_registry = registry
    kit.reg.auto_watch_policy = "reply_only"
    prov = await _with_conn1(kit)
    prov.accessible = [DocSummary(doc_id=DOC, title="共享进来的", can_edit=True)]
    out = await kit.panel.sync_shared_docs()
    assert [r["doc_id"] for r in out["adopted"]] == [DOC]
    entry = registry.get(DOC)
    assert entry is not None and entry["mode"] == "reply_only"


@pytest.mark.asyncio
async def test_re_adding_a_removed_document_does_not_resurrect_its_mandate(kit):
    """Remove leaves a tombstone; the policy on re-adoption must respect it. Only a
    manual grant brings the delegation back."""
    from jiuwenswarm.gateway.clouddoc.watch_registry import WatchRegistry

    registry = WatchRegistry(path=kit.cfg.parent / "watch.json")
    kit.reg._watch_registry = registry
    kit.reg.auto_watch_policy = "reply_only"
    await _with_conn1(kit)
    await kit.panel.add_doc(DOC)
    assert registry.check(DOC).dispatchable
    await kit.panel.remove_doc(DOC)
    await kit.panel.add_doc(DOC)
    assert registry.check(DOC).reason == "no_watch", "策略不得挖出撤销的留碑"
    registry.issue(DOC, mode="reply_only", issued_by="manual")
    assert registry.check(DOC).dispatchable, "手工授权盖过留碑"


# ------------------------------------------------------------ workbench read/write


def _snap(kind, text, rev="r1"):
    from jiuwenswarm.agents.harness.common.tools.clouddoc.provider import DocSnapshot
    return DocSnapshot(doc_id=DOC, kind=kind, revision_id=rev, text=text)


@pytest.mark.asyncio
async def test_workbench_reads_a_registered_document(kit):
    await _with_conn1(kit)
    await kit.panel.add_doc(DOC)
    prov = kit.providers["k1.json"]

    async def read(doc_ref):
        return _snap("markdown", "# 标题\n正文\n")

    prov.read = read
    out = await kit.panel.read_doc(DOC)
    assert out["result"] == "ok" and out["kind"] == "markdown" and out["text"] == "# 标题\n正文\n"
    assert out["revision_id"] == "r1" and out["url"].endswith(DOC)
    assert (await kit.panel.read_doc("doc-not-registered-0000"))["result"] == "not_watched"


@pytest.mark.asyncio
async def test_workbench_save_is_a_whole_file_receipt_by_the_person(kit):
    from jiuwenswarm.agents.harness.common.tools.clouddoc.provider import EditResult
    await _with_conn1(kit)
    await kit.panel.add_doc(DOC)
    prov = kit.providers["k1.json"]
    prov.writes = []

    async def read(doc_ref):
        return _snap("markdown", "old text\n")

    async def edit_batch(doc_ref, edits, *, required_revision_id, window=None, highlight=False):
        prov.writes.append((list(edits), required_revision_id, getattr(prov, "receipt_meta", None)))
        return EditResult("applied", new_revision_id="r2", receipt_id="abc123")

    prov.read = read
    prov.edit_batch = edit_batch
    out = await kit.panel.write_doc(DOC, "new text\n", "r1")
    assert out == {"result": "ok", "revision_id": "r2", "receipt_id": "abc123", "status": "applied"}
    edits, rev, meta = prov.writes[0]
    assert edits == [("old text\n", "new text\n")] and rev == "r1"
    assert meta["executor"] == "person" and meta["source"] == "workbench_save"
    assert prov.receipt_meta is None

    # A stale base revision refuses without writing; an identical text is a no-op.
    assert (await kit.panel.write_doc(DOC, "x", "r0"))["result"] == "conflict"
    assert (await kit.panel.write_doc(DOC, "old text\n", "r1"))["result"] == "unchanged"
    assert len(prov.writes) == 1


@pytest.mark.asyncio
async def test_workbench_save_refuses_formats_with_a_platform_editor(kit):
    await _with_conn1(kit)
    await kit.panel.add_doc(DOC)
    prov = kit.providers["k1.json"]

    async def read(doc_ref):
        return _snap("document", "body")

    prov.read = read
    out = await kit.panel.write_doc(DOC, "changed", "r1")
    assert out["result"] == "refused"


@pytest.mark.asyncio
async def test_unhighlight_clears_the_document_and_stops_the_row_offering_it(kit, monkeypatch):
    """The panel's un-highlight is the manual half of D14, and it had no test.

    Two things have to hold together: the yellow really goes off the document (the
    provider is asked, with the exact strings the batch wrote), and the receipt stops
    advertising a highlight -- the row's label and the button both read ``highlight``,
    so a receipt that kept it True kept offering work already done. A second click is
    then refused rather than writing to the document again.
    """
    from jiuwenswarm.agents.harness.common.tools.clouddoc import deployment
    from jiuwenswarm.agents.harness.common.tools.clouddoc.receipts import ReceiptStore

    ws = kit.tmp / "ws"
    (ws / "config").mkdir(parents=True)
    monkeypatch.setattr(deployment, "workspace_dir", lambda: ws)

    prov = await _with_conn1(kit)
    await kit.panel.add_doc(DOC)
    cleared: list[tuple[str, list[str]]] = []

    async def clear_highlight(doc_id, texts):
        cleared.append((doc_id, list(texts)))
        return {"cleared": len(texts)}

    prov.clear_highlight = clear_highlight

    store = ReceiptStore()
    rid = store.begin(DOC, [{"old": "旧", "new": "新", "for_comment_ids": ["c1"]}], highlight=True)
    store.commit(rid, revision_after="r2")

    out = await kit.panel.unhighlight(rid)
    assert out["ok"] is True
    assert cleared == [(DOC, ["新"])], "要按回执写下的文本去撤，不是按整篇"
    r = store.get(rid)
    assert r["highlight"] is False and r["unhighlighted"] is True

    again = await kit.panel.unhighlight(rid)
    assert again["ok"] is False
    assert len(cleared) == 1, "已经撤过的回执不再动文档"


@pytest.mark.asyncio
async def test_unhighlight_refuses_a_receipt_that_never_highlighted(kit, monkeypatch):
    from jiuwenswarm.agents.harness.common.tools.clouddoc import deployment
    from jiuwenswarm.agents.harness.common.tools.clouddoc.receipts import ReceiptStore

    ws = kit.tmp / "ws2"
    (ws / "config").mkdir(parents=True)
    monkeypatch.setattr(deployment, "workspace_dir", lambda: ws)

    prov = await _with_conn1(kit)
    await kit.panel.add_doc(DOC)
    touched: list[str] = []

    async def clear_highlight(doc_id, texts):
        touched.append(doc_id)
        return {}

    prov.clear_highlight = clear_highlight

    store = ReceiptStore()
    plain = store.begin(DOC, [{"old": "旧", "new": "新", "for_comment_ids": []}], highlight=False)
    store.commit(plain, revision_after="r2")
    pending = store.begin(DOC, [{"old": "a", "new": "b", "for_comment_ids": []}], highlight=True)

    assert (await kit.panel.unhighlight(plain))["ok"] is False
    assert (await kit.panel.unhighlight(pending))["ok"] is False, "未落地的写入没有黄底可撤"
    assert (await kit.panel.unhighlight("nope"))["ok"] is False
    assert touched == []


@pytest.mark.asyncio
async def test_unhighlight_in_flight_survives_the_caller_being_cancelled(kit, monkeypatch):
    """The web channel cancels a request's task when the socket closes.

    Measured on the revert path before it was retired: a platform write cancelled
    after the platform took it and before the ledger did left the document changed
    and the ledger silent. ``unhighlight`` is the panel's remaining document write,
    and it is shielded for exactly this: once the platform has been asked, the
    receipt is marked whoever is still listening.
    """
    import asyncio

    from jiuwenswarm.agents.harness.common.tools.clouddoc import deployment
    from jiuwenswarm.agents.harness.common.tools.clouddoc.receipts import ReceiptStore

    ws = kit.tmp / "ws3"
    (ws / "config").mkdir(parents=True)
    monkeypatch.setattr(deployment, "workspace_dir", lambda: ws)

    prov = await _with_conn1(kit)
    await kit.panel.add_doc(DOC)
    gate = asyncio.Event()

    async def slow_clear(doc_id, texts):
        await gate.wait()
        return {"cleared": len(texts)}

    prov.clear_highlight = slow_clear

    store = ReceiptStore()
    rid = store.begin(DOC, [{"old": "旧", "new": "新", "for_comment_ids": []}], highlight=True)
    store.commit(rid, revision_after="r2")

    task = asyncio.create_task(kit.panel.unhighlight(rid))
    for _ in range(20):  # let it reach the platform call
        await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    gate.set()  # the platform answers after the caller left
    for _ in range(200):
        await asyncio.sleep(0.005)
        if store.get(rid)["highlight"] is False:
            break
    assert store.get(rid)["unhighlighted"] is True, "断连不能让账本漏掉已经发生的事"
