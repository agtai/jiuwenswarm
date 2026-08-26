# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import Assurance, ScopeRef
from jiuwenswarm.server.live_voice.formal_task_models import (
    FormalTaskViolation,
    ResolvedTaskContext,
)
from jiuwenswarm.server.live_voice.p3_confirmation import (
    BoundedP3ConfirmationOwner,
    P3_CONFIRMATION_MAX_CAPACITY,
    P3ConfirmationBinding,
    P3ConfirmationOwnerContext,
    PreparedP3RetryFacts,
    SqliteP3ConfirmationLedger,
    TrustedP3ConfirmationIssue,
    p3_confirmation_intent_fingerprint,
)
from jiuwenswarm.server.live_voice.p3_product_confirmation import (
    ProductP3ConfirmationForwarder,
)


NOW = "2026-08-07T10:00:00Z"
EXPIRY = "2026-08-07T10:02:00Z"


def _scope(
    *,
    subject_id: str = "user-1",
    project_id: str = "project-1",
    session_id: str = "session-1",
) -> ScopeRef:
    return ScopeRef(
        subject_id=subject_id,
        project_id=project_id,
        session_id=session_id,
        assurance=Assurance.AUTHENTICATED,
    )


def _binding(
    *,
    scope: ScopeRef | None = None,
    operation: str = "task.cancel",
    command_id: str = "command-1",
    target_task_id: str | None = "task-1",
    intent_fingerprint: str = "intent-1",
) -> P3ConfirmationBinding:
    resolved_scope = scope or _scope()
    return P3ConfirmationBinding(
        principal_id=resolved_scope.subject_id,
        scope=resolved_scope,
        operation=operation,
        command_id=command_id,
        target_task_id=target_task_id,
        intent_fingerprint=intent_fingerprint,
    )


def _owner_context(
    *,
    session_id: str = "session-1",
    correlation_id: str = "correlation-1",
    owner_generation: int = 1,
) -> P3ConfirmationOwnerContext:
    return P3ConfirmationOwnerContext(
        session_id=session_id,
        correlation_id=correlation_id,
        owner_generation=owner_generation,
    )


def _issue(
    *,
    binding: P3ConfirmationBinding | None = None,
    owner: P3ConfirmationOwnerContext | None = None,
    expires_at: str = EXPIRY,
    confirmation_id: str = "confirmation-1",
) -> TrustedP3ConfirmationIssue:
    return TrustedP3ConfirmationIssue(
        binding=binding or _binding(),
        owner=owner or _owner_context(),
        expires_at=expires_at,
        confirmation_id=confirmation_id,
    )


def _confirmation_row(database: Path, confirmation_id: str) -> sqlite3.Row:
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            "SELECT * FROM p3_confirmations WHERE confirmation_id=?",
            (confirmation_id,),
        ).fetchone()
        assert row is not None
        return row
    finally:
        connection.close()


def _confirmation_count(database: Path) -> int:
    connection = sqlite3.connect(database)
    try:
        return int(
            connection.execute("SELECT COUNT(*) FROM p3_confirmations").fetchone()[0]
        )
    finally:
        connection.close()


def _confirmation_rows(database: Path) -> list[sqlite3.Row]:
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        return connection.execute(
            "SELECT * FROM p3_confirmations ORDER BY issued_at, confirmation_id"
        ).fetchall()
    finally:
        connection.close()


def test_owner_is_default_off_and_allocates_no_database(tmp_path: Path) -> None:
    database = tmp_path / "disabled" / "confirmations.sqlite3"

    owner = BoundedP3ConfirmationOwner(database)

    assert owner.raw_verifier is None
    assert not database.exists()
    assert not database.parent.exists()
    with pytest.raises(FormalTaskViolation) as raised:
        owner.issue(_issue(), now=NOW)
    assert raised.value.reason == "P3_CONFIRMATION_ISSUER_UNAVAILABLE"
    assert not database.exists()


def test_enabled_owner_issues_validates_then_existing_verifier_consumes(
    tmp_path: Path,
) -> None:
    database = tmp_path / "confirmations.sqlite3"
    owner = BoundedP3ConfirmationOwner(database, enabled=True)
    binding = _binding()
    context = _owner_context()

    issued = owner.issue(_issue(binding=binding, owner=context), now=NOW)
    validated = owner.validate_for_forwarding(
        issued.confirmation_id,
        binding,
        context,
        now=NOW,
    )

    assert issued.replayed is False
    assert validated.binding == binding
    assert validated.owner == context
    assert _confirmation_row(database, issued.confirmation_id)["consumed_at"] is None
    verifier = owner.raw_verifier
    assert verifier is not None
    first = verifier.verify_and_consume(issued.confirmation_id, binding, now=NOW)
    replay = verifier.verify_and_consume(issued.confirmation_id, binding, now=NOW)
    assert first.replayed is False
    assert replay.replayed is True


