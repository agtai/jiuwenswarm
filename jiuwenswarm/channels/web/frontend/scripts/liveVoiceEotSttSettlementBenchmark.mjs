import { spawn, execFileSync } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import fs from 'node:fs/promises';
import { constants as fsConstants } from 'node:fs';
import path from 'node:path';
import { performance } from 'node:perf_hooks';
import readline from 'node:readline';
import { fileURLToPath, pathToFileURL } from 'node:url';

import {
  runEotSttSettlementBenchmark,
} from '../node_modules/.cache/live-voice-eot-stt-benchmark/eotSttSettlementBenchmark.js';

const GIT_COMMIT = /^[0-9a-f]{40}$/;
const RUN_ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const EXPECTED_TEXT = 'benchmark recognition';
const FIXTURES = Object.freeze([
  Object.freeze({ id: 'local-fast-provider-fast', localSettlementMs: 50, providerFinalMs: 50 }),
  Object.freeze({ id: 'local-slow-provider-fast', localSettlementMs: 500, providerFinalMs: 50 }),
  Object.freeze({ id: 'local-fast-provider-slow', localSettlementMs: 50, providerFinalMs: 500 }),
  Object.freeze({ id: 'both-slow', localSettlementMs: 500, providerFinalMs: 500 }),
]);
const REQUIRED_MARKS = Object.freeze([
  'browser.eot_received',
  'browser.uplink_closed',
  'browser.streaming_result_request_started',
  'browser.streaming_result_returned',
  'browser.stt_final_received',
]);
const FRONTEND_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const FIXTURE_SCRIPT = fileURLToPath(new URL('../../../../../scripts/live_voice/eot_stt_registry_fixture.py', import.meta.url));
const PRODUCT_MODULE_URL = new URL('../node_modules/.cache/live-voice-integrated-web/features/live-voice/formal/productP1VoiceRoute.js', import.meta.url);
const MEDIA_MODULE_URL = new URL('../node_modules/.cache/live-voice-integrated-web/features/live-voice/formal/adapters/browserDedicatedMediaRoute.js', import.meta.url);
const FIXTURE_REQUEST_TIMEOUT_MS = 10_000;
const FIXTURE_SHUTDOWN_TIMEOUT_MS = 2_000;
const FIXTURE_KILL_TIMEOUT_MS = 2_000;

function fail(code) {
  throw new Error(code);
}

function canonicalInteger(value, minimum, maximum) {
  if (typeof value !== 'string' || !/^(?:0|[1-9][0-9]*)$/.test(value)) return null;
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed >= minimum && parsed <= maximum ? parsed : null;
}

function rounded(value) {
  return Math.round(value * 1_000) / 1_000;
}

export function parseEotSttSettlementBenchmarkArgs(argv) {
  if (!Array.isArray(argv) || argv.length % 2 !== 0) fail('EOT_STT_BENCHMARK_ARGUMENT_INVALID');
  const allowed = new Set(['--output', '--git-commit', '--run-id', '--attempts', '--candidate', '--python-executable']);
  const values = new Map();
  for (let index = 0; index < argv.length; index += 2) {
    const key = argv[index];
    const value = argv[index + 1];
    if (!allowed.has(key) || values.has(key) || typeof value !== 'string' || value === '') {
      fail('EOT_STT_BENCHMARK_ARGUMENT_INVALID');
    }
    values.set(key, value);
  }
  const output = values.get('--output');
  const gitCommit = values.get('--git-commit');
  const runId = values.get('--run-id');
  const attempts = canonicalInteger(values.get('--attempts'), 5, 20);
  const candidate = values.get('--candidate');
  const pythonExecutable = values.get('--python-executable');
  if (
    values.size !== allowed.size ||
    typeof output !== 'string' ||
    !path.isAbsolute(output) ||
    output.includes('\n') ||
    output.includes('\r') ||
    !GIT_COMMIT.test(gitCommit ?? '') ||
    !RUN_ID.test(runId ?? '') ||
    attempts === null ||
    candidate !== 'A1' ||
    typeof pythonExecutable !== 'string' ||
    !path.isAbsolute(pythonExecutable) ||
    pythonExecutable.includes('\n') ||
    pythonExecutable.includes('\r')
  ) {
    fail('EOT_STT_BENCHMARK_ARGUMENT_INVALID');
  }
  return Object.freeze({ output, gitCommit, runId, attempts, candidate: 'A1', pythonExecutable });
}

