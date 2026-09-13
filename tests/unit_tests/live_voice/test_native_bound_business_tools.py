"""One complete operation intent keeps exact v1 authorization and send identity."""
import asyncio
import json

import pytest

from jiuwenswarm.server.live_voice.native_business_tools import (
    native_business_tools, native_business_proposal_from_function_call,
)
from jiuwenswarm.server.live_voice.native_business_contract import NativeBusinessViolation
from tests.unit_tests.live_voice import test_native_business_tools as tools_fixture
from tests.unit_tests.live_voice import test_openai_realtime_native_engine as f


def values(operation):
    fields = tools_fixture.inputs(operation)
    intent = fields.get('instruction', fields.get('adjustment', fields['request_text']))
    return {**{key: value for key, value in fields.items()
               if key not in {'context_id', 'instruction', 'adjustment'}}, 'request_text': intent}


def decode(operation, fields=None, context='a' * 64):
    return native_business_proposal_from_function_call(
        name='jiuwen_bound_' + operation.replace('.', '_'),
        arguments=json.dumps(values(operation) if fields is None else fields, ensure_ascii=False),
        server_context_id=context, **tools_fixture.binding())


@pytest.mark.parametrize('operation', tools_fixture.SCENARIOS)
def test_all_bound_operations_retain_exact_canonical_business_proposal(operation):
    flat = values(operation)
    legacy = {**tools_fixture.inputs(operation), 'request_text': flat['request_text'], 'context_id': 'a' * 64}
    for field in ('instruction', 'adjustment'):
        if field in legacy:
            legacy[field] = flat['request_text']
    assert decode(operation) == tools_fixture.decode(operation, values=legacy)
    for extra in ('context_id', 'instruction', 'adjustment', 'authorized'):
        with pytest.raises(NativeBusinessViolation, match='FIELDS_NOT_CLOSED'):
            decode(operation, {**flat, extra: 'injected'})
    for missing in flat:
        with pytest.raises(NativeBusinessViolation, match='FIELDS_NOT_CLOSED'):
            decode(operation, {key: value for key, value in flat.items() if key != missing})


def test_bound_catalog_advertises_only_one_intent_and_exact_targets():
    for tool in native_business_tools(bound_context=True):
        operation = tool['name'].removeprefix('jiuwen_bound_').replace('_', '.', 1)
        schema = tool['parameters']
        assert set(schema['required']) == set(schema['properties']) == set(values(operation))
        assert schema['additionalProperties'] is False
        assert schema['properties']['request_text']['maxLength'] == (
            4096 if {'instruction', 'adjustment'} & set(tools_fixture.inputs(operation)) else 16384)


@pytest.mark.parametrize('operation', ['task.create', 'task.create_successor', 'task.adjust', 'work.start', 'work.update'])
def test_single_intent_utf8_limit_and_filename_requirements_are_never_truncated(operation):
    complete = '读取深圳出差行程.md，按已确认日期保留交通预算，把海边加入第二天，保存深圳出差行程_海边版.md，原件不得改动。'
    actual = decode(operation, {**values(operation), 'request_text': complete})
    field = 'adjustment' if operation == 'task.adjust' else 'instruction'
    assert getattr(actual.business, field) == actual.request_text == complete
    boundary = '中' * 1365 + 'x'
    assert len(boundary.encode()) == 4096
    assert getattr(decode(operation, {**values(operation), 'request_text': boundary}).business, field) == boundary
    with pytest.raises(NativeBusinessViolation) as rejected:
        decode(operation, {**values(operation), 'request_text': boundary + 'x'})
    assert rejected.value.field == 'request_text'


def bound_call(event_id='bound-call', response='p1', call='bound-1'):
    return f.function_done(event_id, response, call_id=call, item_id='item-' + call,
        name='jiuwen_bound_task_create', arguments=json.dumps({
            'request_text': 'Read source.md, preserve it, write the changed copy to result.md.', 'name': 'Changed copy'}))


@pytest.mark.asyncio
async def test_bound_call_uses_sent_context_and_exact_commit_without_asr_wait():
    event = bound_call()
    engine, socket, commit = await f.admitted_business_engine(event, event)
    try:
        assert not engine._input_transcripts_by_item
        engine._replace_business_context({**f.business_context(), 'context_id': 'b' * 64}, [])
        result = await asyncio.wait_for(engine.next_event(), .2)
        assert result.delegate.business.context_id == 'a' * 64
        assert result.delegate.turn_id == commit.turn_commit.turn_id
        assert result.delegate.request_text == result.delegate.business.instruction
        assert engine.snapshot().delegate_count == 1
        assert await engine.next_event() == f.NativeEngineEvent()
        assert engine.snapshot().delegate_count == 1
        assert engine.snapshot().released_audio_count == 0
        assert not function_outputs(socket)
    finally:
        await engine.close()


