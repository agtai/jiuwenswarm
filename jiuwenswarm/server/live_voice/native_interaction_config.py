# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Closed environment selection for Cascade versus Native interaction."""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum


INTERACTION_ENGINE_ENV = "LIVE_VOICE_INTERACTION_ENGINE"
NATIVE_REALTIME_MODEL_ENV = "LIVE_VOICE_NATIVE_REALTIME_MODEL"
DEFAULT_NATIVE_REALTIME_MODEL = "gpt-realtime-2.1-mini"
_MAX_MODEL_CHARS = 256
_MAX_MODEL_UTF8_BYTES = 1_024


class NativeInteractionConfigurationError(ValueError):
    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


class InteractionEngineKind(StrEnum):
    CASCADE = "cascade"
    OPENAI_REALTIME_NATIVE = "openai-realtime-native"


@dataclass(frozen=True, slots=True)
class NativeInteractionSelection:
    kind: InteractionEngineKind
    native_model: str | None


def _model(value: object) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > _MAX_MODEL_CHARS
        or any(
            unicodedata.category(character) in {"Cc", "Cf", "Zl", "Zp"}
            for character in value
        )
    ):
        raise NativeInteractionConfigurationError(
            "NATIVE_REALTIME_MODEL_INVALID",
            "Native Realtime model must be a bounded, trimmed, single-line value",
        )
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError:
        raise NativeInteractionConfigurationError(
            "NATIVE_REALTIME_MODEL_INVALID",
            "Native Realtime model must contain valid Unicode",
        ) from None
    if len(encoded) > _MAX_MODEL_UTF8_BYTES:
        raise NativeInteractionConfigurationError(
            "NATIVE_REALTIME_MODEL_INVALID",
            "Native Realtime model exceeds its UTF-8 bound",
        )
    return value


def select_interaction_engine_environment(
    environ: Mapping[str, str],
) -> NativeInteractionSelection:
    if not isinstance(environ, Mapping):
        raise NativeInteractionConfigurationError(
            "INTERACTION_ENGINE_ENVIRONMENT_INVALID",
            "interaction Engine environment must be a mapping",
        )
    raw_kind = environ.get(INTERACTION_ENGINE_ENV, InteractionEngineKind.CASCADE.value)
    if (
        type(raw_kind) is not str
        or not raw_kind
        or raw_kind != raw_kind.strip()
        or len(raw_kind) > _MAX_MODEL_CHARS
        or any(
            unicodedata.category(character) in {"Cc", "Cf", "Zl", "Zp"}
            for character in raw_kind
        )
    ):
        raise NativeInteractionConfigurationError(
            "INTERACTION_ENGINE_INVALID",
            "interaction Engine selection must be an exact canonical value",
        )
    try:
        kind = InteractionEngineKind(raw_kind)
    except ValueError:
        raise NativeInteractionConfigurationError(
            "INTERACTION_ENGINE_UNSUPPORTED",
            "interaction Engine selection is unsupported",
        ) from None
    if kind is InteractionEngineKind.CASCADE:
        return NativeInteractionSelection(kind=kind, native_model=None)
    raw_model = environ.get(NATIVE_REALTIME_MODEL_ENV, DEFAULT_NATIVE_REALTIME_MODEL)
    return NativeInteractionSelection(kind=kind, native_model=_model(raw_model))


__all__ = [
    "DEFAULT_NATIVE_REALTIME_MODEL",
    "INTERACTION_ENGINE_ENV",
    "NATIVE_REALTIME_MODEL_ENV",
    "InteractionEngineKind",
    "NativeInteractionConfigurationError",
    "NativeInteractionSelection",
    "select_interaction_engine_environment",
]
