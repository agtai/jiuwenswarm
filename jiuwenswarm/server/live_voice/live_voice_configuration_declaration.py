# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Pure validated-configuration to capability-declaration contract.

This module deliberately has no environment, Provider, worker, backend, or
lifecycle access. A caller may supply only a content-free configuration record
that its owning adapter already validated. Impossible authentication,
durability, Provider, or profile combinations fail closed instead of producing
a weaker declaration.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from jiuwenswarm.server.live_voice.observability import (
    contains_private_observability_content,
)


LIVE_VOICE_CONFIGURATION_CONTRACT_VERSION: Final = (
    "live-voice.configuration-declaration.v1"
)
LIVE_VOICE_CAPABILITY_DECLARATION_VERSION: Final = (
    "live-voice.capability-declaration.v1"
)
MAX_CONFIGURED_PROVIDERS: Final = 8

_IDENTITY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE = re.compile(r"^\+?[0-9][0-9 .()\-]{6,}$")


class ConfigurationContractViolation(ValueError):
    """Raised when configuration cannot support its exact declaration."""


class PrivateConfigurationContent(ConfigurationContractViolation):
    """Raised without echoing rejected secret or content carriers."""


class CapabilityConfigurationConflict(ConfigurationContractViolation):
    """Raised when capability claims exceed validated dependencies."""


class LiveVoiceDeploymentProfile(StrEnum):
    ORDINARY_PRODUCTION = "ordinary_production"
    FORMAL_LIVE_VOICE = "formal_live_voice"


class AuthenticationMode(StrEnum):
    DISABLED = "disabled"
    SCOPED_BEARER = "scoped_bearer"


class DurabilityLevel(StrEnum):
    D0 = "D0"
    D1 = "D1"
    D2 = "D2"


class ExecutorCapability(StrEnum):
    DISPATCH = "dispatch"
    STATUS = "status"
    CANCEL = "cancel"
    CHECKPOINT = "checkpoint"
    RECOVERY = "recovery"
    EFFECT_RECONCILIATION = "effect_reconciliation"


class ProviderCapability(StrEnum):
    SPEECH_RECOGNITION_BATCH = "speech_recognition_batch"
    SPEECH_SYNTHESIS_BATCH = "speech_synthesis_batch"
    SPEECH_RECOGNITION_STREAMING = "speech_recognition_streaming"
    SPEECH_SYNTHESIS_STREAMING = "speech_synthesis_streaming"
    TELEMETRY_EXPORT = "telemetry_export"


class LiveVoiceCapability(StrEnum):
    AUTHENTICATED = "authenticated"
    FORMAL_WEB = "formal_web"
    TASK_QUERY = "task_query"
    TASK_MUTATION = "task_mutation"
    EXECUTOR_D0 = "executor_d0"
    EXECUTOR_D1 = "executor_d1"
    EXECUTOR_D2 = "executor_d2"
    SPEECH_RECOGNITION_BATCH = "speech_recognition_batch"
    SPEECH_SYNTHESIS_BATCH = "speech_synthesis_batch"
    SPEECH_RECOGNITION_STREAMING = "speech_recognition_streaming"
    SPEECH_SYNTHESIS_STREAMING = "speech_synthesis_streaming"
    TELEMETRY_EXPORT = "telemetry_export"


class ConfigurationDeclarationReason(StrEnum):
    FEATURE_DISABLED = "feature_disabled"
    DECLARATION_READY = "declaration_ready"
    INVALID_CONFIGURATION = "invalid_configuration"
    PRIVATE_CONTENT_REJECTED = "private_content_rejected"
    CAPABILITY_CONFLICT = "capability_conflict"


class ConfigurationReplayReason(StrEnum):
    FEATURE_DISABLED = "feature_disabled"
    IDEMPOTENT = "idempotent"
    INVALID_DECLARATION = "invalid_declaration"
    IDENTITY_MISMATCH = "identity_mismatch"
    CONFIGURATION_CONFLICT = "configuration_conflict"


