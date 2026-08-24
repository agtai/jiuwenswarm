# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Default-off LiveVoice D1 adapter over public AgentCore checkpoint seams.

The module deliberately has no import-time AgentCore dependency.  A product
composition must explicitly inject the root-public coordinator/receipt types;
the existing production registry does not do so.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from jiuwenswarm.common.schema.live_voice_contract_v2 import ScopeRef

from .durability_checkpoint import D1Checkpoint, DurabilityCheckpointViolation
from .openjiuwen_task_facade import (
    OpenJiuwenScopeBinding,
    derive_openjiuwen_scope_binding,
)

MAX_OPENJIUWEN_D1_PUBLICATION_BYTES = 1_048_576
OPENJIUWEN_D1_CODEC_ID = "livevoice.d1.checkpoint"
OPENJIUWEN_D1_CODEC_VERSION = 1

_MAX_ID_LENGTH = 255
_MAX_LOCATOR_LENGTH = 2_048
_MAX_TEXT_LENGTH = 65_535
_MAX_SIGNED_BIGINT = (1 << 63) - 1
_MAX_SNAPSHOT_ATTEMPTS = 3
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class OpenJiuwenD1CheckpointAdapterError(RuntimeError):
    """Stable fail-closed adapter error without downstream exception text."""

    def __init__(self, reason: str) -> None:
        super().__init__("OpenJiuwen D1 checkpoint adapter is unavailable")
        self.reason = reason


class OpenJiuwenCheckpointPayloadStoreError(RuntimeError):
    """Stable immutable-store failure without local path disclosure."""

    def __init__(self, reason: str) -> None:
        super().__init__("OpenJiuwen checkpoint payload store rejected the operation")
        self.reason = reason


class AgentCoreCheckpointAuthorityBindingPort(Protocol):
    session_id: str
    team_name: str
    member_name: str


class AgentCoreCheckpointAuthorityPort(Protocol):
    binding: AgentCoreCheckpointAuthorityBindingPort
    executor_authority: bool

    async def publish_execution_checkpoint(
        self, *args: object, **kwargs: object
    ) -> object: ...

    async def read_current_execution_checkpoint(
        self,
        task_id: str,
        execution_id: str,
        expected_execution_version: int,
        *,
        profile_digest: str,
        generation: int,
    ) -> object | None: ...


class AgentCoreCheckpointCoordinatorPort(Protocol):
    async def publish(self, *args: object, **kwargs: object) -> object: ...

    async def load_current(
        self,
        task_id: str,
        execution_id: str,
        expected_execution_version: int,
        *,
        profile_digest: str,
        generation: int,
    ) -> object | None: ...


class AgentCoreCheckpointReceiptFactory(Protocol):
    def __call__(
        self,
        *,
        checkpoint_id: str,
        payload_locator: str,
        payload_digest: str,
        payload_size: int,
    ) -> object: ...


class AgentCoreCheckpointCoordinatorFactory(Protocol):
    def __call__(
        self,
        authority: AgentCoreCheckpointAuthorityPort,
        payload_store: object,
    ) -> AgentCoreCheckpointCoordinatorPort: ...


