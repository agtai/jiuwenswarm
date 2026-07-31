const QUARANTINED_OUTPUT_EVENTS = new Set(['chat.delta', 'chat.final', 'chat.reasoning', 'chat.media']);

export interface SupplementOutputQuarantine {
  begin: (sessionId: string) => void;
  release: (sessionId: string) => void;
  isActive: (sessionId: string) => boolean;
  shouldDrop: (sessionId: string, eventName: string) => boolean;
  clear: (sessionId: string) => void;
  clearAll: () => void;
}

interface SupplementOutputQuarantineContext {
  intent: string;
  newInput?: string;
  mode?: string;
  evolutionStatus?: string;
  hasPendingQuestion?: boolean;
}

export function shouldBeginSupplementOutputQuarantine({
  intent,
  newInput,
  mode,
  evolutionStatus,
  hasPendingQuestion,
}: SupplementOutputQuarantineContext): boolean {
  return Boolean(intent === 'supplement' && newInput && mode === 'agent' && !evolutionStatus && !hasPendingQuestion);
}

/**
 * Short-lived, client-only barrier for the existing supplement flow.
 *
 * In the normal Agent supplement path used by the Demo, the Gateway cancels and
 * awaits the old stream before publishing chat.interrupt_result(supplement),
 * then starts the replacement stream. The WebSocket writer preserves frame
 * order, so that acknowledgement is a usable Demo boundary: response output
 * received before it belongs to the superseded turn and must not mutate UI or
 * start TTS. Team and pending-evolution paths intentionally do not enter this
 * barrier because their existing supplement semantics differ.
 *
 * This is deliberately not a production response-generation fence. It has no
 * response ID and only protects the current ordered WebSocket path.
 */
export function createSupplementOutputQuarantine(): SupplementOutputQuarantine {
  const pendingBySession = new Map<string, number>();

  return {
    begin(sessionId: string): void {
      if (!sessionId) return;
      pendingBySession.set(sessionId, (pendingBySession.get(sessionId) ?? 0) + 1);
    },

    release(sessionId: string): void {
      const pending = pendingBySession.get(sessionId) ?? 0;
      if (pending <= 1) {
        pendingBySession.delete(sessionId);
        return;
      }
      pendingBySession.set(sessionId, pending - 1);
    },

    isActive(sessionId: string): boolean {
      return (pendingBySession.get(sessionId) ?? 0) > 0;
    },

    shouldDrop(sessionId: string, eventName: string): boolean {
      return (pendingBySession.get(sessionId) ?? 0) > 0 && QUARANTINED_OUTPUT_EVENTS.has(eventName);
    },

    clear(sessionId: string): void {
      pendingBySession.delete(sessionId);
    },

    clearAll(): void {
      pendingBySession.clear();
    },
  };
}
