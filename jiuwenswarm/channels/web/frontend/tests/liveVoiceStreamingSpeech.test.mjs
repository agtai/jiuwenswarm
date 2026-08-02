import assert from 'node:assert/strict';
import test from 'node:test';

import {
  advanceLiveVoiceStreamingSpeech,
  createLiveVoiceStreamingSpeechState,
} from '../node_modules/.cache/live-voice-streaming-speech/liveVoiceStreamingSpeech.mjs';

function observe(state, rawContent, options = {}) {
  return advanceLiveVoiceStreamingSpeech(state, {
    responseEpoch: options.responseEpoch ?? 1,
    messageId: options.messageId ?? 'assistant-1',
    rawContent,
    phase: options.phase ?? 'streaming',
  });
}

test('waits for a complete sentence and does not release a sentence at the delta edge', () => {
  let result = observe(createLiveVoiceStreamingSpeechState(), '第一句仍在生成');
  assert.equal(result.outcome, 'waiting');
  assert.deepEqual(result.emissions, []);

  result = observe(createLiveVoiceStreamingSpeechState(), '第一句已经完成。');
  assert.equal(result.outcome, 'waiting');
  assert.deepEqual(result.emissions, []);
});

test('releases a completed sentence only after the next sentence provides lookahead', () => {
  const result = observe(createLiveVoiceStreamingSpeechState(), '第一句已经完成。第二句正在生成');

  assert.equal(result.outcome, 'emitted');
  assert.deepEqual(result.emissions, [
    {
      key: 'assistant-1:stream:0',
      text: '第一句已经完成。',
      responseEpoch: 1,
    },
  ]);
  assert.equal(result.state.emittedSpeakablePrefix, '第一句已经完成。');
});

test('repeated and append-only observations emit each stable sentence exactly once', () => {
  let result = observe(createLiveVoiceStreamingSpeechState(), '第一句。第二句');
  assert.deepEqual(
    result.emissions.map(item => item.text),
    ['第一句。']
  );

  result = observe(result.state, '第一句。第二句');
  assert.equal(result.outcome, 'waiting');
  assert.deepEqual(result.emissions, []);

  result = observe(result.state, '第一句。第二句完成！第三句开始');
  assert.deepEqual(result.emissions, [
    {
      key: 'assistant-1:stream:1',
      text: '第二句完成！',
      responseEpoch: 1,
    },
  ]);
});

test('does not treat a decimal point as a stable sentence boundary', () => {
  const result = observe(createLiveVoiceStreamingSpeechState(), '当前数值是 3.14159，计算仍在继续');

  assert.equal(result.outcome, 'waiting');
  assert.deepEqual(result.emissions, []);
});

test('handles an English sentence before lookahead without splitting its decimal', () => {
  const result = observe(createLiveVoiceStreamingSpeechState(), 'Version 3.14159 is stable. Next sentence is starting');

  assert.deepEqual(
    result.emissions.map(item => item.text),
    ['Version 3 点 1 4 1 5 9 is stable.']
  );
});

test('an unclosed code fence blocks early speech until it closes', () => {
  let result = observe(createLiveVoiceStreamingSpeechState(), '介绍已经完成。```ts\nconst value = 1;');
  assert.equal(result.outcome, 'waiting');
  assert.deepEqual(result.emissions, []);

  result = observe(result.state, '介绍已经完成。```ts\nconst value = 1;\n```。结尾已经开始');
  assert.equal(result.outcome, 'emitted');
  assert.deepEqual(
    result.emissions.map(item => item.text),
    ['介绍已经完成。代码块已省略。']
  );
});

test('a stream rewrite before any emission falls back to complete final speech', () => {
  let result = observe(createLiveVoiceStreamingSpeechState(), '原始内容还没有句末');
  result = observe(result.state, '已重写。下一句开始');

  assert.equal(result.outcome, 'final-only');
  assert.equal(result.state.fallbackReason, 'stream-rewrite-before-emission');
  assert.deepEqual(result.emissions, []);

  result = observe(result.state, '最终改写内容。最后一句。', { phase: 'final' });
  assert.equal(result.outcome, 'finalized');
  assert.deepEqual(
    result.emissions.map(item => item.text),
    ['最终改写内容。最后一句']
  );
});

test('a stream rewrite after an emission becomes a mismatch and never replays', () => {
  let result = observe(createLiveVoiceStreamingSpeechState(), '已经说出的第一句。第二句开始');
  assert.equal(result.emissions.length, 1);

  result = observe(result.state, '完全不同的内容。继续生成');
  assert.equal(result.outcome, 'mismatch');
  assert.equal(result.state.fallbackReason, 'stream-rewrite-after-emission');
  assert.deepEqual(result.emissions, []);

  result = observe(result.state, '完全不同的最终内容。', { phase: 'final' });
  assert.equal(result.outcome, 'mismatch');
  assert.deepEqual(result.emissions, []);
});

test('an exact-prefix final emits only the unspoken suffix', () => {
  const streamingRaw = '第一句已经完成。第二句正在生成';
  const finalRaw = '第一句已经完成。第二句最终完成。';
  let result = observe(createLiveVoiceStreamingSpeechState(), streamingRaw);
  const spokenPrefix = result.emissions.map(item => item.text).join('');

  result = observe(result.state, finalRaw, { phase: 'final' });
  const spokenTail = result.emissions.map(item => item.text).join('');

  assert.equal(result.outcome, 'finalized');
  assert.equal(spokenPrefix, '第一句已经完成。');
  assert.equal(spokenTail, '第二句最终完成');
  assert.equal(spokenPrefix + spokenTail, '第一句已经完成。第二句最终完成');
  assert.deepEqual(
    result.emissions.map(item => item.key),
    ['assistant-1:final-tail:1']
  );
});

