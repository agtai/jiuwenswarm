# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import Assurance, ScopeRef
from jiuwenswarm.server.live_voice.durability_checkpoint import D1Checkpoint
from jiuwenswarm.server.live_voice.durability_identity import (
    DurabilityProfileBinding,
)
from jiuwenswarm.server.live_voice.openjiuwen_d1_checkpoint_adapter import (
    MAX_OPENJIUWEN_D1_PUBLICATION_BYTES,
    OPENJIUWEN_D1_CODEC_ID,
    OPENJIUWEN_D1_CODEC_VERSION,
    ImmutableFileExecutionCheckpointPayloadStore,
    OpenJiuwenCheckpointPayloadStoreError,
    OpenJiuwenD1CheckpointAdapter,
    OpenJiuwenD1CheckpointAdapterError,
    OpenJiuwenD1CheckpointProducer,
    OpenJiuwenD1CheckpointReadBinding,
    derive_openjiuwen_outer_checkpoint_id,
)
from jiuwenswarm.server.live_voice.openjiuwen_task_facade import (
    derive_openjiuwen_scope_binding,
)

SCOPE = ScopeRef("principal-1", "project-1", "session-1", Assurance.AUTHENTICATED)
OTHER_SCOPE = ScopeRef(
    "principal-2",
    "project-2",
    "session-2",
    Assurance.AUTHENTICATED,
)


@dataclass(frozen=True, slots=True)
class _Receipt:
    checkpoint_id: str
    payload_locator: str
    payload_digest: str
    payload_size: int


@dataclass(frozen=True, slots=True)
class _Binding:
    session_id: str
    team_name: str
    member_name: str


@dataclass(frozen=True, slots=True)
class _Record:
    team_name: str
    task_id: str
    execution_id: str
    checkpoint_id: str
    checkpoint_sequence: int
    profile_digest: str
    generation: int
    producer_owner_id: str
    producer_owner_epoch: int
    publication_execution_version: int
    codec_id: str
    codec_version: int
    state_schema_id: str
    state_schema_version: int
    complete: bool
    payload_locator: str
    payload_digest: str
    payload_size: int
    reference_digest: str
    source_event_id: str
    source_sequence: int
    created_at: int


@dataclass(frozen=True, slots=True)
class _Snapshot:
    record: _Record
    current_execution_version: int
    current_execution_disposition: str
    checkpoint_head: int


@dataclass(frozen=True, slots=True)
class _Result:
    ok: bool
    reason: str = ""
    record: _Record | None = None
    changed: bool = False
    replayed: bool = False


@dataclass(frozen=True, slots=True)
class _Loaded:
    snapshot: _Snapshot
    payload: bytes


class _Handle:
    executor_authority = False

    def __init__(self, *, scope: ScopeRef = SCOPE) -> None:
        source = derive_openjiuwen_scope_binding(scope)
        self.binding = _Binding(source.session_id, source.team_name, source.member_name)
        self.snapshots: list[object | None] = []
        self.read_calls: list[tuple[object, ...]] = []

    async def publish_execution_checkpoint(
        self, *args: object, **kwargs: object
    ) -> object:
        raise AssertionError("the coordinator owns publication")

    async def read_current_execution_checkpoint(
        self,
        task_id: str,
        execution_id: str,
        expected_execution_version: int,
        *,
        profile_digest: str,
        generation: int,
    ) -> object | None:
        self.read_calls.append(
            (
                task_id,
                execution_id,
                expected_execution_version,
                profile_digest,
                generation,
            )
        )
        if not self.snapshots:
            return None
        if len(self.snapshots) == 1:
            return self.snapshots[0]
        return self.snapshots.pop(0)


