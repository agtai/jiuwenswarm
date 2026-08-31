# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from jiuwenswarm.common.bounded_git_manifest import (
    MAX_CHANGED_PATHS,
    MAX_CONTENT_BYTES_PER_PATH,
    MAX_TOTAL_CONTENT_BYTES,
    GitManifestCapacityExceeded,
    GitManifestInspectionError,
    capture_bounded_git_manifest,
)


def _git(project: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(project), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return completed.stdout.strip()


def _project(project: Path, *, filename: str = "tracked.txt") -> None:
    project.mkdir(parents=True)
    _git(project, "init", "-q")
    _git(project, "config", "user.name", "Bounded Manifest Test")
    _git(project, "config", "user.email", "manifest@example.invalid")
    (project / filename).write_text("baseline\n", encoding="utf-8")
    _git(project, "add", ".")
    _git(project, "commit", "-q", "-m", "baseline")


def test_frozen_manifest_capacities_are_explicit() -> None:
    assert MAX_CHANGED_PATHS == 32
    assert MAX_CONTENT_BYTES_PER_PATH == 1 * 1024 * 1024
    assert MAX_TOTAL_CONTENT_BYTES == 16 * 1024 * 1024


def test_staged_and_unstaged_same_path_consumes_one_distinct_slot(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    _project(project)
    tracked = project / "tracked.txt"
    tracked.write_text("staged\n", encoding="utf-8")
    _git(project, "add", "tracked.txt")
    tracked.write_text("staged and unstaged\n", encoding="utf-8")
    for index in range(MAX_CHANGED_PATHS - 1):
        (project / f"new-{index:02d}.txt").write_text("new\n", encoding="utf-8")

    manifest = capture_bounded_git_manifest(project)

    assert manifest.changed_path_count == MAX_CHANGED_PATHS
    assert {entry.path for entry in manifest.worktree_entries} == {
        "tracked.txt",
        *(f"new-{index:02d}.txt" for index in range(MAX_CHANGED_PATHS - 1)),
    }

    (project / "one-too-many.txt").write_text("overflow\n", encoding="utf-8")
    with pytest.raises(GitManifestCapacityExceeded) as raised:
        capture_bounded_git_manifest(project)
    assert raised.value.dimension == "changed_paths"
    assert raised.value.observed == MAX_CHANGED_PATHS + 1


def test_single_content_file_limit_is_inclusive(tmp_path: Path) -> None:
    project = tmp_path / "project"
    _project(project)
    candidate = project / "candidate.bin"
    candidate.write_bytes(b"a" * MAX_CONTENT_BYTES_PER_PATH)

    at_limit = capture_bounded_git_manifest(project)

    assert at_limit.total_content_bytes == MAX_CONTENT_BYTES_PER_PATH
    candidate.write_bytes(b"a" * (MAX_CONTENT_BYTES_PER_PATH + 1))
    with pytest.raises(GitManifestCapacityExceeded) as raised:
        capture_bounded_git_manifest(project)
    assert raised.value.dimension == "content_bytes_per_path"
    assert raised.value.observed == MAX_CONTENT_BYTES_PER_PATH + 1


def test_large_clean_tracked_file_uses_index_blob_without_worktree_read(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    _project(project)
    large = project / "large.bin"
    large.write_bytes(b"a" * (MAX_CONTENT_BYTES_PER_PATH + 1))
    _git(project, "add", "large.bin")
    _git(project, "commit", "-q", "-m", "large tracked baseline")

    clean = capture_bounded_git_manifest(project)

    assert clean.changed_path_count == 0
    assert clean.total_content_bytes == 0
    assert any(entry.path == "large.bin" for entry in clean.index_entries)


def test_total_content_limit_is_inclusive(tmp_path: Path) -> None:
    project = tmp_path / "project"
    _project(project)
    file_count = MAX_TOTAL_CONTENT_BYTES // MAX_CONTENT_BYTES_PER_PATH
    for index in range(file_count):
        (project / f"chunk-{index:02d}.bin").write_bytes(
            bytes([index]) * MAX_CONTENT_BYTES_PER_PATH
        )

    at_limit = capture_bounded_git_manifest(project)

    assert at_limit.total_content_bytes == MAX_TOTAL_CONTENT_BYTES
    (project / "overflow.bin").write_bytes(b"x")
    with pytest.raises(GitManifestCapacityExceeded) as raised:
        capture_bounded_git_manifest(project)
    assert raised.value.dimension == "total_content_bytes"
    assert raised.value.observed == MAX_TOTAL_CONTENT_BYTES + 1


def test_tree_and_content_keep_distinct_staging_semantics(tmp_path: Path) -> None:
    project = tmp_path / "project"
    _project(project)
    (project / "tracked.txt").write_text("changed\n", encoding="utf-8")
    unstaged = capture_bounded_git_manifest(project)

    _git(project, "add", "tracked.txt")
    staged = capture_bounded_git_manifest(project)

    assert staged.head_tree == unstaged.head_tree
    assert staged.index_fingerprint() != unstaged.index_fingerprint()
    assert staged.tree_fingerprint() != unstaged.tree_fingerprint()
    assert staged.content_fingerprint() == unstaged.content_fingerprint()


def test_rename_is_canonical_delete_plus_add_and_delete_is_missing(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    _project(project, filename="before.txt")
    baseline = capture_bounded_git_manifest(project)

    _git(project, "mv", "before.txt", "after.txt")
    renamed = capture_bounded_git_manifest(project)

    assert renamed.changed_path_count == 2
    assert [(entry.path, entry.kind) for entry in renamed.worktree_entries] == [
        ("after.txt", "file"),
        ("before.txt", "missing"),
    ]
    assert renamed.tree_fingerprint() != baseline.tree_fingerprint()
    assert renamed.content_fingerprint() != baseline.content_fingerprint()

    _git(project, "commit", "-q", "-m", "rename")
    _git(project, "rm", "after.txt")
    deleted = capture_bounded_git_manifest(project)
    assert any(entry.kind == "missing" for entry in deleted.worktree_entries)


def test_file_mode_is_part_of_index_identity(tmp_path: Path) -> None:
    project = tmp_path / "project"
    _project(project, filename="script.sh")
    baseline = capture_bounded_git_manifest(project)

    _git(project, "update-index", "--chmod=+x", "script.sh")
    executable = capture_bounded_git_manifest(project)

    assert executable.changed_path_count == 1
    assert executable.index_fingerprint() != baseline.index_fingerprint()
    assert any(
        entry.path == "script.sh" and entry.mode == "100755"
        for entry in executable.index_entries
    )


def test_symlink_hashes_link_text_without_following_target(tmp_path: Path) -> None:
    project = tmp_path / "project"
    _project(project)
    external = tmp_path / "external.bin"
    external.write_bytes(b"x" * (MAX_CONTENT_BYTES_PER_PATH + 1))
    link = project / "link.bin"
    try:
        link.symlink_to(external)
    except OSError as error:
        pytest.skip(f"host cannot create symlinks: {error}")

    manifest = capture_bounded_git_manifest(project)

    link_entry = next(
        entry for entry in manifest.worktree_entries if entry.path == "link.bin"
    )
    assert link_entry.kind == "symlink"
    assert link_entry.mode == "120000"
    assert link_entry.content_bytes == len(os.readlink(link).encode("utf-8"))


def test_submodule_uses_gitlink_identity_without_recursive_content_hashing(
    tmp_path: Path,
) -> None:
    child = tmp_path / "child"
    _project(child)
    project = tmp_path / "project"
    _project(project)
    subprocess.run(
        [
            "git",
            "-c",
            "protocol.file.allow=always",
            "-C",
            str(project),
            "submodule",
            "add",
            "-q",
            str(child.resolve()),
            "module",
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    _git(project, "commit", "-q", "-m", "add submodule")
    baseline = capture_bounded_git_manifest(project)
    module = project / "module"
    _git(module, "config", "user.name", "Bounded Manifest Test")
    _git(module, "config", "user.email", "manifest@example.invalid")
    (module / "tracked.txt").write_text("next\n", encoding="utf-8")
    _git(module, "add", "tracked.txt")
    _git(module, "commit", "-q", "-m", "advance")

    advanced = capture_bounded_git_manifest(project)

    assert advanced.changed_path_count == 1
    assert advanced.total_content_bytes == 0
    assert [
        (entry.path, entry.kind, entry.mode) for entry in advanced.worktree_entries
    ] == [("module", "submodule", "160000")]
    assert advanced.tree_fingerprint() != baseline.tree_fingerprint()


def test_unregistered_nested_repository_is_not_a_marker_only_false_negative(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    _project(project)
    nested = project / "nested"
    _project(nested)

    with pytest.raises(GitManifestInspectionError, match="bounded submodule identity"):
        capture_bounded_git_manifest(project)


@pytest.mark.skipif(os.name != "nt", reason="junction escapes are Windows reparse points")
def test_gitlink_junction_target_fails_closed(tmp_path: Path) -> None:
    """A gitlink path replaced by a junction must not run Git in the target."""
    import shutil

    child = tmp_path / "child"
    _project(child)
    parent = tmp_path / "parent"
    _project(parent)
    subprocess.run(
        [
            "git", "-C", str(parent), "-c", "protocol.file.allow=always",
            "submodule", "add", child.resolve().as_posix(), "vendor/child",
        ],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    _git(parent, "commit", "-q", "-m", "add submodule")
    escape_target = tmp_path / "escape"
    _project(escape_target)
    submodule_path = parent / "vendor" / "child"
    shutil.rmtree(submodule_path)
    subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(submodule_path), str(escape_target)],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )

    with pytest.raises(GitManifestInspectionError):
        capture_bounded_git_manifest(parent)
