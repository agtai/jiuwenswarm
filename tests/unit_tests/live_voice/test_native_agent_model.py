# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from jiuwenswarm.server.live_voice.formal_task_models import FormalTaskViolation
from jiuwenswarm.server.live_voice.native_agent_model import (
    AGENT_MODEL_SELECTION_VERSION,
    NativeAgentModelSelection,
    parse_native_agent_model_confirmation,
    parse_native_agent_model_selection,
    resolve_native_agent_model,
)
from jiuwenswarm.server.live_voice.p3_authenticated_composition import (
    P3_PRODUCT_AUTHORITY_OPERATIONS,
)
from jiuwenswarm.server.live_voice.p3_model_resolution import ServerModelCatalogResolver
from jiuwenswarm.server.live_voice.p3_production_intent_composition import (
    production_model_binding_fingerprint,
)
from jiuwenswarm.server.live_voice.project_code_executor import (
    DirectProjectCodeExecutorAdapter,
)
from tests.unit_tests.live_voice.test_p3_authenticated_composition import (
    NOW,
    TOKEN,
    _confirmed_production_resolution,
    _create_params,
    _harness,
    _issue_confirmation,
    _scope,
    _stop_test_reconciliation_worker,
    _store_counts,
)


def _catalog():
    return [
        {
            "alias": "Default",
            "model_client_config": {"model_name": "default", "api_key": "PRIVATE_KEY"},
            "model_config_obj": {"temperature": 0.1},
            "is_default": True,
        },
        {
            "alias": "Selected Agent",
            "model_client_config": {"model_name": "selected", "api_key": "PRIVATE_KEY"},
            "model_config_obj": {"temperature": 0.2},
            "is_default": True,
        },
    ]


def _resolver(catalog, builds):
    return ServerModelCatalogResolver(
        catalog_reader=lambda: catalog,
        model_builder=lambda client, config: builds.append((client, config)),
    )


def test_new_activation_selection_is_closed_bounded_and_secret_free():
    catalog, builds = _catalog(), []
    resolver = _resolver(catalog, builds)
    selection = parse_native_agent_model_selection(
        {
            "contract_version": AGENT_MODEL_SELECTION_VERSION,
            "model_name": "Selected Agent",
        }
    )
    confirmed = resolve_native_agent_model(resolver, selection)
    assert confirmed.model_name == "Selected Agent"
    assert confirmed.model_identity == "selected#0"
    assert len(confirmed.model_config_version) == 64
    assert (
        parse_native_agent_model_confirmation(
            json.loads(json.dumps(confirmed.to_dict()))
        )
        == confirmed
    )
    assert "PRIVATE" not in repr(confirmed) + json.dumps(confirmed.to_dict())
    with pytest.raises(FrozenInstanceError):
        confirmed.model_name = "Default"
    default = resolve_native_agent_model(resolver)
    assert default.model_name == "default" and default.model_identity == "default#0"
    assert builds == []


@pytest.mark.parametrize(
    "value",
    [
        None,
        {},
        [],
        {"contract_version": "wrong", "model_name": "Default"},
        {
            "contract_version": AGENT_MODEL_SELECTION_VERSION,
            "model_name": "Default",
            "api_key": "PRIVATE",
        },
        *(
            {"contract_version": AGENT_MODEL_SELECTION_VERSION, "model_name": value}
            for value in (
                "",
                " Default",
                "Default\n",
                "x" * 257,
                "汉" * 86,
                "\ud800",
                False,
            )
        ),
    ],
)
def test_selection_rejects_unclosed_invalid_inputs_without_model_effects(value):
    with pytest.raises(FormalTaskViolation) as error:
        parse_native_agent_model_selection(value)
    assert error.value.reason == "INVALID_NATIVE_AGENT_MODEL_SELECTION"
    assert "PRIVATE" not in str(error.value)


@pytest.mark.parametrize("model_name", ["x" * 256, "汉" * 85 + "x"])
def test_selection_preserves_maximum_utf8_text(model_name):
    payload = {
        "contract_version": AGENT_MODEL_SELECTION_VERSION,
        "model_name": model_name,
    }
    assert parse_native_agent_model_selection(payload).to_dict() == payload


