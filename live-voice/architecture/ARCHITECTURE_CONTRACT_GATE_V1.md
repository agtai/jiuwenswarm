# Live Voice Architecture Contract Gate v1

> Gate revision: `ACG-1`
> Target contract family: `live-voice.contract.v2`
> Decision: D-042
> Status: accepted normative design; implementation and conformance progress are reported only in STATUS and package review records
> Delivery interpretation: D-046 preserves all semantics in this document but implements them through a Day 1–2 critical kernel plus consumer-specific gates. D-055 changes the current product carrier from Windows Desktop/WebView2 to Web without changing this wire contract. Sections not consumed by an A-package do not globally block unrelated A-package work; every consumed section and the complete Alpha boundary still require the applicable conformance and Sol review before real B/C integration or Week 4 closure.
> Current terminology: under D-075, P1/P2/P3alpha are capability tracks and references here to phases or Week 4 are historical architecture/delivery labels. Current sequential stages and Alpha nodes are defined by the roadmap and reported only in STATUS; this clarification does not change the contract below.

## 1. Purpose and authority

This document is the normative architecture-review output required by [FULL_SOLUTION_2026-07-30.md](FULL_SOLUTION_2026-07-30.md) §5.2 and §8 before P1/P2/P3 `*-A` packages can implement shared types, Ports, fakes, reducers, and conformance suites. It freezes cross-plane meaning; it does not implement a Provider, conversation runtime, task core, executor, transport, or production security boundary.

The immutable full-solution snapshot remains the historical architecture and module-boundary source; D-055 supersedes only its Windows product-carrier and productization interpretation. This Gate is the newer normative source for the shared wire contract where it makes a more specific choice. D-046 risk tiers govern review depth: grouped Tier 2/3 boundaries require Sol pre/post review, while ordinary A-package mechanics use their scoped contract and evidence rather than a universal full-matrix checkpoint.

Normative terms `MUST`, `MUST NOT`, `SHOULD`, and `MAY` have their ordinary RFC-style meanings. An omitted, unknown, unsupported, stale, or untrusted fact MUST NOT be converted to success.

## 2. Version and compatibility decision

The repository already contains a strict Foundation subset named `live-voice.contract.v1`. Its `WorkProgressEvent` has only `work_ref`, a string `provenance`, `seq`, `state`, and `outcome`, and its parser rejects unknown fields. Adding the complete Gate fields under that identifier would silently redefine already serialized data.

Therefore:

- `live-voice.contract.v1` remains a supported Foundation input only. Existing behavior and tests are not rewritten in place.
- The complete target family is `live-voice.contract.v2`. A v2 producer MUST emit the full v2 envelope and payload; it cannot label v1 data as v2.
- A v1→v2 Adapter MAY emit v2 only when it can supply every required identity, scope, sequence, source-event provenance, and known/unknown fact from authoritative data. Otherwise it returns `UNSUPPORTED` or retains a clearly labeled Demo projection.
- A v2→v1 compatibility projection is lossy and MUST NOT be re-emitted as authoritative v2. Terminal outcome and source provenance MUST never be guessed during projection.
- v2 schemas are closed except for an explicit namespaced `extensions` object. Unknown required capabilities, enum values, event types, state transitions, or top-level fields fail closed. Optional evolution that changes interpretation requires a new contract major or an explicitly negotiated capability.
- Canonical command fingerprints use UTF-8 JSON with object keys sorted, no insignificant whitespace, finite numbers only, and exact string values. Integer-valued JSON numbers MUST stay within `[-9007199254740991, 9007199254740991]` so Python and TypeScript produce the same bytes; larger exact values require a separately versioned string or numeric type. Consumers do not trim, case-fold, or Unicode-normalize IDs or enum values.

## 3. Shared identities and scope

All IDs are opaque, non-empty strings, are compared exactly, and are never inferred from display text, timestamps, recency, or another ID kind. Producers MUST NOT reuse an ID within its authoritative lifetime. Prefixes are diagnostic conventions, not parsing rules.

