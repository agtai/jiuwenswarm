import {
  isLiveVoiceTaskCommand,
  type LiveVoiceTaskBridgeResult,
  type LiveVoiceTaskBridgeSnapshot,
  type LiveVoiceTaskExecutionTarget,
} from './liveVoiceTaskBridge';

export type LiveVoiceTaskRecordRole = 'current' | 'predecessor' | 'successor' | 'conflict';

export interface LiveVoiceTaskRecordActivity {
  role: LiveVoiceTaskRecordRole;
  taskId: string;
  commandId?: string;
  status: string;
  source: string;
  resultSource: string;
  recoveryStatus: string;
  executionTarget: LiveVoiceTaskExecutionTarget;
}

export interface LiveVoiceTaskActivity {
  level: 'info' | 'warning' | 'error';
  title: string;
  detail: string;
  /** The command currently being reported, which may differ from a predecessor record. */
  commandId?: string;
  predecessorTaskId?: string;
  successorTaskId?: string;
  conflictingTaskId?: string;
  record?: LiveVoiceTaskRecordActivity;
  disclosure?: string;
}

export function projectLiveVoiceTaskActivity(result: LiveVoiceTaskBridgeResult): LiveVoiceTaskActivity | null {
  if (!result.feedback) return null;
  const task = result.task;
  let role: LiveVoiceTaskRecordRole = 'current';
  if (task && result.conflictingTaskId === task.taskId) {
    role = 'conflict';
  } else if (task && result.command === 'replace' && result.successorTaskId === task.taskId) {
    role = 'successor';
  } else if (task && result.command === 'replace' && result.predecessorTaskId === task.taskId) {
    role = 'predecessor';
  }

  return {
    level: result.feedback.level,
    title: result.feedback.title,
    detail: result.feedback.detail,
    commandId: result.commandId ?? task?.commandId ?? undefined,
    predecessorTaskId: result.command === 'replace' || result.predecessorCancelled ? result.predecessorTaskId : undefined,
    successorTaskId: result.successorTaskId,
    // Never infer a conflict identity from the generic task record: in replace
    // failures that record is commonly the cancelled predecessor.
    conflictingTaskId: result.conflictingTaskId,
    record: task
      ? {
          role,
          taskId: task.taskId,
          commandId: task.commandId ?? undefined,
          status: `${task.status.kind}/${task.status.raw ?? 'unknown'}`,
          source: task.source,
          resultSource: task.resultSource,
          recoveryStatus: result.recoveryStatus ?? task.recoveryStatus,
          executionTarget: task.executionTarget,
        }
      : undefined,
    disclosure: result.disclosure ? `${result.disclosure.label}: ${result.disclosure.description}` : undefined,
  };
}

export interface LiveVoiceTaskContextInvalidation {
  action: 'clear' | 'isolate';
  commandId: string | null;
}

/** Preserve any command whose request/result may still be outstanding. */
export function selectLiveVoiceTaskContextInvalidation(snapshot: LiveVoiceTaskBridgeSnapshot): LiveVoiceTaskContextInvalidation {
  const isolate = snapshot.inFlight || snapshot.mutationUnknown;
  return {
    action: isolate ? 'isolate' : 'clear',
    commandId: snapshot.pendingCommandId ?? (isolate ? snapshot.lastVisibleTask?.commandId ?? null : null),
  };
}

export type LiveVoiceTaskTranscriptRoute =
  | 'chat'
  | 'dispatch-task'
  | 'requires-persisted-session'
  | 'requires-execution-target'
  | 'session-changed'
  | 'execution-target-changed';

export interface LiveVoiceTaskTranscriptRouteInput {
  taskDemoEnabled: boolean;
  transcript: string;
  captureSessionId: string | null;
  currentSessionId: string | null;
  captureExecutionTargetKey: string | null;
  currentExecutionTargetKey: string | null;
}

/**
 * Decide whether the React adapter keeps a committed transcript on the normal
 * Chat/Agent path or hands it to the restricted task bridge. Task matching is
 * deliberately gated before any session or bridge work so flag-off preserves
 * the V0 path exactly.
 */
export function selectLiveVoiceTaskTranscriptRoute({
  taskDemoEnabled,
  transcript,
  captureSessionId,
  currentSessionId,
  captureExecutionTargetKey,
  currentExecutionTargetKey,
}: LiveVoiceTaskTranscriptRouteInput): LiveVoiceTaskTranscriptRoute {
  if (!taskDemoEnabled || !isLiveVoiceTaskCommand(transcript)) {
    return 'chat';
  }
  if (captureSessionId !== currentSessionId) {
    return 'session-changed';
  }
  if (!currentSessionId || currentSessionId === 'new') {
    return 'requires-persisted-session';
  }
  if (!currentExecutionTargetKey) {
    return 'requires-execution-target';
  }
  if (captureExecutionTargetKey !== currentExecutionTargetKey) {
    return 'execution-target-changed';
  }
  return 'dispatch-task';
}

export function selectLiveVoiceTaskSafetyDisclosure(taskDemoEnabled: boolean, disclosure: string): string | undefined {
  return taskDemoEnabled ? disclosure : undefined;
}

/**
 * A bridge result may update UI or speech only while both its session and its
 * exact in-memory bridge context remain current. The identity fence also
 * rejects a late result after navigating away and back to the same session.
 */
export function isLiveVoiceTaskResultCurrentContext(
  originSessionId: string,
  currentSessionId: string | null,
  originContext: unknown,
  currentContext: unknown,
  originExecutionTargetKey?: string | null,
  currentExecutionTargetKey?: string | null
): boolean {
  return (
    originSessionId === currentSessionId &&
    originContext === currentContext &&
    (originExecutionTargetKey === undefined || originExecutionTargetKey === currentExecutionTargetKey)
  );
}

export type LiveVoiceTaskFeedbackDrainAction = 'none' | 'begin-capture';

export interface LiveVoiceTaskFeedbackDrainInput {
  taskFeedbackOwnsResume: boolean;
  resumeRequested: boolean;
  responseInProgress: boolean;
  status: 'idle' | 'listening' | 'thinking' | 'speaking' | 'interrupted' | 'error';
  pendingSpeechCount: number;
  activeSpeechKey: string | null;
}

/**
 * Task feedback is independent of an unrelated Chat/Agent response. Once its
 * own speech drains it may reopen capture even when that Agent is processing.
 */
export function selectLiveVoiceTaskFeedbackDrainAction({
  taskFeedbackOwnsResume,
  resumeRequested,
  responseInProgress: _responseInProgress,
  status,
  pendingSpeechCount,
  activeSpeechKey,
}: LiveVoiceTaskFeedbackDrainInput): LiveVoiceTaskFeedbackDrainAction {
  const speechQueueEmpty = pendingSpeechCount === 0 && activeSpeechKey === null;
  return taskFeedbackOwnsResume && resumeRequested && status === 'idle' && speechQueueEmpty ? 'begin-capture' : 'none';
}
