# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Explicit local JSONL sink for sanitized W2 observability evidence.

The sink accepts only the closed public X-OBS schemas, writes no raw audio or
free-form product content, and has no business authority.  It is a controlled
localhost evidence sink, not a production telemetry or durability backend.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from threading import Lock
from typing import Final

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from jiuwenswarm.server.live_voice.observability import (
    LiveVoiceMetric,
    LiveVoiceObservation,
    create_metric,
    create_observation,
)
from jiuwenswarm.server.live_voice.observability_exporter import (
    ExportRecord,
    mark_current_export_committed,
)


DEFAULT_W2_EVIDENCE_MAX_RECORDS: Final = 100_000
MAX_W2_EVIDENCE_RECORDS: Final = 1_000_000
_BOUND_LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}$")


@dataclass(frozen=True, slots=True)
class W2EvidenceRunBinding:
    candidate_sha: str
    environment_id: str
    session_id: str
    mode_id: str
    evidence_set_id: str
    artifact_id: str
    artifact_sequence: int
    producer_id: str
    process_epoch: str
    repository_path: str
    predecessor_artifact_id: str | None = None

    def __post_init__(self) -> None:
        if re.fullmatch(r"[0-9a-f]{40}", self.candidate_sha) is None:
            raise ValueError("W2 evidence candidate_sha must be a full Git SHA")
        for field_name in (
            "environment_id",
            "session_id",
            "mode_id",
            "evidence_set_id",
            "artifact_id",
            "producer_id",
            "process_epoch",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or _BOUND_LABEL.fullmatch(value) is None:
                raise ValueError(f"W2 evidence {field_name} is invalid")
        if type(self.artifact_sequence) is not int or self.artifact_sequence <= 0:
            raise ValueError("W2 evidence artifact_sequence must be positive")
        repository = Path(self.repository_path)
        if not repository.is_absolute():
            raise ValueError("W2 evidence repository_path must be absolute")
        if self.predecessor_artifact_id is not None and (
            not isinstance(self.predecessor_artifact_id, str)
            or _BOUND_LABEL.fullmatch(self.predecessor_artifact_id) is None
            or self.predecessor_artifact_id == self.artifact_id
        ):
            raise ValueError("W2 evidence predecessor_artifact_id is invalid")


class W2EvidenceExporterError(RuntimeError):
    """Base class for stable local evidence sink failures."""


class W2EvidenceCapacityError(W2EvidenceExporterError):
    """The fixed non-evicting evidence record limit has been reached."""


class W2EvidenceRecordError(W2EvidenceExporterError, TypeError):
    """The sink received something outside the exact public schemas."""


class W2EvidenceSealedError(W2EvidenceExporterError):
    """A closed evidence artifact cannot accept additional records."""


def verify_w2_candidate_checkout(
    *,
    repository_path: object,
    candidate_sha: object,
    bind_loaded_source: bool = False,
) -> str:
    """Bind an enabled evidence run to one clean, exact local Git checkout."""

    if not isinstance(repository_path, (str, os.PathLike)):
        raise ValueError("W2 candidate repository path is required")
    repository = Path(repository_path).resolve()
    if not repository.is_absolute() or not repository.is_dir():
        raise ValueError("W2 candidate repository must be an existing absolute path")
    expected_sha = str(candidate_sha or "")
    if re.fullmatch(r"[0-9a-f]{40}", expected_sha) is None:
        raise ValueError("W2 candidate_sha must be a full Git SHA")
    try:
        if bind_loaded_source:
            loaded_root = subprocess.run(
                [
                    "git",
                    "-C",
                    str(Path(__file__).resolve().parent),
                    "rev-parse",
                    "--show-toplevel",
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            ).stdout.strip()
            if Path(loaded_root).resolve() != repository:
                raise W2EvidenceExporterError(
                    "W2 candidate repository differs from the loaded source tree"
                )
        head = subprocess.run(
            ["git", "-C", str(repository), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()
        status = subprocess.run(
            [
                "git",
                "-C",
                str(repository),
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        raise W2EvidenceExporterError(
            "W2 candidate Git checkout could not be verified"
        ) from exc
    if head != expected_sha:
        raise W2EvidenceExporterError(
            "W2 candidate SHA does not match the checked-out Git HEAD"
        )
    if status:
        raise W2EvidenceExporterError(
            "W2 candidate checkout must be clean before evidence capture"
        )
    return head


class _WriteAttemptState(StrEnum):
    PREPARING = "preparing"
    CANCELLED = "cancelled"
    COMMITTING = "committing"
    COMMITTED = "committed"
    FAILED = "failed"


class _WriteAttempt:
    """Thread-safe cancellation/commit handshake for one filesystem effect."""

    __slots__ = ("_lock", "_state")

    def __init__(self) -> None:
        self._lock = Lock()
        self._state = _WriteAttemptState.PREPARING

    def request_cancel(self) -> _WriteAttemptState:
        with self._lock:
            if self._state is _WriteAttemptState.PREPARING:
                self._state = _WriteAttemptState.CANCELLED
            return self._state

    def begin_commit(self) -> bool:
        with self._lock:
            if self._state is _WriteAttemptState.CANCELLED:
                return False
            if self._state is not _WriteAttemptState.PREPARING:
                raise RuntimeError("evidence write attempt entered commit twice")
            self._state = _WriteAttemptState.COMMITTING
            return True

    def committed(self) -> None:
        with self._lock:
            if self._state is not _WriteAttemptState.COMMITTING:
                raise RuntimeError("evidence write attempt committed out of order")
            self._state = _WriteAttemptState.COMMITTED

    def failed(self) -> None:
        with self._lock:
            if self._state is _WriteAttemptState.COMMITTING:
                self._state = _WriteAttemptState.FAILED


@dataclass(frozen=True, slots=True)
class W2EvidenceExporterSnapshot:
    enabled: bool
    accepted_records: int
    accepted_observations: int
    accepted_metrics: int
    rejected_invalid: int
    rejected_capacity: int
    failed_writes: int = 0
    sealed: bool = False
    business_result_changed: bool = False
    lifecycle_authority_exercised: bool = False
    cancel_authority_exercised: bool = False
    success_authority_exercised: bool = False

    def __post_init__(self) -> None:
        if any(
            (
                self.business_result_changed,
                self.lifecycle_authority_exercised,
                self.cancel_authority_exercised,
                self.success_authority_exercised,
            )
        ):
            raise ValueError("W2 evidence export has no business authority")


class DisabledW2EvidenceExporter:
    """Singleton feature-off value with no path inspection or filesystem effect."""

    __slots__ = ()
    enabled = False
    exporter = None

    def snapshot(self) -> W2EvidenceExporterSnapshot:
        return W2EvidenceExporterSnapshot(
            enabled=False,
            accepted_records=0,
            accepted_observations=0,
            accepted_metrics=0,
            rejected_invalid=0,
            rejected_capacity=0,
        )


class W2JsonlEvidenceExporter:
    """Serialized async appender for exact public observation and metric records."""

    __slots__ = (
        "_accepted_metrics",
        "_accepted_observations",
        "_lock",
        "_failed_writes",
        "_max_records",
        "_path",
        "_rejected_capacity",
        "_rejected_invalid",
        "_run_binding",
        "_sealed",
        "_footer_written",
        "_signing_private_key",
        "_signature_path",
    )
    enabled = True

    def __init__(
        self,
        *,
        path: Path,
        max_records: int,
        run_binding: W2EvidenceRunBinding,
        signing_private_key: bytes | None,
        signature_path: Path | None,
        _construction_token: object,
    ) -> None:
        if _construction_token is not _CONSTRUCTION_TOKEN:
            raise ValueError("use create_w2_evidence_exporter")
        self._path = path
        self._max_records = max_records
        self._run_binding = run_binding
        self._signing_private_key = signing_private_key
        self._signature_path = signature_path
        self._lock = Lock()
        self._accepted_observations = 0
        self._accepted_metrics = 0
        self._rejected_invalid = 0
        self._rejected_capacity = 0
        self._failed_writes = 0
        self._sealed = False
        self._footer_written = False

    @property
    def exporter(self) -> W2JsonlEvidenceExporter:
        """Return the native async callable expected by the product Adapter."""

        return self

    async def __call__(self, record: ExportRecord) -> None:
        kind, payload = self._validated_payload(record)
        attempt = _WriteAttempt()
        retained = asyncio.create_task(
            asyncio.to_thread(self._append, attempt, kind, payload),
            name="live-voice-w2-evidence-write",
        )
        try:
            committed = await asyncio.shield(retained)
            if committed:
                mark_current_export_committed()
            return
        except asyncio.CancelledError:
            state = attempt.request_cancel()
            while not retained.done():
                try:
                    await asyncio.shield(retained)
                except asyncio.CancelledError:
                    state = attempt.request_cancel()
            # Once the append entered its commit section, cancellation is
            # deferred and suppressed so callers cannot report failure while
            # the candidate artifact was durably written.  Before commit,
            # cancellation wins and the thread performs no filesystem effect.
            if retained.cancelled():
                raise
            error = retained.exception()
            if error is not None:
                with self._lock:
                    self._failed_writes += 1
                raise error
            if retained.result() is True:
                mark_current_export_committed()
                return
            assert state is _WriteAttemptState.CANCELLED
            raise
        except Exception:
            with self._lock:
                self._failed_writes += 1
            raise

    def snapshot(self) -> W2EvidenceExporterSnapshot:
        with self._lock:
            observations = self._accepted_observations
            metrics = self._accepted_metrics
            rejected_invalid = self._rejected_invalid
            rejected_capacity = self._rejected_capacity
            failed_writes = self._failed_writes
        return W2EvidenceExporterSnapshot(
            enabled=True,
            accepted_records=observations + metrics,
            accepted_observations=observations,
            accepted_metrics=metrics,
            rejected_invalid=rejected_invalid,
            rejected_capacity=rejected_capacity,
            failed_writes=failed_writes,
            sealed=self._sealed,
        )

    async def seal(self) -> None:
        """Durably close the raw artifact with exact exporter counters."""

        await asyncio.to_thread(self._seal)

    def _validated_payload(self, record: object) -> tuple[str, dict[str, object]]:
        try:
            if type(record) is LiveVoiceObservation:
                validated = create_observation(record)
                return "observation", validated.to_dict()
            if type(record) is LiveVoiceMetric:
                validated = create_metric(record)
                return "metric", validated.to_dict()
        except Exception as exc:
            with self._lock:
                self._rejected_invalid += 1
            raise W2EvidenceRecordError("invalid public evidence record") from exc
        with self._lock:
            self._rejected_invalid += 1
        raise W2EvidenceRecordError("unsupported public evidence record")

    def _append(
        self,
        attempt: _WriteAttempt,
        kind: str,
        payload: dict[str, object],
    ) -> bool:
        with self._lock:
            if self._sealed:
                raise W2EvidenceSealedError("W2 evidence artifact is already sealed")
            if not attempt.begin_commit():
                return False
            try:
                sequence = self._accepted_observations + self._accepted_metrics
                if sequence >= self._max_records:
                    self._rejected_capacity += 1
                    raise W2EvidenceCapacityError(
                        "W2 evidence record capacity has been reached"
                    )
                envelope = {
                    "evidence_schema": "live-voice.w2-jsonl-evidence.v2",
                    "candidate": {
                        "candidate_sha": self._run_binding.candidate_sha,
                        "environment_id": self._run_binding.environment_id,
                        "session_id": self._run_binding.session_id,
                        "mode_id": self._run_binding.mode_id,
                    },
                    "record_kind": kind,
                    "sequence": sequence,
                    "record": payload,
                }
                encoded = json.dumps(
                    envelope,
                    ensure_ascii=True,
                    allow_nan=False,
                    separators=(",", ":"),
                    sort_keys=True,
                )
                mode = "x" if sequence == 0 else "a"
                with self._path.open(mode, encoding="utf-8", newline="\n") as stream:
                    if sequence == 0:
                        stream.write(self._encoded_header())
                        stream.write("\n")
                    stream.write(encoded)
                    stream.write("\n")
                    stream.flush()
                    os.fsync(stream.fileno())
            except OSError as exc:
                attempt.failed()
                raise W2EvidenceExporterError(
                    "W2 evidence sink is unavailable"
                ) from exc
            except BaseException:
                attempt.failed()
                raise
            if kind == "observation":
                self._accepted_observations += 1
            else:
                self._accepted_metrics += 1
            attempt.committed()
            return True

    def _encoded_header(self) -> str:
        return json.dumps(
            {
                "evidence_schema": "live-voice.w2-jsonl-evidence.v2",
                "record_kind": "header",
                "evidence_set_id": self._run_binding.evidence_set_id,
                "artifact_id": self._run_binding.artifact_id,
                "artifact_sequence": self._run_binding.artifact_sequence,
                "producer_id": self._run_binding.producer_id,
                "process_epoch": self._run_binding.process_epoch,
                "predecessor_artifact_id": (
                    self._run_binding.predecessor_artifact_id
                ),
                "repository_path": self._run_binding.repository_path,
                "candidate": {
                    "candidate_sha": self._run_binding.candidate_sha,
                    "environment_id": self._run_binding.environment_id,
                    "session_id": self._run_binding.session_id,
                    "mode_id": self._run_binding.mode_id,
                },
            },
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )

    def _seal(self) -> None:
        with self._lock:
            if self._sealed:
                return
            footer = json.dumps(
                {
                    "evidence_schema": "live-voice.w2-jsonl-evidence.v2",
                    "record_kind": "footer",
                    "artifact_id": self._run_binding.artifact_id,
                    "record_count": (
                        self._accepted_observations + self._accepted_metrics
                    ),
                    "last_sequence": (
                        self._accepted_observations + self._accepted_metrics - 1
                    ),
                    "accepted_observations": self._accepted_observations,
                    "accepted_metrics": self._accepted_metrics,
                    "rejected_invalid": self._rejected_invalid,
                    "rejected_capacity": self._rejected_capacity,
                    "failed_writes": self._failed_writes,
                    "closed": True,
                },
                ensure_ascii=True,
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            if not self._footer_written:
                mode = "a" if self._path.exists() else "x"
                try:
                    with self._path.open(
                        mode, encoding="utf-8", newline="\n"
                    ) as stream:
                        if mode == "x":
                            stream.write(self._encoded_header())
                            stream.write("\n")
                        stream.write(footer)
                        stream.write("\n")
                        stream.flush()
                        os.fsync(stream.fileno())
                except OSError as exc:
                    raise W2EvidenceExporterError(
                        "W2 evidence artifact could not be sealed"
                    ) from exc
                self._footer_written = True
            if self._signing_private_key is not None:
                assert self._signature_path is not None
                content = self._path.read_bytes()
                signature_header = json.dumps(
                    {
                        "schema": "live-voice.w2-artifact-signature.v1",
                        "kind": "runtime_jsonl",
                        "artifact_id": self._run_binding.artifact_id,
                        "sequence": self._run_binding.artifact_sequence,
                        "source_label": None,
                        "content_sha256": hashlib.sha256(content).hexdigest(),
                    },
                    ensure_ascii=True,
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode("ascii") + b"\n"
                signature = Ed25519PrivateKey.from_private_bytes(
                    self._signing_private_key
                ).sign(signature_header)
                try:
                    descriptor = os.open(
                        self._signature_path,
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                        0o600,
                    )
                    with os.fdopen(
                        descriptor, "w", encoding="ascii", newline="\n"
                    ) as stream:
                        stream.write(signature.hex())
                        stream.write("\n")
                        stream.flush()
                        os.fsync(stream.fileno())
                except OSError as exc:
                    raise W2EvidenceExporterError(
                        "W2 producer signature could not be sealed"
                    ) from exc
            self._sealed = True


_CONSTRUCTION_TOKEN = object()
_DISABLED_EXPORTER = DisabledW2EvidenceExporter()


def create_w2_evidence_exporter(
    *,
    enabled: bool = False,
    path: object = None,
    max_records: int = DEFAULT_W2_EVIDENCE_MAX_RECORDS,
    candidate_sha: object = None,
    environment_id: object = None,
    session_id: object = None,
    mode_id: object = None,
    evidence_set_id: object = None,
    artifact_id: object = None,
    artifact_sequence: object = None,
    producer_id: object = None,
    process_epoch: object = None,
    predecessor_artifact_id: object = None,
    repository_path: object = None,
    signing_private_key_path: object = None,
    signature_path: object = None,
) -> DisabledW2EvidenceExporter | W2JsonlEvidenceExporter:
    """Create a local sink only after an explicit feature-on decision."""

    if enabled is not True:
        return _DISABLED_EXPORTER
    if not isinstance(path, (str, os.PathLike)):
        raise ValueError("enabled W2 evidence export requires an exact path")
    evidence_path = Path(path)
    if not evidence_path.is_absolute() or evidence_path.name in {"", ".", ".."}:
        raise ValueError("W2 evidence path must be an absolute file path")
    if not evidence_path.parent.is_dir():
        raise ValueError("W2 evidence parent directory must already exist")
    if evidence_path.exists():
        if not evidence_path.is_file():
            raise ValueError("W2 evidence path must identify a regular file")
        raise ValueError("W2 evidence path must be new for this candidate run")
    signing_private_key: bytes | None = None
    resolved_signature_path: Path | None = None
    if (signing_private_key_path is None) is not (signature_path is None):
        raise ValueError("W2 producer signing inputs must be supplied together")
    if signing_private_key_path is not None:
        private_path = Path(signing_private_key_path)
        resolved_signature_path = Path(signature_path)
        if (
            not private_path.is_absolute()
            or not private_path.is_file()
            or not resolved_signature_path.is_absolute()
            or not resolved_signature_path.parent.is_dir()
            or resolved_signature_path.exists()
        ):
            raise ValueError("W2 producer signing paths are invalid")
        private_hex = private_path.read_text(encoding="ascii").strip()
        if re.fullmatch(r"[0-9a-f]{64}", private_hex) is None:
            raise ValueError("W2 producer private key is invalid")
        signing_private_key = bytes.fromhex(private_hex)
    run_binding = W2EvidenceRunBinding(
        candidate_sha=str(candidate_sha or ""),
        environment_id=str(environment_id or ""),
        session_id=str(session_id or ""),
        mode_id=str(mode_id or ""),
        evidence_set_id=str(evidence_set_id or ""),
        artifact_id=str(artifact_id or ""),
        artifact_sequence=artifact_sequence,  # type: ignore[arg-type]
        producer_id=str(producer_id or ""),
        process_epoch=str(process_epoch or ""),
        repository_path=str(
            Path(
                repository_path
                if repository_path is not None
                else Path(__file__).resolve().parents[3]
            ).resolve()
        ),
        predecessor_artifact_id=(
            None
            if predecessor_artifact_id in {None, ""}
            else str(predecessor_artifact_id)
        ),
    )
    if (
        type(max_records) is not int
        or max_records <= 0
        or max_records > MAX_W2_EVIDENCE_RECORDS
    ):
        raise ValueError(f"max_records must be between 1 and {MAX_W2_EVIDENCE_RECORDS}")
    return W2JsonlEvidenceExporter(
        path=evidence_path,
        max_records=max_records,
        run_binding=run_binding,
        signing_private_key=signing_private_key,
        signature_path=resolved_signature_path,
        _construction_token=_CONSTRUCTION_TOKEN,
    )


__all__ = [
    "DEFAULT_W2_EVIDENCE_MAX_RECORDS",
    "MAX_W2_EVIDENCE_RECORDS",
    "DisabledW2EvidenceExporter",
    "W2EvidenceCapacityError",
    "W2EvidenceExporterError",
    "W2EvidenceExporterSnapshot",
    "W2EvidenceRecordError",
    "W2EvidenceSealedError",
    "W2EvidenceRunBinding",
    "W2JsonlEvidenceExporter",
    "create_w2_evidence_exporter",
    "verify_w2_candidate_checkout",
]
