# P3-3 Capability / Admission Activation Preparation (2026-08-18)

Status at the preparation snapshot: `PREPARATION ONLY / NOT YET ACTIVATED / NO CREDIT`

This review prepares the capability, admission, Attempt, lease and recovery
decisions that P3-3 must freeze before implementation. It inherits accepted
P3-1 but does **not** activate P3-3, select a historical branch, grant an
Executor capability, or turn a candidate/fact/receipt into runtime authority.
The current queue and authority remain [STATUS](../STATUS.md). The normative
P3-3/P3-4 contract remains the [complete P3 execution plan](../roadmap/FULL_P3_EXECUTION_PLAN.md).
Risk and evidence closure remain governed by [TESTING](../../TESTING.md).

Historical reuse decisions below are subordinate to the frozen
[P3 coverage/reuse audit](P3_IMPLEMENTATION_COVERAGE_AND_HISTORICAL_REUSE_AUDIT_2026-08-18.md)
and [source-asset manifest](P3_HISTORICAL_SOURCE_ASSET_EXTRACTION_MANIFEST_2026-08-18.md).

## 1. Integrated baseline and evidence boundary

| Role | Exact identity | Meaning |
|---|---|---|
| formal P3-G0 product source | `f24dd17d336c8266954f2d7299ca13bd0314d424` | G0_FINAL product source; D-086 records scoped foundation acceptance while preserving the controlled product-readiness candidate as `FAIL` |
| G0 close and audit rebaseline | `8df7d38227b684177efca8cad83d77278ad42c19`; `5787eda931159ba533e0a81ca8be8b744f449a8b` | scoped P3-G0 close/queue transition and the frozen P3 audit/manifest rebaselined onto that lineage |
| accepted P3-1 source and inspected target | `d40e0ee391fdf162faa9d9938eb9b9610020c1a7` | clean integrated source used for the current inventory and accepted P3-1 evidence below |

The former split histories and transient pre-amend G0 workspace description are
superseded by this integrated lineage. P3-1 is accepted at `d40e0ee3`; that does
not invent a physical G0 candidate PASS or activate P3-3. Rebase/integration
identity and affected facts must be re-recorded if Main changes this baseline.

Historical commits were not imported or executed in this preparation branch.
Their identities, files, symbols and tests are inventory facts from the frozen
manifest. Any later port must reopen the exact source object and review its diff.

## 2. Admission gates and activation rule

The P3-1 hard dependency was satisfied at `d40e0ee3` on the formal G0_FINAL
lineage. At this 2026-08-18 preparation snapshot, STATUS activated P3-2 rather
than P3-3; a later queue decision still had to activate a bounded P3-3 packet
before production work. This preparation itself does not satisfy either P3-3
or P3-4 acceptance; later package outcomes are recorded in
[STATUS](../STATUS.md) and the
[Wave-2 implementation review](P3_WAVE2_COMMAND_ADMISSION_REPLAY_REVIEW_2026-08-19.md).

Before P3-3 implementation, Main must accept one contract that:

1. gives a versioned, immutable Executor capability profile a canonical owner;
2. maps Task execution requirements to that profile without reusing command
   authorization vocabulary;
3. selects exactly one real Adapter before Task/Attempt/outbox mutation for
   static unsupported requirements;
4. persists the selected Adapter/profile identity and admission facts on the
   exact Attempt;
5. separates Task acceptance, queue/admission, Attempt allocation, running
   evidence and terminal truth;
6. bounds volatile capacity/busy retry and unknown/orphan reconciliation;
7. preserves the current Store claim, Adapter lease and OS ownership fences as
   distinct authorities; and
8. rejects undeclared operations before any Executor or protected side effect.

## 3. Current real capability inventory at `d40e0ee3`

Evidence locations in this section are `path:line @ d40e0ee3`.

