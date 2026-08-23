# P3 historical source-asset extraction manifest — 2026-08-18

> **Historical source inventory with a 2026-08-19 routing snapshot.** Source assets were
> inspected read-only against product baseline
> `7a8ba7e82042e188efe6adbac98d47363b0d5d8e`; their source facts remain fixed,
> while activation mapping is always validated against current HEAD. At that
> routing snapshot, P3-G0 had passed only its D-086 authoritative-foundation
> Gate, exact product source `f24dd17d` remained a failed controlled
> product-readiness candidate, P3-1 was accepted at
> `d40e0ee391fdf162faa9d9938eb9b9610020c1a7`, and P3-2 was active.
> This manifest grants no implementation or acceptance credit. Package
> status, dependencies and the active packet always remain in [STATUS](../STATUS.md)
> and the [complete P3 plan](../roadmap/FULL_P3_EXECUTION_PLAN.md). Package-level
> estimates, Git topology and evidence boundaries are in the companion
> [P3 implementation/reuse audit](P3_IMPLEMENTATION_COVERAGE_AND_HISTORICAL_REUSE_AUDIT_2026-08-18.md).

## 1. Why this manifest exists

Historical discovery is centralized once so future workers do not independently
reinterpret the same branches, duplicate semantic owners or mistake a reader,
candidate, fake, policy or wire document for runtime authority. The extraction
unit is a **source asset**, not a commit: one mixed commit may contain several
assets with different target packages and eligibility.

This inventory names domain/authority symbols and semantically important private
transaction seams. Generic scalar validators and every parameterized test case
are not separate assets; their owning source/test file is still recorded.

The source population is bounded and complete: all 13 requested 3A commits, all
8 requested 3B commits, all 3 specified sibling candidates and all 9 requested
S8.5 commits were inspected (**33/33**), with the preceding S8.5 contract also
read as dependency context. The 57 assets exhaust the materially reusable or
historically significant content of those requested diffs at module/contract/
fixture/oracle/provenance granularity. They do not claim coverage of every other
commit or branch in repository history, and they are intentionally not 57
ready-made cherry-picks.

The operating split is deliberate:

- **Now, centrally:** freeze source commit/file/symbol, fixture and representative
  tests, dependency chain, actual authority boundary, current overlap, target
  package, earliest gate and `PORT/ORACLE/REWRITE/FUTURE/HISTORY` disposition.
- **At package activation:** the Integration Owner selects admitted asset IDs and
  fills the exact current target file/symbol, schema migration, patch boundary,
  test destination, command and ownership lease against the then-current HEAD.
- **Worker responsibility:** verify the selected source facts, implement only the
  assigned mapping, transplant the named oracles and report evidence. A worker
  must not rescan all historical branches or silently reactivate a rejected
  semantic choice.

This avoids both failure modes: repeated worker forensics and prematurely frozen
line-level patches before P3-1/P3-3 and later package checkpoints settle the
current target. Current changes are recoverable through Git history; no separate
G0 delta inventory is required.

### 1.1 Verified source recovery locator

The 24 commits in the 3A, 3B and three sibling-candidate populations are absent
from the current `live voice hx` object database. On 2026-08-19 their named refs
were also absent from configured GitHub remote `origin`; they remain recoverable
from the read-only legacy checkout at `C:\Users\admin\Desktop\live voice`:

| Population | Legacy ref | Exact tip / shape |
|---|---|---|
| 3A durability/Executor integration | `codex/live-voice-3a-durability-executor-integration` | `3cd0f46cec6d3c145eab218e865c4d4e4d4a5a1e`; 13 linear commits after `2529e2ce743ac606c21198c3efaa1c97c14ac211` |
| 3B foundation integration v2 | `codex/live-voice-3b-foundation-integration-v2` | `d3e6edf4dd9a19f1bfcf031e9c0820131477b028`; 8 linear commits after `2529e2ce743ac606c21198c3efaa1c97c14ac211` |
| D1 transactional reader | `codex/live-voice-3a-d1-transactional-reader` | `b017a9e6a72afbc185f2ac4bc179703551d8a5be`; direct parent `3cd0f46c` |
| Current D2 candidate-facts reader | `codex/live-voice-3a-d1-current-effect-reader` | `e5603aa729bb1f174ee4223ce29c228213267cc6`; direct parent `3cd0f46c` |
| Executor recovery Store | `codex/live-voice-3a-executor-recovery-store` | `6e1b4bfcbb337d0a7e5de17708b3956d39b094aa`; direct parent `3cd0f46c` |

The second candidate's ref contains `d1`, but its content is the current D2
candidate-facts reader. Do **not** substitute
`codex/live-voice-3a-d2-transactional-reader` / `62610699`; that is a different
transactional D2 snapshot-reader candidate. S8.5 remains independently
recoverable at `codex/live-voice-s8-5-incubator` / `d2f860fd2e42421a758751869db9b45f0143df3d`
(9 requested commits after `bc53e75d`); unlike the 24 commits above, that named
ref was present on `origin` when verified.

Treat the legacy checkout as the sole verified recovery source for the 24
unpublished commits: do not delete its named refs or run destructive cleanup
until every selected asset is migrated/deferred/rejected or another verified
bundle/repository contains the objects. Recovery availability still does not
authorize branch-wide import.

## 2. Disposition and gate vocabulary

| Code | Meaning |
|---|---|
| `PORT` | Isolated type, codec, Port, pure decider or caller-owned read seam worth adapting after its gate; never means whole-file cherry-pick |
| `ORACLE` | Contract, fixture, negative/failure/race/restart invariant worth transplanting; it grants no runtime authority |
| `REWRITE` | Behavior and tests are valuable but old Store/Core/product integration must be rebuilt inside the current canonical owner |
| `FUTURE` | Valid Productized/RC/Production material outside current feature-complete P3 |
| `HISTORY` | Exact-source design/review/status/showcase provenance only |

| Gate | Required current checkpoint |
|---|---|
| `G0` | P3-G0 passes the D-086 authoritative-foundation Gate; only `HISTORY`/`ORACLE` registration is admitted and no historical production import receives G0 credit |
| `G1` | P3-1 canonical multi-Task model, Store schema/migration and component ownership freeze |
| `G2` | P3-2 operation, command, successor/revision, confirmation and replay semantics freeze |
| `G3` | P3-3 capability/admission/Attempt/lease contract and real Executor selection freeze |
| `G4D` | P3-4 chooses real D1/D2 Adapters, same-versus-linked recovery Attempt and persisted capability/durability identity |
| `G4T` | P3-4 authorizes one current-schema transaction owner and migration packet |
| `G5` | P3-5 result/event/cursor/unread/consumption contract freezes |
| `G6` | P3-6 multi-Task resolver and text/voice operation parity freeze |
| `G7` | P3-7 authoritative backend response and formal Web state schema freeze |
| `G8` | P3-8 observability/privacy/configuration/profile owner freezes |
| `G9` | P3-9 current-source Tier-3, real-Adapter, fault/restart and human acceptance; a completion gate, not an early import gate |

