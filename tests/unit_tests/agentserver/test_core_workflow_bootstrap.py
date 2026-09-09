"""Trusted startup assembly preserves original SDK registration and run owners."""
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest

from openjiuwen.core.runner import Runner
from openjiuwen.core.runner.resources_manager.base import Ok
from openjiuwen.core.workflow import Workflow, WorkflowCard
from jiuwenswarm.server.runtime.core_workflow_capabilities import CoreWorkflowCapabilities, CoreWorkflowError, CoreWorkflowScope

SCOPE = CoreWorkflowScope('web', 'bootstrap-session', 'bootstrap-project', 'agent')
SCHEMA = {'type': 'object', 'properties': {'text': {'type': 'string'}},
          'required': ['text'], 'additionalProperties': False}


@pytest.fixture
def resource():
    card = WorkflowCard(id='bootstrap-' + uuid4().hex, name='Bootstrap SDK fixture', version='1',
                        input_params=deepcopy(SCHEMA))
    workflow = Workflow(card=card.model_copy(deep=True))
    provider = Mock(return_value=workflow)
    assert isinstance(Runner.resource_mgr.add_workflow(card=card, workflow=provider), Ok)
    try:
        yield SimpleNamespace(card=card, workflow=workflow, provider=provider)
    finally:
        Runner.resource_mgr.remove_workflow(card.id)


def spec(card, capability_id='registered'):
    return dict(capability_id=capability_id, card=card, required_permissions=('task.execute',),
                continuation_schemas={'ask': {'type': 'string', 'minLength': 1}})


def test_batch_validation_and_collision_leave_original_directory_untouched(resource):
    directory = CoreWorkflowCapabilities()
    invalid = {**spec(resource.card, 'bad'), 'required_permissions': ['not-a-tuple']}
    with pytest.raises(CoreWorkflowError):
        directory.register_many(scope=SCOPE, definitions=(spec(resource.card), invalid))
    assert directory.list(SCOPE) == ()
    first = directory.register_many(scope=SCOPE, definitions=(spec(resource.card),))[0]
    conflict = {**spec(resource.card), 'required_permissions': ('project.write',)}
    with pytest.raises(CoreWorkflowError):
        directory.register_many(scope=SCOPE, definitions=(spec(resource.card, 'new'), conflict))
    assert directory.list(SCOPE) == (first,)
    assert directory.register_many(scope=SCOPE, definitions=(spec(resource.card),))[0] is first
    resource.provider.assert_not_called()


def test_bulk_binding_keeps_existing_register_collision_contract(resource):
    directory = CoreWorkflowCapabilities()
    first = directory.register(scope=SCOPE, **spec(resource.card))
    assert directory.register_many(scope=SCOPE, definitions=(spec(resource.card),))[0] is first
    with pytest.raises(CoreWorkflowError, match='already_registered'):
        directory.register(scope=SCOPE, **spec(resource.card))
    assert directory.list(replace(SCOPE, project_id='other')) == ()


def test_batch_capacity_rejects_without_eviction_and_hook_install_is_one_shot(resource):
    directory = CoreWorkflowCapabilities()
    definitions = tuple(spec(resource.card, f'cap-{number}') for number in range(128))
    original = directory.register_many(scope=SCOPE, definitions=definitions)
    with pytest.raises(CoreWorkflowError, match='registration_capacity'):
        directory.register_many(scope=replace(SCOPE, session_id='new-session'),
                                definitions=(spec(resource.card),))
    assert directory.list(SCOPE) == original
    assert directory.list(replace(SCOPE, session_id='new-session')) == ()
    assert directory.register_many(scope=SCOPE, definitions=definitions)[0] is original[0]
    hook = Mock()
    directory.bind_resolution_guard(hook)
    directory.bind_resolution_guard(hook)
    with pytest.raises(CoreWorkflowError, match='resolution_guard_already_bound'):
        directory.bind_resolution_guard(Mock())
    hook.assert_not_called()
    resource.provider.assert_not_called()


