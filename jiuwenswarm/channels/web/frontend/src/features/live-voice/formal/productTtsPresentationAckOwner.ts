import type { AudioResponseRef } from './audioPort.js';

export interface ProductTtsPresentationAckAttempt<TAttempt> {
  readonly response: Readonly<AudioResponseRef>;
  readonly unitId: string;
  readonly seq: number;
  readonly attempt: TAttempt;
}

export interface ProductTtsPresentationAckSnapshot {
  readonly phase: 'active' | 'cancelled' | 'failed';
  readonly queued_count: number;
  readonly in_flight: boolean;
  readonly settled_count: number;
  readonly cancelled_count: number;
  readonly reason: string | null;
}

function sameResponse(left: Readonly<AudioResponseRef>, right: Readonly<AudioResponseRef>): boolean {
  return left.interaction_id === right.interaction_id
    && left.response_id === right.response_id
    && left.response_generation === right.response_generation;
}

export class ProductTtsPresentationAckOwner<TAttempt> {
  readonly #firstUnitSeq: 0 | 1;
  readonly #lastUnitSeq: 4;
  readonly #settle: (attempt: TAttempt) => Promise<void>;
  readonly #onFailure: (error: unknown) => void;
  readonly #queue: Readonly<ProductTtsPresentationAckAttempt<TAttempt>>[] = [];
  readonly #unitIds = new Set<string>();
  readonly #idleWaiters = new Set<() => void>();
  #phase: 'active' | 'cancelled' | 'failed' = 'active';
  #response: Readonly<AudioResponseRef> | null = null;
  #nextSeq: number;
  #inFlight = false;
  #settledCount = 0;
  #cancelledCount = 0;
  #reason: string | null = null;
  #generation = 0;

  constructor(input: Readonly<{
    firstUnitSeq: 0 | 1;
    lastUnitSeq: 4;
    settle: (attempt: TAttempt) => Promise<void>;
    onFailure: (error: unknown) => void;
  }>) {
    if (
      (input.firstUnitSeq !== 0 && input.firstUnitSeq !== 1)
      || input.lastUnitSeq !== 4
      || typeof input.settle !== 'function'
      || typeof input.onFailure !== 'function'
    ) {
      throw new TypeError('TTS presentation ACK policy is invalid');
    }
    this.#firstUnitSeq = input.firstUnitSeq;
    this.#lastUnitSeq = input.lastUnitSeq;
    this.#nextSeq = input.firstUnitSeq;
    this.#settle = input.settle;
    this.#onFailure = input.onFailure;
  }

  enqueue(input: Readonly<ProductTtsPresentationAckAttempt<TAttempt>>): void {
    if (this.#phase !== 'active') throw new Error('TTS presentation ACK owner is closed');
    if (!input || typeof input.unitId !== 'string' || input.unitId.length === 0) {
      throw new TypeError('TTS presentation ACK unit is invalid');
    }
    if (!Number.isSafeInteger(input.seq) || input.seq < this.#firstUnitSeq) {
      throw new TypeError('TTS presentation ACK sequence is invalid');
    }
    if (input.seq > this.#lastUnitSeq) {
      throw new Error('TTS presentation ACK sequence exceeds its bound');
    }
    if (input.seq !== this.#nextSeq) {
      throw new Error('TTS presentation ACK sequence is not contiguous');
    }
    if (this.#unitIds.has(input.unitId)) {
      throw new Error('TTS presentation ACK unit identity is reused');
    }
    if (this.#response === null) {
      this.#response = Object.freeze({ ...input.response });
    } else if (!sameResponse(this.#response, input.response)) {
      throw new Error('TTS presentation ACK response is foreign');
    }
    this.#unitIds.add(input.unitId);
    this.#queue.push(Object.freeze({ ...input }));
    this.#nextSeq += 1;
    this.#drain();
  }

  cancel(reason: string): void {
    if (this.#phase !== 'active') return;
    this.#phase = 'cancelled';
    this.#reason = reason || 'TTS_PRESENTATION_ACK_CANCELLED';
    this.#cancelledCount += this.#queue.length + (this.#inFlight ? 1 : 0);
    this.#queue.splice(0);
    this.#inFlight = false;
    this.#generation += 1;
    this.#resolveIdle();
  }

  whenIdle(): Promise<void> {
    if (!this.#inFlight && this.#queue.length === 0) return Promise.resolve();
    return new Promise(resolve => this.#idleWaiters.add(resolve));
  }

  snapshot(): Readonly<ProductTtsPresentationAckSnapshot> {
    return Object.freeze({
      phase: this.#phase,
      queued_count: this.#queue.length,
      in_flight: this.#inFlight,
      settled_count: this.#settledCount,
      cancelled_count: this.#cancelledCount,
      reason: this.#reason,
    });
  }

  #drain(): void {
    if (this.#phase !== 'active' || this.#inFlight) return;
    const next = this.#queue.shift();
    if (next === undefined) {
      this.#resolveIdle();
      return;
    }
    this.#inFlight = true;
    const generation = this.#generation;
    let settlement: Promise<void>;
    try {
      settlement = this.#settle(next.attempt);
    } catch (error) {
      settlement = Promise.reject(error);
    }
    void Promise.resolve(settlement).then(
      () => {
        if (this.#phase !== 'active' || this.#generation !== generation) return;
        this.#inFlight = false;
        this.#settledCount += 1;
        this.#drain();
      },
      error => {
        if (this.#phase !== 'active' || this.#generation !== generation) return;
        this.#phase = 'failed';
        this.#reason = 'TTS_PRESENTATION_ACK_FAILED';
        this.#inFlight = false;
        this.#cancelledCount += this.#queue.length;
        this.#queue.splice(0);
        this.#generation += 1;
        this.#onFailure(error);
        this.#resolveIdle();
      },
    );
  }

  #resolveIdle(): void {
    if (this.#inFlight || this.#queue.length > 0) return;
    for (const resolve of this.#idleWaiters) resolve();
    this.#idleWaiters.clear();
  }
}
