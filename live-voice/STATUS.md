# Live Voice current project status

> Updated: 2026-08-20. This is the only mutable source for current product
> judgement, capability completion, remaining scope, dependency order and the
> next execution packet. Read live branch/HEAD/upstream state from Git; do not
> copy transient ahead/behind, dirty-tree or “uncommitted” claims into this file.

## Project judgement

- **Last product-composed baseline assessed:**
  `f24dd17d336c8266954f2d7299ca13bd0314d424`. Accepted P3-1 Task source and the
  scoped additive P3-8A pure assets are newer source packages, but neither
  changes the immutable physical product result or receives unrun composition
  credit.
- **Current product status:** **P3 EXPANSION ACTIVE — P3-G0 passed its scoped
  authoritative-foundation Gate under D-086; controlled product readiness
  remains unpassed.** P3-2, P3-3 and P3-5A now have locally integrated source,
  affected automation and independent review credit. Their bounded physical
  Wave-2 run proved two-project Direct concurrency but did not reach the
  required file-Tool/A2/control/cleanup journey, so that Gate remains PARTIAL.
  The failed post-TTS continuation also remains deferred to P1/P2 completion;
  neither gap receives a fabricated physical PASS.
- **Accepted historical baseline:** `PASS — INTEGRATED WEB ALPHA` remains bound
  only to `d33b520e0d21ae0829d30814d77a01cc18256f09`. Later source and broader
  functionality do not inherit that result.
- **Latest physical product result:** `FAIL — P3-G0 CONTROLLED CANDIDATE NOT
  ACCEPTED` on exact clean product source `f24dd17d336c8266954f2d7299ca13bd0314d424`.
  See the sanitized [P3-G0 attempt](evidence/P3_G0_PRODUCT_READINESS_FAIL_20260819_f24dd17d.md).
- **P3-G0 status:** **PASS — AUTHORITATIVE P3 FOUNDATION; CONTROLLED
  PRODUCT-READINESS REMAINS FAIL.** [D-086](decisions/DECISIONS.md) accepts the
  sequencing risk and removes the failed P1/P2 hands-free condition as a P3-1
  Gate without changing the immutable candidate result.
- **Current highest priority:** close the D-088 Wave-2 physical evidence gap
  without weakening its source authority: diagnose why the private production
  run produced no successful file write/edit pair, A2 or clean Store settlement,
  then make a new explicit execution decision before any further private run.
  The accepted packet's single fresh-root retry has been consumed. The deferred
  P1/P2 issue is recorded in the
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

The detailed complete-P3 workload, P3alpha inheritance, package acceptance,
critical path and parallel collision rules are defined in the
[complete P3 execution plan](roadmap/FULL_P3_EXECUTION_PLAN.md). That
preparatory contract is not the active queue. By default this STATUS activates
one coherent packet; a D-060/D-062 packet may instead activate one explicitly
bounded multi-package batch whose child packages have separate owners, files,
risks, dependencies, acceptance and integration order.

