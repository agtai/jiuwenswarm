import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import test from 'node:test';

import {
  CapabilityRegistry,
  CommandResultLedger,
  ContractViolation,
  EventSequenceTracker,
  IdentityRegistry,
  ResponseFence,
  TurnCommitLedger,
  canonicalJson,
  canonicalJsonBytes,
  classifyContract,
  commandFingerprint,
  defaultBargeInScopes,
  dispatchCancel,
  dispatchCommittedInput,
  parseCapabilityDescriptor,
  parseCommandEnvelope,
  parseConnectionEpochRef,
  parseEventEnvelope,
  parseIdentityRef,
  parseQueryEnvelope,
  parseResultEnvelope,
  parseScopeRef,
  parseTurnCommit,
  parseV2Envelope,
  successResult,
  validateTransition,
} from '../node_modules/.cache/live-voice-contract-v2/liveVoiceContractV2.js';

const fixtureRoot = resolve(process.cwd(), '../../../../tests/fixtures/live_voice_contract_v2');

function load(name) {
  return JSON.parse(readFileSync(resolve(fixtureRoot, name), 'utf8'));
}

function clone(value) {
  return structuredClone(value);
}

function registry(fixture) {
  const identities = new IdentityRegistry();
  const scope = parseScopeRef(fixture.scope);
  for (const raw of fixture.identities) {
    identities.register({
      ref: parseIdentityRef(raw.ref),
      scope,
      parents: raw.parents.map(parent => parseIdentityRef(parent)),
      connection_epoch_ref: raw.connection_epoch_ref == null ? null : parseConnectionEpochRef(raw.connection_epoch_ref),
    });
  }
  return identities;
}

function eventFrom(fixture, options) {
  const raw = clone(fixture.event);
  raw.event_id = options.eventId;
  raw.seq = options.seq;
  raw.causation_id = options.causationId ?? null;
  raw.producer.instance_id = options.producerInstance ?? 'task-core-1';
  raw.event_type = options.eventType ?? 'task.accepted';
  raw.stream_ref.id = options.streamId ?? 'task-1';
  raw.payload = { state: raw.event_type.split('.', 2)[1] };
  return parseEventEnvelope(raw);
}

test('shared valid fixture round-trips with immutable snapshots', () => {
  const fixture = load('critical_kernel.valid.json');
  const identities = registry(fixture);
  const command = parseCommandEnvelope(fixture.command, identities);
  const query = parseQueryEnvelope(fixture.query, identities);
  const result = parseResultEnvelope(fixture.result, command);
  const event = parseEventEnvelope(fixture.event, identities);
  const commit = parseTurnCommit(fixture.turn_commit, identities);
  const capability = parseCapabilityDescriptor(fixture.capability);

  assert.deepEqual(parseV2Envelope(command), command);
  assert.deepEqual(parseV2Envelope(query), query);
  assert.deepEqual(parseV2Envelope(result), result);
  assert.deepEqual(parseV2Envelope(event), event);
  assert.deepEqual(commit, fixture.turn_commit);
  assert.deepEqual(capability, fixture.capability);

  fixture.command.payload.name = 'mutated';
  assert.equal(command.payload.name, 'check inventory');
  assert.equal(Object.isFrozen(command.payload), true);
  assert.throws(() => {
    command.payload.name = 'forbidden';
  }, TypeError);
});

test('shared canonical JSON cases have exact bytes', () => {
  const fixture = load('critical_kernel.valid.json');
  for (const scenario of fixture.canonical_cases) {
    assert.equal(canonicalJson(scenario.input), scenario.canonical);
  }
  assert.deepEqual([...canonicalJsonBytes({ text: '茅' })], [...new TextEncoder().encode(canonicalJson({ text: '茅' }))]);
  assert.deepEqual(
    [...commandFingerprint(parseCommandEnvelope(fixture.command))],
    [...new TextEncoder().encode(canonicalJson((({ request_id: _, ...rest }) => rest)(fixture.command)))]
  );
});

