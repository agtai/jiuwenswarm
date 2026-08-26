export interface ReplicaScope {
  readonly subject_id: string;
  readonly project_id: string | null;
  readonly session_id: string | null;
  readonly assurance: 'request_asserted' | 'authenticated';
}

export interface CanonicalConversationEvent {
  readonly seq: number;
  readonly event_type: string;
  readonly scope: Readonly<ReplicaScope>;
  readonly interaction_id: string;
  readonly turn_id: string | null;
  readonly response_id: string | null;
  readonly response_generation: number | null;
  readonly state: string | null;
  readonly cancel_state: string | null;
  readonly outcome: string | null;
}

export interface ReplicaInteraction {
  readonly interaction_id: string;
  readonly state: 'open' | 'closing' | 'closed';
}

export interface ReplicaTurn {
  readonly turn_id: string;
  readonly interaction_id: string;
  readonly state: 'capturing' | 'committed' | 'cancelled';
}

export interface ReplicaResponse {
  readonly interaction_id: string;
  readonly turn_id: string;
  readonly response_id: string;
  readonly response_generation: number;
  readonly state: 'accepted' | 'generating' | 'speaking' | 'terminal';
  readonly fenced: boolean;
  readonly cancel_state: 'none' | 'requested' | 'acknowledged' | 'result_unknown';
  readonly outcome: string | null;
}

export interface ReplicaSnapshot {
  readonly scope: Readonly<ReplicaScope>;
  readonly interactions: readonly Readonly<ReplicaInteraction>[];
  readonly turns: readonly Readonly<ReplicaTurn>[];
  readonly responses: readonly Readonly<ReplicaResponse>[];
  readonly last_seq: number;
  readonly rebuild_required: boolean;
  readonly replay: Readonly<ReplicaReplayCheckpoint>;
}

export interface ReplicaGenerationHighWater {
  readonly interaction_id: string;
  readonly response_generation: number;
}

export interface ReplicaActiveResponse {
  readonly interaction_id: string;
  readonly response_id: string;
  readonly response_generation: number;
}

export interface ReplicaReplayCheckpoint {
  readonly exact_response_ids: readonly string[];
  readonly closed_interaction_fence: string;
  readonly retired_turn_fence: string;
  readonly retired_response_fence: string;
  readonly generation_high_water: readonly Readonly<ReplicaGenerationHighWater>[];
  readonly active_responses: readonly Readonly<ReplicaActiveResponse>[];
  readonly retirable_turn_ids: readonly string[];
}

export interface ReplicaEffect {
  readonly effect_type: 'ui.render' | 'history.append' | 'audio.enqueue';
  readonly interaction_id: string;
  readonly response_id: string;
  readonly response_generation: number;
}

export class ConversationReplicaViolation extends Error {
  constructor(
    readonly reason: string,
    message: string
  ) {
    super(message);
    this.name = 'ConversationReplicaViolation';
  }
}

function requiredText(value: string, field: string): string {
  if (typeof value !== 'string' || value.trim().length === 0) {
    throw new ConversationReplicaViolation('INVALID_REQUIRED_TEXT', `${field} must be non-empty`);
  }
  return value;
}

function scopeKey(scope: Readonly<ReplicaScope>): string {
  return JSON.stringify([scope.subject_id, scope.project_id, scope.session_id, scope.assurance]);
}

function responseKey(interactionId: string, responseId: string, generation: number): string {
  return `${interactionId}\u0000${responseId}\u0000${generation}`;
}

function allowed(current: string, next: string, values: Readonly<Record<string, readonly string[]>>): boolean {
  return (values[current] ?? []).includes(next);
}

const INTERACTION_TRANSITIONS = Object.freeze({ open: Object.freeze(['closing', 'closed']), closing: Object.freeze(['closed']) });
const TURN_TRANSITIONS = Object.freeze({ capturing: Object.freeze(['committed', 'cancelled']) });
const RESPONSE_TRANSITIONS = Object.freeze({
  accepted: Object.freeze(['generating', 'terminal']),
  generating: Object.freeze(['speaking', 'terminal']),
  speaking: Object.freeze(['terminal']),
});

