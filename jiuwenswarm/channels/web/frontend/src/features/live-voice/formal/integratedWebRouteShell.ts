import { CONTRACT_VERSION, createRouteTelemetryRecord, type RouteImplementationClass, type RouteTelemetryRecord } from './liveVoiceRouteTelemetry.js';

export const INTEGRATED_WEB_SEGMENTS = Object.freeze(['p1.speech_io', 'p2.realtime_conversation', 'p3alpha.task_control'] as const);
export type IntegratedWebSegmentId = (typeof INTEGRATED_WEB_SEGMENTS)[number];

export type IntegratedWebRequestedClass = Exclude<RouteImplementationClass, 'unknown'>;
export type IntegratedWebCompositionState = 'flag_off' | 'shell_only' | 'formal_seams' | 'degraded' | 'unsupported';
export type IntegratedWebWiringState = 'activation_seam' | 'manifest_only' | 'unavailable';

export interface IntegratedWebRouteContext {
  readonly session_id: string | null;
  readonly correlation_id: string;
  readonly observed_at: string;
}

export interface IntegratedWebRouteLease {
  close(): void | Promise<void>;
}

export interface IntegratedWebRouteAdapter {
  readonly segment_id: IntegratedWebSegmentId;
  readonly adapter_id: string;
  readonly implementation_class: Exclude<RouteImplementationClass, 'unsupported' | 'unknown'>;
  readonly owner_module: string;
  readonly capability_provider: string | null;
  readonly contract_version: string | null;
  readonly safe_reason: string | null;
  readonly available: boolean;
  readonly unavailable_reason: string | null;
  readonly capabilities: readonly string[];
  readonly activate?: (context: Readonly<IntegratedWebRouteActivationContext>) => IntegratedWebRouteLease | Promise<IntegratedWebRouteLease>;
}

export interface IntegratedWebRouteActivationContext extends IntegratedWebRouteContext {
  readonly route: Readonly<IntegratedWebSegmentRoute>;
  readonly signal: AbortSignal;
}

export interface IntegratedWebSegmentRoute extends RouteTelemetryRecord {
  readonly segment_id: IntegratedWebSegmentId;
  readonly requested_class: IntegratedWebRequestedClass;
  readonly adapter_id: string | null;
  readonly wiring_state: IntegratedWebWiringState;
  readonly capabilities: readonly string[];
}

export type IntegratedWebRoutePolicy = Readonly<Record<IntegratedWebSegmentId, IntegratedWebRequestedClass>>;

export interface IntegratedWebRouteManifest {
  readonly enabled: boolean;
  readonly session_id: string | null;
  readonly correlation_id: string;
  readonly observed_at: string;
  readonly composition_state: IntegratedWebCompositionState;
  readonly segments: readonly Readonly<IntegratedWebSegmentRoute>[];
  readonly activation_leases_active: boolean;
  readonly teardown_state: 'idle' | 'pending' | 'cleanup_required';
  readonly gate_claim: 'NONE';
}

export class IntegratedWebRouteViolation extends Error {
  constructor(
    readonly reason: string,
    message: string
  ) {
    super(message);
    this.name = 'IntegratedWebRouteViolation';
  }
}

function requiredText(value: string, field: string): string {
  if (typeof value !== 'string' || value.trim().length === 0) {
    throw new IntegratedWebRouteViolation('INVALID_REQUIRED_TEXT', `${field} must be non-empty`);
  }
  return value;
}

function adapterKey(segmentId: IntegratedWebSegmentId, implementationClass: IntegratedWebRequestedClass): string {
  return `${segmentId}\u0000${implementationClass}`;
}

function isSegmentId(value: string): value is IntegratedWebSegmentId {
  return INTEGRATED_WEB_SEGMENTS.includes(value as IntegratedWebSegmentId);
}