class _Coordinator:
    def __init__(self, handle: _Handle, _store: object) -> None:
        self.handle = handle
        self.publish_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
        self.publish_result: object | None = None
        self.loaded: object | None = None
        self.publish_gate: asyncio.Event | None = None

    async def publish(self, *args: object, **kwargs: object) -> object:
        self.publish_calls.append((args, kwargs))
        if self.publish_gate is not None:
            await self.publish_gate.wait()
        if self.publish_result is not None:
            return self.publish_result
        task_id, execution_id, checkpoint_id, payload = args
        record = _Record(
            team_name=self.handle.binding.team_name,
            task_id=str(task_id),
            execution_id=str(execution_id),
            checkpoint_id=str(checkpoint_id),
            checkpoint_sequence=int(kwargs["checkpoint_sequence"]),
            profile_digest=str(kwargs["profile_digest"]),
            generation=int(kwargs["generation"]),
            producer_owner_id=str(kwargs["owner_id"]),
            producer_owner_epoch=int(kwargs["owner_epoch"]),
            publication_execution_version=int(kwargs["expected_execution_version"]),
            codec_id=str(kwargs["codec_id"]),
            codec_version=int(kwargs["codec_version"]),
            state_schema_id=str(kwargs["state_schema_id"]),
            state_schema_version=int(kwargs["state_schema_version"]),
            complete=bool(kwargs["complete"]),
            payload_locator="livevoice-checkpoints/v1/aa/payload.payload",
            payload_digest=hashlib.sha256(bytes(payload)).hexdigest(),
            payload_size=len(bytes(payload)),
            reference_digest="a" * 64,
            source_event_id="event-checkpoint-1",
            source_sequence=9,
            created_at=1,
        )
        return _Result(ok=True, record=record, changed=True)

    async def load_current(self, *args: object, **kwargs: object) -> object | None:
        return self.loaded


def _profile(*, durability_level: str = "D1") -> DurabilityProfileBinding:
    return DurabilityProfileBinding(
        executor_id="jiuwenswarm_code_agent.project_code",
        adapter_id="direct-project-code-executor",
        profile_id="direct-profile",
        profile_version="profile.v1",
        profile_digest="1" * 64,
        durability_level=durability_level,
        durability_capability_version="d1.v1",
    )


def _checkpoint(
    *,
    scope: ScopeRef = SCOPE,
    task_id: str = "task-1",
    execution_id: str = "execution-1",
    native_sequence: int = 0,
    generation: int = 0,
    profile: DurabilityProfileBinding | None = None,
    state_bytes: bytes = b"durable-state",
) -> D1Checkpoint:
    return D1Checkpoint.create(
        checkpoint_id="native-checkpoint-1",
        scope=scope,
        task_id=task_id,
        producer_attempt_id=execution_id,
        checkpoint_sequence=native_sequence,
        recovery_generation=generation,
        profile=profile or _profile(),
        complete=True,
        task_spec_digest="4" * 64,
        context_version="context.v1",
        context_digest="2" * 64,
        input_digest="3" * 64,
        state_schema_id="agent-state",
        state_schema_version=4,
        state_bytes=state_bytes,
        effect_head=7,
        effect_prefix_digest="5" * 64,
    )


def _producer(**changes: object) -> OpenJiuwenD1CheckpointProducer:
    values: dict[str, object] = {
        "task_id": "task-1",
        "execution_id": "execution-1",
        "profile_digest": "1" * 64,
        "generation": 0,
        "owner_id": "runtime-owner-1",
        "owner_epoch": 2,
        "execution_version": 3,
        "expected_checkpoint_head": 0,
    }
    values.update(changes)
    return OpenJiuwenD1CheckpointProducer(**values)  # type: ignore[arg-type]


def _read_binding(**changes: object) -> OpenJiuwenD1CheckpointReadBinding:
    values: dict[str, object] = {
        "task_id": "task-1",
        "execution_id": "execution-1",
        "profile_digest": "1" * 64,
        "generation": 0,
        "execution_version": 3,
    }
    values.update(changes)
    return OpenJiuwenD1CheckpointReadBinding(**values)  # type: ignore[arg-type]


def _store(tmp_path: Path) -> ImmutableFileExecutionCheckpointPayloadStore:
    return ImmutableFileExecutionCheckpointPayloadStore(
        tmp_path / "agentcore-checkpoints",
        receipt_factory=_Receipt,
    )


