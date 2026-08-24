from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import subprocess
from pathlib import Path

import pytest
import scripts.live_voice.l0_browser_capture as l0_browser_capture
from websockets.datastructures import Headers
from websockets.exceptions import InvalidStatus
from websockets.http11 import Response

from scripts.live_voice.l0_browser_capture import (
    ACCEPTANCE_VERSION,
    SESSION_VERSION,
    _aggregate_cold_evidence,
    _assert_browser_socket_owner,
    _browser_websocket_connect,
    _browser_round_complete,
    _connect_owned_browser_socket,
    _configured_run_labels,
    _correlated_success_counts,
    _assert_browser_endpoint_owner,
    _discover_page,
    _invalidate_cold_eligibility,
    _labels,
    _load_session,
    _loopback_websocket,
    _owned_browser_socket,
    _read_browser_pages,
    _scenario_matrix_complete,
    _select_cases,
    _validate_temperature_capture_policy,
    _warmup_case,
)
from jiuwenswarm.server.live_voice.latency_measurement import (
    L0_RUN_LABELS_VERSION,
    load_l0_corpus_manifest,
)


CORPUS = Path("scripts/live_voice/l0_fixed_corpus.json")
LAUNCHER = Path("scripts/live_voice/start_hands_free_demo.ps1")
SOURCE_HEAD = "c31e85ade1a69e934d05bfb9c277568a1238663c"
ENVIRONMENT_REF = "environment-physical-formal-web-test-room"
CONFIGURATION_SHA256 = "b" * 64


def _session(tmp_path: Path, **updates: object) -> Path:
    path = tmp_path / "browser-session.json"
    browser_executable = tmp_path / "chrome.exe"
    browser_executable.touch(exist_ok=True)
    value: dict[str, object] = {
        "schema_version": SESSION_VERSION,
        "source_head": SOURCE_HEAD,
        "runtime_profile": "formal-web-validation",
        "evidence_directory": str(tmp_path),
        "run_labels_file": str(tmp_path / "run-labels.json"),
        "browser_endpoint": "http://127.0.0.1:9223",
        "browser_page_origin": "http://localhost:5173",
        "browser_executable_path": str(browser_executable.resolve()),
        "browser_profile_path": str(tmp_path.resolve()),
        "browser_launch_process_id": 4101,
        "browser_debugger_process_id": 4102,
        "browser_launch_nonce": "2" * 32,
        "temperature_epoch_id": "1" * 32,
        "cold_sample_available": True,
        "environment_ref": ENVIRONMENT_REF,
        "configuration_sha256": CONFIGURATION_SHA256,
        "physical_evidence": "pending-user-run",
        "raw_audio_retained": False,
        "transcript_retained": False,
    }
    value.update(updates)
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _cold_shard(
    root: Path,
    *,
    sample_index: int,
    epoch: str,
    scenario_id: str = "short-no-tool-zh",
    environment_ref: str = ENVIRONMENT_REF,
    configuration_sha256: str = CONFIGURATION_SHA256,
    corpus_sha256: str | None = None,
) -> Path:
    evidence = root / f"cold-{sample_index}"
    evidence.mkdir()
    _session(
        evidence,
        temperature_epoch_id=epoch,
        environment_ref=environment_ref,
        configuration_sha256=configuration_sha256,
    )
    acceptance = {
        "schema_version": ACCEPTANCE_VERSION,
        "profile_id": "physical-formal-web-cold",
        "scenario_id": scenario_id,
        "sample_index": sample_index,
        "temperature_epoch_id": epoch,
        "temperature_state": "fresh_launcher_epoch",
        "operator_confirmation": "pass",
        "browser_record_count": 2,
        "browser_dropped_record_count": 0,
        "automated_browser_complete": True,
        "physical_microphone": "operator_observed",
        "physical_speaker": "operator_observed",
        "subjective_audio": "operator_confirmed",
    }
    (evidence / "physical-acceptance.jsonl").write_text(
        json.dumps(acceptance) + "\n",
        encoding="utf-8",
    )
    (evidence / "cold-sample-consumed.json").write_text(
        json.dumps(
            {
                "schema_version": SESSION_VERSION,
                "temperature_epoch_id": epoch,
                "sample_index": sample_index,
            }
        ),
        encoding="utf-8",
    )
    (evidence / "browser.jsonl").write_text("{}\n", encoding="utf-8")
    _, expected_corpus_sha256 = load_l0_corpus_manifest(CORPUS)
    (evidence / "physical-report.json").write_text(
        json.dumps(
            {
                "source_head": SOURCE_HEAD,
                "corpus_sha256": corpus_sha256 or expected_corpus_sha256,
                "environment_ref": environment_ref,
                "physical_configuration_sha256": configuration_sha256,
                "physical_capture_kind": "cold_epoch_shard",
                "physical_temperature_epoch_id": epoch,
            }
        ),
        encoding="utf-8",
    )
    return evidence


