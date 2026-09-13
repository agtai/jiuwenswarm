# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Project-bound execution contract for Live Voice background code tasks.

The legacy schedule service is only the compatibility carrier.  This module
defines the narrow contract that makes the selected Web project, the effective
Code Agent root, and the result artifact agree before any model work starts.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any


PROJECT_CODE_PIPELINE = "project_code_pipeline"
PROJECT_CODE_EXECUTOR = "jiuwenswarm_code_agent"
PROJECT_CODE_ARTIFACT_KIND = "git_visible_project_change"
PROJECT_CODE_RESULT_CONTRACT = "target_tree_change_required"
PROJECT_CODE_EFFECT_POLICY = {
    "git_commit": "forbidden",
    "git_push": "forbidden",
    "tests": "forbidden",
    "shell": "forbidden",
}

EXECUTION_TARGET_NOT_BOUND = "EXECUTION_TARGET_NOT_BOUND"
UNSUPPORTED_PROJECT_TASK_CONSTRAINT = "UNSUPPORTED_PROJECT_TASK_CONSTRAINT"

_NO_TEST_PATTERNS = (
    re.compile(r"不要(?:运行|执行|跑)?(?:任何)?测试"),
    re.compile(r"不(?:运行|执行|跑)测试"),
    re.compile(
        r"(?:do\s+not|don't|without)\s+(?:run(?:ning)?\s+)?tests?\b", re.IGNORECASE
    ),
    re.compile(r"跳过(?:所有|任何)?测试"),
    re.compile(r"不(?:需要|必)(?:运行|执行|跑)?测试"),
    re.compile(r"\b(?:no|skip)\s+(?:all\s+|the\s+)?tests?\b", re.IGNORECASE),
)
_REQUIRED_TEST_PATTERNS = (
    re.compile(r"(?:运行|执行|跑)(?:所有|任何|相关|完整)?测试"),
    re.compile(r"确保(?:所有|相关)?测试通过"),
    re.compile(
        r"\b(?:run|execute)\s+(?:all\s+|the\s+|relevant\s+)?tests?\b",
        re.IGNORECASE,
    ),
    re.compile(r"\btests?\s+must\s+pass\b", re.IGNORECASE),
)
_NEGATED_COMMAND_CLAUSE_PATTERNS = (
    re.compile(
        r"\b(?:do\s+not|don't|never|without|no)\b.*?"
        r"(?=\b(?:but|however|then)\b|[.;\n]|$)",
        re.IGNORECASE,
    ),
    re.compile(r"(?:不要|不得|禁止|不允许|无需|不需要).*?(?=但|然后|再|[。；\n]|$)"),
)
_REQUIRED_SHELL_OR_GIT_PATTERNS = (
    re.compile(r"\b(?:git\s+)?(?:commit|push)\b", re.IGNORECASE),
    re.compile(r"\bgit\s+[a-z][\w-]*\b", re.IGNORECASE),
    re.compile(
        r"\b(?:run|execute|invoke)\b[^.;\n]{0,40}"
        r"\b(?:shell|command|script|npm|pnpm|yarn|make|cmake|python|node|bash|powershell)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:npm|pnpm|yarn)\s+(?:run\s+)?[\w:-]+\b", re.IGNORECASE),
    re.compile(r"\b(?:bash|powershell|cmd)(?:\.exe)?\s+\S+", re.IGNORECASE),
    re.compile(
        r"(?:运行|执行|跑)[^。；\n]{0,30}"
        r"(?:命令|脚本|npm|pnpm|yarn|git|bash|powershell|构建|迁移)"
    ),
    re.compile(r"(?:提交|推送)(?:代码|更改|改动|提交|到|至)?"),
)


def _path_key(value: str | os.PathLike[str]) -> str:
    return os.path.normcase(os.path.normpath(str(Path(value).resolve())))


