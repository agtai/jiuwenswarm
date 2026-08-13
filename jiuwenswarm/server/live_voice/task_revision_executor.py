# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Executor fence, disposable fixture, and verifier for the S8.5 profile.

The module is intentionally unavailable unless an application constructs the
registry and coordinator explicitly.  It accepts no model-selected executable,
project root, task identity, or write policy.  Those facts come from a trusted
fixture manifest and the Task-Core-owned revision ledger.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    ErrorCode,
    TerminalOutcome,
    canonical_json_bytes,
)

from .formal_task_models import (
    ExecutorDeliveryResult,
    FormalAttemptState,
    FormalTaskViolation,
    PersistentOutboxItem,
)
from .project_code_executor import (
    DirectProjectCodeExecutorAdapter,
    _git_head,
    _git_output,
    _git_root,
    _path_key,
    _project_content_fingerprint,
    _project_tree_fingerprint,
    _reject_git_visible_symlinks,
)
from .task_revision import (
    TaskRevisionConstraints,
    TaskRevisionExecutionAck,
    TaskRevisionVerifierResult,
    TaskRevisionVerifierState,
)
from .task_revision_store import (
    SqliteTaskRevisionStore,
    TaskRevisionReceipt,
)


S8_5_FIXTURE_PROFILE = "live-voice.s8-5-disposable-fixture.v1"
S8_5_FIXTURE_MARKER = ".live-voice-s8-5-fixture.json"
_MAX_VERIFIER_TIMEOUT_SECONDS = 120.0
_MAX_VERIFIER_OUTPUT_BYTES = 64 * 1024
_BLOCKED_EXECUTABLES = frozenset(
    {
        "bash",
        "cmd",
        "curl",
        "git",
        "pwsh",
        "powershell",
        "scp",
        "sh",
        "ssh",
        "wget",
    }
)
_DEPENDENCY_NAMES = frozenset(
    {
        "cargo.lock",
        "cargo.toml",
        "composer.json",
        "composer.lock",
        "go.mod",
        "go.sum",
        "package-lock.json",
        "package.json",
        "pnpm-lock.yaml",
        "poetry.lock",
        "pyproject.toml",
        "requirements.txt",
        "uv.lock",
        "yarn.lock",
    }
)
_CONFIG_NAMES = frozenset(
    {
        ".editorconfig",
        ".env",
        ".gitattributes",
        ".gitignore",
        "dockerfile",
        "makefile",
        "tox.ini",
    }
)
_SECRET_PATTERN = re.compile(
    r"(?i)(api[_-]?key|authorization|password|secret|token)\s*[:=]\s*\S+"
)


def _text(value: object, field_name: str) -> str:
    if type(value) is not str or not value.strip():
        raise ValueError(f"{field_name} must be non-empty")
    return value


