# Live Voice strict-review repair execution — 2026-08-20

> Status: **ACTIVE — 31/88 unique defects closed.** This is a user-routed,
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
3. Preserve the current **31/88 closed, 57 remaining** count. The closed set is
   A1, A2, A3, A4, A6, A8, A11, A12, A13, A16, A18, A20, A21, A23, A25, B2, B4,
   B6, B7, B9, B10, B12, B13, B14, B16, B36, B41, C5, L14, L20 and L21. A8+B6 share
   SRR-06, A2+B2 share SRR-10, B12+B13+B14 share SRR-20, B36+L20+L21 share
   SRR-21 and A6+B4 share SRR-22; each shared packet still counts one unique
   defect per finding.
4. No candidate is implemented or awaiting review. Wave 10 closed with
   SRR-22/A6+B4 at `935a4f74e`, SRR-23/A13 at `1c860f980` and SRR-24/A1 at
   `05b59e317`; all three worker branches were left unmerged and must stay that way. No closure credit
   is granted before an independent reviewer who did not implement a packet
   passes its complete module diff.
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

## 5.9 Wave 9 ownership record — CLOSED

Wave 9 is frozen from integration baseline `c4301ef98`, the SRR-10 closure
record. Its two writer surfaces are disjoint: one backend Python module and one
frontend TypeScript pair. Both packets come from batch 1 of the historical
revalidation's highest-priority ordering ("privacy and authority integrity"),
which that report requires before reliability-only work.

B18, B32, B37, B38, B39, D2 and L19 belong to the same historical family but are
deliberately excluded from Wave 9. `productP1VoiceRoute.ts` and
`LiveVoiceIntegratedRoutePanel.tsx` are being modified in parallel on
`agtai/hx/0819_live_voice_p1p2`, so B32, L19, B37, B38 and B39 must be routed
after that branch merges; B18 and D2 stay unactivated in §6.

### SRR-20 — B12+B13+B14 composition registry generation authority

- Capability/owner: `ProductCompositionRegistry` progress-generation admission,
  higher-generation P2 replacement cleanup and post-gate failure release.
- Risk: Tier 3 authority and generation integrity. This umbrella does not
  propagate Tier 3 to later repairs in the same file.
- Worker-owned source/tests:
  `jiuwenswarm/server/live_voice/product_composition_registry.py` and
  `tests/unit_tests/live_voice/test_product_composition_registry.py` only.
- Intended behavior:
  - B12 (`:681,1077-1107,7971`): progress-generation admission retains an
    owner-scoped monotonic fence independent of the heavy route state, so a
    generation evicted at capacity can never activate again.
  - B13 (`:1872,2008-2009`): higher-generation P2 replacement performs the same
    exact voice-origin drop and critical-token release that normal close
    performs at `:5862-5872,8787-8796` before the successor is published, and
    pairs with the conditional index release B7/SRR-09 already established.
  - B14 (`:663-664,2869,3103`): a gate-approved submit that later fails
    releases both exact maps and the token gate; the existing failure cleanup at
    `:2534+` handles only pending/unknown outcomes.
- Acceptance: each of the three mechanisms is reproduced RED first. Then
  fill/evict/replay of an old generation rejects as stale with zero
  subscription/output effects; an old origin/token cannot act after replacement
  while the successor stays intact; a forced post-gate admission failure retains
  no entry and releases no successor. Capacity and stop-time assertions,
  concurrency linearization and restart/replay coverage are required, and every
  rejected path asserts zero Agent/Tool/Task/audio/history/store effects.
- Exclusions: no new product policy or classifier, no protocol/schema or
  migration change, no capacity-policy change beyond the recorded fence, no
  Gateway route or conformance source change, no other module owner, no
  physical Provider claim.