_REQUIRED_EXECUTOR_CAPABILITIES: Final = {
    DurabilityLevel.D0: frozenset(
        {
            ExecutorCapability.DISPATCH,
            ExecutorCapability.STATUS,
            ExecutorCapability.CANCEL,
        }
    ),
    DurabilityLevel.D1: frozenset(
        {
            ExecutorCapability.DISPATCH,
            ExecutorCapability.STATUS,
            ExecutorCapability.CANCEL,
            ExecutorCapability.CHECKPOINT,
            ExecutorCapability.RECOVERY,
        }
    ),
    DurabilityLevel.D2: frozenset(ExecutorCapability),
}

_DURABILITY_CAPABILITY: Final = {
    DurabilityLevel.D0: LiveVoiceCapability.EXECUTOR_D0,
    DurabilityLevel.D1: LiveVoiceCapability.EXECUTOR_D1,
    DurabilityLevel.D2: LiveVoiceCapability.EXECUTOR_D2,
}

_PROVIDER_CAPABILITY: Final = {
    ProviderCapability.SPEECH_RECOGNITION_BATCH: (
        LiveVoiceCapability.SPEECH_RECOGNITION_BATCH
    ),
    ProviderCapability.SPEECH_SYNTHESIS_BATCH: (
        LiveVoiceCapability.SPEECH_SYNTHESIS_BATCH
    ),
    ProviderCapability.SPEECH_RECOGNITION_STREAMING: (
        LiveVoiceCapability.SPEECH_RECOGNITION_STREAMING
    ),
    ProviderCapability.SPEECH_SYNTHESIS_STREAMING: (
        LiveVoiceCapability.SPEECH_SYNTHESIS_STREAMING
    ),
    ProviderCapability.TELEMETRY_EXPORT: LiveVoiceCapability.TELEMETRY_EXPORT,
}


def _safe_identity(value: object, field_name: str) -> str:
    if type(value) is str and (
        _EMAIL.fullmatch(value) is not None
        or _PHONE.fullmatch(value) is not None
        or contains_private_observability_content(value)
    ):
        raise PrivateConfigurationContent(f"{field_name} contains private content")
    if type(value) is not str or _IDENTITY.fullmatch(value) is None:
        raise ConfigurationContractViolation(
            f"{field_name} must be a bounded public identity"
        )
    return value


def _digest(value: object, field_name: str) -> str:
    if type(value) is not str or _DIGEST.fullmatch(value) is None:
        raise ConfigurationContractViolation(f"{field_name} must be lowercase SHA-256")
    return value


def _canonical_enum_tuple(
    values: object,
    enum_type: type[StrEnum],
    field_name: str,
) -> tuple[StrEnum, ...]:
    if type(values) is not tuple or any(
        type(value) is not enum_type for value in values
    ):
        raise ConfigurationContractViolation(
            f"{field_name} must use one exact immutable vocabulary"
        )
    if len(values) != len(set(values)) or values != tuple(
        sorted(values, key=lambda value: value.value)
    ):
        raise ConfigurationContractViolation(
            f"{field_name} must be unique and canonically ordered"
        )
    return values


@dataclass(frozen=True, slots=True)
class ValidatedAuthenticationConfiguration:
    mode: AuthenticationMode
    validation_receipt_id: str | None
    scope_digest: str | None

    def __post_init__(self) -> None:
        if type(self.mode) is not AuthenticationMode:
            raise ConfigurationContractViolation(
                "authentication mode must use the closed vocabulary"
            )
        if self.mode is AuthenticationMode.DISABLED:
            if self.validation_receipt_id is not None or self.scope_digest is not None:
                raise CapabilityConfigurationConflict(
                    "disabled authentication cannot carry authority evidence"
                )
            return
        _safe_identity(self.validation_receipt_id, "authentication receipt")
        _digest(self.scope_digest, "authentication scope digest")


@dataclass(frozen=True, slots=True)
class ValidatedExecutorConfiguration:
    executor_id: str
    adapter_id: str
    durability_level: DurabilityLevel
    capabilities: tuple[ExecutorCapability, ...]
    validation_receipt_id: str
    configuration_digest: str

    def __post_init__(self) -> None:
        _safe_identity(self.executor_id, "executor_id")
        _safe_identity(self.adapter_id, "adapter_id")
        if type(self.durability_level) is not DurabilityLevel:
            raise ConfigurationContractViolation(
                "durability level must use the closed vocabulary"
            )
        checked = _canonical_enum_tuple(
            self.capabilities,
            ExecutorCapability,
            "executor capabilities",
        )
        if frozenset(checked) != _REQUIRED_EXECUTOR_CAPABILITIES[self.durability_level]:
            raise CapabilityConfigurationConflict(
                "executor capabilities do not exactly support declared durability"
            )
        _safe_identity(self.validation_receipt_id, "executor validation receipt")
        _digest(self.configuration_digest, "executor configuration digest")