## 3. Cross-asset dependency chains

```text
P3A-D1-01 → P3A-D1-02 → P3A-D1-SQL-01 → P3A-D1-SQL-02
                                               └──────────────┐
P3A-D2-01 → P3A-D2-SQL-01 → P3A-D2-SQL-02 → P3A-D1-D2-READ-01
          └→ P3A-D2-03 → P3A-D2-CAND-TXN-01 ────────────────┘

3B-SECEX-POLICY → 3B-SECEX-RECEIPT → 3B-SECEX-WIRE
3B-PRIVACY-POLICY → 3B-PRIVACY-LIFECYCLE
3B-OTEL-PROJECTION → 3B-SLI-WINDOW
3B-AUTH-DOMAIN → 3B-AUTH-POLICY
               └→ 3B-AUTH-INGRESS → 3B-AUTH-WIRE
3B-DEPLOY-TOPOLOGY → 3B-DEPLOY-LIFECYCLE → 3B-DEPLOY-WIRE

S85-DOC-CONTRACT-01 → S85-RK-01 → S85-STORE-01
                                  ├→ S85-EVENT-01
                                  ├→ S85-BRIDGE-01 → S85-CONFIRM-01
                                  └→ S85-EXEC-01 → S85-VERIFY-01
S85-STORE-01 + S85-EXEC-01 → S85-RECOVERY-01
S85-EVENT-01 → S85-WEB-01 → S85-WEB-02
```

The chains express source dependencies, not a recommendation to retain every
intermediate component. In particular, the current D2 design may eliminate the
old candidate journal, and the current Executor lease model may eliminate the
old recovery-facts component.

## 4. 3A durability/Executor and three sibling candidates

Historical line: `6bc8d6ac..3cd0f46c`; sibling candidates `b017a9e6`,
`e5603aa7`, `6e1b4bfc`. Production paths below are relative to
`jiuwenswarm/server/live_voice/`; tests are under
`tests/unit_tests/live_voice/` unless stated otherwise.

### `P3A-DUR-01` — D0/D1/D2 recovery decision algebra

- **Source/symbols:** `6bc8d6ac`, `durability_contract.py` — `DurabilityLevel`,
  `AttemptTruth`, `AttemptOutcome`, `EffectKind`, `EffectTruth`, `RecoveryAction`,
  `CheckpointRef`, `ExternalEffectRef`, `RecoveryObservation`,
  `RecoveryDecision`, `decide_recovery()`, `SchemaCompatibility`.
- **Evidence:** fixture `live_voice_durability_v1/contract.json`;
  `test_active_and_terminal_truth_never_dispatch_recovery`,
  `test_unknown_external_effect_never_silently_retries_checkpoint`,
  `test_safe_checkpoint_requires_complete_exact_binding_and_safe_effect`,
  `test_schema_compatibility_requires_explicit_migration_and_rollback`.
- **Decision:** `ORACLE`, target P3-3/P3-4, gate `G0`. Pure classification:
  no Store read, dispatch or proof that checkpoint/effect facts exist. It must
  not coexist with a second production recovery decider.

### `P3A-CTRL-01` — canonical full-P3 control envelope and decider

- **Source/symbols:** `249e9081`, `full_p3_control_contract.py` —
  `ProvideInputPayload`, `UpdatePayload`, `PausePayload`, `ResumePayload`,
  `ReprioritizePayload`, `FullP3ControlEnvelope`, `ControlAuthoritySnapshot`,
  `ControlAuthorizationGrant`, `ControlConfirmation`, `ControlApplicationPlan`,
  `AppliedControlResult`, `AppliedControlReplay`, `decide_full_p3_control()`.
- **Evidence:** fixture `live_voice_full_p3_control_v1/contract.json`; exact replay
  before current preconditions, changed-binding conflict with zero mutation,
  destructive confirmation binding and exact Task→Attempt state-map tests.
- **Decision:** `ORACLE`, target P3-2, gate `G2`. Reuse closed wire,
  fingerprint, confirmation and replay/conflict cases inside the current command
  owner; do not restore a second contract beside current D119 adjustment/control.

### `P3A-D1-01` — canonical D1 checkpoint wire

- **Source/symbols:** `13459f2d`, `d1_checkpoint_port.py` —
  `CheckpointExecutorBinding`, `CheckpointProducer`, `D1Checkpoint` canonical
  create/dict/bytes/checksum/input/state/context/version binding.
- **Evidence:** fixture `live_voice_d1_checkpoint_v1/contract.json`; closed
  self-checksummed round trip, duplicate/noncanonical fingerprint rejection and
  capability-version tests in `test_d1_checkpoint_port.py`.
- **Decision:** `PORT`, target P3-4 D1, gate `G4D`. Immutable checkpoint
  description only; it has no resume authority. Common basis for the SQLite port,
  transactional reader and future recovery owner.

### `P3A-D1-02` — checkpoint Port/fake and candidate prefilter

- **Source/symbols:** `13459f2d`, `d1_checkpoint_port.py` — `CheckpointPort`,
  `InMemoryCheckpointPort`, `CheckpointReadSnapshot`,
  `D1RecoveryAuthoritySnapshot`, `ExecutorCheckpointCapability`,
  `RecoveryEffectSnapshot`, `RecoveryCandidateDecision`,
  `select_recovery_candidate()`.
- **Evidence:** immutable/idempotent/monotonic write, latest-complete,
  conflicting-sequence, exact authority/effect binding and
  `test_candidate_selection_has_zero_port_mutation_and_no_execution_authority`.
- **Decision:** `ORACLE`, target P3-4, gate `G4D`. A future transaction owner
  must reread checkpoint, lease/generation and D2 truth atomically; selector
  output cannot authorize resume/redispatch.

### `P3A-D2-01` — D2 fact model and reconciliation decider

- **Source/symbols:** `74bf6788`, `external_effect_reconciliation.py` —
  `ExternalEffectBinding`, `CompensationPolicy`, `ExternalEffectIntent`,
  `EffectDispatchReceipt`, `ExternalEffectObservation`,
  `CompensationExecutionReceipt`, `ExternalEffectHandlingOutcome`,
  `AttemptEffectTruth`, `ExternalEffectLedgerSnapshot`, `ReconciliationDecision`,
  `decide_reconciliation()`.
- **Evidence:** fixture `live_voice_external_effect_reconciliation_v1/contract.json`;
  manual/compensation/unknown/applied/no-effect, cross-binding, identity-borrowing
  and `test_unknown_or_applied_effect_never_produces_retry_candidate` cases.
