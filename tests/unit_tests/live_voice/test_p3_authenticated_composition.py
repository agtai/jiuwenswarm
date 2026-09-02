# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import sqlite3
import subprocess
import threading
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from jiuwenswarm.common.schema.agent import AgentRequest
from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    Assurance,
    CONTRACT_VERSION,
    CommandEnvelope,
    ErrorCode,
    ProducerRef,
    ResponseRef,
    ScopeRef,
    TerminalOutcome,
    TurnCommit,
    TurnCommitLedger,
)
from jiuwenswarm.common.schema.message import ReqMethod
from jiuwenswarm.server.agent_ws_server import AgentWebSocketServer
from jiuwenswarm.server.live_voice.formal_task_models import (
    AdmissionDisposition,
    AdmissionPolicy,
    ExecutorDeliveryResult,
    ExecutorObservation,
    ExecutorResolution,
    ExecutorRetryReadiness,
    FormalAttemptState,
    FormalTaskState,
    FormalTaskViolation,
    OutboxState,
    PersistentAttemptRecord,
    PersistentOutboxItem,
    PersistentTaskRecord,
    ReconciliationState,
    ResolvedTaskContext,
    TaskAuthorizationGrant,
    TaskAdjustmentDeliveryResult,
    TaskAdjustmentSettlement,
    TaskAdjustmentState,
    utc_now,
)
from jiuwenswarm.server.live_voice.executor_capabilities import (
    ExecutorCapabilityProfile,
)
from jiuwenswarm.server.live_voice.live_voice_configuration_declaration import (
    AuthenticationMode,
    DurabilityLevel,
    LiveVoiceCapability,
)
from jiuwenswarm.server.live_voice.p3_authenticated_composition import (
    AgentManagerProjectBindingResolver,
    AuthenticatedPrincipal,
    P3AuthenticatedComposition,
    PreparedProductionIntentAuthority,
    P3_MUTATIONS,
    P3_OPERATIONS,
    P3_PRODUCTION_OPERATIONS,
    P3_PRODUCT_AUTHORITY_OPERATIONS,
    P3_ROUTE_METHODS,
    P3_TARGETED_MUTATIONS,
    P3RouteTelemetry,
    ResolvedAuthority,
    ServerSessionProjectAuthorityResolver,
    StaticBearerAuthenticator,
    _DirectP3RuntimeOwner,
    _resolve_database_path,
    create_p3_composition_from_environment,
)
from jiuwenswarm.server.live_voice.p3_production_intent_composition import (
    CallLocalProductionConfirmationConsumer,
    CallLocalProductionOriginAuthority,
    StoreProductionTaskAuthorityReader,
    production_context_fingerprint,
    production_model_binding_fingerprint,
)
from jiuwenswarm.server.live_voice.presentation_ledger import (
    TaskPresentationDelivery,
)
from jiuwenswarm.server.live_voice.product_composition_registry import (
    AgentServerProductCompositionRegistry,
    ProductCompositionSettings,
    _project_production_status_authority,
)
from jiuwenswarm.server.live_voice.product_authority import (
    AuthorityDecisionStatus,
    AuthorityRouteContext,
    ProductAuthorityRequest,
    ProductAuthorityService,
)
from jiuwenswarm.server.live_voice.product_observability_runtime import (
    BoundedInMemoryOtelBackend,
)
from jiuwenswarm.server.live_voice.p3_confirmation import (
    BoundedP3ConfirmationOwner,
    P3ConfirmationBinding,
    P3ConfirmationOwnerContext,
    PreparedP3RetryFacts,
    SqliteP3ConfirmationLedger,
    TrustedP3ConfirmationIssue,
    p3_confirmation_intent_fingerprint,
)
from jiuwenswarm.server.live_voice.p3_product_confirmation import (
    ProductP3ConfirmationForwarder,
)
from jiuwenswarm.server.live_voice.p3_model_resolution import (
    ResolvedP3Model,
    ServerModelCatalogResolver,
)
from jiuwenswarm.server.live_voice.persistent_task_core import PersistentTaskCore
from jiuwenswarm.server.live_voice.project_code_executor import (
    DirectProjectCodeExecutorAdapter,
    DirectProjectManagedBaselineReader,
    FORMAL_PROJECT_EXECUTOR_ID,
    ProjectExecutionBinding,
)
from jiuwenswarm.server.live_voice.production_task_classifier import (
    ProductionTaskIntentClassifier,
)
from jiuwenswarm.server.live_voice.production_task_intent import (
    BoundedClarificationOwner,
    ProductionIntentOrigin,
    ProductionTaskIntentRequest,
    build_production_origin_binding,
)
from jiuwenswarm.server.live_voice.task_store import SqliteTaskStore
from jiuwenswarm.server.live_voice.task_progress_return import (
    TaskProgressOriginBinding,
    TaskProgressOriginKind,
)
from jiuwenswarm.server.live_voice.voice_task_bridge import VoiceTaskBridge
from jiuwenswarm.server.live_voice.voice_task_policy import FormalTaskPolicyAdapter

NOW = "2026-08-05T12:00:00Z"
EXPIRY = "2026-08-05T13:00:00Z"
TOKEN = "test-only-p3-bearer-token-000000000000"


def _scope(*, project_id: str = "project-1", session_id: str = "session-1") -> ScopeRef:
    return ScopeRef("user-1", project_id, session_id, Assurance.AUTHENTICATED)


def _context(
    project: Path,
    *,
    project_id: str = "project-1",
    session_id: str = "session-1",
    expires_at: str = EXPIRY,
    redacted: bool = False,
) -> ResolvedTaskContext:
    return ResolvedTaskContext(
        source="agent_server.session_project_registry",
        stable_id=project_id,
        uri=project.resolve().as_uri(),
        revision_kind="version",
        revision_value="a77516a0",
        scope=_scope(project_id=project_id, session_id=session_id),
        permissions=("task.execute", "project.write"),
        expires_at=expires_at,
        redaction_policy_id="live_voice.p3alpha.project.v1",
        redacted=redacted,
        redacted_fields=(("secret",) if redacted else ()),
    )


class _AuthorityResolver:
    def __init__(self, contexts: dict[str, ResolvedTaskContext]) -> None:
        self.contexts = contexts
        self.calls: list[tuple[str, bool]] = []
        self.dirty = False

    def resolve(self, principal, *, session_id: str, now: str, require_clean: bool):
        del now
        self.calls.append((session_id, require_clean))
        if require_clean and self.dirty:
            raise FormalTaskViolation(
                "TASK_CONTEXT_WORKTREE_DIRTY",
                "formal task project must have a clean worktree",
                ErrorCode.PERMISSION_DENIED,
            )
        context = self.contexts.get(session_id)
        if (
            context is None
            or context.scope.project_id not in principal.allowed_project_ids
        ):
            raise FormalTaskViolation(
                "FORMAL_TASK_AUTHORIZATION_DENIED",
                "formal task scope is unavailable",
                ErrorCode.PERMISSION_DENIED,
            )
        return ResolvedAuthority(principal, context.scope, context)


def _observations(
    item: PersistentOutboxItem,
    *,
    outcome: TerminalOutcome | None = None,
) -> tuple[ExecutorObservation, ...]:
    target_seq = 2 if outcome is not None else 1
    states = (
        (FormalAttemptState.ACCEPTED, None),
        (FormalAttemptState.RUNNING, None),
        (FormalAttemptState.TERMINAL, outcome),
    )
    return tuple(
        ExecutorObservation(
            resolution=ExecutorResolution.KNOWN,
            executor_id=FORMAL_PROJECT_EXECUTOR_ID,
            executor_ref=f"carrier:{item.attempt_id}",
            task_id=item.task_id,
            attempt_id=item.attempt_id,
            source_event_id=f"carrier:{item.attempt_id}:{seq}",
            source_seq=seq,
            attempt_state=states[seq][0],
            attempt_outcome=states[seq][1],
            occurred_at=utc_now(),
            raw_status=(outcome.value if outcome is not None else "running"),
            adapter_id=(None if item.selection is None else item.selection.adapter_id),
            capability_profile_digest=(
                None
                if item.selection is None
                else item.selection.capability_profile_digest
            ),
        )
        for seq in range(item.source_seq + 1, target_seq + 1)
    )


class _Executor:
    executor_id = FORMAL_PROJECT_EXECUTOR_ID

    def __init__(self) -> None:
        self.dispatches: list[str] = []
        self.cancels: list[str] = []
        self.statuses: list[str] = []
        self.adjustments: list[str] = []
        self.adjustment_settlements: list[tuple[str, TaskAdjustmentState]] = []
        self.readiness: list[tuple[str, str]] = []
        self.retry_ready = True
        self.dispatch_outcome: TerminalOutcome | None = None

    def retry_readiness(
        self,
        task: PersistentTaskRecord,
        attempt: PersistentAttemptRecord,
    ) -> ExecutorRetryReadiness:
        self.readiness.append((task.task_id, attempt.attempt_id))
        assert attempt.outcome is not None
        return ExecutorRetryReadiness(
            task_id=task.task_id,
            previous_attempt_id=attempt.attempt_id,
            previous_outcome=attempt.outcome,
            previous_attempt_number=attempt.attempt_number,
            ready=self.retry_ready,
            reason=(
                "PREDECESSOR_QUIESCENT"
                if self.retry_ready
                else "ATTEMPT_CLEANUP_RETAINED"
            ),
        )

    async def dispatch(self, item: PersistentOutboxItem) -> ExecutorDeliveryResult:
        self.dispatches.append(item.attempt_id)
        return ExecutorDeliveryResult(
            f"carrier:{item.attempt_id}",
            _observations(item, outcome=self.dispatch_outcome),
        )

    async def cancel(self, item: PersistentOutboxItem) -> ExecutorDeliveryResult:
        self.cancels.append(item.attempt_id)
        return ExecutorDeliveryResult(
            f"carrier:{item.attempt_id}",
            _observations(item, outcome=TerminalOutcome.CANCELLED),
        )

    async def adjust(self, item: PersistentOutboxItem) -> TaskAdjustmentDeliveryResult:
        assert item.adjustment is not None
        self.adjustments.append(item.adjustment.adjustment_id)
        return TaskAdjustmentDeliveryResult(
            f"carrier:{item.attempt_id}",
            item.adjustment.adjustment_id,
            TaskAdjustmentState.APPLIED,
        )

    async def settle_adjustment(
        self,
        item: PersistentOutboxItem,
        settlement: TaskAdjustmentSettlement,
    ) -> None:
        self.adjustment_settlements.append((item.command_id, settlement.state))

    async def status(
        self,
        task: PersistentTaskRecord,
        attempt: PersistentAttemptRecord,
    ) -> ExecutorDeliveryResult:
        self.statuses.append(task.task_id)
        return ExecutorDeliveryResult(attempt.executor_ref or "", ())


class _CloseRecorder:
    def __init__(self) -> None:
        self.calls = 0

    async def close(self) -> None:
        self.calls += 1


class _Telemetry:
    def __init__(self) -> None:
        self.events: list[P3RouteTelemetry] = []

    def emit(self, event: P3RouteTelemetry) -> None:
        self.events.append(event)


class _ModelResolver:
    def __init__(self) -> None:
        self.identity = "default#0"
        self.config_version = "catalog-v1"
        self.calls: list[str | None] = []

    def resolve(
        self,
        model_intent: str | None,
        *,
        expected_identity: str | None = None,
        expected_config_version: str | None = None,
        instantiate: bool = False,
    ) -> ResolvedP3Model:
        self.calls.append(model_intent)
        if model_intent not in {None, "default", self.identity}:
            raise FormalTaskViolation(
                "P3_MODEL_INTENT_UNKNOWN",
                "unknown model",
                ErrorCode.CAPABILITY_UNAVAILABLE,
            )
        if (expected_identity is not None and expected_identity != self.identity) or (
            expected_config_version is not None
            and expected_config_version != self.config_version
        ):
            raise FormalTaskViolation(
                "EXECUTOR_MODEL_BINDING_DRIFT",
                "model drift",
                ErrorCode.PERMISSION_DENIED,
            )
        return ResolvedP3Model(
            object() if instantiate else None,
            self.identity,
            self.config_version,
        )


class _NoProductionConfirmation:
    def verify_and_consume(self, confirmation_id, binding):
        del confirmation_id, binding
        raise AssertionError("read-only production query consumed confirmation")


def _confirmed_production_resolution(
    harness: _Harness,
    tmp_path: Path,
    *,
    operation: str,
    target: str | None,
    arguments: dict[str, object],
    identity: str,
    now: str,
    expires_at: str,
):
    classifier = ProductionTaskIntentClassifier()
    proposal = classifier.parse_structured(
        {"operation": operation, "target": target, "arguments": arguments},
        committed=True,
        source_confidence=1.0,
    )
    request = ProductionTaskIntentRequest(
        origin=ProductionIntentOrigin.STRUCTURED,
        scope=_scope(),
        command_id=f"command-production-{identity}",
        proposal=proposal,
        source_id=f"structured-production-{identity}",
    )
    expected_origin = build_production_origin_binding(request)
    origin_authority = CallLocalProductionOriginAuthority(
        expected_binding=expected_origin
    )
    reader_arguments: dict[str, object] = {
        "store": harness.composition._core.store,
        "principal_id": _scope().subject_id,
        "scope": _scope(),
        "authority_context_fingerprint": production_context_fingerprint(
            harness.authority.contexts["session-1"]
        ),
    }
    if operation == "task.create":
        reader_arguments["collection_capability_profile_digest"] = (
            harness.composition._select_production_create_candidate().capability_profile_digest
        )
        reader_arguments["collection_model_binding_fingerprint"] = (
            production_model_binding_fingerprint(
                {
                    "model_config_version": harness.models.config_version,
                    "model_identity": harness.models.identity,
                }
            )
        )
    reader = StoreProductionTaskAuthorityReader(**reader_arguments)
    clarification = BoundedClarificationOwner(
        capacity=8,
        per_subject_capacity=2,
        boot_id=f"production-{identity}-boot",
    )
    bridge = VoiceTaskBridge()
    prepared = bridge.resolve_production(
        request,
        reader,
        origin_authority,
        _NoProductionConfirmation(),
        clarification,
    )
    assert prepared.confirmation == "required", prepared
    assert prepared.confirmation_binding is not None
    production_binding = prepared.confirmation_binding
    p3_binding = P3ConfirmationBinding(
        principal_id=_scope().subject_id,
        scope=_scope(),
        operation=production_binding.operation,
        command_id=production_binding.command_id,
        target_task_id=production_binding.target_task_id,
        intent_fingerprint=production_binding.fingerprint,
    )
    owner_context = P3ConfirmationOwnerContext(
        session_id="session-1",
        correlation_id=f"correlation-production-{identity}",
        owner_generation=1,
    )
    owner = BoundedP3ConfirmationOwner(
        harness.database,
        enabled=True,
    )
    confirmation_id = f"confirmation-production-{identity}"
    owner.issue(
        TrustedP3ConfirmationIssue(
            binding=p3_binding,
            owner=owner_context,
            expires_at=expires_at,
            confirmation_id=confirmation_id,
        ),
        now=now,
    )
    validated = owner.validate_for_forwarding(
        confirmation_id,
        p3_binding,
        owner_context,
        now=now,
    )
    consumer = CallLocalProductionConfirmationConsumer(
        expected_binding=production_binding,
        validated=validated,
        forwarder=ProductP3ConfirmationForwarder(owner),
        now=now,
    )
    confirmed = bridge.resolve_production(
        replace(request, confirmation_id=confirmation_id),
        reader,
        origin_authority,
        consumer,
        clarification,
    )
    assert confirmed.confirmation == "confirmed", confirmed
    return confirmed, origin_authority, consumer


@pytest.mark.asyncio
async def test_production_core_rejects_duck_typed_origin_authority(
    tmp_path: Path,
) -> None:
    run_now = "2026-08-21T02:00:00Z"
    harness = _harness(
        tmp_path,
        contexts={
            "session-1": _context(
                tmp_path,
                expires_at="2026-08-22T04:00:00Z",
            )
        },
        executor_profiles=(DirectProjectCodeExecutorAdapter.capability_profile(),),
        expires_at="2026-08-22T04:00:00Z",
        clock=lambda: run_now,
    )
    await harness.composition.start()
    await _stop_test_reconciliation_worker(harness.composition)
    try:
        resolution, _origin_authority, consumer = _confirmed_production_resolution(
            harness,
            tmp_path,
            operation="task.create",
            target=None,
            arguments={"name": "sealed", "instruction": "stay sealed"},
            identity="forged-origin",
            now=run_now,
            expires_at="2026-08-21T02:02:00Z",
        )
        before = _store_counts(harness.database)

        class _ForgedOriginAuthority:
            calls = 0

            def verify_origin(self, _binding):
                self.calls += 1
                raise AssertionError("duck-typed origin authority was invoked")

        forged = _ForgedOriginAuthority()
        routed = await harness.composition.handle_production_resolution(
            resolution=resolution,
            bearer_token=TOKEN,
            request_id="request-production-forged-origin",
            session_id="session-1",
            correlation_id="correlation-production-forged-origin",
            origin_authority=forged,  # type: ignore[arg-type]
            confirmation_consumer=consumer,
        )

        assert routed.ok is False
        assert routed.payload["error"]["reason"] == (
            "PRODUCTION_ORIGIN_AUTHORITY_MISMATCH"
        )
        assert forged.calls == 0
        assert _store_counts(harness.database) == before
        assert harness.executor.dispatches == []
        assert harness.executor.cancels == []
        assert harness.executor.adjustments == []
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_production_core_rejects_duck_typed_confirmation_consumer(
    tmp_path: Path,
) -> None:
    run_now = "2026-08-21T02:00:00Z"
    harness = _harness(
        tmp_path,
        contexts={
            "session-1": _context(
                tmp_path,
                expires_at="2026-08-22T04:00:00Z",
            )
        },
        executor_profiles=(DirectProjectCodeExecutorAdapter.capability_profile(),),
        expires_at="2026-08-22T04:00:00Z",
        clock=lambda: run_now,
    )
    await harness.composition.start()
    await _stop_test_reconciliation_worker(harness.composition)
    try:
        resolution, origin_authority, _consumer = _confirmed_production_resolution(
            harness,
            tmp_path,
            operation="task.create",
            target=None,
            arguments={"name": "sealed", "instruction": "stay sealed"},
            identity="forged-consumer",
            now=run_now,
            expires_at="2026-08-21T02:02:00Z",
        )
        before = _store_counts(harness.database)

        class _ForgedConsumer:
            def claim_for(self, _resolution):
                raise AssertionError("duck-typed confirmation consumer was invoked")

        routed = await harness.composition.handle_production_resolution(
            resolution=resolution,
            bearer_token=TOKEN,
            request_id="request-production-forged-consumer",
            session_id="session-1",
            correlation_id="correlation-production-forged-consumer",
            origin_authority=origin_authority,
            confirmation_consumer=_ForgedConsumer(),  # type: ignore[arg-type]
        )

        assert routed.ok is False
        assert routed.payload["error"]["reason"] == "PRODUCTION_CONFIRMATION_REQUIRED"
        assert _store_counts(harness.database) == before
        assert harness.executor.dispatches == []
        assert harness.executor.cancels == []
        assert harness.executor.adjustments == []

        production_binding = resolution.confirmation_binding
        assert production_binding is not None
        rogue_owner = BoundedP3ConfirmationOwner(
            tmp_path / "rogue-production-confirmations.sqlite3",
            enabled=True,
        )
        rogue_p3_binding = P3ConfirmationBinding(
            principal_id=production_binding.principal_id,
            scope=production_binding.scope,
            operation=production_binding.operation,
            command_id=production_binding.command_id,
            target_task_id=production_binding.target_task_id,
            intent_fingerprint=production_binding.fingerprint,
        )
        rogue_context = P3ConfirmationOwnerContext(
            session_id="session-1",
            correlation_id="correlation-production-forged-ledger",
            owner_generation=1,
        )
        rogue_id = "confirmation-production-forged-ledger"
        rogue_owner.issue(
            TrustedP3ConfirmationIssue(
                binding=rogue_p3_binding,
                owner=rogue_context,
                expires_at="2026-08-21T02:02:00Z",
                confirmation_id=rogue_id,
            ),
            now=run_now,
        )
        rogue_consumer = CallLocalProductionConfirmationConsumer(
            expected_binding=production_binding,
            validated=rogue_owner.validate_for_forwarding(
                rogue_id,
                rogue_p3_binding,
                rogue_context,
                now=run_now,
            ),
            forwarder=ProductP3ConfirmationForwarder(rogue_owner),
            now=run_now,
        )
        rogue_receipt = rogue_consumer.verify_and_consume(rogue_id, production_binding)
        rogue_routed = await harness.composition.handle_production_resolution(
            resolution=replace(
                resolution,
                confirmation_consumption_id=rogue_receipt.consumption_id,
            ),
            bearer_token=TOKEN,
            request_id="request-production-forged-ledger",
            session_id="session-1",
            correlation_id="correlation-production-forged-ledger",
            origin_authority=origin_authority,
            confirmation_consumer=rogue_consumer,
        )
        assert rogue_routed.ok is False
        assert rogue_routed.payload["error"]["reason"] == (
            "PRODUCTION_CONFIRMATION_REQUIRED"
        )
        assert _store_counts(harness.database) == before
    finally:
        await harness.composition.stop()


async def _stop_test_reconciliation_worker(
    composition: P3AuthenticatedComposition,
) -> None:
    """Leave the route accepting while deterministic tests invoke Core directly."""

    worker = composition._worker
    assert worker is not None
    composition._closed = True
    composition._wake.set()
    await worker
    composition._worker = None
    composition._closed = False


@dataclass
class _Harness:
    composition: P3AuthenticatedComposition
    database: Path
    executor: object
    authority: _AuthorityResolver
    closer: _CloseRecorder
    telemetry: _Telemetry
    confirmations: SqliteP3ConfirmationLedger
    models: _ModelResolver


def _principal(
    *,
    expires_at: str = EXPIRY,
    allowed_project_ids: frozenset[str] = frozenset({"project-1", "project-2"}),
    allowed_operations: frozenset[str] = P3_OPERATIONS,
) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        principal_id="user-1",
        allowed_project_ids=allowed_project_ids,
        allowed_operations=allowed_operations,
        expires_at=expires_at,
    )


_DEFAULT_CONFIRMATION_VERIFIER = object()


def _harness(
    tmp_path: Path,
    *,
    contexts=None,
    expires_at: str = EXPIRY,
    allowed_project_ids: frozenset[str] = frozenset({"project-1", "project-2"}),
    allowed_operations: frozenset[str] = P3_OPERATIONS,
    commit_ledger: TurnCommitLedger | None = None,
    executor_profiles: tuple[ExecutorCapabilityProfile, ...] | None = None,
    executor_override: object | None = None,
    confirmation_verifier: object = _DEFAULT_CONFIRMATION_VERIFIER,
    clock=None,
) -> _Harness:
    database = tmp_path / "formal-tasks.sqlite3"
    executor = executor_override or _Executor()
    authority = _AuthorityResolver(
        contexts
        or {
            "session-1": _context(tmp_path),
            "session-2": _context(
                tmp_path, project_id="project-2", session_id="session-2"
            ),
        }
    )
    closer = _CloseRecorder()
    telemetry = _Telemetry()
    confirmations = SqliteP3ConfirmationLedger(database)
    models = _ModelResolver()
    composition = P3AuthenticatedComposition(
        authenticator=StaticBearerAuthenticator(
            token=TOKEN,
            principal=_principal(
                expires_at=expires_at,
                allowed_project_ids=allowed_project_ids,
                allowed_operations=allowed_operations,
            ),
        ),
        authority_resolver=authority,
        core=PersistentTaskCore(SqliteTaskStore(database), executor),
        confirmation_verifier=(
            confirmations
            if confirmation_verifier is _DEFAULT_CONFIRMATION_VERIFIER
            else confirmation_verifier
        ),
        model_resolver=models,
        binding_resolver=closer,
        telemetry=telemetry,
        policy=FormalTaskPolicyAdapter(commit_ledger),
        reconcile_interval=3600,
        clock=clock or (lambda: NOW),
        executor_profiles=executor_profiles,
    )
    return _Harness(
        composition,
        database,
        executor,
        authority,
        closer,
        telemetry,
        confirmations,
        models,
    )


def _production_registry_text_params(
    *,
    stem: str,
    text: str,
    continuation_id: str | None = None,
) -> dict[str, object]:
    params: dict[str, object] = {
        "auth_token": TOKEN,
        "session_id": "session-1",
        "correlation_id": f"production-correlation-{stem}",
        "source": "text",
        "interaction_id": "production-intent-interaction",
        "turn_id": f"production-turn-{stem}",
        "commit_id": f"production-commit-{stem}",
        "committed_at": NOW,
        "text": text,
    }
    if continuation_id is not None:
        params["continuation_id"] = continuation_id
    return params


@pytest.mark.asyncio
async def test_accepting_p3_owner_projects_exact_auth_executor_and_backend_configuration(
    tmp_path: Path,
) -> None:
    profile = DirectProjectCodeExecutorAdapter.capability_profile()
    backend = BoundedInMemoryOtelBackend(capacity=7)

    query_root = tmp_path / "query-only"
    query_root.mkdir()
    query_only = _harness(
        query_root,
        executor_profiles=(profile,),
        confirmation_verifier=None,
    )
    await query_only.composition.start()
    await _stop_test_reconciliation_worker(query_only.composition)
    try:
        configuration = query_only.composition.validated_live_voice_configuration(
            provider=backend.validated_provider_configuration()
        )

        assert configuration.authentication is not None
        assert configuration.authentication.mode is AuthenticationMode.SCOPED_BEARER
        assert TOKEN not in repr(configuration)
        assert configuration.executor is None
        assert configuration.providers == (backend.validated_provider_configuration(),)
        assert set(configuration.capabilities) == {
            LiveVoiceCapability.AUTHENTICATED,
            LiveVoiceCapability.FORMAL_WEB,
            LiveVoiceCapability.TASK_QUERY,
            LiveVoiceCapability.TELEMETRY_EXPORT,
        }
        assert configuration.ordinary_production_default_off is True
    finally:
        await query_only.composition.stop()

    with pytest.raises(FormalTaskViolation) as stopped:
        query_only.composition.validated_live_voice_configuration(
            provider=backend.validated_provider_configuration()
        )
    assert stopped.value.reason == "P3_CONFIGURATION_OWNER_UNAVAILABLE"

    expired_root = tmp_path / "expired-auth"
    expired_root.mkdir()
    expired = _harness(
        expired_root,
        expires_at="2025-01-01T00:00:00Z",
        executor_profiles=(profile,),
        confirmation_verifier=None,
    )
    await expired.composition.start()
    await _stop_test_reconciliation_worker(expired.composition)
    try:
        with pytest.raises(FormalTaskViolation) as invalid_auth:
            expired.composition.validated_live_voice_configuration(
                provider=backend.validated_provider_configuration()
            )
        assert invalid_auth.value.reason == "FORMAL_TASK_AUTHORIZATION_EXPIRED"
        assert backend.health().state.value == "created"
        assert backend.health().accepted == 0
    finally:
        await expired.composition.stop()

    revoked_root = tmp_path / "incomplete-query-scope"
    revoked_root.mkdir()
    revoked = _harness(
        revoked_root,
        allowed_operations=frozenset({"task.status"}),
        executor_profiles=(profile,),
        confirmation_verifier=None,
    )
    await revoked.composition.start()
    await _stop_test_reconciliation_worker(revoked.composition)
    try:
        with pytest.raises(FormalTaskViolation) as incomplete_scope:
            revoked.composition.validated_live_voice_configuration(
                provider=backend.validated_provider_configuration()
            )
        assert incomplete_scope.value.reason == "P3_QUERY_CONFIGURATION_UNAVAILABLE"
        assert backend.health().state.value == "created"
        assert backend.health().accepted == 0
    finally:
        await revoked.composition.stop()

    poison_root = tmp_path / "poison-confirmation"
    poison_root.mkdir()
    poison = _harness(
        poison_root,
        executor_profiles=(profile,),
        confirmation_verifier=object(),
    )
    await poison.composition.start()
    await _stop_test_reconciliation_worker(poison.composition)
    try:
        with pytest.raises(FormalTaskViolation) as invalid_confirmation:
            poison.composition.validated_live_voice_configuration(
                provider=backend.validated_provider_configuration()
            )
        assert (
            invalid_confirmation.value.reason
            == "P3_CONFIRMATION_CONFIGURATION_UNAVAILABLE"
        )
        assert backend.health().state.value == "created"
        assert backend.health().accepted == 0
    finally:
        await poison.composition.stop()

    mutation_root = tmp_path / "trusted-mutation"
    mutation_root.mkdir()
    direct = object.__new__(DirectProjectCodeExecutorAdapter)
    direct._durability_store = None
    trusted = _harness(
        mutation_root,
        executor_profiles=(profile,),
        executor_override=direct,
    )
    await trusted.composition.start()
    await _stop_test_reconciliation_worker(trusted.composition)
    try:
        with pytest.raises(FormalTaskViolation) as unprepared_direct:
            trusted.composition.validated_live_voice_configuration(
                provider=backend.validated_provider_configuration()
            )
        assert unprepared_direct.value.reason == "P3_EXECUTOR_CONFIGURATION_UNAVAILABLE"
        assert backend.health().state.value == "created"
        assert backend.health().accepted == 0
    finally:
        await trusted.composition.stop()

    missing_root = tmp_path / "missing-direct"
    missing_root.mkdir()
    missing = _harness(missing_root, executor_profiles=(profile,))
    await missing.composition.start()
    await _stop_test_reconciliation_worker(missing.composition)
    try:
        with pytest.raises(FormalTaskViolation) as unavailable:
            missing.composition.validated_live_voice_configuration(
                provider=backend.validated_provider_configuration()
            )
        assert unavailable.value.reason == "P3_EXECUTOR_CONFIGURATION_UNAVAILABLE"
    finally:
        await missing.composition.stop()

    conflict_root = tmp_path / "conflicting-profile"
    conflict_root.mkdir()
    d2_profile = DirectProjectCodeExecutorAdapter.construction_capability_profiles(
        store_backed=True
    )[-1]
    conflict_direct = object.__new__(DirectProjectCodeExecutorAdapter)
    conflict_direct._durability_store = None
    conflict = _harness(
        conflict_root,
        executor_profiles=(d2_profile,),
        executor_override=conflict_direct,
    )
    await conflict.composition.start()
    await _stop_test_reconciliation_worker(conflict.composition)
    try:
        with pytest.raises(FormalTaskViolation) as mismatched:
            conflict.composition.validated_live_voice_configuration(
                provider=backend.validated_provider_configuration()
            )
        assert mismatched.value.reason == "P3_EXECUTOR_CONFIGURATION_UNAVAILABLE"
    finally:
        await conflict.composition.stop()


