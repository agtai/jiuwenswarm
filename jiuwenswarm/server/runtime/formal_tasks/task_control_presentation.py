# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Presentation of canonical control facts; never a language/target classifier."""

from collections.abc import Mapping
import hashlib
import json

from jiuwenswarm.common.schema.live_voice_contract_v2 import canonical_json_bytes


def task_subject(facts: Mapping[str, object], *, chinese: bool) -> str:
    name = str(facts.get("name") or facts["task_id"])
    return f"“{name}”" if chinese else f'Task "{name}"'


def adjustment_status_text(state: object, *, chinese: bool) -> str:
    if chinese:
        return {
            "pending": "修改要求已提交，尚未确认应用。",
            "applied": "最近一次修改已应用。",
            "rejected": "最近一次修改未能应用。",
            "none": "尚无已提交的修改记录。",
        }.get(state, "目前无法确认修改是否已应用。")
    return {
        "pending": "The adjustment was submitted; application is not yet confirmed.",
        "applied": "The latest adjustment has been applied.",
        "rejected": "The latest adjustment was not applied.",
        "none": "No adjustment has been submitted.",
    }.get(state, "Whether the adjustment was applied is currently unknown.")


def task_status_text(facts: Mapping[str, object], *, chinese: bool) -> str:
    subject = task_subject(facts, chinese=chinese)
    state = facts.get("outcome") if facts.get("state") == "terminal" else facts.get("state")
    if chinese:
        description = {
            "accepted": "已受理，等待执行", "running": "正在执行",
            "blocked": "受阻，等待所需条件", "decision_required": "需要你的决定",
            "completed": "已完成", "cancelled": "已取消", "failed": "执行失败",
            "interrupted": "已中断",
        }.get(state, "的执行状态暂时无法确认")
        text = f"{subject}{description}。"
    else:
        description = {
            "accepted": "is queued", "running": "is running", "blocked": "is blocked",
            "decision_required": "needs your decision", "completed": "is complete",
            "cancelled": "was cancelled", "failed": "failed", "interrupted": "was interrupted",
        }.get(state, "has an unconfirmed execution state")
        text = f"{subject} {description}. "
    return text + adjustment_status_text(facts.get("adjustment_state"), chinese=chinese)


