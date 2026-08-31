import assert from 'node:assert/strict';
import { appendFileSync, mkdtempSync, readFileSync, readdirSync, rmSync, statSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';

import {
  INVALID_DEV_WS_PAYLOAD_REDACTION,
  MEDIA_TICKET_REDACTION,
  PRIVATE_CONTENT_REDACTION,
  RAW_AUDIO_REDACTION,
  RAW_TRANSPORT_DATA_REDACTION,
  SPEECH_TEXT_REDACTION,
  VOICE_COMMIT_RECEIPT_REDACTION,
  prepareDevWsTrafficPayloadForPersistence,
  redactRawAudioForDevLog,
} from '../node_modules/.cache/live-voice-gateway-batch-speech/devWsTrafficPrivacy.mjs';

test('streaming speech result text and commit receipt never reach the dev log', () => {
  const transcript = 'PRIVATE_STREAMING_TRANSCRIPT';
  const receipt = 'PRIVATE_VOICE_COMMIT_RECEIPT';
  const source = {
    type: 'res',
    payload: JSON.stringify({
      status: 'completed',
      final_text: transcript,
      raw_text: transcript,
      voice_commit_receipt: receipt,
    }),
  };

  const sanitized = redactRawAudioForDevLog(source);
  const payload = JSON.parse(sanitized.payload);

  assert.equal(payload.final_text, SPEECH_TEXT_REDACTION);
  assert.equal(payload.raw_text, SPEECH_TEXT_REDACTION);
  assert.equal(payload.voice_commit_receipt, VOICE_COMMIT_RECEIPT_REDACTION);
  assert.equal(JSON.stringify(sanitized).includes(transcript), false);
  assert.equal(JSON.stringify(sanitized).includes(receipt), false);
  assert.equal(source.payload.includes(transcript), true);
});

test('real recognition alternatives and synthesis render plans redact display and spoken text variants', () => {
  const privateValues = Array.from({ length: 11 }, (_, index) => 'PRIVATE_RENDER_TEXT_' + index);
  const source = {
    type: 'res',
    id: 'speech-render-1',
    ok: true,
    payload: JSON.stringify({
      status: 'completed',
      event: {
        hypothesis: {
          alternatives: [
            {
              display_text: privateValues[0],
              displayText: privateValues[1],
              'DISPLAY-TEXT': privateValues[2],
              confidence: 0.91,
            },
          ],
          selected_index: 0,
        },
      },
      deliveries: [
        {
          render_plan: {
            display_text: privateValues[3],
            spoken_text: privateValues[4],
            transforms: [
              {
                transform: 'abbreviation',
                source_start: 0,
                source_end: 3,
                rendered_text: privateValues[5],
              },
            ],
          },
        },
      ],
      compact_variants: [
        { spokenText: privateValues[6] },
        { 'SPOKEN-TEXT': privateValues[7] },
        { renderedText: privateValues[8] },
        { 'rendered_-text': privateValues[9] },
        { Display__Text: privateValues[10] },
      ],
      provider: 'safe-provider-id',
    }),
  };

  const sanitized = redactRawAudioForDevLog(source);
  const payload = JSON.parse(sanitized.payload);

  assert.deepEqual(payload.event.hypothesis.alternatives[0], {
    display_text: SPEECH_TEXT_REDACTION,
    displayText: SPEECH_TEXT_REDACTION,
    'DISPLAY-TEXT': SPEECH_TEXT_REDACTION,
    confidence: 0.91,
  });
  assert.deepEqual(payload.deliveries[0].render_plan, {
    display_text: SPEECH_TEXT_REDACTION,
    spoken_text: SPEECH_TEXT_REDACTION,
    transforms: [
      {
        transform: 'abbreviation',
        source_start: 0,
        source_end: 3,
        rendered_text: SPEECH_TEXT_REDACTION,
      },
    ],
  });
  assert.equal(payload.compact_variants[0].spokenText, SPEECH_TEXT_REDACTION);
  assert.equal(payload.compact_variants[1]['SPOKEN-TEXT'], SPEECH_TEXT_REDACTION);
  assert.equal(payload.compact_variants[2].renderedText, SPEECH_TEXT_REDACTION);
  assert.equal(payload.compact_variants[3]['rendered_-text'], SPEECH_TEXT_REDACTION);
  assert.equal(payload.compact_variants[4].Display__Text, SPEECH_TEXT_REDACTION);
  assert.equal(payload.provider, 'safe-provider-id');
  for (const privateValue of privateValues) {
    assert.equal(JSON.stringify(sanitized).includes(privateValue), false);
    assert.equal(source.payload.includes(privateValue), true);
  }
});

test('speech compact keys remove every non-ASCII-alphanumeric separator without touching safe metadata', () => {
  const privateValues = Array.from({ length: 6 }, (_, index) => `PRIVATE_SEPARATOR_TEXT_${index}`);
  const source = {
    'display.text': privateValues[0],
    'spoken text': privateValues[1],
    'rendered/text': privateValues[2],
    'fi--nal_ / .. text': privateValues[3],
    'raw. _-/ text': privateValues[4],
    'voice // commit_-. receipt': privateValues[5],
    rendered_text_digest: 'safe-rendered-digest',
    display_text_confidence: 0.98,
    spoken_text_locale: 'en-GB',
    provider: 'safe-provider-id',
  };
  const before = JSON.stringify(source);

  const sanitized = redactRawAudioForDevLog(source);

  assert.deepEqual(sanitized, {
    'display.text': SPEECH_TEXT_REDACTION,
    'spoken text': SPEECH_TEXT_REDACTION,
    'rendered/text': SPEECH_TEXT_REDACTION,
    'fi--nal_ / .. text': SPEECH_TEXT_REDACTION,
    'raw. _-/ text': SPEECH_TEXT_REDACTION,
    'voice // commit_-. receipt': VOICE_COMMIT_RECEIPT_REDACTION,
    rendered_text_digest: 'safe-rendered-digest',
    display_text_confidence: 0.98,
    spoken_text_locale: 'en-GB',
    provider: 'safe-provider-id',
  });
  assert.equal(JSON.stringify(source), before);
  for (const privateValue of privateValues) {
    assert.equal(JSON.stringify(sanitized).includes(privateValue), false);
  }
});

test('malformed JSON display and spoken text variants fail closed', () => {
  const privateValues = Array.from({ length: 6 }, (_, index) => 'PRIVATE_MALFORMED_RENDER_TEXT_' + index);
  const variants = [
    '{"display_text":"' + privateValues[0] + '"',
    '{"displayText":"' + privateValues[1] + '"',
    '{"DISPLAY-TEXT":"' + privateValues[2] + '"',
    '{"spoken_text":"' + privateValues[3] + '"',
    '{"spokenText":"' + privateValues[4] + '"',
    '{"SPOKEN_-TEXT":"' + privateValues[5] + '"',
  ];
  const source = { type: 'res', payload: JSON.stringify({ malformed: variants, status: 'failed' }) };

  const sanitized = redactRawAudioForDevLog(source);
  const payload = JSON.parse(sanitized.payload);

  assert.deepEqual(
    payload.malformed,
    variants.map(() => RAW_TRANSPORT_DATA_REDACTION),
  );
  assert.equal(payload.status, 'failed');
  for (const privateValue of privateValues) {
    assert.equal(JSON.stringify(sanitized).includes(privateValue), false);
    assert.equal(source.payload.includes(privateValue), true);
  }
});

test('JSON-looking malformed object and array strings fail closed without private-key regex matching', () => {
  const privateValues = Array.from({ length: 3 }, (_, index) => `PRIVATE_MALFORMED_JSON_SHAPE_${index}`);
  const malformed = [String.raw`{"\u0064isplay_text":"${privateValues[0]}"`, `  {"safe_metadata":"${privateValues[1]}"`, `\n\t["${privateValues[2]}"`];
  const source = {
    type: 'res',
    payload: JSON.stringify({ malformed, ordinary: 'ordinary diagnostic' }),
  };
  const before = JSON.stringify(source);

  const sanitized = redactRawAudioForDevLog(source);
  const payload = JSON.parse(sanitized.payload);

  assert.deepEqual(
    payload.malformed,
    malformed.map(() => RAW_TRANSPORT_DATA_REDACTION),
  );
  assert.equal(payload.ordinary, 'ordinary diagnostic');
  assert.equal(JSON.stringify(source), before);
  for (const privateValue of privateValues) {
    assert.equal(JSON.stringify(sanitized).includes(privateValue), false);
  }
});

test('JSON-wrapped and malformed speech key variants fail closed', () => {
  const privateValues = Array.from({ length: 10 }, (_, index) => `PRIVATE_SPEECH_VARIANT_${index}`);
  const source = {
    type: 'res',
    payload: JSON.stringify({
      finalText: privateValues[0],
      final_text: privateValues[1],
      'final-text': privateValues[2],
      rawtext: privateValues[3],
      rawText: privateValues[4],
      voiceCommitReceipt: privateValues[5],
      wrapped: JSON.stringify({ 'RAW-TEXT': privateValues[6] }),
      malformedCamel: `{"voiceCommitReceipt":"${privateValues[7]}"`,
      malformedCompact: `{"rawtext":"${privateValues[8]}"`,
      malformedMixed: `{"final_-text":"${privateValues[9]}"`,
      finalTextDigest: 'safe-final-digest',
      drawText: 'safe-drawing-label',
      voiceCommitmentReceipt: 'safe-near-miss',
    }),
  };

  const sanitized = redactRawAudioForDevLog(source);
  const payload = JSON.parse(sanitized.payload);

  assert.equal(payload.finalText, SPEECH_TEXT_REDACTION);
  assert.equal(payload.final_text, SPEECH_TEXT_REDACTION);
  assert.equal(payload['final-text'], SPEECH_TEXT_REDACTION);
  assert.equal(payload.rawtext, SPEECH_TEXT_REDACTION);
  assert.equal(payload.rawText, SPEECH_TEXT_REDACTION);
  assert.equal(payload.voiceCommitReceipt, VOICE_COMMIT_RECEIPT_REDACTION);
  assert.equal(JSON.parse(payload.wrapped)['RAW-TEXT'], SPEECH_TEXT_REDACTION);
  assert.equal(payload.malformedCamel, RAW_TRANSPORT_DATA_REDACTION);
  assert.equal(payload.malformedCompact, RAW_TRANSPORT_DATA_REDACTION);
  assert.equal(payload.malformedMixed, RAW_TRANSPORT_DATA_REDACTION);
  assert.equal(payload.finalTextDigest, 'safe-final-digest');
  assert.equal(payload.drawText, 'safe-drawing-label');
  assert.equal(payload.voiceCommitmentReceipt, 'safe-near-miss');
  for (const privateValue of privateValues) {
    assert.equal(JSON.stringify(sanitized).includes(privateValue), false);
  }
});

test('media tickets are removed recursively and from JSON-wrapped persistence payloads', () => {
  const ticket = 'PRIVATE_MEDIA_TICKET_8f2c6bb7d6af4ea78bf07a3e9ebf8505';
  const source = {
    type: 'res',
    payload: JSON.stringify({
      media_ticket: ticket,
      nested: [{ 'media-ticket': ticket }],
    }),
  };

  const sanitized = redactRawAudioForDevLog(source);
  const payload = JSON.parse(sanitized.payload);

  assert.equal(payload.media_ticket, MEDIA_TICKET_REDACTION);
  assert.equal(payload.nested[0]['media-ticket'], MEDIA_TICKET_REDACTION);
  assert.equal(JSON.stringify(sanitized).includes(ticket), false);
  assert.equal(source.payload.includes(ticket), true);
  assert.equal(redactRawAudioForDevLog({ type: 'res', payload: `{"media_ticket":"${ticket}"` }).payload, RAW_TRANSPORT_DATA_REDACTION);
});

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
    }),
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
    // F12 收紧：text 是承载已提交语音的真实线上字段，任何上下文一律脱敏。
    text: PRIVATE_CONTENT_REDACTION,
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

