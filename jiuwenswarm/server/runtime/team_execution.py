# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.
"""Configured Team control through the original producer and member rails.

Service records retain bounded observation/control state. TeamManager and the
SDK still own execution. Input or workflow launch receipts never mean business
completion, and legacy EOF/finally events are not completion evidence.
"""
from __future__ import annotations

import asyncio
import inspect
import json
from copy import deepcopy
from contextlib import aclosing
from dataclasses import asdict, dataclass, field
from typing import Any
from uuid import uuid4

from jiuwenswarm.common.schema.agent import AgentRequest
from jiuwenswarm.server.runtime.team_execution_capabilities import (
    ConfiguredTeamUnavailable, TeamExecutionScope,
    _fingerprint, _stored_owner, resolve_configured_team,
)


_KIND = 'configured_team'
_CONTROL = 'configured_team_control'


def _guard(callback, capability):
    if not callable(callback):
        raise ValueError('configured_team_authority_required')
    result = callback(capability)
    if inspect.iscoroutine(result):
        result.close()
    if result is not None:
        raise ValueError('configured_team_authority_must_return_none')


def _configuration_fingerprint(spec):
    # TeamAgentSpec.build resolves only unspecified member languages in place.
    # Compare that exact documented normalization without accepting arbitrary
    # post-build spec/model/permission changes or resetting the frozen digest.
    from openjiuwen.harness.prompts import resolve_language

    snapshot = spec.model_dump(mode='json')
    language = resolve_language(spec.language)
    for member in snapshot['agents'].values():
        if member.get('language') is None:
            member['language'] = language
    return _fingerprint(snapshot)


@dataclass(frozen=True)
class SwarmflowStartIntent:
    script_path: str | None = None
    script: str | None = None
    args: str | None = None

    def __post_init__(self):
        sources = (self.script_path, self.script)
        if sum(value is not None for value in sources) != 1:
            raise ValueError('swarmflow_source_required')
        if any(value is not None and (type(value) is not str or not value.strip() or '\x00' in value)
               for value in sources):
            raise ValueError('swarmflow_source_invalid')
        if self.args is not None and (type(self.args) is not str or '\x00' in self.args):
            raise ValueError('swarmflow_args_invalid')
        try:
            for value in (*sources, self.args):
                if value is not None:
                    value.encode('utf-8')
        except UnicodeError as exc:
            raise ValueError('swarmflow_input_invalid') from exc
        if len(json.dumps(asdict(self), ensure_ascii=True).encode()) > 64 * 1024:
            raise ValueError('swarmflow_input_too_large')


@dataclass
class _Intent:
    inputs: dict
    before_effect: Any = None
    tool_call_id: str = field(default_factory=lambda: 'team-control-' + uuid4().hex)
    admitted: asyncio.Event = field(default_factory=asyncio.Event)
    observed: asyncio.Event = field(default_factory=asyncio.Event)
    claimed: bool = False
    tool: Any = None
    leader: Any = None
    receipt: dict | None = None
    failure: str | None = None


