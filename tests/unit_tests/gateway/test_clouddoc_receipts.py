"""The receipt store (PR2c, D8): WAL lifecycle, retention, cross-process reads.

The receipt invariant's mechanical half: begin lands before the platform write,
commit after — a crash in between leaves a pending receipt, never an untracked
write. Three-shot repetition on the invariant per the §13 discipline.
"""

from __future__ import annotations

import pytest

from jiuwenswarm.agents.harness.common.tools.clouddoc.receipts import ReceiptStore


@pytest.fixture()
def store(tmp_path):
    clock = {"t": 1_000_000.0}
    s = ReceiptStore(tmp_path / "r.json", now_fn=lambda: clock["t"])
    s.clock = clock
    return s


def _edits():
    return [{"old": "旧句", "new": "新句", "for_comment_ids": ["c1", "c2"]}]


def test_begin_before_commit_is_the_wal_order_three_ways(store):
    for i in (1, 2, 3):
        rid = store.begin(f"d{i}", _edits(), highlight=True, source="apply_for_comment")
        assert store.get(rid)["status"] == "pending", "写前必须先落 pending(WAL)"
        store.commit(rid, revision_after=f"rev{i}")
        r = store.get(rid)
        assert r["status"] == "applied" and r["revision_after"] == f"rev{i}"


def test_crash_window_shows_as_pending_for_the_sweep(store):
    rid = store.begin("d1", _edits(), highlight=False)
    # no commit: the process died between begin and the platform write's ack
    assert [r["receipt_id"] for r in store.pending()] == [rid]
    store.commit(rid, revision_after=None)
    assert store.pending() == []


def test_abort_closes_pending_as_audit_fact(store):
    rid = store.begin("d1", _edits(), highlight=False)
    store.abort(rid, reason="conflict")
    r = store.get(rid)
    assert r["status"] == "aborted" and r["abort_reason"] == "conflict"
    assert store.pending() == []


def test_receipt_carries_inverse_material_and_comment_map(store):
    rid = store.begin("d1", _edits(), highlight=True, executor="agent-1")
    r = store.get(rid)
    e = r["edits"][0]
    assert e["old"] == "旧句" and e["new"] == "新句", "逆操作材料 = old/new 对"
    assert e["for_comment_ids"] == ["c1", "c2"], "D5 多对多映射"
    assert r["highlight"] is True, "撤高亮与退文字共用同一份回执"


def test_mark_reverted_links_both_receipts(store):
    rid = store.begin("d1", _edits(), highlight=True)
    store.commit(rid, revision_after="r1")
    rev_rid = store.begin("d1", [{"old": "新句", "new": "旧句", "for_comment_ids": []}],
                          highlight=False, source="revert")
    store.commit(rev_rid, revision_after="r2")
    store.mark_reverted(rid, by_receipt=rev_rid)
    assert store.get(rid)["status"] == "reverted"
    assert store.get(rid)["reverted_by"] == rev_rid, "回退本身产生新回执并回链(D8.0)"


def test_list_for_orders_newest_first(store):
    a = store.begin("d1", _edits(), highlight=False)
    store.clock["t"] += 10
    b = store.begin("d1", _edits(), highlight=False)
    store.begin("d2", _edits(), highlight=False)
    ids = [r["receipt_id"] for r in store.list_for("d1")]
    assert ids == [b, a]


def test_retention_prunes_applied_never_pending(tmp_path):
    clock = {"t": 0.0}
    s = ReceiptStore(tmp_path / "r.json", now_fn=lambda: clock["t"], max_receipts=3)
    pend = s.begin("d", _edits(), highlight=False)  # stays pending
    old_ids = []
    for i in range(4):
        clock["t"] += 1
        rid = s.begin("d", _edits(), highlight=False)
        s.commit(rid, revision_after=None)
        old_ids.append(rid)
    assert s.get(pend) is not None, "pending 永不被保留期修剪"
    assert s.get(old_ids[-1]) is not None
    assert s.get(old_ids[0]) is None, "最老的 applied 回执按保留量修剪(回退窗口=保留期)"


def test_cross_process_read(store, tmp_path):
    rid = store.begin("d1", _edits(), highlight=True)
    store.commit(rid, revision_after="rX")
    other = ReceiptStore(tmp_path / "r.json")
    assert other.get(rid)["revision_after"] == "rX", "回执跨进程可读(IC-3)"


def test_corrupt_file_treated_as_empty(store, tmp_path):
    (tmp_path / "r.json").write_text("{broken", encoding="utf-8")
    assert store.pending() == []
    rid = store.begin("d1", _edits(), highlight=False)
    assert store.get(rid) is not None


def test_a_crash_window_receipt_is_adjudicated_as_unknown(tmp_path):
    """Pending meant "begun, never closed", and nothing ever settled one: ``pending()``
    named a startup sweep in its docstring and had no caller outside these tests.

    Adjudicating honestly means recording that the outcome is unknown. The document
    cannot answer it -- matching text may mean the write landed, or that it did not and
    someone wrote the same words -- so re-reading would turn a known unknown into a
    confident wrong answer."""
    now = [1000.0]
    store = ReceiptStore(path=tmp_path / "r.json", now_fn=lambda: now[0])
    rid = store.begin("doc", [{"old": "a", "new": "b", "for_comment_ids": []}], highlight=False)

    now[0] += 100
    assert store.sweep_stale() == [], "在途写入不得被误判——文件是跨进程共享的"

    now[0] += 2000
    assert store.sweep_stale() == [rid]
    rec = store.get(rid)
    assert rec["status"] == "unknown"
    assert "无从判断" in rec["abort_reason"]