def _adapter(
    tmp_path: Path,
    *,
    handle: _Handle | None = None,
) -> tuple[OpenJiuwenD1CheckpointAdapter, _Handle, _Coordinator]:
    selected_handle = handle or _Handle()
    coordinator: _Coordinator | None = None

    def factory(authority: _Handle, store: object) -> _Coordinator:
        nonlocal coordinator
        coordinator = _Coordinator(authority, store)
        return coordinator

    adapter = OpenJiuwenD1CheckpointAdapter(
        selected_handle,
        SCOPE,
        payload_store=_store(tmp_path),
        coordinator_factory=factory,
    )
    assert coordinator is not None
    return adapter, selected_handle, coordinator


def _record(
    *,
    checkpoint: D1Checkpoint | None = None,
    binding: OpenJiuwenD1CheckpointReadBinding | None = None,
    checkpoint_sequence: int = 1,
) -> tuple[_Record, bytes]:
    selected = checkpoint or _checkpoint()
    selected_binding = binding or _read_binding()
    payload = selected.canonical_bytes()
    scope_binding = derive_openjiuwen_scope_binding(SCOPE)
    outer_id = derive_openjiuwen_outer_checkpoint_id(
        scope_binding,
        task_id=selected_binding.task_id,
        execution_id=selected_binding.execution_id,
        native_checkpoint_id=selected.checkpoint_id,
    )
    return (
        _Record(
            team_name=scope_binding.team_name,
            task_id=selected_binding.task_id,
            execution_id=selected_binding.execution_id,
            checkpoint_id=outer_id,
            checkpoint_sequence=checkpoint_sequence,
            profile_digest=selected_binding.profile_digest,
            generation=selected_binding.generation,
            producer_owner_id="runtime-owner-1",
            producer_owner_epoch=2,
            publication_execution_version=3,
            codec_id=OPENJIUWEN_D1_CODEC_ID,
            codec_version=OPENJIUWEN_D1_CODEC_VERSION,
            state_schema_id=selected.state_schema_id,
            state_schema_version=selected.state_schema_version,
            complete=True,
            payload_locator="livevoice-checkpoints/v1/aa/payload.payload",
            payload_digest=hashlib.sha256(payload).hexdigest(),
            payload_size=len(payload),
            reference_digest="a" * 64,
            source_event_id="event-checkpoint-1",
            source_sequence=9,
            created_at=1,
        ),
        payload,
    )


def test_default_off_import_and_store_construction_do_not_allocate(
    tmp_path: Path,
) -> None:
    root = tmp_path / "not-created"

    store = ImmutableFileExecutionCheckpointPayloadStore(
        root,
        receipt_factory=_Receipt,
    )

    assert store.root == root.resolve()
    assert not root.exists()


def test_adapter_normalizes_unauthenticated_scope_before_coordinator(
    tmp_path: Path,
) -> None:
    request_asserted = ScopeRef(
        "principal-1",
        "project-1",
        "session-1",
        Assurance.REQUEST_ASSERTED,
    )
    coordinator_calls: list[object] = []

    def coordinator_factory(*args: object) -> None:
        coordinator_calls.append(args)

    with pytest.raises(OpenJiuwenD1CheckpointAdapterError) as rejected:
        OpenJiuwenD1CheckpointAdapter(
            _Handle(),
            request_asserted,
            payload_store=_store(tmp_path),
            coordinator_factory=coordinator_factory,  # type: ignore[arg-type]
        )

    assert rejected.value.reason == "INVALID_PRODUCT_SCOPE"
    assert coordinator_calls == []
    assert not (tmp_path / "agentcore-checkpoints").exists()


