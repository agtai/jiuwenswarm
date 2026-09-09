# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.
"""Read-only bindings to configured, already resident Team owners.

This is an observation, not execution admission or proof that rails are mounted.
Cold configuration is deliberately unavailable: the existing TeamManager loader
can ensure entities and write metadata. Future execution must use the original
team_helpers -> Runner team stream path, with its Team model pool and permission
rails, and recheck scope/authority/configuration at that owner's effect boundary.
No ordinary Agent model policy or direct Swarmflow tool call substitutes for it.
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import os
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any

from jiuwenswarm.common.mode_matrix import TEAM_CANONICAL_MODES
from jiuwenswarm.common.schema.agent import AgentRequest
from jiuwenswarm.server.runtime.agent_resolution import resolve_request_runtime_mode


class ConfiguredTeamUnavailable(ValueError):
    """There is no proven exact resident configured Team for this scope."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def _identity(value: Any) -> bool:
    return (type(value) is str and bool(value) and value.strip() == value
            and len(value) <= 4096 and not any(ord(c) < 32 for c in value)
            and not any(0xD800 <= ord(c) <= 0xDFFF for c in value))


@dataclass(frozen=True)
class TeamExecutionScope:
    channel_id: str
    session_id: str
    project_dir: str
    project_id: str | None
    agent_mode: str
    work_mode: str

    def __post_init__(self):
        from jiuwenswarm.server.runtime.session.session_history import is_valid_session_id

        if (not all(_identity(v) for v in (self.channel_id, self.session_id,
                                          self.project_dir, self.agent_mode, self.work_mode))
                or not is_valid_session_id(self.session_id)
                or self.project_id is not None and not _identity(self.project_id)
                or self.agent_mode not in TEAM_CANONICAL_MODES
                or self.work_mode not in {'work', 'code'}):
            raise ConfiguredTeamUnavailable('scope_invalid')


@dataclass(frozen=True)
class ConfiguredTeamCapability:
    team_id: str
    team_name: str
    identity_kind: str
    runtime_state: str
    gate_closed: bool
    member_roles: tuple[str, ...]
    enable_permissions: bool
    spec_fingerprint: str
    model_fingerprint: str
    permission_fingerprint: str


_SEAL = object()


@dataclass(frozen=True, init=False)
class ConfiguredTeamBinding:
    """Opaque in-process observation; never deserialize this from a request."""

    scope: TeamExecutionScope
    capability: ConfiguredTeamCapability
    _identities: tuple[Any, ...] = field(repr=False)
    _seal: Any = field(repr=False)

    def __init__(self, scope, capability, identities, *, _seal=None):
        if _seal is not _SEAL:
            raise ConfiguredTeamUnavailable('binding_invalid')
        object.__setattr__(self, 'scope', scope)
        object.__setattr__(self, 'capability', capability)
        object.__setattr__(self, '_identities', identities)
        object.__setattr__(self, '_seal', _seal)


def _guard(callback):
    if not callable(callback):
        raise TypeError('before_read must be a synchronous authority check')
    result = callback()
    if inspect.iscoroutine(result):
        result.close()
    if result is not None:
        raise TypeError('before_read must return None or raise')


def _fingerprint(value):
    try:
        raw = json.dumps(value, sort_keys=True, ensure_ascii=True,
                         separators=(',', ':'), allow_nan=False).encode('utf-8')
        if len(raw) > 1024 * 1024:
            raise ValueError('oversized configuration')
        return hashlib.sha256(raw).hexdigest()
    except (TypeError, ValueError, RecursionError) as exc:
        raise ConfiguredTeamUnavailable('configuration_unrepresentable') from exc


def _path(value):
    return os.path.normcase(os.path.abspath(os.path.expanduser(value)))


async def _stored_owner(agent_manager, scope):
    from jiuwenswarm.server.runtime.session.session_metadata import _read_metadata

    # Raw strict read avoids get_session_metadata's legacy mode inference and
    # all ensure/normalization writebacks. Absent facts cannot grant a scope.
    metadata = await asyncio.to_thread(_read_metadata, scope.session_id,
                                       cache_bust=True, strict=True)
    if (not isinstance(metadata, dict)
            or metadata.get('session_id') != scope.session_id
            or metadata.get('channel_id') != scope.channel_id
            or metadata.get('project_id') != scope.project_id
            or not _identity(metadata.get('project_dir'))
            or _path(metadata['project_dir']) != _path(scope.project_dir)
            or metadata.get('work_mode') != scope.work_mode
            or not _identity(metadata.get('mode'))):
        raise ConfiguredTeamUnavailable('stored_scope_mismatch')
    request = AgentRequest(request_id='team-capability-read', channel_id=scope.channel_id,
                           session_id=scope.session_id,
                           params={'mode': metadata['mode'], 'work_mode': scope.work_mode})
    mode = resolve_request_runtime_mode(request, work_mode=scope.work_mode)
    if mode.canonical_mode != scope.agent_mode or not mode.is_team:
        raise ConfiguredTeamUnavailable('stored_mode_mismatch')
    facade = agent_manager.find_agent_exact(channel_id=scope.channel_id,
        mode=mode.manager_mode, project_dir=metadata['project_dir'], sub_mode=mode.sub_mode)
    if facade is None:
        raise ConfiguredTeamUnavailable('session_owner_unavailable')
    return facade, metadata.get('team_name')