def test_exact_issue_replay_is_idempotent_but_conflict_is_rejected(
    tmp_path: Path,
) -> None:
    database = tmp_path / "confirmations.sqlite3"
    owner = BoundedP3ConfirmationOwner(database, enabled=True, capacity=1)
    issue = _issue()

    first = owner.issue(issue, now=NOW)
    replay = BoundedP3ConfirmationOwner(
        database,
        enabled=True,
        capacity=1,
    ).issue(
        issue,
        now="2026-08-07T10:00:01Z",
    )
    with pytest.raises(FormalTaskViolation) as raised:
        owner.issue(
            replace(
                issue,
                owner=replace(issue.owner, correlation_id="correlation-other"),
            ),
            now=NOW,
        )

    assert first.replayed is False
    assert replay == replace(first, replayed=True)
    assert raised.value.reason == "P3_CONFIRMATION_CONFLICT"
    assert _confirmation_count(database) == 1
    assert _confirmation_row(database, first.confirmation_id)["consumed_at"] is None


@pytest.mark.parametrize("confirmation_id", [None, "", "   "])
def test_trusted_issue_requires_caller_stable_non_empty_confirmation_id(
    confirmation_id: object,
) -> None:
    with pytest.raises(FormalTaskViolation) as raised:
        TrustedP3ConfirmationIssue(
            binding=_binding(),
            owner=_owner_context(),
            expires_at=EXPIRY,
            confirmation_id=confirmation_id,  # type: ignore[arg-type]
        )

    assert raised.value.reason == "INVALID_P3_CONFIRMATION"


def test_trusted_issue_cannot_omit_confirmation_id() -> None:
    with pytest.raises(TypeError):
        TrustedP3ConfirmationIssue(  # type: ignore[call-arg]
            binding=_binding(),
            owner=_owner_context(),
            expires_at=EXPIRY,
        )


@pytest.mark.parametrize(
    "capacity",
    [0, -1, True, P3_CONFIRMATION_MAX_CAPACITY + 1],
)
def test_capacity_must_be_within_fixed_hard_bound(
    tmp_path: Path,
    capacity: object,
) -> None:
    database = tmp_path / "disabled" / "confirmations.sqlite3"

    with pytest.raises(FormalTaskViolation) as raised:
        BoundedP3ConfirmationOwner(
            database,
            capacity=capacity,  # type: ignore[arg-type]
        )

    assert raised.value.reason == "INVALID_P3_CONFIRMATION_CAPACITY"
    assert not database.exists()


def test_low_level_ledger_also_enforces_hard_capacity(tmp_path: Path) -> None:
    database = tmp_path / "confirmations.sqlite3"
    ledger = SqliteP3ConfirmationLedger(database, capacity=1)
    ledger.issue(
        _binding(),
        expires_at=EXPIRY,
        now=NOW,
        confirmation_id="legacy-confirmation-1",
    )

    with pytest.raises(FormalTaskViolation) as raised:
        ledger.issue(
            _binding(
                command_id="command-2",
                target_task_id="task-2",
                intent_fingerprint="intent-2",
            ),
            expires_at=EXPIRY,
            now=NOW,
            confirmation_id="legacy-confirmation-2",
        )

    assert raised.value.reason == "P3_CONFIRMATION_CAPACITY_EXCEEDED"
    assert _confirmation_count(database) == 1


@pytest.mark.parametrize("terminal_kind", ("consumed", "expired"))
def test_low_level_terminal_row_reclaims_capacity_without_reauthorizing(
    tmp_path: Path,
    terminal_kind: str,
) -> None:
    database = tmp_path / "confirmations.sqlite3"
    ledger = SqliteP3ConfirmationLedger(database, capacity=1)
    first_binding = _binding()
    first_expiry = (
        "2026-08-07T10:01:00Z"
        if terminal_kind == "consumed"
        else "2026-08-07T10:00:01Z"
    )
    first_id = ledger.issue(
        first_binding,
        expires_at=first_expiry,
        now=NOW,
        confirmation_id="legacy-confirmation-1",
    )
    if terminal_kind == "consumed":
        ledger.verify_and_consume(first_id, first_binding, now=NOW)

    reopened = SqliteP3ConfirmationLedger(database, capacity=1)
    second_binding = _binding(
        command_id="command-2",
        target_task_id="task-2",
        intent_fingerprint="intent-2",
    )
    second_id = reopened.issue(
        second_binding,
        expires_at=EXPIRY,
        now="2026-08-07T10:00:01Z",
        confirmation_id="legacy-confirmation-2",
    )

    if terminal_kind == "consumed":
        assert (
            reopened.verify_and_consume(
                first_id,
                first_binding,
                now="2026-08-07T10:00:02Z",
            ).replayed
            is True
        )
        assert len(_confirmation_rows(database)) == 2
    else:
        with pytest.raises(FormalTaskViolation) as stale:
            reopened.verify_and_consume(
                first_id,
                first_binding,
                now="2026-08-07T10:00:02Z",
            )
        assert stale.value.reason == "P3_CONFIRMATION_EXPIRED"
        assert len(_confirmation_rows(database)) == 2
    assert second_id == "legacy-confirmation-2"
    assert _confirmation_row(database, second_id)["consumed_at"] is None


