# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Bounded synthetic-canary checks for Live Voice Alpha privacy surfaces.

This module performs no I/O and grants no Alpha acceptance credit. A caller
must capture every closed surface for one declared candidate/run/source and
pass immutable records here. The evaluator detects only its deterministic
exact canaries. It cannot prove route binding, absence of unknown secrets, or
absence of audio after transformations that change the checked bytes.
"""

from __future__ import annotations

import base64
import hashlib
import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, cast


_CANDIDATE_SHA = re.compile(r"[0-9a-f]{40}")
_RUN_REF = re.compile(r"alpha-privacy-run:[0-9a-f]{64}")
_CAPTURE_RECEIPT = re.compile(r"sha256:[0-9a-f]{64}")

MAX_OBSERVATIONS = 40
MAX_RECORDS_PER_OBSERVATION = 64
MAX_CHUNKS_PER_RECORD = 64
MAX_CHUNKS_PER_OBSERVATION = 256
MAX_CHUNK_BYTES = 262_144
MAX_BOUNDED_TEXT_ENCODE_BYTES = 4 * MAX_CHUNK_BYTES
MAX_RECORD_BYTES = 1_048_576
MAX_BYTES_PER_OBSERVATION = 1_048_576
MAX_TOTAL_RECORDS = 1_280
MAX_TOTAL_CHUNKS = 4_096
MAX_TOTAL_BYTES = 4_194_304
MAX_CANARY_PATTERN_UNITS = 512


class AlphaPrivacyConformanceViolation(ValueError):
    """Fail-closed boundary violation with a non-sensitive reason."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


class AlphaPrivacySurface(StrEnum):
    """Closed Alpha capture vocabulary; in-memory media buffers are excluded."""

    RUNTIME_FILESYSTEM = "runtime_filesystem"
    EVIDENCE_FILESYSTEM = "evidence_filesystem"
    BROWSER_LOCAL_STORAGE = "browser_local_storage"
    BROWSER_SESSION_STORAGE = "browser_session_storage"
    BROWSER_INDEXED_DB = "browser_indexed_db"
    BROWSER_CACHE_STORAGE = "browser_cache_storage"
    BROWSER_COOKIES = "browser_cookies"
    BROWSER_OPFS = "browser_origin_private_file_system"
    BROWSER_ADDRESS_HISTORY = "browser_address_history"
    BROWSER_NETWORK_URLS = "browser_network_urls"
    BROWSER_CONSOLE = "browser_console"
    WEB_RUNTIME_LOGS = "web_runtime_logs"
    GATEWAY_RUNTIME_LOGS = "gateway_runtime_logs"
    AGENT_SERVER_RUNTIME_LOGS = "agent_server_runtime_logs"
    CONTEXT = "context"
    TASK_EVENT = "task_event"
    WORK_PROGRESS = "work_progress"
    SPEECH_EVIDENCE = "speech_evidence"
    X_OBSERVABILITY_EVIDENCE = "x_observability_evidence"


ALPHA_PRIVACY_SURFACES = tuple(AlphaPrivacySurface)


class SyntheticSecretKind(StrEnum):
    """Secret/content identities represented by deterministic synthetic values."""

    PROVIDER_CREDENTIAL = "provider_credential"
    MEDIA_TICKET = "media_ticket"
    DEVICE_IDENTITY = "device_identity"
    UNAUTHORIZED_CONTENT = "unauthorized_content"


class AlphaPrivacyCaptureSource(StrEnum):
    """Closed non-sensitive identity for the governed capture implementation."""

    CONTROLLED_ALPHA_PRIVACY_CAPTURE_V1 = "controlled_alpha_privacy_capture_v1"


class AlphaPrivacyChunkKind(StrEnum):
    TEXT = "text"
    BYTES = "bytes"


class AlphaPrivacyRecordBuildReason(StrEnum):
    READY = "record_ready"
    INVALID_CONTAINER = "invalid_record_container"
    EMPTY = "empty_record"
    CHUNK_COUNT_EXCEEDED = "record_chunk_count_exceeded"
    INVALID_CHUNK_TYPE = "invalid_chunk_type"
    MIXED_CHUNK_TYPES = "mixed_chunk_types"
    INVALID_UTF8 = "invalid_utf8_chunk"
    CHUNK_BYTES_EXCEEDED = "chunk_bytes_exceeded"
    RECORD_BYTES_EXCEEDED = "record_bytes_exceeded"
    FORGED_RECORD = "forged_record"
    OBSERVATION_RECORD_COUNT_EXCEEDED = "observation_record_count_exceeded"
    OBSERVATION_CHUNK_COUNT_EXCEEDED = "observation_chunk_count_exceeded"
    OBSERVATION_BYTES_EXCEEDED = "observation_bytes_exceeded"


class CanaryFamily(StrEnum):
    SECRET = "synthetic_secret"
    AUDIO_BYTES = "deterministic_audio_bytes"


class CanaryRepresentation(StrEnum):
    UTF8_TEXT = "utf8_text"
    UTF8_BYTES = "utf8_bytes"
    RAW_BYTES = "raw_bytes"
    BASE64_TEXT = "base64_text"
    BASE64_BYTES = "base64_bytes"