| Component | Current facts | P3-3 credit | Missing / unsafe to infer |
|---|---|---|---|
| historical `ExecutorPort` fake | `executor_port.py:38` has unversioned booleans for start/status/cancel acknowledgement/terminal/restart; `ExecutorPort:46` stores attempts in memory and exposes `dispatch/start/cancel/finish/status` | deterministic test oracle only | no product composition, persistence, real Adapter, selection, version/digest, resource/admission facts, control surface or restart recovery; P3-1 review keeps it as historical fake/test support |
| production `FormalExecutor` Protocol | `persistent_task_core.py:65` declares `dispatch/cancel/adjust/settle_adjustment/status/retry_readiness` | real current Port boundary for Direct Adapter | no capability-description method, selector/registry/fallback, explicit start, update/input/pause/resume/priority/checkpoint/recover API; startup/close are composition conventions rather than Protocol capabilities |
| production Adapter composition | `FORMAL_PROJECT_EXECUTOR_ID` at `project_code_executor.py:71`; factory composes one `DirectProjectCodeExecutorAdapter` | one real in-process Adapter path; exact executor identity | Task spec preselects the only executor; there is no selection among versioned profiles or safe fallback |
| Task requirement carrier | `FormalTaskSpec` at `formal_task_models.py:522` persists `executor_id`, `required_capabilities`, context and side-effect class | immutable exact Task input | current `required_capabilities` originates in command authorization (for create, `task.create`); it is not an Executor operation/profile contract and must not be silently repurposed |
| Task truth | `PersistentTaskRecord` at `formal_task_models.py:671` persists canonical scope/spec/state/current Attempt/reconciliation/revision/event head | canonical Task owner, including multi-Task identity | no durable admission/queue reason, selected capability profile, deadline or retry budget projection |
| Attempt truth | `PersistentAttemptRecord` at `formal_task_models.py:760` persists Attempt, Task, executor id/ref, lifecycle, source sequence and attempt number | exact Task→Attempt→Executor binding and stale-event fence | no profile id/version/digest, Adapter build/protocol identity, durability level/version, admission decision, lease generation or queue deadline |
| Store | schema v4 at `task_store.py:60`; canonical commands/tasks/attempts/events/outbox/current-background/results; create at `:1263`; claim/release/complete at `:2894/:2973/:3151`; observations at `:3513` | one transaction owner for Task/Attempt/event/outbox; claim-token CAS; current-background is explicitly a UI hint, never authority (`:1406`) | no capability/admission tables or migration, no visible queue reason/deadline/backoff, no versioned Adapter selection record |
| outbox | `PersistentOutboxItem` at `formal_task_models.py:1484`; Store records delivery count, claim owner/time/token and last error; claim lease is five minutes (`persistent_task_core.py:62`) | idempotent dispatch/cancel/adjust delivery and stale worker fencing | claim lease is not Executor lease or admission timeout; busy/capacity release can retry indefinitely; `last_error` is not a supported user projection |
| Direct Attempt journal | `_DirectProjectAttemptJournal` at `project_code_executor.py:1185`, component table `live_voice_formal_project_attempts_v1` at `:90` | durable Adapter-owned exact attempt/ref, project binding, owner lease/heartbeat, absolute runtime deadline, cancel and restart facts | separate component schema/transaction owner; not the Task Store; no versioned capability/admission profile or D1/D2 truth |
| Direct dispatch/admission | `DirectProjectCodeExecutorAdapter` at `:2312`; dispatch `:2593`; max live workers 32 (`:99`, check `:2625`); same project is serialized by the journal | capacity and project-busy reject before Direct Attempt creation; exact replay and project binding | limits are private constants, not declared capability facts; capacity/busy retry has no persisted policy/deadline; cross-project concurrency lacks focused real-Adapter proof |
| Direct cleanup/recovery | retry readiness `:2418`; startup recovery `:2514`; expired recovery `:2084`; status `:3613` | current D0 proof for worker/apply/interruption/journal/lease/retained-worktree quiescence; OS lock prevents ownership borrowing | failure to prove OS ownership leaves truth unchanged; no bounded user-visible orphan state; no D1 resume or D2 effect reconciliation |
| adjustments | Direct `adjust` at `:3476`; Store-ordered adjustment and terminal settlement fence | real bounded text adjustment only while an in-memory demo itinerary checkpoint is open | not generic update, provide-input or persistent checkpoint; legacy Adapter rejects adjustment; product flags restrict the positive path |
| reconciliation | Core `reconcile()` at `persistent_task_core.py:747` resets expired Store claims, drains outbox and asks status for nonterminal Attempts | D0 restart/status/lost handling without redispatching a known original Attempt | no bounded unknown deadline, no capability-driven recovery selection, no D1 checkpoint recovery and no D2 effect ledger/manual settlement |

