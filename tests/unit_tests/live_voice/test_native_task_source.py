"""Original speech survives model rewriting, durable dispatch and adjustments."""
import asyncio
import hashlib
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from jiuwenswarm.server.live_voice.native_task_source import NativeTaskSource, NativeTaskSourceError
from jiuwenswarm.server.live_voice.native_business_contract import NativeBusinessAction, NativeBusinessProposal
from jiuwenswarm.server.runtime.formal_tasks.formal_task_models import FormalTaskSpec, TaskAdjustmentRequest
from jiuwenswarm.server.runtime.formal_tasks.project_code_executor import DirectProjectCodeExecutorAdapter
from jiuwenswarm.server.runtime.formal_tasks.task_store import SqliteTaskStore
from tests.unit_tests.live_voice.test_native_interaction_runtime import (
    active_owner, turn_commit, input_transcript, delegate_proposal,
)
from tests.unit_tests.live_voice.test_native_business_registry import make_registry, call


PROPOSAL = "Write vad300_c.md and preserve all existing files."
ORIGINAL = "Write vad300_d.md and preserve all existing files."


def source(*, scope=None):
    commit = turn_commit()
    transcript = replace(input_transcript(), transcript=ORIGINAL)
    if scope is not None:
        binding = replace(commit.binding, scope=scope)
        commit, transcript = replace(commit, binding=binding), replace(transcript, binding=binding)
    return NativeTaskSource("native-business:" + "a" * 64, "task.create",
        hashlib.sha256(PROPOSAL.encode()).hexdigest(), commit, transcript)


async def admit(owner, *, number=1):
    response = await owner.accept_provider_response("response-" + str(number), "runtime-" + str(number),
        turn_id=turn_commit(number).turn_id)
    base = replace(delegate_proposal(response.response), turn_id=turn_commit(number).turn_id, request_text=PROPOSAL)
    proposal = NativeBusinessProposal(**{k: getattr(base, k) for k in base.__dataclass_fields__},
        business=NativeBusinessAction("task.create", "a" * 64, None, None, "Budget D", PROPOSAL, None))
    _, admitted = await owner.admit_delegate(proposal, committed_at="2026-09-08T06:00:00Z")
    return admitted


def test_original_and_proposal_have_distinct_persisted_meaning():
    retained = source()
    assert NativeTaskSource.from_dict(retained.to_dict()) == retained
    text = retained.agent_request(PROPOSAL)
    evidence = json.loads(text.split("\n", 1)[1])
    assert evidence["current_anchor"]["text"] == ORIGINAL
    assert evidence["model_proposal"] == PROPOSAL
    assert evidence["source_digest"] == retained.digest
    with pytest.raises(NativeTaskSourceError):
        retained.agent_request("a different instruction")


@pytest.mark.parametrize("mutation", ["null", "extra", "scope", "duplicate", "too_many", "operation", "unhashable_operation", "digest", "bool"])
def test_source_closed_bounds_and_identity(mutation):
    retained = source()
    payload = retained.to_dict()
    if mutation == "null": payload = None
    elif mutation == "extra": payload["allow_replace"] = True
    elif mutation == "scope": payload["transcript"]["binding"]["scope"]["project_id"] = "other"
    elif mutation == "duplicate": payload["preceding"] = [{"commit": payload["anchor"], "transcript": payload["transcript"]}]
    elif mutation == "too_many": payload["preceding"] = [{}] * 17
    elif mutation == "operation": payload["operation"] = "task.cancel"
    elif mutation == "unhashable_operation": payload["operation"] = []
    elif mutation == "digest": payload["instruction_sha256"] = "z" * 64
    elif mutation == "bool": payload["omitted_preceding"] = True
    with pytest.raises((NativeTaskSourceError, ValueError)):
        NativeTaskSource.from_dict(payload)


