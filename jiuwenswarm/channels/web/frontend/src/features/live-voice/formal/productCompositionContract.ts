export const PRODUCT_COMPOSITION_CONTRACT_VERSION = 'live-voice.product-composition.gate0.v1' as const;

export const PRODUCT_ROUTE_TRUTH = Object.freeze(['formal', 'fallback', 'demo_substitute', 'unavailable', 'disabled'] as const);
export type ProductRouteTruth = (typeof PRODUCT_ROUTE_TRUTH)[number];

export const PRODUCT_SEGMENTS = Object.freeze([
  'authority',
  'p1.speech_media',
  'p2.agent_interaction',
  'p3.query',
  'p3.control',
  'p3.progress',
  'browser.audio',
  'observability',
] as const);
export type ProductSegment = (typeof PRODUCT_SEGMENTS)[number];

export const PRODUCT_ROUTE_REASONS = Object.freeze([
  'FORMAL_ROUTE_OBSERVED',
  'EXPLICIT_FALLBACK_ACTIVE',
  'D047_DEMO_SUBSTITUTE_ACTIVE',
  'FEATURE_DISABLED',
  'ADAPTER_NOT_REGISTERED',
  'REQUESTED_ROUTE_UNAVAILABLE',
  'FORMAL_ACTIVATION_EVIDENCE_MISSING',
  'TRUSTED_AUTHORITY_UNAVAILABLE',
  'SPEECH_AUTHORIZATION_UNAVAILABLE',
  'MEDIA_AUTHORITY_UNAVAILABLE',
  'MEDIA_PROVIDER_UNAVAILABLE',
  'MEDIA_TRANSPORT_UNAVAILABLE',
  'MEDIA_LOGGER_ZERO_PERSISTENCE_UNPROVEN',
  'P2_AUTHORITY_UNAVAILABLE',
  'P2_RUNTIME_UNAVAILABLE',
  'P2_NOTIFICATION_BACKPRESSURE_UNRESOLVED',
  'P3_QUERY_AUTHORITY_UNAVAILABLE',
  'P3_CONFIRMATION_ISSUER_UNAVAILABLE',
  'TASK_PROGRESS_AUTHORITY_HANDOFF_UNAVAILABLE',
  'BROWSER_AUDIO_UNAVAILABLE',
  'OBSERVABILITY_CONSUMER_UNAVAILABLE',
  'ACTIVATION_FAILED',
] as const);
export type ProductRouteReason = (typeof PRODUCT_ROUTE_REASONS)[number];

export const PRODUCT_EVIDENCE_IDS = Object.freeze([
  'GATE0_CONTRACT_ONLY',
  'FEATURE_FLAG_OFF',
  'TRUSTED_AUTHORITY_RESOLVED',
  'FORMAL_ACTIVATION_LEASE_OPEN',
  'RUNTIME_PATH_OBSERVED',
  'P2_NOTIFICATION_BACKPRESSURE_CLOSED',
  'MEDIA_LOGGER_ZERO_PERSISTENCE_VERIFIED',
  'FALLBACK_ROUTE_SELECTED',
  'D047_LEGACY_ROUTE_SELECTED',
  'FORMAL_BATCH_SPEECH_FOUNDATION',
  'D059_AGENT_CR_FOUNDATION',
  'P3_QUERY_FOUNDATION',
  'TASK_EVENT_LIVE_ONLY',
  'PROGRESS_ARBITER_CONTIGUOUS_SEQUENCE_REQUIRED',
  'BROWSER_AUDIO_FOUNDATION',
  'OBSERVABILITY_FOUNDATION',
  'P2_NOTIFICATION_QUEUE_BLOCKING_RISK',
  'DEV_AUDIO_LOG_PERSISTENCE_RISK',
  'PREINTEGRATION_STATIC_AUDIT_ONLY',
  'PACKAGE_CONTRACT_ONLY',
  'NO_RUNTIME_EVIDENCE',
] as const);
export type ProductEvidenceId = (typeof PRODUCT_EVIDENCE_IDS)[number];

export type LegacyIntegratedRouteClass = 'formal' | 'fallback' | 'demo_substitute' | 'unsupported' | 'unknown';

export interface ProductRouteFact {
  readonly segment: ProductSegment;
  readonly truth: ProductRouteTruth;
  readonly reason_id: ProductRouteReason;
  readonly evidence_ids: readonly ProductEvidenceId[];
  readonly formal_runtime_observed: boolean;
}

export interface ProductCompositionManifest {
  readonly contract_version: typeof PRODUCT_COMPOSITION_CONTRACT_VERSION;
  readonly enabled: boolean;
  readonly routes: readonly ProductRouteFact[];
}

export class ProductCompositionContractViolation extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ProductCompositionContractViolation';
  }
}

const formalEvidence = new Set<ProductEvidenceId>(['TRUSTED_AUTHORITY_RESOLVED', 'FORMAL_ACTIVATION_LEASE_OPEN', 'RUNTIME_PATH_OBSERVED']);