def _relative_path(value: object, field_name: str) -> str:
    text = _text(value, field_name)
    path = PurePosixPath(text)
    if (
        "\\" in text
        or path.is_absolute()
        or text != path.as_posix()
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ValueError(f"{field_name} must be a normalized relative POSIX path")
    return text


def _within(path: str, parent: str) -> bool:
    return path == parent or path.startswith(parent + "/")


def _git_remote_names(root: Path) -> tuple[str, ...]:
    raw = _git_output(root, "remote")
    return tuple(
        sorted(
            value.decode("utf-8", errors="strict").strip()
            for value in raw.splitlines()
            if value
        )
    )


def _changed_paths(root: Path) -> tuple[str, ...]:
    tracked = _git_output(root, "diff", "--name-only", "-z", "HEAD", "--")
    untracked = _git_output(root, "ls-files", "--others", "--exclude-standard", "-z")
    ignored = _git_output(
        root, "ls-files", "--others", "--ignored", "--exclude-standard", "-z"
    )
    paths: set[str] = set()
    for raw in (
        *tracked.split(b"\0"),
        *untracked.split(b"\0"),
        *ignored.split(b"\0"),
    ):
        if not raw:
            continue
        try:
            paths.add(_relative_path(raw.decode("utf-8", errors="strict"), "path"))
        except (UnicodeDecodeError, ValueError) as error:
            raise FormalTaskViolation(
                "TASK_REVISION_FIXTURE_PATH_UNSAFE",
                "fixture contains an unsafe changed path",
                ErrorCode.PERMISSION_DENIED,
            ) from error
    return tuple(sorted(paths))


def _is_dependency_or_configuration(path: str) -> bool:
    name = PurePosixPath(path).name.lower()
    return (
        name in _DEPENDENCY_NAMES
        or name in _CONFIG_NAMES
        or name.startswith("requirements-")
        and name.endswith(".txt")
        or name.startswith(".env.")
        or name.endswith((".config.js", ".config.mjs", ".config.ts"))
        or path.lower().startswith(".github/")
    )


@dataclass(frozen=True, slots=True)
class TrustedRevisionFixtureManifest:
    """Server-provisioned identity for one disposable no-remote Git fixture."""

    fixture_id: str
    project_id: str
    fixture_parent: str
    project_root: str
    baseline_head: str
    baseline_tree: str
    baseline_content: str
    write_scope: tuple[str, ...]
    immutable_paths: tuple[str, ...]
    verifier_id: str

    def __post_init__(self) -> None:
        for field_name in (
            "fixture_id",
            "project_id",
            "fixture_parent",
            "project_root",
            "baseline_head",
            "baseline_tree",
            "baseline_content",
            "verifier_id",
        ):
            _text(getattr(self, field_name), field_name)
        if type(self.write_scope) is not tuple or not self.write_scope:
            raise ValueError("write_scope must be a non-empty immutable tuple")
        if type(self.immutable_paths) is not tuple:
            raise ValueError("immutable_paths must be an immutable tuple")
        scope = TaskRevisionConstraints(self.write_scope).write_scope
        immutable = tuple(
            sorted(
                {
                    _relative_path(path, f"immutable_paths[{index}]")
                    for index, path in enumerate(self.immutable_paths)
                }
            )
        )
        if S8_5_FIXTURE_MARKER not in immutable:
            immutable = tuple(sorted((*immutable, S8_5_FIXTURE_MARKER)))
        object.__setattr__(self, "write_scope", scope)
        object.__setattr__(self, "immutable_paths", immutable)

    @property
    def root(self) -> Path:
        return Path(self.project_root).resolve(strict=True)

    @property
    def parent(self) -> Path:
        return Path(self.fixture_parent).resolve(strict=True)

    @property
    def marker_bytes(self) -> bytes:
        return canonical_json_bytes(
            {
                "fixture_id": self.fixture_id,
                "profile": S8_5_FIXTURE_PROFILE,
            }
        )

    @property
    def checkout_identity(self) -> str:
        payload = {
            "profile": S8_5_FIXTURE_PROFILE,
            "fixture_id": self.fixture_id,
            "project_id": self.project_id,
            "baseline_head": self.baseline_head,
            "baseline_tree": self.baseline_tree,
            "baseline_content": self.baseline_content,
            "write_scope": list(self.write_scope),
            "immutable_paths": list(self.immutable_paths),
            "verifier_id": self.verifier_id,
        }
        return (
            "fixture-sha256:"
            + hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
        )

    def require_original_clean_base(self) -> None:
        """Fail closed unless this is the exact provisioned original checkout."""

        try:
            root = self.root
            parent = self.parent
            root.relative_to(parent)
        except (OSError, ValueError) as error:
            raise FormalTaskViolation(
                "TASK_REVISION_REAL_PROJECT_FORBIDDEN",
                "revision target is outside the disposable fixture parent",
                ErrorCode.PERMISSION_DENIED,
            ) from error
        if root == parent or _path_key(root) != _path_key(_git_root(root)):
            raise FormalTaskViolation(
                "TASK_REVISION_REAL_PROJECT_FORBIDDEN",
                "revision target is not one exact disposable fixture root",
                ErrorCode.PERMISSION_DENIED,
            )
        _reject_git_visible_symlinks(root)
        marker = root / S8_5_FIXTURE_MARKER
        try:
            marker_bytes = marker.read_bytes()
        except OSError as error:
            raise FormalTaskViolation(
                "TASK_REVISION_FIXTURE_MARKER_MISSING",
                "disposable fixture marker is unavailable",
                ErrorCode.PERMISSION_DENIED,
            ) from error
        tracked_marker = _git_output(
            root, "ls-files", "--error-unmatch", "--", S8_5_FIXTURE_MARKER
        )
        if not tracked_marker or marker_bytes != self.marker_bytes:
            raise FormalTaskViolation(
                "TASK_REVISION_FIXTURE_MARKER_MISMATCH",
                "disposable fixture marker is not exact",
                ErrorCode.PERMISSION_DENIED,
            )
        if _git_remote_names(root):
            raise FormalTaskViolation(
                "TASK_REVISION_REMOTE_FIXTURE_FORBIDDEN",
                "revision fixture must have no Git remote",
                ErrorCode.PERMISSION_DENIED,
            )
        if _git_output(
            root,
            "ls-files",
            "--others",
            "--ignored",
            "--exclude-standard",
            "-z",
        ):
            raise FormalTaskViolation(
                "TASK_REVISION_IGNORED_FIXTURE_CONTENT_FORBIDDEN",
                "revision fixture must not hide ignored baseline content",
                ErrorCode.PERMISSION_DENIED,
            )
        if _git_output(root, "status", "--porcelain=v2", "-z", "--untracked-files=all"):
            raise FormalTaskViolation(
                "TASK_REVISION_DIRTY_FIXTURE_FORBIDDEN",
                "revision successor requires the original clean fixture base",
                ErrorCode.PERMISSION_DENIED,
            )
        if (
            _git_head(root) != self.baseline_head
            or _project_tree_fingerprint(root) != self.baseline_tree
            or _project_content_fingerprint(root) != self.baseline_content
        ):
            raise FormalTaskViolation(
                "TASK_REVISION_FIXTURE_BASELINE_MISMATCH",
                "revision fixture does not match its trusted manifest",
                ErrorCode.PERMISSION_DENIED,
            )

    def require_constraints(self, constraints: TaskRevisionConstraints) -> None:
        if type(constraints) is not TaskRevisionConstraints:
            raise TypeError("constraints must be exact TaskRevisionConstraints")
        if any(
            not any(_within(path, allowed) for allowed in self.write_scope)
            for path in constraints.write_scope
        ):
            raise FormalTaskViolation(
                "TASK_REVISION_WRITE_SCOPE_NOT_MANIFESTED",
                "effective write scope exceeds the trusted fixture manifest",
                ErrorCode.PERMISSION_DENIED,
            )


@dataclass(frozen=True, slots=True)
class TrustedVerifierCommand:
    verifier_id: str
    argv: tuple[str, ...]
    timeout_seconds: float = 30.0
    maximum_output_bytes: int = 16 * 1024

    def __post_init__(self) -> None:
        _text(self.verifier_id, "verifier_id")
        if (
            type(self.argv) is not tuple
            or not self.argv
            or any(type(value) is not str or not value for value in self.argv)
        ):
            raise ValueError("argv must be a non-empty immutable string tuple")
        executable = Path(self.argv[0]).name.lower()
        if executable.endswith(".exe"):
            executable = executable[:-4]
        if executable in _BLOCKED_EXECUTABLES:
            raise ValueError("verifier executable is not allowlisted for S8.5")
        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, (int, float))
            or not 0 < self.timeout_seconds <= _MAX_VERIFIER_TIMEOUT_SECONDS
        ):
            raise ValueError("timeout_seconds is outside the bounded range")
        if (
            type(self.maximum_output_bytes) is not int
            or not 1 <= self.maximum_output_bytes <= _MAX_VERIFIER_OUTPUT_BYTES
        ):
            raise ValueError("maximum_output_bytes is outside the bounded range")


