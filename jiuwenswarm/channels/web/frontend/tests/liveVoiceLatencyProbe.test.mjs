import assert from 'node:assert/strict';
import test from 'node:test';

import {
  BROWSER_LATENCY_CORE_POINTS,
  LATENCY_PROBE_BATCH_METHOD,
  createBrowserLatencyProbe,
} from '../node_modules/.cache/live-voice-latency-probe/latencyProbe.mjs';

const profiles = ['dialogue_no_tool', 'dialogue_with_tool', 'task_create', 'task_status', 'task_cancel'];

const baseSearch = '?lv_latency_run=run-20260819-a&lv_latency_profile=dialogue_no_tool&lv_latency_case=short-greeting-v1';
const initialIdentity = Object.freeze({ correlation_id: 'corr-1', interaction_id: 'interaction-1' });

function memoryStorage(initial = new Map()) {
  const values = new Map(initial);
  const calls = [];
  return {
    calls,
    values,
    getItem(key) {
      calls.push(['getItem', key]);
      return values.has(key) ? values.get(key) : null;
    },
    setItem(key, value) {
      calls.push(['setItem', key, value]);
      values.set(key, value);
    },
  };
}

function harness(overrides = {}) {
  const storage = overrides.storage ?? memoryStorage();
  const requestCalls = [];
  const ids = [...(overrides.ids ?? ['source-instance-1', 'browser-clock-1', 'batch-1', 'batch-2', 'batch-3'])];
  const clockValues = [...(overrides.clockValues ?? [10, 20, 30, 40, 50, 60, 70])];
  let randomCalls = 0;
  let clockCalls = 0;
  let locationReads = 0;
  const dependencies = {
    enabled: overrides.enabled ?? true,
    get location() {
      locationReads += 1;
      if (overrides.locationError) throw overrides.locationError;
      return { search: overrides.search ?? baseSearch };
    },
    storage,
    monotonicMs() {
      clockCalls += 1;
      if (overrides.clockError) throw overrides.clockError;
      return clockValues.shift() ?? 100;
    },
    randomId() {
      randomCalls += 1;
      if (overrides.randomError) throw overrides.randomError;
      const next = ids.shift() ?? `generated-${randomCalls}`;
      if (next instanceof Error) throw next;
      return next;
    },
    request(method, params) {
      requestCalls.push([method, params]);
      if (overrides.requestError) throw overrides.requestError;
      return overrides.requestResult ?? Promise.resolve({ status: 'written' });
    },
    experimentPoints: overrides.experimentPoints ?? [],
    onBatchSettled: overrides.onBatchSettled,
  };
  return {
    dependencies,
    storage,
    requestCalls,
    counts: () => ({ randomCalls, clockCalls, locationReads }),
  };
}

function finishedBatch(probe, outcome = 'completed') {
  const round = probe.beginRound(initialIdentity);
  assert.equal(round.mark('browser.eot_received', initialIdentity), true);
  const batch = round.finish(outcome);
  assert.notEqual(batch, null);
  return batch;
}

test('feature-off returns null before reading browser, storage, clock, randomness, or transport dependencies', () => {
  let reads = 0;
  const dependencies = {
    enabled: false,
    get location() {
      reads += 1;
      throw new Error('PRIVATE location');
    },
    get storage() {
      reads += 1;
      throw new Error('PRIVATE storage');
    },
    get monotonicMs() {
      reads += 1;
      throw new Error('PRIVATE clock');
    },
    get randomId() {
      reads += 1;
      throw new Error('PRIVATE random');
    },
    get request() {
      reads += 1;
      throw new Error('PRIVATE request');
    },
  };

  assert.equal(createBrowserLatencyProbe(dependencies), null);
  assert.equal(reads, 0);
});

test('batch settlement observer sees only the closed diagnostic receipt after export', async () => {
  const settlements = [];
  const h = harness({
    onBatchSettled(batch, receipt) {
      settlements.push([batch, receipt]);
      throw new Error('observer failures are contained');
    },
    requestResult: Promise.resolve({ status: 'idempotent' }),
  });
  const probe = createBrowserLatencyProbe(h.dependencies);
  const batch = finishedBatch(probe);

  await probe.exportBatch('web_benchmark_session', batch);

  assert.equal(settlements.length, 1);
  assert.equal(settlements[0][0], batch);
  assert.deepEqual(settlements[0][1], { disposition: 'idempotent' });
});