export function assertEotSttCleanSource(expectedCommit, actualCommit, statusText) {
  if (expectedCommit !== actualCommit || statusText !== '') fail('EOT_STT_BENCHMARK_SOURCE_NOT_CLEAN');
}

export async function validateEotSttPythonExecutable(pythonExecutable) {
  try {
    if (typeof pythonExecutable !== 'string' || !path.isAbsolute(pythonExecutable)) {
      fail('EOT_STT_BENCHMARK_PYTHON_INVALID');
    }
    const resolved = await fs.realpath(pythonExecutable);
    if (!path.isAbsolute(resolved)) fail('EOT_STT_BENCHMARK_PYTHON_INVALID');
    await fs.access(pythonExecutable, fsConstants.X_OK);
    const metadata = await fs.stat(pythonExecutable);
    if (!metadata.isFile()) fail('EOT_STT_BENCHMARK_PYTHON_INVALID');
    return pythonExecutable;
  } catch {
    fail('EOT_STT_BENCHMARK_PYTHON_INVALID');
  }
}

export async function writeEotSttSettlementBenchmarkReport(output, report, options = {}) {
  let handle = null;
  let temporary = null;
  try {
    if (
      options === null ||
      typeof options !== 'object' ||
      Array.isArray(options) ||
      Object.keys(options).some(key => key !== 'before_publish') ||
      (options.before_publish !== undefined && typeof options.before_publish !== 'function')
    ) {
      fail('EOT_STT_BENCHMARK_REPORT_WRITE_FAILED');
    }
    const serialized = `${JSON.stringify(report)}\n`;
    const directory = path.dirname(output);
    temporary = path.join(directory, `.${path.basename(output)}.${randomUUID()}.tmp`);
    handle = await fs.open(temporary, 'wx', 0o600);
    await handle.writeFile(serialized, 'utf8');
    await handle.chmod(0o600);
    await handle.sync();
    await handle.close();
    handle = null;
    await options.before_publish?.();
    await fs.link(temporary, output);
  } catch (error) {
    if (handle !== null) await handle.close().catch(() => undefined);
    if (temporary !== null) await fs.unlink(temporary).catch(() => undefined);
    if (error?.code === 'EEXIST') fail('EOT_STT_BENCHMARK_OUTPUT_EXISTS');
    fail('EOT_STT_BENCHMARK_REPORT_WRITE_FAILED');
  }
  try {
    await fs.unlink(temporary);
  } catch {
    await fs.unlink(output).catch(() => undefined);
    fail('EOT_STT_BENCHMARK_REPORT_WRITE_FAILED');
  }
}

