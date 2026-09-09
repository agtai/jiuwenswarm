# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Authenticated structured Native calls into existing Task and Agent owners.

The Registry owns admission and transport. This adapter never classifies text,
invents a semantic decision, completes a Task, or turns speech STOP into work
cancellation. Durable call receipts precede their spoken presentation.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from datetime import UTC, datetime

from jiuwenswarm.common.schema.live_voice_contract_v2 import ErrorCode, canonical_json_bytes
from jiuwenswarm.common.live_voice_profiling import profile_event, error_fields, profiled, ProfileSpan
from jiuwenswarm.server.runtime.agent_adapter.formal_live_voice import FormalContextSnapshot
from jiuwenswarm.server.runtime.session.session_history import load_history_records
from .native_business_contract import NATIVE_BUSINESS_CONTRACT_VERSION, NativeBusinessProposal, NativeBusinessViolation
from .native_business_context import NativeBusinessContextStore, formal_context, select_conversation_history
from .native_business_observation import (
    NATIVE_BUSINESS_OBSERVATION_VERSION, MAX_OBSERVATION_WAIT_MS,
    observation_cursor, canonical_native_receipt, is_task_acceptance_receipt, is_task_feedback_receipt,
)
from .native_interaction_contract import NativeInteractionBinding
from .native_interaction_runtime import NativeInteractionRuntimeError
from .voice_task_bridge import UnifiedCommittedInputRoute


def _now():
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