### Current capability record that must be replaced, not promoted

`ExecutorCapabilities` in the historical fake is an unversioned bundle of test
booleans. It is not a product declaration. P3-3 needs an immutable profile with
at least profile schema/version/digest, Adapter/executor identity, supported
operation versions, lifecycle/observation semantics, concurrency/capacity
semantics, durability level/version and enforcement facts. Absence is
unsupported; `True` in a fake is never a real Adapter proof.

## 4. Operation-by-operation evidence

“Unsupported” means reject before Adapter action and before any protected
mutation. It must not be translated to an accepted no-op.

| Required operation | Current production evidence | Status for P3-3 | Required activation disposition |
|---|---|---|---|
| start | there is no explicit production Port `start`; `dispatch()` both admits and launches Direct work; only the historical fake has `start()` | **unsupported as a separately declared operation** | either version `dispatch` as the one accepted start semantic, or add a real explicit start boundary; do not claim the fake |
| status | Direct and legacy Adapters return exact lifecycle observations; Store validates exact Attempt/ref/source sequence before projecting | **supported current D0 seam** | declare/version observation semantics and add profile/selection proof; unknown/unavailable must stay non-success |
| cancel | Direct `cancel()` at `project_code_executor.py:3542` and legacy cancel exist; exact binding; cancellation acceptance can remain pending and does not terminalize by itself | **supported current seam** | declare/version cancel and preserve “accepted is not terminal”; prove replay/race/zero wrong-target effects |
| update | current command is `task.adjust`; Direct applies bounded text only at the demo itinerary checkpoint; legacy rejects | **generic update unsupported** | P3-2 must freeze update semantics first; Adapter must declare a real versioned positive or reject before mutation |
| input / provide-input | no Port method or durable blocking-question answer path | **unsupported** | define exact pending-question identity, scope, Attempt/generation and replay/conflict contract before adding a positive |
| pause | no Port method, Adapter action or durable paused truth | **unsupported** | reject before mutation; positive requires real Adapter pause/observation and P3-2 command contract |
| resume | no Port method; restart recovery is not user resume | **unsupported** | reject before mutation; positive must bind exact paused Attempt/generation and is not D1 checkpoint recovery |
| priority / reprioritize | no Port method, queue priority model or Adapter action | **unsupported** | reject before mutation; define whether priority affects accepted queue only or running work, with exact race semantics |
| checkpoint | `_AdjustmentCheckpoint` at `project_code_executor.py:2306` is in-memory demo coordination | **D1 unsupported** | never advertise as persistent checkpoint; defer canonical wire/store/real Adapter to P3-4 `G4D/G4T` |
| reconcile | Core status/restart and Direct lease recovery provide D0; `ReconciliationState` exists | **partial D0 only** | version D0 facts and bound unknown/orphan handling in P3-3; D1/D2 positives remain P3-4 unsupported |

Current `task.retry` is also not a capability profile. It creates a bounded new
Attempt after current cleanup proof. It does not authorize checkpoint resume,
and it must remain unavailable for Adapters that cannot produce current
`retry_readiness()` facts.

## 5. Task accepted versus Attempt running

The current boundary is correct and must be preserved:

1. `SqliteTaskStore.create()` atomically creates Task `accepted`, Attempt
   `accepted`, `task.accepted`, a dispatch outbox item and command replay truth.
   It performs no Executor call.
2. A worker claims the exact outbox item under a fresh Store claim token.
3. The Adapter may reject as unavailable because of capacity or project-busy.
   The Core releases the outbox; Task and Attempt remain `accepted`. They are
   queued for another bounded admission attempt, never `running`.
4. Only a Store-validated known `attempt.running` observation for the exact
   Attempt/ref/source sequence emits `task.running` (`task_store.py:3764`) and
   transitions Task to `running`.
