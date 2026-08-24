import assert from 'node:assert/strict';
import test from 'node:test';

import {
  adoptProductTextProgressEvent,
  adoptParsedProductTextProgressEvent,
  createProductTextProgressDeliveryAck,
  parseProductTextProgressEvent,
  ProductTextProgressAckOwner,
  ProductTextProgressDomAdoptionOwner,
  productTextProgressPresentationBinding,
} from '../node_modules/.cache/live-voice-integrated-web/features/live-voice/formal/productTextProgress.js';

function progressEvent(overrides = {}) {
  const sessionId = overrides.session_id ?? 'session-1';
  const projectId = overrides.project_id ?? 'project-1';
  const taskId = overrides.task_id ?? 'task-1';
  const correlationId = overrides.correlation_id ?? 'correlation-1';
  const seq = overrides.seq ?? 7;
  const attemptId = overrides.attempt_id ?? 'attempt-1';
  const eventType = overrides.event_type ?? 'task.running';
  const state = overrides.state ?? 'running';
  const outcome = overrides.outcome ?? null;
  const persistentSourceEventId =
    overrides.persistent_source_event_id ?? (outcome === 'completed' ? `executor-${seq}` : null);
  const sourceId = `source-${seq}`;
  const scope = {
    subject_id: overrides.subject_id ?? 'principal-1',
    session_id: sessionId,
    project_id: projectId,
    assurance: overrides.assurance ?? 'authenticated',
  };
  return {
    event_type: 'live_voice.task.progress',
    delivery_id: overrides.delivery_id ?? `delivery-${seq}`,
    session_id: sessionId,
    project_id: projectId,
    task_id: taskId,
    correlation_id: correlationId,
    origin_id: 'web-surface-1',
    origin_kind: overrides.origin_kind ?? 'text',
    requested_origin_kind: overrides.requested_origin_kind ?? overrides.origin_kind ?? 'text',
    effective_origin_kind: 'text',
    delivery_mode: overrides.delivery_mode ?? 'text',
    fallback_reason: overrides.fallback_reason ?? null,
    generation_kind: 'web_task_progress_generation',
    generation_id: 'web-generation-1',
    generation: overrides.generation ?? 1,
    evidence_id: `evidence-${seq}`,
    presentation_class: 'text',
    response_ref: {
      interaction_id: 'interaction-progress-1',
      response_id: `response-progress-${seq}`,
      response_generation: overrides.response_generation ?? 1,
    },
    unit_id: `unit-progress-${seq}`,
    expected_event_head: overrides.expected_event_head ?? seq,
    result_source_event_id:
      overrides.result_source_event_id === undefined
        ? outcome === 'completed'
          ? persistentSourceEventId
          : null
        : overrides.result_source_event_id,
    state,
    source_event: {
      event_id: sourceId,
      event_type: eventType,
      seq,
      correlation_id: correlationId,
      causation_id: 'cause-1',
      stream_ref: { kind: 'task', id: taskId },
      scope: { ...scope },
      payload: outcome === null ? { state } : { state, outcome },
      extensions: {
        'jiuwenswarm.task_progress_return': {
          persistent_event_seq: seq,
          persistent_event_type: eventType,
          persistent_event_producer: 'task_core',
          persistent_attempt_id: attemptId,
          persistent_source_event_id: persistentSourceEventId,
        },
      },
    },
    progress_event: {
      event_id: `progress-${seq}`,
      event_type: 'work.progress',
      seq,
      correlation_id: correlationId,
      causation_id: sourceId,
      stream_ref: { kind: 'task', id: taskId },
      scope: { ...scope },
      payload: {
        work_ref: { kind: 'task', id: taskId },
        seq,
        state,
        ...(outcome === null ? {} : { outcome }),
      },
    },
  };
}

function legacyProgressEvent(overrides = {}) {
  const event = progressEvent(overrides);
  delete event.presentation_class;
  delete event.response_ref;
  delete event.unit_id;
  delete event.expected_event_head;
  delete event.result_source_event_id;
  delete event.state;
  return event;
}

