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
* **There is no "remove this document".** Turning the watch off is what the
  panel does instead. A local removal would have been a claim about the platform
  (the share is still there), so discovery would have overruled it on the next
  pass; turning the watch off claims only what this deployment owns: stop the
  standing delegation, and drop the row out of the default view. The
  document stays adopted and stays polled, so a collaborator @-ing the agent
  there still hears why nothing will happen -- and no turn is dispatched, so it
  costs a comment poll and no model call.
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
from typing import Any

from jiuwenswarm.extensions.co_scribe.backend.toolkit.providers.provider import ProviderError
from jiuwenswarm.common.config import (
    CONFIG_YAML_PATH,
    dump_yaml_round_trip,
    load_yaml_round_trip,
    update_config,
)
from jiuwenswarm.extensions.co_scribe.backend.host.authority.connections import CloudDocConnection, CloudDocConnections

logger = logging.getLogger(__name__)

# Display names by provider.kind. A second provider registers itself here.
_PROVIDER_NAMES = {"google": "Google Docs", "feishu": "飞书文档"}


def _key_stem(parsed: Any) -> str | None:
    """The file stem an uploaded key gets, from the key's own shape -- the same test
    ``factory.detect_vendor`` applies once the file exists. ``None`` when the JSON is
    neither vendor's key, so the panel refuses before writing anything."""
    if not isinstance(parsed, dict):
        return None
    email = str(parsed.get("client_email") or "")
    if email:
        return email.split("@")[0]
    if parsed.get("app_id") and parsed.get("app_secret"):
        return str(parsed["app_id"])
    return None


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
            conns.append({
                "id": c.id,
                "provider": c.kind,
                "provider_name": _PROVIDER_NAMES.get(c.kind, c.kind),
                "agent_address": c.address,
                "agent_display": c.display_name,
                "docs_count": summary["total"],
                **{k: v for k, v in summary.items() if k != "total"},
            })
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
        }

    async def list_docs(self) -> list[dict[str, Any]]:
        """A snapshot of every connection's documents, each row carrying its owner.

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
        for c in self._reg.list():
            for doc_id in list(c.watcher._docs):
                health = await self._reg.store.doc_health(doc_id)
                meta = health.get("panel_meta") or {}
                # The format, so the panel can tell a spreadsheet from a document --
                # both in the icon it draws and in the link it opens, since a
                # spreadsheet's editor lives at a different path. Recorded at adoption;
                # asked of the provider for a document adopted before this existed, and
                # left empty when even that cannot answer, which the UI reads as "a
                # document" rather than showing nothing.
                kind = meta.get("kind") or ""
                if not kind and doc_id not in probed:
                    fn = getattr(c.provider, "doc_kind", None)
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
                    note = getattr(c.provider, "note_kind", None)
                    if note is not None:
                        note(doc_id, kind)
                # The title heals the same way the kind does: a document adopted
                # before titles were recorded shows its id prefix forever unless
                # someone asks the provider once and caches the answer.
                title = meta.get("title") or ""
                if not title and doc_id not in probed:
                    probed.add(doc_id)
                    try:
                        title = await c.provider.title(doc_id)
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
                    fn = getattr(c.provider, "canonical_url", None)
                    if fn is not None:
                        try:
                            u = str(await fn(doc_id) or "")
                            if u.startswith("http"):
                                url = u
                                await self._reg.store.set_panel_meta(doc_id, url=u)
                        except Exception:  # noqa: BLE001 - a dead link is not an outage
                            pass
                rows.append({
                    "doc_id": doc_id,
                    "url": url or c.provider.doc_url(doc_id, kind),
                    "title": title or doc_id[:12] + "…",
                    "kind": kind,
                    "checked_at": meta.get("checked_at"),
                    # The document's own model pin. Empty means it follows the
                    # deployment default, which the record dialog spells out.
                    "model_name": self._expanded(str(meta.get("model_name") or "")),
                    "status": self._status_of(health),
                    "retry_at": health.get("until"),
                    "provider": c.kind,
                    "provider_name": _PROVIDER_NAMES.get(c.kind, c.kind),
                    "connection_id": c.id,
                })
        return rows

    @staticmethod
    def _status_of(health: dict[str, Any]) -> str:
        if health.get("failed"):
            # comment_only is a configuration mistake the user can fix themselves, so
            # it gets its own state and its own guidance. Every other failure -- three
            # consecutive 403s or 404s -- is simply frozen.
            if health.get("failed_reason") == "comment_only_access":
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
        states = [self._status_of(await self._reg.store.doc_health(d)) for d in docs]
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

        Nothing here needs a memory of what a person dismissed. Hiding a document is
        a watch turned off, and the document **stays adopted**; the ``in watched``
        skip below already passes over it, so there is no local "removed" state for
        discovery to contradict. A local removal would have been a claim about the
        platform -- the share is still there -- and discovery would have overruled it
        on the next pass, correctly.
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

        watched = set(self._reg.all_docs())
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
        mine = [d for d in self._reg.all_docs() if self._reg.find_doc(d) is conn]
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

    # Which failure tells the person the most. ``comment_only`` names a specific
    # mistake with a specific fix, so it outranks ``not_shared``, which outranks a
    # transient ``unknown``.
    _DIAGNOSIS_RANK = {"comment_only": 3, "not_shared": 2, "unknown": 1}

    async def add_doc(self, url_or_id: str, connection_id: str | None = None) -> dict[str, Any]:
        """Verify a pasted link, and adopt it if it checks out.

        This is not how documents get in -- sharing is, and ``sync_shared_docs``
        adopts on its own. What a person needs here is the answer to "why isn't
        mine in the list?", which discovery cannot give because it never saw that
        document.

        Which connection to ask is not a question worth putting to the person: the
        link says which provider, and only the identity the document was actually
        shared with can see it. So with no connection named, every connection that
        can parse the link is tried, and the most informative verdict is returned.
        """
        if connection_id:
            conn = self._reg.get(connection_id)
            if conn is None:
                return {"result": "no_connection"}
            try:
                doc_id = conn.provider.parse_doc_ref(url_or_id)
            except ProviderError as exc:
                return {"result": "invalid", "detail": str(exc)}
            return await self._add_one(conn, doc_id, url_or_id)

        candidates: list[tuple[Any, str]] = []
        last_invalid = ""
        for c in self._reg.list():
            try:
                candidates.append((c, c.provider.parse_doc_ref(url_or_id)))
            except ProviderError as exc:
                last_invalid = str(exc)
        if not candidates:
            if not self._reg.list():
                return {"result": "no_connection"}
            return {"result": "invalid", "detail": last_invalid}

        best: dict[str, Any] | None = None
        for c, doc_id in candidates:
            out = await self._add_one(c, doc_id, url_or_id)
            if out.get("result") in ("ok", "exists"):
                return out
            rank = self._DIAGNOSIS_RANK.get(str(out.get("result")), 0)
            if best is None or rank > self._DIAGNOSIS_RANK.get(str(best.get("result")), 0):
                best = out
        return best or {"result": "unknown"}

    async def _add_one(
        self, conn: Any, doc_id: str, url_or_id: str
    ) -> dict[str, Any]:
        """Verify one document against one connection, adopting it if it checks out."""
        owner = self._reg.find_doc(doc_id)
        if owner is not None:
            # Re-pasting a link is how a document adopted before URL persistence
            # heals: the token is known, only the tenant-domain link was lost.
            if url_or_id.strip().startswith("http"):
                await self._reg.store.set_panel_meta(
                    doc_id, url=url_or_id.split("?", 1)[0].split("#", 1)[0]
                )
            # A document belongs to one connection: two identities on one document
            # means every mention answered twice, and state keyed by doc_id means the
            # two overwrite each other. The owner is returned in full so the UI can
            # say which connection already has it.
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
        self._reg.policy_issue([doc_id])
        await asyncio.to_thread(self._persist)
        return {"result": "ok", "doc_id": doc_id, "title": probe.get("title")}

    # There is no ``remove_doc``. Taking a document out of the panel's list was a
    # claim this deployment could not make: the share lives on the platform, so a
    # local removal changed no fact anybody else could see, and the next discovery
    # pass adopted the document again -- correctly, because it was still shared.
    # The panel now says the thing it can actually do: turn the watch **off**.
    # The document stays adopted and stays polled; what stops is the standing
    # delegation, and the row leaves the default view. Removing the
    # *connection* is still real, because credentials are this deployment's own.

    async def update_doc(self, doc_id: str) -> dict[str, Any]:
        """Refresh is repair: reclassify against current facts, thaw what now works,
        and leave what does not with guidance."""
        conn = self._reg.find_doc(doc_id)
        if conn is None:
            return {"result": "not_watched"}
        probe = await self._probe(conn, doc_id)
        if probe["result"] == "ok":
            # The facts say healthy: clear the verdict bit and the watcher re-admits it
            # on the next tick.
            await self._reg.store.clear_failure(doc_id)
            await self._reg.store.set_panel_meta(
                doc_id, title=probe.get("title") or "",
                kind=probe.get("kind") or "", checked_at=time.time(),
            )
            return {"result": "ok", "title": probe.get("title")}
        if probe["result"] == "comment_only":
            # Same verdict as admission: record it, and the UI keeps its amber light.
            await self._reg.store.note_permanent_failure(doc_id, "comment_only_access")
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
                    "detail": "not a Google service-account key (client_email) "
                              "nor a Feishu app (app_id + app_secret)",
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
            "connection": {
                "id": conn.id,
                "provider": conn.kind,
                "provider_name": _PROVIDER_NAMES.get(conn.kind, conn.kind),
                "agent_address": conn.address,
                "agent_display": conn.display_name,
                "docs_count": 0,
                "health": "idle",
            },
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
        await self._reg.store.gc(self._reg.all_docs())
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
        """Every standing mandate: level, issuance mode, term -- the
        panel-always-visible guarantee (D3).

        Two values, off and on, plus the one state the system reaches by itself,
        expired. ``suspended`` and ``global_suspended`` are gone from the payload
        with the state they described; a ledger that still carries the flag has
        been tombstoned by the registry before this reads it, so those rows
        arrive as ``revoked`` -- off, with a reason.
        """
        snap = self._registry().snapshot()
        return {
            "watches": [
                {"doc_id": d, **{k: e.get(k) for k in
                                 ("mode", "issued_at", "issued_by",
                                  "expires_at", "expired", "budget",
                                  "revoked", "revoked_at", "revoked_reason")}}
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
        exists precisely to keep "said nothing" and "said forever" apart."""
        from jiuwenswarm.extensions.co_scribe.backend.host.authority.watch_registry import MODES, RETIRED_MODES

        if mode not in MODES:
            # A stale client (or a stale bookmark) can still name the retired
            # ``reply_only``. Answer it as a refusal rather than letting ``issue``
            # raise into an INTERNAL_ERROR -- and never by rounding it to the one
            # surviving, wider level.
            if mode in RETIRED_MODES:
                return {"ok": False,
                        "detail": f"档位 {mode!r} 已退役，值守只有「关 / 开（操作权）」两档。"}
            return {"ok": False, "detail": f"未知档位：{mode!r}（可选 {'/'.join(MODES)}）。"}
        if self._reg.find_doc(doc_id) is None:
            # A mandate names a document this deployment manages. Issuing one for
            # an id nobody adopted left an entry that no watcher would ever read
            # and that the panel could not show.
            return {"ok": False, "detail": "文档未纳管，不能签发档位。"}
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
        suggestions only -- an idle grant reads as "consider turning it off", a
        grant with repeated denials as "consider renewing" -- and the decision
        stays with the owner (recertification at renewal time).

        ``lineage`` is this document's own slice of the audit journal, newest
        first. It ships with the usage numbers rather than behind a second RPC
        because they answer one question between them: the counts say how much of
        the grant was spent, the lineage says who granted it, who changed it, and
        why it is in the state it is in -- and the panel opens both at once.
        """
        from jiuwenswarm.extensions.co_scribe.backend.toolkit.receipts import ReceiptStore

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

        lineage = reg.audit_for(doc_id, limit=50)

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
            "lineage": lineage,
            "hints": hints,
        }

    async def watch_revoke(self, doc_id: str) -> dict[str, Any]:
        return {"ok": self._registry().revoke(doc_id)}

    async def watch_revoke_all(self) -> dict[str, Any]:
        """The kill switch (D8).

        No button points here any more -- the panel turns off a **selection**, so
        that what is being revoked is on screen while it is decided. The op stays
        because the deployment-wide "everything, now" is a real operational need
        that a selection cannot express when the panel is what is broken.
        """
        return {"ok": True, "revoked": self._registry().revoke_all()}

    async def watch_set_many(self, doc_ids: list[str], mode: str) -> dict[str, Any]:
        """Turn the watch on for a selection, **skipping the ones already on**.

        Re-issuing over a live grant is not a no-op: issuance sets a fresh term,
        so "turn on the 40 I selected" would quietly extend the thirty days on
        every watch already running -- the owner would be renewing grants they
        had only meant to leave alone, without a word on screen saying so.
        Renewal stays where it can be seen, one document at a time, in the usage
        audit. Skipped ids come back so the panel can say how many were already
        on rather than reporting a number that changed nothing.
        """
        reg = self._registry()
        issued: list[str] = []
        skipped: list[dict[str, str]] = []
        for doc_id in list(doc_ids or []):
            doc_id = str(doc_id or "")
            if not doc_id:
                continue
            if reg.is_on(doc_id):
                skipped.append({"doc_id": doc_id, "reason": "already_on"})
                continue
            out = await self.watch_set(doc_id, mode)
            if out.get("ok"):
                issued.append(doc_id)
            else:
                skipped.append({"doc_id": doc_id, "reason": "refused",
                                "detail": str(out.get("detail") or "")})
        return {"ok": True, "issued": issued, "skipped": skipped}

    async def watch_revoke_many(self, doc_ids: list[str]) -> dict[str, Any]:
        """Turn the watch off for a selection.

        One ``revoke`` per document rather than ``revoke_all`` over a filtered
        set: each document is a separate delegation and each termination is a
        separate fact, so each lands its own audit line and its own tombstone.
        A batch that wrote one line would leave the other documents' histories
        with a silent gap exactly where the answer to "who turned this off"
        should be.
        """
        reg = self._registry()
        revoked: list[str] = []
        skipped: list[dict[str, str]] = []
        for doc_id in list(doc_ids or []):
            doc_id = str(doc_id or "")
            if not doc_id:
                continue
            if reg.revoke(doc_id):
                revoked.append(doc_id)
            else:
                skipped.append({"doc_id": doc_id, "reason": "already_off"})
        return {"ok": True, "revoked": revoked, "skipped": skipped}

    async def watch_audit(self, limit: int = 100) -> dict[str, Any]:
        """The history view's data feed: one line per lifecycle event."""
        return {"events": self._registry().audit_tail(limit)}

    # -------------------------------------------------------- un-highlight (D14)

    async def unhighlight(self, receipt_id: str) -> dict[str, Any]:
        """D8.3's manual half: remove one applied batch's highlights by receipt.
        Shielded for the same reason as ``revert``: a document write in flight."""
        return await asyncio.shield(self._unhighlight_unshielded(receipt_id))

    async def _unhighlight_unshielded(self, receipt_id: str) -> dict[str, Any]:
        from jiuwenswarm.extensions.co_scribe.backend.toolkit.receipts import ReceiptStore

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
                try:
                    data = json.loads(f.read_text())
                    email = str(data.get("client_email") or "")
                    address = email or str(data.get("app_id") or "")
                except Exception:  # noqa: BLE001 - an unreadable key still gets listed
                    email = address = ""
                rows.append({
                    "filename": f.name,
                    "path": str(f),
                    "client_email": email,
                    # What the key names, whichever vendor: the SA email or the app id.
                    "address": address,
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
        if not caps.can_edit:
            return {"result": "comment_only"}
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
            {"credentials_file": c.credentials_file, "documents": list(c.watcher._docs)}
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
            from jiuwenswarm.extensions.co_scribe.backend.toolkit.clouddoc_tools import (
                _ask_channel_available,
            )

            return bool(_ask_channel_available())
        except Exception:  # noqa: BLE001 - an unreadable config reads as no channel
            return False

    def _current_model_name(self) -> str:
        """The model unattended turns run on, read from the config file each call.
        Empty means the deployment default.

        Expanded before it is handed out: what is stored can be a template the
        config never resolved (``${MODEL_NAME}``), and the panel's job is to show
        which model actually runs, not which string happens to be on disk. The
        dispatcher expands the same way, so the two agree.
        """
        try:
            data = load_yaml_round_trip(self._config_path)
            raw = str(((data or {}).get("clouddoc") or {}).get("model_name") or "").strip()
        except Exception:  # noqa: BLE001 - an unreadable config reads as the default
            return ""
        return self._expanded(raw)

    @staticmethod
    def _expanded(name: str) -> str:
        """A stored model name with any ``${VAR}`` resolved; unchanged if it has none."""
        if not name:
            return ""
        try:
            from jiuwenswarm.common.config import resolve_env_vars

            return str(resolve_env_vars(name) or "").strip()
        except Exception:  # noqa: BLE001 - expansion is a convenience, not a gate
            return name

    def _currently_enabled(self) -> bool:
        try:
            data = load_yaml_round_trip(self._config_path)
            return bool(((data or {}).get("clouddoc") or {}).get("enabled", True))
        except Exception:  # noqa: BLE001
            return True

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
        """Pin the model unattended turns run on, deployment-wide -- the default every
        document without a pin of its own falls back to (see ``set_doc_model``). Empty
        restores the agentserver's own default. The name is validated the way cron
        validates its jobs' models, so what lands in the config is a key the
        agentserver can resolve."""
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

    async def set_doc_model(self, doc_id: str, model_name: str) -> dict[str, Any]:
        """Pin the model **this document's** unattended turns run on. Empty clears the
        pin and the document follows the deployment default.

        Same shape as ``set_model``: validate first, persist second, so only a key the
        agentserver can resolve is ever stored. It lands in ``panel_meta`` -- where the
        panel already keeps title, kind, url and checked_at -- and not in the watch
        registry: the registry records authority, and which model runs the turn is an
        operational setting, not part of what was delegated.
        """
        from jiuwenswarm.gateway.cron.models import validate_cron_model

        doc_id = str(doc_id or "").strip()
        if not doc_id:
            return {"ok": False, "detail": "缺少 doc_id。"}
        try:
            canonical = validate_cron_model(model_name) or ""
        except ValueError as exc:
            return {"ok": False, "detail": str(exc)}

        await self._reg.store.set_panel_meta(doc_id, model_name=canonical)
        return {"ok": True, "doc_id": doc_id, "model_name": canonical}

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