| Capability / module | Status and implemented fact | Remaining for feature complete | Dependency / acceptance |
|---|---|---|---|
| Audio Device & browser I/O | **PARTIAL; deferred from the P3-1 Gate.** Browser capture/playout, lifecycle fencing and dedicated media wiring exist, but `f24dd17d` twice entered `AUDIO_CAPTURE_DURATION_EXCEEDED` after TTS instead of continuing automatically | Execute the [recorded repair direction](evidence/P1_P2_POST_TTS_CAPTURE_CONTINUATION_DEFERRED_20260819.md); physically verify overlap/idle rotation; device/permission recovery; AEC/NS/AGC and double-talk; measured first-frame/loss/stop targets | P1/P2 completion before controlled-candidate/feature-complete acceptance; not a P3-1 dependency |
| Speech Recognition | **PARTIAL.** Two real microphone finals reached the Agent, but each post-TTS failure also produced streaming-route abort, cleanup timeout and unacknowledged cancel | Exact capture/provider-speech-start attribution, robust fallback/cancel, Provider-neutral configuration, fixed accuracy/latency corpus and broader device/network validation | Audio I/O, media route and benchmark owner |
| Speech Synthesis | **PARTIAL.** Streaming/Batch TTS, browser playout, response ownership and ACK paths exist | Provider-neutral configuration, first-audio/underrun/pronunciation targets and complete stale/cancel recovery | Conversation Runtime ownership and Audio I/O stop confirmation |
| Realtime Media | **PARTIAL; deferred from the P3-1 Gate.** Dedicated transport, media registration and presentation ACK worked, but repeated post-TTS capture rotation did not preserve a usable media loop | Repair the exact rotation/cancel seam; backpressure/load targets; drop/reorder/corruption/reconnect matrix; stable diagnostics across repeated recovery | Audio I/O plus Conversation Runtime; cumulative real network/device verification |
| Conversation Runtime | **PARTIAL.** committed-input fencing, generation ownership, ACK/history projection, Exit fencing and playout-time barge-in exist; manual retry admitted a second turn | Automatic continuation without recurrent recovery failure; interruption during Agent generation, complete `ask_user` voice loop and cross-load arbitration | Media, Interaction Intelligence, Agent Bridge and presentation regressions |
| Interaction Intelligence | **PARTIAL.** VAD/EOT and bounded dialogue/background routing exist for the controlled journey | General natural-language routing, false endpoint/interruption and echo/double-talk evaluation, language/config generalization; Native model-level duplex remains optional | Streaming Speech plus Runtime; measured golden corpus |
| Agent Bridge and dialogue truth | **PARTIAL.** Real Agent dialogue/tools and bounded response/progress integration exist | Non-blocking progress provenance, strict Task-truth isolation, bounded result-context reservation and unconstrained reread prevention | Runtime, Task/Event truth and affected text-path regressions |
| Task Control Core and Store | **PARTIAL overall; P3-1, P3-2 and P3-5A source/automation/review PASS.** Schema v5 retains the P3-1 multi-Task authority, implements the closed P3-2 command/disposition/update/successor matrix and adds retained result/event plus pure unread and explicit class-isolated ACK. Durable negative decisions, failpoints, restart verification and two-Store races are closed; unsupported controls remain truthful rather than inventing Executor primitives | Close the batch's physical Direct/Tool/terminal evidence, then implement P3-5B presentation filtering/invocation, P3-6 product targeting and the later complete one-product-Task model | Executor capability/admission facts, Voice–Task Bridge and restart/concurrency matrix; exact Wave-2 facts in the [evidence](evidence/P3_WAVE2_COMMAND_ADMISSION_REPLAY_EVIDENCE_20260819.md) and [review](reviews/P3_WAVE2_COMMAND_ADMISSION_REPLAY_REVIEW_2026-08-19.md) |
| Executor & Durability | **PARTIAL overall; P3-3 source/automation/review PASS; physical Gate PARTIAL.** Immutable Direct capability/profile selection, priority/FIFO admission, project-busy/capacity deferral, absolute deadline, three-fence separation, queued reprioritization and bounded reconciliation are integrated. The private run proved overlapping A1/B1 Direct-running intervals on two distinct projects and persisted the selected Direct binding, but produced no validated file-Tool pair or A2/control/clean-settlement evidence | Diagnose the missing real Tool emission and unresolved `EXECUTOR_STATUS_SELECTION_PROOF_REQUIRED` settlement before another bounded run; later add supported D1 checkpoint and D2 reconciliation semantics in P3-4 | Tier-3 Direct Adapter/Agent/Tool evidence plus Core/Store admission integration; D1/D2 remain explicitly excluded |
| Voice–Task Bridge | **PARTIAL.** Natural-language create/status/adjust/result paths and durable adjustment delivery exist | General routing, explicit multi-Task targeting, full Task operations, text/voice parity, clarification and zero false truth | Task Core and Executor truth; precision/recall plus zero-side-effect tests |
| Integrated Web product experience | **PARTIAL.** The explicit profile, authenticated route, P2/P3 composition, real foreground Agent text/TTS and manual retry worked; automatic listening failed after both responses. A broader P3-1 diagnostic also reproduced the unchanged mounted Exit/immediate-re-enable presentation-ACK timing failure at 406/407; both remain outside the accepted Core/Store package | Complete P3 controls/projections while preserving profile semantics; later close capture/Exit recovery, truthful queued/running/terminal UX, device/privacy/recovery UX and the cumulative human journey; retire legacy hooks/flags | P3-2 through P3-9 plus deferred P1/P2 completion |
| Observability, benchmark and latency | **PARTIAL overall; additive P3-8A assets PASS.** Trace/correlation foundations now include a bounded content-free SLI calculator, complete declaration-only telemetry privacy profile and source-bound canonical OTel backend codec that reuses the current observability owner's calendar and private-carrier validation. The codec is not product-composed and owns no exporter/backend lifecycle | Compose the codec behind the existing adapter/exporter in the later owning package; add validated backend configuration and exact Task/Attempt/Command/activation/generation/ACK/Executor diagnostics; then execute the [latency optimization plan](roadmap/LATENCY_OPTIMIZATION_PLAN_2026-08-18.md) with a fresh physical baseline, stable EOT/Agent/TTS/first-audible facts, authoritative ACK, formal sentence-level Agent→TTS overlap and fixed-corpus p50/p95 proof | Exact scoped evidence in the [P3-8A review](reviews/P3_8A_OBSERVABILITY_ASSETS_REVIEW_2026-08-19.md); P3-8B composition/retirement after P3-7; fixed corpus/environment and Conversation Runtime/P1 media owners |
| Automated verification and product acceptance | **PARTIAL.** Exact-source G0 affected backend (`916 passed, 2 skipped`), Formal Web (`407/407`), profile tests, builds and static review retain their source-bound credit. P3-1 and Wave-2 source packages have affected automation/static/build and independent Tier-3 review credit; the Wave-2 physical run proves only selected two-project Direct concurrency. The controlled product candidate remains FAIL | Close the Wave-2 file-Tool/A2/control/cleanup evidence, then repair/rerun the P1/P2 seam and complete the clean cumulative Journey, feature-complete matrix, competitor-gap review and independent deep review | Root `TESTING.md`, D-086 risk transfer, the [Wave-2 evidence](evidence/P3_WAVE2_COMMAND_ADMISSION_REPLAY_EVIDENCE_20260819.md), current acceptance and exact clean source |
| Configuration, code and document cleanup | **PARTIAL.** Three cleanup audits and document Batch A are complete; `f24dd17d` makes ordinary production flag-off and an explicit named Live Voice profile flag-on, with profile/build/deploy evidence | Preserve those profile semantics while repairing P1; re-home test support; consolidate scheduled duplicates; retire obsolete entrypoints/legacy paths after replacement; execute document B/C after oracle extraction; exclude local artifacts | Follow the [code-duplication](reviews/CODE_DUPLICATION_AND_RETIREMENT_AUDIT_2026-08-17.md), [branch-retirement](reviews/BRANCH_CONTENT_RETIREMENT_AUDIT_2026-08-17.md) and [document-retirement](reviews/DOCUMENT_RETIREMENT_AUDIT_2026-08-17.md) gates |
| Production operations | **NOT STARTED as a complete boundary.** Privacy/preflight/observability foundations exist | Production auth/tenancy, public deployment, SLO/retention, security operations, compatibility matrix and release/rollback | Begins after feature-complete integration unless a newer decision changes scope |