function normalizeAdapter(adapter: Readonly<IntegratedWebRouteAdapter>): Readonly<IntegratedWebRouteAdapter> {
  if (!isSegmentId(adapter.segment_id)) {
    throw new IntegratedWebRouteViolation('INVALID_SEGMENT', 'adapter segment is not part of the cumulative Web route');
  }
  const adapterId = requiredText(adapter.adapter_id, 'adapter_id');
  const ownerModule = requiredText(adapter.owner_module, 'owner_module');
  if (!['formal', 'fallback', 'demo_substitute'].includes(adapter.implementation_class)) {
    throw new IntegratedWebRouteViolation('INVALID_ADAPTER_CLASS', 'an injectable adapter must be formal, fallback, or demo_substitute');
  }
  if (typeof adapter.available !== 'boolean') {
    throw new IntegratedWebRouteViolation('INVALID_AVAILABLE', 'adapter available must be boolean');
  }
  if (!adapter.available && (typeof adapter.unavailable_reason !== 'string' || adapter.unavailable_reason.trim().length === 0)) {
    throw new IntegratedWebRouteViolation('UNAVAILABLE_REASON_REQUIRED', 'an unavailable adapter requires an explicit reason');
  }
  const capabilities = adapter.capabilities.map((capability, index) => requiredText(capability, `capabilities[${index}]`));
  if (new Set(capabilities).size !== capabilities.length) {
    throw new IntegratedWebRouteViolation('DUPLICATE_CAPABILITY', 'adapter capabilities must be unique');
  }

  const registrationRecord = createRouteTelemetryRecord({
    segment_id: adapter.segment_id,
    implementation_class: adapter.implementation_class,
    owner_module: ownerModule,
    capability_provider: adapter.capability_provider,
    contract_version: adapter.contract_version,
    correlation_id: 'adapter-registration',
    observed_at: '2026-08-05T00:00:00Z',
    safe_reason: adapter.safe_reason,
  });
  if (registrationRecord.implementation_class !== adapter.implementation_class) {
    throw new IntegratedWebRouteViolation('INCOMPLETE_ADAPTER_PROVENANCE', 'adapter provenance cannot support its declared implementation class');
  }

  return Object.freeze({
    ...adapter,
    adapter_id: adapterId,
    owner_module: ownerModule,
    unavailable_reason: adapter.available ? null : adapter.unavailable_reason,
    capabilities: Object.freeze(capabilities),
  });
}

export class IntegratedWebAdapterRegistry {
  readonly #adapters = new Map<string, Readonly<IntegratedWebRouteAdapter>>();

  register(adapter: Readonly<IntegratedWebRouteAdapter>): this {
    const normalized = normalizeAdapter(adapter);
    const key = adapterKey(normalized.segment_id, normalized.implementation_class);
    if (this.#adapters.has(key)) {
      throw new IntegratedWebRouteViolation('AMBIGUOUS_ROUTE_BINDING', `${normalized.segment_id} already has a ${normalized.implementation_class} adapter`);
    }
    this.#adapters.set(key, normalized);
    return this;
  }

  find(segmentId: IntegratedWebSegmentId, implementationClass: IntegratedWebRequestedClass): Readonly<IntegratedWebRouteAdapter> | null {
    return this.#adapters.get(adapterKey(segmentId, implementationClass)) ?? null;
  }