| Identity | Authority and lifetime | Required parent / scope rule |
|---|---|---|
| `connection_id` | Realtime transport; one physical/logical connection attempt | bound to one `connection_epoch`; never a business replay identity |
| `connection_epoch` | Realtime transport; monotonic non-negative integer within a client transport instance | changes whenever old media callbacks must be fenced |
| `media_session_id` | Realtime Media | belongs to one interaction and one active connection epoch at a time |
| `track_id` | Realtime Media / Audio Port | belongs to one media session; direction and media kind are explicit |
| `interaction_id` | Conversation Runtime | owns a sequence of turns/responses; survives media reconnect according to capability |
| `turn_id` | Conversation Runtime | belongs to exactly one interaction; one immutable commit boundary |
| `response_id` | Conversation Runtime | belongs to exactly one interaction and initiating turn; never reused for a replacement generation |
| `response_generation` | Conversation Runtime | monotonic non-negative integer per interaction; the authoritative stale-output fence |
| `round_id` | Harness/Agent Runtime | one conversational work execution; Agent Bridge maps but never creates its execution facts |
| `task_id` | Task Control Core | stable task lifecycle independent of interaction/session/media lifetime |
| `attempt_id` | Task Control Core + Executor | belongs to exactly one task; identifies one actual execution attempt |
| `command_id` | Command origin + owning Core | stable across delivery retries; its canonical fingerprint is immutable |
| `request_id` | Transport/API caller | one delivery/query attempt; a retry gets a new request ID even when command ID is reused |
| `event_id` | Event producer | immutable unique event identity; duplicate ID with different bytes is a protocol violation |

`connection_epoch` and `response_generation` are numeric fencing values, not opaque string identity kinds. A connection record carries its exact `{connection_id, connection_epoch}` binding; a media-session record carries the same binding plus its interaction parent. Registration rejects an absent connection, a different scope, or a stale/different epoch. A round has no generic identity parent; its execution relationships come from authoritative Harness/Agent events rather than a fabricated turn parent.

`ScopeRef` is required on commands, queries, events, WorkProgress, and ContextRef:

```text
ScopeRef {
  subject_id: non-empty opaque string
  project_id: non-empty opaque string | null
  session_id: non-empty opaque string | null
  assurance: "request_asserted" | "authenticated"
}
```

An exact `request_asserted` match proves only D-033 single-user request consistency. It MUST NOT be described as authentication, tenant isolation, authorization, or existence hiding. Production-sensitive operations require `authenticated` plus a separate authorization decision. A consumer MUST reject a scope mismatch before returning object content or causing control, storage, Agent, Tool, Task, or TTS side effects.

## 4. Authority map

| Fact / action | Sole authority | Forbidden substitution |
|---|---|---|
| physical capture, playout, mute, playback cursor/ACK | Audio Device & I/O | media transport or UI guessing that audio was heard |
| connection/frame/ACK/backpressure | Realtime Media | transport owning turn, response, round, or task state |
| interaction, turn, response, response generation, presented ledger | Conversation Runtime | Provider callback, UI component, or Agent Bridge becoming a second lifecycle owner |
| conversational round execution facts | Harness/Agent Runtime | Agent Bridge fabricating state/progress/outcome |
| task, command, TaskEvent, canonical attempt record | Task Control Core | Voice–Task Bridge, UI, or Executor directly editing canonical lifecycle |
| actual attempt execution | Executor | Task Core claiming side effects completed without Executor evidence/reconciliation |
| natural-language task intent conversion | Voice–Task Bridge after TurnCommit | partial transcript, Provider, or generic Chat handler emitting TaskCommand |
| structured task command conversion | authorized Command Adapter | UI bypassing Core idempotency/scope checks |
| notification timing and speech arbitration | Conversation Runtime | WorkProgress producer or task monitor calling TTS directly |

## 5. API and event envelopes

### 5.1 Command, query, and result

A state-changing command uses:

