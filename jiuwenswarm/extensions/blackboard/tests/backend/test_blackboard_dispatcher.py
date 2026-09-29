"""The dispatcher on a member's jiuwenswarm: the turn prompt, and chat tasks run end to end against a
real host with a stand-in AgentServer client."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Callable

from jiuwenswarm.extensions.blackboard.client.dispatcher import CHANNEL, MandateDispatcher, answer_text
from jiuwenswarm.extensions.blackboard.client.prompt import build_turn_prompt
from jiuwenswarm.extensions.blackboard.common import protocol as p
from jiuwenswarm.extensions.blackboard.common.config import HostSettings
from jiuwenswarm.extensions.blackboard.tests.backend.support import Instance, eventually, free_port

AGENT = [{"kind": "agent"}]


def test_the_prompt_fences_workspace_material_and_names_the_reply_place():
    material = {
        "origin": "comment",
        "requester": "Alice",
        "instruction": "shorten this",
        "workspace": {"id": "ws1", "title": "Launch plan"},
        "scope": {"doc_id": "d1", "doc_title": "Plan", "block_from": "b1", "block_to": "b1"},
        "instructions_doc": {"id": "d0", "title": "Instructions", "markdown": "Write plainly."},
        "docs": [{"id": "d1", "title": "Plan", "is_instructions": False}],
        "passage": "<!-- block:b1 -->\nWe ship once the tests pass.",
        "quote": "once the tests pass",
        "thread": [{"author": "Alice", "kind": "person", "body": "@jiuwen shorten this"}],
        "chat": [],
        "answer": None,
    }
    prompt = build_turn_prompt(material, nonce="n1")
    assert 'Alice gave you a task through a comment on a passage in the Blackboard workspace "Launch plan"' in prompt
    assert 'Scope: the commented passage of the document "Plan" (block b1)' in prompt
    assert "<instructions-n1>\nWrite plainly.\n</instructions-n1>" in prompt
    assert "<thread-n1>\nAlice: @jiuwen shorten this\n</thread-n1>" in prompt
    assert "posted in the comment thread" in prompt
    assert prompt.rstrip().endswith("<request-n1>\nshorten this\n</request-n1>")

    answered = build_turn_prompt(
        {
            **material,
            "origin": "workspace_chat",
            "scope": {},
            "chat": ["Bob: we lack a risks part"],
            "answer": {"question": "Which risks?", "options": [{"label": "A"}, {"label": "B"}], "chosen": "B", "answered_by": "Carol", "accepted_by": "Alice"},
        },
        nonce="n2",
    )
    assert "Scope: the whole workspace." in answered
    assert "<chat-n2>\nBob: we lack a risks part\n</chat-n2>" in answered
    assert "Options: 1. A; 2. B" in answered and "The answer (Carol, accepted by Alice)" in answered
    assert answered.rstrip().endswith("Continue the task with this answer.")


def test_the_final_answer_is_read_from_the_usual_response_shapes():
    assert answer_text({"content": {"output": "Done."}}) == "Done."
    assert answer_text({"content": "Done."}) == "Done."
    assert answer_text({"text": "Done."}) == "Done."
    assert answer_text(None) == ""


@dataclass
class _Response:
    ok: bool
    payload: dict[str, Any]


class FakeAgent:
    """Stands in for the AgentServer client: records requests and answers chat turns with `reply`."""

    def __init__(self, reply: Callable[[Any], Any]) -> None:
        self.reply = reply
        self.envelopes: list[Any] = []
        self.release = asyncio.Event()

    async def send_request(self, envelope: Any, *, timeout: float | None = None) -> _Response:
        self.envelopes.append(envelope)
        method = envelope.method
        if method == "session.create":
            return _Response(True, {"session_id": "sess-new"})
        if method == "chat.interrupt":
            self.release.set()
            return _Response(True, {"success": True})
        result = self.reply(envelope)
        if asyncio.iscoroutine(result):
            result = await result
        return result

    def named(self, method: str) -> list[Any]:
        return [e for e in self.envelopes if e.method == method]


async def _alice(tmp_path, agent: FakeAgent | None):
    instance = Instance(tmp_path, HostSettings(enabled=True, port=free_port(), operator_name="Alice"))
    if agent is not None:
        instance.client.dispatcher = MandateDispatcher(instance.client, agent)
    await instance.start()
    workspace = (await instance.channel.ok(p.WORKSPACE_CREATE, {"name": "launch", "title": "Launch plan"}))["workspace"]
    return instance, workspace["id"]


def _agent_messages(instance) -> list[dict[str, Any]]:
    return [e["message"] for e in instance.channel.named(p.EV_CHAT_MESSAGE) if e["message"]["author_kind"] == "agent"]


async def test_a_chat_task_runs_in_the_workspace_session_and_answers_in_the_chat(tmp_path):
    agent = FakeAgent(lambda env: _Response(True, {"content": {"output": "Added a Risks section."}}))
    instance, workspace_id = await _alice(tmp_path, agent)
    try:
        await instance.channel.ok(p.CHAT_POST, {"workspace_id": workspace_id, "body": "@jiuwen add a Risks section", "mentions": AGENT})
        await eventually(lambda: bool(_agent_messages(instance)), timeout=10)
        assert _agent_messages(instance)[0]["body"] == "Added a Risks section."

        (turn,) = agent.named("chat.send")
        assert (turn.channel, turn.session_id) == (CHANNEL, "sess-new")
        assert turn.channel_context["blackboard"]["workspace_id"] == workspace_id and turn.channel_context["blackboard"]["origin"] == "workspace_chat"
        assert "<request-" in turn.params["query"] and "add a Risks section" in turn.params["query"]
        assert turn.params["supports_user_interaction"] is False
        # The session is the workspace's default one now, attached so the agent has the tools.
        assert instance.client.sessions.default_for(instance.client.registry.default_id(), workspace_id) == "sess-new"
        assert [a.workspace_id for a in instance.client.sessions.for_session("sess-new")] == [workspace_id]
        # A second task reuses the session.
        await instance.channel.ok(p.CHAT_POST, {"workspace_id": workspace_id, "body": "@jiuwen again", "mentions": AGENT})
        await eventually(lambda: len(_agent_messages(instance)) == 2, timeout=10)
        assert len(agent.named("session.create")) == 1
        # Run events stay with the dispatcher.
        assert not instance.channel.named(p.EV_MANDATE_RUN)
    finally:
        await instance.stop()


async def test_a_question_leaves_the_task_waiting_until_the_answer(tmp_path):
    instance_box: dict[str, Any] = {}

    async def ask_then_answer(envelope):
        if "The answer" in envelope.params["query"]:
            return _Response(True, {"content": {"output": "Used option B."}})
        # What the agent's blackboard_ask does: the question, from inside the turn.
        client = instance_box["instance"].client
        await client.call(None, p.DECISION_CREATE, {
            "mandate_id": envelope.channel_context["blackboard"]["mandate_id"],
            "question": "Which risks?",
            "options": [{"label": "A"}, {"label": "B"}],
        })
        return _Response(True, {"content": {"output": "I asked which risks to cover."}})

    agent = FakeAgent(ask_then_answer)
    instance, workspace_id = await _alice(tmp_path, agent)
    instance_box["instance"] = instance
    try:
        await instance.channel.ok(p.CHAT_POST, {"workspace_id": workspace_id, "body": "@jiuwen add risks", "mentions": AGENT})

        async def waiting() -> bool:
            listed = (await instance.channel.ok(p.MANDATE_LIST, {"workspace_id": workspace_id}))["mandates"]
            return listed[0]["status"] == "waiting_for_answer"

        for _ in range(200):
            if await waiting():
                break
            await asyncio.sleep(0.05)
        assert await waiting()
        (decision,) = (await instance.channel.ok(p.DECISION_LIST, {"workspace_id": workspace_id}))["decisions"]
        await instance.channel.ok(p.DECISION_ANSWER, {"decision_id": decision["id"], "option": 1})
        await eventually(lambda: any(m["body"] == "Used option B." for m in _agent_messages(instance)), timeout=10)
        second = agent.named("chat.send")[1]
        assert second.session_id == agent.named("chat.send")[0].session_id and "<answer-" in second.params["query"]
    finally:
        await instance.stop()


async def test_stopping_a_task_interrupts_its_turn(tmp_path):
    async def slow(envelope):
        await agent.release.wait()
        return _Response(False, {"error": "interrupted"})

    agent = FakeAgent(slow)
    instance, workspace_id = await _alice(tmp_path, agent)
    try:
        await instance.channel.ok(p.CHAT_POST, {"workspace_id": workspace_id, "body": "@jiuwen long job", "mentions": AGENT})
        await eventually(lambda: bool(agent.named("chat.send")), timeout=10)
        (mandate,) = (await instance.channel.ok(p.MANDATE_LIST, {"workspace_id": workspace_id}))["mandates"]
        await instance.channel.ok(p.MANDATE_CANCEL, {"mandate_id": mandate["id"]})
        await eventually(lambda: bool(agent.named("chat.interrupt")), timeout=10)
        (interrupt,) = agent.named("chat.interrupt")
        assert interrupt.session_id == agent.named("chat.send")[0].session_id
        await asyncio.sleep(0.2)
        assert not _agent_messages(instance)
    finally:
        await instance.stop()


async def test_tasks_offered_while_away_run_when_the_dispatcher_asks(tmp_path):
    instance, workspace_id = await _alice(tmp_path, None)
    try:
        await instance.channel.ok(p.CHAT_POST, {"workspace_id": workspace_id, "body": "@jiuwen summarize", "mentions": AGENT})
        agent = FakeAgent(lambda env: _Response(True, {"content": {"output": "Summary."}}))
        instance.client.dispatcher = MandateDispatcher(instance.client, agent)
        await instance.client.dispatcher.resume(instance.client.registry.default_id())
        await eventually(lambda: any(m["body"] == "Summary." for m in _agent_messages(instance)), timeout=10)
    finally:
        await instance.stop()