@pytest.mark.parametrize('invalid', ['duplicate', 'unknown', 'list', 'async_selection', 'false_grant', 'async_grant'])
def test_invalid_trusted_hooks_fail_closed_without_metadata_or_provider_effects(resource, invalid):
    from jiuwenswarm.server.runtime.core_workflow_bootstrap import (
        CoreWorkflowBootstrap, CoreWorkflowDefinition, install_core_workflow_bootstrap,
    )
    async def asynchronous(**_):
        return None
    async def async_selection(_):
        return ('registered',)
    selections = {'duplicate': lambda _: ('registered', 'registered'),
                  'unknown': lambda _: ('unknown',), 'list': lambda _: ['registered'],
                  'async_selection': async_selection}
    bootstrap = CoreWorkflowBootstrap(definitions=(CoreWorkflowDefinition(
        registered_provider=resource.provider, **spec(resource.card)),),
        select=selections.get(invalid, lambda _: ('registered',)),
        authorize_web=asynchronous if invalid == 'async_grant' else
        (lambda **_: False) if invalid == 'false_grant' else (lambda **_: None))
    manager = SimpleNamespace(core_workflow_capabilities=CoreWorkflowCapabilities())
    host = install_core_workflow_bootstrap(manager, bootstrap)
    guard = host.web_guard(connection=object(), request_user_id='user', scope=SCOPE, operation='list')
    with pytest.raises(CoreWorkflowError):
        host.bind_scope(SCOPE, operation='list', before_read=lambda: guard(None))
    assert manager.core_workflow_capabilities.list(SCOPE) == ()
    resource.provider.assert_not_called()

@pytest.fixture
def installed(resource):
    from jiuwenswarm.server.runtime.core_workflow_bootstrap import (
        CoreWorkflowBootstrap, CoreWorkflowDefinition, install_core_workflow_bootstrap,
    )
    selected = [True]
    authorized = [True]
    web_calls = []
    def authorize_web(**kwargs):
        web_calls.append(kwargs)
        if not authorized[0]:
            raise PermissionError('Web grant revoked')
    definition = CoreWorkflowDefinition(registered_provider=resource.provider, **spec(resource.card))
    bootstrap = CoreWorkflowBootstrap(definitions=(definition,),
        select=lambda scope: ('registered',) if selected[0] and scope == SCOPE else (),
        authorize_web=authorize_web)
    manager = SimpleNamespace(core_workflow_capabilities=CoreWorkflowCapabilities())
    host = install_core_workflow_bootstrap(manager, bootstrap)
    return SimpleNamespace(**locals())


def test_real_registration_is_read_only_and_definition_snapshots_are_immutable(installed):
    i = installed
    from jiuwenswarm.server.runtime.core_workflow_bootstrap import install_core_workflow_bootstrap
    assert install_core_workflow_bootstrap(i.manager, i.bootstrap) is i.host
    assert install_core_workflow_bootstrap(i.manager, None) is i.host
    assert i.host.bind_scope(replace(SCOPE, session_id='other'), operation='list', before_read=lambda: None) == ()
    cap = i.host.bind_scope(SCOPE, operation='list', before_read=lambda: None)[0]
    assert i.host.bind_scope(SCOPE, operation='list', before_read=lambda: None)[0] is cap
    i.definition.card.input_params['type'] = 'null'
    i.definition.continuation_schemas['ask']['type'] = 'integer'
    assert cap.input_schema == SCHEMA and i.definition.card.input_params == SCHEMA
    assert cap.continuation_schemas['ask']['type'] == 'string'
    i.resource.provider.assert_not_called()


def test_failed_install_or_different_bootstrap_never_replaces_registration(installed):
    from jiuwenswarm.server.runtime.core_workflow_bootstrap import CoreWorkflowBootstrap, install_core_workflow_bootstrap
    i = installed
    other = CoreWorkflowBootstrap(definitions=i.bootstrap.definitions, select=i.bootstrap.select,
                                  authorize_web=i.bootstrap.authorize_web)
    with pytest.raises(CoreWorkflowError, match='already_installed'):
        install_core_workflow_bootstrap(i.manager, other)
    assert i.manager.core_workflow_host is i.host
    fresh = SimpleNamespace(core_workflow_capabilities=CoreWorkflowCapabilities())
    i.resource.card.version = 'changed'
    with pytest.raises(CoreWorkflowError, match='sdk_registration_changed'):
        install_core_workflow_bootstrap(fresh, other)
    assert not hasattr(fresh, 'core_workflow_host') and fresh.core_workflow_capabilities.list(SCOPE) == ()
    assert Runner.resource_mgr._resource_registry.workflow()._providers.get(i.resource.card.id) is i.resource.provider
    i.resource.provider.assert_not_called()


