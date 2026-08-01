import assert from 'node:assert/strict';
import test from 'node:test';

import {
  resolveLiveVoiceSessionTransition,
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
