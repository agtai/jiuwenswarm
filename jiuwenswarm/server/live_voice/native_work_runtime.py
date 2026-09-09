# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Bounded, service-owned Native analysis; speech responses own no work lifetime.

The injected journal owns durable storage. Admission is saved before scheduling
an Agent. Recovery restores facts only: interrupted process ownership is UNKNOWN
and never replays tools. This is not the durable Task executor.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import secrets
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import TypeVar

from openjiuwen.core.common.background_tasks import wait_for_task_settlement

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    ErrorCode,
    ScopeRef,
    TurnCommit,
    canonical_json_bytes,
)
from jiuwenswarm.server.live_voice.native_foreground import NATIVE_FOREGROUND
from jiuwenswarm.server.runtime.agent_adapter.formal_live_voice import (
    FormalContextSnapshot,
    FormalAgentExecution,
)

T = TypeVar("T")


class NativeWorkViolation(ValueError):
    def __init__(
        self, reason: str, message: str, code: ErrorCode = ErrorCode.INVALID_ARGUMENT
    ):
        super().__init__(message)
        self.reason = reason
        self.code = code


class NativeWorkCancelled(NativeWorkViolation):
    def __init__(self) -> None:
        super().__init__(
            "NATIVE_WORK_CANCELLED",
            "Native work cancellation requested",
            ErrorCode.CANCELLED,
        )


class NativeWorkState(StrEnum):
    ACCEPTED = "accepted"
    RUNNING = "running"
    CANCELLING = "cancelling"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    SUPERSEDED = "superseded"
    FAILED = "failed"
    UNKNOWN = "unknown"


_TERMINAL = frozenset(
    {
        NativeWorkState.COMPLETED,
        NativeWorkState.CANCELLED,
        NativeWorkState.SUPERSEDED,
        NativeWorkState.FAILED,
        NativeWorkState.UNKNOWN,
    }
)


def context_identity(context: FormalContextSnapshot) -> str:
    return hashlib.sha256(
        canonical_json_bytes(
            {
                "scope": context.scope.to_dict(),
                "entries": [
                    {"ref": entry.ref.to_dict(), "content": entry.content}
                    for entry in context.entries
                ],
            }
        )
    ).hexdigest()


async def execute_native_work(*, service, agent, control: NativeWorkControl,
                              commit: TurnCommit, context: FormalContextSnapshot,
                              channel_id: str = "web", allow_tools: bool = True) -> str:
    """Project admitted Native work into the common configured Agent service.

    The journal owns durable admission and results; the service owns the actual
    producer. No conversation runtime, synthetic speech response or bridge is
    needed to execute work which has no speech lifetime.
    """
    from jiuwenswarm.server.runtime.session_execution import SessionExecutionUnavailable

    if (not isinstance(control, NativeWorkControl) or not isinstance(commit, TurnCommit)
            or not isinstance(context, FormalContextSnapshot)
            or control.snapshot.scope != commit.scope or context.scope != commit.scope
            or control.snapshot.input_id != commit.commit_id
            or control.snapshot.context_id != context_identity(context)):
        raise NativeWorkViolation("NATIVE_WORK_BINDING_MISMATCH",
            "work requires its exact admitted input and context", ErrorCode.PERMISSION_DENIED)
    specifications = [entry for entry in context.entries
                      if entry.ref.source == "live_voice.native_work_specification"]
    try:
        specification = json.loads(specifications[0].content) if len(specifications) == 1 else None
    except (ValueError, TypeError):
        specification = None
    if not isinstance(specification, dict) or specification.get("instruction") != control.snapshot.instruction:
        raise NativeWorkViolation("NATIVE_WORK_SPECIFICATION_MISMATCH",
            "work requires its exact selected specification", ErrorCode.PERMISSION_DENIED)
    if type(allow_tools) is not bool:
        raise NativeWorkViolation("INVALID_AGENT_TOOL_POLICY", "tool policy must be boolean")
    context.validate_for(commit)
    control.check()
    identity = control.snapshot
    request_id = f"{identity.work_id}:r{identity.revision}"
    private_id = hashlib.sha256(canonical_json_bytes({
        "scope": identity.scope.to_dict(), "request_id": request_id,
    })).hexdigest()
    execution = FormalAgentExecution(request_id=request_id, channel_id=channel_id,
        internal_session_id="lv-formal-work-" + private_id, commit=commit, context=context,
        allow_tools=allow_tools and not any(entry.ref.source == "live_voice.task_result" for entry in context.entries),
        read_only_tools=True, model_identity=identity.model_identity,
        model_config_version=identity.model_config_version)
    binding = NATIVE_FOREGROUND.set(None)
    try:
        entry = service.start_formal(agent, execution)
        control.settlement = entry.task
        return await control.read_only(service.wait_formal(entry))
    except SessionExecutionUnavailable as error:
        raise NativeWorkViolation(error.reason, "configured Agent result is unavailable",
                                  ErrorCode.RESULT_UNKNOWN) from error
    finally:
        NATIVE_FOREGROUND.reset(binding)