- Review outcome — **REJECTED at `f04f10027`, 0 closure credit.** Independent
  Tier-3 review confirmed the scope surface (exactly the two owned files, no
  `critical_token_safety.py`, Gateway, conformance or other owner edit, no
  protocol/schema change), reproduced B12 and B14 as genuine business RED on
  baseline `455873109`, and confirmed Ruff parity, format, `py_compile`,
  `git diff --check` and the adjacent-seam `pywintypes` failure as
  byte-identical pre-existing. Two blocking findings are returned to the packet
  owner:
  - **BLOCKING-1 (HIGH, candidate-introduced).** The B14 release at
    `product_composition_registry.py:2608-2618` also fires on the **successful**
    default dispatch path. `_accepted_turn_commits_by_commit` is written only in
    the `dispatch_target == "task"` branch at `:2537`, and `result_unknown` is
    set only inside that same branch, so for `dispatch_target == "agent"` — the
    default at `:3013` — all three conjuncts are true on success and
    `release_commit` wipes the gate's per-commit evidence one turn early. The
    two map operations are no-ops there, but the gate release is not: it shortens
    the contracted "until the outer route is fenced" lifetime, leaves at-most-once
    resting on `agent_conversation_runtime.py` alone, and changes
    `GATE_CAPACITY_EXCEEDED` accounting, which this packet's exclusions forbid.
    Minimum fix: add `dispatch_target == "task"` as the first conjunct, and pin
    gate retention across a successful agent-target submit with a regression test.
    The reviewer verified that narrowing restores baseline state exactly and keeps
    all candidate tests green.
  - **BLOCKING-2 (HIGH).** B13's acceptance — an old origin/token cannot act
    after replacement — is unproven and false on the reachable surface. In a real
    journey `_voice_task_origins` is already empty before replacement, so the added
    `_drop_voice_task_origins_for_route_locked(key)` had no observable effect; the
    actionable path is `_obtain_task_intent_commit` at `:3172-3184`, whose four
    conditions all still hold after replacement because
    `_accepted_voice_commit_routes` is keyed by session and interaction only, with
    no activation id or generation. The candidate test hand-injects
    `_VoiceTaskOrigin` entries and pokes a private lease field, never acts with the
    superseded identity, and asserts nothing about the critical token. The recorded
    rationale is also wrong: `_release_task_intent_commit_locked` returns early for
    `source == "voice"` and never reaches the conditional release. The decision to
    omit `release_interaction` is nevertheless correct on other grounds — it would
    pop `_latest_input_generation` and re-open stale-input admission for the
    successor. Repair the acceptance with a real-journey test that acts with the
    superseded identity and asserts the critical-token outcome, or explicitly
    re-scope that clause.
  - **Evidence gaps to close with the repair:** restart coverage is required by
    this record's acceptance and is absent; the concurrency test uses
    `asyncio.gather` with near-tautological assertions instead of a deterministic
    barrier; there is no oversized-generation boundary test for the new fence
    despite the file's own precedent; and no test pins the successful-path gate
    retention contract, which is exactly where BLOCKING-1 escaped. Two of the five
    new tests fail on baseline only through `AttributeError` on new internal
    fields, so they are not defect reproductions.
  - **B12 passed in full**: the sketch is byte-identical in shape to the accepted
    `_p2_response_generation_fence` precedent, collisions can only raise a cell and
    therefore only fail closed, the exact layer wins over the sketch, unrecorded
    keys read as absent rather than generation 0, and oversized generations fail
    closed upstream before reaching the fence.

### SRR-21 — B36+L20+L21 formal task leaf and intent authority

- Capability/owner: formal task control-leaf snapshot monotonicity, mutation
  envelope authority, and durable cancellation fencing in the intent route.
- Risk: Tier 3 authority and durability boundary.
- Worker-owned source/tests:
  `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/formalTaskControlLeaf.ts`,
  `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/formalTaskIntentRoute.ts`
  and their `tests/formalTaskControlLeaf.test.mjs` and
  `tests/formalTaskIntentRoute.test.mjs` only.
- Intended behavior:
  - B36 (`formalTaskControlLeaf.ts:339-344,525-583`): adopting `task.get`/
    `status` rejects attempt and event-head rollback, terminal resurrection and
    outcome change, and retains the known event cursor instead of resetting it
    to null.
  - L21 (`formalTaskControlLeaf.ts:537-549,603-667`): create/cancel/retry
    require the product mutation envelope; legacy `{ok:true,result}` success is
    reserved for queries and never carries mutation authority.
  - L20 (`formalTaskIntentRoute.ts:590-599,956-969`): a durable cancellation
    tombstone, or an equivalent durable fail-closed state, is written before or
    with local invalidation, so a journal-removal failure cannot later let
    `recoverPending` at `:640-674,721-730,972-993` claim and re-authorize the
    cancelled token.
- Acceptance: each mechanism is reproduced RED first. Then stale get/status
  after terminal events is rejected and the snapshot is unchanged; every legacy
  mutation response rejects without replica or receipt change; checkpoint
  removal failure first blocks submit and then `recoverPending` cannot
  resurrect the cancelled token, with zero Gateway mutation. Restart/replay and
  concurrent-adoption coverage are required.
