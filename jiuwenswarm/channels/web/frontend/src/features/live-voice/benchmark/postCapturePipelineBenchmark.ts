export type PostCaptureBenchmarkPhase = 'waiting_for_session' | 'loading_fixture' | 'waiting_for_activation' | 'running' | 'exporting' | 'completed' | 'failed';

export interface PostCaptureBenchmarkConfig {
  readonly run_id: string;
  readonly profile_id: 'dialogue_no_tool' | 'dialogue_with_tool';
  readonly input_case_id: string;
  readonly round_index: number;
  readonly session_id: string;
  readonly fixture_url: string;
  readonly result_url: string;
  readonly start_delay_ms: number;
}

export interface PostCaptureBenchmarkControl {
  startFixture(wavBytes: ArrayBuffer): Promise<void>;
  close(): Promise<void>;
}

export interface PostCaptureBenchmarkDependencies {
  fetchFixture(url: string, signal: AbortSignal): Promise<Readonly<{ wav_bytes: ArrayBuffer; expected_transcript_sha256: string }>>;
  postResult(result: Readonly<PostCaptureBenchmarkResult>): Promise<void>;
  digestTranscript(normalizedText: string): Promise<string>;
}

export interface PostCaptureBenchmarkResult {
  readonly schema_version: 'live-voice.post-capture-result.v0';
  readonly run_id: string;
  readonly profile_id: string;
  readonly input_case_id: string;
  readonly round_index: number;
  readonly outcome: 'completed' | 'unknown';
}

type BatchReceipt = Readonly<{ disposition: 'written' | 'idempotent' | 'unknown' }>;
type Batch = Readonly<{ run_id: string; profile_id: string; input_case_id: string; round_index: number; terminal_outcome: string }>;

const KEYS = new Set([
  'live_voice_post_capture_benchmark',
  'run_id',
  'profile_id',
  'input_case_id',
  'round_index',
  'session_id',
  'fixture_url',
  'result_url',
  'start_delay_ms',
]);
const TOKEN = /^[A-Za-z0-9_-][A-Za-z0-9._-]{0,127}$/;
const SHA256 = /^[0-9a-f]{64}$/;

function canonicalInteger(value: string, minimum: number, maximum: number): number | null {
  if (!/^(0|[1-9][0-9]*)$/.test(value)) return null;
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed >= minimum && parsed <= maximum ? parsed : null;
}

function closedLoopbackUrl(value: string, path: string): URL | null {
  try {
    const url = new URL(value);
    if (
      url.protocol !== 'http:' ||
      url.hostname !== '127.0.0.1' ||
      url.username !== '' ||
      url.password !== '' ||
      url.hash !== '' ||
      url.search !== '' ||
      url.pathname !== path
    )
      return null;
    return url;
  } catch {
    return null;
  }
}

export function parsePostCaptureBenchmarkConfig(
  enabled: boolean,
  location: Pick<Location, 'search' | 'origin' | 'pathname'>,
): PostCaptureBenchmarkConfig | null {
  if (enabled !== true) return null;
  try {
    const params = new URLSearchParams(location.search);
    const values: Record<string, string> = {};
    for (const [key, value] of params) {
      if (!KEYS.has(key) || key in values) return null;
      values[key] = value;
    }
    if (Object.keys(values).length !== KEYS.size || values.live_voice_post_capture_benchmark !== '1') return null;
    const profile = values.profile_id;
    if (profile !== 'dialogue_no_tool' && profile !== 'dialogue_with_tool') return null;
    for (const key of ['run_id', 'input_case_id', 'session_id'] as const) if (!TOKEN.test(values[key])) return null;
    const roundIndex = canonicalInteger(values.round_index, 0, 255);
    const startDelay = canonicalInteger(values.start_delay_ms, 250, 5_000);
    if (roundIndex === null || startDelay === null || location.pathname !== `/chat/${values.session_id}`) return null;
    const fixture = closedLoopbackUrl(values.fixture_url, `/fixture/${values.input_case_id}.wav`);
    const result = closedLoopbackUrl(values.result_url, '/result');
    if (fixture === null || result === null || fixture.origin !== result.origin) return null;
    return Object.freeze({
      run_id: values.run_id,
      profile_id: profile,
      input_case_id: values.input_case_id,
      round_index: roundIndex,
      session_id: values.session_id,
      fixture_url: fixture.href,
      result_url: result.href,
      start_delay_ms: startDelay,
    });
  } catch {
    return null;
  }
}

