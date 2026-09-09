"""Host allowlist and real SDK Core Workflow invocation/continuation boundary."""

import asyncio
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from unittest.mock import AsyncMock, Mock

import pytest

from openjiuwen.core.common.constants.constant import INTERACTION
from openjiuwen.core.runner import Runner
from openjiuwen.core.session import InteractionOutput
from openjiuwen.core.session.checkpointer import CheckpointerFactory
from openjiuwen.core.session.checkpointer.inmemory import InMemoryCheckpointer
from openjiuwen.core.workflow import End, Start, Workflow, WorkflowCard, WorkflowComponent

from jiuwenswarm.server.runtime.core_workflow_capabilities import (
    CoreWorkflowCapabilities,
    CoreWorkflowError,
    CoreWorkflowScope,
    ResolvedCoreWorkflow,
)


INPUT_SCHEMA = {
    "type": "object", "properties": {"text": {"type": "string"}},
    "required": ["text"], "additionalProperties": False,
}
ANSWER_SCHEMA = {"type": "string", "minLength": 1}
SCOPE = CoreWorkflowScope("web", "public-a", "project-a", "deep")


@pytest.fixture
def registered(monkeypatch):
    directory = CoreWorkflowCapabilities()
    card = WorkflowCard(id="core-fixture", name="Core fixture", version="1", input_params=deepcopy(INPUT_SCHEMA))
    workflow = Workflow(card=card.model_copy(deep=True))
    provider = Mock(return_value=workflow)
    Runner.resource_mgr.add_workflow(card=card, workflow=provider)
    metadata = directory.register(scope=SCOPE, capability_id="fixture", card=card,
        required_permissions=("task.execute",), continuation_schemas={"ask": ANSWER_SCHEMA})
    checkpoint = InMemoryCheckpointer()
    monkeypatch.setattr(CheckpointerFactory, "_default_checkpointer", checkpoint)
    yield directory, metadata, card, workflow, provider, checkpoint
    Runner.resource_mgr.remove_workflow(card.id)


def test_empty_directory_and_metadata_listing_never_instantiate_provider(registered):
    directory, metadata, card, _, provider, _ = registered
    assert CoreWorkflowCapabilities().list(SCOPE) == ()
    assert directory.list(SCOPE) == (metadata,)
    assert directory.list(replace(SCOPE, project_id=None)) == ()
    assert metadata.required_permissions == ("task.execute",)
    card.input_params["properties"]["text"]["type"] = "number"
    assert metadata.input_schema["properties"]["text"]["type"] == "string"
    metadata.input_schema["properties"]["text"]["type"] = "null"
    assert metadata.input_schema["properties"]["text"]["type"] == "string"
    with pytest.raises(FrozenInstanceError):
        metadata.capability_id = "other"
    provider.assert_not_called()


@pytest.mark.parametrize("field,value", [
    ("channel_id", None), ("channel_id", " web"), ("session_id", 12),
    ("session_id", ""), ("project_id", []), ("project_id", ""),
    ("agent_mode", False), ("agent_mode", "deep\x00"),
])
def test_scope_has_exact_typed_identity_fields(field, value):
    with pytest.raises(CoreWorkflowError):
        replace(SCOPE, **{field: value})


def test_registration_requires_schema_and_is_not_silently_replaced(registered):
    directory, metadata, card, _, provider, _ = registered
    with pytest.raises(CoreWorkflowError, match="already_registered"):
        directory.register(scope=SCOPE, capability_id="fixture", card=card, required_permissions=())
    card.input_params = None
    with pytest.raises(CoreWorkflowError, match="missing_schema"):
        directory.register(scope=SCOPE, capability_id="other", card=card, required_permissions=())
    assert directory.list(SCOPE) == (metadata,)
    provider.assert_not_called()


@pytest.mark.parametrize("field,value", [
    ("channel_id", "native"), ("session_id", "other"),
    ("project_id", None), ("agent_mode", "code"),
])
@pytest.mark.asyncio
async def test_wrong_scope_has_zero_provider_and_checkpoint_effects(registered, field, value):
    directory, _, _, _, provider, checkpoint = registered
    guard = Mock(return_value=None)
    with pytest.raises(CoreWorkflowError, match="not_registered"):
        await directory.resolve(scope=replace(SCOPE, **{field: value}), capability_id="fixture", before_effect=guard)
    provider.assert_not_called()
    guard.assert_not_called()
    assert checkpoint._workflow_stores == {}


@pytest.mark.asyncio
async def test_global_sdk_registration_is_not_host_authorization(registered):
    _, _, _, _, provider, _ = registered
    with pytest.raises(CoreWorkflowError, match="not_registered"):
        await CoreWorkflowCapabilities().resolve(scope=SCOPE, capability_id="core-fixture", before_effect=Mock(return_value=None))
    provider.assert_not_called()


