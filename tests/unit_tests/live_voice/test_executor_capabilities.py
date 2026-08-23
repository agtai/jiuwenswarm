# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import hashlib
import json
from dataclasses import FrozenInstanceError, replace

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    ErrorCode,
    MAX_SAFE_INTEGER,
)
from jiuwenswarm.server.live_voice.executor_capabilities import (
    EXECUTOR_CAPABILITY_PROFILE_SCHEMA_VERSION,
    TASK_EXECUTION_REQUIREMENTS_SCHEMA_VERSION,
    ExecutorCapabilityProfile,
    ExecutorSelection,
    TaskExecutionRequirements,
    select_executor,
)
from jiuwenswarm.server.live_voice.formal_task_models import FormalTaskViolation


def _profile(**overrides: object) -> ExecutorCapabilityProfile:
    values: dict[str, object] = {
        "schema_version": EXECUTOR_CAPABILITY_PROFILE_SCHEMA_VERSION,
        "profile_id": "profile.direct.d0.v1",
        "executor_id": "jiuwenswarm_code_agent.project_code",
        "adapter_id": "adapter.direct-project-code",
        "adapter_protocol_version": "live-voice.direct-project-code.v1",
        "operation_versions": (
            ("status", "v1"),
            ("dispatch", "v1"),
            ("cancel", "v1"),
        ),
        "durability_level": "D0",
        "durability_version": "live-voice.direct-d0.v1",
        "project_serialization": "exclusive",
        "max_live_attempts": 32,
        "enforcement_facts": (
            "side-effect.project-mutation",
            "direct-journal.d0",
        ),
    }
    values.update(overrides)
    return ExecutorCapabilityProfile(**values)  # type: ignore[arg-type]


def _requirements(**overrides: object) -> TaskExecutionRequirements:
    values: dict[str, object] = {
        "schema_version": TASK_EXECUTION_REQUIREMENTS_SCHEMA_VERSION,
        "executor_id": "jiuwenswarm_code_agent.project_code",
        "operation_versions": (("dispatch", "v1"), ("status", "v1")),
        "durability_level": "D0",
        "side_effect_class": "project_mutation",
        "project_serialization": "exclusive",
    }
    values.update(overrides)
    return TaskExecutionRequirements(**values)  # type: ignore[arg-type]


def test_profile_is_frozen_canonical_and_has_a_stable_lowercase_digest() -> None:
    profile = _profile()
    expected = {
        "adapter_id": "adapter.direct-project-code",
        "adapter_protocol_version": "live-voice.direct-project-code.v1",
        "durability_level": "D0",
        "durability_version": "live-voice.direct-d0.v1",
        "enforcement_facts": [
            "direct-journal.d0",
            "side-effect.project-mutation",
        ],
        "executor_id": "jiuwenswarm_code_agent.project_code",
        "max_live_attempts": 32,
        "operation_versions": [
            ["cancel", "v1"],
            ["dispatch", "v1"],
            ["status", "v1"],
        ],
        "profile_id": "profile.direct.d0.v1",
        "project_serialization": "exclusive",
        "schema_version": "live-voice.executor-capability-profile.v1",
    }
    expected_bytes = json.dumps(
        expected,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    expected_digest = hashlib.sha256(expected_bytes).hexdigest()

    assert profile.operation_versions == (
        ("cancel", "v1"),
        ("dispatch", "v1"),
        ("status", "v1"),
    )
    assert profile.enforcement_facts == (
        "direct-journal.d0",
        "side-effect.project-mutation",
    )
    assert profile.to_dict() == expected
    assert profile.canonical_bytes() == expected_bytes
    assert profile.digest_sha256() == expected_digest
    assert profile.digest_sha256().isalnum()
    assert profile.digest_sha256() == profile.digest_sha256().lower()
    assert hash(profile) == hash(ExecutorCapabilityProfile.from_dict(expected))
    with pytest.raises(FrozenInstanceError):
        profile.profile_id = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"schema_version": "live-voice.executor-capability-profile.v2"}, "schema"),
        ({"durability_level": "d1"}, "durability"),
        ({"durability_level": "D3"}, "durability"),
        ({"project_serialization": "shared"}, "serialization"),
        ({"max_live_attempts": True}, "max_live_attempts"),
        ({"max_live_attempts": 0}, "max_live_attempts"),
        ({"max_live_attempts": MAX_SAFE_INTEGER + 1}, "max_live_attempts"),
        (
            {
                "operation_versions": (
                    ("dispatch", "v1"),
                    ("dispatch", "v2"),
                )
            },
            "unique",
        ),
        (
            {
                "enforcement_facts": (
                    "direct-journal.d0",
                    "direct-journal.d0",
                )
            },
            "unique",
        ),
        ({"operation_versions": (("dispatch", "V1"),)}, "version"),
        ({"adapter_id": "C:\\private\\adapter"}, "identifier"),
        ({"profile_id": "api-token.production"}, "sensitive"),
    ],
)
def test_profile_rejects_unknown_versions_duplicates_and_invalid_bounds(
    overrides: dict[str, object],
    match: str,
) -> None:
    with pytest.raises(ValueError, match=match):
        _profile(**overrides)


def test_profile_from_dict_rejects_unknown_or_noncanonical_fields() -> None:
    payload = _profile().to_dict()
    payload["database_path"] = "private.sqlite3"

    with pytest.raises(ValueError, match="fields"):
        ExecutorCapabilityProfile.from_dict(payload)

    malformed = _profile().to_dict()
    malformed["operation_versions"] = [["dispatch", "v1", "unexpected"]]
    with pytest.raises(ValueError, match="operation_versions"):
        ExecutorCapabilityProfile.from_dict(malformed)


