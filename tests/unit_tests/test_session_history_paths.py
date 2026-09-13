import time

import pytest

from jiuwenswarm.server.runtime.session import session_history


def test_read_history_paths_do_not_create_missing_session_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(session_history, "get_agent_sessions_dir", lambda: tmp_path)

    session_id = "sess_missing"
    session_dir = tmp_path / session_id

    read_path = session_history.get_read_history_path(session_id)

    assert read_path == session_dir / "history.jsonl"
    assert not session_dir.exists()
    assert not session_history.history_exists(session_id)
    assert session_history.load_history_records(session_id) == []
    assert not session_dir.exists()


def test_write_history_path_still_creates_session_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(session_history, "get_agent_sessions_dir", lambda: tmp_path)

    session_id = "sess_new"
    session_dir = tmp_path / session_id

    write_path = session_history.get_write_history_path(session_id)

    assert write_path == session_dir / "history.jsonl"
    assert session_dir.is_dir()


def test_formal_history_append_is_exact_and_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(session_history, "get_agent_sessions_dir", lambda: tmp_path)
    record = {
        "id": "live-voice:response-1:0:text:0",
        "role": "assistant",
        "request_id": "response-1",
        "channel_id": "web",
        "timestamp": 1.0,
        "content": "presented",
    }
    assert session_history.append_formal_history_record_idempotent(
        session_id="session-formal", record=record
    ) is True
    assert session_history.append_formal_history_record_idempotent(
        session_id="session-formal", record=record
    ) is False
    assert session_history.load_history_records("session-formal") == [record]

    with pytest.raises(ValueError, match="idempotency conflict"):
        session_history.append_formal_history_record_idempotent(
            session_id="session-formal",
            record={**record, "content": "rewritten"},
        )
    assert session_history.load_history_records("session-formal") == [record]


def test_unregistered_formal_looking_session_keeps_direct_chat_history(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(session_history, "get_agent_sessions_dir", lambda: tmp_path)
    session_id = "lv-formal-user-selected-direct-chat"
    session_history.append_history_record(
        session_id=session_id,
        request_id="direct-chat-request",
        channel_id="web",
        role="user",
        content="direct chat remains unchanged",
        timestamp=time.time(),
    )
    session_history._WRITE_QUEUE.join()

    records = session_history.load_history_records(session_id)
    assert [record["content"] for record in records] == [
        "direct chat remains unchanged"
    ]
