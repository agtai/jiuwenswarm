# Live Voice current project status

> Updated: 2026-08-18. This is the only mutable source for current product
> judgement, capability completion, remaining scope, dependency order and the
> next execution packet. Read live branch/HEAD/upstream state from Git; do not
> copy transient ahead/behind, dirty-tree or “uncommitted” claims into this file.

## Project judgement

- **Last product-code baseline assessed:**
  `ca9a9d9a3be5f76c4feee980030a1b3ce065b9ab`. Documentation-only commits after
  that source do not change its product credit.
- **Current product status:** **PARTIAL — controlled Demo capable, not a clean
  product-readiness candidate and not feature-complete.** Speech, realtime,
  Task, authority, Executor and Integrated Web foundations exist, but the
  expanded hands-free/background-Task journey still has authoritative truth
  defects.
- **Accepted historical baseline:** `PASS — INTEGRATED WEB ALPHA` remains bound
  only to `d33b520e0d21ae0829d30814d77a01cc18256f09`. Later source and broader
  functionality do not inherit that result.
- **Latest physical product result:** `COMPLETED — DEFECTS RECORDED`, not PASS.
  See the sanitized [product run](evidence/POST_ALPHA_DEMO_20260817_95b26308_WORKTREE.md).
- **Current highest priority:** the fresh 15-domain code-fact audit is now
  complete (see
  [module code-fact audit](reviews/MODULE_CODE_FACT_AUDIT_2026-08-17.md)); next
  close the confirmed product-truth defects (result-context capacity, semantic
  routing, recovery diagnostics) and re-verify Executor terminalization and
  admission truth on one clean immutable candidate.
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
| Audio Device & browser I/O | **PARTIAL.** Browser capture/playout, lifecycle fencing and dedicated media wiring exist | Default formal route; device/permission recovery; AEC/NS/AGC and double-talk behaviour; measured first-frame/loss/stop targets | P2 media/runtime integration plus declared browser/device matrix |
| Speech Recognition | **PARTIAL.** Controlled OpenAI Streaming/Batch STT and browser fallback work | Provider-neutral configuration, fixed accuracy/latency corpus, robust fallback/cancel and broader device/network validation | Audio I/O, media route and benchmark owner |
| Speech Synthesis | **PARTIAL.** Streaming/Batch TTS, browser playout, response ownership and ACK paths exist | Provider-neutral configuration, first-audio/underrun/pronunciation targets and complete stale/cancel recovery | Conversation Runtime ownership and Audio I/O stop confirmation |
| Realtime Media | **PARTIAL.** Dedicated transport, media registration, receipts/ACK and bounded close behaviour exist | Backpressure/load targets; drop/reorder/corruption/reconnect matrix; stable diagnostics across repeated recovery | Audio I/O plus Conversation Runtime; real network/device verification |
| Conversation Runtime | **PARTIAL.** committed-input fencing, generation ownership, ACK/history projection, Exit fencing and playout-time barge-in exist | Interruption during Agent generation, complete `ask_user` voice loop, cross-load arbitration and recovery without repeated ambiguous state | Media, Interaction Intelligence, Agent Bridge and presentation regressions |
| Interaction Intelligence | **PARTIAL.** VAD/EOT and bounded dialogue/background routing exist for the controlled journey | General natural-language routing, false endpoint/interruption and echo/double-talk evaluation, language/config generalization; Native model-level duplex remains optional | Streaming Speech plus Runtime; measured golden corpus |
| Agent Bridge and dialogue truth | **PARTIAL.** Real Agent dialogue/tools and bounded response/progress integration exist | Non-blocking progress provenance, strict Task-truth isolation, bounded result-context reservation and unconstrained reread prevention | Runtime, Task/Event truth and affected text-path regressions |
| Task Control Core and Store | **PARTIAL.** Stable Task/Attempt/Event/Command IDs, SQLite schema v3, idempotency, outbox, results, adjustments and one-current-Task recovery exist | Multiple addressed Tasks, target disambiguation, `update/provide_input/pause/resume/reprioritize`, successor revision, replay/unread and one canonical Task model | Executor status resolution, Voice–Task Bridge and restart/concurrency matrix |
| Executor & Durability | **PARTIAL.** Direct isolated Code Executor, lease/journal, terminalization and recovery foundations exist and are statically closed on the audited source | Clean physical re-verification of Agent-return → validation → application → result → terminalization; bounded timeout/orphan handling; capability selection; supported D1 checkpoint and D2 reconciliation semantics | Highest-priority Tier-3 clean re-verification; D1/D2/capability remain feature-complete scope |
| Voice–Task Bridge | **PARTIAL.** Natural-language create/status/adjust/result paths and durable adjustment delivery exist | General routing, explicit multi-Task targeting, full Task operations, text/voice parity, clarification and zero false truth | Task Core and Executor truth; precision/recall plus zero-side-effect tests |
| Integrated Web product experience | **PARTIAL.** One-click hands-free shell, formal route, progress, TTS and current Task presentation exist | Formal route becomes the only supported default; truthful queued/running/terminal UX; device/privacy/recovery UX; legacy hook/flags removed | All P1/P2/P3 owners plus complete human journey |
| Observability, benchmark and latency | **PARTIAL.** Trace/correlation and historical verification foundations exist. The default-off minimal latency probe records the Browser timeline plus Gateway/Agent same-clock drill-downs and passed its final independent Tier-3 code review; real warm/cold runs have not yet granted baseline credit | Execute the [latency optimization plan](roadmap/LATENCY_OPTIMIZATION_PLAN_2026-08-18.md): accepted fresh physical baseline; low-risk pipeline waits; authoritative ACK; formal sentence-level Agent→TTS overlap; fixed-corpus p50/p95 and no-regression proof | Fixed clean-source corpus/environment measurement, then Conversation Runtime and P1 media owners |
| Automated verification and product acceptance | **PARTIAL.** Broad exact-source backend/frontend/build/review credit exists | Affected defect reruns, capability-owned test migration, cumulative feature-complete matrix, clean real Journey, competitor-gap review and independent deep review | Root `TESTING.md`, current acceptance and exact clean source |
| Configuration, code and document cleanup | **PARTIAL.** Three cleanup audits and document Batch A are complete | Explicit Demo profile; remove `.env.production` default-on dependency; re-home test support; consolidate scheduled duplicates; retire obsolete entrypoints/legacy paths after replacement; execute document B/C after oracle extraction; exclude local artifacts | Follow the [code-duplication](reviews/CODE_DUPLICATION_AND_RETIREMENT_AUDIT_2026-08-17.md), [branch-retirement](reviews/BRANCH_CONTENT_RETIREMENT_AUDIT_2026-08-17.md) and [document-retirement](reviews/DOCUMENT_RETIREMENT_AUDIT_2026-08-17.md) gates |
| Production operations | **NOT STARTED as a complete boundary.** Privacy/preflight/observability foundations exist | Production auth/tenancy, public deployment, SLO/retention, security operations, compatibility matrix and release/rollback | Begins after feature-complete integration unless a newer decision changes scope |

