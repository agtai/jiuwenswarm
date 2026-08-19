# Live Voice current project status

> Updated: 2026-08-19. This is the only mutable source for current product
> judgement, capability completion, remaining scope, dependency order and the
> next execution packet. Read live branch/HEAD/upstream state from Git; do not
> copy transient ahead/behind, dirty-tree or “uncommitted” claims into this file.

## Project judgement

- **Last product-code baseline assessed:**
  `f24dd17d336c8266954f2d7299ca13bd0314d424`. Documentation-only commits after
  that source do not change its product credit.
- **Current product status:** **P3 EXPANSION ACTIVE — P3-G0 is scope-closed as
  the authoritative P3 foundation under D-086; controlled product readiness
  remains unpassed.** The six recorded P3 product-truth repair groups and
  explicit build profile retain their source/automated evidence. The failed
  post-TTS continuation is deferred to P1/P2 completion and the unrun combined
  Task Journey returns in cumulative acceptance; neither receives a fabricated
  physical PASS.
- **Accepted historical baseline:** `PASS — INTEGRATED WEB ALPHA` remains bound
  only to `d33b520e0d21ae0829d30814d77a01cc18256f09`. Later source and broader
  functionality do not inherit that result.
- **Latest physical product result:** `FAIL — P3-G0 CONTROLLED CANDIDATE NOT
  ACCEPTED` on exact clean product source `f24dd17d336c8266954f2d7299ca13bd0314d424`.
  See the sanitized [P3-G0 attempt](evidence/P3_G0_PRODUCT_READINESS_FAIL_20260819_f24dd17d.md).
- **P3-G0 status:** **CLOSED — AUTHORITATIVE P3 FOUNDATION; PRODUCT-READINESS
  DEFERRED.** [D-086](decisions/DECISIONS.md) accepts the sequencing risk and
  removes the failed P1/P2 hands-free condition as a P3-1 Gate without changing
  the immutable candidate result.
- **Current highest priority:** execute P3-1 canonical multi-Task identity,
  state, Store and migration. The deferred P1/P2 issue is recorded in the
  [post-TTS continuation record](evidence/P1_P2_POST_TTS_CAPTURE_CONTINUATION_DEFERRED_20260819.md)
  and must close before a later controlled-candidate or feature-complete claim.
- **Integration:** integration with a `develop` ref is deferred until the
  feature-complete boundary below passes. At that future boundary, re-read the
  configured remotes and live ref before any integration; this document assumes
  no current remote name or divergence count.

## Completion boundaries

These boundaries define what “done” means. They are cumulative but must not be
reported interchangeably.

| Boundary | Required outcome | Explicit exclusions / consequence |
|---|---|---|
| **Controlled product-readiness candidate** | Current formal Web route passes affected automation, Tier-3 review and one clean real microphone/TTS journey with truthful Task adjustment, result and terminal notification | Does not prove all P1/P2/P3 features, generalization, RC or Production |
| **Feature complete — trigger for `develop` integration** | Formal P1/P2 plus complete P3 are implemented on the supported Integrated Web carrier; multiple addressed Tasks, full control operations, replay/unread result, capability-driven Executor/D0–D2 semantics where supported, latency targets, general configuration, removal of Demo/legacy authority, broad automated verification, competitor-gap review and independent cross-module review are closed | Excludes production authentication/multi-tenancy, public deployment, SLO/retention/release operations, additional platform commitments and optional Native model-level duplex |
| **Productized candidate** | Feature-complete source is integrated, configuration/diagnostics/privacy/platform support are hardened for the declared deployment and the cumulative integration diff passes product acceptance | Still does not claim public production operations |
| **RC / Production ready** | Production authentication, tenancy, deployment, observability/SLO, retention, security operations, compatibility matrix and release/rollback support pass their own acceptance | Not part of the pre-`develop` feature-complete trigger |

The full P1/P2/P3 capability boundary remains grounded in
[the accepted design snapshot](architecture/FULL_SOLUTION_2026-07-30.md) §§2,
4–5. Its dated carrier, code baseline, work-package schedule and timeboxes are
historical and cannot become the current queue.

## Current capability completion and full remaining scope

`COMPLETE` means the named boundary is implemented and accepted on identified
source. `PARTIAL` means useful implementation exists but required behaviour or
evidence remains. `BLOCKED` means a demonstrated defect prevents the positive
journey. `NOT STARTED` means no accepted current implementation boundary.
These rows are evidence-based planning judgements, now grounded in the
[module code-fact audit](reviews/MODULE_CODE_FACT_AUDIT_2026-08-17.md). That
audit is documentation, not product progress: it grants no new module-completion
credit and does not repair defects.