const formalStopClosureBySegment: Readonly<Partial<Record<ProductSegment, ProductEvidenceId>>> = {
  'p1.speech_media': 'MEDIA_LOGGER_ZERO_PERSISTENCE_VERIFIED',
  'p2.agent_interaction': 'P2_NOTIFICATION_BACKPRESSURE_CLOSED',
};

const forbiddenEvidence: Readonly<Record<ProductRouteTruth, ReadonlySet<ProductEvidenceId>>> = {
  formal: new Set([
    'GATE0_CONTRACT_ONLY',
    'FEATURE_FLAG_OFF',
    'FALLBACK_ROUTE_SELECTED',
    'D047_LEGACY_ROUTE_SELECTED',
    'P2_NOTIFICATION_QUEUE_BLOCKING_RISK',
    'DEV_AUDIO_LOG_PERSISTENCE_RISK',
    'NO_RUNTIME_EVIDENCE',
  ]),
  fallback: new Set([...formalEvidence, 'FEATURE_FLAG_OFF', 'D047_LEGACY_ROUTE_SELECTED']),
  demo_substitute: new Set([...formalEvidence, 'FEATURE_FLAG_OFF', 'FALLBACK_ROUTE_SELECTED']),
  unavailable: new Set(['FEATURE_FLAG_OFF', 'FORMAL_ACTIVATION_LEASE_OPEN', 'RUNTIME_PATH_OBSERVED', 'FALLBACK_ROUTE_SELECTED', 'D047_LEGACY_ROUTE_SELECTED']),
  disabled: new Set(PRODUCT_EVIDENCE_IDS.filter(evidence => evidence !== 'FEATURE_FLAG_OFF')),
};

const allowedReasons: Readonly<Record<ProductRouteTruth, ReadonlySet<ProductRouteReason>>> = {
  formal: new Set(['FORMAL_ROUTE_OBSERVED']),
  fallback: new Set(['EXPLICIT_FALLBACK_ACTIVE']),
  demo_substitute: new Set(['D047_DEMO_SUBSTITUTE_ACTIVE']),
  disabled: new Set(['FEATURE_DISABLED']),
  unavailable: new Set(
    PRODUCT_ROUTE_REASONS.filter(
      reason =>
        reason !== 'FORMAL_ROUTE_OBSERVED' && reason !== 'EXPLICIT_FALLBACK_ACTIVE' && reason !== 'D047_DEMO_SUBSTITUTE_ACTIVE' && reason !== 'FEATURE_DISABLED'
    )
  ),
};

function freezeFact(input: ProductRouteFact): Readonly<ProductRouteFact> {
  if (!PRODUCT_SEGMENTS.includes(input.segment)) throw new ProductCompositionContractViolation('invalid product segment');
  if (!PRODUCT_ROUTE_TRUTH.includes(input.truth)) throw new ProductCompositionContractViolation('invalid product route truth');
  if (!allowedReasons[input.truth].has(input.reason_id)) {
    throw new ProductCompositionContractViolation('reason_id is incompatible with route truth');
  }
  if (!Array.isArray(input.evidence_ids) || input.evidence_ids.length === 0) {
    throw new ProductCompositionContractViolation('evidence_ids must be non-empty');
  }
  if (input.evidence_ids.some(evidence => !PRODUCT_EVIDENCE_IDS.includes(evidence))) {
    throw new ProductCompositionContractViolation('invalid product evidence id');
  }
  if (new Set(input.evidence_ids).size !== input.evidence_ids.length) {
    throw new ProductCompositionContractViolation('evidence_ids must not contain duplicates');
  }
  if (typeof input.formal_runtime_observed !== 'boolean') {
    throw new ProductCompositionContractViolation('formal_runtime_observed must be boolean');
  }
  const evidence = new Set(input.evidence_ids);
  if ([...forbiddenEvidence[input.truth]].some(id => evidence.has(id))) {
    throw new ProductCompositionContractViolation('route truth contains contradictory evidence');
  }
  if (input.truth === 'formal') {
    if (!input.formal_runtime_observed || [...formalEvidence].some(id => !evidence.has(id))) {
      throw new ProductCompositionContractViolation('formal truth requires trusted authority, an open activation lease, and observed runtime-path evidence');
    }
    const requiredStopClosure = formalStopClosureBySegment[input.segment];
    if (requiredStopClosure !== undefined && !evidence.has(requiredStopClosure)) {
      throw new ProductCompositionContractViolation('formal segment is missing its affirmative activation-stop closure evidence');
    }
  } else if (input.formal_runtime_observed) {
    throw new ProductCompositionContractViolation('non-formal truth cannot claim formal runtime observation');
  }
  const required: Partial<Record<ProductRouteTruth, ProductEvidenceId>> = {
    fallback: 'FALLBACK_ROUTE_SELECTED',
    demo_substitute: 'D047_LEGACY_ROUTE_SELECTED',
    disabled: 'FEATURE_FLAG_OFF',
  };
  if (required[input.truth] && !evidence.has(required[input.truth]!)) {
    throw new ProductCompositionContractViolation('route truth is missing its required evidence identifier');
  }
  return Object.freeze({ ...input, evidence_ids: Object.freeze([...input.evidence_ids]) });
}