@pytest.mark.asyncio
async def test_registry_production_classifier_bridge_store_and_core_without_hints(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commits = TurnCommitLedger()
    harness = _harness(
        tmp_path,
        commit_ledger=commits,
        executor_profiles=(DirectProjectCodeExecutorAdapter.capability_profile(),),
        allowed_operations=P3_PRODUCT_AUTHORITY_OPERATIONS,
    )
    await harness.composition.start()
    await _stop_test_reconciliation_worker(harness.composition)
    owner = BoundedP3ConfirmationOwner(harness.database, enabled=True)
    forwarder = ProductP3ConfirmationForwarder(owner)

    async def push(_message: dict[str, object]) -> bool:
        return True

    registry = AgentServerProductCompositionRegistry(
        settings=ProductCompositionSettings(
            p2_enabled=False,
            p3_text_enabled=True,
            p3_mutation_enabled=True,
        ),
        p3_composition=harness.composition,
        agent_manager=object(),
        push_text_event=push,
        p3_confirmation_owner=owner,
        p3_confirmation_forwarder=forwarder,
        commit_ledger=commits,
    )
    created_pending = await registry.handle_p3_intent(
        params=_production_registry_text_params(
            stem="create",
            text="新建一个任务，基于合成依赖起草发布说明。",
        ),
        request_id="production-intent-create",
        session_id="session-1",
    )
    assert created_pending.ok is True, created_pending.payload
    pending_result = created_pending.payload["result"]
    assert isinstance(pending_result, dict)
    token = pending_result["confirmation_token"]
    assert isinstance(token, str)
    assert pending_result["operation"] == "task.create"
    retained_confirmation = registry._pending_production_task_intents[token]
    assert retained_confirmation.confirmation_id is not None
    assert retained_confirmation.confirmation_owner_context is not None
    production_binding = retained_confirmation.resolution.confirmation_binding
    assert production_binding is not None
    owner.validate_for_forwarding(
        retained_confirmation.confirmation_id,
        P3ConfirmationBinding(
            principal_id=production_binding.principal_id,
            scope=production_binding.scope,
            operation=production_binding.operation,
            command_id=production_binding.command_id,
            target_task_id=production_binding.target_task_id,
            intent_fingerprint=production_binding.fingerprint,
        ),
        retained_confirmation.confirmation_owner_context,
        now=NOW,
    )

    create_confirmation_params = _production_registry_text_params(
        stem="create-confirm",
        text=f"confirm task request {token}",
        continuation_id=token,
    )
    original_issue = owner.issue

    def unexpected_reissue(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("confirmation answer cannot issue a new authority fact")

    monkeypatch.setattr(owner, "issue", unexpected_reissue)
    created = await registry.handle_p3_intent(
        params=create_confirmation_params,
        request_id="production-intent-create-confirm",
        session_id="session-1",
    )
    monkeypatch.setattr(owner, "issue", original_issue)
    assert created.ok is True, created.payload
    created_result = created.payload["result"]
    assert isinstance(created_result, dict)
    assert created_result["status"] == "dispatched"
    task_id = created_result["task_id"]
    assert isinstance(task_id, str)
    assert harness.composition._core.store.get_task(task_id, _scope()) is not None
    after_create = harness.composition._core.store.counts()
    replayed_create = await registry.handle_p3_intent(
        params=create_confirmation_params,
        request_id="production-intent-create-confirm",
        session_id="session-1",
    )
    assert replayed_create.payload == created.payload
    assert harness.composition._core.store.counts() == after_create
    changed_replay = await registry.handle_p3_intent(
        params={**create_confirmation_params, "text": "confirm changed request"},
        request_id="production-intent-create-confirm",
        session_id="session-1",
    )
    assert changed_replay.ok is False
    assert changed_replay.payload["error"]["reason"] == ("PRODUCT_REQUEST_ID_CONFLICT")
    assert harness.composition._core.store.counts() == after_create

    recovered_create = await registry.handle_p3_intent_status(
        params={
            "auth_token": TOKEN,
            "session_id": "session-1",
            "correlation_id": "production-correlation-create-confirm",
            "intent_request_id": "production-intent-create-confirm",
        },
        request_id="production-intent-create-recovery",
        session_id="session-1",
    )
    assert recovered_create.ok is True, recovered_create.payload
    recovered_result = recovered_create.payload["result"]
    assert isinstance(recovered_result, dict)
    assert recovered_result["status"] == "settled"
    recovered_intent = recovered_result["intent"]
    assert isinstance(recovered_intent, dict)
    assert recovered_intent["formal_task_result"] == {
        "recovered": True,
        "task_id": task_id,
    }
    assert harness.composition._core.store.counts() == after_create

    reprioritize_pending = await registry.handle_p3_intent(
        params=_production_registry_text_params(
            stem="reprioritize",
            text="Set priority urgent for task named Synthetic release notes.",
        ),
        request_id="production-intent-reprioritize",
        session_id="session-1",
    )
    assert reprioritize_pending.ok is True, reprioritize_pending.payload
    reprioritize_pending_result = reprioritize_pending.payload["result"]
    assert isinstance(reprioritize_pending_result, dict)
    reprioritize_token = reprioritize_pending_result["confirmation_token"]
    assert isinstance(reprioritize_token, str)
    reprioritized = await registry.handle_p3_intent(
        params=_production_registry_text_params(
            stem="reprioritize-confirm",
            text=f"confirm task request {reprioritize_token}",
            continuation_id=reprioritize_token,
        ),
        request_id="production-intent-reprioritize-confirm",
        session_id="session-1",
    )
    assert reprioritized.ok is True, reprioritized.payload
    assert (
        harness.composition._core.store.admission_projection(
            task_id, _scope()
        ).priority.value
        == "urgent"
    )

    listed = await registry.handle_p3_intent(
        params=_production_registry_text_params(
            stem="list",
            text="列出当前任务",
        ),
        request_id="production-intent-list",
        session_id="session-1",
    )
    assert listed.ok is True, listed.payload
    listed_result = listed.payload["result"]
    assert isinstance(listed_result, dict)
    assert listed_result["operation"] == "task.list"
    formal_list = listed_result["formal_task_result"]
    assert isinstance(formal_list, dict)
    assert any(item["task_id"] == task_id for item in formal_list["tasks"])

    authenticator = harness.composition._authenticator

    class _RevokedAuthenticator:
        def authenticate(
            self, *_args: object, **_kwargs: object
        ) -> AuthenticatedPrincipal:
            raise FormalTaskViolation(
                "FORMAL_TASK_AUTHENTICATION_REQUIRED",
                "revoked production intent bearer",
                ErrorCode.UNAUTHENTICATED,
            )

    before_revoked_replay = harness.composition._core.store.counts()
    harness.composition._authenticator = _RevokedAuthenticator()
    revoked_replay = await registry.handle_p3_intent(
        params=_production_registry_text_params(
            stem="list",
            text="列出当前任务",
        ),
        request_id="production-intent-list",
        session_id="session-1",
    )
    assert revoked_replay.ok is False
    assert revoked_replay.payload["error"]["reason"] == (
        "FORMAL_TASK_AUTHENTICATION_REQUIRED"
    )
    assert harness.composition._core.store.counts() == before_revoked_replay
    harness.composition._authenticator = authenticator

    status = await registry.handle_p3_intent(
        params=_production_registry_text_params(
            stem="status",
            text=f"status {task_id}",
        ),
        request_id="production-intent-status",
        session_id="session-1",
    )
    assert status.ok is True, status.payload
    status_result = status.payload["result"]
    assert isinstance(status_result, dict)
    assert status_result["operation"] == "task.status"
    assert status_result["task_id"] == task_id

    structured_status = await registry.handle_p3_intent(
        params={
            "auth_token": TOKEN,
            "session_id": "session-1",
            "correlation_id": "production-correlation-structured-status",
            "source": "structured",
            "source_id": "accepted-structured-status",
            "structured_intent": {
                "operation": "task.status",
                "target": task_id,
                "arguments": {"query_kind": "status"},
            },
        },
        request_id="production-intent-structured-status",
        session_id="session-1",
    )
    assert structured_status.ok is True, structured_status.payload
    structured_result = structured_status.payload["result"]
    assert isinstance(structured_result, dict)
    assert structured_result["operation"] == "task.status"
    assert structured_result["task_id"] == task_id
    assert (
        structured_result["formal_task_result"] == (status_result["formal_task_result"])
    )

    before_unsupported = harness.composition._core.store.counts()
    unsupported_pause = await registry.handle_p3_intent(
        params=_production_registry_text_params(
            stem="pause",
            text=f"pause {task_id}",
        ),
        request_id="production-intent-pause",
        session_id="session-1",
    )
    assert unsupported_pause.ok is False
    assert unsupported_pause.payload["error"]["code"] == ErrorCode.UNSUPPORTED.value
    assert harness.composition._core.store.counts() == before_unsupported
    assert registry._pending_production_task_intents == {}

    cancel_pending = await registry.handle_p3_intent(
        params=_production_registry_text_params(
            stem="cancel",
            text=f"cancel {task_id}",
        ),
        request_id="production-intent-cancel",
        session_id="session-1",
    )
    assert cancel_pending.ok is True, cancel_pending.payload
    cancel_pending_result = cancel_pending.payload["result"]
    assert isinstance(cancel_pending_result, dict)
    cancel_token = cancel_pending_result["confirmation_token"]
    assert isinstance(cancel_token, str)
    cancelled = await registry.handle_p3_intent(
        params=_production_registry_text_params(
            stem="cancel-confirm",
            text=f"confirm task request {cancel_token}",
            continuation_id=cancel_token,
        ),
        request_id="production-intent-cancel-confirm",
        session_id="session-1",
    )
    assert cancelled.ok is True, cancelled.payload
    cancelled_result = cancelled.payload["result"]
    assert isinstance(cancelled_result, dict)
    assert cancelled_result["status"] == "dispatched"
    assert cancelled_result["task_id"] == task_id
    assert registry._pending_production_task_intents == {}

    await registry.stop()
    await harness.composition.stop()


@pytest.mark.asyncio
async def test_agentserver_structured_continuation_reaches_registry_and_sqlite_exactly_once(
    tmp_path: Path,
) -> None:
    future_expiry = "2100-01-01T00:00:00Z"
    harness = _harness(
        tmp_path,
        expires_at=future_expiry,
        contexts={
            "session-1": _context(tmp_path, expires_at=future_expiry),
            "session-2": _context(
                tmp_path,
                project_id="project-2",
                session_id="session-2",
                expires_at=future_expiry,
            ),
        },
        executor_profiles=(DirectProjectCodeExecutorAdapter.capability_profile(),),
        allowed_operations=P3_PRODUCT_AUTHORITY_OPERATIONS,
    )
    await harness.composition.start()
    await _stop_test_reconciliation_worker(harness.composition)
    owner = BoundedP3ConfirmationOwner(harness.database, enabled=True)

    async def push(_message: dict[str, object]) -> bool:
        return True

    registry = AgentServerProductCompositionRegistry(
        settings=ProductCompositionSettings(
            p2_enabled=False,
            p3_text_enabled=True,
            p3_mutation_enabled=True,
        ),
        p3_composition=harness.composition,
        agent_manager=object(),
        push_text_event=push,
        p3_confirmation_owner=owner,
        p3_confirmation_forwarder=ProductP3ConfirmationForwarder(owner),
    )
    server = object.__new__(AgentWebSocketServer)
    server._live_voice_product_composition = registry
    server._live_voice_product_observability = None

    class Socket:
        def __init__(self) -> None:
            self.sent: list[str] = []

        async def send(self, payload: str) -> None:
            self.sent.append(payload)

    async def through_agentserver(
        request_id: str,
        params: dict[str, object],
        *,
        session_id: str = "session-1",
    ) -> dict[str, object]:
        socket = Socket()
        await server._handle_live_voice_product_request(
            socket,
            AgentRequest(
                request_id=request_id,
                channel_id="web",
                session_id=session_id,
                req_method=ReqMethod.LIVE_VOICE_COMPOSITION_P3_INTENT,
                params=params,
            ),
            asyncio.Lock(),
        )
        wire = json.loads(socket.sent[0])
        assert wire["status"] == "succeeded", wire
        payload = wire["body"]["result"]
        assert isinstance(payload, dict)
        return payload

    try:
        created = await harness.composition.handle(
            operation="task.create",
            params=_issued_create_params(harness, "command-structured-seed"),
            request_id="request-structured-seed",
            session_id="session-1",
        )
        assert created.ok is True, created.payload
        task_id = str(created.payload["result"]["task_id"])
        assert await harness.composition._core.drain_outbox_once(observed_at=NOW)

        structured = {
            "auth_token": TOKEN,
            "session_id": "session-1",
            "correlation_id": "correlation-structured-cancel",
            "source": "structured",
            "source_id": "command-structured-cancel",
            "source_confidence": 1,
            "committed": True,
            "operation_hint": "task.cancel",
            "task_id_hint": task_id,
            "structured_intent": {
                "operation": "task.cancel",
                "target": task_id,
                "arguments": {},
            },
        }
        pending_payload = await through_agentserver(
            "request-structured-cancel-pending", structured
        )
        pending = pending_payload["result"]
        assert isinstance(pending, dict)
        assert pending["status"] == "clarification"
        token = str(pending["confirmation_token"])
        confirmation = {**structured, "continuation_id": token}

        before_confirm = harness.composition._core.store.counts()
        confirmed_payload = await through_agentserver(
            "request-structured-cancel-confirm", confirmation
        )
        confirmed = confirmed_payload["result"]
        assert isinstance(confirmed, dict)
        assert confirmed["status"] == "dispatched"
        assert confirmed["operation"] == "task.cancel"
        assert confirmed["task_id"] == task_id
        after_confirm = harness.composition._core.store.counts()
        assert after_confirm != before_confirm

        replayed_payload = await through_agentserver(
            "request-structured-cancel-confirm", confirmation
        )
        assert replayed_payload == confirmed_payload
        assert harness.composition._core.store.counts() == after_confirm

        changed_duplicate = await registry.handle_p3_intent(
            params={
                **confirmation,
                "source_id": "command-structured-cancel-changed",
            },
            request_id="request-structured-cancel-confirm",
            session_id="session-1",
        )
        assert changed_duplicate.ok is False
        assert changed_duplicate.payload["error"]["reason"] == (
            "PRODUCT_REQUEST_ID_CONFLICT"
        )
        assert harness.composition._core.store.counts() == after_confirm

        second = await harness.composition.handle(
            operation="task.create",
            params=_issued_create_params(harness, "command-structured-negative"),
            request_id="request-structured-negative-create",
            session_id="session-1",
        )
        assert second.ok is True, second.payload
        second_task_id = str(second.payload["result"]["task_id"])
        # The previously confirmed cancellation is ahead of this create in the
        # durable outbox. Drain both exact effects before testing an adjustment
        # that is valid only for the second Task's running Attempt.
        assert await harness.composition._core.drain_outbox_once(observed_at=NOW)
        assert await harness.composition._core.drain_outbox_once(observed_at=NOW)
        assert (
            harness.composition._core.store.get_task(
                second_task_id, _scope()
            ).state.value
            == "running"
        )
        adjustment = {
            "auth_token": TOKEN,
            "session_id": "session-1",
            "correlation_id": "correlation-structured-adjust",
            "source": "structured",
            "source_id": "command-structured-adjust",
            "source_confidence": 1,
            "committed": True,
            "operation_hint": "task.adjust",
            "task_id_hint": second_task_id,
            "structured_intent": {
                "operation": "task.adjust",
                "target": second_task_id,
                "arguments": {"adjustment": "retain exact proposal"},
            },
        }
        adjustment_pending = await registry.handle_p3_intent(
            params=adjustment,
            request_id="request-structured-adjust-pending",
            session_id="session-1",
        )
        assert adjustment_pending.ok is True, adjustment_pending.payload
        adjustment_token = str(
            adjustment_pending.payload["result"]["confirmation_token"]
        )
        before_rejections = harness.composition._core.store.counts()
        changed_continuation = await registry.handle_p3_intent(
            params={
                **adjustment,
                "continuation_id": adjustment_token,
                "source_id": "command-structured-adjust-changed",
                "operation_hint": "task.cancel",
                "task_id_hint": task_id,
                "structured_intent": {
                    "operation": "task.cancel",
                    "target": task_id,
                    "arguments": {},
                },
            },
            request_id="request-structured-adjust-changed",
            session_id="session-1",
        )
        cross_scope = await registry.handle_p3_intent(
            params={
                **adjustment,
                "session_id": "session-2",
                "continuation_id": adjustment_token,
            },
            request_id="request-structured-adjust-cross-scope",
            session_id="session-2",
        )
        assert changed_continuation.ok is False
        assert cross_scope.ok is False
        assert harness.composition._core.store.counts() == before_rejections
        assert harness.executor.adjustments == []
    finally:
        await registry.stop()
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_product_status_projects_only_exact_existing_authority_operations(
    tmp_path: Path,
) -> None:
    harness = _harness(
        tmp_path,
        executor_profiles=(DirectProjectCodeExecutorAdapter.capability_profile(),),
        allowed_operations=P3_PRODUCT_AUTHORITY_OPERATIONS,
    )
    await harness.composition.start()
    await _stop_test_reconciliation_worker(harness.composition)
    try:
        created = await harness.composition.handle(
            operation="task.create",
            params=_issued_create_params(harness, "command-status-projection"),
            request_id="request-status-projection-create",
            session_id="session-1",
        )
        assert created.ok is True, created.payload
        task_id = str(created.payload["result"]["task_id"])
        status = await harness.composition.handle(
            operation="task.status",
            params={**_base(), "task_id": task_id},
            request_id="request-status-projection",
            session_id="session-1",
        )
        assert status.ok is True, status.payload
        raw = status.payload["result"]
        assert isinstance(raw, dict)
        retry_admission = raw["retry_admission"]
        assert isinstance(retry_admission, dict)
        authority = harness.composition.prepare_production_intent_authority(
            bearer_token=TOKEN,
            operation="task.status",
            session_id="session-1",
        )
        fact = authority.reader.task_status(authority.scope, task_id)
        assert fact is not None

        before_counts = harness.composition._core.store.counts()
        before_effects = (
            list(harness.executor.dispatches),
            list(harness.executor.cancels),
            list(harness.executor.adjustments),
        )
        expected_operations = set(fact.supported_operations)
        if retry_admission["eligible"] is True:
            expected_operations.add("task.retry")
        projected = _project_production_status_authority(
            raw,
            production_authority=authority,
            authority_fact=fact,
            retry_admission=retry_admission,
            authorized_operations=frozenset(expected_operations),
        )
        assert projected["supported_operations"] == sorted(expected_operations)

        def changed(path: tuple[str, ...], value: object) -> dict[str, object]:
            candidate = json.loads(json.dumps(raw))
            cursor: dict[str, object] = candidate
            for key in path[:-1]:
                child = cursor[key]
                assert isinstance(child, dict)
                cursor = child
            cursor[path[-1]] = value
            return candidate

        mismatches = (
            changed(("task", "scope", "subject_id"), "subject-foreign"),
            changed(("task", "scope", "project_id"), "project-foreign"),
            changed(("task", "task_id"), "task-foreign"),
            changed(("attempt", "attempt_id"), "attempt-stale"),
            changed(("task", "event_head"), int(raw["task"]["event_head"]) + 1),
            changed(
                ("task", "revision", "number"),
                int(raw["task"]["revision"]["number"]) + 1,
            ),
            {**raw, "supported_operations": ["task.cancel"]},
        )
        for mismatch in mismatches:
            with pytest.raises(FormalTaskViolation) as rejected:
                _project_production_status_authority(
                    mismatch,
                    production_authority=authority,
                    authority_fact=fact,
                    retry_admission=retry_admission,
                    authorized_operations=frozenset(expected_operations),
                )
            assert rejected.value.reason == (
                "PRODUCTION_TASK_AUTHORITY_PROJECTION_MISMATCH"
            )

        stale_admission = json.loads(json.dumps(raw))
        assert isinstance(stale_admission["admission"], dict)
        stale_admission["admission"]["attempt_count"] += 1
        stale_admission["admission"]["reason"] = "EXECUTOR_PROJECT_BUSY"
        stale_admission["task"]["admission"] = dict(
            stale_admission["admission"]
        )
        with pytest.raises(FormalTaskViolation) as changed_generation:
            _project_production_status_authority(
                stale_admission,
                production_authority=authority,
                authority_fact=fact,
                retry_admission=retry_admission,
                authorized_operations=frozenset(expected_operations),
            )
        assert changed_generation.value.reason == (
            "PRODUCTION_TASK_AUTHORITY_CHANGED"
        )
        assert changed_generation.value.code is ErrorCode.STALE
        assert harness.composition._core.store.counts() == before_counts
        assert (
            harness.executor.dispatches,
            harness.executor.cancels,
            harness.executor.adjustments,
        ) == before_effects
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_product_status_projects_fresh_busy_admission_as_reprioritize_only(
    tmp_path: Path,
) -> None:
    harness = _harness(
        tmp_path,
        executor_profiles=(DirectProjectCodeExecutorAdapter.capability_profile(),),
        allowed_operations=P3_PRODUCT_AUTHORITY_OPERATIONS,
    )
    await harness.composition.start()
    await _stop_test_reconciliation_worker(harness.composition)
    try:
        created = await harness.composition.handle(
            operation="task.create",
            params=_issued_create_params(harness, "command-status-busy"),
            request_id="request-status-busy-create",
            session_id="session-1",
        )
        assert created.ok is True, created.payload
        task_id = str(created.payload["result"]["task_id"])
        claimed = harness.composition._core.store.claim_outbox(
            "worker-status-busy",
            observed_at=NOW,
        )
        assert claimed is not None and claimed.task_id == task_id
        assert (
            harness.composition._core.store.defer_admission(
                claimed,
                reason="EXECUTOR_PROJECT_BUSY",
                policy=AdmissionPolicy(),
                observed_at=NOW,
            )
            is AdmissionDisposition.DEFERRED
        )
        reconciliation = await harness.composition._core.reconcile_status()
        assert reconciliation["known"] == 1
        assert reconciliation["unavailable"] == 0
        queued_task = harness.composition._core.store.get_task(
            task_id, harness.authority.contexts["session-1"].scope
        )
        assert queued_task.reconciliation_state is None

        status = await harness.composition.handle(
            operation="task.status",
            params={**_base(), "task_id": task_id},
            request_id="request-status-busy",
            session_id="session-1",
        )
        assert status.ok is True, status.payload
        raw = status.payload["result"]
        authority = harness.composition.prepare_production_intent_authority(
            bearer_token=TOKEN,
            operation="task.status",
            session_id="session-1",
        )
        fact = authority.reader.task_status(authority.scope, task_id)
        assert fact is not None
        before = harness.composition._core.store.counts()

        projected = _project_production_status_authority(
            raw,
            production_authority=authority,
            authority_fact=fact,
            retry_admission=raw["retry_admission"],
            authorized_operations=fact.supported_operations,
        )

        assert raw["admission"]["reason"] == "EXECUTOR_PROJECT_BUSY"
        assert raw["admission"]["queued"] is True
        assert projected["supported_operations"] == [
            "task.cancel",
            "task.events",
            "task.get",
            "task.list",
            "task.reprioritize",
            "task.result",
            "task.status",
        ]
        assert harness.composition._core.store.counts() == before
        assert harness.executor.dispatches == []
        assert harness.executor.cancels == []
        assert harness.executor.adjustments == []
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_registry_status_controls_intersect_principal_and_existing_retry_admission(
    tmp_path: Path,
) -> None:
    future_expiry = "2100-01-01T00:00:00Z"
    harness = _harness(
        tmp_path,
        expires_at=future_expiry,
        contexts={"session-1": _context(tmp_path, expires_at=future_expiry)},
        executor_profiles=(DirectProjectCodeExecutorAdapter.capability_profile(),),
        allowed_operations=P3_PRODUCT_AUTHORITY_OPERATIONS,
    )
    harness.executor.dispatch_outcome = TerminalOutcome.CANCELLED
    await harness.composition.start()
    await _stop_test_reconciliation_worker(harness.composition)
    owner = BoundedP3ConfirmationOwner(harness.database, enabled=True)

    async def push(_message: dict[str, object]) -> bool:
        return True

    registry = AgentServerProductCompositionRegistry(
        settings=ProductCompositionSettings(
            p2_enabled=False,
            p3_text_enabled=True,
            p3_mutation_enabled=True,
        ),
        p3_composition=harness.composition,
        agent_manager=object(),
        push_text_event=push,
        p3_confirmation_owner=owner,
        p3_confirmation_forwarder=ProductP3ConfirmationForwarder(owner),
    )
    try:
        created = await harness.composition.handle(
            operation="task.create",
            params=_issued_create_params(harness, "command-status-principal"),
            request_id="request-status-principal-create",
            session_id="session-1",
        )
        assert created.ok is True, created.payload
        task_id = str(created.payload["result"]["task_id"])
        assert await harness.composition._core.drain_outbox_once(observed_at=NOW)

        eligible = await registry.handle_p3_query(
            operation="task.status",
            params={**_base(), "task_id": task_id},
            request_id="request-status-principal-eligible",
            session_id="session-1",
        )
        assert eligible.ok is True, eligible.payload
        eligible_result = eligible.payload["result"]
        assert isinstance(eligible_result, dict)
        assert eligible_result["retry_admission"]["eligible"] is True, eligible_result
        assert "task.retry" in eligible_result["supported_operations"]

        before_counts = harness.composition._core.store.counts()
        before_effects = (
            list(harness.executor.dispatches),
            list(harness.executor.cancels),
            list(harness.executor.adjustments),
        )
        harness.composition._authenticator = StaticBearerAuthenticator(
            token=TOKEN,
            principal=_principal(
                expires_at=future_expiry,
                allowed_operations=frozenset({"task.list", "task.status"}),
            ),
        )
        listed = await registry.handle_p3_query(
            operation="task.list",
            params=_base(),
            request_id="request-status-principal-list-only",
            session_id="session-1",
        )
        status_only = await registry.handle_p3_query(
            operation="task.status",
            params={**_base(), "task_id": task_id},
            request_id="request-status-principal-status-only",
            session_id="session-1",
        )
        assert listed.ok is True, listed.payload
        assert listed.payload["result"]["supported_operations"] == []
        assert status_only.ok is True, status_only.payload
        status_result = status_only.payload["result"]
        assert isinstance(status_result, dict)
        assert status_result["supported_operations"] == []
        assert status_result["retry_admission"] == {
            "eligible": False,
            "reason": "FORMAL_TASK_AUTHORIZATION_DENIED",
            "task_id": task_id,
            "attempt_id": None,
            "attempt_number": None,
        }
        assert harness.composition._core.store.counts() == before_counts
        assert (
            harness.executor.dispatches,
            harness.executor.cancels,
            harness.executor.adjustments,
        ) == before_effects
    finally:
        await registry.stop()
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_registry_inflight_production_replay_reauthorizes_resolved_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commits = TurnCommitLedger()
    harness = _harness(
        tmp_path,
        commit_ledger=commits,
        executor_profiles=(DirectProjectCodeExecutorAdapter.capability_profile(),),
    )
    await harness.composition.start()
    await _stop_test_reconciliation_worker(harness.composition)
    owner = BoundedP3ConfirmationOwner(harness.database, enabled=True)
    forwarder = ProductP3ConfirmationForwarder(owner)

    async def push(_message: dict[str, object]) -> bool:
        return True

    registry = AgentServerProductCompositionRegistry(
        settings=ProductCompositionSettings(
            p2_enabled=False,
            p3_text_enabled=True,
            p3_mutation_enabled=True,
        ),
        p3_composition=harness.composition,
        agent_manager=object(),
        push_text_event=push,
        p3_confirmation_owner=owner,
        p3_confirmation_forwarder=forwarder,
        commit_ledger=commits,
    )
    pending = await registry.handle_p3_intent(
        params=_production_registry_text_params(
            stem="inflight-create",
            text="新建一个任务，基于合成依赖起草发布说明。",
        ),
        request_id="production-inflight-create",
        session_id="session-1",
    )
    assert pending.ok is True, pending.payload
    pending_result = pending.payload["result"]
    assert isinstance(pending_result, dict)
    token = pending_result["confirmation_token"]
    assert isinstance(token, str)

    base_authenticator = harness.composition._authenticator
    observed_operations: list[str] = []

    class _MutationRevokedAfterOriginalInvocation:
        create_authentications = 0

        def authenticate(
            self, bearer_token: object, *, operation: str, now: str
        ) -> AuthenticatedPrincipal:
            observed_operations.append(operation)
            if operation == "task.create":
                self.create_authentications += 1
                if self.create_authentications > 4:
                    raise FormalTaskViolation(
                        "PRODUCTION_MUTATION_AUTHORITY_REVOKED",
                        "retained mutation authority was revoked",
                        ErrorCode.PERMISSION_DENIED,
                    )
            return base_authenticator.authenticate(
                bearer_token,
                operation=operation,
                now=now,
            )

    harness.composition._authenticator = _MutationRevokedAfterOriginalInvocation()
    original_prepare = harness.composition.prepare_production_intent_authority
    preparation_entered = threading.Event()
    release_preparation = threading.Event()
    prepare_calls = 0

    def blocked_prepare(**kwargs: object) -> PreparedProductionIntentAuthority:
        nonlocal prepare_calls
        prepared = original_prepare(**kwargs)
        if kwargs.get("operation") == "task.create":
            prepare_calls += 1
        if prepare_calls == 2:
            preparation_entered.set()
            if not release_preparation.wait(5):
                raise AssertionError(
                    "timed out waiting to release production preparation"
                )
        return prepared

    monkeypatch.setattr(
        harness.composition,
        "prepare_production_intent_authority",
        blocked_prepare,
    )
    confirmation_params = _production_registry_text_params(
        stem="inflight-create-confirm",
        text=f"confirm task request {token}",
        continuation_id=token,
    )
    original = asyncio.create_task(
        registry.handle_p3_intent(
            params=confirmation_params,
            request_id="production-inflight-create-confirm",
            session_id="session-1",
        )
    )
    assert await asyncio.to_thread(preparation_entered.wait, 5)
    replay = asyncio.create_task(
        registry.handle_p3_intent(
            params=confirmation_params,
            request_id="production-inflight-create-confirm",
            session_id="session-1",
        )
    )
    release_preparation.set()
    original_result, replay_result = await asyncio.gather(original, replay)

    assert original_result.ok is True, original_result.payload
    assert replay_result.ok is False
    assert replay_result.payload["error"]["reason"] == (
        "PRODUCTION_MUTATION_AUTHORITY_REVOKED"
    )
    assert observed_operations.count("task.create") == 5
    assert "task.list" not in observed_operations
    assert harness.composition._core.store.counts()["tasks"] == 1

    await registry.stop()
    await harness.composition.stop()


@pytest.mark.asyncio
async def test_registry_preflights_production_authority_before_replay_capacity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commits = TurnCommitLedger()
    harness = _harness(
        tmp_path,
        commit_ledger=commits,
        executor_profiles=(DirectProjectCodeExecutorAdapter.capability_profile(),),
    )
    await harness.composition.start()
    await _stop_test_reconciliation_worker(harness.composition)
    owner = BoundedP3ConfirmationOwner(harness.database, enabled=True)

    async def push(_message: dict[str, object]) -> bool:
        return True

    registry = AgentServerProductCompositionRegistry(
        settings=ProductCompositionSettings(
            p2_enabled=False,
            p3_text_enabled=True,
            p3_mutation_enabled=True,
        ),
        p3_composition=harness.composition,
        agent_manager=object(),
        push_text_event=push,
        p3_confirmation_owner=owner,
        p3_confirmation_forwarder=ProductP3ConfirmationForwarder(owner),
        commit_ledger=commits,
    )
    retained = await registry.handle_p3_intent(
        params=_production_registry_text_params(
            stem="preflight-retained",
            text="列出当前任务",
        ),
        request_id="production-preflight-retained",
        session_id="session-1",
    )
    assert retained.ok is True, retained.payload
    monkeypatch.setattr(registry, "_PRODUCT_OPERATION_CAPACITY", 1)
    retained_entry = registry._p3_intent_operations["production-preflight-retained"]
    authenticator = harness.composition._authenticator

    class _RevokedAuthenticator:
        def authenticate(
            self, *_args: object, **_kwargs: object
        ) -> AuthenticatedPrincipal:
            raise FormalTaskViolation(
                "FORMAL_TASK_AUTHENTICATION_REQUIRED",
                "revoked before replay capacity",
                ErrorCode.UNAUTHENTICATED,
            )

    harness.composition._authenticator = _RevokedAuthenticator()
    rejected = await registry.handle_p3_intent(
        params=_production_registry_text_params(
            stem="preflight-revoked",
            text="列出当前任务",
        ),
        request_id="production-preflight-revoked",
        session_id="session-1",
    )
    assert rejected.ok is False
    assert rejected.payload["error"]["reason"] == (
        "FORMAL_TASK_AUTHENTICATION_REQUIRED"
    )
    assert registry._p3_intent_operations == {
        "production-preflight-retained": retained_entry
    }

    harness.composition._authenticator = authenticator
    uncommitted = await registry.handle_p3_intent(
        params={
            **_production_registry_text_params(
                stem="preflight-uncommitted",
                text="列出当前任务",
            ),
            "committed": False,
        },
        request_id="production-preflight-uncommitted",
        session_id="session-1",
    )
    assert uncommitted.ok is False
    assert uncommitted.payload["error"]["reason"] == "INPUT_NOT_COMMITTED"
    assert registry._p3_intent_operations == {
        "production-preflight-retained": retained_entry
    }
    assert registry._pending_production_task_intents == {}
    assert registry._critical_input_guarded_commits == set()

    voice_commit = TurnCommit.from_dict(
        {
            "contract_version": CONTRACT_VERSION,
            "commit_id": "production-preflight-voice-commit",
            "turn_id": "production-preflight-voice-turn",
            "interaction_id": "production-preflight-voice-interaction",
            "text": "新建一个任务，基于合成依赖起草发布说明。",
            "hypothesis_provenance": {
                "provider": "product.web.voice",
                "kind": "committed_text",
            },
            "scope": _scope().to_dict(),
            "context_refs": [],
            "committed_at": NOW,
        }
    )
    assert commits.accept(voice_commit) is True
    voice_route = ("session-1", voice_commit.interaction_id)
    registry._accepted_turn_commits_by_commit[voice_commit.commit_id] = voice_commit
    registry._accepted_voice_commit_routes[voice_commit.commit_id] = voice_route
    registry._p2_routes[voice_route] = object()  # type: ignore[assignment]
    registry._critical_input_guarded_commits.add(voice_commit.commit_id)
    before_voice_maps = (
        dict(registry._accepted_turn_commits_by_commit),
        dict(registry._accepted_voice_commit_routes),
        dict(registry._p2_routes),
        set(registry._critical_input_guarded_commits),
    )
    uncommitted_voice = await registry.handle_p3_intent(
        params={
            "auth_token": TOKEN,
            "session_id": "session-1",
            "correlation_id": "production-preflight-voice-correlation",
            "source": "voice",
            "interaction_id": voice_commit.interaction_id,
            "turn_id": voice_commit.turn_id,
            "commit_id": voice_commit.commit_id,
            "source_confidence": 1.0,
            "committed": False,
        },
        request_id="production-preflight-uncommitted-voice",
        session_id="session-1",
    )
    assert uncommitted_voice.ok is False
    assert uncommitted_voice.payload["error"]["reason"] == "INPUT_NOT_COMMITTED"
    assert (
        dict(registry._accepted_turn_commits_by_commit),
        dict(registry._accepted_voice_commit_routes),
        dict(registry._p2_routes),
        set(registry._critical_input_guarded_commits),
    ) == before_voice_maps
    assert registry._p3_intent_operations == {
        "production-preflight-retained": retained_entry
    }
    registry._p2_routes.pop(voice_route)
    registry._accepted_turn_commits_by_commit.pop(voice_commit.commit_id)
    registry._accepted_voice_commit_routes.pop(voice_commit.commit_id)
    registry._critical_input_guarded_commits.remove(voice_commit.commit_id)

    feature_off = AgentServerProductCompositionRegistry(
        settings=ProductCompositionSettings(
            p2_enabled=False,
            p3_text_enabled=False,
            p3_mutation_enabled=True,
        ),
        p3_composition=harness.composition,
        agent_manager=object(),
        push_text_event=push,
        p3_confirmation_owner=owner,
        p3_confirmation_forwarder=ProductP3ConfirmationForwarder(owner),
        commit_ledger=commits,
    )
    disabled = await feature_off.handle_p3_intent(
        params=_production_registry_text_params(
            stem="preflight-disabled",
            text="列出当前任务",
        ),
        request_id="production-preflight-disabled",
        session_id="session-1",
    )
    assert disabled.ok is False
    assert disabled.payload["error"]["reason"] == "PRODUCT_P3_TEXT_DISABLED"
    assert feature_off._p3_intent_operations == {}

    await feature_off.stop()
    await registry.stop()
    await harness.composition.stop()


@pytest.mark.asyncio
async def test_registry_production_clarification_is_owner_bound_and_single_use(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commits = TurnCommitLedger()
    harness = _harness(
        tmp_path,
        commit_ledger=commits,
        executor_profiles=(DirectProjectCodeExecutorAdapter.capability_profile(),),
    )
    await harness.composition.start()
    await _stop_test_reconciliation_worker(harness.composition)
    owner = BoundedP3ConfirmationOwner(harness.database, enabled=True)
    forwarder = ProductP3ConfirmationForwarder(owner)

    async def push(_message: dict[str, object]) -> bool:
        return True

    registry = AgentServerProductCompositionRegistry(
        settings=ProductCompositionSettings(
            p2_enabled=False,
            p3_text_enabled=True,
            p3_mutation_enabled=True,
        ),
        p3_composition=harness.composition,
        agent_manager=object(),
        push_text_event=push,
        p3_confirmation_owner=owner,
        p3_confirmation_forwarder=forwarder,
        commit_ledger=commits,
    )

    async def create(stem: str) -> str:
        pending = await registry.handle_p3_intent(
            params=_production_registry_text_params(
                stem=f"{stem}-create",
                text="新建一个任务，基于合成依赖起草发布说明。",
            ),
            request_id=f"{stem}-create",
            session_id="session-1",
        )
        assert pending.ok is True, pending.payload
        result = pending.payload["result"]
        assert isinstance(result, dict)
        token = result["confirmation_token"]
        assert isinstance(token, str)
        confirmed = await registry.handle_p3_intent(
            params=_production_registry_text_params(
                stem=f"{stem}-confirm",
                text=f"confirm task request {token}",
                continuation_id=token,
            ),
            request_id=f"{stem}-confirm",
            session_id="session-1",
        )
        assert confirmed.ok is True, confirmed.payload
        confirmed_result = confirmed.payload["result"]
        assert isinstance(confirmed_result, dict)
        task_id = confirmed_result["task_id"]
        assert isinstance(task_id, str)
        return task_id

    first_task = await create("duplicate-a")
    second_task = await create("duplicate-b")
    assert first_task != second_task
    before = harness.composition._core.store.counts()

    failed_issue_pending = await registry.handle_p3_intent(
        params=_production_registry_text_params(
            stem="ambiguous-cancel-failed-issue",
            text="Cancel the task named Synthetic release notes.",
        ),
        request_id="duplicate-cancel-failed-issue",
        session_id="session-1",
    )
    assert failed_issue_pending.ok is True, failed_issue_pending.payload
    failed_issue_result = failed_issue_pending.payload["result"]
    assert isinstance(failed_issue_result, dict)
    assert failed_issue_result["status"] == "clarification"
    failed_issue_token = failed_issue_result["confirmation_token"]
    assert isinstance(failed_issue_token, str)
    original_issue = owner.issue
    issue_calls = 0

    def fail_before_issue(*_args: object, **_kwargs: object) -> None:
        nonlocal issue_calls
        issue_calls += 1
        raise FormalTaskViolation(
            "P3_CONFIRMATION_UNAVAILABLE",
            "injected confirmation issue failure",
            ErrorCode.UNAVAILABLE,
        )

    monkeypatch.setattr(owner, "issue", fail_before_issue)
    failed_issue = await registry.handle_p3_intent(
        params=_production_registry_text_params(
            stem="ambiguous-cancel-failed-answer",
            text=f"cancel {second_task}",
            continuation_id=failed_issue_token,
        ),
        request_id="duplicate-cancel-failed-answer",
        session_id="session-1",
    )
    monkeypatch.setattr(owner, "issue", original_issue)
    assert failed_issue.ok is False
    assert failed_issue.payload["error"]["reason"] == "P3_CONFIRMATION_UNAVAILABLE"
    assert issue_calls == 1
    assert failed_issue_token not in registry._pending_production_task_intents
    assert registry._pending_production_task_intents == {}
    assert harness.composition._core.store.counts() == before
    assert harness.executor.cancels == []

    failed_issue_retry = await registry.handle_p3_intent(
        params=_production_registry_text_params(
            stem="ambiguous-cancel-failed-retry",
            text=f"cancel {second_task}",
            continuation_id=failed_issue_token,
        ),
        request_id="duplicate-cancel-failed-retry",
        session_id="session-1",
    )
    assert failed_issue_retry.ok is False
    assert failed_issue_retry.payload["error"]["reason"] == (
        "TASK_INTENT_CONTINUATION_UNAVAILABLE"
    )
    assert harness.composition._core.store.counts() == before

    committed_issue_pending = await registry.handle_p3_intent(
        params=_production_registry_text_params(
            stem="ambiguous-cancel-committed-issue",
            text="Cancel the task named Synthetic release notes.",
        ),
        request_id="duplicate-cancel-committed-issue",
        session_id="session-1",
    )
    assert committed_issue_pending.ok is True, committed_issue_pending.payload
    committed_issue_result = committed_issue_pending.payload["result"]
    assert isinstance(committed_issue_result, dict)
    committed_clarification_token = committed_issue_result["confirmation_token"]
    assert isinstance(committed_clarification_token, str)

    def fail_after_issue(*args: object, **kwargs: object) -> None:
        original_issue(*args, **kwargs)
        raise RuntimeError("injected post-commit confirmation response loss")

    monkeypatch.setattr(owner, "issue", fail_after_issue)
    reconciled_issue = await registry.handle_p3_intent(
        params=_production_registry_text_params(
            stem="ambiguous-cancel-committed-answer",
            text=f"cancel {second_task}",
            continuation_id=committed_clarification_token,
        ),
        request_id="duplicate-cancel-committed-answer",
        session_id="session-1",
    )
    monkeypatch.setattr(owner, "issue", original_issue)
    assert reconciled_issue.ok is True, reconciled_issue.payload
    reconciled_result = reconciled_issue.payload["result"]
    assert isinstance(reconciled_result, dict)
    assert reconciled_result["status"] == "clarification"
    assert reconciled_result["reason"] == "TASK_CONFIRMATION_REQUIRED"
    reconciled_token = reconciled_result["confirmation_token"]
    assert isinstance(reconciled_token, str)
    assert committed_clarification_token not in (
        registry._pending_production_task_intents
    )
    assert reconciled_token in registry._pending_production_task_intents
    assert harness.composition._core.store.counts() == before

    retained_reconciled = registry._pending_production_task_intents[reconciled_token]
    retained_binding = retained_reconciled.resolution.confirmation_binding
    assert retained_binding is not None
    expected_p3_binding = P3ConfirmationBinding(
        principal_id=retained_binding.principal_id,
        scope=retained_binding.scope,
        operation=retained_binding.operation,
        command_id=retained_binding.command_id,
        target_task_id=retained_binding.target_task_id,
        intent_fingerprint=retained_binding.fingerprint,
    )
    original_validate = owner.validate_for_forwarding
    observed_confirmation_bindings: list[P3ConfirmationBinding] = []

    def capture_confirmation_binding(
        confirmation_id: str,
        binding: P3ConfirmationBinding,
        owner_context: P3ConfirmationOwnerContext,
        *,
        now: str,
    ):
        observed_confirmation_bindings.append(binding)
        return original_validate(
            confirmation_id,
            binding,
            owner_context,
            now=now,
        )

    monkeypatch.setattr(owner, "validate_for_forwarding", capture_confirmation_binding)

    cancelled = await registry.handle_p3_intent(
        params=_production_registry_text_params(
            stem="ambiguous-cancel-committed-confirm",
            text=f"confirm task request {reconciled_token}",
            continuation_id=reconciled_token,
        ),
        request_id="duplicate-cancel-committed-confirm",
        session_id="session-1",
    )
    monkeypatch.setattr(owner, "validate_for_forwarding", original_validate)
    assert observed_confirmation_bindings[-1] == expected_p3_binding
    assert cancelled.ok is True, cancelled.payload
    cancelled_result = cancelled.payload["result"]
    assert isinstance(cancelled_result, dict)
    assert cancelled_result["status"] == "dispatched"
    assert cancelled_result["task_id"] == second_task
    assert registry._pending_production_task_intents == {}
    before = harness.composition._core.store.counts()

    ambiguous = await registry.handle_p3_intent(
        params=_production_registry_text_params(
            stem="ambiguous-status",
            text="status “Synthetic release notes”",
        ),
        request_id="duplicate-status",
        session_id="session-1",
    )
    assert ambiguous.ok is True, ambiguous.payload
    ambiguous_result = ambiguous.payload["result"]
    assert isinstance(ambiguous_result, dict)
    assert ambiguous_result["status"] == "clarification"
    assert set(ambiguous_result["candidate_task_ids"]) == {
        first_task,
        second_task,
    }
    token = ambiguous_result["confirmation_token"]
    assert isinstance(token, str)

    wrong_hint = await registry.handle_p3_intent(
        params={
            **_production_registry_text_params(
                stem="ambiguous-wrong-hint",
                text=f"status {second_task}",
                continuation_id=token,
            ),
            "operation_hint": "task.status",
            "task_id_hint": first_task,
        },
        request_id="duplicate-status-wrong-hint",
        session_id="session-1",
    )
    assert wrong_hint.ok is False
    assert wrong_hint.payload["error"]["reason"] == "TASK_INTENT_HINT_MISMATCH"
    assert token in registry._pending_production_task_intents
    assert harness.composition._core.store.counts() == before

    selected = await registry.handle_p3_intent(
        params=_production_registry_text_params(
            stem="ambiguous-select",
            text=f"status {second_task}",
            continuation_id=token,
        ),
        request_id="duplicate-status-selected",
        session_id="session-1",
    )
    assert selected.ok is True, selected.payload
    selected_result = selected.payload["result"]
    assert isinstance(selected_result, dict)
    assert selected_result["status"] == "dispatched"
    assert selected_result["task_id"] == second_task
    assert harness.composition._core.store.counts() == before

    replay = await registry.handle_p3_intent(
        params=_production_registry_text_params(
            stem="ambiguous-replay",
            text=f"status {second_task}",
            continuation_id=token,
        ),
        request_id="duplicate-status-replay",
        session_id="session-1",
    )
    assert replay.ok is False
    assert replay.payload["error"]["reason"] == ("TASK_INTENT_CONTINUATION_UNAVAILABLE")
    assert harness.composition._core.store.counts() == before
    assert registry._pending_production_task_intents == {}

    restart_pending = await registry.handle_p3_intent(
        params=_production_registry_text_params(
            stem="restart-status",
            text="status “Synthetic release notes”",
        ),
        request_id="duplicate-status-restart",
        session_id="session-1",
    )
    assert restart_pending.ok is True, restart_pending.payload
    restart_result = restart_pending.payload["result"]
    assert isinstance(restart_result, dict)
    restart_token = restart_result["confirmation_token"]
    assert isinstance(restart_token, str)
    await registry.stop()

    restarted = AgentServerProductCompositionRegistry(
        settings=ProductCompositionSettings(
            p2_enabled=False,
            p3_text_enabled=True,
            p3_mutation_enabled=True,
        ),
        p3_composition=harness.composition,
        agent_manager=object(),
        push_text_event=push,
        p3_confirmation_owner=owner,
        p3_confirmation_forwarder=forwarder,
        commit_ledger=commits,
    )
    after_restart = await restarted.handle_p3_intent(
        params=_production_registry_text_params(
            stem="restart-answer",
            text=f"status {first_task}",
            continuation_id=restart_token,
        ),
        request_id="duplicate-status-restart-answer",
        session_id="session-1",
    )
    assert after_restart.ok is False
    assert after_restart.payload["error"]["reason"] == (
        "TASK_INTENT_CONTINUATION_UNAVAILABLE"
    )
    assert harness.composition._core.store.counts() == before
    assert restarted._pending_production_task_intents == {}
    await restarted.stop()
    await harness.composition.stop()


@pytest.mark.asyncio
async def test_registry_production_confirmation_task_set_drift_has_zero_effect(
    tmp_path: Path,
) -> None:
    commits = TurnCommitLedger()
    harness = _harness(
        tmp_path,
        commit_ledger=commits,
        executor_profiles=(DirectProjectCodeExecutorAdapter.capability_profile(),),
    )
    await harness.composition.start()
    await _stop_test_reconciliation_worker(harness.composition)
    owner = BoundedP3ConfirmationOwner(harness.database, enabled=True)
    forwarder = ProductP3ConfirmationForwarder(owner)

    async def push(_message: dict[str, object]) -> bool:
        return True

    registry = AgentServerProductCompositionRegistry(
        settings=ProductCompositionSettings(
            p2_enabled=False,
            p3_text_enabled=True,
            p3_mutation_enabled=True,
        ),
        p3_composition=harness.composition,
        agent_manager=object(),
        push_text_event=push,
        p3_confirmation_owner=owner,
        p3_confirmation_forwarder=forwarder,
        commit_ledger=commits,
    )
    stale = await registry.handle_p3_intent(
        params=_production_registry_text_params(
            stem="stale-create",
            text="新建一个任务，基于合成依赖起草发布说明。",
        ),
        request_id="stale-create",
        session_id="session-1",
    )
    assert stale.ok is True, stale.payload
    stale_result = stale.payload["result"]
    assert isinstance(stale_result, dict)
    stale_token = stale_result["confirmation_token"]
    assert isinstance(stale_token, str)

    intervening = await registry.handle_p3_intent(
        params=_production_registry_text_params(
            stem="intervening-create",
            text="新建一个任务，基于合成依赖起草发布说明。",
        ),
        request_id="intervening-create",
        session_id="session-1",
    )
    intervening_result = intervening.payload["result"]
    assert isinstance(intervening_result, dict)
    intervening_token = intervening_result["confirmation_token"]
    assert isinstance(intervening_token, str)
    accepted = await registry.handle_p3_intent(
        params=_production_registry_text_params(
            stem="intervening-confirm",
            text=f"confirm task request {intervening_token}",
            continuation_id=intervening_token,
        ),
        request_id="intervening-confirm",
        session_id="session-1",
    )
    assert accepted.ok is True, accepted.payload
    before_stale_confirmation = harness.composition._core.store.counts()

    rejected = await registry.handle_p3_intent(
        params=_production_registry_text_params(
            stem="stale-confirm",
            text=f"confirm task request {stale_token}",
            continuation_id=stale_token,
        ),
        request_id="stale-confirm",
        session_id="session-1",
    )
    assert rejected.ok is False
    assert rejected.payload["error"]["reason"] == (
        "TASK_INTENT_CONFIRMATION_FACTS_CHANGED"
    )
    assert harness.composition._core.store.counts() == before_stale_confirmation
    assert stale_token not in registry._pending_production_task_intents

    replay = await registry.handle_p3_intent(
        params=_production_registry_text_params(
            stem="stale-confirm-replay",
            text=f"confirm task request {stale_token}",
            continuation_id=stale_token,
        ),
        request_id="stale-confirm-replay",
        session_id="session-1",
    )
    assert replay.ok is False
    assert replay.payload["error"]["reason"] == ("TASK_INTENT_CONTINUATION_UNAVAILABLE")
    assert harness.composition._core.store.counts() == before_stale_confirmation

    await registry.stop()
    await harness.composition.stop()


def _base(session_id: str = "session-1") -> dict[str, object]:
    return {"auth_token": TOKEN, "session_id": session_id}


def _create_params(command_id: str = "command-create") -> dict[str, object]:
    return {
        **_base(),
        "command_id": command_id,
        "confirmation_id": f"forged:{command_id}",
        "issued_at": NOW,
        "correlation_id": f"correlation:{command_id}",
        "name": "Formal project task",
        "instruction": "Create one bounded project change.",
        "model_intent": "default",
    }


def _mutation_params(task_id: str) -> dict[str, object]:
    return {
        **_base(),
        "command_id": "command-cancel",
        "confirmation_id": "forged:command-cancel",
        "issued_at": NOW,
        "correlation_id": "correlation:command-cancel",
        "task_id": task_id,
    }


def _adjust_params(
    task_id: str, command_id: str = "command-adjust"
) -> dict[str, object]:
    return {
        **_base(),
        "command_id": command_id,
        "confirmation_id": f"forged:{command_id}",
        "issued_at": NOW,
        "correlation_id": f"correlation:{command_id}",
        "task_id": task_id,
        "instruction": "Change the dinner reservation to 19:00.",
    }


def _issue_confirmation(
    harness: _Harness,
    params: dict[str, object],
    *,
    operation: str,
    principal_id: str = "user-1",
    scope: ScopeRef | None = None,
    expires_at: str = EXPIRY,
    now: str = NOW,
) -> dict[str, object]:
    target_task_id = (
        str(params["task_id"]) if operation in P3_TARGETED_MUTATIONS else None
    )
    context = (
        harness.authority.contexts[str(params["session_id"])]
        if operation == "task.create"
        else None
    )
    model = (
        ResolvedP3Model(
            object(), harness.models.identity, harness.models.config_version
        )
        if operation == "task.create"
        else None
    )
    command_id = str(params["command_id"])
    binding = P3ConfirmationBinding(
        principal_id=principal_id,
        scope=scope or context.scope if context is not None else scope or _scope(),
        operation=operation,
        command_id=command_id,
        target_task_id=target_task_id,
        intent_fingerprint=p3_confirmation_intent_fingerprint(
            operation=operation,
            command_id=command_id,
            target_task_id=target_task_id,
            context=context,
            name=(str(params["name"]) if operation == "task.create" else None),
            instruction=(
                str(params["instruction"])
                if operation in {"task.create", "task.adjust"}
                else None
            ),
            model=model,
            source=str(params.get("source", "structured")),
            interaction_id=(
                str(params["interaction_id"]) if "interaction_id" in params else None
            ),
            turn_id=(str(params["turn_id"]) if "turn_id" in params else None),
            commit_id=(str(params["commit_id"]) if "commit_id" in params else None),
        ),
    )
    params["confirmation_id"] = harness.confirmations.issue(
        binding, expires_at=expires_at, now=now
    )
    return params


def _issued_create_params(
    harness: _Harness, command_id: str = "command-create"
) -> dict[str, object]:
    return _issue_confirmation(
        harness, _create_params(command_id), operation="task.create"
    )


def _issued_cancel_params(harness: _Harness, task_id: str) -> dict[str, object]:
    return _issue_confirmation(
        harness, _mutation_params(task_id), operation="task.cancel"
    )


def _store_counts(database: Path) -> tuple[int, ...]:
    with sqlite3.connect(database) as connection:
        return tuple(
            connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("tasks", "attempts", "task_events", "outbox", "commands")
        )


def test_p2_response_generation_owner_is_lazy_and_bound_to_the_task_store(
    tmp_path: Path,
) -> None:
    first = _harness(tmp_path)
    sidecar = tmp_path / "formal-tasks.sqlite3.p2-response-generations.sqlite3"

    assert first.composition._p2_response_generation_database == sidecar
    assert first.composition._p2_response_generation_owner is None
    assert sidecar.exists() is False
    assert (
        first.composition.next_product_p2_response_generation(
            "session-generation",
            "interaction-generation",
            -1,
        )
        == 0
    )
    assert sidecar.is_file()

    restarted = _harness(tmp_path)
    assert restarted.composition._p2_response_generation_owner is None
    assert (
        restarted.composition.next_product_p2_response_generation(
            "session-generation",
            "interaction-generation",
            -1,
        )
        == 1
    )


async def _wait_until(predicate, *, attempts: int = 100) -> None:
    for _ in range(attempts):
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("condition was not reached")


@pytest.mark.asyncio
async def test_authenticated_six_operation_journey_is_exactly_scoped_and_idempotent(
    tmp_path: Path,
) -> None:
    harness = _harness(tmp_path)
    await harness.composition.start()
    try:
        created = await harness.composition.handle(
            operation="task.create",
            params=_issued_create_params(harness),
            request_id="request-create",
            session_id="session-1",
        )
        assert created.ok is True
        task_id = created.payload["result"]["task_id"]
        persisted = harness.composition._core.store.get_task(task_id, _scope())
        assert dict(persisted.spec.attributes) == {
            "model_identity": "default#0",
            "model_config_version": "catalog-v1",
        }
        await _wait_until(lambda: len(harness.executor.dispatches) == 1)

        get_result = await harness.composition.handle(
            operation="task.get",
            params={**_base(), "task_id": task_id},
            request_id="request-get",
            session_id="session-1",
        )
        list_result = await harness.composition.handle(
            operation="task.list",
            params=_base(),
            request_id="request-list",
            session_id="session-1",
        )
        status_result = await harness.composition.handle(
            operation="task.status",
            params={**_base(), "task_id": task_id},
            request_id="request-status",
            session_id="session-1",
        )
        events_result = await harness.composition.handle(
            operation="task.events",
            params={**_base(), "task_id": task_id, "after_seq": -1},
            request_id="request-events",
            session_id="session-1",
        )
        result_result = await harness.composition.handle(
            operation="task.result",
            params={**_base(), "task_id": task_id},
            request_id="request-result",
            session_id="session-1",
        )

        assert get_result.payload["result"]["task"]["task_id"] == task_id
        assert [item["task_id"] for item in list_result.payload["result"]["tasks"]] == [
            task_id
        ]
        assert status_result.payload["result"]["attempt"]["executor_ref"].startswith(
            "carrier:"
        )
        assert [
            event["seq"] for event in events_result.payload["result"]["events"]
        ] == [
            0,
            1,
            2,
            3,
        ]
        assert result_result.ok is True
        assert result_result.payload["result"] == {
            "availability": "not_ready",
            "reason": "TASK_RESULT_NOT_READY",
            "task_id": task_id,
            "task_result": None,
        }

        wrong_scope = await harness.composition.handle(
            operation="task.get",
            params={**_base("session-2"), "task_id": task_id},
            request_id="request-wrong-scope",
            session_id="session-2",
        )
        wrong_scope_result = await harness.composition.handle(
            operation="task.result",
            params={**_base("session-2"), "task_id": task_id},
            request_id="request-wrong-scope-result",
            session_id="session-2",
        )
        assert wrong_scope_result.ok is False
        assert wrong_scope.ok is False
        assert wrong_scope.payload["error"]["code"] == "NOT_FOUND"
        assert task_id not in str(wrong_scope.payload["error"])

        cancelled = await harness.composition.handle(
            operation="task.cancel",
            params=_issued_cancel_params(harness, task_id),
            request_id="request-cancel",
            session_id="session-1",
        )
        assert cancelled.ok is True
        await _wait_until(lambda: len(harness.executor.cancels) == 1)
        await harness.composition.reconcile_once()
        await harness.composition.reconcile_once()
        assert len(harness.executor.dispatches) == 1
        assert len(harness.executor.cancels) == 1
        assert len(harness.telemetry.events) == 9
    finally:
        await harness.composition.stop()
    assert harness.closer.calls == 1


@pytest.mark.asyncio
async def test_production_classifier_bridge_store_and_authenticated_core_queries(
    tmp_path: Path,
) -> None:
    harness = _harness(
        tmp_path,
        allowed_operations=P3_PRODUCT_AUTHORITY_OPERATIONS,
    )
    await harness.composition.start()
    try:
        created = await harness.composition.handle(
            operation="task.create",
            params=_issued_create_params(harness, "command-production-query-seed"),
            request_id="request-production-query-seed",
            session_id="session-1",
        )
        assert created.ok and created.payload["result"] is not None
        task_id = str(created.payload["result"]["task_id"])
        await harness.composition.reconcile_once()
        assert (
            harness.composition._core.store.get_task(task_id, _scope()).state
            is FormalTaskState.RUNNING
        )
        before = _store_counts(harness.database)
        classifier = ProductionTaskIntentClassifier()
        bridge = VoiceTaskBridge()
        clarification = BoundedClarificationOwner(
            capacity=8,
            per_subject_capacity=2,
            boot_id="production-query-boot",
        )
        reader = StoreProductionTaskAuthorityReader(
            store=harness.composition._core.store,
            principal_id=_scope().subject_id,
            scope=_scope(),
            authority_context_fingerprint=production_context_fingerprint(
                harness.authority.contexts["session-1"]
            ),
        )
        cases = (
            ("task.list", None, {"query_kind": "list", "limit": 20}),
            ("task.get", task_id, {"query_kind": "get"}),
            ("task.status", task_id, {"query_kind": "status"}),
            (
                "task.events",
                task_id,
                {"query_kind": "events", "after_seq": -1, "limit": 100},
            ),
            ("task.result", task_id, {"query_kind": "result"}),
        )
        assert {case[0] for case in cases} <= P3_PRODUCTION_OPERATIONS
        results = {}
        for index, (operation, target, arguments) in enumerate(cases):
            proposal = classifier.parse_structured(
                {
                    "operation": operation,
                    "target": target,
                    "arguments": arguments,
                },
                committed=True,
                source_confidence=1.0,
            )
            request = ProductionTaskIntentRequest(
                origin=ProductionIntentOrigin.STRUCTURED,
                scope=_scope(),
                command_id=f"command-production-query-{index}",
                proposal=proposal,
                source_id=f"structured-production-query-{index}",
            )
            expected_origin = build_production_origin_binding(request)
            origin_authority = CallLocalProductionOriginAuthority(
                expected_binding=expected_origin
            )
            resolution = bridge.resolve_production(
                request,
                reader,
                origin_authority,
                _NoProductionConfirmation(),
                clarification,
            )

            routed = await harness.composition.handle_production_resolution(
                resolution=resolution,
                bearer_token=TOKEN,
                request_id=f"request-production-query-{index}",
                session_id="session-1",
                correlation_id=f"correlation-production-query-{index}",
                origin_authority=origin_authority,
            )

            assert routed.ok is True, routed.payload
            results[operation] = routed.payload["result"]

        assert [item["task_id"] for item in results["task.list"]["tasks"]] == [task_id]
        assert results["task.get"]["task"]["task_id"] == task_id
        assert results["task.status"]["attempt"]["task_id"] == task_id
        assert results["task.events"]["events"][0]["event_type"] == "task.accepted"
        assert results["task.result"]["availability"] == "not_ready"
        assert _store_counts(harness.database) == before
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_production_confirmation_is_consumed_once_before_exact_core_cancel(
    tmp_path: Path,
) -> None:
    run_now = "2026-08-21T02:00:00Z"
    run_expiry = "2026-08-22T04:00:00Z"
    context = _context(tmp_path, expires_at=run_expiry)
    harness = _harness(
        tmp_path,
        contexts={"session-1": context},
        expires_at=run_expiry,
        allowed_operations=P3_PRODUCT_AUTHORITY_OPERATIONS,
        executor_profiles=(DirectProjectCodeExecutorAdapter.capability_profile(),),
        clock=lambda: run_now,
    )
    await harness.composition.start()
    await _stop_test_reconciliation_worker(harness.composition)
    try:
        create_params = _create_params("command-production-cancel-seed")
        create_params["issued_at"] = run_now
        _issue_confirmation(
            harness,
            create_params,
            operation="task.create",
            expires_at="2026-08-21T02:02:00Z",
            now=run_now,
        )
        created = await harness.composition.handle(
            operation="task.create",
            params=create_params,
            request_id="request-production-cancel-seed",
            session_id="session-1",
        )
        assert created.ok and created.payload["result"] is not None
        task_id = str(created.payload["result"]["task_id"])
        assert await harness.composition._core.drain_outbox_once(observed_at=run_now)
        assert (
            harness.composition._core.store.get_task(task_id, _scope()).state
            is FormalTaskState.RUNNING
        )
        reader = StoreProductionTaskAuthorityReader(
            store=harness.composition._core.store,
            principal_id=_scope().subject_id,
            scope=_scope(),
            authority_context_fingerprint=production_context_fingerprint(
                harness.authority.contexts["session-1"]
            ),
        )
        classifier = ProductionTaskIntentClassifier()
        proposal = classifier.parse_structured(
            {
                "operation": "task.cancel",
                "target": task_id,
                "arguments": {},
            },
            committed=True,
            source_confidence=1.0,
        )
        request = ProductionTaskIntentRequest(
            origin=ProductionIntentOrigin.STRUCTURED,
            scope=_scope(),
            command_id="command-production-cancel",
            proposal=proposal,
            source_id="structured-production-cancel",
        )
        expected_origin = build_production_origin_binding(request)
        origin_authority = CallLocalProductionOriginAuthority(
            expected_binding=expected_origin
        )
        clarification = BoundedClarificationOwner(
            capacity=8,
            per_subject_capacity=2,
            boot_id="production-cancel-boot",
        )
        bridge = VoiceTaskBridge()
        prepared = bridge.resolve_production(
            request,
            reader,
            origin_authority,
            _NoProductionConfirmation(),
            clarification,
        )
        assert prepared.confirmation == "required"
        assert prepared.confirmation_binding is not None
        production_binding = prepared.confirmation_binding
        p3_binding = P3ConfirmationBinding(
            principal_id=_scope().subject_id,
            scope=_scope(),
            operation=production_binding.operation,
            command_id=production_binding.command_id,
            target_task_id=production_binding.target_task_id,
            intent_fingerprint=production_binding.fingerprint,
        )
        owner_context = P3ConfirmationOwnerContext(
            session_id="session-1",
            correlation_id="correlation-production-cancel",
            owner_generation=1,
        )
        confirmation_owner = BoundedP3ConfirmationOwner(
            harness.database,
            enabled=True,
        )
        confirmation_id = "confirmation-production-cancel"
        confirmation_owner.issue(
            TrustedP3ConfirmationIssue(
                binding=p3_binding,
                owner=owner_context,
                expires_at="2026-08-21T02:02:00Z",
                confirmation_id=confirmation_id,
            ),
            now=run_now,
        )
        validated = confirmation_owner.validate_for_forwarding(
            confirmation_id,
            p3_binding,
            owner_context,
            now=run_now,
        )
        consumer = CallLocalProductionConfirmationConsumer(
            expected_binding=production_binding,
            validated=validated,
            forwarder=ProductP3ConfirmationForwarder(confirmation_owner),
            now=run_now,
        )
        confirmed = bridge.resolve_production(
            replace(request, confirmation_id=confirmation_id),
            reader,
            origin_authority,
            consumer,
            clarification,
        )
        assert confirmed.confirmation == "confirmed"
        before = _store_counts(harness.database)

        routed = await harness.composition.handle_production_resolution(
            resolution=confirmed,
            bearer_token=TOKEN,
            request_id="request-production-cancel",
            session_id="session-1",
            correlation_id="correlation-production-cancel",
            origin_authority=origin_authority,
            confirmation_consumer=consumer,
        )
        assert await harness.composition._core.drain_outbox_once(observed_at=run_now)
        await _wait_until(lambda: len(harness.executor.cancels) == 1)
        after = _store_counts(harness.database)
        replay = await harness.composition.handle_production_resolution(
            resolution=confirmed,
            bearer_token=TOKEN,
            request_id="request-production-cancel-replay",
            session_id="session-1",
            correlation_id="correlation-production-cancel",
            origin_authority=origin_authority,
            confirmation_consumer=consumer,
        )

        assert routed.ok is True, routed.payload
        assert after[4] == before[4] + 1
        reopened = SqliteTaskStore(harness.database)
        assert reopened.get_task(task_id, _scope()).task_id == task_id
        assert replay.ok is False
        assert replay.payload["error"]["reason"] in {
            "PRODUCTION_CONFIRMATION_CLAIM_REPLAY",
            "PRODUCTION_TASK_AUTHORITY_CHANGED",
        }
        assert _store_counts(harness.database) == after
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "drift",
    ["context_revision", "context_uri", "model_catalog"],
)
async def test_production_create_confirmation_rejects_context_or_model_drift(
    tmp_path: Path,
    drift: str,
) -> None:
    run_now = "2026-08-21T02:00:00Z"
    run_expiry = "2026-08-22T04:00:00Z"
    harness = _harness(
        tmp_path,
        contexts={"session-1": _context(tmp_path, expires_at=run_expiry)},
        expires_at=run_expiry,
        allowed_operations=P3_PRODUCT_AUTHORITY_OPERATIONS,
        executor_profiles=(DirectProjectCodeExecutorAdapter.capability_profile(),),
        clock=lambda: run_now,
    )
    await harness.composition.start()
    await _stop_test_reconciliation_worker(harness.composition)
    try:
        resolution, origin_authority, confirmation_consumer = (
            _confirmed_production_resolution(
                harness,
                tmp_path,
                operation="task.create",
                target=None,
                arguments={
                    "name": "Context-bound production task",
                    "instruction": "Create only under the confirmed authority.",
                },
                identity=f"create-{drift}",
                now=run_now,
                expires_at="2026-08-21T02:02:00Z",
            )
        )
        before = _store_counts(harness.database)
        if drift in {"context_revision", "context_uri"}:
            current = harness.authority.contexts["session-1"]
            harness.authority.contexts["session-1"] = replace(
                current,
                revision_value=(
                    "different-clean-revision"
                    if drift == "context_revision"
                    else current.revision_value
                ),
                uri=(
                    (tmp_path / "remapped-project").resolve().as_uri()
                    if drift == "context_uri"
                    else current.uri
                ),
            )
        else:
            harness.models.config_version = "catalog-v2"

        routed = await harness.composition.handle_production_resolution(
            resolution=resolution,
            bearer_token=TOKEN,
            request_id=f"request-production-create-{drift}",
            session_id="session-1",
            correlation_id=f"correlation-production-create-{drift}",
            origin_authority=origin_authority,
            confirmation_consumer=confirmation_consumer,
            current_background_session_id="session-1",
        )

        assert routed.ok is False
        assert routed.payload["error"]["reason"] == (
            "PRODUCTION_TASK_AUTHORITY_CHANGED"
        )
        assert _store_counts(harness.database) == before
        assert harness.executor.dispatches == []
        assert harness.executor.cancels == []
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_production_target_mutation_requires_exact_persisted_context_revision(
    tmp_path: Path,
) -> None:
    run_now = "2026-08-21T02:00:00Z"
    run_expiry = "2026-08-22T04:00:00Z"
    harness = _harness(
        tmp_path,
        contexts={"session-1": _context(tmp_path, expires_at=run_expiry)},
        expires_at=run_expiry,
        allowed_operations=P3_PRODUCT_AUTHORITY_OPERATIONS,
        executor_profiles=(DirectProjectCodeExecutorAdapter.capability_profile(),),
        clock=lambda: run_now,
    )
    await harness.composition.start()
    await _stop_test_reconciliation_worker(harness.composition)
    try:
        create, create_origin, create_consumer = _confirmed_production_resolution(
            harness,
            tmp_path,
            operation="task.create",
            target=None,
            arguments={
                "name": "Context seed task",
                "instruction": "Seed one context-bound Task.",
            },
            identity="context-seed",
            now=run_now,
            expires_at="2026-08-21T02:02:00Z",
        )
        created = await harness.composition.handle_production_resolution(
            resolution=create,
            bearer_token=TOKEN,
            request_id="request-production-context-seed",
            session_id="session-1",
            correlation_id="correlation-production-context-seed",
            origin_authority=create_origin,
            confirmation_consumer=create_consumer,
            current_background_session_id="session-1",
        )
        assert created.ok and created.payload["result"] is not None
        task_id = str(created.payload["result"]["task_id"])
        resolution, origin_authority, confirmation_consumer = (
            _confirmed_production_resolution(
                harness,
                tmp_path,
                operation="task.cancel",
                target=task_id,
                arguments={},
                identity="cancel-context-drift",
                now=run_now,
                expires_at="2026-08-21T02:02:00Z",
            )
        )
        before = _store_counts(harness.database)
        current = harness.authority.contexts["session-1"]
        harness.authority.contexts["session-1"] = replace(
            current,
            revision_value="different-clean-revision",
        )

        routed = await harness.composition.handle_production_resolution(
            resolution=resolution,
            bearer_token=TOKEN,
            request_id="request-production-cancel-context-drift",
            session_id="session-1",
            correlation_id="correlation-production-cancel-context-drift",
            origin_authority=origin_authority,
            confirmation_consumer=confirmation_consumer,
        )

        assert routed.ok is False
        assert routed.payload["error"]["reason"] in {
            "EXECUTION_CONTEXT_REVISION_MISMATCH",
            "PRODUCTION_TASK_AUTHORITY_CHANGED",
        }
        assert _store_counts(harness.database) == before
        assert (
            harness.composition._core.store.get_task(task_id, _scope()).cancel_requested
            is False
        )
        assert harness.executor.cancels == []
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_production_target_mutation_accepts_compatible_context_renewal(
    tmp_path: Path,
) -> None:
    run_now = "2026-08-21T02:00:00Z"
    run_expiry = "2026-08-22T04:00:00Z"
    harness = _harness(
        tmp_path,
        contexts={"session-1": _context(tmp_path, expires_at=run_expiry)},
        expires_at="2026-08-22T06:00:00Z",
        allowed_operations=P3_PRODUCT_AUTHORITY_OPERATIONS,
        executor_profiles=(DirectProjectCodeExecutorAdapter.capability_profile(),),
        clock=lambda: run_now,
    )
    await harness.composition.start()
    await _stop_test_reconciliation_worker(harness.composition)
    try:
        create, create_origin, create_consumer = _confirmed_production_resolution(
            harness,
            tmp_path,
            operation="task.create",
            target=None,
            arguments={
                "name": "Renewable context task",
                "instruction": "Accept authority renewal without changing revision.",
            },
            identity="context-renewal-seed",
            now=run_now,
            expires_at="2026-08-21T02:02:00Z",
        )
        created = await harness.composition.handle_production_resolution(
            resolution=create,
            bearer_token=TOKEN,
            request_id="request-production-context-renewal-seed",
            session_id="session-1",
            correlation_id="correlation-production-context-renewal-seed",
            origin_authority=create_origin,
            confirmation_consumer=create_consumer,
            current_background_session_id="session-1",
        )
        assert created.ok and created.payload["result"] is not None
        task_id = str(created.payload["result"]["task_id"])
        persisted = harness.composition._core.store.get_task(task_id, _scope())
        current = harness.authority.contexts["session-1"]
        harness.authority.contexts["session-1"] = replace(
            current,
            expires_at="2026-08-22T05:00:00Z",
        )
        resolution, origin_authority, confirmation_consumer = (
            _confirmed_production_resolution(
                harness,
                tmp_path,
                operation="task.cancel",
                target=task_id,
                arguments={},
                identity="cancel-context-renewal",
                now=run_now,
                expires_at="2026-08-21T02:02:00Z",
            )
        )

        routed = await harness.composition.handle_production_resolution(
            resolution=resolution,
            bearer_token=TOKEN,
            request_id="request-production-cancel-context-renewal",
            session_id="session-1",
            correlation_id="correlation-production-cancel-context-renewal",
            origin_authority=origin_authority,
            confirmation_consumer=confirmation_consumer,
        )

        assert routed.ok is True, routed.payload
        cancelled = harness.composition._core.store.get_task(task_id, _scope())
        assert cancelled.cancel_requested is True
        assert cancelled.spec.context == persisted.spec.context
        assert (
            harness.authority.contexts["session-1"].revision_value
            == persisted.spec.context.revision_value
        )
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_production_query_allows_clean_revision_advance_but_rejects_remap(
    tmp_path: Path,
) -> None:
    run_now = "2026-08-21T02:00:00Z"
    run_expiry = "2026-08-22T04:00:00Z"
    harness = _harness(
        tmp_path,
        contexts={"session-1": _context(tmp_path, expires_at=run_expiry)},
        expires_at=run_expiry,
        allowed_operations=P3_PRODUCT_AUTHORITY_OPERATIONS,
        executor_profiles=(DirectProjectCodeExecutorAdapter.capability_profile(),),
        clock=lambda: run_now,
    )
    await harness.composition.start()
    await _stop_test_reconciliation_worker(harness.composition)
    try:
        create, create_origin, create_consumer = _confirmed_production_resolution(
            harness,
            tmp_path,
            operation="task.create",
            target=None,
            arguments={
                "name": "Readable context task",
                "instruction": "Remain readable across one clean revision advance.",
            },
            identity="query-context-seed",
            now=run_now,
            expires_at="2026-08-21T02:02:00Z",
        )
        created = await harness.composition.handle_production_resolution(
            resolution=create,
            bearer_token=TOKEN,
            request_id="request-production-query-context-seed",
            session_id="session-1",
            correlation_id="correlation-production-query-context-seed",
            origin_authority=create_origin,
            confirmation_consumer=create_consumer,
            current_background_session_id="session-1",
        )
        assert created.ok and created.payload["result"] is not None
        task_id = str(created.payload["result"]["task_id"])
        proposal = ProductionTaskIntentClassifier().parse_structured(
            {
                "operation": "task.get",
                "target": task_id,
                "arguments": {"query_kind": "get"},
            },
            committed=True,
            source_confidence=1.0,
        )
        request = ProductionTaskIntentRequest(
            origin=ProductionIntentOrigin.STRUCTURED,
            scope=_scope(),
            command_id="command-production-query-context",
            proposal=proposal,
            source_id="structured-production-query-context",
        )
        origin_binding = build_production_origin_binding(request)
        origin_authority = CallLocalProductionOriginAuthority(
            expected_binding=origin_binding
        )
        original = harness.authority.contexts["session-1"]
        reader = StoreProductionTaskAuthorityReader(
            store=harness.composition._core.store,
            principal_id=_scope().subject_id,
            scope=_scope(),
            authority_context_fingerprint=production_context_fingerprint(original),
        )
        resolution = VoiceTaskBridge().resolve_production(
            request,
            reader,
            origin_authority,
            _NoProductionConfirmation(),
            BoundedClarificationOwner(
                capacity=8,
                per_subject_capacity=2,
                boot_id="production-query-context-boot",
            ),
        )
        before = _store_counts(harness.database)
        harness.authority.contexts["session-1"] = replace(
            original,
            revision_value="next-clean-revision",
        )
        readable = await harness.composition.handle_production_resolution(
            resolution=resolution,
            bearer_token=TOKEN,
            request_id="request-production-query-context-revision",
            session_id="session-1",
            correlation_id="correlation-production-query-context-revision",
            origin_authority=origin_authority,
        )
        assert readable.ok is True, readable.payload
        assert readable.payload["result"]["task"]["task_id"] == task_id
        assert _store_counts(harness.database) == before

        harness.authority.contexts["session-1"] = replace(
            original,
            uri=(tmp_path / "remapped-project").resolve().as_uri(),
        )
        remapped = await harness.composition.handle_production_resolution(
            resolution=resolution,
            bearer_token=TOKEN,
            request_id="request-production-query-context-remap",
            session_id="session-1",
            correlation_id="correlation-production-query-context-remap",
            origin_authority=origin_authority,
        )
        assert remapped.ok is False
        assert remapped.payload["error"]["reason"] == (
            "EXECUTION_CONTEXT_SCOPE_MISMATCH"
        )
        assert _store_counts(harness.database) == before
        assert harness.executor.cancels == []
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_production_list_revalidates_returned_context_after_query_race(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_now = "2026-08-21T02:30:00Z"
    harness = _harness(
        tmp_path,
        contexts={"session-1": _context(tmp_path, expires_at="2026-08-22T04:00:00Z")},
        expires_at="2026-08-22T06:00:00Z",
        allowed_operations=P3_PRODUCT_AUTHORITY_OPERATIONS,
        executor_profiles=(DirectProjectCodeExecutorAdapter.capability_profile(),),
        clock=lambda: run_now,
    )
    await harness.composition.start()
    await _stop_test_reconciliation_worker(harness.composition)
    try:
        classifier = ProductionTaskIntentClassifier()
        proposal = classifier.parse_structured(
            {
                "operation": "task.list",
                "target": None,
                "arguments": {"query_kind": "list", "limit": 20},
            },
            committed=True,
            source_confidence=1.0,
        )
        request = ProductionTaskIntentRequest(
            origin=ProductionIntentOrigin.STRUCTURED,
            scope=_scope(),
            command_id="command-production-list-context-race",
            proposal=proposal,
            source_id="structured-production-list-context-race",
        )
        origin_binding = build_production_origin_binding(request)
        origin_authority = CallLocalProductionOriginAuthority(
            expected_binding=origin_binding
        )
        reader = StoreProductionTaskAuthorityReader(
            store=harness.composition._core.store,
            principal_id=_scope().subject_id,
            scope=_scope(),
            authority_context_fingerprint=production_context_fingerprint(
                harness.authority.contexts["session-1"]
            ),
        )
        resolution = VoiceTaskBridge().resolve_production(
            request,
            reader,
            origin_authority,
            _NoProductionConfirmation(),
            BoundedClarificationOwner(
                capacity=8,
                per_subject_capacity=2,
                boot_id="production-list-context-race-boot",
            ),
        )
        assert resolution.confirmation == "not_required"

        core = harness.composition._core
        original_query = core.query
        injected_counts: list[tuple[int, ...]] = []

        def query_after_context_remap(envelope, authorization, **kwargs):
            command_id = "command-injected-remapped-context"
            create = CommandEnvelope.from_dict(
                {
                    "contract_version": CONTRACT_VERSION,
                    "request_id": "request-injected-remapped-context",
                    "command_id": command_id,
                    "command_type": "task.create",
                    "issued_at": run_now,
                    "scope": _scope().to_dict(),
                    "correlation_id": "correlation-injected-remapped-context",
                    "causation_id": None,
                    "origin": {
                        "kind": "structured",
                        "turn_id": None,
                        "commit_id": None,
                    },
                    "target_ref": {"kind": "task", "id": f"create:{command_id}"},
                    "context_refs": [],
                    "required_capabilities": ["task.create"],
                    "payload": {
                        "name": "Concurrent remapped Task",
                        "instruction": "Must not escape through the returned list page.",
                        "executor_id": FORMAL_PROJECT_EXECUTOR_ID,
                        "side_effect_class": "project_mutation",
                        "attributes": {
                            "model_identity": harness.models.identity,
                            "model_config_version": harness.models.config_version,
                        },
                    },
                    "extensions": {},
                }
            )
            remapped_context = replace(
                harness.authority.contexts["session-1"],
                uri=(tmp_path / "concurrent-remapped-project").resolve().as_uri(),
            )
            injected = core.execute(
                create,
                TaskAuthorizationGrant(
                    principal_id=_scope().subject_id,
                    scope=_scope(),
                    operation="task.create",
                    command_id=command_id,
                    target_task_id=None,
                    allowed_capabilities=frozenset({"task.create"}),
                    confirmation_id="confirmation-injected-remapped-context",
                    confirmed=True,
                    expires_at="2026-08-22T05:00:00Z",
                ),
                context=remapped_context,
                now=run_now,
                selection=harness.composition._select_production_create_candidate(),
                admission_policy=harness.composition._admission_policy,
            )
            assert injected.ok is True
            injected_counts.append(_store_counts(harness.database))
            return original_query(envelope, authorization, **kwargs)

        monkeypatch.setattr(core, "query", query_after_context_remap)
        before_executor = (
            tuple(harness.executor.dispatches),
            tuple(harness.executor.cancels),
            tuple(harness.executor.adjustments),
        )

        routed = await harness.composition.handle_production_resolution(
            resolution=resolution,
            bearer_token=TOKEN,
            request_id="request-production-list-context-race",
            session_id="session-1",
            correlation_id="correlation-production-list-context-race",
            origin_authority=origin_authority,
        )

        assert routed.ok is False
        assert routed.payload["error"]["reason"] == "EXECUTION_CONTEXT_SCOPE_MISMATCH"
        assert len(injected_counts) == 1
        assert _store_counts(harness.database) == injected_counts[0]
        assert (
            tuple(harness.executor.dispatches),
            tuple(harness.executor.cancels),
            tuple(harness.executor.adjustments),
        ) == before_executor
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_production_mutations_map_create_update_reprioritize_adjust_and_successor(
    tmp_path: Path,
) -> None:
    run_now = "2026-08-21T02:00:00Z"
    confirmation_expiry = "2026-08-21T02:02:00Z"
    run_expiry = "2026-08-22T04:00:00Z"
    harness = _harness(
        tmp_path,
        contexts={"session-1": _context(tmp_path, expires_at=run_expiry)},
        expires_at=run_expiry,
        allowed_operations=P3_PRODUCT_AUTHORITY_OPERATIONS,
        executor_profiles=(DirectProjectCodeExecutorAdapter.capability_profile(),),
        clock=lambda: run_now,
    )
    await harness.composition.start()
    await _stop_test_reconciliation_worker(harness.composition)
    try:
        create, create_origin, create_consumer = _confirmed_production_resolution(
            harness,
            tmp_path,
            operation="task.create",
            target=None,
            arguments={
                "name": "Production mutable task",
                "instruction": "Prepare one bounded production artifact.",
            },
            identity="create-full",
            now=run_now,
            expires_at=confirmation_expiry,
        )
        exact_profiles = harness.composition._executor_profiles
        assert exact_profiles is not None
        before_create_drift = _store_counts(harness.database)
        harness.composition._executor_profiles = (
            replace(exact_profiles[0], profile_id="direct-drifted-create"),
        )
        rejected_create_drift = await harness.composition.handle_production_resolution(
            resolution=create,
            bearer_token=TOKEN,
            request_id="request-production-create-drifted",
            session_id="session-1",
            correlation_id="correlation-production-create-full",
            origin_authority=create_origin,
            confirmation_consumer=create_consumer,
            current_background_session_id="session-1",
        )
        assert rejected_create_drift.ok is False
        assert rejected_create_drift.payload["error"]["reason"] == (
            "PRODUCTION_TASK_AUTHORITY_CHANGED"
        )
        assert _store_counts(harness.database) == before_create_drift
        harness.composition._executor_profiles = exact_profiles
        created = await harness.composition.handle_production_resolution(
            resolution=create,
            bearer_token=TOKEN,
            request_id="request-production-create-full",
            session_id="session-1",
            correlation_id="correlation-production-create-full",
            origin_authority=create_origin,
            confirmation_consumer=create_consumer,
            current_background_session_id="session-1",
        )
        assert created.ok and created.payload["result"] is not None
        task_id = str(created.payload["result"]["task_id"])
        task = harness.composition._core.store.get_task(task_id, _scope())
        assert task.state is FormalTaskState.ACCEPTED

        update, update_origin, update_consumer = _confirmed_production_resolution(
            harness,
            tmp_path,
            operation="task.update",
            target=task_id,
            arguments={"instruction": "Prepare the revised bounded artifact."},
            identity="update-full",
            now=run_now,
            expires_at=confirmation_expiry,
        )
        updated = await harness.composition.handle_production_resolution(
            resolution=update,
            bearer_token=TOKEN,
            request_id="request-production-update-full",
            session_id="session-1",
            correlation_id="correlation-production-update-full",
            origin_authority=update_origin,
            confirmation_consumer=update_consumer,
        )
        assert updated.ok is True, updated.payload
        assert (
            harness.composition._core.store.get_task(task_id, _scope()).spec.instruction
            == "Prepare the revised bounded artifact."
        )

        reprioritize, reprioritize_origin, reprioritize_consumer = (
            _confirmed_production_resolution(
                harness,
                tmp_path,
                operation="task.reprioritize",
                target=task_id,
                arguments={"priority": "urgent"},
                identity="reprioritize-full",
                now=run_now,
                expires_at=confirmation_expiry,
            )
        )
        reprioritized = await harness.composition.handle_production_resolution(
            resolution=reprioritize,
            bearer_token=TOKEN,
            request_id="request-production-reprioritize-full",
            session_id="session-1",
            correlation_id="correlation-production-reprioritize-full",
            origin_authority=reprioritize_origin,
            confirmation_consumer=reprioritize_consumer,
        )
        assert reprioritized.ok is True, reprioritized.payload
        assert (
            harness.composition._core.store.admission_projection(
                task_id, _scope()
            ).priority.value
            == "urgent"
        )

        harness.executor.dispatch_outcome = None
        assert await harness.composition._core.drain_outbox_once(observed_at=run_now)
        assert (
            harness.composition._core.store.get_task(task_id, _scope()).state
            is FormalTaskState.RUNNING
        )
        adjust, adjust_origin, adjust_consumer = _confirmed_production_resolution(
            harness,
            tmp_path,
            operation="task.adjust",
            target=task_id,
            arguments={"adjustment": "Use the final bounded checkpoint."},
            identity="adjust-full",
            now=run_now,
            expires_at=confirmation_expiry,
        )
        adjusted = await harness.composition.handle_production_resolution(
            resolution=adjust,
            bearer_token=TOKEN,
            request_id="request-production-adjust-full",
            session_id="session-1",
            correlation_id="correlation-production-adjust-full",
            origin_authority=adjust_origin,
            confirmation_consumer=adjust_consumer,
        )
        assert adjusted.ok is True, adjusted.payload
        assert adjusted.payload["result"]["adjustment_state"] == "pending"
        reopened = SqliteTaskStore(harness.database)
        assert reopened.get_task(task_id, _scope()).task_id == task_id

        second_create, second_origin, second_consumer = (
            _confirmed_production_resolution(
                harness,
                tmp_path,
                operation="task.create",
                target=None,
                arguments={
                    "name": "Production predecessor task",
                    "instruction": "Produce one predecessor artifact.",
                },
                identity="predecessor-full",
                now=run_now,
                expires_at=confirmation_expiry,
            )
        )
        predecessor_created = await harness.composition.handle_production_resolution(
            resolution=second_create,
            bearer_token=TOKEN,
            request_id="request-production-predecessor-full",
            session_id="session-1",
            correlation_id="correlation-production-predecessor-full",
            origin_authority=second_origin,
            confirmation_consumer=second_consumer,
        )
        assert predecessor_created.ok and predecessor_created.payload["result"]
        predecessor_id = str(predecessor_created.payload["result"]["task_id"])
        harness.executor.dispatch_outcome = TerminalOutcome.CANCELLED
        while await harness.composition._core.drain_outbox_once(observed_at=run_now):
            pass
        predecessor = harness.composition._core.store.get_task(predecessor_id, _scope())
        assert predecessor.outcome is TerminalOutcome.CANCELLED

        successor, successor_origin, successor_consumer = (
            _confirmed_production_resolution(
                harness,
                tmp_path,
                operation="task.create_successor",
                target=predecessor_id,
                arguments={
                    "name": "Production successor task",
                    "instruction": "Produce the exact successor artifact.",
                },
                identity="successor-full",
                now=run_now,
                expires_at=confirmation_expiry,
            )
        )
        exact_profiles = harness.composition._executor_profiles
        assert exact_profiles is not None
        before_successor_drift = _store_counts(harness.database)
        current_context = harness.authority.contexts["session-1"]
        harness.authority.contexts["session-1"] = replace(
            current_context,
            revision_value="successor-context-drift",
        )
        rejected_successor_context_drift = (
            await harness.composition.handle_production_resolution(
                resolution=successor,
                bearer_token=TOKEN,
                request_id="request-production-successor-context-drifted",
                session_id="session-1",
                correlation_id="correlation-production-successor-full",
                origin_authority=successor_origin,
                confirmation_consumer=successor_consumer,
            )
        )
        assert rejected_successor_context_drift.ok is False
        assert rejected_successor_context_drift.payload["error"]["reason"] in {
            "EXECUTION_CONTEXT_REVISION_MISMATCH",
            "PRODUCTION_TASK_AUTHORITY_CHANGED",
        }
        assert _store_counts(harness.database) == before_successor_drift
        harness.authority.contexts["session-1"] = current_context
        harness.composition._executor_profiles = (
            replace(exact_profiles[0], profile_id="direct-drifted-successor"),
        )
        rejected_successor_drift = (
            await harness.composition.handle_production_resolution(
                resolution=successor,
                bearer_token=TOKEN,
                request_id="request-production-successor-drifted",
                session_id="session-1",
                correlation_id="correlation-production-successor-full",
                origin_authority=successor_origin,
                confirmation_consumer=successor_consumer,
            )
        )
        assert rejected_successor_drift.ok is False
        assert rejected_successor_drift.payload["error"]["reason"] == (
            "PRODUCTION_TASK_AUTHORITY_CHANGED"
        )
        assert _store_counts(harness.database) == before_successor_drift
        harness.composition._executor_profiles = exact_profiles
        succeeded = await harness.composition.handle_production_resolution(
            resolution=successor,
            bearer_token=TOKEN,
            request_id="request-production-successor-full",
            session_id="session-1",
            correlation_id="correlation-production-successor-full",
            origin_authority=successor_origin,
            confirmation_consumer=successor_consumer,
        )
        assert succeeded.ok is True, succeeded.payload
        successor_id = str(succeeded.payload["result"]["task_id"])
        successor_task = harness.composition._core.store.get_task(
            successor_id, _scope()
        )
        predecessor_attempt = harness.composition._core.store.task_read_snapshot(
            predecessor_id, _scope()
        )[1]
        successor_attempt = harness.composition._core.store.task_read_snapshot(
            successor_id, _scope()
        )[1]
        assert successor_attempt.selection == predecessor_attempt.selection
        assert successor_task.predecessor_task_id == predecessor_id
        assert successor_task.revision_number == predecessor.revision_number + 1
        projected = StoreProductionTaskAuthorityReader(
            store=harness.composition._core.store,
            principal_id=_scope().subject_id,
            scope=_scope(),
        ).list_visible_tasks(_scope())
        projected_by_id = {fact.task_id: fact for fact in projected.tasks}
        assert projected_by_id[predecessor_id].successor_task_id == successor_id
        assert projected_by_id[successor_id].predecessor_task_id == predecessor_id
        assert (
            projected_by_id[successor_id].revision_number
            == projected_by_id[predecessor_id].revision_number + 1
        )
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_authenticated_task_list_preserves_page_continuation_metadata(
    tmp_path: Path,
) -> None:
    harness = _harness(tmp_path)
    await harness.composition.start()
    try:
        task_ids: set[str] = set()
        for suffix in ("one", "two"):
            created = await harness.composition.handle(
                operation="task.create",
                params=_issued_create_params(harness, f"command-page-{suffix}"),
                request_id=f"request-page-create-{suffix}",
                session_id="session-1",
            )
            assert created.ok is True
            task_ids.add(str(created.payload["result"]["task_id"]))

        first = await harness.composition.handle(
            operation="task.list",
            params={**_base(), "limit": 1},
            request_id="request-page-one",
            session_id="session-1",
        )
        assert first.ok is True
        first_page = first.payload["result"]
        assert first_page["cursor"] is None
        assert first_page["limit"] == 1
        assert first_page["has_more"] is True
        assert first_page["next_cursor"] == first_page["tasks"][0]["task_id"]

        second = await harness.composition.handle(
            operation="task.list",
            params={
                **_base(),
                "cursor": first_page["next_cursor"],
                "limit": 1,
            },
            request_id="request-page-two",
            session_id="session-1",
        )
        assert second.ok is True
        second_page = second.payload["result"]
        assert second_page["cursor"] == first_page["next_cursor"]
        assert second_page["limit"] == 1
        assert second_page["has_more"] is False
        assert second_page["next_cursor"] is None
        assert {
            first_page["tasks"][0]["task_id"],
            second_page["tasks"][0]["task_id"],
        } == task_ids
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_voice_task_create_requires_exact_accepted_commit_and_text(
    tmp_path: Path,
) -> None:
    ledger = TurnCommitLedger()
    harness = _harness(tmp_path, commit_ledger=ledger)
    voice_commit = TurnCommit.from_dict(
        {
            "contract_version": CONTRACT_VERSION,
            "commit_id": "commit-voice-task",
            "turn_id": "turn-voice-task",
            "interaction_id": "interaction-voice-task",
            "text": "Create one bounded project change.",
            "hypothesis_provenance": {
                "provider": "product.web.voice",
                "kind": "committed_text",
            },
            "scope": _scope().to_dict(),
            "context_refs": [],
            "committed_at": NOW,
        }
    )
    await harness.composition.start()
    try:
        unaccepted = _create_params("command-unaccepted-voice")
        unaccepted.update(
            source="voice",
            interaction_id=voice_commit.interaction_id,
            turn_id=voice_commit.turn_id,
            commit_id=voice_commit.commit_id,
        )
        rejected = await harness.composition.handle(
            operation="task.create",
            params=_issue_confirmation(harness, unaccepted, operation="task.create"),
            request_id="request-unaccepted-voice",
            session_id="session-1",
        )
        assert rejected.ok is False
        assert rejected.payload["error"]["reason"] == "TURN_COMMIT_NOT_ACCEPTED"
        assert _store_counts(harness.database) == (0, 0, 0, 0, 0)
        assert harness.executor.dispatches == []

        assert ledger.accept(voice_commit) is True
        changed = _create_params("command-changed-voice")
        changed.update(
            source="voice",
            interaction_id=voice_commit.interaction_id,
            turn_id=voice_commit.turn_id,
            commit_id=voice_commit.commit_id,
            instruction="A different instruction must not borrow the commit.",
        )
        changed_result = await harness.composition.handle(
            operation="task.create",
            params=_issue_confirmation(harness, changed, operation="task.create"),
            request_id="request-changed-voice",
            session_id="session-1",
        )
        assert changed_result.ok is False
        assert changed_result.payload["error"]["reason"] == (
            "VOICE_TASK_INSTRUCTION_MISMATCH"
        )
        assert _store_counts(harness.database) == (0, 0, 0, 0, 0)
        assert harness.executor.dispatches == []

        exact = _create_params("command-exact-voice")
        exact.update(
            source="voice",
            interaction_id=voice_commit.interaction_id,
            turn_id=voice_commit.turn_id,
            commit_id=voice_commit.commit_id,
        )
        accepted = await harness.composition.handle(
            operation="task.create",
            params=_issue_confirmation(harness, exact, operation="task.create"),
            request_id="request-exact-voice",
            session_id="session-1",
        )
        assert accepted.ok is True
        await _wait_until(lambda: len(harness.executor.dispatches) == 1)
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_trusted_demo_bypass_requires_unified_voice_current_binding(
    tmp_path: Path,
) -> None:
    ledger = TurnCommitLedger()
    harness = _harness(tmp_path, commit_ledger=ledger)
    await harness.composition.start()
    try:
        structured = _create_params("command-structured-bypass")
        structured.pop("confirmation_id")
        forbidden = await harness.composition.handle(
            operation="task.create",
            params=structured,
            request_id="request-structured-bypass",
            session_id="session-1",
            trusted_demo_policy_bypass=True,
            current_background_session_id="session-1",
        )
        assert forbidden.ok is False
        assert forbidden.payload["error"]["reason"] == (
            "TRUSTED_DEMO_POLICY_BYPASS_FORBIDDEN"
        )
        assert _store_counts(harness.database) == (0, 0, 0, 0, 0)

        create_commit = TurnCommit.from_dict(
            {
                "contract_version": CONTRACT_VERSION,
                "commit_id": "commit-demo-create",
                "turn_id": "turn-demo-create",
                "interaction_id": "interaction-demo",
                "text": "Create one bounded project change.",
                "hypothesis_provenance": {
                    "provider": "product.web.voice",
                    "kind": "committed_text",
                },
                "scope": _scope().to_dict(),
                "context_refs": [],
                "committed_at": NOW,
            }
        )
        assert ledger.accept(create_commit) is True
        create_params = _create_params("command-demo-create")
        create_params.pop("confirmation_id")
        create_params.update(
            source="voice",
            interaction_id=create_commit.interaction_id,
            turn_id=create_commit.turn_id,
            commit_id=create_commit.commit_id,
            origin_commit_sha256=hashlib.sha256(
                create_commit.canonical_bytes()
            ).hexdigest(),
            source_start=0,
            source_end=len(create_commit.text),
        )
        created = await harness.composition.handle(
            operation="task.create",
            params=create_params,
            request_id="request-demo-create",
            session_id="session-1",
            trusted_demo_policy_bypass=True,
            current_background_session_id="session-1",
        )
        assert created.ok is True
        task_id = created.payload["result"]["task_id"]
        current = await harness.composition.read_current_background_task(
            bearer_token=TOKEN,
            session_id="session-1",
        )
        assert current is not None and current.task_id == task_id
        current_result = await harness.composition.handle(
            operation="task.result",
            params={**_base(), "task_id": task_id},
            request_id="request-demo-current-result",
            session_id="session-1",
        )
        assert current_result.ok is True
        assert current_result.payload["result"] == {
            "task_id": task_id,
            "availability": "not_ready",
            "reason": "TASK_RESULT_NOT_READY",
            "task_result": None,
        }

        cancel_commit = TurnCommit.from_dict(
            {
                "contract_version": CONTRACT_VERSION,
                "commit_id": "commit-demo-cancel",
                "turn_id": "turn-demo-cancel",
                "interaction_id": "interaction-demo",
                "text": "停止刚才的后台任务。",
                "hypothesis_provenance": {
                    "provider": "product.web.voice",
                    "kind": "committed_text",
                },
                "scope": _scope().to_dict(),
                "context_refs": [],
                "committed_at": NOW,
            }
        )
        assert ledger.accept(cancel_commit) is True
        cancel_params = _mutation_params(task_id)
        cancel_params.pop("confirmation_id")
        cancel_params.update(
            source="voice",
            interaction_id=cancel_commit.interaction_id,
            turn_id=cancel_commit.turn_id,
            commit_id=cancel_commit.commit_id,
            origin_commit_sha256=hashlib.sha256(
                cancel_commit.canonical_bytes()
            ).hexdigest(),
            source_start=0,
            source_end=len(cancel_commit.text),
        )
        wrong_binding = await harness.composition.handle(
            operation="task.cancel",
            params=cancel_params,
            request_id="request-demo-cancel-wrong-target",
            session_id="session-1",
            trusted_demo_policy_bypass=True,
            trusted_current_task_id="task-wrong-current",
        )
        assert wrong_binding.ok is False
        assert wrong_binding.payload["error"]["reason"] == (
            "CURRENT_BACKGROUND_TASK_MISMATCH"
        )
        assert (
            harness.composition._core.store.get_task(task_id, _scope()).cancel_requested
            is False
        )

        cancelled = await harness.composition.handle(
            operation="task.cancel",
            params=cancel_params,
            request_id="request-demo-cancel",
            session_id="session-1",
            trusted_demo_policy_bypass=True,
            trusted_current_task_id=task_id,
        )
        assert cancelled.ok is True
        assert (
            harness.composition._core.store.get_task(task_id, _scope()).cancel_requested
            is True
        )
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_authenticated_addressed_adjust_can_target_noncurrent_task(
    tmp_path: Path,
) -> None:
    harness = _harness(tmp_path)
    await harness.composition.start()
    try:
        task_ids: list[str] = []
        for suffix in ("first", "current"):
            created = await harness.composition.handle(
                operation="task.create",
                params=_issued_create_params(
                    harness, f"command-create-adjust-{suffix}"
                ),
                request_id=f"request-create-adjust-{suffix}",
                session_id="session-1",
                current_background_session_id="session-1",
            )
            assert created.ok is True
            task_ids.append(str(created.payload["result"]["task_id"]))
        await _wait_until(lambda: len(harness.executor.dispatches) == 2)

        store = harness.composition._core.store
        noncurrent_task_id, current_task_id = task_ids
        selection = store.get_current_background_task(_scope(), session_id="session-1")
        assert selection is not None and selection.task_id == current_task_id
        current_before = store.get_task(current_task_id, _scope())
        assert current_before is not None

        params = _issue_confirmation(
            harness,
            _adjust_params(noncurrent_task_id, "command-adjust-addressed"),
            operation="task.adjust",
        )
        adjusted = await harness.composition.handle(
            operation="task.adjust",
            params=params,
            request_id="request-adjust-addressed",
            session_id="session-1",
        )

        assert adjusted.ok is True
        assert adjusted.payload["result"]["task_id"] == noncurrent_task_id
        await _wait_until(
            lambda: harness.executor.adjustments == ["command-adjust-addressed"]
        )
        noncurrent_events = store.events(noncurrent_task_id, _scope(), after_seq=-1)
        assert [
            event.event_type
            for event in noncurrent_events
            if event.event_type.startswith("task.adjust_")
        ] == ["task.adjust_requested", "task.adjust_applied"]
        current_after = store.get_task(current_task_id, _scope())
        assert current_after is not None
        assert current_after.event_head == current_before.event_head
        assert not any(
            event.event_type.startswith("task.adjust_")
            for event in store.events(current_task_id, _scope(), after_seq=-1)
        )
        selection = store.get_current_background_task(_scope(), session_id="session-1")
        assert selection is not None and selection.task_id == current_task_id
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_task_adjust_requires_exact_current_binding_and_reaches_core(
    tmp_path: Path,
) -> None:
    ledger = TurnCommitLedger()
    harness = _harness(tmp_path, commit_ledger=ledger)
    await harness.composition.start()
    try:
        created = await harness.composition.handle(
            operation="task.create",
            params=_issued_create_params(harness, "command-create-for-adjust"),
            request_id="request-create-for-adjust",
            session_id="session-1",
            current_background_session_id="session-1",
        )
        assert created.ok is True
        task_id = str(created.payload["result"]["task_id"])
        await _wait_until(lambda: len(harness.executor.dispatches) == 1)
        before_rejection = _store_counts(harness.database)

        oversized = _adjust_params(task_id, "command-adjust-oversized")
        oversized["instruction"] = "好" * 1_366
        oversized_result = await harness.composition.handle(
            operation="task.adjust",
            params=oversized,
            request_id="request-adjust-oversized",
            session_id="session-1",
            current_background_session_id="session-1",
            trusted_current_task_id=task_id,
        )
        assert oversized_result.ok is False
        assert oversized_result.payload["error"]["reason"] == (
            "INVALID_TASK_ADJUSTMENT"
        )
        assert _store_counts(harness.database) == before_rejection

        def voice_adjust(command_id: str) -> dict[str, object]:
            params = _adjust_params(task_id, command_id)
            commit = TurnCommit.from_dict(
                {
                    "contract_version": CONTRACT_VERSION,
                    "commit_id": f"commit:{command_id}",
                    "turn_id": f"turn:{command_id}",
                    "interaction_id": "interaction-adjust",
                    "text": params["instruction"],
                    "hypothesis_provenance": {
                        "provider": "product.web.voice",
                        "kind": "committed_text",
                    },
                    "scope": _scope().to_dict(),
                    "context_refs": [],
                    "committed_at": NOW,
                }
            )
            assert ledger.accept(commit) is True
            params.update(
                source="voice",
                interaction_id=commit.interaction_id,
                turn_id=commit.turn_id,
                commit_id=commit.commit_id,
                origin_commit_sha256=hashlib.sha256(
                    commit.canonical_bytes()
                ).hexdigest(),
                source_start=0,
                source_end=len(commit.text),
            )
            return _issue_confirmation(harness, params, operation="task.adjust")

        wrong_session_params = voice_adjust("command-adjust-wrong-session")
        wrong_session = await harness.composition.handle(
            operation="task.adjust",
            params=wrong_session_params,
            request_id="request-adjust-wrong-session",
            session_id="session-1",
            current_background_session_id="session-2",
            trusted_current_task_id=task_id,
        )
        assert wrong_session.ok is False
        assert wrong_session.payload["error"]["reason"] == (
            "CURRENT_BACKGROUND_TASK_BINDING_REQUIRED"
        )
        assert _store_counts(harness.database) == before_rejection

        wrong_task_params = voice_adjust("command-adjust-wrong-task")
        wrong_task = await harness.composition.handle(
            operation="task.adjust",
            params=wrong_task_params,
            request_id="request-adjust-wrong-task",
            session_id="session-1",
            current_background_session_id="session-1",
            trusted_current_task_id="task-not-current",
        )
        assert wrong_task.ok is False
        assert wrong_task.payload["error"]["reason"] == (
            "CURRENT_BACKGROUND_TASK_MISMATCH"
        )
        assert _store_counts(harness.database) == before_rejection

        exact_params = voice_adjust("command-adjust-exact")
        exact = await harness.composition.handle(
            operation="task.adjust",
            params=exact_params,
            request_id="request-adjust-exact",
            session_id="session-1",
            current_background_session_id="session-1",
            trusted_current_task_id=task_id,
        )
        assert exact.ok is True
        assert exact.payload["result"]["adjustment_state"] == "pending"
        await _wait_until(
            lambda: harness.executor.adjustments == ["command-adjust-exact"]
        )
        await _wait_until(
            lambda: (
                harness.executor.adjustment_settlements
                == [("command-adjust-exact", TaskAdjustmentState.APPLIED)]
            )
        )
        adjustment_events = [
            event
            for event in harness.composition._core.store.events(
                task_id, _scope(), after_seq=-1
            )
            if event.event_type.startswith("task.adjust_")
        ]
        assert [event.event_type for event in adjustment_events] == [
            "task.adjust_requested",
            "task.adjust_applied",
        ]
        assert all(
            event.causation_id == "command-adjust-exact" for event in adjustment_events
        )
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_invalid_voice_origin_is_rejected_before_durable_confirmation(
    tmp_path: Path,
) -> None:
    ledger = TurnCommitLedger()
    harness = _harness(tmp_path, commit_ledger=ledger)
    params = _create_params("command-invalid-voice-confirmation")
    params.update(
        source="voice",
        interaction_id="interaction-not-accepted",
        turn_id="turn-not-accepted",
        commit_id="commit-not-accepted",
    )
    await harness.composition.start()
    try:
        with pytest.raises(FormalTaskViolation) as raised:
            await harness.composition.prepare_mutation_confirmation(
                operation="task.create",
                params=params,
                session_id="session-1",
            )
        assert raised.value.reason == "TURN_COMMIT_NOT_ACCEPTED"
        with sqlite3.connect(harness.database) as connection:
            assert (
                connection.execute("SELECT COUNT(*) FROM p3_confirmations").fetchone()[
                    0
                ]
                == 0
            )
        assert _store_counts(harness.database) == (0, 0, 0, 0, 0)
        assert harness.executor.dispatches == []
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", (TerminalOutcome.COMPLETED, TerminalOutcome.FAILED))
async def test_product_registry_replays_terminal_p3_authority_after_clean_checkpoint(
    tmp_path: Path,
    outcome: TerminalOutcome,
) -> None:
    from jiuwenswarm.server.live_voice.product_composition_registry import (
        AgentServerProductCompositionRegistry,
        ProductCompositionSettings,
    )

    future_expiry = "2100-01-01T00:00:00Z"
    authorized_context = _context(tmp_path, expires_at=future_expiry)
    harness = _harness(
        tmp_path,
        expires_at=future_expiry,
        contexts={
            "session-1": authorized_context,
        },
    )
    pushed: list[dict[str, object]] = []

    async def push(message: dict[str, object]) -> bool:
        pushed.append(message)
        return True

    registry = AgentServerProductCompositionRegistry(
        settings=ProductCompositionSettings(p2_enabled=False, p3_text_enabled=True),
        p3_composition=harness.composition,
        agent_manager=object(),
        push_text_event=push,
    )
    harness.executor.dispatch_outcome = outcome
    await harness.composition.start()
    try:
        create_params = _issued_create_params(harness, "command-product-owner")
        created = await harness.composition.handle(
            operation="task.create",
            params=create_params,
            request_id="request-product-create",
            session_id="session-1",
        )
        assert created.ok is True
        task_id = str(created.payload["result"]["task_id"])
        await _wait_until(
            lambda: (
                harness.composition._core.store.get_task(task_id, _scope()).state.value
                == "terminal"
            )
        )
        harness.authority.contexts["session-1"] = replace(
            authorized_context,
            revision_value="clean-checkpoint-revision",
        )
        counts_before_progress = harness.composition._core.store.counts()

        queried = await registry.handle_p3_query(
            operation="task.list",
            params=_base(),
            request_id="request-product-list",
            session_id="session-1",
        )
        activated = await registry.handle_p3_progress_activate(
            params={
                **_base(),
                "task_id": task_id,
                "correlation_id": str(create_params["correlation_id"]),
                "origin_id": "web-product-owner",
                "generation_id": "web-product-generation",
                "generation": 1,
            },
            request_id="request-product-progress",
            session_id="session-1",
            channel_id="web",
        )
        assert queried.ok is True
        assert activated.ok is True
        await _wait_until(
            lambda: any(
                message["payload"]["source_event"]["event_type"] == "task.terminal"
                for message in pushed
            )
        )
        closed = await registry.handle_p3_progress_close(
            params={
                **_base(),
                "task_id": task_id,
                "correlation_id": str(create_params["correlation_id"]),
                "origin_id": "web-product-owner",
                "generation_id": "web-product-generation",
                "generation": 1,
            },
            request_id="request-product-progress-close",
            session_id="session-1",
        )
        assert closed.ok is True
        assert activated.payload["result"]["voice_progress"] == "unavailable"
        assert [
            message["payload"]["source_event"]["event_type"] for message in pushed
        ] == ["task.accepted", "task.running", "task.terminal"]
        assert pushed[-1]["payload"]["source_event"]["payload"] == {
            "state": "terminal",
            "outcome": outcome.value,
        }
        assert harness.composition._core.store.counts() == counts_before_progress
    finally:
        await registry.stop()
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_product_registry_uses_real_authority_and_agent_runtime_for_p2(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from jiuwenswarm.server.live_voice.product_composition_registry import (
        AgentServerProductCompositionRegistry,
        ProductCompositionSettings,
    )

    class Facade:
        def supports_formal_live_voice(self) -> bool:
            return True

        async def process_formal_live_voice_stream(self, _execution):
            if False:
                yield None

    class Manager:
        def __init__(self) -> None:
            self.facade = Facade()
            self.get_calls: list[tuple[object, ...]] = []
            self.pins = 0
            self.unpins = 0

        async def get_agent(self, *args):
            self.get_calls.append(args)
            return self.facade

        def pin_agent(self, agent) -> None:
            assert agent is self.facade
            self.pins += 1

        def unpin_agent(self, agent) -> None:
            assert agent is self.facade
            self.unpins += 1

    future_expiry = "2100-01-01T00:00:00Z"
    authorized_context = _context(tmp_path, expires_at=future_expiry)
    harness = _harness(
        tmp_path,
        expires_at=future_expiry,
        contexts={
            "session-1": authorized_context,
        },
        allowed_operations=P3_OPERATIONS | frozenset({"agent.chat"}),
    )
    manager = Manager()

    async def push(_message: dict[str, object]) -> bool:
        raise AssertionError("P2 activation must not use the P3 progress sink")

    registry = AgentServerProductCompositionRegistry(
        settings=ProductCompositionSettings(p2_enabled=True, p3_text_enabled=False),
        p3_composition=harness.composition,
        agent_manager=manager,
        push_text_event=push,
    )
    params = {
        **_base(),
        "correlation_id": "correlation-product-p2",
        "interaction_id": "interaction-product-p2",
        "activation_id": "activation-product-p2",
        "activation_generation": 1,
    }
    await harness.composition.start()
    try:
        harness.authority.contexts["session-1"] = replace(
            authorized_context, permissions=()
        )
        denied = await registry.handle_p2_activate(
            params=params,
            request_id="request-product-p2-denied",
            session_id="session-1",
            channel_id="web",
        )
        assert denied.ok is False
        assert manager.get_calls == []

        harness.authority.contexts["session-1"] = authorized_context
        activated = await registry.handle_p2_activate(
            params=params,
            request_id="request-product-p2",
            session_id="session-1",
            channel_id="web",
        )
        closed = await registry.handle_p2_close(
            params=params,
            request_id="request-product-p2-close",
            session_id="session-1",
        )

        assert activated.ok is True
        assert closed.ok is True
        assert len(manager.get_calls) == 1
        assert manager.pins == 1
        assert manager.unpins == 1
    finally:
        await registry.stop()
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_task_dirty_worktree_allows_reads_and_exact_cancel_but_blocks_new_create(
    tmp_path: Path,
) -> None:
    harness = _harness(tmp_path)
    await harness.composition.start()
    try:
        created = await harness.composition.handle(
            operation="task.create",
            params=_issued_create_params(harness),
            request_id="request-clean-create",
            session_id="session-1",
        )
        task_id = str(created.payload["result"]["task_id"])
        await _wait_until(lambda: len(harness.executor.dispatches) == 1)
        harness.authority.dirty = True

        operations = {
            "task.get": {**_base(), "task_id": task_id},
            "task.list": _base(),
            "task.status": {**_base(), "task_id": task_id},
            "task.events": {**_base(), "task_id": task_id, "after_seq": -1},
        }
        for operation, params in operations.items():
            result = await harness.composition.handle(
                operation=operation,
                params=params,
                request_id=f"request-dirty-{operation}",
                session_id="session-1",
            )
            assert result.ok is True

        cancelled = await harness.composition.handle(
            operation="task.cancel",
            params=_issued_cancel_params(harness, task_id),
            request_id="request-dirty-cancel",
            session_id="session-1",
        )
        assert cancelled.ok is True
        await _wait_until(lambda: len(harness.executor.cancels) == 1)
        before_new_create = _store_counts(harness.database)

        denied = await harness.composition.handle(
            operation="task.create",
            params=_issued_create_params(harness, "command-after-dirty"),
            request_id="request-dirty-create",
            session_id="session-1",
        )

        assert denied.payload["error"]["reason"] == "TASK_CONTEXT_WORKTREE_DIRTY"
        assert _store_counts(harness.database) == before_new_create
        assert len(harness.executor.dispatches) == 1
        assert len(harness.executor.cancels) == 1
        assert harness.authority.calls[0] == ("session-1", True)
        assert [
            require_clean for _session, require_clean in harness.authority.calls
        ] == [
            True,
            False,
            False,
            False,
            True,
            False,
            False,
            True,
        ]
        assert harness.authority.calls[-1] == ("session-1", True)
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_read_queries_survive_clean_checkpoint_revision_but_cancel_fails_closed(
    tmp_path: Path,
) -> None:
    harness = _harness(tmp_path)
    await harness.composition.start()
    try:
        created = await harness.composition.handle(
            operation="task.create",
            params=_issued_create_params(harness),
            request_id="request-create-context-drift",
            session_id="session-1",
        )
        task_id = str(created.payload["result"]["task_id"])
        await _wait_until(lambda: len(harness.executor.dispatches) == 1)
        harness.authority.contexts["session-1"] = replace(
            harness.authority.contexts["session-1"],
            revision_value="clean-checkpoint-revision",
        )
        before = _store_counts(harness.database)

        operations = {
            "task.get": {**_base(), "task_id": task_id},
            "task.list": _base(),
            "task.status": {**_base(), "task_id": task_id},
            "task.events": {**_base(), "task_id": task_id, "after_seq": -1},
        }
        for operation, params in operations.items():
            result = await harness.composition.handle(
                operation=operation,
                params=params,
                request_id=f"request-checkpoint-{operation}",
                session_id="session-1",
            )
            assert result.ok is True, operation

        cancel = await harness.composition.handle(
            operation="task.cancel",
            params=_issued_cancel_params(harness, task_id),
            request_id="request-drift-cancel",
            session_id="session-1",
        )

        assert (
            cancel.payload["error"]["reason"] == "EXECUTION_CONTEXT_REVISION_MISMATCH"
        )
        assert _store_counts(harness.database) == before
        assert harness.executor.cancels == []
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_read_and_cancel_still_fail_closed_on_redacted_context(
    tmp_path: Path,
) -> None:
    harness = _harness(tmp_path)
    await harness.composition.start()
    try:
        created = await harness.composition.handle(
            operation="task.create",
            params=_issued_create_params(harness),
            request_id="request-create-redacted-context",
            session_id="session-1",
        )
        task_id = str(created.payload["result"]["task_id"])
        await _wait_until(lambda: len(harness.executor.dispatches) == 1)
        harness.authority.contexts["session-1"] = replace(
            harness.authority.contexts["session-1"],
            redacted=True,
            redacted_fields=("secret",),
        )
        before = _store_counts(harness.database)

        operations = {
            "task.get": {**_base(), "task_id": task_id},
            "task.list": _base(),
            "task.status": {**_base(), "task_id": task_id},
            "task.events": {**_base(), "task_id": task_id, "after_seq": -1},
            "task.cancel": _issued_cancel_params(harness, task_id),
        }
        for operation, params in operations.items():
            result = await harness.composition.handle(
                operation=operation,
                params=params,
                request_id=f"request-redacted-{operation}",
                session_id="session-1",
            )
            assert result.payload["error"]["reason"] == "TASK_CONTEXT_REDACTED"

        assert _store_counts(harness.database) == before
        assert harness.executor.cancels == []
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_restart_runs_startup_reconciliation_without_duplicate_dispatch(
    tmp_path: Path,
) -> None:
    first = _harness(tmp_path)
    await first.composition.start()
    created = await first.composition.handle(
        operation="task.create",
        params=_issued_create_params(first),
        request_id="request-create",
        session_id="session-1",
    )
    task_id = created.payload["result"]["task_id"]
    await _wait_until(lambda: len(first.executor.dispatches) == 1)
    await first.composition.stop()

    restarted = _harness(tmp_path)
    await restarted.composition.start()
    try:
        status = await restarted.composition.handle(
            operation="task.status",
            params={**_base(), "task_id": task_id},
            request_id="request-after-restart",
            session_id="session-1",
        )
        await restarted.composition.reconcile_once()
        assert status.ok is True
        assert restarted.executor.dispatches == []
        assert restarted.executor.statuses == [task_id, task_id]
        assert _store_counts(restarted.database)[0] == 1
    finally:
        await restarted.composition.stop()


@pytest.mark.asyncio
async def test_concurrent_cancel_replay_produces_one_carrier_effect(
    tmp_path: Path,
) -> None:
    harness = _harness(tmp_path)
    await harness.composition.start()
    try:
        created = await harness.composition.handle(
            operation="task.create",
            params=_issued_create_params(harness),
            request_id="request-create",
            session_id="session-1",
        )
        task_id = created.payload["result"]["task_id"]
        await _wait_until(lambda: len(harness.executor.dispatches) == 1)

        cancel_params = _issued_cancel_params(harness, task_id)
        first, replay = await asyncio.gather(
            harness.composition.handle(
                operation="task.cancel",
                params=dict(cancel_params),
                request_id="request-cancel-1",
                session_id="session-1",
            ),
            harness.composition.handle(
                operation="task.cancel",
                params=dict(cancel_params),
                request_id="request-cancel-2",
                session_id="session-1",
            ),
        )
        assert first.ok is True
        assert replay.ok is True
        await _wait_until(lambda: len(harness.executor.cancels) == 1)
        await harness.composition.reconcile_once()
        assert harness.executor.cancels == [harness.executor.dispatches[0]]
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case", "params", "session_id", "contexts", "expiry", "expected"),
    [
        (
            "unauthenticated",
            {**_create_params(), "auth_token": "wrong"},
            "session-1",
            None,
            EXPIRY,
            "FORMAL_TASK_AUTHENTICATION_REQUIRED",
        ),
        (
            "session-mismatch",
            _create_params(),
            "session-other",
            None,
            EXPIRY,
            "FORMAL_TASK_SESSION_MISMATCH",
        ),
        (
            "expired",
            _create_params(),
            "session-1",
            None,
            "2026-08-05T11:59:59Z",
            "FORMAL_TASK_AUTHORIZATION_EXPIRED",
        ),
        (
            "redacted",
            _create_params(),
            "session-1",
            {"session-1": _context(Path.cwd(), redacted=True)},
            EXPIRY,
            "TASK_CONTEXT_REDACTED",
        ),
    ],
)
async def test_authority_failures_have_zero_persistence_and_executor_effects(
    tmp_path: Path,
    case: str,
    params: dict[str, object],
    session_id: str,
    contexts: dict[str, ResolvedTaskContext] | None,
    expiry: str,
    expected: str,
) -> None:
    del case
    if contexts is not None:
        contexts = {
            key: replace(value, uri=tmp_path.resolve().as_uri())
            for key, value in contexts.items()
        }
    harness = _harness(tmp_path, contexts=contexts, expires_at=expiry)
    await harness.composition.start()
    before = _store_counts(harness.database)
    try:
        result = await harness.composition.handle(
            operation="task.create",
            params=params,
            request_id="request-rejected",
            session_id=session_id,
        )
        await asyncio.sleep(0)
        assert result.ok is False
        assert result.payload["error"]["reason"] == expected
        assert _store_counts(harness.database) == before
        assert harness.executor.dispatches == []
        assert harness.executor.cancels == []
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_authenticated_wrong_project_scope_fails_before_store_and_executor(
    tmp_path: Path,
) -> None:
    harness = _harness(
        tmp_path,
        allowed_project_ids=frozenset({"project-1"}),
    )
    await harness.composition.start()
    before = _store_counts(harness.database)
    try:
        denied_create = await harness.composition.handle(
            operation="task.create",
            params={**_create_params(), "session_id": "session-2"},
            request_id="request-wrong-project-create",
            session_id="session-2",
        )
        denied_list = await harness.composition.handle(
            operation="task.list",
            params=_base("session-2"),
            request_id="request-wrong-project-list",
            session_id="session-2",
        )

        assert denied_create.payload["error"]["reason"] == (
            "FORMAL_TASK_AUTHORIZATION_DENIED"
        )
        assert denied_list.payload["error"]["reason"] == (
            "FORMAL_TASK_AUTHORIZATION_DENIED"
        )
        assert _store_counts(harness.database) == before
        assert harness.executor.dispatches == []
        assert harness.executor.cancels == []
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_browser_authority_fields_and_unconfirmed_cancel_fail_before_core(
    tmp_path: Path,
) -> None:
    harness = _harness(tmp_path)
    await harness.composition.start()
    before = _store_counts(harness.database)
    try:
        claimed = await harness.composition.handle(
            operation="task.create",
            params={**_create_params(), "principal_id": "admin", "project_id": "other"},
            request_id="request-claimed-authority",
            session_id="session-1",
        )
        unconfirmed = await harness.composition.handle(
            operation="task.cancel",
            params={**_mutation_params("task-does-not-exist"), "confirmed": False},
            request_id="request-unconfirmed",
            session_id="session-1",
        )
        assert claimed.payload["error"]["reason"] == "INVALID_P3_ROUTE_ARGUMENT"
        assert unconfirmed.payload["error"]["reason"] == "INVALID_P3_ROUTE_ARGUMENT"
        assert _store_counts(harness.database) == before
        assert harness.executor.dispatches == []
        assert harness.executor.cancels == []
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_confirmation_forgery_cross_binding_and_expiry_have_zero_effects(
    tmp_path: Path,
) -> None:
    harness = _harness(tmp_path)
    await harness.composition.start()
    before = _store_counts(harness.database)
    try:
        forged_claim = await harness.composition.handle(
            operation="task.create",
            params={**_create_params(), "confirmed": True},
            request_id="request-forged-claim",
            session_id="session-1",
        )
        forged_id = await harness.composition.handle(
            operation="task.create",
            params=_create_params(),
            request_id="request-forged-id",
            session_id="session-1",
        )

        command_bound = _issued_create_params(harness, "command-bound")
        cross_command = await harness.composition.handle(
            operation="task.create",
            params={**command_bound, "command_id": "command-other"},
            request_id="request-cross-command",
            session_id="session-1",
        )

        principal_bound = _issue_confirmation(
            harness,
            _create_params("command-principal"),
            operation="task.create",
            principal_id="user-other",
        )
        cross_principal = await harness.composition.handle(
            operation="task.create",
            params=principal_bound,
            request_id="request-cross-principal",
            session_id="session-1",
        )

        scope_bound = _issue_confirmation(
            harness,
            _create_params("command-scope"),
            operation="task.create",
            scope=_scope(project_id="project-2", session_id="session-2"),
        )
        cross_scope = await harness.composition.handle(
            operation="task.create",
            params=scope_bound,
            request_id="request-cross-scope",
            session_id="session-1",
        )

        expired = _issue_confirmation(
            harness,
            _create_params("command-expired"),
            operation="task.create",
            expires_at="2026-08-05T11:30:00Z",
            now="2026-08-05T11:00:00Z",
        )
        expired_result = await harness.composition.handle(
            operation="task.create",
            params=expired,
            request_id="request-expired-confirmation",
            session_id="session-1",
        )

        assert forged_claim.payload["error"]["reason"] == "INVALID_P3_ROUTE_ARGUMENT"
        assert forged_id.payload["error"]["reason"] == "P3_CONFIRMATION_INVALID"
        for result in (cross_command, cross_principal, cross_scope):
            assert result.payload["error"]["reason"] == (
                "P3_CONFIRMATION_BINDING_MISMATCH"
            )
        assert expired_result.payload["error"]["reason"] == "P3_CONFIRMATION_EXPIRED"
        assert _store_counts(harness.database) == before
        assert harness.executor.dispatches == []
        assert harness.executor.cancels == []
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_confirmation_is_single_use_with_exact_idempotent_replay_only(
    tmp_path: Path,
) -> None:
    harness = _harness(tmp_path)
    await harness.composition.start()
    try:
        params = _issued_create_params(harness)
        first = await harness.composition.handle(
            operation="task.create",
            params=dict(params),
            request_id="request-create-first",
            session_id="session-1",
        )
        replay = await harness.composition.handle(
            operation="task.create",
            params=dict(params),
            request_id="request-create-replay",
            session_id="session-1",
        )
        await _wait_until(lambda: len(harness.executor.dispatches) == 1)
        before_conflict = _store_counts(harness.database)
        conflict = await harness.composition.handle(
            operation="task.create",
            params={**params, "command_id": "command-reuse-other"},
            request_id="request-create-reuse-conflict",
            session_id="session-1",
        )

        assert first.ok is True and replay.ok is True
        assert first.payload["result"]["task_id"] == replay.payload["result"]["task_id"]
        assert conflict.payload["error"]["reason"] == (
            "P3_CONFIRMATION_BINDING_MISMATCH"
        )
        assert _store_counts(harness.database) == before_conflict
        assert len(harness.executor.dispatches) == 1
        assert harness.executor.cancels == []
    finally:
        await harness.composition.stop()


def test_confirmation_consumption_and_exact_replay_survive_ledger_restart(
    tmp_path: Path,
) -> None:
    database = tmp_path / "confirmation-restart.sqlite3"
    binding = P3ConfirmationBinding(
        principal_id="user-1",
        scope=_scope(),
        operation="task.cancel",
        command_id="command-cancel",
        target_task_id="task-1",
        intent_fingerprint=p3_confirmation_intent_fingerprint(
            operation="task.cancel",
            command_id="command-cancel",
            target_task_id="task-1",
            context=None,
        ),
    )
    ledger = SqliteP3ConfirmationLedger(database)
    confirmation_id = ledger.issue(binding, expires_at=EXPIRY, now=NOW)

    first = ledger.verify_and_consume(confirmation_id, binding, now=NOW)
    replay = SqliteP3ConfirmationLedger(database).verify_and_consume(
        confirmation_id, binding, now=NOW
    )

    assert first.replayed is False
    assert replay.replayed is True


@pytest.mark.asyncio
async def test_cross_task_confirmation_rejected_without_cancel_effect(
    tmp_path: Path,
) -> None:
    harness = _harness(tmp_path)
    await harness.composition.start()
    try:
        created = []
        for suffix in ("one", "two"):
            result = await harness.composition.handle(
                operation="task.create",
                params=_issued_create_params(harness, f"command-{suffix}"),
                request_id=f"request-{suffix}",
                session_id="session-1",
            )
            created.append(str(result.payload["result"]["task_id"]))
        await _wait_until(lambda: len(harness.executor.dispatches) == 2)
        cancel_one = _issued_cancel_params(harness, created[0])
        before = _store_counts(harness.database)

        result = await harness.composition.handle(
            operation="task.cancel",
            params={**cancel_one, "task_id": created[1]},
            request_id="request-cross-task",
            session_id="session-1",
        )

        assert result.payload["error"]["reason"] == ("P3_CONFIRMATION_BINDING_MISMATCH")
        assert _store_counts(harness.database) == before
        assert harness.executor.cancels == []
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_mutation_without_trusted_confirmation_owner_fails_closed(
    tmp_path: Path,
) -> None:
    database = tmp_path / "no-confirmation-owner.sqlite3"
    executor = _Executor()
    authority = _AuthorityResolver({"session-1": _context(tmp_path)})
    composition = P3AuthenticatedComposition(
        authenticator=StaticBearerAuthenticator(token=TOKEN, principal=_principal()),
        authority_resolver=authority,
        core=PersistentTaskCore(SqliteTaskStore(database), executor),
        model_resolver=_ModelResolver(),
        reconcile_interval=3600,
        clock=lambda: NOW,
    )
    await composition.start()
    before = _store_counts(database)
    try:
        result = await composition.handle(
            operation="task.create",
            params=_create_params(),
            request_id="request-no-confirmation-owner",
            session_id="session-1",
        )
        await asyncio.sleep(0)
        assert result.payload["error"]["reason"] == (
            "FORMAL_TASK_CONFIRMATION_REQUIRED"
        )
        assert _store_counts(database) == before
        assert executor.dispatches == []
        assert executor.cancels == []
    finally:
        await composition.stop()


class _ExplodingCore:
    async def reconcile(self):
        return {}

    def query(self, *_args, **_kwargs):
        raise RuntimeError("corrupt store details must not escape")


@pytest.mark.asyncio
async def test_startup_recovers_carrier_before_core_reconciliation() -> None:
    order: list[str] = []

    class Binding:
        async def prepare_startup(self) -> int:
            order.append("carrier")
            return 1

        async def close(self) -> None:
            order.append("close")

    class Core:
        async def reconcile(self):
            if order == ["carrier"]:
                order.append("core")
            else:
                assert order == ["carrier", "core"]
                order.append("shutdown-core")
            return {"reconciled": 1}

    composition = P3AuthenticatedComposition(
        authenticator=StaticBearerAuthenticator(token=TOKEN, principal=_principal()),
        authority_resolver=_AuthorityResolver({}),
        core=Core(),
        binding_resolver=Binding(),
        reconcile_interval=3600,
        clock=lambda: NOW,
    )

    summary = await composition.start()
    await composition.stop()

    assert summary == {"reconciled": 1}
    assert order == ["carrier", "core", "shutdown-core", "close"]


@pytest.mark.asyncio
async def test_concurrent_starts_create_one_worker_and_one_startup_reconciliation() -> (
    None
):
    prepare_entered = asyncio.Event()
    prepare_release = asyncio.Event()

    class Binding:
        def __init__(self) -> None:
            self.prepare_calls = 0
            self.close_calls = 0

        async def prepare_startup(self) -> int:
            self.prepare_calls += 1
            prepare_entered.set()
            await prepare_release.wait()
            return 1

        async def close(self) -> None:
            self.close_calls += 1

    class Core:
        def __init__(self) -> None:
            self.reconcile_calls = 0

        async def reconcile(self):
            self.reconcile_calls += 1
            return {"reconciled": self.reconcile_calls}

    binding = Binding()
    core = Core()
    composition = P3AuthenticatedComposition(
        authenticator=StaticBearerAuthenticator(token=TOKEN, principal=_principal()),
        authority_resolver=_AuthorityResolver({}),
        core=core,
        binding_resolver=binding,
        reconcile_interval=3600,
        clock=lambda: NOW,
    )

    first = asyncio.create_task(composition.start())
    await prepare_entered.wait()
    second = asyncio.create_task(composition.start())
    prepare_release.set()
    first_result, second_result = await asyncio.gather(first, second)
    worker = composition._worker
    await composition.stop()

    assert first_result == {"reconciled": 1}
    assert second_result == {}
    assert binding.prepare_calls == 1
    assert binding.close_calls == 1
    assert core.reconcile_calls == 2  # startup plus the final shutdown drain
    assert worker is not None and worker.done()


@pytest.mark.asyncio
async def test_stop_wakes_periodic_reconciler_without_cancelling_child_waiter() -> None:
    class Core:
        def __init__(self) -> None:
            self.reconcile_calls = 0

        async def reconcile(self):
            self.reconcile_calls += 1
            return {"reconciled": self.reconcile_calls}

    core = Core()
    composition = P3AuthenticatedComposition(
        authenticator=StaticBearerAuthenticator(token=TOKEN, principal=_principal()),
        authority_resolver=_AuthorityResolver({}),
        core=core,
        reconcile_interval=3600,
        clock=lambda: NOW,
    )

    await composition.start()
    worker = composition._worker
    await asyncio.wait_for(composition.stop(), timeout=1)

    assert core.reconcile_calls == 2  # startup plus final shutdown drain
    assert worker is not None and worker.done() and worker.cancelled() is False


@pytest.mark.asyncio
async def test_stop_waits_for_start_and_prevents_post_stop_reactivation() -> None:
    prepare_entered = asyncio.Event()
    prepare_release = asyncio.Event()

    class Binding:
        def __init__(self) -> None:
            self.close_calls = 0

        async def prepare_startup(self) -> int:
            prepare_entered.set()
            await prepare_release.wait()
            return 0

        async def close(self) -> None:
            self.close_calls += 1

    class Core:
        async def reconcile(self):
            return {}

    binding = Binding()
    composition = P3AuthenticatedComposition(
        authenticator=StaticBearerAuthenticator(token=TOKEN, principal=_principal()),
        authority_resolver=_AuthorityResolver({}),
        core=Core(),
        binding_resolver=binding,
        reconcile_interval=3600,
        clock=lambda: NOW,
    )

    starting = asyncio.create_task(composition.start())
    await prepare_entered.wait()
    stopping = asyncio.create_task(composition.stop())
    await asyncio.sleep(0)
    assert stopping.done() is False
    prepare_release.set()
    await starting
    await stopping

    assert composition.accepting is False
    assert composition._worker is None
    assert binding.close_calls == 1
    with pytest.raises(FormalTaskViolation) as closed:
        await composition.start()
    assert closed.value.reason == "FORMAL_TASK_ROUTE_DISABLED"


@pytest.mark.asyncio
async def test_shutdown_drains_cancelled_mutation_thread_before_carrier_close(
    tmp_path: Path,
) -> None:
    harness = _harness(tmp_path)
    original_execute = harness.composition._core.execute
    execute_entered = threading.Event()
    execute_release = threading.Event()

    def blocking_execute(*args, **kwargs):
        execute_entered.set()
        assert execute_release.wait(timeout=5)
        return original_execute(*args, **kwargs)

    harness.composition._core.execute = blocking_execute  # type: ignore[method-assign]
    await harness.composition.start()
    route = asyncio.create_task(
        harness.composition.handle(
            operation="task.create",
            params=_issued_create_params(harness),
            request_id="request-cancelled-during-store",
            session_id="session-1",
        )
    )
    assert await asyncio.to_thread(execute_entered.wait, 2)
    route.cancel()
    stopping = asyncio.create_task(harness.composition.stop())
    await asyncio.sleep(0)

    assert route.done() is False
    assert stopping.done() is False
    assert harness.closer.calls == 0
    execute_release.set()
    with pytest.raises(asyncio.CancelledError):
        await route
    await stopping

    assert len(harness.executor.dispatches) == 1
    assert harness.closer.calls == 1


@pytest.mark.asyncio
async def test_corruption_fails_closed_without_executor_or_sensitive_error() -> None:
    project = Path.cwd()
    authority = _AuthorityResolver({"session-1": _context(project)})
    composition = P3AuthenticatedComposition(
        authenticator=StaticBearerAuthenticator(token=TOKEN, principal=_principal()),
        authority_resolver=authority,
        core=_ExplodingCore(),
        reconcile_interval=3600,
        clock=lambda: NOW,
    )
    await composition.start()
    try:
        result = await composition.handle(
            operation="task.list",
            params=_base(),
            request_id="request-corrupt",
            session_id="session-1",
        )
        assert result.ok is False
        assert result.payload["error"] == {
            "code": "INTERNAL",
            "reason": "FORMAL_TASK_ROUTE_INTERNAL",
            "message": "formal task route failed closed",
        }
    finally:
        await composition.stop()


def test_flag_off_constructs_no_store_scheduler_or_agent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "must-not-exist.sqlite3"
    monkeypatch.setenv("JIUWENSWARM_LIVE_VOICE_P3_ENABLED", "0")
    monkeypatch.setenv("JIUWENSWARM_LIVE_VOICE_P3_DATABASE", str(database))

    observer_calls: list[object] = []
    composition = create_p3_composition_from_environment(
        agent_manager=object(),
        model_resolver=lambda _name: None,
        stream_observer=observer_calls.append,
    )

    assert composition is None
    assert not database.exists()
    assert observer_calls == []


@pytest.mark.parametrize(
    "interval",
    [math.nan, math.inf, -math.inf, 0.0, -1.0, 3600.0001],
)
def test_composition_rejects_non_finite_or_out_of_range_interval(
    tmp_path: Path, interval: float
) -> None:
    with pytest.raises(ValueError, match=r"\(0, 3600\]"):
        P3AuthenticatedComposition(
            authenticator=StaticBearerAuthenticator(
                token=TOKEN, principal=_principal()
            ),
            authority_resolver=_AuthorityResolver({}),
            core=PersistentTaskCore(
                SqliteTaskStore(tmp_path / f"interval-{repr(interval)}.sqlite3"),
                _Executor(),
            ),
            reconcile_interval=interval,
            clock=lambda: NOW,
        )


@pytest.mark.parametrize("interval", [1e-9, 3600.0])
def test_composition_accepts_reconciliation_interval_boundaries(
    tmp_path: Path, interval: float
) -> None:
    composition = P3AuthenticatedComposition(
        authenticator=StaticBearerAuthenticator(token=TOKEN, principal=_principal()),
        authority_resolver=_AuthorityResolver({}),
        core=PersistentTaskCore(
            SqliteTaskStore(tmp_path / f"valid-interval-{interval}.sqlite3"),
            _Executor(),
        ),
        reconcile_interval=interval,
        clock=lambda: NOW,
    )
    assert composition._reconcile_interval == interval


def _configure_enabled_factory(
    monkeypatch: pytest.MonkeyPatch, interval: object
) -> None:
    monkeypatch.setenv("JIUWENSWARM_LIVE_VOICE_P3_ENABLED", "1")
    monkeypatch.setenv("JIUWENSWARM_LIVE_VOICE_P3_AUTH_TOKEN", TOKEN)
    monkeypatch.setenv("JIUWENSWARM_LIVE_VOICE_P3_PRINCIPAL_ID", "user-1")
    monkeypatch.setenv("JIUWENSWARM_LIVE_VOICE_P3_PROJECT_IDS", "project-1")
    monkeypatch.setenv(
        "JIUWENSWARM_LIVE_VOICE_P3_AUTH_EXPIRES_AT", "2100-01-01T00:00:00Z"
    )
    monkeypatch.setenv(
        "JIUWENSWARM_LIVE_VOICE_P3_EXECUTOR_PROFILE",
        "live-voice.direct-project-code.d2.v1",
    )
    monkeypatch.setenv("JIUWENSWARM_LIVE_VOICE_P3_RECONCILE_SECONDS", str(interval))


@pytest.mark.parametrize("interval", ["nan", "inf", "-inf", "0", "-1", "3600.1"])
def test_factory_rejects_non_finite_or_out_of_range_interval(
    monkeypatch: pytest.MonkeyPatch, interval: str
) -> None:
    _configure_enabled_factory(monkeypatch, interval)
    with pytest.raises(FormalTaskViolation) as raised:
        create_p3_composition_from_environment(
            agent_manager=object(), model_resolver=_ModelResolver()
        )
    assert raised.value.reason == "INVALID_P3_AUTH_CONFIGURATION"


@pytest.mark.parametrize("interval", [1e-9, 3600.0])
def test_factory_accepts_reconciliation_interval_boundaries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    interval: float,
) -> None:
    _configure_enabled_factory(monkeypatch, interval)
    database = tmp_path / f"factory-{interval}.sqlite3"
    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.p3_authenticated_composition._resolve_database_path",
        lambda _configured: database,
    )
    composition = create_p3_composition_from_environment(
        agent_manager=object(), model_resolver=_ModelResolver()
    )

    assert composition is not None
    assert composition._reconcile_interval == interval
    assert type(composition._core.executor) is DirectProjectCodeExecutorAdapter


def test_factory_passes_only_the_explicit_direct_stream_observer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_enabled_factory(monkeypatch, 3600)
    database = tmp_path / "factory-observer.sqlite3"
    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.p3_authenticated_composition._resolve_database_path",
        lambda _configured: database,
    )
    observed: list[object] = []
    observer = observed.append
    profile_before = DirectProjectCodeExecutorAdapter.capability_profile()

    composition = create_p3_composition_from_environment(
        agent_manager=object(),
        model_resolver=_ModelResolver(),
        stream_observer=observer,
    )

    assert composition is not None
    direct = composition._core.executor
    assert type(direct) is DirectProjectCodeExecutorAdapter
    assert direct._stream_observer is observer
    assert direct.capability_profile() is profile_before
    assert direct.capability_profile().digest_sha256() == profile_before.digest_sha256()
    assert observed == []


