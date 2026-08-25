# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Authenticated, server-resolved P3 product composition.

The formal Task Core intentionally does not authenticate callers or resolve
projects.  This module supplies that missing product boundary.  Browser input
may select a persisted session and carry business fields, but it can never
assert a principal, project, scope, authorization grant, or ContextRef.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import math
import os
import stat
import subprocess
import threading
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    Assurance,
    CONTRACT_VERSION,
    CommandEnvelope,
    ErrorCode,
    InputCommitState,
    QueryEnvelope,
    ResultEnvelope,
    ScopeRef,
    TurnCommitLedger,
    canonical_json_bytes,
)
from jiuwenswarm.common.utils import get_user_workspace_dir

from .formal_task_models import (
    AdmissionPolicy,
    FormalTaskViolation,
    FormalTaskSpec,
    PersistentTaskRecord,
    PersistentTaskEvent,
    PersistedExecutorSelection,
    ResolvedTaskContext,
    TaskAuthorizationGrant,
    TaskMutationPrecondition,
    TaskResultAvailability,
    TaskResultRecord,
    TaskRetryPrecondition,
    TaskRetryProductRequestFingerprint,
    TaskUnreadPage,
    utc_now,
)
from .live_voice_configuration_declaration import (
    LIVE_VOICE_CONFIGURATION_CONTRACT_VERSION,
    AuthenticationMode,
    DurabilityLevel,
    ExecutorCapability,
    LiveVoiceCapability,
    LiveVoiceDeploymentProfile,
    ProviderCapability,
    ValidatedAuthenticationConfiguration,
    ValidatedExecutorConfiguration,
    ValidatedLiveVoiceConfiguration,
    ValidatedProviderConfiguration,
)
from .executor_capabilities import (
    TASK_EXECUTION_REQUIREMENTS_SCHEMA_VERSION,
    ExecutorCapabilityProfile,
    ExecutorSelection,
    TaskExecutionRequirements,
    select_executor,
)
from .persistent_task_core import PersistentTaskCore, ReconciliationEventSink
from .p2_response_generation_store import SqliteP2ResponseGenerationOwner
from .p3_confirmation import (
    P3ConfirmationBinding,
    P3ConfirmationVerifier,
    PreparedP3RetryFacts,
    SqliteP3ConfirmationLedger,
    VerifiedP3Confirmation,
    p3_confirmation_intent_fingerprint,
)
from .p3_model_resolution import P3ModelResolver, ResolvedP3Model
from .p3_production_intent_composition import (
    CallLocalProductionConfirmationClaim,
    CallLocalProductionConfirmationConsumer,
    CallLocalProductionOriginAuthority,
    StoreProductionTaskAuthorityReader,
    production_context_fingerprint,
    production_model_binding_fingerprint,
)
from .product_authority import (
    AuthorityResourceBinding,
    ResolvedProductAuthority,
    TrustedAuthorityCandidate,
)
from .presentation_ledger import TaskPresentationDelivery
from .product_p3_text_adapter import ProductP3AuthorizedQuery
from .project_code_executor import (
    AttemptProjectExecutorLease,
    DirectProjectCodeExecutorAdapter,
    DirectStreamObserver,
    FORMAL_PROJECT_EXECUTOR_ID,
    ProjectExecutionBinding,
)
from .production_task_intent import (
    AuthenticatedTaskFact,
    ProductionIntentOrigin,
    ProductionOriginBinding,
    ProductionTaskPolicyOutcome,
    ProductionTaskResolution,
    TaskAuthorityRead,
)
from .task_event_subscription import TaskEventSubscription
from .task_progress_return import (
    TaskEventAuthorityProgressSource,
    TaskProgressOriginBinding,
    TaskProgressOriginKind,
)
from .task_store import SqliteTaskStore, TaskDurabilityDiagnosticSnapshot
from .voice_task_policy import FormalTaskPolicyAdapter, FormalTaskPolicyInput

logger = logging.getLogger(__name__)

P3_ROUTE_METHODS: Mapping[str, str] = {
    "live_voice.task.create": "task.create",
    "live_voice.task.get": "task.get",
    "live_voice.task.list": "task.list",
    "live_voice.task.status": "task.status",
    "live_voice.task.cancel": "task.cancel",
    "live_voice.task.events": "task.events",
    "live_voice.task.result": "task.result",
}
P3_MUTATIONS = frozenset({"task.create", "task.adjust", "task.cancel", "task.retry"})
P3_TARGETED_MUTATIONS = frozenset({"task.adjust", "task.cancel", "task.retry"})
P3_QUERY_OPERATIONS = frozenset(
    {"task.get", "task.list", "task.status", "task.events", "task.result"}
)
# ``task.retry`` deliberately has no direct transport method: the only W2
# carrier is the product composition mutate route.  It must still be a first
# class P3 operation, because dropping it here would silently disable the
# mutation validation every retry admission depends on.
P3_OPERATIONS = frozenset(P3_ROUTE_METHODS.values()) | P3_MUTATIONS
P3_PRODUCTION_MUTATIONS = frozenset(
    {
        "task.create",
        "task.update",
        "task.adjust",
        "task.reprioritize",
        "task.cancel",
        "task.create_successor",
    }
)
P3_PRODUCTION_OPERATIONS = P3_QUERY_OPERATIONS | P3_PRODUCTION_MUTATIONS
P3_PRESENTATION_OPERATIONS = frozenset({"task.unread_events", "task.ack_events"})
P3_PRODUCT_AUTHORITY_OPERATIONS = (
    P3_OPERATIONS | P3_PRODUCTION_OPERATIONS | P3_PRESENTATION_OPERATIONS
)

_ENABLE_ENV = "JIUWENSWARM_LIVE_VOICE_P3_ENABLED"
_TOKEN_ENV = "JIUWENSWARM_LIVE_VOICE_P3_AUTH_TOKEN"
_PRINCIPAL_ENV = "JIUWENSWARM_LIVE_VOICE_P3_PRINCIPAL_ID"
_PROJECTS_ENV = "JIUWENSWARM_LIVE_VOICE_P3_PROJECT_IDS"
_EXPIRY_ENV = "JIUWENSWARM_LIVE_VOICE_P3_AUTH_EXPIRES_AT"
_DATABASE_ENV = "JIUWENSWARM_LIVE_VOICE_P3_DATABASE"
_RECONCILE_ENV = "JIUWENSWARM_LIVE_VOICE_P3_RECONCILE_SECONDS"
_EXECUTOR_PROFILE_ENV = "JIUWENSWARM_LIVE_VOICE_P3_EXECUTOR_PROFILE"
_PRODUCT_COMPOSITION_ENV = "JIUWENSWARM_LIVE_VOICE_PRODUCT_COMPOSITION_ENABLED"
_PRODUCT_P2_ENV = "JIUWENSWARM_LIVE_VOICE_PRODUCT_P2_ENABLED"
_PRODUCT_DEMO_POLICY_BYPASS_ENV = (
    "JIUWENSWARM_LIVE_VOICE_PRODUCT_DEMO_POLICY_BYPASS_ENABLED"
)
_DEMO_ADJUSTMENT_CHECKPOINT_ENV = (
    "JIUWENSWARM_LIVE_VOICE_DEMO_ADJUSTMENT_CHECKPOINT_ENABLED"
)
_PRODUCT_P2_OPERATION = "agent.chat"

_PRODUCT_DIRECT_OPERATION_VERSIONS = (
    ("dispatch", "v1"),
    ("status", "v1"),
    ("cancel", "v1"),
    ("adjust.demo-itinerary-checkpoint", "v1"),
    ("reconcile.d0", "v1"),
)
_PRODUCT_DIRECT_D2_OPERATION_VERSIONS = (
    *_PRODUCT_DIRECT_OPERATION_VERSIONS,
    ("checkpoint.d1", "v1"),
    ("recover.d1", "v1"),
    ("effect.d2", "v1"),
    ("reconcile.d2", "v1"),
)
_PRODUCT_ADMISSION_POLICY = AdmissionPolicy(
    deadline_seconds=3_600,
    initial_backoff_seconds=1,
    max_backoff_seconds=60,
    max_attempts=120,
)


def _validated_executor_configuration(
    profile: ExecutorCapabilityProfile,
) -> ValidatedExecutorConfiguration:
    """Bind one exact construction profile to the public configuration fact."""

    if type(profile) is not ExecutorCapabilityProfile:
        raise TypeError("profile must be an exact ExecutorCapabilityProfile")
    durability = DurabilityLevel(profile.durability_level)
    capabilities = {
        DurabilityLevel.D0: (
            ExecutorCapability.CANCEL,
            ExecutorCapability.DISPATCH,
            ExecutorCapability.STATUS,
        ),
        DurabilityLevel.D1: (
            ExecutorCapability.CANCEL,
            ExecutorCapability.CHECKPOINT,
            ExecutorCapability.DISPATCH,
            ExecutorCapability.RECOVERY,
            ExecutorCapability.STATUS,
        ),
        DurabilityLevel.D2: tuple(
            sorted(ExecutorCapability, key=lambda item: item.value)
        ),
    }[durability]
    profile_digest = profile.digest_sha256()
    return ValidatedExecutorConfiguration(
        executor_id=profile.executor_id,
        adapter_id=profile.adapter_id,
        durability_level=durability,
        capabilities=capabilities,
        validation_receipt_id=f"executor-profile.v1.{profile_digest[:32]}",
        configuration_digest=profile_digest,
    )


def _product_execution_requirements(
    *,
    executor_id: str,
    side_effect_class: str,
    durability_level: str = "D0",
) -> TaskExecutionRequirements:
    operation_versions = (
        _PRODUCT_DIRECT_D2_OPERATION_VERSIONS
        if durability_level == "D2"
        else _PRODUCT_DIRECT_OPERATION_VERSIONS
    )
    return TaskExecutionRequirements(
        schema_version=TASK_EXECUTION_REQUIREMENTS_SCHEMA_VERSION,
        executor_id=executor_id,
        operation_versions=operation_versions,
        durability_level=durability_level,
        side_effect_class=side_effect_class,
        project_serialization="exclusive",
    )


def _persisted_executor_selection(
    selection: ExecutorSelection,
) -> PersistedExecutorSelection:
    """Adapt the approved selector value without recanonicalizing its bytes."""

    return PersistedExecutorSelection(
        adapter_id=selection.profile.adapter_id,
        capability_profile_json=selection.profile.canonical_bytes(),
        capability_profile_digest=selection.profile_digest,
        execution_requirements_json=selection.requirements.canonical_bytes(),
    )


