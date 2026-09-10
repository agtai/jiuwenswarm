"""Result input isolation and query/notification delivery share exact identities."""

import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from jiuwenswarm.server.live_voice.native_business_router import NativeBusinessRouter
from jiuwenswarm.server.live_voice.native_business_contract import NativeBusinessAction
from jiuwenswarm.server.live_voice.native_interaction_runtime import NativeInteractionRuntimeError
from jiuwenswarm.server.live_voice.native_work_journal import SqliteNativeWorkJournal
from jiuwenswarm.server.live_voice.native_work_runtime import NativeWorkRuntime
from jiuwenswarm.server.live_voice.unified_committed_input import SqliteUnifiedCommittedInputJournal
from jiuwenswarm.server.live_voice.voice_task_bridge import UnifiedCommittedInputRoute
from tests.unit_tests.live_voice import test_native_continuation_preparation as p
from tests.unit_tests.live_voice.test_native_business_runtime import business
from tests.unit_tests.live_voice.test_native_interaction_runtime import active_owner, audio, done, ack_for
from tests.unit_tests.live_voice.test_native_work_runtime import admission, terminal


@pytest.mark.asyncio
async def test_prepared_result_input_excludes_latest_question_and_other_work():
    engine, socket, fresh = await p.preparing_engine(prepare=False)
    try:
        selected = p.work_event()
        fresh["context"]["history"] = [{"role": "user", "content": "UNRELATED_QUESTION", "delivery": "user_input"}]
        fresh["context"]["works"] = [
            {"work_id": selected["work_id"], "revision": 1, "instruction": "Find original facts"},
            {"work_id": "other", "revision": 1, "instruction": "UNRELATED_WORK"},
        ]
        fresh["work_events"] = [selected]
        await engine.update_business_context(fresh["context"], fresh["work_events"])
        request = p.requests(socket)[-1]["response"]
        data = json.loads(request["input"][0]["content"][0]["text"])
        assert data == {"native_work_result": selected, "original_work_request": "Find original facts"}
        assert "UNRELATED" not in json.dumps(request)
        assert request["tool_choice"] == "none"
        # A later direct response must not inherit a cancelled notification's
        # full result from a synthetic user message in the default conversation.
        published = [event for event in socket.sent if event["type"] == "conversation.item.create"]
        assert published
        assert selected["result_text"] not in json.dumps(published)
        assert "native_work_result" not in json.dumps(published)
        # Pending generation does not become audio or claim presentation.
        assert engine.snapshot().released_audio_count == 1
    finally:
        await engine.close()


@pytest.mark.asyncio
async def test_query_ack_retires_prepared_notification_before_audio_and_cleans_output():
    engine, socket, fresh = await p.preparing_engine()
    try:
        await p.feed(engine, socket, p.output_audio_delta("a2", "p2", "audio2", 0))
        await p.complete_audio(engine, socket, transcript="Original result")
        # The foreground query's full ACK removes this event in the server's
        # next authorized observation, after notification audio was prepared.
        fresh["work_events"] = []
        await engine.acknowledge_presentation(p.response_ref(1))
        if engine._continuation_scheduler is not None:
            await engine._continuation_scheduler
        assert engine._prepared.output.discarded
        assert engine._responses["p2"].runtime_ref is None
        assert engine.snapshot().released_audio_count == 1
        truncations = [event for event in socket.sent if event["type"] == "conversation.item.truncate"]
        assert truncations[-1]["item_id"] == "audio2"
        assert truncations[-1]["audio_end_ms"] == 0
        await p.feed(engine, socket, p.provider_event("conversation.item.truncated", "cleaned",
            item_id="audio2", content_index=0, audio_end_ms=0))
        assert engine._prepared is None
        assert len(p.requests(socket)) == 2
        assert not engine._delegates
    finally:
        await engine.close()


async def result_harness(tmp_path):
    owner, runtime = await active_owner()
    router = NativeBusinessRouter(SimpleNamespace())
    unified = SqliteUnifiedCommittedInputJournal(tmp_path / "work.sqlite3")
    router._work_journal = SqliteNativeWorkJournal(unified.database_path)
    router._work_owner = NativeWorkRuntime(save=router._work_journal.save)
    source = await owner.accept_provider_response("source", "runtime-source")
    scope = owner._binding.scope
    route = SimpleNamespace(binding=owner._binding, native_runtime_owner=owner)
    async def runner(control):
        return "Verified result: 12 units; source may be incomplete."
    works = []
    for index in range(3):
        item = await router.works().start(**admission(runner, current_scope=scope,
            request=f"request-{index}", input_id=f"input-{index}"))
        works.append(await terminal(router.works(), item))
    return SimpleNamespace(owner=owner, runtime=runtime, router=router, route=route,
                           scope=scope, source=source, works=works)


async def query_receipt(h, index, *, fact=None, operation="work.get"):
    work = h.works[index]
    proposal = replace(business(h.source.response, f"query-{index}"),
        business=NativeBusinessAction(operation, "a" * 64,
            work.work_id if operation == "work.get" else None, None, None, None, None))
    _, admitted = await h.owner.admit_delegate(proposal, committed_at="2026-09-10T00:00:00Z")
    await h.owner.prepare_delegate_result(admitted, canonical_text=json.dumps({
        "operation": operation, "work": fact if fact is not None else work.to_dict(),
    }), route=UnifiedCommittedInputRoute.DIALOGUE, allow_interrupted=True)


async def successor(h):
    await h.owner.accept_provider_done(done(h.source.response, "source", transcript=None))
    return await h.router.admit_business_response(h.route,
        provider_response_id="answer", call_id="query-0", turn_id="native-turn-1")


