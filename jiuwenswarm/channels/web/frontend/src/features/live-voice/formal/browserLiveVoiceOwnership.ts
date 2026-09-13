export const BROWSER_LIVE_VOICE_OWNERSHIP_UNAVAILABLE = 'BROWSER_LIVE_VOICE_OWNERSHIP_UNAVAILABLE';
export const BROWSER_LIVE_VOICE_OWNERSHIP_SUPERSEDED = 'BROWSER_LIVE_VOICE_OWNERSHIP_SUPERSEDED';
export const BROWSER_LIVE_VOICE_TAKEOVER_CLEANUP_PENDING = 'BROWSER_LIVE_VOICE_TAKEOVER_CLEANUP_PENDING';

const BROWSER_LIVE_VOICE_OWNERSHIP_NAME = 'jiuwenswarm.live-voice.capture-owner.v1';

type BrowserLiveVoiceTakeover = () => void | Promise<void>;

type BrowserLiveVoiceClaim = Readonly<{
  issued_at: number;
  claim_id: string;
}>;

type BrowserLiveVoiceChannel = Readonly<{
  postMessage(message: unknown): void;
  addEventListener(type: 'message', listener: (event: { data: unknown }) => void): void;
  removeEventListener(type: 'message', listener: (event: { data: unknown }) => void): void;
  close(): void;
}>;

type BrowserLiveVoiceRequestLock = (
  name: string,
  signal: AbortSignal,
  callback: (lock: object | null) => void | Promise<void>,
) => Promise<unknown>;

export type BrowserLiveVoiceOwnershipEnvironment = Readonly<{
  requestLock?: BrowserLiveVoiceRequestLock | null;
  createChannel?: ((name: string) => BrowserLiveVoiceChannel) | null;
  now?: () => number;
  randomId?: () => string;
}>;

export interface BrowserLiveVoiceOwnership {
  acquire(onTakeover: BrowserLiveVoiceTakeover): Promise<void>;
  release(): Promise<void>;
  dispose(): Promise<void>;
  disposeAfterRelease(): void;
  isOwner(): boolean;
}

export interface BrowserLiveVoiceOwnershipBarrier {
  wait(): Promise<void>;
  run<T>(operation: () => Promise<T>): Promise<T>;
}

type Deferred<T> = Readonly<{
  promise: Promise<T>;
  resolve(value: T | PromiseLike<T>): void;
  reject(reason?: unknown): void;
}>;

type Acquisition = {
  claim: BrowserLiveVoiceClaim;
  controller: AbortController;
  granted: Deferred<void>;
  onTakeover: BrowserLiveVoiceTakeover;
  requestPromise: Promise<unknown> | null;
  cancelled: boolean;
  cancellationReason: string | null;
};

type HeldOwnership = {
  acquisition: Acquisition;
  releaseSignal: Deferred<void>;
  releaseRequested: boolean;
  revocationPromise: Promise<void> | null;
  revocationToken: object | null;
};

function createDeferred<T>(): Deferred<T> {
  let resolve!: (value: T | PromiseLike<T>) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return Object.freeze({ promise, resolve, reject });
}

function browserRequestLock(): BrowserLiveVoiceRequestLock | null {
  if (typeof navigator === 'undefined' || navigator.locks === undefined) return null;
  return (name, signal, callback) =>
    navigator.locks.request(name, { mode: 'exclusive', signal }, async lock => {
      await callback(lock);
    });
}

function browserCreateChannel(): ((name: string) => BrowserLiveVoiceChannel) | null {
  if (typeof BroadcastChannel === 'undefined') return null;
  return name => {
    const channel = new BroadcastChannel(name);
    const listenerWrappers = new Map<(event: { data: unknown }) => void, EventListener>();
    return Object.freeze({
      postMessage: message => channel.postMessage(message),
      addEventListener: (_type, listener) => {
        const wrapper: EventListener = event => listener({ data: (event as MessageEvent<unknown>).data });
        listenerWrappers.set(listener, wrapper);
        channel.addEventListener('message', wrapper);
      },
      removeEventListener: (_type, listener) => {
        const wrapper = listenerWrappers.get(listener);
        if (wrapper === undefined) return;
        listenerWrappers.delete(listener);
        channel.removeEventListener('message', wrapper);
      },
      close: () => channel.close(),
    });
  };
}

