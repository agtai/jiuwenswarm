"""The Feishu/Lark provider, driven through the official CLI.

Read the seam first: ``lark_cli.LarkCli`` builds, runs and classifies every command,
and this file is what interprets the results as documents, comments and edits.

**Commands and response shapes come from the CLI itself.** Every command name and flag
was read from ``lark-cli 1.0.89``'s help, every field name from its ``schema``
outputSchema, and the whole set is checked against the installed binary in the tests.

What no local source can answer is what a *tenant* permits -- whether an app may
enumerate what was shared with it, own a document, or read a collaborator list. None
of those is left as an assumption to be checked later. Each is **asked at runtime and
remembered**, and a refusal degrades rather than fails:

* Enumeration refused → discovery returns nothing and adoption happens the way it
  already works, from a link pasted into the panel. Raising would take the panel down
  over a feature it does not need.
* Permission query refused → capabilities are settled by attempting the read the
  feature actually depends on, rather than reporting no access, which would put a
  workable document into the comment-only bucket and have admission refuse it.
* Ownership refused → the failure is translated into the sentence that helps ("share
  a document with this app instead") rather than relayed, the way Google's "storage
  quota exceeded" sends people to empty a trash folder that was never full.

The provider is therefore correct whichever way a tenant answers, rather than correct
only if a guess was right. What is still marked ``ASSUMPTION`` is narrow: field
spellings the schema did not cover, and limits such as where quoted text truncates --
each noted with the spike (§17.2) that measures it.

Reading the CLI corrected four guesses that would each have failed at runtime:
``--scope`` takes ``full`` and not ``all``; resolved comments are selected by
``--solved-status`` rather than an ``--include-resolved`` switch, and its default is
``false``, so the unresolved ones are what a caller gets unless it says otherwise;
collaborators are managed by ``+member-add`` / ``+member-list``, not
``+add-permission``; and identity comes from a top-level ``whoami``.

The largest correction is a capability. ``docs +update`` takes ``--revision-id`` as a
base revision, which is Feishu's answer to Google's WriteControl, so this provider
does have optimistic locking and says so. It also accepts comma-separated block ids
for a single ``block_replace``, which is worth knowing but does not change the atomic
batch answer: one command is one write, and several edits still mean several commands.

Two findings from the CLI change what was expected of this platform:

* **Document comments have no event.** ``event list`` offers eight domains --
  application, approval, board, card, im, minutes, task, vc -- and none carries a
  drive or comment event. The capability survey expected a push channel to replace
  polling here; there is none, so the watcher polls on Feishu exactly as it does on
  Google, and the "idle polling quota disappears structurally" note in §17.1 does not
  hold. What does hold is that event payloads carry ``sender_id`` as an ``ou_``-
  prefixed open_id, so were an event to exist, recognising the agent's own would be a
  platform fact rather than a guess.
* **The write channel has no highlight.** ``docs +update`` exposes no background
  colour, so the visible half of acceptance is unavailable and a caller asking for it
  is refused rather than quietly served a plain edit.

Three things are decided rather than observed:

* **``--as bot``.** Enforced in the CLI wrapper. Acting as a user misattributes the
  write and, worse, breaks the loop prohibition: the agent recognises its own events
  by author, and an event it produced under a person's identity is indistinguishable
  from one that person produced.
* **No atomic multi-edit writes.** The CLI applies edits one at a time and promises
  nothing about the batch, so ``capabilities`` reports ``atomic_batch=False`` and a
  multi-edit batch is refused upstream (C9). It is not simulated by editing and
  undoing: the document is shared, a half-written state is what readers see, and the
  undo would race whoever else is typing.
* **``+history-revert`` is not part of the edit path.** It restores a whole document
  to a point in time, taking other people's concurrent edits with it, which is the
  path D8-5 rejected. It stays available only as manual disaster recovery.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from jiuwenswarm.agents.harness.common.tools.clouddoc.lark_cli import LarkCli, _classify
from jiuwenswarm.agents.harness.common.tools.clouddoc import feishu_formats
from jiuwenswarm.agents.harness.common.tools.clouddoc.provider import (
    AgentIdentity,
    DocCapabilities,
    DocComment,
    DocProvider,
    DocRef,
    DocReply,
    DocSnapshot,
    DocSummary,
    EditResult,
    ProviderError,
    Segment,
    TextDomain,
)

logger = logging.getLogger(__name__)


def _first(d: Any, *names: str, default: Any = None) -> Any:
    """Read the first key that is present.

    The CLI's field names are among the things no spike has confirmed, so each reader
    lists the plausible spellings rather than betting on one. This is scaffolding for
    an unverified integration, not a pattern to carry into settled code.
    """
    if not isinstance(d, dict):
        return default
    for n in names:
        if n in d and d[n] is not None:
            return d[n]
    return default


def _reply_text(content: Any) -> str:
    """Flatten a reply's rich content into text.

    A reply is not a string: the contract gives ``content.elements``, a list of typed
    runs. Reading it as a string yields nothing, which would make every reply look
    empty -- including the agent's own, which is how a verdict is recognised.
    """
    if isinstance(content, str):
        return content
    if not isinstance(content, dict):
        return ""
    parts: list[str] = []
    for el in content.get("elements") or []:
        if isinstance(el, str):
            parts.append(el)
            continue
        if not isinstance(el, dict):
            continue
        # TENANT-VERIFY (2026-09-02): each element is {"type": <t>, <t>: {...}}
        # with every other type key present as null. Walking the values
        # indiscriminately appended the type tag itself, so a live comment read
        # back as "person 修改题目text_run".
        etype = el.get("type")
        payload = el.get(etype) if isinstance(etype, str) else None
        if etype == "text_run":
            t = (payload or {}).get("text")
            if isinstance(t, str):
                parts.append(t)
        elif etype == "person":
            uid = str((payload or {}).get("user_id") or "")
            parts.append(f"@{uid}" if uid else "@")
        elif etype == "docs_link":
            u = (payload or {}).get("url")
            if isinstance(u, str):
                parts.append(u)
        elif isinstance(payload, dict):
            t = payload.get("content") or payload.get("text")
            if isinstance(t, str):
                parts.append(t)
    return "".join(parts)


def _mentioned_ids(content: Any) -> list[str]:
    """Every person element's user_id in one rich-content payload.

    The mention-hint path compares these against the bot's own id: a person typing @
    in the editor produces a ``person`` element, which is the only mention signal
    this platform's comment payload carries.
    """
    if not isinstance(content, dict):
        return []
    ids: list[str] = []
    for el in content.get("elements") or []:
        if not isinstance(el, dict):
            continue
        etype = el.get("type")
        payload = el.get(etype) if isinstance(etype, str) else None
        if etype == "person":
            uid = str((payload or {}).get("user_id") or "").strip()
            if uid:
                ids.append(uid)
    return ids


def _comment_text(comment: Any) -> str:
    """A comment's own text, which the contract carries in its first reply.

    Feishu models a comment as a thread whose opening message is reply one, so there
    is no separate body field. Taking the first reply is what the platform means by
    "the comment", and an empty thread reads as empty rather than raising.
    """
    if not isinstance(comment, dict):
        return ""
    replies = (comment.get("reply_list") or {}).get("replies") or []
    if not replies:
        return ""
    return _reply_text((replies[0] or {}).get("content"))


class FeishuDocsProvider(DocProvider):
    def __init__(
        self,
        *,
        profile: str = "",
        binary: str = "lark-cli",
        self_open_id: str = "",
        agent_roster: tuple[str, ...] = (),
    ) -> None:
        # The app's secret is registered with the CLI once (``config init``) and lives
        # in its store; a connection names a profile, never a secret.
        self._cli = LarkCli(binary=binary, profile=profile)
        # The bot's own open_id, which is how its own comments are recognised. Left
        # empty it is fetched once on first use; see self_identity.
        self._self_open_id = self_open_id
        # Open_ids the deployer declares to be other agents. This platform's comment
        # payload carries a bare user_id with no identity type, so a bot cannot be told
        # from a person by inspection (see _is_other_agent); the roster supplies the
        # fact the payload withholds, which is what lets the loop-prohibition rail work
        # on Feishu once mentions -- rather than assignments -- trigger.
        self._roster: set[str] = {str(a).strip() for a in agent_roster if str(a).strip()}
        self._identity: AgentIdentity | None = None
        # Capabilities the tenant decides rather than the code. None means "not asked
        # yet"; the answer is remembered so a degraded deployment is told once instead
        # of on every poll.
        self._discovery_available: bool | None = None
        self._can_own_documents: bool | None = None

    # The receipt plumbing is set on the instance by the connection registry, exactly
    # as it is for Google. Declared here as class defaults so the write primitive can
    # read them whatever path built the provider -- a test constructing one directly
    # must not have to know about them.
        # A connection reaches docx, markdown files and spreadsheets alike, so the
        # format belongs to the document. Cached because a document does not change
        # type and this sits on the read path.
        self._kind_cache: dict[str, str] = {}
        # Tokens that came from /wiki/ links, or answered "not exist" as docx
        # and resolved as wiki. Drive verbs need --type wiki for these; docs
        # +fetch unwraps on its own, which is exactly how the gap hid: reading
        # worked while every comment and member verb reported "not exist"
        # (TENANT-VERIFY 2026-09-02, live).
        self._wiki_tokens: set[str] = set()
        # Shared files this provider cannot work on, learned during discovery and
        # reported to the person rather than dropped.
        self._unsupported: dict[str, tuple[str, str]] = {}
        # Links as the platform reported them. A Feishu URL carries the tenant's own
        # domain, which nothing here can know, so a URL is remembered when one is seen
        # and never constructed.
        self._url_cache: dict[str, str] = {}

    receipt_sink = None
    receipt_meta = None

    @property
    def kind(self) -> str:
        return "feishu"

    @property
    def text_domain(self) -> TextDomain:
        # Not an assumption: this provider reads and writes with --doc-format markdown,
        # so markers in the body are content the platform round-trips rather than
        # literal characters that would land in someone's document. The rail may
        # therefore allow them, which is the correct behaviour for this transport.
        return "markdown"

    # ---------------------------------------------------------------- basics

    def parse_doc_ref(self, url_or_id: str) -> DocRef:
        """Accept a docx link, a wiki link, or a bare token.

        Wiki links address a node rather than the document, and the CLI resolves one
        to the other. That resolution needs a call, which a parser cannot make, so a
        wiki token is returned as-is and resolved at first use.
        """
        s = (url_or_id or "").strip()
        if not s:
            raise ProviderError("invalid", "空的文档引用。")
        for marker in ("/docx/", "/docs/", "/wiki/", "/sheets/", "/slides/", "/file/"):
            if marker in s:
                tail = s.split(marker, 1)[1]
                token = tail.split("?", 1)[0].split("#", 1)[0].split("/", 1)[0]
                if token:
                    if marker == "/wiki/":
                        self._wiki_tokens.add(token)
                    if marker == "/sheets/":
                        # A pasted link is the only place a spreadsheet's format is
                        # ever visible up front: there is no listing to teach it, and
                        # without this the token would read as a docx and fail on the
                        # fetch with the platform's message instead of being served.
                        self._kind_cache[token] = "spreadsheet"
                    if marker == "/slides/":
                        self._kind_cache[token] = "presentation"
                    if marker == "/file/":
                        # ASSUMPTION: of Drive's plain files co-scribe serves only
                        # markdown, so a pasted file link is read as one; a PDF pasted
                        # here fails honestly on the markdown fetch with the platform's
                        # message rather than being half-served.
                        self._kind_cache[token] = "markdown"
                    if s.startswith("http"):
                        # The pasted link is the only place the tenant's own
                        # domain ever appears; without keeping it, the panel
                        # could only ever show the bare token back.
                        self._url_cache[token] = s.split("?", 1)[0].split("#", 1)[0]
                    return token
                break
        if "/" in s or " " in s:
            raise ProviderError("invalid", f"无法从 {url_or_id!r} 解析出文档 token。")
        return s

    async def self_identity(self) -> AgentIdentity:
        if self._identity is not None:
            return self._identity
        # `whoami` is a top-level command and reports the effective identity, which
        # under --as bot is the app. ASSUMPTION (spike 9): the open_id it returns is
        # the one that appears as the author of the bot's own comments. Falsified if
        # the two differ -- self-comment filtering would then have no basis and the
        # loop prohibition would need the content marker of §16.8 instead.
        data = await self._cli.json(["whoami"])
        open_id = str(_first(data, "open_id", "openId", "bot_open_id", default="") or "")
        name = str(_first(data, "name", "app_name", "display_name", default="") or "")
        self._self_open_id = self._self_open_id or open_id
        # The preset id wins: on this tenant whoami answers without an open_id, and
        # the credentials file's bot_open_id is then the only identity the trigger
        # config can anchor on. Ignoring it here made sa_address degrade to the
        # display name, which no mention ever matches.
        self._identity = AgentIdentity(
            display_name=name or "bot", address=self._self_open_id or None
        )
        return self._identity

    async def _title_from_meta(self, doc_ref: DocRef) -> str:
        """Title from drive metadata, for the formats ``docs +fetch`` cannot serve.

        TENANT-VERIFY (2026-09-02): a spreadsheet has no fetch of its own, and the
        metas query answers any type. It also carries the canonical URL, learned here
        so a token adopted bare still links to the real document.
        """
        async def ask(doc_type: str) -> dict:
            data = await self._cli.json([
                "drive", "metas", "batch_query", "--data",
                json.dumps({"request_docs": [{"doc_token": str(doc_ref),
                                              "doc_type": doc_type}],
                            "with_url": True}, ensure_ascii=False),
            ])
            metas = _first(data or {}, "metas", default=[]) or []
            return metas[0] if isinstance(metas, list) and metas else {}

        meta = await ask(self._drive_type(doc_ref))
        if not meta and str(doc_ref) not in self._wiki_tokens:
            # The wiki flavor is process memory too: a wiki-hosted token after a
            # restart reads as a docx here, and the platform answers the mismatch
            # with a failed_list rather than an error. Same posture as _drive_json:
            # retried once as wiki, and success teaches the flavor.
            meta = await ask("wiki")
            if meta:
                self._wiki_tokens.add(str(doc_ref))
        url = str(_first(meta, "url", default="") or "")
        if url.startswith("http"):
            self._url_cache.setdefault(str(doc_ref), url)
        return str(_first(meta, "title", default="") or "")

    async def canonical_url(self, doc_ref: DocRef) -> str:
        """The tenant-domain URL for a token nobody ever pasted.

        A bot-created document has no pasted link to remember, and the bare token
        renders as dead text in the panel. The metas query is the platform's own
        answer, cached the same way a paste would have been.
        """
        cached = self._url_cache.get(str(doc_ref))
        if cached:
            return cached
        await self._title_from_meta(doc_ref)
        return self._url_cache.get(str(doc_ref)) or str(doc_ref)

    async def title(self, doc_ref: DocRef) -> str:
        kind = await self.doc_kind(doc_ref)
        if kind != "document" and str(doc_ref) not in self._wiki_tokens:
            return await self._title_from_meta(doc_ref)
        # TENANT-VERIFY (2026-09-02, cli 1.0.89): --detail meta does not exist
        # (allowed: simple/with-ids/full); simple carries the title as a tag in
        # the rendered content.
        data = await self._cli.json(["docs", "+fetch", "--doc", doc_ref, "--detail", "simple"])
        doc = _first(data, "document", default=data) or {}
        direct = str(_first(doc, "title", "name", default="") or "")
        if direct:
            return direct
        content = str(_first(doc, "content", default="") or "")
        m = re.search(r"<title>(.*?)</title>", content, re.S)
        return m.group(1).strip() if m else ""

    async def capabilities(self, doc_ref: DocRef) -> DocCapabilities:
        """What the platform lets the bot do with one document.

        ``atomic_batch`` is False and stays False: it is a property of the CLI's edit
        path, not of one document, and no spike can turn it on.
        """
        # Reading the collaborator list may itself be a user-only operation on some
        # tenants. When it is, the honest answer is not "no access" -- that would put
        # a perfectly workable document into the comment-only bucket and admission
        # would refuse it. The document is read instead, which is the access the
        # feature actually needs, and the flags follow from whether that worked.
        try:
            data = await self._drive_json(doc_ref, lambda ftype: [
                "drive", "+member-list", "--token", doc_ref, "--type", ftype,
            ])
        except ProviderError as exc:
            if exc.kind == "not_found":
                return DocCapabilities(
                    can_read=False, can_edit=False, can_comment=False, can_resolve=False,
                    has_revision_control=False, max_quote_chars=None, atomic_batch=False,
                )
            if exc.kind in ("forbidden", "unsupported", "invalid"):
                return await self._capabilities_by_probe(doc_ref)
            raise
        # member-list answers with an ``items`` array, one row per collaborator;
        # the app's own permission is the row whose member is this app id. Reading
        # ``perm`` off the top level (as this once did) always found nothing, so
        # every document -- including ones the bot fully owns -- read as
        # non-editable and fell to comment-only or backoff. (TENANT-VERIFY
        # 2026-09-02, live: the bot's own P1 doc showed full_access in the row.)
        members = _first(data, "items", "members", default=[]) or []
        app_id = str(_first(data, "app_id", default="") or "") or self._app_id_hint()
        perm = ""
        for m in members:
            mid = str(_first(m, "member_id", "open_id", "id", default="") or "")
            mtype = str(_first(m, "member_type", "type", default="") or "").lower()
            if mtype in ("appid", "app") or mid.startswith("cli_"):
                perm = str(_first(m, "perm", "permission", "role", default="") or "").lower()
                if not app_id or mid == app_id:
                    break
        if not perm and members:
            # A single-member list is the bot's own view of its own access.
            perm = str(_first(members[0], "perm", "permission", "role", default="") or "").lower()
        can_edit = perm in ("edit", "full_access", "manage_collaborator", "owner")
        return DocCapabilities(
            can_read=bool(perm) or True,
            can_edit=can_edit,
            can_comment=can_edit or perm in ("comment", "view_and_comment"),
            can_resolve=can_edit,
            # **False, and the earlier True was the more dangerous error.** The
            # reading that `--revision-id` is Feishu's WriteControl does not survive
            # the sibling command's own help text: pinning an older revision "rebuilds
            # the page from that snapshot and discards newer edits to it". A flag that
            # destroys a concurrent edit is not a lock, and declaring one here would
            # let admission rely on protection that does not exist.
            #
            # Declared absent rather than simulated (C9). See the write path for the
            # tenant check that would settle it.
            has_revision_control=False,
            # Spike 7 closed (TENANT-VERIFY 2026-09-02): quotes truncate at exactly
            # 128 code points, hard, with no mark -- measured identically for an API
            # block anchor and for a live user selection (a 538-char paragraph came
            # back as precisely 128). Declared unmarked so the rail routes a
            # limit-length quote to QUOTE_TRUNCATED instead of anchoring the fragment.
            max_quote_chars=128,
            quote_truncates_unmarked=True,
            atomic_batch=False,
        )

    async def _capabilities_by_probe(self, doc_ref: DocRef) -> DocCapabilities:
        """Infer access by attempting the read the feature depends on.

        Used when the permission query is unavailable. It answers the question that
        matters -- can this document be worked on -- without claiming to know the
        collaborator list. Edit is assumed available where read succeeded, and a write
        that turns out to be refused fails with the platform's own message, which is a
        better outcome than declaring the document unusable in advance.
        """
        try:
            await self.read(doc_ref)
        except ProviderError:
            return DocCapabilities(
                can_read=False, can_edit=False, can_comment=False, can_resolve=False,
                has_revision_control=False, max_quote_chars=None, atomic_batch=False,
            )
        return DocCapabilities(
            can_read=True, can_edit=True, can_comment=True, can_resolve=False,
            has_revision_control=False,
            # Same measured platform fact as the member-list path: the truncation
            # point belongs to the platform, not to how access was determined.
            max_quote_chars=128, quote_truncates_unmarked=True,
            atomic_batch=False,
        )

    # ---------------------------------------------------------------- reading

    def doc_url(self, doc_ref: DocRef, kind: str = "") -> str:
        """The link the platform gave for this document, or the token.

        Not built from a template: a Feishu document's URL begins with the tenant's own
        domain, and there is no way to derive it from a token. Returning the token when
        no URL was seen is the honest answer -- a person can paste a token into the
        panel, and a fabricated link would only look right.
        """
        return self._url_cache.get(doc_ref) or str(doc_ref)

    def note_kind(self, doc_ref: DocRef, kind: str) -> None:
        """Accept a format learned elsewhere -- the panel's persisted metadata.

        The kind cache is process memory and the pasted link that taught it does not
        come back after a restart; the panel's store is what survives. Without this
        seam a restarted process routes a known spreadsheet down the docx paths until
        someone pastes the link again.
        """
        if kind:
            self._kind_cache[str(doc_ref)] = str(kind)

    def note_url(self, doc_ref: DocRef, url: str) -> None:
        """Accept a document's link from the panel's persisted metadata.

        A Feishu link is not derivable from a token, so a provider that never saw one
        answers ``doc_url`` with the bare token -- and, worse, a document *created* in
        a fresh process had no tenant domain to build its own link from, so the person
        got a token instead of a link (measured 2026-09-03). One seeded link teaches
        the tenant origin (`_tenant_origin`), which every later create reuses. Same
        survives-restart contract as ``note_kind``: process memory, refilled from the
        store by priming.
        """
        u = str(url or "").strip()
        if u.startswith("http"):
            self._url_cache.setdefault(str(doc_ref), u.split("?", 1)[0].split("#", 1)[0])

    async def doc_kind(self, doc_ref: DocRef) -> str:
        """Which format this document is.

        Answered from what discovery already saw, and otherwise assumed to be a docx.
        The assumption is the safe one: docx is the only format that was ever reachable
        before this, so a token arriving from somewhere else -- a link pasted into the
        panel -- behaves exactly as it did. A markdown file or spreadsheet adopted that
        way reads as a docx and fails on the fetch, with the platform's own message,
        which is a better outcome than a metadata call on every read to serve a case
        the listing already covers.
        """
        return self._kind_cache.get(doc_ref, "document")

    async def text_domain_for(self, doc_ref: DocRef) -> str:
        kind = await self.doc_kind(doc_ref)
        return feishu_formats.TEXT_DOMAIN.get(kind, self.text_domain)

    async def read(self, doc_ref: DocRef) -> DocSnapshot:
        """The body as flat text, plus how that text maps back onto the document.

        The CLI answers with ``document.content`` -- one string, XML by default and
        markdown on request -- rather than a block array, so the body arrives already
        flat and markdown is what this asks for: the rails work in character offsets
        over plain text, and XML tags would count as characters they must not.

        The segment map exists for Google, where document indices and characters
        diverge. Here the whole body is one run, which is what a single segment says.
        Block-level addressing is recovered at write time by fetching with ids, so
        reading stays cheap and the write pays for the precision it needs.
        """
        kind = await self.doc_kind(doc_ref)
        reader = feishu_formats.READERS.get(kind)
        if reader is not None:
            return await reader(self, doc_ref)
        data = await self._cli.json(
            ["docs", "+fetch", "--doc", doc_ref, "--doc-format", "markdown"]
        )
        doc = _first(data, "document", default={}) or {}
        body = str(_first(doc, "content", default="") or "")
        return DocSnapshot(
            doc_id=str(_first(doc, "document_id", default=doc_ref) or doc_ref),
            kind="document",
            # Confirmed present in the response contract, and the same value
            # ``docs +update --revision-id`` pins a write to.
            revision_id=str(_first(doc, "revision_id", default="") or ""),
            text=body,
            segments=(
                Segment(char_start=0, char_end=len(body), index_start=0, index_end=1),
            ),
        )

    async def list_comments(
        self, doc_ref: DocRef, *, include_resolved: bool = False
    ) -> list[DocComment]:
        # TENANT-VERIFY (2026-09-02, cli 1.0.89): a bare token now requires an
        # explicit --type; the spike-era CLI inferred it. The document's kind is
        # already cached on the read path, and docx is the right default for a
        # document never read (comments are polled after adoption, which reads).
        def make(ftype: str) -> list[str]:
            args = ["drive", "+list-comments", "--token", doc_ref, "--type", ftype, "--need-relation"]
            # The CLI defaults to unresolved only, so asking for everything is explicit.
            args += ["--solved-status", "all" if include_resolved else "false"]
            return args

        data = await self._drive_json(doc_ref, make)
        # The schema names this list `items`, alongside has_more/page_token.
        raw = _first(data, "items", default=[]) or []
        out: list[DocComment] = []
        for c in raw:
            cid = str(_first(c, "comment_id", default="") or "")
            if not cid:
                continue
            author = _first(c, "user_id", default="") or ""
            reply_rows = (_first(c, "reply_list", default={}) or {}).get("replies") or []
            # A mention anywhere in the thread marks the thread: the comment's own
            # body is reply one on this platform, so the walk covers both at once.
            # A mention authored by this agent or another is not counted: where a
            # mention triggers, counting one an agent wrote would let an agent summon
            # an agent, the exact recruitment the loop prohibition forbids. Only a
            # mention a person typed becomes a trigger signal.
            mentioned: list[str] = []
            # Per reply, the same parse and the same author filter: the follow-up
            # gate reads each reply's own mention set, and a reply built without
            # one can never continue a thread on this platform.
            reply_mentions: list[tuple[str, ...]] = []
            for r in reply_rows:
                r_author = _first(r, "user_id", default="")
                if self._is_self(r_author) or self._is_other_agent(r_author):
                    reply_mentions.append(())
                    continue
                ids = _mentioned_ids(_first(r, "content", default=None))
                mentioned += ids
                reply_mentions.append(tuple(dict.fromkeys(ids)))
            replies = tuple(
                DocReply(
                    reply_id=str(_first(r, "reply_id", default="") or ""),
                    author_is_self=self._is_self(_first(r, "user_id", default="")),
                    author_is_service_account=self._is_other_agent(
                        _first(r, "user_id", default="")
                    ),
                    author_display_name=str(_first(r, "name", "user_name", default="") or ""),
                    created_time=str(_first(r, "create_time", default="") or ""),
                    content=_reply_text(_first(r, "content", default=None)),
                    mentioned_addresses=r_mentions,
                )
                for r, r_mentions in zip(reply_rows, reply_mentions)
            )
            out.append(
                DocComment(
                    comment_id=cid,
                    # Author identity is a platform fact here, unlike Google, which is
                    # what makes watch_grant.from implementable on this provider.
                    author_is_self=self._is_self(author),
                    author_is_service_account=self._is_other_agent(author),
                    author_display_name=str(_first(c, "name", "user_name", default="") or ""),
                    created_time=str(_first(c, "create_time", default="") or ""),
                    content=_comment_text(c),
                    # `quote` is in the response contract, which is what the rails
                    # anchor on. Without it a comment could not scope an edit.
                    quoted_text=str(_first(c, "quote", default="") or ""),
                    resolved=bool(_first(c, "is_solved", default=False)),
                    mentioned_addresses=tuple(dict.fromkeys(mentioned)),
                    replies=replies,
                )
            )
        return out

    def _is_self(self, author_id: Any) -> bool:
        """Whether a comment or reply is the bot's own.

        Compared by id, never by display name: a person can set their name to the
        bot's, and the self-filter is what stops the agent answering itself forever.
        An unknown id is not self -- the failure that lets a loop start is calling
        someone else's comment ours, so the doubt resolves the other way.
        """
        me = (self._self_open_id or "").strip()
        other = str(author_id or "").strip()
        return bool(me and other and me == other)

    def _is_other_agent(self, author_id: Any) -> bool:
        """Whether an author is some *other* agent, for the loop prohibition.

        IC-6 forbids deciding this from a display-name suffix: Google's providers end
        in .iam.gserviceaccount.com, a Feishu bot's name does not, and a provider that
        borrowed that test would classify every bot as a person -- invariant ⑤ would
        fail exactly where two deployments share a document.

        The platform fact that would answer it is not in the comment payload: the
        contract carries a bare ``user_id`` and no identity type. Until a tenant shows
        what a bot's authorship looks like (spike 9), this reports False, which is the
        safe direction for the one thing it feeds: an unrecognised author is treated as
        a person, so a comment is answered rather than silently ignored. The cost is
        that agent-to-agent loops across deployments are not yet cut here, which is the
        residue §16.8 already records and the content marker is meant to close.

        The roster closes that residue where it matters most -- mention-triggering,
        where an agent's post could otherwise become a summons. A declared open_id is a
        known other agent; nothing else is, so an unrecognised author is still treated
        as a person (the safe direction for answering).
        """
        aid = str(author_id or "").strip()
        return bool(aid) and aid in self._roster

    # ---------------------------------------------------------------- writing

    async def edit(
        self,
        doc_ref: DocRef,
        old_string: str,
        new_string: str,
        *,
        revision_id: str | None = None,
    ) -> EditResult:
        return await self.edit_batch(
            doc_ref, [(old_string, new_string)], required_revision_id=revision_id or ""
        )

    async def edit_batch(
        self,
        doc_ref: DocRef,
        edits: list[tuple[str, str]],
        *,
        required_revision_id: str,
        window: tuple[int, int] | None = None,
        highlight: bool = False,
    ) -> EditResult:
        """One edit, submitted once.

        More than one is refused here as well as upstream. The upstream check reads
        capabilities and is the one a person sees a sentence from; this one is the
        guarantee, so a caller that reaches the provider directly cannot half-write a
        document by going around it.
        """
        if len(edits) > 1:
            raise ProviderError(
                "invalid",
                "本平台不支持一次提交多处修改；请逐条调用。",
            )
        if not edits:
            return EditResult("applied", new_revision_id="")
        old, new = edits[0]

        # Uniqueness is decided here, by the rail's rule, before the platform is asked
        # to substitute anything. str_replace matches on its own terms, and a pattern
        # that appears twice would otherwise be resolved by the platform's choice
        # rather than by the range a person approved.
        snap = await self.read(doc_ref)
        writer = feishu_formats.WRITERS.get(snap.kind)
        if writer is not None:
            # ``window`` is carried through so that this layer judges uniqueness by the
            # same rule the range rail did. Dropping it re-judges across the whole body,
            # and in a spreadsheet a quote of "42" matches every cell showing 42 -- the
            # proposal is refused after a person approved it.
            #
            # ``highlight`` is likewise not attempted -- no styling primitive exists on
            # this CLI's update surface for either format, and inventing one out of a
            # cell background would be a separate, permanent change to the document
            # (C9: declare, do not simulate).
            return await writer(
                self, doc_ref, snap, edits, required_revision_id, window
            )
        if old and not self._unique_in_window(snap, old, window):
            return EditResult("locate_failed", new_revision_id="")

        args = ["docs", "+update", "--doc", doc_ref]
        if old:
            args += ["--command", "str_replace", "--pattern", old, "--content", new]
        else:
            # An empty old_string means writing into an empty document, which append
            # expresses; overwrite is avoided because it can drop comments and blocks
            # the CLI does not model.
            args += ["--command", "append", "--content", new]
        args += ["--doc-format", "markdown"]
        # **The revision is deliberately not pinned.** It was, on the reading that
        # ``--revision-id`` is Feishu's WriteControl; the sibling command's help text
        # says otherwise, in words: for ``slides +update-slide``, "pinning an older
        # revision rebuilds the page from that snapshot and **discards newer edits to
        # it**". ``docs +update`` documents the same flag as a "base revision id" with
        # the same ``-1`` default, so the same reading applies until a tenant says
        # otherwise.
        #
        # If that is what it does, pinning is worse than having no lock at all: a
        # concurrent edit stops being a refused write and becomes a destroyed one, and
        # the caller is told "applied". Leaving it at latest and declaring no revision
        # control fails safe under either reading -- the content check below is what
        # actually guards the write.
        #
        # TENANT-VERIFY: send an update pinned to a stale revision against a document
        # edited in between, and see whether it errors or silently discards. If it
        # errors, this is a real lock and both this block and ``capabilities`` change
        # back together.
        # **Highlighting is unavailable here, and that is reported rather than raised.**
        #
        # It used to raise. Measured, that made ``apply_for_comment`` fail on every
        # single call against this platform -- the tool asks for highlighting
        # unconditionally -- so the entire apply_scoped watch level was unusable on
        # Feishu, and had been since PR3, with no test catching it because the fake
        # provider in the suite always accepts the flag.
        #
        # Refusing was the recorded decision (§17.6: degrade to refusal), and it is the
        # wrong one. What ring ⑥ needs is that the reader can see what changed; a
        # background colour is one way to show them, not the requirement itself. The
        # write happens, ``highlighted=False`` comes back, and the caller spells the
        # change out in its reply instead. That substitutes an honest mechanism rather
        # than simulating a missing one, which is what C9 forbids.
        highlighted = False

        # Written before the platform call and settled after it (IC-2's write-ahead
        # shape): a crash between the two leaves a pending entry for the sweep, which
        # is the whole point of recording intent first.
        receipt_id = self._receipt_begin(doc_ref, [(old, new)], highlight=highlighted)

        res = await self._cli.run(args)
        if not res.ok:
            err = _classify(res.code, res.stderr)
            low = f"{res.stderr}".lower()
            if "revision" in low or "conflict" in low or "version" in low:
                self._receipt_abort(receipt_id, "conflict")
                return EditResult("conflict", new_revision_id="")
            self._receipt_abort(receipt_id, err.kind)
            raise err
        try:
            payload = json.loads(res.stdout or "{}")
        except ValueError:
            payload = {}
        doc = ((payload.get("data") or {}).get("document") or {})
        new_rev = str(doc.get("revision_id") or "")
        self._receipt_commit(receipt_id, new_rev, highlighted=highlighted)
        return EditResult("applied", new_revision_id=new_rev, highlighted=highlighted,
                          receipt_id=receipt_id)

    @staticmethod
    def _unique_in_window(
        snap: DocSnapshot, old: str, window: tuple[int, int] | None
    ) -> bool:
        """Whether ``old`` occurs exactly once where the rail allowed it.

        The rail and the write must judge uniqueness by one rule: inside the approved
        window when there is one, across the body otherwise. Disagreement means an edit
        the rail passed gets refused after a person already approved it.
        """
        lo, hi = window if window else (0, len(snap.text))
        return snap.text[lo:hi].count(old) == 1

    # -------------------------------------------------------- receipt plumbing

    def _receipt_begin(self, doc_ref, edits, *, highlight, regions=None):
        """Record the intent before the platform is touched.

        Mechanical, inside the write primitive, so a model cannot skip it (IC-2). A
        sink that is absent or that fails records nothing and refuses nothing: the
        fail-closed duty belongs to the caller that requires a sink, and a write must
        not die on its own bookkeeping.

        ``regions`` names the addressed form of each entry, parallel to ``edits``. A
        region receipt's old and new are the region's flattened content -- the pair
        the inverse is materialized from -- and the address is what the inverse is
        written back through. A region write's old is computed here rather than named
        by the caller, so a comment-commissioned one attributes every edit via the
        blanket ``for_comment_ids`` instead of the by-old map.
        """
        sink = self.receipt_sink
        if sink is None:
            return None
        meta = getattr(self, "receipt_meta", None) or {}
        by_old = meta.get("for_comment_ids_by_old") or {}
        blanket = [str(x) for x in (meta.get("for_comment_ids") or [])]
        rows = [
            {"old": old, "new": new,
             "for_comment_ids": list(dict.fromkeys(
                 list(by_old.get(old, [])) + blanket
             ))}
            for old, new in edits
        ]
        # Each region spec is ``(address, old_grid)``: the flat old in the pair reads
        # as history; the grid is what a revert actually writes back, kept verbatim
        # because flattening is lossy once a cell's text contains the row separator.
        for i, (addr, old_grid) in enumerate(regions or []):
            rows[i]["region"] = addr
            rows[i]["old_grid"] = old_grid
        try:
            return sink.begin(
                str(doc_ref), rows, highlight=highlight,
                source=str(meta.get("source") or ""),
                executor=str(meta.get("executor") or ""),
            )
        except Exception:  # noqa: BLE001 - the write must not die on audit plumbing
            logger.exception("[clouddoc] receipt begin failed")
            return None

    def _receipt_commit(self, receipt_id, new_rev, *, highlighted: bool | None = None):
        """Close the receipt, correcting the highlight flag with what actually happened.

        ``begin`` recorded the request; only the platform knows the outcome, and the
        panel's unhighlight button reads this field to decide whether there is anything
        to undo.
        """
        if receipt_id is None or self.receipt_sink is None:
            return
        try:
            self.receipt_sink.commit(
                receipt_id, revision_after=new_rev, highlighted=highlighted
            )
        except Exception:  # noqa: BLE001
            logger.exception("[clouddoc] receipt commit failed")

    def _receipt_abort(self, receipt_id, reason):
        if receipt_id is None or self.receipt_sink is None:
            return
        try:
            self.receipt_sink.abort(receipt_id, reason=reason)
        except Exception:  # noqa: BLE001
            logger.exception("[clouddoc] receipt abort failed")

    async def write_regions(
        self,
        doc_ref: DocRef,
        regions: list[tuple[str, list[list[str]]]],
        *,
        required_revision_id: str = "",
    ) -> EditResult:
        """D15's addressed write, for the formats that are addressed by something other
        than position. A docx has no region form and the base class says so."""
        kind = await self.doc_kind(doc_ref)
        writer = feishu_formats.REGION_WRITERS.get(kind)
        if writer is None:
            return await super().write_regions(
                doc_ref, regions, required_revision_id=required_revision_id
            )
        return await writer(
            self, doc_ref, regions, required_revision_id=required_revision_id
        )

    async def read_regions(self, doc_ref: DocRef, regions: list[str]) -> list[str]:
        """The read half of the addressed write, for the revert path's anchor check."""
        kind = await self.doc_kind(doc_ref)
        reader = feishu_formats.REGION_READERS.get(kind)
        if reader is None:
            return await super().read_regions(doc_ref, regions)
        return await reader(self, doc_ref, regions)

    async def clear_highlight(self, doc_ref: DocRef, texts: list[str]) -> dict:
        """Remove the highlight over the given text.

        The write channel has no highlight primitive here (see the module docstring),
        so nothing was ever painted and there is nothing to clear. Answering the shape
        callers expect keeps revert and the resolve-driven clearing working -- they
        call this unconditionally, and an AttributeError would turn a successful undo
        into a crash over a decoration that does not exist on this platform.
        """
        return {"cleared": 0, "missed": list(texts)}

    # ---------------------------------------------------------------- comments

    def _app_id_hint(self) -> str:
        """The bound app id, used to find the app's own row in a member list.
        The lark-cli profile name is the app id in this deployment."""
        return getattr(self._cli, "_profile", "") or ""

    def _drive_type(self, doc_ref: DocRef) -> str:
        """The --type every drive comment verb now demands for a bare token
        (TENANT-VERIFY 2026-09-02, cli 1.0.89: it used to be inferred)."""
        if str(doc_ref) in self._wiki_tokens:
            return "wiki"
        kind = self._kind_cache.get(str(doc_ref), "")
        return {
            "spreadsheet": "sheet",
            "presentation": "slides",
            # A markdown file is a Drive file; its comment and member verbs take
            # --type file. Left unmapped it went out as docx, hit "not exist", and
            # burned the wiki retry for nothing (measured on the markdown live run).
            "markdown": "file",
        }.get(kind, "docx")

    async def _drive_json(self, doc_ref: DocRef, make_args) -> Any:
        """Run a drive verb, learning a wiki-hosted document the honest way.

        Feishu masks both no-permission and wrong-container reads as "not
        exist". For a token adopted without its /wiki/ link there is no way to
        know the container up front, so the first failure is retried once as
        wiki; success teaches the flavor for every later call."""
        try:
            return await self._cli.json(make_args(self._drive_type(doc_ref)))
        except ProviderError as exc:
            token = str(doc_ref)
            if token not in self._wiki_tokens and (
                "not exist" in str(exc) or "invalid parameter" in str(exc).lower()
            ):
                data = await self._cli.json(make_args("wiki"))
                self._wiki_tokens.add(token)
                return data
            raise

    @staticmethod
    def _reply_payload(content: str) -> str:
        # TENANT-VERIFY (2026-09-02, cli 1.0.89): --content takes a JSON element
        # array, not plain text -- plain text is rejected as invalid JSON, which
        # would silence every mechanical reply on this platform.
        return json.dumps([{"type": "text", "text": content}], ensure_ascii=False)

    async def reply_comment(self, doc_ref: DocRef, comment_id: str, content: str) -> str:
        data = await self._drive_json(doc_ref, lambda ftype: [
            "drive", "+add-reply", "--token", doc_ref, "--type", ftype,
            "--comment-id", comment_id, "--content", self._reply_payload(content),
        ])
        return str(_first(data, "reply_id", "id", default="") or "")

    async def update_reply(
        self, doc_ref: DocRef, comment_id: str, reply_id: str, content: str
    ) -> None:
        await self._drive_json(doc_ref, lambda ftype: [
            "drive", "+update-reply", "--token", doc_ref, "--type", ftype,
            "--comment-id", comment_id, "--reply-id", reply_id,
            "--content", self._reply_payload(content),
        ])

    async def delete_reply(self, doc_ref: DocRef, comment_id: str, reply_id: str) -> None:
        await self._cli.json(
            ["drive", "+delete-reply", "--token", doc_ref, "--type", self._drive_type(doc_ref),
             "--comment-id", comment_id,
             "--reply-id", reply_id]
        )

    async def resolve_comment(self, doc_ref: DocRef, comment_id: str) -> None:
        """Not offered, on principle rather than platform limitation.

        The platform has the API. Invariant ③ says the agent does not close a thread a
        person opened: resolving is the reader's acknowledgement that the answer was
        the one they wanted, and an agent doing it removes the acknowledgement rather
        than earning it. PR1 removed this for Google and it does not come back here.
        """
        raise ProviderError("unsupported", "agent 不解决他人开启的评论线程。")

    # ---------------------------------------------------------------- documents

    async def create_document(self, title: str) -> DocRef:
        try:
            data = await self._cli.json(["docs", "+create", "--title", title])
        except ProviderError as exc:
            # Whether an app identity may own a file is the tenant's policy. Google
            # reports its answer as "storage quota exceeded", which sends people to
            # empty a trash folder that was never full; whatever Feishu calls it, the
            # useful sentence is the same one, so the failure is translated rather
            # than relayed.
            if exc.kind in ("forbidden", "invalid") or "quota" in str(exc).lower():
                self._can_own_documents = False
                raise ProviderError(
                    "forbidden",
                    "创建失败：此部署的应用身份不能在飞书名下持有文档。"
                    "请让用户自己新建文档并共享给本应用。",
                ) from exc
            raise
        doc = _first(data, "document", default=data) or {}
        token = str(
            _first(doc, "document_id", "token", "obj_token", default="") or ""
        )
        if not token:
            raise ProviderError("unknown", "创建文档未返回 token。")
        self._can_own_documents = True
        # The create call returns no link, and a Feishu link starts with the tenant's
        # own domain, which cannot be derived from a token. It can be learned from any
        # link this provider has already seen (a pasted document, the panel's rows):
        # the tenant is the same for every document the app reaches. With no link
        # ever seen the token stands, as doc_url documents.
        origin = self._tenant_origin()
        if origin:
            self._url_cache[token] = f"{origin}/docx/{token}"
        if not self._self_open_id:
            await self._learn_self_from_owned(token)
        return token

    def _tenant_origin(self) -> str:
        for url in self._url_cache.values():
            m = re.match(r"^(https?://[^/]+)/", str(url or ""))
            if m:
                return m.group(1)
        return ""

    async def _learn_self_from_owned(self, token: str) -> None:
        """Learn the bot's own open_id from a document it just created.

        Spike 9 fell the other way on this tenant: ``whoami`` answers without an
        open_id, so the bot's own comments could not be recognised by author and
        unattended dispatch had nothing to filter with. The owner of a document this
        very call created is this identity -- which makes the metas query a mechanical
        way to learn the id, with no guess and no configuration. Fail-soft: a create
        must not die on identity bookkeeping, and §16.8's content marker remains the
        fallback when no document was ever created from here.
        """
        try:
            data = await self._cli.json([
                "drive", "metas", "batch_query", "--data",
                json.dumps({"request_docs": [{"doc_token": token, "doc_type": "docx"}]}),
            ])
            metas = _first(data or {}, "metas", default=[]) or []
            meta = metas[0] if isinstance(metas, list) and metas else {}
            owner = str(_first(meta, "owner_id", default="") or "")
            if owner.startswith("ou_"):
                self._self_open_id = owner
                if self._identity is not None and not self._identity.address:
                    self._identity = AgentIdentity(
                        display_name=self._identity.display_name, address=owner,
                    )
        except Exception:  # noqa: BLE001 - the create must not fail on this
            logger.debug("[clouddoc] owner-based identity learning skipped", exc_info=True)

    async def share_document(
        self, doc_ref: DocRef, address: str, *, role: str = "writer"
    ) -> None:
        member_type = self._member_type_of(address)
        # ASSUMPTION (spike 4): a bot may grant access to a document it owns.
        # lark-cli rates adding a member as a high-risk write and refuses without
        # ``--yes`` (measured 1.0.93: "requires confirmation", surfaced here as
        # ``unknown`` and reported to the person as an unrecognised address). The
        # confirmation it asks for has already been given: sharing is part of a
        # creation the person asked for and approved through the tool's own gate.
        await self._drive_json(doc_ref, lambda ftype: [
            "drive", "+member-add", "--token", doc_ref, "--type", ftype,
            "--member-id", address, "--member-type", member_type,
            "--perm", "edit" if role == "writer" else "view", "--yes",
        ])

    @staticmethod
    def _member_type_of(address: str) -> str:
        # --member-type is required and the CLI rejects a mismatch with the id's own
        # prefix, so it is derived from the address rather than defaulted: an open_id
        # starts ou_, a chat oc_, and anything with an @ is an email.
        if address.startswith("ou_"):
            return "openid"
        if address.startswith("oc_"):
            return "openchat"
        if address.startswith("on_"):
            return "unionid"
        if "@" in address:
            return "email"
        raise ProviderError(
            "invalid",
            f"无法判断 {address!r} 的类型：需要 open_id（ou_ 开头）或邮箱。",
        )

    async def trash_document(self, doc_ref: DocRef) -> None:
        # Feishu's delete moves the file to the owner's recycle bin (the app's, for a
        # document the app created), where a person can bring it back from the UI.
        await self._drive_json(doc_ref, lambda ftype: [
            "drive", "+delete", "--file-token", doc_ref, "--type", ftype, "--yes",
        ])

    async def list_accessible_documents(self) -> list[DocSummary]:
        """Documents the bot can reach, for adoption.

        Whether a bot may enumerate what was shared with it is the tenant's policy, not
        something this code can settle in advance -- so it asks, and an answer of "no"
        is a degraded capability rather than an error. Discovery then returns nothing
        and adoption happens the other way it already works: a person pastes a link
        into the panel. Raising instead would take the panel down over a feature it
        does not need.
        """
        try:
            data = await self._cli.json(["drive", "+list-files"])
        except ProviderError as exc:
            if exc.kind in ("forbidden", "unsupported", "invalid"):
                if self._discovery_available is not False:
                    logger.info(
                        "[clouddoc] 飞书应用无法枚举共享文件（%s），发现功能降级；"
                        "请在面板中粘贴文档链接纳管。",
                        exc.kind,
                    )
                self._discovery_available = False
                return []
            raise
        self._discovery_available = True
        out: list[DocSummary] = []
        for f in _first(data, "files", "items", default=[]) or []:
            token = str(_first(f, "token", "obj_token", "document_id", default="") or "")
            if not token:
                continue
            perm = str(_first(f, "perm", "permission", default="") or "").lower()
            ftype = str(_first(f, "type", "obj_type", default="") or "").lower()
            kind = feishu_formats.KIND_BY_TYPE.get(ftype, "")
            if not kind:
                # Seen but not workable. Kept out of the managed list and reported by
                # ``list_shared_unsupported`` instead, so a person who shared a deck
                # learns it arrived and why nothing happens -- silence reads as a
                # sharing mistake and sends them to re-share it.
                self._unsupported[token] = (
                    str(_first(f, "name", "title", default="") or ""),
                    ftype,
                )
                continue
            self._kind_cache[token] = kind
            url = str(_first(f, "url", "link", default="") or "")
            if url:
                self._url_cache[token] = url
            out.append(
                DocSummary(
                    doc_id=token,
                    title=str(_first(f, "name", "title", default="") or ""),
                    can_edit=perm in ("edit", "full_access", "owner") or not perm,
                    kind=kind,
                )
            )
        return out

    async def list_shared_unsupported(self) -> list[dict]:
        """Shared files this provider cannot co-edit.

        Reported rather than hidden: a person who shared a deck needs to know it was
        seen and why nothing happens, which is a different message from silence.

        Filled by the discovery pass above, which is the only place the file types are
        visible. Empty before discovery has run, and empty forever on a tenant that
        does not let the bot enumerate -- in which case the person is pasting links by
        hand anyway and finds out at adoption.
        """
        return [
            {
                "title": title,
                "kind": ftype or "file",
                "reason": feishu_formats.UNSUPPORTED_REASON.get(ftype, ""),
            }
            for title, ftype in self._unsupported.values()
        ]

    async def sharing_posture(self, doc_ref: DocRef) -> list[tuple[str, str]]:
        data = await self._drive_json(doc_ref, lambda ftype: [
            "drive", "+member-list", "--token", doc_ref, "--type", ftype,
        ])
        out: list[tuple[str, str]] = []
        for m in _first(data, "members", "items", default=[]) or []:
            who = str(_first(m, "member_id", "open_id", "name", default="") or "")
            perm = str(_first(m, "perm", "role", default="") or "")
            if who:
                out.append((who, perm))
        return out
