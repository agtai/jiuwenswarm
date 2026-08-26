# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Bounded, read-only identity for the Git-visible project state.

The manifest deliberately separates Git's durable identities (HEAD and index)
from the bounded set of paths whose worktree state differs.  Callers own the
meaning of the resulting fingerprints; this module owns only inspection,
capacity enforcement, and canonical low-level identity.

Renames are requested from Git with ``--no-renames`` and therefore have one
canonical representation: a source deletion plus a destination addition.  A
rename consequently consumes two distinct changed-path slots.  A path present
in both the staged and unstaged columns consumes one slot.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable

MAX_CHANGED_PATHS = 32
MAX_CONTENT_BYTES_PER_PATH = 1 * 1024 * 1024
MAX_TOTAL_CONTENT_BYTES = 16 * 1024 * 1024

_SCHEMA = "jiuwenswarm.bounded-git-manifest.v1"
_UNBORN_HEAD = "unborn"


class BoundedGitManifestError(RuntimeError):
    """A Git-visible project could not be represented safely."""


class GitManifestCapacityExceeded(BoundedGitManifestError):
    """A frozen B27 manifest capacity was exceeded."""

    code = "GIT_MANIFEST_CAPACITY_EXCEEDED"

    def __init__(self, dimension: str, *, limit: int, observed: int) -> None:
        self.dimension = dimension
        self.limit = limit
        self.observed = observed
        super().__init__(f"{self.code}: {dimension} limit={limit} observed={observed}")


class GitManifestInspectionError(BoundedGitManifestError):
    """Git metadata or one bounded worktree entry was not inspectable."""

    code = "GIT_MANIFEST_INSPECTION_FAILED"

    def __init__(self, detail: str) -> None:
        super().__init__(f"{self.code}: {detail}")


@dataclass(frozen=True, slots=True)
class GitIndexEntry:
    path: str
    mode: str
    object_id: str
    stage: int


@dataclass(frozen=True, slots=True)
class GitStatusEntry:
    record_kind: str
    fields: tuple[str, ...]
    path: str
    original_path: str | None = None

    @property
    def paths(self) -> tuple[str, ...]:
        if self.original_path is None:
            return (self.path,)
        return (self.path, self.original_path)


@dataclass(frozen=True, slots=True)
class GitWorktreeEntry:
    path: str
    kind: str
    mode: str
    object_id: str
    content_bytes: int


@dataclass(frozen=True, slots=True)
class BoundedGitManifest:
    root: Path
    head_tree: str
    index_entries: tuple[GitIndexEntry, ...]
    status_entries: tuple[GitStatusEntry, ...]
    worktree_entries: tuple[GitWorktreeEntry, ...]
    changed_path_count: int
    total_content_bytes: int

    def index_fingerprint(self) -> str:
        digest = _new_digest("index")
        for entry in self.index_entries:
            _update_digest(
                digest,
                (entry.path, entry.mode, entry.object_id, str(entry.stage)),
            )
        return digest.hexdigest()

    def tree_fingerprint(self) -> str:
        """Exact Git presentation: HEAD, index, status, and bounded deltas."""

        digest = _new_digest("tree")
        _update_digest(digest, (self.head_tree, self.index_fingerprint()))
        for entry in self.status_entries:
            _update_digest(
                digest,
                (
                    entry.record_kind,
                    *entry.fields,
                    entry.path,
                    entry.original_path or "",
                ),
            )
        for entry in self.worktree_entries:
            _update_digest(
                digest,
                (
                    entry.path,
                    entry.kind,
                    entry.mode,
                    entry.object_id,
                    str(entry.content_bytes),
                ),
            )
        return digest.hexdigest()

    def content_fingerprint(self) -> str:
        """Canonical Git-visible content/mode state, independent of staging."""

        visible: dict[str, tuple[str, str, str]] = {
            entry.path: (_kind_for_mode(entry.mode), entry.mode, entry.object_id)
            for entry in self.index_entries
            if entry.stage == 0
        }
        for entry in self.worktree_entries:
            if entry.kind in {"missing", "directory"}:
                visible.pop(entry.path, None)
            else:
                visible[entry.path] = (
                    entry.kind,
                    entry.mode,
                    entry.object_id,
                )
        digest = _new_digest("content")
        for path, (kind, mode, object_id) in sorted(visible.items()):
            _update_digest(digest, (path, kind, mode, object_id))
        return digest.hexdigest()