def test_product_factory_selects_exact_same_store_backed_d2_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catches product composition advertising D2 without its Store authority."""

    _configure_enabled_factory(monkeypatch, 3600)
    database = tmp_path / "factory-d2.sqlite3"
    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.p3_authenticated_composition._resolve_database_path",
        lambda _configured: database,
    )

    composition = create_p3_composition_from_environment(
        agent_manager=object(), model_resolver=_ModelResolver()
    )

    assert composition is not None
    store = composition._core.store
    direct = composition._core.executor
    assert type(store) is SqliteTaskStore
    assert type(direct) is DirectProjectCodeExecutorAdapter
    assert direct._durability_store is store
    assert type(
        composition._authority_resolver._managed_worktree_reader
    ) is DirectProjectManagedBaselineReader
    assert (
        composition._authority_resolver._managed_worktree_reader._store is store
    )
    candidates = direct.capability_profiles()
    assert tuple(profile.durability_level for profile in candidates) == ("D0", "D2")
    assert composition._executor_profiles == (candidates[-1],)
    assert composition._execution_durability_level == "D2"
    assert composition._validated_executor_configuration is not None
    assert (
        composition._validated_executor_configuration.configuration_digest
        == candidates[-1].digest_sha256()
    )


@pytest.mark.parametrize(
    "configured_profile",
    [None, "live-voice.direct-project-code.d1.v1", "unknown-profile"],
)
def test_enabled_factory_fails_closed_without_one_available_exact_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    configured_profile: str | None,
) -> None:
    _configure_enabled_factory(monkeypatch, 3600)
    if configured_profile is None:
        monkeypatch.delenv(
            "JIUWENSWARM_LIVE_VOICE_P3_EXECUTOR_PROFILE", raising=False
        )
    else:
        monkeypatch.setenv(
            "JIUWENSWARM_LIVE_VOICE_P3_EXECUTOR_PROFILE", configured_profile
        )
    database = tmp_path / "unselected-profile.sqlite3"
    resolver_calls: list[str] = []

    def forbidden_database_resolver(_configured: str) -> Path:
        resolver_calls.append("database")
        raise AssertionError("invalid profile reached database resolution")

    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.p3_authenticated_composition._resolve_database_path",
        forbidden_database_resolver,
    )

    with pytest.raises(FormalTaskViolation) as rejected:
        create_p3_composition_from_environment(
            agent_manager=object(), model_resolver=_ModelResolver()
        )

    assert rejected.value.reason == "INVALID_P3_EXECUTOR_CONFIGURATION"
    assert rejected.value.code is ErrorCode.CAPABILITY_UNAVAILABLE
    assert resolver_calls == []
    assert database.exists() is False


def test_factory_consumes_explicit_direct_d0_profile_without_d2_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_enabled_factory(monkeypatch, 3600)
    monkeypatch.setenv(
        "JIUWENSWARM_LIVE_VOICE_P3_EXECUTOR_PROFILE",
        "live-voice.direct-project-code.d0.v1",
    )
    database = tmp_path / "factory-d0.sqlite3"
    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.p3_authenticated_composition._resolve_database_path",
        lambda _configured: database,
    )

    composition = create_p3_composition_from_environment(
        agent_manager=object(), model_resolver=_ModelResolver()
    )

    assert composition is not None
    assert composition._execution_durability_level == "D0"
    assert composition._executor_profiles is not None
    assert composition._executor_profiles[0].profile_id.endswith(".d0.v1")
    assert composition._validated_executor_configuration is not None
    assert (
        composition._validated_executor_configuration.durability_level
        is DurabilityLevel.D0
    )


def test_factory_static_profile_mismatch_precedes_adapter_store_and_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catches factory startup allocating authority before static selection."""

    _configure_enabled_factory(monkeypatch, 3600)
    database = tmp_path / "factory-static-mismatch.sqlite3"
    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.p3_authenticated_composition._resolve_database_path",
        lambda _configured: database,
    )
    direct = DirectProjectCodeExecutorAdapter.construction_capability_profiles(
        store_backed=True
    )[-1]
    incompatible = replace(
        direct,
        operation_versions=tuple(
            (operation, "v2" if operation == "dispatch" else version)
            for operation, version in direct.operation_versions
        ),
    )
    monkeypatch.setattr(
        DirectProjectCodeExecutorAdapter,
        "construction_capability_profiles",
        classmethod(lambda cls, *, store_backed: (incompatible,)),
    )
    adapter_calls: list[str] = []
    store_calls: list[str] = []

    def forbidden_adapter_init(self, *_args, **_kwargs) -> None:
        del self
        adapter_calls.append("adapter")
        raise AssertionError("static mismatch reached Adapter construction")

    class ForbiddenStore:
        def __init__(self, *_args, **_kwargs) -> None:
            store_calls.append("store")
            raise AssertionError("static mismatch reached Store construction")

    monkeypatch.setattr(
        DirectProjectCodeExecutorAdapter,
        "__init__",
        forbidden_adapter_init,
    )
    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.p3_authenticated_composition.SqliteTaskStore",
        ForbiddenStore,
    )

    with pytest.raises(FormalTaskViolation) as rejected:
        create_p3_composition_from_environment(
            agent_manager=object(), model_resolver=_ModelResolver()
        )

    assert rejected.value.reason == "EXECUTOR_CAPABILITY_UNAVAILABLE"
    assert rejected.value.code is ErrorCode.CAPABILITY_UNAVAILABLE
    assert adapter_calls == []
    assert store_calls == []
    assert database.exists() is False


