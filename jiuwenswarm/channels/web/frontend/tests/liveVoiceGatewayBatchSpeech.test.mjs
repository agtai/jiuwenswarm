import assert from 'node:assert/strict';
import test from 'node:test';

import {
  GatewayBatchSpeechClient,
  GatewayBatchSpeechError,
  SPEECH_CAPABILITIES_METHOD,
  SPEECH_CANCEL_METHOD,
  SPEECH_RECOGNIZE_BATCH_METHOD,
  SPEECH_SYNTHESIZE_BATCH_METHOD,
  capturedFramesToPcm16Wav,
} from '../node_modules/.cache/live-voice-gateway-batch-speech/gatewayBatchSpeechClient.mjs';

const scope = Object.freeze({
  subject_id: 'alice',
  project_id: null,
  session_id: 'session-1',
  assurance: 'request_asserted',
});

function ids() {
  let value = 0;
  return () => `generated-${++value}`;
}

function frame(generation = 1, seq = 0, value = 0.25, captureId = 'capture-1') {
  return {
    capture: {
      capture_id: captureId,
      capture_generation: generation,
      track_id: 'track-1',
    },
    seq,
    sample_cursor: seq * 320,
    context_time_s: seq * 0.02,
    format: {
      encoding: 'pcm_f32',
      sample_rate_hz: 16000,
      channel_count: 1,
      frame_duration_ms: 20,
      samples_per_channel: 320,
    },
    samples: new Float32Array(320).fill(value),
  };
}