def capture_bounded_git_manifest(root: str | Path) -> BoundedGitManifest:
    """Capture a read-only Git manifest under the frozen B27 capacities."""

    canonical_root = Path(root).resolve()
    if not canonical_root.is_dir():
        raise GitManifestInspectionError("target is not a directory")

    status_entries = _status_entries(canonical_root)
    changed_paths = sorted({path for entry in status_entries for path in entry.paths})
    if len(changed_paths) > MAX_CHANGED_PATHS:
        raise GitManifestCapacityExceeded(
            "changed_paths",
            limit=MAX_CHANGED_PATHS,
            observed=len(changed_paths),
        )

    index_entries = _index_entries(canonical_root)
    index_modes: dict[str, str] = {}
    for entry in index_entries:
        if entry.stage == 0:
            index_modes[entry.path] = entry.mode
        elif entry.path not in index_modes and entry.mode == "160000":
            index_modes[entry.path] = entry.mode

    worktree_entries: list[GitWorktreeEntry] = []
    total_content_bytes = 0
    for relative in changed_paths:
        entry = _worktree_entry(
            canonical_root,
            relative,
            index_mode=index_modes.get(relative),
            total_content_bytes=total_content_bytes,
        )
        total_content_bytes += entry.content_bytes
        if total_content_bytes > MAX_TOTAL_CONTENT_BYTES:
            raise GitManifestCapacityExceeded(
                "total_content_bytes",
                limit=MAX_TOTAL_CONTENT_BYTES,
                observed=total_content_bytes,
            )
        worktree_entries.append(entry)

    return BoundedGitManifest(
        root=canonical_root,
        head_tree=_head_tree(canonical_root),
        index_entries=index_entries,
        status_entries=status_entries,
        worktree_entries=tuple(worktree_entries),
        changed_path_count=len(changed_paths),
        total_content_bytes=total_content_bytes,
    )


def _new_digest(projection: str) -> "hashlib._Hash":
    digest = hashlib.sha256()
    _update_digest(digest, (_SCHEMA, projection))
    return digest


def _update_digest(digest: "hashlib._Hash", fields: Iterable[str]) -> None:
    payload = json.dumps(
        tuple(fields),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8", errors="strict")
    digest.update(len(payload).to_bytes(8, "big"))
    digest.update(payload)


def _run_git(
    root: Path,
    *args: str,
    required: bool = True,
) -> bytes | None:
    environment = dict(os.environ)
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            env=environment,
        )
    except OSError as error:
        raise GitManifestInspectionError("Git inspection could not start") from error
    if completed.returncode != 0:
        if not required:
            return None
        raise GitManifestInspectionError("required Git inspection failed")
    return completed.stdout


def _head_tree(root: Path) -> str:
    raw = _run_git(root, "rev-parse", "--verify", "HEAD^{tree}", required=False)
    if raw is None:
        return _UNBORN_HEAD
    try:
        value = raw.decode("ascii", errors="strict").strip()
    except UnicodeDecodeError as error:
        raise GitManifestInspectionError("HEAD tree identity is invalid") from error
    if not value or any(character not in "0123456789abcdef" for character in value):
        raise GitManifestInspectionError("HEAD tree identity is invalid")
    return value


def _index_entries(root: Path) -> tuple[GitIndexEntry, ...]:
    raw = _run_git(root, "ls-files", "--stage", "-z")
    assert raw is not None
    entries: list[GitIndexEntry] = []
    for record in (item for item in raw.split(b"\0") if item):
        try:
            metadata, raw_path = record.split(b"\t", 1)
            raw_mode, raw_object_id, raw_stage = metadata.split(b" ", 2)
            mode = raw_mode.decode("ascii", errors="strict")
            object_id = raw_object_id.decode("ascii", errors="strict")
            stage = int(raw_stage.decode("ascii", errors="strict"))
            path = _decode_path(raw_path)
        except (UnicodeDecodeError, ValueError) as error:
            raise GitManifestInspectionError("Git index entry is invalid") from error
        if (
            len(mode) != 6
            or any(character not in "01234567" for character in mode)
            or not object_id
            or any(character not in "0123456789abcdef" for character in object_id)
            or stage not in {0, 1, 2, 3}
        ):
            raise GitManifestInspectionError("Git index entry is invalid")
        entries.append(GitIndexEntry(path, mode, object_id, stage))
    return tuple(sorted(entries, key=lambda item: (item.path, item.stage)))