- **Decision:** `PORT+ORACLE`, target P3-4 D2, gate `G4D`. Pure fact/decision
  layer: no dispatch, compensation or Task mutation. Candidate manifests/journals
  must not replace this decision boundary.

### `P3A-D2-02` — deterministic D2 fake

- **Source/symbols:** `74bf6788`, `external_effect_reconciliation.py` —
  `DeterministicExternalEffectPortFake`.
- **Evidence:** intent/dispatch/observation/outcome replay/conflict and read-only
  observation cases in `test_external_effect_reconciliation.py`.
- **Decision:** `ORACLE`, target P3-4 tests, gate `G0`. It is a test fact source,
  never Provider/Task authority; a real D2 Adapter must replace positive paths.

### `P3A-EXEC-CTRL-01` — Executor-control candidate contract

- **Source/symbols:** `228c93c7`, `full_p3_executor_control.py` —
  `ExecutorControlAuthority`, `ExecutorControlRequest`,
  `ExecutorControlCandidateReceipt`, `ExecutorControlDecision`,
  `decide_executor_control()`, `FullP3ExecutorControlPort`,
  `DeterministicFullP3ExecutorControlFake`.
- **Evidence:** fixture `live_voice_full_p3_executor_control_v1/contract.json`;
  feature-off, epoch/generation/attempt mismatch, duplicate/conflict/concurrency
  and zero-effect tests.
- **Decision:** `ORACLE`, target P3-2/P3-3, gate `G3`. It records a
  content-free candidate and deliberately never pauses, resumes, reprioritizes,
  starts, cancels or terminates an Executor. A real Adapter API must own positives.

### `P3A-D2-03` — D2 Task-Core candidate wire

- **Source/symbols:** `6a8c8377`, `external_effect_task_core.py` —
  `ExternalEffectTaskCoreCandidateManifest`,
  `ExternalEffectTaskCoreCandidateReceipt`, candidate/snapshot/truth/decision
  fingerprints and `_NoRuntimeAuthority`.
- **Evidence:** fixture `live_voice_external_effect_task_core_v1/contract.json`;
  cross-binding, canonical bytes, duplicate keys, forged nested facts and
  all-authority-slots-false tests.
- **Decision:** `PORT+ORACLE`, target optional P3-4 audit metadata, gate `G4D`.
  It does no Store I/O, reconciliation, lifecycle or Provider/Executor action. If
  current D2 settles directly in one effect/Task transaction, omit this journal
  and retain only fingerprint/corruption oracles.

### `P3A-D1-03` — same-Attempt recovery preparation vocabulary

- **Source/symbols:** `6d04ff61`, `same_attempt_checkpoint_recovery.py` —
  `SameAttemptRecoveryRequest`, `SameAttemptRecoveryAuthorization`,
  `TaskCoreCheckpointAdmissionManifest`, `D2AuthoritativeEffectTruth`,
  `ExecutorRecoveryLease`, `SameAttemptRecoveryAdmissionFacts`, candidate/receipt
  types and `decide_same_attempt_checkpoint_recovery()`.
- **Evidence:** fixture `live_voice_same_attempt_checkpoint_recovery_v1/contract.json`;
  auth expiry/binding, checkpoint/effect/lease/generation exactness, forgery and
  all-authority-slots-false cases.
- **Decision:** `REWRITE+ORACLE`, target P3-4 D1, gate `G4D`. The positive
  prepared state is deliberately unreachable and the module never resumes. It
  hard-codes a still-unaccepted same-Attempt choice; retain only binding/lease/
  effect negatives after the current decision freezes.

### `P3A-D2-SQL-01` — durable SQLite effect ledger

- **Source/symbols:** `bfd387a1`, enhanced by `83de3eb8`,
  `sqlite_external_effect_ledger.py` — `SqliteExternalEffectLedger` methods
  `register_intent`, `record_dispatch`, `record_observation`,
  `record_handling_outcome`, `snapshot`.
- **Evidence:** durable order/reopen, identity claim, manual/compensation facts,
  concurrent replay/conflict, failpoint rollback and schema/trigger/index/storage
  corruption in `test_sqlite_external_effect_ledger.py`.
- **Decision:** `PORT`, target P3-4 D2, gates `G1+G4T`. It stores effect facts
  only; no Provider/Executor/Task/compensation authority. Rebase the module under
  current migration ownership rather than copying its old component DDL.

### `P3A-D2-SQL-02` — caller-owned transactional D2 prefix reader

- **Source/symbols:** `83de3eb8`, `sqlite_external_effect_ledger.py` —
  `_VerifiedExternalEffectLedgerPrefix`, `_require_bound_reader_connection()`,
  `_read_verified_snapshot_prefix()`.
- **Evidence:** caller-transaction-only, active same-database connection,
  dirty/temp-shadow/full-audit-before-predicate, unknown/applied and canonical
  prefix tests in `test_sqlite_external_effect_ledger.py`.
- **Decision:** `PORT`, target P3-4 D2 and D1 effect-safety input, gate `G4T`.
  It never opens/commits/rolls back the caller transaction, writes or decides
  recovery. It is the preferred lower seam for `P3A-D1-D2-READ-01`.

### `P3A-D1-SQL-01` — immutable SQLite checkpoint storage

- **Source/symbols:** `cbca1cec`, superseded for extraction by `b017a9e6`,
  `sqlite_d1_checkpoint_port.py` — `SqliteD1CheckpointPort.write/read_attempt`,
  component audit and immutable idempotent/monotonic row storage.
- **Evidence:** reopen, concurrent duplicate/conflict, binding isolation,
  preserved corrupt bytes, schema/trigger/index/sidecar failure, insert rollback
  and zero Task/Event/Outbox/Executor mutation tests.
- **Decision:** `PORT`, target P3-4 D1, gates `G1+G4T`. It does not select or
  resume. Use the final `b017a9e6` file as extraction source instead of applying
  `cbca1cec` and then replaying its enhancement.

### `P3A-SQL-COHOST-01` — D1/D2 cohost oracle

- **Source/evidence:** `70648baf`,
  `test_sqlite_d1_d2_cohost_integration.py` —
  `test_d1_and_d2_sqlite_components_cohost_in_both_initialization_orders`.
- **Decision:** `ORACLE`, target P3-4 Store integration, gate `G1`. Expand from
  two old sidecars to all initialization/migration orders for current schema,
  D1, D2 and any selected recovery component.

### `P3A-D1-SQL-02` — bounded transactional checkpoint reader

- **Source/symbols:** `b017a9e6`, `sqlite_d1_checkpoint_port.py` —
  `_VerifiedD1CheckpointRecord`, `_VerifiedD1CheckpointPrefix`,
  `content_facts()`, `canonical_prefix_bytes()`, `prefix_fingerprint_hex()`,
  `_iter_bounded_checkpoint_rows()`, `_read_verified_attempt_prefix()`.