def test_reconnected_context_uses_admission_order_not_provider_clock():
    retained = source()
    old = replace(turn_commit(2), provider_session_id="older-session",
        input_audio_start_ms=5000, input_audio_end_ms=5020)
    old_text = replace(input_transcript(2), provider_session_id=old.provider_session_id)
    candidate = replace(retained, preceding=((old, old_text),))
    assert NativeTaskSource.from_dict(candidate.to_dict()) == candidate


def test_source_total_bytes_are_bounded_even_with_legal_individual_transcripts():
    retained = source()
    retained = replace(retained, transcript=replace(retained.transcript, transcript="x" * 60000))
    history = tuple((turn_commit(index), replace(input_transcript(index), transcript="y" * 60000))
        for index in range(2, 6))
    candidate = replace(retained, preceding=history[:3])
    assert NativeTaskSource.from_dict(candidate.to_dict()) == candidate
    with pytest.raises(NativeTaskSourceError, match="TOO_LARGE"):
        replace(retained, preceding=history)


@pytest.mark.asyncio
async def test_source_wait_does_not_block_runtime_and_excludes_future_turns():
    owner, runtime = await active_owner()
    try:
        admission = await admit(owner)
        pending = asyncio.create_task(owner.task_source(admission, timeout=1))
        await asyncio.sleep(0)
        assert not pending.done()
        await owner.accept_turn(turn_commit(2))
        await owner.accept_input_transcript(replace(input_transcript(), transcript=ORIGINAL))
        retained = await pending
        assert retained.anchor == turn_commit() and retained.preceding == ()
        assert retained.transcript.transcript == ORIGINAL
        assert await owner.task_source(admission) is retained
        assert runtime.snapshot().presentation.records == ()
    finally:
        await owner.close()


@pytest.mark.asyncio
async def test_missing_anchor_never_uses_proposal_and_close_wakes_wait():
    owner, runtime = await active_owner()
    admission = await admit(owner)
    before = runtime.snapshot()
    with pytest.raises(NativeTaskSourceError, match="TRANSCRIPT_UNAVAILABLE"):
        await owner.task_source(admission, timeout=.01)
    assert runtime.snapshot() == before
    waiting = asyncio.create_task(owner.task_source(admission, timeout=1))
    await asyncio.sleep(0)
    await owner.close()
    with pytest.raises(Exception):
        await asyncio.wait_for(waiting, .1)


@pytest.mark.asyncio
async def test_missing_preceding_stays_explicit_and_sealed_on_replay():
    owner, _ = await active_owner()
    try:
        await owner.accept_turn(turn_commit(2))
        admission = await admit(owner, number=2)
        await owner.accept_input_transcript(input_transcript(2))
        retained = await owner.task_source(admission)
        assert retained.preceding == ((turn_commit(), None),)
        await owner.accept_input_transcript(input_transcript())
        assert await owner.task_source(admission) is retained
        assert retained.preceding[0][1] is None
    finally:
        await owner.close()


@pytest.mark.asyncio
async def test_actual_registry_sqlite_and_executor_request_retain_d_after_model_c(tmp_path, monkeypatch):
    env = await make_registry(tmp_path, monkeypatch, input_text=ORIGINAL)
    try:
        result, params = await call(env, "task.create", name="Budget D", instruction=PROPOSAL)
        assert result["status"] == "dispatched", result
        store = env.harness.composition._core.store
        task = store.get_task(result["task_id"], env.binding.scope)
        retained = task.spec.native_source
        assert retained.transcript.transcript == ORIGINAL
        assert task.spec.instruction == PROPOSAL
        assert FormalTaskSpec.from_dict(task.spec.to_dict()) == task.spec
        reopened = SqliteTaskStore(env.harness.database)
        adapter = object.__new__(DirectProjectCodeExecutorAdapter)
        adapter._durability_store = reopened
        item = SimpleNamespace(task_id=task.task_id, attempt_id=task.attempt_id, scope=task.scope, spec=task.spec)
        text = await adapter._source_instruction(item)
        assert json.loads(text.split("\n", 1)[1])["current_anchor"]["text"] == ORIGINAL
        before = store.counts()
        replay = await env.registry.handle_native_propose(params=params, request_id="call", session_id="session-1")
        assert replay.ok and store.counts() == before
        assert store.get_task(task.task_id, env.binding.scope).spec.native_source == retained
        assert env.manager.agent.executions == []
    finally:
        await env.registry.stop()
        await env.harness.composition.stop()


