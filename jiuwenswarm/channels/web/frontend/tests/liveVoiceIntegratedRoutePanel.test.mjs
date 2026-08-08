import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

import i18next from 'i18next';
import React from 'react';
import { I18nextProvider } from 'react-i18next';
import { renderToStaticMarkup } from 'react-dom/server';

import {
  LiveVoiceIntegratedRoutePanelView,
  PRODUCT_P2_NOTIFICATION_CLIENT_TIMEOUT_MS,
  classifyProductP2Notification,
  ProductResponseSurfaceFence,
  coordinateRetainedProductP2Close,
  executeProductVoiceBargeIn,
  executeProductPresentationWithFence,
  executeProductP3TaskQuery,
  settleRetainedProductVoiceResponseCancel,
  extractWebErrorReason,
  isCurrentProgressOwner,
  productP2WebRequestOptions,
  productTextBlockedByP1Status,
  progressMatchesOwnedBinding,
  resolveProductTaskCreateOrigin,
  retainBoundedPresentedProductResponse,
} from '../node_modules/.cache/live-voice-integrated-web/LiveVoiceIntegratedRoutePanel.mjs';
import {
  PRODUCT_P2_NOTIFICATION_NEXT_METHOD,
  PRODUCT_P2_ACTIVATE_METHOD,
  PRODUCT_P2_BARGE_IN_METHOD,
  PRODUCT_P2_CLOSE_METHOD,
  PRODUCT_P2_SUBMIT_METHOD,
  ProductWebP2ActivationOwner,
  ProductWebP3TaskQueryOwner,
} from '../node_modules/.cache/live-voice-integrated-web/features/live-voice/formal/productWebActivation.js';
import {
  FormalTaskControlLeaf,
} from '../node_modules/.cache/live-voice-integrated-web/features/live-voice/formal/formalTaskControlLeaf.js';
import {
  IntegratedWebRouteShell,
  createCurrentIntegratedWebRouteSelection,
} from '../node_modules/.cache/live-voice-integrated-web/features/live-voice/formal/integratedWebRouteShell.js';
import { parseProductTextProgressEvent } from '../node_modules/.cache/live-voice-integrated-web/features/live-voice/formal/productTextProgress.js';

async function renderPanel({
  sessionId = 'persisted-session',
  platform = null,
  progress = null,
  viewProps = {},
} = {}) {
  const translations = JSON.parse(await readFile(new URL('../src/i18n/locales/en.json', import.meta.url), 'utf8'));
  const i18n = i18next.createInstance();
  await i18n.init({
    lng: 'en',
    fallbackLng: false,
    resources: { en: { translation: translations } },
    interpolation: { escapeValue: false },
  });
  const selection = createCurrentIntegratedWebRouteSelection({
    p1_browser_speech_available: true,
    p2_text_chat_available: true,
    p3_task_compatibility_enabled: true,
    p3_task_compatibility_available: true,
  });
  const manifest = new IntegratedWebRouteShell({
    enabled: true,
    registry: selection.registry,
    policy: selection.policy,
    context: {
      session_id: sessionId,
      correlation_id: 'ui-route-test',
      observed_at: '2026-08-05T12:00:00Z',
    },
  }).preview();
  return renderToStaticMarkup(
    React.createElement(
      I18nextProvider,
      { i18n },
      React.createElement(LiveVoiceIntegratedRoutePanelView, {
        manifest,
        platform,
        progress,
        onRefresh: () => {},
        ...viewProps,
      })
    )
  );
}

