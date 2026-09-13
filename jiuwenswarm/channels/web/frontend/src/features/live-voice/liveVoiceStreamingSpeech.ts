import { sanitizeLiveVoiceTtsText, splitLiveVoiceTtsText } from '../../utils/ttsText';

/**
 * Conservative, pure planning for sentence-level Live Voice playback.
 *
 * This module deliberately does not subscribe to WebSocket deltas or play
 * audio. A future React adapter may feed it the assistant message snapshots
 * already accepted into chatStore, then pass the returned emissions through
 * LiveVoiceCore.enqueueSpeech. Keeping those boundaries outside this planner
 * preserves the existing supplement quarantine and responseEpoch fence.
 */

export type LiveVoiceStreamingSpeechPhase = 'streaming' | 'final';

export type LiveVoiceStreamingSpeechMode = 'streaming' | 'final-only' | 'mismatch' | 'finalized';

export type LiveVoiceStreamingSpeechFallbackReason =
  | 'message-changed-before-emission'
  | 'message-changed-after-emission'
  | 'stream-rewrite-before-emission'
  | 'stream-rewrite-after-emission'
  | 'final-prefix-mismatch'
  | 'final-rewrite-after-final';

export type LiveVoiceStreamingSpeechOutcome = 'waiting' | 'emitted' | 'final-only' | 'mismatch' | 'finalized' | 'stale-epoch';

export interface LiveVoiceStreamingSpeechObservation {
  responseEpoch: number;
  messageId: string;
  rawContent: string;
  phase: LiveVoiceStreamingSpeechPhase;
}

export interface LiveVoiceStreamingSpeechEmission {
  key: string;
  text: string;
  responseEpoch: number;
}

export interface LiveVoiceStreamingSpeechState {
  responseEpoch: number | null;
  messageId: string | null;
  mode: LiveVoiceStreamingSpeechMode;
  lastRawContent: string;
  emittedSpeakablePrefix: string;
  nextEmissionIndex: number;
  finalSpeakableText: string | null;
  fallbackReason: LiveVoiceStreamingSpeechFallbackReason | null;
}

export interface LiveVoiceStreamingSpeechResult {
  state: LiveVoiceStreamingSpeechState;
  emissions: LiveVoiceStreamingSpeechEmission[];
  outcome: LiveVoiceStreamingSpeechOutcome;
}

const SENTENCE_END_RE = /[。！？!?；;.…]/;
const SENTENCE_TRAILER_RE = /[。！？!?；;.…”’」』】）》)\]]/;
const LETTER_OR_NUMBER_RE = /[\p{L}\p{N}_]/u;

export function createLiveVoiceStreamingSpeechState(): LiveVoiceStreamingSpeechState {
  return {
    responseEpoch: null,
    messageId: null,
    mode: 'streaming',
    lastRawContent: '',
    emittedSpeakablePrefix: '',
    nextEmissionIndex: 0,
    finalSpeakableText: null,
    fallbackReason: null,
  };
}

function resetForObservation(observation: LiveVoiceStreamingSpeechObservation): LiveVoiceStreamingSpeechState {
  return {
    ...createLiveVoiceStreamingSpeechState(),
    responseEpoch: observation.responseEpoch,
    messageId: observation.messageId,
  };
}

function hasUnclosedCodeFence(text: string): boolean {
  let fenceCount = 0;
  let searchFrom = 0;

  while (searchFrom < text.length) {
    const fenceIndex = text.indexOf('```', searchFrom);
    if (fenceIndex < 0) break;
    fenceCount += 1;
    searchFrom = fenceIndex + 3;
  }

  return fenceCount % 2 === 1;
}

function isEnglishPeriodBoundary(text: string, index: number): boolean {
  const previous = text[index - 1] ?? '';
  const next = text[index + 1] ?? '';

  if (/\d/.test(previous) && /\d/.test(next)) {
    return false;
  }

  return !next || !LETTER_OR_NUMBER_RE.test(next);
}

