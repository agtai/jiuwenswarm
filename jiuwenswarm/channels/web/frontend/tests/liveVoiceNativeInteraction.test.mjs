import assert from 'node:assert/strict';
import test from 'node:test';

import {
  parseProductP1NativeInteractionActivation,
} from '../node_modules/.cache/live-voice-integrated-web/features/live-voice/formal/productP1VoiceRoute.js';
import {
  classifyProductP2Notification,
  shouldBlockProductP2NotificationPoll,
} from '../node_modules/.cache/live-voice-integrated-web/LiveVoiceIntegratedRoutePanel.mjs';

function nativeNotification(overrides = {}) {
  const response = {
    interaction_id: 'interaction-native-1',
    response_id: 'response-native-1',
    response_generation: 1,
  };
  return {
    status: 'notification',
    kind: 'native.audio',
    request_id: 'notification-native-1',
    round_id: null,
    response,
    agent_event: null,
    source_event: null,
    progress_event: null,
    presentation_unit: {
      response,
      surface: 'audio',
      unit_id: 'native-audio-unit-0',
      seq: 0,
      source_start_utf8: 0,
      source_end_utf8: 480,
      content_ref: `sha256:${'a'.repeat(64)}`,
    },
    audio: {
      delivery: 'dedicated_media_downlink',
      media_ticket: 'N'.repeat(43),
    },
    error_reason: null,
    publish_seq: null,
    session_id: 'session-native-1',
    correlation_id: 'correlation-native-1',
    interaction_id: response.interaction_id,
    activation_id: 'activation-native-1',
    activation_generation: 1,
    ...overrides,
  };
}

function nativeUserTranscriptNotification(overrides = {}) {
  const binding = {
    scope: {
      subject_id: 'subject-native-1',
      project_id: null,
      session_id: 'session-native-1',
      assurance: 'authenticated',
    },
    interaction_id: 'interaction-native-1',
    activation_id: 'activation-native-1',
    activation_generation: 1,
    correlation_id: 'correlation-native-1',
    turn_id: 'turn-native-1',
    commit_id: 'commit-native-1',
    provider_session_id: 'provider-session-native-1',
    provider_item_id: 'provider-item-native-1',
    provider_event_id: 'provider-event-native-1',
  };
  return {
    status: 'notification',
    kind: 'native.user_transcript',
    request_id: 'notification-native-transcript-1',
    round_id: null,
    response: null,
    agent_event: {
      event_type: 'chat.final',
      message: {
        id: 'live-voice:commit-native-1:native-user',
        role: 'user',
        content: '介绍你自己',
        timestamp: 1_788_134_400.125,
      },
      binding,
    },
    source_event: null,
    progress_event: null,
    presentation_unit: null,
    audio: null,
    error_reason: null,
    publish_seq: null,
    session_id: 'session-native-1',
    correlation_id: 'correlation-native-1',
    interaction_id: 'interaction-native-1',
    activation_id: 'activation-native-1',
    activation_generation: 1,
    ...overrides,
  };
}

test('Native activation is a closed server-selected Engine descriptor', () => {
  assert.deepEqual(
    parseProductP1NativeInteractionActivation({
      contract_version: 'live-voice.native-interaction.v1',
      engine: 'openai-realtime-native',
      model: 'gpt-realtime',
    }),
    {
      contract_version: 'live-voice.native-interaction.v1',
      engine: 'openai-realtime-native',
      model: 'gpt-realtime',
    },
  );
  assert.throws(
    () => parseProductP1NativeInteractionActivation({
      contract_version: 'live-voice.native-interaction.v1',
      engine: 'cascade',
      model: 'gpt-realtime',
    }),
    /activation is invalid/,
  );
});