test('shared invalid fixture rejects every indexed scenario with zero effects', () => {
  const { cases } = load('critical_kernel.invalid.json');
  assert.equal(new Set(cases.map(item => item.id)).size, cases.length);
  const fixture = load('critical_kernel.valid.json');
  for (const scenario of cases) {
    let effects = 0;
    assert.throws(
      () => {
        if (scenario.change === 'context_refs_non_empty') {
          const raw = clone(fixture.command);
          raw.context_refs = [{ kind: 'turn', id: 'turn-1' }];
          parseCommandEnvelope(raw);
        } else if (scenario.change === 'wrong_scope_type') {
          const raw = clone(fixture.command);
          raw.scope = [];
          parseCommandEnvelope(raw);
        } else if (scenario.change === 'wrong_authority') {
          const raw = clone(fixture.event);
          raw.producer.authority = 'adapter';
          parseEventEnvelope(raw);
        } else if (scenario.change === 'success_with_error') {
          const raw = clone(fixture.result);
          raw.error = {
            code: 'INTERNAL',
            reason: 'IMPOSSIBLE_SUCCESS',
            message: 'success cannot also carry an error',
            retriable: false,
            correlation_id: null,
            details: {},
          };
          parseResultEnvelope(raw);
        } else if (scenario.change === 'unsafe_integer') {
          const raw = clone(fixture.command);
          raw.payload.number = 9_007_199_254_740_992;
          parseCommandEnvelope(raw);
        } else if (scenario.change === 'unpaired_surrogate') {
          const raw = clone(fixture.command);
          raw.payload.text = '\ud800';
          parseCommandEnvelope(raw);
        } else if (scenario.change === 'accepted_to_terminal') {
          validateTransition('attempt', 'accepted', 'terminal', 'failed');
        } else if (scenario.change === 'generation_only_match') {
          const fence = new ResponseFence();
          fence.begin({
            interaction_id: 'interaction-1',
            response_id: 'response-1',
            response_generation: 0,
          });
          fence.applyIfCurrent(
            {
              interaction_id: 'interaction-1',
              response_id: 'wrong-response',
              response_generation: 0,
            },
            () => {
              effects += 1;
            }
          );
        } else {
          assert.fail(`unknown invalid scenario ${scenario.change}`);
        }
      },
      error => error instanceof ContractViolation && error.error.reason === scenario.reason,
      scenario.id
    );
    assert.equal(effects, 0, scenario.id);
    assert.equal(scenario.zero_effect, true, scenario.id);
  }
});

for (const state of ['partial', 'uncommitted']) {
  for (const target of ['agent', 'tool', 'task']) {
    test(`${state} input has zero ${target} effects`, () => {
      let calls = 0;
      assert.throws(
        () =>
          dispatchCommittedInput(state, target, () => {
            calls += 1;
          }),
        error => error instanceof ContractViolation && error.error.reason === 'INPUT_NOT_COMMITTED'
      );
      assert.equal(calls, 0);
      dispatchCommittedInput('committed', target, () => {
        calls += 1;
      });
      assert.equal(calls, 1);
    });
  }
}

test('turn commit is parent-bound, immutable, and once-only', () => {
  const fixture = load('critical_kernel.valid.json');
  const identities = registry(fixture);
  const ledger = new TurnCommitLedger();
  const commit = parseTurnCommit(fixture.turn_commit, identities);
  assert.equal(ledger.accept(commit), true);
  assert.equal(ledger.accept(commit), false);
  assert.equal(parseCommandEnvelope(fixture.command, identities, ledger).origin.commit_id, commit.commit_id);
  const wrongOrigin = clone(fixture.command);
  wrongOrigin.origin.commit_id = 'commit-not-accepted';
  assert.throws(
    () => parseCommandEnvelope(wrongOrigin, identities, ledger),
    error => error instanceof ContractViolation && error.error.reason === 'TURN_COMMIT_NOT_ACCEPTED'
  );

  const dispatchLedger = new TurnCommitLedger();
  let effects = 0;
  assert.deepEqual(
    dispatchLedger.dispatch(commit, 'agent', () => {
      effects += 1;
      return 'sent';
    }),
    [true, 'sent']
  );
  assert.deepEqual(
    dispatchLedger.dispatch(commit, 'agent', () => {
      effects += 1;
      return 'duplicate';
    }),
    [false, undefined]
  );
  assert.equal(effects, 1);

  const changed = clone(fixture.turn_commit);
  changed.text = 'different';
  assert.throws(
    () => ledger.accept(parseTurnCommit(changed, identities)),
    error => error instanceof ContractViolation && error.error.reason === 'TURN_COMMIT_CONFLICT'
  );

  const wrongParent = clone(fixture.turn_commit);
  wrongParent.interaction_id = 'interaction-other';
  assert.throws(() => parseTurnCommit(wrongParent, identities), ContractViolation);
});

