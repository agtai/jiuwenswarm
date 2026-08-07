# AB-B and WorkProgress v2 implementation review

> Batch date: 2026-08-05
>
> Source branch/worktree: `codex/ab-b-work-progress` / independent worktree based on
> committed CR-B candidate `4b384970ff06ef7adc5fe9ad4b0bd7f745ab412b`;
> integration base at review closure: `1d721ca07587764f054e905bb4701e5af6d6a6ef` on
> `hx/0803_live_voice`
>
> Review-snapshot state: **CURRENT-BRANCH INTEGRATION REVIEW PASS AFTER FIXES; no real-route
> or release claim**
>
> Integration reconciliation: D-031 is closed under D-057, AIO-B is recorded under
> D-058, CR-B was integrated at closure, and later landed/current state is owned only by `STATUS.md`.

## 1. Original request and bounded outcome

The source candidate continued an independent module while D-031 was being completed.
This batch implements the reusable `WorkProgressEventV2`/`ContextRef` contract slice
and an `AB-B` non-blocking runtime foundation over an injected Agent/Harness Adapter.

The runtime accepts an already committed Turn, returns immediately, bounds dispatch
and output pressure, preserves exact Agent event provenance, and projects only real
authoritative Harness round events into WorkProgress. It never guesses summaries,
artifacts, blocking questions or terminal outcomes.

The Adapter is intentionally injected. This batch does not modify the real Agent
WebSocket server, D-031 Agent Adapter, Scheduler/Task/AutoHarness code, frontend
D-031 UI/i18n, Conversation Runtime notification policy, media, TTS or Session
History. It therefore remains a `PARTIAL` AB-B foundation and earns no P2, Week 2
or Web Alpha replacement credit.

## 2. Authority, dependency and risk

- Normative authority: `architecture/ARCHITECTURE_CONTRACT_GATE_V1.md`, especially
  identity/scope, event authority, WorkProgress and ContextRef sections.
- Package boundary: `roadmap/WEB_ALPHA_DELIVERY_MATRIX_2026-08-05.md`, `AB-B`.
- Existing dependencies: committed AB-A mapping, shared-v2 critical kernel and CR-B
  runtime candidate.
- Accepted decisions: D-032, D-042, D-043, D-046, D-047, D-052, D-053, D-055,
  D-057 and D-058.

The shared protocol change is Tier 3 and the concurrent bounded runtime is Tier 2.
The coherent batch therefore uses the complete applicable D-032 matrix, scoped Sol
pre/post review and all three D-053 review passes.

## 3. Scoped Sol pre-review and frozen corrections

The scoped Sol pre-review returned conditional approval with these requirements:

1. `EventEnvelope.seq` and `WorkProgressEventV2.seq` are independent domains.
   Future projection sequence is quarantined and drained when its gap closes; old
   or conflicting projection sequence fails closed.
2. Authority/ref pairs are exact: Harness owns round, Task Core owns task and
   Executor owns attempt. Attempt-to-task projection requires an
   `IdentityRegistry` parent binding.
3. The projection source event ID must equal causation ID; scope, correlation,
   source identity, state and outcome must match the already accepted source event.
4. Only real `round.*` Harness events produce round progress. Text chunks and
   Adapter completion cannot fabricate accepted/running/terminal facts.
5. Dispatch overflow is a synchronous zero-Adapter-effect rejection. Output
   backpressure waits only inside a background worker; terminal output is never
   dropped.
6. Close drains accepted work and never implies `round.cancel`. Adapter failure is
   local and never creates a fake terminal event.
7. Queues and replay ledgers are bounded. This slice is memory/session lifetime and
   refuses unsafe eviction instead of claiming durable recovery.
8. `ContextRef` in this batch proves strict wire shape, revision variants and scope
   matching only. Permission, expiry, redaction policy and destructive-operation
   authorization remain consumer-owned gates.

## 4. Implemented contract

### Shared WorkProgress and ContextRef

- Python and TypeScript expose the same closed `ContextRef` shape with version,
  snapshot and explicitly unversioned revision kinds. Multiple revisions of one
  logical resource are valid; a reference is not authorization and carries no
  content bytes.
- Command, Query and TurnCommit parse, retain and round-trip non-empty ContextRefs;
  cross-scope references fail closed.
- `WorkProgressEventV2` carries exact work/source identities, source event ID,
  projection sequence, state/outcome, known-versus-unknown facts, urgency and
  speakability.
- Known-empty artifact lists are distinct from unknown artifacts. Terminal requires
  an outcome and non-terminal forbids one.
- `work.progress` is an Adapter-authored EventEnvelope projection. It cannot mutate
  the source round/task lifecycle and cannot authorize cancellation or speech.
- Python and TypeScript sequence trackers validate source causation and keep
  envelope sequence separate from per-work projection sequence. Source projection
  order follows scoped logical source identity across producer replacement, while
  Task Core and different Executor attempt sources may interleave independently.
