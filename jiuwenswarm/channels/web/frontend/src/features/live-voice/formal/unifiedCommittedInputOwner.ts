export const PRODUCT_UNIFIED_COMMITTED_INPUT_METHOD = 'live_voice.composition.unified.submit' as const;

type JsonObject = Readonly<Record<string, unknown>>;

export type UnifiedCommittedInputRequest = (
  method: typeof PRODUCT_UNIFIED_COMMITTED_INPUT_METHOD,
  params: Record<string, unknown>,
  requestId: string,
) => Promise<unknown>;

export type UnifiedCommittedInputBinding = Readonly<{
  session_id: string;
  correlation_id: string;
  interaction_id: string;
  activation_id: string;
  activation_generation: number;
}>;

export type UnifiedAuthoritativeFinal = Readonly<{
  request_id: string;
  commit_id: string;
  turn_id: string;
  committed_at: string;
  text: string;
  voice_commit_receipt: string;
}>;

function requiredText(value: unknown, name: string, maximum = 100_000): string {
  if (typeof value !== 'string' || !value.trim() || new TextEncoder().encode(value).length > maximum) {
    throw new Error(`${name} is invalid`);
  }
  return value;
}
function requiredContent(value: unknown, name: string): string {
  if (typeof value !== 'string' || !value.trim() || [...value].length > 8_192) {
    throw new Error(`${name} is invalid`);
  }
  for (let index = 0; index < value.length; index += 1) {
    const unit = value.charCodeAt(index);
    if (unit >= 0xd800 && unit <= 0xdbff) {
      const next = value.charCodeAt(index + 1);
      if (!(next >= 0xdc00 && next <= 0xdfff)) throw new Error(`${name} is invalid`);
      index += 1;
    } else if (unit >= 0xdc00 && unit <= 0xdfff) {
      throw new Error(`${name} is invalid`);
    }
  }
  if (new TextEncoder().encode(value).length > 32_768) throw new Error(`${name} is invalid`);
  return value;
}
function requireSafeGeneration(value: unknown): number {
  if (!Number.isSafeInteger(value) || Number(value) <= 0) throw new Error('activation_generation is invalid');
  return Number(value);
}

function exactKeys(value: Record<string, unknown>, required: readonly string[], optional: readonly string[] = []): boolean {
  const allowed = new Set([...required, ...optional]);
  return required.every(key => Object.prototype.hasOwnProperty.call(value, key))
    && Object.keys(value).every(key => allowed.has(key));
}

function exactControlResult(
  value: unknown,
  requestId: string,
  binding: UnifiedCommittedInputBinding,
  input: UnifiedAuthoritativeFinal,
): JsonObject {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) throw new Error('unified committed-input response is invalid');
  const envelope = value as Record<string, unknown>;
  const payload = Object.prototype.hasOwnProperty.call(envelope, 'payload')
    ? exactKeys(envelope, ['payload'])
      && envelope.payload !== null
      && typeof envelope.payload === 'object'
      && !Array.isArray(envelope.payload)
      ? (envelope.payload as Record<string, unknown>)
      : null
    : envelope;
  if (
    payload === null
    || !exactKeys(payload, ['request_id', 'ok', 'result', 'error'], ['product_composition'])
    || payload.request_id !== requestId
    || typeof payload.ok !== 'boolean'
    || (
      Object.prototype.hasOwnProperty.call(payload, 'product_composition')
      && (payload.product_composition === null
        || typeof payload.product_composition !== 'object'
        || Array.isArray(payload.product_composition))
    )
  ) throw new Error('unified committed-input response binding is invalid');
  if (payload.ok !== true) {
    const error = payload.error;
    const errorObject = error !== null && typeof error === 'object' && !Array.isArray(error)
      ? (error as Record<string, unknown>)
      : null;
    if (
      payload.result !== null
      || errorObject === null
      || !exactKeys(errorObject, ['code', 'reason', 'message'])
      || typeof errorObject.code !== 'string'
      || typeof errorObject.reason !== 'string'
      || typeof errorObject.message !== 'string'
    ) throw new Error('unified committed-input rejection is invalid');
    throw Object.assign(new Error('unified committed-input request was rejected'), {
      reason: errorObject.reason,
    });
  }
  const result = payload.result;
  if (
    payload.error !== null
    || result === null
    || typeof result !== 'object'
    || Array.isArray(result)
  ) throw new Error('unified committed-input success is invalid');
  const resultObject = result as Record<string, unknown>;
  const status = resultObject.status;
  const authoritativePresentation = status === 'authoritative_presentation_accepted';
  const roundAccepted = status === 'round_accepted';
  if (
    (!authoritativePresentation && !roundAccepted)
    || (authoritativePresentation && !exactKeys(resultObject, ['status', 'response'], ['task_id']))
    || (roundAccepted && !exactKeys(resultObject, [
      'status',
      'session_id',
      'correlation_id',
      'interaction_id',
      'activation_id',
      'activation_generation',
      'turn_id',
      'commit_id',
      'request_id',
      'round_id',
      'response',
    ]))
    || resultObject.response === null
    || typeof resultObject.response !== 'object'
    || Array.isArray(resultObject.response)
  ) throw new Error('unified committed-input result is invalid');
  if (
    roundAccepted
    && (
      resultObject.session_id !== binding.session_id
      || resultObject.correlation_id !== binding.correlation_id
      || resultObject.interaction_id !== binding.interaction_id
      || resultObject.activation_id !== binding.activation_id
      || resultObject.activation_generation !== binding.activation_generation
      || resultObject.turn_id !== input.turn_id
      || resultObject.commit_id !== input.commit_id
      || typeof resultObject.request_id !== 'string'
      || !resultObject.request_id.trim()
      || new TextEncoder().encode(resultObject.request_id).length > 256
      || typeof resultObject.round_id !== 'string'
      || !resultObject.round_id.trim()
      || new TextEncoder().encode(resultObject.round_id).length > 256
    )
  ) throw new Error('unified committed-input round binding is invalid');
  const response = resultObject.response as Record<string, unknown>;
  if (
    !exactKeys(response, ['interaction_id', 'response_id', 'response_generation'])
    || response.interaction_id !== binding.interaction_id
    || typeof response.response_id !== 'string'
    || !response.response_id.trim()
    || new TextEncoder().encode(response.response_id).length > 256
    || !Number.isSafeInteger(response.response_generation)
    || Number(response.response_generation) < 0
  ) throw new Error('unified committed-input presentation binding is invalid');
  if (
    authoritativePresentation
    && Object.prototype.hasOwnProperty.call(resultObject, 'task_id')
    && (typeof resultObject.task_id !== 'string' || !resultObject.task_id.trim())
  ) throw new Error('unified committed-input task_id is invalid');
  return Object.freeze({ ...payload });
}

