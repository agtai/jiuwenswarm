# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
import pytest

from jiuwenswarm.server.live_voice.native_foreground import (
    NativeForegroundControl,
    NATIVE_FOREGROUND,
)
from jiuwenswarm.server.live_voice.native_work_runtime import (
    NativeWorkRuntime,
    NativeWorkState,
    NativeWorkViolation,
    NativeWorkSnapshot,
    context_identity,
)
from jiuwenswarm.common.schema.live_voice_contract_v2 import ResponseRef, ContextRef
from jiuwenswarm.server.runtime.agent_adapter.formal_live_voice import (
    FormalContextSnapshot,
    FormalContextEntry,
)
from tests.unit_tests.live_voice.test_agent_conversation_runtime import (
    scope,
    commit,
    runtime,
    LowerFormalAdapter,
    RecordingHistoryWriter,
)


def admission(
    runner,
    *,
    request="request-1",
    input_id="commit-1",
    foreground=False,
    current_scope=None,
):
    current_scope = current_scope or scope()
    return dict(
        scope=current_scope,
        request_id=request,
        input_id=input_id,
        instruction="hello",
        model_identity="model#0",
        model_config_version="config-version",
        context_id=context_identity(FormalContextSnapshot(current_scope)),
        runner=runner,
        foreground=foreground,
    )


def agent_input():
    reference = ContextRef.from_dict(
        {
            "source": "live_voice.native_work_specification",
            "stable_id": "spec-1",
            "uri": "urn:live-voice:work:spec-1",
            "scope": scope().to_dict(),
            "revision": {"kind": "version", "value": "1"},
            "permissions": ["context.read"],
            "expires_at": None,
            "redaction": {"policy_id": "test", "redacted": False, "fields": []},
            "extensions": {},
        }
    )
    context = FormalContextSnapshot(
        scope(), (FormalContextEntry(reference, json.dumps({"instruction": "hello"})),)
    )
    return replace(
        commit(text="Keep A and change B"), context_refs=(reference,)
    ), context


async def terminal(owner, work, *, state=None):
    for _ in range(500):
        current = owner.query(
            scope=work.scope, work_id=work.work_id, revision=work.revision
        )
        if (state is None and current.execution_settled) or current.state == state:
            return current
        await asyncio.sleep(0.002)
    raise AssertionError(f"work did not settle: {current}")


@pytest.mark.asyncio
async def test_admission_precedes_execution_and_replay_never_reexecutes():
    journal = []
    effects = []
    release = asyncio.Event()

    async def runner(control):
        assert journal[-1].state is NativeWorkState.RUNNING
        assert NATIVE_FOREGROUND.get() is None
        effects.append(control.snapshot.model_identity)
        await control.read_only(release.wait())
        return "verified final"

    owner = NativeWorkRuntime(save=journal.append)
    speech = NativeForegroundControl(ResponseRef("interaction-1", "speech-1", 1), {})
    work = await speech.run(owner.start(**admission(runner)))
    assert work.state is NativeWorkState.ACCEPTED
    assert not effects
    speech.interrupt()
    await asyncio.sleep(0.01)
    assert effects == ["model#0"]
    assert (
        owner.query(scope=scope(), work_id=work.work_id).state
        is NativeWorkState.RUNNING
    )
    replay = await owner.start(**admission(runner))
    assert replay.work_id == work.work_id
    release.set()
    done = await terminal(owner, work)
    assert (
        done.state is NativeWorkState.COMPLETED and done.result_text == "verified final"
    )
    assert (await owner.start(**admission(runner))).result_text == "verified final"
    assert effects == ["model#0"]
    assert NativeWorkSnapshot.from_dict(done.to_dict()) == done
    await owner.close()