@dataclass(frozen=True, slots=True)
class ValidatedProviderConfiguration:
    provider_id: str
    capabilities: tuple[ProviderCapability, ...]
    validation_receipt_id: str
    configuration_digest: str

    def __post_init__(self) -> None:
        _safe_identity(self.provider_id, "provider_id")
        checked = _canonical_enum_tuple(
            self.capabilities,
            ProviderCapability,
            "provider capabilities",
        )
        if not checked:
            raise CapabilityConfigurationConflict(
                "a configured Provider must declare at least one capability"
            )
        _safe_identity(self.validation_receipt_id, "Provider validation receipt")
        _digest(self.configuration_digest, "Provider configuration digest")


@dataclass(frozen=True, slots=True)
class ValidatedLiveVoiceConfiguration:
    contract_version: str
    configuration_id: str
    configuration_digest: str
    profile: LiveVoiceDeploymentProfile
    enabled: bool
    ordinary_production_default_off: bool
    authentication: ValidatedAuthenticationConfiguration | None
    executor: ValidatedExecutorConfiguration | None
    providers: tuple[ValidatedProviderConfiguration, ...]
    capabilities: tuple[LiveVoiceCapability, ...]

    def __post_init__(self) -> None:
        if self.contract_version != LIVE_VOICE_CONFIGURATION_CONTRACT_VERSION:
            raise ConfigurationContractViolation(
                "unsupported Live Voice configuration contract"
            )
        _safe_identity(self.configuration_id, "configuration_id")
        _digest(self.configuration_digest, "configuration digest")
        if type(self.profile) is not LiveVoiceDeploymentProfile:
            raise ConfigurationContractViolation(
                "deployment profile must use the closed vocabulary"
            )
        if (
            type(self.enabled) is not bool
            or type(self.ordinary_production_default_off) is not bool
        ):
            raise ConfigurationContractViolation(
                "configuration gates must be exact bools"
            )
        if self.ordinary_production_default_off is not True:
            raise CapabilityConfigurationConflict(
                "ordinary production must remain explicitly default-off"
            )
        if (
            type(self.providers) is not tuple
            or len(self.providers) > MAX_CONFIGURED_PROVIDERS
            or any(
                type(provider) is not ValidatedProviderConfiguration
                for provider in self.providers
            )
        ):
            raise ConfigurationContractViolation(
                "Providers must use one bounded immutable tuple"
            )
        provider_ids = tuple(provider.provider_id for provider in self.providers)
        if len(provider_ids) != len(set(provider_ids)) or provider_ids != tuple(
            sorted(provider_ids)
        ):
            raise ConfigurationContractViolation(
                "Provider identities must be unique and canonically ordered"
            )
        declared = _canonical_enum_tuple(
            self.capabilities,
            LiveVoiceCapability,
            "declared capabilities",
        )
        if self.profile is LiveVoiceDeploymentProfile.ORDINARY_PRODUCTION:
            if (
                self.enabled is not False
                or self.authentication is not None
                or self.executor is not None
                or self.providers
                or declared
            ):
                raise CapabilityConfigurationConflict(
                    "ordinary production cannot implicitly enable Live Voice"
                )
            return
        if self.enabled is not True:
            raise CapabilityConfigurationConflict(
                "the explicit Live Voice profile must be explicitly enabled"
            )
        if type(self.authentication) is not ValidatedAuthenticationConfiguration:
            raise CapabilityConfigurationConflict(
                "formal Live Voice requires validated authentication"
            )
        if self.authentication.mode is not AuthenticationMode.SCOPED_BEARER:
            raise CapabilityConfigurationConflict(
                "formal Live Voice cannot downgrade authentication"
            )
        required_base = {
            LiveVoiceCapability.AUTHENTICATED,
            LiveVoiceCapability.FORMAL_WEB,
            LiveVoiceCapability.TASK_QUERY,
        }
        declared_set = set(declared)
        if not required_base.issubset(declared_set):
            raise CapabilityConfigurationConflict(
                "formal Live Voice is missing its exact base capabilities"
            )

        durability_claims = declared_set.intersection(_DURABILITY_CAPABILITY.values())
        if self.executor is None:
            if durability_claims or LiveVoiceCapability.TASK_MUTATION in declared_set:
                raise CapabilityConfigurationConflict(
                    "Executor or mutation capability lacks validated configuration"
                )
        else:
            if type(self.executor) is not ValidatedExecutorConfiguration:
                raise ConfigurationContractViolation(
                    "executor must use the exact validated contract"
                )
            expected_durability = _DURABILITY_CAPABILITY[self.executor.durability_level]
            if durability_claims != {expected_durability}:
                raise CapabilityConfigurationConflict(
                    "capability declaration cannot downgrade or upgrade durability"
                )
            if LiveVoiceCapability.TASK_MUTATION not in declared_set:
                raise CapabilityConfigurationConflict(
                    "a selected formal Executor must retain mutation truth"
                )

        provider_claims = {
            _PROVIDER_CAPABILITY[capability]
            for provider in self.providers
            for capability in provider.capabilities
        }
        declared_provider_claims = declared_set.intersection(
            _PROVIDER_CAPABILITY.values()
        )
        if declared_provider_claims != provider_claims:
            raise CapabilityConfigurationConflict(
                "Provider capability declaration does not match validated Providers"
            )