def test_requirements_are_frozen_canonical_and_strict() -> None:
    requirements = _requirements(
        operation_versions=(("status", "v1"), ("dispatch", "v1"))
    )
    expected = {
        "durability_level": "D0",
        "executor_id": "jiuwenswarm_code_agent.project_code",
        "operation_versions": [["dispatch", "v1"], ["status", "v1"]],
        "project_serialization": "exclusive",
        "schema_version": "live-voice.task-execution-requirements.v1",
        "side_effect_class": "project_mutation",
    }

    assert requirements.to_dict() == expected
    assert requirements == TaskExecutionRequirements.from_dict(expected)
    assert hash(requirements)
    with pytest.raises(FrozenInstanceError):
        requirements.executor_id = "changed"  # type: ignore[misc]

    unknown = dict(expected)
    unknown["fallback"] = True
    with pytest.raises(ValueError, match="fields"):
        TaskExecutionRequirements.from_dict(unknown)
    with pytest.raises(ValueError, match="schema"):
        _requirements(schema_version="live-voice.task-execution-requirements.v2")
    with pytest.raises(ValueError, match="durability"):
        _requirements(durability_level="d1")
    with pytest.raises(ValueError, match="durability"):
        _requirements(durability_level="D3")
    with pytest.raises(ValueError, match="serialization"):
        _requirements(project_serialization="shared")


def test_selector_filters_exact_compatibility_before_stable_ranking() -> None:
    requirements = _requirements()
    incompatible_first = _profile(
        profile_id="a.incompatible",
        executor_id="another.executor",
    )
    later = _profile(
        profile_id="z.compatible",
        adapter_id="adapter.z",
    )
    selected = _profile(
        profile_id="b.compatible",
        adapter_id="adapter.b",
        operation_versions=(
            ("status", "v1"),
            ("dispatch", "v1"),
            ("cancel", "v1"),
        ),
    )

    first = select_executor(
        (later, incompatible_first, selected),
        requirements,
    )
    second = select_executor(
        (selected, later, incompatible_first),
        requirements,
    )

    assert first == second
    assert first.profile is selected
    assert first.profile_digest == selected.digest_sha256()
    assert first.requirements is requirements
    assert ExecutorSelection.from_dict(first.to_dict()) == first
    assert hash(first)


@pytest.mark.parametrize(
    ("profile_level", "requirement_level", "supported"),
    [
        ("D0", "D0", True),
        ("D1", "D0", True),
        ("D1", "D1", True),
        ("D2", "D0", True),
        ("D2", "D1", True),
        ("D2", "D2", True),
        ("D0", "D1", False),
        ("D0", "D2", False),
        ("D1", "D2", False),
    ],
)
def test_selector_uses_closed_cumulative_durability_order(
    profile_level: str,
    requirement_level: str,
    supported: bool,
) -> None:
    profile = _profile(durability_level=profile_level)
    requirements = _requirements(durability_level=requirement_level)

    if supported:
        selection = select_executor((profile,), requirements)
        assert selection.profile.durability_level == profile_level
        assert selection.requirements.durability_level == requirement_level
    else:
        with pytest.raises(FormalTaskViolation) as rejected:
            select_executor((profile,), requirements)
        assert rejected.value.reason == "EXECUTOR_CAPABILITY_UNAVAILABLE"


@pytest.mark.parametrize(
    ("profile", "requirements"),
    [
        (_profile(executor_id="another.executor"), _requirements()),
        (_profile(), _requirements(operation_versions=(("dispatch", "v2"),))),
        (
            _profile(enforcement_facts=("direct-journal.d0",)),
            _requirements(),
        ),
        (_profile(), _requirements(side_effect_class="read_only")),
    ],
)
def test_selector_returns_one_stable_unsupported_violation_for_mismatch(
    profile: ExecutorCapabilityProfile,
    requirements: TaskExecutionRequirements,
) -> None:
    with pytest.raises(FormalTaskViolation) as rejected:
        select_executor((profile,), requirements)

    assert rejected.value.reason == "EXECUTOR_CAPABILITY_UNAVAILABLE"
    assert rejected.value.code is ErrorCode.CAPABILITY_UNAVAILABLE
    assert str(rejected.value) == (
        "no Executor capability profile satisfies the exact task requirements"
    )


def test_selection_rejects_wrong_digest_incompatible_profile_and_fallback_fields() -> (
    None
):
    profile = _profile()
    requirements = _requirements()

    with pytest.raises(ValueError, match="digest"):
        ExecutorSelection(profile, "0" * 64, requirements)
    with pytest.raises(ValueError, match="compatible"):
        ExecutorSelection(
            profile,
            profile.digest_sha256(),
            replace(requirements, operation_versions=(("dispatch", "v2"),)),
        )

    selection = select_executor((profile,), requirements)
    payload = selection.to_dict()
    payload["fallback_profile"] = _profile(profile_id="fallback").to_dict()
    with pytest.raises(ValueError, match="fields"):
        ExecutorSelection.from_dict(payload)


def test_selector_rejects_duplicate_rank_identity_instead_of_using_input_order() -> (
    None
):
    first = _profile(max_live_attempts=31)
    second = _profile(max_live_attempts=32)

    with pytest.raises(ValueError, match="unique"):
        select_executor((first, second), _requirements())
