import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const processorSource = readFileSync(new URL('../src/features/live-voice/formal/adapters/liveVoiceCaptureProcessor.js', import.meta.url), 'utf8');

function loadProcessor(sampleRate = 48000) {
  let processorConstructor = null;
  class FakeAudioWorkletProcessor {
    constructor() {
      this.port = {
        messages: [],
        postMessage: (message, transfer = []) => {
          this.port.messages.push({ message, transfer });
        },
      };
    }
  }
  const sandbox = {
    AudioWorkletProcessor: FakeAudioWorkletProcessor,
    Float32Array,
    Math,
    currentFrame: 0,
    sampleRate,
    registerProcessor(name, constructor) {
      assert.equal(name, 'jiuwenswarm-live-voice-capture-v1');
      processorConstructor = constructor;
    },
  };
  vm.runInNewContext(processorSource, sandbox, { filename: 'liveVoiceCaptureProcessor.js' });
  assert.notEqual(processorConstructor, null);
  const processor = new processorConstructor({
    processorOptions: { captureGeneration: 7, frameDurationMs: 20 },
  });
  return { processor, sandbox };
}

function stereoQuantum(leftValue, rightValue, length = 128) {
  return [[new Float32Array(length).fill(leftValue), new Float32Array(length).fill(rightValue)]];
}

test('AudioWorklet downmixes and aggregates render quanta into exact 20ms PCM frames', () => {
  const { processor, sandbox } = loadProcessor();
  for (let index = 0; index < 8; index += 1) {
    assert.equal(processor.process(stereoQuantum(0.2, 0.4)), true);
    sandbox.currentFrame += 128;
  }
  assert.equal(processor.port.messages.length, 1);
  const { message, transfer } = processor.port.messages[0];
  assert.equal(message.kind, 'frame');
  assert.equal(message.capture_generation, 7);
  assert.equal(message.seq, 0);
  assert.equal(message.sample_cursor, 0);
  assert.equal(message.context_time_s, 0);
  assert.equal(message.sample_rate_hz, 48000);
  assert.equal(message.samples.length, 960);
  assert.ok(Math.abs(message.samples[0] - 0.3) < 1e-6);
  assert.equal(transfer[0], message.samples.buffer);
});

test('AudioWorklet preserves contiguous cursor across multiple non-quantum-aligned frames', () => {
  const { processor, sandbox } = loadProcessor(44100);
  for (let index = 0; index < 14; index += 1) {
    assert.equal(processor.process(stereoQuantum(0.1, 0.1)), true);
    sandbox.currentFrame += 128;
  }
  assert.equal(processor.port.messages.length, 2);
  assert.deepEqual(
    processor.port.messages.map(({ message }) => [message.seq, message.sample_cursor, message.samples.length]),
    [
      [0, 0, 882],
      [1, 882, 882],
    ]
  );
});

test('AudioWorklet starts from a reused running context frame and follows fixed 128-frame quanta', () => {
  const { processor, sandbox } = loadProcessor();
  sandbox.currentFrame = 8192;
  for (let index = 0; index < 8; index += 1) {
    assert.equal(processor.process(stereoQuantum(0.2, 0.2)), true);
    sandbox.currentFrame += 128;
  }

  assert.equal(processor.port.messages.length, 1);
  const output = processor.port.messages[0].message;
  assert.deepEqual([output.seq, output.sample_cursor, output.context_time_s], [0, 0, 8192 / 48000]);
  assert.equal(output.samples.length, 960);
  assert.equal(processor.failed, false);
});

test('AudioWorklet supports a fixed non-128 render quantum without duplicate or missing samples', () => {
  const { processor, sandbox } = loadProcessor();
  for (let index = 0; index < 4; index += 1) {
    assert.equal(processor.process(stereoQuantum(0.25, 0.25, 256)), true);
    sandbox.currentFrame += 256;
  }

  assert.equal(processor.port.messages.length, 1);
  const output = processor.port.messages[0].message;
  assert.deepEqual([output.seq, output.sample_cursor, output.context_time_s], [0, 0, 0]);
  assert.equal(output.samples.length, 960);
  assert.equal(
    output.samples.every(sample => Math.abs(sample - 0.25) < 1e-6),
    true
  );
  assert.equal(processor.pendingLength, 64);
  assert.equal(processor.expectedRenderFrame, 1024);
});

