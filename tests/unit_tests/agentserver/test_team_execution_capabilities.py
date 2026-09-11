"""Read-only configured Team binding against real SDK owners and metadata files."""

import asyncio
import dataclasses
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import pytest_asyncio

from openjiuwen.agent_teams.agent.blueprint import TeamAgentBlueprint
from openjiuwen.agent_teams.agent.team_agent import TeamAgent
from openjiuwen.agent_teams.runtime.manager import TeamRuntimeManager
from openjiuwen.agent_teams.runtime.pool import ActiveTeam, RuntimeState
from openjiuwen.agent_teams.schema.blueprint import TeamAgentSpec
from openjiuwen.agent_teams.schema.team import TeamRuntimeContext, TeamSpec
from openjiuwen.core.runner import runner as runner_module
from openjiuwen.core.single_agent.schema.agent_card import AgentCard
from jiuwenswarm.agents.harness.team import team_manager as team_module
from jiuwenswarm.server.runtime.session import session_metadata
from jiuwenswarm.server.runtime.team_execution_capabilities import (
    ConfiguredTeamUnavailable, TeamExecutionScope, inspect_configured_team,
    resolve_configured_team, validate_configured_team_binding,
)

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def configured(tmp_path, monkeypatch):
    scope = TeamExecutionScope('web', 'session-a', str(tmp_path), 'project-a', 'team', 'work')
    folder = tmp_path / 'sessions' / scope.session_id
    folder.mkdir(parents=True)
    path = folder / 'metadata.json'
    metadata = dict(session_id=scope.session_id, channel_id=scope.channel_id,
                    project_dir=scope.project_dir, project_id=scope.project_id,
                    mode='team', work_mode='work', team_name='team-a')
    path.write_text(json.dumps(metadata), encoding='utf-8')
    monkeypatch.setattr(session_metadata, 'get_agent_sessions_dir', lambda: folder.parent)
    manager = team_module.TeamManager()
    manager.commit_runtime_ready(scope.session_id, 'team-a')
    monkeypatch.setattr(team_module, '_team_manager', manager)
    forbidden = Mock(side_effect=AssertionError('read must not prepare or restore'))
    monkeypatch.setattr(team_module, 'get_team_manager', forbidden)
    monkeypatch.setattr(manager, '_load_session_team_spec', forbidden)
    monkeypatch.setattr(manager, 'get_or_create_team', forbidden)
    spec = TeamAgentSpec(agents={'leader': {'system_prompt': 'private-prompt',
        'model': {'model_client_config': {'client_provider': 'OpenAI', 'api_key': 'private-key',
                                          'api_base': 'https://unused.invalid'},
                  'model_request_config': {'model': 'configured-model'}}},
        'teammate': {}}, team_name='team-a', enable_permissions=True)
    runtime_spec = TeamSpec(team_name='team-a', display_name='Configured Team')
    ctx = TeamRuntimeContext(team_spec=runtime_spec)
    team = TeamAgent(AgentCard(id='team-a', name='team-a'))
    # Configure only the real static assembly seam. Full configure mounts tools,
    # models and transports, which this read-only contract must never initialize.
    team._configurator._blueprint = TeamAgentBlueprint(team.card, spec, ctx, 'en')
    runtime = TeamRuntimeManager()
    entry = ActiveTeam('team-a', team, scope.session_id)
    await runtime.pool.add(entry)
    monkeypatch.setattr(runner_module.GLOBAL_RUNNER, '_team_runtime_manager', runtime)
    facade = object()
    app = SimpleNamespace(find_agent_exact=Mock(return_value=facade))
    return SimpleNamespace(scope=scope, manager=manager, app=app, spec=spec,
                           ctx=ctx, runtime=runtime, entry=entry, team=team,
                           metadata=metadata, path=path, forbidden=forbidden)


def allow():
    return None


