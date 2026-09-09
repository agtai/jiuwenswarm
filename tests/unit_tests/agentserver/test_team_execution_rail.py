"""Configured Team guard retains actual model/tool/permission implementations."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from openjiuwen.agent_teams.harness.async_tools import AsyncToolRuntime
from openjiuwen.agent_teams.rails.team_permission_rail import TeamPermissionRail
from openjiuwen.agent_teams.schema.blueprint import TeamAgentSpec
from openjiuwen.agent_teams.workflow.concurrency import ConcurrencyGovernor, ConcurrencyLimits
from openjiuwen.agent_teams.workflow.tool_swarmflow import SwarmflowTool
from openjiuwen.core.single_agent.agents.react_agent import ReActAgent
from openjiuwen.core.single_agent.rail.base import AgentRail
from openjiuwen.core.single_agent.schema.agent_card import AgentCard
from jiuwenswarm.agents.harness.team.rails.team_execution_rail import TeamExecutionRail
from jiuwenswarm.server.runtime.team_execution import _Intent, _TeamRun, SwarmflowStartIntent
from jiuwenswarm.server.runtime.team_execution_capabilities import TeamExecutionScope
from jiuwenswarm.server.runtime.session import session_metadata

pytestmark = pytest.mark.asyncio


@pytest.fixture
def run(tmp_path, monkeypatch):
    scope = TeamExecutionScope('web', 'team-session', str(tmp_path), None, 'team', 'work')
    path = tmp_path / scope.session_id
    path.mkdir()
    identity = dict(session_id=scope.session_id, channel_id=scope.channel_id,
                    project_dir=scope.project_dir, project_id=None, mode='team', work_mode='work', team_name='team')
    (path / 'metadata.json').write_text(json.dumps(identity), encoding='utf-8')
    monkeypatch.setattr(session_metadata, 'get_agent_sessions_dir', lambda: tmp_path)
    state = _TeamRun(scope, lambda _: None, None, None, spec=TeamAgentSpec(agents={}, team_name='team'),
                     identity=identity, cold_start=True)
    return state


@pytest.mark.parametrize('permission', ['allow', 'deny'])
async def test_explicit_intent_uses_real_permission_tool_and_engine(run, tmp_path, monkeypatch, permission):
    from openjiuwen.agent_teams.workflow import runner as workflow_runner

    run.entry = SimpleNamespace(task=asyncio.current_task())
    script = tmp_path / 'workflow.py'
    script.write_text("META = {'name': 'team-rail'}\nasync def run(args):\n    return 'engine-finished'\n")
    monkeypatch.setattr(workflow_runner, '_resolve_journal_path', lambda *_: str(tmp_path / 'journal.jsonl'))
    runtime = AsyncToolRuntime(inject=AsyncMock())
    native = SimpleNamespace(model=None, launch_async_tool=runtime.launch,
                             async_tool_runtime=runtime, background_task_controller=None)
    tool = SwarmflowTool(parent_agent=native, messager=None, team_name='team', model_resolver=None,
                        concurrency_governor=ConcurrencyGovernor(
                            ConcurrencyLimits(max_workflows=1, max_agents_total=1), agents_per_run_cap=1))
    leader = ReActAgent(AgentCard(id='configured-leader', name='configured-leader'))
    leader.ability_manager.add_ability(tool.card, tool)
    intent = _Intent({'script_path': str(script)})
    run.intent = run.initial_intent = intent
    model_lookup = Mock(side_effect=AssertionError('no implicit model fallback'))
    monkeypatch.setattr(leader, '_get_llm', model_lookup)

    class FinishAfterReceipt(AgentRail):
        async def before_model_call(self, ctx):
            if intent.observed.is_set():
                ctx.request_force_finish({'output': 'control observed', 'result_type': 'answer'})

    await leader.register_rail(FinishAfterReceipt())
    await leader.register_rail(TeamPermissionRail(config={
        'enabled': True, 'schema': 'tiered_policy', 'permission_mode': 'normal',
        'defaults': {'*': permission}, 'rules': [], 'approval_overrides': [],
    }))
    await leader.register_rail(TeamExecutionRail(run, role='leader', member_name='leader'))
    try:
        await asyncio.wait_for(leader.invoke({'query': 'explicit host intent'}), 5)
        model_lookup.assert_not_called()
        assert run.input_accepted
        if permission == 'allow':
            assert intent.receipt['run_id'].startswith('wf_')
            record = await runtime.wait(intent.receipt['task_id'], 3)
            assert record.execution_settled and record.result == 'engine-finished'
        else:
            assert intent.receipt is None and intent.failure == 'swarmflow_tool_not_launched'
            assert runtime.registry == {}
    finally:
        for task in list(runtime._tasks.values()):
            if not task.done():
                task.cancel()
        await asyncio.gather(*runtime._tasks.values(), return_exceptions=True)
        leader.ability_manager.teardown_tools()


@pytest.mark.parametrize('values', [{}, {'script': 'a', 'script_path': 'b'}, {'script': ''},
                                   {'script': 'a', 'args': {}}, {'script': 'a\x00b'}])
async def test_closed_intent_shape(values):
    with pytest.raises(ValueError):
        SwarmflowStartIntent(**values)


async def test_fake_context_cannot_create_authority():
    with pytest.raises(ValueError, match='authority_unavailable'):
        TeamExecutionRail({'scope': 'trusted'}, role='leader')


class RecordingModelClient:
    def __init__(self, text):
        self.text = text
        self.calls = []

    async def invoke(self, **kwargs):
        from openjiuwen.core.foundation.llm import AssistantMessage
        self.calls.append(kwargs)
        return AssistantMessage(content=self.text)

    async def stream(self, **kwargs):
        if False:
            yield None


async def test_warm_native_revocation_does_not_change_original_text_model_or_tool(run, monkeypatch):
    from openjiuwen.core.foundation.llm import Model, ModelClientConfig, ModelRequestConfig
    from openjiuwen.core.runner import Runner
    from openjiuwen.core.runner.callback import AsyncCallbackFramework

    client = RecordingModelClient('original Text continues')
    monkeypatch.setattr(Runner, 'callback_framework', AsyncCallbackFramework())
    monkeypatch.setattr('openjiuwen.core.foundation.llm.model.create_model_client', lambda **_: client)
    original = Model(model_client_config=ModelClientConfig(client_provider='OpenAI', api_key='test',
                    api_base='http://127.0.0.1:1'), model_config=ModelRequestConfig(model='configured-member'))
    leader = ReActAgent(AgentCard(id='warm-leader', name='warm-leader'))
    leader.set_llm(original)
    run.entry = SimpleNamespace(task=asyncio.current_task())
    run.preserve_original = True
    run.input_accepted = True
    def revoked(_):
        raise PermissionError('native grant revoked')
    run.before_effect = revoked
    intent = _Intent({'script': 'must not execute'}, revoked)
    intent.admitted.set()
    run.intent = intent
    rail = TeamExecutionRail(run, role='leader', control_only=True)
    await leader.register_rail(rail)
    response = await leader.invoke({'query': 'existing Text work'})
    assert response['output'] == 'original Text continues'
    assert len(client.calls) == 1
    assert leader._get_llm() is original
    assert intent.observed.is_set() and intent.receipt is None
    assert intent.before_effect is None
    # A later ordinary Text tool remains governed by its original rails.
    context = SimpleNamespace(agent=leader, inputs=SimpleNamespace(
        tool_call=SimpleNamespace(id='original-text-tool'), tool_name='anything', tool_args={}))
    await rail.before_tool_call(context)
    assert not intent.claimed


async def test_cold_member_model_keeps_original_client_and_checks_after_sdk_hook(run, monkeypatch):
    from openjiuwen.core.foundation.llm import Model, ModelClientConfig, ModelRequestConfig
    from openjiuwen.core.runner import Runner
    from openjiuwen.core.runner.callback import AsyncCallbackFramework
    from openjiuwen.core.runner.callback.events import LLMCallEvents
    from jiuwenswarm.agents.harness.team.rails.team_execution_rail import ConfiguredTeamModel

    framework = AsyncCallbackFramework()
    monkeypatch.setattr(Runner, 'callback_framework', framework)
    client = RecordingModelClient('member result')
    monkeypatch.setattr('openjiuwen.core.foundation.llm.model.create_model_client', lambda **_: client)
    model = Model(model_client_config=ModelClientConfig(client_provider='OpenAI', api_key='test',
                  api_base='http://127.0.0.1:1'), model_config=ModelRequestConfig(model='configured-member'))
    allowed = True
    def guard():
        if not allowed:
            raise PermissionError('revoked')
    proxy = ConfiguredTeamModel(model, guard)
    await proxy.invoke(messages=[])
    assert len(client.calls) == 1 and proxy._client is model._client
    assert proxy.model_config is model.model_config
    async def revoke(*args, **kwargs):
        nonlocal allowed
        await asyncio.sleep(0)
        allowed = False
    await framework.register(LLMCallEvents.LLM_INVOKE_INPUT, revoke)
    with pytest.raises(PermissionError, match='revoked'):
        await proxy.invoke(messages=[])
    assert len(client.calls) == 1


async def test_real_member_assembly_and_local_derived_context_preserve_guard_and_models(run, monkeypatch):
    from jiuwenswarm.agents.swarm import assembly
    from jiuwenswarm.agents.swarm.context import SwarmBuildContext
    from jiuwenswarm.agents.swarm.providers.member_rails import _build_team_execution_rail
    from jiuwenswarm.agents.harness.team.rails.team_execution_rail import TEAM_EXECUTION_CONTEXT, TEAM_EXECUTION_RAIL
    from openjiuwen.harness.schema.deep_agent_spec import DeepAgentSpec

    run.entry = SimpleNamespace(task=asyncio.current_task())
    member = DeepAgentSpec(model={'model_client_config': {'client_provider': 'OpenAI', 'api_key': 'test',
                             'api_base': 'http://127.0.0.1:1'},
                         'model_request_config': {'model': 'configured-member'}})
    spec = TeamAgentSpec(agents={'leader': member, 'teammate': member.model_copy(deep=True)},
                        team_name='team', spawn_mode='inprocess', enable_permissions=True)
    models = {role: value.model.model_dump(mode='json') for role, value in spec.agents.items()}
    monkeypatch.setattr(assembly, 'get_config', lambda: {})
    assembly.enrich_team_spec_for_swarm(spec, session_id=run.scope.session_id, mode='team',
        project_dir=run.scope.project_dir, channel_id='web', execution_context=run)
    assert spec.build_context.extras[TEAM_EXECUTION_CONTEXT] is run
    for role, member_spec in spec.agents.items():
        assert member_spec.model.model_dump(mode='json') == models[role]
        assert TEAM_EXECUTION_RAIL in [rail.type for rail in member_spec.rails]
        derived = spec.build_context.derive(role=role, member_name=role + '-1')
        rail = _build_team_execution_rail({}, derived)
        assert rail.execution is run and rail.role == role
    # Serialized remote seeds never acquire the in-process grant.
    seed = spec.build_context.to_seed()
    rebuilt = SwarmBuildContext.from_seed(seed, config={}, trajectory_registry=None)
    with pytest.raises(ValueError, match='authority_unavailable'):
        _build_team_execution_rail({}, rebuilt)
    assert TEAM_EXECUTION_CONTEXT not in seed


async def test_fake_assembly_authority_rejects_before_spec_or_provider_mutation(monkeypatch):
    from jiuwenswarm.agents.swarm import assembly
    spec = TeamAgentSpec(agents={'leader': {}}, team_name='team')
    before = spec.model_dump(mode='json')
    register = Mock(side_effect=AssertionError('no provider registration'))
    monkeypatch.setattr(assembly, 'register_swarm_providers', register)
    with pytest.raises(ValueError, match='authority_unavailable'):
        assembly.enrich_team_spec_for_swarm(spec, session_id='s', mode='team',
                                           execution_context={'trusted': True})
    assert spec.model_dump(mode='json') == before
    register.assert_not_called()


async def test_actual_member_harness_rebuild_keeps_same_inprocess_guard(run):
    from openjiuwen.core.runner import Runner
    from openjiuwen.agent_teams.harness.team_harness import TeamHarness
    from openjiuwen.agent_teams.schema.team import TeamRole
    from openjiuwen.harness.schema.deep_agent_spec import DeepAgentSpec, RailSpec
    from jiuwenswarm.agents.swarm import register_swarm_providers
    from jiuwenswarm.agents.swarm.context import SwarmBuildContext
    from jiuwenswarm.agents.harness.team.rails.team_execution_rail import TEAM_EXECUTION_CONTEXT, TEAM_EXECUTION_RAIL

    run.entry = SimpleNamespace(task=asyncio.current_task())
    register_swarm_providers()
    base = SwarmBuildContext(session_id=run.scope.session_id)
    base.extras[TEAM_EXECUTION_CONTEXT] = run
    member_context = base.derive(role='teammate', member_name='actual-member')
    spec = DeepAgentSpec(card=AgentCard(id='real-member', name='real-member'),
        model={'model_client_config': {'client_provider': 'OpenAI', 'api_key': 'test',
                                       'api_base': 'http://127.0.0.1:1'},
               'model_request_config': {'model': 'configured-member'}},
        rails=[RailSpec(type=TEAM_EXECUTION_RAIL)])
    await Runner.start()
    harness = TeamHarness.build(agent_spec=spec, role=TeamRole.TEAMMATE,
                                member_name='actual-member', build_context=member_context)
    try:
        await harness.start()
        first = harness.get_deep_agent()
        first_rail = harness.find_rails(TeamExecutionRail)[0]
        assert first_rail.execution is run
        await harness.stop()
        await harness.start()
        second = harness.get_deep_agent()
        second_rail = harness.find_rails(TeamExecutionRail)[0]
        assert second is not first and second_rail is not first_rail
        assert second_rail.execution is run
        assert harness._agent_spec.model.model_request_config.model_name == 'configured-member'
        assert harness.build_context.extras[TEAM_EXECUTION_CONTEXT] is run
    finally:
        await harness.stop()
        await Runner.stop()


async def test_unsupported_configuration_rejects_before_record_or_team_creation(run, monkeypatch):
    from jiuwenswarm.server.runtime import team_execution as execution
    from jiuwenswarm.server.runtime.session_execution import SessionExecutionService
    from jiuwenswarm.agents.harness.team import team_manager
    from jiuwenswarm.common.schema.agent import AgentRequest

    facade = object()
    manager = SimpleNamespace(find_agent_exact=Mock(return_value=facade),
                              pin_agent=Mock(), unpin_agent=Mock())
    service = SessionExecutionService(manager)
    def unsupported(*_):
        raise ValueError('configured_team_remote_execution_unsupported')
    monkeypatch.setattr(execution, '_preflight', unsupported)
    monkeypatch.setattr(team_manager, '_team_manager', None)
    create = Mock(side_effect=AssertionError('must not prepare another Team'))
    monkeypatch.setattr(team_manager, 'get_team_manager', create)
    req = AgentRequest(request_id='unsupported', session_id=run.scope.session_id,
                       channel_id=run.scope.channel_id, params={'query': 'explicit request'})
    with pytest.raises(ValueError, match='remote_execution_unsupported'):
        await execution.start_configured_team(service, facade, req, scope=run.scope,
                                               before_effect=lambda _: None)
    assert not service.list_internal(facade, session_id=run.scope.session_id, kind='configured_team')
    manager.pin_agent.assert_not_called()
    create.assert_not_called()
    await service.close()


async def test_original_callback_framework_cannot_swallow_first_model_authority_failure(run, monkeypatch):
    run.entry = SimpleNamespace(task=asyncio.current_task())
    def denied(_):
        raise PermissionError('team grant revoked before model')
    run.before_effect = denied
    leader = ReActAgent(AgentCard(id='guarded-model-leader', name='guarded-model-leader'))
    model_lookup = Mock(side_effect=AssertionError('forbidden model fallback'))
    monkeypatch.setattr(leader, '_get_llm', model_lookup)
    await leader.register_rail(TeamExecutionRail(run, role='leader'))
    with pytest.raises(PermissionError, match='team grant revoked before model'):
        await asyncio.wait_for(leader.invoke({'query': 'configured input'}), 3)
    model_lookup.assert_not_called()
    assert not run.input_accepted
