/**
 * Fail-closed recorder for bounded Web Alpha lifecycle observations.
 *
 * This module preserves controlled-browser and deterministic-conformance facts.
 * It does not drive product lifecycle, reconnect media, or award Alpha Gate credit.
 */

export const WEB_LIFECYCLE_OBSERVATION_SCOPE = 'web_lifecycle_observation_only' as const;
export const WEB_LIFECYCLE_OBSERVATION_SCHEMA_VERSION = 1 as const;
export const WEB_LIFECYCLE_SCENARIOS = Object.freeze([
  'microphone_permission_grant',
  'microphone_permission_denial',
  'microphone_permission_revocation',
  'device_change',
  'input_loss',
  'output_loss',
  'autoplay_user_activation',
  'hidden_background_resume',
  'refresh_reconnect',
  'visible_diagnostics',
  'network_transport_close',
] as const);

export type WebLifecycleScenario = (typeof WEB_LIFECYCLE_SCENARIOS)[number];
export type WebLifecycleObservationSource = 'automated_conformance' | 'controlled_real_chrome';
export type WebLifecycleBrowserFamily = 'simulated_google_chrome_contract' | 'google_chrome';
export type WebLifecycleOperatingSystem = 'windows' | 'macos' | 'linux';

export const WEB_LIFECYCLE_EXPECTED_TERMINAL_REASON: Readonly<Record<WebLifecycleScenario, string>> = Object.freeze({
  microphone_permission_grant: 'MICROPHONE_PERMISSION_GRANTED',
  microphone_permission_denial: 'MICROPHONE_PERMISSION_DENIED',
  microphone_permission_revocation: 'MICROPHONE_PERMISSION_REVOKED_CAPTURE_FENCED',
  device_change: 'DEVICE_CHANGE_DIAGNOSTIC_ONLY',
  input_loss: 'AUDIO_INPUT_LOST_CAPTURE_FENCED',
  output_loss: 'AUDIO_OUTPUT_CONTEXT_LOST',
  autoplay_user_activation: 'AUTOPLAY_USER_ACTIVATION_OBSERVED',
  hidden_background_resume: 'PAGE_HIDDEN_CAPTURE_FENCED_EXPLICIT_RESUME_REQUIRED',
  refresh_reconnect: 'REFRESH_OBSERVED_RECONNECT_UNPROVEN',
  visible_diagnostics: 'VISIBLE_DIAGNOSTICS_OBSERVED',
  network_transport_close: 'MEDIA_TRANSPORT_CLOSED_NO_RETRY',
});

export interface WebLifecycleObservationContext {
  readonly context_binding_id: string;
  readonly candidate_sha: string;
  readonly run_id: string;
  readonly observation_source: WebLifecycleObservationSource;
  readonly browser_family: WebLifecycleBrowserFamily;
  readonly browser_version: string;
  readonly os_family: WebLifecycleOperatingSystem;
  readonly os_version_ref: string;
  readonly origin: string;
  readonly input_device_ref: string;
  readonly output_device_ref: string;
  readonly input_selection: 'default' | 'explicit';
  readonly output_selection: 'system_default' | 'explicit';
  readonly network_profile_ref: string;
  readonly initial_page_epoch_id: string;
}

export interface WebLifecycleTerminalObservation {
  readonly context_binding_id: string;
  readonly candidate_sha: string;
  readonly run_id: string;
  readonly observation_source: WebLifecycleObservationSource;
  readonly scenario_id: WebLifecycleScenario;
  readonly sequence: number;
  readonly page_epoch_id: string;
  readonly successor_page_epoch_id: string | null;
  readonly result: 'expected_boundary_observed' | 'unexpected_boundary_observed';
  readonly reason_id: string;
  readonly observed_at_monotonic_ms: number;
  readonly stale_effect_count: 0;
  readonly business_cancel_count_delta: 0;
  readonly automatic_retry_count: 0;
  readonly raw_audio_persisted: false;
  readonly credential_material_observed: false;
}

export interface WebLifecycleObservationCheckpoint {
  readonly schema_version: typeof WEB_LIFECYCLE_OBSERVATION_SCHEMA_VERSION;
  readonly evidence_scope: typeof WEB_LIFECYCLE_OBSERVATION_SCOPE;
  readonly source_is_declared_provenance: true;
  /** The recorder checks internal equality only; an external verifier remains required. */
  readonly binding_verified: false;
  /** Declared provenance and terminal facts are not independently verified by this recorder. */
  readonly evidence_verified: false;
  readonly context: Readonly<WebLifecycleObservationContext>;
  readonly observations: readonly Readonly<WebLifecycleTerminalObservation>[];
}

