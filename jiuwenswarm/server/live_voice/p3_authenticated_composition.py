# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Authenticated, server-resolved P3-alpha product composition.

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
import subprocess
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    Assurance,
    CommandEnvelope,
    ErrorCode,
    InputCommitState,
    QueryEnvelope,
    ResultEnvelope,
    ScopeRef,
    TurnCommitLedger,
)
from jiuwenswarm.common.utils import get_user_workspace_dir

from .formal_task_models import (
    FormalTaskViolation,
    FormalTaskSpec,
    ResolvedTaskContext,
    TaskAuthorizationGrant,
    utc_now,
)
from .persistent_task_core import PersistentTaskCore, ReconciliationEventSink
from .p3_confirmation import (
    P3ConfirmationBinding,
    P3ConfirmationVerifier,
    SqliteP3ConfirmationLedger,
    VerifiedP3Confirmation,
    p3_confirmation_intent_fingerprint,
)
from .p3_model_resolution import P3ModelResolver, ResolvedP3Model
from .product_authority import (
    AuthorityResourceBinding,
    TrustedAuthorityCandidate,
)
from .product_p3_text_adapter import ProductP3AuthorizedQuery
from .project_code_executor import (
    DirectProjectCodeExecutorAdapter,
    ProjectExecutionBinding,
    _project_content_fingerprint,
)
from .task_event_subscription import TaskEventSubscription
from .task_progress_return import TaskProgressOriginBinding
from .task_store import SqliteTaskStore
from .voice_task_policy import FormalTaskPolicyAdapter, FormalTaskPolicyInput

logger = logging.getLogger(__name__)

P3_ROUTE_METHODS: Mapping[str, str] = {
    "live_voice.task.create": "task.create",
    "live_voice.task.get": "task.get",
    "live_voice.task.list": "task.list",
    "live_voice.task.status": "task.status",
    "live_voice.task.cancel": "task.cancel",
    "live_voice.task.events": "task.events",
}
P3_OPERATIONS = frozenset(P3_ROUTE_METHODS.values())
P3_MUTATIONS = frozenset({"task.create", "task.cancel"})

_ENABLE_ENV = "JIUWENSWARM_LIVE_VOICE_P3_ENABLED"
_TOKEN_ENV = "JIUWENSWARM_LIVE_VOICE_P3_AUTH_TOKEN"
_PRINCIPAL_ENV = "JIUWENSWARM_LIVE_VOICE_P3_PRINCIPAL_ID"
_PROJECTS_ENV = "JIUWENSWARM_LIVE_VOICE_P3_PROJECT_IDS"
_EXPIRY_ENV = "JIUWENSWARM_LIVE_VOICE_P3_AUTH_EXPIRES_AT"
_DATABASE_ENV = "JIUWENSWARM_LIVE_VOICE_P3_DATABASE"
_RECONCILE_ENV = "JIUWENSWARM_LIVE_VOICE_P3_RECONCILE_SECONDS"
_PRODUCT_COMPOSITION_ENV = "JIUWENSWARM_LIVE_VOICE_PRODUCT_COMPOSITION_ENABLED"
_PRODUCT_P2_ENV = "JIUWENSWARM_LIVE_VOICE_PRODUCT_P2_ENABLED"
_PRODUCT_P2_OPERATION = "agent.chat"


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

    store_root = (get_user_workspace_dir() / "live_voice" / "p3alpha").resolve()
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


@dataclass(frozen=True, slots=True)
class ResolvedAuthority:
    principal: AuthenticatedPrincipal
    scope: ScopeRef
    context: ResolvedTaskContext


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


class ClosableBindingResolver(Protocol):
    async def close(self) -> None: ...


