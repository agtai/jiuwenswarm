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
  bindProductVoiceTaskOrigin,
  classifyProductP2Notification,
  extractWebErrorReason,
  inspectProductP3RetryCandidate,
  isCurrentProgressOwner,
  reconcileProductP3ProgressEvent,
  productP2WebRequestOptions,
  productVoiceDraftMatchesBinding,
  recognizedSpeechConfirmationMatches,
  productTextBlockedByP1Status,
  progressMatchesOwnedBinding,
  resolveProductTaskCreateOrigin,
  retainBoundedPresentedProductResponse,
} from '../node_modules/.cache/live-voice-integrated-web/LiveVoiceIntegratedRoutePanel.mjs';
import {
  FormalTaskControlLeaf,
  isFormalTaskRetryEligible,
} from '../node_modules/.cache/live-voice-integrated-web/features/live-voice/formal/formalTaskControlLeaf.js';
import {
  PRODUCT_P2_NOTIFICATION_NEXT_METHOD,
  PRODUCT_P2_SUBMIT_METHOD,
} from '../node_modules/.cache/live-voice-integrated-web/features/live-voice/formal/productWebActivation.js';
import {
  IntegratedWebRouteShell,
  createCurrentIntegratedWebRouteSelection,
} from '../node_modules/.cache/live-voice-integrated-web/features/live-voice/formal/integratedWebRouteShell.js';
import { parseProductTextProgressEvent } from '../node_modules/.cache/live-voice-integrated-web/features/live-voice/formal/productTextProgress.js';

const retryBinding = Object.freeze({
  subject_id: 'principal-1',
  session_id: 'session-1',
  project_id: 'project-1',
  correlation_id: 'correlation-1',
  generation: 1,
});

const retryScope = Object.freeze({
  subject_id: retryBinding.subject_id,
  session_id: retryBinding.session_id,
  project_id: retryBinding.project_id,
  assurance: 'authenticated',
});

function retryStatus({ taskId = 'task-1', attemptId = 'attempt-b', attemptNumber = 2, state = 'terminal', outcome = 'completed', eventHead = 3 } = {}) {
  return {
    ok: true,
    result: {
      task: {
        task_id: taskId,
        scope: { ...retryScope },
        correlation_id: retryBinding.correlation_id,
        attempt_id: attemptId,
        state,
        outcome,
        event_head: eventHead,
      },
      attempt: { task_id: taskId, attempt_id: attemptId, attempt_number: attemptNumber },
    },
  };
}

function retryEvent(seq, { attemptId, eventType, state, outcome = null, sourceEventId, causationId, details = {}, producer = 'task_core' } = {}) {
  const source = sourceEventId === undefined ? (seq === 0 ? null : `source-${seq}`) : sourceEventId;
  return {
    event_id: `task-1:event:${seq}`,
    task_id: 'task-1',
    attempt_id: attemptId,
    scope: { ...retryScope },
    seq,
    event_type: eventType,
    state,
    outcome,
    producer,
    source_event_id: source,
    causation_id: causationId ?? source ?? `cause-${seq}`,
    correlation_id: retryBinding.correlation_id,
    occurred_at: '2026-08-09T12:00:00Z',
    details,
  };
}

function retryHistoryThroughB() {
  return [
    retryEvent(0, { attemptId: 'attempt-a', eventType: 'task.accepted', state: 'accepted' }),
    retryEvent(1, { attemptId: 'attempt-a', eventType: 'task.terminal', state: 'terminal', outcome: 'cancelled' }),
    retryEvent(2, {
      attemptId: 'attempt-b',
      eventType: 'task.retry_accepted',
      state: 'accepted',
      sourceEventId: null,
      causationId: 'retry-b',
      details: {
        command_id: 'retry-b',
        retry_of_attempt_id: 'attempt-a',
        previous_outcome: 'cancelled',
        attempt_number: 2,
      },
    }),
    retryEvent(3, {
      attemptId: 'attempt-b',
      eventType: 'task.terminal',
      state: 'terminal',
      outcome: 'completed',
      producer: 'task_core.delivery',
    }),
  ];
}

function retryEvents(events = retryHistoryThroughB(), headSeq = 3) {
  return {
    ok: true,
    result: { events, head_seq: headSeq, task_id: 'task-1', after_seq: -1 },
  };
}

