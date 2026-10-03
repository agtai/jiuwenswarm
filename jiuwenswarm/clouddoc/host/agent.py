"""The agent adapter's side of co-scribe: one toolkit per session, and the closed set.

The adapter is cached per session, and so is this object: the provider holds a
threading-local client cache, and sharing it across sessions would mix
credentials and connections from different sessions together, so there is no
process-level singleton. On every request the adapter calls ``update``, which
refreshes the turn's authorization snapshot, narrows an unattended session to the
closed set, and registers the cloud-document tools.

Two orderings carry the whole safety argument of the unattended path:

* **The ability boundary comes before every early return.** Feature disabled,
  credentials missing, extras absent, provider construction failing -- each of
  these used to return before stripping, so an unattended turn would run with the
  full default tool set, bash included. That hung the boundary on a feature
  switch, when it should hang only on whether anyone is present this turn.
* **The tools read the snapshot, not the contextvars.** The request binding is
  gone by the time a tool runs, so a tool reading the contextvars sees no
  authorized document at all; the snapshot is taken inside the binding window and
  refreshed every turn -- back to empty on a chat turn, so a session cannot carry
  the previous turn's authority.

Stripping works from an allowlist, not a denylist: a denylist fails silently the
moment someone adds a default tool, while an allowlist fails toward "the agent is
missing a tool" rather than "the unattended agent also has bash".
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

from jiuwenswarm.clouddoc.host import turn as turn_ctx
from jiuwenswarm.clouddoc.settings import deployment_config

logger = logging.getLogger(__name__)


def workmode_prefer_zh(clouddoc_cfg: dict) -> bool:
    """Pick the builtin workmode template language from the configured conventions
    marker, the same rule the watcher uses (``workmode.prefer_zh_from_words``)."""
    sample = str(clouddoc_cfg.get("conventions_marker") or "")
    if not sample:
        return True
    return any("一" <= ch <= "鿿" for ch in sample)


def user_text(session_id: str | None) -> str:
    """Everything the **user** typed in this session, joined; never anything the model
    wrote.

    Feeds the toolkit's ambiguity rail, which needs one thing the model cannot forge.
    ``history.jsonl`` stamps each record with a role, so filtering to ``user`` gives
    exactly that -- and an ``ask_user`` answer counts too, even though its record's
    role is assistant: the text came from the person, and it is the only way a
    refused turn can recover. Any failure returns the empty string, the fail-closed
    direction: with no evidence the user named a document, an ambiguous write is
    refused rather than allowed.
    """
    if not session_id:
        return ""
    try:
        from jiuwenswarm.common.utils import get_agent_sessions_dir

        # history.jsonl, one JSON object per line -- not the history.json that
        # compaction reads. Getting this wrong is silent and total: every lookup
        # returns "" and the rail refuses every document operation on the chat path.
        path = get_agent_sessions_dir() / session_id / "history.jsonl"
        if not path.exists():
            return ""
        records = []
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except ValueError:
                    continue  # a torn last line while the file is being appended to
    except Exception:  # noqa: BLE001 - a missing or corrupt history must not break tools
        return ""

    out: list[str] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        if record.get("tool_name") == "ask_user":
            result = record.get("result")
            if isinstance(result, str):
                out.append(result)
            continue
        if record.get("role") != "user":
            continue
        content = record.get("content")
        if isinstance(content, str):
            out.append(content)
        elif isinstance(content, list):
            # Multimodal turns carry a parts list; only the text parts are evidence.
            out.extend(
                part["text"]
                for part in content
                if isinstance(part, dict) and isinstance(part.get("text"), str)
            )
    return "\n".join(out)


def credentials_for_turn(specs: list[dict], turn_doc: str | None) -> str:
    """The credentials an unattended turn runs under: the connection that adopted
    the turn's document, compared by exact document id.

    The chat path, and a document no connection lists, take the first connection --
    the same rule as ``registry.get(None)`` on the gateway side. Equality on the
    canonical token, never containment: two ids sharing a prefix are two documents,
    and a turn routed by substring could write under the wrong account.
    """
    from jiuwenswarm.clouddoc.providers.base import doc_ref_token

    credentials_file = str(specs[0]["credentials_file"])
    # Both sides through the same reduction: a configured entry may be a link, and
    # so may the dispatched id when the config held one.
    want = doc_ref_token(turn_doc)
    if not want:
        return credentials_file
    for spec in specs:
        if any(doc_ref_token(d) == want for d in spec.get("documents") or []):
            return str(spec["credentials_file"])
    return credentials_file


def self_address(credentials_file: str) -> str:
    """This connection's own address, read from its key file: a Google key names a
    service-account email, a Feishu key the bot's open id. The tools ask on every
    call, so the helper caches on the key file's mtime."""
    try:
        from jiuwenswarm.clouddoc.providers.factory import credential_address
    except ImportError:
        return ""
    return credential_address(credentials_file)


