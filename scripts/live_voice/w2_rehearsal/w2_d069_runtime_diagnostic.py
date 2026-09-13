from __future__ import annotations

import argparse
import asyncio
import json
import os
import secrets
import sqlite3
import sys
import time
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path


_MAX_SAFE_INTEGER = (1 << 53) - 1
_DIRECT_EXECUTOR_TABLE = "live_voice_formal_project_attempts_v1"
_P3_FROZEN_ENTRY_COUNTS = {
    "retry_readiness": 0,
    "dispatch": 1,
    "cancel": 0,
    "agent": 1,
    "tool": 0,
}
_P3_CANCEL_ENTRY_DELTA = {
    **_P3_FROZEN_ENTRY_COUNTS,
    "dispatch": 0,
    "agent": 0,
    "cancel": 1,
}
def _iso_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _configure(args: argparse.Namespace) -> str:
    token = secrets.token_urlsafe(48)
    expiry = (datetime.now(UTC) + timedelta(hours=4)).isoformat().replace("+00:00", "Z")
    values = {
        "JIUWENSWARM_DATA_DIR": str(args.data_dir),
        "JIUWENSWARM_LIVE_VOICE_P3_ENABLED": "true",
        "JIUWENSWARM_LIVE_VOICE_P3_EXECUTOR_PROFILE": (
            "live-voice.direct-project-code.d2.v2"
        ),
        "JIUWENSWARM_LIVE_VOICE_PRODUCT_COMPOSITION_ENABLED": "true",
        "JIUWENSWARM_LIVE_VOICE_PRODUCT_P2_ENABLED": "true",
        "JIUWENSWARM_LIVE_VOICE_PRODUCT_P3_TEXT_ENABLED": "true",
        "JIUWENSWARM_LIVE_VOICE_PRODUCT_P3_MUTATION_ENABLED": "true",
        "JIUWENSWARM_LIVE_VOICE_P3_AUTH_TOKEN": token,
        "JIUWENSWARM_LIVE_VOICE_P3_PRINCIPAL_ID": args.principal_id,
        "JIUWENSWARM_LIVE_VOICE_P3_PROJECT_IDS": args.project_id,
        "JIUWENSWARM_LIVE_VOICE_P3_AUTH_EXPIRES_AT": expiry,
        "JIUWENSWARM_LIVE_VOICE_P3_DATABASE": str(args.database),
        "JIUWENSWARM_LIVE_VOICE_P3_RECONCILE_SECONDS": "0.2",
    }
    for key, value in values.items():
        os.environ[key] = value
    return token






class _P3BarrierAgent:
    def __init__(self, agent: object, owner: "_P3NonterminalBarrier") -> None:
        self._agent = agent
        self._owner = owner

    def __getattr__(self, name: str) -> object:
        return getattr(self._agent, name)

    async def process_background_code_task_stream(self, request: object):
        adapter = getattr(self._agent, "_adapter", None)
        original_prepare = getattr(adapter, "prepare_background_project_session", None)
        get_child = getattr(adapter, "_get_cached_session_adapter", None)
        if not callable(original_prepare) or not callable(get_child):
            raise RuntimeError("P3 probe requires real Code Agent session routing")

        async def observed_prepare(session_id: str) -> None:
            await original_prepare(session_id)
            child = get_child(session_id)
            instance = getattr(child, "_instance", None)
            manager = getattr(instance, "ability_manager", None)
            original_execute = getattr(manager, "execute", None)
            if child is None or child is adapter or not callable(original_execute):
                raise RuntimeError(
                    "P3 probe cannot observe the session Tool entrypoint"
                )

            async def observed_execute(*args: object, **kwargs: object) -> object:
                self._owner._record("tool")
                return await original_execute(*args, **kwargs)

            manager.execute = observed_execute
            self._owner._agent_entered.set()
            try:
                await self._owner._agent_barrier.wait()
            finally:
                if getattr(manager, "execute", None) is observed_execute:
                    manager.execute = original_execute
                self._owner._agent_stopped.set()

        adapter.prepare_background_project_session = observed_prepare
        self._owner._record("agent")
        try:
            async for chunk in self._agent.process_background_code_task_stream(request):
                yield chunk
        finally:
            if (
                getattr(adapter, "prepare_background_project_session", None)
                is observed_prepare
            ):
                adapter.prepare_background_project_session = original_prepare


