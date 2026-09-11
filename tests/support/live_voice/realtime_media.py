# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Bounded, conversation-neutral realtime media port."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Callable, cast

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    ConnectionEpochRef,
    ContractViolation,
)
from jiuwenswarm.gateway.live_voice.browser_gateway_media_transport import (
    MediaAuthorityBinding,
    MediaFrameFormat,
    MediaGenerationBinding,
    MediaPlayoutBinding,
    MediaTransportViolation as GatewayMediaTransportViolation,
)


class RealtimeMediaViolation(ValueError):
    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class MediaFrame:
    connection: ConnectionEpochRef
    track_id: str
    seq: int
    payload: bytes = field(repr=False)


@dataclass(frozen=True, slots=True)
class _RetainedMediaFrame:
    connection: ConnectionEpochRef
    track_id: str
    seq: int
    payload: bytes = field(repr=False)


@dataclass(frozen=True, slots=True)
class MediaAck:
    connection: ConnectionEpochRef
    track_id: str
    through_seq: int


@dataclass(frozen=True, slots=True)
class MediaPortCloseResult:
    was_active: bool
    dropped_frames: int
    dropped_payload_bytes: int
    business_cancel_count_delta: int = field(default=0, init=False)


@dataclass(frozen=True, slots=True)
class MediaPayloadLifecycleSnapshot:
    """Payload-free RM leaf facts for a future route persistence audit.

    This snapshot proves only bounded in-memory ownership in this leaf.  It
    deliberately cannot claim that a product route was registered or that a
    socket, consumer, logger, or another process did not persist the payload.
    """

    closed: bool
    accepted_frames: int
    accepted_payload_bytes: int
    delivered_frames: int
    delivered_payload_bytes: int
    acknowledged_frames: int
    acknowledged_payload_bytes: int
    dropped_frames: int
    dropped_payload_bytes: int
    pending_frames: int
    pending_payload_bytes: int
    evidence_scope: str = field(default="realtime_media_leaf_only", init=False)
    snapshot_contains_raw_payload: bool = field(default=False, init=False)
    registered_route_observed: bool = field(default=False, init=False)
    route_to_disk_zero_persistence_observed: bool = field(default=False, init=False)


@dataclass(frozen=True, slots=True)
class RealtimeMediaLeafAuditFact:
    """Payload-free lifecycle fact for an IO-owned registered-route audit.

    These facts deliberately remain leaf-only.  Observing them cannot prove
    that a product handler was registered or that another process, logger, or
    consumer avoided persistence.
    """

    event: str
    lease_id: str
    authority_evidence_id: str
    connection_id: str
    connection_epoch: int
    session_id: str
    media_session_id: str
    interaction_id: str
    track_id: str
    correlation_id: str
    direction: str
    generation_kind: str
    generation_id: str
    generation_value: int
    response_id: str | None
    response_generation: int | None
    unit_id: str | None
    closed: bool
    accepted_frames: int
    accepted_payload_bytes: int
    delivered_frames: int
    delivered_payload_bytes: int
    acknowledged_frames: int
    acknowledged_payload_bytes: int
    dropped_frames: int
    dropped_payload_bytes: int
    pending_frames: int
    pending_payload_bytes: int
    pending_audit_facts: int
    dropped_audit_facts: int
    audit_delivery_failures: int
    evidence_scope: str = field(
        default="realtime_media_registration_leaf_only", init=False
    )
    fact_contains_raw_payload: bool = field(default=False, init=False)
    registered_route_observed: bool = field(default=False, init=False)
    formal_route_ready: bool = field(default=False, init=False)
    route_to_disk_zero_persistence_observed: bool = field(default=False, init=False)
    business_cancel_count_delta: int = field(default=0, init=False)


@dataclass(frozen=True, slots=True)
class RealtimeMediaActivationRequest:
    """Already-authorized inputs for one bounded registration-owner leaf."""

    enabled: bool
    binding: MediaAuthorityBinding | None
    provider_available: bool
    transport_available: bool
    capacity: int = 32
    max_frame_payload_bytes: int = 15_360
    max_retained_payload_bytes: int | None = None
    audit_capacity: int = 32