## P3-G0 scoped PASS and deferred gaps

The six audit-derived repair groups are implemented and have affected automated
credit on `f24dd17d`. Under D-086 they pass P3-G0 only as the authoritative
source foundation for P3 expansion. The physical run stopped before their full
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
source/build/deploy verified. D-086 passes only the P3 expansion prerequisite;
it cannot upgrade the failed candidate or invalidate the historical
exact-source Alpha result.

## Current execution packet

- **Packet:** D-088 bounded Wave 2 — P3-2 complete commands/revisions, P3-3
  capability-driven admission and P3-5A result/event/unread persistence.
- **Authority:** activation baseline `b1a6290b6ccbe5948c5700a8c6e103798160d7f1`,
  accepted P3-1 ancestor `d40e0ee3`, [D-087](decisions/DECISIONS.md),
  [D-088](decisions/DECISIONS.md), the
  [P3-2/P3-5A map](reviews/P3_2_P3_5A_ACTIVATION_PREPARATION_2026-08-18.md)
  and [P3-3 map](reviews/P3_3_CAPABILITY_ADMISSION_ACTIVATION_PREPARATION_2026-08-18.md).
  Minimum-intervention mode remains active for local closure; every remote-ref
  update remains separately excluded until exact user approval.
- **Source state:** P3-2, P3-3, P3-5A, their Task6 composition/control-history
  seams and the default-off content-free evidence observer are locally
  implemented and integrated. Schema v5 contains only the frozen P3-3 Attempt
  facts and P3-5A consumer state beyond the prior schema; no P3-4 D1/D2 DDL was
  introduced. Child and cumulative Tier-3 reviews report no remaining
  Critical/Important/Minor finding.