- Cursor wording, made exact during review: the leaf retains the consumed event
  cursor **while the snapshot still describes the event head that produced it**,
  and otherwise clears it and requires a complete `task.events` replay.
  Unconditional retention is not implementable: `#adoptEvents` requires
  `existing.last_event_seq === after_seq` for an incremental fetch, so a
  snapshot ahead of the cursor would make the record self-contradictory. The
  defect being closed is the unconditional reset to null, not the safe clear.
- Candidate state — **CLOSED, 3 unique defects credited:** independent Tier-3
  review signed `f5c186934` and Main applied `9c855b11c` and `f5c186934` onto
  the integration branch as `155c15b36` and `b0341f41b`, byte-identical to the
  signed candidate. The worker branch `codex/lv-srr21-formal-task-authority`
  was not merged.
- Review note: the reviewer first saw a false green because the tests import
  the tsc output under `node_modules/.cache/live-voice-integrated-web/`, not
  the `.ts` sources. Any baseline comparison on this package **must recompile**
  before running `node --test`, or it silently exercises the previous build.
- Exclusions: no new product policy or classifier, no protocol/schema change,
  no backend source change, no touch of `productP1VoiceRoute.ts` or
  `LiveVoiceIntegratedRoutePanel.tsx` (owned by the parallel p1p2 branch), no
  other module owner.

## 5.10 Wave 10 ownership record — CLOSED

Wave 10 is frozen from integration baseline `ab46ad3e4`, the Wave 9 closure
record. Its three writer surfaces are disjoint. All three packets come from
batch 2 of the historical revalidation's priority ordering, "unbounded lifetime
state with permanent refusal", and they deliberately share one shape that two
independent reviews have already accepted: release the heavy state a bound
exists to reclaim, and retain a separate compact fence so the released identity
can never be replayed. SRR-17/A25 established the durable form of that fence and
SRR-20/B12 the fixed-memory sketch form; a plain LRU remains excluded.

B11 belongs to the same batch but is deliberately excluded: `project_code_executor.py`
is being modified in parallel on `agtai/hx/0812_live_voice_w3`, so it must be
routed after that branch merges. A5, A9, A15, A17 and B42 stay unactivated in §6.

### SRR-22 — A6+B4 conversation runtime critical-key lifetime

- Capability/owner: `agent_conversation_runtime` critical publication identity,
  queue capacity and bridge-consumer supervision.
- Risk: Tier 3 authority and availability. A6 and B4 share one packet because
  both are the same `_critical_keys` double-duty defect.
- Worker-owned source/tests:
  `jiuwenswarm/server/live_voice/agent_conversation_runtime.py` and
  `tests/unit_tests/live_voice/test_agent_conversation_runtime.py` only.
- Intended behavior:
  - A6 (`:184-242,347-363` and `:2640-2652,2793-2799`): queue capacity is sized
    by queued items and no longer shares one ledger with replay identity, and a
    publication failure surfaces explicitly without terminating the sole
    long-lived bridge consumer.
  - B4 (`:192,214-235,284,347-363`): `_critical_keys` stops being both a
    uniqueness ledger and a capacity counter; released entries leave a bounded
    replay tombstone, and progress notification gets an independent quota so it
    cannot starve terminal or presentation delivery.
- Acceptance: each mechanism is reproduced RED first. Then an injected critical
  publish violation yields an explicit failure and the next request is still
  delivered; drain and discard past capacity leave the runtime usable while
  duplicates still fail; progress cannot starve terminal or presentation
  notification. Concurrency, restart/replay and zero forbidden
  Agent/Tool/Task/audio-history effects on every rejected path are required.
- Exclusions: no new product policy or classifier, no protocol/schema change,
  no other module owner, no Gateway route change, no physical Provider claim.
  SRR-06/A8+B6 closed the terminal-truth and cleanup-ownership boundary in this
  same file; do not reopen or weaken it.

### SRR-23 — A13 composition registry accepted-commit lifetime

- Capability/owner: `ProductCompositionRegistry` accepted turn-commit retention
  across capacity eviction, route close and active-route shutdown.
- Risk: Tier 3 authority and availability.
- Worker-owned source/tests:
  `jiuwenswarm/server/live_voice/product_composition_registry.py` and
  `tests/unit_tests/live_voice/test_product_composition_registry.py` only.
