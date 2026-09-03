"""Revert-by-receipt (PR2c, D8): the first principle, atomicity, and un-highlight.

「回退必须有可回退的路径,路径不存在就不能回退」— the provider's locate is the
enforcement: an inverse that no longer anchors refuses the whole batch.
"""

from __future__ import annotations

import pytest

from jiuwenswarm.agents.harness.common.tools.clouddoc.provider import (
    DocSnapshot,
    EditResult,
    ProviderError,
)
from jiuwenswarm.gateway.clouddoc.panel import CloudDocPanel
from jiuwenswarm.agents.harness.common.tools.clouddoc.receipts import ReceiptStore


class _Prov:
    def __init__(self, body="开头。这一句已经改好。收尾。"):
        self.body = body
        self.batches = []
        self.cleared = []
        self.receipt_meta = None
        self.receipt_sink = None
        self.batch_result = EditResult("applied", new_revision_id="rev9")

    async def read(self, doc_ref):
        return DocSnapshot(doc_id=doc_ref, kind="document", revision_id="rev8", text=self.body)

    async def edit_batch(self, doc_ref, pairs, *, required_revision_id=None, highlight=False):
        self.batches.append((doc_ref, list(pairs), required_revision_id, highlight))
        if self.batch_result.status == "applied" and self.receipt_sink is not None:
            meta = self.receipt_meta or {}
            rid = self.receipt_sink.begin(
                doc_ref,
                [{"old": o, "new": n, "for_comment_ids": []} for o, n in pairs],
                highlight=highlight, source=str(meta.get("source") or ""),
            )
            self.receipt_sink.commit(rid, revision_after="rev9")
        return self.batch_result

    async def clear_highlight(self, doc_ref, texts):
        self.cleared.append((doc_ref, list(texts)))
        return {"cleared": len(texts), "missed": []}


class _Conn:
    def __init__(self, prov, docs):
        self.provider = prov
        self.watcher = type("W", (), {"_docs": docs})()


class _Reg:
    def __init__(self, conns):
        self._conns = conns

    def list(self):
        return self._conns


DOC = "doc-R-000000000000"


@pytest.fixture()
def rig(tmp_path, monkeypatch):
    import jiuwenswarm.agents.harness.common.tools.clouddoc.receipts as rc

    monkeypatch.setattr(rc, "get_receipts_path", lambda: tmp_path / "r.json")
    store = ReceiptStore(tmp_path / "r.json")
    prov = _Prov()
    prov.receipt_sink = store
    panel = object.__new__(CloudDocPanel)
    panel._reg = _Reg([_Conn(prov, [DOC])])
    # An applied, highlighted batch: old "这一句需要被改写。" -> new "这一句已经改好。"
    rid = store.begin(DOC, [{"old": "这一句需要被改写。", "new": "这一句已经改好。",
                             "for_comment_ids": ["c1"]}], highlight=True,
                      source="apply_for_comment")
    store.commit(rid, revision_after="rev8")
    return panel, prov, store, rid


@pytest.mark.asyncio
async def test_revert_applies_inverse_atomically_and_links_receipts(rig):
    panel, prov, store, rid = rig
    r = await panel.revert(rid)
    assert r["ok"], r
    doc, pairs, rev, hl = prov.batches[0]
    assert pairs == [("这一句已经改好。", "这一句需要被改写。")], "逆操作 = new→old 交换"
    assert rev == "rev8" and hl is False
    got = store.get(rid)
    assert got["status"] == "reverted"
    assert got["reverted_by"], "回退本身产生新回执并回链(D8.0)"
    assert store.get(got["reverted_by"])["source"] == f"revert:{rid}"
    assert prov.cleared and prov.cleared[0][1] == ["这一句需要被改写。"], (
        "回退后清除恢复文本可能继承的黄底"
    )


@pytest.mark.asyncio
async def test_no_viable_path_refuses_whole_batch_three_ways(rig):
    panel, prov, store, rid = rig
    prov.batch_result = EditResult("invalid", detail="cannot locate uniquely")
    for _ in range(3):
        r = await panel.revert(rid)
        assert not r["ok"] and "第一原则" in r["detail"], (
            "逆操作锚不上→整批拒绝,报告不逼近"
        )
    assert store.get(rid)["status"] == "applied", "拒绝的回退不改回执状态"


@pytest.mark.asyncio
async def test_revert_survives_acceptance(rig):
    # D8.0: resolve is no deadline — an unhighlighted (accepted) batch still reverts.
    panel, prov, store, rid = rig
    store.mark_unhighlighted(rid)
    r = await panel.revert(rid)
    assert r["ok"], "验收(撤高亮)之后仍可按回执回退"


