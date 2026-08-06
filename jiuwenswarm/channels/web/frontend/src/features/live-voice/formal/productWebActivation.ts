export const PRODUCT_P2_ACTIVATE_METHOD = 'live_voice.composition.p2.activate' as const;
export const PRODUCT_P2_CLOSE_METHOD = 'live_voice.composition.p2.close' as const;
export const PRODUCT_P3_TASK_LIST_METHOD = 'live_voice.task.list' as const;
export const PRODUCT_P3_PROGRESS_ACTIVATE_METHOD = 'live_voice.composition.p3.progress.activate' as const;
export const PRODUCT_P3_PROGRESS_CLOSE_METHOD = 'live_voice.composition.p3.progress.close' as const;

type JsonObject = Readonly<Record<string, unknown>>;

export type ProductWebP2ActivationStatus =
  | 'disabled'
  | 'idle'
  | 'activating'
  | 'active'
  | 'unavailable'
  | 'cleanup_pending'
  | 'closed';

export interface ProductWebP2ActivationBinding {
  readonly session_id: string;
  readonly correlation_id: string;
  readonly interaction_id: string;
  readonly activation_id: string;
  readonly activation_generation: number;
}

export interface ProductWebP2ActivationSnapshot {
  readonly status: ProductWebP2ActivationStatus;
  readonly binding: ProductWebP2ActivationBinding | null;
  readonly reason: string | null;
}

export interface ProductWebP3ProgressBinding {
  readonly session_id: string;
  readonly task_id: string;
  readonly correlation_id: string;
  readonly origin_id: string;
  readonly generation_id: string;
  readonly generation: number;
}

export interface ProductWebP3ProgressSnapshot {
  readonly status: ProductWebP2ActivationStatus;
  readonly binding: ProductWebP3ProgressBinding | null;
  readonly reason: string | null;
}

type ProductWebCloseRetryObserver<TSnapshot> = (
  snapshot: Readonly<TSnapshot>,
  attempt: number
) => void;

export interface ProductWebCloseRetryOptions<TSnapshot> {
  readonly max_attempts?: number;
  readonly retry_delay_ms?: number;
  readonly on_retry?: ProductWebCloseRetryObserver<TSnapshot>;
}

type ProductWebAmbiguousActivationError = Error & {
  readonly product_activation_cleanup_required: true;
};

const AMBIGUOUS_ACTIVATION_TRANSPORT_CODES = new Set([
  'REQUEST_TIMEOUT',
  'WS_DISCONNECTED',
  'WS_CLOSED',
]);

export type ProductWebRequest = (
  method: string,
  params: Record<string, unknown>
) => Promise<unknown>;

