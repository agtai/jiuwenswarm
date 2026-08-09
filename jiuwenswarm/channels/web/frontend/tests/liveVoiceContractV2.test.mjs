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
  parseContextRef,
  parseEventEnvelope,
  parseIdentityRef,
  parseQueryEnvelope,
  parseResultEnvelope,
  parseScopeRef,
  parseTurnCommit,
  parseV2Envelope,
  parseWorkProgressEventV2,
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

test('ContextRef wire shape round-trips and cross-scope use fails closed', () => {
  const fixture = load('critical_kernel.valid.json');
  const progressFixture = load('work_progress.v2.json');
  const refs = progressFixture.context_refs.map(parseContextRef);
  assert.deepEqual(refs, progressFixture.context_refs);
  assert.equal(refs[0].revision.value, 'sha256:abc');
  assert.equal(refs[1].revision.value, 'snapshot-2');
  assert.equal(refs[2].revision.value, undefined);

  const commandRaw = clone(fixture.command);
  commandRaw.context_refs = clone(progressFixture.context_refs);
  const command = parseCommandEnvelope(commandRaw);
  assert.deepEqual(command, commandRaw);
  assert.equal(command.context_refs.length, 3);

  const queryRaw = clone(fixture.query);
  queryRaw.context_refs = clone(progressFixture.context_refs);
  assert.deepEqual(parseQueryEnvelope(queryRaw), queryRaw);

  const commitRaw = clone(fixture.turn_commit);
  commitRaw.context_refs = clone(progressFixture.context_refs);
  assert.deepEqual(parseTurnCommit(commitRaw), commitRaw);

  const wrongScope = clone(commandRaw);
  wrongScope.context_refs[0].scope.session_id = 'other-session';
  assert.throws(
    () => parseCommandEnvelope(wrongScope),
    error => error instanceof ContractViolation && error.error.reason === 'CONTEXT_SCOPE_MISMATCH'
  );

  const secretField = clone(progressFixture.context_refs[0]);
  secretField.content = 'must-not-cross-the-wire';
  assert.throws(
    () => parseContextRef(secretField),
    error => error instanceof ContractViolation && error.error.reason === 'UNKNOWN_FIELD'
  );
});