test('an exact final equal to the emitted prefix adds no duplicate speech', () => {
  let result = observe(createLiveVoiceStreamingSpeechState(), '第一句。第二句开始');
  result = observe(result.state, '第一句。', { phase: 'final' });

  // The final sanitizer removes edge punctuation that was internal in the
  // stream; exact edge normalization is reconciled without fuzzy matching.
  assert.equal(result.outcome, 'finalized');
  assert.deepEqual(result.emissions, []);
});

test('a final prefix mismatch after early speech never emits the complete final', () => {
  let result = observe(createLiveVoiceStreamingSpeechState(), '旧的第一句。第二句开始');
  result = observe(result.state, '更正后的第一句。最终内容。', { phase: 'final' });

  assert.equal(result.outcome, 'mismatch');
  assert.equal(result.state.fallbackReason, 'final-prefix-mismatch');
  assert.deepEqual(result.emissions, []);
});

test('repeating the same final is idempotent while a changed final is rejected', () => {
  let result = observe(createLiveVoiceStreamingSpeechState(), '完整最终回答。', { phase: 'final' });
  assert.equal(result.outcome, 'finalized');
  assert.equal(result.emissions.length, 1);

  result = observe(result.state, '完整最终回答。', { phase: 'final' });
  assert.equal(result.outcome, 'finalized');
  assert.deepEqual(result.emissions, []);

  result = observe(result.state, '最终回答随后被改写。', { phase: 'final' });
  assert.equal(result.outcome, 'mismatch');
  assert.equal(result.state.fallbackReason, 'final-rewrite-after-final');
  assert.deepEqual(result.emissions, []);
});

test('a new responseEpoch resets all cursors and deterministic keys', () => {
  let result = observe(createLiveVoiceStreamingSpeechState(), '旧回答第一句。旧回答继续');
  assert.equal(result.state.responseEpoch, 1);
  assert.equal(result.emissions[0].key, 'assistant-1:stream:0');

  result = observe(result.state, '新回答第一句。新回答继续', {
    responseEpoch: 2,
    messageId: 'assistant-2',
  });

  assert.equal(result.state.responseEpoch, 2);
  assert.equal(result.state.messageId, 'assistant-2');
  assert.deepEqual(result.emissions, [
    {
      key: 'assistant-2:stream:0',
      text: '新回答第一句。',
      responseEpoch: 2,
    },
  ]);
});

test('an older or invalid responseEpoch is ignored without changing current state', () => {
  let result = observe(createLiveVoiceStreamingSpeechState(), '当前回答第一句。当前回答继续', { responseEpoch: 2, messageId: 'assistant-2' });
  const currentState = result.state;

  result = observe(currentState, '迟到的旧回答。仍在继续', {
    responseEpoch: 1,
    messageId: 'assistant-old',
  });
  assert.equal(result.outcome, 'stale-epoch');
  assert.equal(result.state, currentState);
  assert.deepEqual(result.emissions, []);

  result = observe(currentState, '无效回答。仍在继续', {
    responseEpoch: 0,
    messageId: 'assistant-invalid',
  });
  assert.equal(result.outcome, 'stale-epoch');
  assert.equal(result.state, currentState);
  assert.deepEqual(result.emissions, []);
});

test('a message change before emission uses the new message only at final', () => {
  let result = observe(createLiveVoiceStreamingSpeechState(), '尚未完成');
  result = observe(result.state, '新消息。继续生成', { messageId: 'assistant-2' });

  assert.equal(result.outcome, 'final-only');
  assert.equal(result.state.fallbackReason, 'message-changed-before-emission');

  result = observe(result.state, '新消息的最终回答。', {
    messageId: 'assistant-2',
    phase: 'final',
  });
  assert.equal(result.outcome, 'finalized');
  assert.deepEqual(
    result.emissions.map(item => item.text),
    ['新消息的最终回答']
  );
});

test('a message change after emission is a mismatch', () => {
  let result = observe(createLiveVoiceStreamingSpeechState(), '已经释放。继续生成');
  result = observe(result.state, '另一个消息。继续', { messageId: 'assistant-2' });

  assert.equal(result.outcome, 'mismatch');
  assert.equal(result.state.fallbackReason, 'message-changed-after-emission');
  assert.deepEqual(result.emissions, []);
});

test('a collapsed final with a new message id never replays an emitted prefix', () => {
  let result = observe(createLiveVoiceStreamingSpeechState(), '已经提前朗读。后续内容仍在生成', { messageId: 'assistant-streaming' });
  assert.deepEqual(
    result.emissions.map(item => item.text),
    ['已经提前朗读。']
  );

  result = observe(result.state, '已经提前朗读。最终内容完成。', {
    messageId: 'assistant-collapsed-final',
    phase: 'final',
  });

  assert.equal(result.outcome, 'mismatch');
  assert.equal(result.state.fallbackReason, 'message-changed-after-emission');
  assert.deepEqual(result.emissions, []);
});

test('long stable prefixes use the existing lossless bounded chunker', () => {
  const first = `${'甲'.repeat(244)}。`;
  const second = `${'乙'.repeat(269)}！`;
  const result = observe(createLiveVoiceStreamingSpeechState(), `${first}${second}第三句开始`);

  assert.equal(result.outcome, 'emitted');
  assert.deepEqual(
    result.emissions.map(item => item.text),
    [first, second]
  );
  assert.deepEqual(
    result.emissions.map(item => item.key),
    ['assistant-1:stream:0', 'assistant-1:stream:1']
  );
  assert.equal(result.emissions.map(item => item.text).join(''), result.state.emittedSpeakablePrefix);
});