@dataclass(frozen=True, slots=True)
class OpenJiuwenD1CheckpointProducer:
    """Exact producer token and outer-head fence captured before publication."""

    task_id: str
    execution_id: str
    profile_digest: str
    generation: int
    owner_id: str
    owner_epoch: int
    execution_version: int
    expected_checkpoint_head: int

    @property
    def executor_authority(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class OpenJiuwenD1CheckpointReadBinding:
    """Exact current execution binding used for an authority-free read."""

    task_id: str
    execution_id: str
    profile_digest: str
    generation: int
    execution_version: int

    @property
    def executor_authority(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class OpenJiuwenD1CheckpointPublication:
    task_id: str
    execution_id: str
    outer_checkpoint_id: str
    outer_checkpoint_sequence: int
    native_checkpoint_id: str
    native_checkpoint_sequence: int
    publication_execution_version: int
    payload_locator: str
    payload_digest: str
    payload_size: int
    reference_digest: str
    source_event_id: str
    source_sequence: int
    changed: bool
    replayed: bool

    @property
    def executor_authority(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class OpenJiuwenD1CheckpointPublishDecision:
    ok: bool
    reason: str
    publication: OpenJiuwenD1CheckpointPublication | None

    @property
    def executor_authority(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class OpenJiuwenD1LoadedCheckpoint:
    checkpoint: D1Checkpoint
    outer_checkpoint_id: str
    outer_checkpoint_sequence: int
    publication_execution_version: int
    current_execution_version: int
    current_execution_disposition: str
    payload_locator: str
    payload_digest: str
    payload_size: int
    reference_digest: str

    @property
    def resume_authority(self) -> bool:
        return False

    @property
    def executor_authority(self) -> bool:
        return False


def _adapter_error(reason: str) -> OpenJiuwenD1CheckpointAdapterError:
    return OpenJiuwenD1CheckpointAdapterError(reason)


def _text(
    value: object,
    field_name: str,
    *,
    maximum: int = _MAX_ID_LENGTH,
    allow_empty: bool = False,
) -> str:
    if type(value) is not str or "\x00" in value:
        raise _adapter_error(f"INVALID_{field_name.upper()}")
    if not allow_empty and not value.strip():
        raise _adapter_error(f"INVALID_{field_name.upper()}")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise _adapter_error(f"INVALID_{field_name.upper()}") from None
    if len(value) > maximum:
        raise _adapter_error(f"INVALID_{field_name.upper()}")
    return value


def _integer(value: object, field_name: str, *, positive: bool = False) -> int:
    lower = 1 if positive else 0
    if type(value) is not int or not lower <= value <= _MAX_SIGNED_BIGINT:
        raise _adapter_error(f"INVALID_{field_name.upper()}")
    return value


def _boolean(value: object, field_name: str) -> bool:
    if type(value) is not bool:
        raise _adapter_error(f"INVALID_{field_name.upper()}")
    return value


def _sha256(value: object, field_name: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise _adapter_error(f"INVALID_{field_name.upper()}")
    return value


def _enum_text(value: object, field_name: str) -> str:
    return _text(getattr(value, "value", value), field_name)


def derive_openjiuwen_outer_checkpoint_id(
    binding: OpenJiuwenScopeBinding,
    *,
    task_id: str,
    execution_id: str,
    native_checkpoint_id: str,
) -> str:
    """Derive a stable global store key without binding it to mutable bytes."""

    if type(binding) is not OpenJiuwenScopeBinding:
        raise _adapter_error("INVALID_OPENJIUWEN_BINDING")
    task_id = _text(task_id, "task_id")
    execution_id = _text(execution_id, "execution_id")
    native_checkpoint_id = _text(
        native_checkpoint_id,
        "native_checkpoint_id",
        maximum=_MAX_TEXT_LENGTH,
    )
    payload = json.dumps(
        {
            "execution_id": execution_id,
            "native_checkpoint_id": native_checkpoint_id,
            "session_id": _text(binding.session_id, "binding_session_id"),
            "task_id": task_id,
            "team_name": _text(binding.team_name, "binding_team_name"),
        },
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hashlib.sha256(
        b"livevoice.openjiuwen.d1.outer-id.v1\x00" + payload
    ).hexdigest()
    return f"lv-oj-d1-{digest}"


class ImmutableFileExecutionCheckpointPayloadStore:
    """Exact-idempotent local payload store with stable opaque locators."""

    __slots__ = ("_receipt_factory", "_root")

    def __init__(
        self,
        root: str | os.PathLike[str],
        *,
        receipt_factory: AgentCoreCheckpointReceiptFactory,
    ) -> None:
        if not callable(receipt_factory):
            raise OpenJiuwenCheckpointPayloadStoreError("INVALID_RECEIPT_FACTORY")
        try:
            raw_root = os.fspath(root)
        except TypeError:
            raise OpenJiuwenCheckpointPayloadStoreError(
                "INVALID_PAYLOAD_ROOT"
            ) from None
        if type(raw_root) is not str or not raw_root or "\x00" in raw_root:
            raise OpenJiuwenCheckpointPayloadStoreError("INVALID_PAYLOAD_ROOT")
        candidate = Path(raw_root)
        if not candidate.is_absolute():
            raise OpenJiuwenCheckpointPayloadStoreError("PAYLOAD_ROOT_MUST_BE_ABSOLUTE")
        try:
            self._root = candidate.resolve(strict=False)
        except OSError:
            raise OpenJiuwenCheckpointPayloadStoreError(
                "INVALID_PAYLOAD_ROOT"
            ) from None
        self._receipt_factory = receipt_factory

    @property
    def root(self) -> Path:
        return self._root

    @staticmethod
    def _checkpoint_id(value: object) -> str:
        if (
            type(value) is not str
            or not value.strip()
            or "\x00" in value
            or len(value) > _MAX_ID_LENGTH
        ):
            raise OpenJiuwenCheckpointPayloadStoreError("INVALID_CHECKPOINT_ID")
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            raise OpenJiuwenCheckpointPayloadStoreError(
                "INVALID_CHECKPOINT_ID"
            ) from None
        return value

    @staticmethod
    def _payload(value: object) -> bytes:
        if (
            type(value) is not bytes
            or not value
            or len(value) > MAX_OPENJIUWEN_D1_PUBLICATION_BYTES
        ):
            raise OpenJiuwenCheckpointPayloadStoreError("INVALID_CHECKPOINT_PAYLOAD")
        return value

    def _location(self, checkpoint_id: str) -> tuple[Path, str]:
        key = hashlib.sha256(checkpoint_id.encode("utf-8")).hexdigest()
        locator = f"livevoice-checkpoints/v1/{key[:2]}/{key}.payload"
        target = self._root / "v1" / key[:2] / f"{key}.payload"
        try:
            target.relative_to(self._root)
        except ValueError:
            raise OpenJiuwenCheckpointPayloadStoreError(
                "INVALID_PAYLOAD_LOCATION"
            ) from None
        return target, locator

    @staticmethod
    def _read_exact(target: Path, expected: bytes | None = None) -> bytes:
        try:
            if target.is_symlink() or not target.is_file():
                raise OpenJiuwenCheckpointPayloadStoreError(
                    "PAYLOAD_OBJECT_UNAVAILABLE"
                )
            size = target.stat().st_size
            if not 0 < size <= MAX_OPENJIUWEN_D1_PUBLICATION_BYTES:
                raise OpenJiuwenCheckpointPayloadStoreError(
                    "PAYLOAD_OBJECT_OUT_OF_BOUNDS"
                )
            payload = target.read_bytes()
        except OpenJiuwenCheckpointPayloadStoreError:
            raise
        except OSError:
            raise OpenJiuwenCheckpointPayloadStoreError(
                "PAYLOAD_OBJECT_UNAVAILABLE"
            ) from None
        if len(payload) != size:
            raise OpenJiuwenCheckpointPayloadStoreError("PAYLOAD_OBJECT_CHANGED")
        if expected is not None and payload != expected:
            raise OpenJiuwenCheckpointPayloadStoreError("CHECKPOINT_ID_CONFLICT")
        return payload

    @classmethod
    def _put_sync(cls, target: Path, payload: bytes) -> bytes:
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            raise OpenJiuwenCheckpointPayloadStoreError(
                "PAYLOAD_ROOT_UNAVAILABLE"
            ) from None
        if target.exists() or target.is_symlink():
            return cls._read_exact(target, payload)

        temp_name: str | None = None
        try:
            descriptor, temp_name = tempfile.mkstemp(
                prefix=".openjiuwen-checkpoint-",
                suffix=".tmp",
                dir=target.parent,
            )
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temp_name, target)
            except FileExistsError:
                pass
            except OSError:
                raise OpenJiuwenCheckpointPayloadStoreError(
                    "IMMUTABLE_CREATE_FAILED"
                ) from None
        finally:
            if temp_name is not None:
                try:
                    os.unlink(temp_name)
                except FileNotFoundError:
                    pass
                except OSError:
                    pass
        return cls._read_exact(target, payload)

    def _make_receipt(
        self,
        *,
        checkpoint_id: str,
        payload_locator: str,
        payload_digest: str,
        payload_size: int,
    ) -> object:
        try:
            receipt = self._receipt_factory(
                checkpoint_id=checkpoint_id,
                payload_locator=payload_locator,
                payload_digest=payload_digest,
                payload_size=payload_size,
            )
        except Exception:
            raise OpenJiuwenCheckpointPayloadStoreError(
                "RECEIPT_FACTORY_FAILED"
            ) from None
        if (
            getattr(receipt, "checkpoint_id", None) != checkpoint_id
            or getattr(receipt, "payload_locator", None) != payload_locator
            or getattr(receipt, "payload_digest", None) != payload_digest
            or getattr(receipt, "payload_size", None) != payload_size
        ):
            raise OpenJiuwenCheckpointPayloadStoreError("INVALID_PAYLOAD_RECEIPT")
        return receipt

    async def put(self, checkpoint_id: str, payload: bytes) -> object:
        checkpoint_id = self._checkpoint_id(checkpoint_id)
        payload = self._payload(payload)
        target, locator = self._location(checkpoint_id)
        stored = await asyncio.to_thread(self._put_sync, target, payload)
        digest = hashlib.sha256(stored).hexdigest()
        return self._make_receipt(
            checkpoint_id=checkpoint_id,
            payload_locator=locator,
            payload_digest=digest,
            payload_size=len(stored),
        )

    async def get(self, receipt: object) -> bytes:
        checkpoint_id = self._checkpoint_id(getattr(receipt, "checkpoint_id", None))
        target, expected_locator = self._location(checkpoint_id)
        if getattr(receipt, "payload_locator", None) != expected_locator:
            raise OpenJiuwenCheckpointPayloadStoreError("PAYLOAD_LOCATOR_MISMATCH")
        raw_digest = getattr(receipt, "payload_digest", None)
        if type(raw_digest) is not str or _SHA256_RE.fullmatch(raw_digest) is None:
            raise OpenJiuwenCheckpointPayloadStoreError("INVALID_PAYLOAD_DIGEST")
        raw_size = getattr(receipt, "payload_size", None)
        if (
            type(raw_size) is not int
            or not 0 < raw_size <= MAX_OPENJIUWEN_D1_PUBLICATION_BYTES
        ):
            raise OpenJiuwenCheckpointPayloadStoreError("INVALID_PAYLOAD_SIZE")
        payload = await asyncio.to_thread(self._read_exact, target)
        if (
            len(payload) != raw_size
            or hashlib.sha256(payload).hexdigest() != raw_digest
        ):
            raise OpenJiuwenCheckpointPayloadStoreError("PAYLOAD_RECEIPT_MISMATCH")
        return payload


class OpenJiuwenD1CheckpointAdapter:
    """Map complete LiveVoice D1 payloads to one bound AgentCore authority."""

    __slots__ = ("_binding", "_coordinator", "_handle", "_scope")

    def __init__(
        self,
        handle: AgentCoreCheckpointAuthorityPort,
        scope: ScopeRef,
        *,
        payload_store: object,
        coordinator_factory: AgentCoreCheckpointCoordinatorFactory,
    ) -> None:
        if not isinstance(scope, ScopeRef):
            raise _adapter_error("INVALID_PRODUCT_SCOPE")
        try:
            self._scope = ScopeRef.from_dict(scope.to_dict())
        except Exception:
            raise _adapter_error("INVALID_PRODUCT_SCOPE") from None
        try:
            self._binding = derive_openjiuwen_scope_binding(self._scope)
        except Exception:
            raise _adapter_error("INVALID_PRODUCT_SCOPE") from None
        self._handle = handle
        self._require_handle_binding()
        if not callable(coordinator_factory):
            raise _adapter_error("INVALID_CHECKPOINT_COORDINATOR_FACTORY")
        try:
            self._coordinator = coordinator_factory(handle, payload_store)
        except Exception:
            raise _adapter_error("CHECKPOINT_COORDINATOR_UNAVAILABLE") from None
        if any(
            not callable(getattr(self._coordinator, name, None))
            for name in ("publish", "load_current")
        ):
            raise _adapter_error("INVALID_CHECKPOINT_COORDINATOR")

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
            or any(
                not callable(getattr(self._handle, name, None))
                for name in (
                    "publish_execution_checkpoint",
                    "read_current_execution_checkpoint",
                )
            )
        ):
            raise _adapter_error("AGENTCORE_BINDING_MISMATCH")

    @staticmethod
    def _producer(value: object) -> OpenJiuwenD1CheckpointProducer:
        if type(value) is not OpenJiuwenD1CheckpointProducer:
            raise _adapter_error("INVALID_CHECKPOINT_PRODUCER")
        _text(value.task_id, "task_id")
        _text(value.execution_id, "execution_id")
        _sha256(value.profile_digest, "profile_digest")
        _integer(value.generation, "generation")
        _text(value.owner_id, "owner_id")
        _integer(value.owner_epoch, "owner_epoch")
        _integer(value.execution_version, "execution_version")
        head = _integer(value.expected_checkpoint_head, "expected_checkpoint_head")
        if head == _MAX_SIGNED_BIGINT:
            raise _adapter_error("EXPECTED_CHECKPOINT_HEAD_NOT_INCREMENTABLE")
        return value

    @staticmethod
    def _read_binding(value: object) -> OpenJiuwenD1CheckpointReadBinding:
        if type(value) is not OpenJiuwenD1CheckpointReadBinding:
            raise _adapter_error("INVALID_CHECKPOINT_READ_BINDING")
        _text(value.task_id, "task_id")
        _text(value.execution_id, "execution_id")
        _sha256(value.profile_digest, "profile_digest")
        _integer(value.generation, "generation")
        _integer(value.execution_version, "execution_version")
        return value

    def _checkpoint(
        self,
        value: object,
        *,
        task_id: str,
        execution_id: str,
        profile_digest: str,
        generation: int,
    ) -> D1Checkpoint:
        if type(value) is not D1Checkpoint:
            raise _adapter_error("INVALID_D1_CHECKPOINT")
        checkpoint = value
        if (
            checkpoint.scope != self._scope
            or checkpoint.task_id != task_id
            or checkpoint.producer_attempt_id != execution_id
            or checkpoint.profile.profile_digest != profile_digest
            or checkpoint.profile.durability_level != "D1"
            or checkpoint.recovery_generation != generation
            or checkpoint.complete is not True
        ):
            raise _adapter_error("D1_CHECKPOINT_BINDING_MISMATCH")
        _text(checkpoint.state_schema_id, "state_schema_id")
        _integer(checkpoint.state_schema_version, "state_schema_version", positive=True)
        return checkpoint

    async def _authority_read(
        self,
        binding: OpenJiuwenD1CheckpointReadBinding,
    ) -> object | None:
        self._require_handle_binding()
        try:
            result = await self._handle.read_current_execution_checkpoint(
                binding.task_id,
                binding.execution_id,
                binding.execution_version,
                profile_digest=binding.profile_digest,
                generation=binding.generation,
            )
        except OpenJiuwenD1CheckpointAdapterError:
            raise
        except Exception:
            raise _adapter_error("AGENTCORE_CHECKPOINT_AUTHORITY_FAILURE") from None
        self._require_handle_binding()
        return result

    @staticmethod
    def _record_facts(record: object) -> dict[str, object]:
        facts = {
            name: getattr(record, name, None)
            for name in (
                "team_name",
                "task_id",
                "execution_id",
                "checkpoint_id",
                "checkpoint_sequence",
                "profile_digest",
                "generation",
                "producer_owner_id",
                "producer_owner_epoch",
                "publication_execution_version",
                "codec_id",
                "codec_version",
                "state_schema_id",
                "state_schema_version",
                "complete",
                "payload_locator",
                "payload_digest",
                "payload_size",
                "reference_digest",
                "source_event_id",
                "source_sequence",
                "created_at",
            )
        }
        _text(facts["team_name"], "record_team_name")
        _text(facts["task_id"], "record_task_id")
        _text(facts["execution_id"], "record_execution_id")
        _text(facts["checkpoint_id"], "record_checkpoint_id")
        _integer(
            facts["checkpoint_sequence"], "record_checkpoint_sequence", positive=True
        )
        _sha256(facts["profile_digest"], "record_profile_digest")
        _integer(facts["generation"], "record_generation")
        _text(facts["producer_owner_id"], "record_producer_owner_id")
        _integer(facts["producer_owner_epoch"], "record_producer_owner_epoch")
        _integer(
            facts["publication_execution_version"],
            "record_publication_execution_version",
        )
        _text(facts["codec_id"], "record_codec_id")
        _integer(facts["codec_version"], "record_codec_version", positive=True)
        _text(facts["state_schema_id"], "record_state_schema_id")
        _integer(
            facts["state_schema_version"],
            "record_state_schema_version",
            positive=True,
        )
        if _boolean(facts["complete"], "record_complete") is not True:
            raise _adapter_error("INCOMPLETE_CHECKPOINT_RECORD")
        _text(
            facts["payload_locator"],
            "record_payload_locator",
            maximum=_MAX_LOCATOR_LENGTH,
        )
        _sha256(facts["payload_digest"], "record_payload_digest")
        payload_size = _integer(
            facts["payload_size"], "record_payload_size", positive=True
        )
        if payload_size > MAX_OPENJIUWEN_D1_PUBLICATION_BYTES:
            raise _adapter_error("RECORD_PAYLOAD_SIZE_EXCEEDED")
        _sha256(facts["reference_digest"], "record_reference_digest")
        _text(facts["source_event_id"], "record_source_event_id")
        _integer(facts["source_sequence"], "record_source_sequence", positive=True)
        _integer(facts["created_at"], "record_created_at", positive=True)
        return facts

    def _snapshot_facts(
        self,
        snapshot: object,
        *,
        binding: OpenJiuwenD1CheckpointReadBinding,
    ) -> tuple[dict[str, object], int, str, int]:
        record_facts = self._record_facts(getattr(snapshot, "record", None))
        current_version = _integer(
            getattr(snapshot, "current_execution_version", None),
            "current_execution_version",
        )
        disposition = _enum_text(
            getattr(snapshot, "current_execution_disposition", None),
            "current_execution_disposition",
        )
        checkpoint_head = _integer(
            getattr(snapshot, "checkpoint_head", None),
            "checkpoint_head",
            positive=True,
        )
        if (
            record_facts["team_name"] != self._binding.team_name
            or record_facts["task_id"] != binding.task_id
            or record_facts["execution_id"] != binding.execution_id
            or record_facts["profile_digest"] != binding.profile_digest
            or record_facts["generation"] != binding.generation
            or current_version != binding.execution_version
            or record_facts["publication_execution_version"] > current_version
            or disposition not in {"owned", "recoverable"}
            or record_facts["checkpoint_sequence"] != checkpoint_head
        ):
            raise _adapter_error("CHECKPOINT_SNAPSHOT_BINDING_MISMATCH")
        return record_facts, current_version, disposition, checkpoint_head

    async def publish(
        self,
        checkpoint: D1Checkpoint,
        producer: OpenJiuwenD1CheckpointProducer,
    ) -> OpenJiuwenD1CheckpointPublishDecision:
        producer = self._producer(producer)
        checkpoint = self._checkpoint(
            checkpoint,
            task_id=producer.task_id,
            execution_id=producer.execution_id,
            profile_digest=producer.profile_digest,
            generation=producer.generation,
        )
        payload = checkpoint.canonical_bytes()
        if not payload or len(payload) > MAX_OPENJIUWEN_D1_PUBLICATION_BYTES:
            raise _adapter_error("D1_CHECKPOINT_WIRE_EXCEEDS_AGENTCORE_LIMIT")
        outer_id = derive_openjiuwen_outer_checkpoint_id(
            self._binding,
            task_id=producer.task_id,
            execution_id=producer.execution_id,
            native_checkpoint_id=checkpoint.checkpoint_id,
        )
        outer_sequence = producer.expected_checkpoint_head + 1
        payload_digest = hashlib.sha256(payload).hexdigest()
        self._require_handle_binding()
        try:
            raw = await self._coordinator.publish(
                producer.task_id,
                producer.execution_id,
                outer_id,
                payload,
                profile_digest=producer.profile_digest,
                generation=producer.generation,
                owner_id=producer.owner_id,
                owner_epoch=producer.owner_epoch,
                expected_execution_version=producer.execution_version,
                checkpoint_sequence=outer_sequence,
                expected_checkpoint_head=producer.expected_checkpoint_head,
                codec_id=OPENJIUWEN_D1_CODEC_ID,
                codec_version=OPENJIUWEN_D1_CODEC_VERSION,
                state_schema_id=checkpoint.state_schema_id,
                state_schema_version=checkpoint.state_schema_version,
                complete=True,
            )
        except OpenJiuwenD1CheckpointAdapterError:
            raise
        except Exception:
            raise _adapter_error("AGENTCORE_CHECKPOINT_PUBLICATION_FAILURE") from None
        self._require_handle_binding()

        ok = _boolean(getattr(raw, "ok", None), "checkpoint_result_ok")
        changed = _boolean(getattr(raw, "changed", None), "checkpoint_result_changed")
        replayed = _boolean(
            getattr(raw, "replayed", None), "checkpoint_result_replayed"
        )
        reason = _text(
            getattr(raw, "reason", None),
            "checkpoint_result_reason",
            maximum=_MAX_TEXT_LENGTH,
            allow_empty=True,
        )
        record = getattr(raw, "record", None)
        if not ok:
            if record is not None or changed or replayed or not reason.strip():
                raise _adapter_error("INVALID_CHECKPOINT_PUBLICATION_RESULT")
            return OpenJiuwenD1CheckpointPublishDecision(
                ok=False,
                reason="AGENTCORE_CHECKPOINT_REJECTED",
                publication=None,
            )
        if reason or record is None or changed == replayed:
            raise _adapter_error("INVALID_CHECKPOINT_PUBLICATION_RESULT")
        facts = self._record_facts(record)
        expected = {
            "team_name": self._binding.team_name,
            "task_id": producer.task_id,
            "execution_id": producer.execution_id,
            "checkpoint_id": outer_id,
            "checkpoint_sequence": outer_sequence,
            "profile_digest": producer.profile_digest,
            "generation": producer.generation,
            "producer_owner_id": producer.owner_id,
            "producer_owner_epoch": producer.owner_epoch,
            "publication_execution_version": producer.execution_version,
            "codec_id": OPENJIUWEN_D1_CODEC_ID,
            "codec_version": OPENJIUWEN_D1_CODEC_VERSION,
            "state_schema_id": checkpoint.state_schema_id,
            "state_schema_version": checkpoint.state_schema_version,
            "complete": True,
            "payload_digest": payload_digest,
            "payload_size": len(payload),
        }
        if any(facts[name] != value for name, value in expected.items()):
            raise _adapter_error("CHECKPOINT_PUBLICATION_BINDING_MISMATCH")
        publication = OpenJiuwenD1CheckpointPublication(
            task_id=producer.task_id,
            execution_id=producer.execution_id,
            outer_checkpoint_id=outer_id,
            outer_checkpoint_sequence=outer_sequence,
            native_checkpoint_id=checkpoint.checkpoint_id,
            native_checkpoint_sequence=checkpoint.checkpoint_sequence,
            publication_execution_version=producer.execution_version,
            payload_locator=str(facts["payload_locator"]),
            payload_digest=payload_digest,
            payload_size=len(payload),
            reference_digest=str(facts["reference_digest"]),
            source_event_id=str(facts["source_event_id"]),
            source_sequence=int(facts["source_sequence"]),
            changed=changed,
            replayed=replayed,
        )
        return OpenJiuwenD1CheckpointPublishDecision(
            ok=True,
            reason="",
            publication=publication,
        )

    async def load_current(
        self,
        binding: OpenJiuwenD1CheckpointReadBinding,
    ) -> OpenJiuwenD1LoadedCheckpoint | None:
        binding = self._read_binding(binding)
        for _attempt in range(_MAX_SNAPSHOT_ATTEMPTS):
            before = await self._authority_read(binding)
            before_facts = (
                None
                if before is None
                else self._snapshot_facts(before, binding=binding)
            )
            self._require_handle_binding()
            try:
                loaded = await self._coordinator.load_current(
                    binding.task_id,
                    binding.execution_id,
                    binding.execution_version,
                    profile_digest=binding.profile_digest,
                    generation=binding.generation,
                )
            except OpenJiuwenD1CheckpointAdapterError:
                raise
            except Exception:
                raise _adapter_error("AGENTCORE_CHECKPOINT_LOAD_FAILURE") from None
            self._require_handle_binding()
            after = await self._authority_read(binding)
            after_facts = (
                None if after is None else self._snapshot_facts(after, binding=binding)
            )
            if before_facts != after_facts:
                continue
            if before_facts is None:
                if loaded is not None:
                    raise _adapter_error("CHECKPOINT_LOAD_WITHOUT_REFERENCE")
                return None
            if loaded is None:
                raise _adapter_error("CHECKPOINT_PAYLOAD_UNAVAILABLE_OR_CORRUPT")
            loaded_snapshot = getattr(loaded, "snapshot", None)
            loaded_facts = self._snapshot_facts(loaded_snapshot, binding=binding)
            if loaded_facts != before_facts:
                raise _adapter_error("CHECKPOINT_LOAD_SNAPSHOT_MISMATCH")
            payload = getattr(loaded, "payload", None)
            if (
                type(payload) is not bytes
                or not payload
                or len(payload) > MAX_OPENJIUWEN_D1_PUBLICATION_BYTES
            ):
                raise _adapter_error("INVALID_LOADED_CHECKPOINT_PAYLOAD")
            try:
                checkpoint = D1Checkpoint.from_bytes(payload)
            except DurabilityCheckpointViolation:
                raise _adapter_error("INVALID_LOADED_D1_CHECKPOINT") from None
            checkpoint = self._checkpoint(
                checkpoint,
                task_id=binding.task_id,
                execution_id=binding.execution_id,
                profile_digest=binding.profile_digest,
                generation=binding.generation,
            )
            record_facts, current_version, disposition, _head = loaded_facts
            expected_outer_id = derive_openjiuwen_outer_checkpoint_id(
                self._binding,
                task_id=binding.task_id,
                execution_id=binding.execution_id,
                native_checkpoint_id=checkpoint.checkpoint_id,
            )
            payload_digest = hashlib.sha256(payload).hexdigest()
            if (
                record_facts["checkpoint_id"] != expected_outer_id
                or record_facts["codec_id"] != OPENJIUWEN_D1_CODEC_ID
                or record_facts["codec_version"] != OPENJIUWEN_D1_CODEC_VERSION
                or record_facts["state_schema_id"] != checkpoint.state_schema_id
                or record_facts["state_schema_version"]
                != checkpoint.state_schema_version
                or record_facts["payload_digest"] != payload_digest
                or record_facts["payload_size"] != len(payload)
            ):
                raise _adapter_error("LOADED_D1_CHECKPOINT_BINDING_MISMATCH")
            return OpenJiuwenD1LoadedCheckpoint(
                checkpoint=checkpoint,
                outer_checkpoint_id=expected_outer_id,
                outer_checkpoint_sequence=int(record_facts["checkpoint_sequence"]),
                publication_execution_version=int(
                    record_facts["publication_execution_version"]
                ),
                current_execution_version=current_version,
                current_execution_disposition=disposition,
                payload_locator=str(record_facts["payload_locator"]),
                payload_digest=payload_digest,
                payload_size=len(payload),
                reference_digest=str(record_facts["reference_digest"]),
            )
        raise _adapter_error("CHECKPOINT_SNAPSHOT_CHANGED")


__all__ = [
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
]
