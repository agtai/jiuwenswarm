"""Transport observations, not physical/network-root-cause acceptance."""
import asyncio
import json
from types import SimpleNamespace

import pytest

from jiuwenswarm.server.live_voice import speech_socket_diagnostics as diag


class Transport:
    size = 0
    def get_write_buffer_size(self):
        return self.size
    def get_write_buffer_limits(self):
        return (8192, 32768)
    def get_extra_info(self, key):
        return ("127.0.0.1", 12345)


class FlowBase:
    def __init__(self):
        self.transport = Transport()
        self.paused = False
        self.gate = asyncio.Event()
        self.entered = asyncio.Event()
        self.sent = []
        self.failure = None

    def pause_writing(self):
        self.paused = True
    def resume_writing(self):
        self.paused = False
        self.gate.set()
    async def drain(self):
        self.entered.set()
        if self.paused:
            await self.gate.wait()
        if self.failure:
            raise self.failure
    async def send(self, message):
        self.sent.append(message)
        await self.drain()


class Socket(diag._ObservedFlowControl, FlowBase):
    pass


def attach(socket, capture="capture-a"):
    observer = diag.attach_socket_diagnostics(socket, "wss://example.invalid/realtime",
        media_session_id="media-a", capture_id=capture, generation=1)
    assert observer is not None
    return observer


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["complete", "cancelled", "failed"])
async def test_flow_wait_cancel_failure_wire_identity_and_timer_cleanup(monkeypatch, outcome):
    records = []
    monkeypatch.setattr(diag, "record_audio_diagnostic", lambda e, **f: records.append((e, f)))
    socket = Socket()
    observer = attach(socket)
    observer.begin(50, 52)
    timer = observer.timer
    socket.transport.size = 40000
    socket.pause_writing()
    send = asyncio.create_task(socket.send("PRIVATE_AUDIO_AND_KEY"))
    await asyncio.wait_for(socket.entered.wait(), 1)
    assert not send.done()
    # Heartbeat must execute while the send is suspended, not after it returns.
    await asyncio.sleep(0.12)
    assert observer.timer is not timer and not send.done()
    if outcome == "cancelled":
        send.cancel()
        with pytest.raises(asyncio.CancelledError):
            await send
    else:
        if outcome == "failed":
            socket.failure = OSError("PRIVATE_NETWORK_ERROR")
        socket.transport.size = 0
        socket.resume_writing()
        if outcome == "failed":
            with pytest.raises(OSError):
                await send
        else:
            await send
    last_timer = observer.timer
    result = observer.finish()
    assert last_timer.cancelled() and observer.timer is None and not observer.active
    assert observer.send_task is None
    assert result["write_buffer_peak_bytes"] == 40000
    assert result["drain_ms"] >= 100
    assert socket.sent == ["PRIVATE_AUDIO_AND_KEY"]  # No retry, duplicate or extra sends.
    assert next(f for e, f in records if e == "socket_drain_settled")["outcome"] == outcome
    assert all(f["capture_id"] == "capture-a" and f["generation"] == 1 for _, f in records)
    assert "PRIVATE" not in repr(records)


def test_event_loop_lag_and_heartbeat_no_catchup_or_stale_callbacks(monkeypatch):
    records, handles = [], []
    clock = [10.0]
    class Handle:
        cancelled = False
        def cancel(self):
            self.cancelled = True
    def schedule(deadline, callback):
        handle = Handle()
        handles.append((deadline, callback, handle))
        return handle
    loop = SimpleNamespace(time=lambda: clock[0], call_at=schedule)
    monkeypatch.setattr(diag.asyncio, "get_running_loop", lambda: loop)
    monkeypatch.setattr(diag, "record_audio_diagnostic", lambda e, **f: records.append((e, f)))
    observer = diag.SocketDiagnostics(SimpleNamespace(transport=Transport(), paused=False), capture_id="isolated")
    observer.begin(0, 1)
    clock[0] = 12.1
    handles[0][1]()
    assert len(handles) == 2 and handles[-1][0] == pytest.approx(12.2)
    pending = next(f for e, f in records if e == "socket_send_pending")
    assert pending["loop_lag_ms"] == pytest.approx(2000)
    assert pending["elapsed_ms"] == pytest.approx(2100)
    result = observer.finish()
    handles[-1][1]()  # Stale callback after owner ended cannot reschedule.
    assert len(handles) == 2 and handles[-1][2].cancelled
    assert result["loop_lag_peak_ms"] == pytest.approx(2000)
    assert result["drain_ms"] is None  # Missing flow instrumentation isn't zero wait.
    observer.begin(1, 2, budget_seconds=0.5)
    clock[0] += 1
    last_count = len(handles)
    handles[-1][1]()
    assert len(handles) == last_count and not observer.active and observer.timer is None
    assert any(e == "socket_observation_expired" for e, _ in records)
    peak_at_expiry = observer.loop_lag_peak_ms
    clock[0] += 90  # No heartbeat observed this interval; it isn't loop lag.
    expired = observer.finish()
    assert expired["loop_lag_peak_ms"] == peak_at_expiry
    assert expired["drain_ms"] is None and expired["observation_expired"] is True


