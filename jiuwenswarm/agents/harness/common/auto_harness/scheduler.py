# jiuwenswarm/agentserver/deep_agent/auto_harness/scheduler.py
# Copyright (c) Huawei Technologies Co., Ltd. 2025. All rights reserved.

"""Scheduler for recurring auto_harness task execution."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from openjiuwen.rsi.auto_harness.pipelines import META_EVOLVE_PIPELINE
from openjiuwen.core.foundation.llm import Model

from jiuwenswarm.agents.harness.common.tools.command_tools import (
    forbid_background_project_shell_commands,
)
from jiuwenswarm.common.bounded_git_manifest import (
    BoundedGitManifestError,
    GitManifestCapacityExceeded,
    capture_bounded_git_manifest,
)

from .project_execution import (
    PROJECT_CODE_ARTIFACT_KIND,
    PROJECT_CODE_EFFECT_POLICY,
    PROJECT_CODE_EXECUTOR,
    PROJECT_CODE_PIPELINE,
)
from .run_log_status import TERMINAL_STATUSES, has_terminal_session_event

if TYPE_CHECKING:
    from .service import AutoHarnessService
    from .task_store import TaskStore

logger = logging.getLogger(__name__)

TARGET_TREE_CHANGE_REQUIRED = "target_tree_change_required"
NO_EFFECTIVE_TARGET_CHANGE_ERROR = (
    "NO_EFFECTIVE_TARGET_CHANGE: target project has no file changes"
)
_LOG_APPEND_OPEN_RETRY_DELAYS_SECONDS = (0.0, 0.01, 0.05, 0.1, 0.25, 0.5)


def _sync_append_log(log_path: Path, line: str) -> None:
    """Synchronous append+flush for log file — called via asyncio.to_thread."""
    last_error: PermissionError | None = None
    for delay in _LOG_APPEND_OPEN_RETRY_DELAYS_SECONDS:
        if delay:
            time.sleep(delay)
        try:
            stream = log_path.open("a", encoding="utf-8")
        except PermissionError as exc:
            last_error = exc
            continue
        with stream:
            stream.write(line)
            stream.flush()
        return
    assert last_error is not None
    raise last_error


def _snapshot_target_tree(project_dir: str) -> str:
    root = Path(project_dir).resolve()
    if not root.is_dir():
        raise RuntimeError(f"execution target is not a directory: {root}")
    try:
        return capture_bounded_git_manifest(root).tree_fingerprint()
    except GitManifestCapacityExceeded:
        raise
    except BoundedGitManifestError as exc:
        raise RuntimeError(str(exc)) from exc


class Scheduler:
    """Async scheduler that triggers scheduled auto_harness tasks.

    Checks pending tasks every 60 seconds and executes those that are due.
    Uses META_EVOLVE_PIPELINE for TUI channel tasks.
    """

    def __init__(
        self,
        service: "AutoHarnessService",
        task_store: "TaskStore",
    ):
        self._service = service
        self._task_store = task_store
        self._loop_task: Optional[asyncio.Task] = None
        self._running_executions: dict[str, asyncio.Task] = {}
        self._cancellation_tasks: dict[str, asyncio.Task[bool]] = {}
        self._shutdown_interruptions: set[str] = set()
        self._model_cache: dict[str, Model] = {}
        self._default_model: Optional[Model] = None

    def _resolve_model(self, model_name: Optional[str] = None) -> Optional[Model]:
        """Resolve model from jiuwenswarm config (same approach as interface_deep).

        Args:
            model_name: Requested model name, falls back to default if None or not found

        Returns:
            Model instance or None if config cannot be loaded
        """
        # Build model cache if not already done
        if not self._model_cache:
            self._build_model_cache()

        # Resolve by name or use default
        if model_name and model_name in self._model_cache:
            return self._model_cache[model_name]
        return self._default_model

    def _build_model_cache(self) -> None:
        """Build model cache from jiuwenswarm config.yaml (reuse interface_deep logic)."""
        try:
            from jiuwenswarm.common.config import get_config, get_default_models
            # Use the same model building function as interface_deep
            from jiuwenswarm.server.runtime.agent_adapter.interface_deep import build_model_from_entry

            config = get_config()

            # Build from models.defaults list
            for entry in get_default_models(config):
                mcc = entry.get("model_client_config") or {}
                model_name = mcc.get("model_name")
                if not model_name:
                    continue
                mco = entry.get("model_config_obj") or {}
                self._model_cache[model_name] = build_model_from_entry(mcc, mco)

            # Fallback to legacy format if needed (same as interface_deep._build_model_cache_legacy)
            if not self._model_cache:
                default_model_config = config.get("models", {}).get("default", {})
                react_config = config.get("react", {})
                mcc = dict(
                    default_model_config.get("model_client_config")
                    or react_config.get("model_client_config")
                    or {}
                )
                model_name = mcc.get("model_name") or react_config.get("model_name") or "gpt-4"
                if "model_name" not in mcc:
                    mcc["model_name"] = model_name
                mco = (
                    default_model_config.get("model_config_obj")
                    or react_config.get("model_config_obj")
                    or {}
                )
                self._model_cache[model_name] = build_model_from_entry(mcc, mco)

            # Set default model (first one)
            if self._model_cache:
                first_name = next(iter(self._model_cache))
                self._default_model = self._model_cache[first_name]
                logger.info(
                    "[Scheduler] Built model cache with %d models, default=%s",
                    len(self._model_cache), first_name
                )

        except Exception as e:
            logger.warning("[Scheduler] Failed to build model cache: %s", e)

    async def start(self) -> None:
        """Start the scheduling loop."""
        if self._loop_task is not None:
            logger.warning("[Scheduler] Already running")
            return

        self._loop_task = asyncio.create_task(self._schedule_loop())
        logger.info("[Scheduler] Started scheduling loop")

    async def stop(self, *, interrupt_running: bool = False) -> None:
        """Stop the scheduler and terminate running executions.

        ``interrupt_running`` is reserved for durable formal task shutdown. It
        records process interruption rather than inventing a user cancellation.
        """
        # Cancel all running executions
        for task_id, exec_task in list(self._running_executions.items()):
            if interrupt_running:
                self._shutdown_interruptions.add(task_id)
            exec_task.cancel()
            try:
                await exec_task
            except asyncio.CancelledError:
                pass

        self._running_executions.clear()

        # Cancel the loop
        if self._loop_task is not None:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
            self._loop_task = None

        logger.info("[Scheduler] Stopped")

    async def cancel_execution(self, task_id: str) -> bool:
        """Cancel one task through a shared, task-scoped cancellation operation."""
        cancellation_task = self._cancellation_tasks.get(task_id)
        if cancellation_task is None:
            cancellation_task = asyncio.create_task(self._cancel_execution_once(task_id))
            self._cancellation_tasks[task_id] = cancellation_task
            cancellation_task.add_done_callback(
                lambda completed, current_task_id=task_id: self._discard_cancellation_task(
                    current_task_id,
                    completed,
                )
            )
        return await asyncio.shield(cancellation_task)

    def _discard_cancellation_task(
        self,
        task_id: str,
        cancellation_task: asyncio.Task[bool],
    ) -> None:
        if self._cancellation_tasks.get(task_id) is cancellation_task:
            self._cancellation_tasks.pop(task_id, None)

    async def _cancel_execution_once(self, task_id: str) -> bool:
        """Cancel a running execution for a task.

        Returns:
            True if execution was cancelled, False if not running
        """
        exec_task = self._running_executions.get(task_id)
        if exec_task is None or exec_task.done():
            return False

        # Get current execution_id to build session_id
        task_data = self._task_store.get_task(task_id)
        task_status = str(task_data.get("status") or "") if task_data else ""
        if task_status in TERMINAL_STATUSES:
            return False
        execution_id = task_data.get("current_execution_id") if task_data else None
        started_at_str = None
        log_path_str = None

        # Try to get started_at from execution_history (most recent)
        if task_data:
            history = task_data.get("execution_history", [])
            if history:
                # Find the execution record for this execution_id
                for record in reversed(history):
                    if record.get("execution_id") == execution_id:
                        started_at_str = record.get("started_at")
                        log_path_str = record.get("log_path")
                        break

        # Cancel the internal service run first (orchestrator execution)
        if execution_id:
            session_id = f"sched_{task_id}_{execution_id}"
            logger.info("[Scheduler] Cancelling service run for session %s", session_id)
            self._service.cancel_session_run(session_id)

        # Cancel the scheduler-level asyncio.Task
        logger.info("[Scheduler] Cancelling asyncio.Task for task %s", task_id)
        exec_task.cancel()
        try:
            await exec_task
        except asyncio.CancelledError:
            logger.info("[Scheduler] CancelledError caught for task %s", task_id)

        # Do not remove a newer execution that may have reused the task ID.
        if self._running_executions.get(task_id) is exec_task:
            self._running_executions.pop(task_id, None)

        # The execution coroutine normally records its own terminal state in
        # ``finally``. Preserve a real success/failure if it won the race with
        # cancellation, and avoid appending a duplicate cancelled record.
        latest_task = self._task_store.get_task(task_id)
        latest_status = str(latest_task.get("status") or "") if latest_task else ""
        if latest_status in TERMINAL_STATUSES:
            return latest_status == "cancelled"

        if execution_id and latest_task:
            for record in reversed(latest_task.get("execution_history", [])):
                if record.get("execution_id") != execution_id:
                    continue
                record_status = str(record.get("status") or "")
                if record_status in TERMINAL_STATUSES:
                    return record_status == "cancelled"
                break

        # Record execution history if we have execution_id
        # (This ensures history is recorded even if _execute_scheduled_task's finally block didn't run)
        if execution_id and task_data:
            completed_at = datetime.now(timezone.utc)
            logger.info(
                "[Scheduler] Recording execution history for cancelled task %s, execution_id %s",
                task_id, execution_id
            )

            # Build log path if not found
            if not log_path_str:
                log_path = self._task_store.get_log_path(task_id, execution_id)
                log_path_str = str(log_path)

            # Use current time as started_at if not found
            if not started_at_str:
                started_at_str = completed_at.isoformat()

            await self._task_store.add_execution_record(task_id, {
                "execution_id": execution_id,
                "started_at": started_at_str,
                "completed_at": completed_at.isoformat(),
                "status": "cancelled",
                "error": "User cancelled",
                "log_path": log_path_str,
            })

            # Update task status to cancelled
            await self._task_store.update_task(task_id, {
                "status": "cancelled",
                "current_execution_id": None,
            })
            logger.info("[Scheduler] Task %s execution %s marked as cancelled in history", task_id, execution_id)

        logger.info("[Scheduler] Cancelled execution for task: %s", task_id)
        return True

    def is_execution_active(self, task_id: str) -> bool:
        """Return whether the scheduler has claimed a live execution task."""
        exec_task = self._running_executions.get(task_id)
        return exec_task is not None and not exec_task.done()

    async def trigger_immediate(self, task_id: str) -> bool:
        """Trigger immediate execution of a pending task.

        Returns:
            True if execution was triggered, False if task not found or already running
        """
        logger.info("[Scheduler] trigger_immediate called for task: %s", task_id)

        if task_id in self._running_executions:
            logger.warning("[Scheduler] Task %s already running", task_id)
            return False

        task = self._task_store.get_task(task_id)
        if not task:
            logger.warning("[Scheduler] Task %s not found in task_store", task_id)
            return False

        if task.get("status") != "pending":
            logger.warning("[Scheduler] Task %s not in pending status: %s", task_id, task.get("status"))
            return False

        # Spawn execution immediately
        logger.info("[Scheduler] Spawning execution task for: %s", task_id)
        exec_task = asyncio.create_task(
            self._execute_scheduled_task(task)
        )
        self._running_executions[task_id] = exec_task
        logger.info("[Scheduler] Triggered immediate execution for task: %s", task_id)
        return True

    async def _schedule_loop(self) -> None:
        """Main scheduling loop - check pending tasks every 60 seconds."""
        while True:
            try:
                pending_tasks = self._task_store.list_pending_tasks()

                for task in pending_tasks:
                    task_id = task.get("task_id")
                    # Formal Live Voice rows have a separate authenticated
                    # composition owner and may only run via trigger_immediate
                    # after a fresh process-local authority binding.
                    if task.get("origin_namespace") == "live_voice":
                        continue
                    if task_id and task_id not in self._running_executions:
                        # Spawn execution
                        exec_task = asyncio.create_task(
                            self._execute_scheduled_task(task)
                        )
                        self._running_executions[task_id] = exec_task

                await self._recover_blocked_tasks()

                await asyncio.sleep(60)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("[Scheduler] Loop error: %s", e)
                await asyncio.sleep(60)

    async def _recover_blocked_tasks(self) -> int:
        """F17: 把可重建上下文的 blocked 任务翻回 pending(本轮不执行)。"""
        rehydrate = getattr(
            self._service, "rehydrate_scheduled_task_execution_context", None
        )
        if not callable(rehydrate):
            return 0
        recovered = 0
        for task in list(self._task_store.list_tasks()):
            if task.get("status") != "blocked":
                continue
            if task.get("origin_namespace") == "live_voice":
                continue
            task_id = task.get("task_id")
            if not task_id or task_id in self._running_executions:
                continue
            if rehydrate(task_id, task.get("execution_descriptor")) is None:
                continue
            await self._task_store.update_task(
                task_id, {"status": "pending", "last_error": None}
            )
            recovered += 1
        return recovered

    async def _execute_scheduled_task(self, task: dict[str, Any]) -> None:
        """Execute a single scheduled task run.

        Uses the immutable process-local context bound when the task was created.
        """
        task_id = task.get("task_id")
        if not task_id:
            logger.warning("[Scheduler] Invalid task data: %s", task)
            return

        # A delete/cancel request may have won after the scheduler listed this
        # pending task but before this coroutine actually started.
        current_task = self._task_store.get_task(task_id)
        if current_task is None or current_task.get("status") != "pending":
            logger.info(
                "[Scheduler] Skipping stale task claim: %s, status=%s",
                task_id,
                current_task.get("status") if current_task else "missing",
            )
            current_execution = asyncio.current_task()
            if self._running_executions.get(task_id) is current_execution:
                self._running_executions.pop(task_id, None)
            if current_task is None or str(current_task.get("status") or "") in TERMINAL_STATUSES:
                release_execution_context = getattr(
                    self._service,
                    "release_scheduled_task_execution_context",
                    None,
                )
                if callable(release_execution_context):
                    release_execution_context(task_id)
            return
        task = current_task

        query = task.get("query")
        interval_hours = task.get("interval_hours", 4)
        model_name = task.get("model_name")
        pipeline = task.get("pipeline")  # Pipeline preference from task
        if not isinstance(query, str) or not query.strip():
            logger.warning("[Scheduler] Invalid task data: %s", task)
            current_execution = asyncio.current_task()
            if self._running_executions.get(task_id) is current_execution:
                self._running_executions.pop(task_id, None)
            await self._task_store.update_task(task_id, {
                "status": "failed",
                "current_execution_id": None,
                "last_error": "任务内容不能为空",
                "completed_at": datetime.now(timezone.utc).isoformat(),
            })
            release_execution_context = getattr(
                self._service,
                "release_scheduled_task_execution_context",
                None,
            )
            if callable(release_execution_context):
                release_execution_context(task_id)
            return

        get_execution_context = getattr(
            self._service,
            "get_scheduled_task_execution_context",
            None,
        )
        execution_context = (
            get_execution_context(task_id)
            if callable(get_execution_context)
            else None
        )
        if execution_context is None:
            # F17: 先按持久化描述符 rehydrate;仍不可重建的进可恢复的
            # blocked,绝不永久 failed(拒绝可变 Agent 兜底的立场不变)。
            rehydrate = getattr(
                self._service, "rehydrate_scheduled_task_execution_context", None
            )
            if callable(rehydrate):
                execution_context = rehydrate(
                    task_id, task.get("execution_descriptor")
                )
        if execution_context is None:
            logger.warning(
                "[Scheduler] Task %s has no rehydratable execution context; "
                "parking it as blocked until configuration returns",
                task_id,
            )
            current_execution = asyncio.current_task()
            if self._running_executions.get(task_id) is current_execution:
                self._running_executions.pop(task_id, None)
            await self._task_store.update_task(task_id, {
                "status": "blocked",
                "current_execution_id": None,
                "last_error": "任务执行上下文不可用；已置为 blocked，配置恢复后自动回到 pending",
            })
            return

        execution_id = f"exec_{uuid.uuid4().hex[:8]}"
        session_id = f"sched_{task_id}_{execution_id}"

        # Update status to running
        await self._task_store.update_task(task_id, {
            "status": "running",
            "current_execution_id": execution_id,
        })

        started_at = datetime.now(timezone.utc)
        log_path = self._task_store.get_log_path(task_id, execution_id)
        final_status = "success"
        error_msg = ""
        target_tree_before: str | None = None
        project_execution = pipeline == PROJECT_CODE_PIPELINE

        try:
            if task.get("result_contract") == TARGET_TREE_CHANGE_REQUIRED:
                execution_target = task.get("execution_target")
                project_dir = (
                    execution_target.get("project_dir")
                    if isinstance(execution_target, dict)
                    else None
                )
                if not isinstance(project_dir, str) or not project_dir.strip():
                    raise RuntimeError(
                        "execution target is required for target change validation"
                    )
                try:
                    target_tree_before = await asyncio.to_thread(
                        _snapshot_target_tree,
                        project_dir,
                    )
                except GitManifestCapacityExceeded as exc:
                    raise RuntimeError(
                        f"TARGET_CHANGE_VALIDATION_FAILED: {exc}"
                    ) from exc

            if project_execution:
                execution_contract = task.get("execution_contract")
                effective_root = (
                    execution_contract.get("effective_execution_root")
                    if isinstance(execution_contract, dict)
                    else None
                )
                artifact_kind = (
                    execution_contract.get("artifact_kind")
                    if isinstance(execution_contract, dict)
                    else None
                )
                executor_id = (
                    execution_contract.get("executor")
                    if isinstance(execution_contract, dict)
                    else None
                )
                contract_pipeline = (
                    execution_contract.get("pipeline")
                    if isinstance(execution_contract, dict)
                    else None
                )
                effect_policy = (
                    execution_contract.get("effect_policy")
                    if isinstance(execution_contract, dict)
                    else None
                )
                target = task.get("execution_target")
                selected_root = (
                    target.get("project_dir") if isinstance(target, dict) else None
                )
                if (
                    not isinstance(effective_root, str)
                    or not isinstance(selected_root, str)
                    or os.path.normcase(os.path.normpath(str(Path(effective_root).resolve())))
                    != os.path.normcase(os.path.normpath(str(Path(selected_root).resolve())))
                    or artifact_kind != PROJECT_CODE_ARTIFACT_KIND
                    or executor_id != PROJECT_CODE_EXECUTOR
                    or contract_pipeline != PROJECT_CODE_PIPELINE
                    or effect_policy != PROJECT_CODE_EFFECT_POLICY
                    or execution_context.project_executor is None
                ):
                    raise RuntimeError(
                        "EXECUTION_TARGET_NOT_BOUND: persisted project execution contract is invalid"
                    )

            logger.info(
                "[Scheduler] Using task-bound agent for task %s: %s",
                task_id,
                execution_context.agent is not None,
            )

            # Build request for execution
            from jiuwenswarm.common.schema.agent import AgentRequest

            # Resolve pipeline preference (use task's pipeline or default to META_EVOLVE_PIPELINE)
            pipeline_preference = pipeline if pipeline else META_EVOLVE_PIPELINE
            params = {
                "mode": "code" if project_execution else "auto_harness",
                "scheduled": True,
                "pipeline_preference": pipeline_preference,
                "query": query,
            }
            optimization_task = task.get("optimization_task")
            if isinstance(optimization_task, dict):
                params["optimization_task"] = optimization_task
            repo_url = task.get("repo_url", "")
            if repo_url:
                params["repo_url"] = repo_url
            if project_execution:
                params.update(
                    {
                        "project_dir": effective_root,
                        "cwd": effective_root,
                        "trusted_dirs": [effective_root],
                        "supports_user_interaction": False,
                    }
                )
                if model_name:
                    params["model_name"] = model_name

            request = AgentRequest(
                request_id=execution_id,
                channel_id=str(
                    (task.get("owner_scope") or {}).get("channel_id") or "web"
                ),
                session_id=session_id,
                params=params,
                metadata={
                    "enable_memory": False,
                    "background_task": True,
                    "task_id": task_id,
                },
            )

            # Resolve model from jiuwenswarm config (same approach as interface_deep)
            model = None if project_execution else self._resolve_model(model_name)
            logger.info(
                "[Scheduler] Resolved model for task %s: %s (requested=%s)",
                task_id, model is not None, model_name
            )

            # Execute with the task-scoped binding. Scheduled runs have no
            # interactive channel, so interactions are auto-accepted.
            if project_execution:
                stream = execution_context.project_executor.process_background_code_task_stream(
                    request
                )
            else:
                stream = self._service.run(
                    request,
                    session_id,
                    execution_id,
                    query=query,
                    model=model,
                    auto_accept=True,
                    execution_agent=execution_context.agent,
                    stream_event_rail=execution_context.stream_event_rail,
                )

            project_terminal = False
            project_error = ""
            shell_policy = (
                forbid_background_project_shell_commands()
                if project_execution
                else contextlib.nullcontext()
            )
            with shell_policy:
                async for chunk in stream:
                    payload = chunk.payload if isinstance(chunk.payload, dict) else None
                    if project_execution and chunk.is_complete:
                        project_terminal = True
                    if project_execution and payload and payload.get("event_type") == "chat.error":
                        project_error = str(
                            payload.get("error") or payload.get("message") or "project executor failed"
                        )
                    if not payload:
                        continue
                    # Skip context compression events - not needed in logs
                    event_type = payload.get("event_type", "")
                    if event_type in ("context.usage", "context.compression_state"):
                        continue
                    if event_type == "harness.message" and chunk.payload.get("stage"):
                        logger.info(
                            "[Scheduler] Task %s execution %s stage=%s message=%s",
                            task_id,
                            execution_id,
                            chunk.payload.get("stage"),
                            str(chunk.payload.get("content") or "")[:160],
                        )
                    elif event_type == "harness.stage_result":
                        logger.info(
                            "[Scheduler] Task %s execution %s stage=%s status=%s error=%s",
                            task_id,
                            execution_id,
                            chunk.payload.get("stage"),
                            chunk.payload.get("status"),
                            str(chunk.payload.get("error") or "")[:200],
                        )
                    # Append log chunk via thread pool (avoids blocking event loop)
                    line = json.dumps(chunk.payload, ensure_ascii=False) + "\n"
                    await asyncio.to_thread(_sync_append_log, log_path, line)
                    if (
                        not project_execution
                        and event_type == "harness.session_finished"
                        and chunk.payload.get("is_terminal") is True
                    ):
                        logger.info(
                            "[Scheduler] Task %s execution %s received terminal session event",
                            task_id,
                            execution_id,
                        )
                        break

            if project_execution and project_error:
                raise RuntimeError(project_error)
            if project_execution and not project_terminal:
                raise RuntimeError("PROJECT_EXECUTOR_INCOMPLETE: no terminal response")

            logger.info(
                "[Scheduler] Task %s execution %s completed successfully",
                task_id, execution_id
            )

        except asyncio.CancelledError:
            if task_id in self._shutdown_interruptions:
                final_status = "interrupted"
                error_msg = "formal task execution interrupted by process shutdown"
                logger.info(
                    "[Scheduler] Task %s execution %s interrupted by shutdown",
                    task_id,
                    execution_id,
                )
            else:
                final_status = "cancelled"
                logger.info("[Scheduler] Task %s execution %s cancelled", task_id, execution_id)

        except Exception as e:
            final_status = "failed"
            error_msg = str(e)
            logger.exception("[Scheduler] Task %s execution %s failed: %s", task_id, execution_id, e)

        finally:
            if (
                final_status == "success"
                and not project_execution
                and log_path.exists()
                and not has_terminal_session_event(log_path)
            ):
                logger.warning(
                    "[Scheduler] Task %s execution %s ended without terminal session event",
                    task_id,
                    execution_id,
                )
            if final_status == "success" and not project_execution and log_path.exists():
                result = self._task_store.determine_pipeline_status_from_log(log_path)
                if result["failed"]:
                    final_status = "failed"
                    error_msg = result["error"]
            if (
                final_status == "success"
                and task.get("result_contract") == TARGET_TREE_CHANGE_REQUIRED
            ):
                execution_target = task.get("execution_target")
                project_dir = (
                    execution_target.get("project_dir")
                    if isinstance(execution_target, dict)
                    else None
                )
                try:
                    if not isinstance(project_dir, str) or not project_dir.strip():
                        raise RuntimeError(
                            "execution target is required for target change validation"
                        )
                    target_tree_after = await asyncio.to_thread(
                        _snapshot_target_tree,
                        project_dir,
                    )
                except Exception as exc:
                    final_status = "failed"
                    error_msg = f"TARGET_CHANGE_VALIDATION_FAILED: {exc}"
                else:
                    if target_tree_after == target_tree_before:
                        final_status = "failed"
                        error_msg = NO_EFFECTIVE_TARGET_CHANGE_ERROR

            # Record execution
            completed_at = datetime.now(timezone.utc)
            await self._task_store.add_execution_record(task_id, {
                "execution_id": execution_id,
                "started_at": started_at.isoformat(),
                "completed_at": completed_at.isoformat(),
                "status": final_status,
                "error": error_msg,
                "log_path": str(log_path),
            })

            # Update next run time if not cancelled
            if final_status != "cancelled":
                is_one_time = task.get("is_one_time", False)
                if is_one_time:
                    terminal_updates = {
                        "status": final_status,
                        "current_execution_id": None,
                    }
                    if final_status == "failed":
                        terminal_updates["last_error"] = error_msg or "任务执行失败"
                    await self._task_store.update_task(task_id, terminal_updates)
                    logger.info("[Scheduler] One-time task %s finished with status: %s", task_id, final_status)
                else:
                    next_run = completed_at + timedelta(hours=interval_hours)
                    await self._task_store.update_task(task_id, {
                        "status": "pending",
                        "current_execution_id": None,
                        "next_run_time": next_run.isoformat(),
                    })
            else:
                await self._task_store.update_task(task_id, {
                    "status": "cancelled",
                    "current_execution_id": None,
                })

            if task.get("is_one_time", False) or final_status == "cancelled":
                release_execution_context = getattr(
                    self._service,
                    "release_scheduled_task_execution_context",
                    None,
                )
                if callable(release_execution_context):
                    release_execution_context(task_id)

            # Remove from running dict
            self._running_executions.pop(task_id, None)
            self._shutdown_interruptions.discard(task_id)
