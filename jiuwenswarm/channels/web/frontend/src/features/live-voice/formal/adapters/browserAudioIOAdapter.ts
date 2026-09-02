import {
  AudioPort,
  AudioPortViolation,
  LIVE_VOICE_AUDIO_FRAME_DURATION_MS,
  audioFrameSamples,
  createCapturedAudioFrame,
  type AudioProviderRef,
  type AudioResponseRef,
  type CapturedAudioFrame,
} from '../audioPort.js';

export type BrowserAudioCaptureState = 'idle' | 'starting' | 'active' | 'stopping' | 'stopped' | 'failed';
export type BrowserAudioPlayoutState = 'locked' | 'ready' | 'playing' | 'stopped' | 'failed' | 'closed';

const C019_PLAYOUT_DIAGNOSTIC_CAPACITY = 1_024;
const c019PlayoutDiagnosticRecords: Readonly<Record<string, unknown>>[] = [];
let c019PlayoutDiagnosticsEnabled = false;
const c019PlayoutDiagnosticControl = Object.freeze({
  clear: (): void => {
    c019PlayoutDiagnosticRecords.length = 0;
  },
  snapshot: (): Readonly<{ records: readonly Readonly<Record<string, unknown>>[] }> =>
    Object.freeze({ records: Object.freeze([...c019PlayoutDiagnosticRecords]) }),
});

function enableBrowserC019PlayoutDiagnostics(): void {
  if (c019PlayoutDiagnosticsEnabled) return;
  c019PlayoutDiagnosticsEnabled = true;
  if (typeof window === 'undefined') return;
  Object.defineProperty(globalThis, '__JIUWENSWARM_LIVE_VOICE_C019_PLAYOUT__', {
    configurable: true,
    enumerable: false,
    writable: false,
    value: c019PlayoutDiagnosticControl,
  });
}

export function reportBrowserC019PlayoutDiagnostic(
  level: 'info' | 'warn',
  value: Readonly<Record<string, unknown>>,
): void {
  if (!c019PlayoutDiagnosticsEnabled) return;
  const record = Object.freeze({
    observed_at: new Date().toISOString(),
    monotonic_ms: typeof performance === 'undefined' ? Date.now() : performance.now(),
    ...value,
  });
  if (c019PlayoutDiagnosticRecords.length >= C019_PLAYOUT_DIAGNOSTIC_CAPACITY) {
    c019PlayoutDiagnosticRecords.shift();
  }
  c019PlayoutDiagnosticRecords.push(record);
  if (level === 'warn') console.warn('[LiveVoiceC019] playout diagnostic', record);
  else console.info('[LiveVoiceC019] playout diagnostic', record);
}

type BrowserEventListener = () => void;

export interface BrowserAudioDocumentLike {
  readonly visibilityState: string;
  addEventListener(type: 'visibilitychange', listener: BrowserEventListener): void;
  removeEventListener(type: 'visibilitychange', listener: BrowserEventListener): void;
}

export interface BrowserAudioTrackSettingsLike {
  readonly sampleRate?: number;
  readonly channelCount?: number;
  readonly echoCancellation?: boolean;
  readonly noiseSuppression?: boolean;
  readonly autoGainControl?: boolean;
  readonly deviceId?: string;
}

export interface BrowserAudioTrackLike {
  readonly id: string;
  readonly kind: string;
  readonly readyState?: string;
  readonly muted?: boolean;
  stop(): void;
  getSettings(): BrowserAudioTrackSettingsLike;
  addEventListener(type: 'ended' | 'mute' | 'unmute', listener: BrowserEventListener): void;
  removeEventListener(type: 'ended' | 'mute' | 'unmute', listener: BrowserEventListener): void;
}

export interface BrowserMediaStreamLike {
  getAudioTracks(): BrowserAudioTrackLike[];
  getTracks(): BrowserAudioTrackLike[];
}

export interface BrowserMediaDeviceInfoLike {
  readonly kind: string;
  readonly deviceId?: string;
  readonly label?: string;
}

export interface BrowserMediaDevicesLike {
  getUserMedia(constraints: MediaStreamConstraints): Promise<BrowserMediaStreamLike>;
  enumerateDevices(): Promise<BrowserMediaDeviceInfoLike[]>;
  addEventListener(type: 'devicechange', listener: BrowserEventListener): void;
  removeEventListener(type: 'devicechange', listener: BrowserEventListener): void;
}

export type BrowserAudioCaptureStreamFactory = (
  constraints: MediaStreamConstraints,
) => Promise<BrowserMediaStreamLike>;

export interface BrowserPermissionStatusLike {
  readonly state: string;
  addEventListener(type: 'change', listener: BrowserEventListener): void;
  removeEventListener(type: 'change', listener: BrowserEventListener): void;
}

export interface BrowserPermissionsLike {
  query(descriptor: Readonly<{ name: 'microphone' }>): Promise<BrowserPermissionStatusLike>;
}

export interface BrowserAudioMessagePortLike {
  onmessage: ((event: Readonly<{ data: unknown }>) => void) | null;
  close(): void;
}

export interface BrowserAudioNodeLike {
  connect(destination: unknown): unknown;
  disconnect(): void;
}

export interface BrowserAudioWorkletNodeLike extends BrowserAudioNodeLike {
  readonly port: BrowserAudioMessagePortLike;
  onprocessorerror: BrowserEventListener | null;
}

export interface BrowserAudioBufferLike {
  copyToChannel(source: Float32Array, channelNumber: number): void;
}

export interface BrowserAudioBufferSourceLike extends BrowserAudioNodeLike {
  buffer: BrowserAudioBufferLike | null;
  onended: BrowserEventListener | null;
  start(when?: number): void;
  stop(): void;
}

export interface BrowserAudioContextLike {
  readonly sampleRate: number;
  readonly currentTime: number;
  readonly destination: unknown;
  readonly audioWorklet?: Readonly<{ addModule(moduleUrl: string): Promise<void> }>;
  readonly state: 'suspended' | 'running' | 'closed' | string;
  onstatechange: BrowserEventListener | null;
  resume(): Promise<void>;
  setSinkId?(sinkId: string): Promise<void>;
  close(): Promise<void>;
  createMediaStreamSource(stream: unknown): BrowserAudioNodeLike;
  createBuffer(numberOfChannels: number, length: number, sampleRate: number): BrowserAudioBufferLike;
  createBufferSource(): BrowserAudioBufferSourceLike;
}

export interface BrowserAudioEnvironment {
  readonly isSecureContext: boolean;
  readonly document: BrowserAudioDocumentLike | null;
  readonly mediaDevices: BrowserMediaDevicesLike | null;
  readonly permissions?: BrowserPermissionsLike | null;
  readonly createAudioContext: (() => BrowserAudioContextLike) | null;
  readonly createAudioWorkletNode:
    | ((context: BrowserAudioContextLike, name: string, options: Readonly<Record<string, unknown>>) => BrowserAudioWorkletNodeLike)
    | null;
  readonly createId: (() => string) | null;
  readonly outputDeviceSelection?: boolean;
}

export interface BrowserAudioPlatformCapability {
  readonly enabled: boolean;
  readonly secure_context: boolean;
  readonly document_visibility: boolean;
  readonly media_devices: boolean;
  readonly audio_context: boolean;
  readonly audio_worklet_node: boolean;
  readonly stable_identity: boolean;
  readonly capture_pcm_f32: boolean;
  readonly playout_pcm_f32: boolean;
  readonly media_recorder_realtime: false;
  readonly output_device_selection: boolean;
  readonly physical_heard_ack: false;
  readonly reasons: readonly string[];
}

export interface BrowserAudioCaptureMetadata {
  readonly capture_id: string;
  readonly capture_generation: number;
  readonly track_id: string;
  readonly requested_device: 'default' | 'exact';
  readonly requested_processing: Readonly<{
    echo_cancellation: true;
    noise_suppression: true;
    auto_gain_control: true;
    channel_count: 1;
  }>;
  readonly actual_processing: Readonly<{
    echo_cancellation: boolean | null;
    noise_suppression: boolean | null;
    auto_gain_control: boolean | null;
    track_sample_rate_hz: number | null;
    track_channel_count: number | null;
    device_id_present: boolean;
  }>;
  readonly frame_format: Readonly<{
    encoding: 'pcm_f32';
    sample_rate_hz: number;
    channel_count: 1;
    frame_duration_ms: typeof LIVE_VOICE_AUDIO_FRAME_DURATION_MS;
    samples_per_channel: number;
  }>;
}

export interface BrowserAudioPlayoutMetadata {
  readonly encoding: 'pcm_f32';
  readonly sample_rate_hz: number;
  readonly channel_count: 1;
  readonly output_device_selection: boolean;
  readonly physical_heard_ack: false;
}

export type BrowserAudioLocalStopOutcome =
  | 'local_fence_established'
  | 'local_fence_established_source_unknown'
  | 'target_mismatch'
  | 'no_active_target'
  | 'already_stopped'
  | 'local_fence_failed'
  | 'feature_disabled'
  | 'adapter_closed';

export type BrowserAudioSourceActionStatus = 'not_attempted' | 'not_applicable' | 'completed' | 'unknown';

export interface BrowserAudioSourceActionConfirmation {
  readonly status: BrowserAudioSourceActionStatus;
  readonly attempted_count: number;
  readonly completed_count: number;
  readonly failed_count: number;
}

export interface BrowserAudioConfirmedCursor {
  readonly unit_id: string;
  readonly contiguous_through_seq: number | null;
}

export interface BrowserAudioLocalStopReceipt {
  readonly kind: 'browser_audio.local_stop.v1';
  readonly outcome: BrowserAudioLocalStopOutcome;
  readonly response: Readonly<AudioResponseRef>;
  readonly reason: string;
  readonly local_fence_established: boolean;
  readonly confirmed_cursor_before_stop: readonly Readonly<BrowserAudioConfirmedCursor>[];
  readonly browser_sources: Readonly<{
    source_count: number;
    stop_request: Readonly<BrowserAudioSourceActionConfirmation>;
    disconnect: Readonly<BrowserAudioSourceActionConfirmation>;
  }>;
  readonly timing: Readonly<{
    status: 'confirmed' | 'unknown';
    requested_at_monotonic_ms: number | null;
    confirmed_at_monotonic_ms: number | null;
    duration_ms: number | null;
  }>;
  readonly physical_heard: 'unproven';
  readonly physical_silence: 'unproven';
  readonly business_cancel_count_before: number;
  readonly business_cancel_count_after: number;
  readonly business_cancel_count_delta: number;
}

export interface BrowserAudioCaptureStateEvent {
  readonly state: BrowserAudioCaptureState;
  readonly reason: string;
  readonly capture_id: string | null;
  readonly capture_generation: number | null;
}

export interface BrowserAudioDeviceEvent {
  readonly audio_input_count: number | null;
  readonly reason: 'devicechange' | 'enumeration_failed';
}

export interface BrowserAudioPlayoutEvent {
  readonly state: BrowserAudioPlayoutState;
  readonly reason: string;
  readonly response: Readonly<AudioResponseRef> | null;
  readonly unit_id: string | null;
  readonly through_seq: number | null;
}

export interface BrowserAudioPlayoutScheduledEvent {
  readonly response: Readonly<AudioResponseRef>;
  readonly unit_id: string;
  readonly seq: number;
  readonly start_delay_ms: number;
  readonly scheduled_start_clock: Readonly<{
    readonly observed_at: string;
    readonly monotonic_ms: number;
  }> | null;
  readonly has_started: () => boolean;
}

export interface BrowserAudioObserver {
  onCaptureFrame?(frame: Readonly<CapturedAudioFrame>): void;
  onCaptureState?(event: Readonly<BrowserAudioCaptureStateEvent>): void;
  onDeviceChange?(event: Readonly<BrowserAudioDeviceEvent>): void;
  onPlayoutState?(event: Readonly<BrowserAudioPlayoutEvent>): void;
  onPlayoutScheduled?(event: Readonly<BrowserAudioPlayoutScheduledEvent>): void;
}

export interface BrowserAudioPcmChunk {
  readonly response: Readonly<AudioResponseRef>;
  readonly unit_id: string;
  readonly seq: number;
  readonly sample_rate_hz: number;
  readonly channel_count: 1;
  readonly samples: Float32Array;
  readonly provider: Readonly<AudioProviderRef>;
}