test('malformed or throwing dependency setup fails locally without escaping private content', () => {
  assert.doesNotThrow(() => assert.equal(createBrowserLatencyProbe(null), null));
  assert.doesNotThrow(() =>
    assert.equal(
      createBrowserLatencyProbe({
        get enabled() {
          throw new Error('PRIVATE feature dependency');
        },
      }),
      null,
    ),
  );
});

test('query selector accepts every fixed profile and ignores unrelated application query keys', () => {
  for (const profile of profiles) {
    const h = harness({ search: `?project=demo&lv_latency_run=run-a&lv_latency_profile=${profile}&lv_latency_case=case-a&tab=agent` });
    const probe = createBrowserLatencyProbe(h.dependencies);
    assert.notEqual(probe, null);
    const round = probe.beginRound(initialIdentity);
    assert.deepEqual(round.context, {
      schema_version: 'live-voice.latency-context.v0',
      run_id: 'run-a',
      profile_id: profile,
      input_case_id: 'case-a',
      round_index: 0,
    });
  }
});

test('query selector rejects missing, duplicate, empty, sensitive, overlong, malformed, and unknown values without storage or transport', () => {
  const invalidSearches = [
    '?lv_latency_run=run-a&lv_latency_profile=dialogue_no_tool',
    '?lv_latency_run=run-a&lv_latency_run=run-b&lv_latency_profile=dialogue_no_tool&lv_latency_case=case-a',
    '?lv_latency_run=&lv_latency_profile=dialogue_no_tool&lv_latency_case=case-a',
    '?lv_latency_run=PRIVATE_TRANSCRIPT_SENTINEL&lv_latency_profile=dialogue_no_tool&lv_latency_case=case-a',
    `?lv_latency_run=${'a'.repeat(257)}&lv_latency_profile=dialogue_no_tool&lv_latency_case=case-a`,
    '?lv_latency_run=run-a&lv_latency_profile=dialogue_no_tool&lv_latency_case=%ED%A0%80',
    '?lv_latency_run=run-a&lv_latency_profile=unknown&lv_latency_case=case-a',
    '?lv_latency_run=../escape&lv_latency_profile=dialogue_no_tool&lv_latency_case=case-a',
  ];

  for (const search of invalidSearches) {
    const h = harness({ search });
    assert.equal(createBrowserLatencyProbe(h.dependencies), null);
    assert.equal(h.storage.calls.length, 0);
    assert.equal(h.requestCalls.length, 0);
    assert.equal(h.counts().randomCalls, 0);
  }
});

test('round admission assigns contiguous 0 and 1 only after the prior provisional round commits', () => {
  const storage = memoryStorage();
  const firstHarness = harness({ storage, ids: ['source-a', 'clock-a', 'batch-a'] });
  const secondHarness = harness({ storage, ids: ['source-b', 'clock-b', 'batch-b'] });
  const first = createBrowserLatencyProbe(firstHarness.dependencies);
  const second = createBrowserLatencyProbe(secondHarness.dependencies);

  const firstRound = first.beginRound(initialIdentity);
  assert.equal(firstRound.context.round_index, 0);
  assert.equal(storage.values.size, 0);
  assert.equal(firstRound.commit(), true);
  assert.equal(second.beginRound(initialIdentity).context.round_index, 1);
  assert.equal(storage.values.size, 1);
  assert.equal([...storage.values.values()][0], '1');
});