class TrustedRevisionFixtureRegistry:
    """Immutable application registry; no Voice/Agent values enter this map."""

    def __init__(
        self,
        manifests: tuple[TrustedRevisionFixtureManifest, ...],
        verifiers: tuple[TrustedVerifierCommand, ...],
    ) -> None:
        if type(manifests) is not tuple or type(verifiers) is not tuple:
            raise TypeError("fixture registry inputs must be immutable tuples")
        by_project = {manifest.project_id: manifest for manifest in manifests}
        by_verifier = {verifier.verifier_id: verifier for verifier in verifiers}
        if len(by_project) != len(manifests) or len(by_verifier) != len(verifiers):
            raise ValueError("fixture and verifier identities must be unique")
        if any(manifest.verifier_id not in by_verifier for manifest in manifests):
            raise ValueError("every fixture must select one registered verifier")
        self._by_project: Mapping[str, TrustedRevisionFixtureManifest] = by_project
        self._by_verifier: Mapping[str, TrustedVerifierCommand] = by_verifier

    def fixture(self, project_id: str) -> TrustedRevisionFixtureManifest:
        try:
            return self._by_project[project_id]
        except KeyError as error:
            raise FormalTaskViolation(
                "TASK_REVISION_FIXTURE_NOT_REGISTERED",
                "scope project has no trusted S8.5 fixture",
                ErrorCode.PERMISSION_DENIED,
            ) from error

    def verifier(self, verifier_id: str) -> TrustedVerifierCommand:
        try:
            return self._by_verifier[verifier_id]
        except KeyError as error:
            raise FormalTaskViolation(
                "TASK_REVISION_VERIFIER_NOT_REGISTERED",
                "fixture verifier is unavailable",
                ErrorCode.CAPABILITY_UNAVAILABLE,
            ) from error


