import assert from 'node:assert/strict';
import test from 'node:test';

import { selectLiveVoiceResponseMessages } from '../node_modules/.cache/live-voice-message-gate/features/live-voice/liveVoiceMessageGate.js';

function message(id, role, content, options = {}) {
  return {
    id,
    role,
    content,
    timestamp: `2026-07-31T00:00:${id}.000Z`,
    ...options,
  };
}

test('an unknown boundary resolves to the latest matching user transcript', () => {
  const messages = [
    message('user-old', 'user', '检查 当前仓库'),
    message('assistant-old', 'assistant', '历史回答'),
    message('user-other', 'user', '另一个问题'),
    message('assistant-other', 'assistant', '另一个历史回答'),
    message('user-current', 'user', '  检查\n当前仓库  '),
    message('assistant-current', 'assistant', '当前回答'),
  ];

  const result = selectLiveVoiceResponseMessages({
    messages,
    voiceTranscript: '检查 当前仓库',
    isProcessing: false,
    spokenMessageIds: new Set(),
  });

  assert.equal(result.userBoundaryId, 'user-current');
  assert.deepEqual(
    result.speakableMessages.map(item => item.id),
    ['assistant-current']
  );
});

test('a known user boundary remains authoritative for repeated transcripts', () => {
  const messages = [
    message('user-known', 'user', '继续'),
    message('assistant-known', 'assistant', '第一轮回答'),
    message('user-later', 'user', '继续'),
    message('assistant-later', 'assistant', '第二轮回答'),
  ];

  const result = selectLiveVoiceResponseMessages({
    messages,
    voiceTranscript: '继续',
    knownUserBoundaryId: 'user-known',
    isProcessing: false,
    spokenMessageIds: new Set(),
  });

  assert.equal(result.userBoundaryId, 'user-known');
  assert.deepEqual(
    result.speakableMessages.map(item => item.id),
    ['assistant-known']
  );
});

test('an invalid known boundary falls back to the latest transcript match', () => {
  const messages = [message('not-a-user', 'system', '继续'), message('user-current', 'user', '继续'), message('assistant-current', 'assistant', '好的')];

  const result = selectLiveVoiceResponseMessages({
    messages,
    voiceTranscript: '继续',
    knownUserBoundaryId: 'not-a-user',
    isProcessing: false,
    spokenMessageIds: new Set(),
  });

  assert.equal(result.userBoundaryId, 'user-current');
  assert.deepEqual(
    result.speakableMessages.map(item => item.id),
    ['assistant-current']
  );
});

test('processing resolves the boundary but releases no assistant messages', () => {
  const messages = [message('user-current', 'user', '检查仓库'), message('assistant-current', 'assistant', '尚未完成')];

  const result = selectLiveVoiceResponseMessages({
    messages,
    voiceTranscript: '检查仓库',
    isProcessing: true,
    spokenMessageIds: new Set(),
  });

  assert.equal(result.userBoundaryId, 'user-current');
  assert.deepEqual(result.speakableMessages, []);
  assert.equal(result.streamingCandidate, null);
});

test('processing exposes one streaming assistant candidate without making it final-speakable', () => {
  const messages = [
    message('user-current', 'user', 'voice request'),
    message('assistant-streaming', 'assistant', '第一句已经完成。第二句正在生成', { isStreaming: true }),
  ];

  const result = selectLiveVoiceResponseMessages({
    messages,
    voiceTranscript: 'voice request',
    isProcessing: true,
    spokenMessageIds: new Set(),
  });

  assert.deepEqual(result.speakableMessages, []);
  assert.equal(result.streamingCandidate?.id, 'assistant-streaming');
});

test('multiple assistant messages conservatively disable streaming preview', () => {
  const messages = [
    message('user-current', 'user', 'voice request'),
    message('assistant-first', 'assistant', '第一段', { isStreaming: false }),
    message('assistant-streaming', 'assistant', '第二段仍在生成', { isStreaming: true }),
  ];

  const result = selectLiveVoiceResponseMessages({
    messages,
    voiceTranscript: 'voice request',
    isProcessing: true,
    spokenMessageIds: new Set(),
  });

  assert.equal(result.streamingCandidate, null);
});

test('a complete planner-owned final remains observable after it was spoken', () => {
  const messages = [
    message('user-current', 'user', 'voice request'),
    message('assistant-owned', 'assistant', '修订后的完整回答', {
      isStreaming: false,
    }),
  ];

  const result = selectLiveVoiceResponseMessages({
    messages,
    voiceTranscript: 'voice request',
    isProcessing: false,
    spokenMessageIds: new Set(['assistant-owned']),
    plannerMessageId: 'assistant-owned',
  });

  assert.equal(result.plannerFinalObservation?.content, '修订后的完整回答');
  assert.deepEqual(result.speakableMessages, []);
});

test('a planner-owned final can be reconciled before processing becomes idle', () => {
  const messages = [message('user-current', 'user', 'voice request'), message('assistant-owned', 'assistant', '完整回答', { isStreaming: false })];

  const result = selectLiveVoiceResponseMessages({
    messages,
    voiceTranscript: 'voice request',
    isProcessing: true,
    spokenMessageIds: new Set(),
    plannerMessageId: 'assistant-owned',
  });

  assert.equal(result.plannerFinalObservation?.id, 'assistant-owned');
  assert.deepEqual(result.speakableMessages, []);
});

