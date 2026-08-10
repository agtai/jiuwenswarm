# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Closed, public-authority-derived W2 product fault identities.

This module is deliberately pure.  A caller must first validate the signed
public W2 policy, then pass only its public policy/candidate/evidence binding.
Private signing keys, credentials and runtime claims are not inputs.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from enum import Enum
from typing import Final

from jiuwenswarm.common.schema.live_voice_contract_v2 import canonical_json_bytes


W2_FAULT_DERIVATION_VERSION: Final = "w2.product-fault-plan.v1"

P1_RECOGNIZE_OPERATION: Final = "speech.recognize.batch"
P2_PRESENTATION_ACK_OPERATION: Final = (
    "live_voice.composition.p2.presentation.ack"
)
P3_PROGRESS_ACK_OPERATION: Final = "live_voice.composition.p3.progress.ack"
P3_MUTATION_OPERATION: Final = "live_voice.composition.p3.mutate"
P3_RETRY_OPERATION: Final = "task.retry"

P1_RETRIABLE_FAULT_REQUEST_ID_ENV: Final = (
    "JIUWENSWARM_LIVE_VOICE_SPEECH_RETRIABLE_FAULT_REQUEST_ID"
)
P1_RETRIABLE_FAULT_OPERATION_ENV: Final = (
    "JIUWENSWARM_LIVE_VOICE_SPEECH_RETRIABLE_FAULT_OPERATION"
)
P2_RETRIABLE_FAULT_REQUEST_ID_ENV: Final = (
    "JIUWENSWARM_LIVE_VOICE_PRODUCT_P2_RETRIABLE_FAULT_REQUEST_ID"
)
P2_RETRIABLE_FAULT_OPERATION_ENV: Final = (
    "JIUWENSWARM_LIVE_VOICE_PRODUCT_P2_RETRIABLE_FAULT_OPERATION"
)
P2_STALE_FAULT_REQUEST_ID_ENV: Final = (
    "JIUWENSWARM_LIVE_VOICE_PRODUCT_P2_STALE_FAULT_REQUEST_ID"
)
P2_STALE_FAULT_OPERATION_ENV: Final = (
    "JIUWENSWARM_LIVE_VOICE_PRODUCT_P2_STALE_FAULT_OPERATION"
)
P3_STALE_FAULT_REQUEST_ID_ENV: Final = (
    "JIUWENSWARM_LIVE_VOICE_PRODUCT_P3_STALE_FAULT_REQUEST_ID"
)
P3_STALE_FAULT_OPERATION_ENV: Final = (
    "JIUWENSWARM_LIVE_VOICE_PRODUCT_P3_STALE_FAULT_OPERATION"
)

_MAX_PUBLIC_LABEL_CHARACTERS: Final = 256
_MAX_PUBLIC_LABEL_UTF8_BYTES: Final = 1_024
_CANDIDATE_PATTERN: Final = re.compile(r"[0-9a-f]{40}")


class W2FaultPlanError(ValueError):
    """The public W2 fault authority is incomplete, open or contradictory."""


class W2FaultPlane(str, Enum):
    P1_SPEECH_MEDIA = "p1.speech_media"
    P2_CONVERSATION = "p2.conversation"
    P3_TASK = "p3.task"


class W2FaultClass(str, Enum):
    RETRIABLE = "retriable"
    NON_RETRIABLE = "non_retriable"
    ZERO_EFFECT = "zero_effect"


_PAIR_BY_CLASS: Final = {
    W2FaultClass.RETRIABLE: 1,
    W2FaultClass.NON_RETRIABLE: 2,
    W2FaultClass.ZERO_EFFECT: 3,
}

_OPERATION_BY_IDENTITY: Final = {
    (W2FaultPlane.P1_SPEECH_MEDIA, W2FaultClass.RETRIABLE): P1_RECOGNIZE_OPERATION,
    (
        W2FaultPlane.P1_SPEECH_MEDIA,
        W2FaultClass.NON_RETRIABLE,
    ): P1_RECOGNIZE_OPERATION,
    (W2FaultPlane.P1_SPEECH_MEDIA, W2FaultClass.ZERO_EFFECT): P1_RECOGNIZE_OPERATION,
    (
        W2FaultPlane.P2_CONVERSATION,
        W2FaultClass.RETRIABLE,
    ): P2_PRESENTATION_ACK_OPERATION,
    (
        W2FaultPlane.P2_CONVERSATION,
        W2FaultClass.NON_RETRIABLE,
    ): P2_PRESENTATION_ACK_OPERATION,
    (
        W2FaultPlane.P2_CONVERSATION,
        W2FaultClass.ZERO_EFFECT,
    ): P2_PRESENTATION_ACK_OPERATION,
    (W2FaultPlane.P3_TASK, W2FaultClass.RETRIABLE): P3_PROGRESS_ACK_OPERATION,
    (W2FaultPlane.P3_TASK, W2FaultClass.NON_RETRIABLE): P3_MUTATION_OPERATION,
    (W2FaultPlane.P3_TASK, W2FaultClass.ZERO_EFFECT): P3_MUTATION_OPERATION,
}


