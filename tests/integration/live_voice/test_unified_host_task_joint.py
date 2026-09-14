# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.
"""Current unified ingress with real Host runtime, Task core and SQLite.

Only configured model responses and the lower Agent are controlled. This is
execution/lifetime evidence, not natural-language or physical voice acceptance.
"""

import asyncio
import json
import sqlite3
from types import SimpleNamespace

import pytest

from jiuwenswarm.runtime.service import AgentRuntime
from jiuwenswarm.server.runtime.formal_tasks.unified_committed_input import SqliteUnifiedCommittedInputJournal
from jiuwenswarm.server.runtime.session.session_history import load_history_records
from tests.support.live_voice.semantic_model import decision
from tests.integration.live_voice.test_d90_formal_task_vertical import (
    NOW, EXPIRY, PRODUCT_TOKEN, _project, _context, _scope, _git, _wait,
    _DirectAgentFacade, _SlowConversationAdapter, _JointProductAgentManager,
    _ProductAuthorityResolver, _ProductModelResolver, _Resolver,
    _joint_product_p2_params, ProjectExecutionBinding, DirectProjectCodeExecutorAdapter,
    SqliteTaskStore, PersistentTaskCore, TurnCommitLedger, BoundedP3ConfirmationOwner,
    ProductP3ConfirmationForwarder, P3AuthenticatedComposition, StaticBearerAuthenticator,
    AuthenticatedPrincipal, P3_PRODUCT_AUTHORITY_OPERATIONS, FormalTaskPolicyAdapter,
    AgentServerProductCompositionRegistry, ProductCompositionSettings, TerminalOutcome,
)


class JointModel:
    def __init__(self, calls):
        self.calls = calls

    async def invoke(self, *, messages, tools, **options):
        assert tools == []
        data = json.loads(messages[1].content)
        self.calls.append(data["commit"]["text"])
        text = data["commit"]["text"]
        if text == "create joint task":
            value = decision(data, "task.create", {
                "name": "Synthetic release notes",
                "instruction": "Draft a synthetic dependency release note.",
            })
        elif text == "cancel joint task":
            assert len(data["context"]["tasks"]) == 1
            value = decision(data, "task.cancel", target=data["context"]["tasks"][0]["task_id"], kind="task_id")
        elif text == "confirm the pending task":
            candidates = [p for p in data["context"]["pending"] if p["operation"] == "task.create"]
            assert len(candidates) == 1, candidates
            pending = candidates[0]
            value = decision(data, pending["operation"], pending["arguments"],
                pending["target"], pending["target_kind"], pending)
        else:
            assert text in {"keep the conversation running", "continue a new foreground answer"}
            value = decision(data)
        return SimpleNamespace(content=json.dumps(value), tool_calls=[])


class JointModelResolver(_ProductModelResolver):
    def __init__(self):
        self.calls = []

    def resolve(self, *args, **kwargs):
        from dataclasses import replace
        result = super().resolve(*args, **kwargs)
        return replace(result, model=JointModel(self.calls) if kwargs.get("instantiate") else None)


class JointAgentManager(_JointProductAgentManager):
    def get_agent_nowait(self, **kwargs):
        return self.agent

    async def begin_foreground_chat(self, *args, **kwargs):
        pass

    async def end_foreground_chat(self, *args, **kwargs):
        pass

    async def cancel_all_inflight_work(self, *args, **kwargs):
        pass

    async def cleanup(self):
        pass


class JointDialogueAgent(_SlowConversationAdapter):
    def __init__(self):
        super().__init__()
        self.cancelled = set()
        self.finished = set()
        self.hold_text = None

    async def process_formal_live_voice_stream_impl(self, request, inputs):
        hold = self.hold_text is not None and self.hold_text in str(inputs.get("query", ""))
        if self.entered and not hold:
            self.release.setdefault(request.request_id, asyncio.Event()).set()
        try:
            async for item in super().process_formal_live_voice_stream_impl(request, inputs):
                yield item
            self.finished.add(request.request_id)
        except asyncio.CancelledError:
            self.cancelled.add(request.request_id)
            raise