@pytest.mark.asyncio
async def test_file_store_is_exact_idempotent_and_survives_reopen(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    payload = b"canonical-payload"

    first = await store.put("checkpoint-1", payload)
    second = await store.put("checkpoint-1", payload)
    reopened = _store(tmp_path)

    assert first == second
    assert await reopened.get(first) == payload
    assert first.payload_digest == hashlib.sha256(payload).hexdigest()
    with pytest.raises(OpenJiuwenCheckpointPayloadStoreError) as conflict:
        await reopened.put("checkpoint-1", b"changed-payload")
    assert conflict.value.reason == "CHECKPOINT_ID_CONFLICT"


@pytest.mark.asyncio
async def test_file_store_concurrency_linearizes_same_and_changed_bytes(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)

    for index in range(20):
        same = await asyncio.gather(
            store.put(f"same-id-{index}", b"same"),
            store.put(f"same-id-{index}", b"same"),
        )
        changed = await asyncio.gather(
            store.put(f"changed-id-{index}", b"left"),
            store.put(f"changed-id-{index}", b"right"),
            return_exceptions=True,
        )

        assert same[0] == same[1]
        assert sum(not isinstance(item, BaseException) for item in changed) == 1
        failures = [item for item in changed if isinstance(item, BaseException)]
        assert len(failures) == 1
        assert isinstance(failures[0], OpenJiuwenCheckpointPayloadStoreError)
        assert failures[0].reason == "CHECKPOINT_ID_CONFLICT"


@pytest.mark.asyncio
async def test_file_store_rejects_bounds_locator_and_corruption(tmp_path: Path) -> None:
    store = _store(tmp_path)

    maximum = await store.put(
        "x" * 255,
        b"x" * MAX_OPENJIUWEN_D1_PUBLICATION_BYTES,
    )
    assert len(await store.get(maximum)) == MAX_OPENJIUWEN_D1_PUBLICATION_BYTES

    with pytest.raises(OpenJiuwenCheckpointPayloadStoreError):
        await store.put("checkpoint-empty", b"")
    with pytest.raises(OpenJiuwenCheckpointPayloadStoreError):
        await store.put(
            "checkpoint-large",
            b"x" * (MAX_OPENJIUWEN_D1_PUBLICATION_BYTES + 1),
        )
    for invalid_id in ("x" * 256, "bad\x00id", "\ud800"):
        with pytest.raises(OpenJiuwenCheckpointPayloadStoreError):
            await store.put(invalid_id, b"payload")

    receipt = await store.put("checkpoint-corrupt", b"truth")
    wrong_locator = replace(receipt, payload_locator="foreign/object")
    with pytest.raises(OpenJiuwenCheckpointPayloadStoreError) as locator:
        await store.get(wrong_locator)
    assert locator.value.reason == "PAYLOAD_LOCATOR_MISMATCH"

    key = hashlib.sha256(receipt.checkpoint_id.encode()).hexdigest()
    target = store.root / "v1" / key[:2] / f"{key}.payload"
    target.write_bytes(b"lies")
    with pytest.raises(OpenJiuwenCheckpointPayloadStoreError) as corrupt:
        await store.get(receipt)
    assert corrupt.value.reason == "PAYLOAD_RECEIPT_MISMATCH"


def test_outer_checkpoint_identity_is_stable_payload_independent_and_scope_safe() -> (
    None
):
    binding = derive_openjiuwen_scope_binding(SCOPE)
    other = derive_openjiuwen_scope_binding(OTHER_SCOPE)

    first = derive_openjiuwen_outer_checkpoint_id(
        binding,
        task_id="task-1",
        execution_id="execution-1",
        native_checkpoint_id="native-1",
    )

    assert first == derive_openjiuwen_outer_checkpoint_id(
        binding,
        task_id="task-1",
        execution_id="execution-1",
        native_checkpoint_id="native-1",
    )
    assert first != derive_openjiuwen_outer_checkpoint_id(
        other,
        task_id="task-1",
        execution_id="execution-1",
        native_checkpoint_id="native-1",
    )
    assert first != derive_openjiuwen_outer_checkpoint_id(
        binding,
        task_id="task-1",
        execution_id="execution-2",
        native_checkpoint_id="native-1",
    )
    assert first.startswith("lv-oj-d1-") and len(first) <= 255


@pytest.mark.asyncio
async def test_publish_keeps_native_and_outer_sequences_independent(
    tmp_path: Path,
) -> None:
    adapter, _handle, coordinator = _adapter(tmp_path)
    checkpoint = _checkpoint(native_sequence=0)

    decision = await adapter.publish(checkpoint, _producer())

    assert decision.ok is True and decision.reason == ""
    assert decision.publication is not None
    assert decision.publication.native_checkpoint_sequence == 0
    assert decision.publication.outer_checkpoint_sequence == 1
    args, kwargs = coordinator.publish_calls[0]
    assert args[3] == checkpoint.canonical_bytes()
    assert kwargs["checkpoint_sequence"] == 1
    assert kwargs["expected_checkpoint_head"] == 0
    assert kwargs["codec_id"] == OPENJIUWEN_D1_CODEC_ID
    assert kwargs["codec_version"] == OPENJIUWEN_D1_CODEC_VERSION
    assert kwargs["state_schema_id"] == checkpoint.state_schema_id
    assert decision.publication.executor_authority is False


@pytest.mark.asyncio
async def test_publish_preserves_exact_retry_facts_and_projects_replay(
    tmp_path: Path,
) -> None:
    adapter, handle, coordinator = _adapter(tmp_path)
    checkpoint = _checkpoint(native_sequence=7)
    producer = _producer(expected_checkpoint_head=4)
    scope_binding = derive_openjiuwen_scope_binding(SCOPE)
    outer_id = derive_openjiuwen_outer_checkpoint_id(
        scope_binding,
        task_id=producer.task_id,
        execution_id=producer.execution_id,
        native_checkpoint_id=checkpoint.checkpoint_id,
    )
    payload = checkpoint.canonical_bytes()
    coordinator.publish_result = _Result(
        ok=True,
        record=_Record(
            team_name=handle.binding.team_name,
            task_id=producer.task_id,
            execution_id=producer.execution_id,
            checkpoint_id=outer_id,
            checkpoint_sequence=5,
            profile_digest=producer.profile_digest,
            generation=producer.generation,
            producer_owner_id=producer.owner_id,
            producer_owner_epoch=producer.owner_epoch,
            publication_execution_version=producer.execution_version,
            codec_id=OPENJIUWEN_D1_CODEC_ID,
            codec_version=OPENJIUWEN_D1_CODEC_VERSION,
            state_schema_id=checkpoint.state_schema_id,
            state_schema_version=checkpoint.state_schema_version,
            complete=True,
            payload_locator="livevoice-checkpoints/v1/aa/payload.payload",
            payload_digest=hashlib.sha256(payload).hexdigest(),
            payload_size=len(payload),
            reference_digest="a" * 64,
            source_event_id="event-checkpoint-1",
            source_sequence=9,
            created_at=1,
        ),
        replayed=True,
    )

    decision = await adapter.publish(checkpoint, producer)

    assert decision.ok is True
    assert decision.publication is not None
    assert decision.publication.changed is False
    assert decision.publication.replayed is True
    assert decision.publication.outer_checkpoint_id == outer_id
    assert decision.publication.outer_checkpoint_sequence == 5


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("checkpoint", "producer"),
    [
        (_checkpoint(scope=OTHER_SCOPE), _producer()),
        (_checkpoint(task_id="task-2"), _producer()),
        (_checkpoint(execution_id="execution-2"), _producer()),
        (_checkpoint(profile=_profile(durability_level="D2")), _producer()),
        (_checkpoint(generation=1), _producer()),
        (_checkpoint(), _producer(profile_digest="2" * 64)),
    ],
)
async def test_publish_rejects_embedded_binding_drift_before_store(
    tmp_path: Path,
    checkpoint: D1Checkpoint,
    producer: OpenJiuwenD1CheckpointProducer,
) -> None:
    adapter, _handle, coordinator = _adapter(tmp_path)

    with pytest.raises(OpenJiuwenD1CheckpointAdapterError) as rejected:
        await adapter.publish(checkpoint, producer)

    assert rejected.value.reason == "D1_CHECKPOINT_BINDING_MISMATCH"
    assert coordinator.publish_calls == []
    assert not (tmp_path / "agentcore-checkpoints").exists()