def test_an_adjudicated_receipt_can_finally_be_reclaimed(tmp_path):
    """The retention cap skips pending on purpose -- a pending receipt is the only
    evidence a write may have landed. That exemption is why they accumulated forever
    while every write rewrote the whole file."""
    now = [1000.0]
    store = ReceiptStore(path=tmp_path / "r.json", now_fn=lambda: now[0], max_receipts=5)
    for _ in range(20):
        store.begin("doc", [{"old": "a", "new": "b", "for_comment_ids": []}], highlight=False)
    assert len(store._load()["receipts"]) == 20, "未裁决前不该被回收"

    now[0] += 2000
    store.sweep_stale()
    store.begin("doc", [{"old": "a", "new": "b", "for_comment_ids": []}], highlight=False)
    assert len(store._load()["receipts"]) == 5


def test_an_unknown_receipt_is_not_revertible(tmp_path):
    """Revert requires ``applied``. An outcome nobody knows must not offer an undo:
    reverting a write that never landed would be a fresh edit dressed as an undo."""
    now = [1000.0]
    store = ReceiptStore(path=tmp_path / "r.json", now_fn=lambda: now[0])
    rid = store.begin("doc", [{"old": "a", "new": "b", "for_comment_ids": []}], highlight=False)
    now[0] += 2000
    store.sweep_stale()
    assert store.get(rid)["status"] != "applied"


# ------------------------------------------------- gaps the mutation probe found
#
# Every test below exists because a mutation survived: the code could have been wrong
# in that exact way and the suite stayed green. Line coverage on this module was 99%
# throughout, which is the point -- coverage says a line ran, not that anything checked
# what it did.


def test_commit_corrects_the_highlight_flag_and_leaves_it_alone_when_told_nothing(tmp_path):
    """``begin`` records the request; only the platform knows the outcome, so ``commit``
    carries the correction. Both branches of that were unchecked: flipping the condition
    either way changed nothing any test looked at -- in code added one round earlier
    precisely to stop the panel offering an undo for a highlight that never happened."""
    store = ReceiptStore(path=tmp_path / "r.json")

    asked = store.begin("doc", [{"old": "a", "new": "b", "for_comment_ids": []}], highlight=True)
    store.commit(asked, revision_after="r1", highlighted=False)
    assert store.get(asked)["highlight"] is False, "平台没上色时必须更正为 False"

    kept = store.begin("doc", [{"old": "a", "new": "b", "for_comment_ids": []}], highlight=True)
    store.commit(kept, revision_after="r2")
    assert store.get(kept)["highlight"] is True, "不传 highlighted 时不得改动已记录的值"


def test_settling_an_unknown_receipt_id_does_nothing_rather_than_raising(tmp_path):
    """Every lifecycle method guards on the receipt existing, and nothing exercised the
    branch. These run inside a provider's write path, where an exception would take down
    the write itself -- the outcome the guards are there to prevent."""
    store = ReceiptStore(path=tmp_path / "r.json")
    store.commit("nope", revision_after="r")
    store.abort("nope", reason="x")
    store.mark_unhighlighted("nope")
    store.mark_reverted("nope", by_receipt="other")
    assert store.get("nope") is None
    assert store.pending() == []


def test_clearing_a_highlight_is_recorded_as_done(tmp_path):
    """``mark_unhighlighted`` wrote a flag no test read, so the value it wrote was free
    to be anything."""
    store = ReceiptStore(path=tmp_path / "r.json")
    rid = store.begin("doc", [{"old": "a", "new": "b", "for_comment_ids": []}], highlight=True)
    assert not store.get(rid).get("unhighlighted")
    store.mark_unhighlighted(rid)
    assert store.get(rid)["unhighlighted"] is True


def test_mark_unverified_demotes_only_applied(tmp_path, monkeypatch):
    """D19 tier 3b: only a clean applied can become applied_unverified -- a pending
    or aborted receipt saying "read-back differed" would be claiming a write that
    never stood."""
    import jiuwenswarm.agents.harness.common.tools.clouddoc.receipts as rc

    monkeypatch.setattr(rc, "get_receipts_path", lambda: tmp_path / "r.json")
    store = rc.ReceiptStore(tmp_path / "r.json")
    rid = store.begin("d", [{"old": "a", "new": "b", "for_comment_ids": []}], highlight=False)
    store.mark_unverified(rid, detail="尚未 applied 不得降")
    assert store.get(rid)["status"] == "pending"
    store.commit(rid, revision_after="rev1")
    store.mark_unverified(rid, detail="p/i0 现读作别的")
    r = store.get(rid)
    assert r["status"] == "applied_unverified"
    assert "p/i0" in r["unverified_detail"]
