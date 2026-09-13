# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Native's server-owned read window preserves exact Store and auth fences."""

from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import sqlite3

import pytest

from jiuwenswarm.server.live_voice.formal_task_models import FormalTaskViolation
from jiuwenswarm.server.live_voice.p3_authenticated_composition import (
    P3_PRODUCT_AUTHORITY_OPERATIONS,
)
from jiuwenswarm.server.live_voice.p3_production_intent_composition import (
    CallLocalProductionOriginAuthority,
    StoreProductionTaskAuthorityReader,
)
from jiuwenswarm.server.live_voice.production_task_classifier import (
    ProductionTaskIntentClassifier,
)
from jiuwenswarm.server.live_voice.production_task_intent import (
    BoundedClarificationOwner,
    ProductionIntentOrigin,
    ProductionTaskIntentRequest,
    ProductionTaskPolicyOutcome,
    build_production_origin_binding,
)
from jiuwenswarm.server.live_voice.task_store import SqliteTaskStore
from jiuwenswarm.server.live_voice.voice_task_bridge import VoiceTaskBridge
from tests.unit_tests.live_voice.test_p3_authenticated_composition import (
    TOKEN,
    _NoProductionConfirmation,
    _harness,
    _stop_test_reconciliation_worker,
)
from tests.unit_tests.live_voice.test_p3_production_intent_composition import (
    EXPIRY,
    NOW,
    SCOPE,
    _context,
    _seed_selected_task,
)


def _database_facts(database: Path) -> tuple[str, ...]:
    with sqlite3.connect(database) as connection:
        return tuple(connection.iterdump())


def _reader(store, **kwargs):
    return StoreProductionTaskAuthorityReader(
        store=store, principal_id=SCOPE.subject_id, scope=SCOPE, **kwargs
    )


def test_native_window_reads_100_complete_facts_but_rejects_101(tmp_path):
    database = tmp_path / "native-reader.sqlite3"
    store = SqliteTaskStore(database)
    tasks = {
        _seed_selected_task(store, tmp_path, suffix=str(index))[0]
        for index in range(100)
    }
    before = _database_facts(database)
    reader = _reader(store, visible_task_capacity=100)
    visible = reader.list_visible_tasks(SCOPE)
    assert {item.task_id for item in visible.tasks} == tasks
    assert _database_facts(database) == before

    with pytest.raises(FormalTaskViolation) as legacy:
        _reader(store).list_visible_tasks(SCOPE)
    assert legacy.value.reason == "PRODUCTION_TASK_AUTHORITY_CAPACITY_EXCEEDED"
    with pytest.raises(FormalTaskViolation) as foreign:
        reader.list_visible_tasks(replace(SCOPE, session_id="other-session"))
    assert foreign.value.reason == "PRODUCTION_TASK_AUTHORITY_SCOPE_MISMATCH"
    assert _database_facts(database) == before

    _seed_selected_task(store, tmp_path, suffix="overflow")
    before = _database_facts(database)
    with pytest.raises(FormalTaskViolation) as overflow:
        reader.list_visible_tasks(SCOPE)
    assert overflow.value.reason == "PRODUCTION_TASK_AUTHORITY_CAPACITY_EXCEEDED"
    assert _database_facts(database) == before


@pytest.mark.parametrize("capacity", [0, 101, True, 1.0, "100", None])
def test_native_reader_rejects_invalid_capacity_before_store_read(tmp_path, capacity):
    database = tmp_path / "native-invalid-capacity.sqlite3"
    store = SqliteTaskStore(database)
    before = _database_facts(database)
    with pytest.raises(ValueError, match="INVALID_PRODUCTION_TASK_AUTHORITY_CAPACITY"):
        _reader(store, visible_task_capacity=capacity)
    assert _database_facts(database) == before


def _resolution(reader, *, operation, target, stem):
    arguments = (
        {"query_kind": "list", "limit": 100}
        if operation == "task.list"
        else {"query_kind": "get"}
    )
    proposal = ProductionTaskIntentClassifier().parse_structured(
        {"operation": operation, "target": target, "arguments": arguments},
        committed=True,
        source_confidence=1.0,
    )
    request = ProductionTaskIntentRequest(
        origin=ProductionIntentOrigin.STRUCTURED,
        scope=SCOPE,
        command_id=f"command-{stem}",
        proposal=proposal,
        source_id=f"structured-{stem}",
    )
    origin = CallLocalProductionOriginAuthority(
        expected_binding=build_production_origin_binding(request)
    )
    resolution = VoiceTaskBridge().resolve_production(
        request,
        reader,
        origin,
        _NoProductionConfirmation(),
        BoundedClarificationOwner(
            capacity=8, per_subject_capacity=2, boot_id=f"boot-{stem}"
        ),
    )
    assert resolution.outcome is ProductionTaskPolicyOutcome.PROPOSED
    return resolution, origin


