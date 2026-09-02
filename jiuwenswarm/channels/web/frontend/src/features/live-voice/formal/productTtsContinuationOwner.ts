import type { AudioResponseRef } from './audioPort.js';

export interface ProductTtsContinuationUnit {
  readonly response: Readonly<AudioResponseRef>;
  readonly unitId: string;
  readonly seq: number;
  readonly sourceStartUtf8: number;
  readonly sourceEndUtf8: number;
  readonly text: string;
}

export interface ProductTtsContinuationSnapshot {
  readonly phase: 'active' | 'cancelled';
  readonly queued_count: number;
  readonly active_count: number;
  readonly prepared_count: number;
  readonly released_count: number;
  readonly rendered_count: number;
  readonly cancelled_count: number;
  readonly wasted_prefetch_count: number;
  readonly retry_count: 0;
  readonly reason: string | null;
}

type EntryState = 'queued' | 'preparing' | 'prepared' | 'released' | 'rendered' | 'cancelled';

interface Entry<TPrepared> {
  readonly unit: Readonly<ProductTtsContinuationUnit>;
  state: EntryState;
  controller: AbortController | null;
  prepared: TPrepared | null;
}

export class ProductTtsContinuationViolation extends Error {
  readonly reason: string;

  constructor(reason: string, message: string) {
    super(message);
    this.name = 'ProductTtsContinuationViolation';
    this.reason = reason;
  }
}

function sameResponse(left: Readonly<AudioResponseRef>, right: Readonly<AudioResponseRef>): boolean {
  return left.interaction_id === right.interaction_id
    && left.response_id === right.response_id
    && left.response_generation === right.response_generation;
}

