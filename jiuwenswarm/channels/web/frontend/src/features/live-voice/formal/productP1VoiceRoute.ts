import { LIVE_VOICE_AUDIO_FRAME_DURATION_MS, createAudioRenderPlan, type AudioResponseRef, type CapturedAudioFrame } from './audioPort.js';
import {
  BrowserAudioIOAdapter,
  reportBrowserC019PlayoutDiagnostic,
  type BrowserAudioCaptureStreamFactory,
  type BrowserAudioEnvironment,
  type BrowserAudioPcmChunk,
  type BrowserAudioPlayoutEvent,
  type BrowserAudioPlayoutMetadata,
  type BrowserAudioPlayoutScheduledEvent,
} from './adapters/browserAudioIOAdapter.js';
import {
  createBrowserDedicatedMediaRoute,
  deserializeMediaControl,
  type ActiveBrowserDedicatedMediaRoute,
  type BrowserDedicatedMediaRouteActivation,
  type DedicatedMediaTerminalEvent,
  type DedicatedMediaSocketFactory,
  type MediaFirstFrameDiagnostic,
} from './adapters/browserDedicatedMediaRoute.js';
import {
  MEDIA_END_OF_TURN_CAPABILITY,
  type MediaAudioFrame,
  type MediaEndOfTurn,
  type MediaSpeechStart,
} from './adapters/browserGatewayMediaTransport.js';
import {
  GatewayBatchSpeechClient,
  isStreamingSpeechDegradationReason,
  normalizeStreamingXObs,
  type FormalBatchRecognitionResult,
  type FormalBatchSynthesisResult,
  type FormalStreamingRecognitionResult,
  type FormalSynthesisDownlink,
  type GatewaySpeechProvider,
} from './gatewayBatchSpeechClient.js';
import {
  browserL0Available,
  browserL0Enabled,
  recordBrowserL0Milestone,
  registerBrowserL0Response,
  type BrowserL0Binding,
} from './l0Measurement.js';

export const PRODUCT_P1_MEDIA_ACTIVATE_METHOD = 'live_voice.media.activate';
export const PRODUCT_P1_MEDIA_CLOSE_METHOD = 'live_voice.media.close';

// Temporary C019 diagnostic: every media authority revocation names its exact
// call site with a closed label so a physical run can attribute the revoke
// that aborted the interrupting capture (C019-SPOKEN-BARGE-CONTINUATION-01).
export type ProductP1MediaAuthorityRevokeCaller =
  | 'start_capture'
  | 'playout_completed_receipt'
  | 'degraded_concurrent_capture'
  | 'overlap_capture_rotation'
  | 'idle_capture_rotation'
  | 'release_resources_close'
  | 'release_resources_failed'
  | 'continuation_playout_barged'
  | 'continuation_recognition_requested'
  | 'continuation_response_replaced'
  | 'continuation_playout_completed'
  | 'continuation_cancelled'
  | 'continuation_completed';
export type ProductP1MediaAuthorityRole = 'current' | 'continuation' | 'retained' | 'foreign';
export const PRODUCT_P1_MEDIA_AUTHORITY_REVOKE_EVENT = 'browser_media_authority_revoke_requested';
export const PRODUCT_P1_MEDIA_PLAYOUT_RECEIPT_METHOD = 'live_voice.media.playout_receipt';

export const PRODUCT_P1_CAPTURE_MAX_DURATION_MS = 30_000;
export const PRODUCT_P1_CAPTURE_DURATION_EXCEEDED_REASON = 'AUDIO_CAPTURE_DURATION_EXCEEDED';
export const PRODUCT_P1_EMPTY_TRANSCRIPT_REASON = 'SPEECH_PROVIDER_EMPTY_TRANSCRIPT';
const MAX_CAPTURE_FRAMES = PRODUCT_P1_CAPTURE_MAX_DURATION_MS / LIVE_VOICE_AUDIO_FRAME_DURATION_MS;
// This local observation never commits speech or selects a business route. It
// only prevents a lease rotation from truncating a possibly spoken utterance.
const CAPTURE_SPEECH_ENERGY_FLOOR = 0.015;
// A local energy observation is a short-lived hint that an utterance might be
// in flight before the Provider confirms it. The hint decays after 1.5 seconds
// of consecutive sub-floor frames, so one TTS tail, echo or environmental
// sound cannot permanently block a silent lease rotation; only the current
// lease's provider speech-start is authoritative speech state.
const CAPTURE_LOCAL_ACTIVITY_DECAY_FRAMES = 1_500 / LIVE_VOICE_AUDIO_FRAME_DURATION_MS;
// Recent local activity defers the boundary rotation by at most this bounded
// grace; sustained energy that the Provider never confirms as speech rotates
// late instead of failing the lease.
const CAPTURE_ROTATION_GRACE_FRAMES = CAPTURE_LOCAL_ACTIVITY_DECAY_FRAMES;
// Defense-in-depth memory bound: every legal path rotates or fails the
// utterance budget before reaching it.
const CAPTURE_ABSOLUTE_MAX_FRAMES = MAX_CAPTURE_FRAMES * 2 + CAPTURE_ROTATION_GRACE_FRAMES;
export const PRODUCT_P1_PLAYOUT_QUEUE_CAPACITY = 256;
const STAGED_SUCCESSOR_RESERVE_CEILING_MS = 1_000;
const STAGED_SUCCESSOR_RESERVE_TARGET_MS = 500;
// Streaming TTS is independently bounded from the 30-second microphone
// capture. Reusing the capture frame limit here cut every answer at exactly
// 30 seconds even though the Provider stream and browser playout were healthy.
export const PRODUCT_P1_STREAMING_PLAYOUT_MAX_DURATION_MS = 180_000;
const MAX_STREAMING_PLAYOUT_FRAMES = PRODUCT_P1_STREAMING_PLAYOUT_MAX_DURATION_MS / LIVE_VOICE_AUDIO_FRAME_DURATION_MS;
const ROUTE_READY_TIMEOUT_MS = 3_000;
const ROUTE_DRAIN_TIMEOUT_MS = 3_000;
const ROUTE_COMPLETION_TIMEOUT_MS = 3_000;
const CAPTURE_FIRST_FRAME_TIMEOUT_MS = 1_000;
const L0_WEBAUDIO_START_CONFIRMATION_RETRIES = 20;

type ProductP1SuccessorCaptureReadiness = 'not_started' | 'pending' | 'ready' | 'degraded';

export type ProductP1VoiceStatus = 'idle' | 'starting' | 'capturing' | 'recognizing' | 'recognized' | 'playing' | 'cleanup_pending' | 'failed' | 'closed';

export interface ProductP1AudioDeviceSelection {
  readonly selection_generation: number;
  readonly input_device_id?: string;
  readonly output_device_id?: string;
}

export interface ProductP1Recognition {
  readonly text: string;
  readonly voice_commit_receipt: string;
}

type ProductP1Request = (
  method: string,
  params: Record<string, unknown>,
  options?: Readonly<{ timeoutMs?: number; signal?: AbortSignal }>,
) => Promise<unknown>;

interface PendingProductPlayout {
  readonly response: Readonly<AudioResponseRef>;
  readonly unitId: string;
  readonly unitSeq: number;
  readonly chunks: Readonly<BrowserAudioPcmChunk>[];
  readonly frameCount: number | null;
  readonly degradationReason: string | null;
  readonly downlinkRoute: ActiveBrowserDedicatedMediaRoute | null;
  readonly receiptAuthority: Readonly<ProductP1MediaCloseBinding>;
  readonly captureFramesAcked: number;
  readonly transportAcknowledgedThrough: number;
  nextChunkIndex: number;
  renderedChunks: number;
  peakDepth: number;
  filling: boolean;
  readonly expected: Map<string, number>;
  readonly observed: Map<string, number>;
  lastRenderedClock: Readonly<{
    unitId: string;
    throughSeq: number;
    observedAt: string;
    monotonicMs: number;
  }> | null;
  readonly resolve: () => void;
  readonly reject: (error: Error) => void;
}

export interface ProductP1MediaCloseBinding {
  readonly session_id: string;
  readonly subject_id: string;
  readonly correlation_id: string;
  readonly interaction_id: string;
  readonly activation_id: string;
  readonly activation_generation: number;
}

export interface ProductP1AgentTextInput {
  readonly response: Readonly<AudioResponseRef>;
  readonly unit_id: string;
  readonly unit_seq?: number;
  readonly text: string;
  readonly capture_during_playout?: boolean;
  readonly response_continuation?: boolean;
}

export interface PreparedProductSpeech {
  readonly response: Readonly<AudioResponseRef>;
  readonly unitId: string;
  readonly unitSeq: number;
  readonly provider: Readonly<GatewaySpeechProvider>;
  readonly chunks: readonly Readonly<BrowserAudioPcmChunk>[];
  readonly downlink: Readonly<FormalSynthesisDownlink> | null;
  readonly receiptAuthority: Readonly<ProductP1MediaCloseBinding>;
  readonly captureFramesAcked: number;
}

interface PreparedProductSpeechMetadata {
  readonly result: Readonly<FormalBatchSynthesisResult>;
  readonly operationGeneration: number;
  readonly responseContinuation: boolean;
  readonly continuationOverCapture: boolean;
  readonly captureDuringPlayout: boolean;
  readonly responseKey: string;
  readonly speech: GatewayBatchSpeechClient;
  readonly continuationAdmissionEpoch: number | null;
}

interface ActiveContinuationAdmission {
  readonly epoch: number;
  readonly response: Readonly<AudioResponseRef>;
  readonly responseKey: string;
  readonly unitId: string;
  readonly unitSeq: number;
  readonly speech: GatewayBatchSpeechClient;
  readonly signal: AbortSignal | null;
  readonly removeAbortListener: () => void;
}

interface DeferredContinuationAdmission extends ActiveContinuationAdmission {
  readonly resolve: () => void;
  readonly reject: (error: Error) => void;
}

interface StagedProductSuccessor {
  readonly prepared: Readonly<PreparedProductSpeech>;
  readonly metadata: Readonly<PreparedProductSpeechMetadata>;
  downlinkRoute: ActiveBrowserDedicatedMediaRoute | null;
  readonly chunks: Readonly<BrowserAudioPcmChunk>[];
  terminal: Readonly<DedicatedMediaTerminalEvent> | null;
  attached: boolean;
  promoted: boolean;
  reserveBytes: number;
  transportAcknowledgedThrough: number;
  pending: PendingProductPlayout | null;
  parked: boolean;
  transitionPromise: Promise<void> | null;
}

const MAX_DEFERRED_CONTINUATION_ADMISSIONS = 3;

function objectValue(value: unknown, field: string): Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error(`${field} must be an object`);
  }
  return value as Record<string, unknown>;
}

function exactObject(value: unknown, fields: readonly string[], field: string): Record<string, unknown> {
  const result = objectValue(value, field);
  const keys = Object.keys(result).sort();
  const expected = [...fields].sort();
  if (keys.length !== expected.length || keys.some((key, index) => key !== expected[index])) {
    throw new Error(`${field} fields are not closed`);
  }
  return result;
}

function exactMediaActivation(value: unknown): Record<string, unknown> {
  const record = objectValue(value, 'media_activation');
  const hasStreaming = Object.prototype.hasOwnProperty.call(record, 'streaming_recognition');
  const hasDegradation = Object.prototype.hasOwnProperty.call(record, 'streaming_degradation');
  const hasEndOfTurn = Object.prototype.hasOwnProperty.call(record, 'end_of_turn');
  if (hasStreaming !== hasDegradation) {
    throw new Error('media activation streaming fields are incomplete');
  }
  return exactObject(
    record,
    [
      'status',
      'reason_id',
      'subject_id',
      'endpoint_path',
      'media_ticket',
      'subprotocol',
      'ticket_ttl_ms',
      'binding',
      'privacy',
      ...(hasStreaming ? ['streaming_recognition', 'streaming_degradation'] : []),
      ...(hasEndOfTurn ? ['end_of_turn'] : []),
    ],
    'media_activation'
  );
}

function requiredText(value: unknown, field: string): string {
  if (typeof value !== 'string' || value.trim().length === 0 || value !== value.trim()) {
    throw new Error(`${field} is invalid`);
  }
  return value;
}

function requiredSpeakableText(value: unknown, field: string): string {
  if (typeof value !== 'string' || value.trim().length === 0) {
    throw new Error(`${field} is invalid`);
  }
  return value;
}

function l0ResponseKey(response: Readonly<AudioResponseRef>): string {
  return `${response.interaction_id}\u0000${response.response_id}\u0000${response.response_generation}`;
}

function consumePrivateText(record: Record<string, unknown>, key: string, field: string): string {
  const value = requiredText(record[key], field);
  if (!Reflect.deleteProperty(record, key) || Object.prototype.hasOwnProperty.call(record, key)) {
    throw new Error(`${field} could not be released from memory`);
  }
  return value;
}

function stableFailureReason(error: unknown): string {
  if (error !== null && typeof error === 'object') {
    for (const field of ['reason', 'reason_id', 'code'] as const) {
      const candidate = (error as Record<string, unknown>)[field];
      if (typeof candidate === 'string' && /^[A-Z][A-Z0-9_]{0,127}$/.test(candidate)) return candidate;
    }
  }
  return 'FORMAL_P1_ROUTE_FAILED';
}

function stableCaptureStopReason(reason: string): string {
  switch (reason) {
    case 'audio_context_not_running':
    case 'audio_context_lost_during_start':
      return 'AUDIO_CONTEXT_NOT_RUNNING';
    case 'track_ended':
    case 'track_ended_during_start':
      return 'AUDIO_TRACK_ENDED';
    case 'audio_input_unavailable':
      return 'AUDIO_INPUT_UNAVAILABLE';
    case 'audio_input_selection_lost':
      return 'AUDIO_INPUT_SELECTION_LOST';
    case 'audio_input_selection_unverified':
      return 'AUDIO_INPUT_SELECTION_UNVERIFIED';
    case 'audio_output_selection_lost':
      return 'AUDIO_OUTPUT_SELECTION_LOST';
    case 'audio_output_selection_unverified':
      return 'AUDIO_OUTPUT_SELECTION_UNVERIFIED';
    case 'microphone_permission_revoked':
      return 'MICROPHONE_PERMISSION_REVOKED';
    case 'page_hidden':
      return 'PAGE_HIDDEN';
    case 'audio_processor_error':
      return 'AUDIO_PROCESSOR_ERROR';
    case 'audio_frame_consumer_failed':
      return 'AUDIO_FRAME_CONSUMER_FAILED';
    case 'audio_input_gap_exceeded':
      return 'AUDIO_INPUT_GAP_EXCEEDED';
    case 'audio_render_frame_regressed':
      return 'AUDIO_RENDER_FRAME_REGRESSED';
    case 'audio_render_frame_not_advanced':
      return 'AUDIO_RENDER_FRAME_NOT_ADVANCED';
    case 'audio_worklet_gap':
      return 'AUDIO_WORKLET_GAP';
    case 'invalid_audio_worklet_configuration':
      return 'INVALID_AUDIO_WORKLET_CONFIGURATION';
    case 'invalid_audio_worklet_message':
      return 'INVALID_AUDIO_WORKLET_MESSAGE';
    case 'non_contiguous_audio_sequence':
      return 'NON_CONTIGUOUS_AUDIO_SEQUENCE';
    case 'audio_sample_rate_changed':
      return 'AUDIO_SAMPLE_RATE_CHANGED';
    default:
      return 'AUDIO_CAPTURE_STOPPED';
  }
}

function routeUnavailable(reason: unknown): Error & { readonly reason_id: string } {
  const reasonId = requiredText(reason, 'reason_id');
  return Object.assign(new Error('formal P1 route is unavailable'), {
    reason_id: reasonId,
  });
}

function waitTurn(): Promise<void> {
  // The media sender exposes an eight-frame ACK window. A 10 ms polling turn
  // can consume almost the entire three-second drain budget for the legal
  // 1,500-frame capture boundary under ordinary browser scheduling load.
  return new Promise(resolve => globalThis.setTimeout(resolve, 5));
}

function monotonicNowMs(): number {
  return typeof globalThis.performance?.now === 'function' ? globalThis.performance.now() : Date.now();
}

function l0ClockNow(): Readonly<{ observedAt: string; monotonicMs: number }> {
  return Object.freeze({
    observedAt: new Date().toISOString(),
    monotonicMs: monotonicNowMs(),
  });
}

async function awaitRouteCompletion<T>(operation: Promise<T>): Promise<T> {
  let timeoutHandle: ReturnType<typeof globalThis.setTimeout> | null = null;
  const timeout = new Promise<T>((_resolve, reject) => {
    timeoutHandle = globalThis.setTimeout(() => {
      reject(
        Object.assign(new Error('media route completion timed out'), {
          reason_id: 'MEDIA_ROUTE_COMPLETION_TIMEOUT',
        })
      );
    }, ROUTE_COMPLETION_TIMEOUT_MS);
  });
  try {
    return await Promise.race([operation, timeout]);
  } finally {
    if (timeoutHandle !== null) globalThis.clearTimeout(timeoutHandle);
  }
}

function mediaEndpoint(origin: string, endpointPath: string): string {
  const url = new URL(endpointPath, origin);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  return url.href;
}

function defaultSocketFactory(url: string, protocols: readonly string[]): ReturnType<DedicatedMediaSocketFactory> {
  return new WebSocket(url, [...protocols]) as unknown as ReturnType<DedicatedMediaSocketFactory>;
}

export interface ProductP1CaptureRotationDiagnostics {
  readonly mode: 'overlap' | 'idle';
  readonly trigger: 'silent_boundary' | 'local_activity_grace_elapsed';
  readonly at_frame_count: number;
  readonly local_activity_recency_frames: number;
  readonly completed: boolean;
}

export interface ProductP1CaptureProcessingDiagnostics {
  readonly echo_cancellation: boolean | null;
  readonly noise_suppression: boolean | null;
  readonly auto_gain_control: boolean | null;
  readonly track_sample_rate_hz: number | null;
  readonly track_channel_count: number | null;
  readonly device_id_present: boolean;
}

// Sanitized capture diagnostics: counters, phases and processing booleans
// only. No raw audio, transcript content, credentials or device identity.
export interface ProductP1CaptureDiagnostics {
  readonly status: ProductP1VoiceStatus;
  readonly operation_generation: number;
  readonly frame_count: number;
  readonly frames_acked: number;
  readonly local_activity_observed: boolean;
  readonly local_activity_recency_frames: number;
  readonly provider_speech_start_observed: boolean;
  readonly provider_end_of_turn_pending: boolean;
  readonly utterance_start_frame_index: number | null;
  readonly rotation_in_flight: boolean;
  readonly last_rotation: Readonly<ProductP1CaptureRotationDiagnostics> | null;
  readonly actual_processing: Readonly<ProductP1CaptureProcessingDiagnostics> | null;
  readonly successor_readiness: ProductP1SuccessorCaptureReadiness;
  readonly successor_readiness_reason: string | null;
  readonly successor_readiness_elapsed_ms: number | null;
}

