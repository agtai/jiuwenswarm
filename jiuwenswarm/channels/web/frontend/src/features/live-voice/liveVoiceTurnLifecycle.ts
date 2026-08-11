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

export interface LiveVoiceTurnSessionRebindInput {
  originatingSessionId: string | null;
  previousSessionId: string | null;
  activeSessionId: string | null;
  transitionAction: LiveVoiceSessionTransitionAction;
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

/**
 * Keep a voice turn bound to the session where its request was dispatched.
 * The only legal rebind is the already-validated `new` session promotion;
 * ordinary navigation must leave the old identity intact so later selectors
 * can fence the turn before React's passive exit effect runs.
 */
export function resolveLiveVoiceTurnOriginatingSessionId({
  originatingSessionId,
  previousSessionId,
  activeSessionId,
  transitionAction,
}: LiveVoiceTurnSessionRebindInput): string | null {
  if (
    transitionAction === 'preserve' &&
    originatingSessionId === 'new' &&
    previousSessionId === 'new' &&
    activeSessionId !== null &&
    activeSessionId !== 'new'
  ) {
    return activeSessionId;
  }
  return originatingSessionId;
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

export type LiveVoicePostSpeechAction = 'none' | 'mark-thinking' | 'begin-capture';

export const LIVE_VOICE_STREAMING_FINAL_TIMEOUT_MS = 10_000;

export type LiveVoiceStreamingFinalTimeoutAction = 'none' | 'wait' | 'recover';

export interface LiveVoiceStreamingFinalTimeoutInput {
  streamingEnabled: boolean;
  liveVoiceActive: boolean;
  responseInProgress: boolean;
  responseObserved: boolean;
  originatingSessionId: string | null;
  activeSessionId: string | null;
  currentTurnResponseEpoch: number | null;
  plannerResponseEpoch: number | null;
  plannerMessageId: string | null;
  plannerMode: 'streaming' | 'final-only' | 'mismatch' | 'finalized';
  status: 'idle' | 'listening' | 'thinking' | 'speaking' | 'interrupted' | 'error';
  pendingSpeechCount: number;
  activeSpeechKey: string | null;
  timeoutExpired: boolean;
}

interface AwaitingAuthoritativeFinalInput {
  responseObserved: boolean;
  currentTurnResponseEpoch: number | null;
  plannerResponseEpoch: number | null;
  plannerMessageId: string | null;
  plannerMode: 'streaming' | 'final-only' | 'mismatch' | 'finalized';
}

function isAwaitingAuthoritativeFinal({
  responseObserved,
  currentTurnResponseEpoch,
  plannerResponseEpoch,
  plannerMessageId,
  plannerMode,
}: AwaitingAuthoritativeFinalInput): boolean {
  if (!responseObserved || currentTurnResponseEpoch === null || currentTurnResponseEpoch <= 0) {
    return false;
  }
  if (plannerMode === 'finalized' || plannerMode === 'mismatch') {
    return false;
  }

  const plannerHasNotObservedAMessage = plannerResponseEpoch === null && plannerMessageId === null;
  const plannerOwnsCurrentTurn = plannerResponseEpoch === currentTurnResponseEpoch && plannerMessageId !== null;
  return plannerHasNotObservedAMessage || plannerOwnsCurrentTurn;
}

/**
 * Decide whether the React adapter should wait for an authoritative final or
 * recover from a missing one. The timeout starts only after Agent processing
 * and provisional playback have both drained, so it never promotes or cuts
 * off provisional text. A caller must invalidate the response on `recover`;
 * this function deliberately does not manufacture a final observation.
 */
export function selectLiveVoiceStreamingFinalTimeoutAction({
  streamingEnabled,
  liveVoiceActive,
  responseInProgress,
  responseObserved,
  originatingSessionId,
  activeSessionId,
  currentTurnResponseEpoch,
  plannerResponseEpoch,
  plannerMessageId,
  plannerMode,
  status,
  pendingSpeechCount,
  activeSpeechKey,
  timeoutExpired,
}: LiveVoiceStreamingFinalTimeoutInput): LiveVoiceStreamingFinalTimeoutAction {
  const awaitingAuthoritativeFinal =
    streamingEnabled &&
    liveVoiceActive &&
    !responseInProgress &&
    originatingSessionId !== null &&
    originatingSessionId === activeSessionId &&
    isAwaitingAuthoritativeFinal({
      responseObserved,
      currentTurnResponseEpoch,
      plannerResponseEpoch,
      plannerMessageId,
      plannerMode,
    }) &&
    (status === 'idle' || status === 'thinking') &&
    pendingSpeechCount === 0 &&
    activeSpeechKey === null;

  if (!awaitingAuthoritativeFinal) {
    return 'none';
  }
  return timeoutExpired ? 'recover' : 'wait';
}

export interface LiveVoicePostSpeechInput {
  streamingEnabled: boolean;
  responseInProgress: boolean;
  responseObserved: boolean;
  currentTurnResponseEpoch: number | null;
  plannerResponseEpoch: number | null;
  plannerMessageId: string | null;
  plannerMode: 'streaming' | 'final-only' | 'mismatch' | 'finalized';
  status: 'idle' | 'listening' | 'thinking' | 'speaking' | 'interrupted' | 'error';
  pendingSpeechCount: number;
  activeSpeechKey: string | null;
  resumeRequested: boolean;
}

/**
 * Decide the React adapter's next action from a live core snapshot.
 *
 * In particular, processing=false is not sufficient to reopen the mic while
 * a streamed prefix still awaits chat.final, and an idle render is not truly
 * idle while enqueueSpeech has installed an active key before onStart.
 */
export function selectLiveVoicePostSpeechAction({
  streamingEnabled,
  responseInProgress,
  responseObserved,
  currentTurnResponseEpoch,
  plannerResponseEpoch,
  plannerMessageId,
  plannerMode,
  status,
  pendingSpeechCount,
  activeSpeechKey,
  resumeRequested,
}: LiveVoicePostSpeechInput): LiveVoicePostSpeechAction {
  const speechQueueEmpty = pendingSpeechCount === 0 && activeSpeechKey === null;
  const awaitingStreamingFinal =
    streamingEnabled &&
    isAwaitingAuthoritativeFinal({
      responseObserved,
      currentTurnResponseEpoch,
      plannerResponseEpoch,
      plannerMessageId,
      plannerMode,
    });

  if (awaitingStreamingFinal) {
    return status === 'idle' && speechQueueEmpty ? 'mark-thinking' : 'none';
  }
  if (responseInProgress) {
    return streamingEnabled && currentTurnResponseEpoch !== null && status === 'idle' && speechQueueEmpty ? 'mark-thinking' : 'none';
  }
  return status === 'idle' && speechQueueEmpty && resumeRequested ? 'begin-capture' : 'none';
}
