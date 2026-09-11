import { parseNativeWorkStateNotification, type NativeWorkStateNotification } from './nativeWorkState';
import { parseEventEnvelope } from './liveVoiceContractV2';
import { taskNotificationSourceKey } from './taskNotificationIdentity';

export type ProductPresentationAckInput = {
  response_id: string;
  response_generation: number;
  surface: 'text' | 'audio';
  unit_id: string;
  contiguous_cursor: number;
};

export type ProductP2NotificationDisposition =
  | NativeWorkStateNotification
  | { readonly kind: 'continue' }
  | {
      readonly kind: 'native_task_association';
      readonly session_id: string;
      readonly correlation_id: string;
      readonly interaction_id: string;
      readonly activation_id: string;
      readonly activation_generation: number;
      readonly task_id: string;
      readonly turn_commit_id: string;
      readonly provider_call_id: string;
    }
  | {
      readonly kind: 'failed';
      readonly reason: string;
      readonly response?: Readonly<{
        interaction_id: string;
        response_id: string;
        response_generation: number;
      }>;
    }
  | {
      readonly kind: 'presentation';
      readonly text: string;
      readonly response_id: string;
      readonly response: Readonly<{
        interaction_id: string;
        response_id: string;
        response_generation: number;
      }>;
      readonly unit_id: string;
      readonly history_message_id: string | null;
      readonly task_notification_event_key?: string | null;
      readonly task_notification_text_sha256?: string | null;
      readonly ack: ProductPresentationAckInput;
      readonly replayed: boolean;
      readonly task_notification: boolean;
      readonly task_id: string | null;
      readonly task_notification_terminal: boolean;
      readonly adjustment_notification: boolean;
    }
  | {
      readonly kind: 'native_audio';
      readonly response_id: string;
      readonly response: Readonly<{
        interaction_id: string;
        response_id: string;
        response_generation: number;
      }>;
      readonly unit_id: string;
      readonly presentation_unit: Readonly<Record<string, unknown>>;
      readonly audio: Readonly<Record<string, unknown>>;
    }
  | {
      readonly kind: 'native_user_transcript';
      readonly session_id: string;
      readonly correlation_id: string;
      readonly interaction_id: string;
      readonly activation_id: string;
      readonly activation_generation: number;
      readonly message: Readonly<{
        id: string;
        role: 'user';
        content: string;
        timestamp: string;
        nativeTurnKey: string;
      }>;
      readonly following_assistant: readonly Readonly<{
        id: string;
        role: 'assistant';
        content: string;
        timestamp: string;
      }>[];
    }
  | {
      readonly kind: 'native_request_state';
      readonly response: Readonly<{ interaction_id: string; response_id: string; response_generation: number }> | null;
      readonly session_id: string; readonly correlation_id: string; readonly interaction_id: string;
      readonly activation_id: string; readonly activation_generation: number;
      readonly turn_id: string; readonly sequence: number;
      readonly phase: 'processing' | 'interrupted' | 'failed'; readonly reason: string | null;
    };