class AlphaPrivacyConformanceStatus(StrEnum):
    DISABLED = "disabled"
    INCOMPLETE = "incomplete"
    LEAK_DETECTED = "leak_detected"
    SUPPLIED_CAPTURE_EXACT_MATCH_CLEAR = "supplied_capture_exact_match_clear"


@dataclass(frozen=True, slots=True)
class _ExactPattern:
    family: CanaryFamily
    classification: str
    representation: CanaryRepresentation
    value: str | bytes = field(repr=False)


@dataclass(frozen=True, slots=True)
class SyntheticSecretCanary:
    """One generated secret/content canary; values are hidden from repr."""

    kind: SyntheticSecretKind
    utf8_text: str = field(repr=False)
    utf8_bytes: bytes = field(repr=False)
    base64_text: str = field(repr=False)
    base64_bytes: bytes = field(repr=False)

    @classmethod
    def _for_binding(
        cls,
        *,
        kind: SyntheticSecretKind,
        candidate_sha: str,
        run_ref: str,
        capture_source: AlphaPrivacyCaptureSource,
    ) -> SyntheticSecretCanary:
        marker = (
            "LV_PRIVACY_SECRET_CANARY_V1|"
            f"{kind.value}|{candidate_sha}|{run_ref}|{capture_source.value}"
        )
        encoded = marker.encode("utf-8")
        encoded_base64 = base64.b64encode(encoded)
        return cls(
            kind=kind,
            utf8_text=marker,
            utf8_bytes=encoded,
            base64_text=encoded_base64.decode("ascii"),
            base64_bytes=encoded_base64,
        )

    def _patterns(self) -> tuple[_ExactPattern, ...]:
        return (
            _ExactPattern(
                CanaryFamily.SECRET,
                self.kind.value,
                CanaryRepresentation.UTF8_TEXT,
                self.utf8_text,
            ),
            _ExactPattern(
                CanaryFamily.SECRET,
                self.kind.value,
                CanaryRepresentation.UTF8_BYTES,
                self.utf8_bytes,
            ),
            _ExactPattern(
                CanaryFamily.SECRET,
                self.kind.value,
                CanaryRepresentation.BASE64_TEXT,
                self.base64_text,
            ),
            _ExactPattern(
                CanaryFamily.SECRET,
                self.kind.value,
                CanaryRepresentation.BASE64_BYTES,
                self.base64_bytes,
            ),
        )


@dataclass(frozen=True, slots=True)
class DeterministicAudioByteCanary:
    """Synthetic bytes for exact raw/UTF-8/base64 audio-payload checks."""

    raw_bytes: bytes = field(repr=False)
    utf8_text: str = field(repr=False)
    utf8_bytes: bytes = field(repr=False)
    base64_text: str = field(repr=False)
    base64_bytes: bytes = field(repr=False)

    @classmethod
    def _for_binding(
        cls,
        *,
        candidate_sha: str,
        run_ref: str,
        capture_source: AlphaPrivacyCaptureSource,
    ) -> DeterministicAudioByteCanary:
        marker = (
            "LV_PRIVACY_AUDIO_CANARY_V1|"
            f"{candidate_sha}|{run_ref}|{capture_source.value}"
        )
        utf8_bytes = marker.encode("utf-8")
        raw_bytes = b"\x00\xffLVRAW\x01" + utf8_bytes + b"\x80\xfeLVEND\x00"
        encoded_base64 = base64.b64encode(raw_bytes)
        return cls(
            raw_bytes=raw_bytes,
            utf8_text=marker,
            utf8_bytes=utf8_bytes,
            base64_text=encoded_base64.decode("ascii"),
            base64_bytes=encoded_base64,
        )

    def _patterns(self) -> tuple[_ExactPattern, ...]:
        return (
            _ExactPattern(
                CanaryFamily.AUDIO_BYTES,
                "raw_audio",
                CanaryRepresentation.RAW_BYTES,
                self.raw_bytes,
            ),
            _ExactPattern(
                CanaryFamily.AUDIO_BYTES,
                "raw_audio",
                CanaryRepresentation.UTF8_TEXT,
                self.utf8_text,
            ),
            _ExactPattern(
                CanaryFamily.AUDIO_BYTES,
                "raw_audio",
                CanaryRepresentation.UTF8_BYTES,
                self.utf8_bytes,
            ),
            _ExactPattern(
                CanaryFamily.AUDIO_BYTES,
                "raw_audio",
                CanaryRepresentation.BASE64_TEXT,
                self.base64_text,
            ),
            _ExactPattern(
                CanaryFamily.AUDIO_BYTES,
                "raw_audio",
                CanaryRepresentation.BASE64_BYTES,
                self.base64_bytes,
            ),
        )


def _run_ref(value: object) -> str:
    if type(value) is not str or _RUN_REF.fullmatch(value) is None:
        raise AlphaPrivacyConformanceViolation(
            "INVALID_RUN_REF",
            "declared_run_ref must use the canonical non-sensitive digest form",
        )
    return value


