# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Declaration-only privacy vocabulary for P3 telemetry composition.

This module performs no capture, scan, redaction, export, persistence, lifecycle
mutation, or compliance decision. It remains uncomposed until the P3-8 owner
binds the declaration to existing runtime privacy enforcement.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Final, Mapping


TELEMETRY_PRIVACY_CONTRACT_VERSION: Final = "live-voice.telemetry-privacy.v1"

_SAFE_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$")
_SENSITIVE_ID = re.compile(
    r"(?:api[_-]?key|authorization|bearer|credential|password|passwd|secret|token|transcript)",
    re.IGNORECASE,
)


class TelemetryDataClass(StrEnum):
    PUBLIC_IDENTITY = "public_identity"
    LIFECYCLE_STATE = "lifecycle_state"
    DIAGNOSTIC_CODE = "diagnostic_code"
    METRIC_VALUE = "metric_value"
    TASK_CONTENT = "task_content"
    RESULT_CONTENT = "result_content"
    BLOCKING_INPUT = "blocking_input"
    ARTIFACT_DETAIL = "artifact_detail"
    CREDENTIAL = "credential"
    RAW_AUDIO = "raw_audio"
    DEVICE_IDENTITY = "device_identity"


class TelemetryDisposition(StrEnum):
    ALLOW_CLOSED_FIELD = "allow_closed_field"
    PROHIBIT = "prohibit"


class TelemetryPrivacyReason(StrEnum):
    FEATURE_DISABLED = "feature_disabled"
    INVALID_PROFILE = "invalid_profile"
    UNSAFE_DISPOSITION = "unsafe_disposition"
    DECLARATION_READY = "declaration_ready"


REQUIRED_TELEMETRY_DISPOSITIONS: Final[
    Mapping[TelemetryDataClass, TelemetryDisposition]
] = MappingProxyType(
    {
        TelemetryDataClass.PUBLIC_IDENTITY: TelemetryDisposition.ALLOW_CLOSED_FIELD,
        TelemetryDataClass.LIFECYCLE_STATE: TelemetryDisposition.ALLOW_CLOSED_FIELD,
        TelemetryDataClass.DIAGNOSTIC_CODE: TelemetryDisposition.ALLOW_CLOSED_FIELD,
        TelemetryDataClass.METRIC_VALUE: TelemetryDisposition.ALLOW_CLOSED_FIELD,
        TelemetryDataClass.TASK_CONTENT: TelemetryDisposition.PROHIBIT,
        TelemetryDataClass.RESULT_CONTENT: TelemetryDisposition.PROHIBIT,
        TelemetryDataClass.BLOCKING_INPUT: TelemetryDisposition.PROHIBIT,
        TelemetryDataClass.ARTIFACT_DETAIL: TelemetryDisposition.PROHIBIT,
        TelemetryDataClass.CREDENTIAL: TelemetryDisposition.PROHIBIT,
        TelemetryDataClass.RAW_AUDIO: TelemetryDisposition.PROHIBIT,
        TelemetryDataClass.DEVICE_IDENTITY: TelemetryDisposition.PROHIBIT,
    }
)


def _safe_id(value: object, field_name: str) -> str:
    if type(value) is not str or _SAFE_ID.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a bounded identifier")
    if _SENSITIVE_ID.search(value) is not None:
        raise ValueError(f"{field_name} must not carry sensitive identity")
    return value


@dataclass(frozen=True, slots=True)
class TelemetryPrivacyRule:
    data_class: TelemetryDataClass
    disposition: TelemetryDisposition

    def __post_init__(self) -> None:
        if type(self.data_class) is not TelemetryDataClass:
            raise ValueError("data_class must use the closed vocabulary")
        if type(self.disposition) is not TelemetryDisposition:
            raise ValueError("disposition must use the closed vocabulary")