def test_full_capacity_allows_exact_replay_but_rejects_new_issue(
    tmp_path: Path,
) -> None:
    database = tmp_path / "confirmations.sqlite3"
    owner = BoundedP3ConfirmationOwner(database, enabled=True, capacity=1)
    issue = _issue()
    first = owner.issue(issue, now=NOW)

    replay = owner.issue(issue, now="2026-08-07T10:00:01Z")
    with pytest.raises(FormalTaskViolation) as raised:
        owner.issue(
            replace(issue, confirmation_id="confirmation-2"),
            now=NOW,
        )

    assert first.replayed is False
    assert replay.replayed is True
    assert raised.value.reason == "P3_CONFIRMATION_CAPACITY_EXCEEDED"
    assert _confirmation_count(database) == 1
    assert _confirmation_row(database, first.confirmation_id)["command_id"] == (
        issue.binding.command_id
    )


def test_concurrent_exact_issue_retries_retain_one_row(tmp_path: Path) -> None:
    database = tmp_path / "confirmations.sqlite3"
    owner = BoundedP3ConfirmationOwner(database, enabled=True, capacity=1)
    issue = _issue()

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: owner.issue(issue, now=NOW), range(8)))

    assert sum(not result.replayed for result in results) == 1
    assert sum(result.replayed for result in results) == 7
    assert {result.confirmation_id for result in results} == {"confirmation-1"}
    assert _confirmation_count(database) == 1


def test_concurrent_new_issuance_cannot_cross_capacity(tmp_path: Path) -> None:
    database = tmp_path / "confirmations.sqlite3"
    owner = BoundedP3ConfirmationOwner(database, enabled=True, capacity=2)

    def attempt(index: int) -> tuple[str, str]:
        issue = _issue(
            binding=_binding(
                command_id=f"command-{index}",
                target_task_id=f"task-{index}",
                intent_fingerprint=f"intent-{index}",
            ),
            confirmation_id=f"confirmation-{index}",
        )
        try:
            return "issued", owner.issue(issue, now=NOW).confirmation_id
        except FormalTaskViolation as exc:
            return "rejected", exc.reason

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(attempt, range(8)))

    assert sum(kind == "issued" for kind, _ in outcomes) == 2
    assert (
        sum(value == "P3_CONFIRMATION_CAPACITY_EXCEEDED" for _, value in outcomes) == 6
    )
    assert _confirmation_count(database) == 2


def test_consumed_confirmation_reclaims_capacity_with_durable_minimal_replay_fence(
    tmp_path: Path,
) -> None:
    database = tmp_path / "confirmations.sqlite3"
    owner = BoundedP3ConfirmationOwner(database, enabled=True, capacity=1)
    issue = _issue(expires_at="2026-08-07T10:01:00Z")
    confirmation_id = owner.issue(issue, now=NOW).confirmation_id
    verifier = owner.raw_verifier
    assert verifier is not None
    verifier.verify_and_consume(confirmation_id, issue.binding, now=NOW)

    reopened = BoundedP3ConfirmationOwner(database, enabled=True, capacity=1)
    second_issue = _issue(
        binding=_binding(
            command_id="command-2",
            target_task_id="task-2",
            intent_fingerprint="intent-2",
        ),
        owner=_owner_context(correlation_id="correlation-2"),
        confirmation_id="confirmation-2",
        expires_at=EXPIRY,
    )
    second = reopened.issue(second_issue, now="2026-08-07T10:00:01Z")

    replayed_issue = reopened.issue(issue, now="2026-08-07T10:00:02Z")
    replayed_forwarding = reopened.validate_for_forwarding(
        confirmation_id,
        issue.binding,
        issue.owner,
        now="2026-08-07T10:00:02Z",
    )
    with pytest.raises(FormalTaskViolation) as wrong_owner:
        reopened.validate_for_forwarding(
            confirmation_id,
            issue.binding,
            replace(issue.owner, correlation_id="correlation-other"),
            now="2026-08-07T10:00:02Z",
        )
    reopened_verifier = reopened.raw_verifier
    assert reopened_verifier is not None
    forwarder = ProductP3ConfirmationForwarder(reopened)
    with forwarder.permit(replayed_forwarding):
        replayed_consume = forwarder.verify_and_consume(
            confirmation_id,
            issue.binding,
            now="2026-08-07T10:00:02Z",
        )
    with pytest.raises(FormalTaskViolation) as mismatched:
        reopened_verifier.verify_and_consume(
            confirmation_id,
            _binding(intent_fingerprint="intent-other"),
            now="2026-08-07T10:00:02Z",
        )

    rows = _confirmation_rows(database)
    assert second.confirmation_id == "confirmation-2"
    assert second.replayed is False
    assert replayed_issue.replayed is True
    assert wrong_owner.value.reason == "P3_CONFIRMATION_BINDING_MISMATCH"
    assert replayed_forwarding.confirmation_id == confirmation_id
    assert replayed_forwarding.binding == issue.binding
    assert replayed_forwarding.owner == issue.owner
    assert replayed_consume.replayed is True
    assert mismatched.value.reason == "P3_CONFIRMATION_BINDING_MISMATCH"
    assert {row["confirmation_id"] for row in rows} == {
        "confirmation-1",
        "confirmation-2",
    }
    fence = next(row for row in rows if row["confirmation_id"] == confirmation_id)
    serialized_fence = "|".join(
        str(fence[field])
        for field in (
            "principal_id",
            "scope_key",
            "operation",
            "command_id",
            "target_task_id",
            "intent_fingerprint",
            "owner_session_id",
            "owner_correlation_id",
            "owner_generation",
        )
    )
    for heavy_value in (
        "user-1",
        "project-1",
        "session-1",
        "task-1",
        "command-1",
        "intent-1",
        "correlation-1",
    ):
        assert heavy_value not in serialized_fence
    assert _confirmation_row(database, second.confirmation_id)["consumed_at"] is None