@dataclass(frozen=True, slots=True)
class InactiveRealtimeMediaActivation:
    active: bool
    reason_id: str
    evidence_scope: str = field(
        default="realtime_media_registration_leaf_only", init=False
    )
    registered_route_observed: bool = field(default=False, init=False)
    formal_route_ready: bool = field(default=False, init=False)
    route_to_disk_zero_persistence_observed: bool = field(default=False, init=False)


@dataclass(frozen=True, slots=True)
class ActiveRealtimeMediaActivation:
    active: bool
    binding: MediaAuthorityBinding
    owner: "RealtimeMediaRegistrationOwner"
    evidence_scope: str = field(
        default="realtime_media_registration_leaf_only", init=False
    )
    registered_route_observed: bool = field(default=False, init=False)
    formal_route_ready: bool = field(default=False, init=False)
    route_to_disk_zero_persistence_observed: bool = field(default=False, init=False)


RealtimeMediaActivation = (
    InactiveRealtimeMediaActivation | ActiveRealtimeMediaActivation
)


class RealtimeMediaPort:
    # 20 ms of mono pcm_f32 at the media contract's 192 kHz ceiling.
    _DEFAULT_MAX_FRAME_PAYLOAD_BYTES = 15_360

    def __init__(
        self,
        connection: ConnectionEpochRef,
        *,
        capacity: int = 32,
        allowed_track_id: str | None = None,
        max_frame_payload_bytes: int = _DEFAULT_MAX_FRAME_PAYLOAD_BYTES,
        max_retained_payload_bytes: int | None = None,
    ) -> None:
        canonical_connection = self._canonicalize_connection_ref(
            connection,
            reason="INVALID_CONNECTION_EPOCH_REF",
            field_name="connection",
        )
        if type(capacity) is not int or capacity <= 0:
            raise RealtimeMediaViolation(
                "INVALID_CAPACITY", "capacity must be a positive integer"
            )
        if allowed_track_id is not None:
            self._validate_track_id(allowed_track_id)
        if type(max_frame_payload_bytes) is not int or max_frame_payload_bytes <= 0:
            raise RealtimeMediaViolation(
                "INVALID_PAYLOAD_BOUND",
                "max_frame_payload_bytes must be a positive integer",
            )
        if max_retained_payload_bytes is None:
            max_retained_payload_bytes = capacity * max_frame_payload_bytes
        if (
            type(max_retained_payload_bytes) is not int
            or max_retained_payload_bytes <= 0
        ):
            raise RealtimeMediaViolation(
                "INVALID_PAYLOAD_BOUND",
                "max_retained_payload_bytes must be a positive integer",
            )
        self._connection = canonical_connection
        self._capacity = capacity
        self._allowed_track_id = allowed_track_id
        self._max_frame_payload_bytes = max_frame_payload_bytes
        self._max_retained_payload_bytes = max_retained_payload_bytes
        self._lock = threading.RLock()
        self._queues: dict[str, list[_RetainedMediaFrame]] = {}
        self._last_seq: dict[str, int] = {}
        self._delivered: dict[str, int] = {}
        self._acked: dict[str, int] = {}
        self._closed = False
        self._accepted_frames = 0
        self._accepted_payload_bytes = 0
        self._delivered_frames = 0
        self._delivered_payload_bytes = 0
        self._acknowledged_frames = 0
        self._acknowledged_payload_bytes = 0
        self._dropped_frames = 0
        self._dropped_payload_bytes = 0
        self._retained_frames = 0
        self._retained_payload_bytes = 0

    def enqueue(self, frame: MediaFrame) -> None:
        with self._lock:
            self._require_open()
            retained_frame = self._validate_frame(frame)
            self._require_allowed_track(retained_frame.track_id, bind_if_unset=False)
            if self._retained_frames >= self._capacity:
                raise RealtimeMediaViolation(
                    "MEDIA_QUEUE_OVERFLOW", "bounded media queue is full"
                )
            payload_bytes = len(retained_frame.payload)
            if (
                self._retained_payload_bytes + payload_bytes
                > self._max_retained_payload_bytes
            ):
                raise RealtimeMediaViolation(
                    "MEDIA_PAYLOAD_CAPACITY_EXCEEDED",
                    "aggregate retained media payload capacity would be exceeded",
                )
            expected = self._last_seq.get(retained_frame.track_id, -1) + 1
            if retained_frame.seq != expected:
                raise RealtimeMediaViolation(
                    "NON_CONTIGUOUS_MEDIA_SEQUENCE",
                    f"expected media sequence {expected}",
                )
            self._require_allowed_track(retained_frame.track_id, bind_if_unset=True)
            self._queues.setdefault(retained_frame.track_id, []).append(retained_frame)
            self._last_seq[retained_frame.track_id] = retained_frame.seq
            self._accepted_frames += 1
            self._accepted_payload_bytes += payload_bytes
            self._retained_frames += 1
            self._retained_payload_bytes += payload_bytes

    def read(
        self, track_id: str, *, limit: int | None = None
    ) -> tuple[MediaFrame, ...]:
        with self._lock:
            self._require_open()
            self._validate_track_id(track_id)
            self._require_allowed_track(track_id, bind_if_unset=False)
            queue = self._queues.get(track_id, [])
            if limit is None:
                limit = len(queue)
            if type(limit) is not int or limit < 0:
                raise RealtimeMediaViolation(
                    "INVALID_LIMIT", "limit must be a non-negative integer"
                )
            selected_records = tuple(queue[:limit])
            if selected_records:
                prior = self._delivered.get(track_id, -1)
                newly_delivered = tuple(
                    frame for frame in selected_records if frame.seq > prior
                )
                self._delivered[track_id] = max(prior, selected_records[-1].seq)
                self._delivered_frames += len(newly_delivered)
                self._delivered_payload_bytes += sum(
                    len(frame.payload) for frame in newly_delivered
                )
            return tuple(self._snapshot_frame(frame) for frame in selected_records)

    def acknowledge(self, ack: MediaAck) -> int:
        with self._lock:
            self._require_open()
            if type(ack) is not MediaAck:
                raise RealtimeMediaViolation(
                    "INVALID_MEDIA_ACK", "acknowledgement must be typed"
                )
            canonical_ack_connection = self._canonicalize_connection_ref(
                ack.connection,
                reason="INVALID_MEDIA_ACK",
                field_name="ack.connection",
            )
            if not self._same_connection(canonical_ack_connection, self._connection):
                raise RealtimeMediaViolation(
                    "CONNECTION_EPOCH_MISMATCH",
                    "media acknowledgement belongs to another connection epoch",
                )
            self._validate_track_id(ack.track_id)
            self._require_allowed_track(ack.track_id, bind_if_unset=False)
            if type(ack.through_seq) is not int or ack.through_seq < 0:
                raise RealtimeMediaViolation(
                    "INVALID_MEDIA_ACK",
                    "acknowledgement sequence must be a non-negative integer",
                )
            queue = self._queues.get(ack.track_id, [])
            delivered = self._delivered.get(ack.track_id, -1)
            prior = self._acked.get(ack.track_id, -1)
            if ack.through_seq < prior or ack.through_seq > delivered:
                raise RealtimeMediaViolation(
                    "INVALID_MEDIA_ACK", "acknowledgement is stale or beyond delivery"
                )
            acknowledged = [frame for frame in queue if frame.seq <= ack.through_seq]
            acknowledged_payload_bytes = sum(
                len(frame.payload) for frame in acknowledged
            )
            self._queues[ack.track_id] = [
                frame for frame in queue if frame.seq > ack.through_seq
            ]
            self._acked[ack.track_id] = ack.through_seq
            self._acknowledged_frames += len(acknowledged)
            self._acknowledged_payload_bytes += acknowledged_payload_bytes
            self._retained_frames -= len(acknowledged)
            self._retained_payload_bytes -= acknowledged_payload_bytes
            return len(acknowledged)

    def pending(self, track_id: str) -> int:
        with self._lock:
            self._validate_track_id(track_id)
            self._require_allowed_track(track_id, bind_if_unset=False)
            return len(self._queues.get(track_id, []))

    def close(self) -> MediaPortCloseResult:
        """Fence the leaf and release every retained payload reference.

        Repeated close is a zero-effect cleanup retry.  Closing this transport
        leaf never widens into a response, round, or task cancellation.
        """

        with self._lock:
            if self._closed:
                return MediaPortCloseResult(
                    was_active=False,
                    dropped_frames=0,
                    dropped_payload_bytes=0,
                )
            self._closed = True
            dropped_frames = sum(len(queue) for queue in self._queues.values())
            dropped_payload_bytes = sum(
                len(frame.payload) for queue in self._queues.values() for frame in queue
            )
            self._dropped_frames += dropped_frames
            self._dropped_payload_bytes += dropped_payload_bytes
            self._retained_frames = 0
            self._retained_payload_bytes = 0
            self._queues.clear()
            self._last_seq.clear()
            self._delivered.clear()
            self._acked.clear()
            return MediaPortCloseResult(
                was_active=True,
                dropped_frames=dropped_frames,
                dropped_payload_bytes=dropped_payload_bytes,
            )

    def payload_lifecycle_snapshot(self) -> MediaPayloadLifecycleSnapshot:
        """Return content-free leaf counters without upgrading product truth."""

        with self._lock:
            return MediaPayloadLifecycleSnapshot(
                closed=self._closed,
                accepted_frames=self._accepted_frames,
                accepted_payload_bytes=self._accepted_payload_bytes,
                delivered_frames=self._delivered_frames,
                delivered_payload_bytes=self._delivered_payload_bytes,
                acknowledged_frames=self._acknowledged_frames,
                acknowledged_payload_bytes=self._acknowledged_payload_bytes,
                dropped_frames=self._dropped_frames,
                dropped_payload_bytes=self._dropped_payload_bytes,
                pending_frames=self._retained_frames,
                pending_payload_bytes=self._retained_payload_bytes,
            )

    def _require_open(self) -> None:
        if self._closed:
            raise RealtimeMediaViolation(
                "MEDIA_PORT_CLOSED", "realtime media port is closed"
            )

    @staticmethod
    def _validate_track_id(track_id: object) -> None:
        if type(track_id) is not str or not track_id.strip():
            raise RealtimeMediaViolation(
                "INVALID_TRACK_ID", "track_id must be non-empty"
            )

    def _require_allowed_track(self, track_id: str, *, bind_if_unset: bool) -> None:
        if self._allowed_track_id is None:
            if bind_if_unset:
                self._allowed_track_id = track_id
            return
        if track_id != self._allowed_track_id:
            raise RealtimeMediaViolation(
                "MEDIA_TRACK_MISMATCH",
                "track_id does not match the port's admitted track",
            )

    @staticmethod
    def _canonicalize_connection_ref(
        connection: object, *, reason: str, field_name: str
    ) -> ConnectionEpochRef:
        if type(connection) is not ConnectionEpochRef:
            raise RealtimeMediaViolation(
                reason, f"{field_name} must be an exact ConnectionEpochRef"
            )
        typed_connection = cast(ConnectionEpochRef, connection)
        try:
            return ConnectionEpochRef.from_dict(  # type: ignore[attr-defined,no-any-return]
                typed_connection.to_dict()
            )
        except ContractViolation as exc:
            raise RealtimeMediaViolation(
                reason, f"{field_name} is not canonical ({exc.reason})"
            ) from exc

    @staticmethod
    def _same_connection(left: ConnectionEpochRef, right: ConnectionEpochRef) -> bool:
        return (
            left.connection_id == right.connection_id
            and left.connection_epoch == right.connection_epoch
        )

    @staticmethod
    def _snapshot_frame(frame: _RetainedMediaFrame) -> MediaFrame:
        return MediaFrame(
            connection=ConnectionEpochRef(
                connection_id=frame.connection.connection_id,
                connection_epoch=frame.connection.connection_epoch,
            ),
            track_id=frame.track_id,
            seq=frame.seq,
            payload=memoryview(frame.payload).tobytes(),
        )

    def _validate_frame(self, frame: MediaFrame) -> _RetainedMediaFrame:
        if type(frame) is not MediaFrame:
            raise RealtimeMediaViolation(
                "INVALID_MEDIA_FRAME", "media frame must be typed"
            )
        submitted_connection = frame.connection
        submitted_track_id = frame.track_id
        submitted_seq = frame.seq
        submitted_payload = frame.payload
        canonical_frame_connection = self._canonicalize_connection_ref(
            submitted_connection,
            reason="INVALID_MEDIA_FRAME",
            field_name="frame.connection",
        )
        if not self._same_connection(canonical_frame_connection, self._connection):
            raise RealtimeMediaViolation(
                "CONNECTION_EPOCH_MISMATCH",
                "media frame belongs to another connection epoch",
            )
        self._validate_track_id(submitted_track_id)
        if type(submitted_seq) is not int or submitted_seq < 0:
            raise RealtimeMediaViolation(
                "INVALID_MEDIA_SEQUENCE", "media sequence must be non-negative"
            )
        if type(submitted_payload) is not bytes or not submitted_payload:
            raise RealtimeMediaViolation(
                "INVALID_MEDIA_PAYLOAD", "media payload must be non-empty bytes"
            )
        if len(submitted_payload) > self._max_frame_payload_bytes:
            raise RealtimeMediaViolation(
                "MEDIA_FRAME_PAYLOAD_TOO_LARGE",
                "media frame payload exceeds the per-frame byte bound",
            )
        return _RetainedMediaFrame(
            connection=canonical_frame_connection,
            track_id=submitted_track_id,
            seq=submitted_seq,
            payload=memoryview(submitted_payload).tobytes(),
        )