class _P3NonterminalBarrier:
    """Freeze one real D0 worker before Agent/Tool execution and count entries."""

    _MAX_ENTRY_COUNT = 4

    def __init__(self, core: object) -> None:
        self._core = core
        self._executor = core.executor
        self._counts = {name: 0 for name in _P3_FROZEN_ENTRY_COUNTS}
        self._agent_barrier = asyncio.Event()
        self._agent_entered = asyncio.Event()
        self._agent_stopped = asyncio.Event()
        self._original_resolve: object | None = None

    def __getattr__(self, name: str) -> object:
        return getattr(self._executor, name)

    def _record(self, name: str) -> None:
        count = self._counts[name] + 1
        if count > self._MAX_ENTRY_COUNT:
            raise RuntimeError(f"P3 probe {name} entry count exceeded its bound")
        self._counts[name] = count

    def snapshot(self) -> dict[str, int]:
        return dict(self._counts)

    def delta(self, before: Mapping[str, int]) -> dict[str, int]:
        return {name: self._counts[name] - before[name] for name in self._counts}

    async def wait_frozen(self, *, timeout: float) -> None:
        await asyncio.wait_for(self._agent_entered.wait(), timeout=timeout)

    async def wait_agent_stopped(self, *, timeout: float) -> None:
        await asyncio.wait_for(self._agent_stopped.wait(), timeout=timeout)

    def retry_readiness(self, task: object, attempt: object) -> object:
        self._record("retry_readiness")
        return self._executor.retry_readiness(task, attempt)

    async def dispatch(self, item: object) -> object:
        self._record("dispatch")
        return await self._executor.dispatch(item)

    async def cancel(self, item: object) -> object:
        self._record("cancel")
        return await self._executor.cancel(item)

    def install(self) -> None:
        if self._original_resolve is not None:
            raise RuntimeError("P3 nonterminal barrier is already installed")
        resolver = self._executor._resolver
        original_resolve = resolver.resolve

        async def observed_resolve(spec: object, *, for_dispatch: bool) -> object:
            binding = await original_resolve(spec, for_dispatch=for_dispatch)
            factory = getattr(binding, "attempt_executor_factory", None)
            if not for_dispatch or not callable(factory):
                return binding

            async def acquire(attempt_root: str) -> object:
                lease = await factory(attempt_root)
                return replace(
                    lease,
                    project_executor=_P3BarrierAgent(lease.project_executor, self),
                )

            return replace(binding, attempt_executor_factory=acquire)

        self._original_resolve = original_resolve
        resolver.resolve = observed_resolve
        self._core.executor = self

    def restore(self) -> None:
        if self._core.executor is self:
            self._core.executor = self._executor
        if self._original_resolve is not None:
            self._executor._resolver.resolve = self._original_resolve
            self._original_resolve = None






def _read_attempt_lineage(
    database: Path, task_id: str
) -> tuple[tuple[str, int, str, str | None], ...]:
    connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            """
            SELECT attempt_id, attempt_number, state, outcome
              FROM attempts
             WHERE task_id=?
             ORDER BY attempt_number
            """,
            (task_id,),
        ).fetchall()
        return tuple(
            (
                str(row[0]),
                int(row[1]),
                str(row[2]),
                None if row[3] is None else str(row[3]),
            )
            for row in rows
        )
    finally:
        connection.close()


















