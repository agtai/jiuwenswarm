# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Current-owner forwarding permit for product P3 mutation calls.

The durable confirmation ledger proves that a confirmation was issued for one
exact mutation.  It does not prove that the caller is the current product route
owner.  This wrapper supplies that second, task-local fence.  A direct legacy
``task.create`` or ``task.cancel`` call has no permit and therefore cannot use
the injected verifier, even if transport credentials are present.
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Iterator

from jiuwenswarm.common.schema.live_voice_contract_v2 import ErrorCode

from .formal_task_models import FormalTaskViolation
from .p3_confirmation import (
    BoundedP3ConfirmationOwner,
    P3ConfirmationBinding,
    P3ConfirmationOwnerContext,
    P3ConfirmationVerifier,
    ValidatedP3ConfirmationForwarding,
    VerifiedP3Confirmation,
)


@dataclass(slots=True)
class _ForwardingPermit:
    confirmation_id: str
    binding: P3ConfirmationBinding
    owner: P3ConfirmationOwnerContext
    _used: bool = False
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def claim(self, confirmation_id: str, binding: P3ConfirmationBinding) -> bool:
        with self._lock:
            if (
                self._used
                or confirmation_id != self.confirmation_id
                or binding != self.binding
            ):
                return False
            self._used = True
            return True


class ProductP3ConfirmationForwarder(P3ConfirmationVerifier):
    """Permit-gated verifier injected into the authenticated P3 composition."""

    def __init__(self, owner: BoundedP3ConfirmationOwner) -> None:
        if not isinstance(owner, BoundedP3ConfirmationOwner):
            raise FormalTaskViolation(
                "INVALID_P3_CONFIRMATION_FORWARDER",
                "a bounded confirmation owner is required",
                ErrorCode.INVALID_ARGUMENT,
            )
        verifier = owner.raw_verifier
        if verifier is None:
            raise FormalTaskViolation(
                "P3_CONFIRMATION_ISSUER_UNAVAILABLE",
                "the product confirmation owner is disabled",
                ErrorCode.UNAVAILABLE,
            )
        self._owner = owner
        self._verifier = verifier
        self._permit: ContextVar[_ForwardingPermit | None] = ContextVar(
            f"live_voice_p3_confirmation_permit_{id(self)}",
            default=None,
        )

    @property
    def owner(self) -> BoundedP3ConfirmationOwner:
        return self._owner

    @contextmanager
    def permit(
        self,
        validated: ValidatedP3ConfirmationForwarding,
    ) -> Iterator[None]:
        """Authorize one exact verifier call in the current async context."""

        if not isinstance(validated, ValidatedP3ConfirmationForwarding):
            raise FormalTaskViolation(
                "INVALID_P3_CONFIRMATION_FORWARDING",
                "validated current-owner confirmation facts are required",
                ErrorCode.INVALID_ARGUMENT,
            )
        token = self._permit.set(
            _ForwardingPermit(
                confirmation_id=validated.confirmation_id,
                binding=validated.binding,
                owner=validated.owner,
            )
        )
        try:
            yield
        finally:
            self._permit.reset(token)

    def verify_and_consume(
        self,
        confirmation_id: str,
        binding: P3ConfirmationBinding,
        *,
        now: str,
    ) -> VerifiedP3Confirmation:
        permit = self._permit.get()
        if permit is None or not permit.claim(confirmation_id, binding):
            raise FormalTaskViolation(
                "P3_CONFIRMATION_FORWARDING_REQUIRED",
                "formal task mutation requires a current product forwarding permit",
                ErrorCode.PERMISSION_DENIED,
            )
        return self._verifier.verify_and_consume(
            confirmation_id,
            binding,
            now=now,
        )


__all__ = ["ProductP3ConfirmationForwarder"]
