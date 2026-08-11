import type { FormalTaskControlBinding } from './formalTaskControlLeaf';

const PRODUCT_P3_TASK_TARGET_CONTRACT = 'live-voice.product-p3-task-target.v1' as const;
const PRODUCT_P3_TASK_TARGET_STORAGE_PREFIX = 'jiuwenswarm.live_voice.product_p3_task_target.v1:';
const PRODUCT_P3_TASK_TARGET_MAX_TEXT_CHARS = 4_096;
const PRODUCT_P3_TASK_TARGET_MAX_SERIALIZED_CHARS = 32_768;

export type ProductP3TaskTargetJournalStore = Pick<Storage, 'getItem' | 'setItem'>;

export type ProductP3TaskTargetJournalRecord = Readonly<{
  contract_version: typeof PRODUCT_P3_TASK_TARGET_CONTRACT;
  session_id: string;
  correlation_id: string;
  task_id: string;
  task_control_binding: FormalTaskControlBinding;
}>;

function requiredText(value: unknown): string {
  if (typeof value !== 'string' || !value.trim() || value.length > PRODUCT_P3_TASK_TARGET_MAX_TEXT_CHARS) {
    throw new Error('product P3 task target text is invalid');
  }
  return value;
}

function storageKey(sessionId: string): string {
  return `${PRODUCT_P3_TASK_TARGET_STORAGE_PREFIX}${encodeURIComponent(requiredText(sessionId))}`;
}

function browserStorage(): ProductP3TaskTargetJournalStore {
  if (typeof window === 'undefined' || !window.sessionStorage) {
    throw new Error('product P3 task target storage is unavailable');
  }
  return window.sessionStorage;
}

function freezeRecord(input: {
  session_id: unknown;
  correlation_id: unknown;
  task_id: unknown;
  task_control_binding: unknown;
}): ProductP3TaskTargetJournalRecord {
  const sessionId = requiredText(input.session_id);
  const correlationId = requiredText(input.correlation_id);
  const taskId = requiredText(input.task_id);
  const rawBinding = input.task_control_binding;
  if (rawBinding === null || typeof rawBinding !== 'object' || Array.isArray(rawBinding)) {
    throw new Error('product P3 task control binding is invalid');
  }
  const binding = rawBinding as Record<string, unknown>;
  const bindingKeys = Object.keys(binding).sort();
  const expectedBindingKeys = ['correlation_id', 'generation', 'project_id', 'session_id', 'subject_id'];
  if (bindingKeys.length !== expectedBindingKeys.length || bindingKeys.some((key, index) => key !== expectedBindingKeys[index])) {
    throw new Error('product P3 task control binding shape is invalid');
  }
  const generation = binding.generation;
  if (!Number.isSafeInteger(generation) || Number(generation) <= 0) {
    throw new Error('product P3 task control generation is invalid');
  }
  const frozenBinding = Object.freeze({
    subject_id: requiredText(binding.subject_id),
    session_id: requiredText(binding.session_id),
    project_id: requiredText(binding.project_id),
    correlation_id: requiredText(binding.correlation_id),
    generation: Number(generation),
  });
  if (frozenBinding.session_id !== sessionId || frozenBinding.correlation_id !== correlationId) {
    throw new Error('product P3 task target scope is invalid');
  }
  return Object.freeze({
    contract_version: PRODUCT_P3_TASK_TARGET_CONTRACT,
    session_id: sessionId,
    correlation_id: correlationId,
    task_id: taskId,
    task_control_binding: frozenBinding,
  });
}

/**
 * Persist one exact, credential-free P3 task target for this browser tab. The
 * server remains authoritative: a refreshed page must validate status/history
 * before publishing this hint back into the product UI.
 */
export function persistProductP3TaskTarget(
  input: Omit<ProductP3TaskTargetJournalRecord, 'contract_version'>,
  storage?: ProductP3TaskTargetJournalStore
): boolean {
  try {
    const record = freezeRecord(input);
    (storage ?? browserStorage()).setItem(storageKey(record.session_id), JSON.stringify(record));
    return true;
  } catch {
    return false;
  }
}

/** Read only the exact Session/correlation target; stale or malformed hints fail closed. */
export function readProductP3TaskTarget(
  input: Readonly<{ session_id: string; correlation_id: string }>,
  storage?: ProductP3TaskTargetJournalStore
): ProductP3TaskTargetJournalRecord | null {
  try {
    const sessionId = requiredText(input.session_id);
    const correlationId = requiredText(input.correlation_id);
    const serialized = (storage ?? browserStorage()).getItem(storageKey(sessionId));
    if (serialized === null) return null;
    if (serialized.length > PRODUCT_P3_TASK_TARGET_MAX_SERIALIZED_CHARS) return null;
    const raw: unknown = JSON.parse(serialized);
    if (raw === null || typeof raw !== 'object' || Array.isArray(raw)) return null;
    const record = raw as Record<string, unknown>;
    const keys = Object.keys(record).sort();
    const expectedKeys = ['contract_version', 'correlation_id', 'session_id', 'task_control_binding', 'task_id'];
    if (
      keys.length !== expectedKeys.length ||
      keys.some((key, index) => key !== expectedKeys[index]) ||
      record.contract_version !== PRODUCT_P3_TASK_TARGET_CONTRACT
    ) {
      return null;
    }
    const frozen = freezeRecord({
      session_id: record.session_id,
      correlation_id: record.correlation_id,
      task_id: record.task_id,
      task_control_binding: record.task_control_binding,
    });
    if (frozen.session_id !== sessionId || frozen.correlation_id !== correlationId) return null;
    return frozen;
  } catch {
    return null;
  }
}
