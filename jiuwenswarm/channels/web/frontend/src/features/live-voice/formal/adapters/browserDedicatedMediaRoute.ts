/** Real WebSocket leaf for the closed Browser <-> Gateway Media contract. */

import { createCapturedAudioFrame, type CapturedAudioFrame } from '../audioPort.js';
import type { BrowserAudioLocalStopReceipt } from './browserAudioIOAdapter.js';
import {
  createBrowserGatewayMediaActivation,
  createPlaybackStopReceipt,
  deserializeMediaControl,
  MediaTransportViolation,
  serializeMediaControl,
  type ActiveMediaActivation,
  type MediaAuthorityBinding,
  type MediaAck,
  type MediaControl,
  type MediaDetach,
  type MediaDetachReason,
  type MediaEndOfTurn,
  type MediaSpeechStart,
  type MediaEnqueueResult,
  type MediaAudioFrame,
  type MediaPlaybackStopReceipt,
  type MediaRegistrationOwnerCloseResult,
} from './browserGatewayMediaTransport.js';

export { decodeAudioFrame, deserializeMediaControl, encodeAudioFrame, serializeMediaControl } from './browserGatewayMediaTransport.js';

export const DEDICATED_MEDIA_SUBPROTOCOL = 'live-voice.media.v1' as const;
export const DEDICATED_MEDIA_ROUTE_PATH = '/ws/live-voice/media' as const;
export const DEDICATED_MEDIA_AUTH_CONTRACT_VERSION = 'live-voice.media-auth.v1' as const;
export const DEDICATED_MEDIA_ROUTE_EVIDENCE_SCOPE = 'browser_dedicated_media_socket_leaf_only' as const;

const SOCKET_CONNECTING = 0;
const SOCKET_OPEN = 1;
const SOCKET_CLOSING = 2;
const SOCKET_CLOSED = 3;
const DEFAULT_SOCKET_HIGH_WATER_BYTES = 256 * 1024;
const DEFAULT_DRAIN_RETRY_DELAY_MS = 25;
const DEFAULT_MAX_DRAIN_STALL_RETRIES = 120;
const MAX_PENDING_FRAMES = 256;
const MAX_PENDING_BYTES = 8 * 1024 * 1024;
const MAX_SOCKET_HIGH_WATER_BYTES = 8 * 1024 * 1024;
const MAX_DRAIN_RETRY_DELAY_MS = 1_000;
const MAX_DRAIN_STALL_RETRIES = 10_000;
const MAX_LOCAL_STOP_CURSOR_FACTS = 256;
const MAX_MEDIA_TICKET_CHARS = 128;
const MAX_MEDIA_AUTH_FRAME_BYTES = 8 * 1024;
const DEDICATED_MEDIA_LEAF_CONSTRUCTION_TOKEN = Symbol('dedicated-media-socket-leaf');
const BROWSER_AUDIO_LOCAL_STOP_OUTCOMES: ReadonlySet<string> = new Set([
  'local_fence_established',
  'local_fence_established_source_unknown',
  'target_mismatch',
  'no_active_target',
  'already_stopped',
  'local_fence_failed',
  'feature_disabled',
  'adapter_closed',
]);
const DETACH_REASONS: ReadonlySet<string> = new Set([
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
  'MEDIA_TRANSPORT_CLOSED',
  'MEDIA_TRANSPORT_PROTOCOL_ERROR',
  'MEDIA_TRANSPORT_SEND_FAILED',
]);

export interface DedicatedMediaSocketMessageEventLike {
  readonly data: unknown;
}

export interface DedicatedMediaSocketLike {
  readonly readyState: number;
  readonly bufferedAmount: number;
  readonly protocol: string;
  binaryType: string;
  onopen: ((event: unknown) => void) | null;
  onmessage: ((event: DedicatedMediaSocketMessageEventLike) => void) | null;
  onerror: ((event: unknown) => void) | null;
  onclose: ((event: unknown) => void) | null;
  send(data: string | ArrayBuffer | ArrayBufferView): void;
  close(code?: number, reason?: string): void;
}

interface PendingUplinkCompletion {
  readonly expected: MediaDetach;
  readonly promise: Promise<MediaRegistrationOwnerCloseResult>;
  readonly resolve: (value: MediaRegistrationOwnerCloseResult) => void;
  readonly reject: (reason: unknown) => void;
}

export type DedicatedMediaSocketFactory = (url: string, protocols: readonly string[]) => DedicatedMediaSocketLike;
export type DedicatedMediaDrainRetryScheduler = (callback: () => void, delayMs: number) => unknown;
export type DedicatedMediaDrainRetryCanceller = (handle: unknown) => void;

export type DedicatedMediaTerminalSource = 'local_close' | 'expected_completion' | 'peer_detach' | 'transport_close' | 'internal_failure';

export interface DedicatedMediaTerminalEvent {
  readonly reason_id: MediaDetachReason;
  readonly source: DedicatedMediaTerminalSource;
  readonly direction: MediaAuthorityBinding['direction'];
  readonly attached_before_close: boolean;
}

export interface BrowserDedicatedMediaRouteRequest {
  readonly enabled: boolean;
  readonly expected_origin: string;
  readonly endpoint_url: string;
  readonly media_ticket?: string;
  readonly binding: MediaAuthorityBinding | null;
  readonly provider_available: boolean;
  readonly transport_available: boolean;
  readonly socket_factory: DedicatedMediaSocketFactory;
  readonly on_audio_frame: (frame: MediaAudioFrame) => void;
  readonly on_uplink_frame_sent?: (seq: number) => void;
  readonly on_terminal?: (event: Readonly<DedicatedMediaTerminalEvent>) => void;
  readonly end_of_turn_capability?: 'media.end_of_turn.v1';
  readonly on_speech_start?: (event: Readonly<MediaSpeechStart>) => void;
  readonly on_end_of_turn?: (event: Readonly<MediaEndOfTurn>) => void;
  readonly max_pending_frames?: number;
  readonly max_pending_bytes?: number;
  readonly socket_high_water_bytes?: number;
  readonly drain_retry_delay_ms?: number;
  readonly max_drain_stall_retries?: number;
  readonly schedule_drain_retry?: DedicatedMediaDrainRetryScheduler;
  readonly cancel_drain_retry?: DedicatedMediaDrainRetryCanceller;
  /** Hold downlink ACKs until the corresponding browser audio chunk renders. */
  readonly defer_downlink_ack?: boolean;
}

export interface DedicatedMediaRouteCapability {
  readonly evidence_scope: typeof DEDICATED_MEDIA_ROUTE_EVIDENCE_SCOPE;
  readonly binary_websocket_leaf: true;
  readonly same_origin_required: true;
  readonly server_authored_attach_required: true;
  readonly socket_allocated: boolean;
  readonly registered_route_observed: false;
  readonly route_to_disk_zero_persistence_observed: false;
  readonly formal_route_ready: false;
}