@pytest.mark.parametrize(
    "changes",
    [
        {"contract_version": "wrong"},
        {"model_identity": ""},
        {"model_config_version": None},
        {"model_identity": "x" * 257},
        {"model_identity": "selected#0\n"},
        {"api_key": "PRIVATE"},
    ],
)
def test_confirmation_rejects_incomplete_or_unclosed_fields(changes):
    payload = {
        "contract_version": AGENT_MODEL_SELECTION_VERSION,
        "model_name": "Selected Agent",
        "model_identity": "selected#0",
        "model_config_version": "a" * 64,
        **changes,
    }
    with pytest.raises(FormalTaskViolation):
        parse_native_agent_model_confirmation(payload)
    payload.pop("model_identity")
    with pytest.raises(FormalTaskViolation):
        parse_native_agent_model_confirmation(payload)


def test_selection_unknown_ambiguous_and_catalog_drift_do_not_construct_models():
    catalog, builds = _catalog(), []
    resolver = _resolver(catalog, builds)
    with pytest.raises(FormalTaskViolation, match="available model"):
        resolve_native_agent_model(
            resolver,
            NativeAgentModelSelection(AGENT_MODEL_SELECTION_VERSION, "missing"),
        )
    catalog.append({**catalog[1]})
    with pytest.raises(FormalTaskViolation) as error:
        resolve_native_agent_model(
            resolver,
            NativeAgentModelSelection(AGENT_MODEL_SELECTION_VERSION, "Selected Agent"),
        )
    assert error.value.reason == "P3_MODEL_INTENT_AMBIGUOUS"
    catalog.pop()
    confirmed = resolve_native_agent_model(
        resolver,
        NativeAgentModelSelection(AGENT_MODEL_SELECTION_VERSION, "Selected Agent"),
    )
    catalog[1]["model_config_obj"]["temperature"] = 0.5
    with pytest.raises(FormalTaskViolation) as error:
        resolver.resolve(
            confirmed.model_identity,
            expected_identity=confirmed.model_identity,
            expected_config_version=confirmed.model_config_version,
        )
    assert error.value.reason == "EXECUTOR_MODEL_BINDING_DRIFT"
    assert builds == []


