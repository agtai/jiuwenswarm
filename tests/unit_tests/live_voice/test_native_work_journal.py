# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import asyncio
import hashlib
import json
import sqlite3

import pytest
from jiuwenswarm.common.schema.live_voice_contract_v2 import canonical_json_bytes

from jiuwenswarm.server.live_voice.native_work_journal import SqliteNativeWorkJournal
from jiuwenswarm.server.live_voice.native_work_runtime import (
    NativeWorkRuntime,
    NativeWorkSnapshot,
    NativeWorkState,
    NativeWorkViolation,
)
from jiuwenswarm.server.live_voice.unified_committed_input import (
    SqliteUnifiedCommittedInputJournal,
)
from tests.unit_tests.live_voice.test_native_work_runtime import (
    admission,
    scope,
    terminal,
)


def journal(tmp_path, **options):
    unified = SqliteUnifiedCommittedInputJournal(tmp_path / "conversation.sqlite3")
    with sqlite3.connect(unified.database_path) as connection:
        connection.execute("CREATE TABLE protected_business_state(value TEXT NOT NULL)")
        connection.execute("INSERT INTO protected_business_state VALUES('unchanged')")
    return SqliteNativeWorkJournal(unified.database_path, **options)


def accepted(**changes):
    values = admission(lambda _: None)
    values.pop("runner")
    return replace(
        NativeWorkSnapshot(
            **values,
            work_id="native-work-1",
            revision=1,
            sequence=1,
            state=NativeWorkState.ACCEPTED,
            accepted_at="2026-09-06T10:00:00Z",
            updated_at="2026-09-06T10:00:00Z",
        ),
        **changes,
    )


def protected(journal):
    with sqlite3.connect(journal.database_path) as connection:
        return connection.execute(
            "SELECT value FROM protected_business_state"
        ).fetchall()


@pytest.mark.parametrize("fault", [None, "scope", "source", "fingerprint", "extra_origin_field", "pending", "not_create"])
def test_creation_receipt_recovery_requires_exact_completed_scoped_identity(tmp_path, fault):
    store = journal(tmp_path)
    unified = SqliteUnifiedCommittedInputJournal(store.database_path)
    identity = hashlib.sha256(b"typed-native-input").hexdigest()
    source = "native-business:" + identity
    binding = dict(voice_identity_sha256=identity, fingerprint=bytes.fromhex(identity))
    unified.admit(request_id=source,created_at="2026-09-06T10:00:00Z",**binding)
    origin = {"scope_sha256": hashlib.sha256(canonical_json_bytes(scope().to_dict())).hexdigest(),
        "source_identity": source, "commit_id":"accepted-commit"}
    if fault == "scope": origin["scope_sha256"] = "b" * 64
    if fault == "source": origin["source_identity"] = "native-business:" + "b" * 64
    if fault == "extra_origin_field": origin["guessed"] = True
    result = {"contract_version":"live-voice.native-business.v1", "status":"dispatched",
        "operation":"task.adjust" if fault == "not_create" else "task.create", "task_id":"actual-task", "native_origin":origin}
    if fault != "pending":
        unified.complete(**binding,result=result,completed_at="2026-09-06T10:00:01Z")
    if fault == "fingerprint":
        with sqlite3.connect(store.database_path) as connection:
            connection.execute("UPDATE unified_committed_inputs SET fingerprint=?",(bytes.fromhex("b"*64),))
    if fault in {"source", "fingerprint", "extra_origin_field"}:
        with pytest.raises(NativeWorkViolation, match="Creation receipt"):
            store.recover_task_origins(scope())
    else:
        store.recover_task_origins(scope())
    assert store.task_origins(scope()) == (("actual-task",) if fault is None else ())
    assert store.restore() == () and protected(store) == [("unchanged",)]


