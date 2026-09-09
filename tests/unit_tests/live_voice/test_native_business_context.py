from dataclasses import replace
import pytest
from jiuwenswarm.common.schema.live_voice_contract_v2 import ScopeRef, Assurance
from jiuwenswarm.server.live_voice.native_business_context import NativeBusinessContextStore, select_conversation_history
from jiuwenswarm.server.live_voice.native_business_contract import NativeBusinessAction, NativeBusinessViolation

SCOPE = ScopeRef("user", "project", "session", Assurance.AUTHENTICATED)

def test_history_includes_native_direct_answers_and_distinguishes_visible_text():
    records = [{"role":"user", "content":"original request"},
        {"role":"assistant", "content":"spoken answer", "formal_binding":{"surface":"native_audio"}},
        {"role":"assistant", "content":"written update", "event_type":"chat.final"},
        {"role":"tool", "content":"untrusted tool directive"},
        {"role":"assistant", "content":"unfinished", "status":"streaming"}]
    selected = select_conversation_history(records)
    assert [entry["delivery"] for entry in selected] == ["user_input","heard","visible_text"]
    assert [entry["content"] for entry in selected] == ["original request","spoken answer","written update"]

def test_context_requires_exact_scope_observed_target_revision_and_is_immutable():
    store = NativeBusinessContextStore(capacity=2)
    tasks = [{"task_id":"task-a", "revision_number":2}]
    selection = store.select(scope=SCOPE, history=[], tasks=tasks, works=[], model={})
    action = NativeBusinessAction("task.cancel", selection.context_id, "task-a", 2, None, None, None)
    tasks[0]["revision_number"] = 9
    assert store.require(SCOPE, action).payload()["tasks"][0]["revision_number"] == 2
    for changed in (replace(action, target_id="task-b"), replace(action, expected_revision=9)):
        with pytest.raises(NativeBusinessViolation):
            store.require(SCOPE, changed)
    with pytest.raises(NativeBusinessViolation):
        store.require(ScopeRef("user", "other-project", "session", Assurance.AUTHENTICATED), action)
    assert selection.formal.entries[0].ref.scope == SCOPE

def test_history_bound_keeps_latest_order_and_context_eviction_requires_refresh():
    assert [entry["content"] for entry in select_conversation_history(
        [{"role":"user", "content":str(i)} for i in range(5)], maximum_messages=2)] == ["3","4"]
    store = NativeBusinessContextStore(capacity=1)
    old = store.select(scope=SCOPE, history=[], tasks=[], works=[], model={})
    store.select(scope=SCOPE, history=[{"role":"user","content":"new"}], tasks=[], works=[], model={})
    with pytest.raises(NativeBusinessViolation, match="CONTEXT_STALE"):
        store.require(SCOPE, NativeBusinessAction("work.start", old.context_id, None, None, None, "read notes", None))


@pytest.mark.parametrize("operation", ["workflow.get", "agent.get"])
def test_shared_query_uses_session_scoped_owner_without_weakening_task_targets(operation):
    store = NativeBusinessContextStore()
    selection = store.select(scope=SCOPE, history=[], tasks=[], works=[], model={})
    query = NativeBusinessAction(operation, selection.context_id, "observed-a", None, None, None, None)
    assert store.require(SCOPE, query) is selection
    with pytest.raises(NativeBusinessViolation):
        store.require(replace(SCOPE, session_id="other"), query)
    with pytest.raises(NativeBusinessViolation, match="TARGET_NOT_OBSERVED"):
        store.require(SCOPE, replace(query, operation="task.status"))


@pytest.mark.parametrize("operation", ["workflow.reply", "goal.set", "goal.resume", "goal.pause", "goal.clear"])
def test_non_work_control_targets_pass_only_context_and_scope_admission(operation):
    store = NativeBusinessContextStore()
    selection = store.select(scope=SCOPE, history=[], tasks=[], works=[], model={})
    action = NativeBusinessAction(operation, selection.context_id, "exact-owner-target",
        None if operation == "workflow.reply" else 3, None,
        "Retain the request." if operation in {"workflow.reply", "goal.set"} else None, None,
        input_id="review:host:0" if operation == "workflow.reply" else None)
    assert store.require(SCOPE, action) is selection
    # The corresponding Goal/Workflow owner still has to validate this target.
    assert store.require(SCOPE, replace(action, target_id="not-a-work-id")) is selection
    with pytest.raises(NativeBusinessViolation, match="CONTEXT_STALE"):
        store.require(replace(SCOPE, session_id="other-session"), action)