@pytest.mark.asyncio
@pytest.mark.parametrize("finish", ["complete", "cancel", "barge"])
async def test_unified_task_replay_scope_and_voice_close_share_host_lifetime(tmp_path, monkeypatch, finish):
    monkeypatch.setattr("openjiuwen.core.application.tasks.task_store.utc_now", lambda: NOW)
    monkeypatch.setattr("jiuwenswarm.server.runtime.session.session_history.get_agent_sessions_dir",
        lambda: tmp_path / "sessions")
    project = tmp_path / "project"
    revision = _project(project)
    database = tmp_path / "state" / "task.sqlite3"
    task_agent = _DirectAgentFacade(project)

    async def fence():
        assert _git(project, "rev-parse", "HEAD") == revision

    binding = ProjectExecutionBinding(
        execution_agent=object(), project_executor=task_agent,
        effective_execution_root=str(project.resolve()),
        execution_target={"project_dir": str(project.resolve()), "project_id": "project-1",
            "origin_session_id": "session-1", "origin_channel_id": "web"},
        owner_scope={"channel_id": "formal-task-core", "session_id": "session-1", "app_id": "live-voice"},
        resolved_revision_kind="version", resolved_revision_value=revision,
        model_identity="default#0", model_config_version="catalog-v1", dispatch_fence=fence,
    )
    executor = DirectProjectCodeExecutorAdapter(_Resolver(binding), database, clock=lambda: NOW)
    store = SqliteTaskStore(database)
    core = PersistentTaskCore(store, executor)
    ledger = TurnCommitLedger(capacity=128)
    confirmations = BoundedP3ConfirmationOwner(database, enabled=True)
    forwarder = ProductP3ConfirmationForwarder(confirmations)
    models = JointModelResolver()
    composition = P3AuthenticatedComposition(
        authenticator=StaticBearerAuthenticator(token=PRODUCT_TOKEN, principal=AuthenticatedPrincipal(
            principal_id="principal-1", allowed_project_ids=frozenset({"project-1"}),
            allowed_operations=P3_PRODUCT_AUTHORITY_OPERATIONS | {"agent.chat"}, expires_at=EXPIRY)),
        authority_resolver=_ProductAuthorityResolver(_context(project, revision), project),
        core=core, confirmation_verifier=forwarder, model_resolver=models,
        policy=FormalTaskPolicyAdapter(ledger), reconcile_interval=3600, clock=lambda: NOW,
        executor_profiles=(executor.capability_profile(),),
    )
    dialogue_agent = JointDialogueAgent()
    manager = JointAgentManager(dialogue_agent)

    async def initialized():
        pass

    async def push(message):
        return True

    runtime = AgentRuntime(agent_manager=manager, initializer=initialized)
    registry = AgentServerProductCompositionRegistry(
        settings=ProductCompositionSettings(p2_enabled=True, p3_text_enabled=True, p3_mutation_enabled=True),
        p3_composition=composition, agent_manager=manager, runtime=runtime, push_text_event=push,
        p3_confirmation_owner=confirmations, p3_confirmation_forwarder=forwarder,
        commit_ledger=ledger, unified_journal=SqliteUnifiedCommittedInputJournal(database),
    )

    async def submit(stem, text, **claims):
        return await asyncio.wait_for(registry.handle_unified_submit(params={**_joint_product_p2_params(),
            "commit_id": "commit-" + stem, "turn_id": "turn-" + stem,
            "committed_at": NOW, "text": text, "input_kind": "text", "input_state": "final", **claims},
            request_id="request-" + stem, session_id="session-1", channel_id="web"), 10)

    await composition.start()
    try:
        activated = await registry.handle_p2_activate(params=_joint_product_p2_params(),
            request_id="activate", session_id="session-1", channel_id="web")
        assert activated.ok, activated.payload
        dialogue = await submit("dialogue", "keep the conversation running")
        assert dialogue.ok, dialogue.payload
        await _wait(lambda: bool(dialogue_agent.entered))
        pending = await submit("create", "create joint task")
        assert pending.ok, pending.payload
        assert pending.payload["result"]["status"] == "round_accepted", pending.payload
        assert store.counts()["tasks"] == 0
        confirmed_text = "confirm the pending task"
        created = await submit("confirm", confirmed_text)
        assert created.ok, created.payload
        task_id = created.payload["result"]["task_id"]
        await _wait(lambda: bool(task_agent.requests))
        await composition.reconcile_once()
        assert store.get_task(task_id, _scope()).state.value == "running"
        counts = store.counts()
        replay = await submit("confirm", confirmed_text)
        assert replay.payload == created.payload
        rejected = await registry.handle_p3_query(operation="task.status", params={
            "auth_token": PRODUCT_TOKEN, "session_id": "session-1",
            "task_id": task_id, "claimed_project_id": "foreign"},
            request_id="wrong-scope", session_id="session-1")
        assert not rejected.ok
        assert store.counts() == counts and len(task_agent.requests) == 1
        def durable_state():
            with sqlite3.connect(database) as connection:
                return tuple(connection.iterdump())
        before = durable_state()
        model_calls, agent_calls = len(models.calls), len(dialogue_agent.entered)
        wrong_submit = await submit("foreign", "create joint task", claimed_project_id="foreign")
        assert not wrong_submit.ok, wrong_submit.payload
        assert wrong_submit.payload["error"]["reason"] == "PROJECT_MISMATCH", wrong_submit.payload
        stale = await submit("confirm", "create joint task")
        assert not stale.ok and stale.payload["error"]["reason"] == "UNIFIED_INPUT_ID_CONFLICT", stale.payload
        assert durable_state() == before
        assert len(models.calls) == model_calls and len(dialogue_agent.entered) == agent_calls
        assert len(task_agent.requests) == 1 and not (project / "RESULT-joint.md").exists()
        if finish == "barge":
            response = dialogue.payload["result"]["response"]
            rejected_barge = await registry.handle_p2_barge_in(params={
                **_joint_product_p2_params(), "action_id": "interrupt-current-dialogue",
                "response_id": response["response_id"],
                "response_generation": response["response_generation"], "cancel_response": True,
            }, request_id="stale-barge", session_id="session-1")
            assert not rejected_barge.ok, rejected_barge.payload
            assert rejected_barge.payload["error"]["reason"] == "STALE_RESPONSE_OUTPUT"
            assert not dialogue_agent.cancelled
            assert durable_state() == before
            # The real Host serializes foreground execution in one public
            # session. Settle its first dialogue before starting the next;
            # the independent durable Task remains running throughout.
            first_dialogue = next(iter(dialogue_agent.entered))
            dialogue_agent.release[first_dialogue].set()
            await _wait(lambda: first_dialogue in dialogue_agent.finished)
            second_route = _joint_product_p2_params(correlation_id="correlation-second",
                interaction_id="interaction-second", activation_id="activation-second")
            activated_second = await registry.handle_p2_activate(params=second_route,
                request_id="activate-second", session_id="session-1", channel_id="web")
            assert activated_second.ok, activated_second.payload
            previous_dialogues = set(dialogue_agent.entered)
            dialogue_agent.hold_text = "continue a new foreground answer"
            current_dialogue = await submit("second-dialogue", dialogue_agent.hold_text, **second_route)
            assert current_dialogue.ok, current_dialogue.payload
            await _wait(lambda: bool(set(dialogue_agent.entered) - previous_dialogues - dialogue_agent.finished))
            active_dialogues = set(dialogue_agent.entered) - previous_dialogues - dialogue_agent.finished
            assert len(active_dialogues) == 1
            second_dialogue = active_dialogues.pop()
            response = current_dialogue.payload["result"]["response"]
            interrupted = await registry.handle_p2_barge_in(params={
                **second_route, "action_id": "interrupt-second-dialogue",
                "response_id": response["response_id"],
                "response_generation": response["response_generation"], "cancel_response": True,
            }, request_id="barge", session_id="session-1")
            assert interrupted.ok, interrupted.payload
            assert interrupted.payload["result"]["applied"] is True
            assert second_dialogue not in dialogue_agent.cancelled
            interrupt_params = {**second_route, "action_id": "stop-second-generation",
                "response_id": response["response_id"], "response_generation": response["response_generation"]}
            before_interrupt = durable_state()
            forbidden_scope = await registry.handle_p2_interrupt_generation(
                params={**interrupt_params, "cancel_scope": "task.cancel"},
                request_id="forbidden-cancel-scope", session_id="session-1")
            assert not forbidden_scope.ok, forbidden_scope.payload
            assert durable_state() == before_interrupt
            assert second_dialogue not in dialogue_agent.cancelled
            generation_interrupted = await registry.handle_p2_interrupt_generation(
                params=interrupt_params, request_id="stop-generation", session_id="session-1")
            assert generation_interrupted.ok, generation_interrupted.payload
            await _wait(lambda: second_dialogue in dialogue_agent.cancelled)
            replayed_interrupt = await registry.handle_p2_interrupt_generation(
                params=interrupt_params, request_id="stop-generation", session_id="session-1")
            assert replayed_interrupt.payload == generation_interrupted.payload
            assert second_dialogue not in dialogue_agent.finished
            assert dialogue_agent.cancelled == {second_dialogue}
            assert store.get_task(task_id, _scope()).outcome is None
            assert not task_agent.release["joint"].is_set()
            assert len(task_agent.requests) == 1
            second_closed = await registry.handle_p2_close(params=second_route,
                request_id="close-second", session_id="session-1")
            assert second_closed.ok, second_closed.payload
            history = load_history_records("session-1")
            assert any(row["content"] == "continue a new foreground answer" for row in history)
            assert all(row["role"] == "user" for row in history), history
            assert len({row["id"] for row in history}) == len(history)
        if finish == "cancel":
            # Current explicit semantic cancel supplies consent to the normal
            # durable claim; it does not fabricate a second utterance.
            cancelled = await submit("cancel", "cancel joint task")
            assert cancelled.ok, cancelled.payload
            assert cancelled.payload["result"]["task_id"] == task_id
            await composition.reconcile_once()
            assert store.get_task(task_id, _scope()).outcome is TerminalOutcome.CANCELLED
            assert not (project / "RESULT-joint.md").exists()
            first_dialogue = next(iter(dialogue_agent.entered))
            assert first_dialogue not in dialogue_agent.cancelled | dialogue_agent.finished
            dialogue_agent.release[first_dialogue].set()
            await _wait(lambda: first_dialogue in dialogue_agent.finished)
            assert first_dialogue not in dialogue_agent.cancelled
        closed = await registry.handle_p2_close(params=_joint_product_p2_params(),
            request_id="close-voice", session_id="session-1")
        assert closed.ok, closed.payload
        if finish in {"complete", "barge"}:
            assert store.get_task(task_id, _scope()).outcome is None
            assert not task_agent.release["joint"].is_set()
            task_agent.release["joint"].set()
            await _wait(lambda: not executor._running)
            summary = await composition.reconcile_once()
            record = store.get_task(task_id, _scope())
            assert record.outcome is TerminalOutcome.COMPLETED, (record.state, record.attempt_id, summary, store.counts())
            assert (project / "RESULT-joint.md").read_text() == "completed joint\n"
            result = await registry.handle_p3_query(operation="task.result", params={
                "auth_token": PRODUCT_TOKEN, "session_id": "session-1", "task_id": task_id},
                request_id="read-completed-result", session_id="session-1")
            assert result.ok, result.payload
            assert result.payload["result"]["availability"] == "available", result.payload
            saved = result.payload["result"]["task_result"]
            assert saved["task_id"] == task_id and saved["attempt_id"] == record.attempt_id
            assert saved["result_text"] == "completed"
        assert (project / "README.md").read_text() == "baseline\n"
        assert len(task_agent.requests) == 1
    finally:
        for release in dialogue_agent.release.values():
            release.set()
        for release in task_agent.release.values():
            release.set()
        try:
            await asyncio.wait_for(registry.stop(), 5)
        finally:
            try:
                await asyncio.wait_for(composition.stop(), 5)
            finally:
                try:
                    await asyncio.wait_for(executor.close(), 5)
                finally:
                    await asyncio.wait_for(runtime.close(), 5)