def test_missing_second_registered_provider_does_not_partially_bind(resource):
    from jiuwenswarm.server.runtime.core_workflow_bootstrap import (
        CoreWorkflowBootstrap, CoreWorkflowDefinition, install_core_workflow_bootstrap,
    )
    second = resource.card.model_copy(deep=True)
    second.id = 'bootstrap-' + uuid4().hex
    second_provider = Mock(return_value=Workflow(card=second))
    assert isinstance(Runner.resource_mgr.add_workflow(card=second, workflow=second_provider), Ok)
    try:
        bootstrap = CoreWorkflowBootstrap(definitions=(
            CoreWorkflowDefinition(registered_provider=resource.provider, **spec(resource.card)),
            CoreWorkflowDefinition(registered_provider=second_provider, **spec(second, 'second'))),
            select=lambda _: ('registered', 'second'), authorize_web=lambda **_: None)
        manager = SimpleNamespace(core_workflow_capabilities=CoreWorkflowCapabilities())
        host = install_core_workflow_bootstrap(manager, bootstrap)
        Runner.resource_mgr.remove_workflow(second.id)
        with pytest.raises(CoreWorkflowError, match='sdk_registration_changed'):
            host.bind_scope(SCOPE, operation='list', before_read=lambda: None)
        assert manager.core_workflow_capabilities.list(SCOPE) == ()
        resource.provider.assert_not_called()
        second_provider.assert_not_called()
    finally:
        Runner.resource_mgr.remove_workflow(second.id)


@pytest.mark.parametrize('failure', ['read_denied', 'revoked', 'replaced', 'scope'])
def test_failed_current_admission_has_no_provider_or_metadata_effects(installed, failure):
    i = installed
    scope = SCOPE
    def before():
        return None
    if failure == 'read_denied':
        before = Mock(side_effect=PermissionError('scope denied'))
    elif failure == 'revoked':
        i.host.revoke()
    elif failure == 'replaced':
        i.manager.core_workflow_host = object()
    else:
        scope = object()
    with pytest.raises((CoreWorkflowError, PermissionError)):
        i.host.bind_scope(scope, operation='list', before_read=before)
    assert i.manager.core_workflow_capabilities.list(SCOPE) == ()
    i.resource.provider.assert_not_called()


def test_web_caller_and_permission_callback_are_current_not_wire_authority(installed):
    i = installed
    connection = object()
    guard = i.host.web_guard(connection=connection, request_user_id='authenticated-user',
                             scope=SCOPE, operation='start')
    cap = i.host.bind_scope(SCOPE, operation='start', before_read=lambda: guard(None))[0]
    guard(cap)
    assert i.web_calls[-1] == dict(connection=connection, request_user_id='authenticated-user',
                                  scope=SCOPE, operation='start', capability=cap)
    i.authorized[0] = False
    with pytest.raises(PermissionError, match='Web grant revoked'):
        guard(cap)
    i.authorized[0] = True
    i.selected[0] = False
    with pytest.raises(CoreWorkflowError, match='capability_revoked'):
        guard(cap)
    i.resource.provider.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['selection', 'web_grant', 'installation', 'provider', 'card'])
