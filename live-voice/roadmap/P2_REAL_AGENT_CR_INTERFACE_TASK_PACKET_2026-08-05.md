# P2 Real Agent + CR interface Task Packet

> Frozen: 2026-08-05
>
> Package: `P2-REAL-AGENT-CR`
>
> Decision authority: D-059; the user accepted Integration Owner recommendations `1A 2A 3A 4A 5A`
>
> Execution state and current blockers remain owned by [`STATUS.md`](../STATUS.md). This packet freezes the package contract; it does not claim implementation, review, integration or Gate acceptance.

## 1. Objective and risk

Resume the blocked real P2 Agent compatibility route by adding only the adjacent Agent/Harness and formal-history interfaces that CR-B and AB-B require. The package must connect an already committed turn to the real JiuwenSwarm Agent/Harness without inventing round facts, widening cancellation, writing unpresented history or allowing caller cancellation to consume teardown ownership.

This is a coherent Tier 3 authority/protocol boundary with Tier 2 state and concurrency behavior. It requires the applicable complete D-032 matrix, D-053 self-review, cold complete-diff review and an independent `/review` or recorded equivalent. The implementation remains a formal foundation until authenticated product composition, real browser PresentationAck and the cumulative route pass their own Gates.

## 2. Frozen interface contract

### 2.1 Harness-owned canonical round reservation and events

The Agent/Harness runtime that owns actual round execution must also own canonical `round_id` allocation and round lifecycle events. Agent Bridge and compatibility facades may carry these facts but must not create, infer or relabel them.

Before a round can execute, the Harness owner returns a reservation/handle containing:

- a Harness-allocated opaque `round_id`;
- an opaque reservation token used only at the trusted internal boundary;
- the exact immutable binding to `ScopeRef`, request, TurnCommit, correlation and owning Harness instance;
- declared event/cancel/detach capabilities.

The exact class and method names are implementation-owned, but the behavior must support a flow equivalent to:

```text
Harness.reserve_round(binding) -> HarnessRoundReservation
Harness.commit_round(reservation, request) -> HarnessRoundHandle
Harness.abort_round_reservation(reservation, reason)
HarnessRoundHandle.events() -> canonical EventEnvelope stream
HarnessRoundHandle.cancel(exact command) -> cancel request result
HarnessRoundHandle.detach() -> subscription/resource detach only
```

The source stream supports the complete canonical state vocabulary:

```text
round.accepted
round.running
round.blocked
round.decision_required
round.terminal + exact terminal outcome
```

Only states actually observed by the Harness may be emitted. An unavailable state/capability remains unsupported or absent; the Adapter must not manufacture it. Every event is an immutable `live-voice.contract.v2` `EventEnvelope` with exact Harness producer authority, scope, round stream reference, stable event ID/bytes, contiguous source sequence, correlation/causation and valid state/outcome. Agent text/tool chunks are not round lifecycle events. Stream end without a source terminal stays explicit incomplete/error truth.

Reservation is not `round.accepted` and must cause zero Agent, Tool or Task business effects. The accepted event is emitted only after the Harness commits the reserved round for execution.

### 2.2 Exact scoped round cancel

The Harness owner exposes an exact cancel operation bound to:

```text
command_id + scope + request_id + round_id + trusted reservation/round binding
```

The same owner atomically checks the active/terminal round registry before any cancel effect. Missing, wrong-scope, wrong-request, stale, rebound or terminal targets reject without touching another round, Agent, Tool or Task. The same command ID and fingerprint replays the original result; a changed fingerprint is `IDEMPOTENCY_CONFLICT` with zero new effect.

An accepted ACK proves only that the exact cancel request was accepted. It does not prove execution or side effects stopped and does not make the round terminal. Only the authoritative `round.terminal` event closes the lifecycle; normal completion may win the race. `playback.stop`, barge-in and `response.cancel` never implicitly upgrade to `round.cancel`.

### 2.3 Formal deferred/no-history execution seam

The formal P2 route must not call the legacy `process_message_stream()` history-owning path. Add a distinct formal Agent execution seam that:

- consumes one immutable committed turn and an explicitly injected CR-selected context snapshot;
- bypasses direct legacy user/assistant/tool/error/final Session History writes;
- bypasses implicit legacy cloud/auto-memory history hooks for this first slice;
- emits Agent output and Harness events without persisting them as presented facts;
- leaves the existing Direct Chat/fallback path byte-for-byte behaviorally unchanged when the formal feature/capability is off.

The frozen Alpha history surface is `text`. A formal History Writer may persist the committed user turn after the TurnCommit boundary. Assistant history may be persisted only from the CR text-surface selector after an exact contiguous UI PresentationAck. Audio ACK remains playback evidence and does not independently enter Session History. Produced/enqueued text and unacknowledged or fenced suffixes never enter history.

History effects/writes are idempotent under an exact response/generation/surface/cursor binding. Response replacement, cancel, terminal or interaction close retains the acknowledged prefix and permanently invalidates the unacknowledged suffix. The formal Agent seam must not read uncontrolled legacy history as a substitute for the injected selected context.

### 2.4 Atomic dispatch reservation before CR mutation

Composition uses a strict two-phase admission protocol:

```text
reserve dispatch capacity + request ledger + scoped round binding
-> obtain HarnessRoundReservation
-> only the new reservation owner may call CR accept_response
-> commit the exact ResponseRef to the reservation and start dispatch
or
-> abort the reservation without Agent/Tool/Task effects
```

Reservation occurs before any CR response mutation or generation fence. It must hold the bounded dispatch capacity and immutable request/round/commit/correlation fingerprint. Concurrent exact replay returns the same reservation/composition handle and causes no second CR mutation or Agent dispatch. Conflicting request fingerprints, scoped-round rebinding, exhausted capacity or rejected Harness admission fail before CR mutation.

