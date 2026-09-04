"""Passive, content-free recognition send/flow-control observations.

No global monkey-patching, routing changes, extra sends or background tasks.
The one heartbeat timer exists only during an observed send and is cancelled
on every success/error/cancel path. Socket completion isn't Provider receipt.
"""
from __future__ import annotations

import asyncio
import ipaddress
import time
from contextlib import suppress

from jiuwenswarm.common.live_voice_audio_diagnostics import record_audio_diagnostic


class SocketDiagnostics:
    def __init__(self, socket, **identity):
        self.socket = socket
        self.identity = identity
        self.active = False
        self.timer = None
        self.pause_started = None
        self.frame_seq = None
        self.wire_seq = None
        self.loop_lag_peak_ms = 0.0
        self.drain_ms = 0.0
        self.buffer_peak_bytes = 0
        self.next_tick = 0.0
        self.next_report = 0.0
        self.send_started = 0.0

    def emit(self, event, **fields):
        with suppress(Exception):
            record_audio_diagnostic(event, **self.identity,
                frame_seq=self.frame_seq, wire_seq=self.wire_seq, **fields)

    def snapshot(self):
        result = {}
        with suppress(Exception):
            transport = self.socket.transport
            size = transport.get_write_buffer_size()
            low, high = transport.get_write_buffer_limits()
            result.update(write_buffer_bytes=size, write_buffer_low_bytes=low,
                write_buffer_high_bytes=high, transport_paused=self.socket.paused)
            self.buffer_peak_bytes = max(self.buffer_peak_bytes, size)
        return result

    def begin(self, frame_seq, wire_seq, *, budget_seconds=30.0):
        with suppress(Exception):
            self.frame_seq, self.wire_seq = frame_seq, wire_seq
            self.loop_lag_peak_ms = self.drain_ms = 0.0
            self.buffer_peak_bytes = 0
            self.active = True
            self.loop = asyncio.get_running_loop()
            self.send_started = self.loop.time()
            self.observation_deadline = self.send_started + budget_seconds
            self.next_tick = self.loop.time() + 0.1
            self.next_report = self.loop.time() + 1.0
            self.snapshot()
            self.timer = self.loop.call_at(self.next_tick, self._tick)

    def _tick(self):
        # Never schedule catch-up bursts after a stalled event loop.
        self.timer = None
        if not self.active:
            return
        with suppress(Exception):
            now = self.loop.time()
            lag = max(0.0, (now - self.next_tick) * 1000)
            self.loop_lag_peak_ms = max(self.loop_lag_peak_ms, lag)
            snapshot = self.snapshot()
            if now >= self.next_report or lag >= 100:
                self.emit("socket_send_pending", loop_lag_ms=lag,
                    elapsed_ms=(now - self.send_started) * 1000,
                    loop_lag_peak_ms=self.loop_lag_peak_ms, **snapshot)
                self.next_report = now + 1.0
            if now >= self.observation_deadline:
                self.emit("socket_observation_expired", **snapshot)
                self.active = False
                return  # A cancellation-hostile custom socket cannot leak timers forever.
            self.next_tick = now + 0.1
            self.timer = self.loop.call_at(self.next_tick, self._tick)

    def finish(self):
        # Called synchronously in the send's finally, including cancellation.
        self.active = False
        if self.timer is not None:
            self.timer.cancel()
            self.timer = None
        with suppress(Exception):
            self.loop_lag_peak_ms = max(self.loop_lag_peak_ms,
                max(0.0, (self.loop.time() - self.next_tick) * 1000))
        result = dict(self.snapshot(), loop_lag_peak_ms=self.loop_lag_peak_ms,
            drain_ms=self.drain_ms if isinstance(self.socket, _ObservedFlowControl) else None,
            write_buffer_peak_bytes=self.buffer_peak_bytes,
            flow_observer=isinstance(self.socket, _ObservedFlowControl))
        self.frame_seq = self.wire_seq = None
        return result

    def paused(self):
        with suppress(Exception):
            self.pause_started = time.monotonic()
            self.emit("socket_write_paused", **self.snapshot())

    def resumed(self):
        with suppress(Exception):
            duration = None if self.pause_started is None else (time.monotonic() - self.pause_started) * 1000
            self.pause_started = None
            self.emit("socket_write_resumed", write_pause_ms=duration, **self.snapshot())

    def drained(self, duration, outcome):
        with suppress(Exception):
            if not self.active:
                return  # No unrelated ping/close traffic labelled as a speech send.
            self.drain_ms += duration
            if duration >= 100 or outcome != "complete":
                self.emit("socket_drain_settled", drain_ms=duration,
                    outcome=outcome, **self.snapshot())


class _ObservedFlowControl:
    """Only observe; superclass remains the sole flow-control owner."""
    voice_diagnostics = None

    def pause_writing(self):
        super().pause_writing()
        with suppress(Exception):
            if self.voice_diagnostics is not None:
                self.voice_diagnostics.paused()

    def resume_writing(self):
        super().resume_writing()
        with suppress(Exception):
            if self.voice_diagnostics is not None:
                self.voice_diagnostics.resumed()

    async def drain(self):
        started = time.monotonic()
        # Attribute only drain in the actual socket.send task, not keepalive.
        observer = self.voice_diagnostics
        if observer is not None and asyncio.current_task() is not getattr(observer, "send_task", None):
            observer = None
        outcome = "failed"
        try:
            await super().drain()
            outcome = "complete"
        except asyncio.CancelledError:
            outcome = "cancelled"
            raise
        finally:
            with suppress(Exception):
                if observer is not None:
                    observer.drained((time.monotonic() - started) * 1000, outcome)

    async def send(self, message, **kwargs):
        observer = self.voice_diagnostics
        if observer is not None:
            observer.send_task = asyncio.current_task()
        try:
            return await super().send(message, **kwargs)
        finally:
            if observer is not None:
                observer.send_task = None


async def diagnostic_socket_factory(url, headers, timeout_seconds):
    from jiuwenswarm.server.live_voice.openai_realtime_session import default_realtime_socket_factory
    connection_factory = None
    try:
        from websockets.asyncio.client import ClientConnection
        class ObservedConnection(_ObservedFlowControl, ClientConnection):
            pass
        connection_factory = ObservedConnection
    except ImportError:
        pass  # websockets 12/custom factories retain the existing send path.
    socket = await default_realtime_socket_factory(url, headers, timeout_seconds,
        connection_factory=connection_factory)
    return socket


def attach_socket_diagnostics(socket, url, **identity):
    """Best effort; route hint is a policy snapshot, never actual-path proof."""
    try:
        observer = SocketDiagnostics(socket, **identity)
        if isinstance(socket, _ObservedFlowControl):
            socket.voice_diagnostics = observer
        route_hint = "unknown"
        with suppress(Exception):
            from websockets.uri import get_proxy, parse_uri
            from urllib.parse import urlsplit
            proxy = get_proxy(parse_uri(url))
            route_hint = "direct" if proxy is None else urlsplit(proxy).scheme
            if route_hint not in {"direct", "http", "https", "socks5", "socks5h", "socks4", "socks4a"}:
                route_hint = "unknown"
        peer_loopback = None
        with suppress(Exception):
            peer_loopback = ipaddress.ip_address(socket.transport.get_extra_info("peername")[0]).is_loopback
        observer.emit("socket_observer_attached", proxy_route_hint=route_hint,
            peer_loopback=peer_loopback, flow_observer=isinstance(socket, _ObservedFlowControl),
            **observer.snapshot())
        return observer
    except Exception:
        return None
