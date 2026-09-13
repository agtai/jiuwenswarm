export interface SpeechRecognitionNaturalEndInput {
  useContinuous: boolean;
  restartRequested: boolean;
  receivedAnyResult: boolean;
  terminalRecognitionError: boolean;
  manualStop: boolean;
  autoStop: boolean;
}

export interface SpeechRecognitionInitialRetryInput {
  retryRequested: boolean;
  receivedAnyResult: boolean;
  beforeInitialDeadline: boolean;
  terminalRecognitionError: boolean;
  manualStop: boolean;
  autoStop: boolean;
}

export function shouldRetrySpeechCaptureDuringInitialSilence({
  retryRequested,
  receivedAnyResult,
  beforeInitialDeadline,
  terminalRecognitionError,
  manualStop,
  autoStop,
}: SpeechRecognitionInitialRetryInput): boolean {
  return !terminalRecognitionError && !manualStop && !autoStop && (retryRequested || (!receivedAnyResult && beforeInitialDeadline));
}

/**
 * Decide whether a browser-level `onend` should end the user's logical
 * capture. Chromium can emit `onend` immediately after a small final result,
 * even in continuous mode. Restarting in that case lets the existing trailing
 * silence deadline collect the rest of the utterance; manual/automatic stops
 * and real errors must still finish exactly once.
 */
export function shouldContinueSpeechCaptureAfterNaturalEnd({
  useContinuous,
  restartRequested,
  receivedAnyResult,
  terminalRecognitionError,
  manualStop,
  autoStop,
}: SpeechRecognitionNaturalEndInput): boolean {
  return useContinuous && restartRequested && receivedAnyResult && !terminalRecognitionError && !manualStop && !autoStop;
}

/** A no-speech edge after an earlier result closes the tail grace successfully. */
export function isSuccessfulSpeechTailNoSpeech(error: string, receivedAnyResult: boolean): boolean {
  return error === 'no-speech' && receivedAnyResult;
}

export interface SpeechRecognitionTranscriptState {
  finalTranscript: string;
  interimTranscript: string;
}

/** Merge result chunks across browser-level restarts of one logical capture. */
export function mergeSpeechRecognitionTranscript(
  state: SpeechRecognitionTranscriptState,
  transcript: string,
  isFinal: boolean
): SpeechRecognitionTranscriptState {
  if (isFinal) {
    return {
      finalTranscript: state.finalTranscript + transcript,
      interimTranscript: '',
    };
  }
  return {
    finalTranscript: state.finalTranscript,
    interimTranscript: transcript,
  };
}

export function combinedSpeechRecognitionTranscript(state: SpeechRecognitionTranscriptState): string {
  return state.finalTranscript + state.interimTranscript;
}