@dataclass(frozen=True, slots=True)
class TelemetryPrivacyProfile:
    contract_version: str
    profile_id: str
    rules: tuple[TelemetryPrivacyRule, ...]

    def __post_init__(self) -> None:
        if self.contract_version != TELEMETRY_PRIVACY_CONTRACT_VERSION:
            raise ValueError("unsupported telemetry privacy contract")
        _safe_id(self.profile_id, "profile_id")
        if type(self.rules) is not tuple or any(
            type(rule) is not TelemetryPrivacyRule for rule in self.rules
        ):
            raise ValueError("rules must be exact immutable privacy rules")
        classes = tuple(rule.data_class for rule in self.rules)
        if len(classes) != len(set(classes)):
            raise ValueError("privacy data classes must be unique")
        if set(classes) != set(TelemetryDataClass):
            raise ValueError("every telemetry data class must be explicit")


@dataclass(frozen=True, slots=True)
class TelemetryPrivacyReadiness:
    declaration_ready: bool
    reason: TelemetryPrivacyReason
    declaration_only: bool = True
    runtime_scanned: bool = False
    exporter_called: bool = False
    persistence_changed: bool = False
    business_result_changed: bool = False

    def __post_init__(self) -> None:
        if type(self.declaration_ready) is not bool:
            raise ValueError("declaration_ready must be exact bool")
        if type(self.reason) is not TelemetryPrivacyReason:
            raise ValueError("reason must use the closed vocabulary")
        if self.declaration_ready != (
            self.reason is TelemetryPrivacyReason.DECLARATION_READY
        ):
            raise ValueError("only a ready declaration may report declaration_ready")
        if any(
            value is not expected
            for value, expected in (
                (self.declaration_only, True),
                (self.runtime_scanned, False),
                (self.exporter_called, False),
                (self.persistence_changed, False),
                (self.business_result_changed, False),
            )
        ):
            raise ValueError("privacy readiness cannot claim runtime authority")


def default_telemetry_privacy_profile() -> TelemetryPrivacyProfile:
    """Return the closed declaration; this does not activate enforcement."""

    return TelemetryPrivacyProfile(
        contract_version=TELEMETRY_PRIVACY_CONTRACT_VERSION,
        profile_id="p3.telemetry.default",
        rules=tuple(
            TelemetryPrivacyRule(data_class=data_class, disposition=disposition)
            for data_class, disposition in REQUIRED_TELEMETRY_DISPOSITIONS.items()
        ),
    )


def evaluate_telemetry_privacy_profile(
    profile: object,
    *,
    enabled: bool,
) -> TelemetryPrivacyReadiness:
    """Validate declaration completeness without touching a runtime surface."""

    if type(enabled) is not bool:
        raise ValueError("enabled must be exact bool")
    if not enabled:
        return TelemetryPrivacyReadiness(
            declaration_ready=False,
            reason=TelemetryPrivacyReason.FEATURE_DISABLED,
        )
    if type(profile) is not TelemetryPrivacyProfile:
        return TelemetryPrivacyReadiness(
            declaration_ready=False,
            reason=TelemetryPrivacyReason.INVALID_PROFILE,
        )
    try:
        validated = TelemetryPrivacyProfile(
            contract_version=profile.contract_version,
            profile_id=profile.profile_id,
            rules=tuple(
                TelemetryPrivacyRule(
                    data_class=rule.data_class,
                    disposition=rule.disposition,
                )
                for rule in profile.rules
            ),
        )
    except Exception:
        return TelemetryPrivacyReadiness(
            declaration_ready=False,
            reason=TelemetryPrivacyReason.INVALID_PROFILE,
        )
    actual = {rule.data_class: rule.disposition for rule in validated.rules}
    if any(
        actual[data_class] is not required
        for data_class, required in REQUIRED_TELEMETRY_DISPOSITIONS.items()
    ):
        return TelemetryPrivacyReadiness(
            declaration_ready=False,
            reason=TelemetryPrivacyReason.UNSAFE_DISPOSITION,
        )
    return TelemetryPrivacyReadiness(
        declaration_ready=True,
        reason=TelemetryPrivacyReason.DECLARATION_READY,
    )


__all__ = [
    "REQUIRED_TELEMETRY_DISPOSITIONS",
    "TELEMETRY_PRIVACY_CONTRACT_VERSION",
    "TelemetryDataClass",
    "TelemetryDisposition",
    "TelemetryPrivacyProfile",
    "TelemetryPrivacyReadiness",
    "TelemetryPrivacyReason",
    "TelemetryPrivacyRule",
    "default_telemetry_privacy_profile",
    "evaluate_telemetry_privacy_profile",
]