@pytest.mark.asyncio
async def test_removed_sdk_registration_is_unavailable_without_execution(registered, monkeypatch):
    directory, _, card, _, provider, checkpoint = registered
    Runner.resource_mgr.remove_workflow(card.id)
    execute = AsyncMock()
    monkeypatch.setattr(Runner, "run_workflow", execute)
    with pytest.raises(CoreWorkflowError, match="workflow_unavailable"):
        await directory.resolve(scope=SCOPE, capability_id="fixture", before_effect=Mock(return_value=None))
    provider.assert_not_called()
    execute.assert_not_awaited()
    assert checkpoint._workflow_stores == {}


@pytest.mark.asyncio
async def test_revoked_authority_prevents_provider_resolution(registered):
    directory, _, _, _, provider, _ = registered
    with pytest.raises(PermissionError):
        await directory.resolve(scope=SCOPE, capability_id="fixture",
            before_effect=Mock(side_effect=PermissionError("revoked")))
    provider.assert_not_called()


@pytest.mark.parametrize("guard", [None, AsyncMock(), Mock(return_value=False)])
@pytest.mark.asyncio
async def test_missing_async_or_false_authority_guard_has_zero_provider_effects(registered, guard):
    directory, _, _, _, provider, _ = registered
    with pytest.raises(CoreWorkflowError):
        await directory.resolve(scope=SCOPE, capability_id="fixture", before_effect=guard)
    provider.assert_not_called()


@pytest.mark.parametrize("field,value", [("id", "different"), ("version", "2"), ("input_params", {"type": "null"})])
@pytest.mark.asyncio
async def test_provider_card_mismatch_is_rejected_before_runner(registered, monkeypatch, field, value):
    directory, _, _, workflow, provider, checkpoint = registered
    setattr(workflow.card, field, value)
    execute = AsyncMock()
    monkeypatch.setattr(Runner, "run_workflow", execute)
    with pytest.raises(CoreWorkflowError, match="card_mismatch"):
        await directory.resolve(scope=SCOPE, capability_id="fixture", before_effect=Mock(return_value=None))
    provider.assert_called_once()
    execute.assert_not_awaited()
    assert checkpoint._workflow_stores == {}


@pytest.mark.asyncio
async def test_invalid_inputs_and_wrong_binding_scope_never_enter_runner(registered, monkeypatch):
    directory, _, _, _, _, checkpoint = registered
    binding = await directory.resolve(scope=SCOPE, capability_id="fixture", before_effect=Mock(return_value=None))
    execute = AsyncMock()
    monkeypatch.setattr(Runner, "run_workflow", execute)
    for scope, inputs in [(SCOPE, {"text": 12}), (replace(SCOPE, session_id="other"), {"text": "valid"})]:
        with pytest.raises(CoreWorkflowError):
            await directory.invoke(scope=scope, binding=binding, sdk_session_id="private-a",
                inputs=inputs, before_effect=Mock(return_value=None))
    with pytest.raises(CoreWorkflowError, match="invalid_binding"):
        await CoreWorkflowCapabilities().invoke(scope=SCOPE, binding=binding, sdk_session_id="private-a",
            inputs={"text": "valid"}, before_effect=Mock(return_value=None))
    execute.assert_not_awaited()
    assert checkpoint._workflow_stores == {}


@pytest.mark.asyncio
async def test_fabricated_binding_and_changed_card_never_enter_runner(registered, monkeypatch):
    directory, _, _, workflow, _, _ = registered
    binding = await directory.resolve(scope=SCOPE, capability_id="fixture", before_effect=Mock(return_value=None))
    execute = AsyncMock()
    monkeypatch.setattr(Runner, "run_workflow", execute)
    with pytest.raises(CoreWorkflowError, match="invalid_binding"):
        await directory.invoke(scope=SCOPE, binding=ResolvedCoreWorkflow(), sdk_session_id="private-a",
            inputs={"text": "valid"}, before_effect=Mock(return_value=None))
    workflow.card.version = "changed-after-resolve"
    with pytest.raises(CoreWorkflowError, match="card_mismatch"):
        await directory.invoke(scope=SCOPE, binding=binding, sdk_session_id="private-a",
            inputs={"text": "valid"}, before_effect=Mock(return_value=None))
    execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_sdk_execution_exception_is_not_fabricated_completion(registered, monkeypatch):
    directory, _, _, _, _, _ = registered
    binding = await directory.resolve(scope=SCOPE, capability_id="fixture", before_effect=Mock(return_value=None))
    execute = AsyncMock(side_effect=RuntimeError("checkpoint unavailable"))
    monkeypatch.setattr(Runner, "run_workflow", execute)
    with pytest.raises(RuntimeError, match="checkpoint unavailable"):
        await directory.invoke(scope=SCOPE, binding=binding, sdk_session_id="private-a",
            inputs={"text": "valid"}, before_effect=Mock(return_value=None))