export class ProductP1VoiceRouteOwner {
  readonly #enabled: boolean;
  readonly #request: ProductP1Request;
  readonly #origin: string;
  readonly #socketFactory: DedicatedMediaSocketFactory;
  readonly #onStatus?: (status: ProductP1VoiceStatus, reason: string | null) => void;
  readonly #onConcurrentCaptureStarted?: () => void;
  readonly #onBargeInSpeechStart?: (event: Readonly<MediaSpeechStart>) => void;
  readonly #onBargeInEndOfTurn?: (event: Readonly<MediaEndOfTurn>) => void;
  readonly #audio: BrowserAudioIOAdapter;
  #status: ProductP1VoiceStatus;
  #reason: string | null = null;
  #frames: Readonly<CapturedAudioFrame>[] = [];
  #captureSpeechObserved = false;
  #captureProviderSpeechStartObserved = false;
  #captureLocalActivityRecencyFrames = 0;
  #captureUtteranceStartFrameIndex: number | null = null;
  #lastCaptureRotation: Readonly<ProductP1CaptureRotationDiagnostics> | null = null;
  #captureActualProcessing: Readonly<ProductP1CaptureProcessingDiagnostics> | null = null;
  #mediaSentFrames = 0;
  #captureFirstFrameAcknowledged = false;
  #captureFirstFrameDiagnostic: Readonly<MediaFirstFrameDiagnostic> | null = null;
  #captureFramesAcked = 0;
  #route: ActiveBrowserDedicatedMediaRoute | null = null;
  #speech: GatewayBatchSpeechClient | null = null;
  #sessionId: string | null = null;
  #interactionId: string | null = null;
  #correlationId: string | null = null;
  #locale: 'zh-CN' | 'en-US' = 'zh-CN';
  #activationId: string | null = null;
  #activationGeneration = 0;
  #deviceSelection: Readonly<ProductP1AudioDeviceSelection> = Object.freeze({ selection_generation: 1 });
  #playout: Readonly<BrowserAudioPlayoutMetadata> | null = null;
  #closed = false;
  #closeRequested = false;
  #operationGeneration = 0;
  #mediaCloseBinding: Readonly<ProductP1MediaCloseBinding> | null = null;
  readonly #retainedMediaAuthorities = new Map<string, Readonly<ProductP1MediaCloseBinding>>();
  #closePromise: Promise<void> | null = null;
  #failureCleanupPromise: Promise<void> | null = null;
  #failureCleanupReason: string | null = null;
  #pendingPlayout: PendingProductPlayout | null = null;
  #settlingPlayout: PendingProductPlayout | null = null;
  #continuationResponseKey: string | null = null;
  #continuationSpeech: GatewayBatchSpeechClient | null = null;
  #continuationReceiptAuthority: Readonly<ProductP1MediaCloseBinding> | null = null;
  #continuationCaptureFramesAcked = 0;
  readonly #preparedSpeech = new Map<
    Readonly<PreparedProductSpeech>,
    Readonly<PreparedProductSpeechMetadata>
  >();
  #stagedSuccessor: StagedProductSuccessor | null = null;
  #preparingSpeechCount = 0;
  #captureStartupAudioReady = false;
  #captureStartupFailure: (Error & { readonly reason: string }) | null = null;
  #mediaTerminalFailure: (Error & { readonly reason: string }) | null = null;
  #captureReadinessPending = false;
  #captureReadinessPurpose: 'initial' | 'successor' | null = null;
  #successorCaptureReadiness: ProductP1SuccessorCaptureReadiness = 'not_started';
  #successorCaptureReadinessReason: string | null = null;
  #successorCaptureReadinessStartedAtMs: number | null = null;
  #successorCaptureReadinessElapsedMs: number | null = null;
  #streamingRecognitionAvailable = false;
  #streamingFallbackReason: string | null = null;
  #streamingFallbackTier: 'batch' | 'text' | null = null;
  #pendingMediaActivation: Promise<unknown> | null = null;
  #endOfTurnNegotiated = false;
  #prefetchPromotionCapability: 'live-voice.media.prefetch-promotion.v1' | null = null;
  #activeContinuationAdmission: ActiveContinuationAdmission | null = null;
  readonly #deferredContinuationAdmissions: DeferredContinuationAdmission[] = [];
  #continuationAdmissionEpoch = 0;
  #continuationAdmissionCleanupPromise: Promise<void> | null = null;
  readonly #prefetchPromotionEnabled: boolean;
  #pendingSpeechStart: Readonly<MediaSpeechStart> | null = null;
  #pendingEndOfTurn: Readonly<MediaEndOfTurn> | null = null;
  #endOfTurnHandler: (() => void) | null = null;
  #endOfTurnDelivered = false;
  #bargeInSpeechStartDelivered = false;
  #bargeInEndOfTurnDelivered = false;
  #stopAndRecognizePromise: Promise<Readonly<ProductP1Recognition>> | null = null;
  #captureRotationPromise: Promise<void> | null = null;
  #captureRotationSourceId: string | null = null;
  #idleCapturePausePromise: Promise<'paused' | 'speech_active'> | null = null;
  #captureStopExpected = false;
  #l0Available: boolean;
  #l0PlayoutStartedAtMs: number | null = null;
  #l0PlayoutResponseKey: string | null = null;
  #l0PlayoutCompleted: Readonly<{
    responseKey: string;
    observedAt: string;
    monotonicMs: number;
    elapsedMs: number;
  }> | null = null;
  #l0ScheduledResponseKey: string | null = null;
  #l0FirstFrameResponseKey: string | null = null;
  #l0LastFrameSentClock: Readonly<{ observedAt: string; monotonicMs: number }> | null = null;
  #l0CaptureStartedAtMs: number | null = null;

  constructor(
    input: Readonly<{
      enabled: boolean;
      request: ProductP1Request;
      expected_origin: string;
      socket_factory?: DedicatedMediaSocketFactory;
      audio_environment?: BrowserAudioEnvironment;
      capture_stream_factory?: BrowserAudioCaptureStreamFactory;
      playout_startup_lead_ms?: number;
      prefetch_promotion_enabled?: boolean;
      on_status?: (status: ProductP1VoiceStatus, reason: string | null) => void;
      on_concurrent_capture_started?: () => void;
      on_barge_in_speech_start?: (event: Readonly<MediaSpeechStart>) => void;
      on_barge_in_end_of_turn?: (event: Readonly<MediaEndOfTurn>) => void;
    }>
  ) {
    this.#enabled = input.enabled === true;
    this.#request = input.request;
    this.#origin = requiredText(input.expected_origin, 'expected_origin');
    this.#socketFactory = input.socket_factory ?? defaultSocketFactory;
    this.#onStatus = input.on_status;
    this.#onConcurrentCaptureStarted = input.on_concurrent_capture_started;
    this.#onBargeInSpeechStart = input.on_barge_in_speech_start;
    this.#onBargeInEndOfTurn = input.on_barge_in_end_of_turn;
    this.#l0Available = browserL0Available();
    this.#prefetchPromotionEnabled = input.prefetch_promotion_enabled === true;
    this.#status = this.#enabled ? 'idle' : 'closed';
    this.#audio = new BrowserAudioIOAdapter({
      enabled: this.#enabled,
      c019DiagnosticsEnabled: this.#prefetchPromotionEnabled,
      ...(input.audio_environment === undefined ? {} : { environment: input.audio_environment }),
      ...(input.capture_stream_factory === undefined ? {} : { captureStreamFactory: input.capture_stream_factory }),
      ...(input.playout_startup_lead_ms === undefined
        ? {}
        : { playoutStartupLeadMs: input.playout_startup_lead_ms }),
      observer: {
        onCaptureFrame: frame => this.#acceptCaptureFrame(frame),
        onCaptureState: event => {
          let failure: (Error & { readonly reason: string }) | null = null;
          if (event.state === 'failed' && (!this.#captureReadinessPending || this.#captureStartupAudioReady)) {
            failure = Object.assign(new Error('formal browser capture failed'), {
              reason: 'AUDIO_CAPTURE_FAILED',
            });
          } else if (event.state === 'active' && event.reason === 'track_muted') {
            failure = Object.assign(new Error('formal browser capture was muted'), {
              reason: 'AUDIO_INPUT_MUTED',
            });
          } else if (['stopping', 'stopped'].includes(event.state)) {
            if (this.#captureStopExpected) return;
            failure = Object.assign(new Error('formal browser capture stopped unexpectedly'), {
              reason: stableCaptureStopReason(event.reason),
            });
          }
          if (failure === null || this.#failureCleanupPromise !== null || this.#closed || this.#closeRequested) return;
          if (this.#captureReadinessPending) {
            this.#captureStartupFailure ??= failure;
            this.#reason = this.#captureStartupFailure.reason;
            if (this.#captureReadinessPurpose === 'initial') {
              if (this.#status !== 'starting') return;
              this.#status = 'cleanup_pending';
              void this.#audio.close().catch(() => undefined);
            } else if (this.#captureReadinessPurpose !== 'successor') {
              return;
            }
            this.#publish();
          } else if (['capturing', 'playing'].includes(this.#status)) {
            void this.#fail(failure);
          }
        },
        onPlayoutState: event => this.#observePlayout(event),
        ...(this.#l0Available
          ? { onPlayoutScheduled: (event: Readonly<BrowserAudioPlayoutScheduledEvent>) => this.#observePlayoutScheduled(event) }
          : {}),
      },
    });
    this.#publish();
  }

  captureDiagnostics(): Readonly<ProductP1CaptureDiagnostics> {
    return Object.freeze({
      status: this.#status,
      operation_generation: this.#operationGeneration,
      frame_count: this.#frames.length,
      frames_acked: this.#captureFramesAcked,
      local_activity_observed: this.#captureSpeechObserved,
      local_activity_recency_frames: this.#captureLocalActivityRecencyFrames,
      provider_speech_start_observed: this.#captureProviderSpeechStartObserved,
      provider_end_of_turn_pending: this.#pendingEndOfTurn !== null,
      utterance_start_frame_index: this.#captureUtteranceStartFrameIndex,
      rotation_in_flight: this.#captureRotationPromise !== null,
      last_rotation: this.#lastCaptureRotation,
      actual_processing: this.#captureActualProcessing,
      successor_readiness: this.#successorCaptureReadiness,
      successor_readiness_reason: this.#successorCaptureReadinessReason,
      successor_readiness_elapsed_ms: this.#successorCaptureReadinessElapsedMs,
    });
  }

  #l0Binding(
    response: Readonly<AudioResponseRef> | null = null,
    unitSeq: number | null = null,
    unitId: string | null = null,
  ): Readonly<BrowserL0Binding> | null {
    if (
      !this.#l0Available
      || this.#sessionId === null
      || this.#correlationId === null
      || this.#interactionId === null
      || this.#activationId === null
      || this.#activationGeneration <= 0
    ) return null;
    return Object.freeze({
      correlation_id: this.#correlationId,
      session_id: this.#sessionId,
      interaction_id: this.#interactionId,
      activation_id: this.#activationId,
      activation_generation: this.#activationGeneration,
      response_id: response?.response_id ?? null,
      response_generation: response?.response_generation ?? null,
      unit_id: unitId,
      unit_seq: unitSeq,
      turn_id: null,
      round_id: null,
      task_id: null,
      attempt_id: null,
    });
  }

  #l0Record(
    milestone: Parameters<typeof recordBrowserL0Milestone>[0]['milestone'],
    response: Readonly<AudioResponseRef> | null = null,
    durationMs?: number,
    classification?: Parameters<typeof recordBrowserL0Milestone>[0]['classification'],
    clock?: Readonly<{ observedAt: string; monotonicMs: number }>,
    unitSeq: number | null = null,
    unitId: string | null = null,
  ): boolean {
    if (!this.#l0Available) return false;
    const binding = this.#l0Binding(response, unitSeq, unitId);
    if (binding === null) return false;
    return recordBrowserL0Milestone({
      milestone,
      binding,
      ...(durationMs === undefined ? {} : { duration_ms: durationMs }),
      ...(classification === undefined ? {} : { classification }),
      ...(clock === undefined ? {} : {
        observed_at: clock.observedAt,
        monotonic_ms: clock.monotonicMs,
      }),
    });
  }

  status(): Readonly<{ status: ProductP1VoiceStatus; reason: string | null }> {
    return Object.freeze({ status: this.#status, reason: this.#reason });
  }

  async startCapture(
    input: Readonly<{
      session_id: string;
      interaction_id: string;
      correlation_id: string;
      activation_id: string;
      activation_generation: number;
      locale?: 'zh-CN' | 'en-US';
      device_selection?: Readonly<ProductP1AudioDeviceSelection>;
    }>
  ): Promise<void> {
    if (!this.#enabled || this.#closed) throw new Error('formal P1 voice route is disabled');
    if (this.#closeRequested) throw new Error('formal P1 cleanup is in progress');
    if (this.#closePromise !== null) throw new Error('formal P1 cleanup is in progress');
    if (!['idle', 'recognized'].includes(this.#status)) throw new Error('formal P1 capture is already active');
    const sessionId = requiredText(input.session_id, 'session_id');
    const interactionId = requiredText(input.interaction_id, 'interaction_id');
    const correlationId = requiredText(input.correlation_id, 'correlation_id');
    const activationId = requiredText(input.activation_id, 'activation_id');
    const activationGeneration = input.activation_generation;
    if (!Number.isSafeInteger(activationGeneration) || activationGeneration <= 0) {
      throw new Error('activation_generation is invalid');
    }
    const locale = input.locale ?? 'zh-CN';
    if (!['zh-CN', 'en-US'].includes(locale)) throw new Error('locale is invalid');
    const selected: Readonly<ProductP1AudioDeviceSelection> = input.device_selection ?? Object.freeze({ selection_generation: 1 });
    if (!Number.isSafeInteger(selected.selection_generation) || selected.selection_generation <= 0) {
      throw new Error('device selection generation is invalid');
    }
    const inputDeviceId = selected.input_device_id === undefined ? undefined : requiredText(selected.input_device_id, 'input_device_id');
    const outputDeviceId = selected.output_device_id === undefined ? undefined : requiredText(selected.output_device_id, 'output_device_id');
    const deviceSelection = Object.freeze({
      selection_generation: selected.selection_generation,
      ...(inputDeviceId === undefined ? {} : { input_device_id: inputDeviceId }),
      ...(outputDeviceId === undefined ? {} : { output_device_id: outputDeviceId }),
    });
    const operationGeneration = ++this.#operationGeneration;
    this.#setStatus('starting', null);
    this.#captureStartupAudioReady = false;
    this.#captureStartupFailure = null;
    this.#mediaTerminalFailure = null;
    this.#captureReadinessPending = true;
    this.#captureReadinessPurpose = 'initial';
    this.#successorCaptureReadiness = 'not_started';
    this.#successorCaptureReadinessReason = null;
    this.#successorCaptureReadinessStartedAtMs = null;
    this.#successorCaptureReadinessElapsedMs = null;
    this.#streamingRecognitionAvailable = false;
    this.#streamingFallbackReason = null;
    this.#streamingFallbackTier = null;
    this.#endOfTurnNegotiated = false;
    this.#prefetchPromotionCapability = null;
    this.#pendingSpeechStart = null;
    this.#pendingEndOfTurn = null;
    this.#endOfTurnHandler = null;
    this.#endOfTurnDelivered = false;
    this.#bargeInSpeechStartDelivered = false;
    this.#bargeInEndOfTurnDelivered = false;
    this.#stopAndRecognizePromise = null;
    this.#failureCleanupReason = null;
    this.#continuationResponseKey = null;
    this.#frames = [];
    this.#captureSpeechObserved = false;
    this.#captureProviderSpeechStartObserved = false;
    this.#captureLocalActivityRecencyFrames = 0;
    this.#captureUtteranceStartFrameIndex = null;
    this.#mediaSentFrames = 0;
    this.#captureFirstFrameAcknowledged = false;
    this.#captureFirstFrameDiagnostic = null;
    this.#captureFramesAcked = 0;
    this.#route = null;
    this.#speech = null;
    this.#sessionId = sessionId;
    this.#interactionId = interactionId;
    this.#correlationId = correlationId;
    this.#locale = locale;
    this.#activationId = activationId;
    this.#activationGeneration = activationGeneration;
    this.#deviceSelection = deviceSelection;
    try {
      if (this.#mediaCloseBinding !== null) {
        await this.#revokeMediaAuthority(this.#mediaCloseBinding, 'start_capture');
      }
      this.#requireCurrent(operationGeneration);
      this.#playout = await this.#audio.unlockPlayout(
        deviceSelection.output_device_id ? { deviceId: deviceSelection.output_device_id } : {}
      );
      this.#requireCurrent(operationGeneration);
      if (this.#l0Available) {
        this.#l0CaptureStartedAtMs = monotonicNowMs();
        this.#l0LastFrameSentClock = null;
      }
      const metadata = await this.#audio.startCapture(deviceSelection.input_device_id ? { deviceId: deviceSelection.input_device_id } : {});
      this.#captureActualProcessing = metadata.actual_processing;
      this.#captureStartupAudioReady = true;
      this.#requireHealthyCaptureReadiness(operationGeneration);
      if (this.#playout.sample_rate_hz !== metadata.frame_format.sample_rate_hz) {
        throw new Error('capture and playout sample rates do not match');
      }
      const activationOperation = Promise.resolve().then(async () => {
        const activationValue = await this.#request(PRODUCT_P1_MEDIA_ACTIVATE_METHOD, {
          session_id: this.#sessionId,
          interaction_id: this.#interactionId,
          correlation_id: this.#correlationId,
          activation_id: activationId,
          activation_generation: activationGeneration,
          capture_id: metadata.capture_id,
          capture_generation: metadata.capture_generation,
          track_id: metadata.track_id,
          sample_rate_hz: metadata.frame_format.sample_rate_hz,
          locale: this.#locale,
          end_of_turn_capability: MEDIA_END_OF_TURN_CAPABILITY,
        });
        const activationEnvelope = objectValue(activationValue, 'media_activation');
        if (activationEnvelope.status !== 'active') {
          const inactive = exactObject(activationEnvelope, ['status', 'reason_id'], 'media_activation');
          if (!['disabled', 'unavailable'].includes(String(inactive.status))) {
            throw new Error('media activation returned an unknown status');
          }
          throw routeUnavailable(inactive.reason_id);
        }
        const activation = exactMediaActivation(activationEnvelope);
        if (activation.status !== 'active' || activation.subprotocol !== 'live-voice.media.v1') {
          throw routeUnavailable(activation.reason_id);
        }
        this.#mediaCloseBinding = Object.freeze({
          session_id: sessionId,
          subject_id: requiredText(activation.subject_id, 'subject_id'),
          correlation_id: correlationId,
          interaction_id: interactionId,
          activation_id: activationId,
          activation_generation: activationGeneration,
        });
        const privacy = exactObject(activation.privacy, ['raw_audio_persisted', 'raw_audio_logged', 'memory_only'], 'media_activation.privacy');
        if (privacy.raw_audio_persisted !== false || privacy.raw_audio_logged !== false || privacy.memory_only !== true)
          throw new Error('media activation did not prove its privacy boundary');
        this.#observeStreamingAvailability(activation);
        this.#observeEndOfTurnAvailability(activation);
        return activation;
      });
      this.#pendingMediaActivation = activationOperation;
      let activation: Record<string, unknown>;
      try {
        activation = await activationOperation;
      } finally {
        if (this.#pendingMediaActivation === activationOperation) this.#pendingMediaActivation = null;
      }
      this.#requireHealthyCaptureReadiness(operationGeneration);
      const attach = deserializeMediaControl(
        JSON.stringify({
          type: 'media.attach',
          contract_version: 'live-voice.media.v1',
          binding: activation.binding,
        })
      );
      if (
        attach.type !== 'media.attach' ||
        attach.binding.session_id !== this.#sessionId ||
        attach.binding.interaction_id !== this.#interactionId ||
        attach.binding.correlation_id !== this.#correlationId ||
        attach.binding.track_id !== metadata.track_id ||
        attach.binding.generation.kind !== 'capture' ||
        attach.binding.generation.id !== metadata.capture_id ||
        attach.binding.generation.value !== metadata.capture_generation ||
        attach.binding.frame_format.sample_rate_hz !== metadata.frame_format.sample_rate_hz
      )
        throw new Error('server media binding does not match the active browser capture');
      let ownedRoute: ActiveBrowserDedicatedMediaRoute | null = null;
      let mediaTicket = consumePrivateText(activation, 'media_ticket', 'media_ticket');
      let route: BrowserDedicatedMediaRouteActivation;
      try {
        route = createBrowserDedicatedMediaRoute({
          enabled: true,
          expected_origin: this.#origin,
          endpoint_url: mediaEndpoint(this.#origin, requiredText(activation.endpoint_path, 'endpoint_path')),
          media_ticket: mediaTicket,
          binding: attach.binding,
          provider_available: true,
          transport_available: typeof WebSocket === 'function',
          socket_factory: this.#socketFactory,
          on_audio_frame: () => undefined,
          ...(this.#l0Available
            ? {
                on_uplink_frame_sent: (seq: number) => {
                  if (ownedRoute !== null) this.#observeUplinkFrameSent(ownedRoute, seq);
                },
              }
            : {}),
          on_uplink_frame_acknowledged: (throughSeq: number) => {
            if (ownedRoute !== null) this.#observeUplinkFrameAcknowledged(ownedRoute, throughSeq);
          },
          on_first_frame_diagnostic: (fact: Readonly<MediaFirstFrameDiagnostic>) => {
            if (ownedRoute !== null) this.#observeFirstFrameDiagnostic(ownedRoute, fact);
          },
          on_terminal: event => {
            if (ownedRoute !== null) this.#observeMediaTerminal(ownedRoute, event);
          },
          ...(this.#endOfTurnNegotiated
            ? {
                end_of_turn_capability: MEDIA_END_OF_TURN_CAPABILITY,
                on_speech_start: (event: Readonly<MediaSpeechStart>) => {
                  this.#observeSpeechStartControl(operationGeneration, ownedRoute, event);
                },
                on_end_of_turn: (event: Readonly<MediaEndOfTurn>) => {
                  this.#observeEndOfTurnControl(operationGeneration, ownedRoute, event);
                },
              }
            : {}),
        });
      } finally {
        mediaTicket = '';
      }
      if (!route.active) throw new Error(route.reason_id);
      ownedRoute = route;
      this.#route = route;
      this.#speech = new GatewayBatchSpeechClient({
        enabled: true,
        transport: {
          request: async <T = unknown>(
            method: string,
            params?: Record<string, unknown>,
            options?: Readonly<{ timeoutMs?: number; signal?: AbortSignal }>,
          ) => (await this.#request(method, params ?? {}, options)) as T,
        },
        scope: {
          subject_id: requiredText(activation.subject_id, 'subject_id'),
          project_id: null,
          session_id: this.#sessionId,
          assurance: 'authenticated',
        },
      });
      this.#prefetchPromotionCapability = this.#prefetchPromotionEnabled
        ? await this.#speech.negotiatePrefetchPromotion({
            session_id: this.#sessionId,
            activation_id: activationId,
            activation_generation: activationGeneration,
          })
        : null;
      await this.#awaitCaptureReadiness(route, operationGeneration);
      this.#captureStartupAudioReady = false;
      this.#captureStartupFailure = null;
      this.#mediaTerminalFailure = null;
      this.#captureReadinessPending = false;
      this.#captureReadinessPurpose = null;
      this.#setStatus('capturing', this.#streamingFallbackReason);
    } catch (error) {
      const failure = this.#captureStartupFailure ?? this.#mediaTerminalFailure ?? error;
      this.#captureStartupAudioReady = false;
      this.#captureStartupFailure = null;
      this.#mediaTerminalFailure = null;
      this.#captureReadinessPending = false;
      this.#captureReadinessPurpose = null;
      await this.#fail(failure);
      throw failure;
    }
  }

  armEndOfTurn(handler: () => void): boolean {
    if (typeof handler !== 'function') throw new TypeError('end-of-turn handler is invalid');
    if (!this.#endOfTurnNegotiated) return false;
    if (this.#status !== 'capturing' || this.#route === null) {
      throw new Error('end-of-turn can only arm the current capture');
    }
    this.#endOfTurnHandler = handler;
    this.#deliverEndOfTurn(this.#operationGeneration, this.#route);
    return true;
  }

  stopAndRecognize(): Promise<Readonly<ProductP1Recognition>> {
    const retained = this.#stopAndRecognizePromise;
    if (retained !== null) return retained;
    const operation = this.#stopAndRecognizeOnce();
    this.#stopAndRecognizePromise = operation;
    return operation;
  }

  pauseIdleCaptureForNotification(): Promise<'paused' | 'speech_active'> {
    const retained = this.#idleCapturePausePromise;
    if (retained !== null) return retained;
    const operation = this.#pauseIdleCaptureForNotificationOnce().finally(() => {
      if (this.#idleCapturePausePromise === operation) this.#idleCapturePausePromise = null;
    });
    this.#idleCapturePausePromise = operation;
    return operation;
  }

  async #pauseIdleCaptureForNotificationOnce(): Promise<'paused' | 'speech_active'> {
    const rotation = this.#captureRotationPromise;
    if (rotation !== null) await rotation;
    if (this.#failureCleanupPromise !== null || this.#status !== 'capturing' || this.#route === null || this.#speech === null) {
      throw new Error('formal P1 idle capture is not active');
    }
    if (this.#captureSpeechObserved || this.#captureProviderSpeechStartObserved) return 'speech_active';
    const operationGeneration = ++this.#operationGeneration;
    const route = this.#route;
    try {
      this.#captureStopExpected = true;
      try {
        await this.#audio.stopCapture('formal_notification_idle_capture_pause');
      } finally {
        this.#captureStopExpected = false;
      }
      this.#requireCurrent(operationGeneration);
      this.#drainCaptureFrames();
      const deadline = Date.now() + ROUTE_DRAIN_TIMEOUT_MS;
      let pending = route.leaf.flush();
      while ((this.#mediaSentFrames !== this.#frames.length || pending.pending_frames !== 0) && !route.leaf.closed && Date.now() < deadline) {
        await waitTurn();
        this.#requireCurrent(operationGeneration);
        this.#drainCaptureFrames();
        pending = route.leaf.flush();
      }
      if (this.#mediaSentFrames !== this.#frames.length || pending.pending_frames !== 0) {
        throw Object.assign(new Error('formal idle capture did not drain before notification'), {
          reason: 'FORMAL_NOTIFICATION_CAPTURE_DRAIN_FAILED',
        });
      }
      this.#captureFramesAcked = this.#mediaSentFrames;
      await awaitRouteCompletion(route.leaf.completeUplink('MEDIA_LOCAL_CLOSE'));
      this.#requireCurrent(operationGeneration);
      this.#frames = [];
      this.#captureSpeechObserved = false;
      this.#captureProviderSpeechStartObserved = false;
      this.#captureLocalActivityRecencyFrames = 0;
      this.#captureUtteranceStartFrameIndex = null;
      this.#mediaSentFrames = 0;
      this.#captureFirstFrameAcknowledged = false;
      this.#captureFirstFrameDiagnostic = null;
      if (this.#route === route) this.#route = null;
      this.#endOfTurnHandler = null;
      this.#pendingSpeechStart = null;
      this.#pendingEndOfTurn = null;
      this.#setStatus('recognized', null);
      return 'paused';
    } catch (error) {
      this.#captureStopExpected = false;
      if (this.#closeRequested) {
        throw Object.assign(new Error('formal notification capture pause was cancelled by route close'), {
          reason: 'FORMAL_P1_CLOSED',
        });
      }
      await this.#fail(error);
      throw error;
    }
  }

  async #stopAndRecognizeOnce(): Promise<Readonly<ProductP1Recognition>> {
    if (this.#failureCleanupPromise !== null || this.#status !== 'capturing' || this.#route === null || this.#speech === null) {
      throw new Error('formal P1 capture is not active');
    }
    const operationGeneration = ++this.#operationGeneration;
    const route = this.#route;
    const speech = this.#speech;
    this.#setStatus('recognizing', null);
    try {
      await this.#releaseContinuationSpeechAuthority('continuation_recognition_requested');
      this.#requireCurrent(operationGeneration);
      await this.#audio.stopCapture('formal_recognition_requested');
      this.#l0Record('capture_stopped');
      this.#requireCurrent(operationGeneration);
      this.#drainCaptureFrames();
      const deadline = Date.now() + ROUTE_DRAIN_TIMEOUT_MS;
      let pending = route.leaf.flush();
      while ((this.#mediaSentFrames !== this.#frames.length || pending.pending_frames !== 0) && !route.leaf.closed && Date.now() < deadline) {
        await waitTurn();
        this.#requireCurrent(operationGeneration);
        this.#drainCaptureFrames();
        pending = route.leaf.flush();
      }
      if (this.#mediaSentFrames !== this.#frames.length || pending.pending_frames !== 0) {
        throw new Error('dedicated media route did not acknowledge the complete capture');
      }
      if (
        this.#l0CaptureStartedAtMs !== null
        && this.#l0LastFrameSentClock !== null
        && this.#l0LastFrameSentClock.monotonicMs >= this.#l0CaptureStartedAtMs
      ) {
        this.#l0Record(
          'last_frame_sent',
          null,
          this.#l0LastFrameSentClock.monotonicMs - this.#l0CaptureStartedAtMs,
          undefined,
          this.#l0LastFrameSentClock,
        );
      }
      this.#captureFramesAcked = this.#mediaSentFrames;
      await awaitRouteCompletion(route.leaf.completeUplink('MEDIA_LOCAL_CLOSE'));
      this.#requireCurrent(operationGeneration);
      // A lease extended by the utterance budget keeps its complete frame set:
      // the Speech client requires batch recognition input to start at the
      // first captured frame, so no pre-utterance audio is dropped here. The
      // extreme corner where a late-started utterance pushes batch-fallback
      // WAV past the Gateway's upload bound is a disclosed Speech-fallback
      // limitation owned outside this packet; the streaming-primary path is
      // unaffected.
      const recognitionInput = Object.freeze({
        frames: this.#frames,
        locale: this.#locale,
        correlationId: requiredText(this.#correlationId, 'correlation_id'),
        interactionId: requiredText(this.#interactionId, 'interaction_id'),
      });
      let degradationReason: string | null = this.#streamingFallbackReason;
      let result: Readonly<FormalBatchRecognitionResult | FormalStreamingRecognitionResult> | null;
      if (this.#streamingRecognitionAvailable) {
        const streaming = await speech.recognizeStreamingFinal(recognitionInput);
        this.#requireCurrent(operationGeneration);
        if (streaming.status === 'completed') {
          result = streaming.result;
        } else if (streaming.fallback.fallback_tier === 'batch') {
          degradationReason = streaming.fallback.reason_id;
          this.#l0Record('fallback', null, undefined, 'fallback');
          console.warn(`live_voice_speech_degradation reason=${degradationReason} target=batch visible=true`);
          this.#setStatus('recognizing', degradationReason);
          result = await speech.recognizeFinal(recognitionInput);
        } else {
          throw Object.assign(new Error('streaming recognition requires text fallback'), {
            reason_id: streaming.fallback.reason_id,
          });
        }
      } else {
        if (degradationReason !== null) {
          const fallbackTier = this.#streamingFallbackTier;
          if (fallbackTier === null) throw new Error('streaming recognition fallback tier is absent');
          this.#l0Record('fallback', null, undefined, 'fallback');
          console.warn(`live_voice_speech_degradation reason=${degradationReason} target=${fallbackTier} visible=true`);
          this.#setStatus('recognizing', degradationReason);
          if (fallbackTier === 'text') {
            throw Object.assign(new Error('streaming recognition requires text fallback'), {
              reason_id: degradationReason,
            });
          }
        }
        result = await speech.recognizeFinal(recognitionInput);
      }
      // The formal STT result, not captured samples, is the retained product
      // fact. Release the browser copy as soon as the exact request settles.
      this.#frames = [];
      this.#captureSpeechObserved = false;
      this.#captureProviderSpeechStartObserved = false;
      this.#captureLocalActivityRecencyFrames = 0;
      this.#captureUtteranceStartFrameIndex = null;
      this.#mediaSentFrames = 0;
      this.#captureFirstFrameAcknowledged = false;
      this.#captureFirstFrameDiagnostic = null;
      this.#route = null;
      this.#requireCurrent(operationGeneration);
      if (result === null) throw new Error('formal recognition was fenced');
      this.#setStatus('recognized', degradationReason);
      return Object.freeze({
        text: result.final_text,
        voice_commit_receipt: result.voice_commit_receipt,
      });
    } catch (error) {
      if (stableFailureReason(error) === PRODUCT_P1_EMPTY_TRANSCRIPT_REASON) {
        // An empty successor capture is an expected zero-input outcome, not a
        // broken Speech/media route. The exact capture has already been flushed
        // and closed above, so release its browser samples while retaining the
        // authenticated Speech/playout authority for the next P2 response.
        // No recognition receipt is returned, so callers cannot commit an empty
        // Agent/Tool turn.
        this.#frames = [];
        this.#captureSpeechObserved = false;
        this.#captureProviderSpeechStartObserved = false;
        this.#captureLocalActivityRecencyFrames = 0;
        this.#captureUtteranceStartFrameIndex = null;
        this.#mediaSentFrames = 0;
        this.#captureFirstFrameAcknowledged = false;
        this.#captureFirstFrameDiagnostic = null;
        this.#route = null;
        this.#setStatus('idle', PRODUCT_P1_EMPTY_TRANSCRIPT_REASON);
        throw error;
      }
      await this.#fail(error);
      throw error;
    }
  }

  async playAgentText(input: Readonly<ProductP1AgentTextInput>): Promise<void> {
    const prepared = await this.prepareAgentText(input);
    const continuationOverCapture =
      this.#preparedSpeech.get(prepared)?.continuationOverCapture === true;
    await this.playPreparedAgentText(prepared);
    // Preserve the C2 one-tail compatibility path. C3 calls prepare/play
    // directly and closes the retained authority only after the whole group.
    if (continuationOverCapture) await this.completePreparedResponse(input.response);
  }

  async prepareAgentText(
    input: Readonly<ProductP1AgentTextInput>,
    signal?: AbortSignal,
  ): Promise<Readonly<PreparedProductSpeech>> {
    if (this.#speech === null || this.#playout === null || this.#closed || this.#closeRequested) {
      throw new Error('formal P1 synthesis authority is unavailable');
    }
    const responseKey = l0ResponseKey(input.response);
    const unitSeq = input.unit_seq ?? 0;
    if (!Number.isSafeInteger(unitSeq) || unitSeq < 0) {
      throw new Error('agent_text unit sequence is invalid');
    }
    const unitId = requiredText(input.unit_id, 'unit_id');
    const negotiatedContinuation =
      input.response_continuation === true
      && this.#prefetchPromotionCapability !== null
      && unitSeq >= 1;
    const responseContinuation =
      input.response_continuation === true &&
      this.#continuationResponseKey === responseKey;
    if (negotiatedContinuation && !responseContinuation) {
      throw new Error('negotiated continuation response is stale or foreign');
    }
    const continuationOverCapture =
      this.#status === 'capturing' &&
      responseContinuation;
    if (
      ['starting', 'recognizing'].includes(this.#status) ||
      (this.#status === 'capturing' && !continuationOverCapture)
    ) {
      throw new Error('formal P1 capture must settle before Agent playout');
    }
    if (this.#status === 'recognized') {
      if (
        this.#continuationResponseKey !== null &&
        this.#continuationResponseKey !== responseKey
      ) {
        await this.#releaseContinuationSpeechAuthority('continuation_response_replaced');
      }
      this.#continuationResponseKey =
        input.response_continuation === true ? responseKey : null;
      if (input.response_continuation === true) {
        this.#continuationSpeech = this.#speech;
        this.#continuationReceiptAuthority = this.#mediaCloseBinding;
        this.#continuationCaptureFramesAcked = this.#captureFramesAcked;
      }
    }
    const operationGeneration = responseContinuation
      ? this.#operationGeneration
      : ++this.#operationGeneration;
    const speech = responseContinuation
      ? this.#continuationSpeech
      : this.#speech;
    if (speech === null) {
      throw new Error('formal P1 continuation speech authority is unavailable');
    }
    let continuationAdmissionEpoch: number | null = null;
    try {
      // C2 AUDIO spans preserve the exact UTF-8 slice of chat.final.  A stable
      // prefix may therefore end in separator whitespace and its tail may
      // begin with it; trimming here would either reject or rewrite spoken
      // authoritative bytes.
      const text = requiredSpeakableText(input.text, 'agent_text');
      continuationAdmissionEpoch = negotiatedContinuation
        ? await this.#acquireContinuationAdmission(
            input.response,
            responseKey,
            unitId,
            unitSeq,
            speech,
            signal,
          )
        : null;
      const measurementBinding = this.#l0Binding(input.response, unitSeq, unitId);
      if (measurementBinding !== null) registerBrowserL0Response(measurementBinding);
      this.#l0Record('unit_tts_requested', input.response, undefined, undefined, undefined, unitSeq, unitId);
      if (unitSeq >= 1) {
        this.#l0Record('successor_tts_requested', input.response, undefined, undefined, undefined, unitSeq, unitId);
      }
      this.#preparingSpeechCount += 1;
      let result: Readonly<FormalBatchSynthesisResult> | null;
      try {
        result = await speech.synthesizeAuthoritative({
          response: input.response,
          unitId,
          unitSeq,
          renderPlan: createAudioRenderPlan(text, text, []),
          authoritativeAgentText: true,
          locale: this.#locale,
          voice: null,
          requiredSampleRateHz: this.#playout.sample_rate_hz,
          correlationId: requiredText(this.#correlationId, 'correlation_id'),
          ...(responseContinuation && this.#prefetchPromotionCapability !== null
            ? { prefetchPromotionCapability: this.#prefetchPromotionCapability }
            : {}),
          signal,
        });
      } finally {
        this.#preparingSpeechCount -= 1;
      }
      if (
        continuationAdmissionEpoch !== null
        && (
          this.#continuationAdmissionEpoch !== continuationAdmissionEpoch
          || this.#activeContinuationAdmission?.responseKey !== responseKey
          || this.#activeContinuationAdmission.unitId !== unitId
          || this.#activeContinuationAdmission.unitSeq !== unitSeq
        )
      ) {
        throw new Error('continuation admission was superseded');
      }
      this.#requireCurrent(operationGeneration);
      if (result === null) throw new Error('formal synthesis was fenced');
      if ((result.chunks.length === 0) === (result.downlink === null)) {
        throw new Error('formal synthesis must return exactly one audio delivery');
      }
      const receiptAuthority = responseContinuation
        ? this.#continuationReceiptAuthority
        : this.#mediaCloseBinding;
      const captureFramesAcked = responseContinuation
        ? this.#continuationCaptureFramesAcked
        : this.#captureFramesAcked;
      if (receiptAuthority === null || captureFramesAcked <= 0) {
        throw new Error('formal synthesis lost its capture authority');
      }
      if (result.chunks.length > 0) {
        this.#l0Record('unit_first_pcm', input.response, undefined, undefined, undefined, unitSeq, result.unit_id);
      }
      this.#l0Record('unit_prepared', input.response, undefined, undefined, undefined, unitSeq, result.unit_id);
      const prepared: Readonly<PreparedProductSpeech> = Object.freeze({
        response: Object.freeze({ ...result.response }),
        unitId: result.unit_id,
        unitSeq,
        provider: result.provider,
        chunks: Object.freeze([...result.chunks]),
        downlink: result.downlink,
        receiptAuthority,
        captureFramesAcked,
      });
      this.#preparedSpeech.set(
        prepared,
        Object.freeze({
          result,
          operationGeneration,
          responseContinuation,
          continuationOverCapture,
          captureDuringPlayout: input.capture_during_playout !== false,
          responseKey,
          speech,
          continuationAdmissionEpoch,
        }),
      );
      return prepared;
    } catch (error) {
      if (
        signal?.aborted
        || (
          continuationAdmissionEpoch !== null
          && continuationAdmissionEpoch !== this.#continuationAdmissionEpoch
        )
      ) {
        const cancellation = Object.assign(new Error('prepared formal speech was cancelled'), {
          reason: 'TTS_CONTINUATION_CANCELLED',
        });
        throw cancellation;
      }
      if (!this.#closeRequested) await this.#fail(error);
      throw error;
    }
  }

  async stagePreparedAgentText(
    prepared: Readonly<PreparedProductSpeech>,
  ): Promise<void> {
    const metadata = this.#preparedSpeech.get(prepared);
    if (metadata === undefined || this.#closed || this.#closeRequested) {
      throw new Error('prepared formal speech is stale, foreign, or already consumed');
    }
    if (!metadata.responseContinuation) {
      throw new Error('only a same-response continuation can be staged');
    }
    const existing = this.#stagedSuccessor;
    if (existing !== null) {
      if (existing.prepared === prepared && existing.attached && !existing.promoted) return;
      throw new Error('a prepared formal speech successor is already staged');
    }
    const staged: StagedProductSuccessor = {
      prepared,
      metadata,
      downlinkRoute: null,
      chunks: [...metadata.result.chunks],
      terminal: null,
      attached: metadata.result.downlink === null,
      promoted: false,
      reserveBytes: 0,
      transportAcknowledgedThrough: -1,
      pending: null,
      parked: false,
      transitionPromise: null,
    };
    this.#stagedSuccessor = staged;
    if (metadata.result.downlink === null) return;

    let resolveAttach!: () => void;
    let rejectAttach!: (error: Error) => void;
    let resolveFirstFrame!: () => void;
    let rejectFirstFrame!: (error: Error) => void;
    const attached = new Promise<void>((resolve, reject) => {
      resolveAttach = resolve;
      rejectAttach = reject;
    });
    const firstFrame = new Promise<void>((resolve, reject) => {
      resolveFirstFrame = resolve;
      rejectFirstFrame = reject;
    });
    void attached.catch(() => undefined);
    void firstFrame.catch(() => undefined);
    try {
      staged.downlinkRoute = this.#openDownlinkRoute(
        metadata.result.downlink,
        metadata.result.provider,
        metadata.result.response,
        metadata.result.unit_id,
        prepared.unitSeq,
        () => {
          if (this.#stagedSuccessor !== staged || staged.promoted) return;
          staged.attached = true;
          this.#l0Record(
            'successor_downlink_attached',
            metadata.result.response,
            undefined,
            undefined,
            undefined,
            prepared.unitSeq,
            prepared.unitId,
          );
          resolveAttach();
        },
        frame => {
          if (staged.promoted && staged.pending !== null) {
            this.#acceptDownlinkFrame(staged.pending, frame, metadata.result.provider);
            return;
          }
          if (
            this.#stagedSuccessor !== staged
            || frame.seq !== staged.chunks.length
            || frame.seq >= Math.min(
              metadata.result.downlink?.frame_count ?? MAX_STREAMING_PLAYOUT_FRAMES,
              STAGED_SUCCESSOR_RESERVE_CEILING_MS / LIVE_VOICE_AUDIO_FRAME_DURATION_MS,
            )
          ) {
            throw new Error('staged dedicated media frame is stale or non-contiguous');
          }
          const frameBytes = frame.samples.byteLength;
          const format = staged.downlinkRoute!.binding.frame_format;
          const reserveByteCeiling = format.sample_rate_hz
            * format.channel_count
            * Float32Array.BYTES_PER_ELEMENT
            * STAGED_SUCCESSOR_RESERVE_CEILING_MS / 1_000;
          if (staged.reserveBytes + frameBytes > reserveByteCeiling) {
            throw new Error('staged successor reserve byte ceiling exceeded');
          }
          staged.chunks.push(Object.freeze({
            response: metadata.result.response,
            unit_id: metadata.result.unit_id,
            seq: frame.seq,
            sample_rate_hz: staged.downlinkRoute!.binding.frame_format.sample_rate_hz,
            channel_count: 1,
            samples: Float32Array.from(frame.samples),
            provider: metadata.result.provider,
          }));
          staged.reserveBytes += frameBytes;
          const transportWindowFrames = Math.min(
            metadata.result.downlink!.max_pending_frames,
            Math.floor(metadata.result.downlink!.max_pending_bytes / frameBytes),
          );
          const reserveFrameCeiling = STAGED_SUCCESSOR_RESERVE_CEILING_MS / LIVE_VOICE_AUDIO_FRAME_DURATION_MS;
          const reserveByteHeadroom = transportWindowFrames * frameBytes;
          if (
            staged.chunks.length + transportWindowFrames <= reserveFrameCeiling
            && staged.reserveBytes + reserveByteHeadroom <= reserveByteCeiling
            && (
              metadata.result.downlink!.prefetch_promotion_capability === null
              || frame.seq < STAGED_SUCCESSOR_RESERVE_TARGET_MS / LIVE_VOICE_AUDIO_FRAME_DURATION_MS
            )
          ) {
            this.#scheduleStagedDownlinkAck(staged, frame.seq);
          }
          if (frame.seq === 0) {
            this.#l0Record(
              'successor_first_frame_buffered',
              metadata.result.response,
              undefined,
              undefined,
              undefined,
              prepared.unitSeq,
              prepared.unitId,
            );
            resolveFirstFrame();
          }
        },
        event => {
          staged.terminal = event;
          // An owned local close (barge-in, Stop, Exit, continuation cancel)
          // settles a staged route that never attached or never buffered as a
          // cancellation. Only peer_detach, transport_close and internal
          // failures keep the transport reason as the failure reason.
          const stagedClosure = (message: string): Error =>
            Object.assign(
              new Error(message),
              event.source === 'local_close'
                ? {
                    reason: 'TTS_CONTINUATION_CANCELLED',
                    source: event.source,
                    transport_reason_id: event.reason_id,
                  }
                : { reason: event.reason_id, source: event.source },
            );
          if (!staged.attached) {
            const failure = stagedClosure('staged downlink closed before attach');
            rejectAttach(failure);
            rejectFirstFrame(failure);
          } else if (staged.chunks.length === 0) {
            rejectFirstFrame(stagedClosure('staged downlink closed before first frame'));
          } else if (
            !staged.promoted
            && staged.metadata.result.downlink?.prefetch_promotion_capability !== null
          ) {
            if (event.source === 'local_close' || this.#stagedTransitionSuperseded(staged)) {
              // Stop, barge-in or Exit released this staged slot and closed
              // its route locally. That owned close is expected and must not
              // become a visible failure or an L0 failure record.
              console.info('[LiveVoiceC019] transition diagnostic', {
                event: 'browser_staged_close_expected',
                response_generation: staged.prepared.response.response_generation,
                unit_seq: staged.prepared.unitSeq,
                reason_id: event.reason_id,
              });
            } else {
              this.#stagedSuccessor = null;
              void this.#fail(Object.assign(
                new Error('negotiated staged downlink closed before promotion'),
                { reason: event.reason_id },
              ));
            }
          }
          if (staged.promoted && staged.pending !== null && staged.downlinkRoute !== null) {
            this.#observeMediaTerminal(staged.downlinkRoute, event);
          }
        },
      );
      await Promise.all([attached, firstFrame]);
      this.#requireCurrent(metadata.operationGeneration);
    } catch (error) {
      if (this.#stagedSuccessor === staged) this.#stagedSuccessor = null;
      staged.downlinkRoute?.leaf.close('MEDIA_LOCAL_CLOSE');
      throw error;
    }
  }

  async playPreparedAgentText(
    prepared: Readonly<PreparedProductSpeech>,
  ): Promise<void> {
    let metadata = this.#preparedSpeech.get(prepared);
    if (metadata === undefined || this.#closed || this.#closeRequested) {
      throw new Error('prepared formal speech is stale, foreign, or already consumed');
    }
    if (metadata.responseContinuation && this.#stagedSuccessor?.prepared !== prepared) {
      await this.stagePreparedAgentText(prepared);
      metadata = this.#preparedSpeech.get(prepared);
      if (metadata === undefined) throw new Error('staged formal speech lost its owner');
    }
    const staged = metadata.responseContinuation ? this.#stagedSuccessor : null;
    if (
      metadata.responseContinuation
      && (staged === null || staged.prepared !== prepared || !staged.attached || staged.promoted)
    ) {
      throw new Error('prepared formal speech is not staged for promotion');
    }
    if (staged !== null) {
      const selected = staged.metadata.result.downlink?.prefetch_promotion_capability;
      if (selected !== null && selected !== undefined && staged.downlinkRoute !== null) {
        // Let an ACK/PARK microtask already scheduled by the frame callback
        // linearize before deciding the short-tail frontier.
        await Promise.resolve();
        if (staged.transitionPromise !== null) await staged.transitionPromise;
        if (staged.parked) {
          console.info('[LiveVoiceC019] transition diagnostic', {
            event: 'browser_product_promotion_requested',
            response_generation: prepared.response.response_generation,
            unit_seq: prepared.unitSeq,
          });
          this.#l0Record(
            'successor_promotion_requested', prepared.response,
            undefined, undefined, undefined, prepared.unitSeq, prepared.unitId,
          );
          await staged.downlinkRoute.leaf.promotePrefetch();
          console.info('[LiveVoiceC019] transition diagnostic', {
            event: 'browser_product_promotion_acknowledged',
            response_generation: prepared.response.response_generation,
            unit_seq: prepared.unitSeq,
          });
          this.#l0Record(
            'successor_promoted', prepared.response,
            undefined, undefined, undefined, prepared.unitSeq, prepared.unitId,
          );
        } else {
          if (staged.transportAcknowledgedThrough < 0) {
            throw new Error('staged successor has no transport ACK to promote');
          }
          await staged.downlinkRoute.leaf.promoteUnparked(
            staged.transportAcknowledgedThrough,
          );
          this.#l0Record(
            'successor_promoted_unparked', prepared.response,
            undefined, undefined, undefined, prepared.unitSeq, prepared.unitId,
          );
        }
      }
      staged.promoted = true;
      this.#stagedSuccessor = null;
      this.#releaseContinuationAdmission(prepared, metadata);
    }
    this.#preparedSpeech.delete(prepared);
    const {
      result,
      operationGeneration,
      responseContinuation,
      responseKey,
      speech,
      captureDuringPlayout: captureDuringPlayoutRequested,
    } = metadata;
    const input = Object.freeze({ response: prepared.response, unit_id: prepared.unitId });
    const receiptAuthority = prepared.receiptAuthority;
    const captureFramesAcked = prepared.captureFramesAcked;
    let playoutResponse: Readonly<AudioResponseRef> | null = null;
    let capturePreparation: Promise<Readonly<{ ready: boolean; reason: string | null }>> | null = null;
    try {
      let downlinkRoute: ActiveBrowserDedicatedMediaRoute | null = staged?.downlinkRoute ?? null;
      let downlinkTerminal: Readonly<DedicatedMediaTerminalEvent> | null = staged?.terminal ?? null;
      let downlinkAttached = staged?.attached ?? false;
      let pendingRef: PendingProductPlayout | null = null;
      const chunks = staged?.chunks ?? [...result.chunks];
      // A streaming downlink deliberately declares no final frame count. Keep
      // that `null` distinct from the batch path's in-envelope chunk count;
      // nullish coalescing here would turn a valid stream into a zero-frame
      // batch and reject its first media frame as stale.
      const frameCount = result.downlink === null ? chunks.length : result.downlink.frame_count;
      const captureDuringPlayout =
        result.downlink !== null
        && captureDuringPlayoutRequested
        && !responseContinuation;
      if (result.downlink !== null && downlinkRoute === null) {
        let resolveDownlinkAttach!: () => void;
        let rejectDownlinkAttach!: (error: Error) => void;
        const downlinkAttachReadiness = new Promise<void>((resolve, reject) => {
          resolveDownlinkAttach = resolve;
          rejectDownlinkAttach = reject;
        });
        void downlinkAttachReadiness.catch(() => undefined);
        downlinkRoute = this.#openDownlinkRoute(
          result.downlink,
          result.provider,
          result.response,
          result.unit_id,
          prepared.unitSeq,
          () => {
            downlinkAttached = true;
            resolveDownlinkAttach();
          },
          frame => {
            if (pendingRef === null) throw new Error('downlink arrived before playout ownership');
            this.#acceptDownlinkFrame(pendingRef, frame, result.provider);
          },
          event => {
            downlinkTerminal = event;
            if (!downlinkAttached) {
              rejectDownlinkAttach(
                Object.assign(new Error('dedicated media downlink closed before attach'), {
                  reason: event.reason_id,
                }),
              );
            }
            if (pendingRef !== null && downlinkRoute !== null) this.#observeMediaTerminal(downlinkRoute, event);
          }
        );
        if (captureDuringPlayout) {
          this.#successorCaptureReadiness = 'pending';
          this.#successorCaptureReadinessReason = null;
          this.#successorCaptureReadinessStartedAtMs = monotonicNowMs();
          this.#successorCaptureReadinessElapsedMs = null;
          capturePreparation = downlinkAttachReadiness.then(() => {
            this.#requireCurrent(operationGeneration);
            return this.#prepareConcurrentCapture(
              operationGeneration,
              receiptAuthority,
              speech,
              result.response,
            );
          });
          // The authoritative downlink must start independently. Retain a
          // rejection handler immediately, then join the bounded preparation
          // after browser rendering. Successor capture begins only after the
          // exact predecessor downlink attaches, so successor-only cleanup
          // cannot revoke its one-use ticket while the socket is connecting.
          void capturePreparation.catch(() => undefined);
        }
      }
      const expected = new Map<string, number>();
      if (frameCount !== null) expected.set(result.unit_id, frameCount - 1);
      let resolvePlayout!: () => void;
      let rejectPlayout!: (error: Error) => void;
      const rendered = new Promise<void>((resolve, reject) => {
        resolvePlayout = resolve;
        rejectPlayout = reject;
      });
      // A browser source can fail synchronously during enqueue after the
      // observer has already rejected this exact render waiter. Install a
      // handler immediately so that direct enqueue failure cannot leave an
      // unhandled rejection; awaiting `rendered` below still preserves failure.
      void rendered.catch(() => undefined);
      playoutResponse = result.response;
      const pendingPlayout: PendingProductPlayout = {
        response: result.response,
        unitId: requiredText(input.unit_id, 'unit_id'),
        unitSeq: prepared.unitSeq,
        chunks,
        frameCount,
        degradationReason: result.downlink?.degradation_reason ?? null,
        downlinkRoute,
        receiptAuthority,
        captureFramesAcked,
        transportAcknowledgedThrough: staged?.transportAcknowledgedThrough ?? -1,
        nextChunkIndex: 0,
        renderedChunks: 0,
        peakDepth: 0,
        filling: false,
        expected,
        observed: new Map(),
        lastRenderedClock: null,
        resolve: resolvePlayout,
        reject: rejectPlayout,
      };
      pendingRef = pendingPlayout;
      if (staged !== null) staged.pending = pendingPlayout;
      this.#pendingPlayout = pendingPlayout;
      if (downlinkTerminal !== null && downlinkRoute !== null) {
        this.#observeMediaTerminal(downlinkRoute, downlinkTerminal);
        this.#requireCurrent(operationGeneration);
      }
      if (this.#l0Available) {
        this.#l0PlayoutStartedAtMs = monotonicNowMs();
        this.#l0PlayoutResponseKey = l0ResponseKey(result.response);
        this.#l0PlayoutCompleted = null;
        this.#l0ScheduledResponseKey = null;
        this.#l0FirstFrameResponseKey = null;
      }
      if (staged !== null) {
        this.#l0Record(
          'successor_promoted_to_playout',
          pendingPlayout.response,
          undefined,
          undefined,
          undefined,
          pendingPlayout.unitSeq,
          pendingPlayout.unitId,
        );
      }
      this.#audio.beginPlayout(
        result.response,
        responseContinuation
          ? { continuation_unit_id: result.unit_id }
          : {},
      );
      this.#fillPlayoutQueue(pendingPlayout);
      this.#deliverBargeInSpeechStart(operationGeneration, this.#route);
      this.#deliverBargeInEndOfTurn(operationGeneration, this.#route);
      await rendered;
      const renderedUnitCompletion = this.#currentL0PlayoutCompletion();
      if (
        renderedUnitCompletion !== null
        && renderedUnitCompletion.responseKey === l0ResponseKey(pendingPlayout.response)
      ) {
        this.#l0Record(
          'unit_playout_completed',
          pendingPlayout.response,
          renderedUnitCompletion.elapsedMs,
          'success',
          renderedUnitCompletion,
          pendingPlayout.unitSeq,
          pendingPlayout.unitId,
        );
      }
      this.#requireCurrent(operationGeneration);
      if (downlinkRoute !== null) {
        const deadline = Date.now() + ROUTE_DRAIN_TIMEOUT_MS;
        while (!downlinkRoute.leaf.closed && Date.now() < deadline) await waitTurn();
        if (!downlinkRoute.leaf.closed) {
          throw new Error('dedicated media downlink did not close after final render ACK');
        }
        await waitTurn();
      }
      const rotation = this.#captureRotationPromise;
      if (rotation !== null) await rotation;
      const captureReadiness = capturePreparation === null ? null : await capturePreparation;
      // When overlap is enabled, the successor capture remains live while the
      // final downlink detach is drained. Any capture startup or device failure
      // synchronously changes the operation generation; fence it before minting
      // a render receipt in both the overlapping and deferred cases.
      this.#requireCurrent(operationGeneration);
      await this.#acknowledgePlayout(pendingPlayout);
      this.#l0Record(
        'unit_acknowledged',
        pendingPlayout.response,
        undefined,
        'success',
        undefined,
        pendingPlayout.unitSeq,
        pendingPlayout.unitId,
      );
      this.#requireCurrent(operationGeneration);
      const completed = this.#currentL0PlayoutCompletion();
      if (
        completed !== null
        && completed.responseKey === l0ResponseKey(pendingPlayout.response)
      ) {
        this.#l0Record(
          'playout_completed',
          pendingPlayout.response,
          completed.elapsedMs,
          'success',
          completed,
        );
        this.#l0PlayoutCompleted = null;
      }
      if (downlinkRoute !== null) {
        if (this.#settlingPlayout === pendingPlayout) this.#settlingPlayout = null;
        if (responseContinuation) {
          this.#setStatus('capturing', pendingPlayout.degradationReason);
          this.#deliverEndOfTurn(this.#operationGeneration, this.#route);
        } else if (!captureDuringPlayout) {
          // Task announcements deliberately pause listening before playback.
          // Do not create an overlap capture that can hear the announcement
          // itself and survive as an unarmed successor after the final ACK.
          // The Integrated route starts one fresh capture after presentation
          // settlement, using the normal authorized media-start path.
          this.#setStatus('recognized', null);
        } else if (captureReadiness?.ready === true) {
          if (this.#continuationResponseKey !== responseKey) {
            await this.#revokeMediaAuthority(receiptAuthority, 'playout_completed_receipt');
            this.#requireCurrent(operationGeneration);
          }
          this.#setStatus('capturing', pendingPlayout.degradationReason);
          this.#deliverEndOfTurn(this.#operationGeneration, this.#route);
        } else {
          this.#setStatus('recognized', captureReadiness?.reason ?? 'AUDIO_CAPTURE_FAILED');
        }
      } else {
        if (this.#settlingPlayout === pendingPlayout) this.#settlingPlayout = null;
        this.#setStatus('recognized', null);
      }
    } catch (error) {
      if (error !== null && typeof error === 'object' && (error as Record<string, unknown>).reason === 'FORMAL_PLAYOUT_BARGED') {
        if (this.#continuationAdmissionCleanupPromise !== null) {
          await this.#continuationAdmissionCleanupPromise;
        }
        await this.#releaseContinuationSpeechAuthority('continuation_playout_barged');
        this.#setStatus(this.#route === null ? 'recognized' : 'capturing', null);
        this.#deliverEndOfTurn(this.#operationGeneration, this.#route);
        return;
      }
      if (this.#closeRequested) {
        throw Object.assign(new Error('formal playout was cancelled by route close'), {
          reason: 'FORMAL_P1_CLOSED',
        });
      }
      const failure =
        playoutResponse !== null && stableFailureReason(error) === 'PAGE_HIDDEN'
          ? Object.assign(new Error('formal browser playout was fenced because the page is hidden'), {
              reason: 'PAGE_HIDDEN_PLAYOUT_FENCED',
            })
          : this.#failureCleanupReason !== null
            ? Object.assign(new Error('formal playout was fenced by the retained route failure'), {
                reason: this.#failureCleanupReason,
              })
            : error;
      const pending = this.#pendingPlayout;
      if (pending !== null && playoutResponse !== null) {
        this.#pendingPlayout = null;
        this.#audio.stopPlayout(playoutResponse, 'formal_playout_failed');
      }
      await this.#fail(failure);
      throw failure;
    }
  }

  async cancelPreparedResponse(
    response: Readonly<AudioResponseRef>,
    reason: string,
  ): Promise<void> {
    requiredText(reason, 'reason');
    const responseKey = l0ResponseKey(response);
    if (
      this.#activeContinuationAdmission?.responseKey === responseKey
      || this.#deferredContinuationAdmissions.some(item => item.responseKey === responseKey)
    ) {
      await this.#retainContinuationAdmissionCleanup(reason);
    }
    let speech: GatewayBatchSpeechClient | null = null;
    const staged = this.#stagedSuccessor;
    if (staged !== null && staged.metadata.responseKey === responseKey) {
      this.#stagedSuccessor = null;
      staged.downlinkRoute?.leaf.close('MEDIA_LOCAL_CLOSE');
      staged.chunks.splice(0);
    }
    for (const [prepared, metadata] of this.#preparedSpeech) {
      if (metadata.responseKey !== responseKey) continue;
      speech = metadata.speech;
      this.#preparedSpeech.delete(prepared);
    }
    if (speech !== null) await speech.fenceSynthesis(response.interaction_id);
    if (this.#continuationResponseKey === responseKey) {
      await this.#releaseContinuationSpeechAuthority('continuation_cancelled');
    }
  }

  async completePreparedResponse(
    response: Readonly<AudioResponseRef>,
  ): Promise<void> {
    const responseKey = l0ResponseKey(response);
    if (
      [...this.#preparedSpeech.values()].some(
        metadata => metadata.responseKey === responseKey,
      )
    ) {
      throw new Error('prepared formal speech remains unconsumed');
    }
    if (this.#continuationResponseKey === responseKey) {
      await this.#releaseContinuationSpeechAuthority('continuation_completed');
    }
  }

  stopAgentPlayout(response: Readonly<AudioResponseRef>): boolean {
    const pending = this.#pendingPlayout;
    if (
      pending === null ||
      pending.response.interaction_id !== response.interaction_id ||
      pending.response.response_id !== response.response_id ||
      pending.response.response_generation !== response.response_generation
    )
      return false;
    this.#pendingPlayout = null;
    const requestedClock = this.#l0Available ? l0ClockNow() : null;
    const stopReceipt = this.#audio.stopPlayoutExact(
      response,
      'formal_product_barge_in'
    );
    if (!stopReceipt.local_fence_established) {
      this.#pendingPlayout = pending;
      return false;
    }
    if (this.#activeContinuationAdmission !== null) {
      this.#status = 'cleanup_pending';
      this.#reason = 'FORMAL_P1_CLEANUP_IN_PROGRESS';
      this.#publish();
      void this.#retainContinuationAdmissionCleanup('FORMAL_PRODUCT_BARGE_IN');
    }
    this.#continuationResponseKey = null;
    if (requestedClock !== null) {
      const confirmedMonotonicMs = stopReceipt.timing.confirmed_at_monotonic_ms;
      const confirmedClock =
        stopReceipt.timing.status === 'confirmed'
        && confirmedMonotonicMs !== null
        && confirmedMonotonicMs >= requestedClock.monotonicMs
          ? Object.freeze({
              observedAt: new Date(
                Date.parse(requestedClock.observedAt)
                + confirmedMonotonicMs
                - requestedClock.monotonicMs,
              ).toISOString(),
              monotonicMs: confirmedMonotonicMs,
            })
          : l0ClockNow();
      this.#l0Record('barge_in', response, undefined, undefined, requestedClock);
      this.#l0Record(
        'fence_cancel_completion',
        response,
        undefined,
        'cancelled',
        confirmedClock,
      );
    }
    pending.downlinkRoute?.leaf.close('MEDIA_LOCAL_CLOSE');
    pending.reject(
      Object.assign(new Error('formal playout was interrupted'), {
        reason: 'FORMAL_PLAYOUT_BARGED',
      })
    );
    return true;
  }

  async close(): Promise<void> {
    if (this.#closed) return;
    if (this.#closePromise !== null) return this.#closePromise;
    // Exit is an owned close: mark it before any route closes so a late
    // transport terminal or staged transition rejection is classified as
    // expected instead of reaching the failure path.
    this.#closeRequested = true;
    this.#preparedSpeech.clear();
    const staged = this.#stagedSuccessor;
    this.#stagedSuccessor = null;
    staged?.downlinkRoute?.leaf.close('MEDIA_LOCAL_CLOSE');
    staged?.chunks.splice(0);
    this.#operationGeneration += 1;
    this.#status = 'cleanup_pending';
    this.#reason = 'FORMAL_P1_CLEANUP_IN_PROGRESS';
    this.#publish();
    const retained = Promise.resolve().then(async () => {
      try {
        await this.#audio.close();
      } catch {
        /* authoritative release retries below */
      }
      const pendingActivation = this.#pendingMediaActivation;
      if (pendingActivation !== null) {
        try {
          await pendingActivation;
        } catch {
          /* no authority was issued or binding is retained */
        }
      }
      if (this.#failureCleanupPromise !== null) {
        try {
          await this.#failureCleanupPromise;
        } catch {
          /* retry below */
        }
      }
      await this.#releaseResources('formal_route_close');
      this.#closed = true;
      this.#setStatus('closed', null);
    })
      .catch(error => {
        this.#reason = 'FORMAL_P1_CLEANUP_PENDING';
        this.#status = 'cleanup_pending';
        this.#publish();
        throw error;
      })
      .finally(() => {
        if (this.#closePromise === retained) this.#closePromise = null;
      });
    this.#closePromise = retained;
    return retained;
  }

  async #prepareConcurrentCapture(
    operationGeneration: number,
    priorAuthority: Readonly<ProductP1MediaCloseBinding>,
    priorSpeech: GatewayBatchSpeechClient,
    response: Readonly<AudioResponseRef>,
  ): Promise<Readonly<{ ready: boolean; reason: string | null }>> {
    try {
      await this.#startConcurrentCapture(operationGeneration);
      this.#requireCurrent(operationGeneration);
      this.#successorCaptureReadiness = 'ready';
      this.#successorCaptureReadinessReason = null;
      this.#successorCaptureReadinessElapsedMs = Math.max(
        0,
        monotonicNowMs() - (this.#successorCaptureReadinessStartedAtMs ?? monotonicNowMs()),
      );
      this.#l0Record('successor_capture_ready', response);
      return Object.freeze({ ready: true, reason: null });
    } catch (error) {
      this.#requireCurrent(operationGeneration);
      const reason = stableFailureReason(error);
      const failureDiagnostic = this.#captureFirstFrameDiagnostic;
      await this.#releaseDegradedConcurrentCapture(
        operationGeneration,
        priorAuthority,
        priorSpeech,
        reason,
      );
      this.#requireCurrent(operationGeneration);
      this.#successorCaptureReadiness = 'degraded';
      this.#successorCaptureReadinessReason = reason;
      this.#successorCaptureReadinessElapsedMs = Math.max(
        0,
        monotonicNowMs() - (this.#successorCaptureReadinessStartedAtMs ?? monotonicNowMs()),
      );
      this.#reason = reason;
      this.#publish();
      const failureObservedAtMs = monotonicNowMs();
      console.warn(
        `live_voice_successor_capture_degradation stage=browser_readiness_failed scope_sha256=${failureDiagnostic?.scope_sha256 ?? 'unavailable'} generation=${failureDiagnostic?.capture_generation ?? 'unavailable'} seq=${failureDiagnostic?.frame_seq ?? 'unavailable'} monotonic_ms=${failureObservedAtMs.toFixed(3)} stage_elapsed_ms=${Math.max(0, failureObservedAtMs - (failureDiagnostic?.monotonic_ms ?? failureObservedAtMs)).toFixed(3)} outcome=failure reason=${reason} elapsed_ms=${Math.round(this.#successorCaptureReadinessElapsedMs)} fallback=no_barge_in visible=true`
      );
      return Object.freeze({ ready: false, reason });
    }
  }

  async #releaseDegradedConcurrentCapture(
    operationGeneration: number,
    priorAuthority: Readonly<ProductP1MediaCloseBinding>,
    priorSpeech: GatewayBatchSpeechClient,
    reason: string,
  ): Promise<void> {
    this.#requireCurrent(operationGeneration);
    const failedRoute = this.#route;
    const failedAuthority = this.#mediaCloseBinding;
    failedRoute?.leaf.close('MEDIA_LOCAL_CLOSE');
    if (this.#route === failedRoute) this.#route = null;
    this.#speech = null;
    this.#captureStopExpected = true;
    try {
      await this.#audio.stopCapture('formal_successor_capture_degraded');
    } finally {
      this.#captureStopExpected = false;
    }
    this.#requireCurrent(operationGeneration);
    if (failedAuthority !== null && failedAuthority.subject_id !== priorAuthority.subject_id) {
      await this.#revokeMediaAuthority(failedAuthority, 'degraded_concurrent_capture');
      this.#requireCurrent(operationGeneration);
    }
    // The TTS downlink and its final receipt remain owned by the predecessor
    // subject. Restore only that authority after the failed successor uplink
    // has been physically stopped and exactly revoked.
    this.#mediaCloseBinding = priorAuthority;
    this.#retainedMediaAuthorities.delete(priorAuthority.subject_id);
    this.#speech = priorSpeech;
    this.#frames = [];
    this.#captureSpeechObserved = false;
    this.#captureProviderSpeechStartObserved = false;
    this.#captureLocalActivityRecencyFrames = 0;
    this.#captureUtteranceStartFrameIndex = null;
    this.#mediaSentFrames = 0;
    this.#captureFirstFrameAcknowledged = false;
    this.#captureFirstFrameDiagnostic = null;
    this.#captureFramesAcked = 0;
    this.#endOfTurnNegotiated = false;
    this.#pendingSpeechStart = null;
    this.#pendingEndOfTurn = null;
    this.#endOfTurnDelivered = false;
    this.#bargeInSpeechStartDelivered = false;
    this.#bargeInEndOfTurnDelivered = false;
    this.#stopAndRecognizePromise = null;
    this.#continuationResponseKey = null;
    this.#reason = reason;
  }

  async #startConcurrentCapture(operationGeneration: number): Promise<void> {
    this.#captureStartupAudioReady = false;
    this.#captureStartupFailure = null;
    this.#mediaTerminalFailure = null;
    this.#captureReadinessPending = true;
    this.#captureReadinessPurpose = 'successor';
    try {
      await this.#startConcurrentCaptureOwned(operationGeneration);
      this.#captureStartupAudioReady = false;
      this.#captureStartupFailure = null;
      this.#mediaTerminalFailure = null;
      this.#captureReadinessPending = false;
      this.#captureReadinessPurpose = null;
    } catch (error) {
      const failure = this.#captureStartupFailure ?? this.#mediaTerminalFailure ?? error;
      this.#captureStartupAudioReady = false;
      this.#captureStartupFailure = null;
      this.#mediaTerminalFailure = null;
      this.#captureReadinessPending = false;
      this.#captureReadinessPurpose = null;
      throw failure;
    }
  }

  async #startConcurrentCaptureOwned(operationGeneration: number): Promise<void> {
    const sessionId = requiredText(this.#sessionId, 'session_id');
    const interactionId = requiredText(this.#interactionId, 'interaction_id');
    const correlationId = requiredText(this.#correlationId, 'correlation_id');
    const activationId = requiredText(this.#activationId, 'activation_id');
    const activationGeneration = this.#activationGeneration;
    const priorAuthority = this.#mediaCloseBinding;
    if (priorAuthority === null || activationGeneration <= 0 || this.#playout === null) {
      throw new Error('concurrent capture authority is unavailable');
    }
    this.#frames = [];
    this.#captureSpeechObserved = false;
    this.#captureProviderSpeechStartObserved = false;
    this.#captureLocalActivityRecencyFrames = 0;
    this.#captureUtteranceStartFrameIndex = null;
    this.#mediaSentFrames = 0;
    this.#captureFirstFrameAcknowledged = false;
    this.#captureFirstFrameDiagnostic = null;
    this.#captureFramesAcked = 0;
    this.#route = null;
    this.#speech = null;
    this.#endOfTurnNegotiated = false;
    this.#pendingSpeechStart = null;
    this.#pendingEndOfTurn = null;
    this.#endOfTurnDelivered = false;
    this.#bargeInSpeechStartDelivered = false;
    this.#bargeInEndOfTurnDelivered = false;
    this.#stopAndRecognizePromise = null;
    if (this.#l0Available) {
      this.#l0CaptureStartedAtMs = monotonicNowMs();
      this.#l0LastFrameSentClock = null;
    }
    const metadata = await this.#audio.startCapture(
      this.#deviceSelection.input_device_id ? { deviceId: this.#deviceSelection.input_device_id } : {}
    );
    this.#captureActualProcessing = metadata.actual_processing;
    this.#captureStartupAudioReady = true;
    this.#requireHealthyCaptureReadiness(operationGeneration);
    if (this.#playout.sample_rate_hz !== metadata.frame_format.sample_rate_hz) {
      throw new Error('concurrent capture and playout sample rates do not match');
    }
    const activationOperation = Promise.resolve().then(async () => {
      const activationValue = await this.#request(PRODUCT_P1_MEDIA_ACTIVATE_METHOD, {
        session_id: sessionId,
        interaction_id: interactionId,
        correlation_id: correlationId,
        activation_id: activationId,
        activation_generation: activationGeneration,
        capture_id: metadata.capture_id,
        capture_generation: metadata.capture_generation,
        track_id: metadata.track_id,
        sample_rate_hz: metadata.frame_format.sample_rate_hz,
        locale: this.#locale,
        end_of_turn_capability: MEDIA_END_OF_TURN_CAPABILITY,
      });
      const activation = exactMediaActivation(activationValue);
      if (activation.status !== 'active' || activation.subprotocol !== 'live-voice.media.v1') {
        throw routeUnavailable(activation.reason_id);
      }
      const subjectId = requiredText(activation.subject_id, 'subject_id');
      this.#retainedMediaAuthorities.set(priorAuthority.subject_id, priorAuthority);
      this.#mediaCloseBinding = Object.freeze({
        session_id: sessionId,
        subject_id: subjectId,
        correlation_id: correlationId,
        interaction_id: interactionId,
        activation_id: activationId,
        activation_generation: activationGeneration,
      });
      const privacy = exactObject(activation.privacy, ['raw_audio_persisted', 'raw_audio_logged', 'memory_only'], 'media_activation.privacy');
      if (privacy.raw_audio_persisted !== false || privacy.raw_audio_logged !== false || privacy.memory_only !== true)
        throw new Error('concurrent media activation did not prove its privacy boundary');
      this.#observeStreamingAvailability(activation);
      this.#observeEndOfTurnAvailability(activation);
      return Object.freeze({ activation, subjectId });
    });
    this.#pendingMediaActivation = activationOperation;
    let activated: Readonly<{ activation: Record<string, unknown>; subjectId: string }>;
    try {
      activated = await activationOperation;
    } finally {
      if (this.#pendingMediaActivation === activationOperation) this.#pendingMediaActivation = null;
    }
    const { activation, subjectId } = activated;
    this.#requireHealthyCaptureReadiness(operationGeneration);
    const attach = deserializeMediaControl(
      JSON.stringify({
        type: 'media.attach',
        contract_version: 'live-voice.media.v1',
        binding: activation.binding,
      })
    );
    if (
      attach.type !== 'media.attach' ||
      attach.binding.session_id !== sessionId ||
      attach.binding.interaction_id !== interactionId ||
      attach.binding.correlation_id !== correlationId ||
      attach.binding.track_id !== metadata.track_id ||
      attach.binding.generation.kind !== 'capture' ||
      attach.binding.generation.id !== metadata.capture_id ||
      attach.binding.generation.value !== metadata.capture_generation ||
      attach.binding.frame_format.sample_rate_hz !== metadata.frame_format.sample_rate_hz
    )
      throw new Error('concurrent server media binding does not match browser capture');
    let ownedRoute: ActiveBrowserDedicatedMediaRoute | null = null;
    let mediaTicket = consumePrivateText(activation, 'media_ticket', 'media_ticket');
    let route: BrowserDedicatedMediaRouteActivation;
    try {
      route = createBrowserDedicatedMediaRoute({
        enabled: true,
        expected_origin: this.#origin,
        endpoint_url: mediaEndpoint(this.#origin, requiredText(activation.endpoint_path, 'endpoint_path')),
        media_ticket: mediaTicket,
        binding: attach.binding,
        provider_available: true,
        transport_available: true,
        socket_factory: this.#socketFactory,
        on_audio_frame: () => undefined,
        ...(this.#l0Available
          ? {
              on_uplink_frame_sent: (seq: number) => {
                if (ownedRoute !== null) this.#observeUplinkFrameSent(ownedRoute, seq);
              },
            }
          : {}),
        on_uplink_frame_acknowledged: (throughSeq: number) => {
          if (ownedRoute !== null) this.#observeUplinkFrameAcknowledged(ownedRoute, throughSeq);
        },
        on_first_frame_diagnostic: (fact: Readonly<MediaFirstFrameDiagnostic>) => {
          if (ownedRoute !== null) this.#observeFirstFrameDiagnostic(ownedRoute, fact);
        },
        on_terminal: event => {
          if (ownedRoute !== null) this.#observeMediaTerminal(ownedRoute, event);
        },
        ...(this.#endOfTurnNegotiated
          ? {
              end_of_turn_capability: MEDIA_END_OF_TURN_CAPABILITY,
              on_speech_start: (event: Readonly<MediaSpeechStart>) => {
                this.#observeSpeechStartControl(operationGeneration, ownedRoute, event);
              },
              on_end_of_turn: (event: Readonly<MediaEndOfTurn>) => {
                this.#observeEndOfTurnControl(operationGeneration, ownedRoute, event);
              },
            }
          : {}),
      });
    } finally {
      mediaTicket = '';
    }
    if (!route.active) throw new Error(route.reason_id);
    ownedRoute = route;
    this.#route = route;
    this.#speech = new GatewayBatchSpeechClient({
      enabled: true,
      transport: {
        request: async <T = unknown>(
          method: string,
          params?: Record<string, unknown>,
          options?: Readonly<{ timeoutMs?: number; signal?: AbortSignal }>,
        ) => (await this.#request(method, params ?? {}, options)) as T,
      },
      scope: {
        subject_id: subjectId,
        project_id: null,
        session_id: sessionId,
        assurance: 'authenticated',
      },
    });
    await this.#awaitCaptureReadiness(route, operationGeneration);
    this.#requireCurrent(operationGeneration);
    this.#onConcurrentCaptureStarted?.();
  }

  async #rotateConcurrentCapture(operationGeneration: number): Promise<void> {
    const route = this.#route;
    const priorAuthority = this.#mediaCloseBinding;
    if (route === null || priorAuthority === null) {
      throw Object.assign(new Error('formal overlap capture rotation lost authority'), {
        reason: 'FORMAL_OVERLAP_CAPTURE_ROTATION_UNAVAILABLE',
      });
    }
    const requireSafeRotation = (): void => {
      this.#requireCurrent(operationGeneration);
      if (this.#captureProviderSpeechStartObserved) {
        throw Object.assign(new Error('formal overlap capture observed speech before rotation settled'), {
          reason: PRODUCT_P1_CAPTURE_DURATION_EXCEEDED_REASON,
        });
      }
      if (
        route !== this.#route
        || (this.#pendingPlayout ?? this.#settlingPlayout) === null
        || this.#status !== 'playing'
      ) {
        throw Object.assign(new Error('formal overlap capture rotation lost authority'), {
          reason: 'FORMAL_OVERLAP_CAPTURE_ROTATION_UNAVAILABLE',
        });
      }
    };
    requireSafeRotation();
    this.#captureStopExpected = true;
    try {
      await this.#audio.stopCapture('formal_overlap_capture_rotation');
    } finally {
      this.#captureStopExpected = false;
    }
    requireSafeRotation();
    this.#drainCaptureFrames();
    const deadline = Date.now() + ROUTE_DRAIN_TIMEOUT_MS;
    let pending = route.leaf.flush();
    while ((this.#mediaSentFrames !== this.#frames.length || pending.pending_frames !== 0) && !route.leaf.closed && Date.now() < deadline) {
      await waitTurn();
      requireSafeRotation();
      this.#drainCaptureFrames();
      pending = route.leaf.flush();
    }
    if (this.#mediaSentFrames !== this.#frames.length || pending.pending_frames !== 0) {
      throw Object.assign(new Error('formal overlap capture did not drain before rotation'), {
        reason: 'FORMAL_OVERLAP_CAPTURE_ROTATION_DRAIN_FAILED',
      });
    }
    await awaitRouteCompletion(route.leaf.completeUplink('MEDIA_LOCAL_CLOSE'));
    requireSafeRotation();
    this.#frames = [];
    this.#captureSpeechObserved = false;
    this.#captureProviderSpeechStartObserved = false;
    this.#captureLocalActivityRecencyFrames = 0;
    this.#captureUtteranceStartFrameIndex = null;
    this.#mediaSentFrames = 0;
    this.#captureFirstFrameAcknowledged = false;
    this.#captureFirstFrameDiagnostic = null;
    this.#captureFramesAcked = 0;
    if (this.#route === route) this.#route = null;
    this.#speech = null;
    await this.#startConcurrentCapture(operationGeneration);
    this.#requireCurrent(operationGeneration);
    await this.#revokeMediaAuthority(priorAuthority, 'overlap_capture_rotation');
    this.#requireCurrent(operationGeneration);
  }

  async #rotateIdleCapture(operationGeneration: number): Promise<void> {
    const route = this.#route;
    const priorAuthority = this.#mediaCloseBinding;
    if (route === null || priorAuthority === null) {
      throw Object.assign(new Error('formal idle capture rotation lost authority'), {
        reason: 'FORMAL_IDLE_CAPTURE_ROTATION_UNAVAILABLE',
      });
    }
    const requireSafeRotation = (): void => {
      this.#requireCurrent(operationGeneration);
      if (this.#captureProviderSpeechStartObserved) {
        throw Object.assign(new Error('formal idle capture observed speech before rotation settled'), {
          reason: PRODUCT_P1_CAPTURE_DURATION_EXCEEDED_REASON,
        });
      }
      // Local energy is a decaying hint that was already weighed when this
      // rotation was dispatched; re-checking it here would turn one late echo
      // frame into a visible rotation failure. The provider speech-start check
      // above remains the only authoritative mid-rotation abort.
      if (route !== this.#route || this.#status !== 'capturing') {
        throw Object.assign(new Error('formal idle capture rotation lost authority'), {
          reason: 'FORMAL_IDLE_CAPTURE_ROTATION_UNAVAILABLE',
        });
      }
    };
    requireSafeRotation();
    this.#captureStopExpected = true;
    try {
      await this.#audio.stopCapture('formal_idle_capture_rotation');
    } finally {
      this.#captureStopExpected = false;
    }
    requireSafeRotation();
    this.#drainCaptureFrames();
    const deadline = Date.now() + ROUTE_DRAIN_TIMEOUT_MS;
    let pending = route.leaf.flush();
    while ((this.#mediaSentFrames !== this.#frames.length || pending.pending_frames !== 0) && !route.leaf.closed && Date.now() < deadline) {
      await waitTurn();
      requireSafeRotation();
      this.#drainCaptureFrames();
      pending = route.leaf.flush();
    }
    if (this.#mediaSentFrames !== this.#frames.length || pending.pending_frames !== 0) {
      throw Object.assign(new Error('formal idle capture did not drain before rotation'), {
        reason: 'FORMAL_IDLE_CAPTURE_ROTATION_DRAIN_FAILED',
      });
    }
    await awaitRouteCompletion(route.leaf.completeUplink('MEDIA_LOCAL_CLOSE'));
    requireSafeRotation();
    this.#frames = [];
    this.#captureSpeechObserved = false;
    this.#captureProviderSpeechStartObserved = false;
    this.#captureLocalActivityRecencyFrames = 0;
    this.#captureUtteranceStartFrameIndex = null;
    this.#mediaSentFrames = 0;
    this.#captureFirstFrameAcknowledged = false;
    this.#captureFirstFrameDiagnostic = null;
    this.#captureFramesAcked = 0;
    if (this.#route === route) this.#route = null;
    this.#speech = null;
    await this.#startConcurrentCapture(operationGeneration);
    this.#requireCurrent(operationGeneration);
    await this.#revokeMediaAuthority(priorAuthority, 'idle_capture_rotation');
    this.#requireCurrent(operationGeneration);
    this.#setStatus('capturing', this.#streamingFallbackReason);
    this.#deliverEndOfTurn(this.#operationGeneration, this.#route);
  }

  #openDownlinkRoute(
    downlink: Readonly<FormalSynthesisDownlink>,
    provider: Readonly<GatewaySpeechProvider>,
    response: Readonly<AudioResponseRef>,
    unitId: string,
    unitSeq: number,
    onAttached: () => void,
    onFrame: (frame: Readonly<MediaAudioFrame>) => void,
    onTerminal: (event: Readonly<DedicatedMediaTerminalEvent>) => void
  ): ActiveBrowserDedicatedMediaRoute {
    const mediaTicket = downlink.take_media_ticket();
    const attach = deserializeMediaControl(
      JSON.stringify({
        type: 'media.attach',
        contract_version: 'live-voice.media.v1',
        binding: downlink.binding,
      })
    );
    if (
      attach.type !== 'media.attach' ||
      attach.binding.direction !== 'downlink' ||
      attach.binding.session_id !== this.#sessionId ||
      attach.binding.interaction_id !== response.interaction_id ||
      attach.binding.correlation_id !== this.#correlationId ||
      attach.binding.generation.kind !== 'response' ||
      attach.binding.generation.id !== response.response_id ||
      attach.binding.generation.value !== response.response_generation ||
      attach.binding.playout?.response_id !== response.response_id ||
      attach.binding.playout.response_generation !== response.response_generation ||
      attach.binding.playout.unit_id !== unitId ||
      attach.binding.frame_format.sample_rate_hz !== downlink.sample_rate_hz ||
      downlink.subprotocol !== 'live-voice.media.v1'
    )
      throw new Error('dedicated media downlink binding mismatch');
    // Provider is checked by the Speech client and carried into every browser
    // audio chunk; reading it here keeps the downlink composition explicit.
    requiredText(provider.provider_id, 'provider.provider_id');
    const route = createBrowserDedicatedMediaRoute({
      enabled: true,
      expected_origin: this.#origin,
      endpoint_url: mediaEndpoint(this.#origin, downlink.endpoint_path),
      media_ticket: mediaTicket,
      binding: attach.binding,
      provider_available: true,
      transport_available: true,
      socket_factory: this.#socketFactory,
      on_attached: onAttached,
      on_audio_frame: onFrame,
      on_terminal: onTerminal,
      max_pending_frames: downlink.max_pending_frames,
      max_pending_bytes: downlink.max_pending_bytes,
      defer_downlink_ack: true,
      ...(downlink.prefetch_promotion_capability === null
        ? {}
        : {
            prefetch_promotion_capability: downlink.prefetch_promotion_capability,
            unit_seq: unitSeq,
          }),
    });
    if (!route.active) throw new Error(route.reason_id);
    return route;
  }

  #acceptDownlinkFrame(pending: PendingProductPlayout, frame: Readonly<MediaAudioFrame>, provider: Readonly<GatewaySpeechProvider>): void {
    if (
      this.#failureCleanupPromise !== null ||
      this.#pendingPlayout !== pending ||
      frame.seq !== pending.chunks.length ||
      frame.seq >= (pending.frameCount ?? MAX_STREAMING_PLAYOUT_FRAMES)
    )
      throw new Error('dedicated media downlink frame is stale or non-contiguous');
    if (this.#l0Available && frame.seq === 0) {
      this.#observeBrowserFirstFrame(pending.response, frame.seq);
      this.#l0Record(
        'unit_first_pcm',
        pending.response,
        undefined,
        undefined,
        undefined,
        pending.unitSeq,
        pending.unitId,
      );
    }
    pending.chunks.push(
      Object.freeze({
        response: pending.response,
        unit_id: pending.unitId,
        seq: frame.seq,
        sample_rate_hz: pending.downlinkRoute!.binding.frame_format.sample_rate_hz,
        channel_count: 1,
        samples: Float32Array.from(frame.samples),
        provider,
      })
    );
    if (frame.seq === 0 || frame.seq % 50 === 0) {
      reportBrowserC019PlayoutDiagnostic('info', {
        event: 'browser_downlink_frame_received',
        response_generation: pending.response.response_generation,
        unit_seq: pending.unitSeq,
        frame_seq: frame.seq,
        received_frames: pending.chunks.length,
        scheduled_frames: pending.nextChunkIndex,
        rendered_frames: pending.renderedChunks,
        unscheduled_frames: pending.chunks.length - pending.nextChunkIndex,
      });
    }
    this.#fillPlayoutQueue(pending);
  }

  #fillPlayoutQueue(pending: PendingProductPlayout): void {
    if (pending.filling || this.#failureCleanupPromise !== null || this.#pendingPlayout !== pending) return;
    pending.filling = true;
    const scheduledFrom = pending.nextChunkIndex;
    try {
      while (pending.nextChunkIndex < pending.chunks.length && pending.nextChunkIndex - pending.renderedChunks < PRODUCT_P1_PLAYOUT_QUEUE_CAPACITY) {
        const chunk = pending.chunks[pending.nextChunkIndex];
        if (this.#l0Available && chunk.seq === 0) {
          this.#observeBrowserFirstFrame(pending.response, chunk.seq);
        }
        pending.nextChunkIndex += 1;
        const depthAfterEnqueue = pending.nextChunkIndex - pending.renderedChunks;
        if (!this.#audio.enqueuePlayout(chunk)) {
          pending.nextChunkIndex -= 1;
          throw new Error('browser playout rejected a formal chunk');
        }
        // Product `playing` is a claim about browser-owned scheduled audio,
        // not about completed Agent text or an allocated TTS descriptor.
        if (this.#status !== 'playing') {
          this.#setStatus('playing', this.#successorCaptureReadinessReason ?? pending.degradationReason);
        }
        // Media ACK is the bounded transport-pressure signal. The separate
        // media.playout_receipt below remains the authoritative proof that the
        // exact chunks actually rendered. Waiting for each 20 ms source to
        // finish before its ACK forced a network round trip between adjacent
        // frames and made otherwise clean Provider PCM sound broken.
        if (
          pending.downlinkRoute !== null
          && chunk.seq > pending.transportAcknowledgedThrough
        ) this.#scheduleDownlinkAck(pending, chunk.seq);
        pending.peakDepth = Math.max(pending.peakDepth, depthAfterEnqueue);
      }
    } finally {
      pending.filling = false;
    }
    const scheduledThrough = pending.nextChunkIndex - 1;
    if (
      scheduledThrough >= scheduledFrom
      && (scheduledFrom === 0 || scheduledThrough % 50 === 0)
    ) {
      reportBrowserC019PlayoutDiagnostic('info', {
        event: 'browser_playout_queue_filled',
        response_generation: pending.response.response_generation,
        unit_seq: pending.unitSeq,
        scheduled_from_seq: scheduledFrom,
        scheduled_through_seq: scheduledThrough,
        received_frames: pending.chunks.length,
        scheduled_frames: pending.nextChunkIndex,
        rendered_frames: pending.renderedChunks,
        queue_depth: pending.nextChunkIndex - pending.renderedChunks,
        peak_depth: pending.peakDepth,
      });
    }
  }

  async #acknowledgePlayout(pending: PendingProductPlayout): Promise<void> {
    const authority = pending.receiptAuthority;
    const throughSeq = pending.expected.get(pending.unitId);
    if (
      pending.captureFramesAcked <= 0 ||
      pending.chunks.length <= 0 ||
      throughSeq === undefined ||
      pending.expected.size !== 1 ||
      pending.renderedChunks !== pending.chunks.length ||
      pending.peakDepth <= 0 ||
      pending.peakDepth > PRODUCT_P1_PLAYOUT_QUEUE_CAPACITY
    )
      throw new Error('formal browser playout receipt is incomplete');
    const receipt = exactObject(
      await this.#request(PRODUCT_P1_MEDIA_PLAYOUT_RECEIPT_METHOD, {
        session_id: authority.session_id,
        subject_id: authority.subject_id,
        correlation_id: authority.correlation_id,
        interaction_id: pending.response.interaction_id,
        response_id: pending.response.response_id,
        response_generation: pending.response.response_generation,
        unit_id: pending.unitId,
        capture_frames_acked: pending.captureFramesAcked,
        rendered_chunks: pending.renderedChunks,
        rendered_through_seq: throughSeq,
        playout_queue_capacity: PRODUCT_P1_PLAYOUT_QUEUE_CAPACITY,
        playout_peak_depth: pending.peakDepth,
        capture_control_ack: 'capture_flush_acked',
        playout_state: 'render_completed',
      }),
      [
        'status',
        'reason_id',
        'receipt_id',
        'session_id',
        'subject_id',
        'correlation_id',
        'interaction_id',
        'response_id',
        'response_generation',
        'unit_id',
        'capture_frames_acked',
        'rendered_chunks',
        'rendered_through_seq',
        'playout_queue_capacity',
        'playout_peak_depth',
        'capture_control_ack',
        'playout_state',
        'duplex_media_observed',
      ],
      'media_playout_receipt'
    );
    if (
      receipt.status !== 'media_playout_acknowledged' ||
      receipt.reason_id !== 'MEDIA_PLAYOUT_RECEIPT_ACCEPTED' ||
      typeof receipt.receipt_id !== 'string' ||
      receipt.session_id !== authority.session_id ||
      receipt.subject_id !== authority.subject_id ||
      receipt.correlation_id !== authority.correlation_id ||
      receipt.interaction_id !== pending.response.interaction_id ||
      receipt.response_id !== pending.response.response_id ||
      receipt.response_generation !== pending.response.response_generation ||
      receipt.unit_id !== pending.unitId ||
      receipt.capture_frames_acked !== pending.captureFramesAcked ||
      receipt.rendered_chunks !== pending.renderedChunks ||
      receipt.rendered_through_seq !== throughSeq ||
      receipt.playout_queue_capacity !== PRODUCT_P1_PLAYOUT_QUEUE_CAPACITY ||
      receipt.playout_peak_depth !== pending.peakDepth ||
      receipt.capture_control_ack !== 'capture_flush_acked' ||
      receipt.playout_state !== 'render_completed' ||
      typeof receipt.duplex_media_observed !== 'boolean'
    )
      throw new Error('media playout receipt binding mismatch');
  }

  #scheduleDownlinkAck(pending: PendingProductPlayout, throughSeq: number): void {
    // The media receiver publishes its frame callback before it retains the
    // corresponding deferred ACK. Cross that re-entrant boundary by one
    // microtask, then acknowledge the exact frame that is already scheduled in
    // Web Audio. Render completion remains separately observed below.
    Promise.resolve().then(() => {
      const route = pending.downlinkRoute;
      if (
        route === null ||
        this.#closed ||
        this.#closeRequested ||
        this.#failureCleanupPromise !== null ||
        (this.#pendingPlayout !== pending && this.#settlingPlayout !== pending)
      )
        return;
      try {
        route.leaf.acknowledgeDownlinkThrough(throughSeq);
      } catch (error) {
        if (this.#pendingPlayout === pending) this.#pendingPlayout = null;
        route.leaf.close('MEDIA_TRANSPORT_PROTOCOL_ERROR');
        this.#audio.stopPlayout(pending.response, 'formal_downlink_ack_failed');
        pending.reject(error instanceof Error ? error : new Error('formal downlink ACK failed'));
      }
    });
  }

  #stagedTransitionSuperseded(staged: StagedProductSuccessor): boolean {
    // A staged slot released by an owned local close (Stop, barge-in, Exit)
    // or replaced by promotion no longer owns transport failure authority.
    return this.#stagedSuccessor !== staged || this.#closeRequested || this.#closed;
  }

  #scheduleStagedDownlinkAck(staged: StagedProductSuccessor, throughSeq: number): void {
    // A staged frame has no WebAudio owner yet. After it is retained in the
    // bounded reserve, release only the exact sender window; rendering and
    // presentation truth remain unavailable until promotion and playout.
    Promise.resolve().then(() => {
      const route = staged.downlinkRoute;
      if (
        route === null
        || this.#closed
        || this.#closeRequested
        || this.#failureCleanupPromise !== null
        || this.#stagedSuccessor !== staged
        || staged.promoted
      )
        return;
      try {
        route.leaf.acknowledgeDownlinkThrough(throughSeq);
        staged.transportAcknowledgedThrough = throughSeq;
        if (
          staged.metadata.result.downlink?.prefetch_promotion_capability !== null
          && throughSeq === STAGED_SUCCESSOR_RESERVE_TARGET_MS / LIVE_VOICE_AUDIO_FRAME_DURATION_MS - 1
          && staged.transitionPromise === null
        ) {
          console.info('[LiveVoiceC019] transition diagnostic', {
            event: 'browser_product_park_requested',
            response_generation: staged.prepared.response.response_generation,
            unit_seq: staged.prepared.unitSeq,
            retained_through_seq: throughSeq,
          });
          this.#l0Record(
            'successor_park_requested',
            staged.prepared.response,
            undefined, undefined, undefined,
            staged.prepared.unitSeq,
            staged.prepared.unitId,
          );
          staged.transitionPromise = route.leaf.parkPrefetch(throughSeq).then(() => {
            if (this.#stagedSuccessor === staged && !staged.promoted) {
              staged.parked = true;
              console.info('[LiveVoiceC019] transition diagnostic', {
                event: 'browser_product_park_acknowledged',
                response_generation: staged.prepared.response.response_generation,
                unit_seq: staged.prepared.unitSeq,
                retained_through_seq: throughSeq,
              });
              this.#l0Record(
                'successor_parked',
                staged.prepared.response,
                undefined, undefined, undefined,
                staged.prepared.unitSeq,
                staged.prepared.unitId,
              );
            }
          });
          void staged.transitionPromise.catch(error => {
            if (this.#stagedTransitionSuperseded(staged)) {
              // Stop, barge-in, Exit or promotion already released this
              // staged slot and closed its route locally. The rejected PARK
              // acknowledgement is that expected local close, not a failure.
              console.info('[LiveVoiceC019] transition diagnostic', {
                event: 'browser_product_park_superseded',
                response_generation: staged.prepared.response.response_generation,
                unit_seq: staged.prepared.unitSeq,
              });
              return;
            }
            console.warn('[LiveVoiceC019] transition diagnostic', {
              event: 'browser_product_park_failed',
              response_generation: staged.prepared.response.response_generation,
              unit_seq: staged.prepared.unitSeq,
            });
            this.#stagedSuccessor = null;
            void this.#fail(error instanceof Error ? error : new Error('staged PARK failed'));
          });
        }
      } catch (error) {
        if (this.#stagedTransitionSuperseded(staged)) return;
        this.#stagedSuccessor = null;
        route.leaf.close('MEDIA_TRANSPORT_PROTOCOL_ERROR');
        void this.#fail(error instanceof Error ? error : new Error('staged transport ACK failed'));
      }
    });
  }

  #observePlayout(event: Readonly<BrowserAudioPlayoutEvent>): void {
    const pending = this.#pendingPlayout;
    const deviceFailure =
      event.state === 'failed' && ['audio_output_selection_lost', 'audio_output_selection_unverified'].includes(event.reason)
        ? stableCaptureStopReason(event.reason)
        : null;
    if (deviceFailure !== null && this.#failureCleanupPromise === null && !this.#closed && !this.#closeRequested) {
      const failure = Object.assign(new Error('formal browser output selection failed'), { reason: deviceFailure });
      if (pending !== null) {
        this.#pendingPlayout = null;
        pending.reject(failure);
      }
      if (
        this.#captureReadinessPending
        && this.#captureReadinessPurpose === 'initial'
        && this.#status === 'starting'
      ) {
        this.#captureStartupFailure ??= failure;
        this.#reason = this.#captureStartupFailure.reason;
        this.#status = 'cleanup_pending';
        void this.#audio.close().catch(() => undefined);
        this.#publish();
        return;
      }
      void this.#fail(failure);
      return;
    }
    if (pending === null) return;
    if (
      event.response !== null &&
      (event.response.interaction_id !== pending.response.interaction_id ||
        event.response.response_id !== pending.response.response_id ||
        event.response.response_generation !== pending.response.response_generation)
    ) {
      this.#l0Record('discarded_work', pending.response);
      return;
    }
    if (event.state === 'failed' || event.state === 'stopped' || event.state === 'closed') {
      this.#pendingPlayout = null;
      pending.reject(
        Object.assign(new Error('formal browser playout failed'), {
          reason:
            event.reason.startsWith('page_hidden')
              ? 'PAGE_HIDDEN_PLAYOUT_FENCED'
              : stableCaptureStopReason(event.reason) === 'AUDIO_CAPTURE_STOPPED'
                ? 'FORMAL_PLAYOUT_FAILED'
                : stableCaptureStopReason(event.reason),
        })
      );
      return;
    }
    if (event.state !== 'playing' || event.reason !== 'render_completed' || event.unit_id === null || event.through_seq === null) return;
    if (this.#l0Available) {
      const renderMonotonicMs = monotonicNowMs();
      const priorRenderedClock = pending.lastRenderedClock;
      if (
        event.unit_id === pending.unitId
        && (priorRenderedClock === null || event.through_seq >= priorRenderedClock.throughSeq)
      ) {
        pending.lastRenderedClock = Object.freeze({
          unitId: event.unit_id,
          throughSeq: event.through_seq,
          observedAt: new Date().toISOString(),
          monotonicMs: renderMonotonicMs,
        });
      }
    }
    pending.observed.set(event.unit_id, Math.max(pending.observed.get(event.unit_id) ?? -1, event.through_seq));
    pending.renderedChunks = pending.frameCount === null
      ? Math.max(0, (pending.observed.get(pending.unitId) ?? -1) + 1)
      : [...pending.expected].reduce(
          (count, [unitId, finalSeq]) => count + Math.max(0, Math.min(finalSeq, pending.observed.get(unitId) ?? -1) + 1),
          0
        );
    if (event.through_seq === 0 || event.through_seq % 50 === 0) {
      reportBrowserC019PlayoutDiagnostic('info', {
        event: 'browser_playout_render_advanced',
        response_generation: pending.response.response_generation,
        unit_seq: pending.unitSeq,
        rendered_through_seq: event.through_seq,
        received_frames: pending.chunks.length,
        scheduled_frames: pending.nextChunkIndex,
        rendered_frames: pending.renderedChunks,
        queue_depth: pending.nextChunkIndex - pending.renderedChunks,
        peak_depth: pending.peakDepth,
      });
    }
    try {
      this.#fillPlayoutQueue(pending);
    } catch (error) {
      this.#pendingPlayout = null;
      this.#audio.stopPlayout(pending.response, 'formal_playout_queue_failed');
      pending.reject(error instanceof Error ? error : new Error('formal playout queue failed'));
      return;
    }
    if (pending.expected.size === 1 && [...pending.expected].every(([unitId, seq]) => (pending.observed.get(unitId) ?? -1) >= seq) && pending.nextChunkIndex === pending.chunks.length) {
      this.#stageL0PlayoutCompletion(pending.response, pending.lastRenderedClock);
      this.#pendingPlayout = null;
      this.#settlingPlayout = pending;
      pending.resolve();
    }
  }

  #stageL0PlayoutCompletion(
    response: Readonly<AudioResponseRef>,
    renderClock: Readonly<{ observedAt: string; monotonicMs: number }> | null = null,
  ): void {
    if (!this.#l0Available) return;
    const responseKey = l0ResponseKey(response);
    if (
      this.#l0PlayoutCompleted !== null
      || this.#l0PlayoutStartedAtMs === null
      || this.#l0PlayoutResponseKey !== responseKey
    ) return;
    const monotonicMs = renderClock?.monotonicMs ?? monotonicNowMs();
    const elapsedMs = monotonicMs - this.#l0PlayoutStartedAtMs;
    if (elapsedMs < 0) return;
    this.#l0PlayoutCompleted = Object.freeze({
      responseKey,
      observedAt: renderClock?.observedAt ?? new Date().toISOString(),
      monotonicMs,
      elapsedMs,
    });
  }

  #currentL0PlayoutCompletion(): Readonly<{
    responseKey: string;
    observedAt: string;
    monotonicMs: number;
    elapsedMs: number;
  }> | null {
    return this.#l0PlayoutCompleted;
  }

  #observeBrowserFirstFrame(response: Readonly<AudioResponseRef>, seq: number): void {
    if (!this.#l0Available || seq !== 0) return;
    const key = l0ResponseKey(response);
    if (this.#l0FirstFrameResponseKey === key) return;
    if (this.#l0Record('browser_first_frame', response)) {
      this.#l0FirstFrameResponseKey = key;
    }
  }

  #observePlayoutScheduled(event: Readonly<BrowserAudioPlayoutScheduledEvent>): void {
    if (!this.#l0Available || event.seq !== 0) return;
    const key = l0ResponseKey(event.response);
    if (this.#l0ScheduledResponseKey === key) return;
    if (!this.#l0Record('webaudio_first_frame_scheduled', event.response)) return;
    this.#l0ScheduledResponseKey = key;
    if (!browserL0Enabled()) return;
    const delay = Math.max(0, Math.ceil(event.start_delay_ms));
    const confirmStarted = (retriesRemaining: number): void => {
      if (
        this.#l0ScheduledResponseKey !== key
        || this.#l0PlayoutResponseKey !== key
      ) return;
      if (!event.has_started()) {
        if (retriesRemaining > 0) {
          globalThis.setTimeout(
            () => confirmStarted(retriesRemaining - 1),
            1,
          );
        }
        return;
      }
      const clock = event.scheduled_start_clock;
      this.#l0Record(
        'webaudio_actually_started',
        event.response,
        undefined,
        undefined,
        clock === null
          ? undefined
          : Object.freeze({
              observedAt: clock.observed_at,
              monotonicMs: clock.monotonic_ms,
            }),
      );
      const pending = this.#pendingPlayout ?? this.#settlingPlayout;
      if (pending !== null && l0ResponseKey(pending.response) === key) {
        this.#l0Record(
          'unit_playout_started',
          pending.response,
          undefined,
          undefined,
          clock === null
            ? undefined
            : Object.freeze({
                observedAt: clock.observed_at,
                monotonicMs: clock.monotonic_ms,
              }),
          pending.unitSeq,
          pending.unitId,
        );
      }
    };
    globalThis.setTimeout(
      () => confirmStarted(L0_WEBAUDIO_START_CONFIRMATION_RETRIES),
      delay,
    );
  }

  #observeMediaTerminal(route: ActiveBrowserDedicatedMediaRoute, event: Readonly<DedicatedMediaTerminalEvent>): void {
    if (event.source === 'local_close' || this.#closed || this.#closeRequested || this.#failureCleanupPromise !== null) return;
    const pending = this.#pendingPlayout ?? this.#settlingPlayout;
    if (this.#route !== route && pending?.downlinkRoute !== route) return;
    if (event.source === 'expected_completion') {
      if (event.direction === 'uplink') return;
      if (
        pending?.downlinkRoute === route
        && pending.frameCount === null
        && pending.chunks.length > 0
        && pending.chunks.length <= MAX_STREAMING_PLAYOUT_FRAMES
      ) {
        const finalSeq = pending.chunks.length - 1;
        pending.expected.set(pending.unitId, finalSeq);
        if (
          pending.nextChunkIndex === pending.chunks.length
          && pending.renderedChunks === pending.chunks.length
          && (pending.observed.get(pending.unitId) ?? -1) >= finalSeq
        ) {
          if (this.#pendingPlayout === pending) {
            const renderClock = pending.lastRenderedClock;
            if (
              renderClock !== null
              && renderClock.unitId === pending.unitId
              && renderClock.throughSeq >= finalSeq
            ) this.#stageL0PlayoutCompletion(pending.response, renderClock);
            this.#pendingPlayout = null;
            this.#settlingPlayout = pending;
            pending.resolve();
          }
        }
        // Transport completion may precede browser rendering because media ACK
        // now means safely scheduled, not physically rendered. Keep the exact
        // final cursor and let onended observations drive the product receipt.
        return;
      }
      const finalSeq = pending?.expected.get(pending.unitId);
      if (
        pending?.downlinkRoute === route &&
        pending.expected.size === 1 &&
        pending.frameCount !== null &&
        pending.frameCount > 0 &&
        finalSeq === pending.frameCount - 1 &&
        pending.chunks.length === pending.frameCount &&
        (
          pending.transportAcknowledgedThrough === finalSeq
          || pending.nextChunkIndex === pending.frameCount
        )
      )
        return;
      void this.#fail(
        Object.assign(new Error('formal dedicated media downlink completed before every declared frame rendered'), {
          reason: 'MEDIA_TRANSPORT_PROTOCOL_ERROR',
        })
      );
      return;
    }
    if (this.#captureReadinessPending && this.#route === route) {
      this.#mediaTerminalFailure ??= Object.assign(new Error('formal dedicated media route closed before capture readiness'), {
        reason: 'AUDIO_CAPTURE_MEDIA_ROUTE_CLOSED',
      });
      return;
    }
    void this.#fail(
      Object.assign(new Error('formal dedicated media route terminated unexpectedly'), {
        reason: event.reason_id,
      })
    );
  }

  #mediaAuthorityRole(binding: Readonly<ProductP1MediaCloseBinding>): ProductP1MediaAuthorityRole {
    if (this.#mediaCloseBinding?.subject_id === binding.subject_id) return 'current';
    if (this.#continuationReceiptAuthority?.subject_id === binding.subject_id) return 'continuation';
    if (this.#retainedMediaAuthorities.has(binding.subject_id)) return 'retained';
    return 'foreign';
  }

  async #revokeMediaAuthority(
    binding: Readonly<ProductP1MediaCloseBinding>,
    caller: ProductP1MediaAuthorityRevokeCaller,
    role: ProductP1MediaAuthorityRole = this.#mediaAuthorityRole(binding),
  ): Promise<void> {
    // Content-free: no subject, ticket, text or audio; only the closed caller
    // label, the binding's role for this owner and the owner's own truth.
    console.info('[LiveVoiceC019] transition diagnostic', {
      event: PRODUCT_P1_MEDIA_AUTHORITY_REVOKE_EVENT,
      caller,
      binding_role: role,
      status: this.#status,
      operation_generation: this.#operationGeneration,
      activation_generation: binding.activation_generation,
      capture_route_attached: this.#route !== null,
      continuation_pending: this.#continuationResponseKey !== null,
    });
    const value = exactObject(
      await this.#request(PRODUCT_P1_MEDIA_CLOSE_METHOD, { ...binding }),
      ['status', 'reason_id', 'session_id', 'subject_id', 'correlation_id', 'interaction_id', 'activation_id', 'activation_generation'],
      'media_close'
    );
    if (
      value.status !== 'closed' ||
      value.session_id !== binding.session_id ||
      value.subject_id !== binding.subject_id ||
      value.correlation_id !== binding.correlation_id ||
      value.interaction_id !== binding.interaction_id ||
      value.activation_id !== binding.activation_id ||
      value.activation_generation !== binding.activation_generation
    )
      throw new Error('media close binding mismatch');
    this.#retainedMediaAuthorities.delete(binding.subject_id);
    if (this.#mediaCloseBinding?.subject_id === binding.subject_id) {
      this.#mediaCloseBinding = null;
      this.#speech = null;
    }
  }

  async #releaseContinuationSpeechAuthority(
    caller: ProductP1MediaAuthorityRevokeCaller,
  ): Promise<void> {
    const authority = this.#continuationReceiptAuthority;
    const role = authority === null ? null : this.#mediaAuthorityRole(authority);
    this.#continuationResponseKey = null;
    this.#continuationSpeech = null;
    this.#continuationReceiptAuthority = null;
    this.#continuationCaptureFramesAcked = 0;
    if (authority !== null && role !== null) {
      await this.#revokeMediaAuthority(authority, caller, role);
    }
  }

  async #acquireContinuationAdmission(
    response: Readonly<AudioResponseRef>,
    responseKey: string,
    unitId: string,
    unitSeq: number,
    speech: GatewayBatchSpeechClient,
    signal?: AbortSignal,
  ): Promise<number> {
    if (this.#continuationAdmissionCleanupPromise !== null) {
      throw Object.assign(new Error('continuation admission cleanup is pending'), {
        reason: 'CONTINUATION_ADMISSION_CLEANUP_PENDING',
      });
    }
    if (signal?.aborted) {
      void this.#retainContinuationAdmissionCleanup('TTS_CONTINUATION_CANCELLED');
      throw Object.assign(new Error('continuation admission was cancelled'), {
        reason: 'TTS_CONTINUATION_CANCELLED',
      });
    }
    const active = this.#activeContinuationAdmission;
    if (active === null) {
      const epoch = this.#continuationAdmissionEpoch;
      let listenerRemoved = false;
      const removeAbortListener = () => {
        if (listenerRemoved) return;
        listenerRemoved = true;
        signal?.removeEventListener('abort', onAbort);
      };
      const onAbort = () => {
        removeAbortListener();
        void this.#retainContinuationAdmissionCleanup('TTS_CONTINUATION_CANCELLED');
      };
      this.#activeContinuationAdmission = Object.freeze({
        epoch,
        response: Object.freeze({ ...response }),
        responseKey,
        unitId,
        unitSeq,
        speech,
        signal: signal ?? null,
        removeAbortListener,
      });
      signal?.addEventListener('abort', onAbort, { once: true });
      if (signal?.aborted) onAbort();
      return epoch;
    }
    const tail =
      this.#deferredContinuationAdmissions[
        this.#deferredContinuationAdmissions.length - 1
      ] ?? active;
    if (
      active.responseKey !== responseKey
      || active.response.response_generation !== response.response_generation
    ) {
      throw new Error('continuation admission response is stale or foreign');
    }
    if (unitSeq !== tail.unitSeq + 1) {
      throw new Error('continuation admission unit sequence is not contiguous');
    }
    if (this.#deferredContinuationAdmissions.length >= MAX_DEFERRED_CONTINUATION_ADMISSIONS) {
      throw Object.assign(new Error('continuation admission capacity is exhausted'), {
        reason: 'CONTINUATION_ADMISSION_CAPACITY_EXHAUSTED',
      });
    }
    const epoch = active.epoch;
    await new Promise<void>((resolve, reject) => {
      let listenerRemoved = false;
      let waiter: DeferredContinuationAdmission;
      const removeAbortListener = () => {
        if (listenerRemoved) return;
        listenerRemoved = true;
        signal?.removeEventListener('abort', onAbort);
      };
      const onAbort = () => {
        removeAbortListener();
        void this.#retainContinuationAdmissionCleanup('TTS_CONTINUATION_CANCELLED');
      };
      waiter = {
        epoch,
        response: Object.freeze({ ...response }),
        responseKey,
        unitId,
        unitSeq,
        speech,
        signal: signal ?? null,
        resolve,
        reject,
        removeAbortListener,
      };
      this.#deferredContinuationAdmissions.push(waiter);
      signal?.addEventListener('abort', onAbort, { once: true });
      if (signal?.aborted) onAbort();
    });
    if (
      this.#continuationAdmissionEpoch !== epoch
      || this.#activeContinuationAdmission?.unitSeq !== unitSeq
      || this.#activeContinuationAdmission.responseKey !== responseKey
    ) {
      throw new Error('continuation admission was superseded');
    }
    return epoch;
  }

  #releaseContinuationAdmission(
    prepared: Readonly<PreparedProductSpeech>,
    metadata: Readonly<PreparedProductSpeechMetadata>,
  ): void {
    const epoch = metadata.continuationAdmissionEpoch;
    if (epoch === null) return;
    const active = this.#activeContinuationAdmission;
    if (
      active === null
      || active.epoch !== epoch
      || active.responseKey !== metadata.responseKey
      || active.unitId !== prepared.unitId
      || active.unitSeq !== prepared.unitSeq
    ) {
      throw new Error('continuation admission release owner mismatch');
    }
    const next = this.#deferredContinuationAdmissions.shift() ?? null;
    active.removeAbortListener();
    if (next === null) {
      this.#activeContinuationAdmission = null;
      return;
    }
    if (next.signal?.aborted || next.epoch !== this.#continuationAdmissionEpoch) {
      next.removeAbortListener();
      next.reject(new Error('continuation admission was cancelled'));
      void this.#retainContinuationAdmissionCleanup('TTS_CONTINUATION_CANCELLED');
      return;
    }
    this.#activeContinuationAdmission = Object.freeze({
      epoch: next.epoch,
      response: next.response,
      responseKey: next.responseKey,
      unitId: next.unitId,
      unitSeq: next.unitSeq,
      speech: next.speech,
      signal: next.signal,
      removeAbortListener: next.removeAbortListener,
    });
    next.resolve();
  }

  #retainContinuationAdmissionCleanup(reason: string): Promise<void> {
    const retained = this.#continuationAdmissionCleanupPromise;
    if (retained !== null) return retained;
    const active = this.#activeContinuationAdmission;
    active?.removeAbortListener();
    this.#continuationAdmissionEpoch += 1;
    this.#activeContinuationAdmission = null;
    const failure = Object.assign(new Error('continuation admission was closed'), {
      reason,
    });
    for (const waiter of this.#deferredContinuationAdmissions.splice(0)) {
      waiter.removeAbortListener();
      waiter.reject(failure);
    }
    const responseKey = active?.responseKey ?? null;
    const staged = this.#stagedSuccessor;
    if (responseKey !== null && staged?.metadata.responseKey === responseKey) {
      this.#stagedSuccessor = null;
      staged.downlinkRoute?.leaf.close('MEDIA_LOCAL_CLOSE');
      staged.chunks.splice(0);
    }
    if (responseKey !== null) {
      for (const [prepared, metadata] of this.#preparedSpeech) {
        if (metadata.responseKey === responseKey) this.#preparedSpeech.delete(prepared);
      }
    }
    const cleanup = Promise.resolve()
      .then(async () => {
        if (active !== null) {
          await active.speech.fenceSynthesis(active.response.interaction_id);
        }
      })
      .finally(() => {
        if (this.#continuationAdmissionCleanupPromise === cleanup) {
          this.#continuationAdmissionCleanupPromise = null;
        }
      });
    this.#continuationAdmissionCleanupPromise = cleanup;
    return cleanup;
  }

  #acceptCaptureFrame(frame: Readonly<CapturedAudioFrame>): void {
    if (this.#closed || this.#closeRequested || this.#failureCleanupPromise !== null || ['cleanup_pending', 'failed', 'closed'].includes(this.#status)) return;
    const captureDuringPlayout = this.#status === 'playing';
    if (!captureDuringPlayout) {
      let energy = 0;
      for (const sample of frame.samples) energy += sample * sample;
      if (Math.sqrt(energy / frame.samples.length) >= CAPTURE_SPEECH_ENERGY_FLOOR) {
        // Local energy is a decaying recency hint, never authoritative speech
        // state. The sticky observation below only guards the notification
        // pause path; rotation eligibility uses the decaying recency counter.
        this.#captureSpeechObserved = true;
        this.#captureLocalActivityRecencyFrames = CAPTURE_LOCAL_ACTIVITY_DECAY_FRAMES;
      } else if (this.#captureLocalActivityRecencyFrames > 0) {
        this.#captureLocalActivityRecencyFrames -= 1;
      }
    }
    if (
      this.#captureRotationPromise !== null &&
      frame.capture.capture_id === this.#captureRotationSourceId
    ) {
      // The exact boundary frame is already retained and draining. Ignore
      // additional uncommitted frames emitted while the expected local stop
      // settles; a current-lease provider speech-start still aborts the
      // in-flight rotation through its own fail-closed checkpoint.
      return;
    }
    const activePlayout = this.#pendingPlayout ?? this.#settlingPlayout;
    const utteranceActive = this.#captureProviderSpeechStartObserved;
    const localActivityRecent = !captureDuringPlayout && this.#captureLocalActivityRecencyFrames > 0;
    const canRotateBoundedCapture =
      this.#captureRotationPromise === null &&
      this.#frames.length >= MAX_CAPTURE_FRAMES - 1 &&
      !utteranceActive &&
      (!localActivityRecent ||
        this.#frames.length >= MAX_CAPTURE_FRAMES - 1 + CAPTURE_ROTATION_GRACE_FRAMES) &&
      ((this.#status === 'playing' && activePlayout !== null) || this.#status === 'capturing');
    if (canRotateBoundedCapture) {
      // Keep the exact boundary frame before rotating. During TTS overlap,
      // loudspeaker echo can cross the local energy floor, so only the current
      // media lease's authoritative speech-start protects a real utterance.
      // Outside playout, recent local energy defers this rotation until it
      // decays or the bounded grace elapses; it can no longer fail the lease.
      this.#frames.push(frame);
      this.#drainCaptureFrames();
      {
        const operationGeneration = this.#operationGeneration;
        const rotationSourceId = frame.capture.capture_id;
        this.#captureRotationSourceId = rotationSourceId;
        const rotationMode: 'overlap' | 'idle' = this.#status === 'playing' ? 'overlap' : 'idle';
        const rotationDiagnostics: Readonly<ProductP1CaptureRotationDiagnostics> = Object.freeze({
          mode: rotationMode,
          trigger: localActivityRecent
            ? ('local_activity_grace_elapsed' as const)
            : ('silent_boundary' as const),
          at_frame_count: this.#frames.length,
          local_activity_recency_frames: this.#captureLocalActivityRecencyFrames,
          completed: false,
        });
        this.#lastCaptureRotation = rotationDiagnostics;
        if (rotationDiagnostics.trigger === 'local_activity_grace_elapsed') {
          console.warn(
            `live_voice_capture_rotation trigger=local_activity_grace_elapsed mode=${rotationMode} frames=${this.#frames.length} recency_frames=${this.#captureLocalActivityRecencyFrames} generation=${operationGeneration} visible=false`
          );
        }
        const rotation = (rotationMode === 'overlap' ? this.#rotateConcurrentCapture(operationGeneration) : this.#rotateIdleCapture(operationGeneration))
          .then(() => {
            if (this.#lastCaptureRotation === rotationDiagnostics) {
              this.#lastCaptureRotation = Object.freeze({ ...rotationDiagnostics, completed: true });
            }
          })
          .catch(async error => {
            if (!this.#closed && this.#operationGeneration === operationGeneration) await this.#fail(error);
          })
          .finally(() => {
            if (this.#captureRotationPromise === rotation) this.#captureRotationPromise = null;
            if (this.#captureRotationSourceId === rotationSourceId) this.#captureRotationSourceId = null;
          });
        this.#captureRotationPromise = rotation;
      }
      return;
    }
    const utteranceStartFrameIndex = this.#captureUtteranceStartFrameIndex;
    if (
      (utteranceActive &&
        utteranceStartFrameIndex !== null &&
        this.#frames.length - utteranceStartFrameIndex >= MAX_CAPTURE_FRAMES) ||
      this.#frames.length >= CAPTURE_ABSOLUTE_MAX_FRAMES
    ) {
      // The declared 30-second budget bounds one authoritative utterance from
      // its provider speech-start, not the lease's wall-clock age: overlapped
      // TTS time and deferred-rotation grace no longer expire a user who has
      // not spoken. Batch STT owns the complete bounded utterance, so ACKed
      // frames cannot be evicted without truncating recognition input; an
      // utterance exceeding its own budget remains an exact Product P1
      // failure instead of leaking a trusted capacity decision through the
      // Adapter's generic consumer-error channel.
      void this.#fail(
        Object.assign(new Error('formal capture duration exceeded'), {
          reason: PRODUCT_P1_CAPTURE_DURATION_EXCEEDED_REASON,
        })
      );
      return;
    }
    this.#frames.push(frame);
    this.#drainCaptureFrames();
  }

  #requireHealthyCaptureReadiness(operationGeneration: number): void {
    this.#requireCurrent(operationGeneration);
    if (this.#captureStartupFailure !== null) throw this.#captureStartupFailure;
    if (this.#mediaTerminalFailure !== null) throw this.#mediaTerminalFailure;
  }

  async #awaitCaptureReadiness(route: ActiveBrowserDedicatedMediaRoute, operationGeneration: number): Promise<void> {
    const routeDeadline = Date.now() + ROUTE_READY_TIMEOUT_MS;
    while (!route.leaf.attached && !route.leaf.closed && Date.now() < routeDeadline) await waitTurn();
    this.#requireHealthyCaptureReadiness(operationGeneration);
    if (route.leaf.closed) {
      throw Object.assign(new Error('formal dedicated media route closed before capture readiness'), {
        reason: 'AUDIO_CAPTURE_MEDIA_ROUTE_CLOSED',
      });
    }
    if (!route.leaf.attached) {
      throw Object.assign(new Error('formal dedicated media route did not attach'), {
        reason: 'AUDIO_CAPTURE_MEDIA_ROUTE_NOT_ATTACHED',
      });
    }
    this.#drainCaptureFrames();
    const firstFrameDeadline = Date.now() + CAPTURE_FIRST_FRAME_TIMEOUT_MS;
    route.leaf.flush();
    while (
      (this.#frames.length === 0 || this.#mediaSentFrames === 0 || !this.#captureFirstFrameAcknowledged) &&
      !route.leaf.closed &&
      Date.now() < firstFrameDeadline
    ) {
      await waitTurn();
      this.#requireHealthyCaptureReadiness(operationGeneration);
      this.#drainCaptureFrames();
      route.leaf.flush();
    }
    this.#requireHealthyCaptureReadiness(operationGeneration);
    if (this.#audio.captureState() !== 'active') {
      throw Object.assign(new Error('formal browser capture stopped before readiness'), {
        reason: 'AUDIO_CAPTURE_STOPPED',
      });
    }
    if (!route.leaf.attached || route.leaf.closed) {
      throw Object.assign(new Error('formal dedicated media route closed before capture readiness'), {
        reason: 'AUDIO_CAPTURE_MEDIA_ROUTE_CLOSED',
      });
    }
    if (this.#frames.length === 0 || this.#mediaSentFrames === 0) {
      throw Object.assign(new Error('formal browser capture had no accepted media frames'), {
        reason: 'AUDIO_CAPTURE_NO_FRAMES',
      });
    }
    if (!this.#captureFirstFrameAcknowledged) {
      throw Object.assign(new Error('formal media route did not acknowledge capture readiness'), {
        reason: 'AUDIO_CAPTURE_MEDIA_NOT_ACKNOWLEDGED',
      });
    }
    this.#captureFramesAcked = this.#mediaSentFrames;
  }

  #drainCaptureFrames(): void {
    const route = this.#route;
    if (route === null || !route.leaf.attached || route.leaf.closed) return;
    while (this.#mediaSentFrames < this.#frames.length) {
      const result = route.leaf.sendCaptureFrame(this.#frames[this.#mediaSentFrames]);
      if (!result.accepted) {
        if (['MEDIA_NOT_ATTACHED', 'MEDIA_BACKPRESSURE_LIMIT'].includes(result.reason_id)) return;
        throw Object.assign(new Error('formal media route rejected a capture frame'), {
          reason: result.reason_id,
        });
      }
      this.#mediaSentFrames += 1;
    }
  }

  #observeUplinkFrameSent(
    route: ActiveBrowserDedicatedMediaRoute,
    seq: number,
  ): void {
    if (
      !this.#l0Available
      || route !== this.#route
      || !Number.isSafeInteger(seq)
      || seq < 0
      || seq >= this.#frames.length
    ) return;
    this.#l0LastFrameSentClock = l0ClockNow();
  }

  #observeUplinkFrameAcknowledged(
    route: ActiveBrowserDedicatedMediaRoute,
    throughSeq: number,
  ): void {
    if (
      route !== this.#route
      || route.leaf.closed
      || !Number.isSafeInteger(throughSeq)
      || throughSeq < 0
    ) return;
    this.#captureFirstFrameAcknowledged = true;
  }

  #observeFirstFrameDiagnostic(
    route: ActiveBrowserDedicatedMediaRoute,
    fact: Readonly<MediaFirstFrameDiagnostic>,
  ): void {
    if (route !== this.#route || route.leaf.closed) return;
    this.#captureFirstFrameDiagnostic = fact;
    console.info(
      `live_voice_media_first_frame stage=${fact.stage} scope_sha256=${fact.scope_sha256} generation=${fact.capture_generation} seq=${fact.frame_seq} monotonic_ms=${fact.monotonic_ms.toFixed(3)} elapsed_ms=${fact.elapsed_ms.toFixed(3)} outcome=${fact.outcome} reason=${fact.reason}`,
    );
  }

  async #fail(error: unknown): Promise<void> {
    if (this.#closed) {
      this.#setStatus('closed', null);
      return;
    }
    if (this.#closeRequested) return;
    // A late continuation from the operation already fenced by the first
    // failure cannot start a second cleanup or replace its exact stable reason.
    if (this.#failureCleanupReason !== null && ['cleanup_pending', 'failed'].includes(this.#status) && this.#failureCleanupPromise === null) return;
    const failureReason = stableFailureReason(error);
    if (this.#failureCleanupPromise === null) {
      const failureResponse = (
        this.#pendingPlayout ?? this.#settlingPlayout
      )?.response ?? null;
      this.#l0Record('browser_failure', failureResponse, undefined, 'failure');
      this.#failureCleanupReason = failureReason;
      this.#operationGeneration += 1;
      this.#reason = failureReason;
      this.#status = 'cleanup_pending';
      const retained = Promise.resolve()
        .then(() => this.#releaseResources('formal_route_failed', failureReason))
        .finally(() => {
          if (this.#failureCleanupPromise === retained) {
            this.#failureCleanupPromise = null;
          }
        });
      this.#failureCleanupPromise = retained;
      this.#publish();
    }
    try {
      await this.#failureCleanupPromise;
      this.#reason = this.#failureCleanupReason ?? failureReason;
      this.#status = 'failed';
    } catch {
      // The exact media binding is retained so close() can retry revocation;
      // UI truth must not claim that the failed owner is already clean.
      this.#reason = 'FORMAL_P1_CLEANUP_PENDING';
      this.#status = 'cleanup_pending';
    }
    this.#publish();
  }

  async #releaseResources(reason: string, pendingFailureReason: string | null = null): Promise<void> {
    await this.#retainContinuationAdmissionCleanup(reason);
    this.#operationGeneration += 1;
    this.#captureReadinessPending = false;
    this.#captureReadinessPurpose = null;
    this.#captureStartupAudioReady = false;
    this.#captureStartupFailure = null;
    this.#mediaTerminalFailure = null;
    this.#pendingSpeechStart = null;
    this.#pendingEndOfTurn = null;
    this.#endOfTurnHandler = null;
    this.#endOfTurnDelivered = false;
    this.#stopAndRecognizePromise = null;
    this.#continuationResponseKey = null;
    this.#continuationSpeech = null;
    this.#continuationReceiptAuthority = null;
    this.#continuationCaptureFramesAcked = 0;
    this.#captureStopExpected = false;
    this.#route?.leaf.close('MEDIA_LOCAL_CLOSE');
    this.#route = null;
    this.#speech = null;
    const staged = this.#stagedSuccessor;
    this.#stagedSuccessor = null;
    staged?.downlinkRoute?.leaf.close('MEDIA_LOCAL_CLOSE');
    staged?.chunks.splice(0);
    this.#preparedSpeech.clear();
    const pending = this.#pendingPlayout ?? this.#settlingPlayout;
    this.#pendingPlayout = null;
    this.#settlingPlayout = null;
    if (pending !== null) {
      pending.downlinkRoute?.leaf.close('MEDIA_LOCAL_CLOSE');
      this.#audio.stopPlayout(pending.response, reason);
      pending.reject(
        pendingFailureReason === null
          ? new Error('formal P1 route closed during playout')
          : Object.assign(new Error('formal P1 route failed during playout'), {
              reason: pendingFailureReason,
            })
      );
    }
    // Raw PCM is local, memory-only recognition input. Release it before any
    // fallible browser or remote authority cleanup; retained close bindings are
    // sufficient for an exact retry and must never retain expired audio.
    this.#frames = [];
    this.#captureSpeechObserved = false;
    this.#captureProviderSpeechStartObserved = false;
    this.#captureLocalActivityRecencyFrames = 0;
    this.#captureUtteranceStartFrameIndex = null;
    this.#captureRotationSourceId = null;
    this.#mediaSentFrames = 0;
    this.#captureFirstFrameAcknowledged = false;
    this.#captureFirstFrameDiagnostic = null;
    this.#captureFramesAcked = 0;
    this.#playout = null;
    try {
      await this.#audio.stopCapture(reason);
    } catch {
      /* close remains authoritative */
    }
    await this.#audio.close();
    const authorities = new Map(this.#retainedMediaAuthorities);
    if (this.#mediaCloseBinding !== null) {
      authorities.set(this.#mediaCloseBinding.subject_id, this.#mediaCloseBinding);
    }
    const releaseCaller: ProductP1MediaAuthorityRevokeCaller =
      reason === 'formal_route_failed' ? 'release_resources_failed' : 'release_resources_close';
    for (const authority of authorities.values()) {
      await this.#revokeMediaAuthority(authority, releaseCaller);
    }
  }

  #requireCurrent(operationGeneration: number): void {
    if (this.#closed || this.#operationGeneration !== operationGeneration) {
      throw new Error('formal P1 operation was superseded');
    }
  }

  #setStatus(status: ProductP1VoiceStatus, reason: string | null): void {
    this.#status = status;
    this.#reason = reason;
    this.#publish();
  }

  #observeStreamingAvailability(activation: Record<string, unknown>): void {
    if (!Object.prototype.hasOwnProperty.call(activation, 'streaming_recognition')) {
      this.#streamingRecognitionAvailable = false;
      this.#streamingFallbackReason = null;
      this.#streamingFallbackTier = null;
      return;
    }
    if (typeof activation.streaming_recognition !== 'boolean') {
      throw new Error('media activation streaming capability is invalid');
    }
    this.#streamingRecognitionAvailable = activation.streaming_recognition;
    if (activation.streaming_degradation === null) {
      if (!this.#streamingRecognitionAvailable) {
        throw new Error('media activation omitted streaming degradation');
      }
      this.#streamingFallbackReason = null;
      this.#streamingFallbackTier = null;
      return;
    }
    if (this.#streamingRecognitionAvailable) {
      throw new Error('active streaming recognition cannot declare degradation');
    }
    const degradation = exactObject(
      activation.streaming_degradation,
      ['reason_id', 'fallback_tier', 'visible', 'x_obs_event', 'x_obs_metric'],
      'media_activation.streaming_degradation'
    );
    const reason = requiredText(degradation.reason_id, 'streaming_degradation.reason_id');
    normalizeStreamingXObs(degradation.x_obs_event, degradation.x_obs_metric);
    if (
      !isStreamingSpeechDegradationReason(reason) ||
      !['batch', 'text'].includes(String(degradation.fallback_tier)) ||
      degradation.visible !== true
    ) {
      throw new Error('media activation streaming degradation is invalid');
    }
    this.#streamingFallbackReason = reason;
    this.#streamingFallbackTier = degradation.fallback_tier as 'batch' | 'text';
  }

  #observeEndOfTurnAvailability(activation: Record<string, unknown>): void {
    if (!Object.prototype.hasOwnProperty.call(activation, 'end_of_turn')) {
      throw new Error('media activation omitted requested end-of-turn negotiation');
    }
    const value = objectValue(activation.end_of_turn, 'media_activation.end_of_turn');
    if (value.status === 'active') {
      const active = exactObject(
        value,
        ['status', 'capability_version', 'detector', 'create_response', 'interrupt_response'],
        'media_activation.end_of_turn'
      );
      if (
        active.capability_version !== MEDIA_END_OF_TURN_CAPABILITY ||
        active.detector !== 'server_vad' ||
        active.create_response !== false ||
        active.interrupt_response !== false
      ) {
        throw new Error('media activation end-of-turn capability mismatched');
      }
      this.#endOfTurnNegotiated = true;
      return;
    }
    const fallback = exactObject(
      value,
      ['status', 'requested_capability', 'reason_id', 'fallback', 'visible'],
      'media_activation.end_of_turn'
    );
    if (
      fallback.status !== 'fallback' ||
      fallback.requested_capability !== MEDIA_END_OF_TURN_CAPABILITY ||
      fallback.fallback !== 'manual' ||
      fallback.visible !== true
    ) {
      throw new Error('media activation end-of-turn fallback is invalid');
    }
    const reason = requiredText(fallback.reason_id, 'end_of_turn.reason_id');
    if (reason !== 'MEDIA_END_OF_TURN_FEATURE_OFF' && reason !== 'MEDIA_END_OF_TURN_PROVIDER_UNAVAILABLE') {
      throw new Error('media activation end-of-turn fallback reason is unsupported');
    }
    console.warn(`live_voice_end_of_turn_degradation reason=${reason} target=manual visible=true`);
    this.#endOfTurnNegotiated = false;
  }

  #deliverEndOfTurn(operationGeneration: number, route: ActiveBrowserDedicatedMediaRoute | null): void {
    if (
      this.#pendingEndOfTurn === null ||
      this.#endOfTurnHandler === null ||
      this.#endOfTurnDelivered ||
      route === null ||
      route !== this.#route ||
      operationGeneration !== this.#operationGeneration
    ) {
      return;
    }
    if (this.#status !== 'capturing') {
      if (this.#stopAndRecognizePromise !== null) this.#endOfTurnDelivered = true;
      return;
    }
    this.#endOfTurnDelivered = true;
    const handler = this.#endOfTurnHandler;
    Promise.resolve().then(() => {
      if (
        !this.#closed &&
        operationGeneration === this.#operationGeneration &&
        route === this.#route &&
        this.#status === 'capturing'
      ) {
        handler();
      }
    });
  }

  #observeSpeechStartControl(
    operationGeneration: number,
    route: ActiveBrowserDedicatedMediaRoute | null,
    event: Readonly<MediaSpeechStart>
  ): void {
    if (
      route === null ||
      route !== this.#route ||
      operationGeneration !== this.#operationGeneration
    ) {
      return;
    }
    if (
      event.lease_id !== route.binding.lease_id ||
      event.generation !== route.binding.generation.value
    ) {
      throw new Error('speech-start control escaped its media authority');
    }
    this.#captureProviderSpeechStartObserved = true;
    if (this.#captureUtteranceStartFrameIndex === null) {
      // The authoritative utterance budget starts at the first provider
      // speech-start on this lease; capture-lease age alone never expires an
      // active utterance.
      this.#captureUtteranceStartFrameIndex = this.#frames.length;
    }
    this.#pendingSpeechStart = event;
    this.#deliverBargeInSpeechStart(operationGeneration, route);
  }

  #deliverBargeInSpeechStart(
    operationGeneration: number,
    route: ActiveBrowserDedicatedMediaRoute | null
  ): void {
    const event = this.#pendingSpeechStart;
    const continuationPreparing =
      this.#status === 'capturing' &&
      this.#continuationResponseKey !== null &&
      (this.#preparingSpeechCount > 0 || this.#preparedSpeech.size > 0);
    if (
      event === null ||
      this.#onBargeInSpeechStart === undefined ||
      this.#bargeInSpeechStartDelivered ||
      (!continuationPreparing &&
        (this.#status !== 'playing' || this.#pendingPlayout === null)) ||
      route === null ||
      route !== this.#route ||
      operationGeneration !== this.#operationGeneration
    ) {
      return;
    }
    this.#bargeInSpeechStartDelivered = true;
    this.#onBargeInSpeechStart(event);
  }

  #observeEndOfTurnControl(
    operationGeneration: number,
    route: ActiveBrowserDedicatedMediaRoute | null,
    event: Readonly<MediaEndOfTurn>
  ): void {
    if (
      route === null ||
      route !== this.#route ||
      operationGeneration !== this.#operationGeneration
    ) {
      return;
    }
    if (
      event.lease_id !== route.binding.lease_id ||
      event.generation !== route.binding.generation.value
    ) {
      throw new Error('end-of-turn control escaped its media authority');
    }
    this.#l0Record('browser_eot_receipt');
    this.#pendingEndOfTurn = event;
    this.#deliverBargeInEndOfTurn(operationGeneration, route);
    this.#deliverEndOfTurn(operationGeneration, route);
  }

  #deliverBargeInEndOfTurn(
    operationGeneration: number,
    route: ActiveBrowserDedicatedMediaRoute | null
  ): void {
    const event = this.#pendingEndOfTurn;
    if (
      event === null ||
      this.#onBargeInEndOfTurn === undefined ||
      this.#bargeInEndOfTurnDelivered ||
      this.#status !== 'playing' ||
      this.#pendingPlayout === null ||
      route === null ||
      route !== this.#route ||
      operationGeneration !== this.#operationGeneration
    ) {
      return;
    }
    this.#bargeInEndOfTurnDelivered = true;
    const callback = this.#onBargeInEndOfTurn;
    Promise.resolve().then(() => {
      if (
        !this.#closed &&
        this.#status === 'playing' &&
        this.#pendingEndOfTurn === event &&
        route === this.#route &&
        operationGeneration === this.#operationGeneration
      ) {
        callback(event);
      }
    });
  }

  #publish(): void {
    this.#onStatus?.(this.#status, this.#reason);
  }
}