function sentenceBoundaryAfter(text: string, index: number): number | null {
  const character = text[index];
  if (character === '.') {
    if (!isEnglishPeriodBoundary(text, index)) return null;
  } else if (!SENTENCE_END_RE.test(character)) {
    return null;
  }

  let boundary = index + 1;
  while (boundary < text.length && SENTENCE_TRAILER_RE.test(text[boundary])) {
    boundary += 1;
  }
  while (boundary < text.length && /\s/.test(text[boundary])) {
    boundary += 1;
  }
  return boundary;
}

/**
 * Return the largest complete-sentence prefix that has visible lookahead.
 *
 * Requiring non-whitespace text after the boundary intentionally keeps the
 * latest sentence buffered. A sentence ending at the current delta edge may
 * still be extended, normalized, or immediately replaced by chat.final; the
 * next sentence beginning is a cheap, deterministic stability signal.
 */
function stableSentencePrefixEnd(text: string): number {
  let stableEnd = 0;

  for (let index = 0; index < text.length; index += 1) {
    const boundary = sentenceBoundaryAfter(text, index);
    if (boundary === null) continue;
    if (text.slice(boundary).trim().length === 0) continue;
    stableEnd = boundary;
  }

  return stableEnd;
}

function createEmissions(
  text: string,
  state: LiveVoiceStreamingSpeechState,
  kind: 'stream' | 'final-tail'
): {
  emissions: LiveVoiceStreamingSpeechEmission[];
  nextEmissionIndex: number;
} {
  const emissions: LiveVoiceStreamingSpeechEmission[] = [];
  let nextEmissionIndex = state.nextEmissionIndex;

  for (const chunk of splitLiveVoiceTtsText(text)) {
    const playableText = chunk.trim();
    if (!playableText) continue;
    emissions.push({
      key: `${state.messageId}:${kind}:${nextEmissionIndex}`,
      text: playableText,
      responseEpoch: state.responseEpoch as number,
    });
    nextEmissionIndex += 1;
  }

  return { emissions, nextEmissionIndex };
}

function mismatchResult(state: LiveVoiceStreamingSpeechState, reason: LiveVoiceStreamingSpeechFallbackReason): LiveVoiceStreamingSpeechResult {
  return {
    state: {
      ...state,
      mode: 'mismatch',
      fallbackReason: reason,
    },
    emissions: [],
    outcome: 'mismatch',
  };
}

function reconciledFinalTail(finalSpeakableText: string, emittedSpeakablePrefix: string): string | null {
  if (finalSpeakableText.startsWith(emittedSpeakablePrefix)) {
    return finalSpeakableText.slice(emittedSpeakablePrefix.length);
  }

  // Live Voice sanitization intentionally trims display punctuation at the
  // very end of a complete response. The same punctuation remains internal
  // while streaming because another sentence provides lookahead. Treat only
  // that exact edge-normalization case as equal; broader fuzzy matching could
  // hide a real final rewrite.
  const normalizedEmittedPrefix = emittedSpeakablePrefix.replace(/[\s。:：]+$/g, '');
  return finalSpeakableText === normalizedEmittedPrefix ? '' : null;
}

function finalize(state: LiveVoiceStreamingSpeechState, observation: LiveVoiceStreamingSpeechObservation): LiveVoiceStreamingSpeechResult {
  const finalSpeakableText = sanitizeLiveVoiceTtsText(observation.rawContent);

  if (state.mode === 'finalized' && state.finalSpeakableText !== finalSpeakableText) {
    return mismatchResult(state, 'final-rewrite-after-final');
  }
  if (state.mode === 'finalized') {
    return { state, emissions: [], outcome: 'finalized' };
  }
  if (state.mode === 'mismatch') {
    return { state, emissions: [], outcome: 'mismatch' };
  }
  const tail = reconciledFinalTail(finalSpeakableText, state.emittedSpeakablePrefix);
  if (tail === null) {
    return mismatchResult({ ...state, lastRawContent: observation.rawContent }, 'final-prefix-mismatch');
  }

  const planned = createEmissions(tail, state, 'final-tail');
  return {
    state: {
      ...state,
      mode: 'finalized',
      lastRawContent: observation.rawContent,
      emittedSpeakablePrefix: finalSpeakableText,
      nextEmissionIndex: planned.nextEmissionIndex,
      finalSpeakableText,
    },
    emissions: planned.emissions,
    outcome: 'finalized',
  };
}

