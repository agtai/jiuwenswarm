"""Native/Web commands reach the same real SDK pending Agent and original work."""
import asyncio
from copy import deepcopy
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
import pytest_asyncio

from jiuwenswarm.common.schema.agent import AgentRequest
from jiuwenswarm.common.schema.live_voice_contract_v2 import Assurance, ScopeRef
from jiuwenswarm.common.schema.message import ReqMethod
from jiuwenswarm.server.live_voice.native_business_router import NativeBusinessRouter
from jiuwenswarm.server.live_voice.native_business_tools import native_business_proposal_from_function_call
from jiuwenswarm.server.live_voice.native_interaction_contract import NativeInteractionBinding
from jiuwenswarm.server.runtime.agent_interrupt_requests import dispatch_agent_input_request
from tests.unit_tests.agentserver.test_shared_agent_interrupt_execution import actual_execution  # noqa: F401


@pytest_asyncio.fixture
async def public(actual_execution, monkeypatch, tmp_path):  # noqa: F811
    run = actual_execution
    manager = run.service.manager
    manager.find_agent_exact = Mock(return_value=run.facade)
    manager.executions = run.service
    metadata = {'session_id': 'session', 'channel_id': 'web', 'user_id': 'alice',
                'project_dir': str(tmp_path), 'project_id': 'project', 'work_mode': 'code', 'mode': 'code.normal'}
    def read(*args, **kwargs):
        return deepcopy(metadata)
    monkeypatch.setattr('jiuwenswarm.server.runtime.session.session_metadata.get_session_metadata', read)
    scope = ScopeRef('alice', 'project', 'session', Assurance.AUTHENTICATED)
    context = SimpleNamespace(file_path=str(tmp_path), require_usable=Mock(return_value=None))
    current = SimpleNamespace(context=context)
    registry = SimpleNamespace(_agent_manager=manager, _stopped=False,
        _p3_composition=SimpleNamespace(_accepting=True, _clock=lambda: 'now'))
    router = NativeBusinessRouter(registry)
    router._require_current_context_route = Mock(return_value=None)
    router._require_context_authority = AsyncMock(return_value=current)
    router._require_work_authority = AsyncMock(return_value=current)
    binding = NativeInteractionBinding(scope, 'interaction', 'activation', 1, 'correlation')
    route = SimpleNamespace(binding=binding, native_p3_authority=SimpleNamespace(
        context=context, principal=SimpleNamespace(require_usable=Mock(return_value=None))))
    connection_guard = Mock(return_value=None)

    async def native(question=None, *, call='native-reply'):
        params = {'request_text': 'I approve this exact pending question', 'context_id': 'a' * 64}
        if question is not None:
            params.update(target_id=question['source_binding_id'], source_task_id=question['source_task_id'],
                pending_token=question['pending_token'], input_id=question['input_id'],
                answers=[{'selected_options': ['approve']}])
        proposal = native_business_proposal_from_function_call(
            name='jiuwen_agent_pending' if question is None else 'jiuwen_agent_reply', arguments=json.dumps(params),
            binding=binding, turn_id='turn', response_generation=1,
            provider_event_id='event', provider_call_id=call, provider_item_id='item')
        return await router._agent(route, proposal)

    async def web(question=None, *, rpc='web-reply', user_id='alice'):
        params = {'action': 'list' if question is None else 'reply', 'session_id': 'session'}
        if question is not None:
            params.update({key: question[key] for key in ('source_binding_id', 'source_task_id', 'pending_token', 'input_id')})
            params['answers'] = [{'selected_options': ['approve']}]
        return await dispatch_agent_input_request(manager, AgentRequest(request_id=rpc, channel_id='web',
            session_id='session', user_id=user_id, req_method=ReqMethod.COMMAND_AGENT_INPUT, params=params),
            before_effect=connection_guard)

    return SimpleNamespace(**locals())


@pytest.mark.asyncio
@pytest.mark.parametrize('origin', ['native', 'web'])
async def test_public_reply_claims_original_sdk_once_and_shares_observation(public, origin):
    p, run = public, public.run
    entry = run.start(['A'])
    question = await run.next_question()
    native_list = await p.native()
    web_list = await p.web()
    assert web_list.ok and web_list.payload == native_list
    observed = native_list['pending'][0]
    assert observed['pending_token'] == question['pending_token']
    assert observed['question']['request_id'] == question['request_id']
    if origin == 'native':
        receipt = await p.native(question)
    else:
        response = await p.web(question)
        assert response.ok
        receipt = response.payload
    assert receipt['accepted'] and receipt['pending_token'] == question['pending_token']
    await asyncio.wait_for(asyncio.shield(entry.task), 10)
    again = await p.native(question) if origin == 'native' else (await p.web(question)).payload
    assert again == receipt
    assert run.effects == [('A', 'original-owner')]
    assert run.provider == [('original-model', 'original-owner')] * 2
    assert len(run.facade_calls) == 1
    assert (await p.native())['pending'] == []
    assert (await p.web()).payload['pending'] == []
    final = next(event for event in run.events if event.get('event_type') == 'chat.final')
    assert final['source_request_id'] == 'original'
    assert final['source_binding_id'] == question['source_binding_id']
    assert final['source_task_id'] != question['source_task_id']


