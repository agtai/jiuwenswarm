"""Connection registry: a connection is a provider and an account, one watcher each.

Design constraints:

* **One state file and one dispatcher, shared.** Sessions and state are keyed by
  doc_id, so ``add`` below enforces that **a document belongs to exactly one
  connection**. That constraint replaced a state-key migration
  (``doc_id`` → ``(connection, doc_id)``) and was the cheapest trade in the whole
  multi-connection change.
* **Connections are immutable**: the credentials decide the address, and the
  address is the connection's identity. There is no editing, only add and
  remove -- changing the identity means deleting and re-adding.
* Connection id is ``{kind}:{address}``. An address is naturally unique and
  stable, so the id does not shift when the list is reordered.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, replace
from typing import Any, Callable

from jiuwenswarm.agents.harness.common.tools.clouddoc.provider import (
    read_connection_specs,  # noqa: F401 - re-export: the reader lives in the cross-process contract module
)
from jiuwenswarm.gateway.clouddoc.comment_watcher import CloudDocCommentWatcher

logger = logging.getLogger(__name__)


@dataclass
class CloudDocConnection:
    id: str
    kind: str
    address: str
    # What a person recognises the account by. The address is the identity the
    # trigger config anchors on -- on Feishu an opaque ou_ open_id -- and showing
    # that in a connection column reads as a defect, not a name.
    display_name: str
    credentials_file: str
    provider: Any
    watcher: CloudDocCommentWatcher


class CloudDocConnections:
    """Holds every connection. Shared parts and the provider factory are injected at
    construction, which is how tests substitute a fake provider."""

    def __init__(
        self,
        *,
        store,
        dispatcher,
        watcher_cfg,
        base_trigger_cfg,
        provider_factory: Callable[[str], Any],
        now_fn: Callable[[], float],
        enabled: bool = True,
        watch_registry: "object | None" = None,
    ) -> None:
        self._store = store
        self._dispatcher = dispatcher
        self.watcher_cfg = watcher_cfg
        self._base_trigger = base_trigger_cfg
        self._provider_factory = provider_factory
        self._now_fn = now_fn
        self._watch_registry = watch_registry
        # D2's adoption policy: "" / "off" issues nothing (default: adoption ≠
        # delegation); "reply_only" / "apply_scoped" auto-issues that level per newly
        # adopted document. The policy line in the config **is** the owner's explicit
        # batch signature -- issued watches are ordinary watches (equal rights, equal
        # visibility, equal audit; the audit line says so).
        self.auto_watch_policy = ""
        self._conns: dict[str, CloudDocConnection] = {}
        self._started = False
        # The registry exists even when the feature is off, because the panel is how a
        # user turns it on -- see ``start_all``. Off means "do not poll", not "do not
        # answer the panel".
        self.enabled = enabled

    # ------------------------------------------------------------ reads

    def list(self) -> list[CloudDocConnection]:
        return list(self._conns.values())

    def get(self, conn_id: str | None) -> CloudDocConnection | None:
        if conn_id:
            return self._conns.get(conn_id)
        # Unspecified means the first one -- every call in a single-connection
        # deployment arrives this way
        return next(iter(self._conns.values()), None)

    def find_doc(self, doc_id: str) -> CloudDocConnection | None:
        """Which connection owns a document. ``add`` keeps documents unique across
        connections, so there is never more than one answer."""
        for c in self._conns.values():
            if doc_id in c.watcher._docs:
                return c
        return None

    def all_docs(self) -> list[str]:
        out: list[str] = []
        for c in self._conns.values():
            out += c.watcher._docs
        return out

    @property
    def store(self):
        return self._store

    # ------------------------------------------------------------ writes

    async def add(
        self, credentials_file: str, documents: list[str] | None = None, *, start: bool = False
    ) -> CloudDocConnection:
        """Create a connection. ``start=True`` brings the watcher up immediately, which
        is what a run-time addition needs; on the startup path ``start_all`` does it.

        A duplicate address is refused outright. The same account twice means two
        watchers polling under one identity, and every mention answered twice --
        the hazard the single-instance assumption exists to prevent, reappearing at
        the connection level.
        """
        provider = self._provider_factory(credentials_file)
        ident = await provider.self_identity()
        address = ident.address or ident.display_name
        conn_id = f"{provider.kind}:{address}"
        if conn_id in self._conns:
            raise ValueError(f"duplicate connection: {address}")

        try:
            from jiuwenswarm.agents.harness.common.tools.clouddoc.receipts import ReceiptStore

            provider.receipt_sink = ReceiptStore()
        except Exception:  # noqa: BLE001 - a member must still be built without it
            # The fallback used to be "the watcher path has its own WAL
            # (begin_applying)". It does not any more: deleting the retired apply
            # machinery took the only caller of begin_applying with it, so this sink is
            # the whole of the recording. Every write path that matters now refuses
            # rather than proceeding without one, which is why failing here is survivable
            # -- the writes stop, they do not go unrecorded.
            logger.exception("[clouddoc] receipt sink unavailable on the watcher path")
        watcher = CloudDocCommentWatcher(
            provider,
            self._store,
            replace(
                self._base_trigger,
                sa_address=address,
                # The mention is the summons on every platform (§16.14: a mention is a
                # pointer edge and carries no authority, so the assignment field adds
                # no safety -- confinement and the watch grant do that). Google kept
                # the assignment gate for one campaign after Feishu switched, and the
                # measured cost was a person @-ing twice and hearing "assign it to me"
                # then silence. Assignment still counts where a platform has it.
                mention_triggers=True,
            ),
            self.watcher_cfg,
            dispatch=self._dispatcher,
            now_fn=self._now_fn,
            registry=self._watch_registry,
        )
        # **Uniqueness across connections is enforced here**, not in the panel.
        # panel.add_doc is one of two entrances; the other is reading config at
        # startup. A hand-edited (or copied) config that puts one document under two
        # connections gets two watchers on it: every mention answered twice, and
        # since state is keyed by doc_id, the two overwrite each other. Leaving the
        # check on the UI path would lock one door of two.
        taken = {d for c in self._conns.values() for d in c.watcher._docs}
        docs, dropped = [], []
        for d in documents or []:
            (dropped if d in taken else docs).append(d)
            taken.add(d)
        if dropped:
            logger.warning(
                "[clouddoc] %s 跳过 %d 篇已属于其他连接的文档：%s——"
                "一篇文档只能由一个身份纳管，否则每条 @ 会收到两份回应",
                address, len(dropped), ", ".join(x[:12] + "…" for x in dropped),
            )

        for d in docs:
            watcher.watch(d)
        conn = CloudDocConnection(
            id=conn_id, kind=provider.kind, address=address,
            display_name=ident.display_name or address,
            credentials_file=credentials_file, provider=provider, watcher=watcher,
        )
        self._conns[conn_id] = conn
        if start or self._started:
            watcher.start()
        self.policy_issue(documents or [])
        return conn

    def policy_issue(self, doc_ids: list[str]) -> None:
        """Auto-issue per the adoption policy (D2). Never overwrites an existing entry:
        a manual grant outranks the policy, re-adoption must not reset terms, and a
        revoked or expired entry is the owner's tombstone -- policy does not dig it
        up. Every adoption path calls this: a connection being built, a link pasted
        into the panel, and a shared document discovered at run time."""
        policy = (self.auto_watch_policy or "").strip()
        if policy in ("", "off") or self._watch_registry is None:
            return
        from jiuwenswarm.gateway.clouddoc.watch_registry import MODES

        if policy not in MODES:
            logger.warning("[clouddoc] auto_watch_on_adopt 值非法，忽略：%r", policy)
            return
        for doc_id in doc_ids:
            if self._watch_registry.get(doc_id) is not None:
                # Live, expired or revoked alike: an entry of any state is the
                # owner's word on this document, and the journal below is only the
                # backstop for an entry that was lost.
                continue
            if self._watch_registry.terminated_by_owner(doc_id):
                # The owner revoked this delegation; adoption alone must not
                # bring it back. Only a manual grant outranks a revocation.
                continue
            self._watch_registry.issue(doc_id, policy, issued_by="policy")

    async def remove(self, conn_id: str) -> CloudDocConnection | None:
        """Drop a connection and, with it, every mandate signed under it.

        Removing the connection is the end of the mandator's authority for that
        account (D3): the account can no longer act, so a standing mandate for its
        documents must not outlive it in the registry, where a later re-adoption
        would find it still live and resume unattended dispatch. Each revocation is
        journaled with its reason, and the tombstone keeps policy from re-issuing.
        """
        conn = self._conns.pop(conn_id, None)
        if conn is None:
            return None
        await conn.watcher.stop()
        if self._watch_registry is not None:
            for doc_id in list(getattr(conn.watcher, "_docs", []) or []):
                try:
                    self._watch_registry.revoke(doc_id, reason="connection_removed")
                except Exception:  # noqa: BLE001 - the connection is gone either way; say so
                    logger.exception("[clouddoc] 撤销 %s 的值守失败（连接已移除）", doc_id)
        return conn

    async def start_all(self) -> None:
        """Start every watcher, after collecting state for documents nobody watches.

        The collection lives here rather than in a watcher because ``gc`` is absolute --
        it keeps exactly the documents it is handed and deletes the rest -- and a watcher
        knows only its own. Called from one, every other connection's state was deleted
        on every start: dedup keys, pending proposals, sessions and the seeded flag. The
        documents then re-seeded, which marks everything currently outstanding as
        handled, so a comment written between the last poll and a restart was silently
        swallowed.

        Without any collection at all, a document dropped from the config would leave its
        whole state on disk, and empty thread entries from retired proposals would only
        accumulate -- ``triggered_ids`` is bounded at 500 entries over 30 days,
        ``threads`` is not.
        """
        if not self.enabled:
            # Configured off by hand. Adding a connection through the panel turns it on,
            # so reaching here with connections means somebody wrote enabled: false on
            # purpose -- and it must be loud, or the documents sit in the panel looking
            # managed while nothing polls them.
            if self._conns:
                logger.warning(
                    "[clouddoc] clouddoc.enabled=false，%d 个连接下的文档不会被轮询",
                    len(self._conns),
                )
            self._started = True
            return
        removed = await self._store.gc(self.all_docs())
        if removed:
            logger.info("[clouddoc] GC 清除了 %d 篇不再纳管的文档状态", len(removed))
        for c in self._conns.values():
            c.watcher.start()
        self._started = True

    async def stop_all(self) -> None:
        await asyncio.gather(*(c.watcher.stop() for c in self._conns.values()))
        self._started = False
