import { ProductP1VoiceRouteOwner, type ProductP1VoiceStatus } from './productP1VoiceRoute';
import { ProductWebP2ActivationOwner, type ProductWebP2ActivationBinding } from './productWebActivation';
import { classifyProductP2Notification } from './productP2Notification';
import { parseNativeGeneratedText, nativeVoiceResponseKey } from './nativeGeneratedText';
import type { DedicatedMediaSocketFactory } from './adapters/browserDedicatedMediaRoute';
import type { AudioResponseRef } from './audioPort';

export type NativeVoiceMessage = Readonly<{
  id: string; role: 'user' | 'assistant'; content: string; timestamp: string;
  responseKey?: string;
  nativeTurnKey?: string;
  state?: 'generating' | 'generated' | 'interrupted' | 'played';
}>;

export type NativeVoiceRequest = (method: string, params: Record<string, unknown>, options?: {
  requestId?: string; timeoutMs?: number; signal?: AbortSignal;
}) => Promise<unknown>;

/** Headless Native composition. Audio algorithms and all protocol validation
 * remain with the production owners; the host supplies only transport and UI.
 * A client instance owns exactly one activation and is never reopened.
 */
export class HeadlessNativeVoice {
  private readonly activation: ProductWebP2ActivationOwner;
  private readonly voice: ProductP1VoiceRouteOwner;
  private binding: ProductWebP2ActivationBinding | null = null;
  private retired = false;
  private starting: Promise<void> | null = null;
  private closing: Promise<void> | null = null;
  private response: Readonly<AudioResponseRef> | null = null;
  private readonly stopped = new Set<Readonly<AudioResponseRef>>();
  private readonly timers = new Set<ReturnType<typeof setTimeout>>();
  private textRevision = 0;
  private confirmedHost: unknown;

  constructor(private readonly options: {
    request: NativeVoiceRequest;
    expectedOrigin: string;
    expectedAtlasBindingId: string;
    captureWorkletModuleUrl: string;
    socketFactory?: DedicatedMediaSocketFactory;
    onMessage: (message: NativeVoiceMessage) => void;
    onStatus: (status: ProductP1VoiceStatus | 'connecting' | 'failed', reason: string | null) => void;
  }) {
    this.activation = new ProductWebP2ActivationOwner({ enabled: true,
      request: async (method, params, requestId) => {
        const response = await options.request(method, params, { requestId });
        if (method === 'live_voice.composition.p2.activate') {
          this.confirmedHost = (response as { result?: { execution_host?: unknown } })?.result?.execution_host;
        }
        return response;
      },
    });
    this.voice = new ProductP1VoiceRouteOwner({ enabled: true,
      request: options.request, expected_origin: options.expectedOrigin,
      capture_worklet_module_url: options.captureWorkletModuleUrl,
      ...(options.socketFactory ? { socket_factory: options.socketFactory } : {}),
      native_agent_model_confirmed: () => this.activation.snapshot().agent_model_selection !== undefined,
      on_status: (status, reason) => { if (!this.retired) options.onStatus(status, reason); },
      on_barge_in_speech_start: () => { void this.interruptSpeech().catch(error => this.fail(error)); },
    });
  }

  start(binding: ProductWebP2ActivationBinding): Promise<void> {
    if (this.retired) return Promise.reject(new Error('NATIVE_VOICE_RETIRED'));
    if (this.starting) return this.starting;
    if (this.binding) return Promise.reject(new Error('NATIVE_VOICE_ALREADY_STARTED'));
    this.binding = Object.freeze({ ...binding });
    this.options.onStatus('connecting', null);
    this.starting = (async () => {
      await this.activation.start(binding);
      if (this.retired) return;
      const host = this.confirmedHost as { kind?: unknown; binding_id?: unknown } | undefined;
      if (host?.kind !== 'atlas' || host.binding_id !== this.options.expectedAtlasBindingId) {
        throw new Error('ATLAS_EXECUTION_HOST_NOT_CONFIRMED');
      }
      await this.activation.runAuthorizedMediaStart(binding, {
        start: () => this.voice.startCapture(binding), cancel: () => this.voice.close(),
      });
      if (this.retired) return;
      if (this.voice.interactionEngine() !== 'openai-realtime-native') throw new Error('NATIVE_VOICE_ENGINE_REQUIRED');
      // Native VAD owns committed speech. Never call stopAndRecognize or submit
      // transcriptions to the business bridge a second time.
      void this.pollNotifications();
      void this.pollText();
    })().catch(async error => {
      this.options.onStatus('failed', error instanceof Error ? error.message : 'NATIVE_VOICE_START_FAILED');
      await this.close().catch(() => undefined);
      throw error;
    });
    return this.starting;
  }