export interface InactiveBrowserDedicatedMediaRoute {
  readonly active: false;
  readonly reason_id:
    | 'MEDIA_FEATURE_DISABLED'
    | 'MEDIA_AUTHORITY_UNAVAILABLE'
    | 'MEDIA_PROVIDER_UNAVAILABLE'
    | 'MEDIA_TRANSPORT_UNAVAILABLE'
    | 'MEDIA_ORIGIN_REJECTED';
  readonly capability: DedicatedMediaRouteCapability;
}

export interface ActiveBrowserDedicatedMediaRoute {
  readonly active: true;
  readonly binding: MediaAuthorityBinding;
  readonly leaf: BrowserDedicatedMediaSocketLeaf;
  readonly capability: DedicatedMediaRouteCapability;
}

export type BrowserDedicatedMediaRouteActivation = InactiveBrowserDedicatedMediaRoute | ActiveBrowserDedicatedMediaRoute;

function capability(socketAllocated: boolean): DedicatedMediaRouteCapability {
  return Object.freeze({
    evidence_scope: DEDICATED_MEDIA_ROUTE_EVIDENCE_SCOPE,
    binary_websocket_leaf: true,
    same_origin_required: true,
    server_authored_attach_required: true,
    socket_allocated: socketAllocated,
    registered_route_observed: false,
    route_to_disk_zero_persistence_observed: false,
    formal_route_ready: false,
  });
}

function canonicalOrigin(value: unknown): URL | null {
  if (typeof value !== 'string' || value.length === 0 || value !== value.trim()) return null;
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    return null;
  }
  if (
    !['http:', 'https:'].includes(parsed.protocol) ||
    parsed.username !== '' ||
    parsed.password !== '' ||
    parsed.pathname !== '/' ||
    parsed.search !== '' ||
    parsed.hash !== ''
  )
    return null;
  return parsed;
}

function dedicatedEndpoint(expectedOrigin: unknown, endpointUrl: unknown): string | null {
  const origin = canonicalOrigin(expectedOrigin);
  if (origin === null || typeof endpointUrl !== 'string' || endpointUrl !== endpointUrl.trim()) return null;
  let endpoint: URL;
  try {
    endpoint = new URL(endpointUrl);
  } catch {
    return null;
  }
  const requiredProtocol = origin.protocol === 'https:' ? 'wss:' : 'ws:';
  if (
    endpoint.protocol !== requiredProtocol ||
    endpoint.host !== origin.host ||
    endpoint.username !== '' ||
    endpoint.password !== '' ||
    endpoint.search !== '' ||
    endpoint.hash !== '' ||
    endpoint.pathname !== DEDICATED_MEDIA_ROUTE_PATH
  )
    return null;
  return endpoint.href;
}

function validMediaTicket(value: unknown): value is string {
  return (
    typeof value === 'string'
    && value.length >= 32
    && value.length <= MAX_MEDIA_TICKET_CHARS
    && /^[A-Za-z0-9_-]+$/.test(value)
  );
}

function mediaAuthFrame(ticket: string, binding: MediaAuthorityBinding): string {
  const attach = JSON.parse(serializeMediaControl({ type: 'media.attach', binding })) as { binding?: unknown };
  const frame = JSON.stringify({
    type: 'media.auth',
    contract_version: DEDICATED_MEDIA_AUTH_CONTRACT_VERSION,
    media_ticket: ticket,
    binding: attach.binding,
  });
  if (new TextEncoder().encode(frame).byteLength > MAX_MEDIA_AUTH_FRAME_BYTES) {
    throw new TypeError('dedicated media authentication frame exceeds its bound');
  }
  return frame;
}

function closeReasonFrom(error: unknown): MediaDetachReason {
  if (typeof error === 'object' && error !== null && 'reasonId' in error && typeof (error as { reasonId?: unknown }).reasonId === 'string') {
    const reason = (error as { reasonId: string }).reasonId;
    if (DETACH_REASONS.has(reason)) {
      return reason as MediaDetachReason;
    }
  }
  return 'MEDIA_TRANSPORT_PROTOCOL_ERROR';
}

function binaryFromMessage(value: unknown): Uint8Array | null {
  if (value instanceof ArrayBuffer) return new Uint8Array(value);
  if (ArrayBuffer.isView(value)) {
    return new Uint8Array(value.buffer, value.byteOffset, value.byteLength).slice();
  }
  return null;
}

function boundedPositiveInteger(value: unknown, maximum: number, field: string): number {
  if (!Number.isSafeInteger(value) || (value as number) <= 0 || (value as number) > maximum) {
    throw new TypeError(`${field} must be a positive safe integer no greater than ${maximum}`);
  }
  return value as number;
}

const scheduleDefaultDrainRetry: DedicatedMediaDrainRetryScheduler = (callback, delayMs) => globalThis.setTimeout(callback, delayMs);
const cancelDefaultDrainRetry: DedicatedMediaDrainRetryCanceller = handle => globalThis.clearTimeout(handle as number);

interface ScheduledDrainRetry {
  readonly generation: number;
  scheduling: boolean;
  fired: boolean;
  handle: unknown;
}

function hasExactFrozenDataFields(value: unknown, fields: readonly string[]): value is Readonly<Record<string, unknown>> {
  if (typeof value !== 'object' || value === null || Array.isArray(value) || !Object.isFrozen(value)) return false;
  const ownKeys = Reflect.ownKeys(value);
  if (ownKeys.length !== fields.length || ownKeys.some(key => typeof key !== 'string' || !fields.includes(key))) return false;
  return fields.every(field => {
    const descriptor = Object.getOwnPropertyDescriptor(value, field);
    return descriptor !== undefined && descriptor.enumerable === true && 'value' in descriptor;
  });
}

function isNonNegativeSafeInteger(value: unknown): value is number {
  return Number.isSafeInteger(value) && (value as number) >= 0;
}

function isMonotonicFact(value: unknown): value is number | null {
  return value === null || (typeof value === 'number' && Number.isFinite(value) && value >= 0);
}

function validateSourceActionConfirmation(value: unknown, sourceCount: number): value is BrowserAudioLocalStopReceipt['browser_sources']['stop_request'] {
  if (!hasExactFrozenDataFields(value, ['status', 'attempted_count', 'completed_count', 'failed_count'])) return false;
  const { status, attempted_count: attempted, completed_count: completed, failed_count: failed } = value;
  if (!isNonNegativeSafeInteger(attempted) || !isNonNegativeSafeInteger(completed) || !isNonNegativeSafeInteger(failed) || attempted !== completed + failed)
    return false;
  if (status === 'not_attempted') return sourceCount === 0 && attempted === 0;
  if (status === 'not_applicable') return sourceCount === 0 && attempted === 0;
  if (status === 'completed') {
    return sourceCount > 0 && attempted === sourceCount && completed === sourceCount && failed === 0;
  }
  if (status === 'unknown') {
    return sourceCount > 0 && attempted === sourceCount && failed > 0;
  }
  return false;
}