test('AudioWorklet resumes at the next render quantum without treating suspended wall time as an input gap', () => {
  const { processor, sandbox } = loadProcessor();
  sandbox.currentFrame = 4096;
  assert.equal(processor.process(stereoQuantum(0.1, 0.1)), true);

  // A suspended context invokes no process callback. On resume the render
  // timeline continues at the next quantum, regardless of elapsed wall time.
  sandbox.currentFrame = 4224;
  assert.equal(processor.process(stereoQuantum(0.2, 0.2)), true);
  assert.equal(processor.recentInputGapSamples, 0);
  assert.equal(processor.expectedRenderFrame, 4352);
  assert.equal(processor.failed, false);
});

test('AudioWorklet compatibility recovery de-duplicates a monotonic full-overlap UA anomaly', () => {
  const { processor, sandbox } = loadProcessor();
  assert.equal(processor.process(stereoQuantum(0.1, 0.1, 256)), true);

  sandbox.currentFrame = 128;
  assert.equal(processor.process(stereoQuantum(0.2, 0.2)), true);
  assert.equal(processor.failed, false);
  assert.equal(processor.port.messages.length, 0);

  for (let frame = 256; frame <= 896; frame += 128) {
    sandbox.currentFrame = frame;
    assert.equal(processor.process(stereoQuantum(0.3, 0.3)), true);
  }

  assert.equal(processor.port.messages.length, 1);
  const output = processor.port.messages[0].message;
  assert.equal(output.kind, 'frame');
  assert.equal(output.context_time_s, 0);
  assert.equal(output.samples.length, 960);
  assert.equal(Math.abs(output.samples[0] - 0.1) < 1e-6, true);
  assert.equal(Math.abs(output.samples[255] - 0.1) < 1e-6, true);
  assert.equal(Math.abs(output.samples[256] - 0.3) < 1e-6, true);
  assert.equal(Math.abs(output.samples[959] - 0.3) < 1e-6, true);
});

test('AudioWorklet compatibility recovery drops only a partial-overlap UA anomaly prefix', () => {
  const { processor, sandbox } = loadProcessor();
  assert.equal(processor.process(stereoQuantum(0.1, 0.1)), true);

  const overlapping = new Float32Array(128).fill(0.2);
  overlapping.fill(0.4, 64);
  sandbox.currentFrame = 64;
  assert.equal(processor.process([[overlapping, overlapping]]), true);

  for (let frame = 192; frame <= 832; frame += 128) {
    sandbox.currentFrame = frame;
    assert.equal(processor.process(stereoQuantum(0.3, 0.3)), true);
  }

  assert.equal(processor.port.messages.length, 1);
  const output = processor.port.messages[0].message;
  assert.deepEqual([output.seq, output.sample_cursor, output.context_time_s], [0, 0, 0]);
  assert.equal(Math.abs(output.samples[0] - 0.1) < 1e-6, true);
  assert.equal(Math.abs(output.samples[127] - 0.1) < 1e-6, true);
  assert.equal(Math.abs(output.samples[128] - 0.4) < 1e-6, true);
  assert.equal(Math.abs(output.samples[191] - 0.4) < 1e-6, true);
  assert.equal(Math.abs(output.samples[192] - 0.3) < 1e-6, true);
  assert.equal(Math.abs(output.samples[959] - 0.3) < 1e-6, true);
});

test('AudioWorklet de-duplicates a bounded same-frame callback anomaly and resumes on clock advance', () => {
  const { processor, sandbox } = loadProcessor();
  assert.equal(processor.process(stereoQuantum(0.1, 0.1)), true);
  assert.equal(processor.process(stereoQuantum(0.9, 0.9)), true);
  assert.equal(processor.pendingLength, 128);
  assert.equal(processor.duplicateRenderFrameCount, 1);

  for (let frame = 128; frame <= 896; frame += 128) {
    sandbox.currentFrame = frame;
    assert.equal(processor.process(stereoQuantum(0.2, 0.2)), true);
  }

  assert.equal(processor.failed, false);
  assert.equal(processor.duplicateRenderFrameCount, 0);
  assert.equal(processor.port.messages.length, 1);
  const output = processor.port.messages[0].message;
  assert.equal(Math.abs(output.samples[0] - 0.1) < 1e-6, true);
  assert.equal(Math.abs(output.samples[127] - 0.1) < 1e-6, true);
  assert.equal(Math.abs(output.samples[128] - 0.2) < 1e-6, true);
});

