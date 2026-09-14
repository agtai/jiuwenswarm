# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Formal ingress reads the real Host catalog without a parallel fallback."""

from copy import deepcopy

import pytest

from jiuwenswarm.common.config import get_default_models
from jiuwenswarm.server import agent_ws_server
from jiuwenswarm.server.runtime.agent_adapter.p3_model_resolution import ServerModelCatalogResolver
from openjiuwen.core.application.tasks.formal_task_models import FormalTaskViolation


def entry(name, **extra):
    return {"model_client_config": {"model_name": name, "api_key": ""},
            "model_config_obj": {}, **extra}


@pytest.mark.parametrize("config,environment,identity", [
    ({"models": {"defaults": [entry("modern")]}}, "env", "modern#0"),
    ({"models": {"default": entry("legacy")}}, "env", "legacy#0"),
    ({}, "environment", "environment#0"),
    ({"models": {"defaults": [entry("primary")], "agentos": [entry("backup")]}}, "env", "primary#0"),
    ({"models": {"defaults": [entry("same"), entry("same", is_default=True)]}}, "env", "same#1"),
])
def test_formal_catalog_uses_host_formats_and_exact_drift_binding(monkeypatch, config, environment, identity):
    monkeypatch.setattr(agent_ws_server, "get_config", lambda: config)
    for key in ("API_KEY", "API_BASE", "MODEL_PROVIDER", "MODEL_ALIAS", "CUSTOM_HEADERS"):
        monkeypatch.setenv(key, "")
    monkeypatch.setenv("MODEL_NAME", environment)
    before = deepcopy(config)
    catalog = agent_ws_server.AgentWebSocketServer._live_voice_p3_model_catalog
    expected = get_default_models(config)
    assert catalog() == expected
    assert config == before
    builds = []
    resolver = ServerModelCatalogResolver(catalog_reader=catalog,
        model_builder=lambda *args: builds.append(args))
    selected = resolver.resolve(None)
    assert selected.identity == identity and builds == []
    with pytest.raises(FormalTaskViolation) as unknown:
        resolver.resolve("not-registered", instantiate=True)
    assert unknown.value.reason == "P3_MODEL_INTENT_UNKNOWN" and builds == []
    config["models"] = {"defaults": [entry("changed")]}
    with pytest.raises(FormalTaskViolation) as drift:
        resolver.resolve(None, expected_identity=selected.identity,
                         expected_config_version=selected.config_version, instantiate=True)
    assert drift.value.reason == "EXECUTOR_MODEL_BINDING_DRIFT" and builds == []


def test_empty_formal_catalog_does_not_invent_react_or_default_model(monkeypatch):
    config = {"react": {"model_name": "legacy-react-only"}}
    monkeypatch.setattr(agent_ws_server, "get_config", lambda: config)
    for key in ("MODEL_NAME", "API_KEY", "API_BASE", "MODEL_PROVIDER", "MODEL_ALIAS", "CUSTOM_HEADERS"):
        monkeypatch.setenv(key, "")
    catalog = agent_ws_server.AgentWebSocketServer._live_voice_p3_model_catalog
    assert catalog() == get_default_models(config)
    builds = []
    resolver = ServerModelCatalogResolver(catalog_reader=catalog,
        model_builder=lambda *args: builds.append(args))
    with pytest.raises(FormalTaskViolation) as unavailable:
        resolver.resolve(None, instantiate=True)
    assert unavailable.value.reason == "P3_MODEL_CATALOG_UNAVAILABLE"
    assert builds == []
