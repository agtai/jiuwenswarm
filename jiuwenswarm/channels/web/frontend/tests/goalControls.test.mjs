import assert from 'node:assert/strict';
import test, { after, afterEach } from 'node:test';
import { JSDOM } from 'jsdom';
import React, { act } from 'react';
import { webcrypto } from 'node:crypto';

globalThis.crypto ??= webcrypto;

const dom = new JSDOM('<!doctype html><html><body></body></html>', { url: 'http://127.0.0.1:5173/' });
for (const key of ['window', 'document', 'navigator', 'localStorage', 'HTMLElement', 'Node', 'Event', 'MouseEvent']) {
  Object.defineProperty(globalThis, key, { configurable: true, value: dom.window[key] });
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
// Vite's static provider-icon catalog is unrelated to Goal control behavior.
globalThis.__goalTestAssetGlob = () => ({});
const { createRoot } = await import('react-dom/client');
const {
  GoalBar,
  InputArea,
  useWebSocket,
  useGoalStore,
  useChatStore,
  useSessionStore,
  captureGoalTarget,
  webClient,
  requestGoalAction,
  sendGoalStreamCommand,
} = await import('../node_modules/.cache/goal-controls/entry.mjs');

const calls = [];
let serverGoal;
webClient.connect = async () => {};
webClient.disconnect = async () => {};
webClient.request = async (method, payload) => {
  calls.push({ method, payload });
  return { goal: payload.action === 'clear' ? null : serverGoal };
};
webClient.sendFireAndForget = async (method, payload, options) => calls.push({ method, payload, options });

function goal(overrides = {}) {
  return {
    session_id: 'session',
    goal_id: 'goal-1',
    control_revision: 3,
    revision: 17,
    status: 'paused',
    objective: 'Original objective',
    attempt_count: 2,
    ...overrides,
  };
}

let root;
let api;
let container;
function Controls({ withComposer = false }) {
  api = useWebSocket({});
  if (withComposer) {
    return React.createElement(InputArea, {
      onSetGoal: api.setGoalObjective,
      onClearGoal: api.clearGoal,
      onSubmit() {
        throw new Error('Goal must not use ordinary chat');
      },
      onPersistMedia: async () => ({}),
      onPersistDocuments: async () => ({}),
      onInterrupt() {
        throw new Error('Goal must not interrupt ordinary chat');
      },
      onCancel() {
        throw new Error('Goal must not cancel ordinary chat');
      },
      onSwitchMode() {},
      isProcessing: false,
      permissionsEnabled: true,
      onSavePermission: async () => {},
    });
  }
  return React.createElement(GoalBar, {
    onSetGoal: api.setGoalObjective,
    onPauseGoal: api.pauseGoal,
    onResumeGoal: api.resumeGoal,
    onClearGoal: api.clearGoal,
  });
}

async function mount(record = goal(), withComposer = false) {
  serverGoal = record;
  calls.length = 0;
  useChatStore.setState({ runtimes: {}, activeSessionId: 'session' });
  useChatStore.getState().ensureRuntime('session');
  useGoalStore.setState({ runtimes: {}, objectiveMessageTexts: {}, bannerHiddenGoalIds: {} });
  useGoalStore.getState().setGoal('session', record);
  useSessionStore.getState().ensureRuntime('session');
  useSessionStore.getState().setConnected(true);
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
  await act(async () => root.render(React.createElement(Controls, { withComposer })));
  calls.length = 0;
}

async function incoming(event, payload) {
  await act(async () => webClient.handleIncoming(JSON.stringify({ type: 'event', event, payload })));
}

async function click(element) {
  assert.ok(element, 'expected mounted control');
  await act(async () => element.dispatchEvent(new MouseEvent('click', { bubbles: true })));
}

async function editText(value) {
  const textarea = document.querySelector('textarea');
  assert.ok(textarea);
  await act(async () => {
    Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set.call(textarea, value);
    textarea.dispatchEvent(new Event('input', { bubbles: true }));
  });
}

afterEach(async () => {
  if (root) await act(async () => root.unmount());
  root = null;
  container?.remove();
});
after(() => dom.window.close());

test('actual Web client sends exact observed targets; missing/cross-session targets send nothing', async () => {
  calls.length = 0;
  const observed = captureGoalTarget('session', goal());
  await requestGoalAction({ sessionId: 'session', action: 'pause', target: observed });
  await requestGoalAction({ sessionId: 'session', action: 'clear', target: observed });
  await sendGoalStreamCommand({ sessionId: 'session', action: 'resume', target: observed });
  assert.equal(calls.length, 3);
  for (const { method, payload } of calls) {
    assert.equal(method, 'command.goal');
    assert.equal(payload.expected_goal_id, 'goal-1');
    assert.equal(payload.expected_control_revision, 3);
  }
  calls.length = 0;
  for (const target of [
    undefined,
    { ...observed, session_id: 'other' },
    { ...observed, control_revision: undefined },
    { ...observed, control_revision: true },
    { ...observed, control_revision: 0 },
    { ...observed, control_revision: 1.5 },
  ]) {
    await assert.rejects(requestGoalAction({ sessionId: 'session', action: 'clear', target }));
    await assert.rejects(sendGoalStreamCommand({ sessionId: 'session', action: 'resume', target }));
  }
  assert.deepEqual(calls, []);
});

test('new set cannot overwrite; rejected and accepted events credit only authoritative objectives', async () => {
  await mount();
  await act(async () => api.setGoalObjective('session', 'Attempted replacement'));
  assert.equal(calls[0].payload.overwrite_confirmed, false);
  assert.equal(calls[0].payload.expected_goal_id, undefined);
  assert.deepEqual(useGoalStore.getState().getGoalObjectiveTextsForSession('session'), []);
  await incoming('goal.confirm_required', { session_id: 'session', existing_goal: goal(), requested_objective: 'Attempted replacement' });
  assert.equal(useGoalStore.getState().runtimes.session.pendingAction, null);
  assert.deepEqual(useGoalStore.getState().getGoalObjectiveTextsForSession('session'), ['Original objective']);
  assert.equal(calls.length, 1, 'no automatic retry/overwrite');
  await incoming('goal.snapshot', { session_id: 'session', goal: goal({ goal_id: 'goal-2', objective: 'Accepted objective' }) });
  assert.ok(useGoalStore.getState().getGoalObjectiveTextsForSession('session').includes('Accepted objective'));
  assert.ok(!useGoalStore.getState().getGoalObjectiveTextsForSession('session').includes('Attempted replacement'));
});

test('mounted edit sends the target captured at dialog open', async () => {
  await mount();
  await click(container.querySelector('.goal-bar__action-btn'));
  await editText('Edited objective');
  await click(document.querySelector('.fixed textarea').parentElement.querySelector('button.bg-text-strong'));
  const command = calls.find(call => call.payload.action === 'set');
  assert.equal(command.payload.objective, 'Edited objective');
  assert.equal(command.payload.overwrite_confirmed, true);
  assert.equal(command.payload.expected_goal_id, 'goal-1');
  assert.equal(command.payload.expected_control_revision, 3);
  assert.equal(document.querySelector('textarea'), null);
});

for (const change of ['replacement', 'control_revision', 'session']) {
  test(`mounted edit closes on ${change} without sending a replacement`, async () => {
    await mount();
    await click(container.querySelector('.goal-bar__action-btn'));
    await editText('Do not retarget');
    await act(async () => {
      if (change === 'session') {
        useChatStore.getState().ensureRuntime('other');
        useGoalStore.getState().setGoal('other', goal({ session_id: 'other' }));
        useChatStore.getState().setActiveSessionId('other');
      } else {
        useGoalStore.getState().setGoal('session', goal(change === 'replacement' ? { goal_id: 'goal-2' } : { control_revision: 4 }));
      }
    });
    assert.equal(document.querySelector('textarea'), null);
    assert.equal(calls.filter(call => call.payload.action === 'set').length, 0);
  });
}

test('clear sends one exact Goal command; unavailable snapshots and unscoped errors preserve other sessions', async () => {
  await mount();
  await click(container.querySelector('.goal-bar__action-btn--danger'));
  assert.deepEqual(
    calls.map(call => call.method),
    ['command.goal'],
  );
  assert.equal(calls[0].payload.expected_goal_id, 'goal-1');
  await act(async () => useGoalStore.getState().setGoal('session', goal({ control_revision: undefined })));
  assert.ok([...container.querySelectorAll('button')].every(button => button.disabled));
  const before = useGoalStore.getState().runtimes.session.goal;
  await incoming('execution.error', { goal: null, message: 'unscoped' });
  assert.equal(useGoalStore.getState().runtimes.session.goal, before);
  await act(async () => useGoalStore.getState().setPendingAction('session', 'resume'));
  await incoming('execution.error', { session_id: 'session', message: 'state unavailable' });
  assert.equal(useGoalStore.getState().runtimes.session.goal, before);
  assert.equal(useGoalStore.getState().runtimes.session.pendingAction, null);
  assert.equal(useGoalStore.getState().runtimes.session.queryStatus, 'unknown');
});

test('completed Goal can be followed by a new Goal using only its exact completed target', async () => {
  await mount(goal({ status: 'completed' }));
  await act(async () => api.setGoalObjective('session', 'Next objective'));
  assert.equal(calls[0].payload.overwrite_confirmed, true);
  assert.equal(calls[0].payload.expected_goal_id, 'goal-1');
  assert.equal(calls[0].payload.expected_control_revision, 3);
  assert.equal(
    useChatStore
      .getState()
      .getRuntime('session')
      .messages.filter(message => message.isGoalObjectiveMessage).length,
    0,
  );
  await incoming('goal.snapshot', { action: 'set', session_id: 'session', goal: goal({ goal_id: 'goal-2', objective: 'Next objective' }) });
  assert.deepEqual(
    useChatStore
      .getState()
      .getRuntime('session')
      .messages.filter(message => message.isGoalObjectiveMessage)
      .map(message => message.content),
    ['Next objective'],
  );
});

test('actual composer does not pre-credit a rejected Goal and accepted busy-turn bubbles keep their order', async () => {
  await mount(null, true);
  await act(async () => {
    useGoalStore.getState().setArmed('session', true);
    const editor = container.querySelector('[contenteditable]');
    editor.textContent = 'Composer objective';
    editor.dispatchEvent(new Event('input', { bubbles: true }));
  });
  await click(container.querySelector('[data-testid="chat-send"]'));
  assert.equal(calls.find(call => call.method === 'command.goal').payload.objective, 'Composer objective');
  assert.equal(
    useChatStore
      .getState()
      .getRuntime('session')
      .messages.some(message => message.isGoalObjectiveMessage),
    false,
  );
  await incoming('goal.confirm_required', { session_id: 'session', existing_goal: goal(), requested_objective: 'Composer objective' });
  assert.equal(
    useChatStore
      .getState()
      .getRuntime('session')
      .messages.some(message => message.isGoalObjectiveMessage),
    false,
  );
  await act(async () => {
    useChatStore
      .getState()
      .addMessage('session', { id: 'ordinary', role: 'assistant', content: 'Finishing ordinary reply', timestamp: new Date().toISOString() });
    useChatStore.getState().setProcessing('session', true);
  });
  await incoming('goal.snapshot', { session_id: 'session', action: 'set', goal: goal({ goal_id: 'goal-2', objective: 'Accepted while busy' }) });
  assert.equal(
    useChatStore
      .getState()
      .getRuntime('session')
      .messages.some(message => message.isGoalObjectiveMessage),
    false,
  );
  await act(async () => useChatStore.getState().flushPendingGoalObjectiveBubble('session'));
  const messages = useChatStore.getState().getRuntime('session').messages;
  assert.equal(messages.at(-2).id, 'ordinary');
  assert.equal(messages.at(-1).content, 'Accepted while busy');
  assert.equal(messages.at(-1).isGoalObjectiveMessage, true);
});

test('wrong-session Goal events cannot update Goal state or accepted history', async () => {
  await mount();
  const before = useGoalStore.getState().runtimes.session.goal;
  await incoming('goal.snapshot', { session_id: 'session', action: 'set', goal: goal({ session_id: 'other', objective: 'Wrong target' }) });
  await incoming('goal.confirm_required', { session_id: 'session', existing_goal: goal({ session_id: 'other' }) });
  assert.equal(useGoalStore.getState().runtimes.session.goal, before);
  assert.equal(useChatStore.getState().getRuntime('session').messages.length, 0);
});

function agentQuestion(token = 'a', overrides = {}) {
  return {
    session_id: 'session', request_id: `agent-input.display-${token}`, input_id: 'provider-reused-id',
    source_binding_id: 'original-work', source_task_id: `actual-task-${token}`, pending_token: token,
    source: 'permission_interrupt', questions: [{ question: 'Proceed?', header: 'Approval', options: [{ label: 'Approve' }] }],
    ...overrides,
  };
}
const explicitAnswer = [{ question: 'Proceed?', selected_options: ['Approve'] }];

test('managed Agent answers preserve exact observed selectors and replay request ID without new chat history', async () => {
  await mount();
  const original = webClient.request;
  webClient.request = async (method, payload, options) => {
    calls.push({ method, payload, options });
    return { accepted: true };
  };
  try {
    for (let attempt = 0; attempt < 2; attempt++) {
      await incoming('chat.ask_user_question', agentQuestion());
      await act(async () => api.sendUserAnswer('session', 'agent-input.display-a', explicitAnswer));
      assert.equal(useChatStore.getState().getRuntime('session').pendingQuestion, null);
    }
    assert.equal(calls.length, 2);
    assert.deepEqual(calls[0], calls[1]);
    assert.equal(calls[0].method, 'command.agent_input');
    assert.match(calls[0].options.requestId, /^agent-input\.[0-9a-f]{64}$/);
    assert.deepEqual(calls[0].payload, {
      action: 'reply', session_id: 'session', source_binding_id: 'original-work', source_task_id: 'actual-task-a',
      pending_token: 'a', input_id: 'provider-reused-id', answers: explicitAnswer,
    });
    assert.equal(useChatStore.getState().getRuntime('session').messages.length, 0);
  } finally { webClient.request = original; }
});

test('an old Agent answer receipt and stale UI callback cannot clear or answer the next generation', async () => {
  await mount();
  const original = webClient.request;
  webClient.request = async (method, payload) => {
    calls.push({ method, payload });
    useChatStore.getState().setPendingQuestion('session', agentQuestion('b'));
    return { accepted: true };
  };
  try {
    await incoming('chat.ask_user_question', agentQuestion());
    await act(async () => api.sendUserAnswer('session', 'agent-input.display-a', explicitAnswer));
    await act(async () => api.sendUserAnswer('session', 'agent-input.display-a', explicitAnswer));
    assert.equal(calls.length, 1);
    assert.equal(useChatStore.getState().getRuntime('session').pendingQuestion.pending_token, 'b');
  } finally { webClient.request = original; }
});

test('incomplete Agent selectors send nothing and a rejected claim keeps its question', async () => {
  await mount();
  const original = webClient.request;
  webClient.request = async (method, payload) => {
    calls.push({ method, payload });
    return { accepted: false, reason: 'AGENT_INTERRUPT_STALE' };
  };
  try {
    await incoming('chat.ask_user_question', agentQuestion('a', { pending_token: undefined }));
    await act(async () => api.sendUserAnswer('session', 'agent-input.display-a', explicitAnswer));
    assert.equal(calls.length, 0);
    await incoming('chat.ask_user_question', agentQuestion());
    await act(async () => api.sendUserAnswer('session', 'agent-input.display-a', explicitAnswer));
    assert.equal(calls.length, 1);
    assert.equal(useChatStore.getState().getRuntime('session').pendingQuestion.pending_token, 'a');
  } finally { webClient.request = original; }
});

test('unmanaged legacy interrupt keeps its existing chat answer adapter', async () => {
  await mount();
  await incoming('chat.ask_user_question', {
    session_id: 'session', request_id: 'legacy-input', source: 'permission_interrupt', questions: [],
  });
  await act(async () => api.sendUserAnswer('session', 'legacy-input', explicitAnswer));
  assert.equal(calls.length, 1);
  assert.equal(calls[0].method, 'chat.send');
  assert.equal(calls[0].payload.request_id, 'legacy-input');
  assert.deepEqual(calls[0].payload.answers, explicitAnswer);
});

test('unknown Agent receipt keeps the exact question and retry request identity', async () => {
  await mount();
  const original = webClient.request;
  webClient.request = async (method, payload, options) => {
    calls.push({ method, payload, options });
    return { status: 'unknown', observation_required: true, reason: 'AGENT_INTERRUPT_CLAIM_UNOBSERVED' };
  };
  try {
    await incoming('chat.ask_user_question', agentQuestion());
    for (let attempt = 0; attempt < 2; attempt++) {
      await act(async () => api.sendUserAnswer('session', 'agent-input.display-a', explicitAnswer));
      assert.equal(useChatStore.getState().getRuntime('session').pendingQuestion.pending_token, 'a');
    }
    assert.deepEqual(calls[0], calls[1]);
    assert.equal(useChatStore.getState().getRuntime('session').messages.length, 0);
  } finally { webClient.request = original; }
});