async def close_harness(h):
    await h.owner.close()
    await h.router.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["heard", "interrupted", "silent", "failed"])
async def test_multiple_query_receipts_share_delivery_without_consuming_other_work(tmp_path, outcome):
    h = await result_harness(tmp_path)
    try:
        await query_receipt(h, 0)
        await query_receipt(h, 1)
        reply = await successor(h)
        ids = [h.router._work_event_id(work) for work in h.works]
        journal = h.router._work_journal
        assert len(h.owner.business_query_receipts("query-0", "native-turn-1")) == 2
        assert not any(journal.presented(event, h.scope) for event in ids)
        # Neither generation, silent settlement nor another response's ACK is a
        # heard result. The Registry invokes acknowledge_work after history ACK.
        h.router.acknowledge_work(h.route, h.source.response)
        if outcome != "silent":
            await h.owner.accept_audio(audio(reply.response, "answer", 0))
        await h.owner.accept_provider_done(done(reply.response, "answer",
            transcript=None if outcome == "silent" else "Both verified results, including qualifications.",
            completed=outcome != "failed"))
        assert not any(journal.presented(event, h.scope) for event in ids)
        if outcome == "heard":
            heard = await h.owner.acknowledge_audio(ack_for(h.runtime, reply.response, 0))
            assert heard is not None
            h.router.acknowledge_work(h.route, heard.response)
            h.router.acknowledge_work(h.route, heard.response)
            assert all(journal.presented(event, h.scope) for event in ids[:2])
            assert h.router.work_events(h.scope)[0]["event_id"] == ids[2]
        elif outcome == "interrupted":
            h.router.interrupt_work_presentation(h.route, reply.response)
            assert all(journal.suppressed(event, h.scope) for event in ids[:2])
            assert not any(journal.presented(event, h.scope) for event in ids)
        else:
            h.router.release_unheard_work_response(h.route, reply.response)
            assert not h.router._work_presentations
            assert not any(journal.presented(event, h.scope) for event in ids)
        assert not journal.presented(ids[2], h.scope)
        assert not journal.suppressed(ids[2], h.scope)
        assert all(work.state.value == "completed" for work in h.router.works().list(scope=h.scope))
    finally:
        await close_harness(h)


@pytest.mark.asyncio
@pytest.mark.parametrize("defect", ["revision", "state", "scope", "result", "not_query"])
async def test_only_exact_current_query_facts_bind_delivery(tmp_path, defect):
    h = await result_harness(tmp_path)
    try:
        fact = h.works[0].to_dict()
        if defect == "revision":
            fact["revision"] += 1
        elif defect == "state":
            fact["state"] = "running"
        elif defect == "scope":
            fact["scope"] = {**fact["scope"], "session_id": "other-session"}
        elif defect == "result":
            fact["result_text"] = "unrelated result"
        await query_receipt(h, 0, fact=fact, operation="work.list" if defect == "not_query" else "work.get")
        reply = await successor(h)
        assert not h.router._work_presentations
        h.router.acknowledge_work(h.route, reply.response)
        assert len(h.router.work_events(h.scope)) == 1
        assert not any(h.router._work_journal.presented(h.router._work_event_id(w), h.scope) for w in h.works)
        with pytest.raises(NativeInteractionRuntimeError):
            h.owner.business_query_receipts("foreign", "native-turn-1")
    finally:
        await close_harness(h)


@pytest.mark.asyncio
async def test_late_query_ack_does_not_consume_a_new_work_revision(tmp_path):
    h = await result_harness(tmp_path)
    try:
        await query_receipt(h, 0)
        reply = await successor(h)
        async def revised(control):
            return "New verified result"
        arguments = admission(revised, current_scope=h.scope, request="new-revision", input_id="new-input")
        arguments.pop("foreground")
        current = await h.router.works().update(**arguments, work_id=h.works[0].work_id, revision=1)
        current = await terminal(h.router.works(), current)
        await h.owner.accept_audio(audio(reply.response, "answer", 0))
        await h.owner.accept_provider_done(done(reply.response, "answer", transcript="Original result"))
        heard = await h.owner.acknowledge_audio(ack_for(h.runtime, reply.response, 0))
        h.router.acknowledge_work(h.route, heard.response)
        assert h.router._work_journal.presented(h.router._work_event_id(h.works[0]), h.scope)
        assert not h.router._work_journal.presented(h.router._work_event_id(current), h.scope)
        assert not h.router._work_journal.suppressed(h.router._work_event_id(current), h.scope)
    finally:
        await close_harness(h)


@pytest.mark.asyncio
async def test_query_admission_replay_is_idempotent_and_capacity_has_zero_response_effect(tmp_path):
    h = await result_harness(tmp_path)
    try:
        await query_receipt(h, 0)
        reply = await successor(h)
        before = h.runtime.snapshot()
        again = await h.router.admit_business_response(h.route,
            provider_response_id="answer", call_id="query-0", turn_id="native-turn-1")
        assert again == reply and h.runtime.snapshot() == before
        assert len(h.router._work_presentations) == 1
        with pytest.raises(NativeInteractionRuntimeError):
            await h.router.admit_business_response(h.route,
                provider_response_id="another-answer", call_id="query-0", turn_id="wrong-turn")
        assert h.runtime.snapshot() == before
        h.router._work_presentations.update({(h.scope, index): ("occupied",) for index in range(128)})
        with pytest.raises(NativeInteractionRuntimeError) as error:
            await h.router.admit_business_response(h.route,
                provider_response_id="overflow", call_id="query-0", turn_id="native-turn-1")
        assert error.value.reason == "NATIVE_WORK_PRESENTATION_CAPACITY"
        assert h.runtime.snapshot() == before
    finally:
        await close_harness(h)