- **Evidence:** caller transaction, invalid bytes as untrusted facts,
  duplicate/conflicting sequence, global audit, dirty/temp shadow, oversized
  blob/cross-scope bounds, no partial prefix and corruption tests. Historical
  bounds are 1 MiB/item, 4096 rows/16 MiB store, 1024 rows/8 MiB target prefix.
- **Decision:** `PORT+ORACLE`, highest-value D1 Store asset, target P3-4, gate
  `G4T`. It returns verified content only and reads no lease/effect authority;
  the current transaction owner must continue with Task/Attempt/generation/D2.

### `P3A-D1-D2-READ-01` — current D2 candidate-facts compositor

- **Source/symbols:** `e5603aa7`, `d1_current_effect_candidate.py` —
  `_D1CurrentEffectCandidateFacts`, `_read_current_effect_candidate_for_d1()`,
  `_configuration_is_exact()`; binds journal head, Task event head and current
  ledger-prefix fingerprint.
- **Evidence:** fixture `live_voice_d1_current_effect_candidate_v1/contract.json`;
  caller connection, stale prefix/head, missing/wrong target hiding, global
  corruption, reopen/fresh clone and all-authority-false tests.
- **Decision:** `ORACLE`, optionally small `PORT`, target P3-4 D1+D2 admission,
  gate `G4T`. It cannot make D1 reachable. If current design omits the candidate
  journal, compose direct current-ledger facts and drop that dependency.

### `P3A-CTRL-TXN-01` — durable control transaction

- **Source/symbols:** `fe2884db`, `full_p3_control_task_core.py`, old
  `persistent_task_core.py`/`task_store.py` — portable
  `FullP3ControlPolicy`, `FullP3ControlProjection`, `FullP3ControlReceipt`,
  `normalize_full_p3_control_admission()`; old seams
  `read_full_p3_control_authority()` and `apply_full_p3_control()`.
- **Evidence to transplant:** authorization before Store/DDL, authority reread,
  replay/conflict, accepted→applied CAS, event/projection/replay atomic commit,
  failpoint rollback, global lifecycle revision and concurrent one-winner tests.
- **Decision:** `REWRITE`, target P3-2/P3-3, gates `G1+G2`. Current D119 owns
  adjustment transactions; merge oracles into that canonical owner instead of
  restoring `full_p3_control_*`. Durable Task apply does not prove Executor action.

### `P3A-D2-CAND-TXN-01` — atomic D2 candidate journal transaction

- **Source/symbols:** `3cd0f46c`, `external_effect_task_core_runtime.py`, old
  Core/Store — portable normalization, timestamp/order, record-byte,
  snapshot/truth/decision/prefix codecs, `create_candidate_receipt()`,
  `verify_candidate_facts()`; old `_record_external_effect_candidate()` and
  candidate-head/generation/ledger-link seams.
- **Evidence to transplant:** exact cohost path, caller-owned immediate
  transaction, current ledger and Task/Attempt truth reread, pure reconciliation,
  hash-chain/CAS, failpoints, cross-binding, stale/supersede and corruption.
- **Decision:** helpers `PORT` at `G4D`, Store integration `REWRITE` at `G4T`,
  target P3-4. It writes metadata only. Omit the candidate journal if direct
  effect settlement/manual truth makes it redundant.

### `P3A-EXEC-REC-01` — Executor recovery canonical facts

- **Source/symbols:** `6e1b4bfc`, `executor_recovery_store_foundation.py` —
  `ExecutorRecoveryEpochCandidate`, `ExecutorRecoveryAttemptCandidate`, event
  kinds, foundation state/receipt/snapshot and canonical record-byte functions.
- **Evidence:** fixture `live_voice_executor_recovery_store_foundation_v1/contract.json`;
  canonical parity, expiry/state constraints, forgery and authority-false tests.
- **Decision:** `PORT+ORACLE`, target P3-3/P3-4, gates `G3+G4D`. Facts do not
  prove revalidation, checkpoint capability, prior quiescence, invocation or
  Task change. Map into current `project_code_executor.py` lease/heartbeat model;
  never create parallel lease authority.

### `P3A-EXEC-REC-02` — Executor recovery Store event chain

- **Source/symbols:** `6e1b4bfc`, old `task_store.py` — append/read epoch and
  Attempt candidate seams, component audit, heads, hash-chain and CAS.
- **Evidence to transplant:** domain-separated append-only identity,
  generation/previous-generation/lease/owner/event-head binding, irrevocable
  expiry/revoke, linked provenance, replay/conflict/concurrency, failpoints and
  schema/trigger/casefold/storage corruption.
- **Decision:** `REWRITE`, target P3-3/P3-4, gates `G3+G4T`. Candidates never
  prove quiescence or recovery. Add a minimal current-schema journal only if
  current lease tables cannot express the required facts; otherwise tests only.

## 5. 3B hardening foundations

Historical line `6306b21e..d3e6edf4`. Paths use the same server/test roots as
§4; channel modules/tests are called out explicitly.

### `3B-SECEX-POLICY` — secure-Executor policy vocabulary

- **Source/symbols:** `6306b21e`, `secure_executor_policy.py` — `PolicyStatus`,
  sandbox/egress/secret/artifact enums, `ResourceQuota`, `NetworkPolicy`,
  `SecretPolicy`, `ArtifactPolicy`, `KillEscalation`, `SecureExecutorFacts`,
  `SecureExecutorDecision`, `evaluate_secure_executor()`.
- **Evidence:** `test_secure_executor_policy.py` — least privilege, exact HTTPS
  allowlist, no inline/URL secret, quota/artifact/kill ordering, image digest,
  exact-root/forgery and configuration-only assertions.
- **Decision:** `REWRITE`, target P3-3/P3-8, after `G1+G3`. Map vocabulary into
  current capability/admission and one real Adapter. Readiness does not prove an
  OS sandbox, filesystem/network/secret/quota enforcement or dispatch.

### `3B-SECEX-RECEIPT` — enforcement preparation/receipt seam

- **Source/symbols:** `96ca1306`, `secure_executor_enforcement.py` —
  `secure_executor_policy_fingerprint()`, `ExecutorEnforcementCapabilities`,
  `SecureExecutionPreparationRequest`, `build_preparation_request()`,
  `ExecutorEnforcementReceipt`, `SecureExecutorEnforcementPort`,
  `ExecutorEnforcementDecision`, `evaluate_enforcement_receipt()`.
- **Evidence:** `test_secure_executor_enforcement.py` — capability/receipt and
  scope/Attempt/adapter binding, missing capability before dispatch, forged
  facts and evaluator-never-invokes-adapter.
- **Decision:** `REWRITE`, target P3-3, gate `G3`. Integrate reported facts into
  the single admission/Attempt path and prove a real Adapter; a receipt alone is
  not sandbox/process enforcement.

