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
    assert (await host.execute(binding, delegate, snapshot=snapshot))["reason"] == "ATLAS_APPROVAL_STALE"
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