def _configuration_fingerprint(
    configuration: ValidatedLiveVoiceConfiguration,
) -> str:
    authentication = (
        None
        if configuration.authentication is None
        else {
            "mode": configuration.authentication.mode.value,
            "validation_receipt_id": (
                configuration.authentication.validation_receipt_id
            ),
            "scope_digest": configuration.authentication.scope_digest,
        }
    )
    executor = (
        None
        if configuration.executor is None
        else {
            "executor_id": configuration.executor.executor_id,
            "adapter_id": configuration.executor.adapter_id,
            "durability_level": configuration.executor.durability_level.value,
            "capabilities": [
                capability.value for capability in configuration.executor.capabilities
            ],
            "validation_receipt_id": configuration.executor.validation_receipt_id,
            "configuration_digest": configuration.executor.configuration_digest,
        }
    )
    payload = {
        "contract_version": configuration.contract_version,
        "configuration_id": configuration.configuration_id,
        "configuration_digest": configuration.configuration_digest,
        "profile": configuration.profile.value,
        "enabled": configuration.enabled,
        "ordinary_production_default_off": (
            configuration.ordinary_production_default_off
        ),
        "authentication": authentication,
        "executor": executor,
        "providers": [
            {
                "provider_id": provider.provider_id,
                "capabilities": [
                    capability.value for capability in provider.capabilities
                ],
                "validation_receipt_id": provider.validation_receipt_id,
                "configuration_digest": provider.configuration_digest,
            }
            for provider in configuration.providers
        ],
        "capabilities": [capability.value for capability in configuration.capabilities],
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def _validation_receipts(
    configuration: ValidatedLiveVoiceConfiguration,
) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                receipt
                for receipt in (
                    (
                        None
                        if configuration.authentication is None
                        else configuration.authentication.validation_receipt_id
                    ),
                    (
                        None
                        if configuration.executor is None
                        else configuration.executor.validation_receipt_id
                    ),
                    *(
                        provider.validation_receipt_id
                        for provider in configuration.providers
                    ),
                )
                if receipt is not None
            }
        )
    )


