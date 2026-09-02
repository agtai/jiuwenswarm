# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Pre-command continuity only; these tests do not authorize Task effects."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import sqlite3

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import Assurance, ScopeRef
from jiuwenswarm.server.live_voice.formal_task_models import FormalTaskViolation
from jiuwenswarm.server.live_voice.unified_committed_input import (
    SqliteUnifiedCommittedInputJournal,
)


SCOPE = ScopeRef("subject-a", "project-a", "session-a", Assurance.AUTHENTICATED)


def retain(journal, **overrides):
    values = dict(
        scope=SCOPE,
        kind="proposal",
        source_id="presented-analysis-1",
        payload={
            "operation": "task.create",
            "arguments": {"goal": "Read the source data."},
        },
        issued_at=100.0,
        expires_at=160.0,
        now=110.0,
    )
    values.update(overrides)
    return journal.retain_semantic_context(**values)


def consume(journal, record, **overrides):
    values = dict(
        scope=SCOPE,
        context_id=record.context_id,
        version=record.version,
        commit_sha256="a" * 64,
        now=120.0,
    )
    values.update(overrides)
    return journal.consume_semantic_context(**values)


def test_pending_reopen_replay_and_route_generation_independent_scope(tmp_path):
    path = tmp_path / "unified.sqlite"
    first = SqliteUnifiedCommittedInputJournal(path)
    record = retain(first)
    restarted = SqliteUnifiedCommittedInputJournal(path)
    assert retain(restarted) == record
    assert restarted.read_semantic_contexts(scope=SCOPE, now=120) == (record,)
    consumed = consume(restarted, record)
    assert consumed.consumed_by == "a" * 64
    assert consume(first, record, now=161) == consumed
    assert first.read_semantic_contexts(scope=SCOPE, now=120) == ()
    assert retain(first) == consumed
    with first._connect() as db:
        assert (
            db.execute("SELECT COUNT(*) FROM unified_committed_inputs").fetchone()[0]
            == 0
        )
        assert (
            db.execute("SELECT COUNT(*) FROM unified_foreground_effects").fetchone()[0]
            == 0
        )


@pytest.mark.parametrize(
    "changed",
    [
        {"subject_id": "another-subject"},
        {"project_id": "another-project"},
        {"session_id": "another-session"},
    ],
)
def test_pending_cannot_cross_authenticated_scope(tmp_path, changed):
    journal = SqliteUnifiedCommittedInputJournal(tmp_path / "unified.sqlite")
    record = retain(journal)
    scope = replace(SCOPE, **changed)
    assert journal.read_semantic_contexts(scope=scope, now=120) == ()
    with pytest.raises(FormalTaskViolation, match="exact pending context unavailable"):
        consume(journal, record, scope=scope)
    assert journal.read_semantic_contexts(scope=SCOPE, now=120) == (record,)


@pytest.mark.parametrize(
    "changed",
    [
        {"version": 2},
        {"now": 160},
        {"commit_sha256": "not-a-digest"},
    ],
)
def test_pending_wrong_version_expiry_and_binding_fail_closed(tmp_path, changed):
    journal = SqliteUnifiedCommittedInputJournal(tmp_path / "unified.sqlite")
    record = retain(journal)
    with pytest.raises(FormalTaskViolation):
        consume(journal, record, **changed)
    assert journal.read_semantic_contexts(scope=SCOPE, now=159) == (record,)
    assert journal.read_semantic_contexts(scope=SCOPE, now=160) == ()


def test_pending_concurrent_consumption_has_exactly_one_input_owner(tmp_path):
    path = tmp_path / "unified.sqlite"
    journal = SqliteUnifiedCommittedInputJournal(path)
    record = retain(journal)

    def claim(digest):
        try:
            return consume(
                SqliteUnifiedCommittedInputJournal(path), record, commit_sha256=digest
            )
        except FormalTaskViolation as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(claim, ["a" * 64, "b" * 64]))
    assert sum(not isinstance(r, Exception) for r in results) == 1
    loser = next(r for r in results if isinstance(r, FormalTaskViolation))
    assert loser.reason == "SEMANTIC_CONTEXT_STALE"
    winner = next(r for r in results if not isinstance(r, Exception))
    assert consume(journal, record, commit_sha256=winner.consumed_by) == winner


@pytest.mark.parametrize(
    "changed",
    [
        {"expires_at": 161},
        {"issued_at": 99},
        {"payload": {"changed": True}},
    ],
)
def test_repeated_source_cannot_change_goal_or_extend_expiry(tmp_path, changed):
    journal = SqliteUnifiedCommittedInputJournal(tmp_path / "unified.sqlite")
    original = retain(journal)
    with pytest.raises(FormalTaskViolation) as failure:
        retain(journal, **changed)
    assert failure.value.reason == "SEMANTIC_CONTEXT_SOURCE_CONFLICT"
    assert journal.read_semantic_contexts(scope=SCOPE, now=120) == (original,)


