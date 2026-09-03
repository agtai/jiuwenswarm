"""Offline tests for the Feishu provider.

What can be tested without a tenant is the part that is decisions rather than
observations: that the bot never acts as a user, that a multi-edit batch is refused
rather than half-applied, that an unknown author is not treated as the bot itself, and
that locating honours the window the rail approved. The platform's own shapes are
assumptions marked in the provider and settled by the spikes in §17.2; a stub stands
in for them here, and passing these tests says nothing about whether those assumptions
hold.
"""

from __future__ import annotations

import json

import pytest

from jiuwenswarm.agents.harness.common.tools.clouddoc.feishu_provider import (
    FeishuDocsProvider,
)
from jiuwenswarm.agents.harness.common.tools.clouddoc.lark_cli import (
    LarkCli,
    LarkResult,
    _classify,
)
from jiuwenswarm.agents.harness.common.tools.clouddoc.provider import ProviderError

DOC = "DocToken123456"


class _StubCli(LarkCli):
    """A CLI that answers from a script and records what it was asked."""

    def __init__(self, replies: dict | None = None) -> None:
        super().__init__(binary="lark-cli", profile="p")
        self.calls: list[list[str]] = []
        self._replies = replies or {}
        self.fail_with: ProviderError | None = None

    @property
    def available(self) -> bool:
        return True

    async def run(self, args, *, timeout=None) -> LarkResult:
        self.calls.append(list(args))
        if self.fail_with is not None:
            return LarkResult(stdout="", stderr=str(self.fail_with), code=1)
        key = " ".join(args[:2])
        payload = self._replies.get(key)
        # The real CLI answers in an envelope; the stub does too, or the code under
        # test would be exercised against a shape it never sees.
        return LarkResult(
            stdout=json.dumps({"ok": True, "identity": "bot", "data": payload or {}}),
            stderr="", code=0,
        )

    async def json(self, args, *, timeout=None):
        res = await self.run(args, timeout=timeout)
        if not res.ok:
            raise self.fail_with or ProviderError("unknown", res.stderr)
        return json.loads(res.stdout).get("data")


def _provider(replies: dict | None = None) -> tuple[FeishuDocsProvider, _StubCli]:
    p = FeishuDocsProvider(profile="p", self_open_id="ou_bot")
    stub = _StubCli(replies)
    p._cli = stub
    return p, stub


# --------------------------------------------------------------------- identity


def test_every_command_is_issued_as_the_bot():
    """Acting as a user misattributes the write, and it breaks the loop prohibition:
    the agent recognises its own events by author."""
    cli = LarkCli(binary="lark-cli", profile="p")
    args = cli._base_args()
    assert "--as" in args and args[args.index("--as") + 1] == "bot"
    assert "user" not in args


@pytest.mark.asyncio
async def test_an_unknown_author_is_not_the_bot():
    """The failure that starts a loop is calling someone else's comment ours, so doubt
    resolves toward not-self."""
    p, _ = _provider()
    assert p._is_self("ou_bot") is True
    assert p._is_self("ou_someone") is False
    assert p._is_self("") is False
    assert p._is_self(None) is False


@pytest.mark.asyncio
async def test_identity_is_compared_by_id_never_by_display_name():
    """A person can set their display name to the bot's; the id is the fact."""
    p = FeishuDocsProvider(self_open_id="ou_bot")
    p._cli = _StubCli()
    assert p._is_self("bot") is False


# --------------------------------------------------------------------- capabilities


@pytest.mark.asyncio
async def test_the_platform_declares_it_cannot_batch_atomically():
    """C9: a missing capability is declared, not simulated. Upstream refuses the batch
    on the strength of this flag."""
    # The live shape (TENANT-VERIFY 2026-09-02): an items array, one row per
    # collaborator, the app's own row keyed by its appid member type.
    p, _ = _provider({"drive +member-list": {"items": [
        {"member_id": "ou_owner", "member_type": "openid", "perm": "full_access"},
        {"member_id": "cli_app", "member_type": "appid", "perm": "edit"},
    ]}})
    caps = await p.capabilities(DOC)
    assert caps.atomic_batch is False
    assert caps.can_edit is True


@pytest.mark.asyncio
async def test_no_optimistic_locking_is_claimed_because_the_flag_is_not_one():
    """This asserted the opposite, on the reading that ``--revision-id`` is Feishu's
    WriteControl. The CLI's own help text for the sibling command says what the flag
    actually does: pinning an older revision "rebuilds the page from that snapshot and
    **discards newer edits to it**". ``docs +update`` documents the same flag the same
    way, as a "base revision id".

    A flag that destroys a concurrent edit is not a lock, and claiming one here is
    worse than claiming nothing: admission would rely on protection that does not
    exist, and the person would be told "applied" about a write that removed someone
    else's work. Declared absent until a tenant proves otherwise (C9)."""
    p, _ = _provider({"drive +member-list": {"perm": "edit"}})
    caps = await p.capabilities(DOC)
    assert caps.has_revision_control is False


@pytest.mark.asyncio
async def test_a_document_the_bot_cannot_see_reports_no_capabilities():
    p, stub = _provider()
    stub.fail_with = ProviderError("not_found", "not found")
    caps = await p.capabilities(DOC)
    assert caps.can_read is False and caps.can_edit is False


# --------------------------------------------------------------------- writing


@pytest.mark.asyncio
async def test_a_multi_edit_batch_is_refused_at_the_provider_too():
    """The upstream check is what a person sees a sentence from; this one is the
    guarantee, so going around it cannot half-write a shared document."""
    p, stub = _provider()
    with pytest.raises(ProviderError) as e:
        await p.edit_batch(DOC, [("a", "b"), ("c", "d")], required_revision_id="")
    assert e.value.kind == "invalid"
    assert not stub.calls, "拒绝必须发生在任何写入之前"


@pytest.mark.asyncio
async def test_locating_honours_the_window_the_rail_approved():
    """The rail and the write must judge uniqueness by one rule, or an edit the rail
    passed is refused after a person approved it."""
    from jiuwenswarm.agents.harness.common.tools.clouddoc.provider import (
        DocSnapshot,
        Segment,
    )

    body = "甲句。乙句。甲句。"
    snap = DocSnapshot(
        doc_id=DOC, kind="document", revision_id="", text=body,
        segments=(
            Segment(char_start=0, char_end=3, index_start=0, index_end=1),
            Segment(char_start=4, char_end=7, index_start=1, index_end=2),
            Segment(char_start=8, char_end=11, index_start=2, index_end=3),
        ),
    )
    # Ambiguous across the whole body.
    assert FeishuDocsProvider._unique_in_window(snap, "甲句", None) is False
    # Unique inside the approved window.
    assert FeishuDocsProvider._unique_in_window(snap, "甲句", (0, 4)) is True


