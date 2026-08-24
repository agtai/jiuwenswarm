# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import asyncio
import subprocess
import threading
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from types import SimpleNamespace

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import Assurance, ScopeRef
from jiuwenswarm.server.live_voice import openjiuwen_project_file_effect_adapter
from jiuwenswarm.server.live_voice.openjiuwen_project_file_effect_adapter import (
    MAX_OPENJIUWEN_PROJECT_PATCH_BYTES,
    OPENJIUWEN_PROJECT_EFFECT_KIND,
    OPENJIUWEN_PROJECT_EFFECT_REPLAY_POLICY,
    CrossProcessProjectFileEffectOwnership,
    OpenJiuwenProjectFileEffectAdapter,
    OpenJiuwenProjectFileEffectAdapterError,
    OpenJiuwenProjectFileEffectPlan,
    derive_openjiuwen_project_intended_effect_digest,
    derive_openjiuwen_project_target_digest,
)
from jiuwenswarm.server.live_voice.openjiuwen_task_facade import (
    derive_openjiuwen_scope_binding,
)
from jiuwenswarm.server.live_voice.project_code_executor import (
    _AttemptOwnershipLock,
    _encode_expected_project_state,
    _git_head,
    _git_visible_patch,
    _project_content_fingerprint,
    _project_tree_fingerprint,
    _target_support_fingerprints,
)

SCOPE = ScopeRef("principal-1", "project-1", "session-1", Assurance.AUTHENTICATED)
OTHER_SCOPE = ScopeRef(
    "principal-2",
    "project-2",
    "session-2",
    Assurance.AUTHENTICATED,
)
PROFILE = "1" * 64


class _ReceiptStatus(str, Enum):
    ACCEPTED = "accepted"


class _ObservationKind(str, Enum):
    NOT_OBSERVED = "not_observed"
    OBSERVED = "observed"
    AMBIGUOUS = "ambiguous"


class _ReplayPolicy(str, Enum):
    NEVER = "never"


@dataclass(frozen=True, slots=True)
class _Receipt:
    status: _ReceiptStatus
    receipt_id: str
    receipt_digest: str


@dataclass(frozen=True, slots=True)
class _Observation:
    kind: _ObservationKind
    evidence_digest: str
    call_quiesced: bool


@dataclass(frozen=True, slots=True)
class _HandleBinding:
    session_id: str
    team_name: str
    member_name: str


class _Handle:
    executor_authority = False

    def __init__(self, scope: ScopeRef = SCOPE) -> None:
        binding = derive_openjiuwen_scope_binding(scope)
        self.binding = _HandleBinding(
            binding.session_id,
            binding.team_name,
            binding.member_name,
        )
        self.call_authorizations = 0
        self.observation_authorizations = 0
        self._used_calls: set[int] = set()
        self._used_observations: set[int] = set()

    async def authorize_effect_call(self, authorization: object) -> bool:
        self.call_authorizations += 1
        key = id(authorization)
        if key in self._used_calls:
            return False
        self._used_calls.add(key)
        return True

    async def authorize_effect_observation(self, authorization: object) -> bool:
        self.observation_authorizations += 1
        key = id(authorization)
        if key in self._used_observations:
            return False
        self._used_observations.add(key)
        return True


class _Coordinator:
    def __init__(self, authority: _Handle, adapter: object) -> None:
        self._authority = authority
        self._adapter = adapter

    async def dispatch(self, authorization: object) -> object | None:
        if not await self._authority.authorize_effect_call(authorization):
            return None
        return await self._adapter.dispatch(authorization)  # type: ignore[attr-defined]

    async def observe(self, authorization: object) -> object | None:
        if not await self._authority.authorize_effect_observation(authorization):
            return None
        return await self._adapter.observe(authorization)  # type: ignore[attr-defined]