class _AttemptScopedProjectExecutor:
    """Create and retire the formal Code Agent at the isolated attempt root."""

    def __init__(self, agent_manager: Any) -> None:
        self._agent_manager = agent_manager

    async def process_background_code_task_stream(
        self, request: Any
    ) -> AsyncIterator[Any]:
        requested_root = (request.params or {}).get("project_dir")
        if not isinstance(requested_root, str):
            raise RuntimeError("EXECUTION_TARGET_NOT_BOUND")
        try:
            attempt_root = Path(requested_root).resolve(strict=True)
        except OSError as error:
            raise RuntimeError("EXECUTION_TARGET_NOT_BOUND") from error
        if not attempt_root.is_dir():
            raise RuntimeError("EXECUTION_TARGET_NOT_BOUND")

        async def fingerprint(failure_reason: str) -> str:
            try:
                return await asyncio.to_thread(
                    _project_content_fingerprint, attempt_root
                )
            except Exception as error:
                raise RuntimeError(failure_reason) from error

        before_setup = await fingerprint("EXECUTION_TARGET_NOT_BOUND")
        agent = await self._agent_manager.get_live_voice_formal_task_agent(
            str(attempt_root)
        )
        if agent is None:
            raise RuntimeError("EXECUTOR_CAPABILITY_UNAVAILABLE")
        cleanup = getattr(
            self._agent_manager, "cleanup_live_voice_formal_task_agent", None
        )
        if not callable(cleanup):
            raise RuntimeError("EXECUTOR_CAPABILITY_UNAVAILABLE")
        terminal_content: str | None = None
        stream_error: BaseException | None = None
        try:
            get_root = getattr(agent, "get_project_execution_root", None)
            if not callable(get_root) or _path_key(get_root()) != _path_key(attempt_root):
                raise RuntimeError("EXECUTION_TARGET_NOT_BOUND")
            agent.get_instance()
            if await fingerprint(
                "PROJECT_EXECUTOR_AGENT_SETUP_MUTATED_TARGET"
            ) != before_setup:
                raise RuntimeError("PROJECT_EXECUTOR_AGENT_SETUP_MUTATED_TARGET")
            async for chunk in agent.process_background_code_task_stream(request):
                if terminal_content is not None:
                    raise RuntimeError(
                        "PROJECT_EXECUTOR_AGENT_POST_TERMINAL_MUTATION"
                    )
                if bool(getattr(chunk, "is_complete", False)):
                    terminal_content = await fingerprint(
                        "PROJECT_EXECUTOR_AGENT_POST_TERMINAL_MUTATION"
                    )
                yield chunk
            if terminal_content is not None and (
                await fingerprint("PROJECT_EXECUTOR_AGENT_POST_TERMINAL_MUTATION")
                != terminal_content
            ):
                raise RuntimeError("PROJECT_EXECUTOR_AGENT_POST_TERMINAL_MUTATION")
        except BaseException as error:
            stream_error = error
            raise
        finally:
            before_cleanup = (
                await fingerprint("PROJECT_EXECUTOR_AGENT_CLEANUP_MUTATED_TARGET")
                if terminal_content is not None
                else None
            )
            try:
                cleaned = await cleanup(str(attempt_root), expected_agent=agent)
            except Exception as error:
                raise RuntimeError("PROJECT_EXECUTOR_AGENT_CLEANUP_FAILED") from error
            if not cleaned:
                raise RuntimeError("PROJECT_EXECUTOR_AGENT_CLEANUP_FAILED")
            if before_cleanup is not None and (
                await fingerprint("PROJECT_EXECUTOR_AGENT_CLEANUP_MUTATED_TARGET")
                != before_cleanup
            ):
                raise RuntimeError(
                    "PROJECT_EXECUTOR_AGENT_CLEANUP_MUTATED_TARGET"
                ) from stream_error


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
        if self._closed:
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
        dispatch_fence: Callable[[], Awaitable[None]] | None = None
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
            project_executor = _AttemptScopedProjectExecutor(self._agent_manager)
            execution_agent = project_executor

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
        return ProjectExecutionBinding(
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
            context_release=None,
            dispatch_fence=dispatch_fence,
        )

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        scheduler_stopped = self._service is None
        stop_scheduler = getattr(self._service, "stop_scheduler", None)
        if callable(stop_scheduler):
            try:
                await stop_scheduler(interrupt_running=True)
                scheduler_stopped = True
            except Exception as exc:  # noqa: BLE001 -- release remaining owners
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
                logger.warning(
                    "[LiveVoiceP3] carrier execution-context cleanup failed: %s",
                    exc,
                )
        cleanup = getattr(
            self._agent_manager, "cleanup_live_voice_formal_task_agents", None
        )
        if callable(cleanup):
            await cleanup()


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

    async def close(self) -> None:
        await self._executor.close(interrupt_running=True)
        await self._binding_resolver.close()


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
    ) -> None:
        _validate_reconcile_interval(reconcile_interval)
        self._authenticator = authenticator
        self._authority_resolver = authority_resolver
        self._core = core
        self._confirmation_verifier = confirmation_verifier
        self._model_resolver = model_resolver
        self._binding_resolver = binding_resolver
        self._policy = policy or FormalTaskPolicyAdapter()
        self._telemetry = telemetry or LoggingP3TelemetrySink()
        self._reconcile_interval = reconcile_interval
        self._clock = clock
        self._lifecycle_lock = asyncio.Lock()
        self._reconcile_lock = asyncio.Lock()
        self._active_condition = asyncio.Condition()
        self._active_operations = 0
        self._wake = asyncio.Event()
        self._worker: asyncio.Task[None] | None = None
        self._accepting = False
        self._closed = False
        self._cleanup_complete = False

    @property
    def accepting(self) -> bool:
        return self._accepting

    @property
    def mutation_authority_ready(self) -> bool:
        return self._confirmation_verifier is not None

    def resolve_product_authority_candidate(
        self,
        *,
        bearer_token: object,
        operation: str,
        session_id: str,
        correlation_id: str,
        required_capabilities: frozenset[str],
        task_id: str | None = None,
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
        if operation not in P3_OPERATIONS | {_PRODUCT_P2_OPERATION}:
            raise FormalTaskViolation(
                "FORMAL_TASK_AUTHORIZATION_DENIED",
                "formal product operation is unavailable",
                ErrorCode.PERMISSION_DENIED,
            )
        if required_capabilities != frozenset({operation}):
            raise FormalTaskViolation(
                "FORMAL_TASK_AUTHORIZATION_DENIED",
                "formal product capability is unavailable",
                ErrorCode.PERMISSION_DENIED,
            )
        targeted = operation in {"task.get", "task.status", "task.events"}
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
            self._require_exact_task_context(
                authority=authority,
                operation=operation,
                task_id=str(task_id),
                now=now,
            )
        elif operation == "task.list":
            self._require_list_task_contexts(authority=authority, now=now)

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
        if operation in {"task.get", "task.status", "task.events"}:
            self._require_exact_task_context(
                authority=current,
                operation=operation,
                task_id=str(target_task_id or ""),
                now=observed_at,
            )
        elif operation == "task.list":
            self._require_list_task_contexts(authority=current, now=observed_at)
        else:
            raise FormalTaskViolation(
                "UNSUPPORTED_FORMAL_TASK_INTENT",
                "formal task operation is unsupported",
                ErrorCode.UNSUPPORTED,
            )
        return self._core.query(
            query.envelope,
            query.authorization,
            now=observed_at,
        )

    def create_product_subscription(
        self,
        authorization: TaskAuthorizationGrant,
        binding: TaskProgressOriginBinding,
    ) -> TaskEventSubscription:
        """Create one live-only exact-task reader for text/UI projection."""

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
            if self._binding_resolver is not None:
                await self._binding_resolver.close()
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
        destructive = operation == "task.cancel"
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
    ) -> None:
        for task in self._core.store.list_tasks(authority.scope):
            self._require_task_context(
                authority=authority,
                operation="task.list",
                context=task.spec.context,
                now=now,
            )

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
    ) -> VerifiedP3Confirmation:
        if self._confirmation_verifier is None:
            raise FormalTaskViolation(
                "FORMAL_TASK_CONFIRMATION_REQUIRED",
                "formal task mutation requires a trusted confirmation owner",
                ErrorCode.PERMISSION_DENIED,
            )
        command_id = str(clean["command_id"])
        target_task_id = str(clean["task_id"]) if operation == "task.cancel" else None
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
                    "confirmation preparation supports task.create or task.cancel",
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
                require_clean=operation == "task.create",
            )
            authority.context.require_usable(
                scope=authority.scope,
                required_permissions=frozenset({"task.execute", "project.write"}),
                destructive=True,
                now=now,
            )
            if operation == "task.cancel":
                await self._run_blocking(
                    self._require_exact_task_context,
                    authority=authority,
                    operation=operation,
                    task_id=str(clean["task_id"]),
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
                if clean["source"] == "voice":
                    self._policy.require_voice_origin(
                        scope=authority.scope,
                        interaction_id=str(clean["interaction_id"]),
                        turn_id=str(clean["turn_id"]),
                        commit_id=str(clean["commit_id"]),
                        instruction=str(clean["instruction"]),
                    )
            target_task_id = (
                str(clean["task_id"]) if operation == "task.cancel" else None
            )
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
                    context=(authority.context if operation == "task.create" else None),
                    name=clean.get("name"),
                    instruction=clean.get("instruction"),
                    model=model,
                    source=str(clean["source"]),
                    interaction_id=clean.get("interaction_id"),
                    turn_id=clean.get("turn_id"),
                    commit_id=clean.get("commit_id"),
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
                    "mutation replay supports task.create or task.cancel",
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
                str(clean["task_id"]) if operation == "task.cancel" else None
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

    async def handle(
        self,
        *,
        operation: str,
        params: Mapping[str, object],
        request_id: str,
        session_id: str | None,
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
            principal = self._authenticator.authenticate(
                params.get("auth_token"), operation=operation, now=now
            )
            clean = self._validate_params(
                operation, params, session_id=session_id, now=now
            )
            authority = await self._run_blocking(
                self._authority_resolver.resolve,
                principal,
                session_id=clean["session_id"],
                now=now,
                require_clean=operation == "task.create",
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
            if operation in {"task.get", "task.status", "task.events", "task.cancel"}:
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
            verified_confirmation = (
                await self._verify_confirmation(
                    principal=principal,
                    scope=authority.scope,
                    operation=operation,
                    clean=clean,
                    context=(authority.context if operation == "task.create" else None),
                    model=resolved_model,
                    now=now,
                )
                if destructive
                else None
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
            )
            intent = FormalTaskPolicyInput(
                state=InputCommitState.COMMITTED,
                source=str(clean["source"]),
                operation=operation,
                request_id=_required_text(request_id, "request_id", maximum=256),
                issued_at=clean.get("issued_at", now),
                scope=authority.scope,
                correlation_id=clean.get("correlation_id", request_id),
                authorization=grant,
                command_id=clean.get("command_id"),
                interaction_id=clean.get("interaction_id"),
                turn_id=clean.get("turn_id"),
                commit_id=clean.get("commit_id"),
                task_id=clean.get("task_id"),
                name=clean.get("name"),
                instruction=clean.get("instruction"),
                context=(authority.context if operation == "task.create" else None),
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
                after_seq=int(clean.get("after_seq", -1)),
            )
            invocation = self._policy.map(intent)
            if isinstance(invocation.envelope, CommandEnvelope):
                result = await self._run_blocking(
                    self._core.execute,
                    invocation.envelope,
                    invocation.authorization,
                    context=invocation.context,
                    now=now,
                )
            else:
                assert isinstance(invocation.envelope, QueryEnvelope)
                result = await self._run_blocking(
                    self._core.query,
                    invocation.envelope,
                    invocation.authorization,
                    now=now,
                )
            if result.ok and destructive:
                self._wake.set()
            outcome = "accepted" if result.ok else "rejected"
            reason = None if result.error is None else result.error.reason
            return P3RouteResult(result.ok, result.to_dict())
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
                frozenset({"source"}),
            ),
            "task.list": (
                frozenset({"auth_token", "session_id"}),
                frozenset(),
            ),
            "task.events": (
                frozenset({"auth_token", "session_id", "task_id"}),
                frozenset({"after_seq"}),
            ),
            "task.get": (
                frozenset({"auth_token", "session_id", "task_id"}),
                frozenset(),
            ),
            "task.status": (
                frozenset({"auth_token", "session_id", "task_id"}),
                frozenset(),
            ),
        }
        required, optional = fields[operation]
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
                params["instruction"], "instruction", maximum=100_000
            )
        if "model_intent" in params:
            clean["model_intent"] = _required_text(
                params["model_intent"], "model_intent", maximum=256
            )
        source = _required_text(
            params.get("source", "structured"), "source", maximum=32
        )
        if source not in {"structured", "voice"}:
            raise FormalTaskViolation(
                "INVALID_TASK_INTENT_SOURCE",
                "formal task intent source must be voice or structured",
                ErrorCode.INVALID_ARGUMENT,
            )
        if source == "voice":
            if operation != "task.create" or not {
                "interaction_id",
                "turn_id",
                "commit_id",
            }.issubset(params):
                raise FormalTaskViolation(
                    "COMMITTED_ORIGIN_REQUIRED",
                    "voice task.create requires the exact committed turn origin",
                    ErrorCode.PERMISSION_DENIED,
                )
            clean["interaction_id"] = _required_text(
                params["interaction_id"], "interaction_id", maximum=256
            )
            clean["turn_id"] = _required_text(
                params["turn_id"], "turn_id", maximum=256
            )
            clean["commit_id"] = _required_text(
                params["commit_id"], "commit_id", maximum=256
            )
        elif (
            "interaction_id" in params
            or "turn_id" in params
            or "commit_id" in params
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
        return clean


def create_p3_composition_from_environment(
    *,
    agent_manager: Any,
    model_resolver: P3ModelResolver,
    confirmation_verifier: P3ConfirmationVerifier | None = None,
    telemetry: P3TelemetrySink | None = None,
    commit_ledger: TurnCommitLedger | None = None,
    reconciliation_event_sink: ReconciliationEventSink | None = None,
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
    database = str(os.getenv(_DATABASE_ENV) or "").strip()
    database_path = _resolve_database_path(database)
    principal = AuthenticatedPrincipal(
        principal_id=principal_id,
        allowed_project_ids=project_ids,
        allowed_operations=(
            P3_OPERATIONS | {_PRODUCT_P2_OPERATION}
            if _is_enabled(os.getenv(_PRODUCT_COMPOSITION_ENV))
            and _is_enabled(os.getenv(_PRODUCT_P2_ENV))
            else P3_OPERATIONS
        ),
        expires_at=expires_at,
    )
    authenticator = StaticBearerAuthenticator(token=token, principal=principal)
    authority_resolver = ServerSessionProjectAuthorityResolver()

    binding_resolver = AgentManagerProjectBindingResolver(
        authority_resolver=authority_resolver,
        agent_manager=agent_manager,
        service=None,
        model_resolver=model_resolver,
        principal=principal,
    )
    executor = DirectProjectCodeExecutorAdapter(binding_resolver, database_path)
    runtime_owner = _DirectP3RuntimeOwner(
        executor=executor,
        binding_resolver=binding_resolver,
    )
    store = SqliteTaskStore(database_path)
    core = PersistentTaskCore(
        store,
        executor,
        reconciliation_event_sink=reconciliation_event_sink,
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
    )


def resolve_p3_database_path_from_environment() -> Path:
    """Resolve the application-owned P3 database path without opening it."""

    return _resolve_database_path(str(os.getenv(_DATABASE_ENV) or "").strip())


__all__ = [
    "AgentManagerProjectBindingResolver",
    "AuthenticatedPrincipal",
    "LoggingP3TelemetrySink",
    "P3AuthenticatedComposition",
    "PreparedP3MutationConfirmation",
    "P3ConfirmationBinding",
    "P3RouteResult",
    "P3RouteTelemetry",
    "P3_ROUTE_METHODS",
    "ServerSessionProjectAuthorityResolver",
    "SqliteP3ConfirmationLedger",
    "StaticBearerAuthenticator",
    "create_p3_composition_from_environment",
    "resolve_p3_database_path_from_environment",
]