- Intended behavior: A13 (`:2470-2479`, `:2553-2573`, `:1813-1818`,
  `:5861-5864`, `:8786-8788`, `:7158-7170`, `:8856-8862` at audit line numbers)
  — an abandoned closed-route origin gets a bounded late-create grace, after
  which its heavy state is released and only a compact stale/replay fence is
  retained. Repeating a successful task-origin submit and closing the route
  without a P3 create must not fill the 128 accepted entries for the registry
  lifetime.
- The grace is **global to the registry, not per route or per session**, which
  matches the shared 128-slot committed-turn ledger it protects. Independent
  review confirmed the consequence: an unrelated route's pending late create can
  be aged out by eight abandonments elsewhere. That is a fail-closed liveness
  contraction, strictly better than the unbounded leak it replaces, and it stays
  inside the recorded grace. Whether a per-route floor is wanted is routed for
  later tuning.
- Also delivered in this packet, outside the audited 88 and credited only in
  §6.1: the superseded identity that survives close then higher-generation
  reactivate. It lives in the same file and the same helper family, and its
  minimum direction is recorded in §6.1. Keep it in a separate commit so the
  numerator stays exact.
- Acceptance: reproduce RED first. Then 128 abandoned routes do not block a new
  submit; one late create succeeds within the grace and is refused after it;
  retired replay is stable and stale replay is refused; the existing eviction
  tests keep passing. Concurrency, restart/replay and zero forbidden effects on
  every rejected path are required.
- Exclusions: no new product policy or classifier, no protocol/schema change,
  no capacity-policy change beyond the recorded grace and fence, no Gateway or
  conformance source change, no other module owner. SRR-20 closed the
  progress-generation fence, the replacement cleanup and the definite-failure
  release in this same file; do not reopen or weaken them.

### SRR-24 — A1 conformance identity ledger lifetime

- Capability/owner: `StreamingSpeechConformance` generation and response
  identity retention, with provider and product-route capacity alignment.
- Risk: Tier 3 authority and availability. This is the most user-visible defect
  in the batch: after 64 distinct streams the conformance owner refuses further
  streaming for its whole lifetime.
- Worker-owned source/tests:
  `jiuwenswarm/server/live_voice/streaming_speech.py`,
  `jiuwenswarm/server/live_voice/openai_streaming_speech.py`,
  `jiuwenswarm/server/live_voice/dedicated_media_registration.py` and their
  focused tests only.
- Intended behavior: A1 (`streaming_speech.py:469-490,522-523,1028-1048,`
  `1215-1238,1597-1606`) — terminal reap releases heavy terminal identities by
  connection or session instead of retaining the 64-entry identity ledger for
  the conformance instance lifetime, a bounded generation tombstone keeps stale
  replay refusable, and the default provider at
  `openai_streaming_speech.py:879-881` and the product TTS allocation at
  `dedicated_media_registration.py:2658-2687` are aligned to the same capacity
  truth.
- Acceptance: reproduce RED first, proving that the 65th distinct stream is
  refused today. Then more than 64 sequential successful streams remain usable
  while stale generation replay is still rejected with its exact existing
  reason; provider and route capacities agree; identity/isolation across
  connections and sessions holds. Concurrency, restart/replay and zero
  forbidden effects are required.
- **Closure boundary, stated so the numerator is not misread.** A1's acceptance
  holds: the conformance owner no longer refuses streaming after 64 streams, more
  than 64 sequential streams stay usable, and stale replay is still refused with
  its exact existing reason. Product-side TTS end to end nevertheless remains
  capped at **256 per channel owner** by
  `StreamingSynthesisRouteOwner._retained_bindings`, which the strict review
  already numbers separately as **A17** — its text ends "This is a separate second
  limit from A1" — and which stays unactivated in §6. **31/88 must not be read as
  "streaming capacity is fully solved."**
- Exclusions: no new product policy or classifier, no protocol/schema change,
  no Gateway route source change, no physical Provider claim. SRR-10/A2+B2
  closed queued-terminal retirement in `openai_streaming_speech.py`; its
  fences, its reap semantics and its exception priority must survive unchanged,
  and the packet must rerun that file's focused suite to prove it.

## 5.11 Wave 11 ownership record — ACTIVE

Wave 11 is frozen from integration baseline `7109a274b`, the Wave 10 closure record.
Its three writer surfaces are disjoint. All three continue batch 2 of the
revalidation's priority ordering and reuse the same accepted shape as Wave 10:
release the heavy state a bound exists to reclaim, retain a separate compact
fence, never a plain LRU. SRR-17, SRR-20, SRR-22 and SRR-24 have now each had
that shape signed by an independent review, so a packet that departs from it
must say why.

