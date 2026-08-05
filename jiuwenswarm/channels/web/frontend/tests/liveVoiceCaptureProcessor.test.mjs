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

test('AudioWorklet fails closed on missing input or a render-frame gap', () => {
  const missing = loadProcessor();
  assert.equal(missing.processor.process([[]]), false);
  assert.equal(missing.processor.port.messages[0].message.kind, 'error');
  assert.equal(missing.processor.port.messages[0].message.reason, 'missing_input');

  const gap = loadProcessor();
  assert.equal(gap.processor.process(stereoQuantum(0, 0)), true);
  gap.sandbox.currentFrame = 256;
  assert.equal(gap.processor.process(stereoQuantum(0, 0)), false);
  assert.equal(gap.processor.port.messages[0].message.kind, 'error');
  assert.equal(gap.processor.port.messages[0].message.reason, 'render_gap');
});

test('AudioWorklet rejects a rate that cannot produce an exact 20ms frame', () => {
  const invalid = loadProcessor(44117);
  assert.equal(invalid.processor.process(stereoQuantum(0, 0)), false);
  assert.equal(invalid.processor.port.messages[0].message.kind, 'error');
  assert.equal(invalid.processor.port.messages[0].message.reason, 'invalid_frame_configuration');
});