## Current blocking defects

Re-verified against the audited source (see
[module code-fact audit](reviews/MODULE_CODE_FACT_AUDIT_2026-08-17.md) §7).

1. **Executor terminalization — partially closed, clean re-verification open.**
   The Agent-return → validation → application → result → terminalization path is
   statically closed and unit-tested on this source; the Post-Alpha dirty-source
   observation of a missing terminal event / lease renewal must be re-checked on
   one clean immutable candidate before it is declared fixed.
2. **Admission truth — backend correct, display wording open.** An accepted Task
   blocked by `EXECUTOR_PROJECT_BUSY` is not authoritatively running at the
   backend; the residual risk is user-visible “已开始处理”/running wording, not
   authoritative state.
3. **Semantic routing:** valid Chinese adjustments without “把/将” and prefixed
   status questions can route incorrectly.
4. **Task-truth isolation — downgraded to Low residual.** Five-layer isolation is
   source-backed; the remaining gap is an end-to-end negative oracle proving a
   DIALOGUE `chat.final` cannot assert applied/completed/result, plus
   presentation wording.
5. **Result-context capacity:** a legal TaskResult can be rejected when dialogue
   context already occupies the selected capacity.
6. **Recovery diagnostics:** repeated “正在恢复” lacks stable correlation needed
   to identify the failed activation/generation/ACK/TTS seam.

Items 3, 5 and 6 remain blockers for a new controlled candidate; items 1, 2 and
4 are re-scoped per the audit and still carry their listed follow-up. These do
not invalidate the historical exact-source Alpha result.

## Current execution packet

- **Objective:** repair the authoritative product-truth path and produce one
  clean controlled product-readiness candidate.
- **Capability/modules:** Executor & Durability, Task Control Core,
  Voice–Task Bridge, Agent Bridge, Conversation Runtime and presentation/TTS.
- **Preparation:** the read-only 15-domain audit and its recommended repair
  order are complete (see the
  [module code-fact audit](reviews/MODULE_CODE_FACT_AUDIT_2026-08-17.md) §17);
  no product repair receives credit until its owner-scoped implementation packet
  and applicable tests are executed.