@pytest.mark.asyncio
async def test_missing_transport_throwing_sink_and_concurrent_capture_isolation(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("PRIVATE_SINK")
    monkeypatch.setattr(diag, "record_audio_diagnostic", fail)
    first, second = Socket(), Socket()
    a, b = attach(first, "capture-a"), attach(second, "capture-b")
    a.begin(0, 1)
    b.begin(0, 1)
    first.pause_writing()
    send = asyncio.create_task(first.send("first"))
    await first.entered.wait()
    await second.send("second")
    b.finish()
    assert a.active and a.timer is not None and not send.done()
    first.resume_writing()
    await send
    a.finish()
    missing = attach(object())
    missing.begin(0, 1)
    assert missing.finish()["drain_ms"] is None
    assert first.sent == ["first"] and second.sent == ["second"]


@pytest.mark.asyncio
async def test_keepalive_drain_is_not_counted_as_speech_send(monkeypatch):
    records = []
    monkeypatch.setattr(diag, "record_audio_diagnostic", lambda e, **f: records.append((e, f)))
    socket = Socket()
    observer = attach(socket)
    observer.begin(0, 1)
    socket.pause_writing()
    ping = asyncio.create_task(socket.drain())
    await socket.entered.wait()
    await asyncio.sleep(0.12)
    socket.resume_writing()
    await ping
    assert observer.finish()["drain_ms"] == 0
    assert not any(e == "socket_drain_settled" for e, _ in records)


@pytest.mark.asyncio
async def test_real_loopback_factory_wire_and_observer(monkeypatch):
    from websockets.asyncio.server import serve
    import websockets.asyncio.client as client
    monkeypatch.setattr(client, "get_proxy", lambda uri: None)
    received = []
    records = []
    monkeypatch.setattr(diag, "record_audio_diagnostic", lambda e, **f: records.append((e, f)))
    async def echo(connection):
        async for message in connection:
            received.append(message)
            await connection.send(message)
    async with serve(echo, "127.0.0.1", 0) as server:
        url = f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}/"
        socket = await diag.diagnostic_socket_factory(url, {"X-Test": "PRIVATE_HEADER"}, 2)
        observer = diag.attach_socket_diagnostics(socket, url, capture_id="real-loopback", generation=9)
        try:
            assert isinstance(socket, diag._ObservedFlowControl)
            observer.begin(0, 1)
            try:
                await socket.send(json.dumps({"type": "input_audio_buffer.append", "audio": "PRIVATE_AUDIO"}))
            finally:
                result = observer.finish()
            assert await socket.recv() == received[0]
            assert len(received) == 1 and result["flow_observer"] is True
            attached = next(f for e, f in records if e == "socket_observer_attached")
            assert attached["peer_loopback"] is True
            assert attached["write_buffer_high_bytes"] > 0
            assert "PRIVATE" not in repr(records)
            assert observer.timer is None
            # Fault injection on the real websockets flow-control implementation;
            # not a claim that this loopback network is congested.
            observer.begin(1, 2)
            socket.pause_writing()
            pending = asyncio.create_task(socket.send("second"))
            try:
                await asyncio.sleep(0.12)
                assert not pending.done()
            finally:
                socket.resume_writing()
                await pending
                flow_result = observer.finish()
            assert await socket.recv() == "second" and len(received) == 2
            assert flow_result["drain_ms"] >= 100
            assert any(e == "socket_write_paused" for e, _ in records)
            assert any(e == "socket_write_resumed" for e, _ in records)
        finally:
            await socket.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("modern", [True, False])
async def test_factory_preserves_options_and_legacy_compatibility(monkeypatch, modern):
    import websockets
    captured = {}
    marker = object()
    async def legacy(url, **kwargs):
        captured.update(kwargs)
        return marker
    async def current(url, *, create_connection=None, additional_headers=None, **kwargs):
        captured.update(kwargs, create_connection=create_connection, additional_headers=additional_headers)
        return marker
    monkeypatch.setattr(websockets, "connect", current if modern else legacy)
    assert await diag.diagnostic_socket_factory("wss://example.invalid", {"Authorization": "private"}, 2) is marker
    assert captured["open_timeout"] == 2 and captured["compression"] is None
    assert "proxy" not in captured and "write_limit" not in captured
    if modern:
        assert issubclass(captured["create_connection"], diag._ObservedFlowControl)
    else:
        assert "create_connection" not in captured
