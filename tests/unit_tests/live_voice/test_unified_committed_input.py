# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

import hashlib
import sqlite3

import pytest

from jiuwenswarm.server.live_voice.formal_task_models import FormalTaskViolation
from jiuwenswarm.server.live_voice.unified_committed_input import (
    SqliteUnifiedCommittedInputJournal,
)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def fingerprint(value: str) -> bytes:
    return hashlib.sha256(value.encode("utf-8")).digest()


def test_journal_connections_enforce_request_binding_foreign_key(tmp_path) -> None:
    journal = SqliteUnifiedCommittedInputJournal(tmp_path / "unified.sqlite3")

    with journal._connect() as connection:
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO unified_request_bindings(
                    request_id, voice_identity_sha256, fingerprint
                ) VALUES(?, ?, ?)
                """,
                ("orphan-request", digest("missing-voice"), fingerprint("final")),
            )


def test_same_voice_identity_replays_original_result_across_request_ids(
    tmp_path,
) -> None:
    journal = SqliteUnifiedCommittedInputJournal(tmp_path / "unified.sqlite3")
    voice = digest("session/capture/generation")
    binding = fingerprint("authoritative final")
    assert journal.admit(
        request_id="request-1",
        voice_identity_sha256=voice,
        fingerprint=binding,
        created_at="2030-01-01T00:00:00Z",
    ).execute
    expected = {"ok": True, "result": {"status": "accepted"}}
    assert journal.complete(
        voice_identity_sha256=voice,
        fingerprint=binding,
        result=expected,
        completed_at="2030-01-01T00:00:01Z",
    ) == expected

    replay = journal.admit(
        request_id="request-2",
        voice_identity_sha256=voice,
        fingerprint=binding,
        created_at="2030-01-01T00:00:02Z",
    )
    assert not replay.execute
    assert replay.replay_result == expected


def test_same_voice_identity_keeps_first_semantic_target_binding(tmp_path) -> None:
    journal = SqliteUnifiedCommittedInputJournal(tmp_path / "unified.sqlite3")
    voice = digest("semantic target voice")
    binding = fingerprint("stop the current trip")
    original = {
        "route": "background.cancel",
        "task_id": "task-original",
        "current_task_sha256": digest("task-original"),
    }
    replacement = {
        "route": "background.cancel",
        "task_id": "task-new",
        "current_task_sha256": digest("task-new"),
    }

    first = journal.admit(
        request_id="request-original",
        voice_identity_sha256=voice,
        fingerprint=binding,
        created_at="2030-01-01T00:00:00Z",
        semantic_binding=original,
    )
    replay = journal.admit(
        request_id="request-replay",
        voice_identity_sha256=voice,
        fingerprint=binding,
        created_at="2030-01-01T00:00:01Z",
        semantic_binding=replacement,
    )

    assert first.execute
    assert first.semantic_binding == original
    assert not replay.execute
    assert replay.in_progress
    assert replay.semantic_binding == original


def test_request_id_and_voice_identity_cannot_change_content(tmp_path) -> None:
    journal = SqliteUnifiedCommittedInputJournal(tmp_path / "unified.sqlite3")
    voice = digest("voice-1")
    original = fingerprint("first final")
    journal.admit(
        request_id="request-stable",
        voice_identity_sha256=voice,
        fingerprint=original,
        created_at="2030-01-01T00:00:00Z",
    )

    with pytest.raises(FormalTaskViolation, match="different content") as request:
        journal.admit(
            request_id="request-stable",
            voice_identity_sha256=digest("voice-2"),
            fingerprint=fingerprint("second final"),
            created_at="2030-01-01T00:00:01Z",
        )
    assert request.value.reason == "UNIFIED_INPUT_ID_CONFLICT"

    with pytest.raises(FormalTaskViolation, match="different content") as identity:
        journal.admit(
            request_id="request-other",
            voice_identity_sha256=voice,
            fingerprint=fingerprint("changed final"),
            created_at="2030-01-01T00:00:01Z",
        )
    assert identity.value.reason == "UNIFIED_INPUT_ID_CONFLICT"


def test_new_request_alias_is_itself_immutable_after_voice_replay(tmp_path) -> None:
    journal = SqliteUnifiedCommittedInputJournal(tmp_path / "unified.sqlite3")
    voice = digest("voice-1")
    binding = fingerprint("final")
    journal.admit(
        request_id="request-first",
        voice_identity_sha256=voice,
        fingerprint=binding,
        created_at="2030-01-01T00:00:00Z",
    )
    journal.complete(
        voice_identity_sha256=voice,
        fingerprint=binding,
        result={"ok": True},
        completed_at="2030-01-01T00:00:01Z",
    )
    journal.admit(
        request_id="request-alias",
        voice_identity_sha256=voice,
        fingerprint=binding,
        created_at="2030-01-01T00:00:02Z",
    )

    with pytest.raises(FormalTaskViolation) as raised:
        journal.admit(
            request_id="request-alias",
            voice_identity_sha256=digest("voice-foreign"),
            fingerprint=fingerprint("foreign final"),
            created_at="2030-01-01T00:00:03Z",
        )
    assert raised.value.reason == "UNIFIED_INPUT_ID_CONFLICT"


def test_separate_owner_cannot_execute_same_pending_voice_identity(tmp_path) -> None:
    database = tmp_path / "unified.sqlite3"
    first_owner = SqliteUnifiedCommittedInputJournal(database)
    second_owner = SqliteUnifiedCommittedInputJournal(database)
    voice = digest("one pending voice")
    binding = fingerprint("authoritative final")

    first = first_owner.admit(
        request_id="request-first-owner",
        voice_identity_sha256=voice,
        fingerprint=binding,
        created_at="2030-01-01T00:00:00Z",
    )
    competing = second_owner.admit(
        request_id="request-second-owner",
        voice_identity_sha256=voice,
        fingerprint=binding,
        created_at="2030-01-01T00:00:01Z",
    )

    assert first.execute
    assert not competing.execute
    assert competing.in_progress
    expected = {"ok": True, "result": {"status": "accepted"}}
    first_owner.complete(
        voice_identity_sha256=voice,
        fingerprint=binding,
        result=expected,
        completed_at="2030-01-01T00:00:02Z",
    )
    assert second_owner.wait_for_completion(
        voice_identity_sha256=voice,
        fingerprint=binding,
        timeout_seconds=0.1,
    ) == expected


def test_same_owner_cannot_execute_same_pending_voice_identity_twice(tmp_path) -> None:
    journal = SqliteUnifiedCommittedInputJournal(tmp_path / "unified.sqlite3")
    voice = digest("one same-process pending voice")
    binding = fingerprint("authoritative final")

    first = journal.admit(
        request_id="request-first",
        voice_identity_sha256=voice,
        fingerprint=binding,
        created_at="2030-01-01T00:00:00Z",
    )
    competing = journal.admit(
        request_id="request-second",
        voice_identity_sha256=voice,
        fingerprint=binding,
        created_at="2030-01-01T00:00:01Z",
    )

    assert first.execute
    assert not competing.execute
    assert competing.in_progress


def test_expired_pending_execution_lease_can_be_recovered(tmp_path) -> None:
    database = tmp_path / "unified.sqlite3"
    crashed_owner = SqliteUnifiedCommittedInputJournal(database)
    recovery_owner = SqliteUnifiedCommittedInputJournal(database)
    voice = digest("crashed voice")
    binding = fingerprint("authoritative final")
    assert crashed_owner.admit(
        request_id="request-crashed-owner",
        voice_identity_sha256=voice,
        fingerprint=binding,
        created_at="2030-01-01T00:00:00Z",
    ).execute
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE unified_committed_inputs SET lease_expires_at=0 "
            "WHERE voice_identity_sha256=?",
            (voice,),
        )

    recovered = recovery_owner.admit(
        request_id="request-recovery-owner",
        voice_identity_sha256=voice,
        fingerprint=binding,
        created_at="2030-01-01T00:00:31Z",
    )

    assert recovered.execute
    with pytest.raises(FormalTaskViolation) as stale_completion:
        crashed_owner.complete(
            voice_identity_sha256=voice,
            fingerprint=binding,
            result={"ok": True},
            completed_at="2030-01-01T00:00:32Z",
        )
    assert stale_completion.value.reason == "UNIFIED_INPUT_EXECUTION_LEASE_LOST"


def test_stale_parent_owner_cannot_publish_foreground_effect_after_takeover(
    tmp_path,
) -> None:
    database = tmp_path / "unified.sqlite3"
    stale_owner = SqliteUnifiedCommittedInputJournal(database)
    recovery_owner = SqliteUnifiedCommittedInputJournal(database)
    voice = digest("stale foreground owner")
    binding = fingerprint("authoritative final")
    assert stale_owner.admit(
        request_id="request-stale-owner",
        voice_identity_sha256=voice,
        fingerprint=binding,
        created_at="2030-01-01T00:00:00Z",
    ).execute
    assert stale_owner.admit_foreground_effect(
        voice_identity_sha256=voice,
        fingerprint=binding,
        effect_kind="agent_submit",
    ).execute
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE unified_committed_inputs SET lease_expires_at=0 "
            "WHERE voice_identity_sha256=?",
            (voice,),
        )
    assert recovery_owner.admit(
        request_id="request-recovery-owner",
        voice_identity_sha256=voice,
        fingerprint=binding,
        created_at="2030-01-01T00:00:31Z",
    ).execute

    with pytest.raises(FormalTaskViolation) as stale_checkpoint:
        stale_owner.checkpoint_foreground_effect(
            voice_identity_sha256=voice,
            fingerprint=binding,
            effect_kind="agent_submit",
            result=None,
            recovery={"response_generation": 0, "round_id": "round-stale"},
        )
    assert stale_checkpoint.value.reason == "UNIFIED_FOREGROUND_EFFECT_MISSING"
    assert recovery_owner.admit_foreground_effect(
        voice_identity_sha256=voice,
        fingerprint=binding,
        effect_kind="agent_submit",
    ).execute
    recovery_owner.checkpoint_foreground_effect(
        voice_identity_sha256=voice,
        fingerprint=binding,
        effect_kind="agent_submit",
        result=None,
        recovery={"response_generation": 0, "round_id": "round-recovered"},
    )
    with pytest.raises(FormalTaskViolation) as stale_complete:
        stale_owner.complete_foreground_effect(
            voice_identity_sha256=voice,
            fingerprint=binding,
            effect_kind="agent_submit",
            result={"ok": True},
        )
    assert stale_complete.value.reason == "UNIFIED_FOREGROUND_EFFECT_MISSING"


def test_completed_foreground_effect_replays_across_process_owner(tmp_path) -> None:
    database = tmp_path / "unified.sqlite3"
    first_owner = SqliteUnifiedCommittedInputJournal(database)
    voice = digest("presented voice")
    binding = fingerprint("authoritative final")
    assert first_owner.admit(
        request_id="request-present",
        voice_identity_sha256=voice,
        fingerprint=binding,
        created_at="2030-01-01T00:00:00Z",
    ).execute
    assert first_owner.admit_foreground_effect(
        voice_identity_sha256=voice,
        fingerprint=binding,
        effect_kind="authoritative_presentation",
    ).execute
    expected = {
        "request_id": "unified-present-stable",
        "ok": True,
        "result": {"status": "authoritative_presentation_accepted"},
        "error": None,
    }
    recovery = {"response_generation": 7, "text": "已开始处理。"}
    first_owner.checkpoint_foreground_effect(
        voice_identity_sha256=voice,
        fingerprint=binding,
        effect_kind="authoritative_presentation",
        result=expected,
        recovery=recovery,
    )
    first_owner.complete_foreground_effect(
        voice_identity_sha256=voice,
        fingerprint=binding,
        effect_kind="authoritative_presentation",
        result=expected,
    )

    restarted_owner = SqliteUnifiedCommittedInputJournal(database)
    recovered = restarted_owner.read_foreground_effect(
        voice_identity_sha256=voice,
        fingerprint=binding,
    )

    assert recovered is not None
    assert not recovered.execute
    assert not recovered.result_unknown
    assert recovered.replay_result == expected
    assert recovered.recovery == recovery


def test_uncheckpointed_presentation_is_safely_rebuilt_after_process_loss(
    tmp_path,
) -> None:
    database = tmp_path / "unified.sqlite3"
    crashed_owner = SqliteUnifiedCommittedInputJournal(database)
    voice = digest("possibly presented voice")
    binding = fingerprint("authoritative final")
    assert crashed_owner.admit(
        request_id="request-crashed-presentation",
        voice_identity_sha256=voice,
        fingerprint=binding,
        created_at="2030-01-01T00:00:00Z",
    ).execute
    assert crashed_owner.admit_foreground_effect(
        voice_identity_sha256=voice,
        fingerprint=binding,
        effect_kind="authoritative_presentation",
    ).execute
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE unified_committed_inputs SET lease_expires_at=0 "
            "WHERE voice_identity_sha256=?",
            (voice,),
        )

    recovery_owner = SqliteUnifiedCommittedInputJournal(database)
    assert recovery_owner.admit(
        request_id="request-recovered-presentation",
        voice_identity_sha256=voice,
        fingerprint=binding,
        created_at="2030-01-01T00:00:31Z",
    ).execute
    recovered = recovery_owner.read_foreground_effect(
        voice_identity_sha256=voice,
        fingerprint=binding,
    )
    retried = recovery_owner.admit_foreground_effect(
        voice_identity_sha256=voice,
        fingerprint=binding,
        effect_kind="authoritative_presentation",
    )

    assert recovered is None
    assert retried.execute


def test_checkpointed_presentation_is_claimed_for_exact_recovery(tmp_path) -> None:
    database = tmp_path / "unified.sqlite3"
    crashed_owner = SqliteUnifiedCommittedInputJournal(database)
    voice = digest("checkpointed presentation")
    binding = fingerprint("authoritative final")
    assert crashed_owner.admit(
        request_id="request-checkpointed",
        voice_identity_sha256=voice,
        fingerprint=binding,
        created_at="2030-01-01T00:00:00Z",
    ).execute
    assert crashed_owner.admit_foreground_effect(
        voice_identity_sha256=voice,
        fingerprint=binding,
        effect_kind="authoritative_presentation",
    ).execute
    expected = {
        "request_id": "unified-present-checkpointed",
        "ok": True,
        "result": {"status": "authoritative_presentation_accepted"},
        "error": None,
    }
    recovery = {"response_generation": 4, "text": "已开始处理。"}
    crashed_owner.checkpoint_foreground_effect(
        voice_identity_sha256=voice,
        fingerprint=binding,
        effect_kind="authoritative_presentation",
        result=expected,
        recovery=recovery,
    )
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE unified_committed_inputs SET lease_expires_at=0 "
            "WHERE voice_identity_sha256=?",
            (voice,),
        )

    recovery_owner = SqliteUnifiedCommittedInputJournal(database)
    assert recovery_owner.admit(
        request_id="request-checkpointed-recovery",
        voice_identity_sha256=voice,
        fingerprint=binding,
        created_at="2030-01-01T00:00:31Z",
    ).execute
    recovered = recovery_owner.read_foreground_effect(
        voice_identity_sha256=voice,
        fingerprint=binding,
    )
    claimed = recovery_owner.claim_foreground_effect_recovery(
        voice_identity_sha256=voice,
        fingerprint=binding,
    )

    assert recovered is not None
    assert recovered.replay_result == expected
    assert recovered.recovery == recovery
    assert claimed.replay_result == expected
    assert claimed.recovery == recovery


def test_pre_dispatch_agent_checkpoint_is_safely_rebuilt_after_process_loss(
    tmp_path,
) -> None:
    database = tmp_path / "unified.sqlite3"
    crashed_owner = SqliteUnifiedCommittedInputJournal(database)
    voice = digest("checkpointed agent ambiguity")
    binding = fingerprint("authoritative dialogue final")
    assert crashed_owner.admit(
        request_id="request-agent-crashed",
        voice_identity_sha256=voice,
        fingerprint=binding,
        created_at="2030-01-01T00:00:00Z",
    ).execute
    assert crashed_owner.admit_foreground_effect(
        voice_identity_sha256=voice,
        fingerprint=binding,
        effect_kind="agent_submit",
    ).execute
    crashed_owner.checkpoint_foreground_effect(
        voice_identity_sha256=voice,
        fingerprint=binding,
        effect_kind="agent_submit",
        result=None,
        recovery={"response_generation": 0, "round_id": "round-stable"},
    )
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE unified_committed_inputs SET lease_expires_at=0 "
            "WHERE voice_identity_sha256=?",
            (voice,),
        )

    recovery_owner = SqliteUnifiedCommittedInputJournal(database)
    assert recovery_owner.admit(
        request_id="request-agent-recovery",
        voice_identity_sha256=voice,
        fingerprint=binding,
        created_at="2030-01-01T00:00:31Z",
    ).execute
    recovered = recovery_owner.read_foreground_effect(
        voice_identity_sha256=voice,
        fingerprint=binding,
    )
    fenced = recovery_owner.admit_foreground_effect(
        voice_identity_sha256=voice,
        fingerprint=binding,
        effect_kind="agent_submit",
    )

    assert recovered is None
    assert fenced.execute
    assert not fenced.result_unknown
    with sqlite3.connect(database) as connection:
        execution_owner, recovery_json = connection.execute(
            "SELECT execution_owner, recovery_json "
            "FROM unified_foreground_effects WHERE voice_identity_sha256=?",
            (voice,),
        ).fetchone()
    assert execution_owner == recovery_owner._execution_owner
    assert recovery_json is None


def test_agent_result_promotion_is_immutable_and_replayable(tmp_path) -> None:
    database = tmp_path / "unified.sqlite3"
    journal = SqliteUnifiedCommittedInputJournal(database)
    voice = digest("promoted agent result")
    binding = fingerprint("authoritative dialogue final")
    expected = {
        "request_id": "unified-agent-stable",
        "ok": True,
        "result": {"status": "round_accepted"},
        "error": None,
    }
    assert journal.admit(
        request_id="request-agent-promote",
        voice_identity_sha256=voice,
        fingerprint=binding,
        created_at="2030-01-01T00:00:00Z",
    ).execute
    assert journal.admit_foreground_effect(
        voice_identity_sha256=voice,
        fingerprint=binding,
        effect_kind="agent_submit",
    ).execute
    journal.checkpoint_foreground_effect(
        voice_identity_sha256=voice,
        fingerprint=binding,
        effect_kind="agent_submit",
        result=None,
        recovery={"response_generation": 0, "round_id": "round-stable"},
    )
    assert journal.checkpoint_foreground_effect_result(
        voice_identity_sha256=voice,
        fingerprint=binding,
        effect_kind="agent_submit",
        result=expected,
    ) == expected
    assert journal.checkpoint_foreground_effect_result(
        voice_identity_sha256=voice,
        fingerprint=binding,
        effect_kind="agent_submit",
        result=expected,
    ) == expected
    with pytest.raises(FormalTaskViolation) as conflict:
        journal.checkpoint_foreground_effect_result(
            voice_identity_sha256=voice,
            fingerprint=binding,
            effect_kind="agent_submit",
            result={"ok": False},
        )
    assert conflict.value.reason == "UNIFIED_FOREGROUND_EFFECT_CONFLICT"

    restarted = SqliteUnifiedCommittedInputJournal(database)
    recovered = restarted.read_foreground_effect(
        voice_identity_sha256=voice,
        fingerprint=binding,
    )
    assert recovered is not None
    assert recovered.replay_result == expected