```text
CommandEnvelope {
  contract_version: "live-voice.contract.v2"
  request_id: string
  command_id: string
  command_type: namespaced string
  issued_at: RFC3339 UTC timestamp
  scope: ScopeRef
  correlation_id: string
  causation_id: string | null
  origin: { kind: "structured" | "committed_turn", turn_id: string | null, commit_id: string | null }
  target_ref: { kind: identity kind, id: string }
  context_refs: ContextRef[]
  required_capabilities: string[]
  payload: closed object
  extensions: namespaced object
}
```

Only committed natural-language input may use `origin.kind=committed_turn`; both IDs are then required. Structured commands require an authorized adapter and null turn/commit IDs. The same `command_id` and canonical fingerprint replay the original result; the same ID with a different fingerprint returns `CONFLICT/IDEMPOTENCY_CONFLICT` and causes zero mutation.

Read-only `get/list/status/events` use `QueryEnvelope`, which replaces `command_id`, `command_type`, and `origin` with `query_type`. A query MUST NOT create, retry, cancel, claim, or mutate work. Transport cancellation of a query does not imply any business cancel.

Every request receives exactly one `ResultEnvelope` owned by the addressed API handler:

```text
ResultEnvelope {
  contract_version: "live-voice.contract.v2"
  request_id: string
  command_id: string | null
  ok: boolean
  result: closed object | null
  error: ContractError | null
  observed_at: RFC3339 UTC timestamp
  extensions: namespaced object
}
```

`ok=true` requires a result and forbids an error. `ok=false` requires an error and forbids a result. A payload that violates this exclusive rule is a protocol violation, not a business success.

### 5.2 EventEnvelope

```text
EventEnvelope {
  contract_version: "live-voice.contract.v2"
  event_id: string
  event_type: namespaced string
  producer: { component: string, instance_id: string, authority: string }
  stream_ref: { kind: identity kind, id: string }
  seq: non-negative integer
  occurred_at: RFC3339 UTC timestamp
  scope: ScopeRef
  correlation_id: string
  causation_id: string | null
  required_capabilities: string[]
  payload: closed object
  extensions: namespaced object
}
```

Sequence is monotonic and contiguous only within `(producer.component, producer.instance_id, stream_ref)`. There is no global ordering. Consumers MUST apply state by sequence, never wall-clock time. Exact duplicate `event_id` plus identical canonical bytes is idempotent; the same ID with different bytes, a reused sequence with different content, or a backward transition is `PROTOCOL_VIOLATION`. A gap or out-of-order future event is quarantined until replay/reconciliation closes the gap; it is not applied speculatively. A stream with conflicting content is fail-closed: later sequence values are not applied automatically. The consumer must obtain an authority-led reconciliation/rebuild or a verified replacement producer instance before resuming. When replay is not a declared capability, the consumer exposes an honest gap/error and reconciles via the owning authority.

Root events may have null `causation_id`; all derived events reference the immediately causal command/event. All events in one user-visible operation share `correlation_id`. Adapter-produced events identify the Adapter as producer and reference the authoritative source event; an Adapter does not impersonate the source authority.

## 6. Lifecycle state machines

### 6.1 Interaction, turn, and response

Conversation Runtime owns these transitions:

```text
interaction: open -> closing -> closed
             open ------------> closed

turn: capturing -> committed
      capturing -> cancelled

response: accepted -> generating -> speaking -> terminal
          accepted -> terminal
          generating -> terminal
          speaking -> terminal
```

- `committed` and `cancelled` turns are terminal and immutable. A correction is a new turn or an explicit superseding commit; it does not rewrite a committed turn.
- A turn can emit at most one `TurnCommit`. Repeated delivery of the same commit ID is idempotent; a second different commit for the same turn is a conflict.
- Response terminal outcome is required and one of `completed`, `failed`, `cancelled`, `interrupted`, or `unknown`. Non-terminal responses MUST NOT carry an outcome.
- `speaking` means at least one output unit has entered an Audio/UI presentation pipeline. It does not prove the user heard or saw it; only PresentationAck updates the presented ledger.
- Each new or replacement response gets a new `response_id` and a strictly greater `response_generation` within the interaction. Every response delta, audio unit, presentation ACK, terminal event, and cancel target carries the exact tuple.
- Once the active generation changes or becomes terminal, callbacks for any older tuple have zero projection, history, Agent, Tool, Task, audio, or notification effect.
- Closing an interaction fences new turns and responses. `closed` is irreversible, but it does not cancel an independent task.