test('WorkProgress v2 preserves known/unknown facts and separates envelope/project sequences', () => {
  const fixture = load('work_progress.v2.json');
  const tracker = new EventSequenceTracker();
  const sources = fixture.source_events.map(item => parseEventEnvelope(item));
  const progressEvents = fixture.progress_events.map(item => parseEventEnvelope(item));
  const accepted = parseWorkProgressEventV2(progressEvents[0].payload, progressEvents[0].scope);
  const running = parseWorkProgressEventV2(progressEvents[1].payload, progressEvents[1].scope);
  const terminal = parseWorkProgressEventV2(progressEvents[2].payload, progressEvents[2].scope);
  assert.deepEqual(accepted, fixture.progress_events[0].payload);
  assert.deepEqual(accepted.artifact_refs, { knowledge: 'unknown' });
  assert.deepEqual(running.artifact_refs, { knowledge: 'unknown' });
  assert.equal(terminal.outcome, 'completed');
  assert.equal(progressEvents[1].seq, 0);
  assert.equal(running.seq, 1);
  const maximum = clone(progressEvents[0].payload);
  maximum.seq = Number.MAX_SAFE_INTEGER;
  assert.equal(parseWorkProgressEventV2(maximum).seq, Number.MAX_SAFE_INTEGER);
  const knownEmpty = clone(progressEvents[0].payload);
  knownEmpty.artifact_refs = { knowledge: 'known', value: [] };
  assert.deepEqual(parseWorkProgressEventV2(knownEmpty).artifact_refs, { knowledge: 'known', value: [] });

  for (const source of sources) assert.equal(tracker.accept(source).status, 'applied');
  const futureRaw = clone(fixture.progress_events[2]);
  futureRaw.producer.instance_id = 'bridge-3';
  futureRaw.seq = 0;
  const future = tracker.accept(parseEventEnvelope(futureRaw));
  assert.equal(future.status, 'quarantined_projection');
  assert.equal(future.error.reason, 'PROGRESS_SEQUENCE_GAP');
  assert.equal(tracker.accept(progressEvents[0]).status, 'applied');
  const second = tracker.accept(progressEvents[1]);
  assert.equal(second.status, 'applied');
  assert.deepEqual(second.appliedEventIds, ['progress-1', 'progress-2']);

  const duplicateSource = clone(fixture.progress_events[0]);
  duplicateSource.event_id = 'progress-overlap';
  duplicateSource.producer.instance_id = 'bridge-overlap';
  duplicateSource.seq = 0;
  duplicateSource.payload.seq = 3;
  const duplicate = tracker.accept(parseEventEnvelope(duplicateSource));
  assert.equal(duplicate.status, 'rejected_projection');
  assert.equal(duplicate.error.reason, 'PROGRESS_SOURCE_ALREADY_PROJECTED');

  const orderTracker = new EventSequenceTracker();
  for (const source of sources) assert.equal(orderTracker.accept(source).status, 'applied');
  const reversedProgress = clone(fixture.progress_events[2]);
  reversedProgress.event_id = 'progress-terminal-first';
  reversedProgress.producer.instance_id = 'bridge-terminal-first';
  reversedProgress.seq = 0;
  reversedProgress.payload.seq = 0;
  const reversed = orderTracker.accept(parseEventEnvelope(reversedProgress));
  assert.equal(reversed.status, 'rejected_projection');
  assert.equal(reversed.error.reason, 'PROGRESS_SOURCE_ORDER_MISMATCH');

  const fabricatedDetail = clone(fixture.progress_events[0]);
  fabricatedDetail.event_id = 'progress-fabricated-detail';
  fabricatedDetail.producer.instance_id = 'bridge-fabricated-detail';
  fabricatedDetail.seq = 0;
  fabricatedDetail.payload.summary = { knowledge: 'known', value: 'guessed' };
  const detail = orderTracker.accept(parseEventEnvelope(fabricatedDetail));
  assert.equal(detail.status, 'rejected_projection');
  assert.equal(detail.error.reason, 'PROGRESS_DETAIL_UNPROVEN');
});

test('WorkProgress v2 rejects false authority, outcome, and source mapping', () => {
  const fixture = load('work_progress.v2.json');
  const wrongAuthority = clone(fixture.progress_events[0]);
  wrongAuthority.payload.source.authority = 'executor';
  assert.throws(
    () => parseEventEnvelope(wrongAuthority),
    error => error instanceof ContractViolation && error.error.reason === 'PROGRESS_SOURCE_AUTHORITY_MISMATCH'
  );

  const wrongOutcome = clone(fixture.progress_events[0]);
  wrongOutcome.payload.outcome = 'completed';
  assert.throws(
    () => parseEventEnvelope(wrongOutcome),
    error => error instanceof ContractViolation && error.error.reason === 'NON_TERMINAL_OUTCOME_FORBIDDEN'
  );

  const tracker = new EventSequenceTracker();
  assert.equal(tracker.accept(parseEventEnvelope(fixture.source_events[0])).status, 'applied');
  const falseProgress = clone(fixture.progress_events[0]);
  falseProgress.payload.state = 'running';
  const rejected = tracker.accept(parseEventEnvelope(falseProgress));
  assert.equal(rejected.status, 'rejected_causation');
  assert.equal(rejected.error.reason, 'PROGRESS_SOURCE_MISMATCH');

  const attemptProgress = clone(fixture.progress_events[0]);
  attemptProgress.event_id = 'attempt-progress-0';
  attemptProgress.stream_ref = { kind: 'task', id: 'task-1' };
  attemptProgress.causation_id = 'attempt-source-0';
  attemptProgress.payload.work_ref = { kind: 'task', id: 'task-1' };
  attemptProgress.payload.source = {
    authority: 'executor',
    event_id: 'attempt-source-0',
    source_work_ref: { kind: 'attempt', id: 'attempt-1' },
    adapter: 'jiuwenswarm.executor',
  };
  assert.throws(
    () => parseEventEnvelope(attemptProgress),
    error => error instanceof ContractViolation && error.error.reason === 'PROGRESS_ATTEMPT_PARENT_UNVERIFIED'
  );
  const identities = new IdentityRegistry();
  const exactScope = parseScopeRef(fixture.scope);
  identities.register({ ref: { kind: 'task', id: 'task-1' }, scope: exactScope, parents: [], connection_epoch_ref: null });
  identities.register({
    ref: { kind: 'attempt', id: 'attempt-1' },
    scope: exactScope,
    parents: [{ kind: 'task', id: 'task-1' }],
    connection_epoch_ref: null,
  });
  const parsedAttemptProgress = parseEventEnvelope(attemptProgress, identities);
  assert.equal(parsedAttemptProgress.stream_ref.id, 'task-1');

  const attemptSource = clone(fixture.source_events[0]);
  attemptSource.event_id = 'attempt-source-0';
  attemptSource.event_type = 'attempt.accepted';
  attemptSource.producer = { component: 'task.executor', instance_id: 'executor-1', authority: 'executor' };
  attemptSource.stream_ref = { kind: 'attempt', id: 'attempt-1' };
  const attemptTracker = new EventSequenceTracker(identities);
  assert.equal(attemptTracker.accept(parseEventEnvelope(attemptSource, identities)).status, 'applied');
  assert.equal(attemptTracker.accept(parsedAttemptProgress).status, 'applied');
});