test('Native audio is isolated from text presentation and malformed carriers fail closed', () => {
  const notification = nativeNotification();
  const disposition = classifyProductP2Notification(notification);
  assert.equal(disposition.kind, 'native_audio');
  assert.equal(disposition.response_id, 'response-native-1');
  assert.equal('ack' in disposition, false);
  assert.equal('text' in disposition, false);

  assert.deepEqual(
    classifyProductP2Notification(nativeNotification({ forged_text: 'not authoritative' })),
    {
      kind: 'failed',
      reason: 'PRODUCT_NATIVE_AUDIO_NOTIFICATION_INVALID',
      response: {
        interaction_id: 'interaction-native-1',
        response_id: 'response-native-1',
        response_generation: 1,
      },
    },
  );
});

test('Native user transcript is an exact current-binding chat projection', () => {
  assert.deepEqual(
    classifyProductP2Notification(nativeUserTranscriptNotification()),
    {
      kind: 'native_user_transcript',
      session_id: 'session-native-1',
      correlation_id: 'correlation-native-1',
      interaction_id: 'interaction-native-1',
      activation_id: 'activation-native-1',
      activation_generation: 1,
      message: {
        id: 'live-voice:commit-native-1:native-user',
        role: 'user',
        content: '介绍你自己',
        timestamp: '2026-08-31T00:00:00.125Z',
      },
      following_assistant: [],
    },
  );

  const base = nativeUserTranscriptNotification();
  assert.deepEqual(
    classifyProductP2Notification({
      ...base,
      agent_event: {
        ...base.agent_event,
        following_assistant: [
          {
            message: {
              id: 'live-voice:interaction-native-1:response-native-1:1:native-audio:digest',
              role: 'assistant',
              content: '你好，我是 JiuwenSwarm。',
              timestamp: 1_788_134_401.5,
            },
            binding: {
              turn_id: 'turn-native-1',
              response: {
                interaction_id: 'interaction-native-1',
                response_id: 'response-native-1',
                response_generation: 1,
              },
              surface: 'native_audio',
              presented_at: '2026-08-31T00:00:01.500Z',
            },
          },
        ],
      },
    }),
    {
      kind: 'native_user_transcript',
      session_id: 'session-native-1',
      correlation_id: 'correlation-native-1',
      interaction_id: 'interaction-native-1',
      activation_id: 'activation-native-1',
      activation_generation: 1,
      message: {
        id: 'live-voice:commit-native-1:native-user',
        role: 'user',
        content: '介绍你自己',
        timestamp: '2026-08-31T00:00:00.125Z',
      },
      following_assistant: [
        {
          id: 'live-voice:interaction-native-1:response-native-1:1:native-audio:digest',
          role: 'assistant',
          content: '你好，我是 JiuwenSwarm。',
          timestamp: '2026-08-31T00:00:01.500Z',
        },
      ],
    },
  );
  assert.deepEqual(
    classifyProductP2Notification({ ...base, forged_text: 'not authoritative' }),
    { kind: 'failed', reason: 'PRODUCT_NATIVE_USER_TRANSCRIPT_NOTIFICATION_INVALID' },
  );
  assert.deepEqual(
    classifyProductP2Notification({
      ...base,
      agent_event: {
        ...base.agent_event,
        binding: { ...base.agent_event.binding, activation_generation: 2 },
      },
    }),
    { kind: 'failed', reason: 'PRODUCT_NATIVE_USER_TRANSCRIPT_NOTIFICATION_INVALID' },
  );
  assert.deepEqual(
    classifyProductP2Notification({
      ...base,
      agent_event: {
        ...base.agent_event,
        message: { ...base.agent_event.message, timestamp: Number.POSITIVE_INFINITY },
      },
    }),
    { kind: 'failed', reason: 'PRODUCT_NATIVE_USER_TRANSCRIPT_NOTIFICATION_INVALID' },
  );
});

test('Native continuous capture keeps P2 audio polling live without weakening Cascade', () => {
  assert.equal(shouldBlockProductP2NotificationPoll('capturing', 'cascade'), true);
  assert.equal(
    shouldBlockProductP2NotificationPoll('capturing', 'openai-realtime-native'),
    false,
  );
  assert.equal(
    shouldBlockProductP2NotificationPoll('playing', 'openai-realtime-native'),
    true,
  );
});