@dataclass
class _TeamRun:
    scope: TeamExecutionScope
    before_effect: Any
    service: Any
    agent: Any
    entry: Any = None
    manager: Any = None
    spec: Any = None
    capability: Any = None
    producer: Any = None
    sdk_owner: Any = None
    runtime: Any = None
    identity: dict = field(default_factory=dict)
    configuration: str | None = None
    cancelled: bool = False
    failure: str | None = None
    input_accepted: bool = False
    cold_start: bool = False
    receipt_changed: asyncio.Event = field(default_factory=asyncio.Event)
    intent: _Intent | None = None
    initial_intent: _Intent | None = None
    runtime_bound: bool = False
    preserve_original: bool = False

    def check(self):
        if self.cancelled or self.entry is None or self.entry.task.done():
            raise ValueError('configured_team_execution_closed')
        if not self.preserve_original:
            _guard(self.before_effect, self.capability)
        from jiuwenswarm.server.runtime.session.session_metadata import _read_metadata

        metadata = _read_metadata(self.scope.session_id, cache_bust=True, strict=True)
        if any(metadata.get(key) != value for key, value in self.identity.items()):
            raise ValueError('configured_team_scope_changed')
        if self.configuration is not None and _configuration_fingerprint(self.spec) != self.configuration:
            raise ValueError('configured_team_configuration_changed')
        if self.sdk_owner is not None:
            entry = self.runtime.pool._teams.get(self.spec.team_name)
            if (entry is not self.sdk_owner or entry.agent.spec is not self.spec
                    or entry.current_session_id != self.scope.session_id
                    or self.runtime_bound and entry.closing):
                raise ValueError('configured_team_runtime_changed')
            if self.capability is not None:
                actual = _fingerprint([self.spec.model_dump(mode='json'),
                    entry.agent.team_spec.model_dump(mode='json'),
                    entry.agent.runtime_context.model_dump(mode='json')])
                if actual != self.capability.spec_fingerprint:
                    raise ValueError('configured_team_configuration_changed')

    def on_model_boundary(self):
        self.check()
        if self.cold_start and not self.input_accepted:
            self.input_accepted = True
            if self.intent is not None:
                self.intent.admitted.set()
            self.receipt_changed.set()

    def check_intent(self, intent):
        self.check()
        if self.intent is not intent or intent.observed.is_set():
            raise ValueError('swarmflow_intent_closed')
        if intent.before_effect is not None:
            _guard(intent.before_effect, self.capability)

    def claim_intent(self, intent, leader):
        self.check_intent(intent)
        if self.intent is not intent or intent.claimed or not self.input_accepted:
            raise ValueError('swarmflow_intent_not_admitted')
        from openjiuwen.agent_teams.workflow.tool_swarmflow import SwarmflowTool
        from openjiuwen.core.runner import Runner

        card = leader.ability_manager._tools.get('swarmflow')
        tool = Runner.resource_mgr.get_tool(card.id) if card is not None else None
        if not isinstance(tool, SwarmflowTool) or tool._team_name != self.spec.team_name:
            raise ValueError('configured_swarmflow_tool_unavailable')
        if self.sdk_owner is not None:
            native = self.sdk_owner.agent.harness.get_deep_agent()
            if tool._parent_agent is not native or leader not in (native, native.react_agent):
                raise ValueError('configured_swarmflow_tool_owner_changed')
        intent.tool, intent.leader, intent.claimed = tool, leader, True

    def check_tool(self, ctx):
        self.check()
        args = ctx.inputs.tool_args
        if type(args) is str:
            try:
                args = json.loads(args)
            except ValueError:
                raise ValueError('configured_team_tool_input_invalid') from None
        if isinstance(args, dict) and (args.get('cli_agent') or args.get('ssh_transport')):
            raise ValueError('configured_team_remote_execution_unsupported')
        intent = self.intent
        if intent is not None and getattr(ctx.inputs.tool_call, 'id', None) == intent.tool_call_id:
            self.check_intent(intent)
            from openjiuwen.core.runner import Runner

            card = ctx.agent.ability_manager._tools.get('swarmflow')
            if (ctx.agent is not intent.leader or ctx.inputs.tool_name != 'swarmflow'
                    or args != intent.inputs or card is None
                    or Runner.resource_mgr.get_tool(card.id) is not intent.tool):
                raise ValueError('swarmflow_intent_changed')

    def capture_tool_result(self, ctx):
        intent = self.intent
        if intent is None or getattr(ctx.inputs.tool_call, 'id', None) != intent.tool_call_id:
            return
        if ctx.agent is not intent.leader:
            raise ValueError('swarmflow_result_owner_changed')
        from openjiuwen.harness.tools.base_tool import ToolOutput

        result = ctx.inputs.tool_result
        data = result.data if isinstance(result, ToolOutput) else None
        if (isinstance(result, ToolOutput) and result.success and isinstance(data, dict)
                and data.get('status') == 'launched'
                and all(type(data.get(key)) is str and data[key] for key in ('run_id', 'task_id'))):
            intent.receipt = {key: data.get(key) for key in ('status', 'run_id', 'task_id', 'script_path')}
        else:
            intent.failure = intent.failure or 'swarmflow_tool_not_launched'
        intent.before_effect = None
        intent.observed.set()
        self.receipt_changed.set()

    async def runtime_ready(self):
        from openjiuwen.core.runner.runner import GLOBAL_RUNNER

        self.runtime = vars(GLOBAL_RUNNER).get('_team_runtime_manager')
        entry = self.runtime.pool._teams.get(self.spec.team_name) if self.runtime is not None else None
        if entry is None or entry.current_session_id != self.scope.session_id or entry.agent.spec is not self.spec:
            raise ValueError('configured_team_runtime_unavailable')
        self.sdk_owner = entry
        self.runtime_bound = True
        binding = await resolve_configured_team(self.service.manager, scope=self.scope,
                                                before_read=lambda: _guard(self.before_effect, self.capability))
        self.capability = binding.capability
        self.check()