async def test_actual_async_factory_rechecks_after_wait_before_issuing_binding(resource, change):
    import asyncio
    from jiuwenswarm.server.runtime.core_workflow_bootstrap import (
        CoreWorkflowBootstrap, CoreWorkflowDefinition, install_core_workflow_bootstrap,
    )
    entered, release = asyncio.Event(), asyncio.Event()
    calls = []
    async def factory():
        calls.append('factory')
        entered.set()
        await release.wait()
        return resource.workflow
    Runner.resource_mgr.remove_workflow(resource.card.id)
    assert isinstance(Runner.resource_mgr.add_workflow(card=resource.card, workflow=factory), Ok)
    selected, authorized = [True], [True]
    def authorize(**_):
        if not authorized[0]:
            raise PermissionError('revoked during provider wait')
    definition = CoreWorkflowDefinition(registered_provider=factory, **spec(resource.card))
    bootstrap = CoreWorkflowBootstrap(definitions=(definition,),
        select=lambda _: ('registered',) if selected[0] else (), authorize_web=authorize)
    manager = SimpleNamespace(core_workflow_capabilities=CoreWorkflowCapabilities())
    host = install_core_workflow_bootstrap(manager, bootstrap)
    guard = host.web_guard(connection=object(), request_user_id='user', scope=SCOPE, operation='start')
    host.bind_scope(SCOPE, operation='start', before_read=lambda: guard(None))
    capability = manager.core_workflow_capabilities.get(scope=SCOPE, capability_id='registered')
    pending = asyncio.create_task(manager.core_workflow_capabilities.resolve(scope=SCOPE,
        capability_id='registered', before_effect=lambda: guard(capability)))
    await asyncio.wait_for(entered.wait(), 2)
    replacement = Mock(side_effect=AssertionError('replacement cannot execute'))
    if change == 'selection':
        selected[0] = False
    elif change == 'web_grant':
        authorized[0] = False
    elif change == 'installation':
        manager.core_workflow_host = object()
    elif change == 'provider':
        Runner.resource_mgr.remove_workflow(resource.card.id)
        Runner.resource_mgr.add_workflow(card=resource.card, workflow=replacement)
    else:
        resource.card.version = 'changed'
    release.set()
    with pytest.raises((CoreWorkflowError, PermissionError)):
        await asyncio.wait_for(pending, 2)
    assert calls == ['factory']
    replacement.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('interactive', [False, True])
async def test_real_sdk_completion_and_strict_original_instance_continuation(installed, monkeypatch, interactive):
    from openjiuwen.core.common.constants.constant import INTERACTION
    from openjiuwen.core.session.checkpointer import CheckpointerFactory
    from openjiuwen.core.session.checkpointer.inmemory import InMemoryCheckpointer
    from openjiuwen.core.workflow import End, Start, WorkflowComponent, WorkflowResumeGuard
    i = installed
    checkpoint = InMemoryCheckpointer()
    monkeypatch.setattr(CheckpointerFactory, '_default_checkpointer', checkpoint)
    class Ask(WorkflowComponent):
        async def invoke(self, inputs, session, context):
            return {'answer': await session.interact('Bootstrap continuation fixture')}
    workflow = i.resource.workflow
    workflow.set_start_comp('start', Start(), inputs_schema={'text': '${text}'})
    if interactive:
        workflow.add_workflow_comp('ask', Ask())
        workflow.add_connection('start', 'ask')
        workflow.set_end_comp('end', End(), inputs_schema={'answer': '${ask.answer}'})
        workflow.add_connection('ask', 'end')
    else:
        workflow.set_end_comp('end', End(), inputs_schema={'text': '${start.text}'})
        workflow.add_connection('start', 'end')
    capability = i.host.bind_scope(SCOPE, operation='start', before_read=lambda: None)[0]
    def guard():
        return i.host.guard(SCOPE, 'start', capability)
    directory = i.manager.core_workflow_capabilities
    binding = await directory.resolve(scope=SCOPE, capability_id='registered', before_effect=guard)
    sid = 'bootstrap-private-' + uuid4().hex
    result = await directory.invoke(scope=SCOPE, binding=binding, sdk_session_id=sid,
                                    inputs={'text': 'actual-sdk'}, before_effect=guard)
    if interactive:
        assert result.state.value == 'INPUT_REQUIRED'
        pending = [chunk.payload for chunk in result.result if chunk.type == INTERACTION]
        Runner.resource_mgr.remove_workflow(workflow.card.id)
        replacement = Mock(side_effect=AssertionError('old run must not resolve a replacement'))
        Runner.resource_mgr.add_workflow(card=workflow.card, workflow=replacement)
        assert i.host.bind_scope(SCOPE, operation='resume', before_read=lambda: None)[0] is capability
        with pytest.raises(CoreWorkflowError, match='sdk_registration_changed'):
            await directory.resolve(scope=SCOPE, capability_id='registered', before_effect=guard)
        result = await directory.continue_workflow(scope=SCOPE, binding=binding, sdk_session_id=sid,
            pending=pending, answers={'ask': 'original-instance'}, before_effect=guard,
            resume_guard=WorkflowResumeGuard(before_effect=guard))
        replacement.assert_not_called()
        assert result.result == {'output': {'answer': 'original-instance'}}
    else:
        assert result.result == {'output': {'text': 'actual-sdk'}}
    assert result.state.value == 'COMPLETED' and sid not in checkpoint._workflow_stores
    i.resource.provider.assert_called_once()