test('accepts the exact production presentation state binding', () => {
  const parsed = parseProductTextProgressEvent(progressEvent({ state: 'running' }));
  assert.notEqual(parsed, null);
  assert.equal(parsed.state, 'running');

  const mismatched = progressEvent({ state: 'running' });
  mismatched.state = 'waiting';
  assert.equal(parseProductTextProgressEvent(mismatched), null);
});

test('DOM adoption owner ACKs only an exact connected rendered delivery', () => {
  const parsed = parseProductTextProgressEvent(progressEvent());
  assert.notEqual(parsed, null);
  const retained = [];
  const ackOwner = {
    retain: event => {
      retained.push(event);
      return { status: 'pending' };
    },
  };
  const owner = new ProductTextProgressDomAdoptionOwner(ackOwner);
  const node = {
    isConnected: true,
    getAttribute(name) {
      return {
        'data-presentation-binding': productTextProgressPresentationBinding(parsed),
        'data-delivery-id': parsed.delivery_id,
        'data-session-id': parsed.session_id,
        'data-subject-id': parsed.source_event.scope.subject_id,
        'data-project-id': parsed.project_id,
        'data-task-id': parsed.task_id,
        'data-attempt-id': parsed.attempt_id,
        'data-event-id': parsed.source_event.event_id,
        'data-event-seq': String(parsed.source_event.seq),
        'data-generation-id': parsed.generation_id,
        'data-generation': String(parsed.generation),
        'data-presentation-class': parsed.presentation_class,
        'data-response-interaction-id': parsed.response_ref.interaction_id,
        'data-response-id': parsed.response_ref.response_id,
        'data-response-generation': String(parsed.response_ref.response_generation),
        'data-unit-id': parsed.unit_id,
        'data-expected-event-head': String(parsed.expected_event_head),
        'data-result-source-event-id': parsed.result_source_event_id ?? '',
      }[name] ?? null;
    },
  };

  assert.deepEqual(owner.adopt(parsed, { ...node, isConnected: false }), null);
  assert.deepEqual(retained, []);
  assert.throws(
    () => owner.adopt(parsed, { ...node, getAttribute: name => (name === 'data-task-id' ? 'task-foreign' : node.getAttribute(name)) }),
    /DOM presentation binding mismatch/,
  );
  const changedEvidenceRaw = progressEvent();
  changedEvidenceRaw.state = 'waiting';
  changedEvidenceRaw.source_event.payload.state = 'waiting';
  changedEvidenceRaw.progress_event.payload.state = 'waiting';
  const changedEvidence = parseProductTextProgressEvent(changedEvidenceRaw);
  assert.notEqual(changedEvidence, null);
  assert.throws(
    () => owner.adopt(changedEvidence, node),
    /DOM presentation binding mismatch/,
  );
  assert.deepEqual(retained, []);
  assert.deepEqual(owner.adopt(parsed, node), { status: 'pending' });
  assert.deepEqual(retained, [parsed]);
});

test('parses an exact session/task/correlation/causation progress binding', () => {
  const parsed = parseProductTextProgressEvent(progressEvent());

  assert.equal(parsed?.task_id, 'task-1');
  assert.equal(parsed?.state, 'running');
  assert.equal(parsed?.source_event.seq, 7);
  assert.equal(parsed?.attempt_id, 'attempt-1');
  assert.equal(Object.isFrozen(parsed), true);
});

test('adopts an already parsed exact event without weakening raw-envelope parsing', () => {
  const parsed = parseProductTextProgressEvent(progressEvent());
  assert.notEqual(parsed, null);

  assert.equal(adoptProductTextProgressEvent(null, parsed, 'session-1'), null);
  assert.equal(adoptParsedProductTextProgressEvent(null, parsed, 'session-1'), parsed);
  assert.equal(adoptParsedProductTextProgressEvent(null, parsed, 'session-foreign'), null);
});

