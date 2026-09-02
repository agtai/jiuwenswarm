# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""The legacy workspace migration must not delete what it did not relocate.

``_migrate_legacy_workspace`` used to finish with ``shutil.rmtree(agent/home)``
after relocating exactly one file out of it, ``cron_jobs.json``. ``agent/home``
is where ``get_heartbeat_jobs_path`` keeps ``heartbeat_jobs.json``, so every
persisted heartbeat job was destroyed -- no backup, no error, and a log line
reporting the removal as ordinary housekeeping. The same removal ran a second
time from ``prepare_workspace`` on the ``overwrite=True`` branch.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from jiuwenswarm.common import utils
from jiuwenswarm.common.utils import (
    _migrate_legacy_workspace,
    get_heartbeat_jobs_path,
    get_user_workspace_dir,
)

_CRON_DOC = '{"version": 1, "jobs": [{"id": "cron-1"}]}'
_HEARTBEAT_DOC = '{"version": 1, "jobs": [{"id": "hb-1"}]}'


@pytest.fixture
def migration_log():
    """Yield the records the migration's own logger emits.

    ``caplog`` alone sees nothing here: the project's loggers do not propagate
    to the root logger the fixture attaches to, so the handler has to go on the
    emitting logger directly.
    """
    records: list[logging.LogRecord] = []

    class _Collector(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    logger = logging.getLogger(utils.__name__)
    handler = _Collector()
    logger.addHandler(handler)
    previous = logger.level
    logger.setLevel(logging.DEBUG)
    try:
        yield records
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous)


def _legacy_workspace(tmp_path: Path, *, cron: str = _CRON_DOC) -> Path:
    """A pre-DeepAgent workspace holding both job stores in ``agent/home``."""
    workspace = tmp_path / ".jiuwenswarm"
    old_home = workspace / "agent" / "home"
    old_home.mkdir(parents=True)
    (old_home / "PRINCIPLE.md").write_text("be helpful\n", encoding="utf-8")
    (old_home / "TONE.md").write_text("be brief\n", encoding="utf-8")
    (old_home / "cron_jobs.json").write_text(cron, encoding="utf-8")
    (old_home / "heartbeat_jobs.json").write_text(
        _HEARTBEAT_DOC, encoding="utf-8"
    )
    return workspace


def _served_workspace(tmp_path: Path, *, cron: str = _CRON_DOC) -> Path:
    """A legacy workspace a running gateway has already opened the store in.

    The difference from ``_legacy_workspace`` is one empty file. Reading the
    cron store takes a cross-process lock on ``cron_jobs.json.lock`` beside the
    data, so every deployment that ever started reaches the migration with that
    file present -- which is to say, every real one.
    """
    workspace = _legacy_workspace(tmp_path, cron=cron)
    (workspace / "agent" / "home" / "cron_jobs.json.lock").write_text(
        "", encoding="utf-8"
    )
    return workspace


def test_heartbeat_store_lives_in_the_directory_the_migration_clears() -> None:
    """Pin the coupling this whole file is about, so it cannot drift silently."""
    relative = get_heartbeat_jobs_path().relative_to(get_user_workspace_dir())

    assert relative == Path("agent") / "home" / "heartbeat_jobs.json"


def test_migration_keeps_heartbeat_jobs_it_does_not_relocate(
    tmp_path: Path,
) -> None:
    workspace = _legacy_workspace(tmp_path)
    heartbeat = workspace / "agent" / "home" / "heartbeat_jobs.json"

    _migrate_legacy_workspace(workspace)

    # The contrast the defect turns on: cron_jobs.json is the one file the
    # migration rescues, and it is relocated as before.
    assert (workspace / "gateway" / "cron_jobs.json").exists()
    assert heartbeat.exists()
    assert json.loads(heartbeat.read_text(encoding="utf-8")) == {
        "version": 1,
        "jobs": [{"id": "hb-1"}],
    }


def test_migration_warns_about_what_it_leaves_behind(
    tmp_path: Path, migration_log: list[logging.LogRecord]
) -> None:
    workspace = _legacy_workspace(tmp_path)

    _migrate_legacy_workspace(workspace)

    warnings = [
        record.getMessage()
        for record in migration_log
        if record.levelno >= logging.WARNING
    ]
    assert any("heartbeat_jobs.json" in message for message in warnings), warnings


def test_migration_still_retires_the_superseded_soul_files(
    tmp_path: Path,
) -> None:
    """Preserving unmigrated data must not turn into preserving everything.

    PRINCIPLE.md and TONE.md are merged into SOUL.md, so they are the
    migration's to remove -- and removing them is what stops the workspace from
    being classified legacy again on the next start.
    """
    workspace = _legacy_workspace(tmp_path)
    old_home = workspace / "agent" / "home"

    _migrate_legacy_workspace(workspace)

    assert (workspace / "agent" / "workspace" / "SOUL.md").exists()
    assert not (old_home / "PRINCIPLE.md").exists()
    assert not (old_home / "TONE.md").exists()