@pytest.mark.asyncio
async def test_real_work_callbacks_checkpoint_and_restore_exact_completed_result_in_same_database(
    tmp_path,
):
    store = journal(tmp_path)
    calls = []

    async def runner(_control):
        calls.append("read")
        return "verified result including its tail"

    owner = NativeWorkRuntime(save=store.save)
    work = await owner.start(**admission(runner))
    done = await terminal(owner, work)
    persisted = store.restore()
    assert persisted == (done,) and done.state is NativeWorkState.COMPLETED
    reconstructed = SqliteNativeWorkJournal(store.database_path)
    restored_owner = NativeWorkRuntime(
        save=reconstructed.save, restored=reconstructed.restore()
    )
    assert (await restored_owner.start(**admission(runner))) == done
    assert calls == ["read"]
    assert protected(store) == [("unchanged",)]
    with sqlite3.connect(store.database_path) as connection:
        tables = {
            r[0]
            for r in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    assert {
        "unified_committed_inputs",
        "native_work_checkpoint",
        "native_work_presentation",
        "native_work_suppression",
        "native_business_task_origin",
    } <= tables
    await restored_owner.close()
    await owner.close()


@pytest.mark.asyncio
async def test_restart_nonterminal_becomes_persisted_unknown_without_executing_tools(
    tmp_path,
):
    store = journal(tmp_path)
    initial = accepted()
    store.save(initial)
    running = replace(initial, sequence=2, state=NativeWorkState.RUNNING)
    store.save(running)
    assert store.restore() == (running,)
    owner = NativeWorkRuntime(save=store.save, restored=store.restore())
    unknown = owner.query(scope=scope(), work_id=initial.work_id)
    assert unknown.state is NativeWorkState.UNKNOWN and unknown.sequence == 3
    assert unknown.reason == "PROCESS_OWNERSHIP_LOST" and store.restore() == (unknown,)
    calls = []

    async def forbidden(_control):
        calls.append("forbidden")
        return "never"

    assert (await owner.start(**admission(forbidden))).state is NativeWorkState.UNKNOWN
    assert calls == [] and protected(store) == [("unchanged",)]
    await owner.close()


def test_checkpoint_exact_replay_sequence_identity_and_request_fences_have_zero_store_effects(
    tmp_path,
):
    store = journal(tmp_path)
    initial = accepted()
    store.save(initial)
    store.save(initial)
    candidates = [
        replace(initial, sequence=3, state=NativeWorkState.RUNNING),
        replace(initial, state=NativeWorkState.RUNNING),
        replace(initial, sequence=2, instruction="changed specification"),
        replace(initial, sequence=2, model_identity="other#0"),
        replace(initial, work_id="another-work"),
        replace(initial, revision=3, supersedes_revision=2, request_id="revision-3"),
    ]
    for candidate in candidates:
        with pytest.raises(NativeWorkViolation):
            store.save(candidate)
        assert store.restore() == (initial,)
        assert protected(store) == [("unchanged",)]
    finished = replace(
        initial, sequence=2, state=NativeWorkState.CANCELLED, execution_settled=True
    )
    store.save(finished)
    with pytest.raises(NativeWorkViolation) as stale:
        store.save(
            replace(
                finished,
                sequence=3,
                state=NativeWorkState.RUNNING,
                execution_settled=False,
            )
        )
    assert stale.value.reason == "NATIVE_WORK_CHECKPOINT_STATE_CONFLICT"
    assert store.restore() == (finished,)


def test_revisions_and_foreign_scopes_remain_independent(tmp_path):
    store = journal(tmp_path)
    first = accepted()
    store.save(first)
    revised = replace(
        first,
        revision=2,
        supersedes_revision=1,
        request_id="revision-2",
        instruction="revised specification",
    )
    store.save(revised)
    store.save(replace(first, sequence=2, state=NativeWorkState.SUPERSEDED))
    foreign = accepted(scope=scope(session_id="other-session"))
    store.save(foreign)
    restored = store.restore()
    assert len(restored) == 3
    assert {item.instruction for item in restored if item.scope == first.scope} == {
        "hello",
        "revised specification",
    }
    assert tuple(item for item in restored if item.scope == foreign.scope) == (foreign,)
    assert protected(store) == [("unchanged",)]


def test_concurrent_checkpoint_compare_and_swap_and_ack_are_exact(tmp_path):
    store = journal(tmp_path)
    initial = accepted()
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert list(pool.map(store.save, [initial] * 4)) == [None] * 4
    one = replace(initial, sequence=2, state=NativeWorkState.RUNNING)
    two = replace(initial, sequence=2, state=NativeWorkState.CANCELLING)

    def write(snapshot):
        try:
            store.save(snapshot)
            return "saved"
        except NativeWorkViolation:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(write, [one, two])) == ["conflict", "saved"]
        assert sorted(
            pool.map(lambda _: store.mark_presented("event-1", scope()), range(2))
        ) == [False, True]
    assert store.restore()[0] in (one, two)
    assert store.presented("event-1", scope())
    assert protected(store) == [("unchanged",)]


