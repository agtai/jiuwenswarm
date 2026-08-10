# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Fail-closed evaluator for one immutable W2 Integrated Demo record.

The evaluator never manufactures evidence or exercises product authority.  It
only relates bounded, candidate-bound artifacts to the immutable W2 ledger,
Gate 1 verification, invariants, showcase runs, faults, and recovery record.
"""

from __future__ import annotations

from collections.abc import Callable, Hashable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
import hashlib
import hmac
import json
from pathlib import Path
import re
import secrets
from types import MappingProxyType
from typing import Final, TypeVar

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from jiuwenswarm.server.live_voice.observability import (
    LiveVoiceObservation,
    create_metric,
    create_observation,
)
from jiuwenswarm.server.live_voice.w2_fault_plan import (
    W2FaultClass as W2PlannedFaultClass,
    W2FaultPlane as W2PlannedFaultPlane,
    derive_w2_product_fault_plan,
)


class W2GateContractViolation(ValueError):
    """Raised when a supplied record is structurally unsafe or contradictory."""


_T = TypeVar("_T")
_K = TypeVar("_K", bound=Hashable)
_RESULT_CONSTRUCTION_TOKEN = object()
_ARTIFACT_CONSTRUCTION_TOKEN = object()
_ARTIFACT_ATTESTATION_KEY = secrets.token_bytes(32)
MAX_W2_GATE_RECORDS: Final = 4_096
MAX_W2_EVIDENCE_IDS: Final = 64
MAX_W2_PROVIDER_LABELS: Final = 16
_MAX_LABEL_CHARACTERS: Final = 256
_MAX_LABEL_UTF8_BYTES: Final = 1_024
_MAX_PATH_CHARACTERS: Final = 4_096
_MAX_PATH_UTF8_BYTES: Final = 16_384
MAX_W2_ARTIFACT_BYTES: Final = 32 * 1024 * 1024
_SENSITIVE_MARKER = re.compile(
    r"(?:^|[._:@-])(?:api[-_]?key|access[-_]?token|authorization|bearer|password|"
    r"passwd|secret|credential|transcript|raw[-_]?audio|audio[-_]?bytes|"
    r"data[-_]?base64)(?:$|[=._:@-])",
    re.IGNORECASE,
)


class W2GateStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"


class W2Section(StrEnum):
    P1 = "p1"
    P2 = "p2"
    P3 = "p3alpha"
    CROSS_CUTTING = "cross_cutting"


class W2LedgerItem(StrEnum):
    P1_AUDIO = "p1.audio_capture_playout"
    P1_RECOGNITION = "p1.recognition_port_adapter"
    P1_SYNTHESIS = "p1.synthesis_port_adapter"
    P1_COMMIT_DEGRADATION = "p1.commit_clarification_text_degradation"
    P2_RUNTIME = "p2.runtime_identity_lifecycle_fence"
    P2_MEDIA = "p2.realtime_media"
    P2_ENGINE = "p2.interaction_engine"
    P2_AGENT = "p2.agent_bridge"
    P2_PRESENTATION = "p2.presentation_history_truth"
    P3_CORE = "p3.core_ledger_event_truth"
    P3_EXECUTOR = "p3.d0_executor"
    P3_VOICE_BRIDGE = "p3.voice_task_bridge"
    P3_PROGRESS = "p3.progress_result_return"
    P3_UI = "p3.ui_control_integration"
    CROSS_ROUTE = "cross.route_telemetry"
    CROSS_CONTEXT = "cross.context"
    CROSS_FAILURE = "cross.failure_degradation"
    CROSS_OBSERVABILITY = "cross.observability_fault_injection"
    CROSS_FLAG_OFF = "cross.feature_off_text_regression"


class W2Invariant(StrEnum):
    COMMITTED_ONLY = "committed_only"
    AT_MOST_ONCE = "at_most_once"
    STALE_EFFECT_ZERO = "stale_effect_zero"
    CANCEL_SCOPE_EXACT = "cancel_scope_exact"
    AUTHORITY_FAILS_CLOSED = "authority_fails_closed"
    NONTERMINAL_TRUTH = "nonterminal_truth"
    DESTRUCTIVE_CONFIRMATION = "destructive_confirmation"
    FEATURE_OFF_ZERO_EFFECT = "feature_off_zero_effect"
    CLAIM_TRUTH = "claim_truth"
    EXIT_CLOSES_LOCAL_EFFECTS = "exit_closes_local_effects"


class W2EvidenceKind(StrEnum):
    REAL_RUNTIME = "real_runtime"
    AUTOMATED_CONFORMANCE = "automated_conformance"
    INDEPENDENT_REVIEW = "independent_review"
    FAULT_INJECTION = "fault_injection"
    HUMAN_OBSERVATION = "human_observation"


@dataclass(frozen=True, slots=True)
class W2RuntimeArtifactSlot:
    """Root-authorized identity for one required v2 runtime artifact."""

    artifact_id: str
    artifact_sequence: int
    producer_id: str
    process_epoch: str
    predecessor_artifact_id: str | None
    showcase_run: int | None

    def __post_init__(self) -> None:
        _required_text(self.artifact_id, "runtime slot artifact_id")
        if type(self.artifact_sequence) is not int or self.artifact_sequence <= 0:
            raise W2GateContractViolation(
                "runtime slot artifact_sequence must be positive"
            )
        if self.producer_id not in {"gateway", "agentserver"}:
            raise W2GateContractViolation("runtime slot producer_id is invalid")
        _required_text(self.process_epoch, "runtime slot process_epoch")
        if self.predecessor_artifact_id is not None:
            _required_text(
                self.predecessor_artifact_id,
                "runtime slot predecessor_artifact_id",
            )
            if self.predecessor_artifact_id == self.artifact_id:
                raise W2GateContractViolation(
                    "runtime slot cannot be its own predecessor"
                )
        if self.showcase_run is not None and self.showcase_run not in {1, 2, 3}:
            raise W2GateContractViolation("runtime slot showcase_run is invalid")


@dataclass(frozen=True, slots=True)
class W2EvidenceArtifactSlot:
    """One root-authorized artifact in the closed W2 attempt plan."""

    artifact_id: str
    artifact_sequence: int
    evidence_kind: W2EvidenceKind
    signer_id: str
    source_label: str | None = None
    expected_subjects: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _required_text(self.artifact_id, "artifact slot artifact_id")
        if type(self.artifact_sequence) is not int or self.artifact_sequence <= 0:
            raise W2GateContractViolation(
                "artifact slot artifact_sequence must be positive"
            )
        if not isinstance(self.evidence_kind, W2EvidenceKind):
            raise W2GateContractViolation("artifact slot evidence_kind is invalid")
        _required_text(self.signer_id, "artifact slot signer_id")
        if self.evidence_kind is W2EvidenceKind.AUTOMATED_CONFORMANCE:
            _required_text(self.source_label, "artifact slot source_label")
        elif self.source_label is not None:
            raise W2GateContractViolation(
                "only automated artifact slots have a source_label"
            )
        if (
            not self.expected_subjects
            or type(self.expected_subjects) is not tuple
            or any(
                not isinstance(subject, str) or not subject
                for subject in self.expected_subjects
            )
        ):
            raise W2GateContractViolation(
                "artifact slot must predeclare non-empty exact subjects"
            )
        if len(set(self.expected_subjects)) != len(self.expected_subjects):
            raise W2GateContractViolation("artifact slot subjects contain duplicates")


@dataclass(frozen=True, slots=True)
class W2EvidenceTrustPolicy:
    """Pinned external signer roots; private signing keys never enter Gate."""

    public_keys: Mapping[str, bytes]
    signer_roles: Mapping[str, frozenset[W2EvidenceKind]]
    principal_ids: Mapping[str, str] | None = None
    producer_ids: Mapping[str, str | None] | None = None
    candidate_binding: tuple[str, str, str, str] | None = None
    evidence_set_id: str | None = None
    runtime_slots: tuple[W2RuntimeArtifactSlot, ...] = ()
    artifact_slots: tuple[W2EvidenceArtifactSlot, ...] = ()
    policy_id: str | None = None
    repository_path: str | None = None

    def __post_init__(self) -> None:
        if not self.public_keys or set(self.public_keys) != set(self.signer_roles):
            raise W2GateContractViolation("trusted signer roots are incomplete")
        keys: dict[str, bytes] = {}
        roles: dict[str, frozenset[W2EvidenceKind]] = {}
        raw_principals = self.principal_ids or {
            signer_id: signer_id for signer_id in self.public_keys
        }
        raw_producers = self.producer_ids or {
            signer_id: (
                signer_id
                if W2EvidenceKind.REAL_RUNTIME
                in self.signer_roles.get(signer_id, frozenset())
                else None
            )
            for signer_id in self.public_keys
        }
        if set(raw_principals) != set(self.public_keys) or set(raw_producers) != set(
            self.public_keys
        ):
            raise W2GateContractViolation("trusted signer identities are incomplete")
        principals: dict[str, str] = {}
        producers: dict[str, str | None] = {}
        for signer_id, raw_key in self.public_keys.items():
            _required_text(signer_id, "trusted signer_id")
            if type(raw_key) is not bytes or len(raw_key) != 32:
                raise W2GateContractViolation("trusted Ed25519 key is invalid")
            role_set = self.signer_roles[signer_id]
            if (
                type(role_set) is not frozenset
                or len(role_set) != 1
                or any(not isinstance(role, W2EvidenceKind) for role in role_set)
            ):
                raise W2GateContractViolation(
                    "each trusted signer must own exactly one evidence role"
                )
            try:
                Ed25519PublicKey.from_public_bytes(raw_key)
            except ValueError as exc:
                raise W2GateContractViolation("trusted Ed25519 key is invalid") from exc
            keys[signer_id] = bytes(raw_key)
            roles[signer_id] = frozenset(role_set)
            principals[signer_id] = _required_text(
                raw_principals[signer_id], "trusted principal_id"
            )
            producer_id = raw_producers[signer_id]
            if producer_id is not None:
                producer_id = _required_text(producer_id, "trusted runtime producer_id")
            if (W2EvidenceKind.REAL_RUNTIME in role_set) is not (
                producer_id is not None
            ):
                raise W2GateContractViolation(
                    "only runtime signers require one exact producer_id"
                )
            producers[signer_id] = producer_id
        if len(set(keys.values())) != len(keys):
            raise W2GateContractViolation(
                "trusted evidence roles must use distinct public keys"
            )
        if len(set(principals.values())) != len(principals):
            raise W2GateContractViolation(
                "trusted evidence roles must use distinct principals"
            )
        if set(role for role_set in roles.values() for role in role_set) != set(
            W2EvidenceKind
        ):
            raise W2GateContractViolation(
                "trusted signer roots must cover every evidence role"
            )
        scope_present = (
            self.candidate_binding is not None
            or self.evidence_set_id is not None
            or bool(self.runtime_slots)
            or bool(self.artifact_slots)
            or self.policy_id is not None
            or self.repository_path is not None
        )
        if scope_present:
            if (
                type(self.candidate_binding) is not tuple
                or len(self.candidate_binding) != 4
                or self.evidence_set_id is None
                or type(self.runtime_slots) is not tuple
                or not self.runtime_slots
                or type(self.artifact_slots) is not tuple
                or not self.artifact_slots
                or self.policy_id is None
                or self.repository_path is None
                or any(
                    type(slot) is not W2RuntimeArtifactSlot
                    for slot in self.runtime_slots
                )
                or any(
                    type(slot) is not W2EvidenceArtifactSlot
                    for slot in self.artifact_slots
                )
            ):
                raise W2GateContractViolation(
                    "root-authorized evidence scope is incomplete"
                )
            candidate_sha, environment_id, session_id, mode_id = self.candidate_binding
            if re.fullmatch(r"[0-9a-f]{40}", candidate_sha) is None:
                raise W2GateContractViolation(
                    "root-authorized candidate SHA is invalid"
                )
            for value, label in (
                (environment_id, "environment_id"),
                (session_id, "session_id"),
                (mode_id, "mode_id"),
                (self.evidence_set_id, "evidence_set_id"),
                (self.policy_id, "policy_id"),
            ):
                _required_text(value, f"root-authorized {label}")
            _required_absolute_path(
                self.repository_path, "root-authorized repository_path"
            )
            artifact_ids = [slot.artifact_id for slot in self.runtime_slots]
            sequences = [slot.artifact_sequence for slot in self.runtime_slots]
            if len(artifact_ids) != len(set(artifact_ids)) or len(sequences) != len(
                set(sequences)
            ):
                raise W2GateContractViolation(
                    "root-authorized runtime slots contain duplicate identity"
                )
            planned_ids = [slot.artifact_id for slot in self.artifact_slots]
            planned_sequences = [slot.artifact_sequence for slot in self.artifact_slots]
            if len(planned_ids) != len(set(planned_ids)) or len(
                planned_sequences
            ) != len(set(planned_sequences)):
                raise W2GateContractViolation(
                    "root-authorized artifact plan contains duplicate identity"
                )
            for slot in self.artifact_slots:
                expected_roles = roles.get(slot.signer_id)
                if expected_roles != frozenset({slot.evidence_kind}):
                    raise W2GateContractViolation(
                        "artifact slot signer does not own its evidence role"
                    )
            runtime_plan = {
                (slot.artifact_id, slot.artifact_sequence)
                for slot in self.artifact_slots
                if slot.evidence_kind is W2EvidenceKind.REAL_RUNTIME
            }
            runtime_scope = {
                (slot.artifact_id, slot.artifact_sequence)
                for slot in self.runtime_slots
            }
            if runtime_plan != runtime_scope:
                raise W2GateContractViolation(
                    "runtime slots differ from the closed artifact plan"
                )
            slots_by_id = {slot.artifact_id: slot for slot in self.runtime_slots}
            for slot in self.runtime_slots:
                predecessor_id = slot.predecessor_artifact_id
                if predecessor_id is None:
                    continue
                predecessor = slots_by_id.get(predecessor_id)
                if (
                    predecessor is None
                    or predecessor.producer_id != slot.producer_id
                    or predecessor.artifact_sequence >= slot.artifact_sequence
                    or predecessor.process_epoch == slot.process_epoch
                ):
                    raise W2GateContractViolation(
                        "root-authorized runtime predecessor is invalid"
                    )
            slot_producers = {slot.producer_id for slot in self.runtime_slots}
            trusted_producers = {
                producer_id for producer_id in producers.values() if producer_id
            }
            if slot_producers != {"gateway", "agentserver"} or not (
                slot_producers <= trusted_producers
            ):
                raise W2GateContractViolation(
                    "root-authorized scope lacks trusted runtime producers"
                )
            showcase_slots = [
                slot for slot in self.runtime_slots if slot.showcase_run is not None
            ]
            if {slot.showcase_run for slot in showcase_slots} != {1, 2, 3} or any(
                {
                    slot.producer_id
                    for slot in showcase_slots
                    if slot.showcase_run == run
                }
                != {"gateway", "agentserver"}
                for run in (1, 2, 3)
            ):
                raise W2GateContractViolation(
                    "root-authorized scope must bind both producers to three showcases"
                )
            run_sequences = {
                run: [
                    slot.artifact_sequence
                    for slot in showcase_slots
                    if slot.showcase_run == run
                ]
                for run in (1, 2, 3)
            }
            if not (
                max(run_sequences[1]) < min(run_sequences[2])
                and max(run_sequences[2]) < min(run_sequences[3])
            ):
                raise W2GateContractViolation(
                    "root-authorized showcases are not runtime ordered"
                )
            for producer_id in ("gateway", "agentserver"):
                producer_runs = [
                    next(
                        slot
                        for slot in showcase_slots
                        if slot.showcase_run == run and slot.producer_id == producer_id
                    )
                    for run in (1, 2, 3)
                ]
                if any(
                    current.predecessor_artifact_id != previous.artifact_id
                    for previous, current in zip(
                        producer_runs, producer_runs[1:], strict=False
                    )
                ):
                    raise W2GateContractViolation(
                        "root-authorized showcase producer chain is incomplete"
                    )
        object.__setattr__(self, "public_keys", MappingProxyType(keys))
        object.__setattr__(self, "signer_roles", MappingProxyType(roles))
        object.__setattr__(self, "principal_ids", MappingProxyType(principals))
        object.__setattr__(self, "producer_ids", MappingProxyType(producers))

    def verify(
        self,
        *,
        signer_id: str,
        signature_hex: str,
        content: bytes,
        required_kind: W2EvidenceKind,
        required_producer_id: str | None = None,
        required_principal_id: str | None = None,
    ) -> None:
        _required_text(signer_id, "evidence signer_id")
        raw_key = self.public_keys.get(signer_id)
        roles = self.signer_roles.get(signer_id, frozenset())
        if raw_key is None or required_kind not in roles:
            raise W2GateContractViolation(
                "evidence signer is not trusted for this role"
            )
        assert self.principal_ids is not None
        assert self.producer_ids is not None
        if (
            required_principal_id is not None
            and self.principal_ids.get(signer_id) != required_principal_id
        ):
            raise W2GateContractViolation(
                "evidence witness does not match the trusted principal"
            )
        if (
            required_producer_id is not None
            and self.producer_ids.get(signer_id) != required_producer_id
        ):
            raise W2GateContractViolation(
                "runtime signer does not own the declared producer"
            )
        if re.fullmatch(r"[0-9a-f]{128}", signature_hex) is None:
            raise W2GateContractViolation("evidence signature is invalid")
        try:
            signature = bytes.fromhex(signature_hex)
            Ed25519PublicKey.from_public_bytes(raw_key).verify(signature, content)
        except (InvalidSignature, ValueError) as exc:
            raise W2GateContractViolation(
                "evidence signature verification failed"
            ) from exc


class W2RouteClass(StrEnum):
    FORMAL = "formal"
    FALLBACK = "fallback"
    DEMO_SUBSTITUTE = "demo_substitute"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


class W2CapabilityPlane(StrEnum):
    P1_SPEECH_MEDIA = "p1.speech_media"
    P2_CONVERSATION = "p2.conversation"
    P3_TASK = "p3.task"
    OBSERVABILITY = "observability"


class W2JourneyStep(StrEnum):
    REAL_AGENT_TOOL_SPEECH = "real_agent_tool_speech_response"
    NONBLOCKING_OR_INTERRUPTION = "nonblocking_or_interruption"
    CONFIRMED_TASK_CREATE = "confirmed_formal_task_creation"
    CONVERSATION_DURING_TASK = "conversation_while_task_runs"
    EXACT_TASK_RESULT = "exact_task_progress_result"
    TEXT_DEGRADATION = "degradation_with_text_fallback"
    ROUTE_TELEMETRY = "route_telemetry_inspection"


class W2ReconciliationOutcome(StrEnum):
    TERMINAL = "terminal"
    INTERRUPTED = "interrupted"
    UNKNOWN = "unknown"


_ITEM_SECTION: Mapping[W2LedgerItem, W2Section] = {
    W2LedgerItem.P1_AUDIO: W2Section.P1,
    W2LedgerItem.P1_RECOGNITION: W2Section.P1,
    W2LedgerItem.P1_SYNTHESIS: W2Section.P1,
    W2LedgerItem.P1_COMMIT_DEGRADATION: W2Section.P1,
    W2LedgerItem.P2_RUNTIME: W2Section.P2,
    W2LedgerItem.P2_MEDIA: W2Section.P2,
    W2LedgerItem.P2_ENGINE: W2Section.P2,
    W2LedgerItem.P2_AGENT: W2Section.P2,
    W2LedgerItem.P2_PRESENTATION: W2Section.P2,
    W2LedgerItem.P3_CORE: W2Section.P3,
    W2LedgerItem.P3_EXECUTOR: W2Section.P3,
    W2LedgerItem.P3_VOICE_BRIDGE: W2Section.P3,
    W2LedgerItem.P3_PROGRESS: W2Section.P3,
    W2LedgerItem.P3_UI: W2Section.P3,
    W2LedgerItem.CROSS_ROUTE: W2Section.CROSS_CUTTING,
    W2LedgerItem.CROSS_CONTEXT: W2Section.CROSS_CUTTING,
    W2LedgerItem.CROSS_FAILURE: W2Section.CROSS_CUTTING,
    W2LedgerItem.CROSS_OBSERVABILITY: W2Section.CROSS_CUTTING,
    W2LedgerItem.CROSS_FLAG_OFF: W2Section.CROSS_CUTTING,
}

_ITEM_MAX: Mapping[W2LedgerItem, int] = {
    W2LedgerItem.P1_AUDIO: 5,
    W2LedgerItem.P1_RECOGNITION: 6,
    W2LedgerItem.P1_SYNTHESIS: 5,
    W2LedgerItem.P1_COMMIT_DEGRADATION: 4,
    W2LedgerItem.P2_RUNTIME: 10,
    W2LedgerItem.P2_MEDIA: 8,
    W2LedgerItem.P2_ENGINE: 8,
    W2LedgerItem.P2_AGENT: 8,
    W2LedgerItem.P2_PRESENTATION: 6,
    W2LedgerItem.P3_CORE: 8,
    W2LedgerItem.P3_EXECUTOR: 6,
    W2LedgerItem.P3_VOICE_BRIDGE: 5,
    W2LedgerItem.P3_PROGRESS: 4,
    W2LedgerItem.P3_UI: 2,
    W2LedgerItem.CROSS_ROUTE: 4,
    W2LedgerItem.CROSS_CONTEXT: 3,
    W2LedgerItem.CROSS_FAILURE: 3,
    W2LedgerItem.CROSS_OBSERVABILITY: 3,
    W2LedgerItem.CROSS_FLAG_OFF: 2,
}

_SECTION_MAX: Mapping[W2Section, int] = {
    W2Section.P1: 20,
    W2Section.P2: 40,
    W2Section.P3: 25,
    W2Section.CROSS_CUTTING: 15,
}

_SECTION_MIN: Mapping[W2Section, int] = {
    W2Section.P1: 16,
    W2Section.P2: 36,
    W2Section.P3: 20,
    W2Section.CROSS_CUTTING: 12,
}


def _runtime_fact(source: str, segment: str, event: str = "segment.completed") -> str:
    return f"fact:{source}:{segment}:{event}"


def w2_artifact_signature_payload(
    *,
    kind: str,
    artifact_id: str,
    sequence: int,
    source_label: str | None,
    content: bytes,
) -> bytes:
    """Bind signed content to its closed import identity and ordering metadata."""

    if kind not in {"runtime_jsonl", "automated_report", "assisted_receipt"}:
        raise W2GateContractViolation("artifact signature kind is unsupported")
    _required_text(artifact_id, "artifact signature artifact_id")
    if type(sequence) is not int or sequence <= 0:
        raise W2GateContractViolation("artifact signature sequence is invalid")
    if kind == "automated_report":
        _required_text(source_label, "artifact signature source_label")
    elif source_label is not None:
        raise W2GateContractViolation(
            "runtime and assisted artifact source_label must be null"
        )
    if type(content) is not bytes or not 0 < len(content) <= MAX_W2_ARTIFACT_BYTES:
        raise W2GateContractViolation("artifact signature content is invalid")
    header = json.dumps(
        {
            "schema": "live-voice.w2-artifact-signature.v1",
            "kind": kind,
            "artifact_id": artifact_id,
            "sequence": sequence,
            "source_label": source_label,
            "content_sha256": hashlib.sha256(content).hexdigest(),
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return header + b"\n"


_ITEM_REQUIRED_RUNTIME_FACTS: Mapping[W2LedgerItem, frozenset[str]] = {
    W2LedgerItem.P1_AUDIO: frozenset(
        {
            _runtime_fact("product.w2.media.capture", "speech.capture"),
            _runtime_fact("product.w2.browser.playout", "speech.playout"),
        }
    ),
    W2LedgerItem.P1_RECOGNITION: frozenset(
        {_runtime_fact("product.w2.speech.recognize", "speech.recognition")}
    ),
    W2LedgerItem.P1_SYNTHESIS: frozenset(
        {_runtime_fact("product.w2.speech.synthesize", "speech.synthesis")}
    ),
    W2LedgerItem.P1_COMMIT_DEGRADATION: frozenset(
        {
            _runtime_fact("product.w2.speech.recognize", "speech.recognition"),
            _runtime_fact("product.w2.p2.submit.agent", "runtime.turn"),
            _runtime_fact(
                "product.w2.text.degradation",
                "system.degradation",
                "degradation.activated",
            ),
        }
    ),
    W2LedgerItem.P2_RUNTIME: frozenset(
        {
            _runtime_fact("product.w2.p2.activate", "runtime.queue"),
            _runtime_fact("product.w2.p2.submit.agent", "runtime.turn"),
            _runtime_fact("product.w2.p2.close", "runtime.queue"),
        }
    ),
    W2LedgerItem.P2_MEDIA: frozenset(
        {
            _runtime_fact("product.w2.media.capture", "speech.capture"),
            _runtime_fact("product.w2.browser.playout", "speech.playout"),
            _runtime_fact("product.w2.media.downlink", "runtime.queue"),
            _runtime_fact("product.w2.media.duplex", "runtime.queue"),
        }
    ),
    W2LedgerItem.P2_ENGINE: frozenset(
        {
            _runtime_fact("product.w2.p2.notification", "agent.progress"),
            _runtime_fact(
                "product.w2.p2.barge",
                "speech.playout",
                "cancel.acknowledged",
            ),
        }
    ),
    W2LedgerItem.P2_AGENT: frozenset(
        {
            _runtime_fact("product.w2.p2.submit.agent", "agent.dispatch"),
            _runtime_fact("product.w2.p2.notification", "agent.progress"),
        }
    ),
    W2LedgerItem.P2_PRESENTATION: frozenset(
        {_runtime_fact("product.w2.p2.presentation", "runtime.presentation")}
    ),
    W2LedgerItem.P3_CORE: frozenset(
        {
            _runtime_fact("product.w2.task.create", "task.command"),
            _runtime_fact("product.w2.task.get", "task.progress"),
            _runtime_fact("product.w2.task.list", "runtime.queue"),
            _runtime_fact("product.w2.task.status", "task.progress"),
            _runtime_fact("product.w2.task.cancel", "task.command"),
            _runtime_fact("product.w2.task.events", "task.progress"),
        }
    ),
    W2LedgerItem.P3_EXECUTOR: frozenset(
        {_runtime_fact("product.w2.task.d0", "task.attempt")}
    ),
    W2LedgerItem.P3_VOICE_BRIDGE: frozenset(
        {
            _runtime_fact("product.voice_task_origin", "runtime.turn"),
            _runtime_fact("product.voice_task_bridge", "task.command"),
        }
    ),
    W2LedgerItem.P3_PROGRESS: frozenset(
        {
            _runtime_fact("product.w2.task.status", "task.progress"),
            _runtime_fact("product.w2.task.events", "task.progress"),
            _runtime_fact("product.w2.p3.progress", "task.progress"),
        }
    ),
    W2LedgerItem.P3_UI: frozenset({_runtime_fact("product.w2.p3.ui", "task.progress")}),
    W2LedgerItem.CROSS_ROUTE: frozenset(
        {
            _runtime_fact("product.w2.speech.recognize", "speech.recognition"),
            _runtime_fact("product.w2.p2.submit.agent", "agent.dispatch"),
            _runtime_fact("product.w2.task.create", "task.command"),
        }
    ),
    W2LedgerItem.CROSS_CONTEXT: frozenset(
        {
            _runtime_fact("product.w2.p2.submit.agent", "runtime.turn"),
            _runtime_fact("product.w2.p2.submit.agent", "agent.dispatch"),
            _runtime_fact("product.w2.task.create", "task.command"),
        }
    ),
    W2LedgerItem.CROSS_FAILURE: frozenset(
        {
            _runtime_fact(
                "product.w2.fault",
                "runtime.turn",
                "failure.observed",
            ),
            _runtime_fact(
                "product.w2.text.degradation",
                "system.degradation",
                "degradation.activated",
            ),
        }
    ),
    W2LedgerItem.CROSS_OBSERVABILITY: frozenset(
        {
            _runtime_fact("product.w2.observability", "runtime.queue"),
            _runtime_fact(
                "product.w2.fault",
                "runtime.turn",
                "failure.observed",
            ),
        }
    ),
}

_ITEM_REQUIRED_KINDS: Mapping[W2LedgerItem, frozenset[W2EvidenceKind]] = {
    item: frozenset({W2EvidenceKind.REAL_RUNTIME})
    for item in W2LedgerItem
    if item is not W2LedgerItem.CROSS_FLAG_OFF
}
_ITEM_REQUIRED_KINDS = {
    **_ITEM_REQUIRED_KINDS,
    W2LedgerItem.P1_AUDIO: frozenset(
        {W2EvidenceKind.REAL_RUNTIME, W2EvidenceKind.HUMAN_OBSERVATION}
    ),
    W2LedgerItem.P3_UI: frozenset(
        {W2EvidenceKind.REAL_RUNTIME, W2EvidenceKind.HUMAN_OBSERVATION}
    ),
    W2LedgerItem.CROSS_FAILURE: frozenset(
        {W2EvidenceKind.REAL_RUNTIME, W2EvidenceKind.FAULT_INJECTION}
    ),
    W2LedgerItem.CROSS_FLAG_OFF: frozenset({W2EvidenceKind.AUTOMATED_CONFORMANCE}),
}

_JOURNEY_REQUIRED_RUNTIME_FACTS: Mapping[W2JourneyStep, frozenset[str]] = {
    W2JourneyStep.REAL_AGENT_TOOL_SPEECH: frozenset(
        {
            _runtime_fact("product.w2.journey.agent_speech", "runtime.turn"),
            _runtime_fact("product.w2.speech.recognize", "speech.recognition"),
            _runtime_fact("product.w2.p2.submit.agent", "agent.dispatch"),
            _runtime_fact("product.w2.speech.synthesize", "speech.synthesis"),
        }
    ),
    W2JourneyStep.NONBLOCKING_OR_INTERRUPTION: frozenset(
        {
            _runtime_fact("product.w2.journey.interruption", "runtime.turn"),
            _runtime_fact("product.w2.p2.submit.agent", "agent.dispatch"),
            _runtime_fact(
                "product.w2.p2.barge",
                "speech.playout",
                "cancel.acknowledged",
            ),
        }
    ),
    W2JourneyStep.CONFIRMED_TASK_CREATE: frozenset(
        {
            _runtime_fact("product.w2.journey.task_create", "runtime.turn"),
            _runtime_fact("product.voice_task_origin", "runtime.turn"),
            _runtime_fact("product.voice_task_bridge", "task.command"),
        }
    ),
    W2JourneyStep.CONVERSATION_DURING_TASK: frozenset(
        {
            _runtime_fact(
                "product.w2.journey.conversation_during_task", "runtime.turn"
            ),
            _runtime_fact("product.w2.task.create", "task.command"),
            _runtime_fact("product.w2.p2.submit.agent", "agent.dispatch"),
        }
    ),
    W2JourneyStep.EXACT_TASK_RESULT: frozenset(
        {
            _runtime_fact("product.w2.journey.task_result", "runtime.turn"),
            _runtime_fact("product.w2.task.status", "task.progress"),
            _runtime_fact("product.w2.task.events", "task.progress"),
            _runtime_fact("product.w2.p3.progress", "task.progress"),
        }
    ),
    W2JourneyStep.TEXT_DEGRADATION: frozenset(
        {
            _runtime_fact("product.w2.journey.text_degradation", "runtime.turn"),
            _runtime_fact(
                "product.w2.text.degradation",
                "system.degradation",
                "degradation.activated",
            ),
            _runtime_fact("product.w2.p2.submit.agent", "runtime.turn"),
        }
    ),
    W2JourneyStep.ROUTE_TELEMETRY: frozenset(
        {
            _runtime_fact("product.w2.journey.route_telemetry", "runtime.turn"),
            *_ITEM_REQUIRED_RUNTIME_FACTS[W2LedgerItem.CROSS_ROUTE],
            _runtime_fact("product.w2.observability", "runtime.queue"),
        }
    ),
}

_SHOWCASE_SOURCE_SUBJECTS: Mapping[str, str] = {
    f"product.w2.showcase.{number}": f"showcase:{number}" for number in (1, 2, 3)
}

_FAULT_SOURCE_SUBJECTS: Mapping[str, str] = {
    (
        f"product.w2.fault_marker.{plane.value.replace('.', '_')}.{fault_class}"
    ): f"fault:{plane.value}:{fault_class}"
    for plane in W2CapabilityPlane
    for fault_class in ("retriable", "non_retriable", "zero_effect")
}


def _required_text(value: object, field: str) -> str:
    if type(value) is not str or not value or len(value) > _MAX_LABEL_CHARACTERS:
        raise W2GateContractViolation(f"{field} must be non-empty bounded text")
    try:
        encoded = value.encode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise W2GateContractViolation(f"{field} must be valid UTF-8 text") from exc
    if len(encoded) > _MAX_LABEL_UTF8_BYTES:
        raise W2GateContractViolation(f"{field} exceeds the UTF-8 byte limit")
    if any(character.isspace() for character in value):
        raise W2GateContractViolation(f"{field} must be an opaque label")
    if _SENSITIVE_MARKER.search(value) is not None:
        raise W2GateContractViolation(f"{field} contains a sensitive marker")
    return value


def _required_absolute_path(value: object, field: str) -> str:
    """Validate one bounded absolute filesystem path without label semantics."""

    if type(value) is not str or not value or len(value) > _MAX_PATH_CHARACTERS:
        raise W2GateContractViolation(f"{field} must be a non-empty bounded path")
    try:
        encoded = value.encode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise W2GateContractViolation(f"{field} must be valid UTF-8") from exc
    if len(encoded) > _MAX_PATH_UTF8_BYTES:
        raise W2GateContractViolation(f"{field} exceeds the UTF-8 byte limit")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise W2GateContractViolation(f"{field} contains a control character")
    if not Path(value).is_absolute():
        raise W2GateContractViolation(f"{field} must be absolute")
    return value


def _bounded_tuple(value: object, field: str, maximum: int) -> tuple[object, ...]:
    if type(value) is not tuple or not value or len(value) > maximum:
        raise W2GateContractViolation(
            f"{field} must be a non-empty tuple with at most {maximum} entries"
        )
    return value


def _labels(value: object, field: str, maximum: int) -> tuple[str, ...]:
    items = _bounded_tuple(value, field, maximum)
    labels = tuple(_required_text(item, field) for item in items)
    if len(set(labels)) != len(labels):
        raise W2GateContractViolation(f"{field} must not contain duplicates")
    return labels


def _evidence_ids(value: object, field: str) -> tuple[str, ...]:
    return _labels(value, field, MAX_W2_EVIDENCE_IDS)


def _bool_field(owner: object, field_name: str) -> None:
    if type(getattr(owner, field_name)) is not bool:
        raise W2GateContractViolation(f"{field_name} must be a boolean")


@dataclass(frozen=True, slots=True)
class W2CandidateEvidence:
    candidate_sha: str
    environment_id: str
    session_id: str
    mode_id: str
    project_label: str
    model_labels: tuple[str, ...]
    provider_labels: tuple[str, ...]
    executor_label: str
    browser_label: str
    os_label: str
    device_label: str
    network_label: str
    origin_security_label: str
    worktree_clean: bool
    isolated_runtime_data_observed: bool
    secrets_boundary_recorded: bool
    routes_and_flags_recorded: bool
    real_source_facts_observed: bool
    sanitized_route_trace_observed: bool
    active_planes: frozenset[W2CapabilityPlane]

    def __post_init__(self) -> None:
        if re.fullmatch(r"[0-9a-f]{40}", self.candidate_sha) is None:
            raise W2GateContractViolation("candidate_sha must be a full Git SHA")
        for field_name in (
            "environment_id",
            "session_id",
            "mode_id",
            "project_label",
            "executor_label",
            "browser_label",
            "os_label",
            "device_label",
            "network_label",
            "origin_security_label",
        ):
            _required_text(getattr(self, field_name), field_name)
        _labels(self.model_labels, "model_labels", MAX_W2_PROVIDER_LABELS)
        _labels(self.provider_labels, "provider_labels", MAX_W2_PROVIDER_LABELS)
        for field_name in (
            "worktree_clean",
            "isolated_runtime_data_observed",
            "secrets_boundary_recorded",
            "routes_and_flags_recorded",
            "real_source_facts_observed",
            "sanitized_route_trace_observed",
        ):
            _bool_field(self, field_name)
        if (
            type(self.active_planes) is not frozenset
            or not self.active_planes
            or len(self.active_planes) > len(W2CapabilityPlane)
            or any(
                not isinstance(plane, W2CapabilityPlane) for plane in self.active_planes
            )
        ):
            raise W2GateContractViolation(
                "active_planes must be a non-empty closed set"
            )


@dataclass(frozen=True, slots=True)
class W2EvidenceArtifact:
    artifact_id: str
    sequence: int
    candidate_sha: str
    environment_id: str
    session_id: str
    mode_id: str
    evidence_kinds: frozenset[W2EvidenceKind]
    signer_id: str
    source_label: str
    content_sha256: str
    content_size: int
    proven_ledger_items: frozenset[W2LedgerItem]
    proven_target_items: frozenset[W2LedgerItem]
    proven_route_classes: Mapping[W2LedgerItem, W2RouteClass]
    proven_task_ids: frozenset[str]
    proven_subjects: frozenset[str]
    attested_content_sha256: frozenset[str]
    runtime_format_version: int = 0
    evidence_set_id: str | None = None
    producer_id: str | None = None
    process_epoch: str | None = None
    predecessor_artifact_id: str | None = None
    runtime_observations: tuple[LiveVoiceObservation, ...] = ()
    receipt_evidence_set_id: str | None = None
    receipt_predecessor_sha256: str | None = None
    _construction_token: object = field(default=None, repr=False, compare=False)
    _attestation: str = field(default="", repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._construction_token is not _ARTIFACT_CONSTRUCTION_TOKEN:
            raise W2GateContractViolation(
                "evidence artifacts must be content-verified by the factory"
            )
        if not hmac.compare_digest(self._attestation, _artifact_attestation(self)):
            raise W2GateContractViolation("evidence artifact verification was altered")
        _required_text(self.artifact_id, "artifact_id")
        if type(self.sequence) is not int or self.sequence <= 0:
            raise W2GateContractViolation(
                "artifact sequence must be a positive integer"
            )
        if re.fullmatch(r"[0-9a-f]{40}", self.candidate_sha) is None:
            raise W2GateContractViolation(
                "artifact candidate_sha must be a full Git SHA"
            )
        for field_name in ("environment_id", "session_id", "mode_id"):
            _required_text(getattr(self, field_name), f"artifact {field_name}")
        _required_text(self.source_label, "artifact source_label")
        _required_text(self.signer_id, "artifact signer_id")
        if re.fullmatch(r"[0-9a-f]{64}", self.content_sha256) is None:
            raise W2GateContractViolation("artifact content_sha256 is invalid")
        if (
            type(self.content_size) is not int
            or self.content_size <= 0
            or self.content_size > MAX_W2_ARTIFACT_BYTES
        ):
            raise W2GateContractViolation("artifact content_size is invalid")
        if (
            type(self.evidence_kinds) is not frozenset
            or not self.evidence_kinds
            or any(not isinstance(kind, W2EvidenceKind) for kind in self.evidence_kinds)
        ):
            raise W2GateContractViolation(
                "artifact evidence_kinds must be a non-empty closed set"
            )
        for field_name in ("proven_ledger_items", "proven_target_items"):
            items = getattr(self, field_name)
            if type(items) is not frozenset or any(
                not isinstance(item, W2LedgerItem) for item in items
            ):
                raise W2GateContractViolation(
                    f"artifact {field_name} must be a closed ledger set"
                )
        if not self.proven_target_items.issubset(self.proven_ledger_items):
            raise W2GateContractViolation(
                "artifact target proof must be a subset of ledger proof"
            )
        if type(self.proven_route_classes) not in {dict, MappingProxyType} or any(
            not isinstance(item, W2LedgerItem)
            or not isinstance(route_class, W2RouteClass)
            or item not in self.proven_ledger_items
            for item, route_class in self.proven_route_classes.items()
        ):
            raise W2GateContractViolation(
                "artifact proven_route_classes must be an item-scoped route map"
            )
        object.__setattr__(
            self,
            "proven_route_classes",
            MappingProxyType(dict(self.proven_route_classes)),
        )
        if type(self.proven_task_ids) is not frozenset:
            raise W2GateContractViolation(
                "artifact proven_task_ids must be a closed set"
            )
        for task_id in self.proven_task_ids:
            _required_text(task_id, "artifact proven_task_id")
        if type(self.proven_subjects) is not frozenset:
            raise W2GateContractViolation(
                "artifact proven_subjects must be a closed set"
            )
        for subject in self.proven_subjects:
            _required_text(subject, "artifact proven_subject")
        if type(self.attested_content_sha256) is not frozenset or any(
            re.fullmatch(r"[0-9a-f]{64}", digest) is None
            for digest in self.attested_content_sha256
        ):
            raise W2GateContractViolation(
                "artifact attested_content_sha256 must be a closed digest set"
            )
        if self.runtime_format_version not in {0, 1, 2}:
            raise W2GateContractViolation("artifact runtime format is invalid")
        runtime_metadata = (
            self.evidence_set_id,
            self.producer_id,
            self.process_epoch,
        )
        if self.runtime_format_version == 2:
            if any(value is None for value in runtime_metadata):
                raise W2GateContractViolation("v2 runtime metadata is incomplete")
            for field_name in ("evidence_set_id", "producer_id", "process_epoch"):
                _required_text(getattr(self, field_name), f"artifact {field_name}")
            if (
                self.predecessor_artifact_id is not None
                and self.predecessor_artifact_id == self.artifact_id
            ):
                raise W2GateContractViolation("runtime predecessor cannot be self")
        elif any(value is not None for value in runtime_metadata) or (
            self.predecessor_artifact_id is not None
        ):
            raise W2GateContractViolation("non-v2 artifact carries runtime metadata")
        if type(self.runtime_observations) is not tuple or any(
            type(item) is not LiveVoiceObservation for item in self.runtime_observations
        ):
            raise W2GateContractViolation(
                "artifact runtime observations must be a closed tuple"
            )
        if self.runtime_observations and (
            W2EvidenceKind.REAL_RUNTIME not in self.evidence_kinds
        ):
            raise W2GateContractViolation(
                "runtime observations must belong only to real runtime evidence"
            )
        if self.runtime_format_version in {1, 2} and not self.runtime_observations:
            raise W2GateContractViolation("runtime artifact has no observations")
        if self.runtime_format_version == 0 and self.runtime_observations:
            raise W2GateContractViolation(
                "non-runtime artifact carries runtime observations"
            )
        if self.receipt_evidence_set_id is not None:
            _required_text(self.receipt_evidence_set_id, "receipt evidence_set_id")
            if self.attested_content_sha256 == frozenset():
                raise W2GateContractViolation(
                    "receipt evidence set requires attested content"
                )
        if (
            self.receipt_predecessor_sha256 is not None
            and re.fullmatch(r"[0-9a-f]{64}", self.receipt_predecessor_sha256) is None
        ):
            raise W2GateContractViolation("receipt predecessor digest is invalid")


def _artifact_attestation(artifact: W2EvidenceArtifact) -> str:
    fields = (
        artifact.artifact_id,
        str(artifact.sequence),
        artifact.candidate_sha,
        artifact.environment_id,
        artifact.session_id,
        artifact.mode_id,
        ",".join(sorted(kind.value for kind in artifact.evidence_kinds)),
        artifact.signer_id,
        artifact.source_label,
        artifact.content_sha256,
        str(artifact.content_size),
        ",".join(sorted(item.value for item in artifact.proven_ledger_items)),
        ",".join(sorted(item.value for item in artifact.proven_target_items)),
        ",".join(
            f"{item.value}={route_class.value}"
            for item, route_class in sorted(
                artifact.proven_route_classes.items(), key=lambda value: value[0].value
            )
        ),
        ",".join(sorted(artifact.proven_task_ids)),
        ",".join(sorted(artifact.proven_subjects)),
        ",".join(sorted(artifact.attested_content_sha256)),
        str(artifact.runtime_format_version),
        artifact.evidence_set_id or "",
        artifact.producer_id or "",
        artifact.process_epoch or "",
        artifact.predecessor_artifact_id or "",
        hashlib.sha256(
            json.dumps(
                [item.to_dict() for item in artifact.runtime_observations],
                ensure_ascii=True,
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest(),
        artifact.receipt_evidence_set_id or "",
        artifact.receipt_predecessor_sha256 or "",
    )
    return hmac.new(
        _ARTIFACT_ATTESTATION_KEY,
        "\0".join(fields).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _verified_artifact(
    *,
    artifact_id: str,
    sequence: int,
    candidate_sha: str,
    environment_id: str,
    session_id: str,
    mode_id: str,
    evidence_kinds: frozenset[W2EvidenceKind],
    signer_id: str,
    source_label: str,
    content: bytes,
    proven_ledger_items: frozenset[W2LedgerItem] = frozenset(),
    proven_target_items: frozenset[W2LedgerItem] = frozenset(),
    proven_route_classes: Mapping[W2LedgerItem, W2RouteClass] = MappingProxyType({}),
    proven_task_ids: frozenset[str] = frozenset(),
    proven_subjects: frozenset[str] = frozenset(),
    attested_content_sha256: frozenset[str] = frozenset(),
    runtime_format_version: int = 0,
    evidence_set_id: str | None = None,
    producer_id: str | None = None,
    process_epoch: str | None = None,
    predecessor_artifact_id: str | None = None,
    runtime_observations: tuple[LiveVoiceObservation, ...] = (),
    receipt_evidence_set_id: str | None = None,
    receipt_predecessor_sha256: str | None = None,
) -> W2EvidenceArtifact:
    if type(content) is not bytes or not 0 < len(content) <= MAX_W2_ARTIFACT_BYTES:
        raise W2GateContractViolation(
            "artifact content must be non-empty bounded bytes"
        )
    artifact = W2EvidenceArtifact.__new__(W2EvidenceArtifact)
    values = {
        "artifact_id": artifact_id,
        "sequence": sequence,
        "candidate_sha": candidate_sha,
        "environment_id": environment_id,
        "session_id": session_id,
        "mode_id": mode_id,
        "evidence_kinds": evidence_kinds,
        "signer_id": signer_id,
        "source_label": source_label,
        "content_sha256": hashlib.sha256(content).hexdigest(),
        "content_size": len(content),
        "proven_ledger_items": proven_ledger_items,
        "proven_target_items": proven_target_items,
        "proven_route_classes": proven_route_classes,
        "proven_task_ids": proven_task_ids,
        "proven_subjects": proven_subjects,
        "attested_content_sha256": attested_content_sha256,
        "runtime_format_version": runtime_format_version,
        "evidence_set_id": evidence_set_id,
        "producer_id": producer_id,
        "process_epoch": process_epoch,
        "predecessor_artifact_id": predecessor_artifact_id,
        "runtime_observations": runtime_observations,
        "receipt_evidence_set_id": receipt_evidence_set_id,
        "receipt_predecessor_sha256": receipt_predecessor_sha256,
        "_construction_token": _ARTIFACT_CONSTRUCTION_TOKEN,
    }
    for name, value in values.items():
        object.__setattr__(artifact, name, value)
    object.__setattr__(artifact, "_attestation", _artifact_attestation(artifact))
    artifact.__post_init__()
    return artifact


def verify_w2_evidence_content(
    *,
    artifact_id: str,
    sequence: int,
    candidate_sha: str,
    environment_id: str,
    session_id: str,
    mode_id: str,
    evidence_kinds: frozenset[W2EvidenceKind],
    source_label: str,
    content: bytes,
    trust_policy: W2EvidenceTrustPolicy,
    signer_id: str,
    signature_hex: str,
) -> W2EvidenceArtifact:
    """Verify an automated artifact; never mint runtime/human/review truth."""

    if evidence_kinds != frozenset({W2EvidenceKind.AUTOMATED_CONFORMANCE}):
        raise W2GateContractViolation(
            "generic content verification can only prove automated conformance"
        )
    if not isinstance(trust_policy, W2EvidenceTrustPolicy):
        raise W2GateContractViolation("automated evidence trust policy is required")
    trust_policy.verify(
        signer_id=signer_id,
        signature_hex=signature_hex,
        content=w2_artifact_signature_payload(
            kind="automated_report",
            artifact_id=artifact_id,
            sequence=sequence,
            source_label=source_label,
            content=content,
        ),
        required_kind=W2EvidenceKind.AUTOMATED_CONFORMANCE,
    )
    _required_text(source_label, "automated source_label")
    try:
        report = json.loads(content.decode("utf-8", errors="strict"))
    except (UnicodeError, ValueError) as exc:
        raise W2GateContractViolation(
            "automated evidence must be a valid closed report"
        ) from exc
    if not isinstance(report, dict) or set(report) != {
        "schema",
        "candidate_sha",
        "suite_id",
        "passed_subjects",
    }:
        raise W2GateContractViolation("automated evidence report fields are not closed")
    if (
        report["schema"] != "live-voice.w2-automated-report.v2"
        or report["candidate_sha"] != candidate_sha
    ):
        raise W2GateContractViolation("automated evidence report did not pass")
    _required_text(report["suite_id"], "automated report suite_id")
    raw_subjects = report["passed_subjects"]
    if (
        not isinstance(raw_subjects, list)
        or not raw_subjects
        or len(raw_subjects) > MAX_W2_EVIDENCE_IDS
    ):
        raise W2GateContractViolation("automated report subjects are invalid")
    proven_subjects = frozenset(
        _required_text(item, "automated report subject") for item in raw_subjects
    )
    if len(proven_subjects) != len(raw_subjects):
        raise W2GateContractViolation("automated report subjects contain duplicates")
    forbidden_ledger_subjects = {
        subject
        for subject in proven_subjects
        if subject.startswith("ledger:")
        and subject != f"ledger:{W2LedgerItem.CROSS_FLAG_OFF.value}"
    }
    if forbidden_ledger_subjects:
        raise W2GateContractViolation(
            "automated report cannot prove runtime ledger behavior"
        )
    proven_items = (
        frozenset({W2LedgerItem.CROSS_FLAG_OFF})
        if f"ledger:{W2LedgerItem.CROSS_FLAG_OFF.value}" in proven_subjects
        else frozenset()
    )
    return _verified_artifact(
        artifact_id=artifact_id,
        sequence=sequence,
        candidate_sha=candidate_sha,
        environment_id=environment_id,
        session_id=session_id,
        mode_id=mode_id,
        evidence_kinds=evidence_kinds,
        signer_id=signer_id,
        source_label=source_label,
        content=content,
        proven_ledger_items=proven_items,
        proven_target_items=proven_items,
        proven_route_classes={item: W2RouteClass.FORMAL for item in proven_items},
        proven_subjects=proven_subjects,
    )


def verify_w2_runtime_jsonl_content(
    *,
    artifact_id: str,
    sequence: int,
    content: bytes,
    trust_policy: W2EvidenceTrustPolicy,
    signer_id: str,
    signature_hex: str,
) -> W2EvidenceArtifact:
    """Derive runtime kinds, bindings, and ledger claims from exact W2 JSONL."""

    if type(content) is not bytes or not 0 < len(content) <= MAX_W2_ARTIFACT_BYTES:
        raise W2GateContractViolation("runtime JSONL must be non-empty bounded bytes")
    if not isinstance(trust_policy, W2EvidenceTrustPolicy):
        raise W2GateContractViolation("runtime evidence trust policy is required")
    trust_policy.verify(
        signer_id=signer_id,
        signature_hex=signature_hex,
        content=w2_artifact_signature_payload(
            kind="runtime_jsonl",
            artifact_id=artifact_id,
            sequence=sequence,
            source_label=None,
            content=content,
        ),
        required_kind=W2EvidenceKind.REAL_RUNTIME,
    )
    try:
        text = content.decode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise W2GateContractViolation("runtime JSONL must be valid UTF-8") from exc
    raw_lines = text.splitlines()
    if not raw_lines or len(raw_lines) > MAX_W2_GATE_RECORDS + 2:
        raise W2GateContractViolation("runtime JSONL record count is invalid")
    try:
        envelopes = [json.loads(line) for line in raw_lines]
    except (TypeError, ValueError) as exc:
        raise W2GateContractViolation("runtime JSONL contains invalid JSON") from exc
    if any(not isinstance(envelope, dict) for envelope in envelopes):
        raise W2GateContractViolation("runtime JSONL envelope is not closed")
    candidate_binding: tuple[str, str, str, str] | None = None
    observations: list[LiveVoiceObservation] = []
    runtime_format_version = 1
    evidence_set_id: str | None = None
    producer_id: str | None = None
    process_epoch: str | None = None
    predecessor_artifact_id: str | None = None
    record_envelopes = envelopes
    if envelopes[0].get("evidence_schema") == "live-voice.w2-jsonl-evidence.v2":
        runtime_format_version = 2
        if len(envelopes) < 3:
            raise W2GateContractViolation("v2 runtime JSONL is not closed")
        header = envelopes[0]
        if (
            set(header)
            != {
                "evidence_schema",
                "record_kind",
                "evidence_set_id",
                "artifact_id",
                "artifact_sequence",
                "producer_id",
                "process_epoch",
                "predecessor_artifact_id",
                "repository_path",
                "candidate",
            }
            or header.get("record_kind") != "header"
        ):
            raise W2GateContractViolation("v2 runtime header is not closed")
        if (
            header.get("artifact_id") != artifact_id
            or header.get("artifact_sequence") != sequence
        ):
            raise W2GateContractViolation(
                "v2 signed runtime identity does not match its import"
            )
        evidence_set_id = _required_text(
            header.get("evidence_set_id"), "runtime evidence_set_id"
        )
        producer_id = _required_text(header.get("producer_id"), "runtime producer_id")
        process_epoch = _required_text(
            header.get("process_epoch"), "runtime process_epoch"
        )
        predecessor_artifact_id = header.get("predecessor_artifact_id")
        if predecessor_artifact_id is not None:
            predecessor_artifact_id = _required_text(
                predecessor_artifact_id, "runtime predecessor_artifact_id"
            )
            if predecessor_artifact_id == artifact_id:
                raise W2GateContractViolation("runtime predecessor cannot be self")
        repository_path = header.get("repository_path")
        if (
            not isinstance(repository_path, str)
            or not Path(repository_path).is_absolute()
            or (
                trust_policy.repository_path is not None
                and Path(repository_path).resolve()
                != Path(trust_policy.repository_path).resolve()
            )
        ):
            raise W2GateContractViolation(
                "runtime repository differs from the root-authorized source tree"
            )
        footer = envelopes[-1]
        if set(footer) != {
            "evidence_schema",
            "record_kind",
            "artifact_id",
            "record_count",
            "last_sequence",
            "accepted_observations",
            "accepted_metrics",
            "rejected_invalid",
            "rejected_capacity",
            "failed_writes",
            "closed",
        } or (
            footer.get("evidence_schema") != "live-voice.w2-jsonl-evidence.v2"
            or footer.get("record_kind") != "footer"
            or footer.get("artifact_id") != artifact_id
            or footer.get("closed") is not True
        ):
            raise W2GateContractViolation("v2 runtime footer is not closed")
        record_envelopes = envelopes[1:-1]
        if (
            footer.get("record_count") != len(record_envelopes)
            or footer.get("last_sequence") != len(record_envelopes) - 1
            or footer.get("rejected_invalid") != 0
            or footer.get("rejected_capacity") != 0
            or footer.get("failed_writes") != 0
        ):
            raise W2GateContractViolation(
                "v2 runtime footer reports incomplete evidence capture"
            )
        candidate = header.get("candidate")
        if not isinstance(candidate, dict) or set(candidate) != {
            "candidate_sha",
            "environment_id",
            "session_id",
            "mode_id",
        }:
            raise W2GateContractViolation("v2 runtime candidate binding is not closed")
        candidate_binding = (
            candidate["candidate_sha"],
            candidate["environment_id"],
            candidate["session_id"],
            candidate["mode_id"],
        )
    observation_count = 0
    metric_count = 0
    for expected_sequence, envelope in enumerate(record_envelopes):
        if not isinstance(envelope, dict) or set(envelope) != {
            "evidence_schema",
            "candidate",
            "record_kind",
            "sequence",
            "record",
        }:
            raise W2GateContractViolation("runtime JSONL envelope is not closed")
        if (
            envelope["evidence_schema"]
            != f"live-voice.w2-jsonl-evidence.v{runtime_format_version}"
            or envelope["record_kind"] not in {"observation", "metric"}
            or envelope["sequence"] != expected_sequence
        ):
            raise W2GateContractViolation("runtime JSONL envelope is inconsistent")
        candidate = envelope["candidate"]
        if not isinstance(candidate, dict) or set(candidate) != {
            "candidate_sha",
            "environment_id",
            "session_id",
            "mode_id",
        }:
            raise W2GateContractViolation(
                "runtime JSONL candidate binding is not closed"
            )
        binding = (
            candidate["candidate_sha"],
            candidate["environment_id"],
            candidate["session_id"],
            candidate["mode_id"],
        )
        if candidate_binding is None:
            candidate_binding = binding
        elif binding != candidate_binding:
            raise W2GateContractViolation("runtime JSONL mixes candidate bindings")
        try:
            if envelope["record_kind"] == "observation":
                observations.append(create_observation(envelope["record"]))
                observation_count += 1
            else:
                create_metric(envelope["record"])
                metric_count += 1
        except Exception as exc:
            raise W2GateContractViolation(
                "runtime JSONL contains an invalid public record"
            ) from exc
    if runtime_format_version == 2:
        footer = envelopes[-1]
        if (
            footer.get("accepted_observations") != observation_count
            or footer.get("accepted_metrics") != metric_count
        ):
            raise W2GateContractViolation("v2 runtime footer counters disagree")
        assert producer_id is not None
        trust_policy.verify(
            signer_id=signer_id,
            signature_hex=signature_hex,
            content=w2_artifact_signature_payload(
                kind="runtime_jsonl",
                artifact_id=artifact_id,
                sequence=sequence,
                source_label=None,
                content=content,
            ),
            required_kind=W2EvidenceKind.REAL_RUNTIME,
            required_producer_id=producer_id,
        )
    assert candidate_binding is not None
    candidate_sha, environment_id, session_id, mode_id = candidate_binding
    if runtime_format_version == 2 and any(
        item.source_component.startswith(
            (
                "product.w2.journey.",
                "product.w2.showcase.",
                "product.w2.fault_marker.",
            )
        )
        or item.source_component
        in {
            "product.task_restart_recovery",
            "product.w2.text.degradation",
            "product.w2.observability",
        }
        for item in observations
    ):
        raise W2GateContractViolation(
            "v2 runtime cannot use self-reporting Gate marker sources"
        )
    if runtime_format_version == 2:
        gateway_sources = {
            "product.w2.browser.playout",
            "product.w2.media.capture",
            "product.w2.media.downlink",
            "product.w2.media.duplex",
            "product.w2.speech.recognize",
            "product.w2.speech.synthesize",
        }
        agentserver_prefixes = (
            "product.w2.p2.",
            "product.w2.p3.",
            "product.w2.agent.",
            "product.w2.task.",
            "product.voice_task_",
        )
        wrong_owner = any(
            (producer_id == "gateway" and item.source_component not in gateway_sources)
            or (
                producer_id == "agentserver"
                and (
                    item.source_component in gateway_sources
                    or not item.source_component.startswith(agentserver_prefixes)
                )
            )
            for item in observations
        )
        if wrong_owner:
            raise W2GateContractViolation(
                "v2 runtime source is not owned by its signed producer"
            )
    route_keys = {
        (
            item.source_component if runtime_format_version == 2 else "",
            item.segment_name,
            json.dumps(item.binding.to_dict(), sort_keys=True),
            json.dumps(item.route.to_dict(), sort_keys=True),
            item.source_record_id if runtime_format_version == 2 else None,
        )
        for item in observations
        if item.event_name == "route.selected"
        and item.route.implementation_class == "formal"
        and (runtime_format_version == 1 or item.source_record_id is not None)
    }
    completed = [
        item
        for item in observations
        if item.event_name == "segment.completed"
        and item.route.implementation_class == "formal"
        and (
            item.source_component if runtime_format_version == 2 else "",
            item.segment_name,
            json.dumps(item.binding.to_dict(), sort_keys=True),
            json.dumps(item.route.to_dict(), sort_keys=True),
            item.source_record_id if runtime_format_version == 2 else None,
        )
        in route_keys
    ]
    facts_by_correlation: dict[str, set[str]] = {}
    fact_records = [
        item
        for item in observations
        if item in completed
        or item.event_name
        in {"cancel.acknowledged", "degradation.activated", "failure.observed"}
    ]
    for item in fact_records:
        facts_by_correlation.setdefault(item.binding.correlation_id, set()).add(
            _runtime_fact(
                item.source_component,
                item.segment_name,
                item.event_name,
            )
        )
    proven_by_correlation = {
        correlation_id: frozenset(
            item
            for item, required in _ITEM_REQUIRED_RUNTIME_FACTS.items()
            if required.issubset(facts)
        )
        for correlation_id, facts in facts_by_correlation.items()
    }
    proven_items = frozenset(
        item for items in proven_by_correlation.values() for item in items
    )
    if runtime_format_version == 2:
        # v2 credit is derived only after all independently signed producer
        # artifacts are assembled; one local stream cannot self-award a
        # cross-product journey by correlation alone.
        proven_items = frozenset()
    failure_observed = any(
        item.event_name
        in {"segment.failed", "failure.observed", "degradation.activated"}
        for item in observations
    )
    kinds = {W2EvidenceKind.REAL_RUNTIME}
    task_state_observed = any(
        item.event_name == "task.state_observed" for item in observations
    )
    if not completed and not failure_observed and not task_state_observed:
        raise W2GateContractViolation(
            "runtime JSONL contains no completed route, task state, or observed fault"
        )
    task_ids = frozenset(
        item.binding.task_id
        for item in observations
        if item.binding.task_id is not None
    )
    runtime_subjects = {f"runtime:{item.segment_name}" for item in observations}
    runtime_subjects.update(
        fact for facts in facts_by_correlation.values() for fact in facts
    )
    runtime_subjects.update(f"ledger:{item.value}" for item in proven_items)
    runtime_subjects.update(
        _SHOWCASE_SOURCE_SUBJECTS[item.source_component]
        for item in completed
        if item.source_component in _SHOWCASE_SOURCE_SUBJECTS
    )
    runtime_subjects.update(
        _FAULT_SOURCE_SUBJECTS[item.source_component]
        for item in observations
        if item.event_name == "failure.observed"
        and item.source_component in _FAULT_SOURCE_SUBJECTS
    )
    for correlation_id, facts in facts_by_correlation.items():
        chain_id = hashlib.sha256(correlation_id.encode("utf-8")).hexdigest()[:32]
        correlation_records = [
            (index, item)
            for index, item in enumerate(observations)
            if item.binding.correlation_id == correlation_id
        ]
        correlation_task_ids = {
            item.binding.task_id
            for _, item in correlation_records
            if item.binding.task_id is not None
        }
        for step, required in _JOURNEY_REQUIRED_RUNTIME_FACTS.items():
            if not required.issubset(facts):
                continue
            marker_source = {
                W2JourneyStep.REAL_AGENT_TOOL_SPEECH: "product.w2.journey.agent_speech",
                W2JourneyStep.NONBLOCKING_OR_INTERRUPTION: "product.w2.journey.interruption",
                W2JourneyStep.CONFIRMED_TASK_CREATE: "product.w2.journey.task_create",
                W2JourneyStep.CONVERSATION_DURING_TASK: (
                    "product.w2.journey.conversation_during_task"
                ),
                W2JourneyStep.EXACT_TASK_RESULT: "product.w2.journey.task_result",
                W2JourneyStep.TEXT_DEGRADATION: ("product.w2.journey.text_degradation"),
                W2JourneyStep.ROUTE_TELEMETRY: ("product.w2.journey.route_telemetry"),
            }[step]
            marker_indices = [
                index
                for index, item in correlation_records
                if item.source_component == marker_source
                and item.event_name == "segment.completed"
            ]
            if not marker_indices:
                continue
            runtime_subjects.update(
                {
                    f"journey:{step.value}",
                    f"journey-chain:{chain_id}",
                    f"journey-order:{step.value}:{min(marker_indices)}",
                }
            )
            if step in {
                W2JourneyStep.CONFIRMED_TASK_CREATE,
                W2JourneyStep.CONVERSATION_DURING_TASK,
                W2JourneyStep.EXACT_TASK_RESULT,
            }:
                runtime_subjects.update(
                    f"journey-task-chain:{hashlib.sha256(task_id.encode('utf-8')).hexdigest()[:32]}"
                    for task_id in correlation_task_ids
                )
    if route_keys:
        runtime_subjects.add("candidate:sanitized_route_trace_observed")
    if {
        "agent.dispatch",
        "task.command",
    }.issubset({item.segment_name for item in completed}):
        runtime_subjects.add("candidate:real_source_facts_observed")
    restart_records = [
        item
        for item in observations
        if item.source_component == "product.task_restart_recovery"
        and item.segment_name == "task.progress"
        and item.event_name == "task.state_observed"
        and item.binding.task_id is not None
    ]
    if restart_records:
        runtime_subjects.add("restart:boundary")
    for item in restart_records:
        if item.binding.task_id is None:
            continue
        if item.state in {"accepted", "running", "blocked", "decision_required"}:
            runtime_subjects.add(f"restart:inflight:{item.binding.task_id}")
        if item.state == "terminal":
            outcome = (
                item.outcome
                if item.outcome in {"interrupted", "unknown"}
                else "terminal"
            )
            runtime_subjects.add(f"restart:reconciled:{item.binding.task_id}:{outcome}")
    digest = hashlib.sha256(content).hexdigest()
    return _verified_artifact(
        artifact_id=artifact_id,
        sequence=sequence,
        candidate_sha=candidate_sha,
        environment_id=environment_id,
        session_id=session_id,
        mode_id=mode_id,
        evidence_kinds=frozenset(kinds),
        signer_id=signer_id,
        source_label=f"w2-runtime-{digest[:32]}",
        content=content,
        proven_ledger_items=proven_items,
        proven_target_items=proven_items,
        proven_route_classes={item: W2RouteClass.FORMAL for item in proven_items},
        proven_task_ids=task_ids,
        proven_subjects=frozenset(runtime_subjects),
        runtime_format_version=runtime_format_version,
        evidence_set_id=evidence_set_id,
        producer_id=producer_id,
        process_epoch=process_epoch,
        predecessor_artifact_id=predecessor_artifact_id,
        runtime_observations=tuple(observations),
    )


def verify_w2_assisted_receipt_content(
    content: bytes,
    *,
    trust_policy: W2EvidenceTrustPolicy,
    signer_id: str,
    signature_hex: str,
) -> W2EvidenceArtifact:
    """Verify one closed external human or independent-review receipt."""

    if type(content) is not bytes or not 0 < len(content) <= MAX_W2_ARTIFACT_BYTES:
        raise W2GateContractViolation(
            "assisted receipt must be non-empty bounded bytes"
        )
    try:
        receipt = json.loads(content.decode("utf-8", errors="strict"))
    except (UnicodeError, ValueError) as exc:
        raise W2GateContractViolation("assisted receipt must be valid JSON") from exc
    if not isinstance(receipt, dict):
        raise W2GateContractViolation("assisted receipt fields are not closed")
    receipt_version = receipt.get("schema")
    expected_fields = (
        {
            "schema",
            "receipt_type",
            "artifact_id",
            "sequence",
            "candidate",
            "witness_id",
            "observed_subject",
            "observed_content_sha256",
            "passed",
        }
        if receipt_version == "live-voice.w2-assisted-receipt.v1"
        else {
            "schema",
            "receipt_type",
            "artifact_id",
            "sequence",
            "candidate",
            "evidence_set_id",
            "witness_id",
            "observed_subject",
            "observed_content_sha256s",
            "previous_receipt_sha256",
            "passed",
        }
    )
    if set(receipt) != expected_fields or receipt_version not in {
        "live-voice.w2-assisted-receipt.v1",
        "live-voice.w2-assisted-receipt.v2",
    }:
        raise W2GateContractViolation("assisted receipt schema is invalid")
    kind = {
        "human_observation": W2EvidenceKind.HUMAN_OBSERVATION,
        "independent_review": W2EvidenceKind.INDEPENDENT_REVIEW,
        "fault_injection": W2EvidenceKind.FAULT_INJECTION,
        "runtime_attestation": W2EvidenceKind.REAL_RUNTIME,
    }.get(receipt["receipt_type"])
    if kind is None or receipt["passed"] is not True:
        raise W2GateContractViolation("assisted receipt outcome is not accepted")
    if not isinstance(trust_policy, W2EvidenceTrustPolicy):
        raise W2GateContractViolation("assisted evidence trust policy is required")
    trust_policy.verify(
        signer_id=signer_id,
        signature_hex=signature_hex,
        content=w2_artifact_signature_payload(
            kind="assisted_receipt",
            artifact_id=receipt["artifact_id"],
            sequence=receipt["sequence"],
            source_label=None,
            content=content,
        ),
        required_kind=kind,
        required_principal_id=receipt["witness_id"],
    )
    candidate = receipt["candidate"]
    if not isinstance(candidate, dict) or set(candidate) != {
        "candidate_sha",
        "environment_id",
        "session_id",
        "mode_id",
    }:
        raise W2GateContractViolation("assisted receipt candidate is not closed")
    _required_text(receipt["witness_id"], "assisted receipt witness_id")
    observed_subject = _required_text(
        receipt["observed_subject"], "assisted receipt observed_subject"
    )
    receipt_evidence_set_id: str | None = None
    receipt_predecessor_sha256: str | None = None
    if receipt_version == "live-voice.w2-assisted-receipt.v1":
        observed_digests = (str(receipt["observed_content_sha256"]),)
    else:
        receipt_evidence_set_id = _required_text(
            receipt["evidence_set_id"], "assisted receipt evidence_set_id"
        )
        raw_digests = receipt["observed_content_sha256s"]
        if (
            not isinstance(raw_digests, list)
            or not raw_digests
            or len(raw_digests) > MAX_W2_EVIDENCE_IDS
        ):
            raise W2GateContractViolation(
                "assisted receipt observed digests are invalid"
            )
        observed_digests = tuple(str(value) for value in raw_digests)
        if len(set(observed_digests)) != len(observed_digests):
            raise W2GateContractViolation(
                "assisted receipt observed digests are duplicated"
            )
        raw_predecessor = receipt["previous_receipt_sha256"]
        if raw_predecessor is not None:
            receipt_predecessor_sha256 = str(raw_predecessor)
            if re.fullmatch(r"[0-9a-f]{64}", receipt_predecessor_sha256) is None:
                raise W2GateContractViolation(
                    "assisted receipt predecessor digest is invalid"
                )
    if any(
        re.fullmatch(r"[0-9a-f]{64}", digest) is None for digest in observed_digests
    ):
        raise W2GateContractViolation("assisted receipt observed digest is invalid")
    digest = hashlib.sha256(content).hexdigest()
    return _verified_artifact(
        artifact_id=receipt["artifact_id"],
        sequence=receipt["sequence"],
        candidate_sha=candidate["candidate_sha"],
        environment_id=candidate["environment_id"],
        session_id=candidate["session_id"],
        mode_id=candidate["mode_id"],
        evidence_kinds=frozenset({kind}),
        signer_id=signer_id,
        source_label=f"w2-{receipt['receipt_type']}-{digest[:24]}",
        content=content,
        proven_ledger_items=frozenset(),
        proven_target_items=frozenset(),
        proven_route_classes={},
        attested_content_sha256=frozenset(observed_digests),
        proven_subjects=frozenset({observed_subject}),
        receipt_evidence_set_id=receipt_evidence_set_id,
        receipt_predecessor_sha256=receipt_predecessor_sha256,
    )


@dataclass(frozen=True, slots=True)
class W2AutomatedVerificationEvidence:
    affected_python_passed: bool
    affected_web_passed: bool
    frontend_build_passed: bool
    negative_fault_and_flag_off_passed: bool
    required_reviews_passed: bool
    unexplained_required_gaps_zero: bool
    flaky_passes_zero: bool
    evidence_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        for field_name in (
            "affected_python_passed",
            "affected_web_passed",
            "frontend_build_passed",
            "negative_fault_and_flag_off_passed",
            "required_reviews_passed",
            "unexplained_required_gaps_zero",
            "flaky_passes_zero",
        ):
            _bool_field(self, field_name)
        _evidence_ids(self.evidence_ids, "verification evidence_ids")


@dataclass(frozen=True, slots=True)
class W2LedgerAward:
    item: W2LedgerItem
    points: int
    route_class: W2RouteClass
    evidence_kinds: frozenset[W2EvidenceKind]
    evidence_ids: tuple[str, ...]
    target_route_owned: bool

    def __post_init__(self) -> None:
        if not isinstance(self.item, W2LedgerItem):
            raise W2GateContractViolation("item must use W2LedgerItem")
        if type(self.points) is not int or not 0 <= self.points <= _ITEM_MAX[self.item]:
            raise W2GateContractViolation("points exceed the immutable item weight")
        if not isinstance(self.route_class, W2RouteClass):
            raise W2GateContractViolation("route_class must use W2RouteClass")
        if type(self.evidence_kinds) is not frozenset or any(
            not isinstance(kind, W2EvidenceKind) for kind in self.evidence_kinds
        ):
            raise W2GateContractViolation("evidence_kinds must be a closed set")
        _evidence_ids(self.evidence_ids, "ledger evidence_ids")
        _bool_field(self, "target_route_owned")
        if (
            self.points > 0
            and self.item is not W2LedgerItem.CROSS_FLAG_OFF
            and W2EvidenceKind.REAL_RUNTIME not in self.evidence_kinds
        ):
            raise W2GateContractViolation(
                "positive credit requires candidate-observed real runtime evidence"
            )
        if self.points > 0 and self.route_class in {
            W2RouteClass.UNSUPPORTED,
            W2RouteClass.UNKNOWN,
        }:
            raise W2GateContractViolation(
                "unsupported or unknown routes cannot receive credit"
            )
        if (
            self.points > 0
            and _ITEM_SECTION[self.item] is W2Section.P3
            and self.route_class is W2RouteClass.DEMO_SUBSTITUTE
        ):
            raise W2GateContractViolation(
                "D-031/D-057 forbid demo-substitute credit for every P3 item"
            )
        if self.points == _ITEM_MAX[self.item] and (
            not self.target_route_owned
            or self.route_class is W2RouteClass.DEMO_SUBSTITUTE
        ):
            raise W2GateContractViolation(
                "full item credit requires the target route to own the behavior"
            )


@dataclass(frozen=True, slots=True)
class W2InvariantEvidence:
    invariant: W2Invariant
    passed: bool
    evidence_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.invariant, W2Invariant):
            raise W2GateContractViolation("invariant must use W2Invariant")
        _bool_field(self, "passed")
        _evidence_ids(self.evidence_ids, "invariant evidence_ids")


@dataclass(frozen=True, slots=True)
class W2ShowcaseRun:
    run_number: int
    candidate_sha: str
    environment_id: str
    session_id: str
    mode_id: str
    passed: bool
    evidence_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.run_number) is not int or self.run_number not in {1, 2, 3}:
            raise W2GateContractViolation("showcase run_number must be 1, 2, or 3")
        if re.fullmatch(r"[0-9a-f]{40}", self.candidate_sha) is None:
            raise W2GateContractViolation(
                "showcase candidate_sha must be a full Git SHA"
            )
        for field_name in ("environment_id", "session_id", "mode_id"):
            _required_text(getattr(self, field_name), f"showcase {field_name}")
        _bool_field(self, "passed")
        _evidence_ids(self.evidence_ids, "showcase evidence_ids")


@dataclass(frozen=True, slots=True)
class W2JourneyStepEvidence:
    step: W2JourneyStep
    passed: bool
    evidence_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.step, W2JourneyStep):
            raise W2GateContractViolation("journey step must use W2JourneyStep")
        _bool_field(self, "passed")
        _evidence_ids(self.evidence_ids, "journey evidence_ids")


@dataclass(frozen=True, slots=True)
class W2FaultEvidence:
    plane: W2CapabilityPlane
    active: bool
    retriable_observed: bool
    non_retriable_observed: bool
    stale_effects_zero: bool
    false_success_zero: bool
    retriable_evidence_ids: tuple[str, ...]
    non_retriable_evidence_ids: tuple[str, ...]
    zero_effect_evidence_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.plane, W2CapabilityPlane):
            raise W2GateContractViolation("plane must use W2CapabilityPlane")
        for field_name in (
            "active",
            "retriable_observed",
            "non_retriable_observed",
            "stale_effects_zero",
            "false_success_zero",
        ):
            _bool_field(self, field_name)
        evidence_sets = tuple(
            set(_evidence_ids(getattr(self, field_name), field_name))
            for field_name in (
                "retriable_evidence_ids",
                "non_retriable_evidence_ids",
                "zero_effect_evidence_ids",
            )
        )
        if any(
            left & right
            for index, left in enumerate(evidence_sets)
            for right in evidence_sets[index + 1 :]
        ):
            raise W2GateContractViolation(
                "fault classes and zero-effect proof require distinct artifacts"
            )

    @property
    def evidence_ids(self) -> tuple[str, ...]:
        return (
            *self.retriable_evidence_ids,
            *self.non_retriable_evidence_ids,
            *self.zero_effect_evidence_ids,
        )


@dataclass(frozen=True, slots=True)
class W2TaskReconciliationEvidence:
    task_id: str
    outcome: W2ReconciliationOutcome
    evidence_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _required_text(self.task_id, "reconciliation task_id")
        if not isinstance(self.outcome, W2ReconciliationOutcome):
            raise W2GateContractViolation(
                "reconciliation outcome must use W2ReconciliationOutcome"
            )
        _evidence_ids(self.evidence_ids, "reconciliation evidence_ids")


@dataclass(frozen=True, slots=True)
class W2RestartEvidence:
    performed: bool
    inflight_task_ids: tuple[str, ...]
    reconciliations: tuple[W2TaskReconciliationEvidence, ...]
    evidence_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _bool_field(self, "performed")
        _labels(
            self.inflight_task_ids, "restart inflight_task_ids", MAX_W2_EVIDENCE_IDS
        )
        _evidence_ids(self.evidence_ids, "restart evidence_ids")
        if (
            type(self.reconciliations) is not tuple
            or len(self.reconciliations) > MAX_W2_EVIDENCE_IDS
        ):
            raise W2GateContractViolation("restart reconciliations are unbounded")
        if any(
            type(item) is not W2TaskReconciliationEvidence
            for item in self.reconciliations
        ):
            raise W2GateContractViolation("restart reconciliation type is invalid")
        task_ids = tuple(item.task_id for item in self.reconciliations)
        if len(task_ids) != len(set(task_ids)):
            raise W2GateContractViolation("restart reconciliations contain duplicates")


@dataclass(frozen=True, slots=True)
class W2GateResult:
    status: W2GateStatus
    section_scores: Mapping[W2Section, int]
    total_score: int
    failures: tuple[str, ...]
    _construction_token: object = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._construction_token is not _RESULT_CONSTRUCTION_TOKEN:
            raise W2GateContractViolation("W2GateResult must come from the evaluator")
        if not isinstance(self.status, W2GateStatus):
            raise W2GateContractViolation("status must use W2GateStatus")
        if set(self.section_scores) != set(W2Section):
            raise W2GateContractViolation("section_scores must cover every section")
        if any(
            type(score) is not int or not 0 <= score <= _SECTION_MAX[section]
            for section, score in self.section_scores.items()
        ):
            raise W2GateContractViolation("section_scores contain an invalid score")
        if self.total_score != sum(self.section_scores.values()):
            raise W2GateContractViolation("total_score must equal section scores")
        if type(self.failures) is not tuple or len(set(self.failures)) != len(
            self.failures
        ):
            raise W2GateContractViolation("failures must be a unique tuple")
        if self.status is W2GateStatus.PASS and self.failures:
            raise W2GateContractViolation("PASS cannot retain failures")
        if self.status is W2GateStatus.FAIL and not self.failures:
            raise W2GateContractViolation("FAIL requires at least one reason")
        object.__setattr__(
            self, "section_scores", MappingProxyType(dict(self.section_scores))
        )


def _unique_by_key(
    values: Sequence[_T],
    key: Callable[[_T], _K],
    expected_type: type[_T],
    label: str,
) -> dict[_K, _T]:
    if type(values) is not tuple or len(values) > MAX_W2_GATE_RECORDS:
        raise W2GateContractViolation(f"{label} exceeds the bounded record limit")
    result: dict[_K, _T] = {}
    for value in values:
        if type(value) is not expected_type:
            raise W2GateContractViolation(f"{label} has an invalid record type")
        identity = key(value)
        if identity in result:
            raise W2GateContractViolation(f"duplicate {label}: {identity}")
        result[identity] = value
    return result


def _v2_runtime_facts(
    artifacts: Sequence[W2EvidenceArtifact],
) -> tuple[
    list[tuple[W2EvidenceArtifact, int, LiveVoiceObservation]],
    list[tuple[W2EvidenceArtifact, int, LiveVoiceObservation]],
]:
    """Return exact completed operations and other governed v2 runtime facts."""

    completed: list[tuple[W2EvidenceArtifact, int, LiveVoiceObservation]] = []
    governed: list[tuple[W2EvidenceArtifact, int, LiveVoiceObservation]] = []
    for artifact in artifacts:
        if artifact.runtime_format_version != 2:
            continue
        routes = {
            (
                item.source_component,
                item.segment_name,
                json.dumps(item.binding.to_dict(), sort_keys=True),
                json.dumps(item.route.to_dict(), sort_keys=True),
                item.source_record_id,
            )
            for item in artifact.runtime_observations
            if item.event_name == "route.selected"
            and item.route.implementation_class == "formal"
            and item.source_record_id is not None
        }
        for index, item in enumerate(artifact.runtime_observations):
            exact = (
                item.source_component,
                item.segment_name,
                json.dumps(item.binding.to_dict(), sort_keys=True),
                json.dumps(item.route.to_dict(), sort_keys=True),
                item.source_record_id,
            )
            if item.event_name == "segment.completed" and exact in routes:
                completed.append((artifact, index, item))
            elif item.event_name in {
                "segment.failed",
                "cancel.acknowledged",
                "task.state_observed",
            } and (
                item.route.implementation_class == "formal"
                and (
                    item.event_name == "task.state_observed"
                    or item.source_record_id is not None
                )
            ):
                governed.append((artifact, index, item))
    return completed, governed


def _same_binding(
    left: LiveVoiceObservation,
    right: LiveVoiceObservation,
    *fields: str,
) -> bool:
    identity_fields = (
        "correlation_id",
        "interaction_id",
        "turn_id",
        "response_id",
        "response_generation",
        "round_id",
        "task_id",
        "attempt_id",
    )
    if left.binding.correlation_id != right.binding.correlation_id:
        return False
    if any(
        getattr(left.binding, field_name) is not None
        and getattr(right.binding, field_name) is not None
        and getattr(left.binding, field_name) != getattr(right.binding, field_name)
        for field_name in identity_fields
    ):
        return False
    return all(
        getattr(left.binding, field_name) is not None
        and getattr(left.binding, field_name) == getattr(right.binding, field_name)
        for field_name in fields
    )


def _observations_are_ordered(
    positions: Mapping[int, tuple[str, int]],
    *items: LiveVoiceObservation,
) -> bool:
    """Order facts by their producer record, or by cross-producer wall time.

    Artifact sequence identifies an authorized file slot; it is not a causal
    clock. Records in one artifact retain their exact append order. Facts from
    different producer artifacts must instead have strictly increasing UTC
    observation times, which are captured on the same controlled W2 host.
    """

    for left, right in zip(items, items[1:], strict=False):
        left_artifact, left_index = positions[id(left)]
        right_artifact, right_index = positions[id(right)]
        if left_artifact == right_artifact:
            if left_index >= right_index:
                return False
            continue
        left_time = datetime.fromisoformat(left.observed_at.replace("Z", "+00:00"))
        right_time = datetime.fromisoformat(right.observed_at.replace("Z", "+00:00"))
        if left_time >= right_time:
            return False
    return True


@dataclass(frozen=True, slots=True)
class _V2CoreCancelWitness:
    """One exact Core attempt whose accepted cancel reached terminal truth."""

    attempt_id: str
    create: LiveVoiceObservation
    cancel: LiveVoiceObservation
    terminal: LiveVoiceObservation


def _derive_v2_runtime_items(
    artifacts: Sequence[W2EvidenceArtifact],
) -> frozenset[W2LedgerItem]:
    runtime = [
        artifact
        for artifact in artifacts
        if artifact.runtime_format_version == 2
        and W2EvidenceKind.REAL_RUNTIME in artifact.evidence_kinds
    ]
    if not runtime:
        return frozenset()
    evidence_sets = {artifact.evidence_set_id for artifact in runtime}
    if len(evidence_sets) != 1:
        return frozenset()
    completed, governed = _v2_runtime_facts(runtime)
    positions = {
        id(item): (artifact.artifact_id, index)
        for artifact, index, item in (*completed, *governed)
    }

    def ordered(*items: LiveVoiceObservation) -> bool:
        return _observations_are_ordered(positions, *items)

    def facts(source: str, segment: str) -> list[LiveVoiceObservation]:
        return [
            item
            for _, _, item in completed
            if item.source_component == source and item.segment_name == segment
        ]

    def governed_facts(
        event_name: str, *, source: str | None = None
    ) -> list[LiveVoiceObservation]:
        return [
            item
            for _, _, item in governed
            if item.event_name == event_name
            and (source is None or item.source_component == source)
        ]

    capture = facts("product.w2.media.capture", "speech.capture")
    playout = facts("product.w2.browser.playout", "speech.playout")
    downlink = facts("product.w2.media.downlink", "runtime.queue")
    duplex = facts("product.w2.media.duplex", "runtime.queue")
    recognition = facts("product.w2.speech.recognize", "speech.recognition")
    synthesis = facts("product.w2.speech.synthesize", "speech.synthesis")
    submit_turn = facts("product.w2.p2.submit.agent", "runtime.turn")
    submit_agent = facts("product.w2.p2.submit.agent", "agent.dispatch")
    activation = facts("product.w2.p2.activate", "runtime.queue")
    closure = facts("product.w2.p2.close", "runtime.queue")
    notification = facts("product.w2.p2.notification", "agent.progress")
    tool_call = facts("product.w2.agent.tool_call", "agent.progress")
    tool_result = facts("product.w2.agent.tool_result", "agent.progress")
    agent_final = facts("product.w2.agent.final", "agent.progress")
    presentation = facts("product.w2.p2.presentation", "runtime.presentation")
    barges = governed_facts("cancel.acknowledged", source="product.w2.p2.barge")
    task_create = facts("product.w2.task.create", "task.command")
    task_get = facts("product.w2.task.get", "task.progress")
    task_list = facts("product.w2.task.list", "runtime.queue")
    task_status = facts("product.w2.task.status", "task.progress")
    task_cancel = facts("product.w2.task.cancel", "task.command")
    task_retry = facts("product.w2.task.retry", "task.command")
    task_events = facts("product.w2.task.events", "task.progress")
    task_attempt = facts("product.w2.task.d0", "task.attempt")
    task_origin = facts("product.voice_task_origin", "runtime.turn")
    task_bridge = facts("product.voice_task_bridge", "task.command")
    task_progress = facts("product.w2.p3.progress", "task.progress")
    task_ui = facts("product.w2.p3.ui", "task.progress")
    state_events = governed_facts("task.state_observed", source="product.w2.task.event")
    failures = governed_facts("segment.failed")

    items: set[W2LedgerItem] = set()
    if recognition:
        items.add(W2LedgerItem.P1_RECOGNITION)
    if synthesis:
        items.add(W2LedgerItem.P1_SYNTHESIS)
    if any(
        _same_binding(captured, played, "interaction_id") and ordered(captured, played)
        for captured in capture
        for played in playout
    ):
        items.add(W2LedgerItem.P1_AUDIO)
    if any(
        failed.segment_name.startswith("speech.")
        and _same_binding(failed, submitted, "interaction_id")
        for failed in failures
        for submitted in submit_turn
    ):
        items.add(W2LedgerItem.P1_COMMIT_DEGRADATION)
        items.add(W2LedgerItem.CROSS_FAILURE)
    if any(
        _same_binding(opened, submitted, "interaction_id")
        and _same_binding(submitted, closed, "interaction_id")
        and ordered(opened, submitted, closed)
        for opened in activation
        for submitted in submit_turn
        for closed in closure
    ):
        items.add(W2LedgerItem.P2_RUNTIME)
    if any(
        _same_binding(
            sent, played, "interaction_id", "response_id", "response_generation"
        )
        and _same_binding(
            played, overlapped, "interaction_id", "response_id", "response_generation"
        )
        and _same_binding(overlapped, captured, "interaction_id")
        and ordered(sent, played, overlapped, captured)
        for sent in downlink
        for played in playout
        for overlapped in duplex
        for captured in capture
    ):
        items.add(W2LedgerItem.P2_MEDIA)
    if any(
        _same_binding(submitted, final, "round_id")
        and any(
            _same_binding(submitted, barge, "interaction_id")
            and _same_binding(final, barge, "response_id")
            for barge in barges
        )
        for submitted in submit_agent
        for final in notification + agent_final
    ):
        items.add(W2LedgerItem.P2_ENGINE)
    if any(
        _same_binding(submitted, call, "round_id")
        and any(_same_binding(call, result, "round_id") for result in tool_result)
        and any(
            _same_binding(result, final, "round_id")
            for result in tool_result
            for final in agent_final
        )
        for submitted in submit_agent
        for call in tool_call
    ):
        items.add(W2LedgerItem.P2_AGENT)
    if presentation:
        items.add(W2LedgerItem.P2_PRESENTATION)
    def by_task_attempt(
        records: Sequence[LiveVoiceObservation],
    ) -> dict[tuple[str, str], list[LiveVoiceObservation]]:
        indexed: dict[tuple[str, str], list[LiveVoiceObservation]] = {}
        for record in records:
            task_id = record.binding.task_id
            attempt_id = record.binding.attempt_id
            if task_id is None or attempt_id is None:
                continue
            indexed.setdefault((task_id, attempt_id), []).append(record)
        return indexed

    def ordered_chain(
        groups: Sequence[Sequence[LiveVoiceObservation]],
    ) -> tuple[LiveVoiceObservation, ...] | None:
        if not groups or any(not group for group in groups):
            return None
        chains = [(item,) for item in groups[0]]
        for group in groups[1:]:
            advanced: dict[int, tuple[LiveVoiceObservation, ...]] = {}
            for item in group:
                chain = next(
                    (
                        previous + (item,)
                        for previous in chains
                        if ordered(previous[-1], item)
                    ),
                    None,
                )
                if chain is not None:
                    advanced[id(item)] = chain
            chains = list(advanced.values())
            if not chains:
                return None
        return chains[0]

    create_by_pair = by_task_attempt(task_create)
    get_by_pair = by_task_attempt(task_get)
    status_by_pair = by_task_attempt(task_status)
    cancel_by_pair = by_task_attempt(task_cancel)
    events_by_pair = by_task_attempt(task_events)
    state_by_pair = by_task_attempt(state_events)
    core_cancel_witnesses: dict[str, _V2CoreCancelWitness] = {}
    ambiguous_core_tasks: set[str] = set()
    if task_list:
        for pair, creates in create_by_pair.items():
            task_id, attempt_id = pair
            terminal_records = [
                item
                for item in state_by_pair.get(pair, ())
                if item.state == "terminal"
            ]
            if not terminal_records or any(
                item.outcome != "cancelled" for item in terminal_records
            ):
                continue
            chain = None
            for create in creates:
                matching_groups = tuple(
                    [
                        item
                        for item in indexed.get(pair, ())
                        if _same_binding(create, item, "task_id", "attempt_id")
                    ]
                    for indexed in (
                        get_by_pair,
                        status_by_pair,
                        cancel_by_pair,
                        events_by_pair,
                    )
                )
                matching_list = [
                    item for item in task_list if _same_binding(create, item)
                ]
                matching_terminal = [
                    item
                    for item in terminal_records
                    if _same_binding(create, item, "task_id", "attempt_id")
                ]
                if not matching_list or any(not group for group in matching_groups):
                    continue
                chain = ordered_chain(
                    ([create], matching_groups[2], matching_terminal)
                )
                if chain is not None:
                    break
            if chain is None:
                continue
            if task_id in ambiguous_core_tasks:
                continue
            existing = core_cancel_witnesses.get(task_id)
            if existing is not None and existing.attempt_id != attempt_id:
                # One Core task cannot claim two competing cancellation attempts.
                core_cancel_witnesses.pop(task_id, None)
                ambiguous_core_tasks.add(task_id)
                continue
            core_cancel_witnesses[task_id] = _V2CoreCancelWitness(
                attempt_id=attempt_id,
                create=chain[0],
                cancel=chain[1],
                terminal=chain[-1],
            )
    core_task_ids = set(core_cancel_witnesses)
    if core_task_ids:
        items.add(W2LedgerItem.P3_CORE)

    restart_details = _derive_v2_restart_details(runtime)
    retry_by_task: dict[str, list[LiveVoiceObservation]] = {}
    for retry in task_retry:
        if retry.binding.task_id is not None:
            retry_by_task.setdefault(retry.binding.task_id, []).append(retry)
    d0_by_task: dict[str, list[LiveVoiceObservation]] = {}
    for attempt in task_attempt:
        if attempt.binding.task_id is not None:
            d0_by_task.setdefault(attempt.binding.task_id, []).append(attempt)

    attempt_sources = {
        "product.w2.task.create",
        "product.w2.task.get",
        "product.w2.task.status",
        "product.w2.task.cancel",
        "product.w2.task.retry",
        "product.w2.task.events",
        "product.w2.task.d0",
        "product.w2.task.event",
        "product.w2.task.reconciliation",
    }
    executor_tasks: set[str] = set()
    for task_id, core in core_cancel_witnesses.items():
        restart_attempt = restart_details.attempts_by_task.get(task_id)
        restart_initial = restart_details.predecessor_events.get(task_id)
        restart_terminal = restart_details.successor_events.get(task_id)
        retries = retry_by_task.get(task_id, [])
        d0_attempts = d0_by_task.get(task_id, [])
        if (
            restart_attempt is None
            or restart_initial is None
            or restart_terminal is None
            or len(retries) != 2
            or not d0_attempts
        ):
            continue
        first_retry, second_retry = retries
        if ordered(second_retry, first_retry):
            first_retry, second_retry = second_retry, first_retry
        elif not ordered(first_retry, second_retry):
            continue
        retry_b = first_retry.binding.attempt_id
        retry_c = second_retry.binding.attempt_id
        correlation_id = core.create.binding.correlation_id
        # The public observation schema has no caller-selectable attempt-number
        # field.  Exactly three identities plus two ordered retry completions
        # therefore proves B and C as attempts 2 and 3 without reinterpreting a
        # TaskEvent source_seq as an attempt ordinal.
        if (
            retry_b is None
            or retry_c is None
            or len({core.attempt_id, retry_b, retry_c}) != 3
            or restart_attempt != retry_c
            or any(
                item.binding.correlation_id != correlation_id
                for item in (
                    first_retry,
                    second_retry,
                    restart_initial,
                    restart_terminal,
                )
            )
        ):
            continue
        matching_d0 = [
            item
            for item in d0_attempts
            if item.binding.attempt_id == retry_b
            and item.binding.correlation_id == correlation_id
            and ordered(first_retry, item, second_retry)
        ]
        if not matching_d0 or any(
            item.binding.attempt_id != retry_b
            or item.binding.correlation_id != correlation_id
            for item in d0_attempts
        ):
            continue
        completed_attempt = matching_d0[0]
        observed_attempts = {
            item.binding.attempt_id
            for _, _, item in (*completed, *governed)
            if item.source_component in attempt_sources
            and item.binding.task_id == task_id
            and item.binding.attempt_id is not None
        }
        if observed_attempts != {core.attempt_id, retry_b, retry_c}:
            continue
        if not ordered(
            core.terminal,
            first_retry,
            completed_attempt,
            second_retry,
            restart_initial,
            restart_terminal,
        ):
            continue
        executor_tasks.add(task_id)
    if executor_tasks:
        items.add(W2LedgerItem.P3_EXECUTOR)
    bridged_task_ids = {
        bridge.binding.task_id
        for bridge in task_bridge
        if bridge.binding.task_id is not None
        and any(
            _same_binding(origin, bridge, "interaction_id", "turn_id")
            for origin in task_origin
        )
    }
    if bridged_task_ids:
        items.add(W2LedgerItem.P3_VOICE_BRIDGE)
    progressed_task_ids = {
        item.binding.task_id
        for item in task_progress
        if item.binding.task_id is not None
        and any(
            status.binding.task_id == item.binding.task_id for status in task_status
        )
        and any(
            events.binding.task_id == item.binding.task_id for events in task_events
        )
        and any(state.binding.task_id == item.binding.task_id for state in state_events)
    }
    if progressed_task_ids:
        items.add(W2LedgerItem.P3_PROGRESS)
    if any(item.binding.task_id in progressed_task_ids for item in task_ui):
        items.add(W2LedgerItem.P3_UI)
    if (
        any(
            _same_binding(recognized, submitted, "interaction_id")
            for recognized in recognition
            for submitted in submit_turn
        )
        and bridged_task_ids
    ):
        items.add(W2LedgerItem.CROSS_ROUTE)
    if bridged_task_ids and any(
        submitted.binding.task_id in bridged_task_ids for submitted in submit_turn
    ):
        items.add(W2LedgerItem.CROSS_CONTEXT)
    gateway_completed = [
        item for artifact, _, item in completed if artifact.producer_id == "gateway"
    ]
    agentserver_completed = [
        item for artifact, _, item in completed if artifact.producer_id == "agentserver"
    ]
    if any(
        _same_binding(gateway_item, agentserver_item, "interaction_id")
        and gateway_item.source_record_id is not None
        and agentserver_item.source_record_id is not None
        for gateway_item in gateway_completed
        for agentserver_item in agentserver_completed
    ):
        items.add(W2LedgerItem.CROSS_OBSERVABILITY)
    return frozenset(items)


@dataclass(frozen=True, slots=True)
class _V2JourneyWitness:
    step: W2JourneyStep
    correlation_id: str
    start: LiveVoiceObservation
    end: LiveVoiceObservation
    task_id: str | None = None


@dataclass(frozen=True, slots=True)
class _V2JourneyDerivation:
    steps: frozenset[W2JourneyStep]
    task_ids: frozenset[str]
    full_chain_correlations: frozenset[str]
    full_chain_task_ids: frozenset[str]


def _common_v2_journey_runtime_ids(
    runtime_id_sets: Sequence[set[str]],
) -> frozenset[str]:
    """Return the one exact runtime set used by every cumulative Gate step."""

    if len(runtime_id_sets) != len(W2JourneyStep) or not runtime_id_sets:
        return frozenset()
    first = runtime_id_sets[0]
    if not first or any(runtime_ids != first for runtime_ids in runtime_id_sets[1:]):
        return frozenset()
    return frozenset(first)


def _derive_v2_journey_steps(
    artifacts: Sequence[W2EvidenceArtifact],
) -> _V2JourneyDerivation:
    completed, governed = _v2_runtime_facts(artifacts)
    positions = {
        id(item): (artifact.artifact_id, index)
        for artifact, index, item in (*completed, *governed)
    }

    def ordered(*items: LiveVoiceObservation) -> bool:
        return _observations_are_ordered(positions, *items)

    def facts(source: str, segment: str) -> list[LiveVoiceObservation]:
        return [
            item
            for _, _, item in completed
            if item.source_component == source and item.segment_name == segment
        ]

    recognition = facts("product.w2.speech.recognize", "speech.recognition")
    synthesis = facts("product.w2.speech.synthesize", "speech.synthesis")
    submit = facts("product.w2.p2.submit.agent", "agent.dispatch")
    tool_call = facts("product.w2.agent.tool_call", "agent.progress")
    tool_result = facts("product.w2.agent.tool_result", "agent.progress")
    agent_final = facts("product.w2.agent.final", "agent.progress")
    presentation = facts("product.w2.p2.presentation", "runtime.presentation")
    origins = facts("product.voice_task_origin", "runtime.turn")
    bridges = facts("product.voice_task_bridge", "task.command")
    task_create = facts("product.w2.task.create", "task.command")
    task_status = facts("product.w2.task.status", "task.progress")
    task_events = facts("product.w2.task.events", "task.progress")
    progress = facts("product.w2.p3.progress", "task.progress")
    ui = facts("product.w2.p3.ui", "task.progress")
    barges = [
        item
        for _, _, item in governed
        if item.source_component == "product.w2.p2.barge"
        and item.event_name == "cancel.acknowledged"
        and item.cancel_scope == "playback.stop"
    ]
    failures = [item for _, _, item in governed if item.event_name == "segment.failed"]
    states = [
        item
        for _, _, item in governed
        if item.source_component == "product.w2.task.event"
        and item.event_name == "task.state_observed"
    ]
    witnesses: list[_V2JourneyWitness] = []
    witness_keys: set[tuple[W2JourneyStep, int, int, str | None]] = set()

    def add_witness(
        step: W2JourneyStep,
        start: LiveVoiceObservation,
        end: LiveVoiceObservation,
        *,
        task_id: str | None = None,
    ) -> None:
        if start.binding.correlation_id != end.binding.correlation_id:
            return
        key = (step, id(start), id(end), task_id)
        if key in witness_keys:
            return
        witness_keys.add(key)
        witnesses.append(
            _V2JourneyWitness(
                step=step,
                correlation_id=start.binding.correlation_id,
                start=start,
                end=end,
                task_id=task_id,
            )
        )

    for recognized in recognition:
        for dispatched in submit:
            for call in tool_call:
                for result in tool_result:
                    for final in agent_final:
                        for spoken in synthesis:
                            for shown in presentation:
                                if (
                                    _same_binding(
                                        recognized, dispatched, "interaction_id"
                                    )
                                    and _same_binding(dispatched, call, "round_id")
                                    and _same_binding(call, result, "round_id")
                                    and _same_binding(result, final, "round_id")
                                    and _same_binding(
                                        dispatched,
                                        spoken,
                                        "interaction_id",
                                        "response_id",
                                    )
                                    and _same_binding(
                                        dispatched,
                                        shown,
                                        "interaction_id",
                                        "response_id",
                                    )
                                    and ordered(
                                        recognized,
                                        dispatched,
                                        call,
                                        result,
                                        final,
                                    )
                                    and ordered(final, spoken)
                                    and ordered(final, shown)
                                ):
                                    if ordered(spoken, shown):
                                        response_end = shown
                                    elif ordered(shown, spoken):
                                        response_end = spoken
                                    else:
                                        continue
                                    add_witness(
                                        W2JourneyStep.REAL_AGENT_TOOL_SPEECH,
                                        recognized,
                                        response_end,
                                    )
    for dispatched in submit:
        for barge in barges:
            if _same_binding(
                dispatched, barge, "interaction_id", "response_id"
            ) and ordered(dispatched, barge):
                add_witness(
                    W2JourneyStep.NONBLOCKING_OR_INTERRUPTION,
                    dispatched,
                    barge,
                )

    for bridge in bridges:
        task_id = bridge.binding.task_id
        attempt_id = bridge.binding.attempt_id
        if task_id is None or attempt_id is None:
            continue
        for origin in origins:
            if not _same_binding(origin, bridge, "interaction_id", "turn_id"):
                continue
            for created in task_create:
                if not _same_binding(
                    bridge, created, "task_id", "attempt_id"
                ) or not ordered(origin, created, bridge):
                    continue
                for active in states:
                    if active.state not in {
                        "accepted",
                        "running",
                        "blocked",
                        "decision_required",
                    } or not _same_binding(created, active, "task_id", "attempt_id"):
                        continue
                    for dispatched in submit:
                        if not _same_binding(
                            active, dispatched, "task_id", "attempt_id"
                        ):
                            continue
                        for terminal in states:
                            if (
                                terminal.state != "terminal"
                                or terminal.outcome is None
                                or not _same_binding(
                                    dispatched,
                                    terminal,
                                    "task_id",
                                    "attempt_id",
                                )
                                or not ordered(
                                    origin,
                                    created,
                                    bridge,
                                    active,
                                    dispatched,
                                    terminal,
                                )
                            ):
                                continue
                            projections = (task_status, task_events, progress, ui)
                            matching_projections = [
                                [
                                    item
                                    for item in group
                                    if (
                                        _same_binding(
                                            terminal,
                                            item,
                                            "task_id",
                                            "attempt_id",
                                        )
                                        and ordered(terminal, item)
                                    )
                                ]
                                for group in projections
                            ]
                            if not all(matching_projections):
                                continue
                            projection_end = max(
                                (
                                    item
                                    for group in matching_projections
                                    for item in group
                                ),
                                key=lambda item: (
                                    datetime.fromisoformat(
                                        item.observed_at.replace("Z", "+00:00")
                                    ),
                                    positions[id(item)],
                                ),
                            )
                            add_witness(
                                W2JourneyStep.CONFIRMED_TASK_CREATE,
                                origin,
                                bridge,
                                task_id=task_id,
                            )
                            add_witness(
                                W2JourneyStep.CONVERSATION_DURING_TASK,
                                active,
                                dispatched,
                                task_id=task_id,
                            )
                            add_witness(
                                W2JourneyStep.EXACT_TASK_RESULT,
                                terminal,
                                projection_end,
                                task_id=task_id,
                            )

    for failed in failures:
        for dispatched in submit:
            if (
                failed.segment_name.startswith("speech.")
                and _same_binding(failed, dispatched, "interaction_id")
                and ordered(failed, dispatched)
            ):
                add_witness(
                    W2JourneyStep.TEXT_DEGRADATION,
                    failed,
                    dispatched,
                )
    gateway_completed = [
        item for artifact, _, item in completed if artifact.producer_id == "gateway"
    ]
    agentserver_completed = [
        item for artifact, _, item in completed if artifact.producer_id == "agentserver"
    ]
    for gateway_item in gateway_completed:
        for agentserver_item in agentserver_completed:
            if not (
                _same_binding(gateway_item, agentserver_item, "interaction_id")
                and gateway_item.source_record_id is not None
                and agentserver_item.source_record_id is not None
            ):
                continue
            if ordered(gateway_item, agentserver_item):
                start, end = gateway_item, agentserver_item
            elif ordered(agentserver_item, gateway_item):
                start, end = agentserver_item, gateway_item
            else:
                continue
            add_witness(W2JourneyStep.ROUTE_TELEMETRY, start, end)

    full_chain_correlations: set[str] = set()
    full_chain_task_ids: set[str] = set()
    required_steps = tuple(W2JourneyStep)
    for correlation_id in {item.correlation_id for item in witnesses}:
        by_step = {
            step: [
                item
                for item in witnesses
                if item.correlation_id == correlation_id and item.step is step
            ]
            for step in required_steps
        }
        if any(not by_step[step] for step in required_steps):
            continue
        states: list[tuple[LiveVoiceObservation, str | None]] = [
            (item.end, item.task_id) for item in by_step[required_steps[0]]
        ]
        for step in required_steps[1:]:
            next_states: dict[
                tuple[int, str | None], tuple[LiveVoiceObservation, str | None]
            ] = {}
            for item in by_step[step]:
                for previous_end, state_task_id in states:
                    if not ordered(previous_end, item.start):
                        continue
                    if (
                        state_task_id is not None
                        and item.task_id is not None
                        and state_task_id != item.task_id
                    ):
                        continue
                    task_id = state_task_id or item.task_id
                    next_states[(id(item.end), task_id)] = (item.end, task_id)
            states = list(next_states.values())
            if not states:
                break
        if states:
            full_chain_correlations.add(correlation_id)
            full_chain_task_ids.update(
                task_id for _, task_id in states if task_id is not None
            )

    return _V2JourneyDerivation(
        steps=frozenset(item.step for item in witnesses),
        task_ids=frozenset(
            item.task_id for item in witnesses if item.task_id is not None
        ),
        full_chain_correlations=frozenset(full_chain_correlations),
        full_chain_task_ids=frozenset(full_chain_task_ids),
    )


_V2_RETRIABLE_ERRORS: Final = frozenset(
    {"TIMEOUT", "CAPABILITY_UNAVAILABLE", "UNAVAILABLE"}
)
_V2_NON_RETRIABLE_ERRORS: Final = frozenset(
    {"INVALID_ARGUMENT", "UNSUPPORTED", "CONFLICT", "PROTOCOL_VIOLATION"}
)


def _v2_fault_matches_plane(
    observation: LiveVoiceObservation, plane: W2CapabilityPlane
) -> bool:
    if plane is W2CapabilityPlane.P1_SPEECH_MEDIA:
        return observation.segment_name.startswith("speech.")
    if plane is W2CapabilityPlane.P2_CONVERSATION:
        return observation.segment_name.startswith(("runtime.", "agent."))
    if plane is W2CapabilityPlane.P3_TASK:
        return observation.segment_name.startswith("task.")
    return False


def _derive_v2_fault_class(
    artifacts: Sequence[W2EvidenceArtifact],
    *,
    plane: W2CapabilityPlane,
    fault_class: str,
    expected_source_record_id: str | None = None,
    expected_source_component: str | None = None,
    expected_segment_name: str | None = None,
) -> bool:
    """Derive one injected-fault class from closed runtime facts, not booleans."""

    runtime = [
        artifact
        for artifact in artifacts
        if artifact.runtime_format_version == 2
        and W2EvidenceKind.REAL_RUNTIME in artifact.evidence_kinds
    ]
    if not runtime or plane is W2CapabilityPlane.OBSERVABILITY:
        return False
    completed, governed = _v2_runtime_facts(runtime)
    failures = [
        (artifact, index, item)
        for artifact, index, item in governed
        if item.event_name == "segment.failed"
        and _v2_fault_matches_plane(item, plane)
        and (
            expected_source_record_id is None
            or item.source_record_id == expected_source_record_id
        )
        and (
            expected_source_component is None
            or item.source_component == expected_source_component
        )
        and (
            expected_segment_name is None
            or item.segment_name == expected_segment_name
        )
    ]
    if fault_class == "retriable":
        return any(item.error_code in _V2_RETRIABLE_ERRORS for _, _, item in failures)
    if fault_class == "non_retriable":
        return any(
            item.error_code in _V2_NON_RETRIABLE_ERRORS for _, _, item in failures
        )
    if fault_class != "zero_effect":
        return False
    stale_failures = [
        (artifact, index, item)
        for artifact, index, item in failures
        if item.error_code == "STALE"
    ]
    return bool(stale_failures) and all(
        not any(
            completed_item.source_record_id == failed_item.source_record_id
            or (
                completed_item.source_component == failed_item.source_component
                and _same_binding(completed_item, failed_item)
            )
            for _, _, completed_item in completed
        )
        for _, _, failed_item in stale_failures
    )


_W2_PRODUCT_FAULT_RUNTIME_BINDINGS: Final = MappingProxyType(
    {
        (W2PlannedFaultPlane.P1_SPEECH_MEDIA, W2PlannedFaultClass.RETRIABLE): (
            "product.w2.speech.recognize",
            "speech.recognition",
        ),
        (W2PlannedFaultPlane.P1_SPEECH_MEDIA, W2PlannedFaultClass.NON_RETRIABLE): (
            "product.w2.speech.recognize",
            "speech.recognition",
        ),
        (W2PlannedFaultPlane.P1_SPEECH_MEDIA, W2PlannedFaultClass.ZERO_EFFECT): (
            "product.w2.speech.recognize",
            "speech.recognition",
        ),
        (W2PlannedFaultPlane.P2_CONVERSATION, W2PlannedFaultClass.RETRIABLE): (
            "product.w2.p2.presentation",
            "runtime.presentation",
        ),
        (W2PlannedFaultPlane.P2_CONVERSATION, W2PlannedFaultClass.NON_RETRIABLE): (
            "product.w2.p2.presentation",
            "runtime.presentation",
        ),
        (W2PlannedFaultPlane.P2_CONVERSATION, W2PlannedFaultClass.ZERO_EFFECT): (
            "product.w2.p2.presentation",
            "runtime.presentation",
        ),
        (W2PlannedFaultPlane.P3_TASK, W2PlannedFaultClass.RETRIABLE): (
            "product.w2.p3.progress",
            "task.progress",
        ),
        (W2PlannedFaultPlane.P3_TASK, W2PlannedFaultClass.NON_RETRIABLE): (
            "product.w2.task.retry",
            "task.command",
        ),
        (W2PlannedFaultPlane.P3_TASK, W2PlannedFaultClass.ZERO_EFFECT): (
            "product.w2.task.retry",
            "task.command",
        ),
    }
)


def verify_w2_planned_product_faults(
    *,
    artifacts: Sequence[W2EvidenceArtifact],
    faults: Sequence[W2FaultEvidence],
    trust_policy: W2EvidenceTrustPolicy,
) -> None:
    """Require all nine product faults to match the signed policy-derived plan."""

    if not isinstance(trust_policy, W2EvidenceTrustPolicy):
        raise W2GateContractViolation("signed W2 trust policy is required")
    if (
        trust_policy.policy_id is None
        or trust_policy.candidate_binding is None
        or trust_policy.evidence_set_id is None
    ):
        raise W2GateContractViolation(
            "signed W2 trust policy lacks exact fault-plan authority"
        )
    plan = derive_w2_product_fault_plan(
        policy_id=trust_policy.policy_id,
        candidate_sha=trust_policy.candidate_binding[0],
        evidence_set_id=trust_policy.evidence_set_id,
    )
    artifact_by_id = _unique_by_key(
        artifacts,
        lambda artifact: artifact.artifact_id,
        W2EvidenceArtifact,
        "artifact",
    )
    fault_by_plane = _unique_by_key(
        faults,
        lambda evidence: evidence.plane,
        W2FaultEvidence,
        "fault plane",
    )
    slots_by_run = {
        run: tuple(
            slot for slot in trust_policy.runtime_slots if slot.showcase_run == run
        )
        for run in (1, 2, 3)
    }

    for identity in plan.items:
        plane = W2CapabilityPlane(identity.plane.value)
        evidence = fault_by_plane.get(plane)
        if evidence is None:
            raise W2GateContractViolation(
                f"planned product fault is omitted: {identity.plane.value}:"
                f"{identity.fault_class.value}"
            )
        evidence_ids = {
            W2PlannedFaultClass.RETRIABLE: evidence.retriable_evidence_ids,
            W2PlannedFaultClass.NON_RETRIABLE: evidence.non_retriable_evidence_ids,
            W2PlannedFaultClass.ZERO_EFFECT: evidence.zero_effect_evidence_ids,
        }[identity.fault_class]
        slots = slots_by_run[identity.pair]
        expected_runtime_ids = {slot.artifact_id for slot in slots}
        if (
            len(slots) != 2
            or {slot.producer_id for slot in slots} != {"gateway", "agentserver"}
        ):
            raise W2GateContractViolation(
                f"planned product fault pair {identity.pair} lacks exact runtime slots"
            )
        declared_runtime_ids = {
            evidence_id
            for evidence_id in evidence_ids
            if evidence_id in artifact_by_id
            and W2EvidenceKind.REAL_RUNTIME
            in artifact_by_id[evidence_id].evidence_kinds
        }
        if declared_runtime_ids != expected_runtime_ids:
            raise W2GateContractViolation(
                f"planned product fault uses the wrong runtime pair: "
                f"{identity.plane.value}:{identity.fault_class.value}"
            )
        pair_artifacts = tuple(artifact_by_id[item] for item in expected_runtime_ids)
        source_component, segment_name = _W2_PRODUCT_FAULT_RUNTIME_BINDINGS[
            (identity.plane, identity.fault_class)
        ]
        _, governed = _v2_runtime_facts(pair_artifacts)
        relevant_failures = [
            observation
            for _, _, observation in governed
            if observation.event_name == "segment.failed"
            and observation.source_component == source_component
            and observation.segment_name == segment_name
        ]
        expected_errors = {
            W2PlannedFaultClass.RETRIABLE: _V2_RETRIABLE_ERRORS,
            W2PlannedFaultClass.NON_RETRIABLE: _V2_NON_RETRIABLE_ERRORS,
            W2PlannedFaultClass.ZERO_EFFECT: frozenset({"STALE"}),
        }[identity.fault_class]
        if (
            not relevant_failures
            or {item.source_record_id for item in relevant_failures}
            != {identity.source_record_id}
            or any(item.error_code not in expected_errors for item in relevant_failures)
            or not _derive_v2_fault_class(
                pair_artifacts,
                plane=plane,
                fault_class=identity.fault_class.value,
                expected_source_record_id=identity.source_record_id,
                expected_source_component=source_component,
                expected_segment_name=segment_name,
            )
        ):
            raise W2GateContractViolation(
                f"planned product fault lacks one exact runtime failure: "
                f"{identity.plane.value}:{identity.fault_class.value}"
            )


@dataclass(frozen=True, slots=True)
class _V2RestartDerivation:
    """Closed restart derivation plus fail-closed diagnostics.

    Valid witnesses remain visible for unaffected tasks even when another task
    is contradictory.  The Gate separately treats every diagnostic as a
    failure, so retaining those witnesses can never turn partial evidence into
    acceptance credit.
    """

    valid_artifact_pairs: frozenset[tuple[str, str]]
    valid_task_attempt_pairs: frozenset[tuple[str, str]]
    tasks: Mapping[str, W2ReconciliationOutcome]
    attempts_by_task: Mapping[str, str]
    predecessor_events: Mapping[str, LiveVoiceObservation]
    successor_events: Mapping[str, LiveVoiceObservation]
    diagnostics: tuple[str, ...]


def _derive_v2_restart_details(
    artifacts: Sequence[W2EvidenceArtifact],
) -> _V2RestartDerivation:
    """Derive exact predecessor-close/successor reconciliation ownership."""

    diagnostics: list[str] = []
    runtime: dict[str, W2EvidenceArtifact] = {}
    for artifact in artifacts:
        if (
            artifact.runtime_format_version != 2
            or artifact.producer_id != "agentserver"
            or W2EvidenceKind.REAL_RUNTIME not in artifact.evidence_kinds
        ):
            continue
        if artifact.artifact_id in runtime:
            diagnostics.append(f"duplicate_artifact:{artifact.artifact_id}")
            continue
        runtime[artifact.artifact_id] = artifact

    valid_artifact_pairs: set[tuple[str, str]] = set()
    invalid_tasks: set[str] = set()
    candidates: dict[
        str,
        list[
            tuple[
                str,
                W2ReconciliationOutcome,
                LiveVoiceObservation,
                LiveVoiceObservation,
            ]
        ],
    ] = {}
    nonterminal_states = {"accepted", "running", "blocked", "decision_required"}

    for successor in sorted(runtime.values(), key=lambda item: (item.sequence, item.artifact_id)):
        predecessor_id = successor.predecessor_artifact_id
        if predecessor_id is None:
            continue
        predecessor = runtime.get(predecessor_id)
        if predecessor is None:
            diagnostics.append(
                f"missing_predecessor:{successor.artifact_id}:{predecessor_id}"
            )
            continue
        pair = (predecessor.artifact_id, successor.artifact_id)
        if predecessor.evidence_set_id != successor.evidence_set_id:
            diagnostics.append(
                f"evidence_set_mismatch:{predecessor.artifact_id}:{successor.artifact_id}"
            )
            continue
        if predecessor.process_epoch == successor.process_epoch:
            diagnostics.append(
                f"epoch_not_advanced:{predecessor.artifact_id}:{successor.artifact_id}"
            )
            continue
        if predecessor.sequence >= successor.sequence:
            diagnostics.append(
                f"artifact_seq_not_advanced:{predecessor.artifact_id}:"
                f"{successor.artifact_id}"
            )
            continue
        valid_artifact_pairs.add(pair)

        predecessor_by_task: dict[str, list[LiveVoiceObservation]] = {}
        for item in predecessor.runtime_observations:
            task_id = item.binding.task_id
            if (
                item.source_component == "product.w2.task.event"
                and item.event_name == "task.state_observed"
                and task_id is not None
                and item.binding.attempt_id is not None
                and item.source_seq is not None
            ):
                predecessor_by_task.setdefault(task_id, []).append(item)

        current: dict[tuple[str, str], LiveVoiceObservation] = {}
        for task_id, task_records in predecessor_by_task.items():
            latest_seq = max(item.source_seq for item in task_records if item.source_seq is not None)
            latest = [item for item in task_records if item.source_seq == latest_seq]
            if len(latest) != 1:
                signatures = {
                    (item.binding.attempt_id, item.state, item.outcome) for item in latest
                }
                diagnostic = (
                    "predecessor_latest_conflict"
                    if len(signatures) > 1
                    else "predecessor_latest_duplicate"
                )
                diagnostics.append(f"{diagnostic}:{task_id}:{latest_seq}")
                invalid_tasks.add(task_id)
                continue
            initial = latest[0]
            attempt_id = initial.binding.attempt_id
            if initial.state in nonterminal_states and attempt_id is not None:
                current[(task_id, attempt_id)] = initial

        successor_records = [
            item
            for item in successor.runtime_observations
            if item.source_component == "product.w2.task.reconciliation"
            and item.event_name == "task.state_observed"
            and item.binding.task_id is not None
            and item.binding.attempt_id is not None
            and item.source_seq is not None
        ]
        successor_by_pair: dict[tuple[str, str], list[LiveVoiceObservation]] = {}
        successor_attempts_by_task: dict[str, set[str]] = {}
        for item in successor_records:
            task_id = item.binding.task_id
            attempt_id = item.binding.attempt_id
            assert task_id is not None and attempt_id is not None
            successor_attempts_by_task.setdefault(task_id, set()).add(attempt_id)
            successor_by_pair.setdefault((task_id, attempt_id), []).append(item)
            if item.state != "terminal" or item.outcome is None:
                diagnostics.append(
                    f"successor_nonterminal:{task_id}:{attempt_id}:{item.source_seq}"
                )
                invalid_tasks.add(task_id)
        for task_id, attempt_ids in successor_attempts_by_task.items():
            if len(attempt_ids) > 1:
                diagnostics.append(f"successor_multiple_attempts:{task_id}")
                invalid_tasks.add(task_id)

        expected_pairs = set(current)
        actual_pairs = set(successor_by_pair)
        for task_id, attempt_id in sorted(expected_pairs - actual_pairs):
            diagnostics.append(f"successor_missing:{task_id}:{attempt_id}")
            invalid_tasks.add(task_id)
        for task_id, attempt_id in sorted(actual_pairs - expected_pairs):
            diagnostics.append(f"successor_extra:{task_id}:{attempt_id}")
            invalid_tasks.add(task_id)

        for task_id, attempt_id in sorted(expected_pairs & actual_pairs):
            initial = current[(task_id, attempt_id)]
            terminals = successor_by_pair[(task_id, attempt_id)]
            if len(terminals) != 1:
                outcomes = {item.outcome for item in terminals}
                diagnostic = (
                    "successor_raw_outcome_conflict"
                    if len(outcomes) > 1
                    else "successor_duplicate"
                )
                diagnostics.append(f"{diagnostic}:{task_id}:{attempt_id}")
                invalid_tasks.add(task_id)
                continue
            terminal = terminals[0]
            if initial.binding.correlation_id != terminal.binding.correlation_id:
                diagnostics.append(
                    f"successor_binding_conflict:{task_id}:{attempt_id}"
                )
                invalid_tasks.add(task_id)
                continue
            assert initial.source_seq is not None and terminal.source_seq is not None
            if terminal.source_seq <= initial.source_seq:
                diagnostics.append(
                    f"task_seq_not_advanced:{task_id}:{attempt_id}:"
                    f"{initial.source_seq}:{terminal.source_seq}"
                )
                invalid_tasks.add(task_id)
                continue
            outcome = {
                "interrupted": W2ReconciliationOutcome.INTERRUPTED,
                "unknown": W2ReconciliationOutcome.UNKNOWN,
            }.get(terminal.outcome, W2ReconciliationOutcome.TERMINAL)
            candidates.setdefault(task_id, []).append(
                (attempt_id, outcome, initial, terminal)
            )

    tasks: dict[str, W2ReconciliationOutcome] = {}
    attempts_by_task: dict[str, str] = {}
    predecessor_events: dict[str, LiveVoiceObservation] = {}
    successor_events: dict[str, LiveVoiceObservation] = {}
    for task_id, task_candidates in sorted(candidates.items()):
        if task_id in invalid_tasks:
            continue
        if len(task_candidates) != 1:
            diagnostics.append(f"task_reconciled_multiple_times:{task_id}")
            continue
        attempt_id, outcome, initial, terminal = task_candidates[0]
        tasks[task_id] = outcome
        attempts_by_task[task_id] = attempt_id
        predecessor_events[task_id] = initial
        successor_events[task_id] = terminal

    unique_diagnostics = tuple(dict.fromkeys(diagnostics))
    return _V2RestartDerivation(
        valid_artifact_pairs=frozenset(valid_artifact_pairs),
        valid_task_attempt_pairs=frozenset(attempts_by_task.items()),
        tasks=MappingProxyType(tasks),
        attempts_by_task=MappingProxyType(attempts_by_task),
        predecessor_events=MappingProxyType(predecessor_events),
        successor_events=MappingProxyType(successor_events),
        diagnostics=unique_diagnostics,
    )


def _derive_v2_restart(
    artifacts: Sequence[W2EvidenceArtifact],
) -> Mapping[str, W2ReconciliationOutcome]:
    """Return the compatibility task/outcome mapping for valid restart witnesses."""

    return _derive_v2_restart_details(artifacts).tasks


def _artifact_kinds(
    evidence_ids: tuple[str, ...], artifacts: Mapping[str, W2EvidenceArtifact]
) -> frozenset[W2EvidenceKind]:
    missing = set(evidence_ids) - set(artifacts)
    if missing:
        raise W2GateContractViolation(
            "an evidence claim references an unknown artifact"
        )
    return frozenset(
        kind
        for evidence_id in evidence_ids
        for kind in artifacts[evidence_id].evidence_kinds
    )


def _has_attested_content_link(
    evidence_ids: tuple[str, ...], artifacts: Mapping[str, W2EvidenceArtifact]
) -> bool:
    referenced = [artifacts[evidence_id] for evidence_id in evidence_ids]
    claimed_digests = {
        digest for artifact in referenced for digest in artifact.attested_content_sha256
    }
    observed_digests = {
        artifact.content_sha256
        for artifact in referenced
        if not artifact.attested_content_sha256
    }
    return bool(claimed_digests & observed_digests)


def _has_subject_attestation(
    evidence_ids: tuple[str, ...],
    artifacts: Mapping[str, W2EvidenceArtifact],
    *,
    subject: str,
    required_kind: W2EvidenceKind,
) -> bool:
    referenced = [artifacts[evidence_id] for evidence_id in evidence_ids]
    observed_digests = {
        artifact.content_sha256
        for artifact in referenced
        if not artifact.attested_content_sha256 and subject in artifact.proven_subjects
    }
    return any(
        required_kind in artifact.evidence_kinds
        and subject in artifact.proven_subjects
        and bool(artifact.attested_content_sha256 & observed_digests)
        for artifact in referenced
    )


def _has_v2_claim_attestation(
    evidence_ids: tuple[str, ...],
    artifacts: Mapping[str, W2EvidenceArtifact],
    *,
    subject: str,
    required_kind: W2EvidenceKind,
) -> bool:
    runtime_digests = {
        artifacts[evidence_id].content_sha256
        for evidence_id in evidence_ids
        if artifacts[evidence_id].runtime_format_version == 2
    }
    evidence_sets = {
        artifacts[evidence_id].evidence_set_id
        for evidence_id in evidence_ids
        if artifacts[evidence_id].runtime_format_version == 2
    }
    return bool(runtime_digests) and any(
        required_kind in artifact.evidence_kinds
        and subject in artifact.proven_subjects
        and artifact.receipt_evidence_set_id in evidence_sets
        and runtime_digests.issubset(artifact.attested_content_sha256)
        for artifact in (artifacts[evidence_id] for evidence_id in evidence_ids)
    )


def _subjects_for(
    evidence_ids: tuple[str, ...], artifacts: Mapping[str, W2EvidenceArtifact]
) -> frozenset[str]:
    return frozenset(
        subject
        for evidence_id in evidence_ids
        for subject in artifacts[evidence_id].proven_subjects
    )


def evaluate_w2_demo_gate(
    *,
    candidate: W2CandidateEvidence,
    artifacts: Sequence[W2EvidenceArtifact],
    verification: W2AutomatedVerificationEvidence,
    awards: Sequence[W2LedgerAward],
    invariants: Sequence[W2InvariantEvidence],
    showcase_runs: Sequence[W2ShowcaseRun],
    journey_steps: Sequence[W2JourneyStepEvidence],
    faults: Sequence[W2FaultEvidence],
    restart: W2RestartEvidence,
) -> W2GateResult:
    """Evaluate one complete record without filling or inferring missing facts."""

    if not isinstance(candidate, W2CandidateEvidence):
        raise W2GateContractViolation("candidate evidence is required")
    if not isinstance(verification, W2AutomatedVerificationEvidence):
        raise W2GateContractViolation("Gate 1 verification evidence is required")
    if not isinstance(restart, W2RestartEvidence):
        raise W2GateContractViolation("restart evidence is required")
    artifact_by_id = _unique_by_key(
        artifacts, lambda artifact: artifact.artifact_id, W2EvidenceArtifact, "artifact"
    )
    _unique_by_key(
        artifacts,
        lambda artifact: artifact.sequence,
        W2EvidenceArtifact,
        "artifact sequence",
    )
    award_by_item = _unique_by_key(
        awards, lambda award: award.item, W2LedgerAward, "ledger item"
    )
    invariant_by_id = _unique_by_key(
        invariants,
        lambda evidence: evidence.invariant,
        W2InvariantEvidence,
        "invariant",
    )
    run_by_number = _unique_by_key(
        showcase_runs, lambda run: run.run_number, W2ShowcaseRun, "showcase run"
    )
    journey_by_step = _unique_by_key(
        journey_steps,
        lambda evidence: evidence.step,
        W2JourneyStepEvidence,
        "journey step",
    )
    fault_by_plane = _unique_by_key(
        faults, lambda evidence: evidence.plane, W2FaultEvidence, "fault plane"
    )

    failures: list[str] = []
    candidate_binding = (
        candidate.candidate_sha,
        candidate.environment_id,
        candidate.session_id,
        candidate.mode_id,
    )
    if any(
        (
            artifact.candidate_sha,
            artifact.environment_id,
            artifact.session_id,
            artifact.mode_id,
        )
        != candidate_binding
        for artifact in artifact_by_id.values()
    ):
        failures.append("an evidence artifact is not bound to this candidate record")
    runtime_artifacts = [
        artifact
        for artifact in artifact_by_id.values()
        if W2EvidenceKind.REAL_RUNTIME in artifact.evidence_kinds
        and artifact.runtime_format_version in {1, 2}
    ]
    if any(artifact.runtime_format_version == 2 for artifact in runtime_artifacts):
        if any(artifact.runtime_format_version != 2 for artifact in runtime_artifacts):
            failures.append("v2 evidence set mixes legacy runtime artifacts")
        if len({artifact.evidence_set_id for artifact in runtime_artifacts}) != 1:
            failures.append("v2 runtime artifacts do not share one evidence set")
        if not {artifact.producer_id for artifact in runtime_artifacts}.issuperset(
            {"gateway", "agentserver"}
        ):
            failures.append("v2 evidence set lacks both runtime producers")
        for artifact in runtime_artifacts:
            predecessor_id = artifact.predecessor_artifact_id
            if predecessor_id is None:
                continue
            predecessor = artifact_by_id.get(predecessor_id)
            if (
                predecessor is None
                or predecessor.runtime_format_version != 2
                or predecessor.producer_id != artifact.producer_id
                or predecessor.sequence >= artifact.sequence
                or predecessor.process_epoch == artifact.process_epoch
            ):
                failures.append(
                    f"runtime artifact {artifact.artifact_id} has an invalid predecessor"
                )
        restart_details = _derive_v2_restart_details(runtime_artifacts)
        failures.extend(
            f"restart evidence diagnostic: {diagnostic}"
            for diagnostic in restart_details.diagnostics
        )
    if len({artifact.source_label for artifact in artifact_by_id.values()}) != len(
        artifact_by_id
    ):
        failures.append("evidence artifacts reuse a source label")
    if len({artifact.content_sha256 for artifact in artifact_by_id.values()}) != len(
        artifact_by_id
    ):
        failures.append("evidence artifacts reuse content")
    all_subjects = frozenset(
        subject
        for artifact in artifact_by_id.values()
        for subject in artifact.proven_subjects
    )

    section_scores = {section: 0 for section in W2Section}
    for item, award in award_by_item.items():
        artifact_kinds = _artifact_kinds(award.evidence_ids, artifact_by_id)
        if artifact_kinds != award.evidence_kinds:
            failures.append(f"ledger item {item.value} self-declared evidence kinds")
        claim_artifacts = [
            artifact_by_id[evidence_id] for evidence_id in award.evidence_ids
        ]
        v2_proven_items = _derive_v2_runtime_items(claim_artifacts)
        proven_items = (
            frozenset(
                proven
                for artifact in claim_artifacts
                for proven in artifact.proven_ledger_items
            )
            | v2_proven_items
        )
        target_items = (
            frozenset(
                proven
                for artifact in claim_artifacts
                for proven in artifact.proven_target_items
            )
            | v2_proven_items
        )
        route_classes = {
            artifact.proven_route_classes[item]
            for artifact in claim_artifacts
            if item in artifact.proven_route_classes
        }
        if item in v2_proven_items:
            route_classes.add(W2RouteClass.FORMAL)
        route_class = next(iter(route_classes)) if len(route_classes) == 1 else None
        required_kinds = _ITEM_REQUIRED_KINDS[item]
        supporting_attestations_passed = all(
            (
                _has_v2_claim_attestation(
                    award.evidence_ids,
                    artifact_by_id,
                    subject=f"ledger:{item.value}",
                    required_kind=kind,
                )
                if v2_proven_items
                else _has_subject_attestation(
                    award.evidence_ids,
                    artifact_by_id,
                    subject=f"ledger:{item.value}",
                    required_kind=kind,
                )
            )
            for kind in required_kinds
            if kind
            not in {
                W2EvidenceKind.REAL_RUNTIME,
                W2EvidenceKind.AUTOMATED_CONFORMANCE,
            }
        )
        verified_points = (
            _ITEM_MAX[item]
            if item in proven_items
            and required_kinds.issubset(artifact_kinds)
            and supporting_attestations_passed
            else 0
        )
        section_scores[_ITEM_SECTION[item]] += verified_points
        if award.points != verified_points:
            failures.append(
                f"ledger item {item.value} points were not derived from evidence"
            )
        if award.route_class is not route_class:
            failures.append(
                f"ledger item {item.value} route class was not derived from evidence"
            )
        if award.target_route_owned is not (item in target_items):
            failures.append(
                f"ledger item {item.value} target ownership was not derived from evidence"
            )
    if any(section_scores[section] > _SECTION_MAX[section] for section in W2Section):
        raise W2GateContractViolation("section score exceeds immutable maximum")

    if set(award_by_item) != set(W2LedgerItem):
        failures.append("itemized Replacement Ledger evidence is incomplete")
    candidate_requirements = (
        ("worktree_clean", candidate.worktree_clean, "candidate worktree is not clean"),
        (
            "isolated_runtime_data_observed",
            candidate.isolated_runtime_data_observed,
            "isolated runtime data boundary was not observed",
        ),
        (
            "secrets_boundary_recorded",
            candidate.secrets_boundary_recorded,
            "secrets boundary was not recorded",
        ),
        (
            "routes_and_flags_recorded",
            candidate.routes_and_flags_recorded,
            "routes and flags were not recorded",
        ),
        (
            "real_source_facts_observed",
            candidate.real_source_facts_observed,
            "real Agent/Tool/task source facts were not observed",
        ),
        (
            "sanitized_route_trace_observed",
            candidate.sanitized_route_trace_observed,
            "sanitized route ownership trace was not observed",
        ),
    )
    for field_name, passed, message in candidate_requirements:
        if not passed:
            failures.append(message)
        elif f"candidate:{field_name}" not in all_subjects:
            failures.append(f"candidate fact {field_name} lacks signed proof")
        elif field_name in {
            "real_source_facts_observed",
            "sanitized_route_trace_observed",
        } and not any(
            W2EvidenceKind.REAL_RUNTIME in artifact.evidence_kinds
            and f"candidate:{field_name}" in artifact.proven_subjects
            for artifact in artifact_by_id.values()
        ):
            failures.append(f"candidate fact {field_name} lacks runtime-derived proof")

    verification_kinds = _artifact_kinds(verification.evidence_ids, artifact_by_id)
    if not {
        W2EvidenceKind.AUTOMATED_CONFORMANCE,
        W2EvidenceKind.INDEPENDENT_REVIEW,
    }.issubset(verification_kinds):
        failures.append("Gate 1 artifacts lack automated and independent review proof")
    if not _has_subject_attestation(
        verification.evidence_ids,
        artifact_by_id,
        subject="review:gate1",
        required_kind=W2EvidenceKind.INDEPENDENT_REVIEW,
    ):
        failures.append("Gate 1 review receipt is not bound to its reviewed artifact")
    verification_fields = (
        "affected_python_passed",
        "affected_web_passed",
        "frontend_build_passed",
        "negative_fault_and_flag_off_passed",
        "required_reviews_passed",
        "unexplained_required_gaps_zero",
        "flaky_passes_zero",
    )
    if not all(getattr(verification, field_name) for field_name in verification_fields):
        failures.append(
            "Gate 1 verification/build/review/gap/flaky truth is incomplete"
        )
    verification_subjects = _subjects_for(verification.evidence_ids, artifact_by_id)
    if any(
        f"verification:{field_name}" not in verification_subjects
        for field_name in verification_fields
    ):
        failures.append("Gate 1 verification booleans lack signed check subjects")

    for section in W2Section:
        minimum = _SECTION_MIN[section]
        if section_scores[section] < minimum:
            failures.append(
                f"{section.value} score {section_scores[section]} is below {minimum}"
            )
    total_score = sum(section_scores.values())
    if total_score < 90:
        failures.append(f"total score {total_score} is below 90")

    scored_planes = {
        plane
        for section, plane in (
            (W2Section.P1, W2CapabilityPlane.P1_SPEECH_MEDIA),
            (W2Section.P2, W2CapabilityPlane.P2_CONVERSATION),
            (W2Section.P3, W2CapabilityPlane.P3_TASK),
        )
        if section_scores[section] > 0
    }
    scored_planes.add(W2CapabilityPlane.OBSERVABILITY)
    if not scored_planes.issubset(candidate.active_planes):
        failures.append("a scored capability plane was not declared active")

    if set(journey_by_step) != set(W2JourneyStep):
        failures.append("Gate 2 cumulative journey evidence is incomplete")
    journey_receipt_id_sets: list[set[str]] = []
    journey_chain_sets: list[set[str]] = []
    journey_order_values: list[int] = []
    task_chain_sets: list[set[str]] = []
    v2_journey_used = False
    v2_journey_runtime_id_sets: list[set[str]] = []
    for step in W2JourneyStep:
        evidence = journey_by_step.get(step)
        if evidence is None:
            continue
        if not evidence.passed:
            failures.append(f"Gate 2 journey step {step.value} failed")
        kinds = _artifact_kinds(evidence.evidence_ids, artifact_by_id)
        journey_artifacts = [
            artifact_by_id[evidence_id] for evidence_id in evidence.evidence_ids
        ]
        is_v2 = any(
            artifact.runtime_format_version == 2 for artifact in journey_artifacts
        )
        if is_v2:
            v2_journey_used = True
            derivation = _derive_v2_journey_steps(journey_artifacts)
            if step not in derivation.steps:
                failures.append(
                    f"Gate 2 journey step {step.value} is not runtime-derived"
                )
            v2_journey_runtime_id_sets.append(
                {
                    artifact.artifact_id
                    for artifact in journey_artifacts
                    if artifact.runtime_format_version == 2
                }
            )
        required_kinds = {
            W2EvidenceKind.REAL_RUNTIME,
            W2EvidenceKind.HUMAN_OBSERVATION,
        }
        if step is W2JourneyStep.TEXT_DEGRADATION:
            required_kinds.add(W2EvidenceKind.FAULT_INJECTION)
        if not required_kinds.issubset(kinds):
            failures.append(
                f"Gate 2 journey step {step.value} lacks required real evidence"
            )
        human_attested = (
            _has_v2_claim_attestation(
                evidence.evidence_ids,
                artifact_by_id,
                subject=f"journey:{step.value}",
                required_kind=W2EvidenceKind.HUMAN_OBSERVATION,
            )
            if is_v2
            else _has_subject_attestation(
                evidence.evidence_ids,
                artifact_by_id,
                subject=f"journey:{step.value}",
                required_kind=W2EvidenceKind.HUMAN_OBSERVATION,
            )
        )
        if not human_attested:
            failures.append(
                f"Gate 2 journey step {step.value} human receipt is unbound"
            )
        if step is W2JourneyStep.TEXT_DEGRADATION and not (
            _has_v2_claim_attestation(
                evidence.evidence_ids,
                artifact_by_id,
                subject=f"journey:{step.value}",
                required_kind=W2EvidenceKind.FAULT_INJECTION,
            )
            if is_v2
            else _has_subject_attestation(
                evidence.evidence_ids,
                artifact_by_id,
                subject=f"journey:{step.value}",
                required_kind=W2EvidenceKind.FAULT_INJECTION,
            )
        ):
            failures.append("Gate 2 text degradation fault receipt is unbound")
        journey_receipt_id_sets.append(
            {
                evidence_id
                for evidence_id in evidence.evidence_ids
                if artifact_by_id[evidence_id].attested_content_sha256
                and artifact_by_id[evidence_id].evidence_kinds
                & {
                    W2EvidenceKind.HUMAN_OBSERVATION,
                    W2EvidenceKind.FAULT_INJECTION,
                }
            }
        )
        if is_v2:
            continue
        subjects = _subjects_for(evidence.evidence_ids, artifact_by_id)
        journey_chain_sets.append(
            {subject for subject in subjects if subject.startswith("journey-chain:")}
        )
        order_prefix = f"journey-order:{step.value}:"
        order_values = {
            int(subject[len(order_prefix) :])
            for subject in subjects
            if subject.startswith(order_prefix)
            and subject[len(order_prefix) :].isdigit()
        }
        if len(order_values) != 1:
            failures.append(
                f"Gate 2 journey step {step.value} lacks one exact runtime order"
            )
        else:
            journey_order_values.append(next(iter(order_values)))
        if step in {
            W2JourneyStep.CONFIRMED_TASK_CREATE,
            W2JourneyStep.CONVERSATION_DURING_TASK,
            W2JourneyStep.EXACT_TASK_RESULT,
        }:
            task_chain_sets.append(
                {
                    subject
                    for subject in subjects
                    if subject.startswith("journey-task-chain:")
                }
            )
    if any(
        left & right
        for index, left in enumerate(journey_receipt_id_sets)
        for right in journey_receipt_id_sets[index + 1 :]
    ):
        failures.append("Gate 2 journey steps reused an assisted receipt")
    if v2_journey_used:
        common_runtime_ids = _common_v2_journey_runtime_ids(v2_journey_runtime_id_sets)
        if not common_runtime_ids:
            failures.append(
                "Gate 2 v2 steps do not share one exact runtime artifact set"
            )
        else:
            common_derivation = _derive_v2_journey_steps(
                [artifact_by_id[artifact_id] for artifact_id in common_runtime_ids]
            )
            if not common_derivation.full_chain_correlations:
                failures.append(
                    "Gate 2 v2 steps do not form one ordered runtime causal chain"
                )
            if not common_derivation.full_chain_task_ids:
                failures.append(
                    "Gate 2 v2 task steps do not share one exact task chain"
                )
    else:
        if len(journey_chain_sets) != len(W2JourneyStep) or not set.intersection(
            *journey_chain_sets
        ):
            failures.append(
                "Gate 2 journey steps do not share one runtime causal chain"
            )
        if len(journey_order_values) != len(W2JourneyStep) or any(
            left >= right
            for left, right in zip(
                journey_order_values, journey_order_values[1:], strict=False
            )
        ):
            failures.append("Gate 2 journey runtime facts are not cumulatively ordered")
        if len(task_chain_sets) != 3 or not set.intersection(*task_chain_sets):
            failures.append("Gate 2 task steps do not share one exact task chain")

    missing_invariants = set(W2Invariant) - set(invariant_by_id)
    if missing_invariants:
        failures.append("mandatory invariant evidence is incomplete")
    for invariant_evidence in invariant_by_id.values():
        kinds = _artifact_kinds(invariant_evidence.evidence_ids, artifact_by_id)
        if not kinds & {
            W2EvidenceKind.REAL_RUNTIME,
            W2EvidenceKind.AUTOMATED_CONFORMANCE,
            W2EvidenceKind.FAULT_INJECTION,
        }:
            failures.append("an invariant lacks executable or runtime proof")
        if f"invariant:{invariant_evidence.invariant.value}" not in _subjects_for(
            invariant_evidence.evidence_ids, artifact_by_id
        ):
            failures.append("an invariant lacks its exact signed proof subject")
    if any(not evidence.passed for evidence in invariant_by_id.values()):
        failures.append("one or more mandatory invariants failed")

    if set(run_by_number) != {1, 2, 3}:
        failures.append("three consecutive showcase runs were not recorded")
    else:
        ordered_runs = [run_by_number[number] for number in (1, 2, 3)]
        if any(
            (run.candidate_sha, run.environment_id, run.session_id, run.mode_id)
            != candidate_binding
            for run in ordered_runs
        ):
            failures.append(
                "showcase runs do not share the candidate/environment/session/mode"
            )
        if any(not run.passed for run in ordered_runs):
            failures.append("one or more showcase runs failed")
        run_id_sets = [set(run.evidence_ids) for run in ordered_runs]
        if any(
            left & right
            for index, left in enumerate(run_id_sets)
            for right in run_id_sets[index + 1 :]
        ):
            failures.append("showcase runs reused an evidence artifact")
        run_sequences: list[list[int]] = []
        v2_showcase_used = False
        v2_showcase_receipts: list[W2EvidenceArtifact] = []
        v2_showcase_task_sets: list[set[str]] = []
        for run in ordered_runs:
            kinds = _artifact_kinds(run.evidence_ids, artifact_by_id)
            if not {
                W2EvidenceKind.REAL_RUNTIME,
                W2EvidenceKind.HUMAN_OBSERVATION,
            }.issubset(kinds):
                failures.append("a showcase run lacks real-runtime human observation")
            run_artifacts = [
                artifact_by_id[evidence_id] for evidence_id in run.evidence_ids
            ]
            is_v2 = any(
                artifact.runtime_format_version == 2 for artifact in run_artifacts
            )
            if is_v2:
                v2_showcase_used = True
                derivation = _derive_v2_journey_steps(run_artifacts)
                if (
                    derivation.steps != frozenset(W2JourneyStep)
                    or not derivation.full_chain_correlations
                ):
                    failures.append(
                        f"showcase run {run.run_number} lacks a full derived journey"
                    )
                v2_showcase_task_sets.append(set(derivation.full_chain_task_ids))
            showcase_attested = (
                _has_v2_claim_attestation(
                    run.evidence_ids,
                    artifact_by_id,
                    subject=f"showcase:{run.run_number}",
                    required_kind=W2EvidenceKind.HUMAN_OBSERVATION,
                )
                if is_v2
                else _has_subject_attestation(
                    run.evidence_ids,
                    artifact_by_id,
                    subject=f"showcase:{run.run_number}",
                    required_kind=W2EvidenceKind.HUMAN_OBSERVATION,
                )
            )
            if not showcase_attested:
                failures.append("a showcase human receipt is not bound to runtime")
            if is_v2:
                receipts = [
                    artifact
                    for artifact in run_artifacts
                    if W2EvidenceKind.HUMAN_OBSERVATION in artifact.evidence_kinds
                    and f"showcase:{run.run_number}" in artifact.proven_subjects
                ]
                if len(receipts) != 1:
                    failures.append("a v2 showcase lacks one exact human receipt")
                else:
                    v2_showcase_receipts.append(receipts[0])
            run_sequences.append(
                [artifact_by_id[item].sequence for item in run.evidence_ids]
            )
        if v2_showcase_used:
            if len(v2_showcase_receipts) == 3 and not (
                v2_showcase_receipts[0].receipt_predecessor_sha256 is None
                and v2_showcase_receipts[1].receipt_predecessor_sha256
                == v2_showcase_receipts[0].content_sha256
                and v2_showcase_receipts[2].receipt_predecessor_sha256
                == v2_showcase_receipts[1].content_sha256
            ):
                failures.append("v2 showcase receipts do not form one ordered chain")
            if len(v2_showcase_task_sets) != 3 or any(
                not task_ids for task_ids in v2_showcase_task_sets
            ):
                failures.append("v2 showcases lack exact task identity")
            elif any(
                left & right
                for index, left in enumerate(v2_showcase_task_sets)
                for right in v2_showcase_task_sets[index + 1 :]
            ):
                failures.append("v2 showcase runs reused task identity")
        elif not (
            max(run_sequences[0]) < min(run_sequences[1])
            and max(run_sequences[1]) < min(run_sequences[2])
        ):
            failures.append("showcase artifacts are not three ordered consecutive runs")

    if set(fault_by_plane) != set(candidate.active_planes):
        failures.append(
            "fault records do not cover exactly the active capability planes"
        )
    v2_evidence_set = any(
        artifact.runtime_format_version == 2
        for artifact in artifacts
        if W2EvidenceKind.REAL_RUNTIME in artifact.evidence_kinds
    )
    for plane, fault_evidence in fault_by_plane.items():
        fault_groups = (
            fault_evidence.retriable_evidence_ids,
            fault_evidence.non_retriable_evidence_ids,
            fault_evidence.zero_effect_evidence_ids,
        )
        fault_subjects = (
            f"fault:{plane.value}:retriable",
            f"fault:{plane.value}:non_retriable",
            f"fault:{plane.value}:zero_effect",
        )
        fault_classes = ("retriable", "non_retriable", "zero_effect")
        v2_groups = tuple(
            any(
                artifact_by_id[evidence_id].runtime_format_version == 2
                for evidence_id in group
            )
            for group in fault_groups
        )
        if v2_evidence_set and not all(v2_groups):
            failures.append(
                f"active plane {plane.value} lacks v2 runtime-bound fault proof"
            )
        elif any(v2_groups) and not all(v2_groups):
            failures.append(f"active plane {plane.value} mixes v1 and v2 fault proof")
        injected_faults_valid = all(
            W2EvidenceKind.FAULT_INJECTION in _artifact_kinds(group, artifact_by_id)
            and (
                _has_v2_claim_attestation(
                    group,
                    artifact_by_id,
                    subject=subject,
                    required_kind=W2EvidenceKind.FAULT_INJECTION,
                )
                if is_v2
                else _has_subject_attestation(
                    group,
                    artifact_by_id,
                    subject=subject,
                    required_kind=W2EvidenceKind.FAULT_INJECTION,
                )
            )
            for group, subject, is_v2 in zip(
                fault_groups, fault_subjects, v2_groups, strict=True
            )
        )
        if not injected_faults_valid:
            failures.append(
                f"active plane {plane.value} lacks injected-fault artifacts"
            )
        if (
            all(v2_groups)
            and plane is not W2CapabilityPlane.OBSERVABILITY
            and not all(
                _derive_v2_fault_class(
                    [artifact_by_id[evidence_id] for evidence_id in group],
                    plane=plane,
                    fault_class=fault_class,
                )
                for group, fault_class in zip(fault_groups, fault_classes, strict=True)
            )
        ):
            failures.append(
                f"active plane {plane.value} fault classes are not runtime-derived"
            )
        if (
            v2_evidence_set
            and plane is W2CapabilityPlane.OBSERVABILITY
            and any(
                W2EvidenceKind.AUTOMATED_CONFORMANCE
                not in _artifact_kinds(group, artifact_by_id)
                for group in fault_groups
            )
        ):
            failures.append(
                "observability faults lack independent automated operation proof"
            )
        if not fault_evidence.active or not (
            fault_evidence.retriable_observed
            and fault_evidence.non_retriable_observed
            and fault_evidence.stale_effects_zero
            and fault_evidence.false_success_zero
        ):
            failures.append(f"active plane {plane.value} lacks complete fault evidence")

    restart_kinds = _artifact_kinds(restart.evidence_ids, artifact_by_id)
    if W2EvidenceKind.REAL_RUNTIME not in restart_kinds:
        failures.append("restart evidence lacks real-runtime proof")
    if not restart.performed:
        failures.append("restart/recovery evidence was not recorded")
    restart_artifacts = [
        artifact_by_id[evidence_id] for evidence_id in restart.evidence_ids
    ]
    v2_restart = any(
        artifact.runtime_format_version == 2 for artifact in restart_artifacts
    )
    restart_subjects = _subjects_for(restart.evidence_ids, artifact_by_id)
    restart_details = (
        _derive_v2_restart_details(restart_artifacts) if v2_restart else None
    )
    derived_restart = (
        restart_details.tasks if restart_details is not None else MappingProxyType({})
    )
    if v2_restart:
        if any(
            artifact.runtime_format_version not in {0, 2}
            for artifact in restart_artifacts
        ):
            failures.append("restart evidence mixes legacy and v2 runtime proof")
        if set(derived_restart) != set(restart.inflight_task_ids):
            failures.append(
                "restart boundary is not derived from linked AgentServer epochs"
            )
        assert restart_details is not None
        failures.extend(
            f"restart evidence diagnostic: {diagnostic}"
            for diagnostic in restart_details.diagnostics
        )
    elif "restart:boundary" not in restart_subjects:
        failures.append("restart boundary lacks signed durable-store proof")
    expected_inflight = set(restart.inflight_task_ids)
    reconciled = {item.task_id for item in restart.reconciliations}
    if reconciled != expected_inflight:
        failures.append("restart reconciliation does not exactly cover in-flight tasks")
    for reconciliation in restart.reconciliations:
        kinds = _artifact_kinds(reconciliation.evidence_ids, artifact_by_id)
        task_ids = {
            task_id
            for evidence_id in reconciliation.evidence_ids
            for task_id in artifact_by_id[evidence_id].proven_task_ids
        }
        exact_v2_details = _derive_v2_restart_details(
            [artifact_by_id[evidence_id] for evidence_id in reconciliation.evidence_ids]
        )
        exact_v2 = exact_v2_details.tasks
        runtime_proof_valid = (
            not exact_v2_details.diagnostics
            and exact_v2.get(reconciliation.task_id) is reconciliation.outcome
            if v2_restart
            else (
                reconciliation.task_id in task_ids
                and f"restart:inflight:{reconciliation.task_id}" in restart_subjects
                and (
                    f"restart:reconciled:{reconciliation.task_id}:"
                    f"{reconciliation.outcome.value}"
                    in _subjects_for(reconciliation.evidence_ids, artifact_by_id)
                )
            )
        )
        if W2EvidenceKind.REAL_RUNTIME not in kinds or not runtime_proof_valid:
            failures.append(
                f"restart task {reconciliation.task_id} lacks exact runtime proof"
            )

    unique_failures = tuple(dict.fromkeys(failures))
    return W2GateResult(
        status=W2GateStatus.FAIL if unique_failures else W2GateStatus.PASS,
        section_scores=section_scores,
        total_score=total_score,
        failures=unique_failures,
        _construction_token=_RESULT_CONSTRUCTION_TOKEN,
    )


__all__ = [
    "MAX_W2_EVIDENCE_IDS",
    "MAX_W2_ARTIFACT_BYTES",
    "MAX_W2_GATE_RECORDS",
    "MAX_W2_PROVIDER_LABELS",
    "W2AutomatedVerificationEvidence",
    "W2CandidateEvidence",
    "W2CapabilityPlane",
    "W2EvidenceArtifact",
    "W2EvidenceArtifactSlot",
    "W2EvidenceKind",
    "W2EvidenceTrustPolicy",
    "W2FaultEvidence",
    "W2GateContractViolation",
    "W2GateResult",
    "W2GateStatus",
    "W2Invariant",
    "W2InvariantEvidence",
    "W2JourneyStep",
    "W2JourneyStepEvidence",
    "W2LedgerAward",
    "W2LedgerItem",
    "W2RestartEvidence",
    "W2ReconciliationOutcome",
    "W2RouteClass",
    "W2RuntimeArtifactSlot",
    "W2Section",
    "W2ShowcaseRun",
    "W2TaskReconciliationEvidence",
    "evaluate_w2_demo_gate",
    "verify_w2_planned_product_faults",
    "verify_w2_assisted_receipt_content",
    "verify_w2_evidence_content",
    "verify_w2_runtime_jsonl_content",
    "w2_artifact_signature_payload",
]
