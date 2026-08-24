# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import asyncio
import hashlib
import inspect
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    Assurance,
    ErrorCode,
    QueryEnvelope,
    ScopeRef,
)
from jiuwenswarm.server.live_voice.formal_task_models import TaskAuthorizationGrant
from jiuwenswarm.server.live_voice.openjiuwen_product_query_adapter import (
    OpenJiuwenProductP3QueryOwner,
)
from jiuwenswarm.server.live_voice.openjiuwen_task_facade import (
    OpenJiuwenTaskFacade,
    OpenJiuwenTaskFacadeError,
    derive_openjiuwen_scope_binding,
)
from jiuwenswarm.server.live_voice.product_authority import (
    AuthorityResourceBinding,
    P3AuthorityContext,
    ResolvedProductAuthority,
)
from jiuwenswarm.server.live_voice.product_p3_text_adapter import (
    ProductP3AuthorizedQuery,
)

SCOPE = ScopeRef("principal-1", "project-1", "session-1", Assurance.AUTHENTICATED)
OTHER_SCOPE = ScopeRef(
    "principal-2",
    "project-2",
    "session-2",
    Assurance.AUTHENTICATED,
)
TASK = "task-1"
NOW = "2030-01-01T00:00:00Z"
EXPIRY = "2035-01-01T00:00:00Z"
PROJECTION = "openjiuwen.agentcore.task-query.v1"


def _resource(task_id: str) -> AuthorityResourceBinding:
    return AuthorityResourceBinding(
        "task",
        task_id,
        hashlib.sha256(task_id.encode("utf-8")).hexdigest(),
    )


def _authority(
    operation: str,
    *,
    scope: ScopeRef = SCOPE,
    task_id: str | None = TASK,
) -> ResolvedProductAuthority:
    return ResolvedProductAuthority(
        principal_id=scope.subject_id,
        session_id=scope.session_id,
        project_id=scope.project_id,
        scope=scope,
        operation=operation,
        capabilities=frozenset({operation}),
        expires_at=EXPIRY,
        assurance=Assurance.AUTHENTICATED,
        source="server.auth.session",
        correlation_id="correlation-1",
        resource=None if task_id is None else _resource(task_id),
        confirmation=None,
    )


def _query(
    operation: str,
    payload: dict[str, object],
    *,
    scope: ScopeRef = SCOPE,
    task_id: str | None = TASK,
    grant_operation: str | None = None,
    grant_capabilities: frozenset[str] | None = None,
    grant_expires_at: str = EXPIRY,
    authority_resource_task_id: str | None = None,
) -> ProductP3AuthorizedQuery:
    target_id = "task-list" if operation == "task.list" else task_id
    assert target_id is not None
    authority = _authority(
        operation,
        scope=scope,
        task_id=(
            task_id
            if authority_resource_task_id is None
            else authority_resource_task_id
        ),
    )
    envelope = QueryEnvelope.from_dict(
        {
            "contract_version": "live-voice.contract.v2",
            "request_id": f"request-{operation}",
            "query_type": operation,
            "issued_at": NOW,
            "scope": scope.to_dict(),
            "correlation_id": "correlation-1",
            "causation_id": None,
            "target_ref": {"kind": "task", "id": target_id},
            "context_refs": [],
            "required_capabilities": [operation],
            "payload": payload,
            "extensions": {},
        }
    )
    context = P3AuthorityContext(
        authority=authority,
        resource=authority.resource,
        command_id=None,
        target_task_id=task_id,
        intent_sha256=None,
        confirmation_id=None,
        confirmation_binding=None,
    )
    grant = TaskAuthorizationGrant(
        principal_id=scope.subject_id,
        scope=scope,
        operation=grant_operation or operation,
        command_id=None,
        target_task_id=task_id,
        allowed_capabilities=(
            frozenset({operation}) if grant_capabilities is None else grant_capabilities
        ),
        confirmation_id=None,
        confirmed=False,
        expires_at=grant_expires_at,
    )
    return ProductP3AuthorizedQuery(context, envelope, grant)


def _event(binding, sequence: int = 1):
    payload = "{}"
    return SimpleNamespace(
        team_name=binding.team_name,
        stream_id=TASK,
        sequence=sequence,
        event_id=f"event-{sequence}",
        event_type=SimpleNamespace(value="task.created"),
        schema_version=1,
        producer="task.create",
        causation_id=TASK,
        correlation_id=TASK,
        payload_json=payload,
        payload_digest=hashlib.sha256(payload.encode()).hexdigest(),
        occurred_at=sequence,
        execution_id=None,
        execution_version=None,
    )


