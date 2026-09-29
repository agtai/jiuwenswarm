"""Decisions (milestone 5): the agent's questions and the workspace's answers.

The agent asks with ``blackboard_ask`` during a comment or chat task; the question shows in the chat,
in the thread for a comment task, and in the Decisions panel. Any editor may answer. The requester's
own answer is final; anyone else's is a proposal the requester accepts or replaces. The accepted
answer starts the agent's next turn in the same session.
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Any

from jiuwenswarm.extensions.blackboard.common import protocol as p
from jiuwenswarm.extensions.blackboard.common.errors import CONFLICT, FORBIDDEN, BlackboardError, invalid, not_found
from jiuwenswarm.extensions.blackboard.host import validation as v
from jiuwenswarm.extensions.blackboard.host.api import dispatch
from jiuwenswarm.extensions.blackboard.host.api.access import require_member
from jiuwenswarm.extensions.blackboard.host.api.context import HostContext
from jiuwenswarm.extensions.blackboard.host.api.feed import coded, post_chat, post_comment
from jiuwenswarm.extensions.blackboard.host.api.mandates import finish_mandate
from jiuwenswarm.extensions.blackboard.host.api.methods import Call, method
from jiuwenswarm.extensions.blackboard.host.store import comments, decisions, docs, mandates, users
from jiuwenswarm.extensions.blackboard.host.store.models import Decision, Mandate

logger = logging.getLogger(__name__)

MAX_QUESTION = 1000
MAX_LABEL = 120
MAX_DESCRIPTION = 600
MAX_ANSWER = 2000


def _view(conn: sqlite3.Connection, decision: Decision) -> dict[str, Any]:
    names = users.names(conn, [decision.requester_id, decision.answered_by or "", decision.accepted_by or ""])
    return decision.to_dict(names)


def _options(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list) or not 2 <= len(value) <= 4:
        raise invalid("options is a list of 2 to 4 {label, description?}", field="options")
    out = []
    for item in value:
        label = item.get("label") if isinstance(item, dict) else None
        if not isinstance(label, str) or not label.strip() or len(label.strip()) > MAX_LABEL:
            raise invalid(f"every option needs a label of at most {MAX_LABEL} characters", field="options")
        description = item.get("description") or ""
        if not isinstance(description, str) or len(description) > MAX_DESCRIPTION:
            raise invalid(f"a description is at most {MAX_DESCRIPTION} characters", field="options")
        out.append({"label": label.strip(), "description": description.strip()})
    return out


@method(p.DECISION_CREATE)
async def decision_create(call: Call) -> dict[str, Any]:
    """The agent's question, during a turn of a comment or chat task; one open question per task."""
    mandate_id = v.required_str(call.params, "mandate_id")
    question = call.params.get("question")
    if not isinstance(question, str) or not question.strip() or len(question) > MAX_QUESTION:
        raise invalid(f"question is 1 to {MAX_QUESTION} characters", field="question")
    question = question.strip()
    options = _options(call.params.get("options"))
    recommended = call.params.get("recommended")
    if recommended is not None and (isinstance(recommended, bool) or not isinstance(recommended, int) or not 0 <= recommended < len(options)):
        raise invalid("recommended is the index of an option", field="recommended")
    doc_id = call.params.get("doc_id") if isinstance(call.params.get("doc_id"), str) else None
    block_id = call.params.get("block_id") if isinstance(call.params.get("block_id"), str) else None

    def check(conn: sqlite3.Connection) -> Mandate:
        mandate = mandates.get(conn, mandate_id)
        if mandate is None:
            raise BlackboardError("no_mandate", "no such mandate of yours", {"mandate_id": mandate_id})
        if mandate.requester_id != call.uid:
            raise BlackboardError(FORBIDDEN, "this mandate belongs to someone else", {"mandate_id": mandate_id})
        if mandate.status != "running":
            raise BlackboardError("no_mandate", f"the mandate is {mandate.status}", {"mandate_id": mandate_id, "status": mandate.status})
        if mandate.origin not in mandates.DISPATCHED_ORIGINS:
            raise BlackboardError(CONFLICT, "questions belong to tasks from a comment or the chat", {"mandate_id": mandate_id})
        if decisions.open_for_mandate(conn, mandate_id) is not None:
            raise BlackboardError("already_asked", "this task already has an open question", {"mandate_id": mandate_id})
        if doc_id is not None:
            doc = docs.get(conn, doc_id)
            if doc is None or doc.workspace_id != mandate.workspace_id:
                raise invalid("doc_id is a document of the task's workspace", field="doc_id")
        return mandate

    mandate = await call.ctx.store.read(check)
    digest, quote = await _passage(call.ctx, doc_id, block_id)

    def work(conn: sqlite3.Connection) -> dict[str, Any]:
        decision = decisions.create(
            conn,
            workspace_id=mandate.workspace_id,
            mandate_id=mandate_id,
            requester_id=call.uid,
            question=question,
            options=options,
            recommended=recommended,
            doc_id=doc_id,
            block_id=block_id if doc_id else None,
            block_digest=digest,
            quote=quote,
        )
        mandates.touch(conn, mandate_id)
        return _view(conn, decision)

    decision = await call.ctx.store.transact(work)
    await post_chat(
        call.ctx,
        workspace_id=mandate.workspace_id,
        author_id=call.uid,
        author_kind="agent",
        kind="question",
        body=question,
        mandate_id=mandate_id,
        decision_id=decision["id"],
    )
    if mandate.origin == "comment":
        thread = await call.ctx.store.read(lambda c: comments.get_thread(c, str(mandate.origin_ref.get("thread_id", ""))))
        if thread is not None:
            await post_comment(call.ctx, thread, author_id=call.uid, author_kind="agent", body=question, mandate_id=mandate_id, decision_id=decision["id"])
    await dispatch.publish_decision(call.ctx, mandate.workspace_id, decision["id"], "open")
    return {
        "decision_id": decision["id"],
        "instruction": "The question is posted. End your turn now; you will be started again with the answer.",
    }


