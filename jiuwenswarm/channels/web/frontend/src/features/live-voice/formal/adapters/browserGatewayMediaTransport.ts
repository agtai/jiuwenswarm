/** Provider-neutral Browser <-> Gateway media framing and bounded transport seams. */

export const MEDIA_CONTRACT_VERSION = 'live-voice.media.v1' as const;
export const MEDIA_TRANSPORT_KIND = 'websocket_binary' as const;
export const MEDIA_WIRE_CODEC = 'pcm_f32le' as const;
export const MEDIA_CAPTURE_ENCODING = 'pcm_f32' as const;
export const MEDIA_FRAME_DURATION_MS = 20 as const;
export const MEDIA_END_OF_TURN_CAPABILITY = 'media.end_of_turn.v1' as const;

const WIRE_MAGIC = [0x4c, 0x56, 0x4d, 0x31] as const;
const WIRE_VERSION = 1;
const WIRE_AUDIO_KIND = 1;
const WIRE_HEADER_BYTES = 36;
const MAX_SAFE_UINT = Number.MAX_SAFE_INTEGER;
const MIN_SAMPLE_RATE_HZ = 8_000;
const MAX_SAMPLE_RATE_HZ = 192_000;
const MAX_LEASE_ID_BYTES = 128;
const MAX_ID_CHARS = 256;
const MAX_CONTROL_BYTES = 16_384;
const MAX_PCM_F32_ABS = 3.4028234663852886e38;
const MAX_PCM_PAYLOAD_BYTES = (MAX_SAMPLE_RATE_HZ / 50) * 4;
const MAX_BINARY_FRAME_BYTES = WIRE_HEADER_BYTES + MAX_LEASE_ID_BYTES + MAX_PCM_PAYLOAD_BYTES;
const MAX_LIFECYCLE_FACT_CAPACITY = 256;
const REGISTRATION_OWNER_CONSTRUCTION_TOKEN = Symbol('browser-gateway-media-registration-owner');

export type MediaDirection = 'uplink' | 'downlink';
export type MediaGenerationKind = 'capture' | 'response';
export type BinarySendDisposition = 'sent' | 'backpressured' | 'closed';
export type MediaPlaybackStopOutcome =
  | 'local_fence_established'
  | 'local_fence_established_source_unknown'
  | 'target_mismatch'
  | 'no_active_target'
  | 'already_stopped'
  | 'local_fence_failed'
  | 'feature_disabled'
  | 'adapter_closed';
export type MediaDetachReason =
  | 'MEDIA_ACK_GAP'
  | 'MEDIA_ACK_OUT_OF_ORDER'
  | 'MEDIA_ACK_UNSENT'
  | 'MEDIA_BINDING_MISMATCH'
  | 'MEDIA_CANCEL_SCOPE_VIOLATION'
  | 'MEDIA_CONSUMER_FAILED'
  | 'MEDIA_CURSOR_MISMATCH'
  | 'MEDIA_DUPLICATE_ATTACH'
  | 'MEDIA_DUPLICATE_OR_OUT_OF_ORDER'
  | 'MEDIA_INVALID_FRAME'
  | 'MEDIA_LEASE_CLOSED'
  | 'MEDIA_LOCAL_CLOSE'
  | 'MEDIA_MALFORMED_FRAME'
  | 'MEDIA_NONFINITE_AUDIO'
  | 'MEDIA_NOT_ATTACHED'
  | 'MEDIA_OVERSIZED_FRAME'
  | 'MEDIA_PEER_CLOSE'
  | 'MEDIA_RECOGNITION_CONTINUATION'
  | 'MEDIA_SEQUENCE_GAP'
  | 'MEDIA_SEQUENCE_VIOLATION'
  | 'MEDIA_STALE_GENERATION'
  | 'MEDIA_STREAMING_TTS_TEXT_OR_RETRY'
  | 'MEDIA_TRANSPORT_CLOSED'
  | 'MEDIA_TRANSPORT_PROTOCOL_ERROR'
  | 'MEDIA_TRANSPORT_SEND_FAILED';

const MEDIA_PLAYBACK_STOP_OUTCOMES: readonly MediaPlaybackStopOutcome[] = Object.freeze([
  'local_fence_established',
  'local_fence_established_source_unknown',
  'target_mismatch',
  'no_active_target',
  'already_stopped',
  'local_fence_failed',
  'feature_disabled',
  'adapter_closed',
]);
const MEDIA_DETACH_REASONS: readonly MediaDetachReason[] = Object.freeze([
  'MEDIA_ACK_GAP',
  'MEDIA_ACK_OUT_OF_ORDER',
  'MEDIA_ACK_UNSENT',
  'MEDIA_BINDING_MISMATCH',
  'MEDIA_CANCEL_SCOPE_VIOLATION',
  'MEDIA_CONSUMER_FAILED',
  'MEDIA_CURSOR_MISMATCH',
  'MEDIA_DUPLICATE_ATTACH',
  'MEDIA_DUPLICATE_OR_OUT_OF_ORDER',
  'MEDIA_INVALID_FRAME',
  'MEDIA_LEASE_CLOSED',
  'MEDIA_LOCAL_CLOSE',
  'MEDIA_MALFORMED_FRAME',
  'MEDIA_NONFINITE_AUDIO',
  'MEDIA_NOT_ATTACHED',
  'MEDIA_OVERSIZED_FRAME',
  'MEDIA_PEER_CLOSE',
  'MEDIA_RECOGNITION_CONTINUATION',
  'MEDIA_SEQUENCE_GAP',
  'MEDIA_SEQUENCE_VIOLATION',
  'MEDIA_STALE_GENERATION',
  'MEDIA_STREAMING_TTS_TEXT_OR_RETRY',
  'MEDIA_TRANSPORT_CLOSED',
  'MEDIA_TRANSPORT_PROTOCOL_ERROR',
  'MEDIA_TRANSPORT_SEND_FAILED',
]);

export class MediaTransportViolation extends Error {
  readonly reasonId: string;

  constructor(reasonId: string, message: string) {
    super(message);
    this.name = 'MediaTransportViolation';
    this.reasonId = reasonId;
  }
}

export interface MediaGenerationBinding {
  readonly kind: MediaGenerationKind;
  readonly id: string;
  readonly value: number;
}

export interface MediaPlayoutBinding {
  readonly response_id: string;
  readonly response_generation: number;
  readonly unit_id: string;
}

export interface MediaFrameFormat {
  readonly sample_rate_hz: number;
  readonly samples_per_channel: number;
  readonly encoding: typeof MEDIA_CAPTURE_ENCODING;
  readonly byte_order: 'little';
  readonly channel_count: 1;
  readonly frame_duration_ms: typeof MEDIA_FRAME_DURATION_MS;
}

export interface MediaAuthorityBinding {
  readonly lease_id: string;
  readonly authority_evidence_id: string;
  readonly connection_id: string;
  readonly connection_epoch: number;
  readonly session_id: string;
  readonly media_session_id: string;
  readonly interaction_id: string;
  readonly track_id: string;
  readonly correlation_id: string;
  readonly direction: MediaDirection;
  readonly generation: MediaGenerationBinding;
  readonly frame_format: MediaFrameFormat;
  readonly playout: MediaPlayoutBinding | null;
}

export interface MediaAttach {
  readonly type: 'media.attach';
  readonly binding: MediaAuthorityBinding;
}

export interface MediaAck {
  readonly type: 'media.ack';
  readonly lease_id: string;
  readonly generation: number;
  readonly through_seq: number;
}

export interface MediaDetach {
  readonly type: 'media.detach';
  readonly lease_id: string;
  readonly generation: number;
  readonly reason_id: MediaDetachReason;
  readonly through_seq: number | null;
  readonly business_cancel_count_delta: 0;
}

export interface MediaSpeechStart {
  readonly type: 'media.speech_start';
  readonly capability_version: typeof MEDIA_END_OF_TURN_CAPABILITY;
  readonly lease_id: string;
  readonly generation: number;
  readonly detector: 'server_vad';
  readonly provider_start_ms: number;
  readonly timing_basis: 'provider_time';
  readonly timing_provenance: 'adapter_derived';
  readonly create_response: false;
  readonly interrupt_response: false;
  readonly business_cancel_count_delta: 0;
}

export interface MediaEndOfTurn {
  readonly type: 'media.end_of_turn';
  readonly capability_version: typeof MEDIA_END_OF_TURN_CAPABILITY;
  readonly lease_id: string;
  readonly generation: number;
  readonly detector: 'server_vad';
  readonly speech_started_observed: true;
  readonly provider_start_ms: number;
  readonly provider_end_ms: number;
  readonly timing_basis: 'provider_time';
  readonly timing_provenance: 'adapter_derived';
  readonly create_response: false;
  readonly interrupt_response: false;
  readonly business_cancel_count_delta: 0;
}