### `3B-SECEX-WIRE` — closed secure-Executor wire

- **Source/symbols:** `df80cfb3`,
  `secure_executor_enforcement_wire_contract.py` — `SecureExecutorWireKind`,
  `SecureExecutorWireEnvelope` canonical encode/decode/fingerprint and
  authority-false accessors.
- **Evidence:** fixture `live_voice_secure_executor_enforcement_v1/contract.json`;
  exact roundtrip/binding, recursive forgery, safe integer/Unicode, mutation
  isolation, secret-safe failure and untrusted-wire-never-becomes-authority tests.
- **Decision:** adjusted `PORT`, target P3-3, after `G3` and a real cross-process
  wire selection. Regenerate/map against current types and avoid a second
  validator owner. The current in-process path may not need this wire.

### `3B-PRIVACY-POLICY` — privacy classification/readiness vocabulary

- **Source/symbols:** `6306b21e`, `privacy_policy.py` — data class,
  persistence/control/requirement/readiness enums, `PrivacyClassification`,
  `PrivacyControlDecision`, `PrivacyPolicy`, `PrivacyReadiness`,
  `evaluate_privacy_readiness()`.
- **Evidence:** `test_privacy_policy.py` — default raw-audio prohibition,
  complete declarations remain declaration-only, unsafe identity, duplicates,
  forgery and feature-off zero-touch.
- **Decision:** `REWRITE`, target P3-8, after `G1+G8`. Unify with current runtime
  private-content canary/export rejection. No legal, regional, retention, delete,
  export, runtime scan or compliance authority.

### `3B-PRIVACY-LIFECYCLE` — lifecycle candidate identity/ledger

- **Source/symbols:** `a770f862`, `privacy_lifecycle_port.py` — lifecycle
  operation/decision/reason/disposition, request/policy binding/decision,
  candidate receipt build/validate, `PrivacyLifecycleCandidatePort`,
  `InMemoryPrivacyLifecycleCandidatePort`.
- **Evidence:** fixture `live_voice_privacy_lifecycle_v1/contract.json`;
  raw-audio rejection, binding negatives, replay/conflict, concurrent one-write,
  wrong-scope hiding, feature-off, forgery and candidate identity tests.
- **Decision:** adjusted `PORT`, target P3-8, after `G1+G5+G8`. Bind to real
  log/TaskResult/artifact owners. Candidate receipts touch no underlying data;
  tenant export/delete/retention execution remains `FUTURE`.

### `3B-OTEL-PROJECTION` — bounded private-safe OTel projection

- **Source/symbols:** `6306b21e`, `otel_export_contract.py` —
  `OtelSignalKind`, `OtelProjectionReason`, issued `TelemetryTraceContext`,
  allowlisted `OtelAttribute`, `OtelExportRecord`, `OtelProjection`,
  `validate_otel_projection_for_export()`, observation/metric projectors.
- **Evidence:** `test_otel_export_contract.py` — safe span/metric, private and
  dynamic-route rejection, exact trace binding, closed attributes/finite values,
  forged seals and feature-off.
- **Decision:** small `REWRITE`, target P3-8, after `G1+G8`. Current
  observability types are compatible, but compose as one backend codec behind
  the current adapter/exporter; it performs no export, I/O or lifecycle action.

### `3B-SLI-WINDOW` — content-free SLI arithmetic

- **Source/symbols:** `a1d42996`, `sli_window_contract.py` — sample/state types,
  `SliWindowTarget`, `SliWindowSample`, `SliWindowMeasurement`, validation and
  `calculate_sli_window()`.
- **Evidence:** fixture `live_voice_sli_window_v1/contract.json`; latency/ratio,
  duplicate/conflict, incomplete prefix, cross-scope, gap/reorder/out-of-window,
  nonfinite/bounds and authority-false tests.
- **Decision:** `ORACLE`, target P3-8 diagnostics/latency, after `G1+G8`. It
  performs arithmetic only and claims no SLO, alert, export or mutation. Do not
  install a second measurement truth owner without an explicit P3-8 choice.

### `3B-SLO-DECLARATION` — SLO/cost declaration model

- **Source/symbols:** `6306b21e`, `slo_contract.py` — indicator/decision/
  comparator/unit/cost/gap/readiness types, `SloObjective`, `SloCostEnvelope`,
  `SloContract`, `evaluate_slo_readiness()`.
- **Evidence:** `test_slo_contract.py` — no defaults, completeness, indicator,
  threshold/window/cost boundaries, duplicate/out-of-scope, forgery/feature-off.
- **Decision:** `FUTURE` with current `ORACLE` value. It measures nothing and
  owns no alert/release authority. Revisit only after P3-9 under a new Productized
  SLO/cost packet.

### `3B-AUTH-DOMAIN` — auth/tenant immutable domain

- **Source/symbols:** `6306b21e`, `auth_tenant_contract.py` — membership/proof/
  decision enums, `PolicyAttribute`, `ResourceScope`, trusted principal/session/
  membership/proof/context/resource, request/rule/policy, sealed grant/decision.
- **Evidence:** fixture `live_voice_auth_tenant_v1/negative_matrix.json` with 35
  default-deny/replay/revocation/RBAC/ABAC/scope/tenant/resource cases and zero
  Agent/Tool/Task/Executor/Store/audio/history effects; policy tests cover closed
  shapes, unmintable authority, existence hiding and expiry boundaries.
- **Decision:** implementation `FUTURE`; selected exact-scope/default-deny/
  replay/zero-effect cases are `ORACLE` for P3-2/P3-6/P3-7 after `G0`. Never
  create a parallel authority beside current `product_authority.py`.

### `3B-AUTH-POLICY` — pure RBAC/ABAC evaluator

- **Source/symbols:** `6306b21e`, `auth_tenant_policy.py` — `AuthTenantPolicy`
  and exact scope/rule/attribute/grant fingerprint matchers.
- **Evidence:** trusted RBAC+ABAC+capability authorize, default deny, strict
  attribute types, bounded scope, membership/grant expiry, forgery, existence
  hiding and the 35-case matrix.
- **Decision:** `FUTURE`, with denial `ORACLE` value now. No clock/network/config/
  audit/persistence/replay owner. Revisit only with real trusted ingress,
  revocation and one Production authority owner.

### `3B-AUTH-INGRESS` — identity-provider Adapter seam

- **Source/symbols:** `96ca1306`, `auth_tenant_adapter.py` — authentication
  status/reason, request/provider result, `IdentityProviderPort`, decision and
  `AuthTenantAdapter.authenticate()`.
- **Evidence:** `test_auth_tenant_adapter.py` — exact provider context,
  flag-off/invalid zero calls, provider/protocol failures, binding, redaction and
  recursive forgery.
