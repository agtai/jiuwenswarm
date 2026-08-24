# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Isolated Live Voice facade over the public AgentCore Task authority.

The module deliberately uses structural protocols.  Importing Live Voice does
not require the local AgentCore candidate, and this boundary never imports an
AgentCore DAO, Manager, dynamic model, or legacy Live Voice Task store.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from jiuwenswarm.common.schema.live_voice_contract_v2 import Assurance, ScopeRef

from .product_authority import ResolvedProductAuthority

_MAX_PRODUCT_ID_LENGTH = 256
_MAX_ID_LENGTH = 255
_MAX_TEXT_LENGTH = 65_535
_MAX_EVENT_PAYLOAD_BYTES = 16_384
_MAX_LOCATOR_LENGTH = 2048
_MAX_SIGNED_BIGINT = (1 << 63) - 1
_MAX_LIST_LIMIT = 100
_MAX_EVENT_LIMIT = 500
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_CHANNELS = frozenset({"text", "voice"})
_TASK_STATUSES = frozenset(
    {
        "pending",
        "blocked",
        "planning",
        "in_progress",
        "in_review",
        "completed",
        "failed",
        "cancelled",
        "interrupted",
        "unknown",
    }
)
_ACTIVE_TASK_STATUSES = frozenset({"planning", "in_progress", "in_review"})
_TERMINAL_TASK_STATUSES = frozenset(
    {"completed", "failed", "cancelled", "interrupted", "unknown"}
)
_EXECUTION_DISPOSITIONS = frozenset(
    {
        "prepared",
        "owned",
        "recoverable",
        "orphaned",
        "completed",
        "failed",
        "cancelled",
        "interrupted",
        "unknown",
    }
)
_EXECUTION_OUTCOMES = frozenset(
    {"completed", "failed", "cancelled", "interrupted", "unknown"}
)
_TASK_EVENT_TYPES = frozenset(
    {
        "task.created",
        "task.updated",
        "task.status_changed",
        "task.deleted",
        "task.dependencies_changed",
        "task.review_changed",
        "task.execution_prepared",
        "task.execution_admitted",
        "task.execution_reconciled",
        "task.execution_settled",
        "task.execution_checkpoint_published",
    }
)
_SUPPORTED_OPERATIONS = frozenset(
    {
        "task.get",
        "task.list",
        "task.status",
        "task.events",
        "task.result",
        "task.unread_events",
        "task.ack_events",
    }
)
_UNSUPPORTED_OPERATIONS = frozenset(
    {
        "task.create",
        "task.update",
        "task.cancel",
        "task.retry",
        "task.adjust",
        "task.reprioritize",
        "task.create_successor",
    }
)


class OpenJiuwenTaskFacadeError(RuntimeError):
    """Stable fail-closed facade error without downstream exception text."""

    def __init__(self, reason: str) -> None:
        super().__init__("OpenJiuwen Task facade is unavailable")
        self.reason = reason


class AgentCoreTaskAuthorityBindingPort(Protocol):
    session_id: str
    team_name: str
    member_name: str


class AgentCoreTaskAuthorityPort(Protocol):
    """Only the public authority surface consumed by this adapter."""

    binding: AgentCoreTaskAuthorityBindingPort
    executor_authority: bool

    async def get(self, task_id: str) -> object | None: ...

    async def list(self, *, limit: int = 100) -> tuple[object, ...]: ...

    async def read_events(
        self,
        task_id: str,
        *,
        after_sequence: int = 0,
        limit: int = 100,
    ) -> object: ...

    async def read_unread(
        self,
        task_id: str,
        consumer_id: str,
        channel: str,
        *,
        limit: int = 100,
    ) -> object | None: ...

    async def advance_cursor(
        self,
        task_id: str,
        consumer_id: str,
        channel: str,
        advance_id: str,
        *,
        expected_cursor_sequence: int,
        expected_cursor_version: int,
        expected_head_sequence: int,
        acknowledged_sequence: int,
        acknowledged_event_id: str,
        acknowledged_event_payload_digest: str,
    ) -> object: ...


@dataclass(frozen=True, slots=True)
class OpenJiuwenScopeBinding:
    product_scope_digest: str
    session_id: str
    team_name: str
    member_name: str
    consumer_id: str


@dataclass(frozen=True, slots=True)
class OpenJiuwenTaskResultRef:
    result_id: str
    digest: str
    locator: str | None


