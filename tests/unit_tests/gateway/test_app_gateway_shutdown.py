from __future__ import annotations

import asyncio
import importlib
import logging
import traceback
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
    "channels.pop.xiaoyi",
    "cron.stop",
    "dispatch.stop",
    "heartbeat.stop",
    "forward.stop",
    "client.disconnect",
    "restart_cleanup",
)

_ENTERPRISE_BOT_KEY = (
    "bot|wss://private.invalid/socket?credential=shutdown-secret|"
    "close_reason=private-close"
)

_AGENT_SERVER_URL = (
    "ws://private-agent.invalid/ws?credential=startup-secret&"
    "close_reason=startup-private-close"
)
_FEISHU_APP_IDS = (
    "feishu-app|credential=private-feishu-one",
    "feishu-app|credential=private-feishu-two",
)
_XIAOYI_API_IDS = (
    "xiaoyi-api|credential=private-xiaoyi-one",
    "xiaoyi-api|credential=private-xiaoyi-two",
)

_ALL_OWNER_SHUTDOWN_PHASES = (
    "prewarm.debounce_task",
    "prewarm.periodic_task",
    "a2a.task",
    "a2a.stop",
    "a2a.unregister",
    "gateway.task",
    "gateway.stop",
    "inbound.stop",
    "tui.stop",
    "web.task",
    "web.stop",
    "feishu.enterprise.task",
    "feishu.enterprise.stop",
    "channels.pop.feishu",
    "channels.feishu.task",
    "channels.feishu.stop",
    "channels.pop.xiaoyi",
    "channels.xiaoyi.task",
    "channels.xiaoyi.stop",
    "dingtalk.task",
    "dingtalk.stop",
    "telegram.task",
    "telegram.stop",
    "discord.task",
    "discord.stop",
    "slack.task",
    "slack.stop",
    "whatsapp.task",
    "whatsapp.stop",
    "wecom.task",
    "wecom.stop",
    "wechat.task",
    "wechat.stop",
    "ssh.task",
    "ssh.stop",
    "ssh.clear_key_issuer",
    "cron.stop",
    "dispatch.stop",
    "heartbeat.stop",
    "forward.stop",
    "client.disconnect",
    "restart_cleanup",
)

_ALL_OWNER_EXPECTED_CALLS = (
    *_ALL_OWNER_SHUTDOWN_PHASES[:16],
    "channels.feishu.task",
    "channels.feishu.stop",
    *_ALL_OWNER_SHUTDOWN_PHASES[16:19],
    "channels.xiaoyi.task",
    "channels.xiaoyi.stop",
    *_ALL_OWNER_SHUTDOWN_PHASES[19:],
)


class _ShutdownHarness:
    def __init__(
        self,
        *,
        failures: dict[str, BaseException] | None = None,
        restart_requested: bool = True,
        wait_failure: BaseException | None = None,
        enable_all_owners: bool = False,
        enterprise_bot_key: str = _ENTERPRISE_BOT_KEY,
        agent_server_url: str = _AGENT_SERVER_URL,
        cancel_barrier_phase: str | None = None,
    ) -> None:
        self.failures = dict(failures or {})
        self.restart_requested = restart_requested
        self.wait_failure = wait_failure
        self.enable_all_owners = enable_all_owners
        self.enterprise_bot_key = enterprise_bot_key
        self.agent_server_url = agent_server_url
        self.cancel_barrier_phase = cancel_barrier_phase
        self.calls: list[str] = []
        self.issuer_values: list[object | None] = []
        self.shutdown_started = False
        self.cleanup_task: asyncio.Task[None] | None = None
        self.test_cleanup_active = False
        self.cancel_barrier_started = asyncio.Event()
        self.release_cancel_barrier = asyncio.Event()
        self.observed_caller_cancellations: list[asyncio.CancelledError] = []
        self.registered_channels: dict[str, list[object]] = {
            "feishu": [],
            "xiaoyi": [],
        }
        self.popped_channels: dict[str, list[object]] = {
            "feishu": [],
            "xiaoyi": [],
        }
        self.stopped_channels: list[object] = []
        self.channel_manager: object | None = None

    def call(self, phase: str) -> None:
        self.calls.append(phase)
        failure = self.failures.get(phase)
        if failure is not None:
            raise failure

    async def async_call(self, phase: str) -> None:
        self.call(phase)

    async def cancel_leftover_cleanup(self) -> None:
        task = self.cleanup_task
        if task is not None and not task.done():
            self.test_cleanup_active = True
            try:
                task.cancel()
                try:
                    await task
                except BaseException:
                    pass
            finally:
                self.test_cleanup_active = False

        for channels in self.registered_channels.values():
            for channel in channels:
                task = getattr(channel, "start_task", None)
                if task is None or task.done():
                    continue
                task.cancel()
                try:
                    await task
                except BaseException:
                    pass

    async def owned_task(self, phase: str) -> None:
        try:
            await _wait_forever()
        except asyncio.CancelledError:
            if self.cancel_barrier_phase == phase:
                self.cancel_barrier_started.set()
                while not self.release_cancel_barrier.is_set():
                    try:
                        await self.release_cancel_barrier.wait()
                    except asyncio.CancelledError:
                        continue
            raise