test('five-profile reload cycles retain thirty contiguous real attempts while every unused successor is abandoned', () => {
  const storage = memoryStorage();
  const admitted = new Map(profiles.map(profile => [profile, []]));

  for (let attempt = 0; attempt < 30; attempt += 1) {
    for (const profile of profiles) {
      const currentHarness = harness({
        storage,
        search: `?lv_latency_run=run-cycle&lv_latency_profile=${profile}&lv_latency_case=case-${profile}`,
        ids: [`source-${profile}-${attempt}`, `clock-${profile}-${attempt}`, `batch-${profile}-${attempt}`, `unused-${profile}-${attempt}`],
      });
      const currentProbe = createBrowserLatencyProbe(currentHarness.dependencies);
      const current = currentProbe.beginRound(initialIdentity);
      assert.equal(current.context.round_index, attempt);
      assert.equal(current.commit(), true);
      assert.equal(current.mark('browser.eot_received', initialIdentity), true);
      admitted.get(profile).push(current.finish('completed').round_index);

      const unusedSuccessor = currentProbe.beginRound(initialIdentity);
      assert.equal(unusedSuccessor.context.round_index, attempt + 1);
      assert.equal(unusedSuccessor.mark('browser.capture_start_requested', initialIdentity), true);
      assert.equal(unusedSuccessor.abandon(), true);
      assert.equal(unusedSuccessor.finish('cancelled'), null);
    }
  }

  for (const profile of profiles) {
    assert.deepEqual(
      admitted.get(profile),
      Array.from({ length: 30 }, (_value, index) => index),
    );
  }
  assert.deepEqual([...storage.values.values()], ['30', '30', '30', '30', '30']);
});

test('round allocator accepts 255 then fails inert at 256 without randomness, clocks, or transport', () => {
  const storage = memoryStorage();
  const first = harness({ storage });
  const firstProbe = createBrowserLatencyProbe(first.dependencies);
  storage.values.clear();
  const warmup = firstProbe.beginRound({ correlation_id: '', interaction_id: 'interaction-1' });
  assert.equal(warmup.finish('completed'), null);
  assert.equal(storage.calls.length, 0);

  // Obtain the opaque tuple key through one ordinary allocation, then set its next value.
  const allocated = firstProbe.beginRound(initialIdentity);
  assert.equal(allocated.context.round_index, 0);
  const tupleKey = storage.calls.find(call => call[0] === 'getItem')[1];
  assert.equal(allocated.abandon(), true);
  storage.values.set(tupleKey, '255');
  const atLimit = firstProbe.beginRound(initialIdentity);
  assert.equal(atLimit.context.round_index, 255);
  assert.equal(atLimit.commit(), true);
  assert.equal(storage.values.get(tupleKey), '256');

  const before = first.counts();
  const exhausted = firstProbe.beginRound(initialIdentity);
  assert.equal(exhausted.mark('browser.eot_received', initialIdentity), false);
  assert.equal(exhausted.finish('completed'), null);
  assert.deepEqual(first.counts(), before);
  assert.equal(first.requestCalls.length, 0);
});

test('corrupt, unsafe, throwing, and conflicting storage returns an inert round without leaking failure content', () => {
  const invalidStates = ['-1', '01', '1.5', '257', '9007199254740992', 'PRIVATE_TRANSCRIPT_SENTINEL'];
  for (const state of invalidStates) {
    const storage = memoryStorage();
    const h = harness({ storage });
    const probe = createBrowserLatencyProbe(h.dependencies);
    storage.getItem = key => state;
    const before = h.counts();
    const round = probe.beginRound(initialIdentity);
    assert.equal(round.finish('unknown'), null);
    assert.equal(h.counts().randomCalls, before.randomCalls);
  }

  for (const storage of [
    {
      getItem() {
        throw new Error('PRIVATE read');
      },
      setItem() {},
    },
    {
      getItem() {
        return null;
      },
      setItem() {
        throw new Error('PRIVATE write');
      },
    },
    {
      getItem() {
        return null;
      },
      setItem() {},
    },
  ]) {
    const h = harness({ storage });
    const probe = createBrowserLatencyProbe(h.dependencies);
    const round = probe.beginRound(initialIdentity);
    assert.equal(round.finish('failed'), null);
    assert.equal(h.requestCalls.length, 0);
  }
});

test('failed batch randomness consumes no provisional index so the next active round remains contiguous', () => {
  const h = harness({
    ids: ['source-instance-1', 'browser-clock-1', new Error('PRIVATE random failure'), 'batch-after-recovery'],
  });
  const probe = createBrowserLatencyProbe(h.dependencies);

  assert.equal(probe.beginRound(initialIdentity).finish('failed'), null);
  const recovered = probe.beginRound(initialIdentity);
  assert.equal(recovered.context.round_index, 0);
  assert.notEqual(recovered.finish('completed'), null);
});