def test_presentation_requires_explicit_ack_and_survives_reopen_without_cross_scope_replay(
    tmp_path,
):
    store = journal(tmp_path)
    initial = accepted()
    store.save(initial)
    assert not store.presented("work-finished", scope())
    assert store.mark_presented("work-finished", scope()) is True
    assert store.mark_presented("work-finished", scope()) is False
    other = scope(session_id="other-session")
    assert not store.presented("work-finished", other)
    reopened = SqliteNativeWorkJournal(store.database_path)
    assert reopened.presented("work-finished", scope())
    assert not reopened.presented("unheard", scope())
    assert not reopened.presented("work-finished", other)
    with pytest.raises(NativeWorkViolation):
        reopened.mark_presented("", scope())
    assert store.restore() == (initial,) and protected(store) == [("unchanged",)]


def test_capacity_has_no_eviction_or_new_effects_and_replay_still_works(tmp_path):
    store = journal(tmp_path, max_records=1, max_presentations=1)
    initial = accepted()
    store.save(initial)
    with pytest.raises(NativeWorkViolation) as full:
        store.save(accepted(work_id="work-2", request_id="request-2"))
    assert full.value.reason == "NATIVE_WORK_JOURNAL_FULL"
    store.save(initial)
    assert store.mark_presented("event-1", scope())
    with pytest.raises(NativeWorkViolation) as full:
        store.mark_presented("event-2", scope())
    assert full.value.reason == "NATIVE_WORK_PRESENTATION_LEDGER_FULL"
    assert store.mark_presented("event-1", scope()) is False
    assert not store.presented("event-2", scope())
    assert store.restore() == (initial,) and protected(store) == [("unchanged",)]


@pytest.mark.parametrize("damage", ["payload", "schema", "trigger", "ack"])
def test_corrupt_or_changed_owned_journal_fails_closed_without_business_effects(
    tmp_path, damage
):
    store = journal(tmp_path)
    initial = accepted()
    store.save(initial)
    store.mark_presented("event-1", scope())
    with sqlite3.connect(store.database_path) as connection:
        if damage == "payload":
            changed = initial.to_dict()
            changed["instruction"] = "tampered"
            connection.execute(
                "UPDATE native_work_checkpoint SET snapshot_json=?",
                (json.dumps(changed),),
            )
        elif damage == "schema":
            connection.execute(
                "ALTER TABLE native_work_checkpoint ADD COLUMN unsupported TEXT"
            )
        elif damage == "trigger":
            connection.execute(
                "CREATE TRIGGER forbidden_trigger AFTER UPDATE ON native_work_checkpoint BEGIN UPDATE protected_business_state SET value='forbidden'; END"
            )
        else:
            connection.execute(
                "UPDATE native_work_presentation SET presented_at='invalid'"
            )
    with pytest.raises(NativeWorkViolation):
        if damage == "ack":
            store.presented("event-1", scope())
        else:
            store.save(replace(initial, sequence=2, state=NativeWorkState.RUNNING))
    assert protected(store) == [("unchanged",)]


