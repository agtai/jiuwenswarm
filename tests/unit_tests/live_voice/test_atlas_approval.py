from types import SimpleNamespace
import pytest
from jiuwenswarm.server.live_voice.atlas_local_host import AtlasLocalHost


def fixture(tmp_path):
    host = AtlasLocalHost(tmp_path / "unused")
    call = {"callId": "task:c", "requestText": "帮我复购三月份的咖啡", "revision": 5,
        "status": "waiting_for_user", "turnId": "t", "mandateId": "m", "text": "every step",
        "files": [], "textTruncated": False, "answer": None,
        "operations": [{"seq": 1, "tool": "history", "argsSummary": "March", "resultSummary": "500g EUR18.50", "at": "now"}],
        "operationsTruncated": False,
        "pending": {"interactionId": "i", "kind": "confirm", "message": "500g变成450g，确认购买？",
                    "money": {"amount": "22.85", "currency": "EUR"}, "merchant": "Harbour Lane",
                    "receiptId": "r", "preparedActionHash": "hash"}}
    calls = []
    async def callback(binding, method, params):
        calls.append((method, params))
        if method == "context":
            return {"history": [], "calls": [call], "capabilities": ["repurchase"]}
        if method == "observe":
            return call
        if method == "decide":
            call.update(status="running", pending=None, decision={"interactionId": params["interactionId"], "approved": params["approved"]})
            return call
        raise AssertionError(method)
    host._call = callback
    return host, call, calls


@pytest.mark.asyncio
async def test_pending_notification_is_stable_and_operations_are_on_demand(tmp_path):
    host, call, _ = fixture(tmp_path)
    binding = SimpleNamespace(session_id="s")
    first = await host.context(binding)
    assert first["events"][0]["state"] == "awaiting_approval"
    assert "22.85" in first["events"][0]["result_text"]
    assert "operations" not in first["tasks"][0]
    call["revision"] += 1
    assert (await host.context(binding))["events"] == first["events"]
    delegate = SimpleNamespace(business=SimpleNamespace(operation="task.details", target_id="atlas:task:c"))
    details = await host.execute(binding, delegate)
    assert details["operations"] == call["operations"]
    call.update(status="completed", answer="订单已创建，总额22.85欧元", pending=None)
    result = await host.context(binding)
    assert result["events"][0]["result_text"] == call["answer"]
    assert "every step" not in result["events"][0]["result_text"]


@pytest.mark.asyncio
@pytest.mark.parametrize("operation,approved", [("task.approve", True), ("task.reject", False)])
async def test_decision_checks_current_revision_and_exact_pending(tmp_path, operation, approved):
    host, call, calls = fixture(tmp_path)
    binding = SimpleNamespace(session_id="s")
    snapshot = await host.context(binding)
    action = SimpleNamespace(operation=operation, target_id="atlas:task:c", expected_revision=4)
    delegate = SimpleNamespace(business=action, request_text="confirm")
    assert (await host.execute(binding, delegate, snapshot=snapshot))["status"] == "rejected"
    assert not any(method == "decide" for method, _ in calls)
    action.expected_revision = 5
    assert (await host.execute(binding, delegate, snapshot=snapshot))["status"] == ("approved" if approved else "rejected_by_user")
    decision = [params for method, params in calls if method == "decide"]
    assert decision == [{"callId": "task:c", "interactionId": "i", "approved": approved}]
    await host.execute(binding, delegate, snapshot=snapshot)
    assert len([method for method, _ in calls if method == "decide"]) == 1


@pytest.mark.asyncio
async def test_ui_decision_or_changed_hash_rejects_delayed_voice_without_effects(tmp_path):
    host, call, calls = fixture(tmp_path)
    binding = SimpleNamespace(session_id="s")
    snapshot = await host.context(binding)
    action = SimpleNamespace(operation="task.approve", target_id="atlas:task:c", expected_revision=5)
    delegate = SimpleNamespace(business=action)
    call["pending"]["preparedActionHash"] = "replacement"
    assert (await host.execute(binding, delegate, snapshot=snapshot))["reason"] == "ATLAS_APPROVAL_STALE"
    call.update(pending=None, status="running")
    assert (await host.context(binding))["events"] == []
    assert (await host.execute(binding, delegate, snapshot=snapshot))["reason"] == "ATLAS_NO_PENDING_APPROVAL"
    assert not any(method == "decide" for method, _ in calls)