test('WorkProgress mixed authority streams do not invent a global source order', () => {
  const fixture = load('work_progress.v2.json');
  const exactScope = parseScopeRef(fixture.scope);
  const identities = new IdentityRegistry();
  const taskRef = { kind: 'task', id: 'task-mixed' };
  identities.register({ ref: taskRef, scope: exactScope, parents: [], connection_epoch_ref: null });
  for (const attemptId of ['attempt-mixed-1', 'attempt-mixed-2']) {
    identities.register({
      ref: { kind: 'attempt', id: attemptId },
      scope: exactScope,
      parents: [taskRef],
      connection_epoch_ref: null,
    });
  }
  const sourceEvent = ({ eventId, kind, refId, authority, instance }) => {
    const raw = clone(fixture.source_events[0]);
    raw.event_id = eventId;
    raw.event_type = `${kind}.accepted`;
    raw.producer = { component: `${kind}.runtime`, instance_id: instance, authority };
    raw.stream_ref = { kind, id: refId };
    return parseEventEnvelope(raw, identities);
  };
  const taskSource = sourceEvent({
    eventId: 'task-mixed-source',
    kind: 'task',
    refId: taskRef.id,
    authority: 'task_core',
    instance: 'task-core-1',
  });
  const attemptOne = sourceEvent({
    eventId: 'attempt-mixed-source-1',
    kind: 'attempt',
    refId: 'attempt-mixed-1',
    authority: 'executor',
    instance: 'executor-1',
  });
  const attemptTwo = sourceEvent({
    eventId: 'attempt-mixed-source-2',
    kind: 'attempt',
    refId: 'attempt-mixed-2',
    authority: 'executor',
    instance: 'executor-2',
  });
  const tracker = new EventSequenceTracker(identities);
  for (const source of [taskSource, attemptOne, attemptTwo]) assert.equal(tracker.accept(source).status, 'applied');

  const projection = (source, seq) => {
    const raw = clone(fixture.progress_events[0]);
    raw.event_id = `mixed-progress-${seq}`;
    raw.producer.instance_id = `mixed-bridge-${seq}`;
    raw.stream_ref = taskRef;
    raw.seq = 0;
    raw.causation_id = source.event_id;
    raw.payload.work_ref = taskRef;
    raw.payload.source = {
      authority: source.producer.authority,
      event_id: source.event_id,
      source_work_ref: source.stream_ref,
      adapter: 'mixed.authority.adapter',
    };
    raw.payload.seq = seq;
    return parseEventEnvelope(raw, identities);
  };
  for (const [seq, source] of [attemptTwo, taskSource, attemptOne].entries()) {
    assert.equal(tracker.accept(projection(source, seq)).status, 'applied');
  }
});