export class BrowserAudioIOViolation extends Error {
  constructor(
    readonly reason: string,
    message: string,
    readonly retriable = false
  ) {
    super(message);
    this.name = 'BrowserAudioIOViolation';
  }
}

interface CaptureSession {
  readonly token: number;
  readonly metadata: Readonly<BrowserAudioCaptureMetadata>;
  readonly stream: BrowserMediaStreamLike;
  readonly track: BrowserAudioTrackLike;
  readonly context: BrowserAudioContextLike;
  readonly source: BrowserAudioNodeLike;
  readonly worklet: BrowserAudioWorkletNodeLike;
  readonly onTrackEnded: BrowserEventListener;
  readonly onTrackMute: BrowserEventListener;
  readonly onTrackUnmute: BrowserEventListener;
  readonly onDeviceChange: BrowserEventListener;
  readonly onContextStateChange: BrowserEventListener;
  readonly priorContextStateChange: BrowserEventListener | null;
  readonly installedContextStateChange: BrowserEventListener;
  readonly ownsContext: boolean;
  readonly permissionObservation: CapturePermissionObservation;
  readonly requestedDeviceId: string | null;
  expectedSeq: number;
  closed: boolean;
}

type MicrophonePermissionState = 'granted' | 'prompt' | 'denied';

interface CapturePermissionObservation {
  readonly token: number;
  readonly onChange: BrowserEventListener;
  readonly revocation: Promise<never>;
  readonly rejectRevocation: (failure: BrowserAudioIOViolation) => void;
  status: BrowserPermissionStatusLike | null;
  lastKnownState: MicrophonePermissionState | null;
  mediaAccessGranted: boolean;
  listenerAttached: boolean;
  closed: boolean;
  revocationFailure: BrowserAudioIOViolation | null;
}

interface PendingCaptureResources {
  readonly token: number;
  stream: BrowserMediaStreamLike | null;
  track: BrowserAudioTrackLike | null;
  context: BrowserAudioContextLike | null;
  source: BrowserAudioNodeLike | null;
  worklet: BrowserAudioWorkletNodeLike | null;
  readonly onTrackEnded: BrowserEventListener;
  readonly onDeviceChange: BrowserEventListener;
  readonly onContextStateChange: BrowserEventListener;
  priorContextStateChange: BrowserEventListener | null;
  installedContextStateChange: BrowserEventListener | null;
  ownsContext: boolean;
  readonly permissionObservation: CapturePermissionObservation;
  requestedDeviceId: string | null;
  trackListenerAttached: boolean;
  deviceListenerAttached: boolean;
  contextHasRun: boolean;
  cleanupPromise: Promise<void> | null;
}

interface PlaybackSourceRecord {
  readonly unitId: string;
  readonly seq: number;
  readonly source: BrowserAudioBufferSourceLike;
  stopped: boolean;
}

interface PlaybackSession {
  readonly response: Readonly<AudioResponseRef>;
  readonly sources: Map<string, PlaybackSourceRecord>;
  readonly completed: Map<string, Set<number>>;
  readonly acknowledged: Map<string, number>;
  readonly units: Set<string>;
  nextStartTime: number;
  stopped: boolean;
}

interface PlaybackSourceCleanupSummary {
  readonly sourceCount: number;
  readonly stopCompletedCount: number;
  readonly stopFailedCount: number;
  readonly disconnectCompletedCount: number;
  readonly disconnectFailedCount: number;
}

const CAPTURE_PROCESSOR_NAME = 'jiuwenswarm-live-voice-capture-v1';
// OpenAI streaming TTS can emit a short seed chunk and then pause before the
// first sustained burst.  Schedule the browser graph slightly ahead so that
// ordered 20 ms sources remain contiguous instead of exposing that Provider
// interarrival gap as a click or a short dropout.
export const PLAYOUT_STARTUP_LEAD_MIN_MS = 160;
export const PLAYOUT_STARTUP_LEAD_MAX_MS = 1000;
export const PLAYOUT_STARTUP_LEAD_BASELINE_MS = 1000;

function requirePlayoutStartupLeadMs(value: number): number {
  if (
    !Number.isSafeInteger(value)
    || value < PLAYOUT_STARTUP_LEAD_MIN_MS
    || value > PLAYOUT_STARTUP_LEAD_MAX_MS
  ) {
    throw new BrowserAudioIOViolation(
      'INVALID_PLAYOUT_STARTUP_LEAD',
      'playout startup lead must be an integer from 160 to 1000 ms',
    );
  }
  return value;
}

const DISABLED_BROWSER_AUDIO_ENVIRONMENT: BrowserAudioEnvironment = Object.freeze({
  isSecureContext: false,
  document: null,
  mediaDevices: null,
  permissions: null,
  createAudioContext: null,
  createAudioWorkletNode: null,
  createId: null,
  outputDeviceSelection: false,
});

const DISABLED_BROWSER_AUDIO_CAPABILITY: Readonly<BrowserAudioPlatformCapability> = Object.freeze({
  enabled: false,
  secure_context: false,
  document_visibility: false,
  media_devices: false,
  audio_context: false,
  audio_worklet_node: false,
  stable_identity: false,
  capture_pcm_f32: false,
  playout_pcm_f32: false,
  media_recorder_realtime: false,
  output_device_selection: false,
  physical_heard_ack: false,
  reasons: Object.freeze(['FEATURE_DISABLED']),
});

function defaultBrowserAudioEnvironment(): BrowserAudioEnvironment {
  if (typeof window === 'undefined' || typeof navigator === 'undefined') {
    return Object.freeze({
      isSecureContext: false,
      document: null,
      mediaDevices: null,
      permissions: null,
      createAudioContext: null,
      createAudioWorkletNode: null,
      createId: null,
    });
  }
  const browserWindow = window as Window & {
    webkitAudioContext?: typeof AudioContext;
    AudioWorkletNode?: typeof AudioWorkletNode;
  };
  const browserNavigator = navigator as Navigator & { permissions?: BrowserPermissionsLike };
  const audioContextConstructor = (typeof AudioContext === 'undefined' ? undefined : AudioContext) ?? browserWindow.webkitAudioContext;
  const workletNodeConstructor = browserWindow.AudioWorkletNode ?? (globalThis as { AudioWorkletNode?: typeof AudioWorkletNode }).AudioWorkletNode;
  return Object.freeze({
    isSecureContext: window.isSecureContext,
    document: document as unknown as BrowserAudioDocumentLike,
    mediaDevices: navigator.mediaDevices ? (navigator.mediaDevices as unknown as BrowserMediaDevicesLike) : null,
    permissions: browserNavigator.permissions ?? null,
    createAudioContext: audioContextConstructor ? () => new audioContextConstructor() as unknown as BrowserAudioContextLike : null,
    createAudioWorkletNode: workletNodeConstructor
      ? (context: BrowserAudioContextLike, name: string, options: Readonly<Record<string, unknown>>) =>
          new workletNodeConstructor(context as unknown as BaseAudioContext, name, options as AudioWorkletNodeOptions) as unknown as BrowserAudioWorkletNodeLike
      : null,
    createId: typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function' ? () => crypto.randomUUID() : null,
    outputDeviceSelection: Boolean(audioContextConstructor && 'setSinkId' in audioContextConstructor.prototype),
  });
}

export function inspectBrowserAudioPlatform(enabled: boolean, environment?: BrowserAudioEnvironment): Readonly<BrowserAudioPlatformCapability> {
  if (!enabled) return DISABLED_BROWSER_AUDIO_CAPABILITY;
  const selectedEnvironment = environment ?? defaultBrowserAudioEnvironment();
  const reasons: string[] = [];
  if (!selectedEnvironment.isSecureContext) reasons.push('INSECURE_CONTEXT');
  if (selectedEnvironment.document === null) reasons.push('DOCUMENT_VISIBILITY_UNAVAILABLE');
  if (selectedEnvironment.mediaDevices === null) reasons.push('MEDIA_DEVICES_UNAVAILABLE');
  if (selectedEnvironment.createAudioContext === null) reasons.push('AUDIO_CONTEXT_UNAVAILABLE');
  if (selectedEnvironment.createAudioWorkletNode === null) reasons.push('AUDIO_WORKLET_NODE_UNAVAILABLE');
  if (selectedEnvironment.createId === null) reasons.push('STABLE_IDENTITY_UNAVAILABLE');
  const captureSupported = reasons.length === 0;
  const playoutSupported =
    selectedEnvironment.isSecureContext && selectedEnvironment.document !== null && selectedEnvironment.createAudioContext !== null;
  return Object.freeze({
    enabled,
    secure_context: selectedEnvironment.isSecureContext,
    document_visibility: selectedEnvironment.document !== null,
    media_devices: selectedEnvironment.mediaDevices !== null,
    audio_context: selectedEnvironment.createAudioContext !== null,
    audio_worklet_node: selectedEnvironment.createAudioWorkletNode !== null,
    stable_identity: selectedEnvironment.createId !== null,
    capture_pcm_f32: captureSupported,
    playout_pcm_f32: playoutSupported,
    media_recorder_realtime: false,
    output_device_selection: selectedEnvironment.outputDeviceSelection === true && selectedEnvironment.mediaDevices !== null,
    physical_heard_ack: false,
    reasons: Object.freeze(reasons),
  });
}

function requiredText(value: string, field: string): string {
  if (typeof value !== 'string' || value.trim().length === 0) {
    throw new BrowserAudioIOViolation('INVALID_REQUIRED_TEXT', `${field} must be non-empty`);
  }
  return value;
}

function sameResponse(left: Readonly<AudioResponseRef>, right: Readonly<AudioResponseRef>): boolean {
  return left.interaction_id === right.interaction_id && left.response_id === right.response_id && left.response_generation === right.response_generation;
}

function normalizeResponse(response: Readonly<AudioResponseRef>): Readonly<AudioResponseRef> {
  if (typeof response !== 'object' || response === null) {
    throw new BrowserAudioIOViolation('INVALID_RESPONSE', 'response must be an object');
  }
  if (!Number.isSafeInteger(response.response_generation) || response.response_generation < 0) {
    throw new BrowserAudioIOViolation('INVALID_RESPONSE_GENERATION', 'response_generation must be a non-negative safe integer');
  }
  return Object.freeze({
    interaction_id: requiredText(response.interaction_id, 'interaction_id'),
    response_id: requiredText(response.response_id, 'response_id'),
    response_generation: response.response_generation,
  });
}

function defaultMonotonicNowMs(): number {
  return typeof globalThis.performance?.now === 'function' ? globalThis.performance.now() : Number.NaN;
}

function readMonotonicNow(clock: () => number): number | null {
  try {
    const value = clock();
    return Number.isFinite(value) && value >= 0 ? value : null;
  } catch {
    return null;
  }
}

function safeBoolean(value: unknown): boolean | null {
  return typeof value === 'boolean' ? value : null;
}

function safePositiveInteger(value: unknown): number | null {
  return Number.isSafeInteger(value) && (value as number) > 0 ? (value as number) : null;
}

function errorName(error: unknown): string {
  if (typeof error === 'object' && error !== null && 'name' in error && typeof error.name === 'string') return error.name;
  return '';
}

function mapBrowserFailure(error: unknown, fallbackReason: string): BrowserAudioIOViolation {
  if (error instanceof BrowserAudioIOViolation) return error;
  if (error instanceof AudioPortViolation) return new BrowserAudioIOViolation(error.reason, error.message);
  const name = errorName(error);
  if (name === 'NotAllowedError' || name === 'SecurityError') {
    return new BrowserAudioIOViolation('MICROPHONE_PERMISSION_DENIED', 'microphone permission was denied');
  }
  if (name === 'NotFoundError' || name === 'DevicesNotFoundError') {
    return new BrowserAudioIOViolation('AUDIO_INPUT_NOT_FOUND', 'no matching audio input device is available', true);
  }
  if (name === 'OverconstrainedError' || name === 'ConstraintNotSatisfiedError') {
    return new BrowserAudioIOViolation('AUDIO_CONSTRAINT_UNSATISFIED', 'the requested audio input constraint is unsupported');
  }
  if (name === 'NotReadableError' || name === 'TrackStartError' || name === 'AbortError') {
    return new BrowserAudioIOViolation('AUDIO_DEVICE_UNAVAILABLE', 'the audio device could not be started', true);
  }
  return new BrowserAudioIOViolation(fallbackReason, 'browser audio operation failed', true);
}