@dataclass
class _TeamControl:
    run: _TeamRun
    before_effect: Any
    intent: _Intent | None = None
    input_accepted: bool = False
    failure: str | None = None


def _request(request, scope, expected_fingerprint, swarmflow):
    if (type(scope) is not TeamExecutionScope or not isinstance(request, AgentRequest)
            or request.session_id != scope.session_id or request.channel_id != scope.channel_id
            or type(request.request_id) is not str or not request.request_id.strip()):
        raise ValueError('configured_team_request_scope_invalid')
    query = (request.params or {}).get('query')
    if type(query) is not str or not query.strip() or '\x00' in query or len(query.encode('utf-8')) > 64 * 1024:
        raise ValueError('configured_team_query_invalid')
    if expected_fingerprint is not None and (type(expected_fingerprint) is not str or len(expected_fingerprint) != 64
            or any(char not in '0123456789abcdef' for char in expected_fingerprint)):
        raise ValueError('configured_team_fingerprint_invalid')
    if swarmflow is not None and type(swarmflow) is not SwarmflowStartIntent:
        raise ValueError('swarmflow_intent_invalid')
    return AgentRequest(request_id=request.request_id, channel_id=scope.channel_id,
        session_id=scope.session_id, is_stream=True, req_method=request.req_method,
        params={'query': query, 'scope': asdict(scope), 'expected_fingerprint': expected_fingerprint,
                'swarmflow': asdict(swarmflow) if swarmflow is not None else None})


def _fact(entry, state):
    control = state if type(state) is _TeamControl else None
    state = control.run if control is not None else state
    task = state.producer
    intent = control.intent if control is not None else state.initial_intent
    accepted = control.input_accepted if control is not None else state.input_accepted
    return {'execution_id': entry.request.request_id,
        'output_execution_id': state.entry.request.request_id if state.entry is not None else None,
        'status': 'launched' if intent is not None and intent.receipt is not None else
                  'input_accepted' if accepted else 'unknown' if entry.task.done() else 'pending',
        'input_accepted': accepted,
        'workflow': deepcopy(intent.receipt) if intent is not None else None,
        'failure': (control.failure if control is not None else state.failure)
                   or (intent.failure if intent is not None else None),
        'capability': asdict(state.capability) if state.capability is not None else None,
        'producer_exited': bool(task is not None and task.done()),
        'business_completed': False, 'cleanup_outcome': 'unproven',
        'epoch': state.service.execution_epoch, 'inventory_scope': 'current_process'}