@pytest.mark.parametrize("failure_stage", ["store", "core"])
def test_factory_construction_failure_aborts_owners_in_reverse_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_stage: str,
) -> None:
    """Catches a synchronous Store/Core failure leaking unstarted owners."""

    _configure_enabled_factory(monkeypatch, 3600)
    database = tmp_path / f"factory-{failure_stage}-failure.sqlite3"
    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.p3_authenticated_composition._resolve_database_path",
        lambda _configured: database,
    )
    cleanup_order: list[str] = []
    resolvers: list[AgentManagerProjectBindingResolver] = []
    adapters: list[DirectProjectCodeExecutorAdapter] = []
    original_failure = RuntimeError(f"private-{failure_stage}-initialization")

    class TrackingResolver(AgentManagerProjectBindingResolver):
        def __init__(self, **kwargs) -> None:
            super().__init__(**kwargs)
            resolvers.append(self)

        def _abort_initialization(self) -> None:
            cleanup_order.append("resolver")
            super()._abort_initialization()

    class TrackingAdapter(DirectProjectCodeExecutorAdapter):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)
            adapters.append(self)

        def _abort_initialization(self) -> None:
            cleanup_order.append("executor")
            super()._abort_initialization()

    class FailingStore:
        def __init__(self, *_args, **_kwargs) -> None:
            raise original_failure

    class FailingCore:
        def __init__(self, *_args, **_kwargs) -> None:
            raise original_failure

    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.p3_authenticated_composition.AgentManagerProjectBindingResolver",
        TrackingResolver,
    )
    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.p3_authenticated_composition.DirectProjectCodeExecutorAdapter",
        TrackingAdapter,
    )
    if failure_stage == "store":
        monkeypatch.setattr(
            "jiuwenswarm.server.live_voice.p3_authenticated_composition.SqliteTaskStore",
            FailingStore,
        )
    else:
        monkeypatch.setattr(
            "jiuwenswarm.server.live_voice.p3_authenticated_composition.PersistentTaskCore",
            FailingCore,
        )

    with pytest.raises(RuntimeError) as raised:
        create_p3_composition_from_environment(
            agent_manager=object(), model_resolver=_ModelResolver()
        )

    assert raised.value is original_failure
    expected_cleanup = (
        ["resolver"] if failure_stage == "store" else ["executor", "resolver"]
    )
    assert cleanup_order == expected_cleanup
    assert len(resolvers) == 1
    assert len(adapters) == (0 if failure_stage == "store" else 1)
    if adapters:
        assert adapters[0]._closed is True
        assert adapters[0].has_live_workers is False
        assert adapters[0]._running == {}
        assert adapters[0]._retained_worktree_cleanups == {}
    assert resolvers[0]._close_requested is True
    assert resolvers[0]._closed is True
    assert database.exists() is (failure_stage == "core")
    assert Path(f"{database}-wal").exists() is False
    assert Path(f"{database}-shm").exists() is False
    if database.exists():
        unlocked_database = database.with_suffix(".unlocked")
        database.replace(unlocked_database)
        unlocked_database.replace(database)
        assert tuple(tmp_path.iterdir()) == (database,)
    else:
        assert tuple(tmp_path.iterdir()) == ()