class NativeBusinessRouter:
    def __init__(self, registry):
        self.registry = registry
        self.contexts = NativeBusinessContextStore()
        self._work_owner = None
        self._work_journal = None
        self._work_presentations = {}
        self._selected_work_events = {}
        self._task_events = {}
        self._context_reads = {}
        self._context_read_sequence = 0

    def require_route(self, *, binding, capability, session_id):
        from .product_p2_interaction_adapter import P2LeaseState
        registry = self.registry
        route = registry._p2_routes.get((session_id, binding.interaction_id))
        if (registry._stopped or route is None or not route.native_business_enabled
            or route.native_runtime_owner is None or route.native_p3_authority is None
            or route.native_closed or route.native_close_retry is not None
            or route.activation_lease.snapshot().state is not P2LeaseState.OPEN
            or binding.scope.session_id != session_id or route.binding.scope != binding.scope
            or route.binding.correlation_id != binding.correlation_id
            or route.binding.activation_id != binding.activation_id
            or route.binding.activation_generation != binding.activation_generation
            or type(capability) is not str or route.native_capability is None
            or not hmac.compare_digest(route.native_capability, capability)):
            raise NativeBusinessViolation("NATIVE_RUNTIME_CAPABILITY_REJECTED", code=ErrorCode.PERMISSION_DENIED)
        return route

    def works(self):
        if self._work_owner is None:
            from .native_work_runtime import NativeWorkRuntime
            from .native_work_journal import SqliteNativeWorkJournal
            if self.registry._unified_journal is None:
                raise NativeBusinessViolation("NATIVE_WORK_JOURNAL_UNAVAILABLE", code=ErrorCode.UNAVAILABLE)
            self._work_journal = SqliteNativeWorkJournal(self.registry._unified_journal.database_path)
            self._work_owner = NativeWorkRuntime(save=self._work_journal.save, restored=self._work_journal.restore())
        return self._work_owner

    @staticmethod
    def _work_fact(snapshot):
        return {key: value for key, value in snapshot.to_dict().items() if key in {
            "work_id", "revision", "sequence", "instruction", "state", "reason", "input_id",
            "model_identity", "model_config_version", "execution_settled"}}

    async def context(self, route):
        return (await self._context_result(route))[0]

    async def _context_result(self, route):
        key = id(route)
        operation = self._context_reads.get(key)
        if operation is None:
            if len(self._context_reads) >= 128:
                raise NativeBusinessViolation("NATIVE_CONTEXT_READ_CAPACITY", code=ErrorCode.UNAVAILABLE)
            operation = asyncio.create_task(self._read_context(route))
            self._context_reads[key] = operation
            def finished(task):
                if self._context_reads.get(key) is task:
                    self._context_reads.pop(key, None)
                if not task.cancelled():
                    task.exception()
            operation.add_done_callback(finished)
        return await asyncio.shield(operation)

    @profiled("native.context_read", "route.binding")
    async def _read_context(self, route):
        with ProfileSpan("native.context_authorize"):
            authority = await asyncio.to_thread(
                self.registry._p3_composition.prepare_production_intent_authority,
                bearer_token=None, operation="task.list", session_id=route.binding.session_id,
                native_authority=route.native_p3_authority,
            )
        with ProfileSpan("native.context_task_read"):
            read = await asyncio.to_thread(authority.reader.list_visible_tasks, authority.scope)
        with ProfileSpan("native.context_history_read"):
            history = await asyncio.to_thread(load_history_records, authority.scope.session_id)
        tasks = [{key: value for key, value in fact.canonical_dict().items() if key in {
            "task_id", "name", "state", "outcome", "revision_number", "attempt_id", "event_head",
            "supported_operations", "predecessor_task_id", "successor_task_id"}}
            for fact in read.tasks]
        snapshots = self.works().list(scope=authority.scope)
        with ProfileSpan("native.context_projection_restore"):
            await self._restore_task_projection(route, authority.scope, read.tasks)
        from .task_control_presentation import native_task_presentation
        task_facts, task_events = await asyncio.to_thread(
            native_task_presentation, self.registry._p3_composition._core.store,
            authority.scope, [task["task_id"] for task in tasks],
            presented=self._work_journal.presented,
        )
        for task in tasks:
            task.update(task_facts[task["task_id"]])
        self._task_events[authority.scope] = task_events
        while len(self._task_events) > 128:
            self._task_events.pop(next(iter(self._task_events)))
        ordered = sorted(snapshots, key=lambda item: (
            item.state.value in {"accepted", "running", "cancelling"} or not item.execution_settled,
            item.updated_at), reverse=True)
        works = [self._work_fact(snapshot) for snapshot in ordered[:32]]
        native = route.native_p3_authority
        selection = self.contexts.select(scope=authority.scope,
            history=select_conversation_history(history), tasks=tasks, works=works,
            model={"model_identity": native.model_identity, "model_config_version": native.model_config_version})
        self._context_read_sequence += 1
        return selection, self._context_read_sequence

    def _require_current_context_route(self, route):
        from .product_p2_interaction_adapter import P2LeaseState
        composition = self.registry._p3_composition
        if self.registry._stopped or not composition._accepting:
            raise NativeBusinessViolation("NATIVE_WORK_AUTHORITY_UNAVAILABLE", code=ErrorCode.UNAVAILABLE)
        if (self.registry._p2_routes.get((route.binding.session_id, route.binding.interaction_id)) is not route
            or route.native_closed or route.native_close_retry is not None
            or route.activation_lease.snapshot().state is not P2LeaseState.OPEN):
            raise NativeBusinessViolation("NATIVE_RUNTIME_CAPABILITY_REJECTED", code=ErrorCode.PERMISSION_DENIED)

    @profiled("native.authority_reread", "route.binding", require_context=True)
    async def _require_context_authority(self, route):
        self._require_current_context_route(route)
        composition = self.registry._p3_composition
        now = composition._clock()
        # The resolver reads project/session files and executes Git. Never run
        # this blocking I/O on the audio event loop or under the registry lock.
        current = await asyncio.to_thread(composition._resolve_native_activation_authority, route.native_p3_authority,
            operation="task.list", session_id=route.binding.session_id, now=now, require_clean=False)
        self._recheck_context_authority(route, current)
        return current

    def _recheck_context_authority(self, route, current):
        """Pure in-memory fence, including time spent waiting for a shared lock."""
        self._require_current_context_route(route)
        now = self.registry._p3_composition._clock()
        route.native_p3_authority.principal.require_usable(operation="task.list", now=now)
        current.context.require_usable(scope=route.binding.scope,
            required_permissions=frozenset(), destructive=False, now=now)

    async def _restore_task_projection(self, route, scope, tasks):
        """Join durable creation evidence with fresh authorized Task facts.

        A create receipt may settle after replacement activation discovery. Each
        authenticated refresh repairs that projection without replaying the call
        or allowing the retired route to overwrite the current activation.
        """
        from .product_composition_registry import _VoiceTaskOrigin
        from .product_p2_interaction_adapter import P2LeaseState
        # Recovery scans the durable input journal. It must not block the
        # audio/RPC event loop while another Task is writing that same store.
        self.works()
        origins = set(await asyncio.to_thread(self.task_origins, scope))
        restored = [task.task_id for task in tasks if task.task_id in origins]
        current = await self._require_context_authority(route)
        async with self.registry._lock:
            self._recheck_context_authority(route, current)
            if (self.registry._stopped or route.native_closed
                or self.registry._p2_routes.get((route.binding.session_id, route.binding.interaction_id)) is not route
                or route.activation_lease.snapshot().state is not P2LeaseState.OPEN):
                return
            for task_id in restored:
                prior = self.registry._voice_task_origins.get(task_id)
                if prior is not None and (prior.session_id, prior.interaction_id, prior.activation_id,
                    prior.activation_generation, prior.correlation_id) == (route.binding.session_id,
                    route.binding.interaction_id, route.binding.activation_id, route.binding.activation_generation,
                    route.binding.correlation_id):
                    continue
                if prior is None and len(self.registry._voice_task_origins) >= self.registry._PRODUCT_OPERATION_CAPACITY:
                    continue
                self.registry._voice_task_origins[task_id] = _VoiceTaskOrigin(
                    session_id=scope.session_id, interaction_id=route.binding.interaction_id,
                    activation_id=route.binding.activation_id, activation_generation=route.binding.activation_generation,
                    correlation_id=route.binding.correlation_id, response_ref=None)

    def _record_task_origin(self, route, delegate, admission, result):
        if (result.get("status") != "dispatched" or not result.get("task_id")
            or delegate.business.operation not in {"task.create", "task.create_successor"}):
            return None
        try:
            self.works()
            self._work_journal.record_task_origin(route.binding.scope, result["task_id"],
                delegate.source_identity, admission.turn_commit.commit_id)
        except Exception as error:
            return getattr(error, "reason", "NATIVE_TASK_ORIGIN_UNAVAILABLE")
        return None

    @staticmethod
    def _work_event_id(snapshot):
        return "native-work-event-" + hashlib.sha256(canonical_json_bytes({
            "scope": snapshot.scope.to_dict(), "work_id": snapshot.work_id,
            "revision": snapshot.revision, "state": snapshot.state.value,
        })).hexdigest()

    def work_events(self, scope):
        self.works()
        events = [event for event in self._task_events.get(scope, ())
                  if not self._work_journal.presented(event["event_id"], scope)]
        for snapshot in self.works().list(scope=scope):
            if snapshot.state.value not in {"completed", "failed", "unknown", "cancelled"}:
                continue
            identity = self._work_event_id(snapshot)
            if self._work_journal.presented(identity, scope) or self._work_journal.suppressed(identity, scope):
                continue
            events.append({"event_id": identity, "work_id": snapshot.work_id, "revision": snapshot.revision,
                "state": snapshot.state.value, "result_text": snapshot.result_text, "reason": snapshot.reason})
        # One application result owns the output slot. Keep that selection until
        # actual delivery, interruption, or revision retirement, so another
        # completion never displaces speech already in progress. Full results
        # stay queryable; this also bounds one serialized audio handoff.
        selected = self._selected_work_events.get(scope)
        event = next((event for event in events if event["event_id"] == selected), None)
        if event is None and events:
            event = events[0]
        if event is None:
            self._selected_work_events.pop(scope, None)
            return []
        self._selected_work_events[scope] = event["event_id"]
        return [event]

    async def context_request(self, *, params, request_id, session_id):
        from .product_composition_registry import _success_result, _error_result
        try:
            observing = params.get("contract_version") == NATIVE_BUSINESS_OBSERVATION_VERSION
            if observing:
                if (set(params) != {"contract_version", "binding", "capability", "after", "wait_ms"}
                        or type(params["wait_ms"]) is not int or not 0 <= params["wait_ms"] <= MAX_OBSERVATION_WAIT_MS):
                    raise NativeBusinessViolation("NATIVE_BUSINESS_CONTEXT_REQUEST_INVALID")
                try:
                    after = observation_cursor(params["after"])
                except ValueError:
                    raise NativeBusinessViolation("NATIVE_BUSINESS_CONTEXT_REQUEST_INVALID") from None
            elif set(params) != {"contract_version", "binding", "capability", "context"} or params["context"] is not True:
                raise NativeBusinessViolation("NATIVE_BUSINESS_CONTEXT_REQUEST_INVALID")
            binding = NativeInteractionBinding.from_dict(params["binding"])
            async with self.registry._lock:
                route = self.require_route(binding=binding, capability=params["capability"], session_id=session_id)
            owner = self.works()
            if observing:
                await owner.wait_for_observation(scope=binding.scope, after=after, wait_ms=params["wait_ms"])
            # Capture the work cursor before reading facts. A transition during
            # the read remains observable by the following wait instead of lost.
            cursor = owner.observation_cursor(binding.scope)
            context, read_sequence = await self._context_result(route)
            cursor["read_sequence"] = read_sequence
            # Never return facts after the authenticated activation was retired.
            current = await self._require_context_authority(route)
            async with self.registry._lock:
                self._recheck_context_authority(route, current)
                self.require_route(binding=binding, capability=params["capability"], session_id=session_id)
            return _success_result(request_id, {"kind": "business_observation" if observing else "business_context",
                "contract_version": NATIVE_BUSINESS_OBSERVATION_VERSION if observing else NATIVE_BUSINESS_CONTRACT_VERSION,
                **({"cursor": cursor} if observing else {}),
                "context": context.payload(), "work_events": self.work_events(binding.scope)}, route.manifest)
        except Exception as error:
            return _error_result(request_id, reason=getattr(error, "reason", "NATIVE_BUSINESS_CONTEXT_UNAVAILABLE"),
                code=getattr(error, "code", ErrorCode.UNAVAILABLE))

    async def _agent(self, route, delegate):
        from jiuwenswarm.server.runtime.agent_resolution import find_session_agent

        await self._require_context_authority(route)
        manager = self.registry._agent_manager
        owner = await find_session_agent(manager, channel_id="web",
            session_id=route.binding.scope.session_id,
            project_dir=route.native_p3_authority.context.file_path)
        await self._require_context_authority(route)
        arguments = dict(session_id=route.binding.scope.session_id)
        action = delegate.business
        if action.operation in {"agent.pending", "agent.reply"}:
            from jiuwenswarm.common.schema.agent import AgentRequest
            from jiuwenswarm.server.runtime.agent_interrupt_execution import list_agent_interrupts, reply_agent_interrupt

            if owner.project_id != route.binding.scope.project_id:
                raise NativeBusinessViolation("EXECUTION_CONTEXT_SCOPE_MISMATCH", code=ErrorCode.PERMISSION_DENIED)
            mutates = action.operation == "agent.reply"
            current = await (self._require_work_authority(route) if mutates else self._require_context_authority(route))

            def guard():
                self._recheck_context_authority(route, current)
                now = self.registry._p3_composition._clock()
                route.native_p3_authority.principal.require_usable(
                    operation="agent.chat" if mutates else "task.list", now=now)
                current.context.require_usable(scope=route.binding.scope,
                    required_permissions=frozenset({"task.execute", "project.write"}) if mutates else frozenset(),
                    destructive=False, now=now)

            if not mutates:
                return list_agent_interrupts(manager.executions, owner.agent, **arguments, before_read=guard)
            request = AgentRequest(request_id=delegate.source_identity, channel_id="web",
                session_id=route.binding.scope.session_id, params={})
            return await reply_agent_interrupt(manager.executions, owner.agent, request,
                source_binding_id=action.target_id, source_task_id=action.source_task_id,
                expected_pending_token=action.pending_token, input_id=action.input_id,
                answers=action.answers, before_effect=guard)
        if delegate.business.operation == "agent.list":
            return manager.executions.list(owner.agent, **arguments)
        return manager.executions.observe(owner.agent, **arguments,
                                          execution_id=delegate.business.target_id)

    async def _goal(self, route, delegate=None):
        from jiuwenswarm.server.runtime.agent_resolution import find_session_agent
        from openjiuwen.harness.goal.schema import GoalOperationError

        await self._require_context_authority(route)
        owner = await find_session_agent(self.registry._agent_manager, channel_id="web",
            session_id=route.binding.scope.session_id,
            project_dir=route.native_p3_authority.context.file_path)
        await self._require_context_authority(route)
        action = delegate.business if delegate is not None else None
        if action is None or action.operation == "goal.get":
            # No await between the final authority check and the snapshot.
            return {"goal": owner.agent.peek_session_goal(route.binding.scope.session_id),
                    "source": "session_agent"}
        await self._require_work_authority(route)
        if action.operation in {"goal.set", "goal.resume"}:
            return await self._start_goal(route, delegate, owner)
        effect_admitted = False

        async def before_effect():
            nonlocal effect_admitted
            # SDK invokes this inside its control lock, including time spent
            # waiting behind a text command. Reread registry/project authority;
            # the preflight snapshot cannot authorize a later effect.
            current = await self._require_work_authority(route)
            self._recheck_context_authority(route, current)
            now = self.registry._p3_composition._clock()
            route.native_p3_authority.principal.require_usable(operation="agent.chat", now=now)
            current.context.require_usable(scope=route.binding.scope,
                required_permissions=frozenset({"task.execute", "project.write"}), destructive=False, now=now)
            effect_admitted = True

        operation = action.operation.split(".", 1)[1]
        try:
            goal = await owner.agent.control_session_goal(route.binding.scope.session_id,
                action=operation, goal_id=action.target_id, control_revision=action.expected_revision,
                before_effect=before_effect)
        except GoalOperationError as error:
            return {"status": "rejected", "reason": "GOAL_" + error.code.upper(), "error": str(error)}
        except Exception:
            if not effect_admitted:
                raise
            # SDK may have saved state before persistence or cancellation
            # failed. The command journal must retain this as uncertain.
            return {"status": "unknown", "reason": "GOAL_CONTROL_OUTCOME_UNKNOWN",
                    "action": operation, "goal_id": action.target_id, "observation_required": True}
        return {"action": operation, "goal": None if operation == "clear" else goal,
                "cleared_goal": goal if operation == "clear" else None, "source": "session_agent"}

    async def _start_goal(self, route, delegate, owner):
        from jiuwenswarm.common.schema.agent import AgentRequest
        from jiuwenswarm.common.schema.message import ReqMethod
        from jiuwenswarm.server.runtime.execution_context import AgentExecutionPolicy

        action = delegate.business
        operation = action.operation.split(".", 1)[1]
        native = route.native_p3_authority
        admitted = False
        entry = None

        async def before_effect():
            nonlocal admitted
            current = await self._require_work_authority(route)
            if not admitted:
                # Initial admission requires the live authenticated carrier.
                # Detached execution keeps its project/principal grant, rather
                # than being cancelled when that speech carrier later closes.
                self._recheck_context_authority(route, current)
            resolver = self.registry._p3_composition._model_resolver
            resolver.resolve(native.model_identity, expected_identity=native.model_identity,
                expected_config_version=native.model_config_version, instantiate=False)
            work = entry.prepared_work if entry is not None else None
            if (work is not None and work.policy is entry.policy
                    and entry.policy.before_effect is before_effect):
                # The service coalesces repeated control requests. Keep the
                # original guard's admission evidence on that exact entry so a
                # replay cannot lose it or infer it from an arbitrary snapshot.
                entry._native_goal_admission = (work, entry.policy)
                admitted = True

        params = {"action": operation, "mode": owner.canonical_mode,
                  "work_mode": owner.work_mode, "project_dir": owner.project_dir,
                  "model_name": native.model_identity}
        if action.target_id is not None:
            params.update(expected_goal_id=action.target_id,
                          expected_control_revision=action.expected_revision)
        if operation == "set":
            params.update(objective=action.instruction,
                          overwrite_confirmed=action.target_id is not None)
        request = AgentRequest(
            request_id="native-goal." + hashlib.sha256(delegate.source_identity.encode()).hexdigest(),
            channel_id="web", session_id=route.binding.scope.session_id,
            req_method=ReqMethod.COMMAND_GOAL, params=params, is_stream=True,
            metadata={"enable_memory": False, "skip_a2ui": True})
        service = self.registry._agent_manager.executions
        entry = service.start_bound(owner.agent, request, policy=AgentExecutionPolicy(
            origin="native", tool_policy="read_only", model_identity=native.model_identity,
            model_config_version=native.model_config_version, before_effect=before_effect))
        try:
            result = await service.wait_control_result(entry)
        except Exception:
            # Scheduling/timeout/EOF does not prove whether SDK control saved.
            return {"status": "unknown", "reason": "GOAL_CONTROL_OUTCOME_UNKNOWN",
                    "action": operation, "execution_id": request.request_id,
                    "observation_required": True}
        if result.get("event_type") != "goal.snapshot":
            return {"status": "rejected", "reason": result.get("code") or "GOAL_CONTROL_REJECTED",
                    "action": operation, "goal": result.get("goal") or result.get("existing_goal")}
        work = entry.prepared_work
        evidence = getattr(entry, "_native_goal_admission", None)
        if (work is None or type(evidence) is not tuple or len(evidence) != 2
                or evidence[0] is not work or evidence[1] is not entry.policy
                or work.policy is not entry.policy):
            return {"status": "unknown", "reason": "GOAL_CONTROL_ADMISSION_UNOBSERVED",
                    "action": operation, "observation_required": True}
        goal = result.get("goal")
        receipt = {"status": "accepted", "action": operation, "goal": goal,
                   "execution_id": request.request_id, "source": "session_agent"}
        if (operation == "resume" and isinstance(goal, dict)
                and goal.get("goal_id") == action.target_id
                and type(goal.get("control_revision")) is int
                and goal["control_revision"] == action.expected_revision):
            # An ACTIVE resume retains its actual Goal run context. This ID
            # identifies the control request; shared observation follows the
            # original output owner, with its original model and tool policy.
            receipt["execution_binding"] = "preserved"
        return receipt

    async def _workflow(self, route, delegate):
        from jiuwenswarm.common.schema.agent import AgentRequest
        from jiuwenswarm.common.schema.message import ReqMethod
        from jiuwenswarm.server.runtime.workflow_queries import query_workflows

        await self._require_context_authority(route)
        action = delegate.business
        if action.operation == "workflow.start":
            return await self._team(route, delegate)
        if action.operation == "workflow.reply":
            from jiuwenswarm.server.runtime.team_workflow_capabilities import reply_swarmflow

            current = await self._require_work_authority(route)
            admitted = False

            def before_effect():
                nonlocal admitted
                self._recheck_context_authority(route, current)
                now = self.registry._p3_composition._clock()
                route.native_p3_authority.principal.require_usable(operation="agent.chat", now=now)
                current.context.require_usable(scope=route.binding.scope,
                    required_permissions=frozenset({"task.execute", "project.write"}),
                    destructive=False, now=now)
                admitted = True

            try:
                ok, reason = await reply_swarmflow(session_id=route.binding.scope.session_id,
                    run_id=action.target_id, correlation_id=action.input_id,
                    answer=action.instruction, channel_id="web", before_effect=before_effect)
            except Exception:
                if not admitted:
                    raise
                return {"status": "unknown", "reason": "WORKFLOW_REPLY_OUTCOME_UNKNOWN",
                        "workflow_id": action.target_id, "input_id": action.input_id}
            if ok and not admitted:
                return {"status": "unknown", "reason": "WORKFLOW_REPLY_ADMISSION_UNOBSERVED",
                        "workflow_id": action.target_id, "input_id": action.input_id}
            return {"status": "input_accepted" if ok else "rejected", "reason": reason,
                    "workflow_id": action.target_id, "input_id": action.input_id,
                    "source": "session_team"}
        response = await query_workflows(AgentRequest(
            request_id=delegate.source_identity,
            channel_id="web",
            session_id=route.binding.scope.session_id,
            req_method=ReqMethod.COMMAND_WORKFLOWS,
            params={"action": action.operation.split(".", 1)[1], "workflow_id": action.target_id},
        ))
        # Checkpoint I/O may outlive the activation or its project grant.
        await self._require_context_authority(route)
        if not response.ok:
            return {"status": "rejected", "reason": "WORKFLOW_QUERY_UNAVAILABLE", **response.payload}
        return response.payload

    async def _configured_execution_owner(self, route, *, mutates):
        from jiuwenswarm.server.runtime.agent_resolution import find_session_agent

        require = self._require_work_authority if mutates else self._require_context_authority
        current = await require(route)
        owner = await find_session_agent(self.registry._agent_manager, channel_id="web", session_id=route.binding.scope.session_id,
                                         project_dir=current.context.file_path)
        current = await require(route)
        self._recheck_context_authority(route, current)
        if owner.project_id != route.binding.scope.project_id:
            raise NativeBusinessViolation("EXECUTION_CONTEXT_SCOPE_MISMATCH", code=ErrorCode.PERMISSION_DENIED)
        return owner, current

    def _configured_execution_guard(self, route, owner, current, *, mutates, capability_scope=None):
        """Shared Native authority; capability owners retain execution semantics."""
        admitted = False

        def guard(capability=None):
            nonlocal admitted
            # Accepted Team/Workflow work outlives speech. Current service,
            # principal and project permissions still fence every later effect.
            if not admitted or not mutates:
                self._recheck_context_authority(route, current)
            composition = self.registry._p3_composition
            if self.registry._stopped or not composition._accepting:
                raise NativeBusinessViolation("NATIVE_WORK_AUTHORITY_UNAVAILABLE", code=ErrorCode.UNAVAILABLE)
            now = composition._clock()
            route.native_p3_authority.principal.require_usable(
                operation="agent.chat" if mutates else "task.list", now=now)
            required = frozenset(capability.required_permissions) if capability is not None and capability_scope is not None else frozenset()
            if mutates:
                required |= {"task.execute", "project.write"}
            current.context.require_usable(scope=route.binding.scope,
                required_permissions=required, destructive=False, now=now)
            if (current.context.file_path != owner.project_dir
                    or capability is not None and capability_scope is not None and capability.scope != capability_scope):
                raise NativeBusinessViolation("EXECUTION_CONTEXT_SCOPE_MISMATCH", code=ErrorCode.PERMISSION_DENIED)
            if capability_scope is None or capability is not None:
                admitted = True

        return guard

    async def _team(self, route, delegate):
        from jiuwenswarm.common.schema.agent import AgentRequest
        from jiuwenswarm.server.runtime.team_execution_capabilities import TeamExecutionScope, inspect_configured_team
        from jiuwenswarm.server.runtime.team_execution import (
            SwarmflowStartIntent, start_configured_team, get_configured_team_execution,
            list_configured_team_executions, cancel_configured_team_execution,
        )

        action = delegate.business
        operation = action.operation.split(".", 1)[1]
        mutates = operation in {"start", "cancel"}
        owner, current = await self._configured_execution_owner(route, mutates=mutates)
        scope = TeamExecutionScope("web", route.binding.scope.session_id, owner.project_dir,
                                  owner.project_id, owner.canonical_mode, owner.work_mode)
        manager = self.registry._agent_manager
        service = manager.executions
        if operation != "list" and action.epoch != service.execution_epoch:
            raise NativeBusinessViolation("TEAM_EXECUTION_EPOCH_MISMATCH")
        guard = self._configured_execution_guard(route, owner, current, mutates=mutates)
        if operation == "list":
            capability = await inspect_configured_team(manager, scope=scope, before_read=guard)
            executions = list_configured_team_executions(service, owner.agent, scope=scope, before_effect=guard)
            return {"epoch": service.execution_epoch, "configured_team": capability, "executions": executions}
        if operation == "get":
            return get_configured_team_execution(service, owner.agent, scope=scope,
                execution_id=action.target_id, before_effect=guard)
        request = AgentRequest(request_id=delegate.source_identity, channel_id="web", session_id=scope.session_id,
            params={"query": action.instruction or delegate.request_text})
        if operation == "cancel":
            return await cancel_configured_team_execution(service, owner.agent, request, scope=scope,
                execution_id=action.target_id, before_effect=guard)
        intent = SwarmflowStartIntent(**action.inputs) if action.operation == "workflow.start" else None
        return await start_configured_team(service, owner.agent, request, scope=scope,
            expected_fingerprint=action.fingerprint, before_effect=guard, swarmflow=intent)

    async def _core_workflow(self, route, delegate):
        """Thin Native admission into the common registered Core Workflow owner."""
        from jiuwenswarm.common.schema.agent import AgentRequest
        from jiuwenswarm.common.schema.message import ReqMethod
        from jiuwenswarm.server.runtime.core_workflow_capabilities import CoreWorkflowScope
        from jiuwenswarm.server.runtime.core_workflow_execution import (
            list_core_workflows, get_core_workflow, start_core_workflow, resume_core_workflow,
        )

        action = delegate.business
        operation = action.operation.split(".", 1)[1]
        mutates = operation in {"start", "resume"}
        owner, current = await self._configured_execution_owner(route, mutates=mutates)
        scope = CoreWorkflowScope("web", route.binding.scope.session_id,
                                  route.binding.scope.project_id, owner.canonical_mode)
        service = self.registry._agent_manager.executions
        if operation != "list" and action.epoch != service.execution_epoch:
            raise NativeBusinessViolation("CORE_WORKFLOW_EPOCH_MISMATCH")
        native_guard = self._configured_execution_guard(route, owner, current, mutates=mutates, capability_scope=scope)
        installed = getattr(self.registry._agent_manager, "core_workflow_host", None)

        def before_effect(capability):
            native_guard(capability)
            if installed is not None:
                installed.guard(scope, operation, capability)

        if installed is not None and operation in {"list", "start"}:
            installed.bind_scope(scope, operation=operation, before_read=lambda: before_effect(None))
        if operation == "list":
            return list_core_workflows(service, owner.agent, scope=scope, before_effect=before_effect)
        if operation == "get":
            return get_core_workflow(service, owner.agent, scope=scope,
                                     run_id=action.target_id, before_effect=before_effect)
        request = AgentRequest(request_id=delegate.source_identity, channel_id="web",
            session_id=scope.session_id, req_method=ReqMethod.COMMAND_WORKFLOWS,
            params={"kind": "core", "action": operation, "mode": owner.canonical_mode,
                    "project_dir": owner.project_dir, "work_mode": owner.work_mode})
        if operation == "start":
            return await start_core_workflow(service, owner.agent, request=request, scope=scope,
                epoch=action.epoch, capability_id=action.capability_id, inputs=action.inputs,
                before_effect=before_effect)
        return await resume_core_workflow(service, owner.agent, request=request, scope=scope,
            epoch=action.epoch, run_id=action.target_id, expected_revision=action.expected_revision,
            answers=action.answers, before_effect=before_effect)

    async def _executor(self, route):
        # This is the ordinary configured Agent capability. Code remains its
        # separate configured capability; Work never rebinds a cached Code facade.
        facade = await self.registry._agent_manager.get_agent(
            "web", "agent", route.native_p3_authority.context.file_path, None)
        if facade is None or not callable(getattr(facade, "process_formal_live_voice_stream", None)):
            raise NativeBusinessViolation("FORMAL_AGENT_FACADE_UNAVAILABLE", code=ErrorCode.UNAVAILABLE)
        return facade

    async def _work(self, route, delegate, admission, selection):
        from .native_work_runtime import context_identity, execute_native_work
        action = delegate.business
        # Admission/journal I/O can yield after context selection. Query and
        # cancellation, as well as execution, need authority at their effect.
        await self._require_context_authority(route)
        owner, scope = self.works(), route.binding.scope
        if action.operation == "work.list":
            return {"works": [{key: value for key, value in self._work_fact(item).items() if key != "instruction"}
                for item in owner.list(scope=scope)], "details_operation": "work.get"}
        if action.operation == "work.get":
            return {"work": owner.query(scope=scope, work_id=action.target_id).to_dict()}
        if action.operation == "work.cancel":
            return {"work": (await owner.cancel(scope=scope, work_id=action.target_id, revision=action.expected_revision)).to_dict()}
        specification = formal_context(scope, {"instruction": action.instruction,
            "current_request": delegate.request_text, "source_identity": delegate.source_identity},
            source="live_voice.native_work_specification")
        context = FormalContextSnapshot(scope, selection.formal.entries + specification.entries)
        commit = admission.turn_commit
        executor = await self._executor(route)
        await self._require_work_authority(route)
        async def run(control):
            control.check()
            await self._require_work_authority(route)
            control.check()
            return await execute_native_work(service=self.registry._agent_manager.executions,
                agent=executor, control=control, commit=commit, context=context)
        arguments = dict(scope=scope, request_id=delegate.source_identity, input_id=commit.commit_id,
            instruction=action.instruction, model_identity=route.native_p3_authority.model_identity,
            model_config_version=route.native_p3_authority.model_config_version,
            context_id=context_identity(context), runner=run)
        if action.operation == "work.start":
            # These are explicit conversational analyses; background artifact
            # Tasks have their own P3 execution owner and do not consume this slot.
            snapshot = await owner.start(**arguments, foreground=True)
        else:
            snapshot = await owner.update(**arguments, work_id=action.target_id, revision=action.expected_revision)
        return {"work": self._work_fact(snapshot)}

    async def _require_work_authority(self, route):
        composition = self.registry._p3_composition
        if self.registry._stopped or not composition._accepting:
            raise NativeBusinessViolation("NATIVE_WORK_AUTHORITY_UNAVAILABLE", code=ErrorCode.UNAVAILABLE)
        now = composition._clock()
        current = await asyncio.to_thread(composition._resolve_native_activation_authority,
            route.native_p3_authority, operation="agent.chat", session_id=route.binding.session_id,
            now=now, require_clean=False)
        # The resolver performs blocking I/O. Detached work keeps its carrier
        # independence, but every effect still requires a live service and grant
        # at the time that read finishes.
        if self.registry._stopped or not composition._accepting:
            raise NativeBusinessViolation("NATIVE_WORK_AUTHORITY_UNAVAILABLE", code=ErrorCode.UNAVAILABLE)
        now = composition._clock()
        route.native_p3_authority.principal.require_usable(operation="agent.chat", now=now)
        current.context.require_usable(scope=route.binding.scope,
            required_permissions=frozenset({"task.execute", "project.write"}), destructive=False, now=now)
        if current.context.file_path != route.native_p3_authority.context.file_path:
            raise NativeBusinessViolation("EXECUTION_CONTEXT_SCOPE_MISMATCH", code=ErrorCode.PERMISSION_DENIED)
        return current

    @profiled("native.task_intent", "route.binding", "delegate", require_context=True)
    async def _task(self, route, delegate, request_id, *, native_source=None):
        from .production_task_intent import (ProductionTaskIntentRequest, ProductionIntentOrigin,
            build_production_origin_binding, ProductionTaskPolicyOutcome)
        from .p3_production_intent_composition import CallLocalProductionOriginAuthority
        from .product_composition_registry import _RejectingProductionConfirmationConsumer
        registry = self.registry
        action = delegate.business
        authority = await asyncio.to_thread(registry._p3_composition.prepare_production_intent_authority,
            bearer_token=None, operation=action.operation, session_id=route.binding.session_id,
            native_authority=route.native_p3_authority)
        request = ProductionTaskIntentRequest(origin=ProductionIntentOrigin.STRUCTURED, scope=authority.scope,
            command_id="native-command." + hashlib.sha256(delegate.source_identity.encode()).hexdigest(),
            proposal=action.task_proposal(), commit=None, source_id=delegate.source_identity,
            native_source=native_source)
        origin = CallLocalProductionOriginAuthority(expected_binding=build_production_origin_binding(request), commit_ledger=None)
        resolution = await asyncio.to_thread(registry._task_intent_bridge.resolve_production,
            request, authority.reader, origin, _RejectingProductionConfirmationConsumer(), registry._production_clarification_owner)
        if resolution.outcome is not ProductionTaskPolicyOutcome.PROPOSED:
            return {"status": "rejected", "reason": resolution.reason, "operation": action.operation}
        clean = {"source": "structured", "source_id": delegate.source_identity, "session_id": route.binding.session_id,
                 "correlation_id": route.binding.correlation_id}
        if action.mutates:
            if not registry._p3_control_ready():
                raise NativeBusinessViolation("P3_CONFIRMATION_ISSUER_UNAVAILABLE", code=ErrorCode.UNAVAILABLE)
            if action.operation in {"task.create", "task.create_successor"}:
                registry._p3_composition.require_local_artifact_delegation_capability(resolution)
            else:
                registry._p3_composition.require_local_task_control_capability(resolution)
            token = await registry._issue_production_confirmation_continuation(clean=clean, request_id=request_id,
                proposal=request.proposal, resolution=resolution, commit=None, authority=authority,
                replacing_token=None, clarification_answer_fingerprint=None)
            async with registry._lock:
                pending = registry._pending_production_task_intents[token]
            # Use the existing durable confirmation claim and final exact scope,
            # model, revision and capability reread; no invented second utterance.
            _, formal = await registry._confirm_production_intent(clean=clean, request_id=request_id, pending=pending,
                request=request, authority=authority, origin_authority=origin, preliminary=resolution,
                native_authority=route.native_p3_authority)
        else:
            formal = await registry._invoke_production_resolution(clean=clean, request_id=request_id,
                resolution=resolution, origin_authority=origin, confirmation_consumer=None,
                native_authority=route.native_p3_authority)
        if not formal.ok:
            return {"status": "rejected", "operation": action.operation, "error": formal.payload.get("error")}
        result = {"status": "dispatched", "operation": action.operation,
                "task_id": formal.payload.get("result", {}).get("task_id", action.target_id),
                "receipt": formal.payload.get("result")}
        if action.operation in {"task.status", "task.result"}:
            await self._task_result_facts(route, result)
        return result

    async def _task_result_facts(self, route, result):
        from .task_control_presentation import native_task_presentation
        try:
            facts, events = await asyncio.to_thread(native_task_presentation,
                self.registry._p3_composition._core.store, route.binding.scope, [result["task_id"]], maximum_result_bytes=0,
                presented=self._work_journal.presented)
            result["task_control"] = facts[result["task_id"]]
            result["task_notifications"] = events
            self._task_events[route.binding.scope] = [event for event in self._task_events.get(route.binding.scope, ())
                if event["task_id"] != result["task_id"]] + events
        except Exception:
            # Read failure must not rewrite an accepted mutation or saved result.
            result["task_control_reason"] = "NATIVE_TASK_CONTROL_UNAVAILABLE"

    async def _adjustment_observation(self, route, result):
        """Seal one as-of control read without changing the durable command receipt."""
        receipt = result.get("receipt")
        unknown = {"state": "unknown", "observation_reason": "NATIVE_ADJUSTMENT_RECEIPT_INVALID"}
        if (type(receipt) is not dict or receipt.get("task_id") != result.get("task_id")
                or any(type(receipt.get(key)) is not str or not receipt[key]
                       or len(receipt[key].encode("utf-8")) > 256
                       for key in ("task_id", "attempt_id", "adjustment_id"))):
            return unknown
        identity = {key: receipt[key] for key in ("task_id", "attempt_id", "adjustment_id")}
        unknown = {**identity, "state": "unknown", "observation_reason": "NATIVE_ADJUSTMENT_OBSERVATION_UNAVAILABLE"}
        try:
            facts = await self.registry._p3_composition.read_task_control_snapshot(
                bearer_token=None, session_id=route.binding.session_id,
                native_authority=route.native_p3_authority,
                task_id=identity["task_id"], adjustment_id=identity["adjustment_id"],
            )
            state = facts.get("requested_adjustment_state")
            head = facts.get("event_head")
            if (facts.get("task_id") != identity["task_id"] or facts.get("attempt_id") != identity["attempt_id"]
                    or type(state) is not str or state not in {"pending", "applied", "rejected", "unknown"}
                    or type(head) is not int or not 0 <= head <= 9_007_199_254_740_991
                    or (receipt.get("adjustment_state") in {"applied", "rejected"}
                        and state not in {receipt["adjustment_state"], "unknown"})):
                return {**unknown, "observation_reason": "NATIVE_ADJUSTMENT_OBSERVATION_MISMATCH"}
            reason = facts.get("requested_adjustment_reason")
            return {**identity, "state": state, "event_head": head,
                    "timing": "observed_before_receipt_sealed",
                    "reason": reason,
                    **({"execution_mode": "followup", "continuation_task_id": facts["followup_adjustment"].get("continuation_task_id")}
                       if "followup_adjustment" in facts else {})}
        except Exception:
            return unknown

    @profiled("native.business", "retained_route.binding", "proposal.delegate")
    async def handle(self, *, owner, proposal, request_id, retained_route, **unused):
        from .product_composition_registry import _success_result, _error_result, _VoiceTaskOrigin
        delegate = proposal.delegate
        route = retained_route
        try:
            if not route.native_business_enabled or not isinstance(delegate, NativeBusinessProposal):
                raise NativeBusinessViolation("NATIVE_BUSINESS_CAPABILITY_REQUIRED")
            if (proposal.action is None or proposal.action.operation != "DELEGATE"
                or dict(proposal.action.payload) != {"provider_call_id": delegate.provider_call_id, "turn_id": delegate.turn_id}
                or any(value is not None for value in (proposal.turn_commit, proposal.input_transcript, proposal.audio_observation, proposal.provider_done))):
                raise NativeBusinessViolation("NATIVE_BUSINESS_PROPOSAL_INVALID")
            route.activation_lease.propose_action(route.binding, proposal.action)
            invalid = None
            try:
                if delegate.business.operation == "context.get":
                    selection = await self.context(route)
                else:
                    # The proposal names an immutable, already-observed context.
                    # Fresh authority and the operation's own Task reader still
                    # validate current scope/revision before any real effect.
                    await self._require_context_authority(route)
                    selection = self.contexts.require(route.binding.scope, delegate.business)
            except NativeBusinessViolation as error:
                profile_event("native_context_check", stage=delegate.business.operation,
                    observed_context_id=delegate.business.context_id,
                    requested_target_id=delegate.business.target_id,
                    provider_call_id=delegate.provider_call_id, reason=error.reason,
                    outcome="rejected")
                if error.reason != "NATIVE_BUSINESS_CONTEXT_STALE" and error.reason not in {
                    "NATIVE_BUSINESS_TARGET_NOT_OBSERVED", "NATIVE_BUSINESS_REVISION_NOT_OBSERVED"}:
                    raise
                selection, invalid = await self.context(route), error.reason
            entries = selection.formal.entries
            if invalid is None and delegate.business.operation in {"work.start", "work.update"}:
                specification = formal_context(route.binding.scope, {"instruction": delegate.business.instruction,
                    "current_request": delegate.request_text, "source_identity": delegate.source_identity},
                    source="live_voice.native_work_specification")
                entries += specification.entries
            accepted, admission = await owner.admit_delegate(delegate, committed_at=_now(),
                context_refs=tuple(entry.ref for entry in entries))
            profile_event("native_business", milestone="admitted", request_id=request_id,
                session_id=route.binding.session_id, provider_call_id=delegate.provider_call_id,
                turn_commit_id=admission.turn_commit.commit_id, context_id=selection.context_id,
                stage=delegate.business.operation)
            journal = self.registry._unified_journal
            identity = delegate.source_identity.split(":", 1)[1]
            fingerprint = bytes.fromhex(identity)
            admitted = await asyncio.to_thread(journal.admit, request_id=delegate.source_identity,
                voice_identity_sha256=identity, fingerprint=fingerprint, created_at=admission.turn_commit.committed_at)
            result = admitted.replay_result
            if result is None and not admitted.execute:
                result = await asyncio.to_thread(journal.wait_for_completion, voice_identity_sha256=identity, fingerprint=fingerprint)
                if result is None:
                    raise NativeBusinessViolation("NATIVE_BUSINESS_OUTCOME_UNKNOWN", code=ErrorCode.RESULT_UNKNOWN)
            if result is None:
                try:
                    if invalid:
                        facts = {"status": "rejected", "reason": invalid}
                    elif delegate.business.operation == "context.get":
                        facts = {"status": "observed"}
                    elif delegate.business.operation.startswith("task."):
                        from .native_task_source import SOURCE_OPERATIONS
                        with ProfileSpan("native.task_source_wait"):
                            source = (await owner.task_source(admission)
                                      if delegate.business.operation in SOURCE_OPERATIONS else None)
                        # A source wait is not permission to dispatch after close
                        # or project rebind. Recheck before any Task mutation.
                        await self._require_context_authority(route)
                        facts = await self._task(route, delegate, delegate.source_identity, native_source=source)
                    elif delegate.business.operation.startswith("core_workflow."):
                        facts = await self._core_workflow(route, delegate)
                    elif delegate.business.operation.startswith("workflow."):
                        facts = await self._workflow(route, delegate)
                    elif delegate.business.operation.startswith("goal."):
                        facts = await self._goal(route, delegate)
                    elif delegate.business.operation.startswith("agent."):
                        facts = await self._agent(route, delegate)
                    elif delegate.business.operation.startswith("team."):
                        facts = await self._team(route, delegate)
                    else:
                        facts = await self._work(route, delegate, admission, selection)
                    result = {"contract_version": NATIVE_BUSINESS_CONTRACT_VERSION, "operation": delegate.business.operation, **facts}
                except Exception as error:
                    profile_event("native_business", milestone="failed", request_id=request_id,
                        provider_call_id=delegate.provider_call_id, **error_fields(error))
                    result = {"contract_version": NATIVE_BUSINESS_CONTRACT_VERSION, "operation": delegate.business.operation,
                        "status": "rejected", "reason": getattr(error, "reason", "NATIVE_BUSINESS_EXECUTION_FAILED")}
                # Save the creation association before any optional await. A
                # reconnect can discover the true receipt even while refresh is
                # pending. Recording is idempotent and also retried on replay.
                if (result.get("status") == "dispatched" and result.get("task_id")
                    and delegate.business.operation in {"task.create", "task.create_successor"}):
                    result["native_origin"] = {
                        "scope_sha256": hashlib.sha256(canonical_json_bytes(route.binding.scope.to_dict())).hexdigest(),
                        "source_identity": delegate.source_identity, "commit_id": admission.turn_commit.commit_id}
                origin_reason = self._record_task_origin(route, delegate, admission, result)
                if origin_reason is not None:
                    result["task_origin_reason"] = origin_reason
                # A failed optional context refresh cannot rewrite a committed
                # Task receipt as a rejected operation or invite a new mutation.
                if is_task_acceptance_receipt(result) or is_task_feedback_receipt(result):
                    # Speak this exact operation's receipt without rebuilding
                    # all Task/history context. A later dependent operation
                    # still requires fresh context and its own authority read.
                    result["context_refresh_reason"] = "NATIVE_BUSINESS_CONTEXT_REQUIRES_REFRESH"
                else:
                    try:
                        result["context"] = (await self.context(route)).payload()
                    except Exception as error:
                        result["context_refresh_reason"] = getattr(error, "reason", "NATIVE_BUSINESS_CONTEXT_UNAVAILABLE")
                if delegate.business.operation == "task.adjust" and result.get("status") == "dispatched":
                    result["adjustment_observation"] = await self._adjustment_observation(route, result)
                    await self._task_result_facts(route, result)
                    observed = result["adjustment_observation"]
                    result["task_notifications"] = [event for event in result.get("task_notifications", ())
                        if event["adjustment_id"] == observed.get("adjustment_id") and event["state"] == observed.get("state")]
                if (len(canonical_json_bytes(result)) > 262144
                    or len(json.dumps(result, ensure_ascii=True, separators=(",", ":")).encode()) > 524288):
                    result.pop("context", None)
                    result["context_refresh_reason"] = "NATIVE_BUSINESS_CONTEXT_REQUIRES_REFRESH"
                result = await asyncio.to_thread(journal.complete, voice_identity_sha256=identity, fingerprint=fingerprint,
                    result=result, completed_at=_now())
            else:
                # Repair projection persistence from the same durable receipt;
                # the original Task effect and replay payload remain unchanged.
                self._record_task_origin(route, delegate, admission, result)
            text = canonical_native_receipt(result)
            profile_event("native_business", milestone="receipt_ready", request_id=request_id,
                provider_call_id=delegate.provider_call_id, turn_commit_id=admission.turn_commit.commit_id,
                output_chars=len(text), result_state=result.get("status", "observed"))
            result_route = UnifiedCommittedInputRoute.TASK if delegate.business.operation.startswith("task.") else UnifiedCommittedInputRoute.DIALOGUE
            prepared = await owner.prepare_delegate_result(admission, canonical_text=text, route=result_route, allow_interrupted=True)
            task_id = result.get("task_id")
            if type(task_id) is str:
                async with self.registry._lock:
                    if (self.registry._p2_routes.get((route.binding.session_id, route.binding.interaction_id)) is route
                        and not route.native_closed and not self.registry._stopped
                        and (task_id in self.registry._voice_task_origins
                            or len(self.registry._voice_task_origins) < self.registry._PRODUCT_OPERATION_CAPACITY)):
                        self.registry._voice_task_origins[task_id] = _VoiceTaskOrigin(
                            session_id=route.binding.session_id, interaction_id=route.binding.interaction_id,
                            activation_id=route.binding.activation_id, activation_generation=route.binding.activation_generation,
                            correlation_id=route.binding.correlation_id, response_ref=prepared.response)

            await self._require_context_authority(route)
            return _success_result(request_id, {"kind": "delegate", "status": "prepared", "accepted": accepted,
                "provider_call_id": delegate.provider_call_id, "route": result_route.value,
                "turn_commit_id": admission.turn_commit.commit_id, "canonical_text": text,
                **({"task_id": task_id} if type(task_id) is str else {}),
                "response": {"interaction_id": prepared.response.interaction_id,
                    "response_id": prepared.response.response_id, "response_generation": prepared.response.response_generation}}, route.manifest)
        except Exception as error:
            profile_event("native_business", milestone="rejected", request_id=request_id, **error_fields(error))
            return _error_result(request_id, reason=getattr(error, "reason", "NATIVE_BUSINESS_REJECTED"),
                code=getattr(error, "code", ErrorCode.UNAVAILABLE), manifest=route.manifest)
        finally:
            if delegate is not None:
                await owner.release_failed_delegate(delegate.provider_call_id)

    def task_origins(self, scope):
        self.works()
        self._work_journal.recover_task_origins(scope)
        return self._work_journal.task_origins(scope)

    async def admit_work_response(self, route, *, event_id, provider_response_id, turn_id):
        if not route.activation_lease.task_notification_foreground_safe(route.binding):
            raise NativeInteractionRuntimeError("NATIVE_RESPONSE_PRESENTATION_BUSY", "work result waits for the shared foreground presentation owner")
        events = self.work_events(route.binding.scope)
        if not any(event["event_id"] == event_id for event in events):
            raise NativeInteractionRuntimeError("NATIVE_WORK_EVENT_STALE", "work result is no longer current")
        if len(self._work_presentations) >= 128:
            raise NativeInteractionRuntimeError("NATIVE_WORK_PRESENTATION_CAPACITY", "work presentation ledger is full")
        # The result identity survives interruption; each actual generation has
        # its own response identity while an exact Provider replay stays stable.
        response_id = "native-work-response-" + hashlib.sha256(canonical_json_bytes({
            "event_id": event_id, "provider_response_id": provider_response_id,
        })).hexdigest()
        admission = await route.native_runtime_owner.accept_work_provider_response(provider_response_id, response_id, turn_id=turn_id)
        self._work_presentations[(route.binding.scope, admission.response)] = (event_id,)
        return admission

    async def admit_business_response(self, route, *, provider_response_id, call_id, turn_id):
        """Bind explicit result queries and notifications to one delivery ledger."""
        owner, scope = route.native_runtime_owner, route.binding.scope
        receipts = owner.business_query_receipts(call_id, turn_id)
        if receipts and len(self._work_presentations) >= 128:
            raise NativeInteractionRuntimeError("NATIVE_WORK_PRESENTATION_CAPACITY", "work presentation ledger is full")
        admission = await owner.accept_delegate_provider_response(provider_response_id, call_id, turn_id)
        # Admission freezes every sibling call onto the same response. Inspect
        # server receipts, not a model's claim that it used a particular result.
        events = set()
        for text in receipts:
            receipt = json.loads(text)
            if receipt.get("status") != "rejected" and receipt.get("operation") in {"task.status", "task.result", "task.adjust"}:
                for event in receipt.get("task_notifications", ()):
                    if event in self._task_events.get(scope, ()) and not self._work_journal.presented(event["event_id"], scope):
                        events.add(event["event_id"])
            if receipt.get("operation") != "work.get" or receipt.get("status") == "rejected":
                continue
            fact = receipt.get("work")
            if not isinstance(fact, dict):
                continue
            snapshot = next((item for item in self.works().list(scope=scope)
                             if item.work_id == fact.get("work_id")), None)
            # A later revision/state may have appeared while the query's answer
            # waited. It must never be consumed by that old answer's ACK.
            if (snapshot is None or snapshot.state.value not in {"completed", "failed", "unknown", "cancelled"}
                    or snapshot.to_dict() != fact):
                continue
            identity = self._work_event_id(snapshot)
            if not self._work_journal.presented(identity, scope) and not self._work_journal.suppressed(identity, scope):
                events.add(identity)
        if events:
            self._work_presentations[(scope, admission.response)] = tuple(sorted(events))
        return admission

    def acknowledge_work(self, route, response):
        key = (route.binding.scope, response)
        events = self._work_presentations.get(key)
        if events is not None:
            for event_id in events:
                self._work_journal.mark_presented(event_id, route.binding.scope)
            self._work_presentations.pop(key, None)
            self.works().wake_observers(route.binding.scope)

    def release_unheard_work_response(self, route, response):
        # A failed or transcript-free generation cannot produce canonical heard
        # history. Release its in-memory binding without consuming the result.
        self._work_presentations.pop((route.binding.scope, response), None)

    def interrupt_work_presentation(self, route, response):
        key = (route.binding.scope, response)
        events = self._work_presentations.get(key)
        if events is not None:
            for event_id in events:
                if not any(event["event_id"] == event_id for event in self._task_events.get(route.binding.scope, ())):
                    self._work_journal.mark_suppressed(event_id, route.binding.scope, "speech_interrupted")
            self._work_presentations.pop(key, None)
            self.works().wake_observers(route.binding.scope)

    def retire_activation(self, route):
        if self._work_owner is not None:
            self._work_owner.wake_observers(route.binding.scope)
        for scope, response in tuple(self._work_presentations):
            if scope == route.binding.scope and response.interaction_id == route.binding.interaction_id:
                self._work_presentations.pop((scope, response), None)

    async def close(self):
        reads = tuple(self._context_reads.values())
        for read in reads:
            read.cancel()
        if reads:
            await asyncio.gather(*reads, return_exceptions=True)
        if self._work_owner is not None:
            await self._work_owner.close()