class _LoseDispatchResponseCoordinator(_Coordinator):
    async def dispatch(self, authorization: object) -> None:
        if not await self._authority.authorize_effect_call(authorization):
            return None
        await self._adapter.dispatch(authorization)  # type: ignore[attr-defined]
        return None


class _CountingOwnership:
    def __init__(self) -> None:
        self.inner = CrossProcessProjectFileEffectOwnership()
        self.acquisitions: list[str] = []

    async def acquire(
        self,
        root: Path,
        attempt_id: str,
        *,
        purpose: str,
    ) -> object | None:
        self.acquisitions.append(purpose)
        return await self.inner.acquire(root, attempt_id, purpose=purpose)


class _Lease:
    def release(self) -> None:
        return None


class _RenameRootOwnership:
    def __init__(self) -> None:
        self.moved_root: Path | None = None

    async def acquire(
        self,
        root: Path,
        attempt_id: str,
        *,
        purpose: str,
    ) -> _Lease:
        del attempt_id, purpose
        moved = root.with_name(f"{root.name}-moved")
        root.rename(moved)
        self.moved_root = moved
        return _Lease()


def _run(root: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _repo(tmp_path: Path, name: str = "project") -> Path:
    root = tmp_path / name
    root.mkdir()
    _run(root, "init")
    _run(root, "config", "user.email", "test@example.invalid")
    _run(root, "config", "user.name", "Test User")
    (root / "sample.txt").write_text("before\n", encoding="utf-8")
    (root / ".gitignore").write_text(
        "coding_memory/\nprompt_attachment/\n.agent_history/\n",
        encoding="utf-8",
    )
    _run(root, "add", "sample.txt", ".gitignore")
    _run(root, "commit", "-m", "baseline")
    return root.resolve()


def _plan(root: Path, *, scope: ScopeRef = SCOPE) -> OpenJiuwenProjectFileEffectPlan:
    before_head = _git_head(root)
    before_tree = _project_tree_fingerprint(root)
    before_content = _project_content_fingerprint(root)
    support = tuple(sorted(_target_support_fingerprints(root).items()))
    (root / "sample.txt").write_text("after\n", encoding="utf-8")
    patch = _git_visible_patch(root)
    after_content = _project_content_fingerprint(root)
    expected_tree = _encode_expected_project_state(after_content, patch=patch)
    (root / "sample.txt").write_text("before\n", encoding="utf-8")
    return OpenJiuwenProjectFileEffectPlan(
        scope=scope,
        task_id="task-1",
        execution_id="execution-1",
        profile_digest=PROFILE,
        generation=0,
        effect_id="effect-1",
        operation_kind=OPENJIUWEN_PROJECT_EFFECT_KIND,
        operation_ordinal=1,
        dispatch_ordinal=1,
        provider_operation_key="effect-1",
        target_digest=derive_openjiuwen_project_target_digest(
            scope,
            project_source="local",
            project_stable_id=scope.project_id or "",
            project_uri=f"project://{scope.project_id}",
            project_root=str(root),
        ),
        intended_effect_digest=derive_openjiuwen_project_intended_effect_digest(
            expected_tree=expected_tree,
            patch=patch,
            before_tree=before_tree,
            before_content=before_content,
            before_head=before_head,
            protected_support=support,
        ),
        replay_policy=OPENJIUWEN_PROJECT_EFFECT_REPLAY_POLICY,
        project_source="local",
        project_stable_id=scope.project_id or "",
        project_uri=f"project://{scope.project_id}",
        project_root=str(root),
        attempt_id="execution-1",
        patch=patch,
        expected_tree=expected_tree,
        before_tree=before_tree,
        before_content=before_content,
        before_head=before_head,
        protected_support=support,
    )


def _authorization(
    plan: OpenJiuwenProjectFileEffectPlan,
    *,
    call: bool,
) -> object:
    scope_binding = derive_openjiuwen_scope_binding(plan.scope)
    binding = SimpleNamespace(
        team_name=scope_binding.team_name,
        task_id=plan.task_id,
        execution_id=plan.execution_id,
        profile_digest=plan.profile_digest,
        generation=plan.generation,
        effect_id=plan.effect_id,
        operation_kind=plan.operation_kind,
        operation_ordinal=plan.operation_ordinal,
        provider_operation_key=plan.provider_operation_key,
        target_digest=plan.target_digest,
        intended_effect_digest=plan.intended_effect_digest,
        replay_policy=_ReplayPolicy.NEVER,
    )
    common = {
        "binding": binding,
        "claim_owner_id": "runtime-1" if call else "recovery-1",
        "claim_version": 1,
        "effect_version": 3,
        "journal_head": 2,
        "journal_prefix_digest": "2" * 64,
        "expires_at": 2**62,
        "external_call_authority": call,
    }
    if call:
        common.update(
            continuation_token="continuation-1",
            dispatch_ordinal=plan.dispatch_ordinal,
        )
    else:
        common.update(claim_token="observation-claim-1")
    return SimpleNamespace(**common)


def _adapter(
    handle: _Handle,
    ownership: _CountingOwnership,
    *,
    lose_dispatch_response: bool = False,
) -> OpenJiuwenProjectFileEffectAdapter:
    coordinator = (
        _LoseDispatchResponseCoordinator if lose_dispatch_response else _Coordinator
    )
    return OpenJiuwenProjectFileEffectAdapter(
        handle,
        SCOPE,
        coordinator_factory=coordinator,
        receipt_factory=lambda **values: _Receipt(
            status=_ReceiptStatus(values["status"]),
            receipt_id=values["receipt_id"],
            receipt_digest=values["receipt_digest"],
        ),
        observation_factory=lambda **values: _Observation(
            kind=_ObservationKind(values["kind"]),
            evidence_digest=values["evidence_digest"],
            call_quiesced=values["call_quiesced"],
        ),
        ownership=ownership,
    )


@pytest.mark.asyncio
async def test_dispatch_is_token_gated_exact_once_and_root_bound(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    other_root = _repo(tmp_path, "other-project")
    plan = _plan(root)
    other_plan = _plan(other_root)
    cross_handle = _Handle()
    cross_ownership = _CountingOwnership()
    with pytest.raises(OpenJiuwenProjectFileEffectAdapterError):
        await _adapter(cross_handle, cross_ownership).dispatch(
            other_plan,
            _authorization(plan, call=True),
        )
    assert cross_handle.call_authorizations == 0
    assert cross_ownership.acquisitions == []
    assert (other_root / "sample.txt").read_text(encoding="utf-8") == "before\n"

    handle = _Handle()
    ownership = _CountingOwnership()
    adapter = _adapter(handle, ownership)
    authorization = _authorization(plan, call=True)

    first, second = await asyncio.gather(
        adapter.dispatch(plan, authorization),
        adapter.dispatch(plan, authorization),
    )
    receipt = first or second

    assert receipt is not None and receipt.status is _ReceiptStatus.ACCEPTED
    assert (first is None) != (second is None)
    assert (root / "sample.txt").read_text(encoding="utf-8") == "after\n"
    assert (other_root / "sample.txt").read_text(encoding="utf-8") == "before\n"
    assert ownership.acquisitions == ["dispatch"]
    assert handle.call_authorizations == 2
    assert plan.target_digest != derive_openjiuwen_project_target_digest(
        SCOPE,
        project_source=plan.project_source,
        project_stable_id=plan.project_stable_id,
        project_uri=plan.project_uri,
        project_root=str(other_root),
    )


@pytest.mark.asyncio
async def test_response_loss_recovers_observed_without_second_file_call(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    plan = _plan(root)
    handle = _Handle()
    ownership = _CountingOwnership()
    adapter = _adapter(handle, ownership, lose_dispatch_response=True)

    assert await adapter.dispatch(plan, _authorization(plan, call=True)) is None
    observation = await adapter.observe(plan, _authorization(plan, call=False))

    assert observation is not None
    assert observation.kind is _ObservationKind.OBSERVED
    assert observation.call_quiesced is False
    assert (root / "sample.txt").read_text(encoding="utf-8") == "after\n"
    assert ownership.acquisitions == ["dispatch", "observe"]


@pytest.mark.asyncio
async def test_observation_distinguishes_quiesced_before_and_ambiguous_drift(
    tmp_path: Path,
) -> None:
    before_root = _repo(tmp_path, "before-project")
    before_plan = _plan(before_root)
    before = await _adapter(_Handle(), _CountingOwnership()).observe(
        before_plan,
        _authorization(before_plan, call=False),
    )
    assert before is not None
    assert before.kind is _ObservationKind.NOT_OBSERVED
    assert before.call_quiesced is True

    drift_root = _repo(tmp_path, "drift-project")
    drift_plan = _plan(drift_root)
    (drift_root / "sample.txt").write_text("foreign\n", encoding="utf-8")
    drift = await _adapter(_Handle(), _CountingOwnership()).observe(
        drift_plan,
        _authorization(drift_plan, call=False),
    )
    assert drift is not None
    assert drift.kind is _ObservationKind.AMBIGUOUS
    assert drift.call_quiesced is False


@pytest.mark.asyncio
async def test_observation_requires_unchanged_head_and_protected_support(
    tmp_path: Path,
) -> None:
    head_root = _repo(tmp_path, "head-project")
    head_plan = _plan(head_root)
    head_adapter = _adapter(_Handle(), _CountingOwnership())
    assert await head_adapter.dispatch(head_plan, _authorization(head_plan, call=True))
    _run(head_root, "add", "sample.txt")
    _run(head_root, "commit", "-m", "foreign head")
    head_observation = await head_adapter.observe(
        head_plan,
        _authorization(head_plan, call=False),
    )
    assert head_observation is not None
    assert head_observation.kind is _ObservationKind.AMBIGUOUS

    support_root = _repo(tmp_path, "support-project")
    support_plan = _plan(support_root)
    support_adapter = _adapter(_Handle(), _CountingOwnership())
    assert await support_adapter.dispatch(
        support_plan, _authorization(support_plan, call=True)
    )
    (support_root / "coding_memory").mkdir()
    (support_root / "coding_memory" / "foreign.txt").write_text(
        "foreign\n", encoding="utf-8"
    )
    support_observation = await support_adapter.observe(
        support_plan,
        _authorization(support_plan, call=False),
    )
    assert support_observation is not None
    assert support_observation.kind is _ObservationKind.AMBIGUOUS


@pytest.mark.asyncio
async def test_cancelled_apply_retains_lock_until_worker_quiesces(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _repo(tmp_path)
    plan = _plan(root)
    entered = threading.Event()
    release = threading.Event()

    def blocked_apply(_plan: object) -> None:
        entered.set()
        assert release.wait(timeout=5)

    monkeypatch.setattr(
        openjiuwen_project_file_effect_adapter,
        "_apply_owned_project_effect",
        blocked_apply,
    )
    task = asyncio.create_task(
        _adapter(_Handle(), _CountingOwnership()).dispatch(
            plan,
            _authorization(plan, call=True),
        )
    )
    assert await asyncio.to_thread(entered.wait, 5)
    task.cancel()
    await asyncio.sleep(0.05)
    assert _AttemptOwnershipLock.try_acquire(root, plan.attempt_id) is None
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    reacquired = _AttemptOwnershipLock.try_acquire(root, plan.attempt_id)
    assert reacquired is not None
    reacquired.release()


@pytest.mark.asyncio
async def test_cancelled_probe_retains_lock_until_worker_quiesces(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _repo(tmp_path)
    plan = _plan(root)
    entered = threading.Event()
    release = threading.Event()

    def blocked_probe(_plan: object) -> object:
        entered.set()
        assert release.wait(timeout=5)
        return (
            plan.before_head,
            plan.before_tree,
            plan.before_content,
            dict(plan.protected_support),
            False,
        )

    monkeypatch.setattr(
        openjiuwen_project_file_effect_adapter,
        "_inspect_project_state",
        blocked_probe,
    )
    task = asyncio.create_task(
        _adapter(_Handle(), _CountingOwnership()).observe(
            plan,
            _authorization(plan, call=False),
        )
    )
    assert await asyncio.to_thread(entered.wait, 5)
    task.cancel()
    await asyncio.sleep(0.05)
    assert _AttemptOwnershipLock.try_acquire(root, plan.attempt_id) is None
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    reacquired = _AttemptOwnershipLock.try_acquire(root, plan.attempt_id)
    assert reacquired is not None
    reacquired.release()


@pytest.mark.asyncio
async def test_cancelled_lock_acquisition_releases_late_acquired_lease(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _repo(tmp_path)
    entered = threading.Event()
    release = threading.Event()
    original = _AttemptOwnershipLock.try_acquire

    def delayed_acquire(selected_root: Path, attempt_id: str):
        entered.set()
        assert release.wait(timeout=5)
        return original(selected_root, attempt_id)

    monkeypatch.setattr(
        _AttemptOwnershipLock,
        "try_acquire",
        staticmethod(delayed_acquire),
    )
    ownership = CrossProcessProjectFileEffectOwnership()
    task = asyncio.create_task(
        ownership.acquire(root, "execution-1", purpose="dispatch")
    )
    assert await asyncio.to_thread(entered.wait, 5)
    task.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    reacquired = original(root, "execution-1")
    assert reacquired is not None
    reacquired.release()


@pytest.mark.asyncio
async def test_git_visible_link_recheck_fails_after_ownership_before_apply(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _repo(tmp_path)
    plan = _plan(root)
    applied = False

    def reject_links(_root: Path) -> None:
        raise RuntimeError("unsafe link")

    def forbidden_apply(*args: object, **kwargs: object) -> None:
        nonlocal applied
        applied = True

    monkeypatch.setattr(
        openjiuwen_project_file_effect_adapter,
        "_reject_git_visible_symlinks",
        reject_links,
    )
    monkeypatch.setattr(
        openjiuwen_project_file_effect_adapter,
        "_apply_attempt_patch",
        forbidden_apply,
    )
    result = await _adapter(_Handle(), _CountingOwnership()).dispatch(
        plan,
        _authorization(plan, call=True),
    )
    assert result is None
    assert applied is False
    assert (root / "sample.txt").read_text(encoding="utf-8") == "before\n"


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["dispatch", "observe"])
async def test_root_is_revalidated_after_ownership_acquisition(
    tmp_path: Path,
    operation: str,
) -> None:
    root = _repo(tmp_path)
    plan = _plan(root)
    ownership = _RenameRootOwnership()
    adapter = OpenJiuwenProjectFileEffectAdapter(
        _Handle(),
        SCOPE,
        coordinator_factory=_Coordinator,
        receipt_factory=lambda **values: _Receipt(
            status=_ReceiptStatus(values["status"]),
            receipt_id=values["receipt_id"],
            receipt_digest=values["receipt_digest"],
        ),
        observation_factory=lambda **values: _Observation(
            kind=_ObservationKind(values["kind"]),
            evidence_digest=values["evidence_digest"],
            call_quiesced=values["call_quiesced"],
        ),
        ownership=ownership,
    )

    if operation == "dispatch":
        result = await adapter.dispatch(plan, _authorization(plan, call=True))
    else:
        result = await adapter.observe(plan, _authorization(plan, call=False))

    assert result is None
    assert ownership.moved_root is not None
    assert (ownership.moved_root / "sample.txt").read_text(encoding="utf-8") == (
        "before\n"
    )


@pytest.mark.asyncio
async def test_held_attempt_lock_consumes_authority_without_file_mutation(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    plan = _plan(root)
    held = _AttemptOwnershipLock.try_acquire(root, plan.attempt_id)
    assert held is not None
    try:
        result = await _adapter(_Handle(), _CountingOwnership()).dispatch(
            plan,
            _authorization(plan, call=True),
        )
    finally:
        held.release()

    assert result is None
    assert (root / "sample.txt").read_text(encoding="utf-8") == "before\n"


@pytest.mark.asyncio
async def test_malformed_plan_and_fact_as_authority_have_zero_downstream_effects(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    plan = _plan(root)
    handle = _Handle()
    ownership = _CountingOwnership()
    adapter = _adapter(handle, ownership)

    invalid_plans = (
        replace(plan, task_id="bad\x00task"),
        replace(plan, task_id="x" * 256),
        replace(plan, generation=True),
        replace(plan, patch=b"x" * (MAX_OPENJIUWEN_PROJECT_PATCH_BYTES + 1)),
        replace(plan, target_digest="0" * 64),
    )
    for invalid in invalid_plans:
        with pytest.raises(OpenJiuwenProjectFileEffectAdapterError):
            await adapter.dispatch(invalid, _authorization(plan, call=True))

    with pytest.raises(OpenJiuwenProjectFileEffectAdapterError):
        await adapter.dispatch(
            plan,
            SimpleNamespace(
                binding=_authorization(plan, call=True).binding,
                external_call_authority=False,
            ),
        )
    wrong_scope = _authorization(plan, call=True)
    wrong_scope.binding.team_name = derive_openjiuwen_scope_binding(
        OTHER_SCOPE
    ).team_name
    with pytest.raises(OpenJiuwenProjectFileEffectAdapterError):
        await adapter.dispatch(plan, wrong_scope)

    assert handle.call_authorizations == 0
    assert ownership.acquisitions == []
    assert (root / "sample.txt").read_text(encoding="utf-8") == "before\n"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes",
    [
        {"task_id": ""},
        {"task_id": "\ud800"},
        {"execution_id": "x" * 256},
        {"effect_id": "bad\x00effect"},
        {"provider_operation_key": "x" * 256},
        {"attempt_id": "foreign-attempt"},
        {"generation": -1},
        {"generation": 2**63},
        {"operation_ordinal": True},
        {"operation_ordinal": 2**63},
        {"dispatch_ordinal": False},
        {"project_uri": "x" * 2_049},
        {"project_root": "relative-project"},
        {"project_root": "x" * 4_097},
        {"expected_tree": "content-v2:bad"},
        {"before_head": "a" * 39},
        {"before_tree": "A" * 64},
        {"protected_support": ()},
        {"protected_support": (("z", "1" * 64), ("a", "2" * 64))},
        {"protected_support": (("a", "1" * 64), ("a", "2" * 64))},
        {"scope": OTHER_SCOPE},
    ],
)
async def test_plan_bounds_fail_before_authorization_lock_or_file(
    tmp_path: Path,
    changes: dict[str, object],
) -> None:
    root = _repo(tmp_path)
    plan = _plan(root)
    handle = _Handle()
    ownership = _CountingOwnership()

    with pytest.raises(OpenJiuwenProjectFileEffectAdapterError):
        await _adapter(handle, ownership).dispatch(
            replace(plan, **changes),
            _authorization(plan, call=True),
        )

    assert handle.call_authorizations == 0
    assert ownership.acquisitions == []
    assert (root / "sample.txt").read_text(encoding="utf-8") == "before\n"


@pytest.mark.asyncio
async def test_255_character_effect_identities_are_accepted(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    plan = _plan(root)
    maximum = replace(
        plan,
        task_id="t" * 255,
        execution_id="e" * 255,
        attempt_id="e" * 255,
        effect_id="f" * 255,
        provider_operation_key="f" * 255,
    )
    receipt = await _adapter(_Handle(), _CountingOwnership()).dispatch(
        maximum,
        _authorization(maximum, call=True),
    )
    assert receipt is not None
    assert (root / "sample.txt").read_text(encoding="utf-8") == "after\n"


def test_constructor_rejects_foreign_scope_without_ownership_allocation() -> None:
    ownership = _CountingOwnership()
    with pytest.raises(OpenJiuwenProjectFileEffectAdapterError) as rejected:
        OpenJiuwenProjectFileEffectAdapter(
            _Handle(OTHER_SCOPE),
            SCOPE,
            coordinator_factory=_Coordinator,
            receipt_factory=lambda **values: values,
            observation_factory=lambda **values: values,
            ownership=ownership,
        )

    assert rejected.value.reason == "AGENTCORE_EFFECT_BINDING_MISMATCH"
    assert ownership.acquisitions == []


def test_patch_and_identifier_boundaries_are_type_exact(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    before_tree = _project_tree_fingerprint(root)
    before_content = _project_content_fingerprint(root)
    before_head = _git_head(root)
    support = tuple(sorted(_target_support_fingerprints(root).items()))
    assert derive_openjiuwen_project_intended_effect_digest(
        expected_tree="a" * 64,
        patch=b"x" * MAX_OPENJIUWEN_PROJECT_PATCH_BYTES,
        before_tree=before_tree,
        before_content=before_content,
        before_head=before_head,
        protected_support=support,
    )
    for invalid_patch in (b"", b"x" * (MAX_OPENJIUWEN_PROJECT_PATCH_BYTES + 1)):
        with pytest.raises(OpenJiuwenProjectFileEffectAdapterError):
            derive_openjiuwen_project_intended_effect_digest(
                expected_tree="a" * 64,
                patch=invalid_patch,
                before_tree=before_tree,
                before_content=before_content,
                before_head=before_head,
                protected_support=support,
            )
    for invalid_tree in (
        "bad\x00tree",
        "x" * 256,
        "\ud800",
        "tree",
        f"content-v2:{'a' * 64}:bad",
    ):
        with pytest.raises(OpenJiuwenProjectFileEffectAdapterError):
            derive_openjiuwen_project_intended_effect_digest(
                expected_tree=invalid_tree,
                patch=b"patch",
                before_tree=before_tree,
                before_content=before_content,
                before_head=before_head,
                protected_support=support,
            )

    first = derive_openjiuwen_project_target_digest(
        SCOPE,
        project_source="x" * 255,
        project_stable_id="project-1",
        project_uri="project://project-1",
        project_root=str(root),
    )
    assert len(first) == 64
    assert derive_openjiuwen_project_target_digest(
        SCOPE,
        project_source="source",
        project_stable_id="project-1",
        project_uri="u" * 2_048,
        project_root=str(root),
    )
    with pytest.raises(OpenJiuwenProjectFileEffectAdapterError):
        derive_openjiuwen_project_target_digest(
            SCOPE,
            project_source="source",
            project_stable_id="project-1",
            project_uri="u" * 2_049,
            project_root=str(root),
        )


@pytest.mark.asyncio
async def test_cancellation_propagates_and_does_not_acquire_project_lock(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    plan = _plan(root)
    handle = _Handle()
    ownership = _CountingOwnership()

    class _CancelledCoordinator(_Coordinator):
        async def dispatch(self, authorization: object) -> object:
            raise asyncio.CancelledError

    adapter = OpenJiuwenProjectFileEffectAdapter(
        handle,
        SCOPE,
        coordinator_factory=_CancelledCoordinator,
        receipt_factory=lambda **values: values,
        observation_factory=lambda **values: values,
        ownership=ownership,
    )

    with pytest.raises(asyncio.CancelledError):
        await adapter.dispatch(plan, _authorization(plan, call=True))
    assert ownership.acquisitions == []
    assert (root / "sample.txt").read_text(encoding="utf-8") == "before\n"
