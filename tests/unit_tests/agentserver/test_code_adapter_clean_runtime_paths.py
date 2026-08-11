# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from openjiuwen.core.sys_operation.cwd import (
    get_cwd,
    get_project_root,
    get_workspace,
)
from openjiuwen.harness.tools.filesystem import (
    WriteFileTool,
    _append_op_history,
    _resolve_tool_file_path,
)
from openjiuwen.harness.workspace.workspace import Workspace

from jiuwenswarm.common.coding_memory_paths import (
    resolve_project_coding_memory_dir,
    resolve_project_coding_memory_workspace_path,
)
from jiuwenswarm.server.runtime.agent_adapter.interface_code import (
    JiuwenSwarmCodeAdapter,
    _set_workspace_coding_memory_directory,
)
from jiuwenswarm.server.runtime.agent_adapter.interface_deep import (
    JiuWenSwarmDeepAdapter,
)


def _git(project: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(project), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _project(project: Path) -> str:
    project.mkdir()
    _git(project, "init")
    _git(project, "config", "user.name", "Live Voice Test")
    _git(project, "config", "user.email", "live-voice-test@example.invalid")
    (project / "README.md").write_text("baseline\n", encoding="utf-8")
    _git(project, "add", "README.md")
    _git(project, "commit", "-m", "baseline")
    return _git(project, "rev-parse", "HEAD")


class _Session:
    @staticmethod
    def agent_id() -> str:
        return "formal-agent"

    @staticmethod
    def get_session_id() -> str:
        return "formal-session"


@pytest.mark.asyncio
async def test_clean_runtime_support_stays_external_while_project_write_remains_allowed(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    before_head = _project(project)
    application_workspace = tmp_path / "application" / "agent" / "workspace"
    application_workspace.mkdir(parents=True)
    workspace = Workspace(root_path=project)
    _set_workspace_coding_memory_directory(
        workspace,
        project_dir=str(project),
        agent_workspace_dir=str(application_workspace),
        application_owned=True,
    )

    coding_memory = workspace.get_node_path("coding_memory")
    assert coding_memory is not None
    assert (
        coding_memory.resolve()
        == Path(
            resolve_project_coding_memory_dir(
                agent_workspace_dir=application_workspace,
                project_dir=project,
            )
        ).resolve()
    )
    coding_memory.mkdir(parents=True)

    adapter = object.__new__(JiuwenSwarmCodeAdapter)
    adapter._instance_overrides = {"project_clean_runtime_support": True}
    adapter._project_dir = str(project)
    adapter._workspace_dir = str(project)
    adapter._agent_workspace_dir = str(application_workspace)
    runtime = JiuWenSwarmDeepAdapter._RuntimeConfig(
        project_dir=str(project),
        cwd=str(project),
        workspace=str(project / "browser-supplied-workspace"),
    )
    adapter._seed_code_runtime_cwd(
        runtime,
        project_workspace=str(runtime.workspace),
        task_cwd=str(project),
    )

    assert Path(get_cwd()).resolve() == project.resolve()
    assert Path(get_project_root()).resolve() == project.resolve()
    assert Path(str(get_workspace())).resolve() == application_workspace.resolve()
    intended = Path(_resolve_tool_file_path(object(), "intended.txt"))
    assert intended == project / "intended.txt"
    intended.write_text("intended\n", encoding="utf-8")
    history_path = object.__new__(WriteFileTool)._build_history_path(_Session())
    await _append_op_history(
        history_path,
        str(intended),
        "write",
        None,
        "intended\n",
    )

    assert Path(history_path).is_file()
    assert Path(history_path).is_relative_to(application_workspace)
    assert not (project / ".agent_history").exists()
    assert not (project / "coding_memory").exists()
    assert not (project / "prompt_attachment").exists()
    assert not (project / ".gitignore").exists()
    assert _git(project, "rev-parse", "HEAD") == before_head
    assert _git(project, "status", "--porcelain=v1", "--untracked-files=all") == (
        "?? intended.txt"
    )


def test_ordinary_code_runtime_keeps_project_relative_support_behavior(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    application_workspace = tmp_path / "application"
    workspace = Workspace(root_path=project)
    _set_workspace_coding_memory_directory(
        workspace,
        project_dir=str(project),
        agent_workspace_dir=str(application_workspace),
    )

    assert workspace.get_directory("coding_memory") == (
        resolve_project_coding_memory_workspace_path(project_dir=project)
    )
    adapter = object.__new__(JiuwenSwarmCodeAdapter)
    adapter._instance_overrides = {}
    adapter._project_dir = str(project)
    adapter._workspace_dir = str(project)
    adapter._agent_workspace_dir = str(application_workspace)
    runtime = JiuWenSwarmDeepAdapter._RuntimeConfig(
        project_dir=str(project),
        cwd=str(project),
        workspace=str(project),
    )
    adapter._seed_code_runtime_cwd(
        runtime,
        project_workspace=str(project),
        task_cwd=str(project),
    )

    assert Path(get_cwd()).resolve() == project.resolve()
    assert Path(get_project_root()).resolve() == project.resolve()
    assert Path(str(get_workspace())).resolve() == project.resolve()
