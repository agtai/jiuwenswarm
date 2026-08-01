export type LiveVoiceSessionTransitionAction = 'none' | 'preserve' | 'exit';

export interface LiveVoiceSessionTransitionInput {
  active: boolean;
  previousSessionId: string | null;
  activeSessionId: string | null;
  promotionSequence: number;
  promotionTargetSessionId: string | null;
  lastHandledPromotionSequence: number;
}

export interface LiveVoiceSessionTransitionResult {
  action: LiveVoiceSessionTransitionAction;
  nextHandledPromotionSequence: number;
}

/**
 * Resolve the two-render `new` session promotion without consuming its signal
 * before chatStore publishes the matching activeSessionId transition.
 */
export function resolveLiveVoiceSessionTransition({
  active,
  previousSessionId,
  activeSessionId,
  promotionSequence,
  promotionTargetSessionId,
  lastHandledPromotionSequence,
}: LiveVoiceSessionTransitionInput): LiveVoiceSessionTransitionResult {
  const hasFreshPromotion = promotionSequence > lastHandledPromotionSequence;

  if (!active) {
    return {
      action: 'none',
      nextHandledPromotionSequence: hasFreshPromotion ? promotionSequence : lastHandledPromotionSequence,
    };
  }

  if (previousSessionId === activeSessionId) {
    return {
      action: 'none',
      nextHandledPromotionSequence: lastHandledPromotionSequence,
    };
  }

  const nextHandledPromotionSequence = hasFreshPromotion ? promotionSequence : lastHandledPromotionSequence;
  const isMatchingPromotion =
    previousSessionId === 'new' && Boolean(activeSessionId) && activeSessionId !== 'new' && hasFreshPromotion && promotionTargetSessionId === activeSessionId;

  return {
    action: isMatchingPromotion ? 'preserve' : 'exit',
    nextHandledPromotionSequence,
  };
}

export interface SilentResponseResumeInput {
  responseObserved: boolean;
  responseInProgress: boolean;
  hasUserBoundary: boolean;
  isThinking: boolean;
  pendingSpeechCount: number;
}

/**
 * A local user echo can render before processing=true. It is not evidence that
 * an Agent response has already completed, so it must never reopen the mic.
 */
export function shouldResumeAfterSilentResponse({
  responseObserved,
  responseInProgress,
  hasUserBoundary,
  isThinking,
  pendingSpeechCount,
}: SilentResponseResumeInput): boolean {
  return responseObserved && !responseInProgress && hasUserBoundary && isThinking && pendingSpeechCount === 0;
}
