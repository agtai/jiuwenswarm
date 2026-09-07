"""The service layer behind the Docs panel, serving the web UI's ``clouddoc.*`` RPCs.

Design constraints, each matching the UI:

* ``list_docs`` **makes no Google API calls**. Opening the panel is a frequent
  action and quota is shared across a connection, so the listing reads only the
  health bits and cached titles in the state file. Live facts come from ``add_doc``
  and ``update_doc``, the two things a user does deliberately.
* Adds and removals take effect **without a restart**: the registry's in-memory
  state changes and config.yaml is rewritten round-trip. Round-trip is what keeps
  the comments in a user's config file intact.
* The status vocabulary matches the UI and has exactly four values: ``ok``,
  ``comment_only``, ``frozen``, ``backoff``. Classification shares its source with
  the watcher's admission check -- both treat capabilities as the fact -- so no
  second set of rules is introduced here.
* A comment-only document is **refused**, exactly as admission refuses it.
* **Sharing is what puts a document under management.** ``sync_shared_docs`` adopts
  everything shared with the connection that it can edit, because sharing is already
  a deliberate act performed in the provider's own interface and asking for a second
  confirmation here would only make people copy links around. This is safe only
  because watching costs a poll and nothing more -- work needs an assignment.
* **Connections are immutable**: add_connection and remove_connection, no editing.
  The credentials decide the address and the address is the identity, so changing
  the identity means deleting and re-adding.
* **A document belongs to exactly one connection.** State and sessions are keyed by
  doc_id; this constraint replaced a state-key migration, and it costs only the
  ability to have two identities watch one document -- which was a recipe for
  answering everything twice anyway.
"""

from __future__ import annotations

import asyncio
import json
import pathlib
import logging
import os
import re
import time
import uuid
from typing import Any

from jiuwenswarm.agents.harness.common.tools.clouddoc.provider import ProviderError
from jiuwenswarm.common.config import (
    CONFIG_YAML_PATH,
    dump_yaml_round_trip,
    load_yaml_round_trip,
    update_config,
)
from jiuwenswarm.gateway.clouddoc.connections import CloudDocConnection, CloudDocConnections

logger = logging.getLogger(__name__)

# Display names by provider.kind. A second provider registers itself here.
_PROVIDER_NAMES = {"google": "Google Docs", "feishu": "飞书文档"}

# The personal-signature config key (S.5). The body is the person's to word; the
# receipt number is appended by code and is not in this string.
SIGNATURE_KEY = "personal_signature"


def _key_stem(parsed: Any) -> str | None:
    """The file stem an uploaded key gets, from the key's own shape -- the same test
    ``factory.detect_vendor`` applies once the file exists. ``None`` when the JSON is
    neither vendor's key, so the panel refuses before writing anything."""
    if not isinstance(parsed, dict):
        return None
    if str(parsed.get("kind") or "").strip().lower() == "personal":
        brand = str(parsed.get("brand") or "").strip().lower() or "unknown"
        who = str(parsed.get("open_id") or parsed.get("profile") or "default")
        return f"personal-{brand}-{who}"
    email = str(parsed.get("client_email") or "")
    if email:
        return email.split("@")[0]
    if parsed.get("app_id") and parsed.get("app_secret"):
        return str(parsed["app_id"])
    return None


def _conn_payload(c: CloudDocConnection, **extra: Any) -> dict[str, Any]:
    return {
        "id": c.id,
        "provider": c.kind,
        "provider_name": _PROVIDER_NAMES.get(c.kind, c.kind),
        "agent_address": c.address,
        "agent_display": c.display_name,
        # ``service`` or ``personal`` (S.1). The UI draws the two differently: a
        # personal connection has no tiers, only a notify state.
        "kind": c.identity_kind,
        **extra,
    }