async def _passage(ctx: HostContext, doc_id: str | None, block_id: str | None) -> tuple[str | None, str | None]:
    """The digest and opening text of the block a question is about, so the panel can say when it changed."""
    if not doc_id or not block_id or ctx.docs is None or not ctx.docs.running:
        return None, None
    try:
        result = await ctx.doc_client().markdown(doc_id, range_=f"{block_id}..{block_id}")
    except BlackboardError as exc:
        logger.debug("blackboard: reading block %s for a question failed: %s", block_id, exc.message)
        return None, None
    block = next((b for b in result.get("blocks", []) if b.get("id") == block_id), None)
    text = "\n".join(line for line in result.get("markdown", "").splitlines() if not line.startswith("<!-- block:"))
    return (block or {}).get("digest"), " ".join(text.split())[:300] or None


def _decision(conn: sqlite3.Connection, decision_id: str) -> Decision:
    decision = decisions.get(conn, decision_id)
    if decision is None:
        raise not_found("no such decision", decision_id=decision_id)
    return decision


@method(p.DECISION_LIST)
async def decision_list(call: Call) -> dict[str, Any]:
    workspace_id = v.required_str(call.params, "workspace_id")
    status = call.params.get("status")
    if status is not None and status not in ("open", "proposed", "answered", "cancelled"):
        raise invalid("status is open, proposed, answered or cancelled", field="status")

    def work(conn: sqlite3.Connection) -> list[dict[str, Any]]:
        require_member(conn, call.uid, workspace_id, "viewer")
        return [_view(conn, d) for d in decisions.list_for_workspace(conn, workspace_id, status=status)]

    listed = await call.ctx.store.read(work)
    changed = await _changed_passages(call.ctx, [d for d in listed if d["status"] in decisions.OPEN])
    return {"workspace_id": workspace_id, "decisions": [{**d, "passage_changed": d["id"] in changed} for d in listed]}


async def _changed_passages(ctx: HostContext, open_decisions: list[dict[str, Any]]) -> set[str]:
    """Open questions about a block whose text changed since they were asked."""
    about = [d for d in open_decisions if d.get("doc_id") and d.get("block_id") and d.get("block_digest")]
    if not about or ctx.docs is None or not ctx.docs.running:
        return set()
    digests: dict[str, dict[str, str]] = {}
    for doc_id in {d["doc_id"] for d in about}:
        try:
            result = await ctx.doc_client().markdown(doc_id)
        except BlackboardError:
            continue
        digests[doc_id] = {b["id"]: b["digest"] for b in result.get("blocks", []) if b.get("id")}
    return {
        d["id"]
        for d in about
        if d["doc_id"] in digests and digests[d["doc_id"]].get(d["block_id"]) != d["block_digest"]
    }


@method(p.DECISION_GET)
async def decision_get(call: Call) -> dict[str, Any]:
    decision_id = v.required_str(call.params, "decision_id")

    def work(conn: sqlite3.Connection) -> dict[str, Any]:
        decision = _decision(conn, decision_id)
        require_member(conn, call.uid, decision.workspace_id, "viewer")
        return _view(conn, decision)

    return {"decision": await call.ctx.store.read(work)}


def _answer(params: dict[str, Any], decision: Decision) -> dict[str, Any]:
    """Exactly one of an option's index or free text."""
    option, text = params.get("option"), params.get("text")
    if option is not None and text is not None:
        raise invalid("answer with an option or with text, not both", field="option")
    if option is not None:
        if isinstance(option, bool) or not isinstance(option, int) or not 0 <= option < len(decision.options):
            raise invalid("option is the index of an option", field="option")
        return {"option": option, "text": None}
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_ANSWER:
        raise invalid(f"text is 1 to {MAX_ANSWER} characters", field="text")
    return {"option": None, "text": text.strip()}