async def _wait_forever() -> None:
    await asyncio.Event().wait()


def _all_owner_config(bot_key: str) -> dict[str, object]:
    return {
        "gateway": {"agent_client": {"type": "agentos_router"}},
        "channels": {
            "feishu": {
                "apps": [
                    {
                        "enabled": True,
                        "app_id": app_id,
                        "app_secret": f"private-feishu-secret-{index}",
                    }
                    for index, app_id in enumerate(_FEISHU_APP_IDS)
                ]
            },
            "feishu_enterprise": {
                bot_key: {
                    "enabled": True,
                    "app_id": "enterprise-app",
                    "app_secret": "enterprise-secret",
                }
            },
            "xiaoyi": {
                "apps": [
                    {
                        "enabled": True,
                        "ak": f"private-xiaoyi-ak-{index}",
                        "sk": f"private-xiaoyi-sk-{index}",
                        "agent_id": f"private-xiaoyi-agent-{index}",
                        "api_id": api_id,
                    }
                    for index, api_id in enumerate(_XIAOYI_API_IDS)
                ]
            },
            "dingtalk": {
                "enabled": True,
                "client_id": "dingtalk-client",
                "client_secret": "dingtalk-secret",
            },
            "telegram": {"enabled": True, "bot_token": "telegram-secret"},
            "discord": {"enabled": True, "bot_token": "discord-secret"},
            "slack": {
                "enabled": True,
                "bot_token": "slack-bot-secret",
                "app_token": "slack-app-secret",
            },
            "whatsapp": {
                "enabled": True,
                "bridge_ws_url": "ws://private.invalid/whatsapp",
            },
            "wecom": {
                "enabled": True,
                "bot_id": "wecom-bot",
                "secret": "wecom-secret",
            },
            "wechat": {
                "enabled": True,
                "bot_token": "wechat-secret",
                "credential_file": "private-credential-file",
            },
            "ssh": {
                "enabled": True,
                "listen_port": 2222,
                "auth": {"enabled": True, "ephemeral_key_ttl_sec": 30.0},
            },
        },
    }


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

    class _AgentServerExtension:
        metadata = SimpleNamespace(name="shutdown-test-client")

        @staticmethod
        def get_client() -> _Client:
            return client

        @staticmethod
        def set_key_issuer(
            issuer: object | None,
            *,
            ephemeral_key_ttl_sec: float,
        ) -> None:
            assert ephemeral_key_ttl_sec > 0
            harness.issuer_values.append(issuer)
            if harness.shutdown_started:
                harness.call("ssh.clear_key_issuer")

    agent_server_extension = _AgentServerExtension()

    class _Registry:
        @classmethod
        def create_instance(cls, **_kwargs: object) -> _Registry:
            return cls()

        def get_agent_server_client_extension(self) -> object:
            return agent_server_extension

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

    class _ChannelManager:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            self.enabled_channels: set[str] = set()
            self._config_callback: Any = None
            self._registered: dict[str, list[object]] = {}
            harness.channel_manager = self

        def set_config_callback(self, callback: object) -> None:
            self._config_callback = callback

        async def set_config(self, config: object) -> None:
            if harness.enable_all_owners:
                assert isinstance(config, dict)
                assert self._config_callback is not None
                await self._config_callback(dict(config))

        @staticmethod
        def pop_channel_restart_pending() -> set[str]:
            return set()

        async def start_dispatch(self) -> None:
            return None

        async def stop_dispatch(self) -> None:
            await harness.async_call("dispatch.stop")

        def register_channel(self, channel: object) -> None:
            channel_id = str(getattr(channel, "channel_id", ""))
            self._registered.setdefault(channel_id, []).append(channel)
            if channel_id in harness.registered_channels:
                harness.registered_channels[channel_id].append(channel)

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
            if harness.shutdown_started:
                harness.call(f"channels.pop.{channel_id}")
            channels = self._registered.pop(channel_id, [])
            if channel_id in harness.popped_channels:
                harness.popped_channels[channel_id].extend(channels)
            return channels

    class _BaseChannel:
        channel_id = "unused"
        task_phase = "unused.task"

        def __init__(self, *args: object, **_kwargs: object) -> None:
            self.config = args[0] if args else None
            self.start_task: asyncio.Task[None] | None = None

        async def start(self) -> None:
            await harness.owned_task(self.task_phase)

    def _configured_channel_type(
        channel_id: str,
        shutdown_phase: str | None = None,
    ) -> type[_BaseChannel]:
        class _ConfiguredChannel(_BaseChannel):
            def __init__(self, *_args: object, **_kwargs: object) -> None:
                self.channel_id = channel_id
                self.task_phase = f"{channel_id}.task"
                self.key_issuer = object()

            async def stop(self) -> None:
                await harness.async_call(shutdown_phase or f"{channel_id}.stop")

        return _ConfiguredChannel

    class _FeishuChannel(_BaseChannel):
        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args, **kwargs)
            configured_id = str(getattr(self.config, "channel_id", "feishu"))
            self.channel_id = configured_id
            self.enterprise = configured_id.startswith("feishu_enterprise:")
            self.task_phase = (
                "feishu.enterprise.task" if self.enterprise else "channels.feishu.task"
            )

        async def stop(self) -> None:
            if not self.enterprise:
                harness.stopped_channels.append(self)
            await harness.async_call(
                "feishu.enterprise.stop" if self.enterprise else "channels.feishu.stop"
            )

    class _XiaoyiChannel(_BaseChannel):
        channel_id = "xiaoyi"
        task_phase = "channels.xiaoyi.task"

        async def stop(self) -> None:
            harness.stopped_channels.append(self)
            await harness.async_call("channels.xiaoyi.stop")

    class _A2AChannel(_BaseChannel):
        channel_id = "a2a"

        async def stop(self) -> None:
            await harness.async_call("a2a.stop")

    class _WebChannel(_BaseChannel):
        channel_id = "web"
        task_phase = "web.task"

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
            for key, value in _kwargs.items():
                setattr(self, key, value)

    class _SshConfig(_Config):
        @classmethod
        def from_dict(cls, config: dict[str, object]) -> _SshConfig:
            auth_raw = config.get("auth")
            auth = auth_raw if isinstance(auth_raw, dict) else {}
            return cls(
                listen_host="127.0.0.1",
                listen_port=int(config["listen_port"]),
                auth=SimpleNamespace(
                    enabled=bool(auth.get("enabled", False)),
                    ephemeral_key_ttl_sec=float(
                        auth.get("ephemeral_key_ttl_sec", 300.0)
                    ),
                ),
            )

    class _KeyRegistry:
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
                if harness.cancel_barrier_phase == "restart_cleanup":
                    harness.cancel_barrier_started.set()
                    while not harness.release_cancel_barrier.is_set():
                        try:
                            await harness.release_cancel_barrier.wait()
                        except asyncio.CancelledError:
                            continue
                if harness.test_cleanup_active:
                    harness.calls.append("test.cleanup")
                elif not harness.enable_all_owners:
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
    feishu_module = importlib.import_module(
        "jiuwenswarm.gateway.channel_manager.im_platforms.feishu.feishu_connect"
    )
    xiaoyi_module = importlib.import_module(
        "jiuwenswarm.gateway.channel_manager.im_platforms.xiaoyi.xiaoyi_connect"
    )
    dingtalk_module = importlib.import_module(
        "jiuwenswarm.gateway.channel_manager.im_platforms.dingtalk.dingtalk_connect"
    )
    telegram_module = importlib.import_module(
        "jiuwenswarm.gateway.channel_manager.im_platforms.telegram.telegram_connect"
    )
    discord_module = importlib.import_module(
        "jiuwenswarm.gateway.channel_manager.im_platforms.discord.discord_connect"
    )
    slack_module = importlib.import_module(
        "jiuwenswarm.gateway.channel_manager.im_platforms.slack.slack_connect"
    )
    whatsapp_module = importlib.import_module(
        "jiuwenswarm.gateway.channel_manager.im_platforms.whatsapp.whatsapp_connect"
    )
    wecom_module = importlib.import_module(
        "jiuwenswarm.gateway.channel_manager.im_platforms.wecom.wecom_connect"
    )
    wechat_module = importlib.import_module(
        "jiuwenswarm.gateway.channel_manager.im_platforms.wechat.wechat_connect"
    )
    ssh_module = importlib.import_module(
        "jiuwenswarm.gateway.channel_manager.protocol.ssh.ssh_connect"
    )
    ssh_registry_module = importlib.import_module(
        "jiuwenswarm.extensions.agentos.auth.ssh_key_registry"
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
    full_config = (
        _all_owner_config(harness.enterprise_bot_key)
        if harness.enable_all_owners
        else {"channels": {}}
    )
    monkeypatch.setattr(config_module, "get_config", lambda: full_config)
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
    configured_channels = {
        feishu_module: (
            "FeishuChannel",
            "FeishuConfig",
            _FeishuChannel,
            _Config,
        ),
        xiaoyi_module: (
            "XiaoyiChannel",
            "XiaoyiChannelConfig",
            _XiaoyiChannel,
            _Config,
        ),
        dingtalk_module: (
            "DingTalkChannel",
            "DingTalkConfig",
            _configured_channel_type("dingtalk"),
            _Config,
        ),
        telegram_module: (
            "TelegramChannel",
            "TelegramChannelConfig",
            _configured_channel_type("telegram"),
            _Config,
        ),
        discord_module: (
            "DiscordChannel",
            "DiscordChannelConfig",
            _configured_channel_type("discord"),
            _Config,
        ),
        slack_module: (
            "SlackChannel",
            "SlackChannelConfig",
            _configured_channel_type("slack"),
            _Config,
        ),
        whatsapp_module: (
            "WhatsAppChannel",
            "WhatsAppChannelConfig",
            _configured_channel_type("whatsapp"),
            _Config,
        ),
        wecom_module: (
            "WecomChannel",
            "WecomConfig",
            _configured_channel_type("wecom"),
            _Config,
        ),
        wechat_module: (
            "WechatChannel",
            "WechatConfig",
            _configured_channel_type("wechat"),
            _Config,
        ),
        ssh_module: (
            "SshChannel",
            "SshChannelConfig",
            _configured_channel_type("ssh"),
            _SshConfig,
        ),
    }
    for module, (
        channel_name,
        config_name,
        channel_type,
        config_type,
    ) in configured_channels.items():
        monkeypatch.setattr(module, channel_name, channel_type)
        monkeypatch.setattr(module, config_name, config_type)
    monkeypatch.setattr(ssh_registry_module, "KeyRegistry", _KeyRegistry)
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

    if harness.enable_all_owners:
        original_cancel_gateway_owned_task = gateway_module._cancel_gateway_owned_task
        task_phases = {
            "agent-prewarm-sync-after-startup": "prewarm.debounce_task",
            "agent-prewarm-periodic-sync": "prewarm.periodic_task",
            "a2a-channel": "a2a.task",
            "acp-gateway-server": "gateway.task",
            "web-channel": "web.task",
            "dingtalk": "dingtalk.task",
            "telegram": "telegram.task",
            "discord": "discord.task",
            "slack": "slack.task",
            "whatsapp": "whatsapp.task",
            "wecom": "wecom.task",
            "wechat": "wechat.task",
            "ssh": "ssh.task",
            "shutdown-test-cleanup": "restart_cleanup",
        }

        async def record_cancel_gateway_owned_task(
            task: asyncio.Task[Any],
            *,
            suppress_type_error: bool = False,
        ) -> None:
            task_name = task.get_name()
            if task_name.startswith("feishu-enterprise-"):
                phase = "feishu.enterprise.task"
            elif task_name.startswith("feishu-"):
                phase = "channels.feishu.task"
            elif task_name.startswith("xiaoyi-"):
                phase = "channels.xiaoyi.task"
            else:
                phase = task_phases[task_name]
            try:
                await original_cancel_gateway_owned_task(
                    task,
                    suppress_type_error=suppress_type_error,
                )
            except asyncio.CancelledError as exc:
                exc.add_note("private-caller-cancellation-note")
                harness.calls.append(phase)
                harness.observed_caller_cancellations.append(exc)
                raise
            harness.call(phase)

        monkeypatch.setattr(
            gateway_module,
            "_cancel_gateway_owned_task",
            record_cancel_gateway_owned_task,
        )

    async def wait_for_shutdown(
        _tasks: list[asyncio.Task[Any]],
        _request: gateway_module.GatewayRestartRequest,
    ) -> bool:
        harness.shutdown_started = True
        await asyncio.sleep(0)
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
            harness.agent_server_url,
            "127.0.0.1",
            19000,
            "/ws",
        )
    finally:
        await harness.cancel_leftover_cleanup()


