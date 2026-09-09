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


@pytest.mark.parametrize("operation,extra,mutates", [
    ("core_workflow.list", {"target_id": None}, False),
    ("core_workflow.get", {"epoch": "epoch", "target_id": "run"}, False),
    ("core_workflow.start", {"target_id": None, "epoch": "epoch", "capability_id": "flow", "inputs": {}}, True),
    ("core_workflow.resume", {"target_id": "run", "epoch": "epoch", "expected_revision": 2, "answers": {"ask": "yes"}}, True),
])
def test_core_operations_keep_exact_new_fields_separate_from_existing_wire(operation, extra, mutates):
    body = action(operation, **extra)
    parsed = NativeBusinessAction.from_dict(body)
    assert parsed.to_dict() == body
    assert parsed.mutates is mutates
    for field in {"epoch", "capability_id", "inputs", "answers"} & set(body):
        with pytest.raises(NativeBusinessViolation):
            NativeBusinessAction.from_dict({key: value for key, value in body.items() if key != field})
    for field in {"epoch", "capability_id", "inputs", "answers"} - set(body):
        with pytest.raises(NativeBusinessViolation):
            NativeBusinessAction.from_dict({**body, field: None})
    old = action("workflow.get")
    for key in ("epoch", "capability_id", "inputs", "answers"):
        with pytest.raises(NativeBusinessViolation):
            NativeBusinessAction.from_dict({**old, key: None})


@pytest.mark.parametrize("value", [None, [], {1: "bad"}, {"x": float("nan")}, {"x": object()}, {"x": "a" * 8192}])
def test_core_json_rejects_nonobject_nonfinite_and_oversized_inputs(value):
    with pytest.raises(NativeBusinessViolation):
        NativeBusinessAction.from_dict(action("core_workflow.start", target_id=None,
            epoch="epoch", capability_id="flow", inputs=value))


def test_core_json_snapshots_do_not_mutate_original_or_exported_arguments():
    value = {"nested": ["first"]}
    parsed = NativeBusinessAction.from_dict(action("core_workflow.start", target_id=None,
        epoch="epoch", capability_id="flow", inputs=value))
    value["nested"].append("second")
    exported = parsed.to_dict()
    exported["inputs"]["nested"].append("third")
    assert parsed.to_dict()["inputs"] == {"nested": ["first"]}


def test_agent_reply_requires_exact_source_question_generation_and_snapshots_answer():
    answer = [{"question": "Proceed?", "selected_options": ["Approve"]}]
    body = action("agent.reply", target_id="binding", source_task_id="task",
                  pending_token="generation", input_id="question", answers=answer)
    parsed = NativeBusinessAction.from_dict(body)
    assert parsed.mutates and parsed.to_dict() == body
    for field in ("target_id", "source_task_id", "pending_token", "input_id", "answers"):
        with pytest.raises(NativeBusinessViolation):
            NativeBusinessAction.from_dict({key: value for key, value in body.items() if key != field})
    answer[0]["selected_options"].append("Deny")
    exported = parsed.to_dict()
    exported["answers"].clear()
    assert parsed.to_dict()["answers"][0]["selected_options"] == ["Approve"]
    assert NativeBusinessAction.from_dict(action("agent.pending", target_id=None)).mutates is False


@pytest.mark.parametrize("change", [
    {"answers": {}}, {"answers": []}, {"answers": [float("nan")]}, {"answers": ["x" * 8192]},
    {"pending_token": None}, {"pending_token": " old "}, {"source_task_id": None},
    {"input_id": " wrong "}, {"expected_revision": 1}, {"epoch": "foreign"},
])
def test_agent_reply_rejects_wrong_shapes_and_foreign_family_fields(change):
    body = action("agent.reply", target_id="binding", source_task_id="task",
                  pending_token="generation", input_id="question", answers=[{"selected_options": ["Deny"]}])
    with pytest.raises(NativeBusinessViolation):
        NativeBusinessAction.from_dict({**body, **change})


def test_workflow_reply_requires_exact_pending_input_and_preserves_old_canonical_shapes():
    body = action("workflow.reply", target_id="run-1", instruction="Use the first source.",
                  input_id="review:host:0")
    parsed = NativeBusinessAction.from_dict(body)
    assert parsed.mutates and parsed.input_id == "review:host:0"
    assert parsed.to_dict() == body
    for change in ({"input_id": None}, {"input_id": " foreign "}, {"input_id": "\x00"},
                   {"expected_revision": 1}, {"name": "guessed phase"}):
        with pytest.raises(NativeBusinessViolation):
            NativeBusinessAction.from_dict({**body, **change})
    old = action("workflow.get", target_id="run-1")
    assert NativeBusinessAction.from_dict(old).to_dict() == old
    with pytest.raises(NativeBusinessViolation):
        NativeBusinessAction.from_dict({**old, "input_id": "review:host:0"})


@pytest.mark.parametrize("target,revision", [(None, None), ("goal-a", 7)])
def test_goal_set_requires_explicit_create_or_exact_replacement_pair(target, revision):
    body = action("goal.set", target_id=target, expected_revision=revision, instruction="Read the full source.")
    parsed = NativeBusinessAction.from_dict(body)
    assert parsed.to_dict() == body and parsed.mutates
    for changes in ({"target_id": None, "expected_revision": 7},
                    {"target_id": "goal-a", "expected_revision": None},
                    {"expected_revision": True}, {"instruction": None},
                    {"name": "invented name"}, {"input_id": "wrong-protocol"}):
        with pytest.raises(NativeBusinessViolation):
            NativeBusinessAction.from_dict({**body, **changes})


def test_goal_resume_requires_control_cas_and_does_not_expand_old_canonical_operations():
    body = action("goal.resume", target_id="goal-a", expected_revision=3)
    assert NativeBusinessAction.from_dict(body).mutates
    for changes in ({"target_id": None}, {"expected_revision": None}, {"expected_revision": 0},
                    {"expected_revision": True}, {"instruction": "not a new objective"}):
        with pytest.raises(NativeBusinessViolation):
            NativeBusinessAction.from_dict({**body, **changes})
    for operation in ("goal.pause", "goal.clear", "task.cancel", "work.cancel"):
        old = action(operation, expected_revision=3)
        parsed = NativeBusinessAction.from_dict(old)
        assert json.dumps(parsed.to_dict(), sort_keys=True, separators=(",", ":")) == json.dumps(
            old, sort_keys=True, separators=(",", ":"))
        assert "input_id" not in parsed.to_dict()


@pytest.mark.parametrize("operation,target", [("workflow.list", None), ("workflow.get", "workflow-a")])
def test_workflow_observation_is_read_only_and_has_closed_arguments(operation, target):
    body = action(operation, target_id=target)
    assert NativeBusinessAction.from_dict(body).mutates is False
    for name, value in {"instruction": "start a run", "name": "new workflow", "adjustment": "change it",
                        "expected_revision": 1}.items():
        with pytest.raises(NativeBusinessViolation):
            NativeBusinessAction.from_dict({**body, name: value})


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
