"""Opt-in local Atlas execution adapter; no Swarm executor fallback.

The dedicated local service reads one Atlas-owned pairing file. Its secret is
never part of browser RPCs, URL parameters or provider context. This is not a
remote callback facility: the endpoint must be literal IPv4 loopback.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

import aiohttp

from .native_business_contract import NativeBusinessViolation
from .atlas_demo_routing import DEMO_TASK_NAMES

VERSION = "atlas.live-voice.local.v1"


def _decision_scope(kind, pending):
    if not pending:
        return None
    if kind == "expense":
        return "expense_form_submission" if pending["interactionId"].startswith("expense-submit:") else "directory_listing"
    return "purchase" if kind == "repurchase" else None


class AtlasLocalHost:
    def __init__(self, pairing_file):
        self._path = Path(pairing_file)
        self._pins = {}
        self._approval_events = {}
        self._decision_turns = {}

    @staticmethod
    def _pending(call):
        pending = call.get("pending")
        if pending is None:
            return None
        expense = call.get("expense")
        digest = expense.get("snapshot_hash") if isinstance(expense, dict) else None
        form_confirmation = (call.get("demoKind") == "expense" and isinstance(pending, dict)
            and isinstance(digest, str) and len(digest) == 64 and all(c in "0123456789abcdef" for c in digest)
            and pending.get("interactionId") == "expense-submit:" + digest
            and pending.get("preparedActionHash") == digest)
        required = ("interactionId", "message", "preparedActionHash") if form_confirmation else ("interactionId", "message", "receiptId", "preparedActionHash")
        if (type(pending) is not dict or pending.get("kind") != "confirm"
                or any(type(pending.get(key)) is not str or not pending[key]
                       for key in required)):
            return None  # Older/non-purchase questions remain in the Atlas UI.
        return json.loads(json.dumps(pending))

    @classmethod
    def configured(cls):
        path = os.environ.get("JIUWENSWARM_ATLAS_HOST_FILE")
        return cls(path) if path else None

    def _registration(self, binding):
        try:
            if self._path.stat().st_size > 4096:
                raise ValueError()
            value = json.loads(self._path.read_text(encoding="utf-8"))
            if (type(value) is not dict or set(value) != {"version", "endpoint", "token", "swarm_session_id", "binding"}
                    or value["version"] != VERSION or value["swarm_session_id"] != binding.session_id
                    or type(value["token"]) is not str or len(value["token"]) != 64
                    or any(c not in "0123456789abcdef" for c in value["token"])
                    or type(value["binding"]) is not dict or set(value["binding"]) != {"bindingId", "sessionId"}
                    or any(type(v) is not str or not v or len(v) > 256 for v in value["binding"].values())):
                raise ValueError()
            endpoint = urlsplit(value["endpoint"])
            if (endpoint.scheme != "http" or endpoint.hostname != "127.0.0.1" or not endpoint.port
                    or endpoint.username or endpoint.password or endpoint.query or endpoint.fragment
                    or endpoint.path != "/live-voice/business"):
                raise ValueError()
            key = (binding.session_id, binding.interaction_id, binding.activation_id, binding.activation_generation)
            digest = hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()
            if key not in self._pins:
                if len(self._pins) >= 128:
                    raise ValueError()
                self._pins[key] = digest
            elif self._pins[key] != digest:
                raise ValueError()
            return value
        except (OSError, TypeError, ValueError, KeyError):
            raise NativeBusinessViolation("ATLAS_HOST_BINDING_UNAVAILABLE") from None

    async def _call(self, binding, method, params):
        registration = self._registration(binding)
        timeout = aiohttp.ClientTimeout(total=25)
        async with aiohttp.ClientSession(timeout=timeout, trust_env=False) as client:
            async with client.post(registration["endpoint"], allow_redirects=False,
                    headers={"Authorization": "Bearer " + registration["token"]},
                    json={"version": VERSION, "binding": registration["binding"], "method": method, "params": params}) as response:
                if response.status != 200:
                    raise NativeBusinessViolation("ATLAS_HOST_UNAVAILABLE")
                body = bytearray()
                async for chunk in response.content.iter_chunked(16384):
                    body.extend(chunk)
                    if len(body) > 524288:
                        raise NativeBusinessViolation("ATLAS_HOST_RESULT_TOO_LARGE")
                result = json.loads(body)
        # A pairing change while HTTP was pending invalidates this observation.
        self._registration(binding)
        if type(result) is not dict or set(result) != {"ok", "result"} or result["ok"] is not True:
            raise NativeBusinessViolation("ATLAS_HOST_REQUEST_FAILED")
        return result["result"]

    async def context(self, binding):
        result = await self._call(binding, "context", {})
        if (type(result) is not dict or set(result) not in ({"history", "calls"}, {"history", "calls", "capabilities"})
                or type(result["history"]) is not list or type(result["calls"]) is not list
                or len(result["calls"]) > 128):
            raise NativeBusinessViolation("ATLAS_HOST_CONTEXT_INVALID")
        if "capabilities" in result and result["capabilities"] not in ([], ["repurchase"], ["expense"], ["repurchase", "expense"], ["expense", "repurchase"]):
            raise NativeBusinessViolation("ATLAS_HOST_CONTEXT_INVALID")
        tasks, works, events = [], [], []
        for call in result["calls"]:
            kind = call.get("demoKind") or (result.get("capabilities", [None])[0] if len(result.get("capabilities", [])) == 1 else None)
            expense = kind == "expense"
            call_id, revision, phase = call["callId"], call["revision"], call["status"]
            if (type(call_id) is not str or not call_id.startswith(("task:", "work:"))
                    or type(revision) is not int or revision < 1):
                raise NativeBusinessViolation("ATLAS_HOST_CONTEXT_INVALID")
            terminal = phase in {"completed", "failed", "aborted", "withdrawn", "unknown"}
            outcome = {"aborted": "cancelled", "withdrawn": "cancelled"}.get(phase, phase)
            target = "atlas:" + call_id
            final = call.get("answer") or call["text"]
            pending = self._pending(call) if phase == "waiting_for_user" else None
            decision_scope = _decision_scope(kind, pending)
            if terminal and kind == "repurchase" and call.get("decision") is not None:
                final = json.dumps({"executor_result": final,
                    "purchase_decision": call["decision"], "pending_purchase_approval": pending,
                    "memory_review_is_separate_from_purchase": True}, ensure_ascii=False)
            expense_snapshot = call.get("expense") if expense else None
            expense_summary = ({key: expense_snapshot.get("state", {}).get(key)
                for key in ("status", "claim_id", "totals", "findings")} if isinstance(expense_snapshot, dict) else None)
            if expense:
                final = json.dumps({"executor_result": final, "expense_form": expense_summary,
                    "form_state_unavailable": bool(call.get("expenseStateUnavailable"))}, ensure_ascii=False)
            common = {"execution_owner": "atlas", "atlas_turn_id": call["turnId"], "atlas_mandate_id": call["mandateId"],
                      "request_text": call["requestText"],
                      **({"demo_kind": kind} if kind else {}),
                      **({"approval_channel": "voice_and_ui" if expense_snapshot is not None else "atlas_ui", "expense_form": expense_summary} if expense else {}),
                      "phase": phase, "result_text": final if terminal else None, "files": call["files"],
                      **({"pending": pending} if pending else {}),
                      **({"pending_decision_scope": decision_scope} if decision_scope else {}),
                      "result_truncated": call["textTruncated"]}
            if call_id.startswith("task:"):
                tasks.append({**common, "task_id": target, "name": call["requestText"][:80], "revision_number": revision,
                              "state": "terminal" if terminal else "running", "outcome": outcome if terminal else None,
                              "supported_operations": ["task.status", "task.result", "task.details"]
                              + (["task.adjust"] if expense_snapshot and expense_snapshot.get("state", {}).get("status") == "draft" else [])
                              + (["task.approve", "task.reject"] if pending and (kind == "repurchase" or expense_snapshot is not None) else [])})
                # This identifies the Atlas execution for Native delivery. It is
                # not a Swarm Task adjustment and must not claim applied/rejected.
                identity = {"work_id": target}
            else:
                works.append({**common, "work_id": target, "revision": revision, "sequence": revision,
                              "instruction": call["requestText"], "state": outcome if terminal else "running",
                              "execution_settled": terminal, "reason": "awaiting_atlas_user" if phase == "waiting_for_user" else None})
                identity = {"work_id": target}
            if pending:
                key = (binding.session_id, target, pending["interactionId"], pending["preparedActionHash"], expense_snapshot.get("snapshot_hash") if isinstance(expense_snapshot, dict) else None)
                if key not in self._approval_events:
                    if len(self._approval_events) >= 128:
                        raise NativeBusinessViolation("ATLAS_APPROVAL_CAPACITY")
                    self._approval_events[key] = {**identity,
                        "event_id": "atlas-approval-" + hashlib.sha256(json.dumps(key).encode()).hexdigest(),
                        "revision": revision, "state": "awaiting_approval",
                        "result_text": json.dumps({"request": call["requestText"],
                            "pending_decision_scope": decision_scope,
                            "expense_form": expense_summary,
                            "approval": {key: pending[key] for key in ("message", "money", "merchant") if key in pending}}, ensure_ascii=False),
                        "reason": "ATLAS_EXPENSE_APPROVAL_REQUIRED" if expense else "ATLAS_APPROVAL_REQUIRED"}
                events.append(self._approval_events[key])
            if terminal:
                text = final
                if len(text.encode("utf-8")) > 131072:
                    text = text.encode("utf-8")[:131072].decode("utf-8", errors="ignore")
                events.append({**identity, "event_id": "atlas-result-" + hashlib.sha256(
                    json.dumps([binding.session_id, target, revision], separators=(",", ":")).encode()).hexdigest(),
                    "revision": revision, "state": outcome, "result_text": text or None,
                    "reason": "ATLAS_RESULT_TRUNCATED" if call["textTruncated"] else None})
        if len(works) > 32:
            raise NativeBusinessViolation("ATLAS_HOST_WORK_CAPACITY")
        return {"history": result["history"], "tasks": tasks, "works": works, "events": events,
                **({"capabilities": result["capabilities"]} if "capabilities" in result else {})}

    async def execute(self, binding, delegate, *, snapshot=None):
        action = delegate.business
        if action.operation == "task.adjust":
            if not action.target_id.startswith("atlas:task:"):
                return {"status": "rejected", "reason": "ATLAS_TARGET_NOT_FOUND"}
            try:
                edit = json.loads(action.adjustment)
                if type(edit) is not dict or set(edit) != {"line_id", "amount", "expected_hash"}:
                    raise ValueError()
                if type(edit["line_id"]) is not str or not edit["line_id"] or type(edit["expected_hash"]) is not str:
                    raise ValueError()
                if type(edit["amount"]) not in (int, float):
                    raise ValueError()
            except (ValueError, TypeError):
                return {"status": "rejected", "reason": "ATLAS_EXPENSE_ADJUSTMENT_INVALID",
                        "hint": "adjustment must be JSON with the exact observed line_id, amount and expected_hash from task.details expense.snapshot_hash."}
            current = await self._call(binding, "observe", {"callId": action.target_id[len("atlas:"):]})
            expense = current.get("expense") or {}
            if (current.get("demoKind") != "expense" or current["revision"] != action.expected_revision
                    or expense.get("snapshot_hash") != edit["expected_hash"] or expense.get("state", {}).get("status") != "draft"):
                return {"status": "rejected", "reason": "ATLAS_EXPENSE_ADJUSTMENT_STALE"}
            turn_id = getattr(delegate, "turn_id", None)
            if turn_id is not None:
                turn_key = (binding.session_id, getattr(binding, "interaction_id", None), turn_id)
                if turn_key not in self._decision_turns and len(self._decision_turns) >= 512:
                    return {"status": "rejected", "reason": "ATLAS_APPROVAL_TURN_CAPACITY"}
                # A correction cannot also approve its newly calculated amount.
                # Keep the fence even when the callback outcome is unknown.
                self._decision_turns[turn_key] = (action.target_id, "expense-adjust", edit["expected_hash"])
            try:
                result = await self._call(binding, "adjust", {"callId": action.target_id[len("atlas:"):],
                    "expectedHash": edit["expected_hash"], "lineId": edit["line_id"], "amount": edit["amount"]})
            except Exception:
                return {"status": "unknown", "reason": "ATLAS_EXPENSE_ADJUSTMENT_OUTCOME_UNKNOWN",
                        "hint": "Read task.details to verify the actual form and last_adjustment. Do not blindly retry or submit."}
            state = (result.get("expense") or {}).get("state", {})
            receipt = state.get("last_adjustment", {})
            if receipt.get("status") != "applied" or receipt.get("line_id") != edit["line_id"] or receipt.get("amount") != edit["amount"]:
                return {"status": "unknown", "reason": "ATLAS_EXPENSE_ADJUSTMENT_RECEIPT_MISMATCH"}
            return {"status": "applied", "task_id": action.target_id, "expense_form": state,
                    "adjustment_receipt": receipt, "submitted": False,
                    "hint": "The amount was updated and artifacts published. Ask for confirmation of the new total and remaining policy exceptions before submission; old approval is invalid."}
        if action.operation in {"task.details", "task.approve", "task.reject"}:
            if not action.target_id.startswith("atlas:task:"):
                return {"status": "rejected", "reason": "ATLAS_TARGET_NOT_FOUND"}
            call_id = action.target_id[len("atlas:"):]
            current = await self._call(binding, "observe", {"callId": call_id})
            if action.operation == "task.details":
                return {"status": "observed", "task_id": action.target_id, "phase": current["status"],
                        "pending_decision_scope": _decision_scope(current.get("demoKind"), self._pending(current)),
                        "pending": self._pending(current), "decision": current.get("decision"),
                        "operations": current.get("operations", []),
                        "operations_truncated": current.get("operationsTruncated", False),
                        "answer": current.get("answer"), "files": current["files"],
                        "expense": current.get("expense"), "expense_state_unavailable": current.get("expenseStateUnavailable", False)}
            # Re-read authority; expense voice decisions require a current form-aware adapter.
            authority = await self._call(binding, "context", {})
            kind = current.get("demoKind") or (authority.get("capabilities", [None])[0] if len(authority.get("capabilities", [])) == 1 else None)
            if kind != "repurchase" and not (kind == "expense" and isinstance(current.get("expense"), dict)):
                return {"status": "rejected", "reason": "ATLAS_EXPENSE_APPROVAL_REQUIRES_UI"}
            observed = next((task for task in (snapshot or {}).get("tasks", [])
                             if task.get("task_id") == action.target_id), {})
            pending = self._pending(current)
            facts = {"task_id": action.target_id, "phase": current["status"],
                     "revision_number": current["revision"], "decision": current.get("decision"),
                     "pending_decision_scope": _decision_scope(kind, pending),
                     "pending": pending, "executor_result": current.get("answer"),
                     "expense_form": current.get("expense", {}).get("state") if kind == "expense" else None}
            if pending is None and current.get("pending") is not None:
                return {**facts, "status": "rejected", "reason": "ATLAS_APPROVAL_STALE", "executed": False,
                        "hint": "The pending decision cannot be validated. No action was executed; do not retry or claim completion."}
            if pending is None:
                # Observing a consumed gate never executes or reverses a decision.
                # This also recovers a lost callback receipt without a blind retry.
                return {**facts, "status": "observed", "executed": False,
                        "reason": "ATLAS_APPROVAL_ALREADY_RESOLVED" if current.get("decision") else "ATLAS_NO_PENDING_APPROVAL",
                        "hint": "No approval was executed by this call. Report the current decision and result, not an expired approval or task failure. Do not retry or create another task."}
            if (current["revision"] != action.expected_revision or pending is None
                    or current["status"] != "waiting_for_user" or observed.get("pending") != pending
                    or observed.get("revision_number") != action.expected_revision):
                return {**facts, "status": "rejected", "reason": "ATLAS_APPROVAL_STALE", "executed": False,
                        "hint": "The pending decision changed; this call did not execute. Preserve earlier successful receipts. Ask about the current pending action and wait for a new explicit answer; never blindly retry."}
            # One spoken answer cannot authorize a new gate exposed by the
            # first decision (directory access is not form submission).
            turn_id = getattr(delegate, "turn_id", None)
            if turn_id is not None:
                turn_key = (binding.session_id, getattr(binding, "interaction_id", None), turn_id)
                decision_key = (action.target_id, pending["interactionId"], pending["preparedActionHash"])
                prior = self._decision_turns.get(turn_key)
                if prior is not None and prior != decision_key:
                    return {"status": "rejected", "reason": "ATLAS_APPROVAL_REQUIRES_NEW_USER_TURN",
                            "hint": "The previous spoken answer applied to another approval. Ask the new pending question and wait for a new explicit user answer. Do not retry now."}
                if prior is None and len(self._decision_turns) >= 512:
                    return {"status": "rejected", "reason": "ATLAS_APPROVAL_TURN_CAPACITY"}
                self._decision_turns[turn_key] = decision_key
            # The exact snapshot's question/hash must still be held. The callback
            # rechecks interaction identity and the gate owns prepared-action validation.
            try:
                result = await self._call(binding, "decide", {"callId": call_id,
                    "interactionId": pending["interactionId"], "approved": action.operation == "task.approve"})
            except Exception:
                return {"status": "unknown", "reason": "ATLAS_DECISION_OUTCOME_UNKNOWN"}
            if result.get("decision") != {"interactionId": pending["interactionId"], "approved": action.operation == "task.approve"}:
                return {"status": "unknown", "reason": "ATLAS_DECISION_RECEIPT_MISMATCH"}
            return {"status": "approved" if action.operation == "task.approve" else "rejected_by_user",
                    "task_id": action.target_id, "phase": result["status"], "purchase_completed": False,
                    "demo_kind": kind,
                    **({"decision_scope": "expense_form_submission" if pending["interactionId"].startswith("expense-submit:") else "directory_listing",
                        "expense_form": result.get("expense", {}).get("state")} if kind == "expense" else {})}
        if action.operation in {"task.create", "work.start"}:
            call_id = action.operation.split(".")[0] + ":" + delegate.source_identity
            text = delegate.request_text
            if action.instruction and action.instruction != text:
                text += "\n\n执行说明：\n" + action.instruction
            demo_kind = DEMO_TASK_NAMES.get(getattr(action, "name", None))
            # Translate the explicit selector to the existing Demo entrypoint.
            # Do not depend on the model repeating an English trigger phrase.
            if demo_kind == "expense":
                text = "Expense the Paris trip.\n\n用户请求及约束：\n" + text
            try:
                accepted = await self._call(binding, "submit", {"callId": call_id, "text": text,
                    "nativeTurnKey": json.dumps([binding.interaction_id, delegate.turn_id], separators=(",", ":")),
                    "userText": delegate.request_text})
                if type(accepted) is not dict or type(accepted.get("turnId")) is not str or not accepted["turnId"]:
                    raise ValueError()
            except Exception:
                # The Atlas request may already have run. Never label a lost
                # acceptance as rejection or retry with a different request ID.
                return {"status": "unknown", "reason": "ATLAS_ACCEPTANCE_UNKNOWN", "host_call_id": call_id}
            if demo_kind and (accepted.get("demoKind") != demo_kind or not accepted.get("mandateId")):
                return {"status": "unknown", "reason": "ATLAS_DEMO_ROUTE_MISMATCH", "host_call_id": call_id}
            identity = "atlas:" + call_id
            if action.operation == "task.create":
                return {"status": "dispatched", "task_id": identity,
                        "receipt": {"task_id": identity, "state": "accepted", "execution_owner": "atlas",
                                    "atlas_turn_id": accepted["turnId"], "atlas_mandate_id": accepted.get("mandateId")}}
            return {"work": {"work_id": identity, "revision": 1, "sequence": 1, "state": "accepted",
                             "execution_settled": False, "reason": None, "execution_owner": "atlas"}}
        if action.operation in {"task.list", "task.status", "task.result", "work.list", "work.get"}:
            context = await self.context(binding)
            collection = context["tasks"] if action.operation.startswith("task.") else context["works"]
            if action.operation.endswith(".list"):
                return {"status": "observed", "tasks" if action.operation.startswith("task.") else "works": collection}
            id_key = "task_id" if action.operation.startswith("task.") else "work_id"
            fact = next((item for item in collection if item[id_key] == action.target_id), None)
            if fact is None:
                return {"status": "rejected", "reason": "ATLAS_TARGET_NOT_FOUND"}
            events = [event for event in context["events"] if event.get("work_id") == action.target_id]
            return {"status": "observed", "task" if id_key == "task_id" else "work": fact,
                    "host_notifications": events}
        return {"status": "rejected", "reason": "ATLAS_OPERATION_NOT_SUPPORTED",
                "hint": "Read the task's supported_operations. Pending purchase, directory, and expense submission decisions use task.approve or task.reject, not task.adjust."}