@dataclass(frozen=True, slots=True)
class OpenJiuwenTaskExecution:
    task_id: str
    execution_id: str
    profile_digest: str
    generation: int
    owner_id: str | None
    owner_epoch: int | None
    disposition: str
    execution_version: int
    checkpoint_head: int
    outcome: str | None
    result_ref: OpenJiuwenTaskResultRef | None

    @property
    def executor_authority(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class OpenJiuwenTask:
    task_id: str
    title: str
    content: str
    status: str
    assignee: str | None
    current_execution_id: str | None
    execution_version: int
    event_head: int
    updated_at: int | None


@dataclass(frozen=True, slots=True)
class OpenJiuwenTaskSnapshot:
    task: OpenJiuwenTask
    execution: OpenJiuwenTaskExecution | None

    @property
    def executor_authority(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class OpenJiuwenTaskEvent:
    task_id: str
    sequence: int
    event_id: str
    event_type: str
    schema_version: int
    producer: str
    causation_id: str
    correlation_id: str
    payload_json: str
    payload_digest: str
    occurred_at: int
    execution_id: str | None
    execution_version: int | None


@dataclass(frozen=True, slots=True)
class OpenJiuwenTaskEventPage:
    head_sequence: int
    events: tuple[OpenJiuwenTaskEvent, ...]


@dataclass(frozen=True, slots=True)
class OpenJiuwenTaskCursor:
    task_id: str
    consumer_id: str
    channel: str
    sequence: int
    version: int
    event_id: str | None
    event_payload_digest: str | None
    updated_at: int | None


@dataclass(frozen=True, slots=True)
class OpenJiuwenTaskUnreadPage:
    cursor: OpenJiuwenTaskCursor
    head_sequence: int
    events: tuple[OpenJiuwenTaskEvent, ...]
    next_after_sequence: int | None
    has_more: bool


@dataclass(frozen=True, slots=True)
class OpenJiuwenCursorAdvanceDecision:
    ok: bool
    reason: str
    advance_id: str | None
    replayed: bool
    advanced: bool
    cursor: OpenJiuwenTaskCursor | None


@dataclass(frozen=True, slots=True)
class OpenJiuwenTaskResultView:
    task_id: str
    task_status: str
    execution_id: str | None
    outcome: str | None
    result_ref: OpenJiuwenTaskResultRef | None


def _error(reason: str) -> OpenJiuwenTaskFacadeError:
    return OpenJiuwenTaskFacadeError(reason)


def _text(
    value: object,
    field_name: str,
    *,
    maximum: int = _MAX_ID_LENGTH,
    allow_empty: bool = False,
) -> str:
    if type(value) is not str or "\x00" in value:
        raise _error(f"INVALID_{field_name.upper()}")
    if not allow_empty and not value.strip():
        raise _error(f"INVALID_{field_name.upper()}")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise _error(f"INVALID_{field_name.upper()}") from None
    if len(value) > maximum:
        raise _error(f"INVALID_{field_name.upper()}")
    return value


def _utf8_text(
    value: object,
    field_name: str,
    *,
    maximum_bytes: int,
    allow_empty: bool = False,
) -> str:
    text = _text(
        value,
        field_name,
        maximum=maximum_bytes,
        allow_empty=allow_empty,
    )
    if len(text.encode("utf-8")) > maximum_bytes:
        raise _error(f"INVALID_{field_name.upper()}")
    return text


def _optional_text(
    value: object,
    field_name: str,
    *,
    maximum: int = _MAX_ID_LENGTH,
) -> str | None:
    if value is None:
        return None
    return _text(value, field_name, maximum=maximum)


def _integer(value: object, field_name: str, *, positive: bool = False) -> int:
    lower = 1 if positive else 0
    if type(value) is not int or not lower <= value <= _MAX_SIGNED_BIGINT:
        raise _error(f"INVALID_{field_name.upper()}")
    return value


def _boolean(value: object, field_name: str) -> bool:
    if type(value) is not bool:
        raise _error(f"INVALID_{field_name.upper()}")
    return value


def _sha256(value: object, field_name: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise _error(f"INVALID_{field_name.upper()}")
    return value


def _enum_text(value: object, field_name: str) -> str:
    return _text(getattr(value, "value", value), field_name)


def _canonical_digest(domain: str, payload: dict[str, object]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(domain.encode("ascii") + b"\x00" + encoded).hexdigest()


def derive_openjiuwen_scope_binding(scope: ScopeRef) -> OpenJiuwenScopeBinding:
    """Derive stable, non-secret AgentCore identities from one exact scope."""

    if (
        not isinstance(scope, ScopeRef)
        or scope.assurance is not Assurance.AUTHENTICATED
    ):
        raise _error("INVALID_PRODUCT_SCOPE")
    subject_id = _text(
        scope.subject_id,
        "scope_subject_id",
        maximum=_MAX_PRODUCT_ID_LENGTH,
    )
    session_id = _text(
        scope.session_id,
        "scope_session_id",
        maximum=_MAX_PRODUCT_ID_LENGTH,
    )
    project_id = _optional_text(
        scope.project_id,
        "scope_project_id",
        maximum=_MAX_PRODUCT_ID_LENGTH,
    )
    facts = {
        "project_id": project_id,
        "session_id": session_id,
        "subject_id": subject_id,
    }
    scope_digest = _canonical_digest("livevoice.openjiuwen.scope.v1", facts)
    consumer_digest = _canonical_digest(
        "livevoice.openjiuwen.consumer.v1",
        {"project_id": project_id, "subject_id": subject_id},
    )
    return OpenJiuwenScopeBinding(
        product_scope_digest=scope_digest,
        session_id=f"lv-oj-session-{scope_digest[:48]}",
        team_name=f"lv-oj-team-{scope_digest[:48]}",
        member_name=f"lv-oj-member-{scope_digest[:48]}",
        consumer_id=f"lv-oj-consumer-{consumer_digest[:48]}",
    )


def _project_result_ref(value: object) -> OpenJiuwenTaskResultRef:
    return OpenJiuwenTaskResultRef(
        result_id=_text(getattr(value, "result_id", None), "result_id"),
        digest=_sha256(getattr(value, "digest", None), "result_digest"),
        locator=_optional_text(
            getattr(value, "locator", None),
            "result_locator",
            maximum=_MAX_LOCATOR_LENGTH,
        ),
    )


def _project_task(value: object, binding: OpenJiuwenScopeBinding) -> OpenJiuwenTask:
    if _text(getattr(value, "team_name", None), "task_team_name") != binding.team_name:
        raise _error("AGENTCORE_TASK_SCOPE_MISMATCH")
    status = _text(getattr(value, "status", None), "task_status")
    if status not in _TASK_STATUSES:
        raise _error("INVALID_TASK_STATUS")
    current_execution_id = _optional_text(
        getattr(value, "current_execution_id", None), "current_execution_id"
    )
    execution_version = _integer(
        getattr(value, "execution_version", None), "execution_version"
    )
    if current_execution_id is not None and execution_version == 0:
        raise _error("INVALID_CURRENT_EXECUTION_VERSION")
    updated_at = getattr(value, "updated_at", None)
    return OpenJiuwenTask(
        task_id=_text(getattr(value, "task_id", None), "task_id"),
        title=_text(
            getattr(value, "title", None),
            "task_title",
            maximum=_MAX_TEXT_LENGTH,
            allow_empty=True,
        ),
        content=_text(
            getattr(value, "content", None),
            "task_content",
            maximum=_MAX_TEXT_LENGTH,
            allow_empty=True,
        ),
        status=status,
        assignee=_optional_text(getattr(value, "assignee", None), "task_assignee"),
        current_execution_id=current_execution_id,
        execution_version=execution_version,
        event_head=_integer(getattr(value, "event_head", None), "event_head"),
        updated_at=(
            None if updated_at is None else _integer(updated_at, "task_updated_at")
        ),
    )


def _project_execution(
    value: object,
    *,
    task: OpenJiuwenTask,
    binding: OpenJiuwenScopeBinding,
) -> OpenJiuwenTaskExecution:
    if (
        _text(getattr(value, "team_name", None), "execution_team_name")
        != binding.team_name
        or _text(getattr(value, "task_id", None), "execution_task_id") != task.task_id
    ):
        raise _error("AGENTCORE_EXECUTION_SCOPE_MISMATCH")
    execution_id = _text(getattr(value, "execution_id", None), "execution_id")
    execution_version = _integer(
        getattr(value, "execution_version", None), "execution_version"
    )
    if (
        execution_id != task.current_execution_id
        or execution_version != task.execution_version
    ):
        raise _error("AGENTCORE_EXECUTION_BINDING_MISMATCH")
    disposition = _text(getattr(value, "disposition", None), "execution_disposition")
    if disposition not in _EXECUTION_DISPOSITIONS:
        raise _error("INVALID_EXECUTION_DISPOSITION")
    owner_id = _optional_text(getattr(value, "owner_id", None), "execution_owner_id")
    raw_owner_epoch = getattr(value, "owner_epoch", None)
    owner_epoch = (
        None
        if raw_owner_epoch is None
        else _integer(raw_owner_epoch, "execution_owner_epoch")
    )
    if (owner_id is None) != (owner_epoch is None):
        raise _error("INCOMPLETE_EXECUTION_OWNER_BINDING")
    raw_outcome = getattr(value, "outcome", None)
    outcome = None if raw_outcome is None else _enum_text(raw_outcome, "outcome")
    if outcome is not None and outcome not in _EXECUTION_OUTCOMES:
        raise _error("INVALID_EXECUTION_OUTCOME")
    raw_result = getattr(value, "result_ref", None)
    result_ref = None if raw_result is None else _project_result_ref(raw_result)
    checkpoint_head = _integer(
        getattr(value, "checkpoint_head", None), "checkpoint_head"
    )
    if disposition == "prepared":
        valid = (
            task.status == "pending"
            and owner_id is None
            and outcome is None
            and result_ref is None
            and checkpoint_head == 0
        )
    elif disposition == "owned":
        valid = (
            task.status in _ACTIVE_TASK_STATUSES
            and task.assignee is not None
            and owner_id is not None
            and outcome is None
            and result_ref is None
        )
    elif disposition in {"recoverable", "orphaned"}:
        valid = (
            task.status in _ACTIVE_TASK_STATUSES
            and owner_id is None
            and outcome is None
            and result_ref is None
        )
    elif disposition in _TERMINAL_TASK_STATUSES:
        valid = (
            task.status == disposition
            and owner_id is None
            and outcome == disposition
            and (result_ref is None or disposition == "completed")
        )
    else:
        valid = False
    if not valid:
        raise _error("INVALID_EXECUTION_STATE_COMBINATION")
    return OpenJiuwenTaskExecution(
        task_id=task.task_id,
        execution_id=execution_id,
        profile_digest=_sha256(
            getattr(value, "profile_digest", None), "execution_profile_digest"
        ),
        generation=_integer(getattr(value, "generation", None), "generation"),
        owner_id=owner_id,
        owner_epoch=owner_epoch,
        disposition=disposition,
        execution_version=execution_version,
        checkpoint_head=checkpoint_head,
        outcome=outcome,
        result_ref=result_ref,
    )


def _project_snapshot(
    value: object,
    *,
    binding: OpenJiuwenScopeBinding,
    expected_task_id: str | None = None,
) -> OpenJiuwenTaskSnapshot:
    if _boolean(getattr(value, "executor_authority", None), "executor_authority"):
        raise _error("UNEXPECTED_EXECUTOR_AUTHORITY")
    task = _project_task(getattr(value, "task", None), binding)
    if expected_task_id is not None and task.task_id != expected_task_id:
        raise _error("AGENTCORE_TASK_BINDING_MISMATCH")
    raw_execution = getattr(value, "execution", None)
    if task.current_execution_id is None:
        if raw_execution is not None:
            raise _error("UNBOUND_EXECUTION")
        execution = None
    else:
        if raw_execution is None:
            raise _error("MISSING_CURRENT_EXECUTION")
        execution = _project_execution(raw_execution, task=task, binding=binding)
    return OpenJiuwenTaskSnapshot(task=task, execution=execution)


def _project_event(
    value: object,
    *,
    binding: OpenJiuwenScopeBinding,
    task_id: str,
    expected_sequence: int,
) -> OpenJiuwenTaskEvent:
    if (
        _text(getattr(value, "team_name", None), "event_team_name") != binding.team_name
        or _text(getattr(value, "stream_id", None), "event_stream_id") != task_id
    ):
        raise _error("AGENTCORE_EVENT_SCOPE_MISMATCH")
    sequence = _integer(
        getattr(value, "sequence", None), "event_sequence", positive=True
    )
    if sequence != expected_sequence:
        raise _error("NONCONTIGUOUS_TASK_EVENT_STREAM")
    event_type = _enum_text(getattr(value, "event_type", None), "event_type")
    if event_type not in _TASK_EVENT_TYPES:
        raise _error("INVALID_EVENT_TYPE")
    schema_version = _integer(
        getattr(value, "schema_version", None), "event_schema_version", positive=True
    )
    if schema_version != 1:
        raise _error("INVALID_EVENT_SCHEMA_VERSION")
    payload_json = _utf8_text(
        getattr(value, "payload_json", None),
        "event_payload_json",
        maximum_bytes=_MAX_EVENT_PAYLOAD_BYTES,
    )
    try:
        payload = json.loads(payload_json)
    except (TypeError, ValueError):
        raise _error("INVALID_EVENT_PAYLOAD_JSON") from None
    if type(payload) is not dict:
        raise _error("INVALID_EVENT_PAYLOAD_JSON")
    try:
        canonical = json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError):
        raise _error("INVALID_EVENT_PAYLOAD_JSON") from None
    if canonical != payload_json:
        raise _error("NONCANONICAL_EVENT_PAYLOAD")
    payload_digest = _sha256(
        getattr(value, "payload_digest", None), "event_payload_digest"
    )
    if hashlib.sha256(payload_json.encode("utf-8")).hexdigest() != payload_digest:
        raise _error("EVENT_PAYLOAD_DIGEST_MISMATCH")
    execution_id = _optional_text(
        getattr(value, "execution_id", None), "event_execution_id"
    )
    raw_execution_version = getattr(value, "execution_version", None)
    execution_version = (
        None
        if raw_execution_version is None
        else _integer(raw_execution_version, "event_execution_version", positive=True)
    )
    if (execution_id is None) != (execution_version is None):
        raise _error("INCOMPLETE_EVENT_EXECUTION_BINDING")
    return OpenJiuwenTaskEvent(
        task_id=task_id,
        sequence=sequence,
        event_id=_text(getattr(value, "event_id", None), "event_id"),
        event_type=event_type,
        schema_version=schema_version,
        producer=_text(getattr(value, "producer", None), "event_producer"),
        causation_id=_text(getattr(value, "causation_id", None), "event_causation_id"),
        correlation_id=_text(
            getattr(value, "correlation_id", None), "event_correlation_id"
        ),
        payload_json=payload_json,
        payload_digest=payload_digest,
        occurred_at=_integer(
            getattr(value, "occurred_at", None), "event_occurred_at", positive=True
        ),
        execution_id=execution_id,
        execution_version=execution_version,
    )


def _project_event_page(
    value: object,
    *,
    binding: OpenJiuwenScopeBinding,
    task_id: str,
    after_sequence: int,
    limit: int,
) -> OpenJiuwenTaskEventPage:
    head = _integer(getattr(value, "head_sequence", None), "event_head")
    if after_sequence > head:
        raise _error("EVENT_CURSOR_AHEAD_OF_HEAD")
    raw_events = getattr(value, "events", None)
    if type(raw_events) is not tuple or len(raw_events) > limit:
        raise _error("INVALID_EVENT_PAGE")
    events = tuple(
        _project_event(
            event,
            binding=binding,
            task_id=task_id,
            expected_sequence=after_sequence + index,
        )
        for index, event in enumerate(raw_events, start=1)
    )
    if after_sequence < head and not events:
        raise _error("INCOMPLETE_EVENT_PAGE")
    if events and events[-1].sequence > head:
        raise _error("EVENT_BEYOND_HEAD")
    if len(events) != min(limit, head - after_sequence):
        raise _error("INCOMPLETE_EVENT_PAGE")
    return OpenJiuwenTaskEventPage(head_sequence=head, events=events)


def _project_cursor(
    value: object,
    *,
    binding: OpenJiuwenScopeBinding,
    task_id: str,
    consumer_id: str,
    channel: str,
    head_sequence: int | None = None,
) -> OpenJiuwenTaskCursor:
    if (
        _text(getattr(value, "team_name", None), "cursor_team_name")
        != binding.team_name
        or _text(getattr(value, "stream_id", None), "cursor_stream_id") != task_id
        or _text(getattr(value, "consumer_id", None), "cursor_consumer_id")
        != consumer_id
        or _text(getattr(value, "channel", None), "cursor_channel") != channel
    ):
        raise _error("AGENTCORE_CURSOR_SCOPE_MISMATCH")
    sequence = _integer(getattr(value, "sequence", None), "cursor_sequence")
    version = _integer(getattr(value, "version", None), "cursor_version")
    if (sequence == 0) != (version == 0) or version > sequence:
        raise _error("INVALID_CURSOR_POSITION")
    if head_sequence is not None and sequence > head_sequence:
        raise _error("CURSOR_AHEAD_OF_HEAD")
    raw_event_id = getattr(value, "event_id", None)
    raw_digest = getattr(value, "event_payload_digest", None)
    raw_updated_at = getattr(value, "updated_at", None)
    if sequence == 0:
        if (
            raw_event_id is not None
            or raw_digest is not None
            or raw_updated_at is not None
        ):
            raise _error("INVALID_INITIAL_CURSOR_POSITION")
        event_id = None
        event_digest = None
        updated_at = None
    else:
        event_id = _text(raw_event_id, "cursor_event_id")
        event_digest = _sha256(raw_digest, "cursor_event_payload_digest")
        updated_at = _integer(raw_updated_at, "cursor_updated_at", positive=True)
    return OpenJiuwenTaskCursor(
        task_id=task_id,
        consumer_id=consumer_id,
        channel=channel,
        sequence=sequence,
        version=version,
        event_id=event_id,
        event_payload_digest=event_digest,
        updated_at=updated_at,
    )


class OpenJiuwenTaskFacade:
    """One immutable product-scope adapter over one bound AgentCore handle."""

    __slots__ = ("_binding", "_clock", "_handle", "_scope")

    def __init__(
        self,
        handle: AgentCoreTaskAuthorityPort,
        scope: ScopeRef,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not isinstance(scope, ScopeRef):
            raise _error("INVALID_PRODUCT_SCOPE")
        try:
            self._scope = ScopeRef.from_dict(scope.to_dict())
        except Exception:
            raise _error("INVALID_PRODUCT_SCOPE") from None
        self._binding = derive_openjiuwen_scope_binding(self._scope)
        self._handle = handle
        self._clock = clock or (lambda: datetime.now(UTC))
        self._require_handle_binding()

    @property
    def binding(self) -> OpenJiuwenScopeBinding:
        return self._binding

    @property
    def executor_authority(self) -> bool:
        return False

    def _require_handle_binding(self) -> None:
        binding = getattr(self._handle, "binding", None)
        methods = (
            "get",
            "list",
            "read_events",
            "read_unread",
            "advance_cursor",
        )
        if (
            binding is None
            or getattr(binding, "session_id", None) != self._binding.session_id
            or getattr(binding, "team_name", None) != self._binding.team_name
            or getattr(binding, "member_name", None) != self._binding.member_name
            or getattr(self._handle, "executor_authority", None) is not False
            or any(not callable(getattr(self._handle, name, None)) for name in methods)
        ):
            raise _error("AGENTCORE_BINDING_MISMATCH")

    def _require_authority(
        self,
        authority: ResolvedProductAuthority,
        *,
        operation: str,
        task_id: str | None,
    ) -> None:
        if type(authority) is not ResolvedProductAuthority:
            raise _error("INVALID_PRODUCT_AUTHORITY")
        if (
            authority.assurance is not Assurance.AUTHENTICATED
            or authority.scope != self._scope
            or authority.principal_id != self._scope.subject_id
            or authority.session_id != self._scope.session_id
            or authority.project_id != self._scope.project_id
        ):
            raise _error("PRODUCT_SCOPE_MISMATCH")
        if authority.operation != operation:
            raise _error("PRODUCT_OPERATION_MISMATCH")
        if authority.capabilities != frozenset({operation}):
            raise _error("PRODUCT_CAPABILITY_MISMATCH")
        now = self._clock()
        if not isinstance(now, datetime) or now.tzinfo is None:
            raise _error("INVALID_AUTHORITY_CLOCK")
        try:
            expiry = datetime.fromisoformat(authority.expires_at.replace("Z", "+00:00"))
        except (AttributeError, ValueError):
            raise _error("INVALID_PRODUCT_AUTHORITY_EXPIRY") from None
        if expiry.tzinfo is None:
            raise _error("INVALID_PRODUCT_AUTHORITY_EXPIRY")
        if expiry.astimezone(UTC) <= now.astimezone(UTC):
            raise _error("PRODUCT_AUTHORITY_EXPIRED")
        resource = authority.resource
        if task_id is None:
            if resource is not None:
                raise _error("UNEXPECTED_TASK_RESOURCE")
        else:
            expected_digest = hashlib.sha256(task_id.encode("utf-8")).hexdigest()
            if (
                resource is None
                or resource.kind != "task"
                or resource.resource_id != task_id
                or resource.fingerprint_sha256 != expected_digest
            ):
                raise _error("TASK_RESOURCE_MISMATCH")
        if authority.confirmation is not None:
            raise _error("UNEXPECTED_PRODUCT_CONFIRMATION")
        self._require_handle_binding()

    async def _call(self, operation: Awaitable[object]) -> object:
        try:
            return await operation
        except OpenJiuwenTaskFacadeError:
            raise
        except Exception:
            raise _error("AGENTCORE_AUTHORITY_FAILURE") from None

    async def get(
        self,
        authority: ResolvedProductAuthority,
        task_id: str,
    ) -> OpenJiuwenTaskSnapshot | None:
        task_id = _text(task_id, "task_id")
        self._require_authority(authority, operation="task.get", task_id=task_id)
        raw = await self._call(self._handle.get(task_id))
        if raw is None:
            return None
        return _project_snapshot(
            raw,
            binding=self._binding,
            expected_task_id=task_id,
        )

    async def list(
        self,
        authority: ResolvedProductAuthority,
        *,
        limit: int = 100,
    ) -> tuple[OpenJiuwenTaskSnapshot, ...]:
        if type(limit) is not int or not 1 <= limit <= _MAX_LIST_LIMIT:
            raise _error("INVALID_LIST_LIMIT")
        self._require_authority(authority, operation="task.list", task_id=None)
        raw = await self._call(self._handle.list(limit=limit))
        if type(raw) is not tuple or len(raw) > limit:
            raise _error("INVALID_TASK_LIST")
        projected = tuple(
            _project_snapshot(item, binding=self._binding) for item in raw
        )
        task_ids = tuple(item.task.task_id for item in projected)
        if task_ids != tuple(sorted(task_ids)) or len(set(task_ids)) != len(task_ids):
            raise _error("INVALID_TASK_LIST")
        return projected

    async def status(
        self,
        authority: ResolvedProductAuthority,
        task_id: str,
    ) -> OpenJiuwenTaskSnapshot | None:
        """Read the canonical snapshot under exact ``task.status`` authority."""

        task_id = _text(task_id, "task_id")
        self._require_authority(authority, operation="task.status", task_id=task_id)
        raw = await self._call(self._handle.get(task_id))
        if raw is None:
            return None
        return _project_snapshot(
            raw,
            binding=self._binding,
            expected_task_id=task_id,
        )

    async def apply_update(
        self,
        authority: ResolvedProductAuthority,
        task_id: str,
        command_id: str,
        *,
        expected_execution_version: int,
        expected_event_head: int,
        title: str | None = None,
        content: str | None = None,
    ) -> None:
        """Fail closed until a server-owned prepared patch binds confirmation."""

        raise _error("UNSUPPORTED_AGENTCORE_OPERATION")

    async def read_events(
        self,
        authority: ResolvedProductAuthority,
        task_id: str,
        *,
        after_sequence: int = 0,
        limit: int = 100,
    ) -> OpenJiuwenTaskEventPage:
        task_id = _text(task_id, "task_id")
        after_sequence = _integer(after_sequence, "after_sequence")
        if type(limit) is not int or not 1 <= limit <= _MAX_EVENT_LIMIT:
            raise _error("INVALID_EVENT_LIMIT")
        self._require_authority(authority, operation="task.events", task_id=task_id)
        raw = await self._call(
            self._handle.read_events(
                task_id,
                after_sequence=after_sequence,
                limit=limit,
            )
        )
        return _project_event_page(
            raw,
            binding=self._binding,
            task_id=task_id,
            after_sequence=after_sequence,
            limit=limit,
        )

    async def read_result(
        self,
        authority: ResolvedProductAuthority,
        task_id: str,
    ) -> OpenJiuwenTaskResultView | None:
        task_id = _text(task_id, "task_id")
        self._require_authority(authority, operation="task.result", task_id=task_id)
        raw = await self._call(self._handle.get(task_id))
        if raw is None:
            return None
        snapshot = _project_snapshot(
            raw,
            binding=self._binding,
            expected_task_id=task_id,
        )
        execution = snapshot.execution
        return OpenJiuwenTaskResultView(
            task_id=task_id,
            task_status=snapshot.task.status,
            execution_id=None if execution is None else execution.execution_id,
            outcome=None if execution is None else execution.outcome,
            result_ref=None if execution is None else execution.result_ref,
        )

    async def read_unread(
        self,
        authority: ResolvedProductAuthority,
        task_id: str,
        channel: str,
        *,
        limit: int = 100,
    ) -> OpenJiuwenTaskUnreadPage | None:
        task_id = _text(task_id, "task_id")
        channel = _text(channel, "presentation_channel")
        if channel not in _CHANNELS:
            raise _error("UNSUPPORTED_PRESENTATION_CHANNEL")
        if type(limit) is not int or not 1 <= limit <= _MAX_EVENT_LIMIT:
            raise _error("INVALID_EVENT_LIMIT")
        self._require_authority(
            authority,
            operation="task.unread_events",
            task_id=task_id,
        )
        raw = await self._call(
            self._handle.read_unread(
                task_id,
                self._binding.consumer_id,
                channel,
                limit=limit,
            )
        )
        if raw is None:
            return None
        head = _integer(getattr(raw, "head_sequence", None), "event_head")
        cursor = _project_cursor(
            getattr(raw, "cursor", None),
            binding=self._binding,
            task_id=task_id,
            consumer_id=self._binding.consumer_id,
            channel=channel,
            head_sequence=head,
        )
        raw_events = getattr(raw, "events", None)
        if type(raw_events) is not tuple or len(raw_events) > limit:
            raise _error("INVALID_UNREAD_PAGE")
        events = tuple(
            _project_event(
                event,
                binding=self._binding,
                task_id=task_id,
                expected_sequence=cursor.sequence + index,
            )
            for index, event in enumerate(raw_events, start=1)
        )
        if len(events) != min(limit, head - cursor.sequence):
            raise _error("INCOMPLETE_UNREAD_PAGE")
        has_more = _boolean(getattr(raw, "has_more", None), "unread_has_more")
        page_end = cursor.sequence + len(events)
        if has_more != (page_end < head):
            raise _error("INVALID_UNREAD_PAGE")
        expected_next = events[-1].sequence if has_more and events else None
        if getattr(raw, "next_after_sequence", None) != expected_next:
            raise _error("INVALID_UNREAD_PAGE")
        return OpenJiuwenTaskUnreadPage(
            cursor=cursor,
            head_sequence=head,
            events=events,
            next_after_sequence=expected_next,
            has_more=has_more,
        )

    async def advance_after_presentation_ack(
        self,
        authority: ResolvedProductAuthority,
        task_id: str,
        channel: str,
        advance_id: str,
        *,
        expected_cursor_sequence: int,
        expected_cursor_version: int,
        expected_head_sequence: int,
        acknowledged_sequence: int,
        acknowledged_event_id: str,
        acknowledged_event_payload_digest: str,
    ) -> OpenJiuwenCursorAdvanceDecision:
        task_id = _text(task_id, "task_id")
        channel = _text(channel, "presentation_channel")
        if channel not in _CHANNELS:
            raise _error("UNSUPPORTED_PRESENTATION_CHANNEL")
        advance_id = _text(advance_id, "advance_id")
        expected_cursor_sequence = _integer(
            expected_cursor_sequence, "expected_cursor_sequence"
        )
        expected_cursor_version = _integer(
            expected_cursor_version, "expected_cursor_version"
        )
        expected_head_sequence = _integer(
            expected_head_sequence, "expected_head_sequence"
        )
        acknowledged_sequence = _integer(
            acknowledged_sequence, "acknowledged_sequence", positive=True
        )
        acknowledged_event_id = _text(acknowledged_event_id, "acknowledged_event_id")
        acknowledged_event_payload_digest = _sha256(
            acknowledged_event_payload_digest,
            "acknowledged_event_payload_digest",
        )
        if (
            (expected_cursor_sequence == 0) != (expected_cursor_version == 0)
            or expected_cursor_version > expected_cursor_sequence
            or expected_cursor_sequence >= acknowledged_sequence
            or acknowledged_sequence > expected_head_sequence
        ):
            raise _error("INVALID_CURSOR_ADVANCE_REQUEST")
        self._require_authority(
            authority,
            operation="task.ack_events",
            task_id=task_id,
        )
        raw = await self._call(
            self._handle.advance_cursor(
                task_id,
                self._binding.consumer_id,
                channel,
                advance_id,
                expected_cursor_sequence=expected_cursor_sequence,
                expected_cursor_version=expected_cursor_version,
                expected_head_sequence=expected_head_sequence,
                acknowledged_sequence=acknowledged_sequence,
                acknowledged_event_id=acknowledged_event_id,
                acknowledged_event_payload_digest=acknowledged_event_payload_digest,
            )
        )
        ok = _boolean(getattr(raw, "ok", None), "cursor_advance_ok")
        replayed = _boolean(getattr(raw, "replayed", None), "cursor_advance_replayed")
        advanced = _boolean(getattr(raw, "advanced", None), "cursor_advance_advanced")
        reason = _text(
            getattr(raw, "reason", None),
            "cursor_advance_reason",
            maximum=_MAX_TEXT_LENGTH,
            allow_empty=True,
        )
        raw_cursor = getattr(raw, "cursor", None)
        raw_advance_id = getattr(raw, "advance_id", None)
        if not ok:
            if (
                not reason.strip()
                or replayed
                or advanced
                or raw_cursor is not None
                or raw_advance_id is not None
            ):
                raise _error("INVALID_CURSOR_ADVANCE_DECISION")
            return OpenJiuwenCursorAdvanceDecision(
                ok=False,
                reason=reason,
                advance_id=None,
                replayed=False,
                advanced=False,
                cursor=None,
            )
        if reason or raw_advance_id != advance_id or raw_cursor is None:
            raise _error("INVALID_CURSOR_ADVANCE_DECISION")
        cursor = _project_cursor(
            raw_cursor,
            binding=self._binding,
            task_id=task_id,
            consumer_id=self._binding.consumer_id,
            channel=channel,
        )
        if advanced and (
            cursor.sequence != acknowledged_sequence
            or cursor.version != expected_cursor_version + 1
            or cursor.event_id != acknowledged_event_id
            or cursor.event_payload_digest != acknowledged_event_payload_digest
        ):
            raise _error("INVALID_CURSOR_ADVANCE_DECISION")
        if not advanced and cursor.sequence < acknowledged_sequence:
            raise _error("INVALID_CURSOR_ADVANCE_DECISION")
        return OpenJiuwenCursorAdvanceDecision(
            ok=True,
            reason="",
            advance_id=advance_id,
            replayed=replayed,
            advanced=advanced,
            cursor=cursor,
        )

    def reject_unsupported(self, operation: str) -> None:
        operation = _text(operation, "operation")
        if operation in _SUPPORTED_OPERATIONS:
            raise _error("SUPPORTED_OPERATION_REQUIRES_EXACT_METHOD")
        if operation not in _UNSUPPORTED_OPERATIONS:
            raise _error("UNKNOWN_PRODUCT_OPERATION")
        raise _error("UNSUPPORTED_AGENTCORE_OPERATION")


__all__ = [
    "AgentCoreTaskAuthorityPort",
    "OpenJiuwenCursorAdvanceDecision",
    "OpenJiuwenScopeBinding",
    "OpenJiuwenTask",
    "OpenJiuwenTaskEvent",
    "OpenJiuwenTaskEventPage",
    "OpenJiuwenTaskExecution",
    "OpenJiuwenTaskFacade",
    "OpenJiuwenTaskFacadeError",
    "OpenJiuwenTaskResultRef",
    "OpenJiuwenTaskResultView",
    "OpenJiuwenTaskSnapshot",
    "OpenJiuwenTaskUnreadPage",
    "OpenJiuwenTaskCursor",
    "derive_openjiuwen_scope_binding",
]
