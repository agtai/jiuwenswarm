"""Exact Host execution binding for existing Agent model/tool callbacks."""

from contextlib import contextmanager
import asyncio
import json

from .store import TaskStore, task_database


class TaskCheckpoint:
    def __init__(self, store, task, root, harness=None):
        self.store, self.task_id, self.root = store, task["id"], root
        self.request_id = task["request_id"]
        self.closed = False
        self.harness = harness
        self.native_executions = set()
        self.settlement_unobserved = False
        self.output_stream = None

    def check(self, ctx):
        run = ctx.extra.get("run_context")
        extra = (
            run.get("extra", {}) if isinstance(run, dict) else getattr(run, "extra", {})
        )
        if self.closed or extra.get("managed_task_request") != self.request_id:
            raise RuntimeError("TASK_EXECUTION_BINDING_STALE")
        task = self.store.read(self.task_id)
        if task["request_id"] != self.request_id or task["status"] not in {
            "running",
            "waiting_user",
        }:
            raise RuntimeError("TASK_EXECUTION_NOT_RUNNING")

    async def before_model(self, ctx):
        self.check(ctx)
        # A Core output stream can close before its cancelled scheduler task drains.
        # Capture that exact handle while the round still owns it; never infer
        # settlement from a terminal status or disappearance from the scheduler.
        active = getattr(self.harness, "active_round", None)
        controller = getattr(self.harness, "loop_controller", None)
        scheduler = getattr(controller, "task_scheduler", None)
        entry = getattr(scheduler, "_running_tasks", {}).get(
            getattr(active, "task_id", None)
        )
        if entry and entry[1] is not None:
            self.native_executions.add(entry[1])
        elif active is not None:
            # Interrupt resumes may execute directly rather than in the scheduler
            # map. Capture the exact callback's task, never infer completion from
            # a missing scheduler entry or the preceding interrupted round.
            native = asyncio.current_task()
            if native is not None:
                self.native_executions.add(native)
            else:
                self.settlement_unobserved = True
        from openjiuwen.core.foundation.llm import UserMessage

        with self.store.transaction() as db:
            task = self.store.get(db, self.task_id)
            if task["request_id"] != self.request_id or task["status"] not in {
                "running",
                "waiting_user",
            }:
                raise RuntimeError("TASK_EXECUTION_NOT_RUNNING")
            pending = [c for c in task["changes"] if c["state"] == "pending"]
            for change in pending:
                change["state"] = "claimed"
            self.store.put(db, task)
        for change in pending:
            # SQLite and model context are not one transaction: a lost ACK stays unknown.
            await ctx.context.add_messages(
                UserMessage(
                    content=json.dumps(
                        {
                            "managed_task_change": change["id"],
                            "instruction": change["instruction"],
                            "meaning": (
                                "User changes this task's requirements; "
                                "retain other constraints and permissions."
                            ),
                        },
                        ensure_ascii=False,
                    )
                )
            )

            def acknowledge(task, change_id=change["id"]):
                for item in task["changes"]:
                    if item["id"] == change_id and item["state"] == "claimed":
                        item["state"] = "context_written"

            self.store.update(self.task_id, acknowledge)
        self.check(ctx)

    def after_model(self, ctx):
        # This observes the final request, not semantic compliance with the change.
        messages = getattr(ctx.inputs, "messages", []) or []
        observed = set()
        for message in messages:
            content = (
                message.get("content")
                if isinstance(message, dict)
                else getattr(message, "content", None)
            )
            if not isinstance(content, str):
                continue
            try:
                value = json.loads(content)
                if isinstance(value, dict):
                    observed.add(value.get("managed_task_change"))
            except (ValueError, TypeError):
                continue
        if observed:

            def mark(task):
                for change in task["changes"]:
                    if (
                        change["state"] == "context_written"
                        and change["id"] in observed
                    ):
                        change["state"] = "model_input_observed"

            self.store.update(self.task_id, mark)