def test_factory_adapter_initialization_failure_aborts_only_resolver(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catches cleanup fabricating an Adapter owner after its constructor failed."""

    _configure_enabled_factory(monkeypatch, 3600)
    database = tmp_path / "factory-adapter-failure.sqlite3"
    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.p3_authenticated_composition._resolve_database_path",
        lambda _configured: database,
    )
    cleanup_order: list[str] = []
    original_failure = RuntimeError("private-adapter-initialization")

    class TrackingResolver(AgentManagerProjectBindingResolver):
        def _abort_initialization(self) -> None:
            cleanup_order.append("resolver")
            super()._abort_initialization()

    class FailingAdapter(DirectProjectCodeExecutorAdapter):
        def __init__(self, *_args, **_kwargs) -> None:
            raise original_failure

        def _abort_initialization(self) -> None:
            cleanup_order.append("executor")
            raise AssertionError("an unconstructed Adapter cannot be closed")

    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.p3_authenticated_composition.AgentManagerProjectBindingResolver",
        TrackingResolver,
    )
    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.p3_authenticated_composition.DirectProjectCodeExecutorAdapter",
        FailingAdapter,
    )

    with pytest.raises(RuntimeError) as raised:
        create_p3_composition_from_environment(
            agent_manager=object(), model_resolver=_ModelResolver()
        )

    assert raised.value is original_failure
    assert cleanup_order == ["resolver"]
    assert database.exists() is True
    assert Path(f"{database}-wal").exists() is False
    assert Path(f"{database}-shm").exists() is False


def test_factory_cleanup_failure_preserves_primary_error_and_sanitizes_log(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catches cleanup replacing or disclosing the synchronous factory failure."""

    _configure_enabled_factory(monkeypatch, 3600)
    database = tmp_path / "factory-cleanup-failure.sqlite3"
    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.p3_authenticated_composition._resolve_database_path",
        lambda _configured: database,
    )
    cleanup_order: list[str] = []
    warnings: list[tuple[str, tuple[object, ...]]] = []
    original_failure = RuntimeError("PRIVATE_PRIMARY_SENTINEL")

    def capture_warning(message: str, *args: object) -> None:
        warnings.append((message, args))

    class TrackingResolver(AgentManagerProjectBindingResolver):
        def _abort_initialization(self) -> None:
            cleanup_order.append("resolver")
            super()._abort_initialization()

    class FailingCleanupAdapter(DirectProjectCodeExecutorAdapter):
        def _abort_initialization(self) -> None:
            cleanup_order.append("executor")
            raise RuntimeError("PRIVATE_CLEANUP_SENTINEL")

    class FailingCore:
        def __init__(self, *_args, **_kwargs) -> None:
            raise original_failure

    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.p3_authenticated_composition.AgentManagerProjectBindingResolver",
        TrackingResolver,
    )
    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.p3_authenticated_composition.DirectProjectCodeExecutorAdapter",
        FailingCleanupAdapter,
    )
    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.p3_authenticated_composition.PersistentTaskCore",
        FailingCore,
    )
    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.p3_authenticated_composition.logger.warning",
        capture_warning,
    )

    with pytest.raises(RuntimeError) as raised:
        create_p3_composition_from_environment(
            agent_manager=object(), model_resolver=_ModelResolver()
        )

    assert raised.value is original_failure
    assert cleanup_order == ["executor", "resolver"]
    assert warnings == [
        (
            "[LiveVoiceP3] factory initialization cleanup failed for %s",
            ("executor",),
        )
    ]
    rendered_warnings = repr(warnings)
    assert "PRIVATE_CLEANUP_SENTINEL" not in rendered_warnings
    assert "PRIVATE_PRIMARY_SENTINEL" not in rendered_warnings


