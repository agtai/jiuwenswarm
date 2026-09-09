"""Native's pending-input adapter rechecks authority at actual consumption."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import Assurance, ScopeRef
from jiuwenswarm.server.live_voice.native_business_contract import NativeBusinessAction, NativeBusinessViolation
from jiuwenswarm.server.live_voice.native_business_router import NativeBusinessRouter


@pytest.fixture
def boundary():
    scope = ScopeRef("user", "project", "session", Assurance.AUTHENTICATED)
    context = SimpleNamespace(require_usable=Mock())
    current = SimpleNamespace(context=context)
    route = SimpleNamespace(binding=SimpleNamespace(scope=scope),
        native_p3_authority=SimpleNamespace(principal=SimpleNamespace(require_usable=Mock())))
    router = NativeBusinessRouter(SimpleNamespace(_p3_composition=SimpleNamespace(_clock=lambda: "now")))
    router._require_context_authority = AsyncMock(return_value=current)
    router._require_work_authority = AsyncMock(return_value=current)
    router._recheck_context_authority = Mock()
    delegate = SimpleNamespace(source_identity="admitted-native-input",
        business=NativeBusinessAction("workflow.reply", "a" * 64, "run-1", None,
            None, "Use the first source.", None, input_id="review:host:0"))
    return router, route, delegate, current


@pytest.mark.asyncio
async def test_native_reply_calls_the_common_owner_and_reports_only_input_acceptance(boundary, monkeypatch):
    router, route, delegate, current = boundary
    delivered = []
    async def reply(**arguments):
        arguments.pop("before_effect")()
        delivered.append(arguments)
        return True, None
    monkeypatch.setattr("jiuwenswarm.server.runtime.team_workflow_capabilities.reply_swarmflow", reply)
    result = await router._workflow(route, delegate)
    assert result["status"] == "input_accepted" and "completed" not in result
    assert delivered == [dict(session_id="session", run_id="run-1", correlation_id="review:host:0",
        answer="Use the first source.", channel_id="web")]
    router._recheck_context_authority.assert_called_once_with(route, current)
    current.context.require_usable.assert_called_once_with(scope=route.binding.scope,
        required_permissions=frozenset({"task.execute", "project.write"}), destructive=False, now="now")
    assert router._work_owner is None


@pytest.mark.asyncio
async def test_revoked_authority_at_consumption_has_zero_input_effects(boundary, monkeypatch):
    router, route, delegate, current = boundary
    delivered = []
    router._recheck_context_authority.side_effect = NativeBusinessViolation("RETIRED")
    async def reply(**arguments):
        arguments["before_effect"]()
        delivered.append(arguments)
        return True, None
    monkeypatch.setattr("jiuwenswarm.server.runtime.team_workflow_capabilities.reply_swarmflow", reply)
    with pytest.raises(NativeBusinessViolation, match="RETIRED"):
        await router._workflow(route, delegate)
    assert delivered == []
    current.context.require_usable.assert_not_called()


@pytest.mark.asyncio
async def test_stale_input_and_uncertain_delivery_keep_truthful_receipts(boundary, monkeypatch):
    router, route, delegate, _ = boundary
    reply = AsyncMock(return_value=(False, "no_pending_input"))
    monkeypatch.setattr("jiuwenswarm.server.runtime.team_workflow_capabilities.reply_swarmflow", reply)
    assert (await router._workflow(route, delegate))["status"] == "rejected"
    router._recheck_context_authority.assert_not_called()
    async def uncertain(**arguments):
        arguments["before_effect"]()
        raise OSError("unconfirmed delivery")
    monkeypatch.setattr("jiuwenswarm.server.runtime.team_workflow_capabilities.reply_swarmflow", uncertain)
    result = await router._workflow(route, delegate)
    assert result["status"] == "unknown" and result["reason"] == "WORKFLOW_REPLY_OUTCOME_UNKNOWN"
