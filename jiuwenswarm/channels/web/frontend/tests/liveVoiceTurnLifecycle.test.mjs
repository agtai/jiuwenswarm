import assert from 'node:assert/strict';
import test from 'node:test';

import {
  LIVE_VOICE_STREAMING_FINAL_TIMEOUT_MS,
  resolveLiveVoiceSessionTransition,
  resolveLiveVoiceTurnOriginatingSessionId,
  selectLiveVoicePostSpeechAction,
  selectLiveVoiceStreamingFinalTimeoutAction,
  shouldResumeAfterSilentResponse,
} from '../node_modules/.cache/live-voice-turn-lifecycle/features/live-voice/liveVoiceTurnLifecycle.js';

test('holds a fresh promotion signal until the active session actually changes', () => {
  const signalFirst = resolveLiveVoiceSessionTransition({
    active: true,
    previousSessionId: 'new',
    activeSessionId: 'new',
    promotionSequence: 1,
    promotionTargetSessionId: 'session-1',
    lastHandledPromotionSequence: 0,
  });
  assert.deepEqual(signalFirst, { action: 'none', nextHandledPromotionSequence: 0 });

  const transitionSecond = resolveLiveVoiceSessionTransition({
    active: true,
    previousSessionId: 'new',
    activeSessionId: 'session-1',
    promotionSequence: 1,
    promotionTargetSessionId: 'session-1',
    lastHandledPromotionSequence: signalFirst.nextHandledPromotionSequence,
  });
  assert.deepEqual(transitionSecond, { action: 'preserve', nextHandledPromotionSequence: 1 });
});

test('a mismatched promotion is consumed but cannot preserve navigation', () => {
  const result = resolveLiveVoiceSessionTransition({
    active: true,
    previousSessionId: 'new',
    activeSessionId: 'session-2',
    promotionSequence: 1,
    promotionTargetSessionId: 'session-1',
    lastHandledPromotionSequence: 0,
  });
  assert.deepEqual(result, { action: 'exit', nextHandledPromotionSequence: 1 });
});

test('inactive Live Voice consumes a promotion so it cannot authorize a later visit', () => {
  const result = resolveLiveVoiceSessionTransition({
    active: false,
    previousSessionId: 'new',
    activeSessionId: 'new',
    promotionSequence: 2,
    promotionTargetSessionId: 'session-2',
    lastHandledPromotionSequence: 1,
  });
  assert.deepEqual(result, { action: 'none', nextHandledPromotionSequence: 2 });
});

test('ordinary session navigation exits Live Voice', () => {
  const result = resolveLiveVoiceSessionTransition({
    active: true,
    previousSessionId: 'session-1',
    activeSessionId: 'session-2',
    promotionSequence: 1,
    promotionTargetSessionId: 'session-1',
    lastHandledPromotionSequence: 1,
  });
  assert.deepEqual(result, { action: 'exit', nextHandledPromotionSequence: 1 });
});

test('only a validated new-session promotion may rebind a voice turn session', () => {
  assert.equal(
    resolveLiveVoiceTurnOriginatingSessionId({
      originatingSessionId: 'new',
      previousSessionId: 'new',
      activeSessionId: 'session-1',
      transitionAction: 'preserve',
    }),
    'session-1'
  );
  assert.equal(
    resolveLiveVoiceTurnOriginatingSessionId({
      originatingSessionId: 'session-1',
      previousSessionId: 'session-1',
      activeSessionId: 'session-2',
      transitionAction: 'exit',
    }),
    'session-1'
  );
  assert.equal(
    resolveLiveVoiceTurnOriginatingSessionId({
      originatingSessionId: 'session-0',
      previousSessionId: 'new',
      activeSessionId: 'session-1',
      transitionAction: 'preserve',
    }),
    'session-0'
  );
});

test('a local user echo cannot reopen the microphone before Agent processing starts', () => {
  assert.equal(
    shouldResumeAfterSilentResponse({
      responseObserved: false,
      responseInProgress: false,
      hasUserBoundary: true,
      isThinking: true,
      pendingSpeechCount: 0,
    }),
    false
  );
});

test('a completed observed response with no playable speech can resume capture', () => {
  assert.equal(
    shouldResumeAfterSilentResponse({
      responseObserved: true,
      responseInProgress: false,
      hasUserBoundary: true,
      isThinking: true,
      pendingSpeechCount: 0,
    }),
    true
  );
  assert.equal(
    shouldResumeAfterSilentResponse({
      responseObserved: true,
      responseInProgress: true,
      hasUserBoundary: true,
      isThinking: true,
      pendingSpeechCount: 0,
    }),
    false
  );
});

function postSpeechInput(overrides = {}) {
  return {
    streamingEnabled: true,
    responseInProgress: false,
    responseObserved: true,
    currentTurnResponseEpoch: 3,
    plannerResponseEpoch: 3,
    plannerMessageId: 'assistant-1',
    plannerMode: 'streaming',
    status: 'idle',
    pendingSpeechCount: 0,
    activeSpeechKey: null,
    resumeRequested: true,
    ...overrides,
  };
}

