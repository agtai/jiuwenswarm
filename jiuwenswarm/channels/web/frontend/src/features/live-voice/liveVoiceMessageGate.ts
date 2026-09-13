import type { Message } from '../../types/message';

export interface SelectLiveVoiceResponseMessagesOptions {
  messages: readonly Message[];
  voiceTranscript: string;
  knownUserBoundaryId?: string | null;
  isProcessing: boolean;
  spokenMessageIds: ReadonlySet<string>;
  /** Final message already owned by the optional streaming planner. */
  plannerMessageId?: string | null;
  /** Ignore stopStreaming-only bubbles until chat.final marks them. */
  requireAuthoritativeFinal?: boolean;
}

export interface LiveVoiceMessageGateResult {
  userBoundaryId: string | null;
  speakableMessages: Message[];
  /** A single append-only chatStore candidate eligible for conservative preview. */
  streamingCandidate: Message | null;
  /**
   * A complete planner-owned message, including later same-ID revisions.
   * It is excluded from speakableMessages so only the idempotent planner may
   * reconcile or reject it.
   */
  plannerFinalObservation: Message | null;
  /** All complete assistant segments in this turn, including spoken ones. */
  finalAssistantMessageCount: number;
}

function normalizeTranscript(value: string): string {
  return value.trim().replace(/\s+/g, ' ');
}

function findUserBoundaryIndex(messages: readonly Message[], voiceTranscript: string, knownUserBoundaryId?: string | null): number {
  if (knownUserBoundaryId) {
    for (let index = messages.length - 1; index >= 0; index -= 1) {
      const message = messages[index];
      if (message.id === knownUserBoundaryId && message.role === 'user') {
        return index;
      }
    }
  }

  const normalizedTranscript = normalizeTranscript(voiceTranscript);
  if (!normalizedTranscript) {
    return -1;
  }

  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (message.role === 'user' && normalizeTranscript(message.content) === normalizedTranscript) {
      return index;
    }
  }

  return -1;
}

/**
 * Finds the current voice turn's user-message boundary and returns only complete,
 * unread assistant messages that arrived after it.
 *
 * A known boundary ID is authoritative while it still identifies a user message.
 * Otherwise the latest user message matching the normalized transcript becomes
 * the boundary. No boundary means no speech, which prevents historical messages
 * from being read while the local user echo is still pending.
 */
export function selectLiveVoiceResponseMessages({
  messages,
  voiceTranscript,
  knownUserBoundaryId,
  isProcessing,
  spokenMessageIds,
  plannerMessageId = null,
  requireAuthoritativeFinal = false,
}: SelectLiveVoiceResponseMessagesOptions): LiveVoiceMessageGateResult {
  const userBoundaryIndex = findUserBoundaryIndex(messages, voiceTranscript, knownUserBoundaryId);
  const userBoundaryId = userBoundaryIndex >= 0 ? messages[userBoundaryIndex].id : null;

  const nextUserOffset = userBoundaryIndex < 0 ? -1 : messages.slice(userBoundaryIndex + 1).findIndex(message => message.role === 'user');
  const turnEndIndex = userBoundaryIndex < 0 ? 0 : nextUserOffset < 0 ? messages.length : userBoundaryIndex + 1 + nextUserOffset;
  const turnMessages = userBoundaryIndex < 0 ? [] : messages.slice(userBoundaryIndex + 1, turnEndIndex);
  const completedAssistantMessages = turnMessages.filter(message => {
    return message.role === 'assistant' && message.isStreaming !== true && (!requireAuthoritativeFinal || message.isResponseFinal === true);
  });
  const finalAssistantMessages = completedAssistantMessages.filter(message => normalizeTranscript(message.content).length > 0);
  const plannerFinalObservation = plannerMessageId ? (completedAssistantMessages.find(message => message.id === plannerMessageId) ?? null) : null;

  if (userBoundaryIndex < 0 || isProcessing) {
    let streamingCandidate: Message | null = null;
    if (userBoundaryIndex >= 0 && isProcessing) {
      const assistantMessages = turnMessages.filter(message => {
        return message.role === 'assistant' && normalizeTranscript(message.content).length > 0;
      });
      if (assistantMessages.length === 1 && assistantMessages[0].isStreaming === true) {
        streamingCandidate = assistantMessages[0];
      }
    }
    return {
      userBoundaryId,
      speakableMessages: [],
      streamingCandidate,
      plannerFinalObservation,
      finalAssistantMessageCount: completedAssistantMessages.length,
    };
  }

  const speakableMessages = finalAssistantMessages.filter(message => {
    return message.id !== plannerFinalObservation?.id && !spokenMessageIds.has(message.id);
  });

  return {
    userBoundaryId,
    speakableMessages,
    streamingCandidate: null,
    plannerFinalObservation,
    finalAssistantMessageCount: completedAssistantMessages.length,
  };
}