@pytest.mark.asyncio
async def test_a_single_edit_replaces_the_block_wholesale():
    """The write says "make this block read exactly this", so its outcome does not
    depend on the platform's own matching rules."""
    p, stub = _provider({
        "docs +fetch": {"document": {"content": "这一句需要被改写。", "revision_id": 7}},
    })
    res = await p.edit_batch(
        DOC, [("需要被改写", "已经改好")], required_revision_id="7"
    )
    assert res.status == "applied"
    update = [c for c in stub.calls if c[:2] == ["docs", "+update"]]
    assert update, "应当发出一次 docs +update"
    assert "str_replace" in update[0]
    assert "需要被改写" in update[0] and "已经改好" in update[0]
    # And the revision must **not** travel with it. Pinning to the revision the body
    # was read at looks like the Google write control it was modelled on, and does the
    # opposite: it rebuilds from that snapshot, discarding anything newer. Leaving the
    # write at latest is what fails safe under either reading of the flag.
    assert "--revision-id" not in update[0]


@pytest.mark.asyncio
async def test_an_edit_that_cannot_be_located_reports_rather_than_guessing():
    p, _ = _provider({"docs +fetch": {"document": {"content": "完全不同的内容。"}}})
    res = await p.edit_batch(DOC, [("找不到的原文", "新文")], required_revision_id="")
    assert res.status == "locate_failed"


# --------------------------------------------------------------------- principle


@pytest.mark.asyncio
async def test_resolving_a_thread_is_refused_on_principle():
    """The platform has the API; invariant ③ is why it is not offered. Resolving is the
    reader's acknowledgement, and an agent doing it removes the acknowledgement."""
    p, _ = _provider()
    with pytest.raises(ProviderError) as e:
        await p.resolve_comment(DOC, "c1")
    assert e.value.kind == "unsupported"


# --------------------------------------------------------------------- link parsing


@pytest.mark.parametrize(
    "given,expected",
    [
        ("https://x.feishu.cn/docx/AbC123456789", "AbC123456789"),
        ("https://x.feishu.cn/docx/AbC123456789?from=space", "AbC123456789"),
        ("https://x.feishu.cn/wiki/W12345678", "W12345678"),
        ("BareToken12345", "BareToken12345"),
    ],
)
def test_document_links_and_tokens_are_accepted(given, expected):
    p = FeishuDocsProvider()
    assert p.parse_doc_ref(given) == expected


def test_an_unparseable_reference_is_refused():
    p = FeishuDocsProvider()
    for bad in ("", "   ", "not a token at all"):
        with pytest.raises(ProviderError):
            p.parse_doc_ref(bad)


# --------------------------------------------------------------------- error mapping


@pytest.mark.parametrize(
    "stderr,kind",
    [
        ("permission denied", "forbidden"),
        ("document not found", "not_found"),
        ("429 too many requests", "rate_limited"),
        ("request timed out", "transport"),
        ("invalid token", "auth"),
        ("something nobody predicted", "unknown"),
    ],
)
def test_failures_map_onto_the_shared_error_vocabulary(stderr, kind):
    """A Feishu failure should reach a person as the same kind of sentence a Google
    failure does, and an unrecognised one is unknown rather than guessed at."""
    assert _classify(1, stderr).kind == kind


# --------------------------------------------------------------------- vendor choice


def test_the_vendor_is_read_from_the_credentials_not_declared(tmp_path):
    """The file decides, because the file is what the calls actually run on. A vendor
    field in config could disagree with it, and then one of the two is a lie."""
    from jiuwenswarm.agents.harness.common.tools.clouddoc.factory import detect_vendor

    g = tmp_path / "g.json"
    g.write_text(json.dumps({"type": "service_account", "client_email": "a@b.iam"}))
    assert detect_vendor(str(g)) == "google"

    f = tmp_path / "f.json"
    f.write_text(json.dumps({"app_id": "cli_x", "app_secret": "s"}))
    assert detect_vendor(str(f)) == "feishu"


def test_an_unrecognisable_credential_is_a_configuration_error(tmp_path):
    """Raised rather than defaulted: guessing a vendor produces calls that fail much
    later, with nothing pointing back at the file."""
    from jiuwenswarm.agents.harness.common.tools.clouddoc.factory import detect_vendor

    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"hello": "world"}))
    with pytest.raises(ProviderError):
        detect_vendor(str(bad))

    missing = tmp_path / "nope.json"
    with pytest.raises(ProviderError):
        detect_vendor(str(missing))


def test_a_feishu_credential_builds_a_feishu_provider(tmp_path):
    from jiuwenswarm.agents.harness.common.tools.clouddoc.factory import build_provider

    f = tmp_path / "f.json"
    f.write_text(json.dumps({"app_id": "cli_x", "app_secret": "s", "bot_open_id": "ou_b"}))
    prov = build_provider(str(f))
    assert prov.kind == "feishu"
    assert prov._is_self("ou_b") is True


# ------------------------------------------------- the commands the real CLI accepts


def _lark_binary() -> str | None:
    import shutil

    return shutil.which("lark-cli")


# Every command this provider issues, as it issues it. Checked against the installed
# binary rather than against a help text pasted into a comment, so a flag that is
# renamed upstream fails here instead of at a customer's first write.
_ISSUED_COMMANDS = [
    ["docs", "+fetch", "--doc", "T", "--detail", "with-ids", "--scope", "full"],
    ["docs", "+update", "--doc", "T", "--command", "str_replace",
     "--pattern", "old", "--content", "new", "--doc-format", "markdown",
     "--revision-id", "5"],
    ["docs", "+update", "--doc", "T", "--command", "append",
     "--content", "x", "--doc-format", "markdown"],
    ["docs", "+fetch", "--doc", "T", "--doc-format", "markdown"],
    ["docs", "+create", "--title", "T"],
    ["drive", "+list-comments", "--token", "T", "--type", "docx",
     "--need-relation", "--solved-status", "all"],
    ["drive", "+add-reply", "--token", "T", "--type", "docx",
     "--comment-id", "c1", "--content", '[{"type":"text","text":"hi"}]'],
    ["drive", "+member-list", "--token", "T", "--type", "docx"],
    ["drive", "+member-add", "--token", "T", "--type", "docx",
     "--member-id", "ou_x", "--member-type", "openid", "--perm", "edit", "--yes"],
]