- **Decision:** `FUTURE`, tests as `ORACLE`. Scripted-provider authentication is
  not action authorization or Production proof. Requires future real provider,
  credential refs, channel binding, rotation/revocation and policy composition.

### `3B-AUTH-WIRE` — untrusted auth/tenant codec

- **Source/symbols:** `90fa6927`, `auth_tenant_wire_contract.py` — wire kinds,
  opaque envelope and `AuthTenantWireCodec` request/context/provider-result
  encode/decode.
- **Evidence:** fixture `live_voice_auth_tenant_adapter_v1/contract.json`;
  exact roundtrip, untrusted decoded values, bounds/canonical JSON, binding,
  unknown fields, forgery, feature-off, secret-safe errors and mutation isolation.
- **Decision:** `FUTURE`, tests as `ORACLE`. Decode selects/calls no IDP and
  authorizes nothing. Do not add this schema before a future provider protocol.

### `3B-DEPLOY-TOPOLOGY` — secure-topology declaration

- **Source/symbols:** `6306b21e`, channel
  `live_voice_secure_topology.py` — decision/control/routing/owner/reason types,
  `SecureTopologyOwnerRef`, `SecureTopologyFacts`, result and evaluator.
- **Evidence:** channel topology tests — affinity/shared-state routing,
  cross-origin/insecure/localhost rejection, missing/proposed controls,
  feature-off, forgery and zero external effects.
- **Decision:** `FUTURE`, tests as `ORACLE`. It reads no environment, service,
  certificate or deployment truth and cannot replace current bounded preflight/
  observer evidence. Revisit after P3-9 in a public-deployment packet.

### `3B-DEPLOY-LIFECYCLE` — deployment lifecycle candidate

- **Source/symbols:** `e499217f`, channel
  `live_voice_deployment_lifecycle.py` — lifecycle state/dependency/command/
  result types, config/snapshot/bootstrap/decision, bootstrap/decide functions
  and `DeterministicDeploymentLifecycleFake`.
- **Evidence:** fixture `live_voice_deployment_lifecycle_v1/contract.json`;
  ready/admit/drain/release/stop, binding/replay/conflict/capacity/deadline/
  concurrency/forgery and zero-runtime-effect tests.
- **Decision:** `FUTURE`, `ORACLE` only. It is in-memory candidate state and
  opens/closes no service, changes no Task and proves no deployment/release.

### `3B-DEPLOY-WIRE` — deployment transcript codec

- **Source/symbols:** `d3e6edf4`, channel
  `live_voice_deployment_lifecycle_wire_contract.py` — config/snapshot/command
  codecs, transcript entry/candidate, replay and canonical bytes.
- **Evidence:** `wire_contract.json`; canonical fingerprints, replay/conflict,
  closed schema/forgery/mutation and all-runtime-authority-false tests.
- **Decision:** `FUTURE`, `ORACLE` only. It replays a fake and owns no
  persistence, probe, socket, product or release truth.

### `3B-HARDENING-DOC-ORACLE` — old 3B review/acceptance record

- **Source:** `6306b21e`, old foundation review and beta/RC/Production
  acceptance document.
- **Evidence boundary:** the review labels modules configuration/policy/
  projection only and acceptance open; tracked counts are `281 passed` and
  `1650 passed, 2 skipped`. An unbound `499/499` receives no credit.
- **Decision:** `HISTORY+ORACLE`; current complete-P3 plan and TESTING remain
  authoritative. Do not migrate readiness labels or counts.

## 6. S8.5 incubator

Historical contract `bc53e75d`; requested commits `caed0ff2`, `f13cfe8d`,
`0c994b1b`, `ab200d2c`, `be4e71b3`, `8be8398a`, `fc7348f2`, `c9e7aba6`,
`d2f860fd`. The last product-code point is `8be8398a`; later commits are docs.

### `S85-RK-01` — bounded revision command kernel

- **Source/symbols:** `caed0ff2`, `task_revision.py` — operation, constraints,
  patch, command/grant/authority/target/plan, `plan_task_revision()`, canonical
  parsing/fingerprint and bounded facts/write scopes.
- **Evidence:** `test_task_revision.py` — canonical roundtrip, bounds/Unicode,
  generic/unknown rejection, confirmation binds all facts, feature/pending/stale
  admission, wrong scope and duplicate fact.
- **Decision:** `PORT+REWRITE`, target P3-2/P3-6, after `G0+G1+G2`. Keep pure
  parsing/fingerprint/revalidation; remove one-revision, same-Task successor,
  fixed Attempt and historical `update_constraints` operation authority. Merge
  into current formal models/policy/confirmation rather than creating a second stack.

### `S85-RK-02` — cleanup/verifier value contracts

- **Source/symbols:** `0c994b1b`, `task_revision.py` — `RevisionFenceRequest`,
  `RevisionFenceAck`, verifier state/result and `TaskRevisionExecutionAck`.
- **Evidence:** serialization/conflict in Store tests and verifier combinations
  in Executor tests.
- **Decision:** adjusted `PORT`, target P3-3/P3-4/P3-9, gate `G3`. Cleanup can
  prove exact predecessor quiescence and verifier can prove one allowlisted run;
  neither decides Task terminal. Map into current `retry_readiness()`/capability
  response and remove same-Task/fixed-Attempt lineage.

### `S85-STORE-01` — transactional revision saga sidecar

- **Source/symbols:** `caed0ff2`, `0c994b1b`, `8be8398a`,
  `task_revision_store.py` plus old `task_store.py` — `SqliteTaskRevisionStore`,
  receipt/fence/dispatch/truth types, request/claim/complete/pending/ACK/truth
  methods and `s85_*` metadata/revision/command/outbox/fence/dispatch/execution tables.
- **Evidence:** see `S85-STORE-ORACLE-01`.
- **Decision:** `REWRITE`, target P3-1/2/3/5, gate `G1`. Preserve atomic
  command/state/outbox/ACK, claims, failpoint rollback and late-event quarantine.
  Never create the second sidecar schema or split authority from current
  adjustment/event/outbox owners; no Executor effect inside DB transactions.

### `S85-STORE-ORACLE-01` — atomicity/race/restart suite

- **Source/evidence:** `caed0ff2`, `0c994b1b`, `8be8398a`,
  `test_task_revision_store.py` — feature-off no schema; partial/unknown/weakened
  schema failure; request atomicity; replay/conflict/stale; late predecessor;
  cleanup mismatch/unknown; cancel race; corrupt lineage; reopen; request/
  complete failpoints; concurrent one fence; immutable execution ACK.
- **Decision:** `ORACLE`, targets P3-1/2/3/5/9, first gate `G1`. Rewrite
  same-Task assertions into the accepted running-checkpoint-update or
  terminal-new-Task successor contract and preserve zero forbidden side effects.

### `S85-EVENT-01` — revision event/replay invariants