def test_expired_confirmation_reclaims_capacity_and_old_token_stays_expired(
    tmp_path: Path,
) -> None:
    database = tmp_path / "confirmations.sqlite3"
    owner = BoundedP3ConfirmationOwner(database, enabled=True, capacity=1)
    expired_issue = _issue(expires_at="2026-08-07T10:00:01Z")
    expired_id = owner.issue(expired_issue, now=NOW).confirmation_id

    reopened = BoundedP3ConfirmationOwner(database, enabled=True, capacity=1)
    active_issue = _issue(
        binding=_binding(
            command_id="command-2",
            target_task_id="task-2",
            intent_fingerprint="intent-2",
        ),
        owner=_owner_context(correlation_id="correlation-2"),
        confirmation_id="confirmation-2",
    )
    active = reopened.issue(active_issue, now="2026-08-07T10:00:01Z")

    verifier = reopened.raw_verifier
    assert verifier is not None
    with pytest.raises(FormalTaskViolation) as stale:
        verifier.verify_and_consume(
            expired_id,
            expired_issue.binding,
            now="2026-08-07T10:00:01Z",
        )

    assert active.replayed is False
    assert stale.value.reason == "P3_CONFIRMATION_EXPIRED"
    assert {row["confirmation_id"] for row in _confirmation_rows(database)} == {
        "confirmation-1",
        "confirmation-2",
    }
    assert _confirmation_row(database, expired_id)["consumed_at"] is not None
    assert _confirmation_row(database, active.confirmation_id)["consumed_at"] is None


def test_replay_fence_is_bounded_and_evicted_token_never_authorizes(
    tmp_path: Path,
) -> None:
    database = tmp_path / "confirmations.sqlite3"
    owner = BoundedP3ConfirmationOwner(database, enabled=True, capacity=1)
    first_issue = _issue(expires_at="2026-08-07T10:01:00Z")
    first = owner.issue(first_issue, now=NOW)
    verifier = owner.raw_verifier
    assert verifier is not None
    verifier.verify_and_consume(first.confirmation_id, first_issue.binding, now=NOW)

    second_issue = _issue(
        binding=_binding(
            command_id="command-2",
            target_task_id="task-2",
            intent_fingerprint="intent-2",
        ),
        owner=_owner_context(correlation_id="correlation-2"),
        confirmation_id="confirmation-2",
        expires_at="2026-08-07T10:01:00Z",
    )
    second = owner.issue(second_issue, now="2026-08-07T10:00:01Z")
    verifier.verify_and_consume(
        second.confirmation_id,
        second_issue.binding,
        now="2026-08-07T10:00:01Z",
    )
    third_issue = _issue(
        binding=_binding(
            command_id="command-3",
            target_task_id="task-3",
            intent_fingerprint="intent-3",
        ),
        owner=_owner_context(correlation_id="correlation-3"),
        confirmation_id="confirmation-3",
    )
    third = owner.issue(third_issue, now="2026-08-07T10:00:02Z")

    with pytest.raises(FormalTaskViolation) as evicted:
        verifier.verify_and_consume(
            first.confirmation_id,
            first_issue.binding,
            now="2026-08-07T10:00:02Z",
        )
    second_replay = verifier.verify_and_consume(
        second.confirmation_id,
        second_issue.binding,
        now="2026-08-07T10:00:02Z",
    )

    assert third.replayed is False
    assert evicted.value.reason == "P3_CONFIRMATION_INVALID"
    assert second_replay.replayed is True
    rows = _confirmation_rows(database)
    assert len(rows) == 2
    assert {row["confirmation_id"] for row in rows} == {
        "confirmation-2",
        "confirmation-3",
    }
    assert _confirmation_row(database, third.confirmation_id)["consumed_at"] is None


