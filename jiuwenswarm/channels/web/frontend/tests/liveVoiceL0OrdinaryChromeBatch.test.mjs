import assert from 'node:assert/strict';
import test from 'node:test';
import { pathToFileURL } from 'node:url';
import path from 'node:path';

const moduleUrl = pathToFileURL(
  path.resolve(process.cwd(), 'node_modules/.cache/live-voice-l0-ordinary-batch/l0OrdinaryChromeBatch.mjs')
).href;

test('ordinary batch query is exact loopback-only and feature-off is inert', async () => {
  const batch = await import(moduleUrl);
  assert.equal(batch.parseOrdinaryChromeBatchConfig(''), null);
  assert.equal(batch.parseOrdinaryChromeBatchConfig('?live_voice_l0_batch=1&live_voice_l0_coordinator_port=80&live_voice_l0_nonce=0'.repeat(32)), null);
  assert.equal(batch.parseOrdinaryChromeBatchConfig('?live_voice_l0_batch=1&live_voice_l0_coordinator_url=https://example.com&live_voice_l0_nonce=0123456789abcdef0123456789abcdef'), null, 'an arbitrary URL must not become coordinator authority');
  assert.deepEqual(
    batch.parseOrdinaryChromeBatchConfig('?live_voice_l0_batch=1&live_voice_l0_coordinator_port=9233&live_voice_l0_nonce=0123456789abcdef0123456789abcdef'),
    {
      base_url: 'http://127.0.0.1:9233',
      nonce: '0123456789abcdef0123456789abcdef',
    },
  );
});

test('per-unit reducer reports exact gaps waits waste and total without small-sample p95', async () => {
  const { reduceProductTtsUnitLatency } = await import(moduleUrl);
  const record = (unitSeq, milestone, monotonicMs) => ({
    milestone,
    binding: {
      session_id: 'session-1', interaction_id: 'interaction-1',
      response_id: 'response-1', response_generation: 0,
      unit_id: unitSeq === null ? null : `unit-${unitSeq}`, unit_seq: unitSeq,
    },
    observation: { monotonic_ms: monotonicMs },
  });
  const records = [
    record(0, 'unit_tts_requested', 0), record(0, 'unit_prepared', 30),
    record(0, 'unit_playout_started', 50), record(0, 'unit_playout_completed', 100),
    record(0, 'unit_acknowledged', 105),
    record(1, 'unit_tts_requested', 60), record(1, 'unit_prepared', 130),
    record(1, 'unit_playout_started', 140), record(1, 'unit_playout_completed', 200),
    record(1, 'unit_acknowledged', 205),
    record(2, 'unit_tts_requested', 150), record(2, 'unit_prepared', 200),
    record(2, 'unit_playout_started', 210), record(2, 'unit_playout_completed', 300),
    record(2, 'unit_acknowledged', 305),
    record(3, 'unit_tts_requested', 220), record(3, 'unit_prepared', 250),
  ];
  assert.deepEqual(reduceProductTtsUnitLatency(records), {
    unit_count: 4,
    request_count: 4,
    cancelled_unit_count: 1,
    wasted_prefetch_count: 1,
    prefix_end_to_tail_start_ms: 40,
    inter_unit_gap_ms: [40, 10],
    inter_unit_gap_max_ms: 40,
    inter_unit_gap_p95_ms: null,
    prepared_wait_ms: [20, 10, 10],
    total_response_playout_ms: 250,
  });
  const population = [];
  let priorCompleted = 10;
  population.push(record(0, 'unit_playout_started', 0), record(0, 'unit_playout_completed', priorCompleted));
  for (let seq = 1; seq <= 20; seq += 1) {
    const started = priorCompleted + seq - 1;
    priorCompleted = started + 10;
    population.push(
      record(seq, 'unit_prepared', Math.max(0, started - 1)),
      record(seq, 'unit_playout_started', started),
      record(seq, 'unit_playout_completed', priorCompleted),
    );
  }
  assert.equal(reduceProductTtsUnitLatency(population).inter_unit_gap_p95_ms, 18);
  assert.throws(
    () => reduceProductTtsUnitLatency([
      record(0, 'unit_prepared', 20),
      record(0, 'unit_playout_started', 19),
    ]),
    /clocks are contradictory/,
  );
});

