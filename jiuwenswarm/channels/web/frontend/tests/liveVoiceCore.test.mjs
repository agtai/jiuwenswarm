import assert from 'node:assert/strict';
import test from 'node:test';

import { createLiveVoiceCore } from '../node_modules/.cache/live-voice-core/features/live-voice/liveVoiceCore.js';

class FakeSpeechPlayer {
  plays = [];
  stopCount = 0;

  play(text, callbacks) {
    this.plays.push({ text, callbacks });
  }

  stop() {
    this.stopCount += 1;
  }
}

function createFixture() {
  const player = new FakeSpeechPlayer();
  const core = createLiveVoiceCore({ player });
  return { core, player };
}

function commitTurn(core, transcript = '检查当前仓库') {
  core.beginListening();
  const result = core.commitFinalTranscript(transcript);
  assert.equal(result.accepted, true);
  return result;
}

test('partial transcript only updates display state and one cycle commits once', () => {
  const { core, player } = createFixture();
  const captureId = core.beginListening();

  assert.equal(core.setInterimTranscript('检查当前'), true);
  assert.deepEqual(core.getSnapshot(), {
    status: 'listening',
    captureId,
    responseEpoch: 0,
    interimTranscript: '检查当前',
    finalTranscript: '',
    pendingSpeechCount: 0,
    activeSpeechKey: null,
    error: null,
  });
  assert.equal(player.plays.length, 0);

  const first = core.commitFinalTranscript('  检查当前\n仓库  ');
  assert.deepEqual(first, {
    accepted: true,
    captureId,
    responseEpoch: 1,
    transcript: '检查当前 仓库',
  });
  assert.equal(core.getSnapshot().status, 'thinking');
  assert.equal(core.getSnapshot().interimTranscript, '');

  assert.deepEqual(core.commitFinalTranscript('检查当前仓库'), {
    accepted: false,
    reason: 'already-committed',
  });
  assert.equal(core.getSnapshot().responseEpoch, 1);
});

test('empty final remains retryable and the same text is valid in a new cycle', () => {
  const { core } = createFixture();
  core.beginListening();

  assert.deepEqual(core.commitFinalTranscript('  '), {
    accepted: false,
    reason: 'empty',
  });
  const first = core.commitFinalTranscript('继续');
  assert.equal(first.accepted, true);

  const secondCaptureId = core.beginListening();
  const second = core.commitFinalTranscript('继续');
  assert.equal(second.accepted, true);
  assert.equal(second.captureId, secondCaptureId);
  assert.notEqual(second.captureId, first.captureId);
  assert.ok(second.responseEpoch > first.responseEpoch);
});

test('speech is played in FIFO order and duplicate keys stay suppressed for the epoch', () => {
  const { core, player } = createFixture();
  const turn = commitTurn(core);

  assert.deepEqual(core.enqueueSpeech('第一句。', turn.responseEpoch, 'message-1:0'), {
    accepted: true,
    key: 'message-1:0',
  });
  assert.deepEqual(core.enqueueSpeech('第二句。', turn.responseEpoch, 'message-1:1'), {
    accepted: true,
    key: 'message-1:1',
  });
  assert.equal(player.plays.length, 1);
  assert.equal(player.plays[0].text, '第一句。');
  assert.equal(core.getSnapshot().pendingSpeechCount, 2);

  player.plays[0].callbacks.onStart();
  assert.equal(core.getSnapshot().status, 'speaking');
  player.plays[0].callbacks.onEnd();

  assert.equal(player.plays.length, 2);
  assert.equal(player.plays[1].text, '第二句。');
  assert.equal(core.getSnapshot().activeSpeechKey, 'message-1:1');
  player.plays[1].callbacks.onStart();
  player.plays[1].callbacks.onEnd();

  assert.equal(core.getSnapshot().status, 'idle');
  assert.equal(core.getSnapshot().pendingSpeechCount, 0);
  assert.deepEqual(core.enqueueSpeech('第一句。', turn.responseEpoch, 'message-1:0'), {
    accepted: false,
    reason: 'duplicate',
  });
});

