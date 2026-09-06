"""Native proposals retain explicit source/context and closed operation shapes."""

import pytest
import json

from jiuwenswarm.server.live_voice.native_business_contract import (
    NativeBusinessAction,
    NativeBusinessViolation,
    NativeBusinessProposal,
)
from jiuwenswarm.server.live_voice.native_interaction_contract import NativeInteractionBinding, NativeDelegateProposal
from jiuwenswarm.server.live_voice.native_interaction_carrier import NativeInteractionProposal
from jiuwenswarm.common.schema.live_voice_contract_v2 import ScopeRef, Assurance


def action(operation="task.status", **values):
    return {"operation": operation, "context_id": "a" * 64,
            "target_id": "task-a", "expected_revision": None,
            "name": None, "instruction": None, "adjustment": None, **values}


def test_read_cannot_carry_write_arguments():
    with pytest.raises(NativeBusinessViolation):
        NativeBusinessAction.from_dict(action(adjustment="change a requirement"))
    read = NativeBusinessAction.from_dict(action())
    assert read.task_proposal().operation == "task.status"
    assert dict(read.task_proposal().arguments) == {"query_kind": "status"}
    assert read.mutates is False


def test_exact_adjustment_requires_observed_context_target_and_revision():
    command = action("task.adjust", adjustment="arrive before the meeting", expected_revision=4)
    parsed = NativeBusinessAction.from_dict(command)
    assert parsed.mutates is True
    assert parsed.task_proposal().observed_task_revision == 4
    for field in ("target_id", "context_id", "expected_revision", "adjustment"):
        with pytest.raises(NativeBusinessViolation):
            NativeBusinessAction.from_dict({**command, field: None})


@pytest.mark.parametrize("field,value", [("adjustment", None), ("instruction", "private instruction"),
    ("expected_revision", "4"), ("target_id", None), ("context_id", None)])
def test_adjustment_validation_identifies_field_without_exposing_values(field, value):
    command = action("task.adjust", adjustment="new requirement", expected_revision=4)
    with pytest.raises(NativeBusinessViolation) as rejected:
        NativeBusinessAction.from_dict({**command, field: value})
    assert rejected.value.field == "action." + field
    assert rejected.value.expected
    assert "private instruction" not in str(rejected.value)


def test_operation_and_shape_are_closed_without_text_keyword_classification():
    for operation in ("task.pause", "shell", "task.delete"):
        with pytest.raises(NativeBusinessViolation):
            NativeBusinessAction.from_dict(action(operation))
    with pytest.raises(NativeBusinessViolation):
        NativeBusinessAction.from_dict({**action(), "authorized": True})
    query = NativeBusinessAction.from_dict(action("work.start", target_id=None,
        instruction="Explain the refund order; do not change the running task."))
    assert query.operation == "work.start"
    assert query.mutates is False


def test_create_work_and_task_are_distinct_and_unused_parameters_fail_closed():
    create = NativeBusinessAction.from_dict(action("task.create", target_id=None,
        name="Prepare the report", instruction="Read the project and write the report."))
    assert dict(create.task_proposal().arguments) == {
        "name": "Prepare the report", "instruction": "Read the project and write the report."}
    with pytest.raises(NativeBusinessViolation):
        NativeBusinessAction.from_dict(action("work.start", target_id=None,
            name="Not a Task", instruction="Read the notes"))


def test_context_bootstrap_is_only_operation_allowed_without_context_id():
    request = action("context.get", target_id=None, context_id=None)
    assert NativeBusinessAction.from_dict(request).to_dict() == request
    with pytest.raises(NativeBusinessViolation):
        NativeBusinessAction.from_dict(action(context_id=None))


def test_revision_and_text_bounds_reject_bool_oversize_and_null_bytes():
    for revision in (True, 0, -1, 2**53):
        with pytest.raises(NativeBusinessViolation):
            NativeBusinessAction.from_dict(action("task.cancel", expected_revision=revision))
    for instruction in ("x" * 4097, "\x00", ""):
        with pytest.raises(NativeBusinessViolation):
            NativeBusinessAction.from_dict(action("work.start", target_id=None, instruction=instruction))


def proposal():
    return NativeBusinessProposal(
        binding=NativeInteractionBinding(ScopeRef("user", "project", "session", Assurance.AUTHENTICATED),
            "interaction", "activation", 1, "correlation"),
        turn_id="turn", response_generation=1, provider_event_id="event",
        provider_call_id="call", provider_item_id="item", request_text="What is the task status?",
        business=NativeBusinessAction.from_dict(action()),
    )


def test_actual_carrier_roundtrip_retains_versioned_business_source():
    original = NativeInteractionProposal(binding=proposal().binding, delegate=proposal())
    encoded = json.loads(json.dumps(original.to_dict()))
    with pytest.raises(ValueError, match="Native business proposals require"):
        NativeInteractionProposal.from_dict(encoded)
    restored = NativeInteractionProposal.from_dict(encoded, business_capability=True)
    assert restored == original
    assert isinstance(restored.delegate, NativeBusinessProposal)
    assert restored.delegate.source_identity == original.delegate.source_identity
    # An old delegate parser must not silently discard the extension.
    with pytest.raises(ValueError):
        NativeDelegateProposal.from_dict(proposal().to_dict())


def test_business_function_rejects_duplicate_arguments_and_unknown_version():
    original = proposal()
    base = {key: getattr(original, key) for key in (
        "binding", "turn_id", "response_generation", "provider_event_id", "provider_call_id", "provider_item_id")}
    with pytest.raises(NativeBusinessViolation):
        NativeBusinessProposal.from_function_call(**base,
            arguments='{"request_text":"one","request_text":"two","action":{}}')
    payload = original.to_dict()
    payload["business"]["contract_version"] = "future-version"
    with pytest.raises(NativeBusinessViolation):
        NativeBusinessProposal.from_dict(payload)


def test_proposed_task_arguments_pass_actual_production_policy_validator():
    from jiuwenswarm.server.live_voice.production_task_intent import _validate_arguments
    for value in (
        action("task.list", target_id=None), action(), action("task.result"),
        action("task.create", target_id=None, name="x" * 256, instruction="Read the project"),
        action("task.create_successor", expected_revision=2, name="Successor", instruction="Read the project"),
        action("task.adjust", expected_revision=2, adjustment="New requirements"),
        action("task.cancel", expected_revision=2),
    ):
        parsed = NativeBusinessAction.from_dict(value).task_proposal()
        assert _validate_arguments(parsed.operation, parsed.arguments) is None
    with pytest.raises(NativeBusinessViolation):
        NativeBusinessAction.from_dict(action("task.create", target_id=None, name="x" * 257, instruction="Read the project"))
