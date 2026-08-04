import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

import {
  ConversationReplicaViolation,
  ConversationRuntimeReplica,
} from '../node_modules/.cache/live-voice-conversation-runtime/features/live-voice/formal/conversationRuntimeReplica.js';

const fixture = JSON.parse(await readFile(new URL('../../../../../tests/fixtures/live_voice_a_packages/conversation_runtime.json', import.meta.url), 'utf8'));

test('replica applies the shared canonical fixture and matches final state', () => {
  const replica = new ConversationRuntimeReplica(fixture.scope);
  for (const event of fixture.events) assert.equal(replica.apply(event), true);
  const snapshot = replica.snapshot();
  assert.equal(snapshot.interactions[0].state, fixture.expected.interaction_state);
  assert.equal(snapshot.turns[0].state, fixture.expected.turn_state);
  assert.equal(snapshot.responses[0].state, fixture.expected.response_state);
  assert.equal(snapshot.responses[0].outcome, fixture.expected.response_outcome);
  assert.equal(snapshot.last_seq, fixture.expected.last_seq);
  assert.deepEqual(replica.selectOutputEffects('interaction-1', 'response-1', 0), []);
});

test('only current unfenced response selects UI history and audio effects', () => {
  const replica = new ConversationRuntimeReplica(fixture.scope);
  for (const event of fixture.events.slice(0, 5)) replica.apply(event);
  assert.deepEqual(
    replica.selectOutputEffects('interaction-1', 'response-1', 0).map(item => item.effect_type),
    ['ui.render', 'history.append', 'audio.enqueue']
  );
  assert.deepEqual(replica.selectOutputEffects('interaction-1', 'response-1', 1), []);
  assert.deepEqual(replica.selectOutputEffects('other', 'response-1', 0), []);
});

test('gap and wrong scope reject without advancing state', () => {
  const replica = new ConversationRuntimeReplica(fixture.scope);
  assert.throws(
    () => replica.apply({ ...fixture.events[0], seq: 2 }),
    error => error instanceof ConversationReplicaViolation && error.reason === 'NON_CONTIGUOUS_EVENT_SEQUENCE'
  );
  assert.equal(replica.snapshot().last_seq, 0);
  assert.throws(
    () => replica.apply({ ...fixture.events[0], scope: { ...fixture.scope, subject_id: 'other' } }),
    error => error instanceof ConversationReplicaViolation && error.reason === 'EVENT_SCOPE_MISMATCH'
  );
  assert.equal(replica.snapshot().last_seq, 0);
});

test('illegal lifecycle event rejects before state mutation', () => {
  const replica = new ConversationRuntimeReplica(fixture.scope);
  for (const event of fixture.events.slice(0, 4)) replica.apply(event);
  const before = replica.snapshot();
  assert.throws(
    () => replica.apply({ ...fixture.events[5], seq: 5 }),
    error => error instanceof ConversationReplicaViolation && error.reason === 'INVALID_CANONICAL_EVENT'
  );
  assert.deepEqual(replica.snapshot(), before);
});

test('cancel acknowledgement fences output but is not terminal', () => {
  const replica = new ConversationRuntimeReplica(fixture.scope);
  for (const event of fixture.events.slice(0, 5)) replica.apply(event);
  const generating = replica.snapshot().responses[0];
  replica.apply({
    ...fixture.events[4],
    seq: 6,
    event_type: 'response.cancel_requested',
    state: 'generating',
    cancel_state: 'requested',
  });
  replica.apply({
    ...fixture.events[4],
    seq: 7,
    event_type: 'response.cancel_acknowledged',
    state: 'generating',
    cancel_state: 'acknowledged',
  });
  const response = replica.snapshot().responses[0];
  assert.equal(generating.state, 'generating');
  assert.equal(response.state, 'generating');
  assert.equal(response.cancel_state, 'acknowledged');
  assert.deepEqual(replica.selectOutputEffects('interaction-1', 'response-1', 0), []);
});

test('disabled replica accepts no events and produces no effects', () => {
  const replica = new ConversationRuntimeReplica(fixture.scope, { enabled: false });
  assert.equal(replica.apply(fixture.events[0]), false);
  assert.equal(replica.snapshot().last_seq, 0);
  assert.deepEqual(replica.snapshot().interactions, []);
  assert.deepEqual(replica.selectOutputEffects('interaction-1', 'response-1', 0), []);
});

test('response generations must increase and response ids cannot be reused', () => {
  const replica = new ConversationRuntimeReplica(fixture.scope);
  for (const event of fixture.events.slice(0, 4)) replica.apply(event);
  const before = replica.snapshot();
  assert.throws(
    () =>
      replica.apply({
        ...fixture.events[3],
        seq: 5,
        response_id: 'response-2',
        response_generation: 0,
      }),
    error => error instanceof ConversationReplicaViolation && error.reason === 'INVALID_CANONICAL_EVENT'
  );
  assert.deepEqual(replica.snapshot(), before);
});

test('closing an interaction fences current output without selecting task effects', () => {
  const replica = new ConversationRuntimeReplica(fixture.scope);
  for (const event of fixture.events.slice(0, 5)) replica.apply(event);
  replica.apply({ ...fixture.events[7], seq: 6 });
  assert.deepEqual(replica.selectOutputEffects('interaction-1', 'response-1', 0), []);
  assert.equal(replica.snapshot().responses[0].state, 'generating');
});