### 6.2 Conversational round

Harness/Agent Runtime is authoritative for a round. A round is distinct from a response and from a task. Its portable progress projection uses the WorkProgress states in §8, but the Bridge MUST retain the real source event and `round_id`. `round.cancel` requests cancellation of exactly one round; acceptance of the command is not proof that execution or side effects stopped. Only a terminal round event closes it.

### 6.3 Task and attempt

Task Control Core owns canonical task transitions:

```text
accepted -> running | blocked | decision_required | terminal
running -> blocked | decision_required | terminal
blocked -> running | decision_required | terminal
decision_required -> running | blocked | terminal
terminal -> (no transitions)
```

Terminal outcome is required and uses `completed`, `failed`, `cancelled`, `interrupted`, or `unknown`; non-terminal task states forbid outcome. `unknown` is an honest terminal reconciliation result, never a synonym for success.

Executor attempt transitions are `accepted -> running -> terminal`, with the same terminal outcome vocabulary. An Executor reports events; it does not directly mutate the canonical task. Task Core may project `blocked` or `decision_required` from authoritative Executor/Harness events while an attempt remains live.

P3α operations are `create/get/list/status/cancel/events`. `update`, `provide_input`, `pause`, `resume`, `reprioritize`, arbitrary execution recovery, and side-effect reconciliation are `UNSUPPORTED` until a later contract explicitly adds them.

`task.cancel` targets one exact task. A cancel command result says only accepted/replayed/rejected/unknown. The task becomes terminal `cancelled` only from authoritative Executor/Core evidence. Already completed or irreversible side effects are not retroactively cancelled. D0 means a task may outlive voice/session/media disconnect while the application and Executor remain alive; after process restart, Task Core reconciles and reports truth but does not promise attempt resume.

### 6.4 S8.5 bounded task revision extension

D-079 adds a separately flagged S8.5 profile; it does not expand P3α or change
the Alpha contract above. Its only additional mutations are
`task.provide_input` and `task.update_constraints`, governed by the
[S8.5 revision contract](S8_5_TASK_REVISION_CONTRACT_2026-08-13.md).

Both commands retain the canonical `task_id`, require the exact current
`task_revision`, and create a new immutable revision plus successor attempt only
after Executor-owned predecessor fencing is acknowledged. They never steer a
live attempt in place. Revision-command application state is separate from task
lifecycle state; an accepted command is not proof that the predecessor stopped,
the successor started, a patch applied, or verification passed.

`pause`, `resume`, `reprioritize`, arbitrary instruction replacement, decision
response and constraint relaxation remain unsupported. With the S8.5 feature
off—or under the Alpha/P3α capability profile—the two extension commands fail
closed with zero Task, Attempt, Store, Executor, Agent, Tool or project mutation.

## 7. Cancel, commit, fence, and presented history

The four command types are exact and non-interchangeable:

| Command | Exact authority effect | Must not imply |
|---|---|---|
| `playback.stop` | Audio Device stops the targeted playback and returns a playback confirmation/cursor | response, round, or task cancellation |
| `response.cancel` | Conversation Runtime fences one response tuple and requests generation cancellation | Harness round or task cancellation; backend side effects stopped |
| `round.cancel` | Harness/Agent Runtime requests stop for one round | task cancellation or physical playback stop |
| `task.cancel` | Task Control Core requests stop for one task/attempt | response/round cancellation or side-effect rollback |