async def _model_harness(tmp_path: Path):
    harness = _harness(
        tmp_path,
        allowed_operations=P3_PRODUCT_AUTHORITY_OPERATIONS | frozenset({"agent.chat"}),
        executor_profiles=(DirectProjectCodeExecutorAdapter.capability_profile(),),
    )
    catalog, builds = _catalog(), []
    resolver = _resolver(catalog, builds)
    confirmed = resolve_native_agent_model(
        resolver,
        NativeAgentModelSelection(AGENT_MODEL_SELECTION_VERSION, "Selected Agent"),
    )
    harness.composition._model_resolver = resolver
    # Existing confirmation fixture publishes the selected model fingerprint.
    harness.models.identity = confirmed.model_identity
    harness.models.config_version = confirmed.model_config_version
    await harness.composition.start()
    await _stop_test_reconciliation_worker(harness.composition)
    authority = harness.composition.prepare_native_activation_authority(
        bearer_token=TOKEN,
        session_id="session-1",
        correlation_id="native-model",
        model_identity=confirmed.model_identity,
        model_config_version=confirmed.model_config_version,
    )
    return harness, catalog, builds, confirmed, authority


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize(
    "fault", [None, "catalog_drift", "foreign_scope", "model_override"]
)
async def test_native_task_create_persists_selected_model_and_rejects_drift_with_zero_effects(
    tmp_path, legacy, fault
):
    harness, catalog, builds, confirmed, authority = await _model_harness(tmp_path)
    try:
        prepared = harness.composition.prepare_production_intent_authority(
            bearer_token=None,
            operation="task.create",
            session_id="session-1",
            native_authority=authority,
        )
        expected = production_model_binding_fingerprint(
            {
                "model_identity": confirmed.model_identity,
                "model_config_version": confirmed.model_config_version,
            }
        )
        assert (
            prepared.reader.list_visible_tasks(
                _scope()
            ).collection_model_binding_fingerprint
            == expected
        )
        before = _store_counts(harness.database)
        params = _create_params("native-model-create")
        params.pop("model_intent")
        _issue_confirmation(harness, params, operation="task.create")
        resolution, origin, consumer = _confirmed_production_resolution(
            harness,
            tmp_path,
            operation="task.create",
            target=None,
            arguments={"name": "Model bound", "instruction": "Use selected Agent"},
            identity="native-model",
            now=NOW,
            expires_at="2026-08-05T12:02:00Z",
        )
        if fault == "catalog_drift":
            catalog[1]["model_config_obj"]["temperature"] = 0.5
            with pytest.raises(FormalTaskViolation) as error:
                harness.composition.prepare_production_intent_authority(
                    bearer_token=None,
                    operation="task.create",
                    session_id="session-1",
                    native_authority=authority,
                )
            assert error.value.reason == "EXECUTOR_MODEL_BINDING_DRIFT"
        elif fault == "foreign_scope":
            authority = replace(
                authority,
                session_id="session-2",
                scope=_scope(session_id="session-2"),
                context=replace(
                    authority.context, scope=_scope(session_id="session-2")
                ),
            )
        elif fault == "model_override":
            if legacy:
                params["model_intent"] = "Default"
            else:
                authority = replace(authority, model_identity="default#0")
        if legacy:
            result = await harness.composition.handle_native(
                authority,
                operation="task.create",
                params=params,
                request_id="native-model-request",
                session_id="session-1",
            )
        else:
            result = await harness.composition.handle_production_resolution(
                resolution=resolution,
                bearer_token=None,
                native_authority=authority,
                request_id="native-model-request",
                session_id="session-1",
                correlation_id="native-model",
                origin_authority=origin,
                confirmation_consumer=consumer,
                current_background_session_id="session-1",
            )
        if fault is None:
            assert result.ok, result.payload
            task = harness.composition._core.store.get_task(
                result.payload["result"]["task_id"], _scope()
            )
            assert (
                dict(task.spec.attributes)["model_identity"] == confirmed.model_identity
            )
            assert (
                dict(task.spec.attributes)["model_config_version"]
                == confirmed.model_config_version
            )
        else:
            assert not result.ok
            reason = result.payload["error"]["reason"]
            if fault == "catalog_drift" or (fault == "model_override" and legacy):
                assert reason == "EXECUTOR_MODEL_BINDING_DRIFT"
            elif fault == "foreign_scope":
                assert reason == "NATIVE_P3_ACTIVATION_AUTHORITY_MISMATCH"
            else:
                assert reason == "PRODUCTION_TASK_AUTHORITY_CHANGED"
            assert _store_counts(harness.database) == before
        assert builds == []
        assert (
            harness.executor.dispatches
            == harness.executor.cancels
            == harness.executor.adjustments
            == []
        )
    finally:
        await harness.composition.stop()


@pytest.mark.asyncio
async def test_native_unbound_and_cascade_defaults_remain_unchanged(tmp_path):
    harness, catalog, builds, confirmed, authority = await _model_harness(tmp_path)
    try:
        for native in [
            None,
            replace(authority, model_identity=None, model_config_version=None),
        ]:
            prepared = harness.composition.prepare_production_intent_authority(
                bearer_token=TOKEN if native is None else None,
                operation="task.create",
                session_id="session-1",
                native_authority=native,
            )
            default = harness.composition._model_resolver.resolve(None)
            expected = production_model_binding_fingerprint(
                {
                    "model_identity": default.identity,
                    "model_config_version": default.config_version,
                }
            )
            assert (
                prepared.reader.list_visible_tasks(
                    _scope()
                ).collection_model_binding_fingerprint
                == expected
            )
        for changes in [
            {"model_identity": None},
            {"model_config_version": None},
            {"model_identity": ""},
            {"model_identity": False},
        ]:
            with pytest.raises(FormalTaskViolation):
                replace(authority, **changes)
        assert builds == []
    finally:
        await harness.composition.stop()