def test_concurrent_reopen_issuers_recover_consumed_capacity_once(
    tmp_path: Path,
) -> None:
    database = tmp_path / "confirmations.sqlite3"
    initial_owner = BoundedP3ConfirmationOwner(database, enabled=True, capacity=1)
    initial_issue = _issue(expires_at="2026-08-07T10:01:00Z")
    initial = initial_owner.issue(initial_issue, now=NOW)
    initial_verifier = initial_owner.raw_verifier
    assert initial_verifier is not None
    initial_verifier.verify_and_consume(
        initial.confirmation_id,
        initial_issue.binding,
        now=NOW,
    )
    owners = (
        BoundedP3ConfirmationOwner(database, enabled=True, capacity=1),
        BoundedP3ConfirmationOwner(database, enabled=True, capacity=1),
    )

    def attempt(index: int) -> tuple[str, str]:
        candidate = _issue(
            binding=_binding(
                command_id=f"command-{index}",
                target_task_id=f"task-{index}",
                intent_fingerprint=f"intent-{index}",
            ),
            owner=_owner_context(correlation_id=f"correlation-{index}"),
            confirmation_id=f"confirmation-{index}",
        )
        try:
            return "issued", owners[index - 2].issue(
                candidate,
                now="2026-08-07T10:00:01Z",
            ).confirmation_id
        except FormalTaskViolation as exc:
            return "rejected", exc.reason

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(attempt, (2, 3)))

    assert sum(kind == "issued" for kind, _ in outcomes) == 1
    assert outcomes.count(("rejected", "P3_CONFIRMATION_CAPACITY_EXCEEDED")) == 1
    rows = _confirmation_rows(database)
    assert len(rows) == 2
    assert sum(row["consumed_at"] is None for row in rows) == 1
    assert sum(row["consumed_at"] is not None for row in rows) == 1
    reopened_verifier = owners[0].raw_verifier
    assert reopened_verifier is not None
    assert (
        reopened_verifier.verify_and_consume(
            initial.confirmation_id,
            initial_issue.binding,
            now="2026-08-07T10:00:02Z",
        ).replayed
        is True
    )


@pytest.mark.parametrize("failure_point", ("cleanup", "insert"))
def test_capacity_recovery_failure_rolls_back_before_retry(
    tmp_path: Path,
    failure_point: str,
) -> None:
    database = tmp_path / "confirmations.sqlite3"
    owner = BoundedP3ConfirmationOwner(database, enabled=True, capacity=1)
    initial_issue = _issue(expires_at="2026-08-07T10:01:00Z")
    initial = owner.issue(initial_issue, now=NOW)
    verifier = owner.raw_verifier
    assert verifier is not None
    verifier.verify_and_consume(initial.confirmation_id, initial_issue.binding, now=NOW)
    before = [tuple(row) for row in _confirmation_rows(database)]

    connection = sqlite3.connect(database)
    try:
        if failure_point == "cleanup":
            connection.executescript(
                """
                CREATE TRIGGER reject_confirmation_cleanup_update
                BEFORE UPDATE ON p3_confirmations
                WHEN OLD.consumed_at IS NOT NULL
                BEGIN
                    SELECT RAISE(ABORT, 'injected cleanup failure');
                END;
                CREATE TRIGGER reject_confirmation_cleanup_delete
                BEFORE DELETE ON p3_confirmations
                BEGIN
                    SELECT RAISE(ABORT, 'injected cleanup failure');
                END;
                """
            )
        else:
            connection.execute(
                """
                CREATE TRIGGER reject_confirmation_insert
                BEFORE INSERT ON p3_confirmations
                WHEN NEW.confirmation_id = 'confirmation-2'
                BEGIN
                    SELECT RAISE(ABORT, 'injected insert failure');
                END
                """
            )
        connection.commit()
    finally:
        connection.close()

    second_issue = _issue(
        binding=_binding(
            command_id="command-2",
            target_task_id="task-2",
            intent_fingerprint="intent-2",
        ),
        owner=_owner_context(correlation_id="correlation-2"),
        confirmation_id="confirmation-2",
    )
    with pytest.raises(FormalTaskViolation) as failed:
        owner.issue(second_issue, now="2026-08-07T10:00:01Z")

    assert failed.value.reason == "P3_CONFIRMATION_UNAVAILABLE"
    assert [tuple(row) for row in _confirmation_rows(database)] == before
    assert (
        verifier.verify_and_consume(
            initial.confirmation_id,
            initial_issue.binding,
            now="2026-08-07T10:00:02Z",
        ).replayed
        is True
    )

    connection = sqlite3.connect(database)
    try:
        trigger = (
            "reject_confirmation_insert"
            if failure_point == "insert"
            else "reject_confirmation_cleanup_update"
        )
        connection.execute(f"DROP TRIGGER {trigger}")
        if failure_point == "cleanup":
            connection.execute("DROP TRIGGER reject_confirmation_cleanup_delete")
        connection.commit()
    finally:
        connection.close()

    recovered = BoundedP3ConfirmationOwner(
        database,
        enabled=True,
        capacity=1,
    ).issue(second_issue, now="2026-08-07T10:00:02Z")
    assert recovered.replayed is False


