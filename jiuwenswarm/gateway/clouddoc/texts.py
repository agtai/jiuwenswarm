"""Every string the watcher writes into a document, in both languages.

The language policy has three layers, each with a different reader:

* **System text and the agent's own prose** -- follows the language of the
  triggering comment. The reader is the person in the document, and a
  deployment-level switch would have to pick a side in a document where Chinese
  and English collaborators share a thread.
* **Structural labels in a proposal block** -- same rule. The parser does not
  depend on them; it keys off the block marker and the fences.
* **The words ``approve`` and ``keep``** -- **always English**, see turn_prompt
  and render_proposal. These are not prose but **command tokens the reader is
  asked to type back**: one spelling, so a Chinese thread does not leave anyone
  guessing between 同意 and approve. Matching still accepts both word lists, so
  typing 同意 keeps working.
"""

from __future__ import annotations

from jiuwenswarm.gateway.clouddoc.turn_prompt import looks_chinese

from jiuwenswarm.agents.harness.common.tools.clouddoc.wording import (  # noqa: E402
    TOOL_TEXTS as _TOOL_TEXTS,
)

_TEXTS: dict[str, tuple[str, str]] = {
    # The five entries the write tools speak themselves live in the toolkit's
    # wording module (single source); this table composes them back in.
    **_TOOL_TEXTS,
    # key: (Chinese, English)
    "placeholder":        ("⏳ 正在处理…", "⏳ Working on it…"),
    "rail_refused":       ("这条提议未通过范围检查：{detail}",
                           "This proposal did not pass the range check: {detail}"),
    # "Reply in this thread", not "@ me again": an interrupted thread continues on
    # A bare reply no longer continues a thread: participation needs a mention, so
    # that a discussion between other collaborators does not wake the agent. Every
    # text that asks for something back therefore asks to be named.
    "turn_incomplete":    ("这一轮没有完成。在本线程 @ 我一句（如「@我 继续」）即可让我重试。（编号 {ref}）",
                           "This turn didn't complete. @-mention me in this thread "
                           "(e.g. \"@me continue\") and I'll retry. (ref {ref})"),
    "apply_failed_status": ("未能应用（{status}），请重新触发。",
                            "Could not apply ({status}) — please trigger again."),
    "apply_refused":      ("未能应用：{detail}", "Could not apply: {detail}"),
    "kept":               ("已保留原文。", "Kept the original."),
    "no_pending":         ("这条线程没有待批的提议——之前那条已经失效了。"
                           "重新**指派**（或重新 @ 我），我会基于当前正文重新提议。",
                           "There is no pending proposal in this thread -- the earlier "
                           "one is no longer valid. **Assign** it to me again (or @ me again) "
                           "and I'll propose against the current text."),
    # D2②: never-authorized wording -- asserts the authority gap truthfully.
    "watch_unauthorized": ("已记录。我尚未获得处理此文档的授权，暂不能安排这条批注。"
                           "授权由部署主人在 Jiuwen 的「Docs」面板为这篇文档签发值守；"
                           "签发后请在本线程再 @ 我一次。",
                           "Recorded. I have not been authorized to handle this "
                           "document yet, so I cannot schedule this comment. The "
                           "deployment owner grants that by signing a watch for this "
                           "document in Jiuwen's Docs panel; once signed, @ me again "
                           "in this thread."),
    # D3: suspend-specific neutral text -- authority exists, so it must not claim
    # otherwise, and it must not disclose the suspension either (privacy).
    "watch_suspended":    ("已记录，本轮暂不安排处理。",
                           "Recorded; not scheduled this round."),
    # D9 / review M-cluster-1: the third visible wording -- over budget is queued
    # work, and silence here would be indistinguishable from silent dropping.
    "watch_over_budget":  ("已记录并排队：今日的自动处理额度已用完。重新指派（或在本线程重新 @ 我）即视为新任务。",
                           "Recorded and queued: today's automatic-handling budget is "
                           "used up. Re-assigning (or @-ing me again in this thread) counts as a fresh task."),
    "ack_conventions":    ("已读取本文档约定（{count} 条）。",
                           "Conventions noted ({count} item(s))."),
    "ack_truncated":      ("已读取本文档约定（{count} 条），超出 {limit} 字符的部分已按行截断。",
                           "Conventions noted ({count} item(s)); text beyond {limit} characters was truncated by line."),
    # The receipt apply_for_comment posts under the comment it answered (D1d). These
    # used to be Chinese literals in the tool, so an English thread got a Chinese
    # receipt on every direct edit -- the one reply the reader sees on that turn.
    "reverted_notice":    ("本轮针对该批注的修改已按回执回退，正文已恢复原状。如仍需修改，请重新指派（或重新 @ 我）。",
                           "The edit made for this comment has been reverted by receipt; "
                           "the text is back as it was. Re-assign it (or @ me again) if you "
                           "still want it changed."),
}


def msg(key: str, lang_sample: str = "", **kw: object) -> str:
    """Pick a language from ``lang_sample`` -- usually the body of the triggering
    comment -- and format the result.

    Guessing wrong costs nothing but a reply in the other language; no mechanism
    or decision depends on it.
    """
    zh, en = _TEXTS[key]
    return (zh if looks_chinese(lang_sample) else en).format(**kw)