test('identity scope, kind, parent, and closed-object boundaries reject', () => {
  const fixture = load('critical_kernel.valid.json');
  const identities = registry(fixture);

  const emptyId = clone(fixture.command);
  emptyId.request_id = '  ';
  assert.throws(
    () => parseCommandEnvelope(emptyId),
    error => error instanceof ContractViolation && error.error.reason === 'INVALID_REQUIRED_TEXT'
  );

  const wrongKind = clone(fixture.query);
  wrongKind.target_ref = { kind: 'response', id: 'response-1' };
  assert.throws(
    () => parseQueryEnvelope(wrongKind),
    error => error instanceof ContractViolation && error.error.reason === 'IDENTITY_KIND_MISMATCH'
  );

  const unknownField = clone(fixture.command);
  unknownField.unexpected = true;
  assert.throws(
    () => parseCommandEnvelope(unknownField),
    error => error instanceof ContractViolation && error.error.reason === 'UNKNOWN_FIELD'
  );

  const ownProto = JSON.parse(JSON.stringify(fixture.command));
  Object.defineProperty(ownProto, '__proto__', {
    value: { polluted: true },
    enumerable: true,
    configurable: true,
    writable: true,
  });
  assert.throws(
    () => parseCommandEnvelope(ownProto),
    error => error instanceof ContractViolation && error.error.reason === 'UNKNOWN_FIELD'
  );

  const unknownEnum = clone(fixture.command);
  unknownEnum.scope.assurance = 'trusted';
  assert.throws(
    () => parseCommandEnvelope(unknownEnum),
    error => error instanceof ContractViolation && error.error.reason === 'INVALID_ENUM'
  );

  const scope = parseScopeRef(fixture.scope);
  const interaction2 = { kind: 'interaction', id: 'interaction-2' };
  identities.register({ ref: interaction2, scope, parents: [] });
  assert.throws(
    () =>
      identities.register({
        ref: { kind: 'response', id: 'response-cross-parent' },
        scope,
        parents: [interaction2, { kind: 'turn', id: 'turn-1' }],
      }),
    error => error instanceof ContractViolation && error.error.reason === 'IDENTITY_PARENT_MISMATCH'
  );

  const differentScope = { ...scope, project_id: 'project-other' };
  assert.throws(
    () =>
      identities.register({
        ref: { kind: 'turn', id: 'turn-cross-scope' },
        scope: differentScope,
        parents: [{ kind: 'interaction', id: 'interaction-1' }],
      }),
    error => error instanceof ContractViolation && error.error.reason === 'IDENTITY_SCOPE_MISMATCH'
  );
});

test('connection epoch binding and round parent rules are exact', () => {
  const fixture = load('critical_kernel.valid.json');
  const identities = registry(fixture);
  const scope = parseScopeRef(fixture.scope);
  const binding = parseConnectionEpochRef({ connection_id: 'connection-1', connection_epoch: 7 });

  const connection = identities.require({ kind: 'connection', id: 'connection-1' });
  const media = identities.require({ kind: 'media_session', id: 'media-session-1' });
  assert.deepEqual(connection.connection_epoch_ref, binding);
  assert.deepEqual(media.connection_epoch_ref, binding);
  assert.equal(Object.isFrozen(connection.connection_epoch_ref), true);
  assert.throws(() => {
    connection.connection_epoch_ref.connection_epoch = 8;
  }, TypeError);

  assert.throws(
    () => new IdentityRegistry().register({ ref: { kind: 'connection', id: 'connection-2' }, scope, parents: [] }),
    error => error instanceof ContractViolation && error.error.reason === 'CONNECTION_EPOCH_BINDING_REQUIRED'
  );
  assert.throws(
    () =>
      new IdentityRegistry().register({
        ref: { kind: 'connection', id: 'connection-2' },
        scope,
        parents: [],
        connection_epoch_ref: { connection_id: 'connection-other', connection_epoch: 0 },
      }),
    error => error instanceof ContractViolation && error.error.reason === 'CONNECTION_EPOCH_BINDING_MISMATCH'
  );
  assert.throws(
    () =>
      identities.register({
        ref: { kind: 'media_session', id: 'media-session-2' },
        scope,
        parents: [{ kind: 'interaction', id: 'interaction-1' }],
      }),
    error => error instanceof ContractViolation && error.error.reason === 'CONNECTION_EPOCH_BINDING_REQUIRED'
  );
  assert.throws(
    () =>
      identities.register({
        ref: { kind: 'media_session', id: 'media-session-2' },
        scope,
        parents: [{ kind: 'interaction', id: 'interaction-1' }],
        connection_epoch_ref: { connection_id: 'connection-unknown', connection_epoch: 7 },
      }),
    error => error instanceof ContractViolation && error.error.reason === 'IDENTITY_CONNECTION_NOT_FOUND'
  );
  assert.throws(
    () =>
      identities.register({
        ref: { kind: 'media_session', id: 'media-session-2' },
        scope,
        parents: [{ kind: 'interaction', id: 'interaction-1' }],
        connection_epoch_ref: { connection_id: 'connection-1', connection_epoch: 6 },
      }),
    error => error instanceof ContractViolation && error.error.reason === 'CONNECTION_EPOCH_BINDING_MISMATCH'
  );
  assert.throws(
    () =>
      identities.register({
        ref: { kind: 'round', id: 'round-2' },
        scope,
        parents: [],
        connection_epoch_ref: binding,
      }),
    error => error instanceof ContractViolation && error.error.reason === 'CONNECTION_EPOCH_BINDING_FORBIDDEN'
  );
  assert.throws(
    () =>
      identities.register({
        ref: { kind: 'round', id: 'round-2' },
        scope,
        parents: [{ kind: 'turn', id: 'turn-1' }],
      }),
    error => error instanceof ContractViolation && error.error.reason === 'IDENTITY_PARENT_MISMATCH'
  );

  const crossScope = new IdentityRegistry();
  crossScope.register({ ref: { kind: 'interaction', id: 'interaction-a' }, scope, parents: [] });
  crossScope.register({
    ref: { kind: 'connection', id: 'connection-cross' },
    scope: { ...scope, project_id: 'project-other' },
    parents: [],
    connection_epoch_ref: { connection_id: 'connection-cross', connection_epoch: 1 },
  });
  assert.throws(
    () =>
      crossScope.register({
        ref: { kind: 'media_session', id: 'media-cross' },
        scope,
        parents: [{ kind: 'interaction', id: 'interaction-a' }],
        connection_epoch_ref: { connection_id: 'connection-cross', connection_epoch: 1 },
      }),
    error => error instanceof ContractViolation && error.error.reason === 'IDENTITY_SCOPE_MISMATCH'
  );
});