_REGISTRATION_OWNER_CONSTRUCTION_TOKEN = object()
_MAX_AUDIT_CAPACITY = 256


def _copy_media_authority_binding(
    binding: MediaAuthorityBinding,
) -> MediaAuthorityBinding:
    """Retain an independently validated copy of the existing Media contract."""

    if type(binding) is not MediaAuthorityBinding:
        raise RealtimeMediaViolation(
            "MEDIA_AUTHORITY_UNAVAILABLE",
            "an exact server-authored MediaAuthorityBinding is required",
        )
    try:
        generation = MediaGenerationBinding(
            kind=binding.generation.kind,
            id=binding.generation.id,
            value=binding.generation.value,
        )
        frame_format = MediaFrameFormat(
            sample_rate_hz=binding.frame_format.sample_rate_hz,
            samples_per_channel=binding.frame_format.samples_per_channel,
            encoding=binding.frame_format.encoding,
            byte_order=binding.frame_format.byte_order,
            channel_count=binding.frame_format.channel_count,
            frame_duration_ms=binding.frame_format.frame_duration_ms,
        )
        playout = (
            None
            if binding.playout is None
            else MediaPlayoutBinding(
                response_id=binding.playout.response_id,
                response_generation=binding.playout.response_generation,
                unit_id=binding.playout.unit_id,
            )
        )
        return MediaAuthorityBinding(
            lease_id=binding.lease_id,
            authority_evidence_id=binding.authority_evidence_id,
            connection_id=binding.connection_id,
            connection_epoch=binding.connection_epoch,
            session_id=binding.session_id,
            media_session_id=binding.media_session_id,
            interaction_id=binding.interaction_id,
            track_id=binding.track_id,
            correlation_id=binding.correlation_id,
            direction=binding.direction,
            generation=generation,
            frame_format=frame_format,
            playout=playout,
        )
    except (AttributeError, GatewayMediaTransportViolation) as exc:
        raise RealtimeMediaViolation(
            "MEDIA_INVALID_AUTHORITY_BINDING",
            "the Media authority binding is not canonical",
        ) from exc


