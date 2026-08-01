/**
 * A deliberately narrow Voice–Task Bridge for the two-week Live Voice demo.
 *
 * This module does not own recognition, chat routing, WebSocket requests, UI,
 * or TTS. It only accepts a committed final transcript, recognizes a small
 * set of exact Chinese commands, and calls an injected AutoHarness gateway.
 * Keeping the gateway behind an interface lets the current demo adapter be
 * replaced by the production P3 Task Control Core without inventing task IDs,
 * states, or outcomes here.
 */

import { generateUuidV4 } from '../../utils/uuid';

export const LIVE_VOICE_AUTO_HARNESS_PIPELINE = 'extended_evolve_pipeline' as const;

export const LIVE_VOICE_AUTO_HARNESS_DEMO_DISCLOSURE = {
  label: 'Demo substitute: AutoHarness',
  executor: 'AutoHarness',
  pipeline: LIVE_VOICE_AUTO_HARNESS_PIPELINE,
  hasCodeSideEffects: true,
  description: '这是受限 AutoHarness Demo。任务会使用 extended_evolve_pipeline 生成或修改本地 Harness 代码包，不是只读仓库检查，也不是完整 P3 Task Control。',
} as const;

export interface LiveVoiceTaskGateway {
  owner?: {
    sessionId: string;
    projectDir: string;
    projectId: string | null;
  };
  run(request: { query: string; pipeline: typeof LIVE_VOICE_AUTO_HARNESS_PIPELINE; commandId: string }): Promise<unknown>;
  listByCommand(commandId: string): Promise<unknown>;
  status(taskId: string): Promise<unknown>;
  cancel(taskId: string): Promise<unknown>;
}

export interface LiveVoiceTaskBridgeInput {
  captureKey: string;
  text: string;
  transcriptKind: 'interim' | 'final';
  committed: boolean;
}

export type LiveVoiceTaskCommandKind = 'create' | 'status' | 'cancel' | 'replace';

export type LiveVoiceTaskStatusKind = 'queued' | 'running' | 'success' | 'failed' | 'cancelled' | 'unknown';

export interface LiveVoiceTaskStatus {
  kind: LiveVoiceTaskStatusKind;
  /** The backend value, preserved for truthful UI display. */
  raw: string | null;
  terminal: boolean;
}

export interface LiveVoiceTaskExecutionTarget {
  projectDir: string | null;
  projectId: string | null;
  originSessionId: string | null;
  originChannelId: string | null;
}

export interface LiveVoiceVisibleTask {
  taskId: string;
  commandId: string | null;
  query: string | null;
  status: LiveVoiceTaskStatus;
  source: 'schedule.run' | 'schedule.list' | 'schedule.status' | 'schedule.cancel';
  resultSource:
    | 'fresh'
    | 'same-key-retry'
    | 'idempotent-replay'
    | 'exact-key-reconciliation'
    | 'status-observation'
    | 'cancel-observation';
  recoveryStatus: 'not-needed' | 'recovered' | 'pending' | 'conflict';
  pipeline: typeof LIVE_VOICE_AUTO_HARNESS_PIPELINE;
  /** Backend-owned task provenance. Missing/legacy fields remain null. */
  executionTarget: LiveVoiceTaskExecutionTarget;
}

export type LiveVoiceTaskBridgeOutcome =
  | 'not-handled'
  | 'ignored-not-committed'
  | 'invalid-capture'
  | 'duplicate-capture'
  | 'busy'
  | 'confirmation-required'
  | 'no-visible-task'
  | 'active-task-exists'
  | 'already-terminal'
  | 'started'
  | 'status'
  | 'cancelled'
  | 'replaced'
  | 'recovered'
  | 'recovery-conflict'
  | 'mutation-unknown'
  | 'failed';

export interface LiveVoiceTaskBridgeFeedback {
  level: 'info' | 'warning' | 'error';
  /** Stable machine-readable code for future UI and trace adapters. */
  code: string;
  title: string;
  detail: string;
  /** Optional copy a future TTS policy may choose to speak. */
  speakableText: string;
}

export interface LiveVoiceTaskBridgeResult {
  handled: boolean;
  outcome: LiveVoiceTaskBridgeOutcome;
  command?: LiveVoiceTaskCommandKind;
  commandId?: string;
  recoveryStatus?: LiveVoiceVisibleTask['recoveryStatus'];
  captureKey?: string;
  requestedQuery?: string;
  task?: LiveVoiceVisibleTask;
  predecessorTaskId?: string;
  successorTaskId?: string;
  /** Conflicting backend record observed during reconciliation; never proof of a successor. */
  conflictingTaskId?: string;
  predecessorCancelled?: boolean;
  feedback?: LiveVoiceTaskBridgeFeedback;
  disclosure?: typeof LIVE_VOICE_AUTO_HARNESS_DEMO_DISCLOSURE;
}

export interface LiveVoiceTaskBridgeSnapshot {
  inFlight: boolean;
  /** A non-idempotent run may have reached the backend without returning an ID. */
  mutationUnknown: boolean;
  rememberedCaptureCount: number;
  /** Stable create/replace command ID, including while its first request is in flight. */
  pendingCommandId: string | null;
  lastVisibleTask: LiveVoiceVisibleTask | null;
}

type ParsedCommand =
  | { kind: 'status'; confirmed: true }
  | { kind: 'cancel'; confirmed: boolean }
  | { kind: 'create' | 'replace'; confirmed: boolean; query: string };

interface ParsedGatewayPayload {
  record: Record<string, unknown> | null;
  taskId: string | null;
  existingTaskId: string | null;
  status: LiveVoiceTaskStatus;
  error: string | null;
  code: string | null;
  idempotentReplay: boolean;
  executionTarget: LiveVoiceTaskExecutionTarget;
}

interface TaskMutationAttempt {
  ok: boolean;
  code: string;
  message: string;
  mutationUnknown?: boolean;
  recovered?: boolean;
  conflict?: boolean;
  conflictingTaskId?: string;
  commandId?: string;
  task?: LiveVoiceVisibleTask;
}

