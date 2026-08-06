import assert from 'node:assert/strict';
import test from 'node:test';

import {
  adoptProductTextProgressEvent,
  parseProductTextProgressEvent,
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