export class ProductTtsContinuationOwner<TPrepared> {
  readonly #prepare: (
    unit: Readonly<ProductTtsContinuationUnit>,
    signal: AbortSignal,
  ) => Promise<TPrepared>;
  readonly #maximumUnits: number;
  readonly #entries: Entry<TPrepared>[] = [];
  #phase: 'active' | 'cancelled' = 'active';
  #response: Readonly<AudioResponseRef> | null = null;
  #reason: string | null = null;
  #renderedCount = 0;
  #releasedCount = 0;
  #cancelledCount = 0;
  #wastedPrefetchCount = 0;

  constructor(input: Readonly<{
    maxActivePreparations: 1;
    maxPreparedSuccessors: 1;
    maximumUnits: 4;
    prepare: (
      unit: Readonly<ProductTtsContinuationUnit>,
      signal: AbortSignal,
    ) => Promise<TPrepared>;
  }>) {
    if (
      input.maxActivePreparations !== 1
      || input.maxPreparedSuccessors !== 1
      || input.maximumUnits !== 4
      || typeof input.prepare !== 'function'
    ) {
      throw new ProductTtsContinuationViolation(
        'INVALID_TTS_CONTINUATION_POLICY',
        'TTS continuation policy must use the closed 1/1/4 bounds',
      );
    }
    this.#prepare = input.prepare;
    this.#maximumUnits = input.maximumUnits;
  }

  enqueue(unit: Readonly<ProductTtsContinuationUnit>): void {
    if (this.#phase !== 'active') {
      throw new ProductTtsContinuationViolation(
        'TTS_CONTINUATION_CANCELLED',
        'cancelled TTS continuation cannot accept units',
      );
    }
    if (this.#entries.length >= this.#maximumUnits) {
      throw new ProductTtsContinuationViolation(
        'TTS_CONTINUATION_CAPACITY_EXCEEDED',
        'TTS continuation exceeds four authoritative units',
      );
    }
    if (
      !unit
      || typeof unit.unitId !== 'string'
      || unit.unitId.length === 0
      || !Number.isSafeInteger(unit.seq)
      || !Number.isSafeInteger(unit.sourceStartUtf8)
      || !Number.isSafeInteger(unit.sourceEndUtf8)
      || unit.sourceStartUtf8 < 0
      || unit.sourceEndUtf8 <= unit.sourceStartUtf8
      || typeof unit.text !== 'string'
      || unit.text.length === 0
    ) {
      throw new ProductTtsContinuationViolation(
        'INVALID_TTS_CONTINUATION_UNIT',
        'TTS continuation unit is malformed',
      );
    }
    const previous = this.#entries.length === 0
      ? null
      : this.#entries[this.#entries.length - 1].unit;
    if (previous === null) {
      if (unit.seq !== 1) {
        throw new ProductTtsContinuationViolation(
          'TTS_CONTINUATION_SEQUENCE_GAP',
          'first TTS continuation unit must have sequence one',
        );
      }
      this.#response = Object.freeze({ ...unit.response });
    } else if (
      !sameResponse(previous.response, unit.response)
      || unit.seq !== previous.seq + 1
      || unit.sourceStartUtf8 !== previous.sourceEndUtf8
    ) {
      throw new ProductTtsContinuationViolation(
        'TTS_CONTINUATION_ORDER_MISMATCH',
        'TTS continuation response, sequence and spans must be contiguous',
      );
    }
    if (this.#response === null || !sameResponse(this.#response, unit.response)) {
      throw new ProductTtsContinuationViolation(
        'TTS_CONTINUATION_RESPONSE_MISMATCH',
        'TTS continuation cannot adopt a foreign response',
      );
    }
    if (this.#entries.some(entry => entry.unit.unitId === unit.unitId)) {
      throw new ProductTtsContinuationViolation(
        'DUPLICATE_TTS_CONTINUATION_UNIT',
        'TTS continuation unit id must be unique',
      );
    }
    this.#entries.push({ unit, state: 'queued', controller: null, prepared: null });
    this.#pump();
  }

  takeReleasable(): Readonly<{
    unit: ProductTtsContinuationUnit;
    prepared: TPrepared;
  }> | null {
    if (this.#phase !== 'active') return null;
    const current = this.#entries.find(entry => entry.state !== 'rendered');
    if (current?.state !== 'prepared' || current.prepared === null) return null;
    current.state = 'released';
    this.#releasedCount += 1;
    this.#pump();
    return Object.freeze({ unit: current.unit, prepared: current.prepared });
  }

  markRendered(unitId: string): void {
    if (this.#phase !== 'active') return;
    const current = this.#entries.find(entry => entry.state !== 'rendered');
    if (current?.state !== 'released' || current.unit.unitId !== unitId) {
      throw new ProductTtsContinuationViolation(
        'TTS_CONTINUATION_RENDER_MISMATCH',
        'TTS continuation render must match the released frontier',
      );
    }
    current.state = 'rendered';
    current.controller = null;
    current.prepared = null;
    this.#renderedCount += 1;
    this.#pump();
  }

  cancel(reason: string): void {
    if (this.#phase === 'cancelled') return;
    this.#phase = 'cancelled';
    this.#reason = reason || 'TTS_CONTINUATION_CANCELLED';
    for (const entry of this.#entries) {
      if (entry.state === 'rendered') continue;
      if (entry.state === 'prepared') this.#wastedPrefetchCount += 1;
      entry.controller?.abort(this.#reason);
      entry.controller = null;
      entry.prepared = null;
      entry.state = 'cancelled';
      this.#cancelledCount += 1;
    }
  }

  snapshot(): Readonly<ProductTtsContinuationSnapshot> {
    return Object.freeze({
      phase: this.#phase,
      queued_count: this.#entries.length,
      active_count: this.#entries.filter(entry => entry.state === 'preparing').length,
      prepared_count: this.#entries.filter(entry => entry.state === 'prepared').length,
      released_count: this.#releasedCount,
      rendered_count: this.#renderedCount,
      cancelled_count: this.#cancelledCount,
      wasted_prefetch_count: this.#wastedPrefetchCount,
      retry_count: 0,
      reason: this.#reason,
    });
  }

  #pump(): void {
    if (this.#phase !== 'active') return;
    const frontier = this.#entries.findIndex(entry => entry.state !== 'rendered');
    if (frontier < 0) return;
    const preparationLimit = Math.min(
      this.#entries.length,
      frontier + (this.#entries[frontier].state === 'released' ? 2 : 1),
    );
    for (let index = frontier; index < preparationLimit; index += 1) {
      const entry = this.#entries[index];
      if (entry.state !== 'queued') continue;
      const active = this.#entries.filter(item => item.state === 'preparing').length;
      if (active >= 1) break;
      this.#startPreparation(entry);
    }
  }

  #startPreparation(entry: Entry<TPrepared>): void {
    const controller = new AbortController();
    entry.controller = controller;
    entry.state = 'preparing';
    let preparation: Promise<TPrepared>;
    try {
      preparation = this.#prepare(entry.unit, controller.signal);
    } catch {
      this.cancel('TTS_PREPARATION_FAILED');
      return;
    }
    void Promise.resolve(preparation).then(
      prepared => {
        if (this.#phase !== 'active' || entry.state !== 'preparing') return;
        entry.prepared = prepared;
        entry.state = 'prepared';
        this.#pump();
      },
      () => {
        if (this.#phase === 'active' && entry.state === 'preparing') {
          this.cancel('TTS_PREPARATION_FAILED');
        }
      },
    );
  }
}