5. Cancellation acceptance, delivery acknowledgement, verifier success,
   candidate preparation and reconciliation facts do not imply terminal truth.

P3-3 should retain `accepted without running evidence` as the canonical queued
condition, not add an independent `queued` lifecycle owner. A projection may
show `queued`, but it must derive from persisted admission facts plus accepted
lifecycle and must not redirect mutation authority away from an addressed Task.

## 6. Proposed P3-3 admission freeze

This subsection is a recommendation awaiting Integration Owner acceptance. It
does not change current behavior.

### 6.1 Static selection

- Introduce one canonical immutable `ExecutorCapabilityProfile` owner and a
  distinct Task execution-requirement carrier. Do not overload the current
  command `required_capabilities` field.
- Select one Adapter/profile deterministically using exact executor, context,
  side-effect and operation-version requirements before creating Task, Attempt
  or outbox state. A static mismatch returns stable `UNSUPPORTED` with zero
  Store/Executor/project effects.
- Persist the selected profile id/version/digest, Adapter identity and requested
  operation versions on the Attempt/admission record. Reconciliation must use
  the persisted selection, never a newly convenient Adapter.
- Do not add fallback after any Adapter acceptance or unknown result. Fallback
  before mutation is allowed only if the frozen selector ranks compatible
  profiles deterministically and the selected fact is persisted.

### 6.2 Volatile capacity and queue

- Capacity/project-busy may occur after canonical Task/Attempt acceptance. Keep
  the Attempt accepted, persist a bounded machine-readable reason, next eligible
  time, admission attempt count and absolute admission deadline, and expose a
  read-only queued projection.
- Freeze a bounded retry/backoff policy in configuration plus persisted facts.
  Current immediate release/retry with only `outbox.last_error` is insufficient.
- On deadline/budget exhaustion, do not invent running or Adapter terminal
  truth. P3-3 must freeze one Task/Attempt outcome/reason mapping and prove it
  atomically before implementation. This is an activation-blocking decision.
- Preserve same-project serialization. Prove simultaneous Tasks on two distinct
  eligible project roots and capacity exhaustion with the real Direct Adapter.

### 6.3 Timeout, orphan and fencing

- Preserve the Direct absolute runtime deadline; heartbeat renewal must not move
  it. Add a separate absolute admission deadline for pre-dispatch accepted work.
- Preserve three different fences: (a) Store outbox claim token/time, (b)
  Adapter journal owner/generation/lease/runtime deadline, and (c) OS ownership
  lock. Never treat one as proof of another.
- Reconciliation may terminalize only from exact Adapter observation or from a
  frozen, proven recovery rule. Inability to acquire the OS lock is not proof of
  loss or safety to retry.
- Current “leave truth untouched” is safe against double execution but can leave
  a running-looking Task indefinitely. Before activation, freeze a bounded
  non-success orphan/reconciliation projection and its escalation/manual action
  without falsely terminalizing or reallocating the Attempt. This representation
  is the second activation-blocking decision.
- Exact Task, current Attempt, executor ref, source sequence, project binding,
  owner/generation and capability-profile digest must fence late callbacks and
  recovery. A successor cannot borrow predecessor cleanup or observations.

## 7. Shared schema and semantic ownership conflicts

| Boundary | Current owner | P3-3 rule |
|---|---|---|
| Task/Attempt lifecycle, events, command replay, outbox | `SqliteTaskStore` schema v4 | extend through one Store migration/transaction owner only; no historical sidecar restoring lifecycle authority |
| Adapter runtime attempt, heartbeat/deadline and project recovery facts | Direct journal in `project_code_executor.py` | retain Adapter ownership; reference exact facts from Store without duplicating a second lease owner |
| outbox delivery lease | Store claim token/time | keep delivery-only; never call it Executor ownership or recovery authority |
| OS process/worktree ownership | `_AttemptOwnershipLock` | keep as an external proof input; database expiry alone cannot override it |
| operation authorization/confirmation | current P3-2 command/policy/confirmation owners | historical control/receipt contracts are oracles; no second control stack |
| current-background selection | Store UI hint | projection only; never target/mutation authority |
| D1 checkpoint / D2 effect truth | not implemented in current canonical Store | reserve migration ownership for P3-4 `G4T`; do not precreate old component DDL in P3-3 |

