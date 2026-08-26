import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

import {
  ConversationReplicaViolation,
  ConversationRuntimeReplica,
} from '../node_modules/.cache/live-voice-conversation-runtime/features/live-voice/formal/conversationRuntimeReplica.js';

const fixture = JSON.parse(await readFile(new URL('../../../../../tests/fixtures/live_voice_a_packages/conversation_runtime.json', import.meta.url), 'utf8'));

function canonicalEvent(seq, eventType, interactionId, overrides = {}) {
  return {
    seq,
    event_type: eventType,
    scope: fixture.scope,
    interaction_id: interactionId,
    turn_id: null,
    response_id: null,
    response_generation: null,
    state: null,
    cancel_state: null,
    outcome: null,
    ...overrides,
  };
}

function rebuildFromAuthoritativeSnapshot(replica, snapshot) {
  return replica.rebuildFromAuthoritativeSnapshot?.(snapshot) ?? false;
}

function applyClosedInteractions(replica, count) {
  let seq = 0;
  for (let index = 0; index < count; index += 1) {
    const interactionId = `replica-closed-interaction-${index}`;
    replica.apply(canonicalEvent(++seq, 'interaction.opened', interactionId, { state: 'open' }));
    replica.apply(canonicalEvent(++seq, 'interaction.closed', interactionId, { state: 'closed' }));
  }
  return seq;
}

function applyTerminalResponses(replica, count) {
  let seq = 0;
  const interactionId = 'replica-long-interaction';
  replica.apply(canonicalEvent(++seq, 'interaction.opened', interactionId, { state: 'open' }));
  for (let generation = 0; generation < count; generation += 1) {
    const turnId = `replica-turn-${generation}`;
    const responseId = `replica-response-${generation}`;
    replica.apply(canonicalEvent(++seq, 'turn.started', interactionId, { turn_id: turnId, state: 'capturing' }));
    replica.apply(canonicalEvent(++seq, 'turn.committed', interactionId, { turn_id: turnId, state: 'committed' }));
    replica.apply(
      canonicalEvent(++seq, 'response.accepted', interactionId, {
        turn_id: turnId,
        response_id: responseId,
        response_generation: generation,
        state: 'accepted',
        cancel_state: 'none',
      })
    );
    replica.apply(
      canonicalEvent(++seq, 'response.terminal', interactionId, {
        turn_id: turnId,
        response_id: responseId,
        response_generation: generation,
        state: 'terminal',
        cancel_state: 'none',
        outcome: 'completed',
      })
    );
  }
  return seq;
}

test('replica applies the shared canonical fixture and matches final state', () => {
  const replica = new ConversationRuntimeReplica(fixture.scope);
  for (const event of fixture.events) assert.equal(replica.apply(event), true);
  const snapshot = replica.snapshot();
  assert.deepEqual(snapshot.interactions, []);
  assert.deepEqual(snapshot.turns, []);
  assert.deepEqual(snapshot.responses, []);
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

test('late authoritative cancel acknowledgement reconciles an unknown result', () => {
  const replica = new ConversationRuntimeReplica(fixture.scope);
  for (const event of fixture.events.slice(0, 5)) replica.apply(event);
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
    event_type: 'response.cancel_result_unknown',
    state: 'generating',
    cancel_state: 'result_unknown',
  });
  replica.apply({
    ...fixture.events[4],
    seq: 8,
    event_type: 'response.cancel_acknowledged',
    state: 'generating',
    cancel_state: 'acknowledged',
  });

  const response = replica.snapshot().responses[0];
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
  assert.deepEqual(replica.snapshot().responses, []);
});

