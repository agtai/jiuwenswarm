# CR-B runtime implementation review

> Batch date: 2026-08-05
>
> Source branch/worktree: `codex/cr-b-runtime` / independent worktree based on
> `e407af45cbb97b23aedab5b5ce9b24880b09667b`; current integration base:
> `50b98b4a381cc44c25a63b8c37ec684ecb6adea3` on `hx/0803_live_voice`
>
> Current state: **CURRENT-BRANCH INTEGRATION REVIEW PASS AFTER FIX; no real-route or release claim**
>
> Integration reconciliation: D-031 is already closed on the current base, AIO-B is
> recorded under D-058, and current state is owned only by `STATUS.md`.

## 1. Original request and bounded outcome

Continue useful work while D-031 is being completed by implementing the independent
`CR-B` runtime-core slice. The bounded result is an explicitly started, non-blocking
Conversation Runtime event loop over the existing CR-A reducer, with deterministic
generation fencing, non-escalating barge-in, a per-surface presented ledger and a
declarative effect outbox.

This slice uses only fake/deferred upstreams. It does not connect a real Agent,
Provider, browser presentation ACK, Realtime Media route, Session History writer or
durable store, and it cannot close the P2, Week 2 or Web Alpha Gate.

## 2. Authority, dependency and risk

- Normative authority: `architecture/ARCHITECTURE_CONTRACT_GATE_V1.md`, especially
  section 7.
- Current package boundary: `roadmap/WEB_ALPHA_DELIVERY_MATRIX_2026-08-05.md`,
  `CR-B`.
- Frozen scenario oracle: `SOL_MODULE_PRE_REVIEWS_2026-08-03.md`, CR-A P/N/B/S/T/C/R/I/F/K/X matrix.
- Existing dependency: CR-A `ConversationRuntime` remains the lifecycle and
  generation reducer; CR-B exclusively serializes its write entry points.
- Accepted decision set: D-039, D-042, D-043, D-046, D-047, D-052, D-053 and D-058.

CR-B is Tier 2 because it changes state, concurrency, response-output fencing and
presentation/history truth. It therefore requires the D-053 implementation
self-review, cold complete-diff review and independent review, plus scoped Sol pre-
and post-review.

## 3. Scoped Sol pre-review

The read-only scoped Sol review returned **conditional GO** with four mandatory
conditions:

1. Normal output saturation must never block barge-in or exact cancellation.
   The loop therefore has bounded normal, ordered-observation and high-priority
   control lanes. Presentation ACK uses the separate observation capacity; an ACK
   accepted before a later control is applied first, while ordinary output cannot
   consume the critical control reserve. The worker never waits for Agent, Provider,
   media, UI, history or another effect owner.
2. `contiguous_cursor` is the zero-based contiguous unit sequence for one exact
   `(ResponseRef, surface)`. Source spans are separate UTF-8 byte offsets. `union`
   deduplicates identical source-span/content-ref facts and sorts by source span.
3. Presentation ACK after stop/cancel/fence/terminal cannot advance. Response-cancel
   ACK or `result_unknown` remains orthogonal and may update its known old response
   record after terminal. An authoritative terminal event for an old known response
   can update only that record and produces no current-response or presentation
   effect.
4. CR-B owns the CR-A write entry. Callers receive only controlled snapshots and a
   declarative outbox. A new generation invalidates unclaimed old UI/audio output;
   already claimed effects still require the owner to validate the exact response
   tuple before applying them.

The review also confirmed that the old CR-A design record mentioned a presentation
ledger while the implemented CR-A reducer does not contain one and the current Web
matrix assigns it to CR-B. CR-B may add server-internal types without changing or
claiming the shared wire-v2 schema. Browser protocol and durable ACK integration are
explicit later work.

## 4. Frozen implementation contract

### Event loop and outbox

- Construction creates no task, timer, request or effect. `start()` is explicit.
- Feature-off creates no worker and all mutations remain absent.
- One worker linearizes reducer operations. Normal, ordered-observation and critical
  control lanes are separately bounded. Presentation ACK ordering relative to a
  later critical control uses a monotonic ingress sequence; critical control still
  preempts ordinary output. Normal or observation overflow fails immediately and
  cannot consume critical control capacity.
- The ordered-observation lane uses the configured normal-capacity bound but has
  separate occupancy. Without a pending critical control it preserves ingress order
  with normal work, so an ACK cannot overtake its earlier local enqueue.
