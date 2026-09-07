# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Authority-free identity values shared by pure durability assets.

These values describe the exact selected Executor Adapter/profile. They do not
select a profile, prove a capability, persist admission, or authorize work.
"""

from __future__ import annotations

from functools import partial
from .durability_validation import (
    require_digest,
    require_text,
)

from dataclasses import dataclass
from typing import Final


DURABILITY_PROFILE_BINDING_VERSION: Final = "live-voice.durability-profile-binding.v1"

_MAX_DURABILITY_TEXT_BYTES = 512
_DURABILITY_LEVELS = frozenset({"D0", "D1", "D2"})


class DurabilityIdentityViolation(ValueError):
    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


_text = partial(
    require_text,
    violation=DurabilityIdentityViolation,
    reason="INVALID_DURABILITY_PROFILE",
    maximum=_MAX_DURABILITY_TEXT_BYTES,
)


_digest = partial(
    require_digest,
    violation=DurabilityIdentityViolation,
    reason="INVALID_DURABILITY_PROFILE",
)


@dataclass(frozen=True, slots=True)
class DurabilityProfileBinding:
    """Exact persisted-profile identity without capability authority."""

    executor_id: str
    adapter_id: str
    profile_id: str
    profile_version: str
    profile_digest: str
    durability_level: str
    durability_capability_version: str
    contract_version: str = DURABILITY_PROFILE_BINDING_VERSION

    def __post_init__(self) -> None:
        if self.contract_version != DURABILITY_PROFILE_BINDING_VERSION:
            raise DurabilityIdentityViolation(
                "INVALID_DURABILITY_PROFILE",
                "durability profile binding version is unsupported",
            )
        _text(self.executor_id, "profile.executor_id")
        _text(self.adapter_id, "profile.adapter_id")
        _text(self.profile_id, "profile.profile_id")
        _text(self.profile_version, "profile.profile_version")
        _digest(self.profile_digest, "profile.profile_digest")
        if self.durability_level not in _DURABILITY_LEVELS:
            raise DurabilityIdentityViolation(
                "INVALID_DURABILITY_PROFILE",
                "profile.durability_level must be D0, D1, or D2",
            )
        _text(
            self.durability_capability_version,
            "profile.durability_capability_version",
        )

    @classmethod
    def from_dict(cls, payload: object) -> DurabilityProfileBinding:
        if type(payload) is not dict or set(payload) != {
            "contract_version",
            "executor_id",
            "adapter_id",
            "profile_id",
            "profile_version",
            "profile_digest",
            "durability_level",
            "durability_capability_version",
        }:
            raise DurabilityIdentityViolation(
                "INVALID_DURABILITY_PROFILE",
                "durability profile binding has an invalid closed field set",
            )
        return cls(
            contract_version=_text(
                payload["contract_version"], "profile.contract_version"
            ),
            executor_id=_text(payload["executor_id"], "profile.executor_id"),
            adapter_id=_text(payload["adapter_id"], "profile.adapter_id"),
            profile_id=_text(payload["profile_id"], "profile.profile_id"),
            profile_version=_text(
                payload["profile_version"], "profile.profile_version"
            ),
            profile_digest=_digest(payload["profile_digest"], "profile.profile_digest"),
            durability_level=_text(
                payload["durability_level"], "profile.durability_level"
            ),
            durability_capability_version=_text(
                payload["durability_capability_version"],
                "profile.durability_capability_version",
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "contract_version": self.contract_version,
            "executor_id": self.executor_id,
            "adapter_id": self.adapter_id,
            "profile_id": self.profile_id,
            "profile_version": self.profile_version,
            "profile_digest": self.profile_digest,
            "durability_level": self.durability_level,
            "durability_capability_version": self.durability_capability_version,
        }

    @property
    def capability_authority(self) -> bool:
        return False


__all__ = [
    "DURABILITY_PROFILE_BINDING_VERSION",
    "DurabilityIdentityViolation",
    "DurabilityProfileBinding",
]
