import assert from 'node:assert/strict';
import test from 'node:test';

import {
  INVALID_DEV_WS_PAYLOAD_REDACTION,
  RAW_AUDIO_REDACTION,
  RAW_TRANSPORT_DATA_REDACTION,
  prepareDevWsTrafficPayloadForPersistence,
  redactRawAudioForDevLog,
} from '../node_modules/.cache/live-voice-gateway-batch-speech/devWsTrafficPrivacy.mjs';

test('recursive log copy removes request and response audio without mutating WebSocket data', () => {
  const rawRequestAudio = 'UklGRlJFUVVFU1Q=';
  const rawResponseAudio = 'UklGRlJFU1BPTlNF';
  const message = {
    type: 'req',
    id: 'speech-1',
    method: 'live_voice.speech.recognize',
    params: {
      audio: {
        format: 'wav_pcm16_mono',
        data_base64: rawRequestAudio,
      },
      nested: [{ data_base64: rawResponseAudio, sample_rate_hz: 16000 }],
      data_base64_digest: 'allowed-near-miss',
      metadata_base64: 'allowed-metadata',
      dataBase64: 'allowed-camel-case',
      DATA_BASE64: 'allowed-uppercase',
      authorization: 'kept-for-the-existing-secret-mask',
    },
  };
  const wireBytesBeforeLogging = JSON.stringify(message);

  const redacted = redactRawAudioForDevLog(message);

  assert.equal(redacted.params.audio.data_base64, RAW_AUDIO_REDACTION);
  assert.equal(redacted.params.nested[0].data_base64, RAW_AUDIO_REDACTION);
  assert.equal(redacted.params.data_base64_digest, 'allowed-near-miss');
  assert.equal(redacted.params.metadata_base64, 'allowed-metadata');
  assert.equal(redacted.params.dataBase64, 'allowed-camel-case');
  assert.equal(redacted.params.DATA_BASE64, 'allowed-uppercase');
  assert.equal(redacted.params.authorization, 'kept-for-the-existing-secret-mask');
  assert.equal(message.params.audio.data_base64, rawRequestAudio);
  assert.equal(message.params.nested[0].data_base64, rawResponseAudio);
  assert.equal(JSON.stringify(message), wireBytesBeforeLogging);
  assert.equal(JSON.stringify(redacted).includes(rawRequestAudio), false);
  assert.equal(JSON.stringify(redacted).includes(rawResponseAudio), false);
});

test('persistence parser sanitizes valid objects and fails closed for malformed bodies', () => {
  const rawAudio = 'UklGRk1BTEZPUk1FRA==';
  const sanitized = prepareDevWsTrafficPayloadForPersistence(
    JSON.stringify({
      direction: 'incoming',
      data: { result: { audio: { data_base64: rawAudio } } },
    })
  );

  assert.equal(sanitized.data.result.audio.data_base64, RAW_AUDIO_REDACTION);
  assert.equal(JSON.stringify(sanitized).includes(rawAudio), false);
  assert.equal(prepareDevWsTrafficPayloadForPersistence(`{"data_base64":"${rawAudio}"`), INVALID_DEV_WS_PAYLOAD_REDACTION);
  assert.equal(prepareDevWsTrafficPayloadForPersistence(JSON.stringify(`{"data_base64":"${rawAudio}"}`)), INVALID_DEV_WS_PAYLOAD_REDACTION);
  assert.equal(prepareDevWsTrafficPayloadForPersistence(JSON.stringify(42)), INVALID_DEV_WS_PAYLOAD_REDACTION);
});

test('real parse-failed WebSocket envelope cannot persist its malformed raw carrier', () => {
  const rawAudio = 'UklGRlBBUlNFLUZBSUxFRA==';
  const malformedWebSocketData = `{"result":{"audio":{"data_base64":"${rawAudio}"}`;
  const reportedEnvelope = {
    direction: 'incoming',
    data: { rawData: malformedWebSocketData, parse: 'failed' },
  };

  const sanitized = prepareDevWsTrafficPayloadForPersistence(JSON.stringify(reportedEnvelope));

  assert.equal(sanitized.data.rawData, RAW_TRANSPORT_DATA_REDACTION);
  assert.equal(sanitized.data.parse, 'failed');
  assert.equal(JSON.stringify(sanitized).includes(rawAudio), false);
  assert.equal(JSON.stringify(sanitized).includes(malformedWebSocketData), false);
  assert.equal(reportedEnvelope.data.rawData, malformedWebSocketData);
});

