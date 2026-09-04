"""apply_for_comment (PR2c, D1): the bounded direct-apply primitive.

Every rail is fail-closed (IC-2), the pre-write checkpoint reads the registry
live (IC-3), highlight is mandatory, and the receipt reply names revertability
(D1d). Three-shot repetition on the authority behaviors per §13.
"""

from __future__ import annotations

import pytest

from jiuwenswarm.agents.harness.common.tools.clouddoc.clouddoc_tools import CloudDocToolkit
from jiuwenswarm.agents.harness.common.tools.clouddoc.provider import (
    DocComment,
    DocSnapshot,
    EditResult,
    ProviderError,
)
from jiuwenswarm.gateway.clouddoc.watch_registry import WatchRegistry

DOC = "doc-A-000000000000"
CID = "c1"


class _RecordingSink:
    """The smallest thing that satisfies IC-2: it records, and it can be inspected."""

    def __init__(self) -> None:
        self.begun: list[tuple] = []

    def begin(self, doc_id, edits, *, highlight, source="", executor=""):
        self.begun.append((doc_id, edits, highlight, source, executor))
        return f"r{len(self.begun)}"

    def commit(self, receipt_id, *, revision_after, highlighted=None):
        pass

    def abort(self, receipt_id, *, reason):
        pass


class _Prov:
    text_domain = "plain"

    def __init__(self, body="总结：这一句需要被改写。收尾。", content="改这句"):
        self.body = body
        self.content = content
        self.replies = []
        self.edits = []
        self.highlights = []
        # **A sink, because IC-2 refuses the write without one.** This was ``None``,
        # and every test in this file passed with it -- so the suite was certifying that
        # an unattended direct apply works with no audit record, which is the opposite
        # of the rule. A gap left out of the code gets written into the tests as a
        # contract, and then the tests are the reason nobody notices.
        self.receipt_sink = _RecordingSink()
        self.receipt_meta = None
        self.batch_result = EditResult("applied", new_revision_id="rev2")

    async def read(self, doc_ref):
        return DocSnapshot(doc_id=doc_ref, kind="document", revision_id="rev1", text=self.body)

    async def list_comments(self, doc_ref, *, include_resolved=False):
        return [DocComment(
            comment_id=CID, author_is_self=False, author_display_name="张三",
            created_time="2026-08-19T00:00:00.000Z", content=self.content,
            quoted_text="这一句需要被改写。", resolved=False,
            mentioned_addresses=(), replies=(), assignee_address=None,
            author_is_service_account=False,
        )]

    async def edit_batch(self, doc_ref, pairs, *, required_revision_id=None,
                         window=None, highlight=False):
        # ``window`` joined the contract with D22/D23: the rail-approved window rides
        # to the provider so both layers judge uniqueness by one rule. Recorded so a
        # test can assert it arrives -- a fake that silently swallows a contract
        # argument is how the last drift went unseen.
        self.edits.append((doc_ref, list(pairs), required_revision_id))
        self.windows = getattr(self, "windows", [])
        self.windows.append(window)
        self.highlights.append(highlight)
        self.meta_at_submit = dict(self.receipt_meta or {})
        return self.batch_result

    async def reply_comment(self, doc_ref, comment_id, content):
        self.replies.append((doc_ref, comment_id, content))
        return "r1"


def _kit(prov, *, doc=DOC, cid=CID, registry_path=None):
    return CloudDocToolkit(
        prov,
        turn_doc_id=lambda: doc,
        turn_comment_id=lambda: cid,
    ), prov


def _grant(tmp_path):
    reg = WatchRegistry(tmp_path / "w.json")
    reg.issue(DOC, "apply_scoped")
    return reg


@pytest.fixture(autouse=True)
def _registry_at_tmp(tmp_path, monkeypatch):
    """Point the cross-process registry at the test dir for every case."""
    import jiuwenswarm.gateway.clouddoc.watch_registry as wr

    monkeypatch.setattr(wr, "get_watch_registry_path", lambda: tmp_path / "w.json")
    yield


GOOD = [{"old_string": "这一句需要被改写。", "new_string": "这一句已经改好。"}]


