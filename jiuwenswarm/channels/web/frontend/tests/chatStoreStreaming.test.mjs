import assert from 'node:assert/strict';
import test from 'node:test';

import { useChatStore } from '../node_modules/.cache/chat-store-streaming/chatStore.mjs';

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

test('collapsed Agent final keeps the selected Agent identity', () => {
  const sessionId = 'streaming-agent-identity';
  useChatStore.getState().ensureRuntime(sessionId);
  useChatStore.getState().addMessage(sessionId, {
    id: 'user-identity',
    role: 'user',
    content: 'question',
    timestamp: '2026-08-31T10:00:00.000Z',
  });
  useChatStore.getState().addMessage(sessionId, {
    id: 'assistant-identity',
    role: 'assistant',
    content: 'partial',
    timestamp: '2026-08-31T10:00:01.000Z',
    isStreaming: true,
  });

  try {
    useChatStore.getState().collapseTurnFinal(sessionId, {
      kind: 'agent',
      content: 'complete',
      finalId: 'final-identity',
      timestampIso: '2026-08-31T10:00:02.000Z',
      agentTemplateName: 'expert-a',
    });
    const messages = useChatStore.getState().getRuntime(sessionId)?.messages ?? [];
    assert.equal(messages.at(-1)?.agentTemplateName, 'expert-a');
  } finally {
    useChatStore.getState().removeRuntime(sessionId);
  }
});

test('streaming reasoning keeps the selected Agent identity', () => {
  const sessionId = 'streaming-reasoning-identity';
  useChatStore.getState().ensureRuntime(sessionId);

  try {
    useChatStore.getState().appendReasoning(sessionId, 'thinking', {
      atMs: Date.parse('2026-08-31T10:00:01.000Z'),
      agentTemplateName: 'expert-a',
    });
    const segment = useChatStore.getState().getRuntime(sessionId)?.reasoningSegments.at(-1);
    assert.equal(segment?.agentTemplateName, 'expert-a');
  } finally {
    useChatStore.getState().removeRuntime(sessionId);
  }
});

test('restored reasoning keeps the persisted Agent identity', () => {
  const sessionId = 'restored-reasoning-identity';
  useChatStore.getState().ensureRuntime(sessionId);

  try {
    useChatStore.getState().restoreReasoningSegments(sessionId, [{
      at: '2026-08-31T10:00:01.000Z',
      text: 'thinking',
      agentTemplateName: 'expert-a',
    }]);
    const segment = useChatStore.getState().getRuntime(sessionId)?.reasoningSegments.at(-1);
    assert.equal(segment?.agentTemplateName, 'expert-a');
  } finally {
    useChatStore.getState().removeRuntime(sessionId);
  }
});

test('replaceHistoryMessages keeps a pending approval prompt armed', () => {
  // Reattach flow: the backend republishes the parked tool-approval ask on
  // session.switch, which can land BEFORE history restore finishes. The
  // restore's replaceHistoryMessages must not wipe pendingQuestion, or the
  // republished prompt dies again and the parked tool call waits forever.
  const sessionId = 'restore-pending-question';
  useChatStore.getState().ensureRuntime(sessionId);
  const pending = {
    request_id: 'chatcmpl-tool-parked-1',
    source: 'permission_interrupt',
    questions: [
      {
        question: 'allow clouddoc_batch_edit?',
        options: [{ label: '本次允许' }, { label: '拒绝' }],
        multi_select: false,
      },
    ],
  };

  try {
    useChatStore.getState().setPendingQuestion(sessionId, pending);
    useChatStore.getState().replaceHistoryMessages(sessionId, [
      {
        id: 'hist-user-1',
        role: 'user',
        content: 'edit the doc',
        timestamp: '2026-09-04T06:27:00.000Z',
      },
    ]);

    const runtime = useChatStore.getState().runtimes[sessionId];
    assert.equal(runtime.messages.length, 1);
    assert.deepEqual(runtime.pendingQuestion, pending);
  } finally {
    useChatStore.getState().removeRuntime(sessionId);
  }
});