function randomOwnershipId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID();
  return `${Math.random().toString(36).slice(2)}-${Math.random().toString(36).slice(2)}`;
}

function browserClaimTimestamp(): number {
  if (typeof performance !== 'undefined') {
    const timestamp = Math.floor((performance.timeOrigin + performance.now()) * 1_000);
    if (Number.isSafeInteger(timestamp) && timestamp >= 0) return timestamp;
  }
  return Date.now() * 1_000;
}

function compareClaims(left: BrowserLiveVoiceClaim, right: BrowserLiveVoiceClaim): number {
  if (left.issued_at !== right.issued_at) return left.issued_at - right.issued_at;
  return left.claim_id.localeCompare(right.claim_id);
}

function parseTakeoverClaim(value: unknown): BrowserLiveVoiceClaim | null {
  if (typeof value !== 'object' || value === null) return null;
  const message = value as { type?: unknown; claim?: unknown };
  if (message.type !== 'takeover' || typeof message.claim !== 'object' || message.claim === null) return null;
  const claim = message.claim as { issued_at?: unknown; claim_id?: unknown };
  if (!Number.isSafeInteger(claim.issued_at) || (claim.issued_at as number) < 0) return null;
  if (typeof claim.claim_id !== 'string' || claim.claim_id.trim() === '') return null;
  return Object.freeze({ issued_at: claim.issued_at as number, claim_id: claim.claim_id });
}

class BrowserLiveVoiceOwnershipCoordinator implements BrowserLiveVoiceOwnership {
  readonly #requestLock: BrowserLiveVoiceRequestLock | null;
  readonly #createChannel: ((name: string) => BrowserLiveVoiceChannel) | null;
  readonly #now: () => number;
  readonly #randomId: () => string;
  readonly #onMessage = (event: { data: unknown }) => this.#handleMessage(event.data);
  #channel: BrowserLiveVoiceChannel | null = null;
  #latestObservedClaim: BrowserLiveVoiceClaim | null = null;
  #pending: Acquisition | null = null;
  #held: HeldOwnership | null = null;
  #disposed = false;
  #disposalPromise: Promise<void> | null = null;

  constructor(environment: BrowserLiveVoiceOwnershipEnvironment) {
    this.#requestLock = environment.requestLock === undefined ? browserRequestLock() : environment.requestLock;
    this.#createChannel = environment.createChannel === undefined ? browserCreateChannel() : environment.createChannel;
    this.#now = environment.now ?? browserClaimTimestamp;
    this.#randomId = environment.randomId ?? randomOwnershipId;
  }

