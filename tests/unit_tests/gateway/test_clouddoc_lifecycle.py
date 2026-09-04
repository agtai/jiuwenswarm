"""Lifecycle receipts: creating, sharing and trashing a document leave receipts whose
inverse is another lifecycle act, materialized by the same revert core as edits."""
from __future__ import annotations

import pytest

from jiuwenswarm.agents.harness.common.tools.clouddoc.clouddoc_tools import (
    ALL_TOOL_NAMES,
    UNATTENDED_DENYLIST,
    CloudDocToolkit,
)
from jiuwenswarm.agents.harness.common.tools.clouddoc.provider import ProviderError
from jiuwenswarm.agents.harness.common.tools.clouddoc.receipts import ReceiptStore
from jiuwenswarm.agents.harness.common.tools.clouddoc.revert import (
    LIFECYCLE_INVERSE,
    execute_revert,
)

DOC = "doc-LIFECYCLE-0000000000"


class _Prov:
    """A platform that can do every lifecycle act (Google-shaped)."""

    kind = "google"

    def __init__(self, store):
        self.receipt_sink = store
        self.log: list[tuple] = []

    def parse_doc_ref(self, ref):
        return ref

    def doc_url(self, doc_id, kind=""):
        return f"https://example.test/{doc_id}"

    async def create_document(self, title):
        self.log.append(("create", title))
        return DOC

    async def share_document(self, doc_ref, email, *, role="writer"):
        if email.endswith("@bad"):
            raise ProviderError("invalid", "bad address")
        self.log.append(("share", doc_ref, email, role))

    async def unshare_document(self, doc_ref, email):
        self.log.append(("unshare", doc_ref, email))

    async def trash_document(self, doc_ref):
        self.log.append(("trash", doc_ref))

    async def restore_document(self, doc_ref):
        self.log.append(("restore", doc_ref))


class _FeishuLike(_Prov):
    kind = "feishu"

    async def restore_document(self, doc_ref):
        raise ProviderError("unsupported", "no restore call")


def _kit(prov, *, unattended=False, ask=True):
    kit = CloudDocToolkit(
        prov,
        turn_address=lambda: "bot@example.test",
        turn_doc_id=(lambda: DOC) if unattended else (lambda: None),
    )
    kit._ask_channel_override = ask
    return kit


# ------------------------------------------------------------------ the ledger


def test_a_lifecycle_receipt_records_its_act_and_subject(tmp_path):
    s = ReceiptStore(tmp_path / "r.json")
    rid = s.begin(DOC, [], highlight=False, op="share",
                  subject={"email": "a@b.c", "role": "writer"})
    s.commit(rid, revision_after=None)
    r = s.get(rid)
    assert r["op"] == "share" and r["subject"] == {"email": "a@b.c", "role": "writer"}
    assert r["status"] == "applied" and r["edits"] == []


def test_an_edit_receipt_written_before_the_field_existed_reads_as_an_edit(tmp_path):
    s = ReceiptStore(tmp_path / "r.json")
    rid = s.begin(DOC, [{"old": "a", "new": "b"}], highlight=False)
    assert s.get(rid)["op"] == "edit"


def test_every_lifecycle_act_has_exactly_one_inverse():
    assert set(LIFECYCLE_INVERSE) == {"create", "share", "trash", "restore", "unshare"}
    # Applying the table twice lands back on an act of the same effect.
    assert LIFECYCLE_INVERSE[LIFECYCLE_INVERSE["share"]] == "share"
    assert LIFECYCLE_INVERSE[LIFECYCLE_INVERSE["trash"]] == "trash"


# ------------------------------------------------------------------ revert


@pytest.mark.asyncio
@pytest.mark.parametrize("op,subject,expect", [
    ("create", {"title": "t"}, ("trash", DOC)),
    ("share", {"email": "a@b.c", "role": "writer"}, ("unshare", DOC, "a@b.c")),
    ("trash", {}, ("restore", DOC)),
    ("unshare", {"email": "a@b.c", "role": "writer"}, ("share", DOC, "a@b.c", "writer")),
])
async def test_reverting_a_lifecycle_receipt_performs_its_inverse(tmp_path, op, subject, expect):
    s = ReceiptStore(tmp_path / "r.json")
    prov = _Prov(s)
    rid = s.begin(DOC, [], highlight=False, op=op, subject=subject)
    s.commit(rid, revision_after=None)

    out = await execute_revert(prov, s, rid)
    assert out.ok, out.detail
    assert prov.log == [expect]
    original = s.get(rid)
    assert original["status"] == "reverted"
    link = s.get(original["reverted_by"])
    assert link["op"] == LIFECYCLE_INVERSE[op]
    assert link["source"] == f"revert:{rid}" and link["executor"] == "panel"
    assert link["status"] == "applied" and link["subject"] == subject