def load_trusted_revision_fixture_registry(
    manifest_path: str | os.PathLike[str],
) -> TrustedRevisionFixtureRegistry:
    """Load one exact server-owned fixture registry from machine-private JSON."""

    try:
        path = Path(manifest_path).expanduser().resolve(strict=True)
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise FormalTaskViolation(
            "TASK_REVISION_FIXTURE_REGISTRY_UNAVAILABLE",
            "S8.5 fixture registry could not be loaded",
            ErrorCode.UNAVAILABLE,
        ) from error
    if (
        type(payload) is not dict
        or set(payload)
        != {
            "profile",
            "fixtures",
            "verifiers",
        }
        or payload.get("profile") != S8_5_FIXTURE_PROFILE
    ):
        raise FormalTaskViolation(
            "INVALID_TASK_REVISION_FIXTURE_REGISTRY",
            "S8.5 fixture registry has incomplete or unknown fields",
            ErrorCode.INVALID_ARGUMENT,
        )
    raw_fixtures = payload.get("fixtures")
    raw_verifiers = payload.get("verifiers")
    if type(raw_fixtures) is not list or type(raw_verifiers) is not list:
        raise FormalTaskViolation(
            "INVALID_TASK_REVISION_FIXTURE_REGISTRY",
            "S8.5 fixture and verifier registries must be arrays",
            ErrorCode.INVALID_ARGUMENT,
        )
    if not raw_fixtures or not raw_verifiers:
        raise FormalTaskViolation(
            "INVALID_TASK_REVISION_FIXTURE_REGISTRY",
            "S8.5 fixture registry must contain a fixture and verifier",
            ErrorCode.INVALID_ARGUMENT,
        )
    fixture_fields = {
        "fixture_id",
        "project_id",
        "fixture_parent",
        "project_root",
        "baseline_head",
        "baseline_tree",
        "baseline_content",
        "write_scope",
        "immutable_paths",
        "verifier_id",
    }
    verifier_fields = {
        "verifier_id",
        "argv",
        "timeout_seconds",
        "maximum_output_bytes",
    }
    if any(
        type(item) is not dict
        or set(item) != fixture_fields
        or type(item["write_scope"]) is not list
        or not item["write_scope"]
        or any(type(value) is not str for value in item["write_scope"])
        or type(item["immutable_paths"]) is not list
        or any(type(value) is not str for value in item["immutable_paths"])
        for item in raw_fixtures
    ) or any(
        type(item) is not dict
        or set(item) != verifier_fields
        or type(item["argv"]) is not list
        or not item["argv"]
        or any(type(value) is not str for value in item["argv"])
        for item in raw_verifiers
    ):
        raise FormalTaskViolation(
            "INVALID_TASK_REVISION_FIXTURE_REGISTRY",
            "S8.5 fixture registry entries have incomplete or unknown fields",
            ErrorCode.INVALID_ARGUMENT,
        )
    try:
        manifests = tuple(
            TrustedRevisionFixtureManifest(
                fixture_id=item["fixture_id"],
                project_id=item["project_id"],
                fixture_parent=item["fixture_parent"],
                project_root=item["project_root"],
                baseline_head=item["baseline_head"],
                baseline_tree=item["baseline_tree"],
                baseline_content=item["baseline_content"],
                write_scope=tuple(item["write_scope"]),
                immutable_paths=tuple(item["immutable_paths"]),
                verifier_id=item["verifier_id"],
            )
            for item in raw_fixtures
        )
        verifiers = tuple(
            TrustedVerifierCommand(
                verifier_id=item["verifier_id"],
                argv=tuple(item["argv"]),
                timeout_seconds=item["timeout_seconds"],
                maximum_output_bytes=item["maximum_output_bytes"],
            )
            for item in raw_verifiers
        )
    except (KeyError, TypeError, ValueError) as error:
        raise FormalTaskViolation(
            "INVALID_TASK_REVISION_FIXTURE_REGISTRY",
            "S8.5 fixture registry values are invalid",
            ErrorCode.INVALID_ARGUMENT,
        ) from error
    try:
        registry = TrustedRevisionFixtureRegistry(manifests, verifiers)
        for manifest in manifests:
            manifest.require_original_clean_base()
        return registry
    except (OSError, TypeError, ValueError) as error:
        if isinstance(error, FormalTaskViolation):
            raise
        raise FormalTaskViolation(
            "INVALID_TASK_REVISION_FIXTURE_REGISTRY",
            "S8.5 fixture registry failed validation",
            ErrorCode.INVALID_ARGUMENT,
        ) from error