test('creates an exact credential-free Web UI delivery acknowledgement', () => {
  const parsed = parseProductTextProgressEvent(progressEvent());
  assert.notEqual(parsed, null);

  assert.deepEqual(createProductTextProgressDeliveryAck(parsed), {
    session_id: 'session-1',
    task_id: 'task-1',
    correlation_id: 'correlation-1',
    origin_id: 'web-surface-1',
    generation_id: 'web-generation-1',
    generation: 1,
    delivery_id: 'delivery-7',
    source_event_id: 'source-7',
    progress_event_id: 'progress-7',
    seq: 7,
    evidence_id: 'evidence-7',
    presentation_class: 'text',
    response_ref: {
      interaction_id: 'interaction-progress-1',
      response_id: 'response-progress-7',
      response_generation: 1,
    },
    unit_id: 'unit-progress-7',
    expected_event_head: 7,
    result_source_event_id: null,
    presentation_binding: createProductTextProgressDeliveryAck(parsed).presentation_binding,
  });
  assert.equal('auth_token' in createProductTextProgressDeliveryAck(parsed), false);
});

test('feature-off legacy progress keeps exact DOM adoption and never acquires presentation authority', async () => {
  const parsed = parseProductTextProgressEvent(legacyProgressEvent());
  assert.notEqual(parsed, null);
  assert.equal(parsed.consumption_mode, 'legacy_delivery');
  assert.equal(parsed.presentation_class, null);
  assert.equal(parsed.response_ref, null);
  assert.equal(parsed.unit_id, null);
  assert.equal(parsed.expected_event_head, null);
  const ack = createProductTextProgressDeliveryAck(parsed);
  assert.deepEqual(ack, {
    session_id: 'session-1',
    task_id: 'task-1',
    correlation_id: 'correlation-1',
    origin_id: 'web-surface-1',
    generation_id: 'web-generation-1',
    generation: 1,
    delivery_id: 'delivery-7',
    source_event_id: 'source-7',
    progress_event_id: 'progress-7',
    seq: 7,
    evidence_id: 'evidence-7',
  });
  for (const forbidden of [
    'presentation_class',
    'response_ref',
    'unit_id',
    'expected_event_head',
    'result_source_event_id',
    'presentation_binding',
  ]) {
    assert.equal(forbidden in ack, false, forbidden);
  }

  const retained = [];
  const domOwner = new ProductTextProgressDomAdoptionOwner({
    retain: event => {
      retained.push(event);
      return { status: 'pending' };
    },
  });
  const attributes = {
    'data-delivery-id': parsed.delivery_id,
    'data-session-id': parsed.session_id,
    'data-subject-id': parsed.source_event.scope.subject_id,
    'data-project-id': parsed.project_id,
    'data-task-id': parsed.task_id,
    'data-attempt-id': parsed.attempt_id,
    'data-event-id': parsed.source_event.event_id,
    'data-event-seq': String(parsed.source_event.seq),
    'data-generation-id': parsed.generation_id,
    'data-generation': String(parsed.generation),
  };
  const legacyNode = {
    isConnected: true,
    getAttribute: name => attributes[name] ?? null,
  };
  assert.deepEqual(domOwner.adopt(parsed, legacyNode), { status: 'pending' });
  assert.deepEqual(retained, [parsed]);
  assert.throws(
    () =>
      domOwner.adopt(parsed, {
        ...legacyNode,
        getAttribute: name => (name === 'data-presentation-binding' ? productTextProgressPresentationBinding(parsed) : legacyNode.getAttribute(name)),
      }),
    /legacy DOM acquired presentation authority/,
  );

  const calls = [];
  const owner = new ProductTextProgressAckOwner({
    enabled: true,
    retry_delay_ms: 1000,
    request: async (_method, params) => {
      calls.push(params);
      return {
        ok: true,
        result: {
          status: 'acknowledged',
          replayed: false,
          attempt_id: 'attempt-1',
          ...params,
          acknowledgement: 'web_ui_text_consumed',
        },
      };
    },
  });
  owner.setConnected(true);
  owner.retain(parsed);
  for (let attempt = 0; attempt < 50 && owner.status(parsed.delivery_id)?.status !== 'acknowledged'; attempt += 1) {
    await new Promise(resolve => setTimeout(resolve, 1));
  }
  assert.equal(owner.status(parsed.delivery_id)?.status, 'acknowledged');
  assert.deepEqual(calls, [ack]);
  owner.close();
});

