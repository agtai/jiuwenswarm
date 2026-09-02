import assert from 'node:assert/strict';
import test from 'node:test';
import { pathToFileURL } from 'node:url';
import path from 'node:path';

const moduleUrl = pathToFileURL(
  path.resolve(process.cwd(), 'node_modules/.cache/live-voice-l0-measurement/l0Measurement.mjs')
).href;

function setSearch(search) {
  Object.defineProperty(globalThis, 'location', {
    configurable: true,
    enumerable: false,
    writable: true,
    value: { search },
  });
}

function binding(response = false) {
  return {
    correlation_id: 'correlation:opaque:1',
    session_id: 'session:opaque:1',
    interaction_id: 'interaction:opaque:1',
    activation_id: 'activation:opaque:1',
    activation_generation: 3,
    response_id: response ? 'response:opaque:1' : null,
    response_generation: response ? 2 : null,
    unit_id: null,
    unit_seq: null,
    turn_id: null,
    round_id: null,
    task_id: null,
    attempt_id: null,
  };
}

test('flag off exposes no control and records no observation', async () => {
  setSearch('');
  const measurement = await import(`${moduleUrl}?off`);
  assert.equal(measurement.browserL0Available(), false);
  assert.equal(measurement.browserL0Enabled(), false);
  assert.equal(measurement.browserL0Control(), null);
  assert.equal(globalThis.__JIUWENSWARM_LIVE_VOICE_L0__, undefined);
  assert.equal(
    measurement.recordBrowserL0Milestone({
      milestone: 'browser_eot_receipt',
      binding: binding(),
    }),
    false
  );
  assert.equal(measurement.registerBrowserL0Response(binding(true)), false);
});

test('opt-in control retains only closed content-free production observations', async () => {
  setSearch('?live_voice_l0_measurement=1');
  const measurement = await import(`${moduleUrl}?enabled`);
  const control = globalThis.__JIUWENSWARM_LIVE_VOICE_L0__;
  assert.ok(control);
  assert.equal(measurement.browserL0Control(), control);
  assert.equal(measurement.browserL0Available(), true);
  assert.equal(measurement.browserL0Enabled(), false);
  assert.equal(
    control.configure({
      profile_id: 'physical-formal-web-warm',
      scenario_id: 'short-no-tool-zh',
      sample_index: 4,
      temperature: 'warm',
      evidence_source: 'physical',
    }),
    true
  );
  assert.equal(measurement.browserL0Enabled(), true);
  assert.equal(measurement.registerBrowserL0Response(binding(true)), true);
  assert.equal(
    measurement.recordBrowserL0Milestone({
      milestone: 'browser_eot_receipt',
      binding: binding(),
      observed_at: '2026-08-23T10:11:12.345Z',
      monotonic_ms: 1234.5,
    }),
    true
  );
  assert.equal(
    measurement.recordBrowserL0Milestone({
      milestone: 'capture_stopped',
      binding: binding(),
      observed_at: '2026-08-23T10:11:12.346Z',
    }),
    false,
    'wall and monotonic clocks must be supplied as one exact pair'
  );
  assert.equal(
    measurement.recordBrowserL0Milestone({
      milestone: 'task_commit',
      binding: { ...binding(), task_id: 'task:opaque:1' },
    }),
    false,
    'Task and Attempt identity must be supplied as one exact pair'
  );
  assert.equal(
    measurement.recordBrowserL0Milestone({
      milestone: 'playout_completed',
      binding: binding(true),
    }),
    false,
    'completed segments cannot fabricate an unmeasured zero duration'
  );
  assert.equal(
    measurement.recordBrowserL0Milestone({
      milestone: 'playout_completed',
      binding: binding(true),
      duration_ms: 812.5,
    }),
    true
  );
  assert.equal(
    measurement.recordBrowserL0Milestone({
      milestone: 'barge_in',
      binding: binding(true),
    }),
    true
  );
  assert.equal(
    measurement.recordBrowserL0Milestone({
      milestone: 'fence_cancel_completion',
      binding: binding(true),
      classification: 'cancelled',
    }),
    true
  );
  assert.equal(
    measurement.recordBrowserL0Milestone({
      milestone: 'discarded_work',
      binding: binding(true),
    }),
    true
  );
  assert.equal(
    measurement.recordBrowserL0Milestone({
      milestone: 'browser_failure',
      binding: binding(true),
      classification: 'failure',
    }),
    true
  );
  const snapshot = control.snapshot();
  assert.equal(snapshot.accepted_records, 6);
  assert.equal(snapshot.dropped_records, 0);
  assert.deepEqual(snapshot.records.map(item => item.milestone), [
    'browser_eot_receipt',
    'playout_completed',
    'barge_in',
    'fence_cancel_completion',
    'discarded_work',
    'browser_failure',
  ]);
  assert.equal(snapshot.records[0].observation.source_component, 'measurement.browser.eot_receipt');
  assert.equal(snapshot.records[0].observation.observed_at, '2026-08-23T10:11:12.345Z');
  assert.equal(snapshot.records[0].observation.monotonic_ms, 1234.5);
  assert.equal(snapshot.records[1].observation.duration_ms, 812.5);
  assert.equal(snapshot.records[2].observation.route.reason_code, null);
  assert.equal(snapshot.records[2].observation.reason_code, 'CANCEL_REQUESTED');
  assert.equal(snapshot.records[3].observation.route.reason_code, null);
  assert.equal(snapshot.records[3].observation.reason_code, 'CANCEL_TERMINAL');
  assert.equal(snapshot.records[4].observation.segment_name, 'runtime.presentation');
  assert.equal(snapshot.records[4].observation.error_code, 'STALE');
  assert.equal(snapshot.records[5].classification, 'failure');
  assert.equal(snapshot.records[5].observation.source_component, 'measurement.browser.failure');
  assert.equal(snapshot.records[5].observation.reason_code, 'UNAVAILABLE');
  assert.equal(snapshot.records[5].observation.error_code, 'UNAVAILABLE');
  const serialized = JSON.stringify(snapshot);
  assert.equal(/transcript|audio|credential|agent_text|final_text/i.test(serialized), false);
  assert.equal(serialized.includes('physical-formal-web-warm'), true);
});