test('AudioWorklet resets the duplicate-frame watchdog only after render-clock advance', () => {
  const { processor, sandbox } = loadProcessor();
  assert.equal(processor.process(stereoQuantum(0.1, 0.1)), true);
  for (let duplicate = 0; duplicate < 8; duplicate += 1) {
    assert.equal(processor.process(stereoQuantum(0.9, 0.9)), true);
  }
  assert.equal(processor.duplicateRenderFrameCount, 8);
  assert.equal(processor.pendingLength, 128);

  sandbox.currentFrame = 128;
  assert.equal(processor.process(stereoQuantum(0.2, 0.2)), true);
  assert.equal(processor.duplicateRenderFrameCount, 0);
  for (let duplicate = 0; duplicate < 8; duplicate += 1) {
    assert.equal(processor.process(stereoQuantum(0.8, 0.8)), true);
  }
  assert.equal(processor.duplicateRenderFrameCount, 8);
  assert.equal(processor.pendingLength, 256);
  assert.equal(processor.port.messages.length, 0);

  assert.equal(processor.process(stereoQuantum(0.8, 0.8)), false);
  assert.equal(processor.port.messages.length, 1);
  assert.equal(processor.port.messages[0].message.kind, 'error');
  assert.equal(processor.port.messages[0].message.reason, 'render_frame_not_advanced');
});

test('AudioWorklet keeps a true regression immediately terminal after tolerated duplicate callbacks', () => {
  const { processor, sandbox } = loadProcessor();
  sandbox.currentFrame = 256;
  assert.equal(processor.process(stereoQuantum(0.25, 0.25)), true);
  for (let duplicate = 0; duplicate < 3; duplicate += 1) {
    assert.equal(processor.process(stereoQuantum(0.75, 0.75)), true);
  }
  assert.equal(processor.duplicateRenderFrameCount, 3);
  assert.equal(processor.pendingLength, 128);

  sandbox.currentFrame = 255;
  assert.equal(processor.process(stereoQuantum(0.5, 0.5)), false);
  assert.equal(processor.port.messages.length, 1);
  assert.equal(processor.port.messages[0].message.kind, 'error');
  assert.equal(processor.port.messages[0].message.reason, 'render_frame_regressed');
  assert.equal(processor.process(stereoQuantum(0.5, 0.5)), false);
  assert.equal(processor.port.messages.length, 1);
  assert.equal(processor.pendingLength, 128);
  assert.equal(processor.seq, 0);
});

test('AudioWorklet same-frame empty callbacks cannot advance samples or readiness and remain watchdog-bounded', () => {
  const { processor } = loadProcessor();
  assert.equal(processor.process(stereoQuantum(0.4, 0.4)), true);
  assert.equal(processor.pendingLength, 128);
  assert.equal(processor.seq, 0);
  assert.equal(processor.port.messages.length, 0);

  for (let duplicate = 0; duplicate < 8; duplicate += 1) {
    assert.equal(processor.process([[]]), true);
    assert.equal(processor.pendingLength, 128);
    assert.equal(processor.seq, 0);
    assert.equal(processor.port.messages.length, 0);
  }
  assert.equal(processor.duplicateRenderFrameCount, 8);

  assert.equal(processor.process([[]]), false);
  assert.equal(processor.pendingLength, 128);
  assert.equal(processor.seq, 0);
  assert.equal(processor.port.messages.length, 1);
  assert.equal(processor.port.messages[0].message.kind, 'error');
  assert.equal(processor.port.messages[0].message.reason, 'render_frame_not_advanced');
});

test('AudioWorklet same-frame quantum growth preserves the first prefix and appends only the unseen suffix', () => {
  const { processor, sandbox } = loadProcessor();
  assert.equal(processor.process(stereoQuantum(0.1, 0.1)), true);

  const longerLeft = new Float32Array(256).fill(0.9);
  const longerRight = new Float32Array(256).fill(0.9);
  longerLeft.fill(0.4, 128);
  longerRight.fill(0.4, 128);
  assert.equal(processor.process([[longerLeft, longerRight]]), true);
  assert.equal(processor.pendingLength, 256);
  assert.equal(processor.expectedRenderFrame, 256);
  assert.equal(processor.duplicateRenderFrameCount, 1);

  for (let frame = 256; frame <= 896; frame += 128) {
    sandbox.currentFrame = frame;
    assert.equal(processor.process(stereoQuantum(0.3, 0.3)), true);
  }

  assert.equal(processor.failed, false);
  assert.equal(processor.duplicateRenderFrameCount, 0);
  assert.equal(processor.port.messages.length, 1);
  const output = processor.port.messages[0].message;
  assert.deepEqual([output.seq, output.sample_cursor, output.context_time_s], [0, 0, 0]);
  assert.equal(Math.abs(output.samples[0] - 0.1) < 1e-6, true);
  assert.equal(Math.abs(output.samples[127] - 0.1) < 1e-6, true);
  assert.equal(Math.abs(output.samples[128] - 0.4) < 1e-6, true);
  assert.equal(Math.abs(output.samples[255] - 0.4) < 1e-6, true);
  assert.equal(Math.abs(output.samples[256] - 0.3) < 1e-6, true);
  assert.equal(Math.abs(output.samples[959] - 0.3) < 1e-6, true);
});