test('command ledger executes one concurrent request and replays owner-bound results', async () => {
  const fixture = load('critical_kernel.valid.json');
  const command = parseCommandEnvelope(fixture.command);
  const replayRaw = clone(fixture.command);
  replayRaw.request_id = 'request-replay';
  const replay = parseCommandEnvelope(replayRaw);
  const ledger = new CommandResultLedger();
  let calls = 0;
  let release;
  const blocked = new Promise(resolveRelease => {
    release = resolveRelease;
  });
  const handler = async owner => {
    calls += 1;
    await blocked;
    return successResult(owner, { accepted: true }, '2026-08-04T08:00:02Z');
  };

  const first = ledger.execute(command, '2026-08-04T08:00:02Z', handler);
  const second = ledger.execute(replay, '2026-08-04T08:00:02Z', handler);
  release();
  const [firstResult, replayResult] = await Promise.all([first, second]);
  assert.equal(calls, 1);
  assert.equal(firstResult.request_id, command.request_id);
  assert.equal(replayResult.request_id, replay.request_id);
  assert.equal(replayResult.command_id, command.command_id);
});

test('command ledger publishes the pending entry before a synchronous reentrant delivery', async () => {
  const fixture = load('critical_kernel.valid.json');
  const command = parseCommandEnvelope(fixture.command);
  const replayRaw = clone(fixture.command);
  replayRaw.request_id = 'request-reentrant';
  const replay = parseCommandEnvelope(replayRaw);
  const ledger = new CommandResultLedger();
  let calls = 0;
  let reentrant;
  const handler = async owner => {
    calls += 1;
    if (reentrant === undefined) {
      reentrant = ledger.execute(replay, '2026-08-04T08:00:02Z', handler);
    }
    return successResult(owner, { accepted: true }, '2026-08-04T08:00:02Z');
  };
  const first = await ledger.execute(command, '2026-08-04T08:00:02Z', handler);
  const second = await reentrant;
  assert.equal(calls, 1);
  assert.equal(first.request_id, command.request_id);
  assert.equal(second.request_id, replay.request_id);
});

test('command conflict and handler failure never cause re-execution', async () => {
  const fixture = load('critical_kernel.valid.json');
  const command = parseCommandEnvelope(fixture.command);
  const ledger = new CommandResultLedger();
  let calls = 0;
  const broken = async () => {
    calls += 1;
    throw new Error('private detail must not escape');
  };

  const first = await ledger.execute(command, '2026-08-04T08:00:02Z', broken);
  const replay = await ledger.execute(command, '2026-08-04T08:00:03Z', broken);
  assert.equal(calls, 1);
  assert.equal(first.error.reason, 'COMMAND_HANDLER_FAILED');
  assert.deepEqual(replay.error, first.error);

  const changed = clone(fixture.command);
  changed.payload.priority = 2;
  const conflict = await ledger.execute(parseCommandEnvelope(changed), '2026-08-04T08:00:04Z', broken);
  assert.equal(calls, 1);
  assert.equal(conflict.error.code, 'CONFLICT');
  assert.equal(conflict.error.reason, 'IDEMPOTENCY_CONFLICT');
});