test('authoritative mode ignores stopStreaming-only content until chat.final marks it', () => {
  const user = message('user-current', 'user', 'voice request');
  const stoppedOnly = message('assistant-current', 'assistant', 'stream stopped but final is pending', { isStreaming: false });

  const beforeFinal = selectLiveVoiceResponseMessages({
    messages: [user, stoppedOnly],
    voiceTranscript: 'voice request',
    isProcessing: false,
    spokenMessageIds: new Set(),
    requireAuthoritativeFinal: true,
  });
  assert.deepEqual(beforeFinal.speakableMessages, []);
  assert.equal(beforeFinal.finalAssistantMessageCount, 0);

  const afterFinal = selectLiveVoiceResponseMessages({
    messages: [user, { ...stoppedOnly, isResponseFinal: true }],
    voiceTranscript: 'voice request',
    isProcessing: false,
    spokenMessageIds: new Set(),
    requireAuthoritativeFinal: true,
  });
  assert.deepEqual(
    afterFinal.speakableMessages.map(item => item.id),
    ['assistant-current']
  );
  assert.equal(afterFinal.finalAssistantMessageCount, 1);
});

test('a planner-owned final plus a later segment remains a two-message turn', () => {
  const result = selectLiveVoiceResponseMessages({
    messages: [
      message('user-current', 'user', 'voice request'),
      message('assistant-a', 'assistant', 'segment A', {
        isStreaming: false,
        isResponseFinal: true,
      }),
      message('assistant-b', 'assistant', 'segment B', {
        isStreaming: false,
        isResponseFinal: true,
      }),
    ],
    voiceTranscript: 'voice request',
    isProcessing: false,
    spokenMessageIds: new Set(['assistant-a']),
    plannerMessageId: 'assistant-a',
    requireAuthoritativeFinal: true,
  });

  assert.equal(result.plannerFinalObservation?.id, 'assistant-a');
  assert.deepEqual(
    result.speakableMessages.map(item => item.id),
    ['assistant-b']
  );
  assert.equal(result.finalAssistantMessageCount, 2);
});

test('an authoritative empty planner-owned final is still observable', () => {
  const result = selectLiveVoiceResponseMessages({
    messages: [
      message('user-current', 'user', 'voice request'),
      message('assistant-owned', 'assistant', '', {
        isStreaming: false,
        isResponseFinal: true,
      }),
    ],
    voiceTranscript: 'voice request',
    isProcessing: false,
    spokenMessageIds: new Set(),
    plannerMessageId: 'assistant-owned',
    requireAuthoritativeFinal: true,
  });

  assert.equal(result.plannerFinalObservation?.id, 'assistant-owned');
  assert.equal(result.finalAssistantMessageCount, 1);
  assert.deepEqual(result.speakableMessages, []);
});

test('filters historical, non-assistant, streaming, empty, and already spoken messages while preserving order', () => {
  const messages = [
    message('assistant-before', 'assistant', '边界前历史'),
    message('user-current', 'user', '开始'),
    message('system-after', 'system', '系统消息'),
    message('tool-after', 'tool', '工具消息'),
    message('assistant-streaming', 'assistant', '仍在生成', { isStreaming: true }),
    message('assistant-empty', 'assistant', ' \n\t '),
    message('assistant-first', 'assistant', '第一段'),
    message('assistant-spoken', 'assistant', '已经朗读'),
    message('assistant-second', 'assistant', '第二段', { isStreaming: false }),
  ];

  const result = selectLiveVoiceResponseMessages({
    messages,
    voiceTranscript: '开始',
    isProcessing: false,
    spokenMessageIds: new Set(['assistant-spoken']),
  });

  assert.equal(result.userBoundaryId, 'user-current');
  assert.deepEqual(
    result.speakableMessages.map(item => item.id),
    ['assistant-first', 'assistant-second']
  );
});

test('does not expose history before the user echo becomes available', () => {
  const messages = [message('assistant-history', 'assistant', '旧回答')];

  const result = selectLiveVoiceResponseMessages({
    messages,
    voiceTranscript: '尚未回显的语音输入',
    isProcessing: false,
    spokenMessageIds: new Set(),
  });

  assert.equal(result.userBoundaryId, null);
  assert.deepEqual(result.speakableMessages, []);
});

test('does not claim assistant output after a newer text user turn', () => {
  const messages = [
    message('voice-user', 'user', 'voice request'),
    message('voice-answer', 'assistant', 'voice answer'),
    message('text-user', 'user', 'typed request'),
    message('text-answer', 'assistant', 'typed answer'),
  ];

  const result = selectLiveVoiceResponseMessages({
    messages,
    voiceTranscript: 'voice request',
    knownUserBoundaryId: 'voice-user',
    isProcessing: false,
    spokenMessageIds: new Set(),
  });

  assert.deepEqual(
    result.speakableMessages.map(item => item.id),
    ['voice-answer']
  );
});
