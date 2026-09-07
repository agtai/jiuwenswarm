# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Closed, credential-free Native Agent model selection and confirmation values."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from jiuwenswarm.common.schema.live_voice_contract_v2 import ErrorCode

from .formal_task_models import FormalTaskViolation
from .p3_model_resolution import P3ModelResolver

AGENT_MODEL_SELECTION_VERSION = "live-voice.agent-model-selection.v1"


def _invalid() -> FormalTaskViolation:
    return FormalTaskViolation(
        "INVALID_NATIVE_AGENT_MODEL_SELECTION",
        "Native Agent model selection is invalid",
        ErrorCode.INVALID_ARGUMENT,
    )


def _text(value: object) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise _invalid()
    try:
        bounded = len(value.encode("utf-8")) <= 256
    except UnicodeEncodeError:
        bounded = False
    if not bounded or any(ord(char) < 32 for char in value):
        raise _invalid()
    return value


def _closed(value: object, fields: set[str]) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise _invalid()
    return value


@dataclass(frozen=True, slots=True)
class NativeAgentModelSelection:
    contract_version: str
    model_name: str

    def __post_init__(self) -> None:
        if (
            type(self.contract_version) is not str
            or self.contract_version != AGENT_MODEL_SELECTION_VERSION
        ):
            raise _invalid()
        _text(self.model_name)

    def to_dict(self) -> dict[str, str]:
        return {
            "contract_version": self.contract_version,
            "model_name": self.model_name,
        }


@dataclass(frozen=True, slots=True)
class NativeAgentModelConfirmation(NativeAgentModelSelection):
    model_identity: str
    model_config_version: str

    def __post_init__(self) -> None:
        NativeAgentModelSelection.__post_init__(self)
        _text(self.model_identity)
        _text(self.model_config_version)

    def to_dict(self) -> dict[str, str]:
        return {
            **NativeAgentModelSelection.to_dict(self),
            "model_identity": self.model_identity,
            "model_config_version": self.model_config_version,
        }


def parse_native_agent_model_selection(value: object) -> NativeAgentModelSelection:
    record = _closed(value, {"contract_version", "model_name"})
    return NativeAgentModelSelection(
        contract_version=record["contract_version"], model_name=record["model_name"]
    )


def resolve_native_agent_model(
    resolver: P3ModelResolver,
    selection: NativeAgentModelSelection | None = None,
) -> NativeAgentModelConfirmation:
    """Resolve a new activation only; exact activation replay retains its confirmation.

    The request's alias is echoed unchanged. With no requested choice, report the
    catalog model name from its stable ``model-name#index`` identity. Resolution
    does not construct a model, return configuration, or retain credentials.
    """
    if selection is not None and type(selection) is not NativeAgentModelSelection:
        raise _invalid()
    resolved = resolver.resolve(
        None if selection is None else selection.model_name, instantiate=False
    )
    name, separator, index = resolved.identity.rpartition("#")
    default_name = (
        name if separator and name and index.isdecimal() else resolved.identity
    )
    return NativeAgentModelConfirmation(
        contract_version=AGENT_MODEL_SELECTION_VERSION,
        model_name=default_name if selection is None else selection.model_name,
        model_identity=resolved.identity,
        model_config_version=resolved.config_version,
    )