function disabledFact(segment: ProductSegment): Readonly<ProductRouteFact> {
  return freezeFact({
    segment,
    truth: 'disabled',
    reason_id: 'FEATURE_DISABLED',
    evidence_ids: ['FEATURE_FLAG_OFF'],
    formal_runtime_observed: false,
  });
}

export function createProductCompositionManifest(input: {
  readonly enabled: boolean;
  readonly route_facts?: readonly ProductRouteFact[];
}): Readonly<ProductCompositionManifest> {
  if (typeof input.enabled !== 'boolean') throw new ProductCompositionContractViolation('enabled must be boolean');
  if (!input.enabled) {
    return Object.freeze({
      contract_version: PRODUCT_COMPOSITION_CONTRACT_VERSION,
      enabled: false,
      routes: Object.freeze(PRODUCT_SEGMENTS.map(disabledFact)),
    });
  }
  const routeFacts = input.route_facts ?? [];
  if (!Array.isArray(routeFacts)) {
    throw new ProductCompositionContractViolation('route_facts must be an array');
  }
  const facts = new Map<ProductSegment, Readonly<ProductRouteFact>>();
  for (const raw of routeFacts) {
    const fact = freezeFact(raw);
    if (facts.has(fact.segment)) throw new ProductCompositionContractViolation('duplicate product segment');
    facts.set(fact.segment, fact);
  }
  const routes = PRODUCT_SEGMENTS.map(
    segment =>
      facts.get(segment) ??
      freezeFact({
        segment,
        truth: 'unavailable',
        reason_id: 'ADAPTER_NOT_REGISTERED',
        evidence_ids: ['GATE0_CONTRACT_ONLY'],
        formal_runtime_observed: false,
      })
  );
  if (routes.slice(1).some(route => route.truth === 'formal') && routes[0].truth !== 'formal') {
    throw new ProductCompositionContractViolation('formal product segments require a formal authority segment');
  }
  return Object.freeze({
    contract_version: PRODUCT_COMPOSITION_CONTRACT_VERSION,
    enabled: true,
    routes: Object.freeze(routes),
  });
}

export function routeFactFromIntegratedShell(input: {
  readonly segment: ProductSegment;
  readonly feature_enabled: boolean;
  readonly legacy_route_class: unknown;
  readonly formal_runtime_observed?: boolean;
  readonly formal_evidence_ids?: readonly ProductEvidenceId[];
}): Readonly<ProductRouteFact> {
  if (typeof input.feature_enabled !== 'boolean') {
    throw new ProductCompositionContractViolation('feature_enabled must be boolean');
  }
  if (!input.feature_enabled) return disabledFact(input.segment);
  if (!PRODUCT_SEGMENTS.includes(input.segment)) throw new ProductCompositionContractViolation('invalid product segment');
  if (input.formal_runtime_observed !== undefined && typeof input.formal_runtime_observed !== 'boolean') {
    throw new ProductCompositionContractViolation('formal_runtime_observed must be boolean');
  }
  if (typeof input.legacy_route_class !== 'string') {
    throw new ProductCompositionContractViolation('legacy_route_class must be string');
  }
  if (input.legacy_route_class === 'fallback') {
    return freezeFact({
      segment: input.segment,
      truth: 'fallback',
      reason_id: 'EXPLICIT_FALLBACK_ACTIVE',
      evidence_ids: ['FALLBACK_ROUTE_SELECTED'],
      formal_runtime_observed: false,
    });
  }
  if (input.legacy_route_class === 'demo_substitute') {
    return freezeFact({
      segment: input.segment,
      truth: 'demo_substitute',
      reason_id: 'D047_DEMO_SUBSTITUTE_ACTIVE',
      evidence_ids: ['D047_LEGACY_ROUTE_SELECTED'],
      formal_runtime_observed: false,
    });
  }
  if (input.legacy_route_class === 'formal') {
    if (input.formal_runtime_observed !== true) {
      return freezeFact({
        segment: input.segment,
        truth: 'unavailable',
        reason_id: 'FORMAL_ACTIVATION_EVIDENCE_MISSING',
        evidence_ids: ['GATE0_CONTRACT_ONLY', 'NO_RUNTIME_EVIDENCE'],
        formal_runtime_observed: false,
      });
    }
    return freezeFact({
      segment: input.segment,
      truth: 'formal',
      reason_id: 'FORMAL_ROUTE_OBSERVED',
      evidence_ids: input.formal_evidence_ids ?? [],
      formal_runtime_observed: true,
    });
  }
  if (input.legacy_route_class === 'unsupported' || input.legacy_route_class === 'unknown') {
    return freezeFact({
      segment: input.segment,
      truth: 'unavailable',
      reason_id: 'REQUESTED_ROUTE_UNAVAILABLE',
      evidence_ids: ['GATE0_CONTRACT_ONLY', 'NO_RUNTIME_EVIDENCE'],
      formal_runtime_observed: false,
    });
  }
  throw new ProductCompositionContractViolation('unknown legacy route class');
}