function objectValue(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function requiredText(value: string, field: string): string {
  const text = value.trim();
  if (!text || text.length > 256) throw new Error(`${field} is invalid`);
  return text;
}

function freezeBinding(
  input: Readonly<ProductWebP2ActivationBinding>
): ProductWebP2ActivationBinding {
  if (!Number.isSafeInteger(input.activation_generation) || input.activation_generation <= 0) {
    throw new Error('activation_generation is invalid');
  }
  return Object.freeze({
    session_id: requiredText(input.session_id, 'session_id'),
    correlation_id: requiredText(input.correlation_id, 'correlation_id'),
    interaction_id: requiredText(input.interaction_id, 'interaction_id'),
    activation_id: requiredText(input.activation_id, 'activation_id'),
    activation_generation: input.activation_generation,
  });
}

function sameBinding(
  left: Readonly<ProductWebP2ActivationBinding>,
  right: Readonly<ProductWebP2ActivationBinding>
): boolean {
  return (
    left.session_id === right.session_id &&
    left.correlation_id === right.correlation_id &&
    left.interaction_id === right.interaction_id &&
    left.activation_id === right.activation_id &&
    left.activation_generation === right.activation_generation
  );
}

function requireResult(
  value: unknown,
  expectedStatus: 'active' | 'closed',
  binding: Readonly<ProductWebP2ActivationBinding>
): JsonObject {
  const payload = objectValue(value);
  const result = objectValue(payload?.result);
  if (payload?.ok !== true || result?.status !== expectedStatus) {
    throw new Error(`product P2 ${expectedStatus} response is unavailable`);
  }
  if (expectedStatus === 'active') {
    if (
      result.session_id !== binding.session_id ||
      result.correlation_id !== binding.correlation_id ||
      result.interaction_id !== binding.interaction_id ||
      result.activation_id !== binding.activation_id ||
      result.activation_generation !== binding.activation_generation
    ) {
      throw new Error('product P2 activation binding mismatch');
    }
  } else if (
    result.session_id !== binding.session_id ||
    result.correlation_id !== binding.correlation_id ||
    result.interaction_id !== binding.interaction_id ||
    result.activation_id !== binding.activation_id ||
    result.activation_generation !== binding.activation_generation
  ) {
    throw new Error('product P2 close binding mismatch');
  }
  return Object.freeze({ ...result });
}

function selectSingleActiveTask(value: unknown): string {
  const payload = objectValue(value);
  const result = objectValue(payload?.result);
  const tasks = result?.tasks;
  if (payload?.ok !== true || !Array.isArray(tasks)) {
    throw new Error('formal task list is unavailable');
  }
  const active: string[] = [];
  for (const item of tasks) {
    const task = objectValue(item);
    if (!task || typeof task.task_id !== 'string' || typeof task.state !== 'string') {
      throw new Error('formal task list binding is invalid');
    }
    const taskId = requiredText(task.task_id, 'task_id');
    const state = requiredText(task.state, 'task.state');
    if (state !== 'terminal') active.push(taskId);
  }
  if (active.length !== 1) {
    throw new Error('formal text progress requires exactly one active task');
  }
  return active[0]!;
}

function freezeP3Binding(
  input: Readonly<ProductWebP3ProgressBinding>
): ProductWebP3ProgressBinding {
  if (!Number.isSafeInteger(input.generation) || input.generation <= 0) {
    throw new Error('generation is invalid');
  }
  return Object.freeze({
    session_id: requiredText(input.session_id, 'session_id'),
    task_id: requiredText(input.task_id, 'task_id'),
    correlation_id: requiredText(input.correlation_id, 'correlation_id'),
    origin_id: requiredText(input.origin_id, 'origin_id'),
    generation_id: requiredText(input.generation_id, 'generation_id'),
    generation: input.generation,
  });
}

function requireP3Result(
  value: unknown,
  expectedStatus: 'active' | 'closed',
  binding: Readonly<ProductWebP3ProgressBinding>
): JsonObject {
  const payload = objectValue(value);
  const result = objectValue(payload?.result);
  if (
    payload?.ok !== true ||
    result?.status !== expectedStatus ||
    result.session_id !== binding.session_id ||
    result.task_id !== binding.task_id ||
    result.correlation_id !== binding.correlation_id ||
    result.origin_id !== binding.origin_id ||
    result.generation_id !== binding.generation_id ||
    result.generation !== binding.generation
  ) {
    throw new Error(`product P3 progress ${expectedStatus} binding mismatch`);
  }
  return Object.freeze({ ...result });
}

function ambiguousActivationResponse(error: unknown): ProductWebAmbiguousActivationError {
  const message = error instanceof Error
    ? error.message
    : 'product activation response binding is unavailable';
  const wrapped = new Error(message) as ProductWebAmbiguousActivationError;
  wrapped.name = 'ProductWebAmbiguousActivationError';
  Object.defineProperty(wrapped, 'product_activation_cleanup_required', {
    value: true,
    enumerable: true,
  });
  return wrapped;
}

/** True only when the request may have opened a route without a usable reply. */
export function requiresProductActivationCleanup(error: unknown): boolean {
  const candidate = objectValue(error);
  return (
    candidate?.product_activation_cleanup_required === true ||
    (typeof candidate?.code === 'string' &&
      AMBIGUOUS_ACTIVATION_TRANSPORT_CODES.has(candidate.code))
  );
}

function closeWithBoundedRetry<TSnapshot>(input: {
  close: () => Promise<TSnapshot>;
  snapshot: () => TSnapshot;
  options: ProductWebCloseRetryOptions<TSnapshot>;
}): Promise<TSnapshot> {
  const maxAttempts = input.options.max_attempts ?? 3;
  const retryDelayMs = input.options.retry_delay_ms ?? 100;
  if (!Number.isSafeInteger(maxAttempts) || maxAttempts <= 0) {
    return Promise.reject(new Error('cleanup retry attempts are invalid'));
  }
  if (!Number.isSafeInteger(retryDelayMs) || retryDelayMs < 0) {
    return Promise.reject(new Error('cleanup retry delay is invalid'));
  }
  const run = async (): Promise<TSnapshot> => {
    let lastError: unknown = new Error('product cleanup unavailable');
    for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
      try {
        return await input.close();
      } catch (error) {
        lastError = error;
        input.options.on_retry?.(input.snapshot(), attempt);
        if (attempt < maxAttempts && retryDelayMs > 0) {
          await new Promise(resolve => setTimeout(resolve, retryDelayMs));
        }
      }
    }
    throw lastError;
  };
  return run();
}