async def start_configured_team(service, agent, request, *, scope, expected_fingerprint=None,
                                before_effect, swarmflow=None):
    canonical = _request(request, scope, expected_fingerprint, swarmflow)
    _guard(before_effect, None)
    owner, _ = await _stored_owner(service.manager, scope)
    if owner is not agent:
        raise ValueError('configured_team_agent_owner_mismatch')
    _guard(before_effect, None)
    try:
        previous = _find(service, agent, scope, canonical.request_id)
    except ValueError:
        previous = None
    if previous is not None:
        # Let the common service compare its canonical fingerprint. The new
        # closure cannot replace the original accepted producer or authority.
        entry = service.start_internal(agent, canonical, kind=previous.internal_kind,
            producer=previous.internal_producer, capability_state=previous.capability_state,
            retain_record=True, control_only=previous.control_only)
        previous_state = entry.capability_state
        run = previous_state.run if type(previous_state) is _TeamControl else previous_state
        if run.scope != scope:
            raise ValueError('configured_team_scope_mismatch')
        _guard(before_effect, run.capability)
        return _fact(entry, previous_state)
    for active in service.list_internal(agent, session_id=scope.session_id, kind=_KIND):
        original = active.capability_state
        if type(original) is _TeamRun and not active.task.done() and original.producer is None:
            raise ValueError('configured_team_preparing')
    from jiuwenswarm.agents.harness.team.team_manager import get_existing_team_manager

    manager = get_existing_team_manager(scope.channel_id)
    task = manager.get_stream_task(scope.session_id) if manager is not None else None
    existing = getattr(task, '_jiuwenswarm_team_execution', None)
    if type(existing) is _TeamRun and not task.done():
        if existing.scope != scope or existing.agent is not agent:
            raise ValueError('configured_team_scope_mismatch')
        control = _TeamControl(existing, before_effect,
            _Intent({key: value for key, value in asdict(swarmflow).items() if value is not None}, before_effect)
            if swarmflow is not None else None)
        entry = service.start_internal(agent, canonical, kind=_CONTROL, producer=_produce_control,
            capability_state=control, retain_record=True, control_only=True)
        control = entry.capability_state
        try:
            await asyncio.shield(entry.task)
        except Exception:
            if not control.input_accepted:
                raise
        return _fact(entry, control)
    state = _TeamRun(scope, before_effect, service, agent)
    from jiuwenswarm.server.runtime.session.session_metadata import _read_metadata

    _preflight(state, _read_metadata(scope.session_id, cache_bust=True, strict=True))
    _guard(before_effect, None)
    if swarmflow is not None:
        state.intent = _Intent({key: value for key, value in asdict(swarmflow).items() if value is not None}, before_effect)
        state.initial_intent = state.intent
    entry = service.start_internal(agent, canonical, kind=_KIND, producer=lambda original: _produce(original),
                                   capability_state=state, retain_record=True)
    state = entry.capability_state
    _guard(before_effect, state.capability)
    if not state.input_accepted and not entry.task.done():
        try:
            await asyncio.wait_for(asyncio.shield(state.receipt_changed.wait()), 1.0)
        except TimeoutError:
            pass
    return _fact(entry, state)


async def _produce_control(entry):
    control = entry.capability_state
    state = control.run
    try:
        state.check()
        _guard(control.before_effect, state.capability)
        expected = entry.request.params['expected_fingerprint']
        if expected is not None and expected != state.capability.spec_fingerprint:
            raise ValueError('configured_team_binding_changed')
        if state.manager.get_stream_task(state.scope.session_id) is not state.producer:
            raise ValueError('configured_team_producer_changed')
        if control.intent is not None:
            if state.intent is not None and not state.intent.observed.is_set():
                raise ValueError('swarmflow_intent_pending')
            state.intent = control.intent
        def admit():
            state.check()
            _guard(control.before_effect, state.capability)
        success, reason = await state.manager.interact(state.scope.session_id, entry.request.params['query'],
            expected_task=state.producer, before_effect=admit)
        if not success:
            raise ValueError(reason or 'configured_team_input_rejected')
        control.input_accepted = True
        if control.intent is not None:
            control.intent.admitted.set()
        # Receipt is retained before the observer/publication can fail.
        if False:
            yield None
    except BaseException as exc:
        control.failure = type(exc).__name__
        if control.intent is not None and not control.input_accepted:
            control.intent.failure = control.failure
            control.intent.before_effect = None
            control.intent.admitted.set()
            control.intent.observed.set()
        raise


