# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

import asyncio
import hashlib
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import ResponseRef
from jiuwenswarm.server.live_voice.formal_task_models import FormalTaskViolation
from jiuwenswarm.server.live_voice.semantic_continuity import SemanticContinuity
from jiuwenswarm.server.live_voice.task_semantics import TaskSemanticResolver
from jiuwenswarm.server.live_voice.unified_committed_input import (
    SqliteUnifiedCommittedInputJournal,
)
from jiuwenswarm.server.runtime.agent_adapter.formal_live_voice import (
    PresentedAgentAnalysis,
)
from tests.unit_tests.live_voice.test_task_semantics import (
    _commit,
    _context,
    _output,
    _Catalog,
    _Model,
)


def test_confirmation_clock_precision_does_not_reject_already_issued_context(tmp_path, monkeypatch):
    from jiuwenswarm.server.live_voice import unified_committed_input as module

    instant = datetime(2026, 9, 3, 12, 0, 0, 123456, tzinfo=UTC)
    issued = instant.timestamp()

    class Clock:
        @staticmethod
        def now(zone):
            assert zone is UTC
            return instant

    monkeypatch.setattr(module, "datetime", Clock, raising=False)
    monkeypatch.setattr(module.time, "time", lambda: issued - 0.000000238418579)
    journal = SqliteUnifiedCommittedInputJournal(tmp_path / "precision.db")
    args = dict(scope=_commit().scope, kind="confirmation", source_id="exact-origin",
                payload={"operation": "task.create"}, issued_at=issued, expires_at=issued+120)
    retained = journal.retain_semantic_context(**args)
    assert retained.issued_at == issued and retained.expires_at == issued+120
    for change in ({"issued_at": issued+0.000001}, {"expires_at": issued}, {"expires_at": issued+121}):
        with pytest.raises(FormalTaskViolation) as error:
            journal.retain_semantic_context(**{**args, **change, "source_id": "rejected"})
        assert error.value.reason == "SEMANTIC_CONTEXT_BOUND_EXCEEDED"


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["cascade", "native", "text"])
async def test_creation_origin_is_read_only_scope_bound_and_survives_reopen(tmp_path, source):
    provenance = {"cascade": {"provider": "formal-batch-speech", "kind": "committed_speech"},
        "native": {"source": "openai_realtime_native_delegate"}, "text": {"source": "explicit_text"}}[source]
    original = _commit()
    commit = type(original).from_dict({**original.to_dict(), "hypothesis_provenance": provenance})
    model = _Model(json.dumps(_output(commit)))
    decision = await TaskSemanticResolver(_Catalog(model)).resolve(commit, _context(commit))
    journal = SqliteUnifiedCommittedInputJournal(tmp_path / "origin.db")
    identity = {"voice_identity_sha256": "a" * 64, "fingerprint": b"f" * 32}
    journal.admit(request_id="origin", created_at="2026-09-03T00:00:00Z", **identity)
    journal.bind_semantic(**identity, semantic_binding=decision.frozen_record())
    reopened = SqliteUnifiedCommittedInputJournal(journal.database_path)
    args = {"scope": commit.scope, "turn_id": commit.turn_id, "commit_id": commit.commit_id}
    assert reopened.read_creation_origin(**args) == commit
    for scope in (replace(commit.scope, subject_id="foreign"), replace(commit.scope, project_id="foreign"), replace(commit.scope, session_id="foreign")):
        assert reopened.read_creation_origin(**{**args, "scope": scope}) is None
    with reopened._connect() as connection:
        row = dict(connection.execute("SELECT * FROM unified_committed_inputs").fetchone())
    assert row["status"] == "pending" and row["result_json"] is None
    assert len(model.calls) == 1
    changed = decision.frozen_record()
    changed["body"]["input"]["commit"]["text"] = "tampered without recomputing the frozen digest"
    with reopened._connect() as connection:
        connection.execute("UPDATE unified_committed_inputs SET semantic_binding_json=?", (json.dumps(changed),))
    with pytest.raises(FormalTaskViolation, match="creation origin record is invalid"):
        reopened.read_creation_origin(**args)
    assert len(model.calls) == 1


@pytest.mark.asyncio
async def test_creation_origin_duplicate_exact_record_is_not_guessed(tmp_path):
    commit = _commit()
    decision = await TaskSemanticResolver(_Catalog(_Model(json.dumps(_output(commit))))).resolve(commit, _context(commit))
    journal = SqliteUnifiedCommittedInputJournal(tmp_path / "duplicate-origin.db")
    for stem in ("a", "b"):
        identity = {"voice_identity_sha256": stem * 64, "fingerprint": stem.encode() * 32}
        journal.admit(request_id=stem, created_at="2026-09-03T00:00:00Z", **identity)
        journal.bind_semantic(**identity, semantic_binding=decision.frozen_record())
    with pytest.raises(FormalTaskViolation, match="creation origin is not unique"):
        journal.read_creation_origin(scope=commit.scope, turn_id=commit.turn_id, commit_id=commit.commit_id)


