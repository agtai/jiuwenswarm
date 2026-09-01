# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import pytest

from jiuwenswarm.server.live_voice.native_interaction_config import (
    DEFAULT_NATIVE_REALTIME_MODEL,
    INTERACTION_ENGINE_ENV,
    NATIVE_REALTIME_MODEL_ENV,
    InteractionEngineKind,
    NativeInteractionConfigurationError,
    select_interaction_engine_environment,
)


def test_cascade_is_the_default_and_does_not_require_openai_secret() -> None:
    selection = select_interaction_engine_environment({})

    assert selection.kind is InteractionEngineKind.CASCADE
    assert selection.native_model is None


def test_explicit_cascade_ignores_native_model_configuration() -> None:
    selection = select_interaction_engine_environment(
        {
            INTERACTION_ENGINE_ENV: "cascade",
            NATIVE_REALTIME_MODEL_ENV: "not-used-by-cascade",
        }
    )

    assert selection.kind is InteractionEngineKind.CASCADE
    assert selection.native_model is None


def test_native_uses_one_default_model_and_accepts_override() -> None:
    default = select_interaction_engine_environment(
        {INTERACTION_ENGINE_ENV: "openai-realtime-native"}
    )
    override = select_interaction_engine_environment(
        {
            INTERACTION_ENGINE_ENV: "openai-realtime-native",
            NATIVE_REALTIME_MODEL_ENV: "gpt-realtime-custom",
        }
    )

    assert default.kind is InteractionEngineKind.OPENAI_REALTIME_NATIVE
    assert default.native_model == DEFAULT_NATIVE_REALTIME_MODEL
    assert DEFAULT_NATIVE_REALTIME_MODEL == "gpt-realtime-2.1-mini"
    assert override.native_model == "gpt-realtime-custom"


@pytest.mark.parametrize(
    ("environ", "reason"),
    [
        ({INTERACTION_ENGINE_ENV: "native-ish"}, "INTERACTION_ENGINE_UNSUPPORTED"),
        ({INTERACTION_ENGINE_ENV: " cascade"}, "INTERACTION_ENGINE_INVALID"),
        ({INTERACTION_ENGINE_ENV: "native\nother"}, "INTERACTION_ENGINE_INVALID"),
        ({INTERACTION_ENGINE_ENV: "n" * 257}, "INTERACTION_ENGINE_INVALID"),
        (
            {
                INTERACTION_ENGINE_ENV: "openai-realtime-native",
                NATIVE_REALTIME_MODEL_ENV: "",
            },
            "NATIVE_REALTIME_MODEL_INVALID",
        ),
        (
            {
                INTERACTION_ENGINE_ENV: "openai-realtime-native",
                NATIVE_REALTIME_MODEL_ENV: " model",
            },
            "NATIVE_REALTIME_MODEL_INVALID",
        ),
        (
            {
                INTERACTION_ENGINE_ENV: "openai-realtime-native",
                NATIVE_REALTIME_MODEL_ENV: "model\nother",
            },
            "NATIVE_REALTIME_MODEL_INVALID",
        ),
        (
            {
                INTERACTION_ENGINE_ENV: "openai-realtime-native",
                NATIVE_REALTIME_MODEL_ENV: "model\u2028other",
            },
            "NATIVE_REALTIME_MODEL_INVALID",
        ),
        (
            {
                INTERACTION_ENGINE_ENV: "openai-realtime-native",
                NATIVE_REALTIME_MODEL_ENV: "m" * 257,
            },
            "NATIVE_REALTIME_MODEL_INVALID",
        ),
    ],
)
def test_invalid_selection_fails_closed_without_cascade_fallback(
    environ: dict[str, str], reason: str
) -> None:
    with pytest.raises(NativeInteractionConfigurationError) as raised:
        select_interaction_engine_environment(environ)

    assert raised.value.reason == reason


def test_selection_reads_only_passed_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(INTERACTION_ENGINE_ENV, "openai-realtime-native")

    selection = select_interaction_engine_environment({})

    assert selection.kind is InteractionEngineKind.CASCADE
