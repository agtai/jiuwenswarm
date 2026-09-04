# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""The process-local tool gate and the facade methods that drive it."""

from __future__ import annotations

import pytest

from jiuwenswarm.server.runtime.agent_adapter import formal_tool_gate
from jiuwenswarm.server.runtime.agent_adapter.interface import JiuWenSwarm


class _Rail:
    def __init__(self) -> None:
        self.paused: list[str] = []
        self.resumed: list[str] = []
        self.aborted: list[str] = []

    def pause_tools(self, session_id: str = "") -> None:
        self.paused.append(session_id)

    def resume_tools(self, session_id: str = "") -> None:
        self.resumed.append(session_id)

    def abort(self, session_id: str = "") -> None:
        self.aborted.append(session_id)


class _SessionScopedRoot:
    """Mirrors the deep adapter: rails live on per-session children."""

    supports_formal_tool_gate = True
    _is_session_scoped_adapter = False

    def __init__(self) -> None:
        self._session_adapters: dict[str, object] = {}
        self._stream_event_rail = None

    @staticmethod
    def _session_adapter_key(session_id: str | None) -> str:
        return str(session_id or "").strip() or "default"

    def supports_formal_live_voice(self) -> bool:
        return True

    async def process_formal_live_voice_stream_impl(self, request, inputs):  # pragma: no cover
        yield None


class _Child:
    def __init__(self) -> None:
        self._stream_event_rail = _Rail()


def _facade(root) -> JiuWenSwarm:
    facade = JiuWenSwarm()
    facade._adapter = root  # type: ignore[assignment]
    return facade


@pytest.fixture(autouse=True)
def _clean_gate():
    for key in list(formal_tool_gate._entries):
        formal_tool_gate._entries.pop(key, None)
    yield
    for key in list(formal_tool_gate._entries):
        formal_tool_gate._entries.pop(key, None)


def test_pause_is_recorded_before_the_session_adapter_exists_and_applied_by_it() -> None:
    root = _SessionScopedRoot()
    facade = _facade(root)
    session = "lv-formal-spec-0001"
    facade.pause_formal_tools(session)
    assert formal_tool_gate.should_pause(session)
    # The session adapter starts later and consults the gate on its own rail.
    child = _Child()
    root._session_adapters[session] = child
    if formal_tool_gate.should_pause(session):
        child._stream_event_rail.pause_tools(session)
    assert child._stream_event_rail.paused == [session]
    facade.resume_formal_tools(session)
    assert not formal_tool_gate.should_pause(session)
    assert child._stream_event_rail.resumed == [session]
    assert formal_tool_gate.snapshot() == {"pending": 0}


def test_release_before_the_stream_starts_means_no_pause_at_all() -> None:
    root = _SessionScopedRoot()
    facade = _facade(root)
    session = "lv-formal-spec-0002"
    facade.pause_formal_tools(session)
    facade.resume_formal_tools(session)
    assert not formal_tool_gate.should_pause(session)
    child = _Child()
    root._session_adapters[session] = child
    assert child._stream_event_rail.paused == [] and child._stream_event_rail.resumed == []


def test_abort_forgets_the_pause_and_aborts_an_existing_rail() -> None:
    root = _SessionScopedRoot()
    facade = _facade(root)
    session = "lv-formal-spec-0003"
    facade.pause_formal_tools(session)
    child = _Child()
    root._session_adapters[session] = child
    facade.abort_formal_tools(session)
    assert not formal_tool_gate.should_pause(session)
    assert child._stream_event_rail.aborted == [session]
    assert formal_tool_gate.snapshot() == {"pending": 0}


def test_an_existing_rail_is_paused_immediately_and_the_gate_is_bounded() -> None:
    root = _SessionScopedRoot()
    facade = _facade(root)
    session = "lv-formal-spec-0004"
    child = _Child()
    root._session_adapters[session] = child
    facade.pause_formal_tools(session)
    assert child._stream_event_rail.paused == [session]
    for index in range(formal_tool_gate._MAX_ENTRIES + 5):
        formal_tool_gate.request_pause(f"lv-formal-spec-bound-{index}")
    assert len(formal_tool_gate._entries) == formal_tool_gate._MAX_ENTRIES
    with pytest.raises(RuntimeError):
        formal_tool_gate.request_pause("chat-session")


def test_support_requires_the_adapter_gate_marker() -> None:
    class NoGate(_SessionScopedRoot):
        supports_formal_tool_gate = False

    assert _facade(_SessionScopedRoot()).supports_speculative_dialogue()
    assert not _facade(NoGate()).supports_speculative_dialogue()