function productProgressForTaskEvent(event, { sourceOutcome = event.outcome, progressOutcome = event.outcome } = {}) {
  const sourcePayload = { state: event.state };
  if (sourceOutcome !== null) sourcePayload.outcome = sourceOutcome;
  const raw = {
    event_type: 'live_voice.task.progress',
    delivery_id: `delivery-${event.seq}`,
    session_id: retryBinding.session_id,
    project_id: retryBinding.project_id,
    task_id: event.task_id,
    correlation_id: retryBinding.correlation_id,
    origin_id: 'origin-1',
    generation_kind: 'web_task_progress_generation',
    generation_id: 'generation-1',
    generation: 1,
    evidence_id: `evidence-${event.seq}`,
    source_event: {
      event_id: event.event_id,
      event_type: event.event_type,
      seq: event.seq,
      correlation_id: event.correlation_id,
      causation_id: event.causation_id,
      stream_ref: { kind: 'task', id: event.task_id },
      scope: { ...event.scope },
      payload: sourcePayload,
      extensions: {
        'jiuwenswarm.task_progress_return': {
          persistent_event_seq: event.seq,
          persistent_event_type: event.event_type,
          persistent_event_producer: event.producer,
          persistent_attempt_id: event.attempt_id,
          persistent_source_event_id: event.source_event_id,
        },
      },
    },
    progress_event: {
      event_id: `task-progress:${event.event_id}`,
      event_type: 'work.progress',
      seq: event.seq,
      correlation_id: event.correlation_id,
      causation_id: event.event_id,
      stream_ref: { kind: 'task', id: event.task_id },
      scope: { ...event.scope },
      payload: {
        work_ref: { kind: 'task', id: event.task_id },
        seq: event.seq,
        state: event.state,
        outcome: progressOutcome,
      },
    },
  };
  const parsed = parseProductTextProgressEvent(raw);
  assert.notEqual(parsed, null);
  return parsed;
}

function adoptTaskEvents(leaf, response) {
  leaf.adopt('task.events', response, {
    connection_generation: leaf.snapshot().connection_generation,
    command_id: null,
    target_task_id: null,
    events_query: { task_id: 'task-1', after_seq: -1 },
  });
}