@pytest.mark.asyncio
async def test_chat_path_refuses_three_ways(tmp_path):
    _grant(tmp_path)
    for _ in range(3):
        kit, prov = _kit(_Prov(), doc=None, cid=None)
        r = await kit.apply_for_comment(edits=GOOD)
        assert not r["ok"] and "batch_edit" in r["detail"]
        assert prov.edits == [], "聊天路径必须拒绝(单表面单写路径)"


@pytest.mark.asyncio
async def test_applies_with_mandatory_highlight_and_receipt_reply(tmp_path):
    _grant(tmp_path)
    kit, prov = _kit(_Prov())
    r = await kit.apply_for_comment(edits=GOOD)
    assert r["ok"], r
    assert prov.highlights == [True], "高亮是强制的:可见性是验收的基础"
    assert prov.edits[0][2] == "rev1", "revision pin 必须携带"
    assert any("版本历史" in c for _, _, c in prov.replies), "回执文案要指向平台版本历史(D1d)"
    assert prov.meta_at_submit.get("source") == "apply_for_comment"
    assert prov.meta_at_submit["for_comment_ids_by_old"]["这一句需要被改写。"] == [CID]


@pytest.mark.asyncio
async def test_the_reply_says_highlighted_only_when_the_platform_highlighted(tmp_path):
    """The reply told the reader the change was marked in yellow whatever the platform
    had done, so on a surface with no highlighting primitive -- Feishu, and every format
    past a plain document -- the person was sent looking for a marker that was not
    there.

    Ring ⑥ asks that the reader can see what changed. Where a colour is unavailable the
    reply carries the changes themselves, which answers the same question honestly."""
    _grant(tmp_path)
    prov = _Prov()
    prov.batch_result = EditResult("applied", new_revision_id="rev2", highlighted=True)
    kit, prov = _kit(prov)
    r = await kit.apply_for_comment(edits=GOOD)
    assert r["highlighted"] is True
    assert any("高亮" in c for _, _, c in prov.replies)


@pytest.mark.asyncio
async def test_a_platform_that_cannot_highlight_still_applies_and_lists_the_changes(
    tmp_path,
):
    """The write is not refused for want of a colour. Refusing was the recorded stance
    and it made apply_scoped unusable on Feishu entirely."""
    _grant(tmp_path)
    prov = _Prov()
    prov.batch_result = EditResult("applied", new_revision_id="rev2", highlighted=False)
    kit, prov = _kit(prov)
    r = await kit.apply_for_comment(edits=GOOD)
    assert r["ok"] and r["highlighted"] is False
    reply = "\n".join(c for _, _, c in prov.replies)
    assert "不支持高亮" in reply, "必须说明为什么没有高亮"
    assert "这一句需要被改写。" in reply, "改动本身要列出来，否则读者无从看见改了什么"


def _has_cjk(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in text)


@pytest.mark.asyncio
async def test_receipt_reply_follows_the_commenter_language(tmp_path):
    """The receipt is the one reply the reader sees on an apply turn, and it was a
    Chinese literal: an English comment got a Chinese receipt on every direct edit.
    Both branches (highlighted, listed) and the revert hint follow the comment."""
    _grant(tmp_path)
    for highlighted in (True, False):
        prov = _Prov(content="fix this")
        prov.batch_result = EditResult("applied", new_revision_id="rev2", highlighted=highlighted)
        kit, prov = _kit(prov)
        r = await kit.apply_for_comment(edits=GOOD)
        assert r["ok"], r
        reply = "\n".join(c for _, _, c in prov.replies)
        assert "version history" in reply, "the undo hint must survive translation (D1d)"
        assert ("highlighted" in reply) is highlighted
        # The edit text itself is quoted in the listed branch and is allowed to be
        # Chinese; the wording around it must not be.
        wording = reply.replace("这一句需要被改写。", "").replace("这一句已经改好。", "")
        assert not _has_cjk(wording), wording

    prov = _Prov(content="改这句")
    prov.batch_result = EditResult("applied", new_revision_id="rev2", highlighted=True)
    kit, prov = _kit(prov)
    await kit.apply_for_comment(edits=GOOD)
    assert any("高亮" in c and "版本历史" in c for _, _, c in prov.replies)