/**
 * Stock-Web owner for one exact P2 activation lease.
 *
 * The owner deliberately has no bearer-token field. The default-off Gateway
 * credential bridge injects the bounded Alpha bearer server-side. An ambiguous
 * response-lost activation retains enough exact binding to attempt cleanup;
 * an authoritative rejection remains unavailable without fake ownership.
 */
export class ProductWebP2ActivationOwner {
  private readonly enabled: boolean;
  private readonly request: ProductWebRequest;
  private readonly onSnapshot?: (snapshot: ProductWebP2ActivationSnapshot) => void;
  private binding: ProductWebP2ActivationBinding | null = null;
  private status: ProductWebP2ActivationStatus;
  private reason: string | null = null;
  private activationAttempted = false;
  private cleanupRequired = false;
  private activationPromise: Promise<ProductWebP2ActivationSnapshot> | null = null;
  private closePromise: Promise<ProductWebP2ActivationSnapshot> | null = null;
  private closeRetryPromise: Promise<ProductWebP2ActivationSnapshot> | null = null;
  private readonly closeRetryObservers = new Set<
    ProductWebCloseRetryObserver<ProductWebP2ActivationSnapshot>
  >();

  constructor(input: {
    enabled: boolean;
    request: ProductWebRequest;
    on_snapshot?: (snapshot: ProductWebP2ActivationSnapshot) => void;
  }) {
    if (typeof input.request !== 'function') throw new Error('product request owner is required');
    this.enabled = input.enabled;
    this.request = input.request;
    this.onSnapshot = input.on_snapshot;
    this.status = input.enabled ? 'idle' : 'disabled';
    this.publish();
  }

  snapshot(): ProductWebP2ActivationSnapshot {
    return Object.freeze({ status: this.status, binding: this.binding, reason: this.reason });
  }

  needsCleanup(): boolean {
    return this.activationPromise !== null || this.cleanupRequired;
  }

  start(
    input: Readonly<ProductWebP2ActivationBinding>
  ): Promise<ProductWebP2ActivationSnapshot> {
    if (!this.enabled) return Promise.resolve(this.snapshot());
    const binding = freezeBinding(input);
    if (this.binding && !sameBinding(this.binding, binding)) {
      return Promise.reject(new Error('a different product P2 activation is already owned'));
    }
    if (this.activationPromise) return this.activationPromise;
    if (this.status === 'active') return Promise.resolve(this.snapshot());
    this.binding = binding;
    this.activationAttempted = true;
    this.cleanupRequired = false;
    this.status = 'activating';
    this.reason = null;
    this.publish();
    this.activationPromise = this.request(PRODUCT_P2_ACTIVATE_METHOD, { ...binding })
      .then(value => {
        try {
          requireResult(value, 'active', binding);
        } catch (error) {
          throw ambiguousActivationResponse(error);
        }
        this.cleanupRequired = true;
        this.status = 'active';
        this.reason = null;
        return this.publish();
      })
      .catch(error => {
        this.cleanupRequired = requiresProductActivationCleanup(error);
        this.status = 'unavailable';
        this.reason = error instanceof Error ? error.message : 'product P2 activation unavailable';
        this.publish();
        throw error;
      })
      .finally(() => {
        this.activationPromise = null;
      });
    return this.activationPromise;
  }