@pytest.mark.asyncio
async def test_missing_source_rejects_before_task_agent_or_file_effects(tmp_path, monkeypatch):
    env = await make_registry(tmp_path, monkeypatch, input_text=None)
    try:
        before = env.harness.composition._core.store.counts()
        result, _ = await call(env, "task.create", name="D", instruction=PROPOSAL)
        assert result["status"] == "rejected" and result["reason"] == "NATIVE_TASK_SOURCE_TRANSCRIPT_UNAVAILABLE"
        assert env.harness.composition._core.store.counts() == before
        assert env.manager.agent.executions == []
    finally:
        await env.registry.stop()
        await env.harness.composition.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("rebind", [False, True])
async def test_gateway_rpc_late_transcript_releases_only_current_authorized_task(tmp_path, monkeypatch, rebind):
    from tests.unit_tests.live_voice.test_product_composition_registry import _native_input_transcript_proposal
    from jiuwenswarm.server.live_voice.openai_realtime_native_engine import NativeEngineEvent
    env = await make_registry(tmp_path, monkeypatch, input_text=None)
    route = env.registry._p2_routes[("session-1", "interaction-1")]
    owner = route.native_runtime_owner
    entered = asyncio.Event()
    original = owner.task_source
    async def waiting(admission, **kwargs):
        entered.set()
        return await original(admission, **kwargs)
    monkeypatch.setattr(owner, "task_source", waiting)
    pending = None
    try:
        before = env.harness.composition._core.store.counts()
        pending = asyncio.create_task(call(env, "task.create", name="D", instruction=PROPOSAL))
        await asyncio.wait_for(entered.wait(), 2)
        assert not pending.done()
        if rebind:
            env.harness.authority.contexts["session-1"] = replace(
                env.harness.authority.contexts["session-1"], uri=(tmp_path / "rebound").as_uri())
        value = _native_input_transcript_proposal(env.binding).input_transcript
        await env.client.propose(binding=env.binding, capability=env.capability,
            event=NativeEngineEvent(input_transcript=replace(value, transcript=ORIGINAL)), request_id="late-asr")
        if rebind:
            from jiuwenswarm.gateway.live_voice.native_interaction_runtime_client import NativeRuntimeClientError
            with pytest.raises(NativeRuntimeClientError) as rejected:
                await asyncio.wait_for(pending, 2)
            assert rejected.value.reason == "EXECUTION_CONTEXT_SCOPE_MISMATCH"
            assert env.harness.composition._core.store.counts() == before
        else:
            result, _ = await asyncio.wait_for(pending, 2)
            assert result["status"] == "dispatched", result
            task = env.harness.composition._core.store.get_task(result["task_id"], env.binding.scope)
            assert task.spec.native_source.transcript.transcript == ORIGINAL
        assert env.manager.agent.executions == []
    finally:
        if pending is not None:
            await asyncio.gather(pending, return_exceptions=True)
        await env.registry.stop()
        await env.harness.composition.stop()


def test_legacy_spec_adjustment_bytes_and_source_null_are_distinct(tmp_path):
    from tests.unit_tests.live_voice.test_project_code_executor import _spec
    legacy = _spec(tmp_path)
    original = legacy.fingerprint_bytes()
    assert "native_source" not in legacy.to_dict()
    assert FormalTaskSpec.from_dict(legacy.to_dict()).fingerprint_bytes() == original
    value = TaskAdjustmentRequest("adjust-1", "Add a header.", 1)
    assert value.to_dict() == {"adjustment_id": "adjust-1", "adjustment": "Add a header.", "requested_seq": 1}
    with pytest.raises(NativeTaskSourceError):
        FormalTaskSpec.from_dict({**legacy.to_dict(), "native_source": None})
    with pytest.raises(NativeTaskSourceError):
        TaskAdjustmentRequest.from_dict({**value.to_dict(), "native_source": None})


