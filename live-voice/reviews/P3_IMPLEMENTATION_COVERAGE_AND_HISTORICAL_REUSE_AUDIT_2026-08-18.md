# P3 implementation coverage and historical reuse audit — 2026-08-18

> **Historical coverage snapshot with current routing.** The percentage estimates
> remain bound to implementation baseline
> `7a8ba7e82042e188efe6adbac98d47363b0d5d8e` and have an approximate `±5%`
> review margin. They intentionally do not re-score later P3-G0 work and are not
> acceptance credit or package closure. Current [STATUS](../STATUS.md) records
> that P3-G0 passed only its D-086 authoritative-foundation Gate, exact product
> source `f24dd17d` remains a failed controlled product-readiness candidate, and
> P3-1 is active. At each package activation, validate only its selected assets
> against current HEAD and the relevant Git range; no separate G0 delta document
> or whole-audit re-score is required.

The companion
[source-asset extraction manifest](P3_HISTORICAL_SOURCE_ASSET_EXTRACTION_MANIFEST_2026-08-18.md)
decomposes the 33 requested commits and the preceding S8.5 contract into 57
implementation-level assets with source symbols, representative tests,
dependencies, authority exclusions, current overlap, target packages and gates.

## 1. Purpose and authority boundary

This record preserves three connected facts that would otherwise be lost when
the old integration/incubator branches retire or are absent from the current
repository object database:

1. how much of each of the nine complete-P3 packages exists on the committed
   baseline, including the strongest existing implementation and the decisive
   remaining gaps;
2. when a historical asset is eligible for extraction under the authoritative
   P3 dependency waves; and
3. which individual historical commits contain a portable module, a regression
   oracle, a current-schema rewrite candidate, future-scope material or only an
   exact-source historical record.

The authoritative package outcomes, dependencies and `Done when` boundaries
remain in the [complete P3 execution plan](../roadmap/FULL_P3_EXECUTION_PLAN.md).
Current capability judgement and the active execution packet remain in
[STATUS](../STATUS.md). Root [TESTING](../../TESTING.md) continues to own risk,
scenario and independent-review requirements. This audit neither redefines
those authorities nor activates a historical branch as the current queue.

Git/source/tests were treated as implementation fact. Historical test results
were treated only as exact-source regression evidence. A candidate, reader,
policy, fixture or passing fake test received no authority or positive real-path
credit that its source explicitly withholds.

### 1.1 What “complete historical analysis” means here

The audit is **complete for the four historical populations explicitly requested
for P3 reuse**, not for every commit reachable anywhere in the repository:

| Population | Coverage in this audit |
|---|---|
| 3A durability/Executor integration | All 13 requested linear commits |
| 3B foundation integration v2 | All 8 requested linear commits |
| Unintegrated reader/recovery work | All 3 specified sibling single-commit candidates |
| S8.5 incubator | All 9 requested commits, plus the immediately preceding `bc53e75d` contract as required semantic context |

Thus the requested commit denominator is **33/33 inspected and classified**.
Every materially reusable production module, contract, fixture, test-oracle
family and documentation/provenance change in those diffs is represented by a
per-commit row and one or more of the 57 source-asset entries. Generic scalar
validators and individual parameterized cases remain grouped under their owning
asset rather than being inflated into separate rows.

This completeness claim does **not** include unrelated historical branches or
ancestors, every repository commit, later product work, a line-by-line patch
recipe, rerunning every old suite or proving current acceptance. Exact current
target files/symbols, schema edits and verification commands intentionally stay
open until the owning package activates against its then-current HEAD. Those
are dynamic implementation facts, not missing branch-forensics work.

## 2. Scoring method and overall conclusion

Each package estimate considers four equally important questions:

1. Is the required contract implemented rather than merely named?
2. Does the authoritative product path use it with the required persistence,
   fencing and scope binding?
3. Do risk-proportional automated tests cover positive, negative, failure,
   concurrency and restart behavior?
4. Is there clean-source review and real product/Adapter acceptance?

The committed baseline has useful foundations in every P3 domain, but no
package meets its complete `Done when` boundary. The formal package result is
therefore **0/9 complete**. The unweighted mean of the estimates is about
**32%**; that aggregate is orientation only because package sizes and
dependencies differ.

The imported historical audit recorded focused backend verification as
`475 passed, 2 skipped, 1 warning`, but did not retain an exact command in the
current evidence set. Treat that count only as historical context, not current
evidence credit. It does not cover the absent multi-Task, complete-control,
D1/D2 or cumulative real-product requirements.