async def _wait_task(
    composition: object,
    scope: object,
    task_id: str,
    *,
    terminal: bool,
    timeout: float,
) -> object:
    deadline = time.monotonic() + timeout
    last: tuple[object, ...] | None = None
    while time.monotonic() < deadline:
        task = composition._core.store.get_task(task_id, scope)
        attempt = composition._core.store.get_attempt(task.attempt_id)
        snapshot = (
            task.state.value,
            None if task.outcome is None else task.outcome.value,
            task.attempt_id,
            attempt.attempt_number,
        )
        if snapshot != last:
            print("W2_D069_TASK_STATE " + json.dumps(snapshot), flush=True)
            last = snapshot
        if terminal and task.state.value == "terminal":
            return task
        if not terminal and task.state.value == "running":
            return task
        await asyncio.sleep(0.25)
    raise TimeoutError(f"task {task_id} did not reach the required state")


async def _mutate(
    registry: object,
    *,
    token: str,
    session_id: str,
    operation: str,
    command_id: str,
    task_id: str | None = None,
    instruction: str | None = None,
    model_intent: str | None = None,
) -> dict[str, object]:
    params: dict[str, object] = {
        "auth_token": token,
        "session_id": session_id,
        "operation": operation,
        "command_id": command_id,
        "issued_at": _iso_now(),
        "correlation_id": f"correlation:{command_id}",
    }
    if task_id is not None:
        params["task_id"] = task_id
    if operation == "task.create":
        params.update(
            {
                "name": "W2 D-069 disposable D0 diagnostic",
                "instruction": instruction,
                "model_intent": model_intent,
            }
        )
    issued = await registry.handle_p3_confirmation_issue(
        params=params,
        request_id=f"issue:{command_id}",
        session_id=session_id,
    )
    if not issued.ok:
        raise RuntimeError(f"confirmation issue failed: {issued.payload!r}")
    receipt = dict(issued.payload["result"])
    params["confirmation_id"] = receipt["confirmation_id"]
    mutated = await registry.handle_p3_mutation(
        params=params,
        request_id=f"mutate:{command_id}",
        session_id=session_id,
    )
    if not mutated.ok:
        raise RuntimeError(f"mutation failed: {mutated.payload!r}")
    product_result = dict(mutated.payload["result"])
    formal = product_result.get("formal_task_result")
    if not isinstance(formal, dict):
        raise RuntimeError("mutation returned no formal task result")
    return dict(formal)




async def _stop(server: object) -> None:
    for _ in range(5):
        product_closed = await server._stop_live_voice_product_composition()
        p3_closed = await server._stop_live_voice_p3_composition()
        if product_closed and p3_closed:
            return
        await asyncio.sleep(1)
    raise RuntimeError("diagnostic runtime cleanup remained pending")