@pytest.mark.asyncio
async def test_durable_update_preserves_original_source_and_proves_new_requirement(tmp_path):
    from tests.unit_tests.live_voice.test_persistent_task_core import _create, _Executor, _wave2_command, NOW
    from jiuwenswarm.server.runtime.formal_tasks.persistent_task_core import PersistentTaskCore
    from jiuwenswarm.common.schema.live_voice_contract_v2 import CommandEnvelope
    invocation = _create(tmp_path)
    scope = invocation.envelope.scope
    retained = source(scope=scope)
    data = invocation.envelope.to_dict()
    data["payload"]["instruction"] = PROPOSAL
    data["payload"]["native_source"] = retained.to_dict()
    command = CommandEnvelope.from_dict(data)
    store = SqliteTaskStore(tmp_path / "source-update.sqlite")
    core = PersistentTaskCore(store, _Executor())
    created = core.execute(command, invocation.authorization, context=invocation.context, now=NOW)
    assert created.ok, created.to_dict()
    task_id, attempt_id = created.result["task_id"], created.result["attempt_id"]
    update, grant = _wave2_command(task_id, "task.update", {
        "attempt_id": attempt_id, "expected_event_head": 0, "instruction": "Use the explicitly revised requirements.",
        "constraints": None}, command_id="update-source")
    assert core.execute(update, grant, now=NOW).ok
    current = store.get_task(task_id, scope)
    assert current.spec.native_source == retained
    adapter = object.__new__(DirectProjectCodeExecutorAdapter)
    adapter._durability_store = store
    item = SimpleNamespace(task_id=task_id, attempt_id=attempt_id, scope=scope, spec=current.spec)
    text = await adapter._source_instruction(item)
    values = json.loads(text.split("\n", 1)[1])
    assert values["current_task_instruction"] == current.spec.instruction
    assert values["current_anchor"]["text"] == ORIGINAL
    with pytest.raises(RuntimeError, match="SPEC_MISMATCH"):
        await adapter._source_instruction(SimpleNamespace(**{**vars(item), "spec": replace(current.spec, instruction="forged")}))


def with_source(command, retained):
    from jiuwenswarm.common.schema.live_voice_contract_v2 import CommandEnvelope
    data = command.to_dict()
    field = "adjustment" if command.command_type == "task.adjust" else "instruction"
    data["payload"][field] = PROPOSAL
    data["payload"]["native_source"] = retained.to_dict()
    return CommandEnvelope.from_dict(data)