test('exact golden batch mirrors the Python browser contract and is deeply frozen', () => {
  const h = harness({ clockValues: [12.5, 18.75] });
  const probe = createBrowserLatencyProbe(h.dependencies);
  const round = probe.beginRound(initialIdentity);
  assert.equal(round.mark('browser.eot_received', initialIdentity), true);
  assert.equal(
    round.mark(
      'browser.playout_first_frame_started_estimate',
      {
        ...initialIdentity,
        activation_id: 'activation-1',
        activation_generation: 2,
        turn_id: 'turn-1',
        response_id: 'response-1',
        response_generation: 3,
        task_id: 'task-1',
      },
      { uncertainty_ms: 1.25, outcome: 'observed', reason_code: null },
    ),
    true,
  );
  const batch = round.finish('completed');

  assert.deepEqual(batch, {
    schema_version: 'live-voice.latency-batch.v0',
    batch_id: 'batch-1',
    run_id: 'run-20260819-a',
    profile_id: 'dialogue_no_tool',
    input_case_id: 'short-greeting-v1',
    round_index: 0,
    source_instance_id: 'source-instance-1',
    component: 'browser',
    phase: 'browser_round',
    terminal_outcome: 'completed',
    marks: [
      {
        schema_version: 'live-voice.latency-probe.v0',
        run_id: 'run-20260819-a',
        profile_id: 'dialogue_no_tool',
        input_case_id: 'short-greeting-v1',
        round_index: 0,
        source_instance_id: 'source-instance-1',
        mark_index: 0,
        component: 'browser',
        clock_domain_id: 'browser-clock-1',
        point: 'browser.eot_received',
        monotonic_ms: 12.5,
        uncertainty_ms: null,
        outcome: 'observed',
        reason_code: null,
        correlation_id: 'corr-1',
        interaction_id: 'interaction-1',
        activation_id: null,
        activation_generation: null,
        turn_id: null,
        response_id: null,
        response_generation: null,
        task_id: null,
      },
      {
        schema_version: 'live-voice.latency-probe.v0',
        run_id: 'run-20260819-a',
        profile_id: 'dialogue_no_tool',
        input_case_id: 'short-greeting-v1',
        round_index: 0,
        source_instance_id: 'source-instance-1',
        mark_index: 1,
        component: 'browser',
        clock_domain_id: 'browser-clock-1',
        point: 'browser.playout_first_frame_started_estimate',
        monotonic_ms: 18.75,
        uncertainty_ms: 1.25,
        outcome: 'observed',
        reason_code: null,
        correlation_id: 'corr-1',
        interaction_id: 'interaction-1',
        activation_id: 'activation-1',
        activation_generation: 2,
        turn_id: 'turn-1',
        response_id: 'response-1',
        response_generation: 3,
        task_id: 'task-1',
      },
    ],
  });
  assert.equal(Object.isFrozen(batch), true);
  assert.equal(Object.isFrozen(batch.marks), true);
  assert.equal(
    batch.marks.every(mark => Object.isFrozen(mark)),
    true,
  );
});

test('explicit scheduling times are retained exactly without sampling the recorder clock', () => {
  const h = harness({ clockValues: [999] });
  const probe = createBrowserLatencyProbe(h.dependencies);
  const round = probe.beginRound(initialIdentity);

  assert.equal(round.mark('browser.playout_first_frame_scheduled', initialIdentity, { monotonic_ms: 123.5 }), true);
  assert.equal(
    round.mark('browser.playout_first_frame_started_estimate', initialIdentity, {
      monotonic_ms: 456.75,
      uncertainty_ms: 2.5,
    }),
    true,
  );

  const batch = round.finish('completed');
  assert.deepEqual(
    batch.marks.map(mark => [mark.point, mark.monotonic_ms, mark.uncertainty_ms]),
    [
      ['browser.playout_first_frame_scheduled', 123.5, null],
      ['browser.playout_first_frame_started_estimate', 456.75, 2.5],
    ],
  );
  assert.equal(h.counts().clockCalls, 0);
});