export class JsonLineRegistryFixture {
  constructor(pythonExecutable, localSettlementMs, providerFinalMs, options = {}) {
    if (options === null || typeof options !== 'object' || Array.isArray(options)) {
      fail('EOT_STT_BENCHMARK_FIXTURE_FAILED');
    }
    const requestTimeoutMs = options.request_timeout_ms ?? FIXTURE_REQUEST_TIMEOUT_MS;
    const shutdownTimeoutMs = options.shutdown_timeout_ms ?? FIXTURE_SHUTDOWN_TIMEOUT_MS;
    const killTimeoutMs = options.kill_timeout_ms ?? FIXTURE_KILL_TIMEOUT_MS;
    const fixtureScript = options.fixture_script ?? FIXTURE_SCRIPT;
    if (
      Object.keys(options).some(key => ![
        'fixture_script',
        'request_timeout_ms',
        'shutdown_timeout_ms',
        'kill_timeout_ms',
      ].includes(key)) ||
      typeof fixtureScript !== 'string' ||
      !path.isAbsolute(fixtureScript) ||
      ![requestTimeoutMs, shutdownTimeoutMs, killTimeoutMs].every(
        value => Number.isSafeInteger(value) && value >= 10 && value <= 60_000,
      )
    ) {
      fail('EOT_STT_BENCHMARK_FIXTURE_FAILED');
    }
    this.requestTimeoutMs = requestTimeoutMs;
    this.shutdownTimeoutMs = shutdownTimeoutMs;
    this.killTimeoutMs = killTimeoutMs;
    this.child = spawn(
      pythonExecutable,
      [fixtureScript, '--local-settlement-ms', String(localSettlementMs), '--provider-final-ms', String(providerFinalMs)],
      { shell: false, stdio: ['pipe', 'pipe', 'pipe'] },
    );
    this.lines = readline.createInterface({ input: this.child.stdout, crlfDelay: Infinity });
    this.iterator = this.lines[Symbol.asyncIterator]();
    this.stderrBytes = 0;
    this.protocolFailed = false;
    this.protocolClosed = false;
    this.reaped = false;
    this.termSent = false;
    this.killSent = false;
    this.exitFact = null;
    this.spawnObserved = false;
    this.terminationRequested = false;
    this.closePromise = null;
    this.terminationPromise = null;
    let resolveSpawn;
    let resolveExit;
    this.spawned = new Promise(resolve => { resolveSpawn = resolve; });
    this.exited = new Promise(resolve => { resolveExit = resolve; });
    const settleExit = fact => {
      if (this.reaped) return;
      this.reaped = true;
      this.exitFact = fact;
      resolveExit(fact);
    };
    this.child.once('spawn', () => {
      this.spawnObserved = true;
      resolveSpawn(true);
      if (this.terminationRequested && !this.reaped) {
        this.termSent = this.child.kill('SIGTERM') || this.termSent;
      }
    });
    this.child.on('error', () => {
      this.protocolFailed = true;
      if (!this.spawnObserved) {
        resolveSpawn(false);
        settleExit({ code: null, signal: null, spawn_error: true });
      }
    });
    this.child.once('exit', (code, signal) => {
      settleExit({ code, signal, spawn_error: false });
    });
    this.child.stderr.on('data', chunk => {
      this.stderrBytes = Math.min(4097, this.stderrBytes + chunk.length);
    });
    const observeStreamError = () => {
      this.protocolFailed = true;
    };
    this.child.stdin.on('error', observeStreamError);
    this.child.stdout.on('error', observeStreamError);
    this.child.stderr.on('error', observeStreamError);
  }

  async _bounded(promise, timeoutMs) {
    let timer = null;
    try {
      return await Promise.race([
        promise.then(
          value => ({ settled: true, value }),
          () => ({ settled: false, timed_out: false }),
        ),
        new Promise(resolve => {
          timer = setTimeout(
            () => resolve({ settled: false, timed_out: true }),
            timeoutMs,
          );
        }),
      ]);
    } finally {
      if (timer !== null) clearTimeout(timer);
    }
  }

  async _requireSpawned() {
    const result = await this._bounded(this.spawned, this.requestTimeoutMs);
    if (!result.settled || result.value !== true) fail('EOT_STT_BENCHMARK_FIXTURE_FAILED');
  }

