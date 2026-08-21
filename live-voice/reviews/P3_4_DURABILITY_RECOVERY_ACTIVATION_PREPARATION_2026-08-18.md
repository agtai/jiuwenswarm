# P3-4 Durability / Recovery Activation Preparation (2026-08-18)

Status at the preparation snapshot: `PREPARATION ONLY / NOT YET ACTIVATED / NO CREDIT`

This document prepares the P3-4 D0/D1/D2 design checkpoint, source landing and
evidence matrix. It implements no production behavior, authorizes no schema or
Adapter change, and awards no implementation, review, test or acceptance
credit. Current priority and authority remain [STATUS](../STATUS.md); the
normative package contract remains [FULL_P3_EXECUTION_PLAN §7.5](../roadmap/FULL_P3_EXECUTION_PLAN.md#75-p3-4--d0-d1-and-d2-durabilityrecovery),
and risk/evidence closure remains governed by [TESTING](../../TESTING.md).
All activation/dependency language below is frozen to the 2026-08-18
preparation point; later P3-4 outcome is recorded in the
[implementation review](P3_4_DURABILITY_RECOVERY_IMPLEMENTATION_REVIEW_2026-08-21.md)
and current [STATUS](../STATUS.md).

Historical reuse is routed only through the frozen
[P3 implementation/reuse audit](P3_IMPLEMENTATION_COVERAGE_AND_HISTORICAL_REUSE_AUDIT_2026-08-18.md)
and [57-asset source manifest](P3_HISTORICAL_SOURCE_ASSET_EXTRACTION_MANIFEST_2026-08-18.md).
The preceding
[P3-3 activation preparation](P3_3_CAPABILITY_ADMISSION_ACTIVATION_PREPARATION_2026-08-18.md)
defines the capability/admission questions on which this packet depends.

## 1. Integrated baseline and non-authority boundary

| Role | Exact identity | Meaning |
|---|---|---|
| formal P3-G0 product source | `f24dd17d336c8266954f2d7299ca13bd0314d424`; close `8df7d38227b684177efca8cad83d77278ad42c19` | G0_FINAL product source and scoped P3-G0 close; D-086 preserves the controlled product-readiness candidate as `FAIL` |
| audit and P3-3 preparation lineage | `5787eda931159ba533e0a81ca8be8b744f449a8b`; `b0f6d381f728efbe21bdc193bece890e767d618c` | rebaselined frozen audit/manifest and the documentation-only P3-3 preparation on the same lineage |
| accepted implementation target | `d40e0ee391fdf162faa9d9938eb9b9610020c1a7` | clean accepted P3-1 source used for current code/test facts |

The former split histories and transient pre-amend G0 workspace description are
superseded by this integrated lineage. P3-1 is accepted at `d40e0ee3`, but no
physical G0 candidate PASS is invented and no P3-3 implementation is accepted.
Therefore:

- `d40e0ee3` is the accepted P3-1 code-fact base, not P3-4 acceptance;
- the P3-3 preparation is a question/landing inventory, not the hard dependency;
- historical candidates and test fakes are evidence inputs, not runtime facts;
- a checkpoint, lease expiry, cleanup ACK, effect observation, reconciliation
  receipt or verifier result grants only its explicitly accepted bounded fact;
  none alone authorizes recovery, replacement execution or Task terminal truth.

P3-4 production work is blocked until P3-3 is accepted on the integration
baseline. `G4D` and `G4T` below are proposed checkpoints, not opened Gates.

## 2. Required P3-4 design checkpoint

The Integration Owner must freeze both checkpoints before production divergence:

| Gate | Required accepted decision | Recommendation in this preparation |
|---|---|---|
| `G4D` | real D1/D2 Adapter(s), persisted capability/durability identity, same-versus-linked recovery Attempt | make Direct the first real D1/D2 candidate; keep legacy D0-only; require at least one real declared Adapter at D1 and one at D2 for feature-complete P3; use a linked recovery Attempt under the same Task |
| `G4T` | one current-schema migration and recovery transaction owner | `SqliteTaskStore` owns schema/migration and the atomic Task/Attempt/checkpoint/effect/recovery decision; Adapter runtime journal remains Adapter-owned; external calls stay outside Store transactions |
| D2 manual-settlement sub-gate within `G4D` | one command authority, confirmation/permission rule and command-ledger owner | require the accepted P3-2 command owner before product/user settlement; otherwise freeze a separately named operator-only settlement contract and keep it unreachable from normal voice/text commands |

If Direct cannot expose real checkpoint production/resume and stable effect
identity/observation seams, P3-4 must either select another real Adapter or
change feature-complete scope through the decision process. It must not promote
the current in-memory adjustment checkpoint, Git patch fingerprint or an
interface declaration to D1/D2.

## 3. Current path at `d40e0ee3`

Evidence locations below are `path:line @ d40e0ee3`.

| Boundary | Current symbol / behavior | Durable fact | P3-4 gap |
|---|---|---|---|
| product composition | `create_p3_composition_from_environment()` in `p3_authenticated_composition.py:2829`; constructs `DirectProjectCodeExecutorAdapter` at `:2903`, `SqliteTaskStore` and `PersistentTaskCore` | one selected Direct product path and one SQLite path | no versioned durability declaration/selection; legacy shares executor id but is not selected |
| startup order | `P3AuthenticatedComposition.start()` around `p3_authenticated_composition.py:1269` calls runtime `prepare_startup()`, then Core `reconcile_once()`, then periodic reconciliation | Adapter recovery precedes Store reconciliation; periodic interval is configured in `(0, 3600]` | no transactional D1/D2 admission phase or two-process recovery election |
| production Executor Protocol | `FormalExecutor` in `persistent_task_core.py:65`: `dispatch/cancel/adjust/settle_adjustment/status/retry_readiness` | exact Attempt delivery/status/cleanup seam | no capability version, checkpoint create/read/resume, effect intent/observation or manual resolution API |
| canonical Store | schema v4 at `task_store.py:60`; Task/Attempt/event/outbox/result transaction owner | atomic canonical lifecycle, command replay and outbox | no durability identity, checkpoint, effect ledger, recovery link or manual-effect settlement schema |
| Task/Attempt records | `PersistentTaskRecord` at `formal_task_models.py:671`; `PersistentAttemptRecord` at `:760` | exact Task/current Attempt/executor/ref/source sequence/retry number and reconciliation fields | no selected durability level/version, Adapter/profile digest, checkpoint producer/recovery provenance or effect head |
| Store delivery lease | five-minute `_OUTBOX_CLAIM_LEASE` at `persistent_task_core.py:62`; claim/release/complete at `task_store.py:2894/:2973/:3151` | claim-token CAS fences stale delivery workers | delivery lease is not Executor ownership, runtime timeout or recovery authority |
| Core D0 reconciliation | `PersistentTaskCore.reconcile()` at `persistent_task_core.py:747` resets expired claims, drains outbox and queries every original nonterminal Attempt; it explicitly creates no replacement | known observations apply; unavailable stays pending; lost resolves interrupted; superseded callbacks do not mutate current Attempt | no bounded unknown/manual state, checkpoint selection, D2 effect safety reread or authorized linked recovery creation |
| Direct runtime record | `_DirectAttempt` at `project_code_executor.py:1144`; `_DirectProjectAttemptJournal` at `:1185`; table `live_voice_formal_project_attempts_v1` at `:90` | Attempt/task/ref/spec/project, source sequence, before/expected Git facts, result/artifacts, owner lease, absolute runtime deadline and cancel flag | separate component table with no checkpoint/effect/profile fields and no Task mutation authority |
| Direct ownership | `_AttemptOwnershipLock` at `project_code_executor.py:722`; journal owner/lease/heartbeat `:1684/:1740`; runtime deadline terminalization `:1358` | cross-process OS ownership plus CAS lease/deadline facts; heartbeat never moves absolute deadline | lock failure leaves truth untouched indefinitely; there is no bounded orphan/manual projection |
| Direct restart | `_DirectProjectAttemptJournal.recover_expired()` at `project_code_executor.py:2084`; `DirectProjectCodeExecutorAdapter.prepare_startup()` at `:2514` | after OS ownership, pre-apply work becomes interrupted; exact applied state becomes completed; unchanged state becomes interrupted; ambiguous apply remains unknown | this is bounded D0 Git-apply classification, not general D2 evidence for Agent/Tool/external effects |
| Direct lifecycle | `dispatch()` at `:2593`, `_run_attempt()` at `:2972`, heartbeat at `:3407`, `cancel()` at `:3542`, `status()` at `:3613`, `close()` at `:3732` | actual Direct Adapter, isolated Git worktree, exact apply/result lifecycle and cleanup | no checkpoint resume; worker/Agent state is not restorable; effect calls are not ledgered with stable keys |
| Direct cleanup | `retry_readiness()` at `:2418` proves exact worker/apply/interruption/retained-cleanup/journal-lease quiescence | safe predecessor cleanup input | cleanup does not prove checkpoint integrity, effect safety or recovery authorization |
| adjustment checkpoint | `_AdjustmentCheckpoint` at `project_code_executor.py:2306`, held in `_adjustment_checkpoints`; positive is Demo-itinerary gated | in-process ordered adjustment safe point only | not persisted, versioned, integrity checked or restart-readable; no D1 credit |
| legacy Adapter | `ProjectCodeExecutorAdapter` at `project_code_executor.py:3971`; exact `run_task/status/cancel` carrier mapping | actual compatibility Adapter can reconcile a stable legacy ref and report known/lost/unavailable | not selected by current product factory; no `retry_readiness`, D1/D2 API or current real restart/fault closure |

The Store string `durability: sqlite_outbox` and comments that call adjustment
settlement a checkpoint describe Store delivery durability, not P3-4 D1.

## 4. Real Adapter D0/D1/D2 declaration matrix

| Adapter / composition | D0 today | D1 today | D2 today | Allowed declaration before new work | Required proof to change declaration |
|---|---|---|---|---|---|
| `DirectProjectCodeExecutorAdapter` (current product selection) | **PARTIAL real seam, explicitly D0-only**: Task persists independently of voice; journal/lease/deadline/OS lock and restart classification exist; exact Direct tests exercise SQLite and Git worktrees, though Agent workers are usually doubles | **unsupported**: only an in-memory Demo adjustment safe point | **unsupported**: exact target-patch crash classification exists, but there is no stable general Agent/Tool/effect ledger or manual settlement | D0 candidate only, still subject to accepted P3-3 profile and exact disconnect/restart evidence | real checkpoint producer/resume boundary, canonical Store integration, stable effect-key/ledger boundary, fault/two-process tests and actual selected product composition |
| `ProjectCodeExecutorAdapter` (legacy compatibility path) | **PARTIAL non-product seam**: stable carrier idempotency/status/cancel and known/lost/unavailable mapping; current factory does not select it | **unsupported** | **unsupported** | compatibility D0 observation only; not a feature-complete selection | distinct Adapter/profile identity, real selected composition, retry/lease/timeout contract and full restart/fault evidence; otherwise remain unsupported |
| `ExecutorPort` / deterministic historical fakes | in-memory only; restart false | unsupported | unsupported | test oracle only | cannot gain positive product credit; replace positives with a real Adapter |

Both real Adapters currently publish the same
`jiuwenswarm_code_agent.project_code` executor id. P3-3/P3-4 must persist a
distinct Adapter/profile/durability version so restart cannot select the other
implementation merely because the logical executor id matches.

## 5. D0 contract and recovery sequence

### 5.1 Boundary to preserve

- Voice interruption, response replacement, Session disconnect and browser
  reconnect must not widen to `task.cancel`. While application and Direct worker
  remain alive, the exact Task/Attempt continues and remains queryable.
- Application/process restart is not continuation under D0. It reconciles the
  persisted original Attempt to known terminal, interrupted, unavailable or
  unknown. It does not allocate a replacement or promise resumed work.
- Store outbox reclaim, Executor lease expiry and OS ownership acquisition are
  independent facts. All three relevant fences must pass before mutation.
- Repeated startup reconciliation is idempotent. A second process may observe or
  lose an election, but may not redispatch, delete, apply or terminalize work
  owned by the first.

### 5.2 Required startup order after P3-4

1. Open and audit the one current Store schema; reject partial/unknown schema
   before Adapter or project effects.
2. Let the exact persisted Adapter/profile inspect its runtime journal. Direct
   may recover only after acquiring the exact OS ownership lock and matching
   owner/lease/deadline/spec/project facts.
3. Core reclaims only expired Store outbox claims, redelivers exact items and
   applies only exact monotonic Adapter observations.
4. In one caller-owned Store transaction, reread current Task/Attempt/profile,
   recovery generation, verified checkpoint prefix, verified D2 effect prefix,
   lease/cleanup facts and cancellation/terminal fences.
5. Purely decide no action, wait, interrupted, linked D1 recovery, D2 reconcile
   or manual resolution. Commit any linked Attempt/outbox or manual projection
   atomically. Invoke no Adapter inside this transaction.
6. Outbox delivery invokes only the persisted Adapter/profile. Subsequent
   observation settlement repeats exact binding and effect-head checks.

At D0, step 4 must never manufacture a D1/D2 action. Undeclared levels return
`unsupported` with zero checkpoint/effect/recovery writes and zero Executor,
Agent, Tool or project effects.

## 6. D1 checkpoint and linked-recovery decision

### 6.1 Recommended identity and integrity contract

An immutable checkpoint record should bind at least:

| Fact group | Required exact facts |
|---|---|
| checkpoint identity | `checkpoint_id`, `task_id`, producer `attempt_id`, monotonic checkpoint sequence and canonical wire version |
| producer | Adapter/profile id+version+digest, durability capability version, producer build/protocol identity and recovery generation |
| content integrity | canonical bytes, schema/version, bounded content length, digest algorithm+digest, input/state/context fingerprints and completeness marker |
| Task context | Task spec/origin fingerprint, server-resolved scope/project/root, project head/tree/content base, Task event head and relevant command/revision identities |
| execution context | Agent/model/tool/provider configuration versions required for replay, excluding credentials; checkpoint producer/source sequence and runtime policy version |
| effect safety | D2 ledger head/prefix fingerprint and a pure classification of `no_effect`, `safely_retryable`, `applied`, `unknown` or `manual_required` |
| provenance | predecessor checkpoint when any, created/accepted facts, linked recovery Attempt(s) and the exact terminal/result-producing Attempt |

The digest detects corruption; it does not by itself prove trust, freshness,
effect safety or resume authority. Reads are globally bounded and reject
duplicate/conflicting sequence, noncanonical bytes, unsupported version,
oversized content, wrong scope/project/Attempt and corrupt surrounding rows
without returning a partial usable prefix.

### 6.2 Effect-safe selection

A checkpoint is eligible only if the current transaction proves all of:

- exact current Task and predecessor Attempt, selected Adapter/profile and D1
  capability version;
- immutable, complete, integrity-valid checkpoint and exact context versions;
- predecessor worker/apply/interrupt/cleanup/lease/OS ownership quiescence;
- no current cancel/terminal/superseding recovery winner;
- D2 ledger prefix matches the checkpoint-bound effect head; and
- every effect after/before the checkpoint is proven absent or safely retryable.

`unknown`, merely `dispatched`, applied-without-idempotent-observation, corrupt,
stale, missing or cross-bound effect truth forbids automatic D1 recovery. It
enters bounded reconciliation/manual handling; it does not fall back to D0
redispatch.

### 6.3 Recommended choice: linked recovery Attempt under the same Task

Recommendation: preserve `task_id` and create a new, explicitly linked recovery
`attempt_id`; do not revive the producer Attempt.

Rationale:

- one Attempt continues to mean one execution ownership/source-sequence epoch;
- the producer journal, lease, result and effect facts stay immutable;
- a new Direct process/worktree cannot accidentally impersonate the old owner;
- late predecessor lifecycle/effect evidence can be retained without projecting
  it onto the new current Attempt; and
- recovery count, retry budget and result producer remain auditable.

The linked recovery is neither a new Task revision nor ordinary user retry. In
one Store transaction it must fence the producer, consume a bounded shared
recovery/retry budget, record producer Attempt/checkpoint/effect-head/profile
provenance, allocate the new Attempt and enqueue exactly one recovery dispatch.
It must not reset the current maximum-attempt policy silently. The resulting
`TaskResult`, if any, binds the recovery Attempt; provenance continues to name
the checkpoint-producing Attempt.

If this recommendation is accepted, the old `P3A-D1-03` same-Attempt positive
is dropped. Its exact binding, lease, effect and forgery negatives are retained
and rewritten for the linked choice. Selecting same-Attempt recovery instead
requires an explicit design decision and complete re-review of lifecycle,
source-sequence, lease and result semantics.

### 6.4 Real Adapter landing

Direct may declare D1 only after a real JiuwenSwarm Agent/Tool execution can
produce and resume the canonical checkpoint through a public Adapter seam.
Deserializing a test fixture or restarting from the original instruction is not
resume. Legacy remains D1-unsupported unless its real carrier independently
implements the same contract and evidence.

## 7. D2 stable effects and manual resolution

### 7.1 Stable operation/effect ledger

Before each supported external effect, allocate one stable **logical operation
identity** bound to Task, immutable origin/producer Attempt, operation kind/
ordinal, exact target, canonical intended-effect fingerprint and Adapter/profile
version. The origin Attempt is provenance; it does not change when recovery
continues the operation. Each external dispatch or observation separately binds
an **actor Attempt** (the origin Attempt or one linked recovery Attempt), its
dispatch ordinal and recovery generation. Before a linked Attempt may reuse the
logical operation id, the Store must commit an explicit continuation
authorization bound to the current Task/Attempt/checkpoint/effect heads and
cancel/terminal fences. A different intended effect receives a different id;
the same id with different canonical bytes, origin Attempt or target is a
conflict, never replay. An actor Attempt cannot borrow another Task's or
unlinked Attempt's logical operation.

The canonical ledger must append immutable facts in order:

1. intent registered and committed before the external call;
2. dispatch attempt with stable provider/tool idempotency key where supported;
3. provider/tool receipt or explicit lack of receipt;
4. independently observed effect (`no_effect`, `applied`, `unknown`, or an
   accepted compensation fact);
5. settlement (`resolved`, `compensated`, `manual_required`) with exact evidence
   head, Task, logical operation, immutable origin Attempt and latest authorized
   actor Attempt binding.

The phrase “exactly once” is not allowed unless the external boundary proves
it. P3-4 promises exactly-once-equivalent behavior: idempotent stable-key replay
or explicit observation/reconciliation/manual resolution.

### 7.2 Process-death and unknown rule

Process death after the external call but before Store acknowledgement is
`unknown`. Automatic retry is forbidden until a real observation proves
`no_effect` or the exact provider contract proves safe idempotent replay.
Current Direct Git before/expected/content/artifact facts can be one bounded
file-apply observation source; they do not prove Agent tool, network, message,
payment or other external effects.

For a declared Direct D2 profile, every enabled effecting Agent/Tool operation
must either accept the stable key and expose observation, or be rejected as
unsupported before execution. Side-effect-free tools may be declared separately
but still need exact classification. A final patch alone cannot summarize
unobserved tool effects.

### 7.3 Manual resolution

After a bounded reconcile deadline/attempt budget, unresolved effect truth
enters a durable explicit manual-required state. Recommended presentation is a
nonterminal `decision_required` Task projection backed by a separate canonical
effect-reconciliation record; it must not overload completed/failed/cancelled.

Manual settlement requires an authorized, addressed, idempotent command bound
to the exact Task, logical operation id, immutable origin Attempt, latest
authorized actor Attempt, effect-ledger head, observed evidence and chosen
outcome. It atomically appends settlement and re-evaluates Task/recovery truth.
It cannot rewrite history, erase unknown effects, automatically mark the Task
completed, or authorize compensation unless the real Adapter separately proves
that compensation action and receipt.

There must be exactly one command authority. The recommended product landing is
the accepted P3-2 command envelope/authorization/confirmation/ledger owner with
a distinct `settle_external_effect` operation and operator-only permission. It
must not reuse ordinary `provide_input` or a generic `decision_required` reply.
If P3-2 is not accepted when D1 work begins, P3-4 may define only an isolated
operator-only settlement contract whose adapter is not registered in normal
voice/text routing; D2 manual-settlement activation remains blocked until the
integration owner chooses one path and deletes/forbids the other. Replay,
conflict, stale-head, cross-Task/Attempt and feature-off cases must reuse the
single selected command ledger and assert zero effect/Task mutation on reject.

## 8. Restart, race and fence matrix

| Scenario | Required invariant / settlement |
|---|---|
| voice/Session disconnect while app lives | no implicit Task cancel; same Attempt continues and remains queryable |
| restart before Adapter acceptance | reuse exact accepted Attempt/outbox; no replacement or running claim |
| restart with live foreign Direct owner | OS lock/lease prevents recovery and cleanup; bounded pending/orphan projection, zero redispatch |
| expired lease/deadline before apply | after exact OS ownership and CAS, interrupt original Attempt; D1 recovery only through the accepted linked transaction |
| crash while applying target patch | exact expected applied state may settle completed, exact unchanged state interrupted, ambiguous state unknown/manual; never blind reapply |
| crash after effect intent, before call | observation may prove no effect; only then safe linked recovery/retry |
| crash after external call, before receipt | unknown; query by stable operation id; no automatic retry |
| two startup processes | Store `BEGIN IMMEDIATE`/CAS, Adapter owner generation and OS lock elect one mutator; loser is read-only/pending |
| cancel races D1 recovery creation | one Store transaction wins: cancel prevents linked dispatch, or linked Attempt becomes current and cancel targets it; predecessor effect reconciliation remains |
| cancel with unknown/applied effect | stops further supported work but does not erase or settle effect truth |
| runtime timeout during resumed work | terminalize only exact linked Attempt under its own absolute deadline; no Task/recovery-budget reset |
| reconciliation timeout | escalate to explicit manual-required, not completed/failed by inference and not replacement execution |
| late predecessor lifecycle result | may be retained as predecessor diagnostic/evidence; cannot overwrite current linked Attempt or Task terminal/result |
| late predecessor effect observation | append to the predecessor-bound effect ledger and re-evaluate safety; do not discard it or project lifecycle onto the linked Attempt |
| stale outbox worker | claim-token/profile/Attempt/recovery-generation fence produces zero Adapter and Store settlement effects |
| schema/checkpoint/ledger corruption | fail closed before Adapter/Agent/Tool/project effects; no partial prefix or automatic repair that changes authority |

The bounded orphan representation and admission-timeout result identified by
the P3-3 preparation must be accepted first. P3-4 consumes those facts; it does
not create a competing state machine.

## 9. Single-owner schema and transaction landing

Recommended target file names below are implementation landings, not authorized
file creation by this review.

| Semantic boundary | One owner / proposed landing | Explicit conflict to avoid |
|---|---|---|
| pure durability/checkpoint/effect wires and deciders | a bounded current module such as `durability_contract.py`, imported by current models/Core/Adapter | no second lifecycle, command or recovery authority; pure decisions perform no I/O |
| persisted durability/profile/recovery identity | current `formal_task_models.py` plus Store codecs | do not reuse command authorization `required_capabilities` or infer Adapter identity from shared executor id |
| schema, migration, checkpoint/effect rows, event heads and recovery CAS | `task_store.py` under one schema version/migration verifier | do not copy historical component auto-DDL or add an S8/3A sidecar owner |
| checkpoint/effect caller-owned readers | helper module callable only with the active same-database Store transaction | readers never open/commit/rollback, write, choose recovery or call Adapter |
| orchestration and outbox | `persistent_task_core.py` | no external call inside SQLite transaction; no second recovery pump |
| Direct checkpoint/effect production, observation and resume | `project_code_executor.py` public Adapter seam | keep runtime journal/lease/OS lock Adapter-owned; no direct canonical Task mutation |
| D2 manual-settlement command | accepted P3-2 command service/ledger; otherwise one explicitly isolated operator-only P3-4 contract pending integration decision | no ordinary `provide_input`, no parallel voice/text command authority, and no settlement from a presentation ACK |
| startup/profile selection | `p3_authenticated_composition.py`, integrated centrally after P3-3 | do not register Direct and legacy ambiguously under only the shared logical executor id |
| owned tests | `test_durability_contract.py`, `test_persistent_task_core.py`, `test_project_code_executor.py`, `test_p3_authenticated_composition.py`, plus a current integration recovery test | no historical stage runner/fake under production paths |

### Transaction boundaries

- Checkpoint append: immutable bounded row and head/CAS commit; no Adapter call.
- Effect dispatch: commit intent first, call externally, then append receipt/
  observation in a new transaction.
- Recovery admission: one `BEGIN IMMEDIATE` rereads Task/current Attempt/profile,
  retry/recovery budget, checkpoint prefix, effect prefix, reconciliation state,
  cancel/terminal fence and Adapter cleanup/lease facts; then atomically creates
  linked Attempt/provenance/event/outbox or manual state.
- Settlement: the one selected command ledger consumes its idempotency key and,
  with verified Adapter/effect observation, appends settlement plus canonical
  Task/Attempt/result/event mutation in one Store transaction where the external
  boundary permits; otherwise unknown remains explicit.

The existing Direct runtime table may remain a cohosted Adapter component, but
its initializer must not race or silently migrate canonical D1/D2 tables.
Cross-database reads cannot claim atomic recovery. `G4T` must name the actual
schema version, migration/rollback compatibility and initialization order only
after the accepted P3-3 integration schema is known.

## 10. Historical asset landing manifest

`PORT` means extract exact current-owned code; `ORACLE` means tests/contracts
only; `REWRITE` means preserve behavior but rebuild integration; `DROP` means do
not land that historical production component. Every positive still needs a
real current Adapter.

| Asset | Exact source / key symbols | Decision | Proposed current target | Test/fixture landing and preserved boundary |
|---|---|---|---|---|
| `P3A-DUR-01` | `6bc8d6ac`, `durability_contract.py`: `DurabilityLevel`, recovery/effect truth, `decide_recovery()` | `ORACLE`, optionally port one pure decider only after ownership freeze | current pure durability contract | migrate `live_voice_durability_v1` and active/terminal, unknown-effect, safe-checkpoint, schema-compatibility negatives; drop any second production decider |
| `P3A-D1-01` | `13459f2d`, `d1_checkpoint_port.py`: binding/producer/`D1Checkpoint` canonical bytes/checksum | `PORT` at `G4D` | current checkpoint wire/model | `test_d1_checkpoint_port.py` roundtrip, noncanonical, duplicate, integrity and capability-version cases; type has no resume authority |
| `P3A-D1-02` | `13459f2d`: Port/fake/snapshots/`select_recovery_candidate()` | `ORACLE` | pure selection tests; real reads move to Store transaction | keep immutable/monotonic/latest-complete/exact-binding and zero-mutation tests; drop fake positive authority |
| `P3A-D1-03` | `6d04ff61`, `same_attempt_checkpoint_recovery.py` | negatives `REWRITE+ORACLE`; positive `DROP` | linked-recovery admission transaction | retain auth/binding/checkpoint/effect/lease/generation/forgery negatives rewritten for linked Attempt |
| `P3A-D1-SQL-01` | final source `b017a9e6`, `sqlite_d1_checkpoint_port.py`: immutable write/read/component audit | `PORT`, DDL `REWRITE` at `G4T` | current Store schema/checkpoint methods | reopen/concurrent replay-conflict/binding/corrupt bytes/failpoint/zero-side-effect tests; drop old self-owned DDL |
| `P3A-D1-SQL-02` | `b017a9e6`: bounded verified record/prefix/readers | `PORT+ORACLE` | caller-owned Store transaction reader | preserve dirty/temp shadow, global audit, oversize/cross-scope bounds and no-partial-prefix tests; revalidate historical bounds |
| `P3A-D2-01` | `74bf6788`, `external_effect_reconciliation.py`: binding, intent/receipt/observation/outcome, `decide_reconciliation()` | `PORT+ORACLE` | current pure effect fact/decision contract | migrate `live_voice_external_effect_reconciliation_v1`, manual/compensation/unknown/applied/no-effect and identity-borrowing tests; no dispatch/Task mutation |
| `P3A-D2-02` | `74bf6788`, `DeterministicExternalEffectPortFake` | `ORACLE` | tests/support only | retain replay/conflict/read-only observation negatives; replace every positive with real Direct Adapter evidence |
| `P3A-D2-SQL-01` | `bfd387a1` enhanced by `83de3eb8`, `SqliteExternalEffectLedger` | `PORT`, DDL `REWRITE` | current Store-owned effect ledger | reopen/order/identity/manual/compensation/concurrency/failpoint/schema corruption tests; no Provider/Task authority |
| `P3A-D2-SQL-02` | `83de3eb8`, verified ledger prefix/caller-connection helpers | `PORT` | caller-owned Store transaction reader | caller transaction, same DB, global audit, unknown/applied and canonical prefix tests; never writes/decides recovery |
| `P3A-SQL-COHOST-01` | `70648baf`, D1/D2 cohost integration test | `ORACLE` | current Store migration integration tests | expand both historical initialization orders to current schema + Direct component + D1/D2; one migration owner |
| `P3A-D1-D2-READ-01` | `e5603aa7`, current-effect candidate facts/compositor | small `PORT+ORACLE` only if useful | direct checkpoint/effect/current-Task reader | preserve stale head/prefix, wrong target, corruption and authority-false cases; drop candidate-journal dependency by default |
| `P3A-D2-03` | `6a8c8377`, D2 candidate manifest/receipt/fingerprints | default `DROP` production; selected fingerprint `ORACLE` | omit unless accepted audit metadata need appears | retain nested-forgery/all-authority-false tests only; direct effect settlement is preferred |
| `P3A-D2-CAND-TXN-01` | `3cd0f46c`, candidate runtime codecs and old Core/Store seams | codecs/oracles `PORT`; Store integration `REWRITE`; journal default `DROP` | one current recovery transaction | preserve caller transaction, current truth reread, hash/CAS/failpoint/stale/corruption tests without restoring journal if redundant |
| `P3A-EXEC-REC-01` | `6e1b4bfc`, recovery epoch/Attempt canonical facts | `PORT+ORACLE` | map minimal facts to current Direct lease/generation and linked provenance | canonical parity/expiry/forgery/authority-false tests; never create parallel lease or infer quiescence |
| `P3A-EXEC-REC-02` | `6e1b4bfc`, old Store recovery event chain | conditional `REWRITE`, component `DROP` if current facts suffice | current Store recovery event/provenance fields only if required | port replay/conflict/concurrency/failpoint/corruption oracles; candidate never authorizes recovery |
| `P3A-CTRL-TXN-01` | `02911fce`, transactional command reader/commit/replay/CAS failpoint oracles | conditional `ORACLE`; required if the accepted P3-2 command owner is used for D2 manual settlement | the one current command-ledger/Store transaction owner | preserve exact addressed replay/conflict/stale-head/CAS/failpoint and zero-side-effect rejects; do not restore the historical command service or a second Store owner |
| `S85-RK-02` | `0c994b1b`, cleanup/verifier value contracts | adjusted `PORT` | current cleanup/capability and recovery-readiness facts | preserve exact serialization/conflict/unknown combinations; remove same-Task/fixed-Attempt and terminal inference |
| `S85-EXEC-01` | `0c994b1b`, old Direct fence/cleanup/coordinator | `PORT+REWRITE` | current Direct `retry_readiness` plus D1 recovery preparation | preserve noncooperative/unknown/already-applied cleanup rejection; ACK gives no D1/D2 credit |
| `S85-EXEC-ORACLE-01` | `8be8398a`, coordinator restart/reopen test | `ORACLE` | current Core/Direct restart integration | avoid redispatch, reconcile exact terminal, add two-process/lease/orphan/linked-Attempt/effect dimensions |
| `S85-RECOVERY-01` | `8be8398a`, Registry `fence_once→dispatch_once→verify_once` pump | sequencing `ORACLE+REWRITE`; old pump `DROP` | existing Core outbox/reconcile owner | preserve ordering/restart negative cases; no parallel worker, polling terminal inference or single-process authority |

Assets outside these P3-4 chains remain deferred to their manifest package.
No whole 3A/3B/S8.5 branch or historical schema is selected by this document.

## 11. Tier-3 D-032 and fault evidence plan

Existing target evidence is useful but not P3-4 closure. The accepted P3-1
review records 376 migration/Core/auth tests, 544 product/text/Executor/
compatibility tests with two Windows-platform skips, 62 AgentServer/integration
tests and 34 TypeScript contract tests, plus Ruff, compileall, build and diff
checks. This preparation did not rerun them.

| D-032 | Existing target evidence examples | Mandatory P3-4 addition |
|---|---|---|
| `P` | `test_direct_d0_executor_persists_exact_lifecycle_without_schedule_carrier`; production resolver facade executes exact D0 root | voice disconnect D0; real Direct D1 checkpoint→linked resume→result; bounded declared D2 effect→observation→settlement |
| `N` | wrong root/binding, feature-off, symlink/junction and missing journal fail closed | undeclared D1/D2, corrupt checkpoint, unknown effect, wrong Adapter/profile/context and forged manual settlement with zero forbidden effects |
| `B` | closed attempt/cleanup timeouts and absolute deadline bounds | checkpoint item/store/prefix bounds, ledger rows/prefix, recovery count/deadline and manual evidence bounds |
| `S` | exact accepted/running/terminal and immutable result; retry predecessor history | linked producer/recovery lifecycle, manual-required nonterminal state, non-revivable producer/result ownership |
| `T` | heartbeat/deadline boundary; stale outbox and source-sequence fencing | crash at every checkpoint/effect/settlement boundary; reordered checkpoint/effect/late predecessor evidence |
| `C` | Store claim races, concurrent retry winner, same-project serialization | two processes elect one recovery/manual settler; checkpoint/effect duplicate/conflict; cancel versus linked recovery |
| `R` | expired Direct lease recovery, apply-crash classification, original-Attempt Core reconcile | repeated restart idempotence, D1 resume without duplicate effects, D2 unknown/query/manual, schema migration failpoints |
| `I` | Task/Attempt/project/ref/spec/OS-lock exact binding | profile/durability/checkpoint/effect/context/recovery-generation cross-Task/project/Adapter isolation |
| `F` | Direct feature-off zero binding/Agent work; unavailable/lost non-success | undeclared level unsupported; Adapter unavailable, observation unavailable, unsupported checkpoint version, and feature-off retains D0 with zero D1/D2 authority/effects; migration behavior follows the accepted `G4T` contract |
| `K` | schema v1/v3→v4 migrations and unrelated component cohost | accepted current schema→new schema, rollback/failpoint, current D0/legacy compatibility and persisted version rejection |
| `X` | actual Direct class + SQLite journal + real Git worktrees/locks; legacy carrier integration uses actual service seam with stubs | current product factory, actual Direct Agent/Tool checkpoint/effect seam, process restart/two-process and disposable-project evidence; fakes only supplement negatives |

### Fault-injection points

At minimum inject failure: before/after checkpoint row and head update; corrupt
checkpoint bytes/version/digest/context; after effect intent commit; during
external call; after effect but before receipt; after receipt before observation;
after observation before Task settlement; before/after linked Attempt/outbox
commit; during Direct resume startup; during heartbeat; at runtime deadline;
during target apply; during cancel; during manual settlement; at every schema
migration boundary; and while a second process owns the OS lock/lease. Every
case asserts exact persisted facts after reopen and zero forbidden duplicate
Agent/Tool/file/external/other-Task effects.

The real-path boundary must name the actual selected Adapter/profile, isolated
SQLite database, disposable no-remote project, process identities and effect
service/tool without credentials. A production class backed only by a fake
Agent or fake effect port cannot close the corresponding positive D1/D2 claim.
Tier 3 also requires cold complete-diff review, one independent module review,
cumulative integration-seam review and eventual P3-9 exact-candidate evidence.

## 12. Activation checklist and re-review triggers

P3-4 implementation may start only when all are recorded on one integration
baseline:

- the scoped P3-G0 foundation and P3-1 are already accepted on the exact
  G0_FINAL/`d40e0ee3` lineage; P3-3 remains the unsatisfied hard dependency;
- STATUS activates one Tier-3 P3-4 packet with owner, dependencies, scope,
  exclusions, D-032 matrix, migration, real path and review destination;
- `G4D` accepts Direct or another exact real D1/D2 Adapter, persisted profile/
  durability versions, the linked recovery Attempt decision, the logical-
  operation/origin-Attempt/actor-Attempt/continuation identity split, and the
  D2 manual-settlement command sub-gate;
- `G4T` accepts one Store migration/transaction owner and cohost strategy;
- admission timeout/orphan semantics from P3-3 are frozen;
- every unsupported level/operation is declared and tested before mutation;
- historical assets have exact source objects reopened and each row is marked
  landed, deferred or rejected against current HEAD; and
- the real checkpoint/effect and fault harness is available on a disposable,
  isolated target.

Mandatory re-review is triggered by any change to: target/integration HEAD;
P3-3 profile/admission identity; Task/Attempt/retry/result state; same-versus-
linked decision; Store schema/migration/transaction owner; Direct journal,
lease/deadline/OS lock/Git apply; Adapter/Agent/Tool API; effect provider
idempotency/observation semantics; cancellation/manual-resolution contract;
startup order; historical source hash; or feature-complete D1/D2 requirement.

## 13. Explicit exclusions and forbidden claims

This preparation does not implement or accept D0, D1 or D2; run migrations;
select or enable an Adapter/profile; create a checkpoint/effect ledger; resume
an Attempt; perform reconciliation/manual settlement; change retry budgets;
modify product composition; or verify a physical Agent/Tool/external-effect
journey. It does not add to accepted `d40e0ee3` P3-1 credit, make P3-3
complete, activate P3-4, or open `G4D/G4T`.

In particular, interface support, canonical bytes, checksum success, checkpoint
presence, cleanup/quiescence, lease expiry, OS lock acquisition, outbox ACK,
effect intent/receipt, verifier success, candidate selection and UI projection
are facts—not execution or terminal authority. Only the accepted current
transaction plus the real selected Adapter can authorize the exact next action,
and only authoritative observed settlement can change canonical Task truth.
