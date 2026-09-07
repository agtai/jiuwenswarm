# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Shared pure validation; each durability fact retains its own error contract."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    MAX_SAFE_INTEGER,
    Assurance,
    ScopeRef,
)

Violation = Callable[[str, str], ValueError]
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def require_text(value, field_name, *, violation: Violation, reason, maximum=512):
    if type(value) is not str or not value.strip():
        raise violation(reason, f"{field_name} must be a non-empty exact string")
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise violation(
            reason, f"{field_name} must contain valid Unicode scalar values"
        ) from error
    if len(encoded) > maximum:
        raise violation(reason, f"{field_name} is outside the bounded range")
    return value


def require_integer(value, field_name, *, violation: Violation, reason, positive=False):
    if type(value) is not int or value < int(positive) or value > MAX_SAFE_INTEGER:
        kind = "positive" if positive else "non-negative"
        raise violation(reason, f"{field_name} must be one {kind} safe integer")
    return value


def require_digest(value, field_name="", *, violation: Violation, reason, message=None):
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        raise violation(reason, message or f"{field_name} must be lowercase SHA-256")
    return value


def require_scope(value, *, violation: Violation, reason, subject):
    if type(value) is not ScopeRef:
        raise violation(reason, f"{subject} must be exact")
    try:
        checked = ScopeRef.from_dict(value.to_dict())
    except (TypeError, ValueError) as error:
        raise violation(reason, f"{subject} is invalid") from error
    if checked.assurance is not Assurance.AUTHENTICATED:
        raise violation(reason, f"{subject} must be authenticated")
    return checked


def require_profile(value, *, violation: Violation, reason, subject):
    # Identity values use the text/digest helpers in this module themselves.
    from .durability_identity import (
        DurabilityIdentityViolation,
        DurabilityProfileBinding,
    )

    if type(value) is not DurabilityProfileBinding:
        raise violation(reason, f"{subject} must be exact")
    try:
        return DurabilityProfileBinding.from_dict(value.to_dict())
    except DurabilityIdentityViolation as error:
        raise violation(reason, f"{subject} is invalid") from error


def reject_duplicate_keys(pairs, *, violation: Violation, reason, message):
    result = {}
    for key, value in pairs:
        if key in result:
            raise violation(reason, message)
        result[key] = value
    return result


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()