- **Source/symbols:** `caed0ff2`, old common schema, formal models, Core,
  progress arbiter, event subscription and progress return. Requested events are
  non-projecting; applied events mark settlement; sequence tracking binds
  task/revision/Attempt; late predecessor facts remain diagnostic.
- **Evidence:** requested-event replay, exact replay and late-predecessor Store tests.
- **Decision:** `ORACLE`, with small schema helpers possibly `PORT`, target
  P3-2/P3-5 after `G1+G2+G5`. Extend current adjustment/event owners; do not
  restore an S8 event namespace or infer authority from projection.

### `S85-BRIDGE-01` — committed-input and Store-target bridge

- **Source/symbols:** `f13cfe8d`, `task_revision_bridge.py` — intent disposition,
  target reader/span/draft/prepared types, `BoundedTaskRevisionVoiceBridge.resolve()`,
  `TaskRevisionPolicyAdapter.prepare()/authorize()`.
- **Evidence:** `test_task_revision_bridge.py` — feature-off before input,
  target never from speech, accepted commit and Store target, stale revalidation,
  wrong scope/ineligible target and ambiguous/generic/forbidden rejection.
- **Decision:** `PORT+REWRITE`, target P3-6, after `G1+G2+G5+G6`. Merge
  Store-derived target and revalidation into current Bridge/policy. Remove exact
  regex as product NLU, voice-only behavior and single-current-Task assumptions.

### `S85-CONFIRM-01` — exact mutation fingerprint binding

- **Source/symbols:** `f13cfe8d`, `8be8398a`, old `p3_confirmation.py` — exact
  operation/scope/task/revision/Attempt/facts fingerprint, target reread and
  operation enable checks.
- **Evidence:** policy requires exact confirmation, all-fact binding, separately
  default-off capability and product-authority gating tests.
- **Decision:** `PORT+ORACLE`, target P3-2/P3-6/P3-8, gate `G2`. Add missing
  version/facts oracles to current confirmation ledger; do not create an S8 owner/
  flag. Confirmation selects neither language intent nor target and proves no execution.

### `S85-EXEC-01` — predecessor fence and cleanup proof

- **Source/symbols:** `0c994b1b`, old `project_code_executor.py` and
  `task_revision_executor.py` — Direct fence/cleanup checks and coordinator
  `fence_once()`.
- **Evidence:** discard/ACK exact base, noncooperative worker no ACK, already
  applied rejection and unknown-cleanup no verifier-success tests.
- **Decision:** `PORT+REWRITE`, target P3-3/P3-4, gate `G3`. ACK only after
  worker/apply/interrupt/journal/lease/retained cleanup are proven quiet;
  timeout/mismatch/unknown cannot start successor. Add through the current
  capability seam, not private Executor fields. It gives no D1/D2 credit.

### `S85-FIXTURE-01` — trusted disposable fixture profile

- **Source/symbols:** `0c994b1b` plus `8be8398a`,
  `task_revision_executor.py` — fixture manifest, verifier command/registry,
  loader, exact root/parent/marker/checkout identity and clean-base constraints.
- **Evidence:** dirty/remote/unmarked, exact clean registry, forbidden path,
  commit/remote and missing/shell-verifier tests.
- **Decision:** `PORT`, target P3-3/P3-9 with configuration in P3-8, after `G3`.
  Only explicit local disposable fixtures qualify; forbid remote, escape/symlink,
  dependency/public API/config/out-of-scope mutation, commit and push. Do not
  duplicate current project binding/fingerprint authority.

### `S85-VERIFY-01` — allowlisted bounded verifier

- **Source/symbols:** `0c994b1b` plus `8be8398a`,
  `task_revision_executor.py` — `TrustedVerifierCommand`, sanitized output,
  fixture verifier, coordinator `verify_once()` and execution ACK.
- **Evidence:** bound success/redaction, fail/timeout/mutation, forbidden path,
  missing/shell verifier and exact coordinator journey tests.
- **Decision:** `PORT+ORACLE`, target P3-3/P3-9, after `G3` and product claim
  only at `G9`. Registry supplies argv; no shell/git/curl/ssh; timeout/output/path
  are bounded. Failure/unknown never becomes success; ACK is not Task terminal truth.

### `S85-EXEC-ORACLE-01` — restart delivery/reconcile

- **Source/evidence:** `8be8398a`, executor test reopens the revision Store with
  a new coordinator, rediscovers delivered dispatch, avoids redispatch,
  reconciles terminal truth, persists execution ACK and clears pending work.
- **Decision:** `ORACLE`, target P3-3/P3-4/P3-9, after `G3`. Rewrite for current
  outbox/settlement owner and new-Task successor; add multi-process/lease/orphan
  dimensions absent from the old profile.

### `S85-WEB-01` — strict revision-truth parser/replica

- **Source/symbols:** `ab200d2c`, frontend `taskRevisionTruth.ts` — limits,
  snapshot types, revision/pending/cleanup/verifier/execution parsers,
  status parser, `TaskRevisionTruthReplica`, application state/warning helpers.
- **Evidence:** frontend `taskRevisionTruth.test.mjs` — application separate from
  success, explicit extension, unknown cleanup/verifier non-success, monotonic
  replay, lifecycle regression, disconnect generation, wrong target/unknown
  fields and no inferred success.
- **Decision:** `PORT+ORACLE`, target P3-7/P3-9, after `G2+G5+G6+G7`. Merge
  unique fields into current `FormalTaskControlLeaf`; keep strict exact-key/
  wrong-task/monotonic/generation behavior and avoid a second replica owner.

### `S85-WEB-02` — old Panel polling and S8 selector

- **Source:** `ab200d2c`, `8be8398a`, old Panel/CSS/feature flags/
  `formalTaskIntentRoute.ts`; current/created-target polling, S8 selector and
  voice-only confirmation route.
- **Evidence:** separately gated voice-only route and feature-off/no-DOM/no-read tests.
- **Decision:** `REWRITE`, target P3-7/P3-8, gate `G7`. Do not port JSX,
  polling, selector or bespoke flag. Current formal UI must cover multi-Task,
  text/voice parity and all operations under one owner.

### `S85-PRODUCT-01` — commit→confirmation→Store admission sequence

- **Source/symbols:** `8be8398a`, old Registry/authenticated composition/
  confirmation/text route — pending revision, fact builder, intent runner and
  confirm handler.
- **Evidence:** exact commit+confirmation+Store write, flag-off before authority,
  separate capability gate and frontend confirmation-bound tests.
- **Decision:** `ORACLE`, target P3-2/P3-6/P3-9, after `G1+G2+G5+G6`. Preserve
  accepted commit→Store target→prepared facts→later confirmation→reread→one write.
  Remove voice-only, S8 grammar, same-Task revision and Registry semantic ownership.

### `S85-RECOVERY-01` — fence/dispatch/verify recovery pump

