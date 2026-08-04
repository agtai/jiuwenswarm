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
  readonly interactions: readonly Readonly<ReplicaInteraction>[];
  readonly turns: readonly Readonly<ReplicaTurn>[];
  readonly responses: readonly Readonly<ReplicaResponse>[];
  readonly last_seq: number;
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

export class ConversationRuntimeReplica {
  readonly #scope: Readonly<ReplicaScope>;
  readonly #enabled: boolean;
  readonly #interactions = new Map<string, ReplicaInteraction>();
  readonly #turns = new Map<string, ReplicaTurn>();
  readonly #responses = new Map<string, ReplicaResponse>();
  readonly #activeResponse = new Map<string, string>();
  readonly #seenResponseIds = new Set<string>();
  readonly #lastGeneration = new Map<string, number>();
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
      interactions: Object.freeze([...this.#interactions.values()].map(item => Object.freeze({ ...item }))),
      turns: Object.freeze([...this.#turns.values()].map(item => Object.freeze({ ...item }))),
      responses: Object.freeze([...this.#responses.values()].map(item => Object.freeze({ ...item }))),
      last_seq: this.#lastSeq,
    });
  }

  #applyLifecycle(event: Readonly<CanonicalConversationEvent>): void {
    if (event.event_type === 'interaction.opened') {
      if (event.state !== 'open' || this.#interactions.has(event.interaction_id)) this.#invalid(event.event_type);
      this.#interactions.set(event.interaction_id, Object.freeze({ interaction_id: event.interaction_id, state: 'open' }));
      return;
    }
    const interaction = this.#interactions.get(event.interaction_id);
    if (interaction === undefined) this.#invalid(event.event_type);
    if (event.event_type === 'interaction.closing' || event.event_type === 'interaction.closed') {
      const next = event.event_type === 'interaction.closing' ? 'closing' : 'closed';
      if (!allowed(interaction!.state, next, INTERACTION_TRANSITIONS) || event.state !== next) this.#invalid(event.event_type);
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
      this.#turns.set(turnId, Object.freeze({ turn_id: turnId, interaction_id: event.interaction_id, state: 'capturing' }));
      return;
    }
    if (event.event_type === 'turn.committed' || event.event_type === 'turn.cancelled') {
      const turn = this.#turns.get(event.turn_id ?? '');
      const next = event.event_type === 'turn.committed' ? 'committed' : 'cancelled';
      if (turn === undefined || turn.interaction_id !== event.interaction_id || !allowed(turn.state, next, TURN_TRANSITIONS) || event.state !== next) {
        this.#invalid(event.event_type);
      }
      this.#turns.set(turn!.turn_id, Object.freeze({ ...turn!, state: next }));
      return;
    }
    if (event.event_type === 'response.accepted') {
      const turn = this.#turns.get(event.turn_id ?? '');
      const responseId = requiredText(event.response_id ?? '', 'response_id');
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
      this.#seenResponseIds.add(responseId);
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
      this.#responses.set(key, Object.freeze({ ...response!, state: next, fenced: next === 'terminal' || response!.fenced, outcome: event.outcome }));
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
    if (nextCancel !== 'requested' && response!.cancel_state !== 'requested') this.#invalid(event.event_type);
    this.#responses.set(key, Object.freeze({ ...response!, cancel_state: nextCancel, fenced: true }));
  }

  #invalid(eventType: string): never {
    throw new ConversationReplicaViolation('INVALID_CANONICAL_EVENT', `invalid canonical event ${eventType}`);
  }
}