  async acquire(onTakeover: BrowserLiveVoiceTakeover): Promise<void> {
    if (this.#disposed) throw new Error(BROWSER_LIVE_VOICE_OWNERSHIP_UNAVAILABLE);
    this.#ensureChannel();
    if (this.#requestLock === null) throw new Error(BROWSER_LIVE_VOICE_OWNERSHIP_UNAVAILABLE);
    if (this.#held !== null) {
      const held = this.#held;
      held.acquisition.onTakeover = onTakeover;
      if (held.releaseRequested || held.revocationPromise !== null) {
        const revocation = held.revocationPromise;
        if (revocation !== null) await revocation;
        if (!held.releaseRequested) throw new Error(BROWSER_LIVE_VOICE_TAKEOVER_CLEANUP_PENDING);
        await held.acquisition.requestPromise?.catch(() => undefined);
        await this.acquire(onTakeover);
        return;
      }
      const previousClaim = held.acquisition.claim;
      held.acquisition.claim = this.#mintClaim(previousClaim);
      try {
        this.#channel?.postMessage(Object.freeze({ type: 'takeover', claim: held.acquisition.claim }));
      } catch (error) {
        held.acquisition.claim = previousClaim;
        this.#revoke(held);
        await held.revocationPromise;
        throw error;
      }
      return;
    }
    let previousClaim: BrowserLiveVoiceClaim | null = null;
    if (this.#pending !== null) {
      const pending = this.#pending;
      previousClaim = pending.claim;
      pending.cancelled = true;
      pending.cancellationReason = BROWSER_LIVE_VOICE_OWNERSHIP_SUPERSEDED;
      if (this.#pending === pending) this.#pending = null;
      pending.controller.abort();
    }

    const acquisition: Acquisition = {
      claim: this.#mintClaim(previousClaim),
      controller: new AbortController(),
      granted: createDeferred<void>(),
      onTakeover,
      requestPromise: null,
      cancelled: false,
      cancellationReason: null,
    };
    this.#pending = acquisition;
    acquisition.requestPromise = this.#requestLock(
      BROWSER_LIVE_VOICE_OWNERSHIP_NAME,
      acquisition.controller.signal,
      async lock => {
        if (lock === null) throw new Error(BROWSER_LIVE_VOICE_OWNERSHIP_UNAVAILABLE);
        if (acquisition.cancelled) return;
        const held: HeldOwnership = {
          acquisition,
          releaseSignal: createDeferred<void>(),
          releaseRequested: false,
          revocationPromise: null,
          revocationToken: null,
        };
        if (this.#pending === acquisition) this.#pending = null;
        this.#held = held;
        acquisition.granted.resolve();
        const latest = this.#latestObservedClaim;
        if (latest !== null && compareClaims(latest, acquisition.claim) > 0) this.#revoke(held);
        await held.releaseSignal.promise;
        if (this.#held === held) this.#held = null;
      },
    );
    void acquisition.requestPromise.catch(error => {
      if (this.#pending === acquisition) this.#pending = null;
      if (this.#held?.acquisition === acquisition) this.#held = null;
      acquisition.granted.reject(
        acquisition.cancellationReason === null ? error : new Error(acquisition.cancellationReason),
      );
    });

    try {
      this.#channel?.postMessage(Object.freeze({ type: 'takeover', claim: acquisition.claim }));
    } catch (error) {
      acquisition.cancelled = true;
      acquisition.cancellationReason = BROWSER_LIVE_VOICE_OWNERSHIP_UNAVAILABLE;
      if (this.#pending === acquisition) this.#pending = null;
      acquisition.controller.abort();
      await acquisition.requestPromise.catch(() => undefined);
      await acquisition.granted.promise.catch(() => undefined);
      throw error;
    }
    await this.#awaitCurrentAcquisition(acquisition);
  }

  async release(): Promise<void> {
    const pending = this.#pending;
    if (pending !== null) {
      pending.cancelled = true;
      pending.cancellationReason = BROWSER_LIVE_VOICE_OWNERSHIP_SUPERSEDED;
      if (this.#pending === pending) this.#pending = null;
      pending.controller.abort();
      await pending.requestPromise?.catch(() => undefined);
    }

    const held = this.#held;
    if (held === null) return;
    if (held.revocationPromise !== null) await held.revocationPromise;
    if (this.#held !== held) {
      await held.acquisition.requestPromise?.catch(() => undefined);
      return;
    }
    held.releaseRequested = true;
    held.releaseSignal.resolve();
    await held.acquisition.requestPromise?.catch(() => undefined);
  }

  async dispose(): Promise<void> {
    if (this.#disposalPromise !== null) {
      await this.#disposalPromise;
      return;
    }
    if (this.#disposed) return;
    this.#disposed = true;
    await this.release();
    this.#closeChannel();
  }

  disposeAfterRelease(): void {
    if (this.#disposalPromise !== null) return;
    this.#disposed = true;
    const pending = this.#pending;
    if (pending !== null) {
      pending.cancelled = true;
      pending.cancellationReason = BROWSER_LIVE_VOICE_OWNERSHIP_SUPERSEDED;
      if (this.#pending === pending) this.#pending = null;
      pending.controller.abort();
    }
    const held = this.#held;
    if (held !== null) {
      held.releaseRequested = true;
      held.releaseSignal.resolve();
    }
    const completion = held?.acquisition.requestPromise ?? pending?.requestPromise ?? Promise.resolve();
    this.#disposalPromise = Promise.resolve(completion)
      .catch(() => undefined)
      .then(() => this.#closeChannel());
  }

  isOwner(): boolean {
    return this.#held !== null;
  }

  #ensureChannel(): void {
    if (this.#channel !== null) return;
    if (this.#createChannel === null) throw new Error(BROWSER_LIVE_VOICE_OWNERSHIP_UNAVAILABLE);
    try {
      this.#channel = this.#createChannel(BROWSER_LIVE_VOICE_OWNERSHIP_NAME);
      this.#channel.addEventListener('message', this.#onMessage);
    } catch {
      this.#channel = null;
      throw new Error(BROWSER_LIVE_VOICE_OWNERSHIP_UNAVAILABLE);
    }
  }

  #mintClaim(previousClaim: BrowserLiveVoiceClaim | null): BrowserLiveVoiceClaim {
    let issuedAt = this.#now();
    if (!Number.isSafeInteger(issuedAt) || issuedAt < 0) {
      throw new Error(BROWSER_LIVE_VOICE_OWNERSHIP_UNAVAILABLE);
    }
    for (const floor of [this.#latestObservedClaim, previousClaim]) {
      if (floor === null || issuedAt > floor.issued_at) continue;
      if (floor.issued_at >= Number.MAX_SAFE_INTEGER) {
        throw new Error(BROWSER_LIVE_VOICE_OWNERSHIP_UNAVAILABLE);
      }
      issuedAt = floor.issued_at + 1;
    }
    const claimId = this.#randomId();
    if (typeof claimId !== 'string' || claimId.trim() === '') {
      throw new Error(BROWSER_LIVE_VOICE_OWNERSHIP_UNAVAILABLE);
    }
    return Object.freeze({ issued_at: issuedAt, claim_id: claimId });
  }

  #closeChannel(): void {
    const channel = this.#channel;
    this.#channel = null;
    if (channel === null) return;
    channel.removeEventListener('message', this.#onMessage);
    channel.close();
  }

  async #awaitCurrentAcquisition(acquisition: Acquisition): Promise<void> {
    await acquisition.granted.promise;
    const held = this.#held;
    if (held !== null && held.acquisition === acquisition && held.revocationPromise !== null) {
      await held.revocationPromise;
      if (!held.releaseRequested) throw new Error(BROWSER_LIVE_VOICE_TAKEOVER_CLEANUP_PENDING);
    }
    if (held?.acquisition === acquisition && !held.releaseRequested) return;
    await acquisition.requestPromise?.catch(() => undefined);
    throw new Error(BROWSER_LIVE_VOICE_OWNERSHIP_SUPERSEDED);
  }

  #handleMessage(value: unknown): void {
    const claim = parseTakeoverClaim(value);
    if (claim === null) return;
    if (this.#latestObservedClaim === null || compareClaims(claim, this.#latestObservedClaim) > 0) {
      this.#latestObservedClaim = claim;
    }
    const held = this.#held;
    if (held !== null && compareClaims(claim, held.acquisition.claim) > 0) this.#revoke(held);
  }

  #revoke(held: HeldOwnership): void {
    if (this.#held !== held || held.revocationPromise !== null) return;
    const token = Object.freeze({});
    held.revocationToken = token;
    held.revocationPromise = (async () => {
      try {
        await held.acquisition.onTakeover();
        if (this.#held === held) {
          held.releaseRequested = true;
          held.releaseSignal.resolve();
        }
      } catch {
        // The successor remains queued behind this Web Lock until the losing
        // tab proves that its exact microphone/media cleanup has completed.
      } finally {
        if (held.revocationToken === token) {
          held.revocationToken = null;
          held.revocationPromise = null;
        }
      }
    })();
  }
}

class SerialBrowserLiveVoiceOwnershipBarrier implements BrowserLiveVoiceOwnershipBarrier {
  #tail: Promise<void> = Promise.resolve();

  wait(): Promise<void> {
    return this.#tail;
  }

  run<T>(operation: () => Promise<T>): Promise<T> {
    const prior = this.#tail;
    const current = (async () => {
      try {
        await prior;
      } catch {
        // A later explicit transition retries the retained exact owner.
      }
      return operation();
    })();
    const tail = current.then(() => undefined);
    void tail.catch(() => undefined);
    this.#tail = tail;
    return current;
  }
}

export function createBrowserLiveVoiceOwnership(
  environment: BrowserLiveVoiceOwnershipEnvironment = {},
): BrowserLiveVoiceOwnership {
  return new BrowserLiveVoiceOwnershipCoordinator(environment);
}

export function createBrowserLiveVoiceOwnershipBarrier(): BrowserLiveVoiceOwnershipBarrier {
  return new SerialBrowserLiveVoiceOwnershipBarrier();
}