The detailed complete-P3 workload, P3alpha inheritance and package acceptance
are defined in the [complete P3 execution plan](roadmap/FULL_P3_EXECUTION_PLAN.md).
That preparatory contract is not the active queue; this STATUS still activates
only one coherent packet at a time.

| Capability / module | Status and implemented fact | Remaining for feature complete | Dependency / acceptance |
|---|---|---|---|
| Audio Device & browser I/O | **PARTIAL; deferred from the P3-1 Gate.** Browser capture/playout, lifecycle fencing and dedicated media wiring exist, but `f24dd17d` twice entered `AUDIO_CAPTURE_DURATION_EXCEEDED` after TTS instead of continuing automatically | Execute the [recorded repair direction](evidence/P1_P2_POST_TTS_CAPTURE_CONTINUATION_DEFERRED_20260819.md); physically verify overlap/idle rotation; device/permission recovery; AEC/NS/AGC and double-talk; measured first-frame/loss/stop targets | P1/P2 completion before controlled-candidate/feature-complete acceptance; not a P3-1 dependency |
| Speech Recognition | **PARTIAL.** Two real microphone finals reached the Agent, but each post-TTS failure also produced streaming-route abort, cleanup timeout and unacknowledged cancel | Exact capture/provider-speech-start attribution, robust fallback/cancel, Provider-neutral configuration, fixed accuracy/latency corpus and broader device/network validation | Audio I/O, media route and benchmark owner |
| Speech Synthesis | **PARTIAL.** Streaming/Batch TTS, browser playout, response ownership and ACK paths exist | Provider-neutral configuration, first-audio/underrun/pronunciation targets and complete stale/cancel recovery | Conversation Runtime ownership and Audio I/O stop confirmation |
| Realtime Media | **PARTIAL; deferred from the P3-1 Gate.** Dedicated transport, media registration and presentation ACK worked, but repeated post-TTS capture rotation did not preserve a usable media loop | Repair the exact rotation/cancel seam; backpressure/load targets; drop/reorder/corruption/reconnect matrix; stable diagnostics across repeated recovery | Audio I/O plus Conversation Runtime; cumulative real network/device verification |
| Conversation Runtime | **PARTIAL.** committed-input fencing, generation ownership, ACK/history projection, Exit fencing and playout-time barge-in exist; manual retry admitted a second turn | Automatic continuation without recurrent recovery failure; interruption during Agent generation, complete `ask_user` voice loop and cross-load arbitration | Media, Interaction Intelligence, Agent Bridge and presentation regressions |
| Interaction Intelligence | **PARTIAL.** VAD/EOT and bounded dialogue/background routing exist for the controlled journey | General natural-language routing, false endpoint/interruption and echo/double-talk evaluation, language/config generalization; Native model-level duplex remains optional | Streaming Speech plus Runtime; measured golden corpus |
| Agent Bridge and dialogue truth | **PARTIAL.** Real Agent dialogue/tools and bounded response/progress integration exist | Non-blocking progress provenance, strict Task-truth isolation, bounded result-context reservation and unconstrained reread prevention | Runtime, Task/Event truth and affected text-path regressions |
| Task Control Core and Store | **PARTIAL.** Stable Task/Attempt/Event/Command IDs, SQLite schema v3, idempotency, outbox, results, adjustments and one-current-Task recovery exist | Multiple addressed Tasks, target disambiguation, `update/provide_input/pause/resume/reprioritize`, successor revision, replay/unread and one canonical Task model | Executor status resolution, Voice–Task Bridge and restart/concurrency matrix |
| Executor & Durability | **PARTIAL.** Direct isolated Code Executor, lease/journal, terminalization and recovery foundations exist and are statically closed on the audited source | Cumulative physical re-verification of Agent-return → validation → application → result → terminalization; bounded timeout/orphan handling; capability selection; supported D1 checkpoint and D2 reconciliation semantics | P3-1 shared identity first, then P3-3/P3-4 and P3-9 real-path closure |
| Voice–Task Bridge | **PARTIAL.** Natural-language create/status/adjust/result paths and durable adjustment delivery exist | General routing, explicit multi-Task targeting, full Task operations, text/voice parity, clarification and zero false truth | Task Core and Executor truth; precision/recall plus zero-side-effect tests |
| Integrated Web product experience | **PARTIAL.** The explicit profile, authenticated route, P2/P3 composition, real foreground Agent text/TTS and manual retry worked; automatic listening failed after both responses and is deferred from P3-1 | Complete P3 controls/projections while preserving profile semantics; later close capture recovery, truthful queued/running/terminal UX, device/privacy/recovery UX and the cumulative human journey; retire legacy hooks/flags | P3-1 through P3-9 plus deferred P1/P2 completion |
| Observability, benchmark and latency | **PARTIAL.** Trace/correlation and historical verification foundations exist | Execute the [latency optimization plan](roadmap/LATENCY_OPTIMIZATION_PLAN_2026-08-18.md): fresh physical baseline; stable EOT/Agent/TTS/first-audible diagnostics; low-risk pipeline waits; authoritative ACK; formal sentence-level Agent→TTS overlap; fixed-corpus p50/p95 and no-regression proof | Instrumentation before optimization; fixed corpus/environment; Conversation Runtime and P1 media owners |
| Automated verification and product acceptance | **PARTIAL.** Exact-source affected backend (`916 passed, 2 skipped`), Formal Web (`407/407`), profile tests, builds and static review have current credit; the physical candidate remains FAIL | Migrate capability-owned oracles with the first owning P3 package; run P3 package evidence; later repair/rerun the P1 seam and complete the clean cumulative Journey, feature-complete matrix, competitor-gap review and independent deep review | Root `TESTING.md`, D-086 risk transfer, current acceptance and exact clean source |
| Configuration, code and document cleanup | **PARTIAL.** Three cleanup audits and document Batch A are complete; `f24dd17d` makes ordinary production flag-off and an explicit named Live Voice profile flag-on, with profile/build/deploy evidence | Preserve those profile semantics while repairing P1; re-home test support; consolidate scheduled duplicates; retire obsolete entrypoints/legacy paths after replacement; execute document B/C after oracle extraction; exclude local artifacts | Follow the [code-duplication](reviews/CODE_DUPLICATION_AND_RETIREMENT_AUDIT_2026-08-17.md), [branch-retirement](reviews/BRANCH_CONTENT_RETIREMENT_AUDIT_2026-08-17.md) and [document-retirement](reviews/DOCUMENT_RETIREMENT_AUDIT_2026-08-17.md) gates |
| Production operations | **NOT STARTED as a complete boundary.** Privacy/preflight/observability foundations exist | Production auth/tenancy, public deployment, SLO/retention, security operations, compatibility matrix and release/rollback | Begins after feature-complete integration unless a newer decision changes scope |