function cacheBusinessResult(payload: JsonObject): JsonObject {
  const { request_id: _requestId, ...business } = payload;
  return Object.freeze({ ...business });
}

function bindCachedResult(business: JsonObject, requestId: string): JsonObject {
  return Object.freeze({ request_id: requestId, ...business });
}

/**
 * One in-memory transport owner for the independent server-side unified
 * committed-input journal. It never stores speech receipts or transcript text
 * in sessionStorage/localStorage and retains only one unresolved final.
 */
export class ProductUnifiedCommittedInputOwner {
  readonly #request: UnifiedCommittedInputRequest;
  #pending: Readonly<{ fingerprint: string; promise: Promise<JsonObject> }> | null = null;
  readonly #completed = new Map<string, JsonObject>();

  constructor(request: UnifiedCommittedInputRequest) {
    if (typeof request !== 'function') throw new Error('unified committed-input request transport is required');
    this.#request = request;
  }

  hasPending(): boolean {
    return this.#pending !== null;
  }

  submit(binding: UnifiedCommittedInputBinding, input: UnifiedAuthoritativeFinal): Promise<JsonObject> {
    const requestId = requiredText(input.request_id, 'request_id', 256);
    const params = {
      session_id: requiredText(binding.session_id, 'session_id', 256),
      correlation_id: requiredText(binding.correlation_id, 'correlation_id', 256),
      interaction_id: requiredText(binding.interaction_id, 'interaction_id', 256),
      activation_id: requiredText(binding.activation_id, 'activation_id', 256),
      activation_generation: requireSafeGeneration(binding.activation_generation),
      commit_id: requiredText(input.commit_id, 'commit_id', 256),
      turn_id: requiredText(input.turn_id, 'turn_id', 256),
      committed_at: requiredText(input.committed_at, 'committed_at', 64),
      text: requiredContent(input.text, 'text'),
      input_state: 'final' as const,
      voice_commit_receipt: requiredText(input.voice_commit_receipt, 'voice_commit_receipt', 16_384),
    };
    const fingerprint = JSON.stringify(params);
    const replay = this.#completed.get(fingerprint);
    if (replay !== undefined) return Promise.resolve(bindCachedResult(replay, requestId));
    if (this.#pending !== null) {
      if (this.#pending.fingerprint !== fingerprint) {
        return Promise.reject(new Error('a different authoritative final is still unresolved'));
      }
      return this.#pending.promise.then(result => bindCachedResult(cacheBusinessResult(result), requestId));
    }
    const promise = this.#request(PRODUCT_UNIFIED_COMMITTED_INPUT_METHOD, params, requestId)
      .then(value => {
        const result = exactControlResult(value, requestId, binding, input);
        if (this.#completed.size >= 128) this.#completed.delete(this.#completed.keys().next().value as string);
        this.#completed.set(fingerprint, cacheBusinessResult(result));
        return result;
      })
      .finally(() => {
        if (this.#pending?.promise === promise) this.#pending = null;
      });
    this.#pending = Object.freeze({ fingerprint, promise });
    return promise;
  }
}