export interface WebLifecycleObservationSnapshot extends WebLifecycleObservationCheckpoint {
  readonly current_page_epoch_id: string;
  readonly next_sequence: number;
  readonly missing_scenarios: readonly WebLifecycleScenario[];
  /** Ledger completeness only; it does not say that the observed boundaries were expected. */
  readonly all_scenarios_observed: boolean;
  readonly expected_boundary_observation_count: number;
  readonly unexpected_boundary_observation_count: number;
  readonly all_expected_boundaries: boolean;
  readonly automated_observation_count: number;
  readonly controlled_real_observation_count: number;
  readonly refresh_reconnect_authority: 'unproven';
  readonly alpha_gate_pass: false;
}

const SCENARIOS = new Set<string>(WEB_LIFECYCLE_SCENARIOS);
const CANDIDATE_SHA = /^(?:[0-9a-f]{40}|[0-9a-f]{64})$/;
const DEVICE_REF = /^(?:device_ref:[0-9a-f]{12,64}|system_default)$/;
const NETWORK_REF = /^network_ref:[0-9a-f]{12,64}$/;
const CONTEXT_REF = /^context_ref:[0-9a-f]{12,64}$/;
const RUN_REF = /^run_ref:[0-9a-f]{12,64}$/;
const PAGE_REF = /^page_ref:[0-9a-f]{12,64}$/;
const OS_VERSION_REF = /^os-version:[0-9a-f]{64}$/;

function canonicalChromeVersion(value: unknown): string {
  if (typeof value !== 'string' || value.length > 40) {
    throw new TypeError('browser_version must be an exact four-part Chrome version');
  }
  const parts = value.split('.');
  if (parts.length !== 4 || parts.some(part => !/^[0-9]+$/.test(part) || String(Number(part)) !== part || !Number.isSafeInteger(Number(part)))) {
    throw new TypeError('browser_version must be an exact four-part Chrome version');
  }
  return value;
}

function canonicalReference(value: unknown, field: string, pattern: RegExp): string {
  if (typeof value !== 'string' || value.length > 80 || !pattern.test(value)) {
    throw new TypeError(`${field} must be a canonical sanitized reference`);
  }
  return value;
}

function exactOrigin(value: unknown): string {
  if (typeof value !== 'string' || value.length === 0 || value.length > 512 || value !== value.trim()) {
    throw new TypeError('origin must be an exact HTTP(S) origin');
  }
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    throw new TypeError('origin must be an exact HTTP(S) origin');
  }
  if (
    !['http:', 'https:'].includes(parsed.protocol) ||
    parsed.username !== '' ||
    parsed.password !== '' ||
    parsed.pathname !== '/' ||
    parsed.search !== '' ||
    parsed.hash !== '' ||
    parsed.origin !== value
  ) {
    throw new TypeError('origin must be an exact HTTP(S) origin');
  }
  return value;
}

function isLocalhostOrigin(value: string): boolean {
  const hostname = new URL(value).hostname.replace(/^\[|\]$/g, '').toLowerCase();
  return hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '::1';
}

function candidateSha(value: unknown): string {
  if (typeof value !== 'string' || !CANDIDATE_SHA.test(value)) {
    throw new TypeError('candidate_sha must be an exact lowercase Git SHA');
  }
  return value;
}

function safeInteger(value: unknown, field: string): number {
  if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < 0) {
    throw new TypeError(`${field} must be a nonnegative safe integer`);
  }
  return value;
}