test('invalid explicit times and accessor observations are inert without clock or mark mutation', () => {
  const h = harness({ clockValues: [999] });
  const probe = createBrowserLatencyProbe(h.dependencies);
  const round = probe.beginRound(initialIdentity);

  assert.equal(round.mark('browser.eot_received', initialIdentity, { monotonic_ms: -1 }), false);
  assert.equal(round.mark('browser.eot_received', initialIdentity, { monotonic_ms: Number.NaN }), false);
  assert.equal(round.mark('browser.eot_received', initialIdentity, { monotonic_ms: null }), false);
  assert.equal(round.mark('browser.eot_received', initialIdentity, { monotonic_ms: 'PRIVATE' }), false);
  let getterReads = 0;
  const accessor = {};
  Object.defineProperty(accessor, 'monotonic_ms', {
    enumerable: true,
    get() {
      getterReads += 1;
      return 42;
    },
  });
  assert.equal(round.mark('browser.eot_received', initialIdentity, accessor), false);
  assert.equal(getterReads, 0);
  assert.equal(h.counts().clockCalls, 0);
  assert.deepEqual(round.finish('unknown').marks, []);
});

test('explicit-time marks preserve busy reentrancy and one-shot closure', () => {
  const h = harness();
  const probe = createBrowserLatencyProbe(h.dependencies);
  const round = probe.beginRound(initialIdentity);
  const observation = {
    monotonic_ms: 20,
    outcome: 'observed',
    reason_code: null,
  };

  assert.equal(round.mark('browser.eot_received', initialIdentity, observation), true);
  const batch = round.finish('completed');
  assert.equal(round.mark('browser.stt_final_received', initialIdentity, { monotonic_ms: 30 }), false);
  assert.equal(round.finish('failed'), null);
  assert.equal(batch.marks[0].monotonic_ms, 20);
});

test('identity enriches monotonically and rejects unknown, private, replacement, and unsafe generation patches without consuming a mark', () => {
  const h = harness();
  const probe = createBrowserLatencyProbe(h.dependencies);
  const round = probe.beginRound(initialIdentity);
  const enriched = { ...initialIdentity, activation_id: 'activation-1', activation_generation: 0 };

  assert.equal(round.mark('browser.eot_received', enriched), true);
  assert.equal(round.mark('browser.stt_final_received', { ...enriched, activation_id: 'activation-2' }), false);
  assert.equal(round.mark('browser.stt_final_received', { ...enriched, extra: 'PRIVATE_TRANSCRIPT_SENTINEL' }), false);
  assert.equal(round.mark('browser.stt_final_received', { ...enriched, turn_id: { text: 'PRIVATE' } }), false);
  assert.equal(round.mark('browser.stt_final_received', { ...enriched, response_generation: -1 }), false);
  assert.equal(round.mark('browser.stt_final_received', enriched), true);
  assert.deepEqual(
    round.finish('completed').marks.map(mark => mark.mark_index),
    [0, 1],
  );
  assert.equal(h.counts().clockCalls, 2);
});

test('closed point and observation validation rejects duplicates, arbitrary experiments, unknown keys, bad uncertainty, and private content', () => {
  const h = harness({ experimentPoints: ['experiment.buffer-tuning.ready'] });
  const probe = createBrowserLatencyProbe(h.dependencies);
  const round = probe.beginRound(initialIdentity);

  assert.equal(round.mark('browser.eot_received', initialIdentity), true);
  assert.equal(round.mark('browser.eot_received', initialIdentity), false);
  assert.equal(round.mark('experiment.not-declared', initialIdentity), false);
  assert.equal(round.mark('experiment.buffer-tuning.ready', initialIdentity), true);
  assert.equal(round.mark('browser.stt_final_received', initialIdentity, { text: 'PRIVATE_TRANSCRIPT_SENTINEL' }), false);
  assert.equal(round.mark('browser.stt_final_received', initialIdentity, { uncertainty_ms: 1 }), false);
  assert.equal(round.mark('browser.playout_first_frame_started_estimate', initialIdentity, { uncertainty_ms: Number.NaN }), false);
  assert.equal(round.mark('browser.playout_first_frame_started_estimate', initialIdentity, { outcome: 'success' }), false);
  assert.equal(round.mark('browser.playout_first_frame_started_estimate', initialIdentity, { reason_code: 'PRIVATE' }), false);
  assert.deepEqual(
    round.finish('unknown').marks.map(mark => mark.point),
    ['browser.eot_received', 'experiment.buffer-tuning.ready'],
  );
});