def function_outputs(socket):
    return f.function_outputs(socket)


@pytest.mark.asyncio
async def test_new_turn_publishes_updated_task_context_before_binding_response():
    engine, socket, _ = await f.started_business_engine(f.speech_started('s', 'u', 0),
        f.speech_stopped('e', 'u', 500), f.input_committed('c', 'u'))
    updated = {**f.business_context(), 'context_id': 'b' * 64,
               'tasks': [{'task_id': 'new-task', 'revision': 1}]}
    try:
        engine._replace_business_context(updated, [])
        _, _, commit = await f.accept_basic_turn(engine)
        await engine.acknowledge_business_turn(commit.turn_commit.turn_id)
        create_index = next(i for i, e in enumerate(socket.sent) if e['type'] == 'response.create')
        published = socket.sent[create_index - 1]
        assert published['type'] == 'conversation.item.create'
        assert json.loads(published['item']['content'][0]['text']) == {'native_business_context': updated}
        assert engine._inflight_response_request.business_binding.context_id == 'b' * 64
        assert engine.snapshot().delegate_count == engine.snapshot().released_audio_count == 0
    finally:
        await engine.close()


@pytest.mark.asyncio
async def test_old_accepted_receipt_during_next_turn_send_wait_refreshes_without_replay():
    engine, socket, _ = await f.admitted_business_engine(
        f.business_function('f', 'p1', 'call1'), f.response_done('d', 'p1'))
    calls = []
    async def refresh():
        calls.append(True)
        return {'context': {**f.business_context(), 'context_id': 'b' * 64}, 'work_events': []}
    engine._business_refresh = refresh
    engine._continuation_preparation = True
    receipt = None
    try:
        await engine.next_event()
        await engine.next_event()
        await engine.stop_foreground(f.response_ref(1))
        await engine._business_send_lock.acquire()
        socket.push(f.speech_started('s2', 'u2', 600))
        socket.push(f.speech_stopped('e2', 'u2', 900))
        socket.push(f.input_committed('c2', 'u2'))
        await f.accept_basic_turn(engine)
        for _ in range(30):
            if engine._inflight_response_request is not None:
                break
            await asyncio.sleep(0)
        assert engine._inflight_response_request is not None
        receipt = asyncio.create_task(engine.send_delegate_result('call1', f.response_ref(1),
            '{"receipt":{"state":"running","work_id":"work-1"}}'))
        await asyncio.sleep(0)
        engine._business_send_lock.release()
        await asyncio.wait_for(receipt, 1)
        scheduler = engine._continuation_scheduler
        if scheduler is not None:
            await asyncio.wait_for(scheduler, 1)
        assert calls == [True]
        assert engine._inflight_response_request.business_binding.context_id == 'b' * 64
        assert len(function_outputs(socket)) == 1
        assert len([e for e in socket.sent if e['type'] == 'response.create']) == 2
        assert engine.snapshot().delegate_count == 1 and engine.snapshot().released_audio_count == 0
    finally:
        if engine._business_send_lock.locked():
            engine._business_send_lock.release()
        if receipt is not None:
            await asyncio.gather(receipt, return_exceptions=True)
        await engine.close()


@pytest.mark.asyncio
async def test_delayed_full_receipt_cannot_roll_back_already_published_newer_facts():
    engine, socket, _ = await f.admitted_business_engine(
        f.business_function('f', 'p1', 'call1'), f.response_done('d', 'p1'))
    newer = {**f.business_context(), 'context_id': 'b' * 64}
    try:
        await engine.next_event()
        await engine.next_event()
        engine._replace_business_context(newer, [])
        await engine._send_business_facts({'native_business_context': newer})
        await engine.send_delegate_result('call1', f.response_ref(1), json.dumps({
            'contract_version': 'live-voice.native-business.v1', 'operation': 'context.get',
            'status': 'observed', 'context': f.business_context()}))
        assert engine._business_context == newer
        assert engine._inflight_response_request.business_binding.context_id == 'b' * 64
        assert len(function_outputs(socket)) == 1
        assert engine.snapshot().released_audio_count == 0
    finally:
        await engine.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('retire', [False, True])