test('response output requires the exact tuple and every replacement gets a new id', () => {
  const fence = new ResponseFence();
  const first = { interaction_id: 'interaction-1', response_id: 'response-1', response_generation: 0 };
  const replacement = {
    interaction_id: 'interaction-1',
    response_id: 'response-2',
    response_generation: 1,
  };
  const effects = [];
  fence.begin(first);
  fence.applyIfCurrent(first, () => effects.push('first'));
  fence.begin(replacement);
  assert.throws(() => fence.applyIfCurrent(first, () => effects.push('stale')), ContractViolation);
  assert.throws(
    () => fence.applyIfCurrent({ interaction_id: 'interaction-1', response_id: 'wrong', response_generation: 1 }, () => effects.push('wrong')),
    ContractViolation
  );
  fence.cancel(replacement);
  assert.throws(() => fence.applyIfCurrent(replacement, () => effects.push('cancelled')));
  assert.throws(() => fence.begin({ interaction_id: 'interaction-1', response_id: 'response-1', response_generation: 2 }));
  assert.deepEqual(effects, ['first']);
});

test('the four cancel scopes route to exactly one handler', () => {
  const fixture = load('critical_kernel.valid.json');
  const expected = {
    'playback.stop': 'response',
    'response.cancel': 'response',
    'round.cancel': 'round',
    'task.cancel': 'task',
  };
  const calls = [];
  const handlers = Object.fromEntries(
    Object.keys(expected).map(scope => [scope, command => calls.push([scope, command.target_ref.id, command.payload.response_generation ?? null])])
  );
  for (const [scope, kind] of Object.entries(expected)) {
    const raw = clone(fixture.command);
    raw.command_type = scope;
    raw.target_ref = { kind, id: `${kind}-1` };
    raw.payload = kind === 'response' ? { interaction_id: 'interaction-1', response_generation: 0 } : {};
    dispatchCancel(parseCommandEnvelope(raw), handlers);
  }
  assert.deepEqual(
    calls,
    Object.entries(expected).map(([scope, kind]) => [scope, `${kind}-1`, kind === 'response' ? 0 : null])
  );
  assert.deepEqual(defaultBargeInScopes(), ['playback.stop']);
  assert.deepEqual(defaultBargeInScopes(true), ['playback.stop', 'response.cancel']);
  for (const invalid of fixture.invalid_cancel_values) {
    const raw = clone(fixture.command);
    raw.command_type = invalid;
    assert.throws(() => parseCommandEnvelope(raw), ContractViolation);
  }
  const wrongOwner = clone(fixture.command);
  Object.assign(wrongOwner, {
    command_type: 'response.cancel',
    target_ref: { kind: 'response', id: 'response-1' },
    payload: { interaction_id: 'interaction-other', response_generation: 0 },
  });
  assert.throws(() => parseCommandEnvelope(wrongOwner, registry(fixture)), ContractViolation);
});

test('attempt cannot skip running and terminal transitions require outcome', () => {
  const fixture = load('critical_kernel.valid.json');
  for (const [kind, current, target] of fixture.lifecycle_allowed) {
    validateTransition(kind, current, target, target === 'terminal' ? 'completed' : null);
  }
  for (const [kind, current, target] of fixture.lifecycle_forbidden) {
    assert.throws(() => validateTransition(kind, current, target, target === 'terminal' ? 'failed' : null));
  }
  validateTransition('attempt', 'accepted', 'running');
  validateTransition('attempt', 'running', 'terminal', 'completed');
  assert.throws(() => validateTransition('attempt', 'accepted', 'terminal', 'failed'));
  assert.throws(() => validateTransition('response', 'generating', 'terminal'));
  assert.throws(() => validateTransition('response', 'accepted', 'generating', 'completed'));
});

