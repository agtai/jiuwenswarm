# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Default-off OpenJiuwen continuation adapter for one project-file effect.

The module has no import-time AgentCore dependency and is not wired into the
production composition.  A trusted composition injects the root-public
coordinator and evidence factories from one exact AgentCore candidate.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    Assurance,
    ScopeRef,
    canonical_json_bytes,
)

from .openjiuwen_task_facade import (
    OpenJiuwenScopeBinding,
    derive_openjiuwen_scope_binding,
)
from .project_code_executor import (
    _apply_attempt_patch,
    _AttemptOwnershipLock,
    _expected_project_state_matches,
    _git_head,
    _git_root,
    _is_unsafe_filesystem_link,
    _path_key,
    _project_content_fingerprint,
    _project_tree_fingerprint,
    _reject_git_visible_symlinks,
    _target_support_fingerprints,
)

MAX_OPENJIUWEN_PROJECT_PATCH_BYTES = 1_048_576
OPENJIUWEN_PROJECT_EFFECT_KIND = "project.apply_patch"
OPENJIUWEN_PROJECT_EFFECT_REPLAY_POLICY = "never"

_MAX_ID_LENGTH = 255
_MAX_PATH_LENGTH = 4_096
_MAX_URI_LENGTH = 2_048
_MAX_SIGNED_BIGINT = (1 << 63) - 1
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_HEAD_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_EXPECTED_STATE_RE = re.compile(
    r"^(?:[0-9a-f]{64}|content-v2:[0-9a-f]{64}:[0-9a-f]{64})$"
)


class OpenJiuwenProjectFileEffectAdapterError(RuntimeError):
    """Stable fail-closed error without project paths or provider details."""

    def __init__(self, reason: str) -> None:
        super().__init__("OpenJiuwen project-file effect adapter is unavailable")
        self.reason = reason


class AgentCoreEffectAuthorityBindingPort(Protocol):
    session_id: str
    team_name: str
    member_name: str


class AgentCoreEffectContinuationAuthorityPort(Protocol):
    binding: AgentCoreEffectAuthorityBindingPort
    executor_authority: bool

    async def authorize_effect_call(self, authorization: object) -> bool: ...

    async def authorize_effect_observation(self, authorization: object) -> bool: ...


class AgentCoreExternalEffectCoordinatorPort(Protocol):
    async def dispatch(self, authorization: object) -> object | None: ...

    async def observe(self, authorization: object) -> object | None: ...


class AgentCoreExternalEffectCoordinatorFactory(Protocol):
    def __call__(
        self,
        authority: AgentCoreEffectContinuationAuthorityPort,
        adapter: object,
    ) -> AgentCoreExternalEffectCoordinatorPort: ...


class AgentCoreExternalEffectReceiptFactory(Protocol):
    def __call__(
        self,
        *,
        status: str,
        receipt_id: str,
        receipt_digest: str,
    ) -> object: ...


class AgentCoreExternalEffectObservationFactory(Protocol):
    def __call__(
        self,
        *,
        kind: str,
        evidence_digest: str,
        call_quiesced: bool,
    ) -> object: ...


class ProjectFileEffectLeasePort(Protocol):
    def release(self) -> None: ...


class ProjectFileEffectOwnershipPort(Protocol):
    """Cancellation-safe ownership acquisition; returned leases are exact-once."""

    async def acquire(
        self,
        root: Path,
        attempt_id: str,
        *,
        purpose: str,
    ) -> ProjectFileEffectLeasePort | None: ...


class CrossProcessProjectFileEffectOwnership:
    """Candidate ownership Port backed by the retained EXE-06 OS lock."""

    async def acquire(
        self,
        root: Path,
        attempt_id: str,
        *,
        purpose: str,
    ) -> ProjectFileEffectLeasePort | None:
        if purpose not in {"dispatch", "observe"}:
            raise _error("INVALID_PROJECT_EFFECT_OWNERSHIP_PURPOSE")
        acquired = await _run_blocking_to_quiescence(
            _AttemptOwnershipLock.try_acquire,
            root,
            attempt_id,
            cancellation_cleanup=lambda lease: lease.release(),
        )
        return acquired  # type: ignore[return-value]