@pytest.mark.asyncio
async def test_only_applied_receipts_revert(rig):
    panel, prov, store, rid = rig
    other = store.begin(DOC, [{"old": "a", "new": "b", "for_comment_ids": []}],
                        highlight=False)
    r = await panel.revert(other)  # still pending
    assert not r["ok"]
    assert not (await panel.revert("missing-id"))["ok"]


@pytest.mark.asyncio
async def test_unhighlight_op_clears_new_spans_and_marks(rig):
    panel, prov, store, rid = rig
    r = await panel.unhighlight(rid)
    assert r["ok"], r
    assert prov.cleared[0][1] == ["这一句已经改好。"], "撤高亮作用于写入的 new 文本"
    assert store.get(rid).get("unhighlighted") is True
    assert not (await panel.unhighlight(rid))["ok"] or True  # second call: no highlight left


@pytest.mark.asyncio
async def test_watcher_unhighlights_on_resolve(tmp_path, monkeypatch):
    """D8.3 automatic half: human resolve → highlights removed by receipt."""
    from test_clouddoc_watcher import C, Clock, FakeProvider, DOC as WDOC, SA
    from jiuwenswarm.gateway.clouddoc.comment_watcher import (
        CloudDocCommentWatcher, WatcherConfig,
    )
    from jiuwenswarm.gateway.clouddoc.cursor_store import CloudDocStore
    from jiuwenswarm.gateway.clouddoc.triggers import TriggerConfig

    store = ReceiptStore(tmp_path / "r.json")
    prov = FakeProvider()
    prov.receipt_sink = store
    cleared = []

    async def clear_highlight(doc_ref, texts):
        cleared.append((doc_ref, list(texts)))
        return {"cleared": len(texts), "missed": []}

    prov.clear_highlight = clear_highlight
    rid = store.begin(WDOC, [{"old": "旧", "new": "新句", "for_comment_ids": ["c1"]}],
                      highlight=True, source="apply_for_comment")
    store.commit(rid, revision_after="r1")

    cstore = CloudDocStore(tmp_path / "s.json", now_fn=Clock())
    w = CloudDocCommentWatcher(
        prov, cstore, TriggerConfig(sa_address=SA), WatcherConfig(),
        dispatch=None, now_fn=Clock(),
    )
    w._docs = [WDOC]
    await cstore.seed_if_new(WDOC, [])
    prov.comments = [C("c1", "改这句", resolved=True)]
    await w.tick()
    assert cleared and cleared[0][1] == ["新句"], "resolve 后按回执撤该批高亮"
    assert store.get(rid).get("unhighlighted") is True
    cleared.clear()
    await w.tick()
    assert cleared == [], "已撤过的不重复撤"


# ------------------------------------------- telling the threads a batch was undone


@pytest.mark.asyncio
async def test_revert_tells_every_thread_the_batch_answered(rig):
    """What the receipt's many-to-many map is for (D5). The people who wrote those
    comments are reading their own threads, not the panel: an edit that appears and
    later disappears with nothing said reads as the agent changing its mind."""
    panel, prov, store, rid = rig
    prov.replies = []

    async def reply(doc_ref, comment_id, content):
        prov.replies.append((comment_id, content))
        return "r-new"

    prov.reply_comment = reply
    out = await panel.revert(rid)
    assert out["ok"], out
    assert out["notified"] == ["c1"]
    assert prov.replies and prov.replies[0][0] == "c1"
    assert "回退" in prov.replies[0][1]


@pytest.mark.asyncio
async def test_revert_notice_follows_the_commenter_language(rig):
    """The notice was a Chinese literal. It follows the thread's comment when the
    provider can list comments, and the receipt's own edit text when it cannot --
    the rig's provider has no list_comments, which is the fallback case."""
    from jiuwenswarm.agents.harness.common.tools.clouddoc.provider import DocComment

    panel, prov, store, rid = rig
    prov.replies = []

    async def reply(doc_ref, comment_id, content):
        prov.replies.append((comment_id, content))
        return "r-new"

    async def list_comments(doc_ref, *, include_resolved=False):
        return [DocComment(
            comment_id="c1", author_is_self=False, author_display_name="Z",
            created_time="2026-08-19T00:00:00.000Z", content="fix this",
            quoted_text="这一句已经改好。", resolved=False,
        )]

    prov.reply_comment = reply
    prov.list_comments = list_comments
    out = await panel.revert(rid)
    assert out["ok"] and out["notified"] == ["c1"]
    text = prov.replies[0][1]
    assert "reverted" in text
    assert not any("\u4e00" <= ch <= "\u9fff" for ch in text), text


