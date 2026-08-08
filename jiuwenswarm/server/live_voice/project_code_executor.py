# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Formal attempt adapters for the bounded project Code Agent.

The direct D0 adapter owns a durable attempt journal and invokes the Code Agent
without ``schedule.*``.  The retained legacy adapter is compatibility-only;
neither adapter owns formal command, task, event, or retry identity.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import math
import os
import re
import shutil
import sqlite3
import stat
import subprocess
import tempfile
import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import partial
from pathlib import Path
from types import MappingProxyType
from typing import Any, Protocol

from jiuwenswarm.agents.harness.common.tools.command_tools import (
    forbid_background_project_shell_commands,
)
from jiuwenswarm.common.coding_memory_paths import (
    resolve_project_coding_memory_dir,
)
from jiuwenswarm.common.schema.agent import AgentRequest
from jiuwenswarm.common.schema.live_voice_contract_v2 import ErrorCode, TerminalOutcome
from jiuwenswarm.common.utils import get_agent_workspace_dir, get_prompt_attachment_dir

from .formal_task_models import (
    ExecutorDeliveryResult,
    ExecutorObservation,
    ExecutorResolution,
    FormalAttemptState,
    FormalTaskSpec,
    FormalTaskViolation,
    OutboxKind,
    PersistentAttemptRecord,
    PersistentOutboxItem,
    PersistentTaskRecord,
    utc_now,
)

FORMAL_PROJECT_EXECUTOR_ID = "jiuwenswarm_code_agent.project_code"
DIRECT_PROJECT_EXECUTOR_REF_PREFIX = "d0-project:"
PROJECT_CODE_PIPELINE = "project_code_pipeline"
PROJECT_CODE_EXECUTOR = "jiuwenswarm_code_agent"
PROJECT_CODE_ARTIFACT_KIND = "git_visible_project_change"
PROJECT_CODE_EFFECT_POLICY = {
    "git_commit": "forbidden",
    "git_push": "forbidden",
    "tests": "forbidden",
    "shell": "forbidden",
}
FORMAL_RUNTIME_SUPPORT_POLICY = MappingProxyType(
    {
        ".gitignore": "target_immutable",
        "coding_memory": "application_owned",
        "prompt_attachment": "application_owned",
        ".agent_history": "application_owned",
    }
)
_DIRECT_EXECUTOR_TABLE = "live_voice_formal_project_attempts_v1"
_DIRECT_EXECUTOR_LEASE = timedelta(minutes=5)
_DIRECT_EXECUTOR_REF_PREFIX = DIRECT_PROJECT_EXECUTOR_REF_PREFIX
_MAX_DIRECT_CLEANUP_TIMEOUT_SECONDS = 5.0
_MAX_DIRECT_RUNNING_WORKERS = 32
_PROTECTED_TARGET_SUPPORT_PATHS = tuple(FORMAL_RUNTIME_SUPPORT_POLICY)
_EXECUTION_TARGET_FIELDS = {
    "project_dir",
    "project_id",
    "origin_session_id",
    "origin_channel_id",
}
_OWNER_SCOPE_FIELDS = {"channel_id", "session_id", "app_id"}


class LegacyProjectTaskService(Protocol):
    async def run_task(
        self, query: str, model: Any = None, pipeline: str | None = None, **kwargs: Any
    ) -> dict[str, Any]: ...

    async def get_scheduled_task_status(
        self, task_id: str, **kwargs: Any
    ) -> dict[str, Any]: ...

    async def cancel_scheduled_task(
        self, task_id: str, **kwargs: Any
    ) -> dict[str, Any]: ...


@dataclass(frozen=True, slots=True)
class ProjectExecutionBinding:
    """Trusted runtime objects for one exact server-resolved project context."""

    service: LegacyProjectTaskService | None
    execution_agent: Any
    project_executor: Any
    effective_execution_root: str
    execution_target: Mapping[str, str]
    owner_scope: Mapping[str, str]
    resolved_revision_kind: str
    resolved_revision_value: str | None
    model: Any = None
    model_identity: str | None = None
    model_config_version: str | None = None
    context_release: Callable[[], None] | None = None
    dispatch_fence: Callable[[], Awaitable[None]] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "execution_target", MappingProxyType(dict(self.execution_target))
        )
        object.__setattr__(
            self, "owner_scope", MappingProxyType(dict(self.owner_scope))
        )

    def validate(self, spec: FormalTaskSpec, *, for_dispatch: bool) -> None:
        context_path = spec.context.file_path
        selected = self.execution_target.get("project_dir")
        if context_path is None or not selected:
            raise FormalTaskViolation(
                "EXECUTION_TARGET_NOT_BOUND",
                "formal project execution requires a file context and selected project",
                ErrorCode.PERMISSION_DENIED,
            )
        if set(self.owner_scope) != _OWNER_SCOPE_FIELDS or any(
            type(value) is not str or not value.strip()
            for value in self.owner_scope.values()
        ):
            raise FormalTaskViolation(
                "LEGACY_ADAPTER_SCOPE_REQUIRED",
                "legacy carrier scope must be an exact trusted owner scope",
                ErrorCode.PERMISSION_DENIED,
            )
        if set(self.execution_target) != _EXECUTION_TARGET_FIELDS or any(
            type(value) is not str or not value.strip()
            for value in self.execution_target.values()
        ):
            raise FormalTaskViolation(
                "EXECUTION_TARGET_NOT_BOUND",
                "legacy carrier target must contain exact project and origin facts",
                ErrorCode.PERMISSION_DENIED,
            )
        if for_dispatch and (
            self.resolved_revision_kind != spec.context.revision_kind
            or self.resolved_revision_value != spec.context.revision_value
        ):
            raise FormalTaskViolation(
                "EXECUTION_CONTEXT_REVISION_MISMATCH",
                "runtime project revision no longer matches the resolved task context",
                ErrorCode.PERMISSION_DENIED,
            )
        selected_project_id = self.execution_target.get("project_id")
        if (
            selected_project_id != spec.context.stable_id
            or spec.context.scope.project_id != spec.context.stable_id
        ):
            raise FormalTaskViolation(
                "EXECUTION_CONTEXT_IDENTITY_MISMATCH",
                "selected project identity does not match the resolved task context",
                ErrorCode.PERMISSION_DENIED,
            )
        formal_session_id = spec.context.scope.session_id
        if (
            formal_session_id is None
            or self.execution_target.get("origin_session_id") != formal_session_id
            or self.owner_scope.get("session_id") != formal_session_id
        ):
            raise FormalTaskViolation(
                "EXECUTION_CONTEXT_SCOPE_MISMATCH",
                "legacy carrier session facts do not match the formal task scope",
                ErrorCode.PERMISSION_DENIED,
            )
        try:
            context_key = _path_key(context_path, strict=for_dispatch)
            selected_key = _path_key(selected, strict=for_dispatch)
            root_key = _path_key(self.effective_execution_root, strict=for_dispatch)
        except OSError as exc:
            raise FormalTaskViolation(
                "EXECUTION_TARGET_NOT_BOUND",
                "formal project execution root cannot be resolved",
                ErrorCode.PERMISSION_DENIED,
            ) from exc
        if context_key != selected_key or context_key != root_key:
            raise FormalTaskViolation(
                "EXECUTION_TARGET_NOT_BOUND",
                "formal context, selected project, and Code Agent root must match",
                ErrorCode.PERMISSION_DENIED,
            )
        attributes = dict(spec.attributes)
        expected_model_identity = attributes.get("model_identity")
        expected_model_config_version = attributes.get("model_config_version")
        if (
            not expected_model_identity
            or not expected_model_config_version
            or self.model_identity != expected_model_identity
            or self.model_config_version != expected_model_config_version
        ):
            raise FormalTaskViolation(
                "EXECUTOR_MODEL_BINDING_MISMATCH",
                "runtime model identity or configuration does not match the task",
                ErrorCode.PERMISSION_DENIED,
            )
        if for_dispatch and self.execution_agent is None:
            raise FormalTaskViolation(
                "EXECUTOR_CAPABILITY_UNAVAILABLE",
                "project dispatch requires a task-scoped execution Agent",
                ErrorCode.CAPABILITY_UNAVAILABLE,
            )
        if for_dispatch and not callable(self.dispatch_fence):
            raise FormalTaskViolation(
                "EXECUTION_DISPATCH_FENCE_REQUIRED",
                "project dispatch requires an authoritative handoff fence",
                ErrorCode.CAPABILITY_UNAVAILABLE,
            )
        if for_dispatch and not callable(
            getattr(self.project_executor, "process_background_code_task_stream", None)
        ):
            raise FormalTaskViolation(
                "EXECUTOR_CAPABILITY_UNAVAILABLE",
                "bound Code Agent lacks the background project capability",
                ErrorCode.CAPABILITY_UNAVAILABLE,
            )


class ProjectExecutionBindingResolver(Protocol):
    async def resolve(
        self,
        spec: FormalTaskSpec,
        *,
        for_dispatch: bool,
    ) -> ProjectExecutionBinding: ...


def _path_key(value: str | os.PathLike[str], *, strict: bool = True) -> str:
    return os.path.normcase(os.path.normpath(str(Path(value).resolve(strict=strict))))


def _expected_contract(root: str) -> dict[str, object]:
    return {
        "effective_execution_root": str(Path(root).resolve(strict=False)),
        "artifact_kind": PROJECT_CODE_ARTIFACT_KIND,
        "executor": PROJECT_CODE_EXECUTOR,
        "pipeline": PROJECT_CODE_PIPELINE,
        "effect_policy": dict(PROJECT_CODE_EFFECT_POLICY),
    }


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(UTC)


def _lease_expiry(now: str) -> str:
    return (_parse_utc(now) + _DIRECT_EXECUTOR_LEASE).isoformat().replace("+00:00", "Z")


def _git_output(root: Path, *args: str) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        raise FormalTaskViolation(
            "EXECUTION_TARGET_NOT_BOUND",
            "selected project failed a required Git inspection",
            ErrorCode.PERMISSION_DENIED,
        )
    return completed.stdout


def _git_root(root: Path) -> Path:
    value = (
        _git_output(root, "rev-parse", "--show-toplevel")
        .decode("utf-8", errors="strict")
        .strip()
    )
    if not value:
        raise FormalTaskViolation(
            "EXECUTION_TARGET_NOT_BOUND",
            "selected project has no Git root",
            ErrorCode.PERMISSION_DENIED,
        )
    return Path(value).resolve(strict=True)


def _git_head(root: Path) -> str:
    value = (
        _git_output(root, "rev-parse", "HEAD").decode("ascii", errors="strict").strip()
    )
    if not value:
        raise FormalTaskViolation(
            "EXECUTION_TARGET_NOT_BOUND",
            "selected project has no committed Git HEAD",
            ErrorCode.PERMISSION_DENIED,
        )
    return value


def _project_tree_fingerprint(root: Path) -> str:
    """Hash tracked and non-ignored untracked project content without mutation."""

    digest = hashlib.sha256()
    digest.update(
        _git_output(root, "status", "--porcelain=v2", "-z", "--untracked-files=all")
    )
    raw_paths = _git_output(
        root,
        "ls-files",
        "--cached",
        "--others",
        "--exclude-standard",
        "-z",
    ).split(b"\0")
    for raw_relative in sorted(path for path in raw_paths if path):
        try:
            relative = raw_relative.decode("utf-8")
        except UnicodeDecodeError as error:
            raise FormalTaskViolation(
                "EXECUTION_TARGET_NOT_BOUND",
                "selected project contains a non-UTF-8 Git path",
                ErrorCode.PERMISSION_DENIED,
            ) from error
        path = root / Path(relative)
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        try:
            if path.is_symlink():
                digest.update(b"L\0")
                digest.update(str(path.readlink()).encode("utf-8"))
            elif not path.exists():
                digest.update(b"M\0")
            elif path.is_dir():
                digest.update(b"D\0")
            else:
                digest.update(b"F\0")
                with path.open("rb") as stream:
                    while chunk := stream.read(1024 * 1024):
                        digest.update(chunk)
        except OSError as error:
            raise FormalTaskViolation(
                "EXECUTION_TARGET_NOT_BOUND",
                "selected project could not be fingerprinted",
                ErrorCode.PERMISSION_DENIED,
            ) from error
        digest.update(b"\0")
    return digest.hexdigest()


