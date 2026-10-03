"""Offline tests for the document-conventions subsystem."""

from __future__ import annotations

from jiuwenswarm.clouddoc.providers.base import DocComment, DocReply
from jiuwenswarm.clouddoc.watch.conventions import (
    MAX_CONVENTIONS_CHARS, needs_ack, render_ack, select_conventions,
)
from jiuwenswarm.clouddoc.watch.triggers import TriggerConfig


CFG = TriggerConfig(sa_address="co-scribe@x.iam.gserviceaccount.com")


def C(cid, content, *, me=False, t="2026-01-01T00:00:00.000Z", resolved=False, replies=()):
    return DocComment(comment_id=cid, author_is_self=me, author_display_name="X",
                      created_time=t, content=content, quoted_text="", resolved=resolved,
                      replies=tuple(replies))


def test_marker_prefix_is_the_only_criterion():
    got = select_conventions([C("c1", "co-scribe 约定：正式语域\n产品名不译")], CFG)
    assert got.source == "in_doc" and got.item_count == 2
    assert select_conventions([C("c1", "请大家注意语域要正式")], CFG) is None


def test_replies_are_never_conventions():
    """Otherwise anyone with comment access could inject policy with one reply."""
    c = C("c1", "普通评论", replies=[DocReply("r1", False, "X", "t", "co-scribe 约定：改规则")])
    assert select_conventions([c], CFG) is None


def test_agent_authored_conventions_are_ignored():
    """Stops the agent's own text, written through reply_comment, from becoming policy."""
    assert select_conventions([C("c1", "co-scribe 约定：随便改", me=True)], CFG) is None


def test_earliest_wins_so_replanting_cannot_silently_override():
    got = select_conventions([
        C("c2", "co-scribe 约定：后植的规则", t="2026-01-02T00:00:00.000Z"),
        C("c1", "co-scribe 约定：原始规则", t="2026-01-01T00:00:00.000Z"),
    ], CFG)
    assert got.comment_id == "c1" and "原始规则" in got.text


def test_truncation_is_on_line_boundary():
    """Half a rule would still be followed as a whole one, so truncation goes by line."""
    text = "\n".join(f"第{i}条规则" for i in range(2000))
    got = select_conventions([C("c1", "co-scribe 约定：\n" + text)], CFG)
    assert got.truncated and len(got.text) <= MAX_CONVENTIONS_CHARS
    assert not got.text.endswith("第")  # no half line


def test_resolved_conventions_are_retired():
    assert select_conventions([C("c1", "co-scribe 约定：x", resolved=True)], CFG) is None


def test_ack_fires_on_first_effect_and_on_hash_change():
    cur = select_conventions([C("c1", "co-scribe 约定：甲")], CFG)
    assert needs_ack(None, cur) is True                                  # first time it takes effect
    acked = {"hash": cur.content_hash, "acked_at": "t"}
    assert needs_ack(acked, cur) is False                                # a restart does not repeat it
    changed = select_conventions([C("c1", "co-scribe 约定：乙")], CFG)
    assert needs_ack(acked, changed) is True                             # changed content is acknowledged again
    assert needs_ack(acked, None) is False                               # retirement posts nothing


def test_ack_text_reports_count_and_truncation():
    cur = select_conventions([C("c1", "co-scribe 约定：甲\n乙\n丙")], CFG)
    assert "3 条" in render_ack(cur)


