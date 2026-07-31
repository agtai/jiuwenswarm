import assert from 'node:assert/strict';
import test from 'node:test';

import {
  createSupplementOutputQuarantine,
  shouldBeginSupplementOutputQuarantine,
} from '../node_modules/.cache/supplement-output-quarantine/services/supplementOutputQuarantine.js';

const quarantinedEvents = ['chat.delta', 'chat.final', 'chat.reasoning', 'chat.media'];

test('starts only for the normal Agent supplement path', () => {
  assert.equal(
    shouldBeginSupplementOutputQuarantine({
      intent: 'supplement',
      newInput: '只分析 Gateway',
      mode: 'agent',
    }),
    true
  );
  assert.equal(
    shouldBeginSupplementOutputQuarantine({
      intent: 'cancel',
      newInput: 'ignored',
      mode: 'agent',
    }),
    false
  );
  assert.equal(shouldBeginSupplementOutputQuarantine({ intent: 'supplement', mode: 'agent' }), false);
  assert.equal(
    shouldBeginSupplementOutputQuarantine({
      intent: 'supplement',
      newInput: 'team follow-up',
      mode: 'team',
    }),
    false
  );
  assert.equal(
    shouldBeginSupplementOutputQuarantine({
      intent: 'supplement',
      newInput: 'harness follow-up',
      mode: 'auto_harness',
    }),
    false
  );
  for (const evolutionStatus of ['start', 'progress', 'end']) {
    assert.equal(
      shouldBeginSupplementOutputQuarantine({
        intent: 'supplement',
        newInput: 'queued evolution input',
        mode: 'agent',
        evolutionStatus,
      }),
      false
    );
  }
  assert.equal(
    shouldBeginSupplementOutputQuarantine({
      intent: 'supplement',
      newInput: 'answer after evolution prompt',
      mode: 'agent',
      hasPendingQuestion: true,
    }),
    false
  );
});

test('drops response output only while the session awaits supplement acknowledgement', () => {
  const quarantine = createSupplementOutputQuarantine();

  quarantine.begin('session-1');

  assert.equal(quarantine.isActive('session-1'), true);
  for (const eventName of quarantinedEvents) {
    assert.equal(quarantine.shouldDrop('session-1', eventName), true);
  }
  assert.equal(quarantine.shouldDrop('session-1', 'chat.processing_status'), false);
  assert.equal(quarantine.shouldDrop('session-1', 'chat.interrupt_result'), false);

  quarantine.release('session-1');

  assert.equal(quarantine.isActive('session-1'), false);
  for (const eventName of quarantinedEvents) {
    assert.equal(quarantine.shouldDrop('session-1', eventName), false);
  }
});

test('keeps sessions isolated', () => {
  const quarantine = createSupplementOutputQuarantine();

  quarantine.begin('session-1');

  assert.equal(quarantine.shouldDrop('session-1', 'chat.final'), true);
  assert.equal(quarantine.shouldDrop('session-2', 'chat.final'), false);

  quarantine.release('session-2');
  assert.equal(quarantine.shouldDrop('session-1', 'chat.final'), true);
});

test('requires one acknowledgement for every overlapping supplement', () => {
  const quarantine = createSupplementOutputQuarantine();

  quarantine.begin('session-1');
  quarantine.begin('session-1');

  quarantine.release('session-1');
  assert.equal(quarantine.shouldDrop('session-1', 'chat.delta'), true);

  quarantine.release('session-1');
  assert.equal(quarantine.shouldDrop('session-1', 'chat.delta'), false);
});

test('clear and clearAll release failed or abandoned barriers', () => {
  const quarantine = createSupplementOutputQuarantine();

  quarantine.begin('session-1');
  quarantine.begin('session-2');
  quarantine.clear('session-1');

  assert.equal(quarantine.isActive('session-1'), false);
  assert.equal(quarantine.isActive('session-2'), true);

  quarantine.clearAll();
  assert.equal(quarantine.isActive('session-2'), false);
  assert.equal(quarantine.shouldDrop('session-2', 'chat.final'), false);
});