@pytest.mark.asyncio
async def test_wrong_scope_stale_and_conflicting_request_have_zero_runner_cancel_or_store_effects():
    journal = []
    calls = []
    release = asyncio.Event()

    async def runner(control):
        calls.append(control)
        await control.read_only(release.wait())
        return "answer"

    owner = NativeWorkRuntime(save=journal.append)
    work = await owner.start(**admission(runner))
    await asyncio.sleep(0.01)
    before = len(journal)
    with pytest.raises(NativeWorkViolation, match="exact scope"):
        await owner.cancel(
            scope=scope(session_id="foreign"), work_id=work.work_id, revision=1
        )
    with pytest.raises(NativeWorkViolation) as stale:
        await owner.cancel(scope=scope(), work_id=work.work_id, revision=2)
    assert stale.value.reason == "NATIVE_WORK_REVISION_STALE"
    changed = admission(runner)
    changed["model_config_version"] = "changed"
    with pytest.raises(NativeWorkViolation) as conflict:
        await owner.start(**changed)
    assert conflict.value.reason == "NATIVE_WORK_REQUEST_CONFLICT"
    changed = admission(runner)
    changed["instruction"] = "different full requirements"
    with pytest.raises(NativeWorkViolation) as conflict:
        await owner.start(**changed)
    assert conflict.value.reason == "NATIVE_WORK_REQUEST_CONFLICT"
    changed = admission(runner, request="oversized-specification")
    changed["instruction"] = "中" * 1366
    with pytest.raises(NativeWorkViolation):
        await owner.start(**changed)
    assert owner.list(scope=scope(session_id="foreign")) == ()
    assert (
        len(journal) == before and len(calls) == 1 and not calls[0].cancelled.is_set()
    )
    await owner.cancel(scope=scope(), work_id=work.work_id, revision=1)
    assert (await terminal(owner, work)).state is NativeWorkState.CANCELLED
    assert owner.query(scope=scope(), work_id=work.work_id).result_text is None
    await owner.close()


@pytest.mark.asyncio
async def test_update_waits_real_old_cleanup_before_new_version_and_fences_late_result():
    started = asyncio.Event()
    cleanup = asyncio.Event()
    new_started = asyncio.Event()

    async def old(control):
        started.set()
        await control.cancelled.wait()
        await cleanup.wait()
        return "stale old final"

    async def revised(control):
        new_started.set()
        return "revised final"

    owner = NativeWorkRuntime(cancel_settlement_seconds=0.5)
    original = await owner.start(**admission(old))
    await started.wait()
    args = admission(revised, request="request-2", input_id="commit-2")
    args.pop("foreground")
    updated = await owner.update(work_id=original.work_id, revision=1, **args)
    assert updated.work_id == original.work_id and updated.revision == 2
    assert (
        await owner.update(work_id=original.work_id, revision=1, **args)
    ).revision == 2
    await asyncio.sleep(0.01)
    assert not new_started.is_set()
    with pytest.raises(NativeWorkViolation):
        await owner.cancel(scope=scope(), work_id=original.work_id, revision=1)
    cleanup.set()
    result = await terminal(owner, updated)
    assert (
        result.state is NativeWorkState.COMPLETED
        and result.result_text == "revised final"
    )
    previous = owner.query(scope=scope(), work_id=original.work_id, revision=1)
    assert previous.state is NativeWorkState.SUPERSEDED and previous.result_text is None
    await owner.close()


@pytest.mark.asyncio
async def test_capacity_reserves_foreground_and_unknown_cleanup_keeps_slot():
    releases = [asyncio.Event(), asyncio.Event()]
    calls = []

    def runner(index):
        async def run(control):
            calls.append(index)
            await releases[index].wait()  # deliberately uncooperative cleanup
            return "late"

        return run

    owner = NativeWorkRuntime(
        max_active=2, reserved_foreground=1, cancel_settlement_seconds=0.01
    )
    first = await owner.start(**admission(runner(0)))
    with pytest.raises(NativeWorkViolation) as full:
        await owner.start(**admission(runner(1), request="other"))
    assert full.value.reason == "NATIVE_WORK_CAPACITY_FULL"
    foreground = await owner.start(
        **admission(runner(1), request="foreground", foreground=True)
    )
    await asyncio.sleep(0.01)
    await owner.cancel(scope=scope(), work_id=first.work_id, revision=1)
    pending = await terminal(owner, first, state=NativeWorkState.UNKNOWN)
    assert not pending.execution_settled
    with pytest.raises(NativeWorkViolation) as still_full:
        await owner.start(
            **admission(runner(1), request="cannot-reuse", foreground=True)
        )
    assert still_full.value.reason == "NATIVE_WORK_CAPACITY_FULL"
    releases[0].set()
    releases[1].set()
    assert (await terminal(owner, first)).state is NativeWorkState.UNKNOWN
    await terminal(owner, foreground)
    assert sorted(calls) == [0, 1]
    await owner.close()


@pytest.mark.asyncio
async def test_persistence_failure_before_admission_and_before_running_produces_zero_effects():
    effects = []

    async def runner(_control):
        effects.append("forbidden")
        return "answer"

    def fail(_snapshot):
        raise OSError("disk unavailable")

    owner = NativeWorkRuntime(save=fail)
    with pytest.raises(NativeWorkViolation) as error:
        await owner.start(**admission(runner))
    assert error.value.reason == "NATIVE_WORK_PERSISTENCE_FAILED"
    assert not effects and owner.list(scope=scope()) == ()
    await owner.close()

    def fail_running(snapshot):
        if snapshot.state is NativeWorkState.RUNNING:
            raise OSError("disk failed after acceptance")

    owner = NativeWorkRuntime(save=fail_running)
    work = await owner.start(**admission(runner))
    failed = await terminal(owner, work, state=NativeWorkState.UNKNOWN)
    assert failed.reason == "NATIVE_WORK_PERSISTENCE_FAILED" and not effects
    await owner.close()