@dataclass(frozen=True, slots=True)
class _ChunkInspection:
    reason: AlphaPrivacyRecordBuildReason
    kind: AlphaPrivacyChunkKind | None
    byte_count: int


def _encode_bounded_text_chunk(chunk: str) -> bytes:
    """Encode text after its code-point count has passed the chunk limit."""

    return chunk.encode("utf-8")


def _inspect_chunk(chunk: object) -> _ChunkInspection:
    """Inspect possibly sensitive input without allowing an exception to escape."""

    if type(chunk) is bytes:
        byte_count = len(chunk)
        kind = AlphaPrivacyChunkKind.BYTES
    elif type(chunk) is str:
        code_point_count = len(chunk)
        if code_point_count > MAX_CHUNK_BYTES:
            return _ChunkInspection(
                AlphaPrivacyRecordBuildReason.CHUNK_BYTES_EXCEEDED,
                AlphaPrivacyChunkKind.TEXT,
                code_point_count,
            )
        try:
            byte_count = len(_encode_bounded_text_chunk(chunk))
        except UnicodeEncodeError:
            return _ChunkInspection(AlphaPrivacyRecordBuildReason.INVALID_UTF8, None, 0)
        kind = AlphaPrivacyChunkKind.TEXT
    else:
        return _ChunkInspection(
            AlphaPrivacyRecordBuildReason.INVALID_CHUNK_TYPE, None, 0
        )
    if byte_count > MAX_CHUNK_BYTES:
        return _ChunkInspection(
            AlphaPrivacyRecordBuildReason.CHUNK_BYTES_EXCEEDED, kind, byte_count
        )
    return _ChunkInspection(AlphaPrivacyRecordBuildReason.READY, kind, byte_count)


@dataclass(frozen=True, slots=True)
class _RecordInspection:
    reason: AlphaPrivacyRecordBuildReason
    kind: AlphaPrivacyChunkKind | None = None
    chunk_count: int = 0
    byte_count: int = 0


def _inspect_chunks(chunks: object) -> _RecordInspection:
    """Return only closed metadata; never raise while raw chunks are in locals."""

    if type(chunks) is not tuple:
        return _RecordInspection(AlphaPrivacyRecordBuildReason.INVALID_CONTAINER)
    if not chunks:
        return _RecordInspection(AlphaPrivacyRecordBuildReason.EMPTY)
    if len(chunks) > MAX_CHUNKS_PER_RECORD:
        return _RecordInspection(AlphaPrivacyRecordBuildReason.CHUNK_COUNT_EXCEEDED)
    kind: AlphaPrivacyChunkKind | None = None
    byte_count = 0
    for chunk in chunks:
        inspection = _inspect_chunk(chunk)
        if inspection.reason is not AlphaPrivacyRecordBuildReason.READY:
            return _RecordInspection(inspection.reason)
        if kind is not None and inspection.kind is not kind:
            return _RecordInspection(AlphaPrivacyRecordBuildReason.MIXED_CHUNK_TYPES)
        kind = inspection.kind
        byte_count += inspection.byte_count
        if byte_count > MAX_RECORD_BYTES:
            return _RecordInspection(
                AlphaPrivacyRecordBuildReason.RECORD_BYTES_EXCEEDED
            )
    return _RecordInspection(
        AlphaPrivacyRecordBuildReason.READY,
        kind=kind,
        chunk_count=len(chunks),
        byte_count=byte_count,
    )


@dataclass(frozen=True, slots=True, init=False, repr=False)
class AlphaPrivacyCaptureRecord:
    """One factory-created deep-immutable record with a constant safe repr."""

    chunks: tuple[str, ...] | tuple[bytes, ...] = field(repr=False)
    chunk_kind: AlphaPrivacyChunkKind
    total_bytes: int

    def __new__(cls) -> AlphaPrivacyCaptureRecord:
        raise AlphaPrivacyConformanceViolation(
            "CAPTURE_RECORD_FACTORY_REQUIRED",
            "capture records must be created by the non-throwing factory",
        ) from None

    def __repr__(self) -> str:
        return "AlphaPrivacyCaptureRecord(<capture-redacted>)"

    @classmethod
    def _create(
        cls,
        *,
        chunks: tuple[str, ...] | tuple[bytes, ...],
        inspection: _RecordInspection,
    ) -> AlphaPrivacyCaptureRecord:
        record = object.__new__(cls)
        object.__setattr__(record, "chunks", chunks)
        object.__setattr__(record, "chunk_kind", inspection.kind)
        object.__setattr__(record, "total_bytes", inspection.byte_count)
        return record


@dataclass(frozen=True, slots=True)
class AlphaPrivacyCaptureRecordBuildResult:
    """Safe result from inspecting raw record input; never contains rejected input."""

    reason: AlphaPrivacyRecordBuildReason
    record: AlphaPrivacyCaptureRecord | None = field(default=None, repr=False)

    @property
    def ready(self) -> bool:
        return (
            self.reason is AlphaPrivacyRecordBuildReason.READY
            and type(self.record) is AlphaPrivacyCaptureRecord
        )

    def require_record(self) -> AlphaPrivacyCaptureRecord:
        if not self.ready:
            raise AlphaPrivacyConformanceViolation(
                self.reason.value,
                "capture record build was rejected by a closed privacy boundary",
            ) from None
        return cast(AlphaPrivacyCaptureRecord, self.record)