function validateLocalStopTiming(value: unknown): value is BrowserAudioLocalStopReceipt['timing'] {
  if (!hasExactFrozenDataFields(value, ['status', 'requested_at_monotonic_ms', 'confirmed_at_monotonic_ms', 'duration_ms'])) return false;
  const requested = value.requested_at_monotonic_ms;
  const confirmed = value.confirmed_at_monotonic_ms;
  const duration = value.duration_ms;
  if (!isMonotonicFact(requested) || !isMonotonicFact(confirmed) || !isMonotonicFact(duration)) return false;
  const confirmable = requested !== null && confirmed !== null && confirmed >= requested;
  if (value.status === 'confirmed') {
    return confirmable && duration === confirmed - requested;
  }
  return value.status === 'unknown' && !confirmable && duration === null;
}

function validateBrowserAudioLocalStopReceipt(value: unknown): Readonly<BrowserAudioLocalStopReceipt> {
  if (
    !hasExactFrozenDataFields(value, [
      'kind',
      'outcome',
      'response',
      'reason',
      'local_fence_established',
      'confirmed_cursor_before_stop',
      'browser_sources',
      'timing',
      'physical_heard',
      'physical_silence',
      'business_cancel_count_before',
      'business_cancel_count_after',
      'business_cancel_count_delta',
    ])
  ) {
    throw new TypeError('local playback stop requires a closed BrowserAudio receipt');
  }
  if (value.kind !== 'browser_audio.local_stop.v1') {
    throw new TypeError('local playback stop requires the BrowserAudio receipt kind');
  }
  if (typeof value.outcome !== 'string' || !BROWSER_AUDIO_LOCAL_STOP_OUTCOMES.has(value.outcome)) {
    throw new TypeError('local playback stop receipt has an invalid outcome');
  }
  const localFenceEstablished = value.outcome === 'local_fence_established' || value.outcome === 'local_fence_established_source_unknown';
  if (value.local_fence_established !== localFenceEstablished) {
    throw new TypeError('local playback stop outcome contradicts the local fence');
  }
  if (
    !hasExactFrozenDataFields(value.response, ['interaction_id', 'response_id', 'response_generation']) ||
    typeof value.response.interaction_id !== 'string' ||
    value.response.interaction_id.trim().length === 0 ||
    typeof value.response.response_id !== 'string' ||
    value.response.response_id.trim().length === 0 ||
    !isNonNegativeSafeInteger(value.response.response_generation) ||
    typeof value.reason !== 'string' ||
    value.reason.trim().length === 0
  ) {
    throw new TypeError('local playback stop receipt has invalid identity facts');
  }
  if (
    !Array.isArray(value.confirmed_cursor_before_stop) ||
    !Object.isFrozen(value.confirmed_cursor_before_stop) ||
    value.confirmed_cursor_before_stop.length > MAX_LOCAL_STOP_CURSOR_FACTS
  ) {
    throw new TypeError('local playback stop receipt has invalid cursor facts');
  }
  const cursorUnits = new Set<string>();
  for (const cursor of value.confirmed_cursor_before_stop) {
    if (
      !hasExactFrozenDataFields(cursor, ['unit_id', 'contiguous_through_seq']) ||
      typeof cursor.unit_id !== 'string' ||
      cursor.unit_id.trim().length === 0 ||
      (cursor.contiguous_through_seq !== null && !isNonNegativeSafeInteger(cursor.contiguous_through_seq)) ||
      cursorUnits.has(cursor.unit_id)
    ) {
      throw new TypeError('local playback stop receipt has invalid cursor facts');
    }
    cursorUnits.add(cursor.unit_id);
  }
  if (!hasExactFrozenDataFields(value.browser_sources, ['source_count', 'stop_request', 'disconnect'])) {
    throw new TypeError('local playback stop receipt has invalid browser source facts');
  }
  const sourceCount = value.browser_sources.source_count;
  if (
    !isNonNegativeSafeInteger(sourceCount) ||
    !validateSourceActionConfirmation(value.browser_sources.stop_request, sourceCount) ||
    !validateSourceActionConfirmation(value.browser_sources.disconnect, sourceCount)
  ) {
    throw new TypeError('local playback stop receipt has invalid browser source facts');
  }
  const stopStatus = value.browser_sources.stop_request.status;
  const disconnectStatus = value.browser_sources.disconnect.status;
  if (localFenceEstablished) {
    if (sourceCount === 0) {
      if (stopStatus !== 'not_applicable' || disconnectStatus !== 'not_applicable') {
        throw new TypeError('local playback stop receipt lacks source cleanup confirmation');
      }
    } else if (stopStatus === 'not_attempted' || disconnectStatus === 'not_attempted') {
      throw new TypeError('local playback stop receipt lacks source cleanup confirmation');
    }
    const cleanupUnknown = stopStatus === 'unknown' || disconnectStatus === 'unknown';
    if (cleanupUnknown !== (value.outcome === 'local_fence_established_source_unknown')) {
      throw new TypeError('local playback stop outcome contradicts source cleanup truth');
    }
  } else if (sourceCount !== 0 || stopStatus !== 'not_attempted' || disconnectStatus !== 'not_attempted') {
    throw new TypeError('non-fenced local playback stop cannot claim source cleanup');
  }
  if (!validateLocalStopTiming(value.timing)) {
    throw new TypeError('local playback stop receipt has contradictory timing facts');
  }
  if (value.physical_heard !== 'unproven' || value.physical_silence !== 'unproven') {
    throw new TypeError('local playback stop receipt cannot claim physical truth');
  }
  const before = value.business_cancel_count_before;
  const after = value.business_cancel_count_after;
  const delta = value.business_cancel_count_delta;
  if (!isNonNegativeSafeInteger(before) || !isNonNegativeSafeInteger(after) || !Number.isSafeInteger(delta) || delta !== after - before || delta !== 0) {
    throw new TypeError('local playback stop cannot carry business cancellation');
  }
  if (!localFenceEstablished) {
    throw new TypeError('local playback stop requires an established local fence');
  }
  return value as unknown as Readonly<BrowserAudioLocalStopReceipt>;
}

/**
 * Create only the route leaf. Registration, trusted binding lookup, and product
 * readiness remain Integration-Owner composition responsibilities.
 */
