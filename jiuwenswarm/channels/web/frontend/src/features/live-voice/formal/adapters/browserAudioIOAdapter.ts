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
}

export interface BrowserMediaDevicesLike {
  getUserMedia(constraints: MediaStreamConstraints): Promise<BrowserMediaStreamLike>;
  enumerateDevices(): Promise<BrowserMediaDeviceInfoLike[]>;
  addEventListener(type: 'devicechange', listener: BrowserEventListener): void;
  removeEventListener(type: 'devicechange', listener: BrowserEventListener): void;
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
  close(): Promise<void>;
  createMediaStreamSource(stream: unknown): BrowserAudioNodeLike;
  createBuffer(numberOfChannels: number, length: number, sampleRate: number): BrowserAudioBufferLike;
  createBufferSource(): BrowserAudioBufferSourceLike;
}

export interface BrowserAudioEnvironment {
  readonly isSecureContext: boolean;
  readonly document: BrowserAudioDocumentLike | null;
  readonly mediaDevices: BrowserMediaDevicesLike | null;
  readonly createAudioContext: (() => BrowserAudioContextLike) | null;
  readonly createAudioWorkletNode:
    ((context: BrowserAudioContextLike, name: string, options: Readonly<Record<string, unknown>>) => BrowserAudioWorkletNodeLike) | null;
  readonly createId: (() => string) | null;
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
  readonly output_device_selection: false;
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
  readonly output_device_selection: false;
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

export interface BrowserAudioObserver {
  onCaptureFrame?(frame: Readonly<CapturedAudioFrame>): void;
  onCaptureState?(event: Readonly<BrowserAudioCaptureStateEvent>): void;
  onDeviceChange?(event: Readonly<BrowserAudioDeviceEvent>): void;
  onPlayoutState?(event: Readonly<BrowserAudioPlayoutEvent>): void;
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
  expectedSeq: number;
  closed: boolean;
}

interface PendingCaptureResources {
  readonly token: number;
  stream: BrowserMediaStreamLike | null;
  track: BrowserAudioTrackLike | null;
  context: BrowserAudioContextLike | null;
  source: BrowserAudioNodeLike | null;
  worklet: BrowserAudioWorkletNodeLike | null;
  readonly onTrackEnded: BrowserEventListener;
  readonly onContextStateChange: BrowserEventListener;
  priorContextStateChange: BrowserEventListener | null;
  installedContextStateChange: BrowserEventListener | null;
  ownsContext: boolean;
  trackListenerAttached: boolean;
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

function defaultBrowserAudioEnvironment(): BrowserAudioEnvironment {
  if (typeof window === 'undefined' || typeof navigator === 'undefined') {
    return Object.freeze({
      isSecureContext: false,
      document: null,
      mediaDevices: null,
      createAudioContext: null,
      createAudioWorkletNode: null,
      createId: null,
    });
  }
  const browserWindow = window as Window & {
    webkitAudioContext?: typeof AudioContext;
    AudioWorkletNode?: typeof AudioWorkletNode;
  };
  const audioContextConstructor = (typeof AudioContext === 'undefined' ? undefined : AudioContext) ?? browserWindow.webkitAudioContext;
  const workletNodeConstructor = browserWindow.AudioWorkletNode ?? (globalThis as { AudioWorkletNode?: typeof AudioWorkletNode }).AudioWorkletNode;
  return Object.freeze({
    isSecureContext: window.isSecureContext,
    document: document as unknown as BrowserAudioDocumentLike,
    mediaDevices: navigator.mediaDevices ? (navigator.mediaDevices as unknown as BrowserMediaDevicesLike) : null,
    createAudioContext: audioContextConstructor ? () => new audioContextConstructor() as unknown as BrowserAudioContextLike : null,
    createAudioWorkletNode: workletNodeConstructor
      ? (context: BrowserAudioContextLike, name: string, options: Readonly<Record<string, unknown>>) =>
          new workletNodeConstructor(context as unknown as BaseAudioContext, name, options as AudioWorkletNodeOptions) as unknown as BrowserAudioWorkletNodeLike
      : null,
    createId: typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function' ? () => crypto.randomUUID() : null,
  });
}

export function inspectBrowserAudioPlatform(
  enabled: boolean,
  environment: BrowserAudioEnvironment = defaultBrowserAudioEnvironment()
): Readonly<BrowserAudioPlatformCapability> {
  const reasons: string[] = [];
  if (!enabled) reasons.push('FEATURE_DISABLED');
  if (!environment.isSecureContext) reasons.push('INSECURE_CONTEXT');
  if (environment.document === null) reasons.push('DOCUMENT_VISIBILITY_UNAVAILABLE');
  if (environment.mediaDevices === null) reasons.push('MEDIA_DEVICES_UNAVAILABLE');
  if (environment.createAudioContext === null) reasons.push('AUDIO_CONTEXT_UNAVAILABLE');
  if (environment.createAudioWorkletNode === null) reasons.push('AUDIO_WORKLET_NODE_UNAVAILABLE');
  if (environment.createId === null) reasons.push('STABLE_IDENTITY_UNAVAILABLE');
  const captureSupported = reasons.length === 0;
  const playoutSupported = enabled && environment.isSecureContext && environment.createAudioContext !== null;
  return Object.freeze({
    enabled,
    secure_context: environment.isSecureContext,
    document_visibility: environment.document !== null,
    media_devices: environment.mediaDevices !== null,
    audio_context: environment.createAudioContext !== null,
    audio_worklet_node: environment.createAudioWorkletNode !== null,
    stable_identity: environment.createId !== null,
    capture_pcm_f32: captureSupported,
    playout_pcm_f32: playoutSupported,
    media_recorder_realtime: false,
    output_device_selection: false,
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
  readonly captureWorkletModuleUrl?: string;
  readonly monotonicNowMs?: () => number;
}

export class BrowserAudioIOAdapter {
  readonly #enabled: boolean;
  readonly #environment: BrowserAudioEnvironment;
  readonly #observer: BrowserAudioObserver;
  readonly #captureWorkletModuleUrl: string;
  readonly #monotonicNowMs: () => number;
  readonly #audioPort = new AudioPort();
  readonly #seenCaptureIds = new Set<string>();
  readonly #onVisibilityChange: BrowserEventListener;
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
  #playbackMutationToken = 0;
  #closed = false;
  #closePromise: Promise<void> | null = null;
  #visibilityListening = false;

  constructor(options: Readonly<BrowserAudioIOAdapterOptions>) {
    this.#enabled = options.enabled;
    this.#environment = options.environment ?? defaultBrowserAudioEnvironment();
    this.#observer = options.observer ?? {};
    this.#captureWorkletModuleUrl = options.captureWorkletModuleUrl ?? new URL('./liveVoiceCaptureProcessor.js', import.meta.url).href;
    this.#monotonicNowMs = options.monotonicNowMs ?? defaultMonotonicNowMs;
    this.#onVisibilityChange = () => {
      if (this.#environment.document?.visibilityState === 'hidden') {
        void this.stopCapture('page_hidden').catch(() => {
          this.#emitCaptureState('failed', 'capture_cleanup_failed', null);
        });
      }
    };
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
      trackListenerAttached: false,
      contextHasRun: false,
      cleanupPromise: null,
    };
    this.#pendingCaptureResources = pending;
    this.#listenForVisibility();
    this.#emitCaptureState('starting', 'start_requested', null, token);

    let stream: BrowserMediaStreamLike | null = null;
    let context: BrowserAudioContextLike | null = null;
    let source: BrowserAudioNodeLike | null = null;
    let worklet: BrowserAudioWorkletNodeLike | null = null;
    let startedSession: CaptureSession | null = null;
    try {
      this.#requireCurrentCaptureToken(token);
      const deviceId = typeof input.deviceId === 'string' && input.deviceId.trim() ? input.deviceId : null;
      const audioConstraints: MediaTrackConstraints = {
        echoCancellation: { ideal: true },
        noiseSuppression: { ideal: true },
        autoGainControl: { ideal: true },
        channelCount: { ideal: 1 },
        ...(deviceId === null ? {} : { deviceId: { exact: deviceId } }),
      };
      stream = await mediaDevices.getUserMedia({ audio: audioConstraints, video: false });
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
          await context.resume();
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
        await context.audioWorklet.addModule(this.#captureWorkletModuleUrl);
      } catch {
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
      const onDeviceChange = () => void this.#observeDeviceChange(token);
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
        expectedSeq: 0,
        closed: false,
      };
      startedSession = session;
      worklet.port.onmessage = event => this.#handleCaptureMessage(session, event.data);
      worklet.onprocessorerror = () => this.#stopCaptureFromBrowser('audio_processor_error');
      track.addEventListener('mute', onTrackMute);
      track.addEventListener('unmute', onTrackUnmute);
      mediaDevices.addEventListener('devicechange', onDeviceChange);
      context.onstatechange = installedContextStateChange;
      this.#requireCurrentCaptureToken(token);
      if ((track.readyState !== undefined && track.readyState !== 'live') || context.state !== 'running') {
        throw new BrowserAudioIOViolation('CAPTURE_STARTUP_LOST', 'audio input or AudioContext was lost during startup');
      }
      if (track.muted === true) {
        throw new BrowserAudioIOViolation('AUDIO_INPUT_MUTED', 'audio input is muted during capture startup');
      }
      this.#capture = session;
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
      this.#unlistenForVisibilityWhenIdle();
      if (cleanupFailure !== null) {
        const mapped = mapBrowserFailure(cleanupFailure, 'CAPTURE_CLEANUP_FAILED');
        this.#emitCaptureState('failed', mapped.reason.toLowerCase(), null, token);
        throw mapped;
      }
      if (cancelled) {
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
    this.#unlistenForVisibilityWhenIdle();
    if (session !== null || pending !== null) {
      try {
        if (session !== null) await this.#cleanupCaptureSession(session);
        else if (pending !== null) await this.#cleanupPendingCapture(pending);
      } catch (error) {
        const mapped = mapBrowserFailure(error, 'CAPTURE_CLEANUP_FAILED');
        this.#emitCaptureState('failed', mapped.reason.toLowerCase(), session?.metadata ?? null);
        throw mapped;
      }
    }
    this.#emitCaptureState('stopped', reason, session?.metadata ?? null);
    return true;
  }

  async unlockPlayout(): Promise<Readonly<BrowserAudioPlayoutMetadata>> {
    if (this.#closed) throw new BrowserAudioIOViolation('ADAPTER_CLOSED', 'browser audio adapter is closed');
    this.#requirePlayoutSourceCleanupHealthy();
    if (!this.#enabled) throw new BrowserAudioIOViolation('FEATURE_DISABLED', 'browser audio is disabled');
    if (!this.#environment.isSecureContext) throw new BrowserAudioIOViolation('INSECURE_CONTEXT', 'browser audio requires a secure context');
    const createContext = this.#environment.createAudioContext;
    if (createContext === null) throw new BrowserAudioIOViolation('AUDIO_CONTEXT_UNAVAILABLE', 'AudioContext is unavailable');
    if (this.#pendingPlayoutGeneration !== null) {
      throw new BrowserAudioIOViolation('PLAYOUT_UNLOCK_IN_PROGRESS', 'browser playout unlock is already in progress');
    }
    const generation = ++this.#playoutGeneration;
    this.#pendingPlayoutGeneration = generation;
    if (this.#playoutContext === null || this.#playoutContext.state === 'closed') {
      try {
        this.#playoutContext = createContext();
      } catch (error) {
        if (this.#pendingPlayoutGeneration === generation) this.#pendingPlayoutGeneration = null;
        throw mapAudioContextFailure(error, 'AUDIO_CONTEXT_CREATE_FAILED');
      }
    }
    const context = this.#playoutContext;
    try {
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
      this.#emitPlayoutState('ready', 'playout_unlocked', null);
      this.#requireCurrentPlayoutUnlock(generation, context);
      return Object.freeze({
        encoding: 'pcm_f32' as const,
        sample_rate_hz: context.sampleRate,
        channel_count: 1 as const,
        output_device_selection: false as const,
        physical_heard_ack: false as const,
      });
    } finally {
      if (this.#pendingPlayoutGeneration === generation) this.#pendingPlayoutGeneration = null;
    }
  }

  beginPlayout(response: Readonly<AudioResponseRef>): void {
    if (this.#closed) throw new BrowserAudioIOViolation('ADAPTER_CLOSED', 'browser audio adapter is closed');
    this.#requirePlayoutSourceCleanupHealthy();
    const context = this.#playoutContext;
    if (context === null || context.state !== 'running') {
      throw new BrowserAudioIOViolation('PLAYOUT_NOT_UNLOCKED', 'playout must be unlocked by a user action');
    }
    const prior = this.#playback;
    let normalizedResponse: Readonly<AudioResponseRef>;
    try {
      normalizedResponse = Object.freeze({
        interaction_id: response.interaction_id,
        response_id: response.response_id,
        response_generation: response.response_generation,
      });
      this.#audioPort.begin(normalizedResponse);
    } catch (error) {
      throw mapBrowserFailure(error, 'PLAYOUT_BEGIN_FAILED');
    }
    const mutationToken = ++this.#playbackMutationToken;
    if (prior !== null) {
      this.#audioPort.stopLocal(prior.response);
      const cleanup = this.#stopPlaybackSources(prior, 'response_replaced', false);
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
      nextStartTime: context.currentTime,
      stopped: false,
    };
    this.#playback = playback;
    if (prior !== null) {
      this.#emitPlayoutState('stopped', 'response_replaced', prior);
      if (this.#playback !== playback || mutationToken !== this.#playbackMutationToken) {
        throw new BrowserAudioIOViolation('PLAYOUT_REPLACED_DURING_BEGIN', 'playout was replaced by a reentrant observer');
      }
    }
    this.#emitPlayoutState('ready', 'response_started', playback);
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
      sourceStartAttempted = true;
      source.start(startAt);
      playback.nextStartTime = startAt + chunk.samples.length / chunk.sample_rate_hz;
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
    if (this.#closed || this.#playoutGeneration !== generation || this.#pendingPlayoutGeneration !== generation || this.#playoutContext !== context) {
      throw new BrowserAudioIOViolation('PLAYOUT_CANCELLED', 'playout unlock was fenced by close or replacement');
    }
    this.#requirePlayoutSourceCleanupHealthy();
  }

  #fencePlayoutForClose(): Readonly<{ context: BrowserAudioContextLike | null; failure: unknown }> {
    const context = this.#playoutContext;
    this.#playoutContext = null;
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
      this.#emitPlayoutState('playing', 'render_completed', playback, record.unitId, through);
    }
  }

  async #observeDeviceChange(token: number): Promise<void> {
    if (this.#capture?.token !== token || this.#environment.mediaDevices === null) return;
    try {
      const devices = await this.#environment.mediaDevices.enumerateDevices();
      if (this.#capture?.token !== token) return;
      const count = devices.filter(device => device.kind === 'audioinput').length;
      this.#notifyDeviceChange(Object.freeze({ audio_input_count: count, reason: 'devicechange' }));
    } catch {
      if (this.#capture?.token !== token) return;
      this.#notifyDeviceChange(Object.freeze({ audio_input_count: null, reason: 'enumeration_failed' }));
    }
  }

  #stopCaptureFromBrowser(reason: string): void {
    void this.stopCapture(reason).catch(() => {
      this.#emitCaptureState('failed', 'capture_cleanup_failed', null);
    });
  }

  async #cleanupCaptureSession(session: CaptureSession): Promise<void> {
    if (session.closed) return;
    session.closed = true;
    session.worklet.port.onmessage = null;
    session.worklet.onprocessorerror = null;
    if (session.context.onstatechange === session.installedContextStateChange) {
      session.context.onstatechange = session.priorContextStateChange;
    }
    session.track.removeEventListener('ended', session.onTrackEnded);
    session.track.removeEventListener('mute', session.onTrackMute);
    session.track.removeEventListener('unmute', session.onTrackUnmute);
    this.#environment.mediaDevices?.removeEventListener('devicechange', session.onDeviceChange);
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
    let cleanupFailed = false;
    try {
      session.worklet.port.close();
    } catch {
      cleanupFailed = true;
    }
    cleanupFailed = stopStream(session.stream) || cleanupFailed;
    if (session.ownsContext && session.context.state !== 'closed') {
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
      if (pending.track !== null && pending.trackListenerAttached) {
        pending.track.removeEventListener('ended', pending.onTrackEnded);
        pending.trackListenerAttached = false;
      }
      if (pending.context !== null && pending.installedContextStateChange !== null && pending.context.onstatechange === pending.installedContextStateChange) {
        pending.context.onstatechange = pending.priorContextStateChange;
      }
      await this.#cleanupLooseCapture(pending.stream, pending.context, pending.source, pending.worklet, pending.ownsContext);
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
      worklet.port.onmessage = null;
      worklet.onprocessorerror = null;
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
    cleanupFailed = stopStream(stream) || cleanupFailed;
    if (closeContext && context !== null && context.state !== 'closed') {
      try {
        await context.close();
      } catch {
        cleanupFailed = true;
      }
    }
    if (cleanupFailed) {
      throw new BrowserAudioIOViolation('CAPTURE_CLEANUP_FAILED', 'partial browser capture resources could not be released', true);
    }
  }

  #listenForVisibility(): void {
    if (this.#visibilityListening || this.#environment.document === null) return;
    this.#environment.document.addEventListener('visibilitychange', this.#onVisibilityChange);
    this.#visibilityListening = true;
  }

  #unlistenForVisibilityWhenIdle(): void {
    if (!this.#visibilityListening || this.#environment.document === null) return;
    if (this.#capture !== null || this.#pendingCaptureToken !== null) return;
    this.#environment.document.removeEventListener('visibilitychange', this.#onVisibilityChange);
    this.#visibilityListening = false;
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
}
