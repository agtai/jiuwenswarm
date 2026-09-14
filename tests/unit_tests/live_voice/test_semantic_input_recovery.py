# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Recovery with real journal/CR snapshots; controlled context selection and model."""

import sqlite3
import asyncio
from datetime import UTC, datetime

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import TurnCommitLedger
from jiuwenswarm.channels.live_voice.product_composition_registry import (
    AgentServerProductCompositionRegistry,
)
from tests.unit_tests.live_voice.test_product_composition_registry import (
    _AgentManager, _shared_test_runtime,
)
from tests.unit_tests.live_voice.test_semantic_registry import (
    semantic_runtime,  # noqa: F401 -- pytest fixture
    model_output, p2_params, typed_final, present_next,
    _scope,
)


async def _matching_presentation(registry, response, prefix):
    seen = []
    # Earlier rounds can leave four notifications each in the original runtime.
    for sequence in range(1, 17):
        polled = await asyncio.wait_for(registry.handle_p2_notification_next(
            params=p2_params(notification_sequence=sequence), request_id=f"{prefix}-{sequence}",
            session_id="session-1"), 2)
        assert polled.ok, polled.payload
        notice = polled.payload["result"]
        seen.append((notice.get("kind"), notice.get("response"), bool(notice.get("presentation_unit"))))
        if notice.get("presentation_unit") and notice.get("response") == response:
            return notice
    raise AssertionError(("Recovery presentation unit not delivered", response, seen))


