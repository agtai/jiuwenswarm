"""Native closed Team tools reach the shared owner and actual configured SDK run.

Trusted activation/context lookup and persisted template selection are fixture
boundaries. TeamManager, assembly, Runner, native input, rails, model objects,
SwarmflowTool and script settlement remain real; only the raw model client is
controlled. This does not claim physical provider or configured product E2E.
"""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
import pytest_asyncio

from openjiuwen.agent_teams.harness import HarnessState
from openjiuwen.agent_teams.paths import configure_openjiuwen_home
from openjiuwen.agent_teams.runtime.manager import TeamRuntimeManager
from openjiuwen.agent_teams.schema.blueprint import TeamAgentSpec
from openjiuwen.core.foundation.llm import AssistantMessage
from openjiuwen.core.foundation.llm.schema.message_chunk import AssistantMessageChunk
from openjiuwen.core.runner import Runner
from openjiuwen.core.runner.runner import GLOBAL_RUNNER
from openjiuwen.harness.schema.deep_agent_spec import DeepAgentSpec

from jiuwenswarm.agents.harness.team import team_manager as team_module
from jiuwenswarm.agents.swarm import assembly
from jiuwenswarm.common.schema.live_voice_contract_v2 import Assurance, ScopeRef
from jiuwenswarm.server.live_voice.native_business_router import NativeBusinessRouter
from jiuwenswarm.server.live_voice.native_business_tools import native_business_proposal_from_function_call
from jiuwenswarm.server.live_voice.native_interaction_contract import NativeInteractionBinding
from jiuwenswarm.server.runtime.session import session_metadata
from jiuwenswarm.server.runtime.session_execution import SessionExecutionService
from jiuwenswarm.server.runtime.team_entity_store import TeamEntityStore


@pytest_asyncio.fixture
async def native_team(tmp_path, monkeypatch):
    configure_openjiuwen_home(str(tmp_path / 'sdk'))
    team_name, session_id = 'nt-' + uuid4().hex[:8], 'ns-' + uuid4().hex[:8]
    project_id = 'project-native-team'
    scope = ScopeRef('user', project_id, session_id, Assurance.AUTHENTICATED)
    folder = tmp_path / session_id
    folder.mkdir()
    spec = TeamAgentSpec(agents={
        'leader': DeepAgentSpec(system_prompt='Configured Native Team leader', model={
            'model_client_config': {'client_provider': 'OpenAI', 'api_key': 'fixture',
                                    'api_base': 'http://127.0.0.1:1'},
            'model_request_config': {'model': 'configured-native-team-model'}}),
        'teammate': DeepAgentSpec()}, team_name=team_name, spawn_mode='inprocess',
        enable_permissions=True, enable_swarmflow=True)
    metadata = dict(session_id=session_id, channel_id='web', project_dir=str(tmp_path),
        project_id=project_id, mode='team', work_mode='work', team_name=team_name,
        team_template_snapshot=spec.model_dump(mode='json'))
    metadata_path = folder / 'metadata.json'
    metadata_path.write_text(json.dumps(metadata), encoding='utf-8')
    monkeypatch.setattr(session_metadata, 'get_agent_sessions_dir', lambda: tmp_path)
    monkeypatch.setattr(TeamEntityStore, 'get', lambda *_: None)
    manager = team_module.TeamManager()
    monkeypatch.setattr(team_module, '_team_manager', manager)
    # Only persisted template selection is supplied. Preflight, enrichment and
    # actual Team creation remain original production implementations.
    monkeypatch.setattr(manager, '_load_session_team_spec', lambda *_, **__: (spec, True))
    config = {'permissions': {'enabled': True, 'schema': 'tiered_policy',
        'permission_mode': 'normal', 'defaults': {'*': 'allow'}, 'rules': [], 'approval_overrides': []}}
    monkeypatch.setattr(team_module, 'get_config', lambda: config)
    monkeypatch.setattr(assembly, 'get_config', lambda: config)
    monkeypatch.setattr('jiuwenswarm.common.config.get_config', lambda: config)
    model_calls = []
    class Client:
        async def invoke(self, **kwargs):
            model_calls.append(kwargs)
            return AssistantMessage(content='Configured Team answered')
        async def stream(self, **kwargs):
            model_calls.append(kwargs)
            yield AssistantMessageChunk(content='Configured Team answered', finish_reason='stop')
    monkeypatch.setattr('openjiuwen.core.foundation.llm.model.create_model_client', lambda **_: Client())
    facade = object()
    def find_agent_exact(**kwargs):
        assert kwargs == dict(channel_id='web', mode='team', project_dir=str(tmp_path), sub_mode=None)
        return facade
    app = SimpleNamespace(find_agent_exact=Mock(side_effect=find_agent_exact),
        pin_agent=Mock(), unpin_agent=Mock())
    service = app.executions = SessionExecutionService(app)
    grants = []
    def authorize(**kwargs):
        assert kwargs['scope'] == scope
        grants.append(kwargs['required_permissions'])
    context = SimpleNamespace(file_path=str(tmp_path), require_usable=Mock(side_effect=authorize))
    current = SimpleNamespace(context=context)
    registry = SimpleNamespace(_agent_manager=app, _stopped=False,
        _p3_composition=SimpleNamespace(_accepting=True, _clock=lambda: 'now'))
    router = NativeBusinessRouter(registry)
    router._require_current_context_route = Mock(return_value=None)
    router._require_context_authority = AsyncMock(return_value=current)
    router._require_work_authority = AsyncMock(return_value=current)
    binding = NativeInteractionBinding(scope, 'interaction', 'activation', 1, 'correlation')
    route = SimpleNamespace(binding=binding, native_p3_authority=SimpleNamespace(
        context=context, principal=SimpleNamespace(require_usable=Mock(return_value=None))))

    def proposal(operation, call_id, **params):
        return native_business_proposal_from_function_call(
            name='jiuwen_' + operation.replace('.', '_'),
            arguments=json.dumps({'request_text': 'Use the configured Team', 'context_id': 'a' * 64, **params}),
            binding=binding, turn_id='turn', response_generation=1,
            provider_event_id='event-' + call_id, provider_call_id=call_id, provider_item_id='item-' + call_id)
    async def call(operation, call_id, **params):
        return await router._team(route, proposal(operation, call_id, **params))

    await Runner.start()
    runtime = TeamRuntimeManager()
    monkeypatch.setattr(GLOBAL_RUNNER, '_team_runtime_manager', runtime)
    try:
        yield SimpleNamespace(**locals())
    finally:
        assert await service.close(timeout=5)
        await asyncio.wait_for(Runner.stop(), 5)