def _public_label(value: object, field: str) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > _MAX_PUBLIC_LABEL_CHARACTERS
        or any(character.isspace() for character in value)
    ):
        raise W2FaultPlanError(f"{field} must be a non-empty bounded opaque label")
    try:
        encoded = value.encode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise W2FaultPlanError(f"{field} must contain Unicode scalar values") from exc
    if len(encoded) > _MAX_PUBLIC_LABEL_UTF8_BYTES:
        raise W2FaultPlanError(f"{field} exceeds the UTF-8 byte limit")
    return value


def _plane(value: object) -> W2FaultPlane:
    try:
        return W2FaultPlane(value)
    except (TypeError, ValueError) as exc:
        raise W2FaultPlanError("fault plane is not one closed product plane") from exc


def _fault_class(value: object) -> W2FaultClass:
    try:
        return W2FaultClass(value)
    except (TypeError, ValueError) as exc:
        raise W2FaultPlanError("fault class is not closed") from exc


def _request_id(
    *,
    policy_id: str,
    candidate_sha: str,
    evidence_set_id: str,
    pair: int,
    plane: W2FaultPlane,
    fault_class: W2FaultClass,
    operation: str,
    derivation_version: str,
) -> str:
    digest = hashlib.sha256(
        canonical_json_bytes(
            {
                "candidate_sha": candidate_sha,
                "derivation_version": derivation_version,
                "evidence_set_id": evidence_set_id,
                "fault_class": fault_class.value,
                "operation": operation,
                "pair": pair,
                "plane": plane.value,
                "policy_id": policy_id,
            }
        )
    ).hexdigest()
    return f"w2-fault-{digest}"


def w2_fault_source_record_id(request_id: object) -> str:
    """Mirror the production observer's exact public request fingerprint."""

    exact_request_id = _public_label(request_id, "request_id")
    return (
        "w2-request-"
        + hashlib.sha256(exact_request_id.encode("utf-8")).hexdigest()[:32]
    )


@dataclass(frozen=True, slots=True)
class W2FaultIdentity:
    policy_id: str
    candidate_sha: str
    evidence_set_id: str
    pair: int
    plane: W2FaultPlane
    fault_class: W2FaultClass
    operation: str
    derivation_version: str
    request_id: str
    source_record_id: str

    def __post_init__(self) -> None:
        policy_id = _public_label(self.policy_id, "policy_id")
        evidence_set_id = _public_label(self.evidence_set_id, "evidence_set_id")
        if (
            type(self.candidate_sha) is not str
            or _CANDIDATE_PATTERN.fullmatch(self.candidate_sha) is None
        ):
            raise W2FaultPlanError("candidate_sha must be a full lowercase Git SHA")
        plane = _plane(self.plane)
        fault_class = _fault_class(self.fault_class)
        if type(self.pair) is not int or self.pair != _PAIR_BY_CLASS[fault_class]:
            raise W2FaultPlanError("fault pair does not match its closed fault class")
        if self.derivation_version != W2_FAULT_DERIVATION_VERSION:
            raise W2FaultPlanError("fault derivation version is unsupported")
        expected_operation = _OPERATION_BY_IDENTITY[(plane, fault_class)]
        if self.operation != expected_operation:
            raise W2FaultPlanError("fault operation does not match the closed plan")
        expected_request_id = _request_id(
            policy_id=policy_id,
            candidate_sha=self.candidate_sha,
            evidence_set_id=evidence_set_id,
            pair=self.pair,
            plane=plane,
            fault_class=fault_class,
            operation=expected_operation,
            derivation_version=self.derivation_version,
        )
        if self.request_id != expected_request_id:
            raise W2FaultPlanError("fault request_id is not authority-derived")
        if self.source_record_id != w2_fault_source_record_id(expected_request_id):
            raise W2FaultPlanError("fault source_record_id does not match the observer")


@dataclass(frozen=True, slots=True)
class W2ProductFaultPlan:
    policy_id: str
    candidate_sha: str
    evidence_set_id: str
    derivation_version: str
    items: tuple[W2FaultIdentity, ...]

    def __post_init__(self) -> None:
        _public_label(self.policy_id, "policy_id")
        _public_label(self.evidence_set_id, "evidence_set_id")
        if (
            type(self.candidate_sha) is not str
            or _CANDIDATE_PATTERN.fullmatch(self.candidate_sha) is None
        ):
            raise W2FaultPlanError("candidate_sha must be a full lowercase Git SHA")
        if self.derivation_version != W2_FAULT_DERIVATION_VERSION:
            raise W2FaultPlanError("fault derivation version is unsupported")
        expected_keys = frozenset(_OPERATION_BY_IDENTITY)
        actual_keys = frozenset((item.plane, item.fault_class) for item in self.items)
        if len(self.items) != 9 or actual_keys != expected_keys:
            raise W2FaultPlanError("product fault plan must contain exactly nine items")
        if any(
            item.policy_id != self.policy_id
            or item.candidate_sha != self.candidate_sha
            or item.evidence_set_id != self.evidence_set_id
            or item.derivation_version != self.derivation_version
            for item in self.items
        ):
            raise W2FaultPlanError("product fault plan mixes public authority")

    def require(
        self, plane: W2FaultPlane | str, fault_class: W2FaultClass | str
    ) -> W2FaultIdentity:
        exact_plane = _plane(plane)
        exact_class = _fault_class(fault_class)
        for item in self.items:
            if item.plane is exact_plane and item.fault_class is exact_class:
                return item
        raise W2FaultPlanError("product fault identity is missing")


