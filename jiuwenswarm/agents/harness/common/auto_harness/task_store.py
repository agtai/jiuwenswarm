# jiuwenswarm/agentserver/deep_agent/auto_harness/task_store.py
# Copyright (c) Huawei Technologies Co., Ltd. 2025. All rights reserved.

"""Task metadata storage for scheduled auto_harness tasks."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .run_log_status import (
    META_EVOLVE_STAGE_ORDER,
    ProgressEnricher,
    STAGE_DISPLAY_NAMES,
    SkippedStageInferer,
    TERMINAL_STATUSES,
    determine_pipeline_status_from_log,
    has_terminal_session_event,
    read_key_events_reverse,
    resolve_latest_task_log_path,
    summarize_progress_from_logs,
    summarize_progress_from_key_events,
)

logger = logging.getLogger(__name__)


_STORE_LOCKS_GUARD = threading.Lock()
_STORE_LOCKS_BY_PATH: dict[str, asyncio.Lock] = {}


def _normalized_store_path(path: Path) -> str:
    """Return the process-wide identity for one task index file."""
    return os.path.normcase(str(path.resolve(strict=False)))


def _lock_for_store(path: Path) -> asyncio.Lock:
    """Share read-modify-write coordination across store instances."""
    store_key = _normalized_store_path(path)
    with _STORE_LOCKS_GUARD:
        lock = _STORE_LOCKS_BY_PATH.get(store_key)
        if lock is None:
            lock = asyncio.Lock()
            _STORE_LOCKS_BY_PATH[store_key] = lock
        return lock


def _sync_write_json(path: Path, data: str) -> None:
    """Atomically replace one JSON file — called via asyncio.to_thread."""
    temp_path = path.with_name(
        f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
    )
    try:
        with temp_path.open("w", encoding="utf-8", newline="\n") as file:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp_path, path)
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            logger.warning(
                "[TaskStore] Failed to clean temporary task index: %s",
                temp_path,
            )


class TaskStore:
    """Manages scheduled task metadata and execution logs.

    Storage layout:
        ~/.jiuwenswarm/auto-harness/
        ├── scheduled-tasks.json        # Task index
        └── runs/
            └── sch_abc123/
                ├── exec_001/
                │   └── log.json        # Structured log
                └── latest -> exec_001  # Symlink to latest

    Uses in-memory cache for reads to avoid blocking the asyncio event loop.
    Writes persist to disk via asyncio.to_thread.
    """

    def __init__(self, data_dir: Path):
        self._data_dir = data_dir
        self._tasks_file = data_dir / "scheduled-tasks.json"
        self._runs_dir = data_dir / "runs"
        self._tasks_cache: Optional[dict[str, Any]] = None
        self._store_lock = _lock_for_store(self._tasks_file)
        self._skipped_stage_inferers: list[SkippedStageInferer] = []
        self._progress_enrichers: list[ProgressEnricher] = []
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        """Ensure required directories exist."""
        self._runs_dir.mkdir(parents=True, exist_ok=True)

    def _load_tasks(self) -> dict[str, Any]:
        """Load tasks — returns in-memory cache if available, otherwise reads from file."""
        if self._tasks_cache is not None:
            return self._tasks_cache

        if not self._tasks_file.exists():
            result = {"tasks": [], "last_updated": None}
            self._tasks_cache = result
            return result

        try:
            data = json.loads(self._tasks_file.read_text(encoding="utf-8"))
            self._tasks_cache = data
            return data
        except Exception as e:
            logger.warning("[TaskStore] Failed to load tasks file: %s", e)
            result = {"tasks": [], "last_updated": None}
            self._tasks_cache = result
            return result

    async def _save_tasks(self, data: dict[str, Any]) -> None:
        """Persist a caller-locked snapshot, publishing its cache only on success."""
        data["last_updated"] = datetime.now(timezone.utc).isoformat()
        json_str = json.dumps(data, ensure_ascii=False, indent=2)
        try:
            await asyncio.to_thread(_sync_write_json, self._tasks_file, json_str)
        except Exception:
            # The caller may already have mutated the old cached object. Never
            # expose that uncommitted state after a failed replace.
            self._tasks_cache = None
            raise
        self._tasks_cache = data

    async def add_task(self, task: dict[str, Any]) -> None:
        """Add a new scheduled task."""
        async with self._store_lock:
            self._tasks_cache = None
            data = self._load_tasks()
            data["tasks"].append(task)
            await self._save_tasks(data)
        logger.info("[TaskStore] Added task: %s", task.get("task_id"))

    async def get_or_create_task_for_command(
        self,
        task: dict[str, Any],
        *,
        owner_scope: dict[str, str],
        origin_namespace: str,
        idempotency_key: str,
        fingerprint: str,
    ) -> dict[str, Any]:
        """Atomically persist or replay one idempotent create command.

        This is a single-process guarantee. The command ledger and winning task
        are written in the same JSON snapshot, but the JSON store does not
        provide cross-process compare-and-swap or exactly-once execution.
        """
        async with self._store_lock:
            # Another TaskStore instance for this path may have committed while
            # this instance retained an older cache. Refresh under the shared
            # command lock before deciding replay/conflict/create.
            self._tasks_cache = None
            data = self._load_tasks()
            commands = data.setdefault("create_commands", [])
            for command in commands:
                if not isinstance(command, dict):
                    continue
                if (
                    command.get("owner_scope") != owner_scope
                    or command.get("origin_namespace") != origin_namespace
                    or command.get("idempotency_key") != idempotency_key
                ):
                    continue

                existing_task_id = str(command.get("task_id") or "")
                if command.get("fingerprint") != fingerprint:
                    return {
                        "result": "conflict",
                        "existing_task_id": existing_task_id,
                    }

                existing_task = next(
                    (
                        item
                        for item in data.get("tasks", [])
                        if item.get("task_id") == existing_task_id
                    ),
                    None,
                )
                return {
                    "result": "replay",
                    "task_id": existing_task_id,
                    "task": dict(existing_task) if existing_task is not None else None,
                    "deleted_at": command.get("deleted_at"),
                    "owner_scope": command.get("owner_scope"),
                    "origin_namespace": command.get("origin_namespace"),
                    "idempotency_key": command.get("idempotency_key"),
                    "execution_target": command.get("execution_target"),
                    "execution_contract": command.get("execution_contract"),
                }

            task_id = str(task.get("task_id") or "")
            if not task_id:
                raise ValueError("task_id is required")
            if any(item.get("task_id") == task_id for item in data.get("tasks", [])):
                raise ValueError(f"Task already exists: {task_id}")

            created_at = datetime.now(timezone.utc).isoformat()
            data.setdefault("tasks", []).append(task)
            command_record = {
                "owner_scope": dict(owner_scope),
                "origin_namespace": origin_namespace,
                "idempotency_key": idempotency_key,
                "fingerprint": fingerprint,
                "task_id": task_id,
                "execution_target": dict(task.get("execution_target") or {}),
                "created_at": created_at,
                "deleted_at": None,
            }
            if isinstance(task.get("execution_contract"), dict):
                command_record["execution_contract"] = dict(
                    task["execution_contract"]
                )
            commands.append(command_record)
            await self._save_tasks(data)
            logger.info(
                "[TaskStore] Added idempotent task: %s namespace=%s",
                task_id,
                origin_namespace,
            )
            return {
                "result": "created",
                "task_id": task_id,
                "task": dict(task),
            }

    def list_tasks_for_create_command(
        self,
        *,
        owner_scope: dict[str, str],
        origin_namespace: str,
        idempotency_key: str | None = None,
    ) -> list[dict[str, Any]]:
        """List live tasks matching an exact owner scope and command namespace."""
        data = self._load_tasks()
        matching_task_ids: list[str] = []
        for command in data.get("create_commands", []):
            if not isinstance(command, dict):
                continue
            if command.get("owner_scope") != owner_scope:
                continue
            if command.get("origin_namespace") != origin_namespace:
                continue
            if (
                idempotency_key is not None
                and command.get("idempotency_key") != idempotency_key
            ):
                continue
            task_id = command.get("task_id")
            if isinstance(task_id, str) and task_id:
                matching_task_ids.append(task_id)

        tasks_by_id = {
            task.get("task_id"): task
            for task in data.get("tasks", [])
            if isinstance(task, dict)
        }
        return [
            tasks_by_id[task_id]
            for task_id in matching_task_ids
            if task_id in tasks_by_id
        ]

    async def update_task(self, task_id: str, updates: dict[str, Any]) -> None:
        """Update an existing task."""
        async with self._store_lock:
            self._tasks_cache = None
            data = self._load_tasks()
            for task in data.get("tasks", []):
                if task.get("task_id") == task_id:
                    task.update(updates)
                    break
            await self._save_tasks(data)

    def get_task(self, task_id: str) -> Optional[dict[str, Any]]:
        """Get task by ID — reads from in-memory cache (zero I/O)."""
        data = self._load_tasks()
        for task in data.get("tasks", []):
            if task.get("task_id") == task_id:
                return task
        return None

    def list_tasks(self) -> list[dict[str, Any]]:
        """List all tasks — reads from in-memory cache (zero I/O)."""
        data = self._load_tasks()
        return data.get("tasks", [])

    def register_run_log_status_extension(
        self,
        *,
        skipped_stage_inferer: SkippedStageInferer | None = None,
        progress_enricher: ProgressEnricher | None = None,
    ) -> None:
        """Register optional run-log status extensions for specialized capabilities."""
        if skipped_stage_inferer is not None and skipped_stage_inferer not in self._skipped_stage_inferers:
            self._skipped_stage_inferers.append(skipped_stage_inferer)
        if progress_enricher is not None and progress_enricher not in self._progress_enrichers:
            self._progress_enrichers.append(progress_enricher)

    def summarize_progress_from_logs(self, logs: Optional[list[dict[str, Any]]] = None) -> dict[str, Any]:
        """Summarize stage progress from structured harness logs."""
        if logs is None:
            logs = []
        return summarize_progress_from_logs(
            logs,
            skipped_stage_inferers=self._skipped_stage_inferers,
            progress_enrichers=self._progress_enrichers,
        )

    def determine_pipeline_status_from_log(self, log_path: Path) -> dict[str, Any]:
        """Determine pipeline status with registered run-log extensions."""
        return determine_pipeline_status_from_log(
            log_path,
            skipped_stage_inferers=self._skipped_stage_inferers,
        )

    async def summarize_task_progress(self, task: dict[str, Any]) -> dict[str, Any]:
        """Read the latest task log and return a compact progress summary.

        对所有任务（含终态）都读取日志获取阶段数据。
        终态任务读取完整日志（以运行 enrichers 提取 PR URL 等），
        运行中任务反向读取关键事件以提升性能。
        """
        log_path = resolve_latest_task_log_path(task, self._runs_dir)
        if not log_path:
            return {
                "summary": "暂无执行日志",
                "stages": [
                    {
                        "stage": stage,
                        "name": STAGE_DISPLAY_NAMES.get(stage, stage),
                        "status": "pending",
                        "messages": [],
                    }
                    for stage in META_EVOLVE_STAGE_ORDER
                ],
                "completed_stages": [],
                "current_stage": "",
                "failed_stage": "",
            }

        task_status = str(task.get("status") or "")
        if task_status in TERMINAL_STATUSES:
            # 终态任务：读取完整日志以运行 enrichers（如提取 PR URL）
            logs = await asyncio.to_thread(self.read_log, log_path, 0, -1)
            progress = self.summarize_progress_from_logs(logs)
        else:
            # 运行中任务：反向读取关键事件
            key_events = await asyncio.to_thread(read_key_events_reverse, log_path, 20)
            if key_events:
                progress = summarize_progress_from_key_events(key_events)
            else:
                # 关键事件为空，读取完整日志
                logs = await asyncio.to_thread(self.read_log, log_path, 0, -1)
                progress = self.summarize_progress_from_logs(logs)

        progress["log_path"] = str(log_path)
        return progress

    async def enrich_task_with_progress(self, task: dict[str, Any]) -> dict[str, Any]:
        """Return a shallow task copy with latest progress attached."""
        enriched = dict(task)
        enriched["progress"] = await self.summarize_task_progress(task)
        return enriched

    async def enrich_tasks_with_progress(self, tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Attach progress summaries to a list of tasks."""
        return [await self.enrich_task_with_progress(task) for task in tasks]

    def list_pending_tasks(self) -> list[dict[str, Any]]:
        """List tasks with status 'pending' that are due for execution."""
        data = self._load_tasks()
        now = datetime.now(timezone.utc)
        pending = []
        for task in data.get("tasks", []):
            if task.get("status") != "pending":
                continue
            next_run_str = task.get("next_run_time")
            if not next_run_str:
                continue
            try:
                next_run = datetime.fromisoformat(next_run_str)
                if now >= next_run:
                    pending.append(task)
            except ValueError:
                logger.warning(
                    "[TaskStore] Invalid next_run_time format for task %s: %s",
                    task.get("task_id"), next_run_str
                )
                continue
        return pending

    async def delete_task(self, task_id: str) -> bool:
        """Delete a task and its log files.

        Args:
            task_id: Task identifier

        Returns:
            True if task was deleted, False if not found
        """
        async with self._store_lock:
            self._tasks_cache = None
            data = self._load_tasks()
            tasks = data.get("tasks", [])

            task_found = False
            deleted_task: dict[str, Any] | None = None
            new_tasks = []
            for task in tasks:
                if task.get("task_id") == task_id:
                    task_found = True
                    deleted_task = task
                else:
                    new_tasks.append(task)

            if not task_found:
                return False

            deleted_at = datetime.now(timezone.utc).isoformat()
            for command in data.get("create_commands", []):
                if isinstance(command, dict) and command.get("task_id") == task_id:
                    command["deleted_at"] = deleted_at
                    assert deleted_task is not None
                    command.setdefault(
                        "owner_scope",
                        deleted_task.get("owner_scope"),
                    )
                    command.setdefault(
                        "origin_namespace",
                        deleted_task.get("origin_namespace"),
                    )
                    command.setdefault(
                        "idempotency_key",
                        deleted_task.get("idempotency_key"),
                    )
                    command.setdefault(
                        "execution_target",
                        dict(deleted_task.get("execution_target") or {}),
                    )

            data["tasks"] = new_tasks
            await self._save_tasks(data)

        # Remove log directory (in thread to avoid blocking event loop)
        run_dir = self._runs_dir / task_id
        if run_dir.exists():
            try:
                await asyncio.to_thread(shutil.rmtree, run_dir)
                logger.info("[TaskStore] Removed log directory for task: %s", task_id)
            except Exception as e:
                logger.warning("[TaskStore] Failed to remove log directory: %s", e)

        logger.info("[TaskStore] Deleted task: %s", task_id)
        return True

    async def add_execution_record(self, task_id: str, record: dict[str, Any]) -> None:
        """Add or replace an execution record, idempotently by execution ID."""
        async with self._store_lock:
            self._tasks_cache = None
            data = self._load_tasks()
            for task in data.get("tasks", []):
                if task.get("task_id") == task_id:
                    history = task.get("execution_history", [])
                    execution_id = record.get("execution_id")
                    replaced = False
                    if execution_id:
                        for index, existing in enumerate(history):
                            if existing.get("execution_id") == execution_id:
                                history[index] = {**existing, **record}
                                replaced = True
                                break
                    if not replaced:
                        history.append(record)
                    task["execution_history"] = history
                    break
            await self._save_tasks(data)

    def get_log_path(self, task_id: str, execution_id: str) -> Path:
        """Get path for execution log file."""
        run_dir = self._runs_dir / task_id / execution_id
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir / "log.json"

    @staticmethod
    def write_log(path: Path, chunks: list[dict[str, Any]]) -> None:
        """Write structured log chunks to file (JSON Lines format)."""
        with path.open("w", encoding="utf-8") as f:
            for chunk in chunks:
                f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    @staticmethod
    def read_log(path: Path, offset: int = 0, limit: int = 500) -> list[dict[str, Any]]:
        """Read log file (JSON Lines format).

        Supports both JSON Lines format (one JSON object per line) and
        legacy array format for backwards compatibility.

        Args:
            path: Log file path
            offset: Skip this many valid JSON entries
            limit: Maximum number of valid JSON entries to return (default 500, -1 = read all)
        """
        if not path.exists():
            return []

        try:
            logs = []
            valid_count = 0
            read_all = limit <= 0
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        valid_count += 1
                        if valid_count <= offset:
                            continue
                        if read_all or len(logs) < limit:
                            logs.append(entry)
                        else:
                            break
                    except json.JSONDecodeError:
                        pass
            return logs
        except Exception as e:
            logger.warning("[TaskStore] Failed to read log as JSON Lines: %s, trying legacy format", e)

        # Legacy array format fallback (only if JSON Lines failed)
        try:
            content = path.read_text(encoding="utf-8").strip()
            if not content:
                return []
            logs = json.loads(content)
            if isinstance(logs, list):
                return logs[offset:offset + limit]
        except json.JSONDecodeError:
            pass

        return []

    @staticmethod
    def get_log_line_count(path: Path) -> int:
        """Get number of valid JSON entries in log file for streaming offset tracking."""
        if not path.exists():
            return 0
        try:
            count = 0
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        json.loads(line)
                        count += 1
                    except json.JSONDecodeError:
                        pass
            return count
        except Exception as e:
            logger.warning("[TaskStore] Failed to count log lines: %s", e)
            return 0

    async def get_logs(
        self,
        task_id: str,
        log_type: str,
        history_index: int = -1,
        offset: int = 0,
        limit: int = 500
    ) -> dict[str, Any]:
        """Get logs for a task — file reads are done via asyncio.to_thread.

        Args:
            task_id: Task identifier
            log_type: "current" or "history"
            history_index: 0=latest completed, 1=second latest, etc.
            offset: Start reading from this line index (for streaming, default 0)
            limit: Maximum number of lines to return (default 500)

        Returns:
            Dict with logs content and metadata
        """
        task = self.get_task(task_id)
        if not task:
            return {"error": "任务不存在", "task_id": task_id}

        if log_type == "current":
            current_exec_id = task.get("current_execution_id")
            if not current_exec_id:
                return {"error": "当前无正在执行的日志", "task_id": task_id}

            log_path = self._runs_dir / task_id / current_exec_id / "log.json"
            logs = await asyncio.to_thread(self.read_log, log_path, offset, limit)
            total_lines = await asyncio.to_thread(self.get_log_line_count, log_path)
            return {
                "logs": logs,
                "execution_id": current_exec_id,
                "type": "current",
                "total_lines": total_lines,
                "is_running": task.get("status") == "running",
                "has_more": offset + len(logs) < total_lines,
            }

        elif log_type == "history":
            history = task.get("execution_history", [])
            if not history:
                return {"error": "无历史执行记录", "task_id": task_id}

            if history_index < 0 or history_index >= len(history):
                return {"error": f"历史记录索引超出范围 (0-{len(history)-1})", "task_id": task_id}

            sorted_history = sorted(
                history,
                key=lambda r: r.get("completed_at", ""),
                reverse=True
            )

            record = sorted_history[history_index]
            log_path_str = record.get("log_path", "")
            if not log_path_str:
                return {"error": "日志路径为空", "record": record}

            log_path = Path(log_path_str)
            if not log_path.exists():
                log_path = self._runs_dir / task_id / record.get("execution_id", "") / "log.json"

            logs = await asyncio.to_thread(self.read_log, log_path, offset, limit)
            total_lines = await asyncio.to_thread(self.get_log_line_count, log_path)
            if logs:
                return {
                    "logs": logs,
                    "execution_id": record.get("execution_id"),
                    "type": "history",
                    "completed_at": record.get("completed_at"),
                    "status": record.get("status"),
                    "total_lines": total_lines,
                    "has_more": offset + len(logs) < total_lines,
                }
            return {"error": "日志文件不存在或为空", "record": record}

        return {"error": f"未知的 log_type: {log_type}"}

    def has_legacy_completed_tasks(self) -> bool:
        """Check if any task may need log-based status reconciliation."""
        data = self._load_tasks()
        return any(t.get("status") in {"completed", "running"} for t in data.get("tasks", []))

    async def reconcile_task_statuses(self) -> int:
        """Re-check task logs and fix stale status values."""
        async with self._store_lock:
            self._tasks_cache = None
            data = self._load_tasks()
            corrected = 0

            for task in data.get("tasks", []):
                task_id = task.get("task_id")
                old_status = task.get("status")

                if old_status not in ("completed", "success", "failed", "running"):
                    continue

                history = task.get("execution_history", [])
                latest = history[-1] if history else None
                current_execution_id = str(task.get("current_execution_id") or "")
                log_path = resolve_latest_task_log_path(task, self._runs_dir)
                orphaned_running = old_status == "running" and (
                    log_path is None or not has_terminal_session_event(log_path)
                )
                if orphaned_running:
                    completed_at = datetime.now(timezone.utc).isoformat()
                    error = "任务执行在服务重启后失去运行上下文"
                    task.update(
                        {
                            "status": "failed",
                            "current_execution_id": None,
                            "last_error": error,
                            "completed_at": completed_at,
                        }
                    )
                    if (
                        latest is None
                        or (
                            current_execution_id
                            and latest.get("execution_id") != current_execution_id
                        )
                    ):
                        latest = {
                            "execution_id": current_execution_id or "unknown",
                            "started_at": task.get("created_at"),
                        }
                        if log_path is not None:
                            latest["log_path"] = str(log_path)
                        history.append(latest)
                        task["execution_history"] = history
                    latest.update(
                        {
                            "status": "failed",
                            "error": error,
                            "completed_at": completed_at,
                        }
                    )
                    corrected += 1
                    logger.warning(
                        "[TaskStore] Reconciled orphaned running task %s as failed",
                        task_id,
                    )
                    continue

                if log_path is None:
                    continue

                result = self.determine_pipeline_status_from_log(log_path)
                new_status = "failed" if result["failed"] else "success"

                if new_status != old_status:
                    task["status"] = new_status
                    task["current_execution_id"] = None
                    if latest is None or latest.get("execution_id") != current_execution_id:
                        latest = {
                            "execution_id": current_execution_id,
                            "started_at": task.get("created_at"),
                            "completed_at": datetime.now(timezone.utc).isoformat(),
                            "log_path": str(log_path),
                        }
                        history.append(latest)
                        task["execution_history"] = history
                    latest["status"] = new_status
                    if result["error"]:
                        latest["error"] = result["error"]
                    corrected += 1
                    logger.info(
                        "[TaskStore] Reconciled task %s: %s -> %s",
                        task_id, old_status, new_status,
                    )

            if corrected > 0:
                await self._save_tasks(data)

            return corrected