Barge-in defaults to `playback.stop`. Interaction policy MAY additionally issue an exact `response.cancel`, but MUST NOT escalate to `round.cancel` or `task.cancel` without a distinct committed/authorized decision.

Command ACK and lifecycle completion are separate. An accepted cancel ACK permits the owner to fence local output; only the authoritative terminal event proves lifecycle termination. Timeout or lost ACK yields `RESULT_UNKNOWN` and reconciliation, not an inferred cancel or retry with a new identity.

Partial/interim/uncommitted input has exactly zero Agent, Tool, Task, command-journal, or destructive-context side effects. `TurnCommit` contains immutable text/hypothesis provenance, scope, context refs, commit ID, and time. Critical-token uncertainty and destructive actions remain subject to D-039 clarification/confirmation even after speech finalization.

Conversation Runtime stores a surface-specific presented ledger:

```text
PresentationAck {
  interaction_id, response_id, response_generation,
  surface: "text" | "audio",
  unit_id, contiguous_cursor, presented_at
}
```

Produced or queued content is not presented. Text becomes presented only after the UI presentation owner ACKs it; audio becomes presented only after Audio Device playout ACK advances the contiguous cursor. Stop/cancel freezes the last acknowledged cursor, retains the acknowledged prefix, invalidates unacknowledged suffixes, and discards all late fenced output. Future context builders consume the explicitly selected surface ledger and MUST NOT claim queued audio was heard. Providers and media transport never write Session History directly.

## 8. WorkProgressEvent v2

`WorkProgressEvent` is a projection, not a lifecycle authority and not a TTS command. It is carried in EventEnvelope and contains:

```text
WorkProgressEventV2 {
  work_ref: { kind: "round" | "task", id: string }
  source: {
    authority: "harness" | "task_core" | "executor"
    event_id: string
    source_work_ref: { kind: "round" | "task" | "attempt", id: string }
    adapter: string | null
  }
  seq: non-negative integer per work_ref projection stream
  state: "accepted" | "running" | "blocked" | "decision_required" | "terminal"
  outcome: terminal outcome | null
  summary: KnownFact<string>
  blocking_question: KnownFact<string>
  artifact_refs: KnownFact<ContextRef[]>
  urgency: "normal" | "attention" | "urgent" | "unknown"
  speakability: "not_speakable" | "eligible" | "attention_requested"
}

KnownFact<T> = { knowledge: "known", value: T }
             | { knowledge: "unknown" }
```

Terminal requires outcome; non-terminal forbids it. Known empty artifacts differ from unknown artifacts. A Bridge maps only a real, scope-matching source event and preserves `work_ref`, source identity, state, outcome, and sequence. It may label absent detail `unknown`; it MUST NOT synthesize percentages, summaries, completion, or blocking questions. `eligible` and `attention_requested` are hints only—Conversation Runtime remains the sole notification/speech arbiter.

Round and task projection sequences are independent. A WorkProgress event cannot change the underlying round/task state and cannot be used to cancel work. A terminal projection with missing/unknown source outcome is invalid; if the owning authority can only establish uncertainty, it emits terminal outcome `unknown` explicitly.

## 9. ContextRef v2

```text
ContextRefV2 {
  source: namespaced string
  stable_id: non-empty opaque string
  uri: non-empty URI string
  revision:
    { kind: "version", value: string }
    | { kind: "snapshot", value: string }
    | { kind: "unversioned" }
  scope: ScopeRef
  permissions: namespaced string[]
  expires_at: RFC3339 UTC timestamp | null
  redaction: { policy_id: string, redacted: boolean, fields: string[] }
  extensions: namespaced object
}
```

Stable ID and URI identify the same logical resource; revision identifies the fact actually observed or authorized. A ContextRef is not itself an authorization grant. Consumers re-check current scope, permissions, expiry, redaction, and resource revision before a side effect. Expired, cross-scope, permission-missing, or redaction-incompatible refs fail before content disclosure or mutation. `unversioned` MUST be disclosed and cannot authorize destructive or irreversible action without a separate fresh resolution and confirmation. Raw secret content is not placed in ContextRef, EventEnvelope, logs, or speech.

