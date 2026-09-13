# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Voice projection of provenance-bearing Host Agent output."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AgentEvent:
    request_id: str
    interaction_id: str
    turn_id: str
    commit_id: str
    seq: int
    event_type: str
    source_provenance: str
    text: str | None = None
    capability: str | None = None
    error_reason: str | None = None
    tool_result_succeeded: bool | None = None
