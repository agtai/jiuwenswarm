import type { AskUserQuestionPayload, UserAnswer } from '../types/websocket';

const selectorFields = ['source_binding_id', 'source_task_id', 'pending_token', 'input_id'] as const;

/** A display ID identifies one observed generation; SDK IDs remain lookup keys. */
export function captureAgentInput(question: AskUserQuestionPayload | null | undefined, displayId: string) {
  if (!question || question.request_id !== displayId) {
    throw new Error('This question changed. Review the current question before answering.');
  }
  if (!selectorFields.some((field) => question[field] !== undefined)) return null;
  for (const field of selectorFields) {
    const value = question[field];
    if (typeof value !== 'string' || !value || value.trim() !== value) {
      throw new Error('This question is missing its execution identity. Refresh before answering.');
    }
  }
  return {
    source_binding_id: question.source_binding_id!,
    source_task_id: question.source_task_id!,
    pending_token: question.pending_token!,
    input_id: question.input_id!,
  };
}

export async function agentInputReply(
  sessionId: string,
  target: NonNullable<ReturnType<typeof captureAgentInput>>,
  answers: UserAnswer[],
) {
  const params = JSON.parse(JSON.stringify({ action: 'reply', session_id: sessionId, ...target, answers }));
  const bytes = new TextEncoder().encode(JSON.stringify(params));
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  const requestId = 'agent-input.' + [...new Uint8Array(digest)].map((part) => part.toString(16).padStart(2, '0')).join('');
  return { params, options: { requestId } };
}