def build_alpha_privacy_capture_record(
    chunks: object,
) -> AlphaPrivacyCaptureRecordBuildResult:
    """Build a record without propagating an exception from sensitive input frames."""

    inspection = _inspect_chunks(chunks)
    if inspection.reason is not AlphaPrivacyRecordBuildReason.READY:
        return AlphaPrivacyCaptureRecordBuildResult(reason=inspection.reason)
    immutable_chunks = cast(tuple[str, ...] | tuple[bytes, ...], chunks)
    record = AlphaPrivacyCaptureRecord._create(
        chunks=immutable_chunks, inspection=inspection
    )
    return AlphaPrivacyCaptureRecordBuildResult(
        reason=AlphaPrivacyRecordBuildReason.READY,
        record=record,
    )


def _inspect_record(record: object) -> _RecordInspection:
    if type(record) is not AlphaPrivacyCaptureRecord:
        return _RecordInspection(AlphaPrivacyRecordBuildReason.FORGED_RECORD)
    try:
        chunks = object.__getattribute__(record, "chunks")
        chunk_kind = object.__getattribute__(record, "chunk_kind")
        total_bytes = object.__getattribute__(record, "total_bytes")
    except AttributeError:
        return _RecordInspection(AlphaPrivacyRecordBuildReason.FORGED_RECORD)
    inspection = _inspect_chunks(chunks)
    if (
        inspection.reason is not AlphaPrivacyRecordBuildReason.READY
        or type(chunk_kind) is not AlphaPrivacyChunkKind
        or chunk_kind is not inspection.kind
        or type(total_bytes) is not int
        or total_bytes != inspection.byte_count
    ):
        return _RecordInspection(AlphaPrivacyRecordBuildReason.FORGED_RECORD)
    return inspection


@dataclass(frozen=True, slots=True)
class _RecordTupleInspection:
    reason: AlphaPrivacyRecordBuildReason
    record_count: int = 0
    chunk_count: int = 0
    byte_count: int = 0


def _inspect_records(records: object) -> _RecordTupleInspection:
    """Validate record tuples without raising from frames that may hold capture data."""

    if type(records) is not tuple:
        return _RecordTupleInspection(AlphaPrivacyRecordBuildReason.INVALID_CONTAINER)
    if len(records) > MAX_RECORDS_PER_OBSERVATION:
        return _RecordTupleInspection(
            AlphaPrivacyRecordBuildReason.OBSERVATION_RECORD_COUNT_EXCEEDED
        )
    chunk_count = 0
    byte_count = 0
    for record in records:
        inspection = _inspect_record(record)
        if inspection.reason is not AlphaPrivacyRecordBuildReason.READY:
            return _RecordTupleInspection(inspection.reason)
        chunk_count += inspection.chunk_count
        byte_count += inspection.byte_count
        if chunk_count > MAX_CHUNKS_PER_OBSERVATION:
            return _RecordTupleInspection(
                AlphaPrivacyRecordBuildReason.OBSERVATION_CHUNK_COUNT_EXCEEDED
            )
        if byte_count > MAX_BYTES_PER_OBSERVATION:
            return _RecordTupleInspection(
                AlphaPrivacyRecordBuildReason.OBSERVATION_BYTES_EXCEEDED
            )
    return _RecordTupleInspection(
        AlphaPrivacyRecordBuildReason.READY,
        record_count=len(records),
        chunk_count=chunk_count,
        byte_count=byte_count,
    )


def _require_valid_records(inspection: _RecordTupleInspection) -> None:
    if inspection.reason is not AlphaPrivacyRecordBuildReason.READY:
        raise AlphaPrivacyConformanceViolation(
            inspection.reason.value,
            "capture records were rejected by a closed privacy boundary",
        ) from None


@dataclass(frozen=True, slots=True)
class AlphaPrivacyConformancePlan:
    """Immutable declared binding and generated canaries for one capture run."""

    declared_candidate_sha: str
    declared_run_ref: str
    declared_capture_source: AlphaPrivacyCaptureSource
    expected_surfaces: tuple[AlphaPrivacySurface, ...] = field(
        default=ALPHA_PRIVACY_SURFACES, init=False
    )
    synthetic_secret_canaries: tuple[SyntheticSecretCanary, ...] = field(
        init=False, repr=False
    )
    deterministic_audio_canary: DeterministicAudioByteCanary = field(
        init=False, repr=False
    )

    def __post_init__(self) -> None:
        if (
            type(self.declared_candidate_sha) is not str
            or _CANDIDATE_SHA.fullmatch(self.declared_candidate_sha) is None
        ):
            raise AlphaPrivacyConformanceViolation(
                "INVALID_CANDIDATE_SHA",
                "declared_candidate_sha must be one lowercase full SHA",
            )
        _run_ref(self.declared_run_ref)
        if type(self.declared_capture_source) is not AlphaPrivacyCaptureSource:
            raise AlphaPrivacyConformanceViolation(
                "INVALID_CAPTURE_SOURCE",
                "declared_capture_source must use the closed capture source vocabulary",
            )
        secrets = tuple(
            SyntheticSecretCanary._for_binding(
                kind=kind,
                candidate_sha=self.declared_candidate_sha,
                run_ref=self.declared_run_ref,
                capture_source=self.declared_capture_source,
            )
            for kind in SyntheticSecretKind
        )
        audio = DeterministicAudioByteCanary._for_binding(
            candidate_sha=self.declared_candidate_sha,
            run_ref=self.declared_run_ref,
            capture_source=self.declared_capture_source,
        )
        object.__setattr__(self, "synthetic_secret_canaries", secrets)
        object.__setattr__(self, "deterministic_audio_canary", audio)


