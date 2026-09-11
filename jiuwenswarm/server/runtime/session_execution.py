# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Service-owned consumers of configured Agent output, shared by text and voice.

This projects the existing facade's events. It does not infer business completion
from EOF, run another Agent scheduler, authorize callers, or persist a Task.
"""
from __future__ import annotations

import asyncio
from collections import OrderedDict, deque
from copy import deepcopy
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
import hashlib
import json
from uuid import uuid4
from typing import Any, AsyncIterator

from jiuwenswarm.common.schema.agent import AgentRequest, AgentResponseChunk
from jiuwenswarm.common.e2a.wire_codec import _json_safe
from jiuwenswarm.server.runtime.session.session_manager import SessionManager
from jiuwenswarm.server.runtime.agent_adapter.formal_live_voice import FormalAgentExecution, FormalAgentOutput
from jiuwenswarm.server.runtime.execution_context import (
    AgentExecutionPolicy, PreparedAgentWork, ExecutionContextUnavailable, context_binding_id,
)


_CURRENT_EXECUTION: ContextVar[tuple | None] = ContextVar("configured_agent_output_owner", default=None)


def current_output_observer(sdk_agent):
    """Internal SDK admission hook; never populated from AgentRequest metadata.

    Facade child tasks inherit this service binding. SDK invokes the returned
    synchronous callback under its own control lock, before scheduling work.
    """
    current = _CURRENT_EXECUTION.get()
    if current is None:
        return None
    service, entry = current
    return lambda token, acquired: service._bind_output(entry, sdk_agent, token, acquired)


def prepare_current_work(*, sdk_agent, session_id, apply_runtime, permission_context=None):
    """Bind host configuration before the SDK admits this request's work."""
    current = _CURRENT_EXECUTION.get()
    if current is None:
        return None
    service, entry = current
    return service, service._prepare_work(entry, sdk_agent=sdk_agent,
        session_id=session_id, apply_runtime=apply_runtime, permission_context=permission_context)


def current_execution_policy():
    current = _CURRENT_EXECUTION.get()
    return current[1].policy if current is not None else None


def current_output_is_managed():
    """Distinguish an actual prepared reader from legacy/Team compatibility."""
    current = _CURRENT_EXECUTION.get()
    return current is not None and (
        current[1].prepared_work is not None or current[1].policy is not None
    )


def current_prepared_work(sdk_agent):
    current = _CURRENT_EXECUTION.get()
    if current is None or current[1].prepared_work is None:
        return None
    work = current[1].prepared_work
    if work.sdk_agent is not sdk_agent:
        raise ExecutionContextUnavailable("AGENT_WORK_OWNER_MISMATCH")
    current[0]._require_work_live(current[1])
    return work


def current_output_work(payload):
    """Resolve projected provenance inside the real service-owned consumer."""
    current = _CURRENT_EXECUTION.get()
    if current is None:
        if isinstance(payload, dict) and "source_binding_id" in payload:
            raise ExecutionContextUnavailable("AGENT_OUTPUT_OWNER_UNAVAILABLE")
        return None
    return current[0].resolve_output_work(current[1], payload)


def observe_current_agent_interrupt(sdk_agent, chunk, question):
    """Capture an exact pending question at the actual SDK output seam."""
    current = _CURRENT_EXECUTION.get()
    if current is not None:
        from jiuwenswarm.server.runtime.agent_interrupt_execution import observe_agent_interrupt
        observe_agent_interrupt(current[0], current[1], sdk_agent, chunk, question)


def current_agent_interrupt_requires_exact_reply(agent, request):
    """Fence the legacy ID-only answer path before it creates another work."""
    current = _CURRENT_EXECUTION.get()
    if current is None:
        return False
    service, _ = current
    session_id = SessionManager.get_session_id(request.session_id)
    from jiuwenswarm.server.runtime.agent_interrupt_execution import has_managed_agent_pending
    return has_managed_agent_pending(service, agent, session_id)