@pytest.mark.asyncio
async def test_product_create_persists_exact_direct_selection_and_admission(
    tmp_path: Path,
) -> None:
    """Catches product Task creation omitting or recomputing selection facts."""

    profile = DirectProjectCodeExecutorAdapter.capability_profile()
    later_profile = replace(
        profile,
        profile_id="zz-live-voice.direct-project-code.d0.v1",
    )
    harness = _harness(
        tmp_path,
        executor_profiles=(later_profile, profile),
    )
    await harness.composition.start()
    try:
        created = await harness.composition.handle(
            operation="task.create",
            params=_issued_create_params(harness, "command-selected-create"),
            request_id="request-selected-create",
            session_id="session-1",
        )

        assert created.ok is True, created.payload
        task_id = str(created.payload["result"]["task_id"])
        task = harness.composition._core.store.get_task(task_id, _scope())
        attempt = harness.composition._core.store.get_attempt(task.attempt_id)
        selection = attempt.selection
        assert selection is not None
        assert selection.adapter_id == profile.adapter_id
        assert selection.capability_profile_digest == profile.digest_sha256()
        assert json.loads(selection.capability_profile_json) == profile.to_dict()
        assert json.loads(selection.execution_requirements_json) == {
            "durability_level": "D0",
            "executor_id": FORMAL_PROJECT_EXECUTOR_ID,
            "operation_versions": [
                ["adjust.demo-itinerary-checkpoint", "v1"],
                ["cancel", "v1"],
                ["dispatch", "v1"],
                ["reconcile.d0", "v1"],
                ["status", "v1"],
            ],
            "project_serialization": "exclusive",
            "schema_version": "live-voice.task-execution-requirements.v1",
            "side_effect_class": "project_mutation",
        }
        admission = harness.composition._core.store.admission_projection(
            task_id, _scope()
        )
        assert admission is not None
        assert admission.deadline_at == "2026-08-05T13:00:00Z"
        assert harness.composition._core._admission_policy == AdmissionPolicy(
            deadline_seconds=3600,
            initial_backoff_seconds=1,
            max_backoff_seconds=60,
            max_attempts=120,
        )
        diagnostics = await harness.composition.read_product_status_diagnostics(
            bearer_token=TOKEN,
            session_id="session-1",
            task_id=task_id,
        )
        assert diagnostics.task_id == task_id
        assert diagnostics.attempt_id == task.attempt_id
        assert diagnostics.executor_id == FORMAL_PROJECT_EXECUTOR_ID
        assert diagnostics.checkpoint_id is None
        assert diagnostics.effect_id is None
        assert diagnostics.recovery_id is None
        assert diagnostics.outbox[0].kind.value == "attempt.dispatch"
        assert diagnostics.outbox[0].state is OutboxState.SUPPRESSED
        harness.authority.contexts["session-1"] = _context(tmp_path, redacted=True)
        with pytest.raises(FormalTaskViolation) as rejected_diagnostics:
            await harness.composition.read_product_status_diagnostics(
                bearer_token=TOKEN,
                session_id="session-1",
                task_id=task_id,
            )
        assert rejected_diagnostics.value.reason == "TASK_CONTEXT_REDACTED"
        frozen_selection = selection
    finally:
        await harness.composition.stop()

    reopened = _harness(
        tmp_path,
        executor_profiles=(later_profile,),
    )
    reopened_task = reopened.composition._core.store.get_task(task_id, _scope())
    reopened_attempt = reopened.composition._core.store.get_attempt(
        reopened_task.attempt_id
    )
    assert reopened_attempt.selection == frozen_selection