@dataclass(frozen=True, slots=True)
class AlphaPrivacySurfaceObservation:
    """Deep-immutable records for exactly one declared privacy surface."""

    surface: AlphaPrivacySurface
    declared_candidate_sha: str
    declared_run_ref: str
    declared_capture_source: AlphaPrivacyCaptureSource
    capture_complete: bool
    records: tuple[AlphaPrivacyCaptureRecord, ...] = field(repr=False)
    capture_receipt: str

    def __post_init__(self) -> None:
        if type(self.surface) is not AlphaPrivacySurface:
            raise AlphaPrivacyConformanceViolation(
                "INVALID_SURFACE", "surface must use the closed Alpha vocabulary"
            )
        if (
            type(self.declared_candidate_sha) is not str
            or _CANDIDATE_SHA.fullmatch(self.declared_candidate_sha) is None
        ):
            raise AlphaPrivacyConformanceViolation(
                "INVALID_CANDIDATE_SHA",
                "declared_candidate_sha must be one lowercase full SHA",
            )
        _run_ref(self.declared_run_ref)
        if type(self.declared_capture_source) is not AlphaPrivacyCaptureSource:
            raise AlphaPrivacyConformanceViolation(
                "INVALID_CAPTURE_SOURCE",
                "declared_capture_source must use the closed capture source vocabulary",
            )
        if type(self.capture_complete) is not bool:
            raise AlphaPrivacyConformanceViolation(
                "INVALID_CAPTURE_COMPLETENESS", "capture_complete must be one boolean"
            )
        _require_valid_records(_inspect_records(self.records))
        if (
            type(self.capture_receipt) is not str
            or _CAPTURE_RECEIPT.fullmatch(self.capture_receipt) is None
        ):
            raise AlphaPrivacyConformanceViolation(
                "INVALID_CAPTURE_RECEIPT",
                "capture_receipt must use the canonical SHA-256 form",
            )


@dataclass(frozen=True, slots=True)
class AlphaPrivacyCanaryFinding:
    """Non-sensitive location/classification of one exact canary match."""

    surface: AlphaPrivacySurface
    family: CanaryFamily
    classification: str
    representation: CanaryRepresentation


_EXCLUDED_AUDIO_TRANSFORMATIONS = (
    "transformed_audio_bytes",
    "unlisted_audio_encodings",
    "resampled_audio",
)


@dataclass(frozen=True, slots=True)
class AlphaPrivacyConformanceReport:
    """Bounded result; acceptance/binding/real-route credit is impossible here."""

    status: AlphaPrivacyConformanceStatus
    declared_candidate_sha: str | None
    declared_run_ref: str | None
    declared_capture_source: AlphaPrivacyCaptureSource | None
    evaluated_surfaces: tuple[AlphaPrivacySurface, ...]
    missing_surfaces: tuple[AlphaPrivacySurface, ...]
    duplicate_surfaces: tuple[AlphaPrivacySurface, ...]
    incomplete_surfaces: tuple[AlphaPrivacySurface, ...]
    binding_conflict_surfaces: tuple[AlphaPrivacySurface, ...]
    capture_receipt_conflict_surfaces: tuple[AlphaPrivacySurface, ...]
    findings: tuple[AlphaPrivacyCanaryFinding, ...]
    observations_examined: int
    records_examined: int
    chunks_examined: int
    bytes_examined: int
    declared_binding_consistent: bool
    capture_receipts_consistent: bool
    supplied_capture_coverage_complete: bool
    supplied_capture_exact_match_clear: bool
    binding_verified: bool = field(default=False, init=False)
    capture_verified: bool = field(default=False, init=False)
    coverage_is_caller_declared: bool = field(default=True, init=False)
    real_route_verified: bool = field(default=False, init=False)
    alpha_gate_pass: bool = field(default=False, init=False)
    raw_audio_default_persistence_verified: bool = field(default=False, init=False)
    unknown_secret_absence_verified: bool = field(default=False, init=False)
    default_product_configuration_verified: bool = field(default=False, init=False)
    evidence_scope: str = field(
        default="caller_supplied_capture_synthetic_exact_canaries_only", init=False
    )
    audio_canary_semantics: str = field(
        default="deterministic_byte_sentinel_not_validated_audio_media", init=False
    )
    excluded_audio_transformations: tuple[str, ...] = field(
        default=_EXCLUDED_AUDIO_TRANSFORMATIONS, init=False
    )