def test_capture_session_is_loopback_closed_and_cannot_escape_evidence_directory(
    tmp_path: Path,
) -> None:
    session = _load_session(_session(tmp_path))
    assert session["browser_endpoint"] == "http://127.0.0.1:9223"

    for endpoint in (
        "http://127.0.0.1:9223@evil.example",
        "http://localhost:9223",
        "https://127.0.0.1:9223",
        "http://127.0.0.1:9000",
        "http://127.0.0.1:9223/path",
    ):
        with pytest.raises(ValueError, match="loopback-only"):
            _load_session(_session(tmp_path, browser_endpoint=endpoint))
    for page_origin in (
        "http://localhost:6173",
        "https://localhost:5173",
        "http://evil.example:5173",
        "http://localhost:5173@evil.example",
    ):
        with pytest.raises(ValueError, match="local Formal Web origin"):
            _load_session(_session(tmp_path, browser_page_origin=page_origin))

    assert (
        _loopback_websocket(
            "ws://127.0.0.1:9223/devtools/page/exact",
            expected_port=9223,
        )
        == "ws://127.0.0.1:9223/devtools/page/exact"
    )
    for websocket_url in (
        "ws://127.0.0.1:9223@evil.example/devtools/page/exact",
        "ws://localhost:9223/devtools/page/exact",
        "ws://127.0.0.1:9224/devtools/page/exact",
        "wss://127.0.0.1:9223/devtools/page/exact",
    ):
        with pytest.raises(RuntimeError, match="non-loopback"):
            _loopback_websocket(websocket_url, expected_port=9223)

    with pytest.raises(ValueError, match="loopback"):
        _load_session(
            _session(tmp_path, browser_endpoint="http://example.test:9223")
        )
    with pytest.raises(ValueError, match="escaped"):
        _load_session(
            _session(tmp_path, run_labels_file=str(tmp_path.parent / "labels.json"))
        )
    with pytest.raises(ValueError, match="closed shape"):
        _load_session(_session(tmp_path, credential="forbidden"))
    with pytest.raises(ValueError, match="environment reference"):
        _load_session(_session(tmp_path, environment_ref="Lab:1"))
    with pytest.raises(ValueError, match="environment reference"):
        _load_session(_session(tmp_path, environment_ref="a" * 65))