def _text(value: str, name: str, maximum: int = 256) -> str:
    if not isinstance(value, str) or not value.strip():
        raise NativeWorkViolation(
            "INVALID_NATIVE_WORK_INPUT", f"{name} must be nonempty"
        )
    try:
        if len(value.encode("utf-8")) > maximum:
            raise NativeWorkViolation(
                "INVALID_NATIVE_WORK_INPUT", f"{name} exceeds its bound"
            )
    except UnicodeEncodeError as error:
        raise NativeWorkViolation(
            "INVALID_NATIVE_WORK_INPUT", f"{name} must be valid UTF-8"
        ) from error
    return value


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class NativeWorkSnapshot:
    scope: ScopeRef
    work_id: str
    revision: int
    sequence: int
    request_id: str
    input_id: str
    instruction: str
    model_identity: str
    model_config_version: str
    context_id: str
    foreground: bool
    state: NativeWorkState
    accepted_at: str
    updated_at: str
    result_text: str | None = None
    reason: str | None = None
    supersedes_revision: int | None = None
    execution_settled: bool = False

    def __post_init__(self) -> None:
        if (
            not isinstance(self.scope, ScopeRef)
            or not isinstance(self.state, NativeWorkState)
            or type(self.revision) is not int
            or self.revision < 1
            or type(self.sequence) is not int
            or self.sequence < 1
            or type(self.foreground) is not bool
            or type(self.execution_settled) is not bool
            or self.supersedes_revision
            != (None if self.revision == 1 else self.revision - 1)
        ):
            raise NativeWorkViolation(
                "INVALID_NATIVE_WORK_SNAPSHOT",
                "invalid retained work identity or state",
            )
        for name in (
            "work_id",
            "request_id",
            "input_id",
            "model_identity",
            "model_config_version",
        ):
            _text(getattr(self, name), name)
        _text(self.instruction, "instruction", 4096)
        if (
            not isinstance(self.context_id, str)
            or len(self.context_id) != 64
            or any(c not in "0123456789abcdef" for c in self.context_id)
        ):
            raise NativeWorkViolation(
                "INVALID_NATIVE_WORK_SNAPSHOT", "invalid context identity"
            )
        for timestamp in (self.accepted_at, self.updated_at):
            try:
                if (
                    datetime.fromisoformat(timestamp.replace("Z", "+00:00")).tzinfo
                    is None
                ):
                    raise ValueError("timezone required")
            except (AttributeError, ValueError) as error:
                raise NativeWorkViolation(
                    "INVALID_NATIVE_WORK_SNAPSHOT", "invalid work timestamp"
                ) from error
        if self.result_text is not None:
            _text(self.result_text, "result_text", 131072)
            if self.state not in {
                NativeWorkState.COMPLETED,
                NativeWorkState.SUPERSEDED,
            }:
                raise NativeWorkViolation(
                    "INVALID_NATIVE_WORK_SNAPSHOT",
                    "uncompleted work cannot claim a result",
                )
        if self.state is NativeWorkState.COMPLETED and (
            not self.execution_settled or self.result_text is None
        ):
            raise NativeWorkViolation(
                "INVALID_NATIVE_WORK_SNAPSHOT",
                "completed work requires a settled result",
            )
        if self.reason is not None:
            _text(self.reason, "reason")

    def to_dict(self) -> dict[str, object]:
        from dataclasses import fields

        result = {item.name: getattr(self, item.name) for item in fields(self)}
        result["scope"] = self.scope.to_dict()
        result["state"] = self.state.value
        return result

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> NativeWorkSnapshot:
        copied = dict(value)
        copied["scope"] = ScopeRef.from_dict(copied["scope"])
        copied["state"] = NativeWorkState(copied["state"])
        return cls(**copied)


