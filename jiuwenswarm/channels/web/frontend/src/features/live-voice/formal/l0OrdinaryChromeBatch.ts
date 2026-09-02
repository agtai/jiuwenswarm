import {
  browserL0Control,
  type BrowserL0Control,
  type BrowserL0ControlSnapshot,
  type BrowserL0Envelope,
  type BrowserL0RunLabels,
} from './l0Measurement.js';
import type {
  BrowserAudioCaptureStreamFactory,
  BrowserMediaStreamLike,
} from './adapters/browserAudioIOAdapter.js';

export const L0_ORDINARY_BATCH_QUERY_FLAG = 'live_voice_l0_batch' as const;
export const L0_ORDINARY_BATCH_PORT_QUERY = 'live_voice_l0_coordinator_port' as const;
export const L0_ORDINARY_BATCH_NONCE_QUERY = 'live_voice_l0_nonce' as const;

const SESSION_VERSION = 'live-voice.l0-ordinary-batch.v1';
const JOB_VERSION = 'live-voice.l0-ordinary-job.v1';
const COMPLETION_VERSION = 'live-voice.l0-ordinary-completion.v1';
const REQUEST_TIMEOUT_MS = 10_000;
const SAMPLE_TIMEOUT_MS = 120_000;
const COORDINATOR_RETRY_MS = 500;
const MAX_COORDINATOR_RETRIES = 240;

export interface OrdinaryChromeBatchConfig {
  readonly base_url: string;
  readonly nonce: string;
}

export interface ProductTtsUnitLatencySummary {
  readonly unit_count: number;
  readonly request_count: number;
  readonly cancelled_unit_count: number;
  readonly wasted_prefetch_count: number;
  readonly prefix_end_to_tail_start_ms: number | null;
  readonly inter_unit_gap_ms: readonly number[];
  readonly inter_unit_gap_max_ms: number | null;
  readonly inter_unit_gap_p95_ms: number | null;
  readonly prepared_wait_ms: readonly number[];
  readonly total_response_playout_ms: number | null;
}

type UnitClocks = Partial<Record<
  | 'unit_tts_requested'
  | 'unit_first_pcm'
  | 'unit_prepared'
  | 'unit_playout_started'
  | 'unit_playout_completed'
  | 'unit_acknowledged',
  number
>>;