## P3-G0 closure and deferred gaps

The six audit-derived repair groups are implemented and have affected automated
credit on `f24dd17d`. Under D-086 they close P3-G0 as the authoritative source
foundation for P3 expansion. The physical run stopped before their full
combined Task journey, so that missing observation is transferred to P3-9 and
cumulative product acceptance; it grants no physical or candidate credit:

1. **Executor terminalization:** bounded deadline/orphan settlement and tests
   are present; the clean physical Agent-return → application → result → terminal
   path was not reached.
2. **Admission truth:** backend and queued/running presentation regressions pass;
   the real create/admission step was not reached.
3. **Semantic routing:** bounded no-“把/将” adjustments and prefixed status forms
   pass affected positive/negative tests; no real running adjustment was issued.
4. **Task-truth isolation:** the end-to-end negative oracle and presentation
   guards pass automation; the combined dialogue/Task physical path was not run.
5. **Result-context capacity:** reserved legal TaskResult capacity passes its
   tests; no physical result query was reached.
6. **Recovery diagnostics:** stable visible correlation/reason fields are now
   present. The failed run identified activation and
   `AUDIO_CAPTURE_DURATION_EXCEEDED`, but available logs still do not distinguish
   provider speech-start/echo from the exact rotation race.

A P1/P2 defect was demonstrated twice on the clean candidate and is explicitly
deferred from the P3-1 sequencing Gate:

7. **P1/P2 post-TTS capture continuation — PARTIAL / DEFERRED.** The 30-second capture bound
   begins during overlapping TTS. After each of two real Agent responses, the
   route entered `AUDIO_CAPTURE_DURATION_EXCEEDED`, streaming recognition aborted
   and speech cancel/cleanup did not acknowledge cleanly. Manual `重新监听` admitted
   one more turn but the same failure recurred. Its phenomenon, confirmed
   mechanism, unresolved trigger attribution, repair direction and later
   acceptance are in the [deferred issue record](evidence/P1_P2_POST_TTS_CAPTURE_CONTINUATION_DEFERRED_20260819.md).