  async request(operation) {
    try {
      if (this.protocolClosed || !['open', 'provider_final', 'route_settled', 'streaming_result', 'close'].includes(operation)) {
        fail('EOT_STT_BENCHMARK_FIXTURE_FAILED');
      }
      await this._requireSpawned();
      if (this.reaped || this.protocolFailed) fail('EOT_STT_BENCHMARK_FIXTURE_FAILED');
      const line = `${JSON.stringify({ operation })}\n`;
      const write = await this._bounded(
        new Promise((resolve, reject) => {
          this.child.stdin.write(line, error => error ? reject(error) : resolve());
        }),
        this.requestTimeoutMs,
      );
      if (!write.settled || this.protocolFailed) fail('EOT_STT_BENCHMARK_FIXTURE_FAILED');
      const itemResult = await this._bounded(this.iterator.next(), this.requestTimeoutMs);
      if (!itemResult.settled || this.protocolFailed) fail('EOT_STT_BENCHMARK_FIXTURE_FAILED');
      const item = itemResult.value;
      if (item.done || typeof item.value !== 'string' || Buffer.byteLength(item.value, 'utf8') > 64 * 1024) {
        fail('EOT_STT_BENCHMARK_FIXTURE_FAILED');
      }
      let response = null;
      try {
        response = JSON.parse(item.value);
      } catch {
        fail('EOT_STT_BENCHMARK_FIXTURE_FAILED');
      }
      if (response === null || typeof response !== 'object' || Array.isArray(response) || response.status === 'rejected') {
        fail('EOT_STT_BENCHMARK_FIXTURE_FAILED');
      }
      if (operation === 'close' && response.cleanup_complete === true) this.protocolClosed = true;
      return response;
    } catch {
      await this.terminate();
      fail('EOT_STT_BENCHMARK_FIXTURE_FAILED');
    }
  }

  async close() {
    if (this.closePromise !== null) return this.closePromise;
    this.closePromise = this._closeOnce();
    return this.closePromise;
  }

  async _closeOnce() {
    try {
      let cleanupComplete = this.protocolClosed;
      for (let attempt = 0; !cleanupComplete && attempt < 2; attempt += 1) {
        if (this.reaped) fail('EOT_STT_BENCHMARK_FIXTURE_FAILED');
        const response = await this.request('close');
        cleanupComplete = response.status === 'closed' && response.cleanup_complete === true;
      }
      if (!cleanupComplete) fail('EOT_STT_BENCHMARK_FIXTURE_FAILED');
      if (!this.child.stdin.destroyed) {
        const ended = await this._bounded(
          new Promise((resolve, reject) => this.child.stdin.end(error => error ? reject(error) : resolve())),
          this.shutdownTimeoutMs,
        );
        if (!ended.settled) fail('EOT_STT_BENCHMARK_FIXTURE_FAILED');
      }
      const exited = await this._bounded(this.exited, this.shutdownTimeoutMs);
      if (!exited.settled) {
        await this.terminate();
        fail('EOT_STT_BENCHMARK_FIXTURE_FAILED');
      }
      this._closePipes();
      if (
        this.exitFact?.spawn_error === true ||
        this.exitFact?.code !== 0 ||
        this.exitFact?.signal !== null ||
        this.protocolFailed ||
        this.stderrBytes !== 0
      ) {
        fail('EOT_STT_BENCHMARK_FIXTURE_FAILED');
      }
      return true;
    } catch {
      await this.terminate();
      fail('EOT_STT_BENCHMARK_FIXTURE_FAILED');
    }
  }

  _closePipes() {
    try { this.lines.close(); } catch {}
    this.child.stdin.destroy();
    this.child.stdout.destroy();
    this.child.stderr.destroy();
  }

  async terminate() {
    if (this.terminationPromise !== null) return this.terminationPromise;
    this.terminationPromise = this._terminateOnce();
    return this.terminationPromise;
  }

  async _terminateOnce() {
    this.terminationRequested = true;
    this.child.stdin.destroy();
    try { this.lines.close(); } catch {}
    if (!this.reaped && !this.spawnObserved) {
      await this._bounded(this.spawned, this.shutdownTimeoutMs);
    }
    if (!this.reaped && this.child.pid !== undefined) {
      if (!this.termSent) this.termSent = this.child.kill('SIGTERM') || this.termSent;
      const terminated = await this._bounded(this.exited, this.shutdownTimeoutMs);
      if (!terminated.settled && !this.reaped) {
        this.killSent = this.child.kill('SIGKILL') || this.killSent;
        const killed = await this._bounded(this.exited, this.killTimeoutMs);
        if (!killed.settled || !this.reaped) {
          this._closePipes();
          fail('EOT_STT_BENCHMARK_FIXTURE_CLEANUP_FAILED');
        }
      }
    } else if (!this.reaped) {
      const exited = await this._bounded(this.exited, this.shutdownTimeoutMs);
      if (!exited.settled || !this.reaped) {
        this._closePipes();
        fail('EOT_STT_BENCHMARK_FIXTURE_CLEANUP_FAILED');
      }
    }
    this._closePipes();
    if (!this.reaped) fail('EOT_STT_BENCHMARK_FIXTURE_CLEANUP_FAILED');
    return this.lifecycle();
  }