def _assert_safe_public_failure(
    failure: BaseException,
    *,
    expected_type: type[BaseException],
    phase: str,
    category: str,
) -> None:
    message = f"Gateway shutdown failed (phase={phase}, failure={category})"
    assert type(failure) is expected_type
    assert failure.args == (message,)
    assert str(failure) == message
    assert failure.__cause__ is None
    assert failure.__context__ is None


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

    _assert_safe_public_failure(
        raised.value,
        expected_type=RuntimeError,
        phase=failure_phase,
        category="runtime_error",
    )
    expected = list(_SHUTDOWN_PHASES)
    assert harness.calls == expected
    assert Counter(harness.calls) == Counter(expected)
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

    _assert_safe_public_failure(
        raised.value,
        expected_type=KeyboardInterrupt,
        phase="web.stop",
        category="interrupt",
    )
    assert harness.calls == list(_SHUTDOWN_PHASES)
    assert "restart.exec" not in harness.calls
    assert any(
        "phase=heartbeat.stop" in message and "failure=runtime_error" in message
        for message in diagnostics
    )
    assert all("heartbeat teardown failed" not in message for message in diagnostics)


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

    _assert_safe_public_failure(
        raised.value,
        expected_type=RuntimeError,
        phase="service.wait",
        category="runtime_error",
    )
    assert harness.calls == list(_SHUTDOWN_PHASES)
    assert "restart.exec" not in harness.calls