The P3-3 schema packet should be reviewed together with P3-4 reservations so
profile/admission columns do not later collide with durability level/version,
checkpoint generation or effect-ledger ownership. Exact table/column names and
migration version are intentionally not authorized by this preparation.

## 8. Historical source-asset disposition

### 8.1 Selected for P3-3 admission work

| Asset | Source | Disposition | Preserve / rewrite / drop boundary |
|---|---|---|---|
| `P3A-DUR-01` | `6bc8d6ac`, `durability_contract.py` | `ORACLE` | preserve D0/D1/D2 and unknown-effect taxonomy; no second production decider or fact authority |
| `P3A-EXEC-CTRL-01` | `228c93c7`, `full_p3_executor_control.py` | `ORACLE` | preserve feature-off, exact binding, replay/conflict and zero-effect negatives; drop fake/candidate positive authority |
| `P3A-CTRL-TXN-01` | `fe2884db`, old control Core/Store | `REWRITE` | transplant reread/CAS/atomicity/failpoint tests only where P3-2/P3-3 touches current Store; drop old control owner |
| `P3A-EXEC-REC-01` | `6e1b4bfc`, `executor_recovery_store_foundation.py` | `PORT+ORACLE` | map canonical owner/generation/lease facts to current Direct journal; never create parallel lease authority |
| `P3A-EXEC-REC-02` | `6e1b4bfc`, old `task_store.py` | conditional `REWRITE` | preserve hash-chain/CAS/corruption/race tests; add minimal current Store facts only if current journal cannot express the frozen contract, otherwise drop production component |
| `3B-SECEX-POLICY` | `6306b21e`, `secure_executor_policy.py` | `REWRITE` | map declarative enforcement/resource vocabulary into the versioned profile and one real Adapter; readiness is not OS enforcement |
| `3B-SECEX-RECEIPT` | `96ca1306`, `secure_executor_enforcement.py` | `REWRITE` | fold exact capability/scope/Attempt/Adapter receipt checks into the single admission path; receipt never proves enforcement |
| `3B-SECEX-WIRE` | `df80cfb3`, secure wire contract | conditional adjusted `PORT` | preserve canonical/forgery/secret-safe oracles only if a real cross-process wire is selected; otherwise drop from P3-3 |
| `S85-RK-02` | `0c994b1b`, `task_revision.py` | adjusted `PORT` | map exact cleanup/verifier facts to current retry-readiness/capability response; remove same-Task/fixed-Attempt lineage and terminal inference |
| `S85-EXEC-01` | `0c994b1b`, old Executor/coordinator | `PORT+REWRITE` | preserve strict predecessor quiescence/unknown rejection; implement only through current Adapter seam, not private-field borrowing |
| `S85-FIXTURE-01` | `0c994b1b` + `8be8398a`, old revision Executor | `PORT` for test/config | preserve explicit disposable-root/marker/clean-base/forbidden-side-effect constraints; no general product capability |
| `S85-VERIFY-01` | `0c994b1b` + `8be8398a`, old revision Executor | `PORT+ORACLE` | preserve argv allowlist, bounds, redaction and mutation detection; verifier success is not Task terminal truth |
| `S85-EXEC-ORACLE-01` | `8be8398a`, restart coordinator test | `ORACLE` | rewrite against current outbox/reconcile, adding lease/orphan/multi-process dimensions; no redispatch of an accepted original Attempt |
| `S85-RECOVERY-01` | `8be8398a`, old Registry pump | `REWRITE+ORACLE` | preserve fence→dispatch→verify ordering as tests; drop parallel worker/single-process owner/poll-derived success |

### 8.2 Explicitly deferred to P3-4