class _HashUpdater(Protocol):
    def update(self, data: bytes, /) -> object: ...


def _hash_frame(hasher: _HashUpdater, tag: bytes, payload: bytes) -> None:
    hasher.update(tag)
    hasher.update(len(payload).to_bytes(8, "big"))
    hasher.update(payload)


def _valid_chunk_payload(chunk: str | bytes) -> bytes:
    """Encode a chunk only after the same immutable record passed inspection."""

    return chunk if type(chunk) is bytes else chunk.encode("utf-8")


def compute_alpha_privacy_capture_receipt(
    *,
    surface: AlphaPrivacySurface,
    declared_candidate_sha: str,
    declared_run_ref: str,
    declared_capture_source: AlphaPrivacyCaptureSource,
    capture_complete: bool,
    records: tuple[AlphaPrivacyCaptureRecord, ...],
) -> str:
    """Return an integrity digest over the exact immutable supplied records."""

    record_inspection = _inspect_records(records)
    immutable_records = (
        cast(tuple[AlphaPrivacyCaptureRecord, ...], records)
        if record_inspection.reason is AlphaPrivacyRecordBuildReason.READY
        else None
    )
    del records
    _require_valid_records(record_inspection)
    assert immutable_records is not None
    if type(surface) is not AlphaPrivacySurface:
        raise AlphaPrivacyConformanceViolation(
            "INVALID_SURFACE", "surface must use the closed Alpha vocabulary"
        )
    if (
        type(declared_candidate_sha) is not str
        or _CANDIDATE_SHA.fullmatch(declared_candidate_sha) is None
    ):
        raise AlphaPrivacyConformanceViolation(
            "INVALID_CANDIDATE_SHA",
            "declared_candidate_sha must be one lowercase full SHA",
        )
    _run_ref(declared_run_ref)
    if type(declared_capture_source) is not AlphaPrivacyCaptureSource:
        raise AlphaPrivacyConformanceViolation(
            "INVALID_CAPTURE_SOURCE",
            "declared_capture_source must use the closed capture source vocabulary",
        )
    if type(capture_complete) is not bool:
        raise AlphaPrivacyConformanceViolation(
            "INVALID_CAPTURE_COMPLETENESS", "capture_complete must be one boolean"
        )
    hasher = hashlib.sha256()
    _hash_frame(hasher, b"V", b"LV_ALPHA_PRIVACY_CAPTURE_RECEIPT_V2")
    _hash_frame(hasher, b"U", surface.value.encode("ascii"))
    _hash_frame(hasher, b"C", declared_candidate_sha.encode("ascii"))
    _hash_frame(hasher, b"R", declared_run_ref.encode("ascii"))
    _hash_frame(hasher, b"O", declared_capture_source.value.encode("ascii"))
    _hash_frame(hasher, b"Q", b"1" if capture_complete else b"0")
    _hash_frame(hasher, b"Z", len(immutable_records).to_bytes(8, "big"))
    for record in immutable_records:
        _hash_frame(hasher, b"K", record.chunk_kind.value.encode("ascii"))
        _hash_frame(hasher, b"N", len(record.chunks).to_bytes(8, "big"))
        for chunk in record.chunks:
            _hash_frame(hasher, b"X", _valid_chunk_payload(chunk))
    return f"sha256:{hasher.hexdigest()}"


def _patterns(plan: AlphaPrivacyConformancePlan) -> tuple[_ExactPattern, ...]:
    patterns: list[_ExactPattern] = []
    for canary in plan.synthetic_secret_canaries:
        patterns.extend(canary._patterns())
    patterns.extend(plan.deterministic_audio_canary._patterns())
    if any(
        not 0 < len(pattern.value) <= MAX_CANARY_PATTERN_UNITS for pattern in patterns
    ):
        raise AlphaPrivacyConformanceViolation(
            "CANARY_LIMIT_EXCEEDED", "generated canary exceeds its overlap limit"
        )
    return tuple(patterns)


@dataclass(slots=True)
class _ScanStats:
    records: int = 0
    chunks: int = 0
    total_bytes: int = 0


def _record_findings(
    *,
    surface: AlphaPrivacySurface,
    value: str | bytes,
    patterns: tuple[_ExactPattern, ...],
    findings: dict[
        tuple[AlphaPrivacySurface, CanaryFamily, str], AlphaPrivacyCanaryFinding
    ],
) -> None:
    priority = {
        CanaryRepresentation.RAW_BYTES: 0,
        CanaryRepresentation.UTF8_TEXT: 1,
        CanaryRepresentation.UTF8_BYTES: 1,
        CanaryRepresentation.BASE64_TEXT: 2,
        CanaryRepresentation.BASE64_BYTES: 2,
    }
    for pattern in patterns:
        if type(pattern.value) is type(value) and pattern.value in value:
            key = (surface, pattern.family, pattern.classification)
            current = findings.get(key)
            if current is not None and (
                priority[current.representation] <= priority[pattern.representation]
            ):
                continue
            findings[key] = AlphaPrivacyCanaryFinding(
                surface=surface,
                family=pattern.family,
                classification=pattern.classification,
                representation=pattern.representation,
            )