@pytest.mark.asyncio
async def test_a_platform_without_the_inverse_refuses_and_changes_nothing(tmp_path):
    """Feishu has no restore call: the trash receipt stays applied, the attempted
    inverse is aborted with the platform's reason, and the person is told."""
    s = ReceiptStore(tmp_path / "r.json")
    prov = _FeishuLike(s)
    rid = s.begin(DOC, [], highlight=False, op="trash", subject={})
    s.commit(rid, revision_after=None)

    out = await execute_revert(prov, s, rid)
    assert not out.ok and "unsupported" in out.detail
    assert s.get(rid)["status"] == "applied"
    aborted = [r for r in s.list_for(DOC) if r["status"] == "aborted"]
    assert len(aborted) == 1 and aborted[0]["op"] == "restore"


@pytest.mark.asyncio
async def test_a_pending_lifecycle_receipt_is_not_revertible(tmp_path):
    s = ReceiptStore(tmp_path / "r.json")
    prov = _Prov(s)
    rid = s.begin(DOC, [], highlight=False, op="share", subject={"email": "a@b.c"})
    out = await execute_revert(prov, s, rid)
    assert not out.ok and prov.log == []


# ------------------------------------------------------------------ the tools


def test_the_two_new_tools_are_registered_and_denied_unattended():
    for name in ("clouddoc_share_document", "clouddoc_trash_document"):
        assert name in ALL_TOOL_NAMES
        assert name in UNATTENDED_DENYLIST


@pytest.mark.asyncio
async def test_creation_leaves_a_receipt_per_act(tmp_path):
    s = ReceiptStore(tmp_path / "r.json")
    prov = _Prov(s)
    out = await _kit(prov).create_document(title="计划", share_with=["a@b.c", "x@bad"])
    assert out["ok"], out
    rows = {r["receipt_id"]: r for r in s.list_for(DOC)}
    create = rows[out["receipt_id"]]
    assert create["op"] == "create" and create["status"] == "applied"
    assert create["subject"] == {"title": "计划"}
    shares = [r for r in rows.values() if r["op"] == "share"]
    by_email = {r["subject"]["email"]: r["status"] for r in shares}
    assert by_email == {"a@b.c": "applied", "x@bad": "aborted"}
    assert out["share_receipt_ids"] == [r["receipt_id"] for r in shares if r["status"] == "applied"]


@pytest.mark.asyncio
async def test_sharing_an_existing_document_leaves_one_receipt_per_address(tmp_path):
    s = ReceiptStore(tmp_path / "r.json")
    prov = _Prov(s)
    out = await _kit(prov).share_document(doc_id=DOC, share_with=["a@b.c", "b@b.c"])
    assert out["ok"], out
    assert [e[2] for e in prov.log] == ["a@b.c", "b@b.c"]
    assert len(out["receipt_ids"]) == 2
    for rid in out["receipt_ids"]:
        assert s.get(rid)["op"] == "share" and s.get(rid)["status"] == "applied"


@pytest.mark.asyncio
async def test_trashing_leaves_a_receipt_and_says_whether_it_can_come_back(tmp_path):
    s = ReceiptStore(tmp_path / "r.json")
    out = await _kit(_Prov(s)).trash_document(doc_id=DOC)
    assert out["ok"], out
    assert s.get(out["receipt_id"])["op"] == "trash"
    assert "回退" in out["detail"]

    s2 = ReceiptStore(tmp_path / "r2.json")
    out2 = await _kit(_FeishuLike(s2)).trash_document(doc_id=DOC)
    assert out2["ok"], out2
    assert "手动恢复" in out2["detail"]