## 3. Pre-G0 nine-package implementation snapshot

| Package | Conservative coverage | Implemented on the baseline | Decisive gaps before closure |
|---|---:|---|---|
| `P3-1` — canonical multi-Task Core/Store | **40%** | Canonical Task/Attempt/Event/Command/TaskResult records; SQLite schema v3, WAL, migrations, command ledger, outbox, idempotency, CAS, exact get/list/status/events and scope isolation | A second non-terminal Task in one Session is still rejected; `current_background_tasks` remains mutation/result authority rather than a UI hint; no Task-to-Task successor relation; queued/paused semantics and the two Task models are not unified; no real two-Task + dialogue + refresh + restart proof |
| `P3-2` — complete commands and revision | **42%** | `create/get/list/status/events/result/adjust/cancel/retry`; exact command identity/fingerprint; confirmation, ledger replay, atomic ordered adjustment, terminal fencing and retry Attempt lineage | No complete `update/provide_input/pause/resume/reprioritize`; no explicit new-`task_id` successor revision; no unified accepted/applied/rejected/unsupported/conflict/timeout/unknown result model; no complete invalid-state/concurrent-terminal/restart/capability matrix |
| `P3-3` — capability-driven Executor and Attempt lifecycle | **45%** | Direct isolated Executor, journal, project lock, owner/lease/heartbeat, outbox claim fencing, exact cancel, expired-lease recovery, apply crash-window `unknown`, late-write isolation and authoritative terminal observations | No versioned complete capability catalog; no capability-driven selection/fallback; one injected Executor and one-current-Task product assumption remain; no multi-Task capacity admission/queue contract; no bounded useful-progress timeout/orphan settlement |
| `P3-4` — D0/D1/D2 durability | **20%** | D0 disconnect survival while the process remains alive; restart-interrupted/unknown classification, repeated reconciliation and cross-process ownership tests | No persisted selected durability level/capability version; no D1 checkpoint schema integrated into current Store, real resume Adapter or duplicate-effect proof; no D2 effect ledger/reconciliation/manual-resolution path; D1 same-versus-linked Attempt remains undecided |
| `P3-5` — result, replay, unread and terminal notification | **52%** | Immutable bounded TaskResult with source terminal event and artifact hash; no false result for non-completed terminal state; Store-owned atomic event prefix; terminal presentation rereads result and fences scope/generation/ACK/TTS | Public events declare cursor replay unsupported; no Store-owned durable unread/consumption/ACK; pending notification maps clear on stop; addressed result is restricted to the current Task; B5 can discard a legal result when context is full; no accepted real terminal/result/ACK journey |
| `P3-6` — generalized Voice–Task Bridge | **28%** | Committed-input and origin fencing, exact scope/Task validation, separate confirmation, create/status/cancel plus bounded adjust/result, negation and ambiguity fail-closed | No multi-Task target resolution or clarification; missing full operations; text/voice parity is incomplete; Chinese update still depends on narrow “把/将” forms; no general precision/recall corpus |
| `P3-7` — formal Integrated Web P3 | **30%** | Current Task/progress/result/terminal projections, reconnect journal, strict TaskEvent revalidation, generation/ACK/TTS fencing and partial feature-off coverage | No Task list/selector, durable unread/replay, revision relation or full control surface; the formal shell remains preview-only; legacy hooks and implicit production flags remain; no real two-Task recovery journey |
| `P3-8` — observability, configuration, privacy and retirement | **22%** | Correlation/interaction/turn/response/round/task/attempt identity, closed schemas, sensitive-field rejection, bounded exporter and broad isolated tests | No complete command/event/outbox/executor/checkpoint/effect/presentation trace; runtime adapter is not composed; recovery seams are not locatable; Demo itinerary/bypass, old entrypoints, compatibility runners and authority flags remain |
| `P3-9` — cumulative complete-P3 acceptance | **10%** | Broad backend/frontend regression foundations and exact-source historical evidence | No cumulative complete-P3 scenario matrix, clean immutable multi-Task/D1/D2/control/replay journey, competitor-gap review, independent cross-module review or final human acceptance; the latest physical run recorded defects rather than PASS |

The detailed module-level source findings that support this package projection
remain in the [2026-08-17 module code-fact audit](MODULE_CODE_FACT_AUDIT_2026-08-17.md).

