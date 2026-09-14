# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Recovery with real journal/CR snapshots; controlled context selection and model."""

import sqlite3

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
)


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