  list(): readonly Readonly<IntegratedWebRouteAdapter>[] {
    return Object.freeze([...this.#adapters.values()]);
  }
}

function unsupportedRoute(
  context: Readonly<IntegratedWebRouteContext>,
  segmentId: IntegratedWebSegmentId,
  requestedClass: IntegratedWebRequestedClass,
  reason: string,
  adapter: Readonly<IntegratedWebRouteAdapter> | null = null
): Readonly<IntegratedWebSegmentRoute> {
  const telemetry = createRouteTelemetryRecord({
    segment_id: segmentId,
    implementation_class: 'unsupported',
    owner_module: adapter?.owner_module ?? 'X-E2E/X-WEB.route-shell',
    capability_provider: null,
    contract_version: adapter === null ? CONTRACT_VERSION : adapter.contract_version,
    correlation_id: context.correlation_id,
    observed_at: context.observed_at,
    safe_reason: reason,
  });
  return Object.freeze({
    ...telemetry,
    segment_id: segmentId,
    requested_class: requestedClass,
    adapter_id: adapter?.adapter_id ?? null,
    wiring_state: 'unavailable',
    capabilities: Object.freeze([]),
  });
}

function selectedRoute(
  context: Readonly<IntegratedWebRouteContext>,
  requestedClass: IntegratedWebRequestedClass,
  adapter: Readonly<IntegratedWebRouteAdapter>
): Readonly<IntegratedWebSegmentRoute> {
  const telemetry = createRouteTelemetryRecord({
    segment_id: adapter.segment_id,
    implementation_class: adapter.implementation_class,
    owner_module: adapter.owner_module,
    capability_provider: adapter.capability_provider,
    contract_version: adapter.contract_version,
    correlation_id: context.correlation_id,
    observed_at: context.observed_at,
    safe_reason: adapter.safe_reason,
  });
  return Object.freeze({
    ...telemetry,
    segment_id: adapter.segment_id,
    requested_class: requestedClass,
    adapter_id: adapter.adapter_id,
    wiring_state: adapter.activate === undefined ? 'manifest_only' : 'activation_seam',
    capabilities: Object.freeze([...adapter.capabilities]),
  });
}

function compositionState(enabled: boolean, segments: readonly Readonly<IntegratedWebSegmentRoute>[]): IntegratedWebCompositionState {
  if (!enabled) return 'flag_off';
  if (segments.some(segment => segment.implementation_class === 'unsupported' || segment.implementation_class === 'unknown')) return 'unsupported';
  if (segments.some(segment => segment.wiring_state !== 'activation_seam')) return 'shell_only';
  if (segments.every(segment => segment.implementation_class === 'formal')) return 'formal_seams';
  return 'degraded';
}

export class IntegratedWebRouteShell {
  readonly #enabled: boolean;
  readonly #registry: IntegratedWebAdapterRegistry;
  readonly #policy: IntegratedWebRoutePolicy;
  readonly #context: Readonly<IntegratedWebRouteContext>;

  constructor(
    options: Readonly<{
      enabled: boolean;
      registry: IntegratedWebAdapterRegistry;
      policy: IntegratedWebRoutePolicy;
      context: IntegratedWebRouteContext;
    }>
  ) {
    if (typeof options.enabled !== 'boolean') {
      throw new IntegratedWebRouteViolation('INVALID_ENABLED', 'enabled must be boolean');
    }
    requiredText(options.context.correlation_id, 'correlation_id');
    createRouteTelemetryRecord({
      segment_id: 'integrated.web.context',
      implementation_class: 'unsupported',
      owner_module: 'X-E2E/X-WEB.route-shell',
      correlation_id: options.context.correlation_id,
      observed_at: options.context.observed_at,
      safe_reason: 'CONTEXT_VALIDATION_ONLY',
    });
    for (const segmentId of INTEGRATED_WEB_SEGMENTS) {
      if (!(segmentId in options.policy)) {
        throw new IntegratedWebRouteViolation('INCOMPLETE_ROUTE_POLICY', `route policy is missing ${segmentId}`);
      }
    }
    this.#enabled = options.enabled;
    if (options.context.session_id !== null && typeof options.context.session_id !== 'string') {
      throw new IntegratedWebRouteViolation('INVALID_SESSION_ID', 'session_id must be a string or null');
    }
    this.#registry = options.registry;
    const requestedClasses: readonly IntegratedWebRequestedClass[] = ['formal', 'fallback', 'demo_substitute', 'unsupported'];
    for (const segmentId of INTEGRATED_WEB_SEGMENTS) {
      if (!requestedClasses.includes(options.policy[segmentId])) {
        throw new IntegratedWebRouteViolation('INVALID_REQUESTED_CLASS', `route policy for ${segmentId} is invalid`);
      }
    }
    this.#policy = Object.freeze({ ...options.policy });
    this.#context = Object.freeze({ ...options.context });
  }

  preview(): Readonly<IntegratedWebRouteManifest> {
    const segments = INTEGRATED_WEB_SEGMENTS.map(segmentId => this.#select(segmentId));
    return Object.freeze({
      enabled: this.#enabled,
      session_id: this.#context.session_id,
      correlation_id: this.#context.correlation_id,
      observed_at: this.#context.observed_at,
      composition_state: compositionState(this.#enabled, segments),
      segments: Object.freeze(segments),
      activation_leases_active: false,
      teardown_state: 'idle',
      gate_claim: 'NONE' as const,
    });
  }

  #select(segmentId: IntegratedWebSegmentId): Readonly<IntegratedWebSegmentRoute> {
    const requestedClass = this.#policy[segmentId];
    if (!this.#enabled) return unsupportedRoute(this.#context, segmentId, requestedClass, 'FEATURE_DISABLED');
    if (this.#context.session_id === null || this.#context.session_id.trim().length === 0) {
      return unsupportedRoute(this.#context, segmentId, requestedClass, 'PERSISTED_SESSION_REQUIRED');
    }
    if (requestedClass === 'unsupported') return unsupportedRoute(this.#context, segmentId, requestedClass, 'CAPABILITY_NOT_REQUESTED');
    const adapter = this.#registry.find(segmentId, requestedClass);
    if (adapter === null) return unsupportedRoute(this.#context, segmentId, requestedClass, 'REQUESTED_ROUTE_CLASS_UNAVAILABLE');
    if (!adapter.available) {
      return unsupportedRoute(this.#context, segmentId, requestedClass, adapter.unavailable_reason ?? 'ADAPTER_UNAVAILABLE', adapter);
    }
    return selectedRoute(this.#context, requestedClass, adapter);
  }
}

export interface CurrentIntegratedWebRouteFacts {
  readonly p1_browser_speech_available: boolean;
  readonly p2_text_chat_available: boolean;
  readonly p1_formal_enabled?: boolean;
  readonly p1_formal_available?: boolean;
  readonly p2_formal_enabled?: boolean;
  readonly p2_formal_available?: boolean;
  readonly p3_formal_enabled?: boolean;
  readonly p3_formal_available?: boolean;
}

export interface IntegratedWebRouteSelection {
  readonly registry: IntegratedWebAdapterRegistry;
  readonly policy: IntegratedWebRoutePolicy;
}

export function createCurrentIntegratedWebRouteSelection(facts: Readonly<CurrentIntegratedWebRouteFacts>): Readonly<IntegratedWebRouteSelection> {
  for (const [field, value] of Object.entries(facts)) {
    if (value !== undefined && typeof value !== 'boolean') {
      throw new IntegratedWebRouteViolation('INVALID_CURRENT_ROUTE_FACT', `${field} must be boolean`);
    }
  }
  const p1FormalEnabled = facts.p1_formal_enabled === true;
  const p2FormalEnabled = facts.p2_formal_enabled === true;
  const p3FormalEnabled = facts.p3_formal_enabled === true;
  const registry = new IntegratedWebAdapterRegistry()
    .register({
      segment_id: 'p1.speech_io',
      adapter_id: 'compat.browser-speech',
      implementation_class: 'fallback',
      owner_module: 'P1.BrowserSpeechCompatibility',
      capability_provider: facts.p1_browser_speech_available ? 'browser-speech' : null,
      contract_version: null,
      safe_reason: 'BROWSER_SPEECH_COMPATIBILITY_FALLBACK',
      available: facts.p1_browser_speech_available,
      unavailable_reason: facts.p1_browser_speech_available ? null : 'BROWSER_SPEECH_UNAVAILABLE',
      capabilities: ['committed_browser_recognition', 'browser_speech_synthesis'],
    })
    .register({
      segment_id: 'p2.realtime_conversation',
      adapter_id: 'compat.text-chat-e2a',
      implementation_class: 'fallback',
      owner_module: 'P2.TextChatE2ACompatibility',
      capability_provider: facts.p2_text_chat_available ? 'existing-chat-e2a' : null,
      contract_version: null,
      safe_reason: 'EXPLICIT_TEXT_CHAT_FALLBACK',
      available: facts.p2_text_chat_available,
      unavailable_reason: facts.p2_text_chat_available ? null : 'TEXT_CHAT_ROUTE_UNAVAILABLE',
      capabilities: ['committed_text_dispatch', 'truthful_text_response'],
    });

  if (p1FormalEnabled) {
    registry.register({
      segment_id: 'p1.speech_io',
      adapter_id: 'formal.product-batch-speech-media',
      implementation_class: 'formal',
      owner_module: 'P1.ProductDedicatedMediaBatchSpeech',
      capability_provider: 'gateway-batch-speech',
      contract_version: CONTRACT_VERSION,
      safe_reason: null,
      available: facts.p1_formal_available === true,
      unavailable_reason: facts.p1_formal_available === true ? null : 'FORMAL_P1_NOT_ACTIVE',
      capabilities: ['browser_audio_io', 'dedicated_binary_media', 'batch_stt', 'batch_tts'],
    });
  }
  if (p2FormalEnabled) {
    registry.register({
      segment_id: 'p2.realtime_conversation',
      adapter_id: 'formal.product-p2-runtime',
      implementation_class: 'formal',
      owner_module: 'P2.ProductConversationRuntime',
      capability_provider: 'jiuwenswarm-agent-runtime',
      contract_version: CONTRACT_VERSION,
      safe_reason: null,
      available: facts.p2_formal_available === true,
      unavailable_reason: facts.p2_formal_available === true ? null : 'FORMAL_P2_NOT_ACTIVE',
      capabilities: ['committed_turn', 'nonblocking_notification_poll', 'presented_history'],
    });
  }
  if (p3FormalEnabled) {
    registry.register({
      segment_id: 'p3alpha.task_control',
      adapter_id: 'formal.product-p3-task-control',
      implementation_class: 'formal',
      owner_module: 'P3alpha.FormalTaskControl',
      capability_provider: 'formal-task-core-direct-d0',
      contract_version: CONTRACT_VERSION,
      safe_reason: null,
      available: facts.p3_formal_available === true,
      unavailable_reason: facts.p3_formal_available === true ? null : 'FORMAL_P3_NOT_ACTIVE',
      capabilities: ['confirmed_task_mutation', 'direct_d0_executor', 'task_event_progress'],
    });
  }

  return Object.freeze({
    registry,
    policy: Object.freeze({
      'p1.speech_io': p1FormalEnabled ? 'formal' : 'fallback',
      'p2.realtime_conversation': p2FormalEnabled ? 'formal' : 'fallback',
      'p3alpha.task_control': p3FormalEnabled
        ? 'formal'
        : 'unsupported',
    }),
  });
}