def test_create_confirmation_binds_no_existing_target(tmp_path: Path) -> None:
    owner = BoundedP3ConfirmationOwner(tmp_path / "confirmations.sqlite3", enabled=True)
    binding = _binding(
        operation="task.create",
        target_task_id=None,
        intent_fingerprint="create-intent-1",
    )
    issue = _issue(binding=binding)

    issued = owner.issue(issue, now=NOW)
    validated = owner.validate_for_forwarding(
        issued.confirmation_id,
        binding,
        issue.owner,
        now=NOW,
    )

    assert validated.confirmation_id == issued.confirmation_id


@pytest.mark.parametrize(
    "owner_context",
    [
        _owner_context(session_id="session-other"),
        _owner_context(correlation_id="correlation-other"),
        _owner_context(owner_generation=2),
    ],
)
def test_owner_context_mismatch_does_not_consume(
    tmp_path: Path,
    owner_context: P3ConfirmationOwnerContext,
) -> None:
    database = tmp_path / "confirmations.sqlite3"
    owner = BoundedP3ConfirmationOwner(database, enabled=True)
    issue = _issue()
    issued = owner.issue(issue, now=NOW)

    with pytest.raises(FormalTaskViolation) as raised:
        owner.validate_for_forwarding(
            issued.confirmation_id,
            issue.binding,
            owner_context,
            now=NOW,
        )

    assert raised.value.reason == "P3_CONFIRMATION_BINDING_MISMATCH"
    assert _confirmation_row(database, issued.confirmation_id)["consumed_at"] is None
    owner.validate_for_forwarding(
        issued.confirmation_id,
        issue.binding,
        issue.owner,
        now=NOW,
    )


@pytest.mark.parametrize(
    "binding",
    [
        _binding(command_id="command-other"),
        _binding(target_task_id="task-other"),
        _binding(intent_fingerprint="intent-other"),
        _binding(scope=_scope(project_id="project-other")),
    ],
)
def test_binding_mismatch_does_not_consume(
    tmp_path: Path,
    binding: P3ConfirmationBinding,
) -> None:
    database = tmp_path / "confirmations.sqlite3"
    owner = BoundedP3ConfirmationOwner(database, enabled=True)
    issue = _issue()
    issued = owner.issue(issue, now=NOW)

    with pytest.raises(FormalTaskViolation) as raised:
        owner.validate_for_forwarding(
            issued.confirmation_id,
            binding,
            issue.owner,
            now=NOW,
        )

    assert raised.value.reason == "P3_CONFIRMATION_BINDING_MISMATCH"
    assert _confirmation_row(database, issued.confirmation_id)["consumed_at"] is None


@pytest.mark.parametrize(
    ("expires_at", "reason"),
    [
        (NOW, "P3_CONFIRMATION_EXPIRED"),
        ("2026-08-07T10:02:00.000001Z", "P3_CONFIRMATION_TTL_EXCEEDED"),
    ],
)
def test_expiry_and_ttl_rejections_create_no_record(
    tmp_path: Path,
    expires_at: str,
    reason: str,
) -> None:
    database = tmp_path / "confirmations.sqlite3"
    owner = BoundedP3ConfirmationOwner(database, enabled=True)

    with pytest.raises(FormalTaskViolation) as raised:
        owner.issue(_issue(expires_at=expires_at), now=NOW)

    assert raised.value.reason == reason
    connection = sqlite3.connect(database)
    try:
        count = connection.execute("SELECT COUNT(*) FROM p3_confirmations").fetchone()[
            0
        ]
        assert count == 0
    finally:
        connection.close()


def test_expired_forwarding_does_not_consume(tmp_path: Path) -> None:
    database = tmp_path / "confirmations.sqlite3"
    owner = BoundedP3ConfirmationOwner(database, enabled=True)
    issue = _issue(expires_at="2026-08-07T10:00:01Z")
    issued = owner.issue(issue, now=NOW)

    with pytest.raises(FormalTaskViolation) as raised:
        owner.validate_for_forwarding(
            issued.confirmation_id,
            issue.binding,
            issue.owner,
            now="2026-08-07T10:00:01Z",
        )

    assert raised.value.reason == "P3_CONFIRMATION_EXPIRED"
    assert _confirmation_row(database, issued.confirmation_id)["consumed_at"] is None