test('event gaps drain in order and a conflicting sequence remains poisoned', () => {
  const fixture = load('critical_kernel.valid.json');
  const later = eventFrom(fixture, { eventId: 'event-1', seq: 1, eventType: 'task.running' });
  const first = eventFrom(fixture, { eventId: 'event-0', seq: 0 });
  const tracker = new EventSequenceTracker();
  assert.equal(tracker.accept(later).status, 'quarantined_gap');
  assert.deepEqual(tracker.accept(first).appliedEventIds, ['event-0', 'event-1']);
  assert.equal(tracker.accept(later).status, 'duplicate_applied');

  const poisoned = new EventSequenceTracker();
  assert.equal(poisoned.accept(later).status, 'quarantined_gap');
  const conflict = eventFrom(fixture, {
    eventId: 'event-conflict',
    seq: 1,
    eventType: 'task.running',
  });
  const rejectedConflict = poisoned.accept(conflict);
  assert.equal(rejectedConflict.status, 'rejected_conflict');
  assert.equal(rejectedConflict.error.code, 'PROTOCOL_VIOLATION');
  assert.deepEqual(poisoned.accept(first).appliedEventIds, ['event-0']);
  const duplicate = poisoned.accept(later);
  assert.equal(duplicate.status, 'duplicate_quarantined');
  assert.notEqual(duplicate.error, null);

  const idConflictTracker = new EventSequenceTracker();
  assert.equal(idConflictTracker.accept(later).status, 'quarantined_gap');
  const sameIdChanged = eventFrom(fixture, {
    eventId: 'event-1',
    seq: 2,
    eventType: 'task.running',
  });
  assert.equal(idConflictTracker.accept(sameIdChanged).status, 'rejected_conflict');
  assert.deepEqual(idConflictTracker.accept(first).appliedEventIds, ['event-0']);
  const poisonedOriginal = idConflictTracker.accept(later);
  assert.equal(poisonedOriginal.status, 'duplicate_quarantined');
  assert.equal(poisonedOriginal.error.reason, 'EVENT_ID_CONFLICT');
});

test('causation requires an applied event while later roots remain valid', () => {
  const fixture = load('critical_kernel.valid.json');
  const tracker = new EventSequenceTracker();
  const child = eventFrom(fixture, {
    eventId: 'event-child',
    seq: 0,
    causationId: 'event-root',
    producerInstance: 'task-core-child',
    eventType: 'task.running',
  });
  const root = eventFrom(fixture, {
    eventId: 'event-root',
    seq: 0,
    producerInstance: 'task-core-root',
  });
  assert.equal(tracker.accept(child).status, 'quarantined_causation');
  assert.deepEqual(tracker.accept(root).appliedEventIds, ['event-root', 'event-child']);
  const laterRoot = eventFrom(fixture, {
    eventId: 'event-later-root',
    seq: 0,
    producerInstance: 'task-core-later',
    streamId: 'task-2',
  });
  assert.equal(tracker.accept(laterRoot).status, 'applied');
  const externallyCaused = eventFrom(fixture, {
    eventId: 'event-command-caused',
    seq: 0,
    causationId: 'command-accepted-1',
    producerInstance: 'task-core-command-caused',
    streamId: 'task-3',
  });
  const commandTracker = new EventSequenceTracker();
  assert.equal(commandTracker.accept(externallyCaused).status, 'quarantined_causation');
  const commandCause = clone(fixture.command);
  commandCause.command_id = 'command-accepted-1';
  assert.deepEqual(commandTracker.registerAppliedCause(parseCommandEnvelope(commandCause)), ['event-command-caused']);
  assert.equal(commandTracker.accept(externallyCaused).status, 'duplicate_applied');
});

test('event causation preserves exact scope and correlation', () => {
  const fixture = load('critical_kernel.valid.json');
  for (const [field, reason] of [
    ['scope', 'CAUSATION_SCOPE_MISMATCH'],
    ['correlation_id', 'CAUSATION_CORRELATION_MISMATCH'],
  ]) {
    const tracker = new EventSequenceTracker();
    const source = eventFrom(fixture, { eventId: `cause-source-${field}`, seq: 0 });
    assert.equal(tracker.accept(source).status, 'applied');
    const childRaw = clone(fixture.event);
    Object.assign(childRaw, {
      event_id: `cause-child-${field}`,
      event_type: 'task.running',
      producer: {
        component: 'task_core',
        instance_id: `cause-child-${field}`,
        authority: 'task_core',
      },
      seq: 0,
      causation_id: `cause-source-${field}`,
      payload: { state: 'running' },
    });
    if (field === 'scope') childRaw.scope.subject_id = 'other-subject';
    else childRaw.correlation_id = 'other-correlation';
    const result = tracker.accept(parseEventEnvelope(childRaw));
    assert.equal(result.status, 'rejected_causation');
    assert.equal(result.error.reason, reason);
  }
});