async function renderPanel({ sessionId = 'persisted-session', platform = null, progress = null, viewProps = {} } = {}) {
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
      extensions: {
        'jiuwenswarm.task_progress_return': {
          persistent_event_seq: 11,
          persistent_event_type: 'task.running',
          persistent_event_producer: 'task_core',
          persistent_attempt_id: 'attempt-product-1',
          persistent_source_event_id: null,
        },
      },
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

test('formal P1 discloses the 30-second capture bound and disables restart on terminal failure', async () => {
  const html = await renderPanel({
    viewProps: {
      p1VoiceEnabled: true,
      p1VoiceStatus: 'failed',
      p1VoiceReason: 'AUDIO_CAPTURE_DURATION_EXCEEDED',
      onP1VoiceStart: () => {},
      onP1VoiceStop: () => {},
    },
  });

  assert.equal(html.includes('This turn retains at most 30 seconds of captured audio.'), true);
  assert.equal(html.includes('audio captured during overlapping playback counts toward the limit.'), true);
  assert.equal(html.includes('Speak and press Stop and recognize before the limit.'), true);
  assert.equal(html.includes('AUDIO_CAPTURE_DURATION_EXCEEDED'), true);
  assert.equal(html.includes('The expired capture was discarded without a new Speech or Agent submission. Refresh to start again.'), true);
  assert.match(html, /<button type="button" disabled="">Start formal voice turn<\/button>/);
});

test('recognized Speech confirmation is an explicit in-page second action that locks dispatch inputs', async () => {
  const html = await renderPanel({
    viewProps: {
      p2Activation: { status: 'active', binding: null, reason: null },
      productInput: 'Confirm this exact recognized text.',
      productTextStatus: 'idle',
      p1VoiceEnabled: true,
      p1VoiceStatus: 'recognized',
      onP1VoiceStart: () => {},
      onP1VoiceStop: () => {},
      onProductInput: () => {},
      onProductSubmit: () => {},
      recognizedSpeechConfirmation: 'agent',
      onRecognizedSpeechConfirm: () => {},
      onRecognizedSpeechCancel: () => {},
    },
  });

  assert.match(html, /data-testid="live-voice-integrated-recognized-confirmation"/);
  assert.match(html, /Review recognized speech/);
  assert.match(html, /Confirm and dispatch/);
  assert.match(html, /Cancel/);
  assert.match(html, /<textarea[^>]*disabled=""[^>]*>Confirm this exact recognized text\.<\/textarea>/);
  assert.match(html, /<button type="submit" disabled="">Submit committed turn<\/button>/);

  const source = await readFile(new URL('../src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx', import.meta.url), 'utf8');
  assert.doesNotMatch(source, /window\.confirm\('Confirm that the recognized speech/);
});

test('recognized Speech confirmation is fenced to its exact Session and displayed text', () => {
  const pending = Object.freeze({
    intent: 'agent',
    phase: 'confirming',
    session_id: 'session-1',
    text: 'exact text',
    correlation_id: 'correlation-1',
    interaction_id: 'interaction-1',
    activation_id: 'activation-1',
    activation_generation: 2,
  });
  const recognized = Object.freeze({
    session_id: 'session-1',
    text: 'exact text',
    correlation_id: 'correlation-1',
    interaction_id: 'interaction-1',
    activation_id: 'activation-1',
    activation_generation: 2,
  });
  const binding = Object.freeze({
    session_id: 'session-1',
    correlation_id: 'correlation-1',
    interaction_id: 'interaction-1',
    activation_id: 'activation-1',
    activation_generation: 2,
  });

  assert.equal(recognizedSpeechConfirmationMatches(pending, recognized, 'session-1', 'exact text', binding), true);
  assert.equal(recognizedSpeechConfirmationMatches(pending, recognized, 'session-2', 'exact text', binding), false);
  assert.equal(recognizedSpeechConfirmationMatches(pending, recognized, 'session-1', 'changed text', binding), false);
  assert.equal(recognizedSpeechConfirmationMatches(pending, null, 'session-1', 'exact text', binding), false);
  assert.equal(recognizedSpeechConfirmationMatches(pending, recognized, 'session-1', 'exact text', { ...binding, activation_generation: 3 }), false);
  assert.equal(recognizedSpeechConfirmationMatches(pending, { ...recognized, activation_generation: 1 }, 'session-1', 'exact text', binding), false);
});

test('edited voice draft confirmation remains fenced to the exact P2 activation', () => {
  const draft = Object.freeze({
    session_id: 'session-1',
    correlation_id: 'correlation-1',
    interaction_id: 'interaction-1',
    activation_id: 'activation-1',
    activation_generation: 2,
  });
  const binding = Object.freeze({ ...draft });

  assert.equal(productVoiceDraftMatchesBinding(draft, 'session-1', binding), true);
  assert.equal(productVoiceDraftMatchesBinding(draft, 'session-2', binding), false);
  assert.equal(productVoiceDraftMatchesBinding(draft, 'session-1', { ...binding, correlation_id: 'correlation-2' }), false);
  assert.equal(productVoiceDraftMatchesBinding(draft, 'session-1', { ...binding, interaction_id: 'interaction-2' }), false);
  assert.equal(productVoiceDraftMatchesBinding(draft, 'session-1', { ...binding, activation_id: 'activation-2' }), false);
  assert.equal(productVoiceDraftMatchesBinding(draft, 'session-1', { ...binding, activation_generation: 3 }), false);
  assert.equal(productVoiceDraftMatchesBinding(null, 'session-1', binding), false);
  assert.equal(productVoiceDraftMatchesBinding(draft, 'session-1', null), false);
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
  assert.deepEqual(productP2WebRequestOptions(PRODUCT_P2_NOTIFICATION_NEXT_METHOD, 'notification-request-1'), {
    requestId: 'notification-request-1',
    timeoutMs: PRODUCT_P2_NOTIFICATION_CLIENT_TIMEOUT_MS,
  });
  assert.equal(PRODUCT_P2_NOTIFICATION_CLIENT_TIMEOUT_MS > 600_000, true);
  assert.deepEqual(productP2WebRequestOptions(PRODUCT_P2_SUBMIT_METHOD, 'submit-request-1'), { requestId: 'submit-request-1' });
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
      p3MutationEnabled: true,
      p3MutationOperation: 'task.create',
      p3TaskName: 'retained task',
      p3TaskInstruction: 'retained instruction',
      p3MutationStatus: 'idle',
      onP3MutationOperation: () => {},
      onP3TaskName: () => {},
      onP3TaskInstruction: () => {},
      onP3TargetTaskId: () => {},
      onP3Issue: () => {},
      onP3Execute: () => {},
    },
  });

  assert.match(html, /<textarea[^>]*disabled=""[^>]*>retained exact text<\/textarea>/);
  assert.match(html, /<button[^>]*type="submit"[^>]*disabled=""/);
  assert.match(html, /<select[^>]*disabled=""/);
  assert.match(html, /<input[^>]*disabled=""[^>]*value="retained task"/);
  assert.match(html, /<button[^>]*disabled="">Issue confirmation<\/button>/);
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

test('route panel renders authoritative completed and failed P3 terminal truth', async () => {
  for (const status of ['completed', 'failed']) {
    const html = await renderPanel({
      viewProps: {
        p3MutationEnabled: true,
        p3MutationOperation: 'task.cancel',
        p3TargetTaskId: 'task-1',
        p3MutationStatus: status,
        onP3MutationOperation: () => {},
        onP3TaskName: () => {},
        onP3TaskInstruction: () => {},
        onP3TargetTaskId: () => {},
        onP3InspectRetry: () => {},
        onP3Issue: () => {},
        onP3Execute: () => {},
      },
    });
    assert.match(html, new RegExp(`<code>${status}</code>`));
    assert.equal(html.includes('Acceptance is not task completion.'), true);
  }
});

test('route panel exposes task.retry only for an inspected eligible terminal attempt', async () => {
  const base = {
    p3MutationEnabled: true,
    p3MutationOperation: 'task.cancel',
    p3TargetTaskId: 'task-1',
    p3MutationStatus: 'idle',
    onP3MutationOperation: () => {},
    onP3TaskName: () => {},
    onP3TaskInstruction: () => {},
    onP3TargetTaskId: () => {},
    onP3InspectRetry: () => {},
    onP3Issue: () => {},
    onP3Execute: () => {},
  };
  const hidden = await renderPanel({
    viewProps: {
      ...base,
      p3RetryEligible: false,
      p3RetryInspectionStatus: 'ineligible',
    },
  });
  assert.equal(hidden.includes('value="task.retry"'), false);
  assert.equal(hidden.includes('Check retry eligibility'), true);

  const visible = await renderPanel({
    viewProps: {
      ...base,
      p3MutationOperation: 'task.retry',
      p3RetryEligible: true,
      p3RetryAttemptNumber: 2,
      p3RetryInspectionStatus: 'eligible',
    },
  });
  assert.equal(visible.includes('value="task.retry"'), true);
  assert.equal(visible.includes('Retry eligible task'), true);
  assert.equal(visible.includes('eligible:2/3'), true);
  assert.equal(visible.includes('Issue confirmation'), true);
  assert.equal(visible.includes('Execute confirmed mutation'), false);
});

test('retry candidate inspection binds exact status and full A/B history before exposing eligibility', async () => {
  const leaf = new FormalTaskControlLeaf({ enabled: true, binding: retryBinding });
  const calls = [];
  const record = await inspectProductP3RetryCandidate({
    leaf,
    session_id: 'session-1',
    task_id: 'task-1',
    request_nonce: 'positive',
    is_current: () => true,
    request: async (method, params, options) => {
      calls.push({ method, params, options });
      if (method === 'live_voice.task.status') return retryStatus();
      if (method === 'live_voice.task.events') return retryEvents();
      throw new Error(`unexpected method ${method}`);
    },
  });

  assert.deepEqual(calls, [
    {
      method: 'live_voice.task.status',
      params: { session_id: 'session-1', task_id: 'task-1' },
      options: { requestId: 'web-task-status-positive' },
    },
    {
      method: 'live_voice.task.events',
      params: { session_id: 'session-1', task_id: 'task-1', after_seq: -1 },
      options: { requestId: 'web-task-events-positive' },
    },
  ]);
  assert.equal(isFormalTaskRetryEligible(record), true);
  assert.deepEqual(
    {
      task_id: record.task_id,
      attempt_id: record.attempt_id,
      attempt_number: record.attempt_number,
      state: record.state,
      outcome: record.outcome,
      event_head: record.event_head,
    },
    {
      task_id: 'task-1',
      attempt_id: 'attempt-b',
      attempt_number: 2,
      state: 'terminal',
      outcome: 'completed',
      event_head: 3,
    }
  );
  assert.deepEqual(leaf.snapshot().tasks, [record]);
});

test('retry candidate inspection rejects a foreign status before events with zero live-replica effect', async () => {
  const leaf = new FormalTaskControlLeaf({ enabled: true, binding: retryBinding });
  let calls = 0;
  await assert.rejects(
    inspectProductP3RetryCandidate({
      leaf,
      session_id: 'session-1',
      task_id: 'task-1',
      request_nonce: 'foreign',
      is_current: () => true,
      request: async method => {
        calls += 1;
        if (method !== 'live_voice.task.status') throw new Error('events must not be requested');
        return retryStatus({ taskId: 'task-foreign', attemptId: 'attempt-foreign', attemptNumber: 1 });
      },
    }),
    /binding mismatch/
  );
  assert.equal(calls, 1);
  assert.deepEqual(leaf.snapshot().tasks, []);
});

test('retry candidate inspection rejects a stale Session binding before any network effect', async () => {
  const wrongSessionLeaf = new FormalTaskControlLeaf({ enabled: true, binding: retryBinding });
  const disconnectedLeaf = new FormalTaskControlLeaf({ enabled: true, binding: retryBinding });
  disconnectedLeaf.disconnect();
  for (const [leaf, sessionId] of [
    [wrongSessionLeaf, 'session-foreign'],
    [disconnectedLeaf, 'session-1'],
  ]) {
    let calls = 0;
    await assert.rejects(
      inspectProductP3RetryCandidate({
        leaf,
        session_id: sessionId,
        task_id: 'task-1',
        request_nonce: 'stale-session',
        is_current: () => true,
        request: async () => {
          calls += 1;
          throw new Error('network must not be reached');
        },
      }),
      /Session binding/
    );
    assert.equal(calls, 0);
    assert.deepEqual(leaf.snapshot().tasks, []);
  }
});

test('retry candidate inspection rejects same-head status/events disagreement with zero live-replica effect', async () => {
  const leaf = new FormalTaskControlLeaf({ enabled: true, binding: retryBinding });
  const staleBAtHeadFour = [
    retryEvent(0, { attemptId: 'attempt-a', eventType: 'task.accepted', state: 'accepted' }),
    retryEvent(1, { attemptId: 'attempt-a', eventType: 'task.terminal', state: 'terminal', outcome: 'cancelled' }),
    retryEvent(2, {
      attemptId: 'attempt-b',
      eventType: 'task.retry_accepted',
      state: 'accepted',
      sourceEventId: null,
      causationId: 'retry-b',
      details: {
        command_id: 'retry-b',
        retry_of_attempt_id: 'attempt-a',
        previous_outcome: 'cancelled',
        attempt_number: 2,
      },
    }),
    retryEvent(3, { attemptId: 'attempt-b', eventType: 'task.running', state: 'running' }),
    retryEvent(4, { attemptId: 'attempt-b', eventType: 'task.terminal', state: 'terminal', outcome: 'completed' }),
  ];
  await assert.rejects(
    inspectProductP3RetryCandidate({
      leaf,
      session_id: 'session-1',
      task_id: 'task-1',
      request_nonce: 'conflict',
      is_current: () => true,
      request: async method =>
        method === 'live_voice.task.status'
          ? retryStatus({ attemptId: 'attempt-c', attemptNumber: 3, state: 'accepted', outcome: null, eventHead: 4 })
          : retryEvents(staleBAtHeadFour, 4),
    }),
    /replay conflicts/
  );
  assert.deepEqual(leaf.snapshot().tasks, []);
});

test('overlapping retry inspections let only the current generation perform events and publish truth', async () => {
  const leaf = new FormalTaskControlLeaf({ enabled: true, binding: retryBinding });
  let currentGeneration = 1;
  let releaseOldStatus;
  const oldStatus = new Promise(resolve => {
    releaseOldStatus = resolve;
  });
  const oldCalls = [];
  const oldInspection = inspectProductP3RetryCandidate({
    leaf,
    session_id: 'session-1',
    task_id: 'task-1',
    request_nonce: 'old',
    is_current: () => currentGeneration === 1,
    request: async method => {
      oldCalls.push(method);
      if (method !== 'live_voice.task.status') throw new Error('stale inspection issued events');
      return oldStatus;
    },
  });

  currentGeneration = 2;
  const currentRecord = await inspectProductP3RetryCandidate({
    leaf,
    session_id: 'session-1',
    task_id: 'task-1',
    request_nonce: 'current',
    is_current: () => currentGeneration === 2,
    request: async method => (method === 'live_voice.task.status' ? retryStatus() : retryEvents()),
  });
  releaseOldStatus(retryStatus());

  await assert.rejects(oldInspection, /became stale/);
  assert.deepEqual(oldCalls, ['live_voice.task.status']);
  assert.equal(currentRecord.attempt_id, 'attempt-b');
  assert.equal(isFormalTaskRetryEligible(currentRecord), true);
  assert.equal(leaf.snapshot().tasks[0].attempt_id, 'attempt-b');
  assert.equal(leaf.snapshot().tasks[0].attempt_number, 2);
});

test('P3 progress reconciliation advances accepted UI truth only from exact authoritative terminal events', async () => {
  for (const outcome of ['completed', 'failed']) {
    const leaf = new FormalTaskControlLeaf({ enabled: true, binding: retryBinding });
    const accepted = retryEvent(0, { attemptId: 'attempt-a', eventType: 'task.accepted', state: 'accepted' });
    const terminal = retryEvent(1, {
      attemptId: 'attempt-a',
      eventType: 'task.terminal',
      state: 'terminal',
      outcome,
      producer: 'task_core.delivery',
    });
    adoptTaskEvents(leaf, retryEvents([accepted], 0));
    const calls = [];
    const record = await reconcileProductP3ProgressEvent({
      request: async (method, params, options) => {
        calls.push({ method, params, options });
        return retryEvents([accepted, terminal], 1);
      },
      leaf,
      event: productProgressForTaskEvent(terminal),
      session_id: 'session-1',
      request_nonce: `terminal-${outcome}`,
      is_current: () => true,
    });

    assert.equal(record.state, 'terminal');
    assert.equal(record.outcome, outcome);
    assert.deepEqual(leaf.snapshot().progress_receipts, [`task-progress:${terminal.event_id}`]);
    assert.deepEqual(calls, [
      {
        method: 'live_voice.task.events',
        params: { session_id: 'session-1', task_id: 'task-1', after_seq: -1 },
        options: { requestId: `web-task-progress-events-terminal-${outcome}` },
      },
    ]);
  }
});

test('P3 progress reconciliation works after reconnect with the new connection generation', async () => {
  const leaf = new FormalTaskControlLeaf({ enabled: true, binding: retryBinding });
  const accepted = retryEvent(0, { attemptId: 'attempt-a', eventType: 'task.accepted', state: 'accepted' });
  const completed = retryEvent(1, {
    attemptId: 'attempt-a',
    eventType: 'task.terminal',
    state: 'terminal',
    outcome: 'completed',
    producer: 'task_core.delivery',
  });
  adoptTaskEvents(leaf, retryEvents([accepted], 0));
  leaf.disconnect();
  leaf.reconnect(retryBinding);

  const record = await reconcileProductP3ProgressEvent({
    request: async () => retryEvents([accepted, completed], 1),
    leaf,
    event: productProgressForTaskEvent(completed),
    session_id: 'session-1',
    request_nonce: 'reconnect',
    is_current: () => true,
  });

  assert.equal(leaf.snapshot().connection_generation, 2);
  assert.equal(record.outcome, 'completed');
});

test('P3 progress reconciliation fails closed on outcome disagreement without live adoption', async () => {
  const leaf = new FormalTaskControlLeaf({ enabled: true, binding: retryBinding });
  const accepted = retryEvent(0, { attemptId: 'attempt-a', eventType: 'task.accepted', state: 'accepted' });
  const failed = retryEvent(1, {
    attemptId: 'attempt-a',
    eventType: 'task.terminal',
    state: 'terminal',
    outcome: 'failed',
    producer: 'task_core.delivery',
  });
  adoptTaskEvents(leaf, retryEvents([accepted], 0));

  await assert.rejects(
    reconcileProductP3ProgressEvent({
      request: async () => retryEvents([accepted, failed], 1),
      leaf,
      event: productProgressForTaskEvent(failed, { progressOutcome: 'completed' }),
      session_id: 'session-1',
      request_nonce: 'outcome-conflict',
      is_current: () => true,
    }),
    /source, state, outcome, or producer mismatch/
  );
  assert.equal(leaf.snapshot().tasks[0].state, 'accepted');
  assert.deepEqual(leaf.snapshot().progress_receipts, []);
});

test('late predecessor progress cannot overwrite a successor attempt', async () => {
  const leaf = new FormalTaskControlLeaf({ enabled: true, binding: retryBinding });
  const acceptedA = retryEvent(0, { attemptId: 'attempt-a', eventType: 'task.accepted', state: 'accepted' });
  const cancelledA = retryEvent(1, {
    attemptId: 'attempt-a',
    eventType: 'task.terminal',
    state: 'terminal',
    outcome: 'cancelled',
    producer: 'task_core.delivery',
  });
  const retryB = retryEvent(2, {
    attemptId: 'attempt-b',
    eventType: 'task.retry_accepted',
    state: 'accepted',
    sourceEventId: null,
    causationId: 'retry-b',
    details: {
      command_id: 'retry-b',
      retry_of_attempt_id: 'attempt-a',
      previous_outcome: 'cancelled',
      attempt_number: 2,
    },
  });
  adoptTaskEvents(leaf, retryEvents([acceptedA], 0));
  let releaseEvents;
  const delayedEvents = new Promise(resolve => {
    releaseEvents = resolve;
  });
  const predecessor = reconcileProductP3ProgressEvent({
    request: async () => delayedEvents,
    leaf,
    event: productProgressForTaskEvent(cancelledA),
    session_id: 'session-1',
    request_nonce: 'late-a',
    is_current: () => true,
  });

  adoptTaskEvents(leaf, retryEvents([acceptedA, cancelledA, retryB], 2));
  releaseEvents(retryEvents([acceptedA, cancelledA], 1));

  await assert.rejects(predecessor, /became stale/);
  assert.equal(leaf.snapshot().tasks[0].attempt_id, 'attempt-b');
  assert.equal(leaf.snapshot().tasks[0].state, 'accepted');
  assert.deepEqual(leaf.snapshot().progress_receipts, []);
});

test('foreign-task progress is rejected before any reconciliation request', async () => {
  const leaf = new FormalTaskControlLeaf({ enabled: true, binding: retryBinding });
  const accepted = retryEvent(0, { attemptId: 'attempt-a', eventType: 'task.accepted', state: 'accepted' });
  adoptTaskEvents(leaf, retryEvents([accepted], 0));
  let calls = 0;
  const foreign = productProgressForTaskEvent({ ...accepted, task_id: 'task-foreign' });

  await assert.rejects(
    reconcileProductP3ProgressEvent({
      request: async () => {
        calls += 1;
        return retryEvents([accepted], 0);
      },
      leaf,
      event: foreign,
      session_id: 'session-1',
      request_nonce: 'foreign-task',
      is_current: () => true,
    }),
    /exact Session\/task\/attempt binding/
  );
  assert.equal(calls, 0);
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
    assert.equal(progressMatchesOwnedBinding({ ...event, [field]: value }, binding, 'session-1'), false, field);
  }
  assert.equal(progressMatchesOwnedBinding(event, binding, 'session-2'), false);
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

  assert.equal(progressMatchesOwnedBinding(sessionAEvent, delayedSessionABinding, 'session-b'), false);
  const current = {
    cancelled: false,
    owner_epoch: 7,
    current_owner_epoch: 7,
    owner_session_id: 'session-a',
    active_session_id: 'session-a',
    is_current_owner: true,
  };
  assert.equal(isCurrentProgressOwner(current), true);
  assert.equal(isCurrentProgressOwner({ ...current, active_session_id: 'session-b' }), false);
  assert.equal(isCurrentProgressOwner({ ...current, current_owner_epoch: 8 }), false);
  assert.equal(isCurrentProgressOwner({ ...current, is_current_owner: false }), false);
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

test('actual Live Voice product entry selects the formal P1 owner while compatibility fallback remains flag-off only', async () => {
  const source = await readFile(new URL('../src/components/ChatPanel/index.tsx', import.meta.url), 'utf8');
  const barSource = await readFile(new URL('../src/components/ChatPanel/LiveVoiceDemoBar.tsx', import.meta.url), 'utf8');

  assert.match(source, /FEATURE_LIVE_VOICE_INTEGRATED_WEB\s*&&\s*FEATURE_LIVE_VOICE_INTEGRATED_P1/);
  assert.match(source, /const liveVoiceDemoProps = formalProductVoiceEnabled \? formalLiveVoiceDemoProps : legacyLiveVoiceDemoProps/);
  assert.match(source, /productVoiceControlRef\.current\?\.start\(\)/);
  assert.match(source, /productVoiceControlRef\.current\?\.stop\(\)/);
  assert.match(source, /productVoiceControlRef\.current\?\.confirm\(\)/);
  assert.match(source, /productVoiceControlRef=\{formalProductVoiceEnabled \? productVoiceControlRef : undefined\}/);
  assert.match(source, /liveVoice\.formal\.routeLabel/);
  assert.match(barSource, /data-testid="live-voice-product-confirmation"/);
  assert.match(barSource, /editableTranscript/);
});

test('integrated route diagnostics remain vertically reachable in a bounded panel', async () => {
  const source = await readFile(new URL('../src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.css', import.meta.url), 'utf8');
  const bodyRule = source.match(/\.live-voice-integrated__body\s*\{(?<body>[\s\S]*?)\}/)?.groups?.body ?? '';

  assert.match(bodyRule, /max-height:\s*min\(70vh, 720px\)/);
  assert.match(bodyRule, /overflow-y:\s*auto/);
  assert.match(bodyRule, /overscroll-behavior:\s*contain/);
  assert.match(bodyRule, /scrollbar-gutter:\s*stable/);
});

test('recognized P1 text can enter P2 while every retained voice operation blocks it', async () => {
  for (const status of ['starting', 'capturing', 'recognizing', 'playing', 'cleanup_pending']) {
    assert.equal(productTextBlockedByP1Status(status), true, status);
  }
  assert.equal(productTextBlockedByP1Status('recognized'), false);
  const source = await readFile(new URL('../src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx', import.meta.url), 'utf8');
  assert.match(source, /const recognition = await owner\.stopAndRecognize\(\)/);
  assert.match(source, /voice_commit_receipt: recognition\.voice_commit_receipt/);
  assert.match(source, /intent: 'agent'[\s\S]{0,300}session_id: recognized\.session_id[\s\S]{0,120}text: recognized\.text/);
  assert.match(source, /await submitProductText\(undefined, 'voice'\)/);
  assert.match(source, /p1VoiceOwnerRef\.current\?\.status\(\)\.status/);
  assert.match(source, /if \(props\.isConnected\) return;/);
  assert.match(source, /voiceOwner\s*\.close\(\)\s*\.then/);
  assert.match(source, /\[props\.isConnected\]/);
});

test('voice Task origin is exact-session and exact-committed-text only', () => {
  const origin = Object.freeze({
    session_id: 'session-voice',
    interaction_id: 'interaction-voice',
    turn_id: 'turn-voice',
    commit_id: 'commit-voice',
    response_id: 'response-server-voice',
    response_generation: 4,
    instruction: 'Create the bounded voice task.',
  });
  assert.deepEqual(resolveProductTaskCreateOrigin('Create the bounded voice task.', 'session-voice', origin), {
    source: 'voice',
    interaction_id: 'interaction-voice',
    turn_id: 'turn-voice',
    commit_id: 'commit-voice',
  });
  assert.deepEqual(resolveProductTaskCreateOrigin('Changed text.', 'session-voice', origin), { source: 'structured' });
  assert.deepEqual(resolveProductTaskCreateOrigin('Create the bounded voice task.', 'session-other', origin), { source: 'structured' });
});

test('voice Task origin adopts only the canonical CR response returned by the server', () => {
  const origin = bindProductVoiceTaskOrigin(
    {
      commit_id: 'commit-voice',
      turn_id: 'turn-voice',
      committed_at: '2026-08-10T00:00:00Z',
      text: 'Create the bounded voice task.',
      dispatch_target: 'task',
      voice_commit_receipt: 'receipt-voice',
      critical_confirmation: true,
    },
    {
      status: 'task_origin_accepted',
      turn_id: 'turn-voice',
      commit_id: 'commit-voice',
      activation_generation: 99,
      response: {
        interaction_id: 'interaction-voice',
        response_id: 'response-server-voice',
        response_generation: 4,
      },
    },
    'session-voice',
    'interaction-voice'
  );

  assert.equal(origin.response_id, 'response-server-voice');
  assert.equal(origin.response_generation, 4);
  assert.notEqual(origin.response_generation, 99);
});

test('fresh task.create rebinds the panel progress owner to its exact task', async () => {
  const source = await readFile(new URL('../src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx', import.meta.url), 'utf8');

  assert.match(source, /setCreatedProgressTaskId\(createdTaskId\)/);
  assert.match(source, /task_id: createdProgressTaskId/);
  assert.match(source, /createdProgressTaskId, props\.activeSessionId/);
});

test('product barge-in stops local playout before any response cancel request', async () => {
  const source = await readFile(new URL('../src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx', import.meta.url), 'utf8');
  const start = source.indexOf('const stopProductVoicePlayout = async () =>');
  const end = source.indexOf('const commitRecognizedVoiceTaskOrigin', start);
  const handler = source.slice(start, end);
  const stopIndex = handler.indexOf('p1Owner.stopAgentPlayout(response)');
  const rejectIndex = handler.indexOf('if (!locallyStopped) return;');
  const clearIndex = handler.indexOf('activeVoiceResponseRef.current = null;');
  const remoteIndex = handler.indexOf('await p2Owner.bargeIn(retained.input)');

  assert.equal(start >= 0 && end > start, true);
  assert.equal(stopIndex >= 0, true);
  assert.equal(stopIndex < rejectIndex && rejectIndex < clearIndex && clearIndex < remoteIndex, true);
  assert.match(handler, /cancel_response: true/);
  assert.match(handler, /p2Owner\.hasPendingBargeIn\(\)/);
  assert.match(handler, /pendingBargeInRef\.current === retained/);
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