- **Source/symbols:** `8be8398a`, old Registry — readiness, lifecycle start and
  bounded loop ordering `fence_once→dispatch_once→verify_once`.
- **Evidence:** coordinator restart/reopen and historical durable-recovery review.
- **Decision:** `REWRITE+ORACLE`, target P3-3/P3-4/P3-9, after `G3`. Merge
  sequencing into current Core/Executor outbox/reconcile owner; do not retain a
  parallel worker, single-process owner or polling-derived terminal success.

### `S85-COMPOSE-01` — fail-closed prerequisite composition

- **Source:** `ab200d2c`, `8be8398a`, old AgentServer/composition/Registry;
  S8 enable/fixture variables and factory prerequisite checks.
- **Evidence:** default-off, authenticated route, fixture+confirmation required,
  separate owner allocation, Store reader required and authenticated projection tests.
- **Decision:** `ORACLE`, target P3-7/P3-8/P3-9, gate `G8`. Preserve “missing
  one prerequisite creates no authority” and feature-off zero-touch. Do not
  restore bespoke env vars, confirmation owner or worker; P3-8 consolidates them.

### `S85-DOC-CONTRACT-01` — historical contract packet

- **Source:** `bc53e75d`, old S8.5 architecture and execution-plan documents.
- **Reusable:** explicit identity, admission/fence/successor/verifier layering
  and restart/concurrency/non-goal questions.
- **Decision:** `HISTORY+ORACLE`, design input for P3-1/2/3. Same-Task
  revision, old operations and D-079/D-080 are superseded by current P3.

### `S85-DOC-ACCEPT-01` — negative/recovery acceptance matrix

- **Source:** `bc53e75d`, old S8.5 acceptance document.
- **Reusable:** replay/conflict, concurrent winner, cancel race, transaction
  failpoints, cleanup timeout/crash/mismatch, intermediate restart, late facts,
  dirty/remote/escaping/symlink target, forbidden mutation, verifier failure and
  zero forbidden side effects.
- **Decision:** `ORACLE`, target P3-1..9 by owner. Rewrite same-Task scenarios
  into running checkpoint update or terminal new-Task successor and add
  multi-Task, text/voice, full-operation and D0/D1/D2 dimensions.

### `S85-DOC-SHOWCASE-01` — old one-revision journey

- **Source:** `bc53e75d`, `fc7348f2`, old showcase and D-080 text.
- **Decision:** `HISTORY`. Voice-only one-revision Task A/Task B cancel/failure
  journey conflicts with current decisions and supplies no implementation credit;
  at most it informs a future P3-9 human journey.

### `S85-DOC-REVIEW-01` — incubation verification record

- **Source:** `be4e71b3`, `c9e7aba6`, `d2f860fd`, old review/STATUS.
- **Evidence boundary:** backend `363/363` reached PASSED but pytest did not exit
  cleanly; frontend `327` and build passed; no independent D-074 review or real
  Speech/Agent/Executor/human path; final label remained PARTIAL.
- **Decision:** `HISTORY`, P3-9 provenance only. Rerun everything on current source.

### `S85-DOC-CLAIMS-01` — old competitor claims

- **Source:** `bc53e75d`, old competitor matrix.
- **Decision:** `HISTORY`. Claims are time-sensitive and tied to a different
  capability boundary; any future use requires fresh research and P3-9 evidence.

### `S85-DOC-MUTABLE-01` — old routing/status/decision edits

- **Source:** `bc53e75d`, `be4e71b3`, `fc7348f2`, `c9e7aba6`, `d2f860fd`, old
  README/STATUS/ACG/DECISIONS edits.
- **Decision:** `HISTORY`. Never cherry-pick or restore old queue, numbering or
  branch status; retain commit provenance only.

## 7. Activation-time implementation packet

When a package gate opens, the Integration Owner selects asset IDs above and
creates one bounded implementation packet with these fields:

| Field | Activation-time requirement |
|---|---|
| `asset_ids` | Exact manifest rows selected; no implicit branch-wide import |
| `source_repository_ref` | Verified source checkout/ref and exact commit or Git range from §1.1 |
| `current_head` | Exact clean source used to validate current overlap |
| `target_files_symbols` | Current canonical owner and exact edit boundary |
| `semantic_decisions` | Accepted state/revision/capability/recovery choices the mapping depends on |
| `schema_migration` | Version, ownership, cohost order, rollback and corruption behavior if applicable |
| `preserve_rewrite_drop` | Source symbols retained, rewritten or deliberately omitted with reason |
| `test_destinations` | Current capability-owned test files and named oracles to transplant |
| `risk_and_dependencies` | TESTING tier, cross-owner seams and real Adapter requirements |
| `forbidden_claims` | Authority/completion the extracted asset still does not prove |
| `verification` | Exact commands, positive/negative/failure/race/restart and independent-review scope |
| `retirement_return` | Historical assets migrated/deferred/rejected and whether the old ref may retire |

The worker validates this mapping against current source; it does not reopen the
complete historical corpus. Any mismatch returns to the Integration Owner rather
than being resolved by inventing a new local semantic owner.

## 8. Recommended extraction order

This order is subordinate to the critical path and parallel collision rules in
[the complete P3 plan](../roadmap/FULL_P3_EXECUTION_PLAN.md#6-dependency-graph-critical-path-and-dispatch-waves).

1. Register all `HISTORY` and `ORACLE` rows now; this grants no product credit.
2. After `G1`, transplant Store schema/failpoint/cohost oracles and decide the
   minimal canonical schema; do not create S8/3A sidecars by default.
3. After `G2`, select current command/fingerprint/confirmation/replay assets.
4. After `G3`, select secure-Executor, cleanup, fixture/verifier and recovery-fact
   assets; bind every positive to a real selected Adapter.
5. At `G4D/G4T`, port the two caller-owned transactional readers, then implement
   the smallest current-owned D1/D2 transaction. Decide whether candidate and
   epoch journals are necessary rather than assuming they are.
6. At `G5/G6/G7`, transplant result/event, Bridge and strict Web oracles into
   their existing owners; never restore old product wiring or polling stacks.
7. At `G8`, compose private-safe observability/privacy and consolidate profiles;
   leave auth/SLO/deployment rows in `FUTURE`.
8. At `G9`, replace fake/candidate positives with current real-Adapter and human
   evidence, then retire old refs only after every `PORT`/`ORACLE` row is marked
   migrated, deferred or rejected with an owner and reason.

## 9. Audit limitations

This was static source, test and Git-history analysis. Historical suites and
real product paths were not rerun during asset extraction. Symbol names and
source dependencies are exact for the cited historical tips; current target
symbols intentionally remain activation-time work because P3-1 and later shared
P3 contracts can change them. No old pass count, candidate receipt, reader fact,
policy decision, wire roundtrip or fake positive transfers acceptance credit.