class RealtimeMediaRegistrationOwner:
    """Retain one exact Media leaf and its idempotent cleanup result.

    This owner is intentionally synchronous.  A caller timeout or cancellation
    cannot consume or interrupt cleanup once ``close`` begins, and every later
    call observes the same retained result.
    """

    def __init__(
        self,
        binding: MediaAuthorityBinding,
        *,
        capacity: int,
        max_frame_payload_bytes: int,
        max_retained_payload_bytes: int | None,
        audit_capacity: int,
        on_audit_fact: Callable[[RealtimeMediaLeafAuditFact], None] | None,
        construction_token: object,
    ) -> None:
        if construction_token is not _REGISTRATION_OWNER_CONSTRUCTION_TOKEN:
            raise RealtimeMediaViolation(
                "MEDIA_ACTIVATION_FACTORY_REQUIRED",
                "registration owners must be created by the activation factory",
            )
        self._binding = binding
        self._port = RealtimeMediaPort(
            ConnectionEpochRef(
                connection_id=binding.connection_id,
                connection_epoch=binding.connection_epoch,
            ),
            capacity=capacity,
            allowed_track_id=binding.track_id,
            max_frame_payload_bytes=max_frame_payload_bytes,
            max_retained_payload_bytes=max_retained_payload_bytes,
        )
        if (
            type(audit_capacity) is not int
            or audit_capacity <= 0
            or audit_capacity > _MAX_AUDIT_CAPACITY
        ):
            raise RealtimeMediaViolation(
                "MEDIA_INVALID_AUDIT_CAPACITY",
                f"audit capacity must be an integer in [1, {_MAX_AUDIT_CAPACITY}]",
            )
        self._audit_capacity = audit_capacity
        self._audit_facts: list[RealtimeMediaLeafAuditFact] = []
        self._on_audit_fact = on_audit_fact
        self._lock = threading.RLock()
        self._close_result: MediaPortCloseResult | None = None
        self._dropped_audit_facts = 0
        self._audit_delivery_failures = 0
        self._record_audit_fact_locked("activation.ready")

    @property
    def binding(self) -> MediaAuthorityBinding:
        return self._binding

    @property
    def closed(self) -> bool:
        with self._lock:
            return self._close_result is not None

    @property
    def audit_delivery_failures(self) -> int:
        with self._lock:
            return self._audit_delivery_failures

    @property
    def pending_audit_facts(self) -> int:
        with self._lock:
            return len(self._audit_facts)

    @property
    def dropped_audit_facts(self) -> int:
        with self._lock:
            return self._dropped_audit_facts

    def enqueue(self, frame: MediaFrame) -> None:
        with self._lock:
            self._port.enqueue(frame)
            self._record_audit_fact_locked("frame.accepted")

    def read(
        self, track_id: str, *, limit: int | None = None
    ) -> tuple[MediaFrame, ...]:
        with self._lock:
            result = self._port.read(track_id, limit=limit)
            self._record_audit_fact_locked("frame.delivered")
        return result

    def acknowledge(self, ack: MediaAck) -> int:
        with self._lock:
            acknowledged = self._port.acknowledge(ack)
            self._record_audit_fact_locked("frame.acknowledged")
        return acknowledged

    def pending(self) -> int:
        with self._lock:
            return self._port.pending(self._binding.track_id)

    def payload_lifecycle_snapshot(self) -> MediaPayloadLifecycleSnapshot:
        with self._lock:
            return self._port.payload_lifecycle_snapshot()

    def audit_snapshot(self) -> RealtimeMediaLeafAuditFact:
        with self._lock:
            return self._audit_fact_locked("lifecycle.snapshot")

    def close(self) -> MediaPortCloseResult:
        with self._lock:
            if self._close_result is not None:
                return self._close_result
            self._close_result = self._port.close()
            self._record_audit_fact_locked("activation.closed")
            retained = self._close_result
        return retained

    def drain_audit_facts(self, *, limit: int) -> int:
        """Explicitly deliver at most ``limit`` retained observer facts.

        Media operations only append to the fixed-capacity lane.  A slow or
        failing consumer can therefore delay this explicit observer drain but
        cannot hold the owner lock or freeze enqueue, read, ACK, or cleanup.
        """

        if type(limit) is not int or limit <= 0:
            raise RealtimeMediaViolation(
                "MEDIA_INVALID_AUDIT_DRAIN_LIMIT",
                "audit drain limit must be a positive integer",
            )
        callback = self._on_audit_fact
        if callback is None:
            return 0
        attempted = 0
        while attempted < limit:
            with self._lock:
                if not self._audit_facts:
                    return attempted
                fact = self._audit_facts.pop(0)
            try:
                callback(fact)
            except Exception:
                with self._lock:
                    self._audit_delivery_failures += 1
            attempted += 1
        return attempted

    def _record_audit_fact_locked(self, event: str) -> None:
        if len(self._audit_facts) >= self._audit_capacity:
            self._dropped_audit_facts += 1
            return
        self._audit_facts.append(
            self._audit_fact_locked(
                event,
                pending_audit_facts=len(self._audit_facts) + 1,
            )
        )

    def _audit_fact_locked(
        self,
        event: str,
        *,
        pending_audit_facts: int | None = None,
    ) -> RealtimeMediaLeafAuditFact:
        snapshot = self._port.payload_lifecycle_snapshot()
        playout = self._binding.playout
        return RealtimeMediaLeafAuditFact(
            event=event,
            lease_id=self._binding.lease_id,
            authority_evidence_id=self._binding.authority_evidence_id,
            connection_id=self._binding.connection_id,
            connection_epoch=self._binding.connection_epoch,
            session_id=self._binding.session_id,
            media_session_id=self._binding.media_session_id,
            interaction_id=self._binding.interaction_id,
            track_id=self._binding.track_id,
            correlation_id=self._binding.correlation_id,
            direction=self._binding.direction.value,
            generation_kind=self._binding.generation.kind.value,
            generation_id=self._binding.generation.id,
            generation_value=self._binding.generation.value,
            response_id=None if playout is None else playout.response_id,
            response_generation=(
                None if playout is None else playout.response_generation
            ),
            unit_id=None if playout is None else playout.unit_id,
            closed=snapshot.closed,
            accepted_frames=snapshot.accepted_frames,
            accepted_payload_bytes=snapshot.accepted_payload_bytes,
            delivered_frames=snapshot.delivered_frames,
            delivered_payload_bytes=snapshot.delivered_payload_bytes,
            acknowledged_frames=snapshot.acknowledged_frames,
            acknowledged_payload_bytes=snapshot.acknowledged_payload_bytes,
            dropped_frames=snapshot.dropped_frames,
            dropped_payload_bytes=snapshot.dropped_payload_bytes,
            pending_frames=snapshot.pending_frames,
            pending_payload_bytes=snapshot.pending_payload_bytes,
            pending_audit_facts=(
                len(self._audit_facts)
                if pending_audit_facts is None
                else pending_audit_facts
            ),
            dropped_audit_facts=self._dropped_audit_facts,
            audit_delivery_failures=self._audit_delivery_failures,
        )


