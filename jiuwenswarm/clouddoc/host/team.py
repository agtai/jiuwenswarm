"""The team member's side of co-scribe: the toolkit for the declarative assembly path.

A single-agent session gets its tools imperatively (``host.agent``), paired with a
second act on an unattended turn: the session's ability set is stripped to a
closed allowlist. A team member is built declaratively -- a provider returns
elements and never touches a live ability manager -- so there is no equivalent of
that stripping here.

**An unattended turn therefore gets nothing, and that is the important line.**
Today no unattended turn reaches this path, because the watcher dispatches to a
single-agent session, but a rule holding because no caller reaches it is not a
rule: the day someone points the watcher at a team, this factory would hand a
closed-set turn an open tool set with nothing raising. So it refuses. If the
closed set cannot be enforced here, the tools that need it are not built here.

The other gates are ordinary. Disabled, no connection, an unreadable key, a
missing extra: build nothing, say so, move on -- a member that failed to build
would take the whole team down over one capability.
"""

from __future__ import annotations

import logging
from typing import Any

from jiuwenswarm.clouddoc.settings import deployment_config

logger = logging.getLogger(__name__)


def build_team_tools(cfg: dict[str, Any], *, channel_id: str | None) -> list[Any]:
    """The co-scribe tools for one team member, or an empty list when skipped.

    ``cfg`` is the deployment's ``clouddoc`` section; ``channel_id`` is the raw
    channel the member is being built for, read off the build context rather than a
    contextvar, since the context is what the declarative path is given.
    """
    cfg = cfg or {}
    if not cfg.get("enabled"):
        return []

    from jiuwenswarm.clouddoc.providers.base import CLOUDDOC_CHANNEL_ID, read_connection_specs

    if channel_id == CLOUDDOC_CHANNEL_ID:
        logger.warning(
            "[clouddoc.team] an unattended turn reached the team assembly path, which "
            "cannot narrow the ability set: no co-scribe tools are provided. Unattended "
            "turns are dispatched by the watcher to a single-agent session."
        )
        return []

    specs = read_connection_specs(cfg)
    if not specs:
        logger.info("[clouddoc.team] skipped: no configured connection")
        return []

    try:
        from jiuwenswarm.clouddoc.providers.factory import build_provider
        from jiuwenswarm.clouddoc.tools.toolkit import CloudDocToolkit
    except ImportError:
        logger.warning("[clouddoc.team] extras not installed, tools not assembled")
        return []

    def live_specs() -> list[dict]:
        # Re-read on every call: the panel adopts documents at any moment and writes
        # them into the config; a snapshot taken at member build time would hide a
        # document from the agent while the panel lists it on screen.
        return read_connection_specs(deployment_config().get("clouddoc") or {})

    # A team turn is a person talking, so it reaches every connection's documents,
    # routed by adoption -- the same helper the chat path uses.
    try:
        from jiuwenswarm.clouddoc.providers.routing import all_adopted_documents, build_routed_provider

        provider, _ = build_routed_provider(
            specs, build=build_provider, live_specs=live_specs, log=logger,
            agent_roster=tuple(str(x) for x in (cfg.get("agent_roster") or [])),
        )
    except Exception as exc:  # noqa: BLE001 - a corrupt key must not end member setup
        logger.warning("[clouddoc.team] provider construction failed: %s", exc)
        return []
    try:
        from jiuwenswarm.clouddoc.providers.kinds import prime_provider_kinds

        prime_provider_kinds(provider, [d for sp in specs for d in (sp.get("documents") or [])])
    except Exception:  # noqa: BLE001 - priming must not stop member setup
        pass

    harness_mode = str(cfg.get("mode") or "mandate").strip().lower()
    if harness_mode not in ("mandate", "recorded", "direct"):
        harness_mode = "mandate"
    try:
        from jiuwenswarm.clouddoc.receipts import ReceiptStore

        # Direct mode carries no receipts by design; the other modes do.
        if harness_mode != "direct":
            provider.receipt_sink = ReceiptStore()
    except Exception as exc:  # noqa: BLE001
        # Attended and ask-gated here, so a missing sink is tolerated; the unattended
        # direct-apply path refuses without one and never reaches this factory.
        logger.warning("[clouddoc.team] receipt sink unavailable: %s", exc)

    try:
        toolkit = CloudDocToolkit(
            provider,
            harness_mode=harness_mode,
            rail_overrides=cfg.get("rail"),
            # No turn document and no turn comment: this path is only ever a person
            # talking, the chat shape. The tools ask which document is meant, using
            # the watched list below.
            watched_docs=lambda: all_adopted_documents(live_specs),
            # Routed across every connection, so the "partial list" note never applies.
            connection_count=lambda: 1,
            workmode_file=str(cfg.get("workmode_file") or ""),
        )
        from jiuwenswarm.clouddoc.host.bridge import to_openjiuwen

        tools = to_openjiuwen(list(toolkit.get_tools()))
        logger.info("[clouddoc.team] built %d co-scribe tools", len(tools))
        return tools
    except Exception as exc:  # noqa: BLE001
        logger.warning("[clouddoc.team] toolkit construction failed: %s", exc)
        return []
