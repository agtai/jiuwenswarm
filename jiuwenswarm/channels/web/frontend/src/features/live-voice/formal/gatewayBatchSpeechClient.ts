import {
  LIVE_VOICE_AUDIO_FRAME_DURATION_MS,
  createAudioRenderPlan,
  createCapturedAudioFrame,
  type AudioProviderRef,
  type AudioRenderPlan,
  type AudioResponseRef,
  type CapturedAudioFrame,
} from './audioPort.js';
import type { BrowserAudioPcmChunk } from './adapters/browserAudioIOAdapter.js';

export const LIVE_VOICE_SPEECH_CONTRACT_VERSION = 'live-voice.contract.v2';
export const SPEECH_CAPABILITIES_METHOD = 'live_voice.speech.capabilities';
export const SPEECH_RECOGNIZE_BATCH_METHOD = 'live_voice.speech.recognize_batch';
export const SPEECH_SYNTHESIZE_BATCH_METHOD = 'live_voice.speech.synthesize_batch';
export const SPEECH_CANCEL_METHOD = 'live_voice.speech.cancel';

const MAX_BATCH_AUDIO_BYTES = 4 * 1024 * 1024;
const MAX_SYNTHESIS_AUDIO_BYTES = 8 * 1024 * 1024;
const MAX_RECOGNITION_TEXT_CHARS = 16_000;
const MAX_SYNTHESIS_TEXT_CHARS = 4_000;
const MAX_BATCH_TIMEOUT_MS = 30_000;
const MAX_CLOSE_TIMEOUT_MS = 5_000;
const MAX_IDENTITY_TOMBSTONES = 512;
const DEFAULT_TIMEOUT_MS = 15_000;
const SPEECH_CAPABILITY_CONTROL_OPERATION = 'speech.capabilities.get' as const;
const SPEECH_CANCEL_OPERATION = 'speech.batch.cancel' as const;
const GATEWAY_SPEECH_OPERATIONS = Object.freeze([
  SPEECH_CAPABILITY_CONTROL_OPERATION,
  'speech.recognize.batch',
  'speech.synthesize.batch',
  SPEECH_CANCEL_OPERATION,
] as const);
const SPEECH_CAPABILITY_DESCRIPTOR_KEYS = Object.freeze([
  'component',
  'contract_major',
  'supported_operations',
  'supported_event_types',
  'batch_modes',
  'stream_modes',
  'supports_cancel_ack',
  'supports_replay',
  'declared_limits',
  'fallback_identity',
  'availability',
]);
const SPEECH_DECLARED_LIMIT_KEYS = Object.freeze([
  'max_input_audio_bytes',
  'max_output_audio_bytes',
  'max_recognition_text_chars',
  'max_text_chars',
  'max_timeout_ms',
  'recognition_input',
  'synthesis_output',
  'resampling',
  'credential_boundary',
  'max_operation_capacity',
  'operation_replay_window',
  'identity_tombstone_window',
  'close_timeout_max_ms',
  'authorization',
]);

export type GatewaySpeechOperation = typeof GATEWAY_SPEECH_OPERATIONS[number];

export interface GatewaySpeechTransport {
  /** Implementations must keep Speech params memory-only and must not log or persist raw audio. */
  request<T = unknown>(method: string, params?: Record<string, unknown>, options?: Readonly<{ timeoutMs?: number; signal?: AbortSignal }>): Promise<T>;
}

export interface GatewaySpeechScope {
  readonly subject_id: string;
  readonly project_id: null;
  readonly session_id: string;
  readonly assurance: 'request_asserted';
}

export interface GatewaySpeechProvider extends AudioProviderRef {
  readonly implementation_class: 'formal';
  readonly fallback_from: null;
  readonly model: string;
  readonly voice?: string;
}

export interface FormalBatchRecognitionResult {
  readonly operation: 'speech.recognize.batch';
  readonly capture: Readonly<{
    capture_id: string;
    capture_generation: number;
    track_id: string;
    final: true;
  }>;
  readonly final_text: string;
  readonly raw_text: string;
  readonly commits_turn: false;
  readonly provider: Readonly<GatewaySpeechProvider>;
}

export interface FormalBatchSynthesisResult {
  readonly operation: 'speech.synthesize.batch';
  readonly response: Readonly<AudioResponseRef>;
  readonly unit_id: string;
  readonly chunks: readonly Readonly<BrowserAudioPcmChunk>[];
  readonly provider: Readonly<GatewaySpeechProvider>;
  readonly presented: false;
}

export interface FormalRecognitionInput {
  readonly frames: readonly Readonly<CapturedAudioFrame>[];
  readonly locale: string;
  readonly correlationId: string;
  readonly operationId?: string;
  readonly timeoutMs?: number;
  readonly signal?: AbortSignal;
}

export interface FormalSynthesisInput {
  readonly response: Readonly<AudioResponseRef>;
  readonly unitId: string;
  readonly renderPlan: Readonly<AudioRenderPlan>;
  readonly authoritativeAgentText: true;
  readonly locale: string;
  readonly voice?: string | null;
  readonly requiredSampleRateHz: number;
  readonly correlationId: string;
  readonly operationId?: string;
  readonly timeoutMs?: number;
  readonly signal?: AbortSignal;
}