@pytest.mark.parametrize(
    "binding",
    [
        _binding(operation="task.query", target_task_id="task-1"),
        _binding(operation="task.create", target_task_id="task-1"),
        _binding(operation="task.cancel", target_task_id=None),
        replace(_binding(), principal_id="user-other"),
    ],
)
def test_issuer_rejects_untrusted_or_invalid_mutation_bindings(
    tmp_path: Path,
    binding: P3ConfirmationBinding,
) -> None:
    owner = BoundedP3ConfirmationOwner(tmp_path / "confirmations.sqlite3", enabled=True)

    with pytest.raises(FormalTaskViolation):
        owner.issue(_issue(binding=binding), now=NOW)


def test_issuer_rejects_raw_mapping_input(tmp_path: Path) -> None:
    owner = BoundedP3ConfirmationOwner(tmp_path / "confirmations.sqlite3", enabled=True)

    with pytest.raises(FormalTaskViolation) as raised:
        owner.issue({"principal_id": "browser-claim"}, now=NOW)  # type: ignore[arg-type]

    assert raised.value.reason == "INVALID_P3_CONFIRMATION"


def test_concurrent_exact_consume_has_one_first_use_and_one_replay(
    tmp_path: Path,
) -> None:
    database = tmp_path / "confirmations.sqlite3"
    owner = BoundedP3ConfirmationOwner(database, enabled=True)
    issue = _issue()
    confirmation_id = owner.issue(issue, now=NOW).confirmation_id
    verifier = owner.raw_verifier
    assert verifier is not None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: verifier.verify_and_consume(
                    confirmation_id,
                    issue.binding,
                    now=NOW,
                ),
                range(2),
            )
        )

    assert sorted(result.replayed for result in results) == [False, True]


def test_existing_ledger_schema_is_migrated_without_breaking_old_records(
    tmp_path: Path,
) -> None:
    database = tmp_path / "legacy-confirmations.sqlite3"
    connection = sqlite3.connect(database)
    try:
        connection.execute(
            """
            CREATE TABLE p3_confirmations (
                confirmation_id TEXT PRIMARY KEY,
                principal_id TEXT NOT NULL,
                scope_key TEXT NOT NULL,
                operation TEXT NOT NULL,
                command_id TEXT NOT NULL,
                target_task_id TEXT,
                intent_fingerprint TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                issued_at TEXT NOT NULL,
                consumed_at TEXT
            )
            """
        )
        connection.commit()
    finally:
        connection.close()

    ledger = SqliteP3ConfirmationLedger(database)
    binding = _binding()
    legacy_id = ledger.issue(
        binding,
        expires_at=EXPIRY,
        now=NOW,
        confirmation_id="legacy-confirmation",
    )

    verified = ledger.verify_and_consume(legacy_id, binding, now=NOW)
    assert verified.replayed is False
    connection = sqlite3.connect(database)
    try:
        columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(p3_confirmations)"
            ).fetchall()
        }
    finally:
        connection.close()
    assert {
        "owner_session_id",
        "owner_correlation_id",
        "owner_generation",
    }.issubset(columns)


# --- D-069 frozen task.retry confirmation snapshot ---------------------------


def _context() -> ResolvedTaskContext:
    return ResolvedTaskContext(
        source="agent_server.session_project_registry",
        stable_id="project-1",
        uri="file:///tmp/project-1",
        revision_kind="version",
        revision_value="a77516a0",
        scope=_scope(),
        permissions=("task.execute", "project.write"),
        expires_at=EXPIRY,
        redaction_policy_id="live_voice.p3alpha.project.v1",
    )


def _retry_facts(**overrides: object) -> PreparedP3RetryFacts:
    base: dict[str, object] = {
        "previous_attempt_id": "attempt-1",
        "previous_outcome": "cancelled",
        "attempt_number": 2,
        "name": "Formal project task",
        "instruction": "Create one bounded project change.",
        "executor_id": "jiuwenswarm_code_agent.project_code",
        "required_capabilities": ("task.create",),
        "side_effect_class": "project_mutation",
        "attributes": (
            ("model_config_version", "catalog-v1"),
            ("model_identity", "default#0"),
        ),
    }
    base.update(overrides)
    return PreparedP3RetryFacts(**base)  # type: ignore[arg-type]


_UNSET = object()


def _retry_fingerprint(**overrides: object) -> str:
    facts = overrides.pop("retry", _UNSET)
    if facts is _UNSET:
        facts = _retry_facts()
    payload: dict[str, object] = {
        "operation": "task.retry",
        "command_id": "command-retry",
        "target_task_id": "task-1",
        "context": _context(),
        "retry": facts,
    }
    payload.update(overrides)
    return p3_confirmation_intent_fingerprint(**payload)  # type: ignore[arg-type]


