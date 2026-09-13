/** Display data only. No parser, control client, Task selection or authority. */
export interface LiveVoiceTaskActivity {
  level: 'info' | 'warning' | 'error';
  title: string;
  detail: string;
  commandId?: string;
  predecessorTaskId?: string;
  successorTaskId?: string;
  conflictingTaskId?: string;
  disclosure?: string;
  record?: {
    role: 'current' | 'predecessor' | 'successor' | 'conflict';
    taskId: string;
    commandId?: string;
    status: string;
    source: string;
    resultSource: string;
    recoveryStatus: string;
    monitorState?: string;
    progressSummary?: string | null;
    lastError?: string | null;
    executionTarget: {
      projectDir: string | null;
      projectId: string | null;
      originSessionId: string | null;
      originChannelId: string | null;
    };
  };
}