def _scan_record(
    record: AlphaPrivacyCaptureRecord,
    *,
    surface: AlphaPrivacySurface,
    patterns: tuple[_ExactPattern, ...],
    findings: dict[
        tuple[AlphaPrivacySurface, CanaryFamily, str], AlphaPrivacyCanaryFinding
    ],
) -> None:
    matching_patterns = tuple(
        pattern
        for pattern in patterns
        if (record.chunk_kind is AlphaPrivacyChunkKind.TEXT)
        is (type(pattern.value) is str)
    )
    overlap_units = max(len(pattern.value) for pattern in matching_patterns) - 1
    rolling_tail: str | bytes = (
        "" if record.chunk_kind is AlphaPrivacyChunkKind.TEXT else b""
    )
    for chunk in record.chunks:
        window = rolling_tail + chunk
        _record_findings(
            surface=surface,
            value=window,
            patterns=matching_patterns,
            findings=findings,
        )
        rolling_tail = window[-overlap_units:] if overlap_units else window[:0]


def _disabled_report() -> AlphaPrivacyConformanceReport:
    return AlphaPrivacyConformanceReport(
        status=AlphaPrivacyConformanceStatus.DISABLED,
        declared_candidate_sha=None,
        declared_run_ref=None,
        declared_capture_source=None,
        evaluated_surfaces=(),
        missing_surfaces=(),
        duplicate_surfaces=(),
        incomplete_surfaces=(),
        binding_conflict_surfaces=(),
        capture_receipt_conflict_surfaces=(),
        findings=(),
        observations_examined=0,
        records_examined=0,
        chunks_examined=0,
        bytes_examined=0,
        declared_binding_consistent=False,
        capture_receipts_consistent=False,
        supplied_capture_coverage_complete=False,
        supplied_capture_exact_match_clear=False,
    )


