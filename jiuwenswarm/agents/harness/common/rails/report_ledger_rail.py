"""D19 tier 2, the chat half: a completion claim must reconcile with the ledger.

The measured failure shape (2026-08-13): the model answered "I have drafted the
plan in the shared document (Q3 Launch Note)" over a turn with **zero write
calls** -- the report was assembled from text the document already held. Nothing
mechanical stood between that sentence and the person reading it.

This rail audits the reconciliation without understanding anything: it counts the
turn's successful cloud-document writes at ``after_tool_call``, and at
``after_invoke`` -- when the final answer exists -- checks one implication: a
turn that *touched* cloud documents, *wrote nothing*, and *claims a document was
modified* is misreporting, whatever its words. The annotation is appended to the
answer rather than replacing it: the person should read the claim **and** the
audit, the same pairing the unattended path posts into the thread.

Honest limitation (VISIBILITY-VERIFY): on the streamed path the answer text may
have reached the client chunk by chunk before ``after_invoke`` runs, in which
case the appended annotation lands in the stored result but possibly not in the
live view. The log line fires either way; whether the annotation surfaces in the
web UI needs one live measurement, and until then this rail is a floor on the
record, not a guarantee on the screen.
"""

from __future__ import annotations

import logging
import re

from openjiuwen.harness.rails.base import DeepAgentRail

logger = logging.getLogger(__name__)

_WRITE_TOOLS = frozenset({
    "clouddoc_batch_edit",
    "clouddoc_write_region",
    "clouddoc_apply_for_comment",
})

_CLAIMS_DOC_MODIFIED = re.compile(
    r"已(?:直接)?(?:修改|更新|写入|应用|改好|完成修改)"
    r"|文档(?:已|中已)"
    r"|I have (?:drafted|updated|modified|edited|written|applied)"
    r"|(?:document|spreadsheet|deck|sheet) (?:has been|was) (?:updated|modified|edited)",
    re.IGNORECASE,
)

_ANNOTATION = (
    "\n\n⚠️ 对账提示：本回合没有产生任何文档写入——如上文声称已修改文档，"
    "该修改并未发生，请勿据此认为文档已更新。"
)


class ReportLedgerRail(DeepAgentRail):
    """Count writes as they happen; audit the closing claim against the count."""

    def __init__(self) -> None:
        super().__init__()
        self._touched = False
        self._writes = 0

    async def before_invoke(self, ctx) -> None:  # noqa: D102 - per-turn reset
        self._touched = False
        self._writes = 0

    async def after_tool_call(self, ctx) -> None:  # noqa: D102
        name = str(getattr(ctx.inputs, "tool_name", "") or "")
        if not name.startswith("clouddoc_"):
            return
        self._touched = True
        if name not in _WRITE_TOOLS:
            return
        result = getattr(ctx.inputs, "tool_result", None)
        ok = bool(result.get("ok")) if isinstance(result, dict) else "\"ok\": true" in str(result or "").lower()
        if ok:
            self._writes += 1

    async def after_invoke(self, ctx) -> None:  # noqa: D102
        try:
            if not self._touched or self._writes:
                return
            result = getattr(ctx.inputs, "result", None)
            if not isinstance(result, dict):
                return
            output = result.get("output")
            if not isinstance(output, str) or not _CLAIMS_DOC_MODIFIED.search(output):
                return
            result["output"] = output + _ANNOTATION
            ctx.extra["_report_ledger_flag"] = True
            logger.warning(
                "[clouddoc] 对账不符（聊天路径）：声称已修改文档但本回合零写入"
            )
        except Exception:  # noqa: BLE001 - annotation duty must not fail the turn
            logger.exception("[clouddoc] 报告对账 rail 未完成")
