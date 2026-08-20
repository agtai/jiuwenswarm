# Live Voice strict-review repair execution — 2026-08-20

> Status: **ACTIVE — 21/88 unique defects closed.** This is a user-routed,
> bounded D-060/D-062 parallel repair packet on the isolated strict-review
> branch. It grants no product-readiness, capability-completion or physical
> acceptance credit.

## 1. Authority, baseline and counting

- Integration worktree:
  `D:\XGG AI\openjiuwen\jiuwenswarm-review-20260819`.
- Activation baseline: `4661ed6d7db11048dad9d070cb9120fe35b049c4`.
- Canonical finding evidence:
  [strict-review revalidation](LIVE_VOICE_STRICT_REVIEW_REVALIDATION_2026-08-19.md).
- Queue size: 88 unique current defects. The audit has 89 active IDs because
  C3 aliases B42; B17 is an inactive duplicate alias of B13.
- Progress advances only when a unique defect meets the closure rule below.
  A code change, passing focused test or worker commit alone does not increment
  the numerator.
- Main is the only Integration Owner and integration-branch history writer.
  Each implementation worker owns one non-overlapping branch/worktree and may
  commit only its assigned files. Workers never push or integrate themselves.

## 2. Required repair and closure sequence

Every finding follows this exact sequence:

1. reproduce the current defect deterministically on the activation baseline;
2. freeze intended behavior, owned source/tests, exclusions and risk tier;
3. add a regression that fails for the original mechanism;
4. implement the minimum root-cause repair;
5. run applicable D-032 positive, negative, boundary, state, time/order,
   concurrency, retry/recovery, identity/isolation, failure/fallback,
   compatibility and real-seam evidence;
6. assert zero forbidden Agent, Tool, Task, audio/history, store and other-scope
   effects on every rejection/failure path;
7. independently review the complete module diff and repair findings;
8. integrate on the exact reviewed commit, rerun affected integration checks
   and only then mark the unique finding `FIXED`.

Deterministic barriers/events are required for races; timing-only sleeps do not
prove closure. Capacity repairs must separate releasable heavy state from the
anti-replay fence; unqualified LRU eviction is excluded. Cleanup timeout may
remain truthfully pending/retained but must never be reported as successful
close.

## 2.1 Session resume checkpoint

This is the only resume route for this repair packet. `STATUS.md` remains the
authority for mutable project priority and the numerator; this execution record
owns exact packet scope, evidence and candidate history. Do not create another
parallel handoff or remaining-work summary.

At the start of every new Session:

1. Open `D:\XGG AI\openjiuwen\jiuwenswarm-review-20260819` and run
   `git status --short --branch`, `git rev-parse HEAD`,
   `git branch --show-current` and
   `git rev-parse --abbrev-ref --symbolic-full-name "@{upstream}"`. A missing
   upstream is a valid result. Git is authoritative if this prose is stale.
2. Confirm that the integration branch is
   `codex/live-voice-strict-review-20260819`, then read `README.md`,
   `STATUS.md` `Current execution packet`, this checkpoint, §6 and §7. Read a
   closed wave record or the historical revalidation only for a disputed
   finding mechanism.
3. Preserve the current **21/88 closed, 67 remaining** count. The closed set is
   A2, A3, A4, A8, A11, A12, A16, A18, A20, A21, A23, A25, B2, B6, B7, B9,
   B10, B16, B41, C5 and L14. A8+B6 share SRR-06 and A2+B2 share SRR-10; each
   pair still counts as two unique defects.
4. No candidate is implemented or awaiting review. SRR-10/A2+B2 closed after an
   independent Tier-3 review signed
   `e97cee0bc17c8d2981d9e4f82d194a5148799a02` and Main applied its four
   reviewed source/test commits onto this branch as `ea55258ff`, `8ecd38267`,
   `90a5f17ad` and `b5e6dd6e7`. Its stale worker branch
   `codex/lv-srr10-stream-terminal` was never merged and must not be.
5. Activate one or more disjoint owner-scoped packets from §6. Freeze each
   packet from the latest integration branch and record its capability/module,
   risk tier, dependencies, scope, exclusions and acceptance before editing.
6. A worker owns only its own task branch in its own worktree. Main is the only
   Integration Owner and applies only reviewed source/test commits, in order,
   onto the integration branch. Any semantic conflict or repair edit creates a
   new candidate that requires review before integration credit.
7. Assign an independent reviewer who did not implement the packet. The
   reviewer reads the complete module diff cold and reruns the packet's focused
   and affected seams. Do not increment the numerator for a worker result or a
   focused green suite. A rejection leaves the numerator unchanged and returns
   the exact reproducible blocker to the same packet owner.
8. After integration, rerun the affected checks on the integration branch,
   inspect status and diff, update the ledger and STATUS, and commit one
   coherent closure record. Remote refs, `develop` and product acceptance
   remain excluded.

The last integrated defect-closure record before this documentation sync is
`b5e6dd6e7` (`fix(live-voice): settle terminal retirement failures`). A later
documentation-only HEAD is expected after this synchronization and does not
change implementation credit.

## 3. Wave 1 ownership record — CLOSED

### SRR-01 — C5 Task Store observation binding

- Capability/owner: Task Control Core/Store.
- Risk: Tier 3 authority and durability.
- Worker-owned source/tests:
  `jiuwenswarm/server/live_voice/task_store.py` and
  `tests/unit_tests/live_voice/test_persistent_task_core.py` only.
- Intended behavior: before any mutation, every Executor observation returned
  for an outbox item must match its exact task, attempt, executor identity and
  executor reference. A mismatch rejects the entire completion transaction.
- Acceptance: reproduce A-outbox/B-observation cross-binding; return one stable
  binding error; prove A, B, command/event/outbox/attempt and Executor effects
  are all unchanged; preserve valid completion, exact replay, transaction
  rollback and reopen behavior.
