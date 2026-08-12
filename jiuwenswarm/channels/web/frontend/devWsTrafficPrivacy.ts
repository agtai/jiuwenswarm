export const RAW_AUDIO_REDACTION = '[REDACTED_RAW_AUDIO]';
export const MEDIA_TICKET_REDACTION = '[REDACTED_MEDIA_TICKET]';
export const SPEECH_TEXT_REDACTION = '[REDACTED_SPEECH_TEXT]';
export const VOICE_COMMIT_RECEIPT_REDACTION = '[REDACTED_VOICE_COMMIT_RECEIPT]';
export const RAW_TRANSPORT_DATA_REDACTION = '[REDACTED_RAW_TRANSPORT_DATA]';
export const INVALID_DEV_WS_PAYLOAD_REDACTION = '[REDACTED_INVALID_DEV_WS_PAYLOAD]';

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

interface RedactionResult {
  readonly value: unknown;
  readonly changed: boolean;
}

const PRIVATE_KEY_IN_JSON_TEXT =
  /"(?:data[-_]base64|media[-_]ticket|final[-_]*text|raw[-_]*text|voice[-_]*commit[-_]*receipt)"\s*:/i;

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
      return PRIVATE_KEY_IN_JSON_TEXT.test(payload) ? { value: RAW_TRANSPORT_DATA_REDACTION, changed: true } : { value: payload, changed: false };
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
    const normalizedKey = key.trim().toLowerCase().replace(/-/g, '_');
    const compactKey = normalizedKey.replace(/_/g, '');
    if (key === 'data_base64') {
      changed = true;
      return [key, RAW_AUDIO_REDACTION] as const;
    }
    if (normalizedKey === 'media_ticket') {
      changed = true;
      return [key, MEDIA_TICKET_REDACTION] as const;
    }
    if (compactKey === 'finaltext' || compactKey === 'rawtext') {
      changed = true;
      return [key, SPEECH_TEXT_REDACTION] as const;
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
 * Return a logging-only copy with raw Speech audio removed. The fixed marker is
 * intentionally not derived from the audio, so logs cannot correlate payloads.
 */
export function redactRawAudioForDevLog(payload: unknown): unknown {
  return redactValue(payload, false).value;
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