async def test_context_publication_in_flight_rechecks_newer_facts_and_stop(retire):
    engine, socket, _ = await f.started_business_engine(f.speech_started('s', 'u', 0),
        f.speech_stopped('e', 'u', 500), f.input_committed('c', 'u'))
    engine._continuation_preparation = True
    try:
        engine._replace_business_context({**f.business_context(), 'context_id': 'b' * 64}, [])
        socket.block_send_at = socket.send_calls + 1
        await f.accept_basic_turn(engine)
        await asyncio.wait_for(socket.send_entered.wait(), .5)
        if retire:
            socket.push(f.speech_started('s2', 'u2', 600))
            await engine.next_event()
        else:
            engine._replace_business_context({**f.business_context(), 'context_id': 'c' * 64}, [])
        socket.release_send.set()
        scheduler = engine._continuation_scheduler
        if scheduler is not None:
            await asyncio.wait_for(scheduler, .5)
        created = [e for e in socket.sent if e['type'] == 'response.create']
        assert len(created) == (0 if retire else 1)
        if not retire:
            assert engine._inflight_response_request.business_binding.context_id == 'c' * 64
        assert engine.snapshot().delegate_count == engine.snapshot().released_audio_count == 0
    finally:
        socket.release_send.set()
        await engine.close()


@pytest.mark.asyncio
async def test_bound_call_after_stop_has_zero_delegate_or_audio_effect():
    engine, socket, _ = await f.admitted_business_engine()
    try:
        await engine.stop_foreground(f.response_ref(1))
        before = engine.snapshot()
        socket.push(bound_call())
        assert await engine.next_event() == f.NativeEngineEvent()
        assert engine.snapshot().delegate_count == before.delegate_count == 0
        assert engine.snapshot().released_audio_count == 0
        assert not engine._delegates and not function_outputs(socket)
    finally:
        await engine.close()


@pytest.mark.asyncio
async def test_response_binding_precedes_send_receipt_and_context_publish_cannot_interleave():
    engine, socket, _ = await f.started_business_engine(f.speech_started('s', 'u', 0),
        f.speech_stopped('e', 'u', 500), f.input_committed('c', 'u'))
    engine._continuation_preparation = True
    try:
        await engine.next_event()
        await engine.next_event()
        socket.block_send_at = socket.send_calls + 1
        commit = await engine.next_event()
        await asyncio.wait_for(socket.send_entered.wait(), .3)
        inflight = engine._inflight_response_request
        assert inflight.business_binding.commit == commit.turn_commit
        publication = asyncio.create_task(engine._send_business_facts({
            'native_business_context': {**f.business_context(), 'context_id': 'b' * 64}}))
        socket.push(f.response_created('r', 'p1'))
        assert (await asyncio.wait_for(engine.next_event(), .3)).action.operation == 'SPEAK'
        assert engine._responses['p1'].business_binding is inflight.business_binding
        assert engine._responses['p1'].business_binding.context_id == 'a' * 64
        assert not publication.done()
        socket.release_send.set()
        await asyncio.wait_for(publication, .3)
        assert engine._sent_business_context_id == 'b' * 64
        assert engine._responses['p1'].business_binding.context_id == 'a' * 64
        assert engine.snapshot().delegate_count == engine.snapshot().released_audio_count == 0
    finally:
        socket.release_send.set()
        await engine.close()


@pytest.mark.asyncio
async def test_stop_while_waiting_for_context_send_does_not_send_retired_response():
    engine, socket, _ = await f.started_business_engine(f.speech_started('s', 'u', 0),
        f.speech_stopped('e', 'u', 500), f.input_committed('c', 'u'))
    engine._continuation_preparation = True
    await engine._business_send_lock.acquire()
    try:
        await engine.next_event()
        await engine.next_event()
        await engine.next_event()
        for _ in range(20):
            if engine._inflight_response_request is not None:
                break
            await asyncio.sleep(0)
        request = engine._inflight_response_request
        assert request is not None
        socket.push(f.speech_started('new-speech', 'u2', 600))
        assert (await engine.next_event()).action.operation == 'LISTEN'
        assert request.retired
        engine._business_send_lock.release()
        await engine._continuation_scheduler
        assert not any(item['type'] == 'response.create' for item in socket.sent)
        assert engine._inflight_response_request is None
        assert not engine._responses and not engine._delegates
        assert engine.snapshot().released_audio_count == 0
    finally:
        if engine._business_send_lock.locked():
            engine._business_send_lock.release()
        await engine.close()