@pytest.mark.asyncio
async def test_cancelled_service_task_is_safe_failure_not_caller_cancellation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = "private-service-task-cancellation"
    raw_failure = asyncio.CancelledError(marker)
    harness = _ShutdownHarness(wait_failure=raw_failure)

    with pytest.raises(gateway_module._GatewayShutdownError) as raised:
        await _run_gateway(monkeypatch, harness)

    assert raised.value is not raw_failure
    _assert_safe_public_failure(
        raised.value,
        expected_type=gateway_module._GatewayShutdownError,
        phase="service.wait",
        category="cancelled",
    )
    assert marker not in "".join(
        traceback.format_exception(
            type(raised.value),
            raised.value,
            raised.value.__traceback__,
        )
    )
    assert harness.calls == list(_SHUTDOWN_PHASES)
    assert "restart.exec" not in harness.calls


@pytest.mark.asyncio
async def test_restart_pending_service_failure_log_is_content_free(
    caplog: pytest.LogCaptureFixture,
) -> None:
    marker = "private-restart-pending-service-failure"

    async def fail_service() -> None:
        raise RuntimeError(marker)

    service_task = asyncio.create_task(fail_service())
    restart_request = gateway_module.GatewayRestartRequest(requested=True)

    gateway_module.logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.WARNING):
            assert await gateway_module._wait_for_gateway_tasks_or_restart(
                [service_task],
                restart_request,
            )
    finally:
        gateway_module.logger.removeHandler(caplog.handler)

    assert marker not in caplog.text
    assert any(
        "failure=runtime_error" in record.getMessage() for record in caplog.records
    )


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
    assert Counter(harness.calls) == Counter(expected)


