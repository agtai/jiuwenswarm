// Test-side authoritative-event fixture. State is supplied explicitly, never
// inferred from the notification's human-language presentation.
export function taskNotificationSource(sessionId, taskId, state = 'terminal') {
  return {
    contract_version: 'live-voice.contract.v2',
    producer: { component: 'test-task-core', instance_id: 'test-core-instance', authority: 'task_core' },
    occurred_at: '2026-09-03T10:00:00Z', required_capabilities: [], extensions: {},
    event_id: `${taskId}-${state}-event`, event_type: `task.${state}`, seq: 1,
    correlation_id: `${taskId}-correlation`, causation_id: null,
    stream_ref: { kind: 'task', id: taskId },
    scope: { subject_id: 'test-subject', project_id: 'test-project', session_id: sessionId, assurance: 'authenticated' },
    payload: { state, ...(state === 'terminal' ? { outcome: 'completed' } : {}) },
  };
}