@pytest.mark.asyncio
async def test_a_refused_trash_aborts_its_receipt(tmp_path):
    s = ReceiptStore(tmp_path / "r.json")
    prov = _Prov(s)

    async def trash_document(doc_ref):
        raise ProviderError("forbidden", "not the owner")

    prov.trash_document = trash_document
    out = await _kit(prov).trash_document(doc_id=DOC)
    assert not out["ok"]
    assert [r["status"] for r in s.list_for(DOC)] == ["aborted"]


@pytest.mark.asyncio
@pytest.mark.parametrize("tool,kwargs", [
    ("share_document", {"doc_id": DOC, "share_with": ["a@b.c"]}),
    ("trash_document", {"doc_id": DOC}),
])
async def test_lifecycle_acts_are_refused_unattended_and_without_a_confirmation_channel(
    tmp_path, tool, kwargs,
):
    s = ReceiptStore(tmp_path / "r.json")
    prov = _Prov(s)
    out = await getattr(_kit(prov, unattended=True), tool)(**kwargs)
    assert not out["ok"] and "无人值守" in out["detail"]
    out = await getattr(_kit(prov, ask=False), tool)(**kwargs)
    assert not out["ok"] and "Full Access" in out["detail"]
    assert prov.log == [] and s.list_for(DOC) == []


# ------------------------------------------------------------------ Feishu link


def test_a_created_feishu_document_gets_a_link_once_the_tenant_is_known():
    """The create call returns only a token; the tenant domain is learned from any
    link seen before, and without one the token stands (the honest answer)."""
    from jiuwenswarm.agents.harness.common.tools.clouddoc.feishu_provider import (
        FeishuDocsProvider,
    )
    prov = FeishuDocsProvider.__new__(FeishuDocsProvider)
    prov._url_cache = {}
    assert prov._tenant_origin() == ""
    prov._url_cache["AAA"] = "https://acme.feishu.cn/docx/AAA?from=x"
    assert prov._tenant_origin() == "https://acme.feishu.cn"


# ------------------------------------------------------------------ E2E 2026-09-03 fixes
from types import SimpleNamespace as _NS


@pytest.mark.asyncio
async def test_a_handled_assignment_no_longer_blocks_chat_writes(tmp_path):
    """Assignment is first-touch: once the agent has posted in the thread the task is
    handled, and an unresolved comment must not freeze chat writes for its lifetime."""
    s = ReceiptStore(tmp_path / "r.json")
    prov = _Prov(s)
    me = "bot@example.test"
    handled = _NS(comment_id="c1", assignee_address=me, resolved=False,
                  replies=(_NS(author_is_self=True),))
    fresh = _NS(comment_id="c2", assignee_address=me, resolved=False, replies=())
    other = _NS(comment_id="c3", assignee_address="someone@else", resolved=False, replies=())

    async def list_comments(doc_id, include_resolved=False):
        return [handled, fresh, other]

    prov.list_comments = list_comments
    assert await _kit(prov)._assigned_open(DOC) == ["c2"]


@pytest.mark.asyncio
async def test_list_documents_names_the_platform(tmp_path):
    s = ReceiptStore(tmp_path / "r.json")
    prov = _Prov(s)

    async def title(ref):
        return "计划"

    async def doc_kind(ref):
        return "document"

    async def list_accessible_documents():
        raise ProviderError("invalid", "cannot enumerate")

    prov.title = title
    prov.doc_kind = doc_kind
    prov.list_accessible_documents = list_accessible_documents
    kit = CloudDocToolkit(prov, turn_address=lambda: "bot", turn_doc_id=lambda: None,
                          watched_docs=lambda: [DOC])
    out = await kit.list_documents()
    assert out["ok"], out
    assert out["documents"][0]["platform"] == "google"


@pytest.mark.asyncio
async def test_workmode_edit_says_it_leaves_no_receipt(tmp_path):
    s = ReceiptStore(tmp_path / "r.json")
    f = tmp_path / "wm.md"
    f.write_text("# 风格\n- 简短\n", encoding="utf-8")
    kit = CloudDocToolkit(_Prov(s), turn_address=lambda: "bot", turn_doc_id=lambda: None,
                          workmode_file=str(f))
    out = await kit.workmode_edit(old_string="- 简短", new_string="- 更简短")
    assert out["ok"], out
    assert "没有回执编号" in out["detail"]
    assert s.list_for(DOC) == []