def test_missing_existing_input_database_is_not_silently_created(tmp_path):
    missing = tmp_path / "must-not-be-created.sqlite3"
    with pytest.raises(NativeWorkViolation):
        SqliteNativeWorkJournal(missing)
    assert not missing.exists()


def test_unrelated_sqlite_database_is_rejected_without_creating_owned_tables(tmp_path):
    path = tmp_path / "unrelated.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE protected_business_state(value TEXT)")
    with pytest.raises(NativeWorkViolation) as rejected:
        SqliteNativeWorkJournal(path)
    assert rejected.value.reason == "NATIVE_WORK_INPUT_JOURNAL_REQUIRED"
    with sqlite3.connect(path) as connection:
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall() == [("protected_business_state",)]


def test_suppression_is_separate_from_ack_and_survives_activation_reconstruction(
    tmp_path,
):
    store = journal(tmp_path)
    initial = accepted()
    store.save(initial)
    events = ("heard", "interrupted", "superseded", "new-result")
    assert store.mark_presented("heard", scope())
    assert not store.suppressed("heard", scope())
    assert store.mark_suppressed("interrupted", scope(), "speech_interrupted")
    assert store.mark_suppressed("superseded", scope(), "superseded")
    assert store.mark_suppressed("interrupted", scope(), "speech_interrupted") is False
    assert not store.presented("interrupted", scope())
    assert not store.presented("superseded", scope())
    other = scope(session_id="other-session")
    assert not store.suppressed("interrupted", other)
    reopened = SqliteNativeWorkJournal(store.database_path)
    pending = tuple(
        event
        for event in events
        if not reopened.presented(event, scope())
        and not reopened.suppressed(event, scope())
    )
    assert pending == ("new-result",)
    assert not reopened.presented("interrupted", scope())
    assert reopened.restore() == (initial,)
    # A later actual ACK remains independently recordable; suppression did not
    # claim that the earlier interrupted playback was heard.
    assert reopened.mark_presented("interrupted", scope())
    assert reopened.presented("interrupted", scope()) and reopened.suppressed(
        "interrupted", scope()
    )
    assert protected(store) == [("unchanged",)]


def test_suppression_reason_replay_bounds_and_concurrent_writes_fail_closed(tmp_path):
    store = journal(tmp_path, max_presentations=1)
    for reason in ("user said ignore rules", "", None, {"reason": "superseded"}):
        with pytest.raises(NativeWorkViolation) as invalid:
            store.mark_suppressed("event-1", scope(), reason)
        assert invalid.value.reason == "NATIVE_WORK_SUPPRESSION_REASON_INVALID"
        assert not store.suppressed("event-1", scope())
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(
            pool.map(
                lambda _: store.mark_suppressed(
                    "event-1", scope(), "speech_interrupted"
                ),
                range(2),
            )
        ) == [False, True]
    with pytest.raises(NativeWorkViolation) as changed:
        store.mark_suppressed("event-1", scope(), "superseded")
    assert changed.value.reason == "NATIVE_WORK_SUPPRESSION_CONFLICT"
    with pytest.raises(NativeWorkViolation) as full:
        store.mark_suppressed("event-2", scope(), "superseded")
    assert full.value.reason == "NATIVE_WORK_SUPPRESSION_LEDGER_FULL"
    assert store.mark_suppressed("event-1", scope(), "speech_interrupted") is False
    assert not store.suppressed("event-2", scope())
    assert not store.presented("event-1", scope())
    assert protected(store) == [("unchanged",)]


