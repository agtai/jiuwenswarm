# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.
"""Per-work buffers for the existing facade history and formatting operations."""
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from jiuwenswarm.common.mode_matrix import is_team_mode
from jiuwenswarm.common.schema.agent import AgentRequest
from jiuwenswarm.server.runtime.a2ui.integration import TeamA2UIBlockBuffer
from jiuwenswarm.server.runtime.agent_adapter.user_turn import UserTurn

SOURCE_FIELDS = (
    "source_binding_id", "source_origin_request_id", "source_session_id", "source_request_id",
    "source_task_id", "source_run_kind", "source_goal_id", "source_goal_revision",
)


@dataclass
class StreamHistoryState:
    request: AgentRequest
    work: Any = None
    source: dict = field(default_factory=dict)
    user_turn: UserTurn | None = None
    has_output: bool = False
    has_final: bool = False
    final_answer_content: str = ""
    final_answer_chunks: list[str] = field(default_factory=list)
    durable_pending_final_chunks: list[str] = field(default_factory=list)
    durable_pending_final_started_at: float | None = None
    durable_pending_reasoning_chunks: list[str] = field(default_factory=list)
    durable_final_content: str = ""
    saw_goal_stream_output: bool = False
    suppress_a2ui_stream: bool = False
    a2ui_pending_render_sent: bool = False
    a2ui_stream_probe: str = ""
    team_a2ui_blocks: TeamA2UIBlockBuffer = field(default_factory=TeamA2UIBlockBuffer)
    team_a2ui_tasks: dict = field(default_factory=dict)
    team_a2ui_pending_finals: dict = field(default_factory=dict)
    repair_call: Any = None
    retry_without_a2ui_call: Any = None

    @property
    def records_history(self):
        return self.work is None or self.work.policy.records_generated_history

    @property
    def is_team_mode(self):
        return self.request.params.get("team", False) or is_team_mode(self.request.params.get("mode", ""))

    def source_payload(self, payload):
        return {**payload, **deepcopy(self.source)}

    def configure_turn(self, *, language, turn=None):
        """Snapshot prompt context without repeating inbound workspace setup."""
        if turn is not None:
            self.user_turn = deepcopy(turn)
            return
        params = self.request.params
        query = params.get("query")
        if query is None or query == "":
            query = params.get("content", "")
        if not self.is_team_mode and isinstance(query, str):
            from jiuwenswarm.server.runtime.debug_trace.directives import strip_debug_directive

            query, _ = strip_debug_directive(query)
        trusted_dirs = params.get("trusted_dirs")
        skills = params.get("skills")
        self.user_turn = UserTurn(
            text=query,
            channel=self.request.channel_id,
            language=language,
            files=deepcopy(params.get("files", {}) or {}),
            trusted_dirs=[item.strip() for item in trusted_dirs if isinstance(item, str) and item.strip()]
                if isinstance(trusted_dirs, list) else [],
            skills=([item.strip() for item in skills if isinstance(item, str) and item.strip()] or None)
                if isinstance(skills, list) else None,
            metadata=deepcopy(self.request.metadata),
        )