@pytest.mark.skipif(_lark_binary() is None, reason="lark-cli 未安装")
@pytest.mark.parametrize("args", _ISSUED_COMMANDS, ids=lambda a: " ".join(a[:2]))
def test_the_cli_accepts_every_command_the_provider_issues(args):
    """--dry-run parses and validates without calling the platform, so this needs no
    tenant: an unknown flag comes back as "validation", while a well-formed call gets
    as far as "config"/not_configured, which is the credentials talking, not the
    command."""
    import json as _json
    import subprocess

    res = subprocess.run(
        [_lark_binary(), *args, "--as", "bot", "--dry-run"],
        capture_output=True, text=True, timeout=60,
    )
    payload = _json.loads(res.stderr or res.stdout or "{}")
    kind = (payload.get("error") or {}).get("type")
    assert kind != "validation", f"CLI 拒绝了这条命令：{payload.get('error')}"


@pytest.mark.skipif(_lark_binary() is None, reason="lark-cli 未安装")
def test_a_wrong_flag_is_actually_caught_by_that_check():
    """The check above is only worth having if it fails on a bad command. --text is
    what this provider used before the CLI was read; block content is --content."""
    import json as _json
    import subprocess

    res = subprocess.run(
        [_lark_binary(), "docs", "+update", "--doc", "T", "--command", "block_replace",
         "--block-id", "0", "--text", "x", "--as", "bot", "--dry-run"],
        capture_output=True, text=True, timeout=60,
    )
    payload = _json.loads(res.stderr or res.stdout or "{}")
    assert (payload.get("error") or {}).get("type") == "validation"


@pytest.mark.skipif(_lark_binary() is None, reason="lark-cli 未安装")
def test_the_error_envelope_is_read_from_its_fields_not_its_prose():
    """Classification reads error.type, because prose is what changes between
    releases. Run against the real binary with no credentials configured."""
    import subprocess

    import os, tempfile

    env = {**os.environ, "HOME": tempfile.mkdtemp()}  # an unconfigured store
    res = subprocess.run(
        [_lark_binary(), "whoami", "--as", "bot"],
        capture_output=True, text=True, timeout=60, env=env,
    )
    err = _classify(res.returncode, res.stderr)
    assert err.kind == "auth"
    # The hint is the actionable half and must survive into the message.
    assert "config init" in str(err)


# ------------------------------------------------ shapes taken from the CLI's schema


@pytest.mark.asyncio
async def test_a_reply_is_read_from_its_elements_not_as_a_string():
    """The schema gives content.elements, a list of typed runs. Read as a string every
    reply looks empty -- including the agent's own, which is how a verdict is
    recognised, so the loop would answer itself forever."""
    p, _ = _provider({
        "drive +list-comments": {
            "items": [{
                "comment_id": "c1",
                "user_id": "ou_someone",
                "create_time": 1700000000,
                "quote": "被引用的原文",
                "is_solved": False,
                "reply_list": {"replies": [
                    {"reply_id": "r1", "user_id": "ou_someone",
                     "create_time": 1700000000,
                     "content": {"elements": [
                         {"type": "person", "person": {"user_id": "ou_bot"}},
                         {"type": "text_run", "text_run": {"text": " 请改这句"}},
                     ]}},
                ]},
            }]
        }
    })
    comments = await p.list_comments(DOC)
    assert len(comments) == 1
    c = comments[0]
    assert c.content == "@ou_bot 请改这句", "评论正文取自首条回复,按元素类型读取"
    assert c.quoted_text == "被引用的原文"
    assert c.replies[0].content == "@ou_bot 请改这句"
    assert c.author_is_self is False


@pytest.mark.asyncio
async def test_the_body_and_its_revision_come_from_the_document_object():
    """content and revision_id are both under data.document; the revision is what a
    later write pins itself to."""
    p, _ = _provider({
        "docs +fetch": {"document": {
            "document_id": DOC, "content": "正文内容。", "revision_id": 12,
        }}
    })
    snap = await p.read(DOC)
    assert snap.text == "正文内容。"
    assert snap.revision_id == "12"
    assert snap.segments[0].char_end == len(snap.text)


@pytest.mark.asyncio
async def test_the_write_lands_and_reports_that_it_could_not_highlight():
    """This used to assert a refusal, and the refusal was the wrong call.

    ``apply_for_comment`` asks for highlighting unconditionally, so raising here made
    every unattended apply on this platform fail -- the whole apply_scoped watch level
    was unusable on Feishu, from PR3 onwards, with nothing catching it because the
    suite's fake provider always accepts the flag.

    What ring ⑥ needs is that the reader can see what changed; a background colour is
    one way of showing them, not the requirement. So the write lands, the result says
    plainly that nothing was painted, and the caller spells the change out in its reply
    instead. Substituting an honest mechanism, not simulating a missing one."""
    p, _ = _provider({"docs +fetch": {"document": {"content": "一句话。"}}})
    res = await p.edit_batch(
        DOC, [("一句话", "改过了")], required_revision_id="", highlight=True
    )
    assert res.status == "applied"
    assert res.highlighted is False, "平台不能高亮时必须如实回报，而不是默认 True"


# ------------------------------------------- capabilities the tenant decides, at runtime


class _RefusingCli(_StubCli):
    """A CLI that refuses one command and answers the rest, as a tenant policy would."""

    def __init__(self, refuse_prefix: str, kind: str = "forbidden", replies=None) -> None:
        super().__init__(replies)
        self._refuse = refuse_prefix
        self._kind = kind

    async def json(self, args, *, timeout=None):
        self.calls.append(list(args))
        if " ".join(args[:2]) == self._refuse:
            raise ProviderError(self._kind, "policy refuses this")
        payload = self._replies.get(" ".join(args[:2])) or {}
        return payload


@pytest.mark.asyncio
async def test_discovery_degrades_instead_of_breaking_the_panel():
    """Whether a bot may enumerate what was shared with it is tenant policy. A refusal
    means adoption happens from a pasted link instead -- it must not take the panel
    down over a feature the panel does not need."""
    p, _ = _provider()
    p._cli = _RefusingCli("drive +list-files")
    assert await p.list_accessible_documents() == []
    assert p._discovery_available is False


@pytest.mark.asyncio
async def test_capabilities_fall_back_to_reading_when_permissions_are_user_only():
    """Reading the collaborator list may itself be user-only. Answering "no access"
    would put a workable document into the comment-only bucket and admission would
    refuse it, so the question that matters is asked directly: can it be read."""
    p, _ = _provider()
    p._cli = _RefusingCli(
        "drive +member-list",
        replies={"docs +fetch": {"document": {"content": "正文", "revision_id": 3}}},
    )
    caps = await p.capabilities(DOC)
    assert caps.can_read is True and caps.can_edit is True
    assert caps.atomic_batch is False


@pytest.mark.asyncio
async def test_a_document_that_cannot_be_read_reports_no_access():
    """The fallback is a probe, not an assumption: when the read fails too, the
    document really is unusable and admission should refuse it."""
    p, _ = _provider()
    p._cli = _RefusingCli("drive +member-list")  # and no docs +fetch reply configured
    p._cli._replies = {}

    async def fail_fetch(args, *, timeout=None):
        raise ProviderError("forbidden", "no")

    p._cli.json = fail_fetch
    caps = await p.capabilities(DOC)
    assert caps.can_read is False and caps.can_edit is False


