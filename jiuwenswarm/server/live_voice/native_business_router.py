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
from jiuwenswarm.common.live_voice_profiling import profile_event, error_fields
from jiuwenswarm.server.runtime.agent_adapter.formal_live_voice import FormalContextSnapshot
from jiuwenswarm.server.runtime.session.session_history import load_history_records
from .native_business_contract import NATIVE_BUSINESS_CONTRACT_VERSION, NativeBusinessProposal, NativeBusinessViolation
from .native_business_context import NativeBusinessContextStore, formal_context, select_conversation_history
from .native_business_observation import (
    NATIVE_BUSINESS_OBSERVATION_VERSION, MAX_OBSERVATION_WAIT_MS,
    observation_cursor, canonical_native_receipt, is_task_acceptance_receipt,
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
        self._executors = {}
        self._executor_lock = asyncio.Lock()
        self._work_presentations = {}
        self._selected_work_events = {}
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

    async def _read_context(self, route):
        authority = await asyncio.to_thread(
            self.registry._p3_composition.prepare_production_intent_authority,
            bearer_token=None, operation="task.list", session_id=route.binding.session_id,
            native_authority=route.native_p3_authority,
        )
        read = await asyncio.to_thread(authority.reader.list_visible_tasks, authority.scope)
        history = await asyncio.to_thread(load_history_records, authority.scope.session_id)
        tasks = [{key: value for key, value in fact.canonical_dict().items() if key in {
            "task_id", "name", "state", "outcome", "revision_number", "attempt_id", "event_head",
            "supported_operations", "predecessor_task_id", "successor_task_id"}}
            for fact in read.tasks]
        snapshots = self.works().list(scope=authority.scope)
        await self._restore_task_projection(route, authority.scope, read.tasks)
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
        origins = set(self.task_origins(scope))
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

    def work_events(self, scope):
        events = []
        for snapshot in self.works().list(scope=scope):
            if snapshot.state.value not in {"completed", "failed", "unknown", "cancelled"}:
                continue
            identity = "native-work-event-" + hashlib.sha256(canonical_json_bytes({
                "scope": scope.to_dict(), "work_id": snapshot.work_id, "revision": snapshot.revision,
                "state": snapshot.state.value,
            })).hexdigest()
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

    async def _executor(self, route):
        from .agent_conversation_runtime import AgentConversationRuntime
        scope = route.binding.scope
        async with self._executor_lock:
            retained = self._executors.get(scope)
            if retained is not None:
                return retained[0]
            if len(self._executors) >= 32:
                raise NativeBusinessViolation("NATIVE_WORK_SCOPE_CAPACITY", code=ErrorCode.UNAVAILABLE)
            facade = await self.registry._agent_manager.get_agent(
                "live_voice_native_work", "agent", route.native_p3_authority.context.file_path, None)
            if facade is None or not callable(getattr(facade, "process_formal_live_voice_stream", None)):
                raise NativeBusinessViolation("FORMAL_AGENT_FACADE_UNAVAILABLE", code=ErrorCode.UNAVAILABLE)
            pin = getattr(self.registry._agent_manager, "pin_agent", None)
            if callable(pin):
                pin(facade)
            identity = hashlib.sha256(canonical_json_bytes(scope.to_dict())).hexdigest()
            runtime = AgentConversationRuntime(scope=scope, instance_id="native-work-service:" + identity,
                facade=facade, enabled=True, max_concurrency=4, max_requests=128)
            try:
                if not await runtime.start():
                    raise NativeBusinessViolation("NATIVE_WORK_EXECUTOR_UNAVAILABLE", code=ErrorCode.UNAVAILABLE)
            except BaseException:
                unpin = getattr(self.registry._agent_manager, "unpin_agent", None)
                if callable(unpin):
                    unpin(facade)
                raise
            self._executors[scope] = (runtime, facade)
            return runtime

    async def _work(self, route, delegate, admission, selection):
        from .native_work_runtime import context_identity
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
            return await executor.execute_native_work(control=control, commit=commit, context=context,
                correlation_id=route.binding.correlation_id, channel_id="web", allow_tools=True)
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
        current.context.require_usable(scope=route.binding.scope,
            required_permissions=frozenset({"task.execute", "project.write"}), destructive=False, now=now)
        if current.context.file_path != route.native_p3_authority.context.file_path:
            raise NativeBusinessViolation("EXECUTION_CONTEXT_SCOPE_MISMATCH", code=ErrorCode.PERMISSION_DENIED)

    async def _task(self, route, delegate, request_id):
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
            proposal=action.task_proposal(), commit=None, source_id=delegate.source_identity)
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
        return {"status": "dispatched", "operation": action.operation,
                "task_id": formal.payload.get("result", {}).get("task_id", action.target_id),
                "receipt": formal.payload.get("result")}

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
            # Only the observed terminal-race reason is needed for this surface.
            # Other rejection details remain with the authenticated Task owner.
            reason = facts.get("requested_adjustment_reason")
            return {**identity, "state": state, "event_head": head,
                    "timing": "observed_before_receipt_sealed",
                    "reason": reason if reason == "TASK_TERMINAL_BEFORE_ADJUSTMENT" else None}
        except Exception:
            return unknown

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
            fresh = await self.context(route)
            invalid = None
            try:
                selection = fresh if delegate.business.operation == "context.get" else self.contexts.require(route.binding.scope, delegate.business)
            except NativeBusinessViolation as error:
                selection, invalid = fresh, error.reason
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
                        facts = await self._task(route, delegate, delegate.source_identity)
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
                if is_task_acceptance_receipt(result):
                    # The durable Task has already accepted this exact command.
                    # Observation refresh runs separately; it cannot delay or
                    # redefine the acceptance receipt or its journal sealing.
                    result["context_refresh_reason"] = "NATIVE_BUSINESS_CONTEXT_REQUIRES_REFRESH"
                else:
                    try:
                        result["context"] = (await self.context(route)).payload()
                    except Exception as error:
                        result["context_refresh_reason"] = getattr(error, "reason", "NATIVE_BUSINESS_CONTEXT_UNAVAILABLE")
                if delegate.business.operation == "task.adjust" and result.get("status") == "dispatched":
                    result["adjustment_observation"] = await self._adjustment_observation(route, result)
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
        response_id = "native-work-response-" + hashlib.sha256(event_id.encode()).hexdigest()
        admission = await route.native_runtime_owner.accept_work_provider_response(provider_response_id, response_id, turn_id=turn_id)
        self._work_presentations[(route.binding.scope, admission.response)] = event_id
        return admission

    def acknowledge_work(self, route, response):
        key = (route.binding.scope, response)
        event_id = self._work_presentations.get(key)
        if event_id is not None:
            self._work_journal.mark_presented(event_id, route.binding.scope)
            self._work_presentations.pop(key, None)
            self.works().wake_observers(route.binding.scope)

    def interrupt_work_presentation(self, route, response):
        key = (route.binding.scope, response)
        event_id = self._work_presentations.get(key)
        if event_id is not None:
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
        for scope, (runtime, facade) in tuple(self._executors.items()):
            result = await runtime.close(timeout_seconds=1.0)
            if getattr(result, "closed", False) or runtime.snapshot().closed:
                unpin = getattr(self.registry._agent_manager, "unpin_agent", None)
                if callable(unpin):
                    unpin(facade)
                del self._executors[scope]