## 10. Capability and error contract

A Provider/Adapter/Executor publishes a `CapabilityDescriptor` with component identity, contract major, supported operations/event types, batch/stream modes, cancel/ACK/replay support, declared limits, fallback identity, and current availability. Capability absence returns `UNSUPPORTED`; declared but temporarily unusable capability returns `UNAVAILABLE`. A fallback is observable provenance and never silently changes authority, scope, safety, or commit rules.

`ContractError` contains `code`, optional stable `reason`, safe `message`, `retriable`, `correlation_id`, and a closed safe `details` object. Core codes are:

`INVALID_ARGUMENT`, `UNSUPPORTED`, `UNAUTHENTICATED`, `PERMISSION_DENIED`, `NOT_FOUND`, `CONFLICT`, `STALE`, `CAPABILITY_UNAVAILABLE`, `UNAVAILABLE`, `TIMEOUT`, `CANCELLED`, `PROTOCOL_VIOLATION`, `RESULT_UNKNOWN`, and `INTERNAL`.

Stable reasons include domain distinctions such as `IDEMPOTENCY_CONFLICT`, `TASK_SCOPE_MISMATCH`, and `TASK_PROJECT_MISMATCH`. Consumers retry only when `retriable=true`, the operation is safe under the same identity, and the current generation/scope remains valid. Error message text is never a retry, missing-object, authorization, or terminal-state oracle. Authorization failures at an authenticated boundary do not disclose whether the target exists.

## 11. Feature flags, privacy, and backward compatibility

- With Live Voice/P3α flags off, current Chat JSON/E2A, public API, Session History, Agent/Tool dispatch, TTS, and task behavior remain unchanged and no new timers, media, commands, projections, or persistence writes occur.
- A failure in P1/P2/P3 must not corrupt or block the text path. Fallback is explicit and carries capability/provider provenance.
- Provider-specific objects and status enums stop at their Adapter. Shared modules receive only v2 types or a clearly labeled compatibility projection.
- Raw audio is not persisted by default. Capture, retention, replay, export, and deletion require explicit consent and a documented policy.
- Machine-private credentials, provider endpoints/configuration, project registration, devices, browser permissions, runtime data, and network availability are never represented as Git-restored capability.

## 12. Dependency DAG and implementation gates

```text
ACG-1 accepted shared semantics
├─ shared v2 types + schema fixtures + fake clock/event store + conformance runner
├─ P1: AIO-A, SR-A, SS-A
│  └─ Browser batch compatibility adapters -> later selected streaming Provider adapters
├─ P2: RM-A, CR-A, II-A, AB-A
│  └─ CR response/fence/presented ledger -> RM/II/AB real B/C integration
├─ P3: TC-A, ED-A, VB-A
│  └─ TC canonical state/event/idempotency -> AutoHarness D0 Executor adapter and Command/Voice bridges
└─ X-OBS contract work
   └─ X-E2E / X-WEB after the relevant real adapters
```

The Day 1–2 critical kernel implements the shared identity/scope, authority, committed-input, core-lifecycle, four-cancel, generation-fence, minimum-envelope/sequence, capability/error, and feature-off primitives. After its grouped Tier 3 review, `*-A` packages may proceed in parallel against shared fakes. Consumer-specific ACG sections become local gates before the B/C package that actually consumes them: Speech/Audio provenance and privacy before real Provider/Audio wiring; presented cursor/history and notification Context before P2 presentation wiring; AuthorizationContext, atomic outbox, attempt dedup, and restart reconciliation before P3 Store/Executor wiring. A pure contract test cannot close a real adapter, and a real happy-path demo cannot replace the required negative/state/race/recovery evidence.

## 13. First baselines

