# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Presentation of canonical control facts; never a language/target classifier."""

from collections.abc import Mapping


def task_subject(facts: Mapping[str, object], *, chinese: bool) -> str:
    name = str(facts.get("name") or facts["task_id"])
    return f"“{name}”" if chinese else f'Task "{name}"'


def adjustment_status_text(state: object, *, chinese: bool) -> str:
    if chinese:
        return {
            "pending": "修改要求已提交，尚未确认应用。",
            "applied": "最近一次修改已应用。",
            "rejected": "最近一次修改未能应用。",
            "none": "尚无已提交的修改记录。",
        }.get(state, "目前无法确认修改是否已应用。")
    return {
        "pending": "The adjustment was submitted; application is not yet confirmed.",
        "applied": "The latest adjustment has been applied.",
        "rejected": "The latest adjustment was not applied.",
        "none": "No adjustment has been submitted.",
    }.get(state, "Whether the adjustment was applied is currently unknown.")


def task_status_text(facts: Mapping[str, object], *, chinese: bool) -> str:
    subject = task_subject(facts, chinese=chinese)
    state = facts.get("outcome") if facts.get("state") == "terminal" else facts.get("state")
    if chinese:
        description = {
            "accepted": "已受理，等待执行", "running": "正在执行",
            "blocked": "受阻，等待所需条件", "decision_required": "需要你的决定",
            "completed": "已完成", "cancelled": "已取消", "failed": "执行失败",
            "interrupted": "已中断",
        }.get(state, "的执行状态暂时无法确认")
        text = f"{subject}{description}。"
    else:
        description = {
            "accepted": "is queued", "running": "is running", "blocked": "is blocked",
            "decision_required": "needs your decision", "completed": "is complete",
            "cancelled": "was cancelled", "failed": "failed", "interrupted": "was interrupted",
        }.get(state, "has an unconfirmed execution state")
        text = f"{subject} {description}. "
    return text + adjustment_status_text(facts.get("adjustment_state"), chinese=chinese)
