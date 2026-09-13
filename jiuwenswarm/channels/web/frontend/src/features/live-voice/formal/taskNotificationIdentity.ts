/** Display identity only. It never grants presentation or Task consumption. */
export interface TaskNotificationDisplay {
  eventKey: string;
  presentation: 'preview' | 'text';
}

export function coalesceTaskNotifications<T extends { taskNotification?: TaskNotificationDisplay; renderKey?: string }>(messages: readonly T[]): T[] {
  const events = new Map<string, number>();
  const result: T[] = [];
  for (const message of messages) {
    const key = message.taskNotification?.eventKey;
    const priorIndex = key ? events.get(key) : undefined;
    if (priorIndex === undefined) {
      if (key) events.set(key, result.length);
      result.push(message);
    } else if (result[priorIndex].taskNotification?.presentation !== 'text' && message.taskNotification?.presentation === 'text') {
      const renderKey = result[priorIndex].renderKey;
      result[priorIndex] = renderKey ? { ...message, renderKey } : message;
    }
  }
  return result;
}

const record = (value: unknown): Record<string, unknown> | null =>
  value !== null && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : null;
const identity = (value: unknown): value is string => typeof value === 'string' &&
  value.length > 0 && value.length <= 256 && value.trim() === value && !/[\u0000-\u001f\u007f]/u.test(value);

export function taskNotificationBindingKey(value: unknown, sessionId: string): string | null {
  const binding = record(value);
  const scope = record(binding?.scope);
  if (!binding || !scope || Object.keys(binding).sort().join(',') !== 'attempt_id,event_id,scope,task_id' ||
      Object.keys(scope).sort().join(',') !== 'assurance,project_id,session_id,subject_id' ||
      scope.assurance !== 'authenticated' || scope.session_id !== sessionId ||
      ![scope.subject_id, scope.project_id, scope.session_id, binding.task_id, binding.attempt_id, binding.event_id].every(identity)) return null;
  return JSON.stringify([scope.subject_id, scope.project_id, scope.session_id, scope.assurance,
    binding.task_id, binding.attempt_id, binding.event_id]);
}

export function taskNotificationSourceKey(source: unknown, sessionId: string): string | null {
  const event = record(source);
  const stream = record(event?.stream_ref);
  const progress = record(record(event?.extensions)?.['jiuwenswarm.task_progress_return']);
  if (!event || stream?.kind !== 'task') return null;
  return taskNotificationBindingKey({ scope: event.scope, task_id: stream.id,
    attempt_id: progress?.persistent_attempt_id, event_id: event.event_id }, sessionId);
}