async def _produce(entry):
    state = entry.capability_state
    state.entry = entry
    from jiuwenswarm.server.runtime.session.session_metadata import _read_metadata
    from jiuwenswarm.agents.harness.team.team_manager import get_team_manager
    from jiuwenswarm.server.runtime.agent_adapter.team_helpers import process_configured_team_stream

    try:
        metadata = _read_metadata(state.scope.session_id, cache_bust=True, strict=True)
        state.identity = {key: metadata.get(key) for key in (
            'session_id', 'channel_id', 'project_dir', 'project_id', 'mode', 'work_mode', 'team_name')}
        state.check()
        _preflight(state, metadata)
        state.manager = get_team_manager(state.scope.channel_id)
        try:
            binding = await resolve_configured_team(state.service.manager, scope=state.scope,
                                                    before_read=lambda: state.check())
        except ConfiguredTeamUnavailable as exc:
            if entry.request.params['expected_fingerprint'] is not None:
                raise ValueError('configured_team_binding_unavailable') from exc
            from openjiuwen.core.runner.runner import GLOBAL_RUNNER
            from openjiuwen.agent_teams.runtime.pool import RuntimeState

            runtime = vars(GLOBAL_RUNNER).get('_team_runtime_manager')
            pooled = runtime.pool._teams.get(metadata['team_name']) if runtime is not None else None
            if pooled is not None:
                if pooled.current_session_id != state.scope.session_id or pooled.state is not RuntimeState.PAUSED:
                    raise ValueError('configured_team_runtime_unavailable') from exc
                state.spec, state.runtime, state.sdk_owner = pooled.agent.spec, runtime, pooled
                await _mount_warm(state)
            else:
                state.cold_start = True
                state.spec = await state.manager.get_swarm_enriched_team_spec(
                    state.scope.session_id, mode=state.scope.agent_mode, project_dir=state.scope.project_dir,
                    request_id=entry.request.request_id, channel_id=state.scope.channel_id,
                    request_metadata={'mode': state.scope.agent_mode, 'project_dir': state.scope.project_dir},
                    execution_context=state)
        else:
            expected = entry.request.params['expected_fingerprint']
            if expected is not None and expected != binding.capability.spec_fingerprint:
                raise ValueError('configured_team_binding_changed')
            state.spec = binding._identities[5]
            state.capability = binding.capability
            state.runtime, state.sdk_owner = binding._identities[2:4]
            state.runtime_bound = True
            await _mount_warm(state)
        state.configuration = _configuration_fingerprint(state.spec)
        state.check()
        async with aclosing(process_configured_team_stream(entry.request, execution=state)) as stream:
            async for chunk in stream:
                yield chunk
    except BaseException as exc:
        state.failure = type(exc).__name__
        if state.intent is not None and not state.intent.admitted.is_set():
            state.intent.failure = state.failure
            state.intent.admitted.set()
        raise
    finally:
        # The service pin follows the physical producer, even if publication or
        # observation fails. Observer detach never closes this internal source.
        task = state.producer
        if task is not None and not task.done():
            # A borrowed Text producer retains its original authority. Failure
            # of this additional observer must not cancel that prior work.
            if not state.preserve_original:
                state.cancelled = True
                task.cancel()
            while not task.done():
                try:
                    await asyncio.shield(task)
                except asyncio.CancelledError:
                    continue
                except Exception:
                    break
        if task is not None and task.done() and not task.cancelled():
            failure = task.exception()
            if failure is not None:
                state.failure = str(failure)
        state.receipt_changed.set()


def _preflight(state, metadata):
    from jiuwenswarm.agents.harness.team.config_loader import load_team_spec_dict
    from jiuwenswarm.agents.harness.team.team_manager import TeamManager
    from jiuwenswarm.common.config import get_config

    config = get_config()
    if TeamManager._is_distributed_mode(config):
        raise ValueError('configured_team_remote_execution_unsupported')
    name = metadata.get('team_name')
    if type(name) is not str or not name.strip():
        raise ValueError('configured_team_identity_unavailable')
    from jiuwenswarm.server.runtime.team_entity_store import TeamEntityStore

    entity = TeamEntityStore().get(name)
    template_id = entity.template_id if entity is not None else metadata.get('team_template_id')
    snapshot = entity.template_snapshot if entity is not None else metadata.get('team_template_snapshot')
    if not template_id and not isinstance(snapshot, dict):
        raise ValueError('configured_team_template_unavailable')
    spec = load_team_spec_dict(config_base=config, template_id=template_id,
                              template_snapshot=snapshot, strict_template=True)
    if (spec.get('spawn_mode') != 'inprocess' or spec.get('external_cli_agents')
            or any(member.get('cli_agent') for member in spec.get('predefined_members', []))):
        raise ValueError('configured_team_remote_execution_unsupported')