test('WorkProgress source order survives producer replacement', () => {
  const fixture = load('work_progress.v2.json');
  const source = ({ eventId, instance, eventType, cause }) => {
    const raw = clone(fixture.source_events[0]);
    raw.event_id = eventId;
    raw.producer.instance_id = instance;
    raw.event_type = eventType;
    raw.seq = 0;
    raw.causation_id = cause;
    raw.payload = { state: eventType.split('.', 2)[1] };
    return parseEventEnvelope(raw);
  };
  const accepted = source({
    eventId: 'round-replaced-accepted',
    instance: 'harness-before-restart',
    eventType: 'round.accepted',
    cause: null,
  });
  const running = source({
    eventId: 'round-replaced-running',
    instance: 'harness-after-restart',
    eventType: 'round.running',
    cause: accepted.event_id,
  });
  const tracker = new EventSequenceTracker();
  assert.equal(tracker.accept(accepted).status, 'applied');
  assert.equal(tracker.accept(running).status, 'applied');

  const projection = (source, { eventId, instance, progressSeq }) => {
    const raw = clone(fixture.progress_events[0]);
    raw.event_id = eventId;
    raw.producer.instance_id = instance;
    raw.seq = 0;
    raw.causation_id = source.event_id;
    raw.payload.source = {
      authority: source.producer.authority,
      event_id: source.event_id,
      source_work_ref: source.stream_ref,
      adapter: 'restarted.task-core.adapter',
    };
    raw.payload.state = source.payload.state;
    raw.payload.seq = progressSeq;
    return parseEventEnvelope(raw);
  };

  const reversed = tracker.accept(
    projection(running, {
      eventId: 'task-replaced-progress-running-early',
      instance: 'bridge-running-early',
      progressSeq: 0,
    })
  );
  assert.equal(reversed.status, 'rejected_projection');
  assert.equal(reversed.error.reason, 'PROGRESS_SOURCE_ORDER_MISMATCH');
  assert.equal(
    tracker.accept(
      projection(accepted, {
        eventId: 'task-replaced-progress-accepted',
        instance: 'bridge-accepted',
        progressSeq: 0,
      })
    ).status,
    'applied'
  );
  assert.equal(
    tracker.accept(
      projection(running, {
        eventId: 'task-replaced-progress-running',
        instance: 'bridge-running',
        progressSeq: 1,
      })
    ).status,
    'applied'
  );
});