| Asset | Source | P3-4 treatment |
|---|---|---|
| `P3A-D1-01` | `13459f2d`, `d1_checkpoint_port.py` | `PORT` canonical checkpoint wire at `G4D`; no resume authority |
| `P3A-D1-02` | `13459f2d`, same file | `ORACLE`; candidate selector remains authority-free |
| `P3A-D1-03` | `6d04ff61`, same-attempt recovery preparation | `REWRITE+ORACLE`; preserve negatives, drop positive until same-vs-linked Attempt is frozen |
| `P3A-D1-SQL-01` | final extraction source `b017a9e6`, `sqlite_d1_checkpoint_port.py` | `PORT` under current Store migration owner at `G1+G4T` |
| `P3A-D1-SQL-02` | `b017a9e6`, bounded transactional reader | highest-value `PORT+ORACLE` at `G4T`; caller-owned transaction, no lease/effect authority |
| `P3A-D2-01` | `74bf6788`, `external_effect_reconciliation.py` | `PORT+ORACLE` fact/decision layer at `G4D`; no dispatch/compensation/Task mutation |
| `P3A-D2-02` | `74bf6788`, deterministic fake | `ORACLE` only; never real D2 authority |
| `P3A-D2-SQL-01` | `bfd387a1` enhanced by `83de3eb8` | `PORT` effect ledger under current migration owner at `G1+G4T` |
| `P3A-D2-SQL-02` | `83de3eb8`, caller-owned reader | `PORT` at `G4T`; no write/decision/recovery authority |
| `P3A-SQL-COHOST-01` | `70648baf`, cohost integration test | `ORACLE`; expand for current Store and all selected components |
| `P3A-D1-D2-READ-01` | `e5603aa7`, current-effect compositor | optional small `PORT`/`ORACLE`; drop candidate-journal dependency if direct current facts suffice |
| `P3A-D2-03` | `6a8c8377`, candidate wire | optional audit metadata; omit if direct effect/Task settlement is canonical |
| `P3A-D2-CAND-TXN-01` | `3cd0f46c`, candidate runtime | port codecs/oracles, rewrite Store integration, drop journal if redundant |

3B privacy/auth/deploy/SLO/telemetry assets and S8.5 Bridge/Web/product assets
are outside this P3-3 admission packet. They are neither silently selected nor
credited here. P3-8/P3-9 may consume their separately gated oracles later.

## 9. Test and real-Adapter evidence matrix

The test names below are existing evidence targets at accepted source
`d40e0ee3`; this preparation did not rerun them. The accepted P3-1 review
records 376 migration/Core/auth tests, 544 product/text/Executor/compatibility
tests with two Windows-platform skips, 62 AgentServer/integration tests and 34
TypeScript contract tests, plus Ruff, compileall, build and diff checks. Those
are inherited P3-1 execution facts, not P3-3 closure.

