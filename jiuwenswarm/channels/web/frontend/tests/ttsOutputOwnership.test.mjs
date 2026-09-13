import assert from 'node:assert/strict';
import test from 'node:test';

import {
  acquireLiveVoiceTtsOutputOwnership,
  beginServerTtsOutput,
  canCompleteServerTtsOutput,
  isLiveVoiceTtsOutputOwned,
} from '../node_modules/.cache/tts-output-ownership/utils/ttsOutputOwnership.js';

test('Live Voice ownership blocks server TTS until the final owner releases', () => {
  assert.equal(isLiveVoiceTtsOutputOwned(), false);
  assert.notEqual(beginServerTtsOutput(), null);

  const releaseFirst = acquireLiveVoiceTtsOutputOwnership();
  const releaseSecond = acquireLiveVoiceTtsOutputOwnership();
  assert.equal(isLiveVoiceTtsOutputOwned(), true);
  assert.equal(beginServerTtsOutput(), null);

  releaseFirst();
  assert.equal(beginServerTtsOutput(), null);
  releaseFirst();
  assert.equal(beginServerTtsOutput(), null);

  releaseSecond();
  assert.equal(isLiveVoiceTtsOutputOwned(), false);
  assert.notEqual(beginServerTtsOutput(), null);
});

test('acquire and release permanently fence a server response already in flight', () => {
  const requestTicket = beginServerTtsOutput();
  assert.notEqual(requestTicket, null);

  const release = acquireLiveVoiceTtsOutputOwnership();
  assert.equal(canCompleteServerTtsOutput(requestTicket), false);
  release();
  assert.equal(canCompleteServerTtsOutput(requestTicket), false);

  const nextRequestTicket = beginServerTtsOutput();
  assert.notEqual(nextRequestTicket, null);
  assert.equal(canCompleteServerTtsOutput(nextRequestTicket), true);
});