test('shared invalid fixture rejects every indexed scenario with zero effects', () => {
  const { cases } = load('critical_kernel.invalid.json');
  assert.equal(new Set(cases.map(item => item.id)).size, cases.length);
  const fixture = load('critical_kernel.valid.json');
  const progressFixture = load('work_progress.v2.json');
  for (const scenario of cases) {
    let effects = 0;
    assert.throws(
      () => {
        if (scenario.change === 'context_refs_malformed') {
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
        } else if (scenario.change === 'context_uri_bom') {
          const raw = clone(progressFixture.context_refs[0]);
          raw.uri = 'urn:test:\ufeff';
          parseContextRef(raw);
        } else if (scenario.change === 'context_stable_id_bom_only') {
          const raw = clone(progressFixture.context_refs[0]);
          raw.stable_id = '\ufeff';
          parseContextRef(raw);
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

test('task.retry accepts only exact server-derived bounded predecessor facts', () => {
  const fixture = load('critical_kernel.valid.json');
  const retry = clone(fixture.command);
  retry.command_type = 'task.retry';
  retry.target_ref = { kind: 'task', id: 'task-1' };
  retry.required_capabilities = ['task.retry'];
  retry.payload = {
    previous_attempt_id: 'attempt-a',
    previous_outcome: 'cancelled',
    attempt_number: 2,
  };
  assert.deepEqual(parseCommandEnvelope(retry).payload, retry.payload);
  for (const payload of [
    { ...retry.payload, previous_attempt_id: '' },
    { ...retry.payload, previous_outcome: 'failed' },
    { ...retry.payload, attempt_number: 1 },
    { ...retry.payload, attempt_number: 4 },
    { ...retry.payload, context: {} },
  ]) {
    assert.throws(() => parseCommandEnvelope({ ...retry, payload }), ContractViolation);
  }
});

test('task.retry_accepted binds the applied command and opens only the next exact epoch', () => {
  const fixture = load('critical_kernel.valid.json');
  const commandRaw = clone(fixture.command);
  Object.assign(commandRaw, {
    request_id: 'request-retry-2',
    command_id: 'command-retry-2',
    command_type: 'task.retry',
    target_ref: { kind: 'task', id: 'task-1' },
    required_capabilities: ['task.retry'],
    payload: {
      previous_attempt_id: 'attempt-1',
      previous_outcome: 'completed',
      attempt_number: 2,
    },
  });
  const command = parseCommandEnvelope(commandRaw);
  const accepted = eventFrom(fixture, { eventId: 'task-a', seq: 0 });
  const terminalRaw = clone(fixture.event);
  Object.assign(terminalRaw, {
    event_id: 'task-a-terminal',
    event_type: 'task.terminal',
    seq: 1,
    causation_id: accepted.event_id,
    payload: { state: 'terminal', outcome: 'completed' },
  });
  const terminal = parseEventEnvelope(terminalRaw);
  const retryRaw = clone(fixture.event);
  Object.assign(retryRaw, {
    event_id: 'task-b',
    event_type: 'task.retry_accepted',
    seq: 2,
    causation_id: command.command_id,
    payload: {
      state: 'accepted',
      command_id: command.command_id,
      retry_of_attempt_id: 'attempt-1',
      previous_outcome: 'completed',
      attempt_number: 2,
    },
  });
  const retryEvent = parseEventEnvelope(retryRaw);
  const tracker = new EventSequenceTracker();
  assert.equal(tracker.accept(accepted).status, 'applied');
  assert.equal(tracker.accept(terminal).status, 'applied');
  tracker.registerAppliedCause(command);
  assert.equal(tracker.accept(retryEvent).status, 'applied');

  const causalTracker = new EventSequenceTracker();
  assert.equal(causalTracker.accept(accepted).status, 'applied');
  assert.equal(causalTracker.accept(terminal).status, 'applied');
  causalTracker.registerAppliedCause(command);
  const mismatchedCause = clone(retryRaw);
  mismatchedCause.event_id = 'task-b-mismatched-cause';
  mismatchedCause.payload.retry_of_attempt_id = 'attempt-other';
  const causalRejection = causalTracker.accept(parseEventEnvelope(mismatchedCause));
  assert.equal(causalRejection.status, 'rejected_causation');
  assert.equal(causalRejection.error.reason, 'TASK_RETRY_CAUSATION_MISMATCH');

  const wrongLineage = clone(retryRaw);
  Object.assign(wrongLineage, {
    event_id: 'task-c',
    seq: 3,
    causation_id: 'command-retry-3',
  });
  Object.assign(wrongLineage.payload, {
    command_id: 'command-retry-3',
    retry_of_attempt_id: 'attempt-2',
    attempt_number: 3,
  });
  const command3Raw = clone(commandRaw);
  Object.assign(command3Raw, { request_id: 'request-retry-3', command_id: 'command-retry-3' });
  Object.assign(command3Raw.payload, { previous_attempt_id: 'attempt-2', attempt_number: 3 });
  tracker.registerAppliedCause(parseCommandEnvelope(command3Raw));
  const rejected = tracker.accept(parseEventEnvelope(wrongLineage));
  assert.equal(rejected.status, 'rejected_lifecycle');
  assert.equal(rejected.error.reason, 'TASK_RETRY_PRECONDITION_STALE');

  const missingCommand = clone(retryRaw);
  delete missingCommand.payload.command_id;
  assert.throws(() => parseEventEnvelope(missingCommand), ContractViolation);
  const badCause = clone(retryRaw);
  badCause.causation_id = 'another-command';
  assert.throws(
    () => parseEventEnvelope(badCause),
    error => error instanceof ContractViolation && error.error.reason === 'TASK_RETRY_CAUSATION_MISMATCH',
  );

  const commandDrift = clone(retryRaw);
  commandDrift.event_id = 'task-b-command-drift';
  commandDrift.payload.command_id = 'another-command';
  const zeroEffectTracker = new EventSequenceTracker();
  assert.equal(zeroEffectTracker.accept(accepted).status, 'applied');
  assert.equal(zeroEffectTracker.accept(terminal).status, 'applied');
  zeroEffectTracker.registerAppliedCause(command);
  assert.throws(() => parseEventEnvelope(commandDrift), ContractViolation);
  assert.equal(zeroEffectTracker.accept(retryEvent).status, 'applied');
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