@dataclass(frozen=True, slots=True)
class LiveVoiceCapabilityDeclaration:
    declaration_version: str
    source_configuration: ValidatedLiveVoiceConfiguration
    source_configuration_fingerprint: str
    source_configuration_id: str
    source_configuration_digest: str
    profile: LiveVoiceDeploymentProfile
    active: bool
    authentication_mode: AuthenticationMode
    durability_level: DurabilityLevel | None
    capabilities: tuple[LiveVoiceCapability, ...]
    provider_ids: tuple[str, ...]
    validation_receipt_ids: tuple[str, ...]
    environment_read: bool = False
    provider_started: bool = False
    backend_called: bool = False
    worker_started: bool = False
    network_changed: bool = False
    persistence_changed: bool = False
    authentication_downgraded: bool = False
    durability_downgraded: bool = False
    business_result_changed: bool = False
    authoritative: bool = False
    authorization_granted: bool = False

    def __post_init__(self) -> None:
        if self.declaration_version != LIVE_VOICE_CAPABILITY_DECLARATION_VERSION:
            raise ValueError("unsupported capability declaration")
        if type(self.source_configuration) is not ValidatedLiveVoiceConfiguration:
            raise ValueError("declaration requires the complete validated projection")
        checked = _validated_configuration(self.source_configuration)
        expected_fingerprint = _configuration_fingerprint(checked)
        if (
            type(self.source_configuration_fingerprint) is not str
            or self.source_configuration_fingerprint != expected_fingerprint
        ):
            raise ValueError("declaration fingerprint is not bound to its projection")
        _safe_identity(self.source_configuration_id, "source configuration")
        _digest(self.source_configuration_digest, "source configuration digest")
        if (
            type(self.profile) is not LiveVoiceDeploymentProfile
            or type(self.active) is not bool
            or type(self.authentication_mode) is not AuthenticationMode
        ):
            raise ValueError("capability declaration truth fields are invalid")
        expected_authentication = (
            AuthenticationMode.DISABLED
            if checked.authentication is None
            else checked.authentication.mode
        )
        expected_durability = (
            None if checked.executor is None else checked.executor.durability_level
        )
        if (
            self.source_configuration_id != checked.configuration_id
            or self.source_configuration_digest != checked.configuration_digest
            or self.profile is not checked.profile
            or self.active is not checked.enabled
            or self.authentication_mode is not expected_authentication
            or self.durability_level is not expected_durability
            or self.capabilities != checked.capabilities
            or self.provider_ids
            != tuple(provider.provider_id for provider in checked.providers)
            or self.validation_receipt_ids != _validation_receipts(checked)
        ):
            raise ValueError(
                "declaration fields do not exactly project validated configuration"
            )
        _canonical_enum_tuple(
            self.capabilities,
            LiveVoiceCapability,
            "capability declaration",
        )
        if type(self.durability_level) not in (type(None), DurabilityLevel):
            raise ValueError("declared durability must use the closed vocabulary")
        if self.provider_ids != tuple(sorted(set(self.provider_ids))):
            raise ValueError("declared Provider identities must be canonical")
        for provider_id in self.provider_ids:
            _safe_identity(provider_id, "declared Provider identity")
        if self.validation_receipt_ids != tuple(
            sorted(set(self.validation_receipt_ids))
        ):
            raise ValueError("validation receipts must be canonical")
        for receipt_id in self.validation_receipt_ids:
            _safe_identity(receipt_id, "validation receipt")
        declared = set(self.capabilities)
        durability_claims = declared.intersection(_DURABILITY_CAPABILITY.values())
        if self.profile is LiveVoiceDeploymentProfile.ORDINARY_PRODUCTION:
            if (
                self.active is not False
                or self.authentication_mode is not AuthenticationMode.DISABLED
                or self.durability_level is not None
                or declared
                or self.provider_ids
                or self.validation_receipt_ids
            ):
                raise ValueError("ordinary declaration must remain exactly inactive")
        else:
            if (
                self.active is not True
                or self.authentication_mode is not AuthenticationMode.SCOPED_BEARER
                or not {
                    LiveVoiceCapability.AUTHENTICATED,
                    LiveVoiceCapability.FORMAL_WEB,
                    LiveVoiceCapability.TASK_QUERY,
                }.issubset(declared)
            ):
                raise ValueError("formal declaration cannot downgrade its base truth")
            if self.durability_level is None:
                if durability_claims or LiveVoiceCapability.TASK_MUTATION in declared:
                    raise ValueError("mutation truth requires declared durability")
            elif (
                durability_claims != {_DURABILITY_CAPABILITY[self.durability_level]}
                or LiveVoiceCapability.TASK_MUTATION not in declared
            ):
                raise ValueError("declared durability must remain exact")
        if any(
            value is not False
            for value in (
                self.environment_read,
                self.provider_started,
                self.backend_called,
                self.worker_started,
                self.network_changed,
                self.persistence_changed,
                self.authentication_downgraded,
                self.durability_downgraded,
                self.business_result_changed,
                self.authoritative,
                self.authorization_granted,
            )
        ):
            raise ValueError(
                "a declaration cannot claim authorization, runtime or downgrade effects"
            )


