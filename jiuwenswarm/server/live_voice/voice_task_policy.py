# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""VB-B policy adapter for formal Task Core commands and queries.

This module maps already-resolved intent.  It does not authenticate a caller,
resolve project context, execute a task, persist lifecycle state, or invoke TTS.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    CONTRACT_VERSION,
    CommandEnvelope,
    ContractViolation,
    ErrorCode,
    InputCommitState,
    OriginRef,
    QueryEnvelope,
    ScopeRef,
    TurnCommit,
    TurnCommitLedger,
)

from .formal_task_models import (
    FormalTaskViolation,
    ResolvedTaskContext,
    TaskAuthorizationGrant,
    TaskRetryPrecondition,
    TaskRetryProductRequestFingerprint,
)


@dataclass(frozen=True, slots=True)
class FormalTaskPolicyInput:
    """A committed semantic decision plus separate trusted policy artifacts."""

    state: InputCommitState
    source: str
    operation: str
    request_id: str
    issued_at: str
    scope: ScopeRef
    correlation_id: str
    authorization: TaskAuthorizationGrant | None
    command_id: str | None = None
    causation_id: str | None = None
    interaction_id: str | None = None
    turn_id: str | None = None
    commit_id: str | None = None
    origin_commit_sha256: str | None = None
    source_start: int | None = None
    source_end: int | None = None
    task_id: str | None = None
    name: str | None = None
    instruction: str | None = None
    context: ResolvedTaskContext | None = None
    attributes: Mapping[str, str] = field(default_factory=dict)
    ambiguous: bool = False
    destructive: bool = False
    confirmed: bool = False
    confirmation_id: str | None = None
    policy_bypass: str | None = None
    current_task_binding: bool = False
    after_seq: int = -1
    retry_precondition: TaskRetryPrecondition | None = None
    retry_product_request: TaskRetryProductRequestFingerprint | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.attributes, Mapping):
            raise FormalTaskViolation(
                "INVALID_FORMAL_TASK_ATTRIBUTES",
                "task intent attributes must be an object",
                ErrorCode.INVALID_ARGUMENT,
            )
        if any(
            type(key) is not str
            or not key.strip()
            or type(value) is not str
            or not value.strip()
            for key, value in self.attributes.items()
        ):
            raise FormalTaskViolation(
                "INVALID_FORMAL_TASK_ATTRIBUTES",
                "task intent attributes must be non-empty string facts",
                ErrorCode.INVALID_ARGUMENT,
            )
        if set(self.attributes) - {"model_identity", "model_config_version"}:
            raise FormalTaskViolation(
                "UNSUPPORTED_FORMAL_TASK_ATTRIBUTE",
                "project task intent accepts only server-resolved model binding facts",
                ErrorCode.UNSUPPORTED,
            )
        if self.attributes and set(self.attributes) != {
            "model_identity",
            "model_config_version",
        }:
            raise FormalTaskViolation(
                "INVALID_FORMAL_TASK_ATTRIBUTES",
                "project task intent requires a complete resolved model binding",
                ErrorCode.INVALID_ARGUMENT,
            )
        object.__setattr__(self, "attributes", MappingProxyType(dict(self.attributes)))


@dataclass(frozen=True, slots=True)
class FormalTaskInvocation:
    envelope: CommandEnvelope | QueryEnvelope
    authorization: TaskAuthorizationGrant
    context: ResolvedTaskContext | None