def test_successor_retry_reopen_preserve_source_and_reject_source_replacement(tmp_path):
    from jiuwenswarm.common.schema.live_voice_contract_v2 import TerminalOutcome
    from jiuwenswarm.server.runtime.formal_tasks.formal_task_models import FormalTaskViolation
    from jiuwenswarm.server.runtime.formal_tasks.persistent_task_core import PersistentTaskCore
    from tests.unit_tests.live_voice.test_persistent_task_core import (
        _successor_fixture, _successor_command, _observations, _retry, _context, _database_dump, NOW,
    )
    database, store, executor, core, parent, terminal, digest = _successor_fixture(tmp_path, "source-chain.sqlite")
    command, grant = _successor_command(parent, terminal, result_sha256=digest)
    retained = replace(source(scope=parent.scope), operation="task.create_successor",
        target_id=parent.task_id, expected_revision=parent.revision_number)
    command = with_source(command, retained)
    created = core.execute(command, grant, context=_context(tmp_path), now=NOW)
    assert created.ok, created.to_dict()
    child = store.get_task(created.result["task_id"], parent.scope)
    assert child.spec.native_source == retained and store.get_task(parent.task_id, parent.scope) == parent
    dispatch = store.claim_outbox("source-chain")
    assert dispatch.spec.native_source == retained
    store.complete_outbox(dispatch, executor_ref=f"legacy:{dispatch.attempt_id}",
        observations=_observations(dispatch, outcome=TerminalOutcome.CANCELLED))
    retry, retry_grant = _retry(child.task_id, child.attempt_id, TerminalOutcome.CANCELLED, 2)
    authority = store.read_retry_authority(retry)
    before = _database_dump(database)
    forged = replace(retained, transcript=replace(retained.transcript, transcript="Replace protected C."))
    with pytest.raises(FormalTaskViolation) as rejected:
        store.retry(retry, replace(authority.task.spec, native_source=forged), authority, observed_at=NOW)
    assert rejected.value.reason == "TASK_RETRY_SPEC_MISMATCH"
    assert _database_dump(database) == before
    retried = core.execute(retry, retry_grant, context=_context(tmp_path), now=NOW)
    assert retried.ok, retried.to_dict()
    reopened = SqliteTaskStore(database)
    task, attempt, _ = reopened.task_read_snapshot(child.task_id, child.scope, verify_lineage=True)
    assert task.task_id == child.task_id and attempt.attempt_number == 2
    assert task.spec.native_source == retained
    before = _database_dump(database)
    replay = PersistentTaskCore(reopened, executor).execute(retry, retry_grant, context=_context(tmp_path), now=NOW)
    assert replay.result == retried.result and _database_dump(database) == before
    assert executor.dispatches == executor.cancels == executor.adjustments == []


@pytest.mark.asyncio
async def test_direct_worker_injects_create_and_applied_adjustment_sources(tmp_path):
    from pathlib import Path
    from jiuwenswarm.common.schema.agent import AgentResponseChunk
    from jiuwenswarm.common.schema.live_voice_contract_v2 import TerminalOutcome
    from jiuwenswarm.server.runtime.formal_tasks.persistent_task_core import PersistentTaskCore
    from jiuwenswarm.server.runtime.agent_adapter.background_task_checkpoint import current_background_task_checkpoint
    from tests.unit_tests.live_voice.test_persistent_task_core import _create, _adjust, NOW
    from tests.unit_tests.live_voice.test_project_code_executor import (
        _DirectProjectExecutor, _Resolver, _direct_binding, _git_project, _wait_direct_settled,
    )

    class RecordingAgent(_DirectProjectExecutor):
        def __init__(self, project):
            super().__init__(project)
            self.release = asyncio.Event()
            self.messages = []
        async def add_messages(self, message):
            self.messages.append(message.content)
        async def process_background_code_task_stream(self, request):
            self.requests.append(request)
            self.started.set()
            await self.release.wait()
            checkpoint = current_background_task_checkpoint(request.session_id)
            await checkpoint.adopt(self)
            if checkpoint.file_plan is not None:
                await checkpoint.file_plan.seal({"requirement_head": checkpoint.file_plan.requirement_head,
                    "preserve_existing": True, "effects": [{"path": "source.txt", "operation": "create"}],
                    "required_outputs": ["source.txt"]})
                await checkpoint.file_plan.before_tool("write_file", {"file_path": "source.txt"})
            (Path(request.params["project_dir"]) / "source.txt").write_text("retained\n", encoding="utf-8")
            yield AgentResponseChunk(request.request_id, request.channel_id,
                payload={"event_type": "chat.final", "content": "Saved source.txt."}, is_complete=True)

    project = tmp_path / "source-project"
    _git_project(project)
    agent = RecordingAgent(project)
    database = tmp_path / "direct-source.sqlite"
    store = SqliteTaskStore(database)
    adapter = DirectProjectCodeExecutorAdapter(_Resolver(_direct_binding(project, agent)), database, durability_store=store)
    core = PersistentTaskCore(store, adapter)
    try:
        invocation = _create(project)
        retained = source(scope=invocation.envelope.scope)
        created = core.execute(with_source(invocation.envelope, retained), invocation.authorization,
            context=invocation.context, now=NOW)
        assert created.ok, created.to_dict()
        task_id = created.result["task_id"]
        await core.drain_outbox_once()
        await asyncio.wait_for(agent.started.wait(), 5)
        request_text = agent.requests[0].params["query"]
        evidence, _ = json.JSONDecoder().raw_decode(request_text.split("\n", 1)[1])
        assert evidence["current_anchor"]["text"] == ORIGINAL and evidence["model_proposal"] == PROPOSAL
        task = store.get_task(task_id, retained.anchor.binding.scope)
        command, grant = _adjust(task_id, PROPOSAL)
        adjustment_source = replace(retained, operation="task.adjust", source_identity="native-business:" + "b" * 64,
            target_id=task_id, expected_revision=task.revision_number,
            transcript=replace(retained.transcript, transcript="Add a header in D; preserve C."))
        command = with_source(command, adjustment_source)
        assert core.execute(command, grant, now=NOW).ok
        assert await core.drain_outbox_once(defer_adjustments=True)
        agent.release.set()
        await core.drain_inflight_adjustments(timeout=5)
        await _wait_direct_settled(adapter)
        await core.reconcile_status()
        assert len(agent.requests) == 1 and len(agent.messages) == 1
        assert adjustment_source.digest in agent.messages[0]
        assert "Add a header in D; preserve C." in agent.messages[0]
        assert store.get_task(task_id, task.scope).outcome is TerminalOutcome.COMPLETED
        reopened = SqliteTaskStore(database)
        before = reopened.counts()
        assert PersistentTaskCore(reopened, adapter).execute(command, grant, now=NOW).ok
        assert reopened.counts() == before and len(agent.messages) == 1
        assert (project / "source.txt").read_text(encoding="utf-8") == "retained\n"
        assert reopened.task_read_snapshot(task_id, task.scope, verify_lineage=True)[0].spec.native_source == retained
    finally:
        agent.release.set()
        await adapter.close(interrupt_running=True)