@pytest.mark.asyncio
async def test_publish_rejects_wire_over_agentcore_limit_before_store(
    tmp_path: Path,
) -> None:
    adapter, _handle, coordinator = _adapter(tmp_path)
    checkpoint = _checkpoint(state_bytes=b"x" * 800_000)
    assert len(checkpoint.canonical_bytes()) > MAX_OPENJIUWEN_D1_PUBLICATION_BYTES

    with pytest.raises(OpenJiuwenD1CheckpointAdapterError) as rejected:
        await adapter.publish(checkpoint, _producer())

    assert rejected.value.reason == "D1_CHECKPOINT_WIRE_EXCEEDS_AGENTCORE_LIMIT"
    assert coordinator.publish_calls == []
    assert not (tmp_path / "agentcore-checkpoints").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "producer",
    [
        _producer(task_id="bad\x00task"),
        _producer(execution_id="x" * 256),
        _producer(generation=-1),
        _producer(owner_epoch=True),
        _producer(execution_version=(1 << 63)),
        _producer(expected_checkpoint_head=True),
        _producer(expected_checkpoint_head=(1 << 63) - 1),
    ],
)
async def test_publish_rejects_malformed_fence_before_coordinator_or_store(
    tmp_path: Path,
    producer: OpenJiuwenD1CheckpointProducer,
) -> None:
    adapter, _handle, coordinator = _adapter(tmp_path)

    with pytest.raises(OpenJiuwenD1CheckpointAdapterError):
        await adapter.publish(_checkpoint(), producer)

    assert coordinator.publish_calls == []
    assert not (tmp_path / "agentcore-checkpoints").exists()