function mapAudioContextFailure(error: unknown, fallbackReason: string): BrowserAudioIOViolation {
  if (error instanceof BrowserAudioIOViolation) return error;
  const name = errorName(error);
  if (name === 'NotAllowedError' || name === 'SecurityError') {
    return new BrowserAudioIOViolation('AUDIO_USER_ACTIVATION_REQUIRED', 'browser audio requires an active user gesture');
  }
  return new BrowserAudioIOViolation(fallbackReason, 'browser AudioContext operation failed', true);
}

function mapAudioOutputFailure(error: unknown): BrowserAudioIOViolation {
  if (error instanceof BrowserAudioIOViolation) return error;
  const name = errorName(error);
  if (name === 'NotAllowedError' || name === 'SecurityError') {
    return new BrowserAudioIOViolation('AUDIO_OUTPUT_PERMISSION_DENIED', 'audio output selection was denied');
  }
  if (name === 'NotFoundError') {
    return new BrowserAudioIOViolation('AUDIO_OUTPUT_NOT_FOUND', 'the selected audio output is unavailable', true);
  }
  if (name === 'InvalidStateError') {
    return new BrowserAudioIOViolation('AUDIO_OUTPUT_CONTEXT_INVALID', 'the AudioContext cannot select an output', true);
  }
  return new BrowserAudioIOViolation('AUDIO_OUTPUT_SELECTION_FAILED', 'audio output selection failed', true);
}

function stopStream(stream: BrowserMediaStreamLike | null): boolean {
  if (stream === null) return false;
  let failed = false;
  for (const track of stream.getTracks()) {
    try {
      track.stop();
    } catch {
      failed = true;
    }
  }
  return failed;
}

export interface BrowserAudioIOAdapterOptions {
  readonly enabled: boolean;
  readonly environment?: BrowserAudioEnvironment;
  readonly observer?: BrowserAudioObserver;
  readonly captureStreamFactory?: BrowserAudioCaptureStreamFactory;
  readonly captureWorkletModuleUrl?: string;
  readonly monotonicNowMs?: () => number;
  readonly playoutStartupLeadMs?: number;
  readonly c019DiagnosticsEnabled?: boolean;
}

export class BrowserAudioIOAdapter {
  readonly #enabled: boolean;
  readonly #environment: BrowserAudioEnvironment;
  readonly #observer: BrowserAudioObserver;
  readonly #captureStreamFactory: BrowserAudioCaptureStreamFactory | null;
  readonly #captureWorkletModuleUrl: string;
  readonly #monotonicNowMs: () => number;
  readonly #playoutStartupLeadSeconds: number;
  readonly #audioPort = new AudioPort();
  readonly #seenCaptureIds = new Set<string>();
  readonly #onVisibilityChange: BrowserEventListener;
  readonly #onPlayoutDeviceChange: BrowserEventListener;
  #captureState: BrowserAudioCaptureState = 'idle';
  #playoutState: BrowserAudioPlayoutState = 'locked';
  #captureToken = 0;
  #pendingCaptureToken: number | null = null;
  #pendingCaptureResources: PendingCaptureResources | null = null;
  #capture: CaptureSession | null = null;
  #captureCleanupPromise: Promise<void> | null = null;
  #captureStopPromise: Promise<boolean> | null = null;
  #playoutContext: BrowserAudioContextLike | null = null;
  #playback: PlaybackSession | null = null;
  #lastLocallyStoppedResponse: Readonly<AudioResponseRef> | null = null;
  #playoutSourceCleanupFailure: BrowserAudioIOViolation | null = null;
  #playoutGeneration = 0;
  #pendingPlayoutGeneration: number | null = null;
  #pageHiddenPlayoutGeneration: number | null = null;
  #playoutDeviceId: string | null = null;
  #playoutDeviceListenerAttached = false;
  #playoutSinkExplicit = false;
  #playbackMutationToken = 0;
  #closed = false;
  #closePromise: Promise<void> | null = null;
  #visibilityListening = false;

  constructor(options: Readonly<BrowserAudioIOAdapterOptions>) {
    if (options.c019DiagnosticsEnabled === true) {
      enableBrowserC019PlayoutDiagnostics();
    }
    this.#enabled = options.enabled;
    this.#environment = this.#enabled ? (options.environment ?? defaultBrowserAudioEnvironment()) : DISABLED_BROWSER_AUDIO_ENVIRONMENT;
    this.#observer = options.observer ?? {};
    this.#captureStreamFactory = this.#enabled ? (options.captureStreamFactory ?? null) : null;
    this.#captureWorkletModuleUrl = options.captureWorkletModuleUrl ?? new URL('./liveVoiceCaptureProcessor.js', import.meta.url).href;
    this.#monotonicNowMs = options.monotonicNowMs ?? defaultMonotonicNowMs;
    this.#playoutStartupLeadSeconds = requirePlayoutStartupLeadMs(
      options.playoutStartupLeadMs ?? PLAYOUT_STARTUP_LEAD_BASELINE_MS,
    ) / 1000;
    this.#onVisibilityChange = () => {
      if (this.#closed || this.#environment.document?.visibilityState !== 'hidden') return;
      if (this.#pendingPlayoutGeneration !== null) this.#pageHiddenPlayoutGeneration = this.#pendingPlayoutGeneration;
      ++this.#playoutGeneration;
      const playback = this.#playback;
      if (playback !== null) {
        try {
          if (!this.stopPlayout(playback.response, 'page_hidden') && this.#playback === playback) {
            ++this.#playbackMutationToken;
            this.#lastLocallyStoppedResponse = playback.response;
            this.#stopPlaybackSources(playback, 'page_hidden_stop_failed');
          }
        } catch {
          ++this.#playbackMutationToken;
          this.#lastLocallyStoppedResponse = playback.response;
          this.#stopPlaybackSources(playback, 'page_hidden_stop_failed');
        }
      }
      void this.stopCapture('page_hidden').catch(() => {
        this.#emitCaptureState('failed', 'capture_cleanup_failed', null);
      });
    };
    this.#onPlayoutDeviceChange = () => void this.#observePlayoutDeviceChange(this.#playoutGeneration);
  }

