# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Typed application entry to the production Task authority resolver."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from jiuwenswarm.common.schema.live_voice_contract_v2 import ErrorCode


if TYPE_CHECKING:
    from jiuwenswarm.server.runtime.formal_tasks.production_task_intent import (
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

        from jiuwenswarm.server.runtime.formal_tasks.production_task_intent import (
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


__all__ = ["TaskIntentDisposition", "UnifiedCommittedInputRoute", "VoiceTaskBridge", "VoiceTaskBridgeViolation"]