function normalizeContext(value: Readonly<WebLifecycleObservationContext>): Readonly<WebLifecycleObservationContext> {
  const observationSource = value.observation_source;
  if (observationSource !== 'automated_conformance' && observationSource !== 'controlled_real_chrome') {
    throw new TypeError('observation_source is not supported');
  }
  const browserFamily = value.browser_family;
  if (observationSource === 'controlled_real_chrome' && browserFamily !== 'google_chrome') {
    throw new TypeError('controlled_real_chrome requires an exact Google Chrome browser binding');
  }
  if (observationSource === 'automated_conformance' && browserFamily !== 'simulated_google_chrome_contract') {
    throw new TypeError('automated_conformance requires a simulated browser contract binding');
  }
  if (!['windows', 'macos', 'linux'].includes(value.os_family)) {
    throw new TypeError('os_family is not supported');
  }
  if (!['default', 'explicit'].includes(value.input_selection)) {
    throw new TypeError('input_selection is not supported');
  }
  if (!['system_default', 'explicit'].includes(value.output_selection)) {
    throw new TypeError('output_selection is not supported');
  }
  const inputDeviceRef = canonicalReference(value.input_device_ref, 'input_device_ref', DEVICE_REF);
  const outputDeviceRef = canonicalReference(value.output_device_ref, 'output_device_ref', DEVICE_REF);
  const origin = exactOrigin(value.origin);
  const browserVersion = canonicalChromeVersion(value.browser_version);
  if ((value.input_selection === 'explicit') !== inputDeviceRef.startsWith('device_ref:')) {
    throw new TypeError('input_selection and input_device_ref are inconsistent');
  }
  if ((value.output_selection === 'explicit') !== outputDeviceRef.startsWith('device_ref:')) {
    throw new TypeError('output_selection and output_device_ref are inconsistent');
  }
  if (observationSource === 'controlled_real_chrome' && origin.startsWith('http:') && !isLocalhostOrigin(origin)) {
    throw new TypeError('controlled_real_chrome requires HTTPS or a localhost controlled origin');
  }
  if (observationSource === 'controlled_real_chrome' && Number.parseInt(browserVersion, 10) < 107) {
    throw new TypeError('controlled_real_chrome requires Google Chrome 107 or later');
  }
  return Object.freeze({
    context_binding_id: canonicalReference(value.context_binding_id, 'context_binding_id', CONTEXT_REF),
    candidate_sha: candidateSha(value.candidate_sha),
    run_id: canonicalReference(value.run_id, 'run_id', RUN_REF),
    observation_source: observationSource,
    browser_family: browserFamily,
    browser_version: browserVersion,
    os_family: value.os_family,
    os_version_ref: canonicalReference(value.os_version_ref, 'os_version_ref', OS_VERSION_REF),
    origin,
    input_device_ref: inputDeviceRef,
    output_device_ref: outputDeviceRef,
    input_selection: value.input_selection,
    output_selection: value.output_selection,
    network_profile_ref: canonicalReference(value.network_profile_ref, 'network_profile_ref', NETWORK_REF),
    initial_page_epoch_id: canonicalReference(value.initial_page_epoch_id, 'initial_page_epoch_id', PAGE_REF),
  });
}

export class WebLifecycleObservationRecorder {
  readonly #context: Readonly<WebLifecycleObservationContext>;
  readonly #observations: Readonly<WebLifecycleTerminalObservation>[] = [];
  readonly #observedScenarios = new Set<WebLifecycleScenario>();
  readonly #lastObservedAtByEpoch = new Map<string, number>();
  #currentPageEpochId: string;

  constructor(context: Readonly<WebLifecycleObservationContext>) {
    this.#context = normalizeContext(context);
    this.#currentPageEpochId = this.#context.initial_page_epoch_id;
  }

  static fromCheckpoint(checkpoint: Readonly<WebLifecycleObservationCheckpoint>): WebLifecycleObservationRecorder {
    if (
      checkpoint.schema_version !== WEB_LIFECYCLE_OBSERVATION_SCHEMA_VERSION ||
      checkpoint.evidence_scope !== WEB_LIFECYCLE_OBSERVATION_SCOPE ||
      checkpoint.source_is_declared_provenance !== true ||
      checkpoint.binding_verified !== false ||
      checkpoint.evidence_verified !== false ||
      !Array.isArray(checkpoint.observations)
    ) {
      throw new TypeError('lifecycle observation checkpoint is not supported');
    }
    const recorder = new WebLifecycleObservationRecorder(checkpoint.context);
    for (const observation of checkpoint.observations) recorder.recordTerminal(observation);
    return recorder;
  }