test('real normalize-ignored string envelope cannot persist nested raw text', () => {
  const rawAudio = 'UklGRklHTk9SRUQ=';
  const parsedString = `{"audio":{"data_base64":"${rawAudio}"}}`;
  const reportedEnvelope = {
    direction: 'incoming',
    data: { parsed: parsedString, normalize: 'ignored' },
  };

  const sanitized = prepareDevWsTrafficPayloadForPersistence(JSON.stringify(reportedEnvelope));

  assert.equal(sanitized.data.parsed, RAW_TRANSPORT_DATA_REDACTION);
  assert.equal(sanitized.data.normalize, 'ignored');
  assert.equal(JSON.stringify(sanitized).includes(rawAudio), false);
  assert.equal(reportedEnvelope.data.parsed, parsedString);
});

test('normalize-ignored arrays redact the whole parsed carrier', () => {
  const rawAudio = 'UklGRklHTk9SRUQtQVJSQVk=';
  const parsedArray = [{ safe: true }, `{"data_base64":"${rawAudio}"}`];
  const reportedEnvelope = {
    direction: 'incoming',
    data: { parsed: parsedArray, normalize: 'ignored' },
  };

  const sanitized = prepareDevWsTrafficPayloadForPersistence(JSON.stringify(reportedEnvelope));

  assert.equal(sanitized.data.parsed, RAW_TRANSPORT_DATA_REDACTION);
  assert.equal(JSON.stringify(sanitized).includes(rawAudio), false);
  assert.deepEqual(reportedEnvelope.data.parsed, parsedArray);
});

test('ordinary rawData and parsed fields retain diagnostics outside reporter failure carriers', () => {
  const source = {
    rawData: 'ordinary diagnostic',
    parsed: { status: 'ordinary', nested: { data_base64: 'RAW' } },
  };

  const sanitized = redactRawAudioForDevLog(source);

  assert.equal(sanitized.rawData, 'ordinary diagnostic');
  assert.equal(sanitized.parsed.status, 'ordinary');
  assert.equal(sanitized.parsed.nested.data_base64, RAW_AUDIO_REDACTION);
  assert.equal(source.parsed.nested.data_base64, 'RAW');
});

test('real incoming response sanitizes JSON-wrapped payload without changing normal strings', () => {
  const rawAudio = 'UklGRlNUUklORy1XUkFQUEVE';
  const wrappedPayload = JSON.stringify({ audio: { data_base64: rawAudio }, text: 'kept' });
  const reportedEnvelope = {
    direction: 'incoming',
    messageType: 'res',
    data: { type: 'res', id: 'speech-1', ok: true, payload: wrappedPayload },
  };

  const sanitized = prepareDevWsTrafficPayloadForPersistence(JSON.stringify(reportedEnvelope));

  assert.equal(typeof sanitized.data.payload, 'string');
  assert.deepEqual(JSON.parse(sanitized.data.payload), {
    audio: { data_base64: RAW_AUDIO_REDACTION },
    text: 'kept',
  });
  assert.equal(JSON.stringify(sanitized).includes(rawAudio), false);
  assert.equal(reportedEnvelope.data.payload, wrappedPayload);

  const normal = { type: 'res', payload: 'ordinary Chat response' };
  assert.deepEqual(redactRawAudioForDevLog(normal), normal);
  assert.equal(redactRawAudioForDevLog({ type: 'res', payload: '{"data_base64":"RAW"' }).payload, RAW_TRANSPORT_DATA_REDACTION);
});

test('exact raw-audio key is redacted for every JSON value type', () => {
  const values = ['audio', 7, true, null, { nested: 'audio' }, ['audio']];
  for (const value of values) {
    const source = { data_base64: value };
    assert.deepEqual(redactRawAudioForDevLog(source), {
      data_base64: RAW_AUDIO_REDACTION,
    });
    assert.deepEqual(source, { data_base64: value });
  }
});