@pytest.mark.asyncio
async def test_lost_decision_receipt_is_unknown_and_not_retried(tmp_path):
    host, call, calls = fixture(tmp_path)
    binding = SimpleNamespace(session_id="s")
    snapshot = await host.context(binding)
    original = host._call
    async def lost(binding, method, params):
        result = await original(binding, method, params)
        if method == "decide":
            raise TimeoutError()
        return result
    host._call = lost
    action = SimpleNamespace(operation="task.approve", target_id="atlas:task:c", expected_revision=5)
    result = await host.execute(binding, SimpleNamespace(business=action), snapshot=snapshot)
    assert result["status"] == "unknown"
    assert len([method for method, _ in calls if method == "decide"]) == 1
    assert call["status"] == "running"


@pytest.mark.asyncio
async def test_final_result_separates_consumed_purchase_approval_from_memory_review(tmp_path):
    import json
    host, call, _ = fixture(tmp_path)
    call.update(status="completed", pending=None, answer="Order HL-123 placed. Memory episode pending review.",
                decision={"interactionId": "i", "approved": True})
    context = await host.context(SimpleNamespace(session_id="s"))
    assert context["tasks"][0]["result_text"] == context["events"][0]["result_text"]
    result = json.loads(context["events"][0]["result_text"])
    assert result["executor_result"] == call["answer"]
    assert result["purchase_decision"]["approved"] is True
    assert result["pending_purchase_approval"] is None
    assert result["memory_review_is_separate_from_purchase"] is True


@pytest.mark.asyncio
async def test_legacy_expense_adapter_without_form_state_keeps_decisions_in_ui(tmp_path):
    host, call, calls = fixture(tmp_path)
    original = host._call
    async def expense(binding, method, params):
        result = await original(binding, method, params)
        if method == "context":
            result["capabilities"] = ["expense"]
        return result
    host._call = expense
    call["requestText"] = "报销巴黎出差费用"
    call["pending"]["message"] = "List the working area before publishing the claim."
    binding = SimpleNamespace(session_id="s")
    snapshot = await host.context(binding)
    assert snapshot["capabilities"] == ["expense"]
    assert snapshot["tasks"][0]["approval_channel"] == "atlas_ui"
    assert "task.approve" not in snapshot["tasks"][0]["supported_operations"]
    assert snapshot["events"][0]["reason"] == "ATLAS_EXPENSE_APPROVAL_REQUIRED"
    call["revision"] += 1
    assert (await host.context(binding))["events"] == snapshot["events"]
    for operation in ["task.approve", "task.reject"]:
        delegate = SimpleNamespace(business=SimpleNamespace(operation=operation, target_id="atlas:task:c"))
        assert (await host.execute(binding, delegate, snapshot=snapshot))["reason"] == "ATLAS_EXPENSE_APPROVAL_REQUIRES_UI"
    assert not any(method == "decide" for method, _ in calls)
    call.update(status="completed", pending=None, answer="Expense materials generated; meal cap exceeded")
    result = await host.context(binding)
    import json
    assert json.loads(result["events"][0]["result_text"])["executor_result"] == call["answer"]
    assert result["tasks"][0]["result_text"] == result["events"][0]["result_text"]


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["expense", "repurchase", None])
async def test_combined_capabilities_apply_decision_policy_per_task(tmp_path, kind):
    host, call, effects = fixture(tmp_path)
    original = host._call
    if kind is not None:
        call["demoKind"] = kind
    async def mixed(binding, method, params):
        result = await original(binding, method, params)
        if method == "context":
            result["capabilities"] = ["repurchase", "expense"]
        return result
    host._call = mixed
    binding = SimpleNamespace(session_id="s")
    snapshot = await host.context(binding)
    assert ("task.approve" in snapshot["tasks"][0]["supported_operations"]) == (kind == "repurchase")
    delegate = SimpleNamespace(business=SimpleNamespace(operation="task.approve", target_id="atlas:task:c", expected_revision=5), request_text="yes")
    await host.execute(binding, delegate, snapshot=snapshot)
    assert any(method == "decide" for method, _ in effects) == (kind == "repurchase")


