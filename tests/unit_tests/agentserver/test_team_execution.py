"""Shared Team records retain the real manager producer and SDK input owner.

SDK activation is prepared locally; actual input routing, native supervisor,
TeamManager readers, and SessionExecutionService publication remain real. The
SDK's deterministic lower ReAct fixture avoids physical provider calls.
"""
import asyncio
import importlib.util
import inspect
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
import pytest_asyncio

from openjiuwen.agent_teams.agent.blueprint import TeamAgentBlueprint
from openjiuwen.agent_teams.agent.team_agent import TeamAgent
from openjiuwen.agent_teams.harness import NativeHarness, HarnessState
from openjiuwen.agent_teams.harness.team_harness import TeamHarness
from openjiuwen.agent_teams.runtime.manager import TeamRuntimeManager
from openjiuwen.agent_teams.runtime.pool import ActiveTeam
from openjiuwen.agent_teams.schema.blueprint import TeamAgentSpec
from openjiuwen.harness.schema.deep_agent_spec import DeepAgentSpec
from openjiuwen.agent_teams.schema.team import TeamRuntimeContext, TeamSpec, TeamRole
from openjiuwen.core.runner import Runner
from openjiuwen.core.runner.runner import GLOBAL_RUNNER
from jiuwenswarm.agents.harness.team import team_manager as team_module
from jiuwenswarm.agents.swarm.context import SwarmBuildContext
from jiuwenswarm.common.schema.agent import AgentRequest
from jiuwenswarm.server.runtime.session import session_metadata
from jiuwenswarm.server.runtime.session_execution import SessionExecutionService
from jiuwenswarm.server.runtime import team_execution as execution
from jiuwenswarm.server.runtime.team_execution_capabilities import TeamExecutionScope

pytestmark = pytest.mark.asyncio