test('closed interaction lifecycle is compacted and conservative collision requires authoritative rebuild', () => {
  const replica = new ConversationRuntimeReplica(fixture.scope);
  const lastSeq = applyClosedInteractions(replica, 1_800);
  const compact = replica.snapshot();
  assert.equal(lastSeq, 3_600);
  assert.deepEqual(compact.interactions, []);
  assert.deepEqual(compact.turns, []);
  assert.deepEqual(compact.responses, []);

  const collisionId = 'unused-replica-interaction-40584';
  assert.throws(
    () => replica.apply(canonicalEvent(lastSeq + 1, 'interaction.opened', collisionId, { state: 'open' })),
    error => error instanceof ConversationReplicaViolation && error.reason === 'REPLICA_REBUILD_REQUIRED'
  );
  const blocked = replica.snapshot();
  assert.equal(blocked.last_seq, lastSeq);
  assert.equal(blocked.rebuild_required, true);
  assert.throws(
    () => replica.apply(canonicalEvent(lastSeq + 1, 'interaction.opened', 'replica-recovery-interaction', { state: 'open' })),
    error => error instanceof ConversationReplicaViolation && error.reason === 'REPLICA_REBUILD_REQUIRED'
  );

  const authoritative = Object.freeze({
    ...blocked,
    interactions: Object.freeze([Object.freeze({ interaction_id: collisionId, state: 'open' })]),
    last_seq: lastSeq + 1,
    rebuild_required: false,
  });
  assert.equal(rebuildFromAuthoritativeSnapshot(replica, authoritative), true);
  assert.equal(replica.snapshot().rebuild_required, false);
  assert.equal(replica.snapshot().interactions[0].interaction_id, collisionId);
  assert.equal(replica.apply(canonicalEvent(lastSeq + 2, 'interaction.closed', collisionId, { state: 'closed' })), true);
  assert.deepEqual(replica.snapshot().interactions, []);
});

test('terminal responses and reusable committed turns compact behind distinct bounded owners', () => {
  const replica = new ConversationRuntimeReplica(fixture.scope);
  const lastSeq = applyTerminalResponses(replica, 1_000);
  const compact = replica.snapshot();
  assert.equal(lastSeq, 4_001);
  assert.equal(compact.interactions.length, 1);
  assert.equal(compact.turns.length, 128);
  assert.deepEqual(compact.responses, []);
  assert.equal(compact.replay.exact_response_ids.length, 128);
  assert.equal(compact.replay.retirable_turn_ids.length, 128);

  assert.throws(
    () =>
      replica.apply(
        canonicalEvent(lastSeq + 1, 'response.accepted', 'replica-long-interaction', {
          turn_id: 'replica-turn-999',
          response_id: 'unused-replica-response-37824898',
          response_generation: 1_000,
          state: 'accepted',
          cancel_state: 'none',
        })
      ),
    error => error instanceof ConversationReplicaViolation && error.reason === 'REPLICA_REBUILD_REQUIRED'
  );
  assert.equal(replica.snapshot().last_seq, lastSeq);
});

test('an evicted committed turn cannot be guessed invalid and instead requests authoritative rebuild', () => {
  const replica = new ConversationRuntimeReplica(fixture.scope);
  const lastSeq = applyTerminalResponses(replica, 1_000);
  assert.throws(
    () =>
      replica.apply(
        canonicalEvent(lastSeq + 1, 'response.accepted', 'replica-long-interaction', {
          turn_id: 'replica-turn-0',
          response_id: 'turn-rebuild-response',
          response_generation: 1_000,
          state: 'accepted',
          cancel_state: 'none',
        })
      ),
    error => error instanceof ConversationReplicaViolation && error.reason === 'REPLICA_REBUILD_REQUIRED'
  );
});

test('committed turns are bounded before any response and retain recoverable replacement semantics', () => {
  const replica = new ConversationRuntimeReplica(fixture.scope);
  const interactionId = 'committed-only-interaction';
  let seq = 0;
  replica.apply(canonicalEvent(++seq, 'interaction.opened', interactionId, { state: 'open' }));
  for (let index = 0; index < 1_000; index += 1) {
    const turnId = `committed-only-turn-${index}`;
    replica.apply(canonicalEvent(++seq, 'turn.started', interactionId, { turn_id: turnId, state: 'capturing' }));
    replica.apply(canonicalEvent(++seq, 'turn.committed', interactionId, { turn_id: turnId, state: 'committed' }));
  }
  const compact = replica.snapshot();
  assert.equal(compact.turns.length, 128);
  assert.equal(compact.replay.retirable_turn_ids.length, 128);
  assert.throws(
    () =>
      replica.apply(
        canonicalEvent(seq + 1, 'response.accepted', interactionId, {
          turn_id: 'committed-only-turn-0',
          response_id: 'committed-only-response',
          response_generation: 0,
          state: 'accepted',
          cancel_state: 'none',
        })
      ),
    error => error instanceof ConversationReplicaViolation && error.reason === 'REPLICA_REBUILD_REQUIRED'
  );
});