@pytest.mark.asyncio
async def test_revoked_watch_intercepts_write_three_ways(tmp_path):
    reg = _grant(tmp_path)
    reg.revoke(DOC)
    for _ in range(3):
        kit, prov = _kit(_Prov())
        r = await kit.apply_for_comment(edits=GOOD)
        assert not r["ok"] and "撤销或挂起" in r["detail"]
        assert prov.edits == [], "撤销后的在途写入必须被查询点拦截(IC-3)"


@pytest.mark.asyncio
async def test_a_tier_downgrade_intercepts_the_in_flight_write(tmp_path):
    """The turn started under apply_scoped; the owner changed the mandate to
    reply_only while it ran. The checkpoint holds the registry to the turn's tier,
    so the write is intercepted rather than draining to completion."""
    reg = _grant(tmp_path)
    reg.issue(DOC, "reply_only")
    kit = CloudDocToolkit(
        _Prov(), turn_doc_id=lambda: DOC, turn_comment_id=lambda: CID,
        turn_mode=lambda: "apply_scoped",
    )
    r = await kit.apply_for_comment(edits=GOOD)
    assert not r["ok"] and "撤销或挂起" in r["detail"]
    assert kit._provider.edits == [], "降档后的在途写入必须被查询点拦截"
    # At the tier the turn started with, the same write goes through.
    reg.issue(DOC, "apply_scoped")
    kit2 = CloudDocToolkit(
        _Prov(), turn_doc_id=lambda: DOC, turn_comment_id=lambda: CID,
        turn_mode=lambda: "apply_scoped",
    )
    r2 = await kit2.apply_for_comment(edits=GOOD)
    assert r2["ok"], r2


@pytest.mark.asyncio
async def test_an_expired_watch_intercepts_the_write(tmp_path):
    reg = WatchRegistry(tmp_path / "w.json")
    reg.issue(DOC, "apply_scoped", expires_at=1.0)  # long past
    kit, prov = _kit(_Prov())
    r = await kit.apply_for_comment(edits=GOOD)
    assert not r["ok"] and prov.edits == [], "到期视同不存续"


@pytest.mark.asyncio
async def test_suspended_watch_intercepts_write(tmp_path):
    reg = _grant(tmp_path)
    reg.suspend(DOC)
    kit, prov = _kit(_Prov())
    r = await kit.apply_for_comment(edits=GOOD)
    assert not r["ok"] and prov.edits == []


@pytest.mark.asyncio
async def test_out_of_range_edit_refused_whole_batch(tmp_path):
    _grant(tmp_path)
    # The rail window is quote ± adjacent_budget (200 chars): the far edit must sit
    # beyond it, so pad 300 chars of body between the quote and the target.
    body = "总结：这一句需要被改写。" + "垫" * 300 + "远处的收尾句。"
    kit, prov = _kit(_Prov(body))
    r = await kit.apply_for_comment(edits=[
        {"old_string": "这一句需要被改写。", "new_string": "改好。"},
        {"old_string": "远处的收尾句。", "new_string": "被越界修改的收尾。"},
    ])
    assert not r["ok"] and "整批未做任何修改" in r["detail"]
    assert prov.edits == [], "越界一处,整批拒绝"


@pytest.mark.asyncio
async def test_unanchored_comment_refuses(tmp_path):
    _grant(tmp_path)

    class _NoQuote(_Prov):
        async def list_comments(self, doc_ref, *, include_resolved=False):
            base = await super().list_comments(doc_ref, include_resolved=include_resolved)
            return [DocComment(**{**base[0].__dict__, "quoted_text": ""})]

    kit, prov = _kit(_NoQuote())
    r = await kit.apply_for_comment(edits=GOOD)
    assert not r["ok"] and "锚点已失效" in r["detail"]


@pytest.mark.asyncio
async def test_conflict_is_reported_not_applied(tmp_path):
    _grant(tmp_path)
    prov = _Prov()
    prov.batch_result = EditResult("conflict", detail="revision moved")
    kit, prov = _kit(prov)
    r = await kit.apply_for_comment(edits=GOOD)
    assert not r["ok"] and "冲突" in r["detail"]


@pytest.mark.asyncio
async def test_empty_or_missing_edits_refused(tmp_path):
    _grant(tmp_path)
    kit, prov = _kit(_Prov())
    assert not (await kit.apply_for_comment(edits=[]))["ok"]
    assert not (await kit.apply_for_comment(edits=[{"old_string": "", "new_string": "x"}]))["ok"]