- **Automated state:** combined command/admission/consumption/composition/
  observer automation, shared Python/JavaScript contract parity, static checks
  and the frontend production build pass on the integrated source. Exact
  commands and counts live in the scoped [review](reviews/P3_WAVE2_COMMAND_ADMISSION_REPLAY_REVIEW_2026-08-19.md).
- **Physical state:** the bounded private Windows production run proved two
  distinct selected A1/B1 projects concurrently Direct-running. It produced no
  validated file write/edit observation pair, no A2, no adjustment/cancel and
  no clean terminal settlement. Canonical Tasks remain running while the Direct
  journals are interrupted and reconciliation is pending with
  `EXECUTOR_STATUS_SELECTION_PROOF_REQUIRED`. The physical Gate is therefore
  **PARTIAL**; no positive evidence JSON exists.
- **Private cleanup:** both failed roots remain ACL-private and
  `CLEANUP_PENDING`; they are not reused or recursively deleted while complete
  Agent/worker/Store cleanup is unproved. Private configuration values and raw
  Agent/Tool content were not inspected.
- **Next action:** finish the local documentation/final-regression Gate and form
  the exact normal-push packet. A further private Provider run is not authorized
  by this packet: first diagnose the file-Tool/selection-proof settlement gap,
  then obtain a new explicit execution decision because the single fresh-root
  retry has been consumed.
- **Excluded/non-claims:** deferred P1/P2 capture/Exit repair; positive
  provide-input/pause/resume or unsupported running controls without real
  primitives; P3-4 D1/D2; P3-5B Runtime/Web delivery; P3-6 targeting; P3-7 UI;
  P3-8B retirement; complete P3, feature complete, controlled-candidate PASS,
  Production, `develop` integration and every remote update.
- **Evidence:** the sanitized facts, zero-effect matrix, physical dispositions
  and explicit unknowns are recorded in the
  [Wave-2 evidence](evidence/P3_WAVE2_COMMAND_ADMISSION_REPLAY_EVIDENCE_20260819.md).

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
3. **P3-G0 authoritative-foundation Gate is PASS under D-086.** The failed
   controlled-candidate fact remains immutable; its P1/P2 continuation defect
   and combined physical Journey are transferred to later cumulative
   acceptance without granting physical credit.
4. ~~Execute P3-1 canonical multi-Task model, Store and migration~~ **DONE —
   current-source affected evidence and independent Tier-3 review pass with no
   remaining package P1/P2.**
5. ~~Implement and integrate P3-2 commands/successors, P3-3 capability admission
   and P3-5A retained replay/unread ACK~~ **SOURCE/AUTOMATION/REVIEW DONE; PHYSICAL
   GATE PARTIAL.** The bounded run proved selected two-project Direct concurrency
   but not the required file-Tool pair, A2/control journey or clean settlement.
   Diagnose that exact gap before a newly authorized run; then activate P3-4,
   P3-5B and P3-6 in dependency order. Continue migrating each still-applicable
   historical oracle with its first owning package; perform code placement,
   duplicate consolidation and entrypoint/document retirement only after
   replacement without deleting live coverage. Complete P1/P2 quality in
   parallel with the
   [complete P3 execution plan](roadmap/FULL_P3_EXECUTION_PLAN.md): execute the
   [latency optimization plan](roadmap/LATENCY_OPTIMIZATION_PLAN_2026-08-18.md)
   across Speech/Media/Runtime/Interaction latency and recovery on one side;
   activate owner-scoped packages for multi-Task, full controls, replay,
   capability-driven Executor and supported D1/D2 semantics on the other.
