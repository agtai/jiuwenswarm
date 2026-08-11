/**
 * Pure text preparation helpers shared by regular and Live Voice TTS.
 *
 * Regular TTS intentionally keeps its historical 500-character default.
 * Live Voice sanitizes the complete response and then splits it into bounded
 * FIFO entries so no part of a long Agent answer disappears silently.
 */

const CODE_BLOCK_RE = /```[\s\S]*?```/g;
const INLINE_CODE_RE = /`([^`]+)`/g;
const MEDIA_BRACE_RE = /MEDIA:\{[^}]*\}/gi;
const MEDIA_SIMPLE_RE = /MEDIA:\S+/gi;
const URL_RE = /https?:\/\/\S+/g;
const WWW_RE = /www\.\S+/g;
const WIN_PATH_RE = /[A-Za-z]:\\[^\s]+/g;
const UNIX_PATH_RE = /(?:~|\/)(?:[^\s/]+\/)+[^\s/]*/g;
const QUOTE_BRACE_RE = /['"{}]/g;
const MULTI_NEWLINE_RE = /\n+/g;
const MULTI_PUNCT_RE = /。{2,}/g;
const MULTI_SPACE_RE = /\s{2,}/g;
const TRIM_EDGE_RE = /^[\s。:：]+|[\s。:：]+$/g;
const MARKDOWN_STRONG_RE = /\*\*([^*]+)\*\*/g;
const MARKDOWN_EMPHASIS_RE = /\*([^*]+)\*/g;
const TECHNICAL_TOKEN_RE = /[A-Za-z0-9~./\\:_-]+/g;
const TRAILING_TOKEN_PUNCTUATION_RE = /[.,;!?]+$/;

export const LIVE_VOICE_TTS_MIN_CHUNK_LENGTH = 220;
export const LIVE_VOICE_TTS_TARGET_CHUNK_LENGTH = 260;
export const LIVE_VOICE_TTS_MAX_CHUNK_LENGTH = 300;

const SENTENCE_END_RE = /[。！？!?；;.…]/;
const SENTENCE_TRAILER_RE = /[。！？!?；;.…”’」』】）》)\]]/;
const LETTER_OR_NUMBER_RE = /[\p{L}\p{N}_]/u;

const TECHNICAL_SEPARATOR_SPEECH: Readonly<Record<string, string>> = {
  '/': '斜杠',
  '\\': '反斜杠',
  _: '下划线',
  '.': '点',
  ':': '冒号',
  '-': '连字符',
  '~': '波浪号',
};

function sanitizeTtsTextUnbounded(input: string, preserveTechnicalText = false): string {
  if (!input) {
    return '';
  }

  let sanitized = input.replace(CODE_BLOCK_RE, '代码块已省略');
  if (!preserveTechnicalText) {
    sanitized = sanitized.replace(INLINE_CODE_RE, '');
  }

  sanitized = sanitized.replace(MEDIA_BRACE_RE, '').replace(MEDIA_SIMPLE_RE, '').replace(URL_RE, '').replace(WWW_RE, '');

  if (!preserveTechnicalText) {
    sanitized = sanitized.replace(WIN_PATH_RE, '').replace(UNIX_PATH_RE, '');
  }

  return sanitized
    .replace(QUOTE_BRACE_RE, '')
    .replace(MULTI_NEWLINE_RE, '。')
    .replace(MULTI_PUNCT_RE, '。')
    .replace(MULTI_SPACE_RE, ' ')
    .replace(TRIM_EDGE_RE, '');
}

export function sanitizeTtsText(input: string, maxLength = 500): string {
  return sanitizeTtsTextUnbounded(input).slice(0, maxLength).trim();
}

function shouldSpeakTechnicalToken(token: string, forced: boolean): boolean {
  if (forced) {
    return true;
  }

  return (
    /[_/\\]/.test(token) ||
    /(?=.*[A-Za-z])(?=.*\d)/.test(token) ||
    /[A-Za-z0-9]\.[A-Za-z0-9]/.test(token) ||
    /^\.[A-Za-z0-9]/.test(token) ||
    /^[A-Z]{2,6}$/.test(token) ||
    /[a-z][A-Z]/.test(token)
  );
}

function speakAlphabeticRun(run: string, technical: boolean): string {
  const words = run
    .replace(/([A-Z]+)([A-Z][a-z])/g, '$1 $2')
    .replace(/([a-z\d])([A-Z])/g, '$1 $2')
    .split(' ');

  return words
    .map(word => {
      const shouldSpell = /^[A-Z]{2,6}$/.test(word) || (technical && /^[A-Za-z]{1,3}$/.test(word));
      return shouldSpell ? word.toUpperCase().split('').join(' ') : word;
    })
    .join(' ');
}

function speakTechnicalSegment(segment: string): string {
  const runs = segment.match(/[A-Za-z]+|\d+/g);
  if (!runs) {
    return segment;
  }

  return runs.map(run => (/^\d+$/.test(run) ? run.split('').join(' ') : speakAlphabeticRun(run, true))).join(' ');
}

function speakTechnicalToken(token: string, forced: boolean): string {
  const punctuation = token.match(TRAILING_TOKEN_PUNCTUATION_RE)?.[0] ?? '';
  const coreToken = punctuation ? token.slice(0, -punctuation.length) : token;
  if (!coreToken || !shouldSpeakTechnicalToken(coreToken, forced)) {
    return token;
  }

  const spokenParts: string[] = [];
  let segment = '';
  const flushSegment = () => {
    if (!segment) {
      return;
    }
    spokenParts.push(speakTechnicalSegment(segment));
    segment = '';
  };

  for (const character of coreToken) {
    const separatorSpeech = TECHNICAL_SEPARATOR_SPEECH[character];
    if (separatorSpeech) {
      flushSegment();
      spokenParts.push(separatorSpeech);
    } else {
      segment += character;
    }
  }
  flushSegment();

  return `${spokenParts.join(' ')}${punctuation}`;
}

function speakTechnicalTokens(text: string, forced: boolean): string {
  return text.replace(TECHNICAL_TOKEN_RE, token => speakTechnicalToken(token, forced));
}

/**
 * Convert technical identifiers into words that zh-CN SpeechSynthesis does
 * not silently skip. This only changes the TTS copy; the chat message remains
 * untouched. Ordinary Chinese and English prose is preserved.
 */
export function makeLiveVoiceTextSpeakable(text: string): string {
  if (!text) {
    return '';
  }

  const withSpeakableInlineCode = text.replace(INLINE_CODE_RE, (_match, code: string) => speakTechnicalTokens(code, true));
  const withoutMarkdownEmphasis = withSpeakableInlineCode.replace(MARKDOWN_STRONG_RE, '$1').replace(MARKDOWN_EMPHASIS_RE, '$1');

  return speakTechnicalTokens(withoutMarkdownEmphasis, false).replace(MULTI_SPACE_RE, ' ').trim();
}

export function sanitizeLiveVoiceTtsText(input: string): string {
  return makeLiveVoiceTextSpeakable(sanitizeTtsTextUnbounded(input, true));
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
export function splitLiveVoiceTtsText(text: string): string[] {
  if (!text) {
    return [];
  }

  const chunks: string[] = [];
  let start = 0;

  while (text.length - start > LIVE_VOICE_TTS_MAX_CHUNK_LENGTH) {
    const sentenceBoundary = findPreferredSentenceBoundary(text, start);
    const hardBoundary = avoidSplittingSurrogatePair(text, start + LIVE_VOICE_TTS_TARGET_CHUNK_LENGTH);
    const boundary = sentenceBoundary ?? hardBoundary;
    chunks.push(text.slice(start, boundary));
    start = boundary;
  }

  chunks.push(text.slice(start));
  return chunks;
}