export interface MediaPlaybackStopReceipt {
  readonly type: 'media.playback_stop_receipt';
  readonly lease_id: string;
  readonly response_id: string;
  readonly response_generation: number;
  readonly unit_id: string;
  readonly outcome: MediaPlaybackStopOutcome;
  readonly confirmed_through_seq: number | null;
  readonly business_cancel_count_delta: 0;
}

export type MediaControl = MediaAttach | MediaAck | MediaDetach | MediaSpeechStart | MediaEndOfTurn | MediaPlaybackStopReceipt;

export interface MediaAudioFrame {
  readonly seq: number;
  readonly sample_cursor: number;
  readonly samples: Float32Array;
}

export interface MediaCapability {
  readonly contract_version: typeof MEDIA_CONTRACT_VERSION;
  readonly transport_kind: typeof MEDIA_TRANSPORT_KIND;
  readonly wire_codec: typeof MEDIA_WIRE_CODEC;
  readonly capture_encoding: typeof MEDIA_CAPTURE_ENCODING;
  readonly frame_duration_ms: typeof MEDIA_FRAME_DURATION_MS;
  readonly channel_count: 1;
  readonly provider_neutral: true;
  readonly evidence_scope: 'contract_only';
  readonly contract_vector_evidence_id: 'live-voice.media.v1.roundtrip-vector';
  readonly formal_route_ready: false;
  readonly real_transport_observed: false;
  readonly registration_evidence_id: null;
  readonly runtime_evidence_id: null;
}

export interface MediaActivationRequest {
  readonly enabled: boolean;
  readonly binding: MediaAuthorityBinding | null;
  readonly provider_available: boolean;
  readonly transport_available: boolean;
  readonly on_audio_frame: (frame: MediaAudioFrame) => void;
  readonly on_lifecycle_fact?: (fact: MediaLeafLifecycleFact) => void;
  readonly max_pending_frames?: number;
  readonly max_pending_bytes?: number;
  readonly lifecycle_fact_capacity?: number;
}

const CONSUMER_FAILURE_REASON_PREFIXES = Object.freeze([
  'ADAPTER_',
  'AUDIO_',
  'CAPTURE_',
  'DOCUMENT_',
  'FEATURE_',
  'INSECURE_',
  'INVALID_AUDIO_',
  'INVALID_PLAYOUT_',
  'PAGE_',
  'PLAYOUT_',
] as const);

export type MediaConsumerFailureFallback =
  | 'MEDIA_CONSUMER_FAILED'
  | 'ADAPTER_AUDIO_FRAME_CALLBACK_FAILED'
  | 'ADAPTER_SPEECH_START_CALLBACK_FAILED'
  | 'ADAPTER_END_OF_TURN_CALLBACK_FAILED';

export function boundedMediaConsumerFailureReason(
  error: unknown,
  fallback: MediaConsumerFailureFallback = 'MEDIA_CONSUMER_FAILED'
): string {
  let reason: unknown;
  try {
    reason = typeof error === 'object' && error !== null && 'reason' in error
      ? (error as { readonly reason?: unknown }).reason
      : null;
  } catch {
    return fallback;
  }
  if (
    typeof reason !== 'string'
    || reason.length === 0
    || reason.length > 96
    || !/^[A-Z][A-Z0-9_]*$/.test(reason)
    || !CONSUMER_FAILURE_REASON_PREFIXES.some(prefix => reason.startsWith(prefix))
  ) return fallback;
  return reason;
}

export interface InactiveMediaActivation {
  readonly active: false;
  readonly reason_id:
    | 'MEDIA_FEATURE_DISABLED'
    | 'MEDIA_AUTHORITY_UNAVAILABLE'
    | 'MEDIA_PROVIDER_UNAVAILABLE'
    | 'MEDIA_TRANSPORT_UNAVAILABLE';
  readonly capability: MediaCapability;
}

export interface ActiveMediaActivation {
  readonly active: true;
  readonly binding: MediaAuthorityBinding;
  readonly owner: BrowserGatewayMediaRegistrationOwner;
  readonly capability: MediaCapability;
}

export type BrowserGatewayMediaActivation = InactiveMediaActivation | ActiveMediaActivation;

export interface MediaEnqueueResult {
  readonly accepted: boolean;
  readonly reason_id: string;
}

export interface MediaDrainResult {
  readonly sent_frames: number;
  readonly pending_frames: number;
  readonly pending_bytes: number;
  readonly reason_id: string;
}

export interface MediaCloseResult {
  readonly was_active: boolean;
  readonly reason_id: MediaDetachReason;
  readonly dropped_frames: number;
  readonly dropped_bytes: number;
  readonly detach: MediaDetach | null;
  readonly business_cancel_count_delta: 0;
}

export type MediaLeafLifecycleEvent =
  | 'activation.ready'
  | 'sender.enqueue'
  | 'sender.drain'
  | 'sender.acknowledge'
  | 'receiver.attach'
  | 'receiver.accept_binary'
  | 'receiver.accept_detach'
  | 'activation.closed'
  | 'lifecycle.snapshot';

export interface MediaLeafLifecycleFact {
  readonly event: MediaLeafLifecycleEvent;
  readonly lease_id: string;
  readonly authority_evidence_id: string;
  readonly connection_id: string;
  readonly connection_epoch: number;
  readonly session_id: string;
  readonly media_session_id: string;
  readonly interaction_id: string;
  readonly track_id: string;
  readonly correlation_id: string;
  readonly direction: MediaDirection;
  readonly generation_kind: MediaGenerationKind;
  readonly generation_id: string;
  readonly generation_value: number;
  readonly response_id: string | null;
  readonly response_generation: number | null;
  readonly unit_id: string | null;
  readonly owner_closed: boolean;
  readonly sender_closed: boolean;
  readonly receiver_attached: boolean;
  readonly receiver_closed: boolean;
  readonly receiver_next_seq: number;
  readonly receiver_next_cursor: number;
  readonly receiver_last_ack: number | null;
  readonly sender_pending_frames: number;
  readonly sender_pending_bytes: number;
  readonly pending_lifecycle_facts: number;
  readonly dropped_lifecycle_facts: number;
  readonly audit_delivery_failures: number;
  readonly evidence_scope: 'browser_gateway_media_registration_leaf_only';
  readonly fact_contains_raw_payload: false;
  readonly registered_route_observed: false;
  readonly formal_route_ready: false;
  readonly route_to_disk_zero_persistence_observed: false;
  readonly business_cancel_count_delta: 0;
}

export interface MediaRegistrationOwnerCloseResult {
  readonly was_active: boolean;
  readonly reason_id: MediaDetachReason;
  readonly dropped_frames: number;
  readonly dropped_bytes: number;
  readonly sender_detach: MediaDetach | null;
  readonly receiver_detach: MediaDetach | null;
  readonly business_cancel_count_delta: 0;
}

function requireId(name: string, value: unknown, maxChars = MAX_ID_CHARS): asserts value is string {
  if (typeof value !== 'string' || value.length === 0 || value.length > maxChars) {
    throw new MediaTransportViolation('MEDIA_INVALID_BINDING', `${name} is invalid`);
  }
}

function requireSafeUint(name: string, value: unknown, reasonId = 'MEDIA_INVALID_BINDING'): asserts value is number {
  if (!Number.isSafeInteger(value) || (value as number) < 0 || (value as number) > MAX_SAFE_UINT) {
    throw new MediaTransportViolation(reasonId, `${name} is not a safe unsigned integer`);
  }
}

function requirePlaybackStopOutcome(value: unknown): asserts value is MediaPlaybackStopOutcome {
  if (typeof value !== 'string' || !(MEDIA_PLAYBACK_STOP_OUTCOMES as readonly string[]).includes(value)) {
    throw new MediaTransportViolation('MEDIA_INVALID_CONTROL', 'playback stop outcome is not closed');
  }
}

function isDetachReason(value: unknown): value is MediaDetachReason {
  return typeof value === 'string' && (MEDIA_DETACH_REASONS as readonly string[]).includes(value);
}

function requireDetachReason(value: unknown, reasonId = 'MEDIA_INVALID_CONTROL'): asserts value is MediaDetachReason {
  if (!isDetachReason(value)) {
    throw new MediaTransportViolation(reasonId, 'detach reason is not closed');
  }
}

function coerceDetachReason(
  value: unknown,
  fallback: MediaDetachReason = 'MEDIA_LOCAL_CLOSE',
): MediaDetachReason {
  return isDetachReason(value) ? value : fallback;
}

function validateFrameFormat(format: MediaFrameFormat): void {
  if (format.encoding !== MEDIA_CAPTURE_ENCODING || format.byte_order !== 'little') {
    throw new MediaTransportViolation('MEDIA_INVALID_FORMAT', 'only pcm_f32 little-endian is accepted');
  }
  if (
    !Number.isInteger(format.channel_count)
    || format.channel_count !== 1
    || !Number.isInteger(format.frame_duration_ms)
    || format.frame_duration_ms !== MEDIA_FRAME_DURATION_MS
  ) {
    throw new MediaTransportViolation('MEDIA_INVALID_FORMAT', 'only 20 ms mono frames are accepted');
  }
  if (
    !Number.isInteger(format.sample_rate_hz)
    || format.sample_rate_hz < MIN_SAMPLE_RATE_HZ
    || format.sample_rate_hz > MAX_SAMPLE_RATE_HZ
    || format.sample_rate_hz % 50 !== 0
    || !Number.isInteger(format.samples_per_channel)
    || format.samples_per_channel !== format.sample_rate_hz / 50
  ) {
    throw new MediaTransportViolation('MEDIA_INVALID_FORMAT', 'format does not describe exact 20 ms audio');
  }
}