test('one gesture drives warm-up and a complete first-audio sample without an operator verdict', async () => {
  const batch = await import(moduleUrl);
  const labels = {
    profile_id: 'ordinary-chrome-prerecorded-warm',
    scenario_id: 'short-no-tool-zh',
    sample_index: 0,
    temperature: 'warm',
    evidence_source: 'prerecorded',
  };
  let voiceState = { p1_status: 'idle', text_status: 'idle', recovery_diagnostic: null };
  let sampleStage = 0;
  let playCount = 0;
  let configured = false;
  let records = [];
  let sessionReads = 0;
  const expectedCaptureStreamFactory = async () => ({ injected: true });
  let installedCaptureStreamFactory = null;
  const requests = [];
  const progress = [];
  const measurement = {
    configure(value) {
      assert.deepEqual(value, labels);
      configured = true;
      return true;
    },
    disable() {
      configured = false;
      records = [];
    },
    clear() {
      records = [];
    },
    snapshot() {
      return {
        enabled: true,
        configured,
        accepted_records: records.length,
        dropped_records: 0,
        records,
      };
    },
  };
  const controller = new batch.OrdinaryChromeL0BatchController(
    {
      base_url: 'http://127.0.0.1:9233',
      nonce: '0123456789abcdef0123456789abcdef',
    },
    {
      getControl: () => ({
        async start() { voiceState = { ...voiceState, p1_status: 'capturing' }; },
        async stop() { voiceState = { ...voiceState, p1_status: 'idle' }; },
        setL0CaptureStreamFactory(factory) { installedCaptureStreamFactory = factory; },
      }),
      getState: () => voiceState,
      getConnected: () => true,
      measurement: () => measurement,
      player: {
        async unlock() {},
        captureStreamFactory() { return expectedCaptureStreamFactory; },
        async play(fixture) {
          assert.equal(fixture, 'short');
          playCount += 1;
          sampleStage = 0;
        },
        async close() {},
      },
      async sleep() {
        sampleStage += 1;
        if (playCount === 1) {
          voiceState = { ...voiceState, p1_status: sampleStage === 1 ? 'playing' : 'capturing' };
        } else if (playCount === 2) {
          if (sampleStage === 1) records = [{ milestone: 'webaudio_actually_started' }];
          if (sampleStage === 2) records = [
            { milestone: 'webaudio_actually_started' },
            { milestone: 'playout_completed' },
          ];
        }
      },
      now: (() => { let value = 0; return () => ++value; })(),
      onProgress: value => progress.push(value),
      async request(pathname, init) {
        requests.push([pathname, init]);
        if (pathname === '/v1/session') {
          sessionReads += 1;
          return {
            schema_version: 'live-voice.l0-ordinary-batch.v1',
            temperature: 'warm',
            epoch_id: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
            profile_id: labels.profile_id,
            target: 20,
            first_audio_eligible: sessionReads === 1 ? 0 : 20,
            barge_in_eligible: sessionReads === 1 ? 0 : 20,
            warmup_required: sessionReads === 1,
            epoch_attempted: false,
            batch_complete: sessionReads > 1,
            browser_mode: 'ordinary-installed-chrome',
            physical_evidence: 'not-claimed',
          };
        }
        if (pathname === '/v1/warmup') return {};
        if (pathname === '/v1/next') {
          return {
            schema_version: 'live-voice.l0-ordinary-job.v1',
            job_id: 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
            epoch_id: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
            temperature: 'warm',
            metric: 'first_audio',
            labels: { schema_version: 'live-voice.l0-run-labels.v1', ...labels },
            setup_audio: 'short',
            barge_audio: null,
          };
        }
        if (pathname === '/v1/complete') return { eligible: true };
        throw new Error('unexpected request');
      },
    },
  );

  await controller.run();
  assert.equal(playCount, 2, 'one unmeasured warm-up plus one measured sample');
  assert.equal(installedCaptureStreamFactory, expectedCaptureStreamFactory);
  assert.equal(requests.filter(([pathname]) => pathname === '/v1/warmup').length, 1);
  const completion = requests.find(([pathname]) => pathname === '/v1/complete')[1].body;
  assert.equal(completion.automated_browser_complete, true);
  assert.equal(completion.records.length, 2);
  assert.equal('operator_confirmation' in completion, false);
  assert.equal(progress.at(-1).status, 'complete');
});

