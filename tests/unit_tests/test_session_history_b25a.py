from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from jiuwenswarm.server.runtime.session import session_history


def _formal_record(record_id: str, content: str) -> dict[str, object]:
    return {
        "id": record_id,
        "role": "assistant",
        "request_id": record_id,
        "channel_id": "web",
        "timestamp": 1.0,
        "content": content,
    }


def test_formal_append_does_not_rescan_jsonl_after_index_is_built(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(session_history, "get_agent_sessions_dir", lambda: tmp_path)
    original_build = session_history._build_formal_history_index
    build_calls = 0

    def counted_build(path):
        nonlocal build_calls
        build_calls += 1
        return original_build(path)

    monkeypatch.setattr(session_history, "_build_formal_history_index", counted_build)

    assert session_history.append_formal_history_record_idempotent(
        session_id="session-index", record=_formal_record("formal-1", "one")
    )
    assert session_history.append_formal_history_record_idempotent(
        session_id="session-index", record=_formal_record("formal-2", "two")
    )
    assert not session_history.append_formal_history_record_idempotent(
        session_id="session-index", record=_formal_record("formal-1", "one")
    )

    assert build_calls == 1


def test_formal_appends_for_different_sessions_do_not_share_a_file_lock(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(session_history, "get_agent_sessions_dir", lambda: tmp_path)
    original_append = session_history._append_record_jsonl
    first_entered = threading.Event()
    release_first = threading.Event()
    second_started = threading.Event()
    second_finished = threading.Event()

    def blocked_append(path, record):
        if path.parent.name == "session-a":
            first_entered.set()
            assert release_first.wait(timeout=5)
        original_append(path, record)

    monkeypatch.setattr(session_history, "_append_record_jsonl", blocked_append)

    def append_a():
        return session_history.append_formal_history_record_idempotent(
            session_id="session-a", record=_formal_record("formal-a", "a")
        )

    def append_b():
        second_started.set()
        try:
            return session_history.append_formal_history_record_idempotent(
                session_id="session-b", record=_formal_record("formal-b", "b")
            )
        finally:
            second_finished.set()

    with ThreadPoolExecutor(max_workers=2) as executor:
        future_a = executor.submit(append_a)
        assert first_entered.wait(timeout=5)
        future_b = executor.submit(append_b)
        assert second_started.wait(timeout=5)
        completed_without_session_a = second_finished.wait(timeout=2)
        release_first.set()
        assert future_a.result(timeout=5)
        assert future_b.result(timeout=5)

    assert completed_without_session_a


def test_formal_append_repairs_a_partial_jsonl_tail_before_appending(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(session_history, "get_agent_sessions_dir", lambda: tmp_path)
    session_dir = tmp_path / "session-partial"
    session_dir.mkdir()
    history_path = session_dir / "history.jsonl"
    first = _formal_record("formal-1", "one")
    history_path.write_bytes(
        (json.dumps(first, ensure_ascii=False) + "\n").encode("utf-8")
        + b'{"id":"incomplete"'
    )

    second = _formal_record("formal-2", "two")
    assert session_history.append_formal_history_record_idempotent(
        session_id="session-partial", record=second
    )

    assert session_history.load_history_records("session-partial") == [first, second]
    assert history_path.read_bytes().endswith(b"\n")


def test_formal_append_preserves_a_complete_final_record_missing_only_newline(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(session_history, "get_agent_sessions_dir", lambda: tmp_path)
    session_dir = tmp_path / "session-newline"
    session_dir.mkdir()
    history_path = session_dir / "history.jsonl"
    first = _formal_record("formal-1", "one")
    history_path.write_text(json.dumps(first, ensure_ascii=False), encoding="utf-8")

    second = _formal_record("formal-2", "two")
    assert session_history.append_formal_history_record_idempotent(
        session_id="session-newline", record=second
    )

    assert session_history.load_history_records("session-newline") == [first, second]
    assert history_path.read_bytes().endswith(b"\n")


def test_ordinary_append_updates_an_existing_formal_index_after_success(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(session_history, "get_agent_sessions_dir", lambda: tmp_path)
    builds = 0
    original_build = session_history._build_formal_history_index

    def counted_build(path):
        nonlocal builds
        builds += 1
        return original_build(path)

    monkeypatch.setattr(session_history, "_build_formal_history_index", counted_build)
    first = _formal_record("formal-1", "one")
    ordinary = _formal_record("ordinary-1", "ordinary")

    assert session_history.append_formal_history_record_idempotent(
        session_id="session-ordinary-index", record=first
    )
    session_history._write_item("session-ordinary-index", ordinary)
    assert not session_history.append_formal_history_record_idempotent(
        session_id="session-ordinary-index", record=ordinary
    )
    assert builds == 1


def test_ordinary_append_repairs_a_partial_tail_under_the_same_lock(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(session_history, "get_agent_sessions_dir", lambda: tmp_path)
    session_dir = tmp_path / "session-ordinary-tail"
    session_dir.mkdir()
    history_path = session_dir / "history.jsonl"
    first = _formal_record("formal-1", "one")
    history_path.write_bytes(
        (json.dumps(first, ensure_ascii=False) + "\n").encode("utf-8")
        + b'{"id":"incomplete"'
    )
    ordinary = _formal_record("ordinary-1", "ordinary")

    session_history._write_item("session-ordinary-tail", ordinary)

    assert session_history.load_history_records("session-ordinary-tail") == [
        first,
        ordinary,
    ]


def test_formal_and_ordinary_append_share_the_same_session_lock(tmp_path, monkeypatch):
    monkeypatch.setattr(session_history, "get_agent_sessions_dir", lambda: tmp_path)
    original_append = session_history._append_record_jsonl
    formal_entered = threading.Event()
    release_formal = threading.Event()
    ordinary_lock_attempted = threading.Event()
    ordinary_entered = threading.Event()

    class ObservedRLock:
        def __init__(self):
            self.delegate = threading.RLock()

        def __enter__(self):
            ordinary_lock_attempted.set()
            self.delegate.acquire()
            return self

        def __exit__(self, exc_type, exc, traceback):
            self.delegate.release()

    state = session_history._get_session_history_state("session-shared-lock")
    state.lock = ObservedRLock()

    def blocked_append(path, record):
        if record["id"] == "formal-1":
            formal_entered.set()
            assert release_formal.wait(timeout=5)
        else:
            ordinary_entered.set()
        original_append(path, record)

    monkeypatch.setattr(session_history, "_append_record_jsonl", blocked_append)

    with ThreadPoolExecutor(max_workers=2) as executor:
        formal = executor.submit(
            session_history.append_formal_history_record_idempotent,
            session_id="session-shared-lock",
            record=_formal_record("formal-1", "formal"),
        )
        assert formal_entered.wait(timeout=5)
        ordinary_lock_attempted.clear()
        ordinary = executor.submit(
            session_history._write_item,
            "session-shared-lock",
            _formal_record("ordinary-1", "ordinary"),
        )
        assert ordinary_lock_attempted.wait(timeout=5)
        ordinary_overlapped = ordinary_entered.is_set()
        release_formal.set()
        assert formal.result(timeout=5)
        ordinary.result(timeout=5)

    assert not ordinary_overlapped
    assert ordinary_entered.is_set()


def test_rewrite_invalidates_the_formal_index(tmp_path, monkeypatch):
    monkeypatch.setattr(session_history, "get_agent_sessions_dir", lambda: tmp_path)
    old = _formal_record("formal-1", "old")
    replacement = _formal_record("formal-1", "replacement")

    assert session_history.append_formal_history_record_idempotent(
        session_id="session-rewrite", record=old
    )
    session_history.write_history_records("session-rewrite", [replacement])

    assert not session_history.append_formal_history_record_idempotent(
        session_id="session-rewrite", record=replacement
    )


def test_conflicting_ordinary_duplicate_cannot_be_accepted_as_a_formal_replay(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(session_history, "get_agent_sessions_dir", lambda: tmp_path)
    original = _formal_record("shared-id", "original")
    conflict = _formal_record("shared-id", "conflict")
    assert session_history.append_formal_history_record_idempotent(
        session_id="session-conflict", record=original
    )
    session_history._write_item("session-conflict", conflict)

    with pytest.raises(ValueError, match="idempotency conflict"):
        session_history.append_formal_history_record_idempotent(
            session_id="session-conflict", record=original
        )
    with pytest.raises(ValueError, match="idempotency conflict"):
        session_history.append_formal_history_record_idempotent(
            session_id="session-conflict", record=conflict
        )


def test_truncate_invalidates_the_formal_index(tmp_path, monkeypatch):
    monkeypatch.setattr(session_history, "get_agent_sessions_dir", lambda: tmp_path)
    first = _formal_record("formal-1", "one")
    removed = _formal_record("formal-2", "two")

    assert session_history.append_formal_history_record_idempotent(
        session_id="session-truncate", record=first
    )
    assert session_history.append_formal_history_record_idempotent(
        session_id="session-truncate", record=removed
    )
    assert session_history.truncate_history_records(
        session_id="session-truncate", cut_index=1
    ) == {"remaining_records": 1, "removed_records": 1}

    assert session_history.append_formal_history_record_idempotent(
        session_id="session-truncate", record=removed
    )


def test_legacy_json_is_migrated_but_jsonl_is_the_only_new_write_target(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(session_history, "get_agent_sessions_dir", lambda: tmp_path)
    monkeypatch.setenv(session_history._LEGACY_HISTORY_ENV, "1")
    session_dir = tmp_path / "session-legacy"
    session_dir.mkdir()
    legacy = _formal_record("legacy-1", "legacy")
    (session_dir / "history.json").write_text(
        json.dumps([legacy], ensure_ascii=False), encoding="utf-8"
    )
    appended = _formal_record("formal-1", "formal")

    assert session_history.append_formal_history_record_idempotent(
        session_id="session-legacy", record=appended
    )

    assert (
        session_history.get_write_history_path("session-legacy").name == "history.jsonl"
    )
    assert (
        session_history.get_read_history_path("session-legacy").name == "history.jsonl"
    )
    assert session_history.load_history_records("session-legacy") == [legacy, appended]


def test_malformed_non_tail_jsonl_fails_closed_without_appending(tmp_path, monkeypatch):
    monkeypatch.setattr(session_history, "get_agent_sessions_dir", lambda: tmp_path)
    session_dir = tmp_path / "session-corrupt-middle"
    session_dir.mkdir()
    history_path = session_dir / "history.jsonl"
    original = (
        json.dumps(_formal_record("formal-1", "one"), ensure_ascii=False)
        + "\n{not-json}\n"
    ).encode("utf-8")
    history_path.write_bytes(original)

    with pytest.raises(ValueError, match="index line 2 is invalid"):
        session_history.append_formal_history_record_idempotent(
            session_id="session-corrupt-middle",
            record=_formal_record("formal-2", "two"),
        )

    assert history_path.read_bytes() == original


def test_failed_append_does_not_publish_the_digest_to_memory(tmp_path, monkeypatch):
    monkeypatch.setattr(session_history, "get_agent_sessions_dir", lambda: tmp_path)
    original_append = session_history._append_record_jsonl
    record = _formal_record("formal-1", "one")

    def fail_append(path, value):
        raise OSError("synthetic append failure")

    monkeypatch.setattr(session_history, "_append_record_jsonl", fail_append)
    with pytest.raises(OSError, match="synthetic append failure"):
        session_history.append_formal_history_record_idempotent(
            session_id="session-append-failure", record=record
        )

    monkeypatch.setattr(session_history, "_append_record_jsonl", original_append)
    assert session_history.append_formal_history_record_idempotent(
        session_id="session-append-failure", record=record
    )


def test_session_state_registry_has_bounded_strong_retention():
    active = session_history._get_session_history_state("bounded-active")
    active.lock.acquire()
    try:
        for index in range(session_history._SESSION_STATE_RECENT_LIMIT + 16):
            with session_history._session_history_lock(f"bounded-session-{index}"):
                pass

        # Eviction from the strong LRU must not create a second lock while a caller
        # still owns the exact state through the weak authoritative registry.
        assert session_history._get_session_history_state("bounded-active") is active
    finally:
        active.lock.release()

    for index in range(session_history._SESSION_STATE_RECENT_LIMIT + 16):
        with session_history._session_history_lock(f"bounded-final-{index}"):
            pass

    assert (
        len(session_history._SESSION_STATE_RECENT)
        <= session_history._SESSION_STATE_RECENT_LIMIT
    )