def test_pending_capacity_and_expired_cleanup_are_bounded(tmp_path):
    journal = SqliteUnifiedCommittedInputJournal(tmp_path / "unified.sqlite")
    for index in range(8):
        retain(journal, source_id=f"source-{index}")
    with pytest.raises(FormalTaskViolation) as failure:
        retain(journal, source_id="overflow")
    assert failure.value.reason == "SEMANTIC_CONTEXT_CAPACITY_EXCEEDED"
    newer = retain(journal, source_id="new", issued_at=161, expires_at=190, now=162)
    assert journal.read_semantic_contexts(scope=SCOPE, now=162) == (newer,)


def test_pending_corrupt_payload_does_not_become_a_proposal(tmp_path):
    path = tmp_path / "unified.sqlite"
    journal = SqliteUnifiedCommittedInputJournal(path)
    record = retain(journal)
    with sqlite3.connect(path) as db:
        db.execute(
            "UPDATE semantic_pending_contexts SET payload_json=?",
            ('{"tampered":true}',),
        )
    with pytest.raises(FormalTaskViolation) as failure:
        consume(journal, record)
    assert failure.value.reason == "SEMANTIC_CONTEXT_CORRUPT"
    with pytest.raises(FormalTaskViolation):
        journal.read_semantic_contexts(scope=SCOPE, now=120)


@pytest.mark.parametrize(
    "column,value",
    [
        ("expires_at", 999.0),
        ("issued_at", 99.0),
        ("version", 2),
        ("source_id", "different-source"),
        ("kind", "confirmation"),
        ("consumed_by", "b" * 64),
    ],
)
def test_pending_corrupt_authority_metadata_is_rejected(tmp_path, column, value):
    path = tmp_path / "unified.sqlite"
    journal = SqliteUnifiedCommittedInputJournal(path)
    record = retain(journal)
    with sqlite3.connect(path) as db:
        # Columns are fixed test cases, never caller-supplied SQL identifiers.
        db.execute(f"UPDATE semantic_pending_contexts SET {column}=?", (value,))
    with pytest.raises(FormalTaskViolation) as failure:
        consume(journal, record, version=2 if column == "version" else 1)
    assert failure.value.reason == "SEMANTIC_CONTEXT_CORRUPT"


def test_pending_corrupt_scope_cannot_be_inherited_by_other_scope(tmp_path):
    path = tmp_path / "unified.sqlite"
    journal = SqliteUnifiedCommittedInputJournal(path)
    retain(journal)
    foreign = replace(SCOPE, subject_id="foreign")
    with sqlite3.connect(path) as db:
        db.execute(
            "UPDATE semantic_pending_contexts SET scope_sha256=?",
            (journal._semantic_scope_key(foreign),),
        )
    with pytest.raises(FormalTaskViolation) as failure:
        journal.read_semantic_contexts(scope=foreign, now=120)
    assert failure.value.reason == "SEMANTIC_CONTEXT_CORRUPT"


def test_pending_not_before_and_clock_rollback(tmp_path):
    journal = SqliteUnifiedCommittedInputJournal(tmp_path / "unified.sqlite")
    record = retain(journal)
    assert journal.read_semantic_contexts(scope=SCOPE, now=99) == ()
    with pytest.raises(FormalTaskViolation):
        consume(journal, record, now=99)
    assert journal.read_semantic_contexts(scope=SCOPE, now=100) == (record,)
    consumed = consume(journal, record, now=100)
    assert consume(journal, record, now=99) == consumed
    with pytest.raises(FormalTaskViolation):
        consume(journal, record, now=99, commit_sha256="b" * 64)


@pytest.mark.parametrize("consumed", [False, True])
def test_expired_source_cannot_mint_a_new_proposal_after_reopen(tmp_path, consumed):
    path = tmp_path / "unified.sqlite"
    journal = SqliteUnifiedCommittedInputJournal(path)
    original = retain(journal)
    if consumed:
        consume(journal, original)
    retain(journal, source_id="later-source", issued_at=161, expires_at=190, now=162)
    restarted = SqliteUnifiedCommittedInputJournal(path)
    with pytest.raises(FormalTaskViolation) as failure:
        retain(restarted, issued_at=161, expires_at=190, now=162)
    assert failure.value.reason == "SEMANTIC_CONTEXT_SOURCE_CONFLICT"
    with pytest.raises(FormalTaskViolation):
        consume(restarted, original, commit_sha256="b" * 64, now=162)
    with sqlite3.connect(path) as db:
        assert (
            db.execute("SELECT COUNT(*) FROM semantic_pending_contexts").fetchone()[0]
            == 2
        )


def test_pending_anchor_capacity_fails_closed_instead_of_forgetting_sources(
    tmp_path, monkeypatch
):
    from jiuwenswarm.server.live_voice import unified_committed_input as module

    monkeypatch.setattr(module, "P3_CONFIRMATION_MAX_CAPACITY", 1)
    journal = SqliteUnifiedCommittedInputJournal(tmp_path / "unified.sqlite")
    retain(journal)
    with pytest.raises(FormalTaskViolation) as failure:
        retain(journal, source_id="different", issued_at=161, expires_at=190, now=162)
    assert failure.value.reason == "SEMANTIC_CONTEXT_CAPACITY_EXCEEDED"