@pytest.mark.asyncio
async def test_native_closed_team_and_workflow_start_use_original_runtime_and_cancel(native_team):
    n = native_team
    before = await n.call('team.list', 'list-before')
    assert before['executions'] == [] and before['configured_team']['available'] is False
    assert n.manager.get_stream_task(n.session_id) is None
    epoch = before['epoch']
    start = n.proposal('team.start', 'start', epoch=epoch, fingerprint=None,
                       instruction='Have the configured team answer')
    receipt = await n.router._team(n.route, start)
    root_id = start.source_identity
    async with asyncio.timeout(15):
        while not receipt['input_accepted'] or not n.model_calls:
            await asyncio.sleep(0.02)
            receipt = await n.call('team.get', 'get-start', epoch=epoch, target_id=root_id)
    entry = n.service.get_internal(n.facade, session_id=n.session_id,
                                   execution_id=root_id, kind='configured_team')
    state = entry.capability_state
    physical = state.producer
    native = state.sdk_owner.agent.harness.get_deep_agent()
    async with asyncio.timeout(3):
        while native.state is not HarnessState.IDLE:
            await asyncio.sleep(0)
    assert state.spec is n.spec and physical is n.manager.get_stream_task(n.session_id)
    assert physical is not entry.task and not physical.done()
    assert state.scope.project_id == n.scope.project_id == n.metadata['project_id']
    assert n.model_calls and all(call.get('model') in (None, 'configured-native-team-model') for call in n.model_calls)
    assert not receipt['business_completed'] and receipt['workflow'] is None
    assert (await n.router._team(n.route, start))['output_execution_id'] == root_id
    assert n.manager.get_stream_task(n.session_id) is physical
    listing = await n.call('team.list', 'list-active')
    assert listing['configured_team']['available'] is True
    assert [item['execution_id'] for item in listing['executions']] == [root_id]

    flow = n.proposal('workflow.start', 'flow', epoch=epoch,
        fingerprint=listing['configured_team']['capability']['spec_fingerprint'],
        inputs={'script': "META = {'name': 'native-flow'}\nasync def run(args):\n    return 'native-script-settled'\n"})
    flow_receipt = await n.router._team(n.route, flow)
    async with asyncio.timeout(10):
        while flow_receipt['workflow'] is None:
            await asyncio.sleep(0.02)
            flow_receipt = await n.call('team.get', 'get-flow', epoch=epoch, target_id=flow.source_identity)
    assert flow_receipt['status'] == 'launched'
    assert flow_receipt['output_execution_id'] == root_id
    assert not flow_receipt['business_completed']
    workflow = flow_receipt['workflow']
    settled = await native.async_tool_runtime.wait(workflow['task_id'], 3)
    assert settled.execution_settled and settled.result == 'native-script-settled'
    assert (await n.router._team(n.route, flow))['workflow'] == workflow
    assert len(native.async_tool_runtime.registry) == 1
    assert n.manager.get_stream_task(n.session_id) is physical
    assert frozenset({'task.execute', 'project.write'}) in n.grants

    cancelled = await n.call('team.cancel', 'cancel', epoch=epoch, target_id=root_id)
    assert cancelled['cancel_requested']
    async with asyncio.timeout(5):
        while not physical.done() or not entry.task.done():
            await asyncio.sleep(0.01)
    observed = await n.call('team.get', 'get-cancelled', epoch=epoch, target_id=root_id)
    assert observed['producer_exited'] and not observed['business_completed']
    assert observed['cleanup_outcome'] == 'unproven'
