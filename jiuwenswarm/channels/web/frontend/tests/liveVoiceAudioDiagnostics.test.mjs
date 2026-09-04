import assert from 'node:assert/strict';
import test from 'node:test';
import {
  recordAudioDiagnostic,
  audioDiagnosticSnapshot,
  clearAudioDiagnostics,
} from '../node_modules/.cache/live-voice-audio-diagnostics/audioDiagnostics.mjs';

test('diagnostics contain only allowlisted scalars, freeze records and remain bounded', () => {
  const previous = console.info;
  console.info = () => undefined;
  try {
    clearAudioDiagnostics();
    recordAudioDiagnostic('capture_progress', {
      session_id: 'session-a',
      capture_id: 'capture-a',
      generation: 2,
      pending_frames: 8,
      pcm: new Float32Array(960),
      transcript: 'PRIVATE_TEXT',
      token: 'PRIVATE_SECRET',
      device_id: 'PRIVATE_DEVICE',
      reason: 'contains spaces PRIVATE',
      rms_peak: Infinity,
    });
    const first = audioDiagnosticSnapshot()[0];
    assert.deepEqual(first.fields, { session_id: 'session-a', capture_id: 'capture-a', generation: 2, pending_frames: 8 });
    assert.equal(JSON.stringify(first).includes('PRIVATE'), false);
    assert.ok(Object.isFrozen(first) && Object.isFrozen(first.fields));
    audioDiagnosticSnapshot().pop();
    assert.equal(audioDiagnosticSnapshot().length, 1);
    for (let seq = 0; seq < 2200; seq++) recordAudioDiagnostic('capture_progress', { seq });
    assert.equal(audioDiagnosticSnapshot().length, 2048);
    assert.equal(audioDiagnosticSnapshot().at(-1).fields.seq, 2199);
    recordAudioDiagnostic('not a valid event', {});
    assert.equal(audioDiagnosticSnapshot().length, 2048);
  } finally {
    console.info = previous;
    clearAudioDiagnostics();
  }
});

test('throwing console and payload getters cannot escape or allocate authority', () => {
  const previous = console.info;
  console.info = () => {
    throw new Error('sink failed');
  };
  try {
    assert.doesNotThrow(() => recordAudioDiagnostic('barge_in_gate', { callback_current: false }));
    assert.doesNotThrow(() =>
      recordAudioDiagnostic('capture_progress', {
        get session_id() {
          throw new Error('getter failed');
        },
      }),
    );
    assert.equal(audioDiagnosticSnapshot().at(-1).fields.callback_current, false);
  } finally {
    console.info = previous;
    clearAudioDiagnostics();
  }
});