@pytest.mark.asyncio
async def test_being_unable_to_own_a_document_is_explained_not_relayed():
    """Google reports this as "storage quota exceeded", which sends people to empty a
    trash folder that was never full. Whatever Feishu calls it, the useful sentence is
    the same one."""
    p, _ = _provider()
    p._cli = _RefusingCli("docs +create")
    with pytest.raises(ProviderError) as e:
        await p.create_document("标题")
    assert "共享给本应用" in str(e.value)
    assert p._can_own_documents is False


def test_the_body_travels_as_markdown_so_markers_are_content():
    """Read and written with --doc-format markdown, so a marker round-trips instead of
    landing in someone's document as literal characters. The rail may allow them."""
    p, _ = _provider()
    assert p.text_domain == "markdown"


# ---------------------------------------- "is this author another agent" (IC-6)


@pytest.mark.asyncio
async def test_other_agent_detection_is_not_borrowed_from_google():
    """IC-6: the display-name suffix that identifies a Google service account says
    nothing here. A provider that borrowed it would call every Feishu bot a person and
    invariant ⑤ would fail exactly where two deployments share a document."""
    p, _ = _provider()
    for name in (
        "docs-agent@x.iam.gserviceaccount.com",  # Google's shape, meaningless here
        "ou_someone",
        "cli_app",
        "",
    ):
        assert p._is_other_agent(name) is False


@pytest.mark.asyncio
async def test_an_unrecognised_author_is_answered_rather_than_ignored():
    """Until a tenant shows what a bot's authorship looks like, the answer is False --
    the safe direction for what it feeds: a comment from someone unrecognised gets a
    reply instead of being silently dropped."""
    p, _ = _provider({
        "drive +list-comments": {
            "items": [{
                "comment_id": "c1", "user_id": "ou_unknown",
                "create_time": 1, "quote": "原文", "is_solved": False,
                "reply_list": {"replies": [
                    {"reply_id": "r1", "user_id": "ou_unknown", "create_time": 1,
                     "content": {"elements": [{"text_run": {"text": "看看这句"}}]}},
                ]},
            }]
        }
    })
    c = (await p.list_comments(DOC))[0]
    assert c.author_is_self is False
    assert c.author_is_service_account is False, "未识别的作者按人处理，评论会被回应"


@pytest.mark.asyncio
async def test_the_bots_own_comment_is_still_recognised():
    """Self-recognition works by open_id and is independent of the unresolved question
    about other agents -- the loop that matters most is answering oneself."""
    p, _ = _provider({
        "drive +list-comments": {
            "items": [{
                "comment_id": "c1", "user_id": "ou_bot",
                "create_time": 1, "quote": "原文", "is_solved": False,
                "reply_list": {"replies": []},
            }]
        }
    })
    c = (await p.list_comments(DOC))[0]
    assert c.author_is_self is True


# ------------------------------- the plumbing the rest of the machinery expects


class _Sink:
    def __init__(self) -> None:
        self.begun: list = []
        self.committed: list = []
        self.aborted: list = []

    def begin(self, doc_id, edits, *, highlight, source, executor=""):
        self.begun.append({"doc": doc_id, "edits": edits, "highlight": highlight,
                           "source": source, "executor": executor})
        return f"rcpt{len(self.begun)}"

    def commit(self, receipt_id, *, revision_after, highlighted=None):
        # highlighted corrects what begin() recorded: begin writes the request, and
        # only the platform knows the outcome.
        self.committed.append((receipt_id, revision_after))

    def abort(self, receipt_id, *, reason):
        self.aborted.append((receipt_id, reason))


@pytest.mark.asyncio
async def test_a_write_records_a_receipt_before_touching_the_platform():
    """Tracking and acceptance both read receipts, so a provider that produces none
    silently removes the ability to see or undo what the agent did. Recording happens
    inside the write primitive, where a model cannot skip it."""
    p, _ = _provider({
        "docs +fetch": {"document": {"content": "这一句需要被改写。", "revision_id": 4}},
    })
    sink = _Sink()
    p.receipt_sink = sink
    p.receipt_meta = {"source": "batch_edit",
                      "for_comment_ids_by_old": {"需要被改写": ["c1", "c2"]}}

    res = await p.edit_batch(DOC, [("需要被改写", "已经改好")], required_revision_id="4")
    assert res.status == "applied"
    assert len(sink.begun) == 1
    assert sink.begun[0]["source"] == "batch_edit"
    # The comment map must survive into the receipt, or a revert cannot notify the
    # threads the edit answered.
    assert sink.begun[0]["edits"][0]["for_comment_ids"] == ["c1", "c2"]
    assert sink.committed and sink.committed[0][0] == "rcpt1"


@pytest.mark.asyncio
async def test_a_failed_write_aborts_its_receipt_rather_than_leaving_it_pending():
    """A pending entry means "we do not know whether this landed" and the sweep will
    chase it. A refusal is known, so it is recorded as one."""
    p, stub = _provider({"docs +fetch": {"document": {"content": "原文。"}}})
    sink = _Sink()
    p.receipt_sink = sink

    # Only the write fails; the read before it must still succeed, or the receipt is
    # never opened and the test would pass for the wrong reason.
    async def run_failing_update(args, *, timeout=None):
        if list(args[:2]) == ["docs", "+update"]:
            return LarkResult(stdout="", stderr='{"error":{"type":"permission"}}', code=1)
        return LarkResult(
            stdout=json.dumps({"ok": True, "identity": "bot",
                               "data": {"document": {"content": "原文。"}}}),
            stderr="", code=0,
        )

    stub.run = run_failing_update
    with pytest.raises(ProviderError):
        await p.edit_batch(DOC, [("原文", "新文")], required_revision_id="")
    assert sink.aborted, "失败的写入必须结账，不能留 pending"


@pytest.mark.asyncio
async def test_a_write_without_a_sink_still_goes_through():
    """Recording is unconditional when wired and refuses nothing when not: the
    fail-closed duty belongs to the caller that requires a sink, and a write must not
    die on its own bookkeeping."""
    p, _ = _provider({"docs +fetch": {"document": {"content": "原文。"}}})
    assert p.receipt_sink is None
    res = await p.edit_batch(DOC, [("原文", "新文")], required_revision_id="")
    assert res.status == "applied"