def derive_w2_fault_identity(
    *,
    policy_id: str,
    candidate_sha: str,
    evidence_set_id: str,
    pair: int,
    plane: W2FaultPlane | str,
    fault_class: W2FaultClass | str,
    operation: str,
    derivation_version: str = W2_FAULT_DERIVATION_VERSION,
) -> W2FaultIdentity:
    """Derive one exact identity from an already-verified public policy."""

    exact_policy_id = _public_label(policy_id, "policy_id")
    exact_evidence_set_id = _public_label(evidence_set_id, "evidence_set_id")
    exact_plane = _plane(plane)
    exact_class = _fault_class(fault_class)
    if type(candidate_sha) is not str or _CANDIDATE_PATTERN.fullmatch(candidate_sha) is None:
        raise W2FaultPlanError("candidate_sha must be a full lowercase Git SHA")
    if type(pair) is not int or pair != _PAIR_BY_CLASS[exact_class]:
        raise W2FaultPlanError("fault pair does not match its closed fault class")
    if derivation_version != W2_FAULT_DERIVATION_VERSION:
        raise W2FaultPlanError("fault derivation version is unsupported")
    expected_operation = _OPERATION_BY_IDENTITY[(exact_plane, exact_class)]
    if operation != expected_operation:
        raise W2FaultPlanError("fault operation does not match the closed plan")
    request_id = _request_id(
        policy_id=exact_policy_id,
        candidate_sha=candidate_sha,
        evidence_set_id=exact_evidence_set_id,
        pair=pair,
        plane=exact_plane,
        fault_class=exact_class,
        operation=operation,
        derivation_version=derivation_version,
    )
    return W2FaultIdentity(
        policy_id=exact_policy_id,
        candidate_sha=candidate_sha,
        evidence_set_id=exact_evidence_set_id,
        pair=pair,
        plane=exact_plane,
        fault_class=exact_class,
        operation=operation,
        derivation_version=derivation_version,
        request_id=request_id,
        source_record_id=w2_fault_source_record_id(request_id),
    )


def derive_w2_product_fault_plan(
    *,
    policy_id: str,
    candidate_sha: str,
    evidence_set_id: str,
    derivation_version: str = W2_FAULT_DERIVATION_VERSION,
) -> W2ProductFaultPlan:
    """Derive the complete closed P1/P2/P3 by three-class product plan."""

    items = tuple(
        derive_w2_fault_identity(
            policy_id=policy_id,
            candidate_sha=candidate_sha,
            evidence_set_id=evidence_set_id,
            pair=_PAIR_BY_CLASS[fault_class],
            plane=plane,
            fault_class=fault_class,
            operation=_OPERATION_BY_IDENTITY[(plane, fault_class)],
            derivation_version=derivation_version,
        )
        for plane in W2FaultPlane
        for fault_class in W2FaultClass
    )
    return W2ProductFaultPlan(
        policy_id=policy_id,
        candidate_sha=candidate_sha,
        evidence_set_id=evidence_set_id,
        derivation_version=derivation_version,
        items=items,
    )


__all__ = [
    "P1_RECOGNIZE_OPERATION",
    "P1_RETRIABLE_FAULT_OPERATION_ENV",
    "P1_RETRIABLE_FAULT_REQUEST_ID_ENV",
    "P2_PRESENTATION_ACK_OPERATION",
    "P2_RETRIABLE_FAULT_OPERATION_ENV",
    "P2_RETRIABLE_FAULT_REQUEST_ID_ENV",
    "P2_STALE_FAULT_OPERATION_ENV",
    "P2_STALE_FAULT_REQUEST_ID_ENV",
    "P3_MUTATION_OPERATION",
    "P3_PROGRESS_ACK_OPERATION",
    "P3_RETRY_OPERATION",
    "P3_STALE_FAULT_OPERATION_ENV",
    "P3_STALE_FAULT_REQUEST_ID_ENV",
    "W2_FAULT_DERIVATION_VERSION",
    "W2FaultClass",
    "W2FaultIdentity",
    "W2FaultPlanError",
    "W2FaultPlane",
    "W2ProductFaultPlan",
    "derive_w2_fault_identity",
    "derive_w2_product_fault_plan",
    "w2_fault_source_record_id",
]
