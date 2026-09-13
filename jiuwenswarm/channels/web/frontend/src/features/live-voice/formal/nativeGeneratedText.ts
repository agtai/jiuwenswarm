import type { ProductWebP2ActivationBinding } from './productWebActivation';

export type NativeGeneratedMessage = Readonly<{
  id: string; role: 'assistant'; content: string; timestamp: string; nativeTurnKey: string;
  nativeVoice: Readonly<{ responseKey: string; responseId: string; responseGeneration: number; revision: number; state: 'generating' | 'generated' | 'interrupted' | 'played' }>;
}>;

function record(value: unknown, keys: readonly string[]): Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value) ||
      Object.keys(value).length !== keys.length || keys.some(key => !Object.hasOwn(value, key))) {
    throw new Error('MEDIA_NATIVE_TEXT_INVALID');
  }
  return value as Record<string, unknown>;
}

export function parseNativeGeneratedText(value: unknown, binding: ProductWebP2ActivationBinding, after: number):
    Readonly<{ revision: number; messages: readonly NativeGeneratedMessage[] }> {
  const result = record(value, ['status', 'binding', 'revision', 'snapshots']);
  const expected = ['session_id', 'interaction_id', 'correlation_id', 'activation_id', 'activation_generation'] as const;
  const actual = record(result.binding, expected);
  const revision = result.revision;
  if (result.status !== 'native_text' || expected.some(key => actual[key] !== binding[key]) ||
      typeof revision !== 'number' || !Number.isSafeInteger(revision) || revision < after ||
      !Array.isArray(result.snapshots) || result.snapshots.length > 64) throw new Error('MEDIA_NATIVE_TEXT_INVALID');
  const identities = new Set<string>();
  const messages = result.snapshots.map((raw): NativeGeneratedMessage => {
    const item = record(raw, ['response', 'text', 'state', 'revision', 'timestamp', 'turn_id']);
    const response = record(item.response, ['interaction_id', 'response_id', 'response_generation']);
    if (typeof item.turn_id !== 'string' || !/^[A-Za-z0-9_.:-]{1,256}$/.test(item.turn_id) ||
        response.interaction_id !== binding.interaction_id || typeof response.response_id !== 'string' ||
        !/^[A-Za-z0-9_.:-]{1,256}$/.test(response.response_id) ||
        typeof response.response_generation !== 'number' || !Number.isSafeInteger(response.response_generation) || response.response_generation <= 0 ||
        typeof item.revision !== 'number' || !Number.isSafeInteger(item.revision) || item.revision <= after || item.revision > revision ||
        typeof item.text !== 'string' || !item.text.trim() || item.text !== item.text.trim() ||
        /[\p{Cc}\p{Cf}\p{Zl}\p{Zp}]/u.test(item.text.replaceAll('\n', '')) || new TextEncoder().encode(item.text).length > 65_536 ||
        !['generating', 'generated', 'interrupted', 'played'].includes(String(item.state)) ||
        typeof item.timestamp !== 'string' || !Number.isFinite(Date.parse(item.timestamp))) throw new Error('MEDIA_NATIVE_TEXT_INVALID');
    const responseKey = `live-voice:${response.interaction_id}:${response.response_id}:${response.response_generation}`;
    if (identities.has(responseKey)) throw new Error('MEDIA_NATIVE_TEXT_INVALID');
    identities.add(responseKey);
    return { id: `${responseKey}:native-generated`, role: 'assistant', content: item.text, timestamp: item.timestamp,
      nativeTurnKey: JSON.stringify([binding.interaction_id, item.turn_id]),
      nativeVoice: { responseKey, responseId: response.response_id, responseGeneration: response.response_generation,
        revision: item.revision, state: item.state as NativeGeneratedMessage['nativeVoice']['state'] } };
  });
  return { revision, messages };
}

export function nativeVoiceResponseKey(message: { id: string; role: string; nativeVoice?: { responseKey: string } }): string | null {
  if (message.role !== 'assistant' || !message.id.startsWith('live-voice:')) return null;
  if (message.nativeVoice) return message.nativeVoice.responseKey;
  const boundary = message.id.lastIndexOf(':native-audio:');
  return boundary < 0 ? null : message.id.slice(0, boundary);
}