def evaluate_alpha_privacy_conformance(
    *,
    enabled: bool,
    plan: AlphaPrivacyConformancePlan | None,
    observations: tuple[AlphaPrivacySurfaceObservation, ...] | object,
) -> AlphaPrivacyConformanceReport:
    """Check exact canaries across caller-supplied deep-immutable records."""

    if type(enabled) is not bool:
        raise AlphaPrivacyConformanceViolation(
            "INVALID_ENABLED_FLAG", "enabled must be one boolean"
        )
    if not enabled:
        return _disabled_report()
    if type(plan) is not AlphaPrivacyConformancePlan:
        raise AlphaPrivacyConformanceViolation(
            "INVALID_PLAN", "enabled conformance requires one exact immutable plan"
        )
    if type(observations) is not tuple:
        raise AlphaPrivacyConformanceViolation(
            "INVALID_OBSERVATIONS", "observations must be one immutable tuple"
        )
    if len(observations) > MAX_OBSERVATIONS:
        raise AlphaPrivacyConformanceViolation(
            "CAPTURE_LIMIT_EXCEEDED", "observation count exceeds its limit"
        )
    if any(type(item) is not AlphaPrivacySurfaceObservation for item in observations):
        raise AlphaPrivacyConformanceViolation(
            "INVALID_OBSERVATIONS", "every observation must use the exact capture type"
        )

    grouped: dict[AlphaPrivacySurface, list[AlphaPrivacySurfaceObservation]] = {}
    stats = _ScanStats()
    findings: dict[
        tuple[AlphaPrivacySurface, CanaryFamily, str], AlphaPrivacyCanaryFinding
    ] = {}
    exact_patterns = _patterns(plan)
    binding_conflicts: set[AlphaPrivacySurface] = set()
    receipt_conflicts: set[AlphaPrivacySurface] = set()
    incomplete: set[AlphaPrivacySurface] = set()

    for observation in observations:
        grouped.setdefault(observation.surface, []).append(observation)
        if not observation.capture_complete:
            incomplete.add(observation.surface)
        if (
            observation.declared_candidate_sha != plan.declared_candidate_sha
            or observation.declared_run_ref != plan.declared_run_ref
            or observation.declared_capture_source != plan.declared_capture_source
        ):
            binding_conflicts.add(observation.surface)
        expected_receipt = compute_alpha_privacy_capture_receipt(
            surface=observation.surface,
            declared_candidate_sha=observation.declared_candidate_sha,
            declared_run_ref=observation.declared_run_ref,
            declared_capture_source=observation.declared_capture_source,
            capture_complete=observation.capture_complete,
            records=observation.records,
        )
        if observation.capture_receipt != expected_receipt:
            receipt_conflicts.add(observation.surface)
        for record in observation.records:
            stats.records += 1
            stats.chunks += len(record.chunks)
            stats.total_bytes += record.total_bytes
            if stats.records > MAX_TOTAL_RECORDS:
                raise AlphaPrivacyConformanceViolation(
                    "CAPTURE_LIMIT_EXCEEDED", "total record count exceeds its limit"
                ) from None
            if stats.chunks > MAX_TOTAL_CHUNKS:
                raise AlphaPrivacyConformanceViolation(
                    "CAPTURE_LIMIT_EXCEEDED", "total chunk count exceeds its limit"
                ) from None
            if stats.total_bytes > MAX_TOTAL_BYTES:
                raise AlphaPrivacyConformanceViolation(
                    "CAPTURE_LIMIT_EXCEEDED",
                    "captured material exceeds its total byte limit",
                ) from None
            _scan_record(
                record,
                surface=observation.surface,
                patterns=exact_patterns,
                findings=findings,
            )

    evaluated = tuple(
        surface for surface in ALPHA_PRIVACY_SURFACES if surface in grouped
    )
    missing = tuple(
        surface for surface in ALPHA_PRIVACY_SURFACES if surface not in grouped
    )
    duplicates = tuple(
        surface
        for surface in ALPHA_PRIVACY_SURFACES
        if len(grouped.get(surface, ())) > 1
    )
    incomplete_surfaces = tuple(
        surface for surface in ALPHA_PRIVACY_SURFACES if surface in incomplete
    )
    conflict_surfaces = tuple(
        surface for surface in ALPHA_PRIVACY_SURFACES if surface in binding_conflicts
    )
    receipt_conflict_surfaces = tuple(
        surface for surface in ALPHA_PRIVACY_SURFACES if surface in receipt_conflicts
    )
    ordered_findings = tuple(
        sorted(
            findings.values(),
            key=lambda finding: (
                ALPHA_PRIVACY_SURFACES.index(finding.surface),
                finding.family.value,
                finding.classification,
            ),
        )
    )
    supplied_coverage_complete = not (
        missing
        or duplicates
        or incomplete_surfaces
        or conflict_surfaces
        or receipt_conflict_surfaces
    )
    supplied_exact_match_clear = supplied_coverage_complete and not ordered_findings
    if ordered_findings:
        status = AlphaPrivacyConformanceStatus.LEAK_DETECTED
    elif not supplied_coverage_complete:
        status = AlphaPrivacyConformanceStatus.INCOMPLETE
    else:
        status = AlphaPrivacyConformanceStatus.SUPPLIED_CAPTURE_EXACT_MATCH_CLEAR

    return AlphaPrivacyConformanceReport(
        status=status,
        declared_candidate_sha=plan.declared_candidate_sha,
        declared_run_ref=plan.declared_run_ref,
        declared_capture_source=plan.declared_capture_source,
        evaluated_surfaces=evaluated,
        missing_surfaces=missing,
        duplicate_surfaces=duplicates,
        incomplete_surfaces=incomplete_surfaces,
        binding_conflict_surfaces=conflict_surfaces,
        capture_receipt_conflict_surfaces=receipt_conflict_surfaces,
        findings=ordered_findings,
        observations_examined=len(observations),
        records_examined=stats.records,
        chunks_examined=stats.chunks,
        bytes_examined=stats.total_bytes,
        declared_binding_consistent=not conflict_surfaces,
        capture_receipts_consistent=not receipt_conflict_surfaces,
        supplied_capture_coverage_complete=supplied_coverage_complete,
        supplied_capture_exact_match_clear=supplied_exact_match_clear,
    )


__all__ = [
    "ALPHA_PRIVACY_SURFACES",
    "MAX_BYTES_PER_OBSERVATION",
    "MAX_CANARY_PATTERN_UNITS",
    "MAX_CHUNKS_PER_OBSERVATION",
    "MAX_CHUNKS_PER_RECORD",
    "MAX_CHUNK_BYTES",
    "MAX_BOUNDED_TEXT_ENCODE_BYTES",
    "MAX_OBSERVATIONS",
    "MAX_RECORDS_PER_OBSERVATION",
    "MAX_RECORD_BYTES",
    "MAX_TOTAL_BYTES",
    "MAX_TOTAL_CHUNKS",
    "MAX_TOTAL_RECORDS",
    "AlphaPrivacyCanaryFinding",
    "AlphaPrivacyCaptureRecord",
    "AlphaPrivacyCaptureRecordBuildResult",
    "AlphaPrivacyCaptureSource",
    "AlphaPrivacyChunkKind",
    "AlphaPrivacyConformancePlan",
    "AlphaPrivacyConformanceReport",
    "AlphaPrivacyConformanceStatus",
    "AlphaPrivacyConformanceViolation",
    "AlphaPrivacySurface",
    "AlphaPrivacySurfaceObservation",
    "AlphaPrivacyRecordBuildReason",
    "CanaryFamily",
    "CanaryRepresentation",
    "DeterministicAudioByteCanary",
    "SyntheticSecretCanary",
    "SyntheticSecretKind",
    "build_alpha_privacy_capture_record",
    "compute_alpha_privacy_capture_receipt",
    "evaluate_alpha_privacy_conformance",
]