Reservation abort is mandatory when CR mutation fails or the reservation owner is cancelled before commit. Reservations have a bounded configurable expiry; expiry produces stable failed/expired truth, releases capacity and cannot be replayed as a fresh execution under the same identity. Commit is idempotent and cannot later fail for an admission condition already reserved. If an infrastructure failure makes dispatch truth ambiguous, fence the response and report explicit unknown/error truth; do not invent a round terminal event.

### 2.5 Retained, shielded and bounded shutdown

The first close creates one retained shutdown coordinator. All later close callers observe that same coordinator through shielded waits. Cancelling or timing out one waiter must not cancel teardown, consume its result or release ownership.

Shutdown must:

- stop new admission immediately;
- drain or explicitly settle every accepted reservation/request and already accepted output;
- keep Agent stream/subscription and cleanup ownership until terminal settlement or honest pending/failure truth;
- bound each caller's wait and every Adapter cleanup wait;
- remain `closing`/cleanup-pending after timeout and return a stable pending/timeout result instead of claiming `closed`;
- enter `closed` only after the worker, subscriptions, queues and owned cleanup have actually reached terminal teardown;
- bound retained requests, subscriptions and cleanup tasks.

Subscription detach is infrastructure cleanup, not `round.cancel`. A transient WebSocket/media disconnect does not cancel while the canonical interaction remains open. Explicit `interaction.closed` separately issues one idempotent exact `round.cancel` for its active conversational round, then observes the authoritative terminal event. Infrastructure/runtime shutdown by itself never widens into round or task cancellation.

## 3. Required composition flow

```text
TurnCommit
-> reserve Agent Bridge dispatch and Harness round
-> CR accepts exact response once
-> commit reserved Harness dispatch
-> Harness canonical events + Agent output
-> AB validates/maps source events
-> CR validates/fences output
-> UI text PresentationAck
-> CR text selector
-> idempotent formal History Writer
```

Any failure before CR acceptance has zero CR, Agent, Tool, Task and history mutation. Any failure after dispatch preserves the exact round/response truth and never substitutes Adapter completion, stream end, cancel ACK or shutdown timeout for an authoritative terminal event.

## 4. Package boundaries

In scope:

- the minimal real JiuwenSwarm Agent/Harness reservation, event, exact-cancel and no-history seams;
- the real Agent Adapter required by AB-B;
- atomic Bridge/CR composition admission and exact replay/conflict behavior;
- the CR notification/output consumer needed to carry real Agent output through the existing formal lifecycle;
- bounded retained shutdown and focused formal-history wiring/tests;
- updating the Worker2 review record to supersede its former interface blocker with actual evidence.

Out of scope:

- RM-B/C, II-B/C, real Speech Provider or browser PresentationAck implementation;
- P3 Task authority, `task.cancel`, TC/VB/ED changes or P3 authenticated composition;
- production authentication/authorization, multi-tenant existence hiding or production release claims;
- direct TTS from Harness/WorkProgress and any new fifth cancel scope;
- broad refactoring of Direct Chat, legacy history, SessionManager, Team or AutoHarness;
- STATUS, README, DECISIONS, roadmap, acceptance, Replacement Ledger, merge or push changes from the Worker branch.

The route may be reviewed as a real Agent formal foundation under current single-user consistency, but remains `PARTIAL` and cannot claim Production or Replacement Ledger credit until authenticated product composition and cumulative real-path evidence exist.

## 5. Minimum acceptance matrix

The Worker must add focused tests and affected regressions that prove at least:

1. Positive real-facade path: committed turn reserves once, CR mutates once, Harness emits source-backed accepted/running/terminal and usable final Agent output reaches the typed consumer.
2. Truthful state family: blocked/decision-required are projected only from real Harness source events; absent capabilities remain unsupported/unknown.
3. Exact cancel: correct target accepted; wrong scope/request/round, stale and terminal targets have zero unrelated effects; ACK and terminal remain distinct; completion/cancel races converge truthfully.
4. Atomic admission: concurrent exact replay executes once; conflicting request or round, full queue, Harness reservation failure and CR acceptance failure produce no partial CR/Agent mutation and release reservations.
5. Formal history: no legacy write occurs before ACK; text ACK persists only the contiguous selected prefix; audio-only ACK, unACKed/fenced suffix, late output and wrong generation write zero history; direct Chat history regression passes unchanged.
6. Feature/capability off: zero worker, timer, reservation, Agent, Tool, Task, history or notification effect and existing text route unchanged.
7. Shutdown: cancelled/timed-out close waiter cannot cancel the retained coordinator; stalled stream/cleanup has bounded caller wait and honest pending state; late teardown is observed once; no false closed state or implicit round/task cancel.
8. Empty final, Adapter exception, stream end without terminal, event duplicate/gap/conflict, output backpressure and consumer cancellation fail closed without fabricated completion or lost terminal output.
9. Forbidden effects are asserted as zero for partial/uncommitted input and every admission/cancel/scope/history negative path.

Run the focused package suite, AB-B/CR-B affected tests, all affected Live Voice tests, existing Chat/E2A/cancel/history regressions, formatting/static checks and `git diff --check`. A fake-only test cannot replace the real-facade authority tests.

## 6. Handoff and Git gate

Before requesting a commit, leave the implementation uncommitted and provide:

- branch, base SHA and complete status;
- concise diff and explicit exclusions;
- self-review, final cold complete-diff review and independent review record;
- exact focused/affected test commands and results;
- remaining real-service/auth/browser limitations;
- proposed commit message and exact intended file scope.

Commit, amend, merge, cherry-pick and push remain separately gated by root `AGENTS.md`. Integration Owner review and integration are required before any product or Gate claim.