@pytest.mark.asyncio
async def test_publish_returns_redacted_rejection_and_rejects_malformed_success(
    tmp_path: Path,
) -> None:
    adapter, _handle, coordinator = _adapter(tmp_path)
    coordinator.publish_result = _Result(ok=False, reason="stale owner")

    rejected = await adapter.publish(_checkpoint(), _producer())

    assert rejected.ok is False
    assert rejected.reason == "AGENTCORE_CHECKPOINT_REJECTED"
    assert rejected.publication is None

    coordinator.publish_result = _Result(ok=True, record=None, changed=True)
    with pytest.raises(OpenJiuwenD1CheckpointAdapterError) as malformed:
        await adapter.publish(_checkpoint(), _producer())
    assert malformed.value.reason == "INVALID_CHECKPOINT_PUBLICATION_RESULT"


@pytest.mark.asyncio
async def test_load_current_roundtrips_and_verifies_embedded_facts(
    tmp_path: Path,
) -> None:
    adapter, handle, coordinator = _adapter(tmp_path)
    record, payload = _record()
    snapshot = _Snapshot(
        record=record,
        current_execution_version=3,
        current_execution_disposition="owned",
        checkpoint_head=1,
    )
    handle.snapshots = [snapshot]
    coordinator.loaded = _Loaded(snapshot=snapshot, payload=payload)

    loaded = await adapter.load_current(_read_binding())

    assert loaded is not None
    assert loaded.checkpoint == _checkpoint()
    assert loaded.outer_checkpoint_sequence == 1
    assert loaded.current_execution_disposition == "owned"
    assert loaded.resume_authority is False
    assert loaded.executor_authority is False
    assert len(handle.read_calls) == 2


@pytest.mark.asyncio
async def test_load_current_distinguishes_absence_from_missing_payload(
    tmp_path: Path,
) -> None:
    adapter, handle, coordinator = _adapter(tmp_path)
    handle.snapshots = [None]
    coordinator.loaded = None
    assert await adapter.load_current(_read_binding()) is None

    record, _payload = _record()
    snapshot = _Snapshot(record, 3, "recoverable", 1)
    handle.snapshots = [snapshot]
    coordinator.loaded = None
    with pytest.raises(OpenJiuwenD1CheckpointAdapterError) as unavailable:
        await adapter.load_current(_read_binding())
    assert unavailable.value.reason == "CHECKPOINT_PAYLOAD_UNAVAILABLE_OR_CORRUPT"