def _parse_utc(value: str, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise FormalTaskViolation(
            "INVALID_P3_AUTH_CONFIGURATION",
            f"{field_name} must be an ISO-8601 timestamp",
            ErrorCode.INVALID_ARGUMENT,
        ) from exc
    if parsed.tzinfo is None:
        raise FormalTaskViolation(
            "INVALID_P3_AUTH_CONFIGURATION",
            f"{field_name} must include a timezone",
            ErrorCode.INVALID_ARGUMENT,
        )
    return parsed.astimezone(UTC)


def _is_enabled(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _path_key(value: str | Path) -> str:
    return os.path.normcase(os.path.normpath(str(Path(value).resolve(strict=True))))


def _required_text(value: object, field_name: str, *, maximum: int = 4096) -> str:
    if type(value) is not str or not value.strip() or len(value) > maximum:
        raise FormalTaskViolation(
            "INVALID_P3_ROUTE_ARGUMENT",
            f"{field_name} must be a non-empty string of at most {maximum} characters",
            ErrorCode.INVALID_ARGUMENT,
        )
    return value.strip()


def _resolve_database_path(configured: str) -> Path:
    """Keep formal Store files under the application-owned P3 directory."""

    live_voice_root = get_user_workspace_dir() / "live_voice"
    p3alpha_root = live_voice_root / "p3alpha"
    for component in (live_voice_root, p3alpha_root):
        try:
            attributes = getattr(os.lstat(component), "st_file_attributes", 0)
        except OSError:
            attributes = 0
        if component.is_symlink() or attributes & getattr(
            stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0
        ):
            raise FormalTaskViolation(
                "INVALID_P3_AUTH_CONFIGURATION",
                "P3 database must remain under the application-owned P3 directory",
                ErrorCode.INVALID_ARGUMENT,
            )
    store_root = p3alpha_root.resolve()
    candidate = (
        Path(configured).expanduser()
        if configured
        else store_root / "formal_tasks.sqlite3"
    ).resolve()
    if not candidate.is_relative_to(store_root) or candidate == store_root:
        raise FormalTaskViolation(
            "INVALID_P3_AUTH_CONFIGURATION",
            "P3 database must remain under the application-owned P3 directory",
            ErrorCode.INVALID_ARGUMENT,
        )
    return candidate


def _validate_reconcile_interval(value: float) -> float:
    if not math.isfinite(value) or value <= 0 or value > 3600:
        raise ValueError("reconcile_interval must be in (0, 3600] seconds")
    return value


def _earlier_expiry(left: str, right: str) -> str:
    return left if _parse_utc(left, "expiry") <= _parse_utc(right, "expiry") else right


@dataclass(frozen=True, slots=True)
class AuthenticatedPrincipal:
    """Machine-authenticated identity and its server-side policy grant."""

    principal_id: str
    allowed_project_ids: frozenset[str]
    allowed_operations: frozenset[str]
    expires_at: str

    def require_active(self, *, now: str) -> None:
        if _parse_utc(self.expires_at, "principal.expires_at") <= _parse_utc(
            now, "now"
        ):
            raise FormalTaskViolation(
                "FORMAL_TASK_AUTHORIZATION_EXPIRED",
                "formal task authorization has expired",
                ErrorCode.PERMISSION_DENIED,
            )

    def require_usable(self, *, operation: str, now: str) -> None:
        if operation not in self.allowed_operations:
            raise FormalTaskViolation(
                "FORMAL_TASK_AUTHORIZATION_DENIED",
                "formal task scope is unavailable",
                ErrorCode.PERMISSION_DENIED,
            )
        self.require_active(now=now)


class PrincipalAuthenticator(Protocol):
    def authenticate(
        self, bearer_token: object, *, operation: str, now: str
    ) -> AuthenticatedPrincipal: ...


class StaticBearerAuthenticator:
    """Constant-time verifier for the initial single-principal Web Alpha gate."""

    def __init__(self, *, token: str, principal: AuthenticatedPrincipal) -> None:
        if len(token) < 32:
            raise FormalTaskViolation(
                "INVALID_P3_AUTH_CONFIGURATION",
                "P3 bearer token must contain at least 32 characters",
                ErrorCode.INVALID_ARGUMENT,
            )
        self._token = token
        self._principal = principal

    def authenticate(
        self, bearer_token: object, *, operation: str, now: str
    ) -> AuthenticatedPrincipal:
        candidate = bearer_token if type(bearer_token) is str else ""
        if not candidate or not hmac.compare_digest(candidate, self._token):
            raise FormalTaskViolation(
                "FORMAL_TASK_AUTHENTICATION_REQUIRED",
                "formal task authentication is required",
                ErrorCode.UNAUTHENTICATED,
            )
        self._principal.require_usable(operation=operation, now=now)
        return self._principal

    def validated_configuration_fact(self) -> ValidatedAuthenticationConfiguration:
        """Project exact owner-held authentication configuration without its secret."""

        scope_projection = canonical_json_bytes(
            {
                "principal_id": self._principal.principal_id,
                "allowed_project_ids": sorted(self._principal.allowed_project_ids),
                "allowed_operations": sorted(self._principal.allowed_operations),
                "expires_at": self._principal.expires_at,
                "mode": AuthenticationMode.SCOPED_BEARER.value,
            }
        )
        scope_digest = hashlib.sha256(scope_projection).hexdigest()
        receipt = hmac.new(
            self._token.encode("utf-8"),
            f"live-voice-auth-config\0{scope_digest}".encode("ascii"),
            hashlib.sha256,
        ).hexdigest()
        return ValidatedAuthenticationConfiguration(
            mode=AuthenticationMode.SCOPED_BEARER,
            validation_receipt_id=f"auth-owner.v1.{receipt}",
            scope_digest=scope_digest,
        )

    def validated_allowed_operations(self, *, now: str) -> frozenset[str]:
        """Return the exact currently active operation scope held by this owner."""

        self._principal.require_active(now=now)
        return self._principal.allowed_operations


@dataclass(frozen=True, slots=True)
class ResolvedAuthority:
    principal: AuthenticatedPrincipal
    scope: ScopeRef
    context: ResolvedTaskContext


@dataclass(frozen=True, slots=True, repr=False)
class NativeP3ActivationAuthority:
    """Non-secret activation projection of the existing authenticated principal."""

    principal: AuthenticatedPrincipal = field(repr=False)
    session_id: str
    correlation_id: str
    scope: ScopeRef
    context: ResolvedTaskContext = field(repr=False)

    def __post_init__(self) -> None:
        if (
            not isinstance(self.principal, AuthenticatedPrincipal)
            or type(self.session_id) is not str
            or not self.session_id
            or type(self.correlation_id) is not str
            or not self.correlation_id
            or not isinstance(self.scope, ScopeRef)
            or not isinstance(self.context, ResolvedTaskContext)
            or self.scope != self.context.scope
            or self.scope.subject_id != self.principal.principal_id
            or self.scope.session_id != self.session_id
        ):
            raise FormalTaskViolation(
                "INVALID_NATIVE_P3_ACTIVATION_AUTHORITY",
                "Native P3 activation authority is incomplete",
                ErrorCode.INVALID_ARGUMENT,
            )

    def __repr__(self) -> str:
        return (
            "NativeP3ActivationAuthority("
            f"session_id={self.session_id!r}, "
            f"correlation_id={self.correlation_id!r}, "
            f"expires_at={self.principal.expires_at!r})"
        )


@dataclass(frozen=True, slots=True)
class PreparedProductionIntentAuthority:
    """Authenticated, read-only authority used only while resolving an intent.

    This is not a Task authorization grant.  It exposes the exact authenticated
    Scope and the Store-backed reader needed to resolve a name/reference before
    the final operation and target are freshly authorized by
    ``handle_production_resolution``.
    """

    principal_id: str
    scope: ScopeRef
    reader: StoreProductionTaskAuthorityReader
    observed_at: str


class AuthorityResolver(Protocol):
    def resolve(
        self,
        principal: AuthenticatedPrincipal,
        *,
        session_id: str,
        now: str,
        require_clean: bool,
    ) -> ResolvedAuthority: ...


@dataclass(frozen=True, slots=True)
class _ProjectSnapshot:
    project_id: str
    session_id: str
    project_dir: str
    revision: str


class ServerSessionProjectAuthorityResolver:
    """Resolve an exact project from persisted server session/registry state."""

    def __init__(
        self,
        *,
        session_reader: Callable[[str], Mapping[str, Any] | None] | None = None,
        project_reader: Callable[[str], Any | None] | None = None,
        revision_reader: Callable[[str], tuple[str, str]] | None = None,
        worktree_clean_reader: Callable[[str], bool] | None = None,
        redaction_reader: Callable[
            [Mapping[str, Any], Any], tuple[bool, tuple[str, ...]]
        ]
        | None = None,
    ) -> None:
        self._session_reader = session_reader or self._read_session
        self._project_reader = project_reader or self._read_project
        self._revision_reader = revision_reader or self._read_revision
        self._worktree_clean_reader = worktree_clean_reader or self._is_worktree_clean
        self._redaction_reader = redaction_reader or (
            lambda _session, _project: (False, ())
        )

    @staticmethod
    def _read_session(session_id: str) -> Mapping[str, Any] | None:
        from jiuwenswarm.server.runtime.session.session_metadata import (
            get_session_metadata,
        )

        return get_session_metadata(
            session_id,
            cache_bust=True,
            enable_writeback=False,
        )

    @staticmethod
    def _read_project(project_id: str) -> Any | None:
        from jiuwenswarm.server.runtime.session.project_store import get_project_by_id

        return get_project_by_id(project_id, cache_bust=True)

    @staticmethod
    def _read_revision(project_dir: str) -> tuple[str, str]:
        try:
            revision = subprocess.run(
                ["git", "rev-parse", "--show-toplevel", "HEAD"],
                cwd=project_dir,
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise FormalTaskViolation(
                "TASK_CONTEXT_REVISION_UNAVAILABLE",
                "formal task project revision is unavailable",
                ErrorCode.UNAVAILABLE,
            ) from exc
        lines = revision.stdout.splitlines()
        if revision.returncode != 0 or len(lines) != 2:
            raise FormalTaskViolation(
                "TASK_CONTEXT_REVISION_UNAVAILABLE",
                "formal task project revision is unavailable",
                ErrorCode.UNAVAILABLE,
            )
        return lines[0].strip(), lines[1].strip()

    @staticmethod
    def _is_worktree_clean(project_dir: str) -> bool:
        try:
            status = subprocess.run(
                ["git", "status", "--porcelain=v1", "--untracked-files=all"],
                cwd=project_dir,
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise FormalTaskViolation(
                "TASK_CONTEXT_REVISION_UNAVAILABLE",
                "formal task project revision is unavailable",
                ErrorCode.UNAVAILABLE,
            ) from exc
        if status.returncode != 0:
            raise FormalTaskViolation(
                "TASK_CONTEXT_REVISION_UNAVAILABLE",
                "formal task project revision is unavailable",
                ErrorCode.UNAVAILABLE,
            )
        if status.stdout:
            raise FormalTaskViolation(
                "TASK_CONTEXT_WORKTREE_DIRTY",
                "formal task project must have a clean worktree",
                ErrorCode.PERMISSION_DENIED,
            )
        return True

    @staticmethod
    def _deny_scope() -> FormalTaskViolation:
        return FormalTaskViolation(
            "FORMAL_TASK_AUTHORIZATION_DENIED",
            "formal task scope is unavailable",
            ErrorCode.PERMISSION_DENIED,
        )

    def _snapshot(
        self,
        *,
        session_id: str,
        allowed_project_ids: frozenset[str] | None,
        require_clean: bool,
    ) -> tuple[_ProjectSnapshot, Mapping[str, Any], Any]:
        if not session_id or session_id == "new":
            raise self._deny_scope()
        session = self._session_reader(session_id)
        if not isinstance(session, Mapping) or not session:
            raise self._deny_scope()
        project_id = str(session.get("project_id") or "").strip()
        if not project_id or (
            allowed_project_ids is not None and project_id not in allowed_project_ids
        ):
            # Check the authenticated allow-list before consulting project storage.
            raise self._deny_scope()
        project = self._project_reader(project_id)
        if project is None:
            raise self._deny_scope()
        project_dir = str(getattr(project, "project_dir", "") or "").strip()
        session_dir = str(session.get("project_dir") or "").strip()
        if (
            str(getattr(project, "project_id", "") or "").strip() != project_id
            or not project_dir
            or not session_dir
            or bool(getattr(project, "hidden", False))
            or str(getattr(project, "work_mode", "")).strip().lower() != "code"
        ):
            raise self._deny_scope()
        try:
            selected_key = _path_key(project_dir)
            session_key = _path_key(session_dir)
            root, revision = self._revision_reader(project_dir)
            root_key = _path_key(root)
            if require_clean and not self._worktree_clean_reader(project_dir):
                raise FormalTaskViolation(
                    "TASK_CONTEXT_WORKTREE_DIRTY",
                    "formal task project must have a clean worktree",
                    ErrorCode.PERMISSION_DENIED,
                )
        except FormalTaskViolation:
            # The authenticated caller already passed the exact project
            # allow-list before any project storage was consulted. Preserve
            # negotiated Context/revision reasons such as
            # TASK_CONTEXT_WORKTREE_DIRTY instead of folding them into a
            # generic scope denial; D-069 makes those stable reasons part of
            # retry admission and mutation recovery.
            raise
        except (OSError, RuntimeError, ValueError) as exc:
            raise self._deny_scope() from exc
        if selected_key != session_key or selected_key != root_key or not revision:
            raise self._deny_scope()
        return (
            _ProjectSnapshot(
                project_id, session_id, str(Path(root).resolve()), revision
            ),
            session,
            project,
        )

    def resolve(
        self,
        principal: AuthenticatedPrincipal,
        *,
        session_id: str,
        now: str,
        require_clean: bool,
    ) -> ResolvedAuthority:
        snapshot, session, project = self._snapshot(
            session_id=session_id,
            allowed_project_ids=principal.allowed_project_ids,
            require_clean=require_clean,
        )
        redacted, redacted_fields = self._redaction_reader(session, project)
        scope = ScopeRef(
            principal.principal_id,
            snapshot.project_id,
            snapshot.session_id,
            Assurance.AUTHENTICATED,
        )
        context = ResolvedTaskContext(
            source="agent_server.session_project_registry",
            stable_id=snapshot.project_id,
            uri=Path(snapshot.project_dir).as_uri(),
            revision_kind="version",
            revision_value=snapshot.revision,
            scope=scope,
            permissions=("project.write", "task.execute"),
            expires_at=principal.expires_at,
            redaction_policy_id="live_voice.p3alpha.project.v1",
            redacted=bool(redacted),
            redacted_fields=tuple(redacted_fields),
        )
        return ResolvedAuthority(principal, scope, context)

    def revalidate(
        self,
        context: ResolvedTaskContext,
        *,
        principal: AuthenticatedPrincipal,
        now: str,
        for_dispatch: bool,
    ) -> _ProjectSnapshot:
        principal.require_active(now=now)
        # A persisted redacted/expired/under-permissioned ContextRef remains
        # unusable even if the current registry snapshot is otherwise healthy.
        context.require_usable(
            scope=context.scope,
            required_permissions=frozenset({"task.execute", "project.write"}),
            destructive=True,
            now=now,
        )
        if (
            context.scope.subject_id != principal.principal_id
            or context.stable_id not in principal.allowed_project_ids
        ):
            raise self._deny_scope()
        snapshot, session, project = self._snapshot(
            session_id=context.scope.session_id or "",
            allowed_project_ids=principal.allowed_project_ids,
            require_clean=for_dispatch,
        )
        if context.scope.project_id != snapshot.project_id or _path_key(
            context.file_path or ""
        ) != _path_key(snapshot.project_dir):
            raise self._deny_scope()
        redacted, redacted_fields = self._redaction_reader(session, project)
        current_context = ResolvedTaskContext(
            source=context.source,
            stable_id=context.stable_id,
            uri=context.uri,
            revision_kind=context.revision_kind,
            revision_value=context.revision_value,
            scope=context.scope,
            permissions=context.permissions,
            expires_at=context.expires_at,
            redaction_policy_id=context.redaction_policy_id,
            redacted=bool(redacted),
            redacted_fields=tuple(redacted_fields),
        )
        current_context.require_usable(
            scope=context.scope,
            required_permissions=frozenset({"task.execute", "project.write"}),
            destructive=True,
            now=now,
        )
        if (
            context.revision_kind != "version"
            or context.revision_value != snapshot.revision
        ):
            raise FormalTaskViolation(
                "EXECUTION_CONTEXT_REVISION_MISMATCH",
                "formal task project revision no longer matches its authorization",
                ErrorCode.PERMISSION_DENIED,
            )
        return snapshot


@dataclass(frozen=True, slots=True)
class P3RouteTelemetry:
    operation: str
    outcome: str
    reason: str | None
    duration_ms: int


class P3TelemetrySink(Protocol):
    def emit(self, event: P3RouteTelemetry) -> None: ...


class LoggingP3TelemetrySink:
    def emit(self, event: P3RouteTelemetry) -> None:
        logger.info(
            "[LiveVoiceP3] operation=%s outcome=%s reason=%s duration_ms=%d",
            event.operation,
            event.outcome,
            event.reason,
            event.duration_ms,
        )


@dataclass(frozen=True, slots=True)
class P3RouteResult:
    ok: bool
    payload: dict[str, object]


@dataclass(frozen=True, slots=True)
class PreparedP3MutationConfirmation:
    """Server-resolved facts for confirmation issuance or forwarding."""

    binding: P3ConfirmationBinding
    correlation_id: str
    issued_at: str
    observed_at: str


@dataclass(frozen=True, slots=True)
class _PreparedRetrySnapshot:
    """One frozen retry admission snapshot derived only from server authority.

    ``replayed`` records that the exact predecessor lineage came from the
    durable command ledger rather than from current admission.  That branch is
    evaluated first so a reopened process can prove an already applied retry
    without depending on facts the current task epoch no longer carries.
    """

    precondition: TaskRetryPrecondition
    context: ResolvedTaskContext
    facts: PreparedP3RetryFacts
    correlation_id: str
    product_request: TaskRetryProductRequestFingerprint
    replayed: bool
    selection: PersistedExecutorSelection | None


class ClosableBindingResolver(Protocol):
    async def close(self) -> None: ...


class AgentManagerProjectBindingResolver:
    """Revalidate persisted context and bind the isolated formal Code Agent."""

    def __init__(
        self,
        *,
        authority_resolver: ServerSessionProjectAuthorityResolver,
        agent_manager: Any,
        service: Any,
        model_resolver: P3ModelResolver,
        principal: AuthenticatedPrincipal,
        clock: Callable[[], str] = utc_now,
    ) -> None:
        self._authority_resolver = authority_resolver
        self._agent_manager = agent_manager
        self._service = service
        self._model_resolver = model_resolver
        self._principal = principal
        self._clock = clock
        self._close_lock = asyncio.Lock()
        self._close_requested = False
        self._closed = False

    async def prepare_startup(self) -> int:
        """Recover carrier facts before the formal Core reconciles its outbox."""

        reconcile = getattr(self._service, "reconcile_task_statuses", None)
        if not callable(reconcile):
            return 0
        return int(await reconcile())

    async def resolve(
        self, spec: FormalTaskSpec, *, for_dispatch: bool
    ) -> ProjectExecutionBinding:
        async with self._close_lock:
            return await self._resolve_transition(
                spec,
                for_dispatch=for_dispatch,
            )

    async def _resolve_transition(
        self, spec: FormalTaskSpec, *, for_dispatch: bool
    ) -> ProjectExecutionBinding:
        if self._close_requested or self._closed:
            raise FormalTaskViolation(
                "EXECUTOR_CAPABILITY_UNAVAILABLE",
                "formal project Executor is closed",
                ErrorCode.UNAVAILABLE,
            )
        snapshot = await asyncio.to_thread(
            self._authority_resolver.revalidate,
            spec.context,
            principal=self._principal,
            now=self._clock(),
            for_dispatch=for_dispatch,
        )
        model = None
        attributes = dict(spec.attributes)
        model_identity = attributes.get("model_identity")
        model_config_version = attributes.get("model_config_version")
        execution_agent: Any = None
        project_executor: Any = None
        release: Callable[[], None] | None = None
        dispatch_fence: Callable[[], Awaitable[None]] | None = None
        attempt_executor_factory: (
            Callable[[str], Awaitable[AttemptProjectExecutorLease]] | None
        ) = None
        effective_root = snapshot.project_dir
        if for_dispatch:
            resolved_model = self._model_resolver.resolve(
                model_identity,
                expected_identity=model_identity,
                expected_config_version=model_config_version,
                instantiate=True,
            )
            model = resolved_model.model
            if model is None:
                raise FormalTaskViolation(
                    "P3_MODEL_UNAVAILABLE",
                    "formal task model is unavailable",
                    ErrorCode.CAPABILITY_UNAVAILABLE,
                )
            agent = await self._agent_manager.get_live_voice_formal_task_agent(
                snapshot.project_dir
            )
            if agent is None:
                raise FormalTaskViolation(
                    "EXECUTOR_CAPABILITY_UNAVAILABLE",
                    "formal project Code Agent is unavailable",
                    ErrorCode.CAPABILITY_UNAVAILABLE,
                )
            self._agent_manager.pin_agent(agent)
            released = False

            def release_agent() -> None:
                nonlocal released
                if released:
                    return
                released = True
                self._agent_manager.unpin_agent(agent)

            release = release_agent
            try:
                get_root = getattr(agent, "get_project_execution_root", None)
                effective_root = (
                    get_root() if callable(get_root) else snapshot.project_dir
                )
                # ``get_instance`` is a plain accessor and returns None until
                # the root DeepAgent has been built by the chat path.  A formal
                # task dispatches outside that path on a freshly created
                # project Agent, so it must build the handle it needs; using
                # the accessor left ``execution_agent`` None and failed every
                # real attempt with EXECUTOR_CAPABILITY_UNAVAILABLE.
                execution_agent = await agent.ensure_instance()
                project_executor = agent
            except BaseException:  # noqa: BLE001 -- no acquired pin may be lost
                release()
                raise

            async def require_dispatch_fence() -> None:
                current = await asyncio.to_thread(
                    self._authority_resolver.revalidate,
                    spec.context,
                    principal=self._principal,
                    now=self._clock(),
                    for_dispatch=True,
                )
                if any(
                    getattr(current, field, None) != getattr(snapshot, field, None)
                    for field in ("project_id", "session_id", "project_dir", "revision")
                ):
                    raise FormalTaskViolation(
                        "EXECUTION_CONTEXT_REVISION_MISMATCH",
                        "formal task project changed before Executor handoff",
                        ErrorCode.PERMISSION_DENIED,
                    )
                await asyncio.to_thread(
                    self._model_resolver.resolve,
                    model_identity,
                    expected_identity=model_identity,
                    expected_config_version=model_config_version,
                    instantiate=False,
                )

            dispatch_fence = require_dispatch_fence

            async def acquire_attempt_executor(
                attempt_root: str,
            ) -> AttemptProjectExecutorLease:
                acquire = getattr(
                    self._agent_manager,
                    "acquire_live_voice_formal_task_attempt_agent",
                    None,
                )
                release_attempt = getattr(
                    self._agent_manager,
                    "release_live_voice_formal_task_attempt_agent",
                    None,
                )
                if not callable(acquire) or not callable(release_attempt):
                    raise FormalTaskViolation(
                        "EXECUTOR_CAPABILITY_UNAVAILABLE",
                        "formal attempt Agent leasing is unavailable",
                        ErrorCode.CAPABILITY_UNAVAILABLE,
                    )
                acquisition = await acquire(attempt_root)
                if acquisition is None:
                    raise FormalTaskViolation(
                        "EXECUTOR_CAPABILITY_UNAVAILABLE",
                        "formal attempt Code Agent is unavailable",
                        ErrorCode.CAPABILITY_UNAVAILABLE,
                    )
                attempt_agent = getattr(acquisition, "agent", acquisition)
                initialization_error = getattr(
                    acquisition,
                    "initialization_error",
                    None,
                )
                released = False

                async def release_attempt_agent() -> None:
                    nonlocal released
                    if released:
                        return
                    cleaned = await release_attempt(
                        attempt_root,
                        expected_agent=attempt_agent,
                    )
                    if not cleaned:
                        raise RuntimeError("PROJECT_AGENT_CLEANUP_PENDING")
                    released = True

                return AttemptProjectExecutorLease(
                    project_executor=attempt_agent,
                    # D0 stores ``context_release`` before it calls the real
                    # facade's root getter or checks its stream capability.
                    effective_execution_root=str(attempt_root),
                    context_release=release_attempt_agent,
                    initialization_error=initialization_error,
                )

            attempt_executor_factory = acquire_attempt_executor
        try:
            binding = ProjectExecutionBinding(
                service=self._service,
                execution_agent=execution_agent,
                project_executor=project_executor,
                effective_execution_root=effective_root,
                execution_target={
                    "project_dir": snapshot.project_dir,
                    "project_id": snapshot.project_id,
                    "origin_session_id": snapshot.session_id,
                    "origin_channel_id": "web",
                },
                owner_scope={
                    "channel_id": "formal-task-core",
                    "session_id": snapshot.session_id,
                    "app_id": "live-voice",
                },
                resolved_revision_kind="version",
                resolved_revision_value=snapshot.revision,
                model=model,
                model_identity=model_identity,
                model_config_version=model_config_version,
                context_release=release,
                dispatch_fence=dispatch_fence,
                attempt_executor_factory=attempt_executor_factory,
            )
            if self._close_requested or self._closed:
                if release is not None:
                    release()
                raise FormalTaskViolation(
                    "EXECUTOR_CAPABILITY_UNAVAILABLE",
                    "formal project Executor is closing",
                    ErrorCode.UNAVAILABLE,
                )
            return binding
        except Exception:
            if release is not None:
                release()
            raise

    def _abort_initialization(self) -> None:
        """Synchronously fence a resolver before it can acquire Agent owners."""

        if self._closed:
            return
        if self._close_lock.locked():
            raise RuntimeError("FORMAL_PROJECT_BINDING_INITIALIZATION_ABORT_UNSAFE")
        # The factory never resolves a binding before it returns the composition.
        # Thus no pin, scheduler, execution context, or Agent cleanup is owned,
        # and invoking the broader asynchronous close would be false authority.
        self._close_requested = True
        self._closed = True

    async def close(self) -> None:
        self._close_requested = True
        async with self._close_lock:
            if self._closed:
                return
            cleanup_failures: list[Exception] = []
            scheduler_stopped = self._service is None
            stop_scheduler = getattr(self._service, "stop_scheduler", None)
            if callable(stop_scheduler):
                try:
                    await stop_scheduler(interrupt_running=True)
                    scheduler_stopped = True
                except Exception as exc:  # noqa: BLE001 -- release remaining owners
                    cleanup_failures.append(exc)
                    logger.warning(
                        "[LiveVoiceP3] carrier scheduler shutdown failed: %s", exc
                    )
            clear_contexts = getattr(
                self._service, "clear_scheduled_task_execution_contexts", None
            )
            if not scheduler_stopped and callable(clear_contexts):
                try:
                    clear_contexts()
                except Exception as exc:  # noqa: BLE001 -- release Agent regardless
                    cleanup_failures.append(exc)
                    logger.warning(
                        "[LiveVoiceP3] carrier execution-context cleanup failed: %s",
                        exc,
                    )
            cleanup = getattr(
                self._agent_manager, "cleanup_live_voice_formal_task_agents", None
            )
            if callable(cleanup):
                try:
                    await cleanup()
                except Exception as exc:  # noqa: BLE001 -- retain and retry all owners
                    cleanup_failures.append(exc)
            if cleanup_failures:
                raise RuntimeError(
                    "FORMAL_PROJECT_BINDING_CLEANUP_PENDING: "
                    f"{len(cleanup_failures)} owner cleanup(s) failed"
                ) from cleanup_failures[0]
            # A failed or cancelled cleanup leaves this false, so a later close
            # retries the same retained owners.  New resolves remain fenced by
            # ``_close_requested`` throughout that interval.
            self._closed = True


class _DirectP3RuntimeOwner:
    """Start and close the direct Executor before releasing Agent bindings."""

    def __init__(
        self,
        *,
        executor: DirectProjectCodeExecutorAdapter,
        binding_resolver: AgentManagerProjectBindingResolver,
    ) -> None:
        self._executor = executor
        self._binding_resolver = binding_resolver

    async def prepare_startup(self) -> int:
        return await self._executor.prepare_startup()

    async def close_executor(self) -> None:
        await self._executor.close(interrupt_running=True)
        if self._executor.has_live_workers:
            raise FormalTaskViolation(
                "EXECUTOR_CLOSE_CLEANUP_PENDING",
                "formal attempt workers remain active after bounded shutdown",
                ErrorCode.UNAVAILABLE,
            )

    async def close_bindings(self) -> None:
        await self._binding_resolver.close()

    async def close(self) -> None:
        await self.close_executor()
        await self.close_bindings()


class P3AuthenticatedComposition:
    """Lifecycle owner for authenticated formal P3-alpha task operations."""

    def __init__(
        self,
        *,
        authenticator: PrincipalAuthenticator,
        authority_resolver: AuthorityResolver,
        core: PersistentTaskCore,
        confirmation_verifier: P3ConfirmationVerifier | None = None,
        model_resolver: P3ModelResolver | None = None,
        binding_resolver: ClosableBindingResolver | None = None,
        policy: FormalTaskPolicyAdapter | None = None,
        telemetry: P3TelemetrySink | None = None,
        reconcile_interval: float = 30.0,
        clock: Callable[[], str] = utc_now,
        executor_profiles: tuple[ExecutorCapabilityProfile, ...] | None = None,
        validated_executor_configuration: ValidatedExecutorConfiguration | None = None,
        execution_durability_level: str = "D0",
        admission_policy: AdmissionPolicy = _PRODUCT_ADMISSION_POLICY,
    ) -> None:
        _validate_reconcile_interval(reconcile_interval)
        if executor_profiles is not None and (
            type(executor_profiles) is not tuple
            or not executor_profiles
            or any(
                type(profile) is not ExecutorCapabilityProfile
                for profile in executor_profiles
            )
        ):
            raise TypeError(
                "executor_profiles must be a non-empty tuple of exact profiles"
            )
        if not isinstance(admission_policy, AdmissionPolicy):
            raise TypeError("admission_policy must be an AdmissionPolicy")
        if execution_durability_level not in {"D0", "D1", "D2"}:
            raise ValueError("execution_durability_level must be D0, D1, or D2")
        if validated_executor_configuration is not None:
            if (
                type(validated_executor_configuration)
                is not ValidatedExecutorConfiguration
            ):
                raise TypeError(
                    "validated_executor_configuration must use the exact contract"
                )
            if executor_profiles is None or len(executor_profiles) != 1:
                raise ValueError(
                    "validated Executor configuration requires one selected profile"
                )
            configured_profile = executor_profiles[0]
            if (
                validated_executor_configuration
                != _validated_executor_configuration(configured_profile)
                or execution_durability_level != configured_profile.durability_level
            ):
                raise ValueError(
                    "validated Executor configuration does not match selected profile"
                )
        self._authenticator = authenticator
        self._authority_resolver = authority_resolver
        self._core = core
        task_store = getattr(core, "store", None)
        task_database = getattr(task_store, "database_path", None)
        self._p2_response_generation_database = (
            Path(task_database).with_name(
                f"{Path(task_database).name}.p2-response-generations.sqlite3"
            )
            if task_database is not None
            else None
        )
        self._p2_response_generation_owner: SqliteP2ResponseGenerationOwner | None = (
            None
        )
        self._p2_response_generation_owner_lock = threading.Lock()
        self._confirmation_verifier = confirmation_verifier
        self._model_resolver = model_resolver
        self._binding_resolver = binding_resolver
        self._policy = policy or FormalTaskPolicyAdapter()
        self._telemetry = telemetry or LoggingP3TelemetrySink()
        self._reconcile_interval = reconcile_interval
        self._clock = clock
        self._executor_profiles = executor_profiles
        self._validated_executor_configuration = validated_executor_configuration
        self._execution_durability_level = execution_durability_level
        self._admission_policy = admission_policy
        self._lifecycle_lock = asyncio.Lock()
        self._reconcile_lock = asyncio.Lock()
        self._active_condition = asyncio.Condition()
        self._active_operations = 0
        self._wake = asyncio.Event()
        self._worker: asyncio.Task[None] | None = None
        self._accepting = False
        self._closed = False
        self._cleanup_complete = False
        self._direct_runtime_prepared = False

    @property
    def accepting(self) -> bool:
        return self._accepting

    @property
    def mutation_authority_ready(self) -> bool:
        return self._confirmation_verifier is not None

    @property
    def task_database_path(self) -> Path | None:
        core = getattr(self, "_core", None)
        store = getattr(core, "store", None)
        database = getattr(store, "database_path", None)
        return None if database is None else Path(database)

    @property
    def production_intent_available(self) -> bool:
        """Report whether the formal Store-backed production resolver can run."""

        return isinstance(getattr(self._core, "store", None), SqliteTaskStore)

    def validated_live_voice_configuration(
        self,
        *,
        provider: ValidatedProviderConfiguration,
    ) -> ValidatedLiveVoiceConfiguration:
        """Project exact auth/Executor facts for a non-authoritative declaration.

        The provider fact is issued separately by its owning backend.  This
        method never starts it and cannot turn the resulting declaration into
        authorization.
        """

        if not self._accepting or self._closed:
            raise FormalTaskViolation(
                "P3_CONFIGURATION_OWNER_UNAVAILABLE",
                "formal configuration owner is not accepting",
                ErrorCode.UNAVAILABLE,
            )
        if type(self._authenticator) is not StaticBearerAuthenticator:
            raise FormalTaskViolation(
                "P3_AUTH_CONFIGURATION_UNAVAILABLE",
                "authentication owner cannot project validated configuration",
                ErrorCode.UNAVAILABLE,
            )
        if type(provider) is not ValidatedProviderConfiguration:
            raise FormalTaskViolation(
                "P3_PROVIDER_CONFIGURATION_UNAVAILABLE",
                "provider owner did not supply an exact validated fact",
                ErrorCode.UNAVAILABLE,
            )
        authentication = self._authenticator.validated_configuration_fact()
        allowed_operations = self._authenticator.validated_allowed_operations(
            now=self._clock()
        )
        if not P3_QUERY_OPERATIONS.issubset(allowed_operations):
            raise FormalTaskViolation(
                "P3_QUERY_CONFIGURATION_UNAVAILABLE",
                "authenticated query scope is incomplete",
                ErrorCode.UNAVAILABLE,
            )
        capability_values = [
            LiveVoiceCapability.AUTHENTICATED,
            LiveVoiceCapability.FORMAL_WEB,
            LiveVoiceCapability.TASK_QUERY,
        ]
        executor: ValidatedExecutorConfiguration | None = None
        executor_digest: str | None = None
        mutation_scope = allowed_operations.intersection(
            P3_MUTATIONS | P3_PRODUCTION_MUTATIONS
        )
        confirmation_consumer = getattr(
            self._confirmation_verifier, "verify_and_consume", None
        )
        if self._confirmation_verifier is not None and not callable(
            confirmation_consumer
        ):
            raise FormalTaskViolation(
                "P3_CONFIRMATION_CONFIGURATION_UNAVAILABLE",
                "trusted confirmation consumer is unavailable",
                ErrorCode.UNAVAILABLE,
            )
        mutation_ready = callable(confirmation_consumer) and bool(mutation_scope)
        if mutation_ready:
            if (
                self._executor_profiles is None
                or len(self._executor_profiles) != 1
                or type(self._executor_profiles[0]) is not ExecutorCapabilityProfile
                or type(self._validated_executor_configuration)
                is not ValidatedExecutorConfiguration
            ):
                raise FormalTaskViolation(
                    "P3_EXECUTOR_CONFIGURATION_UNAVAILABLE",
                    "selected Executor profile is unavailable",
                    ErrorCode.UNAVAILABLE,
                )
            profile = self._executor_profiles[0]
            constructed_executor = self._core.executor
            runtime_owner = self._binding_resolver
            if (
                type(constructed_executor) is not DirectProjectCodeExecutorAdapter
                or type(runtime_owner) is not _DirectP3RuntimeOwner
                or runtime_owner._executor is not constructed_executor
                or self._direct_runtime_prepared is not True
            ):
                raise FormalTaskViolation(
                    "P3_EXECUTOR_CONFIGURATION_UNAVAILABLE",
                    "prepared Direct Executor runtime owner is unavailable",
                    ErrorCode.UNAVAILABLE,
                )
            owner_profiles = constructed_executor.capability_profiles()
            if profile not in owner_profiles:
                raise FormalTaskViolation(
                    "P3_EXECUTOR_CONFIGURATION_CONFLICT",
                    "selected Executor profile does not match its constructed owner",
                    ErrorCode.CONFLICT,
                )
            if profile.durability_level != self._execution_durability_level:
                raise FormalTaskViolation(
                    "P3_EXECUTOR_CONFIGURATION_CONFLICT",
                    "Executor durability does not match the selected runtime",
                    ErrorCode.CONFLICT,
                )
            durability = DurabilityLevel(profile.durability_level)
            executor_digest = profile.digest_sha256()
            executor = self._validated_executor_configuration
            if executor != _validated_executor_configuration(profile):
                raise FormalTaskViolation(
                    "P3_EXECUTOR_CONFIGURATION_CONFLICT",
                    "validated Executor configuration does not match its owner",
                    ErrorCode.CONFLICT,
                )
            capability_values.extend(
                (
                    LiveVoiceCapability.TASK_MUTATION,
                    {
                        DurabilityLevel.D0: LiveVoiceCapability.EXECUTOR_D0,
                        DurabilityLevel.D1: LiveVoiceCapability.EXECUTOR_D1,
                        DurabilityLevel.D2: LiveVoiceCapability.EXECUTOR_D2,
                    }[durability],
                )
            )
        if ProviderCapability.TELEMETRY_EXPORT in provider.capabilities:
            capability_values.append(LiveVoiceCapability.TELEMETRY_EXPORT)
        capabilities = tuple(sorted(capability_values, key=lambda item: item.value))
        configuration_projection = canonical_json_bytes(
            {
                "authentication_scope_digest": authentication.scope_digest,
                "executor_profile_digest": executor_digest,
                "provider_id": provider.provider_id,
                "provider_configuration_digest": provider.configuration_digest,
                "capabilities": [item.value for item in capabilities],
            }
        )
        configuration_digest = hashlib.sha256(configuration_projection).hexdigest()
        return ValidatedLiveVoiceConfiguration(
            contract_version=LIVE_VOICE_CONFIGURATION_CONTRACT_VERSION,
            configuration_id="agentserver.formal.live-voice.v1",
            configuration_digest=configuration_digest,
            profile=LiveVoiceDeploymentProfile.FORMAL_LIVE_VOICE,
            enabled=True,
            ordinary_production_default_off=True,
            authentication=authentication,
            executor=executor,
            providers=(provider,),
            capabilities=capabilities,
        )

    def prepare_production_intent_authority(
        self,
        *,
        bearer_token: object,
        operation: str,
        session_id: str,
    ) -> PreparedProductionIntentAuthority:
        """Authenticate one proposal operation and expose read-only Task facts.

        Targeted natural requests may name or describe a Task rather than carry
        its opaque ID.  Consequently this step deliberately does not mint a
        grant or authorize a target.  The final exact operation/target is
        authenticated and reread again by ``handle_production_resolution``.
        """

        if not self._accepting:
            raise FormalTaskViolation(
                "FORMAL_TASK_ROUTE_DISABLED",
                "formal task route is unavailable",
                ErrorCode.UNAVAILABLE,
            )
        if operation not in P3_PRODUCTION_OPERATIONS:
            raise FormalTaskViolation(
                "UNSUPPORTED_FORMAL_TASK_INTENT",
                "production Task intent operation is unsupported",
                ErrorCode.UNSUPPORTED,
            )
        now = self._clock()
        principal = self._authenticator.authenticate(
            bearer_token,
            operation=operation,
            now=now,
        )
        authority = self._authority_resolver.resolve(
            principal,
            session_id=_required_text(session_id, "session_id", maximum=256),
            now=now,
            require_clean=False,
        )
        authority.context.require_usable(
            scope=authority.scope,
            required_permissions=frozenset(),
            destructive=False,
            now=now,
        )
        store = getattr(self._core, "store", None)
        if not isinstance(store, SqliteTaskStore):
            raise FormalTaskViolation(
                "PRODUCTION_TASK_AUTHORITY_UNAVAILABLE",
                "production Task authority requires the formal SQLite Store",
                ErrorCode.UNAVAILABLE,
            )
        collection_selection = (
            self._select_production_create_candidate()
            if operation == "task.create"
            else None
        )
        reader_arguments: dict[str, object] = {
            "store": store,
            "principal_id": principal.principal_id,
            "scope": authority.scope,
            "authority_context_fingerprint": production_context_fingerprint(
                authority.context
            ),
        }
        if collection_selection is not None:
            reader_arguments["collection_capability_profile_digest"] = (
                collection_selection.capability_profile_digest
            )
            if self._model_resolver is None:
                raise FormalTaskViolation(
                    "P3_MODEL_CATALOG_UNAVAILABLE",
                    "production task.create requires model authority",
                    ErrorCode.CAPABILITY_UNAVAILABLE,
                )
            collection_model = self._model_resolver.resolve(
                None,
                instantiate=False,
            )
            reader_arguments["collection_model_binding_fingerprint"] = (
                production_model_binding_fingerprint(
                    {
                        "model_config_version": collection_model.config_version,
                        "model_identity": collection_model.identity,
                    }
                )
            )
        return PreparedProductionIntentAuthority(
            principal_id=principal.principal_id,
            scope=authority.scope,
            reader=StoreProductionTaskAuthorityReader(**reader_arguments),
            observed_at=now,
        )

    def next_product_p2_response_generation(
        self,
        session_id: str,
        interaction_id: str,
        local_prior: int,
    ) -> int:
        """Allocate a restart-stable response generation for formal P2."""

        with self._p2_response_generation_owner_lock:
            owner = self._p2_response_generation_owner
            if owner is None:
                database = self._p2_response_generation_database
                if database is None:
                    raise FormalTaskViolation(
                        "P2_RESPONSE_GENERATION_OWNER_UNAVAILABLE",
                        "durable product response generation owner is unavailable",
                        ErrorCode.UNAVAILABLE,
                    )
                owner = SqliteP2ResponseGenerationOwner(database)
                self._p2_response_generation_owner = owner
            return owner.next_generation(session_id, interaction_id, local_prior)

    def prepare_native_activation_authority(
        self,
        *,
        bearer_token: object,
        session_id: str,
        correlation_id: str,
    ) -> NativeP3ActivationAuthority:
        """Authenticate once without retaining the Native activation's bearer."""

        if not self._accepting:
            raise FormalTaskViolation(
                "FORMAL_TASK_ROUTE_DISABLED",
                "formal task route is unavailable",
                ErrorCode.UNAVAILABLE,
            )
        now = self._clock()
        principal = self._authenticator.authenticate(
            bearer_token,
            operation=_PRODUCT_P2_OPERATION,
            now=now,
        )
        resolved = self._authority_resolver.resolve(
            principal,
            session_id=session_id,
            now=now,
            require_clean=False,
        )
        resolved.context.require_usable(
            scope=resolved.scope,
            required_permissions=frozenset({"task.execute", "project.write"}),
            destructive=False,
            now=now,
        )
        return NativeP3ActivationAuthority(
            principal=principal,
            session_id=session_id,
            correlation_id=correlation_id,
            scope=resolved.scope,
            context=resolved.context,
        )

    def _resolve_native_activation_authority(
        self,
        authority: NativeP3ActivationAuthority,
        *,
        operation: str,
        session_id: str,
        now: str,
        require_clean: bool,
    ) -> ResolvedAuthority:
        if (
            not isinstance(authority, NativeP3ActivationAuthority)
            or authority.session_id != session_id
        ):
            raise FormalTaskViolation(
                "NATIVE_P3_ACTIVATION_AUTHORITY_MISMATCH",
                "Native Task operation does not match its activation authority",
                ErrorCode.PERMISSION_DENIED,
            )
        authority.principal.require_usable(operation=operation, now=now)
        current = self._authority_resolver.resolve(
            authority.principal,
            session_id=session_id,
            now=now,
            require_clean=require_clean,
        )
        if (
            current.scope != authority.scope
            or current.context.scope != authority.context.scope
            or current.context.source != authority.context.source
            or current.context.stable_id != authority.context.stable_id
            or current.context.uri != authority.context.uri
        ):
            raise FormalTaskViolation(
                "EXECUTION_CONTEXT_SCOPE_MISMATCH",
                "Native Task authority no longer matches the activated project",
                ErrorCode.PERMISSION_DENIED,
            )
        return current

    def resolve_product_authority_candidate(
        self,
        *,
        bearer_token: object,
        operation: str,
        session_id: str,
        correlation_id: str,
        required_capabilities: frozenset[str],
        task_id: str | None = None,
        consumer_task_access: bool = False,
    ) -> tuple[TrustedAuthorityCandidate, ResolvedTaskContext]:
        """Authenticate and resolve one product-composition candidate.

        This is the only production bridge from the Alpha bearer gate and the
        server-owned Session/Project registry into ``ProductAuthorityService``.
        The returned candidate is still validated and narrowed by that service;
        browser fields remain comparison inputs and never become grants.
        """

        if not self._accepting:
            raise FormalTaskViolation(
                "FORMAL_TASK_ROUTE_DISABLED",
                "formal task route is unavailable",
                ErrorCode.UNAVAILABLE,
            )
        if operation not in P3_PRODUCT_AUTHORITY_OPERATIONS | {_PRODUCT_P2_OPERATION}:
            raise FormalTaskViolation(
                "FORMAL_TASK_AUTHORIZATION_DENIED",
                "formal product operation is unavailable",
                ErrorCode.PERMISSION_DENIED,
            )
        if operation == "task.retry":
            # Retry authority is only reachable through the confirmation-bound
            # product mutation route, never through query-style registration.
            raise FormalTaskViolation(
                "FORMAL_TASK_AUTHORIZATION_DENIED",
                "task.retry requires the confirmation-bound product mutation route",
                ErrorCode.PERMISSION_DENIED,
            )
        if required_capabilities != frozenset({operation}):
            raise FormalTaskViolation(
                "FORMAL_TASK_AUTHORIZATION_DENIED",
                "formal product capability is unavailable",
                ErrorCode.PERMISSION_DENIED,
            )
        if type(consumer_task_access) is not bool or (
            consumer_task_access and operation != "task.events"
        ):
            raise FormalTaskViolation(
                "INVALID_P3_ROUTE_ARGUMENT",
                "stable consumer access is limited to server progress activation",
                ErrorCode.INVALID_ARGUMENT,
            )
        targeted = operation in {
            "task.get",
            "task.status",
            "task.events",
            "task.result",
            "task.unread_events",
            "task.ack_events",
            "task.update",
            "task.adjust",
            "task.reprioritize",
            "task.cancel",
            "task.create_successor",
        }
        if targeted != bool(task_id):
            raise FormalTaskViolation(
                "INVALID_P3_ROUTE_ARGUMENT",
                "formal product target is incomplete",
                ErrorCode.INVALID_ARGUMENT,
            )

        now = self._clock()
        principal = self._authenticator.authenticate(
            bearer_token,
            operation=operation,
            now=now,
        )
        authority = self._authority_resolver.resolve(
            principal,
            session_id=session_id,
            now=now,
            require_clean=False,
        )
        authority.context.require_usable(
            scope=authority.scope,
            required_permissions=(
                frozenset({"task.execute", "project.write"})
                if operation == _PRODUCT_P2_OPERATION
                else frozenset()
            ),
            destructive=False,
            now=now,
        )
        if targeted:
            if operation in P3_PRESENTATION_OPERATIONS | {"task.result"} or (
                operation == "task.events" and consumer_task_access
            ):
                self._require_consumer_task_context(
                    authority=authority,
                    operation=operation,
                    task_id=str(task_id),
                    now=now,
                )
            else:
                self._require_exact_task_context(
                    authority=authority,
                    operation=operation,
                    task_id=str(task_id),
                    now=now,
                )

        resource = (
            None
            if task_id is None
            else AuthorityResourceBinding(
                kind="task",
                resource_id=task_id,
                fingerprint_sha256=hashlib.sha256(task_id.encode("utf-8")).hexdigest(),
            )
        )
        return (
            TrustedAuthorityCandidate(
                principal_id=principal.principal_id,
                session_id=authority.scope.session_id or "",
                project_id=authority.scope.project_id,
                scope=authority.scope,
                allowed_operations=frozenset({operation}),
                allowed_capabilities=required_capabilities,
                expires_at=principal.expires_at,
                assurance=Assurance.AUTHENTICATED,
                source="agent_server.product_composition",
                correlation_id=correlation_id,
                resource=resource,
            ),
            authority.context,
        )

    def query(
        self,
        query: ProductP3AuthorizedQuery,
        *,
        now: str | None = None,
    ) -> ResultEnvelope:
        """Revalidate one prepared product query before entering Task Core."""

        if not self._accepting or not isinstance(query, ProductP3AuthorizedQuery):
            raise FormalTaskViolation(
                "FORMAL_TASK_ROUTE_DISABLED",
                "formal task route is unavailable",
                ErrorCode.UNAVAILABLE,
            )
        observed_at = now or self._clock()
        canonical = query.authority.authority
        principal = AuthenticatedPrincipal(
            principal_id=canonical.principal_id,
            allowed_project_ids=(
                frozenset()
                if canonical.project_id is None
                else frozenset({canonical.project_id})
            ),
            allowed_operations=frozenset({canonical.operation}),
            expires_at=canonical.expires_at,
        )
        current = self._authority_resolver.resolve(
            principal,
            session_id=canonical.session_id,
            now=observed_at,
            require_clean=False,
        )
        if current.scope != canonical.scope:
            raise FormalTaskViolation(
                "EXECUTION_CONTEXT_SCOPE_MISMATCH",
                "formal task context no longer matches the authenticated project",
                ErrorCode.PERMISSION_DENIED,
            )
        operation = canonical.operation
        target_task_id = query.authorization.target_task_id
        if operation in {"task.get", "task.status", "task.events", "task.result"}:
            self._require_exact_task_context(
                authority=current,
                operation=operation,
                task_id=str(target_task_id or ""),
                now=observed_at,
            )
        elif operation == "task.list":
            payload = query.envelope.payload
            self._require_list_task_contexts(
                authority=current,
                now=observed_at,
                cursor=payload.get("cursor"),
                limit=payload.get("limit", 50),
            )
        else:
            raise FormalTaskViolation(
                "UNSUPPORTED_FORMAL_TASK_INTENT",
                "formal task operation is unsupported",
                ErrorCode.UNSUPPORTED,
            )
        result = self._core.query(
            query.envelope,
            query.authorization,
            now=observed_at,
        )
        if operation == "task.list":
            self._require_list_result_contexts(
                authority=current,
                result=result,
                now=observed_at,
            )
        return result

    def create_product_subscription(
        self,
        authorization: TaskAuthorizationGrant,
        binding: TaskProgressOriginBinding,
    ) -> TaskEventSubscription:
        """Create one authority-replaying exact-task reader for text/UI projection."""

        if not self._accepting:
            raise FormalTaskViolation(
                "FORMAL_TASK_ROUTE_DISABLED",
                "formal task route is unavailable",
                ErrorCode.UNAVAILABLE,
            )
        if (
            not isinstance(authorization, TaskAuthorizationGrant)
            or not isinstance(binding, TaskProgressOriginBinding)
            or authorization.scope != binding.scope
            or authorization.operation != "task.events"
            or authorization.target_task_id != binding.task_id
        ):
            raise FormalTaskViolation(
                "FORMAL_TASK_AUTHORIZATION_DENIED",
                "formal task subscription binding is unavailable",
                ErrorCode.PERMISSION_DENIED,
            )
        return TaskEventSubscription(
            source=self._core.store,
            authorization=authorization,
            scope=binding.scope,
            task_id=binding.task_id,
            enabled=True,
            queue_capacity=256,
            validation_capacity=4096,
            authority_atomic_replay=True,
        )

    def create_product_progress_source(
        self,
        authorization: TaskAuthorizationGrant,
        binding: TaskProgressOriginBinding,
    ) -> TaskEventAuthorityProgressSource:
        """Create the Store-owned atomic cursor handoff required by voice."""

        if not self._accepting:
            raise FormalTaskViolation(
                "FORMAL_TASK_ROUTE_DISABLED",
                "formal task route is unavailable",
                ErrorCode.UNAVAILABLE,
            )
        if (
            not isinstance(authorization, TaskAuthorizationGrant)
            or not isinstance(binding, TaskProgressOriginBinding)
            or authorization.scope != binding.scope
            or authorization.operation != "task.events"
            or authorization.target_task_id != binding.task_id
        ):
            raise FormalTaskViolation(
                "FORMAL_TASK_AUTHORIZATION_DENIED",
                "formal voice progress source binding is unavailable",
                ErrorCode.PERMISSION_DENIED,
            )
        store = self._core.store
        if type(store) is not SqliteTaskStore:
            raise FormalTaskViolation(
                "TASK_PROGRESS_AUTHORITY_HANDOFF_UNAVAILABLE",
                "voice progress requires the concrete SQLite Task authority",
                ErrorCode.CAPABILITY_UNAVAILABLE,
            )
        return TaskEventAuthorityProgressSource(
            store=store,
            authorization=authorization,
            scope=binding.scope,
            task_id=binding.task_id,
            consumer_scope=True,
            presentation_class=(
                "voice"
                if binding.origin_kind is TaskProgressOriginKind.VOICE
                else "text"
            ),
            clock=self._clock,
        )

    @property
    def product_progress_authority_atomic_replay(self) -> bool:
        """Whether text/UI progress can use the same Store cursor handoff."""

        core = getattr(self, "_core", None)
        return (
            core is not None and type(getattr(core, "store", None)) is SqliteTaskStore
        )

    @property
    def product_presentation_consumption_available(self) -> bool:
        """Whether this composition owns the canonical Core/Store ACK seam."""

        core = getattr(self, "_core", None)
        return isinstance(core, PersistentTaskCore) and isinstance(
            getattr(core, "store", None), SqliteTaskStore
        )

    async def start(self) -> dict[str, int]:
        async with self._lifecycle_lock:
            if self._accepting:
                return {}
            if self._closed:
                raise FormalTaskViolation(
                    "FORMAL_TASK_ROUTE_DISABLED",
                    "formal task composition is closed",
                    ErrorCode.UNAVAILABLE,
                )
            if self._binding_resolver is not None:
                prepare_startup = getattr(
                    self._binding_resolver, "prepare_startup", None
                )
                if callable(prepare_startup):
                    await prepare_startup()
                    if isinstance(self._binding_resolver, _DirectP3RuntimeOwner):
                        self._direct_runtime_prepared = True
            summary = await self.reconcile_once()
            worker = asyncio.create_task(
                self._reconcile_loop(), name="live-voice-p3-reconciliation"
            )
            async with self._active_condition:
                self._worker = worker
                self._accepting = True
            return summary

    async def stop(self) -> None:
        async with self._lifecycle_lock:
            if self._cleanup_complete:
                return
            self._closed = True
            was_started = self._worker is not None
            async with self._active_condition:
                self._accepting = False
                while self._active_operations:
                    await self._active_condition.wait()

            # An admitted create/cancel may have persisted an outbox item while
            # shutdown was fencing the route. Deliver that exact item before
            # closing the carrier; failures remain durable for restart recovery.
            if was_started:
                try:
                    await self.reconcile_once()
                except Exception as exc:  # noqa: BLE001 -- continue resource release
                    logger.warning(
                        "[LiveVoiceP3] final shutdown reconciliation failed: %s", exc
                    )

            worker = self._worker
            self._worker = None
            if worker is not None and not worker.done():
                # Ask the periodic worker to leave through its normal wake
                # path.  Cancelling asyncio.wait_for(Event.wait()) can retain
                # its child waiter on the Windows proactor loop, leaving this
                # shutdown permanently stuck in the cancelling state.
                self._wake.set()
                await worker
            # Drain an externally requested reconcile_once before carrier close.
            async with self._reconcile_lock:
                pass
            binding_resolver = self._binding_resolver
            if isinstance(binding_resolver, _DirectP3RuntimeOwner):
                await binding_resolver.close_executor()
                if self._direct_runtime_prepared:
                    status_summary = await self._core.reconcile_status()
                    if status_summary["unavailable"] or status_summary["superseded"]:
                        raise FormalTaskViolation(
                            "EXECUTOR_CLOSE_CLEANUP_PENDING",
                            "formal attempt status remains unsettled after shutdown",
                            ErrorCode.UNAVAILABLE,
                        )
                await binding_resolver.close_bindings()
                self._direct_runtime_prepared = False
            elif binding_resolver is not None:
                await binding_resolver.close()
            self._cleanup_complete = True

    async def _enter_operation(self) -> None:
        async with self._active_condition:
            if not self._accepting:
                raise FormalTaskViolation(
                    "FORMAL_TASK_ROUTE_DISABLED",
                    "formal task route is unavailable",
                    ErrorCode.UNAVAILABLE,
                )
            self._active_operations += 1

    async def _leave_operation(self) -> None:
        async with self._active_condition:
            self._active_operations -= 1
            if self._active_operations == 0:
                self._active_condition.notify_all()

    @staticmethod
    async def _run_blocking(
        callable_: Callable[..., Any], /, *args: Any, **kwargs: Any
    ) -> Any:
        """Do not release shutdown ownership while a submitted thread still runs."""

        task = asyncio.create_task(asyncio.to_thread(callable_, *args, **kwargs))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            try:
                await task
            except Exception:  # noqa: BLE001 -- preserve caller cancellation
                logger.exception("[LiveVoiceP3] cancelled blocking route work failed")
            raise

    async def reconcile_once(self) -> dict[str, int]:
        async with self._reconcile_lock:
            return await self._core.reconcile()

    async def _reconcile_loop(self) -> None:
        while True:
            try:
                await asyncio.wait_for(
                    self._wake.wait(), timeout=self._reconcile_interval
                )
            except TimeoutError:
                pass
            self._wake.clear()
            if self._closed:
                return
            try:
                await self.reconcile_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 -- keep periodic recovery alive
                logger.exception("[LiveVoiceP3] reconciliation failed: %s", exc)

    def _require_exact_task_context(
        self,
        *,
        authority: ResolvedAuthority,
        operation: str,
        task_id: str,
        now: str,
    ) -> None:
        task = self._core.store.get_task(task_id, authority.scope)
        self._require_task_context(
            authority=authority,
            operation=operation,
            context=task.spec.context,
            now=now,
        )

    @staticmethod
    def _require_task_context(
        *,
        authority: ResolvedAuthority,
        operation: str,
        context: ResolvedTaskContext,
        now: str,
    ) -> None:
        destructive = operation in P3_MUTATIONS | P3_PRODUCTION_MUTATIONS
        context.require_usable(
            scope=authority.scope,
            required_permissions=(
                frozenset({"task.execute", "project.write"})
                if destructive
                else frozenset()
            ),
            destructive=destructive,
            now=now,
        )
        persisted = context
        current = authority.context
        if (
            persisted.scope != current.scope
            or persisted.stable_id != current.stable_id
            or persisted.uri != current.uri
        ):
            raise FormalTaskViolation(
                "EXECUTION_CONTEXT_SCOPE_MISMATCH",
                "formal task context no longer matches the authenticated project",
                ErrorCode.PERMISSION_DENIED,
            )
        if operation in P3_QUERY_OPERATIONS | P3_PRESENTATION_OPERATIONS:
            # These are historical, read-only Task Core queries.  D-069 permits
            # a clean checkpoint to advance the same project's revision between
            # attempts; status/events must remain readable so the product can
            # inspect and confirm the bounded retry that follows.  Scope,
            # stable project identity, path, expiry and redaction were all
            # revalidated above.  Mutations still require either exact revision
            # equality (cancel) or the dedicated clean retry admission.
            return
        if (
            persisted.revision_kind != current.revision_kind
            or persisted.revision_value != current.revision_value
        ):
            raise FormalTaskViolation(
                "EXECUTION_CONTEXT_REVISION_MISMATCH",
                "formal task project revision no longer matches its authorization",
                ErrorCode.PERMISSION_DENIED,
            )

    def _require_list_task_contexts(
        self,
        *,
        authority: ResolvedAuthority,
        now: str,
        cursor: str | None = None,
        limit: int = 50,
    ) -> None:
        tasks, _next_cursor, _has_more = self._core.store.list_tasks_page(
            authority.scope,
            cursor=cursor,
            limit=limit,
        )
        for task in tasks:
            self._require_task_context(
                authority=authority,
                operation="task.list",
                context=task.spec.context,
                now=now,
            )

    def _require_list_result_contexts(
        self,
        *,
        authority: ResolvedAuthority,
        result: ResultEnvelope,
        now: str,
    ) -> None:
        """Revalidate the exact returned page after its authoritative read."""

        if not result.ok:
            return
        payload = result.result
        tasks = None if not isinstance(payload, Mapping) else payload.get("tasks")
        if not isinstance(tasks, list):
            raise FormalTaskViolation(
                "FORMAL_TASK_LIST_RESULT_INVALID",
                "formal task list result is malformed",
                ErrorCode.INTERNAL,
            )
        for raw_task in tasks:
            if not isinstance(raw_task, Mapping):
                raise FormalTaskViolation(
                    "FORMAL_TASK_LIST_RESULT_INVALID",
                    "formal task list result is malformed",
                    ErrorCode.INTERNAL,
                )
            task_id = raw_task.get("task_id")
            if type(task_id) is not str or not task_id:
                raise FormalTaskViolation(
                    "FORMAL_TASK_LIST_RESULT_INVALID",
                    "formal task list result is malformed",
                    ErrorCode.INTERNAL,
                )
            self._require_exact_task_context(
                authority=authority,
                operation="task.list",
                task_id=task_id,
                now=now,
            )

    @staticmethod
    def _require_retry_task_identity(
        *,
        authority: ResolvedAuthority,
        context: ResolvedTaskContext,
        now: str,
    ) -> None:
        """Prove the persisted task still names the same clean project identity.

        ``task.retry`` deliberately does not require revision equality: D-069
        allows an externally established clean checkpoint to advance the project
        revision between attempts.  Stable identity, scope, permission, expiry
        and redaction facts are all revalidated instead, and the clean-worktree
        guard remains owned by the authority resolver.
        """

        context.require_usable(
            scope=authority.scope,
            required_permissions=frozenset({"task.execute", "project.write"}),
            destructive=True,
            now=now,
        )
        current = authority.context
        if (
            context.scope != current.scope
            or context.source != current.source
            or context.stable_id != current.stable_id
            or context.uri != current.uri
        ):
            raise FormalTaskViolation(
                "EXECUTION_CONTEXT_SCOPE_MISMATCH",
                "formal task context no longer matches the authenticated project",
                ErrorCode.PERMISSION_DENIED,
            )

    @staticmethod
    def _retry_product_request(
        clean: Mapping[str, Any],
    ) -> TaskRetryProductRequestFingerprint:
        """Digest only the immutable product-owned facts of one retry request.

        Server-derived predecessor, context, readiness and checkout facts are
        excluded on purpose, and so are the transport ``request_id`` and the
        per-issue ``confirmation_id``.  A reopened process that resubmits the
        same external request therefore reproduces this digest and replays the
        applied command instead of admitting a second attempt.
        """

        return TaskRetryProductRequestFingerprint(
            hashlib.sha256(
                canonical_json_bytes(
                    {
                        "operation": "task.retry",
                        "command_id": str(clean["command_id"]),
                        "target_task_id": str(clean["task_id"]),
                        "session_id": str(clean["session_id"]),
                        "correlation_id": str(clean["correlation_id"]),
                        "issued_at": str(clean["issued_at"]),
                    }
                )
            ).hexdigest()
        )

    @staticmethod
    def _retry_facts(
        spec: FormalTaskSpec,
        precondition: TaskRetryPrecondition,
    ) -> PreparedP3RetryFacts:
        return PreparedP3RetryFacts(
            previous_attempt_id=precondition.previous_attempt_id,
            previous_outcome=precondition.previous_outcome.value,
            attempt_number=precondition.attempt_number,
            name=spec.name,
            instruction=spec.instruction,
            executor_id=spec.executor_id,
            required_capabilities=tuple(spec.required_capabilities),
            side_effect_class=spec.side_effect_class,
            attributes=tuple(spec.attributes),
        )

    def _require_retry_executor(self, spec: FormalTaskSpec) -> None:
        """Reject a retry whose original Executor cannot serve this Task Core."""

        if spec.executor_id != self._core.executor.executor_id:
            raise FormalTaskViolation(
                "EXECUTOR_CAPABILITY_UNAVAILABLE",
                "the original task Executor is not available in this Task Core",
                ErrorCode.CAPABILITY_UNAVAILABLE,
            )
        if spec.side_effect_class != "project_mutation":
            raise FormalTaskViolation(
                "EXECUTOR_SIDE_EFFECT_CLASS_MISMATCH",
                "project Code Agent tasks require project_mutation side effects",
                ErrorCode.CAPABILITY_UNAVAILABLE,
            )

    @staticmethod
    def _resolved_create_spec(
        command: CommandEnvelope,
        context: ResolvedTaskContext,
    ) -> FormalTaskSpec:
        """Close the exact Task spec before selecting an Executor profile."""

        if command.command_type != "task.create":
            raise FormalTaskViolation(
                "INVALID_TASK_CREATE_INTENT",
                "Executor selection requires an exact task.create command",
                ErrorCode.PROTOCOL_VIOLATION,
            )
        payload = command.payload
        attributes = payload.get("attributes")
        if type(attributes) is not dict:
            raise FormalTaskViolation(
                "INVALID_FORMAL_TASK_ATTRIBUTES",
                "task attributes must be a string map",
                ErrorCode.INVALID_ARGUMENT,
            )
        return FormalTaskSpec(
            name=payload.get("name"),
            instruction=payload.get("instruction"),
            origin=command.origin,
            context=context,
            executor_id=payload.get("executor_id"),
            required_capabilities=tuple(command.required_capabilities),
            side_effect_class=payload.get("side_effect_class"),
            attributes=tuple(sorted(attributes.items())),
        )

    def _select_create_executor(
        self,
        command: CommandEnvelope,
        context: ResolvedTaskContext | None,
    ) -> PersistedExecutorSelection | None:
        """Select statically before Core can create Store or project effects."""

        if self._executor_profiles is None:
            return None
        if context is None:
            raise FormalTaskViolation(
                "FORMAL_TASK_CONTEXT_REQUIRED",
                "task.create requires server-resolved project context",
                ErrorCode.PERMISSION_DENIED,
            )
        spec = self._resolved_create_spec(command, context)
        requirements = _product_execution_requirements(
            executor_id=spec.executor_id,
            side_effect_class=spec.side_effect_class,
            durability_level=self._execution_durability_level,
        )
        return _persisted_executor_selection(
            select_executor(self._executor_profiles, requirements)
        )

    def _select_production_create_candidate(self) -> PersistedExecutorSelection:
        """Freeze the exact product create capability before confirmation."""

        if self._executor_profiles is None:
            raise FormalTaskViolation(
                "EXECUTOR_CAPABILITY_UNAVAILABLE",
                "production task.create requires an Executor capability candidate",
                ErrorCode.CAPABILITY_UNAVAILABLE,
            )
        requirements = _product_execution_requirements(
            executor_id=FORMAL_PROJECT_EXECUTOR_ID,
            side_effect_class="project_mutation",
            durability_level=self._execution_durability_level,
        )
        return _persisted_executor_selection(
            select_executor(self._executor_profiles, requirements)
        )

    def _resolve_retry_snapshot(
        self,
        *,
        authority: ResolvedAuthority,
        clean: Mapping[str, Any],
        now: str,
    ) -> _PreparedRetrySnapshot:
        """Freeze one exact retry admission without accepting client lineage.

        Durable replay is evaluated before current admission so an already
        applied command resolves from the command ledger even after the task
        advanced.  Both branches produce a read-only snapshot: no attempt,
        event, outbox, command, Executor, worktree or Git state is touched.

        ``correlation_id`` is server-derived like every other retry lineage
        fact.  The Store binds each admission command to the task's own
        correlation identity, so a client-declared value must never reach the
        command envelope.  The replay branch reuses the originally persisted
        value because the durable command fingerprint covers it.
        """

        task_id = str(clean["task_id"])
        product_request = self._retry_product_request(clean)
        replay = self._core.read_applied_retry_replay(
            scope=authority.scope,
            command_id=str(clean["command_id"]),
            task_id=task_id,
            product_request=product_request,
        )
        if replay is not None:
            replayed_spec = replay.resulting_spec
            self._require_retry_executor(replayed_spec)
            replay_result = replay.original_result.result
            if (
                replay_result is None
                or type(replay_result.get("attempt_id")) is not str
            ):
                raise FormalTaskViolation(
                    "TASK_RETRY_REPLAY_BINDING_MISMATCH",
                    "applied retry replay does not identify its durable successor",
                    ErrorCode.PROTOCOL_VIOLATION,
                )
            replayed_attempt = self._core.store.get_attempt(
                str(replay_result["attempt_id"])
            )
            if replayed_attempt.task_id != task_id:
                raise FormalTaskViolation(
                    "TASK_RETRY_REPLAY_BINDING_MISMATCH",
                    "applied retry replay does not bind its durable successor",
                    ErrorCode.PROTOCOL_VIOLATION,
                )
            return _PreparedRetrySnapshot(
                precondition=replay.precondition,
                context=replayed_spec.context,
                facts=self._retry_facts(replayed_spec, replay.precondition),
                correlation_id=replay.original_command.correlation_id,
                product_request=product_request,
                replayed=True,
                selection=replayed_attempt.selection,
            )
        snapshot = self._core.read_current_retry_authority(
            scope=authority.scope,
            task_id=task_id,
        )
        spec = snapshot.task.spec
        self._require_retry_executor(spec)
        self._require_retry_task_identity(
            authority=authority,
            context=spec.context,
            now=now,
        )
        return _PreparedRetrySnapshot(
            precondition=snapshot.precondition,
            context=authority.context,
            facts=self._retry_facts(spec, snapshot.precondition),
            correlation_id=snapshot.task.correlation_id,
            product_request=product_request,
            replayed=False,
            selection=snapshot.attempt.selection,
        )

    async def _read_status_retry_admission(
        self,
        *,
        principal: AuthenticatedPrincipal,
        session_id: str,
        task_id: str,
        now: str,
    ) -> dict[str, object]:
        """Return one authoritative, read-only retry decision for task.status."""

        try:
            if "task.retry" not in principal.allowed_operations:
                raise FormalTaskViolation(
                    "FORMAL_TASK_AUTHORIZATION_DENIED",
                    "task.retry is unavailable to the authenticated principal",
                    ErrorCode.PERMISSION_DENIED,
                )
            authority = await self._run_blocking(
                self._authority_resolver.resolve,
                principal,
                session_id=session_id,
                now=now,
                require_clean=True,
            )
            authority.context.require_usable(
                scope=authority.scope,
                required_permissions=frozenset({"task.execute", "project.write"}),
                destructive=True,
                now=now,
            )
            snapshot = await self._run_blocking(
                self._core.read_current_retry_admission,
                scope=authority.scope,
                task_id=task_id,
            )
            spec = snapshot.task.spec
            self._require_retry_executor(spec)
            self._require_retry_task_identity(
                authority=authority,
                context=spec.context,
                now=now,
            )
            return {
                "eligible": True,
                "reason": "TASK_RETRY_ELIGIBLE",
                "task_id": snapshot.task.task_id,
                "attempt_id": snapshot.attempt.attempt_id,
                "attempt_number": snapshot.precondition.attempt_number,
            }
        except FormalTaskViolation as exc:
            return {
                "eligible": False,
                "reason": exc.reason,
                "task_id": task_id,
                "attempt_id": None,
                "attempt_number": None,
            }

    async def read_product_status_retry_admission(
        self,
        *,
        bearer_token: object,
        session_id: str,
        task_id: str,
    ) -> dict[str, object]:
        """Re-derive retry admission for the authenticated product status path.

        Product P3 queries intentionally enter Task Core through the injected
        query-owner seam instead of :meth:`handle`.  Keep the retry decision on
        that real product path without trusting the narrowed query authority:
        authenticate the original bearer again, then re-read clean Context,
        Store lineage and Executor readiness through the same helper used by
        the direct route.  This method is read-only and owns shutdown exactly
        like the other public composition operations.
        """

        entered = False
        try:
            await self._enter_operation()
            entered = True
            now = self._clock()
            principal = self._authenticator.authenticate(
                bearer_token,
                operation="task.status",
                now=now,
            )
            return await self._read_status_retry_admission(
                principal=principal,
                session_id=session_id,
                task_id=task_id,
                now=now,
            )
        finally:
            if entered:
                await self._leave_operation()

    async def read_product_status_diagnostics(
        self,
        *,
        bearer_token: object,
        session_id: str,
        task_id: str,
    ) -> TaskDurabilityDiagnosticSnapshot:
        """Return authenticated Store diagnostics without business content."""

        entered = False
        try:
            await self._enter_operation()
            entered = True
            now = self._clock()
            principal = self._authenticator.authenticate(
                bearer_token,
                operation="task.status",
                now=now,
            )
            authority = await self._run_blocking(
                self._authority_resolver.resolve,
                principal,
                session_id=session_id,
                now=now,
                require_clean=False,
            )
            authority.context.require_usable(
                scope=authority.scope,
                required_permissions=frozenset(),
                destructive=False,
                now=now,
            )
            await self._run_blocking(
                self._require_exact_task_context,
                authority=authority,
                operation="task.status",
                task_id=task_id,
                now=now,
            )
            return await self._run_blocking(
                self._core.store.read_task_durability_diagnostics,
                scope=authority.scope,
                task_id=task_id,
            )
        finally:
            if entered:
                await self._leave_operation()

    async def read_current_background_task(
        self,
        *,
        bearer_token: object,
        session_id: str,
    ) -> PersistentTaskRecord | None:
        """Restore only the Store-bound current task for one authenticated Session."""

        entered = False
        try:
            await self._enter_operation()
            entered = True
            now = self._clock()
            principal = self._authenticator.authenticate(
                bearer_token,
                operation="task.status",
                now=now,
            )
            authority = await self._run_blocking(
                self._authority_resolver.resolve,
                principal,
                session_id=session_id,
                now=now,
                require_clean=False,
            )
            current = await self._run_blocking(
                self._core.store.get_current_background_task,
                authority.scope,
                session_id=session_id,
            )
            if current is not None:
                await self._run_blocking(
                    self._require_exact_task_context,
                    authority=authority,
                    operation="task.status",
                    task_id=current.task_id,
                    now=now,
                )
            return current
        finally:
            if entered:
                await self._leave_operation()

    async def read_current_background_task_native(
        self,
        authority: NativeP3ActivationAuthority,
        *,
        session_id: str,
    ) -> PersistentTaskRecord | None:
        """Read current Task through the retained principal, never a bearer."""

        entered = False
        try:
            await self._enter_operation()
            entered = True
            now = self._clock()
            resolved = await self._run_blocking(
                self._resolve_native_activation_authority,
                authority,
                operation="task.status",
                session_id=session_id,
                now=now,
                require_clean=False,
            )
            current = await self._run_blocking(
                self._core.store.get_current_background_task,
                resolved.scope,
                session_id=session_id,
            )
            if current is not None:
                await self._run_blocking(
                    self._require_exact_task_context,
                    authority=resolved,
                    operation="task.status",
                    task_id=current.task_id,
                    now=now,
                )
            return current
        finally:
            if entered:
                await self._leave_operation()

    async def read_background_task(
        self,
        *,
        bearer_token: object,
        session_id: str,
        task_id: str,
    ) -> PersistentTaskRecord:
        """Read one immutable semantic target under its authenticated scope."""

        entered = False
        try:
            await self._enter_operation()
            entered = True
            now = self._clock()
            principal = self._authenticator.authenticate(
                bearer_token,
                operation="task.status",
                now=now,
            )
            authority = await self._run_blocking(
                self._authority_resolver.resolve,
                principal,
                session_id=session_id,
                now=now,
                require_clean=False,
            )
            task = await self._run_blocking(
                self._core.store.get_task,
                task_id,
                authority.scope,
            )
            await self._run_blocking(
                self._require_exact_task_context,
                authority=authority,
                operation="task.status",
                task_id=task.task_id,
                now=now,
            )
            return task
        finally:
            if entered:
                await self._leave_operation()

    async def read_task_notification_facts(
        self,
        *,
        task_id: str,
        attempt_id: str,
        scope: ScopeRef,
    ) -> tuple[
        PersistentTaskRecord,
        TaskResultAvailability,
        TaskResultRecord | None,
        str,
    ]:
        """Read terminal TaskEvent presentation facts without retaining credentials."""

        entered = False
        try:
            await self._enter_operation()
            entered = True
            task = await self._run_blocking(
                self._core.store.get_task,
                task_id,
                scope,
            )
            if task.attempt_id != attempt_id:
                raise FormalTaskViolation(
                    "TASK_NOTIFICATION_ATTEMPT_MISMATCH",
                    "terminal notification no longer binds the exact Task attempt",
                    ErrorCode.STALE,
                )
            availability, result, reason = await self._run_blocking(
                self._core.store.task_result,
                task_id,
                scope,
            )
            return task, availability, result, reason
        finally:
            if entered:
                await self._leave_operation()

    async def read_product_unread_events(
        self,
        authority: ResolvedProductAuthority,
        *,
        presentation_class: str,
        request_id: str,
        limit: int = 500,
    ) -> TaskUnreadPage:
        """Read one exact durable consumer prefix through authenticated Core."""

        entered = False
        try:
            await self._enter_operation()
            entered = True
            return await self._run_blocking(
                self._read_product_unread_events,
                authority,
                presentation_class=presentation_class,
                request_id=request_id,
                limit=limit,
            )
        finally:
            if entered:
                await self._leave_operation()

    async def read_product_task_result(
        self,
        authority: ResolvedProductAuthority,
        *,
        request_id: str,
    ) -> tuple[TaskResultAvailability, TaskResultRecord | None]:
        """Read the exact legal result needed by a completed presentation."""

        entered = False
        try:
            await self._enter_operation()
            entered = True
            return await self._run_blocking(
                self._read_product_task_result,
                authority,
                request_id=request_id,
            )
        finally:
            if entered:
                await self._leave_operation()

    def prepare_product_presentation_ack(
        self,
        authority: ResolvedProductAuthority,
        delivery: TaskPresentationDelivery,
        *,
        request_id: str,
        command_id: str,
        now: str | None = None,
    ) -> tuple[CommandEnvelope, TaskAuthorizationGrant]:
        """Build the sole server-presentation command and its exact fresh grant."""

        observed_at = now or self._clock()
        self._require_product_presentation_authority(
            authority,
            operation="task.ack_events",
            task_id=delivery.task_id,
            now=observed_at,
        )
        if delivery.scope != authority.scope:
            raise FormalTaskViolation(
                "TASK_PRESENTATION_AUTHORITY_MISMATCH",
                "presentation delivery changed its authenticated scope",
                ErrorCode.PERMISSION_DENIED,
            )
        command = CommandEnvelope.from_dict(
            {
                "contract_version": CONTRACT_VERSION,
                "request_id": _required_text(request_id, "request_id", maximum=256),
                "command_id": _required_text(command_id, "command_id", maximum=256),
                "command_type": "task.ack_events",
                "issued_at": observed_at,
                "scope": authority.scope.to_dict(),
                "correlation_id": authority.correlation_id,
                "causation_id": delivery.event_id,
                "origin": {"kind": "structured", "turn_id": None, "commit_id": None},
                "target_ref": {"kind": "task", "id": delivery.task_id},
                "context_refs": [],
                "required_capabilities": ["task.ack_events"],
                "payload": {
                    "presentation_class": delivery.presentation_class,
                    "acked_through_seq": delivery.event_seq,
                    "acked_event_id": delivery.event_id,
                    "expected_event_head": delivery.expected_event_head,
                },
                "extensions": {},
            }
        )
        return command, TaskAuthorizationGrant(
            principal_id=authority.principal_id,
            scope=authority.scope,
            operation="task.ack_events",
            command_id=command.command_id,
            target_task_id=delivery.task_id,
            allowed_capabilities=frozenset({"task.ack_events"}),
            confirmation_id=None,
            confirmed=False,
            expires_at=authority.expires_at,
            policy_bypass="server_task_presentation_v1",
        )

    def execute_product_presentation_ack(
        self,
        authority: ResolvedProductAuthority,
        command: CommandEnvelope,
        authorization: TaskAuthorizationGrant,
        *,
        now: str | None = None,
    ) -> ResultEnvelope:
        """Reread authority immediately before the only durable ACK mutation."""

        observed_at = now or self._clock()
        if not self._accepting:
            raise FormalTaskViolation(
                "FORMAL_TASK_ROUTE_DISABLED",
                "formal Task presentation route is unavailable",
                ErrorCode.UNAVAILABLE,
            )
        if (
            not isinstance(command, CommandEnvelope)
            or not isinstance(authorization, TaskAuthorizationGrant)
            or command.command_type != "task.ack_events"
        ):
            raise FormalTaskViolation(
                "TASK_PRESENTATION_ACK_INVALID",
                "presentation ACK invocation is not canonical",
                ErrorCode.INVALID_ARGUMENT,
            )
        self._require_product_presentation_authority(
            authority,
            operation="task.ack_events",
            task_id=command.target_ref.id,
            now=observed_at,
        )
        expected = TaskAuthorizationGrant(
            principal_id=authority.principal_id,
            scope=authority.scope,
            operation="task.ack_events",
            command_id=command.command_id,
            target_task_id=command.target_ref.id,
            allowed_capabilities=frozenset({"task.ack_events"}),
            confirmation_id=None,
            confirmed=False,
            expires_at=authority.expires_at,
            policy_bypass="server_task_presentation_v1",
        )
        if authorization != expected or command.scope != authority.scope:
            raise FormalTaskViolation(
                "TASK_PRESENTATION_AUTHORITY_MISMATCH",
                "presentation ACK changed its fresh authorization binding",
                ErrorCode.PERMISSION_DENIED,
            )
        return self._core.execute(command, authorization, now=observed_at)

    def _read_product_unread_events(
        self,
        authority: ResolvedProductAuthority,
        *,
        presentation_class: str,
        request_id: str,
        limit: int,
    ) -> TaskUnreadPage:
        now = self._clock()
        self._require_product_presentation_authority(
            authority,
            operation="task.unread_events",
            task_id=(
                authority.resource.resource_id if authority.resource is not None else ""
            ),
            now=now,
        )
        if presentation_class not in {"text", "voice"} or not 1 <= limit <= 500:
            raise FormalTaskViolation(
                "INVALID_PRESENTATION_CLASS",
                "presentation unread query has invalid bounds",
                ErrorCode.INVALID_ARGUMENT,
            )
        assert authority.resource is not None
        task_id = authority.resource.resource_id
        query = QueryEnvelope.from_dict(
            {
                "contract_version": CONTRACT_VERSION,
                "request_id": _required_text(request_id, "request_id", maximum=256),
                "query_type": "task.unread_events",
                "issued_at": now,
                "scope": authority.scope.to_dict(),
                "correlation_id": authority.correlation_id,
                "causation_id": None,
                "target_ref": {"kind": "task", "id": task_id},
                "context_refs": [],
                "required_capabilities": ["task.unread_events"],
                "payload": {
                    "presentation_class": presentation_class,
                    "limit": limit,
                },
                "extensions": {},
            }
        )
        grant = TaskAuthorizationGrant(
            principal_id=authority.principal_id,
            scope=authority.scope,
            operation="task.unread_events",
            command_id=None,
            target_task_id=task_id,
            allowed_capabilities=frozenset({"task.unread_events"}),
            confirmation_id=None,
            confirmed=False,
            expires_at=authority.expires_at,
        )
        result = self._core.query(query, grant, now=now)
        if not result.ok or result.result is None:
            error = result.error
            raise FormalTaskViolation(
                (
                    "TASK_UNREAD_EVENTS_UNAVAILABLE"
                    if error is None or error.reason is None
                    else error.reason
                ),
                "authenticated Task unread query failed",
                ErrorCode.UNAVAILABLE if error is None else error.code,
            )
        return self._task_unread_page_from_result(result.result)

    def _require_consumer_task_context(
        self,
        *,
        authority: ResolvedAuthority,
        operation: str,
        task_id: str,
        now: str,
    ) -> None:
        task = self._core.read_consumer_task(
            scope=authority.scope,
            task_id=task_id,
        )
        persisted = task.spec.context
        persisted.require_usable(
            scope=task.scope,
            required_permissions=frozenset(),
            destructive=False,
            now=now,
        )
        current = authority.context
        if (
            (task.scope.subject_id, task.scope.project_id)
            != (authority.scope.subject_id, authority.scope.project_id)
            or persisted.stable_id != current.stable_id
            or persisted.uri != current.uri
            or persisted.redacted
            or current.redacted
        ):
            raise FormalTaskViolation(
                "EXECUTION_CONTEXT_SCOPE_MISMATCH",
                f"{operation} no longer matches the authenticated consumer project",
                ErrorCode.PERMISSION_DENIED,
            )

    def _read_product_task_result(
        self,
        authority: ResolvedProductAuthority,
        *,
        request_id: str,
    ) -> tuple[TaskResultAvailability, TaskResultRecord | None]:
        now = self._clock()
        task_id = (
            authority.resource.resource_id if authority.resource is not None else ""
        )
        self._require_product_presentation_authority(
            authority,
            operation="task.result",
            task_id=task_id,
            now=now,
        )
        _required_text(request_id, "request_id", maximum=256)
        availability, record, _reason = self._core.read_consumer_task_result(
            scope=authority.scope,
            task_id=task_id,
        )
        return availability, record

    def _require_product_presentation_authority(
        self,
        authority: ResolvedProductAuthority,
        *,
        operation: str,
        task_id: str,
        now: str,
    ) -> ResolvedAuthority:
        if (
            not isinstance(authority, ResolvedProductAuthority)
            or operation not in P3_PRESENTATION_OPERATIONS | {"task.result"}
            or authority.operation != operation
            or authority.capabilities != frozenset({operation})
            or authority.assurance is not Assurance.AUTHENTICATED
            or authority.resource
            != AuthorityResourceBinding(
                kind="task",
                resource_id=task_id,
                fingerprint_sha256=hashlib.sha256(task_id.encode("utf-8")).hexdigest(),
            )
        ):
            raise FormalTaskViolation(
                "TASK_PRESENTATION_AUTHORITY_MISMATCH",
                "presentation authority does not bind the exact Task operation",
                ErrorCode.PERMISSION_DENIED,
            )
        if _parse_utc(authority.expires_at, "authority.expires_at") <= _parse_utc(
            now, "now"
        ):
            raise FormalTaskViolation(
                "FORMAL_TASK_AUTHORIZATION_EXPIRED",
                "presentation authority has expired",
                ErrorCode.PERMISSION_DENIED,
            )
        principal = AuthenticatedPrincipal(
            principal_id=authority.principal_id,
            allowed_project_ids=(
                frozenset()
                if authority.project_id is None
                else frozenset({authority.project_id})
            ),
            allowed_operations=frozenset({operation}),
            expires_at=authority.expires_at,
        )
        current = self._authority_resolver.resolve(
            principal,
            session_id=authority.session_id,
            now=now,
            require_clean=False,
        )
        if current.scope != authority.scope:
            raise FormalTaskViolation(
                "EXECUTION_CONTEXT_SCOPE_MISMATCH",
                "presentation authority no longer matches the authenticated project",
                ErrorCode.PERMISSION_DENIED,
            )
        self._require_consumer_task_context(
            authority=current,
            operation=operation,
            task_id=task_id,
            now=now,
        )
        return current

    @staticmethod
    def _task_unread_page_from_result(payload: Mapping[str, object]) -> TaskUnreadPage:
        try:
            raw_events = payload["events"]
            if not isinstance(raw_events, list):
                raise TypeError("events")
            events = tuple(
                PersistentTaskEvent(
                    event_id=str(item["event_id"]),
                    task_id=str(item["task_id"]),
                    attempt_id=str(item["attempt_id"]),
                    scope=ScopeRef.from_dict(item["scope"]),
                    seq=item["seq"],
                    event_type=str(item["event_type"]),
                    state=str(item["state"]),
                    outcome=(None if item["outcome"] is None else str(item["outcome"])),
                    producer=str(item["producer"]),
                    source_event_id=(
                        None
                        if item["source_event_id"] is None
                        else str(item["source_event_id"])
                    ),
                    causation_id=(
                        None
                        if item["causation_id"] is None
                        else str(item["causation_id"])
                    ),
                    correlation_id=str(item["correlation_id"]),
                    occurred_at=str(item["occurred_at"]),
                    details=item["details"],
                )
                for item in raw_events
                if isinstance(item, Mapping)
            )
            if len(events) != len(raw_events):
                raise TypeError("event")
            return TaskUnreadPage(
                task_id=str(payload["task_id"]),
                presentation_class=str(payload["presentation_class"]),
                watermark=payload["watermark"],
                acked_event_id=(
                    None
                    if payload["acked_event_id"] is None
                    else str(payload["acked_event_id"])
                ),
                head_seq=payload["head_seq"],
                events=events,
                next_after_seq=payload["next_after_seq"],
                has_more=payload["has_more"],
            )
        except (KeyError, TypeError, ValueError, FormalTaskViolation) as error:
            raise FormalTaskViolation(
                "INVALID_TASK_UNREAD_PAGE",
                "authenticated Core returned a non-canonical unread page",
                ErrorCode.PROTOCOL_VIOLATION,
            ) from error

    async def _verify_confirmation(
        self,
        *,
        principal: AuthenticatedPrincipal,
        scope: ScopeRef,
        operation: str,
        clean: Mapping[str, Any],
        context: ResolvedTaskContext | None,
        model: ResolvedP3Model | None,
        now: str,
        retry: PreparedP3RetryFacts | None = None,
    ) -> VerifiedP3Confirmation:
        if self._confirmation_verifier is None:
            raise FormalTaskViolation(
                "FORMAL_TASK_CONFIRMATION_REQUIRED",
                "formal task mutation requires a trusted confirmation owner",
                ErrorCode.PERMISSION_DENIED,
            )
        command_id = str(clean["command_id"])
        target_task_id = (
            str(clean["task_id"]) if operation in P3_TARGETED_MUTATIONS else None
        )
        binding = P3ConfirmationBinding(
            principal_id=principal.principal_id,
            scope=scope,
            operation=operation,
            command_id=command_id,
            target_task_id=target_task_id,
            intent_fingerprint=p3_confirmation_intent_fingerprint(
                operation=operation,
                command_id=command_id,
                target_task_id=target_task_id,
                context=context,
                name=clean.get("name"),
                instruction=clean.get("instruction"),
                model=model,
                source=str(clean["source"]),
                interaction_id=clean.get("interaction_id"),
                turn_id=clean.get("turn_id"),
                commit_id=clean.get("commit_id"),
                retry=retry,
            ),
        )
        return await self._run_blocking(
            self._confirmation_verifier.verify_and_consume,
            str(clean["confirmation_id"]),
            binding,
            now=now,
        )

    async def prepare_mutation_confirmation(
        self,
        *,
        operation: str,
        params: Mapping[str, object],
        session_id: str | None,
    ) -> PreparedP3MutationConfirmation:
        """Resolve one mutation without issuing, consuming, or executing it.

        Product Main uses the returned binding twice: first to issue the durable
        confirmation and later to prove that the exact mutation still resolves
        to the same principal, scope, target, context revision, and model.
        """

        entered = False
        try:
            await self._enter_operation()
            entered = True
            if operation not in P3_MUTATIONS:
                raise FormalTaskViolation(
                    "INVALID_P3_CONFIRMATION_OPERATION",
                    "confirmation preparation supports the exact P3 mutations",
                    ErrorCode.UNSUPPORTED,
                )
            now = self._clock()
            principal = self._authenticator.authenticate(
                params.get("auth_token"),
                operation=operation,
                now=now,
            )
            clean = self._validate_params(
                operation,
                params,
                session_id=session_id,
                now=now,
            )
            authority = await self._run_blocking(
                self._authority_resolver.resolve,
                principal,
                session_id=clean["session_id"],
                now=now,
                # A retry may only start from a clean checkout: D-069 forbids
                # relaxing TASK_CONTEXT_WORKTREE_DIRTY for the new attempt.
                require_clean=operation in {"task.create", "task.retry"},
            )
            authority.context.require_usable(
                scope=authority.scope,
                required_permissions=frozenset({"task.execute", "project.write"}),
                destructive=True,
                now=now,
            )
            if operation in {"task.adjust", "task.cancel"}:
                await self._run_blocking(
                    self._require_exact_task_context,
                    authority=authority,
                    operation=operation,
                    task_id=str(clean["task_id"]),
                    now=now,
                )
            retry_snapshot: _PreparedRetrySnapshot | None = None
            if operation == "task.retry":
                retry_snapshot = await self._run_blocking(
                    self._resolve_retry_snapshot,
                    authority=authority,
                    clean=clean,
                    now=now,
                )
            model: ResolvedP3Model | None = None
            if operation == "task.create":
                if self._model_resolver is None:
                    raise FormalTaskViolation(
                        "P3_MODEL_CATALOG_UNAVAILABLE",
                        "formal task model resolver is unavailable",
                        ErrorCode.CAPABILITY_UNAVAILABLE,
                    )
                model = await self._run_blocking(
                    self._model_resolver.resolve,
                    clean.get("model_intent"),
                    instantiate=False,
                )
                if (
                    clean["source"] in {"voice", "text"}
                    and clean.get("origin_commit_sha256") is not None
                ):
                    self._policy.require_committed_origin(
                        scope=authority.scope,
                        interaction_id=str(clean["interaction_id"]),
                        turn_id=str(clean["turn_id"]),
                        commit_id=str(clean["commit_id"]),
                        commit_sha256=str(clean["origin_commit_sha256"]),
                        operation=operation,
                        instruction=str(clean["instruction"]),
                        task_id=None,
                        source_start=int(clean["source_start"]),
                        source_end=int(clean["source_end"]),
                    )
                elif clean["source"] == "voice":
                    self._policy.require_voice_origin(
                        scope=authority.scope,
                        interaction_id=str(clean["interaction_id"]),
                        turn_id=str(clean["turn_id"]),
                        commit_id=str(clean["commit_id"]),
                        instruction=str(clean["instruction"]),
                    )
            elif operation in {"task.adjust", "task.cancel"} and clean["source"] in {
                "voice",
                "text",
            }:
                self._policy.require_committed_origin(
                    scope=authority.scope,
                    interaction_id=str(clean["interaction_id"]),
                    turn_id=str(clean["turn_id"]),
                    commit_id=str(clean["commit_id"]),
                    commit_sha256=str(clean["origin_commit_sha256"]),
                    operation=operation,
                    instruction=(
                        str(clean["instruction"])
                        if operation == "task.adjust"
                        else None
                    ),
                    task_id=str(clean["task_id"]),
                    source_start=int(clean["source_start"]),
                    source_end=int(clean["source_end"]),
                )
            target_task_id = (
                str(clean["task_id"]) if operation in P3_TARGETED_MUTATIONS else None
            )
            if operation == "task.create":
                confirmation_context: ResolvedTaskContext | None = authority.context
            elif retry_snapshot is not None:
                confirmation_context = retry_snapshot.context
            else:
                confirmation_context = None
            binding = P3ConfirmationBinding(
                principal_id=principal.principal_id,
                scope=authority.scope,
                operation=operation,
                command_id=str(clean["command_id"]),
                target_task_id=target_task_id,
                intent_fingerprint=p3_confirmation_intent_fingerprint(
                    operation=operation,
                    command_id=str(clean["command_id"]),
                    target_task_id=target_task_id,
                    context=confirmation_context,
                    name=clean.get("name"),
                    instruction=clean.get("instruction"),
                    model=model,
                    source=str(clean["source"]),
                    interaction_id=clean.get("interaction_id"),
                    turn_id=clean.get("turn_id"),
                    commit_id=clean.get("commit_id"),
                    retry=(None if retry_snapshot is None else retry_snapshot.facts),
                ),
            )
            return PreparedP3MutationConfirmation(
                binding=binding,
                correlation_id=str(clean["correlation_id"]),
                issued_at=str(clean["issued_at"]),
                observed_at=now,
            )
        finally:
            if entered:
                await self._leave_operation()

    async def reauthorize_mutation_replay(
        self,
        *,
        operation: str,
        params: Mapping[str, object],
        session_id: str | None,
        expected_binding: P3ConfirmationBinding,
    ) -> None:
        """Reauthenticate result replay without re-running or consuming mutation."""

        entered = False
        try:
            await self._enter_operation()
            entered = True
            if operation not in P3_MUTATIONS:
                raise FormalTaskViolation(
                    "INVALID_P3_CONFIRMATION_OPERATION",
                    "mutation replay supports the exact P3 mutations",
                    ErrorCode.UNSUPPORTED,
                )
            if not isinstance(expected_binding, P3ConfirmationBinding):
                raise FormalTaskViolation(
                    "P3_CONFIRMATION_BINDING_MISMATCH",
                    "mutation replay requires its retained authority binding",
                    ErrorCode.PERMISSION_DENIED,
                )
            now = self._clock()
            principal = self._authenticator.authenticate(
                params.get("auth_token"),
                operation=operation,
                now=now,
            )
            clean = self._validate_params(
                operation,
                params,
                session_id=session_id,
                now=now,
            )
            authority = await self._run_blocking(
                self._authority_resolver.resolve,
                principal,
                session_id=clean["session_id"],
                now=now,
                require_clean=False,
            )
            authority.context.require_usable(
                scope=authority.scope,
                required_permissions=frozenset({"task.execute", "project.write"}),
                destructive=True,
                now=now,
            )
            target_task_id = (
                str(clean["task_id"]) if operation in P3_TARGETED_MUTATIONS else None
            )
            if (
                principal.principal_id != expected_binding.principal_id
                or authority.scope != expected_binding.scope
                or operation != expected_binding.operation
                or str(clean["command_id"]) != expected_binding.command_id
                or target_task_id != expected_binding.target_task_id
            ):
                raise FormalTaskViolation(
                    "P3_CONFIRMATION_BINDING_MISMATCH",
                    "mutation replay no longer matches current authority",
                    ErrorCode.PERMISSION_DENIED,
                )
        finally:
            if entered:
                await self._leave_operation()

    @staticmethod
    def _production_capability_digest(
        visible: TaskAuthorityRead,
        target: AuthenticatedTaskFact | None,
    ) -> str:
        if target is not None:
            return target.capability_profile_digest
        return visible.collection_capability_profile_digest

    @staticmethod
    def _production_origin_payload(
        binding: ProductionOriginBinding,
    ) -> dict[str, object]:
        if binding.origin is ProductionIntentOrigin.STRUCTURED:
            return {"kind": "structured", "turn_id": None, "commit_id": None}
        return {
            "kind": "committed_turn",
            "turn_id": binding.source_id,
            "commit_id": binding.commit_id,
        }

    async def handle_production_resolution(
        self,
        *,
        resolution: ProductionTaskResolution,
        bearer_token: object,
        request_id: str,
        session_id: str,
        correlation_id: str,
        origin_authority: CallLocalProductionOriginAuthority,
        confirmation_consumer: CallLocalProductionConfirmationConsumer | None = None,
        current_background_session_id: str | None = None,
    ) -> P3RouteResult:
        """Freshly authorize and invoke one generalized production resolution.

        Confirmation was already atomically consumed by the resolver.  This
        path never invokes the legacy confirmation verifier; it rereads all
        Store authority and claims the private call-local receipt immediately
        before the single Core invocation.
        """

        started = time.monotonic()
        outcome = "rejected"
        reason: str | None = None
        entered = False
        operation = (
            resolution.operation
            if isinstance(resolution, ProductionTaskResolution)
            else None
        )
        try:
            await self._enter_operation()
            entered = True
            if (
                not isinstance(resolution, ProductionTaskResolution)
                or resolution.outcome is not ProductionTaskPolicyOutcome.PROPOSED
                or operation not in P3_PRODUCTION_OPERATIONS
                or resolution.command_id is None
                or resolution.origin_binding is None
                or resolution.origin_receipt_id is None
                or resolution.origin_binding_fingerprint is None
                or resolution.task_set_fingerprint is None
            ):
                raise FormalTaskViolation(
                    "INVALID_PRODUCTION_TASK_RESOLUTION",
                    "only one complete proposed production resolution may reach Core",
                    ErrorCode.INVALID_ARGUMENT,
                )
            now = self._clock()
            principal = self._authenticator.authenticate(
                bearer_token,
                operation=operation,
                now=now,
            )
            authority = await self._run_blocking(
                self._authority_resolver.resolve,
                principal,
                session_id=_required_text(session_id, "session_id", maximum=256),
                now=now,
                require_clean=operation in {"task.create", "task.create_successor"},
            )
            destructive = operation in P3_PRODUCTION_MUTATIONS
            authority.context.require_usable(
                scope=authority.scope,
                required_permissions=(
                    frozenset({"task.execute", "project.write"})
                    if destructive
                    else frozenset()
                ),
                destructive=destructive,
                now=now,
            )
            origin_binding = resolution.origin_binding
            if (
                origin_binding.scope != authority.scope
                or origin_binding.principal_id != principal.principal_id
                or origin_binding.fingerprint != resolution.origin_binding_fingerprint
            ):
                raise FormalTaskViolation(
                    "PRODUCTION_ORIGIN_AUTHORITY_MISMATCH",
                    "production origin no longer matches current authenticated authority",
                    ErrorCode.PERMISSION_DENIED,
                )
            if type(origin_authority) is not CallLocalProductionOriginAuthority:
                raise FormalTaskViolation(
                    "PRODUCTION_ORIGIN_AUTHORITY_MISMATCH",
                    "exact call-local production origin authority is required",
                    ErrorCode.PERMISSION_DENIED,
                )
            try:
                origin_receipt = origin_authority.verify_origin(origin_binding)
            except (TypeError, ValueError) as error:
                raise FormalTaskViolation(
                    "PRODUCTION_ORIGIN_AUTHORITY_MISMATCH",
                    "production origin authority could not be re-proved",
                    ErrorCode.PERMISSION_DENIED,
                ) from error
            if (
                origin_receipt.receipt_id != resolution.origin_receipt_id
                or origin_receipt.principal_id != principal.principal_id
                or origin_receipt.binding_fingerprint
                != resolution.origin_binding_fingerprint
            ):
                raise FormalTaskViolation(
                    "PRODUCTION_ORIGIN_AUTHORITY_MISMATCH",
                    "production origin receipt changed before Core invocation",
                    ErrorCode.PERMISSION_DENIED,
                )

            store = getattr(self._core, "store", None)
            if not isinstance(store, SqliteTaskStore):
                raise FormalTaskViolation(
                    "PRODUCTION_TASK_AUTHORITY_UNAVAILABLE",
                    "production Task authority requires the formal SQLite Store",
                    ErrorCode.UNAVAILABLE,
                )
            create_selection = (
                self._select_production_create_candidate()
                if operation == "task.create"
                else None
            )
            current_create_model: ResolvedP3Model | None = None
            reader_arguments: dict[str, object] = {
                "store": store,
                "principal_id": principal.principal_id,
                "scope": authority.scope,
                "authority_context_fingerprint": production_context_fingerprint(
                    authority.context
                ),
            }
            if create_selection is not None:
                reader_arguments["collection_capability_profile_digest"] = (
                    create_selection.capability_profile_digest
                )
                if self._model_resolver is None:
                    raise FormalTaskViolation(
                        "P3_MODEL_CATALOG_UNAVAILABLE",
                        "production task.create requires model authority",
                        ErrorCode.CAPABILITY_UNAVAILABLE,
                    )
                current_create_model = await self._run_blocking(
                    self._model_resolver.resolve,
                    None,
                    instantiate=False,
                )
                reader_arguments["collection_model_binding_fingerprint"] = (
                    production_model_binding_fingerprint(
                        {
                            "model_config_version": (
                                current_create_model.config_version
                            ),
                            "model_identity": current_create_model.identity,
                        }
                    )
                )
            reader = StoreProductionTaskAuthorityReader(**reader_arguments)
            visible = await self._run_blocking(
                reader.list_visible_tasks, authority.scope
            )
            if visible.fingerprint != resolution.task_set_fingerprint:
                raise FormalTaskViolation(
                    "PRODUCTION_TASK_AUTHORITY_CHANGED",
                    "visible Task set changed after intent resolution",
                    ErrorCode.STALE,
                )
            target = (
                None
                if resolution.target_task_id is None
                else next(
                    (
                        item
                        for item in visible.tasks
                        if item.task_id == resolution.target_task_id
                    ),
                    None,
                )
            )
            targeted = operation not in {"task.create", "task.list"}
            if targeted and target is None:
                raise FormalTaskViolation(
                    "PRODUCTION_TASK_NOT_FOUND",
                    "resolved production Task is no longer visible",
                    ErrorCode.NOT_FOUND,
                )
            if target is not None and (
                resolution.authority_fingerprint != target.fingerprint
                or operation not in target.supported_operations
            ):
                raise FormalTaskViolation(
                    "PRODUCTION_TASK_AUTHORITY_CHANGED",
                    "resolved Task capability or lifecycle changed before invocation",
                    ErrorCode.STALE,
                )
            if not targeted and resolution.authority_fingerprint is not None:
                raise FormalTaskViolation(
                    "PRODUCTION_TASK_AUTHORITY_CHANGED",
                    "collection resolution carried an unexpected target authority",
                    ErrorCode.STALE,
                )

            task_snapshot = None
            if operation in {
                "task.update",
                "task.reprioritize",
                "task.create_successor",
            }:
                assert target is not None
                task_snapshot = await self._run_blocking(
                    store.task_read_snapshot,
                    target.task_id,
                    authority.scope,
                )
            final_visible = await self._run_blocking(
                reader.list_visible_tasks, authority.scope
            )
            if final_visible.fingerprint != visible.fingerprint:
                raise FormalTaskViolation(
                    "PRODUCTION_TASK_AUTHORITY_CHANGED",
                    "Task authority changed during final invocation preparation",
                    ErrorCode.STALE,
                )
            final_target = (
                None
                if target is None
                else next(
                    (
                        item
                        for item in final_visible.tasks
                        if item.task_id == target.task_id
                    ),
                    None,
                )
            )
            if target is not None and final_target != target:
                raise FormalTaskViolation(
                    "PRODUCTION_TASK_AUTHORITY_CHANGED",
                    "target Task changed during final invocation preparation",
                    ErrorCode.STALE,
                )

            arguments = dict(resolution.arguments)
            if operation == "task.list":
                self._require_list_task_contexts(
                    authority=authority,
                    now=now,
                    cursor=None,
                    limit=int(arguments["limit"]),
                )
            elif final_target is not None:
                self._require_exact_task_context(
                    authority=authority,
                    operation=operation,
                    task_id=final_target.task_id,
                    now=now,
                )
            issued_at = now
            request_identity = _required_text(request_id, "request_id", maximum=256)
            correlation = _required_text(correlation_id, "correlation_id", maximum=256)
            origin_payload = self._production_origin_payload(origin_binding)
            target_id = resolution.target_task_id
            grant: TaskAuthorizationGrant
            if operation in P3_QUERY_OPERATIONS:
                if resolution.confirmation != "not_required":
                    raise FormalTaskViolation(
                        "PRODUCTION_CONFIRMATION_MISMATCH",
                        "read-only production query cannot consume confirmation",
                        ErrorCode.PERMISSION_DENIED,
                    )
                payload: dict[str, object]
                if operation == "task.list":
                    payload = {"cursor": None, "limit": int(arguments["limit"])}
                    query_target = "task-list"
                elif operation == "task.events":
                    payload = {
                        "after_seq": int(arguments["after_seq"]),
                        "limit": int(arguments["limit"]),
                    }
                    assert target_id is not None
                    query_target = target_id
                else:
                    payload = {}
                    assert target_id is not None
                    query_target = target_id
                envelope: CommandEnvelope | QueryEnvelope = QueryEnvelope.from_dict(
                    {
                        "contract_version": CONTRACT_VERSION,
                        "request_id": request_identity,
                        "query_type": operation,
                        "issued_at": issued_at,
                        "scope": authority.scope.to_dict(),
                        "correlation_id": correlation,
                        "causation_id": None,
                        "target_ref": {"kind": "task", "id": query_target},
                        "context_refs": [],
                        "required_capabilities": [operation],
                        "payload": payload,
                        "extensions": {},
                    }
                )
                grant = TaskAuthorizationGrant(
                    principal_id=principal.principal_id,
                    scope=authority.scope,
                    operation=operation,
                    command_id=None,
                    target_task_id=(None if operation == "task.list" else target_id),
                    allowed_capabilities=frozenset({operation}),
                    confirmation_id=None,
                    confirmed=False,
                    expires_at=principal.expires_at,
                )
                result = await self._run_blocking(
                    self._core.query,
                    envelope,
                    grant,
                    now=now,
                )
                if operation == "task.list":
                    self._require_list_result_contexts(
                        authority=authority,
                        result=result,
                        now=now,
                    )
            else:
                if (
                    resolution.confirmation != "confirmed"
                    or resolution.confirmation_binding is None
                    or type(confirmation_consumer)
                    is not CallLocalProductionConfirmationConsumer
                    or not confirmation_consumer.bound_to_verifier(
                        self._confirmation_verifier
                    )
                ):
                    raise FormalTaskViolation(
                        "PRODUCTION_CONFIRMATION_REQUIRED",
                        "production Task mutation requires one consumed confirmation",
                        ErrorCode.PERMISSION_DENIED,
                    )
                current_capability = self._production_capability_digest(
                    final_visible, final_target
                )
                if (
                    resolution.confirmation_binding.capability_profile_digest
                    != current_capability
                ):
                    raise FormalTaskViolation(
                        "PRODUCTION_TASK_AUTHORITY_CHANGED",
                        "Executor capability changed after confirmation",
                        ErrorCode.STALE,
                    )
                current_context_fingerprint = production_context_fingerprint(
                    authority.context
                )
                current_model_binding_fingerprint = (
                    final_visible.collection_model_binding_fingerprint
                    if operation == "task.create"
                    else final_target.model_binding_fingerprint
                    if final_target is not None
                    else None
                )
                if (
                    resolution.confirmation_binding.context_fingerprint
                    != current_context_fingerprint
                    or current_model_binding_fingerprint is None
                    or resolution.confirmation_binding.model_binding_fingerprint
                    != current_model_binding_fingerprint
                ):
                    raise FormalTaskViolation(
                        "PRODUCTION_TASK_AUTHORITY_CHANGED",
                        "Task context or model binding changed after confirmation",
                        ErrorCode.STALE,
                    )
                command_payload: dict[str, object]
                selection: PersistedExecutorSelection | None = None
                command_context: ResolvedTaskContext | None = None
                mutation_precondition: TaskMutationPrecondition | None = None
                if operation == "task.create":
                    assert current_create_model is not None
                    model = current_create_model
                    command_payload = {
                        "name": arguments["name"],
                        "instruction": arguments["instruction"],
                        "executor_id": FORMAL_PROJECT_EXECUTOR_ID,
                        "side_effect_class": "project_mutation",
                        "attributes": {
                            "model_identity": model.identity,
                            "model_config_version": model.config_version,
                        },
                    }
                    command_context = authority.context
                elif operation == "task.update":
                    assert final_target is not None and task_snapshot is not None
                    persistent_task, persistent_attempt, _admission = task_snapshot
                    if (
                        persistent_task.task_id != final_target.task_id
                        or persistent_attempt.attempt_id != final_target.attempt_id
                        or persistent_task.event_head != final_target.event_head
                    ):
                        raise FormalTaskViolation(
                            "PRODUCTION_TASK_AUTHORITY_CHANGED",
                            "update preparation no longer binds the current Task",
                            ErrorCode.STALE,
                        )
                    command_payload = {
                        "attempt_id": final_target.attempt_id,
                        "expected_event_head": final_target.event_head,
                        "instruction": arguments["instruction"],
                        "constraints": list(persistent_task.spec.constraints),
                    }
                elif operation == "task.adjust":
                    assert final_target is not None
                    command_payload = {"adjustment": arguments["adjustment"]}
                    mutation_precondition = TaskMutationPrecondition(
                        task_id=final_target.task_id,
                        attempt_id=final_target.attempt_id,
                        expected_event_head=final_target.event_head,
                    )
                elif operation == "task.reprioritize":
                    assert final_target is not None and task_snapshot is not None
                    persistent_task, persistent_attempt, _admission = task_snapshot
                    if (
                        persistent_task.task_id != final_target.task_id
                        or persistent_attempt.attempt_id != final_target.attempt_id
                        or persistent_task.event_head != final_target.event_head
                    ):
                        raise FormalTaskViolation(
                            "PRODUCTION_TASK_AUTHORITY_CHANGED",
                            "reprioritize preparation no longer binds the current Task",
                            ErrorCode.STALE,
                        )
                    command_payload = {
                        "attempt_id": final_target.attempt_id,
                        "expected_event_head": final_target.event_head,
                        "priority": arguments["priority"],
                        "reason": "production_intent",
                    }
                elif operation == "task.cancel":
                    assert final_target is not None
                    command_payload = {}
                    mutation_precondition = TaskMutationPrecondition(
                        task_id=final_target.task_id,
                        attempt_id=final_target.attempt_id,
                        expected_event_head=final_target.event_head,
                    )
                else:
                    assert operation == "task.create_successor"
                    assert final_target is not None and task_snapshot is not None
                    persistent_task, persistent_attempt, _admission = task_snapshot
                    if (
                        persistent_task.task_id != final_target.task_id
                        or persistent_attempt.attempt_id != final_target.attempt_id
                        or persistent_task.event_head != final_target.event_head
                        or persistent_task.outcome is None
                        or final_target.terminal_event_id is None
                    ):
                        raise FormalTaskViolation(
                            "PRODUCTION_TASK_AUTHORITY_CHANGED",
                            "successor preparation no longer binds the predecessor",
                            ErrorCode.STALE,
                        )
                    prior_context = persistent_task.spec.context
                    if (
                        prior_context.source,
                        prior_context.stable_id,
                        prior_context.uri,
                        prior_context.scope,
                    ) != (
                        authority.context.source,
                        authority.context.stable_id,
                        authority.context.uri,
                        authority.context.scope,
                    ):
                        raise FormalTaskViolation(
                            "TASK_SUCCESSOR_CONTEXT_IDENTITY_MISMATCH",
                            "successor context changed its predecessor project identity",
                            ErrorCode.PERMISSION_DENIED,
                        )
                    attributes = dict(persistent_task.spec.attributes)
                    if set(attributes) != {
                        "model_identity",
                        "model_config_version",
                    }:
                        raise FormalTaskViolation(
                            "INVALID_FORMAL_TASK_ATTRIBUTES",
                            "successor predecessor lacks one exact model binding",
                            ErrorCode.PROTOCOL_VIOLATION,
                        )
                    if self._model_resolver is None:
                        raise FormalTaskViolation(
                            "P3_MODEL_CATALOG_UNAVAILABLE",
                            "production successor requires model authority",
                            ErrorCode.CAPABILITY_UNAVAILABLE,
                        )
                    model = await self._run_blocking(
                        self._model_resolver.resolve,
                        attributes["model_identity"],
                        expected_identity=attributes["model_identity"],
                        expected_config_version=attributes["model_config_version"],
                        instantiate=False,
                    )
                    command_payload = {
                        "expected_predecessor_revision_number": final_target.revision_number,
                        "expected_predecessor_event_head": final_target.event_head,
                        "predecessor_terminal_event_id": final_target.terminal_event_id,
                        "predecessor_outcome": persistent_task.outcome.value,
                        "predecessor_result_sha256": final_target.result_digest,
                        "name": arguments["name"],
                        "instruction": arguments["instruction"],
                        "constraints": list(persistent_task.spec.constraints),
                        "executor_id": persistent_task.spec.executor_id,
                        "side_effect_class": persistent_task.spec.side_effect_class,
                        "attributes": {
                            "model_identity": model.identity,
                            "model_config_version": model.config_version,
                        },
                    }
                    command_context = authority.context
                assert resolution.command_id is not None
                envelope = CommandEnvelope.from_dict(
                    {
                        "contract_version": CONTRACT_VERSION,
                        "request_id": request_identity,
                        "command_id": resolution.command_id,
                        "command_type": operation,
                        "issued_at": issued_at,
                        "scope": authority.scope.to_dict(),
                        "correlation_id": correlation,
                        "causation_id": None,
                        "origin": origin_payload,
                        "target_ref": {
                            "kind": "task",
                            "id": (
                                f"create:{resolution.command_id}"
                                if operation == "task.create"
                                else target_id
                            ),
                        },
                        "context_refs": [],
                        "required_capabilities": [operation],
                        "payload": command_payload,
                        "extensions": {},
                    }
                )
                if operation == "task.create":
                    fresh_selection = self._select_create_executor(
                        envelope,
                        command_context,
                    )
                    if (
                        create_selection is None
                        or fresh_selection is None
                        or fresh_selection != create_selection
                        or fresh_selection.capability_profile_digest
                        != current_capability
                    ):
                        raise FormalTaskViolation(
                            "PRODUCTION_TASK_AUTHORITY_CHANGED",
                            "task.create Executor selection changed after confirmation",
                            ErrorCode.STALE,
                        )
                    selection = fresh_selection
                elif operation == "task.create_successor":
                    assert task_snapshot is not None
                    _persistent_task, persistent_attempt, _admission = task_snapshot
                    persisted_selection = persistent_attempt.selection
                    if (
                        persisted_selection is None
                        or persisted_selection.capability_profile_digest
                        != current_capability
                    ):
                        raise FormalTaskViolation(
                            "PRODUCTION_TASK_AUTHORITY_CHANGED",
                            "successor Executor selection changed after confirmation",
                            ErrorCode.STALE,
                        )
                    if self._executor_profiles is None:
                        raise FormalTaskViolation(
                            "EXECUTOR_CAPABILITY_UNAVAILABLE",
                            "production successor requires the persisted Executor candidate",
                            ErrorCode.CAPABILITY_UNAVAILABLE,
                        )
                    matching_profiles = tuple(
                        profile
                        for profile in self._executor_profiles
                        if profile.adapter_id == persisted_selection.adapter_id
                        and profile.canonical_bytes()
                        == persisted_selection.capability_profile_json
                        and profile.digest_sha256()
                        == persisted_selection.capability_profile_digest
                    )
                    if len(matching_profiles) != 1:
                        raise FormalTaskViolation(
                            "PRODUCTION_TASK_AUTHORITY_CHANGED",
                            "persisted successor Executor candidate is no longer exact",
                            ErrorCode.STALE,
                        )
                    selection = persisted_selection
                claim = confirmation_consumer.claim_for(resolution)
                if (
                    type(claim) is not CallLocalProductionConfirmationClaim
                    or claim.production_binding != resolution.confirmation_binding
                    or claim.consumption_id != resolution.confirmation_consumption_id
                    or claim.resolution_fingerprint != resolution.fingerprint
                    or claim.p3_binding.intent_fingerprint
                    != claim.production_binding.fingerprint
                    or claim.verified.replayed
                ):
                    raise FormalTaskViolation(
                        "PRODUCTION_CONFIRMATION_CLAIM_INVALID",
                        "Core composition requires the exact sealed call-local claim",
                        ErrorCode.PERMISSION_DENIED,
                    )
                expected_p3 = claim.p3_binding
                if (
                    expected_p3.principal_id != principal.principal_id
                    or expected_p3.scope != authority.scope
                    or expected_p3.operation != operation
                    or expected_p3.command_id != resolution.command_id
                    or expected_p3.target_task_id != target_id
                ):
                    raise FormalTaskViolation(
                        "PRODUCTION_CONFIRMATION_AUTHORITY_MISMATCH",
                        "call-local confirmation claim no longer matches current authority",
                        ErrorCode.PERMISSION_DENIED,
                    )
                grant = TaskAuthorizationGrant(
                    principal_id=principal.principal_id,
                    scope=authority.scope,
                    operation=operation,
                    command_id=resolution.command_id,
                    target_task_id=(None if operation == "task.create" else target_id),
                    allowed_capabilities=frozenset({operation}),
                    confirmation_id=claim.verified.confirmation_id,
                    confirmed=True,
                    expires_at=_earlier_expiry(
                        principal.expires_at, claim.verified.expires_at
                    ),
                )
                result = await self._run_blocking(
                    self._core.execute,
                    envelope,
                    grant,
                    context=command_context,
                    now=now,
                    current_background_session_id=(
                        current_background_session_id
                        if operation == "task.create"
                        else None
                    ),
                    selection=selection,
                    admission_policy=(
                        self._admission_policy if selection is not None else None
                    ),
                    mutation_precondition=mutation_precondition,
                )
                if result.ok:
                    self._wake.set()
            outcome = "accepted" if result.ok else "rejected"
            reason = None if result.error is None else result.error.reason
            return P3RouteResult(result.ok, result.to_dict())
        except FormalTaskViolation as error:
            reason = error.reason
            return P3RouteResult(
                False,
                {
                    "request_id": request_id,
                    "ok": False,
                    "result": None,
                    "error": {
                        "code": error.code.value,
                        "message": str(error),
                        "reason": error.reason,
                        "retryable": error.code
                        in {ErrorCode.UNAVAILABLE, ErrorCode.TIMEOUT},
                        "details": {},
                    },
                },
            )
        finally:
            if entered:
                await self._leave_operation()
            try:
                self._telemetry.emit(
                    P3RouteTelemetry(
                        operation=str(operation or "production.unknown"),
                        outcome=outcome,
                        reason=reason,
                        duration_ms=max(0, int((time.monotonic() - started) * 1000)),
                    )
                )
            except Exception:  # noqa: BLE001 -- telemetry cannot change authority
                logger.exception("[LiveVoiceP3] telemetry sink failed")

    async def handle_native(
        self,
        authority: NativeP3ActivationAuthority,
        *,
        operation: str,
        params: Mapping[str, object],
        request_id: str,
        session_id: str | None,
        trusted_demo_policy_bypass: bool = False,
        current_background_session_id: str | None = None,
        trusted_current_task_id: str | None = None,
    ) -> P3RouteResult:
        """Invoke the existing P3 owner with a server-retained principal."""

        internal_params = dict(params)
        internal_params["auth_token"] = None
        return await self.handle(
            operation=operation,
            params=internal_params,
            request_id=request_id,
            session_id=session_id,
            trusted_demo_policy_bypass=trusted_demo_policy_bypass,
            current_background_session_id=current_background_session_id,
            trusted_current_task_id=trusted_current_task_id,
            _native_authority=authority,
        )

    async def handle(
        self,
        *,
        operation: str,
        params: Mapping[str, object],
        request_id: str,
        session_id: str | None,
        trusted_demo_policy_bypass: bool = False,
        current_background_session_id: str | None = None,
        trusted_current_task_id: str | None = None,
        _native_authority: NativeP3ActivationAuthority | None = None,
    ) -> P3RouteResult:
        started = time.monotonic()
        outcome = "rejected"
        reason: str | None = None
        entered = False
        try:
            await self._enter_operation()
            entered = True
            if operation not in P3_OPERATIONS:
                raise FormalTaskViolation(
                    "UNSUPPORTED_FORMAL_TASK_INTENT",
                    "formal task operation is unsupported",
                    ErrorCode.UNSUPPORTED,
                )
            now = self._clock()
            native_resolved: ResolvedAuthority | None = None
            if _native_authority is None:
                principal = self._authenticator.authenticate(
                    params.get("auth_token"), operation=operation, now=now
                )
            else:
                native_resolved = await self._run_blocking(
                    self._resolve_native_activation_authority,
                    _native_authority,
                    operation=operation,
                    session_id=str(session_id or "").strip(),
                    now=now,
                    require_clean=operation in {"task.create", "task.retry"},
                )
                principal = _native_authority.principal
            clean = self._validate_params(
                operation,
                params,
                session_id=session_id,
                now=now,
                trusted_demo_policy_bypass=trusted_demo_policy_bypass,
            )
            if trusted_demo_policy_bypass and (
                clean.get("source") != "voice"
                or (
                    operation == "task.create"
                    and current_background_session_id != clean.get("session_id")
                )
                or (
                    operation in {"task.adjust", "task.cancel"}
                    and trusted_current_task_id is None
                )
            ):
                raise FormalTaskViolation(
                    "TRUSTED_DEMO_POLICY_BYPASS_FORBIDDEN",
                    "trusted Demo policy requires the unified voice current-task route",
                    ErrorCode.PERMISSION_DENIED,
                )
            if (
                operation == "task.adjust"
                and trusted_current_task_id is not None
                and current_background_session_id != clean.get("session_id")
            ):
                raise FormalTaskViolation(
                    "CURRENT_BACKGROUND_TASK_BINDING_REQUIRED",
                    "voice current-task adjustment requires its exact background Session",
                    ErrorCode.PERMISSION_DENIED,
                )
            authority = native_resolved or await self._run_blocking(
                self._authority_resolver.resolve,
                principal,
                session_id=clean["session_id"],
                now=now,
                # A retry may only start from a clean checkout: D-069 forbids
                # relaxing TASK_CONTEXT_WORKTREE_DIRTY for the new attempt.
                require_clean=operation in {"task.create", "task.retry"},
            )
            destructive = operation in P3_MUTATIONS
            authority.context.require_usable(
                scope=authority.scope,
                required_permissions=(
                    frozenset({"task.execute", "project.write"})
                    if destructive
                    else frozenset()
                ),
                destructive=destructive,
                now=now,
            )
            if operation in {
                "task.get",
                "task.status",
                "task.events",
                "task.result",
                "task.adjust",
                "task.cancel",
            }:
                await self._run_blocking(
                    self._require_exact_task_context,
                    authority=authority,
                    operation=operation,
                    task_id=str(clean["task_id"]),
                    now=now,
                )
            elif operation == "task.list":
                await self._run_blocking(
                    self._require_list_task_contexts,
                    authority=authority,
                    now=now,
                    cursor=clean.get("cursor"),
                    limit=clean.get("limit", 50),
                )
            retry_snapshot: _PreparedRetrySnapshot | None = None
            if operation == "task.retry":
                # Durable replay is resolved before current admission and before
                # any confirmation is consumed, so an already applied command
                # cannot be re-admitted as a second attempt.
                retry_snapshot = await self._run_blocking(
                    self._resolve_retry_snapshot,
                    authority=authority,
                    clean=clean,
                    now=now,
                )
            resolved_model: ResolvedP3Model | None = None
            if operation == "task.create":
                if self._model_resolver is None:
                    raise FormalTaskViolation(
                        "P3_MODEL_CATALOG_UNAVAILABLE",
                        "formal task model resolver is unavailable",
                        ErrorCode.CAPABILITY_UNAVAILABLE,
                    )
                resolved_model = await self._run_blocking(
                    self._model_resolver.resolve,
                    clean.get("model_intent"),
                    instantiate=False,
                )
            if operation == "task.create":
                confirmation_context: ResolvedTaskContext | None = authority.context
            elif retry_snapshot is not None:
                confirmation_context = retry_snapshot.context
            else:
                confirmation_context = None
            verified_confirmation = (
                await self._verify_confirmation(
                    principal=principal,
                    scope=authority.scope,
                    operation=operation,
                    clean=clean,
                    context=confirmation_context,
                    model=resolved_model,
                    now=now,
                    retry=(None if retry_snapshot is None else retry_snapshot.facts),
                )
                if destructive and not trusted_demo_policy_bypass
                else None
            )
            policy_bypass = (
                "trusted_demo_live_voice_v1"
                if destructive and trusted_demo_policy_bypass
                else None
            )
            current_task_binding = trusted_current_task_id is not None
            if current_task_binding and (
                operation not in {"task.adjust", "task.cancel"}
                or clean.get("task_id") != trusted_current_task_id
            ):
                raise FormalTaskViolation(
                    "CURRENT_BACKGROUND_TASK_MISMATCH",
                    "trusted current-task binding changed its exact target",
                    ErrorCode.PERMISSION_DENIED,
                )
            grant = TaskAuthorizationGrant(
                principal_id=principal.principal_id,
                scope=authority.scope,
                operation=operation,
                command_id=clean.get("command_id"),
                target_task_id=(
                    None
                    if operation in {"task.create", "task.list"}
                    else clean.get("task_id")
                ),
                allowed_capabilities=principal.allowed_operations,
                confirmation_id=(
                    verified_confirmation.confirmation_id
                    if verified_confirmation is not None
                    else None
                ),
                confirmed=verified_confirmation is not None,
                expires_at=(
                    _earlier_expiry(
                        principal.expires_at, verified_confirmation.expires_at
                    )
                    if verified_confirmation is not None
                    else principal.expires_at
                ),
                policy_bypass=policy_bypass,
            )
            intent = FormalTaskPolicyInput(
                state=InputCommitState.COMMITTED,
                source=str(clean["source"]),
                operation=operation,
                request_id=_required_text(request_id, "request_id", maximum=256),
                issued_at=clean.get("issued_at", now),
                scope=authority.scope,
                correlation_id=(
                    clean.get("correlation_id", request_id)
                    if retry_snapshot is None
                    else retry_snapshot.correlation_id
                ),
                authorization=grant,
                command_id=clean.get("command_id"),
                interaction_id=clean.get("interaction_id"),
                turn_id=clean.get("turn_id"),
                commit_id=clean.get("commit_id"),
                origin_commit_sha256=clean.get("origin_commit_sha256"),
                source_start=clean.get("source_start"),
                source_end=clean.get("source_end"),
                task_id=clean.get("task_id"),
                name=clean.get("name"),
                instruction=clean.get("instruction"),
                # ``task.create`` resolves a fresh context and ``task.retry``
                # carries the frozen one its confirmation bound; every other
                # operation stays context-free.
                context=confirmation_context,
                attributes=(
                    {
                        "model_identity": resolved_model.identity,
                        "model_config_version": resolved_model.config_version,
                    }
                    if resolved_model is not None
                    else {}
                ),
                destructive=destructive,
                confirmed=verified_confirmation is not None,
                confirmation_id=(
                    verified_confirmation.confirmation_id
                    if verified_confirmation is not None
                    else None
                ),
                policy_bypass=policy_bypass,
                current_task_binding=current_task_binding,
                after_seq=int(clean.get("after_seq", -1)),
                cursor=clean.get("cursor"),
                limit=clean.get("limit"),
                retry_precondition=(
                    None if retry_snapshot is None else retry_snapshot.precondition
                ),
                retry_product_request=(
                    None if retry_snapshot is None else retry_snapshot.product_request
                ),
            )
            invocation = self._policy.map(intent)
            if isinstance(invocation.envelope, CommandEnvelope):
                selection = (
                    self._select_create_executor(
                        invocation.envelope,
                        invocation.context,
                    )
                    if operation == "task.create"
                    else (
                        retry_snapshot.selection
                        if operation == "task.retry" and retry_snapshot is not None
                        else None
                    )
                )
                result = await self._run_blocking(
                    self._core.execute,
                    invocation.envelope,
                    invocation.authorization,
                    context=invocation.context,
                    now=now,
                    current_background_session_id=(
                        current_background_session_id
                        if operation == "task.create"
                        else None
                    ),
                    selection=selection,
                    admission_policy=(
                        self._admission_policy if selection is not None else None
                    ),
                )
            else:
                assert isinstance(invocation.envelope, QueryEnvelope)
                result = await self._run_blocking(
                    self._core.query,
                    invocation.envelope,
                    invocation.authorization,
                    now=now,
                )
                if operation == "task.list":
                    await self._run_blocking(
                        self._require_list_result_contexts,
                        authority=authority,
                        result=result,
                        now=now,
                    )
            if result.ok and destructive:
                self._wake.set()
            outcome = "accepted" if result.ok else "rejected"
            reason = None if result.error is None else result.error.reason
            route_payload = result.to_dict()
            if result.ok and operation == "task.status":
                result_payload = route_payload.get("result")
                if not isinstance(result_payload, dict):
                    raise FormalTaskViolation(
                        "FORMAL_TASK_STATUS_RESULT_INVALID",
                        "formal task status result is malformed",
                        ErrorCode.INTERNAL,
                    )
                result_payload = dict(result_payload)
                result_payload[
                    "retry_admission"
                ] = await self._read_status_retry_admission(
                    principal=principal,
                    session_id=str(clean["session_id"]),
                    task_id=str(clean["task_id"]),
                    now=now,
                )
                route_payload["result"] = result_payload
            return P3RouteResult(result.ok, route_payload)
        except FormalTaskViolation as exc:
            reason = exc.reason
            return P3RouteResult(
                False,
                {
                    "request_id": request_id,
                    "ok": False,
                    "result": None,
                    "error": {
                        "code": exc.code.value,
                        "reason": exc.reason,
                        "message": str(exc),
                    },
                },
            )
        except asyncio.CancelledError:
            if operation in P3_MUTATIONS:
                self._wake.set()
            raise
        except Exception:  # noqa: BLE001 -- route must fail closed
            reason = "FORMAL_TASK_ROUTE_INTERNAL"
            logger.exception("[LiveVoiceP3] route failed closed")
            return P3RouteResult(
                False,
                {
                    "request_id": request_id,
                    "ok": False,
                    "result": None,
                    "error": {
                        "code": ErrorCode.INTERNAL.value,
                        "reason": reason,
                        "message": "formal task route failed closed",
                    },
                },
            )
        finally:
            if entered:
                await self._leave_operation()
            try:
                self._telemetry.emit(
                    P3RouteTelemetry(
                        operation=operation,
                        outcome=outcome,
                        reason=reason,
                        duration_ms=max(0, int((time.monotonic() - started) * 1000)),
                    )
                )
            except Exception:  # noqa: BLE001 -- telemetry cannot change authority
                logger.exception("[LiveVoiceP3] telemetry sink failed")

    @staticmethod
    def _validate_params(
        operation: str,
        params: Mapping[str, object],
        *,
        session_id: str | None,
        now: str,
        trusted_demo_policy_bypass: bool = False,
    ) -> dict[str, Any]:
        fields: dict[str, tuple[frozenset[str], frozenset[str]]] = {
            "task.create": (
                frozenset(
                    {
                        "auth_token",
                        "session_id",
                        "command_id",
                        "confirmation_id",
                        "issued_at",
                        "correlation_id",
                        "name",
                        "instruction",
                    }
                ),
                frozenset(
                    {
                        "model_intent",
                        "source",
                        "interaction_id",
                        "turn_id",
                        "commit_id",
                        "origin_commit_sha256",
                        "source_start",
                        "source_end",
                    }
                ),
            ),
            "task.cancel": (
                frozenset(
                    {
                        "auth_token",
                        "session_id",
                        "command_id",
                        "confirmation_id",
                        "issued_at",
                        "correlation_id",
                        "task_id",
                    }
                ),
                frozenset(
                    {
                        "source",
                        "interaction_id",
                        "turn_id",
                        "commit_id",
                        "origin_commit_sha256",
                        "source_start",
                        "source_end",
                    }
                ),
            ),
            "task.adjust": (
                frozenset(
                    {
                        "auth_token",
                        "session_id",
                        "command_id",
                        "confirmation_id",
                        "issued_at",
                        "correlation_id",
                        "task_id",
                        "instruction",
                    }
                ),
                frozenset(
                    {
                        "source",
                        "interaction_id",
                        "turn_id",
                        "commit_id",
                        "origin_commit_sha256",
                        "source_start",
                        "source_end",
                    }
                ),
            ),
            # ``task.retry`` submits only its target task plus the immutable
            # request facts its product fingerprint binds.  Predecessor,
            # attempt ordinal, outcome, context and readiness stay server-owned.
            "task.retry": (
                frozenset(
                    {
                        "auth_token",
                        "session_id",
                        "command_id",
                        "confirmation_id",
                        "issued_at",
                        "correlation_id",
                        "task_id",
                    }
                ),
                frozenset(),
            ),
            "task.list": (
                frozenset({"auth_token", "session_id"}),
                frozenset({"cursor", "limit"}),
            ),
            "task.events": (
                frozenset({"auth_token", "session_id", "task_id"}),
                frozenset({"after_seq", "limit"}),
            ),
            "task.get": (
                frozenset({"auth_token", "session_id", "task_id"}),
                frozenset(),
            ),
            "task.status": (
                frozenset({"auth_token", "session_id", "task_id"}),
                frozenset(),
            ),
            "task.result": (
                frozenset({"auth_token", "session_id", "task_id"}),
                frozenset(),
            ),
        }
        required, optional = fields[operation]
        if trusted_demo_policy_bypass:
            if operation not in {"task.create", "task.adjust", "task.cancel"}:
                raise FormalTaskViolation(
                    "TRUSTED_DEMO_POLICY_BYPASS_FORBIDDEN",
                    "trusted Demo policy applies only to unified current-task mutations",
                    ErrorCode.PERMISSION_DENIED,
                )
            required = required - {"confirmation_id"}
        keys = set(params)
        if required - keys or keys - required - optional:
            raise FormalTaskViolation(
                "INVALID_P3_ROUTE_ARGUMENT",
                "formal task request fields are incomplete or unknown",
                ErrorCode.INVALID_ARGUMENT,
            )
        clean: dict[str, Any] = {
            "session_id": _required_text(
                params["session_id"], "session_id", maximum=256
            )
        }
        if clean["session_id"] != str(session_id or "").strip():
            raise FormalTaskViolation(
                "FORMAL_TASK_SESSION_MISMATCH",
                "formal task request does not match its routed session",
                ErrorCode.PERMISSION_DENIED,
            )
        for key in (
            "command_id",
            "confirmation_id",
            "correlation_id",
            "task_id",
        ):
            if key in params:
                clean[key] = _required_text(params[key], key, maximum=256)
        if "issued_at" in params:
            clean["issued_at"] = _required_text(
                params["issued_at"], "issued_at", maximum=64
            )
            try:
                issued_at = _parse_utc(clean["issued_at"], "issued_at")
                observed_at = _parse_utc(now, "now")
            except FormalTaskViolation as exc:
                raise FormalTaskViolation(
                    "INVALID_P3_ROUTE_ARGUMENT",
                    "issued_at must be an ISO-8601 timestamp with timezone",
                    ErrorCode.INVALID_ARGUMENT,
                ) from exc
            if issued_at > observed_at:
                raise FormalTaskViolation(
                    "INVALID_P3_ROUTE_ARGUMENT",
                    "issued_at cannot be in the future",
                    ErrorCode.INVALID_ARGUMENT,
                )
        if "name" in params:
            clean["name"] = _required_text(params["name"], "name", maximum=1024)
        if "instruction" in params:
            clean["instruction"] = _required_text(
                params["instruction"],
                "instruction",
                maximum=(4_096 if operation == "task.adjust" else 100_000),
            )
            if (
                operation == "task.adjust"
                and len(clean["instruction"].encode("utf-8")) > 4_096
            ):
                raise FormalTaskViolation(
                    "INVALID_TASK_ADJUSTMENT",
                    "task.adjust exceeds its closed UTF-8 bound",
                    ErrorCode.INVALID_ARGUMENT,
                )
        if "model_intent" in params:
            clean["model_intent"] = _required_text(
                params["model_intent"], "model_intent", maximum=256
            )
        source = _required_text(
            params.get("source", "structured"), "source", maximum=32
        )
        if source not in {"structured", "voice", "text"}:
            raise FormalTaskViolation(
                "INVALID_TASK_INTENT_SOURCE",
                "formal task intent source must be voice, text or structured",
                ErrorCode.INVALID_ARGUMENT,
            )
        if source in {"voice", "text"}:
            origin_fields = {
                "interaction_id",
                "turn_id",
                "commit_id",
            }
            content_binding_fields = {
                "origin_commit_sha256",
                "source_start",
                "source_end",
            }
            legacy_voice_create = source == "voice" and operation == "task.create"
            if (
                operation not in {"task.create", "task.adjust", "task.cancel"}
                or not origin_fields.issubset(params)
                or (
                    not legacy_voice_create
                    and not content_binding_fields.issubset(params)
                )
                or (
                    set(params).intersection(content_binding_fields)
                    and not content_binding_fields.issubset(params)
                )
            ):
                raise FormalTaskViolation(
                    "COMMITTED_ORIGIN_REQUIRED",
                    "natural-language task mutation requires an exact content-bound committed origin",
                    ErrorCode.PERMISSION_DENIED,
                )
            clean["interaction_id"] = _required_text(
                params["interaction_id"], "interaction_id", maximum=256
            )
            clean["turn_id"] = _required_text(params["turn_id"], "turn_id", maximum=256)
            clean["commit_id"] = _required_text(
                params["commit_id"], "commit_id", maximum=256
            )
            if "origin_commit_sha256" in params:
                clean["origin_commit_sha256"] = _required_text(
                    params["origin_commit_sha256"],
                    "origin_commit_sha256",
                    maximum=64,
                )
                if len(clean["origin_commit_sha256"]) != 64 or any(
                    character not in "0123456789abcdef"
                    for character in clean["origin_commit_sha256"]
                ):
                    raise FormalTaskViolation(
                        "INVALID_P3_ROUTE_ARGUMENT",
                        "origin_commit_sha256 must be lowercase hexadecimal",
                        ErrorCode.INVALID_ARGUMENT,
                    )
                for key in ("source_start", "source_end"):
                    value = params[key]
                    if type(value) is not int or value < 0 or value > 100_000:
                        raise FormalTaskViolation(
                            "INVALID_P3_ROUTE_ARGUMENT",
                            "natural-language source spans must be bounded integers",
                            ErrorCode.INVALID_ARGUMENT,
                        )
                    clean[key] = value
                if clean["source_start"] >= clean["source_end"]:
                    raise FormalTaskViolation(
                        "INVALID_P3_ROUTE_ARGUMENT",
                        "natural-language source span must be non-empty",
                        ErrorCode.INVALID_ARGUMENT,
                    )
        elif (
            "interaction_id" in params
            or "turn_id" in params
            or "commit_id" in params
            or "origin_commit_sha256" in params
            or "source_start" in params
            or "source_end" in params
        ):
            raise FormalTaskViolation(
                "INVALID_STRUCTURED_ORIGIN",
                "structured task intent cannot claim a voice commit",
                ErrorCode.INVALID_ARGUMENT,
            )
        clean["source"] = source
        if "after_seq" in params:
            if type(params["after_seq"]) is not int or params["after_seq"] < -1:
                raise FormalTaskViolation(
                    "INVALID_P3_ROUTE_ARGUMENT",
                    "after_seq must be an integer at least -1",
                    ErrorCode.INVALID_ARGUMENT,
                )
            clean["after_seq"] = params["after_seq"]
        if "cursor" in params:
            clean["cursor"] = _required_text(params["cursor"], "cursor", maximum=256)
        if "limit" in params:
            maximum = 100 if operation == "task.list" else 500
            if type(params["limit"]) is not int or not 1 <= params["limit"] <= maximum:
                raise FormalTaskViolation(
                    "INVALID_P3_ROUTE_ARGUMENT",
                    f"{operation} limit must be between 1 and {maximum}",
                    ErrorCode.INVALID_ARGUMENT,
                )
            clean["limit"] = params["limit"]
        return clean


def _abort_factory_owner(owner: object, *, owner_kind: str) -> None:
    """Best-effort bounded cleanup without replacing factory failure truth."""

    abort = getattr(owner, "_abort_initialization", None)
    if not callable(abort):
        logger.warning(
            "[LiveVoiceP3] factory initialization cleanup unavailable for %s",
            owner_kind,
        )
        return
    try:
        abort()
    except BaseException:  # noqa: BLE001 -- preserve the primary initialization error
        # Exception text may contain Provider, path, or private runtime data.
        logger.warning(
            "[LiveVoiceP3] factory initialization cleanup failed for %s",
            owner_kind,
        )


def create_p3_composition_from_environment(
    *,
    agent_manager: Any,
    model_resolver: P3ModelResolver,
    confirmation_verifier: P3ConfirmationVerifier | None = None,
    telemetry: P3TelemetrySink | None = None,
    commit_ledger: TurnCommitLedger | None = None,
    reconciliation_event_sink: ReconciliationEventSink | None = None,
    stream_observer: DirectStreamObserver | None = None,
) -> P3AuthenticatedComposition | None:
    """Build the production composition only after the complete gate validates."""

    if not _is_enabled(os.getenv(_ENABLE_ENV)):
        return None
    token = str(os.getenv(_TOKEN_ENV) or "")
    principal_id = str(os.getenv(_PRINCIPAL_ENV) or "").strip()
    project_ids = frozenset(
        item.strip()
        for item in str(os.getenv(_PROJECTS_ENV) or "").split(",")
        if item.strip()
    )
    expires_at = str(os.getenv(_EXPIRY_ENV) or "").strip()
    if not principal_id or not project_ids or not expires_at:
        raise FormalTaskViolation(
            "INVALID_P3_AUTH_CONFIGURATION",
            "enabled P3 route requires principal, project allow-list, and expiry",
            ErrorCode.INVALID_ARGUMENT,
        )
    expiry_timestamp = _parse_utc(expires_at, _EXPIRY_ENV)
    if expiry_timestamp <= datetime.now(UTC):
        raise FormalTaskViolation(
            "INVALID_P3_AUTH_CONFIGURATION",
            "enabled P3 route requires an unexpired authorization window",
            ErrorCode.PERMISSION_DENIED,
        )
    interval_raw = str(os.getenv(_RECONCILE_ENV) or "30").strip()
    try:
        interval = float(interval_raw)
    except ValueError as exc:
        raise FormalTaskViolation(
            "INVALID_P3_AUTH_CONFIGURATION",
            "P3 reconciliation interval must be numeric",
            ErrorCode.INVALID_ARGUMENT,
        ) from exc
    try:
        _validate_reconcile_interval(interval)
    except ValueError as exc:
        raise FormalTaskViolation(
            "INVALID_P3_AUTH_CONFIGURATION",
            "P3 reconciliation interval must be in (0, 3600] seconds",
            ErrorCode.INVALID_ARGUMENT,
        ) from exc
    configured_profile_id = str(os.getenv(_EXECUTOR_PROFILE_ENV) or "").strip()
    candidates = DirectProjectCodeExecutorAdapter.construction_capability_profiles(
        store_backed=True
    )
    configured_profiles = tuple(
        profile for profile in candidates if profile.profile_id == configured_profile_id
    )
    if len(configured_profiles) != 1:
        raise FormalTaskViolation(
            "INVALID_P3_EXECUTOR_CONFIGURATION",
            "enabled P3 route requires one available exact Executor profile",
            ErrorCode.CAPABILITY_UNAVAILABLE,
        )
    configured_profile = configured_profiles[0]
    direct_selection = select_executor(
        (configured_profile,),
        _product_execution_requirements(
            executor_id=FORMAL_PROJECT_EXECUTOR_ID,
            side_effect_class="project_mutation",
            durability_level=configured_profile.durability_level,
        ),
    )
    validated_executor = _validated_executor_configuration(direct_selection.profile)
    database = str(os.getenv(_DATABASE_ENV) or "").strip()
    database_path = _resolve_database_path(database)
    principal = AuthenticatedPrincipal(
        principal_id=principal_id,
        allowed_project_ids=project_ids,
        allowed_operations=(
            P3_PRODUCT_AUTHORITY_OPERATIONS | {_PRODUCT_P2_OPERATION}
            if _is_enabled(os.getenv(_PRODUCT_COMPOSITION_ENV))
            and _is_enabled(os.getenv(_PRODUCT_P2_ENV))
            else P3_PRODUCT_AUTHORITY_OPERATIONS
        ),
        expires_at=expires_at,
    )
    authenticator = StaticBearerAuthenticator(token=token, principal=principal)
    authority_resolver = ServerSessionProjectAuthorityResolver()

    binding_resolver: AgentManagerProjectBindingResolver | None = None
    executor: DirectProjectCodeExecutorAdapter | None = None
    try:
        binding_resolver = AgentManagerProjectBindingResolver(
            authority_resolver=authority_resolver,
            agent_manager=agent_manager,
            service=None,
            model_resolver=model_resolver,
            principal=principal,
        )
        store = SqliteTaskStore(database_path)
        executor = DirectProjectCodeExecutorAdapter(
            binding_resolver,
            database_path,
            demo_itinerary_fixture_enabled=_is_enabled(
                os.getenv(_PRODUCT_DEMO_POLICY_BYPASS_ENV)
            ),
            demo_itinerary_adjustment_checkpoint_enabled=(
                _is_enabled(os.getenv(_PRODUCT_DEMO_POLICY_BYPASS_ENV))
                and _is_enabled(os.getenv(_DEMO_ADJUSTMENT_CHECKPOINT_ENV))
            ),
            stream_observer=stream_observer,
            durability_store=store,
        )
        if direct_selection.profile not in executor.capability_profiles():
            raise FormalTaskViolation(
                "EXECUTOR_CAPABILITY_UNAVAILABLE",
                "constructed Direct Executor does not expose its selected profile",
                ErrorCode.CAPABILITY_UNAVAILABLE,
            )
        runtime_owner = _DirectP3RuntimeOwner(
            executor=executor,
            binding_resolver=binding_resolver,
        )
        core = PersistentTaskCore(
            store,
            executor,
            reconciliation_event_sink=reconciliation_event_sink,
            admission_policy=_PRODUCT_ADMISSION_POLICY,
        )
        return P3AuthenticatedComposition(
            authenticator=authenticator,
            authority_resolver=authority_resolver,
            core=core,
            confirmation_verifier=confirmation_verifier,
            model_resolver=model_resolver,
            binding_resolver=runtime_owner,
            telemetry=telemetry,
            policy=FormalTaskPolicyAdapter(commit_ledger),
            reconcile_interval=interval,
            executor_profiles=(direct_selection.profile,),
            validated_executor_configuration=validated_executor,
            execution_durability_level=direct_selection.profile.durability_level,
            admission_policy=_PRODUCT_ADMISSION_POLICY,
        )
    except BaseException:  # noqa: BLE001 -- clean every owner, then re-raise exactly
        if executor is not None:
            _abort_factory_owner(executor, owner_kind="executor")
        if binding_resolver is not None:
            _abort_factory_owner(binding_resolver, owner_kind="resolver")
        raise


def resolve_p3_database_path_from_environment() -> Path:
    """Resolve the application-owned P3 database path without opening it."""

    return _resolve_database_path(str(os.getenv(_DATABASE_ENV) or "").strip())


__all__ = [
    "AgentManagerProjectBindingResolver",
    "AuthenticatedPrincipal",
    "LoggingP3TelemetrySink",
    "NativeP3ActivationAuthority",
    "P3AuthenticatedComposition",
    "PreparedProductionIntentAuthority",
    "PreparedP3MutationConfirmation",
    "P3ConfirmationBinding",
    "P3RouteResult",
    "P3RouteTelemetry",
    "P3_MUTATIONS",
    "P3_PRODUCTION_MUTATIONS",
    "P3_PRODUCTION_OPERATIONS",
    "P3_ROUTE_METHODS",
    "P3_TARGETED_MUTATIONS",
    "ServerSessionProjectAuthorityResolver",
    "SqliteP3ConfirmationLedger",
    "StaticBearerAuthenticator",
    "create_p3_composition_from_environment",
    "resolve_p3_database_path_from_environment",
]