def _sanitized_output(root: Path, payload: bytes, maximum: int) -> tuple[str, str]:
    bounded = payload[:maximum]
    text = bounded.decode("utf-8", errors="replace")
    text = re.sub(re.escape(str(root)), "<fixture>", text, flags=re.IGNORECASE)
    text = re.sub(
        re.escape(str(root).replace("\\", "/")),
        "<fixture>",
        text,
        flags=re.IGNORECASE,
    )
    text = _SECRET_PATTERN.sub(r"\1=<redacted>", text)
    text = "".join(
        character if character in "\n\r\t" or ord(character) >= 0x20 else "�"
        for character in text
    )
    if len(payload) > maximum:
        text += "\n<truncated>"
    return hashlib.sha256(payload).hexdigest(), text[:2_000]


class TaskRevisionFixtureVerifier:
    """Run one registry-selected verifier after exact successor completion."""

    def __init__(
        self,
        registry: TrustedRevisionFixtureRegistry,
        *,
        cleanup_proof: Callable[[str, str, str], bool],
    ) -> None:
        if not callable(cleanup_proof):
            raise TypeError("cleanup_proof must be callable")
        self._registry = registry
        self._cleanup_proof = cleanup_proof

    async def verify(
        self,
        *,
        item: PersistentOutboxItem,
        delivery: ExecutorDeliveryResult,
        task_revision: int,
        constraints: TaskRevisionConstraints,
    ) -> TaskRevisionExecutionAck:
        if type(item) is not PersistentOutboxItem:
            raise TypeError("item must be an exact PersistentOutboxItem")
        if type(delivery) is not ExecutorDeliveryResult:
            raise TypeError("delivery must be an exact ExecutorDeliveryResult")
        manifest = self._registry.fixture(item.scope.project_id)
        manifest.require_constraints(constraints)
        root = manifest.root
        if (
            item.spec.context.file_path is None
            or _path_key(item.spec.context.file_path, strict=False)
            != _path_key(root, strict=False)
            or not delivery.observations
            or any(
                observation.task_id != item.task_id
                or observation.attempt_id != item.attempt_id
                or observation.executor_id != item.spec.executor_id
                or observation.executor_ref != delivery.executor_ref
                for observation in delivery.observations
            )
        ):
            raise FormalTaskViolation(
                "TASK_REVISION_EXECUTION_ACK_MISMATCH",
                "Executor result does not bind the exact successor fixture",
                ErrorCode.PROTOCOL_VIOLATION,
            )
        terminal = delivery.observations[-1]
        executor_completed = (
            terminal.attempt_state is FormalAttemptState.TERMINAL
            and terminal.attempt_outcome is TerminalOutcome.COMPLETED
        )
        if not self._cleanup_proof(
            item.task_id, item.attempt_id, delivery.executor_ref
        ):
            raise FormalTaskViolation(
                "TASK_REVISION_SUCCESSOR_CLEANUP_UNKNOWN",
                "successor Executor cleanup is not durably resolved",
                ErrorCode.RESULT_UNKNOWN,
            )
        if _git_head(root) != manifest.baseline_head or _git_remote_names(root):
            raise FormalTaskViolation(
                "TASK_REVISION_FORBIDDEN_GIT_MUTATION",
                "successor changed Git HEAD or configured a remote",
                ErrorCode.PERMISSION_DENIED,
            )
        _reject_git_visible_symlinks(root)
        changed = _changed_paths(root)
        forbidden = tuple(
            path
            for path in changed
            if any(_within(path, immutable) for immutable in manifest.immutable_paths)
            or not any(_within(path, scope) for scope in constraints.write_scope)
            or _is_dependency_or_configuration(path)
        )
        verifier = self._registry.verifier(manifest.verifier_id)
        if forbidden or not executor_completed or not changed:
            result = TaskRevisionVerifierResult(
                verifier.verifier_id,
                TaskRevisionVerifierState.NOT_RUN,
                None,
                False,
                hashlib.sha256(b"").hexdigest(),
                "Verifier was not run because authoritative execution policy failed.",
            )
            return TaskRevisionExecutionAck(
                item.task_id,
                task_revision,
                item.attempt_id,
                delivery.executor_ref,
                manifest.checkout_identity,
                executor_completed,
                changed,
                f"{len(changed)} changed path(s)",
                result,
                "successor_cleanup_resolved",
                len(forbidden),
                False,
            )

        before_head = _git_head(root)
        before_tree = _project_tree_fingerprint(root)
        before_content = _project_content_fingerprint(root)
        before_remotes = _git_remote_names(root)
        environment = {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
            "NO_PROXY": "*",
            "no_proxy": "*",
        }

        def _run() -> subprocess.CompletedProcess[bytes]:
            return subprocess.run(
                list(verifier.argv),
                cwd=str(root),
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=float(verifier.timeout_seconds),
                check=False,
                shell=False,
            )

        timed_out = False
        exit_code: int | None = None
        output = b""
        try:
            completed = await asyncio.to_thread(_run)
            exit_code = completed.returncode
            output = completed.stdout
        except subprocess.TimeoutExpired as error:
            timed_out = True
            output = (error.stdout or b"") + (error.stderr or b"")
        digest, summary = _sanitized_output(root, output, verifier.maximum_output_bytes)
        verifier_mutated = (
            _git_head(root) != before_head
            or _project_tree_fingerprint(root) != before_tree
            or _project_content_fingerprint(root) != before_content
            or _git_remote_names(root) != before_remotes
        )
        result_name = (
            TaskRevisionVerifierState.TIMEOUT
            if timed_out
            else TaskRevisionVerifierState.FAILED
            if exit_code != 0
            else TaskRevisionVerifierState.MUTATED_FIXTURE
            if verifier_mutated
            else TaskRevisionVerifierState.PASSED
        )
        result = TaskRevisionVerifierResult(
            verifier.verifier_id,
            result_name,
            exit_code,
            timed_out,
            digest,
            summary,
        )
        forbidden_count = len(forbidden) + int(verifier_mutated)
        return TaskRevisionExecutionAck(
            item.task_id,
            task_revision,
            item.attempt_id,
            delivery.executor_ref,
            manifest.checkout_identity,
            executor_completed,
            changed,
            f"{len(changed)} changed path(s)",
            result,
            "successor_cleanup_resolved",
            forbidden_count,
            result_name is TaskRevisionVerifierState.PASSED and forbidden_count == 0,
        )


