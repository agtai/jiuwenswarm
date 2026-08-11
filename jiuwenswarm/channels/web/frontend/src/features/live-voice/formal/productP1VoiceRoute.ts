import { LIVE_VOICE_AUDIO_FRAME_DURATION_MS, createAudioRenderPlan, type AudioResponseRef, type CapturedAudioFrame } from './audioPort.js';
import {
  BrowserAudioIOAdapter,
  type BrowserAudioEnvironment,
  type BrowserAudioPcmChunk,
  type BrowserAudioPlayoutEvent,
  type BrowserAudioPlayoutMetadata,
} from './adapters/browserAudioIOAdapter.js';
import {
  createBrowserDedicatedMediaRoute,
  deserializeMediaControl,
  type ActiveBrowserDedicatedMediaRoute,
  type DedicatedMediaSocketFactory,
} from './adapters/browserDedicatedMediaRoute.js';
import type { MediaAudioFrame } from './adapters/browserGatewayMediaTransport.js';
import { GatewayBatchSpeechClient, type FormalSynthesisDownlink, type GatewaySpeechProvider } from './gatewayBatchSpeechClient.js';

export const PRODUCT_P1_MEDIA_ACTIVATE_METHOD = 'live_voice.media.activate';
export const PRODUCT_P1_MEDIA_CLOSE_METHOD = 'live_voice.media.close';
export const PRODUCT_P1_MEDIA_PLAYOUT_RECEIPT_METHOD = 'live_voice.media.playout_receipt';

export const PRODUCT_P1_CAPTURE_MAX_DURATION_MS = 30_000;
export const PRODUCT_P1_CAPTURE_DURATION_EXCEEDED_REASON = 'AUDIO_CAPTURE_DURATION_EXCEEDED';
export const PRODUCT_P1_EMPTY_TRANSCRIPT_REASON = 'SPEECH_PROVIDER_EMPTY_TRANSCRIPT';
const MAX_CAPTURE_FRAMES = PRODUCT_P1_CAPTURE_MAX_DURATION_MS / LIVE_VOICE_AUDIO_FRAME_DURATION_MS;
export const PRODUCT_P1_PLAYOUT_QUEUE_CAPACITY = 256;
const ROUTE_READY_TIMEOUT_MS = 3_000;
const ROUTE_DRAIN_TIMEOUT_MS = 3_000;
const ROUTE_COMPLETION_TIMEOUT_MS = 3_000;
const CAPTURE_FIRST_FRAME_TIMEOUT_MS = 1_000;

export type ProductP1VoiceStatus = 'idle' | 'starting' | 'capturing' | 'recognizing' | 'recognized' | 'playing' | 'cleanup_pending' | 'failed' | 'closed';

export interface ProductP1Recognition {
  readonly text: string;
  readonly voice_commit_receipt: string;
}

type ProductP1Request = (method: string, params: Record<string, unknown>) => Promise<unknown>;

interface PendingProductPlayout {
  readonly response: Readonly<AudioResponseRef>;
  readonly unitId: string;
  readonly chunks: Readonly<BrowserAudioPcmChunk>[];
  readonly frameCount: number;
  readonly downlinkRoute: ActiveBrowserDedicatedMediaRoute | null;
  readonly receiptAuthority: Readonly<ProductP1MediaCloseBinding>;
  readonly captureFramesAcked: number;
  nextChunkIndex: number;
  renderedChunks: number;
  peakDepth: number;
  filling: boolean;
  readonly expected: ReadonlyMap<string, number>;
  readonly observed: Map<string, number>;
  readonly resolve: () => void;
  readonly reject: (error: Error) => void;
}

interface ProductP1MediaCloseBinding {
  readonly session_id: string;
  readonly subject_id: string;
  readonly correlation_id: string;
  readonly interaction_id: string;
  readonly activation_id: string;
  readonly activation_generation: number;
}

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