def test_nothing_is_deleted_when_the_relocation_fails(tmp_path: Path) -> None:
    """Fail safe: a relocation that did not complete authorises no deletion.

    An unreadable ``cron_jobs.json`` makes step 5 log and continue. The cleanup
    used to run regardless and delete the file it had just failed to copy,
    along with everything else in the directory.
    """
    workspace = _legacy_workspace(tmp_path, cron="{not json")
    old_home = workspace / "agent" / "home"

    _migrate_legacy_workspace(workspace)

    assert not (workspace / "gateway" / "cron_jobs.json").exists()
    assert (old_home / "cron_jobs.json").read_text(encoding="utf-8") == "{not json"
    assert (old_home / "heartbeat_jobs.json").exists()


def test_workspace_init_keeps_heartbeat_jobs(tmp_path: Path) -> None:
    """The ``overwrite=True`` branch removes ``agent/home`` on its own path."""
    workspace = _legacy_workspace(tmp_path)
    heartbeat = workspace / "agent" / "home" / "heartbeat_jobs.json"

    utils.prepare_workspace(
        overwrite=True,
        preferred_language="en",
        workspace_dir=workspace,
    )

    assert heartbeat.exists()
    assert json.loads(heartbeat.read_text(encoding="utf-8"))["jobs"] == [
        {"id": "hb-1"}
    ]


def test_old_home_is_removed_once_nothing_is_left_in_it(tmp_path: Path) -> None:
    """The directory still goes away when it holds only migrated entries."""
    workspace = tmp_path / ".jiuwenswarm"
    old_home = workspace / "agent" / "home"
    old_home.mkdir(parents=True)
    (old_home / "PRINCIPLE.md").write_text("be helpful\n", encoding="utf-8")

    _migrate_legacy_workspace(workspace)

    assert not old_home.exists()


def test_the_cron_store_really_does_keep_a_lock_beside_its_data(
    tmp_path: Path,
) -> None:
    """Pin the coupling the lock handling depends on, as with the store path.

    The cleanup knows the suffix rather than asking the store for it, so this
    is where a store that renamed its lock -- or stopped keeping one -- has to
    fail. Asserted by reading through the store rather than by reaching into
    it, so the pin holds against the file the store actually creates.
    """
    import asyncio

    from jiuwenswarm.gateway.cron.store import CronJobStore

    store_path = tmp_path / "cron_jobs.json"
    store_path.write_text(_CRON_DOC, encoding="utf-8")

    asyncio.run(CronJobStore(path=store_path).list_jobs())

    assert (tmp_path / "cron_jobs.json.lock").exists()


def test_the_store_lock_is_retired_with_the_store_it_belongs_to(
    tmp_path: Path,
) -> None:
    """A relocated store leaves no lock behind to keep ``agent/home`` alive.

    The lock is sidecar state, not content: it holds no jobs, and the store at
    its new path takes a fresh one. Left in place it is counted a survivor, so
    the directory is kept, the workspace stays classified legacy, and the
    migration runs and warns again on every single start -- about an empty
    file.
    """
    workspace = _served_workspace(tmp_path)
    old_home = workspace / "agent" / "home"
    (old_home / "heartbeat_jobs.json").unlink()

    _migrate_legacy_workspace(workspace)

    assert (workspace / "gateway" / "cron_jobs.json").exists()
    assert not old_home.exists(), sorted(
        item.name for item in old_home.iterdir()
    )


def test_a_surviving_store_keeps_its_lock(tmp_path: Path) -> None:
    """The lock follows its own store, not the run.

    ``heartbeat_jobs.json`` is not relocated, so nothing about it may be
    deleted -- a lock removed from under a store that stayed put is a
    cross-process mutex silently dropped while a gateway may be holding it.
    """
    workspace = _served_workspace(tmp_path)
    old_home = workspace / "agent" / "home"
    heartbeat_lock = old_home / "heartbeat_jobs.json.lock"
    heartbeat_lock.write_text("", encoding="utf-8")

    _migrate_legacy_workspace(workspace)

    assert heartbeat_lock.exists()
    assert not (old_home / "cron_jobs.json.lock").exists()


def test_a_failed_relocation_keeps_the_lock_with_its_store(
    tmp_path: Path,
) -> None:
    """Fail safe applies to the lock as well: no relocation, no deletion."""
    workspace = _served_workspace(tmp_path, cron="{not json")
    old_home = workspace / "agent" / "home"

    _migrate_legacy_workspace(workspace)

    assert (old_home / "cron_jobs.json").exists()
    assert (old_home / "cron_jobs.json.lock").exists()