@pytest.mark.asyncio
async def test_failed_shutdown_does_not_poison_a_clean_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _ShutdownHarness(failures={"web.stop": RuntimeError("web stop failed")})

    with pytest.raises(RuntimeError) as raised:
        await _run_gateway(monkeypatch, first)

    _assert_safe_public_failure(
        raised.value,
        expected_type=RuntimeError,
        phase="web.stop",
        category="runtime_error",
    )

    assert "restart.exec" not in first.calls

    retry = _ShutdownHarness(restart_requested=True)
    await _run_gateway(monkeypatch, retry)

    assert retry.calls == [*_SHUTDOWN_PHASES, "restart.exec"]


def _all_owner_expected_calls(failure_phase: str | None = None) -> list[str]:
    expected = list(_ALL_OWNER_EXPECTED_CALLS)
    if failure_phase == "channels.pop.feishu":
        expected = [
            phase for phase in expected if not phase.startswith("channels.feishu.")
        ]
    elif failure_phase == "channels.pop.xiaoyi":
        expected = [
            phase for phase in expected if not phase.startswith("channels.xiaoyi.")
        ]
    return expected


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_phase", _ALL_OWNER_SHUTDOWN_PHASES)
async def test_real_run_attempts_every_enabled_owner_after_each_phase_failure(
    monkeypatch: pytest.MonkeyPatch,
    failure_phase: str,
) -> None:
    failure = RuntimeError("private shutdown failure")
    harness = _ShutdownHarness(
        failures={failure_phase: failure},
        enable_all_owners=True,
    )

    with pytest.raises(RuntimeError) as raised:
        await _run_gateway(monkeypatch, harness)

    _assert_safe_public_failure(
        raised.value,
        expected_type=RuntimeError,
        phase=failure_phase,
        category="runtime_error",
    )
    expected = _all_owner_expected_calls(failure_phase)
    assert harness.calls == expected
    assert Counter(harness.calls) == Counter(expected)
    assert "restart.exec" not in harness.calls