def _status_entries(root: Path) -> tuple[GitStatusEntry, ...]:
    raw = _run_git(
        root,
        "status",
        "--porcelain=v2",
        "-z",
        "--untracked-files=all",
        "--no-renames",
        "--ignore-submodules=none",
    )
    assert raw is not None
    records = raw.split(b"\0")
    entries: list[GitStatusEntry] = []
    index = 0
    while index < len(records):
        record = records[index]
        index += 1
        if not record:
            continue
        try:
            marker = record[:1]
            if marker == b"1":
                parts = record.split(b" ", 8)
                if len(parts) != 9:
                    raise ValueError
                entries.append(
                    GitStatusEntry(
                        "ordinary",
                        _decode_ascii_fields(parts[1:8]),
                        _decode_path(parts[8]),
                    )
                )
            elif marker == b"2":
                parts = record.split(b" ", 9)
                if len(parts) != 10 or index >= len(records):
                    raise ValueError
                original = records[index]
                index += 1
                if not original:
                    raise ValueError
                entries.append(
                    GitStatusEntry(
                        "rename",
                        _decode_ascii_fields(parts[1:9]),
                        _decode_path(parts[9]),
                        _decode_path(original),
                    )
                )
            elif marker == b"u":
                parts = record.split(b" ", 10)
                if len(parts) != 11:
                    raise ValueError
                entries.append(
                    GitStatusEntry(
                        "unmerged",
                        _decode_ascii_fields(parts[1:10]),
                        _decode_path(parts[10]),
                    )
                )
            elif marker == b"?" and record.startswith(b"? "):
                entries.append(
                    GitStatusEntry("untracked", (), _decode_path(record[2:]))
                )
            elif marker == b"!" and record.startswith(b"! "):
                continue
            else:
                raise ValueError
        except (UnicodeDecodeError, ValueError) as error:
            raise GitManifestInspectionError("Git status entry is invalid") from error
    return tuple(
        sorted(
            entries,
            key=lambda item: (
                item.path,
                item.original_path or "",
                item.record_kind,
                item.fields,
            ),
        )
    )


def _decode_ascii_fields(fields: Iterable[bytes]) -> tuple[str, ...]:
    return tuple(field.decode("ascii", errors="strict") for field in fields)


def _decode_path(raw: bytes) -> str:
    try:
        value = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise GitManifestInspectionError("Git path is not UTF-8") from error
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or "\x00" in value:
        raise GitManifestInspectionError("Git path is unsafe")
    return value


