"""The gateway's side of co-scribe: build the connections, run the service, stop it.

Every configuration check lives in ``build_connections`` because **a startup
failure must be loud**: the configurable strings must not collide, the
credentials must be readable, the document ids must parse. Discovered at run time
instead, the same problems show up as a watcher failing every 30 seconds with the
real reason buried in a log, while all the user sees is that mentioning the agent
does nothing. It deliberately runs **no admission checks** -- can we edit, is the
document link-shared -- because those need the network, and putting them on the
startup path would stop the gateway from coming up. The watcher does them on its
first tick.

The service is **not gated on ``enabled`` or on having connections.** The panel
is the only way to add the first connection, and a missing registry makes every
clouddoc RPC answer "feature off", so a fresh install could never be configured
from the UI at all. Whether to *poll* is still gated, in
``CloudDocConnections.start_all``.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from typing import Any

from jiuwenswarm.clouddoc.settings import deployment_config

logger = logging.getLogger(__name__)


def start_discovery(panel: Any) -> asyncio.Task | None:
    """Start the periodic adoption of newly shared documents, or return None.

    Adoption is gated by the same admission rules whatever triggers it; this is the
    trigger that does not depend on anyone opening the Docs panel, so a deployment
    driven from a chat channel still manages what is shared with it. Returns the
    task so the caller owns its lifetime; None when the panel is absent or the
    deployment turned discovery off.
    """
    if panel is None:
        return None
    from jiuwenswarm.clouddoc.panel.service import (
        DISCOVERY_INTERVAL_SECONDS,
        discover_shared_periodically,
    )

    cfg = deployment_config().get("clouddoc") or {}
    if not bool(cfg.get("auto_discover_shared", True)):
        logger.info("[clouddoc] periodic discovery of shared documents is off by configuration")
        return None
    try:
        interval = float(cfg.get("discover_interval_seconds") or DISCOVERY_INTERVAL_SECONDS)
    except (TypeError, ValueError):
        logger.warning(
            "[clouddoc] discover_interval_seconds is invalid, using the default %s",
            DISCOVERY_INTERVAL_SECONDS,
        )
        interval = DISCOVERY_INTERVAL_SECONDS
    # A round costs a full listing per connection. Too short a period spends the
    # connection's shared quota on discovery that the comment poll then cannot make.
    interval = max(interval, 60.0)
    task = asyncio.create_task(
        discover_shared_periodically(panel, interval_seconds=interval),
        name="clouddoc-discovery",
    )
    logger.info("[clouddoc] periodic discovery started, every %.0f seconds", interval)
    return task


async def build_connections(*, agent_client: Any) -> Any | None:
    """The connection registry built from the configuration, or None when the
    co-scribe extras are absent or the trigger words collide.

    Built one connection at a time: a broken one -- a corrupt key, an unparseable
    document id -- skips only itself and does not take the others down with it.
    An empty registry is still returned; it is exactly what a first run looks like,
    and the panel needs it to accept the first key.
    """
    cfg = deployment_config().get("clouddoc") or {}
    enabled = bool(cfg.get("enabled"))

    from jiuwenswarm.clouddoc.panel.connections import CloudDocConnections
    from jiuwenswarm.clouddoc.providers.base import read_connection_specs

    specs = read_connection_specs(cfg)

    try:
        from jiuwenswarm.clouddoc.authority.watch_registry import (
            DEFAULT_DISPATCH_RATE_MAX,
            DEFAULT_DISPATCH_RATE_WINDOW_SECONDS,
            WatchRegistry,
        )
        from jiuwenswarm.clouddoc.providers.factory import build_provider
        from jiuwenswarm.clouddoc.state.store import CloudDocStore
        from jiuwenswarm.clouddoc.watch.dispatch import CloudDocDispatcher, make_cancel_fn
        from jiuwenswarm.clouddoc.watch.triggers import TriggerConfig, validate_prefixes
        from jiuwenswarm.clouddoc.watch.watcher import WatcherConfig
    except ImportError as exc:
        logger.warning("[clouddoc] extras not installed (%s); pip install 'jiuwenswarm[clouddoc]'", exc)
        return None

    watcher_cfg = WatcherConfig(
        poll_interval_seconds=float(cfg.get("poll_interval_seconds", 30)),
        turn_timeout_seconds=float(cfg.get("turn_timeout_seconds", 540)),
        workmode_file=str(cfg.get("workmode_file") or ""),
    )
    base_trigger = TriggerConfig(
        sa_address="",  # differs per connection; registry.add derives it from the key
        conventions_marker=str(cfg.get("conventions_marker", "co-scribe 约定")),
    )
    try:
        validate_prefixes(base_trigger)
    except ValueError as exc:
        # A prefix collision makes a conventions comment read as a trigger, or the
        # reverse. Starting with it is worse than not starting: not starting is at
        # least visible.
        logger.error("[clouddoc] trigger words are invalid, the feature did not start: %s", exc)
        return None

    store = CloudDocStore()
    dispatcher = CloudDocDispatcher(
        agent_client, store, watcher_cfg, now_fn=time.time,
        session_max_turns=int(cfg.get("session_max_turns", 50)),
        cancel_fn=make_cancel_fn(agent_client, now_fn=time.time),
    )
    watch_registry = WatchRegistry(
        rate_max=int(cfg.get("dispatch_rate_max", DEFAULT_DISPATCH_RATE_MAX)),
        rate_window_seconds=float(
            cfg.get("dispatch_rate_window_seconds", DEFAULT_DISPATCH_RATE_WINDOW_SECONDS)
        ),
    )
    roster = tuple(str(x) for x in (cfg.get("agent_roster") or []))
    registry = CloudDocConnections(
        store=store, dispatcher=dispatcher, watcher_cfg=watcher_cfg,
        watch_registry=watch_registry,
        base_trigger_cfg=base_trigger,
        # The roster is deployment policy read here and handed into the host-free
        # factory as a plain argument.
        provider_factory=lambda cf: build_provider(cf, agent_roster=roster),
        now_fn=time.time,
        enabled=enabled,
    )
    registry.auto_watch_policy = str(cfg.get("auto_watch_on_adopt") or "off")
    for spec in specs:
        try:
            probe = build_provider(spec["credentials_file"])
            doc_ids = [probe.parse_doc_ref(d) for d in spec["documents"]]
            await registry.add(spec["credentials_file"], doc_ids)
        except Exception as exc:  # noqa: BLE001 - one bad connection must not block startup
            logger.error("[clouddoc] connection failed to build (%s), skipped: %s", spec["credentials_file"], exc)
    if not registry.list():
        logger.info("[clouddoc] no usable connection yet; the panel can add one")
    return registry


class CloudDocService:
    """What the gateway holds for co-scribe: the connections, the panel, discovery.

    Two steps on the way up, because the gateway binds the panel to its web
    handlers before it starts polling: ``prepare`` builds the connections and the
    panel, ``start`` starts the watchers and discovery. ``stop`` undoes both.
    """

    def __init__(self) -> None:
        self.connections: Any | None = None
        self.panel: Any | None = None
        self._discovery: asyncio.Task | None = None

    async def prepare(self, *, agent_client: Any) -> None:
        """Build the connections from the configuration and the panel over them."""
        self.connections = await build_connections(agent_client=agent_client)
        if self.connections is None:
            return
        from jiuwenswarm.clouddoc.panel.service import CloudDocPanel

        self.panel = CloudDocPanel(self.connections)
        # A document dropped for a withdrawn format leaves the adoption list here,
        # not just this process's memory -- otherwise the next start adopts it
        # again. Nothing is written on an ordinary start.
        retired = self.panel.commit_retirements()
        if retired:
            logger.info(
                "[clouddoc] removed %d retired document(s) from the adoption list: %s",
                len(retired), ", ".join(x[:12] + "…" for x in retired),
            )

    async def start(self) -> None:
        """Start the watchers and discovery. Discovery starts whatever the connection
        count is: the loop reads the connection list on every pass, so starting it
        early costs one sleep and lets it pick up a connection added from the panel
        later."""
        if self.connections is not None:
            await self.connections.start_all()
            logger.info("[clouddoc] watcher started for %d document(s)", len(self.connections.all_docs()))
        self._discovery = start_discovery(self.panel)

    async def stop(self) -> None:
        if self._discovery is not None:
            # Cancelled before the watchers: discovery only adopts, so nothing is lost
            # by stopping it first, while a round in flight would otherwise keep a
            # provider call alive past the watchers it feeds.
            self._discovery.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._discovery
            self._discovery = None
        if self.connections is not None:
            # Stopped before the agent client disconnects: the watcher dispatches
            # through it, so disconnecting first would leave a turn in flight to die.
            await self.connections.stop_all()