- Exclusions: no schema change, new Executor policy, outbox operation or
  reconciliation model.

### SRR-02 — A21 Agent-client payload privacy

- Capability/owner: Gateway Agent client/logging boundary.
- Risk: Tier 3 privacy/security.
- Worker-owned source/tests:
  `jiuwenswarm/gateway/routing/agent_client.py`,
  `jiuwenswarm/common/e2a/wire_codec.py`,
  `jiuwenswarm/server/ws_send.py`, and their existing focused test files only.
- Intended behavior: INFO/DEBUG logs expose only an allowlisted, content-free
  request/response summary; transcript/text/audio/credential/private markers
  never appear at any nesting, casing or separator variant. URI, address,
  object identity, exception/close reason and untrusted scalar values are also
  content-hidden across the real unary/stream codec seam; any correlation ref
  must use a process-temporary secret and never appear in task names as raw
  content.
- Acceptance: first demonstrate current transcript leakage with sentinel
  payloads; verify unary and streaming success/error logs, nested list/dict and
  malformed/private values; prove the original payload is not mutated and
  non-Live-Voice supported logging remains compatible. Cover connect/send/
  receive/close diagnostics, low-entropy ref enumeration, untrusted integers,
  common E2A success, fallback and inverse-error logs. Failure classification
  and legacy projection must not invoke hostile instance/class hooks; projection
  has one shared whole-graph depth/item budget and fails closed on cycles or
  aliases; invalid oversized scalar identifiers fail with one static public
  error before send. The real bounded WebSocket sender must log only static
  categories and counts on normal/fallback paths while preserving the existing
  protocol-compatible fallback frame.
- Exclusions: no global logging framework replacement, retention policy,
  protocol wire-body/schema change, streaming/TTS behavior or new product
  classifier.

### SRR-03 — B41 frontend development WebSocket privacy

- Capability/owner: Integrated Web development traffic privacy.
- Risk: Tier 3 privacy/security.
- Worker-owned source/tests:
  `jiuwenswarm/channels/web/frontend/devWsTrafficPrivacy.ts` and
  `jiuwenswarm/channels/web/frontend/tests/devWsTrafficPrivacy.test.mjs` only.
- Intended behavior: real `display_text` and `spoken_text`, including compact
  key variants and malformed JSON fallback text, are never persisted/logged.
- Acceptance: reproduce both leaks; validate structured and malformed paths,
  nested arrays/objects, casing/separator variants and non-sensitive metadata;
  run focused TypeScript/test commands and applicable build/static checks.
- Exclusions: no product telemetry schema, UI rendering or WebSocket protocol
  change.

### SRR-04 — B9 Voice–Task resolver field binding

- Capability/owner: Voice–Task Bridge.
- Risk: Tier 3 authority.
- Main-owned source/tests:
  `jiuwenswarm/server/live_voice/voice_task_bridge.py`, its focused tests and
  the existing product-composition registry integration test only.
- Intended behavior: every populated instruction, confirmation token and task
  ID is independently exact-span validated; conflicting/mutually exclusive
  fields fail closed before confirmation or Task/Tool effects.
- Acceptance: reproduce the mixed-field bypass, add malicious resolver
  combinations, preserve valid committed intent, and assert every forbidden
  effect is zero both at the Bridge and the real product-registry entry.
- Exclusions: no new natural-language classifier, vocabulary or Task operation.

### SRR-05 — B10 static bearer non-ASCII fail-closed behavior

- Capability/owner: P3 authenticated composition.
- Risk: Tier 3 authentication/security.
- Main-owned source/tests:
  `jiuwenswarm/server/live_voice/p3_authenticated_composition.py` and its
  focused tests.
- Intended behavior: invalid non-ASCII configured credentials fail at
  construction; non-ASCII candidates produce the existing typed
  unauthenticated result, never an uncaught `TypeError`.
- Acceptance: reproduce both cases, preserve constant-time comparison for
  supported credentials, and prove zero Store, Executor, authority and Task
  effects.
- Exclusions: no production authentication provider, token format expansion or
  credential migration.

Wave 1 files did not overlap. SRR-01/02/03 implementation workers did not serve
as their own independent reviewers; Main-owned SRR-04/05 also received
independent review. All five packets are closed in the §7 ledger.

## 4. Wave 2 ownership record — CLOSED

At activation, Wave 2 could overlap the final SRR-02 work because all four owner
surfaces below were disjoint from Wave 1 and from each other. A8 and B6
deliberately shared one packet because both defects converge on the same Harness
cleanup coordinator.

### SRR-06 — A8+B6 Harness terminal truth and bounded cleanup

- Capability/owner: Agent round Harness and terminal publication.
- Risk: Tier 3 terminal authority across Agent Bridge and Work Progress.
- Worker-owned source/tests:
  `jiuwenswarm/server/live_voice/jiuwenswarm_round_harness.py` and the existing
  Harness coverage in
  `tests/unit_tests/live_voice/test_agent_conversation_runtime.py` only.
- Intended behavior: business completion/cancellation and cleanup disposition
  are separate. A close failure never rewrites known completed or cancelled
  truth; an otherwise unknown round with a known close failure becomes failed.
  Cleanup has one total deadline, after which the business terminal is
  publishable while one shielded retained-cleanup owner remains observable as
  pending and can later converge.
- Acceptance: deterministic completed+close-failure,
  cancelled+close-failure, unknown+close-failure and never-returning `aclose`
  cases; bounded outer close, no orphan/unowned task, no duplicate terminal or
  Agent/Tool/Task/audio/history effect, and a second close converges after the
  retained cleanup completes.
- Exclusions: no EventEnvelope/shared protocol field, Agent/Bridge/Conversation
  Runtime redesign, Task/Tool cancellation policy, persistence or restart
  claim. Pending cleanup reuses the existing outer close/coordinator truth.

### SRR-07 — A3 batch-recognition canonical transcript