async def _run_ab(args: argparse.Namespace, token: str) -> None:
    from jiuwenswarm.common.schema.live_voice_contract_v2 import Assurance, ScopeRef
    from jiuwenswarm.server.agent_ws_server import AgentWebSocketServer

    args.database.parent.mkdir(parents=True, exist_ok=False)
    server = AgentWebSocketServer()
    started = False
    try:
        await server._start_live_voice_p3_composition()
        await server._start_live_voice_product_composition()
        composition = server._live_voice_p3_composition
        registry = server._live_voice_product_composition
        if composition is None or registry is None:
            raise RuntimeError("production P3/product composition failed to start")
        started = True
        scope = ScopeRef(
            args.principal_id,
            args.project_id,
            args.session_id,
            Assurance.AUTHENTICATED,
        )
        create = await _mutate(
            registry,
            token=token,
            session_id=args.session_id,
            operation="task.create",
            command_id="w2-d069-create-a",
            instruction=args.instruction,
            model_intent=args.model_intent,
        )
        task_id = str(create["task_id"])
        attempt_a = str(create["attempt_id"])
        print(
            "W2_D069_CREATED "
            + json.dumps({"task_id": task_id, "attempt_a": attempt_a}),
            flush=True,
        )
        await _mutate(
            registry,
            token=token,
            session_id=args.session_id,
            operation="task.cancel",
            command_id="w2-d069-cancel-a",
            task_id=task_id,
        )
        cancelled = await _wait_task(
            composition, scope, task_id, terminal=True, timeout=180
        )
        if cancelled.outcome.value != "cancelled" or cancelled.attempt_id != attempt_a:
            raise RuntimeError(
                "attempt A did not form the exact cancelled terminal predecessor"
            )
        retry = await _mutate(
            registry,
            token=token,
            session_id=args.session_id,
            operation="task.retry",
            command_id="w2-d069-retry-b",
            task_id=task_id,
        )
        attempt_b = str(retry["attempt_id"])
        if retry.get("attempt_number") != 2 or attempt_b == attempt_a:
            raise RuntimeError("attempt B lineage is invalid")
        completed = await _wait_task(
            composition, scope, task_id, terminal=True, timeout=900
        )
        if completed.outcome.value != "completed" or completed.attempt_id != attempt_b:
            raise RuntimeError(
                "attempt B did not form the exact completed D0 predecessor"
            )
        print(
            "W2_D069_AB_RESULT "
            + json.dumps(
                {
                    "task_id": task_id,
                    "attempt_a": attempt_a,
                    "attempt_b": attempt_b,
                    "attempt_b_outcome": completed.outcome.value,
                    "attempt_number": composition._core.store.get_attempt(
                        completed.attempt_id
                    ).attempt_number,
                    "database": str(args.database),
                }
            ),
            flush=True,
        )
    finally:
        if started:
            await _stop(server)


async def _run_b(args: argparse.Namespace, token: str) -> None:
    from jiuwenswarm.common.schema.live_voice_contract_v2 import Assurance, ScopeRef
    from jiuwenswarm.server.agent_ws_server import AgentWebSocketServer

    if not args.database.is_file() or not args.task_id:
        raise RuntimeError("resume-b requires an existing database and task id")
    server = AgentWebSocketServer()
    started = False
    try:
        await server._start_live_voice_p3_composition()
        await server._start_live_voice_product_composition()
        composition = server._live_voice_p3_composition
        registry = server._live_voice_product_composition
        if composition is None or registry is None:
            raise RuntimeError("production P3/product composition failed to start")
        started = True
        scope = ScopeRef(
            args.principal_id,
            args.project_id,
            args.session_id,
            Assurance.AUTHENTICATED,
        )
        predecessor = composition._core.store.get_task(args.task_id, scope)
        attempt_a = composition._core.store.get_attempt(predecessor.attempt_id)
        if (
            predecessor.state.value != "terminal"
            or predecessor.outcome.value != "cancelled"
            or attempt_a.attempt_number != 1
        ):
            raise RuntimeError("resume predecessor is not exact cancelled attempt A")
        retry = await _mutate(
            registry,
            token=token,
            session_id=args.session_id,
            operation="task.retry",
            command_id="w2-d069-retry-b",
            task_id=args.task_id,
        )
        attempt_b = str(retry["attempt_id"])
        if retry.get("attempt_number") != 2 or attempt_b == attempt_a.attempt_id:
            raise RuntimeError("attempt B lineage is invalid")
        completed = await _wait_task(
            composition, scope, args.task_id, terminal=True, timeout=900
        )
        if completed.outcome.value != "completed" or completed.attempt_id != attempt_b:
            raise RuntimeError(
                "attempt B did not form the exact completed D0 predecessor"
            )
        print(
            "W2_D069_AB_RESULT "
            + json.dumps(
                {
                    "task_id": args.task_id,
                    "attempt_a": attempt_a.attempt_id,
                    "attempt_b": attempt_b,
                    "attempt_b_outcome": completed.outcome.value,
                    "attempt_number": composition._core.store.get_attempt(
                        completed.attempt_id
                    ).attempt_number,
                    "database": str(args.database),
                }
            ),
            flush=True,
        )
    finally:
        if started:
            await _stop(server)