@pytest.mark.asyncio
async def test_product_static_mismatch_has_zero_task_executor_or_project_effect(
    tmp_path: Path,
) -> None:
    """Catches route-level mismatch reaching Core after a resolved Task spec."""

    direct = DirectProjectCodeExecutorAdapter.capability_profile()
    incompatible = replace(
        direct,
        operation_versions=tuple(
            (operation, "v2" if operation == "dispatch" else version)
            for operation, version in direct.operation_versions
        ),
    )
    harness = _harness(tmp_path, executor_profiles=(incompatible,))
    await harness.composition.start()
    try:
        params = _issued_create_params(harness, "command-static-mismatch")
        before = _store_counts(harness.database)
        project_before = tuple(sorted(path.name for path in tmp_path.iterdir()))

        rejected = await harness.composition.handle(
            operation="task.create",
            params=params,
            request_id="request-static-mismatch",
            session_id="session-1",
        )

        assert rejected.ok is False
        assert rejected.payload["error"]["reason"] == (
            "EXECUTOR_CAPABILITY_UNAVAILABLE"
        )
        assert rejected.payload["error"]["code"] == "CAPABILITY_UNAVAILABLE"
        assert _store_counts(harness.database) == before
        assert harness.executor.dispatches == []
        assert harness.executor.cancels == []
        assert tuple(sorted(path.name for path in tmp_path.iterdir())) == project_before
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_product_retry_reuses_persisted_selection_after_profile_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catches retry reselecting from a changed process capability profile."""

    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.task_store.utc_now",
        lambda: NOW,
    )
    profile = DirectProjectCodeExecutorAdapter.capability_profile()
    harness = _harness(tmp_path, executor_profiles=(profile,))
    await harness.composition.start()
    try:
        task_id = await _terminal_task(harness)
        predecessor = harness.composition._core.store.get_task(task_id, _scope())
        frozen = harness.composition._core.store.get_attempt(
            predecessor.attempt_id
        ).selection
        assert frozen is not None

        changed_profile = replace(
            profile,
            profile_id="live-voice.direct-project-code.d0.v2",
        )
        harness.composition._executor_profiles = (changed_profile,)
        retried = await _apply_retry(
            harness,
            task_id,
            command_id="command-selected-retry",
        )

        successor = harness.composition._core.store.get_attempt(
            str(retried["attempt_id"])
        )
        assert successor.selection == frozen
        assert successor.selection.capability_profile_digest == profile.digest_sha256()
        assert successor.selection.capability_profile_digest != (
            changed_profile.digest_sha256()
        )
    finally:
        await harness.composition.stop()


@pytest.mark.parametrize(
    ("demo_policy", "fixture_enabled"), [("0", False), ("1", True)]
)
def test_factory_gates_itinerary_fixture_with_trusted_demo_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    demo_policy: str,
    fixture_enabled: bool,
) -> None:
    _configure_enabled_factory(monkeypatch, 3600)
    monkeypatch.setenv(
        "JIUWENSWARM_LIVE_VOICE_PRODUCT_DEMO_POLICY_BYPASS_ENABLED",
        demo_policy,
    )
    database = tmp_path / f"demo-policy-{demo_policy}.sqlite3"
    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.p3_authenticated_composition._resolve_database_path",
        lambda _configured: database,
    )

    composition = create_p3_composition_from_environment(
        agent_manager=object(), model_resolver=_ModelResolver()
    )

    assert composition is not None
    assert type(composition._core.executor) is DirectProjectCodeExecutorAdapter
    assert composition._core.executor._demo_itinerary_fixture_enabled is fixture_enabled


@pytest.mark.parametrize(
    ("demo_policy", "checkpoint_policy", "checkpoint_enabled"),
    [
        ("0", "0", False),
        ("0", "1", False),
        ("1", "0", False),
        ("1", "1", True),
    ],
)
def test_factory_gates_demo_adjustment_checkpoint_behind_both_flags(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    demo_policy: str,
    checkpoint_policy: str,
    checkpoint_enabled: bool,
) -> None:
    _configure_enabled_factory(monkeypatch, 3600)
    monkeypatch.setenv(
        "JIUWENSWARM_LIVE_VOICE_PRODUCT_DEMO_POLICY_BYPASS_ENABLED",
        demo_policy,
    )
    monkeypatch.setenv(
        "JIUWENSWARM_LIVE_VOICE_DEMO_ADJUSTMENT_CHECKPOINT_ENABLED",
        checkpoint_policy,
    )
    database = tmp_path / f"demo-checkpoint-{demo_policy}-{checkpoint_policy}.sqlite3"
    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.p3_authenticated_composition._resolve_database_path",
        lambda _configured: database,
    )

    composition = create_p3_composition_from_environment(
        agent_manager=object(), model_resolver=_ModelResolver()
    )

    assert composition is not None
    assert type(composition._core.executor) is DirectProjectCodeExecutorAdapter
    assert (
        composition._core.executor._demo_itinerary_adjustment_checkpoint_enabled
        is checkpoint_enabled
    )


@pytest.mark.asyncio
async def test_factory_direct_executor_lifecycle_releases_agent_bindings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_enabled_factory(monkeypatch, 3600)
    database = tmp_path / "direct-lifecycle.sqlite3"
    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.p3_authenticated_composition._resolve_database_path",
        lambda _configured: database,
    )

    class Manager:
        def __init__(self) -> None:
            self.cleanup_calls = 0

        async def cleanup_live_voice_formal_task_agents(self) -> None:
            self.cleanup_calls += 1

    manager = Manager()
    confirmation_verifier = SqliteP3ConfirmationLedger(database)
    composition = create_p3_composition_from_environment(
        agent_manager=manager,
        model_resolver=_ModelResolver(),
        confirmation_verifier=confirmation_verifier,
    )

    assert composition is not None
    await composition.start()
    backend = BoundedInMemoryOtelBackend(capacity=7)
    configuration = composition.validated_live_voice_configuration(
        provider=backend.validated_provider_configuration()
    )
    assert configuration.executor is not None
    assert configuration.executor.durability_level is DurabilityLevel.D2
    assert set(configuration.capabilities) == {
        LiveVoiceCapability.AUTHENTICATED,
        LiveVoiceCapability.EXECUTOR_D2,
        LiveVoiceCapability.FORMAL_WEB,
        LiveVoiceCapability.TASK_MUTATION,
        LiveVoiceCapability.TASK_QUERY,
        LiveVoiceCapability.TELEMETRY_EXPORT,
    }
    assert backend.health().state.value == "created"
    assert backend.health().accepted == 0
    await composition.stop()
    await composition.stop()

    assert type(composition._core.executor) is DirectProjectCodeExecutorAdapter
    assert manager.cleanup_calls == 1


@pytest.mark.asyncio
async def test_stop_phases_direct_status_settlement_before_binding_release() -> None:
    events: list[str] = []

    class Direct:
        has_live_workers = False

        async def prepare_startup(self) -> int:
            events.append("executor.prepare")
            return 0

        async def close(self, *, interrupt_running: bool) -> None:
            assert interrupt_running is True
            events.append("executor.close")

    class Binding:
        async def close(self) -> None:
            events.append("binding.close")

    class Core:
        async def reconcile(self):
            events.append("core.reconcile")
            return {}

        async def reconcile_status(self):
            events.append("core.reconcile_status")
            return {
                "known": 1,
                "unavailable": 0,
                "lost": 0,
                "superseded": 0,
            }

    runtime_owner = _DirectP3RuntimeOwner(
        executor=Direct(),  # type: ignore[arg-type]
        binding_resolver=Binding(),  # type: ignore[arg-type]
    )
    composition = P3AuthenticatedComposition(
        authenticator=StaticBearerAuthenticator(token=TOKEN, principal=_principal()),
        authority_resolver=_AuthorityResolver({}),
        core=Core(),  # type: ignore[arg-type]
        binding_resolver=runtime_owner,
        reconcile_interval=3600,
        clock=lambda: NOW,
    )

    await composition.start()
    await composition.stop()
    await composition.stop()

    assert events == [
        "executor.prepare",
        "core.reconcile",
        "core.reconcile",  # final generic outbox drain while carrier is open
        "executor.close",
        "core.reconcile_status",
        "binding.close",
    ]


@pytest.mark.asyncio
async def test_stop_retains_direct_owner_until_status_settlement_retries() -> None:
    status_summaries = [
        {
            "known": 0,
            "unavailable": 1,
            "lost": 0,
            "superseded": 0,
        },
        {
            "known": 1,
            "unavailable": 0,
            "lost": 0,
            "superseded": 0,
        },
    ]
    direct_close_calls = binding_close_calls = status_calls = 0

    class Direct:
        has_live_workers = False

        async def prepare_startup(self) -> int:
            return 0

        async def close(self, *, interrupt_running: bool) -> None:
            nonlocal direct_close_calls
            assert interrupt_running is True
            direct_close_calls += 1

    class Binding:
        async def close(self) -> None:
            nonlocal binding_close_calls
            binding_close_calls += 1

    class Core:
        async def reconcile(self):
            return {}

        async def reconcile_status(self):
            nonlocal status_calls
            status_calls += 1
            return status_summaries.pop(0)

    runtime_owner = _DirectP3RuntimeOwner(
        executor=Direct(),  # type: ignore[arg-type]
        binding_resolver=Binding(),  # type: ignore[arg-type]
    )
    composition = P3AuthenticatedComposition(
        authenticator=StaticBearerAuthenticator(token=TOKEN, principal=_principal()),
        authority_resolver=_AuthorityResolver({}),
        core=Core(),  # type: ignore[arg-type]
        binding_resolver=runtime_owner,
        reconcile_interval=3600,
        clock=lambda: NOW,
    )
    await composition.start()

    with pytest.raises(FormalTaskViolation) as pending:
        await composition.stop()

    assert pending.value.reason == "EXECUTOR_CLOSE_CLEANUP_PENDING"
    assert direct_close_calls == 1
    assert status_calls == 1
    assert binding_close_calls == 0

    await composition.stop()
    await composition.stop()

    assert direct_close_calls == 2
    assert status_calls == 2
    assert binding_close_calls == 1


@pytest.mark.asyncio
async def test_stop_retains_direct_owner_when_executor_cleanup_is_pending() -> None:
    cleanup_pending = True
    direct_close_calls = binding_close_calls = status_calls = 0

    class Direct:
        @property
        def has_live_workers(self) -> bool:
            return cleanup_pending

        async def prepare_startup(self) -> int:
            return 0

        async def close(self, *, interrupt_running: bool) -> None:
            nonlocal direct_close_calls
            assert interrupt_running is True
            direct_close_calls += 1

    class Binding:
        async def close(self) -> None:
            nonlocal binding_close_calls
            binding_close_calls += 1

    class Core:
        async def reconcile(self):
            return {}

        async def reconcile_status(self):
            nonlocal status_calls
            status_calls += 1
            return {
                "known": 1,
                "unavailable": 0,
                "lost": 0,
                "superseded": 0,
            }

    runtime_owner = _DirectP3RuntimeOwner(
        executor=Direct(),  # type: ignore[arg-type]
        binding_resolver=Binding(),  # type: ignore[arg-type]
    )
    composition = P3AuthenticatedComposition(
        authenticator=StaticBearerAuthenticator(token=TOKEN, principal=_principal()),
        authority_resolver=_AuthorityResolver({}),
        core=Core(),  # type: ignore[arg-type]
        binding_resolver=runtime_owner,
        reconcile_interval=3600,
        clock=lambda: NOW,
    )
    await composition.start()

    with pytest.raises(FormalTaskViolation) as pending:
        await composition.stop()

    assert pending.value.reason == "EXECUTOR_CLOSE_CLEANUP_PENDING"
    assert direct_close_calls == 1
    assert status_calls == 0
    assert binding_close_calls == 0

    cleanup_pending = False
    await composition.stop()

    assert direct_close_calls == 2
    assert status_calls == 1
    assert binding_close_calls == 1


@pytest.mark.asyncio
async def test_stop_settles_direct_interruption_into_canonical_store(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.task_store.utc_now",
        lambda: NOW,
    )
    project = tmp_path / "project"
    project.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    (project / "tracked.txt").write_text("clean\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=project, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=P3 Test",
            "-c",
            "user.email=p3@example.invalid",
            "commit",
            "-qm",
            "seed",
        ],
        cwd=project,
        check=True,
    )

    class BlockingProjectExecutor:
        def __init__(self) -> None:
            self.started = asyncio.Event()

        async def process_background_code_task_stream(self, _request):
            self.started.set()
            await asyncio.Event().wait()
            if False:
                yield None

    class Resolver:
        def __init__(self, binding: ProjectExecutionBinding) -> None:
            self.binding = binding
            self.close_calls = 0

        async def resolve(self, _spec, *, for_dispatch: bool):
            assert for_dispatch is True
            return self.binding

        async def close(self) -> None:
            self.close_calls += 1

    async def dispatch_fence() -> None:
        return None

    releases: list[str] = []
    blocking_agent = BlockingProjectExecutor()
    binding = ProjectExecutionBinding(
        service=None,
        execution_agent=object(),
        project_executor=blocking_agent,
        effective_execution_root=str(project.resolve()),
        execution_target={
            "project_dir": str(project.resolve()),
            "project_id": "project-1",
            "origin_session_id": "session-1",
            "origin_channel_id": "web",
        },
        owner_scope={
            "channel_id": "formal-task-core",
            "session_id": "session-1",
            "app_id": "live-voice",
        },
        resolved_revision_kind="version",
        resolved_revision_value="a77516a0",
        model_identity="default#0",
        model_config_version="catalog-v1",
        context_release=lambda: releases.append("released"),
        dispatch_fence=dispatch_fence,
    )
    resolver = Resolver(binding)
    database = tmp_path / "shutdown-settlement.sqlite3"
    direct = DirectProjectCodeExecutorAdapter(
        resolver,
        database,
        clock=lambda: NOW,
        heartbeat_interval=60,
        attempt_timeout=300,
    )
    runtime_owner = _DirectP3RuntimeOwner(
        executor=direct,
        binding_resolver=resolver,  # type: ignore[arg-type]
    )
    authority = _AuthorityResolver({"session-1": _context(project)})
    confirmations = SqliteP3ConfirmationLedger(database)
    models = _ModelResolver()
    store = SqliteTaskStore(database)
    composition = P3AuthenticatedComposition(
        authenticator=StaticBearerAuthenticator(token=TOKEN, principal=_principal()),
        authority_resolver=authority,
        core=PersistentTaskCore(store, direct),
        confirmation_verifier=confirmations,
        model_resolver=models,
        binding_resolver=runtime_owner,
        telemetry=_Telemetry(),
        policy=FormalTaskPolicyAdapter(),
        reconcile_interval=3600,
        clock=lambda: NOW,
        executor_profiles=(direct.capability_profile(),),
    )
    harness = _Harness(
        composition,
        database,
        direct,  # type: ignore[arg-type]
        authority,
        runtime_owner,  # type: ignore[arg-type]
        _Telemetry(),
        confirmations,
        models,
    )

    await composition.start()
    created = await composition.handle(
        operation="task.create",
        params=_issued_create_params(harness, "command-shutdown-interruption"),
        request_id="request-shutdown-interruption",
        session_id="session-1",
    )
    assert created.ok is True
    task_id = str(created.payload["result"]["task_id"])
    attempt_id = str(created.payload["result"]["attempt_id"])
    await composition.reconcile_once()
    await asyncio.wait_for(blocking_agent.started.wait(), timeout=2)

    await composition.stop()

    direct_record = direct._journal.get(attempt_id)
    assert direct_record is not None
    assert direct_record.state is FormalAttemptState.TERMINAL
    assert direct_record.outcome is TerminalOutcome.INTERRUPTED
    task = store.get_task(task_id, _scope())
    attempt = store.get_attempt(attempt_id)
    assert task.state is FormalTaskState.TERMINAL
    assert task.outcome is TerminalOutcome.INTERRUPTED
    assert task.reconciliation_state is None
    assert task.reconciliation_reason is None
    assert attempt.state is FormalAttemptState.TERMINAL
    assert attempt.outcome is TerminalOutcome.INTERRUPTED
    assert direct.has_live_workers is False
    assert releases == ["released"]
    assert resolver.close_calls == 1


@pytest.mark.parametrize(
    ("master_enabled", "p2_enabled", "authorized"),
    [(False, True, False), (True, False, False), (True, True, True)],
)
def test_factory_widens_alpha_principal_to_p2_only_behind_both_product_flags(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    master_enabled: bool,
    p2_enabled: bool,
    authorized: bool,
) -> None:
    _configure_enabled_factory(monkeypatch, 3600)
    monkeypatch.setenv(
        "JIUWENSWARM_LIVE_VOICE_PRODUCT_COMPOSITION_ENABLED",
        "1" if master_enabled else "0",
    )
    monkeypatch.setenv(
        "JIUWENSWARM_LIVE_VOICE_PRODUCT_P2_ENABLED",
        "1" if p2_enabled else "0",
    )
    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.p3_authenticated_composition._resolve_database_path",
        lambda _configured: tmp_path / "product-p2-authority.sqlite3",
    )
    composition = create_p3_composition_from_environment(
        agent_manager=object(), model_resolver=_ModelResolver()
    )
    assert composition is not None

    if authorized:
        principal = composition._authenticator.authenticate(
            TOKEN, operation="agent.chat", now=NOW
        )
        assert principal.allowed_operations >= frozenset({"agent.chat"})
    else:
        with pytest.raises(FormalTaskViolation) as denied:
            composition._authenticator.authenticate(
                TOKEN, operation="agent.chat", now=NOW
            )
        assert denied.value.reason == "FORMAL_TASK_AUTHORIZATION_DENIED"


def test_incomplete_enabled_gate_fails_before_store_or_carrier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "must-not-exist.sqlite3"
    monkeypatch.setenv("JIUWENSWARM_LIVE_VOICE_P3_ENABLED", "1")
    monkeypatch.setenv("JIUWENSWARM_LIVE_VOICE_P3_DATABASE", str(database))
    monkeypatch.delenv("JIUWENSWARM_LIVE_VOICE_P3_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("JIUWENSWARM_LIVE_VOICE_P3_PRINCIPAL_ID", raising=False)
    monkeypatch.delenv("JIUWENSWARM_LIVE_VOICE_P3_PROJECT_IDS", raising=False)
    monkeypatch.delenv("JIUWENSWARM_LIVE_VOICE_P3_AUTH_EXPIRES_AT", raising=False)

    with pytest.raises(FormalTaskViolation) as raised:
        create_p3_composition_from_environment(
            agent_manager=object(), model_resolver=lambda _name: None
        )

    assert raised.value.reason == "INVALID_P3_AUTH_CONFIGURATION"
    assert not database.exists()


def test_enabled_gate_rejects_store_artifact_outside_application_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "target-project" / "formal-tasks.sqlite3"
    monkeypatch.setenv("JIUWENSWARM_LIVE_VOICE_P3_ENABLED", "1")
    monkeypatch.setenv("JIUWENSWARM_LIVE_VOICE_P3_AUTH_TOKEN", TOKEN)
    monkeypatch.setenv("JIUWENSWARM_LIVE_VOICE_P3_PRINCIPAL_ID", "user-1")
    monkeypatch.setenv("JIUWENSWARM_LIVE_VOICE_P3_PROJECT_IDS", "project-1")
    monkeypatch.setenv(
        "JIUWENSWARM_LIVE_VOICE_P3_AUTH_EXPIRES_AT", "2100-01-01T00:00:00Z"
    )
    monkeypatch.setenv(
        "JIUWENSWARM_LIVE_VOICE_P3_EXECUTOR_PROFILE",
        "live-voice.direct-project-code.d2.v1",
    )
    monkeypatch.setenv("JIUWENSWARM_LIVE_VOICE_P3_DATABASE", str(database))

    with pytest.raises(FormalTaskViolation) as raised:
        create_p3_composition_from_environment(
            agent_manager=object(), model_resolver=lambda _name: None
        )

    assert raised.value.reason == "INVALID_P3_AUTH_CONFIGURATION"
    assert not database.exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows junction regression")
@pytest.mark.parametrize("junction_level", ["live_voice", "p3alpha"])
def test_database_resolver_rejects_existing_windows_store_junction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    junction_level: str,
) -> None:
    data_root = tmp_path / f"data-{junction_level}"
    data_root.mkdir()
    outside = tmp_path / f"outside-{junction_level}"
    outside.mkdir()
    live_voice = data_root / "live_voice"
    if junction_level == "live_voice":
        junction = live_voice
        outside_database = outside / "p3alpha" / "must-not-exist.sqlite3"
    else:
        live_voice.mkdir()
        junction = live_voice / "p3alpha"
        outside_database = outside / "must-not-exist.sqlite3"
    created = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "New-Item -ItemType Junction -Path $env:JUNCTION_PATH "
            "-Target $env:JUNCTION_TARGET | Out-Null",
        ],
        check=False,
        capture_output=True,
        env={
            **os.environ,
            "JUNCTION_PATH": str(junction),
            "JUNCTION_TARGET": str(outside),
        },
    )
    assert created.returncode == 0
    configured = data_root / "live_voice" / "p3alpha" / "must-not-exist.sqlite3"
    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.p3_authenticated_composition."
        "get_user_workspace_dir",
        lambda: data_root,
    )

    violation = None
    try:
        resolved = _resolve_database_path(str(configured))
        SqliteTaskStore(resolved)
    except FormalTaskViolation as exc:
        violation = exc

    assert not outside_database.exists()
    assert violation is not None
    assert violation.reason == "INVALID_P3_AUTH_CONFIGURATION"


def test_server_resolver_checks_allow_list_before_project_storage(
    tmp_path: Path,
) -> None:
    project_calls: list[str] = []

    def project_reader(project_id: str):
        project_calls.append(project_id)
        return SimpleNamespace(
            project_id=project_id,
            project_dir=str(tmp_path),
            hidden=False,
            work_mode="code",
        )

    resolver = ServerSessionProjectAuthorityResolver(
        session_reader=lambda _session_id: {
            "project_id": "project-1",
            "project_dir": str(tmp_path),
        },
        project_reader=project_reader,
        revision_reader=lambda project_dir: (project_dir, "a77516a0"),
        worktree_clean_reader=lambda _project_dir: True,
    )
    denied = replace(_principal(), allowed_project_ids=frozenset({"project-2"}))

    with pytest.raises(FormalTaskViolation) as raised:
        resolver.resolve(denied, session_id="session-1", now=NOW, require_clean=False)

    assert raised.value.reason == "FORMAL_TASK_AUTHORIZATION_DENIED"
    assert project_calls == []

    resolved = resolver.resolve(
        _principal(), session_id="session-1", now=NOW, require_clean=False
    )
    assert resolved.scope == _scope()
    assert resolved.context.revision_value == "a77516a0"
    assert project_calls == ["project-1"]


def test_server_resolver_rejects_false_clean_reader_result(tmp_path: Path) -> None:
    resolver = ServerSessionProjectAuthorityResolver(
        session_reader=lambda _session_id: {
            "project_id": "project-1",
            "project_dir": str(tmp_path),
        },
        project_reader=lambda project_id: SimpleNamespace(
            project_id=project_id,
            project_dir=str(tmp_path),
            hidden=False,
            work_mode="code",
        ),
        revision_reader=lambda project_dir: (project_dir, "a77516a0"),
        worktree_clean_reader=lambda _project_dir: False,
    )

    with pytest.raises(FormalTaskViolation) as raised:
        resolver.resolve(
            _principal(), session_id="session-1", now=NOW, require_clean=True
        )

    assert raised.value.reason == "TASK_CONTEXT_WORKTREE_DIRTY"


def test_server_resolver_accepts_only_exact_scope_managed_worktree(
    tmp_path: Path,
) -> None:
    observed: list[tuple[str, ScopeRef]] = []

    def managed(project_dir: str, scope: ScopeRef) -> bool:
        observed.append((project_dir, scope))
        return scope == _scope()

    resolver = ServerSessionProjectAuthorityResolver(
        session_reader=lambda _session_id: {
            "project_id": "project-1",
            "project_dir": str(tmp_path),
        },
        project_reader=lambda project_id: SimpleNamespace(
            project_id=project_id,
            project_dir=str(tmp_path),
            hidden=False,
            work_mode="code",
        ),
        revision_reader=lambda project_dir: (project_dir, "a77516a0"),
        worktree_clean_reader=lambda _project_dir: False,
        managed_worktree_reader=managed,
    )

    resolved = resolver.resolve(
        _principal(), session_id="session-1", now=NOW, require_clean=True
    )

    assert resolved.scope == _scope()
    assert observed == [(str(tmp_path), _scope())]


def test_persisted_context_revalidation_uses_current_grant_expiry_and_redaction(
    tmp_path: Path,
) -> None:
    redacted = False

    def redaction_reader(_session, _project):
        return redacted, (("secret",) if redacted else ())

    resolver = ServerSessionProjectAuthorityResolver(
        session_reader=lambda _session_id: {
            "project_id": "project-1",
            "project_dir": str(tmp_path),
        },
        project_reader=lambda project_id: SimpleNamespace(
            project_id=project_id,
            project_dir=str(tmp_path),
            hidden=False,
            work_mode="code",
        ),
        revision_reader=lambda project_dir: (project_dir, "a77516a0"),
        worktree_clean_reader=lambda _project_dir: True,
        redaction_reader=redaction_reader,
    )
    context = _context(tmp_path)

    assert (
        resolver.revalidate(
            context,
            principal=_principal(),
            now=NOW,
            for_dispatch=True,
        ).project_id
        == "project-1"
    )

    persisted_redacted = replace(
        context,
        redacted=True,
        redacted_fields=("persisted-secret",),
    )
    with pytest.raises(FormalTaskViolation) as persisted_hidden:
        resolver.revalidate(
            persisted_redacted,
            principal=_principal(),
            now=NOW,
            for_dispatch=True,
        )
    assert persisted_hidden.value.reason == "TASK_CONTEXT_REDACTED"

    revoked = replace(_principal(), allowed_project_ids=frozenset({"project-2"}))
    with pytest.raises(FormalTaskViolation) as denied:
        resolver.revalidate(context, principal=revoked, now=NOW, for_dispatch=True)
    assert denied.value.reason == "FORMAL_TASK_AUTHORIZATION_DENIED"

    expired = replace(_principal(), expires_at="2026-08-05T11:59:59Z")
    with pytest.raises(FormalTaskViolation) as expiry:
        resolver.revalidate(context, principal=expired, now=NOW, for_dispatch=True)
    assert expiry.value.reason == "FORMAL_TASK_AUTHORIZATION_EXPIRED"

    redacted = True
    with pytest.raises(FormalTaskViolation) as hidden:
        resolver.revalidate(context, principal=_principal(), now=NOW, for_dispatch=True)
    assert hidden.value.reason == "TASK_CONTEXT_REDACTED"


def test_default_server_revision_preserves_dirty_worktree_reason(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    (project / "tracked.txt").write_text("clean\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=project, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=P3 Test",
            "-c",
            "user.email=p3@example.invalid",
            "commit",
            "-qm",
            "seed",
        ],
        cwd=project,
        check=True,
    )
    resolver = ServerSessionProjectAuthorityResolver(
        session_reader=lambda _session_id: {
            "project_id": "project-1",
            "project_dir": str(project),
        },
        project_reader=lambda project_id: SimpleNamespace(
            project_id=project_id,
            project_dir=str(project),
            hidden=False,
            work_mode="code",
        ),
    )
    clean_context = resolver.resolve(
        _principal(), session_id="session-1", now=NOW, require_clean=True
    ).context
    (project / "untracked.txt").write_text("dirty\n", encoding="utf-8")

    with pytest.raises(FormalTaskViolation) as raised:
        resolver.resolve(
            _principal(), session_id="session-1", now=NOW, require_clean=True
        )

    # Authentication and the exact project allow-list were already verified,
    # so the D-069 retry contract keeps the server-derived Context reason.
    assert raised.value.reason == "TASK_CONTEXT_WORKTREE_DIRTY"
    assert (
        resolver.revalidate(
            clean_context,
            principal=_principal(),
            now=NOW,
            for_dispatch=False,
        ).project_id
        == "project-1"
    )
    with pytest.raises(FormalTaskViolation) as dispatch:
        resolver.revalidate(
            clean_context,
            principal=_principal(),
            now=NOW,
            for_dispatch=True,
        )
    assert dispatch.value.reason == "TASK_CONTEXT_WORKTREE_DIRTY"


@pytest.mark.asyncio
async def test_route_resolves_blocking_authority_off_event_loop(tmp_path: Path) -> None:
    main_thread = threading.get_ident()
    authority = _AuthorityResolver({"session-1": _context(tmp_path)})
    original_resolve = authority.resolve

    def resolve(*args, **kwargs):
        assert threading.get_ident() != main_thread
        return original_resolve(*args, **kwargs)

    authority.resolve = resolve  # type: ignore[method-assign]
    harness = _harness(tmp_path)
    harness.composition._authority_resolver = authority
    await harness.composition.start()
    try:
        result = await harness.composition.handle(
            operation="task.list",
            params=_base(),
            request_id="request-threaded-authority",
            session_id="session-1",
        )
    finally:
        await harness.composition.stop()

    assert result.ok is True


@pytest.mark.asyncio
async def test_non_dispatch_binding_has_no_agent_or_model_side_effects(
    tmp_path: Path,
) -> None:
    class Authority:
        def revalidate(self, _context, **_kwargs):
            return SimpleNamespace(
                project_dir=str(tmp_path),
                project_id="project-1",
                session_id="session-1",
                revision="a77516a0",
            )

    class Manager:
        async def get_live_voice_formal_task_agent(self, _project_dir: str):
            raise AssertionError("non-dispatch binding must not create an Agent")

    models = _ModelResolver()
    resolver = AgentManagerProjectBindingResolver(
        authority_resolver=Authority(),
        agent_manager=Manager(),
        service=object(),
        model_resolver=models,
        principal=_principal(),
        clock=lambda: NOW,
    )

    binding = await resolver.resolve(
        SimpleNamespace(
            context=object(),
            attributes=(
                ("model_identity", "demo#0"),
                ("model_config_version", "catalog-demo"),
            ),
        ),
        for_dispatch=False,
    )

    assert binding.model is None
    assert binding.model_identity == "demo#0"
    assert binding.model_config_version == "catalog-demo"
    assert binding.execution_agent is None
    assert binding.project_executor is None
    assert models.calls == []


@pytest.mark.asyncio
async def test_dirty_dispatch_fails_before_model_agent_or_carrier(
    tmp_path: Path,
) -> None:
    class Authority:
        def revalidate(self, _context, **kwargs):
            assert kwargs["for_dispatch"] is True
            raise FormalTaskViolation(
                "TASK_CONTEXT_WORKTREE_DIRTY",
                "formal task project must have a clean worktree",
                ErrorCode.PERMISSION_DENIED,
            )

    class Manager:
        async def get_live_voice_formal_task_agent(self, _project_dir: str):
            raise AssertionError("dirty dispatch must fail before Agent creation")

    class Models:
        def resolve(self, *_args, **_kwargs):
            raise AssertionError("dirty dispatch must fail before model resolution")

    resolver = AgentManagerProjectBindingResolver(
        authority_resolver=Authority(),
        agent_manager=Manager(),
        service=object(),
        model_resolver=Models(),
        principal=_principal(),
        clock=lambda: NOW,
    )
    spec = SimpleNamespace(
        context=object(),
        attributes=(
            ("model_identity", "default#0"),
            ("model_config_version", "catalog-v1"),
        ),
    )

    with pytest.raises(FormalTaskViolation) as raised:
        await resolver.resolve(spec, for_dispatch=True)

    assert raised.value.reason == "TASK_CONTEXT_WORKTREE_DIRTY"


@pytest.mark.asyncio
async def test_dispatch_handoff_fence_rechecks_clean_state_after_agent_setup(
    tmp_path: Path,
) -> None:
    class Authority:
        def __init__(self) -> None:
            self.calls = 0

        def revalidate(self, _context, **kwargs):
            assert kwargs["for_dispatch"] is True
            self.calls += 1
            if self.calls == 2:
                raise FormalTaskViolation(
                    "TASK_CONTEXT_WORKTREE_DIRTY",
                    "formal task project became dirty before handoff",
                    ErrorCode.PERMISSION_DENIED,
                )
            return SimpleNamespace(
                project_dir=str(tmp_path),
                project_id="project-1",
                session_id="session-1",
                revision="a77516a0",
            )

    class Agent:
        def get_project_execution_root(self) -> str:
            return str(tmp_path)

        def get_instance(self):
            return object()

        async def ensure_instance(self):
            # A formal dispatch runs outside the chat path and awaits
            # this rather than reading the bare accessor.
            return object()

        async def process_background_code_task_stream(self):
            return None

    class Manager:
        def __init__(self) -> None:
            self.agent = Agent()
            self.pins = 0
            self.unpins = 0

        async def get_live_voice_formal_task_agent(self, _project_dir: str):
            return self.agent

        def pin_agent(self, _agent) -> None:
            self.pins += 1

        def unpin_agent(self, _agent) -> None:
            self.unpins += 1

    authority = Authority()
    manager = Manager()
    resolver = AgentManagerProjectBindingResolver(
        authority_resolver=authority,
        agent_manager=manager,
        service=object(),
        model_resolver=_ModelResolver(),
        principal=_principal(),
        clock=lambda: NOW,
    )
    binding = await resolver.resolve(
        SimpleNamespace(
            context=object(),
            attributes=(
                ("model_identity", "default#0"),
                ("model_config_version", "catalog-v1"),
            ),
        ),
        for_dispatch=True,
    )

    assert binding.dispatch_fence is not None
    with pytest.raises(FormalTaskViolation) as raised:
        await binding.dispatch_fence()
    assert raised.value.reason == "TASK_CONTEXT_WORKTREE_DIRTY"
    assert authority.calls == 2
    assert manager.pins == 1
    assert binding.context_release is not None
    binding.context_release()
    assert manager.unpins == 1


@pytest.mark.asyncio
async def test_unknown_model_fails_before_store_executor_or_agent(
    tmp_path: Path,
) -> None:
    harness = _harness(tmp_path)
    await harness.composition.start()
    before = _store_counts(harness.database)
    try:
        result = await harness.composition.handle(
            operation="task.create",
            params={**_create_params(), "model_intent": "missing-model"},
            request_id="request-unknown-model",
            session_id="session-1",
        )
        await asyncio.sleep(0)
        assert result.payload["error"]["reason"] == "P3_MODEL_INTENT_UNKNOWN"
        assert _store_counts(harness.database) == before
        assert harness.executor.dispatches == []
        assert harness.executor.cancels == []
    finally:
        await harness.composition.stop()


def test_exact_model_catalog_rejects_unknown_and_ambiguous_without_building() -> None:
    build_calls: list[str] = []

    def build_model(client, _config):
        build_calls.append(str(client["model_name"]))
        return object()

    catalog = [
        {
            "model_client_config": {"model_name": "same"},
            "model_config_obj": {"temperature": 0.1},
            "is_default": True,
        },
        {
            "model_client_config": {"model_name": "same"},
            "model_config_obj": {"temperature": 0.2},
        },
    ]
    resolver = ServerModelCatalogResolver(
        catalog_reader=lambda: catalog,
        model_builder=build_model,
    )

    with pytest.raises(FormalTaskViolation) as unknown:
        resolver.resolve("missing")
    with pytest.raises(FormalTaskViolation) as ambiguous:
        resolver.resolve("same")

    assert unknown.value.reason == "P3_MODEL_INTENT_UNKNOWN"
    assert ambiguous.value.reason == "P3_MODEL_INTENT_AMBIGUOUS"
    assert build_calls == []

    metadata = resolver.resolve("same#0")
    resolved = resolver.resolve(
        metadata.identity,
        expected_identity=metadata.identity,
        expected_config_version=metadata.config_version,
        instantiate=True,
    )
    assert metadata.model is None
    assert resolved.model is not None
    assert build_calls == ["same"]


def test_multi_model_catalog_uses_first_server_model_group_default() -> None:
    catalog = [
        {
            "model_client_config": {"model_name": "alpha", "variant": "secondary"},
            "is_default": False,
        },
        {
            "model_client_config": {"model_name": "alpha", "variant": "primary"},
            "is_default": True,
        },
        {
            "model_client_config": {"model_name": "beta"},
            "is_default": True,
        },
    ]
    resolver = ServerModelCatalogResolver(
        catalog_reader=lambda: catalog,
        model_builder=lambda client, _config: dict(client),
    )

    resolved = resolver.resolve(None, instantiate=True)

    assert resolved.identity == "alpha#1"
    assert resolved.model == {"model_name": "alpha", "variant": "primary"}


@pytest.mark.asyncio
@pytest.mark.parametrize("drift_kind", ["default", "config"])
async def test_default_change_and_model_config_drift_fail_before_agent_or_carrier(
    tmp_path: Path,
    drift_kind: str,
) -> None:
    catalog = [
        {
            "model_client_config": {"model_name": "alpha"},
            "model_config_obj": {"temperature": 0.1},
            "is_default": True,
        },
        {
            "model_client_config": {"model_name": "beta"},
            "model_config_obj": {"temperature": 0.2},
        },
    ]
    model_builds: list[str] = []

    def build_model(client, config):
        model_builds.append(str(client["model_name"]))
        return dict(client), dict(config)

    resolver = ServerModelCatalogResolver(
        catalog_reader=lambda: catalog,
        model_builder=build_model,
    )
    admitted = resolver.resolve(None)
    if drift_kind == "default":
        catalog[0]["is_default"] = False
        catalog[1]["is_default"] = True
    else:
        catalog[0]["model_config_obj"] = {"temperature": 0.9}

    class Authority:
        def revalidate(self, _context, **_kwargs):
            return SimpleNamespace(
                project_dir=str(tmp_path),
                project_id="project-1",
                session_id="session-1",
                revision="a77516a0",
            )

    class Manager:
        async def get_live_voice_formal_task_agent(self, _project_dir: str):
            raise AssertionError("model drift must fail before Agent creation")

    binding_resolver = AgentManagerProjectBindingResolver(
        authority_resolver=Authority(),
        agent_manager=Manager(),
        service=object(),
        model_resolver=resolver,
        principal=_principal(),
        clock=lambda: NOW,
    )
    spec = SimpleNamespace(
        context=object(),
        attributes=(
            ("model_identity", admitted.identity),
            ("model_config_version", admitted.config_version),
        ),
    )

    with pytest.raises(FormalTaskViolation) as drift:
        await binding_resolver.resolve(spec, for_dispatch=True)

    assert drift.value.reason == "EXECUTOR_MODEL_BINDING_DRIFT"
    assert model_builds == []


@pytest.mark.asyncio
async def test_binding_shutdown_releases_contexts_and_agents_after_scheduler_failure() -> (
    None
):
    class FailingService:
        def __init__(self) -> None:
            self.clear_calls = 0
            self.stop_calls = 0

        async def stop_scheduler(self, *, interrupt_running: bool = False) -> None:
            assert interrupt_running is True
            self.stop_calls += 1
            if self.stop_calls == 1:
                raise RuntimeError("scheduler stop failed")

        def clear_scheduled_task_execution_contexts(self) -> None:
            self.clear_calls += 1

    class Manager:
        def __init__(self) -> None:
            self.cleanup_calls = 0

        async def cleanup_live_voice_formal_task_agents(self) -> None:
            self.cleanup_calls += 1

    service = FailingService()
    manager = Manager()
    resolver = AgentManagerProjectBindingResolver(
        authority_resolver=ServerSessionProjectAuthorityResolver(
            session_reader=lambda _session_id: None
        ),
        agent_manager=manager,
        service=service,
        model_resolver=_ModelResolver(),
        principal=_principal(),
        clock=lambda: NOW,
    )

    with pytest.raises(
        RuntimeError,
        match="FORMAL_PROJECT_BINDING_CLEANUP_PENDING",
    ):
        await resolver.close()
    assert resolver._closed is False
    assert resolver._close_requested is True
    assert service.stop_calls == 1
    assert service.clear_calls == 1
    assert manager.cleanup_calls == 1

    await resolver.close()
    await resolver.close()

    assert resolver._closed is True
    assert service.stop_calls == 2
    assert service.clear_calls == 1
    assert manager.cleanup_calls == 2


# --- D-069 bounded same-task task.retry product reachability -----------------


def _retry_params(
    task_id: str,
    *,
    command_id: str = "command-retry",
    session_id: str = "session-1",
    correlation_id: str | None = None,
) -> dict[str, object]:
    return {
        **_base(session_id),
        "command_id": command_id,
        "confirmation_id": f"forged:{command_id}",
        "issued_at": NOW,
        "correlation_id": correlation_id or f"correlation:{command_id}",
        "task_id": task_id,
    }


async def _issued_retry_params(
    harness: _Harness,
    params: dict[str, object],
    *,
    expires_at: str = EXPIRY,
    now: str = NOW,
) -> dict[str, object]:
    """Issue the exact confirmation the production issue route would freeze."""

    prepared = await harness.composition.prepare_mutation_confirmation(
        operation="task.retry",
        params=params,
        session_id=str(params["session_id"]),
    )
    params["confirmation_id"] = harness.confirmations.issue(
        prepared.binding, expires_at=expires_at, now=now
    )
    return params


def _outbox_snapshot(database: Path) -> tuple[tuple[object, ...], ...]:
    with sqlite3.connect(database) as connection:
        return tuple(
            tuple(row)
            for row in connection.execute(
                "SELECT outbox_id, kind, state, claimed_by FROM outbox"
                " ORDER BY outbox_id"
            ).fetchall()
        )


def _confirmation_count(database: Path) -> int:
    with sqlite3.connect(database) as connection:
        return int(
            connection.execute("SELECT COUNT(*) FROM p3_confirmations").fetchone()[0]
        )


async def _effects(harness: _Harness) -> tuple[object, ...]:
    """Every D-069 forbidden effect a rejection or replay must leave untouched.

    The snapshot is taken only once every durable delivery has settled so an
    earlier step's asynchronous tail can never be mistaken for a rejection's
    side effect.

    ``Executor.status`` is deliberately excluded.  An accepted mutation wakes
    the periodic reconciliation worker, whose status query is a read-only
    audit of an already dispatched attempt; the zero-effect oracle forbids
    ``dispatch``/``cancel``, not that audit.  Every mutating surface —
    task/spec/current-attempt rows, attempt/event/outbox/command rows, outbox
    claim state, Executor dispatch/cancel, retry readiness and binding
    resolver ownership — is covered here.
    """

    await _wait_until(
        lambda: all(
            row[2] not in {"pending", "claimed"}
            for row in _outbox_snapshot(harness.database)
        )
    )
    return (
        _store_counts(harness.database),
        _outbox_snapshot(harness.database),
        tuple(harness.executor.dispatches),
        tuple(harness.executor.cancels),
        tuple(harness.executor.readiness),
        harness.closer.calls,
    )


async def _cancel_current(harness: _Harness, task_id: str, *, command_id: str) -> None:
    params = _issue_confirmation(
        harness,
        {
            **_mutation_params(task_id),
            "command_id": command_id,
            "confirmation_id": f"forged:{command_id}",
            "correlation_id": f"correlation:{command_id}",
        },
        operation="task.cancel",
    )
    cancelled = await harness.composition.handle(
        operation="task.cancel",
        params=params,
        request_id=f"request-{command_id}",
        session_id="session-1",
    )
    assert cancelled.ok is True, cancelled.payload
    await _wait_until(
        lambda: (
            harness.composition._core.store.get_task(task_id, _scope()).state.value
            == "terminal"
        )
    )


async def _terminal_task(
    harness: _Harness,
    *,
    command_id: str = "command-create",
    cancel_command_id: str = "command-cancel",
    cancel: bool = True,
) -> str:
    """Drive one exact task to a terminal current attempt through the route."""

    created = await harness.composition.handle(
        operation="task.create",
        params=_issued_create_params(harness, command_id),
        request_id=f"request-{command_id}",
        session_id="session-1",
    )
    assert created.ok is True, created.payload
    task_id = str(created.payload["result"]["task_id"])
    await _wait_until(lambda: len(harness.executor.dispatches) >= 1)
    if cancel:
        await _cancel_current(harness, task_id, command_id=cancel_command_id)
    else:
        await _wait_until(
            lambda: (
                harness.composition._core.store.get_task(task_id, _scope()).state.value
                == "terminal"
            )
        )
    return task_id


@pytest.mark.asyncio
async def test_status_retry_admission_rejects_dirty_context_without_mutation(
    tmp_path: Path,
) -> None:
    harness = _harness(tmp_path)
    await harness.composition.start()
    try:
        task_id = await _terminal_task(harness)
        clean = await harness.composition.handle(
            operation="task.status",
            params={**_base(), "task_id": task_id},
            request_id="request-retry-admission-clean",
            session_id="session-1",
        )
        assert clean.ok is True, clean.payload
        attempt = clean.payload["result"]["attempt"]
        assert clean.payload["result"]["retry_admission"] == {
            "eligible": True,
            "reason": "TASK_RETRY_ELIGIBLE",
            "task_id": task_id,
            "attempt_id": attempt["attempt_id"],
            "attempt_number": attempt["attempt_number"] + 1,
        }
        assert (
            await harness.composition.read_product_status_retry_admission(
                bearer_token=TOKEN,
                session_id="session-1",
                task_id=task_id,
            )
            == clean.payload["result"]["retry_admission"]
        )

        counts = _store_counts(harness.database)
        dispatches = list(harness.executor.dispatches)
        confirmations = _confirmation_count(harness.database)
        harness.authority.dirty = True
        dirty = await harness.composition.handle(
            operation="task.status",
            params={**_base(), "task_id": task_id},
            request_id="request-retry-admission-dirty",
            session_id="session-1",
        )

        assert dirty.ok is True, dirty.payload
        assert dirty.payload["result"]["retry_admission"] == {
            "eligible": False,
            "reason": "TASK_CONTEXT_WORKTREE_DIRTY",
            "task_id": task_id,
            "attempt_id": None,
            "attempt_number": None,
        }
        assert (
            await harness.composition.read_product_status_retry_admission(
                bearer_token=TOKEN,
                session_id="session-1",
                task_id=task_id,
            )
            == dirty.payload["result"]["retry_admission"]
        )
        with pytest.raises(FormalTaskViolation) as invalid_bearer:
            await harness.composition.read_product_status_retry_admission(
                bearer_token="wrong-token",
                session_id="session-1",
                task_id=task_id,
            )
        assert invalid_bearer.value.reason == "FORMAL_TASK_AUTHENTICATION_REQUIRED"
        assert _store_counts(harness.database) == counts
        assert harness.executor.dispatches == dispatches
        assert _confirmation_count(harness.database) == confirmations
    finally:
        await harness.composition.stop()


async def _apply_retry(
    harness: _Harness, task_id: str, *, command_id: str
) -> dict[str, object]:
    params = await _issued_retry_params(
        harness, _retry_params(task_id, command_id=command_id)
    )
    applied = await harness.composition.handle(
        operation="task.retry",
        params=params,
        request_id=f"request-{command_id}",
        session_id="session-1",
    )
    assert applied.ok is True, applied.payload
    return dict(applied.payload["result"])


@pytest.mark.asyncio
async def test_retry_creates_one_successor_attempt_from_server_derived_lineage(
    tmp_path: Path,
) -> None:
    harness = _harness(tmp_path)
    await harness.composition.start()
    try:
        task_id = await _terminal_task(harness)
        predecessor = harness.composition._core.store.get_task(task_id, _scope())
        attempt_a = predecessor.attempt_id
        before = _store_counts(harness.database)

        result = await _apply_retry(harness, task_id, command_id="command-retry-b")

        assert result["task_id"] == task_id
        assert result["previous_attempt_id"] == attempt_a
        assert result["attempt_id"] != attempt_a
        assert result["attempt_number"] == 2
        assert result["applied"] is True
        assert result["state"] == "accepted"

        after = _store_counts(harness.database)
        # No new task row; exactly one new attempt, dispatch outbox row and
        # admission command.  The event count only grows further once the
        # successor is delivered, so it is bounded from below.
        assert after[0] == before[0]
        assert after[1] == before[1] + 1
        assert after[2] >= before[2] + 1
        assert after[3] == before[3] + 1
        assert after[4] == before[4] + 1

        # Executor readiness is proved only at Store apply, after confirmation.
        assert harness.executor.readiness == [(task_id, attempt_a)]

        current = harness.composition._core.store.get_task(task_id, _scope())
        assert current.attempt_id == result["attempt_id"]
        assert current.state.value == "accepted"
        assert current.outcome is None
        # The stable specification, executor and model binding are preserved.
        assert current.spec.name == predecessor.spec.name
        assert current.spec.instruction == predecessor.spec.instruction
        assert current.spec.executor_id == predecessor.spec.executor_id
        assert current.spec.attributes == predecessor.spec.attributes

        boundary = harness.composition._core.store.events(
            task_id, _scope(), after_seq=current.event_head - 1
        )[0]
        assert boundary.event_type == "task.retry_accepted"
        assert boundary.state == "accepted"
        assert boundary.outcome is None
        assert boundary.attempt_id == result["attempt_id"]
        assert boundary.details["retry_of_attempt_id"] == attempt_a
        assert boundary.details["previous_outcome"] == "cancelled"
        assert boundary.details["attempt_number"] == 2
        assert boundary.details["command_id"] == "command-retry-b"

        await _wait_until(lambda: result["attempt_id"] in harness.executor.dispatches)
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_applied_retry_replays_exactly_after_the_task_advanced(
    tmp_path: Path,
) -> None:
    harness = _harness(tmp_path)
    await harness.composition.start()
    try:
        task_id = await _terminal_task(harness)
        applied_params = await _issued_retry_params(
            harness, _retry_params(task_id, command_id="command-retry-b")
        )
        first_confirmation = str(applied_params["confirmation_id"])
        applied = await harness.composition.handle(
            operation="task.retry",
            params=applied_params,
            request_id="request-retry-b",
            session_id="session-1",
        )
        assert applied.ok is True, applied.payload
        original = dict(applied.payload["result"])
        await _wait_until(lambda: original["attempt_id"] in harness.executor.dispatches)
        before = await _effects(harness)

        # 1. Durable replay never bypasses confirmation.  The already consumed
        #    credential still verifies, because the ledger deliberately allows
        #    an exact single-use record to be replayed rather than re-issued,
        #    but it is not an entry point for a second attempt: the command
        #    ledger returns the same applied result with zero new effect.
        consumed_replay = await harness.composition.handle(
            operation="task.retry",
            params={
                **_retry_params(task_id, command_id="command-retry-b"),
                "confirmation_id": first_confirmation,
            },
            request_id="request-retry-b-consumed",
            session_id="session-1",
        )
        assert consumed_replay.ok is True, consumed_replay.payload
        assert consumed_replay.payload["result"] == original
        assert await _effects(harness) == before

        # An expired credential with an otherwise exact binding is refused, and
        # a forged binding is refused before expiry is even considered.
        exact = await harness.composition.prepare_mutation_confirmation(
            operation="task.retry",
            params=_retry_params(task_id, command_id="command-retry-b"),
            session_id="session-1",
        )
        stale_credentials = (
            (
                "expired",
                harness.confirmations.issue(
                    exact.binding,
                    expires_at="2026-08-05T11:30:00Z",
                    now="2026-08-05T11:00:00Z",
                ),
                "P3_CONFIRMATION_EXPIRED",
            ),
            (
                "forged",
                harness.confirmations.issue(
                    P3ConfirmationBinding(
                        principal_id="user-1",
                        scope=_scope(),
                        operation="task.retry",
                        command_id="command-retry-b",
                        target_task_id=task_id,
                        intent_fingerprint="forged-intent",
                    ),
                    expires_at=EXPIRY,
                    now=NOW,
                ),
                "P3_CONFIRMATION_BINDING_MISMATCH",
            ),
        )
        for label, stale, expected in stale_credentials:
            refused = await harness.composition.handle(
                operation="task.retry",
                params={
                    **_retry_params(task_id, command_id="command-retry-b"),
                    "confirmation_id": stale,
                },
                request_id=f"request-retry-b-{label}",
                session_id="session-1",
            )
            assert refused.ok is False, label
            assert refused.payload["error"]["reason"] == expected, label
            assert refused.payload["error"]["code"] == "PERMISSION_DENIED", label
            assert await _effects(harness) == before, label

        # 2. A reopened process re-issues its own confirmation because that
        #    ledger is single-use and short lived.  The new credential is
        #    normally issued, verified and consumed; the durable command ledger
        #    still owns the outcome, so the applied result replays exactly.
        replay_params = await _issued_retry_params(
            harness, _retry_params(task_id, command_id="command-retry-b")
        )
        assert replay_params["confirmation_id"] != first_confirmation
        replayed = await harness.composition.handle(
            operation="task.retry",
            params=replay_params,
            request_id="request-retry-b-replayed",
            session_id="session-1",
        )

        assert replayed.ok is True, replayed.payload
        assert replayed.payload["result"] == original
        assert replayed.payload["request_id"] == "request-retry-b-replayed"
        # Exact replay: zero new durable rows, zero outbox claim change, zero
        # Executor work and — proving replay precedes current admission — zero
        # additional readiness evaluations.
        assert await _effects(harness) == before

        # 3. A fresh valid confirmation does not launder a changed immutable
        #    product fact.  Each one still conflicts or is refused earlier.
        for changed in (
            {"command_id": "command-retry-other"},
            {"correlation_id": "correlation:tampered"},
            {"issued_at": "2026-08-05T11:59:00Z"},
        ):
            tampered = _retry_params(task_id, command_id="command-retry-b")
            tampered.update(changed)
            with pytest.raises(FormalTaskViolation) as conflicted:
                await _issued_retry_params(harness, tampered)
            assert conflicted.value.reason in {
                "IDEMPOTENCY_CONFLICT",
                "TASK_RETRY_REQUIRES_TERMINAL",
            }, changed
            assert await _effects(harness) == before, changed

        # The confirmation ledger may grow — D-069 keeps it an independent
        # authorization record — but it never produced a second attempt.
        assert _confirmation_count(harness.database) > 1
        current = harness.composition._core.store.get_task(task_id, _scope())
        assert current.attempt_id == original["attempt_id"]
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_changed_product_request_facts_conflict_on_the_same_command_id(
    tmp_path: Path,
) -> None:
    harness = _harness(tmp_path)
    await harness.composition.start()
    try:
        task_id = await _terminal_task(harness)
        await _apply_retry(harness, task_id, command_id="command-retry-b")
        before = await _effects(harness)

        confirmations_before = _confirmation_count(harness.database)
        conflicting = _retry_params(
            task_id,
            command_id="command-retry-b",
            correlation_id="correlation:tampered",
        )

        # The conflict is deterministic, so it is decided before any
        # confirmation is issued and long before the route could re-admit.
        with pytest.raises(FormalTaskViolation) as prepared:
            await harness.composition.prepare_mutation_confirmation(
                operation="task.retry",
                params=conflicting,
                session_id="session-1",
            )
        assert prepared.value.reason == "IDEMPOTENCY_CONFLICT"
        assert prepared.value.code is ErrorCode.CONFLICT

        routed = await harness.composition.handle(
            operation="task.retry",
            params=conflicting,
            request_id="request-retry-conflict",
            session_id="session-1",
        )
        assert routed.ok is False
        assert routed.payload["error"]["reason"] == "IDEMPOTENCY_CONFLICT"
        assert routed.payload["error"]["code"] == "CONFLICT"

        assert await _effects(harness) == before
        assert _confirmation_count(harness.database) == confirmations_before
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_retry_rejects_nonterminal_predecessor_with_zero_effect(
    tmp_path: Path,
) -> None:
    harness = _harness(tmp_path)
    await harness.composition.start()
    try:
        created = await harness.composition.handle(
            operation="task.create",
            params=_issued_create_params(harness),
            request_id="request-create",
            session_id="session-1",
        )
        assert created.ok is True
        task_id = str(created.payload["result"]["task_id"])
        await _wait_until(lambda: len(harness.executor.dispatches) == 1)
        before = await _effects(harness)
        confirmations_before = _confirmation_count(harness.database)

        with pytest.raises(FormalTaskViolation) as rejected:
            await harness.composition.prepare_mutation_confirmation(
                operation="task.retry",
                params=_retry_params(task_id),
                session_id="session-1",
            )

        assert rejected.value.reason == "TASK_RETRY_REQUIRES_TERMINAL"
        assert rejected.value.code is ErrorCode.CONFLICT
        assert await _effects(harness) == before
        # A deterministic rejection never reserves confirmation capacity.
        assert _confirmation_count(harness.database) == confirmations_before
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_retry_rejects_ineligible_terminal_outcome_with_zero_effect(
    tmp_path: Path,
) -> None:
    harness = _harness(tmp_path)
    harness.executor.dispatch_outcome = TerminalOutcome.FAILED
    await harness.composition.start()
    try:
        task_id = await _terminal_task(harness, cancel=False)
        assert (
            harness.composition._core.store.get_task(task_id, _scope()).outcome
            is TerminalOutcome.FAILED
        )
        before = await _effects(harness)

        with pytest.raises(FormalTaskViolation) as rejected:
            await harness.composition.prepare_mutation_confirmation(
                operation="task.retry",
                params=_retry_params(task_id),
                session_id="session-1",
            )

        assert rejected.value.reason == "TASK_RETRY_OUTCOME_NOT_ELIGIBLE"
        assert rejected.value.code is ErrorCode.CONFLICT
        assert await _effects(harness) == before
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_retry_budget_stops_at_three_total_attempts(tmp_path: Path) -> None:
    harness = _harness(tmp_path)
    await harness.composition.start()
    try:
        task_id = await _terminal_task(harness)
        second = await _apply_retry(harness, task_id, command_id="command-retry-b")
        assert second["attempt_number"] == 2
        await _cancel_current(harness, task_id, command_id="command-cancel-b")

        third = await _apply_retry(harness, task_id, command_id="command-retry-c")
        assert third["attempt_number"] == 3
        await _cancel_current(harness, task_id, command_id="command-cancel-c")

        before = await _effects(harness)
        with pytest.raises(FormalTaskViolation) as rejected:
            await harness.composition.prepare_mutation_confirmation(
                operation="task.retry",
                params=_retry_params(task_id, command_id="command-retry-d"),
                session_id="session-1",
            )

        assert rejected.value.reason == "TASK_RETRY_LIMIT_EXCEEDED"
        assert rejected.value.code is ErrorCode.CONFLICT
        assert await _effects(harness) == before
        assert (
            harness.composition._core.store.get_task(task_id, _scope()).attempt_id
            == third["attempt_id"]
        )
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_retry_fails_closed_while_executor_cleanup_is_pending(
    tmp_path: Path,
) -> None:
    harness = _harness(tmp_path)
    await harness.composition.start()
    try:
        task_id = await _terminal_task(harness)
        params = await _issued_retry_params(harness, _retry_params(task_id))
        harness.executor.retry_ready = False
        before = await _effects(harness)

        rejected = await harness.composition.handle(
            operation="task.retry",
            params=params,
            request_id="request-retry-cleanup-pending",
            session_id="session-1",
        )

        assert rejected.ok is False
        assert rejected.payload["error"]["reason"] == (
            "TASK_RETRY_EXECUTOR_CLEANUP_PENDING"
        )
        assert rejected.payload["error"]["code"] == "RESULT_UNKNOWN"
        assert (
            rejected.payload["extensions"]["live_voice.command"]["disposition"]
            == "unknown"
        )
        after = await _effects(harness)
        # Readiness itself was evaluated once and nothing else moved.
        assert after[:4] == before[:4]
        assert len(after[4]) == len(before[4]) + 1
        assert after[5] == before[5]
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_retry_rejects_forged_predecessor_lineage_confirmation(
    tmp_path: Path,
) -> None:
    harness = _harness(tmp_path)
    await harness.composition.start()
    try:
        task_id = await _terminal_task(harness)
        prepared = await harness.composition.prepare_mutation_confirmation(
            operation="task.retry",
            params=_retry_params(task_id),
            session_id="session-1",
        )
        honest = harness.authority.contexts["session-1"]
        persisted = harness.composition._core.store.get_task(task_id, _scope()).spec
        forged = PreparedP3RetryFacts(
            previous_attempt_id="attempt-forged",
            previous_outcome="completed",
            attempt_number=3,
            name=persisted.name,
            instruction=persisted.instruction,
            executor_id=persisted.executor_id,
            required_capabilities=tuple(persisted.required_capabilities),
            side_effect_class=persisted.side_effect_class,
            attributes=tuple(persisted.attributes),
        )
        forged_binding = P3ConfirmationBinding(
            principal_id=prepared.binding.principal_id,
            scope=prepared.binding.scope,
            operation="task.retry",
            command_id=prepared.binding.command_id,
            target_task_id=task_id,
            intent_fingerprint=p3_confirmation_intent_fingerprint(
                operation="task.retry",
                command_id=prepared.binding.command_id,
                target_task_id=task_id,
                context=honest,
                retry=forged,
            ),
        )
        assert forged_binding.intent_fingerprint != prepared.binding.intent_fingerprint
        params = _retry_params(task_id)
        params["confirmation_id"] = harness.confirmations.issue(
            forged_binding, expires_at=EXPIRY, now=NOW
        )
        before = await _effects(harness)

        rejected = await harness.composition.handle(
            operation="task.retry",
            params=params,
            request_id="request-retry-forged",
            session_id="session-1",
        )

        assert rejected.ok is False
        assert rejected.payload["error"]["reason"] == "P3_CONFIRMATION_BINDING_MISMATCH"
        assert rejected.payload["error"]["code"] == "PERMISSION_DENIED"
        assert await _effects(harness) == before
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_retry_requires_a_clean_checkout_and_performs_no_git_operation(
    tmp_path: Path,
) -> None:
    harness = _harness(tmp_path)
    await harness.composition.start()
    try:
        task_id = await _terminal_task(harness)
        before = await _effects(harness)
        harness.authority.dirty = True
        harness.authority.calls.clear()

        with pytest.raises(FormalTaskViolation) as prepared:
            await harness.composition.prepare_mutation_confirmation(
                operation="task.retry",
                params=_retry_params(task_id),
                session_id="session-1",
            )
        assert prepared.value.reason == "TASK_CONTEXT_WORKTREE_DIRTY"
        assert prepared.value.code is ErrorCode.PERMISSION_DENIED

        routed = await harness.composition.handle(
            operation="task.retry",
            params=_retry_params(task_id),
            request_id="request-retry-dirty",
            session_id="session-1",
        )
        assert routed.ok is False
        assert routed.payload["error"]["reason"] == "TASK_CONTEXT_WORKTREE_DIRTY"

        # Every retry authority resolution demanded the clean-worktree guard.
        assert harness.authority.calls == [("session-1", True), ("session-1", True)]
        assert await _effects(harness) == before
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_retry_rejects_expired_confirmation_foreign_scope_and_bad_bearer(
    tmp_path: Path,
) -> None:
    harness = _harness(tmp_path)
    await harness.composition.start()
    try:
        task_id = await _terminal_task(harness)
        # Issue against an earlier clock so the record is already expired at NOW.
        expired = await _issued_retry_params(
            harness,
            _retry_params(task_id, command_id="command-retry-expired"),
            expires_at="2026-08-05T11:30:00Z",
            now="2026-08-05T11:00:00Z",
        )
        before = await _effects(harness)

        stale = await harness.composition.handle(
            operation="task.retry",
            params=expired,
            request_id="request-retry-expired",
            session_id="session-1",
        )
        assert stale.ok is False
        assert stale.payload["error"]["reason"] == "P3_CONFIRMATION_EXPIRED"
        assert stale.payload["error"]["code"] == "PERMISSION_DENIED"

        foreign = await harness.composition.handle(
            operation="task.retry",
            params=_retry_params(
                task_id,
                command_id="command-retry-foreign",
                session_id="session-2",
            ),
            request_id="request-retry-foreign",
            session_id="session-2",
        )
        assert foreign.ok is False
        assert foreign.payload["error"]["code"] == "NOT_FOUND"
        assert task_id not in str(foreign.payload["error"])

        unauthorized = await harness.composition.handle(
            operation="task.retry",
            params={**_retry_params(task_id), "auth_token": "wrong-token"},
            request_id="request-retry-unauthorized",
            session_id="session-1",
        )
        assert unauthorized.ok is False
        assert unauthorized.payload["error"]["code"] == "UNAUTHENTICATED"
        assert await _effects(harness) == before
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_retry_fails_closed_while_predecessor_authority_is_unsettled(
    tmp_path: Path,
) -> None:
    """Unsettled outbox or reconciliation ownership blocks admission upstream.

    Both facts are Store-owned, so the product route must surface their exact
    stable reason rather than folding them into a generic retry error.  The
    snapshots below are taken directly instead of through ``_effects`` because
    the injected pending outbox row would otherwise never appear settled.
    """

    harness = _harness(tmp_path)
    await harness.composition.start()
    try:
        task_id = await _terminal_task(harness)
        attempt_id = harness.composition._core.store.get_task(
            task_id, _scope()
        ).attempt_id

        with sqlite3.connect(harness.database) as connection:
            connection.execute(
                "UPDATE tasks SET reconciliation_state=? WHERE task_id=?",
                (ReconciliationState.PENDING.value, task_id),
            )
        before = _store_counts(harness.database)
        readiness_before = len(harness.executor.readiness)

        with pytest.raises(FormalTaskViolation) as reconciliation:
            await harness.composition.prepare_mutation_confirmation(
                operation="task.retry",
                params=_retry_params(task_id),
                session_id="session-1",
            )
        assert reconciliation.value.reason == "TASK_RETRY_RECONCILIATION_PENDING"
        assert reconciliation.value.code is ErrorCode.UNAVAILABLE

        with sqlite3.connect(harness.database) as connection:
            connection.execute(
                "UPDATE tasks SET reconciliation_state=NULL WHERE task_id=?",
                (task_id,),
            )
            connection.execute(
                "UPDATE outbox SET state=? WHERE task_id=? AND attempt_id=?",
                (OutboxState.PENDING.value, task_id, attempt_id),
            )

        with pytest.raises(FormalTaskViolation) as outbox:
            await harness.composition.prepare_mutation_confirmation(
                operation="task.retry",
                params=_retry_params(task_id),
                session_id="session-1",
            )
        assert outbox.value.reason == "TASK_RETRY_OUTBOX_PENDING"
        assert outbox.value.code is ErrorCode.UNAVAILABLE

        # Neither deterministic rejection admitted an attempt, appended an
        # event, claimed an outbox row, issued a command or reached the
        # Executor readiness seam.
        assert _store_counts(harness.database) == before
        assert len(harness.executor.readiness) == readiness_before
        assert harness.executor.dispatches == [attempt_id]
        assert harness.executor.cancels == [attempt_id]
        with sqlite3.connect(harness.database) as connection:
            assert (
                connection.execute(
                    "SELECT COUNT(*) FROM outbox WHERE claimed_by IS NOT NULL"
                ).fetchone()[0]
                == 0
            )
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_retry_rejects_an_unsupported_legacy_executor(tmp_path: Path) -> None:
    harness = _harness(tmp_path)
    await harness.composition.start()
    try:
        task_id = await _terminal_task(harness)
        before = await _effects(harness)
        harness.executor.executor_id = "legacy.demo_substitute"

        with pytest.raises(FormalTaskViolation) as rejected:
            await harness.composition.prepare_mutation_confirmation(
                operation="task.retry",
                params=_retry_params(task_id),
                session_id="session-1",
            )

        assert rejected.value.reason == "EXECUTOR_CAPABILITY_UNAVAILABLE"
        assert rejected.value.code is ErrorCode.CAPABILITY_UNAVAILABLE
        assert await _effects(harness) == before
    finally:
        harness.executor.executor_id = FORMAL_PROJECT_EXECUTOR_ID
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_concurrent_retry_admits_exactly_one_successor_attempt(
    tmp_path: Path,
) -> None:
    harness = _harness(tmp_path)
    await harness.composition.start()
    try:
        task_id = await _terminal_task(harness)
        first = await _issued_retry_params(
            harness, _retry_params(task_id, command_id="command-retry-x")
        )
        second = await _issued_retry_params(
            harness, _retry_params(task_id, command_id="command-retry-y")
        )
        before = _store_counts(harness.database)

        results = await asyncio.gather(
            harness.composition.handle(
                operation="task.retry",
                params=first,
                request_id="request-retry-x",
                session_id="session-1",
            ),
            harness.composition.handle(
                operation="task.retry",
                params=second,
                request_id="request-retry-y",
                session_id="session-1",
            ),
        )

        accepted = [item for item in results if item.ok]
        refused = [item for item in results if not item.ok]
        assert len(accepted) == 1
        assert len(refused) == 1
        assert refused[0].payload["error"]["reason"] in {
            "TASK_RETRY_PRECONDITION_STALE",
            "TASK_RETRY_REQUIRES_TERMINAL",
        }
        after = _store_counts(harness.database)
        # Exactly one successor attempt and one dispatch outbox row.  The loser
        # contributes no durable row at all; delivery of the winner may still
        # append lifecycle events, so that count is bounded from below.
        assert after[1] == before[1] + 1
        assert after[2] >= before[2] + 1
        assert after[3] == before[3] + 1
        assert accepted[0].payload["result"]["attempt_number"] == 2
        assert harness.executor.readiness[-1][0] == task_id
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_retry_route_surface_rejects_client_declared_or_extra_facts(
    tmp_path: Path,
) -> None:
    harness = _harness(tmp_path)
    await harness.composition.start()
    try:
        task_id = await _terminal_task(harness)
        before = await _effects(harness)

        for extra in (
            {"source": "voice"},
            {"previous_attempt_id": "attempt-client-declared"},
            {"attempt_number": 2},
            {"after_seq": 0},
            {"name": "renamed"},
        ):
            rejected = await harness.composition.handle(
                operation="task.retry",
                params={**_retry_params(task_id), **extra},
                request_id=f"request-retry-extra-{next(iter(extra))}",
                session_id="session-1",
            )
            assert rejected.ok is False, extra
            assert rejected.payload["error"]["reason"] == "INVALID_P3_ROUTE_ARGUMENT"

        # Query-style authority registration can never resolve a retry grant.
        with pytest.raises(FormalTaskViolation) as denied:
            harness.composition.resolve_product_authority_candidate(
                bearer_token=TOKEN,
                operation="task.retry",
                session_id="session-1",
                correlation_id="correlation:retry",
                required_capabilities=frozenset({"task.retry"}),
                task_id=task_id,
            )
        assert denied.value.reason == "FORMAL_TASK_AUTHORIZATION_DENIED"
        assert denied.value.code is ErrorCode.PERMISSION_DENIED
        assert await _effects(harness) == before
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_product_authority_candidate_requires_exact_cancel_target(
    tmp_path: Path,
) -> None:
    harness = _harness(tmp_path)
    await harness.composition.start()
    try:
        task_id = await _terminal_task(harness)
        candidate, context = harness.composition.resolve_product_authority_candidate(
            bearer_token=TOKEN,
            operation="task.cancel",
            session_id="session-1",
            correlation_id="correlation:product-cancel",
            required_capabilities=frozenset({"task.cancel"}),
            task_id=task_id,
        )

        assert candidate.resource is not None
        assert candidate.resource.resource_id == task_id
        assert context.scope == _scope()
        with pytest.raises(FormalTaskViolation) as missing:
            harness.composition.resolve_product_authority_candidate(
                bearer_token=TOKEN,
                operation="task.cancel",
                session_id="session-1",
                correlation_id="correlation:product-cancel-missing",
                required_capabilities=frozenset({"task.cancel"}),
                task_id=None,
            )
        assert missing.value.reason == "INVALID_P3_ROUTE_ARGUMENT"
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_product_presentation_uses_fresh_unread_and_server_ack_authorities(
    tmp_path: Path,
) -> None:
    harness = _harness(
        tmp_path,
        allowed_operations=P3_PRODUCT_AUTHORITY_OPERATIONS,
    )
    await harness.composition.start()
    try:
        created = await harness.composition.handle(
            operation="task.create",
            params=_issued_create_params(harness, "command-presentation-task"),
            request_id="request-presentation-task",
            session_id="session-1",
        )
        assert created.ok is True
        task_id = str(created.payload["result"]["task_id"])

        def resolve(operation: str):
            candidate, _context = (
                harness.composition.resolve_product_authority_candidate(
                    bearer_token=TOKEN,
                    operation=operation,
                    session_id="session-1",
                    correlation_id=f"correlation:{operation}",
                    required_capabilities=frozenset({operation}),
                    task_id=task_id,
                )
            )

            class Resolver:
                @staticmethod
                def resolve(_lookup):
                    return (candidate,)

            route = AuthorityRouteContext(
                session_id="session-1",
                correlation_id=f"correlation:{operation}",
                claimed_user_id="user-1",
                claimed_project_id="project-1",
                claimed_scope=_scope(),
            )
            decision = ProductAuthorityService(
                enabled=True,
                resolver=Resolver(),
                clock=lambda: datetime(2026, 8, 5, 12, tzinfo=UTC),
            ).resolve(
                ProductAuthorityRequest(
                    route=route,
                    operation=operation,
                    required_capabilities=frozenset({operation}),
                    resource=candidate.resource,
                )
            )
            assert decision.status is AuthorityDecisionStatus.AUTHORIZED
            assert decision.authority is not None
            return decision.authority

        unread_authority = resolve("task.unread_events")
        page = await harness.composition.read_product_unread_events(
            unread_authority,
            presentation_class="text",
            request_id="request-unread-presentation",
        )
        assert page.events and page.events[0].seq == page.watermark + 1
        event = page.events[0]
        delivery = TaskPresentationDelivery(
            scope=unread_authority.scope,
            presentation_class="text",
            task_id=task_id,
            attempt_id=event.attempt_id,
            event_id=event.event_id,
            event_seq=event.seq,
            expected_event_head=page.head_seq,
            result_source_event_id=None,
            response_ref=ResponseRef("interaction-1", "response-presentation-1", 1),
            runtime_reservation_id="runtime-reservation-1",
            delivery_id="delivery-presentation-1",
            unit_id="unit-presentation-1",
        )
        ack_authority = resolve("task.ack_events")
        command, grant = harness.composition.prepare_product_presentation_ack(
            ack_authority,
            delivery,
            request_id="request-ack-presentation",
            command_id="command-ack-presentation",
            now="2026-08-05T12:00:01Z",
        )
        result = harness.composition.execute_product_presentation_ack(
            ack_authority,
            command,
            grant,
            now="2026-08-05T12:00:01Z",
        )
        assert result.ok is True
        assert result.result is not None
        assert result.result["acked_through_seq"] == event.seq
        after = await harness.composition.read_product_unread_events(
            unread_authority,
            presentation_class="text",
            request_id="request-unread-presentation-after",
        )
        assert after.watermark == event.seq
        assert harness.executor.cancels == []
        assert harness.executor.adjustments == []
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_presentation_consumer_reconnects_in_a_fresh_session(
    tmp_path: Path,
) -> None:
    contexts = {
        "session-1": _context(tmp_path, session_id="session-1"),
        "session-2": _context(tmp_path, session_id="session-2"),
        "session-foreign": _context(
            tmp_path,
            project_id="project-2",
            session_id="session-foreign",
        ),
    }
    harness = _harness(
        tmp_path,
        contexts=contexts,
        allowed_operations=P3_PRODUCT_AUTHORITY_OPERATIONS,
    )
    await harness.composition.start()
    source = None
    try:
        created = await harness.composition.handle(
            operation="task.create",
            params=_issued_create_params(harness, "command-reconnect-task"),
            request_id="request-reconnect-task",
            session_id="session-1",
        )
        assert created.ok is True
        task_id = str(created.payload["result"]["task_id"])

        with pytest.raises(FormalTaskViolation) as exact_session_query:
            harness.composition.resolve_product_authority_candidate(
                bearer_token=TOKEN,
                operation="task.events",
                session_id="session-2",
                correlation_id="correlation:ordinary-events",
                required_capabilities=frozenset({"task.events"}),
                task_id=task_id,
            )
        assert exact_session_query.value.reason == "TASK_NOT_FOUND"

        candidate, _context_2 = harness.composition.resolve_product_authority_candidate(
            bearer_token=TOKEN,
            operation="task.events",
            session_id="session-2",
            correlation_id="correlation:consumer-events",
            required_capabilities=frozenset({"task.events"}),
            task_id=task_id,
            consumer_task_access=True,
        )
        assert candidate.scope == _scope(session_id="session-2")
        grant = TaskAuthorizationGrant(
            principal_id="user-1",
            scope=candidate.scope,
            operation="task.events",
            command_id=None,
            target_task_id=task_id,
            allowed_capabilities=frozenset({"task.events"}),
            confirmation_id=None,
            confirmed=False,
            expires_at=EXPIRY,
        )
        binding = TaskProgressOriginBinding(
            scope=candidate.scope,
            task_id=task_id,
            session_id="session-2",
            project_id="project-1",
            correlation_id="correlation:consumer-events",
            origin_kind=TaskProgressOriginKind.TEXT,
            origin_id="web-progress-reconnect",
            generation_kind="web_task_progress_generation",
            generation_id="generation-reconnect",
            generation=1,
            source_instance_id="agent_server.p3_core",
            progress_producer=ProducerRef(
                component="product_p3_text",
                instance_id="session-2:web-progress-reconnect:1",
                authority="adapter",
            ),
            progress_adapter="agent_server.product_p3_text.v1",
        )
        source = harness.composition.create_product_progress_source(grant, binding)
        assert await source.start() is True
        replayed = await asyncio.wait_for(source.next_event(), timeout=1)
        assert replayed.task_id == task_id
        assert replayed.seq == 0

        def resolve_presentation(operation: str, session_id: str):
            resolved_candidate, _ = (
                harness.composition.resolve_product_authority_candidate(
                    bearer_token=TOKEN,
                    operation=operation,
                    session_id=session_id,
                    correlation_id=f"correlation:{operation}:{session_id}",
                    required_capabilities=frozenset({operation}),
                    task_id=task_id,
                )
            )

            class Resolver:
                @staticmethod
                def resolve(_lookup):
                    return (resolved_candidate,)

            route_scope = contexts[session_id].scope
            service = ProductAuthorityService(
                enabled=True,
                resolver=Resolver(),
                clock=lambda: datetime(2026, 8, 5, 12, tzinfo=UTC),
            )
            decision = service.resolve(
                ProductAuthorityRequest(
                    route=AuthorityRouteContext(
                        session_id=session_id,
                        correlation_id=f"correlation:{operation}:{session_id}",
                        claimed_user_id="user-1",
                        claimed_project_id=route_scope.project_id,
                        claimed_scope=route_scope,
                    ),
                    operation=operation,
                    required_capabilities=frozenset({operation}),
                    resource=resolved_candidate.resource,
                )
            )
            assert decision.status is AuthorityDecisionStatus.AUTHORIZED
            assert decision.authority is not None
            return decision.authority

        unread_authority = resolve_presentation("task.unread_events", "session-2")
        page = await harness.composition.read_product_unread_events(
            unread_authority,
            presentation_class="text",
            request_id="request-reconnect-unread",
        )
        event = page.events[0]
        delivery = TaskPresentationDelivery(
            scope=unread_authority.scope,
            presentation_class="text",
            task_id=task_id,
            attempt_id=event.attempt_id,
            event_id=event.event_id,
            event_seq=event.seq,
            expected_event_head=page.head_seq,
            result_source_event_id=None,
            response_ref=ResponseRef("interaction-reconnect", "response-reconnect", 1),
            runtime_reservation_id="runtime-reservation-reconnect",
            delivery_id="delivery-reconnect",
            unit_id="unit-reconnect",
        )
        ack_authority = resolve_presentation("task.ack_events", "session-2")
        command, ack_grant = harness.composition.prepare_product_presentation_ack(
            ack_authority,
            delivery,
            request_id="request-reconnect-ack",
            command_id="command-reconnect-ack",
            now="2026-08-05T12:00:01Z",
        )
        result = harness.composition.execute_product_presentation_ack(
            ack_authority,
            command,
            ack_grant,
            now="2026-08-05T12:00:01Z",
        )
        assert result.ok is True
        assert result.result is not None
        assert result.result["acked_through_seq"] == event.seq

        before = await _effects(harness)
        with pytest.raises(FormalTaskViolation) as foreign:
            harness.composition.resolve_product_authority_candidate(
                bearer_token=TOKEN,
                operation="task.unread_events",
                session_id="session-foreign",
                correlation_id="correlation:foreign-unread",
                required_capabilities=frozenset({"task.unread_events"}),
                task_id=task_id,
            )
        assert foreign.value.reason == "TASK_NOT_FOUND"
        assert await _effects(harness) == before
    finally:
        if source is not None:
            await source.close()
        await harness.composition.stop()


def test_retry_has_no_direct_transport_route_but_stays_a_p3_mutation() -> None:
    """W2 reaches retry only through the product composition mutate route.

    Removing the direct transport method must not silently demote
    ``task.retry`` to an unknown operation: every admission in ``handle`` and
    ``prepare_mutation_confirmation`` gates on these sets, so losing the
    operation here would disable retry validation instead of disabling retry.
    """

    from jiuwenswarm.common.schema.message import ReqMethod

    assert "live_voice.task.retry" not in P3_ROUTE_METHODS
    assert "task.retry" not in set(P3_ROUTE_METHODS.values())
    assert all(item.value != "live_voice.task.retry" for item in ReqMethod)

    assert "task.retry" in P3_OPERATIONS
    assert "task.retry" in P3_MUTATIONS
    assert "task.retry" in P3_TARGETED_MUTATIONS
    # Every directly routed operation keeps its transport method.
    assert P3_OPERATIONS - P3_MUTATIONS == set(P3_ROUTE_METHODS.values()) - {
        "task.create",
        "task.cancel",
    }


@pytest.mark.asyncio
async def test_unrouted_transport_method_cannot_reach_the_retry_admission(
    tmp_path: Path,
) -> None:
    harness = _harness(tmp_path)
    await harness.composition.start()
    try:
        task_id = await _terminal_task(harness)
        before = await _effects(harness)

        # AgentServer resolves an operation through P3_ROUTE_METHODS; an
        # unrouted method yields the empty operation and must fail closed.
        unrouted = P3_ROUTE_METHODS.get("live_voice.task.retry", "")
        assert unrouted == ""
        rejected = await harness.composition.handle(
            operation=unrouted,
            params=_retry_params(task_id),
            request_id="request-retry-unrouted",
            session_id="session-1",
        )

        assert rejected.ok is False
        assert rejected.payload["error"]["reason"] == "UNSUPPORTED_FORMAL_TASK_INTENT"
        assert rejected.payload["error"]["code"] == "UNSUPPORTED"
        assert await _effects(harness) == before
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_cancel_before_dispatch_predecessor_admits_exactly_one_successor(
    tmp_path: Path,
) -> None:
    """The canonical cancel-before-dispatch shape is retry eligible end to end.

    Admission is opened without the periodic reconciliation worker so the
    create dispatch outbox is never claimed.  That is exactly how a task
    cancelled before dispatch looks: the Direct Executor was never called, so
    it owns no journal row for the predecessor, yet D-069 still makes a
    cancelled terminal attempt retry eligible.
    """

    harness = _harness(tmp_path)
    async with harness.composition._active_condition:
        harness.composition._accepting = True
    try:
        created = await harness.composition.handle(
            operation="task.create",
            params=_issued_create_params(harness),
            request_id="request-create",
            session_id="session-1",
        )
        assert created.ok is True, created.payload
        task_id = str(created.payload["result"]["task_id"])
        assert harness.executor.dispatches == []

        cancelled = await harness.composition.handle(
            operation="task.cancel",
            params=_issued_cancel_params(harness, task_id),
            request_id="request-cancel",
            session_id="session-1",
        )
        assert cancelled.ok is True, cancelled.payload

        store = harness.composition._core.store
        predecessor = store.get_task(task_id, _scope())
        attempt_a = predecessor.attempt_id
        assert predecessor.state.value == "terminal"
        assert predecessor.outcome is TerminalOutcome.CANCELLED
        assert predecessor.cancel_requested is True
        assert predecessor.dispatch_fenced is True
        assert store.get_attempt(attempt_a).executor_ref is None
        # The Executor was never engaged, so it holds no journal for A.
        assert harness.executor.dispatches == []
        assert harness.executor.cancels == []
        before = _store_counts(harness.database)

        result = await _apply_retry(harness, task_id, command_id="command-retry-b")

        assert result["previous_attempt_id"] == attempt_a
        assert result["attempt_number"] == 2
        assert result["applied"] is True
        # Readiness is proved at Store apply from Store facts against exactly A.
        assert harness.executor.readiness == [(task_id, attempt_a)]

        after = _store_counts(harness.database)
        # Exactly one successor attempt, one boundary event, one dispatch
        # outbox row and one admission command; the task row is not duplicated.
        assert after[0] == before[0]
        assert after[1] == before[1] + 1
        assert after[2] == before[2] + 1
        assert after[3] == before[3] + 1
        assert after[4] == before[4] + 1
        current = store.get_task(task_id, _scope())
        assert current.attempt_id == result["attempt_id"]
        assert current.state.value == "accepted"
        assert current.outcome is None
        # No worker ran, so nothing was dispatched or cancelled for B either.
        assert harness.executor.dispatches == []
        assert harness.executor.cancels == []
    finally:
        await harness.composition.stop()


def test_p3_model_builder_uses_the_shared_module_level_entry_builder() -> None:
    """P3 must build its model through the function the runtime actually exports.

    ``build_model_from_entry`` is the module-level function the deep adapter,
    the model cache and the modality warmup all share; it has never been an
    attribute of ``JiuWenSwarmDeepAdapter``.  Calling it as a class method
    raised AttributeError inside model resolution, which the Task Core could
    only report as ``P3_MODEL_UNAVAILABLE``.  Every real attempt dispatch then
    failed with a suppressed outbox item and no project effect, while fake
    resolvers in tests never constructed a model at all.
    """

    from jiuwenswarm.server.runtime.agent_adapter import interface_deep
    from jiuwenswarm.server.agent_ws_server import AgentWebSocketServer

    assert hasattr(interface_deep, "build_model_from_entry")
    assert not hasattr(interface_deep.JiuWenSwarmDeepAdapter, "_build_model_from_entry")

    seen: list[tuple[dict, dict]] = []
    sentinel = object()
    original = interface_deep.build_model_from_entry
    interface_deep.build_model_from_entry = (  # type: ignore[assignment]
        lambda mcc, mco: (seen.append((mcc, mco)), sentinel)[1]
    )
    try:
        built = AgentWebSocketServer._build_live_voice_p3_model(
            {"model_name": "probe-model", "client_provider": "probe"},
            {"temperature": 0.0},
        )
    finally:
        interface_deep.build_model_from_entry = original  # type: ignore[assignment]

    assert built is sentinel
    assert seen == [
        (
            {"model_name": "probe-model", "client_provider": "probe"},
            {"temperature": 0.0},
        )
    ]


@pytest.mark.asyncio
async def test_dispatch_builds_the_agent_handle_instead_of_reading_the_accessor(
    tmp_path: Path,
) -> None:
    """A formal dispatch must build the DeepAgent, not read the bare accessor.

    ``JiuWenSwarm.get_instance`` is a plain accessor that returns None until the
    chat path has built the root DeepAgent.  A formal task dispatches outside
    that path onto a freshly created project Agent, so reading the accessor left
    ``execution_agent`` None and every real attempt failed closed with
    EXECUTOR_CAPABILITY_UNAVAILABLE and no project effect.
    """

    class Authority:
        def revalidate(self, _context, **_kwargs):
            return SimpleNamespace(
                project_dir=str(tmp_path),
                project_id="project-1",
                session_id="session-1",
                revision="a77516a0",
            )

    built = object()

    class Agent:
        def __init__(self) -> None:
            self.ensure_calls = 0

        def get_instance(self):
            # The root DeepAgent does not exist yet outside the chat path.
            return None

        async def ensure_instance(self):
            self.ensure_calls += 1
            return built

        def get_project_execution_root(self) -> str:
            return str(tmp_path)

    agent = Agent()

    class Manager:
        async def get_live_voice_formal_task_agent(self, _project_dir: str):
            return agent

        def pin_agent(self, _agent) -> None:
            return None

        def unpin_agent(self, _agent) -> None:
            return None

    resolver = AgentManagerProjectBindingResolver(
        authority_resolver=Authority(),
        agent_manager=Manager(),
        service=object(),
        model_resolver=_ModelResolver(),
        principal=_principal(),
        clock=lambda: NOW,
    )

    binding = await resolver.resolve(
        SimpleNamespace(
            context=object(),
            attributes=(
                ("model_identity", "default#0"),
                ("model_config_version", "catalog-v1"),
            ),
        ),
        for_dispatch=True,
    )

    assert binding.execution_agent is built
    assert agent.ensure_calls == 1
    assert binding.project_executor is agent