test('streaming result waiter points are core points with closed duplicate and private-observation validation', () => {
  assert.equal(BROWSER_LATENCY_CORE_POINTS.includes('browser.streaming_result_request_started'), true);
  assert.equal(BROWSER_LATENCY_CORE_POINTS.includes('browser.streaming_result_returned'), true);

  const h = harness();
  const probe = createBrowserLatencyProbe(h.dependencies);
  const round = probe.beginRound(initialIdentity);

  assert.equal(round.mark('browser.streaming_result_request_started', initialIdentity), true);
  assert.equal(round.mark('browser.streaming_result_request_started', initialIdentity), false);
  assert.equal(round.mark('browser.streaming_result_returned', initialIdentity, { text: 'PRIVATE_TRANSCRIPT_SENTINEL' }), false);
  assert.equal(round.mark('browser.streaming_result_returned', initialIdentity), true);
  assert.deepEqual(
    round.finish('completed').marks.map(mark => mark.point),
    ['browser.streaming_result_request_started', 'browser.streaming_result_returned'],
  );
});

test('slot 63 is reserved for one capacity observation and all later operations are inert', () => {
  const experimentPoints = Array.from({ length: 64 }, (_, index) => `experiment.capacity-${index}`);
  const h = harness({ experimentPoints, clockValues: Array.from({ length: 70 }, (_, index) => index) });
  const probe = createBrowserLatencyProbe(h.dependencies);
  const round = probe.beginRound(initialIdentity);
  const points = [...BROWSER_LATENCY_CORE_POINTS, ...experimentPoints].slice(0, 64);

  for (const point of points.slice(0, 63)) assert.equal(round.mark(point, initialIdentity), true);
  assert.equal(round.mark(points[63], initialIdentity), false);
  assert.equal(round.mark('browser.eot_received', initialIdentity), false);
  const batch = round.finish('unknown');
  assert.equal(batch.marks.length, 64);
  assert.deepEqual(batch.marks[63], {
    schema_version: 'live-voice.latency-probe.v0',
    run_id: 'run-20260819-a',
    profile_id: 'dialogue_no_tool',
    input_case_id: 'short-greeting-v1',
    round_index: 0,
    source_instance_id: 'source-instance-1',
    mark_index: 63,
    component: 'browser',
    clock_domain_id: 'browser-clock-1',
    point: 'probe.capacity',
    monotonic_ms: 63,
    uncertainty_ms: null,
    outcome: 'unknown',
    reason_code: 'CAPACITY',
    correlation_id: 'corr-1',
    interaction_id: 'interaction-1',
    activation_id: null,
    activation_generation: null,
    turn_id: null,
    response_id: null,
    response_generation: null,
    task_id: null,
  });
});

test('finish accepts one closed terminal outcome, freezes once, and leaves marks and finishes inert', () => {
  const h = harness();
  const probe = createBrowserLatencyProbe(h.dependencies);
  const round = probe.beginRound(initialIdentity);

  assert.equal(round.finish('success'), null);
  assert.equal(round.mark('browser.eot_received', initialIdentity), true);
  const batch = round.finish('cancelled');
  assert.notEqual(batch, null);
  assert.equal(round.finish('completed'), null);
  assert.equal(round.mark('browser.stt_final_received', initialIdentity), false);
  assert.equal(batch.terminal_outcome, 'cancelled');
});

test('export validates complete provenance and sends one exact RPC envelope at most once', async () => {
  const h = harness();
  const probe = createBrowserLatencyProbe(h.dependencies);
  const batch = finishedBatch(probe);

  await probe.exportBatch('session-1', batch);
  await probe.exportBatch('session-1', batch);
  await probe.exportBatch('PRIVATE_SESSION_TOKEN', finishedBatch(probe));
  await probe.exportBatch('session-1', structuredClone(batch));

  assert.equal(h.requestCalls.length, 1);
  assert.equal(h.requestCalls[0][0], LATENCY_PROBE_BATCH_METHOD);
  assert.deepEqual(h.requestCalls[0][1], { session_id: 'session-1', batch });
});