@dataclass(frozen=True, slots=True)
class TaskRevisionSuccessorDispatch:
    item: PersistentOutboxItem
    delivery: ExecutorDeliveryResult


class TaskRevisionExecutionCoordinator:
    """Small outbox pump; Store and Direct Executor retain their authorities."""

    def __init__(
        self,
        store: SqliteTaskRevisionStore,
        executor: DirectProjectCodeExecutorAdapter,
        registry: TrustedRevisionFixtureRegistry,
        *,
        worker_id: str,
    ) -> None:
        if type(store) is not SqliteTaskRevisionStore:
            raise TypeError("store must be an exact SqliteTaskRevisionStore")
        if type(executor) is not DirectProjectCodeExecutorAdapter:
            raise TypeError(
                "executor must be an exact DirectProjectCodeExecutorAdapter"
            )
        self._store = store
        self._executor = executor
        self._registry = registry
        self._worker_id = _text(worker_id, "worker_id")
        self._verifier = TaskRevisionFixtureVerifier(
            registry,
            cleanup_proof=executor.revision_cleanup_resolved,
        )

    async def fence_once(self) -> TaskRevisionReceipt | None:
        claimed = self._store.claim_fence(self._worker_id)
        if claimed is None:
            return None
        try:
            manifest = self._registry.fixture(claimed.scope.project_id)
            manifest.require_original_clean_base()
            ack = await self._executor.fence_revision(
                claimed.request,
                executor_id=claimed.executor_id,
                executor_ref=claimed.executor_ref,
                expected_project_root=manifest.project_root,
                expected_before_head=manifest.baseline_head,
                expected_before_tree=manifest.baseline_tree,
                expected_before_content=manifest.baseline_content,
                checkout_identity=manifest.checkout_identity,
            )
            if ack.checkout_identity != manifest.checkout_identity:
                raise FormalTaskViolation(
                    "TASK_REVISION_FIXTURE_IDENTITY_MISMATCH",
                    "Executor cleanup ACK names another fixture baseline",
                    ErrorCode.PROTOCOL_VIOLATION,
                )
            return self._store.complete_fence(claimed, ack)
        except FormalTaskViolation as error:
            if error.code in {ErrorCode.UNAVAILABLE, ErrorCode.TIMEOUT}:
                self._store.release_fence(claimed, error.reason)
                return None
            return self._store.mark_fence_unknown(claimed, reason=error.reason)
        except asyncio.CancelledError:
            self._store.mark_fence_unknown(
                claimed, reason="TASK_REVISION_FENCE_COORDINATOR_CANCELLED"
            )
            raise
        except Exception as error:  # noqa: BLE001 -- uncertain cleanup stays unknown
            return self._store.mark_fence_unknown(
                claimed, reason=f"TASK_REVISION_FENCE_EXCEPTION:{type(error).__name__}"
            )

    async def dispatch_once(self) -> TaskRevisionSuccessorDispatch | None:
        claimed = self._store.claim_successor_dispatch(self._worker_id)
        if claimed is None:
            return None
        item = claimed.item
        try:
            manifest = self._registry.fixture(item.scope.project_id)
            truth = self._store.truth(item.task_id, item.scope)
            if truth.current_revision.attempt_id != item.attempt_id:
                raise FormalTaskViolation(
                    "TASK_REVISION_DISPATCH_BINDING_MISMATCH",
                    "successor dispatch is not the current revision attempt",
                    ErrorCode.PROTOCOL_VIOLATION,
                )
            manifest.require_constraints(truth.current_revision.constraints)
            manifest.require_original_clean_base()
            if item.spec.context.file_path is None or _path_key(
                item.spec.context.file_path, strict=False
            ) != _path_key(manifest.root, strict=False):
                raise FormalTaskViolation(
                    "TASK_REVISION_FIXTURE_MISMATCH",
                    "successor spec is not bound to the trusted fixture",
                    ErrorCode.PERMISSION_DENIED,
                )
            delivery = await self._executor.dispatch(item)
            self._store.complete_successor_dispatch(claimed, delivery)
            return TaskRevisionSuccessorDispatch(item, delivery)
        except FormalTaskViolation as error:
            self._store.release_successor_dispatch(claimed, error=error.reason)
            return None
        except asyncio.CancelledError:
            self._store.release_successor_dispatch(
                claimed, error="TASK_REVISION_DISPATCH_COORDINATOR_CANCELLED"
            )
            raise
        except Exception as error:  # noqa: BLE001 -- retry durable dispatch later
            self._store.release_successor_dispatch(
                claimed,
                error=f"TASK_REVISION_DISPATCH_EXCEPTION:{type(error).__name__}",
            )
            return None

    async def verify_once(self) -> TaskRevisionExecutionAck | None:
        """Reconcile and verify one durably dispatched successor, if terminal."""

        pending = self._store.pending_execution_items(limit=1)
        if not pending:
            return None
        item = pending[0]
        truth = self._store.truth(item.task_id, item.scope)
        if truth.execution_ack is not None:
            return truth.execution_ack
        if truth.current_revision.attempt_id != item.attempt_id:
            raise FormalTaskViolation(
                "TASK_REVISION_VERIFICATION_BINDING_MISMATCH",
                "pending verification is not the current revision attempt",
                ErrorCode.PROTOCOL_VIOLATION,
            )
        delivery = await self._executor.revision_delivery(truth.task, truth.attempt)
        if not delivery.observations:
            return None
        terminal = delivery.observations[-1]
        if terminal.attempt_state is not FormalAttemptState.TERMINAL:
            observations = tuple(
                observation
                for observation in delivery.observations
                if observation.source_seq is not None
                and observation.source_seq > truth.attempt.source_seq
            )
            if observations:
                self._store.task_store.apply_observations(observations)
            return None
        observations = tuple(
            observation
            for observation in delivery.observations
            if observation.source_seq is not None
            and observation.source_seq > truth.attempt.source_seq
        )
        if observations:
            self._store.task_store.apply_observations(observations)
        refreshed = self._store.truth(item.task_id, item.scope)
        ack = await self._verifier.verify(
            item=item,
            delivery=delivery,
            task_revision=refreshed.current_revision.task_revision,
            constraints=refreshed.current_revision.constraints,
        )
        return self._store.record_execution_ack(item.scope, ack)


__all__ = [
    "S8_5_FIXTURE_MARKER",
    "S8_5_FIXTURE_PROFILE",
    "TaskRevisionExecutionCoordinator",
    "TaskRevisionFixtureVerifier",
    "TaskRevisionSuccessorDispatch",
    "TrustedRevisionFixtureManifest",
    "TrustedRevisionFixtureRegistry",
    "TrustedVerifierCommand",
    "load_trusted_revision_fixture_registry",
]
