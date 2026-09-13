# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import pytest

from jiuwenswarm.server.live_voice.native_interaction_config import (
    DEFAULT_NATIVE_REALTIME_MODEL,
    DEFAULT_NATIVE_VAD_EAGERNESS,
    INTERACTION_ENGINE_ENV,
    NATIVE_REALTIME_MODEL_ENV,
    NATIVE_VAD_EAGERNESS_ENV,
    NATIVE_MAX_OUTPUT_TOKENS_ENV,
    NATIVE_AUDIO_SPEED_ENV,
    NATIVE_REASONING_EFFORT_ENV,
    InteractionEngineKind,
    NativeInteractionConfigurationError,
    NativeInteractionSelection,
    select_interaction_engine_environment,
)


def test_fresh_environment_selects_native_mini_and_vad300() -> None:
    selection = select_interaction_engine_environment({})

    assert selection.kind is InteractionEngineKind.OPENAI_REALTIME_NATIVE
    assert selection.native_model == "gpt-realtime-2.1-mini"
    assert selection.native_endpoint_mode == "server-vad-300"


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
    monkeypatch.setenv(INTERACTION_ENGINE_ENV, "cascade")

    selection = select_interaction_engine_environment({})

    assert selection.kind is InteractionEngineKind.OPENAI_REALTIME_NATIVE


@pytest.mark.parametrize("eagerness", [None, "auto", "high"])
def test_native_endpoint_selection_preserves_model_and_defaults_to_auto(eagerness):
    environment = {
        INTERACTION_ENGINE_ENV: "openai-realtime-native",
        NATIVE_REALTIME_MODEL_ENV: "gpt-realtime-2",
    }
    if eagerness is not None:
        environment[NATIVE_VAD_EAGERNESS_ENV] = eagerness
    original = environment.copy()
    selection = select_interaction_engine_environment(environment)
    assert selection.kind is InteractionEngineKind.OPENAI_REALTIME_NATIVE
    assert selection.native_model == "gpt-realtime-2"
    assert selection.native_vad_eagerness == (eagerness or "auto")
    assert DEFAULT_NATIVE_VAD_EAGERNESS == "auto"
    assert environment == original


@pytest.mark.parametrize("value", [None, "", " high", "high ", "HIGH", "medium", "low", "high\n", "high\x00", True, 1, [], {}])
def test_native_endpoint_configuration_is_exact_and_fails_closed(value):
    with pytest.raises(NativeInteractionConfigurationError) as raised:
        select_interaction_engine_environment({
            INTERACTION_ENGINE_ENV: "openai-realtime-native",
            NATIVE_VAD_EAGERNESS_ENV: value,
        })
    assert raised.value.reason == "NATIVE_VAD_EAGERNESS_INVALID"


def test_cascade_never_reads_native_endpoint_configuration():
    class CascadeEnvironment(dict):
        def get(self, key, *default):
            if key in {"LIVE_VOICE_NATIVE_ENDPOINT_MODE", NATIVE_VAD_EAGERNESS_ENV, NATIVE_REALTIME_MODEL_ENV, NATIVE_MAX_OUTPUT_TOKENS_ENV, NATIVE_AUDIO_SPEED_ENV, NATIVE_REASONING_EFFORT_ENV}:
                raise AssertionError("Cascade accessed Native-only configuration")
            return super().get(key, *default)

    environment = CascadeEnvironment({INTERACTION_ENGINE_ENV: "cascade"})
    selected = select_interaction_engine_environment(environment)
    assert selected.kind is InteractionEngineKind.CASCADE
    assert selected.native_vad_eagerness is None


@pytest.mark.parametrize("raw,expected", [(None, None), ("provider-default", None), ("minimal", "minimal"), ("low", "low")])
def test_reasoning_effort_preserves_omitted_provider_default(raw, expected):
    env = {INTERACTION_ENGINE_ENV: "openai-realtime-native"}
    if raw is not None:
        env[NATIVE_REASONING_EFFORT_ENV] = raw
    assert select_interaction_engine_environment(env).native_reasoning_effort == expected


@pytest.mark.parametrize("raw", [None, "", "LOW", " low", "high", "low\n", True, 1, [], {}])
def test_reasoning_effort_invalid_environment_fails_closed(raw):
    with pytest.raises(NativeInteractionConfigurationError) as exc:
        select_interaction_engine_environment({INTERACTION_ENGINE_ENV: "openai-realtime-native", NATIVE_REASONING_EFFORT_ENV: raw})
    assert exc.value.reason == "NATIVE_REASONING_EFFORT_INVALID"