test('voice barge-in uses the fixed prerecorded fixture and requires fence completion', async () => {
  const batch = await import(moduleUrl);
  const labels = {
    profile_id: 'ordinary-chrome-prerecorded-cold',
    scenario_id: 'playout-barge-in-zh',
    sample_index: 20,
    temperature: 'cold',
    evidence_source: 'prerecorded',
  };
  let voiceState = { p1_status: 'idle', text_status: 'idle', recovery_diagnostic: null };
  let configured = false;
  let records = [];
  let sessionReads = 0;
  let settlingSuccessor = false;
  let successorSettleStage = 0;
  let bargePlaybackResolved = false;
  let resolveBargePlayback = null;
  const fixtures = [];
  const completions = [];
  const progress = [];
  const measurement = {
    configure(value) { assert.deepEqual(value, labels); configured = true; return true; },
    disable() { configured = false; records = []; },
    clear() { records = []; },
    snapshot() {
      return { enabled: true, configured, accepted_records: records.length, dropped_records: 0, records };
    },
  };
  const controller = new batch.OrdinaryChromeL0BatchController(
    { base_url: 'http://127.0.0.1:9233', nonce: '0123456789abcdef0123456789abcdef' },
    {
      getControl: () => ({
        async start() { voiceState = { ...voiceState, p1_status: 'capturing' }; },
        async stop() { voiceState = { ...voiceState, p1_status: 'idle' }; },
        setL0CaptureStreamFactory() {},
      }),
      getState: () => voiceState,
      getConnected: () => true,
      measurement: () => measurement,
      player: {
        async unlock() {},
        captureStreamFactory() { return async () => ({ injected: true }); },
        async play(fixture) {
          fixtures.push(fixture);
          if (fixture === 'barge') {
            records = [...records, { milestone: 'barge_in' }];
            await new Promise(resolve => { resolveBargePlayback = resolve; });
            bargePlaybackResolved = true;
          }
        },
        async close() {},
      },
      async sleep() {
        if (settlingSuccessor) {
          successorSettleStage += 1;
          voiceState = {
            ...voiceState,
            p1_status: successorSettleStage === 1 ? 'playing' : 'capturing',
          };
          return;
        }
        if (!records.some(record => record.milestone === 'webaudio_actually_started')) {
          records = [...records, { milestone: 'webaudio_actually_started' }];
        } else if (!records.some(record => record.milestone === 'fence_cancel_completion')) {
          records = [...records, { milestone: 'fence_cancel_completion' }];
        }
      },
      now: (() => { let value = 0; return () => ++value; })(),
      onProgress: value => progress.push(value),
      async request(pathname, init) {
        if (pathname === '/v1/session') {
          sessionReads += 1;
          return {
            schema_version: 'live-voice.l0-ordinary-batch.v1', temperature: 'cold',
            epoch_id: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', profile_id: labels.profile_id,
            target: 20, first_audio_eligible: 20, barge_in_eligible: sessionReads === 1 ? 19 : 20,
            warmup_required: false, epoch_attempted: false, batch_complete: sessionReads > 1,
            browser_mode: 'ordinary-installed-chrome', physical_evidence: 'not-claimed',
          };
        }
        if (pathname === '/v1/next') return {
          schema_version: 'live-voice.l0-ordinary-job.v1',
          job_id: 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
          epoch_id: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', temperature: 'cold', metric: 'barge_in',
          labels: { schema_version: 'live-voice.l0-run-labels.v1', ...labels },
          setup_audio: 'long', barge_audio: 'barge',
        };
        if (pathname === '/v1/complete') {
          assert.equal(bargePlaybackResolved, false, 'fence completion must close labels before the barge fixture ends');
          completions.push(init.body);
          settlingSuccessor = true;
          resolveBargePlayback();
          return { eligible: true };
        }
        throw new Error('unexpected_request');
      },
    },
  );

  await controller.run();
  assert.deepEqual(fixtures, ['long', 'barge']);
  assert.equal(completions[0].automated_browser_complete, true);
  assert.deepEqual(completions[0].records.map(record => record.milestone), [
    'webaudio_actually_started', 'barge_in', 'fence_cancel_completion',
  ]);
  assert.equal(successorSettleStage, 2, 'the successor response must settle before the next sample/epoch');
  assert.equal(configured, false, 'successor settlement must remain outside measured labels');
  assert.equal(progress.some(value => value.status === 'settling'
    && value.reason === 'successor_playout_not_measured'), true);
});

