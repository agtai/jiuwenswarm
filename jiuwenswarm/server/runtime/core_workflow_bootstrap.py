# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.
"""Trusted production assembly for explicit Core Workflow capabilities.

This module never registers/removes an SDK provider or starts an execution.
Declarations are supplied by the embedding application, never by a wire request.
Native retains its principal/project policy; Web supplies a trusted authorizer.
"""
from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from openjiuwen.core.runner import Runner
from openjiuwen.core.workflow import WorkflowCard

from .core_workflow_capabilities import (
    CoreWorkflowCapabilities, CoreWorkflowCapability, CoreWorkflowError, CoreWorkflowScope,
    _card_text, _guard,
)


@dataclass(frozen=True, slots=True, init=False)
class CoreWorkflowDefinition:
    capability_id: str
    registered_provider: Callable = field(repr=False)
    required_permissions: tuple[str, ...]
    _card_json: str = field(repr=False)
    _continuation_json: tuple[tuple[str, str], ...] = field(repr=False)

    def __init__(self, capability_id: str, card: WorkflowCard, registered_provider: Callable,
                 required_permissions: tuple[str, ...], continuation_schemas: Mapping[str, dict] | None = None):
        if not callable(registered_provider):
            raise CoreWorkflowError('invalid_registered_provider')
        # Reuse the directory's pure schema/card checks, without SDK access.
        scratch = CoreWorkflowCapabilities()
        checked = scratch.register(scope=CoreWorkflowScope('host', 'validation', None, 'validation'),
            capability_id=capability_id, card=card, required_permissions=required_permissions,
            continuation_schemas=continuation_schemas)
        for name, value in (
            ('capability_id', capability_id), ('registered_provider', registered_provider),
            ('required_permissions', checked.required_permissions), ('_card_json', checked._card_json),
            ('_continuation_json', checked._continuation_json),
        ):
            object.__setattr__(self, name, value)

    @property
    def card(self) -> WorkflowCard:
        return WorkflowCard.model_validate(json.loads(self._card_json))

    @property
    def continuation_schemas(self) -> dict[str, dict]:
        return {node: json.loads(schema) for node, schema in self._continuation_json}


@dataclass(frozen=True, slots=True, kw_only=True)
class CoreWorkflowBootstrap:
    definitions: tuple[CoreWorkflowDefinition, ...]
    select: Callable[[CoreWorkflowScope], tuple[str, ...]] = field(repr=False)
    authorize_web: Callable[..., None] = field(repr=False)

    def __post_init__(self):
        if (type(self.definitions) is not tuple or
                any(type(item) is not CoreWorkflowDefinition for item in self.definitions)
                or len({item.capability_id for item in self.definitions}) != len(self.definitions)):
            raise CoreWorkflowError('invalid_bootstrap_definitions')
        if not callable(self.select) or not callable(self.authorize_web):
            raise CoreWorkflowError('invalid_bootstrap_callbacks')


