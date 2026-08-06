import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

import i18next from 'i18next';
import React from 'react';
import { I18nextProvider } from 'react-i18next';
import { renderToStaticMarkup } from 'react-dom/server';

import {
  LiveVoiceIntegratedRoutePanelView,
  isCurrentProgressOwner,
  progressMatchesOwnedBinding,
} from '../node_modules/.cache/live-voice-integrated-web/LiveVoiceIntegratedRoutePanel.mjs';
import {
  IntegratedWebRouteShell,
  createCurrentIntegratedWebRouteSelection,
} from '../node_modules/.cache/live-voice-integrated-web/features/live-voice/formal/integratedWebRouteShell.js';
import { parseProductTextProgressEvent } from '../node_modules/.cache/live-voice-integrated-web/features/live-voice/formal/productTextProgress.js';

async function renderPanel({ sessionId = 'persisted-session', platform = null, progress = null } = {}) {
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
  assert.equal(html.includes('Composition shell only.'), true);
  assert.equal(html.includes('real microphone capture'), true);
  assert.equal(html.includes('physical audio being heard'), true);
  assert.equal(html.includes('task completion'), true);
  assert.equal(html.includes('Gate pass'), true);
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