A5 and A9 belong to the same batch and stay unactivated in §6 to keep this wave
reviewable. B11 stays excluded while `project_code_executor.py` is modified in
parallel on `agtai/hx/0812_live_voice_w3`.

### SRR-25 — A17 streaming synthesis route binding lifetime

- Capability/owner: `StreamingSynthesisRouteOwner` retained binding identity and
  its capacity-exhaustion disposition.
- Risk: Tier 3 authority and availability. This is the **second limit** the
  strict review split from A1: SRR-24 lifted the conformance ceiling, and this
  packet is what makes the product-side lift real end to end.
- Worker-owned source/tests:
  `jiuwenswarm/gateway/routing/streaming_synthesis_route.py` and
  `tests/unit_tests/gateway/test_streaming_synthesis_route.py` only.
- Intended behavior: A17 (`:510-560,716-763,1850-1867`) has **two independent
  changes**. First, `_retained_bindings` — declared at `:558`, written at `:763`,
  read at `:730` and `:1875`, and never deleted — gets bounded identity
  retirement with a compact stale fence, so 256 binding tombstones no longer
  live for the owner's whole lifetime. Second, capacity exhaustion stops raising
  a raw failure that bypasses the normal batch-eligible fallback and becomes a
  typed batch-eligible result instead.
- Acceptance: reproduce both mechanisms RED first. Then beyond 256 streams the
  product falls back without handler failure while stale bindings stay fenced;
  the existing fallback contract and its exact reasons are preserved; every
  refusal keeps zero forbidden effects. Concurrency with a deterministic
  barrier, restart/replay and identity isolation across owners are required.
- Exclusions: no new product policy or classifier, no protocol/schema change,
  no conformance or Provider source change, no other module owner. The typed
  result must reuse the **existing** batch-eligible fallback vocabulary; adding
  a new reason code would be a protocol change and must stop for re-scoping.
  This file carries one disclosed pre-existing failure at
  `test_streaming_synthesis_route.py:1837`
  (`test_cancel_api_caller_cancel_retries_cleanup_then_rethrows`) that four
  independent reviews have confirmed on baseline; it must remain unchanged, and
  the packet must not silently repair or hide it.

### SRR-26 — A15 P2 interaction lease lifetime

- Capability/owner: `ProductP2InteractionAdapter` retained activation leases and
  their terminal release.
- Risk: Tier 3 availability and identity.
- Worker-owned source/tests:
  `jiuwenswarm/server/live_voice/product_p2_interaction_adapter.py` and
  `tests/unit_tests/live_voice/test_product_p2_interaction_adapter.py` only.
- Intended behavior: A15 (`:1154,1199-1203`) — `_leases` has no cap and no
  terminal callback, so only a higher generation of the same key ever removes a
  closed lease. A terminal notification now deletes the heavy closed lease and
  keeps a separate bounded generation tombstone.
- Also delivered in this packet, outside the audited 88 and credited only in
  §6.1: the wall-clock flake in this same file's tests. `_settle_partial_failure`
  (`:1554-1572`) rolls back with `cleanup_timeout_seconds`, defaulting to `0.1`
  at `:1164`, and `cleanup` (`:449`) is `wait_for(shield(coordinator), timeout)`,
  so any scheduling stall past 100 ms downgrades the intended `*_FAILED` reason
  to `ROLLBACK_FAILED`. Two independent reviews reported different reproduction
  rates — one saw 3/8 and 4/8, another 0/34 — which is itself evidence that the
  test is timing-dependent rather than deterministic. Make the affected tests
  deterministic without weakening what they assert. Keep it in a separate commit
  so the numerator stays exact.
- Acceptance: reproduce A15 RED first. Then many distinct closed interactions
  stay bounded while stale generation replay is rejected with its exact existing
  reason; a live lease is never collected; the flake tests become deterministic
  and still fail for their original defect. Concurrency with a deterministic
  barrier, restart/replay and zero forbidden effects are required.
- Exclusions: no new product policy or classifier, no protocol/schema change,
  no other module owner, no Gateway route change. Do not change
  `cleanup_timeout_seconds`' production default as a way of fixing the flake;
  that would be a capacity/timing policy change. Make the tests deterministic
  instead.

### SRR-27 — B42 conversation loop control ledger lifetime

- Capability/owner: `conversation_runtime_loop` barge and cancel control
  identity, and the durability of what it retains about failures.