export function createBrowserDedicatedMediaRoute(request: BrowserDedicatedMediaRouteRequest): BrowserDedicatedMediaRouteActivation {
  const inactive = (reason_id: InactiveBrowserDedicatedMediaRoute['reason_id']): InactiveBrowserDedicatedMediaRoute =>
    Object.freeze({
      active: false,
      reason_id,
      capability: capability(false),
    });

  // This ordering is intentional: feature-off reads no socket, authority,
  // origin, Provider, callback, queue, or transport field.
  if (request.enabled !== true) return inactive('MEDIA_FEATURE_DISABLED');
  if (request.binding === null || request.binding === undefined) {
    return inactive('MEDIA_AUTHORITY_UNAVAILABLE');
  }
  if (request.provider_available !== true) return inactive('MEDIA_PROVIDER_UNAVAILABLE');
  if (request.transport_available !== true) return inactive('MEDIA_TRANSPORT_UNAVAILABLE');
  const endpoint = dedicatedEndpoint(request.expected_origin, request.endpoint_url);
  if (endpoint === null) return inactive('MEDIA_ORIGIN_REJECTED');
  const ticket = request.media_ticket;
  if (!validMediaTicket(ticket)) {
    return inactive('MEDIA_AUTHORITY_UNAVAILABLE');
  }
  if (typeof request.socket_factory !== 'function') {
    return inactive('MEDIA_TRANSPORT_UNAVAILABLE');
  }
  if (request.on_terminal !== undefined && typeof request.on_terminal !== 'function') {
    throw new TypeError('on_terminal must be a function');
  }
  if (request.on_uplink_frame_sent !== undefined && typeof request.on_uplink_frame_sent !== 'function') {
    throw new TypeError('on_uplink_frame_sent must be a function');
  }
  if (
    (request.end_of_turn_capability === undefined) !== (request.on_speech_start === undefined) ||
    (request.end_of_turn_capability === undefined) !== (request.on_end_of_turn === undefined) ||
    (request.end_of_turn_capability !== undefined && request.end_of_turn_capability !== 'media.end_of_turn.v1') ||
    (request.on_speech_start !== undefined && typeof request.on_speech_start !== 'function') ||
    (request.on_end_of_turn !== undefined && typeof request.on_end_of_turn !== 'function')
  ) {
    throw new TypeError('speech boundaries require one exact negotiated capability and both consumers');
  }
  const maxPendingFrames = boundedPositiveInteger(request.max_pending_frames ?? 8, MAX_PENDING_FRAMES, 'max_pending_frames');
  const maxPendingBytes = boundedPositiveInteger(request.max_pending_bytes ?? 131_072, MAX_PENDING_BYTES, 'max_pending_bytes');
  const highWaterBytes = boundedPositiveInteger(
    request.socket_high_water_bytes ?? DEFAULT_SOCKET_HIGH_WATER_BYTES,
    MAX_SOCKET_HIGH_WATER_BYTES,
    'socket_high_water_bytes'
  );
  const drainRetryDelayMs = boundedPositiveInteger(
    request.drain_retry_delay_ms ?? DEFAULT_DRAIN_RETRY_DELAY_MS,
    MAX_DRAIN_RETRY_DELAY_MS,
    'drain_retry_delay_ms'
  );
  const maxDrainStallRetries = boundedPositiveInteger(
    request.max_drain_stall_retries ?? DEFAULT_MAX_DRAIN_STALL_RETRIES,
    MAX_DRAIN_STALL_RETRIES,
    'max_drain_stall_retries'
  );
  const customDrainScheduler = request.schedule_drain_retry;
  const customDrainCanceller = request.cancel_drain_retry;
  if ((customDrainScheduler === undefined) !== (customDrainCanceller === undefined)) {
    throw new TypeError('custom drain retry scheduling requires both schedule and cancel functions');
  }
  if (customDrainScheduler !== undefined && typeof customDrainScheduler !== 'function') {
    throw new TypeError('schedule_drain_retry must be a function');
  }
  if (customDrainCanceller !== undefined && typeof customDrainCanceller !== 'function') {
    throw new TypeError('cancel_drain_retry must be a function');
  }
  if (request.defer_downlink_ack !== undefined && typeof request.defer_downlink_ack !== 'boolean') throw new TypeError('defer_downlink_ack must be boolean');

  const activation = createBrowserGatewayMediaActivation({
    enabled: true,
    binding: request.binding,
    provider_available: true,
    transport_available: true,
    on_audio_frame: request.on_audio_frame,
    max_pending_frames: maxPendingFrames,
    max_pending_bytes: maxPendingBytes,
  });
  if (!activation.active) {
    return inactive(activation.reason_id);
  }
  let socket: DedicatedMediaSocketLike | null = null;
  try {
    const authenticationFrame = mediaAuthFrame(ticket, activation.binding);
    socket = request.socket_factory(endpoint, Object.freeze([DEDICATED_MEDIA_SUBPROTOCOL]));
    if (socket.readyState !== SOCKET_CONNECTING) {
      throw new TypeError('dedicated media socket factory must return a new connecting socket');
    }
    const leaf = new BrowserDedicatedMediaSocketLeaf(
      activation,
      socket,
      maxPendingFrames,
      maxPendingBytes,
      highWaterBytes,
      drainRetryDelayMs,
      maxDrainStallRetries,
      customDrainScheduler ?? scheduleDefaultDrainRetry,
      customDrainCanceller ?? cancelDefaultDrainRetry,
      request.defer_downlink_ack === true,
      authenticationFrame,
      request.on_terminal,
      request.on_uplink_frame_sent,
      request.end_of_turn_capability,
      request.on_speech_start,
      request.on_end_of_turn,
      DEDICATED_MEDIA_LEAF_CONSTRUCTION_TOKEN
    );
    return Object.freeze({
      active: true,
      binding: activation.binding,
      leaf,
      capability: capability(true),
    });
  } catch (error: unknown) {
    activation.owner.close('MEDIA_TRANSPORT_CLOSED');
    if (socket !== null && ![SOCKET_CLOSING, SOCKET_CLOSED].includes(socket.readyState)) {
      try {
        socket.close(1000, 'live-voice media activation failed');
      } catch {
        /* retained local fence */
      }
    }
    throw error;
  }
}

export class BrowserDedicatedMediaSocketLeaf {
  readonly binding: MediaAuthorityBinding;
  readonly #activation: ActiveMediaActivation;
  readonly #socket: DedicatedMediaSocketLike;
  readonly #maxPendingFrames: number;
  readonly #maxPendingBytes: number;
  readonly #socketHighWaterBytes: number;
  readonly #drainRetryDelayMs: number;
  readonly #maxDrainStallRetries: number;
  readonly #scheduleDrainRetry: DedicatedMediaDrainRetryScheduler;
  readonly #cancelDrainRetry: DedicatedMediaDrainRetryCanceller;
  readonly #deferDownlinkAck: boolean;
  #pendingAuthenticationFrame: string | null;
  readonly #onTerminal?: (event: Readonly<DedicatedMediaTerminalEvent>) => void;
  readonly #onUplinkFrameSent?: (seq: number) => void;
  readonly #endOfTurnCapability?: 'media.end_of_turn.v1';
  readonly #onSpeechStart?: (event: Readonly<MediaSpeechStart>) => void;
  readonly #onEndOfTurn?: (event: Readonly<MediaEndOfTurn>) => void;
  readonly #pendingDownlinkAcks = new Map<number, Readonly<{ ack: Readonly<MediaAck>; byteLength: number }>>();
  #pendingDownlinkBytes = 0;
  #lastDeferredDownlinkAck = -1;
  #attached = false;
  #closed = false;
  #retainedClose: MediaRegistrationOwnerCloseResult | null = null;
  #pendingUplinkCompletion: PendingUplinkCompletion | null = null;
  #terminalNotified = false;
  #speechStartSeen = false;
  #speechStartProviderMs: number | null = null;
  #endOfTurnSeen = false;
  #scheduledDrainRetry: ScheduledDrainRetry | null = null;
  #drainRetryGeneration = 0;
  #drainStallRetries = 0;

