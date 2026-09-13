# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Deterministic Task authority bridge; semantics live only in task_semantics."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    ErrorCode,
    InputCommitState,
    ScopeRef,
)

from .task_core import TaskCommand, TaskSpec

if TYPE_CHECKING:
    from .production_task_intent import (
        BoundedClarificationOwner,
        ProductionConfirmationConsumer,
        ProductionOriginAuthority,
        ProductionTaskAuthorityReader,
        ProductionTaskIntentRequest,
        ProductionTaskResolution,
    )


class VoiceTaskBridgeViolation(ValueError):
    def __init__(self, reason: str, message: str, code: ErrorCode) -> None:
        super().__init__(message)
        self.reason = reason
        self.code = code


class TaskIntentDisposition(StrEnum):
    DISPATCHED = "dispatched"
    CLARIFICATION = "clarification"
    REJECTED = "rejected"


class UnifiedCommittedInputRoute(StrEnum):
    """Closed presentation routes; legacy values are read-only protocol compatibility."""

    TASK = "task"

    DIALOGUE = "dialogue"
    BACKGROUND_CREATE = "background.create"
    BACKGROUND_UPDATE = "background.update"
    BACKGROUND_QUERY = "background.query"
    BACKGROUND_STATUS = "background.status"
    BACKGROUND_CANCEL = "background.cancel"


@dataclass(frozen=True, slots=True)
class TaskIntent:
    state: InputCommitState
    operation: str
    request_id: str
    command_id: str
    scope: ScopeRef
    origin_commit_id: str | None
    task_id: str | None = None
    name: str | None = None
    instruction: str | None = None
    ambiguous: bool = False
    destructive: bool = False
    confirmed: bool = False


class VoiceTaskBridge:
    def resolve_production(
        self,
        request: ProductionTaskIntentRequest,
        authority: ProductionTaskAuthorityReader,
        origin_authority: ProductionOriginAuthority,
        confirmation_consumer: ProductionConfirmationConsumer,
        clarification_owner: BoundedClarificationOwner,
    ) -> ProductionTaskResolution:
        """Run the generalized production resolver through the real Bridge.

        The injected authority exposes authenticated Core reads only.  The
        origin, confirmation and clarification authorities are mandatory and
        separate. The Bridge cannot substitute proposal data for their receipts.
        """

        from .production_task_intent import (
            BoundedClarificationOwner,
            ProductionMultiTaskResolver,
            ProductionConfirmationConsumer,
            ProductionOriginAuthority,
            ProductionTaskAuthorityReader,
            ProductionTaskIntentRequest,
        )

        if not isinstance(request, ProductionTaskIntentRequest):
            raise VoiceTaskBridgeViolation(
                "INVALID_PRODUCTION_TASK_INTENT_REQUEST",
                "production task resolution requires one closed request",
                ErrorCode.INVALID_ARGUMENT,
            )
        if not isinstance(authority, ProductionTaskAuthorityReader):
            raise VoiceTaskBridgeViolation(
                "AUTHENTICATED_TASK_AUTHORITY_REQUIRED",
                "production task resolution requires authenticated Core reads",
                ErrorCode.UNAVAILABLE,
            )
        if not isinstance(origin_authority, ProductionOriginAuthority):
            raise VoiceTaskBridgeViolation(
                "TRUSTED_ORIGIN_AUTHORITY_REQUIRED",
                "production resolution requires trusted committed-origin proof",
                ErrorCode.UNAVAILABLE,
            )
        if not isinstance(confirmation_consumer, ProductionConfirmationConsumer):
            raise VoiceTaskBridgeViolation(
                "TRUSTED_CONFIRMATION_CONSUMER_REQUIRED",
                "production resolution requires atomic confirmation consumption",
                ErrorCode.UNAVAILABLE,
            )
        if not isinstance(clarification_owner, BoundedClarificationOwner):
            raise VoiceTaskBridgeViolation(
                "TRUSTED_CLARIFICATION_OWNER_REQUIRED",
                "production resolution requires clarification CAS authority",
                ErrorCode.UNAVAILABLE,
            )
        return ProductionMultiTaskResolver(clarification_owner).resolve(
            request, authority, origin_authority, confirmation_consumer
        )

    def map(self, intent: TaskIntent, authorized_scope: ScopeRef) -> TaskCommand:
        if intent.state is not InputCommitState.COMMITTED:
            raise VoiceTaskBridgeViolation(
                "INPUT_NOT_COMMITTED",
                "partial or uncommitted speech cannot create Task commands",
                ErrorCode.PERMISSION_DENIED,
            )
        if intent.scope != authorized_scope:
            raise VoiceTaskBridgeViolation(
                "TASK_SCOPE_MISMATCH",
                "voice intent must match the exact authorized scope",
                ErrorCode.PERMISSION_DENIED,
            )
        if intent.ambiguous:
            raise VoiceTaskBridgeViolation(
                "TASK_INTENT_AMBIGUOUS",
                "ambiguous task intent requires clarification",
                ErrorCode.INVALID_ARGUMENT,
            )
        if intent.destructive and not intent.confirmed:
            raise VoiceTaskBridgeViolation(
                "TASK_CONFIRMATION_REQUIRED",
                "destructive task intent requires explicit confirmation",
                ErrorCode.PERMISSION_DENIED,
            )
        if not intent.origin_commit_id:
            raise VoiceTaskBridgeViolation(
                "COMMITTED_ORIGIN_REQUIRED",
                "Task commands require a committed turn origin",
                ErrorCode.PERMISSION_DENIED,
            )
        if intent.operation == "task.create":
            if intent.task_id is not None or not intent.name or not intent.instruction:
                raise VoiceTaskBridgeViolation(
                    "INVALID_TASK_CREATE_INTENT",
                    "create intent requires name and instruction but no task id",
                    ErrorCode.INVALID_ARGUMENT,
                )
            spec = TaskSpec(intent.name, intent.instruction)
            target_task_id = None
        elif intent.operation == "task.cancel":
            if intent.task_id is None:
                raise VoiceTaskBridgeViolation(
                    "EXACT_TASK_REQUIRED",
                    "cancel intent requires an exact task id",
                    ErrorCode.INVALID_ARGUMENT,
                )
            spec = None
            target_task_id = intent.task_id
        else:
            raise VoiceTaskBridgeViolation(
                "UNSUPPORTED_TASK_INTENT",
                f"unsupported task intent {intent.operation!r}",
                ErrorCode.UNSUPPORTED,
            )
        return TaskCommand(
            request_id=intent.request_id,
            command_id=intent.command_id,
            operation=intent.operation,
            scope=intent.scope,
            target_task_id=target_task_id,
            spec=spec,
            origin_commit_id=intent.origin_commit_id,
        )


__all__ = ["TaskIntent", "TaskIntentDisposition", "UnifiedCommittedInputRoute", "VoiceTaskBridge", "VoiceTaskBridgeViolation"]