test('invalid labels fail closed and clear prior run ownership', () => {
  const control = globalThis.__JIUWENSWARM_LIVE_VOICE_L0__;
  assert.ok(control);
  assert.equal(
    control.configure({
      profile_id: 'physical-formal-web-warm',
      scenario_id: 'short-no-tool-zh',
      sample_index: 4,
      temperature: 'warm',
      evidence_source: 'physical',
      transcript: 'forbidden',
    }),
    false
  );
  assert.equal(control.snapshot().configured, false);
});

test('explicit disable clears records and prevents abandoned-label observations', async () => {
  const control = globalThis.__JIUWENSWARM_LIVE_VOICE_L0__;
  assert.ok(control);
  assert.equal(
    control.configure({
      profile_id: 'physical-formal-web-warm',
      scenario_id: 'short-no-tool-zh',
      sample_index: 9,
      temperature: 'warm',
      evidence_source: 'physical',
    }),
    true,
  );
  control.disable();
  assert.equal(control.snapshot().configured, false);
  assert.equal(control.snapshot().accepted_records, 0);
  const measurement = await import(`${moduleUrl}?enabled`);
  assert.equal(
    measurement.recordBrowserL0Milestone({
      milestone: 'browser_eot_receipt',
      binding: binding(),
    }),
    false,
  );
});