  capability(): Readonly<BrowserAudioPlatformCapability> {
    return inspectBrowserAudioPlatform(this.#enabled, this.#environment);
  }

  captureState(): BrowserAudioCaptureState {
    return this.#captureState;
  }

  playoutState(): BrowserAudioPlayoutState {
    return this.#playoutState;
  }

  async startCapture(input: Readonly<{ deviceId?: string }> = {}): Promise<Readonly<BrowserAudioCaptureMetadata>> {
    if (this.#closed) throw new BrowserAudioIOViolation('ADAPTER_CLOSED', 'browser audio adapter is closed');
    const capability = this.capability();
    if (!capability.capture_pcm_f32) {
      throw new BrowserAudioIOViolation(capability.reasons[0] ?? 'CAPTURE_UNSUPPORTED', 'browser audio capture is unavailable');
    }
    if (this.#captureStopPromise !== null || this.#captureCleanupPromise !== null) {
      throw new BrowserAudioIOViolation('CAPTURE_STOP_IN_PROGRESS', 'prior browser capture cleanup is still in progress');
    }
    if (this.#capture !== null || this.#pendingCaptureToken !== null) {
      throw new BrowserAudioIOViolation('CAPTURE_ALREADY_ACTIVE', 'only one browser capture may be active');
    }
    if (this.#environment.document?.visibilityState === 'hidden') {
      throw new BrowserAudioIOViolation('PAGE_HIDDEN', 'capture requires a visible page');
    }

    const mediaDevices = this.#environment.mediaDevices as BrowserMediaDevicesLike;
    const createContext = this.#environment.createAudioContext as () => BrowserAudioContextLike;
    const createWorkletNode = this.#environment.createAudioWorkletNode as NonNullable<BrowserAudioEnvironment['createAudioWorkletNode']>;
    const createId = this.#environment.createId as () => string;
    const token = ++this.#captureToken;
    this.#pendingCaptureToken = token;
    let rejectRevocation: (failure: BrowserAudioIOViolation) => void = () => undefined;
    const revocation = new Promise<never>((_resolve, reject) => {
      rejectRevocation = reject;
    });
    let permissionObservation: CapturePermissionObservation;
    permissionObservation = {
      token,
      onChange: () => this.#observeMicrophonePermissionChange(permissionObservation),
      revocation,
      rejectRevocation,
      status: null,
      lastKnownState: null,
      mediaAccessGranted: false,
      listenerAttached: false,
      closed: false,
      revocationFailure: null,
    };
    const pending: PendingCaptureResources = {
      token,
      stream: null,
      track: null,
      context: null,
      source: null,
      worklet: null,
      onTrackEnded: () => {
        if (this.#pendingCaptureToken === token || this.#capture?.token === token) {
          this.#stopCaptureFromBrowser(this.#capture?.token === token ? 'track_ended' : 'track_ended_during_start');
        }
      },
      onDeviceChange: () => void this.#observeDeviceChange(token),
      onContextStateChange: () => {
        if (
          (this.#pendingCaptureToken === token || this.#capture?.token === token) &&
          pending.contextHasRun &&
          pending.context !== null &&
          pending.context.state !== 'running'
        ) {
          this.#stopCaptureFromBrowser(this.#capture?.token === token ? 'audio_context_not_running' : 'audio_context_lost_during_start');
        }
      },
      priorContextStateChange: null,
      installedContextStateChange: null,
      ownsContext: true,
      permissionObservation,
      requestedDeviceId: null,
      trackListenerAttached: false,
      deviceListenerAttached: false,
      contextHasRun: false,
      cleanupPromise: null,
    };
    this.#pendingCaptureResources = pending;

    let stream: BrowserMediaStreamLike | null = null;
    let mediaAcquisition: Promise<BrowserMediaStreamLike> | null = null;
    let context: BrowserAudioContextLike | null = null;
    let source: BrowserAudioNodeLike | null = null;
    let worklet: BrowserAudioWorkletNodeLike | null = null;
    let startedSession: CaptureSession | null = null;
    try {
      this.#listenForVisibility();
      this.#emitCaptureState('starting', 'start_requested', null, token);
      void this.#attachMicrophonePermissionObservation(permissionObservation);
      this.#requireCurrentCaptureToken(token);
      pending.deviceListenerAttached = true;
      mediaDevices.addEventListener('devicechange', pending.onDeviceChange);
      this.#requireCurrentCaptureToken(token);
      const deviceId = typeof input.deviceId === 'string' && input.deviceId.trim() ? input.deviceId.trim() : null;
      pending.requestedDeviceId = deviceId;
      const audioConstraints: MediaTrackConstraints = {
        echoCancellation: { ideal: true },
        noiseSuppression: { ideal: true },
        autoGainControl: { ideal: true },
        channelCount: { ideal: 1 },
        ...(deviceId === null ? {} : { deviceId: { exact: deviceId } }),
      };
      const mediaConstraints = { audio: audioConstraints, video: false } as const;
      mediaAcquisition = this.#captureStreamFactory === null
        ? mediaDevices.getUserMedia(mediaConstraints)
        : this.#captureStreamFactory(mediaConstraints);
      stream = await Promise.race([mediaAcquisition, permissionObservation.revocation]);
      if (this.#ownsCapturePermissionObservation(permissionObservation)) {
        permissionObservation.mediaAccessGranted = true;
        if (permissionObservation.lastKnownState === 'denied') {
          this.#revokeMicrophonePermission(permissionObservation);
        }
      }
      if (this.#pendingCaptureResources !== pending || this.#pendingCaptureToken !== token) {
        stopStream(stream);
        stream = null;
        throw new BrowserAudioIOViolation('CAPTURE_CANCELLED', 'capture startup was fenced before media acquisition completed');
      }
      pending.stream = stream;
      this.#requireCurrentCaptureToken(token);
      const tracks = stream.getAudioTracks();
      if (tracks.length !== 1 || tracks[0].kind !== 'audio') {
        throw new BrowserAudioIOViolation('INVALID_AUDIO_TRACK_COUNT', 'capture requires exactly one audio track');
      }
      const track = tracks[0];
      requiredText(track.id, 'track_id');
      pending.track = track;
      track.addEventListener('ended', pending.onTrackEnded);
      pending.trackListenerAttached = true;
      if (track.readyState !== undefined && track.readyState !== 'live') {
        throw new BrowserAudioIOViolation('AUDIO_TRACK_ENDED', 'the audio input track ended during startup');
      }
      const unlockedPlayoutContext = this.#playoutContext;
      if (unlockedPlayoutContext !== null && unlockedPlayoutContext.state === 'running') {
        context = unlockedPlayoutContext;
        pending.ownsContext = false;
      } else {
        try {
          context = createContext();
        } catch (error) {
          throw mapAudioContextFailure(error, 'AUDIO_CONTEXT_CREATE_FAILED');
        }
      }
      pending.context = context;
      pending.priorContextStateChange = context.onstatechange;
      const installedContextStateChange = () => {
        pending.priorContextStateChange?.();
        pending.onContextStateChange();
      };
      pending.installedContextStateChange = installedContextStateChange;
      context.onstatechange = installedContextStateChange;
      if (!Number.isSafeInteger(context.sampleRate) || context.sampleRate <= 0) {
        throw new BrowserAudioIOViolation('INVALID_AUDIO_CONTEXT_RATE', 'AudioContext sample rate is invalid');
      }
      const frameSamples = audioFrameSamples(context.sampleRate);
      if (context.state === 'suspended') {
        try {
          await Promise.race([context.resume(), permissionObservation.revocation]);
        } catch (error) {
          throw mapAudioContextFailure(error, 'AUDIO_CONTEXT_RESUME_FAILED');
        }
      }
      this.#requireCurrentCaptureToken(token);
      if (context.state !== 'running') {
        throw new BrowserAudioIOViolation('AUDIO_USER_ACTIVATION_REQUIRED', 'AudioContext did not enter running state');
      }
      pending.contextHasRun = true;
      if (context.audioWorklet === undefined) {
        throw new BrowserAudioIOViolation('AUDIO_WORKLET_UNAVAILABLE', 'AudioWorklet is unavailable in this context');
      }
      try {
        await Promise.race([context.audioWorklet.addModule(this.#captureWorkletModuleUrl), permissionObservation.revocation]);
      } catch (error) {
        if (error instanceof BrowserAudioIOViolation) throw error;
        throw new BrowserAudioIOViolation('AUDIO_WORKLET_LOAD_FAILED', 'the capture AudioWorklet module could not be loaded', true);
      }
      this.#requireCurrentCaptureToken(token);
      const sampleRateHz = context.sampleRate;
      worklet = createWorkletNode(context, CAPTURE_PROCESSOR_NAME, {
        numberOfInputs: 1,
        numberOfOutputs: 0,
        channelCount: 1,
        channelCountMode: 'explicit',
        processorOptions: Object.freeze({
          captureGeneration: token,
          frameDurationMs: LIVE_VOICE_AUDIO_FRAME_DURATION_MS,
        }),
      });
      pending.worklet = worklet;
      source = context.createMediaStreamSource(stream);
      pending.source = source;
      const settings = track.getSettings();
      const captureId = requiredText(createId(), 'capture_id');
      if (this.#seenCaptureIds.has(captureId)) {
        throw new BrowserAudioIOViolation('CAPTURE_ID_REUSED', 'capture identifiers cannot be reused');
      }
      this.#seenCaptureIds.add(captureId);
      const metadata = Object.freeze({
        capture_id: captureId,
        capture_generation: token,
        track_id: track.id,
        requested_device: deviceId === null ? ('default' as const) : ('exact' as const),
        requested_processing: Object.freeze({
          echo_cancellation: true as const,
          noise_suppression: true as const,
          auto_gain_control: true as const,
          channel_count: 1 as const,
        }),
        actual_processing: Object.freeze({
          echo_cancellation: safeBoolean(settings.echoCancellation),
          noise_suppression: safeBoolean(settings.noiseSuppression),
          auto_gain_control: safeBoolean(settings.autoGainControl),
          track_sample_rate_hz: safePositiveInteger(settings.sampleRate),
          track_channel_count: safePositiveInteger(settings.channelCount),
          device_id_present: typeof settings.deviceId === 'string' && settings.deviceId.length > 0,
        }),
        frame_format: Object.freeze({
          encoding: 'pcm_f32' as const,
          sample_rate_hz: sampleRateHz,
          channel_count: 1 as const,
          frame_duration_ms: LIVE_VOICE_AUDIO_FRAME_DURATION_MS,
          samples_per_channel: frameSamples,
        }),
      });
      const onTrackEnded = pending.onTrackEnded;
      let reportedTrackMuted: boolean | null = null;
      const onTrackMute = () => {
        if (this.#capture?.token === token && reportedTrackMuted !== true) {
          reportedTrackMuted = true;
          this.#emitCaptureState('active', 'track_muted', metadata);
        }
      };
      const onTrackUnmute = () => {
        if (this.#capture?.token === token && reportedTrackMuted !== false) {
          reportedTrackMuted = false;
          this.#emitCaptureState('active', 'track_unmuted', metadata);
        }
      };
      const onDeviceChange = pending.onDeviceChange;
      const onContextStateChange = pending.onContextStateChange;
      const session: CaptureSession = {
        token,
        metadata,
        stream,
        track,
        context,
        source,
        worklet,
        onTrackEnded,
        onTrackMute,
        onTrackUnmute,
        onDeviceChange,
        onContextStateChange,
        priorContextStateChange: pending.priorContextStateChange,
        installedContextStateChange,
        ownsContext: pending.ownsContext,
        permissionObservation,
        requestedDeviceId: pending.requestedDeviceId,
        expectedSeq: 0,
        closed: false,
      };
      startedSession = session;
      worklet.port.onmessage = event => this.#handleCaptureMessage(session, event.data);
      worklet.onprocessorerror = () => this.#stopCaptureFromBrowser('audio_processor_error');
      track.addEventListener('mute', onTrackMute);
      track.addEventListener('unmute', onTrackUnmute);
      context.onstatechange = installedContextStateChange;
      this.#requireCurrentCaptureToken(token);
      if ((track.readyState !== undefined && track.readyState !== 'live') || context.state !== 'running') {
        throw new BrowserAudioIOViolation('CAPTURE_STARTUP_LOST', 'audio input or AudioContext was lost during startup');
      }
      if (track.muted === true) {
        throw new BrowserAudioIOViolation('AUDIO_INPUT_MUTED', 'audio input is muted during capture startup');
      }
      this.#capture = session;
      pending.deviceListenerAttached = false;
      this.#pendingCaptureToken = null;
      this.#pendingCaptureResources = null;
      source.connect(worklet);
      this.#emitCaptureState('active', 'capture_started', metadata);
      if (this.#capture !== session || token !== this.#captureToken) {
        throw new BrowserAudioIOViolation('CAPTURE_CANCELLED', 'capture was fenced during active handoff');
      }
      return metadata;
    } catch (error) {
      const cancelled = token !== this.#captureToken;
      if (error === permissionObservation.revocationFailure && mediaAcquisition !== null && stream === null) {
        void mediaAcquisition.then(
          lateStream => {
            try {
              stopStream(lateStream);
            } catch {
              // The fenced startup cannot recover a malformed late browser stream.
            }
          },
          () => undefined
        );
      }
      let cleanupFailure: unknown = null;
      const cleanupOperation = startedSession === null ? this.#cleanupPendingCapture(pending) : this.#cleanupCaptureSession(startedSession);
      this.#captureCleanupPromise = cleanupOperation;
      if (this.#capture?.token === token) this.#capture = null;
      if (this.#pendingCaptureToken === token) this.#pendingCaptureToken = null;
      if (this.#pendingCaptureResources === pending) this.#pendingCaptureResources = null;
      try {
        await cleanupOperation;
      } catch (cleanupError) {
        cleanupFailure = cleanupError;
      } finally {
        if (this.#captureCleanupPromise === cleanupOperation) this.#captureCleanupPromise = null;
      }
      if (this.#unlistenForVisibilityWhenIdle() && cleanupFailure === null) {
        cleanupFailure = new BrowserAudioIOViolation('CAPTURE_CLEANUP_FAILED', 'browser visibility listener could not be removed', true);
      }
      if (cleanupFailure !== null) {
        const mapped = mapBrowserFailure(cleanupFailure, 'CAPTURE_CLEANUP_FAILED');
        this.#emitCaptureState('failed', mapped.reason.toLowerCase(), null, token);
        throw mapped;
      }
      if (cancelled) {
        if (permissionObservation.revocationFailure !== null) throw permissionObservation.revocationFailure;
        throw new BrowserAudioIOViolation('CAPTURE_CANCELLED', 'capture was stopped before startup completed');
      }
      const mapped = mapBrowserFailure(error, 'CAPTURE_START_FAILED');
      this.#emitCaptureState('failed', mapped.reason.toLowerCase(), null, token);
      throw mapped;
    }
  }

  stopCapture(reason = 'requested'): Promise<boolean> {
    if (this.#captureStopPromise !== null) return this.#captureStopPromise;
    if (this.#captureCleanupPromise !== null) return this.#captureCleanupPromise.then(() => false);
    let resolveStop: (value: boolean) => void = () => undefined;
    let rejectStop: (reason?: unknown) => void = () => undefined;
    const operation = new Promise<boolean>((resolve, reject) => {
      resolveStop = resolve;
      rejectStop = reject;
    });
    this.#captureStopPromise = operation;
    void this.#stopCaptureResources(reason).then(resolveStop, rejectStop);
    const clearOperation = () => {
      if (this.#captureStopPromise === operation) this.#captureStopPromise = null;
    };
    void operation.then(clearOperation, clearOperation);
    return operation;
  }

  async #stopCaptureResources(reason: string): Promise<boolean> {
    const session = this.#capture;
    const pending = this.#pendingCaptureResources;
    const hadCapture = session !== null || this.#pendingCaptureToken !== null;
    if (!hadCapture) return false;
    ++this.#captureToken;
    this.#pendingCaptureToken = null;
    this.#pendingCaptureResources = null;
    this.#capture = null;
    this.#emitCaptureState('stopping', reason, session?.metadata ?? null);
    let cleanupFailure: unknown = this.#unlistenForVisibilityWhenIdle()
      ? new BrowserAudioIOViolation('CAPTURE_CLEANUP_FAILED', 'browser visibility listener could not be removed', true)
      : null;
    if (session !== null || pending !== null) {
      try {
        if (session !== null) await this.#cleanupCaptureSession(session);
        else if (pending !== null) await this.#cleanupPendingCapture(pending);
      } catch (error) {
        cleanupFailure ??= error;
      }
    }
    if (cleanupFailure !== null) {
      const mapped = mapBrowserFailure(cleanupFailure, 'CAPTURE_CLEANUP_FAILED');
      this.#emitCaptureState('failed', mapped.reason.toLowerCase(), session?.metadata ?? null);
      throw mapped;
    }
    this.#emitCaptureState('stopped', reason, session?.metadata ?? null);
    return true;
  }

  async unlockPlayout(input: Readonly<{ deviceId?: string }> = {}): Promise<Readonly<BrowserAudioPlayoutMetadata>> {
    if (this.#closed) throw new BrowserAudioIOViolation('ADAPTER_CLOSED', 'browser audio adapter is closed');
    this.#requirePlayoutSourceCleanupHealthy();
    if (!this.#enabled) throw new BrowserAudioIOViolation('FEATURE_DISABLED', 'browser audio is disabled');
    if (!this.#environment.isSecureContext) throw new BrowserAudioIOViolation('INSECURE_CONTEXT', 'browser audio requires a secure context');
    if (this.#environment.document === null) {
      throw new BrowserAudioIOViolation('DOCUMENT_VISIBILITY_UNAVAILABLE', 'browser playout requires document lifecycle visibility');
    }
    if (this.#environment.document?.visibilityState === 'hidden') {
      throw new BrowserAudioIOViolation('PAGE_HIDDEN', 'playout unlock requires a visible page');
    }
    const createContext = this.#environment.createAudioContext;
    if (createContext === null) throw new BrowserAudioIOViolation('AUDIO_CONTEXT_UNAVAILABLE', 'AudioContext is unavailable');
    const deviceId = typeof input.deviceId === 'string' && input.deviceId.trim() ? input.deviceId.trim() : null;
    if (deviceId !== null && (this.#environment.outputDeviceSelection !== true || this.#environment.mediaDevices === null)) {
      throw new BrowserAudioIOViolation('AUDIO_OUTPUT_SELECTION_UNAVAILABLE', 'browser output device selection is unavailable');
    }
    if (this.#pendingPlayoutGeneration !== null) {
      throw new BrowserAudioIOViolation('PLAYOUT_UNLOCK_IN_PROGRESS', 'browser playout unlock is already in progress');
    }
    const generation = ++this.#playoutGeneration;
    this.#pendingPlayoutGeneration = generation;
    try {
      this.#listenForVisibility();
      if (this.#playoutContext === null || this.#playoutContext.state === 'closed') {
        this.#playoutContext = null;
        this.#playoutSinkExplicit = false;
        if (this.#unbindPlayoutDeviceSelection()) {
          throw new BrowserAudioIOViolation('AUDIO_OUTPUT_DEVICE_LISTENER_CLEANUP_FAILED', 'audio output device monitoring could not be released', true);
        }
        this.#playoutContext = createContext();
      }
      const context = this.#playoutContext;
      if (deviceId !== null) {
        if (typeof context.setSinkId !== 'function') {
          throw new BrowserAudioIOViolation('AUDIO_OUTPUT_SELECTION_UNAVAILABLE', 'AudioContext output selection is unavailable');
        }
        try {
          await context.setSinkId(deviceId);
        } catch (error) {
          this.#requireCurrentPlayoutUnlock(generation, context);
          throw mapAudioOutputFailure(error);
        }
        this.#playoutSinkExplicit = true;
        this.#requireCurrentPlayoutUnlock(generation, context);
      } else if (this.#playoutSinkExplicit) {
        if (typeof context.setSinkId !== 'function') {
          throw new BrowserAudioIOViolation('AUDIO_OUTPUT_SELECTION_UNAVAILABLE', 'AudioContext output selection is unavailable');
        }
        try {
          await context.setSinkId('');
        } catch (error) {
          this.#requireCurrentPlayoutUnlock(generation, context);
          throw mapAudioOutputFailure(error);
        }
        this.#playoutSinkExplicit = false;
        this.#requireCurrentPlayoutUnlock(generation, context);
      }
      if (context.state === 'suspended') {
        try {
          await context.resume();
        } catch (error) {
          this.#requireCurrentPlayoutUnlock(generation, context);
          throw mapAudioContextFailure(error, 'AUDIO_CONTEXT_RESUME_FAILED');
        }
      }
      this.#requireCurrentPlayoutUnlock(generation, context);
      if (context.state !== 'running') {
        this.#emitPlayoutState('failed', 'user_activation_required', null);
        throw new BrowserAudioIOViolation('AUDIO_USER_ACTIVATION_REQUIRED', 'AudioContext did not enter running state');
      }
      if (!Number.isSafeInteger(context.sampleRate) || context.sampleRate <= 0) {
        this.#emitPlayoutState('failed', 'invalid_audio_context_rate', null);
        throw new BrowserAudioIOViolation('INVALID_AUDIO_CONTEXT_RATE', 'AudioContext sample rate is invalid');
      }
      if (context.onstatechange === null) {
        context.onstatechange = () => {
          if (this.#playoutContext !== context || context.state === 'running') return;
          const playback = this.#playback;
          if (playback !== null) this.stopPlayout(playback.response, 'audio_context_not_running');
          this.#emitPlayoutState('failed', 'audio_context_not_running', playback);
        };
      }
      this.#requireCurrentPlayoutUnlock(generation, context);
      this.#bindPlayoutDeviceSelection(deviceId);
      this.#emitPlayoutState('ready', 'playout_unlocked', null);
      this.#requireCurrentPlayoutUnlock(generation, context);
      return Object.freeze({
        encoding: 'pcm_f32' as const,
        sample_rate_hz: context.sampleRate,
        channel_count: 1 as const,
        output_device_selection: deviceId !== null,
        physical_heard_ack: false as const,
      });
    } catch (error) {
      const mapped =
        error instanceof BrowserAudioIOViolation ? error : mapAudioContextFailure(error, 'AUDIO_CONTEXT_CREATE_FAILED');
      // Once an exact sink is requested (or an exact sink is being reset), a
      // failed unlock cannot leave an older ready route admissible. Recovery is
      // always another explicit unlock; there is no silent output fallback.
      if (!this.#closed && (deviceId !== null || this.#playoutSinkExplicit)) {
        this.#emitPlayoutState('failed', mapped.reason.toLowerCase(), null);
      }
      throw mapped;
    } finally {
      if (this.#pendingPlayoutGeneration === generation) this.#pendingPlayoutGeneration = null;
      if (this.#pageHiddenPlayoutGeneration === generation) this.#pageHiddenPlayoutGeneration = null;
      if (this.#playoutContext === null && this.#unlistenForVisibilityWhenIdle()) {
        throw new BrowserAudioIOViolation('PLAYOUT_CLEANUP_FAILED', 'browser visibility listener could not be removed after playout unlock failed', true);
      }
    }
  }

  beginPlayout(
    response: Readonly<AudioResponseRef>,
    options: Readonly<{ continuation_unit_id?: string }> = {},
  ): void {
    if (this.#closed) throw new BrowserAudioIOViolation('ADAPTER_CLOSED', 'browser audio adapter is closed');
    this.#requirePlayoutSourceCleanupHealthy();
    if (this.#environment.document?.visibilityState === 'hidden') {
      throw new BrowserAudioIOViolation('PAGE_HIDDEN', 'playout cannot begin while the page is hidden');
    }
    const context = this.#playoutContext;
    if (context === null || context.state !== 'running' || ['locked', 'failed', 'closed'].includes(this.#playoutState)) {
      throw new BrowserAudioIOViolation('PLAYOUT_NOT_UNLOCKED', 'playout must be unlocked by a user action');
    }
    const prior = this.#playback;
    const continuationUnitId =
      options.continuation_unit_id === undefined
        ? null
        : requiredText(options.continuation_unit_id, 'continuation_unit_id');
    let normalizedResponse: Readonly<AudioResponseRef>;
    try {
      normalizedResponse = Object.freeze({
        interaction_id: response.interaction_id,
        response_id: response.response_id,
        response_generation: response.response_generation,
      });
      if (continuationUnitId === null) {
        this.#audioPort.begin(normalizedResponse);
      } else {
        this.#audioPort.continueResponse(normalizedResponse, continuationUnitId);
      }
    } catch (error) {
      throw mapBrowserFailure(error, 'PLAYOUT_BEGIN_FAILED');
    }
    const mutationToken = ++this.#playbackMutationToken;
    if (prior !== null) {
      if (continuationUnitId === null) this.#audioPort.stopLocal(prior.response);
      const cleanup = this.#stopPlaybackSources(
        prior,
        continuationUnitId === null ? 'response_replaced' : 'response_continued',
        false,
      );
      if (this.#playbackCleanupUnknown(cleanup)) {
        this.#audioPort.stopLocal(normalizedResponse);
        this.#lastLocallyStoppedResponse = normalizedResponse;
        this.#emitPlayoutState('failed', 'response_replaced_source_unknown', prior);
        throw new BrowserAudioIOViolation('PLAYOUT_SOURCE_CLEANUP_UNKNOWN', 'the replaced browser sources could not be confirmed stopped and disconnected');
      }
    }
    const playback: PlaybackSession = {
      response: normalizedResponse,
      sources: new Map(),
      completed: new Map(),
      acknowledged: new Map(),
      units: new Set(),
      nextStartTime: context.currentTime + this.#playoutStartupLeadSeconds,
      stopped: false,
    };
    this.#playback = playback;
    reportBrowserC019PlayoutDiagnostic('info', {
      event: 'audio_playout_began',
      response_generation: normalizedResponse.response_generation,
      continuation: continuationUnitId !== null,
      context_state: context.state,
      context_time_s: context.currentTime,
      next_start_time_s: playback.nextStartTime,
      scheduled_lead_ms: (playback.nextStartTime - context.currentTime) * 1_000,
      active_sources: playback.sources.size,
    });
    if (prior !== null && continuationUnitId === null) {
      this.#emitPlayoutState('stopped', 'response_replaced', prior);
      if (this.#playback !== playback || mutationToken !== this.#playbackMutationToken) {
        throw new BrowserAudioIOViolation('PLAYOUT_REPLACED_DURING_BEGIN', 'playout was replaced by a reentrant observer');
      }
    }
    this.#emitPlayoutState(
      'ready',
      continuationUnitId === null ? 'response_started' : 'response_continued',
      playback,
    );
    if (this.#playback !== playback || mutationToken !== this.#playbackMutationToken) {
      throw new BrowserAudioIOViolation('PLAYOUT_CANCELLED', 'playout was fenced or replaced during observer notification');
    }
  }

  enqueuePlayout(chunk: Readonly<BrowserAudioPcmChunk>): boolean {
    if (this.#closed || this.#playoutSourceCleanupFailure !== null) return false;
    const context = this.#playoutContext;
    const playback = this.#playback;
    if (context === null || context.state !== 'running' || playback === null || playback.stopped) return false;
    if (!sameResponse(playback.response, chunk.response)) return false;
    requiredText(chunk.unit_id, 'unit_id');
    if (chunk.channel_count !== 1 || !Number.isSafeInteger(chunk.sample_rate_hz) || chunk.sample_rate_hz <= 0) {
      throw new BrowserAudioIOViolation('INVALID_PLAYOUT_FORMAT', 'playout requires mono PCM with a positive sample rate');
    }
    if (chunk.sample_rate_hz !== context.sampleRate) {
      throw new BrowserAudioIOViolation('PLAYOUT_SAMPLE_RATE_MISMATCH', 'playout sample rate must match the AudioContext; AIO-B does not resample');
    }
    if (!(chunk.samples instanceof Float32Array) || chunk.samples.length === 0) {
      throw new BrowserAudioIOViolation('INVALID_PLAYOUT_SAMPLES', 'playout samples must be a non-empty Float32Array');
    }
    for (const sample of chunk.samples) {
      if (!Number.isFinite(sample)) {
        throw new BrowserAudioIOViolation('INVALID_PLAYOUT_SAMPLES', 'playout samples must be finite');
      }
    }
    let buffer: BrowserAudioBufferLike;
    try {
      buffer = context.createBuffer(1, chunk.samples.length, chunk.sample_rate_hz);
      buffer.copyToChannel(chunk.samples.slice(), 0);
    } catch {
      throw new BrowserAudioIOViolation('PLAYOUT_BUFFER_FAILED', 'browser playout buffer creation failed', true);
    }
    let accepted: boolean;
    try {
      accepted = this.#audioPort.enqueue({
        response: chunk.response,
        unit_id: chunk.unit_id,
        seq: chunk.seq,
        audio: new Uint8Array(chunk.samples.buffer.slice(chunk.samples.byteOffset, chunk.samples.byteOffset + chunk.samples.byteLength)),
        provider: chunk.provider,
      });
    } catch (error) {
      throw mapBrowserFailure(error, 'PLAYOUT_ENQUEUE_FAILED');
    }
    if (!accepted) return false;
    playback.units.add(chunk.unit_id);
    const sourceKey = `${chunk.unit_id}\u0000${chunk.seq}`;
    let source: BrowserAudioBufferSourceLike | null = null;
    let sourceStartAttempted = false;
    try {
      source = context.createBufferSource();
      source.buffer = buffer;
      source.connect(context.destination);
      const record: PlaybackSourceRecord = { unitId: chunk.unit_id, seq: chunk.seq, source, stopped: false };
      playback.sources.set(sourceKey, record);
      source.onended = () => this.#handlePlaybackEnded(playback, record);
      const startAt = Math.max(context.currentTime, playback.nextStartTime);
      const leadBeforeScheduleMs = (playback.nextStartTime - context.currentTime) * 1_000;
      const schedulingAfterDepletion = chunk.seq > 0 && leadBeforeScheduleMs <= 0;
      if (typeof this.#observer.onPlayoutScheduled === 'function') {
        const startDelayMs = Math.max(0, (startAt - context.currentTime) * 1_000);
        const scheduledFromMonotonic = readMonotonicNow(this.#monotonicNowMs);
        const scheduledStartClock = scheduledFromMonotonic === null
          ? null
          : Object.freeze({
              observed_at: new Date(Date.now() + startDelayMs).toISOString(),
              monotonic_ms: scheduledFromMonotonic + startDelayMs,
            });
        sourceStartAttempted = true;
        source.start(startAt);
        this.#notifyPlayoutScheduled(
          playback,
          chunk.unit_id,
          chunk.seq,
          startDelayMs,
          scheduledStartClock,
          () => (
            this.#playback === playback
            && !playback.stopped
            && context.state === 'running'
            && context.currentTime >= startAt
          )
        );
      } else {
        sourceStartAttempted = true;
        source.start(startAt);
      }
      playback.nextStartTime = startAt + chunk.samples.length / chunk.sample_rate_hz;
      if (chunk.seq === 0 || chunk.seq % 50 === 0 || schedulingAfterDepletion) {
        reportBrowserC019PlayoutDiagnostic(schedulingAfterDepletion ? 'warn' : 'info', {
          event: schedulingAfterDepletion ? 'audio_playout_underrun_recovery' : 'audio_frame_scheduled',
          response_generation: playback.response.response_generation,
          unit_id: chunk.unit_id,
          frame_seq: chunk.seq,
          context_state: context.state,
          context_time_s: context.currentTime,
          start_at_s: startAt,
          next_start_time_s: playback.nextStartTime,
          lead_before_schedule_ms: leadBeforeScheduleMs,
          scheduled_lead_ms: (playback.nextStartTime - context.currentTime) * 1_000,
          active_sources: playback.sources.size,
        });
      }
    } catch {
      playback.sources.delete(sourceKey);
      if (source !== null) {
        source.onended = null;
        let stopCompletedCount = 0;
        let stopFailedCount = 0;
        if (sourceStartAttempted) {
          try {
            source.stop();
            stopCompletedCount = 1;
          } catch {
            stopFailedCount = 1;
          }
        }
        let disconnectCompletedCount = 0;
        let disconnectFailedCount = 0;
        try {
          source.disconnect();
          disconnectCompletedCount = 1;
        } catch {
          disconnectFailedCount = 1;
        }
        this.#latchPlayoutSourceCleanupFailure(
          Object.freeze({
            sourceCount: 1,
            stopCompletedCount,
            stopFailedCount,
            disconnectCompletedCount,
            disconnectFailedCount,
          })
        );
      }
      this.stopPlayout(playback.response, 'source_setup_failed');
      if (this.#playoutSourceCleanupFailure !== null) {
        this.#emitPlayoutState('failed', 'source_setup_cleanup_unknown', playback);
        throw new BrowserAudioIOViolation('PLAYOUT_SOURCE_CLEANUP_UNKNOWN', 'browser source setup cleanup completion is unknown');
      }
      throw new BrowserAudioIOViolation('PLAYOUT_SOURCE_FAILED', 'browser playout source setup failed', true);
    }
    this.#emitPlayoutState('playing', 'chunk_scheduled', playback, chunk.unit_id, chunk.seq);
    return true;
  }

  stopPlayout(response: Readonly<AudioResponseRef>, reason = 'requested'): boolean {
    return this.stopPlayoutExact(response, reason).local_fence_established;
  }

  stopPlayoutExact(response: Readonly<AudioResponseRef>, reason = 'requested'): Readonly<BrowserAudioLocalStopReceipt> {
    const normalizedResponse = normalizeResponse(response);
    const normalizedReason = requiredText(reason, 'reason');
    const requestedAt = readMonotonicNow(this.#monotonicNowMs);
    const businessCancelCountBefore = this.#audioPort.businessCancelCount();
    if (this.#closed) {
      return this.#localStopReceipt('adapter_closed', normalizedResponse, normalizedReason, requestedAt, businessCancelCountBefore);
    }
    if (!this.#enabled) {
      return this.#localStopReceipt('feature_disabled', normalizedResponse, normalizedReason, requestedAt, businessCancelCountBefore);
    }
    const playback = this.#playback;
    if (playback === null) {
      return this.#localStopReceipt(
        this.#lastLocallyStoppedResponse !== null && sameResponse(this.#lastLocallyStoppedResponse, normalizedResponse)
          ? 'already_stopped'
          : 'no_active_target',
        normalizedResponse,
        normalizedReason,
        requestedAt,
        businessCancelCountBefore
      );
    }
    if (!sameResponse(playback.response, normalizedResponse) || playback.stopped) {
      return this.#localStopReceipt('target_mismatch', normalizedResponse, normalizedReason, requestedAt, businessCancelCountBefore);
    }
    const confirmedCursor = this.#snapshotConfirmedCursor(playback);
    try {
      if (!this.#audioPort.stopLocal(normalizedResponse)) {
        return this.#localStopReceipt('local_fence_failed', normalizedResponse, normalizedReason, requestedAt, businessCancelCountBefore, confirmedCursor);
      }
    } catch (error) {
      throw mapBrowserFailure(error, 'PLAYOUT_STOP_FAILED');
    }
    ++this.#playbackMutationToken;
    this.#lastLocallyStoppedResponse = normalizedResponse;
    const cleanup = this.#stopPlaybackSources(playback, normalizedReason);
    return this.#localStopReceipt(
      this.#playbackCleanupUnknown(cleanup) ? 'local_fence_established_source_unknown' : 'local_fence_established',
      normalizedResponse,
      normalizedReason,
      requestedAt,
      businessCancelCountBefore,
      confirmedCursor,
      cleanup
    );
  }

  #stopPlaybackSources(playback: PlaybackSession, reason: string, emitState = true): Readonly<PlaybackSourceCleanupSummary> {
    playback.stopped = true;
    if (this.#playback === playback) this.#playback = null;
    const sourceCount = playback.sources.size;
    let stopCompletedCount = 0;
    let stopFailedCount = 0;
    let disconnectCompletedCount = 0;
    let disconnectFailedCount = 0;
    for (const record of playback.sources.values()) {
      record.stopped = true;
      record.source.onended = null;
      try {
        record.source.stop();
        stopCompletedCount += 1;
      } catch {
        stopFailedCount += 1;
      }
      try {
        record.source.disconnect();
        disconnectCompletedCount += 1;
      } catch {
        disconnectFailedCount += 1;
      }
    }
    playback.sources.clear();
    const summary = Object.freeze({
      sourceCount,
      stopCompletedCount,
      stopFailedCount,
      disconnectCompletedCount,
      disconnectFailedCount,
    });
    this.#latchPlayoutSourceCleanupFailure(summary);
    if (emitState) {
      if (this.#playoutSourceCleanupFailure !== null) this.#emitPlayoutState('failed', `${reason}_source_unknown`, playback);
      else this.#emitPlayoutState('stopped', reason, playback);
    }
    return summary;
  }

  async close(): Promise<void> {
    if (this.#closePromise !== null) return this.#closePromise;
    this.#closed = true;
    ++this.#playoutGeneration;
    ++this.#playbackMutationToken;
    this.#pendingPlayoutGeneration = null;
    let resolveClose: () => void = () => undefined;
    let rejectClose: (reason?: unknown) => void = () => undefined;
    const closePromise = new Promise<void>((resolve, reject) => {
      resolveClose = resolve;
      rejectClose = reject;
    });
    this.#closePromise = closePromise;
    const { context, failure } = this.#fencePlayoutForClose();
    void this.#closeResources(context, failure).then(resolveClose, rejectClose);
    return closePromise;
  }

  businessCancelCount(): number {
    return this.#audioPort.businessCancelCount();
  }

  #snapshotConfirmedCursor(playback: PlaybackSession): readonly Readonly<BrowserAudioConfirmedCursor>[] {
    return Object.freeze(
      [...playback.units].map(unitId =>
        Object.freeze({
          unit_id: unitId,
          contiguous_through_seq: playback.acknowledged.get(unitId) ?? null,
        })
      )
    );
  }

  #playbackCleanupUnknown(cleanup: Readonly<PlaybackSourceCleanupSummary>): boolean {
    return cleanup.stopFailedCount > 0 || cleanup.disconnectFailedCount > 0;
  }

  #latchPlayoutSourceCleanupFailure(cleanup: Readonly<PlaybackSourceCleanupSummary>): void {
    if (!this.#playbackCleanupUnknown(cleanup) || this.#playoutSourceCleanupFailure !== null) return;
    this.#playoutSourceCleanupFailure = new BrowserAudioIOViolation(
      'PLAYOUT_SOURCE_CLEANUP_UNKNOWN',
      'browser source stop or disconnect completion is unknown'
    );
  }

  #requirePlayoutSourceCleanupHealthy(): void {
    if (this.#playoutSourceCleanupFailure === null) return;
    throw new BrowserAudioIOViolation(
      this.#playoutSourceCleanupFailure.reason,
      'browser playout is unavailable after source cleanup completion became unknown',
      this.#playoutSourceCleanupFailure.retriable
    );
  }

  #sourceActionConfirmation(sourceCount: number, completedCount: number, failedCount: number): Readonly<BrowserAudioSourceActionConfirmation> {
    return Object.freeze({
      status: sourceCount === 0 ? ('not_applicable' as const) : failedCount === 0 ? ('completed' as const) : ('unknown' as const),
      attempted_count: completedCount + failedCount,
      completed_count: completedCount,
      failed_count: failedCount,
    });
  }

  #localStopReceipt(
    outcome: BrowserAudioLocalStopOutcome,
    response: Readonly<AudioResponseRef>,
    reason: string,
    requestedAt: number | null,
    businessCancelCountBefore: number,
    confirmedCursor: readonly Readonly<BrowserAudioConfirmedCursor>[] = Object.freeze([]),
    cleanup: Readonly<PlaybackSourceCleanupSummary> | null = null
  ): Readonly<BrowserAudioLocalStopReceipt> {
    const confirmedAt = readMonotonicNow(this.#monotonicNowMs);
    const timingConfirmed = requestedAt !== null && confirmedAt !== null && confirmedAt >= requestedAt;
    const businessCancelCountAfter = this.#audioPort.businessCancelCount();
    const notAttempted = Object.freeze({
      status: 'not_attempted' as const,
      attempted_count: 0,
      completed_count: 0,
      failed_count: 0,
    });
    const stopRequest =
      cleanup === null ? notAttempted : this.#sourceActionConfirmation(cleanup.sourceCount, cleanup.stopCompletedCount, cleanup.stopFailedCount);
    const disconnect =
      cleanup === null ? notAttempted : this.#sourceActionConfirmation(cleanup.sourceCount, cleanup.disconnectCompletedCount, cleanup.disconnectFailedCount);
    return Object.freeze({
      kind: 'browser_audio.local_stop.v1' as const,
      outcome,
      response,
      reason,
      local_fence_established: outcome === 'local_fence_established' || outcome === 'local_fence_established_source_unknown',
      confirmed_cursor_before_stop: confirmedCursor,
      browser_sources: Object.freeze({
        source_count: cleanup?.sourceCount ?? 0,
        stop_request: stopRequest,
        disconnect,
      }),
      timing: Object.freeze({
        status: timingConfirmed ? ('confirmed' as const) : ('unknown' as const),
        requested_at_monotonic_ms: requestedAt,
        confirmed_at_monotonic_ms: confirmedAt,
        duration_ms: timingConfirmed ? confirmedAt - requestedAt : null,
      }),
      physical_heard: 'unproven' as const,
      physical_silence: 'unproven' as const,
      business_cancel_count_before: businessCancelCountBefore,
      business_cancel_count_after: businessCancelCountAfter,
      business_cancel_count_delta: businessCancelCountAfter - businessCancelCountBefore,
    });
  }

  #requireCurrentCaptureToken(token: number): void {
    if (token !== this.#captureToken || this.#pendingCaptureToken !== token) {
      throw new BrowserAudioIOViolation('CAPTURE_CANCELLED', 'capture startup was fenced');
    }
    if (this.#environment.document?.visibilityState === 'hidden') {
      throw new BrowserAudioIOViolation('PAGE_HIDDEN', 'capture startup was fenced because the page is hidden');
    }
  }

  #requireCurrentPlayoutUnlock(generation: number, context: BrowserAudioContextLike): void {
    if (this.#pageHiddenPlayoutGeneration === generation) {
      throw new BrowserAudioIOViolation('PAGE_HIDDEN', 'playout unlock was fenced because the page was hidden');
    }
    if (this.#closed || this.#playoutGeneration !== generation || this.#pendingPlayoutGeneration !== generation || this.#playoutContext !== context) {
      throw new BrowserAudioIOViolation('PLAYOUT_CANCELLED', 'playout unlock was fenced by close or replacement');
    }
    if (this.#environment.document?.visibilityState === 'hidden') {
      throw new BrowserAudioIOViolation('PAGE_HIDDEN', 'playout unlock was fenced because the page is hidden');
    }
    this.#requirePlayoutSourceCleanupHealthy();
  }

  #fencePlayoutForClose(): Readonly<{ context: BrowserAudioContextLike | null; failure: unknown }> {
    const context = this.#playoutContext;
    this.#playoutContext = null;
    this.#playoutSinkExplicit = false;
    let failure: unknown = this.#playoutSourceCleanupFailure;
    if (context !== null) context.onstatechange = null;
    const playback = this.#playback;
    if (playback !== null) {
      try {
        this.#audioPort.stopLocal(playback.response);
      } catch (error) {
        failure ??= error;
      }
      const cleanup = this.#stopPlaybackSources(playback, 'adapter_closed');
      if (this.#playbackCleanupUnknown(cleanup)) failure = this.#playoutSourceCleanupFailure;
    }
    return Object.freeze({ context, failure });
  }

  async #closeResources(context: BrowserAudioContextLike | null, initialFailure: unknown): Promise<void> {
    let failure = initialFailure;
    if (this.#unbindPlayoutDeviceSelection()) {
      failure ??= new BrowserAudioIOViolation('AUDIO_OUTPUT_DEVICE_LISTENER_CLEANUP_FAILED', 'audio output device monitoring could not be released', true);
    }
    const captureCleanup = this.stopCapture('adapter_closed').catch(error => {
      failure ??= error;
    });
    const playoutCleanup = (async () => {
      if (context === null || context.state === 'closed') return;
      try {
        await context.close();
      } catch (error) {
        failure ??= error;
      }
    })();
    await Promise.all([captureCleanup, playoutCleanup]);
    if (this.#unlistenForVisibilityWhenIdle()) {
      failure ??= new BrowserAudioIOViolation('ADAPTER_CLOSE_FAILED', 'browser visibility listener could not be removed', true);
    }
    if (failure !== null) {
      const mapped = mapBrowserFailure(failure, 'ADAPTER_CLOSE_FAILED');
      this.#emitPlayoutState('failed', mapped.reason === 'PLAYOUT_SOURCE_CLEANUP_UNKNOWN' ? 'adapter_closed_source_unknown' : 'adapter_close_failed', null);
      throw mapped;
    }
    this.#emitPlayoutState('closed', 'adapter_closed', null);
  }

  #handleCaptureMessage(session: CaptureSession, data: unknown): void {
    if (this.#capture !== session || session.closed) return;
    try {
      if (typeof data !== 'object' || data === null) {
        throw new BrowserAudioIOViolation('INVALID_AUDIO_WORKLET_MESSAGE', 'AudioWorklet message must be an object');
      }
      const message = data as Record<string, unknown>;
      if (message.kind === 'error') {
        switch (message.reason) {
          case 'input_gap_exceeded':
            throw new BrowserAudioIOViolation('AUDIO_INPUT_GAP_EXCEEDED', 'AudioWorklet input remained unavailable beyond the bounded transient window');
          case 'render_frame_regressed':
            throw new BrowserAudioIOViolation('AUDIO_RENDER_FRAME_REGRESSED', 'AudioWorklet render clock moved backwards');
          case 'render_frame_not_advanced':
            throw new BrowserAudioIOViolation('AUDIO_RENDER_FRAME_NOT_ADVANCED', 'AudioWorklet render clock did not advance');
          case 'invalid_frame_configuration':
            throw new BrowserAudioIOViolation('INVALID_AUDIO_WORKLET_CONFIGURATION', 'AudioWorklet rejected its frame configuration');
          default:
            throw new BrowserAudioIOViolation('AUDIO_WORKLET_GAP', 'AudioWorklet reported an unknown render-input failure');
        }
      }
      if (message.kind !== 'frame' || message.capture_generation !== session.token) {
        throw new BrowserAudioIOViolation('INVALID_AUDIO_WORKLET_MESSAGE', 'AudioWorklet frame identity is invalid');
      }
      if (message.seq !== session.expectedSeq) {
        throw new BrowserAudioIOViolation('NON_CONTIGUOUS_AUDIO_SEQUENCE', `expected capture sequence ${session.expectedSeq}`);
      }
      if (message.sample_rate_hz !== session.metadata.frame_format.sample_rate_hz) {
        throw new BrowserAudioIOViolation('AUDIO_SAMPLE_RATE_CHANGED', 'AudioWorklet sample rate changed during capture');
      }
      const frame = createCapturedAudioFrame({
        capture: {
          capture_id: session.metadata.capture_id,
          capture_generation: session.metadata.capture_generation,
          track_id: session.metadata.track_id,
        },
        seq: message.seq as number,
        sample_cursor: message.sample_cursor as number,
        context_time_s: message.context_time_s as number,
        format: session.metadata.frame_format,
        samples: message.samples as Float32Array,
      });
      session.expectedSeq += 1;
      try {
        this.#observer.onCaptureFrame?.(frame);
      } catch {
        throw new BrowserAudioIOViolation('AUDIO_FRAME_CONSUMER_FAILED', 'the capture frame consumer rejected a frame');
      }
    } catch (error) {
      const mapped = mapBrowserFailure(error, 'AUDIO_WORKLET_PROTOCOL_VIOLATION');
      this.#stopCaptureFromBrowser(mapped.reason.toLowerCase());
    }
  }

  #handlePlaybackEnded(playback: PlaybackSession, record: PlaybackSourceRecord): void {
    if (this.#playback !== playback || playback.stopped || record.stopped) return;
    record.stopped = true;
    playback.sources.delete(`${record.unitId}\u0000${record.seq}`);
    try {
      record.source.disconnect();
    } catch {
      // The render completion remains fenced by the exact playback session.
    }
    const completed = playback.completed.get(record.unitId) ?? new Set<number>();
    completed.add(record.seq);
    playback.completed.set(record.unitId, completed);
    const prior = playback.acknowledged.get(record.unitId) ?? -1;
    let through = prior;
    while (completed.has(through + 1)) through += 1;
    if (through > prior) {
      try {
        this.#audioPort.acknowledge(playback.response, record.unitId, through);
      } catch {
        this.stopPlayout(playback.response, 'render_ack_failed');
        this.#emitPlayoutState('failed', 'render_ack_failed', null);
        return;
      }
      playback.acknowledged.set(record.unitId, through);
      for (let seq = prior + 1; seq <= through; seq += 1) completed.delete(seq);
      const context = this.#playoutContext;
      const scheduledLeadMs = context === null
        ? null
        : (playback.nextStartTime - context.currentTime) * 1_000;
      const scheduleDrained = playback.sources.size === 0 && (scheduledLeadMs === null || scheduledLeadMs <= 0);
      if (record.seq === 0 || record.seq % 50 === 0 || scheduleDrained) {
        reportBrowserC019PlayoutDiagnostic(scheduleDrained ? 'warn' : 'info', {
          event: scheduleDrained ? 'audio_playout_schedule_drained' : 'audio_frame_rendered',
          response_generation: playback.response.response_generation,
          unit_id: record.unitId,
          frame_seq: record.seq,
          contiguous_through_seq: through,
          context_state: context?.state ?? 'unavailable',
          context_time_s: context?.currentTime ?? null,
          next_start_time_s: playback.nextStartTime,
          scheduled_lead_ms: scheduledLeadMs,
          active_sources: playback.sources.size,
        });
      }
      this.#emitPlayoutState('playing', 'render_completed', playback, record.unitId, through);
    }
  }

  async #attachMicrophonePermissionObservation(observation: CapturePermissionObservation): Promise<void> {
    let permissions: BrowserPermissionsLike | null;
    try {
      permissions = this.#environment.permissions ?? null;
    } catch {
      return;
    }
    if (permissions === null || !this.#ownsCapturePermissionObservation(observation)) return;

    let statusValue: unknown;
    try {
      if (typeof permissions.query !== 'function') return;
      statusValue = await permissions.query(Object.freeze({ name: 'microphone' }));
    } catch {
      return;
    }
    if (!this.#ownsCapturePermissionObservation(observation) || typeof statusValue !== 'object' || statusValue === null) return;

    const status = statusValue as BrowserPermissionStatusLike;
    let addListener: BrowserPermissionStatusLike['addEventListener'];
    let removeListener: BrowserPermissionStatusLike['removeEventListener'];
    try {
      addListener = status.addEventListener;
      removeListener = status.removeEventListener;
    } catch {
      return;
    }
    if (typeof addListener !== 'function' || typeof removeListener !== 'function') return;

    observation.lastKnownState = this.#readMicrophonePermissionState(status);
    if (observation.lastKnownState === 'denied' && observation.mediaAccessGranted) {
      this.#revokeMicrophonePermission(observation);
      return;
    }
    observation.status = status;
    observation.listenerAttached = true;
    try {
      addListener.call(status, 'change', observation.onChange);
    } catch {
      this.#closeMicrophonePermissionObservation(observation);
      return;
    }

    if (!this.#ownsCapturePermissionObservation(observation)) {
      this.#removeMicrophonePermissionListener(status, observation.onChange);
      this.#closeMicrophonePermissionObservation(observation);
      return;
    }
    const stateAfterAttach = this.#readMicrophonePermissionState(status);
    if (stateAfterAttach !== null) this.#acceptMicrophonePermissionState(observation, stateAfterAttach);
  }

  #observeMicrophonePermissionChange(observation: CapturePermissionObservation): void {
    if (!this.#ownsCapturePermissionObservation(observation) || observation.status === null) return;
    const state = this.#readMicrophonePermissionState(observation.status);
    if (state !== null) this.#acceptMicrophonePermissionState(observation, state);
  }

  #acceptMicrophonePermissionState(observation: CapturePermissionObservation, state: MicrophonePermissionState): void {
    if (!this.#ownsCapturePermissionObservation(observation)) return;
    const priorState = observation.lastKnownState;
    observation.lastKnownState = state;
    if (state !== 'denied' || (!observation.mediaAccessGranted && priorState !== 'granted' && priorState !== 'prompt')) return;
    this.#revokeMicrophonePermission(observation);
  }

  #revokeMicrophonePermission(observation: CapturePermissionObservation): void {
    if (!this.#ownsCapturePermissionObservation(observation) || observation.revocationFailure !== null) return;
    observation.revocationFailure = new BrowserAudioIOViolation('MICROPHONE_PERMISSION_REVOKED', 'microphone permission was revoked while capture was owned');
    observation.rejectRevocation(observation.revocationFailure);
    this.#stopCaptureFromBrowser('microphone_permission_revoked');
  }

  #readMicrophonePermissionState(status: BrowserPermissionStatusLike): MicrophonePermissionState | null {
    try {
      const state = status.state;
      return state === 'granted' || state === 'prompt' || state === 'denied' ? state : null;
    } catch {
      return null;
    }
  }

  #ownsCapturePermissionObservation(observation: CapturePermissionObservation): boolean {
    if (observation.closed || observation.token !== this.#captureToken) return false;
    return this.#capture?.permissionObservation === observation || this.#pendingCaptureResources?.permissionObservation === observation;
  }

  #removeMicrophonePermissionListener(status: BrowserPermissionStatusLike, listener: BrowserEventListener): void {
    try {
      status.removeEventListener('change', listener);
    } catch {
      // The closed generation fence keeps a retained browser callback inert.
    }
  }

  #closeMicrophonePermissionObservation(observation: CapturePermissionObservation): void {
    if (observation.closed) return;
    observation.closed = true;
    const status = observation.status;
    const listenerAttached = observation.listenerAttached;
    observation.status = null;
    observation.listenerAttached = false;
    if (status !== null && listenerAttached) this.#removeMicrophonePermissionListener(status, observation.onChange);
  }

  async #observeDeviceChange(token: number): Promise<void> {
    if (!this.#ownsCaptureToken(token) || this.#environment.mediaDevices === null) return;
    const requestedDeviceId = this.#capture?.token === token ? this.#capture.requestedDeviceId : this.#pendingCaptureResources?.requestedDeviceId ?? null;
    try {
      const devices = await this.#environment.mediaDevices.enumerateDevices();
      if (!this.#ownsCaptureToken(token)) return;
      const count = devices.filter(device => device.kind === 'audioinput').length;
      this.#notifyDeviceChange(Object.freeze({ audio_input_count: count, reason: 'devicechange' }));
      const exactDeviceAvailable =
        requestedDeviceId === null ||
        devices.some(device => device.kind === 'audioinput' && typeof device.deviceId === 'string' && device.deviceId === requestedDeviceId);
      if ((!exactDeviceAvailable || count === 0) && this.#ownsCaptureToken(token)) {
        this.#stopCaptureFromBrowser(exactDeviceAvailable ? 'audio_input_unavailable' : 'audio_input_selection_lost');
      }
    } catch {
      if (!this.#ownsCaptureToken(token)) return;
      this.#notifyDeviceChange(Object.freeze({ audio_input_count: null, reason: 'enumeration_failed' }));
      if (requestedDeviceId !== null) this.#stopCaptureFromBrowser('audio_input_selection_unverified');
    }
  }

  #bindPlayoutDeviceSelection(deviceId: string | null): void {
    if (deviceId === null) {
      if (this.#unbindPlayoutDeviceSelection()) {
        throw new BrowserAudioIOViolation('AUDIO_OUTPUT_DEVICE_LISTENER_CLEANUP_FAILED', 'audio output device monitoring could not be released', true);
      }
      return;
    }
    if (this.#environment.mediaDevices === null) {
      throw new BrowserAudioIOViolation('AUDIO_OUTPUT_SELECTION_UNAVAILABLE', 'audio output device monitoring is unavailable');
    }
    this.#playoutDeviceId = deviceId;
    if (this.#playoutDeviceListenerAttached) return;
    try {
      this.#environment.mediaDevices.addEventListener('devicechange', this.#onPlayoutDeviceChange);
      this.#playoutDeviceListenerAttached = true;
    } catch {
      try {
        this.#environment.mediaDevices.removeEventListener('devicechange', this.#onPlayoutDeviceChange);
      } catch {
        // The output generation fence makes any partially retained callback inert.
      }
      this.#playoutDeviceId = null;
      throw new BrowserAudioIOViolation('AUDIO_OUTPUT_DEVICE_LISTENER_FAILED', 'audio output device monitoring is unavailable');
    }
  }

  async #observePlayoutDeviceChange(generation: number): Promise<void> {
    const deviceId = this.#playoutDeviceId;
    const mediaDevices = this.#environment.mediaDevices;
    if (this.#closed || deviceId === null || mediaDevices === null || generation !== this.#playoutGeneration) return;
    let reason: string | null = null;
    try {
      const devices = await mediaDevices.enumerateDevices();
      if (this.#closed || deviceId !== this.#playoutDeviceId || generation !== this.#playoutGeneration) return;
      if (!devices.some(device => device.kind === 'audiooutput' && typeof device.deviceId === 'string' && device.deviceId === deviceId)) {
        reason = 'audio_output_selection_lost';
      }
    } catch {
      if (this.#closed || deviceId !== this.#playoutDeviceId || generation !== this.#playoutGeneration) return;
      reason = 'audio_output_selection_unverified';
    }
    if (reason === null) return;
    ++this.#playoutGeneration;
    const listenerCleanupFailed = this.#unbindPlayoutDeviceSelection();
    const playback = this.#playback;
    if (playback !== null) {
      try {
        this.stopPlayout(playback.response, reason);
      } catch {
        this.#stopPlaybackSources(playback, reason);
      }
    }
    this.#emitPlayoutState('failed', reason, playback);
    if (listenerCleanupFailed) this.#emitPlayoutState('failed', 'audio_output_device_listener_cleanup_failed', null);
    this.#stopCaptureFromBrowser(reason);
  }

  #unbindPlayoutDeviceSelection(): boolean {
    let failed = false;
    if (this.#playoutDeviceListenerAttached) {
      try {
        this.#environment.mediaDevices?.removeEventListener('devicechange', this.#onPlayoutDeviceChange);
      } catch {
        failed = true;
      }
    }
    this.#playoutDeviceListenerAttached = false;
    this.#playoutDeviceId = null;
    return failed;
  }

  #ownsCaptureToken(token: number): boolean {
    return this.#capture?.token === token || (this.#pendingCaptureToken === token && this.#pendingCaptureResources?.token === token);
  }

  #stopCaptureFromBrowser(reason: string): void {
    void this.stopCapture(reason).catch(() => {
      this.#emitCaptureState('failed', 'capture_cleanup_failed', null);
    });
  }

  async #cleanupCaptureSession(session: CaptureSession): Promise<void> {
    if (session.closed) return;
    session.closed = true;
    let cleanupFailed = false;
    this.#closeMicrophonePermissionObservation(session.permissionObservation);
    try {
      session.worklet.port.onmessage = null;
    } catch {
      cleanupFailed = true;
    }
    try {
      session.worklet.onprocessorerror = null;
    } catch {
      cleanupFailed = true;
    }
    try {
      if (session.context.onstatechange === session.installedContextStateChange) {
        session.context.onstatechange = session.priorContextStateChange;
      }
    } catch {
      cleanupFailed = true;
    }
    for (const [type, listener] of [
      ['ended', session.onTrackEnded],
      ['mute', session.onTrackMute],
      ['unmute', session.onTrackUnmute],
    ] as const) {
      try {
        session.track.removeEventListener(type, listener);
      } catch {
        cleanupFailed = true;
      }
    }
    try {
      this.#environment.mediaDevices?.removeEventListener('devicechange', session.onDeviceChange);
    } catch {
      cleanupFailed = true;
    }
    try {
      session.source.disconnect();
    } catch {
      // Continue releasing the device and context.
    }
    try {
      session.worklet.disconnect();
    } catch {
      // A zero-output worklet may already be disconnected.
    }
    try {
      session.worklet.port.close();
    } catch {
      cleanupFailed = true;
    }
    try {
      cleanupFailed = stopStream(session.stream) || cleanupFailed;
    } catch {
      cleanupFailed = true;
    }
    let closeOwnedContext = session.ownsContext;
    if (closeOwnedContext) {
      try {
        closeOwnedContext = session.context.state !== 'closed';
      } catch {
        cleanupFailed = true;
      }
    }
    if (closeOwnedContext) {
      try {
        await session.context.close();
      } catch {
        cleanupFailed = true;
      }
    }
    if (cleanupFailed) {
      throw new BrowserAudioIOViolation('CAPTURE_CLEANUP_FAILED', 'one or more browser capture resources could not be released', true);
    }
  }

  #cleanupPendingCapture(pending: PendingCaptureResources): Promise<void> {
    if (pending.cleanupPromise !== null) return pending.cleanupPromise;
    pending.cleanupPromise = (async () => {
      let cleanupFailed = false;
      this.#closeMicrophonePermissionObservation(pending.permissionObservation);
      if (pending.track !== null && pending.trackListenerAttached) {
        pending.trackListenerAttached = false;
        try {
          pending.track.removeEventListener('ended', pending.onTrackEnded);
        } catch {
          cleanupFailed = true;
        }
      }
      if (pending.deviceListenerAttached) {
        pending.deviceListenerAttached = false;
        try {
          this.#environment.mediaDevices?.removeEventListener('devicechange', pending.onDeviceChange);
        } catch {
          cleanupFailed = true;
        }
      }
      try {
        if (pending.context !== null && pending.installedContextStateChange !== null && pending.context.onstatechange === pending.installedContextStateChange) {
          pending.context.onstatechange = pending.priorContextStateChange;
        }
      } catch {
        cleanupFailed = true;
      }
      try {
        await this.#cleanupLooseCapture(pending.stream, pending.context, pending.source, pending.worklet, pending.ownsContext);
      } catch {
        cleanupFailed = true;
      }
      if (cleanupFailed) {
        throw new BrowserAudioIOViolation('CAPTURE_CLEANUP_FAILED', 'partial browser capture resources could not be released', true);
      }
    })();
    return pending.cleanupPromise;
  }

  async #cleanupLooseCapture(
    stream: BrowserMediaStreamLike | null,
    context: BrowserAudioContextLike | null,
    source: BrowserAudioNodeLike | null,
    worklet: BrowserAudioWorkletNodeLike | null,
    closeContext = true
  ): Promise<void> {
    let cleanupFailed = false;
    if (worklet !== null) {
      try {
        worklet.port.onmessage = null;
      } catch {
        cleanupFailed = true;
      }
      try {
        worklet.onprocessorerror = null;
      } catch {
        cleanupFailed = true;
      }
      try {
        worklet.disconnect();
      } catch {
        // Best-effort cleanup before the session became active.
      }
      try {
        worklet.port.close();
      } catch {
        cleanupFailed = true;
      }
    }
    if (source !== null) {
      try {
        source.disconnect();
      } catch {
        // Best-effort cleanup before the session became active.
      }
    }
    try {
      cleanupFailed = stopStream(stream) || cleanupFailed;
    } catch {
      cleanupFailed = true;
    }
    if (closeContext && context !== null) {
      let shouldCloseContext = true;
      try {
        shouldCloseContext = context.state !== 'closed';
      } catch {
        cleanupFailed = true;
      }
      if (shouldCloseContext) {
        try {
          await context.close();
        } catch {
          cleanupFailed = true;
        }
      }
    }
    if (cleanupFailed) {
      throw new BrowserAudioIOViolation('CAPTURE_CLEANUP_FAILED', 'partial browser capture resources could not be released', true);
    }
  }

  #listenForVisibility(): void {
    if (this.#visibilityListening || this.#environment.document === null) return;
    this.#visibilityListening = true;
    try {
      this.#environment.document.addEventListener('visibilitychange', this.#onVisibilityChange);
    } catch {
      try {
        this.#environment.document.removeEventListener('visibilitychange', this.#onVisibilityChange);
        this.#visibilityListening = false;
      } catch {
        throw new BrowserAudioIOViolation('VISIBILITY_LISTENER_CLEANUP_FAILED', 'browser visibility listener registration cleanup failed', true);
      }
      throw new BrowserAudioIOViolation('VISIBILITY_LISTENER_FAILED', 'browser visibility listener registration failed', true);
    }
  }

  #unlistenForVisibilityWhenIdle(): boolean {
    if (!this.#visibilityListening || this.#environment.document === null) return false;
    if (
      this.#capture !== null ||
      this.#pendingCaptureToken !== null ||
      this.#pendingPlayoutGeneration !== null ||
      this.#playoutContext !== null ||
      this.#playback !== null
    )
      return false;
    try {
      this.#environment.document.removeEventListener('visibilitychange', this.#onVisibilityChange);
      this.#visibilityListening = false;
      return false;
    } catch {
      return true;
    }
  }

  #emitCaptureState(
    state: BrowserAudioCaptureState,
    reason: string,
    metadata: Readonly<BrowserAudioCaptureMetadata> | null,
    generation: number | null = null
  ): void {
    this.#captureState = state;
    try {
      this.#observer.onCaptureState?.(
        Object.freeze({
          state,
          reason,
          capture_id: metadata?.capture_id ?? null,
          capture_generation: metadata?.capture_generation ?? generation,
        })
      );
    } catch {
      // State observers cannot own or interrupt the browser resource lifecycle.
    }
  }

  #emitPlayoutState(
    state: BrowserAudioPlayoutState,
    reason: string,
    playback: PlaybackSession | null,
    unitId: string | null = null,
    throughSeq: number | null = null
  ): void {
    this.#playoutState = state;
    try {
      this.#observer.onPlayoutState?.(
        Object.freeze({
          state,
          reason,
          response: playback?.response ?? null,
          unit_id: unitId,
          through_seq: throughSeq,
        })
      );
    } catch {
      // Playout observers cannot interrupt exact-response fencing or cleanup.
    }
  }

  #notifyDeviceChange(event: Readonly<BrowserAudioDeviceEvent>): void {
    try {
      this.#observer.onDeviceChange?.(event);
    } catch {
      // Diagnostics observers cannot alter device ownership.
    }
  }

  #notifyPlayoutScheduled(
    playback: PlaybackSession,
    unitId: string,
    seq: number,
    startDelayMs: number,
    scheduledStartClock: BrowserAudioPlayoutScheduledEvent['scheduled_start_clock'],
    hasStarted: () => boolean
  ): void {
    try {
      this.#observer.onPlayoutScheduled?.(
        Object.freeze({
          response: playback.response,
          unit_id: unitId,
          seq,
          start_delay_ms: startDelayMs,
          scheduled_start_clock: scheduledStartClock,
          has_started: hasStarted,
        })
      );
    } catch {
      // Timing observers cannot alter browser source scheduling.
    }
  }
}