@pytest.mark.asyncio
async def test_restart_restores_terminal_or_unknown_never_replays_and_close_cancels_live_work():
    saved = {}
    calls = []

    async def runner(control):
        calls.append(1)
        await control.read_only(asyncio.Event().wait())
        return "never"

    owner = NativeWorkRuntime(
        save=lambda s: saved.__setitem__((s.work_id, s.revision), s)
    )
    work = await owner.start(**admission(runner))
    await asyncio.sleep(0.01)
    restored = NativeWorkRuntime(restored=tuple(saved.values()))
    recovered = restored.query(scope=scope(), work_id=work.work_id)
    assert (
        recovered.state is NativeWorkState.UNKNOWN
        and recovered.reason == "PROCESS_OWNERSHIP_LOST"
    )
    assert (await restored.start(**admission(runner))).state is NativeWorkState.UNKNOWN
    assert calls == [1]
    await restored.close()
    closed = await owner.close()
    assert closed[0].state is NativeWorkState.CANCELLED and closed[0].execution_settled
    with pytest.raises(NativeWorkViolation) as error:
        await owner.start(**admission(runner, request="after-close"))
    assert error.value.reason == "NATIVE_WORK_CLOSED"


@pytest.mark.asyncio
async def test_agent_work_uses_actual_harness_independent_of_speech_and_without_history():
    release = asyncio.Event()
    lower = LowerFormalAdapter(final="real formal bridge final", release=release)
    history = RecordingHistoryWriter()
    agent = runtime(lower, history, native_delegate_timeout_seconds=0.01)
    await agent.start()
    current, selected = agent_input()
    owner = NativeWorkRuntime()

    async def runner(control):
        return await agent.execute_native_work(
            control=control,
            commit=current,
            context=selected,
            correlation_id="work-correlation",
        )

    speech = NativeForegroundControl(
        ResponseRef("interaction-1", "unrelated-speech", 1), {}
    )
    args = admission(runner)
    args["context_id"] = context_identity(selected)
    work = await speech.run(owner.start(**args))
    await asyncio.wait_for(lower.started.wait(), 1)
    speech.interrupt()
    await asyncio.sleep(0.025)
    assert agent._harness.snapshot().cancel_effects == 0
    metadata = lower.requests[0].metadata
    assert metadata["formal_live_voice_read_only_tools"] is True
    assert metadata["formal_live_voice_model_identity"] == "model#0"
    assert metadata["formal_live_voice_model_config_version"] == "config-version"
    release.set()
    result = await terminal(owner, work)
    assert (
        result.state is NativeWorkState.COMPLETED
        and result.result_text == "real formal bridge final"
    )
    assert lower.calls == 1 and lower.legacy_calls == 0
    assert (
        history.users
        == history.assistant_intents
        == history.native_assistant_intents
        == []
    )
    snapshot = agent.snapshot()
    assert (
        snapshot.queued_notifications == 0
        and snapshot.conversation.presentation.records == ()
    )
    await owner.close()
    await agent.close(timeout_seconds=1.0)


@pytest.mark.asyncio
async def test_agent_work_exact_cancel_waits_harness_terminal_and_bad_binding_has_zero_effects():
    lower = LowerFormalAdapter(release=asyncio.Event())
    history = RecordingHistoryWriter()
    agent = runtime(lower, history)
    await agent.start()
    current, selected = agent_input()
    owner = NativeWorkRuntime()

    async def runner(control):
        return await agent.execute_native_work(
            control=control,
            commit=current,
            context=selected,
            correlation_id="work-correlation",
        )

    args = admission(runner)
    args["context_id"] = context_identity(selected)
    work = await owner.start(**args)
    await asyncio.wait_for(lower.started.wait(), 1)
    cancelling = await owner.cancel(scope=scope(), work_id=work.work_id, revision=1)
    assert cancelling.state is NativeWorkState.CANCELLING
    assert (await terminal(owner, work)).state is NativeWorkState.CANCELLED
    assert agent._harness.snapshot().cancel_effects == 1
    assert agent._harness.snapshot().active_rounds == ()
    invalid = await owner.start(
        **admission(runner, request="bad-binding", input_id="foreign-commit")
    )
    failed = await terminal(owner, invalid)
    assert (
        failed.state is NativeWorkState.FAILED
        and failed.reason == "NATIVE_WORK_BINDING_MISMATCH"
    )
    assert lower.calls == 1 and agent._harness.snapshot().cancel_effects == 1
    assert history.users == history.assistant_intents == []
    await owner.close()
    await agent.close(timeout_seconds=1.0)


