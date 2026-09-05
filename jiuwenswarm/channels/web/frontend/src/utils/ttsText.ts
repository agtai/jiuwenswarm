/** Preserve the Agent text; chunking limits playback work without rewriting content. */

export const LIVE_VOICE_TTS_MIN_CHUNK_LENGTH = 220;
export const LIVE_VOICE_TTS_TARGET_CHUNK_LENGTH = 260;
export const LIVE_VOICE_TTS_MAX_CHUNK_LENGTH = 300;

const SENTENCE_END_RE = /[。！？!?；;.…]/;
const SENTENCE_TRAILER_RE = /[。！？!?；;.…”’」』】）》)\]]/;
const LETTER_OR_NUMBER_RE = /[\p{L}\p{N}_]/u;

export function sanitizeTtsText(input: string): string {
  return input;
}

export function makeLiveVoiceTextSpeakable(text: string): string {
  return text;
}

export function sanitizeLiveVoiceTtsText(input: string): string {
  return input;
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
    if (!isEnglishPeriodBoundary(text, index)) {
      return null;
    }
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

function findPreferredSentenceBoundary(text: string, start: number): number | null {
  const minimum = start + LIVE_VOICE_TTS_MIN_CHUNK_LENGTH;
  const target = start + LIVE_VOICE_TTS_TARGET_CHUNK_LENGTH;
  const maximum = Math.min(start + LIVE_VOICE_TTS_MAX_CHUNK_LENGTH, text.length);
  let preferred: number | null = null;

  for (let index = start; index < maximum; index += 1) {
    const boundary = sentenceBoundaryAfter(text, index);
    if (boundary === null || boundary < minimum || boundary > maximum) {
      continue;
    }

    const currentDistance = Math.abs(boundary - target);
    const preferredDistance = preferred === null ? Number.POSITIVE_INFINITY : Math.abs(preferred - target);
    if (currentDistance < preferredDistance || (currentDistance === preferredDistance && boundary > (preferred ?? 0))) {
      preferred = boundary;
    }
  }

  return preferred;
}

function avoidSplittingSurrogatePair(text: string, boundary: number): number {
  if (boundary <= 0 || boundary >= text.length) {
    return boundary;
  }

  const previousCodeUnit = text.charCodeAt(boundary - 1);
  const nextCodeUnit = text.charCodeAt(boundary);
  const splitsSurrogatePair = previousCodeUnit >= 0xd800 && previousCodeUnit <= 0xdbff && nextCodeUnit >= 0xdc00 && nextCodeUnit <= 0xdfff;
  return splitsSurrogatePair ? boundary - 1 : boundary;
}

/**
 * Split already-sanitized Live Voice text into roughly 220-300 character
 * chunks. Sentence endings nearest 260 characters win; a sentence longer than
 * the window is hard-split at the target length. Slicing never trims or adds
 * content, so joining every chunk exactly reconstructs the sanitized input.
 */
export function* iterateTtsText(text: string): Generator<string> {
  if (!text) {
    return;
  }

  let start = 0;

  while (text.length - start > LIVE_VOICE_TTS_MAX_CHUNK_LENGTH) {
    const sentenceBoundary = findPreferredSentenceBoundary(text, start);
    const hardBoundary = avoidSplittingSurrogatePair(text, start + LIVE_VOICE_TTS_TARGET_CHUNK_LENGTH);
    const boundary = sentenceBoundary ?? hardBoundary;
    yield text.slice(start, boundary);
    start = boundary;
  }

  yield text.slice(start);
}

export function splitLiveVoiceTtsText(text: string): string[] {
  return [...iterateTtsText(text)];
}