function validateBinding(binding: MediaAuthorityBinding): void {
  requireId('lease_id', binding.lease_id, MAX_LEASE_ID_BYTES);
  if (new TextEncoder().encode(binding.lease_id).length > MAX_LEASE_ID_BYTES) {
    throw new MediaTransportViolation('MEDIA_INVALID_BINDING', 'lease_id is too large when encoded');
  }
  requireId('authority_evidence_id', binding.authority_evidence_id);
  requireId('connection_id', binding.connection_id);
  requireSafeUint('connection_epoch', binding.connection_epoch);
  requireId('session_id', binding.session_id);
  requireId('media_session_id', binding.media_session_id);
  requireId('interaction_id', binding.interaction_id);
  requireId('track_id', binding.track_id);
  requireId('correlation_id', binding.correlation_id);
  if (binding.direction !== 'uplink' && binding.direction !== 'downlink') {
    throw new MediaTransportViolation('MEDIA_INVALID_BINDING', 'direction is not closed');
  }
  if (binding.generation.kind !== 'capture' && binding.generation.kind !== 'response') {
    throw new MediaTransportViolation('MEDIA_INVALID_BINDING', 'generation kind is not closed');
  }
  requireId('generation.id', binding.generation.id);
  requireSafeUint('generation.value', binding.generation.value);
  validateFrameFormat(binding.frame_format);
  if (binding.direction === 'uplink') {
    if (binding.generation.kind !== 'capture' || binding.playout !== null) {
      throw new MediaTransportViolation('MEDIA_INVALID_BINDING', 'uplink authority is inconsistent');
    }
    return;
  }
  if (binding.generation.kind !== 'response' || binding.playout === null) {
    throw new MediaTransportViolation('MEDIA_INVALID_BINDING', 'downlink requires response playout authority');
  }
  requireId('playout.response_id', binding.playout.response_id);
  requireSafeUint('playout.response_generation', binding.playout.response_generation);
  requireId('playout.unit_id', binding.playout.unit_id);
  if (
    binding.generation.id !== binding.playout.response_id
    || binding.generation.value !== binding.playout.response_generation
  ) {
    throw new MediaTransportViolation('MEDIA_INVALID_BINDING', 'response generation is not exact');
  }
}

function freezeBinding(binding: MediaAuthorityBinding): MediaAuthorityBinding {
  validateBinding(binding);
  const generation = Object.freeze({ ...binding.generation });
  const frameFormat = Object.freeze({ ...binding.frame_format });
  const playout = binding.playout === null ? null : Object.freeze({ ...binding.playout });
  return Object.freeze({ ...binding, generation, frame_format: frameFormat, playout });
}

function capability(): MediaCapability {
  return Object.freeze({
    contract_version: MEDIA_CONTRACT_VERSION,
    transport_kind: MEDIA_TRANSPORT_KIND,
    wire_codec: MEDIA_WIRE_CODEC,
    capture_encoding: MEDIA_CAPTURE_ENCODING,
    frame_duration_ms: MEDIA_FRAME_DURATION_MS,
    channel_count: 1,
    provider_neutral: true,
    evidence_scope: 'contract_only',
    contract_vector_evidence_id: 'live-voice.media.v1.roundtrip-vector',
    formal_route_ready: false,
    real_transport_observed: false,
    registration_evidence_id: null,
    runtime_evidence_id: null,
  });
}

export function createBrowserGatewayMediaActivation(
  request: MediaActivationRequest,
): BrowserGatewayMediaActivation {
  const inactive = (reason_id: InactiveMediaActivation['reason_id']): InactiveMediaActivation => ({
    active: false,
    reason_id,
    capability: capability(),
  });
  if (request.enabled !== true) return inactive('MEDIA_FEATURE_DISABLED');
  if (request.binding === null || request.binding === undefined) return inactive('MEDIA_AUTHORITY_UNAVAILABLE');
  if (request.provider_available !== true) return inactive('MEDIA_PROVIDER_UNAVAILABLE');
  if (request.transport_available !== true) return inactive('MEDIA_TRANSPORT_UNAVAILABLE');
  const maxFrames = request.max_pending_frames ?? 8;
  const maxBytes = request.max_pending_bytes ?? 131_072;
  const lifecycleFactCapacity = request.lifecycle_fact_capacity ?? 32;
  if (!Number.isInteger(maxFrames) || maxFrames <= 0 || !Number.isInteger(maxBytes) || maxBytes <= 0) {
    throw new MediaTransportViolation('MEDIA_INVALID_LIMIT', 'queue bounds must be positive integers');
  }
  if (
    !Number.isInteger(lifecycleFactCapacity)
    || lifecycleFactCapacity <= 0
    || lifecycleFactCapacity > MAX_LIFECYCLE_FACT_CAPACITY
  ) {
    throw new MediaTransportViolation(
      'MEDIA_INVALID_AUDIT_CAPACITY',
      `lifecycle fact capacity must be an integer in [1, ${MAX_LIFECYCLE_FACT_CAPACITY}]`,
    );
  }
  if (typeof request.on_audio_frame !== 'function') {
    throw new MediaTransportViolation('MEDIA_INVALID_CONSUMER', 'audio consumer must be callable');
  }
  if (request.on_lifecycle_fact !== undefined && typeof request.on_lifecycle_fact !== 'function') {
    throw new MediaTransportViolation('MEDIA_INVALID_AUDIT_CALLBACK', 'lifecycle fact consumer must be callable');
  }
  const binding = freezeBinding(request.binding);
  const owner = new BrowserGatewayMediaRegistrationOwner(
    binding,
    maxFrames,
    maxBytes,
    request.on_audio_frame,
    request.on_lifecycle_fact,
    lifecycleFactCapacity,
    REGISTRATION_OWNER_CONSTRUCTION_TOKEN,
  );
  return {
    active: true,
    binding,
    owner,
    capability: capability(),
  };
}

function writeSafeUint64(view: DataView, offset: number, value: number): void {
  requireSafeUint('wire integer', value, 'MEDIA_INVALID_FRAME');
  const low = value % 0x1_0000_0000;
  const high = Math.floor(value / 0x1_0000_0000);
  view.setUint32(offset, low, true);
  view.setUint32(offset + 4, high, true);
}

function readSafeUint64(view: DataView, offset: number): number {
  const low = view.getUint32(offset, true);
  const high = view.getUint32(offset + 4, true);
  const value = low + high * 0x1_0000_0000;
  requireSafeUint('wire integer', value, 'MEDIA_MALFORMED_FRAME');
  return value;
}

export function encodeAudioFrame(binding: MediaAuthorityBinding, frame: MediaAudioFrame): Uint8Array {
  validateBinding(binding);
  requireSafeUint('frame.seq', frame.seq, 'MEDIA_INVALID_FRAME');
  requireSafeUint('frame.sample_cursor', frame.sample_cursor, 'MEDIA_INVALID_FRAME');
  if (!(frame.samples instanceof Float32Array) || frame.samples.length !== binding.frame_format.samples_per_channel) {
    throw new MediaTransportViolation('MEDIA_INVALID_FRAME', 'frame does not contain exact 20 ms audio');
  }
  for (const sample of frame.samples) {
    if (!Number.isFinite(sample)) {
      throw new MediaTransportViolation('MEDIA_NONFINITE_AUDIO', 'frame contains non-finite samples');
    }
    if (Math.abs(sample) > MAX_PCM_F32_ABS) {
      throw new MediaTransportViolation('MEDIA_INVALID_FRAME', 'frame sample is outside pcm_f32 range');
    }
  }
  const lease = new TextEncoder().encode(binding.lease_id);
  if (lease.length === 0 || lease.length > MAX_LEASE_ID_BYTES) {
    throw new MediaTransportViolation('MEDIA_INVALID_BINDING', 'lease id is too large');
  }
  const payloadBytes = frame.samples.length * 4;
  const binary = new Uint8Array(WIRE_HEADER_BYTES + lease.length + payloadBytes);
  binary.set(WIRE_MAGIC, 0);
  const view = new DataView(binary.buffer);
  view.setUint8(4, WIRE_VERSION);
  view.setUint8(5, WIRE_AUDIO_KIND);
  view.setUint16(6, lease.length, true);
  writeSafeUint64(view, 8, binding.generation.value);
  writeSafeUint64(view, 16, frame.seq);
  writeSafeUint64(view, 24, frame.sample_cursor);
  view.setUint32(32, payloadBytes, true);
  binary.set(lease, WIRE_HEADER_BYTES);
  const payloadOffset = WIRE_HEADER_BYTES + lease.length;
  for (let index = 0; index < frame.samples.length; index += 1) {
    view.setFloat32(payloadOffset + index * 4, frame.samples[index]!, true);
  }
  return binary;
}