- Capability/owner: Batch Speech Provider boundary and recognition receipt.
- Risk: Tier 3 speech-event and opaque TurnCommit-receipt authority.
- Worker-owned source/tests: `jiuwenswarm/server/live_voice/batch_speech.py` and
  `tests/unit_tests/live_voice/test_batch_speech.py` only.
- Intended behavior: canonicalize Provider transcript once with `strip()` at
  the Provider boundary; the identical canonical value feeds the Provider
  result, final event, hash/receipt and claim. Empty or over-limit canonical
  text still fails closed.
- Acceptance: reproduce ASCII and Unicode surrounding-whitespace failure;
  preserve internal text; prove one canonical event/receipt, exact operation
  replay without a second Provider call, receipt claim/replay and zero partial
  capture/Agent/Tool/Task effects on rejection.
- Exclusions: no Unicode normalization, case/punctuation policy, speech schema,
  receipt format, streaming recognition or TTS change.

### SRR-08 — A20 Gateway all-owner shutdown

- Capability/owner: Gateway lifecycle and process-safe teardown.
- Risk: Tier 2 state, cancellation and recovery-sensitive lifecycle.
- Worker-owned source/tests: `jiuwenswarm/gateway/app_gateway.py` and one focused
  `tests/unit_tests/gateway/test_app_gateway_shutdown.py` module only.
- Intended behavior: teardown remains ordered but independently guards every
  owner. The first `BaseException` remains visible, later failures are recorded,
  and every later channel/scheduler/heartbeat/forward/client/restart-cleanup
  owner is attempted exactly once. Process restart occurs only after the
  required successful safe boundary.
- Acceptance: inject Web stop and each later phase failure; prove all remaining
  owners run once in order, the first error wins, later errors remain
  diagnosable, no restart/equivalent forbidden effect occurs after failed
  teardown, and a clean shutdown preserves existing behavior.
- Exclusions: no channel-internal stop repair, startup/configuration change,
  remote operation or new process/restart policy.

### SRR-09 — B7 critical-token successor index preservation

- Capability/owner: Critical Token protected-route authorization gate.
- Risk: Tier 3 authorization/authority.
- Main-owned source/tests:
  `jiuwenswarm/server/live_voice/critical_token_safety.py` and
  `tests/unit_tests/live_voice/test_critical_token_safety.py` only.
- Intended behavior: releasing an old commit removes an interaction's active
  clarification or authorization index only when that index still maps to the
  exact released identity. A successor remains active and once-only; old
  authority remains unusable.
- Acceptance: reproduce clarification and authorization replacement followed
  by old release; prove the successor dispatches exactly once, old dispatch is
  rejected with zero protected effects, another interaction is unchanged and
  release/replay ordering remains linearized under the existing lock.
- Exclusions: no classifier/token policy, capacity/tombstone repair, persistent
  authorization, schema or protocol change.

Wave 2 writer leases were owner-scoped. No worker reviewed its own lane, and
Main integrated only exact independently signed commits before advancing the
numerator. All four packets are closed in the §7 ledger.

## 5. Wave 3 ownership record — CLOSED

Wave 3 was frozen from integration baseline `9741b805c`. Its three writer
surfaces are disjoint. A2 and B2 deliberately share one packet because both are
the same Adapter queued-terminal retirement invariant. The prior A7 dependency
on SRR-06 is now satisfied; A7 is unactivated in §6 and must start from the
latest integration branch when routed.

### SRR-10 — A2+B2 Streaming Speech queued-terminal retirement

- Capability/owner: `OpenAIStreamingSpeechProvider` recognition/synthesis
  terminal cancellation, sensitive-queue release and transport cleanup.
- Risk: Tier 3 terminal authority and sensitive transcript/PCM lifecycle.
- Worker-owned source/tests: `jiuwenswarm/server/live_voice/openai_streaming_speech.py`
  and `tests/unit_tests/live_voice/test_openai_streaming_speech.py` only.
- Intended behavior: after FINAL/COMPLETED has been published but not dequeued,
  exact local cancel reaps conformance terminal state, clears the sensitive
  queue and retires the exact session without issuing a new Provider cancel or
  changing terminal truth. Active cancel remains unchanged; unknown, stale,
  wrong-generation and already-retired references still reject.
- Acceptance: deterministic Event/queue barriers reproduce both races; cover
  dequeue-vs-cancel and duplicate cancel linearization, done and retained
  transport cleanup, maximal queued transcript/PCM release, neighboring-stream
  isolation, no degradation/business effects and the real Gateway route seams.
- Exclusions: no strict-conformance or route source change, new cancel ACK,
  identity/capacity policy, timeout attribution, queue limit, protocol/schema
  or physical Provider claim.
- Candidate state — **CLOSED, 2 unique defects credited:** independent Tier-3
  review signed `e97cee0bc17c8d2981d9e4f82d194a5148799a02` after a cold read of
  the complete four-commit chain, and Main applied the four reviewed
  source/test commits onto the integration branch as `ea55258ff`, `8ecd38267`,
  `90a5f17ad` and `b5e6dd6e7`, byte-identical to the signed candidate. The
  worker branch `codex/lv-srr10-stream-terminal` was not merged.
- Reviewer-confirmed mechanism: on baseline `3d488e8c3` the candidate tests are
  deterministically RED, including conformance `RECOGNITION_ALREADY_TERMINAL`
  and `SYNTHESIS_ALREADY_TERMINAL` violations. A queued-terminal cancel used to
  re-issue a Provider cancel against an already terminal stream, so the raised
  violation left the sensitive transcript/PCM queue, `partial_text` and the
  session map entry permanently retained.