- Barge-in, response cancel, response replacement and interaction close use the
  critical control lane. Presentation ACK uses ordered observation. No external or
  potentially blocking callback runs in the worker.
- Worker-operation failure completes only that operation with a stable error; the
  worker continues.
- Shutdown is infrastructure teardown, not an interaction/response/round/task
  cancel. It rejects new work, completes or explicitly rejects every accepted
  future, fences local pending presentation facts, and leaves no worker task.
- Effects contain an exact `ResponseRef` and optional surface/unit facts. Pending
  stale `ui.render` and `audio.enqueue` effects become invalidated; claimed effects
  remain auditable and must be revalidated by their owner.

### Presented ledger and history selector

- A presentation unit contains exact response, `text|audio` surface, unit ID,
  zero-based sequence/cursor, UTF-8 source byte span and semantic content ref.
- Per-surface sequence and source span are contiguous. Empty, overlapping, gapped,
  rewritten or cross-surface-conflicting units fail closed.
- State is only `produced -> enqueued -> presented`, or an unpresented unit becomes
  `invalidated`. Presented and invalidated records are immutable.
- `produced` and `enqueued` never count as presented. Only an exact contiguous ACK
  may advance a surface.
- Response acceptance freezes `text|audio|union` history policy. The selector reads
  only presented facts; it does not write Session History. Union uses matching
  source-span/content-ref facts and produces deterministic source order.
- New generation, exact response cancel, terminal, interaction close and loop
  teardown retain the ACKed prefix and invalidate the unACKed suffix. Recovery from
  process loss remains unknown/unpresented because this slice is memory-only.

### Barge-in and cancellation

- Default barge-in closes only the exact audio presentation surface, emits one
  `playback.stop`, retains its ACKed prefix and invalidates its unACKed suffix. Text
  presentation may continue.
- Policy may additionally request one exact `response.cancel`, which fences both
  surfaces. It never produces `round.cancel` or `task.cancel`.
- `playback.stop` and `response.cancel` are independent exact-target effects.
- Same action ID plus same fingerprint is a replay with no new effect. Reusing the
  action ID with different target/policy is a conflict with zero new effects.
- Cancel ACK and `result_unknown` never make a response terminal. A late
  authoritative ACK may reconcile `result_unknown`; a later timeout cannot downgrade
  an acknowledged cancel, and exact duplicate observations emit no new event. Only
  an authoritative terminal transition closes lifecycle.

## 5. Scenario oracle

| ID | Scenario | Required result | Forbidden effect |
|---|---|---|---|
| P-01 | explicit start and legal CR lifecycle | serialized canonical events and exact increasing response generations | direct CR-A mutation or external wait in worker |
| P-02 | text/audio produce, enqueue and contiguous ACK | exact surface cursor advances; selector follows frozen policy | produced/enqueued counted presented |
| N-01 | disabled/not-started/closed runtime | stable reject or disabled no-start with zero state/effect/task | hidden worker, timer or fallback path |
| N-02 | wrong scope/ref/generation/unit/gap/ACK-before-enqueue | stable fail closed and fingerprint unchanged | UI/audio/history/Agent/Tool/Task effect |
| B-01 | first unit, Unicode/code/path source spans, absent surface | byte offsets and cursor 0 remain exact | Python/JavaScript character-index inference |
| S-01 | stop/cancel/fence/terminal after ACKed prefix | prefix retained; unACKed suffix immutable invalidated | prefix erasure or late suffix restoration |
| T-01 | new generation races old output/ACK/terminal | old output/ACK zero effect; old terminal updates only old record | current response/ledger mutation |
| T-02 | cancel request, ACK/result_unknown and terminal reorder | orthogonal facts converge without terminal guess | ACK/timeout-as-terminal or double effect |
| C-01 | duplicate/conflicting barge-in | one exact stop/cancel or deterministic conflict | duplicate or widened cancellation |
| C-02 | normal lane saturated when barge-in arrives | control accepted and handled first; queued stale output is fenced | barge-in wait/drop behind output |
| C-03 | presentation ACK accepted before later barge-in at capacity 1 | ACK is applied first and critical control remains independently admissible | ACKed prefix loss or control-capacity theft |
| R-01 | loop teardown or in-memory restart | no hanging future/task; prior presentation durability is not claimed | restored-heard/presented inference |
| I-01 | fake UI/audio claims effect then ACKs | exact tuple/unit round trip and selected presented facts | owner/lifecycle identity invention |
| F-01 | formal capability off | legacy Chat/Demo paths and stores unchanged; new effects zero | hybrid formal/legacy mutation |
| X-01 | affected CR-A/A-package regressions | existing fixtures and behavior remain green | weakening prior assertion |