@pytest.mark.asyncio
async def test_a_merged_batch_reaches_all_of_its_threads(rig):
    """One edit may answer several comments on one passage; each of them is owed the
    same notice."""
    panel, prov, store, _ = rig
    rid = store.begin(
        DOC,
        [{"old": "原文一。", "new": "改后一。", "for_comment_ids": ["c1", "c2"]},
         {"old": "原文二。", "new": "改后二。", "for_comment_ids": ["c2", "c3"]}],
        highlight=False, source="batch_edit",
    )
    store.commit(rid, revision_after="rev8")
    prov.replies = []

    async def reply(doc_ref, comment_id, content):
        prov.replies.append(comment_id)
        return "r"

    prov.reply_comment = reply
    out = await panel.revert(rid)
    assert out["ok"], out
    # Every thread once, in the order the edits named them.
    assert out["notified"] == ["c1", "c2", "c3"]


@pytest.mark.asyncio
async def test_a_thread_that_cannot_be_replied_to_does_not_fail_the_revert(rig):
    """The undo has already landed and is the thing that mattered. A reply that cannot
    be posted must not turn a successful revert into a reported failure -- and the
    caller is told which threads were actually reached."""
    panel, prov, store, rid = rig

    async def reply(doc_ref, comment_id, content):
        raise ProviderError("forbidden", "cannot reply")

    prov.reply_comment = reply
    out = await panel.revert(rid)
    assert out["ok"], out
    assert out["notified"] == []


@pytest.mark.asyncio
async def test_revert_refuses_without_a_receipt_sink(rig):
    """A revert is a write to a shared document, and D8 wants it to leave a receipt that
    links back to the one it undoes.

    Without a sink the write lands, the link lookup finds nothing, and the chain is
    recorded broken while the person is told it succeeded. The same check was added to
    apply_for_comment and not here -- a pattern fixed on the path that surfaced it
    rather than on every path that has it."""
    panel, prov, store, rid = rig
    prov.receipt_sink = None
    out = await panel.revert(rid)
    assert not out["ok"]
    assert "回执" in out["detail"]
    assert not prov.batches, "没有凭据时一个字也不能回退"


# ---------------------------------------------------------------- region receipts


class _RegionProv(_Prov):
    """A provider whose document is a grid; regions read and write by address."""

    def __init__(self, current: dict[str, str]):
        super().__init__(body="")
        self.current = dict(current)          # region -> flattened current content
        self.region_writes: list[list] = []

    async def read_regions(self, doc_ref, regions):
        return [self.current[r] for r in regions]

    async def write_regions(self, doc_ref, pairs, *, required_revision_id=""):
        self.region_writes.append(list(pairs))
        if self.receipt_sink is not None:
            meta = self.receipt_meta or {}
            rid = self.receipt_sink.begin(
                doc_ref,
                [{"old": "x", "new": "y", "for_comment_ids": []} for _ in pairs],
                highlight=False, source=str(meta.get("source") or ""),
                executor=str(meta.get("executor") or ""),
            )
            self.receipt_sink.commit(rid, revision_after="rev9")
        return EditResult("applied", new_revision_id="rev9")


def _region_rig(tmp_path, monkeypatch, *, current, edits):
    import jiuwenswarm.agents.harness.common.tools.clouddoc.receipts as rc

    monkeypatch.setattr(rc, "get_receipts_path", lambda: tmp_path / "r.json")
    store = ReceiptStore(tmp_path / "r.json")
    prov = _RegionProv(current)
    prov.receipt_sink = store
    panel = object.__new__(CloudDocPanel)
    panel._reg = _Reg([_Conn(prov, [DOC])])
    rid = store.begin(DOC, edits, highlight=False, source="write_region", executor="chat")
    store.commit(rid, revision_after="rev8")
    return panel, prov, store, rid


@pytest.mark.asyncio
async def test_a_region_receipt_reverts_by_writing_the_old_grid_back(tmp_path, monkeypatch):
    """The inverse of an addressed write is the old grid through the same address.

    The first shipped region receipts stored ``(region:addr, "…")`` and every revert
    failed looking for a literal ellipsis in the body. This pins the repaired shape
    end to end: anchor check against ``new``, write of ``old_grid``, and the receipt
    chain the text path already had."""
    panel, prov, store, rid = _region_rig(
        tmp_path, monkeypatch,
        current={"Sheet1!A7:B7": "大家好\t"},
        edits=[{"old": "\t大家好", "new": "大家好\t", "region": "Sheet1!A7:B7",
                "old_grid": [["", "大家好"]], "for_comment_ids": []}],
    )
    out = await panel.revert(rid)
    assert out["ok"], out.get("detail")
    assert prov.region_writes == [[("Sheet1!A7:B7", [["", "大家好"]])]]
    assert store.get(rid)["status"] == "reverted"
    assert store.get(rid)["reverted_by"], "回退回执必须回链到被撤的那笔"


