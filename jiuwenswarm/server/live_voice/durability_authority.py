# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Opaque, one-operation durability mutation authorization.

Checkpoint, effect, prefix, and recovery contracts are immutable data.  Only
the Direct runtime can mint this private construction-token receipt, and the
authoritative Store consumes its exact lease in the mutation transaction.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Final

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    ScopeRef,
    canonical_json_bytes,
)

from .durability_identity import DurabilityProfileBinding

_CONSTRUCTION_TOKEN = object()
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_OPERATIONS: Final = frozenset(
    {
        "checkpoint.append",
        "effect.append",
        "lineage.fork",
        "recovery.admit.applied",
        "recovery.admit.continue",
    }
)


def _text(value: object) -> bool:
    return (
        type(value) is str and bool(value.strip()) and len(value.encode("utf-8")) <= 512
    )


@dataclass(frozen=True, slots=True)
class DurabilityMutationAuthorization:
    """Opaque receipt exact-bound to one Store lease, prefix tip, and write."""

    operation: str
    scope: ScopeRef
    task_id: str
    producer_attempt_id: str
    candidate_attempt_id: str | None
    profile: DurabilityProfileBinding
    executor_owner_id: str
    executor_owner_generation: int
    checkpoint_head: int
    checkpoint_prefix_digest: str
    effect_head: int
    effect_prefix_digest: str
    payload_digest: str
    claim_owner_id: str
    claim_token: str
    claim_generation: int
    _store_identity: object = field(repr=False, compare=False)
    _construction_token: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if (
            self._construction_token is not _CONSTRUCTION_TOKEN
            or self.operation not in _OPERATIONS
            or type(self.scope) is not ScopeRef
            or not _text(self.task_id)
            or not _text(self.producer_attempt_id)
            or (
                self.candidate_attempt_id is not None
                and not _text(self.candidate_attempt_id)
            )
            or type(self.profile) is not DurabilityProfileBinding
            or not _text(self.executor_owner_id)
            or type(self.executor_owner_generation) is not int
            or self.executor_owner_generation < 0
            or type(self.checkpoint_head) is not int
            or self.checkpoint_head < 0
            or _SHA256.fullmatch(self.checkpoint_prefix_digest) is None
            or type(self.effect_head) is not int
            or self.effect_head < 0
            or _SHA256.fullmatch(self.effect_prefix_digest) is None
            or _SHA256.fullmatch(self.payload_digest) is None
            or not _text(self.claim_owner_id)
            or not _text(self.claim_token)
            or type(self.claim_generation) is not int
            or self.claim_generation <= 0
        ):
            raise ValueError("invalid durability mutation authorization")

    def is_for_store(self, store: object) -> bool:
        return self._store_identity is store


def _mint_durability_mutation_authorization(
    *,
    store: object,
    operation: str,
    scope: ScopeRef,
    task_id: str,
    producer_attempt_id: str,
    candidate_attempt_id: str | None,
    profile: DurabilityProfileBinding,
    executor_owner_id: str,
    executor_owner_generation: int,
    checkpoint_head: int,
    checkpoint_prefix_digest: str,
    effect_head: int,
    effect_prefix_digest: str,
    payload_digest: str,
    claim_owner_id: str,
    claim_token: str,
    claim_generation: int,
) -> DurabilityMutationAuthorization:
    """Private Direct/runtime issuer; callers outside the module get data only."""

    return DurabilityMutationAuthorization(
        operation=operation,
        scope=scope,
        task_id=task_id,
        producer_attempt_id=producer_attempt_id,
        candidate_attempt_id=candidate_attempt_id,
        profile=profile,
        executor_owner_id=executor_owner_id,
        executor_owner_generation=executor_owner_generation,
        checkpoint_head=checkpoint_head,
        checkpoint_prefix_digest=checkpoint_prefix_digest,
        effect_head=effect_head,
        effect_prefix_digest=effect_prefix_digest,
        payload_digest=payload_digest,
        claim_owner_id=claim_owner_id,
        claim_token=claim_token,
        claim_generation=claim_generation,
        _store_identity=store,
        _construction_token=_CONSTRUCTION_TOKEN,
    )


def _durability_authorization_payload_digest(payload: object) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


__all__ = ["DurabilityMutationAuthorization"]
