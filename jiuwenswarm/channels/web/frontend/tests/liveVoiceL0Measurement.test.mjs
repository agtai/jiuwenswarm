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
    activation_generation: 3,
    response_id: response ? 'response:opaque:1' : null,
    response_generation: response ? 2 : null,
    turn_id: null,
    round_id: null,
    task_id: null,
    attempt_id: null,
  };
}

test('flag off exposes no control and records no observation', async () => {
  setSearch('');
  const measurement = await import(`${moduleUrl}?off`);
  assert.equal(measurement.browserL0Enabled(), false);
  assert.equal(globalThis.__JIUWENSWARM_LIVE_VOICE_L0__, undefined);
  assert.equal(
    measurement.recordBrowserL0Milestone({
      milestone: 'browser_eot_receipt',
      binding: binding(),
    }),
    false
  );
});

test('opt-in control retains only closed content-free production observations', async () => {
  setSearch('?live_voice_l0_measurement=1');
  const measurement = await import(`${moduleUrl}?enabled`);
  const control = globalThis.__JIUWENSWARM_LIVE_VOICE_L0__;
  assert.ok(control);
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
  const snapshot = control.snapshot();
  assert.equal(snapshot.accepted_records, 2);
  assert.equal(snapshot.dropped_records, 0);
  assert.deepEqual(snapshot.records.map(item => item.milestone), [
    'browser_eot_receipt',
    'playout_completed',
  ]);
  assert.equal(snapshot.records[0].observation.source_component, 'measurement.browser.eot_receipt');
  assert.equal(snapshot.records[0].observation.observed_at, '2026-08-23T10:11:12.345Z');
  assert.equal(snapshot.records[0].observation.monotonic_ms, 1234.5);
  assert.equal(snapshot.records[1].observation.duration_ms, 812.5);
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