@pytest.mark.parametrize("pending,answers", [
    ([], {"ask": "yes"}),
    ([InteractionOutput(id="ask", value="?")], {"different": "yes"}),
    ([InteractionOutput(id="ask", value="?")], {"ask": 12}),
    ([InteractionOutput(id="ask", value="?")], {"ask": "yes", "extra": "no"}),
    ([InteractionOutput(id="ask", value="?"), InteractionOutput(id="ask", value="again")], {"ask": "yes"}),
    ([InteractionOutput(id="unregistered-node", value="?")], {"unregistered-node": "yes"}),
])
@pytest.mark.asyncio
async def test_invalid_continuation_never_enters_runner_or_checkpoint(registered, monkeypatch, pending, answers):
    directory, _, _, _, _, checkpoint = registered
    binding = await directory.resolve(scope=SCOPE, capability_id="fixture", before_effect=Mock(return_value=None))
    execute = AsyncMock()
    monkeypatch.setattr(Runner, "run_workflow", execute)
    with pytest.raises(CoreWorkflowError):
        await directory.continue_workflow(scope=SCOPE, binding=binding, sdk_session_id="private-a",
            pending=pending, answers=answers, before_effect=Mock(return_value=None))
    execute.assert_not_awaited()
    assert checkpoint._workflow_stores == {}


class Ask(WorkflowComponent):
    async def invoke(self, inputs, session, context):
        answer = await session.interact("Confirm the fixture input")
        return {"answer": answer}


@pytest.mark.parametrize("interactive", [False, True])
@pytest.mark.asyncio
async def test_real_sdk_completion_and_input_required_continuation(registered, interactive):
    directory, _, _, workflow, provider, checkpoint = registered
    workflow.set_start_comp("start", Start(), inputs_schema={"text": "${text}"})
    if interactive:
        workflow.add_workflow_comp("ask", Ask())
        workflow.add_connection("start", "ask")
        workflow.set_end_comp("end", End(), inputs_schema={"answer": "${ask.answer}"})
        workflow.add_connection("ask", "end")
    else:
        workflow.set_end_comp("end", End(), inputs_schema={"text": "${start.text}"})
        workflow.add_connection("start", "end")
    guard = Mock(return_value=None)
    binding = await directory.resolve(scope=SCOPE, capability_id="fixture", before_effect=guard)
    result = await directory.invoke(scope=SCOPE, binding=binding, sdk_session_id="private-real",
        inputs={"text": "original"}, before_effect=guard)
    if interactive:
        assert result.state.value == "INPUT_REQUIRED"
        pending = [chunk.payload for chunk in result.result if chunk.type == INTERACTION]
        assert [item.id for item in pending] == ["ask"]
        state_before = dict(checkpoint._workflow_stores["private-real"].state_blobs)
        rejected_guard = Mock(return_value=None)
        for scope, answers in [
            (replace(SCOPE, session_id="wrong-public-session"), {"ask": "valid"}),
            (SCOPE, {"wrong-node": "valid"}), (SCOPE, {"ask": 12}),
        ]:
            with pytest.raises(CoreWorkflowError):
                await directory.continue_workflow(scope=scope, binding=binding, sdk_session_id="private-real",
                    pending=pending, answers=answers, before_effect=rejected_guard)
        rejected_guard.assert_not_called()
        assert checkpoint._workflow_stores["private-real"].state_blobs == state_before
        with pytest.raises(PermissionError):
            await directory.continue_workflow(scope=SCOPE, binding=binding, sdk_session_id="private-real",
                pending=pending, answers={"ask": "denied"},
                before_effect=Mock(side_effect=PermissionError("revoked")))
        assert checkpoint._workflow_stores["private-real"].state_blobs == state_before
        # A changed global registry cannot retarget the resolved run's instance.
        Runner.resource_mgr.remove_workflow(workflow.card.id)
        replacement_provider = Mock(side_effect=AssertionError("continuation must retain original instance"))
        Runner.resource_mgr.add_workflow(card=workflow.card, workflow=replacement_provider)
        result = await directory.continue_workflow(scope=SCOPE, binding=binding, sdk_session_id="private-real",
            pending=pending, answers={"ask": "accepted"}, before_effect=guard)
        replacement_provider.assert_not_called()
        assert result.result == {"output": {"answer": "accepted"}}
    else:
        assert result.result == {"output": {"text": "original"}}
    assert result.state.value == "COMPLETED"
    assert "private-real" not in checkpoint._workflow_stores
    provider.assert_called_once()
    assert guard.call_count == (3 if interactive else 2)
    await asyncio.sleep(0)