export function reduceProductTtsUnitLatency(
  records: readonly Readonly<BrowserL0Envelope>[],
): Readonly<ProductTtsUnitLatencySummary> {
  const elapsed = (start: number, end: number, field: string): number => {
    const value = end - start;
    if (!Number.isFinite(value) || value < 0) {
      throw new TypeError(`${field} clocks are contradictory`);
    }
    return value;
  };
  const units = new Map<number, UnitClocks>();
  let responseKey: string | null = null;
  for (const record of records) {
    if (!record.milestone.startsWith('unit_')) continue;
    const binding = record.binding;
    if (
      binding.response_id === null ||
      binding.response_generation === null ||
      binding.unit_seq === null
    ) continue;
    const key = JSON.stringify([
      binding.session_id,
      binding.interaction_id,
      binding.response_id,
      binding.response_generation,
    ]);
    if (responseKey !== null && responseKey !== key) {
      throw new TypeError('unit latency records cross authoritative responses');
    }
    responseKey = key;
    const clocks = units.get(binding.unit_seq) ?? {};
    const milestone = record.milestone as keyof UnitClocks;
    if (clocks[milestone] !== undefined) {
      throw new TypeError('unit latency milestone is duplicated');
    }
    clocks[milestone] = record.observation.monotonic_ms;
    units.set(binding.unit_seq, clocks);
  }
  const ordered = [...units.entries()].sort(([left], [right]) => left - right);
  const requests = ordered.filter(([, clocks]) => clocks.unit_tts_requested !== undefined);
  const preparedWait = ordered.flatMap(([, clocks]) =>
    clocks.unit_prepared !== undefined && clocks.unit_playout_started !== undefined
      ? [elapsed(clocks.unit_prepared, clocks.unit_playout_started, 'prepared wait')]
      : []
  );
  const gaps: number[] = [];
  for (let index = 1; index < ordered.length; index += 1) {
    const previous = ordered[index - 1][1];
    const current = ordered[index][1];
    if (
      previous.unit_playout_completed !== undefined &&
      current.unit_playout_started !== undefined &&
      current.unit_prepared !== undefined
    ) {
      gaps.push(elapsed(
        previous.unit_playout_completed,
        current.unit_playout_started,
        'inter-unit gap',
      ));
    }
  }
  const sortedGaps = [...gaps].sort((left, right) => left - right);
  const played = ordered.filter(([, clocks]) =>
    clocks.unit_playout_started !== undefined && clocks.unit_playout_completed !== undefined
  );
  const first = played.at(0)?.[1] ?? null;
  const last = played.at(-1)?.[1] ?? null;
  const prefix = units.get(0) ?? null;
  const firstTail = units.get(1) ?? null;
  return Object.freeze({
    unit_count: ordered.length,
    request_count: requests.length,
    cancelled_unit_count: requests.filter(([, clocks]) => clocks.unit_acknowledged === undefined).length,
    wasted_prefetch_count: requests.filter(([, clocks]) =>
      clocks.unit_prepared !== undefined && clocks.unit_playout_started === undefined
    ).length,
    prefix_end_to_tail_start_ms:
      prefix?.unit_playout_completed !== undefined &&
      firstTail?.unit_prepared !== undefined &&
      firstTail.unit_playout_started !== undefined
        ? elapsed(prefix.unit_playout_completed, firstTail.unit_playout_started, 'prefix-tail gap')
        : null,
    inter_unit_gap_ms: Object.freeze(gaps),
    inter_unit_gap_max_ms: sortedGaps.length === 0 ? null : sortedGaps[sortedGaps.length - 1],
    inter_unit_gap_p95_ms:
      sortedGaps.length < 20
        ? null
        : sortedGaps[Math.ceil(sortedGaps.length * 0.95) - 1],
    prepared_wait_ms: Object.freeze(preparedWait),
    total_response_playout_ms:
      first?.unit_playout_started !== undefined && last?.unit_playout_completed !== undefined
        ? elapsed(first.unit_playout_started, last.unit_playout_completed, 'total playout')
        : null,
  });
}

export type OrdinaryChromeBatchProgress = Readonly<{
  status: 'idle' | 'connecting' | 'warming' | 'running' | 'settling' | 'waiting_epoch' | 'complete' | 'failed' | 'cancelled';
  temperature: 'cold' | 'warm' | null;
  metric: 'first_audio' | 'barge_in' | null;
  first_audio_eligible: number;
  barge_in_eligible: number;
  target: number;
  reason: string | null;
}>;

export interface OrdinaryChromeVoiceState {
  readonly p1_status: string;
  readonly text_status: string;
  readonly recovery_diagnostic: unknown;
}

export interface OrdinaryChromeVoiceControl {
  start(): Promise<void>;
  stop(): Promise<void>;
  setL0CaptureStreamFactory(factory: BrowserAudioCaptureStreamFactory | null): void;
}

interface CoordinatorSession {
  readonly schema_version: typeof SESSION_VERSION;
  readonly temperature: 'cold' | 'warm';
  readonly epoch_id: string;
  readonly profile_id: string;
  readonly target: number;
  readonly first_audio_eligible: number;
  readonly barge_in_eligible: number;
  readonly warmup_required: boolean;
  readonly epoch_attempted: boolean;
  readonly batch_complete: boolean;
  readonly browser_mode: 'ordinary-installed-chrome';
  readonly physical_evidence: 'not-claimed';
}