def _is_unsafe_filesystem_link(path: Path) -> bool:
    """Recognize POSIX links plus Windows junction/reparse-point escapes."""

    try:
        if path.is_symlink():
            return True
        is_junction = getattr(path, "is_junction", None)
        if callable(is_junction) and is_junction():
            return True
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except FileNotFoundError:
        return False
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _reject_git_visible_symlinks(root: Path) -> None:
    """D0 rejects link/reparse escapes from every Git-visible path ancestor."""

    raw_paths = _git_output(
        root,
        "ls-files",
        "--cached",
        "--others",
        "--exclude-standard",
        "-z",
    ).split(b"\0")
    for raw_relative in (item for item in raw_paths if item):
        try:
            relative = Path(raw_relative.decode("utf-8", errors="strict"))
        except UnicodeDecodeError as error:
            raise FormalTaskViolation(
                "EXECUTION_TARGET_NOT_BOUND",
                "selected project contains a non-UTF-8 Git path",
                ErrorCode.PERMISSION_DENIED,
            ) from error
        if relative.is_absolute() or ".." in relative.parts:
            raise FormalTaskViolation(
                "EXECUTION_TARGET_SYMLINK_UNSAFE",
                "selected project contains an unsafe Git-visible path",
                ErrorCode.PERMISSION_DENIED,
            )
        try:
            is_link = any(
                _is_unsafe_filesystem_link(root.joinpath(*relative.parts[:depth]))
                for depth in range(1, len(relative.parts) + 1)
            )
        except OSError as error:
            raise FormalTaskViolation(
                "EXECUTION_TARGET_SYMLINK_UNSAFE",
                "selected project symlink safety could not be inspected",
                ErrorCode.PERMISSION_DENIED,
            ) from error
        if is_link:
            raise FormalTaskViolation(
                "EXECUTION_TARGET_SYMLINK_UNSAFE",
                "direct project execution does not permit Git-visible links or reparse points",
                ErrorCode.PERMISSION_DENIED,
            )


def _project_content_fingerprint(root: Path) -> str:
    """Hash the Git-visible path/content state without index presentation details."""

    digest = hashlib.sha256()
    raw_paths = _git_output(
        root,
        "ls-files",
        "--cached",
        "--others",
        "--exclude-standard",
        "-z",
    ).split(b"\0")
    for raw_relative in sorted(path for path in raw_paths if path):
        relative = raw_relative.decode("utf-8", errors="strict")
        path = root / Path(relative)
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        if path.is_symlink():
            digest.update(b"L\0")
            digest.update(str(path.readlink()).encode("utf-8"))
        elif not path.exists():
            digest.update(b"M\0")
        elif path.is_dir():
            digest.update(b"D\0")
        else:
            digest.update(b"F\0")
            with path.open("rb") as stream:
                while chunk := stream.read(1024 * 1024):
                    digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()


def _path_fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    if not path.exists() and not path.is_symlink():
        digest.update(b"missing")
        return digest.hexdigest()
    try:
        if path.is_symlink():
            digest.update(b"link\0")
            digest.update(str(path.readlink()).encode("utf-8"))
        elif path.is_file():
            digest.update(b"file\0")
            with path.open("rb") as stream:
                while chunk := stream.read(1024 * 1024):
                    digest.update(chunk)
        elif path.is_dir():
            digest.update(b"dir\0")
            for child in sorted(path.rglob("*"), key=lambda item: str(item)):
                relative = child.relative_to(path)
                digest.update(str(relative).replace("\\", "/").encode("utf-8"))
                digest.update(b"\0")
                if child.is_symlink():
                    digest.update(b"link\0")
                    digest.update(str(child.readlink()).encode("utf-8"))
                elif child.is_file():
                    digest.update(b"file\0")
                    with child.open("rb") as stream:
                        while chunk := stream.read(1024 * 1024):
                            digest.update(chunk)
                else:
                    digest.update(b"dir\0")
    except OSError as error:
        raise FormalTaskViolation(
            "RUNTIME_SUPPORT_GOVERNANCE_UNAVAILABLE",
            "runtime support paths could not be inspected",
            ErrorCode.UNAVAILABLE,
        ) from error
    return digest.hexdigest()


def _target_support_fingerprints(root: Path) -> dict[str, str]:
    return {
        relative: _path_fingerprint(root / relative)
        for relative in _PROTECTED_TARGET_SUPPORT_PATHS
    }


def _git_run_with_input(root: Path, args: tuple[str, ...], payload: bytes) -> None:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        input=payload,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError("PROJECT_CHANGE_APPLICATION_FAILED")


def _create_attempt_worktree(
    root: Path, attempt_id: str, before_head: str
) -> tuple[Path, Path]:
    parent, worktree = _attempt_worktree_paths(root, attempt_id)
    base = parent.parent
    try:
        base.mkdir(mode=0o700, exist_ok=True)
        safe_temp_root = Path(tempfile.gettempdir()).resolve(strict=True)
    except OSError as error:
        raise RuntimeError("PROJECT_WORKTREE_UNAVAILABLE") from error
    expected_base = safe_temp_root / "jiuwenswarm-live-voice-d0"
    try:
        base_resolved = base.resolve(strict=True)
    except OSError as error:
        raise RuntimeError("PROJECT_WORKTREE_UNAVAILABLE") from error
    if (
        base != expected_base
        or _is_unsafe_filesystem_link(base)
        or _is_unsafe_filesystem_link(base.parent)
        or base_resolved != expected_base
    ):
        raise RuntimeError("PROJECT_WORKTREE_UNAVAILABLE")
    try:
        parent.mkdir(mode=0o700)
    except OSError as error:
        raise RuntimeError("PROJECT_WORKTREE_UNAVAILABLE") from error
    try:
        parent_resolved = parent.resolve(strict=True)
    except OSError as error:
        with contextlib.suppress(OSError):
            parent.rmdir()
        raise RuntimeError("PROJECT_WORKTREE_UNAVAILABLE") from error
    if (
        _is_unsafe_filesystem_link(base)
        or _is_unsafe_filesystem_link(parent)
        or parent_resolved != expected_base / parent.name
        or worktree.exists()
        or _is_unsafe_filesystem_link(worktree)
    ):
        with contextlib.suppress(OSError):
            parent.rmdir()
        raise RuntimeError("PROJECT_WORKTREE_UNAVAILABLE")
    completed = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "worktree",
            "add",
            "--detach",
            str(worktree),
            before_head,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        with contextlib.suppress(OSError):
            parent.rmdir()
        raise RuntimeError("PROJECT_WORKTREE_UNAVAILABLE")
    return parent, worktree


def _attempt_worktree_paths(root: Path, attempt_id: str) -> tuple[Path, Path]:
    base = (
        Path(tempfile.gettempdir()).resolve(strict=True)
        / "jiuwenswarm-live-voice-d0"
    )
    namespace = f"{_path_key(root, strict=False)}\0{attempt_id}".encode("utf-8")
    parent = base / f"attempt-{hashlib.sha256(namespace).hexdigest()}"
    return parent, parent / "checkout"


