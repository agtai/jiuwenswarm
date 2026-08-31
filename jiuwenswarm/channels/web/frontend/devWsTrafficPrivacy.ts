export const RAW_AUDIO_REDACTION = '[REDACTED_RAW_AUDIO]';
export const MEDIA_TICKET_REDACTION = '[REDACTED_MEDIA_TICKET]';
export const SPEECH_TEXT_REDACTION = '[REDACTED_SPEECH_TEXT]';
export const VOICE_COMMIT_RECEIPT_REDACTION = '[REDACTED_VOICE_COMMIT_RECEIPT]';
export const RAW_TRANSPORT_DATA_REDACTION = '[REDACTED_RAW_TRANSPORT_DATA]';
export const INVALID_DEV_WS_PAYLOAD_REDACTION = '[REDACTED_INVALID_DEV_WS_PAYLOAD]';
export const PRIVATE_CONTENT_REDACTION = '[REDACTED_PRIVATE_CONTENT]';

// 承载用户/任务私密内容的键（compact 形式：小写去符号）。宁可多杀：这是
// 开发日志，误杀一个非敏感字段的代价远小于漏掉一段私密语音或任务指令。
const PRIVATE_CONTENT_KEYS = new Set([
  'text',
  'name',
  'taskname',
  'instruction',
  'instructions',
  'adjustment',
  'adjustments',
  'message',
  'messages',
  'content',
  'query',
  'transcript',
  'hypothesistext',
  'partialtext',
]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

interface RedactionResult {
  readonly value: unknown;
  readonly changed: boolean;
}

function redactValue(payload: unknown, inspectJsonStrings: boolean): RedactionResult {
  if (typeof payload === 'string' && inspectJsonStrings) {
    try {
      const parsed: unknown = JSON.parse(payload);
      if (!isRecord(parsed) && !Array.isArray(parsed)) {
        return { value: payload, changed: false };
      }
      const redacted = redactValue(parsed, true);
      return redacted.changed ? { value: JSON.stringify(redacted.value), changed: true } : { value: payload, changed: false };
    } catch {
      const candidate = payload.trimStart();
      return candidate.startsWith('{') || candidate.startsWith('[')
        ? { value: RAW_TRANSPORT_DATA_REDACTION, changed: true }
        : { value: payload, changed: false };
    }
  }

  if (Array.isArray(payload)) {
    const entries = payload.map(item => redactValue(item, inspectJsonStrings));
    return {
      value: entries.map(entry => entry.value),
      changed: entries.some(entry => entry.changed),
    };
  }
  if (!isRecord(payload)) {
    return { value: payload, changed: false };
  }

  const parseFailed = payload.parse === 'failed';
  const normalizeIgnored = payload.normalize === 'ignored';
  let changed = false;
  const entries = Object.entries(payload).map(([key, value]) => {
    const compactKey = key.toLowerCase().replace(/[^a-z0-9]/g, '');
    if (key === 'data_base64') {
      changed = true;
      return [key, RAW_AUDIO_REDACTION] as const;
    }
    if (compactKey === 'mediaticket') {
      changed = true;
      return [key, MEDIA_TICKET_REDACTION] as const;
    }
    if (
      compactKey === 'finaltext' ||
      compactKey === 'rawtext' ||
      compactKey === 'displaytext' ||
      compactKey === 'spokentext' ||
      compactKey === 'renderedtext'
    ) {
      changed = true;
      return [key, SPEECH_TEXT_REDACTION] as const;
    }
    if (PRIVATE_CONTENT_KEYS.has(compactKey)) {
      changed = true;
      return [key, PRIVATE_CONTENT_REDACTION] as const;
    }
    if (compactKey === 'voicecommitreceipt') {
      changed = true;
      return [key, VOICE_COMMIT_RECEIPT_REDACTION] as const;
    }
    if ((key === 'rawData' && parseFailed) || (key === 'parsed' && normalizeIgnored)) {
      changed = true;
      return [key, RAW_TRANSPORT_DATA_REDACTION] as const;
    }
    const child = redactValue(value, inspectJsonStrings || (key === 'payload' && payload.type === 'res'));
    changed ||= child.changed;
    return [key, child.value] as const;
  });
  return { value: Object.fromEntries(entries), changed };
}

/**
 * Return a logging-only copy with private Speech media and text removed. The
 * fixed markers are not derived from private values, so logs cannot correlate
 * payloads. Every string that parses as JSON is inspected recursively so
 * private content cannot hide inside an embedded JSON equivalent, and any
 * redactor failure replaces the entire surface instead of failing open.
 */
export function redactRawAudioForDevLog(payload: unknown): unknown {
  try {
    return redactValue(payload, true).value;
  } catch {
    return INVALID_DEV_WS_PAYLOAD_REDACTION;
  }
}

/** Parse and sanitize an untrusted dev-log POST without persisting malformed raw text. */
export function prepareDevWsTrafficPayloadForPersistence(raw: string): unknown {
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!isRecord(parsed)) {
      return INVALID_DEV_WS_PAYLOAD_REDACTION;
    }
    return redactRawAudioForDevLog(parsed);
  } catch {
    return INVALID_DEV_WS_PAYLOAD_REDACTION;
  }
}