- Non-blocking observations routed to the owning boundary, not repaired here:
  (1) in `_close_serialized`, an ordinary terminal-retirement failure now
  surfaces as the authoritative cleanup failure while neighbouring
  socket/stream/cancel failures remain filtered to process control only — an
  intentional asymmetry frozen by the `[RuntimeError]` case;
  (2) `_adopt_claimed_terminal_*_retirement` does not pre-drain the queue the
  way `_start_queued_*` does, so its boundedness rests on the `_put_bounded`
  wait budget rather than an immediate drain;
  (3) the `removed_sessions` guard skips `reap_terminal()` when both maps are
  empty, which is safe because both rollback paths reap on their own.

### SRR-11 — A4 Batch synthesis event-loop-safe resampling

- Capability/owner: `OpenAICompatibleBatchSpeechProvider` canonical PCM/WAV
  resampling boundary.
- Risk: Tier 2 event-loop responsiveness and cancellation/recovery behavior.
- Dependency: preserve integrated A3 canonical transcript behavior from
  `ec43b0423` and start from the Wave 3 baseline above.
- Worker-owned source/tests: `jiuwenswarm/server/live_voice/batch_speech.py` and
  `tests/unit_tests/live_voice/test_batch_speech.py` only.
- Intended behavior: offload the existing bounded resampling helper at the
  async Provider boundary without changing its algorithm, bytes, rounding,
  validation or error reasons. Heartbeat/deadline/cancel can progress while the
  worker runs; caller cancellation publishes no late result/event/receipt.
- Acceptance: a thread-identity RED proves the baseline executes on the event
  loop; deterministic barriers prove heartbeat and cancellation; maximum input,
  same-rate and 24→48/24→16 output remain byte exact, failures remain typed,
  and a later valid synthesis succeeds without leaked worker effects.
- Exclusions: no DSP/quality/sample-rate policy, global executor/semaphore,
  HTTP, schema/receipt, A3 text, streaming speech or physical latency change.

### SRR-12 — A18 cold schedule execution-agent initialization

- Capability/owner: `AgentWebSocketServer._handle_schedule_request` execution-
  agent capture before `schedule.create` and `schedule.run` mutation.
- Risk: Tier 3 Agent identity, scheduled-Task authority and cold-start
  singleflight.
- Worker-owned source/tests: `jiuwenswarm/server/agent_ws_server.py` and
  `tests/unit_tests/agentserver/test_schedule_request.py` only.
- Intended behavior: create/run await the existing `ensure_instance()` before
  target pin or service mutation, reject exceptions or `None` with zero
  schedule/Task/Store/pin effects, and pass the exact ensured object downstream.
  Warm access and existing DeepAdapter singleflight remain authoritative;
  read-only, cancel, issue-watch and other actions do not gain initialization.
- Acceptance: deterministic cold create/run RED, warm and same-agent concurrent
  singleflight, failure/None then valid retry, ordering before pin/mutation,
  owner/project/session isolation and affected DeepAdapter/AutoHarness/Gateway
  seams with explicit zero forbidden effects.
- Exclusions: no Agent facade/DeepAdapter, AgentManager, scheduler Store/schema,
  AutoHarness execution, project executor, WebSocket protocol or persistence
  migration change.

Wave 3 applies all relevant D-032 P/N/B/S/T/C/R/F/I/K/X dimensions recorded in
the acceptance above. Worker commits alone receive no credit; independent
Tier-2/3 review and integration verification remain mandatory.

## 5.4 Wave 4 ownership record — CLOSED

Wave 4 started from integration commit `4923f05cd` after the first eight unique
closures. Its three source/test ownership sets are disjoint from each other and
from the still-running Wave 2/3 returns. A worker may not broaden a packet into
shared schema, classifier or another module owner without a new checkpoint.

### SRR-13 — A11 Persistent Task Core blocking-store isolation

- Capability/owner: `PersistentTaskCore` asynchronous outbox delivery and
  reconciliation orchestration around the synchronous SQLite Task Store.
- Risk: Tier 3 durable Task authority, event-loop availability and restart
  recovery.
- Dependency: preserve integrated SRR-01/C5 exact Executor-observation binding
  and zero-write rejection semantics.
- Worker-owned source/tests: `jiuwenswarm/server/live_voice/persistent_task_core.py`,
  `tests/unit_tests/live_voice/test_persistent_task_core.py` and the affected
  timing assertions in
  `tests/unit_tests/live_voice/test_p3_authenticated_composition.py`. The
  composition product source remains excluded; its tests must wait for durable
  Store/settlement truth rather than treating Executor entry as Store commit.
- Intended behavior: execute each blocking Store operation through the existing
  blocking runner or an equivalent owner-scoped thread boundary while keeping
  async Executor calls on the owning event loop. Cancellation cannot publish a
  partial authority transition or let a late blocking result mutate a new
  attempt/claim owner.
- Acceptance: deterministic Store barriers reproduce the baseline heartbeat and
  barge delay; positive delivery/reconciliation remains exact; cancellation at
  every Store/Executor boundary, competing Task/scope work, SQLite
  serialization, reopen recovery, mixed-observation rejection and exact replay
  prove no duplicate dispatch, terminalization or cross-attempt effects.
- Exclusions: no Store schema/migration, global executor policy, outbox lease or
  retry policy, Executor protocol, C5 binding relaxation or physical latency
  claim.

### SRR-14 — A12 Code Executor persisted user-cancel terminal truth

- Capability/owner: `ProjectCodeExecutor` attempt execution and journal-backed
  cancellation terminalization.
- Risk: Tier 3 Task terminal authority, retry lineage and crash/restart truth.
- Worker-owned source/tests: `jiuwenswarm/server/live_voice/project_code_executor.py`
  and `tests/unit_tests/live_voice/test_project_code_executor.py` only.
- Intended behavior: an explicit persisted user cancel that is observed and
  acknowledged settles exactly once as `CANCELLED`; `INTERRUPTED` remains
  reserved for shutdown, lost ownership and other non-user interruption causes.