function requiredText(value: unknown, field: string): string {
  if (typeof value !== 'string' || value.trim().length === 0 || value !== value.trim()) {
    throw new Error(`${field} is invalid`);
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
  return new Promise(resolve => globalThis.setTimeout(resolve, 10));
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

export class ProductP1VoiceRouteOwner {
  readonly #enabled: boolean;
  readonly #request: ProductP1Request;
  readonly #origin: string;
  readonly #socketFactory: DedicatedMediaSocketFactory;
  readonly #onStatus?: (status: ProductP1VoiceStatus, reason: string | null) => void;
  readonly #audio: BrowserAudioIOAdapter;
  #status: ProductP1VoiceStatus;
  #reason: string | null = null;
  #frames: Readonly<CapturedAudioFrame>[] = [];
  #mediaSentFrames = 0;
  #captureFramesAcked = 0;
  #route: ActiveBrowserDedicatedMediaRoute | null = null;
  #speech: GatewayBatchSpeechClient | null = null;
  #sessionId: string | null = null;
  #interactionId: string | null = null;
  #correlationId: string | null = null;
  #locale = 'zh-CN';
  #activationId: string | null = null;
  #activationGeneration = 0;
  #deviceId: string | undefined;
  #playout: Readonly<BrowserAudioPlayoutMetadata> | null = null;
  #closed = false;
  #operationGeneration = 0;
  #mediaCloseBinding: Readonly<ProductP1MediaCloseBinding> | null = null;
  readonly #retainedMediaAuthorities = new Map<string, Readonly<ProductP1MediaCloseBinding>>();
  #closePromise: Promise<void> | null = null;
  #failureCleanupPromise: Promise<void> | null = null;
  #failureCleanupReason: string | null = null;
  #pendingPlayout: PendingProductPlayout | null = null;
  #settlingPlayout: PendingProductPlayout | null = null;
  #captureStartupAudioReady = false;
  #captureStartupFailure: (Error & { readonly reason: string }) | null = null;
  #captureReadinessPending = false;
  #pendingMediaActivation: Promise<unknown> | null = null;

  constructor(
    input: Readonly<{
      enabled: boolean;
      request: ProductP1Request;
      expected_origin: string;
      socket_factory?: DedicatedMediaSocketFactory;
      audio_environment?: BrowserAudioEnvironment;
      on_status?: (status: ProductP1VoiceStatus, reason: string | null) => void;
    }>
  ) {
    this.#enabled = input.enabled === true;
    this.#request = input.request;
    this.#origin = requiredText(input.expected_origin, 'expected_origin');
    this.#socketFactory = input.socket_factory ?? defaultSocketFactory;
    this.#onStatus = input.on_status;
    this.#status = this.#enabled ? 'idle' : 'closed';
    this.#audio = new BrowserAudioIOAdapter({
      enabled: this.#enabled,
      ...(input.audio_environment === undefined ? {} : { environment: input.audio_environment }),
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
            failure = Object.assign(new Error('formal browser capture stopped unexpectedly'), {
              reason: stableCaptureStopReason(event.reason),
            });
          }
          if (failure === null || this.#failureCleanupPromise !== null || this.#closed) return;
          if (this.#captureReadinessPending) {
            if (!['starting', 'playing'].includes(this.#status)) return;
            this.#captureStartupFailure ??= failure;
            this.#reason = this.#captureStartupFailure.reason;
            this.#status = 'cleanup_pending';
            void this.#audio.close().catch(() => undefined);
            this.#publish();
          } else if (['capturing', 'playing'].includes(this.#status)) {
            void this.#fail(failure);
          }
        },
        onPlayoutState: event => this.#observePlayout(event),
      },
    });
    this.#publish();
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
      device_id?: string;
    }>
  ): Promise<void> {
    if (!this.#enabled || this.#closed) throw new Error('formal P1 voice route is disabled');
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
    const operationGeneration = ++this.#operationGeneration;
    this.#setStatus('starting', null);
    this.#captureStartupAudioReady = false;
    this.#captureStartupFailure = null;
    this.#captureReadinessPending = true;
    this.#failureCleanupReason = null;
    this.#frames = [];
    this.#mediaSentFrames = 0;
    this.#captureFramesAcked = 0;
    this.#route = null;
    this.#speech = null;
    this.#sessionId = sessionId;
    this.#interactionId = interactionId;
    this.#correlationId = correlationId;
    this.#locale = locale;
    this.#activationId = activationId;
    this.#activationGeneration = activationGeneration;
    this.#deviceId = input.device_id;
    try {
      if (this.#mediaCloseBinding !== null) await this.#revokeMediaAuthority();
      this.#requireCurrent(operationGeneration);
      this.#playout = await this.#audio.unlockPlayout();
      this.#requireCurrent(operationGeneration);
      const metadata = await this.#audio.startCapture(input.device_id ? { deviceId: input.device_id } : {});
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
        });
        const activationEnvelope = objectValue(activationValue, 'media_activation');
        if (activationEnvelope.status !== 'active') {
          const inactive = exactObject(activationEnvelope, ['status', 'reason_id'], 'media_activation');
          if (!['disabled', 'unavailable'].includes(String(inactive.status))) {
            throw new Error('media activation returned an unknown status');
          }
          throw routeUnavailable(inactive.reason_id);
        }
        const activation = exactObject(
          activationEnvelope,
          ['status', 'reason_id', 'subject_id', 'endpoint_path', 'subprotocol', 'ticket_ttl_ms', 'binding', 'privacy'],
          'media_activation'
        );
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
      const route = createBrowserDedicatedMediaRoute({
        enabled: true,
        expected_origin: this.#origin,
        endpoint_url: mediaEndpoint(this.#origin, requiredText(activation.endpoint_path, 'endpoint_path')),
        binding: attach.binding,
        provider_available: true,
        transport_available: typeof WebSocket === 'function',
        socket_factory: this.#socketFactory,
        on_audio_frame: () => undefined,
      });
      if (!route.active) throw new Error(route.reason_id);
      this.#route = route;
      this.#speech = new GatewayBatchSpeechClient({
        enabled: true,
        transport: {
          request: async <T = unknown>(method: string, params?: Record<string, unknown>) => (await this.#request(method, params ?? {})) as T,
        },
        scope: {
          subject_id: requiredText(activation.subject_id, 'subject_id'),
          project_id: null,
          session_id: this.#sessionId,
          assurance: 'authenticated',
        },
      });
      await this.#awaitCaptureReadiness(route, operationGeneration);
      this.#captureStartupAudioReady = false;
      this.#captureStartupFailure = null;
      this.#captureReadinessPending = false;
      this.#setStatus('capturing', null);
    } catch (error) {
      const failure = this.#captureStartupFailure ?? error;
      this.#captureStartupAudioReady = false;
      this.#captureStartupFailure = null;
      this.#captureReadinessPending = false;
      await this.#fail(failure);
      throw failure;
    }
  }

  async stopAndRecognize(): Promise<Readonly<ProductP1Recognition>> {
    if (this.#failureCleanupPromise !== null || this.#status !== 'capturing' || this.#route === null || this.#speech === null) {
      throw new Error('formal P1 capture is not active');
    }
    const operationGeneration = ++this.#operationGeneration;
    const route = this.#route;
    const speech = this.#speech;
    this.#setStatus('recognizing', null);
    try {
      await this.#audio.stopCapture('formal_recognition_requested');
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
      this.#captureFramesAcked = this.#mediaSentFrames;
      await awaitRouteCompletion(route.leaf.completeUplink('MEDIA_LOCAL_CLOSE'));
      this.#requireCurrent(operationGeneration);
      const result = await speech.recognizeFinal({
        frames: this.#frames,
        locale: this.#locale,
        correlationId: requiredText(this.#correlationId, 'correlation_id'),
      });
      // The formal STT result, not captured samples, is the retained product
      // fact. Release the browser copy as soon as the exact request settles.
      this.#frames = [];
      this.#mediaSentFrames = 0;
      this.#route = null;
      this.#requireCurrent(operationGeneration);
      if (result === null) throw new Error('formal recognition was fenced');
      this.#setStatus('recognized', null);
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
        this.#mediaSentFrames = 0;
        this.#route = null;
        this.#setStatus('idle', PRODUCT_P1_EMPTY_TRANSCRIPT_REASON);
        throw error;
      }
      await this.#fail(error);
      throw error;
    }
  }

  async playAgentText(
    input: Readonly<{
      response: Readonly<AudioResponseRef>;
      unit_id: string;
      text: string;
    }>
  ): Promise<void> {
    if (this.#speech === null || this.#playout === null || this.#closed) {
      throw new Error('formal P1 synthesis authority is unavailable');
    }
    if (['starting', 'capturing', 'recognizing'].includes(this.#status)) {
      throw new Error('formal P1 capture must settle before Agent playout');
    }
    const operationGeneration = ++this.#operationGeneration;
    const speech = this.#speech;
    this.#setStatus('playing', null);
    let playoutResponse: Readonly<AudioResponseRef> | null = null;
    try {
      const text = requiredText(input.text, 'agent_text');
      const result = await speech.synthesizeAuthoritative({
        response: input.response,
        unitId: requiredText(input.unit_id, 'unit_id'),
        renderPlan: createAudioRenderPlan(text, text, []),
        authoritativeAgentText: true,
        locale: this.#locale,
        voice: null,
        requiredSampleRateHz: this.#playout.sample_rate_hz,
        correlationId: requiredText(this.#correlationId, 'correlation_id'),
      });
      this.#requireCurrent(operationGeneration);
      if (result === null) throw new Error('formal synthesis was fenced');
      if ((result.chunks.length === 0) === (result.downlink === null)) {
        throw new Error('formal synthesis must return exactly one audio delivery');
      }
      const receiptAuthority = this.#mediaCloseBinding;
      const captureFramesAcked = this.#captureFramesAcked;
      if (receiptAuthority === null || captureFramesAcked <= 0) {
        throw new Error('formal synthesis lost its capture authority');
      }
      let downlinkRoute: ActiveBrowserDedicatedMediaRoute | null = null;
      let pendingRef: PendingProductPlayout | null = null;
      const chunks = [...result.chunks];
      const frameCount = result.downlink?.frame_count ?? chunks.length;
      if (result.downlink !== null) {
        await this.#startConcurrentCapture(operationGeneration);
        this.#requireCurrent(operationGeneration);
        downlinkRoute = this.#openDownlinkRoute(result.downlink, result.provider, result.response, result.unit_id, frame => {
          if (pendingRef === null) throw new Error('downlink arrived before playout ownership');
          this.#acceptDownlinkFrame(pendingRef, frame, result.provider);
        });
      }
      const expected = new Map<string, number>([[result.unit_id, frameCount - 1]]);
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
        chunks,
        frameCount,
        downlinkRoute,
        receiptAuthority,
        captureFramesAcked,
        nextChunkIndex: 0,
        renderedChunks: 0,
        peakDepth: 0,
        filling: false,
        expected,
        observed: new Map(),
        resolve: resolvePlayout,
        reject: rejectPlayout,
      };
      pendingRef = pendingPlayout;
      this.#pendingPlayout = pendingPlayout;
      this.#audio.beginPlayout(result.response);
      this.#fillPlayoutQueue(pendingPlayout);
      await rendered;
      this.#requireCurrent(operationGeneration);
      if (downlinkRoute !== null) {
        const deadline = Date.now() + ROUTE_DRAIN_TIMEOUT_MS;
        while (!downlinkRoute.leaf.closed && Date.now() < deadline) await waitTurn();
        if (!downlinkRoute.leaf.closed) {
          throw new Error('dedicated media downlink did not close after final render ACK');
        }
        await waitTurn();
      }
      // The successor capture remains live while the final downlink detach is
      // drained. A duration/device failure in that window synchronously changes
      // the operation generation; fence it before minting a render receipt.
      this.#requireCurrent(operationGeneration);
      await this.#acknowledgePlayout(pendingPlayout);
      this.#requireCurrent(operationGeneration);
      if (downlinkRoute !== null) {
        await this.#revokeMediaAuthority(receiptAuthority);
        this.#requireCurrent(operationGeneration);
        if (this.#settlingPlayout === pendingPlayout) this.#settlingPlayout = null;
        this.#setStatus('capturing', null);
      } else {
        if (this.#settlingPlayout === pendingPlayout) this.#settlingPlayout = null;
        this.#setStatus('recognized', null);
      }
    } catch (error) {
      if (error !== null && typeof error === 'object' && (error as Record<string, unknown>).reason === 'FORMAL_PLAYOUT_BARGED') {
        this.#setStatus(this.#route === null ? 'recognized' : 'capturing', null);
        return;
      }
      const pending = this.#pendingPlayout;
      if (pending !== null && playoutResponse !== null) {
        this.#pendingPlayout = null;
        this.#audio.stopPlayout(playoutResponse, 'formal_playout_failed');
      }
      await this.#fail(error);
      throw error;
    }
  }

  stopAgentPlayout(response: Readonly<AudioResponseRef>): boolean {
    const pending = this.#pendingPlayout;
    if (
      this.#status !== 'playing' ||
      pending === null ||
      pending.response.interaction_id !== response.interaction_id ||
      pending.response.response_id !== response.response_id ||
      pending.response.response_generation !== response.response_generation
    )
      return false;
    this.#pendingPlayout = null;
    const stopped = this.#audio.stopPlayout(response, 'formal_product_barge_in');
    if (!stopped) {
      this.#pendingPlayout = pending;
      return false;
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
    this.#operationGeneration += 1;
    this.#status = 'cleanup_pending';
    this.#reason = 'FORMAL_P1_CLEANUP_IN_PROGRESS';
    const localAudioClose = this.#audio.close();
    this.#publish();
    const retained = (async () => {
      try {
        await localAudioClose;
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
    })()
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

  async #startConcurrentCapture(operationGeneration: number): Promise<void> {
    this.#captureStartupAudioReady = false;
    this.#captureStartupFailure = null;
    this.#captureReadinessPending = true;
    try {
      await this.#startConcurrentCaptureOwned(operationGeneration);
      this.#captureStartupAudioReady = false;
      this.#captureStartupFailure = null;
      this.#captureReadinessPending = false;
    } catch (error) {
      const failure = this.#captureStartupFailure ?? error;
      this.#captureStartupAudioReady = false;
      this.#captureStartupFailure = null;
      this.#captureReadinessPending = false;
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
    this.#mediaSentFrames = 0;
    this.#captureFramesAcked = 0;
    this.#route = null;
    this.#speech = null;
    const metadata = await this.#audio.startCapture(this.#deviceId ? { deviceId: this.#deviceId } : {});
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
      });
      const activation = exactObject(
        activationValue,
        ['status', 'reason_id', 'subject_id', 'endpoint_path', 'subprotocol', 'ticket_ttl_ms', 'binding', 'privacy'],
        'media_activation'
      );
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
    const route = createBrowserDedicatedMediaRoute({
      enabled: true,
      expected_origin: this.#origin,
      endpoint_url: mediaEndpoint(this.#origin, requiredText(activation.endpoint_path, 'endpoint_path')),
      binding: attach.binding,
      provider_available: true,
      transport_available: true,
      socket_factory: this.#socketFactory,
      on_audio_frame: () => undefined,
    });
    if (!route.active) throw new Error(route.reason_id);
    this.#route = route;
    this.#speech = new GatewayBatchSpeechClient({
      enabled: true,
      transport: {
        request: async <T = unknown>(method: string, params?: Record<string, unknown>) => (await this.#request(method, params ?? {})) as T,
      },
      scope: {
        subject_id: subjectId,
        project_id: null,
        session_id: sessionId,
        assurance: 'authenticated',
      },
    });
    await this.#awaitCaptureReadiness(route, operationGeneration);
  }

  #openDownlinkRoute(
    downlink: Readonly<FormalSynthesisDownlink>,
    provider: Readonly<GatewaySpeechProvider>,
    response: Readonly<AudioResponseRef>,
    unitId: string,
    onFrame: (frame: Readonly<MediaAudioFrame>) => void
  ): ActiveBrowserDedicatedMediaRoute {
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
      binding: attach.binding,
      provider_available: true,
      transport_available: true,
      socket_factory: this.#socketFactory,
      on_audio_frame: onFrame,
      max_pending_frames: downlink.max_pending_frames,
      max_pending_bytes: downlink.max_pending_bytes,
      defer_downlink_ack: true,
    });
    if (!route.active) throw new Error(route.reason_id);
    return route;
  }

  #acceptDownlinkFrame(pending: PendingProductPlayout, frame: Readonly<MediaAudioFrame>, provider: Readonly<GatewaySpeechProvider>): void {
    if (
      this.#status !== 'playing' ||
      this.#failureCleanupPromise !== null ||
      this.#pendingPlayout !== pending ||
      frame.seq !== pending.chunks.length ||
      frame.seq >= pending.frameCount
    )
      throw new Error('dedicated media downlink frame is stale or non-contiguous');
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
    this.#fillPlayoutQueue(pending);
  }

  #fillPlayoutQueue(pending: PendingProductPlayout): void {
    if (pending.filling || this.#status !== 'playing' || this.#failureCleanupPromise !== null || this.#pendingPlayout !== pending) return;
    pending.filling = true;
    try {
      while (pending.nextChunkIndex < pending.chunks.length && pending.nextChunkIndex - pending.renderedChunks < PRODUCT_P1_PLAYOUT_QUEUE_CAPACITY) {
        const chunk = pending.chunks[pending.nextChunkIndex];
        pending.nextChunkIndex += 1;
        const depthAfterEnqueue = pending.nextChunkIndex - pending.renderedChunks;
        if (!this.#audio.enqueuePlayout(chunk)) {
          pending.nextChunkIndex -= 1;
          throw new Error('browser playout rejected a formal chunk');
        }
        pending.peakDepth = Math.max(pending.peakDepth, depthAfterEnqueue);
      }
    } finally {
      pending.filling = false;
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
      receipt.duplex_media_observed !== (pending.downlinkRoute !== null)
    )
      throw new Error('media playout receipt binding mismatch');
  }

  #observePlayout(event: Readonly<BrowserAudioPlayoutEvent>): void {
    const pending = this.#pendingPlayout;
    if (pending === null) return;
    if (
      event.response !== null &&
      (event.response.interaction_id !== pending.response.interaction_id ||
        event.response.response_id !== pending.response.response_id ||
        event.response.response_generation !== pending.response.response_generation)
    )
      return;
    if (event.state === 'failed' || event.state === 'stopped' || event.state === 'closed') {
      this.#pendingPlayout = null;
      pending.reject(
        Object.assign(new Error('formal browser playout failed'), {
          reason: 'FORMAL_PLAYOUT_FAILED',
        })
      );
      return;
    }
    if (event.state !== 'playing' || event.reason !== 'render_completed' || event.unit_id === null || event.through_seq === null) return;
    pending.observed.set(event.unit_id, Math.max(pending.observed.get(event.unit_id) ?? -1, event.through_seq));
    if (pending.downlinkRoute !== null) {
      try {
        pending.downlinkRoute.leaf.acknowledgeDownlinkThrough(event.through_seq);
      } catch (error) {
        this.#pendingPlayout = null;
        pending.downlinkRoute.leaf.close('MEDIA_TRANSPORT_PROTOCOL_ERROR');
        this.#audio.stopPlayout(pending.response, 'formal_downlink_ack_failed');
        pending.reject(error instanceof Error ? error : new Error('formal downlink ACK failed'));
        return;
      }
    }
    pending.renderedChunks = [...pending.expected].reduce(
      (count, [unitId, finalSeq]) => count + Math.max(0, Math.min(finalSeq, pending.observed.get(unitId) ?? -1) + 1),
      0
    );
    try {
      this.#fillPlayoutQueue(pending);
    } catch (error) {
      this.#pendingPlayout = null;
      this.#audio.stopPlayout(pending.response, 'formal_playout_queue_failed');
      pending.reject(error instanceof Error ? error : new Error('formal playout queue failed'));
      return;
    }
    if ([...pending.expected].every(([unitId, seq]) => (pending.observed.get(unitId) ?? -1) >= seq) && pending.nextChunkIndex === pending.chunks.length) {
      this.#pendingPlayout = null;
      this.#settlingPlayout = pending;
      pending.resolve();
    }
  }

  async #revokeMediaAuthority(binding: Readonly<ProductP1MediaCloseBinding> | null = this.#mediaCloseBinding): Promise<void> {
    if (binding === null) return;
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

  #acceptCaptureFrame(frame: Readonly<CapturedAudioFrame>): void {
    if (this.#closed || this.#failureCleanupPromise !== null || ['cleanup_pending', 'failed', 'closed'].includes(this.#status)) return;
    if (this.#frames.length >= MAX_CAPTURE_FRAMES) {
      // Batch STT owns the complete bounded utterance, so ACKed frames cannot be
      // evicted without truncating recognition input. Treat the declared 30s
      // boundary as an exact Product P1 failure instead of leaking a trusted
      // capacity decision through the Adapter's generic consumer-error channel.
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
    let pending = route.leaf.flush();
    while (
      (this.#frames.length === 0 || this.#mediaSentFrames === 0 || pending.pending_frames !== 0) &&
      !route.leaf.closed &&
      Date.now() < firstFrameDeadline
    ) {
      await waitTurn();
      this.#requireHealthyCaptureReadiness(operationGeneration);
      this.#drainCaptureFrames();
      pending = route.leaf.flush();
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
    if (pending.pending_frames !== 0) {
      throw Object.assign(new Error('formal media route did not acknowledge capture readiness'), {
        reason: 'AUDIO_CAPTURE_MEDIA_NOT_ACKNOWLEDGED',
      });
    }
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

  async #fail(error: unknown): Promise<void> {
    if (this.#closed) {
      this.#setStatus('closed', null);
      return;
    }
    // A late continuation from the operation already fenced by the first
    // failure cannot start a second cleanup or replace its exact stable reason.
    if (this.#failureCleanupReason !== null && ['cleanup_pending', 'failed'].includes(this.#status) && this.#failureCleanupPromise === null) return;
    const failureReason = stableFailureReason(error);
    if (this.#failureCleanupPromise === null) {
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
    this.#operationGeneration += 1;
    this.#route?.leaf.close('MEDIA_LOCAL_CLOSE');
    this.#route = null;
    this.#speech = null;
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
    this.#mediaSentFrames = 0;
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
    for (const authority of authorities.values()) await this.#revokeMediaAuthority(authority);
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

  #publish(): void {
    this.#onStatus?.(this.#status, this.#reason);
  }
}
