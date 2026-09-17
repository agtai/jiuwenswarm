# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.
"""JiuwenSwarm application binding for the AgentCore project task executor."""

from pathlib import Path
from openjiuwen.core.application.tasks.project_executor import (
    FORMAL_RUNTIME_SUPPORT_POLICY,
    _is_within,
)
from openjiuwen.core.application.tasks.project_executor import (
    DirectProjectCodeExecutorAdapter as _SdkProjectExecutor,
)
from openjiuwen.core.sys_operation.cwd import get_agent_history_root
from jiuwenswarm.common import live_voice_profiling
from jiuwenswarm.common.schema.agent import AgentRequest
from jiuwenswarm.common.schema.live_voice_contract_v2 import ErrorCode
from openjiuwen.core.application.tasks.formal_task_models import FormalTaskViolation
from jiuwenswarm.common.utils import get_agent_workspace_dir
from jiuwenswarm.common.coding_memory_paths import resolve_project_coding_memory_dir
from jiuwenswarm.agents.harness.common.tools.command_tools import (
    forbid_background_project_shell_commands,
)


def _runtime_support_governance(root: Path) -> dict[str, object]:
    """Resolve protected runtime-support ownership for a formal Agent snapshot."""

    agent_workspace = get_agent_workspace_dir().resolve(strict=False)
    application_paths = {
        "coding_memory": Path(
            resolve_project_coding_memory_dir(
                agent_workspace_dir=agent_workspace,
                project_dir=root,
            )
        ).resolve(strict=False),
        "prompt_attachment": (agent_workspace / "prompt_attachment").resolve(
            strict=False
        ),
        ".agent_history": (Path(get_agent_history_root()) / ".agent_history").resolve(
            strict=False
        ),
    }
    if any(_is_within(path, root) for path in application_paths.values()):
        raise FormalTaskViolation(
            "RUNTIME_SUPPORT_PATH_INSIDE_TARGET",
            "formal Agent runtime support must remain outside the selected project",
            ErrorCode.PERMISSION_DENIED,
        )
    return {
        "policy": dict(FORMAL_RUNTIME_SUPPORT_POLICY),
        "application_paths": {
            key: str(value) for key, value in sorted(application_paths.items())
        },
    }


class JiuwenSwarmProjectExecutionApplication:
    telemetry = live_voice_profiling

    @staticmethod
    def create_request(invocation):
        metadata = {
            "enable_memory": False,
            "skip_a2ui": True,
            "background_task": True,
            "project_task_file_tools_only": True,
            "formal_task_id": invocation.task_id,
            "formal_attempt_id": invocation.attempt_id,
        }
        if invocation.adjustment_id is not None:
            metadata["formal_adjustment_id"] = invocation.adjustment_id
        return AgentRequest(
            request_id=invocation.request_id,
            channel_id="formal-task-core",
            session_id=invocation.session_id,
            params={
                "query": invocation.instruction,
                "mode": "code",
                "project_dir": invocation.project_dir,
                "cwd": invocation.project_dir,
                "workspace_dir": str(get_agent_workspace_dir().resolve(strict=False)),
                "trusted_dirs": [invocation.project_dir],
                "supports_user_interaction": False,
                "source": "live_voice.formal_task.d0"
                + (".adjust" if invocation.adjustment_id is not None else ""),
            },
            is_stream=True,
            metadata=metadata,
            enable_memory=False,
        )

    @staticmethod
    def workspace_dir():
        return get_agent_workspace_dir()

    execution_guard = staticmethod(forbid_background_project_shell_commands)
    runtime_support_governance = staticmethod(_runtime_support_governance)


class DirectProjectCodeExecutorAdapter(_SdkProjectExecutor):
    """Supply Host policy; attempt execution and recovery belong to AgentCore."""

    def __init__(self, *args, **kwargs):
        super().__init__(
            *args, application=JiuwenSwarmProjectExecutionApplication(), **kwargs
        )