@pytest.mark.asyncio
async def test_registry_close_during_source_wait_has_zero_task_agent_and_late_source_effects(tmp_path, monkeypatch):
    from tests.unit_tests.live_voice.test_product_composition_registry import _native_input_transcript_proposal, _native_propose_params
    env = await make_registry(tmp_path, monkeypatch, input_text=None)
    owner = env.registry._p2_routes[("session-1", "interaction-1")].native_runtime_owner
    entered = asyncio.Event()
    original = owner.task_source
    async def waiting(admission, **kwargs):
        entered.set()
        return await original(admission, **kwargs)
    monkeypatch.setattr(owner, "task_source", waiting)
    pending = None
    try:
        store = env.harness.composition._core.store
        before = store.counts()
        pending = asyncio.create_task(call(env, "task.create", name="D", instruction=PROPOSAL))
        await asyncio.wait_for(entered.wait(), 2)
        await env.registry.stop()
        result = await asyncio.wait_for(asyncio.gather(pending, return_exceptions=True), 2)
        assert isinstance(result[0], Exception) or result[0][0]["status"] == "rejected"
        late = await env.registry.handle_native_propose(params=_native_propose_params(env.binding, env.capability,
            _native_input_transcript_proposal(env.binding)), request_id="late-closed", session_id="session-1")
        assert not late.ok
        assert store.counts() == before and env.manager.agent.executions == []
        assert env.registry._p2_routes == {}
    finally:
        if pending is not None:
            await asyncio.gather(pending, return_exceptions=True)
        await env.registry.stop()
        await env.harness.composition.stop()