test('rejects correlation, task, canonical scope, and causation mismatches', () => {
  for (const mutate of [
    event => {
      event.progress_event.correlation_id = 'wrong-correlation';
    },
    event => {
      event.progress_event.stream_ref.id = 'wrong-task';
    },
    event => {
      event.source_event.scope.session_id = 'wrong-session';
    },
    event => {
      event.progress_event.scope.subject_id = 'wrong-principal';
    },
    event => {
      event.source_event.scope.assurance = 'request_asserted';
    },
    event => {
      delete event.source_event.scope.subject_id;
    },
    event => {
      event.source_event.scope.extra = 'unknown';
    },
    event => {
      event.progress_event.causation_id = 'wrong-source';
    },
    event => {
      event.source_event.extensions['jiuwenswarm.task_progress_return'].persistent_event_seq = 8;
    },
    event => {
      delete event.source_event.extensions['jiuwenswarm.task_progress_return'].persistent_attempt_id;
    },
  ]) {
    const event = progressEvent();
    mutate(event);
    assert.equal(parseProductTextProgressEvent(event), null);
  }
});

test('rejects every unknown top-level or envelope key', () => {
  for (const mutate of [
    event => {
      event.unknown = true;
    },
    event => {
      event.source_event.unknown = true;
    },
    event => {
      event.progress_event.unknown = true;
    },
    event => {
      event.response_ref.unknown = true;
    },
    event => {
      event.source_event.stream_ref.unknown = true;
    },
  ]) {
    const event = progressEvent();
    mutate(event);
    assert.equal(parseProductTextProgressEvent(event), null);
  }
});

test('accepts only the exact legal terminal result binding', () => {
  const completed = progressEvent({
    event_type: 'task.terminal',
    state: 'terminal',
    outcome: 'completed',
  });
  assert.notEqual(parseProductTextProgressEvent(completed), null);
  for (const mutate of [
    event => {
      event.result_source_event_id = null;
    },
    event => {
      event.result_source_event_id = 'executor-foreign';
    },
    event => {
      event.progress_event.payload.outcome = 'failed';
    },
    event => {
      event.source_event.payload.state = 'running';
    },
    event => {
      event.state = 'running';
    },
  ]) {
    const event = structuredClone(completed);
    mutate(event);
    assert.equal(parseProductTextProgressEvent(event), null);
  }

  for (const outcome of ['failed', 'cancelled', 'interrupted', 'unknown']) {
    const legal = progressEvent({
      event_type: 'task.terminal',
      state: 'terminal',
      outcome,
    });
    assert.notEqual(parseProductTextProgressEvent(legal), null);
    legal.result_source_event_id = `forged-result-${outcome}`;
    assert.equal(parseProductTextProgressEvent(legal), null);
  }
});

test('adoption retains exact scope and binding within one generation', () => {
  const initial = adoptProductTextProgressEvent(null, progressEvent(), 'session-1');
  const duplicate = adoptProductTextProgressEvent(initial, progressEvent(), 'session-1');
  const newer = adoptProductTextProgressEvent(initial, progressEvent({ seq: 8, state: 'waiting' }), 'session-1');
  const staleGeneration = adoptProductTextProgressEvent(newer, progressEvent({ seq: 9, generation: 0 }), 'session-1');
  const wrongSession = adoptProductTextProgressEvent(newer, progressEvent({ session_id: 'session-2', seq: 10 }), 'session-1');
  const changedCorrelation = adoptProductTextProgressEvent(newer, progressEvent({ correlation_id: 'correlation-2', seq: 10 }), 'session-1');
  const changedProject = adoptProductTextProgressEvent(newer, progressEvent({ project_id: 'project-2', seq: 10 }), 'session-1');
  const changedSubject = adoptProductTextProgressEvent(newer, progressEvent({ subject_id: 'principal-2', seq: 10 }), 'session-1');
  const changedGenerationKind = progressEvent({ seq: 10 });
  changedGenerationKind.generation_kind = 'other-generation-kind';

  assert.equal(duplicate, initial);
  assert.equal(newer?.source_event.seq, 8);
  assert.equal(newer?.state, 'waiting');
  assert.equal(staleGeneration, newer);
  assert.equal(wrongSession, newer);
  assert.equal(changedCorrelation, newer);
  assert.equal(changedProject, newer);
  assert.equal(changedSubject, newer);
  assert.equal(adoptProductTextProgressEvent(newer, changedGenerationKind, 'session-1'), newer);
});