6. Generalize Provider/Executor/configuration/language/task policy and remove
   the exact itinerary, trusted Demo bypass, remaining product/UI current-Task
   assumptions and legacy product routes.
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
- **P3 implementation/reuse audit — COMPLETE (2026-08-18, routing rebased
  2026-08-19):** see the
  [P3 implementation coverage and historical reuse audit](reviews/P3_IMPLEMENTATION_COVERAGE_AND_HISTORICAL_REUSE_AUDIT_2026-08-18.md).
  Its estimates remain a committed pre-G0 nine-package coverage snapshot; its
  current routing records the P3-G0 scoped PASS, accepted P3-1 package and
  active P3-2 package. It also
  records the wave-to-asset migration overlay and per-commit extraction gates
  for the old 3A/3B/reader/S8.5 lines. Its companion
  [source-asset manifest](reviews/P3_HISTORICAL_SOURCE_ASSET_EXTRACTION_MANIFEST_2026-08-18.md)
  centralizes 57 file/symbol/test/dependency-level assets so execution workers
  validate a bounded activation-time mapping instead of repeating branch
  forensics. It also records the verified legacy-checkout refs for the 24 objects
  absent from this repository and the D2-reader branch-name trap. No standalone
  G0 delta or aggregate re-score is required: at P3-1 and every later affected
  package activation, record the current HEAD/relevant Git range and validate
  only the selected rows. The inventory grants no package or acceptance credit;
  never integrate an old branch merely because its content is inventoried.
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
- **P3-8A additive assets — PASS (2026-08-19):** the
  [P3-8A observability assets review](reviews/P3_8A_OBSERVABILITY_ASSETS_REVIEW_2026-08-19.md)
  records the current-source pure SLI/privacy/OTel codec scope, corrected
  `ca3d7780` findings, exact affected evidence and independent Tier-3 PASS. The
  assets are uncomposed and do not make P3-8, product readiness or Production
  operations complete; P3-2 remains the active packet.
- **Local artifacts:** coverage, caches, `dist`, `node_modules`, logs and private
  runtime databases/audio remain ignored and excluded from final integration.

## Verification and runtime truth

- `P3-2/P3-3/P3-5A` Wave-2 source, schema, composition and default-off evidence
  observer have affected automation/static/build and independent Tier-3 review
  credit recorded in the
  [implementation review](reviews/P3_WAVE2_COMMAND_ADMISSION_REPLAY_REVIEW_2026-08-19.md).
  The associated [physical evidence](evidence/P3_WAVE2_COMMAND_ADMISSION_REPLAY_EVIDENCE_20260819.md)
  is intentionally PARTIAL: A1/B1 selected Direct overlap is proved, while
  successful file-Tool pairing, A2/control and clean settlement are absent. No
  positive evidence JSON is committed.
- `P3-8A` current-source focused/affected automation reports **207 passed**;
  Python static/format/compile and Git whitespace checks pass, and an independent
  Tier-3 cold review found no P1/P2. This grants only the additive pure-asset
  credit recorded in the
  [P3-8A review](reviews/P3_8A_OBSERVABILITY_ASSETS_REVIEW_2026-08-19.md): no
  backend/exporter was called and no product build, deployment or physical
  acceptance is implied.
- `P3-1` current-source affected automated/static/build evidence and independent
  Tier-3 review pass with no remaining package P1/P2, as recorded in the
  [P3-1 implementation review](reviews/P3_1_CANONICAL_MULTI_TASK_IMPLEMENTATION_REVIEW_2026-08-19.md).
  Its extra full-Web diagnostic reproduced one unchanged P1/P2 Exit/re-enable
  timing failure at 406/407; that broader Runtime/Web defect is disclosed and
  excluded, not counted as P3-1 credit. The review is Core/Store source
  evidence, not a physical microphone/TTS or `P3-G0` acceptance rerun.
- Historical automated counts and review details remain in their exact-source
  records. They are regression evidence, not current candidate credit.
- Exact product source `f24dd17d` has current affected backend/frontend/profile/
  build/static and clean-deployment credit recorded in the
  [P3-G0 evidence](evidence/P3_G0_PRODUCT_READINESS_FAIL_20260819_f24dd17d.md),
  but its repeated physical continuation failure prevents immutable PASS.
- D-086 records P3-G0 PASS only for the expansion-foundation Gate and originally
  activated P3-1; P3-1 and the Wave-2 source packages now pass their scoped
  source evidence. It explicitly transfers, rather than passes, the missing
  physical Journey and
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