def _git_root(project_dir: Path) -> Path:
    completed = subprocess.run(
        ["git", "-C", str(project_dir), "rev-parse", "--show-toplevel"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(detail or "selected project is not a Git worktree")
    value = completed.stdout.decode("utf-8", errors="strict").strip()
    if not value:
        raise RuntimeError("Git returned an empty project root")
    return Path(value).resolve()


def _unsupported_constraint(query: str) -> str | None:
    explicitly_forbids_tests = any(
        pattern.search(query) for pattern in _NO_TEST_PATTERNS
    )
    if not explicitly_forbids_tests and any(
        pattern.search(query) for pattern in _REQUIRED_TEST_PATTERNS
    ):
        return (
            "the bounded project executor cannot run tests because shell "
            "execution is disabled; remove the test requirement or use a "
            "reviewed executor capability that supports isolated commands"
        )
    negated_ranges = [
        match.span()
        for pattern in _NEGATED_COMMAND_CLAUSE_PATTERNS
        for match in pattern.finditer(query)
    ]
    for pattern in _REQUIRED_SHELL_OR_GIT_PATTERNS:
        for match in pattern.finditer(query):
            if any(start <= match.start() < end for start, end in negated_ranges):
                continue
            return (
                "the bounded project executor cannot run shell or Git commands; "
                "remove the command requirement or use a reviewed executor "
                "capability that supports isolated commands"
            )
    return None


def resolve_project_execution_contract(
    *,
    query: str,
    execution_target: dict[str, str],
    bound_execution_root: Any,
    project_executor: Any,
) -> tuple[dict[str, Any] | None, dict[str, str] | None]:
    """Resolve the trusted project contract or return a stable fail-closed error."""
    unsupported = _unsupported_constraint(query)
    if unsupported is not None:
        return None, {
            "error": unsupported,
            "code": UNSUPPORTED_PROJECT_TASK_CONSTRAINT,
        }

    selected = execution_target.get("project_dir")
    bound = (
        bound_execution_root.strip() if isinstance(bound_execution_root, str) else ""
    )
    if not selected or selected == "unknown" or not bound or project_executor is None:
        return None, {
            "error": "selected project is not bound to a project-capable executor",
            "code": EXECUTION_TARGET_NOT_BOUND,
        }
    if not callable(
        getattr(project_executor, "process_background_code_task_stream", None)
    ):
        return None, {
            "error": "bound executor does not expose the background code-task capability",
            "code": EXECUTION_TARGET_NOT_BOUND,
        }

    try:
        selected_root = Path(selected).resolve(strict=True)
        bound_root = Path(bound).resolve(strict=True)
        if not selected_root.is_dir() or not bound_root.is_dir():
            raise RuntimeError("execution root is not a directory")
        git_root = _git_root(selected_root)
    except (OSError, RuntimeError, UnicodeError) as exc:
        return None, {
            "error": f"selected project cannot be used for project execution: {exc}",
            "code": EXECUTION_TARGET_NOT_BOUND,
        }

    if _path_key(selected_root) != _path_key(bound_root) or _path_key(
        selected_root
    ) != _path_key(git_root):
        return None, {
            "error": "selected project, Code Agent root, and Git root do not match",
            "code": EXECUTION_TARGET_NOT_BOUND,
        }

    return {
        "effective_execution_root": str(selected_root),
        "artifact_kind": PROJECT_CODE_ARTIFACT_KIND,
        "executor": PROJECT_CODE_EXECUTOR,
        "pipeline": PROJECT_CODE_PIPELINE,
        "effect_policy": dict(PROJECT_CODE_EFFECT_POLICY),
    }, None


__all__ = [
    "EXECUTION_TARGET_NOT_BOUND",
    "PROJECT_CODE_ARTIFACT_KIND",
    "PROJECT_CODE_EFFECT_POLICY",
    "PROJECT_CODE_EXECUTOR",
    "PROJECT_CODE_PIPELINE",
    "PROJECT_CODE_RESULT_CONTRACT",
    "UNSUPPORTED_PROJECT_TASK_CONSTRAINT",
    "resolve_project_execution_contract",
]