def create_realtime_media_activation(
    request: RealtimeMediaActivationRequest,
    *,
    on_audit_fact: Callable[[RealtimeMediaLeafAuditFact], None] | None = None,
) -> RealtimeMediaActivation:
    """Create a non-formal Media registration leaf after exact local gates.

    Feature-off returns before inspecting the binding, availability facts, or
    callback and creates no queue, lock, retained owner, or external effect.
    """

    if type(request) is not RealtimeMediaActivationRequest:
        raise RealtimeMediaViolation(
            "MEDIA_INVALID_ACTIVATION_REQUEST",
            "activation request must be exact and typed",
        )
    if request.enabled is not True:
        return InactiveRealtimeMediaActivation(
            active=False, reason_id="MEDIA_FEATURE_DISABLED"
        )
    if type(request.binding) is not MediaAuthorityBinding:
        return InactiveRealtimeMediaActivation(
            active=False, reason_id="MEDIA_AUTHORITY_UNAVAILABLE"
        )
    if request.provider_available is not True:
        return InactiveRealtimeMediaActivation(
            active=False, reason_id="MEDIA_PROVIDER_UNAVAILABLE"
        )
    if request.transport_available is not True:
        return InactiveRealtimeMediaActivation(
            active=False, reason_id="MEDIA_TRANSPORT_UNAVAILABLE"
        )
    if on_audit_fact is not None and not callable(on_audit_fact):
        raise RealtimeMediaViolation(
            "MEDIA_INVALID_AUDIT_CALLBACK",
            "audit callback must be callable",
        )
    binding = _copy_media_authority_binding(request.binding)
    owner = RealtimeMediaRegistrationOwner(
        binding,
        capacity=request.capacity,
        max_frame_payload_bytes=request.max_frame_payload_bytes,
        max_retained_payload_bytes=request.max_retained_payload_bytes,
        audit_capacity=request.audit_capacity,
        on_audit_fact=on_audit_fact,
        construction_token=_REGISTRATION_OWNER_CONSTRUCTION_TOKEN,
    )
    return ActiveRealtimeMediaActivation(
        active=True,
        binding=binding,
        owner=owner,
    )
