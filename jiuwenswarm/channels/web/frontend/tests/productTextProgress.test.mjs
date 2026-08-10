import assert from 'node:assert/strict';
import test from 'node:test';

import {
  adoptProductTextProgressEvent,
  createProductTextProgressDeliveryAck,
  parseProductTextProgressEvent,
  ProductTextProgressAckOwner,
} from '../node_modules/.cache/live-voice-integrated-web/features/live-voice/formal/productTextProgress.js';

function progressEvent(overrides = {}) {
  const sessionId = overrides.session_id ?? 'session-1';
  const projectId = overrides.project_id ?? 'project-1';
  const taskId = overrides.task_id ?? 'task-1';
  const correlationId = overrides.correlation_id ?? 'correlation-1';
  const seq = overrides.seq ?? 7;
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
    generation_kind: 'web_task_progress_generation',
    generation_id: 'web-generation-1',
    generation: overrides.generation ?? 1,
    evidence_id: `evidence-${seq}`,
    source_event: {
      event_id: sourceId,
      event_type: 'task.running',
      seq,
      correlation_id: correlationId,
      causation_id: 'cause-1',
      stream_ref: { kind: 'task', id: taskId },
      scope: { ...scope },
      payload: { state: 'running' },
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
        state: overrides.state ?? 'running',
      },
    },
  };
}

test('parses an exact session/task/correlation/causation progress binding', () => {
  const parsed = parseProductTextProgressEvent(progressEvent());

  assert.equal(parsed?.task_id, 'task-1');
  assert.equal(parsed?.state, 'running');
  assert.equal(parsed?.source_event.seq, 7);
  assert.equal(Object.isFrozen(parsed), true);
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
  });
  assert.equal('auth_token' in createProductTextProgressDeliveryAck(parsed), false);
});

test('rejects correlation, task, canonical scope, and causation mismatches', () => {
  for (const mutate of [
    event => { event.progress_event.correlation_id = 'wrong-correlation'; },
    event => { event.progress_event.stream_ref.id = 'wrong-task'; },
    event => { event.source_event.scope.session_id = 'wrong-session'; },
    event => { event.progress_event.scope.subject_id = 'wrong-principal'; },
    event => { event.source_event.scope.assurance = 'request_asserted'; },
    event => { delete event.source_event.scope.subject_id; },
    event => { event.source_event.scope.extra = 'unknown'; },
    event => { event.progress_event.causation_id = 'wrong-source'; },
  ]) {
    const event = progressEvent();
    mutate(event);
    assert.equal(parseProductTextProgressEvent(event), null);
  }
});

test('adoption retains exact scope and binding within one generation', () => {
  const initial = adoptProductTextProgressEvent(null, progressEvent(), 'session-1');
  const duplicate = adoptProductTextProgressEvent(initial, progressEvent(), 'session-1');
  const newer = adoptProductTextProgressEvent(
    initial,
    progressEvent({ seq: 8, state: 'waiting' }),
    'session-1'
  );
  const staleGeneration = adoptProductTextProgressEvent(
    newer,
    progressEvent({ seq: 9, generation: 0 }),
    'session-1'
  );
  const wrongSession = adoptProductTextProgressEvent(
    newer,
    progressEvent({ session_id: 'session-2', seq: 10 }),
    'session-1'
  );
  const changedCorrelation = adoptProductTextProgressEvent(
    newer,
    progressEvent({ correlation_id: 'correlation-2', seq: 10 }),
    'session-1'
  );
  const changedProject = adoptProductTextProgressEvent(
    newer,
    progressEvent({ project_id: 'project-2', seq: 10 }),
    'session-1'
  );
  const changedSubject = adoptProductTextProgressEvent(
    newer,
    progressEvent({ subject_id: 'principal-2', seq: 10 }),
    'session-1'
  );
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
  assert.equal(
    adoptProductTextProgressEvent(newer, changedGenerationKind, 'session-1'),
    newer
  );
});

test('a higher generation explicitly replaces correlation within one lineage', () => {
  const initial = adoptProductTextProgressEvent(null, progressEvent(), 'session-1');
  const replacement = adoptProductTextProgressEvent(
    initial,
    progressEvent({ generation: 2, correlation_id: 'correlation-2', seq: 1 }),
    'session-1'
  );

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
  assert.equal(snapshots.some(item => item.status === 'failed'), true);
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

test('ACK capacity never evicts an unacknowledged delivery', () => {
  const first = parseProductTextProgressEvent(progressEvent({ seq: 7 }));
  const second = parseProductTextProgressEvent(progressEvent({ seq: 8 }));
  assert.notEqual(first, null);
  assert.notEqual(second, null);
  const owner = new ProductTextProgressAckOwner({
    enabled: true,
    capacity: 1,
    request: async () => { throw new Error('offline'); },
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