@dataclass(frozen=True, slots=True)
class ConfigurationDeclarationResult:
    ready: bool
    reason: ConfigurationDeclarationReason
    declaration: LiveVoiceCapabilityDeclaration | None
    environment_read: bool = False
    provider_started: bool = False
    backend_called: bool = False
    worker_started: bool = False
    network_changed: bool = False
    persistence_changed: bool = False
    authentication_downgraded: bool = False
    durability_downgraded: bool = False
    business_result_changed: bool = False
    agent_effect: bool = False
    tool_effect: bool = False
    task_effect: bool = False
    audio_effect: bool = False
    history_effect: bool = False
    authorization_granted: bool = False

    def __post_init__(self) -> None:
        if (
            type(self.ready) is not bool
            or type(self.reason) is not ConfigurationDeclarationReason
        ):
            raise ValueError("configuration result truth fields are invalid")
        if self.ready != (self.declaration is not None) or self.ready != (
            self.reason is ConfigurationDeclarationReason.DECLARATION_READY
        ):
            raise ValueError("configuration readiness must match its declaration")
        if any(
            value is not False
            for value in (
                self.environment_read,
                self.provider_started,
                self.backend_called,
                self.worker_started,
                self.network_changed,
                self.persistence_changed,
                self.authentication_downgraded,
                self.durability_downgraded,
                self.business_result_changed,
                self.agent_effect,
                self.tool_effect,
                self.task_effect,
                self.audio_effect,
                self.history_effect,
                self.authorization_granted,
            )
        ):
            raise ValueError("a pure configuration result cannot own effects")


@dataclass(frozen=True, slots=True)
class ConfigurationReplayResult:
    accepted: bool
    reason: ConfigurationReplayReason
    environment_read: bool = False
    provider_started: bool = False
    backend_called: bool = False
    worker_started: bool = False
    network_changed: bool = False
    persistence_changed: bool = False
    authentication_downgraded: bool = False
    durability_downgraded: bool = False
    business_result_changed: bool = False
    agent_effect: bool = False
    tool_effect: bool = False
    task_effect: bool = False
    audio_effect: bool = False
    history_effect: bool = False
    authorization_granted: bool = False

    def __post_init__(self) -> None:
        if (
            type(self.accepted) is not bool
            or type(self.reason) is not ConfigurationReplayReason
        ):
            raise ValueError("configuration replay truth fields are invalid")
        if self.accepted != (self.reason is ConfigurationReplayReason.IDEMPOTENT):
            raise ValueError("only an identical configuration replay may be accepted")
        if any(
            value is not False
            for value in (
                self.environment_read,
                self.provider_started,
                self.backend_called,
                self.worker_started,
                self.network_changed,
                self.persistence_changed,
                self.authentication_downgraded,
                self.durability_downgraded,
                self.business_result_changed,
                self.agent_effect,
                self.tool_effect,
                self.task_effect,
                self.audio_effect,
                self.history_effect,
                self.authorization_granted,
            )
        ):
            raise ValueError("configuration replay cannot own effects")


def _validated_authentication(
    value: ValidatedAuthenticationConfiguration | None,
) -> ValidatedAuthenticationConfiguration | None:
    if value is None:
        return None
    if type(value) is not ValidatedAuthenticationConfiguration:
        raise ConfigurationContractViolation(
            "authentication requires the exact validated contract"
        )
    return ValidatedAuthenticationConfiguration(
        mode=value.mode,
        validation_receipt_id=value.validation_receipt_id,
        scope_digest=value.scope_digest,
    )


