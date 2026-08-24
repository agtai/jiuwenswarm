import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

import {
  GatewayBatchSpeechClient,
  GatewayBatchSpeechError,
  SPEECH_CAPABILITIES_METHOD,
  SPEECH_CANCEL_METHOD,
  SPEECH_RECOGNIZE_BATCH_METHOD,
  SPEECH_RECOGNIZE_STREAMING_RESULT_METHOD,
  SPEECH_SYNTHESIZE_BATCH_METHOD,
  capturedFramesToPcm16Wav,
} from '../node_modules/.cache/live-voice-gateway-batch-speech/gatewayBatchSpeechClient.mjs';

const backendStreamingFallback = JSON.parse(readFileSync(
  new URL('../../../../../tests/fixtures/live_voice_streaming_recognition_v1/backend_fallback.json', import.meta.url),
  'utf8',
));

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

function frame(generation = 1, seq = 0, value = 0.25, captureId = 'capture-1', trackId = 'track-1') {
  return {
    capture: {
      capture_id: captureId,
      capture_generation: generation,
      track_id: trackId,
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

function capabilityDescriptor(
  supportedOperations = [
    'speech.capabilities.get',
    'speech.recognize.batch',
    'speech.batch.cancel',
  ],
  overrides = {},
) {
  const { declared_limits: declaredLimitOverrides = {}, ...descriptorOverrides } = overrides;
  const declaredLimits = {
    max_input_audio_bytes: 4 * 1024 * 1024,
    max_output_audio_bytes: 8 * 1024 * 1024,
    max_recognition_text_chars: 16_000,
    max_text_chars: 4_000,
    max_timeout_ms: 30_000,
    recognition_input: 'wav_pcm16_mono',
    synthesis_output: 'wav_pcm16_mono',
    resampling: 'server_linear_pcm16_mono',
    credential_boundary: 'gateway_only',
    max_operation_capacity: 128,
    operation_replay_window: 128,
    identity_tombstone_window: 512,
    close_timeout_max_ms: 5_000,
    authorization: 'authenticated_server_owned_exact_binding',
    ...declaredLimitOverrides,
  };
  return {
    component: 'speech.batch.gateway',
    contract_major: 'v2',
    supported_operations: supportedOperations,
    supported_event_types: [],
    batch_modes: ['batch'],
    stream_modes: [],
    supports_cancel_ack: true,
    supports_replay: false,
    fallback_identity: 'browser-speech-compatibility',
    availability: 'available',
    ...descriptorOverrides,
    declared_limits: declaredLimits,
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
      voice_commit_receipt: `voice-receipt-${params.capture.capture_id}`,
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

test('cross-capture final keeps predecessor provenance and one ordered Batch request', async () => {
  const calls = [];
  const transport = {
    async request(method, params) {
      calls.push({ method, params });
      assert.equal(method, SPEECH_RECOGNIZE_BATCH_METHOD);
      assert.deepEqual(params.predecessor.capture, {
        capture_id: 'capture-prefix',
        capture_generation: 1,
        track_id: 'track-prefix',
        final: true,
      });
      assert.equal(params.predecessor.subject_id, 'subject-prefix');
      const prefix = Buffer.from(params.predecessor.audio.data_base64, 'base64');
      const tail = Buffer.from(params.audio.data_base64, 'base64');
      assert.equal(new DataView(prefix.buffer, prefix.byteOffset, prefix.byteLength).getInt16(44, true) < 0, true);
      assert.equal(new DataView(tail.buffer, tail.byteOffset, tail.byteLength).getInt16(44, true) > 0, true);
      return recognitionEnvelope(params);
    },
  };
  const client = new GatewayBatchSpeechClient({ enabled: true, transport, scope, createId: ids() });

  const result = await client.recognizeFinal({
    frames: [frame(2, 0, 0.5, 'capture-tail', 'track-tail')],
    predecessor: {
      subjectId: 'subject-prefix',
      frames: [frame(1, 0, -0.5, 'capture-prefix', 'track-prefix')],
    },
    locale: 'en-US',
    correlationId: 'correlation-1',
  });

  assert.equal(result.final_text, 'formal text');
  assert.equal(result.capture.capture_id, 'capture-tail');
  assert.equal(calls.length, 1);
});

test('cross-capture final rejects equal predecessor and successor generations locally', async () => {
  let transportCalls = 0;
  const client = new GatewayBatchSpeechClient({
    enabled: true,
    scope,
    createId: ids(),
    transport: {
      async request() {
        transportCalls += 1;
        throw new Error('equal generations must fail before transport');
      },
    },
  });

  await assert.rejects(
    client.recognizeFinal({
      frames: [frame(1, 0, 0.5, 'capture-tail', 'track-tail')],
      predecessor: {
        subjectId: 'subject-prefix',
        frames: [frame(1, 0, -0.5, 'capture-prefix', 'track-prefix')],
      },
      locale: 'en-US',
      correlationId: 'correlation-1',
    }),
    error => error.reason === 'CAPTURE_CONTINUATION_IDENTITY_CONFLICT',
  );
  assert.equal(transportCalls, 0);
});

test('real backend streaming fallback fixture crosses into the frontend contract', async () => {
  const client = new GatewayBatchSpeechClient({
    enabled: true,
    scope,
    createId: ids(),
    transport: {
      async request(method, params) {
        assert.equal(method, SPEECH_RECOGNIZE_STREAMING_RESULT_METHOD);
        assert.equal(params.capture_id, backendStreamingFallback.capture.capture_id);
        assert.equal(params.capture_generation, backendStreamingFallback.capture.capture_generation);
        return backendStreamingFallback;
      },
    },
  });

  const decision = await client.recognizeStreamingFinal({
    frames: [frame(0)],
    locale: 'en-US',
    correlationId: 'correlation-1',
    interactionId: 'interaction-1',
  });

  const { status, ...fallback } = backendStreamingFallback;
  assert.deepEqual(decision, { status, fallback });
});

test('diagnostic absence or corruption cannot change the server-owned fallback', async () => {
  for (const [xObsEvent, xObsMetric] of [
    [null, null],
    ['live_voice.speech.degradation', 'live_voice.failure_total'],
    ['failure.observed', 'live_voice.degradation_total'],
  ]) {
    const client = new GatewayBatchSpeechClient({
      enabled: true,
      scope,
      createId: ids(),
      transport: {
        async request() {
          return {
            ...backendStreamingFallback,
            capture: { ...backendStreamingFallback.capture },
            x_obs_event: xObsEvent,
            x_obs_metric: xObsMetric,
          };
        },
      },
    });
    const decision = await client.recognizeStreamingFinal({
      frames: [frame(0)],
      locale: 'en-US',
      correlationId: 'correlation-1',
      interactionId: 'interaction-1',
    });

    assert.equal(decision.status, 'fallback');
    assert.equal(decision.fallback.fallback_tier, 'batch');
    assert.equal(decision.fallback.reason_id, 'STREAMING_SPEECH_EVENT_QUEUE_EXHAUSTED');
    assert.equal(decision.fallback.x_obs_event, xObsEvent === 'failure.observed' && xObsMetric === 'live_voice.failure_total' ? xObsEvent : null);
    assert.equal(decision.fallback.x_obs_metric, xObsEvent === 'failure.observed' && xObsMetric === 'live_voice.failure_total' ? xObsMetric : null);
  }
});

test('authoritative Agent text declares the synthesis event budget and maps exact-rate WAV into AIO-B chunks', async () => {
  const transport = {
    async request(method, params, options) {
      assert.equal(method, SPEECH_SYNTHESIZE_BATCH_METHOD);
      assert.equal(params.authoritative_agent_text, true);
      assert.equal(params.timeout_ms, 15_000);
      assert.equal(options.timeoutMs, 16_000);
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

test('authoritative synthesis accepts one closed dedicated downlink without exposing inline audio', async () => {
  let streamingDescriptor = false;
  const transport = {
    async request(_method, params) {
      const envelope = synthesisEnvelope(params);
      envelope.result.audio = {
        format: 'pcm_f32_mono_20ms',
        sample_rate_hz: 16_000,
        channel_count: 1,
        frame_count: streamingDescriptor ? null : 2,
        delivery: 'dedicated_media_downlink',
        endpoint_path: '/ws/live-voice/media',
        media_ticket: 'S'.repeat(43),
        subprotocol: 'live-voice.media.v1',
        ticket_ttl_ms: 30_000,
        binding: {
          lease_id: 'downlink-lease-1',
          authority_evidence_id: 'downlink-authority-1',
          connection_id: 'connection-1',
          connection_epoch: 0,
          session_id: 'session-1',
          media_session_id: 'media-session-downlink-1',
          interaction_id: params.response.interaction_id,
          track_id: 'playout-track-1',
          correlation_id: params.correlation_id,
          direction: 'downlink',
          generation: {
            kind: 'response',
            id: params.response.response_id,
            value: params.response.response_generation,
          },
          frame_format: {
            sample_rate_hz: 16_000,
            samples_per_channel: 320,
            encoding: 'pcm_f32',
            byte_order: 'little',
            channel_count: 1,
            frame_duration_ms: 20,
          },
          playout: {
            response_id: params.response.response_id,
            response_generation: params.response.response_generation,
            unit_id: params.unit_id,
          },
        },
        max_pending_frames: 8,
        max_pending_bytes: 131_072,
        streaming: streamingDescriptor,
        degradation_reason: null,
      };
      return envelope;
    },
  };
  const client = new GatewayBatchSpeechClient({ enabled: true, transport, scope, createId: ids() });
  const result = await client.synthesizeAuthoritative({
    response: { interaction_id: 'interaction-1', response_id: 'response-1', response_generation: 1 },
    unitId: 'unit-1',
    renderPlan: { display_text: 'Hello', spoken_text: 'Hello', transforms: [] },
    authoritativeAgentText: true,
    locale: 'en-US',
    requiredSampleRateHz: 16_000,
    correlationId: 'correlation-1',
  });

  assert.equal(result.chunks.length, 0);
  assert.equal(result.downlink.frame_count, 2);
  assert.equal(result.downlink.max_pending_frames, 8);
  assert.equal(result.downlink.streaming, false);
  assert.equal(result.downlink.degradation_reason, null);
  assert.equal(Object.hasOwn(result.downlink, 'data_base64'), false);
  assert.equal(Object.hasOwn(result.downlink, 'media_ticket'), false);
  assert.equal(JSON.stringify(result.downlink).includes('S'.repeat(43)), false);
  assert.equal(result.downlink.take_media_ticket(), 'S'.repeat(43));
  assert.throws(() => result.downlink.take_media_ticket(), /already consumed/);
  assert.equal(JSON.stringify(result.downlink).includes('S'.repeat(43)), false);

  streamingDescriptor = true;
  const streamed = await client.synthesizeAuthoritative({
    response: { interaction_id: 'interaction-1', response_id: 'response-2', response_generation: 2 },
    unitId: 'unit-2',
    renderPlan: { display_text: 'World', spoken_text: 'World', transforms: [] },
    authoritativeAgentText: true,
    locale: 'en-US',
    requiredSampleRateHz: 16_000,
    correlationId: 'correlation-1',
  });
  assert.equal(streamed.downlink.frame_count, null);
  assert.equal(streamed.downlink.streaming, true);
  assert.equal(streamed.downlink.degradation_reason, null);
  assert.equal(streamed.downlink.endpoint_path, '/ws/live-voice/media');
  assert.equal(streamed.downlink.take_media_ticket(), 'S'.repeat(43));
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
  assert.deepEqual(capability.degradation, {
    state: 'formal_disabled',
    reason_id: 'FEATURE_DISABLED',
    browser_fallback_is_formal: false,
    browser_fallback_automatic: false,
  });
});

test('flag-off constructor does not inspect transport, scope, or identity hooks', async () => {
  const client = new GatewayBatchSpeechClient({
    enabled: false,
    get transport() { throw new Error('must not inspect transport'); },
    get scope() { throw new Error('must not inspect scope'); },
    get createId() { throw new Error('must not inspect ids'); },
  });

  const capability = await client.capabilities();

  assert.equal(capability.enabled, false);
  assert.equal(capability.formal_available, false);
  assert.equal(capability.fallback.automatic, false);
});

test('Gateway capability maps recognition and synthesis independently without credentials', async () => {
  const transport = {
    async request(method, params) {
      assert.equal(method, SPEECH_CAPABILITIES_METHOD);
      assert.deepEqual(params, { session_id: 'session-1' });
      return {
        contract_version: 'live-voice.contract.v2',
        capability: capabilityDescriptor(),
        provider: {
          available: true,
          provider_id: 'provider-test',
          implementation_class: 'formal',
          provider_configured: true,
          authorization_available: true,
          service_closed: false,
        },
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
  assert.deepEqual(capability.gateway, {
    contract_version: 'live-voice.contract.v2',
    provider_id: 'provider-test',
    provider_available: true,
    provider_configured: true,
    authorization_available: true,
    service_closed: false,
    supported_operations: [
      'speech.capabilities.get',
      'speech.recognize.batch',
      'speech.batch.cancel',
    ],
    evidence_scope: 'sanitized_gateway_batch_speech_capability',
    browser_fallback_is_formal: false,
    browser_fallback_automatic: false,
  });
});

test('Gateway capability accepts the closed legacy resampling mode', async () => {
  const client = new GatewayBatchSpeechClient({
    enabled: true,
    transport: {
      async request() {
        return {
          contract_version: 'live-voice.contract.v2',
          capability: capabilityDescriptor(undefined, {
            declared_limits: { resampling: 'unsupported' },
          }),
          provider: {
            available: true,
            provider_id: 'provider-test',
            implementation_class: 'formal',
            provider_configured: true,
            authorization_available: true,
            service_closed: false,
          },
          fallback: {
            recognition: 'browser-speech-recognition',
            synthesis: 'browser-speech-synthesis',
            automatic: false,
          },
        };
      },
    },
    scope,
    createId: ids(),
  });

  const capability = await client.capabilities();

  assert.equal(capability.formal_available, true);
  assert.equal(capability.recognition_batch, true);
});

test('unconfigured Provider degrades truthfully to explicit non-formal Browser fallback', async () => {
  const client = new GatewayBatchSpeechClient({
    enabled: true,
    transport: {
      async request() {
        return {
          contract_version: 'live-voice.contract.v2',
          capability: capabilityDescriptor(
            ['speech.capabilities.get', 'speech.batch.cancel'],
            { availability: 'unavailable' },
          ),
          provider: {
            available: false,
            provider_id: 'openai-compatible-batch',
            implementation_class: 'unsupported',
            provider_configured: false,
            authorization_available: true,
            service_closed: false,
            api_key: 'must-not-escape',
          },
          fallback: {
            recognition: 'browser-speech-recognition',
            synthesis: 'browser-speech-synthesis',
            automatic: false,
          },
        };
      },
    },
    scope,
    createId: ids(),
  });

  const capability = await client.capabilities();

  assert.equal(capability.formal_available, false);
  assert.equal(capability.recognition_batch, false);
  assert.equal(capability.synthesis_batch, false);
  assert.equal(capability.degradation.state, 'formal_unavailable');
  assert.equal(capability.degradation.reason_id, 'PROVIDER_UNAVAILABLE');
  assert.equal(capability.fallback.automatic, false);
  assert.equal(capability.gateway.provider_configured, false);
  assert.equal(JSON.stringify(capability).includes('must-not-escape'), false);
});

test('malformed capability cannot relabel automatic Browser fallback as formal', async () => {
  const client = new GatewayBatchSpeechClient({
    enabled: true,
    transport: {
      async request() {
        return {
          contract_version: 'live-voice.contract.v2',
          capability: capabilityDescriptor(),
          provider: {
            available: true,
            provider_id: 'provider-test',
            implementation_class: 'formal',
            provider_configured: true,
            authorization_available: true,
            service_closed: false,
          },
          fallback: {
            recognition: 'browser-speech-recognition',
            synthesis: 'browser-speech-synthesis',
            automatic: true,
          },
        };
      },
    },
    scope,
    createId: ids(),
  });

  await assert.rejects(
    client.capabilities(),
    error => error instanceof GatewayBatchSpeechError && error.reason === 'INVALID_SPEECH_CAPABILITY',
  );
});

test('capability drift, duplicates, and contradictory availability fail without formal relabel', async () => {
  const base = {
    contract_version: 'live-voice.contract.v2',
    capability: capabilityDescriptor(),
    provider: {
      available: true,
      provider_id: 'provider-test',
      implementation_class: 'formal',
      provider_configured: true,
      authorization_available: true,
      service_closed: false,
    },
    fallback: {
      recognition: 'browser-speech-recognition',
      synthesis: 'browser-speech-synthesis',
      automatic: false,
    },
  };
  const cases = [
    { capability: capabilityDescriptor([...base.capability.supported_operations, 'speech.private.unknown']) },
    { capability: capabilityDescriptor([...base.capability.supported_operations, 'speech.recognize.batch']) },
    { capability: capabilityDescriptor(['speech.recognize.batch', 'speech.batch.cancel']) },
    { capability: capabilityDescriptor(['speech.capabilities.get', 'speech.recognize.batch']) },
    { capability: capabilityDescriptor(base.capability.supported_operations, { component: 'speech.private.gateway' }) },
    { capability: capabilityDescriptor(base.capability.supported_operations, { contract_major: 'v1' }) },
    { capability: capabilityDescriptor(base.capability.supported_operations, { availability: 'unavailable' }) },
    { capability: capabilityDescriptor(base.capability.supported_operations, { batch_modes: [] }) },
    { capability: capabilityDescriptor(base.capability.supported_operations, { stream_modes: ['stream'] }) },
    { capability: capabilityDescriptor(base.capability.supported_operations, { supports_cancel_ack: false }) },
    { capability: capabilityDescriptor(base.capability.supported_operations, { supports_replay: true }) },
    { capability: capabilityDescriptor(base.capability.supported_operations, { fallback_identity: 'automatic-browser' }) },
    { capability: capabilityDescriptor(base.capability.supported_operations, { private_mode: 'must-reject' }) },
    {
      capability: capabilityDescriptor(base.capability.supported_operations, {
        declared_limits: { recognition_input: 'raw_pcm_f32' },
      }),
    },
    {
      capability: capabilityDescriptor(base.capability.supported_operations, {
        declared_limits: { synthesis_output: 'mp3' },
      }),
    },
    {
      capability: capabilityDescriptor(base.capability.supported_operations, {
        declared_limits: { resampling: 'provider_owned' },
      }),
    },
    {
      capability: capabilityDescriptor(base.capability.supported_operations, {
        declared_limits: { resampling: 'server_sinc_pcm16_mono' },
      }),
    },
    {
      capability: capabilityDescriptor(base.capability.supported_operations, {
        declared_limits: { credential_boundary: 'browser' },
      }),
    },
    {
      capability: capabilityDescriptor(base.capability.supported_operations, {
        declared_limits: { authorization: 'request_asserted' },
      }),
    },
    {
      capability: capabilityDescriptor(base.capability.supported_operations, {
        declared_limits: { operation_replay_window: 127 },
      }),
    },
    {
      capability: capabilityDescriptor(base.capability.supported_operations, {
        declared_limits: { private_credential_mode: 'must-reject' },
      }),
    },
    { provider: { ...base.provider, provider_configured: false } },
    { provider: { ...base.provider, authorization_available: false } },
    { provider: { ...base.provider, service_closed: true } },
    { provider: { ...base.provider, available: false, implementation_class: 'unsupported' } },
    {
      provider: {
        ...base.provider,
        available: false,
        implementation_class: 'unsupported',
        provider_configured: false,
      },
    },
  ];

  for (const changed of cases) {
    let calls = 0;
    const payload = {
      ...base,
      capability: changed.capability ?? base.capability,
      provider: changed.provider ?? base.provider,
    };
    const client = new GatewayBatchSpeechClient({
      enabled: true,
      transport: { async request() { calls += 1; return payload; } },
      scope,
      createId: ids(),
    });

    await assert.rejects(
      client.capabilities(),
      error => error instanceof GatewayBatchSpeechError && error.reason === 'INVALID_SPEECH_CAPABILITY',
    );
    assert.equal(calls, 1);
  }
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

test('malformed authoritative render plans fail before Provider transport', async () => {
  let calls = 0;
  const client = new GatewayBatchSpeechClient({
    enabled: true,
    transport: { async request() { calls += 1; throw new Error('must not run'); } },
    scope,
    createId: ids(),
  });

  const validTransform = {
    transform: 'normalize',
    source_start: 0,
    source_end: 1,
    rendered_text: 'H',
  };
  const invalidPlans = [
    { display_text: '', spoken_text: '', transforms: [] },
    { display_text: ' ', spoken_text: 'Hello', transforms: [] },
    { display_text: 'Hello', spoken_text: 'Hello', transforms: null },
    { display_text: 'Hello', spoken_text: 'Hello', transforms: [null] },
    { display_text: 'Hello', spoken_text: 'Hello', transforms: [{ ...validTransform, transform: '' }] },
    { display_text: 'Hello', spoken_text: 'Hello', transforms: [{ ...validTransform, rendered_text: '' }] },
    { display_text: 'Hello', spoken_text: 'Hello', transforms: [{ ...validTransform, source_start: -1 }] },
    { display_text: 'Hello', spoken_text: 'Hello', transforms: [{ ...validTransform, source_start: 2, source_end: 1 }] },
    { display_text: 'Hello', spoken_text: 'Hello', transforms: [{ ...validTransform, source_end: 6 }] },
    { display_text: 'Hello', spoken_text: 'Hello', transforms: [{ ...validTransform, private_field: true }] },
    { display_text: 'Hello', spoken_text: 'Hello', transforms: [], private_field: true },
  ];

  for (const renderPlan of invalidPlans) {
    await assert.rejects(client.synthesizeAuthoritative({
      response: { interaction_id: 'interaction-1', response_id: 'response-empty', response_generation: 0 },
      unitId: 'unit-1',
      renderPlan,
      authoritativeAgentText: true,
      locale: 'en-US',
      requiredSampleRateHz: 16000,
      correlationId: 'correlation-empty',
    }), error => error instanceof GatewayBatchSpeechError && error.reason === 'INVALID_RENDER_PLAN');
  }
  assert.equal(calls, 0);
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