  close(): Promise<ProductWebP2ActivationSnapshot> {
    if (!this.enabled) {
      this.status = 'disabled';
      return Promise.resolve(this.publish());
    }
    if (this.closePromise) return this.closePromise;
    const waitForActivation = this.activationPromise
      ? this.activationPromise.catch(() => this.snapshot())
      : Promise.resolve(this.snapshot());
    this.closePromise = waitForActivation
      .then(async () => {
        const binding = this.binding;
        if (!binding || !this.activationAttempted || !this.cleanupRequired) {
          this.status = 'closed';
          this.reason = null;
          this.binding = null;
          this.activationAttempted = false;
          this.cleanupRequired = false;
          return this.publish();
        }
        const value = await this.request(PRODUCT_P2_CLOSE_METHOD, { ...binding });
        requireResult(value, 'closed', binding);
        this.status = 'closed';
        this.reason = null;
        this.binding = null;
        this.activationAttempted = false;
        this.cleanupRequired = false;
        return this.publish();
      })
      .catch(error => {
        this.status = 'cleanup_pending';
        this.reason = error instanceof Error ? error.message : 'product P2 cleanup pending';
        this.publish();
        throw error;
      })
      .finally(() => {
        this.closePromise = null;
      });
    return this.closePromise;
  }

  closeWithRetry(
    options: ProductWebCloseRetryOptions<ProductWebP2ActivationSnapshot> = {}
  ): Promise<ProductWebP2ActivationSnapshot> {
    if (options.on_retry) {
      this.closeRetryObservers.add(options.on_retry);
      if (this.closeRetryPromise && this.status === 'cleanup_pending') {
        try {
          options.on_retry(this.snapshot(), 0);
        } catch {
          // A diagnostic observer must never interrupt exact cleanup.
        }
      }
    }
    if (this.closeRetryPromise) return this.closeRetryPromise;
    let retained: Promise<ProductWebP2ActivationSnapshot>;
    retained = closeWithBoundedRetry({
      close: () => this.close(),
      snapshot: () => this.snapshot(),
      options: {
        ...options,
        on_retry: (snapshot, attempt) => {
          for (const observer of this.closeRetryObservers) {
            try {
              observer(snapshot, attempt);
            } catch {
              // A diagnostic observer must never interrupt exact cleanup.
            }
          }
        },
      },
    }).finally(() => {
      if (this.closeRetryPromise === retained) {
        this.closeRetryPromise = null;
        this.closeRetryObservers.clear();
      }
    });
    this.closeRetryPromise = retained;
    return retained;
  }

  private publish(): ProductWebP2ActivationSnapshot {
    const snapshot = this.snapshot();
    this.onSnapshot?.(snapshot);
    return snapshot;
  }
}

/** Retained stock-Web owner for one query-selected formal text-progress route. */
export class ProductWebP3ProgressOwner {
  private readonly enabled: boolean;
  private readonly request: ProductWebRequest;
  private readonly onSnapshot?: (snapshot: ProductWebP3ProgressSnapshot) => void;
  private binding: ProductWebP3ProgressBinding | null = null;
  private status: ProductWebP2ActivationStatus;
  private reason: string | null = null;
  private activationAttempted = false;
  private cleanupRequired = false;
  private startPromise: Promise<ProductWebP3ProgressSnapshot> | null = null;
  private closePromise: Promise<ProductWebP3ProgressSnapshot> | null = null;
  private closeRetryPromise: Promise<ProductWebP3ProgressSnapshot> | null = null;
  private readonly closeRetryObservers = new Set<
    ProductWebCloseRetryObserver<ProductWebP3ProgressSnapshot>
  >();

  constructor(input: {
    enabled: boolean;
    request: ProductWebRequest;
    on_snapshot?: (snapshot: ProductWebP3ProgressSnapshot) => void;
  }) {
    if (typeof input.request !== 'function') throw new Error('product request owner is required');
    this.enabled = input.enabled;
    this.request = input.request;
    this.onSnapshot = input.on_snapshot;
    this.status = input.enabled ? 'idle' : 'disabled';
    this.publish();
  }

  snapshot(): ProductWebP3ProgressSnapshot {
    return Object.freeze({ status: this.status, binding: this.binding, reason: this.reason });
  }

  needsCleanup(): boolean {
    return this.startPromise !== null || this.cleanupRequired;
  }