test('interrupt invalidates queued speech and ignores every late player callback', () => {
  const { core, player } = createFixture();
  const turn = commitTurn(core);
  core.enqueueSpeech('不会恢复的旧回答', turn.responseEpoch, 'old-response');
  const oldCallbacks = player.plays[0].callbacks;
  oldCallbacks.onStart();
  assert.equal(core.getSnapshot().status, 'speaking');

  const nextEpoch = core.interrupt();
  const interrupted = core.getSnapshot();
  assert.ok(nextEpoch > turn.responseEpoch);
  assert.equal(interrupted.status, 'interrupted');
  assert.equal(interrupted.pendingSpeechCount, 0);
  assert.equal(player.stopCount, 2);
  assert.deepEqual(core.enqueueSpeech('迟到旧回答', turn.responseEpoch), {
    accepted: false,
    reason: 'stale-epoch',
  });

  oldCallbacks.onStart();
  oldCallbacks.onEnd();
  oldCallbacks.onError(new Error('late cancellation error'));
  assert.deepEqual(core.getSnapshot(), interrupted);
});

test('exit invalidates current epoch and stale callbacks cannot leave idle state', () => {
  const { core, player } = createFixture();
  const turn = commitTurn(core);
  core.enqueueSpeech('退出前回答', turn.responseEpoch, 'before-exit');
  const oldCallbacks = player.plays[0].callbacks;
  oldCallbacks.onStart();

  core.exit();
  const exited = core.getSnapshot();
  assert.equal(exited.status, 'idle');
  assert.equal(exited.pendingSpeechCount, 0);
  assert.ok(exited.responseEpoch > turn.responseEpoch);
  assert.equal(core.isCurrentResponseEpoch(turn.responseEpoch), false);

  oldCallbacks.onEnd();
  oldCallbacks.onError(new Error('late'));
  assert.deepEqual(core.getSnapshot(), exited);
});

test('playback error enters visible error state and can recover for a new turn', () => {
  const { core, player } = createFixture();
  const turn = commitTurn(core);
  core.enqueueSpeech('会失败的回答', turn.responseEpoch, 'failure');
  player.plays[0].callbacks.onStart();
  player.plays[0].callbacks.onError(new Error('voice unavailable'));

  assert.deepEqual(core.getSnapshot().error, {
    code: 'speech-playback',
    message: 'voice unavailable',
  });
  assert.equal(core.getSnapshot().status, 'error');
  assert.equal(core.getSnapshot().pendingSpeechCount, 0);
  assert.deepEqual(core.enqueueSpeech('错误状态不继续播', turn.responseEpoch), {
    accepted: false,
    reason: 'error',
  });

  core.clearError();
  assert.equal(core.getSnapshot().status, 'idle');
  assert.equal(core.getSnapshot().error, null);

  const recovered = commitTurn(core, '恢复后的请求');
  assert.ok(recovered.responseEpoch > turn.responseEpoch);
});

test('recognition failure stops speech, invalidates the epoch and clearError restores idle', () => {
  const { core } = createFixture();
  const turn = commitTurn(core);

  core.fail('not-allowed', '麦克风权限被拒绝');
  assert.deepEqual(core.getSnapshot().error, {
    code: 'not-allowed',
    message: '麦克风权限被拒绝',
  });
  assert.equal(core.getSnapshot().status, 'error');
  assert.equal(core.isCurrentResponseEpoch(turn.responseEpoch), false);

  core.clearError();
  assert.equal(core.getSnapshot().status, 'idle');
  assert.equal(core.getSnapshot().error, null);
});

test('stale markThinking and speech are rejected after a newer turn starts', () => {
  const { core } = createFixture();
  const first = commitTurn(core, '第一个请求');
  core.beginListening();
  const second = core.commitFinalTranscript('第二个请求');
  assert.equal(second.accepted, true);

  assert.equal(core.markThinking(first.responseEpoch), false);
  assert.deepEqual(core.enqueueSpeech('第一个迟到回答', first.responseEpoch), {
    accepted: false,
    reason: 'stale-epoch',
  });
  assert.equal(core.markThinking(second.responseEpoch), true);
  assert.equal(core.getSnapshot().status, 'thinking');
});

test('a new capture invalidates the prior epoch after speech drains to idle', () => {
  const { core, player } = createFixture();
  const first = commitTurn(core, 'first request');
  core.enqueueSpeech('finished response', first.responseEpoch, 'finished-response');
  player.plays[0].callbacks.onStart();
  player.plays[0].callbacks.onEnd();
  assert.equal(core.getSnapshot().status, 'idle');

  core.beginListening();

  assert.equal(core.getSnapshot().status, 'listening');
  assert.equal(core.isCurrentResponseEpoch(first.responseEpoch), false);
  assert.deepEqual(core.enqueueSpeech('late response', first.responseEpoch, 'late-response'), {
    accepted: false,
    reason: 'stale-epoch',
  });
});