function pcmWav(sampleRate = 16000, sampleCount = 640) {
  const bytes = new Uint8Array(44 + sampleCount * 2);
  const view = new DataView(bytes.buffer);
  const ascii = (offset, text) => {
    for (let index = 0; index < text.length; index += 1) view.setUint8(offset + index, text.charCodeAt(index));
  };
  ascii(0, 'RIFF');
  view.setUint32(4, bytes.length - 8, true);
  ascii(8, 'WAVE');
  ascii(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  ascii(36, 'data');
  view.setUint32(40, sampleCount * 2, true);
  for (let index = 0; index < sampleCount; index += 1) view.setInt16(44 + index * 2, index % 2 === 0 ? 1000 : -1000, true);
  return bytes;
}

function base64(bytes) {
  return Buffer.from(bytes).toString('base64');
}

function provider(voice) {
  return {
    provider_id: 'provider-test',
    implementation_class: 'formal',
    fallback_from: null,
    model: voice ? 'tts-test' : 'stt-test',
    ...(voice ? { voice } : {}),
  };
}

function recognitionEnvelope(params, generation = params.capture.capture_generation) {
  return {
    contract_version: 'live-voice.contract.v2',
    request_id: params.request_id,
    operation_id: params.operation_id,
    ok: true,
    error: null,
    result: {
      operation: 'speech.recognize.batch',
      capture: { ...params.capture, capture_generation: generation },
      event: {
        session_id: params.capture.capture_id,
        generation,
        seq: 0,
        kind: 'final',
        commits_turn: false,
        hypothesis: {
          alternatives: [{ raw_text: 'raw formal text', display_text: 'formal text', confidence: null }],
          selected_index: 0,
        },
      },
      provider: provider(),
    },
  };
}

function synthesisEnvelope(params, sampleRate = 16000) {
  return {
    contract_version: 'live-voice.contract.v2',
    request_id: params.request_id,
    operation_id: params.operation_id,
    ok: true,
    error: null,
    result: {
      operation: 'speech.synthesize.batch',
      response: { ...params.response },
      unit_id: params.unit_id,
      audio: {
        format: 'wav_pcm16_mono',
        sample_rate_hz: sampleRate,
        channel_count: 1,
        data_base64: base64(pcmWav(sampleRate)),
      },
      provider: provider('voice-test'),
      presented: false,
    },
  };
}

test('AIO-B final frames reach formal SR-B with provenance but never commit a turn', async () => {
  const calls = [];
  const transport = {
    async request(method, params) {
      calls.push({ method, params });
      assert.equal(method, SPEECH_RECOGNIZE_BATCH_METHOD);
      assert.equal(params.audio.format, 'wav_pcm16_mono');
      assert.equal(Buffer.from(params.audio.data_base64, 'base64').subarray(0, 4).toString(), 'RIFF');
      assert.equal(JSON.stringify(params).includes('api_key'), false);
      assert.equal(JSON.stringify(params).includes('server-secret'), false);
      return recognitionEnvelope(params);
    },
  };
  const client = new GatewayBatchSpeechClient({ enabled: true, transport, scope, createId: ids() });

  const result = await client.recognizeFinal({ frames: [frame()], locale: 'en-US', correlationId: 'correlation-1' });

  assert.equal(result.final_text, 'formal text');
  assert.equal(result.commits_turn, false);
  assert.equal(result.provider.implementation_class, 'formal');
  assert.equal(calls.length, 1);
});

test('authoritative Agent text reaches SS-B and maps exact-rate WAV into AIO-B chunks', async () => {
  const transport = {
    async request(method, params) {
      assert.equal(method, SPEECH_SYNTHESIZE_BATCH_METHOD);
      assert.equal(params.authoritative_agent_text, true);
      return synthesisEnvelope(params);
    },
  };
  const client = new GatewayBatchSpeechClient({ enabled: true, transport, scope, createId: ids() });
  const response = { interaction_id: 'interaction-1', response_id: 'response-0', response_generation: 0 };

  const result = await client.synthesizeAuthoritative({
    response,
    unitId: 'unit-1',
    renderPlan: { display_text: 'Hello', spoken_text: 'Hello', transforms: [] },
    authoritativeAgentText: true,
    locale: 'en-US',
    requiredSampleRateHz: 16000,
    correlationId: 'correlation-1',
  });

  assert.equal(result.presented, false);
  assert.equal(result.chunks.length, 2);
  assert.equal(result.chunks[0].samples.length, 320);
  assert.equal(result.chunks[1].seq, 1);
  assert.deepEqual(result.chunks[0].provider, result.provider);
});

test('flag-off preserves Browser Speech fallback without any Gateway side effect', async () => {
  let calls = 0;
  const transport = {
    async request() {
      calls += 1;
      throw new Error('must not run');
    },
  };
  const client = new GatewayBatchSpeechClient({ enabled: false, transport, scope, createId: ids() });

  const capability = await client.capabilities();
  await assert.rejects(
    client.recognizeFinal({ frames: [frame()], locale: 'en-US', correlationId: 'correlation-1' }),
    error => error instanceof GatewayBatchSpeechError && error.reason === 'FEATURE_DISABLED'
  );

  assert.equal(calls, 0);
  assert.deepEqual(capability.fallback, {
    recognition: 'browser-speech-recognition',
    synthesis: 'browser-speech-synthesis',
    automatic: false,
  });
  assert.equal(capability.recognition_batch, false);
  assert.equal(capability.synthesis_batch, false);
});

test('Gateway capability maps recognition and synthesis independently without credentials', async () => {
  const transport = {
    async request(method, params) {
      assert.equal(method, SPEECH_CAPABILITIES_METHOD);
      assert.deepEqual(params, { session_id: 'session-1' });
      return {
        contract_version: 'live-voice.contract.v2',
        capability: { supported_operations: ['speech.recognize.batch'] },
        provider: { available: true, provider_id: 'provider-test' },
        fallback: { recognition: 'browser-speech-recognition', synthesis: 'browser-speech-synthesis', automatic: false },
      };
    },
  };
  const client = new GatewayBatchSpeechClient({ enabled: true, transport, scope, createId: ids() });

  const capability = await client.capabilities();

  assert.equal(capability.formal_available, true);
  assert.equal(capability.recognition_batch, true);
  assert.equal(capability.synthesis_batch, false);
  assert.equal(JSON.stringify(capability).includes('api_key'), false);
});

test('AIO token can skip or restart after Adapter recreation while unique capture ids fence late results', async () => {
  let resolveFirst;
  const calls = [];
  const transport = {
    async request(method, params) {
      calls.push({ method, params });
      if (method === SPEECH_CANCEL_METHOD) return { ok: true };
      if (params.capture.capture_id === 'capture-1') {
        return new Promise(resolve => {
          resolveFirst = () => resolve(recognitionEnvelope(params));
        });
      }
      return recognitionEnvelope(params);
    },
  };
  const client = new GatewayBatchSpeechClient({ enabled: true, transport, scope, createId: ids() });
  const first = client.recognizeFinal({ frames: [frame(1, 0, 0.25, 'capture-1')], locale: 'en-US', correlationId: 'correlation-1' });
  await new Promise(resolve => setImmediate(resolve));
  const second = await client.recognizeFinal({ frames: [frame(3, 0, 0.25, 'capture-2')], locale: 'en-US', correlationId: 'correlation-2' });
  resolveFirst();

  assert.equal(await first, null);
  assert.equal(second.final_text, 'formal text');
  const afterRecreate = await client.recognizeFinal({
    frames: [frame(1, 0, 0.25, 'capture-after-recreate')],
    locale: 'en-US',
    correlationId: 'correlation-after-recreate',
  });
  assert.equal(afterRecreate.final_text, 'formal text');
  await assert.rejects(
    client.recognizeFinal({ frames: [frame(3, 0, 0.25, 'capture-2')], locale: 'en-US', correlationId: 'correlation-3' }),
    error => error instanceof GatewayBatchSpeechError && error.code === 'STALE'
  );
  assert.equal(calls.filter(call => call.method === SPEECH_RECOGNIZE_BATCH_METHOD).length, 3);
  assert.equal(calls.filter(call => call.method === SPEECH_CANCEL_METHOD).length, 1);
});

test('transport timeout requests scoped cancellation and applies no recognition result', async () => {
  const calls = [];
  const transport = {
    async request(method, params) {
      calls.push({ method, params });
      if (method === SPEECH_CANCEL_METHOD) return { ok: true };
      throw Object.assign(new Error('timeout'), { code: 'REQUEST_TIMEOUT' });
    },
  };
  const client = new GatewayBatchSpeechClient({ enabled: true, transport, scope, createId: ids() });

  await assert.rejects(client.recognizeFinal({ frames: [frame()], locale: 'en-US', correlationId: 'correlation-1' }));
  await new Promise(resolve => setImmediate(resolve));

  const cancel = calls.find(call => call.method === SPEECH_CANCEL_METHOD);
  assert.ok(cancel);
  assert.equal(cancel.params.scope.subject_id, 'alice');
  assert.equal(cancel.params.target_operation_id, calls[0].params.operation_id);
});

test('mismatched Provider rate and malformed capture fail closed before AIO application', async () => {
  let calls = 0;
  const transport = {
    async request(_method, params) {
      calls += 1;
      return synthesisEnvelope(params, 24000);
    },
  };
  const client = new GatewayBatchSpeechClient({ enabled: true, transport, scope, createId: ids() });
  await assert.rejects(
    client.synthesizeAuthoritative({
      response: { interaction_id: 'interaction-1', response_id: 'response-0', response_generation: 0 },
      unitId: 'unit-1',
      renderPlan: { display_text: 'Hello', spoken_text: 'Hello', transforms: [] },
      authoritativeAgentText: true,
      locale: 'en-US',
      requiredSampleRateHz: 16000,
      correlationId: 'correlation-1',
    }),
    error => error instanceof GatewayBatchSpeechError && error.reason === 'SPEECH_SAMPLE_RATE_MISMATCH'
  );
  assert.throws(() => capturedFramesToPcm16Wav([frame(0, 1)]), /first AIO-B frame/);
  assert.equal(calls, 1);
});

test('response identity uses structural comparison and rejects delimiter collisions', async () => {
  const expected = { interaction_id: 'a\u0000b', response_id: 'c', response_generation: 0 };
  const transport = {
    async request(_method, params) {
      const result = synthesisEnvelope(params);
      result.result.response = { interaction_id: 'a', response_id: 'b\u0000c', response_generation: 0 };
      return result;
    },
  };
  const client = new GatewayBatchSpeechClient({ enabled: true, transport, scope, createId: ids() });

  await assert.rejects(
    client.synthesizeAuthoritative({
      response: expected,
      unitId: 'unit-1',
      renderPlan: { display_text: 'Hello', spoken_text: 'Hello', transforms: [] },
      authoritativeAgentText: true,
      locale: 'en-US',
      requiredSampleRateHz: 16000,
      correlationId: 'correlation-1',
    }),
    error => error instanceof GatewayBatchSpeechError && error.reason === 'SYNTHESIS_RESULT_MISMATCH'
  );
});