@pytest.mark.asyncio
async def test_chat_writes_are_refused_past_the_per_write_caps(tmp_path):
    """§5.6's caps hold on the chat path: eleven edits used to reach the permission
    prompt and land (measured 2026-09-03, L2-22)."""
    s = ReceiptStore(tmp_path / "r.json")
    prov = _Prov(s)

    async def read(doc_ref):
        return _NS(text="第一句。第二句。", revision_id="r1", cells=None, kind="document", formula_cells=())

    prov.read = read
    kit = CloudDocToolkit(prov, turn_address=lambda: "bot", turn_doc_id=lambda: None,
                          watched_docs=lambda: [DOC])
    kit._ask_channel_override = True
    kit._read_docs.add(DOC)
    edits = [{"old_string": f"第{i}句。", "new_string": f"改{i}。"} for i in range(11)]
    out = await kit.batch_edit(doc_id=DOC, edits=edits)
    assert not out["ok"] and "max_edits" in out["detail"]
    out = await kit.batch_edit(doc_id=DOC, edits=[{"old_string": "第一句。", "new_string": "x" * 2500}])
    assert not out["ok"] and "max_insert_chars" in out["detail"]


def test_priming_seeds_feishu_links_so_a_create_can_build_one(tmp_path, monkeypatch):
    """A Feishu create in a fresh process needs the tenant origin; one persisted
    link teaches it (measured 2026-09-03: the create returned a bare token because
    no link had been seen in that process)."""
    import json
    from jiuwenswarm.agents.harness.common.tools.clouddoc import kinds as kinds_mod
    from jiuwenswarm.agents.harness.common.tools.clouddoc.feishu_provider import FeishuDocsProvider

    state = tmp_path / "clouddoc-state.json"
    state.write_text(json.dumps({"docs": {
        "AAA": {"panel_meta": {"kind": "document", "url": "https://acme.feishu.cn/docx/AAA?from=x"}},
        "BBB": {"panel_meta": {"kind": "spreadsheet"}},
    }}), encoding="utf-8")
    monkeypatch.setattr(kinds_mod, "get_clouddoc_state_path", lambda: state)

    prov = FeishuDocsProvider.__new__(FeishuDocsProvider)
    prov._url_cache = {}
    prov._kind_cache = {}
    kinds_mod.prime_provider_kinds(prov, ["AAA", "BBB"])
    assert prov._url_cache["AAA"] == "https://acme.feishu.cn/docx/AAA"
    assert prov._kind_cache["BBB"] == "spreadsheet"
    assert prov._tenant_origin() == "https://acme.feishu.cn"



# ------------------------------------------------------------------ locate anchors


def test_sheet_and_slide_anchors_are_url_fragments():
    from jiuwenswarm.agents.harness.common.tools.clouddoc.google_formats import sheet_anchor, slide_anchor
    gids = {"评分表": 123, "It's": 7}
    assert sheet_anchor("'评分表'!B3:D7", gids) == "#gid=123&range=B3:D7"
    assert sheet_anchor("评分表!B3", gids) == "#gid=123&range=B3"
    assert sheet_anchor("'It''s'!A1", gids) == "#gid=7&range=A1"
    assert sheet_anchor("'unknown'!A1", gids) == ""
    assert sheet_anchor("B3:D7", gids) == ""
    assert slide_anchor("g3a1f2/title_1") == "#slide=id.g3a1f2"
    assert slide_anchor("") == ""


def test_receipt_begin_records_the_anchor_beside_the_region(tmp_path):
    from jiuwenswarm.agents.harness.common.tools.clouddoc.google_provider import GoogleDocsProvider
    s = ReceiptStore(tmp_path / "r.json")
    prov = GoogleDocsProvider.__new__(GoogleDocsProvider)
    prov.receipt_sink = s
    prov.receipt_meta = None
    rid = prov._receipt_begin(
        DOC, [("old", "new")], highlight=False,
        regions=[("'评分表'!B3:D7", [["old"]])], anchors={"'评分表'!B3:D7": "#gid=1&range=B3:D7"},
    )
    e = s.get(rid)["edits"][0]
    assert e["region"] == "'评分表'!B3:D7" and e["anchor"] == "#gid=1&range=B3:D7"