@dataclass(frozen=True, slots=True)
class OpenJiuwenProjectFileEffectPlan:
    """Authority-free exact project facts prepared before journal dispatch."""

    scope: ScopeRef
    task_id: str
    execution_id: str
    profile_digest: str
    generation: int
    effect_id: str
    operation_kind: str
    operation_ordinal: int
    dispatch_ordinal: int
    provider_operation_key: str
    target_digest: str
    intended_effect_digest: str
    replay_policy: str
    project_source: str
    project_stable_id: str
    project_uri: str
    project_root: str
    attempt_id: str
    patch: bytes
    expected_tree: str
    before_tree: str
    before_content: str
    before_head: str
    protected_support: tuple[tuple[str, str], ...]

    @property
    def external_call_authority(self) -> bool:
        return False

    @property
    def task_mutation_authority(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class _ValidatedProjectEffectPlan:
    source: OpenJiuwenProjectFileEffectPlan
    binding: OpenJiuwenScopeBinding
    root: Path
    protected_support: dict[str, str]
    patch_digest: str


def _error(reason: str) -> OpenJiuwenProjectFileEffectAdapterError:
    return OpenJiuwenProjectFileEffectAdapterError(reason)


def _text(
    value: object,
    field_name: str,
    *,
    maximum: int = _MAX_ID_LENGTH,
) -> str:
    if type(value) is not str or not value.strip() or "\x00" in value:
        raise _error(f"INVALID_{field_name.upper()}")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise _error(f"INVALID_{field_name.upper()}") from None
    if len(value) > maximum:
        raise _error(f"INVALID_{field_name.upper()}")
    return value


def _integer(value: object, field_name: str, *, positive: bool = False) -> int:
    lower = 1 if positive else 0
    if type(value) is not int or not lower <= value <= _MAX_SIGNED_BIGINT:
        raise _error(f"INVALID_{field_name.upper()}")
    return value


def _sha256(value: object, field_name: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise _error(f"INVALID_{field_name.upper()}")
    return value


def _enum_value(value: object, field_name: str) -> str:
    raw = getattr(value, "value", value)
    return _text(raw, field_name)


def derive_openjiuwen_project_target_digest(
    scope: ScopeRef,
    *,
    project_source: str,
    project_stable_id: str,
    project_uri: str,
    project_root: str,
) -> str:
    """Bind one logical project target to one canonical physical Git root."""

    if not isinstance(scope, ScopeRef):
        raise _error("INVALID_PRODUCT_SCOPE")
    try:
        frozen_scope = ScopeRef.from_dict(scope.to_dict())
    except Exception:
        raise _error("INVALID_PRODUCT_SCOPE") from None
    source = _text(project_source, "project_source")
    stable_id = _text(project_stable_id, "project_stable_id")
    uri = _text(project_uri, "project_uri", maximum=_MAX_URI_LENGTH)
    root_text = _text(project_root, "project_root", maximum=_MAX_PATH_LENGTH)
    lexical_root = Path(root_text)
    if not lexical_root.is_absolute():
        raise _error("NON_CANONICAL_PROJECT_ROOT")
    try:
        root = lexical_root.resolve(strict=True)
        if lexical_root != root:
            raise _error("NON_CANONICAL_PROJECT_ROOT")
        if not root.is_dir() or _path_key(_git_root(root)) != _path_key(root):
            raise _error("PROJECT_ROOT_NOT_EXACT_GIT_ROOT")
    except OpenJiuwenProjectFileEffectAdapterError:
        raise
    except Exception:
        raise _error("PROJECT_ROOT_UNAVAILABLE") from None
    return hashlib.sha256(
        canonical_json_bytes(
            {
                "domain": "livevoice.openjiuwen.project-file-target.v1",
                "source": source,
                "stable_id": stable_id,
                "uri": uri,
                "scope": frozen_scope.to_dict(),
                "root_key": _path_key(root),
            }
        )
    ).hexdigest()


def derive_openjiuwen_project_intended_effect_digest(
    *,
    expected_tree: str,
    patch: bytes,
    before_tree: str,
    before_content: str,
    before_head: str,
    protected_support: tuple[tuple[str, str], ...],
) -> str:
    """Bind patch intent to every project safety precondition."""

    expected_tree = _text(expected_tree, "expected_tree")
    if _EXPECTED_STATE_RE.fullmatch(expected_tree) is None:
        raise _error("INVALID_EXPECTED_TREE")
    if (
        type(patch) is not bytes
        or not patch
        or len(patch) > MAX_OPENJIUWEN_PROJECT_PATCH_BYTES
    ):
        raise _error("INVALID_PATCH")
    before_tree = _sha256(before_tree, "before_tree")
    before_content = _sha256(before_content, "before_content")
    if type(before_head) is not str or _GIT_HEAD_RE.fullmatch(before_head) is None:
        raise _error("INVALID_BEFORE_HEAD")
    protected = _validated_protected_support(protected_support)
    return hashlib.sha256(
        canonical_json_bytes(
            {
                "domain": "livevoice.openjiuwen.project-file-intent.v1",
                "expected_tree": expected_tree,
                "patch_digest": hashlib.sha256(patch).hexdigest(),
                "before_tree": before_tree,
                "before_content": before_content,
                "before_head": before_head,
                "protected_support": dict(sorted(protected.items())),
            }
        )
    ).hexdigest()


def _validated_protected_support(
    support: object,
) -> dict[str, str]:
    if (
        type(support) is not tuple
        or not support
        or len(support) > 32
        or tuple(sorted(support)) != support
    ):
        raise _error("INVALID_PROTECTED_SUPPORT")
    protected: dict[str, str] = {}
    for item in support:
        if type(item) is not tuple or len(item) != 2:
            raise _error("INVALID_PROTECTED_SUPPORT")
        key = _text(item[0], "protected_support_key")
        digest = _sha256(item[1], "protected_support_digest")
        if key in protected:
            raise _error("INVALID_PROTECTED_SUPPORT")
        protected[key] = digest
    return protected


def _unsafe_path_component(path: Path) -> bool:
    current = path
    while True:
        if _is_unsafe_filesystem_link(current):
            return True
        parent = current.parent
        if parent == current:
            return False
        current = parent


def _validated_plan(
    value: object,
    *,
    expected_scope: ScopeRef,
    expected_binding: OpenJiuwenScopeBinding,
) -> _ValidatedProjectEffectPlan:
    if type(value) is not OpenJiuwenProjectFileEffectPlan:
        raise _error("INVALID_PROJECT_EFFECT_PLAN")
    try:
        scope = ScopeRef.from_dict(value.scope.to_dict())
    except Exception:
        raise _error("INVALID_PRODUCT_SCOPE") from None
    if (
        scope != expected_scope
        or scope.assurance is not Assurance.AUTHENTICATED
        or scope.project_id is None
        or scope.session_id is None
    ):
        raise _error("PROJECT_EFFECT_SCOPE_MISMATCH")
    try:
        binding = derive_openjiuwen_scope_binding(scope)
    except Exception:
        raise _error("INVALID_PRODUCT_SCOPE") from None
    if binding != expected_binding:
        raise _error("PROJECT_EFFECT_SCOPE_MISMATCH")

    _text(value.task_id, "task_id")
    execution_id = _text(value.execution_id, "execution_id")
    _sha256(value.profile_digest, "profile_digest")
    if _integer(value.generation, "generation") != 0:
        raise _error("UNSUPPORTED_PROJECT_EFFECT_GENERATION")
    effect_id = _text(value.effect_id, "effect_id")
    if _text(value.operation_kind, "operation_kind") != OPENJIUWEN_PROJECT_EFFECT_KIND:
        raise _error("UNSUPPORTED_PROJECT_EFFECT_KIND")
    if _integer(value.operation_ordinal, "operation_ordinal", positive=True) != 1:
        raise _error("UNSUPPORTED_PROJECT_EFFECT_ORDINAL")
    if _integer(value.dispatch_ordinal, "dispatch_ordinal", positive=True) != 1:
        raise _error("UNSUPPORTED_PROJECT_DISPATCH_ORDINAL")
    if _text(value.provider_operation_key, "provider_operation_key") != effect_id:
        raise _error("PROJECT_EFFECT_PROVIDER_KEY_MISMATCH")
    target_digest = _sha256(value.target_digest, "target_digest")
    intended_digest = _sha256(value.intended_effect_digest, "intended_effect_digest")
    if (
        _text(value.replay_policy, "replay_policy")
        != OPENJIUWEN_PROJECT_EFFECT_REPLAY_POLICY
    ):
        raise _error("UNSUPPORTED_PROJECT_EFFECT_REPLAY_POLICY")
    source = _text(value.project_source, "project_source")
    stable_id = _text(value.project_stable_id, "project_stable_id")
    uri = _text(value.project_uri, "project_uri", maximum=_MAX_URI_LENGTH)
    if stable_id != scope.project_id:
        raise _error("PROJECT_EFFECT_PROJECT_MISMATCH")
    if target_digest != derive_openjiuwen_project_target_digest(
        scope,
        project_source=source,
        project_stable_id=stable_id,
        project_uri=uri,
        project_root=value.project_root,
    ):
        raise _error("PROJECT_EFFECT_TARGET_DIGEST_MISMATCH")

    attempt_id = _text(value.attempt_id, "attempt_id")
    if attempt_id != execution_id:
        raise _error("PROJECT_EFFECT_ATTEMPT_MISMATCH")
    if (
        type(value.patch) is not bytes
        or not value.patch
        or len(value.patch) > MAX_OPENJIUWEN_PROJECT_PATCH_BYTES
    ):
        raise _error("INVALID_PATCH")
    expected_tree = _text(value.expected_tree, "expected_tree")
    if _EXPECTED_STATE_RE.fullmatch(expected_tree) is None:
        raise _error("INVALID_EXPECTED_TREE")
    before_tree = _sha256(value.before_tree, "before_tree")
    before_content = _sha256(value.before_content, "before_content")
    if (
        type(value.before_head) is not str
        or _GIT_HEAD_RE.fullmatch(value.before_head) is None
    ):
        raise _error("INVALID_BEFORE_HEAD")
    protected = _validated_protected_support(value.protected_support)
    if intended_digest != derive_openjiuwen_project_intended_effect_digest(
        expected_tree=expected_tree,
        patch=value.patch,
        before_tree=before_tree,
        before_content=before_content,
        before_head=value.before_head,
        protected_support=value.protected_support,
    ):
        raise _error("PROJECT_EFFECT_INTENDED_DIGEST_MISMATCH")

    root_text = _text(value.project_root, "project_root", maximum=_MAX_PATH_LENGTH)
    lexical_root = Path(root_text)
    if not lexical_root.is_absolute():
        raise _error("NON_CANONICAL_PROJECT_ROOT")
    try:
        if _unsafe_path_component(lexical_root):
            raise _error("UNSAFE_PROJECT_ROOT")
        root = lexical_root.resolve(strict=True)
        if lexical_root != root:
            raise _error("NON_CANONICAL_PROJECT_ROOT")
        if not root.is_dir() or _path_key(_git_root(root)) != _path_key(root):
            raise _error("PROJECT_ROOT_NOT_EXACT_GIT_ROOT")
    except OpenJiuwenProjectFileEffectAdapterError:
        raise
    except Exception:
        raise _error("PROJECT_ROOT_UNAVAILABLE") from None
    return _ValidatedProjectEffectPlan(
        source=value,
        binding=binding,
        root=root,
        protected_support=protected,
        patch_digest=hashlib.sha256(value.patch).hexdigest(),
    )


def _authorization_binding(
    authorization: object,
    plan: _ValidatedProjectEffectPlan,
    *,
    call: bool,
) -> None:
    binding = getattr(authorization, "binding", None)
    source = plan.source
    if (
        binding is None
        or getattr(binding, "team_name", None) != plan.binding.team_name
        or getattr(binding, "task_id", None) != source.task_id
        or getattr(binding, "execution_id", None) != source.execution_id
        or getattr(binding, "profile_digest", None) != source.profile_digest
        or getattr(binding, "generation", None) != source.generation
        or getattr(binding, "effect_id", None) != source.effect_id
        or getattr(binding, "operation_kind", None) != source.operation_kind
        or getattr(binding, "operation_ordinal", None) != source.operation_ordinal
        or getattr(binding, "provider_operation_key", None)
        != source.provider_operation_key
        or getattr(binding, "target_digest", None) != source.target_digest
        or getattr(binding, "intended_effect_digest", None)
        != source.intended_effect_digest
        or _enum_value(
            getattr(binding, "replay_policy", None), "authorization_replay_policy"
        )
        != source.replay_policy
        or type(getattr(authorization, "claim_owner_id", None)) is not str
        or not getattr(authorization, "claim_owner_id").strip()
        or type(getattr(authorization, "claim_version", None)) is not int
        or getattr(authorization, "claim_version") <= 0
        or type(getattr(authorization, "effect_version", None)) is not int
        or getattr(authorization, "effect_version") <= 0
        or type(getattr(authorization, "journal_head", None)) is not int
        or getattr(authorization, "journal_head") <= 0
        or _SHA256_RE.fullmatch(getattr(authorization, "journal_prefix_digest", ""))
        is None
        or type(getattr(authorization, "expires_at", None)) is not int
        or getattr(authorization, "expires_at") <= 0
        or getattr(authorization, "external_call_authority", None) is not call
    ):
        raise _error("PROJECT_EFFECT_AUTHORIZATION_MISMATCH")
    token_name = "continuation_token" if call else "claim_token"
    _text(getattr(authorization, token_name, None), token_name)
    if (
        call
        and getattr(authorization, "dispatch_ordinal", None) != source.dispatch_ordinal
    ):
        raise _error("PROJECT_EFFECT_AUTHORIZATION_MISMATCH")


def _project_evidence(
    plan: _ValidatedProjectEffectPlan,
    *,
    result: str,
    actual_head: str,
    actual_tree: str,
    actual_content: str,
    actual_support: dict[str, str],
) -> str:
    return hashlib.sha256(
        canonical_json_bytes(
            {
                "effect_id": plan.source.effect_id,
                "execution_id": plan.source.execution_id,
                "result": result,
                "expected_tree": plan.source.expected_tree,
                "patch_digest": plan.patch_digest,
                "actual_head": actual_head,
                "actual_tree": actual_tree,
                "actual_content": actual_content,
                "actual_support": dict(sorted(actual_support.items())),
            }
        )
    ).hexdigest()


async def _run_blocking_to_quiescence(
    function: object,
    /,
    *args: object,
    cancellation_cleanup: object | None = None,
    **kwargs: object,
) -> object:
    """Do not release project ownership until a cancelled worker really exits."""

    task = asyncio.create_task(asyncio.to_thread(function, *args, **kwargs))  # type: ignore[arg-type]
    cancelled = False
    while True:
        try:
            result = await asyncio.shield(task)
            break
        except asyncio.CancelledError:
            cancelled = True
            continue
        except BaseException:
            if cancelled:
                raise asyncio.CancelledError from None
            raise
    if cancelled:
        if result is not None and callable(cancellation_cleanup):
            cancellation_cleanup(result)
        raise asyncio.CancelledError
    return result


def _inspect_project_state(
    plan: _ValidatedProjectEffectPlan,
) -> tuple[str, str, str, dict[str, str], bool]:
    root = _revalidate_owned_root(plan)
    _reject_git_visible_symlinks(root)
    return (
        _git_head(root),
        _project_tree_fingerprint(root),
        _project_content_fingerprint(root),
        _target_support_fingerprints(root),
        _expected_project_state_matches(root, plan.source.expected_tree),
    )


def _revalidate_owned_root(plan: _ValidatedProjectEffectPlan) -> Path:
    """Rebind the frozen lexical root after the ownership await boundary."""

    lexical_root = Path(plan.source.project_root)
    try:
        if _unsafe_path_component(lexical_root):
            raise _error("UNSAFE_PROJECT_ROOT")
        resolved = lexical_root.resolve(strict=True)
        if (
            lexical_root != resolved
            or resolved != plan.root
            or not resolved.is_dir()
            or _path_key(_git_root(resolved)) != _path_key(resolved)
        ):
            raise _error("PROJECT_ROOT_AUTHORITY_CHANGED")
    except OpenJiuwenProjectFileEffectAdapterError:
        raise
    except Exception:
        raise _error("PROJECT_ROOT_AUTHORITY_CHANGED") from None
    return resolved


def _apply_owned_project_effect(plan: _ValidatedProjectEffectPlan) -> None:
    source = plan.source
    root = _revalidate_owned_root(plan)
    _reject_git_visible_symlinks(root)
    _apply_attempt_patch(
        root,
        source.patch,
        expected_tree=source.expected_tree,
        before_tree=source.before_tree,
        before_head=source.before_head,
        protected_support=plan.protected_support,
    )


class _BoundProjectFileEffectPort:
    __slots__ = (
        "_observation_factory",
        "_ownership",
        "_plan",
        "_receipt_factory",
    )

    def __init__(
        self,
        plan: _ValidatedProjectEffectPlan,
        *,
        receipt_factory: AgentCoreExternalEffectReceiptFactory,
        observation_factory: AgentCoreExternalEffectObservationFactory,
        ownership: ProjectFileEffectOwnershipPort,
    ) -> None:
        self._plan = plan
        self._receipt_factory = receipt_factory
        self._observation_factory = observation_factory
        self._ownership = ownership

    async def dispatch(self, authorization: object) -> object:
        _authorization_binding(authorization, self._plan, call=True)
        source = self._plan.source
        ownership = await self._ownership.acquire(
            self._plan.root,
            source.attempt_id,
            purpose="dispatch",
        )
        if ownership is None:
            raise _error("PROJECT_ATTEMPT_OWNERSHIP_UNAVAILABLE")
        try:
            await _run_blocking_to_quiescence(
                _apply_owned_project_effect,
                self._plan,
            )
            receipt_digest = hashlib.sha256(
                canonical_json_bytes(
                    {
                        "effect_id": source.effect_id,
                        "dispatch_ordinal": source.dispatch_ordinal,
                        "provider_operation_key": source.provider_operation_key,
                        "patch_digest": self._plan.patch_digest,
                        "expected_tree": source.expected_tree,
                        "result": "accepted",
                    }
                )
            ).hexdigest()
            return self._receipt_factory(
                status="accepted",
                receipt_id=f"project-apply-{receipt_digest[:32]}",
                receipt_digest=receipt_digest,
            )
        finally:
            ownership.release()

    async def observe(self, authorization: object) -> object:
        _authorization_binding(authorization, self._plan, call=False)
        source = self._plan.source
        ownership = await self._ownership.acquire(
            self._plan.root,
            source.attempt_id,
            purpose="observe",
        )
        if ownership is None:
            raise _error("PROJECT_ATTEMPT_OWNERSHIP_UNAVAILABLE")
        try:
            inspection = await _run_blocking_to_quiescence(
                _inspect_project_state,
                self._plan,
            )
            (
                actual_head,
                actual_tree,
                actual_content,
                actual_support,
                expected_state_present,
            ) = inspection  # type: ignore[misc]
            unchanged_authority = (
                actual_head == source.before_head
                and actual_support == self._plan.protected_support
            )
            if unchanged_authority and expected_state_present:
                kind = "observed"
                call_quiesced = False
            elif (
                unchanged_authority
                and actual_tree == source.before_tree
                and actual_content == source.before_content
            ):
                kind = "not_observed"
                call_quiesced = True
            else:
                kind = "ambiguous"
                call_quiesced = False
            return self._observation_factory(
                kind=kind,
                evidence_digest=_project_evidence(
                    self._plan,
                    result=kind,
                    actual_head=actual_head,
                    actual_tree=actual_tree,
                    actual_content=actual_content,
                    actual_support=actual_support,
                ),
                call_quiesced=call_quiesced,
            )
        finally:
            ownership.release()


class OpenJiuwenProjectFileEffectAdapter:
    """Invoke one retained project effect only through AgentCore coordinator."""

    __slots__ = (
        "_binding",
        "_coordinator_factory",
        "_handle",
        "_observation_factory",
        "_ownership",
        "_receipt_factory",
        "_scope",
    )

    def __init__(
        self,
        handle: AgentCoreEffectContinuationAuthorityPort,
        scope: ScopeRef,
        *,
        coordinator_factory: AgentCoreExternalEffectCoordinatorFactory,
        receipt_factory: AgentCoreExternalEffectReceiptFactory,
        observation_factory: AgentCoreExternalEffectObservationFactory,
        ownership: ProjectFileEffectOwnershipPort,
    ) -> None:
        if not isinstance(scope, ScopeRef):
            raise _error("INVALID_PRODUCT_SCOPE")
        try:
            self._scope = ScopeRef.from_dict(scope.to_dict())
            self._binding = derive_openjiuwen_scope_binding(self._scope)
        except Exception:
            raise _error("INVALID_PRODUCT_SCOPE") from None
        self._handle = handle
        self._require_handle_binding()
        if not callable(coordinator_factory):
            raise _error("INVALID_EFFECT_COORDINATOR_FACTORY")
        if not callable(receipt_factory) or not callable(observation_factory):
            raise _error("INVALID_EFFECT_EVIDENCE_FACTORY")
        if not callable(getattr(ownership, "acquire", None)):
            raise _error("INVALID_PROJECT_EFFECT_OWNERSHIP")
        self._coordinator_factory = coordinator_factory
        self._receipt_factory = receipt_factory
        self._observation_factory = observation_factory
        self._ownership = ownership

    @property
    def binding(self) -> OpenJiuwenScopeBinding:
        return self._binding

    @property
    def executor_authority(self) -> bool:
        return False

    def _require_handle_binding(self) -> None:
        binding = getattr(self._handle, "binding", None)
        if (
            binding is None
            or getattr(binding, "session_id", None) != self._binding.session_id
            or getattr(binding, "team_name", None) != self._binding.team_name
            or getattr(binding, "member_name", None) != self._binding.member_name
            or getattr(self._handle, "executor_authority", None) is not False
            or not callable(getattr(self._handle, "authorize_effect_call", None))
            or not callable(getattr(self._handle, "authorize_effect_observation", None))
        ):
            raise _error("AGENTCORE_EFFECT_BINDING_MISMATCH")

    def _coordinator(
        self,
        plan: _ValidatedProjectEffectPlan,
    ) -> AgentCoreExternalEffectCoordinatorPort:
        port = _BoundProjectFileEffectPort(
            plan,
            receipt_factory=self._receipt_factory,
            observation_factory=self._observation_factory,
            ownership=self._ownership,
        )
        try:
            coordinator = self._coordinator_factory(self._handle, port)
        except Exception:
            raise _error("EFFECT_COORDINATOR_UNAVAILABLE") from None
        if any(
            not callable(getattr(coordinator, name, None))
            for name in ("dispatch", "observe")
        ):
            raise _error("INVALID_EFFECT_COORDINATOR")
        return coordinator

    async def dispatch(
        self,
        plan: OpenJiuwenProjectFileEffectPlan,
        authorization: object,
    ) -> object | None:
        self._require_handle_binding()
        verified = _validated_plan(
            plan,
            expected_scope=self._scope,
            expected_binding=self._binding,
        )
        _authorization_binding(authorization, verified, call=True)
        coordinator = self._coordinator(verified)
        try:
            result = await coordinator.dispatch(authorization)
        except asyncio.CancelledError:
            raise
        except Exception:
            return None
        self._require_handle_binding()
        if result is None:
            return None
        if (
            _enum_value(getattr(result, "status", None), "receipt_status") != "accepted"
            or not _text(getattr(result, "receipt_id", None), "receipt_id")
            or _SHA256_RE.fullmatch(getattr(result, "receipt_digest", "")) is None
        ):
            raise _error("INVALID_EFFECT_RECEIPT")
        return result

    async def observe(
        self,
        plan: OpenJiuwenProjectFileEffectPlan,
        authorization: object,
    ) -> object | None:
        self._require_handle_binding()
        verified = _validated_plan(
            plan,
            expected_scope=self._scope,
            expected_binding=self._binding,
        )
        _authorization_binding(authorization, verified, call=False)
        coordinator = self._coordinator(verified)
        try:
            result = await coordinator.observe(authorization)
        except asyncio.CancelledError:
            raise
        except Exception:
            return None
        self._require_handle_binding()
        if result is None:
            return None
        kind = _enum_value(getattr(result, "kind", None), "observation_kind")
        call_quiesced = getattr(result, "call_quiesced", None)
        if (
            kind not in {"not_observed", "observed", "ambiguous"}
            or _SHA256_RE.fullmatch(getattr(result, "evidence_digest", "")) is None
            or type(call_quiesced) is not bool
            or (call_quiesced and kind != "not_observed")
        ):
            raise _error("INVALID_EFFECT_OBSERVATION")
        return result


__all__ = [
    "AgentCoreEffectContinuationAuthorityPort",
    "AgentCoreExternalEffectCoordinatorFactory",
    "AgentCoreExternalEffectCoordinatorPort",
    "AgentCoreExternalEffectObservationFactory",
    "AgentCoreExternalEffectReceiptFactory",
    "CrossProcessProjectFileEffectOwnership",
    "MAX_OPENJIUWEN_PROJECT_PATCH_BYTES",
    "OPENJIUWEN_PROJECT_EFFECT_KIND",
    "OPENJIUWEN_PROJECT_EFFECT_REPLAY_POLICY",
    "OpenJiuwenProjectFileEffectAdapter",
    "OpenJiuwenProjectFileEffectAdapterError",
    "OpenJiuwenProjectFileEffectPlan",
    "ProjectFileEffectLeasePort",
    "ProjectFileEffectOwnershipPort",
    "derive_openjiuwen_project_intended_effect_digest",
    "derive_openjiuwen_project_target_digest",
]
