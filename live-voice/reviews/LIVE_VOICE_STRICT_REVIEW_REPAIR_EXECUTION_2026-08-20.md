# Live Voice strict-review repair execution — 2026-08-20

> Status: **ACTIVE — 9/88 unique defects closed.** This is a user-routed,
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

## 3. Active Wave 1 ownership

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
  `jiuwenswarm/gateway/routing/agent_client.py`, the directly invoked
  `jiuwenswarm/common/e2a/wire_codec.py`, and their existing focused tests.
- Intended behavior: INFO/DEBUG logs expose only an allowlisted, content-free
  request/response summary; transcript/text/audio/credential/private markers
  never appear at any nesting, casing or separator variant. URI, address,
  object identity, exception/close reason and untrusted scalar values are also
  content-hidden across the real unary/stream codec seam; any correlation ref
  must use a process-temporary secret and never appear in task names as raw
  content.
- Acceptance: first demonstrate current transcript leakage with sentinel
  payloads; verify unary and streaming success/error logs, nested list/dict and
  malformed/private values; cover connect/send/receive/close diagnostics,
  low-entropy ref enumeration, untrusted integers and common E2A success,
  fallback and inverse-error logs; prove the original payload is not mutated
  and non-Live-Voice supported logging remains compatible.
- Exclusions: no global logging framework replacement, retention policy or
  transport payload change.

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

Wave 1 files do not overlap. SRR-01/02/03 implementation workers cannot serve as
their own independent reviewers. Main implements SRR-04/05 and assigns their
independent review after the first worker wave returns.

## 4. Active Wave 2 ownership

Wave 2 may overlap the final SRR-02 work because all four owner surfaces below
are disjoint from Wave 1 and from each other. A8 and B6 deliberately share one
packet because both defects converge on the same Harness cleanup coordinator.

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

Wave 2 writer leases are owner-scoped. A worker cannot review its own lane, and
Main integrates only the exact independently signed commits before advancing
the numerator.

## 5. Active Wave 3 ownership

Wave 3 is frozen from integration baseline `9741b805c`. Its three writer
surfaces are disjoint. A2 and B2 deliberately share one packet because both are
the same Adapter queued-terminal retirement invariant. A7 remains queued until
SRR-06 is integrated because its test surface overlaps the Harness packet.

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

## 5.4 Wave 4 activation — disjoint durability, terminal and media cleanup

Wave 4 starts from integration commit `4923f05cd` after the first eight unique
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

## 6. Queued repair programs

These groups route work after the currently active packets; they are not yet
worker write authority. Each activation removes its IDs from this queue and
freezes smaller owner-specific packets before editing.

- Generation/successor/authority cleanup: B7, B12, B13, B14, B16, B18, B32,
  B36, B37, B38, B39, D2, L19, L20 and L21. B17 remains an alias of B13.
- Cancellation/teardown/retained cleanup: A7, A8, A19, A20, A22, B6,
  B21, B23, B24, D1, D3 and L7.
- Capacity/lifetime/replay: A1, A5, A6, A9, A13, A15, A17, A25, B4, B11,
  B42, L5 and L18. C3 remains an alias of B42.
- Event-loop, lock and filesystem responsiveness: A14, B15, B25 and B27.
- Protocol/state/compatibility: A3, A23, B1, B3, B5, B8, B19,
  B20, B22, B28, B29, B30, B33, B34, B35, B40, L1, L2, L3, L4, L6, L8,
  L9, L10, L11, L12, L13, L14, L15, L16, L17 and L22.

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

## 8. Global exclusions

No remote update, `develop` integration, production authentication/tenancy,
public deployment, provider/device configuration, physical product acceptance,
new product policy, new classifier, schema migration or broad unrelated cleanup
is included. P3-2 remains frozen under D-087 and resumes only after this
user-routed repair packet closes or is explicitly re-routed; no P3-2
implementation credit is claimed here.