export function decodeAudioFrame(binding: MediaAuthorityBinding, raw: Uint8Array): MediaAudioFrame {
  validateBinding(binding);
  if (!(raw instanceof Uint8Array)) {
    throw new MediaTransportViolation('MEDIA_MALFORMED_FRAME', 'audio frame is not binary');
  }
  if (raw.byteLength > MAX_BINARY_FRAME_BYTES) {
    throw new MediaTransportViolation('MEDIA_OVERSIZED_FRAME', 'audio frame exceeds its global bound');
  }
  if (raw.byteLength < WIRE_HEADER_BYTES) {
    throw new MediaTransportViolation('MEDIA_MALFORMED_FRAME', 'audio frame is truncated');
  }
  const view = new DataView(raw.buffer, raw.byteOffset, raw.byteLength);
  for (let index = 0; index < WIRE_MAGIC.length; index += 1) {
    if (view.getUint8(index) !== WIRE_MAGIC[index]) {
      throw new MediaTransportViolation('MEDIA_MALFORMED_FRAME', 'audio frame magic is not accepted');
    }
  }
  if (view.getUint8(4) !== WIRE_VERSION || view.getUint8(5) !== WIRE_AUDIO_KIND) {
    throw new MediaTransportViolation('MEDIA_MALFORMED_FRAME', 'audio frame header is not accepted');
  }
  const leaseLength = view.getUint16(6, true);
  const generation = readSafeUint64(view, 8);
  const seq = readSafeUint64(view, 16);
  const sampleCursor = readSafeUint64(view, 24);
  const payloadLength = view.getUint32(32, true);
  if (leaseLength === 0 || leaseLength > MAX_LEASE_ID_BYTES) {
    throw new MediaTransportViolation('MEDIA_MALFORMED_FRAME', 'lease length is invalid');
  }
  if (payloadLength !== binding.frame_format.samples_per_channel * 4) {
    throw new MediaTransportViolation('MEDIA_INVALID_FRAME', 'payload does not contain exact 20 ms audio');
  }
  if (raw.byteLength !== WIRE_HEADER_BYTES + leaseLength + payloadLength) {
    throw new MediaTransportViolation('MEDIA_MALFORMED_FRAME', 'audio frame length is inconsistent');
  }
  let leaseId: string;
  try {
    leaseId = new TextDecoder('utf-8', { fatal: true }).decode(
      raw.subarray(WIRE_HEADER_BYTES, WIRE_HEADER_BYTES + leaseLength),
    );
  } catch (error: unknown) {
    throw new MediaTransportViolation('MEDIA_MALFORMED_FRAME', `lease id is not UTF-8: ${String(error)}`);
  }
  if (leaseId !== binding.lease_id) {
    throw new MediaTransportViolation('MEDIA_BINDING_MISMATCH', 'lease binding does not match');
  }
  if (generation !== binding.generation.value) {
    throw new MediaTransportViolation('MEDIA_STALE_GENERATION', 'frame generation does not match');
  }
  const samples = new Float32Array(binding.frame_format.samples_per_channel);
  const payloadOffset = WIRE_HEADER_BYTES + leaseLength;
  for (let index = 0; index < samples.length; index += 1) {
    const sample = view.getFloat32(payloadOffset + index * 4, true);
    if (!Number.isFinite(sample)) {
      throw new MediaTransportViolation('MEDIA_NONFINITE_AUDIO', 'frame contains non-finite samples');
    }
    samples[index] = sample;
  }
  return { seq, sample_cursor: sampleCursor, samples };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function requireRecord(value: unknown, name: string): Record<string, unknown> {
  if (!isRecord(value)) {
    throw new MediaTransportViolation('MEDIA_MALFORMED_CONTROL', `${name} is not an object`);
  }
  return value;
}

function requireExactKeys(value: Record<string, unknown>, expected: readonly string[], name: string): void {
  const actual = Object.keys(value).sort();
  const wanted = [...expected].sort();
  if (actual.length !== wanted.length || actual.some((key, index) => key !== wanted[index])) {
    throw new MediaTransportViolation('MEDIA_MALFORMED_CONTROL', `${name} fields are not closed`);
  }
}

function parseBinding(value: unknown): MediaAuthorityBinding {
  const raw = requireRecord(value, 'binding');
  requireExactKeys(raw, [
    'lease_id', 'authority_evidence_id', 'connection_id', 'connection_epoch', 'session_id',
    'media_session_id', 'interaction_id', 'track_id', 'correlation_id', 'direction',
    'generation', 'frame_format', 'playout',
  ], 'binding');
  const generation = requireRecord(raw.generation, 'generation');
  requireExactKeys(generation, ['kind', 'id', 'value'], 'generation');
  const format = requireRecord(raw.frame_format, 'frame_format');
  requireExactKeys(
    format,
    ['sample_rate_hz', 'samples_per_channel', 'encoding', 'byte_order', 'channel_count', 'frame_duration_ms'],
    'frame_format',
  );
  let playout: MediaPlayoutBinding | null = null;
  if (raw.playout !== null) {
    const item = requireRecord(raw.playout, 'playout');
    requireExactKeys(item, ['response_id', 'response_generation', 'unit_id'], 'playout');
    requireId('playout.response_id', item.response_id);
    requireSafeUint('playout.response_generation', item.response_generation, 'MEDIA_MALFORMED_CONTROL');
    requireId('playout.unit_id', item.unit_id);
    playout = {
      response_id: item.response_id,
      response_generation: item.response_generation,
      unit_id: item.unit_id,
    };
  }
  requireId('lease_id', raw.lease_id, MAX_LEASE_ID_BYTES);
  requireId('authority_evidence_id', raw.authority_evidence_id);
  requireId('connection_id', raw.connection_id);
  requireSafeUint('connection_epoch', raw.connection_epoch, 'MEDIA_MALFORMED_CONTROL');
  requireId('session_id', raw.session_id);
  requireId('media_session_id', raw.media_session_id);
  requireId('interaction_id', raw.interaction_id);
  requireId('track_id', raw.track_id);
  requireId('correlation_id', raw.correlation_id);
  requireId('generation.id', generation.id);
  requireSafeUint('generation.value', generation.value, 'MEDIA_MALFORMED_CONTROL');
  requireSafeUint('frame_format.sample_rate_hz', format.sample_rate_hz, 'MEDIA_MALFORMED_CONTROL');
  requireSafeUint('frame_format.samples_per_channel', format.samples_per_channel, 'MEDIA_MALFORMED_CONTROL');
  const binding: MediaAuthorityBinding = {
    lease_id: raw.lease_id,
    authority_evidence_id: raw.authority_evidence_id,
    connection_id: raw.connection_id,
    connection_epoch: raw.connection_epoch,
    session_id: raw.session_id,
    media_session_id: raw.media_session_id,
    interaction_id: raw.interaction_id,
    track_id: raw.track_id,
    correlation_id: raw.correlation_id,
    direction: raw.direction as MediaDirection,
    generation: {
      kind: generation.kind as MediaGenerationKind,
      id: generation.id,
      value: generation.value,
    },
    frame_format: {
      sample_rate_hz: format.sample_rate_hz,
      samples_per_channel: format.samples_per_channel,
      encoding: format.encoding as typeof MEDIA_CAPTURE_ENCODING,
      byte_order: format.byte_order as 'little',
      channel_count: format.channel_count as 1,
      frame_duration_ms: format.frame_duration_ms as typeof MEDIA_FRAME_DURATION_MS,
    },
    playout,
  };
  return freezeBinding(binding);
}

export function serializeMediaControl(control: MediaControl): string {
  if (control.type === 'media.ack') {
    requireId('lease_id', control.lease_id, MAX_LEASE_ID_BYTES);
    requireSafeUint('generation', control.generation);
    requireSafeUint('through_seq', control.through_seq);
  } else if (control.type === 'media.detach') {
    requireId('lease_id', control.lease_id, MAX_LEASE_ID_BYTES);
    requireSafeUint('generation', control.generation);
    requireDetachReason(control.reason_id);
    if (control.through_seq !== null) requireSafeUint('through_seq', control.through_seq);
    if (control.business_cancel_count_delta !== 0) {
      throw new MediaTransportViolation('MEDIA_CANCEL_SCOPE_VIOLATION', 'detach cannot carry business cancellation');
    }
  } else if (control.type === 'media.playback_stop_receipt') {
    requireId('lease_id', control.lease_id, MAX_LEASE_ID_BYTES);
    requireId('response_id', control.response_id);
    requireSafeUint('response_generation', control.response_generation);
    requireId('unit_id', control.unit_id);
    requirePlaybackStopOutcome(control.outcome);
    if (control.confirmed_through_seq !== null) {
      requireSafeUint('confirmed_through_seq', control.confirmed_through_seq);
    }
    if (control.business_cancel_count_delta !== 0) {
      throw new MediaTransportViolation(
        'MEDIA_CANCEL_SCOPE_VIOLATION',
        'playback stop cannot carry business cancellation',
      );
    }
  } else if (control.type === 'media.speech_start') {
    requireId('lease_id', control.lease_id, MAX_LEASE_ID_BYTES);
    requireSafeUint('generation', control.generation);
    requireSafeUint('provider_start_ms', control.provider_start_ms);
    if (
      control.capability_version !== MEDIA_END_OF_TURN_CAPABILITY ||
      control.detector !== 'server_vad' ||
      control.timing_basis !== 'provider_time' ||
      control.timing_provenance !== 'adapter_derived' ||
      control.create_response !== false ||
      control.interrupt_response !== false ||
      control.business_cancel_count_delta !== 0
    ) {
      throw new MediaTransportViolation('MEDIA_INVALID_CONTROL', 'speech-start control contract is not exact');
    }
  } else if (control.type === 'media.end_of_turn') {
    requireId('lease_id', control.lease_id, MAX_LEASE_ID_BYTES);
    requireSafeUint('generation', control.generation);
    requireSafeUint('provider_start_ms', control.provider_start_ms);
    requireSafeUint('provider_end_ms', control.provider_end_ms);
    if (
      control.capability_version !== MEDIA_END_OF_TURN_CAPABILITY ||
      control.detector !== 'server_vad' ||
      control.speech_started_observed !== true ||
      control.provider_end_ms < control.provider_start_ms ||
      control.timing_basis !== 'provider_time' ||
      control.timing_provenance !== 'adapter_derived' ||
      control.create_response !== false ||
      control.interrupt_response !== false ||
      control.business_cancel_count_delta !== 0
    ) {
      throw new MediaTransportViolation('MEDIA_INVALID_CONTROL', 'EOT control contract is not exact');
    }
  } else {
    validateBinding(control.binding);
  }
  const text = JSON.stringify({
    ...control,
    contract_version: MEDIA_CONTRACT_VERSION,
  });
  if (new TextEncoder().encode(text).length > MAX_CONTROL_BYTES) {
    throw new MediaTransportViolation('MEDIA_OVERSIZED_CONTROL', 'control message exceeds its bound');
  }
  return text;
}

export function deserializeMediaControl(text: string): MediaControl {
  if (typeof text !== 'string' || new TextEncoder().encode(text).length > MAX_CONTROL_BYTES) {
    throw new MediaTransportViolation('MEDIA_OVERSIZED_CONTROL', 'control message exceeds its bound');
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch (error: unknown) {
    throw new MediaTransportViolation('MEDIA_MALFORMED_CONTROL', `control is not valid JSON: ${String(error)}`);
  }
  const raw = requireRecord(parsed, 'control');
  if (raw.contract_version !== MEDIA_CONTRACT_VERSION) {
    throw new MediaTransportViolation('MEDIA_MALFORMED_CONTROL', 'control contract version is not accepted');
  }
  if (raw.type === 'media.attach') {
    requireExactKeys(raw, ['type', 'contract_version', 'binding'], 'attach');
    return Object.freeze({ type: 'media.attach', binding: parseBinding(raw.binding) });
  }
  if (raw.type === 'media.ack') {
    requireExactKeys(raw, ['type', 'contract_version', 'lease_id', 'generation', 'through_seq'], 'ack');
    requireId('lease_id', raw.lease_id, MAX_LEASE_ID_BYTES);
    requireSafeUint('generation', raw.generation, 'MEDIA_MALFORMED_CONTROL');
    requireSafeUint('through_seq', raw.through_seq, 'MEDIA_MALFORMED_CONTROL');
    return Object.freeze({
      type: 'media.ack', lease_id: raw.lease_id, generation: raw.generation, through_seq: raw.through_seq,
    });
  }
  if (raw.type === 'media.detach') {
    requireExactKeys(
      raw,
      ['type', 'contract_version', 'lease_id', 'generation', 'reason_id', 'through_seq', 'business_cancel_count_delta'],
      'detach',
    );
    requireId('lease_id', raw.lease_id, MAX_LEASE_ID_BYTES);
    requireDetachReason(raw.reason_id, 'MEDIA_MALFORMED_CONTROL');
    requireSafeUint('generation', raw.generation, 'MEDIA_MALFORMED_CONTROL');
    if (raw.through_seq !== null) requireSafeUint('through_seq', raw.through_seq, 'MEDIA_MALFORMED_CONTROL');
    if (raw.business_cancel_count_delta !== 0) {
      throw new MediaTransportViolation('MEDIA_MALFORMED_CONTROL', 'detach cannot carry business cancellation');
    }
    return Object.freeze({
      type: 'media.detach',
      lease_id: raw.lease_id,
      generation: raw.generation,
      reason_id: raw.reason_id,
      through_seq: raw.through_seq as number | null,
      business_cancel_count_delta: 0,
    });
  }
  if (raw.type === 'media.speech_start') {
    requireExactKeys(
      raw,
      [
        'type',
        'contract_version',
        'capability_version',
        'lease_id',
        'generation',
        'detector',
        'provider_start_ms',
        'timing_basis',
        'timing_provenance',
        'create_response',
        'interrupt_response',
        'business_cancel_count_delta',
      ],
      'speech_start'
    );
    requireId('lease_id', raw.lease_id, MAX_LEASE_ID_BYTES);
    requireSafeUint('generation', raw.generation, 'MEDIA_MALFORMED_CONTROL');
    requireSafeUint('provider_start_ms', raw.provider_start_ms, 'MEDIA_MALFORMED_CONTROL');
    if (
      raw.capability_version !== MEDIA_END_OF_TURN_CAPABILITY ||
      raw.detector !== 'server_vad' ||
      raw.timing_basis !== 'provider_time' ||
      raw.timing_provenance !== 'adapter_derived' ||
      raw.create_response !== false ||
      raw.interrupt_response !== false ||
      raw.business_cancel_count_delta !== 0
    ) {
      throw new MediaTransportViolation('MEDIA_MALFORMED_CONTROL', 'speech-start control contract is not exact');
    }
    return Object.freeze({
      type: 'media.speech_start',
      capability_version: MEDIA_END_OF_TURN_CAPABILITY,
      lease_id: raw.lease_id,
      generation: raw.generation,
      detector: 'server_vad',
      provider_start_ms: raw.provider_start_ms,
      timing_basis: 'provider_time',
      timing_provenance: 'adapter_derived',
      create_response: false,
      interrupt_response: false,
      business_cancel_count_delta: 0,
    });
  }
  if (raw.type === 'media.end_of_turn') {
    requireExactKeys(
      raw,
      [
        'type',
        'contract_version',
        'capability_version',
        'lease_id',
        'generation',
        'detector',
        'speech_started_observed',
        'provider_start_ms',
        'provider_end_ms',
        'timing_basis',
        'timing_provenance',
        'create_response',
        'interrupt_response',
        'business_cancel_count_delta',
      ],
      'end_of_turn'
    );
    requireId('lease_id', raw.lease_id, MAX_LEASE_ID_BYTES);
    requireSafeUint('generation', raw.generation, 'MEDIA_MALFORMED_CONTROL');
    requireSafeUint('provider_start_ms', raw.provider_start_ms, 'MEDIA_MALFORMED_CONTROL');
    requireSafeUint('provider_end_ms', raw.provider_end_ms, 'MEDIA_MALFORMED_CONTROL');
    if (
      raw.capability_version !== MEDIA_END_OF_TURN_CAPABILITY ||
      raw.detector !== 'server_vad' ||
      raw.speech_started_observed !== true ||
      raw.provider_end_ms < raw.provider_start_ms ||
      raw.timing_basis !== 'provider_time' ||
      raw.timing_provenance !== 'adapter_derived' ||
      raw.create_response !== false ||
      raw.interrupt_response !== false ||
      raw.business_cancel_count_delta !== 0
    ) {
      throw new MediaTransportViolation('MEDIA_MALFORMED_CONTROL', 'EOT control contract is not exact');
    }
    return Object.freeze({
      type: 'media.end_of_turn',
      capability_version: MEDIA_END_OF_TURN_CAPABILITY,
      lease_id: raw.lease_id,
      generation: raw.generation,
      detector: 'server_vad',
      speech_started_observed: true,
      provider_start_ms: raw.provider_start_ms,
      provider_end_ms: raw.provider_end_ms,
      timing_basis: 'provider_time',
      timing_provenance: 'adapter_derived',
      create_response: false,
      interrupt_response: false,
      business_cancel_count_delta: 0,
    });
  }
  if (raw.type === 'media.playback_stop_receipt') {
    requireExactKeys(raw, [
      'type', 'contract_version', 'lease_id', 'response_id', 'response_generation', 'unit_id',
      'outcome', 'confirmed_through_seq', 'business_cancel_count_delta',
    ], 'playback_stop_receipt');
    requireId('lease_id', raw.lease_id, MAX_LEASE_ID_BYTES);
    requireId('response_id', raw.response_id);
    requireSafeUint('response_generation', raw.response_generation, 'MEDIA_MALFORMED_CONTROL');
    requireId('unit_id', raw.unit_id);
    requirePlaybackStopOutcome(raw.outcome);
    if (raw.confirmed_through_seq !== null) {
      requireSafeUint('confirmed_through_seq', raw.confirmed_through_seq, 'MEDIA_MALFORMED_CONTROL');
    }
    if (raw.business_cancel_count_delta !== 0) {
      throw new MediaTransportViolation('MEDIA_MALFORMED_CONTROL', 'playback stop cannot carry business cancellation');
    }
    return Object.freeze({
      type: 'media.playback_stop_receipt',
      lease_id: raw.lease_id,
      response_id: raw.response_id,
      response_generation: raw.response_generation,
      unit_id: raw.unit_id,
      outcome: raw.outcome,
      confirmed_through_seq: raw.confirmed_through_seq as number | null,
      business_cancel_count_delta: 0,
    });
  }
  throw new MediaTransportViolation('MEDIA_MALFORMED_CONTROL', 'unknown control type');
}

interface QueuedFrameMetadata {
  readonly seq: number;
  readonly sample_cursor: number;
}

interface QueuedFrame {
  readonly metadata: Readonly<QueuedFrameMetadata>;
  readonly binary: Uint8Array;
  sent: boolean;
}

function detachFor(binding: MediaAuthorityBinding, reasonId: MediaDetachReason, throughSeq: number | null): MediaDetach {
  return Object.freeze({
    type: 'media.detach',
    lease_id: binding.lease_id,
    generation: binding.generation.value,
    reason_id: reasonId,
    through_seq: throughSeq,
    business_cancel_count_delta: 0,
  });
}

export class BoundedMediaSender {
  readonly binding: MediaAuthorityBinding;
  private readonly maxPendingFrames: number;
  private readonly maxPendingBytes: number;
  private readonly queue: QueuedFrame[] = [];
  private pendingByteCount = 0;
  private nextSeq = 0;
  private nextCursor = 0;
  private lastAck = -1;
  private closedState = false;
  private detachState: MediaDetach | null = null;

  constructor(binding: MediaAuthorityBinding, maxPendingFrames: number, maxPendingBytes: number) {
    if (!Number.isInteger(maxPendingFrames) || maxPendingFrames <= 0
      || !Number.isInteger(maxPendingBytes) || maxPendingBytes <= 0) {
      throw new MediaTransportViolation('MEDIA_INVALID_LIMIT', 'queue bounds must be positive integers');
    }
    this.binding = freezeBinding(binding);
    this.maxPendingFrames = maxPendingFrames;
    this.maxPendingBytes = maxPendingBytes;
  }

  get pending_frames(): number { return this.queue.length; }
  get pending_bytes(): number { return this.pendingByteCount; }
  get closed(): boolean { return this.closedState; }

  private terminal(reasonId: unknown): MediaDetach {
    this.detachState ??= detachFor(
      this.binding,
      coerceDetachReason(reasonId),
      this.lastAck < 0 ? null : this.lastAck,
    );
    this.closedState = true;
    return this.detachState;
  }

  enqueue(frame: MediaAudioFrame): MediaEnqueueResult {
    if (this.closedState) return { accepted: false, reason_id: 'MEDIA_LEASE_CLOSED' };
    if (frame.seq !== this.nextSeq) {
      this.terminal('MEDIA_SEQUENCE_VIOLATION');
      return { accepted: false, reason_id: 'MEDIA_SEQUENCE_VIOLATION' };
    }
    if (frame.sample_cursor !== this.nextCursor) {
      this.terminal('MEDIA_CURSOR_MISMATCH');
      return { accepted: false, reason_id: 'MEDIA_CURSOR_MISMATCH' };
    }
    let binary: Uint8Array;
    try {
      binary = encodeAudioFrame(this.binding, frame);
    } catch (error: unknown) {
      if (!(error instanceof MediaTransportViolation)) throw error;
      this.terminal(error.reasonId);
      return { accepted: false, reason_id: error.reasonId };
    }
    if (
      this.queue.length >= this.maxPendingFrames
      || this.pendingByteCount + binary.byteLength > this.maxPendingBytes
    ) {
      return { accepted: false, reason_id: 'MEDIA_BACKPRESSURE_LIMIT' };
    }
    this.queue.push({
      metadata: Object.freeze({ seq: frame.seq, sample_cursor: frame.sample_cursor }),
      binary,
      sent: false,
    });
    this.pendingByteCount += binary.byteLength;
    this.nextSeq += 1;
    this.nextCursor += this.binding.frame_format.samples_per_channel;
    return { accepted: true, reason_id: 'MEDIA_ENQUEUED' };
  }

  drain(
    trySendBinary: (binary: Uint8Array) => BinarySendDisposition,
    onFrameSent?: (seq: number) => void
  ): MediaDrainResult {
    if (this.closedState) {
      return {
        sent_frames: 0, pending_frames: this.queue.length, pending_bytes: this.pendingByteCount, reason_id: 'MEDIA_LEASE_CLOSED',
      };
    }
    let sentFrames = 0;
    for (const item of this.queue) {
      if (item.sent) continue;
      let disposition: BinarySendDisposition;
      try {
        disposition = trySendBinary(item.binary.slice());
      } catch {
        this.terminal('MEDIA_TRANSPORT_SEND_FAILED');
        break;
      }
      if (this.closedState) break;
      if (disposition === 'backpressured') break;
      if (disposition === 'closed') {
        this.terminal('MEDIA_TRANSPORT_CLOSED');
        break;
      }
      if (disposition !== 'sent') {
        this.terminal('MEDIA_TRANSPORT_PROTOCOL_ERROR');
        break;
      }
      item.sent = true;
      sentFrames += 1;
      try {
        onFrameSent?.(item.metadata.seq);
      } catch {
        // Optional transport diagnostics cannot alter sender ownership.
      }
    }
    return {
      sent_frames: sentFrames,
      pending_frames: this.queue.length,
      pending_bytes: this.pendingByteCount,
      reason_id: this.detachState?.reason_id ?? (
        sentFrames > 0
          ? 'MEDIA_DRAINED'
          : this.queue.length > 0 && this.queue.every((item) => item.sent)
            ? 'MEDIA_AWAITING_ACK'
            : 'MEDIA_BACKPRESSURED'
      ),
    };
  }

  acknowledge(control: MediaAck): MediaDetach | null {
    if (this.closedState) return this.detachState ?? this.terminal('MEDIA_LEASE_CLOSED');
    if (control.lease_id !== this.binding.lease_id) return this.terminal('MEDIA_BINDING_MISMATCH');
    if (control.generation !== this.binding.generation.value) return this.terminal('MEDIA_STALE_GENERATION');
    if (control.through_seq < this.lastAck) return this.terminal('MEDIA_ACK_OUT_OF_ORDER');
    if (control.through_seq === this.lastAck) return null;
    const candidates = this.queue.filter((item) => item.metadata.seq <= control.through_seq);
    if (candidates.some((item) => !item.sent)) return this.terminal('MEDIA_ACK_UNSENT');
    if (
      candidates.length === 0
      || candidates[0]!.metadata.seq !== this.lastAck + 1
      || candidates[candidates.length - 1]!.metadata.seq !== control.through_seq
    ) {
      return this.terminal('MEDIA_ACK_GAP');
    }
    for (const item of candidates) {
      this.queue.shift();
      this.pendingByteCount -= item.binary.byteLength;
    }
    this.lastAck = control.through_seq;
    return null;
  }

  close(reasonId: MediaDetachReason = 'MEDIA_LOCAL_CLOSE'): MediaCloseResult {
    const wasActive = !this.closedState;
    const detach = this.terminal(coerceDetachReason(reasonId));
    const droppedFrames = this.queue.length;
    const droppedBytes = this.pendingByteCount;
    this.queue.splice(0);
    this.pendingByteCount = 0;
    return {
      was_active: wasActive,
      reason_id: detach.reason_id,
      dropped_frames: droppedFrames,
      dropped_bytes: droppedBytes,
      detach,
      business_cancel_count_delta: 0,
    };
  }
}

export class StrictMediaReceiver {
  readonly binding: MediaAuthorityBinding;
  private readonly onAudioFrame: (frame: MediaAudioFrame) => void;
  private attachedState = false;
  private closedState = false;
  private nextSeq = 0;
  private nextCursor = 0;
  private lastAck = -1;
  private detachState: MediaDetach | null = null;
  private consumerFailureReasonId: string | null = null;

  constructor(binding: MediaAuthorityBinding, onAudioFrame: (frame: MediaAudioFrame) => void) {
    if (typeof onAudioFrame !== 'function') {
      throw new MediaTransportViolation('MEDIA_INVALID_CONSUMER', 'audio consumer must be callable');
    }
    this.binding = freezeBinding(binding);
    this.onAudioFrame = onAudioFrame;
  }

  get attached(): boolean { return this.attachedState; }
  get closed(): boolean { return this.closedState; }
  get next_seq(): number { return this.nextSeq; }
  get next_cursor(): number { return this.nextCursor; }
  get last_ack(): number | null { return this.lastAck < 0 ? null : this.lastAck; }
  get consumer_failure_reason_id(): string | null { return this.consumerFailureReasonId; }

  private terminal(reasonId: unknown): MediaDetach {
    this.detachState ??= detachFor(
      this.binding,
      coerceDetachReason(reasonId, 'MEDIA_MALFORMED_FRAME'),
      this.lastAck < 0 ? null : this.lastAck,
    );
    this.closedState = true;
    this.attachedState = false;
    return this.detachState;
  }

  attach(control: MediaAttach): MediaDetach | null {
    if (this.closedState) return this.detachState ?? this.terminal('MEDIA_LEASE_CLOSED');
    if (this.attachedState) return this.terminal('MEDIA_DUPLICATE_ATTACH');
    if (!bindingsEqual(control.binding, this.binding)) return this.terminal('MEDIA_BINDING_MISMATCH');
    this.attachedState = true;
    return null;
  }

  acceptBinary(raw: Uint8Array): MediaAck | MediaDetach {
    if (this.closedState) return this.detachState ?? this.terminal('MEDIA_LEASE_CLOSED');
    if (!this.attachedState) return this.terminal('MEDIA_NOT_ATTACHED');
    let frame: MediaAudioFrame;
    try {
      frame = decodeAudioFrame(this.binding, raw);
    } catch (error: unknown) {
      if (!(error instanceof MediaTransportViolation)) throw error;
      return this.terminal(error.reasonId);
    }
    if (frame.seq < this.nextSeq) return this.terminal('MEDIA_DUPLICATE_OR_OUT_OF_ORDER');
    if (frame.seq > this.nextSeq) return this.terminal('MEDIA_SEQUENCE_GAP');
    if (frame.sample_cursor !== this.nextCursor) return this.terminal('MEDIA_CURSOR_MISMATCH');
    try {
      this.onAudioFrame(frame);
    } catch (error: unknown) {
      this.consumerFailureReasonId = boundedMediaConsumerFailureReason(
        error,
        'ADAPTER_AUDIO_FRAME_CALLBACK_FAILED'
      );
      return this.terminal('MEDIA_CONSUMER_FAILED');
    }
    if (this.closedState) return this.detachState ?? this.terminal('MEDIA_LEASE_CLOSED');
    this.lastAck = frame.seq;
    this.nextSeq += 1;
    this.nextCursor += this.binding.frame_format.samples_per_channel;
    return Object.freeze({
      type: 'media.ack',
      lease_id: this.binding.lease_id,
      generation: this.binding.generation.value,
      through_seq: frame.seq,
    });
  }

  acceptDetach(control: MediaDetach): MediaCloseResult {
    requireDetachReason(control.reason_id);
    if (control.business_cancel_count_delta !== 0) {
      throw new MediaTransportViolation(
        'MEDIA_INVALID_CONTROL',
        'business cancellation delta must be canonical number zero',
      );
    }
    const wasActive = !this.closedState;
    let detach: MediaDetach;
    if (control.lease_id !== this.binding.lease_id) detach = this.terminal('MEDIA_BINDING_MISMATCH');
    else if (control.generation !== this.binding.generation.value) detach = this.terminal('MEDIA_STALE_GENERATION');
    else detach = this.terminal(control.reason_id);
    return {
      was_active: wasActive,
      reason_id: detach.reason_id,
      dropped_frames: 0,
      dropped_bytes: 0,
      detach,
      business_cancel_count_delta: 0,
    };
  }

  close(reasonId: MediaDetachReason = 'MEDIA_LOCAL_CLOSE'): MediaCloseResult {
    const wasActive = !this.closedState;
    const detach = this.terminal(coerceDetachReason(reasonId));
    return {
      was_active: wasActive,
      reason_id: detach.reason_id,
      dropped_frames: 0,
      dropped_bytes: 0,
      detach,
      business_cancel_count_delta: 0,
    };
  }
}

/**
 * One bounded, non-formal registration owner for the existing Media contract.
 *
 * The owner opens no socket and writes no log or storage.  Its synchronous
 * close cannot be cancelled or timed out midway, and every close caller
 * observes the same retained result.  Operations only retain frozen,
 * payload-free facts in a fixed-capacity lane; an observer runs solely during
 * an explicit bounded drain and never becomes business or product authority.
 */
export class BrowserGatewayMediaRegistrationOwner {
  readonly binding: MediaAuthorityBinding;
  readonly #sender: BoundedMediaSender;
  readonly #receiver: StrictMediaReceiver;
  readonly #onLifecycleFact: ((fact: MediaLeafLifecycleFact) => void) | undefined;
  readonly #lifecycleFactCapacity: number;
  readonly #lifecycleFacts: MediaLeafLifecycleFact[] = [];
  #closedState = false;
  #retainedClose: MediaRegistrationOwnerCloseResult | null = null;
  #droppedLifecycleFactCount = 0;
  #auditFailureCount = 0;

  constructor(
    binding: MediaAuthorityBinding,
    maxPendingFrames: number,
    maxPendingBytes: number,
    onAudioFrame: (frame: MediaAudioFrame) => void,
    onLifecycleFact?: (fact: MediaLeafLifecycleFact) => void,
    lifecycleFactCapacity = 32,
    constructionToken?: symbol,
  ) {
    if (constructionToken !== REGISTRATION_OWNER_CONSTRUCTION_TOKEN) {
      throw new MediaTransportViolation(
        'MEDIA_ACTIVATION_FACTORY_REQUIRED',
        'registration owners must be created by the activation factory',
      );
    }
    if (typeof onAudioFrame !== 'function') {
      throw new MediaTransportViolation('MEDIA_INVALID_CONSUMER', 'audio consumer must be callable');
    }
    if (onLifecycleFact !== undefined && typeof onLifecycleFact !== 'function') {
      throw new MediaTransportViolation('MEDIA_INVALID_AUDIT_CALLBACK', 'lifecycle fact consumer must be callable');
    }
    if (
      !Number.isInteger(lifecycleFactCapacity)
      || lifecycleFactCapacity <= 0
      || lifecycleFactCapacity > MAX_LIFECYCLE_FACT_CAPACITY
    ) {
      throw new MediaTransportViolation(
        'MEDIA_INVALID_AUDIT_CAPACITY',
        `lifecycle fact capacity must be an integer in [1, ${MAX_LIFECYCLE_FACT_CAPACITY}]`,
      );
    }
    this.binding = freezeBinding(binding);
    this.#sender = new BoundedMediaSender(this.binding, maxPendingFrames, maxPendingBytes);
    this.#receiver = new StrictMediaReceiver(this.binding, onAudioFrame);
    this.#onLifecycleFact = onLifecycleFact;
    this.#lifecycleFactCapacity = lifecycleFactCapacity;
    this.#record('activation.ready');
  }

  get closed(): boolean { return this.#closedState; }
  get audit_delivery_failures(): number { return this.#auditFailureCount; }
  get pending_lifecycle_facts(): number { return this.#lifecycleFacts.length; }
  get dropped_lifecycle_facts(): number { return this.#droppedLifecycleFactCount; }
  get consumer_failure_reason_id(): string | null { return this.#receiver.consumer_failure_reason_id; }

  enqueue(frame: MediaAudioFrame): MediaEnqueueResult {
    if (this.#closedState) {
      return {
        accepted: false,
        reason_id: this.#retainedClose?.reason_id ?? 'MEDIA_LEASE_CLOSED',
      };
    }
    const result = this.#sender.enqueue(frame);
    this.#record('sender.enqueue');
    if (this.#sender.closed) this.close(coerceDetachReason(result.reason_id));
    return result;
  }

  drain(
    trySendBinary: (binary: Uint8Array) => BinarySendDisposition,
    onFrameSent?: (seq: number) => void
  ): MediaDrainResult {
    if (this.#closedState) {
      return {
        sent_frames: 0,
        pending_frames: this.#sender.pending_frames,
        pending_bytes: this.#sender.pending_bytes,
        reason_id: this.#retainedClose?.reason_id ?? 'MEDIA_LEASE_CLOSED',
      };
    }
    const result = this.#sender.drain(trySendBinary, onFrameSent);
    if (this.#closedState) {
      return {
        sent_frames: 0,
        pending_frames: this.#sender.pending_frames,
        pending_bytes: this.#sender.pending_bytes,
        reason_id: this.#retainedClose?.reason_id ?? result.reason_id,
      };
    }
    this.#record('sender.drain');
    if (this.#sender.closed) this.close(coerceDetachReason(result.reason_id));
    return result;
  }

  acknowledge(control: MediaAck): MediaDetach | null {
    if (this.#closedState) return this.#retainedClose?.sender_detach ?? this.#sender.close().detach;
    const result = this.#sender.acknowledge(control);
    this.#record('sender.acknowledge');
    if (result !== null) this.close(result.reason_id);
    return result;
  }

  attach(control: MediaAttach): MediaDetach | null {
    if (this.#closedState) return this.#retainedClose?.receiver_detach ?? this.#receiver.close().detach;
    const result = this.#receiver.attach(control);
    this.#record('receiver.attach');
    if (result !== null) this.close(result.reason_id);
    return result;
  }

  acceptBinary(raw: Uint8Array): MediaAck | MediaDetach {
    if (this.#closedState) return this.#retainedClose?.receiver_detach ?? this.#receiver.close().detach!;
    const result = this.#receiver.acceptBinary(raw);
    if (this.#closedState) return this.#retainedClose?.receiver_detach ?? result;
    this.#record('receiver.accept_binary');
    if (result.type === 'media.detach') this.close(result.reason_id);
    return result;
  }

  acceptDetach(control: MediaDetach): MediaRegistrationOwnerCloseResult {
    if (this.#retainedClose !== null) return this.#retainedClose;
    const result = this.#receiver.acceptDetach(control);
    this.#record('receiver.accept_detach');
    return this.close(result.reason_id);
  }

  lifecycleSnapshot(): MediaLeafLifecycleFact {
    return this.#fact('lifecycle.snapshot');
  }

  drainLifecycleFacts(limit: number): number {
    if (!Number.isInteger(limit) || limit <= 0) {
      throw new MediaTransportViolation(
        'MEDIA_INVALID_AUDIT_DRAIN_LIMIT',
        'lifecycle fact drain limit must be a positive integer',
      );
    }
    const callback = this.#onLifecycleFact;
    if (callback === undefined) return 0;
    let attempted = 0;
    while (attempted < limit && this.#lifecycleFacts.length > 0) {
      const fact = this.#lifecycleFacts.shift()!;
      try {
        callback(fact);
      } catch {
        this.#auditFailureCount += 1;
      }
      attempted += 1;
    }
    return attempted;
  }

  close(reasonId: MediaDetachReason = 'MEDIA_LOCAL_CLOSE'): MediaRegistrationOwnerCloseResult {
    if (this.#retainedClose !== null) return this.#retainedClose;
    const canonicalReason = coerceDetachReason(reasonId);
    this.#closedState = true;
    const sender = this.#sender.close(canonicalReason);
    const receiver = this.#receiver.close(canonicalReason);
    this.#retainedClose = Object.freeze({
      was_active: sender.was_active || receiver.was_active,
      reason_id: canonicalReason,
      dropped_frames: sender.dropped_frames + receiver.dropped_frames,
      dropped_bytes: sender.dropped_bytes + receiver.dropped_bytes,
      sender_detach: sender.detach,
      receiver_detach: receiver.detach,
      business_cancel_count_delta: 0,
    });
    this.#record('activation.closed');
    return this.#retainedClose;
  }

  #fact(
    event: MediaLeafLifecycleEvent,
    pendingLifecycleFacts = this.#lifecycleFacts.length,
  ): MediaLeafLifecycleFact {
    const playout = this.binding.playout;
    return Object.freeze({
      event,
      lease_id: this.binding.lease_id,
      authority_evidence_id: this.binding.authority_evidence_id,
      connection_id: this.binding.connection_id,
      connection_epoch: this.binding.connection_epoch,
      session_id: this.binding.session_id,
      media_session_id: this.binding.media_session_id,
      interaction_id: this.binding.interaction_id,
      track_id: this.binding.track_id,
      correlation_id: this.binding.correlation_id,
      direction: this.binding.direction,
      generation_kind: this.binding.generation.kind,
      generation_id: this.binding.generation.id,
      generation_value: this.binding.generation.value,
      response_id: playout?.response_id ?? null,
      response_generation: playout?.response_generation ?? null,
      unit_id: playout?.unit_id ?? null,
      owner_closed: this.#closedState,
      sender_closed: this.#sender.closed,
      receiver_attached: this.#receiver.attached,
      receiver_closed: this.#receiver.closed,
      receiver_next_seq: this.#receiver.next_seq,
      receiver_next_cursor: this.#receiver.next_cursor,
      receiver_last_ack: this.#receiver.last_ack,
      sender_pending_frames: this.#sender.pending_frames,
      sender_pending_bytes: this.#sender.pending_bytes,
      pending_lifecycle_facts: pendingLifecycleFacts,
      dropped_lifecycle_facts: this.#droppedLifecycleFactCount,
      audit_delivery_failures: this.#auditFailureCount,
      evidence_scope: 'browser_gateway_media_registration_leaf_only',
      fact_contains_raw_payload: false,
      registered_route_observed: false,
      formal_route_ready: false,
      route_to_disk_zero_persistence_observed: false,
      business_cancel_count_delta: 0,
    });
  }

  #record(event: MediaLeafLifecycleEvent): void {
    if (this.#lifecycleFacts.length >= this.#lifecycleFactCapacity) {
      this.#droppedLifecycleFactCount += 1;
      return;
    }
    this.#lifecycleFacts.push(this.#fact(event, this.#lifecycleFacts.length + 1));
  }
}

function bindingsEqual(left: MediaAuthorityBinding, right: MediaAuthorityBinding): boolean {
  return left.lease_id === right.lease_id
    && left.authority_evidence_id === right.authority_evidence_id
    && left.connection_id === right.connection_id
    && left.connection_epoch === right.connection_epoch
    && left.session_id === right.session_id
    && left.media_session_id === right.media_session_id
    && left.interaction_id === right.interaction_id
    && left.track_id === right.track_id
    && left.correlation_id === right.correlation_id
    && left.direction === right.direction
    && left.generation.kind === right.generation.kind
    && left.generation.id === right.generation.id
    && left.generation.value === right.generation.value
    && left.frame_format.sample_rate_hz === right.frame_format.sample_rate_hz
    && left.frame_format.samples_per_channel === right.frame_format.samples_per_channel
    && left.frame_format.encoding === right.frame_format.encoding
    && left.frame_format.byte_order === right.frame_format.byte_order
    && left.frame_format.channel_count === right.frame_format.channel_count
    && left.frame_format.frame_duration_ms === right.frame_format.frame_duration_ms
    && (left.playout === null) === (right.playout === null)
    && (left.playout === null || right.playout === null || (
      left.playout.response_id === right.playout.response_id
      && left.playout.response_generation === right.playout.response_generation
      && left.playout.unit_id === right.playout.unit_id
    ));
}

export function createPlaybackStopReceipt(
  binding: MediaAuthorityBinding,
  outcome: MediaPlaybackStopOutcome,
  confirmedThroughSeq: number | null = null,
): MediaPlaybackStopReceipt {
  if (binding.direction !== 'downlink' || binding.playout === null) {
    throw new MediaTransportViolation('MEDIA_STOP_BINDING_MISMATCH', 'playback stop requires downlink authority');
  }
  requirePlaybackStopOutcome(outcome);
  if (confirmedThroughSeq !== null) {
    requireSafeUint('confirmed_through_seq', confirmedThroughSeq, 'MEDIA_INVALID_FRAME');
  }
  const receipt: MediaPlaybackStopReceipt = Object.freeze({
    type: 'media.playback_stop_receipt',
    lease_id: binding.lease_id,
    response_id: binding.playout.response_id,
    response_generation: binding.playout.response_generation,
    unit_id: binding.playout.unit_id,
    outcome,
    confirmed_through_seq: confirmedThroughSeq,
    business_cancel_count_delta: 0,
  });
  return validatePlaybackStopReceipt(binding, receipt);
}

export function validatePlaybackStopReceipt(
  binding: MediaAuthorityBinding,
  control: MediaPlaybackStopReceipt,
): MediaPlaybackStopReceipt {
  validateBinding(binding);
  if (binding.direction !== 'downlink' || binding.playout === null) {
    throw new MediaTransportViolation('MEDIA_STOP_BINDING_MISMATCH', 'playback stop requires downlink authority');
  }
  if (
    control.lease_id !== binding.lease_id
    || control.response_id !== binding.playout.response_id
    || control.response_generation !== binding.playout.response_generation
    || control.unit_id !== binding.playout.unit_id
  ) {
    throw new MediaTransportViolation('MEDIA_STOP_BINDING_MISMATCH', 'playback stop tuple does not match');
  }
  requirePlaybackStopOutcome(control.outcome);
  if (control.confirmed_through_seq !== null) {
    requireSafeUint('confirmed_through_seq', control.confirmed_through_seq, 'MEDIA_INVALID_CONTROL');
  }
  if (control.business_cancel_count_delta !== 0) {
    throw new MediaTransportViolation(
      'MEDIA_CANCEL_SCOPE_VIOLATION',
      'playback stop cannot cancel business scope',
    );
  }
  return control;
}
