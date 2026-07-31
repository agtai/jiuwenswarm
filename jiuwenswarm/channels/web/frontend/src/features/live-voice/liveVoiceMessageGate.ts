import type { Message } from '../../types/message';

export interface SelectLiveVoiceResponseMessagesOptions {
  messages: readonly Message[];
  voiceTranscript: string;
  knownUserBoundaryId?: string | null;
  isProcessing: boolean;
  spokenMessageIds: ReadonlySet<string>;
}

export interface LiveVoiceMessageGateResult {
  userBoundaryId: string | null;
  speakableMessages: Message[];
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
}: SelectLiveVoiceResponseMessagesOptions): LiveVoiceMessageGateResult {
  const userBoundaryIndex = findUserBoundaryIndex(messages, voiceTranscript, knownUserBoundaryId);
  const userBoundaryId = userBoundaryIndex >= 0 ? messages[userBoundaryIndex].id : null;

  if (userBoundaryIndex < 0 || isProcessing) {
    return {
      userBoundaryId,
      speakableMessages: [],
    };
  }

  const nextUserOffset = messages.slice(userBoundaryIndex + 1).findIndex(message => message.role === 'user');
  const turnEndIndex = nextUserOffset < 0 ? messages.length : userBoundaryIndex + 1 + nextUserOffset;
  const speakableMessages = messages.slice(userBoundaryIndex + 1, turnEndIndex).filter(message => {
    return message.role === 'assistant' && message.isStreaming !== true && normalizeTranscript(message.content).length > 0 && !spokenMessageIds.has(message.id);
  });

  return {
    userBoundaryId,
    speakableMessages,
  };
}