@pytest.mark.asyncio
async def test_native_window_survives_preparation_and_final_resolution(tmp_path):
    harness = _harness(
        tmp_path,
        contexts={SCOPE.session_id: _context(tmp_path)},
        expires_at=EXPIRY,
        allowed_operations=P3_PRODUCT_AUTHORITY_OPERATIONS | frozenset({"agent.chat"}),
        clock=lambda: NOW,
    )
    composition = harness.composition
    await composition.start()
    await _stop_test_reconciliation_worker(composition)
    try:
        task_ids = {
            _seed_selected_task(composition._core.store, tmp_path, suffix=str(index))[0]
            for index in range(33)
        }
        legacy_native = composition.prepare_native_activation_authority(
            bearer_token=TOKEN,
            session_id=SCOPE.session_id,
            correlation_id="native-capacity",
        )
        assert legacy_native.task_read_capacity == 32
        native = replace(legacy_native, task_read_capacity=100)
        with pytest.raises(FrozenInstanceError):
            native.task_read_capacity = 32
        for invalid in (0, 101, True, 1.0, "100", None):
            with pytest.raises(FormalTaskViolation) as error:
                replace(native, task_read_capacity=invalid)
            assert error.value.reason == "INVALID_NATIVE_P3_ACTIVATION_AUTHORITY"

        before = _database_facts(harness.database)
        for authority in (None, legacy_native):
            prepared = composition.prepare_production_intent_authority(
                bearer_token=TOKEN,
                operation="task.list",
                session_id=SCOPE.session_id,
                native_authority=authority,
            )
            with pytest.raises(FormalTaskViolation) as overflow:
                prepared.reader.list_visible_tasks(SCOPE)
            assert (
                overflow.value.reason == "PRODUCTION_TASK_AUTHORITY_CAPACITY_EXCEEDED"
            )

        prepared = composition.prepare_production_intent_authority(
            bearer_token=None,
            operation="task.list",
            session_id=SCOPE.session_id,
            native_authority=native,
        )
        visible = prepared.reader.list_visible_tasks(SCOPE)
        assert len(visible.tasks) == 33
        target = visible.tasks[32].task_id

        for index, authority in enumerate((None, legacy_native, native)):
            resolution, origin = _resolution(
                prepared.reader,
                operation="task.get",
                target=target,
                stem=f"get-{index}",
            )
            routed = await composition.handle_production_resolution(
                resolution=resolution,
                bearer_token=TOKEN if authority is None else None,
                request_id=f"request-get-{index}",
                session_id=SCOPE.session_id,
                correlation_id=f"correlation-get-{index}",
                origin_authority=origin,
                native_authority=authority,
            )
            if authority is native:
                assert routed.ok, routed.payload
                assert routed.payload["result"]["task"]["task_id"] == target
            else:
                assert not routed.ok
                assert routed.payload["error"]["reason"] == (
                    "PRODUCTION_TASK_AUTHORITY_CAPACITY_EXCEEDED"
                )

        for drift in (False, True):
            resolution, origin = _resolution(
                prepared.reader,
                operation="task.list",
                target=None,
                stem=f"list-{drift}",
            )
            if drift:
                harness.authority.contexts[SCOPE.session_id] = replace(
                    native.context, uri=(tmp_path / "other-project").resolve().as_uri()
                )
            routed = await composition.handle_production_resolution(
                resolution=resolution,
                bearer_token=None,
                request_id=f"request-list-{drift}",
                session_id=SCOPE.session_id,
                correlation_id=f"correlation-list-{drift}",
                origin_authority=origin,
                native_authority=native,
            )
            if drift:
                assert not routed.ok
                assert routed.payload["error"]["reason"] == (
                    "EXECUTION_CONTEXT_SCOPE_MISMATCH"
                )
            else:
                assert routed.ok, routed.payload
                assert {
                    item["task_id"] for item in routed.payload["result"]["tasks"]
                } == task_ids
        assert _database_facts(harness.database) == before
        assert not harness.executor.dispatches
        assert not harness.executor.cancels
        assert not harness.executor.adjustments
    finally:
        await composition.stop()