  lifecycle() {
    return Object.freeze({
      reaped: this.reaped,
      term_sent: this.termSent,
      kill_sent: this.killSent,
    });
  }
}

class FakeEventTarget {
  constructor() {
    this.listeners = new Map();
  }
  addEventListener(type, listener) {
    const listeners = this.listeners.get(type) ?? new Set();
    listeners.add(listener);
    this.listeners.set(type, listeners);
  }
  removeEventListener(type, listener) {
    this.listeners.get(type)?.delete(listener);
  }
}

class FakeNode {
  connect(destination) { return destination; }
  disconnect() {}
}

class FakeAudioContext {
  constructor() {
    this.sampleRate = 48_000;
    this.currentTime = 0;
    this.destination = Object.freeze({ kind: 'destination' });
    this.state = 'suspended';
    this.onstatechange = null;
    this.audioWorklet = { addModule: async () => undefined };
  }
  async resume() { this.state = 'running'; }
  async close() { this.state = 'closed'; }
  createMediaStreamSource() { return new FakeNode(); }
  createBuffer(_channels, length, sampleRate) { return { length, sampleRate, copyToChannel() {} }; }
  createBufferSource() {
    return { buffer: null, onended: null, connect() {}, disconnect() {}, start() {}, stop() {} };
  }
}

class FakeTrack extends FakeEventTarget {
  constructor() {
    super();
    this.id = 'track-1';
    this.kind = 'audio';
    this.readyState = 'live';
    this.muted = false;
  }
  stop() { this.readyState = 'ended'; }
  getSettings() {
    return {
      sampleRate: 48_000,
      channelCount: 1,
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
    };
  }
}

function makeAudioEnvironment() {
  const document = new FakeEventTarget();
  document.visibilityState = 'visible';
  const mediaDevices = new FakeEventTarget();
  mediaDevices.getUserMedia = async () => {
    const track = new FakeTrack();
    environment.track = track;
    return { getAudioTracks: () => [track], getTracks: () => [track] };
  };
  mediaDevices.enumerateDevices = async () => [{ kind: 'audioinput' }];
  const environment = {
    isSecureContext: true,
    document,
    mediaDevices,
    permissions: null,
    createAudioContext: () => new FakeAudioContext(),
    createAudioWorkletNode: (_context, _name, options) => {
      const node = new FakeNode();
      node.port = { onmessage: null, close() {} };
      node.onprocessorerror = null;
      node.captureGeneration = options.processorOptions.captureGeneration;
      environment.worklet = node;
      return node;
    },
    createId: () => 'capture-1',
    outputDeviceSelection: false,
    track: null,
    worklet: null,
  };
  return environment;
}

class BenchmarkMediaSocket {
  constructor(binding, registryFixture) {
    this.binding = binding;
    this.registryFixture = registryFixture;
    this.readyState = 0;
    this.bufferedAmount = 0;
    this.protocol = '';
    this.binaryType = 'blob';
    this.onopen = null;
    this.onmessage = null;
    this.onerror = null;
    this.onclose = null;
    this.binarySendCount = 0;
  }

  open() {
    this.protocol = 'live-voice.media.v1';
    this.readyState = 1;
    this.onopen?.({});
    this.onmessage?.({ data: JSON.stringify({ type: 'media.attach', contract_version: 'live-voice.media.v1', binding: this.binding }) });
  }