  recordTerminal(value: Readonly<WebLifecycleTerminalObservation>): Readonly<WebLifecycleTerminalObservation> {
    this.#requireContextBinding(value);
    if (!SCENARIOS.has(value.scenario_id)) throw new TypeError('scenario_id is not supported');
    const scenario = value.scenario_id as WebLifecycleScenario;
    if (this.#observedScenarios.has(scenario)) throw new Error('lifecycle scenario is already terminal');
    const sequence = safeInteger(value.sequence, 'sequence');
    if (sequence !== this.#observations.length) throw new Error('lifecycle observation sequence is not contiguous');
    const pageEpochId = canonicalReference(value.page_epoch_id, 'page_epoch_id', PAGE_REF);
    if (pageEpochId !== this.#currentPageEpochId) throw new Error('lifecycle observation belongs to a stale or foreign page epoch');
    if (value.result !== 'expected_boundary_observed' && value.result !== 'unexpected_boundary_observed') {
      throw new TypeError('result is not supported');
    }
    const expectedReason = WEB_LIFECYCLE_EXPECTED_TERMINAL_REASON[scenario];
    const acceptedReason = value.result === 'expected_boundary_observed' ? expectedReason : 'UNEXPECTED_LIFECYCLE_BOUNDARY';
    if (value.reason_id !== acceptedReason) throw new TypeError('reason_id does not match the closed scenario terminal diagnostic');
    const observedAt = safeInteger(value.observed_at_monotonic_ms, 'observed_at_monotonic_ms');
    const previousObservedAt = this.#lastObservedAtByEpoch.get(pageEpochId);
    if (previousObservedAt !== undefined && observedAt < previousObservedAt) {
      throw new Error('lifecycle observation monotonic time regressed');
    }
    this.#requireTerminalFacts(value);

    let successorPageEpochId: string | null = null;
    if (scenario === 'refresh_reconnect') {
      successorPageEpochId = canonicalReference(value.successor_page_epoch_id, 'successor_page_epoch_id', PAGE_REF);
      if (successorPageEpochId === pageEpochId) throw new Error('refresh successor page epoch must be distinct');
    } else if (value.successor_page_epoch_id !== null) {
      throw new Error('only refresh_reconnect may advance the page epoch');
    }

    const observation = Object.freeze({
      context_binding_id: this.#context.context_binding_id,
      candidate_sha: this.#context.candidate_sha,
      run_id: this.#context.run_id,
      observation_source: this.#context.observation_source,
      scenario_id: scenario,
      sequence,
      page_epoch_id: pageEpochId,
      successor_page_epoch_id: successorPageEpochId,
      result: value.result,
      reason_id: value.reason_id,
      observed_at_monotonic_ms: observedAt,
      stale_effect_count: 0 as const,
      business_cancel_count_delta: 0 as const,
      automatic_retry_count: 0 as const,
      raw_audio_persisted: false as const,
      credential_material_observed: false as const,
    });
    this.#observations.push(observation);
    this.#observedScenarios.add(scenario);
    this.#lastObservedAtByEpoch.set(pageEpochId, observedAt);
    if (successorPageEpochId !== null) this.#currentPageEpochId = successorPageEpochId;
    return observation;
  }

  checkpoint(): Readonly<WebLifecycleObservationCheckpoint> {
    return Object.freeze({
      schema_version: WEB_LIFECYCLE_OBSERVATION_SCHEMA_VERSION,
      evidence_scope: WEB_LIFECYCLE_OBSERVATION_SCOPE,
      source_is_declared_provenance: true,
      binding_verified: false,
      evidence_verified: false,
      context: this.#context,
      observations: Object.freeze([...this.#observations]),
    });
  }

  snapshot(): Readonly<WebLifecycleObservationSnapshot> {
    const checkpoint = this.checkpoint();
    const missingScenarios = Object.freeze(WEB_LIFECYCLE_SCENARIOS.filter(scenario => !this.#observedScenarios.has(scenario)));
    const automated = this.#context.observation_source === 'automated_conformance' ? this.#observations.length : 0;
    const controlledReal = this.#context.observation_source === 'controlled_real_chrome' ? this.#observations.length : 0;
    const expectedCount = this.#observations.filter(observation => observation.result === 'expected_boundary_observed').length;
    const unexpectedCount = this.#observations.length - expectedCount;
    return Object.freeze({
      ...checkpoint,
      current_page_epoch_id: this.#currentPageEpochId,
      next_sequence: this.#observations.length,
      missing_scenarios: missingScenarios,
      all_scenarios_observed: missingScenarios.length === 0,
      expected_boundary_observation_count: expectedCount,
      unexpected_boundary_observation_count: unexpectedCount,
      all_expected_boundaries: missingScenarios.length === 0 && unexpectedCount === 0,
      automated_observation_count: automated,
      controlled_real_observation_count: controlledReal,
      refresh_reconnect_authority: 'unproven',
      alpha_gate_pass: false,
    });
  }

  /**
   * Requires one terminal receipt per scenario. This checks ledger completeness
   * only; callers must separately inspect all_expected_boundaries and real evidence.
   */
  finalizeCompleteLedger(): Readonly<WebLifecycleObservationSnapshot> {
    const snapshot = this.snapshot();
    if (!snapshot.all_scenarios_observed) throw new Error('lifecycle observation ledger is missing required terminal scenarios');
    return snapshot;
  }

  #requireContextBinding(value: Readonly<WebLifecycleTerminalObservation>): void {
    if (
      value.context_binding_id !== this.#context.context_binding_id ||
      value.candidate_sha !== this.#context.candidate_sha ||
      value.run_id !== this.#context.run_id ||
      value.observation_source !== this.#context.observation_source
    ) {
      throw new Error('lifecycle observation context binding does not match the recorder');
    }
  }

  #requireTerminalFacts(value: Readonly<WebLifecycleTerminalObservation>): void {
    if (
      value.stale_effect_count !== 0 ||
      value.business_cancel_count_delta !== 0 ||
      value.automatic_retry_count !== 0 ||
      value.raw_audio_persisted !== false ||
      value.credential_material_observed !== false
    ) {
      throw new Error('lifecycle terminal observation violates the zero-effect or privacy boundary');
    }
  }
}
