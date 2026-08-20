from __future__ import annotations

import asyncio
import importlib
from collections import Counter
from types import SimpleNamespace
from typing import Any

import pytest

from jiuwenswarm.gateway import app_gateway as gateway_module
from jiuwenswarm.gateway.routing.route_binding import GatewayRouteBinding


_SHUTDOWN_PHASES = (
    "a2a.stop",
    "a2a.unregister",
    "gateway.stop",
    "inbound.stop",
    "tui.stop",
    "web.stop",
    "channels.pop.feishu",
    "channels.feishu.stop",
    "channels.pop.xiaoyi",
    "channels.xiaoyi.stop",
    "cron.stop",
    "dispatch.stop",
    "heartbeat.stop",
    "forward.stop",
    "client.disconnect",
    "restart_cleanup",
)


class _ShutdownHarness:
    def __init__(
        self,
        *,
        failures: dict[str, BaseException] | None = None,
        restart_requested: bool = True,
        wait_failure: BaseException | None = None,
    ) -> None:
        self.failures = dict(failures or {})
        self.restart_requested = restart_requested
        self.wait_failure = wait_failure
        self.calls: list[str] = []
        self.cleanup_task: asyncio.Task[None] | None = None
        self.test_cleanup_active = False

    def call(self, phase: str) -> None:
        self.calls.append(phase)
        failure = self.failures.get(phase)
        if failure is not None:
            raise failure

    async def async_call(self, phase: str) -> None:
        self.call(phase)

    async def cancel_leftover_cleanup(self) -> None:
        task = self.cleanup_task
        if task is None or task.done():
            return
        self.test_cleanup_active = True
        try:
            task.cancel()
            try:
                await task
            except BaseException:
                pass
        finally:
            self.test_cleanup_active = False


async def _wait_forever() -> None:
    await asyncio.Event().wait()