Agent, Tool, Task, Chat-store mutation, Session History persistence, `round.cancel`,
`task.cancel`, raw audio persistence and notification effects are zero in every
scenario.

## 6. Planned files and verification

Actual implementation boundary:

- new `jiuwenswarm/server/live_voice/presentation_ledger.py`;
- new `jiuwenswarm/server/live_voice/conversation_runtime_loop.py`;
- focused `tests/unit_tests/live_voice/test_conversation_runtime_loop.py`;
- narrow canonical cancel-reconciliation correction in
  `jiuwenswarm/server/live_voice/conversation_runtime.py` and its Python test;
- matching parity correction in the existing formal Web replica and its JavaScript
  test;
- this review record and a concise current-state update in `STATUS.md`.

The tracked CR-A/replica correction was added after post-review found that a timed-out
cancel could not converge when its late authoritative ACK arrived. It changes no
shared-v2 wire field: `result_unknown -> acknowledged` is now accepted, while
`acknowledged -> result_unknown` is a no-op and neither observation is terminal.

No shared-v2 schema, Task/Scheduler, `agent_ws_server.py`, Agent Adapter, i18n or
D-031 implementation file is in scope.

Verification covers focused positive/negative/state/timing/concurrency/capacity/
teardown tests, all Live Voice unit regressions, shared-v2/fake-vertical regressions,
frontend replica parity, formatting/static checks, `git diff --check`, Markdown link
validation, D-053 three-pass review and scoped Sol post-review.

## 7. Review and evidence ledger

| Pass | State | Findings/fixes/evidence |
|---|---|---|
| Scoped Sol pre-review | `CONDITIONAL GO / FROZEN` | Four mandatory conditions in section 3 were incorporated before implementation. |
| Implementation self-review | `PASS AFTER FIXES` | Exact-ref authority, three-lane admission/ordering, immutable ACK truth, outbox invalidation/claim, shutdown drain and zero forbidden Task/round effects were reread against the frozen matrix. |
| Cold complete-diff review | `PASS AFTER FIXES` | Initial cold reads found fenced nonterminal mutation, replay admission, ACK ordering/capacity, interaction-close commit, cancel reconciliation, cross-surface conflict and shutdown-effect gaps; each has a focused regression. The final complete-diff reread found no remaining actionable defect. |
| Scoped Sol post-review | `PASS AFTER FIXES` | Sol matched all nine frozen SHA-256 values, reread the expanded complete diff, independently reran Python focused 36/36 and frontend replica 9/9, and reported no remaining finding. |
| Independent review | `PASS AFTER FIXES — EQUIVALENT` | An independent read-only subagent matched all nine frozen SHA-256 values, performed the cold complete-diff review and independently reran focused Python 36/36. This is the recorded D-053 substitute because the product `/review` command was unavailable; it is not a claim that `/review` ran, and the substitute did not rerun browser or external-service evidence. |
| Current-branch integration review | `PASS AFTER FIX` | Reconciled the complete candidate diff against the current AIO/D-031 base, added the missing README evidence route and repeated the cold review. It removed stale parallel-branch/D-031 claims from STATUS and fixed shutdown-result loss: cancelling the first shielded `close()` waiter no longer consumes the one retrievable batch of already-claimed teardown/control effects. A focused cancellation/recovery regression proves the result is delivered once to the first successful waiter. The prior independent review remains the D-053 independent pass; this integration review did not claim a second `/review`. |
| Automated verification | `PASS` | Focused CR-B/CR-A passes 37/37; all Live Voice unit passes 80/80; shared-v2 plus fake verticals pass 42/42; frontend replica passes 9/9; ruff and scoped mypy pass; Prettier and strict TypeScript compile pass; the source candidate's focused coverage result was 91%; current `git diff --check`, trailing-whitespace scan and local Markdown links pass. Repository-wide pytest coverage instrumentation was disabled for scoped runs because its plugin collection is machine-expensive; test selection and assertions were unchanged. |
| Real integration evidence | `NOT IN SCOPE` | Real Agent/Media/browser ACK, Session History durability and complete Web voice E2E remain deferred. |

The bounded CR-B foundation is reconciled on `hx/0803_live_voice`. It establishes an in-memory runtime authority and deterministic fake/deferred evidence only; it does not complete the first real P2 Agent compatibility route or earn P2/Web Gate replacement credit.