@pytest.mark.asyncio
async def test_load_current_rejects_corrupt_or_cross_bound_payload(
    tmp_path: Path,
) -> None:
    adapter, handle, coordinator = _adapter(tmp_path)
    record, payload = _record()
    snapshot = _Snapshot(record, 3, "owned", 1)
    handle.snapshots = [snapshot]
    coordinator.loaded = _Loaded(snapshot, payload[:-1] + b"x")

    with pytest.raises(OpenJiuwenD1CheckpointAdapterError) as corrupt:
        await adapter.load_current(_read_binding())
    assert corrupt.value.reason == "INVALID_LOADED_D1_CHECKPOINT"

    other_payload = _checkpoint(task_id="task-2").canonical_bytes()
    handle.snapshots = [snapshot]
    coordinator.loaded = _Loaded(snapshot, other_payload)
    with pytest.raises(OpenJiuwenD1CheckpointAdapterError) as cross_bound:
        await adapter.load_current(_read_binding())
    assert cross_bound.value.reason == "D1_CHECKPOINT_BINDING_MISMATCH"


@pytest.mark.asyncio
async def test_load_current_rejects_perpetual_snapshot_churn(tmp_path: Path) -> None:
    adapter, handle, coordinator = _adapter(tmp_path)
    record, payload = _record()
    first = _Snapshot(record, 3, "owned", 1)
    second_record = replace(record, checkpoint_sequence=2)
    second = _Snapshot(second_record, 3, "owned", 2)
    handle.snapshots = [first, second, first, second, first, second]
    coordinator.loaded = _Loaded(first, payload)

    with pytest.raises(OpenJiuwenD1CheckpointAdapterError) as changed:
        await adapter.load_current(_read_binding())
    assert changed.value.reason == "CHECKPOINT_SNAPSHOT_CHANGED"


@pytest.mark.asyncio
async def test_binding_drift_and_cancellation_fail_before_success(
    tmp_path: Path,
) -> None:
    adapter, handle, coordinator = _adapter(tmp_path)
    handle.binding = replace(handle.binding, team_name="foreign-team")
    with pytest.raises(OpenJiuwenD1CheckpointAdapterError) as drift:
        await adapter.publish(_checkpoint(), _producer())
    assert drift.value.reason == "AGENTCORE_BINDING_MISMATCH"
    assert coordinator.publish_calls == []

    adapter, _handle, coordinator = _adapter(tmp_path / "cancel")
    coordinator.publish_gate = asyncio.Event()
    task = asyncio.create_task(adapter.publish(_checkpoint(), _producer()))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


def test_public_module_exports_remain_repository_locked() -> None:
    from jiuwenswarm.server.live_voice import openjiuwen_d1_checkpoint_adapter as module

    assert set(module.__all__) == {
        "AgentCoreCheckpointAuthorityPort",
        "AgentCoreCheckpointCoordinatorFactory",
        "AgentCoreCheckpointCoordinatorPort",
        "AgentCoreCheckpointReceiptFactory",
        "ImmutableFileExecutionCheckpointPayloadStore",
        "MAX_OPENJIUWEN_D1_PUBLICATION_BYTES",
        "OPENJIUWEN_D1_CODEC_ID",
        "OPENJIUWEN_D1_CODEC_VERSION",
        "OpenJiuwenCheckpointPayloadStoreError",
        "OpenJiuwenD1CheckpointAdapter",
        "OpenJiuwenD1CheckpointAdapterError",
        "OpenJiuwenD1CheckpointProducer",
        "OpenJiuwenD1CheckpointPublication",
        "OpenJiuwenD1CheckpointPublishDecision",
        "OpenJiuwenD1CheckpointReadBinding",
        "OpenJiuwenD1LoadedCheckpoint",
        "derive_openjiuwen_outer_checkpoint_id",
    }