interface CoordinatorJob {
  readonly schema_version: typeof JOB_VERSION;
  readonly job_id?: string;
  readonly epoch_id?: string;
  readonly temperature?: 'cold' | 'warm';
  readonly metric?: 'first_audio' | 'barge_in';
  readonly labels?: BrowserL0RunLabels & { readonly schema_version: string };
  readonly setup_audio?: 'short' | 'long';
  readonly barge_audio?: 'barge' | null;
  readonly batch_complete?: true;
}

interface StimulusPlayer {
  unlock(): Promise<void>;
  captureStreamFactory(): BrowserAudioCaptureStreamFactory;
  play(fixture: 'short' | 'long' | 'barge', signal: AbortSignal): Promise<void>;
  close(): Promise<void>;
}

export interface OrdinaryChromeBatchDependencies {
  readonly getControl: () => OrdinaryChromeVoiceControl | null;
  readonly getState: () => OrdinaryChromeVoiceState | null;
  readonly getConnected: () => boolean;
  readonly measurement?: () => BrowserL0Control | null;
  readonly request?: (
    path: string,
    init: Readonly<{ method: 'GET' | 'POST'; body?: object }>,
    signal: AbortSignal,
  ) => Promise<unknown>;
  readonly player?: StimulusPlayer;
  readonly sleep?: (milliseconds: number, signal: AbortSignal) => Promise<void>;
  readonly now?: () => number;
  readonly onProgress?: (progress: OrdinaryChromeBatchProgress) => void;
}

function exactKeys(value: object, expected: readonly string[], field: string): void {
  const actual = Object.keys(value).sort();
  const wanted = [...expected].sort();
  if (actual.length !== wanted.length || actual.some((item, index) => item !== wanted[index])) {
    throw new TypeError(`${field} has an invalid closed shape`);
  }
}

function safeInteger(value: unknown, field: string): number {
  if (!Number.isSafeInteger(value) || Number(value) < 0) throw new TypeError(`${field} is invalid`);
  return Number(value);
}

function parseSession(value: unknown): CoordinatorSession {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) throw new TypeError('session is invalid');
  exactKeys(value, [
    'schema_version',
    'temperature',
    'epoch_id',
    'profile_id',
    'target',
    'first_audio_eligible',
    'barge_in_eligible',
    'warmup_required',
    'epoch_attempted',
    'batch_complete',
    'browser_mode',
    'physical_evidence',
  ], 'session');
  const session = value as Readonly<Record<string, unknown>>;
  if (
    session.schema_version !== SESSION_VERSION
    || !['cold', 'warm'].includes(String(session.temperature))
    || typeof session.epoch_id !== 'string'
    || !/^[0-9a-f]{32}$/.test(session.epoch_id)
    || typeof session.profile_id !== 'string'
    || !/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(session.profile_id)
    || typeof session.warmup_required !== 'boolean'
    || typeof session.epoch_attempted !== 'boolean'
    || typeof session.batch_complete !== 'boolean'
    || session.browser_mode !== 'ordinary-installed-chrome'
    || session.physical_evidence !== 'not-claimed'
  ) throw new TypeError('session contains invalid facts');
  const target = safeInteger(session.target, 'target');
  if (target !== 20) throw new TypeError('target is invalid');
  const firstAudioEligible = safeInteger(session.first_audio_eligible, 'first_audio_eligible');
  const bargeInEligible = safeInteger(session.barge_in_eligible, 'barge_in_eligible');
  if (firstAudioEligible > target || bargeInEligible > target) {
    throw new TypeError('session eligible count exceeds target');
  }
  return Object.freeze({
    schema_version: SESSION_VERSION,
    temperature: session.temperature as 'cold' | 'warm',
    epoch_id: session.epoch_id,
    profile_id: session.profile_id,
    target,
    first_audio_eligible: firstAudioEligible,
    barge_in_eligible: bargeInEligible,
    warmup_required: session.warmup_required,
    epoch_attempted: session.epoch_attempted,
    batch_complete: session.batch_complete,
    browser_mode: 'ordinary-installed-chrome',
    physical_evidence: 'not-claimed',
  });
}

