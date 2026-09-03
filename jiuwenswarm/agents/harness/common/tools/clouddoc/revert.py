"""Revert by receipt: the mechanical half of ring ⑥.

Relocated here from the panel during the loosening cuts (§25.5, cut ⑤): the R2
anchor criterion, the inverse's materialization and the chain-marking are
mechanism -- the same machinery whichever surface asks for the undo (the web
panel today, the standalone CLI's acceptance console tomorrow). What stays with
each surface is everything around the mechanics: resolving which provider serves
the document, clearing inherited highlights, notifying the threads a batch
answered, and wording the outcome for its reader.

The contract is the first principle, verbatim: an inverse that no longer anchors
on the current state refuses the whole batch with the drifted spots named --
report, never approximate. A successful revert is itself a receipted write,
linked both ways (the original marked ``reverted_by``, the new receipt carrying
``source=revert:<id>``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jiuwenswarm.agents.harness.common.tools.clouddoc.provider import ProviderError


@dataclass
class RevertOutcome:
    ok: bool
    detail: str
    receipt: dict[str, Any] | None = field(default=None)


async def execute_revert(prov: Any, store: Any, receipt_id: str) -> RevertOutcome:
    """Materialize and apply the inverse of one applied receipt, whole-batch atomic.

    The caller owns provider resolution and everything a person sees afterwards;
    this function owns eligibility, the anchor criterion in both its forms, the
    write, and the chain.
    """
    r = store.get(receipt_id)
    if r is None:
        return RevertOutcome(False, "回执不存在（可能已超出保留期——回退窗口=回执保存期）。")
    if r["status"] not in ("applied", "applied_unverified"):
        # ``applied_unverified`` may attempt a revert: the write landed but the
        # read-back disagreed, and whether the inverse still anchors is exactly
        # what the checks below adjudicate -- a status gate refusing here would
        # leave the one status that most wants undoing without a path.
        return RevertOutcome(False, f"回执状态为 {r['status']}，不可回退。", r)
    doc_id = r["doc_id"]

    # IC-2 on this path too: a revert is a write to a shared document, and D8 wants
    # it to leave a receipt that links back to the one it undoes. Without a sink the
    # write would land, the link lookup would find nothing, and the chain would be
    # recorded broken while the person is told the revert succeeded.
    if getattr(prov, "receipt_sink", None) is None:
        return RevertOutcome(
            False,
            "回执记录不可用，回退被拒绝：回退本身也要留下可回链的凭据。"
            "请检查工作区 config 目录是否可写。",
            r,
        )

    op = str(r.get("op") or "edit")
    if op != "edit":
        return await _revert_lifecycle(prov, store, r)

    edits = list(r["edits"] or [])
    regioned = [e for e in edits if e.get("region")]
    if regioned and len(regioned) != len(edits):
        return RevertOutcome(False, "回执混合了区域条目与文本条目，无法作为一批回退。", r)

    if regioned:
        # The region form of the anchor criterion: each region must still read
        # exactly like what this receipt wrote. Drift anywhere refuses the whole
        # batch with the drifted regions named.
        missing = [e["region"] for e in edits if not isinstance(e.get("old_grid"), list)]
        if missing:
            return RevertOutcome(False, (
                f"这些区域条目缺少写入前内容，无法构造逆操作：{', '.join(missing[:5])}。"
                "（早于内容记录上线的区域回执只能人工恢复。）"
            ), r)
        try:
            current = await prov.read_regions(doc_id, [e["region"] for e in edits])
        except ProviderError as exc:
            return RevertOutcome(False, f"回退被拒（{exc.kind}）：{exc}", r)
        drifted = [e["region"] for e, cur in zip(edits, current) if cur != e["new"]]
        if drifted:
            return RevertOutcome(False, (
                f"这些区域已不再是该回执写入的内容：{', '.join(drifted[:5])}。"
                "可回退路径不存在则不回退（第一原则）——该区域可能已被后续修改覆盖。"
            ), r)

    snap = await prov.read(doc_id)
    prov.receipt_meta = {
        "source": f"revert:{receipt_id}",
        # A revert is commissioned by the principal: ring ⑤ wants that visible when
        # the history is read back, not just the fact that a write happened.
        "executor": "panel",
        "for_comment_ids_by_old": {},
    }
    try:
        if regioned:
            res = await prov.write_regions(
                doc_id,
                [(e["region"], e["old_grid"]) for e in edits],
                required_revision_id=snap.revision_id or "",
            )
        else:
            res = await prov.edit_batch(
                doc_id, [(e["new"], e["old"]) for e in edits],
                required_revision_id=snap.revision_id, highlight=False,
            )
    finally:
        prov.receipt_meta = None
    if res.status != "applied":
        return RevertOutcome(False, (
            f"回退被拒（{res.status}）：{res.detail}。"
            "可回退路径不存在则不回退（第一原则）——该区域可能已被后续修改覆盖。"
        ), r)

    link = next(
        (x["receipt_id"] for x in store.list_for(doc_id)
         if (x.get("source") or "") == f"revert:{receipt_id}"),
        "",
    )
    store.mark_reverted(receipt_id, by_receipt=link)
    return RevertOutcome(True, "已按回执原子回退。", r)


# A lifecycle receipt's inverse is another lifecycle act on the same subject. The
# table is the whole of the policy: an act missing here has no inverse and is
# refused rather than guessed.
LIFECYCLE_INVERSE = {
    "create": "trash",
    "share": "unshare",
    "trash": "restore",
    "restore": "trash",
    "unshare": "share",
}


async def _revert_lifecycle(prov: Any, store: Any, r: dict) -> RevertOutcome:
    """Undo one applied lifecycle receipt by performing its inverse act.

    Same shape as the edit path: the inverse leaves its own receipt (source
    ``revert:<id>``, executor ``panel``), a platform refusal leaves the original
    untouched and aborts the inverse's receipt, and success links the two.
    """
    op = str(r.get("op") or "")
    inverse = LIFECYCLE_INVERSE.get(op)
    if inverse is None:
        return RevertOutcome(False, f"回执的操作类型 {op!r} 没有逆操作，不可回退。", r)
    doc_id = str(r.get("doc_id") or "")
    subject = dict(r.get("subject") or {})
    receipt_id = str(r.get("receipt_id") or "")
    link = store.begin(
        doc_id, [], highlight=False, executor="panel", source=f"revert:{receipt_id}",
        op=inverse, subject=subject,
    )
    try:
        if inverse == "trash":
            await prov.trash_document(doc_id)
        elif inverse == "restore":
            await prov.restore_document(doc_id)
        elif inverse == "unshare":
            await prov.unshare_document(doc_id, str(subject.get("email") or ""))
        elif inverse == "share":
            await prov.share_document(
                doc_id, str(subject.get("email") or ""),
                role=str(subject.get("role") or "writer"),
            )
    except ProviderError as exc:
        store.abort(link, reason=f"{exc.kind}: {exc}")
        return RevertOutcome(False, f"回退被拒（{exc.kind}）：{exc}", r)
    store.commit(link, revision_after=None)
    store.mark_reverted(receipt_id, by_receipt=link)
    return RevertOutcome(True, "已按回执执行逆操作。", r)
