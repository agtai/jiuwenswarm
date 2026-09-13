# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, replace

import pytest

from jiuwenswarm.server.live_voice.live_voice_configuration_declaration import (
    LIVE_VOICE_CONFIGURATION_CONTRACT_VERSION,
    AuthenticationMode,
    CapabilityConfigurationConflict,
    ConfigurationDeclarationReason,
    ConfigurationReplayReason,
    DurabilityLevel,
    ExecutorCapability,
    LiveVoiceCapability,
    LiveVoiceCapabilityDeclaration,
    LiveVoiceDeploymentProfile,
    ProviderCapability,
    ValidatedAuthenticationConfiguration,
    ValidatedExecutorConfiguration,
    ValidatedLiveVoiceConfiguration,
    ValidatedProviderConfiguration,
    declare_live_voice_capabilities,
    evaluate_live_voice_capability_declaration_replay,
)


_DIGEST = "a" * 64


def _ordered(values: set) -> tuple:
    return tuple(sorted(values, key=lambda value: value.value))


def _ordinary() -> ValidatedLiveVoiceConfiguration:
    return ValidatedLiveVoiceConfiguration(
        contract_version=LIVE_VOICE_CONFIGURATION_CONTRACT_VERSION,
        configuration_id="config-ordinary",
        configuration_digest=_DIGEST,
        profile=LiveVoiceDeploymentProfile.ORDINARY_PRODUCTION,
        enabled=False,
        ordinary_production_default_off=True,
        authentication=None,
        executor=None,
        providers=(),
        capabilities=(),
    )


def _formal() -> ValidatedLiveVoiceConfiguration:
    executor = ValidatedExecutorConfiguration(
        executor_id="executor-1",
        adapter_id="adapter-1",
        durability_level=DurabilityLevel.D2,
        capabilities=_ordered(set(ExecutorCapability)),
        validation_receipt_id="executor-receipt",
        configuration_digest=_DIGEST,
    )
    provider = ValidatedProviderConfiguration(
        provider_id="provider-1",
        capabilities=(ProviderCapability.SPEECH_RECOGNITION_STREAMING,),
        validation_receipt_id="provider-receipt",
        configuration_digest=_DIGEST,
    )
    return ValidatedLiveVoiceConfiguration(
        contract_version=LIVE_VOICE_CONFIGURATION_CONTRACT_VERSION,
        configuration_id="config-formal",
        configuration_digest=_DIGEST,
        profile=LiveVoiceDeploymentProfile.FORMAL_LIVE_VOICE,
        enabled=True,
        ordinary_production_default_off=True,
        authentication=ValidatedAuthenticationConfiguration(
            mode=AuthenticationMode.SCOPED_BEARER,
            validation_receipt_id="auth-receipt",
            scope_digest=_DIGEST,
        ),
        executor=executor,
        providers=(provider,),
        capabilities=_ordered(
            {
                LiveVoiceCapability.AUTHENTICATED,
                LiveVoiceCapability.EXECUTOR_D2,
                LiveVoiceCapability.FORMAL_WEB,
                LiveVoiceCapability.SPEECH_RECOGNITION_STREAMING,
                LiveVoiceCapability.TASK_MUTATION,
                LiveVoiceCapability.TASK_QUERY,
            }
        ),
    )


def _assert_zero_effect(result: object) -> None:
    for name in (
        "environment_read",
        "provider_started",
        "backend_called",
        "worker_started",
        "network_changed",
        "persistence_changed",
        "authentication_downgraded",
        "durability_downgraded",
        "business_result_changed",
        "agent_effect",
        "tool_effect",
        "task_effect",
        "audio_effect",
        "history_effect",
        "authorization_granted",
    ):
        assert getattr(result, name) is False


def test_ordinary_production_stays_default_off_and_effect_free() -> None:
    result = declare_live_voice_capabilities(_ordinary(), enabled=True)
    assert result.ready is True
    assert result.reason is ConfigurationDeclarationReason.DECLARATION_READY
    assert result.declaration.active is False
    assert result.declaration.capabilities == ()
    assert result.declaration.authentication_mode is AuthenticationMode.DISABLED
    assert result.declaration.durability_level is None
    assert result.declaration.authoritative is False
    assert result.declaration.authorization_granted is False
    _assert_zero_effect(result)


def test_formal_configuration_produces_exact_capabilities_without_environment_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "os.getenv",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("environment read")
        ),
    )
    result = declare_live_voice_capabilities(_formal(), enabled=True)
    assert result.ready is True
    assert result.declaration.active is True
    assert result.declaration.durability_level is DurabilityLevel.D2
    assert result.declaration.provider_ids == ("provider-1",)
    assert result.declaration.validation_receipt_ids == (
        "auth-receipt",
        "executor-receipt",
        "provider-receipt",
    )
    assert set(result.declaration.capabilities) == set(_formal().capabilities)
    assert result.declaration.source_configuration == _formal()
    assert len(result.declaration.source_configuration_fingerprint) == 64
    _assert_zero_effect(result)
    with pytest.raises(FrozenInstanceError):
        result.declaration.active = False  # type: ignore[misc]


