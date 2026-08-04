import {
  LIVE_VOICE_AUTO_HARNESS_PIPELINE,
  normalizeLiveVoiceTaskStatus,
  type LiveVoiceTaskExecutionTarget,
  type LiveVoiceTaskGateway,
  type LiveVoiceVisibleTask,
} from './liveVoiceTaskBridge';

export type LiveVoiceTaskMonitorPhase =
  | 'idle'
  | 'polling'
  | 'paused-disconnected'
  | 'reconciling'
  | 'backoff'
  | 'terminal'
  | 'missing'
  | 'adapter-error'
  | 'stopped';

export interface LiveVoiceTaskMonitorSnapshot {
  phase: LiveVoiceTaskMonitorPhase;
  task: LiveVoiceVisibleTask;
  progressSummary: string | null;
  lastError: string | null;
  errorCode: string | null;
  errorDetail: string | null;
  retryCount: number;
}

export interface LiveVoiceTaskMonitorClock {
  now(): number;
  setTimeout(callback: () => void, delayMs: number): unknown;
  clearTimeout(handle: unknown): void;
}

export interface LiveVoiceTaskMonitorOptions {
  task: LiveVoiceVisibleTask;
  gateway: Pick<LiveVoiceTaskGateway, 'owner' | 'status' | 'listByCommand'>;
  onSnapshot(snapshot: LiveVoiceTaskMonitorSnapshot): void;
  onObservation(task: LiveVoiceVisibleTask): boolean;
  clock?: LiveVoiceTaskMonitorClock;
}

interface ParsedObservation {
  task: LiveVoiceVisibleTask;
  progressSummary: string | null;
  lastError: string | null;
}

type ObservationResult = { ok: true; observation: ParsedObservation } | { ok: false; code: string; detail: string };

type ReadOperation = 'status' | 'reconcile';

interface ActiveRead {
  controller: AbortController;
  generation: number;
  operation: ReadOperation;
}

const OWN = Object.prototype.hasOwnProperty;
const RETRY_DELAYS_MS = [1000, 2000, 5000, 10000] as const;

const browserClock: LiveVoiceTaskMonitorClock = {
  now: () => Date.now(),
  setTimeout: (callback, delayMs) => setTimeout(callback, delayMs),
  clearTimeout: handle => clearTimeout(handle as ReturnType<typeof setTimeout>),
};