@pytest.mark.asyncio
@pytest.mark.parametrize("operation,rebuild,ack_before_rebuild", [
    (operation, rebuild, False)
    for operation in ("create", "status", "clarification") for rebuild in (False, True)
] + [("clarification", True, True)])
async def test_created_task_survives_unified_completion_loss_without_redispatch(
    semantic_runtime, monkeypatch, rebuild, operation, ack_before_rebuild, tmp_path,  # noqa: F811
):
    monkeypatch.setattr("jiuwenswarm.server.runtime.session.session_history.get_agent_sessions_dir",
        lambda: tmp_path / "session-history")
    s = semantic_runtime
    first = s.registry
    from jiuwenswarm.channels.live_voice.formal_history_writer import SessionFormalHistoryWriter
    from jiuwenswarm.server.runtime.session.session_history import load_history_records
    core = s.harness.composition._core
    s.program = lambda data: model_output(data, operation="task.create",
        arguments={"name": "Inventory recovery", "instruction": "Read inventory and save report.md."},
        reference=next(iter(data["context"]["pending"]), None))
    assert (await first.handle_p2_activate(params=p2_params(), request_id="activate",
        session_id="session-1", channel_id="web")).ok
    next(iter(first._p2_routes.values())).activation_lease._runtime._history_writer = SessionFormalHistoryWriter()
    assert (await first.handle_unified_submit(params=typed_final("propose", "Prepare the inventory report."),
        request_id="propose", session_id="session-1", channel_id="web")).ok
    assert core.store.counts()["tasks"] == 0
    journal = first._unified_journal
    complete = journal.complete
    lost = {}
    params = typed_final("confirm", "Confirm that exact task.")
    task_id = None
    if operation != "create":
        created = await first.handle_unified_submit(params=params, request_id="confirm",
            session_id="session-1", channel_id="web")
        assert created.ok, created.payload
        task_id = created.payload["result"]["task_id"]
        s.program = lambda data: model_output(data, operation="task.status",
            arguments={"query_kind": "status"}, target=task_id)
        params = typed_final("status", "What is the status of that inventory task?")
        if operation == "clarification":
            s.program = lambda data: {**model_output(data, route="clarification"),
                "message": "Please specify the inventory section you want to discuss."}
            params = typed_final("clarify", "Discuss a section of that inventory.")

    class ProcessLost(BaseException):
        pass

    def lose_completion(**kwargs):
        assert core.store.counts()["tasks"] == 1
        lost.update(identity=kwargs["voice_identity_sha256"], task_id=kwargs["result"]["result"].get("task_id"),
            response=kwargs["result"]["result"]["response"])
        raise ProcessLost()

    monkeypatch.setattr(journal, "complete", lose_completion)
    with pytest.raises(ProcessLost):
        await first.handle_unified_submit(params=params, request_id=operation + "-lost",
            session_id="session-1", channel_id="web")
    counts = core.store.counts()
    calls = len(s.calls), s.manager.agent.calls
    monkeypatch.setattr(journal, "complete", complete)
    original_unit = None
    if ack_before_rebuild:
        notice = await _matching_presentation(first, lost["response"], "original-poll")
        original_unit = notice["presentation_unit"]
        response = notice["response"]
        original_ack_params = p2_params(response_id=response["response_id"],
                response_generation=response["response_generation"], surface=original_unit["surface"],
                unit_id=original_unit["unit_id"], contiguous_cursor=original_unit["seq"],
                presented_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"))
        ack = await first.handle_p2_presentation_ack(params=original_ack_params,
            request_id="original-ack", session_id="session-1")
        assert ack.ok, ack.payload
        original_history = load_history_records("session-1")
        assert sum(row["role"] == "assistant" and row["request_id"] == response["response_id"]
            for row in original_history) == 1
        assert sum(row["role"] == "user" and row["request_id"] == params["commit_id"]
            for row in original_history) == 1
    manager = s.manager
    active = first
    if rebuild:
        await first.stop()
        await first._runtime.close()
        manager = _AgentManager()
        active = AgentServerProductCompositionRegistry(
            settings=first._settings, p3_composition=s.harness.composition,
            agent_manager=manager, runtime=_shared_test_runtime(manager),
            push_text_event=first._push_text_event,
            p3_confirmation_owner=first._p3_confirmation_owner,
            p3_confirmation_forwarder=first._p3_confirmation_forwarder,
            commit_ledger=TurnCommitLedger())
    try:
        if rebuild:
            assert (await active.handle_p2_activate(params=p2_params(), request_id="reactivate",
                session_id="session-1", channel_id="web")).ok
            next(iter(active._p2_routes.values())).activation_lease._runtime._history_writer = SessionFormalHistoryWriter()
        with sqlite3.connect(journal.database_path) as connection:
            assert connection.execute("SELECT status FROM unified_committed_inputs WHERE voice_identity_sha256=?",
                (lost["identity"],)).fetchone() == ("pending",)
            assert connection.execute("SELECT effect_kind FROM unified_foreground_effects WHERE voice_identity_sha256=?",
                (lost["identity"],)).fetchone() == (
                    "authoritative_presentation" if operation == "clarification" else "agent_submit",)
            connection.execute("UPDATE unified_committed_inputs SET lease_expires_at=0 WHERE status='pending'")
        recovered = await active.handle_unified_submit(params=params, request_id="retry",
            session_id="session-1", channel_id="web")
        assert recovered.ok, recovered.payload
        assert recovered.payload["result"].get("task_id") == lost["task_id"]
        assert recovered.payload["result"]["response"] == lost["response"]
        with sqlite3.connect(journal.database_path) as connection:
            assert connection.execute("SELECT status FROM unified_committed_inputs WHERE voice_identity_sha256=?",
                (lost["identity"],)).fetchone() == ("completed",)
        assert core.store.counts() == counts and counts["tasks"] == 1
        assert len(s.calls) == calls[0] and s.manager.agent.calls == calls[1]
        if rebuild:
            assert manager.agent.calls == 0
        assert s.harness.executor.dispatches == []
        task = core.store.get_task(lost["task_id"] or task_id, _scope())
        assert task.spec.name == "Inventory recovery"
        if operation == "clarification":
            text = "Please specify the inventory section you want to discuss."
            assert sum(row["role"] == "assistant" and row["content"] == text
                for row in load_history_records("session-1")) == int(ack_before_rebuild)
            notice = await _matching_presentation(active, lost["response"], "recovered-poll")
            unit = notice["presentation_unit"]
            if ack_before_rebuild:
                assert unit["unit_id"] == original_unit["unit_id"]
            response = notice["response"]
            ack_params = p2_params(response_id=response["response_id"],
                response_generation=response["response_generation"], surface=unit["surface"],
                unit_id=unit["unit_id"], contiguous_cursor=unit["seq"],
                presented_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"))
            if ack_before_rebuild:
                ack_params = original_ack_params
            before = load_history_records("session-1")
            wrong = await active.handle_p2_presentation_ack(
                params={**ack_params, "response_generation": response["response_generation"] + 1},
                request_id="wrong-recovered-ack", session_id="session-1")
            assert not wrong.ok and load_history_records("session-1") == before
            ack = await active.handle_p2_presentation_ack(params=ack_params,
                request_id="recovered-ack", session_id="session-1")
            assert ack.ok, ack.payload
            assert not ack.payload["result"]["history_pending"]
            after = load_history_records("session-1")
            assert sum(row["role"] == "assistant" and row["content"] == text for row in after) == 1
            replay_ack = await active.handle_p2_presentation_ack(params=ack_params,
                request_id="recovered-ack", session_id="session-1")
            assert replay_ack.ok and load_history_records("session-1") == after
            assert sum(row["role"] == "user" and row["request_id"] == params["commit_id"]
                for row in after) == 1
            if ack_before_rebuild:
                assert after == original_history
            assert core.store.counts() == counts
        await core.drain_outbox()
        assert s.harness.executor.dispatches == [task.attempt_id]
        assert core.store.counts()["tasks"] == 1
    finally:
        if rebuild:
            await active.stop()
            await active._runtime.close()


@pytest.mark.asyncio
async def test_frozen_dialogue_recovery_uses_current_context_without_reparsing(
    semantic_runtime, monkeypatch,  # noqa: F811 -- injected imported fixture
):
    s = semantic_runtime
    first = s.registry
    assert (await first.handle_p2_activate(
        params=p2_params(), request_id="activate", session_id="session-1", channel_id="web",
    )).ok
    s.program = lambda data: model_output(data)
    assert (await first.handle_unified_submit(
        params=typed_final("preceding", "Tell me about inventory."), request_id="preceding",
        session_id="session-1", channel_id="web",
    )).ok
    route = next(iter(first._p2_routes.values()))
    assert not (await route.activation_lease.select_formal_context(route.binding)).entries
    journal = first._unified_journal
    original_bind = journal.bind_semantic
    frozen = []

    class ProcessLost(BaseException):
        pass

    def freeze_then_lose(**kwargs):
        original_bind(**kwargs)
        frozen.append(kwargs["semantic_binding"])
        raise ProcessLost()

    monkeypatch.setattr(journal, "bind_semantic", freeze_then_lose)
    params = typed_final("recover-dialogue", "Explain inventory further.")
    with pytest.raises(ProcessLost):
        await first.handle_unified_submit(
            params=params, request_id="freeze", session_id="session-1", channel_id="web",
        )
    assert frozen[0]["body"]["input"]["context"]["tasks"] == []
    assert frozen[0]["body"]["input"]["commit"]["context_refs"] == []
    # A delayed ACK of the preceding response creates genuine CR context, without
    # a newer committed input or a fabricated assistant-history reference.
    await present_next(s, 0)
    current = await route.activation_lease.select_formal_context(route.binding)
    assert current.entries
    calls = len(s.calls)
    await first.stop()
    await first._runtime.close()
    with sqlite3.connect(journal.database_path) as connection:
        connection.execute("UPDATE unified_committed_inputs SET lease_expires_at=0 WHERE status='pending'")
    manager = _AgentManager()
    restarted = AgentServerProductCompositionRegistry(
        settings=first._settings, p3_composition=s.harness.composition,
        agent_manager=manager, runtime=_shared_test_runtime(manager),
        push_text_event=first._push_text_event,
        p3_confirmation_owner=first._p3_confirmation_owner,
        p3_confirmation_forwarder=first._p3_confirmation_forwarder,
        commit_ledger=TurnCommitLedger(),
    )
    try:
        assert (await restarted.handle_p2_activate(
            params=p2_params(), request_id="reactivate", session_id="session-1", channel_id="web",
        )).ok
        new_route = next(iter(restarted._p2_routes.values()))

        async def select_current(_lease, _binding):
            return current

        # Controlled selection port returns an actual CR snapshot. This does not
        # claim that the Host automatically reloads CR history after restart.
        monkeypatch.setattr(type(new_route.activation_lease), "select_formal_context", select_current)
        recovered = await restarted.handle_unified_submit(
            params=params, request_id="retry", session_id="session-1", channel_id="web",
        )
        assert recovered.ok, recovered.payload
        assert len(s.calls) == calls
        assert manager.agent.calls == 1
        execution = manager.agent.executions[0]
        assert execution.commit.context_refs == tuple(entry.ref for entry in current.entries)
        assert execution.allow_tools  # Normal dialogue retains its existing execution policy.
        assert s.harness.composition._core.store.counts()["tasks"] == 0
        assert s.harness.executor.dispatches == s.harness.executor.cancels == []
    finally:
        await restarted.stop()
        await restarted._runtime.close()