@pytest.mark.asyncio
async def test_clearing_a_highlight_answers_instead_of_raising():
    """Revert and the resolve-driven clearing call this unconditionally. Nothing was
    ever painted on this platform, so there is nothing to clear -- but an
    AttributeError would turn a successful undo into a crash over a decoration that
    does not exist here."""
    p, _ = _provider()
    out = await p.clear_highlight(DOC, ["某段文字"])
    assert out["cleared"] == 0
    assert out["missed"] == ["某段文字"]


# --------------------------------------------------------------------- regions

SHEET_URL = "https://x.feishu.cn/sheets/SheetTok12345"

_SHEET_REPLIES = {
    "sheets +workbook-info": {
        "sheets": [{"title": "Sheet1",
                    "grid_properties": {"row_count": 3, "column_count": 2}}],
    },
    # The live shape (TENANT-VERIFY 2026-09-02): the grid nests inside ranges[0]
    # with the actual_range the platform really answered.
    "sheets +cells-get": {
        "ranges": [{
            "actual_range": "A1:B3",
            "cells": [["项目", "状态"], ["区域机械", "待验证"], ["回执链", "待验证"]],
        }],
    },
    "sheets +cells-set": {},
}


class _RegionSink(_Sink):
    def __init__(self) -> None:
        super().__init__()
        self.unverified: list = []

    def mark_unverified(self, receipt_id, *, detail):
        self.unverified.append((receipt_id, detail))


class _EchoingSheetCli(_StubCli):
    """After a write, the platform shows what was written; the stub does too, or the
    read-back verification under test would always disagree with itself."""

    async def json(self, args, *, timeout=None):
        data = await super().json(args, timeout=timeout)
        if args[:2] == ["sheets", "+cells-set"]:
            self._replies["sheets +cells-get"] = {
                "ranges": [{
                    "actual_range": "A1:B3",
                    "cells": [["项目", "状态"], ["区域机械", "已验证"], ["回执链", "待验证"]],
                }],
            }
        return data


@pytest.mark.asyncio
async def test_a_sheets_link_teaches_the_format():
    """A pasted link is the only place a spreadsheet announces itself: there is no
    listing on this platform to learn it from, and without the marker the token would
    read as a docx and fail on the fetch."""
    p, _ = _provider()
    ref = p.parse_doc_ref(SHEET_URL)
    assert ref == "SheetTok12345"
    assert await p.doc_kind(ref) == "spreadsheet"
    assert p._drive_type(ref) == "sheet"


@pytest.mark.asyncio
async def test_a_region_write_lands_with_a_sheet_qualified_receipt():
    p = FeishuDocsProvider(profile="p", self_open_id="ou_bot")
    stub = _EchoingSheetCli(dict(_SHEET_REPLIES))
    p._cli = stub
    sink = _RegionSink()
    p.receipt_sink = sink
    ref = p.parse_doc_ref(SHEET_URL)

    res = await p.write_regions(ref, [("Sheet1!B2", [["已验证"]])])
    assert res.status == "applied"
    written = next(c for c in stub.calls if c[:2] == ["sheets", "+cells-set"])
    assert "--sheet-name" in written and written[written.index("--sheet-name") + 1] == "Sheet1"
    assert written[written.index("--range") + 1] == "B2:B2"
    # The receipt's two ends are the region's content before and after, and the
    # address is sheet-qualified so the revert's anchor check can read it back.
    entry = sink.begun[0]["edits"][0]
    assert entry["region"] == "Sheet1!B2:B2"
    assert entry["old_grid"] == [["待验证"]]
    assert (entry["old"], entry["new"]) == ("待验证", "已验证")
    assert sink.committed and not sink.unverified


@pytest.mark.asyncio
async def test_a_multi_region_batch_is_refused_because_it_cannot_be_atomic():
    """The platform's only multi-range write is fail-fast without rollback, so a
    cross-rectangle move sent as one batch can land half. Declared, not simulated."""
    p, _ = _provider(dict(_SHEET_REPLIES))
    ref = p.parse_doc_ref(SHEET_URL)
    res = await p.write_regions(ref, [("Sheet1!A1", [["x"]]), ("Sheet1!B1", [["y"]])])
    assert res.status == "refused"
    assert "原子" in res.detail


@pytest.mark.asyncio
async def test_a_region_whose_shape_disagrees_is_refused():
    p, _ = _provider(dict(_SHEET_REPLIES))
    ref = p.parse_doc_ref(SHEET_URL)
    with pytest.raises(ProviderError) as err:
        await p.write_regions(ref, [("Sheet1!A1:B1", [["only one"]])])
    assert "形状" in str(err.value)


@pytest.mark.asyncio
async def test_a_formula_cell_anywhere_in_the_region_refuses_the_batch():
    """Writing over a formula replaces it with a literal that looks identical, and
    nothing on the document shows it happened (IC-7)."""
    replies = dict(_SHEET_REPLIES)
    replies["sheets +cells-get"] = {
        "ranges": [{
            "actual_range": "A1:B3",
            "cells": [["项目", "状态"],
                      ["区域机械", {"value": "待验证", "formula": "=A1&\"!\""}],
                      ["回执链", "待验证"]],
        }],
    }
    p, stub = _provider(replies)
    ref = p.parse_doc_ref(SHEET_URL)
    with pytest.raises(ProviderError) as err:
        await p.write_regions(ref, [("Sheet1!A2:B2", [["区域机械", "已验证"]])])
    assert "公式" in str(err.value)
    assert not any(c[:2] == ["sheets", "+cells-set"] for c in stub.calls)


@pytest.mark.asyncio
async def test_a_docx_has_no_region_form():
    p, _ = _provider()
    with pytest.raises(ProviderError) as err:
        await p.write_regions(DOC, [("Sheet1!A1", [["x"]])])
    assert err.value.kind == "unsupported"


@pytest.mark.asyncio
async def test_a_read_back_that_disagrees_demotes_the_receipt():
    """D19 tier 3b: "the platform accepted the request" and "the document shows the
    result" are different facts, and acceptance must read the second."""
    p, _ = _provider(dict(_SHEET_REPLIES))  # the stub never echoes the write back
    sink = _RegionSink()
    p.receipt_sink = sink
    ref = p.parse_doc_ref(SHEET_URL)
    res = await p.write_regions(ref, [("Sheet1!B2", [["已验证"]])])
    assert res.status == "applied"
    assert sink.unverified and sink.unverified[0][0] == "rcpt1"


@pytest.mark.asyncio
async def test_region_reading_answers_in_receipt_form():
    p, _ = _provider(dict(_SHEET_REPLIES))
    ref = p.parse_doc_ref(SHEET_URL)
    got = await p.read_regions(ref, ["Sheet1!B2", "Sheet1!A1:B1"])
    assert got == ["待验证", "项目\t状态"]


