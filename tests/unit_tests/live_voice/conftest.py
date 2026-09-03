"""Live Voice unit/integration history never writes to a developer's sessions."""

import pytest


@pytest.fixture(autouse=True)
def isolated_formal_session_history(tmp_path, monkeypatch):
    from jiuwenswarm.server.runtime.session import session_history

    root = tmp_path / "formal-session-history"
    monkeypatch.setattr(session_history, "get_agent_sessions_dir", lambda: root)