def test_endpoint_selection_reads_only_explicit_environment_and_retains_old_constructor(monkeypatch):
    monkeypatch.setenv(NATIVE_VAD_EAGERNESS_ENV, "high")
    selected = select_interaction_engine_environment({INTERACTION_ENGINE_ENV: "openai-realtime-native"})
    assert selected.native_vad_eagerness == "auto"
    assert NativeInteractionSelection(InteractionEngineKind.CASCADE, None).native_vad_eagerness is None


@pytest.mark.parametrize(("raw", "expected"), [(None, "inf"), ("inf", "inf"), ("1", 1), ("2048", 2048), ("4096", 4096)])
def test_native_output_budget_uses_model_maximum_or_explicit_limit(raw, expected):
    environment = {INTERACTION_ENGINE_ENV: "openai-realtime-native"}
    if raw is not None:
        environment[NATIVE_MAX_OUTPUT_TOKENS_ENV] = raw
    selected = select_interaction_engine_environment(environment)
    assert selected.native_max_output_tokens == expected


@pytest.mark.parametrize("raw", [None, True, 1024, "", "INF", " inf", "inf\n", "0", "01", "4097", "32000", "1.5", "١", [], {}])
def test_native_output_budget_rejects_malformed_values(raw):
    with pytest.raises(NativeInteractionConfigurationError) as raised:
        select_interaction_engine_environment({
            INTERACTION_ENGINE_ENV: "openai-realtime-native",
            NATIVE_MAX_OUTPUT_TOKENS_ENV: raw,
        })
    assert raised.value.reason == "NATIVE_MAX_OUTPUT_TOKENS_INVALID"


@pytest.mark.parametrize(("raw", "expected"), [(None, 1.0), ("0.25", 0.25), ("1", 1.0), ("1.5", 1.5)])
def test_native_audio_speed_selection(raw, expected):
    environment = {INTERACTION_ENGINE_ENV: "openai-realtime-native"}
    if raw is not None:
        environment[NATIVE_AUDIO_SPEED_ENV] = raw
    assert select_interaction_engine_environment(environment).native_audio_speed == expected


@pytest.mark.parametrize("raw", [None, True, 1.5, "", " 1.5", "1.5\n", "0.24", "1.51", "2", "nan", "inf", "-1", "١", [], {}])
def test_native_audio_speed_rejects_invalid_environment(raw):
    with pytest.raises(NativeInteractionConfigurationError) as raised:
        select_interaction_engine_environment({
            INTERACTION_ENGINE_ENV: "openai-realtime-native",
            NATIVE_AUDIO_SPEED_ENV: raw,
        })
    assert raised.value.reason == "NATIVE_AUDIO_SPEED_INVALID"


@pytest.mark.parametrize("mode", ["semantic-vad", "server-vad-300", "server-vad-450", "server-vad-600"])
def test_native_fixed_endpoint_presets_are_explicit_and_do_not_read_process_state(mode, monkeypatch):
    monkeypatch.setenv("LIVE_VOICE_NATIVE_ENDPOINT_MODE", "server-vad-450")
    default = select_interaction_engine_environment({INTERACTION_ENGINE_ENV: "openai-realtime-native"})
    assert default.native_endpoint_mode == "server-vad-300"
    selected = select_interaction_engine_environment({INTERACTION_ENGINE_ENV: "openai-realtime-native", "LIVE_VOICE_NATIVE_ENDPOINT_MODE": mode})
    assert selected.native_endpoint_mode == mode


@pytest.mark.parametrize("mode", [None, "", "server_vad", "server-vad-0", "server-vad-299", "server-vad-0300", "server-vad-300\n", "SEMANTIC-VAD", True, 300, [], {}])
def test_native_endpoint_preset_invalid_fails_before_connect(mode):
    with pytest.raises(NativeInteractionConfigurationError) as exc:
        select_interaction_engine_environment({INTERACTION_ENGINE_ENV: "openai-realtime-native", "LIVE_VOICE_NATIVE_ENDPOINT_MODE": mode})
    assert exc.value.reason == "NATIVE_ENDPOINT_MODE_INVALID"