The explicit build profile and ordinary-production flag-off behaviour are
source/build/deploy verified. D-086 closes only the P3 expansion prerequisite;
it cannot upgrade the failed candidate or invalidate the historical
exact-source Alpha result.

## Current execution packet

- **Packet:** P3-1 — canonical multi-Task model, Store and migration.
- **Objective:** support multiple independently addressable Tasks in one
  authorized project/scope, freeze one canonical identity/state/relationship
  model, and migrate current schema-v3 truth without allowing a UI, Session or
  “current Task” hint to become mutation authority.
- **Capability/modules:** Task Control Core and Store are primary; only the
  narrow Executor status-resolution, structured command, Voice–Task Bridge and
  Integrated Web selection/query seams required to freeze the shared contract
  are included.
- **Risk:** Tier 3 under root `TESTING.md` because this package changes shared
  Task identity, canonical state, persistence and migration. Re-scope before
  implementation if it requires speech/media authority, a new Task owner or a
  broader command/execution policy.
- **Included:** multiple nonterminal Tasks; exact Task/Attempt/Command/Event/
  TaskResult and predecessor/successor relationships; canonical state and legal
  transition vocabulary; addressed list/status/events/result queries; durable
  cursor/pagination where required; restart-safe reconstruction; atomic,
  idempotent, fail-closed migration; exact `task_id` validation for structured
  mutation; removal of one-current-Task authority; migration of still-applicable
  historical oracles into current capability ownership.
- **Excluded:** the deferred P1/P2 post-TTS continuation repair; P3-2's complete
  update/provide-input/pause/resume/reprioritize and successor command semantics;
  P3-3 Executor capability/admission expansion; D1/D2 implementation; generalized
  Voice routing or Integrated Web productization; Production work, `develop`
  integration and remote updates.
- **First action:** record intended behaviour, owned source/test surfaces and
  exclusions; inspect the live schema-v3 Store/reducer/query/migration paths and
  every “current Task” selection use; then freeze queued/paused/state and
  relationship decisions before implementation.
- **Deliverables:** accepted owner/state/relationship decision; versioned Store
  migration; addressed multi-Task Core/query behaviour; positive, negative,
  boundary, state-transition, concurrency, recovery/idempotency and fault
  evidence required by root `TESTING.md`; complete-diff and independent Tier-3
  review; synchronized STATUS/evidence on the exact source.
- **Acceptance:** two or more Tasks remain independently addressable across
  foreground dialogue, refresh and restart; wrong/stale/foreign/ambiguous
  identity has zero Task/Attempt/Executor/file/presentation mutation; duplicate
  or conflicting command identity cannot allocate another Task/Attempt; Store
  reconstruction is exact or fails closed without partial promotion; a
  “current Task” convenience cannot redirect another Task's command.

## Dependency route to feature complete

1. ~~Audit all 15 capability/module rows against current source/tests~~ **DONE —
   see [module code-fact audit](reviews/MODULE_CODE_FACT_AUDIT_2026-08-17.md).**
   Remaining disputed facts (Executor clean re-verification, Interaction
   Intelligence ownership, Realtime Media composition owner) stay recorded as
   open conditions; a full suite was not required for the read-only audit.
2. `f24dd17d` implements the six product-truth repair groups and explicit Demo
   profile/default-off production semantics with affected automated/build
   evidence, but its clean P3-G0 physical run failed post-TTS capture
   continuation before the Task journey.
3. **P3-G0 authoritative foundation is scope-closed under D-086.** The failed
   controlled-candidate fact remains immutable; its P1/P2 continuation defect
   and combined physical Journey are transferred to later cumulative
   acceptance without granting physical credit.
4. Execute P3-1 canonical multi-Task model, Store and migration. Migrate each
   still-applicable historical oracle with its first owning package; perform
   code placement, duplicate consolidation and entrypoint/document retirement
   only after replacement without deleting live coverage.
5. Complete P1/P2 quality in parallel with the
   [complete P3 execution plan](roadmap/FULL_P3_EXECUTION_PLAN.md): execute the
   [latency optimization plan](roadmap/LATENCY_OPTIMIZATION_PLAN_2026-08-18.md)
   across Speech/Media/Runtime/Interaction latency and recovery on one side;
   activate owner-scoped packages for multi-Task, full controls, replay,
   capability-driven Executor and supported D1/D2 semantics on the other.
