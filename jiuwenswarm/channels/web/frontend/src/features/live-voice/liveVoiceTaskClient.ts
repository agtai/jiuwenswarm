import { LIVE_VOICE_AUTO_HARNESS_PIPELINE, type LiveVoiceTaskGateway } from './liveVoiceTaskBridge';

export const LIVE_VOICE_TASK_ORIGIN_NAMESPACE = 'live_voice' as const;

export type LiveVoiceTaskRequest = (
  method: string,
  params?: Record<string, unknown>,
  options?: { signal?: AbortSignal }
) => Promise<unknown>;

export interface LiveVoiceTaskExecutionContext {
  /** Absolute project path captured from the persisted chat session. */
  projectDir: string;
  /** Stable project registry identity when the session provides one. */
  projectId: string | null;
}

export interface LiveVoiceTaskPersistedSessionContext {
  sessionId: string;
  projectDir: string | null | undefined;
  projectId: string | null | undefined;
}

export interface LiveVoiceTaskRegisteredProjectContext {
  projectDir: string | null | undefined;
  projectId: string | null | undefined;
}

export interface LiveVoiceTaskClientOptions {
  request: LiveVoiceTaskRequest;
  sessionId: string;
  executionContext: LiveVoiceTaskExecutionContext;
}

function requireRunnableSessionId(sessionId: string): string {
  const normalized = sessionId.trim();
  if (!normalized || normalized === 'new') {
    throw new Error('Live Voice task commands require a persisted session_id');
  }
  return normalized;
}

function isAbsoluteProjectDir(projectDir: string): boolean {
  return /^(?:[a-z]:[\\/]|\\\\|\/)/iu.test(projectDir);
}

/**
 * Normalize only an explicitly supplied persisted-session target. This helper
 * never falls back to cwd, the selected composer project, or another session.
 */
export function normalizeLiveVoiceTaskExecutionContext(
  projectDir: unknown,
  projectId: unknown
): LiveVoiceTaskExecutionContext | null {
  const normalizedProjectDir = typeof projectDir === 'string' ? projectDir.trim() : '';
  if (!normalizedProjectDir || !isAbsoluteProjectDir(normalizedProjectDir)) {
    return null;
  }
  const normalizedProjectId = typeof projectId === 'string' && projectId.trim() ? projectId.trim() : null;
  return {
    projectDir: normalizedProjectDir,
    projectId: normalizedProjectId,
  };
}

/**
 * Resolve an execution target from one persisted active session. A registered
 * project may supply a missing path only when its stable ID exactly matches
 * that session (including an explicitly configured default project).
 */
export function resolveLiveVoiceTaskExecutionContext(
  activeSessionId: string | null,
  session: LiveVoiceTaskPersistedSessionContext | null,
  registeredProject: LiveVoiceTaskRegisteredProjectContext | null
): LiveVoiceTaskExecutionContext | null {
  const normalizedActiveSessionId = activeSessionId?.trim() ?? '';
  if (!normalizedActiveSessionId || normalizedActiveSessionId === 'new' || session?.sessionId.trim() !== normalizedActiveSessionId) {
    return null;
  }

  const sessionProjectId = typeof session.projectId === 'string' && session.projectId.trim() ? session.projectId.trim() : null;
  const registeredProjectId =
    typeof registeredProject?.projectId === 'string' && registeredProject.projectId.trim() ? registeredProject.projectId.trim() : null;
  const matchingRegisteredProject = Boolean(sessionProjectId && registeredProjectId === sessionProjectId);
  return normalizeLiveVoiceTaskExecutionContext(
    session.projectDir || (matchingRegisteredProject ? registeredProject?.projectDir : null),
    sessionProjectId
  );
}

export function liveVoiceTaskExecutionContextKey(context: LiveVoiceTaskExecutionContext | null | undefined): string | null {
  return context ? JSON.stringify([context.projectDir, context.projectId]) : null;
}

/**
 * Narrow Web request adapter for the Post-V0 task demo.
 *
 * The adapter deliberately exposes only the four operations used by
 * LiveVoiceTaskBridge. It always pins AutoHarness mode and the reviewed
 * side-effecting pipeline; response payloads are returned untouched so the
 * bridge, not this transport layer, decides whether a task really started,
 * stopped, or completed.
 */
export function createLiveVoiceTaskGateway({ request, sessionId, executionContext }: LiveVoiceTaskClientOptions): LiveVoiceTaskGateway {
  const normalizedExecutionContext = normalizeLiveVoiceTaskExecutionContext(executionContext.projectDir, executionContext.projectId);

  const commonParams = (): Record<string, unknown> => {
    if (!normalizedExecutionContext) {
      throw new Error('Live Voice task commands require an absolute persisted-session project_dir');
    }
    return {
      session_id: requireRunnableSessionId(sessionId),
      mode: 'auto_harness',
      project_dir: normalizedExecutionContext.projectDir,
      ...(normalizedExecutionContext.projectId ? { project_id: normalizedExecutionContext.projectId } : {}),
    };
  };

  return {
    owner: {
      sessionId: requireRunnableSessionId(sessionId),
      projectDir: normalizedExecutionContext?.projectDir ?? '',
      projectId: normalizedExecutionContext?.projectId ?? null,
      channelId: 'web',
      appId: '',
    },

    run({ query, pipeline, commandId }) {
      return request('schedule.run', {
        ...commonParams(),
        query,
        pipeline,
        origin_namespace: LIVE_VOICE_TASK_ORIGIN_NAMESPACE,
        idempotency_key: commandId,
      });
    },

    listByCommand(commandId, options) {
      return request('schedule.list', {
        ...commonParams(),
        origin_namespace: LIVE_VOICE_TASK_ORIGIN_NAMESPACE,
        idempotency_key: commandId,
      }, options);
    },

    status(taskId, options) {
      return request('schedule.status', {
        ...commonParams(),
        task_id: taskId,
      }, options);
    },

    cancel(taskId) {
      return request('schedule.cancel', {
        ...commonParams(),
        task_id: taskId,
      });
    },
  };
}

export const LIVE_VOICE_TASK_CLIENT_PIPELINE = LIVE_VOICE_AUTO_HARNESS_PIPELINE;