function parseJob(value: unknown, session: CoordinatorSession): CoordinatorJob {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) throw new TypeError('job is invalid');
  const job = value as Readonly<Record<string, unknown>>;
  if (job.schema_version !== JOB_VERSION) throw new TypeError('job version is invalid');
  if (job.batch_complete === true) {
    exactKeys(value, ['schema_version', 'batch_complete'], 'complete job');
    return Object.freeze({ schema_version: JOB_VERSION, batch_complete: true });
  }
  exactKeys(value, [
    'schema_version', 'job_id', 'epoch_id', 'temperature', 'metric', 'labels', 'setup_audio', 'barge_audio',
  ], 'job');
  if (
    typeof job.job_id !== 'string' || !/^[0-9a-f]{32}$/.test(job.job_id)
    || typeof job.epoch_id !== 'string' || !/^[0-9a-f]{32}$/.test(job.epoch_id)
    || job.epoch_id !== session.epoch_id
    || !['cold', 'warm'].includes(String(job.temperature))
    || job.temperature !== session.temperature
    || !['first_audio', 'barge_in'].includes(String(job.metric))
    || !['short', 'long'].includes(String(job.setup_audio))
    || (job.metric === 'first_audio' ? job.setup_audio !== 'short' : job.setup_audio !== 'long')
    || (job.metric === 'first_audio' ? job.barge_audio !== null : job.barge_audio !== 'barge')
    || job.labels === null || typeof job.labels !== 'object' || Array.isArray(job.labels)
  ) throw new TypeError('job contains invalid facts');
  const labels = job.labels as Readonly<Record<string, unknown>>;
  exactKeys(labels, ['schema_version', 'profile_id', 'scenario_id', 'sample_index', 'temperature', 'evidence_source'], 'job labels');
  if (
    labels.schema_version !== 'live-voice.l0-run-labels.v1'
    || labels.profile_id !== session.profile_id
    || labels.scenario_id !== (job.metric === 'first_audio' ? 'short-no-tool-zh' : 'playout-barge-in-zh')
    || labels.temperature !== job.temperature
    || labels.evidence_source !== 'prerecorded'
  ) throw new TypeError('job labels conflict with the job');
  safeInteger(labels.sample_index, 'sample_index');
  return Object.freeze({
    schema_version: JOB_VERSION,
    job_id: job.job_id,
    epoch_id: job.epoch_id,
    temperature: job.temperature as 'cold' | 'warm',
    metric: job.metric as 'first_audio' | 'barge_in',
    labels: labels as unknown as CoordinatorJob['labels'],
    setup_audio: job.setup_audio as 'short' | 'long',
    barge_audio: job.barge_audio as 'barge' | null,
  });
}

export function parseOrdinaryChromeBatchConfig(search: string): OrdinaryChromeBatchConfig | null {
  try {
    const query = new URLSearchParams(search);
    if (query.get(L0_ORDINARY_BATCH_QUERY_FLAG) !== '1') return null;
    const portText = query.get(L0_ORDINARY_BATCH_PORT_QUERY);
    const nonce = query.get(L0_ORDINARY_BATCH_NONCE_QUERY);
    if (portText === null || !/^\d{4}$/.test(portText) || nonce === null || !/^[0-9a-f]{32}$/.test(nonce)) return null;
    const port = Number(portText);
    if (!Number.isSafeInteger(port) || port < 9222 || port > 9322) return null;
    return Object.freeze({ base_url: `http://127.0.0.1:${port}`, nonce });
  } catch {
    return null;
  }
}

function defaultSleep(milliseconds: number, signal: AbortSignal): Promise<void> {
  if (signal.aborted) return Promise.reject(new DOMException('batch cancelled', 'AbortError'));
  return new Promise((resolve, reject) => {
    const timer = setTimeout(resolve, milliseconds);
    signal.addEventListener('abort', () => {
      clearTimeout(timer);
      reject(new DOMException('batch cancelled', 'AbortError'));
    }, { once: true });
  });
}