/**
 * Advance one response-local streaming speech plan.
 *
 * A changed responseEpoch starts a fresh plan. A message ID change inside the
 * same epoch is treated conservatively: before any emission the response falls
 * back to final-only playback; after an emission it becomes a mismatch because
 * already spoken audio cannot be reconciled with a different visible message.
 */
export function advanceLiveVoiceStreamingSpeech(
  previousState: LiveVoiceStreamingSpeechState,
  observation: LiveVoiceStreamingSpeechObservation
): LiveVoiceStreamingSpeechResult {
  let state = previousState;

  if (observation.responseEpoch <= 0 || (state.responseEpoch !== null && observation.responseEpoch < state.responseEpoch)) {
    return { state, emissions: [], outcome: 'stale-epoch' };
  }

  if (state.responseEpoch === null || state.responseEpoch < observation.responseEpoch) {
    state = resetForObservation(observation);
  } else if (state.messageId !== observation.messageId) {
    if (state.emittedSpeakablePrefix) {
      return mismatchResult(state, 'message-changed-after-emission');
    }
    state = {
      ...resetForObservation(observation),
      mode: 'final-only',
      fallbackReason: 'message-changed-before-emission',
    };
  }

  if (observation.phase === 'final') {
    return finalize(state, observation);
  }
  if (state.mode === 'finalized') {
    return { state, emissions: [], outcome: 'finalized' };
  }
  if (state.mode === 'mismatch') {
    return { state, emissions: [], outcome: 'mismatch' };
  }
  if (state.mode === 'final-only') {
    return {
      state: { ...state, lastRawContent: observation.rawContent },
      emissions: [],
      outcome: 'final-only',
    };
  }

  if (!observation.rawContent.startsWith(state.lastRawContent)) {
    const reason = state.emittedSpeakablePrefix ? 'stream-rewrite-after-emission' : 'stream-rewrite-before-emission';
    if (state.emittedSpeakablePrefix) {
      return mismatchResult({ ...state, lastRawContent: observation.rawContent }, reason);
    }
    return {
      state: {
        ...state,
        mode: 'final-only',
        lastRawContent: observation.rawContent,
        fallbackReason: reason,
      },
      emissions: [],
      outcome: 'final-only',
    };
  }

  const nextState = { ...state, lastRawContent: observation.rawContent };
  if (hasUnclosedCodeFence(observation.rawContent)) {
    return { state: nextState, emissions: [], outcome: 'waiting' };
  }

  const speakableText = sanitizeLiveVoiceTtsText(observation.rawContent);
  if (!speakableText.startsWith(state.emittedSpeakablePrefix)) {
    return mismatchResult(nextState, 'stream-rewrite-after-emission');
  }

  const stableEnd = stableSentencePrefixEnd(speakableText);
  if (stableEnd <= state.emittedSpeakablePrefix.length) {
    return { state: nextState, emissions: [], outcome: 'waiting' };
  }

  const stablePrefix = speakableText.slice(0, stableEnd);
  const newlyStableText = stablePrefix.slice(state.emittedSpeakablePrefix.length);
  const planned = createEmissions(newlyStableText, state, 'stream');
  return {
    state: {
      ...nextState,
      emittedSpeakablePrefix: stablePrefix,
      nextEmissionIndex: planned.nextEmissionIndex,
    },
    emissions: planned.emissions,
    outcome: planned.emissions.length > 0 ? 'emitted' : 'waiting',
  };
}