def _worktree_entry(
    root: Path,
    relative: str,
    *,
    index_mode: str | None,
    total_content_bytes: int,
) -> GitWorktreeEntry:
    candidate = root.joinpath(*PurePosixPath(relative).parts)
    try:
        metadata = candidate.lstat()
    except FileNotFoundError:
        return GitWorktreeEntry(relative, "missing", "000000", "", 0)
    except OSError as error:
        raise GitManifestInspectionError(
            "worktree entry metadata is unavailable"
        ) from error

    if stat.S_ISLNK(metadata.st_mode):
        try:
            payload = os.readlink(candidate).encode("utf-8", errors="strict")
        except (OSError, UnicodeEncodeError) as error:
            raise GitManifestInspectionError("symlink target is unavailable") from error
        _enforce_content_capacity(len(payload), total_content_bytes)
        return GitWorktreeEntry(
            relative,
            "symlink",
            "120000",
            _worktree_content_identity(payload),
            len(payload),
        )

    if index_mode == "160000" and stat.S_ISDIR(metadata.st_mode):
        raw_head = _run_git(candidate, "rev-parse", "--verify", "HEAD")
        assert raw_head is not None
        try:
            object_id = raw_head.decode("ascii", errors="strict").strip()
        except UnicodeDecodeError as error:
            raise GitManifestInspectionError("submodule identity is invalid") from error
        if not object_id or any(
            character not in "0123456789abcdef" for character in object_id
        ):
            raise GitManifestInspectionError("submodule identity is invalid")
        return GitWorktreeEntry(relative, "submodule", "160000", object_id, 0)

    if stat.S_ISDIR(metadata.st_mode):
        # ``--untracked-files=all`` normally expands directories to files.  A
        # directory record here is typically an unregistered nested repository
        # (or a sparse boundary), whose contents Git did not enumerate.  A
        # marker-only digest would permit undetected changes below that path.
        raise GitManifestInspectionError(
            "Git-visible directory lacks a bounded submodule identity"
        )
    if not stat.S_ISREG(metadata.st_mode):
        raise GitManifestInspectionError("worktree entry has an unsupported type")

    if metadata.st_size > MAX_CONTENT_BYTES_PER_PATH:
        raise GitManifestCapacityExceeded(
            "content_bytes_per_path",
            limit=MAX_CONTENT_BYTES_PER_PATH,
            observed=metadata.st_size,
        )
    _enforce_total_capacity(metadata.st_size, total_content_bytes)
    payload = _read_bounded_file(candidate)
    _enforce_content_capacity(len(payload), total_content_bytes)
    try:
        after = candidate.lstat()
    except OSError as error:
        raise GitManifestInspectionError(
            "worktree entry changed during inspection"
        ) from error
    if (
        after.st_size != metadata.st_size
        or after.st_mtime_ns != metadata.st_mtime_ns
        or after.st_mode != metadata.st_mode
    ):
        raise GitManifestInspectionError("worktree entry changed during inspection")
    if os.name == "nt" and index_mode in {"100644", "100755"}:
        mode = index_mode
    else:
        mode = "100755" if metadata.st_mode & 0o111 else "100644"
    return GitWorktreeEntry(
        relative,
        "file",
        mode,
        _worktree_content_identity(payload),
        len(payload),
    )


def _read_bounded_file(path: Path) -> bytes:
    payload = bytearray()
    try:
        with path.open("rb") as stream:
            while True:
                remaining = MAX_CONTENT_BYTES_PER_PATH - len(payload)
                chunk = stream.read(min(64 * 1024, remaining + 1))
                if not chunk:
                    break
                payload.extend(chunk)
                if len(payload) > MAX_CONTENT_BYTES_PER_PATH:
                    raise GitManifestCapacityExceeded(
                        "content_bytes_per_path",
                        limit=MAX_CONTENT_BYTES_PER_PATH,
                        observed=len(payload),
                    )
    except GitManifestCapacityExceeded:
        raise
    except OSError as error:
        raise GitManifestInspectionError("worktree file is unreadable") from error
    return bytes(payload)


def _worktree_content_identity(payload: bytes) -> str:
    # Worktree deltas intentionally retain raw bytes; index entries retain the
    # Git-filtered blob identities supplied by Git.  Owner projections decide
    # whether and how to reconcile those two layers.
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _enforce_total_capacity(content_bytes: int, current_total: int) -> None:
    observed = current_total + content_bytes
    if observed > MAX_TOTAL_CONTENT_BYTES:
        raise GitManifestCapacityExceeded(
            "total_content_bytes",
            limit=MAX_TOTAL_CONTENT_BYTES,
            observed=observed,
        )


def _enforce_content_capacity(content_bytes: int, current_total: int) -> None:
    if content_bytes > MAX_CONTENT_BYTES_PER_PATH:
        raise GitManifestCapacityExceeded(
            "content_bytes_per_path",
            limit=MAX_CONTENT_BYTES_PER_PATH,
            observed=content_bytes,
        )
    _enforce_total_capacity(content_bytes, current_total)


def _kind_for_mode(mode: str) -> str:
    if mode == "120000":
        return "symlink"
    if mode == "160000":
        return "submodule"
    return "file"