async def resolve_configured_team(
    agent_manager, *, scope: TeamExecutionScope, before_read: Callable[[], None],
) -> ConfiguredTeamBinding:
    """Observe a single exact existing runtime without constructing any owner.

    The caller must authorize even an empty directory. Guard exceptions propagate;
    they are never converted to a misleading empty successful response.
    """
    if type(scope) is not TeamExecutionScope:
        raise ConfiguredTeamUnavailable('scope_invalid')
    _guard(before_read)
    facade, stored_name = await _stored_owner(agent_manager, scope)
    _guard(before_read)
    from jiuwenswarm.agents.harness.team.team_manager import get_existing_team_manager
    from openjiuwen.agent_teams.agent.team_agent import TeamAgent
    from openjiuwen.agent_teams.runtime.pool import RuntimeState
    from openjiuwen.agent_teams.schema.blueprint import TeamAgentSpec
    from openjiuwen.agent_teams.schema.team import TeamRole, TeamRuntimeContext, TeamSpec
    from openjiuwen.core.runner.runner import GLOBAL_RUNNER

    manager = get_existing_team_manager(scope.channel_id)
    name = manager.get_active_team_name(scope.session_id) if manager is not None else None
    if not _identity(name) or name != stored_name:
        raise ConfiguredTeamUnavailable('resident_team_unavailable')
    # The existing helper creates a manager when missing; never call it here.
    runtime = vars(GLOBAL_RUNNER).get('_team_runtime_manager')
    if runtime is None:
        raise ConfiguredTeamUnavailable('resident_team_unavailable')
    entry = await runtime.pool.get(name)
    # Re-read persisted scope after the pool await before projecting private facts.
    current_facade, current_name = await _stored_owner(agent_manager, scope)
    _guard(before_read)
    if (current_facade is not facade or current_name != name
            or get_existing_team_manager(scope.channel_id) is not manager
            or manager.get_active_team_name(scope.session_id) != name
            or vars(GLOBAL_RUNNER).get('_team_runtime_manager') is not runtime
            or runtime.pool._teams.get(name) is not entry):
        raise ConfiguredTeamUnavailable('owner_changed')
    if (entry is None or entry.team_name != name or entry.current_session_id != scope.session_id
            or entry.closing or entry.state not in (RuntimeState.RUNNING, RuntimeState.PAUSED)
            or not isinstance(entry.agent, TeamAgent)):
        raise ConfiguredTeamUnavailable('resident_team_unavailable')
    agent = entry.agent
    spec, team_spec, ctx = agent.spec, agent.team_spec, agent.runtime_context
    if (not isinstance(spec, TeamAgentSpec) or not isinstance(team_spec, TeamSpec)
            or not isinstance(ctx, TeamRuntimeContext) or ctx.role != TeamRole.LEADER
            or ctx.team_spec is not team_spec or spec.team_name != name or team_spec.team_name != name):
        raise ConfiguredTeamUnavailable('configuration_unavailable')
    try:
        original = spec.model_dump(mode='json')
        assembled = team_spec.model_dump(mode='json')
        context = ctx.model_dump(mode='json')
    except (TypeError, ValueError, RecursionError) as exc:
        raise ConfiguredTeamUnavailable('configuration_unrepresentable') from exc
    models = {key: original.get(key) for key in (
        'model_pool', 'model_pool_strategy', 'model_router', 'model_intelli_router',
        'leader', 'predefined_members', 'tiny_agents')}
    models['agents'] = original['agents']
    models['runtime_pool'] = assembled['model_pool']
    models['runtime_strategy'] = assembled['model_pool_strategy']
    models['member_model'] = context.get('member_model')
    permissions = {'enabled': original['enable_permissions'],
                   'agents': original['agents'], 'override': context.get('permissions_override')}
    capability = ConfiguredTeamCapability(name, name, 'team_name', entry.state.value,
        entry.interact_gate.closed, tuple(sorted(spec.agents)), spec.enable_permissions,
        _fingerprint([original, assembled, context]), _fingerprint(models), _fingerprint(permissions))
    return ConfiguredTeamBinding(scope, capability,
        (facade, manager, runtime, entry, agent, spec, team_spec, ctx), _seal=_SEAL)


async def inspect_configured_team(agent_manager, *, scope, before_read) -> dict[str, Any]:
    """Project authorized metadata only; no prompts, credentials or provider objects."""
    try:
        binding = await resolve_configured_team(agent_manager, scope=scope, before_read=before_read)
    except ConfiguredTeamUnavailable as exc:
        return {'available': False, 'reason': exc.reason, 'execution_admitted': False}
    return {'available': True, 'capability': asdict(binding.capability),
            'execution_admitted': False, 'lifetime': 'current_process'}


async def validate_configured_team_binding(agent_manager, binding, *, before_read) -> None:
    """Reject changed observations; this read check does not reserve an effect."""
    if type(binding) is not ConfiguredTeamBinding or binding._seal is not _SEAL:
        raise ConfiguredTeamUnavailable('binding_invalid')
    try:
        current = await resolve_configured_team(agent_manager, scope=binding.scope,
                                               before_read=before_read)
    except ConfiguredTeamUnavailable as exc:
        raise ConfiguredTeamUnavailable('binding_changed') from exc
    if (current.capability != binding.capability
            or any(a is not b for a, b in zip(current._identities, binding._identities))):
        raise ConfiguredTeamUnavailable('binding_changed')