test('event tracker enforces lifecycle and adapter authority chains', () => {
  const fixture = load('critical_kernel.valid.json');
  const terminalFirstRaw = clone(fixture.event);
  Object.assign(terminalFirstRaw, {
    event_id: 'event-terminal-first',
    event_type: 'task.terminal',
    payload: { state: 'terminal', outcome: 'failed' },
  });
  const tracker = new EventSequenceTracker();
  const rejected = tracker.accept(parseEventEnvelope(terminalFirstRaw));
  assert.equal(rejected.status, 'rejected_lifecycle');
  assert.equal(rejected.error.reason, 'INVALID_INITIAL_LIFECYCLE_STATE');

  const attemptAcceptedRaw = clone(fixture.event);
  Object.assign(attemptAcceptedRaw, {
    event_id: 'attempt-event-0',
    event_type: 'attempt.accepted',
    producer: { component: 'executor', instance_id: 'executor-1', authority: 'executor' },
    stream_ref: { kind: 'attempt', id: 'attempt-1' },
    payload: { state: 'accepted' },
  });
  const attemptTerminalRaw = clone(attemptAcceptedRaw);
  Object.assign(attemptTerminalRaw, {
    event_id: 'attempt-event-1',
    event_type: 'attempt.terminal',
    seq: 1,
    payload: { state: 'terminal', outcome: 'failed' },
  });
  const attemptTracker = new EventSequenceTracker();
  assert.equal(attemptTracker.accept(parseEventEnvelope(attemptAcceptedRaw)).status, 'applied');
  const attemptRejected = attemptTracker.accept(parseEventEnvelope(attemptTerminalRaw));
  assert.equal(attemptRejected.status, 'rejected_lifecycle');
  assert.equal(attemptRejected.error.code, 'PROTOCOL_VIOLATION');

  const taskTracker = new EventSequenceTracker();
  const accepted = eventFrom(fixture, { eventId: 'task-restart-0', seq: 0 });
  const terminalRaw = clone(fixture.event);
  Object.assign(terminalRaw, {
    event_id: 'task-restart-1',
    event_type: 'task.terminal',
    seq: 1,
    payload: { state: 'terminal', outcome: 'completed' },
  });
  const restarted = eventFrom(fixture, {
    eventId: 'task-restart-2',
    seq: 0,
    producerInstance: 'task-core-restarted',
  });
  assert.equal(taskTracker.accept(accepted).status, 'applied');
  assert.equal(taskTracker.accept(parseEventEnvelope(terminalRaw)).status, 'applied');
  const restartedResult = taskTracker.accept(restarted);
  assert.equal(restartedResult.status, 'rejected_lifecycle');
  assert.equal(restartedResult.error.reason, 'INVALID_LIFECYCLE_TRANSITION');

  const source = eventFrom(fixture, { eventId: 'source-event', seq: 0 });
  const adapterRaw = clone(fixture.event);
  Object.assign(adapterRaw, {
    event_id: 'adapter-event-1',
    event_type: 'adapter.observed',
    producer: { component: 'task.adapter', instance_id: 'adapter-1', authority: 'adapter' },
    stream_ref: { kind: 'event', id: 'adapter-stream-1' },
    causation_id: 'source-event',
    payload: { source_event_type: 'task.accepted' },
  });
  const authorityTracker = new EventSequenceTracker();
  assert.equal(authorityTracker.accept(source).status, 'applied');
  const adapter = parseEventEnvelope(adapterRaw);
  assert.equal(authorityTracker.accept(adapter).status, 'applied');

  const chainedRaw = clone(adapterRaw);
  Object.assign(chainedRaw, {
    event_id: 'adapter-event-2',
    producer: { component: 'task.adapter', instance_id: 'adapter-2', authority: 'adapter' },
    stream_ref: { kind: 'event', id: 'adapter-stream-2' },
    causation_id: 'adapter-event-1',
    payload: { source_event_type: 'adapter.observed' },
  });
  const chained = authorityTracker.accept(parseEventEnvelope(chainedRaw));
  assert.equal(chained.status, 'rejected_causation');
  assert.equal(chained.error.reason, 'ADAPTER_SOURCE_NOT_AUTHORITATIVE');
});