def _answer_for_turn(conn: sqlite3.Connection, decision: Decision) -> dict[str, Any]:
    """What the agent's next turn is told."""
    names = users.names(conn, [decision.answered_by or "", decision.accepted_by or ""])
    return {
        "decision_id": decision.id,
        "question": decision.question,
        "options": decision.options,
        "chosen": decision.answer_label(),
        "option": (decision.answer or {}).get("option"),
        "text": (decision.answer or {}).get("text"),
        "answered_by": names.get(decision.answered_by or "", ""),
        "accepted_by": names.get(decision.accepted_by or "", ""),
    }


@method(p.DECISION_ANSWER)
async def decision_answer(call: Call) -> dict[str, Any]:
    """An editor's answer. The requester's answer is final; anyone else's awaits the requester."""
    decision_id = v.required_str(call.params, "decision_id")

    def work(conn: sqlite3.Connection) -> tuple[Decision, dict[str, Any] | None, dict[str, Any]]:
        decision = _decision(conn, decision_id)
        require_member(conn, call.uid, decision.workspace_id, "editor")
        if decision.status not in decisions.OPEN:
            raise BlackboardError(CONFLICT, f"the question is {decision.status}", {"decision_id": decision_id})
        answer = _answer(call.params, decision)
        if call.uid == decision.requester_id:
            decisions.accept(conn, decision_id, call.uid, answer)
        else:
            decisions.propose(conn, decision_id, answer, call.uid)
        updated = _decision(conn, decision_id)
        final = _answer_for_turn(conn, updated) if updated.status == "answered" else None
        return updated, final, _view(conn, updated)

    decision, final, view = await call.ctx.store.transact(work)
    await post_chat(
        call.ctx,
        workspace_id=decision.workspace_id,
        author_id=call.uid,
        author_kind="person",
        kind="answer",
        body=decision.answer_label(),
        mandate_id=decision.mandate_id,
        decision_id=decision.id,
    )
    await dispatch.publish_decision(call.ctx, decision.workspace_id, decision.id, decision.status)
    if final is not None:
        await dispatch.continue_with_answer(call.ctx, decision.mandate_id, final)
    return {"decision": view}


@method(p.DECISION_ACCEPT)
async def decision_accept(call: Call) -> dict[str, Any]:
    """The requester takes the proposed answer; the agent continues."""
    decision_id = v.required_str(call.params, "decision_id")

    def work(conn: sqlite3.Connection) -> tuple[Decision, dict[str, Any], dict[str, Any]]:
        decision = _decision(conn, decision_id)
        require_member(conn, call.uid, decision.workspace_id, "editor")
        if call.uid != decision.requester_id:
            raise BlackboardError(FORBIDDEN, "only the person who gave the task accepts an answer", {"decision_id": decision_id})
        if decision.status != "proposed":
            raise BlackboardError(CONFLICT, f"the question is {decision.status}, with no proposal", {"decision_id": decision_id})
        decisions.accept(conn, decision_id, call.uid)
        updated = _decision(conn, decision_id)
        return updated, _answer_for_turn(conn, updated), _view(conn, updated)

    decision, final, view = await call.ctx.store.transact(work)
    await post_chat(
        call.ctx,
        workspace_id=decision.workspace_id,
        author_id=call.uid,
        author_kind="system",
        kind="notice",
        body=coded("answer_accepted", answered_by=view.get("answered_by_name") or "", answer=decision.answer_label()),
        mandate_id=decision.mandate_id,
        decision_id=decision.id,
    )
    await dispatch.publish_decision(call.ctx, decision.workspace_id, decision.id, decision.status)
    await dispatch.continue_with_answer(call.ctx, decision.mandate_id, final)
    return {"decision": view}


@method(p.DECISION_CANCEL)
async def decision_cancel(call: Call) -> dict[str, Any]:
    """The requester or any editor withdraws the question; the task it belongs to stops."""
    decision_id = v.required_str(call.params, "decision_id")

    def work(conn: sqlite3.Connection) -> Decision:
        decision = _decision(conn, decision_id)
        require_member(conn, call.uid, decision.workspace_id, "viewer" if call.uid == decision.requester_id else "editor")
        if decision.status not in decisions.OPEN:
            raise BlackboardError(CONFLICT, f"the question is {decision.status}", {"decision_id": decision_id})
        decisions.cancel(conn, decision_id)
        return _decision(conn, decision_id)

    decision = await call.ctx.store.transact(work)
    await dispatch.publish_decision(call.ctx, decision.workspace_id, decision.id, decision.status)
    mandate = await call.ctx.store.read(lambda c: mandates.get(c, decision.mandate_id))
    if mandate is not None and mandate.status in mandates.ACTIVE:
        await finish_mandate(call.ctx, mandate.id, "cancelled", f"cancelled by {call.uid}")
    return {"decision": await call.ctx.store.read(lambda c: _view(c, decision))}