test('route panel renders three truthful predecessor classes and the non-success disclosure', async () => {
  const html = await renderPanel();

  assert.equal(html.includes('data-composition="shell_only"'), true);
  assert.equal((html.match(/data-testid="live-voice-integrated-p/g) ?? []).length, 3);
  assert.equal(html.includes('data-implementation-class="fallback"'), true);
  assert.equal(html.includes('data-implementation-class="demo_substitute"'), true);
  assert.equal(html.includes('BROWSER_SPEECH_COMPATIBILITY_FALLBACK'), true);
  assert.equal(html.includes('persisted-session'), true);
  assert.equal(html.includes('ui-route-test'), true);
  assert.equal(html.includes('compat.browser-speech'), true);
  assert.equal(html.includes('browser-speech'), true);
  assert.equal(html.includes('P2 text route below is formal only'), true);
  assert.equal(html.includes('Speech'), true);
  assert.equal(html.includes('physical audio'), true);
  assert.equal(html.includes('task completion'), true);
  assert.equal(html.includes('Gate acceptance'), true);
});

test('route panel renders only a validated authenticated text progress fact', async () => {
  const progress = parseProductTextProgressEvent({
    event_type: 'live_voice.task.progress',
    delivery_id: 'delivery-product-1',
    session_id: 'persisted-session',
    task_id: 'task-product-1',
    project_id: 'project-1',
    correlation_id: 'correlation-product-1',
    origin_id: 'web-surface-1',
    generation_kind: 'web_task_progress_generation',
    generation_id: 'web-generation-1',
    generation: 2,
    evidence_id: 'evidence-product-1',
    source_event: {
      event_id: 'source-product-1',
      event_type: 'task.running',
      seq: 11,
      correlation_id: 'correlation-product-1',
      causation_id: 'cause-product-1',
      stream_ref: { kind: 'task', id: 'task-product-1' },
      scope: {
        subject_id: 'principal-1',
        session_id: 'persisted-session',
        project_id: 'project-1',
        assurance: 'authenticated',
      },
      payload: { state: 'running' },
    },
    progress_event: {
      event_id: 'progress-product-1',
      event_type: 'work.progress',
      seq: 11,
      correlation_id: 'correlation-product-1',
      causation_id: 'source-product-1',
      stream_ref: { kind: 'task', id: 'task-product-1' },
      scope: {
        subject_id: 'principal-1',
        session_id: 'persisted-session',
        project_id: 'project-1',
        assurance: 'authenticated',
      },
      payload: {
        work_ref: { kind: 'task', id: 'task-product-1' },
        seq: 11,
        state: 'running',
      },
    },
  });
  assert.notEqual(progress, null);

  const html = await renderPanel({ progress });

  assert.equal(html.includes('data-testid="live-voice-integrated-product-progress"'), true);
  assert.equal(html.includes('Authenticated task text progress'), true);
  assert.equal(html.includes('task-product-1'), true);
  assert.equal(html.includes('correlation-product-1'), true);
  assert.equal(html.includes('delivery-product-1'), true);
  assert.equal(html.includes('web_task_progress_generation:web-generation-1:2'), true);
  assert.equal(html.includes('It is not voice progress or Integrated Gate evidence.'), true);
});

test('P2 notification classification surfaces errors and terminal-without-final', () => {
  assert.deepEqual(
    classifyProductP2Notification({
      kind: 'agent.error',
      error_reason: 'HARNESS_FAILED',
    }),
    { kind: 'failed', reason: 'HARNESS_FAILED' }
  );
  assert.deepEqual(
    classifyProductP2Notification({
      kind: 'work.progress',
      response: { response_id: 'response-1', response_generation: 0 },
      progress_event: {
        payload: { state: 'terminal', outcome: 'completed' },
      },
    }),
    {
      kind: 'failed',
      reason: 'PRODUCT_AGENT_TERMINAL_WITHOUT_FINAL:completed',
    }
  );
  assert.deepEqual(
    classifyProductP2Notification(
      {
        kind: 'work.progress',
        progress_event: { payload: { state: 'terminal', outcome: 'completed' } },
      },
      true
    ),
    { kind: 'continue' }
  );
});

test('Web response error extraction preserves nested product reason', () => {
  assert.equal(
    extractWebErrorReason({
      error: {
        code: 'PERMISSION_DENIED',
        reason: 'TASK_CONTEXT_PERMISSION_MISSING',
        message: 'revoked',
      },
    }),
    'TASK_CONTEXT_PERMISSION_MISSING'
  );
  assert.equal(extractWebErrorReason({ reason: ' TOP_LEVEL_REASON ' }), 'TOP_LEVEL_REASON');
  assert.equal(extractWebErrorReason({ error: 'legacy error' }), undefined);
});

test('P2 notification polling outlives the retained Gateway unary owner', () => {
  assert.deepEqual(
    productP2WebRequestOptions(
      PRODUCT_P2_NOTIFICATION_NEXT_METHOD,
      'notification-request-1'
    ),
    {
      requestId: 'notification-request-1',
      timeoutMs: PRODUCT_P2_NOTIFICATION_CLIENT_TIMEOUT_MS,
    }
  );
  assert.equal(PRODUCT_P2_NOTIFICATION_CLIENT_TIMEOUT_MS > 600_000, true);
  assert.deepEqual(
    productP2WebRequestOptions(PRODUCT_P2_SUBMIT_METHOD, 'submit-request-1'),
    { requestId: 'submit-request-1' }
  );
  assert.deepEqual(productP2WebRequestOptions(PRODUCT_P2_SUBMIT_METHOD), {});
});

test('presented response ownership stays bounded and evicts conservatively', () => {
  const responses = new Map();
  for (let index = 0; index < 129; index += 1) {
    retainBoundedPresentedProductResponse(responses, `response-${index}`);
  }
  assert.equal(responses.size, 128);
  assert.equal(responses.has('response-0'), false);
  assert.equal(responses.has('response-128'), true);
});

test('unknown retained P2 operation locks editing and second submission', async () => {
  const html = await renderPanel({
    viewProps: {
      p2Activation: {
        status: 'active',
        binding: {
          session_id: 'persisted-session',
          correlation_id: 'ui-route-test',
          interaction_id: 'interaction-1',
          activation_id: 'activation-1',
          activation_generation: 1,
        },
        reason: null,
      },
      productInput: 'retained exact text',
      productTextStatus: 'failed',
      productOperationRetained: true,
      onProductInput: () => {},
      onProductSubmit: () => {},
    },
  });

  assert.match(html, /<textarea[^>]*disabled=""[^>]*>retained exact text<\/textarea>/);
  assert.match(html, /<button[^>]*type="submit"[^>]*disabled=""/);
});

test('route panel renders a distinct two-action formal P3 task control', async () => {
  const html = await renderPanel({
    viewProps: {
      p3MutationEnabled: true,
      p3MutationOperation: 'task.create',
      p3TaskName: 'task name',
      p3TaskInstruction: 'task instruction',
      p3MutationStatus: 'confirmed',
      onP3MutationOperation: () => {},
      onP3TaskName: () => {},
      onP3TaskInstruction: () => {},
      onP3TargetTaskId: () => {},
      onP3Issue: () => {},
      onP3Execute: () => {},
    },
  });

  assert.equal(html.includes('data-testid="live-voice-integrated-p3-mutation"'), true);
  assert.equal(html.includes('Issue confirmation'), false);
  assert.equal(html.includes('Execute confirmed mutation'), true);
  assert.equal(html.includes('Acceptance is not task completion.'), true);
  assert.equal((html.match(/disabled=""/g) ?? []).length >= 3, true);
});

function formalQueryTask(overrides = {}) {
  return {
    task_id: overrides.task_id ?? 'task-1',
    attempt_id: overrides.attempt_id ?? 'attempt-1',
    correlation_id: overrides.correlation_id ?? 'task-correlation-1',
    scope: {
      subject_id: 'subject-1',
      session_id: overrides.session_id ?? 'persisted-session',
      project_id: 'project-1',
      assurance: 'authenticated',
    },
    state: overrides.state ?? 'accepted',
    outcome: overrides.outcome ?? null,
    event_head: overrides.event_head ?? 0,
  };
}

function formalQueryEnvelope(requestId, result) {
  return {
    contract_version: 'live-voice.contract.v2',
    request_id: requestId,
    command_id: null,
    ok: true,
    result,
    error: null,
    observed_at: '2026-08-08T12:00:00Z',
    extensions: {},
  };
}

function formalAcceptedEvent() {
  const task = formalQueryTask();
  return {
    event_id: 'event-0',
    task_id: task.task_id,
    attempt_id: task.attempt_id,
    correlation_id: task.correlation_id,
    scope: task.scope,
    seq: 0,
    event_type: 'task.accepted',
    state: 'accepted',
    outcome: null,
    producer: 'task_core',
    source_event_id: null,
    causation_id: 'command-create-1',
    occurred_at: '2026-08-08T11:59:00Z',
    details: {},
  };
}

test('all four structured P3 queries adopt exact Task Core facts without business cancel effects', async () => {
  const calls = [];
  const owner = new ProductWebP3TaskQueryOwner({
    enabled: true,
    connected: true,
    session_id: 'persisted-session',
    request: async (method, params, requestId) => {
      calls.push([method, params]);
      const task = formalQueryTask();
      if (method.endsWith('.list')) return formalQueryEnvelope(requestId, { tasks: [task] });
      if (method.endsWith('.events')) {
        return formalQueryEnvelope(requestId, {
          task_id: task.task_id,
          after_seq: params.after_seq,
          head_seq: 0,
          events: [formalAcceptedEvent()],
          truncated: false,
          cursor_replay_supported: false,
        });
      }
      return formalQueryEnvelope(requestId, {
        task,
        attempt: { task_id: task.task_id, attempt_id: task.attempt_id },
      });
    },
  });
  let leaf = null;
  for (const query of [
    { operation: 'task.list' },
    { operation: 'task.get', task_id: 'task-1' },
    { operation: 'task.status', task_id: 'task-1' },
    { operation: 'task.events', task_id: 'task-1', after_seq: -1 },
  ]) {
    const result = await executeProductP3TaskQuery({
      owner,
      leaf,
      query,
      expected_session_id: 'persisted-session',
    });
    leaf = result.leaf;
    assert.equal(result.snapshot.tasks[0].task_id, 'task-1');
  }
  assert.equal(leaf.snapshot().tasks[0].last_event_seq, 0);
  assert.deepEqual(
    calls.map(([, params]) => params),
    [
      { session_id: 'persisted-session' },
      { session_id: 'persisted-session', task_id: 'task-1' },
      { session_id: 'persisted-session', task_id: 'task-1' },
      { session_id: 'persisted-session', task_id: 'task-1', after_seq: -1 },
    ],
  );
  assert.equal(
    calls.some(([method]) => /mutate|cancel|barge|submit/.test(method)),
    false,
  );
});

test('formal P3 query UI exposes exact read operations and truthful retained facts', async () => {
  const leaf = new FormalTaskControlLeaf({
    enabled: true,
    binding: {
      subject_id: 'subject-1',
      session_id: 'persisted-session',
      project_id: 'project-1',
      correlation_id: 'task-correlation-1',
      generation: 1,
    },
  });
  const snapshot = leaf.adopt(
    'task.list',
    {
      ok: true,
      result: { tasks: [formalQueryTask()] },
    },
    {
      connection_generation: 1,
      command_id: null,
      events_query: null,
    },
  );
  const html = await renderPanel({
    viewProps: {
      p3QueryEnabled: true,
      p3QueryOperation: 'task.events',
      p3QueryTaskId: 'task-1',
      p3EventsAfterSeq: '0',
      p3QueryStatus: 'disconnected',
      p3QueryReason: 'P3_QUERY_REFRESH_REQUIRED',
      p3QuerySnapshot: snapshot,
      p3QueryEventCount: 0,
      onP3QueryOperation: () => {},
      onP3QueryTaskId: () => {},
      onP3EventsAfterSeq: () => {},
      onP3Query: () => {},
    },
  });

  assert.equal(html.includes('data-testid="live-voice-integrated-p3-query"'), true);
  for (const label of ['List tasks', 'Get task', 'Get task status', 'Get task events']) {
    assert.equal(html.includes(label), true, label);
  }
  for (const fact of ['task-1', 'attempt-1', 'task-correlation-1', 'P3_QUERY_REFRESH_REQUIRED']) {
    assert.equal(html.includes(fact), true, fact);
  }
  assert.equal(html.includes('these controls do not stop playback, responses, or rounds'), true);

  const disabled = await renderPanel({
    viewProps: {
      p3QueryEnabled: false,
      onP3QueryOperation: () => {
        throw new Error('must not run');
      },
      onP3QueryTaskId: () => {
        throw new Error('must not run');
      },
      onP3EventsAfterSeq: () => {
        throw new Error('must not run');
      },
      onP3Query: () => {
        throw new Error('must not run');
      },
    },
  });
  assert.equal(disabled.includes('data-testid="live-voice-integrated-p3-query"'), false);
});

test('browser progress consumption is fenced to the exact owned P3 binding', () => {
  const event = {
    session_id: 'session-1',
    task_id: 'task-1',
    correlation_id: 'correlation-1',
    origin_id: 'origin-1',
    generation_id: 'generation-1',
    generation: 3,
  };
  const binding = { ...event };

  assert.equal(progressMatchesOwnedBinding(event, binding, 'session-1'), true);
  for (const [field, value] of [
    ['session_id', 'wrong-session'],
    ['task_id', 'wrong-task'],
    ['correlation_id', 'wrong-correlation'],
    ['origin_id', 'wrong-origin'],
    ['generation_id', 'wrong-generation-id'],
    ['generation', 4],
  ]) {
    assert.equal(
      progressMatchesOwnedBinding(
        { ...event, [field]: value },
        binding,
        'session-1'
      ),
      false,
      field
    );
  }
  assert.equal(
    progressMatchesOwnedBinding(event, binding, 'session-2'),
    false
  );
  assert.equal(progressMatchesOwnedBinding(event, binding, null), false);
});

test('a delayed prior-session activation cannot own or acknowledge the current session', () => {
  const sessionAEvent = {
    session_id: 'session-a',
    task_id: 'task-a',
    correlation_id: 'correlation-a',
    origin_id: 'origin-a',
    generation_id: 'generation-a',
    generation: 1,
  };
  const delayedSessionABinding = { ...sessionAEvent };

  assert.equal(
    progressMatchesOwnedBinding(
      sessionAEvent,
      delayedSessionABinding,
      'session-b'
    ),
    false
  );
  const current = {
    cancelled: false,
    owner_epoch: 7,
    current_owner_epoch: 7,
    owner_session_id: 'session-a',
    active_session_id: 'session-a',
    is_current_owner: true,
  };
  assert.equal(isCurrentProgressOwner(current), true);
  assert.equal(
    isCurrentProgressOwner({ ...current, active_session_id: 'session-b' }),
    false
  );
  assert.equal(
    isCurrentProgressOwner({ ...current, current_owner_epoch: 8 }),
    false
  );
  assert.equal(
    isCurrentProgressOwner({ ...current, is_current_owner: false }),
    false
  );
  assert.equal(isCurrentProgressOwner({ ...current, cancelled: true }), false);
});

test('ChatPanel retains one integrated route owner across the first-message layout transition', async () => {
  const source = await readFile(new URL('../src/components/ChatPanel/index.tsx', import.meta.url), 'utf8');
  const mounts = source.match(/<LiveVoiceIntegratedRoutePanel\b/g) ?? [];
  const mountIndex = source.indexOf('<LiveVoiceIntegratedRoutePanel');
  const conversationComposerIndex = source.indexOf('{hasConversation && (', mountIndex);

  assert.equal(mounts.length, 1);
  assert.notEqual(mountIndex, -1);
  assert.equal(conversationComposerIndex > mountIndex, true);
});

test('recognized P1 text can enter P2 while every retained voice operation blocks it', async () => {
  for (const status of ['starting', 'capturing', 'recognizing', 'playing', 'cleanup_pending']) {
    assert.equal(productTextBlockedByP1Status(status), true, status);
  }
  assert.equal(productTextBlockedByP1Status('recognized'), false);
  const source = await readFile(
    new URL('../src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx', import.meta.url),
    'utf8'
  );
  assert.match(source, /const recognition = await owner\.stopAndRecognize\(\)/);
  assert.match(source, /voice_commit_receipt: recognition\.voice_commit_receipt/);
  assert.match(source, /\? 'voice'\s*: 'structured'/);
  assert.match(source, /p1VoiceOwnerRef\.current\?\.status\(\)\.status/);
  assert.match(source, /if \(props\.isConnected\) return;/);
  assert.match(source, /voiceOwner\.close\(\)\.then/);
  assert.match(source, /\[props\.isConnected\]/);
});

test('voice Task origin is exact-session and exact-committed-text only', () => {
  const origin = Object.freeze({
    session_id: 'session-voice',
    interaction_id: 'interaction-voice',
    turn_id: 'turn-voice',
    commit_id: 'commit-voice',
    instruction: 'Create the bounded voice task.',
  });
  assert.deepEqual(
    resolveProductTaskCreateOrigin(
      'Create the bounded voice task.',
      'session-voice',
      origin
    ),
    {
      source: 'voice',
      interaction_id: 'interaction-voice',
      turn_id: 'turn-voice',
      commit_id: 'commit-voice',
    }
  );
  assert.deepEqual(
    resolveProductTaskCreateOrigin('Changed text.', 'session-voice', origin),
    { source: 'structured' }
  );
  assert.deepEqual(
    resolveProductTaskCreateOrigin(
      'Create the bounded voice task.',
      'session-other',
      origin
    ),
    { source: 'structured' }
  );
});

test('fresh task.create rebinds the panel progress owner to its exact task', async () => {
  const source = await readFile(
    new URL('../src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx', import.meta.url),
    'utf8'
  );

  assert.match(source, /setCreatedProgressTaskId\(createdTaskId\)/);
  assert.match(source, /task_id: createdProgressTaskId/);
  assert.match(source, /createdProgressTaskId, props\.activeSessionId/);
});

test('product barge-in stops local playout before any response cancel request', async () => {
  const source = await readFile(
    new URL('../src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx', import.meta.url),
    'utf8'
  );
  const start = source.indexOf('const stopProductVoicePlayout = async () =>');
  const end = source.indexOf('const commitRecognizedVoiceTaskOrigin', start);
  const handler = source.slice(start, end);
  const helperIndex = handler.indexOf('await executeProductVoiceBargeIn({');
  const clearIndex = handler.indexOf('activeVoiceResponseRef.current = null;');

  assert.equal(start >= 0 && end > start, true);
  assert.equal(helperIndex >= 0 && helperIndex < clearIndex, true);
  assert.match(handler, /catch \(error\) \{[\s\S]*setProductTextStatus\('failed'\);/);
});

test('product barge helper permits remote cancel only after one successful exact local stop', async () => {
  const response = {
    interaction_id: 'interaction-1',
    response_id: 'response-1',
    response_generation: 1,
  };
  const effects = [];
  const successfulP1 = {
    status: () => ({ status: 'playing', reason: null }),
    stopAgentPlayoutExact: async value => {
      effects.push(['local', value]);
      return Object.freeze({ kind: 'product_p1.agent_playout_stop.v1' });
    },
  };
  const p2 = {
    bargeIn: async value => {
      effects.push(['remote', value]);
      return Object.freeze({});
    },
  };

  assert.equal(await executeProductVoiceBargeIn({
    p1_owner: successfulP1,
    p2_owner: p2,
    response,
    action_id: 'barge-1',
    on_local_stop: () => effects.push(['clear']),
    on_response_cancel_accepted: () => effects.push(['cancelled']),
  }), true);
  assert.deepEqual(effects, [
    ['local', response],
    ['clear'],
    ['remote', {
      action_id: 'barge-1',
      response_id: 'response-1',
      response_generation: 1,
      cancel_response: true,
    }],
    ['cancelled'],
  ]);

  for (const stop of [async () => null, async () => { throw new Error('stop failed'); }]) {
    let remoteCalls = 0;
    const attempt = executeProductVoiceBargeIn({
      p1_owner: { status: () => ({ status: 'playing', reason: null }), stopAgentPlayoutExact: stop },
      p2_owner: { bargeIn: async () => { remoteCalls += 1; } },
      response,
      action_id: 'barge-rejected',
      on_local_stop: () => { throw new Error('must not clear'); },
      on_response_cancel_accepted: () => { throw new Error('must not fence cancel'); },
    });
    await attempt.catch(() => undefined);
    assert.equal(remoteCalls, 0);
  }

  const remoteFailureEffects = [];
  await assert.rejects(executeProductVoiceBargeIn({
    p1_owner: successfulP1,
    p2_owner: { bargeIn: async () => { throw new Error('cancel result unknown'); } },
    response,
    action_id: 'barge-unknown',
    on_local_stop: () => remoteFailureEffects.push('local'),
    on_response_cancel_accepted: () => remoteFailureEffects.push('cancelled'),
  }), /cancel result unknown/);
  assert.deepEqual(remoteFailureEffects, ['local']);

  let disabledEffects = 0;
  assert.equal(await executeProductVoiceBargeIn({
    p1_owner: {
      status: () => ({ status: 'closed', reason: null }),
      stopAgentPlayoutExact: async () => { disabledEffects += 1; return null; },
    },
    p2_owner: { bargeIn: async () => { disabledEffects += 1; } },
    response,
    action_id: 'barge-disabled',
    on_local_stop: () => { disabledEffects += 1; },
    on_response_cancel_accepted: () => { disabledEffects += 1; },
  }), false);
  assert.equal(disabledEffects, 0);
});

test('unknown response cancel is replayed exactly after reconnect before fence promotion', async () => {
  const binding = {
    session_id: 'session-1',
    correlation_id: 'correlation-1',
    interaction_id: 'interaction-1',
    activation_id: 'activation-1',
    activation_generation: 1,
  };
  const response = {
    interaction_id: binding.interaction_id,
    response_id: 'response-1',
    response_generation: 1,
  };
  const calls = [];
  let connected = true;
  let loseFirstResponse = true;
  const owner = new ProductWebP2ActivationOwner({
    enabled: true,
    request: async (method, params, requestId) => {
      calls.push([method, params, requestId]);
      if (method === PRODUCT_P2_ACTIVATE_METHOD) {
        return { ok: true, result: { status: 'active', ...binding } };
      }
      if (method === PRODUCT_P2_BARGE_IN_METHOD) {
        if (loseFirstResponse) {
          loseFirstResponse = false;
          connected = false;
          throw Object.assign(new Error('response lost after server accept'), {
            code: 'UNAVAILABLE',
          });
        }
        return {
          ok: true,
          result: {
            status: 'barge_in_applied',
            ...binding,
            action_id: params.action_id,
            response_id: params.response_id,
            response_generation: params.response_generation,
            cancel_response: true,
            applied: false,
            replayed: true,
            effect_ids: ['response.cancel:response-1:1'],
          },
        };
      }
      if (method === PRODUCT_P2_CLOSE_METHOD) {
        return { ok: true, result: { status: 'closed', ...binding } };
      }
      throw new Error(`forbidden method ${method}`);
    },
  });
  await owner.start(binding);
  let retained = null;
  let cancelAccepted = 0;

  await assert.rejects(executeProductVoiceBargeIn({
    p1_owner: {
      status: () => ({ status: 'playing', reason: null, retained_cleanup_pending: false }),
      stopAgentPlayoutExact: () => Object.freeze({ kind: 'product_p1.agent_playout_stop.v1' }),
    },
    p2_owner: owner,
    response,
    action_id: 'barge-reconnect-1',
    on_local_stop: () => {
      retained = Object.freeze({ owner, response, action_id: 'barge-reconnect-1' });
    },
    on_response_cancel_accepted: () => { cancelAccepted += 1; },
    is_current: () => connected,
  }), /response lost after server accept/);
  assert.notEqual(retained, null);
  assert.equal(cancelAccepted, 0);

  connected = true;
  const inflight = new WeakMap();
  const closeInput = {
    inflight,
    owner,
    settle_retained_cancel: () => settleRetainedProductVoiceResponseCancel({
      operation: retained,
      is_current: () => connected,
      on_accepted: () => { cancelAccepted += 1; },
    }),
    close: () => owner.closeWithRetry({ retry_delay_ms: 0 }),
  };
  const sessionSwitchClose = coordinateRetainedProductP2Close(closeInput);
  const unmountClose = coordinateRetainedProductP2Close(closeInput);
  assert.equal(sessionSwitchClose, unmountClose);
  await sessionSwitchClose;
  assert.equal(owner.snapshot().status, 'closed');
  assert.equal(cancelAccepted, 1);
  const cancelCalls = calls.filter(([method]) => method === PRODUCT_P2_BARGE_IN_METHOD);
  assert.equal(cancelCalls.length, 2);
  assert.deepEqual(cancelCalls[0][1], cancelCalls[1][1]);
  assert.equal(cancelCalls[0][2], cancelCalls[1][2]);
  assert.deepEqual(
    calls.slice(-2).map(([method]) => method),
    [PRODUCT_P2_BARGE_IN_METHOD, PRODUCT_P2_CLOSE_METHOD],
  );
  assert.equal(
    calls.some(([method]) => /submit|round|task/.test(method)),
    false,
  );
});

test('exact response surface fence prevents late audio and cancelled presentation resurrection', () => {
  const fence = new ProductResponseSurfaceFence();
  const response = {
    interaction_id: 'interaction-1',
    response_id: 'response-1',
    response_generation: 1,
  };
  let textEffects = 0;
  let audioEffects = 0;
  const present = () => executeProductPresentationWithFence({
    fence,
    response,
    on_text_presentation: () => { textEffects += 1; },
    on_audio_presentation: () => { audioEffects += 1; },
  });

  assert.equal(present(), 'full');
  assert.deepEqual([textEffects, audioEffects], [1, 1]);
  fence.fenceLocalStop(response);
  assert.equal(present(), 'text_only');
  assert.deepEqual([textEffects, audioEffects], [2, 1]);
  fence.fenceResponseCancelAccepted(response);
  assert.equal(present(), 'dropped');
  assert.deepEqual([textEffects, audioEffects], [2, 1]);

  const nextGeneration = { ...response, response_generation: 2 };
  assert.equal(executeProductPresentationWithFence({
    fence,
    response: nextGeneration,
    on_text_presentation: () => { textEffects += 1; },
    on_audio_presentation: () => { audioEffects += 1; },
  }), 'full');
  assert.deepEqual([textEffects, audioEffects], [3, 2]);
});

test('response surface tombstones outlive more than 128 late notifications without replay', () => {
  const fence = new ProductResponseSurfaceFence();
  const responses = Array.from({ length: 129 }, (_, index) => ({
    interaction_id: `interaction-${index}`,
    response_id: `response-${index}`,
    response_generation: 1,
  }));
  for (const response of responses) fence.fenceResponseCancelAccepted(response);
  let effects = 0;

  assert.equal(executeProductPresentationWithFence({
    fence,
    response: responses[0],
    on_text_presentation: () => { effects += 1; },
    on_audio_presentation: () => { effects += 1; },
  }), 'dropped');
  assert.equal(effects, 0);

  const saturated = new ProductResponseSurfaceFence(2);
  for (const response of responses.slice(0, 3)) {
    saturated.fenceResponseCancelAccepted(response);
  }
  assert.equal(executeProductPresentationWithFence({
    fence: saturated,
    response: { ...responses[2], response_generation: 2 },
    on_text_presentation: () => { effects += 1; },
    on_audio_presentation: () => { effects += 1; },
  }), 'dropped');
  assert.equal(effects, 0);
});

test('product P1 forwards the exact local-stop receipt without creating business cancel authority', async () => {
  const source = await readFile(
    new URL('../src/features/live-voice/formal/productP1VoiceRoute.ts', import.meta.url),
    'utf8'
  );
  const start = source.indexOf('stopAgentPlayoutExact(');
  const end = source.indexOf('async close(): Promise<void>', start);
  const method = source.slice(start, end);
  const releaseIndex = method.indexOf('this.#pendingPlayout = null;');
  const localIndex = method.indexOf('this.#audio.stopPlayoutExact(');
  const fenceIndex = method.indexOf('if (!receipt.local_fence_established) {');
  const mediaIndex = method.indexOf('pending.downlinkRoute.leaf.sendLocalPlaybackStop(receipt)');
  const cleanupIndex = method.indexOf("if (receipt.outcome !== 'local_fence_established') {");
  const rejectIndex = method.indexOf('pending.reject(');

  assert.equal(start >= 0 && end > start, true);
  assert.equal(
    releaseIndex >= 0
      && releaseIndex < localIndex
      && localIndex < fenceIndex
      && fenceIndex < mediaIndex
      && mediaIndex < cleanupIndex,
    true
  );
  assert.equal(rejectIndex >= 0, true);
  assert.match(method, /mediaStopDelivery = 'delivered'/);
  assert.match(method, /this\.#retainPlayoutAuthorityCleanup\(pending\.receiptAuthority\)/);
  assert.match(method, /return Object\.freeze\(\{\s*kind: 'product_p1\.agent_playout_stop\.v1'/);
  assert.match(method, /pending\.downlinkRoute\.leaf\.close\('MEDIA_LOCAL_CLOSE'\)/);
  assert.doesNotMatch(method, /round\.cancel|task\.cancel/);
});

test('missing Session stays unsupported in the rendered UI rather than inferring a fallback success', async () => {
  const html = await renderPanel({ sessionId: null });

  assert.equal(html.includes('data-implementation-class="unsupported"'), true);
  assert.equal((html.match(/PERSISTED_SESSION_REQUIRED/g) ?? []).length, 3);
  assert.equal(html.includes('formal adapter seams present'), false);
  assert.equal(html.includes('wired:true'), false);
});

test('route panel discloses permission, origin, device, activation, lifecycle, network, and unwired AIO diagnostics', async () => {
  const html = await renderPanel({
    platform: {
      secure_context: false,
      origin_scope: 'deployed',
      transport_security: 'insecure',
      browser_family: 'google_chrome',
      browser_version: '150.0.7871.116',
      alpha_browser_scope: 'desktop_google_chrome_candidate',
      reported_platform: 'Win32',
      microphone_permission: 'denied',
      audio_input: 'not_enumerated',
      audio_output: 'enumerated',
      user_activation: 'required',
      page_visibility: 'hidden',
      page_was_discarded: true,
      network: 'offline',
      aio_capability: {
        enabled: true,
        secure_context: false,
        document_visibility: false,
        media_devices: true,
        audio_context: true,
        audio_worklet_node: true,
        stable_identity: true,
        capture_pcm_f32: false,
        playout_pcm_f32: false,
        media_recorder_realtime: false,
        output_device_selection: false,
        physical_heard_ack: false,
        reasons: ['INSECURE_CONTEXT'],
      },
      diagnostic_errors: ['MICROPHONE_PERMISSION_QUERY_FAILED'],
    },
  });

  for (const fact of [
    'google_chrome 150.0.7871.116',
    'desktop_google_chrome_candidate',
    'scope:deployed; transport:insecure; secure_context:false',
    'denied',
    'input:not_enumerated; output:enumerated',
    'required',
    'visibility:hidden; discarded:true',
    'offline',
    'capture:false; playout:false; wired:false',
    'MICROPHONE_PERMISSION_QUERY_FAILED',
  ]) {
    assert.equal(html.includes(fact), true, fact);
  }
});