class WebAudioStimulusPlayer implements StimulusPlayer {
  readonly #config: OrdinaryChromeBatchConfig;
  #context: AudioContext | null = null;
  readonly #captureDestinations = new Set<MediaStreamAudioDestinationNode>();
  readonly #factory: BrowserAudioCaptureStreamFactory = async constraints => {
    if (constraints.video !== false || constraints.audio === false || constraints.audio === undefined) {
      throw new Error('l0_capture_constraints_invalid');
    }
    const context = this.#context;
    if (context === null || context.state !== 'running') throw new Error('audio_not_unlocked');
    const destination = context.createMediaStreamDestination();
    this.#captureDestinations.add(destination);
    return destination.stream as unknown as BrowserMediaStreamLike;
  };

  constructor(config: OrdinaryChromeBatchConfig) {
    this.#config = config;
  }

  async unlock(): Promise<void> {
    this.#context ??= new AudioContext();
    if (this.#context.state === 'suspended') await this.#context.resume();
    if (this.#context.state !== 'running') throw new Error('audio_unlock_failed');
    const buffer = this.#context.createBuffer(1, 1, this.#context.sampleRate);
    const source = this.#context.createBufferSource();
    source.buffer = buffer;
    source.connect(this.#context.destination);
    source.start();
  }

  captureStreamFactory(): BrowserAudioCaptureStreamFactory {
    return this.#factory;
  }

  #liveCaptureDestinations(): readonly MediaStreamAudioDestinationNode[] {
    for (const destination of this.#captureDestinations) {
      if (destination.stream.getAudioTracks().every(track => track.readyState !== 'live')) {
        this.#captureDestinations.delete(destination);
      }
    }
    return [...this.#captureDestinations];
  }

  async play(fixture: 'short' | 'long' | 'barge', signal: AbortSignal): Promise<void> {
    const context = this.#context;
    if (context === null || context.state !== 'running') throw new Error('audio_not_unlocked');
    const response = await fetch(`${this.#config.base_url}/v1/audio/${fixture}`, {
      method: 'GET',
      headers: { 'X-L0-Batch-Nonce': this.#config.nonce },
      cache: 'no-store',
      signal,
    });
    if (!response.ok) throw new Error('audio_fetch_failed');
    const decoded = await context.decodeAudioData(await response.arrayBuffer());
    if (signal.aborted) throw new DOMException('batch cancelled', 'AbortError');
    await new Promise<void>((resolve, reject) => {
      const source = context.createBufferSource();
      const abort = () => {
        try { source.stop(); } catch { /* already terminal */ }
        reject(new DOMException('batch cancelled', 'AbortError'));
      };
      signal.addEventListener('abort', abort, { once: true });
      source.buffer = decoded;
      source.connect(context.destination);
      for (const destination of this.#liveCaptureDestinations()) source.connect(destination);
      source.onended = () => {
        signal.removeEventListener('abort', abort);
        source.disconnect();
        resolve();
      };
      source.start();
    });
  }

  async close(): Promise<void> {
    const context = this.#context;
    this.#context = null;
    for (const destination of this.#captureDestinations) {
      for (const track of destination.stream.getTracks()) track.stop();
    }
    this.#captureDestinations.clear();
    if (context !== null && context.state !== 'closed') await context.close();
  }
}

function milestonePresent(snapshot: BrowserL0ControlSnapshot, milestone: BrowserL0Envelope['milestone']): boolean {
  return snapshot.records.some(record => record.milestone === milestone);
}

function deterministicCoordinatorRejection(error: unknown): boolean {
  return error instanceof Error && /^coordinator_4\d\d$/.test(error.message);
}

export class OrdinaryChromeL0BatchController {
  readonly #config: OrdinaryChromeBatchConfig;
  readonly #dependencies: OrdinaryChromeBatchDependencies;
  readonly #sleep: (milliseconds: number, signal: AbortSignal) => Promise<void>;
  readonly #now: () => number;
  readonly #player: StimulusPlayer;
  #abort: AbortController | null = null;

  constructor(config: OrdinaryChromeBatchConfig, dependencies: OrdinaryChromeBatchDependencies) {
    this.#config = config;
    this.#dependencies = dependencies;
    this.#sleep = dependencies.sleep ?? defaultSleep;
    this.#now = dependencies.now ?? (() => Date.now());
    this.#player = dependencies.player ?? new WebAudioStimulusPlayer(config);
  }

  #progress(value: OrdinaryChromeBatchProgress): void {
    this.#dependencies.onProgress?.(Object.freeze(value));
  }

  async #request(path: string, init: Readonly<{ method: 'GET' | 'POST'; body?: object }>, signal: AbortSignal): Promise<unknown> {
    if (this.#dependencies.request) return this.#dependencies.request(path, init, signal);
    const timeout = AbortSignal.timeout(REQUEST_TIMEOUT_MS);
    const combined = AbortSignal.any([signal, timeout]);
    const response = await fetch(`${this.#config.base_url}${path}`, {
      method: init.method,
      headers: {
        'X-L0-Batch-Nonce': this.#config.nonce,
        ...(init.body === undefined ? {} : { 'Content-Type': 'application/json' }),
      },
      ...(init.body === undefined ? {} : { body: JSON.stringify(init.body) }),
      cache: 'no-store',
      signal: combined,
    });
    if (!response.ok) throw new Error(`coordinator_${response.status}`);
    return response.json();
  }

  async #waitFor(
    predicate: () => boolean,
    signal: AbortSignal,
    timeoutMs = SAMPLE_TIMEOUT_MS,
  ): Promise<void> {
    const deadline = this.#now() + timeoutMs;
    while (!predicate()) {
      if (this.#now() >= deadline) throw new Error('browser_timeout');
      await this.#sleep(50, signal);
    }
  }

  async #session(signal: AbortSignal): Promise<CoordinatorSession> {
    let lastFailure: unknown = null;
    for (let attempt = 0; attempt < MAX_COORDINATOR_RETRIES; attempt += 1) {
      try {
        return parseSession(await this.#request('/v1/session', { method: 'GET' }, signal));
      } catch (error) {
        if (signal.aborted) throw error;
        lastFailure = error;
        this.#progress({
          status: 'waiting_epoch', temperature: null, metric: null,
          first_audio_eligible: 0, barge_in_eligible: 0, target: 20, reason: 'coordinator_unavailable',
        });
        await this.#sleep(COORDINATOR_RETRY_MS, signal);
      }
    }
    throw lastFailure ?? new Error('coordinator_unavailable');
  }

  async #ensureCapturing(signal: AbortSignal): Promise<void> {
    await this.#waitFor(() => this.#dependencies.getConnected(), signal);
    const control = this.#dependencies.getControl();
    if (control === null) throw new Error('surface_unavailable');
    control.setL0CaptureStreamFactory(this.#player.captureStreamFactory());
    if (this.#dependencies.getState()?.p1_status !== 'capturing') {
      await control.start();
    }
    await this.#waitFor(
      () => this.#dependencies.getState()?.p1_status === 'capturing',
      signal,
    );
  }

  async #warmup(session: CoordinatorSession, measurement: BrowserL0Control, signal: AbortSignal): Promise<void> {
    this.#progress({
      status: 'warming', temperature: 'warm', metric: null,
      first_audio_eligible: session.first_audio_eligible,
      barge_in_eligible: session.barge_in_eligible,
      target: session.target,
      reason: null,
    });
    measurement.disable();
    await this.#ensureCapturing(signal);
    await this.#player.play('short', signal);
    await this.#waitFor(() => this.#dependencies.getState()?.p1_status === 'playing', signal);
    await this.#waitFor(() => this.#dependencies.getState()?.p1_status === 'capturing', signal);
    const snapshot = measurement.snapshot();
    await this.#request('/v1/warmup', {
      method: 'POST',
      body: {
        schema_version: COMPLETION_VERSION,
        automated_browser_complete: true,
        browser_record_count: snapshot.records.length,
        browser_dropped_record_count: snapshot.dropped_records,
      },
    }, signal);
  }

  async #completeFailure(job: CoordinatorJob, measurement: BrowserL0Control, reason: string, signal: AbortSignal): Promise<void> {
    const snapshot = measurement.snapshot();
    try {
      await this.#request('/v1/complete', {
        method: 'POST',
        body: {
          schema_version: COMPLETION_VERSION,
          job_id: job.job_id,
          automated_browser_complete: false,
          browser_dropped_record_count: snapshot.dropped_records,
          records: snapshot.records,
          failure_reason: reason,
        },
      }, signal);
    } finally {
      measurement.disable();
    }
  }

  async #settleBargeSuccessor(signal: AbortSignal): Promise<void> {
    // The barge utterance is also a real successor turn.  Keep measurement
    // disabled until that turn has played and capture is ready again, otherwise
    // its delayed response can be relabelled as the next sample and satisfy the
    // next sample's first-audio predicate with the wrong response generation.
    if (this.#dependencies.getState()?.p1_status !== 'playing') {
      await this.#waitFor(() => this.#dependencies.getState()?.p1_status === 'playing', signal);
    }
    await this.#waitFor(() => this.#dependencies.getState()?.p1_status === 'capturing', signal);
  }

  async #sample(
    job: CoordinatorJob,
    session: CoordinatorSession,
    measurement: BrowserL0Control,
    signal: AbortSignal,
  ): Promise<void> {
    if (
      job.batch_complete === true
      || job.job_id === undefined
      || job.metric === undefined
      || job.labels === undefined
      || job.setup_audio === undefined
    ) return;
    const labels = { ...job.labels };
    let bargePlayback: Promise<void> | null = null;
    delete (labels as { schema_version?: string }).schema_version;
    measurement.clear();
    if (!measurement.configure(labels as BrowserL0RunLabels)) throw new Error('browser_labels_rejected');
    try {
      await this.#ensureCapturing(signal);
      await this.#player.play(job.setup_audio, signal);
      await this.#waitFor(() => milestonePresent(measurement.snapshot(), 'webaudio_actually_started'), signal);
      if (job.metric === 'first_audio') {
        await this.#waitFor(() => milestonePresent(measurement.snapshot(), 'playout_completed'), signal);
      } else {
        if (job.barge_audio !== 'barge') throw new Error('barge_fixture_missing');
        bargePlayback = this.#player.play('barge', signal);
        const fence = this.#waitFor(
          () => milestonePresent(measurement.snapshot(), 'fence_cancel_completion'),
          signal,
        );
        // Commit the interrupted response as soon as its exact local fence is
        // observed. Waiting for the whole barge fixture here lets its successor
        // response inherit the still-active sample labels.
        await Promise.race([fence, bargePlayback.then(() => fence)]);
      }
    } catch (error) {
      if (signal.aborted) {
        measurement.disable();
        throw error;
      }
      const reason = error instanceof Error && /^[a-z][a-z0-9_]{0,63}$/.test(error.message)
        ? error.message
        : 'browser_sample_failed';
      try {
        await this.#completeFailure(job, measurement, reason, signal);
      } catch (completionError) {
        if (deterministicCoordinatorRejection(completionError)) throw completionError;
        // The request may have committed before its response was lost. Polling
        // the exact session either recovers that commit or returns the same job.
      }
      return;
    }
    const snapshot = measurement.snapshot();
    const complete = snapshot.configured
      && snapshot.dropped_records === 0
      && (job.metric === 'first_audio'
        ? milestonePresent(snapshot, 'webaudio_actually_started') && milestonePresent(snapshot, 'playout_completed')
        : milestonePresent(snapshot, 'barge_in') && milestonePresent(snapshot, 'fence_cancel_completion'));
    try {
      await this.#request('/v1/complete', {
        method: 'POST',
        body: {
          schema_version: COMPLETION_VERSION,
          job_id: job.job_id,
          automated_browser_complete: complete,
          browser_dropped_record_count: snapshot.dropped_records,
          records: snapshot.records,
          failure_reason: complete ? 'none' : 'browser_incomplete',
        },
      }, signal);
    } catch (error) {
      if (deterministicCoordinatorRejection(error)) throw error;
      // A transport timeout is an unknown outcome, not evidence of failure.
      // The next exact-session read safely determines whether to advance or
      // replay the still-active job.
    } finally {
      measurement.disable();
    }
    if (job.metric === 'barge_in') {
      if (bargePlayback === null) throw new Error('barge_fixture_missing');
      await bargePlayback;
      this.#progress({
        status: 'settling', temperature: session.temperature, metric: 'barge_in',
        first_audio_eligible: session.first_audio_eligible,
        barge_in_eligible: session.barge_in_eligible,
        target: session.target,
        reason: 'successor_playout_not_measured',
      });
      await this.#settleBargeSuccessor(signal);
    }
  }

  async run(): Promise<void> {
    if (this.#abort !== null) return;
    const abort = new AbortController();
    this.#abort = abort;
    try {
      const measurement = (this.#dependencies.measurement ?? browserL0Control)();
      if (measurement === null) throw new Error('measurement_control_unavailable');
      this.#progress({
        status: 'connecting', temperature: null, metric: null,
        first_audio_eligible: 0, barge_in_eligible: 0, target: 20, reason: null,
      });
      await this.#player.unlock();
      while (!abort.signal.aborted) {
        const session = await this.#session(abort.signal);
        if (session.batch_complete) {
          this.#progress({
            status: 'complete', temperature: session.temperature, metric: null,
            first_audio_eligible: session.first_audio_eligible,
            barge_in_eligible: session.barge_in_eligible,
            target: session.target,
            reason: null,
          });
          return;
        }
        if (session.warmup_required) await this.#warmup(session, measurement, abort.signal);
        if (session.temperature === 'cold' && session.epoch_attempted) {
          this.#progress({
            status: 'waiting_epoch', temperature: 'cold', metric: null,
            first_audio_eligible: session.first_audio_eligible,
            barge_in_eligible: session.barge_in_eligible,
            target: session.target,
            reason: 'waiting_fresh_cold_epoch',
          });
          await this.#sleep(COORDINATOR_RETRY_MS, abort.signal);
          continue;
        }
        const job = parseJob(
          await this.#request('/v1/next', { method: 'POST' }, abort.signal),
          session,
        );
        if (job.batch_complete === true) continue;
        this.#progress({
          status: 'running', temperature: session.temperature, metric: job.metric ?? null,
          first_audio_eligible: session.first_audio_eligible,
          barge_in_eligible: session.barge_in_eligible,
          target: session.target,
          reason: null,
        });
        await this.#sample(job, session, measurement, abort.signal);
        if (session.temperature === 'cold') {
          await this.#dependencies.getControl()?.stop().catch(() => undefined);
        }
      }
    } catch (error) {
      if (abort.signal.aborted) {
        this.#progress({
          status: 'cancelled', temperature: null, metric: null,
          first_audio_eligible: 0, barge_in_eligible: 0, target: 20, reason: 'cancelled',
        });
      } else {
        const reason = error instanceof Error && /^[a-z][a-z0-9_]{0,63}$/.test(error.message)
          ? error.message
          : 'batch_failed';
        this.#progress({
          status: 'failed', temperature: null, metric: null,
          first_audio_eligible: 0, barge_in_eligible: 0, target: 20, reason,
        });
        throw error;
      }
    } finally {
      this.#abort = null;
    }
  }

  cancel(): void {
    this.#abort?.abort();
  }

  async close(): Promise<void> {
    this.cancel();
    this.#dependencies.getControl()?.setL0CaptureStreamFactory(null);
    await this.#player.close();
  }
}