@pytest.mark.asyncio
async def test_large_source_native_queries_are_bounded_without_losing_durable_evidence(tmp_path, monkeypatch):
    text = "原始" * 10000
    env = await make_registry(tmp_path, monkeypatch, input_text=text)
    try:
        store = env.harness.composition._core.store
        tasks = []
        for index in range(5):
            result, _ = await call(env, "task.create", stem=f"large-{index}", name=f"Report {index}", instruction=PROPOSAL)
            assert result["status"] == "dispatched", result
            tasks.append(store.get_task(result["task_id"], env.binding.scope))
        for operation, values in [("task.list", {}), ("task.status", {"target_id": tasks[0].task_id})]:
            result, params = await call(env, operation, stem=operation, **values)
            assert result["status"] == "dispatched", result
            encoded = json.dumps(result, ensure_ascii=False).encode()
            assert len(encoded) < 262144 and len(json.dumps(result, ensure_ascii=True)) < 524288
            assert text.encode() not in encoded
            assert tasks[0].spec.native_source.digest in encoded.decode()
            before = store.counts()
            replay = await env.registry.handle_native_propose(params=params, request_id=operation, session_id="session-1")
            assert replay.ok and json.loads(replay.payload["result"]["canonical_text"]) == result
            assert store.counts() == before
        reopened = SqliteTaskStore(env.harness.database)
        assert all(reopened.get_task(task.task_id, task.scope).spec.native_source.transcript.transcript == text for task in tasks)
        assert env.manager.agent.executions == []
    finally:
        await env.registry.stop()
        await env.harness.composition.stop()


@pytest.mark.asyncio
async def test_public_intent_cannot_self_issue_source_and_confirmation_cannot_replace_it(tmp_path, monkeypatch):
    env = await make_registry(tmp_path, monkeypatch, input_text=ORIGINAL)
    try:
        store = env.harness.composition._core.store
        before = store.counts()
        public = await env.registry.handle_p3_intent(params={
            "auth_token": env.params["auth_token"], "session_id": "session-1", "source": "structured",
            "source_id": "public-source", "correlation_id": "public-source", "committed": True,
            "structured_intent": {"operation": "task.create", "target": None,
                "arguments": {"name": "D", "instruction": PROPOSAL}},
            "native_source": source(scope=env.binding.scope).to_dict(),
        }, request_id="public-source", session_id="session-1")
        assert not public.ok and store.counts() == before
        confirm = env.registry._confirm_production_intent
        async def replace_source(**kwargs):
            request = kwargs["request"]
            original = request.native_source
            kwargs["request"] = replace(request, native_source=replace(original,
                transcript=replace(original.transcript, transcript="Overwrite all existing files.")))
            return await confirm(**kwargs)
        monkeypatch.setattr(env.registry, "_confirm_production_intent", replace_source)
        result, _ = await call(env, "task.create", stem="replaced-source", name="D", instruction=PROPOSAL)
        assert result["status"] == "rejected", result
        assert store.counts() == before
        assert env.manager.agent.executions == []
        assert env.harness.executor.dispatches == env.harness.executor.adjustments == env.harness.executor.cancels == []
    finally:
        await env.registry.stop()
        await env.harness.composition.stop()


def test_command_replay_cannot_replace_original_source(tmp_path):
    from tests.unit_tests.live_voice.test_persistent_task_core import _create, _Executor, _database_dump, NOW
    from jiuwenswarm.server.runtime.formal_tasks.persistent_task_core import PersistentTaskCore
    invocation = _create(tmp_path)
    retained = source(scope=invocation.envelope.scope)
    command = with_source(invocation.envelope, retained)
    store = SqliteTaskStore(tmp_path / "source-replay.sqlite")
    executor = _Executor()
    core = PersistentTaskCore(store, executor)
    created = core.execute(command, invocation.authorization, context=invocation.context, now=NOW)
    assert created.ok
    before = _database_dump(store.database_path)
    forged = with_source(command, replace(retained, transcript=replace(retained.transcript, transcript="Overwrite C.")))
    rejected = core.execute(forged, invocation.authorization, context=invocation.context, now=NOW)
    assert not rejected.ok and _database_dump(store.database_path) == before
    assert store.get_task(created.result["task_id"], command.scope).spec.native_source == retained
    assert executor.dispatches == executor.adjustments == executor.cancels == []