def analysis():
    commit = _commit(
        "Please analyze the project information before doing anything in the background."
    )
    return PresentedAgentAnalysis(
        commit,
        ResponseRef(commit.interaction_id, "response", 1),
        "I read the source materials and can prepare a laboratory equipment review in the background.",
        datetime.now(UTC).isoformat(),
    )


@pytest.mark.asyncio
async def test_history_retains_unanswered_committed_user_without_inventing_answer(tmp_path):
    state = SemanticContinuity(SqliteUnifiedCommittedInputJournal(tmp_path / "history.db"))
    original = _commit("Compare storage plans, including local disks.")
    history = await state.history(original.scope, committed=(original,))
    assert history == ({"role": "user", "text": original.text, "source_id": original.commit_id},)
    await state.retain_analysis(PresentedAgentAnalysis(
        original, ResponseRef(original.interaction_id, "response", 1),
        "A documented comparison.", datetime.now(UTC).isoformat(),
    ))
    history = await state.history(original.scope, committed=(original,))
    assert [item["role"] for item in history] == ["user", "assistant"]
    assert sum(item["source_id"] == original.commit_id for item in history) == 1
    with pytest.raises(FormalTaskViolation):
        await state.history(replace(original.scope, session_id="other"), committed=(original,))
    commits = tuple(replace(original, commit_id=f"unanswered-{i}",
                            committed_at=f"2026-09-03T12:{i:02d}:00Z") for i in range(40))
    bounded = await state.history(original.scope, committed=commits)
    assert len(bounded) == 32
    assert [entry["source_id"] for entry in bounded] == [f"unanswered-{i}" for i in range(8, 40)]
    assert all(entry["role"] == "user" for entry in bounded)


@pytest.mark.asyncio
async def test_proposal_lifetime_survives_playout_without_extending_confirmation(tmp_path, monkeypatch):
    from jiuwenswarm.server.live_voice import unified_committed_input as module

    source = analysis()
    issued = datetime.fromisoformat(source.presented_at).timestamp()
    current = [issued]

    class Clock:
        @staticmethod
        def now(zone):
            return datetime.fromtimestamp(current[0], zone)

    monkeypatch.setattr(module, "datetime", Clock)
    monkeypatch.setattr(module.time, "time", lambda: current[0])
    state = SemanticContinuity(SqliteUnifiedCommittedInputJournal(tmp_path / "lifetime.db"))
    record = await state.retain_analysis(source)
    assert record.expires_at == issued + 600
    current[0] += 180  # Realistic playout + extraction latency, not a product delay.
    model = _Model(json.dumps({**_output(source.commit), "route": "proposal"}))

    async def resolve(**kwargs):
        return await TaskSemanticResolver(_Catalog(model)).resolve(
            kwargs["commit"], _context(kwargs["commit"]), analysis=kwargs["analysis"]
        )

    await state.finish_analyses(source.commit.scope, resolve)
    proposal = state.journal.find_semantic_context(
        scope=source.commit.scope, kind="proposal", source_id=record.source_id
    )
    assert proposal.issued_at == issued and proposal.expires_at == issued + 600
    assert len(await state.pending(source.commit.scope)) == 1
    for kind in ("confirmation", "clarification"):
        with pytest.raises(FormalTaskViolation):
            state.journal.retain_semantic_context(
                scope=source.commit.scope, kind=kind, source_id=kind,
                payload={"operation": "task.create"}, issued_at=current[0],
                expires_at=current[0] + 121,
            )
    current[0] = issued + 600
    assert await state.pending(source.commit.scope) == ()
    reopened = SemanticContinuity(SqliteUnifiedCommittedInputJournal(state.journal.database_path))
    replay = await reopened.retain_analysis(source)
    assert replay.context_id == record.context_id and replay.expires_at == record.expires_at
    await reopened.finish_analyses(source.commit.scope, resolve)
    assert await reopened.pending(source.commit.scope) == () and len(model.calls) == 1
    with state.journal._connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM unified_foreground_effects").fetchone()[0] == 0