@pytest.mark.asyncio
@pytest.mark.parametrize("form_submit", [False, True])
@pytest.mark.parametrize("operation", ["task.approve", "task.reject"])
async def test_expense_directory_and_form_have_separate_spoken_decisions(tmp_path, form_submit, operation):
    host, call, effects = fixture(tmp_path)
    call["demoKind"] = "expense"
    digest = "a" * 64
    call["expense"] = {"snapshot_hash": digest, "demo_only": True, "state": {
        "status": "draft", "totals": {"EUR": 1382.9}, "findings": ["Dinner exceeds cap"],
        "lines": [{"label": "Dinner", "amount": 86.5}]}}
    if form_submit:
        call["pending"] = {"interactionId": "expense-submit:" + digest, "kind": "confirm",
            "message": "Submit this mock expense claim?", "preparedActionHash": digest}
    binding = SimpleNamespace(session_id="s")
    snapshot = await host.context(binding)
    assert snapshot["events"][0]["reason"] == "ATLAS_EXPENSE_APPROVAL_REQUIRED"
    assert operation in snapshot["tasks"][0]["supported_operations"]
    details = await host.execute(binding, SimpleNamespace(business=SimpleNamespace(operation="task.details", target_id="atlas:task:c")))
    assert details["expense"]["state"]["lines"][0]["amount"] == 86.5
    scope = "expense_form_submission" if form_submit else "directory_listing"
    assert snapshot["tasks"][0]["pending_decision_scope"] == scope
    assert details["pending_decision_scope"] == scope
    import json
    assert json.loads(snapshot["events"][0]["result_text"])["pending_decision_scope"] == scope
    delegate = SimpleNamespace(business=SimpleNamespace(operation=operation, target_id="atlas:task:c", expected_revision=5))
    await host.execute(binding, delegate, snapshot=snapshot)
    decisions = [params for method, params in effects if method == "decide"]
    assert len(decisions) == 1
    assert decisions[0]["approved"] == (operation == "task.approve")
    assert decisions[0]["interactionId"] == ("expense-submit:" + digest if form_submit else "i")


def test_form_confirmation_requires_matching_expense_snapshot():
    digest = "a" * 64
    call = {"demoKind": "expense", "expense": {"snapshot_hash": digest},
        "pending": {"interactionId": "expense-submit:" + digest, "kind": "confirm", "message": "Submit?", "preparedActionHash": digest}}
    assert AtlasLocalHost._pending(call) is not None
    call["expense"]["snapshot_hash"] = "b" * 64
    assert AtlasLocalHost._pending(call) is None


@pytest.mark.asyncio
async def test_one_spoken_answer_cannot_approve_directory_then_submit_form(tmp_path):
    host, call, effects = fixture(tmp_path)
    digest = "a" * 64
    call.update(demoKind="expense", expense={"snapshot_hash": digest, "state": {"status": "draft"}})
    binding = SimpleNamespace(session_id="s", interaction_id="voice")
    action = SimpleNamespace(operation="task.approve", target_id="atlas:task:c", expected_revision=5)
    delegate = SimpleNamespace(business=action, turn_id="directory-answer")
    first = await host.execute(binding, delegate, snapshot=await host.context(binding))
    assert first["decision_scope"] == "directory_listing"
    call.update(status="waiting_for_user", revision=6, pending={"interactionId": "expense-submit:" + digest,
        "kind": "confirm", "message": "Submit?", "preparedActionHash": digest})
    action.expected_revision = 6
    observed = await host.context(binding)
    blocked = await host.execute(binding, delegate, snapshot=observed)
    assert blocked["reason"] == "ATLAS_APPROVAL_REQUIRES_NEW_USER_TURN"
    assert len([1 for method, _ in effects if method == "decide"]) == 1
    assert call["status"] == "waiting_for_user"
    delegate.turn_id = "explicit-submit-answer"
    second = await host.execute(binding, delegate, snapshot=observed)
    assert second["decision_scope"] == "expense_form_submission"
    assert len([1 for method, _ in effects if method == "decide"]) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["expense", "repurchase"])