  send(value) {
    if (typeof value !== 'string') {
      const throughSeq = this.binarySendCount++;
      queueMicrotask(() => this.onmessage?.({
        data: JSON.stringify({
          type: 'media.ack',
          contract_version: 'live-voice.media.v1',
          lease_id: this.binding.lease_id,
          generation: this.binding.generation.value,
          through_seq: throughSeq,
        }),
      }));
      return;
    }
    let control = null;
    try { control = JSON.parse(value); } catch { control = null; }
    if (control?.type !== 'media.detach') return;
    void this.registryFixture.request('route_settled').then(response => {
      if (response.status !== 'route_settled') fail('EOT_STT_BENCHMARK_FIXTURE_FAILED');
      this.onmessage?.({ data: JSON.stringify(control) });
    }).catch(() => this.onerror?.({}));
  }

  close() { this.readyState = 3; }

  emitEndOfTurn(serializeMediaControl) {
    this.onmessage?.({
      data: serializeMediaControl({
        type: 'media.speech_start',
        capability_version: 'media.end_of_turn.v1',
        lease_id: this.binding.lease_id,
        generation: this.binding.generation.value,
        detector: 'server_vad',
        provider_start_ms: 100,
        timing_basis: 'provider_time',
        timing_provenance: 'adapter_derived',
        create_response: false,
        interrupt_response: false,
        business_cancel_count_delta: 0,
      }),
    });
    this.onmessage?.({
      data: serializeMediaControl({
        type: 'media.end_of_turn',
        capability_version: 'media.end_of_turn.v1',
        lease_id: this.binding.lease_id,
        generation: this.binding.generation.value,
        detector: 'server_vad',
        speech_started_observed: true,
        provider_start_ms: 100,
        provider_end_ms: 700,
        timing_basis: 'provider_time',
        timing_provenance: 'adapter_derived',
        create_response: false,
        interrupt_response: false,
        business_cancel_count_delta: 0,
      }),
    });
  }
}

function mediaBinding(params) {
  return {
    lease_id: 'media-lease-1',
    authority_evidence_id: 'media-authority-1',
    connection_id: 'connection-1',
    connection_epoch: 0,
    session_id: params.session_id,
    media_session_id: 'media-session-1',
    interaction_id: params.interaction_id,
    track_id: params.track_id,
    correlation_id: params.correlation_id,
    direction: 'uplink',
    generation: { kind: 'capture', id: params.capture_id, value: params.capture_generation },
    frame_format: {
      sample_rate_hz: params.sample_rate_hz,
      samples_per_channel: 960,
      encoding: 'pcm_f32',
      byte_order: 'little',
      channel_count: 1,
      frame_duration_ms: 20,
    },
    playout: null,
  };
}

function makeLatencyProbe(now, points) {
  let origin = null;
  let roundIndex = 0;
  return {
    beginRound() {
      const seen = new Set();
      let committed = false;
      let finished = false;
      return {
        context: Object.freeze({
          schema_version: 'live-voice.latency-context.v0',
          run_id: 'eot-stt-a1-local',
          profile_id: 'dialogue_no_tool',
          input_case_id: 'eot-stt-settlement',
          round_index: roundIndex++,
        }),
        mark(point, _identity, observation) {
          if (finished || seen.has(point)) return false;
          seen.add(point);
          if (REQUIRED_MARKS.includes(point)) {
            const observed = observation?.monotonic_ms;
            const markedAt = typeof observed === 'number' && Number.isFinite(observed) ? observed : now();
            if (point === 'browser.eot_received') origin = markedAt;
            if (origin !== null) points[point] = rounded(Math.max(0, markedAt - origin));
          }
          return true;
        },
        commit() {
          if (finished || committed) return false;
          committed = true;
          return true;
        },
        finish() {
          if (finished || !committed) return null;
          finished = true;
          return Object.freeze({ round_index: roundIndex - 1, terminal_outcome: 'completed', marks: [] });
        },
        abandon() { finished = true; return true; },
      };
    },
    async exportBatch() {},
  };
}