def test_impossible_auth_durability_and_provider_claims_fail_closed() -> None:
    with pytest.raises(CapabilityConfigurationConflict):
        replace(
            _formal(),
            authentication=ValidatedAuthenticationConfiguration(
                AuthenticationMode.DISABLED,
                None,
                None,
            ),
        )

    with pytest.raises(CapabilityConfigurationConflict):
        ValidatedExecutorConfiguration(
            executor_id="executor-1",
            adapter_id="adapter-1",
            durability_level=DurabilityLevel.D2,
            capabilities=_ordered({ExecutorCapability.DISPATCH}),
            validation_receipt_id="receipt-1",
            configuration_digest=_DIGEST,
        )

    with pytest.raises(CapabilityConfigurationConflict):
        replace(
            _formal(),
            capabilities=_ordered(
                set(_formal().capabilities)
                - {LiveVoiceCapability.SPEECH_RECOGNITION_STREAMING}
            ),
        )

    formal = _formal()
    object.__setattr__(
        formal,
        "capabilities",
        _ordered(set(formal.capabilities) - {LiveVoiceCapability.EXECUTOR_D2}),
    )
    result = declare_live_voice_capabilities(formal, enabled=True)
    assert result.reason is ConfigurationDeclarationReason.CAPABILITY_CONFLICT
    _assert_zero_effect(result)


def test_private_forgery_is_rejected_without_echo_or_effect() -> None:
    formal = _formal()
    object.__setattr__(formal.providers[0], "provider_id", "transcript-secret")
    result = declare_live_voice_capabilities(formal, enabled=True)
    assert result.reason is ConfigurationDeclarationReason.PRIVATE_CONTENT_REJECTED
    assert result.declaration is None
    _assert_zero_effect(result)


def test_feature_off_short_circuits_before_touching_input() -> None:
    class Poison:
        def __getattribute__(self, name: str) -> object:
            raise AssertionError(name)

    result = declare_live_voice_capabilities(Poison(), enabled=False)
    assert result.reason is ConfigurationDeclarationReason.FEATURE_DISABLED
    _assert_zero_effect(result)


@pytest.mark.parametrize(
    "field_name",
    ["authentication", "executor", "providers", "capabilities"],
)
def test_nested_duck_configuration_rejects_before_getter_effects(
    field_name: str,
) -> None:
    class Poison:
        def __getattribute__(self, name: str) -> object:
            raise AssertionError(name)

    configuration = _formal()
    forged: object = (Poison(),) if field_name == "providers" else Poison()
    object.__setattr__(configuration, field_name, forged)
    result = declare_live_voice_capabilities(configuration, enabled=True)
    assert result.reason is ConfigurationDeclarationReason.INVALID_CONFIGURATION
    _assert_zero_effect(result)


def test_nested_provider_capability_duck_rejects_before_getter_effects() -> None:
    class Poison:
        def __iter__(self) -> object:
            raise AssertionError("iterated")

    configuration = _formal()
    object.__setattr__(configuration.providers[0], "capabilities", Poison())
    result = declare_live_voice_capabilities(configuration, enabled=True)
    assert result.reason is ConfigurationDeclarationReason.INVALID_CONFIGURATION
    _assert_zero_effect(result)


@pytest.mark.parametrize(
    ("field_name", "forged_value"),
    [
        ("provider_ids", ("provider-forged",)),
        ("validation_receipt_ids", ("receipt-forged",)),
        ("authentication_mode", AuthenticationMode.DISABLED),
        ("durability_level", DurabilityLevel.D1),
        (
            "capabilities",
            _ordered(
                {
                    LiveVoiceCapability.AUTHENTICATED,
                    LiveVoiceCapability.EXECUTOR_D2,
                    LiveVoiceCapability.FORMAL_WEB,
                    LiveVoiceCapability.TASK_MUTATION,
                    LiveVoiceCapability.TASK_QUERY,
                }
            ),
        ),
    ],
)
def test_direct_declaration_cannot_forge_projection_mappings(
    field_name: str,
    forged_value: object,
) -> None:
    declaration = declare_live_voice_capabilities(
        _formal(),
        enabled=True,
    ).declaration
    payload = {
        field.name: getattr(declaration, field.name)
        for field in fields(LiveVoiceCapabilityDeclaration)
        if field.init
    }
    payload[field_name] = forged_value
    with pytest.raises(ValueError, match="exactly project"):
        LiveVoiceCapabilityDeclaration(**payload)