@contextmanager
def bind_task_execution(request, adapter, inputs):
    path = task_database()
    managed = (
        request.channel_id == "video_tool"
        and str(request.session_id or "").startswith("managed-task-")
        and getattr(adapter, "_is_session_scoped_adapter", False)
    )
    if (
        request.channel_id != "video_tool"
        or not path.is_file()
        or not getattr(adapter, "_is_session_scoped_adapter", False)
    ):
        if managed:
            raise RuntimeError("Managed task execution binding is unavailable")
        yield
        return
    store = TaskStore(path)
    with store.transaction() as db:
        candidates = []
        for task in store.rows(db):
            if (
                task["core_session_id"] == request.session_id
                and task["request_id"] == request.request_id
            ):
                candidates.append(task)
    if not candidates:
        if managed:
            raise RuntimeError("Managed task execution identity is stale or missing")
        yield
        return
    harness, rail = adapter.task_execution_binding
    root = getattr(harness, "_react_agent", None)
    if root is None or not getattr(adapter, "_is_session_scoped_adapter", False):
        raise RuntimeError("Managed tasks require the session-owned Agent")
    bindings = getattr(rail, "managed_tasks", None)
    if bindings is None:
        rail.managed_tasks = bindings = {}
    if request.session_id in bindings:
        raise RuntimeError("Task execution already bound")
    with store.transaction() as db:
        task = store.get(db, candidates[0]["id"])
        if task["status"] != "running" or task.get("execution_bound"):
            raise RuntimeError("Task execution is not available for a new invocation")
        task["execution_bound"] = True
        task["sequence"] += 1
        store.put(db, task)
    checkpoint = TaskCheckpoint(store, candidates[0], root, harness)
    bindings[request.session_id] = checkpoint
    previous = inputs.get("run")
    run = dict(previous or {})
    context = dict(run.get("context") or {})
    context["extra"] = {
        **context.get("extra", {}),
        "managed_task_request": request.request_id,
    }
    inputs["run"] = {**run, "context": context}
    invocation_cancelled = False
    try:
        yield
    except asyncio.CancelledError:
        # Cancellation can arrive during setup, before the first model callback
        # captures a scheduler handle. The bound invocation itself is evidence.
        invocation_cancelled = True
        raise
    finally:
        checkpoint.closed = True
        bindings.pop(request.session_id, None)
        if previous is None:
            inputs.pop("run", None)
        else:
            inputs["run"] = previous
        store.update(
            checkpoint.task_id,
            lambda t: (
                t.update(checkpoint_open=False)
                if t["request_id"] == checkpoint.request_id
                else None
            ),
        )

        def settled(_done=None):
            if not checkpoint.settlement_unobserved and all(
                task.done() for task in checkpoint.native_executions
            ):
                store.update(
                    checkpoint.task_id,
                    lambda t: (
                        t.update(
                            execution_settled=True,
                            execution_cancelled=invocation_cancelled
                            or any(
                                native.cancelled() or native.cancelling() > 0
                                for native in checkpoint.native_executions
                            ),
                        )
                        if t["request_id"] == checkpoint.request_id
                        else None
                    ),
                )

        for native_task in checkpoint.native_executions:
            if not native_task.done():
                native_task.add_done_callback(settled)
        settled()


async def bind_task_output(rail, request, stream):
    """Keep the exact output lease so cancellation can wake an idle consumer."""
    binding = getattr(rail, "managed_tasks", {}).get(request.session_id)
    if binding is None or binding.request_id != request.request_id:
        return
    binding.output_stream = stream
    if binding.store.read(binding.task_id)["status"] == "cancelling":
        await stream.close(abort_active_round=False)


async def close_task_output(rail, request):
    binding = getattr(rail, "managed_tasks", {}).get(request.session_id)
    expected = (request.params or {}).get("managed_task_request")
    if binding is None or not expected or binding.request_id != expected:
        return
    task = binding.store.read(binding.task_id)
    if task["request_id"] != expected or task["status"] != "cancelling":
        return
    if binding.output_stream is not None:
        # cancel_round has already signalled the execution. Closing its output
        # lease is separate: cancellation alone may leave next_output waiting.
        # The binding still waits for native execution handles before settlement.
        await binding.output_stream.close(abort_active_round=False)


async def task_checkpoint(rail, ctx, stage):
    bindings = getattr(rail, "managed_tasks", {})
    run = (getattr(ctx, "extra", None) or {}).get("run_context")
    extra = run.get("extra", {}) if isinstance(run, dict) else getattr(run, "extra", {})
    if not bindings and not extra.get("managed_task_request"):
        return  # Ordinary Agent callbacks do not require task-management metadata.
    checkpoint = bindings.get(rail.resolve_session_id(ctx, ctx.session))
    from openjiuwen.core.runner.callback.errors import AbortError

    if checkpoint is None:
        if extra.get("managed_task_request"):
            raise AbortError("TASK_EXECUTION_BINDING_CLOSED")
        return
    if ctx.agent is not checkpoint.root:
        return
    try:
        if stage == "before_model":
            await checkpoint.before_model(ctx)
        elif stage == "after_model":
            checkpoint.after_model(ctx)
        else:
            checkpoint.check(ctx)
    except Exception as exc:
        raise AbortError("TASK_CHECKPOINT_REJECTED", cause=exc) from exc