6. Generalize Provider/Executor/configuration/language/task policy and remove
   the exact itinerary, trusted Demo bypass, one-current-Task assumption and
   legacy product routes.
7. Run evidence-backed competitor gap analysis; implement only accepted gaps,
   then perform independent cross-module deep review.
8. Pass the feature-complete automated, integration and human acceptance on one
   exact clean source.
9. Only then audit the configured remotes and live `develop` ref, select and
   execute the accepted integration strategy, rerun affected cumulative
   verification and form the productized candidate.
10. Perform RC/Production security, operations, compatibility and release work
   under a separate acceptance boundary.

## Tracked cleanup and review work

- **Module code-fact audit — COMPLETE (2026-08-17):** see
  [module code-fact audit](reviews/MODULE_CODE_FACT_AUDIT_2026-08-17.md). It
  audited all 15 capability domains and the six known blockers on HEAD
  `6e7e82d3` (product code `ca9a9d9a`) and reconciled every mismatch in this
  STATUS. It is documentation, not product progress: it grants no new
  module-completion credit and does not repair defects. If code changes, repeat
  the affected rows.
- **Tests/code organization:** move every still-applicable old runner oracle to
  its capability owner before deletion; keep test fakes/fault helpers out of the
  apparent production tree.
- **Documents:** Batch A is complete. Batches B/C retain the 55-file retirement
  manifest until regression/contract extraction; the planned interim set is 20
  Live Voice documents. Audit-time line counts are historical metrics, not
  mutable status facts.
- **Hardcodes:** the explicit Demo profile and production-default flag-off are
  implemented and verified on `f24dd17d`; later P1/P2 and P3 packages must
  preserve them. Exact
  itinerary/checkpoint/bypass and other launcher scenario values retire after a
  clean journey during generalization. Protocol constants and accepted safety
  bounds stay; the capture-duration contract must be decided before changing its
  value.
- **Duplicates:** combine registry generation-index traversal only if its owner
  is touched by the defect repair. Formal validators/snapshots wait for the code
  organization batch; authority handlers remain explicit unless semantics match.
- **Latency:** the code-fact diagnosis and implementation approach are now
  defined in the [latency optimization plan](roadmap/LATENCY_OPTIMIZATION_PLAN_2026-08-18.md).
  Establish its current physical baseline first, then execute low-risk pipeline
  work, truthful acknowledgement and formal sentence-level Agent→TTS overlap.
  This remains queued P1/P2 quality work, not completion credit or part of the
  current product-truth repair packet.
- **Reviews:** reproduce findings against current source; fix confirmed issues
  only and rerun affected checks. Feature closure requires one independent
  cross-module review after competitor-gap decisions.
- **Local artifacts:** coverage, caches, `dist`, `node_modules`, logs and private
  runtime databases/audio remain ignored and excluded from final integration.

## Verification and runtime truth

- Historical automated counts and review details remain in their exact-source
  records. They are regression evidence, not current candidate credit.
- Exact product source `f24dd17d` has current affected backend/frontend/profile/
  build/static and clean-deployment credit recorded in the
  [P3-G0 evidence](evidence/P3_G0_PRODUCT_READINESS_FAIL_20260819_f24dd17d.md),
  but its repeated physical continuation failure prevents immutable PASS.
- D-086 closes P3-G0 only as the expansion foundation and activates P3-1. It
  explicitly transfers, rather than passes, the missing physical Journey and
  [P1/P2 continuation defect](evidence/P1_P2_POST_TTS_CAPTURE_CONTINUATION_DEFERRED_20260819.md).
- A documentation-only commit never upgrades product readiness.
- Runtime credentials, Provider settings, registered projects, device/browser
  state, Task databases and network state are machine-private. At the next
  isolated runtime start, re-read actual Task/lease state before settling work.

## Safety and exclusions

- Use only a registered disposable no-remote project and isolated
  `JIUWENSWARM_DATA_DIR` for Executor/Demo work; never target this source tree or
  an uncontrolled user project.
- Partial/uncommitted speech, wrong-scope/stale events and failed confirmation
  must produce zero forbidden Agent/Tool/Task/audio/history mutation.
- The trusted Demo policy and exact itinerary are test/Demo mechanisms, not
  production confirmation or generalized capability.
- Credentials, billing/account changes, private runtime data and remote-ref
  updates are outside source acceptance and require their own authority.
- Numbered plans, historical reviews/evidence and old test names may explain a
  past result; they never define current priority or completion.