async function startCaptureWithFrame(owner, environment) {
  const starting = owner.startCapture({
    session_id: 'session-1',
    interaction_id: 'interaction-1',
    correlation_id: 'correlation-1',
    activation_id: 'activation-1',
    activation_generation: 1,
    locale: 'en-US',
  });
  for (let turn = 0; turn < 100 && typeof environment.worklet?.port.onmessage !== 'function'; turn += 1) {
    await new Promise(resolve => setImmediate(resolve));
  }
  if (typeof environment.worklet?.port.onmessage !== 'function') fail('EOT_STT_BENCHMARK_CAPTURE_FAILED');
  await new Promise(resolve => setImmediate(resolve));
  environment.worklet.port.onmessage({
    data: {
      kind: 'frame',
      capture_generation: environment.worklet.captureGeneration,
      seq: 0,
      sample_rate_hz: 48_000,
      sample_cursor: 0,
      context_time_s: 0,
      samples: new Float32Array(960).fill(0.25),
    },
  });
  await starting;
}

async function runProductAttempt(pythonExecutable, fixture, attemptIndex) {
  const registryFixture = new JsonLineRegistryFixture(pythonExecutable, fixture.localSettlementMs, fixture.providerFinalMs);
  let owner = null;
  let cleanupComplete = false;
  let exactResult = false;
  let rpcCount = 0;
  const points = Object.fromEntries(REQUIRED_MARKS.map(point => [point, null]));
  const now = () => performance.now();
  try {
    const [productModule, mediaModule] = await Promise.all([import(PRODUCT_MODULE_URL.href), import(MEDIA_MODULE_URL.href)]);
    const { ProductP1VoiceRouteOwner, PRODUCT_P1_MEDIA_ACTIVATE_METHOD, PRODUCT_P1_MEDIA_CLOSE_METHOD } = productModule;
    const { serializeMediaControl } = mediaModule;
    const opened = await registryFixture.request('open');
    if (opened.status !== 'opened') fail('EOT_STT_BENCHMARK_FIXTURE_FAILED');
    const environment = makeAudioEnvironment();
    let socket = null;
    let binding = null;
    owner = new ProductP1VoiceRouteOwner({
      enabled: true,
      expected_origin: 'https://voice.example.test',
      latency_probe: makeLatencyProbe(now, points),
      latency_monotonic_ms: now,
      audio_environment: environment,
      socket_factory: () => {
        if (binding === null) fail('EOT_STT_BENCHMARK_BINDING_FAILED');
        socket = new BenchmarkMediaSocket(binding, registryFixture);
        queueMicrotask(() => socket.open());
        return socket;
      },
      request: async (method, params) => {
        if (method === PRODUCT_P1_MEDIA_ACTIVATE_METHOD) {
          binding = mediaBinding(params);
          return {
            status: 'active',
            reason_id: 'MEDIA_ROUTE_TICKET_ISSUED',
            subject_id: 'media-subject-1',
            endpoint_path: '/ws/live-voice/media',
            media_ticket: 'P'.repeat(43),
            subprotocol: 'live-voice.media.v1',
            ticket_ttl_ms: 30_000,
            streaming_recognition: true,
            streaming_degradation: null,
            end_of_turn: {
              status: 'active',
              capability_version: 'media.end_of_turn.v1',
              detector: 'server_vad',
              create_response: false,
              interrupt_response: false,
            },
            binding,
            privacy: { raw_audio_persisted: false, raw_audio_logged: false, memory_only: true },
          };
        }
        if (method === 'live_voice.speech.recognize_streaming_result') {
          rpcCount += 1;
          const provider = await registryFixture.request('provider_final');
          if (provider.status !== 'provider_final') fail('EOT_STT_BENCHMARK_FIXTURE_FAILED');
          const response = await registryFixture.request('streaming_result');
          if (response.status !== 'completed' || response.exact_result !== true || response.business_result?.status !== 'completed') {
            fail('EOT_STT_BENCHMARK_FIXTURE_FAILED');
          }
          exactResult = true;
          return response.business_result;
        }
        if (method === PRODUCT_P1_MEDIA_CLOSE_METHOD) {
          cleanupComplete = await registryFixture.close();
          return { status: 'closed', reason_id: 'MEDIA_ROUTE_REVOKED', ...params };
        }
        fail('EOT_STT_BENCHMARK_FORBIDDEN_RPC');
      },
    });
    await startCaptureWithFrame(owner, environment);
    let recognitionPromise = null;
    if (!owner.armEndOfTurn(() => { recognitionPromise = owner.stopAndRecognize(); })) {
      fail('EOT_STT_BENCHMARK_EOT_FAILED');
    }
    socket.emitEndOfTurn(serializeMediaControl);
    for (let turn = 0; turn < 10 && recognitionPromise === null; turn += 1) await Promise.resolve();
    if (recognitionPromise === null) fail('EOT_STT_BENCHMARK_EOT_FAILED');
    const recognition = await recognitionPromise;
    if (recognition.text !== EXPECTED_TEXT) fail('EOT_STT_BENCHMARK_RESULT_FAILED');
    await owner.close();
    owner = null;
    if (!cleanupComplete || REQUIRED_MARKS.some(point => typeof points[point] !== 'number')) {
      fail('EOT_STT_BENCHMARK_ATTEMPT_INCOMPLETE');
    }
    return Object.freeze({
      fixture_id: fixture.id,
      attempt_index: attemptIndex,
      outcome: 'completed',
      marks_ms: Object.freeze({ ...points }),
      rpc_count: rpcCount,
      exact_result: exactResult,
      cleanup_complete: cleanupComplete,
    });
  } catch {
    if (owner !== null) await owner.close().catch(() => undefined);
    await registryFixture.terminate().catch(() => undefined);
    fail('EOT_STT_BENCHMARK_ATTEMPT_FAILED');
  }
}