@pytest.mark.asyncio
async def test_failed_context_send_does_not_advance_successfully_published_identity():
    engine, socket, _ = await f.started_business_engine()
    try:
        socket.fail_send_at = socket.send_calls + 1
        with pytest.raises(Exception):
            await engine._send_business_facts({'native_business_context': {
                **f.business_context(), 'context_id': 'b' * 64}})
        assert engine._sent_business_context_id == 'a' * 64
        assert not engine._responses and not engine._delegates
        assert engine.snapshot().released_audio_count == 0
    finally:
        await engine.close()


@pytest.mark.asyncio
async def test_nonprojected_context_result_binds_successor_to_facts_actually_sent():
    engine, socket, _ = await f.admitted_business_engine(f.business_function('f', 'p1', 'call1'))
    try:
        await engine.next_event()
        socket.push(f.response_done('d', 'p1'))
        await engine.next_event()
        await engine.send_delegate_result('call1', f.response_ref(1), json.dumps({
            'contract_version': 'live-voice.native-business.v1', 'operation': 'context.get',
            'status': 'observed', 'context': {**f.business_context(), 'context_id': 'b' * 64}}))
        assert engine._inflight_response_request.business_binding.context_id == 'b' * 64
        socket.push(f.response_created('r2', 'p2'))
        await engine.next_event()
        await engine.admit_response('p2', f.response_ref(2))
        socket.push(bound_call(response='p2'))
        assert (await engine.next_event()).delegate.business.context_id == 'b' * 64
    finally:
        await engine.close()


@pytest.mark.asyncio
async def test_bound_create_uses_real_router_journal_task_and_preserves_rejection_effect_fence(tmp_path, monkeypatch):
    from dataclasses import replace
    from tests.unit_tests.live_voice.test_native_business_registry import make_registry, context
    from tests.unit_tests.live_voice.test_product_composition_registry import _native_delegate_proposal, _native_propose_params

    env = await make_registry(tmp_path, monkeypatch)
    store = env.harness.composition._core.store
    intent = '读取深圳出差行程.md，加入海边并保留预算，保存深圳出差行程_海边版.md，不得修改原文件。'
    try:
        facts = await context(env)
        old = _native_delegate_proposal(env.binding, env.source, request_text=intent)
        initial = old.delegate
        base = {key: getattr(initial, key) for key in initial.__dataclass_fields__ if key != 'request_text'}
        proposal = native_business_proposal_from_function_call(name='jiuwen_bound_task_create',
            arguments=json.dumps({'request_text': intent, 'name': '海边版本'}, ensure_ascii=False),
            server_context_id=facts['context_id'], **base)
        carrier = replace(old, delegate=proposal)
        params = _native_propose_params(env.binding, env.capability, carrier)
        result = await env.registry.handle_native_propose(params=params, request_id='bound-create', session_id='session-1')
        assert result.ok, result.payload
        receipt = json.loads(result.payload['result']['canonical_text'])
        assert receipt['status'] == 'dispatched' and receipt['receipt']['state'] == 'accepted'
        actual = store.get_task(receipt['task_id'], env.binding.scope)
        assert actual.spec.instruction == intent
        before = store.counts()
        replay = await env.registry.handle_native_propose(params=params, request_id='bound-replay', session_id='session-1')
        assert replay.ok and json.loads(replay.payload['result']['canonical_text']) == receipt
        assert store.counts() == before
        invalid = replace(proposal, provider_event_id='foreign-event', provider_call_id='foreign-call',
            provider_item_id='foreign-item', business=replace(proposal.business, context_id='f' * 64))
        invalid_carrier = replace(carrier, delegate=invalid, action=replace(carrier.action,
            action_id='foreign-action', payload=(('provider_call_id', invalid.provider_call_id), ('turn_id', invalid.turn_id))))
        rejected = await env.registry.handle_native_propose(
            params=_native_propose_params(env.binding, env.capability, invalid_carrier),
            request_id='bound-stale', session_id='session-1')
        assert rejected.ok, rejected.payload
        rejection = json.loads(rejected.payload['result']['canonical_text'])
        assert rejection['status'] == 'rejected' and rejection['reason'] == 'NATIVE_BUSINESS_CONTEXT_STALE'
        assert store.counts() == before
        assert env.manager.agent.executions == []
        assert env.registry._native_business.task_origins(env.binding.scope) == (receipt['task_id'],)
    finally:
        await env.registry.stop()
        await env.harness.composition.stop()