  start(input: {
    session_id: string;
    correlation_id: string;
    origin_id: string;
    generation_id: string;
    generation: number;
  }): Promise<ProductWebP3ProgressSnapshot> {
    if (!this.enabled) return Promise.resolve(this.snapshot());
    if (this.startPromise) return this.startPromise;
    if (this.status === 'active') return Promise.resolve(this.snapshot());
    const sessionId = requiredText(input.session_id, 'session_id');
    const base = {
      session_id: sessionId,
      correlation_id: requiredText(input.correlation_id, 'correlation_id'),
      origin_id: requiredText(input.origin_id, 'origin_id'),
      generation_id: requiredText(input.generation_id, 'generation_id'),
      generation: input.generation,
    };
    if (!Number.isSafeInteger(base.generation) || base.generation <= 0) {
      return Promise.reject(new Error('generation is invalid'));
    }
    this.cleanupRequired = false;
    this.status = 'activating';
    this.reason = null;
    this.publish();
    this.startPromise = this.request(PRODUCT_P3_TASK_LIST_METHOD, { session_id: sessionId })
      .then(value => {
        const taskId = selectSingleActiveTask(value);
        const binding = freezeP3Binding({ ...base, task_id: taskId });
        this.binding = binding;
        this.activationAttempted = true;
        return this.request(PRODUCT_P3_PROGRESS_ACTIVATE_METHOD, { ...binding })
          .then(response => {
            try {
              requireP3Result(response, 'active', binding);
            } catch (error) {
              throw ambiguousActivationResponse(error);
            }
            this.cleanupRequired = true;
            this.status = 'active';
            this.reason = null;
            return this.publish();
          });
      })
      .catch(error => {
        this.cleanupRequired = (
          this.binding !== null && requiresProductActivationCleanup(error)
        );
        this.status = 'unavailable';
        this.reason = error instanceof Error ? error.message : 'product P3 progress unavailable';
        this.publish();
        throw error;
      })
      .finally(() => {
        this.startPromise = null;
      });
    return this.startPromise;
  }

  close(): Promise<ProductWebP3ProgressSnapshot> {
    if (!this.enabled) {
      this.status = 'disabled';
      return Promise.resolve(this.publish());
    }
    if (this.closePromise) return this.closePromise;
    const waitForStart = this.startPromise
      ? this.startPromise.catch(() => this.snapshot())
      : Promise.resolve(this.snapshot());
    this.closePromise = waitForStart
      .then(async () => {
        const binding = this.binding;
        if (!binding || !this.activationAttempted || !this.cleanupRequired) {
          this.status = 'closed';
          this.reason = null;
          this.binding = null;
          this.activationAttempted = false;
          this.cleanupRequired = false;
          return this.publish();
        }
        const value = await this.request(PRODUCT_P3_PROGRESS_CLOSE_METHOD, {
          ...binding,
        });
        requireP3Result(value, 'closed', binding);
        this.status = 'closed';
        this.reason = null;
        this.binding = null;
        this.activationAttempted = false;
        this.cleanupRequired = false;
        return this.publish();
      })
      .catch(error => {
        this.status = 'cleanup_pending';
        this.reason = error instanceof Error ? error.message : 'product P3 cleanup pending';
        this.publish();
        throw error;
      })
      .finally(() => {
        this.closePromise = null;
      });
    return this.closePromise;
  }

  closeWithRetry(
    options: ProductWebCloseRetryOptions<ProductWebP3ProgressSnapshot> = {}
  ): Promise<ProductWebP3ProgressSnapshot> {
    if (options.on_retry) {
      this.closeRetryObservers.add(options.on_retry);
      if (this.closeRetryPromise && this.status === 'cleanup_pending') {
        try {
          options.on_retry(this.snapshot(), 0);
        } catch {
          // A diagnostic observer must never interrupt exact cleanup.
        }
      }
    }
    if (this.closeRetryPromise) return this.closeRetryPromise;
    let retained: Promise<ProductWebP3ProgressSnapshot>;
    retained = closeWithBoundedRetry({
      close: () => this.close(),
      snapshot: () => this.snapshot(),
      options: {
        ...options,
        on_retry: (snapshot, attempt) => {
          for (const observer of this.closeRetryObservers) {
            try {
              observer(snapshot, attempt);
            } catch {
              // A diagnostic observer must never interrupt exact cleanup.
            }
          }
        },
      },
    }).finally(() => {
      if (this.closeRetryPromise === retained) {
        this.closeRetryPromise = null;
        this.closeRetryObservers.clear();
      }
    });
    this.closeRetryPromise = retained;
    return retained;
  }

  private publish(): ProductWebP3ProgressSnapshot {
    const snapshot = this.snapshot();
    this.onSnapshot?.(snapshot);
    return snapshot;
  }
}