test('processing false before chat.final keeps the microphone closed', () => {
  assert.equal(selectLiveVoicePostSpeechAction(postSpeechInput()), 'mark-thinking');
});

test('an observed response with no planner message still keeps the microphone closed', () => {
  assert.equal(
    selectLiveVoicePostSpeechAction(
      postSpeechInput({
        plannerResponseEpoch: null,
        plannerMessageId: null,
      })
    ),
    'mark-thinking'
  );
});

test('enqueue before onStart is not mistaken for an idle speech queue', () => {
  assert.equal(
    selectLiveVoicePostSpeechAction(
      postSpeechInput({
        plannerMode: 'finalized',
        pendingSpeechCount: 1,
        activeSpeechKey: 'assistant-1:final-tail:1',
      })
    ),
    'none'
  );
});

test('a finalized and drained plan can resume capture exactly once', () => {
  assert.equal(selectLiveVoicePostSpeechAction(postSpeechInput({ plannerMode: 'finalized' })), 'begin-capture');
  assert.equal(selectLiveVoicePostSpeechAction(postSpeechInput({ plannerMode: 'finalized', resumeRequested: false })), 'none');
});

function finalTimeoutInput(overrides = {}) {
  return {
    streamingEnabled: true,
    liveVoiceActive: true,
    responseInProgress: false,
    responseObserved: true,
    originatingSessionId: 'session-1',
    activeSessionId: 'session-1',
    currentTurnResponseEpoch: 3,
    plannerResponseEpoch: 3,
    plannerMessageId: 'assistant-1',
    plannerMode: 'streaming',
    status: 'thinking',
    pendingSpeechCount: 0,
    activeSpeechKey: null,
    timeoutExpired: false,
    ...overrides,
  };
}

test('missing authoritative final starts one conservative grace period only after playback drains', () => {
  assert.equal(LIVE_VOICE_STREAMING_FINAL_TIMEOUT_MS, 10_000);
  assert.equal(selectLiveVoiceStreamingFinalTimeoutAction(finalTimeoutInput()), 'wait');
  assert.equal(
    selectLiveVoiceStreamingFinalTimeoutAction(
      finalTimeoutInput({
        status: 'speaking',
        pendingSpeechCount: 1,
        activeSpeechKey: 'assistant-1:stream:0',
      })
    ),
    'none'
  );
});

test('an expired grace period recovers without treating provisional content as final', () => {
  assert.equal(selectLiveVoiceStreamingFinalTimeoutAction(finalTimeoutInput({ timeoutExpired: true })), 'recover');
});

test('processing observed without a planner message still receives bounded final grace', () => {
  const noPlannerMessage = {
    plannerResponseEpoch: null,
    plannerMessageId: null,
  };
  assert.equal(selectLiveVoiceStreamingFinalTimeoutAction(finalTimeoutInput(noPlannerMessage)), 'wait');
  assert.equal(selectLiveVoiceStreamingFinalTimeoutAction(finalTimeoutInput({ ...noPlannerMessage, timeoutExpired: true })), 'recover');
  assert.equal(
    selectLiveVoiceStreamingFinalTimeoutAction(finalTimeoutInput({ ...noPlannerMessage, responseObserved: false, timeoutExpired: true })),
    'none'
  );
});

test('final timeout is cancelled by an authoritative final, mismatch, or resumed processing', () => {
  assert.equal(selectLiveVoiceStreamingFinalTimeoutAction(finalTimeoutInput({ plannerMode: 'finalized', timeoutExpired: true })), 'none');
  assert.equal(selectLiveVoiceStreamingFinalTimeoutAction(finalTimeoutInput({ plannerMode: 'mismatch', timeoutExpired: true })), 'none');
  assert.equal(selectLiveVoiceStreamingFinalTimeoutAction(finalTimeoutInput({ responseInProgress: true, timeoutExpired: true })), 'none');
});

test('final timeout cannot cross feature, session, response epoch, or UI lifecycle boundaries', () => {
  assert.equal(selectLiveVoiceStreamingFinalTimeoutAction(finalTimeoutInput({ streamingEnabled: false, timeoutExpired: true })), 'none');
  assert.equal(selectLiveVoiceStreamingFinalTimeoutAction(finalTimeoutInput({ liveVoiceActive: false, timeoutExpired: true })), 'none');
  assert.equal(selectLiveVoiceStreamingFinalTimeoutAction(finalTimeoutInput({ activeSessionId: 'session-2', timeoutExpired: true })), 'none');
  assert.equal(selectLiveVoiceStreamingFinalTimeoutAction(finalTimeoutInput({ originatingSessionId: null, activeSessionId: null, timeoutExpired: true })), 'none');
  assert.equal(selectLiveVoiceStreamingFinalTimeoutAction(finalTimeoutInput({ plannerResponseEpoch: 2, timeoutExpired: true })), 'none');
  assert.equal(
    selectLiveVoiceStreamingFinalTimeoutAction(finalTimeoutInput({ plannerResponseEpoch: 2, plannerMessageId: null, timeoutExpired: true })),
    'none'
  );
  assert.equal(selectLiveVoiceStreamingFinalTimeoutAction(finalTimeoutInput({ status: 'error', timeoutExpired: true })), 'none');
});