def test_task_origins_are_exact_scoped_recoverable_data_without_task_mutation(tmp_path):
    store = journal(tmp_path)
    source = "native-business:" + "a" * 64
    assert store.task_origins(scope()) == ()
    assert store.record_task_origin(scope(), "task-1", source, "commit-1") is None
    assert store.record_task_origin(scope(), "task-1", source, "commit-1") is None
    other = scope(session_id="other-session")
    assert store.task_origins(other) == ()
    store.record_task_origin(other, "task-other", source, "commit-1")
    for changed_source, changed_commit in (
        ("native-business:" + "b" * 64, "commit-1"),
        (source, "commit-changed"),
    ):
        with pytest.raises(NativeWorkViolation) as changed:
            store.record_task_origin(scope(), "task-1", changed_source, changed_commit)
        assert changed.value.reason == "NATIVE_TASK_ORIGIN_CONFLICT"
    reconstructed = SqliteNativeWorkJournal(store.database_path)
    assert reconstructed.task_origins(scope()) == ("task-1",)
    assert reconstructed.task_origins(other) == ("task-other",)
    assert not reconstructed.presented("task-1", scope())
    assert reconstructed.restore() == () and protected(store) == [("unchanged",)]


def test_task_origin_validation_capacity_and_concurrent_replay_are_closed(tmp_path):
    store = journal(tmp_path, max_task_origins=1)
    source = "native-business:" + "a" * 64
    for values in (
        ("", source, "commit"),
        ("x" * 257, source, "commit"),
        ("task", source, ""),
        ("task", "committed_turn:abc", "commit"),
        ("task", "native-business:" + "A" * 64, "commit"),
        ("task", source + "0", "commit"),
    ):
        with pytest.raises(NativeWorkViolation) as invalid:
            store.record_task_origin(scope(), *values)
        assert invalid.value.reason == "NATIVE_TASK_ORIGIN_INVALID"
        assert store.task_origins(scope()) == ()
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(
            pool.map(
                lambda _: store.record_task_origin(scope(), "task-1", source, "commit"),
                range(2),
            )
        ) == [None, None]
    with pytest.raises(NativeWorkViolation) as full:
        store.record_task_origin(scope(), "task-2", source, "commit")
    assert full.value.reason == "NATIVE_TASK_ORIGIN_LEDGER_FULL"
    store.record_task_origin(scope(), "task-1", source, "commit")
    assert store.task_origins(scope()) == ("task-1",)
    assert protected(store) == [("unchanged",)]


@pytest.mark.parametrize("kind", ["suppression", "task_origin"])
def test_corrupt_recovery_facts_never_claim_ack_or_task_state(tmp_path, kind):
    store = journal(tmp_path)
    store.mark_suppressed("event", scope(), "speech_interrupted")
    store.record_task_origin(scope(), "task", "native-business:" + "a" * 64, "commit")
    with sqlite3.connect(store.database_path) as connection:
        if kind == "suppression":
            connection.execute("UPDATE native_work_suppression SET reason='superseded'")
        else:
            connection.execute(
                "UPDATE native_business_task_origin SET commit_id='changed'"
            )
    with pytest.raises(NativeWorkViolation) as corrupt:
        if kind == "suppression":
            store.suppressed("event", scope())
        else:
            store.task_origins(scope())
    assert corrupt.value.reason == (
        "NATIVE_WORK_SUPPRESSION_CORRUPT"
        if kind == "suppression"
        else "NATIVE_TASK_ORIGIN_CORRUPT"
    )
    assert not store.presented("event", scope())
    assert store.restore() == () and protected(store) == [("unchanged",)]


