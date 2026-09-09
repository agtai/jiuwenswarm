"""Native Team directory uses the real configured owner and closed wire schema.

Static Team assembly is the same real SDK fixture as capability tests. Runtime
execution/Provider acceptance is separate; directory calls must not initialize it.
"""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
import pytest_asyncio

from jiuwenswarm.common.schema.live_voice_contract_v2 import Assurance, ScopeRef
from jiuwenswarm.server.live_voice.native_business_router import NativeBusinessRouter
from jiuwenswarm.server.live_voice.native_business_tools import native_business_proposal_from_function_call
from jiuwenswarm.server.live_voice.native_interaction_contract import NativeInteractionBinding
from jiuwenswarm.server.runtime.session_execution import SessionExecutionService
from tests.unit_tests.agentserver.test_team_execution_capabilities import configured  # noqa: F401


@pytest_asyncio.fixture
async def entry(configured):  # noqa: F811 - explicitly imported shared fixture
    c = configured
    scope = ScopeRef('user', c.scope.project_id, c.scope.session_id, Assurance.AUTHENTICATED)
    c.app.pin_agent, c.app.unpin_agent = Mock(), Mock()
    service = c.app.executions = SessionExecutionService(c.app)
    granted = [True]

    def authorize(**kwargs):
        assert kwargs['scope'] == scope
        if not granted[0]:
            raise PermissionError('revoked')

    context = SimpleNamespace(file_path=c.scope.project_dir, require_usable=Mock(side_effect=authorize))
    current = SimpleNamespace(context=context)
    registry = SimpleNamespace(_agent_manager=c.app, _stopped=False,
        _p3_composition=SimpleNamespace(_accepting=True, _clock=lambda: 'now'))
    router = NativeBusinessRouter(registry)
    router._require_current_context_route = Mock(return_value=None)
    router._require_context_authority = AsyncMock(return_value=current)
    router._require_work_authority = AsyncMock(return_value=current)
    binding = NativeInteractionBinding(scope, 'interaction', 'activation', 1, 'correlation')
    route = SimpleNamespace(binding=binding, native_p3_authority=SimpleNamespace(
        context=context, principal=SimpleNamespace(require_usable=Mock(return_value=None))))

    async def call(operation='team.list', **params):
        proposal = native_business_proposal_from_function_call(
            name='jiuwen_' + operation.replace('.', '_'),
            arguments=json.dumps({'request_text': 'Use the configured Team', 'context_id': 'a' * 64, **params}),
            binding=binding, turn_id='turn', response_generation=1,
            provider_event_id='event', provider_call_id='call', provider_item_id='item')
        return await router._team(route, proposal)

    yield SimpleNamespace(**locals())
    assert service._records == {}
    assert await service.close()
    c.forbidden.assert_not_called()


@pytest.mark.asyncio
async def test_native_directory_preserves_real_team_facts_without_starting(entry):
    e = entry
    before = e.c.path.read_bytes()
    result = await e.call()
    assert result['epoch'] == e.service.execution_epoch
    assert result['executions'] == []
    assert result['configured_team']['available'] is True
    capability = result['configured_team']['capability']
    assert capability['team_name'] == 'team-a'
    assert capability['enable_permissions'] is True
    assert len(capability['spec_fingerprint']) == 64
    assert 'private-' not in json.dumps(result)
    assert e.c.path.read_bytes() == before
    assert await e.c.runtime.pool.get('team-a') is e.c.entry


@pytest.mark.asyncio
async def test_native_empty_directory_still_checks_current_authority(entry, monkeypatch):
    e = entry
    monkeypatch.setattr('jiuwenswarm.agents.harness.team.team_manager._team_manager', None)
    result = await e.call()
    assert result['configured_team']['available'] is False
    assert result['executions'] == []
    e.granted[0] = False
    with pytest.raises(PermissionError, match='revoked'):
        await e.call()


@pytest.mark.asyncio
async def test_native_team_cannot_change_stored_project_or_mode(entry):
    e = entry
    e.c.metadata['project_id'] = 'other'
    e.c.path.write_text(json.dumps(e.c.metadata), encoding='utf-8')
    with pytest.raises(ValueError, match='EXECUTION_CONTEXT_SCOPE_MISMATCH'):
        await e.call()
    e.c.metadata['project_id'] = e.c.scope.project_id
    e.c.metadata['mode'] = 'agent'
    e.c.path.write_text(json.dumps(e.c.metadata), encoding='utf-8')
    with pytest.raises(ValueError, match='scope_invalid'):
        await e.call()


@pytest.mark.asyncio
@pytest.mark.parametrize('operation,params', [
    ('team.get', {'target_id': 'old-run'}),
    ('team.cancel', {'target_id': 'old-run'}),
    ('team.start', {'fingerprint': None, 'instruction': 'Start the configured task'}),
    ('workflow.start', {'fingerprint': None, 'inputs': {'script': 'answer = 1'}}),
])
async def test_old_epoch_rejects_before_team_preparation_or_execution(entry, operation, params):
    with pytest.raises(ValueError, match='TEAM_EXECUTION_EPOCH_MISMATCH'):
        await entry.call(operation, epoch='old-process', **params)


@pytest.mark.asyncio
@pytest.mark.parametrize('inputs', [{'script': 'x', 'script_path': 'flow.swarmflow'},
    {'args': '{}'}, {'script': 'x', 'args': {}}, {'script': 'x', 'permission': 'allow'}])
async def test_invalid_swarmflow_intent_rejects_without_delivery(entry, inputs):
    with pytest.raises((ValueError, TypeError)):
        await entry.call('workflow.start', epoch=entry.service.execution_epoch,
                         fingerprint=None, inputs=inputs)