async def _run_c_predecessor(args: argparse.Namespace, token: str) -> None:
    from jiuwenswarm.common.schema.live_voice_contract_v2 import Assurance, ScopeRef
    from jiuwenswarm.server.agent_ws_server import AgentWebSocketServer

    if not args.database.is_file() or not args.task_id:
        raise RuntimeError("c-predecessor requires an existing database and task id")
    server = AgentWebSocketServer()
    started = False
    try:
        await server._start_live_voice_p3_composition()
        await server._start_live_voice_product_composition()
        composition = server._live_voice_p3_composition
        registry = server._live_voice_product_composition
        if composition is None or registry is None:
            raise RuntimeError("production P3/product composition failed to start")
        started = True
        scope = ScopeRef(
            args.principal_id,
            args.project_id,
            args.session_id,
            Assurance.AUTHENTICATED,
        )
        predecessor = composition._core.store.get_task(args.task_id, scope)
        attempt_b = composition._core.store.get_attempt(predecessor.attempt_id)
        if (
            predecessor.state.value != "terminal"
            or predecessor.outcome.value != "completed"
            or attempt_b.attempt_number != 2
        ):
            raise RuntimeError("C predecessor is not exact completed attempt B")
        retry = await _mutate(
            registry,
            token=token,
            session_id=args.session_id,
            operation="task.retry",
            command_id="w2-d069-retry-c",
            task_id=args.task_id,
        )
        attempt_c = str(retry["attempt_id"])
        if retry.get("attempt_number") != 3 or attempt_c == attempt_b.attempt_id:
            raise RuntimeError("attempt C lineage is invalid")

        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            current = composition._core.store.get_task(args.task_id, scope)
            current_attempt = composition._core.store.get_attempt(current.attempt_id)
            if current.attempt_id != attempt_c:
                raise RuntimeError("authoritative current attempt changed before crash")
            if current.state.value == "terminal":
                raise RuntimeError("attempt C completed before predecessor crash")
            if current.state.value == "running":
                print(
                    "W2_D069_C_PREDECESSOR_RUNNING "
                    + json.dumps(
                        {
                            "task_id": args.task_id,
                            "attempt_b": attempt_b.attempt_id,
                            "attempt_c": attempt_c,
                            "attempt_number": current_attempt.attempt_number,
                            "event_head": current.event_head,
                            "crash_exit_code": 86,
                        }
                    ),
                    flush=True,
                )
                os._exit(86)
            await asyncio.sleep(0.01)
        raise TimeoutError("attempt C did not reach running before predecessor crash")
    finally:
        if started:
            await _stop(server)


async def _run_c_successor(args: argparse.Namespace, token: str) -> None:
    from jiuwenswarm.common.schema.live_voice_contract_v2 import Assurance, ScopeRef
    from jiuwenswarm.server.agent_ws_server import AgentWebSocketServer

    if not args.database.is_file() or not args.task_id:
        raise RuntimeError("c-successor requires an existing database and task id")
    server = AgentWebSocketServer()
    started = False
    try:
        await server._start_live_voice_p3_composition()
        await server._start_live_voice_product_composition()
        composition = server._live_voice_p3_composition
        if composition is None or server._live_voice_product_composition is None:
            raise RuntimeError("production P3/product composition failed to start")
        started = True
        scope = ScopeRef(
            args.principal_id,
            args.project_id,
            args.session_id,
            Assurance.AUTHENTICATED,
        )
        before = composition._core.store.get_task(args.task_id, scope)
        attempt_c = composition._core.store.get_attempt(before.attempt_id)
        if attempt_c.attempt_number != 3 or before.state.value == "terminal":
            raise RuntimeError("successor did not inherit exact nonterminal attempt C")
        terminal = await _wait_task(
            composition, scope, args.task_id, terminal=True, timeout=420
        )
        attempts = _read_attempt_lineage(args.database, args.task_id)
        if len(attempts) != 3 or [attempt[1] for attempt in attempts] != [1, 2, 3]:
            raise RuntimeError("successor created or lost an attempt")
        if terminal.attempt_id != attempt_c.attempt_id:
            raise RuntimeError("successor reconciled a different attempt")
        if terminal.outcome.value != "interrupted":
            raise RuntimeError(
                f"successor outcome is {terminal.outcome.value}, not interrupted"
            )
        print(
            "W2_D069_C_SUCCESSOR_RESULT "
            + json.dumps(
                {
                    "task_id": args.task_id,
                    "attempt_ids": [attempt[0] for attempt in attempts],
                    "attempt_numbers": [attempt[1] for attempt in attempts],
                    "attempt_c": attempt_c.attempt_id,
                    "attempt_c_outcome": terminal.outcome.value,
                    "event_head": terminal.event_head,
                    "reconciliation_state": (
                        None
                        if terminal.reconciliation_state is None
                        else terminal.reconciliation_state.value
                    ),
                }
            ),
            flush=True,
        )
    finally:
        if started:
            await _stop(server)