export interface LocalSpeechCapability {
  readonly enabled: boolean;
  readonly formal_available: boolean;
  readonly recognition_batch: boolean;
  readonly synthesis_batch: boolean;
  readonly fallback: Readonly<{
    recognition: 'browser-speech-recognition';
    synthesis: 'browser-speech-synthesis';
    automatic: false;
  }>;
  readonly degradation: Readonly<{
    state: 'formal_available' | 'formal_unavailable' | 'formal_disabled';
    reason_id: 'FEATURE_DISABLED' | 'PROVIDER_UNAVAILABLE' | 'SPEECH_OPERATION_UNAVAILABLE' | null;
    browser_fallback_is_formal: false;
    browser_fallback_automatic: false;
  }>;
  readonly gateway?: Readonly<GatewaySpeechCapabilityEvidence>;
}

export interface GatewaySpeechCapabilityEvidence {
  readonly contract_version: typeof LIVE_VOICE_SPEECH_CONTRACT_VERSION;
  readonly provider_id: string;
  readonly provider_available: boolean;
  readonly provider_configured: boolean;
  readonly authorization_available: boolean;
  readonly service_closed: boolean;
  readonly supported_operations: readonly GatewaySpeechOperation[];
  readonly evidence_scope: 'sanitized_gateway_batch_speech_capability';
  readonly browser_fallback_is_formal: false;
  readonly browser_fallback_automatic: false;
}

interface ContractErrorPayload {
  readonly code: string;
  readonly reason: string | null;
  readonly message: string;
  readonly retriable: boolean;
  readonly correlation_id: string | null;
  readonly details: Readonly<Record<string, unknown>>;
}

export class GatewayBatchSpeechError extends Error {
  constructor(
    readonly code: string,
    readonly reason: string,
    message: string,
    readonly retriable = false,
    readonly details: Readonly<Record<string, unknown>> = Object.freeze({})
  ) {
    super(message);
    this.name = 'GatewayBatchSpeechError';
  }
}

interface ActiveOperation {
  readonly operationId: string;
  readonly correlationId: string;
  readonly token: number;
}

interface ActiveRecognition extends ActiveOperation {
  readonly captureId: string;
  readonly captureGeneration: number;
}

function requiredText(value: unknown, field: string): string {
  if (typeof value !== 'string' || value.trim().length === 0) {
    throw new GatewayBatchSpeechError('INVALID_ARGUMENT', 'INVALID_REQUIRED_TEXT', `${field} must be non-empty`);
  }
  return value;
}

function nonNegativeSafeInteger(value: unknown, field: string): number {
  if (!Number.isSafeInteger(value) || (value as number) < 0) {
    throw new GatewayBatchSpeechError('INVALID_ARGUMENT', 'INVALID_SAFE_INTEGER', `${field} must be a non-negative safe integer`);
  }
  return value as number;
}

function positiveSafeInteger(value: unknown, field: string): number {
  const parsed = nonNegativeSafeInteger(value, field);
  if (parsed === 0) {
    throw new GatewayBatchSpeechError('INVALID_ARGUMENT', 'INVALID_SAFE_INTEGER', `${field} must be positive`);
  }
  return parsed;
}

function objectValue(value: unknown, field: string): Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new GatewayBatchSpeechError('PROTOCOL_VIOLATION', 'INVALID_GATEWAY_RESPONSE', `${field} must be an object`);
  }
  return value as Record<string, unknown>;
}

function closedGatewayObject(
  value: unknown,
  expectedKeys: readonly string[],
  field: string,
): Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new GatewayBatchSpeechError(
      'PROTOCOL_VIOLATION',
      'INVALID_SPEECH_CAPABILITY',
      `${field} must be the closed Gateway descriptor object`,
    );
  }
  const record = value as Record<string, unknown>;
  const actual = Object.keys(record).sort();
  const expected = [...expectedKeys].sort();
  if (actual.length !== expected.length || actual.some((key, index) => key !== expected[index])) {
    throw new GatewayBatchSpeechError(
      'PROTOCOL_VIOLATION',
      'INVALID_SPEECH_CAPABILITY',
      `${field} fields do not match the closed Gateway descriptor`,
    );
  }
  return record;
}

function positiveCapabilityInteger(value: unknown): value is number {
  return Number.isSafeInteger(value) && (value as number) > 0;
}

function exactArgumentRecord(
  value: unknown,
  expectedKeys: readonly string[],
  field: string,
): Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new TypeError(`${field} must be an object`);
  }
  const record = value as Record<string, unknown>;
  const keys = Object.keys(record).sort();
  const expected = [...expectedKeys].sort();
  if (keys.length !== expected.length || keys.some((key, index) => key !== expected[index])) {
    throw new TypeError(`${field} fields are not closed`);
  }
  return record;
}