class FormalTaskPolicyAdapter:
    """Fail closed before a formal command/query reaches the Task Core."""

    _QUERIES = frozenset({"task.get", "task.list", "task.status", "task.events"})
    _COMMANDS = frozenset({"task.create", "task.cancel", "task.retry"})

    def __init__(self, commits: TurnCommitLedger | None = None) -> None:
        self._commits = commits

    def map(self, intent: FormalTaskPolicyInput) -> FormalTaskInvocation:
        self._validate_common(intent)
        self._require_committed_origin(intent)
        if intent.operation in self._COMMANDS:
            envelope = self._command(intent)
            destructive = True
            command_id = envelope.command_id
            target_task_id = (
                None if intent.operation == "task.create" else envelope.target_ref.id
            )
        elif intent.operation in self._QUERIES:
            envelope = self._query(intent)
            destructive = False
            command_id = None
            target_task_id = (
                None if intent.operation == "task.list" else envelope.target_ref.id
            )
        else:
            raise FormalTaskViolation(
                "UNSUPPORTED_FORMAL_TASK_INTENT",
                f"unsupported formal task operation {intent.operation!r}",
                ErrorCode.UNSUPPORTED,
            )
        assert intent.authorization is not None
        intent.authorization.authorize(
            scope=intent.scope,
            operation=intent.operation,
            command_id=command_id,
            target_task_id=target_task_id,
            required_capabilities=frozenset(envelope.required_capabilities),
            destructive=destructive,
            now=intent.issued_at,
        )
        return FormalTaskInvocation(envelope, intent.authorization, intent.context)

    def _require_committed_origin(self, intent: FormalTaskPolicyInput) -> None:
        if intent.source not in {"voice", "text"}:
            return
        if self._commits is None:
            raise FormalTaskViolation(
                "COMMIT_AUTHORITY_REQUIRED",
                "natural-language task intent requires the authoritative turn commit ledger",
                ErrorCode.UNAVAILABLE,
            )
        try:
            commit = self._commits.require_origin(
                OriginRef("committed_turn", intent.turn_id, intent.commit_id),
                intent.scope,
            )
        except ContractViolation as error:
            raise FormalTaskViolation(error.reason, str(error), error.code) from error
        if intent.interaction_id != commit.interaction_id:
            raise FormalTaskViolation(
                "TASK_INTENT_INTERACTION_MISMATCH",
                "natural-language task intent must bind the exact committed interaction",
                ErrorCode.PERMISSION_DENIED,
            )
        commit_sha256 = hashlib.sha256(commit.canonical_bytes()).hexdigest()
        if (
            intent.origin_commit_sha256 is not None
            and intent.origin_commit_sha256 != commit_sha256
        ):
            raise FormalTaskViolation(
                "TASK_INTENT_COMMIT_MISMATCH",
                "natural-language task intent must bind the exact committed content",
                ErrorCode.PERMISSION_DENIED,
            )
        if intent.operation == "task.create":
            if intent.source_start is None and intent.source_end is None:
                # Compatibility for the older exact-full-commit voice create
                # path.  The formal Voice--Task Bridge always supplies a span.
                matches = intent.instruction == commit.text
            else:
                matches = (
                    type(intent.source_start) is int
                    and type(intent.source_end) is int
                    and 0 <= intent.source_start < intent.source_end <= len(commit.text)
                    and commit.text[intent.source_start : intent.source_end]
                    == intent.instruction
                )
            if not matches:
                raise FormalTaskViolation(
                    (
                        "VOICE_TASK_INSTRUCTION_MISMATCH"
                        if intent.source == "voice"
                        and intent.source_start is None
                        and intent.source_end is None
                        else "TASK_INTENT_SOURCE_SPAN_MISMATCH"
                    ),
                    "task instruction must equal its exact committed source span",
                    ErrorCode.PERMISSION_DENIED,
                )
        elif intent.source_start is not None or intent.source_end is not None:
            current_binding_matches = (
                intent.operation == "task.cancel"
                and intent.current_task_binding
                and intent.source_start == 0
                and intent.source_end == len(commit.text)
            )
            if (
                type(intent.source_start) is not int
                or type(intent.source_end) is not int
                or not 0 <= intent.source_start < intent.source_end <= len(commit.text)
                or intent.task_id is None
                or (
                    not current_binding_matches
                    and commit.text[intent.source_start : intent.source_end]
                    != intent.task_id
                )
            ):
                raise FormalTaskViolation(
                    "TASK_INTENT_SOURCE_SPAN_MISMATCH",
                    "targeted task intent must equal its exact committed source span",
                    ErrorCode.PERMISSION_DENIED,
                )

    def require_voice_origin(
        self,
        *,
        scope: ScopeRef,
        interaction_id: str,
        turn_id: str,
        commit_id: str,
        instruction: str,
    ) -> TurnCommit:
        """Preflight exact voice authority before durable confirmation issue."""

        if self._commits is None:
            raise FormalTaskViolation(
                "COMMIT_AUTHORITY_REQUIRED",
                "voice task intent requires the authoritative turn commit ledger",
                ErrorCode.UNAVAILABLE,
            )
        try:
            commit = self._commits.require_origin(
                OriginRef("committed_turn", turn_id, commit_id), scope
            )
        except ContractViolation as error:
            raise FormalTaskViolation(error.reason, str(error), error.code) from error
        if commit.interaction_id != interaction_id:
            raise FormalTaskViolation(
                "VOICE_TASK_INTERACTION_MISMATCH",
                "voice task intent must bind the exact committed interaction",
                ErrorCode.PERMISSION_DENIED,
            )
        if commit.text != instruction:
            raise FormalTaskViolation(
                "VOICE_TASK_INSTRUCTION_MISMATCH",
                "voice task instruction must equal its exact committed speech text",
                ErrorCode.PERMISSION_DENIED,
            )
        return commit

    def require_committed_origin(
        self,
        *,
        scope: ScopeRef,
        interaction_id: str,
        turn_id: str,
        commit_id: str,
        commit_sha256: str,
        operation: str,
        instruction: str | None,
        task_id: str | None,
        source_start: int,
        source_end: int,
    ) -> TurnCommit:
        """Preflight the content-bound natural-language resolver result."""

        probe = FormalTaskPolicyInput(
            state=InputCommitState.COMMITTED,
            source="text",
            operation=operation,
            request_id="preflight",
            issued_at="1970-01-01T00:00:00Z",
            scope=scope,
            correlation_id="preflight",
            authorization=None,
            interaction_id=interaction_id,
            turn_id=turn_id,
            commit_id=commit_id,
            origin_commit_sha256=commit_sha256,
            source_start=source_start,
            source_end=source_end,
            instruction=instruction,
            task_id=task_id,
        )
        self._require_committed_origin(probe)
        assert self._commits is not None
        try:
            return self._commits.require_origin(
                OriginRef("committed_turn", turn_id, commit_id), scope
            )
        except ContractViolation as error:
            raise FormalTaskViolation(error.reason, str(error), error.code) from error

    @staticmethod
    def _validate_common(intent: FormalTaskPolicyInput) -> None:
        if intent.state is not InputCommitState.COMMITTED:
            raise FormalTaskViolation(
                "INPUT_NOT_COMMITTED",
                "partial or uncommitted input cannot reach formal Task Core",
                ErrorCode.PERMISSION_DENIED,
            )
        if intent.source not in {"voice", "text", "structured"}:
            raise FormalTaskViolation(
                "INVALID_TASK_INTENT_SOURCE",
                "formal task intent source must be voice, text or structured",
                ErrorCode.INVALID_ARGUMENT,
            )
        if intent.ambiguous:
            raise FormalTaskViolation(
                "TASK_INTENT_AMBIGUOUS",
                "ambiguous task intent requires clarification",
                ErrorCode.INVALID_ARGUMENT,
            )
        if intent.authorization is None:
            raise FormalTaskViolation(
                "FORMAL_TASK_AUTHORIZATION_REQUIRED",
                "request-derived identity cannot substitute for trusted authorization",
                ErrorCode.UNAUTHENTICATED,
            )
        if intent.operation != "task.retry" and (
            intent.retry_precondition is not None
            or intent.retry_product_request is not None
        ):
            raise FormalTaskViolation(
                "INVALID_TASK_RETRY_INTENT",
                "only task.retry may carry server-derived retry lineage",
                ErrorCode.INVALID_ARGUMENT,
            )
        if type(intent.current_task_binding) is not bool or (
            intent.current_task_binding
            and not (
                intent.source == "voice" and intent.operation == "task.cancel"
            )
        ):
            raise FormalTaskViolation(
                "INVALID_CURRENT_TASK_BINDING",
                "current-task binding is valid only for voice cancellation",
                ErrorCode.INVALID_ARGUMENT,
            )
        if intent.source in {"voice", "text"}:
            if not intent.interaction_id or not intent.turn_id or not intent.commit_id:
                raise FormalTaskViolation(
                    "COMMITTED_ORIGIN_REQUIRED",
                    "natural-language task intent requires the exact committed turn origin",
                    ErrorCode.PERMISSION_DENIED,
                )
            if (intent.source == "text" or intent.operation == "task.cancel") and (
                not intent.origin_commit_sha256
                or type(intent.source_start) is not int
                or type(intent.source_end) is not int
            ):
                raise FormalTaskViolation(
                    "TASK_INTENT_SOURCE_BINDING_REQUIRED",
                    "text task intent requires its commit digest and exact source span",
                    ErrorCode.PERMISSION_DENIED,
                )
        elif (
            intent.interaction_id is not None
            or intent.turn_id is not None
            or intent.commit_id is not None
            or intent.origin_commit_sha256 is not None
            or intent.source_start is not None
            or intent.source_end is not None
        ):
            raise FormalTaskViolation(
                "INVALID_STRUCTURED_ORIGIN",
                "structured task intent cannot claim a voice commit",
                ErrorCode.INVALID_ARGUMENT,
            )

    def _command(self, intent: FormalTaskPolicyInput) -> CommandEnvelope:
        if not intent.command_id:
            raise FormalTaskViolation(
                "TASK_COMMAND_ID_REQUIRED",
                "formal task mutation requires a stable command id",
                ErrorCode.INVALID_ARGUMENT,
            )
        confirmed_boundary = intent.confirmed and bool(intent.confirmation_id)
        bypass_boundary = (
            not intent.confirmed
            and intent.confirmation_id is None
            and intent.policy_bypass == "trusted_demo_live_voice_v1"
        )
        if not intent.destructive or not (confirmed_boundary or bypass_boundary):
            raise FormalTaskViolation(
                "TASK_CONFIRMATION_REQUIRED",
                "formal project mutation requires confirmation or trusted policy",
                ErrorCode.PERMISSION_DENIED,
            )
        assert intent.authorization is not None
        if (
            intent.authorization.confirmation_id != intent.confirmation_id
            or intent.authorization.policy_bypass != intent.policy_bypass
        ):
            raise FormalTaskViolation(
                "TASK_CONFIRMATION_MISMATCH",
                "trusted authorization does not bind the exact mutation policy",
                ErrorCode.PERMISSION_DENIED,
            )
        if intent.operation == "task.create":
            if intent.task_id is not None or not intent.name or not intent.instruction:
                raise FormalTaskViolation(
                    "INVALID_TASK_CREATE_INTENT",
                    "task.create requires exact name and instruction but no existing task id",
                    ErrorCode.INVALID_ARGUMENT,
                )
            if intent.context is None:
                raise FormalTaskViolation(
                    "FORMAL_TASK_CONTEXT_REQUIRED",
                    "task.create requires server-resolved project context",
                    ErrorCode.PERMISSION_DENIED,
                )
            if intent.after_seq != -1:
                raise FormalTaskViolation(
                    "INVALID_TASK_CREATE_INTENT",
                    "task.create cannot carry an event cursor",
                    ErrorCode.INVALID_ARGUMENT,
                )
            payload: dict[str, object] = {
                "name": intent.name,
                "instruction": intent.instruction,
                "executor_id": "jiuwenswarm_code_agent.project_code",
                "side_effect_class": "project_mutation",
                "attributes": dict(intent.attributes),
            }
            target_id = f"create:{intent.command_id}"
            extensions: dict[str, object] = {}
        elif intent.operation == "task.retry":
            # Every predecessor fact below is Store-derived by the composition
            # owner.  The external request submits only ``task_id``; this
            # adapter never accepts a client-declared lineage or attempt number.
            if not intent.task_id:
                raise FormalTaskViolation(
                    "EXACT_TASK_REQUIRED",
                    "task.retry requires an exact formal task id",
                    ErrorCode.INVALID_ARGUMENT,
                )
            if intent.source != "structured":
                raise FormalTaskViolation(
                    "INVALID_TASK_RETRY_INTENT",
                    "task.retry accepts only a structured bounded retry request",
                    ErrorCode.INVALID_ARGUMENT,
                )
            if (
                intent.name is not None
                or intent.instruction is not None
                or bool(intent.attributes)
                or intent.after_seq != -1
            ):
                raise FormalTaskViolation(
                    "INVALID_TASK_RETRY_INTENT",
                    "task.retry cannot replace create-only content",
                    ErrorCode.INVALID_ARGUMENT,
                )
            if intent.context is None:
                raise FormalTaskViolation(
                    "FORMAL_TASK_CONTEXT_REQUIRED",
                    "task.retry requires server-resolved project context",
                    ErrorCode.PERMISSION_DENIED,
                )
            if type(intent.retry_precondition) is not TaskRetryPrecondition:
                raise FormalTaskViolation(
                    "TASK_RETRY_PRECONDITION_REQUIRED",
                    "task.retry requires the server-derived predecessor lineage",
                    ErrorCode.PERMISSION_DENIED,
                )
            if (
                type(intent.retry_product_request)
                is not TaskRetryProductRequestFingerprint
            ):
                raise FormalTaskViolation(
                    "TASK_RETRY_PRODUCT_REQUEST_FINGERPRINT_REQUIRED",
                    "task.retry requires one product-owned request fingerprint",
                    ErrorCode.PERMISSION_DENIED,
                )
            payload = intent.retry_precondition.to_dict()
            target_id = intent.task_id
            extensions = intent.retry_product_request.to_extensions()
        else:
            if not intent.task_id:
                raise FormalTaskViolation(
                    "EXACT_TASK_REQUIRED",
                    "task.cancel requires an exact formal task id",
                    ErrorCode.INVALID_ARGUMENT,
                )
            if (
                intent.context is not None
                or intent.name is not None
                or intent.instruction is not None
                or bool(intent.attributes)
                or intent.after_seq != -1
            ):
                raise FormalTaskViolation(
                    "INVALID_TASK_CANCEL_INTENT",
                    "task.cancel cannot carry create-only context or content",
                    ErrorCode.INVALID_ARGUMENT,
                )
            payload = {}
            target_id = intent.task_id
            extensions = {}
        origin = (
            {
                "kind": "committed_turn",
                "turn_id": intent.turn_id,
                "commit_id": intent.commit_id,
            }
            if intent.source in {"voice", "text"}
            else {"kind": "structured", "turn_id": None, "commit_id": None}
        )
        return CommandEnvelope.from_dict(
            {
                "contract_version": CONTRACT_VERSION,
                "request_id": intent.request_id,
                "command_id": intent.command_id,
                "command_type": intent.operation,
                "issued_at": intent.issued_at,
                "scope": intent.scope.to_dict(),
                "correlation_id": intent.correlation_id,
                "causation_id": intent.causation_id,
                "origin": origin,
                "target_ref": {"kind": "task", "id": target_id},
                "context_refs": [],
                "required_capabilities": [intent.operation],
                "payload": payload,
                "extensions": extensions,
            }
        )

    def _query(self, intent: FormalTaskPolicyInput) -> QueryEnvelope:
        if (
            intent.command_id is not None
            or intent.destructive
            or intent.confirmed
            or intent.confirmation_id is not None
        ):
            raise FormalTaskViolation(
                "INVALID_TASK_QUERY_INTENT",
                "read-only task query cannot claim mutation or confirmation fields",
                ErrorCode.INVALID_ARGUMENT,
            )
        if (
            intent.context is not None
            or intent.name is not None
            or intent.instruction is not None
            or bool(intent.attributes)
        ):
            raise FormalTaskViolation(
                "INVALID_TASK_QUERY_INTENT",
                "read-only task query cannot carry create-only context or content",
                ErrorCode.INVALID_ARGUMENT,
            )
        if intent.operation == "task.list":
            if intent.task_id is not None:
                raise FormalTaskViolation(
                    "INVALID_TASK_LIST_INTENT",
                    "task.list must not select one task",
                    ErrorCode.INVALID_ARGUMENT,
                )
            target_id = "task-list"
        else:
            if not intent.task_id:
                raise FormalTaskViolation(
                    "EXACT_TASK_REQUIRED",
                    "formal task query requires an exact task id",
                    ErrorCode.INVALID_ARGUMENT,
                )
            target_id = intent.task_id
        if intent.operation == "task.events":
            if type(intent.after_seq) is not int or intent.after_seq < -1:
                raise FormalTaskViolation(
                    "INVALID_EVENT_CURSOR",
                    "task.events after_seq must be an integer at least -1",
                    ErrorCode.INVALID_ARGUMENT,
                )
            payload: dict[str, object] = {"after_seq": intent.after_seq}
        else:
            if intent.after_seq != -1:
                raise FormalTaskViolation(
                    "INVALID_TASK_QUERY_CURSOR",
                    "only task.events accepts an event cursor",
                    ErrorCode.INVALID_ARGUMENT,
                )
            payload = {}
        return QueryEnvelope.from_dict(
            {
                "contract_version": CONTRACT_VERSION,
                "request_id": intent.request_id,
                "query_type": intent.operation,
                "issued_at": intent.issued_at,
                "scope": intent.scope.to_dict(),
                "correlation_id": intent.correlation_id,
                "causation_id": intent.causation_id,
                "target_ref": {"kind": "task", "id": target_id},
                "context_refs": [],
                "required_capabilities": [intent.operation],
                "payload": payload,
                "extensions": {},
            }
        )


__all__ = [
    "FormalTaskInvocation",
    "FormalTaskPolicyAdapter",
    "FormalTaskPolicyInput",
]