- Acceptance: deterministic barriers order journal persistence, in-memory
  signal and executor observation; assert one terminal event, cancellation ACK
  and correct retry-readiness across both orderings and reopen. Shutdown/lost-
  owner controls remain `INTERRUPTED`, neighboring attempts are unchanged and
  stale/replayed cancel produces zero new effects.
- Exclusions: no journal schema, new terminal enum/retry policy, process
  supervision, Task Store protocol or unrelated timeout/capability behavior.

### SRR-15 — A16 Dedicated Media post-reservation cancellation cleanup

- Capability/owner: Dedicated Media uplink socket leaf after exact authority
  reservation and attach.
- Risk: Tier 3 media authority, socket/child lifecycle and cancellation truth.
- Worker-owned source/tests: `jiuwenswarm/gateway/live_voice/dedicated_media_route.py`
  and `tests/unit_tests/gateway/test_dedicated_live_voice_media_route.py` only.
- Intended behavior: one idempotent outer cleanup boundary owns every
  post-reservation receive, detach, protocol-error and binary-ACK send. Caller
  cancellation remains authoritative only after the exact session is closed,
  socket closure is attempted once and receive/speech/EOT children are settled
  or truthfully retained.
- Acceptance: deterministic send barriers cancel separately at malformed-text
  detach, non-detach text, invalid message-type detach and binary ACK; exact
  reservation usage returns to zero, socket/child calls are once-only, no late
  ACK/audio/history/Task/Tool effect appears, another lease is unaffected and a
  later valid route succeeds. Include process-control, cleanup-error and
  duplicate-cancel orderings without swallowing the authoritative exception.
- Exclusions: no media schema/codec, binding/capacity policy, downlink behavior,
  Speech semantics, Provider/device change or physical transport claim.

Wave 4 applies all relevant D-032 P/N/B/S/T/C/R/F/I/K/X dimensions recorded in
the acceptance above. Worker commits alone receive no credit; independent
Tier-3 review and integration verification remain mandatory.

## 5.5 Wave 5 ownership record — CLOSED

### SRR-16 — B16 P3 control manifest truth

- Capability/owner: natural-language P3 task-intent rejection and
  product-composition evidence.
- Risk: Tier 3 authority and diagnostic-truth boundary.
- Main-owned source/tests:
  `jiuwenswarm/server/live_voice/product_composition_registry.py` and
  `tests/unit_tests/live_voice/test_product_composition_registry.py` only.
- Intended behavior: a rejected natural-language task intent never fabricates
  formal authority, an open activation lease or an observed P3 runtime. Its
  manifest contains only unavailable/disabled facts; successful intent and
  confirmation paths retain their existing real formal manifest.
- Acceptance: first reproduce the fabricated formal manifest for missing or
  invalid bearer, structural-validation, resolver and absent pending-record
  failures that return through `_intent_rejected_result`. Assert unavailable
  reason/evidence IDs, zero confirmation consumption, Store/Executor/Agent/
  Task/Tool mutation and no retained activation lease. Preserve authenticated
  clarification/dispatched success, exact replay and content-free errors.
  Cover another session and registry stop without introducing a shared schema
  or classifier.
- Exclusions: no confirmation/mutation/query result semantics,
  product-composition contract/schema change, authentication or confirmation
  policy, Task operation, generation/capacity cleanup, query-lock redesign,
  frontend behavior or new evidence vocabulary.

## 5.6 Wave 6 ownership record — CLOSED

Wave 6 started from candidate `9921e543208c10dab9d5ee01808823ce97e3eb5e`.
At activation that baseline included the then-pending SRR-16/B16 candidate, but
the two packets had no source or test ownership overlap. Both are now closed.

### SRR-17 — A25 P3 confirmation durable capacity and restart recovery

- Capability/owner: durable P3 confirmation admission and replay authority.
- Risk: Tier 3 durability, authorization and restart recovery.
- Worker-owned source/primary tests:
  `jiuwenswarm/server/live_voice/p3_confirmation.py` and
  `tests/unit_tests/live_voice/test_p3_confirmation.py`. Existing product
  forwarder/composition consumer tests are affected read-only evidence only.
- Intended behavior: within the same `BEGIN IMMEDIATE` transaction and before
  admitting a new confirmation, remove expired or consumed heavy records while
  preserving every live confirmation. If the existing once-only replay
  contract requires consumed identity after cleanup, retain only a minimal,
  bounded durable replay fence; it may identify an exact replay but must never
  let an old token authorize a new mutation.
- Acceptance: at capacity one, consumed then new and expired then new admission
  both recover capacity, while a live row still rejects the newcomer. Reopen
  preserves live authority, cleanup and exact replay fencing; concurrent
  independent issuers linearize so capacity is never exceeded. Injected cleanup
  or insert failure rolls the whole transaction back. Invalid, stale, evicted
  and mismatched confirmation paths have zero new confirmation, Task, Tool,
  Agent, Executor, audio/history or other-scope authority effects, and existing
  supported replay/forwarder consumers remain compatible.
- Exclusions: no Product Registry or forwarder policy, token format or TTL
  policy, external database migration, Task mutation semantics, new shared
  schema or shared capacity/replay policy. Any required schema or shared-policy
  change must be re-scoped with Main before implementation.

SRR-17 applies the complete relevant D-032 P/N/B/S/T/C/R/F/I/K/X matrix. Its
worker cannot independently sign the module, and no closure credit is recorded
before independent Tier-3 review and exact integration verification.

## 5.7 Wave 7 ownership record — CLOSED

### SRR-18 — A23 Web activation durable pending ownership

- Capability/owner: Integrated Web product activation for submit, barge-in and
  presentation acknowledgement operations.
- Risk: Tier 3 durable authority, retry identity and network-effect boundary.
- Main-owned source/tests:
  `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productWebActivation.ts`
  and
  `jiuwenswarm/channels/web/frontend/tests/productWebActivation.test.mjs` only.