def test_cdp_page_selection_requires_exact_origin_nonce_and_websocket(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _load_session(_session(tmp_path))
    page = {
        "type": "page",
        "url": (
            "http://localhost:5173/chat/session-after-spa-navigation"
            f"?live_voice_l0_measurement=1&live_voice_l0_launch_nonce={'2' * 32}"
        ),
        "webSocketDebuggerUrl": "ws://127.0.0.1:9223/devtools/page/exact",
    }
    pages: object = [page]
    monkeypatch.setattr(
        l0_browser_capture,
        "_read_browser_pages",
        lambda _session: pages,
    )
    assert _discover_page(session) == page["webSocketDebuggerUrl"]

    for updates in (
        {"url": "http://evil.example/chat/new"},
        {
            "url": (
                "http://localhost:5173/chat/new?live_voice_l0_measurement=1"
                f"&live_voice_l0_launch_nonce={'3' * 32}"
            )
        },
        {"webSocketDebuggerUrl": "ws://evil.example:9223/devtools/page/exact"},
        {"webSocketDebuggerUrl": "ws://127.0.0.1:9224/devtools/page/exact"},
        {"webSocketDebuggerUrl": "ws://127.0.0.1:9223/devtools/page/exact?x=1"},
    ):
        pages = [{**page, **updates}]
        with pytest.raises(RuntimeError):
            _discover_page(session)


@pytest.mark.asyncio
async def test_preconnected_websocket_disables_proxy_and_structurally_rejects_redirect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ws_proxy", "http://127.0.0.1:65530")
    connected_socket = object()
    connector = _browser_websocket_connect(  # type: ignore[arg-type]
        "ws://127.0.0.1:9223/devtools/page/exact",
        connected_socket,
    )
    assert connector.connection_kwargs["sock"] is connected_socket

    direct_connection = object()
    create_calls: list[dict[str, object]] = []

    async def create_connection(
        _factory: object,
        **kwargs: object,
    ) -> tuple[object, object]:
        create_calls.append(kwargs)
        return object(), direct_connection

    monkeypatch.setattr(
        asyncio.get_running_loop(),
        "create_connection",
        create_connection,
    )
    assert await connector.create_connection() is direct_connection
    assert create_calls == [{"sock": connected_socket}]

    redirect = InvalidStatus(
        Response(
            302,
            "Found",
            Headers(
                {
                    "Location": "ws://127.0.0.1:9224/devtools/page/foreign"
                }
            ),
        )
    )
    result = connector.process_redirect(redirect)
    assert isinstance(result, ValueError)
    assert "preexisting socket" in str(result)


def test_http_discovery_uses_only_the_preconnected_owned_socket(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _load_session(_session(tmp_path))
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:65530")
    monkeypatch.setenv("https_proxy", "http://127.0.0.1:65530")
    requests: list[tuple[object, ...]] = []
    response_status = 200

    class _RawSocket:
        closed = False

        def close(self) -> None:
            self.closed = True

    raw_sockets: list[_RawSocket] = []

    class _Response:
        @property
        def status(self) -> int:
            return response_status

        def read(self, _limit: int) -> bytes:
            return json.dumps([{"type": "page"}]).encode("utf-8")

    class _HttpConnection:
        def __init__(self, host: str, port: int, *, timeout: int) -> None:
            assert (host, port, timeout) == ("127.0.0.1", 9223, 3)
            self.sock: _RawSocket | None = None

        def request(
            self,
            method: str,
            path: str,
            *,
            headers: dict[str, str],
        ) -> None:
            requests.append((method, path, headers, self.sock))

        def getresponse(self) -> _Response:
            return _Response()

        def close(self) -> None:
            assert self.sock is not None
            self.sock.close()

    def connect(_session: dict[str, object]) -> _RawSocket:
        value = _RawSocket()
        raw_sockets.append(value)
        return value

    monkeypatch.setattr(
        l0_browser_capture,
        "_connect_owned_browser_socket",
        connect,
    )
    monkeypatch.setattr(
        l0_browser_capture.http.client,
        "HTTPConnection",
        _HttpConnection,
    )
    assert _read_browser_pages(session) == [{"type": "page"}]
    method, path, headers, used_socket = requests[-1]
    assert (method, path) == ("GET", "/json")
    assert headers == {
        "Accept": "application/json",
        "Connection": "close",
        "Host": "127.0.0.1:9223",
    }
    assert used_socket is raw_sockets[-1]
    assert raw_sockets[-1].closed

    response_status = 302
    with pytest.raises(RuntimeError, match="HTTP 200"):
        _read_browser_pages(session)
    assert raw_sockets[-1].closed


def test_browser_endpoint_owner_requires_exact_listener_profile_and_flags(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _load_session(_session(tmp_path))

    class _Address:
        ip = "127.0.0.1"
        port = 9223

    class _Connection:
        status = l0_browser_capture.psutil.CONN_LISTEN
        pid = 4102
        laddr = _Address()

    class _Process:
        def __init__(self, process_id: int) -> None:
            assert process_id in {4101, 4102}
            self.pid = process_id

        def name(self) -> str:
            return "chrome.exe"

        def exe(self) -> str:
            return str((tmp_path / "chrome.exe").resolve())

        def cmdline(self) -> list[str]:
            return [
                "chrome.exe",
                f"--user-data-dir={tmp_path.resolve()}",
                "--remote-debugging-address=127.0.0.1",
                "--remote-debugging-port=9223",
            ]

        def parents(self) -> list["_Process"]:
            return [_Process(4101)] if self.pid == 4102 else []

    monkeypatch.setattr(
        l0_browser_capture.psutil,
        "net_connections",
        lambda **_kwargs: [_Connection()],
    )
    monkeypatch.setattr(l0_browser_capture.psutil, "Process", _Process)
    _assert_browser_endpoint_owner(session)

    _Connection.pid = None
    with pytest.raises(RuntimeError, match="listener owner"):
        _assert_browser_endpoint_owner(session)
    _Connection.pid = 4102

    for unexpected_address in ("::1", "0.0.0.0", "::"):
        _Address.ip = unexpected_address
        with pytest.raises(RuntimeError, match="listener owner"):
            _assert_browser_endpoint_owner(session)
    _Address.ip = "127.0.0.1"

    class _UnknownIpv4Connection:
        status = l0_browser_capture.psutil.CONN_LISTEN
        pid = None

        class _Ipv4Address:
            ip = "127.0.0.1"
            port = 9223

        laddr = _Ipv4Address()

    _Address.ip = "::1"
    monkeypatch.setattr(
        l0_browser_capture.psutil,
        "net_connections",
        lambda **_kwargs: [_Connection(), _UnknownIpv4Connection()],
    )
    with pytest.raises(RuntimeError, match="listener owner"):
        _assert_browser_endpoint_owner(session)
    _Address.ip = "127.0.0.1"
    monkeypatch.setattr(
        l0_browser_capture.psutil,
        "net_connections",
        lambda **_kwargs: [_Connection()],
    )

    _Connection.pid = 9999
    with pytest.raises(RuntimeError, match="listener owner"):
        _assert_browser_endpoint_owner(session)
    _Connection.pid = 4102

    monkeypatch.setattr(
        _Process,
        "cmdline",
        lambda _self: ["chrome.exe", "--remote-debugging-port=9223"],
    )
    with pytest.raises(RuntimeError, match="exact isolated profile"):
        _assert_browser_endpoint_owner(session)

    exact_arguments = [
        "chrome.exe",
        f"--user-data-dir={tmp_path.resolve()}",
        "--remote-debugging-address=127.0.0.1",
        "--remote-debugging-port=9223",
    ]
    for conflicting_duplicate in (
        f"--user-data-dir={tmp_path.resolve()}-attacker",
        "--remote-debugging-address=0.0.0.0",
        "--remote-debugging-port=9224",
    ):
        monkeypatch.setattr(
            _Process,
            "cmdline",
            lambda _self, extra=conflicting_duplicate: [*exact_arguments, extra],
        )
        with pytest.raises(RuntimeError, match="exact isolated profile"):
            _assert_browser_endpoint_owner(session)

    monkeypatch.setattr(
        _Process,
        "cmdline",
        lambda _self: [
            "chrome.exe",
            f"--user-data-dir={tmp_path.resolve()}-attacker",
            "--remote-debugging-address=127.0.0.1",
            "--remote-debugging-port=9223",
        ],
    )
    with pytest.raises(RuntimeError, match="exact isolated profile"):
        _assert_browser_endpoint_owner(session)

    monkeypatch.setattr(
        _Process,
        "cmdline",
        lambda _self: [
            "chrome.exe",
            f"--user-data-dir={tmp_path.resolve()}",
            "--remote-debugging-address=127.0.0.1",
            "--remote-debugging-port=9223",
        ],
    )
    monkeypatch.setattr(
        _Process,
        "exe",
        lambda _self: str((tmp_path / "different-chrome.exe").resolve()),
    )
    with pytest.raises(RuntimeError, match="exact isolated profile"):
        _assert_browser_endpoint_owner(session)

    monkeypatch.setattr(
        _Process,
        "exe",
        lambda _self: str((tmp_path / "chrome.exe").resolve()),
    )
    monkeypatch.setattr(_Process, "parents", lambda _self: [])
    with pytest.raises(RuntimeError, match="not descended"):
        _assert_browser_endpoint_owner(session)


def test_browser_socket_owner_requires_exact_peer_and_server_four_tuple(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _load_session(_session(tmp_path))

    class _RawSocket:
        peer = ("127.0.0.1", 9223)
        local = ("127.0.0.1", 50123)

        def getpeername(self) -> tuple[str, int]:
            return self.peer

        def getsockname(self) -> tuple[str, int]:
            return self.local

    class _Address:
        def __init__(self, ip: str, port: int) -> None:
            self.ip = ip
            self.port = port

    class _Connection:
        status = l0_browser_capture.psutil.CONN_ESTABLISHED
        pid = 4102
        laddr = _Address("127.0.0.1", 9223)
        raddr = _Address("127.0.0.1", 50123)

    monkeypatch.setattr(
        l0_browser_capture.psutil,
        "net_connections",
        lambda **_kwargs: [_Connection()],
    )
    _assert_browser_socket_owner(session, _RawSocket())  # type: ignore[arg-type]

    _RawSocket.peer = ("127.0.0.1", 9224)
    with pytest.raises(RuntimeError, match="escaped"):
        _assert_browser_socket_owner(session, _RawSocket())  # type: ignore[arg-type]
    _RawSocket.peer = ("127.0.0.1", 9223)

    _Connection.pid = None
    with pytest.raises(RuntimeError, match="not owned"):
        _assert_browser_socket_owner(session, _RawSocket())  # type: ignore[arg-type]
    _Connection.pid = 4102

    _Connection.raddr = _Address("127.0.0.1", 50124)
    with pytest.raises(RuntimeError, match="not owned"):
        _assert_browser_socket_owner(session, _RawSocket())  # type: ignore[arg-type]


def test_direct_socket_connect_revalidates_listener_and_closes_on_owner_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _load_session(_session(tmp_path))
    endpoint_owner_calls = 0
    socket_owner_calls: list[object] = []
    reject_socket_owner = False

    class _RawSocket:
        closed = False

        def close(self) -> None:
            self.closed = True

    created: list[_RawSocket] = []

    def create_connection(
        address: tuple[str, int],
        *,
        timeout: int,
    ) -> _RawSocket:
        assert (address, timeout) == (("127.0.0.1", 9223), 3)
        value = _RawSocket()
        created.append(value)
        return value

    def assert_endpoint_owner(_session: dict[str, object]) -> None:
        nonlocal endpoint_owner_calls
        endpoint_owner_calls += 1

    def assert_socket_owner(_session: dict[str, object], value: object) -> None:
        socket_owner_calls.append(value)
        if reject_socket_owner:
            raise RuntimeError("wrong established owner")

    monkeypatch.setattr(
        l0_browser_capture,
        "_assert_browser_endpoint_owner",
        assert_endpoint_owner,
    )
    monkeypatch.setattr(
        l0_browser_capture,
        "_assert_browser_socket_owner",
        assert_socket_owner,
    )
    monkeypatch.setattr(
        l0_browser_capture.network_socket,
        "create_connection",
        create_connection,
    )

    connected = _connect_owned_browser_socket(session)
    assert connected is created[0]
    assert endpoint_owner_calls == 2
    assert socket_owner_calls == [connected]
    assert not connected.closed

    reject_socket_owner = True
    with pytest.raises(RuntimeError, match="wrong established owner"):
        _connect_owned_browser_socket(session)
    assert created[-1].closed


@pytest.mark.asyncio
async def test_owned_browser_socket_binds_the_established_direct_stream(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _load_session(_session(tmp_path))
    connection = object()
    connector_inputs: list[tuple[str, object]] = []
    socket_owner_calls: list[object] = []

    class _RawSocket:
        blocking: bool | None = None
        closed = False

        def setblocking(self, value: bool) -> None:
            self.blocking = value

        def close(self) -> None:
            self.closed = True

    raw_socket = _RawSocket()

    class _Connection:
        async def __aenter__(self) -> object:
            return connection

        async def __aexit__(self, *_args: object) -> None:
            return None

    def connect(websocket_url: str, value: object) -> _Connection:
        connector_inputs.append((websocket_url, value))
        return _Connection()

    monkeypatch.setattr(
        l0_browser_capture,
        "_discover_page",
        lambda _session: "ws://127.0.0.1:9223/devtools/page/exact",
    )
    monkeypatch.setattr(
        l0_browser_capture,
        "_assert_browser_socket_owner",
        lambda _session, value: socket_owner_calls.append(value),
    )
    monkeypatch.setattr(
        l0_browser_capture,
        "_connect_owned_browser_socket",
        lambda _session: raw_socket,
    )
    monkeypatch.setattr(
        l0_browser_capture,
        "_browser_websocket_connect",
        connect,
    )

    async with _owned_browser_socket(session) as connected:
        assert connected is connection
    assert connector_inputs == [
        ("ws://127.0.0.1:9223/devtools/page/exact", raw_socket)
    ]
    assert socket_owner_calls == [raw_socket]
    assert raw_socket.blocking is False
    assert raw_socket.closed


def test_launcher_binds_l0_to_exact_environment_agent_config_and_project_revision() -> None:
    source = LAUNCHER.read_text(encoding="utf-8-sig")
    assert "^[a-z0-9][a-z0-9._-]{0,63}$" in source
    assert "Get-FileHash -LiteralPath $ConfigYamlPath -Algorithm SHA256" in source
    assert "agent_configuration_sha256 = $agentConfigurationSha256" in source
    assert "revision = $projectRevision" in source
    assert "$L0Measurement -and $projectStatus.Count -gt 0" in source
    assert "Join-Path $l0LogsRoot $L0MeasurementDirectory" in source
    assert "仓库内的 L0 证据目录必须位于已忽略的 logs 目录" in source
    assert "browser_page_origin = \"http://localhost:$FrontendPort\"" in source
    assert "Get-ListeningOwners -Ports @($RemoteDebuggingPort)" in source
    assert "CommandLineToArgvW" in source
    assert "LocalAddress   = [string]$listener.LocalAddress" in source
    assert "$debuggerOwner.LocalAddress -cne '127.0.0.1'" in source
    assert "Test-ExactCommandLineOption" in source
    assert "$matches.Count -eq 1" in source
    assert "$matches[0].Substring($prefix.Length) -ieq $ExpectedValue" in source
    assert "Sort-Object ProcessId, Port, LocalAddress -Unique" in source
    assert '$debuggerOwner.CommandLine -notlike "*$profilePath*"' not in source
    assert "$debuggerOwner.ExecutablePath -ine $ChromeExecutable" in source
    assert "browser_debugger_process_id = [int]$isolatedChrome.DebuggerProcessId" in source
    assert "browser_launch_process_id = [int]$isolatedChrome.LaunchProcessId" in source
    assert "browser_executable_path = $ChromeExecutable" in source
    assert "browser_profile_path = $isolatedChromeProfile" in source
    assert "live_voice_l0_launch_nonce=$browserLaunchNonce" in source
    assert "--remote-debugging-address=127.0.0.1" in source
    assert "Get-ManagedIsolatedChromeProfile" in source
    assert "CommandLine -like \"*$profilePrefix*\"" not in source


def test_launcher_cleanup_selects_only_exact_managed_user_data_dir() -> None:
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if powershell is None:
        pytest.skip("PowerShell is unavailable")
    launcher = str(LAUNCHER.resolve()).replace("'", "''")
    probe = rf"""
$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    '{launcher}', [ref]$tokens, [ref]$errors
)
$definition = $ast.FindAll({{
    param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
        $node.Name -eq 'Get-ManagedIsolatedChromeProfile'
}}, $true) | Select-Object -First 1
if ($null -eq $definition -or $errors.Count -ne 0) {{ exit 10 }}
Invoke-Expression $definition.Extent.Text
$managed = Join-Path ([System.IO.Path]::GetTempPath()) 'jiuwenswarm-live-voice-chrome-20260824-010203-1234abcd'
$ordinary = Join-Path ([System.IO.Path]::GetTempPath()) 'ordinary-profile'
$exact = Get-ManagedIsolatedChromeProfile -Arguments @('chrome.exe', "--user-data-dir=$managed")
if ($exact -ine [System.IO.Path]::GetFullPath($managed).TrimEnd('\')) {{ exit 11 }}
if ($null -ne (Get-ManagedIsolatedChromeProfile -Arguments @(
    'chrome.exe', "--user-data-dir=$ordinary", "--log-file=$managed-decoy.log"
))) {{ exit 12 }}
if ($null -ne (Get-ManagedIsolatedChromeProfile -Arguments @(
    'chrome.exe', "--user-data-dir=$managed-attacker"
))) {{ exit 13 }}
if ($null -ne (Get-ManagedIsolatedChromeProfile -Arguments @(
    'chrome.exe', "--user-data-dir=$managed", "--user-data-dir=$ordinary"
))) {{ exit 14 }}
"""
    result = subprocess.run(
        [powershell, "-NoProfile", "-Command", probe],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_browser_capture_uses_websockets_public_api_at_declared_floor() -> None:
    source = Path(l0_browser_capture.__file__).read_text(encoding="utf-8")
    assert "from websockets import connect as WebSocketConnect" in source
    assert "websockets.asyncio.client" not in source


def test_default_physical_cases_exclude_injected_and_degraded_profiles() -> None:
    manifest, _ = load_l0_corpus_manifest(CORPUS)
    selected = _select_cases(manifest, [])
    categories = {str(item["category"]) for item in selected}
    assert {"short_no_tool", "long_answer", "real_tool", "task_create"} <= categories
    assert "provider_slow" not in categories
    assert "provider_failure" not in categories
    assert "degraded_network" not in categories
    assert all(item["expected_classification"] == "success" for item in selected)

    with pytest.raises(ValueError, match="non-injected nominal success"):
        _select_cases(manifest, ["provider-failure-zh"])


def test_dynamic_labels_have_no_free_form_or_private_fields() -> None:
    labels = _labels(
        profile_id="physical-formal-web-warm",
        scenario_id="short-no-tool-zh",
        sample_index=3,
        temperature="warm",
    )
    assert labels == {
        "schema_version": L0_RUN_LABELS_VERSION,
        "profile_id": "physical-formal-web-warm",
        "scenario_id": "short-no-tool-zh",
        "sample_index": 3,
        "temperature": "warm",
        "evidence_source": "physical",
    }


def test_browser_round_requires_exact_labels_no_drops_and_one_success_terminal() -> None:
    labels = _labels(
        profile_id="physical-formal-web-warm",
        scenario_id="short-no-tool-zh",
        sample_index=3,
        temperature="warm",
    )
    browser_labels = dict(labels)
    browser_labels.pop("schema_version")
    records = [
        {
            **browser_labels,
            "milestone": "browser_eot_receipt",
            "classification": "unknown",
        },
        {
            **browser_labels,
            "milestone": "playout_completed",
            "classification": "success",
        },
    ]
    snapshot = {
        "enabled": True,
        "configured": True,
        "accepted_records": 2,
        "dropped_records": 0,
        "records": records,
    }
    assert _browser_round_complete(snapshot, browser_labels)

    dropped = {**snapshot, "dropped_records": 1}
    assert not _browser_round_complete(dropped, browser_labels)
    partial = {**snapshot, "accepted_records": 1, "records": records[:1]}
    assert not _browser_round_complete(partial, browser_labels)
    wrong = {
        **snapshot,
        "records": [{**records[0], "sample_index": 4}, records[1]],
    }
    assert not _browser_round_complete(wrong, browser_labels)
    fallback = {
        **snapshot,
        "accepted_records": 3,
        "records": [
            *records,
            {
                **browser_labels,
                "milestone": "fallback",
                "classification": "fallback",
            },
        ],
    }
    assert not _browser_round_complete(fallback, browser_labels)


def test_correlated_success_count_intersects_operator_browser_and_aggregate() -> None:
    report = {
        "rounds": [
            {
                "profile_id": "physical-formal-web-warm",
                "scenario_id": "short-no-tool-zh",
                "sample_index": 1,
                "success_eligible": True,
            },
            {
                "profile_id": "physical-formal-web-warm",
                "scenario_id": "long-answer-zh",
                "sample_index": 2,
                "success_eligible": True,
            },
        ]
    }
    accepted = {
        ("physical-formal-web-warm", "short-no-tool-zh", 1),
        ("physical-formal-web-warm", "task-status-zh", 3),
    }
    assert _correlated_success_counts(
        report,
        accepted,
        {"short-no-tool-zh", "task-status-zh"},
    ) == {"short-no-tool-zh": 1, "task-status-zh": 0}


def test_physical_profile_requires_target_total_and_every_selected_scenario() -> None:
    assert not _scenario_matrix_complete(
        {"short-no-tool-zh": 20, "task-status-zh": 0},
        20,
    )
    assert _scenario_matrix_complete(
        {"short-no-tool-zh": 19, "task-status-zh": 1},
        20,
    )


def test_temperature_policy_separates_one_fresh_cold_sample_from_warmed_matrix() -> None:
    manifest, _ = load_l0_corpus_manifest(CORPUS)
    profiles = {
        str(item["profile_id"]): item
        for item in manifest["profiles"]
        if type(item) is dict
    }
    one_case = _select_cases(manifest, ["short-no-tool-zh"])
    all_cases = _select_cases(manifest, [])
    assert (
        _validate_temperature_capture_policy(
            profile=profiles["physical-formal-web-cold"],
            cases=one_case,
            temperature="cold",
            successful_rounds=1,
            sample_index_start=12,
        )
        == 12
    )
    with pytest.raises(ValueError, match="one scenario and one sample"):
        _validate_temperature_capture_policy(
            profile=profiles["physical-formal-web-cold"],
            cases=all_cases,
            temperature="cold",
            successful_rounds=20,
            sample_index_start=0,
        )
    with pytest.raises(ValueError, match="explicit unique"):
        _validate_temperature_capture_policy(
            profile=profiles["physical-formal-web-cold"],
            cases=one_case,
            temperature="cold",
            successful_rounds=1,
            sample_index_start=None,
        )
    assert (
        _validate_temperature_capture_policy(
            profile=profiles["physical-formal-web-warm"],
            cases=all_cases,
            temperature="warm",
            successful_rounds=20,
            sample_index_start=None,
        )
        == 0
    )


def test_any_capture_invalidates_cold_epoch_before_browser_interaction(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "cold-sample-consumed.json"
    _invalidate_cold_eligibility(
        marker_path=marker,
        temperature_epoch_id="1" * 32,
        sample_index=4,
        cold_capture=False,
    )
    assert json.loads(marker.read_text(encoding="utf-8")) == {
        "schema_version": SESSION_VERSION,
        "temperature_epoch_id": "1" * 32,
        "sample_index": 4,
    }
    with pytest.raises(RuntimeError, match="already consumed"):
        _invalidate_cold_eligibility(
            marker_path=marker,
            temperature_epoch_id="1" * 32,
            sample_index=4,
            cold_capture=True,
        )


def test_targeted_warm_capture_uses_one_non_mutating_dialogue_warmup() -> None:
    manifest, _ = load_l0_corpus_manifest(CORPUS)
    warmup = _warmup_case(manifest)
    assert warmup["case_id"] == "short-no-tool-zh"
    assert warmup["expected_route"] == "dialogue"
    assert warmup["action_sequence"] == ["submit", "await-audio"]


def test_twenty_unique_cold_launcher_epochs_complete_one_aggregate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence_directories = [
        _cold_shard(
            tmp_path,
            sample_index=index,
            epoch=f"{index + 1:032x}",
        )
        for index in range(20)
    ]

    def aggregate(**kwargs: object) -> dict[str, object]:
        inputs = kwargs["inputs"]
        assert isinstance(inputs, list)
        assert len(inputs) == 20
        assert kwargs["accepted_round_keys"] == frozenset(
            {
                ("physical-formal-web-cold", "short-no-tool-zh", index)
                for index in range(20)
            }
        )
        return {
            "environment_ref": kwargs["environment_ref"],
            "rounds": [
                {
                    "profile_id": "physical-formal-web-cold",
                    "scenario_id": "short-no-tool-zh",
                    "sample_index": index,
                    "success_eligible": True,
                }
                for index in range(20)
            ]
        }

    monkeypatch.setattr(
        l0_browser_capture,
        "clean_source_head",
        lambda: SOURCE_HEAD,
    )
    monkeypatch.setattr(l0_browser_capture, "aggregate_jsonl", aggregate)
    output = tmp_path / "cold-aggregate.json"
    result = _aggregate_cold_evidence(
        argparse.Namespace(
            corpus=CORPUS,
            scenario=["short-no-tool-zh"],
            successful_rounds=20,
            evidence_directory=evidence_directories,
            output=output,
        )
    )

    assert result == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["physical_capture_kind"] == "cold_epoch_aggregate"
    assert report["physical_cold_epoch_count"] == 20
    assert report["physical_accepted_cold_epoch_count"] == 20
    assert len(report["physical_cold_temperature_epoch_ids"]) == 20
    assert report["physical_correlated_successes"] == 20
    assert report["physical_profile_complete"] is True
    assert report["environment_ref"] == ENVIRONMENT_REF
    assert report["physical_configuration_sha256"] == CONFIGURATION_SHA256


def test_cold_aggregate_rejects_reused_launcher_epoch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    epoch = "a" * 32
    evidence_directories = [
        _cold_shard(tmp_path, sample_index=0, epoch=epoch),
        _cold_shard(tmp_path, sample_index=1, epoch=epoch),
    ]
    monkeypatch.setattr(
        l0_browser_capture,
        "clean_source_head",
        lambda: SOURCE_HEAD,
    )

    with pytest.raises(ValueError, match="reused a launcher temperature epoch"):
        _aggregate_cold_evidence(
            argparse.Namespace(
                corpus=CORPUS,
                scenario=["short-no-tool-zh"],
                successful_rounds=20,
                evidence_directory=evidence_directories,
                output=tmp_path / "must-not-exist.json",
            )
        )


@pytest.mark.parametrize(
    ("shard_updates", "message"),
    [
        ({"environment_ref": "environment-physical-other-room"}, "do not share"),
        ({"configuration_sha256": "c" * 64}, "do not share"),
        ({"corpus_sha256": "d" * 64}, "conflicts with"),
    ],
)
def test_cold_aggregate_requires_one_corpus_environment_and_configuration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    shard_updates: dict[str, str],
    message: str,
) -> None:
    first = _cold_shard(tmp_path, sample_index=0, epoch="1" * 32)
    second = _cold_shard(
        tmp_path,
        sample_index=1,
        epoch="2" * 32,
        **shard_updates,
    )
    monkeypatch.setattr(l0_browser_capture, "clean_source_head", lambda: SOURCE_HEAD)

    with pytest.raises(ValueError, match=message):
        _aggregate_cold_evidence(
            argparse.Namespace(
                corpus=CORPUS,
                scenario=["short-no-tool-zh"],
                successful_rounds=20,
                evidence_directory=[first, second],
                output=tmp_path / "must-not-exist.json",
            )
        )


@pytest.mark.asyncio
async def test_configured_labels_disable_backend_and_browser_on_exception(
    tmp_path: Path,
) -> None:
    labels_path = tmp_path / "run-labels.json"

    class _Cdp:
        def __init__(self) -> None:
            self.expressions: list[str] = []

        async def evaluate(self, expression: str) -> object:
            self.expressions.append(expression)
            return True

    cdp = _Cdp()
    run_labels = _labels(
        profile_id="physical-formal-web-warm",
        scenario_id="short-no-tool-zh",
        sample_index=4,
        temperature="warm",
    )
    browser_labels = dict(run_labels)
    browser_labels.pop("schema_version")
    with pytest.raises(RuntimeError, match="operator interrupted"):
        async with _configured_run_labels(
            labels_path=labels_path,
            cdp=cdp,  # type: ignore[arg-type]
            run_labels=run_labels,
            browser_labels=browser_labels,
        ):
            raise RuntimeError("operator interrupted")

    assert json.loads(labels_path.read_text(encoding="utf-8")) == {
        "schema_version": L0_RUN_LABELS_VERSION,
        "measurement": "disabled",
    }
    assert "disable()" in cdp.expressions[-1]


@pytest.mark.asyncio
async def test_configured_labels_disable_backend_when_browser_configuration_raises(
    tmp_path: Path,
) -> None:
    labels_path = tmp_path / "run-labels.json"

    class _Cdp:
        def __init__(self) -> None:
            self.expressions: list[str] = []

        async def evaluate(self, expression: str) -> object:
            self.expressions.append(expression)
            if len(self.expressions) == 1:
                raise RuntimeError("browser closed during configuration")
            return True

    cdp = _Cdp()
    run_labels = _labels(
        profile_id="physical-formal-web-warm",
        scenario_id="short-no-tool-zh",
        sample_index=5,
        temperature="warm",
    )
    browser_labels = dict(run_labels)
    browser_labels.pop("schema_version")

    with pytest.raises(RuntimeError, match="browser closed"):
        async with _configured_run_labels(
            labels_path=labels_path,
            cdp=cdp,  # type: ignore[arg-type]
            run_labels=run_labels,
            browser_labels=browser_labels,
        ):
            pytest.fail("configuration failure must not enter the capture body")

    assert json.loads(labels_path.read_text(encoding="utf-8")) == {
        "schema_version": L0_RUN_LABELS_VERSION,
        "measurement": "disabled",
    }
    assert len(cdp.expressions) == 2
    assert "disable()" in cdp.expressions[-1]
