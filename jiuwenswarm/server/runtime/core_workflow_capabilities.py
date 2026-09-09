# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Explicit host authorization metadata and thin Core Workflow SDK adapters.

The trusted host registers cards already installed in the SDK registry. This
directory is empty by default and never registers SDK providers itself. Scope
and permission metadata do not grant authority: callers supply a synchronous
guard for every provider-resolution and execution boundary.

The common execution owner retains run identity, revision, replay protection,
the private SDK session ID and the last real pending interaction outputs. This
module owns none of their lifecycle and must not be exposed directly as a wire
endpoint. An INPUT_REQUIRED result is a checkpoint continuation, not completion.
"""

from __future__ import annotations

import hashlib
import inspect
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from jsonschema.validators import validator_for
from pydantic import BaseModel
from referencing import Registry

from openjiuwen.core.runner import Runner
from openjiuwen.core.session import InteractionOutput, InteractiveInput
from openjiuwen.core.workflow import Workflow, WorkflowCard, WorkflowOutput


class CoreWorkflowError(ValueError):
    """A rejected host binding or input, before entering SDK execution."""


def _identity(value: object) -> None:
    if type(value) is not str or not value or value.strip() != value or "\x00" in value:
        raise CoreWorkflowError("invalid_identity")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise CoreWorkflowError("invalid_identity") from exc


def _json_text(value: Any) -> str:
    def check(item):
        if type(item) is dict:
            for key, child in item.items():
                if type(key) is not str:
                    raise CoreWorkflowError("invalid_json")
                check(child)
        elif type(item) is list:
            for child in item:
                check(child)
        elif item is not None and type(item) not in (str, int, float, bool):
            raise CoreWorkflowError("invalid_json")

    try:
        check(value)
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (ValueError, TypeError, RecursionError) as exc:
        raise CoreWorkflowError("invalid_json") from exc


def _schema_text(schema: Any) -> str:
    if isinstance(schema, type) and issubclass(schema, BaseModel):
        schema = schema.model_json_schema()
    if type(schema) is not dict:
        raise CoreWorkflowError("missing_schema")
    text = _json_text(schema)
    try:
        validator_for(schema).check_schema(schema)
    except Exception as exc:
        raise CoreWorkflowError("invalid_schema") from exc
    return text


def _validate(value: Any, schema_text: str) -> Any:
    # Snapshot JSON without coercing values; never fetch remote schema refs.
    snapshot = json.loads(_json_text(value))
    schema = json.loads(schema_text)
    try:
        validator_for(schema)(schema, registry=Registry()).validate(snapshot)
    except Exception as exc:
        raise CoreWorkflowError("invalid_input") from exc
    return snapshot


def _card_text(card: WorkflowCard) -> str:
    if not isinstance(card, WorkflowCard):
        raise CoreWorkflowError("invalid_card")
    _identity(card.id)
    if type(card.version) is not str:
        raise CoreWorkflowError("invalid_card")
    data = card.model_dump(exclude={"input_params"})
    data["input_params"] = json.loads(_schema_text(card.input_params))
    return _json_text(data)


def _guard(before_effect: Callable[[], None]) -> None:
    if not callable(before_effect):
        raise CoreWorkflowError("missing_authority_guard")
    result = before_effect()
    if inspect.isawaitable(result):
        if inspect.iscoroutine(result):
            result.close()
        raise CoreWorkflowError("authority_guard_must_be_synchronous")
    if result is not None:
        raise CoreWorkflowError("authority_guard_must_return_none")


@dataclass(frozen=True, slots=True)
class CoreWorkflowScope:
    channel_id: str
    session_id: str
    project_id: str | None
    agent_mode: str

    def __post_init__(self):
        for value in (self.channel_id, self.session_id, self.agent_mode):
            _identity(value)
        if self.project_id is not None:
            _identity(self.project_id)


@dataclass(frozen=True, slots=True)
class CoreWorkflowCapability:
    capability_id: str
    scope: CoreWorkflowScope
    sdk_id: str
    sdk_version: str
    required_permissions: tuple[str, ...]
    card_fingerprint: str
    input_schema_fingerprint: str
    _card_json: str = field(repr=False)
    _input_schema_json: str = field(repr=False)
    _continuation_json: tuple[tuple[str, str], ...] = field(repr=False)

    @property
    def input_schema(self) -> dict:
        return json.loads(self._input_schema_json)

    @property
    def continuation_schemas(self) -> dict[str, dict]:
        return {node: json.loads(schema) for node, schema in self._continuation_json}


@dataclass(frozen=True, slots=True, init=False)
class ResolvedCoreWorkflow:
    """Opaque directory-issued binding; the workflow instance stays internal."""

    capability: CoreWorkflowCapability
    _workflow: Workflow = field(repr=False)
    _issuer: object = field(repr=False)


class CoreWorkflowCapabilities:
    def __init__(self):
        self._entries: dict[tuple[CoreWorkflowScope, str], CoreWorkflowCapability] = {}
        self._issuer = object()
        self._resolution_guard = None

    def register(self, *, scope: CoreWorkflowScope, capability_id: str,
                 card: WorkflowCard, required_permissions: tuple[str, ...],
                 continuation_schemas: Mapping[str, dict] | None = None) -> CoreWorkflowCapability:
        """Allowlist an already-registered SDK card from trusted host bootstrap."""
        self._check_scope(scope)
        _identity(capability_id)
        if type(required_permissions) is not tuple:
            raise CoreWorkflowError("invalid_permissions")
        for permission in required_permissions:
            _identity(permission)
        if len(set(required_permissions)) != len(required_permissions):
            raise CoreWorkflowError("invalid_permissions")
        key = (scope, capability_id)
        if key in self._entries:
            raise CoreWorkflowError("already_registered")
        card_json = _card_text(card)
        input_json = _schema_text(card.input_params)
        continuation = []
        if continuation_schemas is not None and not isinstance(continuation_schemas, Mapping):
            raise CoreWorkflowError("invalid_continuation_schema")
        for node, schema in (continuation_schemas or {}).items():
            _identity(node)
            continuation.append((node, _schema_text(schema)))
        metadata = CoreWorkflowCapability(capability_id, scope, card.id, card.version,
            required_permissions, hashlib.sha256(card_json.encode()).hexdigest(),
            hashlib.sha256(input_json.encode()).hexdigest(), card_json, input_json,
            tuple(sorted(continuation)))
        self._entries[key] = metadata
        return metadata

    def register_many(self, *, scope: CoreWorkflowScope,
                      definitions: Sequence[Mapping[str, Any]]) -> tuple[CoreWorkflowCapability, ...]:
        """Atomically bind trusted metadata; equal repeats retain original objects."""
        self._check_scope(scope)
        if not isinstance(definitions, (tuple, list)):
            raise CoreWorkflowError("invalid_definitions")
        staged = CoreWorkflowCapabilities()
        required = {"capability_id", "card", "required_permissions"}
        for definition in definitions:
            if (not isinstance(definition, Mapping) or not required <= set(definition)
                    or set(definition) - required - {"continuation_schemas"}):
                raise CoreWorkflowError("invalid_definition")
            staged.register(scope=scope, **definition)
        additions = {}
        result = []
        for candidate in staged.list(scope):
            key = (scope, candidate.capability_id)
            existing = self._entries.get(key)
            if existing is not None and existing != candidate:
                raise CoreWorkflowError("registration_conflict")
            if existing is None:
                additions[key] = candidate
            result.append(existing if existing is not None else candidate)
        if additions and len(self._entries) + len(additions) > 128:
            raise CoreWorkflowError("registration_capacity")
        # All validation precedes this synchronous commit. Existing resolved
        # runs retain the original metadata/issuer and are never replaced.
        self._entries.update(additions)
        return tuple(result)

    def bind_resolution_guard(self, callback: Callable[[CoreWorkflowScope, CoreWorkflowCapability], None]) -> None:
        """Install one trusted new-resolution guard, never a continuation hook."""
        if not callable(callback):
            raise CoreWorkflowError("invalid_resolution_guard")
        if self._resolution_guard is not None and self._resolution_guard is not callback:
            raise CoreWorkflowError("resolution_guard_already_bound")
        self._resolution_guard = callback

    @staticmethod
    def _check_scope(scope: CoreWorkflowScope) -> None:
        if type(scope) is not CoreWorkflowScope:
            raise CoreWorkflowError("invalid_scope")

    def list(self, scope: CoreWorkflowScope) -> tuple[CoreWorkflowCapability, ...]:
        self._check_scope(scope)
        return tuple(entry for (entry_scope, _), entry in self._entries.items() if entry_scope == scope)

    def get(self, *, scope: CoreWorkflowScope, capability_id: str) -> CoreWorkflowCapability:
        """Read exact trusted metadata without resolving a provider."""
        self._check_scope(scope)
        _identity(capability_id)
        entry = self._entries.get((scope, capability_id))
        if entry is None:
            raise CoreWorkflowError("not_registered")
        return entry

    def validate_inputs(self, *, scope: CoreWorkflowScope, capability_id: str, inputs: Any) -> Any:
        entry = self.get(scope=scope, capability_id=capability_id)
        return _validate(inputs, entry._input_schema_json)

    def validate_answers(self, *, scope: CoreWorkflowScope, capability_id: str,
                         pending: Sequence[InteractionOutput], answers: Mapping[str, Any]) -> dict:
        """Pure schema validation; only the common owner proves pending/CAS."""
        entry = self.get(scope=scope, capability_id=capability_id)
        if not isinstance(pending, Sequence) or not pending or not isinstance(answers, Mapping):
            raise CoreWorkflowError("invalid_continuation")
        nodes = []
        for output in pending:
            if not isinstance(output, InteractionOutput):
                raise CoreWorkflowError("invalid_continuation")
            _identity(output.id)
            nodes.append(output.id)
        if len(nodes) != len(set(nodes)) or set(nodes) != set(answers):
            raise CoreWorkflowError("pending_input_mismatch")
        schemas = dict(entry._continuation_json)
        if any(node not in schemas for node in nodes):
            raise CoreWorkflowError("unregistered_continuation")
        validated = {node: _validate(answers[node], schemas[node]) for node in nodes}
        if any(value is None for value in validated.values()):
            raise CoreWorkflowError("invalid_continuation")
        return validated

    async def resolve(self, *, scope: CoreWorkflowScope, capability_id: str,
                      before_effect: Callable[[], None]) -> ResolvedCoreWorkflow:
        entry = self.get(scope=scope, capability_id=capability_id)
        _guard(before_effect)
        resolution_guard = self._resolution_guard
        if resolution_guard is not None:
            _guard(lambda: resolution_guard(scope, entry))
        workflow = await Runner.resource_mgr.get_workflow(workflow_id=entry.sdk_id)
        if resolution_guard is not None:
            _guard(before_effect)
            _guard(lambda: resolution_guard(scope, entry))
        self._check_card(workflow, entry)
        binding = object.__new__(ResolvedCoreWorkflow)
        object.__setattr__(binding, "capability", entry)
        object.__setattr__(binding, "_workflow", workflow)
        object.__setattr__(binding, "_issuer", self._issuer)
        return binding

    @staticmethod
    def _check_card(workflow: Workflow, entry: CoreWorkflowCapability) -> None:
        if not isinstance(workflow, Workflow):
            raise CoreWorkflowError("workflow_unavailable")
        if _card_text(workflow.card) != entry._card_json:
            raise CoreWorkflowError("card_mismatch")

    def _check_binding(self, scope, binding, sdk_session_id):
        self._check_scope(scope)
        _identity(sdk_session_id)
        if (type(binding) is not ResolvedCoreWorkflow
                or getattr(binding, "_issuer", None) is not self._issuer):
            raise CoreWorkflowError("invalid_binding")
        entry = binding.capability
        if entry.scope != scope or self._entries.get((scope, entry.capability_id)) is not entry:
            raise CoreWorkflowError("invalid_binding")
        self._check_card(binding._workflow, entry)
        return entry

    async def invoke(self, *, scope: CoreWorkflowScope, binding: ResolvedCoreWorkflow,
                     sdk_session_id: str, inputs: Any,
                     before_effect: Callable[[], None]) -> WorkflowOutput:
        entry = self._check_binding(scope, binding, sdk_session_id)
        snapshot = _validate(inputs, entry._input_schema_json)
        _guard(before_effect)
        return await Runner.run_workflow(binding._workflow, snapshot, session=sdk_session_id)

    async def continue_workflow(self, *, scope: CoreWorkflowScope, binding: ResolvedCoreWorkflow,
                                sdk_session_id: str, pending: Sequence[InteractionOutput],
                                answers: Mapping[str, Any],
                                before_effect: Callable[[], None], resume_guard: Any = None) -> WorkflowOutput:
        """Continue exactly the pending outputs retained by the common run owner.

        The host must admit the current run/revision before calling; matching a
        caller-fabricated InteractionOutput is not proof that an input is pending.
        """
        entry = self._check_binding(scope, binding, sdk_session_id)
        validated = self.validate_answers(scope=scope, capability_id=entry.capability_id,
            pending=pending, answers=answers)
        interactive = InteractiveInput()
        for node, value in validated.items():
            interactive.update(node, value)
        _guard(before_effect)
        options = {"resume_guard": resume_guard} if resume_guard is not None else {}
        return await Runner.run_workflow(binding._workflow, interactive, session=sdk_session_id, **options)