def read_task_control_facts(store, task_id, scope, *, adjustment_id=None, include_history=False):
    """One shared projection for authenticated queries and Native context."""
    task, attempt, admission = store.task_read_snapshot(task_id, scope)
    after_seq = max(-1, task.event_head - 64)
    events = store.events(task_id, scope, after_seq=after_seq,
                                    attempt_id=task.attempt_id)
    adjustments: dict[str, tuple[int, str, object]] = {}
    requested_state = "unknown"
    requested_reason = None
    execution_event = None
    states = {"task.adjust_requested": "pending", "task.adjust_applied": "applied",
              "task.adjust_rejected": "rejected"}
    if include_history:
        # Diagnostic progress has a window; an unheard final control outcome
        # must not disappear merely because later progress filled that window.
        with store._snapshot_reader() as c:
            store._require_task_row(c, task_id, scope)
            rows = c.execute("""SELECT * FROM task_events WHERE task_id=? AND attempt_id=?
                AND event_type IN ('task.adjust_requested','task.adjust_applied','task.adjust_rejected')
                ORDER BY seq""", (task_id, task.attempt_id)).fetchall()
            events = tuple(e for e in events if e.event_type not in states) + tuple(store._event_from_row(row) for row in rows)
    for event in events:
        if event.seq > task.event_head:
            continue
        if event.event_type.startswith("attempt.") or event.event_type == f"task.{task.state.value}":
            execution_event = {
                "event_id": event.event_id, "event_type": event.event_type,
                "occurred_at": event.occurred_at,
                "details": {key: event.details[key] for key in ("reason", "summary", "error", "raw_status") if key in event.details},
            }
        if event.event_type not in states:
            continue
        command_id = event.details.get("command_id")
        if not isinstance(command_id, str):
            continue
        if adjustment_id is not None and command_id == adjustment_id:
            requested_state = states[event.event_type]
            requested_reason = event.details.get("reason")
        if event.event_type == "task.adjust_requested":
            adjustments[command_id] = (event.seq, "pending", None)
        elif command_id in adjustments:
            adjustments[command_id] = (adjustments[command_id][0], states[event.event_type], event.details.get("reason"))
    latest = max(adjustments.values(), default=None, key=lambda item: item[0])
    facts = {
        "task_id": task.task_id, "attempt_id": task.attempt_id,
        "name": task.spec.name, "state": task.state.value,
        "outcome": None if task.outcome is None else task.outcome.value,
        "attempt_state": None if attempt is None else attempt.state.value,
        "execution_event": execution_event,
        "reconciliation_state": None if task.reconciliation_state is None else task.reconciliation_state.value,
        "reconciliation_reason": task.reconciliation_reason,
        "admission": None if admission is None else {
            "queued": admission.queued,
            "reason": admission.reason,
            "next_eligible_at": admission.next_eligible_at,
            "deadline_at": admission.deadline_at,
            "reconciliation_required": admission.reconciliation_required,
            "reconciliation_reason": admission.reconciliation_reason,
            "manual_action": admission.manual_action,
        },
        "event_head": task.event_head,
        "events_after_seq": after_seq,
        "adjustment_state": latest[1] if latest else ("none" if after_seq == -1 else "unknown"),
        "adjustment_reason": latest[2] if latest else None,
        **({"requested_adjustment_state": requested_state, "requested_adjustment_reason": requested_reason} if adjustment_id is not None else {}),
    }
    facts["adjustments"] = [
        {"adjustment_id": key, "state": value[1], "reason": value[2]}
        for key, value in sorted(adjustments.items(), key=lambda item: item[1][0])
    ]
    queued = store.adjustment_queue.facts(task_id, scope, adjustment_id=adjustment_id, include_history=include_history)
    facts.update(queued)
    followup = queued.get("followup_adjustment")
    if followup is not None:
        facts.update(adjustment_state=followup["adjustment_state"], adjustment_reason=followup["reason"])
        if adjustment_id is not None:
            facts.update(requested_adjustment_state=followup["adjustment_state"],
                         requested_adjustment_reason=followup["reason"])
    return facts


def native_task_presentation(store, scope, task_ids, *, maximum_result_bytes=65536, presented=None):
    """Bound complete saved results, never synthesize them from requested intent."""
    facts, events = {}, []
    for task_id in task_ids:
        control = read_task_control_facts(store, task_id, scope, include_history=True)
        task = store.get_task(task_id, scope)
        fact = {key: control[key] for key in (
            "adjustment_accepting", "adjustment_state", "adjustment_reason",
        )}
        changes = [{**item, "application_stage": "execution"} for item in control["adjustments"]]
        changes.extend({"adjustment_id": item["adjustment_id"], "state": item["adjustment_state"],
                        "reason": item["reason"], "application_stage": "saved_result",
                        "continuation_task_id": item["continuation_task_id"]}
                       for item in control["followup_adjustments"])
        fact["adjustments"] = changes[-8:]
        if "followup_adjustment" in control:
            fact["followup_adjustment"] = control["followup_adjustment"]
        availability, result, _ = store.task_result(task_id, scope)
        fact["result_available"] = result is not None
        if result is not None:
            payload = {"result_text": result.result_text,
                       "artifacts": [artifact.to_dict() for artifact in result.artifacts]}
            size = len(canonical_json_bytes(payload))
            if size <= maximum_result_bytes:
                fact.update(payload)
                maximum_result_bytes -= size
        facts[task_id] = fact
        for change in changes:
            if len(events) >= 64 or change["state"] not in {"applied", "rejected"}:
                continue
            identity = "native-task-adjustment-event-" + hashlib.sha256(canonical_json_bytes({
                "scope": scope.to_dict(), "task_id": task_id, **change,
            })).hexdigest()
            if presented is not None and presented(identity, scope):
                continue
            events.append({"event_id": identity, "task_id": task_id,
                          "adjustment_id": change["adjustment_id"], "revision": task.revision_number,
                          "state": change["state"], "reason": change["reason"],
                          "result_text": json.dumps({"task_name": task.spec.name, **change}, ensure_ascii=False)})
    return facts, events