def sdk_fixture():
    root = Path(inspect.getfile(NativeHarness)).parents[3]
    spec = importlib.util.spec_from_file_location('_team_sdk_fixture',
        root / 'tests/unit_tests/agent_teams/harness/fixtures.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest_asyncio.fixture
async def warm(tmp_path, monkeypatch):
    helpers = sdk_fixture()
    await Runner.start()
    leader_spec = DeepAgentSpec(card=helpers.make_card('configured-leader'), system_prompt='Team fixture',
        model={'model_client_config': {'client_provider': 'OpenAI', 'api_key': 'test',
                                       'api_base': 'http://127.0.0.1:1'},
               'model_request_config': {'model': 'configured-member'}})
    native = NativeHarness(leader_spec)
    fake = await helpers.start_harness(native)
    native_reader = asyncio.create_task(helpers.drain_outputs(native, []))
    scope = TeamExecutionScope('web', 'session-team', str(tmp_path), 'project', 'team', 'work')
    folder = tmp_path / scope.session_id
    folder.mkdir()
    metadata = dict(session_id=scope.session_id, channel_id=scope.channel_id,
                    project_dir=scope.project_dir, project_id=scope.project_id,
                    mode='team', work_mode='work', team_name='existing-team')
    (folder / 'metadata.json').write_text(json.dumps(metadata), encoding='utf-8')
    monkeypatch.setattr(session_metadata, 'get_agent_sessions_dir', lambda: tmp_path)
    spec = TeamAgentSpec(agents={'leader': leader_spec, 'teammate': DeepAgentSpec()},
                         team_name='existing-team', spawn_mode='inprocess')
    spec.build_context = SwarmBuildContext(session_id=scope.session_id)
    context = TeamRuntimeContext(team_spec=TeamSpec(team_name=spec.team_name, display_name='Configured Team'))
    team = TeamAgent(helpers.make_card('existing-team'))
    team._configurator._blueprint = TeamAgentBlueprint(team.card, spec, context, 'en')
    team._configurator.harness = TeamHarness(spec.agents['leader'], spec.build_context, native,
                                              role=TeamRole.LEADER, member_name='leader')
    runtime = TeamRuntimeManager()
    pool_entry = ActiveTeam(spec.team_name, team, scope.session_id)
    await runtime.pool.add(pool_entry)
    monkeypatch.setattr(GLOBAL_RUNNER, '_team_runtime_manager', runtime)
    manager = team_module.TeamManager()
    manager.commit_runtime_ready(scope.session_id, spec.team_name)
    monkeypatch.setattr(team_module, '_team_manager', manager)
    end = asyncio.Event()
    async def physical_stream():
        await end.wait()
    producer = asyncio.create_task(physical_stream())
    manager.register_stream_task(scope.session_id, producer)
    original_reader = asyncio.Queue()
    manager.add_waiter(scope.session_id, 'old-text', original_reader)
    facade = object()
    app = SimpleNamespace(find_agent_exact=Mock(return_value=facade), pin_agent=Mock(), unpin_agent=Mock())
    service = SessionExecutionService(app)
    # Configuration-loading I/O is outside this live-owner seam; the real
    # readonly capability still validates its original spec/runtime identity.
    monkeypatch.setattr(execution, '_preflight', lambda *_: None)
    state = SimpleNamespace(scope=scope, facade=facade, service=service, app=app, manager=manager,
        native=native, fake=fake, producer=producer, end=end, original_reader=original_reader,
        spec=spec, team=team, entry=pool_entry, runtime=runtime, helpers=helpers)
    yield state
    end.set()
    await asyncio.gather(producer, return_exceptions=True)
    await service.close(timeout=2)
    await native.stop()
    await native_reader
    runtime.pool._teams.clear()
    await Runner.stop()


def request(warm, rid='native', query='new input'):
    return AgentRequest(request_id=rid, channel_id=warm.scope.channel_id,
                        session_id=warm.scope.session_id, params={'query': query})


async def test_warm_shared_service_retains_text_reader_replay_and_physical_owner(warm):
    w = warm
    original_spec = w.spec.model_dump(mode='json')
    original_context = dict(w.spec.build_context.extras)
    receipt = await execution.start_configured_team(w.service, w.facade, request(w),
        scope=w.scope, before_effect=lambda _: None)
    assert receipt['input_accepted'] and not receipt['business_completed']
    assert w.manager.get_stream_task(w.scope.session_id) is w.producer
    assert not w.producer.done()
    assert await w.helpers.wait_for_state(w.native, HarnessState.IDLE)
    replay = await execution.start_configured_team(w.service, w.facade, request(w),
        scope=w.scope, before_effect=lambda _: None)
    assert replay['output_execution_id'] == receipt['output_execution_id']
    assert len(w.fake.invocations) == 1
    event = {'event_type': 'chat.delta', 'content': 'same source'}
    await w.manager.broadcast_event(w.scope.session_id, event)
    assert await w.original_reader.get() == event
    async with asyncio.timeout(2):
        while not w.service.list_internal(w.facade, session_id=w.scope.session_id,
                    kind='configured_team')[0].events:
            await asyncio.sleep(0)
    assert w.spec.model_dump(mode='json') == original_spec
    assert w.spec.build_context.extras == original_context
    assert len(execution.list_configured_team_executions(w.service, w.facade,
        scope=w.scope, before_effect=lambda _: None)) == 1


async def test_warm_new_control_does_not_inherit_revoked_previous_native_grant(warm):
    w = warm
    allowed = True
    def first(_):
        if not allowed:
            raise PermissionError('old Native grant revoked')
    assert (await execution.start_configured_team(w.service, w.facade, request(w),
        scope=w.scope, before_effect=first))['input_accepted']
    assert await w.helpers.wait_for_state(w.native, HarnessState.IDLE)
    allowed = False
    result = await execution.start_configured_team(w.service, w.facade, request(w, 'second'),
        scope=w.scope, before_effect=lambda _: None)
    assert result['input_accepted'] and result['output_execution_id'] == 'native'
    assert await w.helpers.wait_for_state(w.native, HarnessState.IDLE)
    assert len(w.fake.invocations) == 2 and not w.producer.done()


async def test_exact_cancel_never_targets_replacement_producer(warm):
    w = warm
    await execution.start_configured_team(w.service, w.facade, request(w), scope=w.scope,
                                          before_effect=lambda _: None)
    replacement = asyncio.create_task(asyncio.Event().wait())
    w.manager.register_stream_task(w.scope.session_id, replacement)
    try:
        result = await execution.cancel_configured_team_execution(w.service, w.facade,
            request(w, 'cancel'), scope=w.scope, execution_id='native', before_effect=lambda _: None)
        assert not result['cancel_requested']
        assert not replacement.done() and not w.producer.done()
    finally:
        replacement.cancel()
        await asyncio.gather(replacement, return_exceptions=True)


async def test_observed_control_id_cancels_only_its_original_team_producer(warm):
    w = warm
    root = await execution.start_configured_team(w.service, w.facade, request(w),
        scope=w.scope, before_effect=lambda _: None)
    assert await w.helpers.wait_for_state(w.native, HarnessState.IDLE)
    control = await execution.start_configured_team(w.service, w.facade, request(w, 'followup'),
        scope=w.scope, before_effect=lambda _: None)
    assert control['execution_id'] == 'followup' and control['output_execution_id'] == root['execution_id']
    assert await w.helpers.wait_for_state(w.native, HarnessState.IDLE)
    result = await execution.cancel_configured_team_execution(w.service, w.facade,
        request(w, 'cancel'), scope=w.scope, execution_id=control['execution_id'], before_effect=lambda _: None)
    assert result['cancel_requested'] and result['execution_id'] == 'followup'
    assert result['output_execution_id'] == root['execution_id'] and w.producer.cancelled()
    assert len(w.fake.invocations) == 2


@pytest.mark.parametrize('flow_permission', [None, 'allow', 'host_revoke'])
async def test_cold_real_manager_assembly_runner_and_member_model(tmp_path, monkeypatch, flow_permission):
    from jiuwenswarm.agents.swarm import assembly
    from openjiuwen.core.foundation.llm import AssistantMessage
    from openjiuwen.core.foundation.llm.schema.message_chunk import AssistantMessageChunk
    from openjiuwen.agent_teams.paths import configure_openjiuwen_home

    configure_openjiuwen_home(str(tmp_path / 'sdk'))
    team_name = 'ct-' + uuid4().hex[:8]
    scope = TeamExecutionScope('web', 'cs-' + uuid4().hex[:8], str(tmp_path), None, 'team', 'work')
    folder = tmp_path / scope.session_id
    folder.mkdir()
    metadata = dict(session_id=scope.session_id, channel_id=scope.channel_id,
        project_dir=scope.project_dir, project_id=None, mode='team', work_mode='work', team_name=team_name)
    (folder / 'metadata.json').write_text(json.dumps(metadata), encoding='utf-8')
    monkeypatch.setattr(session_metadata, 'get_agent_sessions_dir', lambda: tmp_path)
    calls = []
    allowed = True
    tool_finished = asyncio.Event()
    def guard(_):
        if not allowed:
            raise PermissionError('host grant revoked')
    if flow_permission == 'host_revoke':
        from openjiuwen.core.single_agent.rail.base import AgentRail
        original_ready = execution._TeamRun.runtime_ready
        class RevokeAtTool(AgentRail):
            priority = 10000
            async def before_tool_call(self, ctx):
                nonlocal allowed
                if ctx.inputs.tool_name == 'swarmflow':
                    allowed = False
            async def after_tool_call(self, ctx):
                if ctx.inputs.tool_name == 'swarmflow':
                    tool_finished.set()
        async def runtime_ready(state):
            await original_ready(state)
            await state.sdk_owner.agent.harness.register_rail(RevokeAtTool())
        monkeypatch.setattr(execution._TeamRun, 'runtime_ready', runtime_ready)
    class Client:
        async def invoke(self, **kwargs):
            calls.append(kwargs)
            return AssistantMessage(content='configured leader answered')
        async def stream(self, **kwargs):
            calls.append(kwargs)
            yield AssistantMessageChunk(content='configured leader answered', finish_reason='stop')
    monkeypatch.setattr('openjiuwen.core.foundation.llm.model.create_model_client', lambda **_: Client())
    spec = TeamAgentSpec(agents={'leader': DeepAgentSpec(system_prompt='Configured leader',
        model={'model_client_config': {'client_provider': 'OpenAI', 'api_key': 'test',
                                       'api_base': 'http://127.0.0.1:1'},
               'model_request_config': {'model': 'actual-team-model'}}), 'teammate': DeepAgentSpec()},
        team_name=team_name, spawn_mode='inprocess', enable_permissions=flow_permission is not None,
        enable_swarmflow=flow_permission is not None)
    manager = team_module.TeamManager()
    monkeypatch.setattr(team_module, '_team_manager', manager)
    config = {'permissions': {'enabled': True, 'schema': 'tiered_policy', 'permission_mode': 'normal',
        'defaults': {'*': 'allow'}, 'rules': [], 'approval_overrides': []}}
    monkeypatch.setattr(team_module, 'get_config', lambda: config)
    monkeypatch.setattr(assembly, 'get_config', lambda: config)
    # Persisted template lookup is the fixture boundary; the original manager's
    # enrichment, SDK activation, actual member/harness/model and output remain.
    monkeypatch.setattr(manager, '_load_session_team_spec', lambda *_, **__: (spec, True))
    monkeypatch.setattr(execution, '_preflight', lambda *_: None)
    facade = object()
    app = SimpleNamespace(find_agent_exact=Mock(return_value=facade), pin_agent=Mock(), unpin_agent=Mock())
    service = SessionExecutionService(app)
    await Runner.start()
    runtime = TeamRuntimeManager()
    monkeypatch.setattr(GLOBAL_RUNNER, '_team_runtime_manager', runtime)
    try:
        req = AgentRequest(request_id='cold', channel_id='web', session_id=scope.session_id,
                           params={'query': 'Use the configured team'})
        intent = execution.SwarmflowStartIntent(script="META = {'name': 'actual-cold-flow'}\nasync def run(args):\n    return 'actual-script-finished'\n") if flow_permission else None
        receipt = await execution.start_configured_team(service, facade, req, scope=scope,
                                                       before_effect=guard, swarmflow=intent)
        entry = service.get_internal(facade, session_id=scope.session_id,
                                     execution_id='cold', kind='configured_team')
        async with asyncio.timeout(15):
            while (not receipt['input_accepted'] or (not calls if intent is None else
                   not entry.capability_state.initial_intent.observed.is_set())) and not receipt['producer_exited']:
                await asyncio.sleep(0.02)
                receipt = execution.get_configured_team_execution(service, facade, scope=scope,
                    execution_id='cold', before_effect=lambda _: None)
        assert receipt['input_accepted'], receipt
        if flow_permission == 'allow':
            assert receipt['workflow'] is not None, receipt
            native = entry.capability_state.sdk_owner.agent.harness.get_deep_agent()
            settled = await native.async_tool_runtime.wait(receipt['workflow']['task_id'], 3)
            assert settled.execution_settled and settled.result == 'actual-script-finished'
        elif flow_permission == 'host_revoke':
            await asyncio.wait_for(tool_finished.wait(), 3)
            assert receipt['workflow'] is None
            assert entry.capability_state.initial_intent.failure == 'host grant revoked'
            native = entry.capability_state.sdk_owner.agent.harness.get_deep_agent()
            async with asyncio.timeout(3):
                while native.state is not HarnessState.IDLE:
                    await asyncio.sleep(0)
            assert native.async_tool_runtime.registry == {}
        else:
            assert calls and all(call.get('model') in (None, 'actual-team-model') for call in calls)
        assert entry.capability_state.spec is spec
        assert entry.capability_state.producer is not entry.task
        assert not receipt['business_completed']
    finally:
        try:
            assert await service.close(timeout=5)
        finally:
            await asyncio.wait_for(Runner.stop(), 5)


async def test_close_cancels_original_team_when_queue_result_completes_in_same_tick(tmp_path, monkeypatch):
    """The real Service/Team reader must propagate cancel to its physical owner.

    Configuration and SDK activation are controlled; the original _produce,
    managed reader, Service.close and physical Task cleanup remain in the path.
    """
    from jiuwenswarm.server.runtime.agent_adapter import team_helpers
    from jiuwenswarm.server.runtime.team_execution_capabilities import ConfiguredTeamUnavailable

    facade = object()
    app = SimpleNamespace(pin_agent=Mock(), unpin_agent=Mock())
    service = SessionExecutionService(app)
    scope = TeamExecutionScope('web', 'reader-race', str(tmp_path), None, 'team', 'work')
    metadata = dict(session_id=scope.session_id, channel_id='web', project_dir=str(tmp_path),
        project_id=None, mode='team', work_mode='work', team_name='reader-race-team')
    spec = SimpleNamespace(team_name='reader-race-team')
    physical_closed, release_physical, close_started = asyncio.Event(), asyncio.Event(), asyncio.Event()
    physical = close_task = None

    async def physical_run():
        try:
            await release_physical.wait()
        finally:
            physical_closed.set()

    async def close_service():
        close_started.set()
        return await service.close(timeout=0.2)

    class CompletingQueue(asyncio.Queue):
        async def get(self):
            nonlocal close_task
            item = await super().get()
            if close_task is None:
                # For wait_for(queue.get()), close runs after the child get Task
                # completes but before its parent resumes. This fixes the race
                # ordering without relying on sleeps or repeated attempts.
                close_task = asyncio.create_task(close_service())
            return item

    queue = CompletingQueue()
    queue.put_nowait({'event_type': 'chat.delta', 'content': 'original event'})
    manager = SimpleNamespace(get_stream_task=lambda _: None, remove_waiter=Mock())

    async def load_spec(*args, **kwargs):
        return spec

    async def unavailable(*args, **kwargs):
        raise ConfiguredTeamUnavailable('controlled cold fixture')

    async def start_round(*args, **kwargs):
        nonlocal physical
        physical = asyncio.create_task(physical_run())
        kwargs['execution'].producer = physical
        return queue

    manager.get_swarm_enriched_team_spec = load_spec
    monkeypatch.setattr(session_metadata, '_read_metadata', lambda *_, **__: dict(metadata))
    monkeypatch.setattr(team_module, 'get_team_manager', lambda *_: manager)
    monkeypatch.setattr(execution, 'resolve_configured_team', unavailable)
    monkeypatch.setattr(execution, '_preflight', lambda *_: None)
    monkeypatch.setattr(execution, '_configuration_fingerprint', lambda _: 'stable-fixture')
    monkeypatch.setattr(GLOBAL_RUNNER, '_team_runtime_manager', None)
    monkeypatch.setattr(team_helpers, '_start_team_stream_round', start_round)
    state = execution._TeamRun(scope=scope, before_effect=lambda _: None, service=service, agent=facade)
    req = AgentRequest(request_id='race', channel_id='web', session_id=scope.session_id,
        params={'query': 'original query', 'expected_fingerprint': None})
    entry = service.start_internal(facade, req, kind='configured_team',
        producer=execution._produce, capability_state=state)
    try:
        async with asyncio.timeout(1):
            await close_started.wait()
            assert await asyncio.shield(close_task)
        assert entry.cancellation_requested and entry.task.done() and entry.task.cancelled()
        assert physical.done() and physical.cancelled() and physical_closed.is_set()
        manager.remove_waiter.assert_called_once_with(scope.session_id, req.request_id)
        app.unpin_agent.assert_called_once_with(facade)
    finally:
        # Even the original broken reader must not leave pytest teardown hung.
        # Its first result is consumed, so this cleanup interrupts a pending get.
        if not entry.task.done():
            entry.task.cancel()
        if physical is not None and not physical.done():
            physical.cancel()
        owned = [entry.task, *([physical] if physical is not None else [])]
        if close_task is not None:
            owned.append(close_task)
        async with asyncio.timeout(1):
            await asyncio.gather(*owned, return_exceptions=True)