def _completed_snapshot(binding):
    result_ref = SimpleNamespace(
        result_id="result-1",
        digest=hashlib.sha256(b"result").hexdigest(),
        locator="opaque/result-1",
    )
    task = SimpleNamespace(
        team_name=binding.team_name,
        task_id=TASK,
        title="title",
        content="content",
        status="completed",
        assignee=binding.member_name,
        current_execution_id="execution-1",
        execution_version=2,
        event_head=1,
        updated_at=1,
    )
    execution = SimpleNamespace(
        team_name=binding.team_name,
        task_id=TASK,
        execution_id="execution-1",
        profile_digest=hashlib.sha256(b"profile").hexdigest(),
        generation=1,
        owner_id=None,
        owner_epoch=None,
        disposition="completed",
        execution_version=2,
        checkpoint_head=1,
        outcome="completed",
        result_ref=result_ref,
    )
    return SimpleNamespace(
        task=task,
        execution=execution,
        executor_authority=False,
    )


class _Handle:
    def __init__(self, scope: ScopeRef = SCOPE) -> None:
        self.binding = derive_openjiuwen_scope_binding(scope)
        self.executor_authority = False
        self.snapshot = _completed_snapshot(self.binding)
        self.event = _event(self.binding)
        self.calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []
        self.missing = False
        self.failure: Exception | None = None

    def _record(self, name: str, *args: object, **kwargs: object) -> None:
        self.calls.append((name, args, kwargs))
        if self.failure is not None:
            raise self.failure

    async def get(self, task_id: str):
        self._record("get", task_id)
        return None if self.missing else self.snapshot

    async def list(self, *, limit: int = 100):
        self._record("list", limit=limit)
        return () if self.missing else (self.snapshot,)

    async def read_events(
        self,
        task_id: str,
        *,
        after_sequence: int = 0,
        limit: int = 100,
    ):
        self._record(
            "read_events",
            task_id,
            after_sequence=after_sequence,
            limit=limit,
        )
        return SimpleNamespace(head_sequence=1, events=(self.event,))

    async def read_unread(self, *args: object, **kwargs: object):
        self._record("read_unread", *args, **kwargs)
        raise AssertionError("unread is outside this query adapter")

    async def advance_cursor(self, *args: object, **kwargs: object):
        self._record("advance_cursor", *args, **kwargs)
        raise AssertionError("cursor advance is outside this query adapter")


def _owner(
    *,
    scope: ScopeRef = SCOPE,
) -> tuple[OpenJiuwenProductP3QueryOwner, _Handle]:
    handle = _Handle(scope)
    facade = OpenJiuwenTaskFacade(
        handle,
        scope,
        clock=lambda: datetime.fromisoformat(NOW.replace("Z", "+00:00")).astimezone(
            UTC
        ),
    )
    return OpenJiuwenProductP3QueryOwner(facade), handle


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["task.get", "task.status"])
async def test_task_snapshot_queries_return_versioned_agentcore_facts(
    operation: str,
) -> None:
    owner, handle = _owner()

    result = await owner.query(_query(operation, {}), now=NOW)

    assert result.ok is True
    assert result.result is not None
    assert result.result["projection"] == PROJECTION
    assert result.result["task"]["task_id"] == TASK
    assert result.result["task"]["status"] == "completed"
    assert result.result["execution"]["result_ref"] == {
        "result_id": "result-1",
        "digest": hashlib.sha256(b"result").hexdigest(),
        "locator": "opaque/result-1",
    }
    assert handle.calls == [("get", (TASK,), {})]


@pytest.mark.asyncio
async def test_list_is_bounded_and_does_not_invent_continuation_truth() -> None:
    owner, handle = _owner()

    result = await owner.query(
        _query("task.list", {"cursor": None, "limit": 10}, task_id=None),
        now=NOW,
    )

    assert result.ok is True
    assert result.result is not None
    assert result.result["projection"] == PROJECTION
    assert result.result["returned_count"] == 1
    assert result.result["boundary_reached"] is False
    assert result.result["continuation_supported"] is False
    assert result.result["cursor"] is None
    assert handle.calls == [("list", (), {"limit": 10})]