  constructor(
    activation: ActiveMediaActivation,
    socket: DedicatedMediaSocketLike,
    maxPendingFrames: number,
    maxPendingBytes: number,
    socketHighWaterBytes: number,
    drainRetryDelayMs: number,
    maxDrainStallRetries: number,
    scheduleDrainRetry: DedicatedMediaDrainRetryScheduler,
    cancelDrainRetry: DedicatedMediaDrainRetryCanceller,
    deferDownlinkAck: boolean,
    authenticationFrame: string | null,
    onTerminal?: (event: Readonly<DedicatedMediaTerminalEvent>) => void,
    onUplinkFrameSent?: (seq: number) => void,
    endOfTurnCapability?: 'media.end_of_turn.v1',
    onSpeechStart?: (event: Readonly<MediaSpeechStart>) => void,
    onEndOfTurn?: (event: Readonly<MediaEndOfTurn>) => void,
    constructionToken?: symbol
  ) {
    if (constructionToken !== DEDICATED_MEDIA_LEAF_CONSTRUCTION_TOKEN) {
      throw new TypeError('dedicated media socket leaves require the same-origin factory');
    }
    this.#activation = activation;
    this.binding = activation.binding;
    this.#socket = socket;
    this.#maxPendingFrames = maxPendingFrames;
    this.#maxPendingBytes = maxPendingBytes;
    this.#socketHighWaterBytes = socketHighWaterBytes;
    this.#drainRetryDelayMs = drainRetryDelayMs;
    this.#maxDrainStallRetries = maxDrainStallRetries;
    this.#scheduleDrainRetry = scheduleDrainRetry;
    this.#cancelDrainRetry = cancelDrainRetry;
    this.#deferDownlinkAck = deferDownlinkAck;
    this.#pendingAuthenticationFrame = authenticationFrame;
    this.#onTerminal = onTerminal;
    this.#onUplinkFrameSent = onUplinkFrameSent;
    this.#endOfTurnCapability = endOfTurnCapability;
    this.#onSpeechStart = onSpeechStart;
    this.#onEndOfTurn = onEndOfTurn;
    socket.binaryType = 'arraybuffer';
    socket.onopen = () => {
      if (this.#closed) return;
      if (socket.protocol !== DEDICATED_MEDIA_SUBPROTOCOL) {
        this.#terminate('MEDIA_TRANSPORT_PROTOCOL_ERROR', false);
        return;
      }
      const authenticationFrame = this.#pendingAuthenticationFrame;
      if (authenticationFrame !== null) {
        this.#pendingAuthenticationFrame = null;
        try {
          socket.send(authenticationFrame);
        } catch {
          this.#terminate('MEDIA_TRANSPORT_SEND_FAILED', false);
        }
      }
    };
    socket.onmessage = event => {
      this.#acceptMessage(event.data);
    };
    socket.onerror = () => {
      this.#terminate('MEDIA_TRANSPORT_CLOSED', false, 'transport_close');
    };
    socket.onclose = () => {
      this.#terminate('MEDIA_TRANSPORT_CLOSED', false, 'transport_close');
    };
  }

  get attached(): boolean {
    return this.#attached;
  }
  get closed(): boolean {
    return this.#closed || this.#pendingUplinkCompletion !== null;
  }

  sendCaptureFrame(frame: Readonly<CapturedAudioFrame>): MediaEnqueueResult {
    if (this.closed) return { accepted: false, reason_id: this.#retainedClose?.reason_id ?? 'MEDIA_LEASE_CLOSED' };
    if (!this.#attached) return { accepted: false, reason_id: 'MEDIA_NOT_ATTACHED' };
    if (this.binding.direction !== 'uplink' || this.binding.generation.kind !== 'capture') {
      this.#terminate('MEDIA_BINDING_MISMATCH');
      return { accepted: false, reason_id: 'MEDIA_BINDING_MISMATCH' };
    }
    let normalized: Readonly<CapturedAudioFrame>;
    try {
      normalized = createCapturedAudioFrame(frame);
    } catch {
      this.#terminate('MEDIA_INVALID_FRAME');
      return { accepted: false, reason_id: 'MEDIA_INVALID_FRAME' };
    }
    if (
      normalized.capture.capture_id !== this.binding.generation.id ||
      normalized.capture.capture_generation !== this.binding.generation.value ||
      normalized.capture.track_id !== this.binding.track_id
    ) {
      const reason = normalized.capture.capture_generation !== this.binding.generation.value ? 'MEDIA_STALE_GENERATION' : 'MEDIA_BINDING_MISMATCH';
      this.#terminate(reason);
      return { accepted: false, reason_id: reason };
    }
    if (
      normalized.format.sample_rate_hz !== this.binding.frame_format.sample_rate_hz ||
      normalized.format.samples_per_channel !== this.binding.frame_format.samples_per_channel ||
      normalized.format.encoding !== this.binding.frame_format.encoding ||
      normalized.format.channel_count !== this.binding.frame_format.channel_count ||
      normalized.format.frame_duration_ms !== this.binding.frame_format.frame_duration_ms
    ) {
      this.#terminate('MEDIA_INVALID_FRAME');
      return { accepted: false, reason_id: 'MEDIA_INVALID_FRAME' };
    }
    const result = this.#activation.owner.enqueue({
      seq: normalized.seq,
      sample_cursor: normalized.sample_cursor,
      samples: normalized.samples,
    });
    if (!result.accepted && this.#activation.owner.closed) {
      this.#terminate(closeReasonFrom({ reasonId: result.reason_id }));
      return result;
    }
    if (result.accepted) this.flush();
    return result;
  }

  flush(): Readonly<{ sent_frames: number; pending_frames: number; pending_bytes: number; reason_id: string }> {
    return this.#drain(false);
  }

  #drain(fromRetry: boolean): Readonly<{ sent_frames: number; pending_frames: number; pending_bytes: number; reason_id: string }> {
    if (this.closed || !this.#attached) {
      this.#cancelScheduledDrainRetry();
      const snapshot = this.#activation.owner.lifecycleSnapshot();
      return {
        sent_frames: 0,
        pending_frames: snapshot.sender_pending_frames,
        pending_bytes: snapshot.sender_pending_bytes,
        reason_id: this.closed ? (this.#retainedClose?.reason_id ?? 'MEDIA_LEASE_CLOSED') : 'MEDIA_NOT_ATTACHED',
      };
    }
    const drained = this.#activation.owner.drain(
      binary => {
        if (this.#socket.readyState !== SOCKET_OPEN) {
          return this.#socket.readyState === SOCKET_CONNECTING ? 'backpressured' : 'closed';
        }
        if (this.#socket.bufferedAmount + binary.byteLength > this.#socketHighWaterBytes) {
          return 'backpressured';
        }
        this.#socket.send(binary);
        return 'sent';
      },
      seq => this.#onUplinkFrameSent?.(seq)
    );
    if (this.#activation.owner.closed) {
      const reasonId = closeReasonFrom({ reasonId: drained.reason_id });
      const source = ['MEDIA_TRANSPORT_CLOSED', 'MEDIA_TRANSPORT_SEND_FAILED'].includes(reasonId) ? 'transport_close' : 'internal_failure';
      this.#terminate(reasonId, true, source);
      return drained;
    }
    if (fromRetry) {
      if (drained.pending_frames === 0 || drained.sent_frames > 0 || drained.reason_id === 'MEDIA_AWAITING_ACK') this.#drainStallRetries = 0;
      else if (drained.reason_id === 'MEDIA_BACKPRESSURED') this.#drainStallRetries += 1;
    }
    if (this.#drainStallRetries >= this.#maxDrainStallRetries) {
      this.#terminate('MEDIA_TRANSPORT_SEND_FAILED', true, 'transport_close');
      return { ...drained, reason_id: 'MEDIA_TRANSPORT_SEND_FAILED' };
    }
    if (drained.pending_frames > 0 && (drained.reason_id === 'MEDIA_BACKPRESSURED' || (drained.reason_id === 'MEDIA_DRAINED' && drained.pending_frames > 0))) {
      this.#scheduleDrainProbe();
    } else {
      this.#cancelScheduledDrainRetry();
    }
    return drained;
  }

