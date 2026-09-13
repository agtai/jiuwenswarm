import assert from 'node:assert/strict';
import test from 'node:test';

import {
  combinedSpeechRecognitionTranscript,
  isSuccessfulSpeechTailNoSpeech,
  mergeSpeechRecognitionTranscript,
  shouldContinueSpeechCaptureAfterNaturalEnd,
  shouldRetrySpeechCaptureDuringInitialSilence,
} from '../node_modules/.cache/speech-recognition-lifecycle/hooks/speechRecognitionLifecycle.js';

const naturalEnd = (overrides = {}) => ({
  useContinuous: true,
  restartRequested: true,
  receivedAnyResult: true,
  terminalRecognitionError: false,
  manualStop: false,
  autoStop: false,
  ...overrides,
});

test('continues one logical capture after Chromium ends following a result', () => {
  assert.equal(shouldContinueSpeechCaptureAfterNaturalEnd(naturalEnd()), true);
});

test('does not loop a capture that has not received speech', () => {
  assert.equal(shouldContinueSpeechCaptureAfterNaturalEnd(naturalEnd({ receivedAnyResult: false })), false);
});

test('initial no-speech retry cannot revive a manual or automatic stop', () => {
  const initialRetry = (overrides = {}) => ({
    retryRequested: true,
    receivedAnyResult: false,
    beforeInitialDeadline: true,
    terminalRecognitionError: false,
    manualStop: false,
    autoStop: false,
    ...overrides,
  });

  assert.equal(shouldRetrySpeechCaptureDuringInitialSilence(initialRetry()), true);
  assert.equal(shouldRetrySpeechCaptureDuringInitialSilence(initialRetry({ manualStop: true })), false);
  assert.equal(shouldRetrySpeechCaptureDuringInitialSilence(initialRetry({ autoStop: true })), false);
});

test('manual stop, silence auto-stop, and recognition errors remain terminal', () => {
  assert.equal(shouldContinueSpeechCaptureAfterNaturalEnd(naturalEnd({ manualStop: true })), false);
  assert.equal(shouldContinueSpeechCaptureAfterNaturalEnd(naturalEnd({ autoStop: true })), false);
  assert.equal(shouldContinueSpeechCaptureAfterNaturalEnd(naturalEnd({ terminalRecognitionError: true })), false);
});

test('caller can disable browser restart without changing normal hook consumers', () => {
  assert.equal(shouldContinueSpeechCaptureAfterNaturalEnd(naturalEnd({ restartRequested: false })), false);
  assert.equal(shouldContinueSpeechCaptureAfterNaturalEnd(naturalEnd({ useContinuous: false })), false);
});

test('no-speech after a prior result closes tail grace instead of erasing it', () => {
  assert.equal(isSuccessfulSpeechTailNoSpeech('no-speech', true), true);
  assert.equal(isSuccessfulSpeechTailNoSpeech('no-speech', false), false);
  assert.equal(isSuccessfulSpeechTailNoSpeech('network', true), false);
});

test('merges consecutive final and interim chunks across browser restarts', () => {
  let state = { finalTranscript: '', interimTranscript: '' };
  state = mergeSpeechRecognitionTranscript(state, '查', true);
  state = mergeSpeechRecognitionTranscript(state, '看 Git 状态', false);
  assert.equal(combinedSpeechRecognitionTranscript(state), '查看 Git 状态');

  state = mergeSpeechRecognitionTranscript(state, '看 Git 状态', true);
  assert.deepEqual(state, {
    finalTranscript: '查看 Git 状态',
    interimTranscript: '',
  });
  assert.equal(combinedSpeechRecognitionTranscript(state), '查看 Git 状态');
});
