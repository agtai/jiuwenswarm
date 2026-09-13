# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import pytest

from jiuwenswarm.agents.harness.common.tools.bash_tool_safety import (
    _pre_execute_shell_command,
    install_shell_tool_safety_hooks,
    reset_installed_flag,
)
from jiuwenswarm.agents.harness.common.tools.command_tools import (
    forbid_background_project_shell_commands,
)


@pytest.fixture(autouse=True)
def _reset_install_flag():
    reset_installed_flag()
    yield
    reset_installed_flag()


def test_pre_execute_blocks_pkill_on_jiuwenswarm_tui() -> None:
    err = _pre_execute_shell_command('pkill -f "jiuwenswarm-tui" 2>/dev/null')
    assert err is not None
    assert "rejected for safety" in err


def test_pre_execute_allows_unrelated_ps() -> None:
    err = _pre_execute_shell_command("ps aux | grep node | head -5")
    assert err is None


def test_install_wraps_bash_tool_invoke() -> None:
    from openjiuwen.harness.tools.shell.bash._tool import BashTool

    install_shell_tool_safety_hooks()
    assert getattr(BashTool.invoke, "jiuwenswarm_safety_wrapped", False)
    install_shell_tool_safety_hooks()
    assert getattr(BashTool.invoke, "jiuwenswarm_safety_wrapped", False)


@pytest.mark.parametrize(
    "command",
    [
        "git commit -m task",
        "git -C . push origin HEAD",
        "git checkout -b background-branch",
        "git -c alias.ship=push ship",
        'cmd /c "git commit -m task"',
        "bash -lc 'git push origin HEAD'",
        "$(git checkout -b background-branch)",
        "gh pr create --title task",
        "git status --short",
        "python -m pytest -q",
        'python -c "import subprocess; subprocess.run([\'git\', \'commit\'])"',
        "./generated-script.sh",
    ],
)
def test_background_project_context_blocks_all_shell_commands(
    command: str,
) -> None:
    with forbid_background_project_shell_commands():
        err = _pre_execute_shell_command(command)

    assert err is not None
    assert "rejected for safety" in err


def test_background_shell_policy_does_not_leak_outside_task_context() -> None:
    with forbid_background_project_shell_commands():
        assert _pre_execute_shell_command("git commit -m task") is not None

    assert _pre_execute_shell_command("git commit -m task") is None