def test_apply_for_comment_sits_in_apply_scoped_family_only():
    from jiuwenswarm.agents.harness.common.tools.clouddoc.clouddoc_tools import (
        unattended_allowlist_for,
    )

    assert "clouddoc_apply_for_comment" in unattended_allowlist_for("apply_scoped")
    assert "clouddoc_apply_for_comment" not in unattended_allowlist_for("reply_only"), (
        "建议权回合不得持有直改原语(IC-1)"
    )


@pytest.mark.asyncio
async def test_no_receipt_sink_refuses_the_write(tmp_path):
    """IC-2, fail-closed. Two comments in the tree already claimed this check existed;
    it did not, so a sink that failed to construct at wiring time left the unattended
    path writing to a shared document with nothing recording that it had.

    Fail-closed only here. An attended write is asked about first, so a lost record can
    be recovered by asking the person; on this path there is nobody to ask."""
    _grant(tmp_path)
    prov = _Prov()
    prov.receipt_sink = None
    kit, prov = _kit(prov)
    r = await kit.apply_for_comment(edits=GOOD)
    assert not r["ok"]
    assert "回执" in r["detail"]
    assert prov.edits == [], "没有回执凭据时，一个字也不能写"


# ------------------------------------------------------- the region form (shape anchor)


REGION = "g3f83fc648f2_5_0/g3f83fc648f2_5_2"


class _DeckProv(_Prov):
    """A deck: the bound comment quotes nothing and anchors a shape instead."""

    def __init__(self, anchor=(REGION,)):
        super().__init__(body="todo")
        self.anchor = tuple(anchor)
        self.region_writes: list[tuple] = []

    async def read(self, doc_ref):
        return DocSnapshot(doc_id=doc_ref, kind="presentation", revision_id="rev1", text=self.body)

    async def list_comments(self, doc_ref, *, include_resolved=False):
        return [DocComment(
            comment_id=CID, author_is_self=False, author_display_name="张三",
            created_time="2026-08-25T00:00:00.000Z", content="这个添加一个介绍",
            quoted_text="", resolved=False,
            mentioned_addresses=(), replies=(), assignee_address=None,
            author_is_service_account=False, anchor_regions=self.anchor,
        )]

    async def write_regions(self, doc_ref, pairs, *, required_revision_id=""):
        self.region_writes.append((doc_ref, list(pairs), required_revision_id))
        self.meta_at_submit = dict(self.receipt_meta or {})
        return EditResult("applied", new_revision_id="rev2")


@pytest.mark.asyncio
async def test_a_shape_anchored_comment_authorizes_a_region_write(tmp_path):
    """Measured live (2026-08-25): a comment left on a text box as a whole carries a
    decodable shape anchor and no quote. The clicked shape is the person's selection,
    so it is the write bound -- the same principle the quote pathway enforces, on a
    different carrier."""
    _grant(tmp_path)
    kit, prov = _kit(_DeckProv())
    out = await kit.apply_for_comment(regions=[{"at": REGION, "values": [["Jiuwen Swarm 简介"]]}])
    assert out["ok"], out.get("detail")
    (doc, pairs, rev), = prov.region_writes
    assert pairs == [(REGION, [["Jiuwen Swarm 简介"]])]
    assert rev == "rev1", "区域直改必须钉住校验时的 revision"
    assert prov.meta_at_submit.get("executor") == f"comment:{CID}"
    assert prov.meta_at_submit.get("for_comment_ids") == [CID]
    assert out["highlighted"] is False
    assert prov.replies and "不支持高亮" in prov.replies[0][2]


@pytest.mark.asyncio
async def test_a_region_outside_the_anchor_refuses_the_whole_batch(tmp_path):
    """The anchor is the authorization; naming any other shape is out of scope, and a
    partial application would be a write nobody bounded."""
    _grant(tmp_path)
    kit, prov = _kit(_DeckProv())
    out = await kit.apply_for_comment(regions=[
        {"at": REGION, "values": [["ok"]]},
        {"at": "p/other", "values": [["溢出"]]},
    ])
    assert not out["ok"]
    assert "p/other" in out["detail"] and REGION in out["detail"]
    assert prov.region_writes == [], "越界时一个区域也不得写"