def _validated_executor(
    value: ValidatedExecutorConfiguration | None,
) -> ValidatedExecutorConfiguration | None:
    if value is None:
        return None
    if type(value) is not ValidatedExecutorConfiguration:
        raise ConfigurationContractViolation(
            "executor requires the exact validated contract"
        )
    if type(value.capabilities) is not tuple or any(
        type(capability) is not ExecutorCapability for capability in value.capabilities
    ):
        raise ConfigurationContractViolation(
            "executor capabilities contain a non-contract value"
        )
    return ValidatedExecutorConfiguration(
        executor_id=value.executor_id,
        adapter_id=value.adapter_id,
        durability_level=value.durability_level,
        capabilities=tuple(value.capabilities),
        validation_receipt_id=value.validation_receipt_id,
        configuration_digest=value.configuration_digest,
    )


def _validated_configuration(
    value: ValidatedLiveVoiceConfiguration,
) -> ValidatedLiveVoiceConfiguration:
    if type(value) is not ValidatedLiveVoiceConfiguration:
        raise ConfigurationContractViolation(
            "configuration requires the exact validated contract"
        )
    authentication = value.authentication
    executor = value.executor
    providers = value.providers
    capabilities = value.capabilities
    if type(providers) is not tuple or any(
        type(provider) is not ValidatedProviderConfiguration for provider in providers
    ):
        raise ConfigurationContractViolation("Providers contain a non-contract value")
    for provider in providers:
        if type(provider.capabilities) is not tuple or any(
            type(capability) is not ProviderCapability
            for capability in provider.capabilities
        ):
            raise ConfigurationContractViolation(
                "Provider capabilities contain a non-contract value"
            )
    if type(capabilities) is not tuple or any(
        type(capability) is not LiveVoiceCapability for capability in capabilities
    ):
        raise ConfigurationContractViolation(
            "declared capabilities contain a non-contract value"
        )
    return ValidatedLiveVoiceConfiguration(
        contract_version=value.contract_version,
        configuration_id=value.configuration_id,
        configuration_digest=value.configuration_digest,
        profile=value.profile,
        enabled=value.enabled,
        ordinary_production_default_off=value.ordinary_production_default_off,
        authentication=_validated_authentication(authentication),
        executor=_validated_executor(executor),
        providers=tuple(
            ValidatedProviderConfiguration(
                provider_id=provider.provider_id,
                capabilities=tuple(provider.capabilities),
                validation_receipt_id=provider.validation_receipt_id,
                configuration_digest=provider.configuration_digest,
            )
            for provider in providers
        ),
        capabilities=tuple(capabilities),
    )


def _build_declaration(
    configuration: ValidatedLiveVoiceConfiguration,
) -> LiveVoiceCapabilityDeclaration:
    authentication_mode = (
        AuthenticationMode.DISABLED
        if configuration.authentication is None
        else configuration.authentication.mode
    )
    return LiveVoiceCapabilityDeclaration(
        declaration_version=LIVE_VOICE_CAPABILITY_DECLARATION_VERSION,
        source_configuration=configuration,
        source_configuration_fingerprint=_configuration_fingerprint(configuration),
        source_configuration_id=configuration.configuration_id,
        source_configuration_digest=configuration.configuration_digest,
        profile=configuration.profile,
        active=configuration.enabled,
        authentication_mode=authentication_mode,
        durability_level=(
            None
            if configuration.executor is None
            else configuration.executor.durability_level
        ),
        capabilities=configuration.capabilities,
        provider_ids=tuple(
            provider.provider_id for provider in configuration.providers
        ),
        validation_receipt_ids=_validation_receipts(configuration),
    )


def _validated_declaration(
    declaration: LiveVoiceCapabilityDeclaration,
) -> LiveVoiceCapabilityDeclaration:
    checked_configuration = _validated_configuration(declaration.source_configuration)
    checked = _build_declaration(checked_configuration)
    if declaration != checked:
        raise ConfigurationContractViolation(
            "declaration is not the exact non-authoritative projection"
        )
    return checked