test('AudioWorklet accepts real input after an initial empty callback at the same render frame', () => {
  const { processor, sandbox } = loadProcessor();
  sandbox.currentFrame = 8192;
  assert.equal(processor.process([[]]), true);
  assert.equal(processor.process(stereoQuantum(0.75, 0.75)), true);
  for (let index = 1; index < 8; index += 1) {
    sandbox.currentFrame = 8192 + index * 128;
    assert.equal(processor.process(stereoQuantum(0.75, 0.75)), true);
  }

  assert.equal(processor.port.messages.length, 1);
  const output = processor.port.messages[0].message;
  assert.equal(output.context_time_s, 8192 / 48000);
  assert.equal(
    output.samples.every(sample => Math.abs(sample - 0.75) < 1e-6),
    true
  );
  assert.equal(processor.failed, false);
});

test('AudioWorklet tolerates a bounded empty-input window and preserves the PCM timeline', () => {
  const { processor, sandbox } = loadProcessor();
  assert.equal(processor.process(stereoQuantum(1, 1)), true);
  sandbox.currentFrame = 128;
  assert.equal(processor.process([[]]), true);
  sandbox.currentFrame = 256;
  assert.equal(processor.process([[]]), true);
  sandbox.currentFrame = 384;
  assert.equal(processor.process(stereoQuantum(0.5, 0.5)), true);
  for (let index = 0; index < 4; index += 1) {
    sandbox.currentFrame += 128;
    assert.equal(processor.process(stereoQuantum(0.5, 0.5)), true);
  }

  assert.equal(processor.port.messages.length, 1);
  const frame = processor.port.messages[0].message;
  assert.equal(frame.kind, 'frame');
  assert.equal(frame.seq, 0);
  assert.equal(frame.sample_cursor, 0);
  assert.equal(frame.context_time_s, 0);
  assert.equal(frame.samples.length, 960);
  assert.equal(frame.samples[0], 1);
  assert.equal(frame.samples[127], 1);
  assert.equal(frame.samples[128], 0);
  assert.equal(frame.samples[383], 0);
  assert.equal(frame.samples[384], 0.5);
  assert.equal(frame.samples[959], 0.5);

  for (let index = 0; index < 7; index += 1) {
    sandbox.currentFrame += 128;
    assert.equal(processor.process(stereoQuantum(0.25, 0.25)), true);
  }
  assert.deepEqual(
    processor.port.messages.map(({ message }) => [message.seq, message.sample_cursor, message.context_time_s, message.samples.length]),
    [
      [0, 0, 0, 960],
      [1, 960, 0.02, 960],
    ]
  );
});

test('AudioWorklet initial empty input cannot publish readiness without later real input', () => {
  const { processor, sandbox } = loadProcessor();
  assert.equal(processor.process([[]]), true);
  sandbox.currentFrame = 128;
  assert.equal(processor.process([[]]), true);
  assert.equal(processor.port.messages.length, 0);

  sandbox.currentFrame = 256;
  assert.equal(processor.process(stereoQuantum(0.75, 0.75)), true);
  assert.equal(processor.port.messages.length, 0);
  for (let index = 0; index < 5; index += 1) {
    sandbox.currentFrame += 128;
    assert.equal(processor.process(stereoQuantum(0.75, 0.75)), true);
  }
  assert.equal(processor.port.messages.length, 1);
  assert.equal(processor.port.messages[0].message.samples[0], 0);
  assert.equal(processor.port.messages[0].message.samples[255], 0);
  assert.equal(processor.port.messages[0].message.samples[256], 0.75);
});