@pytest.mark.asyncio
async def test_a_spreadsheets_title_comes_from_drive_metadata():
    """``docs +fetch`` serves only a docx; the metas query answers any type, and the
    canonical URL it carries is learned so a bare token still links out."""
    p, _ = _provider({"drive metas": {"metas": [{
        "title": "区域实弹", "url": "https://x.feishu.cn/sheets/SheetTok12345",
        "owner_id": "ou_c004",
    }]}})
    ref = p.parse_doc_ref("SheetTok12345")
    p._kind_cache[ref] = "spreadsheet"
    assert await p.title(ref) == "区域实弹"
    assert p.doc_url(ref) == "https://x.feishu.cn/sheets/SheetTok12345"


@pytest.mark.asyncio
async def test_creating_a_document_teaches_the_bot_its_own_open_id():
    """whoami answers without an open_id on this tenant (spike 9's other leg), but the
    owner of a document this very call created is this identity -- learned
    mechanically, so unattended dispatch can recognise the bot's own comments."""
    p, _ = _provider({
        "docs +create": {"document": {"document_id": "NewTok"}},
        "drive metas": {"metas": [{"owner_id": "ou_learned"}]},
    })
    p._self_open_id = ""
    await p.create_document("t")
    assert p._is_self("ou_learned") is True


@pytest.mark.asyncio
async def test_identity_learning_never_fails_the_create():
    p, stub = _provider({"docs +create": {"document": {"document_id": "NewTok"}}})
    p._self_open_id = ""

    orig = stub.json
    async def flaky(args, *, timeout=None):
        if args[:2] == ["drive", "metas"]:
            raise ProviderError("unknown", "meta down")
        return await orig(args, timeout=timeout)
    stub.json = flaky

    assert await p.create_document("t") == "NewTok"


@pytest.mark.asyncio
async def test_a_noted_format_survives_where_the_pasted_link_did_not():
    """The kind cache is process memory; the panel's store is what survives a restart.
    Fed back through note_kind, a known spreadsheet stays off the docx paths."""
    p, _ = _provider({"drive metas": {"metas": [{"title": "复原标题"}]}})
    p.note_kind("SheetTok12345", "spreadsheet")
    assert p._drive_type("SheetTok12345") == "sheet"
    assert await p.title("SheetTok12345") == "复原标题"


@pytest.mark.asyncio
async def test_a_mention_in_the_thread_is_surfaced_as_an_address():
    """The mention-hint path compares addresses; a person element in any reply is the
    only mention signal this platform's payload carries, so it must surface or every
    @ goes silently unanswered."""
    p, _ = _provider({"drive +list-comments": {"items": [{
        "comment_id": "c1", "user_id": "ou_human",
        "reply_list": {"replies": [
            {"reply_id": "r1", "user_id": "ou_human", "content": {"elements": [
                {"type": "text_run", "text_run": {"text": "Please summarize"}},
            ]}},
            {"reply_id": "r2", "user_id": "ou_human", "content": {"elements": [
                {"type": "person", "person": {"user_id": "ou_bot"}},
            ]}},
        ]},
    }]}})
    comments = await p.list_comments(DOC)
    assert comments[0].mentioned_addresses == ("ou_bot",)


@pytest.mark.asyncio
async def test_a_reply_carries_its_own_mentions():
    """The follow-up gate reads each reply's mention set. A reply built without one
    can never continue a thread on this platform, whatever the comment-level set
    says -- and the re-mention every notice asks for is exactly such a reply."""
    p, _ = _provider({"drive +list-comments": {"items": [{
        "comment_id": "c1", "user_id": "ou_human",
        "reply_list": {"replies": [
            {"reply_id": "r1", "user_id": "ou_human", "content": {"elements": [
                {"type": "text_run", "text_run": {"text": "Please summarize"}},
            ]}},
            {"reply_id": "r2", "user_id": "ou_bot", "content": {"elements": [
                {"type": "text_run", "text_run": {"text": "Done."}},
            ]}},
            {"reply_id": "r3", "user_id": "ou_human", "content": {"elements": [
                {"type": "person", "person": {"user_id": "ou_bot"}},
                {"type": "text_run", "text_run": {"text": " shorter please"}},
            ]}},
        ]},
    }]}})
    comments = await p.list_comments(DOC)
    replies = comments[0].replies
    assert replies[0].mentioned_addresses == ()
    assert replies[1].mentioned_addresses == ()
    assert replies[2].mentioned_addresses == ("ou_bot",)


@pytest.mark.asyncio
async def test_a_reply_an_agent_wrote_carries_no_mentions():
    """Same filter as the comment-level set: a mention an agent typed is not a
    signal, at either level of the thread."""
    p = FeishuDocsProvider(profile="p", self_open_id="ou_bot",
                           agent_roster=("ou_agentB",))
    p._cli = _StubCli({"drive +list-comments": {"items": [{
        "comment_id": "c1", "user_id": "ou_human",
        "reply_list": {"replies": [
            {"reply_id": "r1", "user_id": "ou_agentB", "content": {"elements": [
                {"type": "person", "person": {"user_id": "ou_bot"}},
            ]}},
            {"reply_id": "r2", "user_id": "ou_bot", "content": {"elements": [
                {"type": "person", "person": {"user_id": "ou_bot"}},
            ]}},
        ]},
    }]}})
    comments = await p.list_comments(DOC)
    assert [r.mentioned_addresses for r in comments[0].replies] == [(), ()]


@pytest.mark.asyncio
async def test_the_preset_open_id_wins_when_whoami_carries_none():
    """sa_address anchors on the identity's address; degraded to the display name it
    matches no mention ever."""
    p, _ = _provider({"whoami": {"name": "co-scribe"}})
    ident = await p.self_identity()
    assert ident.address == "ou_bot"


@pytest.mark.asyncio
async def test_a_bot_created_documents_url_is_asked_of_the_platform():
    p, _ = _provider({"drive metas": {"metas": [{
        "title": "T", "url": "https://x.feishu.cn/docx/DocToken123456",
    }]}})
    assert await p.canonical_url(DOC) == "https://x.feishu.cn/docx/DocToken123456"
    # Cached: the panel persists it, and the provider answers from memory after.
    assert p.doc_url(DOC) == "https://x.feishu.cn/docx/DocToken123456"


@pytest.mark.asyncio
async def test_a_wiki_hosted_url_probe_retries_once_as_wiki():
    """The wiki flavor is process memory; after a restart the metas query goes out as
    docx and the platform answers the mismatch with a failed_list, not an error."""
    class _WikiCli(_StubCli):
        async def json(self, args, *, timeout=None):
            self.calls.append(list(args))
            if args[:2] == ["drive", "metas"]:
                body = json.loads(args[args.index("--data") + 1])
                if body["request_docs"][0]["doc_type"] == "wiki":
                    return {"metas": [{"title": "我的文档",
                                       "url": "https://x.feishu.cn/docx/UnderlyingTok"}]}
                return {"failed_list": [{"code": 970005}]}
            return {}

    p = FeishuDocsProvider(profile="p", self_open_id="ou_bot")
    p._cli = _WikiCli()
    assert await p.canonical_url("WikiTok123456") == "https://x.feishu.cn/docx/UnderlyingTok"
    # The flavor is learned: drive verbs go out as wiki from here on.
    assert p._drive_type("WikiTok123456") == "wiki"