@pytest.mark.asyncio
async def test_presented_analysis_produces_one_recoverable_proposal_not_a_task(
    tmp_path,
):
    database = tmp_path / "continuity.sqlite3"
    state = SemanticContinuity(SqliteUnifiedCommittedInputJournal(database))
    source = analysis()
    record = await state.retain_analysis(source)
    output = {**_output(source.commit), "route": "proposal"}
    model = _Model(json.dumps(output))

    async def resolve(**kwargs):
        return await TaskSemanticResolver(_Catalog(model)).resolve(
            kwargs["commit"], _context(kwargs["commit"]), analysis=kwargs["analysis"]
        )

    await asyncio.gather(
        state.finish_analyses(source.commit.scope, resolve),
        state.finish_analyses(source.commit.scope, resolve),
    )
    assert len(model.calls) == 1
    reopened = SemanticContinuity(SqliteUnifiedCommittedInputJournal(database))
    replay = await reopened.retain_analysis(source)
    assert replay.context_id == record.context_id
    assert (
        replay.consumed_by
        == hashlib.sha256(source.commit.canonical_bytes()).hexdigest()
    )
    await reopened.finish_analyses(source.commit.scope, resolve)
    assert len(model.calls) == 1
    pending = await reopened.pending(source.commit.scope)
    assert len(pending) == 1 and pending[0]["kind"] == "proposal"
    assert pending[0]["arguments"] == output["arguments"]
    history = await reopened.history(source.commit.scope)
    assert [entry["text"] for entry in history] == [source.commit.text, source.text]
    with reopened.journal._connect() as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM unified_committed_inputs"
            ).fetchone()[0]
            == 0
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM unified_foreground_effects"
            ).fetchone()[0]
            == 0
        )
    assert (
        await reopened.pending(replace(source.commit.scope, project_id="foreign")) == ()
    )
    assert (
        await reopened.history(replace(source.commit.scope, project_id="foreign")) == ()
    )
    with pytest.raises(FormalTaskViolation, match="continuity"):
        await reopened.retain_analysis(
            replace(source, text="A different answer with the same source")
        )


@pytest.mark.asyncio
async def test_failed_model_retains_analysis_for_authorized_retry(tmp_path):
    state = SemanticContinuity(
        SqliteUnifiedCommittedInputJournal(tmp_path / "journal.sqlite3")
    )
    source = analysis()
    await state.retain_analysis(source)

    async def fail(**kwargs):
        raise TimeoutError("controlled provider fault")

    with pytest.raises(TimeoutError):
        await state.finish_analyses(source.commit.scope, fail)
    assert not state._locks
    records = state.journal.read_semantic_contexts(scope=source.commit.scope)
    assert (
        len(records) == 1
        and records[0].kind == "analysis"
        and records[0].consumed_by is None
    )
    assert await state.pending(source.commit.scope) == ()


def legacy_database(path):
    journal = SqliteUnifiedCommittedInputJournal(path)
    source = analysis()
    record = journal.retain_semantic_context(
        scope=source.commit.scope,
        kind="proposal",
        source_id="original",
        payload={"immutable": True},
        issued_at=100.0,
        expires_at=200.0,
        now=100.0,
    )
    with journal._connect() as connection:
        rows = connection.execute("SELECT * FROM semantic_pending_contexts").fetchall()
        schema = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name='semantic_pending_contexts'"
        ).fetchone()[0]
        connection.execute("DROP TABLE semantic_pending_contexts")
        connection.execute(schema.replace("'analysis', ", ""))
        connection.executemany(
            "INSERT INTO semantic_pending_contexts VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [tuple(row) for row in rows],
        )
    return source, record, [tuple(row) for row in rows]


def test_kind_migration_preserves_all_old_bytes_and_concurrent_initializer(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    source, record, rows = legacy_database(path)
    with ThreadPoolExecutor(max_workers=4) as pool:
        journals = list(
            pool.map(lambda _: SqliteUnifiedCommittedInputJournal(path), range(4))
        )
    for journal in journals:
        assert (
            journal.find_semantic_context(
                scope=source.commit.scope, kind="proposal", source_id="original"
            )
            == record
        )
        with journal._connect() as connection:
            assert [
                tuple(row)
                for row in connection.execute("SELECT * FROM semantic_pending_contexts")
            ] == rows
    journals[0].retain_semantic_context(
        scope=source.commit.scope,
        kind="analysis",
        source_id="new-source",
        payload={"data": True},
        issued_at=100.0,
        expires_at=200.0,
        now=100.0,
    )


def test_kind_migration_rolls_back_when_drop_is_denied(tmp_path):
    path = tmp_path / "rollback.sqlite3"
    _source, _record, rows = legacy_database(path)

    class FaultedJournal(SqliteUnifiedCommittedInputJournal):
        def _connect(self):
            connection = super()._connect()
            connection.set_authorizer(
                lambda action, first, *args: (
                    sqlite3.SQLITE_DENY
                    if action == sqlite3.SQLITE_DROP_TABLE
                    and first == "semantic_pending_contexts"
                    else sqlite3.SQLITE_OK
                )
            )
            return connection

    with pytest.raises(sqlite3.DatabaseError):
        FaultedJournal(path)
    with sqlite3.connect(path) as connection:
        assert (
            connection.execute("SELECT * FROM semantic_pending_contexts").fetchall()
            == rows
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM sqlite_master WHERE name='semantic_pending_contexts_v2'"
            ).fetchone()[0]
            == 0
        )
        schema = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name='semantic_pending_contexts'"
        ).fetchone()[0]
        assert "'analysis'" not in schema