| Claim / risk | Existing evidence examples | Real-path strength | P3-3 gap |
|---|---|---|---|
| accepted is not running | `test_outbox_retries_the_same_attempt_and_read_query_is_side_effect_free`; cancel-before-dispatch zero-effect; Store running projection tests | actual Core + SQLite Store | add capacity/busy/admission-deadline projection assertions |
| multi-Task identity and UI hint non-authority | `test_current_background_selection_allows_concurrent_tasks_and_replays_exactly`; `test_multi_task_pages_restart_and_selection_hint_never_redirects`; addressed result after restart | canonical Store | add two different-project simultaneous Direct Attempts and cross-Task late callbacks |
| Store claim/replay/fence | live cross-process claim not reclaimed; expired claim reuse; stale worker result fenced; released item does not starve another | actual SQLite Store/outbox | add bounded backoff/deadline and process-kill matrix |
| exact cancel | cancel before dispatch; active exact binding once; unknown dispatch retry; terminal/cancel race | Core/Store plus Adapter doubles/Direct tests | profile mismatch, wrong Adapter/profile digest, multi-Task zero side effects |
| D0 restart/reconcile | `test_restart_reconciles_only_the_original_attempt`; old callback supersession | Core/Store and Adapter observation | bounded unknown/orphan escalation and no false running/terminal claim |
| Direct lifecycle | `test_direct_d0_executor_persists_exact_lifecycle_without_schedule_carrier` | actual Direct Adapter, SQLite Direct journal, real Git worktree/lock; Agent worker is a test double | one production-profile declaration/selection test and physical Agent/Tool evidence |
| project isolation | `test_direct_executor_serializes_one_project_and_cannot_borrow_another_attempt_diff` | actual Direct journal/project binding | explicit concurrent distinct-project positive and max-32 capacity exhaustion |
| deadline/heartbeat | noncooperative deadline zero target effect; heartbeat failure interruption; renewed lease does not move deadline | actual Direct Adapter/journal/lock with worker double | admission deadline, stuck apply/orphan bounded projection, process-kill evidence |
| restart ownership | expired lease recovery; predecessor OS lock blocks successor recovery/deletion; applied/unchanged/ambiguous crash classification | actual journal, OS lock and Git facts | multi-process matrix and manual escalation contract when lock cannot be proven |
| retry cleanup | current Direct retry-readiness tests | real Direct cleanup facts | expose through versioned profile; legacy stays unsupported; no cross-Attempt borrowing |
| adjustment | `test_demo_itinerary_checkpoint_keeps_task_running_until_real_adjustment`; ordered durable/fenced adjustment | Direct demo checkpoint plus Store ordering | not generic update/input/pause/resume/priority; add negative declarations and zero effects |
| legacy carrier | `tests/integration/live_voice/test_formal_task_executor_adapter.py::test_formal_ed_dispatches_through_real_project_bound_legacy_carrier` | actual legacy AutoHarness carrier with stub scheduler/project executor | legacy has no retry-readiness and rejects adjust; cannot be selected as full P3-3 positive |
| capability selection | historical fake capability unit test only | fake | missing real version/digest, selector, mismatch-before-mutation, fallback and replay proofs |
| D1/D2 | historical candidates/oracles only | no current real Adapter | P3-4 must provide real checkpoint/effect Adapter, Store transaction and restart/fault proof |

For positive P3-3 acceptance, at least one selected capability profile must be
proved through the real Direct Adapter and current product factory. Deterministic
fakes may prove rejection, replay and races but cannot satisfy a positive
Executor/Agent/Tool claim. Every negative path must assert zero forbidden
Task/Attempt/outbox/Executor/project effects as required by `TESTING.md`.

## 10. Activation and mandatory re-review triggers

Main may activate a P3-3 implementation packet only after all of these are
recorded:

- accepted P3-1 integration source `d40e0ee3` and applicable scoped G0_FINAL
  foundation evidence; the controlled physical-candidate `FAIL` is preserved;
- canonical profile/requirement/select/admission owner and schema reservation;
- exact operation-version support table, with unsupported-before-mutation;
- accepted/queued/running boundary and bounded capacity/busy policy;
- admission timeout result and bounded orphan/reconciliation representation;
- exact Store-claim / Adapter-lease / OS-lock fencing contract;
- real Direct Adapter positive matrix and fake-negative matrix;
- selected historical asset list tied to exact source hashes and destination
  owners; and
- P3-4 reservation for durability level/version, checkpoint and effect truth.

Mandatory re-review is triggered by any change to the inspected HEAD; schema
version or Store migration owner; Task/Attempt/revision identity; Direct journal,
lease, deadline or OS lock; Executor Protocol/factory; operation or confirmation
contract; same-vs-linked Attempt choice; real Adapter selection; product feature
gates; or historical source hashes. A changed target requires rerunning the
relevant matrix, not inheriting this inventory by prose.

## 11. Explicit non-authority statement

Capability declarations are immutable facts, not proof that an Adapter enforced
them. Admission decisions authorize only the exact next Store transition they
name, not execution or terminal truth. Candidate receipts, cleanup ACKs,
verifier results, checkpoint candidates, effect observations, lease expiry,
outbox delivery and UI projections each remain evidence for their own bounded
owner. None grants Task, Attempt, Executor, Agent, Tool, project mutation,
recovery, compensation or terminal authority unless the accepted current
contract and real Adapter path independently prove that exact transition.

Accordingly, this file is an activation preparation checklist. It grants no
feature flag, migration, dispatch, recovery, control, P3-3 acceptance or P3-4
durability claim.