@pytest.mark.asyncio
async def test_list_cursor_fails_before_facade_call() -> None:
    owner, handle = _owner()

    result = await owner.query(
        _query("task.list", {"cursor": "opaque", "limit": 10}, task_id=None),
        now=NOW,
    )

    assert result.ok is False
    assert result.error is not None
    assert result.error.code is ErrorCode.CAPABILITY_UNAVAILABLE
    assert result.error.reason == "OPENJIUWEN_LIST_CONTINUATION_UNAVAILABLE"
    assert handle.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("cursor", ["", 0, True, {}, "x" * 257, "bad\x00cursor"])
async def test_malformed_list_cursor_is_invalid_before_facade(cursor: object) -> None:
    owner, handle = _owner()

    result = await owner.query(
        _query("task.list", {"cursor": cursor, "limit": 10}, task_id=None),
        now=NOW,
    )

    assert result.ok is False
    assert result.error is not None
    assert result.error.code is ErrorCode.INVALID_ARGUMENT
    assert result.error.reason == "INVALID_OPENJIUWEN_LIST_QUERY"
    assert handle.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", [0, 101, True])
async def test_list_bounds_fail_before_facade_call(limit: object) -> None:
    owner, handle = _owner()

    result = await owner.query(
        _query("task.list", {"cursor": None, "limit": limit}, task_id=None),
        now=NOW,
    )

    assert result.ok is False
    assert result.error is not None
    assert result.error.code is ErrorCode.INVALID_ARGUMENT
    assert result.error.reason == "INVALID_OPENJIUWEN_LIST_QUERY"
    assert handle.calls == []


@pytest.mark.asyncio
async def test_events_preserve_head_order_and_exact_canonical_payload() -> None:
    owner, handle = _owner()

    result = await owner.query(
        _query("task.events", {"after_seq": -1, "limit": 20}),
        now=NOW,
    )

    assert result.ok is True
    assert result.result is not None
    assert result.result["after_seq"] == -1
    assert result.result["normalized_after_sequence"] == 0
    assert result.result["head_seq"] == 1
    assert result.result["next_after_seq"] is None
    assert result.result["has_more"] is False
    assert result.result["events"][0]["payload_json"] == "{}"
    assert result.result["events"][0]["sequence"] == 1
    assert handle.calls == [
        ("read_events", (TASK,), {"after_sequence": 0, "limit": 20})
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("after_seq", "limit"),
    [(-2, 10), (True, 10), (0, 0), (0, 501), (0, True)],
)
async def test_event_bounds_fail_before_facade_call(
    after_seq: object,
    limit: object,
) -> None:
    owner, handle = _owner()

    result = await owner.query(
        _query("task.events", {"after_seq": after_seq, "limit": limit}),
        now=NOW,
    )

    assert result.ok is False
    assert result.error is not None
    assert result.error.code is ErrorCode.INVALID_ARGUMENT
    assert handle.calls == []


@pytest.mark.asyncio
async def test_unknown_task_payload_fails_before_facade_call() -> None:
    owner, handle = _owner()

    result = await owner.query(_query("task.get", {"unexpected": True}), now=NOW)

    assert result.ok is False
    assert result.error is not None
    assert result.error.code is ErrorCode.INVALID_ARGUMENT
    assert handle.calls == []


@pytest.mark.asyncio
async def test_unsupported_valid_query_returns_stable_failure_without_facade() -> None:
    owner, handle = _owner()

    result = await owner.query(
        _query(
            "task.unread_events",
            {"presentation_class": "text", "limit": 10},
        ),
        now=NOW,
    )

    assert result.ok is False
    assert result.error is not None
    assert result.error.code is ErrorCode.UNSUPPORTED
    assert result.error.reason == "UNSUPPORTED_OPENJIUWEN_QUERY"
    assert handle.calls == []


@pytest.mark.asyncio
async def test_result_query_returns_reference_without_claiming_result_bytes() -> None:
    owner, handle = _owner()

    result = await owner.query(_query("task.result", {}), now=NOW)

    assert result.ok is True
    assert result.result == {
        "projection": PROJECTION,
        "task_id": TASK,
        "task_status": "completed",
        "execution_id": "execution-1",
        "outcome": "completed",
        "result_ref": {
            "result_id": "result-1",
            "digest": hashlib.sha256(b"result").hexdigest(),
            "locator": "opaque/result-1",
        },
    }
    assert handle.calls == [("get", (TASK,), {})]


