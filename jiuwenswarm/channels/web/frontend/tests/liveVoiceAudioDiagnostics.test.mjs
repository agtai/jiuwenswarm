import assert from 'node:assert/strict';
import test from 'node:test';
import {
  recordAudioDiagnostic,
  audioDiagnosticSnapshot,
  clearAudioDiagnostics,
  audioDiagnosticBundle,
  profileAudioOperation,
  markAudioRpcRejection,
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

test('profiles preserve returned values, rejected envelopes, errors and exact concurrent identities', async () => {
  const previous = console.info;
  console.info = () => undefined;
  clearAudioDiagnostics();
  try {
    let calls = 0;
    const value = { ok: false, secret: 'PRIVATE' };
    assert.equal(
      await profileAudioOperation('browser.rpc', { request_id: 'a' }, async () => {
        calls += 1;
        return value;
      }),
      value,
    );
    const error = Object.assign(new Error('PRIVATE_ERROR'), { code: 'REQUEST_TIMEOUT' });
    await assert.rejects(
      profileAudioOperation('browser.rpc', { request_id: 'b' }, async () => {
        calls += 1;
        throw error;
      }),
      actual => actual === error,
    );
    await Promise.all(['c', 'd'].map(request_id => profileAudioOperation('browser.rpc', { request_id }, async () => request_id)));
    assert.equal(calls, 2);
    const terminal = audioDiagnosticSnapshot().filter(row => row.event === 'profile_span_settled');
    assert.deepEqual(
      terminal.map(row => row.fields.outcome),
      ['rejected', 'timeout', 'returned', 'returned'],
    );
    assert.equal(new Set(terminal.map(row => row.fields.span_id)).size, 4);
    assert.ok(terminal.every(row => row.fields.duration_ms >= 0));
    assert.equal(JSON.stringify(terminal).includes('PRIVATE'), false);
  } finally {
    console.info = previous;
    clearAudioDiagnostics();
  }
});

test('journal survives module reload, sanitizes storage and exports bounded retained records', async () => {
  const previousWindow = globalThis.window;
  const previousInfo = console.info;
  const storage = new Map();
  console.info = () => undefined;
  globalThis.window = {
    sessionStorage: {
      getItem: key => storage.get(key) ?? null,
      setItem: (key, value) => storage.set(key, value),
      removeItem: key => storage.delete(key),
    },
    addEventListener() {},
  };
  try {
    clearAudioDiagnostics();
    for (let seq = 0; seq < 4200; seq++) recordAudioDiagnostic('capture_progress', { seq, session_id: 'a', pcm: 'PRIVATE' });
    const original = audioDiagnosticBundle();
    assert.ok(original.overwritten_pages > 0);
    assert.ok(original.records.length <= 4096);
    const reload = await import('../node_modules/.cache/live-voice-audio-diagnostics/audioDiagnostics.mjs?reloaded');
    const restored = reload.audioDiagnosticBundle();
    assert.ok(restored.records.length > 2000);
    assert.equal(restored.records.at(-1).fields.seq, 4199);
    assert.equal(JSON.stringify(restored).includes('PRIVATE'), false);
    const index = Number(storage.get('live-voice-diagnostics-v1:next')) % 128;
    storage.set(
      `live-voice-diagnostics-v1:${index}`,
      JSON.stringify([
        { ...restored.records.at(-1), sequence: 999999, fields: { session_id: 'a', transcript: 'PRIVATE_INJECTED', stage: '<script>alert(1)</script>' } },
      ]),
    );
    assert.equal(JSON.stringify(reload.audioDiagnosticBundle()).includes('PRIVATE'), false);
    reload.clearAudioDiagnostics();
  } finally {
    clearAudioDiagnostics();
    globalThis.window = previousWindow;
    console.info = previousInfo;
  }
});

test('storage quota denial cannot fail an RPC and is visible in its export', async () => {
  const previousWindow = globalThis.window;
  const previousInfo = console.info;
  console.info = () => undefined;
  globalThis.window = {
    get sessionStorage() {
      throw new Error('quota');
    },
    addEventListener() {},
  };
  try {
    clearAudioDiagnostics();
    let calls = 0;
    assert.equal(
      await profileAudioOperation('browser.rpc', {}, async () => {
        calls += 1;
        return 42;
      }),
      42,
    );
    assert.equal(calls, 1);
    const bundle = audioDiagnosticBundle();
    assert.ok(bundle.storage_failures > 0);
    assert.equal(bundle.records.filter(row => row.event === 'profile_span_settled').length, 1);
  } finally {
    clearAudioDiagnostics();
    globalThis.window = previousWindow;
    console.info = previousInfo;
  }
});

test('clock and metadata observation failures cannot prevent the original action', async () => {
  const previous = globalThis.performance;
  globalThis.performance = {
    now() {
      throw new Error('clock');
    },
  };
  try {
    let calls = 0;
    const metadata = {
      get request_id() {
        throw new Error('PRIVATE');
      },
    };
    const result = { ok: true };
    assert.equal(
      await profileAudioOperation('browser.rpc', metadata, async () => {
        calls++;
        return result;
      }),
      result,
    );
    const error = new Error('original');
    await assert.rejects(
      profileAudioOperation('browser.rpc', metadata, async () => {
        calls++;
        throw error;
      }),
      actual => actual === error,
    );
    assert.equal(calls, 2);
  } finally {
    globalThis.performance = previous;
    clearAudioDiagnostics();
  }
});

test('RPC rejection retains its code and reason, separate from transport failures', async () => {
  const previous = console.info;
  console.info = () => undefined;
  clearAudioDiagnostics();
  try {
    const rejection = Object.assign(new Error('PRIVATE_MESSAGE'), {
      code: 'STALE',
      reason: 'STALE_ACTIVATION',
      payload: { secret: 'PRIVATE_PAYLOAD' },
    });
    markAudioRpcRejection(rejection);
    const network = Object.assign(new Error('PRIVATE_NETWORK'), { code: 'WS_NOT_READY' });
    for (const error of [rejection, network]) {
      await assert.rejects(
        profileAudioOperation('browser.rpc', {}, async () => {
          throw error;
        }),
        actual => actual === error,
      );
    }
    const terminal = audioDiagnosticSnapshot().filter(row => row.event === 'profile_span_settled');
    assert.deepEqual(
      terminal.map(row => row.fields.outcome),
      ['rejected', 'failed'],
    );
    assert.equal(terminal[0].fields.error_reason, 'STALE_ACTIVATION');
    assert.equal(terminal[0].fields.error_code, 'STALE');
    assert.equal(JSON.stringify(terminal).includes('PRIVATE'), false);
  } finally {
    console.info = previous;
    clearAudioDiagnostics();
  }
});