@pytest.mark.asyncio
async def test_the_region_form_needs_an_anchor(tmp_path):
    """A text-quoted comment authorizes text replacement, nothing wider: the region
    form without a shape anchor would be a write bounded by nobody's selection."""
    _grant(tmp_path)
    kit, prov = _kit(_Prov())  # quoted comment, no anchor
    out = await kit.apply_for_comment(regions=[{"at": REGION, "values": [["x"]]}])
    assert not out["ok"]
    assert "没有锚定任何形状" in out["detail"]


@pytest.mark.asyncio
async def test_the_quote_refusal_points_at_the_region_form(tmp_path):
    """The model recovers inside the turn, so the refusal must name the way that
    works: the live incident replied 'anchor is empty' to a comment whose anchor was
    a perfectly decodable shape address."""
    _grant(tmp_path)
    kit, prov = _kit(_DeckProv())
    out = await kit.apply_for_comment(edits=[{"old_string": "todo", "new_string": "新文"}])
    assert not out["ok"]
    assert "regions" in out["detail"] and REGION in out["detail"]


@pytest.mark.asyncio
async def test_both_forms_at_once_are_refused(tmp_path):
    _grant(tmp_path)
    kit, prov = _kit(_DeckProv())
    out = await kit.apply_for_comment(
        edits=[{"old_string": "todo", "new_string": "x"}],
        regions=[{"at": REGION, "values": [["x"]]}],
    )
    assert not out["ok"] and "只能用其一" in out["detail"]


@pytest.mark.asyncio
async def test_the_predicate_rail_refuses_a_longer_shorten(tmp_path):
    """D19 tier 3a wired into the write path: 「剪短」 answered with a longer text
    refuses the batch before anything is sent."""
    _grant(tmp_path)
    prov = _Prov()

    async def _lc(doc_ref, *, include_resolved=False):
        return [DocComment(
            comment_id=CID, author_is_self=False, author_display_name="张三",
            created_time="2026-08-31T00:00:00.000Z", content="把这句剪短",
            quoted_text="这一句需要被改写。", resolved=False,
            mentioned_addresses=(), replies=(), assignee_address=None,
            author_is_service_account=False,
        )]

    prov.list_comments = _lc
    kit, prov = _kit(prov)
    out = await kit.apply_for_comment(edits=[{
        "old_string": "这一句需要被改写。",
        "new_string": "这一句需要被改写，而且被改得比原来还要长了很多。",
    }])
    assert not out["ok"], "更长的「剪短」必须整批拒绝"
    assert "不短于原文" in out["detail"]
    assert prov.edits == [], "谓词违规时不得发出任何写入"


SA = "co-scribe@x.iam.gserviceaccount.com"


@pytest.mark.asyncio
async def test_the_predicate_rail_reads_the_mentioning_reply_on_a_follow_up(tmp_path):
    """The thread began with 「删掉」 and continued with 「加长一倍」 in a reply that
    mentions the agent. The rail must judge the edit against the reply -- checking
    it against the opening comment refuses the very edit that was asked for."""
    from jiuwenswarm.agents.harness.common.tools.clouddoc.provider import DocReply

    _grant(tmp_path)
    prov = _Prov()

    async def _lc(doc_ref, *, include_resolved=False):
        return [DocComment(
            comment_id=CID, author_is_self=False, author_display_name="张三",
            created_time="2026-08-31T00:00:00.000Z", content="把这句删掉",
            quoted_text="这一句需要被改写。", resolved=False,
            mentioned_addresses=(SA,), assignee_address=None,
            author_is_service_account=False,
            replies=(
                DocReply(reply_id="a1", author_is_self=True, author_display_name="agent",
                         created_time="2026-08-31T00:01:00.000Z", content="已删除。"),
                DocReply(reply_id="r2", author_is_self=False, author_display_name="张三",
                         created_time="2026-08-31T00:02:00.000Z",
                         content="改成加长一倍", mentioned_addresses=(SA,)),
            ),
        )]

    prov.list_comments = _lc
    kit = CloudDocToolkit(
        prov, turn_doc_id=lambda: DOC, turn_comment_id=lambda: CID,
        turn_address=lambda: SA,
    )
    out = await kit.apply_for_comment(edits=[{
        "old_string": "这一句需要被改写。",
        "new_string": "这一句需要被改写，而且现在被加长到了原来的两倍那么长。",
    }])
    assert out["ok"], out
    assert prov.edits, "跟进回合按 @ 我的回复判定，不得按首评论的「删掉」拒绝"