## 4. Authoritative execution waves and reuse admission

This section does not create a second schedule. It maps reusable historical
assets onto the existing package order so an old branch cannot be integrated
before its current contract owner is ready.

1. **Wave 0: P3-G0 — passed authoritative foundation.** D-086 accepted the
   sequencing risk and recorded PASS for the P3 foundation Gate without
   upgrading the failed controlled candidate. No G0 production lane remains; retain its
   blocker reproductions and zero-forbidden-side-effect assertions as history/
   oracles for their first owning package.
2. **Wave 1: canonical spine — P3-1.** Freeze canonical multi-Task identity, state,
   Store schema/migration, current-Task-as-hint semantics and successor
   relations. Historical identity/fingerprint/event-lineage models are design
   input only until that contract is accepted.
3. **Wave 2: core fan-out — P3-2, P3-3, P3-5A and P3-8A.** After P3-1 is
   accepted, extract command/revision atomicity, capability/admission vocabulary,
   durable result/event/unread primitives and additive diagnostics,
   configuration and privacy assets in non-overlapping owner lanes. `P3-2` and
   `P3-5A` use one Core/Store lane whenever they touch the same schema or
   transaction. Central profile/composition activation remains with the owner
   of the touched entrypoint.
4. **Wave 3: durability and product semantics — P3-4, P3-6, P3-5B and P3-8A.**
   D1/D2 code waits for accepted P3-3 capability/Attempt implementation; Bridge
   integration waits for accepted P3-2 and P3-5A implementations/tranches;
   presentation waits for accepted P3-5A. These lanes can then run concurrently
   when file and authority ownership are disjoint.
5. **Wave 4: formal carrier — P3-7.** Strict Web replica assets may be prepared
   from frozen schemas, but real product composition waits for the applicable
   P3-2 through P3-6 backend implementations to be integrated and accepted. Do
   not mix the old Panel/Registry wiring into this single-writer integration
   lane.
6. **Wave 5: retirement and acceptance — P3-8B, then P3-9.** Finish shared
   composition and retire superseded authority only after P3-7 proves
   replacement; then execute cumulative acceptance on one exact clean source.
   Evidence preparation may overlap, but the final acceptance run may not.

