"""Actual startup construction installs trusted Core metadata before listening.

Only unrelated import-time configuration/hooks, extensions, image probing and
the final socket-start boundary are suppressed. _run, get_instance, both
constructors, the bootstrap installer and SDK registration are original code.
"""
import importlib
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
import pytest_asyncio

from openjiuwen.core.runner import Runner
from openjiuwen.core.runner.resources_manager.base import Ok
from openjiuwen.core.workflow import WorkflowCard

from jiuwenswarm.server.runtime.core_workflow_bootstrap import CoreWorkflowBootstrap, CoreWorkflowDefinition
from jiuwenswarm.server.runtime.core_workflow_capabilities import CoreWorkflowCapabilities, CoreWorkflowError, CoreWorkflowScope


class BeforeListening(Exception):
    """Sentinel at server.start entry; no socket or background worker starts."""


@pytest_asyncio.fixture
async def startup(monkeypatch, tmp_path):
    # Import the real entrypoint without its unrelated process-wide setup.
    monkeypatch.setenv('JIUWENSWARM_DATA_DIR', str(tmp_path / 'data'))
    monkeypatch.setattr('jiuwenswarm.dotenv_early.parse_dotenv_early', Mock())
    monkeypatch.setattr('jiuwenswarm.dotenv_early.load_dotenv_runtime', Mock())
    monkeypatch.setattr('jiuwenswarm.common.utils.prepare_workspace', Mock())
    monkeypatch.setattr('jiuwenswarm.common.config.get_config', lambda: {})
    monkeypatch.setattr('openjiuwen.core.common.logging.log_config.configure_log', Mock())
    for module_name, name in (
        ('jiuwenswarm.agents.harness.common.tools.bash_tool_safety', 'install_shell_tool_safety_hooks'),
        ('jiuwenswarm.server.runtime.debug_trace.task_tool_patch', 'apply_task_tool_debug_patch'),
        ('jiuwenswarm.agents.harness.agent_observability', 'install_subagent_observability_hook'),
    ):
        monkeypatch.setattr(importlib.import_module(module_name), name, Mock())
    monkeypatch.delitem(sys.modules, 'jiuwenswarm.server.app_agentserver', raising=False)
    entrypoint = importlib.import_module('jiuwenswarm.server.app_agentserver')

    from jiuwenswarm.extensions.manager import ExtensionManager
    from jiuwenswarm.extensions.registry import ExtensionRegistry
    from jiuwenswarm.server.agent_ws_server import AgentWebSocketServer
    from jiuwenswarm.server.runtime.agent_manager import AgentManager
    monkeypatch.setattr(AgentWebSocketServer, '_instance', None)
    monkeypatch.setattr(ExtensionRegistry, '_instance', None)
    load_extensions = AsyncMock()
    image_warmup = AsyncMock()
    monkeypatch.setattr(ExtensionManager, 'load_all_extensions', load_extensions)
    monkeypatch.setattr('jiuwenswarm.server.runtime.image_modality_warmup.warm_image_modality_cache', image_warmup)
    # The unrelated ACP push callback must not leak this disposable server.
    monkeypatch.setattr('jiuwenswarm.server.agent_ws_server.get_acp_output_manager', Mock(return_value=Mock()))
    reached = []
    async def before_listening(server):
        reached.append(server)
        assert type(server) is AgentWebSocketServer
        assert type(server._agent_manager) is AgentManager
        assert server._server is None
        raise BeforeListening()
    monkeypatch.setattr(AgentWebSocketServer, 'start', before_listening)
    try:
        yield SimpleNamespace(**locals())
    finally:
        server = AgentWebSocketServer._instance
        if server is not None:
            assert server._server is None
            await server._agent_manager.executions.close()
        sys.modules.pop('jiuwenswarm.server.app_agentserver', None)


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['default', 'explicit_none', 'configured'])
async def test_real_startup_chain_installs_before_socket_start_without_constructing_provider(startup, mode):
    s = startup
    card = WorkflowCard(id='startup-' + uuid4().hex, name='Startup registration', version='1',
                        input_params={'type': 'object', 'additionalProperties': False})
    provider = Mock(side_effect=AssertionError('startup must not instantiate Workflow'))
    assert isinstance(Runner.resource_mgr.add_workflow(card=card, workflow=provider), Ok)
    scope = CoreWorkflowScope('web', 'disposable-session', 'disposable-project', 'agent')
    select = Mock(return_value=('registered',))
    authorize = Mock(return_value=None)
    bootstrap = CoreWorkflowBootstrap(definitions=(CoreWorkflowDefinition(
        capability_id='registered', card=card, registered_provider=provider,
        required_permissions=('task.execute',)),), select=select, authorize_web=authorize)
    kwargs = {} if mode == 'default' else {'core_workflow_bootstrap': bootstrap if mode == 'configured' else None}
    try:
        with pytest.raises(BeforeListening):
            await s.entrypoint._run('127.0.0.1', 19243, **kwargs)
        server, = s.reached
        assert server is s.AgentWebSocketServer._instance
        assert server.host == '127.0.0.1' and server.port == 19243
        manager = server._agent_manager
        assert type(manager.core_workflow_capabilities) is CoreWorkflowCapabilities
        assert manager.core_workflow_capabilities.list(scope) == ()
        select.assert_not_called()
        authorize.assert_not_called()
        if mode == 'configured':
            installed = manager.core_workflow_host
            assert installed.bootstrap is bootstrap
            metadata, = installed.bind_scope(scope, operation='list', before_read=lambda: None)
            assert metadata is manager.core_workflow_capabilities.get(scope=scope, capability_id='registered')
            assert metadata.sdk_id == card.id and metadata.required_permissions == ('task.execute',)
        else:
            assert manager.core_workflow_host is None
        assert manager.agents == {} and manager.executions._records == {}
        assert server._scheduler_service is None and server._checkpointer_warmup_task is None
        s.load_extensions.assert_awaited_once()
        s.image_warmup.assert_awaited_once_with({}, reason='startup')
        provider.assert_not_called()
    finally:
        Runner.resource_mgr.remove_workflow(card.id)


@pytest.mark.asyncio
async def test_invalid_registration_aborts_real_startup_before_listening(startup):
    s = startup
    card = WorkflowCard(id='missing-' + uuid4().hex, name='Missing registration', version='1',
                        input_params={'type': 'object'})
    provider = Mock(side_effect=AssertionError('missing registration cannot construct'))
    bootstrap = CoreWorkflowBootstrap(definitions=(CoreWorkflowDefinition(
        capability_id='missing', card=card, registered_provider=provider, required_permissions=()),),
        select=lambda scope: ('missing',), authorize_web=lambda **kwargs: None)
    with pytest.raises(CoreWorkflowError, match='sdk_registration_changed'):
        await s.entrypoint._run('127.0.0.1', 19243, core_workflow_bootstrap=bootstrap)
    assert s.reached == [] and s.AgentWebSocketServer._instance is None
    provider.assert_not_called()