class CloudDocPanel:
    """Compose the registry's existing primitives into the actions the panel needs.

    It deliberately holds no state of its own. The truth lives in the registry, the
    state file and config.yaml, so the feature works the same whether the panel is
    broken or never opened.
    """

    def __init__(self, connections: CloudDocConnections, *, config_path=None) -> None:
        self._reg = connections
        self._config_path = pathlib.Path(config_path or CONFIG_YAML_PATH)

    # ------------------------------------------------------------ reads

    async def get_conf(self) -> dict[str, Any]:
        conns = []
        for c in self._reg.list():
            summary = await self._connection_summary(c)
            conns.append(_conn_payload(
                c, docs_count=summary["total"],
                **{k: v for k, v in summary.items() if k != "total"},
            ))
        first = conns[0] if conns else {}
        return {
            "enabled": True,
            # The live config flag, distinct from this panel's boot-time
            # existence: uninstalling the co-scribe plugin flips it off while
            # the panel object survives until restart, and the UI hides the
            # cloud-doc surfaces the moment this reads false.
            "installed": self._currently_enabled(),
            "mode": self._current_mode(),
            # Whether the host offers a question channel. The always-ask floor
            # (share, trash, a write whose ledger is missing) refuses without one,
            # and the shipped config starts with permissions off -- so the panel
            # has to say it, or the first share simply fails.
            "ask_channel": self._ask_channel_available(),
            "model_name": self._current_model_name(),
            "agent_address": first.get("agent_address"),
            "approve_word": list(self._reg.watcher_cfg.approve_word),
            "keep_word": list(self._reg.watcher_cfg.keep_word),
            "connections": conns,
            # The person's half of the personal signature (S.5); empty means the
            # default wording. The receipt number is never part of it.
            "personal_signature": self._current_signature(),
            "identity_choice": self._current_choices(),
            # Whether a Google OAuth client is configured for personal connections.
            # The secret never leaves the config.
            "google_oauth": {
                "configured": bool(self._google_oauth_cfg()["client_id"] and self._google_oauth_cfg()["client_secret"]),
                "client_id": self._google_oauth_cfg()["client_id"],
            },
        }

    async def list_docs(self) -> list[dict[str, Any]]:
        """One row per document -- the union over every connection.

        A person ordinarily holds documents of three kinds at once: some only the
        team's service identity reaches, some only they do (shared with them), some
        both. Each row says how the document is reachable (``reach``: service /
        personal / both) and which identity executes on it (``identity``; the
        person's choice, service by default), with health judged for that
        identity and the other identity's health beside it.

        No API calls in the steady state. The kind/title self-heals below are
        the one exception, and each probes **once per document per process**:
        a document whose provider cannot answer (lost access, unsupported
        format) used to be re-asked on every panel load, and with the awaits
        running serially a handful of unhealable rows turned opening the panel
        into seconds of API round-trips."""
        probed: set[str] = getattr(self, "_meta_probed", None) or set()
        self._meta_probed = probed
        url_probed: set[str] = getattr(self, "_url_probed", None) or set()
        self._url_probed = url_probed
        rows = []
        unread: dict[str, int] = {}
        if self._reg.notice_store is not None:
            try:
                unread = await asyncio.to_thread(self._reg.notice_store.unread_by_doc)
            except Exception:  # noqa: BLE001 - a missing badge is not an outage
                unread = {}
        seen: set[str] = set()
        for c in self._reg.list():
            for doc_id in list(c.watcher._docs):
                if doc_id in seen:
                    continue
                seen.add(doc_id)
                owners = self._reg.owners(doc_id)
                exec_conn = self._reg.find_doc(doc_id) or c
                by_kind = {o.identity_kind: o for o in owners}
                reach = "both" if len(by_kind) == 2 else exec_conn.identity_kind
                # Health is per identity -- the person may have lost access where the
                # bot still has it -- so each owner's scoped entry is read; the
                # metadata is the document's and comes with the executing one.
                health = await self._reg.store_for(exec_conn).doc_health(doc_id)
                status_by = {}
                for kind, o in by_kind.items():
                    h = health if o is exec_conn else await self._reg.store_for(o).doc_health(doc_id)
                    status_by[kind] = self._status_of(h, personal=o.personal)
                meta = health.get("panel_meta") or {}
                # The format, so the panel can tell a spreadsheet from a document --
                # both in the icon it draws and in the link it opens, since a
                # spreadsheet's editor lives at a different path. Recorded at adoption;
                # asked of the provider for a document adopted before this existed, and
                # left empty when even that cannot answer, which the UI reads as "a
                # document" rather than showing nothing.
                kind = meta.get("kind") or ""
                if not kind and doc_id not in probed:
                    fn = getattr(exec_conn.provider, "doc_kind", None)
                    if fn is not None:
                        try:
                            kind = await fn(doc_id)
                            if kind:
                                await self._reg.store.set_panel_meta(doc_id, kind=kind)
                        except Exception:  # noqa: BLE001 - a missing icon is not an outage
                            kind = ""
                # The provider's format routing is process memory; the panel's store
                # is what survives a restart. Feeding the persisted kind back keeps a
                # known spreadsheet off the docx paths -- including the title probe
                # right below, which would otherwise ask the wrong fetch.
                if kind:
                    for o in owners:
                        note = getattr(o.provider, "note_kind", None)
                        if note is not None:
                            note(doc_id, kind)
                # The title heals the same way the kind does: a document adopted
                # before titles were recorded shows its id prefix forever unless
                # someone asks the provider once and caches the answer.
                title = meta.get("title") or ""
                if not title and doc_id not in probed:
                    probed.add(doc_id)
                    try:
                        title = await exec_conn.provider.title(doc_id)
                        if title:
                            await self._reg.store.set_panel_meta(doc_id, title=title)
                    except Exception:  # noqa: BLE001 - a missing name is not an outage
                        title = ""
                # A bot-created document has no pasted link to remember, and the bare
                # token renders as dead text. The provider can ask the platform for
                # the canonical URL; once per document per process, persisted so the
                # next restart reads it back instead of asking again.
                url = str(meta.get("url") or "")
                if not url.startswith("http") and doc_id not in url_probed:
                    url_probed.add(doc_id)
                    fn = getattr(exec_conn.provider, "canonical_url", None)
                    if fn is not None:
                        try:
                            u = str(await fn(doc_id) or "")
                            if u.startswith("http"):
                                url = u
                                await self._reg.store.set_panel_meta(doc_id, url=u)
                        except Exception:  # noqa: BLE001 - a dead link is not an outage
                            pass
                personal_owner = by_kind.get("personal")
                rows.append({
                    "doc_id": doc_id,
                    "url": url or exec_conn.provider.doc_url(doc_id, kind),
                    "title": title or doc_id[:12] + "…",
                    "kind": kind,
                    "checked_at": meta.get("checked_at"),
                    "status": status_by.get(exec_conn.identity_kind, "ok"),
                    "status_by": status_by,
                    "retry_at": health.get("until"),
                    "provider": exec_conn.kind,
                    "provider_name": _PROVIDER_NAMES.get(exec_conn.kind, exec_conn.kind),
                    # The executing connection, and every owner by kind.
                    "connection_id": exec_conn.id,
                    "connections": {k: o.id for k, o in by_kind.items()},
                    # S.1/S.2/S.3 for the row: how the document is reachable, which
                    # identity executes on it, and how many unread notices it holds.
                    "reach": reach,
                    "identity": exec_conn.identity_kind,
                    "notices": int(unread.get(doc_id, 0)) if personal_owner is not None else 0,
                })
        return rows

    @staticmethod
    def _status_of(health: dict[str, Any], *, personal: bool = False) -> str:
        if health.get("failed"):
            # comment_only is a configuration mistake the user can fix themselves, so
            # it gets its own state and its own guidance. Every other failure -- three
            # consecutive 403s or 404s -- is simply frozen. A personal row is never
            # comment-only: the person's own comment access is enough to be told.
            if health.get("failed_reason") == "comment_only_access" and not personal:
                return "comment_only"
            return "frozen"
        until = health.get("until")
        if until and time.time() < float(until):
            return "backoff"
        return "ok"

    async def _connection_summary(self, conn: CloudDocConnection) -> dict[str, Any]:
        """A connection-level summary: counts by class, and the health bit derived from
        them.

        It aggregates per-document facts that already exist rather than probing the
        credentials separately, because the common failure is valid credentials with a
        document that was never shared or shared comment-only. With no documents the
        answer is ``idle``, not ok: configured credentials are not the same as working
        ones, and at that point there is no fact to judge.
        """
        docs = list(conn.watcher._docs)
        states = [
            self._status_of(await self._reg.store_for(conn).doc_health(d), personal=conn.personal)
            for d in docs
        ]
        counts = {
            "total": len(states),
            "ok": sum(1 for x in states if x == "ok"),
            "attention": sum(1 for x in states if x == "comment_only"),
            "down": sum(1 for x in states if x in ("frozen", "backoff")),
        }
        if not states:
            health = "idle"
        elif counts["ok"] == counts["total"]:
            health = "ok"
        elif counts["ok"]:
            health = "attention"
        else:
            health = "down"
        return {**counts, "health": health}

    async def sync_shared_docs(self, connection_id: str | None = None) -> dict[str, Any]:
        """Adopt every document shared with this connection that it can actually edit.

        Sharing a document with the agent **is** the decision -- nobody shares one by
        accident, and it is a deliberate act in another product's interface. Asking for a
        second confirmation here would be ceremony, and it would leave people copying
        links back and forth for something the platform already told us.

        What made this safe is the trigger model. Watching a document used to mean any
        mention could spend a turn; now watching costs a poll and nothing else, because
        work needs an assignment. So adoption buys visibility at the price of polling,
        and the expensive part stays a separate, deliberate act.

        Documents shared **comment-only** are reported rather than adopted. Admission
        would refuse them anyway, and a person who shared one made a specific mistake
        that has a specific fix -- saying so beats an entry that silently never works.
        """
        conn = self._reg.get(connection_id)
        if conn is None:
            return {"result": "no_connection", "adopted": [], "needs_editor": []}
        try:
            found = await conn.provider.list_accessible_documents()
        except ProviderError as exc:
            # A convenience; failing it must not make the panel unusable. The common
            # cause is the Drive API not being enabled, which reads as forbidden.
            logger.warning("[clouddoc] 发现共享文档失败（%s）：%s", exc.kind, exc)
            return {"result": "unknown", "detail": exc.kind, "adopted": [], "needs_editor": []}

        if conn.personal:
            # S.6: a person's "shared with me" may run to hundreds of documents, and
            # polling all of them would spend the quota on nothing. Discovery lists;
            # the person ticks the ones to adopt (``adopt_docs``). Nothing is adopted
            # here, and a document already under this connection is marked so.
            mine = set(conn.watcher._docs)

            def adopted_by(doc_id: str) -> str:
                # Visible so a document the team's service identity already manages
                # is not mistaken for a new one: adopting it here too makes it
                # reachable both ways (one row, ``reach: both``), never a duplicate.
                kinds = {o.identity_kind for o in self._reg.owners(doc_id)}
                return "both" if len(kinds) == 2 else (next(iter(kinds)) if kinds else "")

            candidates = [
                {
                    "doc_id": d.doc_id, "title": d.title, "kind": d.kind,
                    "url": conn.provider.doc_url(d.doc_id, d.kind),
                    "can_edit": bool(d.can_edit), "adopted": d.doc_id in mine,
                    "adopted_by": adopted_by(d.doc_id),
                }
                for d in found
            ]
            return {
                "result": "ok", "adopted": [], "needs_editor": [], "unsupported": [],
                "candidates": candidates,
            }

        # Only a service connection's own documents count as taken: a personal
        # connection on the same document is the overlap S.2 provides for.
        watched = {d for c in self._reg.list() if not c.personal for d in c.watcher._docs}
        adopted: list[dict[str, Any]] = []
        needs_editor: list[dict[str, Any]] = []
        for d in found:
            if d.doc_id in watched:
                continue
            row = {"doc_id": d.doc_id, "title": d.title,
                   "url": conn.provider.doc_url(d.doc_id, d.kind)}
            if not d.can_edit:
                needs_editor.append(row)
                continue
            # No second capability probe: the listing already answered it, with the same
            # two flags admission reads.
            conn.watcher.watch(d.doc_id)
            await self._reg.store.set_panel_meta(
                d.doc_id, title=d.title, kind=d.kind, checked_at=time.time()
            )
            # The adoption policy applies when the document is registered, not
            # only when a connection is built at startup.
            self._reg.policy_issue([d.doc_id])
            adopted.append(row)

        # 刷新 is also "check every row again": a person pressing it expects 检查于 to
        # move on all of them, not only on the ones discovery happened to list
        # (measured: 3 of 15 rows moved). Fail-soft per row, and a row's verdict is
        # updated the same way the single-row refresh does it.
        rechecked = 0
        mine = list(conn.watcher._docs)
        for doc_id in mine:
            try:
                await self.update_doc(doc_id)
                rechecked += 1
            except Exception:  # noqa: BLE001
                logger.debug("[clouddoc] 刷新时重探失败 doc=%s", doc_id, exc_info=True)

        # Same convenience contract as discovery itself: failing to list the
        # unsupported files must not break the panel, it only loses the notice.
        try:
            unsupported = await conn.provider.list_shared_unsupported()
        except Exception:  # noqa: BLE001
            unsupported = []

        if adopted:
            await asyncio.to_thread(self._persist)
            logger.info("[clouddoc] %s 自动纳管了 %d 篇新共享的文档", conn.address, len(adopted))
        return {
            "result": "ok", "adopted": adopted, "needs_editor": needs_editor,
            "unsupported": unsupported,
        }

    # ------------------------------------------------------------ documents

    async def add_doc(self, url_or_id: str, connection_id: str | None = None) -> dict[str, Any]:
        """Pasting a link verifies it. It belongs to the named connection, or the first
        one by default."""
        conn = self._reg.get(connection_id)
        if conn is None:
            return {"result": "no_connection"}
        try:
            doc_id = conn.provider.parse_doc_ref(url_or_id)
        except ProviderError as exc:
            return {"result": "invalid", "detail": str(exc)}
        owner = next((c for c in self._reg.owners(doc_id) if c.personal == conn.personal), None)
        if owner is not None:
            # Re-pasting a link is how a document adopted before URL persistence
            # heals: the token is known, only the tenant-domain link was lost.
            if url_or_id.strip().startswith("http"):
                await self._reg.store.set_panel_meta(
                    doc_id, url=url_or_id.split("?", 1)[0].split("#", 1)[0]
                )
            # A document belongs to one connection **of a kind**: two service
            # identities on one document means every mention answered twice, and
            # state keyed by doc_id means the two overwrite each other. The owner is
            # returned in full so the UI can say which connection already has it. A
            # service and a personal connection may share a document (S.2).
            return {"result": "exists", "doc_id": doc_id, "connection_id": owner.id}

        probe = await self._probe(conn, doc_id)
        if probe["result"] != "ok":
            return probe

        # State changes only after the facts check out: memory first, so it takes
        # effect now, then config, so it survives a restart.
        conn.watcher.watch(doc_id)
        await self._reg.store.set_panel_meta(
            doc_id, title=probe.get("title") or "",
            kind=probe.get("kind") or "", checked_at=time.time(),
            # A Feishu URL starts with the tenant's own domain, which appears
            # nowhere but in the link the person pasted; kept here it survives
            # restarts, where the provider's in-memory cache does not.
            url=url_or_id.split("?", 1)[0].split("#", 1)[0]
            if url_or_id.strip().startswith("http") else None,
        )
        if not conn.personal:
            self._reg.policy_issue([doc_id])
        await asyncio.to_thread(self._persist)
        return {"result": "ok", "doc_id": doc_id, "title": probe.get("title")}

    async def adopt_docs(
        self, connection_id: str | None, doc_ids: list[str]
    ) -> dict[str, Any]:
        """Adopt the documents a person ticked in the discovery list (S.6).

        Each goes through the same probe a pasted link does, so a document the
        listing showed but the identity cannot actually read is refused with the
        same vocabulary. Per-document outcomes come back so the UI can say which
        of a batch landed.
        """
        conn = self._reg.get(connection_id)
        if conn is None:
            return {"result": "no_connection", "adopted": [], "refused": []}
        adopted: list[str] = []
        refused: list[dict[str, Any]] = []
        for raw in doc_ids or []:
            try:
                doc_id = conn.provider.parse_doc_ref(str(raw))
            except ProviderError as exc:
                refused.append({"doc_id": str(raw), "result": "invalid", "detail": str(exc)})
                continue
            if doc_id in conn.watcher._docs:
                continue
            probe = await self._probe(conn, doc_id)
            if probe["result"] != "ok":
                refused.append({"doc_id": doc_id, **probe})
                continue
            conn.watcher.watch(doc_id)
            await self._reg.store.set_panel_meta(
                doc_id, title=probe.get("title") or "", kind=probe.get("kind") or "",
                checked_at=time.time(),
            )
            if not conn.personal:
                self._reg.policy_issue([doc_id])
            adopted.append(doc_id)
        if adopted:
            await asyncio.to_thread(self._persist)
        return {"result": "ok", "adopted": adopted, "refused": refused}

    async def remove_doc(self, doc_id: str, connection_id: str | None = None) -> dict[str, Any]:
        """Drop a document from one connection -- the named one, or every owner when
        none is named (the pre-overlap contract, kept for callers that have no
        connection in hand)."""
        owners = self._reg.owners(doc_id)
        if connection_id:
            owners = [c for c in owners if c.id == connection_id]
        if not owners:
            return {"result": "not_watched"}
        for conn in owners:
            conn.watcher.unwatch(doc_id)
        # Removing the document ends the delegation for it, as removing the
        # connection does for every document under it: a mandate that outlived
        # its document would meet a later re-adoption as still live. Only a
        # service connection ever held one.
        registry = getattr(self._reg, "_watch_registry", None)
        if registry is not None and any(not c.personal for c in owners):
            try:
                registry.revoke(doc_id, reason="document_removed")
            except Exception:  # noqa: BLE001 - the document is gone either way; say so
                logger.exception("[clouddoc] 撤销 %s 的值守失败（文档已移除）", doc_id)
        await asyncio.to_thread(self._persist)
        # The state entry goes to the store's gc, the same primitive sweep uses. It is
        # cleared at once, and re-adding the document cold-starts through seeding
        # rather than replaying its comment history.
        await self._reg.store.gc(self._reg.all_state_keys())
        return {"result": "ok"}

    async def update_doc(self, doc_id: str) -> dict[str, Any]:
        """Refresh is repair: reclassify against current facts, thaw what now works,
        and leave what does not with guidance."""
        conn = self._reg.find_doc(doc_id)
        if conn is None:
            return {"result": "not_watched"}
        store = self._reg.store_for(conn)
        probe = await self._probe(conn, doc_id)
        if probe["result"] == "ok":
            # The facts say healthy: clear the verdict bit and the watcher re-admits it
            # on the next tick.
            await store.clear_failure(doc_id)
            await self._reg.store.set_panel_meta(
                doc_id, title=probe.get("title") or "",
                kind=probe.get("kind") or "", checked_at=time.time(),
            )
            return {"result": "ok", "title": probe.get("title")}
        if probe["result"] == "comment_only":
            # Same verdict as admission: record it, and the UI keeps its amber light.
            await store.note_permanent_failure(doc_id, "comment_only_access")
            await self._reg.store.set_panel_meta(doc_id, checked_at=time.time())
        # not_shared and unknown leave state alone: a transient error is not a fact,
        # and nothing frozen gets thawed on one.
        return probe

    # ------------------------------------------------------------ connections

    async def add_connection(
        self,
        credentials_path: str | None = None,
        credentials_json: str | None = None,
        filename: str | None = None,
    ) -> dict[str, Any]:
        """Add a connection: take a key, either a server-side path or uploaded JSON,
        derive the address from it, and start the watcher immediately.

        An uploaded key is written to ``clouddoc-keys/`` under the config directory,
        the directory created 0700 and the file 0600. **The private key never enters
        config.yaml**; the config holds nothing but the path.
        """
        if credentials_json:
            try:
                parsed = json.loads(credentials_json)
            except ValueError:
                return {"result": "invalid_key", "detail": "not valid JSON"}
            stem = _key_stem(parsed)
            if stem is None:
                return {
                    "result": "invalid_key",
                    "detail": "not a Google service-account key (client_email), "
                              "not a Feishu app (app_id + app_secret), and not a "
                              "personal connection (kind: personal, brand: feishu)",
                }
            name = re.sub(r"[^A-Za-z0-9._-]", "_", filename or "") or (stem + ".json")
            if not name.endswith(".json"):
                name += ".json"
            keys_dir = self._config_path.parent / "clouddoc-keys"
            path = keys_dir / name
            if path.exists():
                return {"result": "invalid_key", "detail": f"key file already exists: {name}"}

            def _write() -> None:
                keys_dir.mkdir(mode=0o700, exist_ok=True)
                path.touch(mode=0o600)
                path.write_text(credentials_json)

            await asyncio.to_thread(_write)
            credentials_path = str(path)
        elif not credentials_path:
            return {"result": "invalid_key", "detail": "credentials required"}
        elif not os.path.isfile(os.path.expanduser(credentials_path)):
            return {"result": "invalid_key", "detail": f"file not found: {credentials_path}"}
        else:
            credentials_path = os.path.expanduser(credentials_path)

        try:
            conn = await self._reg.add(credentials_path, [], start=True)
        except ValueError as exc:            # a duplicate address
            return {"result": "duplicate", "detail": str(exc)}
        except Exception as exc:  # noqa: BLE001 - a malformed key and anything like it
            logger.warning("[clouddoc] add_connection failed: %s", exc)
            return {"result": "invalid_key", "detail": str(exc)}

        await asyncio.to_thread(self._persist)
        return {
            "result": "ok",
            "connection": _conn_payload(conn, docs_count=0, health="idle"),
        }

    async def add_personal_connection(
        self, brand: str = "feishu", profile: str | None = None,
    ) -> dict[str, Any]:
        """Connect as the person themselves (S.1), with no secret to upload.

        The identity is whatever the platform CLI is logged in as: the file this
        writes holds only ``kind``, ``brand``, the CLI profile and -- once the
        identity resolved -- the open_id and name it was verified as. A missing
        login fails here with the CLI's own hint, before anything is persisted.
        """
        brand = str(brand or "feishu").strip().lower()
        if brand not in ("feishu", "lark"):
            return {
                "result": "unsupported",
                "detail": "个人身份目前仅支持飞书（lark-cli 用户登录）；Google 个人身份尚未支持。",
            }
        keys_dir = self._keys_dir()
        name = f"personal-feishu-{re.sub(r'[^A-Za-z0-9._-]', '_', profile or 'default')}.json"
        path = keys_dir / name
        if path.exists():
            return {"result": "invalid_key", "detail": f"key file already exists: {name}"}
        body = {"kind": "personal", "brand": "feishu"}
        if profile:
            body["profile"] = str(profile)

        def _write(payload: dict) -> None:
            keys_dir.mkdir(mode=0o700, exist_ok=True)
            if not path.exists():
                path.touch(mode=0o600)
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=1))

        await asyncio.to_thread(_write, body)
        try:
            conn = await self._reg.add(str(path), [], start=True)
        except ValueError as exc:            # a duplicate identity
            await asyncio.to_thread(path.unlink)
            return {"result": "duplicate", "detail": str(exc)}
        except Exception as exc:  # noqa: BLE001 - not logged in, CLI missing, and the like
            await asyncio.to_thread(path.unlink)
            logger.warning("[clouddoc] add_personal_connection failed: %s", exc)
            return {"result": "not_logged_in", "detail": str(exc)}
        # Persist the verified identity so a restart anchors on it without asking.
        await asyncio.to_thread(
            _write, {**body, "open_id": conn.address, "name": conn.display_name},
        )
        await asyncio.to_thread(self._persist)
        return {
            "result": "ok",
            "connection": _conn_payload(conn, docs_count=0, health="idle"),
        }

    async def remove_connection(self, connection_id: str) -> dict[str, Any]:
        """Remove a connection: stop the watcher, clear its documents' state, write the
        config back.

        The documents themselves and their sharing on the Google side are untouched;
        removal only means this deployment no longer looks after them. An uploaded key
        file is kept, since deleting credentials is an operations decision and should
        not ride along with one click in a UI.
        """
        conn = await self._reg.remove(connection_id)
        if conn is None:
            return {"result": "not_found"}
        await self._reg.store.gc(self._reg.all_state_keys())
        await asyncio.to_thread(self._persist)
        return {"result": "ok"}

    # ------------------------------------------------------------ stored keys

    # ------------------------------------------------------------ watch panel ops

    def _registry(self):
        reg = getattr(self._reg, "_watch_registry", None)
        if reg is None:
            raise RuntimeError("watch registry not wired")
        return reg

    async def watch_list(self) -> dict[str, Any]:
        """Every standing mandate: level, issuance mode, suspended state -- the
        panel-always-visible guarantee (D3)."""
        snap = self._registry().snapshot()
        return {
            "global_suspended": bool(snap["global"].get("suspended")),
            "watches": [
                {"doc_id": d, **{k: e.get(k) for k in
                                 ("mode", "issued_at", "issued_by", "suspended",
                                  "expires_at", "expired", "budget",
                                  "revoked", "revoked_at")}}
                for d, e in sorted(snap["watches"].items())
            ],
        }

    async def watch_set(self, doc_id: str, mode: str, *,
                        expires_at: float | None = None,
                        permanent: bool = False,
                        budget: dict | None = None) -> dict[str, Any]:
        """Grant or modify. The ask-level confirmation lives in the UI flow; this op
        is the signature's mechanical half, and it lands one audit line.

        Term semantics (E1): an explicit ``expires_at`` is honored verbatim;
        ``permanent=true`` is the owner's explicit word for "no expiry"; saying
        neither issues with the registry's default term. Over RPC a missing
        field and an explicit null both arrive as None, so the permanent flag
        exists precisely to keep "said nothing" and "said forever" apart.

        A mandate names a document this deployment manages. Issuing one for an id
        nobody adopted left an entry that no watcher would ever read and that the
        panel could not show. A document reachable **only** through a personal
        connection has no tiers to grant either (S.3): the person's own permission
        is the whole of the authority, and the personal watcher never acts on it.
        Both refusals are here, on the server, so a UI that offered the control
        anyway would still be refused."""
        reg = getattr(self, "_reg", None)
        owners_fn = getattr(reg, "owners", None)
        owners = owners_fn(doc_id) if owners_fn is not None else (
            [] if reg is None or reg.find_doc(doc_id) is None else [reg.find_doc(doc_id)]
        )
        if reg is not None and not owners:
            return {"ok": False, "detail": "文档未纳管，不能签发档位。"}
        if owners and all(getattr(c, "personal", False) for c in owners):
            return {
                "ok": False, "doc_id": doc_id,
                "detail": "个人连接下的文档没有值守档位：个人身份只通知，不代为处理。",
                "reason": "personal_only",
            }
        if expires_at is not None:
            entry = self._registry().issue(
                doc_id, mode, issued_by="manual",
                expires_at=expires_at, budget=budget,
            )
        elif permanent:
            entry = self._registry().issue(
                doc_id, mode, issued_by="manual",
                expires_at=None, budget=budget,
            )
        else:
            entry = self._registry().issue(
                doc_id, mode, issued_by="manual", budget=budget,
            )
        return {"ok": True, "doc_id": doc_id, "entry": entry}

    # ------------------------------------------------------------ workbench

    async def read_doc(self, doc_id: str) -> dict[str, Any]:
        """The document's text for the workbench's own editor (markdown files have no
        platform editor to embed). Metadata comes with it so the tab can be drawn
        before the text is needed."""
        conn = self._reg.find_doc(doc_id)
        if conn is None:
            return {"result": "not_watched"}
        prov = conn.provider
        try:
            snap = await prov.read(doc_id)
        except ProviderError as exc:
            return {"result": "error", "detail": f"{exc.kind}: {exc}"}
        kind = getattr(snap, "kind", "") or ""
        return {
            "result": "ok",
            "doc_id": doc_id,
            "kind": kind,
            "revision_id": getattr(snap, "revision_id", None),
            "text": getattr(snap, "text", "") or "",
            "url": prov.doc_url(doc_id, kind),
            "provider": conn.kind,
        }

    async def write_doc(
        self, doc_id: str, text: str, base_revision_id: str | None = None,
    ) -> dict[str, Any]:
        """A person's save from the workbench editor, as one whole-file receipt.

        It goes through the same provider write as an agent edit, so it lands in the
        ledger with the person as executor -- the history then shows every change
        to the file, whoever made it. Only markdown is editable here; every other
        kind has the platform's own editor in the frame. The pair is (whole old
        text, whole new text), so the row shows the full before and after.
        """
        conn = self._reg.find_doc(doc_id)
        if conn is None:
            return {"result": "not_watched"}
        prov = conn.provider
        try:
            snap = await prov.read(doc_id)
        except ProviderError as exc:
            return {"result": "error", "detail": f"{exc.kind}: {exc}"}
        if (getattr(snap, "kind", "") or "") != "markdown":
            return {"result": "refused", "detail": "只有 markdown 文件在工作台里编辑；其他格式请用平台自己的编辑器。"}
        current = getattr(snap, "text", "") or ""
        if base_revision_id and getattr(snap, "revision_id", None) and base_revision_id != snap.revision_id:
            return {"result": "conflict", "detail": "文件在你打开之后被改动过，没有保存。请重新载入后再改。",
                    "revision_id": snap.revision_id}
        if text == current:
            return {"result": "unchanged", "revision_id": getattr(snap, "revision_id", None)}
        prov.receipt_meta = {"source": "workbench_save", "executor": "person", "for_comment_ids_by_old": {}}
        try:
            res = await prov.edit_batch(
                doc_id, [(current, text)],
                required_revision_id=getattr(snap, "revision_id", None) or "",
                highlight=False,
            )
        except ProviderError as exc:
            return {"result": "error", "detail": f"{exc.kind}: {exc}"}
        finally:
            prov.receipt_meta = None
        if res.status not in ("applied", "applied_unverified"):
            return {"result": "error", "detail": f"{res.status}: {res.detail}"}
        return {
            "result": "ok",
            "revision_id": res.new_revision_id,
            "receipt_id": getattr(res, "receipt_id", None),
            "status": res.status,
        }

    async def watch_usage(self, doc_id: str) -> dict[str, Any]:
        """The audit view (E1): granted minus used, one watch at a time.

        Granted is the registry's entry; used is the receipts ledger plus the
        audit journal's dispatch and denial lines. The two calibration hints are
        suggestions only -- an idle wide grant reads as "consider narrowing", a
        grant with repeated denials as "consider widening or renewing" -- and
        the decision stays with the owner (recertification at renewal time)."""
        from jiuwenswarm.agents.harness.common.tools.clouddoc.receipts import ReceiptStore

        reg = self._registry()
        entry = reg.get(doc_id)
        usage = reg.usage_summary(doc_id)

        store = ReceiptStore()
        rows = store.list_for(doc_id, limit=200)
        writes = [r for r in rows if r.get("status") in ("applied", "applied_unverified", "reverted")]
        regions: set[str] = set()
        executors: set[str] = set()
        sources: set[str] = set()
        for r in writes:
            executors.add(str(r.get("executor") or ""))
            sources.add(str(r.get("source") or ""))
            for e in r.get("edits") or []:
                if e.get("region"):
                    regions.add(str(e["region"]))
        last_write_at = max((r.get("ts") or 0 for r in writes), default=None)

        hints: list[str] = []
        now = time.time()
        if entry is not None and entry.get("mode") == "apply_scoped" and not writes:
            issued = float(entry.get("issued_at") or now)
            if now - issued >= 14 * 24 * 3600:
                hints.append("idle_wide_grant")
        if sum(usage.get("denials", {}).values()) >= 3:
            hints.append("frequent_denials")

        return {
            "ok": True,
            "doc_id": doc_id,
            "granted": entry,
            "used": {
                **usage,
                "write_batches": len(writes),
                "reverted_batches": sum(1 for r in writes if r.get("status") == "reverted"),
                "last_write_at": last_write_at,
                "executors": sorted(x for x in executors if x),
                "sources": sorted(x for x in sources if x),
                "regions_envelope": sorted(regions),
            },
            "hints": hints,
        }

    async def watch_suspend(self, doc_id: str) -> dict[str, Any]:
        return {"ok": self._registry().suspend(doc_id)}

    async def watch_resume(self, doc_id: str) -> dict[str, Any]:
        return {"ok": self._registry().resume(doc_id)}

    async def watch_revoke(self, doc_id: str) -> dict[str, Any]:
        return {"ok": self._registry().revoke(doc_id)}

    async def watch_revoke_all(self) -> dict[str, Any]:
        """The kill switch (D8)."""
        return {"ok": True, "revoked": self._registry().revoke_all()}

    async def watch_suspend_all(self) -> dict[str, Any]:
        self._registry().suspend_all()
        return {"ok": True}

    async def watch_resume_all(self) -> dict[str, Any]:
        self._registry().resume_all()
        return {"ok": True}

    async def watch_audit(self, limit: int = 100) -> dict[str, Any]:
        """The history view's data feed: one line per lifecycle event."""
        return {"events": self._registry().audit_tail(limit)}

    async def backlog(self) -> dict[str, Any]:
        """The derived backlog view (D2: never persisted -- the platform is the single
        source of truth): assigned-to-us, unresolved, and not dispatchable.

        Live API reads, shaped for a panel that opens often: the connection's
        identity is cached per process (an SA's address does not change under a
        running gateway), and the per-document comment reads fan out together
        instead of queueing -- measured serially, nine watched-off documents
        cost as many round-trips and held the panel for seconds."""
        reg = self._registry()
        identity_cache: dict[str, str] = getattr(self, "_identity_cache", None) or {}
        self._identity_cache = identity_cache

        async def one(conn, me: str, doc_id: str, reason: str) -> list[dict[str, Any]]:
            try:
                comments = await conn.provider.list_comments(doc_id)
            except Exception:  # noqa: BLE001 - one bad doc must not hide the rest
                return []
            return [
                {
                    "doc_id": doc_id, "comment_id": c.comment_id,
                    "reason": reason,
                    "excerpt": (c.content or "")[:120],
                }
                for c in comments
                if (c.assignee_address or "").lower() == me and not c.resolved
            ]

        tasks = []
        for conn in self._reg.list():
            if conn.personal:
                # No mandate is ever issued under a personal connection, so its
                # assignments are not "awaiting authorization" -- they are the
                # person's own inbox, which the notice ledger serves.
                continue
            me = identity_cache.get(conn.id, "")
            if not me:
                # ``self_identity`` answers with an AgentIdentity, not a string. An
                # earlier version read it as one and called ``.lower()`` on the
                # object, so the backlog raised on its first line and had never
                # returned a row. The address is what an assignment names; the
                # display name is not an identity (§6.1).
                identity = await conn.provider.self_identity()
                me = (identity.address or "").strip().lower()
                if me:
                    identity_cache[conn.id] = me
            if not me:
                # Without an address there is nothing to compare an assignee
                # against. Skipping the connection says nothing rather than
                # something wrong.
                logger.warning(
                    "[clouddoc] %s 没有账号地址，积压视图跳过该连接", conn.id
                )
                continue
            for doc_id in list(getattr(conn.watcher, "_docs", []) or []):
                verdict = reg.check(doc_id)
                if verdict.dispatchable:
                    continue
                tasks.append(one(conn, me, doc_id, verdict.reason))
        out: list[dict[str, Any]] = []
        for rows in await asyncio.gather(*tasks):
            out.extend(rows)
        return {"items": out, "count": len(out)}

    # -------------------------------------------------------- un-highlight (D14)

    async def unhighlight(self, receipt_id: str) -> dict[str, Any]:
        """D8.3's manual half: remove one applied batch's highlights by receipt.
        Shielded for the same reason as ``revert``: a document write in flight."""
        return await asyncio.shield(self._unhighlight_unshielded(receipt_id))

    async def _unhighlight_unshielded(self, receipt_id: str) -> dict[str, Any]:
        from jiuwenswarm.agents.harness.common.tools.clouddoc.receipts import ReceiptStore

        store = ReceiptStore()
        r = store.get(receipt_id)
        if r is None or r["status"] != "applied" or not r.get("highlight"):
            return {"ok": False, "detail": "回执不存在、未应用或本就无高亮。"}
        conn = next(
            (c for c in self._reg.list()
             if r["doc_id"] in (getattr(c.watcher, "_docs", []) or [])),
            None,
        ) or (self._reg.list()[0] if self._reg.list() else None)
        if conn is None:
            return {"ok": False, "detail": "没有可用连接。"}
        cleared = await conn.provider.clear_highlight(
            r["doc_id"], [e["new"] for e in r["edits"]]
        )
        store.mark_unhighlighted(receipt_id)
        return {"ok": True, **cleared}

    def _keys_dir(self) -> pathlib.Path:
        return pathlib.Path(self._config_path).parent / "clouddoc-keys"

    def _paths_in_use(self) -> set[str]:
        return {os.path.realpath(c.credentials_file) for c in self._reg.list()}

    async def list_keys(self) -> dict[str, Any]:
        """Every key file under clouddoc-keys/, and whether a connection uses it.

        remove_connection keeps key files on purpose -- deleting credentials is an
        operations decision, not a side effect of a click. This is where those kept
        files stop being invisible: without a listing, finding one back means ls in a
        dotfile directory, and deleting one means knowing it is safe to."""
        rows: list[dict[str, Any]] = []
        keys_dir = self._keys_dir()
        in_use = self._paths_in_use()
        if keys_dir.is_dir():
            for f in sorted(keys_dir.glob("*.json"),
                            key=lambda x: x.stat().st_mtime, reverse=True):
                kind = "service"
                try:
                    data = json.loads(f.read_text())
                    email = str(data.get("client_email") or "")
                    address = email or str(data.get("app_id") or "")
                    if str(data.get("kind") or "").lower() == "personal":
                        kind = "personal"
                        address = str(data.get("name") or data.get("open_id") or "personal")
                except Exception:  # noqa: BLE001 - an unreadable key still gets listed
                    email = address = ""
                rows.append({
                    "filename": f.name,
                    "path": str(f),
                    "client_email": email,
                    # What the key names, whichever vendor: the SA email, the app id,
                    # or the person a personal file was verified as.
                    "address": address,
                    "kind": kind,
                    "in_use": os.path.realpath(f) in in_use,
                })
        return {"result": "ok", "keys": rows}

    async def delete_key(self, filename: str) -> dict[str, Any]:
        """Delete one stored key file. Refused while any connection uses it.

        This deletes **the local copy only**. The credential itself stays valid until
        it is revoked in the cloud console -- the panel must not let "deleted here"
        read as "revoked", so the frontend wording says file, not credential.

        ``filename`` must be a bare name inside clouddoc-keys/: anything with a path
        separator is refused, or this endpoint is an arbitrary-file delete."""
        name = os.path.basename(str(filename or ""))
        if not name or name != filename or not name.endswith(".json"):
            return {"result": "bad_name"}
        path = self._keys_dir() / name
        if not path.is_file():
            return {"result": "not_found"}
        if os.path.realpath(path) in self._paths_in_use():
            return {"result": "in_use"}
        await asyncio.to_thread(path.unlink)
        return {"result": "ok"}

    # ------------------------------------------------------------ internals

    async def _probe(self, conn: CloudDocConnection, doc_id: str) -> dict[str, Any]:
        """One live fetch of the facts: capabilities plus title. The vocabulary it
        returns matches the UI's."""
        try:
            caps = await conn.provider.capabilities(doc_id)
        except ProviderError as exc:
            if exc.kind in ("not_found", "forbidden"):
                return {"result": "not_shared", "detail": exc.kind}
            return {"result": "unknown", "detail": f"{exc.kind}: {exc}"}
        if not caps.can_edit and not conn.personal:
            return {"result": "comment_only"}
        if conn.personal and not caps.can_read:
            return {"result": "not_shared", "detail": "no_read_access"}
        try:
            title = await conn.provider.title(doc_id)
        except Exception:  # noqa: BLE001 - a title is decoration and must not block the
            # main path when it cannot be read
            title = ""
        # The format, for the panel's icon and for the link: a spreadsheet's editor is
        # at a different path from a document's. Decorative like the title, and treated
        # the same way -- a failure to read it must not turn an adoptable document away.
        kind = ""
        fn = getattr(conn.provider, "doc_kind", None)
        if fn is not None:
            try:
                kind = await fn(doc_id)
            except Exception:  # noqa: BLE001
                kind = ""
        return {"result": "ok", "title": title, "kind": kind}

    def _mutate_config(self, data: dict) -> dict:
        """Write the registry's current state into the clouddoc section.

        The first write upgrades the old single-connection keys away. The reader
        accepts both shapes, which makes the upgrade one-way and safe.
        """
        section = data.setdefault("clouddoc", {})
        # Adding a connection **is** the act of enabling the feature -- there is no other
        # switch in the UI, and the factory default is off. Without this, a key added
        # through the panel works until the next restart and then goes quiet.
        if self._reg.list():
            section["enabled"] = True
            self._reg.enabled = True
        section["connections"] = [
            {
                "credentials_file": c.credentials_file,
                "documents": list(c.watcher._docs),
                "kind": c.identity_kind,
            }
            for c in self._reg.list()
        ]
        section.pop("credentials_file", None)
        section.pop("documents", None)
        return data

    def _current_mode(self) -> str:
        """The deployment's D21 mode, read from the config file each call."""
        try:
            data = load_yaml_round_trip(self._config_path)
            mode = str(((data or {}).get("clouddoc") or {}).get("mode") or "mandate").strip().lower()
        except Exception:  # noqa: BLE001 - an unreadable config reads as the default
            mode = "mandate"
        return mode if mode in ("mandate", "recorded", "direct") else "mandate"

    @staticmethod
    def _ask_channel_available() -> bool:
        try:
            from jiuwenswarm.agents.harness.common.tools.clouddoc.clouddoc_tools import (
                _ask_channel_available,
            )

            return bool(_ask_channel_available())
        except Exception:  # noqa: BLE001 - an unreadable config reads as no channel
            return False

    def _current_model_name(self) -> str:
        """The model unattended turns run on, read from the config file each call.
        Empty means the deployment default."""
        try:
            data = load_yaml_round_trip(self._config_path)
            return str(((data or {}).get("clouddoc") or {}).get("model_name") or "").strip()
        except Exception:  # noqa: BLE001 - an unreadable config reads as the default
            return ""

    def _currently_enabled(self) -> bool:
        try:
            data = load_yaml_round_trip(self._config_path)
            return bool(((data or {}).get("clouddoc") or {}).get("enabled", True))
        except Exception:  # noqa: BLE001
            return True

    def _current_signature(self) -> str:
        try:
            data = load_yaml_round_trip(self._config_path)
            return str(((data or {}).get("clouddoc") or {}).get(SIGNATURE_KEY) or "")
        except Exception:  # noqa: BLE001 - an unreadable config reads as the default
            return ""

    def _current_choices(self) -> dict[str, str]:
        try:
            data = load_yaml_round_trip(self._config_path)
            raw = ((data or {}).get("clouddoc") or {}).get("identity_choice") or {}
            return {str(k): str(v) for k, v in dict(raw).items() if str(v) == "personal"}
        except Exception:  # noqa: BLE001
            return {}

    async def set_signature(self, text: str) -> dict[str, Any]:
        """Word the person's half of the personal signature (S.5). Empty restores
        the default wording; it never removes the signature, and the receipt number
        is not part of what can be set here."""
        from jiuwenswarm.agents.harness.common.tools.clouddoc.signature import (
            DEFAULT_SIGNATURE_TEMPLATE,
            signature_body,
        )

        body = " ".join(str(text or "").split())[:120]

        def mutate(data: dict) -> dict:
            section = data.setdefault("clouddoc", {})
            if body:
                section[SIGNATURE_KEY] = body
            else:
                section.pop(SIGNATURE_KEY, None)
            return data

        self._write_config(mutate)
        return {
            "ok": True,
            "personal_signature": body,
            "preview": signature_body(body or DEFAULT_SIGNATURE_TEMPLATE, name="{name}"),
        }

    async def set_identity_choice(self, doc_id: str, choice: str) -> dict[str, Any]:
        """Choose which identity executes on a document adopted both ways (S.2).
        Only ``personal`` is written; ``service`` is the default and clears the entry."""
        choice = str(choice or "").strip().lower()
        if choice not in ("service", "personal"):
            return {"ok": False, "detail": f"未知身份 {choice!r}（可选 service / personal）。"}
        owners = self._reg.owners(doc_id)
        if choice == "personal" and not any(c.personal for c in owners):
            return {"ok": False, "detail": "这篇文档没有个人连接纳管，无法以个人身份执行。"}

        def mutate(data: dict) -> dict:
            section = data.setdefault("clouddoc", {})
            choices = section.get("identity_choice")
            if not isinstance(choices, dict):
                choices = {}
                section["identity_choice"] = choices
            if choice == "personal":
                choices[doc_id] = "personal"
            else:
                choices.pop(doc_id, None)
            if not choices:
                section.pop("identity_choice", None)
            return data

        self._write_config(mutate)
        return {"ok": True, "doc_id": doc_id, "identity": choice}

    # ------------------------------------------------- Feishu personal identity (device code)

    # The lark-cli domains a personal connection needs: documents and drive for
    # the body and comments, sheets/slides for the other formats, wiki for
    # wiki-hosted documents.
    FEISHU_LOGIN_DOMAINS = "docs,drive,sheets,slides,wiki"
    FEISHU_LOGIN_SLACK_S = 30.0

    async def _lark_exec(self, args: list[str], *, timeout: float = 60.0) -> tuple[int, str, str]:
        """Run one ``lark-cli`` command. The seam the login tests stub."""
        binary = "lark-cli"
        try:
            proc = await asyncio.create_subprocess_exec(
                binary, *args,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
        except OSError as exc:
            return 127, "", f"cannot start {binary}: {exc}"
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise
        return proc.returncode or 0, out.decode("utf-8", "replace"), err.decode("utf-8", "replace")

    @staticmethod
    def _lark_json(text: str) -> dict:
        text = (text or "").strip()
        if not text.startswith("{"):
            return {}
        try:
            data = json.loads(text)
        except ValueError:
            return {}
        return data if isinstance(data, dict) else {}

    @classmethod
    def _lark_error(cls, out: str, err: str, code: int) -> str:
        for text in (err, out):
            data = cls._lark_json(text)
            e = data.get("error")
            if isinstance(e, dict):
                return str(e.get("message") or e.get("subtype") or e.get("type") or "")
        return (err or out or "").strip()[:300] or f"lark-cli exited with {code}"

    def _feishu_flows(self) -> dict[str, dict[str, Any]]:
        flows = getattr(self, "_feishu_login_flows", None)
        if flows is None:
            flows = {}
            self._feishu_login_flows = flows
        return flows

    async def feishu_user_logged_in(self) -> bool:
        try:
            code, out, _ = await self._lark_exec(["auth", "status", "--json"], timeout=30)
        except asyncio.TimeoutError:
            return False
        data = self._lark_json(out)
        user = (data.get("identities") or {}).get("user") or {}
        return bool(user.get("available"))

    async def feishu_login_start(self) -> dict[str, Any]:
        """Begin the device-code login inside the swarm (no terminal anywhere).

        ``lark-cli auth login --no-wait --json`` returns a verification URL (with
        the user code in its query), a device code and an expiry; the URL is
        rendered to a PNG by ``lark-cli auth qrcode``. The device code stays in
        this process's memory for the life of the flow -- never on disk, never in
        a response -- and the completion (``--device-code``, which blocks until
        the person scans, denies, or the code expires) runs as a background task
        whose outcome ``feishu_login_status`` reports. A user who is already
        logged in gets ``already`` so the caller connects straight away.
        """
        if await self.feishu_user_logged_in():
            return {"result": "already"}
        try:
            code, out, err = await self._lark_exec(
                ["auth", "login", "--no-wait", "--json", "--domain", self.FEISHU_LOGIN_DOMAINS],
                timeout=60,
            )
        except asyncio.TimeoutError:
            return {"result": "error", "detail": "lark-cli 没有在 60 秒内返回登录链接。"}
        if code != 0:
            return {"result": "error", "detail": self._lark_error(out, err, code)}
        data = self._lark_json(out)
        device_code = str(data.get("device_code") or "")
        url = str(data.get("verification_url") or data.get("verification_uri") or "")
        if not device_code or not url:
            return {"result": "error", "detail": "lark-cli 返回的登录信息不完整（缺少设备码或链接）。"}
        try:
            expires_in = float(data.get("expires_in") or 600)
        except (TypeError, ValueError):
            expires_in = 600.0
        from urllib.parse import parse_qs, urlsplit

        user_code = str(data.get("user_code") or (parse_qs(urlsplit(url).query).get("user_code") or [""])[0])
        qr_b64 = await self._feishu_qr_png(url)
        state = uuid.uuid4().hex
        flow: dict[str, Any] = {
            "state": state, "device_code": device_code, "verification_url": url,
            "user_code": user_code, "expires_at": time.time() + expires_in,
            "status": "pending", "detail": "", "connection": None, "identity": None,
        }
        self._feishu_flows()[state] = flow
        flow["task"] = asyncio.create_task(
            self._feishu_login_wait(flow, expires_in), name=f"clouddoc-feishu-login-{state[:8]}",
        )
        return {
            "result": "ok", "state": state, "verification_url": url, "user_code": user_code,
            "qr_png_base64": qr_b64, "expires_at": flow["expires_at"],
        }

    async def _feishu_qr_png(self, url: str) -> str:
        """The verification link as a PNG (base64), via the CLI's own renderer.
        Empty on failure: the link and the user code still get the person there."""
        import base64
        import tempfile

        fd, path = tempfile.mkstemp(prefix="jiuwen-lark-qr-", suffix=".png", dir="/tmp")
        os.close(fd)
        try:
            code, out, err = await self._lark_exec(
                ["auth", "qrcode", url, "--output", path, "--size", "256"], timeout=30,
            )
            if code != 0:
                logger.warning("[clouddoc] lark-cli qrcode failed: %s", self._lark_error(out, err, code))
                return ""
            data = await asyncio.to_thread(pathlib.Path(path).read_bytes)
            return base64.b64encode(data).decode("ascii") if data else ""
        except Exception:  # noqa: BLE001 - the QR is a convenience over the link
            logger.exception("[clouddoc] qr render failed")
            return ""
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass

    async def _feishu_login_wait(self, flow: dict[str, Any], expires_in: float) -> None:
        """Complete the device flow: block on ``--device-code`` until the person
        scans (exit 0), denies, or the code expires; then connect as them."""
        try:
            code, out, err = await self._lark_exec(
                ["auth", "login", "--device-code", flow["device_code"], "--json"],
                timeout=expires_in + self.FEISHU_LOGIN_SLACK_S,
            )
        except asyncio.TimeoutError:
            flow["status"], flow["detail"] = "expired", "登录链接已过期（十分钟内没有完成扫码）。请重新开始。"
            return
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            flow["status"], flow["detail"] = "error", str(exc)
            return
        finally:
            flow["device_code"] = ""
        if code != 0:
            detail = self._lark_error(out, err, code)
            low = detail.lower()
            expired = "expire" in low or "过期" in detail
            flow["status"] = "expired" if expired else "denied"
            flow["detail"] = detail or ("登录链接已过期。" if expired else "授权未完成或被拒绝。")
            return
        result = await self.add_personal_connection("feishu")
        if result.get("result") == "ok":
            flow["status"], flow["connection"] = "done", result.get("connection")
            conn = result.get("connection") or {}
            flow["identity"] = {"open_id": conn.get("agent_address"), "name": conn.get("agent_display")}
        elif result.get("result") == "duplicate":
            flow["status"], flow["detail"] = "done", "这个飞书账号已经连接过了。"
            flow["connection"] = next(
                (_conn_payload(c) for c in self._reg.list() if c.personal and c.kind == "feishu"), None,
            )
        else:
            flow["status"], flow["detail"] = "error", str(result.get("detail") or result.get("result") or "")

    async def feishu_login_status(self, state: str) -> dict[str, Any]:
        flow = self._feishu_flows().get(str(state or ""))
        if flow is None:
            return {"status": "error", "detail": "没有这个登录请求；请重新开始。"}
        if flow["status"] == "pending" and time.time() > float(flow["expires_at"]) + self.FEISHU_LOGIN_SLACK_S:
            flow["status"], flow["detail"] = "expired", "登录链接已过期。请重新开始。"
            task = flow.get("task")
            if task is not None and not task.done():
                task.cancel()
        out = {
            "status": flow["status"], "detail": flow["detail"], "connection": flow["connection"],
            "identity": flow["identity"], "expires_at": flow["expires_at"],
            "verification_url": flow["verification_url"], "user_code": flow["user_code"],
        }
        if flow["status"] != "pending":
            # One flow, one outcome: a finished flow is dropped once reported.
            self._feishu_flows().pop(flow["state"], None)
        return out

    # ------------------------------------------------- Google personal identity (OAuth)

    GOOGLE_OAUTH_KEY = "google_oauth"
    # How long a started consent flow waits for the browser to come back.
    GOOGLE_OAUTH_TIMEOUT_S = 600.0

    def _google_oauth_cfg(self) -> dict[str, str]:
        try:
            data = load_yaml_round_trip(self._config_path)
            raw = ((data or {}).get("clouddoc") or {}).get(self.GOOGLE_OAUTH_KEY) or {}
            return {
                "client_id": str(raw.get("client_id") or ""),
                "client_secret": str(raw.get("client_secret") or ""),
            }
        except Exception:  # noqa: BLE001
            return {"client_id": "", "client_secret": ""}

    async def set_google_oauth(self, client_id: str, client_secret: str) -> dict[str, Any]:
        """Register the OAuth client a self-hoster created in their own GCP project
        (``clouddoc.google_oauth``). Empty values clear it."""
        client_id = str(client_id or "").strip()
        client_secret = str(client_secret or "").strip()

        def mutate(data: dict) -> dict:
            section = data.setdefault("clouddoc", {})
            if client_id or client_secret:
                section[self.GOOGLE_OAUTH_KEY] = {"client_id": client_id, "client_secret": client_secret}
            else:
                section.pop(self.GOOGLE_OAUTH_KEY, None)
            return data

        self._write_config(mutate)
        return {"ok": True, "configured": bool(client_id and client_secret), "client_id": client_id}

    def _oauth_flows(self) -> dict[str, dict[str, Any]]:
        flows = getattr(self, "_google_flows", None)
        if flows is None:
            flows = {}
            self._google_flows = flows
        return flows

    async def google_oauth_start(self) -> dict[str, Any]:
        """Begin the consent flow: a loopback listener on an ephemeral port and the
        link to open. The exchange and the connection follow on their own once the
        browser comes back; ``google_oauth_status`` reports where it got to, and
        ``google_oauth_finish`` is the paste-the-code fallback."""
        from jiuwenswarm.agents.harness.common.tools.clouddoc.google_oauth import (
            LoopbackReceiver,
            build_auth_url,
            new_state,
        )

        cfg = self._google_oauth_cfg()
        if not cfg["client_id"] or not cfg["client_secret"]:
            return {
                "result": "not_configured",
                "detail": "请先在设置里填写 Google OAuth 客户端的 client_id 与 client_secret。",
            }
        state = new_state()
        receiver = LoopbackReceiver(state)
        redirect_uri = await receiver.start()
        auth_url = build_auth_url(cfg["client_id"], redirect_uri, state)
        flow: dict[str, Any] = {
            "state": state, "receiver": receiver, "redirect_uri": redirect_uri,
            "status": "pending", "detail": "", "connection": None, "task": None,
        }
        self._oauth_flows()[state] = flow

        async def run() -> None:
            try:
                code = await receiver.wait(timeout=self.GOOGLE_OAUTH_TIMEOUT_S)
            except asyncio.TimeoutError:
                flow["status"], flow["detail"] = "error", "授权超时：十分钟内没有收到回调。请重新开始。"
                return
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                flow["status"], flow["detail"] = "error", str(exc)
                return
            await self._google_finish(flow, code)

        flow["task"] = asyncio.create_task(run(), name=f"clouddoc-google-oauth-{state[:8]}")
        return {"result": "ok", "state": state, "auth_url": auth_url, "redirect_uri": redirect_uri}

    async def google_oauth_finish(self, state: str, code_or_url: str) -> dict[str, Any]:
        """The manual fallback: the person pastes the redirected URL or the bare
        code (a remote browser cannot reach this machine's loopback)."""
        from jiuwenswarm.agents.harness.common.tools.clouddoc.google_oauth import parse_code

        flow = self._oauth_flows().get(str(state or ""))
        if flow is None:
            return {"status": "error", "detail": "没有这个授权请求；请重新开始。"}
        if flow["status"] != "pending":
            return await self.google_oauth_status(state)
        try:
            code = parse_code(code_or_url, expected_state=flow["state"])
        except ProviderError as exc:
            return {"status": "pending", "detail": str(exc)}
        # Settle the listener's wait too, so the background task ends cleanly
        # rather than finishing a second time when the browser also comes back.
        task = flow.get("task")
        if task is not None and not task.done():
            task.cancel()
        await flow["receiver"].close()
        await self._google_finish(flow, code)
        return await self.google_oauth_status(state)

    async def google_oauth_status(self, state: str) -> dict[str, Any]:
        flow = self._oauth_flows().get(str(state or ""))
        if flow is None:
            return {"status": "error", "detail": "没有这个授权请求；请重新开始。"}
        return {"status": flow["status"], "detail": flow["detail"], "connection": flow["connection"]}

    async def _google_finish(self, flow: dict[str, Any], code: str) -> None:
        """Exchange the code, learn who the token belongs to, write the token file
        (0600, named by email), and add the connection. Every failure lands in the
        flow's status with a sentence the person can act on; no file survives a
        failure."""
        from jiuwenswarm.agents.harness.common.tools.clouddoc.google_oauth import (
            authorized_user_info,
            exchange_code,
            write_authorized_user_file,
        )

        cfg = self._google_oauth_cfg()
        exchange = getattr(self, "_oauth_exchange", None) or (
            lambda cid, secret, c, uri: exchange_code(cid, secret, c, uri)
        )
        try:
            token = await asyncio.to_thread(
                exchange, cfg["client_id"], cfg["client_secret"], code, flow["redirect_uri"],
            )
        except Exception as exc:  # noqa: BLE001 - reported, never raised out of the task
            flow["status"], flow["detail"] = "error", str(exc)
            return
        info = authorized_user_info(cfg["client_id"], cfg["client_secret"], token)
        keys_dir = self._keys_dir()
        pending = keys_dir / f"personal-google-pending-{flow['state'][:8]}.json"
        try:
            await asyncio.to_thread(write_authorized_user_file, pending, info)
            provider = self._reg._provider_factory(str(pending))
            ident = await provider.self_identity()
            email = str(ident.address or "").strip().lower()
            if not email:
                raise ProviderError("auth", "无法取得授权账号的邮箱。")
            final = keys_dir / f"personal-google-{re.sub(r'[^A-Za-z0-9._@+-]', '_', email)}.json"
            if final.exists():
                raise ValueError(f"duplicate connection: {email}")
            info = {**info, "email": email, "name": ident.display_name or email}
            await asyncio.to_thread(write_authorized_user_file, final, info)
            await asyncio.to_thread(pending.unlink)
        except Exception as exc:  # noqa: BLE001
            if pending.exists():
                await asyncio.to_thread(pending.unlink)
            flow["status"], flow["detail"] = "error", str(exc)
            return
        try:
            conn = await self._reg.add(str(final), [], start=True)
        except ValueError as exc:
            await asyncio.to_thread(final.unlink)
            flow["status"], flow["detail"] = "error", f"duplicate: {exc}"
            return
        except Exception as exc:  # noqa: BLE001
            await asyncio.to_thread(final.unlink)
            flow["status"], flow["detail"] = "error", str(exc)
            return
        await asyncio.to_thread(self._persist)
        flow["status"] = "done"
        flow["connection"] = _conn_payload(conn, docs_count=0, health="idle")

    def bind_notifier(self, push) -> None:
        """Give the registry the web channel's broadcast, once the channel exists."""
        self._reg.notifier = push

    async def notices(self, limit: int = 100, unread_only: bool = True) -> dict[str, Any]:
        store = self._reg.notice_store
        if store is None:
            return {"notices": []}
        rows = await asyncio.to_thread(store.list, unread_only=unread_only, limit=limit)
        return {"notices": rows}

    async def notice_ack(
        self, notice_id: str | None = None, doc_id: str | None = None
    ) -> dict[str, Any]:
        store = self._reg.notice_store
        if store is None:
            return {"ok": True, "acked": 0}
        n = await asyncio.to_thread(store.ack, notice_id or None, doc_id=doc_id or None)
        return {"ok": True, "acked": int(n)}

    async def set_mode(self, mode: str) -> dict[str, Any]:
        """Switch between Direct and Mandate (D21). The UI offers exactly these
        two; the config-only ablation tier is never set from here. The switch is
        an explicit act -- the caller's UI carries the confirmation -- and lands
        one audit line on the watch journal, since it changes what every standing
        grant can do."""
        mode = str(mode or "").strip().lower()
        if mode not in ("mandate", "direct"):
            return {"ok": False, "detail": f"未知档位：{mode!r}（可选 mandate / direct）。"}

        def mutate(data: dict) -> dict:
            section = data.setdefault("clouddoc", {})
            section["mode"] = mode
            return data

        self._write_config(mutate)
        try:
            self._registry()._audit("mode", None, value=mode)
        except Exception:  # noqa: BLE001 - the switch stands even if the line is lost
            logger.exception("[clouddoc] mode audit line lost")
        return {"ok": True, "mode": mode}

    async def set_model(self, model_name: str) -> dict[str, Any]:
        """Pin the model unattended turns run on, deployment-wide (§25.3: wiring
        lives in Settings). Empty restores the default. The name is validated the
        way cron validates its jobs' models, so what lands in the config is a key
        the agentserver can resolve."""
        from jiuwenswarm.gateway.cron.models import validate_cron_model

        try:
            canonical = validate_cron_model(model_name) or ""
        except ValueError as exc:
            return {"ok": False, "detail": str(exc)}

        def mutate(data: dict) -> dict:
            section = data.setdefault("clouddoc", {})
            section["model_name"] = canonical
            return data

        self._write_config(mutate)
        return {"ok": True, "model_name": canonical}

    def _persist(self) -> None:
        """Write the config back. **This must go through update_config** rather than a
        load and dump of its own.

        update_config holds a threading lock and a portalocker file lock, which puts
        the whole read-modify-write inside one critical section. A bare load and dump
        makes each individual write atomic, through a temporary file and a rename, but
        not the cycle around it: while the gateway saves a document list, the
        agentserver may be writing permissions or memory config, each process reads the
        old version and writes the whole file back, and whichever lands second erases
        the other's change. That cross-process lock exists for exactly this pair.
        """
        self._write_config(self._mutate_config)

    def _write_config(self, mutate) -> None:
        if self._config_path == CONFIG_YAML_PATH:
            update_config(mutate)
            return
        # A test injected a different path. update_config is bound to the global
        # CONFIG_YAML_PATH, so fall back to reading and writing directly -- tests are
        # single-threaded and single-process, with nothing to race.
        data = load_yaml_round_trip(self._config_path)
        if not isinstance(data, dict):
            raise RuntimeError(f"config not a mapping: {self._config_path}")
        dump_yaml_round_trip(self._config_path, mutate(data))


# --------------------------------------------------------------- background discovery

# Discovery lists a connection's whole Drive surface, which costs far more quota than
# a comment poll. It runs on its own slow cadence rather than per tick.
DISCOVERY_INTERVAL_SECONDS = 300.0


async def discover_shared_periodically(
    panel: "CloudDocPanel",
    *,
    interval_seconds: float = DISCOVERY_INTERVAL_SECONDS,
    sleep_fn=None,
) -> None:
    """Adopt newly shared documents on a timer, for as long as the gateway runs.

    Adoption already happens without anyone confirming it -- ``sync_shared_docs`` treats
    the share itself as the deliberate act. What it lacked was a trigger the deployment
    controls: the only caller was the Docs panel, which runs it when the panel mounts.
    A deployment driven entirely from a chat channel may never open the web UI, and a
    document shared with the service account then stays outside management indefinitely,
    with nothing to say why the agent cannot see it.

    This changes when adoption happens, not what it does. The tier a document lands on
    is still the adoption policy's to decide (D2, ``auto_watch_on_adopt``, off by
    default), so a document adopted here is watched and nothing more -- no turn is
    dispatched until someone grants one.

    A failing round is logged and the loop continues: discovery is a convenience whose
    failure must not take down the process that also polls comments.
    """
    sleep = sleep_fn or asyncio.sleep
    while True:
        await sleep(interval_seconds)
        for conn in panel._reg.list():
            if conn.personal:
                # S.6: a person's share list is only ever listed, never adopted
                # unasked -- and listing it on a timer would spend quota on nothing.
                continue
            try:
                out = await panel.sync_shared_docs(conn.id)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - one bad round must not end the loop
                logger.exception("[clouddoc] 共享文档发现失败：%s", conn.address)
                continue
            adopted = out.get("adopted") or []
            if adopted:
                logger.info(
                    "[clouddoc] 定期发现纳管了 %d 篇文档：%s",
                    len(adopted), conn.address,
                )
            for row in out.get("needs_editor") or []:
                # Shared comment-only. Admission would refuse it anyway, so saying which
                # document and why beats an entry that silently never works.
                logger.warning(
                    "[clouddoc] %s 以仅评论权共享，未纳管（需要编辑权）：%s",
                    row.get("title") or row.get("doc_id"), conn.address,
                )