class PostCapturePipelineBenchmark {
  readonly #config: PostCaptureBenchmarkConfig;
  readonly #dependencies: PostCaptureBenchmarkDependencies;
  readonly #abort = new AbortController();
  #phase: PostCaptureBenchmarkPhase = 'waiting_for_session';
  #control: PostCaptureBenchmarkControl | null = null;
  #terminal = false;
  #batchCompleted = false;
  #presentationAcked = false;
  #expectedTranscriptSha256: string | null = null;

  constructor(config: PostCaptureBenchmarkConfig, dependencies: PostCaptureBenchmarkDependencies) {
    this.#config = config;
    this.#dependencies = dependencies;
  }

  async start(control: PostCaptureBenchmarkControl): Promise<void> {
    if (this.#phase !== 'waiting_for_session' || this.#terminal) return;
    this.#control = control;
    this.#phase = 'loading_fixture';
    try {
      const fixture = await this.#dependencies.fetchFixture(this.#config.fixture_url, this.#abort.signal);
      if (
        fixture === null ||
        typeof fixture !== 'object' ||
        !(fixture.wav_bytes instanceof ArrayBuffer) ||
        fixture.wav_bytes.byteLength === 0 ||
        !SHA256.test(fixture.expected_transcript_sha256) ||
        this.#terminal
      )
        return await this.#terminalize('unknown');
      this.#expectedTranscriptSha256 = fixture.expected_transcript_sha256;
      this.#phase = 'waiting_for_activation';
      await control.startFixture(fixture.wav_bytes);
      if (!this.#terminal) this.#phase = 'running';
    } catch {
      await this.#terminalize('unknown');
    }
  }

  async observeBatch(batch: Batch, receipt: BatchReceipt): Promise<void> {
    if (this.#terminal || this.#phase !== 'running') return;
    if (
      batch.run_id !== this.#config.run_id ||
      batch.profile_id !== this.#config.profile_id ||
      batch.input_case_id !== this.#config.input_case_id ||
      batch.round_index !== this.#config.round_index
    )
      return;
    if (receipt.disposition === 'unknown') {
      await this.#terminalize('unknown');
      return;
    }
    if (batch.terminal_outcome !== 'completed') {
      await this.#terminalize('unknown');
      return;
    }
    this.#batchCompleted = true;
    if (this.#presentationAcked) await this.#terminalize('completed');
  }

  async observePresentationAck(): Promise<void> {
    if (this.#terminal || this.#phase !== 'running') return;
    this.#presentationAcked = true;
    if (this.#batchCompleted) await this.#terminalize('completed');
  }

  async acceptRecognizedText(text: string): Promise<boolean> {
    if (this.#terminal || this.#phase !== 'running' || typeof text !== 'string' || text.length > 16_384) return false;
    const normalized = text
      .normalize('NFKC')
      .toLowerCase()
      .replace(/[^\p{L}\p{N}]+/gu, ' ')
      .trim();
    if (normalized.length === 0) {
      await this.#terminalize('unknown');
      return false;
    }
    try {
      const digest = await this.#dependencies.digestTranscript(normalized);
      if (this.#terminal || this.#phase !== 'running') return false;
      if (digest === this.#expectedTranscriptSha256) return true;
    } catch {
      // A semantic oracle failure is diagnostic and blocks product submission.
    }
    await this.#terminalize('unknown');
    return false;
  }

  async close(): Promise<void> {
    await this.#terminalize('unknown');
  }

  async #terminalize(outcome: 'completed' | 'unknown'): Promise<void> {
    if (this.#terminal) return;
    this.#terminal = true;
    this.#abort.abort();
    this.#phase = 'exporting';
    const result = Object.freeze({
      schema_version: 'live-voice.post-capture-result.v0' as const,
      run_id: this.#config.run_id,
      profile_id: this.#config.profile_id,
      input_case_id: this.#config.input_case_id,
      round_index: this.#config.round_index,
      outcome,
    });
    try {
      await this.#dependencies.postResult(result);
      this.#phase = 'completed';
    } catch {
      this.#phase = 'failed';
    } finally {
      try {
        await this.#control?.close();
      } catch {
        // Product cleanup is terminal and cannot expose an implementation error.
      }
    }
  }
}

export function createPostCapturePipelineBenchmark(
  config: PostCaptureBenchmarkConfig | null,
  dependencies: PostCaptureBenchmarkDependencies | null,
): PostCapturePipelineBenchmark | null {
  if (
    config === null ||
    dependencies === null ||
    typeof dependencies.fetchFixture !== 'function' ||
    typeof dependencies.postResult !== 'function' ||
    typeof dependencies.digestTranscript !== 'function'
  )
    return null;
  return new PostCapturePipelineBenchmark(config, dependencies);
}
