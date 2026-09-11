# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Content-free diagnostic projection on the Registry's existing route state.

This mixin owns no constructor, lease, queue or lifecycle. Business authority
remains with Registry; ProductObservabilityAdapter owns export and its worker.
"""

from __future__ import annotations
import hashlib
from dataclasses import replace
from jiuwenswarm.common.schema.live_voice_contract_v2 import CONTRACT_VERSION, ResponseRef, ScopeRef, canonical_json_bytes
from jiuwenswarm.server.runtime.formal_tasks.formal_task_models import OutboxKind, PersistentTaskEvent, utc_now
from jiuwenswarm.server.runtime.formal_tasks.task_store import TaskDurabilityDiagnosticSnapshot
from .observability import OBSERVABILITY_SCHEMA_VERSION, LiveVoiceMetric, LiveVoiceObservation, create_observation, observation_from_task_event
from .product_p2_interaction_adapter import P2LeaseState
from .presentation_ledger import TaskPresentationDelivery
from .task_progress_return import TaskProgressNotificationIntent, TaskProgressTextEvent
from typing import TYPE_CHECKING
import logging

if TYPE_CHECKING:
    from .product_composition_registry import _ProgressDelivery

# Preserve the original logger identity for handlers and diagnostic consumers.
logger = logging.getLogger("jiuwenswarm.server.live_voice.product_composition_registry")


class ProductDiagnosticProjection:
    def consume_product_observation(
        self,
        *,
        session_id: object,
        correlation_id: object,
        observation: object,
        diagnostic_identity: object,
    ) -> bool:
        """Send one AgentServer producer fact through its active X-OBS lease.

        The product adapter remains the sole FIFO/worker owner.  This hook can
        only consume a fact whose session, correlation and interaction bind an
        already-active P2 observability context; it cannot create or widen an
        authority, adapter, route, or lifecycle lease.
        """

        if type(observation) is not LiveVoiceObservation:
            return False
        return self._consume_product_observability_fact(
            session_id=session_id,
            correlation_id=correlation_id,
            fact=observation,
            diagnostic_identity=diagnostic_identity,
        )

    def consume_product_metric(
        self,
        *,
        session_id: object,
        correlation_id: object,
        metric: object,
        diagnostic_identity: object,
    ) -> bool:
        """Send one metric through the exact active product adapter FIFO."""

        if type(metric) is not LiveVoiceMetric:
            return False
        return self._consume_product_observability_fact(
            session_id=session_id,
            correlation_id=correlation_id,
            fact=metric,
            diagnostic_identity=diagnostic_identity,
        )

    def _consume_product_observability_fact(
        self,
        *,
        session_id: object,
        correlation_id: object,
        fact: LiveVoiceObservation | LiveVoiceMetric,
        diagnostic_identity: object,
    ) -> bool:
        runtime = self._observability_runtime
        binding = fact.binding
        interaction_id = binding.interaction_id
        if (
            runtime is None
            or self._stopped
            or type(session_id) is not str
            or not session_id
            or type(correlation_id) is not str
            or not correlation_id
            or binding.correlation_id != correlation_id
        ):
            return False
        from .product_observability_runtime import (
            ProductDiagnosticIdentity,
            ProductDiagnosticSeam,
        )

        if type(diagnostic_identity) is not ProductDiagnosticIdentity:
            return False
        owned_identity = diagnostic_identity
        if diagnostic_identity.seam is ProductDiagnosticSeam.COMMAND:
            resolution_id = fact.source_record_id
            if diagnostic_identity.command_id is None:
                if (
                    type(fact) is not LiveVoiceObservation
                    or fact.segment_name != "task.command"
                    or type(resolution_id) is not str
                    or len(resolution_id) != 64
                    or any(
                        character not in "0123456789abcdef"
                        for character in resolution_id
                    )
                    or diagnostic_identity.seam_id != resolution_id
                ):
                    return False
                # This registry owns the intent continuation which dispatches
                # ``intent-{resolution_id}``; AgentServer never derives it.
                owned_identity = replace(
                    diagnostic_identity,
                    command_id=f"intent-{resolution_id}",
                )
            elif (
                type(fact) is not LiveVoiceObservation
                or fact.event_name != "segment.completed"
                or fact.segment_name != "task.command"
                or fact.source_component != "product.composition.registry"
                or fact.route.implementation_class != "formal"
                or fact.route.owner_module != "product.composition.registry"
                or fact.binding.task_id is None
                or fact.binding.attempt_id is None
                or diagnostic_identity.seam_id != diagnostic_identity.command_id
                or type(resolution_id) is not str
                or not resolution_id
                or diagnostic_identity.outbox_id != resolution_id
            ):
                return False
        candidates = tuple(
            retained
            for (retained_session, _retained_interaction), retained in tuple(
                self._p2_routes.items()
            )
            if retained_session == session_id
            and retained.binding.correlation_id == correlation_id
            and retained.activation_lease.snapshot().state is P2LeaseState.OPEN
            and retained.observability_context is not None
            and retained.observability_adapter is not None
        )
        # A diagnostic producer is not an interaction router.  Select only the
        # unique OPEN authority route for this Session/correlation; ambiguity,
        # absence, closing and closed leases all fail before identity
        # registration, so no stale or foreign diagnostic can reach a backend.
        if len(candidates) != 1:
            return False
        retained = candidates[0]
        if (
            interaction_id is not None
            and interaction_id != retained.binding.interaction_id
        ):
            return False
        source_id = (
            fact.event_id if type(fact) is LiveVoiceObservation else fact.measurement_id
        )
        if (
            runtime.register_diagnostic_identity(
                source_id,
                owned_identity,
                correlation_id=correlation_id,
            )
            is not True
        ):
            return False
        disposition = (
            retained.observability_adapter.consume_observation(
                context=retained.observability_context,
                observation=fact,
            )
            if type(fact) is LiveVoiceObservation
            else retained.observability_adapter.consume_metric(
                context=retained.observability_context,
                metric=fact,
            )
        )
        return disposition.accepted_for_export

    @staticmethod
    def _diagnostic_route() -> dict[str, object]:
        return {
            "implementation_class": "formal",
            "owner_module": "product.composition.registry",
            "capability_provider": "jiuwenswarm-runtime",
            "contract_version": CONTRACT_VERSION,
            "reason_code": None,
        }

    def _current_observability_correlation(
        self,
        *,
        session_id: str,
        scope: ScopeRef,
    ) -> str | None:
        candidates = tuple(
            retained.binding.correlation_id
            for (candidate_session, _interaction), retained in tuple(
                self._p2_routes.items()
            )
            if candidate_session == session_id
            and retained.binding.scope == scope
            and retained.activation_lease.snapshot().state is P2LeaseState.OPEN
            and retained.observability_context is not None
            and retained.observability_adapter is not None
        )
        return candidates[0] if len(candidates) == 1 else None

    def _emit_authoritative_route_diagnostic(
        self,
        *,
        session_id: str,
        correlation_id: str,
        segment_name: str,
        seam_name: str,
        seam_id: str,
        task_id: str | None = None,
        attempt_id: str | None = None,
        response_ref: ResponseRef | None = None,
        source_record_id: str | None = None,
        command_id: str | None = None,
        event_id: str | None = None,
        outbox_id: str | None = None,
        executor_id: str | None = None,
        checkpoint_id: str | None = None,
        effect_id: str | None = None,
        presentation_id: str | None = None,
        event_name: str | None = None,
        source_seq: int | None = None,
        state: str | None = None,
        completed: bool = False,
        observed_at: str | None = None,
    ) -> bool:
        """Project one owner-validated identity set without business content."""

        if self._observability_runtime is None:
            return False
        try:
            from .product_observability_runtime import (
                ProductDiagnosticIdentity,
                ProductDiagnosticSeam,
            )

            binding: dict[str, object] = {"correlation_id": correlation_id}
            if task_id is not None:
                binding["task_id"] = task_id
            if attempt_id is not None:
                binding["attempt_id"] = attempt_id
            if response_ref is not None:
                binding.update(
                    {
                        "interaction_id": response_ref.interaction_id,
                        "response_id": response_ref.response_id,
                        "response_generation": response_ref.response_generation,
                    }
                )
            observation_id = hashlib.sha256(
                canonical_json_bytes(
                    {
                        "correlation_id": correlation_id,
                        "segment_name": segment_name,
                        "seam_name": seam_name,
                        "seam_id": seam_id,
                        "source_record_id": source_record_id,
                        "event_name": event_name,
                        "source_seq": source_seq,
                        "state": state,
                    }
                )
            ).hexdigest()
            payload: dict[str, object] = {
                "schema_version": OBSERVABILITY_SCHEMA_VERSION,
                "event_id": observation_id,
                "event_name": event_name
                or ("segment.completed" if completed else "route.selected"),
                "segment_name": segment_name,
                "observed_at": observed_at or utc_now(),
                "monotonic_ms": 0.0,
                "binding": binding,
                "route": self._diagnostic_route(),
                "source_component": "product.composition.registry",
            }
            if source_record_id is not None:
                payload["source_record_id"] = source_record_id
            if source_seq is not None:
                payload["source_seq"] = source_seq
            if state is not None:
                payload["state"] = state
            if completed:
                payload.update(
                    {"state": "terminal", "outcome": "completed", "duration_ms": 0.0}
                )
            observation = create_observation(payload)
            return self.consume_product_observation(
                session_id=session_id,
                correlation_id=correlation_id,
                observation=observation,
                diagnostic_identity=ProductDiagnosticIdentity(
                    seam=ProductDiagnosticSeam(seam_name),
                    seam_id=seam_id,
                    command_id=command_id,
                    event_id=event_id,
                    outbox_id=outbox_id,
                    executor_id=executor_id,
                    checkpoint_id=checkpoint_id,
                    effect_id=effect_id,
                    presentation_id=presentation_id,
                ),
            )
        except Exception:  # noqa: BLE001 -- diagnostics never rewrite business truth
            logger.warning(
                "[LiveVoiceProduct] authoritative diagnostic rejected; "
                "reason=FACT_REJECTED"
            )
            return False

    def _emit_authoritative_task_event(
        self,
        event: PersistentTaskEvent,
        *,
        session_id: str,
        correlation_id: str,
    ) -> bool:
        """Project one exact Store event with content-free causal identities."""

        if self._observability_runtime is None:
            return False

        try:
            from .product_observability_runtime import (
                ProductDiagnosticIdentity,
                ProductDiagnosticSeam,
            )

            command_id = (
                event.causation_id
                if event.event_type in {"task.accepted", "task.retry_accepted"}
                else None
            )
            candidates = tuple(
                retained
                for (candidate_session, _interaction), retained in tuple(
                    self._p2_routes.items()
                )
                if candidate_session == session_id
                and retained.binding.correlation_id == correlation_id
                and retained.binding.scope.subject_id == event.scope.subject_id
                and retained.binding.scope.project_id == event.scope.project_id
                and retained.activation_lease.snapshot().state is P2LeaseState.OPEN
            )
            if len(candidates) != 1:
                return False
            observation_payload = observation_from_task_event(
                event,
                observation_id=hashlib.sha256(
                    f"store-event\0{event.event_id}".encode("utf-8")
                ).hexdigest(),
                observed_at=event.occurred_at,
                monotonic_ms=0.0,
                route=self._diagnostic_route(),
            ).to_dict()
            observation_binding = observation_payload.get("binding")
            if not isinstance(observation_binding, dict):
                return False
            observation_binding["correlation_id"] = correlation_id
            observation = create_observation(observation_payload)
            return self.consume_product_observation(
                # A fresh authenticated Session may read an older Task event.
                # Attribution follows the unique current OPEN route while the
                # Store-owned Task scope still proves subject/project identity.
                session_id=session_id,
                correlation_id=correlation_id,
                observation=observation,
                diagnostic_identity=ProductDiagnosticIdentity(
                    seam=ProductDiagnosticSeam.EVENT,
                    seam_id=event.event_id,
                    command_id=command_id,
                    event_id=event.event_id,
                ),
            )
        except Exception:  # noqa: BLE001 -- diagnostics never rewrite business truth
            logger.warning(
                "[LiveVoiceProduct] authoritative task event diagnostic rejected; "
                "reason=FACT_REJECTED"
            )
            return False

    def _emit_authoritative_status_diagnostics(
        self,
        *,
        session_id: str,
        correlation_id: str,
        snapshot: TaskDurabilityDiagnosticSnapshot,
        event_id: str,
        observed_at: str,
    ) -> None:
        """Project verified current Store seams after an authorized status read."""

        common = {
            "session_id": session_id,
            "correlation_id": correlation_id,
            "task_id": snapshot.task_id,
            "attempt_id": snapshot.attempt_id,
            "executor_id": snapshot.executor_id,
            "observed_at": observed_at,
        }
        for item in snapshot.outbox:
            event_name = {
                OutboxKind.ATTEMPT_DISPATCH: "task.dispatch_outbox_observed",
                OutboxKind.ATTEMPT_CANCEL: "task.cancel_outbox_observed",
                OutboxKind.ATTEMPT_ADJUST: "task.adjust_outbox_observed",
            }.get(item.kind)
            self._emit_authoritative_route_diagnostic(
                **common,
                segment_name="task.queue",
                seam_name="outbox",
                seam_id=(f"{item.outbox_id}:{item.state.value}:{item.delivery_count}"),
                source_record_id=item.outbox_id,
                command_id=item.command_id,
                outbox_id=item.outbox_id,
                event_name=event_name,
                source_seq=(item.delivery_count if event_name is not None else None),
                state=(item.state.value if event_name is not None else None),
            )
        if snapshot.checkpoint_id is not None:
            self._emit_authoritative_route_diagnostic(
                **{
                    **common,
                    "attempt_id": snapshot.checkpoint_attempt_id,
                },
                segment_name="task.attempt",
                seam_name="checkpoint",
                seam_id=snapshot.checkpoint_id,
                source_record_id=snapshot.checkpoint_id,
                checkpoint_id=snapshot.checkpoint_id,
            )
        if snapshot.effect_id is not None:
            self._emit_authoritative_route_diagnostic(
                **{
                    **common,
                    "attempt_id": snapshot.effect_attempt_id,
                },
                segment_name="task.attempt",
                seam_name="effect",
                seam_id=snapshot.effect_id,
                source_record_id=snapshot.effect_id,
                effect_id=snapshot.effect_id,
            )
        if snapshot.recovery_id is not None:
            self._emit_authoritative_route_diagnostic(
                **common,
                segment_name="task.attempt",
                seam_name="recovery",
                seam_id=snapshot.recovery_id,
                source_record_id=snapshot.recovery_id,
            )
        if snapshot.reconciliation_state is not None:
            reconcile_id = (
                f"{snapshot.task_id}:{snapshot.attempt_id}:"
                f"{snapshot.reconciliation_state.value}:{event_id}"
            )
            self._emit_authoritative_route_diagnostic(
                **common,
                segment_name="task.attempt",
                seam_name="reconcile",
                seam_id=reconcile_id,
                source_record_id=reconcile_id,
                event_name="task.reconciliation_observed",
                source_seq=snapshot.event_head,
                state=snapshot.reconciliation_state.value,
            )

    def _emit_authoritative_progress_generation(
        self,
        *,
        event: TaskProgressTextEvent | TaskProgressNotificationIntent,
        generation_id: str,
        delivery: _ProgressDelivery,
    ) -> bool:
        if self._observability_runtime is None:
            return False
        try:
            from .product_observability_runtime import (
                ProductDiagnosticIdentity,
                ProductDiagnosticSeam,
            )

            key = self._progress_key_for_delivery(delivery)
            retained = None if key is None else self._progress_routes.get(key)
            if retained is None:
                return False
            binding = retained.binding
            task_event = event.task_event
            source_event = event.source_event
            if (
                task_event.task_id != binding.task_id
                or source_event.event_id != task_event.event_id
                or source_event.stream_ref.id != task_event.task_id
                or source_event.correlation_id != binding.correlation_id
                or source_event.scope != binding.scope
                or task_event.scope.subject_id != binding.scope.subject_id
                or task_event.scope.project_id != binding.scope.project_id
            ):
                return False

            observation_payload = observation_from_task_event(
                task_event,
                observation_id=hashlib.sha256(
                    f"progress-generation\0{generation_id}\0{delivery.delivery_id}".encode(
                        "utf-8"
                    )
                ).hexdigest(),
                observed_at=task_event.occurred_at,
                monotonic_ms=0.0,
                route=self._diagnostic_route(),
            ).to_dict()
            observation_binding = observation_payload.get("binding")
            if not isinstance(observation_binding, dict):
                return False
            observation_binding["correlation_id"] = binding.correlation_id
            presentation = delivery.presentation
            if presentation is not None:
                observation_binding.update(
                    {
                        "interaction_id": presentation.response_ref.interaction_id,
                        "response_id": presentation.response_ref.response_id,
                        "response_generation": (
                            presentation.response_ref.response_generation
                        ),
                    }
                )
            observation = create_observation(observation_payload)
            return self.consume_product_observation(
                session_id=binding.session_id,
                correlation_id=binding.correlation_id,
                observation=observation,
                diagnostic_identity=ProductDiagnosticIdentity(
                    seam=ProductDiagnosticSeam.GENERATION,
                    seam_id=generation_id,
                    event_id=task_event.event_id,
                    presentation_id=(
                        None if presentation is None else presentation.delivery_id
                    ),
                ),
            )
        except Exception:  # noqa: BLE001 -- diagnostics never rewrite business truth
            logger.warning(
                "[LiveVoiceProduct] authoritative generation diagnostic rejected; "
                "reason=FACT_REJECTED"
            )
            return False

    def _emit_authoritative_progress_ack(
        self,
        *,
        delivery: _ProgressDelivery,
        presentation: TaskPresentationDelivery | None,
        observed_at: str,
    ) -> bool:
        """Project an ACK only from a retained, consumed progress delivery."""

        key = self._progress_key_for_delivery(delivery)
        retained = None if key is None else self._progress_routes.get(key)
        if retained is None:
            return False
        binding = retained.binding
        response_ref = None if presentation is None else presentation.response_ref
        return self._emit_authoritative_route_diagnostic(
            session_id=binding.session_id,
            correlation_id=binding.correlation_id,
            segment_name=(
                "task.progress" if presentation is None else "runtime.presentation"
            ),
            seam_name="ack",
            seam_id=delivery.delivery_id,
            task_id=binding.task_id,
            attempt_id=delivery.attempt_id,
            response_ref=response_ref,
            source_record_id=delivery.delivery_id,
            command_id=(
                None if delivery.command is None else delivery.command.command_id
            ),
            event_id=delivery.source_event_id,
            presentation_id=(
                None if presentation is None else presentation.delivery_id
            ),
            completed=presentation is not None,
            observed_at=observed_at,
        )