- **Risk:** the audit is Tier 0 read-only work; confirmed implementation remains
  Tier 3 authority, mutation, durability and cross-module state.
- **Included:** the six re-scoped defects above; bounded D0 timeout/orphan
  settlement and diagnostics needed for truthful candidate state;
  accepted/queued/running display wording; one explicit named Demo profile
  replacing production default-on flags while flag-off preserves the text path;
  affected positive/negative/flag-off/recovery/concurrency and
  zero-forbidden-effect tests. (The fresh audit itself is complete and is no
  longer a packet work item.)
- **Excluded:** multi-Task/full-P3 expansion, broad latency optimization, broad
  duplicate abstraction, D1 checkpoint/D2 reconciliation, competitor feature
  additions, Production work and `develop` integration.
- **First action and order:** instantiate B6 recovery correlation as the first
  owner-scoped Tier-3 repair batch, including its recovery-seam test; then B5
  legal result-context capacity, B3 semantic routing, B4/B2 negative-oracle and
  display truth, and finally the B1/B2 clean physical re-verification. Each
  batch names exact source/tests, exclusions and zero-forbidden-effect evidence
  before implementation.
- **Deliverables:** affected product/test changes, per-batch scoped and
  independent review evidence, the explicit Demo profile, and one exact clean
  candidate with truthful adjustment/result/terminal presentation. A repair
  batch may close only its affected findings; it cannot grant full-P3 credit.
- **Acceptance:** affected backend and Integrated Web checks, cold scoped review,
  independent Tier-3 review, cumulative diff review and one clean immutable
  [product-readiness acceptance](validation/PRODUCT_READINESS_ACCEPTANCE.md) run
  using the [human journey](demo/PRODUCT_READINESS_SHOWCASE.md).
- **Contract/evidence inputs:** the
  [D-085 code-fact audit](reviews/MODULE_CODE_FACT_AUDIT_2026-08-17.md), current
  source/tests, applicable frozen boundaries from
  [D119](D119_RUNNING_TASK_ADJUSTMENT_AND_TERMINAL_NOTIFICATION_REVIEW_2026-08-16.md),
  and the sanitized [Post-Alpha defect run](evidence/POST_ALPHA_DEMO_20260817_95b26308_WORKTREE.md).
  Historical stage packets do not define this work.

## Dependency route to feature complete

1. ~~Audit all 15 capability/module rows against current source/tests~~ **DONE —
   see [module code-fact audit](reviews/MODULE_CODE_FACT_AUDIT_2026-08-17.md).**
   Remaining disputed facts (Executor clean re-verification, Interaction
   Intelligence ownership, Realtime Media composition owner) stay recorded as
   open conditions; a full suite was not required for the read-only audit.
2. Close the confirmed product-truth defects and replace implicit Demo
   production flags before building the next candidate.
3. Pass one clean controlled candidate; findings return only to affected owners.
4. Migrate applicable old test oracles, then perform code placement, duplicate
   consolidation and entrypoint/document retirement without deleting live
   coverage.
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
- **Hardcodes:** explicit Demo profile is part of the current packet. Exact
  itinerary/checkpoint/bypass and other launcher scenario values retire after a
  clean journey during generalization. Protocol constants and safety bounds stay.
- **Duplicates:** combine registry generation-index traversal only if its owner
  is touched by the defect repair. Formal validators/snapshots wait for the code
  organization batch; authority handlers remain explicit unless semantics match.
- **Latency:** the code-fact diagnosis and implementation approach are now
  defined in the [latency optimization plan](roadmap/LATENCY_OPTIMIZATION_PLAN_2026-08-18.md).
  The default-off minimal probe candidate is implemented and its final
  independent Tier-3 code review is closed with no open finding. Establish the
  clean-source physical baseline before low-risk pipeline work, truthful acknowledgement and formal
  sentence-level Agent→TTS overlap. This remains P1/P2 quality work, not
  baseline or completion credit and not part of the current product-truth
  repair packet.
- **Reviews:** reproduce findings against current source; fix confirmed issues
  only and rerun affected checks. Feature closure requires one independent
  cross-module review after competitor-gap decisions.
- **Local artifacts:** coverage, caches, `dist`, `node_modules`, logs and private
  runtime databases/audio remain ignored and excluded from final integration.

## Verification and runtime truth

- Historical automated counts and review details remain in their exact-source
  records. They are regression evidence, not current candidate credit.
- The last assessed product-code baseline has useful backend/frontend/build
  credit, but its physical run ended with defects and no immutable PASS.
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