const EXACT_REPLAY_CAPACITY = 128;
const REPLAY_FENCE_BYTES = 8192;
const REPLAY_FENCE_HEX_LENGTH = REPLAY_FENCE_BYTES * 2;

class ConservativeIdentityFence {
  readonly #bits: Uint8Array;

  constructor(bits: Uint8Array = new Uint8Array(REPLAY_FENCE_BYTES)) {
    this.#bits = bits.slice();
  }

  #indices(value: string): readonly number[] {
    return [0x811c9dc5, 0x9e3779b1, 0x85ebca6b, 0xc2b2ae35].map(seed => {
      let hash = seed;
      for (let index = 0; index < value.length; index += 1) {
        hash = Math.imul(hash ^ value.charCodeAt(index), 0x01000193);
      }
      return (hash >>> 0) % (this.#bits.length * 8);
    });
  }

  add(value: string): void {
    for (const index of this.#indices(value)) this.#bits[index >> 3] |= 1 << (index & 7);
  }

  has(value: string): boolean {
    return this.#indices(value).every(index => (this.#bits[index >> 3] & (1 << (index & 7))) !== 0);
  }

  toHex(): string {
    return Array.from(this.#bits, byte => byte.toString(16).padStart(2, '0')).join('');
  }

  static fromHex(value: string): ConservativeIdentityFence {
    if (typeof value !== 'string' || value.length !== REPLAY_FENCE_HEX_LENGTH || !/^[0-9a-f]+$/.test(value)) {
      throw new Error('replay fence is invalid');
    }
    const bits = new Uint8Array(REPLAY_FENCE_BYTES);
    for (let index = 0; index < bits.length; index += 1) bits[index] = Number.parseInt(value.slice(index * 2, index * 2 + 2), 16);
    return new ConservativeIdentityFence(bits);
  }
}

function invalidAuthoritativeSnapshot(message: string): never {
  throw new ConversationReplicaViolation('INVALID_AUTHORITATIVE_SNAPSHOT', message);
}

function safeGeneration(value: number, field: string): number {
  if (!Number.isSafeInteger(value) || value < 0) invalidAuthoritativeSnapshot(`${field} must be a non-negative safe integer`);
  return value;
}

export class ConversationRuntimeReplica {
  readonly #scope: Readonly<ReplicaScope>;
  readonly #enabled: boolean;
  #interactions = new Map<string, ReplicaInteraction>();
  #turns = new Map<string, ReplicaTurn>();
  #responses = new Map<string, ReplicaResponse>();
  #activeResponse = new Map<string, string>();
  #seenResponseIds = new Set<string>();
  #lastGeneration = new Map<string, number>();
  #retirableTurnIds = new Set<string>();
  #closedInteractions = new ConservativeIdentityFence();
  #retiredTurnIds = new ConservativeIdentityFence();
  #retiredResponseIds = new ConservativeIdentityFence();
  #rebuildRequired = false;
  #lastSeq = 0;

  constructor(scope: Readonly<ReplicaScope>, options: Readonly<{ enabled?: boolean }> = {}) {
    requiredText(scope.subject_id, 'scope.subject_id');
    this.#scope = Object.freeze({ ...scope });
    this.#enabled = options.enabled ?? true;
    if (typeof this.#enabled !== 'boolean') {
      throw new ConversationReplicaViolation('INVALID_BOOLEAN', 'enabled must be boolean');
    }
  }

  apply(event: Readonly<CanonicalConversationEvent>): boolean {
    if (!this.#enabled) return false;
    if (scopeKey(event.scope) !== scopeKey(this.#scope)) {
      throw new ConversationReplicaViolation('EVENT_SCOPE_MISMATCH', 'event belongs to another scope');
    }
    if (this.#rebuildRequired) {
      throw new ConversationReplicaViolation('REPLICA_REBUILD_REQUIRED', 'authoritative replica rebuild is required before applying more events');
    }
    if (!Number.isSafeInteger(event.seq) || event.seq !== this.#lastSeq + 1) {
      throw new ConversationReplicaViolation('NON_CONTIGUOUS_EVENT_SEQUENCE', `expected event sequence ${this.#lastSeq + 1}`);
    }
    requiredText(event.interaction_id, 'interaction_id');
    this.#applyLifecycle(event);
    this.#lastSeq = event.seq;
    return true;
  }

  selectOutputEffects(interactionId: string, responseId: string, responseGeneration: number): readonly Readonly<ReplicaEffect>[] {
    const active = this.#activeResponse.get(interactionId);
    const key = responseKey(interactionId, responseId, responseGeneration);
    const response = this.#responses.get(key);
    if (active !== key || response === undefined || response.fenced || response.state === 'terminal') return Object.freeze([]);
    return Object.freeze(
      (['ui.render', 'history.append', 'audio.enqueue'] as const).map(effectType =>
        Object.freeze({ effect_type: effectType, interaction_id: interactionId, response_id: responseId, response_generation: responseGeneration })
      )
    );
  }

  snapshot(): Readonly<ReplicaSnapshot> {
    return Object.freeze({
      scope: this.#scope,
      interactions: Object.freeze([...this.#interactions.values()].map(item => Object.freeze({ ...item }))),
      turns: Object.freeze([...this.#turns.values()].map(item => Object.freeze({ ...item }))),
      responses: Object.freeze([...this.#responses.values()].map(item => Object.freeze({ ...item }))),
      last_seq: this.#lastSeq,
      rebuild_required: this.#rebuildRequired,
      replay: Object.freeze({
        exact_response_ids: Object.freeze([...this.#seenResponseIds]),
        closed_interaction_fence: this.#closedInteractions.toHex(),
        retired_turn_fence: this.#retiredTurnIds.toHex(),
        retired_response_fence: this.#retiredResponseIds.toHex(),
        generation_high_water: Object.freeze(
          [...this.#lastGeneration].map(([interactionId, generation]) =>
            Object.freeze({ interaction_id: interactionId, response_generation: generation })
          )
        ),
        active_responses: Object.freeze(
          [...this.#activeResponse].map(([interactionId, key]) => {
            const response = this.#responses.get(key)!;
            return Object.freeze({
              interaction_id: interactionId,
              response_id: response.response_id,
              response_generation: response.response_generation,
            });
          })
        ),
        retirable_turn_ids: Object.freeze([...this.#retirableTurnIds]),
      }),
    });
  }

  rebuildFromAuthoritativeSnapshot(snapshot: Readonly<ReplicaSnapshot>): boolean {
    if (!this.#enabled) return false;
    if (snapshot === null || typeof snapshot !== 'object' || snapshot.scope === null || typeof snapshot.scope !== 'object') {
      invalidAuthoritativeSnapshot('authoritative snapshot is invalid');
    }
    if (scopeKey(snapshot.scope) !== scopeKey(this.#scope)) {
      throw new ConversationReplicaViolation('EVENT_SCOPE_MISMATCH', 'authoritative snapshot belongs to another scope');
    }
    try {
      requiredText(snapshot.scope.subject_id, 'snapshot.scope.subject_id');
      if (snapshot.rebuild_required !== false) invalidAuthoritativeSnapshot('authoritative snapshot cannot require another rebuild');
      const lastSeq = safeGeneration(snapshot.last_seq, 'snapshot.last_seq');
      if (lastSeq < this.#lastSeq) invalidAuthoritativeSnapshot('authoritative snapshot cannot roll back the event sequence');
      if (!Array.isArray(snapshot.interactions) || !Array.isArray(snapshot.turns) || !Array.isArray(snapshot.responses)) {
        invalidAuthoritativeSnapshot('authoritative lifecycle collections must be arrays');
      }

      const replay = snapshot.replay;
      if (
        replay === null ||
        typeof replay !== 'object' ||
        !Array.isArray(replay.exact_response_ids) ||
        !Array.isArray(replay.generation_high_water) ||
        !Array.isArray(replay.active_responses) ||
        !Array.isArray(replay.retirable_turn_ids)
      ) {
        invalidAuthoritativeSnapshot('authoritative replay checkpoint is invalid');
      }
      if (replay.exact_response_ids.length > EXACT_REPLAY_CAPACITY || replay.retirable_turn_ids.length > EXACT_REPLAY_CAPACITY) {
        invalidAuthoritativeSnapshot('authoritative exact replay owner exceeds capacity');
      }
      const closedInteractions = ConservativeIdentityFence.fromHex(replay.closed_interaction_fence);
      const retiredTurnIds = ConservativeIdentityFence.fromHex(replay.retired_turn_fence);
      const retiredResponseIds = ConservativeIdentityFence.fromHex(replay.retired_response_fence);

      const seenResponseIds = new Set<string>();
      for (const responseId of replay.exact_response_ids) {
        requiredText(responseId, 'snapshot.replay.exact_response_ids');
        if (seenResponseIds.has(responseId)) invalidAuthoritativeSnapshot('authoritative exact response IDs contain a duplicate');
        seenResponseIds.add(responseId);
      }

      const interactions = new Map<string, ReplicaInteraction>();
      for (const item of snapshot.interactions) {
        const interactionId = requiredText(item.interaction_id, 'snapshot.interaction_id');
        if (item.state !== 'open' && item.state !== 'closing') invalidAuthoritativeSnapshot('authoritative snapshot retained a terminal interaction');
        if (interactions.has(interactionId)) invalidAuthoritativeSnapshot('authoritative interactions contain a duplicate');
        interactions.set(interactionId, Object.freeze({ interaction_id: interactionId, state: item.state }));
      }

      const turns = new Map<string, ReplicaTurn>();
      for (const item of snapshot.turns) {
        const turnId = requiredText(item.turn_id, 'snapshot.turn_id');
        const interactionId = requiredText(item.interaction_id, 'snapshot.turn.interaction_id');
        if (item.state !== 'capturing' && item.state !== 'committed') invalidAuthoritativeSnapshot('authoritative snapshot retained a terminal turn');
        if (!interactions.has(interactionId) || turns.has(turnId)) invalidAuthoritativeSnapshot('authoritative turn ownership is invalid');
        turns.set(turnId, Object.freeze({ turn_id: turnId, interaction_id: interactionId, state: item.state }));
      }

      const responses = new Map<string, ReplicaResponse>();
      const liveResponseIds = new Set<string>();
      const responseGenerations = new Map<string, Set<number>>();
      for (const item of snapshot.responses) {
        const interactionId = requiredText(item.interaction_id, 'snapshot.response.interaction_id');
        const turnId = requiredText(item.turn_id, 'snapshot.response.turn_id');
        const responseId = requiredText(item.response_id, 'snapshot.response_id');
        const generation = safeGeneration(item.response_generation, 'snapshot.response_generation');
        const turn = turns.get(turnId);
        if (turn === undefined || turn.interaction_id !== interactionId || turn.state !== 'committed') {
          invalidAuthoritativeSnapshot('authoritative response turn binding is invalid');
        }
        if (item.state === 'terminal' || !(['accepted', 'generating', 'speaking'] as const).includes(item.state)) {
          invalidAuthoritativeSnapshot('authoritative snapshot retained a terminal or invalid response');
        }
        if (!(['none', 'requested', 'acknowledged', 'result_unknown'] as const).includes(item.cancel_state)) {
          invalidAuthoritativeSnapshot('authoritative response cancel state is invalid');
        }
        const interaction = interactions.get(interactionId)!;
        if (
          typeof item.fenced !== 'boolean' ||
          item.outcome !== null ||
          liveResponseIds.has(responseId) ||
          (item.cancel_state !== 'none' && !item.fenced) ||
          (interaction.state === 'closing' && !item.fenced)
        ) {
          invalidAuthoritativeSnapshot('authoritative response state is invalid');
        }
        const generations = responseGenerations.get(interactionId) ?? new Set<number>();
        if (generations.has(generation)) invalidAuthoritativeSnapshot('authoritative response generation is duplicated');
        generations.add(generation);
        responseGenerations.set(interactionId, generations);
        const key = responseKey(interactionId, responseId, generation);
        if (responses.has(key)) invalidAuthoritativeSnapshot('authoritative responses contain a duplicate');
        if (!seenResponseIds.has(responseId) && !retiredResponseIds.has(responseId)) {
          invalidAuthoritativeSnapshot('authoritative response is absent from replay ownership');
        }
        liveResponseIds.add(responseId);
        responses.set(key, Object.freeze({ ...item, interaction_id: interactionId, turn_id: turnId, response_id: responseId, response_generation: generation }));
      }

      const lastGeneration = new Map<string, number>();
      for (const item of replay.generation_high_water) {
        const interactionId = requiredText(item.interaction_id, 'snapshot.replay.generation_high_water.interaction_id');
        const generation = safeGeneration(item.response_generation, 'snapshot.replay.generation_high_water.response_generation');
        if (!interactions.has(interactionId) || lastGeneration.has(interactionId)) {
          invalidAuthoritativeSnapshot('authoritative generation high-water ownership is invalid');
        }
        lastGeneration.set(interactionId, generation);
      }
      for (const response of responses.values()) {
        const highWater = lastGeneration.get(response.interaction_id);
        if (highWater === undefined || response.response_generation > highWater) {
          invalidAuthoritativeSnapshot('authoritative response exceeds its generation high-water');
        }
      }

      const activeResponse = new Map<string, string>();
      for (const item of replay.active_responses) {
        const interactionId = requiredText(item.interaction_id, 'snapshot.replay.active_response.interaction_id');
        const responseId = requiredText(item.response_id, 'snapshot.replay.active_response.response_id');
        const generation = safeGeneration(item.response_generation, 'snapshot.replay.active_response.response_generation');
        const key = responseKey(interactionId, responseId, generation);
        if (
          activeResponse.has(interactionId) ||
          !responses.has(key) ||
          lastGeneration.get(interactionId) !== generation
        ) {
          invalidAuthoritativeSnapshot('authoritative active response ownership is invalid');
        }
        activeResponse.set(interactionId, key);
      }
      for (const [key, response] of responses) {
        if (!response.fenced && activeResponse.get(response.interaction_id) !== key) {
          invalidAuthoritativeSnapshot('authoritative unfenced response is not active');
        }
      }

      const retirableTurnIds = new Set<string>();
      const turnIdsWithResponses = new Set([...responses.values()].map(response => response.turn_id));
      for (const turnIdValue of replay.retirable_turn_ids) {
        const turnId = requiredText(turnIdValue, 'snapshot.replay.retirable_turn_id');
        const turn = turns.get(turnId);
        if (
          turn === undefined ||
          turn.state !== 'committed' ||
          retirableTurnIds.has(turnId) ||
          turnIdsWithResponses.has(turnId)
        ) {
          invalidAuthoritativeSnapshot('authoritative retirable turn ownership is invalid');
        }
        retirableTurnIds.add(turnId);
      }
      for (const turn of turns.values()) {
        if (
          turn.state === 'committed' &&
          !turnIdsWithResponses.has(turn.turn_id) &&
          !retirableTurnIds.has(turn.turn_id)
        ) {
          invalidAuthoritativeSnapshot('authoritative committed turn escaped bounded reusable ownership');
        }
      }

      this.#interactions = interactions;
      this.#turns = turns;
      this.#responses = responses;
      this.#activeResponse = activeResponse;
      this.#seenResponseIds = seenResponseIds;
      this.#lastGeneration = lastGeneration;
      this.#retirableTurnIds = retirableTurnIds;
      this.#closedInteractions = closedInteractions;
      this.#retiredTurnIds = retiredTurnIds;
      this.#retiredResponseIds = retiredResponseIds;
      this.#lastSeq = lastSeq;
      this.#rebuildRequired = false;
      return true;
    } catch (error) {
      if (error instanceof ConversationReplicaViolation && error.reason === 'INVALID_AUTHORITATIVE_SNAPSHOT') throw error;
      invalidAuthoritativeSnapshot(error instanceof Error ? error.message : 'authoritative snapshot is invalid');
    }
  }

  #applyLifecycle(event: Readonly<CanonicalConversationEvent>): void {
    if (event.event_type === 'interaction.opened') {
      if (event.state !== 'open' || this.#interactions.has(event.interaction_id)) this.#invalid(event.event_type);
      if (this.#closedInteractions.has(event.interaction_id)) this.#requireRebuild(event.event_type);
      this.#interactions.set(event.interaction_id, Object.freeze({ interaction_id: event.interaction_id, state: 'open' }));
      return;
    }
    const interaction = this.#interactions.get(event.interaction_id);
    if (interaction === undefined) this.#invalid(event.event_type);
    if (event.event_type === 'interaction.closing' || event.event_type === 'interaction.closed') {
      const next = event.event_type === 'interaction.closing' ? 'closing' : 'closed';
      if (!allowed(interaction!.state, next, INTERACTION_TRANSITIONS) || event.state !== next) this.#invalid(event.event_type);
      if (next === 'closed') {
        this.#compactInteraction(event.interaction_id);
        return;
      }
      this.#interactions.set(event.interaction_id, Object.freeze({ ...interaction!, state: next }));
      const activeKey = this.#activeResponse.get(event.interaction_id);
      if (activeKey !== undefined) {
        const active = this.#responses.get(activeKey)!;
        this.#responses.set(activeKey, Object.freeze({ ...active, fenced: true }));
      }
      return;
    }
    if (event.event_type === 'turn.started') {
      const turnId = requiredText(event.turn_id ?? '', 'turn_id');
      if (interaction!.state !== 'open' || event.state !== 'capturing' || this.#turns.has(turnId)) this.#invalid(event.event_type);
      if (this.#retiredTurnIds.has(turnId)) this.#requireRebuild(event.event_type);
      this.#turns.set(turnId, Object.freeze({ turn_id: turnId, interaction_id: event.interaction_id, state: 'capturing' }));
      return;
    }
    if (event.event_type === 'turn.committed' || event.event_type === 'turn.cancelled') {
      const turn = this.#turns.get(event.turn_id ?? '');
      const next = event.event_type === 'turn.committed' ? 'committed' : 'cancelled';
      if (turn === undefined || turn.interaction_id !== event.interaction_id || !allowed(turn.state, next, TURN_TRANSITIONS) || event.state !== next) {
        this.#invalid(event.event_type);
      }
      if (next === 'cancelled') {
        this.#retiredTurnIds.add(turn!.turn_id);
        this.#retirableTurnIds.delete(turn!.turn_id);
        this.#turns.delete(turn!.turn_id);
      } else {
        this.#turns.set(turn!.turn_id, Object.freeze({ ...turn!, state: next }));
        this.#markTurnRetirable(turn!.turn_id);
      }
      return;
    }
    if (event.event_type === 'response.accepted') {
      const turnId = requiredText(event.turn_id ?? '', 'turn_id');
      const turn = this.#turns.get(turnId);
      const responseId = requiredText(event.response_id ?? '', 'response_id');
      if (turn === undefined && this.#retiredTurnIds.has(turnId)) this.#requireRebuild(event.event_type);
      if (
        turn === undefined ||
        turn.state !== 'committed' ||
        turn.interaction_id !== event.interaction_id ||
        interaction!.state !== 'open' ||
        event.state !== 'accepted' ||
        event.response_generation === null ||
        !Number.isSafeInteger(event.response_generation) ||
        event.response_generation < 0
      ) {
        this.#invalid(event.event_type);
      }
      const key = responseKey(event.interaction_id, responseId, event.response_generation!);
      const lastGeneration = this.#lastGeneration.get(event.interaction_id) ?? -1;
      if (this.#seenResponseIds.has(responseId) || event.response_generation! <= lastGeneration) {
        this.#invalid(event.event_type);
      }
      if (this.#retiredResponseIds.has(responseId)) this.#requireRebuild(event.event_type);
      const priorKey = this.#activeResponse.get(event.interaction_id);
      if (priorKey !== undefined) {
        const prior = this.#responses.get(priorKey)!;
        this.#responses.set(priorKey, Object.freeze({ ...prior, fenced: true }));
      }
      this.#responses.set(
        key,
        Object.freeze({
          interaction_id: event.interaction_id,
          turn_id: turn!.turn_id,
          response_id: responseId,
          response_generation: event.response_generation!,
          state: 'accepted',
          fenced: false,
          cancel_state: 'none',
          outcome: null,
        })
      );
      this.#activeResponse.set(event.interaction_id, key);
      this.#retirableTurnIds.delete(turn!.turn_id);
      this.#retainResponseId(responseId);
      this.#lastGeneration.set(event.interaction_id, event.response_generation!);
      return;
    }
    this.#applyResponseEvent(event);
  }

  #applyResponseEvent(event: Readonly<CanonicalConversationEvent>): void {
    if (event.response_id === null || event.response_generation === null) this.#invalid(event.event_type);
    const key = responseKey(event.interaction_id, event.response_id!, event.response_generation!);
    const response = this.#responses.get(key);
    if (response === undefined || response.turn_id !== event.turn_id) this.#invalid(event.event_type);
    if (event.event_type === 'response.generating' || event.event_type === 'response.speaking' || event.event_type === 'response.terminal') {
      const next = event.event_type.split('.')[1] as 'generating' | 'speaking' | 'terminal';
      if (!allowed(response!.state, next, RESPONSE_TRANSITIONS) || event.state !== next) this.#invalid(event.event_type);
      if (next === 'terminal' && event.outcome === null) this.#invalid(event.event_type);
      if (next !== 'terminal' && event.outcome !== null) this.#invalid(event.event_type);
      if (next === 'terminal') {
        this.#responses.delete(key);
        if (this.#activeResponse.get(event.interaction_id) === key) this.#activeResponse.delete(event.interaction_id);
        this.#markTurnRetirable(response!.turn_id);
      } else {
        this.#responses.set(key, Object.freeze({ ...response!, state: next, fenced: response!.fenced, outcome: null }));
      }
      return;
    }
    const cancelByType: Readonly<Record<string, ReplicaResponse['cancel_state']>> = Object.freeze({
      'response.cancel_requested': 'requested',
      'response.cancel_acknowledged': 'acknowledged',
      'response.cancel_result_unknown': 'result_unknown',
    });
    const nextCancel = cancelByType[event.event_type];
    if (nextCancel === undefined || event.cancel_state !== nextCancel || event.state !== response!.state) this.#invalid(event.event_type);
    if (nextCancel === 'requested' && response!.cancel_state !== 'none') this.#invalid(event.event_type);
    if (nextCancel === 'acknowledged' && response!.cancel_state !== 'requested' && response!.cancel_state !== 'result_unknown') this.#invalid(event.event_type);
    if (nextCancel === 'result_unknown' && response!.cancel_state !== 'requested') this.#invalid(event.event_type);
    this.#responses.set(key, Object.freeze({ ...response!, cancel_state: nextCancel, fenced: true }));
  }

  #compactInteraction(interactionId: string): void {
    this.#closedInteractions.add(interactionId);
    for (const [turnId, turn] of this.#turns) {
      if (turn.interaction_id !== interactionId) continue;
      this.#retiredTurnIds.add(turnId);
      this.#retirableTurnIds.delete(turnId);
      this.#turns.delete(turnId);
    }
    for (const [key, response] of this.#responses) {
      if (response.interaction_id === interactionId) this.#responses.delete(key);
    }
    this.#activeResponse.delete(interactionId);
    this.#lastGeneration.delete(interactionId);
    this.#interactions.delete(interactionId);
  }

  #retainResponseId(responseId: string): void {
    if (this.#seenResponseIds.size >= EXACT_REPLAY_CAPACITY) {
      const oldest = this.#seenResponseIds.values().next().value;
      if (oldest !== undefined) {
        this.#retiredResponseIds.add(oldest);
        this.#seenResponseIds.delete(oldest);
      }
    }
    this.#seenResponseIds.add(responseId);
  }

  #markTurnRetirable(turnId: string): void {
    const turn = this.#turns.get(turnId);
    if (turn === undefined || turn.state !== 'committed') return;
    if ([...this.#responses.values()].some(response => response.turn_id === turnId)) return;
    this.#retirableTurnIds.delete(turnId);
    this.#retirableTurnIds.add(turnId);
    while (this.#retirableTurnIds.size > EXACT_REPLAY_CAPACITY) {
      const oldest = this.#retirableTurnIds.values().next().value;
      if (oldest === undefined) break;
      this.#retiredTurnIds.add(oldest);
      this.#retirableTurnIds.delete(oldest);
      this.#turns.delete(oldest);
    }
  }

  #requireRebuild(eventType: string): never {
    this.#rebuildRequired = true;
    throw new ConversationReplicaViolation('REPLICA_REBUILD_REQUIRED', `authoritative rebuild required for canonical event ${eventType}`);
  }

  #invalid(eventType: string): never {
    throw new ConversationReplicaViolation('INVALID_CANONICAL_EVENT', `invalid canonical event ${eventType}`);
  }
}
