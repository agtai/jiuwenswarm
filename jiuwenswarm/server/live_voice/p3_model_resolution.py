# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Exact, drift-detecting server model resolution for formal P3 tasks."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from jiuwenswarm.common.schema.live_voice_contract_v2 import ErrorCode

from .formal_task_models import FormalTaskViolation


@dataclass(frozen=True, slots=True)
class ResolvedP3Model:
    model: Any | None
    identity: str
    config_version: str


class P3ModelResolver(Protocol):
    def resolve(
        self,
        model_intent: str | None,
        *,
        expected_identity: str | None = None,
        expected_config_version: str | None = None,
        instantiate: bool = False,
    ) -> ResolvedP3Model: ...


@dataclass(frozen=True, slots=True)
class _CatalogEntry:
    identity: str
    model_name: str
    alias: str | None
    is_default: bool
    client_config: dict[str, Any]
    model_config: dict[str, Any]


class ServerModelCatalogResolver:
    """Resolve one unambiguous catalog entry and bind the whole catalog version."""

    def __init__(
        self,
        *,
        catalog_reader: Callable[[], Sequence[Mapping[str, Any]]],
        model_builder: Callable[[dict[str, Any], dict[str, Any]], Any],
    ) -> None:
        self._catalog_reader = catalog_reader
        self._model_builder = model_builder

    @staticmethod
    def _entries(
        raw_entries: Sequence[Mapping[str, Any]],
    ) -> tuple[_CatalogEntry, ...]:
        counters: dict[str, int] = {}
        entries: list[_CatalogEntry] = []
        for raw in raw_entries:
            if not isinstance(raw, Mapping):
                continue
            raw_client = raw.get("model_client_config")
            raw_model = raw.get("model_config_obj")
            if not isinstance(raw_client, Mapping):
                continue
            model_name = str(raw_client.get("model_name") or "").strip()
            if not model_name:
                continue
            index = counters.get(model_name, 0)
            counters[model_name] = index + 1
            alias_value = str(raw.get("alias") or "").strip()
            entries.append(
                _CatalogEntry(
                    identity=f"{model_name}#{index}",
                    model_name=model_name,
                    alias=alias_value or None,
                    is_default=raw.get("is_default") is True,
                    client_config=dict(raw_client),
                    model_config=(
                        dict(raw_model) if isinstance(raw_model, Mapping) else {}
                    ),
                )
            )
        return tuple(entries)

    @staticmethod
    def _config_version(entries: tuple[_CatalogEntry, ...]) -> str:
        payload = [
            {
                "identity": entry.identity,
                "alias": entry.alias,
                "is_default": entry.is_default,
                "model_client_config": entry.client_config,
                "model_config_obj": entry.model_config,
            }
            for entry in entries
        ]
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _select(
        entries: tuple[_CatalogEntry, ...], model_intent: str | None
    ) -> _CatalogEntry:
        requested = str(model_intent or "").strip()
        if requested:
            matches = tuple(
                entry
                for entry in entries
                if requested in {entry.identity, entry.model_name, entry.alias}
            )
            if not matches:
                raise FormalTaskViolation(
                    "P3_MODEL_INTENT_UNKNOWN",
                    "formal task model intent does not identify an available model",
                    ErrorCode.CAPABILITY_UNAVAILABLE,
                )
            if len(matches) != 1:
                raise FormalTaskViolation(
                    "P3_MODEL_INTENT_AMBIGUOUS",
                    "formal task model intent is ambiguous",
                    ErrorCode.INVALID_ARGUMENT,
                )
            return matches[0]
        # ``get_default_models`` marks one variant as default *per model name*;
        # several distinct names therefore legitimately carry is_default=True.
        # The server's global default is the first configured model-name group.
        default_name = entries[0].model_name
        defaults = tuple(
            entry
            for entry in entries
            if entry.model_name == default_name and entry.is_default
        )
        if len(defaults) > 1:
            raise FormalTaskViolation(
                "P3_DEFAULT_MODEL_AMBIGUOUS",
                "formal task default model is ambiguous",
                ErrorCode.INVALID_ARGUMENT,
            )
        return defaults[0] if defaults else entries[0]

    def resolve(
        self,
        model_intent: str | None,
        *,
        expected_identity: str | None = None,
        expected_config_version: str | None = None,
        instantiate: bool = False,
    ) -> ResolvedP3Model:
        try:
            raw_entries = self._catalog_reader()
        except Exception as exc:
            raise FormalTaskViolation(
                "P3_MODEL_CATALOG_UNAVAILABLE",
                "formal task model catalog is unavailable",
                ErrorCode.UNAVAILABLE,
            ) from exc
        entries = self._entries(raw_entries)
        if not entries:
            raise FormalTaskViolation(
                "P3_MODEL_CATALOG_UNAVAILABLE",
                "formal task model catalog contains no usable models",
                ErrorCode.CAPABILITY_UNAVAILABLE,
            )
        selected = self._select(entries, model_intent)
        config_version = self._config_version(entries)
        if (
            expected_identity is not None and selected.identity != expected_identity
        ) or (
            expected_config_version is not None
            and config_version != expected_config_version
        ):
            raise FormalTaskViolation(
                "EXECUTOR_MODEL_BINDING_DRIFT",
                "runtime model identity or configuration no longer matches the task",
                ErrorCode.PERMISSION_DENIED,
            )
        if not instantiate:
            return ResolvedP3Model(None, selected.identity, config_version)
        try:
            model = self._model_builder(selected.client_config, selected.model_config)
        except Exception as exc:
            raise FormalTaskViolation(
                "P3_MODEL_UNAVAILABLE",
                "formal task model cannot be constructed",
                ErrorCode.CAPABILITY_UNAVAILABLE,
            ) from exc
        if model is None:
            raise FormalTaskViolation(
                "P3_MODEL_UNAVAILABLE",
                "formal task model is unavailable",
                ErrorCode.CAPABILITY_UNAVAILABLE,
            )
        return ResolvedP3Model(model, selected.identity, config_version)


__all__ = [
    "P3ModelResolver",
    "ResolvedP3Model",
    "ServerModelCatalogResolver",
]
