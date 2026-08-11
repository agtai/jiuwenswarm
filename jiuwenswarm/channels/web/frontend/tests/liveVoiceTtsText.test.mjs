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

test('regular TTS keeps the historical 500-character default while Live Voice keeps the complete sanitized text', () => {
  const input = `  ${'甲'.repeat(640)}\n\nhttps://example.com/path  `;
  const regular = sanitizeTtsText(input);
  const liveVoice = sanitizeLiveVoiceTtsText(input);

  assert.equal(regular.length, 500);
  assert.equal(regular, '甲'.repeat(500));
  assert.equal(liveVoice, `${'甲'.repeat(640)}`);
  assert.ok(liveVoice.length > regular.length);
});

test('Live Voice applies the same cleanup rules without truncating the result', () => {
  const input = `${'开场。'.repeat(180)}\n\n\`inline\` https://example.com MEDIA:{"kind":"image"} \`\`\`ts\nconst hidden = true\n\`\`\` 收尾。`;
  const regularPrefix = sanitizeTtsText(input);
  const liveVoice = sanitizeLiveVoiceTtsText(input);

  assert.ok(liveVoice.length > 500);
  assert.equal(liveVoice.slice(0, 500).trim(), regularPrefix);
  assert.equal(liveVoice.includes('inline'), true);
  assert.equal(liveVoice.includes('`'), false);
  assert.equal(liveVoice.includes('https://'), false);
  assert.equal(liveVoice.includes('MEDIA:'), false);
  assert.equal(liveVoice.includes('const hidden'), false);
  assert.equal(liveVoice.includes('代码块已省略'), true);
  assert.equal(liveVoice.endsWith('收尾'), true);
});

test('Live Voice makes the observed branch identifier audible without changing surrounding prose', () => {
  const input = 'The current branch is **hx/0731_live_voice_ux**.';

  assert.equal(sanitizeLiveVoiceTtsText(input), 'The current branch is H X 斜杠 0 7 3 1 下划线 live 下划线 voice 下划线 U X.');
  assert.equal(input, 'The current branch is **hx/0731_live_voice_ux**.');
});

test('file-system paths and inline code are retained and made speakable only for Live Voice', () => {
  const input = '检查 `C:\\Users\\demo\\repo\\src\\main.ts` 和 /home/demo/repo/file_01.py。';
  const spoken = sanitizeLiveVoiceTtsText(input);

  assert.equal(sanitizeTtsText(input).includes('Users'), false);
  assert.equal(spoken.includes('C 冒号 反斜杠 Users 反斜杠 demo'), true);
  assert.equal(spoken.includes('S R C 反斜杠 main 点 T S'), true);
  assert.equal(spoken.includes('斜杠 home 斜杠 demo 斜杠 repo 斜杠 file 下划线 0 1 点 P Y'), true);
  assert.equal(spoken.includes('`'), false);
});

test('mixed alphanumeric identifiers and acronyms are spelled while normal prose stays intact', () => {
  const ordinary = 'This is a normal English sentence. 这是一个普通中文句子';
  const technical = 'Build ABC123 with API version v2.0.';

  assert.equal(makeLiveVoiceTextSpeakable(ordinary), ordinary);
  assert.equal(makeLiveVoiceTextSpeakable(technical), 'Build A B C 1 2 3 with A P I version V 2 点 0.');
});

test('inline command words are made audible without rewriting ordinary long words', () => {
  const spoken = sanitizeLiveVoiceTtsText('Run `npm test --short` and inspect `src/utils/ttsText.ts`.');

  assert.equal(spoken, 'Run N P M test 连字符 连字符 short and inspect S R C 斜杠 utils 斜杠 T T S Text 点 T S.');
});

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
