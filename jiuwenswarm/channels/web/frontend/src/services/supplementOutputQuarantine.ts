const QUARANTINED_OUTPUT_EVENTS = new Set([
  'chat.delta',
  'chat.final',
  'chat.reasoning',
  'chat.media',
  'chat.tool_call',
  'chat.tool_update',
]);

export interface SupplementOutputQuarantine {
  begin: (sessionId: string) => void;
  release: (sessionId: string) => boolean;
  isActive: (sessionId: string) => boolean;
  shouldHoldProcessing: (sessionId: string, isProcessing: boolean) => boolean;
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
  const heldProcessingStops = new Set<string>();

  return {
    begin(sessionId: string): void {
      if (!sessionId) return;
      pendingBySession.set(sessionId, (pendingBySession.get(sessionId) ?? 0) + 1);
    },

    release(sessionId: string): boolean {
      const pending = pendingBySession.get(sessionId) ?? 0;
      if (pending <= 1) {
        pendingBySession.delete(sessionId);
        return heldProcessingStops.delete(sessionId);
      }
      pendingBySession.set(sessionId, pending - 1);
      return false;
    },

    isActive(sessionId: string): boolean {
      return (pendingBySession.get(sessionId) ?? 0) > 0;
    },

    shouldHoldProcessing(sessionId: string, isProcessing: boolean): boolean {
      // The Gateway closes the superseded stream before it acknowledges the
      // supplement. That close emits a short-lived processing=false which is
      // not the end of the replacement turn. Holding only that stop edge keeps
      // Live Voice in the same turn until the ordered ACK opens the barrier.
      const shouldHold = !isProcessing && (pendingBySession.get(sessionId) ?? 0) > 0;
      if (shouldHold) heldProcessingStops.add(sessionId);
      return shouldHold;
    },

    shouldDrop(sessionId: string, eventName: string): boolean {
      return (pendingBySession.get(sessionId) ?? 0) > 0 && QUARANTINED_OUTPUT_EVENTS.has(eventName);
    },

    clear(sessionId: string): void {
      pendingBySession.delete(sessionId);
      heldProcessingStops.delete(sessionId);
    },

    clearAll(): void {
      pendingBySession.clear();
      heldProcessingStops.clear();
    },
  };
}