@pytest.mark.asyncio
async def test_real_run_clean_shutdown_covers_optional_tasks_stops_and_ssh_issuer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _ShutdownHarness(enable_all_owners=True)

    await _run_gateway(monkeypatch, harness)

    expected = [*_ALL_OWNER_EXPECTED_CALLS, "restart.exec"]
    assert harness.calls == expected
    assert Counter(harness.calls) == Counter(expected)
    expected_dynamic = [
        *harness.registered_channels["feishu"],
        *harness.registered_channels["xiaoyi"],
    ]
    assert len(harness.registered_channels["feishu"]) == len(_FEISHU_APP_IDS)
    assert len(harness.registered_channels["xiaoyi"]) == len(_XIAOYI_API_IDS)
    assert harness.popped_channels == harness.registered_channels
    assert harness.stopped_channels == expected_dynamic
    assert Counter(map(id, harness.stopped_channels)) == Counter(
        {id(channel): 1 for channel in expected_dynamic}
    )
    assert all(getattr(channel, "start_task").done() for channel in expected_dynamic)
    task_names = [
        getattr(channel, "start_task").get_name() for channel in expected_dynamic
    ]
    assert len(set(task_names)) == len(expected_dynamic)
    assert all(
        marker not in task_name
        for marker in (*_FEISHU_APP_IDS, *_XIAOYI_API_IDS)
        for task_name in task_names
    )
    assert len(harness.issuer_values) == 3
    assert harness.issuer_values[0] is None
    assert harness.issuer_values[1] is not None
    assert harness.issuer_values[2] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("barrier_phase", ("web.task", "restart_cleanup"))