async def test_real_existing_team_snapshot_is_exact_immutable_and_secret_free(configured):
    c = configured
    before = c.path.read_bytes()
    binding = await resolve_configured_team(c.app, scope=c.scope, before_read=allow)
    info = binding.capability
    assert info.team_id == info.team_name == 'team-a'
    assert info.identity_kind == 'team_name'
    assert info.member_roles == ('leader', 'teammate')
    assert info.enable_permissions is True
    assert len(info.spec_fingerprint) == 64
    payload = await inspect_configured_team(c.app, scope=c.scope, before_read=allow)
    encoded = json.dumps(payload)
    assert payload['available'] is True
    assert 'private-key' not in encoded and 'private-prompt' not in encoded
    assert 'private-key' not in repr(binding)
    with pytest.raises(dataclasses.FrozenInstanceError):
        info.team_name = 'other'
    await validate_configured_team_binding(c.app, binding, before_read=allow)
    assert c.path.read_bytes() == before
    assert await c.runtime.pool.get('team-a') is c.entry
    c.forbidden.assert_not_called()


@pytest.mark.parametrize('field,value', [
    ('channel_id', 'other'), ('session_id', 'other-session'),
    ('project_id', None), ('project_dir', 'other-project'),
    ('agent_mode', 'code.team'), ('work_mode', 'code'),
])
async def test_wrong_scope_has_no_owner_preparation(configured, field, value):
    c = configured
    scope = dataclasses.replace(c.scope, **{field: value})
    with pytest.raises(ConfiguredTeamUnavailable):
        await resolve_configured_team(c.app, scope=scope, before_read=allow)
    c.forbidden.assert_not_called()
    assert await c.runtime.pool.get('team-a') is c.entry


@pytest.mark.parametrize('change', ['manager', 'runtime', 'entry', 'closing', 'session',
                                  'spec_name', 'runtime_name', 'blueprint', 'facade'])
async def test_missing_or_wrong_runtime_does_not_fallback(configured, monkeypatch, change):
    c = configured
    if change == 'manager':
        monkeypatch.setattr(team_module, '_team_manager', None)
    elif change == 'runtime':
        monkeypatch.setattr(runner_module.GLOBAL_RUNNER, '_team_runtime_manager', None)
    elif change == 'entry':
        await c.runtime.pool.remove('team-a')
    elif change == 'closing':
        c.entry.closing = True
    elif change == 'session':
        c.entry.current_session_id = 'other'
    elif change == 'spec_name':
        c.spec.team_name = 'other'
    elif change == 'runtime_name':
        c.ctx.team_spec.team_name = 'other'
    elif change == 'blueprint':
        c.team._configurator._blueprint = None
    else:
        c.app.find_agent_exact.return_value = None
    result = await inspect_configured_team(c.app, scope=c.scope, before_read=allow)
    assert result['available'] is False
    c.forbidden.assert_not_called()


@pytest.mark.parametrize('change', ['model', 'permission', 'spec', 'replacement', 'facade', 'paused'])
async def test_binding_rejects_configuration_and_owner_drift(configured, change):
    c = configured
    binding = await resolve_configured_team(c.app, scope=c.scope, before_read=allow)
    if change == 'model':
        c.spec.agents['leader'].model.model_client_config.api_key = 'new-key'
    elif change == 'permission':
        c.ctx.permissions_override = {'write_file': 'deny'}
    elif change == 'spec':
        c.spec.agents['leader'].system_prompt = 'changed'
    elif change == 'replacement':
        await c.runtime.pool.remove('team-a')
        await c.runtime.pool.add(ActiveTeam('team-a', c.team, c.scope.session_id))
    elif change == 'facade':
        c.app.find_agent_exact.return_value = object()
    else:
        c.entry.state = RuntimeState.PAUSED
    with pytest.raises(ConfiguredTeamUnavailable, match='binding_changed'):
        await validate_configured_team_binding(c.app, binding, before_read=allow)
    c.forbidden.assert_not_called()


async def test_paused_runtime_is_observable_but_not_claimed_ready_to_execute(configured):
    c = configured
    c.entry.state = RuntimeState.PAUSED
    await c.entry.interact_gate.close_and_drain()
    result = await inspect_configured_team(c.app, scope=c.scope, before_read=allow)
    assert result['available'] is True
    assert result['capability']['runtime_state'] == 'paused'
    assert result['capability']['gate_closed'] is True
    assert result['execution_admitted'] is False


async def test_denied_reads_do_not_touch_metadata_or_empty_owner(configured, monkeypatch):
    c = configured
    denied = Mock(side_effect=PermissionError('revoked'))
    read = Mock(side_effect=AssertionError('forbidden metadata read'))
    monkeypatch.setattr(session_metadata, '_read_metadata', read)
    monkeypatch.setattr(team_module, '_team_manager', None)
    with pytest.raises(PermissionError):
        await inspect_configured_team(c.app, scope=c.scope, before_read=denied)
    read.assert_not_called()