- Intended behavior: an operation becomes pending only after its exact request
  is frozen and its durable checkpoint succeeds. UTF-8 size rejection,
  serialization or journal failure leaves no result-less pending identity and
  performs no network, media, presentation or Task effect; the same identity
  can be retried only under the existing exact replay contract.
- Acceptance: deterministically reproduce submit, barge-in and presentation
  ghost entries at the multibyte byte boundary and injected checkpoint failure;
  assert zero retained pending/result entries and zero send/Agent/Task/media/
  presentation effect, then retry a valid exact operation successfully. Cover
  concurrent identical and conflicting callers, pre-write journal rejection,
  after-write ambiguous failure, close/session replacement fencing and
  existing successful replay.
  A checkpoint rejected before durable acceptance must permit retry; an
  ambiguous storage write that is durably recoverable remains owned by the
  existing journal recovery path and must not be reissued under a new identity.
  Preserve request bytes, operation ordering and wire protocol.
- Exclusions: no backend/Gateway change, journal schema or storage-provider
  redesign, retry classifier, media/P1 ownership, Task policy, session rollover
  policy, UI component change or new protocol field.

Wave 7 applied all relevant D-032 P/N/B/S/T/C/R/F/I/K/X dimensions recorded in
the acceptance above. Persistence restart is represented by the existing
journal reconstruction seam; physical browser/network acceptance remains a
candidate-level exclusion.

## 5.8 Wave 8 ownership record — CLOSED

Wave 8 started from integration commit
`9ef6159dd9522e3b893a6b60f12b499401171645` and owns one literal-only
diagnostic repair that does not overlap the active authority or durability
packets.

### SRR-19 — L14 schedule owner-scope diagnostic

- Capability/owner: Auto Harness scheduled-task admission diagnostics for the
  recurring `create_scheduled_task` and one-time `run_task` public service
  entrypoints.
- Risk: Tier 1 ordinary service-output correction. The two existing rejection
  branches, validation order, scheduler/Store/Task authority and all state,
  concurrency, retry and persistence semantics remain unchanged; only their
  mojibake user-visible error text is corrected.
- Owned source/tests:
  `jiuwenswarm/agents/harness/common/auto_harness/service.py` and
  `tests/unit_tests/auto_harness/test_schedule_task_service.py`; this execution
  record is the only documentation surface.
- Intended behavior: an explicitly supplied invalid `owner_scope` returns
  exactly `code=TASK_SCOPE_REQUIRED` and
  `error=调度任务缺少服务端所有者范围` from both public entrypoints before any
  scheduler, Store, Task or execution-context effect.
- Acceptance: first freeze both public paths as deterministic RED against the
  old mojibake literals, including complete zero-effect assertions; replace
  only the two matching strings; then run the focused cases, the complete
  schedule service module and scoped static/diff checks. Existing positive and
  compatibility coverage supplies Tier-1 P/K evidence; this repair directly
  owns N and zero-effect evidence. B/S/T/C/R/I/F/X are unchanged and therefore
  out of scope rather than artificially expanded.
- Exclusions: no owner-scope validator, scheduling/admission, idempotency,
  scheduler/Store/Task, persistence, schema, protocol or error-code change; do
  not alter the separate `幂等任务缺少服务端所有者范围` diagnostic.

## 6. Queued repair programs

The 67 remaining unique defects are the unactivated defects below; no
candidate is in flight. These groups are not worker write authority. Each
activation removes its IDs from this queue and freezes smaller owner-specific
packets before editing.

- Generation/successor/authority cleanup (**13**): B12, B13, B14, B18, B32,
  B36, B37, B38, B39, D2, L19, L20 and L21. B17 remains an inactive alias of
  B13.
- Cancellation/teardown/retained cleanup (**9**): A7, A19, A22, B21, B23,
  B24, D1, D3 and L7.
- Capacity/lifetime/replay: A1, A5, A6, A9, A13, A15, A17, B4, B11,
  B42, L5 and L18 (**12**). C3 remains an active audit-ID alias of B42 and
  adds no unique defect.
- Event-loop, lock and filesystem responsiveness (**4**): A14, B15, B25 and
  B27.
- Protocol/state/compatibility (**29**): B1, B3, B5, B8, B19,
  B20, B22, B28, B29, B30, B33, B34, B35, B40, L1, L2, L3, L4, L6, L8,
  L9, L10, L11, L12, L13, L15, L16, L17 and L22.

The queue arithmetic is `13 + 9 + 12 + 4 + 29 = 67`, which is the complete
remainder now that A2+B2 closed. By historical family the same remainder is
11 A, 32 B, 21 L and three D findings.

The queue excludes the already fixed A10, A24, B31 and L23; superseded B26;
and rejected C1, C2, C4 and C6–C13. New product policy, classifier, shared
schema/migration or another unrecorded module owner requires an explicit scope
and risk checkpoint before implementation.

## 7. Wave progress ledger