test('actual persistence-boundary output contains no raw audio or speech text anywhere on disk', () => {
  const directory = mkdtempSync(join(tmpdir(), 'live-voice-route-to-disk-'));
  const logFile = join(directory, 'ws-dev.log');
  const sentinel = 'RAW_AUDIO_SENTINEL_8f2c6bb7d6af4ea78bf07a3e9ebf8505';
  const displaySentinel = 'DISPLAY_TEXT_SENTINEL_8f2c6bb7d6af4ea78bf07a3e9ebf8505';
  const spokenSentinel = 'SPOKEN_TEXT_SENTINEL_8f2c6bb7d6af4ea78bf07a3e9ebf8505';
  const renderedSentinel = 'RENDERED_TEXT_SENTINEL_8f2c6bb7d6af4ea78bf07a3e9ebf8505';
  try {
    const envelopes = [
      {
        direction: 'outgoing',
        data: {
          method: 'live_voice.speech.recognize_batch',
          params: { audio: { format: 'wav_pcm16_mono', data_base64: sentinel } },
        },
      },
      {
        direction: 'incoming',
        data: {
          type: 'res',
          payload: JSON.stringify({ audio: { data_base64: sentinel } }),
        },
      },
      {
        direction: 'incoming',
        data: { rawData: `{"audio":{"data_base64":"${sentinel}"`, parse: 'failed' },
      },
      {
        direction: 'incoming',
        data: {
          type: 'res',
          payload: JSON.stringify({
            event: {
              hypothesis: {
                alternatives: [{ display_text: displaySentinel, confidence: 0.91 }],
                selected_index: 0,
              },
            },
          }),
        },
      },
      {
        direction: 'outgoing',
        data: {
          method: 'live_voice.speech.synthesize_batch',
          params: {
            render_plan: {
              display_text: displaySentinel,
              spoken_text: spokenSentinel,
              transforms: [
                {
                  transform: 'none',
                  source_start: 0,
                  source_end: 1,
                  rendered_text: renderedSentinel,
                },
              ],
            },
          },
        },
      },
    ];

    for (const envelope of envelopes) {
      const payload = prepareDevWsTrafficPayloadForPersistence(JSON.stringify(envelope));
      appendFileSync(logFile, `${JSON.stringify({ ts: '2026-08-07T00:00:00.000Z', payload })}\n`, 'utf8');
    }

    const persistedFiles = readdirSync(directory, { recursive: true })
      .map(entry => join(directory, String(entry)))
      .filter(path => statSync(path).isFile());
    assert.deepEqual(persistedFiles, [logFile]);
    const persisted = persistedFiles.map(path => readFileSync(path, 'utf8')).join('\n');
    assert.equal(persisted.includes(sentinel), false);
    assert.equal(persisted.includes(displaySentinel), false);
    assert.equal(persisted.includes(spokenSentinel), false);
    assert.equal(persisted.includes(renderedSentinel), false);
    assert.equal(persisted.includes(RAW_AUDIO_REDACTION), true);
    assert.equal(persisted.includes(SPEECH_TEXT_REDACTION), true);
    assert.equal(persisted.includes(RAW_TRANSPORT_DATA_REDACTION), true);
    const persistedEntries = persisted
      .trim()
      .split('\n')
      .map(line => JSON.parse(line));
    const recognitionPayload = JSON.parse(persistedEntries[3].payload.data.payload);
    assert.equal(recognitionPayload.event.hypothesis.alternatives[0].confidence, 0.91);
    assert.deepEqual(persistedEntries[4].payload.data.params.render_plan, {
      display_text: SPEECH_TEXT_REDACTION,
      spoken_text: SPEECH_TEXT_REDACTION,
      transforms: [
        {
          transform: 'none',
          source_start: 0,
          source_end: 1,
          rendered_text: SPEECH_TEXT_REDACTION,
        },
      ],
    });
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});

test('committed speech, task names, instructions and adjustments never reach the dev log', () => {
  const canaries = {
    text: 'CANARY_COMMITTED_SPEECH',
    name: 'CANARY_TASK_NAME',
    instruction: 'CANARY_TASK_INSTRUCTION',
    adjustment: 'CANARY_TASK_ADJUSTMENT',
    message: 'CANARY_CHAT_MESSAGE',
    content: 'CANARY_CHAT_CONTENT',
    query: 'CANARY_CHAT_QUERY',
  };
  const source = {
    direction: 'outgoing',
    messageType: 'req',
    data: {
      type: 'req',
      id: 'req-1',
      method: 'live_voice.composition.unified.submit',
      params: {
        session_id: 'session-1',
        text: canaries.text,
        name: canaries.name,
        task_name: canaries.name,
        instruction: canaries.instruction,
        instructions: [canaries.instruction],
        adjustment: canaries.adjustment,
        adjustments: [canaries.adjustment],
        message: canaries.message,
        content: canaries.content,
        query: canaries.query,
        nested: JSON.stringify({ instruction: canaries.instruction, task_name: canaries.name }),
      },
    },
  };

  const sanitized = prepareDevWsTrafficPayloadForPersistence(JSON.stringify(source));
  const serialized = JSON.stringify(sanitized);
  for (const [key, canary] of Object.entries(canaries)) {
    assert.equal(serialized.includes(canary), false, `${key} canary leaked: ${serialized}`);
  }
  // 诊断价值保留：方法名与非敏感标识仍然可见。
  assert.equal(serialized.includes('live_voice.composition.unified.submit'), true);
  assert.equal(serialized.includes('session-1'), true);
  assert.equal(serialized.includes('req-1'), true);
});

test('a throwing payload fails closed to the fixed marker, never the original data', () => {
  const source = {};
  Object.defineProperty(source, 'boom', {
    enumerable: true,
    get() {
      throw new Error('CANARY_THROWING_GETTER');
    },
  });
  const sanitized = redactRawAudioForDevLog({ data: source });
  assert.equal(sanitized, INVALID_DEV_WS_PAYLOAD_REDACTION);
});