function record(value: unknown): Record<string, unknown> | null {
  return typeof value === 'object' && value !== null && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

function requiredString(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value.trim() : null;
}

function pathKey(value: string): string {
  const normalized = value.replace(/\\/gu, '/').replace(/\/+$/gu, '');
  return /^[a-z]:\//iu.test(normalized) || normalized.startsWith('//') ? normalized.toLowerCase() : normalized;
}

function targetValue(value: unknown): string | null {
  const normalized = requiredString(value);
  return normalized && normalized.toLowerCase() !== 'unknown' ? normalized : null;
}

function sameNullableValue(expected: string | null, value: unknown): boolean {
  const observed = targetValue(value);
  return expected === null ? observed === null : observed === expected;
}

function parseExecutionTarget(
  value: unknown,
  expected: LiveVoiceVisibleTask,
  owner: NonNullable<LiveVoiceTaskGateway['owner']>
): LiveVoiceTaskExecutionTarget | null {
  const source = record(value);
  if (!source) return null;
  const projectDir = targetValue(source.project_dir);
  const projectId = targetValue(source.project_id);
  const originSessionId = targetValue(source.origin_session_id);
  const originChannelId = targetValue(source.origin_channel_id);
  if (!projectDir || !originSessionId || !originChannelId) return null;
  if (pathKey(projectDir) !== pathKey(owner.projectDir) || pathKey(projectDir) !== pathKey(expected.executionTarget.projectDir ?? '')) return null;
  if (!sameNullableValue(owner.projectId, source.project_id) || !sameNullableValue(expected.executionTarget.projectId, source.project_id)) return null;
  if (originSessionId !== owner.sessionId || (expected.executionTarget.originSessionId && originSessionId !== expected.executionTarget.originSessionId)) {
    return null;
  }
  if (originChannelId !== owner.channelId) return null;
  if (expected.executionTarget.originChannelId && originChannelId !== expected.executionTarget.originChannelId) return null;
  return { projectDir, projectId, originSessionId, originChannelId };
}

function validProvenance(
  value: unknown,
  expected: LiveVoiceVisibleTask,
  target: LiveVoiceTaskExecutionTarget,
  owner: NonNullable<LiveVoiceTaskGateway['owner']>
): boolean {
  const provenance = record(value);
  const ownerScope = record(provenance?.owner_scope);
  if (!provenance || !ownerScope) return false;
  if (requiredString(provenance.origin_namespace) !== 'live_voice') return false;
  if (requiredString(provenance.idempotency_key) !== expected.commandId) return false;
  if (provenance.legacy_unscoped !== false || provenance.access !== 'authorized') return false;
  if (requiredString(ownerScope.session_id) !== owner.sessionId) return false;
  if (requiredString(ownerScope.channel_id) !== owner.channelId || target.originChannelId !== owner.channelId) return false;
  return ownerScope.app_id === owner.appId;
}

export function parseLiveVoiceTaskObservation(
  payload: unknown,
  expected: LiveVoiceVisibleTask,
  owner: LiveVoiceTaskGateway['owner'],
  source: 'schedule.status' | 'schedule.list'
): ObservationResult {
  if (!owner || !expected.commandId) {
    return { ok: false, code: 'monitor-identity-incomplete', detail: 'Task monitor identity is incomplete' };
  }
  const value = record(payload);
  if (!value) return { ok: false, code: 'invalid-task-payload', detail: 'Task response is not an object' };
  if (OWN.call(value, 'error')) {
    return {
      ok: false,
      code: requiredString(value.code) ?? 'task-business-error',
      detail: requiredString(value.error) ?? 'Task service returned an error',
    };
  }
  if (requiredString(value.task_id) !== expected.taskId) {
    return { ok: false, code: 'task-id-mismatch', detail: 'Task response does not match the monitored task' };
  }
  const rawStatus = requiredString(value.status);
  if (!rawStatus) return { ok: false, code: 'invalid-task-status', detail: 'Task response has no valid status' };
  const executionTarget = parseExecutionTarget(value.execution_target, expected, owner);
  if (!executionTarget || !validProvenance(value.provenance, expected, executionTarget, owner)) {
    return { ok: false, code: 'task-scope-mismatch', detail: 'Task response identity or scope does not match the monitor' };
  }
  if (OWN.call(value, 'progress') && !record(value.progress)) {
    return { ok: false, code: 'invalid-task-progress', detail: 'Task response has malformed progress' };
  }
  if (OWN.call(value, 'last_error') && typeof value.last_error !== 'string') {
    return { ok: false, code: 'invalid-task-last-error', detail: 'Task response has malformed last_error' };
  }
  const progress = record(value.progress);
  const progressSummary = requiredString(progress?.summary);
  const lastError = requiredString(value.last_error);
  return {
    ok: true,
    observation: {
      task: {
        ...expected,
        status: normalizeLiveVoiceTaskStatus(rawStatus),
        source,
        resultSource: source === 'schedule.list' ? 'exact-key-reconciliation' : 'status-observation',
        recoveryStatus: source === 'schedule.list' ? 'recovered' : expected.recoveryStatus,
        executionTarget,
      },
      progressSummary,
      lastError,
    },
  };
}

function cloneTask(task: LiveVoiceVisibleTask): LiveVoiceVisibleTask {
  return { ...task, status: { ...task.status }, executionTarget: { ...task.executionTarget } };
}

function isRetriableReadError(error: unknown): boolean {
  const value = record(error);
  if (value?.retriable === true) return true;
  const code = requiredString(value?.code);
  return code === 'REQUEST_TIMEOUT' || code === 'WS_DISCONNECTED' || code === 'WS_NOT_READY';
}

function terminalNotificationText(task: LiveVoiceVisibleTask): string {
  const status = task.status.raw ?? 'unknown';
  if (task.status.kind === 'success') return `后台任务 ${task.taskId} 已结束，真实状态为 ${status}。`;
  if (task.status.kind === 'cancelled') return `后台任务 ${task.taskId} 已取消，真实状态为 ${status}。`;
  return `后台任务 ${task.taskId} 已结束，真实状态为 ${status}，不代表成功。`;
}

export class LiveVoiceTaskMonitor {
  private readonly clock: LiveVoiceTaskMonitorClock;

  private snapshot: LiveVoiceTaskMonitorSnapshot;

  private timer: unknown = null;

  private activeRead: ActiveRead | null = null;

  private generation = 0;

  private connected = false;

  private reconcileRequired = false;

  private runningSince: number | null = null;

  private notificationTaken = false;

  constructor(private readonly options: LiveVoiceTaskMonitorOptions) {
    this.clock = options.clock ?? browserClock;
    this.snapshot = {
      phase: 'idle',
      task: cloneTask(options.task),
      progressSummary: null,
      lastError: null,
      errorCode: null,
      errorDetail: null,
      retryCount: 0,
    };
  }

  getSnapshot(): LiveVoiceTaskMonitorSnapshot {
    return { ...this.snapshot, task: cloneTask(this.snapshot.task) };
  }

  start(connected: boolean): void {
    if (this.snapshot.phase !== 'idle') return;
    this.connected = connected;
    if (this.snapshot.task.status.terminal) {
      this.setPhase('terminal');
      return;
    }
    if (!connected) {
      this.reconcileRequired = true;
      this.setPhase('paused-disconnected');
      return;
    }
    void this.performRead('status');
  }

  setConnected(connected: boolean): void {
    if (
      this.connected === connected ||
      this.snapshot.phase === 'stopped' ||
      this.snapshot.phase === 'terminal' ||
      this.snapshot.phase === 'missing' ||
      this.snapshot.phase === 'adapter-error'
    ) {
      return;
    }
    this.connected = connected;
    if (!connected) {
      this.reconcileRequired = true;
      this.generation += 1;
      this.clearTimer();
      this.activeRead?.controller.abort();
      this.setPhase('paused-disconnected');
      return;
    }
    this.reconcileRequired = true;
    if (this.activeRead) {
      this.setPhase('paused-disconnected');
      return;
    }
    void this.performRead('reconcile');
  }

  stop(): void {
    if (this.snapshot.phase === 'stopped') return;
    this.connected = false;
    this.generation += 1;
    this.clearTimer();
    this.activeRead?.controller.abort();
    this.setPhase('stopped');
  }

  takeTerminalNotification(): string | null {
    if (this.snapshot.phase !== 'terminal' || this.notificationTaken) return null;
    this.notificationTaken = true;
    return terminalNotificationText(this.snapshot.task);
  }

  private publish(): void {
    this.options.onSnapshot(this.getSnapshot());
  }

  private setPhase(phase: LiveVoiceTaskMonitorPhase, errorCode: string | null = null, errorDetail: string | null = null): void {
    this.snapshot = { ...this.snapshot, phase, errorCode, errorDetail };
    this.publish();
  }

  private clearTimer(): void {
    if (this.timer === null) return;
    this.clock.clearTimeout(this.timer);
    this.timer = null;
  }

  private schedule(operation: ReadOperation, delayMs: number): void {
    this.clearTimer();
    const generation = this.generation;
    this.timer = this.clock.setTimeout(() => {
      this.timer = null;
      if (generation !== this.generation || !this.connected || this.snapshot.phase === 'stopped' || this.snapshot.phase === 'terminal') return;
      void this.performRead(operation);
    }, delayMs);
  }

  private nextPollDelay(task: LiveVoiceVisibleTask): number {
    if (task.status.kind === 'queued') return 1000;
    if (task.status.kind === 'running') {
      if (this.runningSince === null) this.runningSince = this.clock.now();
      return this.clock.now() - this.runningSince < 30000 ? 2000 : 5000;
    }
    return 5000;
  }

  private fail(code: string, detail: string, phase: 'missing' | 'adapter-error' = 'adapter-error'): void {
    this.clearTimer();
    this.setPhase(phase, code, detail);
  }

  private classifyPayloadError(payload: unknown): boolean {
    const value = record(payload);
    if (!value || !OWN.call(value, 'error')) return false;
    const code = requiredString(value.code) ?? 'task-business-error';
    const detail = requiredString(value.error) ?? 'Task service returned an error';
    if (code === 'TASK_NOT_FOUND') this.fail(code, detail, 'missing');
    else this.fail(code, detail);
    return true;
  }

  private parseReconciliation(payload: unknown): ObservationResult | { missing: true } {
    const envelope = record(payload);
    if (!envelope) return { ok: false, code: 'invalid-task-list', detail: 'Task list response is not an object' };
    if (this.classifyPayloadError(payload)) return { ok: false, code: 'task-business-error', detail: 'Task list returned an error' };
    if (!Array.isArray(envelope.tasks)) return { ok: false, code: 'invalid-task-list', detail: 'Task list response has no tasks array' };
    if (envelope.tasks.length === 0) return { missing: true };
    if (envelope.tasks.length !== 1) return { ok: false, code: 'task-list-conflict', detail: 'Exact task reconciliation returned multiple records' };
    const candidate = record(envelope.tasks[0]);
    if (!candidate) return { ok: false, code: 'invalid-task-list-record', detail: 'Task reconciliation record is malformed' };
    if (requiredString(candidate.query) !== this.snapshot.task.query) {
      return { ok: false, code: 'task-query-mismatch', detail: 'Task reconciliation query does not match' };
    }
    if (requiredString(candidate.pipeline) !== LIVE_VOICE_AUTO_HARNESS_PIPELINE) {
      return { ok: false, code: 'task-pipeline-mismatch', detail: 'Task reconciliation pipeline does not match' };
    }
    if (requiredString(candidate.idempotency_key) !== this.snapshot.task.commandId) {
      return { ok: false, code: 'task-command-mismatch', detail: 'Task reconciliation command does not match' };
    }
    return parseLiveVoiceTaskObservation(candidate, this.snapshot.task, this.options.gateway.owner, 'schedule.list');
  }

  private accept(observation: ParsedObservation): void {
    if (!this.options.onObservation(observation.task)) {
      this.fail('bridge-observation-rejected', 'The current task Bridge rejected a stale monitor observation');
      return;
    }
    this.snapshot = {
      ...this.snapshot,
      task: cloneTask(observation.task),
      progressSummary: observation.progressSummary,
      lastError: observation.lastError,
      errorCode: null,
      errorDetail: null,
      retryCount: 0,
    };
    this.reconcileRequired = false;
    if (observation.task.status.terminal) {
      this.clearTimer();
      this.setPhase('terminal');
      return;
    }
    this.setPhase('polling');
    this.schedule('status', this.nextPollDelay(observation.task));
  }

  private async performRead(operation: ReadOperation): Promise<void> {
    if (this.activeRead || !this.connected || this.snapshot.phase === 'stopped' || this.snapshot.phase === 'terminal') return;
    const controller = new AbortController();
    const activeRead: ActiveRead = { controller, generation: this.generation, operation };
    this.activeRead = activeRead;
    this.setPhase(operation === 'reconcile' ? 'reconciling' : 'polling');
    try {
      const payload =
        operation === 'reconcile'
          ? await this.options.gateway.listByCommand(this.snapshot.task.commandId ?? '', { signal: controller.signal })
          : await this.options.gateway.status(this.snapshot.task.taskId, { signal: controller.signal });
      if (activeRead.generation !== this.generation || this.activeRead !== activeRead) return;
      if (this.classifyPayloadError(payload)) return;
      if (operation === 'reconcile') {
        const parsed = this.parseReconciliation(payload);
        if ('missing' in parsed) {
          this.fail('TASK_NOT_FOUND', 'The exact task command has no stored task', 'missing');
        } else if (parsed.ok === false) {
          this.fail(parsed.code, parsed.detail);
        } else {
          this.accept(parsed.observation);
        }
      } else {
        const parsed = parseLiveVoiceTaskObservation(payload, this.snapshot.task, this.options.gateway.owner, 'schedule.status');
        if (parsed.ok === false) this.fail(parsed.code, parsed.detail);
        else this.accept(parsed.observation);
      }
    } catch (error) {
      if (activeRead.generation !== this.generation || this.activeRead !== activeRead || controller.signal.aborted) return;
      if (!isRetriableReadError(error)) {
        this.fail(requiredString(record(error)?.code) ?? 'task-read-failed', requiredString(record(error)?.message) ?? 'Task read failed');
        return;
      }
      const retryIndex = Math.min(this.snapshot.retryCount, RETRY_DELAYS_MS.length - 1);
      this.snapshot = { ...this.snapshot, retryCount: this.snapshot.retryCount + 1 };
      this.setPhase('backoff', requiredString(record(error)?.code) ?? 'task-read-retry', requiredString(record(error)?.message));
      this.schedule(operation, RETRY_DELAYS_MS[retryIndex]);
    } finally {
      if (this.activeRead === activeRead) this.activeRead = null;
      if (
        this.connected &&
        this.reconcileRequired &&
        !this.activeRead &&
        this.timer === null &&
        this.snapshot.phase !== 'stopped' &&
        this.snapshot.phase !== 'terminal' &&
        this.snapshot.phase !== 'missing' &&
        this.snapshot.phase !== 'adapter-error'
      ) {
        void this.performRead('reconcile');
      }
    }
  }
}