def _worktree_registered(root: Path, worktree: Path) -> bool:
    completed = subprocess.run(
        ["git", "-C", str(root), "worktree", "list", "--porcelain"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError("PROJECT_WORKTREE_CLEANUP_PENDING")
    expected = _path_key(worktree, strict=False)
    for line in completed.stdout.decode("utf-8", errors="strict").splitlines():
        if line.startswith("worktree ") and _path_key(
            line.removeprefix("worktree "), strict=False
        ) == expected:
            return True
    return False


def _remove_attempt_worktree(root: Path, parent: Path, worktree: Path) -> None:
    safe_temp_root = (
        Path(tempfile.gettempdir()).resolve(strict=True)
        / "jiuwenswarm-live-voice-d0"
    )
    resolved_parent = parent.resolve(strict=False)
    resolved_worktree = worktree.resolve(strict=False)
    if (
        resolved_parent.parent != safe_temp_root
        or not re.fullmatch(r"attempt-[0-9a-f]{64}", resolved_parent.name)
        or resolved_worktree != resolved_parent / "checkout"
    ):
        raise RuntimeError("PROJECT_WORKTREE_CLEANUP_TARGET_UNSAFE")
    for _attempt in range(3):
        registered = _worktree_registered(root, worktree)
        if not (worktree.exists() or worktree.is_symlink() or registered):
            break
        completed = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "worktree",
                "remove",
                "--force",
                str(worktree),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if completed.returncode == 0 and not (
            worktree.exists()
            or worktree.is_symlink()
            or _worktree_registered(root, worktree)
        ):
            break
    if (
        worktree.exists()
        or worktree.is_symlink()
        or _worktree_registered(root, worktree)
    ):
        raise RuntimeError("PROJECT_WORKTREE_CLEANUP_PENDING")
    try:
        parent.rmdir()
    except OSError as error:
        raise RuntimeError("PROJECT_WORKTREE_CLEANUP_PENDING") from error


def _seed_attempt_worktree(root: Path, worktree: Path, expected_content: str) -> None:
    cached_patch = _git_output(
        root, "diff", "--cached", "--binary", "--full-index", "HEAD", "--"
    )
    if cached_patch:
        _git_run_with_input(worktree, ("apply", "--binary", "-"), cached_patch)
        _git_output(worktree, "add", "-A", "--")
    unstaged_patch = _git_output(root, "diff", "--binary", "--full-index", "--")
    if unstaged_patch:
        _git_run_with_input(worktree, ("apply", "--binary", "-"), unstaged_patch)
    _reject_git_visible_symlinks(worktree)
    _mirror_git_visible_content(root, worktree)
    _reject_git_visible_symlinks(worktree)
    if _project_content_fingerprint(worktree) != expected_content:
        raise RuntimeError("PROJECT_WORKTREE_BASELINE_MISMATCH")
    _git_output(worktree, "add", "-A", "--")


def _mirror_git_visible_content(
    root: Path,
    worktree: Path,
    *,
    raw_paths: tuple[bytes, ...] | None = None,
) -> None:
    """Preserve the selected checkout's exact bytes across linked worktrees.

    Git may apply a different checkout conversion (notably ``core.autocrlf``)
    when it creates the detached attempt worktree.  The index reconstruction
    above preserves staged versus unstaged state; this final content mirror
    preserves the authority checkout's actual Git-visible working-tree bytes.
    """

    selected_paths = (
        _git_output(
            root,
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
            "-z",
        ).split(b"\0")
        if raw_paths is None
        else raw_paths
    )
    for raw_relative in (item for item in selected_paths if item):
        relative = Path(raw_relative.decode("utf-8", errors="strict"))
        if relative.is_absolute() or ".." in relative.parts:
            raise RuntimeError("PROJECT_WORKTREE_BASELINE_MISMATCH")
        _require_safe_mirror_path(root, relative)
        _require_safe_mirror_path(worktree, relative)
        source = root.joinpath(*relative.parts)
        destination = worktree.joinpath(*relative.parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        _require_safe_mirror_path(worktree, relative)
        if not source.exists() and not source.is_symlink():
            if destination.is_symlink() or destination.is_file():
                destination.unlink()
            elif destination.is_dir():
                shutil.rmtree(destination)
            continue
        if source.is_symlink():
            if destination.is_dir() and not destination.is_symlink():
                shutil.rmtree(destination)
            elif destination.exists() or destination.is_symlink():
                destination.unlink()
            destination.symlink_to(
                source.readlink(), target_is_directory=source.is_dir()
            )
        elif source.is_dir():
            if destination.is_symlink() or destination.is_file():
                destination.unlink()
            destination.mkdir(parents=True, exist_ok=True)
        else:
            if destination.is_dir() and not destination.is_symlink():
                shutil.rmtree(destination)
            shutil.copy2(source, destination)
        _require_safe_mirror_path(worktree, relative)


def _require_safe_mirror_path(root: Path, relative: Path) -> None:
    """Fail closed before mirroring through a link or reparse-point ancestor."""

    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise RuntimeError("PROJECT_WORKTREE_BASELINE_MISMATCH")
    try:
        if _is_unsafe_filesystem_link(root):
            raise RuntimeError("PROJECT_WORKTREE_BASELINE_MISMATCH")
        for depth in range(1, len(relative.parts) + 1):
            candidate = root.joinpath(*relative.parts[:depth])
            if _is_unsafe_filesystem_link(candidate):
                raise RuntimeError("PROJECT_WORKTREE_BASELINE_MISMATCH")
    except OSError as error:
        raise RuntimeError("PROJECT_WORKTREE_BASELINE_MISMATCH") from error


def _attempt_patch(worktree: Path) -> tuple[bytes, str, tuple[bytes, ...]]:
    expected_tree = _project_content_fingerprint(worktree)
    raw_untracked = _git_output(
        worktree,
        "ls-files",
        "--others",
        "--exclude-standard",
        "-z",
    ).split(b"\0")
    untracked = [
        path.decode("utf-8", errors="strict") for path in raw_untracked if path
    ]
    if untracked:
        completed = subprocess.run(
            ["git", "-C", str(worktree), "add", "--intent-to-add", "--", *untracked],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError("PROJECT_CHANGE_CAPTURE_FAILED")
    patch = _git_output(worktree, "diff", "--binary", "--full-index", "--")
    if not patch:
        raise RuntimeError("NO_EFFECTIVE_TARGET_CHANGE")
    changed_paths = tuple(
        path
        for path in _git_output(
            worktree,
            "diff",
            "--name-only",
            "--no-renames",
            "-z",
            "--",
        ).split(b"\0")
        if path
    )
    if not changed_paths:
        raise RuntimeError("PROJECT_CHANGE_CAPTURE_FAILED")
    return patch, expected_tree, changed_paths


def _apply_attempt_patch(
    root: Path,
    patch: bytes,
    *,
    source_worktree: Path,
    changed_paths: tuple[bytes, ...],
    expected_tree: str,
    before_tree: str,
    before_head: str,
    protected_support: Mapping[str, str],
) -> None:
    if (
        _git_head(root) != before_head
        or _project_tree_fingerprint(root) != before_tree
        or _target_support_fingerprints(root) != dict(protected_support)
    ):
        raise RuntimeError("EXECUTION_TARGET_CHANGED_DURING_ATTEMPT")
    before_content = _project_content_fingerprint(root)
    with tempfile.TemporaryDirectory(
        prefix="jiuwenswarm-live-voice-d0-rollback-"
    ) as snapshot_raw:
        snapshot = Path(snapshot_raw)
        _mirror_git_visible_content(root, snapshot, raw_paths=changed_paths)
        try:
            _git_run_with_input(root, ("apply", "--check", "--binary", "-"), patch)
            _git_run_with_input(root, ("apply", "--binary", "-"), patch)
            _mirror_git_visible_content(
                source_worktree,
                root,
                raw_paths=changed_paths,
            )
            if _project_content_fingerprint(root) != expected_tree:
                raise RuntimeError("PROJECT_CHANGE_ATTRIBUTION_FAILED")
        except Exception as error:
            try:
                _mirror_git_visible_content(snapshot, root, raw_paths=changed_paths)
                if (
                    _git_head(root) != before_head
                    or _project_tree_fingerprint(root) != before_tree
                    or _project_content_fingerprint(root) != before_content
                    or _target_support_fingerprints(root) != dict(protected_support)
                ):
                    raise RuntimeError("PROJECT_CHANGE_ROLLBACK_FAILED")
            except Exception as rollback_error:
                raise RuntimeError("PROJECT_CHANGE_ROLLBACK_FAILED") from rollback_error
            raise error


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=True))
    except ValueError:
        return False
    return True


def _runtime_support_governance(root: Path) -> dict[str, object]:
    """Resolve the exact clean-workspace ownership policy for a formal Agent."""

    agent_workspace = get_agent_workspace_dir().resolve(strict=False)
    application_paths = {
        "coding_memory": Path(
            resolve_project_coding_memory_dir(
                agent_workspace_dir=agent_workspace,
                project_dir=root,
            )
        ).resolve(strict=False),
        "prompt_attachment": get_prompt_attachment_dir().resolve(strict=False),
        ".agent_history": (agent_workspace / ".agent_history").resolve(strict=False),
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


@dataclass(frozen=True, slots=True)
class _DirectAttempt:
    attempt_id: str
    task_id: str
    executor_ref: str
    spec_fingerprint: bytes
    project_root: str
    state: FormalAttemptState
    outcome: TerminalOutcome | None
    source_seq: int
    accepted_at: str
    running_at: str | None
    terminal_at: str | None
    raw_status: str
    summary: str | None
    error: str | None
    before_tree: str
    before_content: str | None
    expected_tree: str | None
    before_head: str
    protected_support_json: str
    governance_json: str
    owner_id: str | None
    lease_expires_at: str | None
    cancel_requested: bool


class _DirectProjectAttemptJournal:
    """SQLite truth for the direct D0 Executor; independent of scheduler JSON."""

    def __init__(self, database: str | os.PathLike[str]) -> None:
        self.database = str(Path(database).resolve(strict=False))
        Path(self.database).parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=30000")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def all_attempts(self) -> tuple[_DirectAttempt, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM {_DIRECT_EXECUTOR_TABLE} ORDER BY attempt_id"
            ).fetchall()
        return tuple(self._from_row(row) for row in rows)

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {_DIRECT_EXECUTOR_TABLE} (
                    attempt_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    executor_ref TEXT NOT NULL UNIQUE,
                    spec_fingerprint BLOB NOT NULL,
                    project_root TEXT NOT NULL,
                    state TEXT NOT NULL,
                    outcome TEXT,
                    source_seq INTEGER NOT NULL,
                    accepted_at TEXT NOT NULL,
                    running_at TEXT,
                    terminal_at TEXT,
                    raw_status TEXT NOT NULL,
                    summary TEXT,
                    error TEXT,
                    before_tree TEXT NOT NULL,
                    before_content TEXT,
                    expected_tree TEXT,
                    before_head TEXT NOT NULL,
                    protected_support_json TEXT NOT NULL,
                    governance_json TEXT NOT NULL,
                    owner_id TEXT,
                    lease_expires_at TEXT,
                    cancel_requested INTEGER NOT NULL DEFAULT 0
                        CHECK(cancel_requested IN (0, 1))
                )
                """
            )
            columns = {
                str(row["name"])
                for row in connection.execute(
                    f"PRAGMA table_info({_DIRECT_EXECUTOR_TABLE})"
                ).fetchall()
            }
            if "before_content" not in columns:
                connection.execute(
                    f"ALTER TABLE {_DIRECT_EXECUTOR_TABLE} ADD COLUMN before_content TEXT"
                )
            if "expected_tree" not in columns:
                connection.execute(
                    f"ALTER TABLE {_DIRECT_EXECUTOR_TABLE} ADD COLUMN expected_tree TEXT"
                )

    @staticmethod
    def _from_row(row: sqlite3.Row) -> _DirectAttempt:
        return _DirectAttempt(
            attempt_id=str(row["attempt_id"]),
            task_id=str(row["task_id"]),
            executor_ref=str(row["executor_ref"]),
            spec_fingerprint=bytes(row["spec_fingerprint"]),
            project_root=str(row["project_root"]),
            state=FormalAttemptState(str(row["state"])),
            outcome=(
                None if row["outcome"] is None else TerminalOutcome(str(row["outcome"]))
            ),
            source_seq=int(row["source_seq"]),
            accepted_at=str(row["accepted_at"]),
            running_at=(None if row["running_at"] is None else str(row["running_at"])),
            terminal_at=(
                None if row["terminal_at"] is None else str(row["terminal_at"])
            ),
            raw_status=str(row["raw_status"]),
            summary=None if row["summary"] is None else str(row["summary"]),
            error=None if row["error"] is None else str(row["error"]),
            before_tree=str(row["before_tree"]),
            before_content=(
                None if row["before_content"] is None else str(row["before_content"])
            ),
            expected_tree=(
                None if row["expected_tree"] is None else str(row["expected_tree"])
            ),
            before_head=str(row["before_head"]),
            protected_support_json=str(row["protected_support_json"]),
            governance_json=str(row["governance_json"]),
            owner_id=None if row["owner_id"] is None else str(row["owner_id"]),
            lease_expires_at=(
                None
                if row["lease_expires_at"] is None
                else str(row["lease_expires_at"])
            ),
            cancel_requested=bool(row["cancel_requested"]),
        )

    def get(self, attempt_id: str) -> _DirectAttempt | None:
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT * FROM {_DIRECT_EXECUTOR_TABLE} WHERE attempt_id=?",
                (attempt_id,),
            ).fetchone()
        return None if row is None else self._from_row(row)

    def create(
        self,
        *,
        item: PersistentOutboxItem,
        project_root: str,
        before_tree: str,
        before_content: str,
        before_head: str,
        protected_support: Mapping[str, str],
        governance: Mapping[str, object],
        owner_id: str,
        now: str,
    ) -> tuple[bool, _DirectAttempt]:
        fingerprint = item.spec.fingerprint_bytes()
        executor_ref = f"{_DIRECT_EXECUTOR_REF_PREFIX}{item.attempt_id}"
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                f"SELECT * FROM {_DIRECT_EXECUTOR_TABLE} WHERE attempt_id=?",
                (item.attempt_id,),
            ).fetchone()
            if row is not None:
                existing = self._from_row(row)
                if (
                    existing.task_id != item.task_id
                    or existing.executor_ref != executor_ref
                    or existing.spec_fingerprint != fingerprint
                    or _path_key(existing.project_root, strict=False)
                    != _path_key(project_root, strict=False)
                ):
                    raise FormalTaskViolation(
                        "ATTEMPT_DELIVERY_CONFLICT",
                        "formal attempt identity cannot change its direct Executor binding",
                        ErrorCode.CONFLICT,
                    )
                return False, existing
            canonical_root = str(Path(project_root).resolve(strict=True))
            active_projects = connection.execute(
                f"SELECT project_root FROM {_DIRECT_EXECUTOR_TABLE} WHERE state<>?",
                (FormalAttemptState.TERMINAL.value,),
            ).fetchall()
            if any(
                _path_key(row["project_root"], strict=False)
                == _path_key(canonical_root, strict=False)
                for row in active_projects
            ):
                raise FormalTaskViolation(
                    "EXECUTOR_PROJECT_BUSY",
                    "selected project already has an active formal mutation attempt",
                    ErrorCode.UNAVAILABLE,
                )
            connection.execute(
                f"""
                INSERT INTO {_DIRECT_EXECUTOR_TABLE} (
                    attempt_id, task_id, executor_ref, spec_fingerprint,
                    project_root, state, outcome, source_seq, accepted_at,
                    running_at, terminal_at, raw_status, summary, error,
                    before_tree, before_content, expected_tree, before_head,
                    protected_support_json,
                    governance_json, owner_id, lease_expires_at, cancel_requested
                ) VALUES (?, ?, ?, ?, ?, ?, NULL, 0, ?, NULL, NULL, ?, NULL,
                          NULL, ?, ?, NULL, ?, ?, ?, ?, ?, 0)
                """,
                (
                    item.attempt_id,
                    item.task_id,
                    executor_ref,
                    fingerprint,
                    canonical_root,
                    FormalAttemptState.ACCEPTED.value,
                    now,
                    FormalAttemptState.ACCEPTED.value,
                    before_tree,
                    before_content,
                    before_head,
                    json.dumps(dict(protected_support), sort_keys=True),
                    json.dumps(dict(governance), sort_keys=True),
                    owner_id,
                    _lease_expiry(now),
                ),
            )
            row = connection.execute(
                f"SELECT * FROM {_DIRECT_EXECUTOR_TABLE} WHERE attempt_id=?",
                (item.attempt_id,),
            ).fetchone()
            assert row is not None
            return True, self._from_row(row)

    def start(self, attempt_id: str, *, owner_id: str, now: str) -> _DirectAttempt:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                f"SELECT * FROM {_DIRECT_EXECUTOR_TABLE} WHERE attempt_id=?",
                (attempt_id,),
            ).fetchone()
            if row is None:
                raise FormalTaskViolation(
                    "ATTEMPT_NOT_FOUND",
                    "direct Executor attempt is unavailable",
                    ErrorCode.NOT_FOUND,
                )
            current = self._from_row(row)
            if current.state is FormalAttemptState.TERMINAL:
                return current
            if current.owner_id != owner_id:
                raise FormalTaskViolation(
                    "EXECUTOR_ATTEMPT_LEASE_MISMATCH",
                    "direct Executor attempt is owned by another process",
                    ErrorCode.UNAVAILABLE,
                )
            connection.execute(
                f"""
                UPDATE {_DIRECT_EXECUTOR_TABLE}
                   SET state=?, source_seq=1, running_at=COALESCE(running_at, ?),
                       raw_status=?, lease_expires_at=?
                 WHERE attempt_id=?
                """,
                (
                    FormalAttemptState.RUNNING.value,
                    now,
                    FormalAttemptState.RUNNING.value,
                    _lease_expiry(now),
                    attempt_id,
                ),
            )
            row = connection.execute(
                f"SELECT * FROM {_DIRECT_EXECUTOR_TABLE} WHERE attempt_id=?",
                (attempt_id,),
            ).fetchone()
            assert row is not None
            return self._from_row(row)

    def heartbeat(
        self, attempt_id: str, *, owner_id: str, now: str
    ) -> tuple[bool, bool]:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            changed = connection.execute(
                f"""
                UPDATE {_DIRECT_EXECUTOR_TABLE}
                   SET lease_expires_at=?
                 WHERE attempt_id=? AND owner_id=? AND state<>?
                """,
                (
                    _lease_expiry(now),
                    attempt_id,
                    owner_id,
                    FormalAttemptState.TERMINAL.value,
                ),
            ).rowcount
            row = connection.execute(
                f"SELECT cancel_requested FROM {_DIRECT_EXECUTOR_TABLE} "
                "WHERE attempt_id=? AND owner_id=? AND state<>?",
                (attempt_id, owner_id, FormalAttemptState.TERMINAL.value),
            ).fetchone()
        return changed == 1, row is not None and bool(row["cancel_requested"])

    def finish(
        self,
        attempt_id: str,
        *,
        owner_id: str | None,
        outcome: TerminalOutcome,
        raw_status: str,
        summary: str | None,
        error: str | None,
        now: str,
        require_owner: bool = True,
    ) -> _DirectAttempt:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                f"SELECT * FROM {_DIRECT_EXECUTOR_TABLE} WHERE attempt_id=?",
                (attempt_id,),
            ).fetchone()
            if row is None:
                raise FormalTaskViolation(
                    "ATTEMPT_NOT_FOUND",
                    "direct Executor attempt is unavailable",
                    ErrorCode.NOT_FOUND,
                )
            current = self._from_row(row)
            if current.state is FormalAttemptState.TERMINAL:
                return current
            if require_owner and current.owner_id != owner_id:
                raise FormalTaskViolation(
                    "EXECUTOR_ATTEMPT_LEASE_MISMATCH",
                    "direct Executor attempt is owned by another process",
                    ErrorCode.UNAVAILABLE,
                )
            connection.execute(
                f"""
                UPDATE {_DIRECT_EXECUTOR_TABLE}
                   SET state=?, outcome=?, source_seq=2, terminal_at=?,
                       raw_status=?, summary=?, error=?, owner_id=NULL,
                       lease_expires_at=NULL
                 WHERE attempt_id=? AND state<>?
                """,
                (
                    FormalAttemptState.TERMINAL.value,
                    outcome.value,
                    now,
                    raw_status,
                    summary,
                    error,
                    attempt_id,
                    FormalAttemptState.TERMINAL.value,
                ),
            )
            row = connection.execute(
                f"SELECT * FROM {_DIRECT_EXECUTOR_TABLE} WHERE attempt_id=?",
                (attempt_id,),
            ).fetchone()
            assert row is not None
            return self._from_row(row)

    def mark_cleanup_pending(self, attempt_id: str) -> _DirectAttempt:
        """Expose cleanup truth while preserving the business terminal outcome."""

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                f"SELECT * FROM {_DIRECT_EXECUTOR_TABLE} WHERE attempt_id=?",
                (attempt_id,),
            ).fetchone()
            if row is None:
                raise FormalTaskViolation(
                    "ATTEMPT_NOT_FOUND",
                    "direct Executor attempt is unavailable",
                    ErrorCode.NOT_FOUND,
                )
            current = self._from_row(row)
            suffix = "cleanup_pending"
            raw_status = current.raw_status
            if not raw_status.endswith(suffix):
                raw_status = f"{raw_status}_{suffix}"
            connection.execute(
                f"""
                UPDATE {_DIRECT_EXECUTOR_TABLE}
                   SET raw_status=?,
                       summary=COALESCE(summary, ?)
                 WHERE attempt_id=?
                """,
                (
                    raw_status,
                    "isolated project worktree cleanup remains pending",
                    attempt_id,
                ),
            )
            row = connection.execute(
                f"SELECT * FROM {_DIRECT_EXECUTOR_TABLE} WHERE attempt_id=?",
                (attempt_id,),
            ).fetchone()
            assert row is not None
            return self._from_row(row)

    def mark_cleanup_resolved(self, attempt_id: str) -> _DirectAttempt:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                f"SELECT * FROM {_DIRECT_EXECUTOR_TABLE} WHERE attempt_id=?",
                (attempt_id,),
            ).fetchone()
            if row is None:
                raise FormalTaskViolation(
                    "ATTEMPT_NOT_FOUND",
                    "direct Executor attempt is unavailable",
                    ErrorCode.NOT_FOUND,
                )
            current = self._from_row(row)
            suffix = "cleanup_pending"
            if current.raw_status.endswith(suffix):
                business_status = current.raw_status.removesuffix(suffix).rstrip("_")
                connection.execute(
                    f"""
                    UPDATE {_DIRECT_EXECUTOR_TABLE}
                       SET raw_status=?, summary=?
                     WHERE attempt_id=?
                    """,
                    (
                        f"{business_status}_cleanup_resolved",
                        "isolated project worktree cleanup resolved",
                        attempt_id,
                    ),
                )
            row = connection.execute(
                f"SELECT * FROM {_DIRECT_EXECUTOR_TABLE} WHERE attempt_id=?",
                (attempt_id,),
            ).fetchone()
            assert row is not None
            return self._from_row(row)

    def request_cancel(self, attempt_id: str) -> _DirectAttempt:
        with self._connect() as connection:
            connection.execute(
                f"""
                UPDATE {_DIRECT_EXECUTOR_TABLE}
                   SET cancel_requested=1
                 WHERE attempt_id=? AND state<>? AND raw_status<>'applying'
                """,
                (attempt_id, FormalAttemptState.TERMINAL.value),
            )
            row = connection.execute(
                f"SELECT * FROM {_DIRECT_EXECUTOR_TABLE} WHERE attempt_id=?",
                (attempt_id,),
            ).fetchone()
            if row is None:
                raise FormalTaskViolation(
                    "ATTEMPT_NOT_FOUND",
                    "direct Executor attempt is unavailable",
                    ErrorCode.NOT_FOUND,
                )
            return self._from_row(row)

    def reserve_completion(
        self,
        attempt_id: str,
        *,
        owner_id: str,
        expected_tree: str,
        now: str,
    ) -> tuple[bool, _DirectAttempt]:
        """Make completion win its race before any target patch is applied."""

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            changed = connection.execute(
                f"""
                UPDATE {_DIRECT_EXECUTOR_TABLE}
                   SET raw_status='applying', expected_tree=?, lease_expires_at=?
                 WHERE attempt_id=? AND owner_id=? AND state<>?
                       AND cancel_requested=0 AND raw_status<>'applying'
                """,
                (
                    expected_tree,
                    _lease_expiry(now),
                    attempt_id,
                    owner_id,
                    FormalAttemptState.TERMINAL.value,
                ),
            ).rowcount
            row = connection.execute(
                f"SELECT * FROM {_DIRECT_EXECUTOR_TABLE} WHERE attempt_id=?",
                (attempt_id,),
            ).fetchone()
            if row is None:
                raise FormalTaskViolation(
                    "ATTEMPT_NOT_FOUND",
                    "direct Executor attempt is unavailable",
                    ErrorCode.NOT_FOUND,
                )
            return changed == 1, self._from_row(row)

    def recover_expired(self, *, now: str) -> int:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                f"""
                SELECT * FROM {_DIRECT_EXECUTOR_TABLE}
                 WHERE state<>? AND lease_expires_at IS NOT NULL
                       AND lease_expires_at<=?
                """,
                (FormalAttemptState.TERMINAL.value, now),
            ).fetchall()
            for row in rows:
                record = self._from_row(row)
                outcome = TerminalOutcome.INTERRUPTED
                raw_status = "restart_interrupted"
                summary = None
                error = "EXECUTOR_PROCESS_RESTARTED"
                if record.raw_status == "applying":
                    outcome = TerminalOutcome.UNKNOWN
                    raw_status = "restart_apply_result_unknown"
                    error = "EXECUTOR_RESTART_APPLY_RESULT_UNKNOWN"
                    try:
                        root = Path(record.project_root).resolve(strict=True)
                        current_content = _project_content_fingerprint(root)
                        unchanged_authority = (
                            _git_head(root) == record.before_head
                            and _target_support_fingerprints(root)
                            == json.loads(record.protected_support_json)
                        )
                    except Exception:
                        unchanged_authority = False
                        current_content = None
                    if (
                        unchanged_authority
                        and record.expected_tree is not None
                        and current_content == record.expected_tree
                    ):
                        outcome = TerminalOutcome.COMPLETED
                        raw_status = "restart_apply_completed"
                        summary = (
                            "project change was durably observed after Executor restart"
                        )
                        error = None
                    elif (
                        unchanged_authority
                        and record.before_content is not None
                        and current_content == record.before_content
                    ):
                        outcome = TerminalOutcome.INTERRUPTED
                        raw_status = "restart_before_apply"
                        error = "EXECUTOR_PROCESS_RESTARTED"
                connection.execute(
                    f"""
                    UPDATE {_DIRECT_EXECUTOR_TABLE}
                       SET state=?, outcome=?, source_seq=2, terminal_at=?,
                           raw_status=?, summary=?, error=?, owner_id=NULL,
                           lease_expires_at=NULL
                     WHERE attempt_id=? AND state<>?
                    """,
                    (
                        FormalAttemptState.TERMINAL.value,
                        outcome.value,
                        now,
                        raw_status,
                        summary,
                        error,
                        record.attempt_id,
                        FormalAttemptState.TERMINAL.value,
                    ),
                )
        return len(rows)


def _text(payload: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


class _ReleaseOnce:
    """Keep resolver and carrier cleanup ownership safe across handoff failures."""

    def __init__(self, callback: Callable[[], None]) -> None:
        self._callback = callback
        self._released = False

    def __call__(self) -> None:
        if self._released:
            return
        self._released = True
        self._callback()


class DirectProjectCodeExecutorAdapter:
    """Durable D0 Executor that calls the project Code Agent without schedule.*.

    The formal Task Core remains the command/event/outbox authority.  This
    adapter owns only one exact attempt journal plus the direct Agent worker.
    Voice, response, round, browser and session lifecycles never call
    :meth:`cancel`; only a durable ``task.cancel`` outbox item may do so.
    """

    executor_id = FORMAL_PROJECT_EXECUTOR_ID

    def __init__(
        self,
        resolver: ProjectExecutionBindingResolver,
        database: str | os.PathLike[str],
        *,
        clock: Callable[[], str] = utc_now,
        heartbeat_interval: float = 1.0,
        cancel_timeout: float = 1.0,
        close_timeout: float = 5.0,
    ) -> None:
        if (
            isinstance(heartbeat_interval, bool)
            or not isinstance(heartbeat_interval, (int, float))
            or not math.isfinite(heartbeat_interval)
            or heartbeat_interval <= 0
        ):
            raise ValueError("heartbeat_interval must be positive")
        for field_name, value in (
            ("cancel_timeout", cancel_timeout),
            ("close_timeout", close_timeout),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value <= 0
                or value > _MAX_DIRECT_CLEANUP_TIMEOUT_SECONDS
            ):
                raise ValueError(
                    f"{field_name} must be positive and no greater than "
                    f"{_MAX_DIRECT_CLEANUP_TIMEOUT_SECONDS} seconds"
                )
        self._resolver = resolver
        self._journal = _DirectProjectAttemptJournal(database)
        self._clock = clock
        self._heartbeat_interval = float(heartbeat_interval)
        self._cancel_timeout = float(cancel_timeout)
        self._close_timeout = float(close_timeout)
        self._owner_id = f"d0-project-executor-{uuid.uuid4().hex}"
        self._running: dict[str, asyncio.Task[None]] = {}
        self._applying: set[str] = set()
        self._interruptions: dict[str, tuple[str, str]] = {}
        self._retained_worktree_cleanups: dict[str, tuple[Path, Path, Path]] = {}
        self._lifecycle_lock = asyncio.Lock()
        self._closed = False

    @property
    def database(self) -> str:
        return self._journal.database

    async def prepare_startup(self) -> int:
        """Resolve only expired process leases; active foreign work stays pending."""

        recovered = await asyncio.to_thread(
            self._journal.recover_expired,
            now=self._clock(),
        )
        attempts = await asyncio.to_thread(self._journal.all_attempts)
        for record in attempts:
            root = Path(record.project_root)
            parent, worktree = _attempt_worktree_paths(root, record.attempt_id)
            try:
                registered = await asyncio.to_thread(
                    _worktree_registered, root, worktree
                )
            except Exception:
                registered = False
                if worktree.exists() or parent.exists():
                    self._retained_worktree_cleanups[record.attempt_id] = (
                        root,
                        parent,
                        worktree,
                    )
                continue
            if not (worktree.exists() or parent.exists() or registered):
                if record.raw_status.endswith("cleanup_pending"):
                    await asyncio.to_thread(
                        self._journal.mark_cleanup_resolved,
                        record.attempt_id,
                    )
                continue
            try:
                await asyncio.to_thread(
                    _remove_attempt_worktree, root, parent, worktree
                )
            except Exception:
                self._retained_worktree_cleanups[record.attempt_id] = (
                    root,
                    parent,
                    worktree,
                )
                await asyncio.to_thread(
                    self._journal.mark_cleanup_pending,
                    record.attempt_id,
                )
            else:
                self._retained_worktree_cleanups.pop(record.attempt_id, None)
                await asyncio.to_thread(
                    self._journal.mark_cleanup_resolved,
                    record.attempt_id,
                )
        return recovered

    async def dispatch(self, item: PersistentOutboxItem) -> ExecutorDeliveryResult:
        async with self._lifecycle_lock:
            return await self._dispatch(item)

    async def _dispatch(self, item: PersistentOutboxItem) -> ExecutorDeliveryResult:
        self._require_item(item, expected_kind=OutboxKind.ATTEMPT_DISPATCH)
        if self._closed:
            raise FormalTaskViolation(
                "EXECUTOR_CAPABILITY_UNAVAILABLE",
                "direct project Executor is closed",
                ErrorCode.UNAVAILABLE,
            )
        context_path = item.spec.context.file_path
        if context_path is None:
            raise FormalTaskViolation(
                "EXECUTION_TARGET_NOT_BOUND",
                "direct project Executor requires a file context",
                ErrorCode.PERMISSION_DENIED,
            )
        root = Path(context_path).resolve(strict=True)
        if not root.is_dir() or _path_key(root) != _path_key(_git_root(root)):
            raise FormalTaskViolation(
                "EXECUTION_TARGET_NOT_BOUND",
                "selected project, Code Agent root, and Git root must match",
                ErrorCode.PERMISSION_DENIED,
            )
        await asyncio.to_thread(_reject_git_visible_symlinks, root)

        existing = await asyncio.to_thread(self._journal.get, item.attempt_id)
        if existing is not None:
            self._require_attempt_binding(existing, item, root)
            return self._delivery(existing, after_seq=item.source_seq)
        if len(self._running) >= _MAX_DIRECT_RUNNING_WORKERS:
            raise FormalTaskViolation(
                "EXECUTOR_CAPACITY_EXHAUSTED",
                "direct project Executor retained-worker capacity is exhausted",
                ErrorCode.UNAVAILABLE,
            )

        before_tree = await asyncio.to_thread(_project_tree_fingerprint, root)
        before_content = await asyncio.to_thread(_project_content_fingerprint, root)
        before_head = await asyncio.to_thread(_git_head, root)
        protected_support = await asyncio.to_thread(_target_support_fingerprints, root)
        governance = await asyncio.to_thread(_runtime_support_governance, root)
        binding = await self._resolver.resolve(item.spec, for_dispatch=True)
        release = (
            _ReleaseOnce(binding.context_release)
            if binding.context_release is not None
            else None
        )
        worker_owns_release = False
        worker: asyncio.Task[None] | None = None
        worker_started = asyncio.Event()
        try:
            binding.validate(item.spec, for_dispatch=True)
            assert binding.dispatch_fence is not None
            await binding.dispatch_fence()
            if (
                await asyncio.to_thread(_git_head, root) != before_head
                or await asyncio.to_thread(_project_tree_fingerprint, root)
                != before_tree
                or await asyncio.to_thread(_target_support_fingerprints, root)
                != protected_support
            ):
                raise FormalTaskViolation(
                    "EXECUTOR_INITIALIZATION_MUTATED_TARGET",
                    "formal Agent initialization changed the selected project",
                    ErrorCode.PERMISSION_DENIED,
                )
            await asyncio.to_thread(_reject_git_visible_symlinks, root)
            created, record = await asyncio.to_thread(
                self._journal.create,
                item=item,
                project_root=str(root),
                before_tree=before_tree,
                before_content=before_content,
                before_head=before_head,
                protected_support=protected_support,
                governance=governance,
                owner_id=self._owner_id,
                now=self._clock(),
            )
            if not created:
                self._require_attempt_binding(record, item, root)
                return self._delivery(record, after_seq=item.source_seq)
            record = await asyncio.to_thread(
                self._journal.start,
                item.attempt_id,
                owner_id=self._owner_id,
                now=self._clock(),
            )
            worker = asyncio.create_task(
                self._run_attempt(item, binding, release, worker_started),
                name=f"live-voice-d0-project-{item.attempt_id}",
            )
            self._running[item.attempt_id] = worker
            worker.add_done_callback(partial(self._settle_worker, item.attempt_id))
            worker_owns_release = True
            await worker_started.wait()
            current = await asyncio.to_thread(self._journal.get, item.attempt_id)
            assert current is not None
            return self._delivery(current, after_seq=item.source_seq)
        except asyncio.CancelledError:
            if worker is not None:
                self._interruptions[item.attempt_id] = (
                    "dispatch_interrupted",
                    "EXECUTOR_DISPATCH_INTERRUPTED",
                )
                worker.cancel()
                await asyncio.gather(worker, return_exceptions=True)
                if release is not None:
                    release()
            current = await asyncio.to_thread(self._journal.get, item.attempt_id)
            if (
                current is not None
                and current.state is not FormalAttemptState.TERMINAL
                and current.owner_id == self._owner_id
            ):
                await asyncio.to_thread(
                    self._journal.finish,
                    item.attempt_id,
                    owner_id=self._owner_id,
                    outcome=TerminalOutcome.INTERRUPTED,
                    raw_status="dispatch_interrupted",
                    summary=None,
                    error="EXECUTOR_DISPATCH_INTERRUPTED",
                    now=self._clock(),
                )
            raise
        except Exception:
            current = await asyncio.to_thread(self._journal.get, item.attempt_id)
            if (
                current is not None
                and current.state is not FormalAttemptState.TERMINAL
                and current.owner_id == self._owner_id
            ):
                await asyncio.to_thread(
                    self._journal.finish,
                    item.attempt_id,
                    owner_id=self._owner_id,
                    outcome=TerminalOutcome.FAILED,
                    raw_status="dispatch_failed",
                    summary=None,
                    error="EXECUTOR_DISPATCH_FAILED",
                    now=self._clock(),
                )
            raise
        finally:
            if not worker_owns_release and release is not None:
                release()

    async def _run_attempt(
        self,
        item: PersistentOutboxItem,
        binding: ProjectExecutionBinding,
        release: _ReleaseOnce | None,
        started: asyncio.Event,
    ) -> None:
        heartbeat: asyncio.Task[None] | None = None
        worktree_parent: Path | None = None
        worktree: Path | None = None
        completion_pending = False
        try:
            heartbeat = asyncio.create_task(
                self._heartbeat(item.attempt_id),
                name=f"live-voice-d0-heartbeat-{item.attempt_id}",
            )
            record = await asyncio.to_thread(self._journal.get, item.attempt_id)
            assert record is not None
            target_root = Path(record.project_root)
            created_parent, created_worktree = await asyncio.to_thread(
                _create_attempt_worktree,
                target_root,
                item.attempt_id,
                record.before_head,
            )
            worktree_parent = created_parent
            worktree = created_worktree
            await asyncio.to_thread(
                _seed_attempt_worktree,
                target_root,
                created_worktree,
                record.before_content,
            )
            await asyncio.to_thread(
                _reject_git_visible_symlinks, created_worktree
            )
            if await asyncio.to_thread(
                _git_head, created_worktree
            ) != record.before_head or await asyncio.to_thread(
                _target_support_fingerprints, created_worktree
            ) != json.loads(record.protected_support_json):
                raise RuntimeError("PROJECT_WORKTREE_BASELINE_MISMATCH")
            request = AgentRequest(
                request_id=f"{_DIRECT_EXECUTOR_REF_PREFIX}{item.attempt_id}",
                channel_id="formal-task-core",
                session_id=f"formal-task-{item.attempt_id}",
                params={
                    "query": item.spec.instruction,
                    "mode": "code",
                    "project_dir": str(created_worktree),
                    "cwd": str(created_worktree),
                    "workspace_dir": str(
                        get_agent_workspace_dir().resolve(strict=False)
                    ),
                    "trusted_dirs": [str(created_worktree)],
                    "supports_user_interaction": False,
                    "source": "live_voice.formal_task.d0",
                },
                is_stream=True,
                metadata={
                    "enable_memory": False,
                    "skip_a2ui": True,
                    "background_task": True,
                    "project_task_file_tools_only": True,
                    "formal_task_id": item.task_id,
                    "formal_attempt_id": item.attempt_id,
                },
                enable_memory=False,
            )
            terminal = False
            agent_error = False
            started.set()
            with forbid_background_project_shell_commands():
                async for (
                    chunk
                ) in binding.project_executor.process_background_code_task_stream(
                    request
                ):
                    terminal = terminal or chunk.is_complete
                    payload = chunk.payload if isinstance(chunk.payload, dict) else None
                    if payload and payload.get("event_type") == "chat.error":
                        agent_error = True
            if agent_error:
                raise RuntimeError("PROJECT_EXECUTOR_AGENT_ERROR")
            if not terminal:
                raise RuntimeError("PROJECT_EXECUTOR_INCOMPLETE")
            if (
                await asyncio.to_thread(_git_head, created_worktree)
                != record.before_head
            ):
                raise RuntimeError("FORBIDDEN_GIT_HEAD_CHANGE")
            await asyncio.to_thread(_reject_git_visible_symlinks, created_worktree)
            before_support = json.loads(record.protected_support_json)
            if (
                await asyncio.to_thread(_target_support_fingerprints, created_worktree)
                != before_support
            ):
                raise RuntimeError("RUNTIME_SUPPORT_PATH_MUTATED")
            patch, expected_tree, changed_paths = await asyncio.to_thread(
                _attempt_patch, created_worktree
            )
            interruption = self._interruptions.get(item.attempt_id)
            refreshed = await asyncio.to_thread(self._journal.get, item.attempt_id)
            assert refreshed is not None
            if interruption is not None or refreshed.cancel_requested:
                if interruption is None:
                    interruption = ("cancelled", "TASK_CANCEL_ACKNOWLEDGED")
                raw_status, error = interruption
                await asyncio.to_thread(
                    self._journal.finish,
                    item.attempt_id,
                    owner_id=self._owner_id,
                    outcome=TerminalOutcome.INTERRUPTED,
                    raw_status=raw_status,
                    summary=None,
                    error=error,
                    now=self._clock(),
                )
                return
            reserved, completion_record = await asyncio.to_thread(
                self._journal.reserve_completion,
                item.attempt_id,
                owner_id=self._owner_id,
                expected_tree=expected_tree,
                now=self._clock(),
            )
            if not reserved:
                if completion_record.state is FormalAttemptState.TERMINAL:
                    return
                await asyncio.to_thread(
                    self._journal.finish,
                    item.attempt_id,
                    owner_id=self._owner_id,
                    outcome=TerminalOutcome.CANCELLED,
                    raw_status="cancelled",
                    summary=None,
                    error="TASK_CANCEL_ACKNOWLEDGED",
                    now=self._clock(),
                )
                return
            self._applying.add(item.attempt_id)
            try:
                await asyncio.to_thread(
                    _apply_attempt_patch,
                    target_root,
                    patch,
                    source_worktree=created_worktree,
                    changed_paths=changed_paths,
                    expected_tree=expected_tree,
                    before_tree=record.before_tree,
                    before_head=record.before_head,
                    protected_support=before_support,
                )
            finally:
                self._applying.discard(item.attempt_id)
            completion_pending = True
        except asyncio.CancelledError:
            interruption = self._interruptions.get(item.attempt_id)
            raw_status, error = (
                interruption
                if interruption is not None
                else ("cancelled", "TASK_CANCEL_ACKNOWLEDGED")
            )
            user_cancel = error.startswith("TASK_CANCEL_ACKNOWLEDGED")
            await asyncio.to_thread(
                self._journal.finish,
                item.attempt_id,
                owner_id=self._owner_id,
                outcome=(
                    TerminalOutcome.CANCELLED
                    if user_cancel
                    else TerminalOutcome.INTERRUPTED
                ),
                raw_status=raw_status,
                summary=None,
                error=error,
                now=self._clock(),
            )
            raise
        except Exception as error:  # noqa: BLE001 -- persist stable terminal truth
            code = (
                error.reason
                if isinstance(error, FormalTaskViolation)
                else str(error)
            )
            if code not in {
                "PROJECT_EXECUTOR_AGENT_ERROR",
                "PROJECT_EXECUTOR_AGENT_CLEANUP_FAILED",
                "PROJECT_EXECUTOR_AGENT_SETUP_MUTATED_TARGET",
                "PROJECT_EXECUTOR_AGENT_POST_TERMINAL_MUTATION",
                "PROJECT_EXECUTOR_AGENT_CLEANUP_MUTATED_TARGET",
                "PROJECT_EXECUTOR_INCOMPLETE",
                "PROJECT_CHANGE_ROLLBACK_FAILED",
                "FORBIDDEN_GIT_HEAD_CHANGE",
                "RUNTIME_SUPPORT_PATH_MUTATED",
                "NO_EFFECTIVE_TARGET_CHANGE",
                "PROJECT_WORKTREE_UNAVAILABLE",
                "PROJECT_WORKTREE_BASELINE_MISMATCH",
                "PROJECT_CHANGE_CAPTURE_FAILED",
                "PROJECT_CHANGE_APPLICATION_FAILED",
                "PROJECT_CHANGE_ATTRIBUTION_FAILED",
                "EXECUTION_TARGET_CHANGED_DURING_ATTEMPT",
                "PROJECT_WORKTREE_CLEANUP_PENDING",
                "PROJECT_WORKTREE_CLEANUP_TARGET_UNSAFE",
                "EXECUTION_TARGET_SYMLINK_UNSAFE",
            }:
                code = "PROJECT_EXECUTOR_FAILED"
            await asyncio.to_thread(
                self._journal.finish,
                item.attempt_id,
                owner_id=self._owner_id,
                outcome=TerminalOutcome.FAILED,
                raw_status="failed",
                summary=None,
                error=code,
                now=self._clock(),
            )
        finally:
            started.set()
            if heartbeat is not None:
                heartbeat.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await heartbeat
            if worktree_parent is not None and worktree is not None:
                try:
                    await asyncio.to_thread(
                        _remove_attempt_worktree,
                        Path(binding.effective_execution_root),
                        worktree_parent,
                        worktree,
                    )
                except Exception:
                    self._retained_worktree_cleanups[item.attempt_id] = (
                        Path(binding.effective_execution_root),
                        worktree_parent,
                        worktree,
                    )
                    if completion_pending:
                        await asyncio.to_thread(
                            self._journal.finish,
                            item.attempt_id,
                            owner_id=self._owner_id,
                            outcome=TerminalOutcome.COMPLETED,
                            raw_status="completed",
                            summary=(
                                "project Code Agent completed with a Git-visible "
                                "target change"
                            ),
                            error=None,
                            now=self._clock(),
                        )
                        completion_pending = False
                    await asyncio.to_thread(
                        self._journal.mark_cleanup_pending,
                        item.attempt_id,
                    )
                else:
                    self._retained_worktree_cleanups.pop(item.attempt_id, None)
            if completion_pending:
                await asyncio.to_thread(
                    self._journal.finish,
                    item.attempt_id,
                    owner_id=self._owner_id,
                    outcome=TerminalOutcome.COMPLETED,
                    raw_status="completed",
                    summary="project Code Agent completed with a Git-visible target change",
                    error=None,
                    now=self._clock(),
                )
            if release is not None:
                release()

    async def _heartbeat(self, attempt_id: str) -> None:
        try:
            while True:
                await asyncio.sleep(self._heartbeat_interval)
                active, cancel_requested = await asyncio.to_thread(
                    self._journal.heartbeat,
                    attempt_id,
                    owner_id=self._owner_id,
                    now=self._clock(),
                )
                if not active:
                    return
                if cancel_requested:
                    self._interruptions.setdefault(
                        attempt_id,
                        ("cancelled", "TASK_CANCEL_ACKNOWLEDGED"),
                    )
                    task = self._running.get(attempt_id)
                    if task is not None and not task.done() and task.cancelling() == 0:
                        task.cancel()
                    return
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 -- interrupt on lost durable lease
            self._interruptions.setdefault(
                attempt_id,
                ("heartbeat_interrupted", "EXECUTOR_HEARTBEAT_FAILED"),
            )
            task = self._running.get(attempt_id)
            if task is not None and not task.done():
                task.cancel()

    def _settle_worker(self, attempt_id: str, task: asyncio.Task[None]) -> None:
        if self._running.get(attempt_id) is task:
            self._running.pop(attempt_id, None)
        self._interruptions.pop(attempt_id, None)
        with contextlib.suppress(asyncio.CancelledError, Exception):
            task.result()

    async def cancel(self, item: PersistentOutboxItem) -> ExecutorDeliveryResult:
        self._require_item(item, expected_kind=OutboxKind.ATTEMPT_CANCEL)
        if item.executor_ref != f"{_DIRECT_EXECUTOR_REF_PREFIX}{item.attempt_id}":
            raise FormalTaskViolation(
                "EXECUTOR_REFERENCE_MISMATCH",
                "task.cancel must bind the original direct Executor reference",
                ErrorCode.PROTOCOL_VIOLATION,
            )
        record = await asyncio.to_thread(self._journal.get, item.attempt_id)
        if record is None:
            raise FormalTaskViolation(
                "ATTEMPT_NOT_FOUND",
                "direct Executor attempt is unavailable",
                ErrorCode.NOT_FOUND,
            )
        self._require_attempt_binding(
            record, item, Path(record.project_root).resolve(strict=True)
        )
        record = await asyncio.to_thread(self._journal.request_cancel, item.attempt_id)
        if record.state is FormalAttemptState.TERMINAL:
            return self._delivery(record, after_seq=item.source_seq)
        task = self._running.get(item.attempt_id)
        if task is None:
            recovered = await asyncio.to_thread(
                self._journal.recover_expired, now=self._clock()
            )
            refreshed = await asyncio.to_thread(self._journal.get, item.attempt_id)
            assert refreshed is not None
            if recovered == 0 and refreshed.state is not FormalAttemptState.TERMINAL:
                raise FormalTaskViolation(
                    "EXECUTOR_CANCEL_PENDING",
                    "direct Executor cancellation awaits its active process lease",
                    ErrorCode.UNAVAILABLE,
                )
            return self._delivery(refreshed, after_seq=item.source_seq)
        if record.raw_status == "applying":
            done, _ = await asyncio.wait({task}, timeout=self._cancel_timeout)
            if not done:
                raise FormalTaskViolation(
                    "EXECUTOR_CANCEL_PENDING",
                    "completion won the exact cancel race and is still settling",
                    ErrorCode.UNAVAILABLE,
                )
            refreshed = await asyncio.to_thread(self._journal.get, item.attempt_id)
            assert refreshed is not None
            return self._delivery(refreshed, after_seq=item.source_seq)
        self._interruptions.setdefault(
            item.attempt_id,
            ("cancelled", "TASK_CANCEL_ACKNOWLEDGED"),
        )
        if not task.done() and task.cancelling() == 0:
            task.cancel()
        done, pending = await asyncio.wait({task}, timeout=self._cancel_timeout)
        if pending:
            await asyncio.to_thread(
                self._journal.finish,
                item.attempt_id,
                owner_id=self._owner_id,
                outcome=TerminalOutcome.CANCELLED,
                raw_status="cancelled_cleanup_pending",
                summary=None,
                error="TASK_CANCEL_ACKNOWLEDGED_CLEANUP_PENDING",
                now=self._clock(),
            )
        elif done:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                task.result()
        refreshed = await asyncio.to_thread(self._journal.get, item.attempt_id)
        assert refreshed is not None
        return self._delivery(refreshed, after_seq=item.source_seq)

    async def status(
        self,
        task: PersistentTaskRecord,
        attempt: PersistentAttemptRecord,
    ) -> ExecutorDeliveryResult | ExecutorObservation:
        if (
            attempt.executor_id != self.executor_id
            or task.attempt_id != attempt.attempt_id
        ):
            raise FormalTaskViolation(
                "EXECUTOR_BINDING_MISMATCH",
                "reconciliation must query the exact original formal attempt",
                ErrorCode.PROTOCOL_VIOLATION,
            )
        record = await asyncio.to_thread(self._journal.get, attempt.attempt_id)
        if record is None:
            return self._resolution_observation(
                task.task_id,
                attempt.attempt_id,
                attempt.executor_ref,
                ExecutorResolution.LOST,
                "DIRECT_EXECUTOR_ATTEMPT_NOT_FOUND",
            )
        self._require_record_binding(record, task, attempt)
        if (
            record.state is not FormalAttemptState.TERMINAL
            and attempt.attempt_id not in self._running
        ):
            await asyncio.to_thread(self._journal.recover_expired, now=self._clock())
            record = await asyncio.to_thread(self._journal.get, attempt.attempt_id)
            assert record is not None
        return self._delivery(record, after_seq=attempt.source_seq)

    def retained_cleanup_attempt_ids(self) -> tuple[str, ...]:
        """Expose bounded cleanup truth without leaking temporary paths."""

        return tuple(sorted(self._retained_worktree_cleanups))

    async def close(self, *, interrupt_running: bool = True) -> None:
        self._closed = True
        applying: set[str] = set()
        async with self._lifecycle_lock:
            tasks = list(self._running.items())
            for attempt_id, task in tasks:
                record = await asyncio.to_thread(self._journal.get, attempt_id)
                if attempt_id in self._applying or (
                    record is not None and record.raw_status == "applying"
                ):
                    applying.add(attempt_id)
                    continue
                if interrupt_running:
                    self._interruptions[attempt_id] = (
                        "interrupted",
                        "EXECUTOR_SHUTDOWN_INTERRUPTED",
                    )
                    if not task.done() and task.cancelling() == 0:
                        task.cancel()
        applying_tasks = {task for attempt_id, task in tasks if attempt_id in applying}
        if applying_tasks:
            done, pending = await asyncio.wait(
                applying_tasks,
                timeout=self._close_timeout,
            )
            for task in done:
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    task.result()
            if pending:
                # Applying a staged patch is intentionally not cancelled: a
                # worker thread or Git subprocess cannot be stopped safely in
                # process.  The owner therefore remains cleanup-pending and a
                # later close retry must observe terminal apply before it can
                # report success.  This bounds shutdown without permitting a
                # successful close followed by a late project mutation.
                raise FormalTaskViolation(
                    "EXECUTOR_CLOSE_CLEANUP_PENDING",
                    "project patch apply did not settle within the close budget",
                    ErrorCode.UNAVAILABLE,
                )
        non_applying_tasks = {
            task for attempt_id, task in tasks if attempt_id not in applying
        }
        if non_applying_tasks:
            _done, pending = await asyncio.wait(
                non_applying_tasks,
                timeout=self._close_timeout,
            )
            pending_tasks = {task for task in pending}
            for attempt_id, task in tasks:
                if task not in pending_tasks or attempt_id in applying:
                    continue
                current = await asyncio.to_thread(self._journal.get, attempt_id)
                if (
                    current is not None
                    and current.state is not FormalAttemptState.TERMINAL
                    and current.owner_id == self._owner_id
                ):
                    await asyncio.to_thread(
                        self._journal.finish,
                        attempt_id,
                        owner_id=self._owner_id,
                        outcome=TerminalOutcome.INTERRUPTED,
                        raw_status="interrupted_cleanup_pending",
                        summary=None,
                        error="EXECUTOR_SHUTDOWN_INTERRUPTED_CLEANUP_PENDING",
                        now=self._clock(),
                    )
        cleanup_failures: list[str] = []
        for attempt_id, cleanup in tuple(self._retained_worktree_cleanups.items()):
            try:
                await asyncio.to_thread(_remove_attempt_worktree, *cleanup)
            except Exception:
                cleanup_failures.append(attempt_id)
            else:
                self._retained_worktree_cleanups.pop(attempt_id, None)
                await asyncio.to_thread(
                    self._journal.mark_cleanup_resolved,
                    attempt_id,
                )
        if cleanup_failures:
            raise RuntimeError("PROJECT_WORKTREE_CLEANUP_PENDING")

    @staticmethod
    def _require_item(item: PersistentOutboxItem, *, expected_kind: OutboxKind) -> None:
        if item.spec.executor_id != FORMAL_PROJECT_EXECUTOR_ID:
            raise FormalTaskViolation(
                "EXECUTOR_BINDING_MISMATCH",
                "outbox item targets a different Executor",
                ErrorCode.PROTOCOL_VIOLATION,
            )
        if item.kind is not expected_kind:
            raise FormalTaskViolation(
                "EXECUTOR_OPERATION_MISMATCH",
                "direct Executor operation does not match the durable outbox item",
                ErrorCode.PROTOCOL_VIOLATION,
            )

    @staticmethod
    def _require_attempt_binding(
        record: _DirectAttempt,
        item: PersistentOutboxItem,
        root: Path,
    ) -> None:
        if (
            record.task_id != item.task_id
            or record.attempt_id != item.attempt_id
            or record.executor_ref != f"{_DIRECT_EXECUTOR_REF_PREFIX}{item.attempt_id}"
            or record.spec_fingerprint != item.spec.fingerprint_bytes()
            or _path_key(record.project_root, strict=False)
            != _path_key(root, strict=False)
        ):
            raise FormalTaskViolation(
                "ATTEMPT_DELIVERY_CONFLICT",
                "direct Executor attempt does not match the durable formal binding",
                ErrorCode.CONFLICT,
            )

    @staticmethod
    def _require_record_binding(
        record: _DirectAttempt,
        task: PersistentTaskRecord,
        attempt: PersistentAttemptRecord,
    ) -> None:
        if (
            record.task_id != task.task_id
            or record.attempt_id != attempt.attempt_id
            or record.executor_ref != attempt.executor_ref
            or record.spec_fingerprint != task.spec.fingerprint_bytes()
        ):
            raise FormalTaskViolation(
                "EXECUTOR_BINDING_MISMATCH",
                "direct Executor journal does not bind the original formal attempt",
                ErrorCode.PROTOCOL_VIOLATION,
            )

    def _delivery(
        self, record: _DirectAttempt, *, after_seq: int
    ) -> ExecutorDeliveryResult:
        observations = []
        lifecycle: tuple[
            tuple[FormalAttemptState, TerminalOutcome | None, str], ...
        ] = (
            (FormalAttemptState.ACCEPTED, None, record.accepted_at),
            (
                FormalAttemptState.RUNNING,
                None,
                record.running_at or record.accepted_at,
            ),
            (
                FormalAttemptState.TERMINAL,
                record.outcome,
                record.terminal_at or record.running_at or record.accepted_at,
            ),
        )
        for seq, (state, outcome, occurred_at) in enumerate(lifecycle):
            if seq <= after_seq or seq > record.source_seq:
                continue
            observations.append(
                ExecutorObservation(
                    resolution=ExecutorResolution.KNOWN,
                    executor_id=self.executor_id,
                    executor_ref=record.executor_ref,
                    task_id=record.task_id,
                    attempt_id=record.attempt_id,
                    source_event_id=(
                        f"{record.executor_ref}:formal-lifecycle:{seq}:"
                        f"{state.value}:{'' if outcome is None else outcome.value}"
                    ),
                    source_seq=seq,
                    attempt_state=state,
                    attempt_outcome=outcome,
                    occurred_at=occurred_at,
                    raw_status=(
                        state.value if seq < record.source_seq else record.raw_status
                    ),
                    summary=(record.summary if seq == record.source_seq else None),
                    error=(record.error if seq == record.source_seq else None),
                )
            )
        return ExecutorDeliveryResult(record.executor_ref, tuple(observations))

    def _resolution_observation(
        self,
        task_id: str,
        attempt_id: str,
        executor_ref: str | None,
        resolution: ExecutorResolution,
        error: str,
    ) -> ExecutorObservation:
        return ExecutorObservation(
            resolution=resolution,
            executor_id=self.executor_id,
            executor_ref=executor_ref,
            task_id=task_id,
            attempt_id=attempt_id,
            source_event_id=None,
            source_seq=None,
            attempt_state=None,
            attempt_outcome=None,
            occurred_at=self._clock(),
            raw_status=None,
            error=error,
        )


class ProjectCodeExecutorAdapter:
    """Translate exact formal attempt IDs to legacy project-bound executions."""

    executor_id = FORMAL_PROJECT_EXECUTOR_ID

    def __init__(self, resolver: ProjectExecutionBindingResolver) -> None:
        self._resolver = resolver

    async def dispatch(self, item: PersistentOutboxItem) -> ExecutorDeliveryResult:
        self._require_item(item)
        binding = await self._resolver.resolve(item.spec, for_dispatch=True)
        release = (
            _ReleaseOnce(binding.context_release)
            if binding.context_release is not None
            else None
        )
        carrier_owns_release = False
        try:
            binding.validate(item.spec, for_dispatch=True)
            if binding.service is None:
                raise FormalTaskViolation(
                    "LEGACY_EXECUTOR_UNAVAILABLE",
                    "legacy schedule carrier is unavailable",
                    ErrorCode.CAPABILITY_UNAVAILABLE,
                )
            assert binding.dispatch_fence is not None
            await binding.dispatch_fence()
            payload = await binding.service.run_task(
                item.spec.instruction,
                binding.model,
                PROJECT_CODE_PIPELINE,
                execution_agent=binding.execution_agent,
                project_executor=binding.project_executor,
                effective_execution_root=binding.effective_execution_root,
                context_release=release,
                execution_target=dict(binding.execution_target),
                owner_scope=dict(binding.owner_scope),
                origin_namespace="live_voice",
                idempotency_key=item.attempt_id,
                model_intent=binding.model_identity,
            )
            task_id = _text(payload, "task_id")
            if task_id is None:
                raise self._delivery_error(payload)
            carrier_owns_release = True
        finally:
            if not carrier_owns_release and release is not None:
                release()
        try:
            self._validate_carrier_projection(
                payload,
                binding,
                task_id,
                item.attempt_id,
                require_provenance=False,
            )
            persisted = await binding.service.get_scheduled_task_status(
                task_id,
                requester_owner_scope=dict(binding.owner_scope),
                requester_execution_target=dict(binding.execution_target),
            )
            self._validate_carrier_projection(
                persisted,
                binding,
                task_id,
                item.attempt_id,
                require_provenance=True,
            )
            dispatch_result = self._known_result(
                item=item,
                executor_ref=task_id,
                payload=payload,
            )
            persisted_result = self._known_result(
                item=item,
                executor_ref=task_id,
                payload=persisted,
            )
            return max(
                (persisted_result, dispatch_result),
                key=lambda result: len(result.observations),
            )
        except FormalTaskViolation as error:
            raise self._result_unknown(error) from error

    async def cancel(self, item: PersistentOutboxItem) -> ExecutorDeliveryResult:
        self._require_item(item)
        if item.executor_ref is None:
            raise FormalTaskViolation(
                "EXECUTOR_REFERENCE_REQUIRED",
                "formal cancellation requires the bound original executor reference",
                ErrorCode.PROTOCOL_VIOLATION,
            )
        binding = await self._resolver.resolve(item.spec, for_dispatch=False)
        release = (
            _ReleaseOnce(binding.context_release)
            if binding.context_release is not None
            else None
        )
        try:
            return await self._cancel_bound(item, binding)
        finally:
            if release is not None:
                release()

    async def _cancel_bound(
        self,
        item: PersistentOutboxItem,
        binding: ProjectExecutionBinding,
    ) -> ExecutorDeliveryResult:
        assert item.executor_ref is not None
        binding.validate(item.spec, for_dispatch=False)
        if binding.service is None:
            raise FormalTaskViolation(
                "LEGACY_EXECUTOR_UNAVAILABLE",
                "legacy schedule carrier is unavailable",
                ErrorCode.CAPABILITY_UNAVAILABLE,
            )
        payload = await binding.service.cancel_scheduled_task(
            item.executor_ref,
            requester_owner_scope=dict(binding.owner_scope),
            requester_execution_target=dict(binding.execution_target),
        )
        if payload.get("error") is not None:
            payload = await binding.service.get_scheduled_task_status(
                item.executor_ref,
                requester_owner_scope=dict(binding.owner_scope),
                requester_execution_target=dict(binding.execution_target),
            )
        try:
            self._validate_carrier_projection(
                payload,
                binding,
                item.executor_ref,
                item.attempt_id,
                require_provenance=True,
            )
            return self._known_result(
                item=item,
                executor_ref=item.executor_ref,
                payload=payload,
            )
        except FormalTaskViolation as error:
            raise self._result_unknown(error) from error

    async def status(
        self,
        task: PersistentTaskRecord,
        attempt: PersistentAttemptRecord,
    ) -> ExecutorDeliveryResult | ExecutorObservation:
        if (
            attempt.executor_id != self.executor_id
            or task.attempt_id != attempt.attempt_id
        ):
            raise FormalTaskViolation(
                "EXECUTOR_BINDING_MISMATCH",
                "reconciliation must query the exact original formal attempt",
                ErrorCode.PROTOCOL_VIOLATION,
            )
        if attempt.executor_ref is None:
            return self._resolution_observation(
                task.task_id,
                attempt.attempt_id,
                None,
                ExecutorResolution.UNAVAILABLE,
                "EXECUTOR_REFERENCE_NOT_BOUND",
            )
        binding = await self._resolver.resolve(task.spec, for_dispatch=False)
        release = (
            _ReleaseOnce(binding.context_release)
            if binding.context_release is not None
            else None
        )
        try:
            return await self._status_bound(task, attempt, binding)
        finally:
            if release is not None:
                release()

    async def _status_bound(
        self,
        task: PersistentTaskRecord,
        attempt: PersistentAttemptRecord,
        binding: ProjectExecutionBinding,
    ) -> ExecutorDeliveryResult | ExecutorObservation:
        assert attempt.executor_ref is not None
        binding.validate(task.spec, for_dispatch=False)
        if binding.service is None:
            raise FormalTaskViolation(
                "LEGACY_EXECUTOR_UNAVAILABLE",
                "legacy schedule carrier is unavailable",
                ErrorCode.CAPABILITY_UNAVAILABLE,
            )
        payload = await binding.service.get_scheduled_task_status(
            attempt.executor_ref,
            requester_owner_scope=dict(binding.owner_scope),
            requester_execution_target=dict(binding.execution_target),
        )
        code = _text(payload, "code")
        if _text(payload, "task_id") != attempt.executor_ref:
            raise FormalTaskViolation(
                "LEGACY_EXECUTOR_REFERENCE_MISMATCH",
                "legacy status response does not identify the original attempt",
                ErrorCode.PROTOCOL_VIOLATION,
            )
        if code == "TASK_NOT_FOUND":
            return self._resolution_observation(
                task.task_id,
                attempt.attempt_id,
                attempt.executor_ref,
                ExecutorResolution.LOST,
                code,
            )
        if payload.get("error") is not None:
            if code in {"TASK_SCOPE_MISMATCH", "TASK_PROJECT_MISMATCH"}:
                raise FormalTaskViolation(
                    "LEGACY_EXECUTOR_ACCESS_MISMATCH",
                    "trusted ED binding no longer matches the original legacy attempt",
                    ErrorCode.PROTOCOL_VIOLATION,
                )
            return self._resolution_observation(
                task.task_id,
                attempt.attempt_id,
                attempt.executor_ref,
                ExecutorResolution.UNAVAILABLE,
                code or "LEGACY_EXECUTOR_STATUS_UNAVAILABLE",
            )
        self._validate_carrier_projection(
            payload,
            binding,
            attempt.executor_ref,
            attempt.attempt_id,
            require_provenance=True,
        )
        return self._known_result_for_attempt(
            task.task_id,
            attempt.attempt_id,
            attempt.executor_ref,
            attempt.source_seq,
            payload,
        )

    @staticmethod
    def _result_unknown(error: FormalTaskViolation) -> FormalTaskViolation:
        return FormalTaskViolation(
            error.reason,
            f"legacy attempt exists but its result cannot be accepted: {error}",
            ErrorCode.RESULT_UNKNOWN,
        )

    def _require_item(self, item: PersistentOutboxItem) -> None:
        if item.spec.executor_id != self.executor_id:
            raise FormalTaskViolation(
                "EXECUTOR_BINDING_MISMATCH",
                "outbox item targets a different Executor",
                ErrorCode.PROTOCOL_VIOLATION,
            )

    @staticmethod
    def _delivery_error(payload: Mapping[str, Any]) -> FormalTaskViolation:
        code = _text(payload, "code")
        message = (
            _text(payload, "error", "message")
            or "legacy project Executor rejected delivery"
        )
        if code in {
            "EXECUTION_TARGET_NOT_BOUND",
            "UNSUPPORTED_PROJECT_TASK_CONSTRAINT",
            "IDEMPOTENCY_CONFLICT",
        }:
            error_code = ErrorCode.PERMISSION_DENIED
        else:
            error_code = ErrorCode.UNAVAILABLE
        return FormalTaskViolation(
            code or "EXECUTOR_DELIVERY_UNAVAILABLE", message, error_code
        )

    @staticmethod
    def _validate_carrier_projection(
        payload: Mapping[str, Any],
        binding: ProjectExecutionBinding,
        executor_ref: str,
        attempt_id: str,
        *,
        require_provenance: bool,
    ) -> None:
        if _text(payload, "task_id") != executor_ref:
            raise FormalTaskViolation(
                "LEGACY_EXECUTOR_REFERENCE_MISMATCH",
                "legacy carrier returned a different task reference",
                ErrorCode.PROTOCOL_VIOLATION,
            )
        target = payload.get("execution_target")
        contract = payload.get("execution_contract")
        if (
            not isinstance(target, Mapping)
            or set(target) != _EXECUTION_TARGET_FIELDS
            or _path_key(str(target.get("project_dir", "")), strict=False)
            != _path_key(binding.effective_execution_root, strict=False)
        ):
            raise FormalTaskViolation(
                "EXECUTION_TARGET_MISMATCH",
                "legacy carrier did not preserve the exact project target",
                ErrorCode.PROTOCOL_VIOLATION,
            )
        if contract != _expected_contract(binding.effective_execution_root):
            raise FormalTaskViolation(
                "EXECUTION_CONTRACT_MISMATCH",
                "legacy carrier did not preserve the bounded project contract",
                ErrorCode.PROTOCOL_VIOLATION,
            )
        assert isinstance(target, Mapping)
        if target.get("project_id") != binding.execution_target.get("project_id"):
            raise FormalTaskViolation(
                "EXECUTION_TARGET_MISMATCH",
                "legacy carrier returned a different project identity",
                ErrorCode.PROTOCOL_VIOLATION,
            )
        if any(
            target.get(field) != binding.execution_target.get(field)
            for field in ("origin_session_id", "origin_channel_id")
        ):
            raise FormalTaskViolation(
                "EXECUTION_TARGET_MISMATCH",
                "legacy carrier returned different origin target facts",
                ErrorCode.PROTOCOL_VIOLATION,
            )
        if require_provenance:
            provenance = payload.get("provenance")
            if (
                not isinstance(provenance, Mapping)
                or provenance.get("owner_scope") != dict(binding.owner_scope)
                or provenance.get("origin_namespace") != "live_voice"
                or provenance.get("idempotency_key") != attempt_id
                or provenance.get("legacy_unscoped") is not False
                or provenance.get("access") != "authorized"
            ):
                raise FormalTaskViolation(
                    "EXECUTOR_PROVENANCE_MISMATCH",
                    "legacy carrier did not preserve the formal attempt provenance",
                    ErrorCode.PROTOCOL_VIOLATION,
                )

    def _known_result(
        self,
        *,
        item: PersistentOutboxItem,
        executor_ref: str,
        payload: Mapping[str, Any],
    ) -> ExecutorDeliveryResult:
        return self._known_result_for_attempt(
            item.task_id,
            item.attempt_id,
            executor_ref,
            item.source_seq,
            payload,
        )

    def _known_result_for_attempt(
        self,
        task_id: str,
        attempt_id: str,
        executor_ref: str,
        source_seq: int,
        payload: Mapping[str, Any],
    ) -> ExecutorDeliveryResult:
        status = _text(payload, "status")
        if status is None:
            raise FormalTaskViolation(
                "EXECUTOR_STATUS_REQUIRED",
                "legacy Executor response lacks a stable status",
                ErrorCode.PROTOCOL_VIOLATION,
            )
        target_state, outcome = self._map_status(status)
        target_seq = {
            FormalAttemptState.ACCEPTED: 0,
            FormalAttemptState.RUNNING: 1,
            FormalAttemptState.TERMINAL: 2,
        }[target_state]
        states = (
            (FormalAttemptState.ACCEPTED, None),
            (FormalAttemptState.RUNNING, None),
            (FormalAttemptState.TERMINAL, outcome),
        )
        observed_at = utc_now()
        summary = _text(payload, "message", "progress_summary")
        error = _text(payload, "last_error", "error")
        observations = []
        for seq in range(source_seq + 1, target_seq + 1):
            state, state_outcome = states[seq]
            observations.append(
                ExecutorObservation(
                    resolution=ExecutorResolution.KNOWN,
                    executor_id=self.executor_id,
                    executor_ref=executor_ref,
                    task_id=task_id,
                    attempt_id=attempt_id,
                    source_event_id=(
                        f"{executor_ref}:formal-lifecycle:{seq}:"
                        f"{state.value}:{'' if state_outcome is None else state_outcome.value}"
                    ),
                    source_seq=seq,
                    attempt_state=state,
                    attempt_outcome=state_outcome,
                    occurred_at=observed_at,
                    raw_status=status,
                    summary=summary,
                    error=error,
                )
            )
        return ExecutorDeliveryResult(executor_ref, tuple(observations))

    @staticmethod
    def _map_status(status: str) -> tuple[FormalAttemptState, TerminalOutcome | None]:
        normalized = status.strip().lower()
        if normalized == "pending":
            return FormalAttemptState.ACCEPTED, None
        if normalized == "running":
            return FormalAttemptState.RUNNING, None
        if normalized in {"success", "completed"}:
            return FormalAttemptState.TERMINAL, TerminalOutcome.COMPLETED
        if normalized == "failed":
            return FormalAttemptState.TERMINAL, TerminalOutcome.FAILED
        if normalized == "cancelled":
            return FormalAttemptState.TERMINAL, TerminalOutcome.CANCELLED
        if normalized in {"needs_human", "skipped", "interrupted"}:
            return FormalAttemptState.TERMINAL, TerminalOutcome.INTERRUPTED
        raise FormalTaskViolation(
            "UNSUPPORTED_EXECUTOR_STATUS",
            f"legacy Executor status {status!r} is not valid for project Code Agent tasks",
            ErrorCode.PROTOCOL_VIOLATION,
        )

    def _resolution_observation(
        self,
        task_id: str,
        attempt_id: str,
        executor_ref: str | None,
        resolution: ExecutorResolution,
        error: str,
    ) -> ExecutorObservation:
        return ExecutorObservation(
            resolution=resolution,
            executor_id=self.executor_id,
            executor_ref=executor_ref,
            task_id=task_id,
            attempt_id=attempt_id,
            source_event_id=None,
            source_seq=None,
            attempt_state=None,
            attempt_outcome=None,
            occurred_at=utc_now(),
            raw_status=None,
            error=error,
        )


__all__ = [
    "DirectProjectCodeExecutorAdapter",
    "DIRECT_PROJECT_EXECUTOR_REF_PREFIX",
    "FORMAL_PROJECT_EXECUTOR_ID",
    "FORMAL_RUNTIME_SUPPORT_POLICY",
    "PROJECT_CODE_ARTIFACT_KIND",
    "PROJECT_CODE_EFFECT_POLICY",
    "PROJECT_CODE_EXECUTOR",
    "PROJECT_CODE_PIPELINE",
    "LegacyProjectTaskService",
    "ProjectCodeExecutorAdapter",
    "ProjectExecutionBinding",
    "ProjectExecutionBindingResolver",
]