test('a higher generation explicitly replaces correlation within one lineage', () => {
  const initial = adoptProductTextProgressEvent(null, progressEvent(), 'session-1');
  const replacement = adoptProductTextProgressEvent(initial, progressEvent({ generation: 2, correlation_id: 'correlation-2', seq: 1 }), 'session-1');

  assert.notEqual(replacement, initial);
  assert.equal(replacement?.generation, 2);
  assert.equal(replacement?.correlation_id, 'correlation-2');
});

test('retained ACK owner retries the identical delivery after response loss', async () => {
  const parsed = parseProductTextProgressEvent(progressEvent());
  assert.notEqual(parsed, null);
  const calls = [];
  const snapshots = [];
  const owner = new ProductTextProgressAckOwner({
    enabled: true,
    retry_delay_ms: 0,
    request: async (method, params) => {
      calls.push([method, params]);
      if (calls.length === 1) throw new Error('response lost after server ACK');
      return {
        ok: true,
        result: {
          status: 'acknowledged',
          replayed: true,
          attempt_id: 'attempt-1',
          ...params,
          acknowledgement: 'web_ui_text_consumed',
        },
      };
    },
    on_snapshot: snapshot => snapshots.push(snapshot),
  });
  owner.setConnected(true);
  owner.retain(parsed);
  for (let attempt = 0; attempt < 50 && owner.status(parsed.delivery_id)?.status !== 'acknowledged'; attempt += 1) {
    await new Promise(resolve => setTimeout(resolve, 1));
  }

  assert.equal(owner.status(parsed.delivery_id)?.status, 'acknowledged');
  assert.equal(owner.status(parsed.delivery_id)?.attempts, 2);
  assert.deepEqual(calls[0], calls[1]);
  assert.equal(
    snapshots.some(item => item.status === 'failed'),
    true
  );
  owner.close();
});

test('ACK owner retains every delivery and retries them on reconnect', async () => {
  const first = parseProductTextProgressEvent(progressEvent({ seq: 7 }));
  const second = parseProductTextProgressEvent(progressEvent({ seq: 8 }));
  assert.notEqual(first, null);
  assert.notEqual(second, null);
  const calls = [];
  const owner = new ProductTextProgressAckOwner({
    enabled: true,
    retry_delay_ms: 1000,
    request: async (_method, params) => {
      calls.push(params.delivery_id);
      return {
        ok: true,
        result: {
          status: 'acknowledged',
          replayed: false,
          attempt_id: 'attempt-1',
          ...params,
          acknowledgement: 'web_ui_text_consumed',
        },
      };
    },
  });
  owner.retain(first);
  owner.retain(second);
  assert.equal(owner.status(first.delivery_id)?.status, 'failed');
  assert.equal(owner.status(second.delivery_id)?.status, 'failed');

  owner.setConnected(true);
  for (let attempt = 0; attempt < 50 && calls.length !== 2; attempt += 1) {
    await new Promise(resolve => setTimeout(resolve, 1));
  }
  assert.deepEqual(calls.sort(), [first.delivery_id, second.delivery_id].sort());
  assert.equal(owner.status(first.delivery_id)?.status, 'acknowledged');
  assert.equal(owner.status(second.delivery_id)?.status, 'acknowledged');
  owner.close();
});