async def _mount_warm(state):
    from jiuwenswarm.agents.harness.team.rails.team_execution_rail import (
        TEAM_EXECUTION_CONTEXT, TEAM_EXECUTION_RAIL, TeamExecutionRail,
    )
    from openjiuwen.harness.schema.deep_agent_spec import RailSpec

    spec = state.spec
    if spec.spawn_mode != 'inprocess' or spec.build_context is None:
        raise ValueError('configured_team_runtime_guard_unavailable')
    original = spec.build_context.extras.get(TEAM_EXECUTION_CONTEXT)
    if (original is not None and original is not state
            and (type(original) is not _TeamRun or original.producer is None or not original.producer.done())):
        raise ValueError('configured_team_already_managed')
    physical = state.manager.get_stream_task(state.scope.session_id)
    state.preserve_original = physical is not None and not physical.done()
    if state.preserve_original:
        # This is an observer/control on existing Text work, not a replacement
        # execution policy. Never touch member specs, models, or original rails.
        leader = state.sdk_owner.agent
        if leader.harness is None:
            raise ValueError('configured_team_member_owner_unavailable')
        await leader.harness.register_rail(TeamExecutionRail(
            state, role=leader.role, member_name=leader.member_name, control_only=True))
        return
    agents = [state.sdk_owner.agent]
    for handle in state.sdk_owner.agent._spawn_manager.spawned_handles.values():
        member = getattr(handle, 'agent_ref', None)
        if member is None:
            raise ValueError('configured_team_member_owner_unavailable')
        agents.append(member)
    if any(member.harness is None or member.harness.build_context is None for member in agents):
        raise ValueError('configured_team_member_owner_unavailable')
    # A paused owner's next physical execution owns a fresh guard. The same
    # original specs/context propagate it to later in-process member rebuilds.
    spec.build_context.extras[TEAM_EXECUTION_CONTEXT] = state
    for member in spec.agents.values():
        member.rails = [rail for rail in member.rails or [] if rail.type != TEAM_EXECUTION_RAIL]
        member.rails.append(RailSpec(type=TEAM_EXECUTION_RAIL))
    for member in agents:
        harness = member.harness
        harness.build_context.extras[TEAM_EXECUTION_CONTEXT] = state
        harness._agent_spec.rails = [rail for rail in harness._agent_spec.rails or []
                                     if rail.type != TEAM_EXECUTION_RAIL] + [RailSpec(type=TEAM_EXECUTION_RAIL)]
        for old in harness.find_rails(TeamExecutionRail):
            await harness.unregister_rail(old)
        await harness.register_rail(TeamExecutionRail(state, role=member.role, member_name=member.member_name))


def get_configured_team_execution(service, agent, *, scope, execution_id, before_effect):
    _guard(before_effect, None)
    entry = _find(service, agent, scope, execution_id)
    state = entry.capability_state
    run = state.run if type(state) is _TeamControl else state
    if type(run) is not _TeamRun or run.scope != scope:
        raise ValueError('configured_team_scope_mismatch')
    _guard(before_effect, run.capability)
    return _fact(entry, state)


def list_configured_team_executions(service, agent, *, scope, before_effect):
    _guard(before_effect, None)
    return [get_configured_team_execution(service, agent, scope=scope,
        execution_id=entry.request.request_id, before_effect=before_effect)
        for kind in (_KIND, _CONTROL)
        for entry in service.list_internal(agent, session_id=scope.session_id, kind=kind)]


def _find(service, agent, scope, execution_id):
    for kind in (_KIND, _CONTROL):
        for entry in service.list_internal(agent, session_id=scope.session_id, kind=kind):
            if entry.request.request_id == execution_id:
                return entry
    raise ValueError('configured_team_execution_unavailable')


async def cancel_configured_team_execution(service, agent, request, *, scope, execution_id, before_effect):
    _guard(before_effect, None)
    entry = _find(service, agent, scope, execution_id)
    observed = entry.capability_state
    # Follow an observed control only to its retained original physical owner.
    # The short control task is never a substitute for cancelling the Team.
    state = observed.run if type(observed) is _TeamControl else observed
    if state.scope != scope or request.session_id != scope.session_id or request.channel_id != scope.channel_id:
        raise ValueError('configured_team_scope_mismatch')
    _guard(before_effect, state.capability)
    if state.producer is None or state.manager is None:
        raise ValueError('configured_team_producer_unavailable')
    def admit_cancel():
        _guard(before_effect, state.capability)
        state.cancelled = True
    result = await state.manager.cancel_stream_task_exact(scope.session_id,
        expected_task=state.producer, before_effect=admit_cancel)
    return {**_fact(entry, observed), 'cancel_requested': result}