@pytest.mark.parametrize("authority_field", ["authoritative", "authorization_granted"])
def test_declaration_can_never_be_constructed_as_authority(
    authority_field: str,
) -> None:
    declaration = declare_live_voice_capabilities(_formal(), enabled=True).declaration
    payload = {
        field.name: getattr(declaration, field.name)
        for field in fields(LiveVoiceCapabilityDeclaration)
        if field.init
    }
    payload[authority_field] = True
    with pytest.raises(ValueError, match="cannot claim authorization"):
        LiveVoiceCapabilityDeclaration(**payload)


def test_configuration_replay_detects_same_identity_capability_conflict() -> None:
    original = declare_live_voice_capabilities(_formal(), enabled=True).declaration
    alternate_provider = ValidatedProviderConfiguration(
        provider_id="provider-1",
        capabilities=(ProviderCapability.TELEMETRY_EXPORT,),
        validation_receipt_id="provider-receipt",
        configuration_digest=_DIGEST,
    )
    alternate_configuration = replace(
        _formal(),
        providers=(alternate_provider,),
        capabilities=_ordered(
            {
                LiveVoiceCapability.AUTHENTICATED,
                LiveVoiceCapability.EXECUTOR_D2,
                LiveVoiceCapability.FORMAL_WEB,
                LiveVoiceCapability.TASK_MUTATION,
                LiveVoiceCapability.TASK_QUERY,
                LiveVoiceCapability.TELEMETRY_EXPORT,
            }
        ),
    )
    replay = declare_live_voice_capabilities(
        alternate_configuration,
        enabled=True,
    ).declaration

    exact = evaluate_live_voice_capability_declaration_replay(
        original,
        original,
        enabled=True,
    )
    assert exact.reason is ConfigurationReplayReason.IDEMPOTENT
    assert exact.accepted is True
    _assert_zero_effect(exact)

    conflict = evaluate_live_voice_capability_declaration_replay(
        original,
        replay,
        enabled=True,
    )
    assert conflict.reason is ConfigurationReplayReason.CONFIGURATION_CONFLICT
    assert conflict.accepted is False
    _assert_zero_effect(conflict)

    different_identity = declare_live_voice_capabilities(
        replace(_formal(), configuration_id="config-formal-2"),
        enabled=True,
    ).declaration
    mismatch = evaluate_live_voice_capability_declaration_replay(
        original,
        different_identity,
        enabled=True,
    )
    assert mismatch.reason is ConfigurationReplayReason.IDENTITY_MISMATCH
    _assert_zero_effect(mismatch)


def test_configuration_bounds_and_ordinary_pii_are_fail_closed() -> None:
    longest_id = "c" * 128
    bounded = replace(_ordinary(), configuration_id=longest_id)
    assert declare_live_voice_capabilities(bounded, enabled=True).ready is True
    with pytest.raises(ValueError):
        replace(_ordinary(), configuration_id="c" * 129)

    providers = tuple(
        ValidatedProviderConfiguration(
            provider_id=f"provider-{index:02d}",
            capabilities=(ProviderCapability.SPEECH_RECOGNITION_STREAMING,),
            validation_receipt_id=f"provider-receipt-{index:02d}",
            configuration_digest=_DIGEST,
        )
        for index in range(9)
    )
    at_maximum = replace(_formal(), providers=providers[:8])
    assert declare_live_voice_capabilities(at_maximum, enabled=True).ready is True
    with pytest.raises(ValueError):
        replace(_formal(), providers=providers)

    private = _formal()
    object.__setattr__(private.providers[0], "provider_id", "alice@example.com")
    rejected = declare_live_voice_capabilities(private, enabled=True)
    assert rejected.reason is ConfigurationDeclarationReason.PRIVATE_CONTENT_REJECTED
    _assert_zero_effect(rejected)


def test_configuration_replay_feature_off_and_forgery_are_effect_free() -> None:
    declaration = declare_live_voice_capabilities(_formal(), enabled=True).declaration
    forged = declare_live_voice_capabilities(_formal(), enabled=True).declaration
    object.__setattr__(forged, "provider_ids", ("provider-forged",))
    invalid = evaluate_live_voice_capability_declaration_replay(
        declaration,
        forged,
        enabled=True,
    )
    assert invalid.reason is ConfigurationReplayReason.INVALID_DECLARATION
    _assert_zero_effect(invalid)

    off = evaluate_live_voice_capability_declaration_replay(
        object(),
        object(),
        enabled=False,
    )
    assert off.reason is ConfigurationReplayReason.FEATURE_DISABLED
    _assert_zero_effect(off)
