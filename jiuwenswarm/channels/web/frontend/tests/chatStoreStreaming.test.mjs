import assert from 'node:assert/strict';
import test from 'node:test';

import { useChatStore } from '../node_modules/.cache/chat-store-streaming/chatStore.mjs';

test('addMessageIfAbsent projects one stable formal voice message exactly once', () => {
  const sessionId = 'live-voice-formal-message-projection';
  const store = useChatStore.getState();
  store.ensureRuntime(sessionId);
  const message = {
    id: 'live-voice:commit-1:user',
    role: 'user',
    content: '请用中文回答。',
    timestamp: '2026-08-16T12:00:00.000Z',
  };

  try {
    store.addMessageIfAbsent(sessionId, message);
    store.addMessageIfAbsent(sessionId, { ...message });
    const messages = useChatStore.getState().getRuntime(sessionId).messages;
    assert.equal(messages.length, 1);
    assert.deepEqual(
      { id: messages[0].id, role: messages[0].role, content: messages[0].content },
      { id: message.id, role: message.role, content: message.content },
    );
  } finally {
    useChatStore.getState().removeRuntime(sessionId);
  }
});

test('setThinking does not notify subscribers when the value is unchanged', () => {
  const sessionId = 'streaming-thinking-noop';
  useChatStore.getState().ensureRuntime(sessionId);
  let notifications = 0;
  const unsubscribe = useChatStore.subscribe(() => {
    notifications += 1;
  });

  try {
    useChatStore.getState().setThinking(sessionId, false);
    assert.equal(notifications, 0);

    useChatStore.getState().setThinking(sessionId, true);
    assert.equal(notifications, 1);

    useChatStore.getState().setThinking(sessionId, true);
    assert.equal(notifications, 1);
  } finally {
    unsubscribe();
    useChatStore.getState().removeRuntime(sessionId);
  }
});

test('markAssistantTurnFinal atomically marks only the latest user turn', () => {
  const sessionId = 'live-voice-authoritative-final';
  const store = useChatStore.getState();
  store.ensureRuntime(sessionId);
  store.addMessage(sessionId, {
    id: 'assistant-history',
    role: 'assistant',
    content: 'history',
    timestamp: '2026-08-01T00:00:00.000Z',
  });
  store.addMessage(sessionId, {
    id: 'user-current',
    role: 'user',
    content: 'voice request',
    timestamp: '2026-08-01T00:00:01.000Z',
  });
  store.addMessage(sessionId, {
    id: 'assistant-a',
    role: 'assistant',
    content: 'segment A',
    timestamp: '2026-08-01T00:00:02.000Z',
    isStreaming: false,
  });
  store.addMessage(sessionId, {
    id: 'assistant-b',
    role: 'assistant',
    content: 'segment B',
    timestamp: '2026-08-01T00:00:03.000Z',
    isStreaming: false,
  });

  try {
    store.markAssistantTurnFinal(sessionId);
    const messages = useChatStore.getState().getRuntime(sessionId).messages;
    assert.equal(messages.find(message => message.id === 'assistant-history').isResponseFinal, undefined);
    assert.equal(messages.find(message => message.id === 'assistant-a').isResponseFinal, true);
    assert.equal(messages.find(message => message.id === 'assistant-b').isResponseFinal, true);
  } finally {
    useChatStore.getState().removeRuntime(sessionId);
  }
});

test('markAssistantTurnFinal is a no-op after the turn is already marked', () => {
  const sessionId = 'live-voice-authoritative-final-noop';
  const store = useChatStore.getState();
  store.ensureRuntime(sessionId);
  store.addMessage(sessionId, {
    id: 'user-current',
    role: 'user',
    content: 'voice request',
    timestamp: '2026-08-01T00:00:00.000Z',
  });
  store.addMessage(sessionId, {
    id: 'assistant-current',
    role: 'assistant',
    content: 'answer',
    timestamp: '2026-08-01T00:00:01.000Z',
  });
  store.markAssistantTurnFinal(sessionId);
  let notifications = 0;
  const unsubscribe = useChatStore.subscribe(() => {
    notifications += 1;
  });

  try {
    store.markAssistantTurnFinal(sessionId);
    assert.equal(notifications, 0);
  } finally {
    unsubscribe();
    useChatStore.getState().removeRuntime(sessionId);
  }
});