@pytest.mark.asyncio
async def test_missing_task_returns_stable_not_found() -> None:
    owner, handle = _owner()
    handle.missing = True

    result = await owner.query(_query("task.get", {}), now=NOW)

    assert result.ok is False
    assert result.error is not None
    assert result.error.code is ErrorCode.NOT_FOUND
    assert result.error.reason == "OPENJIUWEN_TASK_NOT_FOUND"
    assert handle.calls == [("get", (TASK,), {})]


@pytest.mark.asyncio
async def test_wrong_grant_fails_before_facade_and_is_replay_safe() -> None:
    owner, handle = _owner()
    invocation = _query("task.get", {}, grant_operation="task.status")

    first = await owner.query(invocation, now=NOW)
    second = await owner.query(invocation, now=NOW)

    assert first.to_dict() == second.to_dict()
    assert first.ok is False
    assert first.error is not None
    assert first.error.code is ErrorCode.PERMISSION_DENIED
    assert handle.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invocation",
    [
        _query(
            "task.get",
            {},
            grant_capabilities=frozenset({"task.get", "task.status"}),
        ),
        _query("task.get", {}, grant_expires_at="2099-01-01T00:00:00Z"),
    ],
)
async def test_noncanonical_grant_fails_before_facade(
    invocation: ProductP3AuthorizedQuery,
) -> None:
    owner, handle = _owner()

    result = await owner.query(invocation, now=NOW)

    assert result.ok is False
    assert result.error is not None
    assert result.error.code is ErrorCode.PERMISSION_DENIED
    assert result.error.reason == "OPENJIUWEN_QUERY_AUTHORIZATION_DENIED"
    assert handle.calls == []


@pytest.mark.asyncio
async def test_resource_rebinding_fails_before_facade() -> None:
    owner, handle = _owner()
    invocation = _query(
        "task.get",
        {},
        authority_resource_task_id="task-2",
    )

    result = await owner.query(invocation, now=NOW)

    assert result.ok is False
    assert result.error is not None
    assert result.error.code is ErrorCode.PERMISSION_DENIED
    assert result.error.reason == "OPENJIUWEN_QUERY_AUTHORIZATION_DENIED"
    assert handle.calls == []


@pytest.mark.asyncio
async def test_foreign_scope_and_dependency_failure_fail_closed() -> None:
    owner, handle = _owner()
    foreign = _query("task.get", {}, scope=OTHER_SCOPE)

    foreign_result = await owner.query(foreign, now=NOW)
    assert foreign_result.ok is False
    assert foreign_result.error is not None
    assert foreign_result.error.code is ErrorCode.PERMISSION_DENIED
    assert foreign_result.error.reason == "OPENJIUWEN_QUERY_AUTHORIZATION_DENIED"
    assert handle.calls == []

    handle.failure = RuntimeError("database secret")
    with pytest.raises(OpenJiuwenTaskFacadeError) as dependency_error:
        await owner.query(_query("task.get", {}), now=NOW)
    assert dependency_error.value.reason == "AGENTCORE_AUTHORITY_FAILURE"
    assert "secret" not in str(dependency_error.value)
    assert handle.calls == [("get", (TASK,), {})]


@pytest.mark.asyncio
async def test_concurrent_get_and_status_share_no_query_owner_state() -> None:
    owner, handle = _owner()

    get_result, status_result = await asyncio.gather(
        owner.query(_query("task.get", {}), now=NOW),
        owner.query(_query("task.status", {}), now=NOW),
    )

    assert get_result.ok and status_result.ok
    assert get_result.result == status_result.result
    assert handle.calls == [("get", (TASK,), {}), ("get", (TASK,), {})]


def test_owner_rejects_wrong_facade_type() -> None:
    with pytest.raises(ValueError, match="facade is required"):
        OpenJiuwenProductP3QueryOwner(object())


def test_query_owner_has_no_agentcore_internal_or_legacy_store_import() -> None:
    import jiuwenswarm.server.live_voice.openjiuwen_product_query_adapter as module

    source = inspect.getsource(module)
    assert "openjiuwen.agent_teams" not in source
    assert "SqliteTaskStore" not in source
    assert "persistent_task_core" not in source