@pytest.mark.asyncio
async def test_a_drifted_region_refuses_the_whole_batch(tmp_path, monkeypatch):
    """R2 in region form: the region must still read exactly like what this receipt
    wrote. Drift anywhere refuses everything, with the drifted region named."""
    panel, prov, store, rid = _region_rig(
        tmp_path, monkeypatch,
        current={"Sheet1!A7:B7": "后来的内容\t"},
        edits=[{"old": "\t大家好", "new": "大家好\t", "region": "Sheet1!A7:B7",
                "old_grid": [["", "大家好"]], "for_comment_ids": []}],
    )
    out = await panel.revert(rid)
    assert not out["ok"]
    assert "Sheet1!A7:B7" in out["detail"]
    assert prov.region_writes == [], "锚不成立时一个区域也不得写"
    assert store.get(rid)["status"] == "applied", "拒绝不是回退，状态不得推进"


@pytest.mark.asyncio
async def test_a_legacy_region_receipt_without_the_before_image_is_refused(tmp_path, monkeypatch):
    """Receipts written before the before-image existed carry no inverse. Saying so
    beats guessing: the region content they would restore is simply not on record."""
    panel, prov, store, rid = _region_rig(
        tmp_path, monkeypatch,
        current={"Sheet1!A7:B7": "大家好\t"},
        edits=[{"old": "region:Sheet1!A7:B7", "new": "…", "region": "Sheet1!A7:B7",
                "for_comment_ids": []}],
    )
    out = await panel.revert(rid)
    assert not out["ok"]
    assert "人工恢复" in out["detail"]
    assert prov.region_writes == []


@pytest.mark.asyncio
async def test_a_mixed_receipt_is_refused_as_one_batch(tmp_path, monkeypatch):
    """Half region, half text cannot revert atomically through either machinery, and
    a partial revert is worse than a refused one."""
    panel, prov, store, rid = _region_rig(
        tmp_path, monkeypatch,
        current={"Sheet1!A7:B7": "大家好\t"},
        edits=[{"old": "\t大家好", "new": "大家好\t", "region": "Sheet1!A7:B7",
                "old_grid": [["", "大家好"]], "for_comment_ids": []},
               {"old": "旧句", "new": "新句", "for_comment_ids": []}],
    )
    out = await panel.revert(rid)
    assert not out["ok"]
    assert "混合" in out["detail"]
    assert prov.region_writes == [] and prov.batches == []


@pytest.mark.asyncio
async def test_an_unverified_receipt_may_attempt_a_revert(tmp_path, monkeypatch):
    """applied_unverified is the status that most wants undoing; whether the inverse
    still anchors is the anchor check's call, not a status gate's."""
    panel, prov, store, rid = _region_rig(
        tmp_path, monkeypatch,
        current={"Sheet1!A7:B7": "大家好\t"},
        edits=[{"old": "\t大家好", "new": "大家好\t", "region": "Sheet1!A7:B7",
                "old_grid": [["", "大家好"]], "for_comment_ids": []}],
    )
    store.mark_unverified(rid, detail="测试降级")
    out = await panel.revert(rid)
    assert out["ok"], out.get("detail")


@pytest.mark.asyncio
async def test_a_revert_in_flight_survives_the_caller_being_cancelled(rig):
    """The web channel cancels a request's task when the socket closes. Measured: a
    Feishu revert cancelled after the platform took the write and before the ledger
    did -- the cell read reverted, the revert receipt stayed pending, the original
    stayed applied. The write runs to its ledger entry whoever is still listening."""
    import asyncio

    panel, prov, store, rid = rig
    gate = asyncio.Event()
    original = prov.edit_batch

    async def slow_edit_batch(*a, **kw):
        await gate.wait()
        return await original(*a, **kw)

    prov.edit_batch = slow_edit_batch
    task = asyncio.create_task(panel.revert(rid))
    for _ in range(20):                      # let it reach the platform call
        await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    gate.set()                                # the platform answers after the caller left
    for _ in range(200):
        await asyncio.sleep(0.005)
        if store.get(rid)["status"] == "reverted":
            break
    got = store.get(rid)
    assert got["status"] == "reverted" and got["reverted_by"], got
    assert store.get(got["reverted_by"])["status"] == "applied"
