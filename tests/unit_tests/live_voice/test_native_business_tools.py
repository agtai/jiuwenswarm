"""Provider-specific shapes retain the real v1 carrier and operation validators."""

import hashlib
import json

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import Assurance, ScopeRef
from jiuwenswarm.server.live_voice.native_business_contract import (
    NATIVE_BUSINESS_OPERATIONS,
    NativeBusinessProposal,
    NativeBusinessViolation,
)
from jiuwenswarm.server.live_voice.native_business_tools import (
    NATIVE_BUSINESS_FUNCTION_NAMES,
    NATIVE_BOUND_BUSINESS_FUNCTION_NAMES,
    native_business_proposal_from_function_call,
    native_business_tools,
)
from jiuwenswarm.server.live_voice.native_interaction_carrier import NativeInteractionProposal
from jiuwenswarm.server.live_voice.native_interaction_contract import (
    NativeInteractionBinding,
    NativeInteractionContractViolation,
)
from jiuwenswarm.server.live_voice.production_task_intent import _validate_arguments


@pytest.mark.parametrize("bound,expected", [
    (False, "56062f53e0997493d74f5cae2c19cd93f42b504386db0f5711f6bb05b905cc82"),
    (True, "2bb0c473bf4beede941064cfd46edd825f55ffbe31f43130fac18ec737cb89d5"),
    (None, "a76483c0d296951464a10f028941fd07f9ae3cd6a7e3423ffc9465dbe34c5f54"),
])
def test_provider_catalog_matches_reviewed_contract_snapshot(bound, expected):
    from jiuwenswarm.server.live_voice.native_business_contract import native_business_tool

    # The shared capability schemas retain the W3 Task/Work prompt and state
    # rules. Array order, required fields, descriptions and nullability stay exact.
    catalog = native_business_tool() if bound is None else native_business_tools(bound_context=bound)
    encoded = json.dumps(catalog, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    assert hashlib.sha256(encoded).hexdigest() == expected


# Expected business inputs are written independently of the adapter's table.
SCENARIOS = {
    "context.get": {"context_id": None},
    "task.list": {},
    "task.status": {"target_id": "task-a"},
    "task.result": {"target_id": "task-a"},
    "task.create": {"name": "Report", "instruction": "Read the source and write the report."},
    "task.create_successor": {"target_id": "task-a", "expected_revision": 4, "name": "Successor", "instruction": "Extend the report."},
    "task.adjust": {"target_id": "task-a", "expected_revision": 4, "adjustment": "下午五点出发，保留其他要求。"},
    "task.cancel": {"target_id": "task-a", "expected_revision": 4},
    "work.start": {"instruction": "Read the actual project facts and identify missing departure constraints."},
    "work.list": {},
    "work.get": {"target_id": "work-a"},
    "work.update": {"target_id": "work-a", "expected_revision": 4, "instruction": "Include the latest stated constraint."},
    "work.cancel": {"target_id": "work-a", "expected_revision": 4},
    "workflow.list": {},
    "workflow.get": {"target_id": "workflow-a"},
    "workflow.reply": {"target_id": "workflow-a", "input_id": "review:host:0", "instruction": "Use the first source."},
    "agent.list": {},
    "agent.get": {"target_id": "execution-a"},
    "agent.pending": {},
    "agent.reply": {"target_id": "original-binding", "source_task_id": "actual-task",
                    "pending_token": "pending-generation", "input_id": "question-id",
                    "answers": [{"id": "approval", "value": "approve"}]},
    "team.list": {},
    "team.get": {"target_id": "team-execution", "epoch": "epoch"},
    "team.start": {"epoch": "epoch", "fingerprint": None, "instruction": "Carry out the configured Team task."},
    "team.cancel": {"target_id": "team-execution", "epoch": "epoch"},
    "workflow.start": {"epoch": "epoch", "fingerprint": "b" * 64, "inputs": {"script_path": "flow.swarmflow", "args": "{}"}},
    "goal.get": {},
    "goal.set": {"target_id": None, "expected_revision": None, "instruction": "Investigate the explicitly requested objective."},
    "goal.resume": {"target_id": "goal-a", "expected_revision": 4},
    "goal.pause": {"target_id": "goal-a", "expected_revision": 4},
    "goal.clear": {"target_id": "goal-a", "expected_revision": 4},
    "core_workflow.list": {},
    "core_workflow.get": {"target_id": "core-run", "epoch": "current-epoch"},
    "core_workflow.start": {"epoch": "current-epoch", "capability_id": "registered-flow", "inputs": {"text": "用户输入"}},
    "core_workflow.resume": {"target_id": "core-run", "epoch": "current-epoch", "expected_revision": 2,
                             "answers": {"ask": {"choice": "first"}}},
}
INTERNAL_FIELDS = {"context_id", "target_id", "expected_revision", "name", "instruction", "adjustment"}


def binding(**changes):
    return {
        "binding": NativeInteractionBinding(
            ScopeRef("user", "project", "session", Assurance.AUTHENTICATED),
            "interaction", "activation", 1, "correlation",
        ),
        "turn_id": "turn", "response_generation": 1,
        "provider_event_id": "event", "provider_call_id": "call", "provider_item_id": "item",
        **changes,
    }


def inputs(operation, **changes):
    return {
        "request_text": "请按我的当前要求处理，保留约束。", "context_id": "a" * 64,
        **SCENARIOS[operation], **changes,
    }


def decode(operation, *, values=None, **changes):
    return native_business_proposal_from_function_call(
        name="jiuwen_" + operation.replace(".", "_"),
        arguments=json.dumps(inputs(operation) if values is None else values, ensure_ascii=False),
        **binding(**changes),
    )


def test_workflow_reply_provider_tool_keeps_run_and_pending_input_identity():
    data = {"request_text": "Use the first source.", "context_id": "a" * 64,
            "target_id": "run-1", "input_id": "review:host:0", "instruction": "Use the first source."}
    proposal = native_business_proposal_from_function_call(name="jiuwen_workflow_reply",
        arguments=json.dumps(data), **binding())
    assert proposal.business.operation == "workflow.reply"
    assert proposal.business.target_id == "run-1"
    assert proposal.business.input_id == "review:host:0"
    assert proposal.business.instruction == "Use the first source."
    with pytest.raises(NativeBusinessViolation):
        native_business_proposal_from_function_call(name="jiuwen_workflow_reply",
            arguments=json.dumps({key: value for key, value in data.items() if key != "input_id"}), **binding())


@pytest.mark.parametrize("operation", SCENARIOS)
def test_every_operation_retains_authoritative_proposal_carrier_and_source(operation):
    flat = inputs(operation)
    legacy = {
        "request_text": flat["request_text"],
        "action": {"operation": operation, **{field: flat.get(field) for field in INTERNAL_FIELDS},
                   **{field: flat[field] for field in ("input_id", "epoch", "capability_id", "inputs", "answers", "source_task_id", "pending_token", "fingerprint") if field in flat}},
    }
    expected = NativeBusinessProposal.from_function_call(arguments=json.dumps(legacy), **binding())
    actual = decode(operation)
    compatible = native_business_proposal_from_function_call(
        name="jiuwen_business", arguments=json.dumps(legacy), **binding(),
    )
    assert actual == expected == compatible
    assert actual.source_identity == expected.source_identity
    carrier = NativeInteractionProposal(binding=actual.binding, delegate=actual)
    assert NativeInteractionProposal.from_dict(
        json.loads(json.dumps(carrier.to_dict())), business_capability=True,
    ) == carrier
    with pytest.raises(ValueError, match="Native business proposals require"):
        NativeInteractionProposal.from_dict(carrier.to_dict())
    if operation.startswith("task."):
        task = actual.business.task_proposal()
        assert _validate_arguments(task.operation, task.arguments) is None


def test_tool_catalog_covers_existing_operations_without_legacy_or_unused_arguments():
    tools = native_business_tools()
    assert set(SCENARIOS) == NATIVE_BUSINESS_OPERATIONS
    assert len(tools) == len(SCENARIOS) == 34
    assert {tool["name"] for tool in tools} | {"jiuwen_business"} | NATIVE_BOUND_BUSINESS_FUNCTION_NAMES == NATIVE_BUSINESS_FUNCTION_NAMES
    for tool in tools:
        operation = next(value for value in SCENARIOS if tool["name"] == "jiuwen_" + value.replace(".", "_"))
        # create_successor's remaining underscore is part of the operation.
        expected_fields = set(inputs(operation))
        schema = tool["parameters"]
        assert set(schema["required"]) == set(schema["properties"]) == expected_fields
        assert schema["additionalProperties"] is False
        assert "strict" not in tool
        assert schema["properties"]["context_id"]["type"] == (
            ["string", "null"] if operation == "context.get" else "string"
        )
        for field in expected_fields - {"context_id"}:
            if field == "fingerprint":
                assert schema["properties"][field]["type"] == ["string", "null"]
                continue
            if operation == "goal.set" and field in {"target_id", "expected_revision"}:
                variants = schema["properties"][field]["anyOf"]
                assert [item["type"] for item in variants] == [
                    "integer" if field == "expected_revision" else "string", "null"]
                continue
            assert schema["properties"][field]["type"] == (
                "integer" if field == "expected_revision" else "array" if operation == "agent.reply" and field == "answers"
                else "object" if field in {"inputs", "answers"} else "string")
    tools[0]["parameters"]["properties"].clear()
    assert native_business_tools()[0]["parameters"]["properties"]


@pytest.mark.parametrize("bound", [False, True])
@pytest.mark.parametrize("target,revision", [(None, None), ("goal-a", 4)])
def test_goal_set_tool_schema_and_decoder_support_exact_null_or_replacement_pair(bound, target, revision):
    from jsonschema import validate

    name = "jiuwen_bound_goal_set" if bound else "jiuwen_goal_set"
    data = {"request_text": "Inspect all requested source facts.", "target_id": target, "expected_revision": revision}
    if not bound:
        data.update(context_id="a" * 64, instruction="Inspect all requested source facts.")
    tool = next(item for item in native_business_tools(bound_context=bound) if item["name"] == name)
    validate(data, tool["parameters"])
    parsed = native_business_proposal_from_function_call(name=name, arguments=json.dumps(data),
        **({"server_context_id": "a" * 64} if bound else {}), **binding())
    assert parsed.business.target_id == target and parsed.business.expected_revision == revision
    assert parsed.business.instruction == data["request_text"]
    for extra in ("model_name", "mode", "authorized", "input_id"):
        with pytest.raises(NativeBusinessViolation):
            native_business_proposal_from_function_call(name=name,
                arguments=json.dumps({**data, extra: "forged"}),
                **({"server_context_id": "a" * 64} if bound else {}), **binding())


@pytest.mark.parametrize("operation", SCENARIOS)
def test_required_fields_are_never_guessed_and_unused_fields_never_ignored(operation):
    valid = inputs(operation)
    for field in valid:
        with pytest.raises(NativeBusinessViolation, match="FIELDS_NOT_CLOSED"):
            decode(operation, values={key: value for key, value in valid.items() if key != field})
    for extra in {"operation", "authorized", "action", "unknown", *INTERNAL_FIELDS} - set(valid):
        with pytest.raises(NativeBusinessViolation, match="FIELDS_NOT_CLOSED"):
            decode(operation, values={**valid, extra: None})


@pytest.mark.parametrize("field,value", [
    ("adjustment", None), ("adjustment", 7), ("adjustment", " "),
    ("adjustment", "x\x00y"), ("adjustment", "中" * 1366),
    ("expected_revision", True), ("expected_revision", "4"),
    ("expected_revision", 4.0), ("expected_revision", 0), ("expected_revision", 2**53),
    ("target_id", None), ("target_id", " task-a"), ("target_id", "x" * 257),
    ("context_id", None), ("context_id", "a" * 63), ("context_id", "A" * 64),
])
def test_invalid_adjustment_exposes_only_the_advertised_flat_field(field, value):
    with pytest.raises(NativeBusinessViolation) as rejected:
        decode("task.adjust", values=inputs("task.adjust", **{field: value}))
    assert rejected.value.field == field
    assert rejected.value.operation == "task.adjust"
    assert rejected.value.expected
    assert "下午五点" not in str(rejected.value)
    assert "下午五点" not in rejected.value.expected


@pytest.mark.parametrize("operation,field,maximum", [
    ("work.start", "instruction", 4096), ("task.adjust", "adjustment", 4096),
    ("task.create", "name", 256), ("task.create", "instruction", 4096),
])
def test_text_utf8_bounds_match_existing_action_validation(operation, field, maximum):
    text = "中" * (maximum // 3) + "x" * (maximum % 3)
    actual = decode(operation, values=inputs(operation, **{field: text}))
    assert getattr(actual.business, field) == text
    with pytest.raises(NativeBusinessViolation):
        decode(operation, values=inputs(operation, **{field: text + "x"}))


@pytest.mark.parametrize("value", [None, "", " request", "request\n", "a\x00b", "\ud800"])
def test_request_text_retains_existing_contract_validation(value):
    raw = json.dumps(inputs("work.start", request_text=value), ensure_ascii=True)
    with pytest.raises(NativeInteractionContractViolation):
        native_business_proposal_from_function_call(name="jiuwen_work_start", arguments=raw, **binding())


@pytest.mark.parametrize("name", [None, [], "work.start", "jiuwen_shell", "jiuwen_work_start "])
def test_unknown_tool_cannot_select_or_guess_operation(name):
    with pytest.raises(NativeBusinessViolation, match="FUNCTION_UNSUPPORTED"):
        native_business_proposal_from_function_call(name=name, arguments="{}", **binding())


@pytest.mark.parametrize("raw", [
    "[]", "null", "true", "{}", "not JSON", "{\"request_text\": \"a\",}",
    "{\"request_text\": NaN}", "{\"request_text\": Infinity}",
    "{\"request_text\":\"a\",\"request_text\":\"b\"}",
    "{\"request_text\":{\"x\":1,\"x\":2}}", "[" * 2000 + "]" * 2000,
    "\ud800", " " * 16385,
])
def test_malformed_duplicate_or_unbounded_json_fails_closed(raw):
    with pytest.raises(NativeBusinessViolation):
        native_business_proposal_from_function_call(name="jiuwen_work_start", arguments=raw, **binding())


def test_duplicate_key_rejection_does_not_echo_untrusted_key_or_value():
    with pytest.raises(NativeBusinessViolation) as rejected:
        native_business_proposal_from_function_call(
            name="jiuwen_work_start", arguments='{"private-secret":"private-value","private-secret":"other"}',
            **binding(),
        )
    assert rejected.value.reason == "NATIVE_BUSINESS_DUPLICATE_FIELD"
    assert rejected.value.operation == "work.start"
    assert "private" not in str(rejected.value) + rejected.value.expected + rejected.value.field


def test_missing_instruction_has_actionable_content_free_flat_diagnostic():
    with pytest.raises(NativeBusinessViolation) as rejected:
        decode("work.start", values={key: value for key, value in inputs("work.start").items() if key != "instruction"})
    assert rejected.value.field == "instruction"
    assert rejected.value.operation == "work.start"
    assert "请按" not in rejected.value.expected


def test_raw_utf8_bound_includes_json_envelope_and_legacy_parser_depth_is_closed():
    raw = json.dumps(inputs("work.start"), ensure_ascii=False)
    padded = raw + " " * (16384 - len(raw.encode("utf-8")))
    assert native_business_proposal_from_function_call(
        name="jiuwen_work_start", arguments=padded, **binding(),
    ) == decode("work.start")
    for name in ("jiuwen_work_start", "jiuwen_business"):
        for invalid in (padded + " ", "[" * 2000 + "]" * 2000, "\ud800"):
            with pytest.raises(NativeBusinessViolation):
                native_business_proposal_from_function_call(name=name, arguments=invalid, **binding())


def test_operation_is_fixed_and_request_text_is_never_used_as_missing_instruction():
    actual = decode("work.start", values=inputs("work.start", request_text="task.cancel task-a now"))
    assert actual.business.operation == "work.start"
    assert actual.business.target_id is None
    assert actual.business.instruction == SCENARIOS["work.start"]["instruction"]
    for instruction in (None, ""):
        with pytest.raises(NativeBusinessViolation):
            decode("work.start", values=inputs("work.start", instruction=instruction))


@pytest.mark.parametrize("field,value", [
    ("turn_id", "other-turn"), ("response_generation", 2),
    ("provider_event_id", "other-event"), ("provider_call_id", "other-call"),
    ("provider_item_id", "other-item"),
    ("binding", NativeInteractionBinding(
        ScopeRef("other-user", "other-project", "other-session", Assurance.AUTHENTICATED),
        "other-interaction", "other-activation", 2, "other-correlation",
    )),
])
def test_binding_remains_exact_and_source_identity_changes_with_scope(field, value):
    original = decode("task.adjust")
    changed = decode("task.adjust", **{field: value})
    assert getattr(changed, field) == value
    assert changed.source_identity != original.source_identity
    assert decode("task.adjust") == original


def test_real_session_serializer_carries_all_named_tool_schemas():
    from jiuwenswarm.server.live_voice.openai_realtime_session import _encode_client_event

    wire = _encode_client_event({
        "event_id": "event", "type": "session.update", "session": {"tools": native_business_tools()},
    })
    assert json.loads(wire)["session"]["tools"] == native_business_tools()