  interruptSpeech(): Promise<void> {
    const response = this.response;
    if (this.retired || !response || this.voice.status().status !== 'playing') return Promise.resolve();
    // Native's media stop already owns the exact stop receipt. P2 bargeIn is
    // the Cascade path and must not be called a second time for Native.
    this.stopped.add(response);
    if (this.stopped.size > 128) this.stopped.delete(this.stopped.values().next().value!);
    this.voice.stopAgentPlayout(response);
    this.response = null;
    return Promise.resolve();
  }

  close(): Promise<void> {
    this.retired = true;
    for (const timer of this.timers) clearTimeout(timer);
    this.timers.clear();
    if (this.closing) return this.closing;
    this.closing = (async () => {
      // Keep the activation alive until the media owner's final receipts settle.
      const results = await Promise.allSettled([this.voice.close()]);
      results.push(...await Promise.allSettled([this.activation.close().then(() => undefined)]));
      const rejected = results.find(result => result.status === 'rejected');
      if (rejected?.status === 'rejected') throw rejected.reason;
      this.options.onStatus('closed', null);
    })().finally(() => { this.closing = null; });
    return this.closing;
  }

  private schedule(action: () => Promise<void>, delay: number): void {
    if (this.retired) return;
    const timer = setTimeout(() => { this.timers.delete(timer); void action(); }, delay);
    this.timers.add(timer);
  }

  private fail(error: unknown): void {
    if (this.retired) return;
    this.options.onStatus('failed', error instanceof Error ? error.message : 'NATIVE_VOICE_FAILED');
    void this.close().catch(() => { this.options.onStatus('failed', 'NATIVE_VOICE_CLEANUP_PENDING'); });
  }

  private async pollNotifications(): Promise<void> {
    try {
      const notification = await this.activation.nextNotification();
      if (this.retired) return;
      const disposition = classifyProductP2Notification(notification);
      if (disposition.kind === 'native_user_transcript') {
        this.options.onMessage(disposition.message);
        for (const message of disposition.following_assistant) this.options.onMessage({ ...message,
          responseKey: nativeVoiceResponseKey(message) ?? undefined, state: 'played' });
      } else if (disposition.kind === 'native_audio') {
        const response = disposition.response;
        this.response = response;
        void this.voice.playNativeAudio(disposition).then(message => {
          if (this.retired) return;
          if (this.response === response) this.response = null;
          if (message) this.options.onMessage({ ...message,
            responseKey: nativeVoiceResponseKey(message) ?? undefined, state: 'played' });
        }).catch(error => {
          // The production audio owner already sealed the stopped prefix.
          if (this.retired || this.stopped.has(response)) return;
          this.fail(error);
        });
      } else if (disposition.kind === 'failed') {
        throw new Error(disposition.reason);
      } else if (disposition.kind === 'presentation') {
        // Host execution results must return through Native. Do not silently
        // adopt the Swarm Task presentation/approval UI in this small client.
        throw new Error('NATIVE_VOICE_UNSUPPORTED_PRESENTATION');
      }
      this.schedule(() => this.pollNotifications(), 50);
    } catch (error) { this.fail(error); }
  }

  private async pollText(): Promise<void> {
    if (this.retired || !this.binding) return;
    try {
      const result = await this.options.request('live_voice.media.native_text', { ...this.binding, after_revision: this.textRevision });
      if (this.retired) return;
      const projection = parseNativeGeneratedText(result, this.binding, this.textRevision);
      this.textRevision = projection.revision;
      for (const message of projection.messages) this.options.onMessage({ ...message,
        responseKey: message.nativeVoice.responseKey, state: message.nativeVoice.state });
      this.schedule(() => this.pollText(), 200);
    } catch (error) { this.fail(error); }
  }
}

export type { ProductWebP2ActivationBinding, ProductP1VoiceStatus, DedicatedMediaSocketFactory };
export { HeadlessVoiceControl } from './headlessControl';