def declare_live_voice_capabilities(
    configuration: object,
    *,
    enabled: bool,
) -> ConfigurationDeclarationResult:
    """Produce an exact declaration without reading or starting dependencies."""

    if type(enabled) is not bool:
        raise ValueError("enabled must be exact bool")
    if not enabled:
        return ConfigurationDeclarationResult(
            ready=False,
            reason=ConfigurationDeclarationReason.FEATURE_DISABLED,
            declaration=None,
        )
    if type(configuration) is not ValidatedLiveVoiceConfiguration:
        return ConfigurationDeclarationResult(
            ready=False,
            reason=ConfigurationDeclarationReason.INVALID_CONFIGURATION,
            declaration=None,
        )
    try:
        checked = _validated_configuration(configuration)
    except PrivateConfigurationContent:
        return ConfigurationDeclarationResult(
            ready=False,
            reason=ConfigurationDeclarationReason.PRIVATE_CONTENT_REJECTED,
            declaration=None,
        )
    except CapabilityConfigurationConflict:
        return ConfigurationDeclarationResult(
            ready=False,
            reason=ConfigurationDeclarationReason.CAPABILITY_CONFLICT,
            declaration=None,
        )
    except Exception:
        return ConfigurationDeclarationResult(
            ready=False,
            reason=ConfigurationDeclarationReason.INVALID_CONFIGURATION,
            declaration=None,
        )

    declaration = _build_declaration(checked)
    return ConfigurationDeclarationResult(
        ready=True,
        reason=ConfigurationDeclarationReason.DECLARATION_READY,
        declaration=declaration,
    )


def evaluate_live_voice_capability_declaration_replay(
    original: object,
    replay: object,
    *,
    enabled: bool,
) -> ConfigurationReplayResult:
    """Compare sealed configuration truth without granting authorization."""

    if type(enabled) is not bool:
        raise ValueError("enabled must be exact bool")
    if not enabled:
        return ConfigurationReplayResult(
            accepted=False,
            reason=ConfigurationReplayReason.FEATURE_DISABLED,
        )
    if (
        type(original) is not LiveVoiceCapabilityDeclaration
        or type(replay) is not LiveVoiceCapabilityDeclaration
    ):
        return ConfigurationReplayResult(
            accepted=False,
            reason=ConfigurationReplayReason.INVALID_DECLARATION,
        )
    try:
        checked_original = _validated_declaration(original)
        checked_replay = _validated_declaration(replay)
    except Exception:
        return ConfigurationReplayResult(
            accepted=False,
            reason=ConfigurationReplayReason.INVALID_DECLARATION,
        )
    original_identity = (
        checked_original.source_configuration_id,
        checked_original.source_configuration_digest,
    )
    replay_identity = (
        checked_replay.source_configuration_id,
        checked_replay.source_configuration_digest,
    )
    if original_identity != replay_identity:
        return ConfigurationReplayResult(
            accepted=False,
            reason=ConfigurationReplayReason.IDENTITY_MISMATCH,
        )
    if (
        checked_original.source_configuration_fingerprint
        != checked_replay.source_configuration_fingerprint
    ):
        return ConfigurationReplayResult(
            accepted=False,
            reason=ConfigurationReplayReason.CONFIGURATION_CONFLICT,
        )
    if checked_original != checked_replay:
        return ConfigurationReplayResult(
            accepted=False,
            reason=ConfigurationReplayReason.INVALID_DECLARATION,
        )
    return ConfigurationReplayResult(
        accepted=True,
        reason=ConfigurationReplayReason.IDEMPOTENT,
    )


__all__ = [
    "AuthenticationMode",
    "CapabilityConfigurationConflict",
    "ConfigurationContractViolation",
    "ConfigurationDeclarationReason",
    "ConfigurationDeclarationResult",
    "ConfigurationReplayReason",
    "ConfigurationReplayResult",
    "DurabilityLevel",
    "ExecutorCapability",
    "LIVE_VOICE_CAPABILITY_DECLARATION_VERSION",
    "LIVE_VOICE_CONFIGURATION_CONTRACT_VERSION",
    "LiveVoiceCapability",
    "LiveVoiceCapabilityDeclaration",
    "LiveVoiceDeploymentProfile",
    "MAX_CONFIGURED_PROVIDERS",
    "PrivateConfigurationContent",
    "ProviderCapability",
    "ValidatedAuthenticationConfiguration",
    "ValidatedExecutorConfiguration",
    "ValidatedLiveVoiceConfiguration",
    "ValidatedProviderConfiguration",
    "declare_live_voice_capabilities",
    "evaluate_live_voice_capability_declaration_replay",
]