@dataclass(slots=True)
class NativeWorkControl:
    """Exact admitted work capability handed only to its owned runner."""

    snapshot: NativeWorkSnapshot
    cancelled: asyncio.Event
    settlement: asyncio.Future | None = None

    def check(self) -> None:
        if self.cancelled.is_set():
            raise NativeWorkCancelled()

    async def read_only(
        self, operation: Awaitable[T], *, timeout: float | None = None
    ) -> T:
        work = asyncio.ensure_future(operation)
        stop = asyncio.create_task(self.cancelled.wait())
        try:
            done, _ = await asyncio.wait(
                {work, stop}, timeout=timeout, return_when=asyncio.FIRST_COMPLETED
            )
            self.check()
            if work not in done:
                raise TimeoutError
            return await work
        finally:
            for task in (work, stop):
                if not task.done():
                    task.cancel()
            await asyncio.gather(work, stop, return_exceptions=True)


NativeWorkRunner = Callable[[NativeWorkControl], Awaitable[str]]


@dataclass(slots=True)
class _Record:
    snapshot: NativeWorkSnapshot
    control: NativeWorkControl
    operation: asyncio.Task[None] | None = None
    runner: asyncio.Task[str] | None = None


class NativeWorkRuntime:
    def __init__(
        self,
        *,
        save: Callable[[NativeWorkSnapshot], None] | None = None,
        restored: tuple[NativeWorkSnapshot, ...] = (),
        max_active: int = 4,
        reserved_foreground: int = 1,
        max_records: int = 128,
        timeout_seconds: float = 120.0,
        cancel_settlement_seconds: float = 1.0,
    ) -> None:
        if (
            type(max_active) is not int
            or type(reserved_foreground) is not int
            or not 0 < reserved_foreground < max_active
            or type(max_records) is not int
            or max_records < max_active
        ):
            raise NativeWorkViolation(
                "INVALID_NATIVE_WORK_BOUNDS", "invalid Native work capacity"
            )
        for bound in (timeout_seconds, cancel_settlement_seconds):
            if (
                isinstance(bound, bool)
                or not isinstance(bound, (int, float))
                or not math.isfinite(bound)
                or bound <= 0
            ):
                raise NativeWorkViolation(
                    "INVALID_NATIVE_WORK_BOUNDS",
                    "deadlines must be positive and finite",
                )
        self._save = save
        self._max_active = max_active
        self._background_limit = max_active - reserved_foreground
        self._max_records = max_records
        self._timeout = timeout_seconds
        self._cancel_timeout = cancel_settlement_seconds
        self._records: dict[tuple[ScopeRef, str, int], _Record] = {}
        self._requests: dict[tuple[ScopeRef, str], _Record] = {}
        self._latest: dict[tuple[ScopeRef, str], int] = {}
        self._closed = False
        self._owner_loop: asyncio.AbstractEventLoop | None = None
        self._observation_epoch = secrets.token_hex(16)
        self._observation_sequence: dict[ScopeRef, int] = {}
        self._observation_events: dict[ScopeRef, asyncio.Event] = {}
        self._observation_waiters = 0
        self._observation_event_waiters: dict[asyncio.Event, int] = {}
        if len(restored) > max_records:
            raise NativeWorkViolation(
                "NATIVE_WORK_LEDGER_FULL", "restored work exceeds configured capacity"
            )
        for original in restored:
            if not isinstance(original, NativeWorkSnapshot):
                raise NativeWorkViolation(
                    "INVALID_NATIVE_WORK_RESTORE",
                    "restore requires canonical snapshots",
                )
            self._validate_identity(
                original.scope,
                original.request_id,
                original.input_id,
                original.instruction,
                original.model_identity,
                original.model_config_version,
                original.context_id,
                original.foreground,
            )
            if original.revision < 1 or original.sequence < 1:
                raise NativeWorkViolation(
                    "INVALID_NATIVE_WORK_RESTORE", "invalid restored version"
                )
            snapshot = original
            if original.state not in _TERMINAL or not original.execution_settled:
                snapshot = replace(
                    original,
                    state=NativeWorkState.UNKNOWN,
                    sequence=original.sequence + 1,
                    reason="PROCESS_OWNERSHIP_LOST",
                    execution_settled=True,
                    updated_at=_now(),
                )
                self._persist(snapshot)
            self._insert(
                _Record(snapshot, NativeWorkControl(snapshot, asyncio.Event()))
            )

    def _require_owner(self) -> None:
        running = asyncio.get_running_loop()
        if self._owner_loop is None:
            self._owner_loop = running
        if self._owner_loop is not running:
            raise NativeWorkViolation(
                "NATIVE_WORK_OWNER_MISMATCH", "work owner cannot cross event loops"
            )

    @staticmethod
    def _validate_identity(
        scope,
        request_id,
        input_id,
        instruction,
        model_identity,
        model_config_version,
        context_id,
        foreground,
    ):
        if not isinstance(scope, ScopeRef) or type(foreground) is not bool:
            raise NativeWorkViolation(
                "INVALID_NATIVE_WORK_INPUT", "canonical scope and priority are required"
            )
        for name, value in (
            ("request_id", request_id),
            ("input_id", input_id),
            ("model_identity", model_identity),
            ("model_config_version", model_config_version),
        ):
            _text(value, name)
        _text(instruction, "instruction", 4096)
        if (
            not isinstance(context_id, str)
            or len(context_id) != 64
            or any(c not in "0123456789abcdef" for c in context_id)
        ):
            raise NativeWorkViolation(
                "INVALID_NATIVE_WORK_INPUT", "context_id must be a SHA256 identity"
            )

    def _persist(self, snapshot: NativeWorkSnapshot) -> None:
        if self._save is not None:
            try:
                self._save(snapshot)
            except Exception as error:
                raise NativeWorkViolation(
                    "NATIVE_WORK_PERSISTENCE_FAILED",
                    "work checkpoint could not be saved",
                    ErrorCode.UNAVAILABLE,
                ) from error

    def _insert(self, record: _Record) -> None:
        s = record.snapshot
        key = (s.scope, s.work_id, s.revision)
        request_key = (s.scope, s.request_id)
        if key in self._records or request_key in self._requests:
            raise NativeWorkViolation(
                "NATIVE_WORK_ID_CONFLICT",
                "retained work identity conflicts",
                ErrorCode.CONFLICT,
            )
        self._records[key] = record
        self._requests[request_key] = record
        self._latest[(s.scope, s.work_id)] = max(
            s.revision, self._latest.get((s.scope, s.work_id), 0)
        )
        self._signal_observation(s.scope)

    def observation_cursor(self, scope: ScopeRef) -> dict[str, object]:
        return {"epoch": self._observation_epoch,
                "sequence": self._observation_sequence.get(scope, 0), "read_sequence": 0}

    def _signal_observation(self, scope: ScopeRef) -> None:
        if (scope not in self._observation_sequence
                and len(self._observation_sequence) >= self._max_records):
            # Retired activations can introduce scopes without any Work record.
            # A bounded observation cache must not retain those scopes forever.
            # Epoch replacement makes every older cursor request full facts;
            # waking the exact old events preserves installed waiter ownership.
            self._observation_epoch = secrets.token_hex(16)
            self._observation_sequence.clear()
            for event in self._observation_events.values():
                event.set()
            self._observation_events.clear()
        self._observation_sequence[scope] = self._observation_sequence.get(scope, 0) + 1
        event = self._observation_events.pop(scope, None)
        if event is not None:
            event.set()

    def wake_observers(self, scope: ScopeRef) -> None:
        self._signal_observation(scope)

    async def wait_for_observation(self, *, scope: ScopeRef, after, wait_ms: int) -> None:
        from .native_business_observation import observation_cursor, MAX_OBSERVATION_WAIT_MS
        self._require_owner()
        after = observation_cursor(after)
        if type(wait_ms) is not int or not 0 <= wait_ms <= MAX_OBSERVATION_WAIT_MS:
            raise ValueError("invalid Native observation wait")
        current = self.observation_cursor(scope)
        if (self._closed or after is None or not wait_ms
                or (after["epoch"], after["sequence"]) != (current["epoch"], current["sequence"])):
            return
        if self._observation_waiters >= 128:
            raise NativeWorkViolation("NATIVE_OBSERVATION_CAPACITY", "bounded observation capacity is full", ErrorCode.UNAVAILABLE)
        # No await separates the cursor check and event installation. Work
        # transitions use this same event-loop owner and set this exact event.
        event = self._observation_events.setdefault(scope, asyncio.Event())
        self._observation_waiters += 1
        self._observation_event_waiters[event] = self._observation_event_waiters.get(event, 0) + 1
        try:
            try:
                await asyncio.wait_for(event.wait(), wait_ms / 1000)
            except TimeoutError:
                pass
        finally:
            self._observation_waiters -= 1
            remaining = self._observation_event_waiters[event] - 1
            if remaining:
                self._observation_event_waiters[event] = remaining
            else:
                self._observation_event_waiters.pop(event, None)
                if self._observation_events.get(scope) is event:
                    self._observation_events.pop(scope, None)

    def _transition(self, record: _Record, state: NativeWorkState, **fields) -> bool:
        if state not in {NativeWorkState.COMPLETED, NativeWorkState.SUPERSEDED}:
            fields.setdefault("result_text", None)
        updated = replace(
            record.snapshot,
            sequence=record.snapshot.sequence + 1,
            state=state,
            updated_at=_now(),
            **fields,
        )
        try:
            self._persist(updated)
        except NativeWorkViolation:
            # Never publish success when its checkpoint failed. The previous
            # durable nonterminal record restores as UNKNOWN, without replay.
            record.snapshot = replace(
                updated,
                state=NativeWorkState.UNKNOWN,
                reason="NATIVE_WORK_PERSISTENCE_FAILED",
                result_text=None,
            )
            record.control.cancelled.set()
            self._signal_observation(record.snapshot.scope)
            return False
        record.snapshot = updated
        self._signal_observation(updated.scope)
        return True

    def _record(
        self,
        scope: ScopeRef,
        work_id: str,
        revision: int | None = None,
        *,
        current: bool = False,
    ) -> _Record:
        latest = self._latest.get((scope, work_id))
        if latest is None:
            raise NativeWorkViolation(
                "NATIVE_WORK_NOT_FOUND",
                "no work in the exact scope",
                ErrorCode.PERMISSION_DENIED,
            )
        if revision is not None and (type(revision) is not int or revision < 1):
            raise NativeWorkViolation(
                "INVALID_NATIVE_WORK_REVISION", "revision must be a positive integer"
            )
        if current and revision != latest:
            raise NativeWorkViolation(
                "NATIVE_WORK_REVISION_STALE",
                "work revision has been superseded",
                ErrorCode.STALE,
            )
        record = self._records.get(
            (scope, work_id, latest if revision is None else revision)
        )
        if record is None:
            raise NativeWorkViolation(
                "NATIVE_WORK_NOT_FOUND", "work revision is unavailable", ErrorCode.STALE
            )
        return record

    def query(
        self, *, scope: ScopeRef, work_id: str, revision: int | None = None
    ) -> NativeWorkSnapshot:
        return self._record(scope, work_id, revision).snapshot

    def list(self, *, scope: ScopeRef) -> tuple[NativeWorkSnapshot, ...]:
        return tuple(
            self._records[(item_scope, work_id, revision)].snapshot
            for (item_scope, work_id), revision in self._latest.items()
            if item_scope == scope
        )

    def _admit(
        self,
        *,
        scope,
        request_id,
        input_id,
        instruction,
        model_identity,
        model_config_version,
        context_id,
        runner,
        foreground,
        predecessor: _Record | None = None,
    ) -> tuple[_Record, bool]:
        self._require_owner()
        self._validate_identity(
            scope,
            request_id,
            input_id,
            instruction,
            model_identity,
            model_config_version,
            context_id,
            foreground,
        )
        if not callable(runner):
            raise NativeWorkViolation(
                "INVALID_NATIVE_WORK_RUNNER", "an owned async runner is required"
            )
        existing = self._requests.get((scope, request_id))
        if existing is not None:
            s = existing.snapshot
            if (
                s.input_id,
                s.instruction,
                s.model_identity,
                s.model_config_version,
                s.context_id,
                s.foreground,
                s.supersedes_revision,
                s.work_id if predecessor else None,
            ) != (
                input_id,
                instruction,
                model_identity,
                model_config_version,
                context_id,
                foreground,
                predecessor.snapshot.revision if predecessor else None,
                predecessor.snapshot.work_id if predecessor else None,
            ):
                raise NativeWorkViolation(
                    "NATIVE_WORK_REQUEST_CONFLICT",
                    "request cannot change its admitted binding",
                    ErrorCode.CONFLICT,
                )
            return existing, False
        if self._closed:
            raise NativeWorkViolation(
                "NATIVE_WORK_CLOSED",
                "service work owner is closed",
                ErrorCode.UNAVAILABLE,
            )
        if len(self._records) >= self._max_records:
            raise NativeWorkViolation(
                "NATIVE_WORK_LEDGER_FULL",
                "bounded work ledger is full",
                ErrorCode.UNAVAILABLE,
            )
        occupied_by_work = {
            (r.snapshot.scope, r.snapshot.work_id): r
            for r in self._records.values()
            if r.operation is not None
            and not r.operation.done()
            and not r.snapshot.execution_settled
        }
        occupied = list(occupied_by_work.values())
        # A replacement shares its predecessor's reservation until settlement.
        occupied = [
            r
            for r in occupied
            if predecessor is None
            or r.snapshot.work_id != predecessor.snapshot.work_id
            or r.snapshot.scope != scope
        ]
        if len(occupied) >= self._max_active or (
            not foreground
            and sum(not r.snapshot.foreground for r in occupied)
            >= self._background_limit
        ):
            raise NativeWorkViolation(
                "NATIVE_WORK_CAPACITY_FULL",
                "bounded work capacity is full; foreground capacity is reserved",
                ErrorCode.UNAVAILABLE,
            )
        now = _now()
        snapshot = NativeWorkSnapshot(
            scope=scope,
            work_id=predecessor.snapshot.work_id
            if predecessor
            else "native-work-" + secrets.token_hex(16),
            revision=predecessor.snapshot.revision + 1 if predecessor else 1,
            sequence=1,
            request_id=request_id,
            input_id=input_id,
            instruction=instruction,
            model_identity=model_identity,
            model_config_version=model_config_version,
            context_id=context_id,
            foreground=foreground,
            state=NativeWorkState.ACCEPTED,
            accepted_at=now,
            updated_at=now,
            supersedes_revision=predecessor.snapshot.revision if predecessor else None,
        )
        self._persist(snapshot)
        record = _Record(snapshot, NativeWorkControl(snapshot, asyncio.Event()))
        self._insert(record)
        if predecessor is not None:
            self._transition(
                predecessor,
                NativeWorkState.SUPERSEDED,
                reason="SUPERSEDED_BY_NEW_REVISION",
            )
            predecessor.control.cancelled.set()
        record.operation = asyncio.create_task(
            self._run(record, runner, predecessor),
            name=f"native-work:{snapshot.work_id}:{snapshot.revision}",
        )
        return record, True

    async def start(
        self,
        *,
        scope: ScopeRef,
        request_id: str,
        input_id: str,
        instruction: str,
        model_identity: str,
        model_config_version: str,
        context_id: str,
        runner: NativeWorkRunner,
        foreground: bool = False,
    ) -> NativeWorkSnapshot:
        record, _ = self._admit(
            scope=scope,
            request_id=request_id,
            input_id=input_id,
            instruction=instruction,
            model_identity=model_identity,
            model_config_version=model_config_version,
            context_id=context_id,
            runner=runner,
            foreground=foreground,
        )
        return record.snapshot

    async def update(
        self,
        *,
        scope: ScopeRef,
        work_id: str,
        revision: int,
        request_id: str,
        input_id: str,
        instruction: str,
        model_identity: str,
        model_config_version: str,
        context_id: str,
        runner: NativeWorkRunner,
    ) -> NativeWorkSnapshot:
        predecessor = self._record(scope, work_id, revision)
        replay = self._requests.get((scope, request_id))
        if replay is None:
            self._record(scope, work_id, revision, current=True)
            if predecessor.snapshot.state in {
                NativeWorkState.UNKNOWN,
                NativeWorkState.CANCELLING,
                NativeWorkState.CANCELLED,
                NativeWorkState.SUPERSEDED,
            }:
                raise NativeWorkViolation(
                    "NATIVE_WORK_NOT_UPDATABLE",
                    "work outcome does not permit an update",
                    ErrorCode.CONFLICT,
                )
        record, _ = self._admit(
            scope=scope,
            request_id=request_id,
            input_id=input_id,
            instruction=instruction,
            model_identity=model_identity,
            model_config_version=model_config_version,
            context_id=context_id,
            runner=runner,
            foreground=predecessor.snapshot.foreground,
            predecessor=predecessor,
        )
        return record.snapshot

    async def cancel(
        self, *, scope: ScopeRef, work_id: str, revision: int
    ) -> NativeWorkSnapshot:
        self._require_owner()
        record = self._record(scope, work_id, revision, current=True)
        if (
            record.snapshot.state not in _TERMINAL
            and record.snapshot.state is not NativeWorkState.CANCELLING
        ):
            self._transition(
                record, NativeWorkState.CANCELLING, reason="EXPLICIT_CANCELLATION"
            )
            record.control.cancelled.set()
        return record.snapshot

    async def _run(
        self, record: _Record, runner: NativeWorkRunner, predecessor: _Record | None
    ) -> None:
        token = NATIVE_FOREGROUND.set(None)
        try:
            if predecessor is not None and predecessor.operation is not None:
                try:
                    await asyncio.wait_for(
                        asyncio.shield(predecessor.operation), timeout=self._timeout
                    )
                except TimeoutError:
                    self._transition(
                        record,
                        NativeWorkState.UNKNOWN,
                        reason="PREDECESSOR_OUTCOME_UNKNOWN",
                        execution_settled=True,
                    )
                    return
                if (
                    not predecessor.snapshot.execution_settled
                    or predecessor.snapshot.state is NativeWorkState.UNKNOWN
                ):
                    self._transition(
                        record,
                        NativeWorkState.UNKNOWN,
                        reason="PREDECESSOR_OUTCOME_UNKNOWN",
                        execution_settled=True,
                    )
                    return
            if record.control.cancelled.is_set():
                if record.snapshot.state is not NativeWorkState.UNKNOWN:
                    state = (
                        NativeWorkState.SUPERSEDED
                        if record.snapshot.state is NativeWorkState.SUPERSEDED
                        else NativeWorkState.CANCELLED
                    )
                    self._transition(record, state, execution_settled=True)
                else:
                    self._transition(
                        record, NativeWorkState.UNKNOWN, execution_settled=True
                    )
                return
            if not self._transition(record, NativeWorkState.RUNNING):
                self._transition(
                    record, NativeWorkState.UNKNOWN, execution_settled=True
                )
                return
            record.runner = asyncio.create_task(runner(record.control))
            settlement = await wait_for_task_settlement(
                record.runner, cancelled=record.control.cancelled,
                timeout=self._timeout, settlement_timeout=self._cancel_timeout,
            )
            timed_out = settlement.timed_out
            if not settlement.settled:
                self._transition(
                    record, NativeWorkState.UNKNOWN,
                    reason="CANCELLATION_OUTCOME_UNKNOWN", execution_settled=False,
                )
                # The SDK wait leaves ownership here until the actual runner exits.
                await asyncio.gather(record.runner, return_exceptions=True)
                self._transition(record, NativeWorkState.UNKNOWN, execution_settled=True)
                return
            if record.snapshot.state is NativeWorkState.UNKNOWN:
                await asyncio.gather(record.runner, return_exceptions=True)
                self._transition(
                    record,
                    NativeWorkState.UNKNOWN,
                    execution_settled=record.control.settlement is None
                    or record.control.settlement.done(),
                )
                return
            if record.control.cancelled.is_set():
                error = (
                    record.runner.exception()
                    if not record.runner.cancelled()
                    else None
                )
                unknown = getattr(error, "code", None) is ErrorCode.RESULT_UNKNOWN
                physical = record.control.settlement
                if physical is not None and physical.done():
                    unknown = unknown or physical.cancelled() or physical.exception() is not None
                state = (
                    NativeWorkState.UNKNOWN
                    if unknown
                    else (
                        NativeWorkState.SUPERSEDED
                        if record.snapshot.state is NativeWorkState.SUPERSEDED
                        else NativeWorkState.CANCELLED
                    )
                )
                self._transition(
                    record,
                    state,
                    reason="WORK_DEADLINE_EXCEEDED"
                    if timed_out
                    else (getattr(error, "reason", None) or record.snapshot.reason),
                    execution_settled=not unknown,
                )
                return
            result = record.runner.result()
            _text(result, "result_text", 131072)
            self._transition(
                record,
                NativeWorkState.COMPLETED,
                result_text=result,
                execution_settled=True,
            )
        except asyncio.CancelledError:
            record.control.cancelled.set()
            self._transition(
                record,
                NativeWorkState.UNKNOWN,
                reason="SERVICE_OWNERSHIP_LOST",
                execution_settled=False,
            )
            raise
        except Exception as error:
            unknown = getattr(error, "code", None) in {
                ErrorCode.RESULT_UNKNOWN,
                ErrorCode.TIMEOUT,
            }
            self._transition(
                record,
                NativeWorkState.UNKNOWN if unknown else NativeWorkState.FAILED,
                reason=getattr(error, "reason", "NATIVE_WORK_EXECUTION_FAILED"),
                execution_settled=not unknown,
            )
        finally:
            if record.control.settlement is not None:
                # A common producer can outlive the request cancellation budget.
                # Keep this reservation until its actual cleanup settles.
                settled = await asyncio.gather(
                    asyncio.shield(record.control.settlement), return_exceptions=True
                )
                if (
                    isinstance(settled[0], BaseException)
                    and record.snapshot.state is not NativeWorkState.UNKNOWN
                ):
                    self._transition(
                        record,
                        NativeWorkState.UNKNOWN,
                        reason="EXECUTION_SETTLEMENT_UNCONFIRMED",
                        execution_settled=True,
                    )
                if record.snapshot.state is NativeWorkState.UNKNOWN:
                    self._transition(
                        record, NativeWorkState.UNKNOWN, execution_settled=True
                    )
            NATIVE_FOREGROUND.reset(token)

    async def close(self) -> tuple[NativeWorkSnapshot, ...]:
        self._require_owner()
        self._closed = True
        for scope in tuple(self._observation_events):
            self._signal_observation(scope)
        pending = []
        for record in self._records.values():
            if record.operation is not None and not record.operation.done():
                if record.snapshot.state not in _TERMINAL:
                    self._transition(
                        record, NativeWorkState.CANCELLING, reason="SERVICE_SHUTDOWN"
                    )
                record.control.cancelled.set()
                pending.append(record.operation)
        if pending:
            _, unsettled = await asyncio.wait(
                pending, timeout=self._cancel_timeout + 0.1
            )
            for record in self._records.values():
                if (
                    record.operation in unsettled
                    and record.snapshot.state is not NativeWorkState.UNKNOWN
                ):
                    self._transition(
                        record,
                        NativeWorkState.UNKNOWN,
                        reason="SERVICE_SHUTDOWN_UNSETTLED",
                        execution_settled=False,
                    )
        return tuple(record.snapshot for record in self._records.values())
