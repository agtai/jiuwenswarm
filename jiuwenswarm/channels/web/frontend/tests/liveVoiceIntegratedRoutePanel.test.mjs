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
  PRODUCT_P2_SUBMIT_METHOD,
} from '../node_modules/.cache/live-voice-integrated-web/features/live-voice/formal/productWebActivation.js';
import {
  IntegratedWebRouteShell,
  createCurrentIntegratedWebRouteSelection,
} from '../node_modules/.cache/live-voice-integrated-web/features/live-voice/formal/integratedWebRouteShell.js';
import { parseProductTextProgressEvent } from '../node_modules/.cache/live-voice-integrated-web/features/live-voice/formal/productTextProgress.js';

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

test('recognized P1 text can enter P2 while every retained voice operation blocks it', async () => {
  for (const status of ['starting', 'capturing', 'recognizing', 'playing', 'cleanup_pending']) {
    assert.equal(productTextBlockedByP1Status(status), true, status);
  }
  assert.equal(productTextBlockedByP1Status('recognized'), false);
  const source = await readFile(new URL('../src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx', import.meta.url), 'utf8');
  assert.match(source, /const recognition = await owner\.stopAndRecognize\(\)/);
  assert.match(source, /voice_commit_receipt: recognition\.voice_commit_receipt/);
  assert.match(source, /\? 'voice'\s*: 'structured'/);
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