| Checkpoint | Closed unique defects | State |
|---|---:|---|
| Activation | 0/88 | Wave 1 packets frozen; no implementation credit yet |
| SRR-04 / B9 | 1/88 | `6b219bd39` + `d47ef7e58`; mixed-field and wrong-span regressions, real pending-token attack with zero confirmation/Task/Tool/ledger effects; 80 Bridge + 150 registry tests; independently signed |
| SRR-05 / B10 | 2/88 | `9b5b9286e` + `5a0d04917`; typed candidate/config failure, environment-factory zero construction and supported ASCII `compare_digest`; 101 module tests; independently signed |
| SRR-03 / B41 | 3/88 | `b200feff7` + `64236924a`; structured, malformed and separator-variant speech fields fail closed before development WebSocket persistence; focused/strict TypeScript 33/33, Prettier, `tsc` and Live Voice Vite build pass; independently signed |
| SRR-01 / C5 | 4/88 | `ec2f7224b` + `c8f858dad`; exact four-field Executor-observation binding before first Store write, real Core mixed-observation failure with zero cross-task effects, reopen retry and replay; 219 module tests; independently signed |
| SRR-09 / B7 | 5/88 | `4f62a0d82` + `31dec8c7c`; exact-ID release preserves successor clarification/authorization across both orderings and a deterministic RLock race while old authority has zero effects; 60 module tests; independently signed |
| SRR-07 / A3 | 6/88 | `ec43b0423`; Provider-boundary canonical transcript is shared exactly by result, event, receipt, hash and claim; ASCII/Unicode boundaries, rejection zero effects, concurrent/later replay and real Gateway/product consumers verified; 58 module + 18 consumer tests; independently signed |
| SRR-12 / A18 | 7/88 | `3f746fd48`; cold create/run await the existing Agent singleflight before target pin or mutation, while exception/None fail closed and retry succeeds without stale effects; 28 handler/DeepAdapter + 212 affected tests; independently signed |
| SRR-11 / A4 | 8/88 | `c255ddcae`; bounded batch audio resampling runs off the event-loop thread without changing DSP bytes or typed failures; deterministic heartbeat/cancel barriers, late worker completion/error containment, 61 module + 14 consumer tests and repeated scheduling probes independently signed |
| SRR-14 / A12 | 9/88 | `bafab7c91`; a durable cross-adapter user cancel observed after normal Agent return now settles exactly as `CANCELLED`, while shutdown/heartbeat/lost-owner interruption remains `INTERRUPTED`; isolated patch zero effects, exact replay, reopen, 100 module tests and independent Tier-3 review passed |
| SRR-15 / A16 | 10/88 | `58121cb70` + `0644edb14` + `75b26f7fc`; every uplink media send/receive descriptor and post-parse cancellation/process-control boundary now closes the exact session/socket and settles speech/EOT/cleanup ownership without replacing the primary failure; only pre-boundary legal audio/ACK effects remain, a successor route stays usable, 134 leaf/registration tests pass under asyncio debug, and independent Tier-3 review signed the final candidate |
| SRR-13 / A11 | 11/88 | `0c7db2994` + `870cb993f` + `73b308362`; every synchronous Task Store operation used by async drain/reconcile now runs off the event-loop while one retained owner survives repeated caller cancellation. The first caller cancellation wins ordinary worker/release failure, process-control and inner cancellation remain authoritative, exact claims are released or durably recoverable, and restart/successor delivery remains once-only; 12 focused asyncio-debug cases plus 231 Core and 101 composition tests passed, and independent Tier-3 review signed the final candidate |
| SRR-16 / B16 | 12/88 | `90865abd4`; every natural-language P3 rejection now reports authority and P3 control as unavailable with package-only/no-runtime evidence instead of fabricating a trusted lease or observed runtime. Invalid bearer/structure, missing binding, resolver failure, duplicate/concurrent replay, other-session, stop and restart probes retain zero forbidden effects; 151 registry + 47 real AgentServer route tests passed after independent Tier-3 review and integration |
| SRR-17 / A25 | 13/88 | `09d2239ff`; consumed and expired P3 confirmations are atomically compacted into a bounded durable replay fence, so only live authority consumes capacity. Exact retained replay and stable expiry remain truthful, evicted tokens never authorize, concurrent reopened issuers cannot exceed capacity, cleanup/insert failure rolls back without partial reclamation, and all forbidden Task mutations stay zero; 45 primary + 349 affected tests passed after independent Tier-3 review and integration |
| SRR-18 / A23 | 14/88 | `3c85728fd`; submit, barge-in and presentation-ACK operations are frozen and durably checkpointed before pending retention or completed-replay eviction. UTF-8/serialization/checkpoint rejection leaves no ghost authority or network/Agent/Task/media/presentation effects, exact concurrent/restart replay remains once-only, and the 128-entry boundary preserves the old replay until durable successor admission; 90 focused tests plus full candidate/baseline Integrated Web comparison passed after independent Tier-3 review |
| SRR-19 / L14 | 15/88 | `7f9dac8fe`; both public scheduling entry points now return the exact UTF-8 owner-scope diagnostic with the existing `TASK_SCOPE_REQUIRED` code. Eight invalid-scope cases prove zero Store, scheduler and retained execution-context effects; the full auto-harness suite passed 129/129 under the Tier-1 literal-only boundary |
| SRR-08 / A20 | 16/88 | `cf2d1a795`…`5aa2bb18c`; Gateway teardown now attempts every owner in order after failures, preserves chronological first-failure/caller-cancellation truth, keeps public diagnostics content-free, blocks restart across failed cleanup, and retains exact Feishu/Xiaoyi dynamic owner identity at registration rather than depending on fallible shutdown discovery. Descriptor/process-control, snapshot+pop+unregister, registry-only, hostile exception and clean-retry matrices pass; 90 focused shutdown + 66 ACP lifecycle tests passed after independent Tier-2 review and integration |
| SRR-02 / A21 | 17/88 | `4567becf3`…`4b08240dc`; Agent-client, E2A codec and WebSocket-send diagnostics are content-free across unary/stream success, failure, fallback and reconnect cleanup. Hook-free physical classification, a whole-graph projection budget and strict UTF-8 preflight prevent hostile objects, oversized identifiers, cycles/aliases and lone surrogates from reaching logs, public exception contents or transport sends while preserving supported OutputSchema/E2A/legacy wire behavior; 142 focused plus 61 direct and 292 additional consumer tests passed after independent Tier-3 review |
| SRR-06 / A8+B6 | 19/88 | `a9e3d6ab8`…`5affa2c8c`; Harness now separates business terminal truth from stream-cleanup disposition, retains one general Awaitable cleanup owner through deadline/cancellation, and preserves terminal ownership across startup and direct-cancel races. Real terminal-owner cancellation propagates without fabricated terminal/_END; public close adopts its abandoned stream cleanup exactly once, remains pending while blocked, and removes only the settled abandoned record. Known completed/cancelled truth survives cleanup failure, unknown+failure becomes failed, and normal rounds remain isolated; 99 Harness + 79 consumer tests and a 10-run race probe passed after independent Tier-3 review |
| SRR-10 / A2+B2 | 21/88 | `ea55258ff`…`b5e6dd6e7`; a FINAL/COMPLETED that was published but not yet dequeued now retires locally on exact cancel — sensitive transcript/PCM queue released, `partial_text` cleared, session and transport converged — without issuing another Provider cancel or rewriting terminal truth. Active cancel is unchanged, and unknown, stale, wrong-generation and already-retired references still reject. Dequeue-vs-cancel and duplicate cancel linearize on one synchronous claim so only one winner reports success; caller cancellation mid-retirement leaves exactly one retained owner genuinely pending instead of a fabricated completion; provider close keeps cleaning neighbouring sessions, transports, queues, maps and owners through ordinary, cancellation and process-control failures while preserving chronological first-failure truth and content-free identity; reap and transport cleanup stay once-only. Independent Tier-3 review reproduced the defect on baseline `3d488e8c3` — candidate tests RED with conformance `RECOGNITION_ALREADY_TERMINAL`/`SYNTHESIS_ALREADY_TERMINAL` violations — then passed 94 provider and 155 affected conformance/route cases under asyncio debug, with the one disclosed pre-existing route failure byte-identical on baseline, candidate and integration, zero new Ruff findings and unchanged formatting |