  #scheduleDrainProbe(): void {
    if (this.closed || this.#scheduledDrainRetry !== null) return;
    const scheduled: ScheduledDrainRetry = {
      generation: ++this.#drainRetryGeneration,
      scheduling: true,
      fired: false,
      handle: undefined,
    };
    this.#scheduledDrainRetry = scheduled;
    try {
      const handle = this.#scheduleDrainRetry(() => {
        scheduled.fired = true;
        if (scheduled.scheduling) {
          if (this.#scheduledDrainRetry === scheduled) {
            this.#scheduledDrainRetry = null;
            this.#terminate('MEDIA_TRANSPORT_SEND_FAILED', true, 'internal_failure');
          }
          return;
        }
        if (this.#scheduledDrainRetry !== scheduled || scheduled.generation !== this.#drainRetryGeneration) return;
        this.#scheduledDrainRetry = null;
        if (this.closed) return;
        try {
          this.#drain(true);
        } catch {
          this.#terminate('MEDIA_TRANSPORT_SEND_FAILED', true, 'internal_failure');
        }
      }, this.#drainRetryDelayMs);
      scheduled.handle = handle;
      scheduled.scheduling = false;
      if (handle === undefined || handle === null) {
        if (this.#scheduledDrainRetry === scheduled) this.#scheduledDrainRetry = null;
        this.#terminate('MEDIA_TRANSPORT_SEND_FAILED', true, 'internal_failure');
      }
    } catch {
      scheduled.scheduling = false;
      if (this.#scheduledDrainRetry === scheduled) this.#scheduledDrainRetry = null;
      this.#terminate('MEDIA_TRANSPORT_SEND_FAILED', true, 'internal_failure');
    }
  }

  #cancelScheduledDrainRetry(): void {
    const scheduled = this.#scheduledDrainRetry;
    if (scheduled === null) return;
    this.#scheduledDrainRetry = null;
    ++this.#drainRetryGeneration;
    if (scheduled.handle === undefined || scheduled.handle === null) return;
    try {
      this.#cancelDrainRetry(scheduled.handle);
    } catch {
      // The leaf generation fence keeps a late callback inert.
    }
  }

  sendLocalPlaybackStop(value: unknown): MediaPlaybackStopReceipt {
    const receipt = validateBrowserAudioLocalStopReceipt(value);
    const playout = this.binding.playout;
    if (
      this.binding.direction !== 'downlink' ||
      playout === null ||
      receipt.response.interaction_id !== this.binding.interaction_id ||
      receipt.response.response_id !== playout.response_id ||
      receipt.response.response_generation !== playout.response_generation
    ) {
      throw new TypeError('local playback stop does not match the media binding');
    }
    const cursor = receipt.confirmed_cursor_before_stop.find(item => item.unit_id === playout.unit_id);
    const confirmedThroughSeq = cursor?.contiguous_through_seq ?? null;
    const receivedThroughSeq = this.#activation.owner.lifecycleSnapshot().receiver_last_ack;
    if (confirmedThroughSeq !== null && (receivedThroughSeq === null || confirmedThroughSeq > receivedThroughSeq)) {
      throw new TypeError('local playback stop cannot confirm an unreceived media frame');
    }
    const control = createPlaybackStopReceipt(this.binding, receipt.outcome, confirmedThroughSeq);
    if (this.#closed) {
      throw new MediaTransportViolation('MEDIA_STOP_NOT_DELIVERED', 'local playback stop was not delivered because the media leaf is closed');
    }
    if (!this.#attached) {
      this.#terminate('MEDIA_LOCAL_CLOSE', true, 'local_close');
      throw new MediaTransportViolation('MEDIA_STOP_NOT_DELIVERED', 'local playback stop was not delivered before server attach');
    }
    if (this.#socket.readyState !== SOCKET_OPEN) {
      this.#terminate('MEDIA_TRANSPORT_CLOSED', false, 'transport_close');
      throw new MediaTransportViolation('MEDIA_STOP_NOT_DELIVERED', 'local playback stop was not delivered because the transport is unavailable');
    }
    try {
      this.#socket.send(serializeMediaControl(control));
    } catch {
      this.#terminate('MEDIA_TRANSPORT_SEND_FAILED', false, 'transport_close');
      throw new MediaTransportViolation('MEDIA_STOP_NOT_DELIVERED', 'local playback stop transport send failed');
    }
    if (!this.#closed) {
      this.#terminate('MEDIA_LOCAL_CLOSE', true, 'local_close');
    }
    return control;
  }

  close(reasonId: MediaDetachReason = 'MEDIA_LOCAL_CLOSE'): MediaRegistrationOwnerCloseResult {
    return this.#terminate(reasonId, true, 'local_close');
  }

  async completeUplink(reasonId: MediaDetachReason = 'MEDIA_LOCAL_CLOSE'): Promise<MediaRegistrationOwnerCloseResult> {
    if (this.binding.direction !== 'uplink') {
      throw new TypeError('authoritative detach completion is uplink-only');
    }
    if (this.#pendingUplinkCompletion !== null) {
      return this.#pendingUplinkCompletion.promise;
    }
    if (this.#closed || this.#retainedClose !== null) {
      throw new MediaTransportViolation('MEDIA_LEASE_CLOSED', 'authoritative detach completion requires an active media leaf');
    }
    if (!this.#attached || this.#socket.readyState !== SOCKET_OPEN) {
      this.#terminate('MEDIA_TRANSPORT_CLOSED', false, 'transport_close');
      throw new MediaTransportViolation('MEDIA_TRANSPORT_CLOSED', 'authoritative detach completion requires an attached transport');
    }
    this.#cancelScheduledDrainRetry();
    const closed = this.#activation.owner.close(reasonId);
    const expected = closed.sender_detach;
    if (expected === null) {
      this.#terminate('MEDIA_TRANSPORT_PROTOCOL_ERROR', false);
      throw new MediaTransportViolation('MEDIA_TRANSPORT_PROTOCOL_ERROR', 'uplink completion detach is unavailable');
    }
    this.#retainedClose = closed;
    this.#pendingDownlinkAcks.clear();
    this.#pendingDownlinkBytes = 0;
    let resolve!: (value: MediaRegistrationOwnerCloseResult) => void;
    let reject!: (reason: unknown) => void;
    const promise = new Promise<MediaRegistrationOwnerCloseResult>((accept, fail) => {
      resolve = accept;
      reject = fail;
    });
    this.#pendingUplinkCompletion = Object.freeze({ expected, promise, resolve, reject });
    try {
      this.#socket.send(serializeMediaControl(expected));
    } catch {
      this.#failPendingUplinkCompletion('MEDIA_TRANSPORT_SEND_FAILED', 'transport_close');
    }
    return promise;
  }

  acknowledgeDownlinkThrough(throughSeq: number): void {
    if (this.binding.direction !== 'downlink' || !this.#deferDownlinkAck || !Number.isSafeInteger(throughSeq) || throughSeq < 0)
      throw new TypeError('deferred downlink ACK is unavailable');
    if (this.closed || !this.#attached) {
      throw new MediaTransportViolation('MEDIA_LEASE_CLOSED', 'deferred downlink ACK requires an attached route');
    }
    const retained = this.#pendingDownlinkAcks.get(throughSeq);
    if (retained === undefined) {
      throw new MediaTransportViolation('MEDIA_ACK_UNSENT', 'deferred downlink ACK does not match a received frame');
    }
    if (throughSeq !== this.#lastDeferredDownlinkAck + 1) {
      throw new MediaTransportViolation('MEDIA_ACK_OUT_OF_ORDER', 'deferred downlink ACK must follow browser render order');
    }
    for (const seq of this.#pendingDownlinkAcks.keys()) {
      if (seq <= throughSeq) {
        this.#pendingDownlinkBytes -= this.#pendingDownlinkAcks.get(seq)!.byteLength;
        this.#pendingDownlinkAcks.delete(seq);
      }
    }
    this.#lastDeferredDownlinkAck = throughSeq;
    this.#sendControl(retained.ack);
  }

  #acceptMessage(value: unknown): void {
    if (this.#pendingUplinkCompletion !== null) {
      if (typeof value !== 'string') {
        this.#failPendingUplinkCompletion('MEDIA_TRANSPORT_PROTOCOL_ERROR');
        return;
      }
      let control: MediaControl;
      try {
        control = deserializeMediaControl(value);
      } catch {
        this.#failPendingUplinkCompletion('MEDIA_TRANSPORT_PROTOCOL_ERROR');
        return;
      }
      this.#acceptUplinkCompletion(control);
      return;
    }
    if (this.#closed) return;
    if (typeof value === 'string') {
      let control: MediaControl;
      try {
        control = deserializeMediaControl(value);
      } catch (error: unknown) {
        this.#terminate(closeReasonFrom(error));
        return;
      }
      this.#acceptControl(control);
      return;
    }
    const binary = binaryFromMessage(value);
    if (binary === null || this.binding.direction !== 'downlink' || !this.#attached) {
      this.#terminate(this.#attached ? 'MEDIA_TRANSPORT_PROTOCOL_ERROR' : 'MEDIA_NOT_ATTACHED');
      return;
    }
    if (
      this.#deferDownlinkAck &&
      (this.#pendingDownlinkAcks.size >= this.#maxPendingFrames || this.#pendingDownlinkBytes + binary.byteLength > this.#maxPendingBytes)
    ) {
      this.#terminate('MEDIA_TRANSPORT_PROTOCOL_ERROR');
      return;
    }
    const result = this.#activation.owner.acceptBinary(binary);
    if (result.type === 'media.ack' && this.#deferDownlinkAck) {
      this.#pendingDownlinkAcks.set(
        result.through_seq,
        Object.freeze({
          ack: result,
          byteLength: binary.byteLength,
        })
      );
      this.#pendingDownlinkBytes += binary.byteLength;
    } else {
      this.#sendControl(result);
    }
    if (result.type === 'media.detach') this.#terminate(result.reason_id, false);
  }

  #acceptControl(control: MediaControl): void {
    if (control.type === 'media.attach') {
      const detach = this.#activation.owner.attach(control);
      if (detach !== null) {
        this.#sendControl(detach);
        this.#terminate(detach.reason_id, false);
        return;
      }
      this.#attached = true;
      return;
    }
    if (!this.#attached) {
      this.#terminate('MEDIA_NOT_ATTACHED');
      return;
    }
    if (control.type === 'media.detach') {
      const attachedBeforeClose = this.#attached;
      this.#cancelScheduledDrainRetry();
      const closed = this.#activation.owner.acceptDetach(control);
      this.#retainedClose = closed;
      this.#closed = true;
      this.#attached = false;
      const expectedCompletion =
        this.binding.direction === 'downlink' &&
        this.#deferDownlinkAck &&
        control.reason_id === 'MEDIA_LOCAL_CLOSE' &&
        this.#lastDeferredDownlinkAck >= 0 &&
        control.through_seq === this.#lastDeferredDownlinkAck &&
        this.#pendingDownlinkAcks.size === 0;
      this.#notifyTerminal(closed.reason_id, expectedCompletion ? 'expected_completion' : 'peer_detach', attachedBeforeClose);
      this.#closeSocket();
      return;
    }
    if (control.type === 'media.speech_start') {
      this.#acceptSpeechStart(control);
      return;
    }
    if (control.type === 'media.end_of_turn') {
      this.#acceptEndOfTurn(control);
      return;
    }
    if (control.type === 'media.ack' && this.binding.direction === 'uplink') {
      const detach = this.#activation.owner.acknowledge(control);
      if (detach !== null) {
        this.#sendControl(detach);
        this.#terminate(detach.reason_id, false);
      } else {
        this.flush();
      }
      return;
    }
    this.#terminate('MEDIA_TRANSPORT_PROTOCOL_ERROR');
  }

  #sendControl(control: MediaControl): void {
    if (this.#socket.readyState !== SOCKET_OPEN) {
      this.#terminate('MEDIA_TRANSPORT_CLOSED', false, 'transport_close');
      return;
    }
    try {
      this.#socket.send(serializeMediaControl(control));
    } catch {
      this.#terminate('MEDIA_TRANSPORT_SEND_FAILED', false, 'transport_close');
    }
  }