test('authority, capability availability, and v1/v2 identity remain distinct', () => {
  const fixture = load('critical_kernel.valid.json');
  const wrong = clone(fixture.event);
  wrong.producer.authority = 'adapter';
  assert.throws(
    () => parseEventEnvelope(wrong),
    error => error instanceof ContractViolation && error.error.code === 'PERMISSION_DENIED'
  );

  const capabilities = new CapabilityRegistry();
  capabilities.register(parseCapabilityDescriptor(fixture.capability));
  capabilities.require('speech.sr', 'recognize.batch');
  assert.throws(() => capabilities.require('speech.sr', 'synthesize.batch'));
  const unavailable = clone(fixture.capability);
  unavailable.component = 'speech.unavailable';
  unavailable.availability = 'unavailable';
  capabilities.register(parseCapabilityDescriptor(unavailable));
  assert.throws(
    () => capabilities.require('speech.unavailable', 'recognize.batch'),
    error => error instanceof ContractViolation && error.error.code === 'UNAVAILABLE'
  );
  const failureRaw = {
    contract_version: 'live-voice.contract.v2',
    request_id: 'request-2',
    command_id: null,
    ok: false,
    result: null,
    error: {
      code: 'UNAVAILABLE',
      reason: 'PROVIDER_DOWN',
      message: 'provider is unavailable',
      retriable: true,
      correlation_id: 'correlation-1',
      details: {},
    },
    observed_at: '2026-08-04T08:00:05Z',
    extensions: {},
  };
  assert.deepEqual(parseResultEnvelope(parseResultEnvelope(failureRaw)), failureRaw);
  const observedCodes = fixture.distinct_error_codes.map(code => {
    const raw = clone(failureRaw);
    raw.error.code = code;
    raw.error.reason = `TEST_${code}`;
    return parseResultEnvelope(raw).error.code;
  });
  assert.deepEqual(observedCodes, fixture.distinct_error_codes);
  const wrongMode = clone(fixture.capability);
  wrongMode.batch_modes = ['stream'];
  assert.throws(() => parseCapabilityDescriptor(wrongMode), ContractViolation);

  const legacy = load('compatibility.v1.json');
  assert.equal(classifyContract(legacy), 'v1');
  assert.throws(() => parseV2Envelope(legacy));
});

test('strict JS boundary rejects accessors, prototype tricks, cycles, sparse arrays, and unsafe integers', () => {
  const fixture = load('critical_kernel.valid.json');
  let getterCalls = 0;
  const accessor = clone(fixture.command);
  Object.defineProperty(accessor, 'payload', {
    enumerable: true,
    get() {
      getterCalls += 1;
      return {};
    },
  });
  assert.throws(() => parseCommandEnvelope(accessor), ContractViolation);
  assert.equal(getterCalls, 0);

  const inherited = Object.create({ scope: fixture.scope });
  Object.assign(inherited, fixture.command);
  delete inherited.scope;
  assert.throws(() => parseCommandEnvelope(inherited), ContractViolation);

  const cycle = clone(fixture.command);
  cycle.payload.cycle = cycle.payload;
  assert.throws(() => parseCommandEnvelope(cycle), ContractViolation);

  const sparse = clone(fixture.command);
  sparse.payload.values = [1, , 3];
  assert.throws(() => parseCommandEnvelope(sparse), ContractViolation);

  const unsafe = clone(fixture.command);
  unsafe.payload.number = 9_007_199_254_740_992;
  assert.throws(
    () => parseCommandEnvelope(unsafe),
    error => error instanceof ContractViolation && error.error.reason === 'INVALID_SAFE_INTEGER'
  );
  const unsafeSequence = clone(fixture.event);
  unsafeSequence.seq = 9_007_199_254_740_992;
  assert.throws(
    () => parseEventEnvelope(unsafeSequence),
    error => error instanceof ContractViolation && error.error.reason === 'INVALID_SAFE_INTEGER'
  );
  assert.throws(
    () => dispatchCommittedInput('invalid', 'agent', () => undefined),
    error => error instanceof ContractViolation && error.error.reason === 'INVALID_ENUM'
  );
  assert.throws(() => defaultBargeInScopes('yes'), ContractViolation);
});

test('stateful TypeScript helpers normalize mutable structural inputs at entry', async () => {
  const fixture = load('critical_kernel.valid.json');
  const rawCommit = clone(fixture.turn_commit);
  const commitLedger = new TurnCommitLedger();
  assert.equal(commitLedger.accept(rawCommit), true);
  rawCommit.text = 'changed after acceptance';
  assert.throws(() => commitLedger.accept(rawCommit), ContractViolation);

  const rawCommand = clone(fixture.command);
  const commandLedger = new CommandResultLedger();
  let release;
  const blocked = new Promise(resolveRelease => {
    release = resolveRelease;
  });
  const execution = commandLedger.execute(rawCommand, '2026-08-04T08:00:06Z', async owner => {
    await blocked;
    return successResult(owner, { accepted: true }, '2026-08-04T08:00:06Z');
  });
  rawCommand.payload.name = 'mutated during execution';
  release();
  assert.equal((await execution).ok, true);

  const rawGap = clone(fixture.event);
  rawGap.event_id = 'normalized-gap';
  rawGap.event_type = 'task.running';
  rawGap.payload = { state: 'running' };
  rawGap.seq = 1;
  const tracker = new EventSequenceTracker();
  assert.equal(tracker.accept(rawGap).status, 'quarantined_gap');
  rawGap.event_id = 'mutated-id';
  rawGap.payload.state = 'blocked';
  const first = eventFrom(fixture, { eventId: 'normalized-first', seq: 0 });
  assert.deepEqual(tracker.accept(first).appliedEventIds, ['normalized-first', 'normalized-gap']);
});