@pytest.mark.asyncio
@pytest.mark.parametrize('origin', ['native', 'web'])
async def test_public_lost_receipt_is_unknown_and_never_resends_actual_claim(public, monkeypatch, origin):
    p, run = public, public.run
    entry = run.start(['A'])
    question = await run.next_question()
    send = run.sdk.send_input
    calls = []
    async def lose_receipt(request):
        calls.append(request)
        assert (await send(request))['accepted']
        raise ConnectionError('Receipt lost after actual SDK admission')
    monkeypatch.setattr(run.sdk, 'send_input', lose_receipt)
    for _ in range(2):
        if origin == 'native':
            receipt = await p.native(question)
        else:
            response = await p.web(question)
            assert response.ok
            receipt = response.payload
        assert receipt['status'] == 'unknown' and receipt['observation_required']
        assert 'accepted' not in receipt
        assert receipt['pending_token'] == question['pending_token']
    await asyncio.wait_for(asyncio.shield(entry.task), 10)
    assert len(calls) == 1 and run.effects == [('A', 'original-owner')]


@pytest.mark.asyncio
async def test_web_scope_change_during_sdk_prepare_cannot_claim_original_pending(public, monkeypatch):
    p, run = public, public.run
    entry = run.start(['A'])
    question = await run.next_question()
    entered, release = asyncio.Event(), asyncio.Event()
    prepare = run.react._init_context
    async def delayed(session):
        context = await prepare(session)
        entered.set()
        await release.wait()
        return context
    monkeypatch.setattr(run.react, '_init_context', delayed)
    reply = asyncio.create_task(p.web(question))
    await asyncio.wait_for(entered.wait(), 10)
    p.metadata['user_id'] = 'bob'
    release.set()
    response = await asyncio.wait_for(reply, 10)
    assert not response.ok and response.payload['reason'] == 'AGENT_INPUT_SESSION_MISMATCH'
    assert run.effects == [] and len(run.provider) == 1 and not entry.task.done()
    assert run.sdk.peek_pending_input()['pending_token'] == question['pending_token']
    p.metadata['user_id'] = 'alice'
    assert (await p.web(question)).payload['accepted']
    await asyncio.wait_for(asyncio.shield(entry.task), 10)
    assert run.effects == [('A', 'original-owner')]


@pytest.mark.asyncio
async def test_old_cross_entry_reply_cannot_answer_new_pending_with_same_provider_id(public):
    p, run = public, public.run
    entry = run.start(['A', 'B'])
    first = await run.next_question()
    assert (await p.native(first))['accepted']
    second = await run.next_question()
    assert first['input_id'] == second['input_id']
    assert first['pending_token'] != second['pending_token']
    rejected = await p.web(first, rpc='old-question-via-web')
    assert not rejected.ok and not rejected.payload['accepted']
    assert run.effects == [('A', 'original-owner')]
    assert run.sdk.peek_pending_input()['pending_token'] == second['pending_token']
    assert (await p.web(second, rpc='second-question')).ok
    await asyncio.wait_for(asyncio.shield(entry.task), 10)
    assert run.effects == [('A', 'original-owner'), ('B', 'original-owner')]
    assert len(run.facade_calls) == 1


@pytest.mark.asyncio
async def test_public_wrong_stored_project_and_web_user_leave_actual_pending_untouched(public):
    p, run = public, public.run
    entry = run.start(['A'])
    question = await run.next_question()
    p.metadata['project_id'] = 'other-project'
    with pytest.raises(ValueError, match='EXECUTION_CONTEXT_SCOPE_MISMATCH'):
        await p.native(question)
    denied = await p.web(question, user_id='mallory')
    assert not denied.ok and denied.payload['reason'] == 'AGENT_INPUT_SESSION_MISMATCH'
    assert run.effects == [] and len(run.provider) == 1
    assert run.sdk.peek_pending_input()['pending_token'] == question['pending_token']
    p.metadata['project_id'] = 'project'
    assert (await p.web(question)).ok
    await asyncio.wait_for(asyncio.shield(entry.task), 10)
    assert run.effects == [('A', 'original-owner')]