@pytest.mark.asyncio
async def test_the_predicate_rail_keeps_the_comment_when_no_reply_mentions_the_agent(tmp_path):
    """A person's reply that does not mention the agent is thread context, not the
    request; the opening instruction still governs."""
    from jiuwenswarm.agents.harness.common.tools.clouddoc.provider import DocReply

    _grant(tmp_path)
    prov = _Prov()

    async def _lc(doc_ref, *, include_resolved=False):
        return [DocComment(
            comment_id=CID, author_is_self=False, author_display_name="张三",
            created_time="2026-08-31T00:00:00.000Z", content="把这句剪短",
            quoted_text="这一句需要被改写。", resolved=False,
            mentioned_addresses=(SA,), assignee_address=None,
            author_is_service_account=False,
            replies=(
                DocReply(reply_id="a1", author_is_self=True, author_display_name="agent",
                         created_time="2026-08-31T00:01:00.000Z", content="好的。"),
                DocReply(reply_id="r2", author_is_self=False, author_display_name="李四",
                         created_time="2026-08-31T00:02:00.000Z", content="其实加长也行"),
            ),
        )]

    prov.list_comments = _lc
    kit = CloudDocToolkit(
        prov, turn_doc_id=lambda: DOC, turn_comment_id=lambda: CID,
        turn_address=lambda: SA,
    )
    out = await kit.apply_for_comment(edits=[{
        "old_string": "这一句需要被改写。",
        "new_string": "这一句需要被改写，而且被改得比原来还要长了很多。",
    }])
    assert not out["ok"] and "不短于原文" in out["detail"]
    assert prov.edits == []


class _FeishuDeckProv(_DeckProv):
    """The Feishu carrier: the comment quotes real text but carries no anchor field.
    The snapshot's segments are what the quote-derived anchor is recovered from."""

    def __init__(self):
        super().__init__(anchor=())

    async def read(self, doc_ref):
        from jiuwenswarm.agents.harness.common.tools.clouddoc.provider import Segment
        body = "标题形状\nTODO\n别的形状"
        return DocSnapshot(
            doc_id=doc_ref, kind="presentation", revision_id="rev1", text=body,
            segments=(
                Segment(char_start=0, char_end=4, address="p1/sA"),
                Segment(char_start=5, char_end=9, address="p1/sTodo"),
                Segment(char_start=10, char_end=14, address="p1/sB"),
            ),
        )

    async def list_comments(self, doc_ref, *, include_resolved=False):
        cs = await super().list_comments(doc_ref, include_resolved=include_resolved)
        import dataclasses
        return [dataclasses.replace(cs[0], quoted_text="TODO", anchor_regions=())]


@pytest.mark.asyncio
async def test_a_quoted_deck_comment_recovers_its_shape_anchor(tmp_path):
    """Feishu's payload gives the quote and withholds the anchor; the shape is
    recovered by anchoring the quote in the flattened deck (measured live: a user
    comment on a TODO text box carried quote='TODO' and nothing else). Same
    authorization criterion as D18's decoded anchor, different carrier."""
    _grant(tmp_path)
    kit, prov = _kit(_FeishuDeckProv())
    out = await kit.apply_for_comment(
        regions=[{"at": "p1/sTodo", "values": [["Co-scribe 简介"]]}]
    )
    assert out["ok"], out.get("detail")
    (_, pairs, _), = prov.region_writes
    assert pairs == [("p1/sTodo", [["Co-scribe 简介"]])]


@pytest.mark.asyncio
async def test_the_recovered_anchor_still_bounds_the_write(tmp_path):
    """The derivation widens nothing: a region outside the quote's own shape is
    refused exactly as a decoded anchor would refuse it."""
    _grant(tmp_path)
    kit, prov = _kit(_FeishuDeckProv())
    out = await kit.apply_for_comment(
        regions=[{"at": "p1/sB", "values": [["越界"]]}]
    )
    assert not out["ok"]
    assert prov.region_writes == []