- Risk: Tier 3 availability and privacy. Retaining raw exception objects and
  tracebacks is the same content-exposure family that SRR-02/A21 closed for the
  Agent client, so the privacy half is not optional.
- Worker-owned source/tests:
  `jiuwenswarm/server/live_voice/conversation_runtime_loop.py` and
  `tests/unit_tests/live_voice/test_conversation_runtime_loop.py` only.
- Intended behavior: B42 (`:180-188,398-434,508-555,741-807`) — six barge and
  cancel fingerprint, result and error maps have no lifetime capacity, and the
  queue's `control_capacity` does not bound completed commands. They gain a
  bounded fail-closed replay ledger, and only a stable error code, reason and
  message are persisted instead of raw `Exception` objects and tracebacks.
- Acceptance: reproduce RED first, for both halves. Then more than capacity
  successful and failed ids keep memory bounded; an evicted old id cannot
  execute again; no raw exception object, traceback, or private payload content
  survives in any retained record or public diagnostic. Concurrency with a
  deterministic barrier, restart/replay and zero forbidden effects are required.
- Exclusions: no new product policy or classifier, no protocol/schema change,
  no other module owner. C3 remains an audit-ID alias of B42 and adds no unique
  defect, so closing B42 closes C3's surviving concern without a separate entry.

## 6. Queued repair programs

The 57 remaining unique defects consist of the three activated Wave 11
candidates A15, A17 and B42 plus the 54 unactivated defects below. These
groups are not worker write authority. Each activation removes its IDs from
this queue and freezes smaller owner-specific packets before editing.

- Generation/successor/authority cleanup (**7**): B18, B32, B37, B38, B39, D2
  and L19. B12, B13, B14, B36, L20 and L21 moved to the active Wave 9 packets.
  B17 remains an inactive alias of B13 and is activated with it.
- Cancellation/teardown/retained cleanup (**9**): A7, A19, A22, B21, B23,
  B24, D1, D3 and L7.
- Capacity/lifetime/replay (**5**): A5, A9, B11, L5 and L18. A1, A6, A13 and
  B4 closed in Wave 10; A15, A17 and B42 moved to the active Wave 11 packets.
  C3 remains an active audit-ID alias of B42 and adds no unique defect, so it
  closes with B42.
- Event-loop, lock and filesystem responsiveness (**4**): A14, B15, B25 and
  B27.
- Protocol/state/compatibility (**29**): B1, B3, B5, B8, B19,
  B20, B22, B28, B29, B30, B33, B34, B35, B40, L1, L2, L3, L4, L6, L8,
  L9, L10, L11, L12, L13, L15, L16, L17 and L22.

The queue arithmetic is `7 + 9 + 5 + 4 + 29 = 54`; adding the three activated
Wave 11 candidates gives the 57 unique remaining defects. By historical family
that remainder is 8 A, 27 B, 19 L and three D findings, of which the
unactivated 54 are 6 A, 26 B, 19 L and three D.

### 6.1 Findings routed out of Wave 9

These were discovered while closing Wave 9. They are **not** part of the 88
audited defects and do not change that denominator. Each needs its own scope
and risk checkpoint before activation.

- **Cross-process cancellation durability (from L20/SRR-21).** A cancellation
  tombstone that survives a process restart is not representable in
  `live-voice.formal-task-intent-recovery.v2`: its phases are
  `resolving|clarification|awaiting_confirmation|post_create_binding`,
  `replace()` enforces `generation + 1` and `save()` requires absence. A true
  cross-process tombstone needs a v3 phase or a journal API addition, both
  excluded from SRR-21. The delivered owner-scoped tombstone fails submit and
  recovery closed and settles retryably; the restart residual is pinned by the
  characterization test `a restarted owner replays a lost cancellation as an
  explicit confirmation, never as a dispatch`, which proves the successor
  issues zero `live_voice.composition.p3.intent` calls and re-presents the
  server-held confirmation as a new explicit user decision.
- **`task.list` replaces the whole replica (sibling of B36).** The list branch
  of `adopt` still overwrites every record and drops every cursor, so a stale
  list can roll a task back. SRR-21's recorded behavior names `task.get` and
  `task.status` only, and adding a monotonic merge would change the list's
  full-replacement (including deletion) semantics. No product exposure today:
  `LiveVoiceIntegratedRoutePanel.tsx` performs zero `task.list` adoptions.
- **Deterministic mounted-panel failure.** The pre-existing
  `liveVoiceIntegratedRoutePanelMounted.test.mjs:7342` failure reproduces
  deterministically when that file runs alone, so it is a real defect rather
  than a load flake. It belongs to the panel owner on
  `agtai/hx/0819_live_voice_p1p2`.