test('synchronous and asynchronous export failures are private, contained, and never retried', async () => {
  for (const requestResult of [
    { requestError: new Error('PRIVATE sync transport failure') },
    { requestResult: Promise.reject(new Error('PRIVATE async transport failure')) },
  ]) {
    const settlements = [];
    const h = harness({
      ...requestResult,
      onBatchSettled(batch, receipt) {
        settlements.push([batch, receipt]);
      },
    });
    const probe = createBrowserLatencyProbe(h.dependencies);
    const batch = finishedBatch(probe);
    await assert.doesNotReject(probe.exportBatch('session-1', batch));
    await assert.doesNotReject(probe.exportBatch('session-1', batch));
    assert.equal(h.requestCalls.length, 1);
    assert.deepEqual(settlements, [[batch, { disposition: 'unknown' }]]);
  }
});

test('invalid initial identity yields an inert round before storage, batch randomness, clocks, or transport', () => {
  const h = harness();
  const probe = createBrowserLatencyProbe(h.dependencies);
  const before = h.counts();
  const round = probe.beginRound({ correlation_id: 'corr-1', interaction_id: 'PRIVATE_TRANSCRIPT_SENTINEL' });

  assert.equal(round.mark('browser.eot_received', initialIdentity), false);
  assert.equal(round.finish('failed'), null);
  assert.equal(h.storage.calls.length, 0);
  assert.deepEqual(h.counts(), before);
  assert.equal(h.requestCalls.length, 0);
});

test('unknown storage write outcomes permanently latch one probe allocator inert', () => {
  const adapters = [
    (() => {
      let value = null;
      return {
        getItem() {
          return value;
        },
        setItem(_key, next) {
          value = next;
          throw new Error('PRIVATE write-then-throw');
        },
      };
    })(),
    (() => {
      let value = null;
      let reads = 0;
      return {
        getItem() {
          reads += 1;
          if (reads === 3) return 'conflicting-next-index';
          return value;
        },
        setItem(_key, next) {
          value = next;
        },
      };
    })(),
  ];

  adapters.forEach(storage => {
    const h = harness({ storage });
    const probe = createBrowserLatencyProbe(h.dependencies);
    const failed = probe.beginRound(initialIdentity);
    assert.equal(failed.finish('failed'), null);
    const afterFailure = h.counts();

    const later = probe.beginRound(initialIdentity);
    assert.equal(later.mark('browser.eot_received', initialIdentity), false);
    assert.equal(later.finish('completed'), null);
    assert.deepEqual(h.counts(), afterFailure);
    assert.equal(h.requestCalls.length, 0);
  });
});

test('safe pre-write admission failure releases the provisional slot for a later round', () => {
  const storage = memoryStorage();
  const ordinaryGet = storage.getItem.bind(storage);
  let reads = 0;
  storage.getItem = key => {
    reads += 1;
    if (reads === 2) throw new Error('PRIVATE pre-write read failure');
    return ordinaryGet(key);
  };
  const h = harness({ storage });
  const probe = createBrowserLatencyProbe(h.dependencies);

  assert.equal(probe.beginRound(initialIdentity).finish('failed'), null);
  storage.getItem = ordinaryGet;
  const recovered = probe.beginRound(initialIdentity);
  assert.equal(recovered.context.round_index, 0);
  assert.equal(recovered.commit(), true);
  assert.notEqual(recovered.finish('completed'), null);
});

test('monotonic clock reentrancy cannot insert a conflicting mark or finish an in-flight mark', () => {
  let markRound;
  let nestedMarkResult = null;
  let markReentered = false;
  const markHarness = harness();
  markHarness.dependencies.monotonicMs = () => {
    if (!markReentered) {
      markReentered = true;
      nestedMarkResult = markRound.mark('browser.stt_final_received', {
        ...initialIdentity,
        activation_id: 'activation-conflict',
      });
    }
    return 10;
  };
  const markProbe = createBrowserLatencyProbe(markHarness.dependencies);
  markRound = markProbe.beginRound(initialIdentity);
  assert.equal(markRound.mark('browser.eot_received', { ...initialIdentity, activation_id: 'activation-authoritative' }), true);
  assert.equal(nestedMarkResult, false);
  const markedBatch = markRound.finish('completed');
  assert.deepEqual(
    markedBatch.marks.map(mark => [mark.point, mark.mark_index, mark.activation_id]),
    [['browser.eot_received', 0, 'activation-authoritative']],
  );

  let finishRound;
  let nestedFinishResult = 'not-called';
  let finishReentered = false;
  const finishHarness = harness();
  finishHarness.dependencies.monotonicMs = () => {
    if (!finishReentered) {
      finishReentered = true;
      nestedFinishResult = finishRound.finish('failed');
    }
    return 20;
  };
  const finishProbe = createBrowserLatencyProbe(finishHarness.dependencies);
  finishRound = finishProbe.beginRound(initialIdentity);
  assert.equal(finishRound.mark('browser.eot_received', initialIdentity), true);
  assert.equal(nestedFinishResult, null);
  const finishedBatch = finishRound.finish('completed');
  assert.equal(finishedBatch.terminal_outcome, 'completed');
  assert.deepEqual(
    finishedBatch.marks.map(mark => mark.point),
    ['browser.eot_received'],
  );
});