test('ACK owner rejects a success response without server-owned attempt identity', async () => {
  const parsed = parseProductTextProgressEvent(progressEvent());
  assert.notEqual(parsed, null);
  const owner = new ProductTextProgressAckOwner({
    enabled: true,
    retry_delay_ms: 1000,
    request: async (_method, params) => ({
      ok: true,
      result: {
        status: 'acknowledged',
        replayed: false,
        ...params,
        acknowledgement: 'web_ui_text_consumed',
      },
    }),
  });
  owner.setConnected(true);
  owner.retain(parsed);
  for (let attempt = 0; attempt < 50 && owner.status(parsed.delivery_id)?.status === 'pending'; attempt += 1) {
    await new Promise(resolve => setTimeout(resolve, 1));
  }

  assert.equal(owner.status(parsed.delivery_id)?.status, 'failed');
  owner.close();
});

test('ACK owner rejects a foreign server attempt without reporting it in request params', async () => {
  const parsed = parseProductTextProgressEvent(progressEvent({ attempt_id: 'attempt-authoritative' }));
  assert.notEqual(parsed, null);
  const calls = [];
  const owner = new ProductTextProgressAckOwner({
    enabled: true,
    retry_delay_ms: 1000,
    request: async (_method, params) => {
      calls.push(params);
      return {
        ok: true,
        result: {
          status: 'acknowledged',
          replayed: false,
          attempt_id: 'attempt-foreign',
          ...params,
          acknowledgement: 'web_ui_text_consumed',
        },
      };
    },
  });
  owner.setConnected(true);
  owner.retain(parsed);
  for (let attempt = 0; attempt < 50 && owner.status(parsed.delivery_id)?.status === 'pending'; attempt += 1) {
    await new Promise(resolve => setTimeout(resolve, 1));
  }

  assert.equal(owner.status(parsed.delivery_id)?.status, 'failed');
  assert.equal(calls.length, 1);
  assert.equal('attempt_id' in calls[0], false);
  owner.close();
});

test('ACK owner rejects a retained delivery whose source attempt changes', () => {
  const first = parseProductTextProgressEvent(progressEvent({ attempt_id: 'attempt-1' }));
  const foreign = parseProductTextProgressEvent(progressEvent({ attempt_id: 'attempt-foreign' }));
  assert.notEqual(first, null);
  assert.notEqual(foreign, null);
  const owner = new ProductTextProgressAckOwner({
    enabled: true,
    request: async () => {
      throw new Error('offline');
    },
  });

  owner.retain(first);
  assert.throws(() => owner.retain(foreign), /delivery_id binding conflict/);
  assert.equal(owner.status(first.delivery_id)?.retained_deliveries, 1);
  owner.close();
});

test('ACK capacity never evicts an unacknowledged delivery', () => {
  const first = parseProductTextProgressEvent(progressEvent({ seq: 7 }));
  const second = parseProductTextProgressEvent(progressEvent({ seq: 8 }));
  assert.notEqual(first, null);
  assert.notEqual(second, null);
  const owner = new ProductTextProgressAckOwner({
    enabled: true,
    capacity: 1,
    request: async () => {
      throw new Error('offline');
    },
  });
  owner.retain(first);
  assert.throws(() => owner.retain(second), /no safe eviction/);
  assert.equal(owner.status(first.delivery_id)?.retained_deliveries, 1);
  assert.equal(owner.status(second.delivery_id), null);
  owner.close();
});

test('closing an ACK owner fences a late request completion callback', async () => {
  const parsed = parseProductTextProgressEvent(progressEvent());
  assert.notEqual(parsed, null);
  const snapshots = [];
  let resolveRequest;
  const request = new Promise(resolve => {
    resolveRequest = resolve;
  });
  const owner = new ProductTextProgressAckOwner({
    enabled: true,
    request: async () => request,
    on_snapshot: snapshot => snapshots.push(snapshot),
  });
  owner.setConnected(true);
  owner.retain(parsed);
  await Promise.resolve();
  const snapshotCountAtClose = snapshots.length;

  owner.close();
  resolveRequest({
    ok: true,
    result: {
      status: 'acknowledged',
      replayed: false,
      attempt_id: 'attempt-1',
      ...createProductTextProgressDeliveryAck(parsed),
      acknowledgement: 'web_ui_text_consumed',
    },
  });
  await request;
  await new Promise(resolve => setTimeout(resolve, 0));

  assert.equal(snapshots.length, snapshotCountAtClose);
  assert.equal(owner.status(parsed.delivery_id), null);
});