- **Reason-code drift on an admission-fence false positive (from SRR-24
  review).** A never-seen identity that collides in the admission bitmap is
  refused as `STALE_*_SESSION` / `STALE_*_STREAM` instead of
  `*_NOT_FOUND` (`streaming_speech.py:1551-1560,1584-1593`). Both are
  fail-closed refusals and the measured rate is ~0% at realistic volumes, but a
  diagnostic consumer keying on the reason would observe the change. Related:
  a released identity whose generation cell collided with a higher one can have
  its own legitimate next generation refused, and
  `retained_identity_tombstones` is no longer monotone because it now counts
  exact entries only. No production consumer of that metric exists.
- **`npm run lint` is unusable package-wide.** No ESLint configuration exists
  in `jiuwenswarm/channels/web/frontend` or any ancestor directory, so the
  script fails for reasons unrelated to any packet. Infrastructure gap.
- **Superseded identity survives close then higher-generation reactivate
  (from SRR-20 review, pre-existing).** The identity leak B13 closes for
  *replacement* remains open on the *close then reactivate* path. After a
  normal `handle_p2_close`, which does call `release_interaction`,
  `_accepted_turn_commits_by_commit`, `_accepted_voice_commit_routes` and
  `_critical_input_guarded_commits` still retain the superseded commit; a fresh
  higher-generation activation republishes the route key and the old speech
  mints a live confirmation token. The reviewer confirmed baseline `455873109`
  produces an identical token, so SRR-20 neither introduced nor widened it, and
  B13's recorded behavior is scoped to replacement. Minimal direction: also
  call `_retire_accepted_voice_commits_for_route_locked` on the close path and
  the disconnect path; close may keep its `release_interaction` because it
  never republishes the key.