def test_retry_confirmation_binds_every_frozen_predecessor_fact() -> None:
    baseline = _retry_fingerprint()
    assert len(baseline) == 64

    # Each frozen fact is load-bearing: changing any one changes the digest, so
    # a confirmation issued for one predecessor can never authorize another.
    for overrides in (
        {"previous_attempt_id": "attempt-other"},
        {"previous_outcome": "completed"},
        {"attempt_number": 3},
        {"name": "renamed"},
        {"instruction": "replaced"},
        {"executor_id": "legacy.demo_substitute"},
        {"required_capabilities": ("task.retry",)},
        {"side_effect_class": "read_only"},
        {"attributes": (("model_identity", "other#1"),)},
    ):
        assert _retry_fingerprint(retry=_retry_facts(**overrides)) != baseline, (
            overrides
        )

    # The re-resolved clean context and the command/target identity are equally
    # bound, so an external checkpoint invalidates the previous confirmation.
    assert (
        _retry_fingerprint(context=replace(_context(), revision_value="b88627b1"))
        != baseline
    )
    assert _retry_fingerprint(command_id="command-other") != baseline
    assert _retry_fingerprint(target_task_id="task-other") != baseline
    # Stability: the same facts always produce the same digest.
    assert _retry_fingerprint() == baseline


def test_retry_confirmation_requires_the_exact_frozen_snapshot() -> None:
    for overrides in (
        {"retry": None},
        {"context": None},
        {"target_task_id": None},
        {"name": "renamed"},
        {"instruction": "replaced"},
    ):
        with pytest.raises(FormalTaskViolation) as raised:
            _retry_fingerprint(**overrides)
        assert raised.value.reason == "INVALID_P3_CONFIRMATION", overrides

    # Frozen retry facts never leak into another operation's fingerprint.
    with pytest.raises(FormalTaskViolation) as leaked:
        p3_confirmation_intent_fingerprint(
            operation="task.cancel",
            command_id="command-cancel",
            target_task_id="task-1",
            context=None,
            retry=_retry_facts(),
        )
    assert leaked.value.reason == "INVALID_P3_CONFIRMATION"


def test_prepared_retry_facts_reject_ineligible_or_malformed_lineage() -> None:
    for overrides, expected in (
        ({"previous_outcome": "failed"}, "TASK_RETRY_OUTCOME_NOT_ELIGIBLE"),
        ({"previous_outcome": "interrupted"}, "TASK_RETRY_OUTCOME_NOT_ELIGIBLE"),
        ({"attempt_number": 1}, "TASK_RETRY_ATTEMPT_NUMBER_INVALID"),
        ({"attempt_number": 4}, "TASK_RETRY_ATTEMPT_NUMBER_INVALID"),
        ({"previous_attempt_id": " "}, "INVALID_P3_CONFIRMATION"),
        ({"executor_id": ""}, "INVALID_P3_CONFIRMATION"),
        ({"side_effect_class": ""}, "INVALID_P3_CONFIRMATION"),
        ({"required_capabilities": ("",)}, "INVALID_P3_CONFIRMATION"),
        ({"attributes": (("k",),)}, "INVALID_P3_CONFIRMATION"),
    ):
        with pytest.raises(FormalTaskViolation) as raised:
            _retry_facts(**overrides)
        assert raised.value.reason == expected, overrides


def test_retry_confirmation_owner_requires_an_exact_target_task() -> None:
    owner_context = P3ConfirmationOwnerContext(
        session_id="session-1",
        correlation_id="correlation-1",
        owner_generation=1,
    )
    BoundedP3ConfirmationOwner._validate_binding_owner(
        _binding(operation="task.retry", target_task_id="task-1"),
        owner_context,
    )

    with pytest.raises(FormalTaskViolation) as raised:
        BoundedP3ConfirmationOwner._validate_binding_owner(
            _binding(operation="task.retry", target_task_id=None),
            owner_context,
        )
    assert raised.value.reason == "INVALID_P3_CONFIRMATION"
    assert "task.retry" in str(raised.value)

    with pytest.raises(FormalTaskViolation) as unsupported:
        BoundedP3ConfirmationOwner._validate_binding_owner(
            _binding(operation="task.resume", target_task_id="task-1"),
            owner_context,
        )
    assert unsupported.value.reason == "INVALID_P3_CONFIRMATION_OPERATION"


@pytest.mark.parametrize(
    "operation",
    ["task.update", "task.reprioritize", "task.create_successor"],
)
def test_production_confirmation_owner_accepts_exact_targeted_mutations(
    operation: str,
) -> None:
    owner_context = _owner_context()

    BoundedP3ConfirmationOwner._validate_binding_owner(
        _binding(operation=operation, target_task_id="task-1"),
        owner_context,
    )

    with pytest.raises(FormalTaskViolation) as raised:
        BoundedP3ConfirmationOwner._validate_binding_owner(
            _binding(operation=operation, target_task_id=None),
            owner_context,
        )

    assert raised.value.reason == "INVALID_P3_CONFIRMATION"
    assert operation in str(raised.value)