test('AudioWorklet fails closed after a single-gap bound, rolling budget, or clock regression', () => {
  const overBound = loadProcessor();
  assert.equal(overBound.processor.process(stereoQuantum(0, 0)), true);
  overBound.sandbox.currentFrame = 128 + 721;
  assert.equal(overBound.processor.process([[]]), false);
  assert.equal(overBound.processor.port.messages[0].message.kind, 'error');
  assert.equal(overBound.processor.port.messages[0].message.reason, 'input_gap_exceeded');

  const repeated = loadProcessor();
  assert.equal(repeated.processor.process(stereoQuantum(0, 0)), true);
  for (let index = 0; index < 4; index += 1) {
    repeated.sandbox.currentFrame = repeated.processor.expectedRenderFrame + 700;
    assert.equal(repeated.processor.process(stereoQuantum(0, 0)), true);
  }
  repeated.sandbox.currentFrame = repeated.processor.expectedRenderFrame + 700;
  assert.equal(repeated.processor.process(stereoQuantum(0, 0)), false);
  assert.equal(repeated.processor.port.messages.at(-1).message.kind, 'error');
  assert.equal(repeated.processor.port.messages.at(-1).message.reason, 'input_gap_exceeded');

  const regressed = loadProcessor();
  regressed.sandbox.currentFrame = 128;
  assert.equal(regressed.processor.process(stereoQuantum(0, 0)), true);
  regressed.sandbox.currentFrame = 64;
  assert.equal(regressed.processor.process(stereoQuantum(0, 0)), false);
  assert.equal(regressed.processor.port.messages[0].message.kind, 'error');
  assert.equal(regressed.processor.port.messages[0].message.reason, 'render_frame_regressed');
  assert.equal(regressed.processor.process(stereoQuantum(0, 0)), false);
  assert.equal(regressed.processor.port.messages.length, 1);

  const stalled = loadProcessor();
  assert.equal(stalled.processor.process(stereoQuantum(0, 0)), true);
  for (let duplicate = 0; duplicate < 8; duplicate += 1) {
    assert.equal(stalled.processor.process(stereoQuantum(0, 0)), true);
  }
  assert.equal(stalled.processor.process(stereoQuantum(0, 0)), false);
  assert.equal(stalled.processor.port.messages[0].message.kind, 'error');
  assert.equal(stalled.processor.port.messages[0].message.reason, 'render_frame_not_advanced');
  assert.equal(stalled.processor.process(stereoQuantum(0, 0)), false);
  assert.equal(stalled.processor.port.messages.length, 1);
});

test('AudioWorklet fails closed on invalid render-frame values and remains side-effect free', () => {
  for (const invalidFrame of [Number.NaN, -1, 1.5]) {
    const { processor, sandbox } = loadProcessor();
    sandbox.currentFrame = invalidFrame;
    assert.equal(processor.process(stereoQuantum(0, 0)), false);
    assert.equal(processor.port.messages.length, 1);
    assert.equal(processor.port.messages[0].message.kind, 'error');
    assert.equal(processor.port.messages[0].message.reason, 'render_frame_regressed');
    assert.equal(processor.process(stereoQuantum(0, 0)), false);
    assert.equal(processor.port.messages.length, 1);
    assert.equal(processor.pendingLength, 0);
    assert.equal(processor.seq, 0);
  }
});

test('AudioWorklet accepts exact gap budgets and expires them on the rolling timeline', () => {
  const { processor, sandbox } = loadProcessor();
  assert.equal(processor.process(stereoQuantum(0.25, 0.25)), true);

  for (let index = 0; index < 4; index += 1) {
    sandbox.currentFrame = processor.expectedRenderFrame + 720;
    assert.equal(processor.process(stereoQuantum(0.25, 0.25)), true);
  }
  assert.equal(processor.recentInputGapSamples, 2880);

  while (processor.expectedRenderFrame < 48_448) {
    sandbox.currentFrame = processor.expectedRenderFrame;
    assert.equal(processor.process(stereoQuantum(0.25, 0.25)), true);
  }
  sandbox.currentFrame = 48_448;
  assert.equal(processor.process(stereoQuantum(0.25, 0.25)), true);
  assert.equal(processor.recentInputGapSamples, 2560);

  while (processor.expectedRenderFrame < 51_392) {
    sandbox.currentFrame = processor.expectedRenderFrame;
    assert.equal(processor.process(stereoQuantum(0.25, 0.25)), true);
  }
  sandbox.currentFrame = 51_392;
  assert.equal(processor.process(stereoQuantum(0.25, 0.25)), true);
  assert.equal(processor.recentInputGapSamples, 0);

  sandbox.currentFrame = processor.expectedRenderFrame + 720;
  assert.equal(processor.process(stereoQuantum(0.25, 0.25)), true);
  assert.equal(processor.recentInputGapSamples, 720);
  assert.equal(processor.failed, false);
});

test('AudioWorklet rejects a rate that cannot produce an exact 20ms frame', () => {
  const invalid = loadProcessor(44117);
  assert.equal(invalid.processor.process(stereoQuantum(0, 0)), false);
  assert.equal(invalid.processor.port.messages[0].message.kind, 'error');
  assert.equal(invalid.processor.port.messages[0].message.reason, 'invalid_frame_configuration');
});