test('authoritative live snapshot rebuild preserves current output authority and rejects wrong scope atomically', () => {
  const authority = new ConversationRuntimeReplica(fixture.scope);
  for (const event of fixture.events.slice(0, 5)) authority.apply(event);
  const replica = new ConversationRuntimeReplica(fixture.scope);
  assert.equal(rebuildFromAuthoritativeSnapshot(replica, authority.snapshot()), true);
  assert.deepEqual(replica.snapshot(), authority.snapshot());
  assert.deepEqual(
    replica.selectOutputEffects('interaction-1', 'response-1', 0).map(item => item.effect_type),
    ['ui.render', 'history.append', 'audio.enqueue']
  );

  const before = replica.snapshot();
  assert.throws(
    () => rebuildFromAuthoritativeSnapshot(replica, { ...before, scope: { ...fixture.scope, subject_id: 'other' } }),
    error => error instanceof ConversationReplicaViolation && error.reason === 'EVENT_SCOPE_MISMATCH'
  );
  assert.deepEqual(replica.snapshot(), before);
});

test('authoritative rebuild rejects lifecycle states that could restore forbidden output', () => {
  const authority = new ConversationRuntimeReplica(fixture.scope);
  for (const event of fixture.events.slice(0, 5)) authority.apply(event);
  const live = authority.snapshot();
  const replica = new ConversationRuntimeReplica(fixture.scope);
  const pristine = replica.snapshot();

  const cancelledButUnfenced = {
    ...live,
    responses: [{ ...live.responses[0], cancel_state: 'acknowledged', fenced: false }],
  };
  assert.throws(
    () => rebuildFromAuthoritativeSnapshot(replica, cancelledButUnfenced),
    error => error instanceof ConversationReplicaViolation && error.reason === 'INVALID_AUTHORITATIVE_SNAPSHOT'
  );
  assert.deepEqual(replica.snapshot(), pristine);

  const closingButUnfenced = {
    ...live,
    interactions: [{ ...live.interactions[0], state: 'closing' }],
  };
  assert.throws(
    () => rebuildFromAuthoritativeSnapshot(replica, closingButUnfenced),
    error => error instanceof ConversationReplicaViolation && error.reason === 'INVALID_AUTHORITATIVE_SNAPSHOT'
  );
  assert.deepEqual(replica.snapshot(), pristine);
});

test('authoritative rebuild cannot hide committed turns outside the bounded reusable owner', () => {
  const authority = new ConversationRuntimeReplica(fixture.scope);
  for (const event of fixture.events.slice(0, 3)) authority.apply(event);
  const live = authority.snapshot();
  assert.equal(live.replay.retirable_turn_ids.length, 1);
  const replica = new ConversationRuntimeReplica(fixture.scope);
  const pristine = replica.snapshot();
  assert.throws(
    () =>
      rebuildFromAuthoritativeSnapshot(replica, {
        ...live,
        replay: { ...live.replay, retirable_turn_ids: [] },
      }),
    error => error instanceof ConversationReplicaViolation && error.reason === 'INVALID_AUTHORITATIVE_SNAPSHOT'
  );
  assert.deepEqual(replica.snapshot(), pristine);
});

test('authoritative rebuild cannot roll back the global event sequence', () => {
  const replica = new ConversationRuntimeReplica(fixture.scope);
  for (const event of fixture.events.slice(0, 5)) replica.apply(event);
  const before = replica.snapshot();
  const staleAuthority = new ConversationRuntimeReplica(fixture.scope);
  for (const event of fixture.events.slice(0, 3)) staleAuthority.apply(event);
  assert.throws(
    () => rebuildFromAuthoritativeSnapshot(replica, staleAuthority.snapshot()),
    error => error instanceof ConversationReplicaViolation && error.reason === 'INVALID_AUTHORITATIVE_SNAPSHOT'
  );
  assert.deepEqual(replica.snapshot(), before);
});
