/** Passive Native work observations; never Task, history or presentation authority. */
import type { ProductWebP2ActivationBinding } from './productWebActivation.js';

export const NATIVE_WORK_STATE_VERSION = 'live-voice.native-work-state.v1';
export const NATIVE_WORK_STATES = ['accepted', 'running', 'cancelling', 'completed', 'cancelled', 'superseded', 'failed', 'unknown'] as const;
export type NativeWorkPhase = typeof NATIVE_WORK_STATES[number];
export type NativeWorkObservation = Readonly<{
  work_id: string; revision: number; sequence: number; state: NativeWorkPhase; execution_settled: boolean;
}>;
export type NativeWorkStateSnapshot = Readonly<ProductWebP2ActivationBinding & {
  sequence: number; works: readonly NativeWorkObservation[];
}>;
export type NativeWorkStateNotification = Readonly<NativeWorkStateSnapshot & { kind: 'native_work_state' }>;

function invalid(): never { throw new Error('PRODUCT_NATIVE_WORK_STATE_INVALID'); }
function closed(value: unknown, keys: readonly string[]): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return invalid();
  const record = value as Record<string, unknown>;
  if (Object.keys(record).length !== keys.length || keys.some(key => !Object.prototype.hasOwnProperty.call(record, key))) return invalid();
  return record;
}
function id(value: unknown): string {
  if (typeof value !== 'string' || !value || value.trim() !== value || new TextEncoder().encode(value).length > 256 ||
      /[\u0000-\u001f\u007f\ud800-\udfff]/u.test(value)) return invalid();
  return value;
}
function positive(value: unknown): number {
  if (!Number.isSafeInteger(value) || (value as number) <= 0) return invalid();
  return value as number;
}
export function parseNativeWorkStateNotification(value: unknown): NativeWorkStateNotification {
  const packet = closed(value, ['status', 'kind', 'request_id', 'round_id', 'response', 'work_state',
    'agent_event', 'source_event', 'progress_event', 'presentation_unit', 'audio', 'error_reason', 'publish_seq',
    'session_id', 'correlation_id', 'interaction_id', 'activation_id', 'activation_generation', 'sequence_effect']);
  if (packet.status !== 'notification' || packet.kind !== 'native.work_state' || packet.sequence_effect !== 'neutral' ||
      ['round_id', 'response', 'agent_event', 'source_event', 'progress_event', 'presentation_unit', 'audio', 'error_reason', 'publish_seq']
        .some(key => packet[key] !== null)) return invalid();
  id(packet.request_id);
  const state = closed(packet.work_state, ['contract_version', 'sequence', 'works']);
  if (state.contract_version !== NATIVE_WORK_STATE_VERSION || !Array.isArray(state.works) || state.works.length > 32) return invalid();
  const identities = new Set<string>();
  const works = state.works.map(raw => {
    const row = closed(raw, ['work_id', 'revision', 'sequence', 'state', 'execution_settled']);
    const workId = id(row.work_id);
    if (identities.has(workId) || !NATIVE_WORK_STATES.includes(row.state as NativeWorkPhase) || typeof row.execution_settled !== 'boolean') return invalid();
    identities.add(workId);
    return Object.freeze({ work_id: workId, revision: positive(row.revision), sequence: positive(row.sequence),
      state: row.state as NativeWorkPhase, execution_settled: row.execution_settled });
  });
  return Object.freeze({ kind: 'native_work_state', session_id: id(packet.session_id), correlation_id: id(packet.correlation_id),
    interaction_id: id(packet.interaction_id), activation_id: id(packet.activation_id), activation_generation: positive(packet.activation_generation),
    sequence: positive(state.sequence), works: Object.freeze(works) });
}
export function nativeWorkBindingMatches(state: NativeWorkStateSnapshot, binding: Readonly<ProductWebP2ActivationBinding> | null): boolean {
  return binding !== null && state.session_id === binding.session_id && state.correlation_id === binding.correlation_id &&
    state.interaction_id === binding.interaction_id && state.activation_id === binding.activation_id && state.activation_generation === binding.activation_generation;
}
export function nativeWorkSnapshotAdvances(previous: NativeWorkStateSnapshot | null, next: NativeWorkStateSnapshot): boolean {
  if (previous === null || !nativeWorkBindingMatches(previous, next)) return true;
  if (next.sequence <= previous.sequence) return false;
  return next.works.every(row => {
    const prior = previous.works.find(item => item.work_id === row.work_id);
    return prior === undefined || (row.revision >= prior.revision && row.sequence >= prior.sequence &&
      (row.sequence !== prior.sequence || (row.revision === prior.revision && row.state === prior.state && row.execution_settled === prior.execution_settled)));
  });
}