export function recordValue(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

export function hasExactFields(value: Readonly<Record<string, unknown>>, fields: readonly string[]): boolean {
  const actual = Object.keys(value).sort();
  const expected = [...fields].sort();
  return actual.length === expected.length && actual.every((field, index) => field === expected[index]);
}

export function classifyProductP2Notification(notification: Readonly<Record<string, unknown>>, hasPresentedOutput = false): ProductP2NotificationDisposition {
  if (notification.kind === 'native.work_state') {
    try { return parseNativeWorkStateNotification(notification); }
    catch { return { kind: 'continue' }; }
  }
  const event = recordValue(notification.agent_event);
  const unit = recordValue(notification.presentation_unit);
  const response = recordValue(notification.response);
  const taskNotification = event?.source_provenance === 'server.task_notification';
  let taskTerminal = false;
  let notificationTaskId: string | null = null;
  if (taskNotification && notification.source_event != null) {
    try {
      const source = parseEventEnvelope(notification.source_event);
      if (source.stream_ref.kind !== 'task' || source.scope.assurance !== 'authenticated' ||
          source.scope.session_id !== notification.session_id || source.scope.project_id === null) throw new Error('Task source binding mismatch');
      taskTerminal = source.payload.state === 'terminal';
      notificationTaskId = source.stream_ref.id;
    } catch {
      return { kind: 'failed', reason: 'PRODUCT_TASK_NOTIFICATION_SOURCE_INVALID' };
    }
  }
  const presentationSurface = unit?.surface === 'text' || (unit?.surface === 'audio' && taskNotification) ? unit.surface : null;
  const errorReason =
    typeof notification.error_reason === 'string' ? notification.error_reason : typeof event?.error_reason === 'string' ? event.error_reason : null;
  const responseBinding =
    typeof response?.interaction_id === 'string' &&
    typeof response.response_id === 'string' &&
    Number.isSafeInteger(response.response_generation)
      ? Object.freeze({
          interaction_id: response.interaction_id,
          response_id: response.response_id,
          response_generation: response.response_generation as number,
        })
      : null;
  if (notification.kind === 'native.request_state') {
    const state = recordValue(notification.request_state);
    const validId = (value: unknown): value is string => typeof value === 'string' && value.length > 0 && value.length <= 256 && value.trim() === value && !/[\u0000-\u001f\u007f]/u.test(value);
    if (!hasExactFields(notification, ['status', 'kind', 'request_id', 'round_id', 'response', 'request_state',
      'agent_event', 'source_event', 'progress_event', 'presentation_unit', 'audio', 'error_reason', 'publish_seq',
      'session_id', 'correlation_id', 'interaction_id', 'activation_id', 'activation_generation', 'sequence_effect']) ||
      notification.status !== 'notification' || notification.sequence_effect !== 'neutral' ||
      !validId(notification.request_id) || !validId(notification.session_id) || !validId(notification.correlation_id) ||
      !validId(notification.interaction_id) || !validId(notification.activation_id) ||
      !Number.isSafeInteger(notification.activation_generation) || (notification.activation_generation as number) <= 0 ||
      state === null || !hasExactFields(state, ['turn_id', 'sequence', 'phase', 'reason']) || !validId(state.turn_id) ||
      !Number.isSafeInteger(state.sequence) || (state.sequence as number) <= 0 ||
      !['processing', 'interrupted', 'failed'].includes(String(state.phase)) ||
      (state.phase === 'failed' ? typeof state.reason !== 'string' || !/^[A-Z][A-Z0-9_]{1,119}$/u.test(state.reason) : state.reason !== null) ||
      (state.phase === 'interrupted' ? (response === null || !hasExactFields(response, ['interaction_id', 'response_id', 'response_generation']) ||
        responseBinding === null || responseBinding.interaction_id !== notification.interaction_id || !validId(responseBinding.response_id) || responseBinding.response_generation < 1) : notification.response !== null) ||
      ['round_id', 'agent_event', 'source_event', 'progress_event', 'presentation_unit', 'audio', 'error_reason', 'publish_seq'].some(key => notification[key] !== null)) {
      return { kind: 'failed', reason: 'PRODUCT_NATIVE_REQUEST_STATE_INVALID' };
    }
    return { kind: 'native_request_state', response: responseBinding, session_id: notification.session_id, correlation_id: notification.correlation_id,
      interaction_id: notification.interaction_id, activation_id: notification.activation_id,
      activation_generation: notification.activation_generation as number, turn_id: state.turn_id,
      sequence: state.sequence as number, phase: state.phase as 'processing' | 'interrupted' | 'failed', reason: state.reason as string | null };
  }
  if (notification.kind === 'native.task_association') {
    const association = recordValue(notification.task_association);
    const validId = (value: unknown): value is string => typeof value === 'string' && value.trim() === value && value.length > 0 &&
      new TextEncoder().encode(value).length <= 256 && !/[\u0000-\u001f\u007f]/u.test(value);
    if (
      !hasExactFields(notification, ['status', 'kind', 'request_id', 'round_id', 'response', 'task_association',
        'agent_event', 'source_event', 'progress_event', 'presentation_unit', 'audio', 'error_reason', 'publish_seq',
        'session_id', 'correlation_id', 'interaction_id', 'activation_id', 'activation_generation', 'sequence_effect']) ||
      notification.status !== 'notification' || notification.sequence_effect !== 'neutral' ||
      !validId(notification.request_id) || !validId(notification.session_id) || !validId(notification.correlation_id) ||
      !validId(notification.interaction_id) || !validId(notification.activation_id) ||
      !Number.isSafeInteger(notification.activation_generation) || (notification.activation_generation as number) <= 0 ||
      response === null || !hasExactFields(response, ['interaction_id', 'response_id', 'response_generation']) ||
      responseBinding === null || responseBinding.interaction_id !== notification.interaction_id ||
      !validId(responseBinding.response_id) || responseBinding.response_generation < 0 ||
      association === null || !hasExactFields(association, ['task_id', 'turn_commit_id', 'provider_call_id']) ||
      !validId(association.task_id) || !validId(association.turn_commit_id) || !validId(association.provider_call_id) ||
      ['round_id', 'agent_event', 'source_event', 'progress_event', 'presentation_unit', 'audio', 'error_reason', 'publish_seq']
        .some(field => notification[field] !== null)
    ) return { kind: 'failed', reason: 'PRODUCT_NATIVE_TASK_ASSOCIATION_INVALID' };
    return Object.freeze({ kind: 'native_task_association', session_id: notification.session_id,
      correlation_id: notification.correlation_id, interaction_id: notification.interaction_id,
      activation_id: notification.activation_id, activation_generation: notification.activation_generation as number,
      task_id: association.task_id, turn_commit_id: association.turn_commit_id, provider_call_id: association.provider_call_id });
  }
  if (notification.kind === 'native.user_transcript') {
    const message = recordValue(event?.message);
    const binding = recordValue(event?.binding);
    const scope = recordValue(binding?.scope);
    const timestamp = message?.timestamp;
    const followingAssistant = event?.following_assistant;
    const timestampDate =
      typeof timestamp === 'number' && Number.isFinite(timestamp) && timestamp >= 0
        ? new Date(timestamp * 1_000)
        : null;
    const valid =
      hasExactFields(notification, [
        'status', 'kind', 'request_id', 'round_id', 'response', 'agent_event',
        'source_event', 'progress_event', 'presentation_unit', 'audio',
        'error_reason', 'publish_seq', 'session_id', 'correlation_id',
        'interaction_id', 'activation_id', 'activation_generation', 'sequence_effect',
      ]) &&
      notification.status === 'notification' &&
      notification.sequence_effect === 'neutral' &&
      typeof notification.request_id === 'string' && notification.request_id.trim().length > 0 &&
      notification.round_id === null &&
      notification.response === null &&
      notification.source_event === null &&
      notification.progress_event === null &&
      notification.presentation_unit === null &&
      notification.audio === null &&
      notification.error_reason === null &&
      notification.publish_seq === null &&
      typeof notification.session_id === 'string' && notification.session_id.trim().length > 0 &&
      typeof notification.correlation_id === 'string' && notification.correlation_id.trim().length > 0 &&
      typeof notification.interaction_id === 'string' && notification.interaction_id.trim().length > 0 &&
      typeof notification.activation_id === 'string' && notification.activation_id.trim().length > 0 &&
      Number.isSafeInteger(notification.activation_generation) &&
      (notification.activation_generation as number) > 0 &&
      event !== null &&
      (hasExactFields(event, ['event_type', 'message', 'binding']) ||
        hasExactFields(event, ['event_type', 'message', 'binding', 'following_assistant'])) &&
      event.event_type === 'chat.final' &&
      message !== null &&
      hasExactFields(message, ['id', 'role', 'content', 'timestamp']) &&
      typeof message.id === 'string' && message.id.trim().length > 0 &&
      message.role === 'user' &&
      typeof message.content === 'string' &&
      message.content.trim().length > 0 &&
      message.content === message.content.trim() &&
      timestampDate !== null &&
      Number.isFinite(timestampDate.getTime()) &&
      binding !== null &&
      hasExactFields(binding, [
        'scope', 'interaction_id', 'activation_id', 'activation_generation',
        'correlation_id', 'turn_id', 'commit_id', 'provider_session_id',
        'provider_item_id', 'provider_event_id',
      ]) &&
      scope !== null &&
      hasExactFields(scope, ['subject_id', 'project_id', 'session_id', 'assurance']) &&
      typeof scope.subject_id === 'string' && scope.subject_id.trim().length > 0 &&
      (scope.project_id === null || (typeof scope.project_id === 'string' && scope.project_id.trim().length > 0)) &&
      scope.session_id === notification.session_id &&
      (scope.assurance === 'request_asserted' || scope.assurance === 'authenticated') &&
      binding.interaction_id === notification.interaction_id &&
      binding.activation_id === notification.activation_id &&
      binding.activation_generation === notification.activation_generation &&
      binding.correlation_id === notification.correlation_id &&
      typeof binding.turn_id === 'string' && binding.turn_id.trim().length > 0 &&
      typeof binding.commit_id === 'string' && binding.commit_id.trim().length > 0 &&
      typeof binding.provider_session_id === 'string' && binding.provider_session_id.trim().length > 0 &&
      typeof binding.provider_item_id === 'string' && binding.provider_item_id.trim().length > 0 &&
      typeof binding.provider_event_id === 'string' && binding.provider_event_id.trim().length > 0 &&
      message.id === `live-voice:${binding.commit_id}:native-user` &&
      (followingAssistant === undefined || (Array.isArray(followingAssistant) && followingAssistant.length > 0));
    if (!valid) {
      return { kind: 'failed', reason: 'PRODUCT_NATIVE_USER_TRANSCRIPT_NOTIFICATION_INVALID' };
    }
    const parsedFollowing: Array<Readonly<{
      id: string;
      role: 'assistant';
      content: string;
      timestamp: string;
    }>> = [];
    for (const candidate of (followingAssistant ?? []) as unknown[]) {
      const projection = recordValue(candidate);
      const assistantMessage = recordValue(projection?.message);
      const assistantBinding = recordValue(projection?.binding);
      const assistantResponse = recordValue(assistantBinding?.response);
      const assistantTimestamp = assistantMessage?.timestamp;
      const assistantTimestampDate =
        typeof assistantTimestamp === 'number' && Number.isFinite(assistantTimestamp) && assistantTimestamp >= 0
          ? new Date(assistantTimestamp * 1_000)
          : null;
      if (
        projection === null ||
        !hasExactFields(projection, ['message', 'binding']) ||
        assistantMessage === null ||
        !hasExactFields(assistantMessage, ['id', 'role', 'content', 'timestamp']) ||
        typeof assistantMessage.id !== 'string' || !assistantMessage.id.trim() ||
        assistantMessage.role !== 'assistant' ||
        typeof assistantMessage.content !== 'string' || !assistantMessage.content.trim() ||
        assistantMessage.content !== assistantMessage.content.trim() ||
        assistantTimestampDate === null || !Number.isFinite(assistantTimestampDate.getTime()) ||
        assistantBinding === null ||
        !hasExactFields(assistantBinding, ['turn_id', 'response', 'surface', 'presented_at']) ||
        assistantBinding.turn_id !== binding.turn_id ||
        assistantBinding.surface !== 'native_audio' ||
        typeof assistantBinding.presented_at !== 'string' ||
        !assistantBinding.presented_at.trim() ||
        !Number.isFinite(Date.parse(assistantBinding.presented_at)) ||
        assistantResponse === null ||
        !hasExactFields(assistantResponse, ['interaction_id', 'response_id', 'response_generation']) ||
        assistantResponse.interaction_id !== notification.interaction_id ||
        typeof assistantResponse.response_id !== 'string' || !assistantResponse.response_id.trim() ||
        !Number.isSafeInteger(assistantResponse.response_generation) ||
        (assistantResponse.response_generation as number) <= 0
      ) {
        return { kind: 'failed', reason: 'PRODUCT_NATIVE_USER_TRANSCRIPT_NOTIFICATION_INVALID' };
      }
      parsedFollowing.push(Object.freeze({
        id: assistantMessage.id,
        role: 'assistant',
        content: assistantMessage.content,
        timestamp: assistantTimestampDate.toISOString(),
      }));
    }
    return {
      kind: 'native_user_transcript',
      session_id: notification.session_id as string,
      correlation_id: notification.correlation_id as string,
      interaction_id: notification.interaction_id as string,
      activation_id: notification.activation_id as string,
      activation_generation: notification.activation_generation as number,
      message: Object.freeze({
        id: message.id as string,
        role: 'user',
        content: message.content as string,
        timestamp: timestampDate!.toISOString(),
        nativeTurnKey: JSON.stringify([notification.interaction_id, binding!.turn_id]),
      }),
      following_assistant: Object.freeze(parsedFollowing),
    };
  }
  if (notification.kind === 'native.audio') {
    const unitResponse = recordValue(unit?.response);
    const audio = recordValue(notification.audio);
    const valid =
      hasExactFields(notification, [
        'status', 'kind', 'request_id', 'round_id', 'response', 'agent_event',
        'source_event', 'progress_event', 'presentation_unit', 'audio',
        'error_reason', 'publish_seq', 'session_id', 'correlation_id',
        'interaction_id', 'activation_id', 'activation_generation', 'sequence_effect',
      ]) &&
      notification.status === 'notification' &&
      notification.sequence_effect === 'neutral' &&
      typeof notification.request_id === 'string' && notification.request_id.trim().length > 0 &&
      notification.round_id === null &&
      notification.agent_event === null &&
      notification.source_event === null &&
      notification.progress_event === null &&
      notification.error_reason === null &&
      notification.publish_seq === null &&
      typeof notification.session_id === 'string' && notification.session_id.trim().length > 0 &&
      typeof notification.correlation_id === 'string' && notification.correlation_id.trim().length > 0 &&
      typeof notification.interaction_id === 'string' &&
      typeof notification.activation_id === 'string' && notification.activation_id.trim().length > 0 &&
      Number.isSafeInteger(notification.activation_generation) &&
      (notification.activation_generation as number) > 0 &&
      responseBinding !== null &&
      responseBinding.interaction_id === notification.interaction_id &&
      responseBinding.response_generation > 0 &&
      unit !== null &&
      hasExactFields(unit, [
        'response', 'surface', 'unit_id', 'seq', 'source_start_utf8',
        'source_end_utf8', 'content_ref',
      ]) &&
      unitResponse !== null &&
      hasExactFields(unitResponse, ['interaction_id', 'response_id', 'response_generation']) &&
      unitResponse.interaction_id === responseBinding.interaction_id &&
      unitResponse.response_id === responseBinding.response_id &&
      unitResponse.response_generation === responseBinding.response_generation &&
      unit.surface === 'audio' &&
      typeof unit.unit_id === 'string' && unit.unit_id.trim().length > 0 &&
      Number.isSafeInteger(unit.seq) && (unit.seq as number) >= 0 &&
      Number.isSafeInteger(unit.source_start_utf8) && (unit.source_start_utf8 as number) >= 0 &&
      Number.isSafeInteger(unit.source_end_utf8) &&
      (unit.source_end_utf8 as number) >= (unit.source_start_utf8 as number) &&
      typeof unit.content_ref === 'string' && /^sha256:[0-9a-f]{64}$/.test(unit.content_ref) &&
      audio !== null;
    if (!valid) {
      return responseBinding === null
        ? { kind: 'failed', reason: 'PRODUCT_NATIVE_AUDIO_NOTIFICATION_INVALID' }
        : { kind: 'failed', reason: 'PRODUCT_NATIVE_AUDIO_NOTIFICATION_INVALID', response: responseBinding };
    }
    return {
      kind: 'native_audio',
      response_id: responseBinding.response_id,
      response: responseBinding,
      unit_id: unit.unit_id as string,
      presentation_unit: Object.freeze({ ...unit, response: Object.freeze({ ...unitResponse }) }),
      // This object is the one-use handoff into P1. P1 must remove the private
      // media ticket immediately after creating its ticket consumer, so freezing
      // the handoff here makes an otherwise valid Gateway descriptor unusable.
      audio: { ...audio },
    };
  }
  if (
    notification.kind === 'agent.error' ||
    errorReason !== null ||
    (typeof event?.event_type === 'string' && /(?:error|failed|blocked)$/.test(event.event_type))
  ) {
    const reason = errorReason ?? 'PRODUCT_AGENT_OUTPUT_FAILED';
    return responseBinding === null ? { kind: 'failed', reason } : { kind: 'failed', reason, response: responseBinding };
  }
  if (
    notification.kind === 'agent.output' &&
    typeof event?.text === 'string' &&
    presentationSurface !== null &&
    unit !== null &&
    typeof unit.unit_id === 'string' &&
    Number.isSafeInteger(unit.seq) &&
    typeof response?.interaction_id === 'string' &&
    typeof response?.response_id === 'string' &&
    Number.isSafeInteger(response.response_generation)
  ) {
    const contentRef = typeof unit.content_ref === 'string' ? unit.content_ref : '';
    const contentDigest = /^sha256:([0-9a-f]{64})$/.exec(contentRef)?.[1] ?? null;
    return {
      kind: 'presentation',
      text: event.text,
      response_id: response.response_id,
      response: {
        interaction_id: response.interaction_id,
        response_id: response.response_id,
        response_generation: response.response_generation as number,
      },
      unit_id: unit.unit_id,
      history_message_id:
        contentDigest === null
          ? null
          : `live-voice:${response.interaction_id}:${response.response_id}:${response.response_generation}:${presentationSurface}:${unit.seq}:${unit.seq}:${contentDigest}`,
      replayed: hasPresentedOutput,
      task_notification_event_key: taskNotification ? taskNotificationSourceKey(notification.source_event, String(notification.session_id)) : null,
      task_notification_text_sha256: taskNotification ? contentDigest : null,
      task_notification: taskNotification,
      task_id: notificationTaskId,
      task_notification_terminal: taskTerminal,
      adjustment_notification: event.source_provenance === 'server.background.adjustment',
      ack: {
        response_id: response.response_id,
        response_generation: response.response_generation as number,
        surface: presentationSurface,
        unit_id: unit.unit_id,
        contiguous_cursor: unit.seq as number,
      },
    };
  }
  const progressEvent = recordValue(notification.progress_event);
  const progressPayload = recordValue(progressEvent?.payload);
  if (notification.kind === 'work.progress' && progressPayload?.state === 'terminal') {
    const outcome = progressPayload.outcome;
    const reason = typeof outcome === 'string' && ['completed', 'failed', 'cancelled', 'unknown'].includes(outcome)
      ? `PRODUCT_AGENT_TERMINAL_WITHOUT_FINAL_${outcome.toUpperCase()}`
      : 'PRODUCT_AGENT_TERMINAL_WITHOUT_FINAL';
    return hasPresentedOutput
      ? { kind: 'continue' }
      : responseBinding === null
        ? {
          kind: 'failed',
          reason,
          }
        : {
            kind: 'failed',
            reason,
            response: responseBinding,
          };
  }
  return { kind: 'continue' };
}