test('response registration freezes sample ownership and rejects late cross-sample callbacks', async () => {
  const control = globalThis.__JIUWENSWARM_LIVE_VOICE_L0__;
  assert.ok(control);
  const measurement = await import(`${moduleUrl}?enabled`);
  const responseA = {
    ...binding(true),
    response_id: 'response:late:a',
    response_generation: 7,
  };
  const responseB = {
    ...binding(true),
    response_id: 'response:current:b',
    response_generation: 8,
  };
  assert.equal(
    control.configure({
      profile_id: 'physical-formal-web-warm',
      scenario_id: 'short-no-tool-zh',
      sample_index: 20,
      temperature: 'warm',
      evidence_source: 'physical',
    }),
    true,
  );
  assert.equal(measurement.registerBrowserL0Response(responseA), true);
  control.disable();
  assert.equal(
    control.configure({
      profile_id: 'physical-formal-web-warm',
      scenario_id: 'long-answer-zh',
      sample_index: 21,
      temperature: 'warm',
      evidence_source: 'physical',
    }),
    true,
  );
  assert.equal(
    measurement.recordBrowserL0Milestone({
      milestone: 'browser_first_frame',
      binding: responseA,
    }),
    false,
  );
  assert.equal(measurement.registerBrowserL0Response(responseA), false);
  assert.equal(measurement.registerBrowserL0Response(responseB), true);
  assert.equal(
    measurement.recordBrowserL0Milestone({
      milestone: 'browser_first_frame',
      binding: responseB,
    }),
    true,
  );
  const snapshot = control.snapshot();
  assert.equal(snapshot.dropped_records, 1);
  assert.equal(snapshot.accepted_records, 1);
  assert.equal(snapshot.records[0].scenario_id, 'long-answer-zh');
  assert.equal(snapshot.records[0].sample_index, 21);
});

test('per-unit milestones require exact response identity and non-negative unit sequence', async () => {
  const measurement = await import(`${moduleUrl}?enabled`);
  const control = globalThis.__JIUWENSWARM_LIVE_VOICE_L0__;
  control.disable();
  assert.equal(control.configure({
    profile_id: 'profile-unit',
    scenario_id: 'scenario-unit',
    sample_index: 0,
    temperature: 'warm',
    evidence_source: 'physical',
  }), true);
  const exact = {
    ...binding(true),
    response_id: 'response:unit:2',
    unit_id: 'unit:opaque:2',
    unit_seq: 2,
  };
  assert.equal(measurement.registerBrowserL0Response(exact), true);
  assert.equal(measurement.recordBrowserL0Milestone({
    milestone: 'unit_tts_requested',
    binding: { ...exact, unit_seq: null },
  }), false);
  assert.equal(measurement.recordBrowserL0Milestone({
    milestone: 'unit_tts_requested',
    binding: { ...exact, unit_id: null },
  }), false);
  assert.equal(measurement.recordBrowserL0Milestone({
    milestone: 'unit_tts_requested',
    binding: exact,
  }), true);
  assert.equal(control.snapshot().records.at(-1).binding.unit_seq, 2);
  assert.equal(control.snapshot().records.at(-1).binding.unit_id, 'unit:opaque:2');
});

test('successor prebuffer milestones retain exact unit identity', async () => {
  const measurement = await import(`${moduleUrl}?enabled`);
  const control = globalThis.__JIUWENSWARM_LIVE_VOICE_L0__;
  control.disable();
  assert.equal(control.configure({
    profile_id: 'profile-successor',
    scenario_id: 'scenario-successor',
    sample_index: 0,
    temperature: 'warm',
    evidence_source: 'physical',
  }), true);
  const exact = {
    ...binding(true),
    response_id: 'response:successor:1',
    unit_id: 'unit:successor:1',
    unit_seq: 1,
  };
  assert.equal(measurement.registerBrowserL0Response(exact), true);
  for (const milestone of [
    'successor_tts_requested',
    'successor_downlink_attached',
    'successor_first_frame_buffered',
    'successor_promoted_to_playout',
  ]) {
    assert.equal(measurement.recordBrowserL0Milestone({ milestone, binding: exact }), true, milestone);
  }
  assert.deepEqual(
    control.snapshot().records.slice(-4).map(record => [
      record.milestone,
      record.binding.unit_id,
      record.binding.unit_seq,
    ]),
    [
      ['successor_tts_requested', 'unit:successor:1', 1],
      ['successor_downlink_attached', 'unit:successor:1', 1],
      ['successor_first_frame_buffered', 'unit:successor:1', 1],
      ['successor_promoted_to_playout', 'unit:successor:1', 1],
    ],
  );
});