async def test_caller_cancellation_settles_owned_task_and_blocks_restart(
    monkeypatch: pytest.MonkeyPatch,
    barrier_phase: str,
) -> None:
    cancel_marker = "private-caller-cancellation"
    harness = _ShutdownHarness(
        enable_all_owners=True,
        cancel_barrier_phase=barrier_phase,
    )
    _install_gateway_fakes(monkeypatch, harness)
    runner = asyncio.create_task(
        gateway_module._run(
            harness.agent_server_url,
            "127.0.0.1",
            19000,
            "/ws",
        ),
        name=f"gateway-caller-cancel-{barrier_phase}",
    )
    raised_cancellation: asyncio.CancelledError | None = None
    settled_before_release = True
    try:
        await asyncio.wait_for(harness.cancel_barrier_started.wait(), timeout=2)
        assert runner.done() is False
        runner.cancel(cancel_marker)
        await asyncio.sleep(0)
        settled_before_release = runner.done()
        harness.release_cancel_barrier.set()
        try:
            await runner
        except asyncio.CancelledError as exc:
            raised_cancellation = exc
    finally:
        harness.release_cancel_barrier.set()
        if not runner.done():
            runner.cancel()
            try:
                await runner
            except BaseException:
                pass
        await harness.cancel_leftover_cleanup()

    assert settled_before_release is False
    assert raised_cancellation is not None
    assert runner.cancelling() == 1
    assert len(harness.observed_caller_cancellations) == 1
    assert raised_cancellation is harness.observed_caller_cancellations[0]
    assert raised_cancellation.args == ()
    assert raised_cancellation.__cause__ is None
    assert raised_cancellation.__context__ is None
    assert raised_cancellation.__notes__ == []
    assert "private-caller-cancellation-note" not in "".join(
        traceback.format_exception(
            type(raised_cancellation),
            raised_cancellation,
            raised_cancellation.__traceback__,
        )
    )
    assert cancel_marker not in "".join(
        traceback.format_exception(
            type(raised_cancellation),
            raised_cancellation,
            raised_cancellation.__traceback__,
        )
    )
    assert harness.calls == list(_ALL_OWNER_EXPECTED_CALLS)
    assert Counter(harness.calls) == Counter(_ALL_OWNER_EXPECTED_CALLS)
    assert "restart.exec" not in harness.calls


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("raw_failure", "expected_type", "category"),
    (
        (TimeoutError("private-supported-timeout"), TimeoutError, "timeout"),
        (OSError("private-supported-io"), OSError, "io_error"),
        (ValueError("private-supported-value"), ValueError, "exception"),
        (TypeError("private-supported-type"), TypeError, "exception"),
        (SystemExit("private-supported-exit"), SystemExit, "interrupt"),
        (GeneratorExit("private-supported-generator"), GeneratorExit, "interrupt"),
        (
            asyncio.CancelledError("private-owned-cancellation"),
            gateway_module._GatewayShutdownError,
            "cancelled",
        ),
    ),
)
async def test_supported_shutdown_exception_family_is_safe_and_diagnosable(
    monkeypatch: pytest.MonkeyPatch,
    raw_failure: BaseException,
    expected_type: type[BaseException],
    category: str,
) -> None:
    harness = _ShutdownHarness(failures={"heartbeat.stop": raw_failure})
    public_failure: BaseException | None = None

    try:
        await _run_gateway(monkeypatch, harness)
    except BaseException as exc:
        public_failure = exc

    assert public_failure is not None
    assert public_failure is not raw_failure
    _assert_safe_public_failure(
        public_failure,
        expected_type=expected_type,
        phase="heartbeat.stop",
        category=category,
    )
    rendered = "".join(
        traceback.format_exception(
            type(public_failure),
            public_failure,
            public_failure.__traceback__,
        )
    )
    assert "private-supported" not in rendered
    assert "private-owned-cancellation" not in rendered
    assert "restart.exec" not in harness.calls