| Boundary | Contract/fake baseline | First concrete integration baseline | Honest limitation |
|---|---|---|---|
| Speech Provider | deterministic batch/stream/cancel/capability/error fake | existing Browser Speech recognition/synthesis behind P1 batch Ports | compatibility/fallback only; fixed-browser quality is not Provider selection or P1 closure |
| Interaction | deterministic Cascade policy fake | Web Alpha Cascade using the shared Speech Ports | Native Audio Engine remains a later replaceable Adapter and never becomes an Agent/Tool control plane |
| Realtime Media | loopback/fault-injection fake | no real Provider selected by this Gate | real duplex transport, AEC, device, latency, and privacy evidence remain open |
| Executor | deterministic event-script Executor fake | existing AutoHarness scheduler plus fixed `extended_evolve_pipeline` behind an Executor Port | side-effecting Demo/D0 integration target only; isolated data/project required; no general Executor, D1/D2, exactly-once, or rollback claim |

No new cloud/native Provider, credential, endpoint, or model is selected here. Provider selection and real-device quality are evidence-bearing later gates.

## 14. Conformance test skeleton

The shared-contract implementation creates language-neutral JSON fixtures plus Python/TypeScript conformance runners. Items 1–8, the minimum Capability/Error portion of item 12, and feature-off portions of item 14 form the critical-kernel baseline. The remaining items land before their consuming B/C integration, and all applicable items must be complete for the Week 4 Integrated Alpha Gate:

1. v1/v2 version separation, canonical round-trip, closed fields, and explicit lossy compatibility behavior;
2. identity kind/parent/scope validation and zero cross-scope disclosure or mutation;
3. Command/Query/Result exclusive-envelope rules, stable command replay, idempotency conflict, and single response ownership;
4. EventEnvelope duplicate, conflicting duplicate, sequence gap, out-of-order, causation, and reconciliation cases;
5. all allowed and forbidden interaction/turn/response/task/attempt transitions, terminal irreversibility, and required outcome;
6. exact four cancel scopes, ACK-versus-terminal behavior, non-escalating barge-in, and zero unrelated cancellation;
7. partial/uncommitted input with zero Agent/Tool/Task side effects and exact once-only TurnCommit;
8. response generation fence and late callback zero effects across UI/history/audio/Agent/Tool/Task;
9. produced/enqueued/presented/invalidation cursors, playback ACK, interrupted prefix retention, and no queued-audio-as-heard claim;
10. WorkProgress source provenance, known/unknown facts, sequence, terminal outcome, and zero direct TTS/state mutation;
11. ContextRef version/snapshot, expiry, permission, redaction, unversioned destructive-action rejection, and secret-safe serialization;
12. capability unsupported/unavailable/fallback distinctions and stable error/retry behavior independent of message text;
13. D0 disconnect/restart reconciliation boundaries and explicit unsupported P3 operations;
14. feature-off/text-path regression and cross-plane fault isolation;
15. fake Provider/Executor fault injection, then one real adapter integration suite per B/C package.

The detailed 2026-08-03 ACG scenario inventory and its original blank execution fields live in the frozen [Sol module pre-review record](../SOL_MODULE_PRE_REVIEWS_2026-08-03.md). Current track state and replacement credit live in [STATUS.md](../STATUS.md). Passing the shared skeleton means only the implemented contract subset is conformant; each runtime module still needs the risk-tier review and real-path evidence required by D-046.

## 15. Gate exclusions and return-to-Sol conditions

This Gate does not select a production Provider, define vendor wire payloads, implement code, approve authentication, restore machine-private state, close D-031, prove real-time latency, or sign a release. Non-Sol execution stops and returns to Sol if implementation requires:

- a new identity, state, transition, outcome, cancel scope, authority, error code/category, or compatibility rule;
- interpreting unknown/unsupported/error as success or making error message text semantic;
- weakening scope, commit, fence, terminal, provenance, zero-side-effect, or feature-off assertions;
- allowing a Provider/Bridge/UI/Executor to become a second authority;
- treating an ACK as lifecycle completion, queued output as presented, or task cancellation as side-effect rollback;
- choosing a real Provider/credential/model or expanding AutoHarness beyond the stated D0 adapter boundary.