- The current lifecycle source schema proves only state/outcome, so a tracked
  projection with known detail or notification hints fails closed. Direct parsing
  still preserves known-empty versus unknown for a later richer authority source.

### AB-B runtime foundation

- Construction and feature-off create no worker or Adapter effect. `start()` is
  explicit and submission is synchronous/non-blocking.
- Dispatch/output queues, concurrency, retained requests and source-event facts are
  bounded. A full dispatch lane rejects before Adapter invocation. A full output
  lane backpressures the background worker only.
- Same request ID and exact fingerprint replays one handle; a changed fingerprint
  is a conflict. A scoped round cannot be rebound to another request.
- Runtime/request/projector identifiers reject invalid Unicode before admission;
  projection event IDs use unambiguous UTF-8 hex tokens rather than delimiter-only
  concatenation.
- Adapter Agent events must retain exact request/commit, provenance and sequence;
  their delivery retains the request's round/response/correlation binding. Harness
  events must retain exact scope, round, correlation, authority, sequence and
  globally stable event bytes.
- Source gaps reorder deterministically, exact duplicates project once and
  conflicting IDs/sequence fail closed.
- Every accepted authoritative round event yields one unknown-detail,
  `not_speakable` WorkProgress projection. No direct TTS, notification, Task, Tool,
  Chat/history or cancel effect exists in the runtime.
- Natural stream end without a source terminal is reported as
  `stream_ended_without_terminal`; Adapter exception fails only that request. Neither
  path invents terminal completion.
- Terminal delivery settles business completion before Adapter cleanup. Cleanup is
  best-effort with a finite wait; timeout/exception cannot rewrite completion.
  A cancellation-suppressing Adapter cleanup may remain pending after runtime close,
  but it is detached from business completion and the retained request bound limits
  how many such cleanup tasks this runtime can originate.
- Delivery waits are owner-loop bound and observe an independent close signal, so
  idle close wakes all waiting consumers without consuming bounded output capacity.
  Close stops admission, drains accepted work and leaves cancellation ownership
  unchanged.
- The shared completion handle isolates caller timeout/cancellation from the retained
  request result. Delivery waiters observe readiness and dequeue only on their
  synchronous successful return, so cancelling one waiter cannot consume an arriving
  Agent or WorkProgress output.

## 5. D-032 scenario matrix

| ID | Dimension/scenario | Required result and evidence | Forbidden effect / remaining limit |
|---|---|---|---|
| P-01 | committed Turn through slow injected Adapter | submit returns immediately; exact Agent event is delivered | caller waits for Agent or identity is rewritten |
| P-02 | all five authoritative round states | one source-backed projection per source event; exact outcome | guessed detail, state or terminal |
| N-01 | disabled, not started, closed, invalid ID or dispatch full | stable admission reject and zero Adapter call | hidden worker/fallback/mutation |
| N-02 | wrong scope/ref/authority/causation/state/outcome/sequence | reject or quarantine with no projection | best-effort mapping or partial acceptance |
| B-01 | seq 0, capacity 1, known empty/unknown, Unicode and multiple revisions | values and knowledge remain exact | truthiness, character-index or empty-as-unknown inference |
| B-02 | request/source ledgers at bound | replay remains safe; new unsafe identity is refused | eviction followed by duplicate execution |
| S-01 | accepted/running/terminal and stream end without terminal | lifecycle projection follows source only; incomplete stream stays explicit | stream end treated as completed |
| T-01 | source gap, reorder, duplicate, conflict and producer replacement | logical-source ordered single projection; different sources may interleave | duplicate/regressed or invented global-order progress |
| T-02 | close with work/output/waiters or stalled cleanup | delivery drains; waiters wake; cleanup wait is bounded | dropped terminal, hung close or `round.cancel` |
| C-01 | concurrent duplicate/conflicting request and event IDs | one execution/projection or deterministic conflict | double Agent dispatch/output |
| C-02 | concurrent rounds/scopes | identities, handles and output remain isolated | cross-session/cross-round delivery |
| R-01 | in-memory shutdown/restart boundary | no durability or replay claim; bounded ledger is session lifetime | inferred recovered completion/exactly-once |
| I-01 | ContextRef version/snapshot/unversioned inputs | strict wire and exact-scope gate pass | permission/expiry/redaction/destructive authorization claim |
| I-02 | typed AB delivery toward later CR consumer | exact response/round/progress facts are available | current batch claiming real CR/UI/TTS integration |
| F-01 | Adapter exception, stalled/raising close or slow/full output consumer | settled business truth plus bounded cleanup/request-local failure/backpressure | fake terminal, completion rewrite, global mutation or terminal drop |
| F-02 | formal capability off | existing text/Demo paths and stores are untouched | hybrid formal/legacy side effects |
| K-01 | Python/TypeScript shared fixture parity | both parsers accept/reject the same canonical cases | language-specific wire reinterpretation |
| K-02 | envelope and projection sequence domains | both domains validate independently | one sequence substituting for the other |
| K-03 | v1 compatibility | v1 source and tests remain unchanged/green | relabeling v1 progress as complete v2 |
| X-01 | committed Turn -> injected Agent/Harness -> typed Agent + progress output | deterministic fake vertical proves the bounded runtime | fake evidence called real Agent integration |
| X-02 | real Chat/Agent, D-031 and full Web voice route | explicitly deferred until branch reconciliation and real Adapter review | P2/Week 2/Web Alpha acceptance claim |