### 7.1 Closed-fix revalidation entrypoints

Run these from the repository root with the repository's configured Python and
Node environments. The ledger above owns the last accepted counts; later tests
may increase collection counts, so require zero new failure rather than
hard-coding an old total. A regression reopens the affected finding until its
mechanism and integration seam are reviewed again.

| Closed finding(s) | Primary revalidation surface |
|---|---|
| C5, A11 | `python -m pytest tests/unit_tests/live_voice/test_persistent_task_core.py tests/unit_tests/live_voice/test_p3_authenticated_composition.py --no-cov` |
| A21 | `python -m pytest tests/unit_tests/gateway/test_agent_client.py tests/unit_tests/e2a/test_wire_codec.py tests/unit_tests/agentserver/test_ws_send.py --no-cov --asyncio-debug` |
| B41 | From `jiuwenswarm/channels/web/frontend`: `npm run test:live-voice-gateway-batch-speech` |
| B9, B16 | `python -m pytest tests/unit_tests/live_voice/test_voice_task_bridge.py tests/unit_tests/live_voice/test_product_composition_registry.py --no-cov` |
| B10 | `python -m pytest tests/unit_tests/live_voice/test_p3_authenticated_composition.py --no-cov` |
| B7 | `python -m pytest tests/unit_tests/live_voice/test_critical_token_safety.py --no-cov` |
| A3, A4 | `python -m pytest tests/unit_tests/live_voice/test_batch_speech.py --no-cov --asyncio-debug` |
| A18 | `python -m pytest tests/unit_tests/agentserver/test_schedule_request.py --no-cov` |
| A12 | `python -m pytest tests/unit_tests/live_voice/test_project_code_executor.py --no-cov --asyncio-debug` |
| A16 | `python -m pytest tests/unit_tests/gateway/test_dedicated_live_voice_media_route.py --no-cov --asyncio-debug` |
| A25 | `python -m pytest tests/unit_tests/live_voice/test_p3_confirmation.py --no-cov` |
| A20 | `python -m pytest tests/unit_tests/gateway/test_app_gateway_shutdown.py tests/unit_tests/gateway/test_app_gateway_acp.py --no-cov --asyncio-debug` |
| A8, B6 | `python -m pytest tests/unit_tests/live_voice/test_agent_conversation_runtime.py --no-cov --asyncio-debug` |
| A2, B2 | `python -m pytest tests/unit_tests/live_voice/test_openai_streaming_speech.py --no-cov --asyncio-debug` |
| L14 | `python -m pytest tests/unit_tests/auto_harness/test_schedule_task_service.py --no-cov` |
| A23 | From `jiuwenswarm/channels/web/frontend`: `npm run test:live-voice-integrated-web`; require the Product Web activation cases to pass and compare any full-suite failure with the disclosed mounted-panel baseline below |

Known baseline conditions must be disclosed, not converted into candidate
credit:

- The full Integrated Web diagnostic has one unchanged mounted-panel failure at
  `tests/liveVoiceIntegratedRoutePanelMounted.test.mjs:7342` (`late
  presentation was not acknowledged`). SRR-18 reproduced the same failure on
  candidate and integration baseline; its focused Product Web activation suite
  remains the A23 closure oracle.
- SRR-10's related route set has one pre-existing fake-provider cancellation
  failure at `tests/unit_tests/gateway/test_streaming_synthesis_route.py:1837`
  (`test_cancel_api_caller_cancel_retries_cleanup_then_rethrows`), outside its
  two owned files. Independent review compared baseline `3d488e8c3`, the signed
  candidate and the integration result: same test, same assertion and a
  byte-identical failure trace on all three. A new or changed failure there may
  not be waived.
- Existing Authlib deprecation and third-party `pysbd` SyntaxWarning output is
  not repair credit. Use the packet's recorded warning handling only when the
  same environment blocks collection, and report it explicitly.
- `app_gateway.py` retains 13 pre-existing whole-file Ruff findings and broad
  formatter drift. SRR-08 passed scoped Ruff, test-file format, compile and diff
  checks; do not claim an unqualified whole-file lint/format PASS or introduce
  unrelated mechanical churn during revalidation.

## 8. Global exclusions

No remote update, `develop` integration, production authentication/tenancy,
public deployment, provider/device configuration, physical product acceptance,
new product policy, new classifier, schema migration or broad unrelated cleanup
is included. P3-2 remains frozen under D-087 and resumes only after this
user-routed repair packet closes or is explicitly re-routed; no P3-2
implementation credit is claimed here.