# ------------------------------------------------------------ the agent roster (§16.14)

def test_a_rostered_open_id_is_recognised_as_another_agent():
    """The Feishu payload carries no identity type, so a bot cannot be told from a
    person by inspection; the deployer's roster supplies that fact."""
    p = FeishuDocsProvider(profile="p", self_open_id="ou_bot",
                           agent_roster=("ou_agentB", "ou_agentC"))
    assert p._is_other_agent("ou_agentB") is True
    assert p._is_other_agent("ou_human") is False
    assert p._is_other_agent("") is False


@pytest.mark.asyncio
async def test_a_mention_an_agent_wrote_is_not_a_trigger_signal():
    """Counting a mention an agent posted would let an agent summon an agent -- the
    recruitment the loop prohibition forbids. Only a person's mention surfaces."""
    p = FeishuDocsProvider(profile="p", self_open_id="ou_bot",
                           agent_roster=("ou_agentB",))
    p._cli = _StubCli({"drive +list-comments": {"items": [{
        "comment_id": "c1", "user_id": "ou_human",
        "reply_list": {"replies": [
            # A human reply, mentioning the bot: this is a real summons.
            {"reply_id": "r1", "user_id": "ou_human", "content": {"elements": [
                {"type": "person", "person": {"user_id": "ou_bot"}},
            ]}},
            # Another agent's reply, also mentioning the bot: must NOT count.
            {"reply_id": "r2", "user_id": "ou_agentB", "content": {"elements": [
                {"type": "person", "person": {"user_id": "ou_bot"}},
            ]}},
        ]},
    }]}})
    comments = await p.list_comments(DOC)
    # ou_bot appears once (from the human), not twice; the agent's mention dropped.
    assert comments[0].mentioned_addresses == ("ou_bot",)


@pytest.mark.asyncio
async def test_a_mention_only_an_agent_wrote_surfaces_nothing():
    p = FeishuDocsProvider(profile="p", self_open_id="ou_bot",
                           agent_roster=("ou_agentB",))
    p._cli = _StubCli({"drive +list-comments": {"items": [{
        "comment_id": "c1", "user_id": "ou_human",
        "reply_list": {"replies": [
            {"reply_id": "r1", "user_id": "ou_agentB", "content": {"elements": [
                {"type": "person", "person": {"user_id": "ou_bot"}},
            ]}},
        ]},
    }]}})
    comments = await p.list_comments(DOC)
    assert comments[0].mentioned_addresses == ()


# ------------------------------------------------------ presentation (slides)

_SLIDE_XML = (
    '<slide id="p1">\n  <style/>\n  <data>\n'
    '    <shape width="800" height="100" type="text" id="sTitle">'
    '<content textType="title"><p>标题形状</p></content></shape>\n'
    '    <shape width="800" height="200" type="text" id="sBody">'
    '<content fontSize="16"><p>正文甲行一</p><p>正文甲行二</p></content></shape>\n'
    '  </data>\n  <note id="sNote"><content><p>讲稿</p></content></note>\n</slide>'
)

_DECK_REPLIES = {
    "slides +xml-get": {"slide": {"content": _SLIDE_XML},
                        "xml_presentation": {"content":
                            '<presentation xmlns="https://www.larkoffice.com/sml/2.0">'
                            + _SLIDE_XML + "</presentation>"}},
    "slides +replace-slide": {},
}


@pytest.mark.asyncio
async def test_a_slides_link_teaches_the_format():
    p, _ = _provider()
    ref = p.parse_doc_ref("https://x.feishu.cn/slides/DeckTok12345")
    assert await p.doc_kind(ref) == "presentation"
    assert p._drive_type(ref) == "slides"


@pytest.mark.asyncio
async def test_a_deck_flattens_one_run_per_shape_with_page_shape_addresses():
    p, _ = _provider(dict(_DECK_REPLIES))
    ref = p.parse_doc_ref("https://x.feishu.cn/slides/DeckTok12345")
    snap = await p.read(ref)
    by = {s.address: snap.text[s.char_start:s.char_end] for s in snap.segments}
    assert by["p1/sTitle"] == "标题形状"
    assert by["p1/sBody"] == "正文甲行一\n正文甲行二"
    assert by["p1/sNote"] == "讲稿"  # notes flatten too, behind the divider


@pytest.mark.asyncio
async def test_a_shape_region_write_swaps_text_and_keeps_the_element():
    """The shape's full XML is sent with only its text nodes swapped: styling and
    geometry survive, and the receipt carries the shape's before-text."""
    p = FeishuDocsProvider(profile="p", self_open_id="ou_bot")
    p._cli = _StubCli(dict(_DECK_REPLIES))
    sink = _RegionSink(); p.receipt_sink = sink
    ref = p.parse_doc_ref("https://x.feishu.cn/slides/DeckTok12345")
    res = await p.write_regions(ref, [("p1/sTitle", [["新标题"]])])
    assert res.status == "applied"
    sent = next(c for c in p._cli.calls if c[:2] == ["slides", "+replace-slide"])
    parts = json.loads(sent[sent.index("--parts") + 1])
    assert parts[0]["target_id"] == "sTitle"
    assert "新标题" in parts[0]["shape"] and 'textType="title"' in parts[0]["shape"]
    entry = sink.begun[0]["edits"][0]
    assert entry["region"] == "p1/sTitle" and entry["old_grid"] == [["标题形状"]]


@pytest.mark.asyncio
async def test_cross_slide_regions_are_refused_as_unatomic():
    p, _ = _provider(dict(_DECK_REPLIES))
    ref = p.parse_doc_ref("https://x.feishu.cn/slides/DeckTok12345")
    res = await p.write_regions(ref, [("p1/sTitle", [["x"]]), ("p2/sOther", [["y"]])])
    assert res.status == "refused" and "同一页" in res.detail


@pytest.mark.asyncio
async def test_a_deck_text_replacement_refuses_with_directions():
    """Without this the docx fallback would receive a slides token and fail with the
    platform's document-flavored error -- the wrong repair path."""
    p, stub = _provider(dict(_DECK_REPLIES))
    ref = p.parse_doc_ref("https://x.feishu.cn/slides/DeckTok12345")
    res = await p.edit_batch(ref, [("标题形状", "新")], required_revision_id="")
    assert res.status == "refused" and "区域" in res.detail
    assert not any(c[:2] == ["docs", "+update"] for c in stub.calls)