def _install_gateway_fakes(
    monkeypatch: pytest.MonkeyPatch,
    harness: _ShutdownHarness,
) -> None:
    class _Client:
        async def connect(self, _url: str) -> None:
            return None

        async def disconnect(self) -> None:
            await harness.async_call("client.disconnect")

        def set_or_update_server_config(self, **_kwargs: object) -> None:
            return None

        def set_channel_manager(self, _manager: object) -> None:
            return None

    client = _Client()

    class _Registry:
        @classmethod
        def create_instance(cls, **_kwargs: object) -> _Registry:
            return cls()

        def get_agent_server_client_extension(self) -> object:
            return SimpleNamespace(
                metadata=SimpleNamespace(name="shutdown-test-client"),
                get_client=lambda: client,
            )

        def get_third_agent_extension(self) -> None:
            return None

    class _ExtensionManager:
        def __init__(self, **_kwargs: object) -> None:
            pass

        async def load_all_extensions(self) -> None:
            return None

        def list_extensions(self) -> list[object]:
            return []

    class _MessageHandler:
        def __init__(self, _client: object) -> None:
            pass

        async def start_forwarding(self) -> None:
            return None

        async def stop_forwarding(self) -> None:
            await harness.async_call("forward.stop")

        def set_inbound_pipeline(self, _pipeline: object) -> None:
            return None

        def set_outbound_pipeline(self, _pipeline: object) -> None:
            return None

        def set_cron_controller(self, _controller: object) -> None:
            return None

        def set_channel_manager(self, _manager: object) -> None:
            return None

        def update_evolution_auto_save(self, _config: object) -> None:
            return None

    class _CronJobStore:
        def __init__(self, **_kwargs: object) -> None:
            pass

    class _CronScheduler:
        def __init__(self, **_kwargs: object) -> None:
            pass

        async def start(self) -> None:
            return None

        async def stop(self) -> None:
            await harness.async_call("cron.stop")

    class _CronController:
        @classmethod
        def get_instance(cls, **_kwargs: object) -> _CronController:
            return cls()

    class _HeartbeatService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        async def start(self) -> None:
            return None

        async def stop(self) -> None:
            await harness.async_call("heartbeat.stop")

    class _DynamicChannel:
        def __init__(self, channel_id: str) -> None:
            self.channel_id = channel_id
            self.start_task = asyncio.create_task(
                _wait_forever(),
                name=f"shutdown-test-{channel_id}",
            )

        async def stop(self) -> None:
            await harness.async_call(f"channels.{self.channel_id}.stop")

    class _ChannelManager:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            self.enabled_channels: set[str] = set()
            self._config_callback: Any = None

        def set_config_callback(self, callback: object) -> None:
            self._config_callback = callback

        async def set_config(self, _config: object) -> None:
            return None

        async def start_dispatch(self) -> None:
            return None

        async def stop_dispatch(self) -> None:
            await harness.async_call("dispatch.stop")

        def register_channel(self, _channel: object) -> None:
            return None

        def register_channel_with_inbound(
            self,
            _channel: object,
            _callback: object,
        ) -> None:
            return None

        def register_external_channel(
            self,
            _channel_id: str,
            _channel: object,
        ) -> None:
            return None

        def unregister_channel(self, channel_id: str) -> None:
            assert channel_id == "a2a"
            harness.call("a2a.unregister")

        def pop_channels_by_id(self, channel_id: str) -> list[object]:
            harness.call(f"channels.pop.{channel_id}")
            return [_DynamicChannel(channel_id)]

    class _BaseChannel:
        channel_id = "unused"

        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        async def start(self) -> None:
            await _wait_forever()

    class _A2AChannel(_BaseChannel):
        channel_id = "a2a"

        async def stop(self) -> None:
            await harness.async_call("a2a.stop")

    class _WebChannel(_BaseChannel):
        channel_id = "web"

        async def stop(self) -> None:
            await harness.async_call("web.stop")

    class _TuiChannel(_BaseChannel):
        channel_id = "tui"

        async def stop(self) -> None:
            await harness.async_call("tui.stop")

    class _InboundGatewayServer:
        def __init__(self, _handler: object) -> None:
            pass

        async def start(self) -> None:
            return None

        async def stop(self) -> None:
            await harness.async_call("inbound.stop")

        async def handle_message(self, _message: object) -> bool:
            return True

    class _GatewayServer:
        def __init__(self, _config: object, _bus: object) -> None:
            self.message_handler_ref: object | None = None

        async def start(self) -> None:
            return None

        async def wait_until_closed(self) -> None:
            await _wait_forever()

        async def stop(self) -> None:
            await harness.async_call("gateway.stop")

        def on_message(self, _callback: object) -> None:
            return None

    class _Config:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

    class _UpdaterService:
        pass

    class _GitWatcherRegistry:
        def set_channel(self, _channel: object) -> None:
            return None

    def start_background_cleanup() -> asyncio.Task[None]:
        async def cleanup_owner() -> None:
            try:
                await _wait_forever()
            except asyncio.CancelledError:
                if harness.test_cleanup_active:
                    harness.calls.append("test.cleanup")
                else:
                    await harness.async_call("restart_cleanup")
                raise

        task = asyncio.create_task(cleanup_owner(), name="shutdown-test-cleanup")
        harness.cleanup_task = task
        return task

    registry_module = importlib.import_module("jiuwenswarm.extensions.registry")
    manager_module = importlib.import_module("jiuwenswarm.extensions.manager")
    message_handler_module = importlib.import_module(
        "jiuwenswarm.gateway.message_handler.message_handler"
    )
    cron_module = importlib.import_module("jiuwenswarm.gateway.cron")
    heartbeat_module = importlib.import_module(
        "jiuwenswarm.gateway.heartbeat.heartbeat"
    )
    channel_manager_module = importlib.import_module(
        "jiuwenswarm.gateway.channel_manager.channel_manager"
    )
    config_module = importlib.import_module("jiuwenswarm.common.config")
    cleanup_module = importlib.import_module("jiuwenswarm.common.cleanup")
    updater_module = importlib.import_module("jiuwenswarm.common.updater")
    web_module = importlib.import_module(
        "jiuwenswarm.gateway.channel_manager.web.web_connect"
    )
    web_handlers_module = importlib.import_module(
        "jiuwenswarm.gateway.channel_manager.web.app_web_handlers"
    )
    tui_module = importlib.import_module(
        "jiuwenswarm.gateway.channel_manager.tui.tui_channel"
    )
    tui_connect_module = importlib.import_module(
        "jiuwenswarm.gateway.channel_manager.tui.tui_connect"
    )
    a2a_module = importlib.import_module(
        "jiuwenswarm.gateway.channel_manager.protocol.a2a.a2a_connect"
    )
    git_watcher_module = importlib.import_module(
        "jiuwenswarm.server.runtime.session.git_diff_watcher"
    )
    proactive_module = importlib.import_module(
        "jiuwenswarm.gateway.cron.proactive_cron_sync"
    )

    monkeypatch.setattr(registry_module, "ExtensionRegistry", _Registry)
    monkeypatch.setattr(manager_module, "ExtensionManager", _ExtensionManager)
    monkeypatch.setattr(message_handler_module, "MessageHandler", _MessageHandler)
    monkeypatch.setattr(cron_module, "CronJobStore", _CronJobStore)
    monkeypatch.setattr(cron_module, "CronSchedulerService", _CronScheduler)
    monkeypatch.setattr(cron_module, "CronController", _CronController)
    monkeypatch.setattr(heartbeat_module, "HeartbeatConfig", _Config)
    monkeypatch.setattr(heartbeat_module, "GatewayHeartbeatService", _HeartbeatService)
    monkeypatch.setattr(channel_manager_module, "ChannelManager", _ChannelManager)
    monkeypatch.setattr(config_module, "get_config", lambda: {"channels": {}})
    monkeypatch.setattr(
        cleanup_module, "start_background_cleanup", start_background_cleanup
    )
    monkeypatch.setattr(updater_module, "UpdaterService", _UpdaterService)
    monkeypatch.setattr(web_module, "WebChannelConfig", _Config)
    monkeypatch.setattr(web_module, "WebChannel", _WebChannel)
    monkeypatch.setattr(
        web_handlers_module, "_register_web_handlers", lambda _params: None
    )
    monkeypatch.setattr(tui_module, "TuiChannelConfig", _Config)
    monkeypatch.setattr(tui_module, "TuiChannel", _TuiChannel)
    monkeypatch.setattr(a2a_module, "A2AChannelConfig", _Config)
    monkeypatch.setattr(a2a_module, "A2AChannel", _A2AChannel)
    monkeypatch.setattr(
        git_watcher_module,
        "get_git_diff_watcher_registry",
        lambda: _GitWatcherRegistry(),
    )

    async def sync_proactive_tick_job(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(
        proactive_module, "sync_proactive_tick_job", sync_proactive_tick_job
    )
    monkeypatch.setattr(
        tui_connect_module,
        "build_cli_route_binding",
        lambda _params: GatewayRouteBinding(path="/tui", channel_id="tui"),
    )
    monkeypatch.setattr(gateway_module, "_InboundGatewayServer", _InboundGatewayServer)
    monkeypatch.setattr(gateway_module, "GatewayServer", _GatewayServer)
    monkeypatch.setattr(
        gateway_module,
        "_build_acp_route_binding",
        lambda **_kwargs: GatewayRouteBinding(path="/acp", channel_id="acp"),
    )

    async def wait_for_shutdown(
        _tasks: list[asyncio.Task[Any]],
        _request: gateway_module.GatewayRestartRequest,
    ) -> bool:
        if harness.wait_failure is not None:
            raise harness.wait_failure
        return harness.restart_requested

    monkeypatch.setattr(
        gateway_module,
        "_wait_for_gateway_tasks_or_restart",
        wait_for_shutdown,
    )
    monkeypatch.setattr(
        gateway_module,
        "_exec_gateway_restart",
        lambda: harness.call("restart.exec"),
    )


async def _run_gateway(
    monkeypatch: pytest.MonkeyPatch,
    harness: _ShutdownHarness,
) -> None:
    _install_gateway_fakes(monkeypatch, harness)
    try:
        await gateway_module._run(
            "ws://shutdown-test.invalid",
            "127.0.0.1",
            19000,
            "/ws",
        )
    finally:
        await harness.cancel_leftover_cleanup()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_phase", _SHUTDOWN_PHASES[5:])
async def test_shutdown_failure_attempts_every_later_owner_once_and_blocks_restart(
    monkeypatch: pytest.MonkeyPatch,
    failure_phase: str,
) -> None:
    failure = RuntimeError(f"{failure_phase} failed")
    harness = _ShutdownHarness(failures={failure_phase: failure})

    with pytest.raises(RuntimeError) as raised:
        await _run_gateway(monkeypatch, harness)

    assert raised.value is failure
    expected = list(_SHUTDOWN_PHASES)
    if failure_phase.startswith("channels.pop."):
        expected.remove(failure_phase.replace("pop.", "") + ".stop")
    assert harness.calls == expected
    assert Counter(harness.calls) == Counter({phase: 1 for phase in expected})
    assert "restart.exec" not in harness.calls


@pytest.mark.asyncio
async def test_first_base_exception_wins_and_later_failures_are_diagnosable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = KeyboardInterrupt("web teardown interrupted")
    later = RuntimeError("heartbeat teardown failed")
    harness = _ShutdownHarness(
        failures={
            "web.stop": first,
            "heartbeat.stop": later,
        }
    )
    diagnostics: list[str] = []
    original_error = gateway_module.logger.error

    def capture_error(message: str, *args: object, **kwargs: object) -> None:
        diagnostics.append(message % args)
        original_error(message, *args, **kwargs)

    monkeypatch.setattr(gateway_module.logger, "error", capture_error)

    with pytest.raises(KeyboardInterrupt) as raised:
        await _run_gateway(monkeypatch, harness)

    assert raised.value is first
    assert harness.calls == list(_SHUTDOWN_PHASES)
    assert "restart.exec" not in harness.calls
    assert any(
        "heartbeat.stop" in message and "heartbeat teardown failed" in message
        for message in diagnostics
    )


@pytest.mark.asyncio
async def test_service_failure_remains_first_while_teardown_still_completes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = RuntimeError("gateway service failed")
    harness = _ShutdownHarness(
        failures={"web.stop": RuntimeError("web stop failed")},
        wait_failure=first,
    )

    with pytest.raises(RuntimeError) as raised:
        await _run_gateway(monkeypatch, harness)

    assert raised.value is first
    assert harness.calls == list(_SHUTDOWN_PHASES)
    assert "restart.exec" not in harness.calls


@pytest.mark.asyncio
@pytest.mark.parametrize("restart_requested", (False, True))
async def test_clean_shutdown_preserves_order_and_restart_boundary(
    monkeypatch: pytest.MonkeyPatch,
    restart_requested: bool,
) -> None:
    harness = _ShutdownHarness(restart_requested=restart_requested)

    await _run_gateway(monkeypatch, harness)

    expected = list(_SHUTDOWN_PHASES)
    if restart_requested:
        expected.append("restart.exec")
    assert harness.calls == expected
    assert Counter(harness.calls) == Counter({phase: 1 for phase in expected})


@pytest.mark.asyncio
async def test_failed_shutdown_does_not_poison_a_clean_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _ShutdownHarness(failures={"web.stop": RuntimeError("web stop failed")})

    with pytest.raises(RuntimeError, match="web stop failed"):
        await _run_gateway(monkeypatch, first)

    assert "restart.exec" not in first.calls

    retry = _ShutdownHarness(restart_requested=True)
    await _run_gateway(monkeypatch, retry)

    assert retry.calls == [*_SHUTDOWN_PHASES, "restart.exec"]