`P3-5A/B` and `P3-8A/B` are scheduling tranches, not additional packages. The
authoritative critical path, parallel eligibility and collision rules are in
[the complete P3 plan](../roadmap/FULL_P3_EXECUTION_PLAN.md#6-dependency-graph-critical-path-and-dispatch-waves).

### 4.1 Package-level reuse overlay

| Target | Historical assets worth extracting | Admission rule / forbidden shortcut |
|---|---|---|
| `P3-G0` | Blocker-specific reproduction, clean-source verification and zero Agent/Tool/Task/audio/history mutation assertions | Gate passed under D-086; no 3A, 3B or S8.5 production-code migration receives retroactive G0 credit |
| `P3-1` | S8.5 identity/fingerprint/event-lineage invariants; 3A control vocabulary as design input | Do not adopt the same-Task revision sidecar or splice an old Store schema into current v3 |
| `P3-2` | `249e9081` command contract; `fe2884db` transactional apply boundaries; `caed0ff2` idempotency/failpoint/concurrency oracles; S8.5 revision races | Freeze new-Task successor and exact blocking-question `provide_input` semantics first |
| `P3-3` | `6bc8d6ac` durability/capability vocabulary; `228c93c7` unsupported-path oracles; 3B secure-Executor policy/wire; `0c994b1b` cleanup/fencing | Candidate ports never prove a real control operation or Adapter capability |
| `P3-4` | `13459f2d`, `cbca1cec`, `b017a9e6` D1 assets; `74bf6788`, `bfd387a1`, `83de3eb8`, `e5603aa7` D2 assets; `70648baf` cohost tests; `6e1b4bfc` recovery facts | Decide same-versus-linked recovery Attempt before using `6d04ff61`; readers/facts cannot grant recovery authority |
| `P3-5` | S8.5 event-prefix, late-event and application/lifecycle separation oracles; transactional-snapshot consistency rules | In-memory ACK and sidecar revision state cannot stand in for durable unread/replay |
| `P3-6` | `f13cfe8d` committed Bridge and confirmation binding; `8be8398a` confirmation-conflict/restart scenarios | Rewrite for multi-Task resolution, exact blocking input and text/voice parity |
| `P3-7` | `ab200d2c` closed-schema replica, generation fence and lineage monotonicity; `8be8398a` disconnect/feature-off tests | Do not reuse the old large Panel/Registry/AgentServer wiring patch |
| `P3-8` | 3B secure-Executor projection, privacy lifecycle, OTel export and SLI-window rules | Production auth/tenant/deployment/SLO/retention remains outside current P3 |
| `P3-9` | All applicable failpoint, concurrency, corruption, restart, verifier, feature-off and real-Adapter scenarios | Historical pass counts and acceptance labels never transfer to current source |

## 5. Historical Git topology and integration fact

| Historical line | Exact identity | Baseline relationship | Current integration fact |
|---|---|---|---|
| 3A durability/Executor integration | tip `3cd0f46cec6d3c145eab218e865c4d4e4d4a5a1e`; 13 linear commits after `2529e2ce743ac606c21198c3efaa1c97c14ac211` | 35 files, `+29,539/-239`; its current-HEAD merge base is `7b69fdeb9e9f47bc32f390ace19f655beab865c6` | Integrated only inside the old 3A integration branch. Of its 35 paths, 33 are absent on the audited HEAD and the two shared Store/Core paths have diverged. No whole commit is a current conforming patch. |
| 3B foundation integration | tip `d3e6edf4dd9a19f1bfcf031e9c0820131477b028`; 8 linear commits after the same old baseline | 38 files, `+19,740`; current-HEAD merge base `7b69fdeb9e9f47bc32f390ace19f655beab865c6` | All 38 added files are absent on the audited HEAD; the eight commits have no current patch-equivalent. |
| Three unintegrated reader/recovery candidates | `b017a9e6a72afbc185f2ac4bc179703551d8a5be`, `e5603aa729bb1f174ee4223ce29c228213267cc6`, `6e1b4bfcbb337d0a7e5de17708b3956d39b094aa` | Three parallel single-commit branches with parent `3cd0f46c`, not one linear three-commit branch | Each depends on old 3A modules/schema and needs independent extraction review. |
| S8.5 incubator | tip `d2f860fd2e42421a758751869db9b45f0143df3d`; merge base `a53856de0af12e2c1b11e6cc8f2dc0a18150a99a` | 10 branch-only commits total. The requested nine are the commits after the preceding `bc53e75df4fedc3ce8dd9f27001daf16525ccd4f` contract commit; those nine touch 41 files, `+11,518/-145`. | None of the nine has a current patch-equivalent. A trial three-way merge of the full branch produced at least 15 content conflicts, in addition to the semantic conflicts below. |

“Integrated” in an old branch name means integrated into that old isolated
integration branch. It does not mean merged, rebased or patch-equivalent on the
audited current HEAD.

## 6. Per-commit extraction inventory

Classification:

- `PORT-MODULE` — high-value isolated logic that may become the starting point
  for a current-owned implementation after its admission rule is satisfied.
- `TRANSPLANT-ORACLE` — preserve contracts, fixtures, negative paths, race or
  failure invariants; production authority must be implemented elsewhere.
- `REWRITE-CURRENT` — the semantic intent is useful, but old Store/Core/product
  integration code must be rebuilt on the current model and schema.
- `FUTURE-SCOPE` — valid later Productized/RC/Production material, excluded from
  current feature-complete P3.
- `HISTORY-ONLY` — exact-source review/status/decision/showcase material; never
  current authority or implementation credit.

### 6.1 3A durability/Executor — 13 commits

| Commit | Portable content | Classification and required adjustment |
|---|---|---|
| `6bc8d6ac` | D0/D1/D2 taxonomy, capability boundaries and illegal-upgrade/fail-closed tests | `TRANSPLANT-ORACLE`: align vocabulary with the current capability catalog and re-evaluate old redispatch/Attempt assumptions |
| `249e9081` | Complete control-operation vocabulary, command fingerprint, conflicts and result categories | `TRANSPLANT-ORACLE`: map to current P3-2 command, successor and `provide_input` contracts |
| `13459f2d` | Checkpoint producer/schema/version/checksum and Task/Attempt/scope/context binding | `PORT-MODULE`: connect to the current Store and one real checkpoint-resume Adapter; selection alone is not D1 |
| `74bf6788` | D2 intent/receipt/observation/settlement/manual/compensation model | `PORT-MODULE`: retain stable effect identity/state transitions and add a real Effect Adapter |
| `228c93c7` | Executor-control candidate interface and unsupported/zero-side-effect paths | `TRANSPLANT-ORACLE`: source deliberately performs no pause/resume/update/reprioritize/start/cancel authority |
| `bfd387a1` | SQLite D2 effect ledger, stable operation key, idempotency, CAS and corruption checks | `PORT-MODULE`: cohost through the current Store migration and transaction owner |
| `cbca1cec` | SQLite D1 checkpoint port, integrity and identity validation | `PORT-MODULE`: adapt to current schema; persistence alone does not prove recovery |
| `70648baf` | D1 checkpoint and D2 ledger cohost, transaction isolation and conflict tests | `TRANSPLANT-ORACLE`: rewrite against the current cohosted schema |
| `6a8c8377` | Task-Core D2 candidate/facts boundary, late facts and conflict fencing | `TRANSPLANT-ORACLE`: candidate-only; connect any implementation to current Task/Attempt authority |
| `6d04ff61` | Same-Attempt recovery preconditions and negative cases | `TRANSPLANT-ORACLE`: do not retain its same-Attempt policy before the P3-4 design checkpoint accepts that choice |
| `83de3eb8` | Transactional D2 ledger-prefix/snapshot reader and consistency/corruption checks | `PORT-MODULE`: adapt connection ownership and current schema |
| `fe2884db` | Atomic control apply across command ledger, outbox and state | `REWRITE-CURRENT`: preserve transaction/failpoint oracles; rebuild the old Store/Core patch on current schema v3 |
| `3cd0f46c` | Durable D2 candidate runtime/facts, conflict and replay handling | `REWRITE-CURRENT`: retain model/oracles; old Store/Core changes cannot be spliced into current adjustment/result/retry/terminal semantics |

### 6.2 3B foundation — 8 commits

| Commit | Portable content | Classification and required adjustment |
|---|---|---|
| `6306b21e` | Mixed secure-Executor, privacy, OTel, auth, SLO and topology foundations | `REWRITE-CURRENT`: extract only secure/privacy/OTel files for current P3; leave auth/SLO/topology in future scope |
| `96ca1306` | Secure-Executor enforcement plus auth/tenant Adapter | `REWRITE-CURRENT`: port the secure half into capability admission; classify the auth half as `FUTURE-SCOPE` |
| `a770f862` | Privacy lifecycle, redaction/retention/delete candidate and invalid-state tests | `PORT-MODULE`: bind to real log, TaskResult/artifact and lifecycle owners; declarations alone grant no P3-8 credit |
| `a1d42996` | Content-free SLI window, time boundaries and missing/late sample handling | `TRANSPLANT-ORACLE`: use for P3-8/latency measurement; it emits no telemetry and decides no SLO |
| `e499217f` | Deployment lifecycle conformance | `FUTURE-SCOPE`: public deployment/release is outside current feature-complete P3 |
| `df80cfb3` | Secure-Executor canonical wire, closed schema and unknown/sensitive-field rejection | `PORT-MODULE`: align with current admission/capability contract; wire validation does not prove sandbox enforcement |
| `90fa6927` | Auth/tenant canonical wire | `FUTURE-SCOPE`: Production authentication/multi-tenancy is excluded from current P3 |
| `d3e6edf4` | Deployment lifecycle wire | `FUTURE-SCOPE`: retain for later Productized/RC/Production work |

### 6.3 Unintegrated reader/recovery candidates — 3 commits

| Commit | Portable content | Classification and required adjustment |
|---|---|---|
| `b017a9e6` | Caller-owned-transaction D1 checkpoint reader, full-database integrity/schema/bounds checks and prefix fingerprint | `PORT-MODULE`, highest priority after D1 storage activation: first port its `cbca1cec` dependency, then bind it to current Store transactions and a real resume policy |
| `e5603aa7` | Same-transaction comparison of current D2 candidate head and ledger prefix | `PORT-MODULE`/`TRANSPLANT-ORACLE`: useful facts reader and stale/corrupt coverage; it grants no recovery authority |
| `6e1b4bfc` | Append-only Executor epoch/generation/lease facts and conflict/corruption/concurrency tests | `REWRITE-CURRENT`: extract the facts model and oracles; do not cherry-pick its approximately 1,931-line schema-v2 Store diff or its all-false authority slots |

### 6.4 S8.5 incubator — requested 9 commits

| Commit | Portable content | Classification and required adjustment |
|---|---|---|
| `caed0ff2` | Fingerprint, accepted-versus-applied separation, transaction failpoints, concurrent unique owner/outbox, late-event fencing and event lineage | `REWRITE-CURRENT`: high-value invariants, but replace the same-`task_id` revision sidecar with current canonical Task/successor semantics |
| `f13cfe8d` | Committed-only Bridge, scope/target revalidation, confirmation fingerprint and feature-off zero effects | `PORT-MODULE`: generalize to multi-Task resolution, exact blocking-question input and text/voice parity |
| `0c994b1b` | Predecessor cleanup, `unknown` fencing, late writes and verifier/path/remote/fixture safety | `PORT-MODULE`/`TRANSPLANT-ORACLE`: integrate through formal Executor capabilities, not a private revision Executor |
| `ab200d2c` | Web closed-schema replica, disconnect generation fence, lineage monotonicity and application/lifecycle separation | `PORT-MODULE`: rebuild on current multi-Task/result/unread schema; do not reuse the old large Panel patch |
| `be4e71b3` | Incubation progress review and old STATUS | `HISTORY-ONLY`: exact-source evidence only |
| `8be8398a` | Recovery-pump, confirmation-conflict zero-effect and restart/feature-off product scenarios | `TRANSPLANT-ORACLE`/`REWRITE-CURRENT`: migrate scenarios; do not reuse the deeply conflicting Registry/AgentServer/Web wiring |
| `fc7348f2` | Old one-revision decision/showcase clarification | `HISTORY-ONLY`: conflicts with current successor-Task semantics |
| `c9e7aba6` | Exact-source S8.5 product-integration review | `HISTORY-ONLY`: regression evidence, not current acceptance credit |
| `d2f860fd` | Old branch STATUS synchronization | `HISTORY-ONLY`: mutable status must be rebuilt from current source |

The preceding `bc53e75d` contract commit is outside the requested nine. Its
same-Task running revision model remains useful only as historical design input
and an invariant source; it is not the accepted current revision authority.

## 7. Semantic conflicts that must not cross the migration boundary

1. **Task revision identity.** S8.5 keeps a running Task on one `task_id` while
   revision `1→2` starts a new Attempt. Current P3 permits a running update only
   at a proved checkpoint and requires terminal revision to preserve the
   predecessor/result while creating an explicit new-`task_id` successor.
2. **Input semantics.** S8.5 accepts a general additive fact. Current
   `provide_input` answers one exact blocking question/decision under bounded
   authority.
3. **D1 Attempt identity.** `6d04ff61` selects same-Attempt recovery without
   performing resume. P3-4 still requires an accepted same-versus-linked
   decision with retry/result/provenance accounting.
4. **Facts versus authority.** Candidate selectors, snapshot readers, recovery
   facts and policy/wire modules describe or validate facts. They must never be
   presented as resume, reconciliation, sandbox or mutation authority.
5. **Schema ownership.** The old 3A Store modifications are schema v2-era. The
   current baseline is schema v3 with later adjustment, result, retry and
   terminalization semantics. All Store changes need an owner-reviewed current
   migration rather than patch composition.
6. **Completion boundary.** Production authentication/multi-tenancy, public
   deployment, SLO/retention and release/rollback remain outside feature-complete
   P3 unless a newer accepted decision changes scope.

## 8. Regression oracles to preserve before branch retirement

The following historical scenarios have current value even when their old
production implementation does not:

- confirmation fingerprints bind every semantic command field;
- exact replay is idempotent and a changed fingerprint conflicts;
- request/apply failpoints leave no partial Task, Attempt, event, ledger or
  outbox effects;
- concurrent commands allocate one authority owner and one durable outbox item;
- stale revision/Attempt/claim/lease/owner writes are fenced;
- predecessor late progress, terminal, result or patch cannot corrupt successor
  truth;
- cleanup `unknown` cannot allocate or start a replacement;
- cancel/update/terminal/restart races settle exactly once;
- D1 validates producer, schema, checksum, Task/Attempt/context and effect-safety
  bindings;
- D2 preserves intent, stable operation identity, observation, settlement and
  explicit unresolved/manual state;
- feature-off is zero-effect at parser, Store/schema, network and DOM layers;
- Web replicas reject unknown schemas, regressing lineage and wrong generation;
- verifier failure/timeout, fixture mutation, remote/path mismatch and dirty
  source cannot report success.

When transplanted, each oracle belongs in the current capability owner's test
suite. Retired stage/readiness runners must not remain as a second acceptance
authority; see the [branch-retirement audit](BRANCH_CONTENT_RETIREMENT_AUDIT_2026-08-17.md).

## 9. Historical evidence boundary

- The old 3A `772/772` result is historical exact-source regression evidence.
  Its candidate/facts suites contain no positive real D1 resume, D2 external
  effect or current-source Tier-3 product acceptance.
- The tracked 3B review records foundation suites at `281 passed` and a broader
  run at `1650 passed, 2 skipped`. A separately mentioned `499/499` lacks a
  tracked exact command/source result and receives no credit. The review ended
  `PARTIAL / SOURCE-AUTOMATION PASS / ACCEPTANCE OPEN`.
- The S8.5 review records backend `363/363` reaching PASSED before the pytest
  process failed to exit cleanly, Integrated Web `327 passed` and a successful
  production build. Independent Tier-3 review and a real Speech/Agent/Executor
  journey did not run.
- The recorded `7a8ba7e` focused result in §2 is historical context only; without
  its exact retained command it grants no current Store/Core/Executor/Bridge/
  text-composition evidence credit.

No historical count upgrades the nine package estimates or supplies current
acceptance. Exact commands, source identity and clean completion must be rerun
under the owning current package.

## 10. Central extraction versus activation-time implementation

Historical source discovery is centralized here; it must not be repeated from
scratch by each execution worker. The companion
[source-asset manifest](P3_HISTORICAL_SOURCE_ASSET_EXTRACTION_MANIFEST_2026-08-18.md)
is the source inventory and uses an asset—not a commit—as its extraction unit.
This is necessary because mixed commits such as `6306b21e` contain both
current-P3 candidates and explicitly deferred Production material.

The central inventory freezes facts that are stable before implementation:
source commit/file/symbol, fixtures and tests, dependency chain, actual and
forbidden authority, semantic conflicts, target package, earliest gate and
current overlap. It deliberately does **not** freeze every final destination
symbol, schema patch or exact verification command while P3-1 and later shared
P3 contracts can still change those targets.

At package activation, the Integration Owner selects explicit asset IDs and
creates one bounded current-HEAD mapping. The worker verifies that mapping,
implements only its assigned files, transplants the named oracles and reports
evidence. The worker does not rescan all historical branches, create an alternate
semantic owner or silently revive an old decision. This two-layer model prevents
duplicated forensics without producing stale line-level implementation plans.

## 11. Extraction protocol and current-HEAD validation triggers

For every extracted asset, record at least:

| Field | Required meaning |
|---|---|
| `source_repository` / `source_ref` / `source_commit` / `source_files` | Exact recoverable historical origin |
| `target_package` / owner | Current P3 package and semantic owner |
| `asset_type` | Module, contract, fixture, invariant or test oracle |
| `current_dependency` | Required contract/schema/capability and whether freeze or integrated acceptance is required first |
| `required_rewrite` | Old assumptions that must be removed |
| `tests_to_transplant` | Positive, negative, failure, race and restart coverage |
| `forbidden_claim` | Authority/completion the asset does not prove |
| `activation_gate` | Review and real-path condition before composition |
| `retirement_gate` | Proof required before the old branch/file can disappear |

Current-HEAD validation triggers are:

1. at each package start, select only that package's admitted asset IDs, record
   the current HEAD and relevant Git range, and validate their current mapping;
   Git history is the G0 backtracking source, so no standalone G0 delta or
   aggregate percentage re-score is required;
2. after P3-1 freezes state/schema/successor semantics, re-evaluate 3A Store
   ports and the S8.5 revision kernel;
3. after P3-3 freezes capability/admission, re-evaluate secure-Executor and D1/D2
   Adapter candidates;
4. after the P3-4 recovery-Attempt decision, re-evaluate `6d04ff61`;
5. for each activated mapping, rerun current-source review/tests under the
   owning package; and
6. before deleting historical refs, prove every `PORT-MODULE` and
   `TRANSPLANT-ORACLE` item was migrated, explicitly deferred or deliberately
   rejected with an owner and reason.

This document remains a dated coverage/source inventory rather than mutable
package status. The activation record owns current mapping and evidence, and
neither this audit nor source availability authorizes integration of an old
branch.
