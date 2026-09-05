import assert from 'node:assert/strict';
import test from 'node:test';

import {
  LIVE_VOICE_TTS_MAX_CHUNK_LENGTH,
  LIVE_VOICE_TTS_MIN_CHUNK_LENGTH,
  LIVE_VOICE_TTS_TARGET_CHUNK_LENGTH,
  makeLiveVoiceTextSpeakable,
  sanitizeLiveVoiceTtsText,
  sanitizeTtsText,
  splitLiveVoiceTtsText,
} from '../node_modules/.cache/live-voice-tts-text/utils/ttsText.js';

for (const input of [
  `  ${'甲'.repeat(640)}\n\nhttps://example.com/path  `,
  '官网：https://example.com',
  '```ts\nconst visible = true;\n```',
  'Run `npm test --short` and inspect `src/utils/ttsText.ts`.',
  'The current branch is **hx/0731_live_voice_ux**.',
  'Build ABC123 with API version v2.0. 路径 C:\\Users\\demo 和 /home/demo/file_01.py',
]) {
  test(`all TTS copies preserve text: ${input.slice(0, 32)}`, () => {
    assert.equal(sanitizeTtsText(input), input);
    assert.equal(sanitizeLiveVoiceTtsText(input), input);
    assert.equal(makeLiveVoiceTextSpeakable(input), input);
    assert.equal(splitLiveVoiceTtsText(input).join(''), input);
  });
}

test('sentence endings nearest the target are preferred and every character is preserved', () => {
  const firstSentence = `${'甲'.repeat(244)}。`;
  const secondSentence = `${'乙'.repeat(269)}！`;
  const thirdSentence = `${'C'.repeat(230)}?`;
  const sanitized = `${firstSentence}${secondSentence}${thirdSentence}`;
  const chunks = splitLiveVoiceTtsText(sanitized);

  assert.deepEqual(chunks, [firstSentence, secondSentence, thirdSentence]);
  assert.equal(chunks.join(''), sanitized);
  assert.ok(chunks.every(chunk => chunk.length >= LIVE_VOICE_TTS_MIN_CHUNK_LENGTH));
  assert.ok(chunks.every(chunk => chunk.length <= LIVE_VOICE_TTS_MAX_CHUNK_LENGTH));
});

test('an overlong sentence is hard-split around the target without splitting a surrogate pair', () => {
  const sanitized = `${'长'.repeat(LIVE_VOICE_TTS_TARGET_CHUNK_LENGTH - 1)}😀${'句'.repeat(360)}`;
  const chunks = splitLiveVoiceTtsText(sanitized);

  assert.equal(chunks.join(''), sanitized);
  assert.equal(chunks[0].endsWith('\ud83d'), false);
  assert.equal(chunks[1].startsWith('\ude00'), false);
  assert.ok(chunks.slice(0, -1).every(chunk => chunk.length >= LIVE_VOICE_TTS_MIN_CHUNK_LENGTH));
  assert.ok(chunks.every(chunk => chunk.length <= LIVE_VOICE_TTS_MAX_CHUNK_LENGTH));
});

test('English periods prefer real sentence endings and do not split decimal numbers', () => {
  const decimalPrefix = `${'A'.repeat(225)} 3.14159`;
  const sentence = `${decimalPrefix}${'B'.repeat(25)}. `;
  const tail = `${'C'.repeat(280)}.`;
  const sanitized = `${sentence}${tail}`;
  const chunks = splitLiveVoiceTtsText(sanitized);

  assert.equal(chunks[0], sentence);
  assert.equal(chunks.join(''), sanitized);
});

test('empty and short text stay lossless without manufacturing chunks', () => {
  assert.deepEqual(splitLiveVoiceTtsText(''), []);
  assert.deepEqual(splitLiveVoiceTtsText('简短回答。'), ['简短回答。']);
});