@pytest.mark.asyncio
async def test_unknown_hostile_shutdown_exception_uses_safe_wrapper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = "private-unknown-base-exception"

    class _UnknownHostileFailure(BaseException):
        def __str__(self) -> str:
            return marker

        def __repr__(self) -> str:
            return f"UnknownHostileFailure({marker})"

    raw_failure = _UnknownHostileFailure()
    harness = _ShutdownHarness(failures={"heartbeat.stop": raw_failure})
    public_failure: BaseException | None = None

    try:
        await _run_gateway(monkeypatch, harness)
    except BaseException as exc:
        public_failure = exc

    assert public_failure is not None
    assert public_failure is not raw_failure
    assert type(public_failure).__name__ == "_GatewayShutdownError"
    _assert_safe_public_failure(
        public_failure,
        expected_type=type(public_failure),
        phase="heartbeat.stop",
        category="base_exception",
    )
    assert marker not in "".join(
        traceback.format_exception(
            type(public_failure),
            public_failure,
            public_failure.__traceback__,
        )
    )
    assert "restart.exec" not in harness.calls


@pytest.mark.asyncio
async def test_real_run_public_failure_and_all_logs_are_content_free(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret_uri = "wss://private.invalid/socket?token=shutdown-secret"
    credential = "Bearer private-credential"
    close_reason = "private-close-reason"
    traceback_marker = "private-traceback-marker"

    class _SensitiveShutdownError(RuntimeError):
        def __str__(self) -> str:
            return f"{secret_uri} {credential} {close_reason} {traceback_marker}"

        def __repr__(self) -> str:
            return f"SensitiveShutdownError({traceback_marker})"

    failure = _SensitiveShutdownError()
    harness = _ShutdownHarness(
        failures={"feishu.enterprise.stop": failure},
        enable_all_owners=True,
    )
    public_failure: BaseException | None = None
    formatted_failure = ""
    caller_logger = logging.getLogger("test.gateway.shutdown.caller")

    gateway_module.logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.INFO):
            try:
                await _run_gateway(monkeypatch, harness)
            except RuntimeError as exc:
                public_failure = exc
                formatted_failure = "".join(
                    traceback.format_exception(type(exc), exc, exc.__traceback__)
                )
                caller_logger.exception("caller observed Gateway shutdown failure")
    finally:
        gateway_module.logger.removeHandler(caplog.handler)

    assert public_failure is not None
    assert public_failure is not failure
    _assert_safe_public_failure(
        public_failure,
        expected_type=RuntimeError,
        phase="feishu.enterprise.stop",
        category="runtime_error",
    )
    rendered = [record.getMessage() for record in caplog.records]
    assert any(
        "phase=feishu.enterprise.stop" in message and "failure=runtime_error" in message
        for message in rendered
    )
    forbidden = (
        harness.enterprise_bot_key,
        harness.agent_server_url,
        *_FEISHU_APP_IDS,
        *_XIAOYI_API_IDS,
        "startup-secret",
        secret_uri,
        credential,
        close_reason,
        traceback_marker,
    )
    assert all(marker not in caplog.text for marker in forbidden)
    assert all(marker not in formatted_failure for marker in forbidden)
    assert all(marker not in message for marker in forbidden for message in rendered)
    assert all(arg is not failure for record in caplog.records for arg in record.args)
    assert all(
        marker not in repr(record.args)
        for marker in forbidden
        for record in caplog.records
    )
    assert "restart.exec" not in harness.calls