interface PendingMutation {
  kind: 'create' | 'replace';
  commandId: string;
  query: string;
  predecessorTaskId?: string;
  predecessorCancelled?: boolean;
}

export interface LiveVoiceTaskBridgeOptions {
  commandIdFactory?: () => string;
}

const OWN = Object.prototype.hasOwnProperty;

const UNKNOWN_EXECUTION_TARGET_VALUE = 'unknown';

function toNonEmptyString(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function stringifyGatewayError(value: unknown): string {
  if (typeof value === 'string' && value.trim()) return value.trim();
  if (value instanceof Error && value.message.trim()) return value.message.trim();
  if (value !== undefined && value !== null) {
    try {
      const serialized = JSON.stringify(value);
      if (serialized) return serialized;
    } catch {
      // Fall through to the stable generic message.
    }
  }
  return '后端返回了未说明细节的业务错误';
}

function errorMessageFromThrown(value: unknown): string {
  if (value instanceof Error && value.message.trim()) return value.message.trim();
  if (typeof value === 'string' && value.trim()) return value.trim();
  return '调用后台任务网关时发生未知异常';
}

function executionTargetField(record: Record<string, unknown> | null, field: string): string | null {
  if (!record) return null;
  const value = toNonEmptyString(record[field]);
  return value && value.toLowerCase() !== UNKNOWN_EXECUTION_TARGET_VALUE ? value : null;
}

function parseExecutionTarget(record: Record<string, unknown> | null): LiveVoiceTaskExecutionTarget {
  const value = record?.execution_target;
  const target = typeof value === 'object' && value !== null && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
  return {
    projectDir: executionTargetField(target, 'project_dir'),
    projectId: executionTargetField(target, 'project_id'),
    originSessionId: executionTargetField(target, 'origin_session_id'),
    originChannelId: executionTargetField(target, 'origin_channel_id'),
  };
}

function mergeExecutionTarget(
  known: LiveVoiceTaskExecutionTarget | null,
  observed: LiveVoiceTaskExecutionTarget
): LiveVoiceTaskExecutionTarget {
  return {
    projectDir: observed.projectDir ?? known?.projectDir ?? null,
    projectId: observed.projectId ?? known?.projectId ?? null,
    originSessionId: observed.originSessionId ?? known?.originSessionId ?? null,
    originChannelId: observed.originChannelId ?? known?.originChannelId ?? null,
  };
}

function normalizedPathForComparison(path: string): string {
  const normalized = path.replace(/\\/gu, '/').replace(/\/+$/gu, '');
  return /^[a-z]:\//iu.test(normalized) || normalized.startsWith('//') ? normalized.toLowerCase() : normalized;
}

function executionTargetConflict(
  owner: LiveVoiceTaskGateway['owner'],
  known: LiveVoiceTaskExecutionTarget | null,
  observed: LiveVoiceTaskExecutionTarget
): string | null {
  if (known) {
    for (const field of ['projectDir', 'projectId', 'originSessionId', 'originChannelId'] as const) {
      const previous = known[field];
      const next = observed[field];
      if (previous && next) {
        const matches =
          field === 'projectDir' ? normalizedPathForComparison(previous) === normalizedPathForComparison(next) : previous === next;
        if (!matches) return `${field} 与已知任务 provenance 冲突`;
      }
    }
  }
  if (!owner) return null;
  if (!observed.projectDir || normalizedPathForComparison(observed.projectDir) !== normalizedPathForComparison(owner.projectDir)) {
    return 'project_dir 不属于当前持久会话目标';
  }
  if ((owner.projectId ?? null) !== (observed.projectId ?? null)) {
    return 'project_id 不属于当前持久会话目标';
  }
  if (!observed.originSessionId || observed.originSessionId !== owner.sessionId) {
    return 'origin_session_id 不属于当前持久会话';
  }
  return null;
}

function normalizeIntentText(value: string | null | undefined): string {
  return (value ?? '').replace(/\r\n?/gu, '\n').trim();
}

export function normalizeLiveVoiceTaskStatus(value: unknown): LiveVoiceTaskStatus {
  const raw = value === undefined || value === null ? null : typeof value === 'string' ? value.trim() || null : String(value);
  const normalized = raw?.toLowerCase().replace(/[\s-]+/g, '_') ?? '';

  if (['accepted', 'pending', 'queued', 'scheduled'].includes(normalized)) {
    return { kind: 'queued', raw, terminal: false };
  }
  if (['running', 'executing', 'in_progress', 'processing', 'started'].includes(normalized)) {
    return { kind: 'running', raw, terminal: false };
  }
  if (['success', 'succeeded', 'completed', 'complete', 'done', 'pr_created', 'completed_without_pr'].includes(normalized)) {
    return { kind: 'success', raw, terminal: true };
  }
  if (['failed', 'failure', 'error'].includes(normalized)) {
    return { kind: 'failed', raw, terminal: true };
  }
  if (['cancelled', 'canceled'].includes(normalized)) {
    return { kind: 'cancelled', raw, terminal: true };
  }
  if (['skipped', 'needs_human', 'deleted'].includes(normalized)) {
    // AutoHarness defines these as terminal, but neither value proves success
    // or failure. Preserve the backend value and expose an honest unknown
    // outcome while still preventing a meaningless cancel request.
    return { kind: 'unknown', raw, terminal: true };
  }

  // Unknown is deliberately non-terminal. A caller must observe a recognized
  // terminal state before starting or replacing work automatically.
  return { kind: 'unknown', raw, terminal: false };
}

function parseCommand(text: string): ParsedCommand | null {
  const normalized = text
    .trim()
    .replace(/[。！？!?]+$/u, '')
    .trim();

  if (normalized === '检查后台任务进度' || normalized === '检查后台演进任务进度') {
    return { kind: 'status', confirmed: true };
  }
  if (normalized === '确认取消后台演进任务') {
    return { kind: 'cancel', confirmed: true };
  }
  if (normalized === '取消后台演进任务') {
    return { kind: 'cancel', confirmed: false };
  }

  const forms: Array<{
    stem: string;
    kind: 'create' | 'replace';
    confirmed: boolean;
  }> = [
    {
      stem: '确认启动后台演进任务',
      kind: 'create',
      confirmed: true,
    },
    { stem: '启动后台演进任务', kind: 'create', confirmed: false },
    {
      stem: '确认替换后台演进任务',
      kind: 'replace',
      confirmed: true,
    },
    { stem: '替换后台演进任务', kind: 'replace', confirmed: false },
  ];

  for (const form of forms) {
    if (!normalized.startsWith(form.stem)) continue;
    const remainder = normalized.slice(form.stem.length);
    const separated = remainder.match(/^(?:[：:，,]\s*|冒号\s*|\s+)(.+)$/u);
    const query = separated?.[1]?.trim() ?? '';
    if (!query) return null;
    return { kind: form.kind, confirmed: form.confirmed, query };
  }

  return null;
}

/** Parse-only probe used by the React adapter before choosing chat vs task. */
export function isLiveVoiceTaskCommand(text: string): boolean {
  return parseCommand(text) !== null;
}

function parseGatewayPayload(payload: unknown): ParsedGatewayPayload {
  const record = typeof payload === 'object' && payload !== null && !Array.isArray(payload) ? (payload as Record<string, unknown>) : null;
  if (!record) {
    return {
      record: null,
      taskId: null,
      existingTaskId: null,
      status: normalizeLiveVoiceTaskStatus(null),
      error: '后端任务网关返回了无效 payload',
      code: null,
      idempotentReplay: false,
      executionTarget: parseExecutionTarget(null),
    };
  }

  return {
    record,
    taskId: toNonEmptyString(record.task_id),
    existingTaskId: toNonEmptyString(record.existing_task_id),
    status: normalizeLiveVoiceTaskStatus(record.status),
    error: OWN.call(record, 'error') ? stringifyGatewayError(record.error) : null,
    code: toNonEmptyString(record.code),
    idempotentReplay: record.idempotent_replay === true,
    executionTarget: parseExecutionTarget(record),
  };
}

function parseExactKeyTaskList(payload: unknown): { tasks: Record<string, unknown>[] | null; error: string | null } {
  const record = typeof payload === 'object' && payload !== null && !Array.isArray(payload) ? (payload as Record<string, unknown>) : null;
  if (!record || !Array.isArray(record.tasks)) {
    return { tasks: null, error: 'schedule.list 返回了无效 payload' };
  }
  if (OWN.call(record, 'error')) {
    return { tasks: null, error: 'schedule.list returned a business error: ' + stringifyGatewayError(record.error) };
  }
  const tasks = record.tasks.filter((task): task is Record<string, unknown> => typeof task === 'object' && task !== null && !Array.isArray(task));
  if (tasks.length !== record.tasks.length) {
    return { tasks: null, error: 'schedule.list 返回了无法解析的任务记录' };
  }
  return { tasks, error: null };
}

function cloneTask(task: LiveVoiceVisibleTask): LiveVoiceVisibleTask {
  return { ...task, status: { ...task.status }, executionTarget: { ...task.executionTarget } };
}

function feedback(
  level: LiveVoiceTaskBridgeFeedback['level'],
  code: string,
  title: string,
  detail: string,
  speakableText = detail
): LiveVoiceTaskBridgeFeedback {
  return { level, code, title, detail, speakableText };
}

export class LiveVoiceTaskBridge {
  private readonly seenCaptureKeys = new Set<string>();

  private inFlight = false;

  private mutationUnknown = false;

  private pendingMutation: PendingMutation | null = null;

  /** The create/replace currently executing before its outcome is classified. */
  private activeMutation: PendingMutation | null = null;

  private lastVisibleTask: LiveVoiceVisibleTask | null = null;

  private readonly commandIdFactory: () => string;

  constructor(
    private readonly gateway: LiveVoiceTaskGateway,
    options: LiveVoiceTaskBridgeOptions = {}
  ) {
    this.commandIdFactory = options.commandIdFactory ?? (() => `lv-${generateUuidV4()}`);
  }

  getSnapshot(): LiveVoiceTaskBridgeSnapshot {
    return {
      inFlight: this.inFlight,
      mutationUnknown: this.mutationUnknown,
      rememberedCaptureCount: this.seenCaptureKeys.size,
      pendingCommandId: this.pendingMutation?.commandId ?? this.activeMutation?.commandId ?? null,
      lastVisibleTask: this.lastVisibleTask ? cloneTask(this.lastVisibleTask) : null,
    };
  }

  async handle(input: LiveVoiceTaskBridgeInput): Promise<LiveVoiceTaskBridgeResult> {
    const command = parseCommand(input.text);
    if (!command) {
      return { handled: false, outcome: 'not-handled' };
    }

    if (input.transcriptKind !== 'final' || !input.committed) {
      return {
        handled: true,
        outcome: 'ignored-not-committed',
        command: command.kind,
        captureKey: input.captureKey,
        disclosure: LIVE_VOICE_AUTO_HARNESS_DEMO_DISCLOSURE,
        feedback: feedback('info', 'task-command-not-committed', '未提交的任务口令', '只有 committed final transcript 可以触发后台任务。'),
      };
    }

    const captureKey = input.captureKey.trim();
    if (!captureKey) {
      return this.handledResult(
        'invalid-capture',
        command,
        input.captureKey,
        feedback('error', 'missing-capture-key', '缺少语音 capture 标识', '为防止重复任务，这条口令未执行。')
      );
    }

    if (this.seenCaptureKeys.has(captureKey)) {
      return this.handledResult(
        'duplicate-capture',
        command,
        captureKey,
        feedback('warning', 'duplicate-capture', '重复的语音提交', '同一 capture 最多解析一条任务命令，本次已拒绝。')
      );
    }
    this.seenCaptureKeys.add(captureKey);

    if (!command.confirmed) {
      return this.handledResult(
        'confirmation-required',
        command,
        captureKey,
        feedback(
          'warning',
          'explicit-confirmation-required',
          '需要明确确认',
          command.kind === 'cancel' ? '请说“确认取消后台演进任务”。' : `请使用带“确认”的${command.kind === 'create' ? '启动' : '替换'}口令。`
        )
      );
    }

    if (this.inFlight) {
      return this.handledResult(
        'busy',
        command,
        captureKey,
        feedback('warning', 'task-command-in-flight', '前一条任务命令仍在处理', '为保证任务 ID 和取消顺序，后台任务命令不并发执行。')
      );
    }

    this.inFlight = true;
    try {
      if (command.kind === 'create') {
        return await this.handleCreate(command.query, command, captureKey);
      }
      if (command.kind === 'status') {
        return await this.handleStatus(command, captureKey);
      }
      if (command.kind === 'cancel') {
        return await this.handleCancel(command, captureKey);
      }
      return await this.handleReplace(command.query, command, captureKey);
    } finally {
      this.inFlight = false;
      this.activeMutation = null;
    }
  }

  private handledResult(
    outcome: LiveVoiceTaskBridgeOutcome,
    command: ParsedCommand,
    captureKey: string,
    resultFeedback: LiveVoiceTaskBridgeFeedback,
    extra: Partial<LiveVoiceTaskBridgeResult> = {}
  ): LiveVoiceTaskBridgeResult {
    const taskCommandId = extra.task?.commandId ?? undefined;
    const taskRecoveryStatus = extra.task?.recoveryStatus;
    return {
      handled: true,
      outcome,
      command: command.kind,
      captureKey,
      requestedQuery: 'query' in command ? command.query : undefined,
      disclosure: LIVE_VOICE_AUTO_HARNESS_DEMO_DISCLOSURE,
      feedback: resultFeedback,
      ...(taskCommandId ? { commandId: taskCommandId } : {}),
      ...(taskRecoveryStatus ? { recoveryStatus: taskRecoveryStatus } : {}),
      ...extra,
    };
  }

  private newPendingMutation(kind: PendingMutation['kind'], query: string): PendingMutation | null {
    try {
      const commandId = toNonEmptyString(this.commandIdFactory());
      if (!commandId) return null;
      const pending = { kind, commandId, query } satisfies PendingMutation;
      this.activeMutation = pending;
      return pending;
    } catch {
      return null;
    }
  }

  private makeTask(
    taskId: string,
    commandId: string | null,
    query: string | null,
    status: LiveVoiceTaskStatus,
    source: LiveVoiceVisibleTask['source'],
    executionTarget: LiveVoiceTaskExecutionTarget,
    resultSource: LiveVoiceVisibleTask['resultSource'],
    recoveryStatus: LiveVoiceVisibleTask['recoveryStatus']
  ): LiveVoiceVisibleTask {
    return {
      taskId,
      commandId,
      query,
      status,
      source,
      resultSource,
      recoveryStatus,
      pipeline: LIVE_VOICE_AUTO_HARNESS_PIPELINE,
      executionTarget: { ...executionTarget },
    };
  }

  private rememberTask(task: LiveVoiceVisibleTask, resolvesMutation = false): LiveVoiceVisibleTask {
    if (resolvesMutation) {
      this.mutationUnknown = false;
      this.pendingMutation = null;
    }
    this.lastVisibleTask = cloneTask(task);
    return cloneTask(task);
  }

  private rememberUnknownRunOutcome(
    pending: PendingMutation,
    message: string,
    conflict = false,
    task?: LiveVoiceVisibleTask,
    conflictingTaskId?: string
  ): TaskMutationAttempt {
    this.mutationUnknown = true;
    this.pendingMutation = { ...pending };
    return {
      ok: false,
      code: conflict ? 'recovery-conflict' : 'mutation-outcome-unknown',
      mutationUnknown: true,
      conflict,
      conflictingTaskId: conflict ? conflictingTaskId ?? task?.taskId : undefined,
      commandId: pending.commandId,
      task,
      message: conflict
        ? `命令 ${pending.commandId} 的恢复结果发生冲突，已禁止继续创建。${message}`
        : `任务可能已经创建，命令 ID 为 ${pending.commandId}。后续只会使用同一 ID 重放或核对，不会盲目创建重复任务。${message}`,
    };
  }

  private observeRunPayload(
    payload: unknown,
    pending: PendingMutation,
    forbiddenTaskId?: string,
    fromRecovery = false
  ): TaskMutationAttempt | null {
    const parsed = parseGatewayPayload(payload);
    if (!parsed.record) return null;

    if (parsed.code === 'IDEMPOTENCY_CONFLICT') {
      return this.rememberUnknownRunOutcome(
        pending,
        `服务端报告 idempotency conflict：${parsed.error ?? 'unknown'}`,
        true,
        undefined,
        parsed.existingTaskId ?? undefined
      );
    }
    if (!parsed.taskId) {
      if (parsed.error) {
        return {
          ok: false,
          code: parsed.code ?? 'gateway-business-error',
          message: parsed.error,
          commandId: pending.commandId,
        };
      }
      return null;
    }

    const candidate = this.makeTask(
      parsed.taskId,
      pending.commandId,
      pending.query,
      parsed.status,
      'schedule.run',
      parsed.executionTarget,
      parsed.idempotentReplay ? 'idempotent-replay' : fromRecovery ? 'same-key-retry' : 'fresh',
      parsed.idempotentReplay || fromRecovery ? 'recovered' : 'not-needed'
    );
    if (parsed.taskId === forbiddenTaskId) {
      return this.rememberUnknownRunOutcome(pending, 'successor 返回了与前任务相同的 task_id。', true, candidate);
    }
    const targetConflict = executionTargetConflict(this.gateway.owner, null, parsed.executionTarget);
    if (targetConflict) {
      candidate.recoveryStatus = 'conflict';
      return this.rememberUnknownRunOutcome(pending, targetConflict, true, candidate);
    }

    const task = this.rememberTask(candidate, true);
    if (parsed.error) {
      return {
        ok: false,
        code: parsed.code ?? 'gateway-business-error',
        message: parsed.error,
        commandId: pending.commandId,
        task,
      };
    }
    return {
      ok: true,
      code: parsed.idempotentReplay ? 'task-idempotent-replay' : 'task-started',
      message: parsed.idempotentReplay ? '已通过相同命令 ID 恢复任务' : '任务已启动',
      recovered: parsed.idempotentReplay || fromRecovery,
      commandId: pending.commandId,
      task,
    };
  }

  private async listExactCommand(pending: PendingMutation, forbiddenTaskId?: string): Promise<TaskMutationAttempt | null> {
    let payload: unknown;
    try {
      payload = await this.gateway.listByCommand(pending.commandId);
    } catch {
      return null;
    }
    const listed = parseExactKeyTaskList(payload);
    if (!listed.tasks) return null;
    if (listed.tasks.length === 0) return null;
    if (listed.tasks.length !== 1) {
      return this.rememberUnknownRunOutcome(pending, `exact-key list 返回 ${listed.tasks.length} 个任务。`, true);
    }

    const record = listed.tasks[0];
    const parsed = parseGatewayPayload(record);
    const listedQuery = toNonEmptyString(record.query);
    const listedPipeline = toNonEmptyString(record.pipeline);
    const listedCommandId = toNonEmptyString(record.idempotency_key);
    const listedNamespace = toNonEmptyString(record.origin_namespace);
    if (parsed.error) {
      return this.rememberUnknownRunOutcome(pending, `exact-key list 的任务记录包含业务错误：${parsed.error}`, true);
    }
    if (!parsed.taskId || normalizeIntentText(listedQuery) !== normalizeIntentText(pending.query)) {
      return this.rememberUnknownRunOutcome(pending, 'exact-key list 的任务 ID 或 query 与当前命令不一致。', true);
    }
    if (listedPipeline !== LIVE_VOICE_AUTO_HARNESS_PIPELINE) {
      return this.rememberUnknownRunOutcome(pending, 'exact-key list 的 pipeline 与当前命令不一致。', true);
    }
    if (listedCommandId !== pending.commandId) {
      return this.rememberUnknownRunOutcome(pending, 'exact-key list 返回了不同的 idempotency_key。', true);
    }
    if (listedNamespace !== 'live_voice') {
      return this.rememberUnknownRunOutcome(pending, 'exact-key list 返回了不同的 origin_namespace。', true);
    }

    const candidate = this.makeTask(
      parsed.taskId,
      pending.commandId,
      pending.query,
      parsed.status,
      'schedule.list',
      parsed.executionTarget,
      'exact-key-reconciliation',
      'recovered'
    );
    if (parsed.taskId === forbiddenTaskId) {
      candidate.recoveryStatus = 'conflict';
      return this.rememberUnknownRunOutcome(pending, 'exact-key list 返回了前任务 ID，无法证明 successor 已创建。', true, candidate);
    }
    const targetConflict = executionTargetConflict(this.gateway.owner, null, parsed.executionTarget);
    if (targetConflict) {
      candidate.recoveryStatus = 'conflict';
      return this.rememberUnknownRunOutcome(pending, targetConflict, true, candidate);
    }

    const task = this.rememberTask(candidate, true);
    return {
      ok: true,
      code: 'task-reconciled',
      message: '已按相同命令 ID 从 schedule.list 恢复真实任务',
      recovered: true,
      commandId: pending.commandId,
      task,
    };
  }

  private async recoverRun(
    pending: PendingMutation,
    forbiddenTaskId: string | undefined,
    initialMessage: string
  ): Promise<TaskMutationAttempt> {
    const beforeRetry = await this.listExactCommand(pending, forbiddenTaskId);
    if (beforeRetry) return beforeRetry;

    // The retry is safe because it uses the exact same server idempotency key.
    // Never issue a second run with a fresh key for this committed command.
    let retryPayload: unknown;
    try {
      retryPayload = await this.gateway.run({
        query: pending.query,
        pipeline: LIVE_VOICE_AUTO_HARNESS_PIPELINE,
        commandId: pending.commandId,
      });
    } catch (error) {
      const afterRetry = await this.listExactCommand(pending, forbiddenTaskId);
      return (
        afterRetry ??
        this.rememberUnknownRunOutcome(pending, `${initialMessage}；同 key 重试错误：${errorMessageFromThrown(error)}`)
      );
    }

    const observedRetry = this.observeRunPayload(retryPayload, pending, forbiddenTaskId, true);
    if (observedRetry) return observedRetry;
    const afterRetry = await this.listExactCommand(pending, forbiddenTaskId);
    return afterRetry ?? this.rememberUnknownRunOutcome(pending, `${initialMessage}；同 key 重试后仍无法核对结果。`);
  }

  private async runTask(pending: PendingMutation, forbiddenTaskId?: string): Promise<TaskMutationAttempt> {
    let payload: unknown;
    try {
      payload = await this.gateway.run({
        query: pending.query,
        pipeline: LIVE_VOICE_AUTO_HARNESS_PIPELINE,
        commandId: pending.commandId,
      });
    } catch (error) {
      return this.recoverRun(pending, forbiddenTaskId, `首次 run 错误：${errorMessageFromThrown(error)}`);
    }

    const observed = this.observeRunPayload(payload, pending, forbiddenTaskId);
    return observed ?? this.recoverRun(pending, forbiddenTaskId, '首次 run 响应缺少可核对 task_id');
  }

  /**
   * Status/cancel may inspect an unresolved create only through the exact-key
   * ledger. They must never retry schedule.run or silently fall back to an old
   * predecessor while a newer mutation remains unresolved.
   */
  private async reconcilePendingForControl(): Promise<TaskMutationAttempt | null> {
    const pending = this.pendingMutation;
    return pending ? this.listExactCommand(pending, pending.predecessorTaskId) : null;
  }

  private async cancelTask(task: LiveVoiceVisibleTask): Promise<TaskMutationAttempt> {
    let payload: unknown;
    try {
      payload = await this.gateway.cancel(task.taskId);
    } catch (error) {
      return {
        ok: false,
        code: 'gateway-threw',
        message: errorMessageFromThrown(error),
      };
    }

    const parsed = parseGatewayPayload(payload);
    if (!parsed.record) {
      return {
        ok: false,
        code: 'invalid-gateway-payload',
        message: parsed.error ?? '后端任务网关返回了无效 payload',
      };
    }
    if (parsed.taskId && parsed.taskId !== task.taskId) {
      return {
        ok: false,
        code: 'task-id-mismatch',
        message: `取消响应属于 ${parsed.taskId}，不是当前任务 ${task.taskId}。`,
      };
    }
    if (!parsed.taskId) {
      return {
        ok: false,
        code: 'task-id-mismatch',
        message: '取消响应没有 task_id，无法证明它命中当前任务。',
      };
    }

    const mergedExecutionTarget = mergeExecutionTarget(task.executionTarget, parsed.executionTarget);
    const targetConflict = executionTargetConflict(this.gateway.owner, task.executionTarget, mergedExecutionTarget);
    if (targetConflict) {
      return {
        ok: false,
        code: 'execution-target-conflict',
        message: targetConflict,
        commandId: task.commandId ?? undefined,
      };
    }
    const observedTask = this.rememberTask(
      this.makeTask(
        task.taskId,
        task.commandId,
        task.query,
        parsed.status,
        'schedule.cancel',
        mergedExecutionTarget,
        'cancel-observation',
        task.recoveryStatus
      )
    );
    if (parsed.error) {
      return {
        ok: false,
        code: 'gateway-business-error',
        message: parsed.error,
        task: observedTask,
      };
    }
    if (parsed.status.kind !== 'cancelled') {
      return {
        ok: false,
        code: 'cancel-not-confirmed',
        message: `取消响应的真实状态是 ${parsed.status.raw ?? 'unknown'}，未确认 cancelled。`,
        task: observedTask,
      };
    }

    return {
      ok: true,
      code: 'task-cancelled',
      message: '任务已取消',
      task: observedTask,
    };
  }

  private async handleCreate(query: string, command: ParsedCommand, captureKey: string): Promise<LiveVoiceTaskBridgeResult> {
    if (this.mutationUnknown) {
      const pending = this.pendingMutation;
      if (pending?.kind === 'create' && normalizeIntentText(pending.query) === normalizeIntentText(query)) {
        const recovered = await this.recoverRun(pending, undefined, '用户再次提交相同启动意图');
        if (recovered.ok && recovered.task) {
          return this.handledResult(
            'recovered',
            command,
            captureKey,
            feedback(
              'info',
              recovered.code,
              '已核对并恢复后台演进任务',
              `命令 ${pending.commandId} 对应真实 task_id ${recovered.task.taskId}。`
            ),
            { task: recovered.task, commandId: pending.commandId, recoveryStatus: 'recovered' }
          );
        }
        return this.handledResult(
          recovered.conflict ? 'recovery-conflict' : 'mutation-unknown',
          command,
          captureKey,
          feedback('error', recovered.code, recovered.conflict ? '任务恢复发生冲突' : '任务结果仍未核对', recovered.message),
          {
            task: recovered.task,
            commandId: pending.commandId,
            recoveryStatus: recovered.conflict ? 'conflict' : 'pending',
            conflictingTaskId: recovered.conflictingTaskId ?? (recovered.conflict ? recovered.task?.taskId : undefined),
          }
        );
      }
      return this.handledResult(
        'mutation-unknown',
        command,
        captureKey,
        feedback(
          'error',
          'mutation-outcome-unknown',
          '存在未核对的任务创建结果',
          '之前的任务可能已经创建但没有返回可用 task_id。为防止重复副作用，本会话不再启动新任务；请到后台任务列表核对。'
        ),
        {
          commandId: pending?.commandId,
          recoveryStatus: pending ? 'pending' : undefined,
        }
      );
    }
    if (this.lastVisibleTask && !this.lastVisibleTask.status.terminal) {
      return this.handledResult(
        'active-task-exists',
        command,
        captureKey,
        feedback(
          'warning',
          'active-task-exists',
          '已有未结束的可见任务',
          `任务 ${this.lastVisibleTask.taskId} 的最新真实状态是 ${this.lastVisibleTask.status.raw ?? 'unknown'}，未启动第二个任务。`
        ),
        { task: cloneTask(this.lastVisibleTask) }
      );
    }

    const pending = this.newPendingMutation('create', query);
    if (!pending) {
      return this.handledResult(
        'failed',
        command,
        captureKey,
        feedback('error', 'command-id-unavailable', '无法生成稳定命令 ID', '本次未发送后台请求，请重新提交。')
      );
    }
    const attempt = await this.runTask(pending);
    if (!attempt.ok || !attempt.task) {
      return this.handledResult(
        attempt.conflict ? 'recovery-conflict' : attempt.mutationUnknown ? 'mutation-unknown' : 'failed',
        command,
        captureKey,
        feedback('error', attempt.code, '后台演进任务未确认启动', attempt.message),
        {
          task: attempt.task,
          commandId: pending.commandId,
          recoveryStatus: attempt.conflict ? 'conflict' : attempt.mutationUnknown ? 'pending' : undefined,
          conflictingTaskId: attempt.conflictingTaskId ?? (attempt.conflict ? attempt.task?.taskId : undefined),
        }
      );
    }

    return this.handledResult(
      attempt.recovered ? 'recovered' : 'started',
      command,
      captureKey,
      feedback(
        'info',
        attempt.code,
        attempt.recovered ? '已恢复后台演进任务' : '后台演进任务已启动',
        `命令 ${pending.commandId} 的真实 task_id 为 ${attempt.task.taskId}，状态为 ${attempt.task.status.raw ?? 'unknown'}。`
      ),
      { task: attempt.task, commandId: pending.commandId, recoveryStatus: attempt.task.recoveryStatus }
    );
  }

  private async handleStatus(command: ParsedCommand, captureKey: string): Promise<LiveVoiceTaskBridgeResult> {
    let current = this.lastVisibleTask;
    if (this.mutationUnknown) {
      const pending = this.pendingMutation;
      const reconciled = await this.reconcilePendingForControl();
      if (reconciled?.ok && reconciled.task) {
        current = reconciled.task;
      } else {
        const conflict = reconciled?.conflict === true;
        return this.handledResult(
          conflict ? 'recovery-conflict' : 'mutation-unknown',
          command,
          captureKey,
          feedback(
            'error',
            reconciled?.code ?? 'mutation-outcome-unknown',
            conflict ? '未决任务核对发生冲突' : '任务可能已创建，但语音侧没有 ID',
            reconciled?.message ??
              '之前的启动或替换没有返回可核对的 task_id；本次只检查了 exact-key 列表，没有查询旧任务或重放 run。请到后台任务列表核对。'
          ),
          {
            commandId: pending?.commandId,
            recoveryStatus: conflict ? 'conflict' : 'pending',
            conflictingTaskId: reconciled?.conflictingTaskId,
            predecessorTaskId: pending?.predecessorTaskId,
            predecessorCancelled: pending?.predecessorCancelled,
          }
        );
      }
    }
    if (!current) {
      return this.handledResult(
        'no-visible-task',
        command,
        captureKey,
        feedback('warning', 'no-visible-task', '没有可查询的任务', '尚未保存任何真实 task_id，本次没有发送状态请求。')
      );
    }

    let payload: unknown;
    try {
      payload = await this.gateway.status(current.taskId);
    } catch (error) {
      return this.handledResult('failed', command, captureKey, feedback('error', 'gateway-threw', '任务进度查询失败', errorMessageFromThrown(error)), {
        task: cloneTask(current),
      });
    }

    const parsed = parseGatewayPayload(payload);
    if (!parsed.record) {
      return this.handledResult(
        'failed',
        command,
        captureKey,
        feedback('error', 'invalid-gateway-payload', '任务进度响应无效', parsed.error ?? '后端任务网关返回了无效 payload'),
        { task: cloneTask(current) }
      );
    }
    if (parsed.taskId && parsed.taskId !== current.taskId) {
      return this.handledResult(
        'failed',
        command,
        captureKey,
        feedback('error', 'task-id-mismatch', '任务进度响应 ID 不匹配', `响应属于 ${parsed.taskId}，不是当前任务 ${current.taskId}。`),
        { task: cloneTask(current) }
      );
    }
    if (parsed.error) {
      return this.handledResult('failed', command, captureKey, feedback('error', 'gateway-business-error', '任务进度查询失败', parsed.error), {
        task: cloneTask(current),
      });
    }
    if (!parsed.taskId) {
      return this.handledResult(
        'failed',
        command,
        captureKey,
        feedback('error', 'task-id-mismatch', '任务进度响应缺少 ID', '响应没有 task_id，不能将状态归属到当前任务。'),
        { task: cloneTask(current) }
      );
    }

    const mergedExecutionTarget = mergeExecutionTarget(current.executionTarget, parsed.executionTarget);
    const targetConflict = executionTargetConflict(this.gateway.owner, current.executionTarget, mergedExecutionTarget);
    if (targetConflict) {
      return this.handledResult(
        'failed',
        command,
        captureKey,
        feedback('error', 'execution-target-conflict', '任务进度响应目标冲突', targetConflict),
        { task: cloneTask(current) }
      );
    }
    const observedTask = this.rememberTask(
      this.makeTask(
        current.taskId,
        current.commandId,
        current.query,
        parsed.status,
        'schedule.status',
        mergedExecutionTarget,
        'status-observation',
        current.recoveryStatus
      )
    );
    return this.handledResult(
      'status',
      command,
      captureKey,
      feedback(
        'info',
        'task-status-observed',
        '已获取真实任务状态',
        `任务 ${observedTask.taskId} 的状态是 ${observedTask.status.kind}/${observedTask.status.raw ?? 'unknown'}。`
      ),
      { task: observedTask }
    );
  }

  private async handleCancel(command: ParsedCommand, captureKey: string): Promise<LiveVoiceTaskBridgeResult> {
    let current = this.lastVisibleTask;
    if (this.mutationUnknown) {
      const pending = this.pendingMutation;
      const reconciled = await this.reconcilePendingForControl();
      if (reconciled?.ok && reconciled.task) {
        current = reconciled.task;
      } else {
        const conflict = reconciled?.conflict === true;
        return this.handledResult(
          conflict ? 'recovery-conflict' : 'mutation-unknown',
          command,
          captureKey,
          feedback(
            'error',
            reconciled?.code ?? 'mutation-outcome-unknown',
            conflict ? '未决任务核对发生冲突' : '任务可能已创建，但语音侧没有 ID',
            reconciled?.message ??
              '之前的启动或替换没有返回可核对的 task_id；本次只检查了 exact-key 列表，没有取消旧任务或重放 run。请到后台任务列表核对。'
          ),
          {
            commandId: pending?.commandId,
            recoveryStatus: conflict ? 'conflict' : 'pending',
            conflictingTaskId: reconciled?.conflictingTaskId,
            predecessorTaskId: pending?.predecessorTaskId,
            predecessorCancelled: pending?.predecessorCancelled,
          }
        );
      }
    }
    if (!current) {
      return this.handledResult(
        'no-visible-task',
        command,
        captureKey,
        feedback('warning', 'no-visible-task', '没有可取消的任务', '尚未保存任何真实 task_id，本次没有发送取消请求。')
      );
    }
    if (current.status.terminal) {
      return this.handledResult(
        'already-terminal',
        command,
        captureKey,
        feedback(
          'info',
          'task-already-terminal',
          '任务已经结束',
          `任务 ${current.taskId} 已是 ${current.status.kind}/${current.status.raw ?? 'unknown'}，未重复发送取消。`
        ),
        { task: cloneTask(current) }
      );
    }

    const attempt = await this.cancelTask(current);
    if (!attempt.ok || !attempt.task) {
      return this.handledResult('failed', command, captureKey, feedback('error', attempt.code, '后台任务未确认取消', attempt.message), {
        task: attempt.task ?? cloneTask(current),
      });
    }

    return this.handledResult(
      'cancelled',
      command,
      captureKey,
      feedback('info', 'task-cancelled', '后台任务已取消', `任务 ${attempt.task.taskId} 的真实状态是 ${attempt.task.status.raw ?? 'unknown'}。`),
      { task: attempt.task, predecessorTaskId: attempt.task.taskId }
    );
  }

  private async handleReplace(query: string, command: ParsedCommand, captureKey: string): Promise<LiveVoiceTaskBridgeResult> {
    if (this.mutationUnknown) {
      const pending = this.pendingMutation;
      if (pending?.kind === 'replace' && normalizeIntentText(pending.query) === normalizeIntentText(query)) {
        const recovered = await this.recoverRun(pending, pending.predecessorTaskId, '用户再次提交相同替换意图');
        if (recovered.ok && recovered.task) {
          return this.handledResult(
            'recovered',
            command,
            captureKey,
            feedback(
              'info',
              recovered.code,
              '已核对并恢复 successor',
              `命令 ${pending.commandId} 对应真实 successor ${recovered.task.taskId}。`
            ),
            {
              task: recovered.task,
              commandId: pending.commandId,
              recoveryStatus: 'recovered',
              predecessorTaskId: pending.predecessorTaskId,
              successorTaskId: recovered.task.taskId,
              predecessorCancelled: pending.predecessorCancelled,
            }
          );
        }
        return this.handledResult(
          recovered.conflict ? 'recovery-conflict' : 'mutation-unknown',
          command,
          captureKey,
          feedback('error', recovered.code, recovered.conflict ? 'successor 恢复发生冲突' : 'successor 结果仍未核对', recovered.message),
          {
            task: recovered.task,
            commandId: pending.commandId,
            recoveryStatus: recovered.conflict ? 'conflict' : 'pending',
            predecessorTaskId: pending.predecessorTaskId,
            successorTaskId: recovered.conflict ? undefined : recovered.task?.taskId,
            conflictingTaskId: recovered.conflictingTaskId ?? (recovered.conflict ? recovered.task?.taskId : undefined),
            predecessorCancelled: pending.predecessorCancelled,
          }
        );
      }
      return this.handledResult(
        'mutation-unknown',
        command,
        captureKey,
        feedback(
          'error',
          'mutation-outcome-unknown',
          '存在未核对的任务创建结果',
          '之前的任务可能已经创建但没有返回可用 task_id。为防止重复副作用，本会话不再替换任务；请到后台任务列表核对。'
        ),
        {
          commandId: pending?.commandId,
          recoveryStatus: pending ? 'pending' : undefined,
          predecessorTaskId: pending?.predecessorTaskId,
          predecessorCancelled: pending?.predecessorCancelled,
        }
      );
    }
    const predecessor = this.lastVisibleTask;
    if (!predecessor) {
      return this.handledResult(
        'no-visible-task',
        command,
        captureKey,
        feedback('warning', 'no-visible-task', '没有可替换的任务', '尚未保存前任务的真实 task_id，本次没有发送任何请求。')
      );
    }
    if (predecessor.status.terminal) {
      return this.handledResult(
        'already-terminal',
        command,
        captureKey,
        feedback(
          'warning',
          'predecessor-already-terminal',
          '前任务已经结束',
          `任务 ${predecessor.taskId} 已是 ${predecessor.status.kind}/${predecessor.status.raw ?? 'unknown'}；请改用明确启动口令创建新任务。`
        ),
        { task: cloneTask(predecessor), predecessorTaskId: predecessor.taskId }
      );
    }

    const pending = this.newPendingMutation('replace', query);
    if (!pending) {
      return this.handledResult(
        'failed',
        command,
        captureKey,
        feedback('error', 'command-id-unavailable', '无法生成稳定命令 ID', '本次未发送取消或创建请求，请重新提交。'),
        { task: cloneTask(predecessor), predecessorTaskId: predecessor.taskId, predecessorCancelled: false }
      );
    }

    const cancelled = await this.cancelTask(predecessor);
    if (!cancelled.ok || !cancelled.task) {
      return this.handledResult('failed', command, captureKey, feedback('error', cancelled.code, '前任务未确认取消，未创建 successor', cancelled.message), {
        task: cancelled.task ?? cloneTask(predecessor),
        commandId: pending.commandId,
        predecessorTaskId: predecessor.taskId,
        predecessorCancelled: false,
      });
    }

    pending.predecessorTaskId = predecessor.taskId;
    pending.predecessorCancelled = true;
    const successor = await this.runTask(pending, predecessor.taskId);
    if (!successor.ok || !successor.task) {
      return this.handledResult(
        successor.conflict ? 'recovery-conflict' : successor.mutationUnknown ? 'mutation-unknown' : 'failed',
        command,
        captureKey,
        feedback('error', successor.code, '前任务已取消，但 successor 创建失败', `前任务 ${predecessor.taskId} 已取消；新任务未确认启动：${successor.message}`),
        {
          task: successor.task ?? cancelled.task,
          commandId: pending.commandId,
          recoveryStatus: successor.conflict ? 'conflict' : successor.mutationUnknown ? 'pending' : undefined,
          predecessorTaskId: predecessor.taskId,
          successorTaskId: successor.conflict ? undefined : successor.task?.taskId,
          conflictingTaskId: successor.conflictingTaskId ?? (successor.conflict ? successor.task?.taskId : undefined),
          predecessorCancelled: true,
        }
      );
    }

    return this.handledResult(
      successor.recovered ? 'recovered' : 'replaced',
      command,
      captureKey,
      feedback(
        'info',
        'task-replaced-with-successor',
        '已取消前任务并创建 successor',
        `前任务 ${predecessor.taskId} 已取消；successor 任务为 ${successor.task.taskId}。`
      ),
      {
        task: successor.task,
        commandId: pending.commandId,
        recoveryStatus: successor.task.recoveryStatus,
        predecessorTaskId: predecessor.taskId,
        successorTaskId: successor.task.taskId,
        predecessorCancelled: true,
      }
    );
  }
}
