"""Provider-specific shapes retain the real v1 carrier and operation validators."""

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
    native_business_proposal_from_function_call,
    native_business_tools,
)
from jiuwenswarm.server.live_voice.native_interaction_carrier import NativeInteractionProposal
from jiuwenswarm.server.live_voice.native_interaction_contract import (
    NativeInteractionBinding,
    NativeInteractionContractViolation,
)
from jiuwenswarm.server.live_voice.production_task_intent import _validate_arguments


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


@pytest.mark.parametrize("operation", SCENARIOS)
def test_every_operation_retains_authoritative_proposal_carrier_and_source(operation):
    flat = inputs(operation)
    legacy = {
        "request_text": flat["request_text"],
        "action": {"operation": operation, **{field: flat.get(field) for field in INTERNAL_FIELDS}},
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
    assert len(tools) == len(SCENARIOS) == 13
    assert {tool["name"] for tool in tools} | {"jiuwen_business"} == NATIVE_BUSINESS_FUNCTION_NAMES
    for tool in tools:
        operation = tool["name"].removeprefix("jiuwen_").replace("_", ".", 1)
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
            assert schema["properties"][field]["type"] == ("integer" if field == "expected_revision" else "string")
    tools[0]["parameters"]["properties"].clear()
    assert native_business_tools()[0]["parameters"]["properties"]


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