@pytest.mark.asyncio
async def test_a_vanished_shape_refuses_the_revert_read():
    p, _ = _provider(dict(_DECK_REPLIES))
    ref = p.parse_doc_ref("https://x.feishu.cn/slides/DeckTok12345")
    with pytest.raises(ProviderError) as err:
        await p.read_regions(ref, ["p1/sGone"])
    assert "不在幻灯片" in str(err.value)


# --------------------------------------------------------- markdown drive files

@pytest.mark.asyncio
async def test_a_markdown_files_drive_verbs_take_type_file():
    """Left unmapped the comment verbs went out as docx, hit "not exist", and burned
    the wiki retry for nothing (measured on the markdown live run)."""
    p, stub = _provider({"drive +list-comments": {"items": []}})
    p.note_kind("MdTok1234567", "markdown")
    assert p._drive_type("MdTok1234567") == "file"
    await p.list_comments("MdTok1234567")
    sent = next(c for c in stub.calls if c[:2] == ["drive", "+list-comments"])
    assert sent[sent.index("--type") + 1] == "file"


@pytest.mark.asyncio
async def test_a_file_link_is_read_as_markdown():
    """ASSUMPTION pinned: of Drive's plain files co-scribe serves only markdown; a
    pasted file link is read as one and a non-md file fails honestly on the fetch."""
    p, _ = _provider()
    ref = p.parse_doc_ref("https://x.feishu.cn/file/MdTok1234567")
    assert ref == "MdTok1234567"
    assert await p.doc_kind(ref) == "markdown"


# ------------------------------------------ review round: slides swap integrity

_COMPLEX_SLIDE = (
    '<slide id="p1"><data>'
    '<shape type="text" id="sTwo">'
    '<content textType="title"><p>头</p></content>'
    '<content><p>尾</p></content></shape>'
    '</data></slide>'
)


@pytest.mark.asyncio
async def test_a_shape_with_several_content_elements_refuses_the_swap():
    """The swap writes into the first content's direct <p> children; a shape holding
    text anywhere else would get its new text appended while the old stayed --
    visible duplication and an inverse that no longer anchors. Refused instead."""
    p = FeishuDocsProvider(profile="p", self_open_id="ou_bot")
    p._cli = _StubCli({"slides +xml-get": {"slide": {"content": _COMPLEX_SLIDE}},
                       "slides +replace-slide": {}})
    ref = p.parse_doc_ref("https://x.feishu.cn/slides/DeckTok99999")
    with pytest.raises(ProviderError) as err:
        await p.write_regions(ref, [("p1/sTwo", [["新文本"]])])
    assert "较复杂" in str(err.value)
    assert not any(c[:2] == ["slides", "+replace-slide"] for c in p._cli.calls)


@pytest.mark.asyncio
async def test_grouped_shapes_flatten_each_leaf_exactly_once():
    """A group's text lives in its child shapes; emitting the parent too duplicated
    every grouped text in the flat, and quotes on it failed the uniqueness anchor."""
    xml = ('<slide id="p1"><data>'
           '<shape type="group" id="g1">'
           '<shape type="text" id="child1"><content><p>组内文字</p></content></shape>'
           '</shape>'
           '</data></slide>')
    p = FeishuDocsProvider(profile="p", self_open_id="ou_bot")
    p._cli = _StubCli({"slides +xml-get": {
        "slide": {"content": xml},
        "xml_presentation": {"content": "<presentation>" + xml + "</presentation>"}}})
    ref = p.parse_doc_ref("https://x.feishu.cn/slides/DeckTok88888")
    snap = await p.read(ref)
    assert snap.text.count("组内文字") == 1
    assert [g.address for g in snap.segments] == ["p1/child1"]


# --------------------------------- review gap: multi-paragraph slides revert loop

class _StatefulDeckCli(_StubCli):
    """A deck whose replace-slide actually lands, so the read after a write shows
    the write -- the shape the real roundtrip has, which the static stubs cannot
    exercise. Review finding: no test drove a multi-paragraph slides receipt
    through execute_revert; the revert suite's grids are all sheet-shaped."""

    def __init__(self, slide_xml: str):
        super().__init__()
        self.slide_xml = slide_xml

    async def json(self, args, *, timeout=None):
        self.calls.append(list(args))
        key = " ".join(args[:2])
        if key == "slides +xml-get":
            return {"slide": {"content": self.slide_xml},
                    "xml_presentation": {"content":
                        "<presentation>" + self.slide_xml + "</presentation>"}}
        if key == "slides +replace-slide":
            import re as _re
            for part in json.loads(args[args.index("--parts") + 1]):
                oid = part["target_id"]
                self.slide_xml = _re.sub(
                    rf'<shape[^>]*id="{oid}".*?</shape>', part["shape"],
                    self.slide_xml, flags=_re.S)
            return {}
        return {}


@pytest.mark.asyncio
async def test_a_multi_paragraph_slides_receipt_survives_the_full_revert_loop(tmp_path):
    """write -> receipt with the two-line before-image -> execute_revert -> both
    paragraphs restored, receipt chain linked both ways."""
    from jiuwenswarm.agents.harness.common.tools.clouddoc.receipts import ReceiptStore
    from jiuwenswarm.agents.harness.common.tools.clouddoc.revert import execute_revert

    xml = ('<slide id="p1"><data>'
           '<shape type="text" id="sMulti">'
           '<content fontSize="16"><p>原一</p><p>原二</p></content></shape>'
           '</data></slide>')
    p = FeishuDocsProvider(profile="p", self_open_id="ou_bot")
    p._cli = _StatefulDeckCli(xml)
    store = ReceiptStore(tmp_path / "receipts.json")
    p.receipt_sink = store
    ref = p.parse_doc_ref("https://x.feishu.cn/slides/DeckTok77777")

    res = await p.write_regions(ref, [("p1/sMulti", [["新一\n新二"]])])
    assert res.status == "applied"
    assert await p.read_regions(ref, ["p1/sMulti"]) == ["新一\n新二"]

    rid = store.list_for(ref)[0]["receipt_id"]
    r = store.get(rid)
    assert r["status"] == "applied", "回读一致，不得降级"
    assert r["edits"][0]["old_grid"] == [["原一\n原二"]]

    out = await execute_revert(p, store, rid)
    assert out.ok, out.detail
    assert await p.read_regions(ref, ["p1/sMulti"]) == ["原一\n原二"]
    assert "<p>原一</p>" in p._cli.slide_xml and "<p>原二</p>" in p._cli.slide_xml
    assert store.get(rid)["status"] == "reverted"
    assert store.get(rid)["reverted_by"], "回执链必须双向"
