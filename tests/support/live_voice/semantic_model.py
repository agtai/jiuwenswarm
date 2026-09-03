# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Controlled model responses for authority regression, NEVER language evidence.

This finite corpus migrates the former parser-dependent Registry safety tests.
Only the configured-model port is doubled; schema, references, Bridge, normal
confirmation, Store and Core remain real. Production must never import this file.
"""

import json
from types import SimpleNamespace


def decision(data, operation=None, arguments=None, target=None, kind=None, reference=None):
    arguments = arguments or {}
    fields = (["dialogue"] if operation is None else
              ["operation", *[f"arguments.{key}" for key in arguments],
               *(["target"] if target is not None else [])])
    return {
        "route": "dialogue" if operation is None else "task",
        "operation": operation, "arguments": arguments, "target": target,
        "target_kind": kind, "message": None,
        "reference_id": None if reference is None else reference["id"],
        "reference_version": None if reference is None else reference["version"],
        "continuation_action": None if reference is None else (
            "confirm" if reference["kind"] == "confirmation" else "answer_clarification"),
        "extractions": [{"field_name": field, "source_start": 0,
                         "source_end": len(data["commit"]["text"])} for field in fields],
    }


class AuthorityCorpusModel:
    """Fixed test responses; unlisted inputs deliberately fail, no fallback."""

    async def invoke(self, *, messages, tools, **_options):
        assert tools == []
        data = json.loads(messages[1].content)
        text = data["commit"]["text"]
        pending = data["context"]["pending"]
        reference = None
        if text.startswith("confirm task request "):
            alias = text.removeprefix("confirm task request ")
            reference = next((p for p in pending if p["source_id"] == alias), None)
            if reference is None:
                output = decision(data)
                output.update(route="clarification", message="该确认已失效，请重新提出操作。")
            else:
                output = decision(data, reference["operation"], reference["arguments"],
                                  reference["target"], reference["target_kind"], reference)
        elif text == "新建一个任务，基于合成依赖起草发布说明。":
            output = decision(data, "task.create", {
                "name": "Synthetic release notes",
                "instruction": "Draft release notes from the supplied synthetic dependencies.",
            })
        elif text == "列出当前任务":
            output = decision(data, "task.list", {"query_kind": "list", "limit": 100})
        elif text == "Set priority urgent for task named Synthetic release notes.":
            output = decision(data, "task.reprioritize", {"priority": "urgent"},
                              "Synthetic release notes", "name")
        elif text == "Cancel the task named Synthetic release notes.":
            output = decision(data, "task.cancel", target="Synthetic release notes", kind="name")
        elif text == "status “Synthetic release notes”":
            output = decision(data, "task.status", {"query_kind": "status"},
                              "Synthetic release notes", "name")
        else:
            # IDs are discovered at runtime from authenticated facts, not preset
            # business targets. This is a test response builder, not a parser.
            matches = [(op, fact["task_id"]) for op in ("status", "pause", "cancel")
                       for fact in data["context"]["tasks"] if text == f"{op} {fact['task_id']}"]
            assert len(matches) == 1, (text, pending)
            op, target = matches[0]
            candidates = [p for p in pending if p["kind"] == "clarification" and p["operation"] == f"task.{op}"]
            assert len(candidates) <= 1, candidates
            reference = candidates[0] if candidates else None
            output = decision(data, f"task.{op}", {"query_kind": "status"} if op == "status" else {},
                              target, "task_id", reference)
        return SimpleNamespace(content=json.dumps(output), tool_calls=[])