test('sample failure posts the retained snapshot before disabling measurement', async () => {
  const batch = await import(moduleUrl);
  const labels = {
    profile_id: 'ordinary-chrome-prerecorded-warm', scenario_id: 'short-no-tool-zh',
    sample_index: 0, temperature: 'warm', evidence_source: 'prerecorded',
  };
  let records = [];
  let configured = false;
  let completion = null;
  let sessionReads = 0;
  const measurement = {
    configure() { configured = true; return true; },
    disable() { configured = false; records = []; },
    clear() { records = []; },
    snapshot() { return { enabled: true, configured, accepted_records: records.length, dropped_records: 0, records }; },
  };
  const controller = new batch.OrdinaryChromeL0BatchController(
    { base_url: 'http://127.0.0.1:9233', nonce: '0123456789abcdef0123456789abcdef' },
    {
      getControl: () => ({ async start() {}, async stop() {}, setL0CaptureStreamFactory() {} }),
      getState: () => ({ p1_status: 'capturing', text_status: 'idle', recovery_diagnostic: null }),
      getConnected: () => true,
      measurement: () => measurement,
      player: {
        async unlock() {},
        captureStreamFactory() { return async () => ({ injected: true }); },
        async play() {
          records = [{ milestone: 'browser_eot_receipt' }];
          throw new Error('audio_fetch_failed');
        },
        async close() {},
      },
      async sleep() {},
      now: () => 0,
      async request(pathname, init) {
        if (pathname === '/v1/session') {
          sessionReads += 1;
          return {
            schema_version: 'live-voice.l0-ordinary-batch.v1', temperature: 'warm',
            epoch_id: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', profile_id: labels.profile_id,
            target: 20, first_audio_eligible: 0, barge_in_eligible: 0,
            warmup_required: false, epoch_attempted: false, batch_complete: sessionReads > 1,
            browser_mode: 'ordinary-installed-chrome', physical_evidence: 'not-claimed',
          };
        }
        if (pathname === '/v1/next') return {
          schema_version: 'live-voice.l0-ordinary-job.v1', job_id: 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
          epoch_id: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', temperature: 'warm', metric: 'first_audio',
          labels: { schema_version: 'live-voice.l0-run-labels.v1', ...labels },
          setup_audio: 'short', barge_audio: null,
        };
        if (pathname === '/v1/complete') { completion = init.body; return { eligible: false }; }
        throw new Error('unexpected_request');
      },
    },
  );

  await controller.run();
  assert.equal(completion.automated_browser_complete, false);
  assert.deepEqual(completion.records, [{ milestone: 'browser_eot_receipt' }]);
  assert.equal(configured, false);
});

test('a cross-epoch job is rejected before injected input or completion effects', async () => {
  const batch = await import(moduleUrl);
  let played = 0;
  let completed = 0;
  let installedCaptureFactories = 0;
  const controller = new batch.OrdinaryChromeL0BatchController(
    { base_url: 'http://127.0.0.1:9233', nonce: '0123456789abcdef0123456789abcdef' },
    {
      getControl: () => ({
        async start() {},
        async stop() {},
        setL0CaptureStreamFactory() { installedCaptureFactories += 1; },
      }),
      getState: () => ({ p1_status: 'capturing', text_status: 'idle', recovery_diagnostic: null }),
      getConnected: () => true,
      measurement: () => ({
        configure() { return true; }, disable() {}, clear() {},
        snapshot() { return { enabled: true, configured: false, accepted_records: 0, dropped_records: 0, records: [] }; },
      }),
      player: {
        async unlock() {},
        captureStreamFactory() { return async () => ({ injected: true }); },
        async play() { played += 1; },
        async close() {},
      },
      async sleep() {},
      now: () => 0,
      async request(pathname) {
        if (pathname === '/v1/session') return {
          schema_version: 'live-voice.l0-ordinary-batch.v1', temperature: 'cold',
          epoch_id: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
          profile_id: 'ordinary-chrome-prerecorded-cold', target: 20,
          first_audio_eligible: 0, barge_in_eligible: 0, warmup_required: false,
          epoch_attempted: false, batch_complete: false,
          browser_mode: 'ordinary-installed-chrome', physical_evidence: 'not-claimed',
        };
        if (pathname === '/v1/next') return {
          schema_version: 'live-voice.l0-ordinary-job.v1',
          job_id: 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
          epoch_id: 'cccccccccccccccccccccccccccccccc',
          temperature: 'cold', metric: 'first_audio',
          labels: {
            schema_version: 'live-voice.l0-run-labels.v1',
            profile_id: 'ordinary-chrome-prerecorded-cold', scenario_id: 'short-no-tool-zh',
            sample_index: 0, temperature: 'cold', evidence_source: 'prerecorded',
          },
          setup_audio: 'short', barge_audio: null,
        };
        if (pathname === '/v1/complete') { completed += 1; return {}; }
        throw new Error('unexpected_request');
      },
    },
  );

  await assert.rejects(controller.run(), /job contains invalid facts/);
  assert.equal(played, 0);
  assert.equal(completed, 0);
  assert.equal(installedCaptureFactories, 0);
});