@pytest.mark.parametrize('result', [False, True, 'ok'])
async def test_guard_must_return_none(configured, result):
    with pytest.raises(TypeError, match='before_read'):
        await resolve_configured_team(configured.app, scope=configured.scope,
                                      before_read=lambda: result)


async def test_invalid_scope_and_forged_binding(configured):
    c = configured
    with pytest.raises(ConfiguredTeamUnavailable):
        TeamExecutionScope('web', '../bad', c.scope.project_dir, None, 'team', 'work')
    with pytest.raises(ConfiguredTeamUnavailable):
        await validate_configured_team_binding(c.app, object(), before_read=allow)


async def test_optional_project_id_and_code_team_keep_stored_configuration(configured):
    c = configured
    c.metadata.update(project_id=None, mode='code.team', work_mode='code')
    c.path.write_text(json.dumps(c.metadata), encoding='utf-8')
    scope = dataclasses.replace(c.scope, project_id=None, agent_mode='code.team', work_mode='code')
    binding = await resolve_configured_team(c.app, scope=scope, before_read=allow)
    assert binding.scope == scope
    c.app.find_agent_exact.assert_called_with(channel_id='web', mode='code',
                                             project_dir=scope.project_dir, sub_mode='team')
    assert binding.capability.enable_permissions is True
    assert c.spec.agents['leader'].model.model_request_config.model_name == 'configured-model'


async def test_other_team_in_same_session_is_not_selected(configured):
    c = configured
    other = ActiveTeam('other-team', c.team, c.scope.session_id)
    await c.runtime.pool.add(other)
    binding = await resolve_configured_team(c.app, scope=c.scope, before_read=allow)
    assert binding.capability.team_name == 'team-a'
    await c.runtime.pool.remove('team-a')
    assert (await inspect_configured_team(c.app, scope=c.scope, before_read=allow))['available'] is False
    assert await c.runtime.pool.get('other-team') is other


@pytest.mark.parametrize('change', ['revoke', 'replace', 'mode'])
async def test_pool_wait_rechecks_authority_original_owner_and_stored_scope(configured, change):
    c = configured
    granted = True
    checks = 0
    read_done = asyncio.Event()

    def guard():
        nonlocal checks
        if not granted:
            raise PermissionError('revoked')
        checks += 1
        if checks == 2:
            read_done.set()

    # Hold the real SDK pool lock; the adapter must pass its first scope read
    # before it can acquire an entry, then observe this change after the await.
    await c.runtime.pool._lock.acquire()
    task = asyncio.create_task(resolve_configured_team(c.app, scope=c.scope, before_read=guard))
    try:
        await asyncio.wait_for(read_done.wait(), 2)
        if change == 'revoke':
            granted = False
        elif change == 'replace':
            c.entry.current_session_id = 'other-session'
        else:
            c.metadata['mode'] = 'agent'
            c.path.write_text(json.dumps(c.metadata), encoding='utf-8')
    finally:
        c.runtime.pool._lock.release()
    error = PermissionError if change == 'revoke' else ConfiguredTeamUnavailable
    with pytest.raises(error):
        await task
    c.forbidden.assert_not_called()


async def test_async_guard_is_rejected_without_running_it(configured):
    effect = Mock()

    async def invalid_guard():
        effect()

    with pytest.raises(TypeError, match='before_read'):
        await resolve_configured_team(configured.app, scope=configured.scope, before_read=invalid_guard)
    effect.assert_not_called()


async def test_malformed_metadata_is_not_an_empty_success(configured):
    configured.path.write_text('{', encoding='utf-8')
    with pytest.raises(ValueError):
        await inspect_configured_team(configured.app, scope=configured.scope, before_read=allow)


async def test_unserializable_runtime_configuration_does_not_expose_objects(configured):
    c = configured
    c.ctx.team_spec.metadata['unsafe'] = object()
    result = await inspect_configured_team(c.app, scope=c.scope, before_read=allow)
    assert result == {'available': False, 'reason': 'configuration_unrepresentable',
                      'execution_admitted': False}