async def _run_p2_smoke(args: argparse.Namespace, token: str) -> None:
    from jiuwenswarm.server.agent_ws_server import AgentWebSocketServer

    args.database.parent.mkdir(parents=True, exist_ok=True)
    if args.expected_text is None:
        raise RuntimeError("p2-smoke requires --expected-text")
    server = AgentWebSocketServer()
    started = False
    suffix = secrets.token_hex(4)
    interaction_id = f"interaction-w2-p2-smoke-{suffix}"
    activation_id = f"activation-w2-p2-smoke-{suffix}"
    correlation_id = f"correlation:w2-p2-smoke-{suffix}"
    base: dict[str, object] = {
        "auth_token": token,
        "session_id": args.session_id,
        "correlation_id": correlation_id,
        "interaction_id": interaction_id,
        "activation_id": activation_id,
        "activation_generation": 1,
    }
    try:
        await server._start_live_voice_p3_composition()
        await server._start_live_voice_product_composition()
        registry = server._live_voice_product_composition
        if server._live_voice_p3_composition is None or registry is None:
            raise RuntimeError("production P3/product composition failed to start")
        started = True
        activated = await registry.handle_p2_activate(
            params=base,
            request_id=f"w2-p2-activate-{suffix}",
            session_id=args.session_id,
            channel_id="web",
        )
        if not activated.ok:
            raise RuntimeError(f"P2 activation failed: {activated.payload!r}")
        submit = await registry.handle_p2_submit(
            params={
                **base,
                "commit_id": f"commit-w2-p2-smoke-{suffix}",
                "turn_id": f"turn-w2-p2-smoke-{suffix}",
                "response_id": f"response-w2-p2-smoke-{suffix}",
                "committed_at": _iso_now(),
                "text": args.instruction,
                "dispatch_target": "agent",
            },
            request_id=f"w2-p2-submit-{suffix}",
            session_id=args.session_id,
            channel_id="web",
        )
        if not submit.ok:
            raise RuntimeError(f"P2 submit failed: {submit.payload!r}")

        terminal = False
        acknowledged = False
        final_texts: list[str] = []
        agent_events: list[dict[str, object]] = []
        for sequence in range(1, 257):
            polled = await asyncio.wait_for(
                registry.handle_p2_notification_next(
                    params={**base, "notification_sequence": sequence},
                    request_id=f"w2-p2-notification-{suffix}-{sequence}",
                    session_id=args.session_id,
                ),
                timeout=180,
            )
            if not polled.ok:
                raise RuntimeError(f"P2 notification failed: {polled.payload!r}")
            notification = dict(polled.payload["result"])
            agent_event = notification.get("agent_event")
            if isinstance(agent_event, dict):
                event = {
                    "seq": agent_event.get("seq"),
                    "event_type": agent_event.get("event_type"),
                    "capability": agent_event.get("capability"),
                    "error_reason": agent_event.get("error_reason"),
                }
                agent_events.append(event)
                text = agent_event.get("text")
                if isinstance(text, str) and text:
                    final_texts.append(text)
            presentation = notification.get("presentation_unit")
            response = notification.get("response")
            if isinstance(presentation, dict) and isinstance(response, dict):
                ack = await registry.handle_p2_presentation_ack(
                    params={
                        **base,
                        "response_id": response["response_id"],
                        "response_generation": response["response_generation"],
                        "surface": presentation["surface"],
                        "unit_id": presentation["unit_id"],
                        "contiguous_cursor": presentation["seq"],
                        "presented_at": _iso_now(),
                    },
                    request_id=f"w2-p2-ack-{suffix}-{sequence}",
                    session_id=args.session_id,
                )
                if not ack.ok or not dict(ack.payload["result"]).get("accepted"):
                    raise RuntimeError(f"P2 presentation ACK failed: {ack.payload!r}")
                acknowledged = True
            progress = notification.get("progress_event")
            progress_state = None
            if isinstance(progress, dict):
                payload = progress.get("payload")
                if isinstance(payload, dict):
                    progress_state = payload.get("state")
                    if progress_state == "terminal":
                        terminal = True
            print(
                "W2_P2_NOTIFICATION "
                + json.dumps(
                    {
                        "sequence": sequence,
                        "kind": notification.get("kind"),
                        "agent_event": agent_events[-1] if agent_events else None,
                        "presentation": isinstance(presentation, dict),
                        "progress_state": progress_state,
                        "terminal": terminal,
                    }
                ),
                flush=True,
            )
            if terminal and acknowledged:
                break
        if not terminal or not acknowledged:
            raise RuntimeError("P2 smoke did not reach terminal plus presentation ACK")
        if args.expected_text not in final_texts:
            raise RuntimeError(
                f"P2 final text mismatch: expected {args.expected_text!r}, "
                f"observed {final_texts!r}"
            )
        closed = await registry.handle_p2_close(
            params=base,
            request_id=f"w2-p2-close-{suffix}",
            session_id=args.session_id,
        )
        if not closed.ok:
            raise RuntimeError(f"P2 close failed: {closed.payload!r}")
        print(
            "W2_P2_SMOKE_RESULT "
            + json.dumps(
                {
                    "session_id": args.session_id,
                    "project_id": args.project_id,
                    "expected_text": args.expected_text,
                    "final_texts": final_texts,
                    "agent_events": agent_events,
                    "presentation_acknowledged": acknowledged,
                    "terminal": terminal,
                }
            ),
            flush=True,
        )
    finally:
        if started:
            await _stop(server)






def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--phase",
        choices=(
            "ab",
            "resume-b",
            "c-predecessor",
            "c-successor",
            "p2-smoke",
        ),
        required=True,
    )
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--principal-id", default="w2-d069-diagnostic-user")
    parser.add_argument("--model-intent", default="deepseek-v4-flash")
    parser.add_argument("--instruction", required=True)
    parser.add_argument("--task-id")
    parser.add_argument("--expected-text")
    return parser


def main() -> int:
    args = _parser().parse_args()
    args.data_dir = args.data_dir.resolve(strict=True)
    args.database = args.database.resolve(strict=False)
    token = _configure(args)
    if args.phase == "ab":
        asyncio.run(_run_ab(args, token))
    elif args.phase == "resume-b":
        asyncio.run(_run_b(args, token))
    elif args.phase == "c-predecessor":
        asyncio.run(_run_c_predecessor(args, token))
    elif args.phase == "c-successor":
        asyncio.run(_run_c_successor(args, token))
    elif args.phase == "p2-smoke":
        asyncio.run(_run_p2_smoke(args, token))
    return 0


if __name__ == "__main__":
    sys.exit(main())