@pytest.mark.asyncio
async def test_reverting_a_restore_receipt_trashes_again(tmp_path):
    s = ReceiptStore(tmp_path / "r.json")
    prov = _Prov(s)
    rid = s.begin(DOC, [], highlight=False, op="restore", subject={})
    s.commit(rid, revision_after=None)
    out = await execute_revert(prov, s, rid)
    assert out.ok and prov.log == [("trash", DOC)]
    assert s.get(s.get(rid)["reverted_by"])["op"] == "trash"


@pytest.mark.asyncio
async def test_deployment_rail_overrides_reach_the_chat_write_caps(tmp_path):
    """config clouddoc.rail.* must do something: the caps the chat path enforces
    come from the deployment's overrides, not only the built-in defaults."""
    s = ReceiptStore(tmp_path / "r.json")
    prov = _Prov(s)

    async def read(doc_ref):
        return _NS(text="第一句。第二句。第三句。", revision_id="r1", cells=None,
                   kind="document", formula_cells=())

    prov.read = read
    kit = CloudDocToolkit(prov, turn_address=lambda: "bot", turn_doc_id=lambda: None,
                          watched_docs=lambda: [DOC], rail_overrides={"max_edits": 2})
    kit._ask_channel_override = True
    kit._read_docs.add(DOC)
    edits = [{"old_string": f"第{w}句。", "new_string": f"改{w}。"} for w in ("一", "二", "三")]
    out = await kit.batch_edit(doc_id=DOC, edits=edits)
    assert not out["ok"] and "max_edits" in out["detail"] and "2" in out["detail"]


# ------------------------------------------------------------------ supersession


def test_a_later_write_marks_the_earlier_receipt_covered(tmp_path):
    """A receipt whose ground a later write covered cannot be reverted -- the
    platform refuses its inverse. The ledger can say so before the person clicks,
    and says it without ever rewriting the receipt."""
    s = ReceiptStore(tmp_path / "r.json")
    first = s.begin(DOC, [{"old": "", "new": "A", "region": "p/i0", "old_grid": [[""]]}],
                    highlight=False)
    s.commit(first, revision_after=None)
    second = s.begin(DOC, [{"old": "A", "new": "B", "region": "p/i0", "old_grid": [["A"]]}],
                     highlight=False)
    s.commit(second, revision_after=None)

    rows = {r["receipt_id"]: r for r in s.list_for(DOC)}
    assert rows[first]["superseded_by"] == second
    assert "superseded_by" not in rows[second]  # the newest still stands
    # The stored ledger is untouched: annotation happens on read.
    import json as _json
    raw = _json.loads((tmp_path / "r.json").read_text())["receipts"]
    assert "superseded_by" not in raw[first]


def test_a_text_edit_is_covered_when_a_later_edit_consumes_what_it_wrote(tmp_path):
    s = ReceiptStore(tmp_path / "r.json")
    first = s.begin(DOC, [{"old": "旧句", "new": "新句"}], highlight=False)
    s.commit(first, revision_after=None)
    second = s.begin(DOC, [{"old": "新句", "new": "更新的句"}], highlight=False)
    s.commit(second, revision_after=None)
    rows = {r["receipt_id"]: r for r in s.list_for(DOC)}
    assert rows[first]["superseded_by"] == second


def test_untouched_regions_and_settled_receipts_are_not_marked(tmp_path):
    s = ReceiptStore(tmp_path / "r.json")
    a = s.begin(DOC, [{"old": "", "new": "A", "region": "p/i0", "old_grid": [[""]]}], highlight=False)
    s.commit(a, revision_after=None)
    b = s.begin(DOC, [{"old": "", "new": "Z", "region": "p/i9", "old_grid": [[""]]}], highlight=False)
    s.commit(b, revision_after=None)
    aborted = s.begin(DOC, [{"old": "A", "new": "X", "region": "p/i0", "old_grid": [["A"]]}], highlight=False)
    s.abort(aborted, reason="platform refused")
    rows = {r["receipt_id"]: r for r in s.list_for(DOC)}
    # Different regions do not cover each other, and a write that never landed
    # covers nothing.
    assert "superseded_by" not in rows[a]
    assert "superseded_by" not in rows[b]