class SessionExecutionUnavailable(ValueError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass
class _Execution:
    agent: Any
    request: AgentRequest
    fingerprint: str
    retained: bool
    events: deque = field(default_factory=deque)
    event_bytes: int = 0
    sequence: int = 0
    changed: asyncio.Event = field(default_factory=asyncio.Event)
    task: asyncio.Task | None = None
    observers: dict = field(default_factory=dict)
    stream_closed: bool = False
    stream_outcome: str | None = None
    cancellation_requested: bool = False
    output_owner: _Execution | None = None
    formal: FormalAgentExecution | None = None
    result_text: str | None = None
    failure_reason: str | None = None
    policy: AgentExecutionPolicy | None = None
    prepared_work: PreparedAgentWork | None = None
    internal_kind: str | None = None
    internal_producer: Any = None
    capability_state: Any = None
    retain_record: bool = False
    control_only: bool = False
    agent_interrupt: Any = None

    def wake(self) -> None:
        old, self.changed = self.changed, asyncio.Event()
        old.set()


class SessionExecutionService:
    """Hold facade producers and provide isolated, bounded output projections.

    Callers authorize the exact configured Agent and session before using this
    service. Request replay is coalesced only while its in-memory record exists;
    durable Native command admission remains owned by the unified journal.
    """

    # Leave room for Native's operation envelope and context reference below
    # the journal's 256 KiB UTF-8 and presentation's 512 KiB ASCII JSON limits.
    PROJECTION_UTF8_BYTES = 96 * 1024
    PROJECTION_ASCII_BYTES = 192 * 1024

    def __init__(self, manager, *, max_records=128, max_active=32,
                 max_events=1024, max_event_bytes=4 * 1024 * 1024, max_observers=32):
        if any(type(value) is not int or value <= 0 for value in
               (max_records, max_active, max_events, max_event_bytes, max_observers)) or max_active > max_records:
            raise ValueError("invalid execution projection bounds")
        self.manager = manager
        self.max_records, self.max_active = max_records, max_active
        self.max_events, self.max_event_bytes = max_events, max_event_bytes
        self.max_observers = max_observers
        self._records: OrderedDict[tuple, _Execution] = OrderedDict()
        self._output_owners: dict[tuple, _Execution] = {}
        self._closed = False
        self._loop = None
        self._execution_epoch = uuid4().hex

    @property
    def execution_epoch(self):
        return self._execution_epoch

    def start_internal(self, agent, request, *, kind, producer, capability_state, retain_record=True, control_only=False):
        """Admit a trusted capability producer through the same bounded owner.

        Producer and state are host objects, never populated from wire fields.
        Retained records preserve admission replay for this service epoch.
        """
        if (not isinstance(kind, str) or not kind or kind.strip() != kind
                or not callable(producer) or type(retain_record) is not bool or type(control_only) is not bool):
            raise SessionExecutionUnavailable("CAPABILITY_PRODUCER_INVALID")
        return self._start(agent, request, retained=True, internal_kind=kind,
            internal_producer=producer, capability_state=capability_state,
            retain_record=retain_record, control_only=control_only)

    def get_internal(self, agent, *, session_id, execution_id, kind):
        entry = self._find(agent, session_id, execution_id)
        if entry.internal_kind != kind:
            raise SessionExecutionUnavailable("CAPABILITY_EXECUTION_KIND_MISMATCH")
        return entry

    def restart_internal_control(self, entry, request, *, expected_state, producer, capability_state):
        """Retry a proven unclaimed Agent answer within its existing ledger slot.

        The interrupt adapter must synchronously recheck the SDK pending origin
        immediately before this call. No other failed execution is restartable.
        """
        self._require_loop()
        key = self._key(entry.agent, SessionManager.get_session_id(request.session_id), request.request_id)
        if self._records.get(key) is not entry or entry.internal_kind != "agent.interrupt.reply" or not entry.control_only:
            raise SessionExecutionUnavailable("AGENT_INTERRUPT_RETRY_CONFLICT")
        # Reuse admission's exact fingerprint check without allocating a record.
        self.start_internal(entry.agent, request, kind=entry.internal_kind, producer=producer,
                            capability_state=capability_state, control_only=True)
        if entry.capability_state is not expected_state:
            return entry  # A concurrent retry already replaced this settled task.
        old_task = entry.task
        if (not entry.stream_closed or old_task is None or not old_task.done() or old_task.cancelled()
                or old_task.cancelling() or entry.cancellation_requested or entry.stream_outcome != "failed"
                or getattr(expected_state, "receipt", None) is not None
                or getattr(expected_state, "preclaim_retryable", False) is not True):
            raise SessionExecutionUnavailable("AGENT_INTERRUPT_RETRY_UNAVAILABLE")
        entry.internal_producer, entry.capability_state = producer, capability_state
        entry.stream_closed, entry.stream_outcome, entry.failure_reason = False, None, None
        self._launch(entry)
        return entry

    def list_internal(self, agent, *, session_id, kind):
        self._require_loop()
        self._key(agent, session_id, "observation")
        return tuple(entry for (owner, sid, _), entry in self._records.items()
                     if owner == id(agent) and sid == session_id and entry.internal_kind == kind)

    def _require_loop(self) -> None:
        loop = asyncio.get_running_loop()
        if self._loop is None:
            self._loop = loop
        if self._loop is not loop:
            raise SessionExecutionUnavailable("AGENT_STREAM_OWNER_LOOP_MISMATCH")

    @staticmethod
    def _key(agent, session_id, execution_id):
        if any(not isinstance(value, str) or not value.strip() for value in (session_id, execution_id)):
            raise SessionExecutionUnavailable("AGENT_STREAM_IDENTITY_INVALID")
        return id(agent), session_id, execution_id

    def start(self, agent, request: AgentRequest, *, retained=False) -> _Execution:
        """Consume this exact configured request once within the retained ledger."""
        return self._start(agent, request, retained=retained)

    def start_bound(self, agent, request: AgentRequest, *, policy: AgentExecutionPolicy):
        """An internal policy argument, never selected through wire metadata."""
        if not isinstance(policy, AgentExecutionPolicy):
            raise ExecutionContextUnavailable("AGENT_WORK_POLICY_INVALID")
        return self._start(agent, request, retained=True, policy=policy)

    def start_formal(self, agent, execution: FormalAgentExecution) -> _Execution:
        """Trusted committed input, using the same configured producer owner.

        Wire metadata cannot select this no-history/model-bound entry point.
        The public session owns observation; the formal facade owns its isolated
        SDK child and exact tool/model restrictions.
        """
        if not isinstance(execution, FormalAgentExecution):
            raise SessionExecutionUnavailable("INVALID_FORMAL_AGENT_INPUT")
        execution.context.validate_for(execution.commit)
        if not callable(getattr(agent, "process_formal_live_voice_stream", None)):
            raise SessionExecutionUnavailable("FORMAL_AGENT_FACADE_UNAVAILABLE")
        request = AgentRequest(request_id=execution.request_id,
            session_id=execution.commit.scope.session_id, channel_id=execution.channel_id,
            is_stream=True, params={"mode": "agent", "model_name": execution.model_identity})
        return self._start(agent, request, retained=True, formal=execution)

    def _start(self, agent, request, *, retained, formal=None, policy=None,
               internal_kind=None, internal_producer=None, capability_state=None, retain_record=False, control_only=False):
        self._require_loop()
        if self._closed:
            raise SessionExecutionUnavailable("AGENT_STREAM_SERVICE_CLOSED")
        key = self._key(agent, SessionManager.get_session_id(request.session_id), request.request_id)
        snapshot = deepcopy(request)
        wire_request = _json_safe(asdict(snapshot))
        if internal_kind is not None:
            wire_request = {"request": wire_request, "internal_kind": internal_kind, "control_only": control_only}
        if formal is not None:
            wire_request = {"request": wire_request, "formal": _json_safe(asdict(formal))}
        if policy is not None:
            wire_request = {"request": wire_request, "policy": {
                "origin": policy.origin, "tool_policy": policy.tool_policy,
                "model_identity": policy.model_identity,
                "model_config_version": policy.model_config_version,
            }}
        fingerprint = hashlib.sha256(json.dumps(wire_request, ensure_ascii=False,
            sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        previous = self._records.get(key)
        if previous is not None:
            if previous.fingerprint != fingerprint:
                raise SessionExecutionUnavailable("AGENT_STREAM_REQUEST_CONFLICT")
            # A replay is never permission to extend the original lifetime.
            return previous
        # Trusted short control producers do not execute another SDK workflow.
        # They must remain admissible when all execution slots await that input;
        # the common record bound still limits their total tasks and replay state.
        if not control_only and sum(not item.stream_closed and not item.control_only
                                    for item in self._records.values()) >= self.max_active:
            raise SessionExecutionUnavailable("AGENT_STREAM_CAPACITY")
        if len(self._records) >= self.max_records:
            evicted = next((candidate for candidate, item in self._records.items()
                            if item.stream_closed and not item.observers and not item.retain_record
                            and not (item.prepared_work is not None and self._work_is_live(item))), None)
            if evicted is None:
                raise SessionExecutionUnavailable("AGENT_STREAM_CAPACITY")
            self._records.pop(evicted)
        entry = _Execution(agent, snapshot, fingerprint, retained, formal=deepcopy(formal), policy=policy,
            internal_kind=internal_kind, internal_producer=internal_producer,
            capability_state=capability_state, retain_record=retain_record, control_only=control_only)
        self._launch(entry)
        self._records[key] = entry
        return entry

    def _launch(self, entry):
        self.manager.pin_agent(entry.agent)
        entry.task = asyncio.create_task(self._consume(entry), name=f"agent-output:{entry.request.request_id}")
        def finished(task):
            if entry.task is task:
                if entry.stream_outcome is None:
                    entry.stream_outcome = "cancelled" if task.cancelled() else "failed"
                entry.stream_closed = True
                entry.wake()
                for output_key, owner in tuple(self._output_owners.items()):
                    if owner is entry:
                        del self._output_owners[output_key]
            # Each physical task releases its own pin even if its record has
            # since moved to a confirmed preclaim retry.
            self.manager.unpin_agent(entry.agent)
            if not task.cancelled():
                task.exception()
        entry.task.add_done_callback(finished)

    def _work_is_live(self, entry):
        owner = entry.output_owner or entry
        return (not self._closed and not entry.cancellation_requested
                and entry.stream_outcome not in {"cancelled", "failed", "cleanup_failed"}
                and not owner.stream_closed and not owner.cancellation_requested
                and owner.task is not None and not owner.task.done() and not owner.task.cancelling())

    def _require_work_live(self, entry):
        self._require_loop()
        if not self._work_is_live(entry):
            raise ExecutionContextUnavailable("AGENT_WORK_BINDING_CLOSED")

    def _prepare_work(self, entry, *, sdk_agent, session_id, apply_runtime, permission_context):
        self._require_work_live(entry)
        if entry.formal is not None:
            # The formal facade already has its own isolated committed policy.
            raise ExecutionContextUnavailable("FORMAL_WORK_CONTEXT_ALREADY_OWNED")
        if entry.prepared_work is not None:
            if entry.prepared_work.sdk_agent is not sdk_agent or entry.prepared_work.sdk_session_id != session_id:
                raise ExecutionContextUnavailable("AGENT_WORK_OWNER_MISMATCH")
            return entry.prepared_work
        request = deepcopy(entry.request)
        request.session_id = SessionManager.get_session_id(request.session_id)
        entry.prepared_work = PreparedAgentWork(request=request,
            policy=entry.policy or AgentExecutionPolicy(), sdk_agent=sdk_agent,
            sdk_session_id=session_id, require_live=lambda: self._require_work_live(entry),
            apply_runtime=apply_runtime, permission_context=permission_context)
        return entry.prepared_work

    def resolve_work_context(self, *, sdk_agent, session_id, run_context):
        self._require_loop()
        binding_id = context_binding_id(run_context)
        if binding_id is None:
            return None
        for entry in self._records.values():
            work = entry.prepared_work
            if work is not None and work.binding_id == binding_id:
                work.require_context(sdk_agent=sdk_agent, session_id=session_id, run_context=run_context)
                return work
        raise ExecutionContextUnavailable("AGENT_WORK_BINDING_UNAVAILABLE")

    def resolve_output_work(self, reader, payload):
        self._require_loop()
        if not isinstance(payload, dict) or "source_binding_id" not in payload:
            return None
        for entry in self._records.values():
            work = entry.prepared_work
            if work is None or work.binding_id != payload["source_binding_id"]:
                continue
            owner = entry.output_owner or entry
            reader_owner = reader.output_owner or reader
            if (owner is reader_owner and entry.agent is reader.agent
                    and SessionManager.get_session_id(entry.request.session_id)
                    == SessionManager.get_session_id(reader.request.session_id)
                    and work.accepts_source(payload)):
                return work
            raise ExecutionContextUnavailable("AGENT_OUTPUT_SOURCE_MISMATCH")
        raise ExecutionContextUnavailable("AGENT_OUTPUT_BINDING_UNAVAILABLE")

    def _bind_output(self, entry, sdk_agent, token, acquired):
        self._require_loop()
        if (self._closed or entry.stream_closed or entry.cancellation_requested
                or entry.task.done() or entry.task.cancelling()):
            raise SessionExecutionUnavailable("AGENT_STREAM_OWNER_STOPPING")
        if not isinstance(token, str) or not token:
            raise SessionExecutionUnavailable("AGENT_STREAM_OUTPUT_IDENTITY_INVALID")
        work = entry.prepared_work
        if work is not None and work.sdk_agent is not sdk_agent:
            raise SessionExecutionUnavailable("AGENT_STREAM_OUTPUT_SDK_MISMATCH")
        key = (id(sdk_agent), token)
        owner = self._output_owners.get(key)
        if acquired:
            if owner is not None and owner is not entry:
                raise SessionExecutionUnavailable("AGENT_STREAM_OUTPUT_OWNER_CONFLICT")
            owner = entry
        elif owner is None:
            # Legacy/unmanaged readers can keep their text compatibility. They
            # cannot take custody of a service-retained invocation.
            if entry.retained:
                raise SessionExecutionUnavailable("AGENT_STREAM_OUTPUT_OWNER_UNOBSERVED")
            return
        if (owner.agent is not entry.agent
                or SessionManager.get_session_id(owner.request.session_id)
                != SessionManager.get_session_id(entry.request.session_id)):
            raise SessionExecutionUnavailable("AGENT_STREAM_OUTPUT_SCOPE_MISMATCH")
        if work is not None and owner is not entry:
            original = owner.prepared_work
            if (original is None or original.sdk_agent is not work.sdk_agent
                    or original.sdk_session_id != work.sdk_session_id):
                raise SessionExecutionUnavailable("AGENT_STREAM_OUTPUT_SDK_SCOPE_MISMATCH")
        if (owner.stream_closed or owner.cancellation_requested
                or owner.task.done() or owner.task.cancelling()):
            raise SessionExecutionUnavailable("AGENT_STREAM_OUTPUT_OWNER_STOPPING")
        # No await: the lease check and retention take effect before the SDK can
        # admit work or a text disconnect can cancel this actual producer.
        self._output_owners[key] = owner
        entry.output_owner = owner
        if entry.retained:
            owner.retained = True

    async def _publish(self, entry, chunk):
        # Preserve text backpressure. Passive list/get queries never subscribe
        # and cannot stall the existing facade producer.
        while any(len(queue) >= self.max_events for queue in entry.observers.values()):
            await entry.changed.wait()
        copied = deepcopy(chunk)
        payload = {
            "request_id": copied.request_id, "channel_id": copied.channel_id,
            "payload": _json_safe(deepcopy(copied.payload)), "is_complete": copied.is_complete,
            "agent_ref": _json_safe(copied.agent_ref or entry.request.agent_ref),
        }
        size = len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        entry.sequence += 1
        entry.events.append((entry.sequence, copied, payload, size))
        entry.event_bytes += size
        while entry.events and (len(entry.events) > self.max_events or entry.event_bytes > self.max_event_bytes):
            entry.event_bytes -= entry.events.popleft()[3]
        for queue in entry.observers.values():
            queue.append(copied)
        entry.wake()

    async def _consume(self, entry):
        stream = None
        validator = FormalAgentOutput(entry.formal) if entry.formal is not None else None
        binding = _CURRENT_EXECUTION.set((self, entry))
        try:
            stream = (entry.internal_producer(entry) if entry.internal_kind is not None else
                      entry.agent.process_formal_live_voice_stream(deepcopy(entry.formal))
                      if entry.formal is not None else
                      entry.agent.process_message_stream(deepcopy(entry.request)))
            async for chunk in stream:
                for accepted in validator.accept(chunk) if validator is not None else (chunk,):
                    await self._publish(entry, accepted)
            if validator is not None:
                entry.result_text = validator.result()
            entry.stream_outcome = "ended"
        except asyncio.CancelledError:
            entry.stream_outcome = "cancelled"
            if validator is None:
                raise
            # Formal work's journal distinguishes a confirmed cancellation from
            # failed cleanup using this actual task's settlement. A requested
            # cancel is a stream fact; finally still owns and awaits cleanup.
        except Exception as error:
            entry.stream_outcome = "failed"
            entry.failure_reason = getattr(error, "reason", "AGENT_STREAM_EXECUTION_UNAVAILABLE")
            if validator is not None or entry.internal_kind is not None:
                # The actual settlement must expose failure even when a caller
                # concurrently requested cancellation and stopped reading results.
                raise
        finally:
            try:
                if stream is not None:
                    await stream.aclose()
            except BaseException:
                entry.stream_outcome = "cleanup_failed"
                raise
            finally:
                _CURRENT_EXECUTION.reset(binding)

    async def wait_formal(self, entry) -> str:
        """Wait for the real final and cleanup; cancellation targets this work.

        Keep the caller alive until its producer settles, so the existing SDK
        settlement helper can report a delayed cancellation as UNKNOWN.
        """
        if (entry.formal is None or self._find(entry.agent,
                SessionManager.get_session_id(entry.request.session_id), entry.request.request_id) is not entry):
            raise SessionExecutionUnavailable("AGENT_STREAM_REQUEST_CONFLICT")
        try:
            await asyncio.shield(entry.task)
        except asyncio.CancelledError:
            self._cancel(entry)
            while not entry.task.done():
                try:
                    await asyncio.shield(entry.task)
                except asyncio.CancelledError:
                    continue
                except Exception:
                    break
            raise
        except Exception:
            raise SessionExecutionUnavailable(entry.failure_reason
                if entry.stream_outcome == "failed" else "AGENT_STREAM_CLEANUP_FAILED") from None
        if entry.stream_outcome != "ended" or entry.result_text is None:
            raise SessionExecutionUnavailable(entry.failure_reason or "FORMAL_AGENT_RESULT_UNAVAILABLE")
        return entry.result_text

    def cancel_formal(self, entry):
        """Request cancellation of this exact owned formal producer only.

        The returned task supplies physical settlement; requesting cancellation
        itself never means the model, tools or cleanup have finished.
        """
        self._require_loop()
        if (entry.formal is None or self._find(entry.agent,
                SessionManager.get_session_id(entry.request.session_id), entry.request.request_id) is not entry):
            raise SessionExecutionUnavailable("AGENT_STREAM_REQUEST_CONFLICT")
        self._cancel(entry)
        return entry.task

    async def wait_control_result(self, entry, *, timeout=10.0):
        """Observe a control receipt without owning or cancelling Goal execution."""
        if self._find(entry.agent, SessionManager.get_session_id(entry.request.session_id),
                      entry.request.request_id) is not entry:
            raise SessionExecutionUnavailable("AGENT_STREAM_REQUEST_CONFLICT")
        async with asyncio.timeout(timeout):
            while True:
                for _, _, event, _ in entry.events:
                    payload = event["payload"]
                    if isinstance(payload, dict) and payload.get("event_type") in {
                        "goal.snapshot", "goal.confirm_required", "chat.error", "error",
                    }:
                        return deepcopy(payload)
                if entry.stream_closed:
                    raise SessionExecutionUnavailable("AGENT_CONTROL_RESULT_UNAVAILABLE")
                await entry.changed.wait()

    async def stream(self, agent, request: AgentRequest) -> AsyncIterator[AgentResponseChunk]:
        entry = self.start(agent, request)
        if len(entry.observers) >= self.max_observers:
            raise SessionExecutionUnavailable("AGENT_STREAM_OBSERVER_CAPACITY")
        first = entry.events[0][0] if entry.events else entry.sequence + 1
        if first != 1:
            raise SessionExecutionUnavailable("AGENT_STREAM_OBSERVATION_LOST")
        token = object()
        queue = deque(chunk for _, chunk, _, _ in entry.events)
        entry.observers[token] = queue
        try:
            while True:
                while queue:
                    chunk = queue.popleft()
                    entry.wake()
                    yield deepcopy(chunk)
                if entry.stream_closed:
                    if entry.stream_outcome == "cancelled":
                        raise asyncio.CancelledError
                    if entry.stream_outcome != "ended":
                        raise SessionExecutionUnavailable("AGENT_STREAM_EXECUTION_UNAVAILABLE")
                    return
                # No await between checking the queue and subscribing.
                await entry.changed.wait()
        finally:
            entry.observers.pop(token)
            entry.wake()
            if not entry.retained and not entry.observers and not entry.stream_closed:
                self._cancel(entry)
                # A repeated observer cancellation must not cancel the producer
                # a second time while it is performing actual cleanup.
                try:
                    await asyncio.shield(entry.task)
                except asyncio.CancelledError:
                    pass

    @staticmethod
    def _cancel(entry):
        if not entry.cancellation_requested and not entry.task.done():
            entry.cancellation_requested = True
            entry.task.cancel()

    def retains_session(self, *, channel_id, session_id):
        """Whether service-owned work still needs this exact session runtime."""
        self._require_loop()
        return any(entry.retained and not entry.task.done()
                   and entry.request.channel_id == channel_id
                   and SessionManager.get_session_id(entry.request.session_id) == session_id
                   for entry in self._records.values())

    def retained_sessions(self, agent=None):
        """Exact runtime exclusions for transport cleanup, never for user Stop."""
        self._require_loop()
        retained = set()
        for entry in self._records.values():
            if entry.retained and not entry.task.done() and (agent is None or entry.agent is agent):
                retained.add(SessionManager.get_session_id(entry.request.session_id))
                if entry.formal is not None:
                    # Formal work's real Deep child is isolated from the public
                    # session. Gateway cleanup must preserve that actual owner.
                    retained.add(entry.formal.internal_session_id)
        return frozenset(retained)

    def disconnect_all(self):
        self._require_loop()
        for entry in self._records.values():
            if not entry.retained:
                self._cancel(entry)

    def disconnect(self, *, channel_id, session_id):
        """Fence text-owned producers synchronously before legacy disconnect abort.

        True means producer cleanup is owned here. A Gateway transport loss must
        not also issue a whole-Agent abort that would cancel retained work.
        Explicit user cancellation still uses the Agent capability owner.
        """
        self._require_loop()
        matched = False
        for entry in self._records.values():
            if (entry.task.done() or entry.request.channel_id != channel_id
                    or SessionManager.get_session_id(entry.request.session_id) != session_id):
                continue
            matched = True
            if not entry.retained:
                self._cancel(entry)
        return matched

    def _find(self, agent, session_id, execution_id):
        self._require_loop()
        entry = self._records.get(self._key(agent, session_id, execution_id))
        if entry is None:
            raise SessionExecutionUnavailable("AGENT_STREAM_NOT_OBSERVED")
        return entry

    @staticmethod
    def _fact(entry):
        output = entry.output_owner or entry
        return {
            "execution_id": entry.request.request_id,
            "method": getattr(entry.request.req_method, "value", entry.request.req_method) or "",
            "mode": deepcopy(entry.request.params.get("mode")),
            "requested_model": deepcopy(entry.request.params.get("model_name")),
            "stream_closed": entry.stream_closed,
            "stream_outcome": entry.stream_outcome,
            "last_sequence": entry.sequence,
            "output_execution_id": output.request.request_id,
            "output_stream_closed": output.stream_closed,
            "output_stream_outcome": output.stream_outcome,
            "output_last_sequence": output.sequence,
            "business_completion": "consult_capability_owner",
        }

    def list(self, agent, *, session_id):
        self._require_loop()
        self._key(agent, session_id, "observation")
        facts = [self._fact(entry) for (owner_id, sid, _), entry in self._records.items()
                 if owner_id == id(agent) and sid == session_id]
        result = {"executions": facts, "total_observed": len(facts), "inventory_truncated": False,
                  "source": "configured_agent_stream", "inventory_scope": "recent_observed_streams"}
        while not self._projection_fits(result):
            facts.pop(0)
            result["inventory_truncated"] = True
        return result

    @classmethod
    def _projection_fits(cls, result):
        try:
            return all(len(json.dumps(result, ensure_ascii=ascii_only, allow_nan=False,
                separators=(",", ":")).encode("utf-8")) <= maximum for ascii_only, maximum in (
                    (False, cls.PROJECTION_UTF8_BYTES), (True, cls.PROJECTION_ASCII_BYTES)))
        except (TypeError, ValueError, UnicodeError):
            raise SessionExecutionUnavailable("AGENT_STREAM_PROJECTION_UNAVAILABLE") from None

    def observe(self, agent, *, session_id, execution_id, limit=32):
        entry = self._find(agent, session_id, execution_id)
        output = entry.output_owner or entry
        if type(limit) is not int or not 1 <= limit <= 32:
            raise ValueError("invalid projection limit")
        result = {
            **self._fact(entry),
            "events": [], "events_omitted": output.sequence,
            "event_range": {"first_sequence": None, "last_sequence": None},
            "history_truncated": bool(output.sequence),
            "source": "configured_agent_stream",
        }
        if not self._projection_fits(result):
            raise SessionExecutionUnavailable("AGENT_STREAM_PROJECTION_TOO_LARGE")
        for number, _, payload, _ in reversed(list(output.events)[-limit:]):
            candidate = {**result,
                "events": [{"sequence": number, **deepcopy(payload)}, *result["events"]],
                "events_omitted": result["events_omitted"] - 1,
                "event_range": {"first_sequence": number,
                    "last_sequence": result["event_range"]["last_sequence"] or number},
                "history_truncated": number != 1}
            if not self._projection_fits(candidate):
                break  # Keep a whole contiguous suffix; never shorten a HITL event.
            result = candidate
        return result

    async def close(self, *, timeout=10.0) -> bool:
        self._require_loop()
        self._closed = True
        live = [entry for entry in self._records.values() if not entry.task.done()]
        tasks = [entry.task for entry in live]
        for entry in live:
            self._cancel(entry)
        if tasks:
            _, pending = await asyncio.wait(tasks, timeout=timeout)
            return not pending
        return True