class InstalledCoreWorkflowHost:
    """One manager's metadata/authority installation; never an execution owner."""

    def __init__(self, manager: Any, bootstrap: CoreWorkflowBootstrap):
        self._manager = manager
        self._bootstrap = bootstrap
        self._directory = manager.core_workflow_capabilities
        self._sdk_registry = Runner.resource_mgr
        self._revoked = False
        # Keep a stable callable identity for the directory's one-shot hook.
        self._resolution_hook = self._before_resolve

    @property
    def bootstrap(self) -> CoreWorkflowBootstrap:
        return self._bootstrap

    def revoke(self) -> None:
        self._revoked = True

    def _current(self) -> None:
        if self._revoked:
            raise CoreWorkflowError('bootstrap_revoked')
        if (getattr(self._manager, 'core_workflow_host', None) is not self
                or self._manager.core_workflow_capabilities is not self._directory):
            raise CoreWorkflowError('bootstrap_replaced')

    @staticmethod
    def _scope_operation(scope: CoreWorkflowScope, operation: str) -> None:
        if type(scope) is not CoreWorkflowScope:
            raise CoreWorkflowError('invalid_scope')
        if operation not in ('list', 'get', 'start', 'resume'):
            raise CoreWorkflowError('invalid_bootstrap_operation')

    def _selection(self, scope: CoreWorkflowScope) -> tuple[CoreWorkflowDefinition, ...]:
        ids = self._bootstrap.select(scope)
        if (type(ids) is not tuple or any(type(item) is not str for item in ids)
                or len(ids) != len(set(ids))):
            # Close accidental coroutine results without scheduling them.
            import inspect
            if inspect.iscoroutine(ids):
                ids.close()
            raise CoreWorkflowError('invalid_bootstrap_selection')
        definitions = self._bootstrap.definitions
        if any(not any(item.capability_id == key for item in definitions) for key in ids):
            raise CoreWorkflowError('unknown_bootstrap_capability')
        return tuple(next(item for item in definitions if item.capability_id == key) for key in ids)

    def _registered(self, definition: CoreWorkflowDefinition) -> None:
        # Pinned SDK read-only metadata/provider lookup: get_workflow would
        # instantiate the provider and is forbidden during installation/list.
        registry = Runner.resource_mgr
        if registry is not self._sdk_registry:
            raise CoreWorkflowError('sdk_registry_changed')
        try:
            card = registry._id_to_card.get(definition.card.id)
            provider = registry._resource_registry.workflow()._providers.get(definition.card.id)
            matches = provider is definition.registered_provider and _card_text(card) == definition._card_json
        except (AttributeError, TypeError, ValueError):
            matches = False
        if not matches:
            raise CoreWorkflowError('sdk_registration_changed')

    def guard(self, scope: CoreWorkflowScope, operation: str,
              capability: CoreWorkflowCapability | None) -> None:
        self._scope_operation(scope, operation)
        self._current()
        selected = self._selection(scope)
        self._current()
        if capability is None:
            return
        if (type(capability) is not CoreWorkflowCapability or capability.scope != scope
                or self._directory.get(scope=scope, capability_id=capability.capability_id) is not capability):
            raise CoreWorkflowError('bootstrap_capability_mismatch')
        definition = next((item for item in selected if item.capability_id == capability.capability_id), None)
        if definition is None:
            raise CoreWorkflowError('bootstrap_capability_revoked')
        if (definition._card_json != capability._card_json
                or definition.required_permissions != capability.required_permissions
                or definition._continuation_json != capability._continuation_json):
            raise CoreWorkflowError('bootstrap_capability_mismatch')
        # A resolved run owns its original instance. Global SDK registry changes
        # only fence new resolution, never retarget or revoke that original run.

    def bind_scope(self, scope: CoreWorkflowScope, *, operation: str,
                   before_read: Callable[[], None]) -> tuple[CoreWorkflowCapability, ...]:
        self._scope_operation(scope, operation)
        _guard(before_read)
        self._current()
        selected = self._selection(scope)
        definitions = tuple(dict(capability_id=item.capability_id, card=item.card,
            required_permissions=item.required_permissions, continuation_schemas=item.continuation_schemas)
            for item in selected)
        _guard(before_read)
        self._current()
        if self._selection(scope) != selected:
            raise CoreWorkflowError('bootstrap_selection_changed')
        self._current()
        existing = {item.capability_id for item in self._directory.list(scope)}
        for item in selected:
            if item.capability_id not in existing:
                self._registered(item)
        return self._directory.register_many(scope=scope, definitions=definitions)

    def _before_resolve(self, scope: CoreWorkflowScope, capability: CoreWorkflowCapability) -> None:
        self.guard(scope, 'start', capability)
        definition = next(item for item in self._bootstrap.definitions
                          if item.capability_id == capability.capability_id)
        self._registered(definition)
        self._current()

    def web_guard(self, *, connection: Any, request_user_id: str, scope: CoreWorkflowScope,
                  operation: str) -> Callable[[CoreWorkflowCapability | None], None]:
        self._scope_operation(scope, operation)
        if type(request_user_id) is not str or connection is None:
            raise CoreWorkflowError('invalid_web_caller')
        def check(capability):
            self.guard(scope, operation, capability)
            _guard(lambda: self._bootstrap.authorize_web(connection=connection,
                request_user_id=request_user_id, scope=scope, operation=operation, capability=capability))
            self.guard(scope, operation, capability)
        return check


def install_core_workflow_bootstrap(manager: Any, bootstrap: CoreWorkflowBootstrap | None) -> InstalledCoreWorkflowHost | None:
    existing = getattr(manager, 'core_workflow_host', None)
    if existing is not None:
        if type(existing) is not InstalledCoreWorkflowHost or existing._manager is not manager:
            raise CoreWorkflowError('bootstrap_already_installed')
        if bootstrap is not None and existing.bootstrap is not bootstrap:
            raise CoreWorkflowError('bootstrap_already_installed')
        existing._current()
        return existing
    if bootstrap is None:
        return None
    if type(bootstrap) is not CoreWorkflowBootstrap or type(manager.core_workflow_capabilities) is not CoreWorkflowCapabilities:
        raise CoreWorkflowError('invalid_bootstrap_installation')
    installed = InstalledCoreWorkflowHost(manager, bootstrap)
    for definition in bootstrap.definitions:
        installed._registered(definition)
    # All declaration/SDK checks precede mutation; a conflicting directory hook
    # rejects without replacing either the current manager or any SDK resource.
    installed._directory.bind_resolution_guard(installed._resolution_hook)
    manager.core_workflow_host = installed
    return installed