@pytest.mark.asyncio
async def test_concurrent_retries_and_immediate_revision_cancel_never_execute_old_input():
    calls = []

    async def runner(control):
        calls.append(control.snapshot.revision)
        return "verified"

    owner = NativeWorkRuntime()
    copies = await asyncio.gather(
        *(owner.start(**admission(runner)) for _ in range(12))
    )
    assert len({work.work_id for work in copies}) == 1
    await terminal(owner, copies[0])
    assert calls == [1]

    work = await owner.start(**admission(runner, request="new-request"))
    args = admission(runner, request="replacement", input_id="replacement-input")
    args.pop("foreground")
    replacement = await owner.update(work_id=work.work_id, revision=1, **args)
    await owner.cancel(scope=scope(), work_id=work.work_id, revision=2)
    assert (await terminal(owner, replacement)).state is NativeWorkState.CANCELLED
    previous = await terminal(owner, work)
    assert previous.state is NativeWorkState.SUPERSEDED
    assert calls == [1]
    await owner.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failed_state", [NativeWorkState.COMPLETED, NativeWorkState.CANCELLING]
)
async def test_terminal_and_cancel_checkpoint_failure_never_claim_success_or_replay(
    failed_state,
):
    release = asyncio.Event()
    effects = []
    saved = []

    async def runner(control):
        effects.append("read")
        await control.read_only(release.wait())
        return "verified"

    def save(snapshot):
        if snapshot.state is failed_state:
            raise OSError("checkpoint failure")
        saved.append(snapshot)

    owner = NativeWorkRuntime(save=save)
    work = await owner.start(**admission(runner))
    await asyncio.sleep(0.01)
    if failed_state is NativeWorkState.CANCELLING:
        rejected = await owner.cancel(scope=scope(), work_id=work.work_id, revision=1)
        assert rejected.state is NativeWorkState.UNKNOWN
    else:
        release.set()
    unknown = await terminal(owner, work, state=NativeWorkState.UNKNOWN)
    assert (
        unknown.result_text is None
        and unknown.reason == "NATIVE_WORK_PERSISTENCE_FAILED"
    )
    assert (await owner.start(**admission(runner))).state is NativeWorkState.UNKNOWN
    assert effects == ["read"]
    await owner.close()


@pytest.mark.asyncio
async def test_work_deadline_cancels_and_shutdown_reports_unsettled_truth_without_freeing_live_owner():
    owner = NativeWorkRuntime(timeout_seconds=0.01, cancel_settlement_seconds=0.02)

    async def cooperative(control):
        await control.read_only(asyncio.Event().wait())
        return "never"

    work = await owner.start(**admission(cooperative))
    done = await terminal(owner, work)
    assert (
        done.state is NativeWorkState.CANCELLED
        and done.reason == "WORK_DEADLINE_EXCEEDED"
    )
    await owner.close()

    release = asyncio.Event()

    async def uncooperative(_control):
        await release.wait()
        return "late"

    owner = NativeWorkRuntime(cancel_settlement_seconds=0.01)
    work = await owner.start(**admission(uncooperative))
    await asyncio.sleep(0.01)
    shutdown = await owner.close()
    assert (
        shutdown[0].state is NativeWorkState.UNKNOWN
        and not shutdown[0].execution_settled
    )
    release.set()
    assert (await terminal(owner, work)).state is NativeWorkState.UNKNOWN


@pytest.mark.asyncio
async def test_restore_completed_result_and_bounded_ledger_reject_new_effects():
    calls = []

    async def runner(_control):
        calls.append(1)
        return "retained verified answer"

    owner = NativeWorkRuntime(max_active=2, max_records=2)
    first = await owner.start(**admission(runner))
    done = await terminal(owner, first)
    second = await owner.start(**admission(runner, request="second"))
    await terminal(owner, second)
    with pytest.raises(NativeWorkViolation) as full:
        await owner.start(**admission(runner, request="third"))
    assert full.value.reason == "NATIVE_WORK_LEDGER_FULL" and calls == [1, 1]
    restored = NativeWorkRuntime(restored=(done,))
    replay = await restored.start(**admission(runner))
    assert (
        replay.state is NativeWorkState.COMPLETED
        and replay.result_text == "retained verified answer"
    )
    assert calls == [1, 1]
    await restored.close()
    await owner.close()
