"""Pre-upgrade retry cannot replay a WebSocket handshake or media capability."""

import socket
from types import SimpleNamespace

import pytest

from jiuwenswarm.channels.web import app_web


def handler(path="/ws/live-voice/media"):
    value = app_web._SpaStaticHandler.__new__(app_web._SpaStaticHandler)
    value.path = path
    value.logger = SimpleNamespace(warning=lambda *args: None)
    return value


def test_local_media_connect_recovers_before_sending_any_bytes(monkeypatch):
    original = socket.create_connection
    calls = []
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()

        def connect(address, *, timeout):
            calls.append(timeout)
            if len(calls) == 1:
                raise TimeoutError("transient TCP connect failure")
            return original(address, timeout=timeout)

        monkeypatch.setattr(app_web.socket, "create_connection", connect)
        with handler()._connect_websocket_upstream(*listener.getsockname()) as upstream:
            peer, _ = listener.accept()
            with peer:
                peer.settimeout(0.05)
                with pytest.raises(TimeoutError):
                    peer.recv(1)
                assert upstream.gettimeout() == handler()._WS_CONNECT_TIMEOUT
    assert calls == [1.0, 1.0]


@pytest.mark.parametrize("error", [TimeoutError, ConnectionRefusedError, PermissionError])
def test_media_connect_is_bounded_and_does_not_retry_permission_failure(monkeypatch, error):
    calls = []

    def connect(address, *, timeout):
        calls.append((address, timeout))
        raise error("failed")

    monkeypatch.setattr(app_web.socket, "create_connection", connect)
    with pytest.raises(error):
        handler()._connect_websocket_upstream("127.0.0.1", 1234)
    assert len(calls) == (1 if error is PermissionError else 2)


@pytest.mark.parametrize("path,host", [("/ws/web", "127.0.0.1"), ("/ws/live-voice/media", "remote.invalid"), ("/ws/live-voice/media", "localhost")])
def test_nonlocal_or_nonmedia_websocket_keeps_existing_connect_policy(monkeypatch, path, host):
    calls = []

    def connect(address, *, timeout):
        calls.append(timeout)
        raise TimeoutError("failed")

    monkeypatch.setattr(app_web.socket, "create_connection", connect)
    with pytest.raises(TimeoutError):
        handler(path)._connect_websocket_upstream(host, 1234)
    assert calls == [handler()._WS_CONNECT_TIMEOUT]
