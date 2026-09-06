import assert from 'node:assert/strict';
import test from 'node:test';

import { useChatStore } from '../node_modules/.cache/chat-store-streaming/chatStore.mjs';

test('Native generated text updates during playback, freezes on interrupt and merges exact heard history', () => {
  const store = useChatStore.getState(), session = 'native-generated-chat';
  store.ensureRuntime(session);
  const responseKey = 'live-voice:interaction:response:1';
  const message = (content, revision, state = 'generating') => ({ id: `${responseKey}:native-generated`,
    role: 'assistant', content, timestamp: '2026-09-06T12:00:00.000Z', nativeVoice: { responseKey, revision, state } });
  const rows = () => useChatStore.getState().getRuntime(session).messages;
  try {
    store.addMessageIfAbsent(session, message('Hello', 1));
    const renderKey = rows()[0].renderKey;
    store.addMessageIfAbsent(session, message('Hello world', 2));
    assert.equal(rows().length, 1);
    assert.equal(rows()[0].content, 'Hello world');
    assert.equal(rows()[0].renderKey, renderKey);
    store.addMessageIfAbsent(session, message('Hello world', 3, 'interrupted'));
    store.addMessageIfAbsent(session, message('late overwrite', 4));
    store.replaceHistoryMessages(session, []);
    assert.equal(rows().length, 1);
    assert.equal(rows()[0].nativeVoice.state, 'interrupted');
    assert.equal(rows()[0].content, 'Hello world');
    const heard = { id: `${responseKey}:native-audio:digest`, role: 'assistant', content: 'Hello world', timestamp: message('', 0).timestamp };
    store.addMessageIfAbsent(session, heard);
    store.addMessageIfAbsent(session, message('late generated', 5));
    store.addMessageIfAbsent(session, heard); // late following_assistant replay
    assert.equal(rows().length, 1);
    assert.equal(rows()[0].id, heard.id);
    assert.equal(rows()[0].renderKey, renderKey);
    assert.equal(rows()[0].nativeVoice, undefined);
    store.replaceHistoryMessages(session, [heard]);
    assert.equal(rows().length, 1);
  } finally { store.removeRuntime(session); }
});

test('same-session history refresh retains Native turn ordering and previous reply failure', () => {
  const store = useChatStore.getState(), session = 'native-reconnect-order';
  store.ensureRuntime(session);
  const nativeTurnKey = '["interaction","turn"]';
  const user = { id: 'live-voice:commit:native-user', role: 'user', content: 'Question', timestamp: '2026-09-06T12:00:02Z' };
  const responseKey = 'live-voice:interaction:response:1';
  const generated = { id: `${responseKey}:native-generated`, role: 'assistant', content: 'Answer',
    timestamp: '2026-09-06T12:00:01Z', nativeTurnKey, nativeVoice: { responseKey, revision: 1, state: 'interrupted' } };
  const failure = { id: 'live-voice-failure:activation:reason:1', role: 'assistant', content: 'Reply failed', timestamp: '2026-09-06T12:00:03Z' };
  try {
    store.addMessageIfAbsent(session, generated);
    store.addMessageIfAbsent(session, { ...user, nativeTurnKey });
    store.addMessageIfAbsent(session, failure);
    store.replaceHistoryMessages(session, [user]);
    const rows = useChatStore.getState().getRuntime(session).messages;
    assert.equal(rows.length, 3);
    assert.deepEqual(rows.find(item => item.id === user.id), { ...user, nativeTurnKey, renderKey: rows.find(item => item.id === user.id).renderKey });
    assert.equal(rows.find(item => item.id === generated.id).nativeTurnKey, nativeTurnKey);
    assert.ok(rows.some(item => item.id === failure.id));
  } finally { store.removeRuntime(session); }
});

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