class CloudDocSessionTools:
    """What one adapter holds for co-scribe: the toolkit, the session, the snapshot."""

    def __init__(self) -> None:
        self.toolkit: Any | None = None
        # The session whose words the ambiguity rail reads; refreshed on every turn.
        self.session_id: str | None = None
        # This turn's authorization snapshot. An empty dict means unbound -- the chat
        # path -- and the tools impose no constraint on it.
        self.turn: dict[str, str | None] = {}
        # Display only, and deliberately outside the dict above: nothing reads it to
        # decide anything.
        self.progress: dict = {}

    def turn_snapshot(self) -> dict[str, Any] | None:
        """This turn's snapshot for the permission rail, or None outside an
        unattended turn. The rail's scene hook runs while a tool is executing, where
        the contextvars are unbound; this is how it still recognises the turn."""
        return dict(self.turn) if self.turn else None

    def update(
        self,
        instance: Any,
        session_id: str | None = None,
        *,
        config_base: dict | None = None,
        register: Callable[[Any], None],
    ) -> None:
        """Refresh the snapshot, close the set on an unattended turn, register the tools.

        ``register`` receives each openjiuwen tool the adapter has not registered yet;
        the adapter owns the registration and the ability manager, this object only
        decides what goes in.
        """
        # Recorded on every call, not only when the toolkit is first built: the
        # toolkit is constructed once per adapter, and its user_text reader resolves
        # the session at call time through this attribute.
        self.session_id = session_id
        if instance is None:
            return

        unattended = turn_ctx.is_unattended_turn()
        if unattended:
            self.turn = {
                "doc_id": turn_ctx.turn_doc_id(),
                "comment_id": turn_ctx.turn_comment_id(),
                # The watch level, snapshotted with the ids. Missing resolves to the
                # strictest family downstream -- never permissive.
                "mode": turn_ctx.turn_mode(),
            }
            self.progress = turn_ctx.turn_progress()
            self.strip_to_closed_set(instance)
        else:
            self.turn = {}
            self.progress = {}

        # One config read per update, so the two decisions cannot see different
        # snapshots.
        if config_base is None:
            config_base = deployment_config()
        clouddoc_cfg = config_base.get("clouddoc") or {}
        if not clouddoc_cfg.get("enabled"):
            return

        if self.toolkit is None:
            self.toolkit = self._build_toolkit(clouddoc_cfg)
            if self.toolkit is None:
                return

        from jiuwenswarm.clouddoc.host.bridge import to_openjiuwen
        from jiuwenswarm.clouddoc.tools.toolkit import unattended_allowlist_for

        tools = to_openjiuwen(list(self.toolkit.get_tools()))
        if unattended:
            # Stripping already happened above, where it must precede the early
            # returns; this only filters the batch about to be registered.
            allowed = unattended_allowlist_for(self.turn.get("mode"))
            tools = [t for t in tools if t.card.name in allowed]

        registered = {
            getattr(existing, "name", "") for existing in (instance.ability_manager.list() or [])
        }
        for tool in tools:
            if tool.card.name in registered:
                continue
            register(tool)
            instance.ability_manager.add(tool.card)

    def strip_to_closed_set(self, instance: Any) -> None:
        """Narrow this session's ability set down to the turn's closed set. Touches only
        this session's ability manager; the watcher uses a separate session per
        document, so chat sessions are unaffected."""
        from jiuwenswarm.clouddoc.tools.toolkit import unattended_allowlist_for

        allowed = unattended_allowlist_for(self.turn.get("mode"))
        before = [getattr(a, "name", "") for a in (instance.ability_manager.list() or [])]
        for name in before:
            if name and name not in allowed:
                instance.ability_manager.remove(name)
        after = [getattr(a, "name", "") for a in (instance.ability_manager.list() or [])]
        # The closed set is this path's only ability boundary, so it has to be
        # auditable. ``remaining`` is what survived the strip, which is not the turn's
        # tool set -- the co-scribe tools are registered a few lines later -- hence
        # ``allowed`` alongside it, the set the turn actually ends up with.
        logger.info(
            "[clouddoc] closed-set strip %d -> %d; remaining=%s; allowed=%s",
            len(before), len(after), sorted(after), sorted(allowed),
        )

    def _build_toolkit(self, clouddoc_cfg: dict) -> Any | None:
        """Build the session's toolkit, or None when the deployment has no usable
        connection. Every failure logs and returns None: a corrupt key or a missing
        extra must not stop the agent from starting."""
        from jiuwenswarm.clouddoc.providers.base import read_connection_specs

        specs = read_connection_specs(clouddoc_cfg)
        if not specs:
            return None
        # With several connections, an unattended turn picks the credentials by which
        # connection owns this turn's document; the chat path takes the first.
        turn_doc = self.turn.get("doc_id")
        credentials_file = credentials_for_turn(specs, turn_doc)
        try:
            from jiuwenswarm.clouddoc.providers.factory import build_provider
            from jiuwenswarm.clouddoc.tools.toolkit import CloudDocToolkit
        except ImportError:
            logger.warning("[clouddoc] extras not installed, tools not registered")
            return None
        try:
            # The factory detects the vendor from the credentials file; this is the one
            # place the agentserver builds a provider, so it routes through the same
            # detection the gateway uses.
            roster = tuple(str(x) for x in (clouddoc_cfg.get("agent_roster") or []))
            if turn_doc:
                # An unattended turn keeps its single, owning provider: its confinement
                # is to one document and one account.
                provider = build_provider(credentials_file, agent_roster=roster)
            else:
                # A chat turn reaches every connection's documents, routed by which
                # connection adopted each one.
                from jiuwenswarm.clouddoc.providers.routing import build_routed_provider

                provider, credentials_file = build_routed_provider(
                    specs,
                    build=build_provider,
                    live_specs=lambda: read_connection_specs(
                        deployment_config().get("clouddoc") or {}
                    ),
                    agent_roster=roster,
                    log=logger,
                )
        except Exception:  # noqa: BLE001 - a corrupt key must not end session setup
            logger.exception("[clouddoc] provider construction failed, tools not registered")
            return None

        # The provider's format routing is process memory and the turn arrives with a
        # bare token; the panel's store is what survives. Primed after the provider
        # exists, for all watched documents: chat turns carry no binding yet reach any
        # watched document by token.
        try:
            from jiuwenswarm.clouddoc.providers.kinds import prime_provider_kinds

            docs = {str(d) for sp in specs for d in sp["documents"]}
            if turn_doc:
                docs.add(str(turn_doc))
            prime_provider_kinds(provider, docs)
        except Exception:  # noqa: BLE001 - priming must not stop the turn
            logger.debug("[clouddoc] turn-side kind priming skipped", exc_info=True)

        def live_specs() -> list[dict]:
            # Re-read on every call: the panel adopts documents at any moment and
            # writes them straight back into the config, and a snapshot taken when the
            # toolkit was built would hide them from the agent for the whole session.
            return read_connection_specs(deployment_config().get("clouddoc") or {})

        routed = provider.__class__.__name__ == "RoutingProvider"

        def watched_docs_live() -> list:
            if routed:
                return [d for sp in live_specs() for d in sp["documents"]]
            return next(
                (sp["documents"] for sp in live_specs() if sp["credentials_file"] == credentials_file),
                [],
            )

        def connection_count_live() -> int:
            # The "partial list" note exists for a toolkit bound to one connection of
            # several; a routed toolkit lists them all.
            return 1 if routed else len(live_specs())

        # The deployment's mode decides how much harness rides along. "direct" is the
        # deliberate baseline -- no receipts, no floor -- and an unknown value falls
        # back to mandate, never to bare.
        harness_mode = str(clouddoc_cfg.get("mode") or "mandate").strip().lower()
        if harness_mode not in ("mandate", "recorded", "direct"):
            harness_mode = "mandate"
        if harness_mode != "direct":
            try:
                from jiuwenswarm.clouddoc.receipts import ReceiptStore

                provider.receipt_sink = ReceiptStore()
            except Exception:  # noqa: BLE001
                # The chat path tolerates a missing sink (attended, ask-gated); the
                # unattended direct-apply path re-checks and refuses without one.
                logger.exception("[clouddoc] receipt sink unavailable on the toolkit path")
        return CloudDocToolkit(
            provider,
            harness_mode=harness_mode,
            # The snapshot, not the contextvar: refreshed each turn by ``update``.
            turn_doc_id=lambda: self.turn.get("doc_id"),
            turn_comment_id=lambda: self.turn.get("comment_id"),
            # The watch level the turn started with: the pre-write checkpoint holds the
            # registry to it, so a tier changed mid-turn intercepts the write.
            turn_mode=lambda: self.turn.get("mode"),
            turn_progress=lambda: self.progress,
            rail_overrides=clouddoc_cfg.get("rail"),
            # Which account the tools are, to tell a task assigned to them from one
            # assigned to another agent in the same document.
            turn_address=lambda: self_address(credentials_file),
            watched_docs=watched_docs_live,
            connection_count=connection_count_live,
            # Resolved at call time through the attribute, never captured at
            # construction: the toolkit outlives the session it was first built for.
            user_text=lambda: user_text(self.session_id),
            workmode_file=str(clouddoc_cfg.get("workmode_file") or ""),
            workmode_prefer_zh=workmode_prefer_zh(clouddoc_cfg),
        )