@pytest.mark.parametrize("approved", [True, False])
async def test_consumed_decision_returns_truth_not_expiry_or_new_effect(tmp_path, kind, approved):
    host, call, effects = fixture(tmp_path)
    call["demoKind"] = kind
    if kind == "expense":
        call["expense"] = {"state": {"status": "draft", "totals": {"EUR": 1382.9}}}
    binding = SimpleNamespace(session_id="s", interaction_id="v")
    snapshot = await host.context(binding)
    operation = "task.approve" if approved else "task.reject"
    delegate = SimpleNamespace(business=SimpleNamespace(operation=operation,
        target_id="atlas:task:c", expected_revision=5), turn_id="u")
    first = await host.execute(binding, delegate, snapshot=snapshot)
    assert first["status"] == ("approved" if approved else "rejected_by_user")
    call.update(status="completed", revision=9, answer="Order placed" if approved else "Cancelled")
    if kind == "expense":
        call["expense"]["state"]["status"] = "submitted" if approved else "rejected"
    # Both replayed and fresh-context repeated/opposite decisions are observations.
    for context in [snapshot, await host.context(binding)]:
        for requested in ["task.approve", "task.reject"]:
            delegate.business.operation = requested
            result = await host.execute(binding, delegate, snapshot=context)
            assert result["status"] == "observed"
            assert result["reason"] == "ATLAS_APPROVAL_ALREADY_RESOLVED"
            assert result["executed"] is False
            assert result["decision"]["approved"] is approved
            assert result["phase"] == "completed"
            assert result["executor_result"] == call["answer"]
            if kind == "expense":
                assert result["expense_form"]["status"] == call["expense"]["state"]["status"]
    assert len([1 for method, _ in effects if method == "decide"]) == 1


@pytest.mark.asyncio
async def test_lost_receipt_recovery_observes_completed_decision_without_reexecution(tmp_path):
    host, call, effects = fixture(tmp_path)
    binding = SimpleNamespace(session_id="s")
    snapshot = await host.context(binding)
    original = host._call
    async def lost(binding, method, params):
        result = await original(binding, method, params)
        if method == "decide":
            raise TimeoutError()
        return result
    host._call = lost
    delegate = SimpleNamespace(business=SimpleNamespace(operation="task.approve", target_id="atlas:task:c", expected_revision=5))
    assert (await host.execute(binding, delegate, snapshot=snapshot))["status"] == "unknown"
    recovered = await host.execute(binding, delegate, snapshot=snapshot)
    assert recovered["status"] == "observed" and recovered["decision"]["approved"] is True
    assert recovered["phase"] == "running"  # Approval is not a purchase receipt.
    assert recovered["executor_result"] is None
    assert len([1 for method, _ in effects if method == "decide"]) == 1


@pytest.mark.asyncio
async def test_malformed_pending_is_not_reported_as_no_approval(tmp_path):
    host, call, effects = fixture(tmp_path)
    call["pending"].pop("preparedActionHash")
    delegate = SimpleNamespace(business=SimpleNamespace(operation="task.approve", target_id="atlas:task:c", expected_revision=5))
    result = await host.execute(SimpleNamespace(session_id="s"), delegate, snapshot={})
    assert result["status"] == "rejected" and result["reason"] == "ATLAS_APPROVAL_STALE"
    assert not any(method == "decide" for method, _ in effects)