Every admission-time negative path asserts zero Adapter calls; post-dispatch invalid
Adapter output fails only that accepted request and produces no derived terminal.
Task, Tool, audio, Chat/history, notification and cancellation have no effect port in
this module.

## 6. Files and verification boundary

Implementation files:

- shared Python v2 schema and language-neutral WorkProgress fixture;
- formal Web TypeScript v2 replica and parity tests;
- new server-internal `agent_bridge_runtime.py` and focused tests;
- narrow invalid-fixture correction because non-empty ContextRef is now supported;
- this review record plus README/STATUS routing updates.

Explicit exclusions:

- `agent_ws_server.py` and `server/runtime/agent_adapter/*`;
- Scheduler, Task Core, AutoHarness and D-031 implementation/UI/i18n;
- real Agent/Harness Adapter, CR notification arbitration and full Web voice E2E;
- ContextRef permission/expiry/redaction policy, persistence and production auth;
- remote push, merge or changes to the user's D-031 worktree.

## 7. Review and evidence ledger

| Pass | State | Findings/fixes/evidence |
|---|---|---|
| Scoped Sol pre-review | `CONDITIONAL GO / FROZEN` | Eight mandatory boundaries in section 3 were incorporated before/during implementation. |
| Implementation self-review | `PASS AFTER FIXES` | Added scoped round single-owner binding, bounded source/request ledgers, strict Agent sequence/Unicode admission, attempt-parent verification and direct `KnownFact` enum validation. Removed an invented ContextRef logical-resource dedup restriction. |
| Cold complete-diff review | `PASS AFTER FIXES` | Re-read all 11 changed/untracked files after the final semantic fix against the request, repository rules, D-032/D-053, existing behavior and actual tests. Confirmed logical-source ordering, owner-loop/close waiter behavior, unambiguous IDs, zero-effect admission and explicit exclusions. |
| Scoped Sol post-review | `PASS AFTER FIXES` | Found and verified fixes for tracker registry loss, duplicate/reordered projection, unproven detail, cross-source over-ordering, producer replacement, terminal/cleanup blocking, delivery close race and Unicode admission. Sol independently ran compile/diff checks; its environment lacked pytest, so Python pytest evidence below is from the implementation environment. |
| Independent review | `PASS AFTER FIXES — EQUIVALENT` | The product `/review` command was unavailable. A separate cold reviewer agent inspected the complete diff and reran a 112-test Python affected subset, runtime 24/24, TypeScript 30/30 and formatting/diff checks. This substitute does not prove the excluded real integrations. |
| Current-branch integration review | `PASS AFTER FIXES` | Reconciled the complete candidate against the integrated D-031/AIO-B/CR-B branch and repeated the complete-diff cold review. It preserved current README/STATUS authority and fixed two observer-cancellation losses: a timed-out completion waiter can no longer cancel the retained request result, and a cancelled delivery waiter can no longer consume an arriving Agent/WorkProgress output. Deterministic regressions cover both scheduling windows. The prior independent review remains the D-053 independent pass; this integration review did not claim a second `/review`. |
| Automated verification | `PASS` | Current-branch Python affected regression passes 201/201; focused runtime passes 26/26 and shared v2 passes 38/38; TypeScript strict compile/parity passes 30/30. Cumulative frontend checks pass AIO-B 31/31, CR replica 9/9 and the complete TypeScript/Vite production build. Ruff format/check, scoped mypy, Prettier, Markdown links and `git diff --check` pass. The source candidate's earlier 187/187 and runtime 24/24 counts remain historical evidence. Scoped pytest runs disabled repository-wide plugin/coverage autoload because its collection is machine-expensive; test selection and assertions were unchanged. |
| Real integration evidence | `NOT IN SCOPE / OPEN` | Injected fakes do not prove the real Agent Adapter, D-031 integration, CR/UI/TTS consumption or complete Web voice path. |

The bounded WorkProgress v2/AB-B foundation is reconciled on `hx/0803_live_voice`.
It establishes strict shared contract parity and deterministic injected-Adapter
evidence only; it does not complete the first real P2 Agent compatibility route or
earn P2/Web Alpha replacement credit.