  #acceptUplinkCompletion(control: MediaControl): void {
    const pending = this.#pendingUplinkCompletion;
    if (pending === null) return;
    const expected = pending.expected;
    if (control.type === 'media.speech_start') {
      this.#acceptSpeechStart(control);
      return;
    }
    if (control.type === 'media.end_of_turn') {
      this.#acceptEndOfTurn(control);
      return;
    }
    if (
      control.type !== 'media.detach' ||
      control.lease_id !== expected.lease_id ||
      control.generation !== expected.generation ||
      control.reason_id !== expected.reason_id ||
      control.through_seq !== expected.through_seq ||
      control.business_cancel_count_delta !== 0
    ) {
      this.#failPendingUplinkCompletion('MEDIA_TRANSPORT_PROTOCOL_ERROR');
      return;
    }
    const closed = this.#retainedClose;
    if (closed === null) {
      this.#failPendingUplinkCompletion('MEDIA_TRANSPORT_PROTOCOL_ERROR');
      return;
    }
    this.#pendingUplinkCompletion = null;
    const attachedBeforeClose = this.#attached;
    this.#closed = true;
    this.#attached = false;
    pending.resolve(closed);
    this.#notifyTerminal(closed.reason_id, 'expected_completion', attachedBeforeClose);
    this.#closeSocket();
  }

  #acceptSpeechStart(control: Readonly<MediaSpeechStart>): void {
    if (
      this.#endOfTurnCapability !== 'media.end_of_turn.v1' ||
      this.#onSpeechStart === undefined ||
      this.binding.direction !== 'uplink' ||
      control.capability_version !== this.#endOfTurnCapability ||
      control.lease_id !== this.binding.lease_id ||
      control.generation !== this.binding.generation.value ||
      this.#speechStartSeen ||
      this.#endOfTurnSeen
    ) {
      if (this.#pendingUplinkCompletion !== null) {
        this.#failPendingUplinkCompletion('MEDIA_TRANSPORT_PROTOCOL_ERROR');
      } else {
        this.#terminate('MEDIA_TRANSPORT_PROTOCOL_ERROR');
      }
      return;
    }
    this.#speechStartSeen = true;
    this.#speechStartProviderMs = control.provider_start_ms;
    try {
      this.#onSpeechStart(control);
    } catch {
      if (this.#pendingUplinkCompletion !== null) {
        this.#failPendingUplinkCompletion('MEDIA_CONSUMER_FAILED');
      } else {
        this.#terminate('MEDIA_CONSUMER_FAILED');
      }
    }
  }

  #acceptEndOfTurn(control: Readonly<MediaEndOfTurn>): void {
    if (
      this.#endOfTurnCapability !== 'media.end_of_turn.v1' ||
      this.#onEndOfTurn === undefined ||
      this.binding.direction !== 'uplink' ||
      control.capability_version !== this.#endOfTurnCapability ||
      control.lease_id !== this.binding.lease_id ||
      control.generation !== this.binding.generation.value ||
      !this.#speechStartSeen ||
      control.provider_start_ms !== this.#speechStartProviderMs ||
      this.#endOfTurnSeen
    ) {
      if (this.#pendingUplinkCompletion !== null) {
        this.#failPendingUplinkCompletion('MEDIA_TRANSPORT_PROTOCOL_ERROR');
      } else {
        this.#terminate('MEDIA_TRANSPORT_PROTOCOL_ERROR');
      }
      return;
    }
    this.#endOfTurnSeen = true;
    try {
      this.#onEndOfTurn(control);
    } catch {
      if (this.#pendingUplinkCompletion !== null) {
        this.#failPendingUplinkCompletion('MEDIA_CONSUMER_FAILED');
      } else {
        this.#terminate('MEDIA_CONSUMER_FAILED');
      }
    }
  }

  #failPendingUplinkCompletion(reasonId: MediaDetachReason, source: DedicatedMediaTerminalSource = 'internal_failure'): void {
    const pending = this.#pendingUplinkCompletion;
    if (pending === null) return;
    const attachedBeforeClose = this.#attached;
    this.#pendingUplinkCompletion = null;
    this.#closed = true;
    this.#attached = false;
    pending.reject(new MediaTransportViolation(reasonId, 'authoritative media completion receipt was not observed'));
    this.#notifyTerminal(reasonId, source, attachedBeforeClose);
    this.#closeSocket();
  }

  #terminate(reasonId: MediaDetachReason, sendDetach = true, source: DedicatedMediaTerminalSource = 'internal_failure'): MediaRegistrationOwnerCloseResult {
    this.#pendingAuthenticationFrame = null;
    if (this.#pendingUplinkCompletion !== null) {
      const retained = this.#retainedClose ?? this.#activation.owner.close(reasonId);
      this.#retainedClose = retained;
      this.#failPendingUplinkCompletion(reasonId, source);
      return retained;
    }
    if (this.#retainedClose !== null) return this.#retainedClose;
    this.#cancelScheduledDrainRetry();
    const attachedBeforeClose = this.#attached;
    const closed = this.#activation.owner.close(reasonId);
    this.#retainedClose = closed;
    this.#pendingDownlinkAcks.clear();
    this.#pendingDownlinkBytes = 0;
    this.#closed = true;
    this.#attached = false;
    if (sendDetach && this.#socket.readyState === SOCKET_OPEN) {
      const detach: MediaDetach | null = this.binding.direction === 'uplink' ? closed.sender_detach : closed.receiver_detach;
      if (detach !== null) {
        try {
          this.#socket.send(serializeMediaControl(detach));
        } catch {
          // The retained local fence is authoritative; no retry is attempted.
        }
      }
    }
    this.#notifyTerminal(closed.reason_id, source, attachedBeforeClose);
    this.#closeSocket();
    return closed;
  }

  #notifyTerminal(reasonId: MediaDetachReason, source: DedicatedMediaTerminalSource, attachedBeforeClose: boolean): void {
    if (this.#terminalNotified) return;
    this.#terminalNotified = true;
    try {
      this.#onTerminal?.(
        Object.freeze({
          reason_id: reasonId,
          source,
          direction: this.binding.direction,
          attached_before_close: attachedBeforeClose,
        })
      );
    } catch {
      // Terminal observers cannot change the already-established media fence.
    }
  }

  #closeSocket(): void {
    if (![SOCKET_CLOSING, SOCKET_CLOSED].includes(this.#socket.readyState)) {
      try {
        this.#socket.close(1000, 'live-voice media leaf closed');
      } catch {
        // Local close remains retained even when the transport cannot confirm.
      }
    }
  }
}