function compileProductOwner() {
  const tsc = path.join(FRONTEND_ROOT, 'node_modules', '.bin', process.platform === 'win32' ? 'tsc.cmd' : 'tsc');
  execFileSync(tsc, [
    'src/features/live-voice/formal/productP1VoiceRoute.ts',
    '--target', 'ES2020', '--module', 'ES2020', '--moduleResolution', 'Bundler',
    '--rootDir', 'src', '--outDir', 'node_modules/.cache/live-voice-integrated-web',
    '--lib', 'ES2020,DOM', '--skipLibCheck', '--noEmitOnError', '--strict',
    '--noUnusedLocals', '--noUnusedParameters',
  ], { cwd: FRONTEND_ROOT, stdio: 'pipe' });
}

export async function runEotSttProductBenchmark({ runId, gitCommit, attempts, candidate, pythonExecutable }) {
  if (candidate !== 'A1') fail('EOT_STT_BENCHMARK_CANDIDATE_INVALID');
  const measurement = await runEotSttSettlementBenchmark({
    fixtures: FIXTURES,
    attempts,
    candidate: 'A1',
    attempt_runner: (fixture, attemptIndex) => runProductAttempt(pythonExecutable, fixture, attemptIndex),
  });
  return Object.freeze({
    ...measurement,
    run_id: runId,
    git_commit: gitCommit,
    source_state: 'clean',
  });
}

export async function main(argv = process.argv.slice(2)) {
  const args = parseEotSttSettlementBenchmarkArgs(argv);
  const pythonExecutable = await validateEotSttPythonExecutable(args.pythonExecutable);
  const actualCommit = execFileSync('git', ['rev-parse', 'HEAD'], { cwd: FRONTEND_ROOT, encoding: 'utf8' }).trim();
  const status = execFileSync('git', ['status', '--porcelain', '--untracked-files=all'], { cwd: FRONTEND_ROOT, encoding: 'utf8' });
  assertEotSttCleanSource(args.gitCommit, actualCommit, status);
  compileProductOwner();
  const report = await runEotSttProductBenchmark({ ...args, pythonExecutable });
  await writeEotSttSettlementBenchmarkReport(args.output, report);
  process.stdout.write(`${JSON.stringify({ run_id: args.runId, candidate: 'A1' })}\n`);
}

const invokedDirectly = process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;
if (invokedDirectly) {
  main().catch(() => {
    process.stderr.write('EOT_STT_BENCHMARK_FAILED\n');
    process.exitCode = 1;
  });
}

export { FIXTURES };