test('identity and observation inputs require own plain data properties and never evaluate accessors', () => {
  const inherited = Object.create(initialIdentity);
  const inheritedHarness = harness();
  const inheritedProbe = createBrowserLatencyProbe(inheritedHarness.dependencies);
  assert.equal(inheritedProbe.beginRound(inherited).finish('failed'), null);
  assert.equal(inheritedHarness.storage.calls.length, 0);

  let identityGetterReads = 0;
  const accessorIdentity = {};
  Object.defineProperties(accessorIdentity, {
    correlation_id: {
      enumerable: true,
      get() {
        identityGetterReads += 1;
        return identityGetterReads === 1 ? 'corr-1' : 'PRIVATE_CHANGED';
      },
    },
    interaction_id: { enumerable: true, value: 'interaction-1' },
  });
  const accessorHarness = harness();
  const accessorProbe = createBrowserLatencyProbe(accessorHarness.dependencies);
  assert.equal(accessorProbe.beginRound(accessorIdentity).finish('failed'), null);
  assert.equal(identityGetterReads, 0);
  assert.equal(accessorHarness.storage.calls.length, 0);

  const proxyIdentity = new Proxy(
    { ...initialIdentity },
    {
      getOwnPropertyDescriptor() {
        throw new Error('PRIVATE descriptor trap');
      },
    },
  );
  const proxyHarness = harness();
  const proxyProbe = createBrowserLatencyProbe(proxyHarness.dependencies);
  assert.equal(proxyProbe.beginRound(proxyIdentity).finish('failed'), null);
  assert.equal(proxyHarness.storage.calls.length, 0);

  const symbolHarness = harness();
  const symbolProbe = createBrowserLatencyProbe(symbolHarness.dependencies);
  assert.equal(symbolProbe.beginRound({ ...initialIdentity, [Symbol('private-metadata')]: 'PRIVATE' }).finish('failed'), null);
  assert.equal(symbolHarness.storage.calls.length, 0);

  let observationGetterReads = 0;
  const observation = {};
  Object.defineProperty(observation, 'outcome', {
    enumerable: true,
    get() {
      observationGetterReads += 1;
      return observationGetterReads === 1 ? 'observed' : 'failed';
    },
  });
  const markHarness = harness();
  const markProbe = createBrowserLatencyProbe(markHarness.dependencies);
  const round = markProbe.beginRound(initialIdentity);
  const before = markHarness.counts();
  assert.equal(round.mark('browser.eot_received', initialIdentity, observation), false);
  assert.equal(observationGetterReads, 0);
  assert.equal(markHarness.counts().clockCalls, before.clockCalls);
  assert.deepEqual(round.finish('unknown').marks, []);
});

test('round context is non-shadowable and export remains bound to private allocated provenance', async () => {
  const h = harness();
  const probe = createBrowserLatencyProbe(h.dependencies);
  const round = probe.beginRound(initialIdentity);
  const replacement = Object.freeze({ ...round.context, round_index: 99 });

  assert.throws(() => {
    round.context = replacement;
  }, TypeError);
  assert.throws(() => Object.defineProperty(round, 'context', { value: replacement }), TypeError);
  assert.equal(round.context.round_index, 0);

  assert.equal(round.mark('browser.eot_received', initialIdentity), true);
  const batch = round.finish('completed');
  await probe.exportBatch('session-1', { ...batch, round_index: 99 });
  assert.equal(h.requestCalls.length, 0);
  await probe.exportBatch('session-1', batch);
  assert.equal(h.requestCalls.length, 1);
  assert.equal(h.requestCalls[0][1].batch.round_index, 0);
});
