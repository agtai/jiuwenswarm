# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import Assurance, ScopeRef
from jiuwenswarm.server.live_voice.formal_task_models import FormalTaskViolation
from jiuwenswarm.server.live_voice.p3_confirmation import (
    BoundedP3ConfirmationOwner,
    P3ConfirmationBinding,
    P3ConfirmationOwnerContext,
    TrustedP3ConfirmationIssue,
)
from jiuwenswarm.server.live_voice.p3_product_confirmation import (
    ProductP3ConfirmationForwarder,
)


NOW = "2026-08-07T10:00:00Z"
EXPIRY = "2026-08-07T10:02:00Z"


def _facts() -> tuple[P3ConfirmationBinding, P3ConfirmationOwnerContext]:
    scope = ScopeRef(
        subject_id="user-1",
        project_id="project-1",
        session_id="session-1",
        assurance=Assurance.AUTHENTICATED,
    )
    return (
        P3ConfirmationBinding(
            principal_id="user-1",
            scope=scope,
            operation="task.cancel",
            command_id="command-1",
            target_task_id="task-1",
            intent_fingerprint="intent-1",
        ),
        P3ConfirmationOwnerContext(
            session_id="session-1",
            correlation_id="correlation-1",
            owner_generation=1,
        ),
    )


def _ready(tmp_path: Path):
    owner = BoundedP3ConfirmationOwner(tmp_path / "confirmations.sqlite3", enabled=True)
    binding, context = _facts()
    issued = owner.issue(
        TrustedP3ConfirmationIssue(
            binding=binding,
            owner=context,
            expires_at=EXPIRY,
            confirmation_id="confirmation-1",
        ),
        now=NOW,
    )
    validated = owner.validate_for_forwarding(
        issued.confirmation_id, binding, context, now=NOW
    )
    return owner, ProductP3ConfirmationForwarder(owner), binding, validated


def test_disabled_owner_cannot_create_product_forwarder(tmp_path: Path) -> None:
    database = tmp_path / "disabled" / "confirmations.sqlite3"

    with pytest.raises(FormalTaskViolation) as raised:
        ProductP3ConfirmationForwarder(BoundedP3ConfirmationOwner(database))

    assert raised.value.reason == "P3_CONFIRMATION_ISSUER_UNAVAILABLE"
    assert not database.exists()


def test_direct_verifier_call_has_no_product_permit_and_does_not_consume(
    tmp_path: Path,
) -> None:
    _owner, forwarder, binding, validated = _ready(tmp_path)

    with pytest.raises(FormalTaskViolation) as raised:
        forwarder.verify_and_consume("confirmation-1", binding, now=NOW)

    assert raised.value.reason == "P3_CONFIRMATION_FORWARDING_REQUIRED"
    with forwarder.permit(validated):
        first = forwarder.verify_and_consume("confirmation-1", binding, now=NOW)
    assert first.replayed is False


def test_exact_permit_is_one_use_and_binding_specific(tmp_path: Path) -> None:
    _owner, forwarder, binding, validated = _ready(tmp_path)

    with forwarder.permit(validated):
        with pytest.raises(FormalTaskViolation) as wrong:
            forwarder.verify_and_consume("confirmation-other", binding, now=NOW)
        first = forwarder.verify_and_consume("confirmation-1", binding, now=NOW)
        with pytest.raises(FormalTaskViolation) as used:
            forwarder.verify_and_consume("confirmation-1", binding, now=NOW)

    assert wrong.value.reason == "P3_CONFIRMATION_FORWARDING_REQUIRED"
    assert first.replayed is False
    assert used.value.reason == "P3_CONFIRMATION_FORWARDING_REQUIRED"


@pytest.mark.asyncio
async def test_permit_flows_to_owned_thread_without_leaking_to_sibling(
    tmp_path: Path,
) -> None:
    _owner, forwarder, binding, validated = _ready(tmp_path)
    entered = asyncio.Event()
    release = asyncio.Event()

    async def owned():
        with forwarder.permit(validated):
            entered.set()
            await release.wait()
            return await asyncio.to_thread(
                forwarder.verify_and_consume,
                "confirmation-1",
                binding,
                now=NOW,
            )

    task = asyncio.create_task(owned())
    await entered.wait()
    with pytest.raises(FormalTaskViolation) as sibling:
        await asyncio.to_thread(
            forwarder.verify_and_consume,
            "confirmation-1",
            binding,
            now=NOW,
        )
    release.set()
    result = await task

    assert sibling.value.reason == "P3_CONFIRMATION_FORWARDING_REQUIRED"
    assert result.replayed is False