- **Uncontained background-task exception in the progress return bridge (from
  SRR-20).** With a delivered subscription event and a generation above
  `MAX_SAFE_INTEGER`, `TaskProgressReturnBridge._run`
  (`jiuwenswarm/server/live_voice/task_progress_return.py:468,1101,1125`) leaves
  an unretrieved `ContractViolation`, surfacing as `Task exception was never
  retrieved` on stderr. The handler's own fail-closed is correct and
  unaffected; the bridge simply does not contain its own background-task
  exception. Outside SRR-20's owned surface, so the packet used an event-free
  subscription to sidestep the noise rather than touching that file.

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
| SRR-21 / B36+L20+L21 | 24/88 | `155c15b36`…`b0341f41b`; an authoritative `task.get`/`task.status` snapshot can no longer roll a formal task replica back. Attempt rollback and identity forgery, event-head rollback, terminal resurrection and terminal-outcome change all reject through the existing `validTaskStateTransition` rule rather than a new policy, and the consumed event cursor survives a refresh that still describes the head that produced it instead of resetting to null. Legacy `{ok:true,result}` success no longer carries mutation authority for create, cancel or retry while queries keep accepting it. A cancelled destructive confirmation is invalidated with, not after, its durable removal: an owner-scoped cancellation tombstone fails both submit and `recoverPending` closed before any journal claim or Gateway call, and settles retryably. Independent Tier-3 review reproduced all three mechanisms RED on baseline `455873109` after recompiling (6 business assertions), then passed 49 focused and 418 package cases with the one disclosed mounted-panel failure unchanged, typecheck and build clean |
| SRR-20 / B12+B13+B14 | 27/88 | `950bb9830`…`0a2361f81`; progress-generation admission no longer erases its high-water when capacity evicts the heavy closed-route state, so a superseded generation can never activate again: the retired mark moves into the same conservative max sketch already used for the P2 fences, where collisions can only fail closed and the exact map still wins. Higher-generation P2 replacement now runs the same cleanup normal close runs, retiring every accepted voice commit bound to the superseded route by exact commit id, which releases the commit-level gate evidence while preserving the interaction's monotonic input-generation fence that the successor immediately reuses. A definite submit failure releases the critical-input maps and the token gate, while unknown outcomes and every successful dispatch keep theirs. Two review rounds: the first rejected the candidate for releasing gate evidence on the successful default Agent path and for an unproven B13 acceptance; the repair narrowed the release to the task branch and proved the acceptance end to end, showing that a superseded generation previously minted a redeemable `formal` confirmation token through the successor's route. Deterministic lock-barrier concurrency, both uint64 boundary sides, restart characterization and exactly-once subscription evidence; 161 focused plus 240 consumer tests passed with Ruff parity and the one disclosed `pywintypes` environment failure unchanged |
| SRR-22 / A6+B4 | 29/88 | `935a4f74e`; the critical notification reserve stops being one set that is simultaneously a uniqueness ledger and a capacity counter and is never released. Capacity is now measured by queued items and returned on both removal paths, released identities move into an exact per-lane bounded tombstone, and only what that tombstone evicts folds into a conservative membership sketch, so eviction can never drop the fence and a collision can only refuse a never-published identity. Progress terminals get an independent reserve, so they can no longer starve presentation or terminal delivery. A publication failure inside the sole bridge consumer is now recorded as an attributable diagnostic instead of killing the consumer, which also lets teardown finish closing the Harness and CR that the escaping violation used to skip. Independent review reproduced six business REDs on baseline, confirmed the implementer's own declaration that two further tests are API-missing rather than defect reproductions, and killed six targeted mutants including a plain-LRU variant; 107 focused and 487 consumer tests passed with Ruff parity |
| SRR-23 / A13 | 30/88 | `323e38dd5`…`1c860f980`; an accepted voice commit whose route has closed no longer holds a committed-turn slot for the registry lifetime. Abandoned origins keep a bounded count-based late-create grace, and past it the oldest surrenders its heavy state through the existing exact commit-id retirement while the compact replay fence keeps it refusable. The grace is global to the registry, matching the shared 128-slot ledger it protects. Delivered in the same packet but credited only in §6.1: superseded identities are now retired at route republication, which independent review confirmed is both the correct deviation from the recorded direction — close must not retire, because an accepted origin legitimately outlives it for the P3 create — and a complete one, since the whole file has exactly one `_p2_routes[key]` assignment and all three removal paths funnel back to it. Review reproduced six business REDs on baseline, ran the 128-route exhaustion for real, and independently probed the mid-flight retirement case to confirm at-most-once still holds through three fail-closed entries plus `TURN_COMMIT_RETIRED`; 167 focused, 240 consumer and 2061 live_voice tests passed with Ruff parity |
| SRR-24 / A1 | 31/88 | `d5559d514`…`05b59e317`; the conformance identity ledgers no longer keep 64 entries for the instance lifetime, so a Provider owner stops losing streaming after 64 distinct streams. An identity owning no live stream surrenders its exact entry and keeps a compact tombstone: a fail-closed admission bitmap plus a conservative maximum generation sketch, 1.25 MiB per instance. Nothing is ever forgotten — LRU order only picks which identity gives up its exact entry — and both fences only rise, so stale replay is still refused with its exact original reason. The Provider identity budget mirrors the route's existing 256 rather than inventing a number, with a test pinning the two constants equal. Implementation also fixed an inherited ordering defect where a rejected start spent a ledger slot because the release ran before a clock read that can raise. Two review rounds: the first rejected the candidate because the only assertion of `RESPONSE_IDENTITY_CAPACITY_EXHAUSTED` had been deleted with a retired test and never re-homed, leaving live raise sites untested; the restored oracle drives both raise sites from one fixture and proves the refusal is non-mutating via zero pending Provider controls. 71 conformance, 95 Provider, 44 media and 185 gateway-seam cases pass with Ruff parity |

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
| A6, B4 | `python -m pytest tests/unit_tests/live_voice/test_agent_conversation_runtime.py --no-cov --asyncio-debug` |
| A13 | `python -m pytest tests/unit_tests/live_voice/test_product_composition_registry.py --no-cov` |
| A1 | `python -m pytest tests/unit_tests/live_voice/test_streaming_speech.py tests/unit_tests/live_voice/test_openai_streaming_speech.py tests/unit_tests/gateway/test_dedicated_media_registration.py --no-cov --asyncio-debug` |
| B12, B13, B14 | `python -m pytest tests/unit_tests/live_voice/test_product_composition_registry.py --no-cov`; also rerun the `test_voice_task_bridge.py`, `test_p3_authenticated_composition.py` and `test_critical_token_safety.py` seams and compare the disclosed `pywintypes` failure with the baseline |
| B36, L20, L21 | From `jiuwenswarm/channels/web/frontend`: `npm run test:live-voice-integrated-web`; require the formal task leaf and intent blocks to pass and compare any full-suite failure with the disclosed mounted-panel baseline below. A source-level baseline comparison **must recompile** first, because the tests import the tsc output under `node_modules/.cache/`. |
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