function createDefaultId(): string {
  const randomUuid = globalThis.crypto?.randomUUID;
  if (typeof randomUuid === 'function') return randomUuid.call(globalThis.crypto);
  return `speech-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function parseContractError(value: unknown): ContractErrorPayload {
  const error = objectValue(value, 'error');
  const details = objectValue(error.details, 'error.details');
  return {
    code: requiredText(error.code, 'error.code'),
    reason: error.reason === null ? null : requiredText(error.reason, 'error.reason'),
    message: requiredText(error.message, 'error.message'),
    retriable: error.retriable === true,
    correlation_id: error.correlation_id === null ? null : requiredText(error.correlation_id, 'error.correlation_id'),
    details,
  };
}

function parseEnvelope(value: unknown, requestId: string, operationId: string): Record<string, unknown> {
  const envelope = objectValue(value, 'speech_result');
  if (
    envelope.contract_version !== LIVE_VOICE_SPEECH_CONTRACT_VERSION ||
    envelope.request_id !== requestId ||
    envelope.operation_id !== operationId ||
    typeof envelope.ok !== 'boolean'
  ) {
    throw new GatewayBatchSpeechError('PROTOCOL_VIOLATION', 'INVALID_RESULT_ENVELOPE', 'Gateway returned an invalid speech result envelope');
  }
  if (!envelope.ok) {
    const error = parseContractError(envelope.error);
    throw new GatewayBatchSpeechError(error.code, error.reason ?? 'SPEECH_OPERATION_FAILED', error.message, error.retriable, error.details);
  }
  if (envelope.error !== null) {
    throw new GatewayBatchSpeechError('PROTOCOL_VIOLATION', 'UNEXPECTED_RESULT_ERROR', 'successful speech result carried an error');
  }
  return objectValue(envelope.result, 'speech_result.result');
}

function encodeBase64(bytes: Uint8Array): string {
  let binary = '';
  const stride = 0x8000;
  for (let offset = 0; offset < bytes.length; offset += stride) {
    binary += String.fromCharCode(...bytes.subarray(offset, Math.min(offset + stride, bytes.length)));
  }
  return btoa(binary);
}

function decodeBase64(value: unknown, maxBytes: number): Uint8Array {
  const encoded = requiredText(value, 'audio.data_base64');
  const maxEncodedChars = 4 * Math.ceil(maxBytes / 3);
  if (encoded.length > maxEncodedChars) {
    throw new GatewayBatchSpeechError('PROTOCOL_VIOLATION', 'AUDIO_LIMIT_EXCEEDED', 'Gateway returned oversized speech audio');
  }
  try {
    const binary = atob(encoded);
    if (binary.length > maxBytes) {
      throw new GatewayBatchSpeechError('PROTOCOL_VIOLATION', 'AUDIO_LIMIT_EXCEEDED', 'Gateway returned oversized speech audio');
    }
    const bytes = new Uint8Array(binary.length);
    for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
    return bytes;
  } catch (error) {
    if (error instanceof GatewayBatchSpeechError) throw error;
    throw new GatewayBatchSpeechError('PROTOCOL_VIOLATION', 'INVALID_AUDIO_BASE64', 'Gateway returned invalid base64 audio', false, { cause: String(error) });
  }
}

function writeAscii(view: DataView, offset: number, value: string): void {
  for (let index = 0; index < value.length; index += 1) view.setUint8(offset + index, value.charCodeAt(index));
}

export function capturedFramesToPcm16Wav(frames: readonly Readonly<CapturedAudioFrame>[]): Uint8Array {
  if (frames.length === 0) {
    throw new GatewayBatchSpeechError('INVALID_ARGUMENT', 'FINAL_CAPTURE_REQUIRED', 'final batch recognition requires captured AIO-B frames');
  }
  const normalized = frames.map(createCapturedAudioFrame);
  const first = normalized[0];
  if (first.seq !== 0 || first.sample_cursor !== 0) {
    throw new GatewayBatchSpeechError('INVALID_ARGUMENT', 'INCOMPLETE_CAPTURE', 'batch recognition must start at the first AIO-B frame');
  }
  let sampleCount = 0;
  for (let index = 0; index < normalized.length; index += 1) {
    const frame = normalized[index];
    if (
      frame.capture.capture_id !== first.capture.capture_id ||
      frame.capture.capture_generation !== first.capture.capture_generation ||
      frame.capture.track_id !== first.capture.track_id ||
      frame.format.sample_rate_hz !== first.format.sample_rate_hz ||
      frame.seq !== index ||
      frame.sample_cursor !== sampleCount
    ) {
      throw new GatewayBatchSpeechError('INVALID_ARGUMENT', 'NON_CONTIGUOUS_CAPTURE', 'AIO-B frames must be one exact contiguous capture');
    }
    sampleCount += frame.samples.length;
  }
  const byteLength = 44 + sampleCount * 2;
  if (byteLength > MAX_BATCH_AUDIO_BYTES) {
    throw new GatewayBatchSpeechError('INVALID_ARGUMENT', 'AUDIO_LIMIT_EXCEEDED', 'batch capture exceeds the formal speech package limit');
  }
  const bytes = new Uint8Array(byteLength);
  const view = new DataView(bytes.buffer);
  writeAscii(view, 0, 'RIFF');
  view.setUint32(4, byteLength - 8, true);
  writeAscii(view, 8, 'WAVE');
  writeAscii(view, 12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, first.format.sample_rate_hz, true);
  view.setUint32(28, first.format.sample_rate_hz * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeAscii(view, 36, 'data');
  view.setUint32(40, sampleCount * 2, true);
  let cursor = 44;
  for (const frame of normalized) {
    for (const sample of frame.samples) {
      const clipped = Math.max(-1, Math.min(1, sample));
      view.setInt16(cursor, clipped < 0 ? Math.round(clipped * 32768) : Math.round(clipped * 32767), true);
      cursor += 2;
    }
  }
  return bytes;
}

interface DecodedPcmWav {
  readonly sampleRateHz: number;
  readonly samples: Float32Array;
}

function decodePcm16MonoWav(bytes: Uint8Array, requiredSampleRateHz: number): DecodedPcmWav {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const ascii = (offset: number, size: number) => String.fromCharCode(...bytes.subarray(offset, offset + size));
  if (bytes.length < 44 || ascii(0, 4) !== 'RIFF' || ascii(8, 4) !== 'WAVE') {
    throw new GatewayBatchSpeechError('PROTOCOL_VIOLATION', 'INVALID_PCM_WAV', 'Gateway returned an invalid WAV payload');
  }
  if (view.getUint32(4, true) + 8 !== bytes.length) {
    throw new GatewayBatchSpeechError('PROTOCOL_VIOLATION', 'INVALID_PCM_WAV', 'Gateway returned a truncated or overlong WAV payload');
  }
  let offset = 12;
  let sampleRateHz = 0;
  let validFormat = false;
  let dataOffset = -1;
  let dataLength = 0;
  while (offset + 8 <= bytes.length) {
    const chunk = ascii(offset, 4);
    const length = view.getUint32(offset + 4, true);
    const body = offset + 8;
    if (body + length > bytes.length) break;
    if (chunk === 'fmt ' && length >= 16) {
      sampleRateHz = view.getUint32(body + 4, true);
      validFormat =
        view.getUint16(body, true) === 1 &&
        view.getUint16(body + 2, true) === 1 &&
        view.getUint16(body + 12, true) === 2 &&
        view.getUint16(body + 14, true) === 16 &&
        view.getUint32(body + 8, true) === sampleRateHz * 2;
    } else if (chunk === 'data') {
      dataOffset = body;
      dataLength = length;
    }
    offset = body + length + (length % 2);
  }
  if (!validFormat || dataOffset < 0 || dataLength === 0 || dataLength % 2 !== 0 || dataOffset + dataLength > bytes.length) {
    throw new GatewayBatchSpeechError('PROTOCOL_VIOLATION', 'UNSUPPORTED_BATCH_AUDIO_FORMAT', 'Gateway speech audio is not non-empty mono PCM16 WAV');
  }
  if (sampleRateHz !== requiredSampleRateHz) {
    throw new GatewayBatchSpeechError(
      'CAPABILITY_UNAVAILABLE',
      'SPEECH_SAMPLE_RATE_MISMATCH',
      'Provider audio does not match the unlocked AIO-B playout rate',
      false,
      {
        expected_sample_rate_hz: requiredSampleRateHz,
        actual_sample_rate_hz: sampleRateHz,
      }
    );
  }
  const samples = new Float32Array(dataLength / 2);
  for (let index = 0; index < samples.length; index += 1) {
    const value = view.getInt16(dataOffset + index * 2, true);
    samples[index] = value < 0 ? value / 32768 : value / 32767;
  }
  return { sampleRateHz, samples };
}

function parseProvider(value: unknown): Readonly<GatewaySpeechProvider> {
  const provider = objectValue(value, 'provider');
  if (provider.implementation_class !== 'formal' || provider.fallback_from !== null) {
    throw new GatewayBatchSpeechError('PROTOCOL_VIOLATION', 'INVALID_PROVIDER_PROVENANCE', 'formal Gateway speech requires exact formal Provider provenance');
  }
  const parsed: GatewaySpeechProvider = {
    provider_id: requiredText(provider.provider_id, 'provider.provider_id'),
    implementation_class: 'formal',
    fallback_from: null,
    model: requiredText(provider.model, 'provider.model'),
    ...(provider.voice === undefined ? {} : { voice: requiredText(provider.voice, 'provider.voice') }),
  };
  return Object.freeze(parsed);
}

function sameResponse(left: Readonly<AudioResponseRef>, right: Readonly<AudioResponseRef>): boolean {
  return left.interaction_id === right.interaction_id && left.response_id === right.response_id && left.response_generation === right.response_generation;
}

export class GatewayBatchSpeechClient {
  readonly #enabled: boolean;
  readonly #transport: GatewaySpeechTransport | null;
  readonly #scope: Readonly<GatewaySpeechScope> | null;
  readonly #createId: () => string;
  #token = 0;
  #activeRecognition: ActiveRecognition | null = null;
  readonly #seenCaptures = new Map<string, number>();
  readonly #responses = new Map<string, ActiveOperation>();
  readonly #responseGenerations = new Map<string, number>();

  constructor(
    options: Readonly<{
      enabled: boolean;
      transport: GatewaySpeechTransport;
      scope: Readonly<GatewaySpeechScope>;
      createId?: () => string;
    }>
  ) {
    this.#enabled = options.enabled === true;
    if (!this.#enabled) {
      // Feature-off deliberately avoids reading transport, scope, or identity
      // hooks so compatibility fallback has zero Gateway allocation/effects.
      this.#transport = null;
      this.#scope = null;
      this.#createId = createDefaultId;
      return;
    }
    this.#transport = options.transport;
    this.#scope = Object.freeze({ ...options.scope });
    this.#createId = options.createId ?? createDefaultId;
    requiredText(this.#scope.subject_id, 'scope.subject_id');
    requiredText(this.#scope.session_id, 'scope.session_id');
    if (this.#scope.project_id !== null || this.#scope.assurance !== 'request_asserted') {
      throw new GatewayBatchSpeechError(
        'INVALID_ARGUMENT',
        'INVALID_SPEECH_SCOPE',
        'formal batch speech requires request-asserted session scope without project authority'
      );
    }
  }

  async capabilities(): Promise<Readonly<LocalSpeechCapability>> {
    const fallback = Object.freeze({
      recognition: 'browser-speech-recognition' as const,
      synthesis: 'browser-speech-synthesis' as const,
      automatic: false as const,
    });
    const disabledDegradation = Object.freeze({
      state: 'formal_disabled' as const,
      reason_id: 'FEATURE_DISABLED' as const,
      browser_fallback_is_formal: false as const,
      browser_fallback_automatic: false as const,
    });
    if (!this.#enabled) {
      return Object.freeze({
        enabled: false,
        formal_available: false,
        recognition_batch: false,
        synthesis_batch: false,
        fallback,
        degradation: disabledDegradation,
      });
    }
    const scope = this.#scope!;
    const gateway = await this.#transport!.request(SPEECH_CAPABILITIES_METHOD, { session_id: scope.session_id });
    const payload = objectValue(gateway, 'capability');
    const provider = objectValue(payload.provider, 'capability.provider');
    const descriptor = closedGatewayObject(
      payload.capability,
      SPEECH_CAPABILITY_DESCRIPTOR_KEYS,
      'capability.capability',
    );
    const declaredLimits = closedGatewayObject(
      descriptor.declared_limits,
      SPEECH_DECLARED_LIMIT_KEYS,
      'capability.capability.declared_limits',
    );
    const gatewayFallback = objectValue(payload.fallback, 'capability.fallback');
    const advertisedOperations = descriptor.supported_operations;
    const providerAvailable = provider.available;
    const providerConfigured = provider.provider_configured;
    const authorizationAvailable = provider.authorization_available;
    const serviceClosed = provider.service_closed;
    if (
      payload.contract_version !== LIVE_VOICE_SPEECH_CONTRACT_VERSION
      || descriptor.component !== 'speech.batch.gateway'
      || descriptor.contract_major !== 'v2'
      || !Array.isArray(advertisedOperations)
      || advertisedOperations.some((operation) => typeof operation !== 'string')
      || advertisedOperations.some((operation) => !(GATEWAY_SPEECH_OPERATIONS as readonly string[]).includes(operation))
      || new Set(advertisedOperations).size !== advertisedOperations.length
      || !advertisedOperations.includes(SPEECH_CAPABILITY_CONTROL_OPERATION)
      || !advertisedOperations.includes(SPEECH_CANCEL_OPERATION)
      || !Array.isArray(descriptor.supported_event_types)
      || descriptor.supported_event_types.length !== 0
      || !Array.isArray(descriptor.batch_modes)
      || descriptor.batch_modes.length !== 1
      || descriptor.batch_modes[0] !== 'batch'
      || !Array.isArray(descriptor.stream_modes)
      || descriptor.stream_modes.length !== 0
      || descriptor.supports_cancel_ack !== true
      || descriptor.supports_replay !== false
      || descriptor.fallback_identity !== 'browser-speech-compatibility'
      || typeof providerAvailable !== 'boolean'
      || typeof providerConfigured !== 'boolean'
      || typeof authorizationAvailable !== 'boolean'
      || typeof serviceClosed !== 'boolean'
      || providerAvailable !== (providerConfigured && authorizationAvailable && !serviceClosed)
      || descriptor.availability !== (providerAvailable ? 'available' : 'unavailable')
      || (providerAvailable === true && provider.implementation_class !== 'formal')
      || (providerAvailable === false && provider.implementation_class !== 'unsupported')
      || (providerAvailable === false && advertisedOperations.some(
        (operation) => operation === 'speech.recognize.batch' || operation === 'speech.synthesize.batch',
      ))
      || declaredLimits.max_input_audio_bytes !== MAX_BATCH_AUDIO_BYTES
      || declaredLimits.max_output_audio_bytes !== MAX_SYNTHESIS_AUDIO_BYTES
      || declaredLimits.max_recognition_text_chars !== MAX_RECOGNITION_TEXT_CHARS
      || declaredLimits.max_text_chars !== MAX_SYNTHESIS_TEXT_CHARS
      || declaredLimits.max_timeout_ms !== MAX_BATCH_TIMEOUT_MS
      || declaredLimits.recognition_input !== 'wav_pcm16_mono'
      || declaredLimits.synthesis_output !== 'wav_pcm16_mono'
      || declaredLimits.resampling !== 'unsupported'
      || declaredLimits.credential_boundary !== 'gateway_only'
      || !positiveCapabilityInteger(declaredLimits.max_operation_capacity)
      || declaredLimits.operation_replay_window !== declaredLimits.max_operation_capacity
      || !positiveCapabilityInteger(declaredLimits.identity_tombstone_window)
      || declaredLimits.close_timeout_max_ms !== MAX_CLOSE_TIMEOUT_MS
      || declaredLimits.authorization !== 'authenticated_server_owned_exact_binding'
      || gatewayFallback.recognition !== 'browser-speech-recognition'
      || gatewayFallback.synthesis !== 'browser-speech-synthesis'
      || gatewayFallback.automatic !== false
    ) {
      throw new GatewayBatchSpeechError('PROTOCOL_VIOLATION', 'INVALID_SPEECH_CAPABILITY', 'Gateway returned invalid Speech operations');
    }
    const providerId = requiredText(provider.provider_id, 'capability.provider.provider_id');
    const supported = Object.freeze(
      GATEWAY_SPEECH_OPERATIONS.filter((operation) => advertisedOperations.includes(operation)),
    );
    const recognitionBatch = providerAvailable === true && supported.includes('speech.recognize.batch');
    const synthesisBatch = providerAvailable === true && supported.includes('speech.synthesize.batch');
    const formalAvailable = recognitionBatch || synthesisBatch;
    const sanitizedGateway = Object.freeze({
      contract_version: LIVE_VOICE_SPEECH_CONTRACT_VERSION,
      provider_id: providerId,
      provider_available: providerAvailable,
      provider_configured: providerConfigured,
      authorization_available: authorizationAvailable,
      service_closed: serviceClosed,
      supported_operations: supported,
      evidence_scope: 'sanitized_gateway_batch_speech_capability' as const,
      browser_fallback_is_formal: false as const,
      browser_fallback_automatic: false as const,
    });
    return Object.freeze({
      enabled: true,
      formal_available: formalAvailable,
      recognition_batch: recognitionBatch,
      synthesis_batch: synthesisBatch,
      fallback,
      degradation: Object.freeze({
        state: formalAvailable ? 'formal_available' as const : 'formal_unavailable' as const,
        reason_id: formalAvailable
          ? null
          : providerAvailable
            ? 'SPEECH_OPERATION_UNAVAILABLE' as const
            : 'PROVIDER_UNAVAILABLE' as const,
        browser_fallback_is_formal: false as const,
        browser_fallback_automatic: false as const,
      }),
      gateway: sanitizedGateway,
    });
  }

  async recognizeFinal(input: Readonly<FormalRecognitionInput>): Promise<Readonly<FormalBatchRecognitionResult> | null> {
    this.#requireEnabled();
    const wav = capturedFramesToPcm16Wav(input.frames);
    const first = input.frames[0];
    const capture = first.capture;
    const captureId = requiredText(capture.capture_id, 'capture_id');
    const captureGeneration = nonNegativeSafeInteger(capture.capture_generation, 'capture_generation');
    const seenGeneration = this.#seenCaptures.get(captureId);
    if (seenGeneration !== undefined) {
      const reason = seenGeneration === captureGeneration ? 'STALE_RECOGNITION_SESSION' : 'CAPTURE_ID_REUSED';
      const code = seenGeneration === captureGeneration ? 'STALE' : 'CONFLICT';
      throw new GatewayBatchSpeechError(code, reason, 'capture identity was already consumed');
    }
    const baseOperation = this.#beginOperation(input.operationId, input.correlationId);
    const operation: ActiveRecognition = Object.freeze({ ...baseOperation, captureId, captureGeneration });
    const prior = this.#activeRecognition;
    if (prior !== null) void this.#cancelBestEffort(prior);
    this.#activeRecognition = operation;
    this.#boundedSet(this.#seenCaptures, captureId, captureGeneration);
    const timeoutMs = input.timeoutMs ?? DEFAULT_TIMEOUT_MS;
    const requestId = this.#createId();
    let raw: unknown;
    try {
      raw = await this.#transport!.request(
        SPEECH_RECOGNIZE_BATCH_METHOD,
        {
          contract_version: LIVE_VOICE_SPEECH_CONTRACT_VERSION,
          request_id: requestId,
          operation_id: operation.operationId,
          operation: 'speech.recognize.batch',
          correlation_id: operation.correlationId,
          session_id: this.#scope!.session_id,
          scope: this.#scope!,
          timeout_ms: timeoutMs,
          capture: { ...capture, final: true },
          audio: {
            format: 'wav_pcm16_mono',
            sample_rate_hz: first.format.sample_rate_hz,
            channel_count: 1,
            data_base64: encodeBase64(wav),
          },
          locale: requiredText(input.locale, 'locale'),
        },
        { timeoutMs: timeoutMs + 1000, signal: input.signal }
      );
    } catch (error) {
      if (this.#activeRecognition?.token === operation.token) this.#activeRecognition = null;
      if (
        input.signal?.aborted ||
        (typeof error === 'object' && error !== null && ['REQUEST_TIMEOUT', 'REQUEST_ABORTED'].includes(String((error as { code?: unknown }).code)))
      ) {
        void this.#cancelBestEffort(operation);
      }
      throw error;
    }
    if (this.#activeRecognition?.token !== operation.token) return null;
    this.#activeRecognition = null;
    const result = parseEnvelope(raw, requestId, operation.operationId);
    const resultCapture = objectValue(result.capture, 'result.capture');
    const event = objectValue(result.event, 'result.event');
    const hypothesis = objectValue(event.hypothesis, 'result.event.hypothesis');
    const alternatives = hypothesis.alternatives;
    if (
      result.operation !== 'speech.recognize.batch' ||
      resultCapture.capture_id !== capture.capture_id ||
      resultCapture.capture_generation !== capture.capture_generation ||
      resultCapture.track_id !== capture.track_id ||
      resultCapture.final !== true ||
      event.session_id !== capture.capture_id ||
      event.generation !== capture.capture_generation ||
      event.seq !== 0 ||
      event.kind !== 'final' ||
      event.commits_turn !== false ||
      !Array.isArray(alternatives) ||
      alternatives.length === 0
    ) {
      throw new GatewayBatchSpeechError(
        'PROTOCOL_VIOLATION',
        'RECOGNITION_RESULT_MISMATCH',
        'Gateway recognition result does not match the final AIO-B capture'
      );
    }
    const selected = objectValue(alternatives[nonNegativeSafeInteger(hypothesis.selected_index, 'selected_index')], 'selected_alternative');
    return Object.freeze({
      operation: 'speech.recognize.batch',
      capture: Object.freeze({ capture_id: capture.capture_id, capture_generation: capture.capture_generation, track_id: capture.track_id, final: true }),
      final_text: requiredText(selected.display_text, 'display_text'),
      raw_text: requiredText(selected.raw_text, 'raw_text'),
      commits_turn: false,
      provider: parseProvider(result.provider),
    });
  }

  async synthesizeAuthoritative(input: Readonly<FormalSynthesisInput>): Promise<Readonly<FormalBatchSynthesisResult> | null> {
    this.#requireEnabled();
    const response = input.response;
    requiredText(response.interaction_id, 'response.interaction_id');
    requiredText(response.response_id, 'response.response_id');
    const generation = nonNegativeSafeInteger(response.response_generation, 'response.response_generation');
    const last = this.#responseGenerations.get(response.interaction_id) ?? -1;
    if (generation <= last) {
      throw new GatewayBatchSpeechError('STALE', 'STALE_SYNTHESIS_RESPONSE', 'response generation is stale or duplicated');
    }
    if (input.authoritativeAgentText !== true) {
      throw new GatewayBatchSpeechError('PERMISSION_DENIED', 'AUTHORITATIVE_AGENT_TEXT_REQUIRED', 'formal synthesis requires authoritative Agent text');
    }
    let renderPlan: Readonly<AudioRenderPlan>;
    try {
      const raw = exactArgumentRecord(
        input.renderPlan,
        ['display_text', 'spoken_text', 'transforms'],
        'render_plan',
      );
      if (!Array.isArray(raw.transforms)) throw new TypeError('render transforms must be an array');
      const transforms = raw.transforms.map((item) => exactArgumentRecord(
        item,
        ['transform', 'source_start', 'source_end', 'rendered_text'],
        'render_plan.transform',
      ));
      renderPlan = createAudioRenderPlan(
        raw.display_text as string,
        raw.spoken_text as string,
        transforms as unknown as Readonly<AudioRenderPlan>['transforms'],
      );
    } catch {
      throw new GatewayBatchSpeechError(
        'INVALID_ARGUMENT',
        'INVALID_RENDER_PLAN',
        'formal synthesis requires a closed authoritative render plan',
      );
    }
    const operation = this.#beginOperation(input.operationId, input.correlationId);
    const prior = this.#responses.get(response.interaction_id);
    if (prior !== undefined) void this.#cancelBestEffort(prior);
    this.#responses.set(response.interaction_id, operation);
    this.#boundedSet(this.#responseGenerations, response.interaction_id, generation);
    const timeoutMs = input.timeoutMs ?? DEFAULT_TIMEOUT_MS;
    const requestId = this.#createId();
    let raw: unknown;
    try {
      raw = await this.#transport!.request(
        SPEECH_SYNTHESIZE_BATCH_METHOD,
        {
          contract_version: LIVE_VOICE_SPEECH_CONTRACT_VERSION,
          request_id: requestId,
          operation_id: operation.operationId,
          operation: 'speech.synthesize.batch',
          correlation_id: operation.correlationId,
          session_id: this.#scope!.session_id,
          scope: this.#scope!,
          timeout_ms: timeoutMs,
          response: { ...response },
          unit_id: requiredText(input.unitId, 'unit_id'),
          render_plan: {
            display_text: renderPlan.display_text,
            spoken_text: renderPlan.spoken_text,
            transforms: renderPlan.transforms.map(item => ({ ...item })),
          },
          authoritative_agent_text: true,
          locale: requiredText(input.locale, 'locale'),
          voice: input.voice ?? null,
          required_sample_rate_hz: positiveSafeInteger(input.requiredSampleRateHz, 'required_sample_rate_hz'),
        },
        { timeoutMs: timeoutMs + 1000, signal: input.signal }
      );
    } catch (error) {
      if (this.#responses.get(response.interaction_id)?.token === operation.token) this.#responses.delete(response.interaction_id);
      if (
        input.signal?.aborted ||
        (typeof error === 'object' && error !== null && ['REQUEST_TIMEOUT', 'REQUEST_ABORTED'].includes(String((error as { code?: unknown }).code)))
      ) {
        void this.#cancelBestEffort(operation);
      }
      throw error;
    }
    if (this.#responses.get(response.interaction_id)?.token !== operation.token) return null;
    this.#responses.delete(response.interaction_id);
    const result = parseEnvelope(raw, requestId, operation.operationId);
    const resultResponse = objectValue(result.response, 'result.response');
    const audio = objectValue(result.audio, 'result.audio');
    if (
      result.operation !== 'speech.synthesize.batch' ||
      !sameResponse(resultResponse as unknown as AudioResponseRef, response) ||
      result.unit_id !== input.unitId ||
      result.presented !== false ||
      audio.format !== 'wav_pcm16_mono' ||
      audio.channel_count !== 1
    ) {
      throw new GatewayBatchSpeechError(
        'PROTOCOL_VIOLATION',
        'SYNTHESIS_RESULT_MISMATCH',
        'Gateway synthesis result does not match the authoritative response'
      );
    }
    const requiredRate = positiveSafeInteger(input.requiredSampleRateHz, 'required_sample_rate_hz');
    if (audio.sample_rate_hz !== requiredRate) {
      throw new GatewayBatchSpeechError('CAPABILITY_UNAVAILABLE', 'SPEECH_SAMPLE_RATE_MISMATCH', 'Gateway declared a mismatched AIO-B playout rate');
    }
    const decoded = decodePcm16MonoWav(decodeBase64(audio.data_base64, MAX_SYNTHESIS_AUDIO_BYTES), requiredRate);
    const provider = parseProvider(result.provider);
    const frameSamples = (decoded.sampleRateHz * LIVE_VOICE_AUDIO_FRAME_DURATION_MS) / 1000;
    if (!Number.isSafeInteger(frameSamples)) {
      throw new GatewayBatchSpeechError('CAPABILITY_UNAVAILABLE', 'NON_INTEGRAL_AUDIO_FRAME', 'Provider sample rate cannot form exact AIO-B 20ms chunks');
    }
    const chunks: Readonly<BrowserAudioPcmChunk>[] = [];
    for (let offset = 0, seq = 0; offset < decoded.samples.length; offset += frameSamples, seq += 1) {
      chunks.push(
        Object.freeze({
          response: Object.freeze({ ...response }),
          unit_id: input.unitId,
          seq,
          sample_rate_hz: decoded.sampleRateHz,
          channel_count: 1,
          samples: decoded.samples.slice(offset, Math.min(offset + frameSamples, decoded.samples.length)),
          provider,
        })
      );
    }
    return Object.freeze({
      operation: 'speech.synthesize.batch',
      response: Object.freeze({ ...response }),
      unit_id: input.unitId,
      chunks: Object.freeze(chunks),
      provider,
      presented: false,
    });
  }

  async fenceRecognition(captureId: string): Promise<void> {
    const expectedCaptureId = requiredText(captureId, 'capture_id');
    const active = this.#activeRecognition;
    if (active === null || active.captureId !== expectedCaptureId) return;
    this.#activeRecognition = null;
    await this.#cancelBestEffort(active);
  }

  async fenceSynthesis(interactionId: string): Promise<void> {
    const active = this.#responses.get(requiredText(interactionId, 'interaction_id'));
    if (active === undefined) return;
    this.#responses.delete(interactionId);
    await this.#cancelBestEffort(active);
  }

  #beginOperation(operationId: string | undefined, correlationId: string): ActiveOperation {
    return Object.freeze({
      operationId: requiredText(operationId ?? this.#createId(), 'operation_id'),
      correlationId: requiredText(correlationId, 'correlation_id'),
      token: ++this.#token,
    });
  }

  #requireEnabled(): void {
    if (!this.#enabled) {
      throw new GatewayBatchSpeechError('CAPABILITY_UNAVAILABLE', 'FEATURE_DISABLED', 'formal Gateway batch speech is disabled');
    }
  }

  #boundedSet<K, V>(mapping: Map<K, V>, key: K, value: V): void {
    mapping.delete(key);
    mapping.set(key, value);
    while (mapping.size > MAX_IDENTITY_TOMBSTONES) {
      const oldest = mapping.keys().next().value as K | undefined;
      if (oldest === undefined) break;
      mapping.delete(oldest);
    }
  }

  async #cancelBestEffort(target: ActiveOperation): Promise<void> {
    try {
      await this.#transport!.request(
        SPEECH_CANCEL_METHOD,
        {
          contract_version: LIVE_VOICE_SPEECH_CONTRACT_VERSION,
          request_id: this.#createId(),
          operation_id: this.#createId(),
          operation: 'speech.batch.cancel',
          correlation_id: target.correlationId,
          session_id: this.#scope!.session_id,
          scope: this.#scope!,
          target_operation_id: target.operationId,
        },
        { timeoutMs: 2000 }
      );
    } catch {
      // The local token fence is authoritative for applying a late result. A
      // failed cancel RPC must never resurrect it or mutate another scope.
    }
  }
}