def test_native_recovery_facts_leave_actual_unified_admission_and_result_unchanged(
    tmp_path,
):
    store = journal(tmp_path)
    unified = SqliteUnifiedCommittedInputJournal(store.database_path)
    identity = hashlib.sha256(b"native-business-proposal").hexdigest()
    fingerprint = hashlib.sha256(b"accepted-input-binding").digest()
    binding = dict(voice_identity_sha256=identity, fingerprint=fingerprint)
    assert unified.admit(
        request_id="request", created_at="2026-09-06T10:00:00Z", **binding
    ).execute
    expected = {"ok": True, "result": {"task_id": "actual-task"}}
    assert (
        unified.complete(
            **binding, result=expected, completed_at="2026-09-06T10:00:01Z"
        )
        == expected
    )
    with unified._connect() as connection:
        before = {
            name: connection.execute(f"SELECT * FROM {name}").fetchall()
            for name in (
                "unified_committed_inputs",
                "unified_request_bindings",
                "unified_foreground_effects",
            )
        }
    store.save(accepted())
    store.record_task_origin(
        scope(), "actual-task", "native-business:" + identity, "commit"
    )
    store.mark_suppressed("event", scope(), "speech_interrupted")
    store.mark_presented("actually-heard", scope())
    with unified._connect() as connection:
        after = {
            name: connection.execute(f"SELECT * FROM {name}").fetchall()
            for name in before
        }
    assert after == before
    assert (
        unified.wait_for_completion(request_id="request", timeout_seconds=0, **binding)
        == expected
    )
    assert protected(store) == [("unchanged",)]


@pytest.mark.asyncio
async def test_real_update_and_cancel_checkpoint_exact_revisions_before_restart(
    tmp_path,
):
    store = journal(tmp_path)
    first_started = asyncio.Event()
    second_started = asyncio.Event()
    first_cleaned = asyncio.Event()
    effects = []

    async def first_runner(control):
        effects.append("first-read")
        first_started.set()
        await control.cancelled.wait()
        first_cleaned.set()
        return "retired result"

    async def second_runner(control):
        assert first_cleaned.is_set()
        effects.append("second-read")
        second_started.set()
        await control.cancelled.wait()
        return "cancelled result"

    owner = NativeWorkRuntime(save=store.save)
    initial = await owner.start(**admission(first_runner))
    await first_started.wait()
    arguments = admission(second_runner, request="revision-2", input_id="commit-2")
    arguments.pop("foreground")
    arguments["instruction"] = "complete revised specification"
    revision = await owner.update(work_id=initial.work_id, revision=1, **arguments)
    await second_started.wait()
    await owner.cancel(scope=scope(), work_id=initial.work_id, revision=2)
    done = await terminal(owner, revision)
    assert done.state is NativeWorkState.CANCELLED and done.result_text is None
    restored = store.restore()
    assert tuple(item.state for item in restored) == (
        NativeWorkState.SUPERSEDED,
        NativeWorkState.CANCELLED,
    )
    assert all(item.execution_settled and item.result_text is None for item in restored)
    assert restored[1].instruction == "complete revised specification"
    restarted = NativeWorkRuntime(save=store.save, restored=restored)
    assert (
        await restarted.update(work_id=initial.work_id, revision=1, **arguments) == done
    )
    assert effects == ["first-read", "second-read"]
    assert protected(store) == [("unchanged",)]
    await restarted.close()
    await owner.close()


@pytest.mark.asyncio
async def test_invalid_storage_prevents_work_admission_and_all_runner_effects(tmp_path):
    store = journal(tmp_path)
    with sqlite3.connect(store.database_path) as connection:
        connection.execute(
            "CREATE TRIGGER forbidden_trigger AFTER INSERT ON native_work_checkpoint BEGIN UPDATE protected_business_state SET value='forbidden'; END"
        )
    effects = []

    async def forbidden(_control):
        effects.append("forbidden")
        return "never"

    owner = NativeWorkRuntime(save=store.save)
    with pytest.raises(NativeWorkViolation):
        await owner.start(**admission(forbidden))
    assert owner.list(scope=scope()) == ()
    await asyncio.sleep(0)
    assert effects == [] and protected(store) == [("unchanged",)]
    await owner.close()
