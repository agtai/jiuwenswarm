# Live Voice current project status

> Updated: 2026-08-21. This is the only mutable source for current product
> judgement, capability completion, remaining scope, dependency order and the
> next execution packet. Read live branch/HEAD/upstream state from Git; do not
> copy transient ahead/behind, dirty-tree or “uncommitted” claims into this file.

## Project judgement

- **Last controlled-product baseline assessed:**
  `f24dd17d336c8266954f2d7299ca13bd0314d424`. Accepted P3-1 Task source and the
  scoped Wave-2, Wave-3 and P3-8A packages do not change its immutable
  controlled-product result.
- **Latest scoped Wave-2 physical source:**
  `3aa61f0193ac25e3da277f2dd632870355baf95a`. This source passes the bounded
  P3-2/P3-3/P3-5A file-Tool/A2/control/cleanup Gate only; it is not a complete
  microphone/TTS controlled-product journey.
- **Latest scoped Wave-3 source and private regression:**
  `17e929650203525dd3cb41d1878908ffd2c1978b`. P3-4, P3-5B and P3-6 pass their
  bounded source/automation/review Gate. A fresh ACL-private current-source run
  also passes the production-factory/real-Agent/file-Tool/reopen/cleanup
  regression; it is not physical browser/audio-device or complete-P3 proof.
- **Current product status:** **P3 EXPANSION ACTIVE — P3-G0 passed its scoped
  authoritative-foundation Gate under D-086; controlled product readiness
  remains unpassed.** P3-2, P3-3, P3-4, P3-5A, P3-5B and P3-6 have locally
  integrated source, affected automation and independent review. P3-7 now also
  passes its scoped formal multi-Task Web source/automation/review Gate on
  `98e063f084c140cb6eb0042de32f3695c89c7279`; it grants no physical or complete-
  product credit. Wave-2 and
  the bounded Wave-3 private regression have validated physical credit only
  for their declared seams. The P1/P2 post-TTS repair is now integrated with
  scoped automation/build evidence and a source-bound functional physical PASS;
  latency, Exit/re-enable, broader generalization and cumulative product
  acceptance remain open, so no product-readiness PASS is inferred.
- **Accepted historical baseline:** `PASS — INTEGRATED WEB ALPHA` remains bound
  only to `d33b520e0d21ae0829d30814d77a01cc18256f09`. Later source and broader
  functionality do not inherit that result.
- **Latest physical product result:** `FAIL — P3-G0 CONTROLLED CANDIDATE NOT
  ACCEPTED` on exact clean product source `f24dd17d336c8266954f2d7299ca13bd0314d424`.
  See the sanitized [P3-G0 attempt](evidence/P3_G0_PRODUCT_READINESS_FAIL_20260819_f24dd17d.md).
- **Latest scoped P1/P2 physical result:** **FUNCTIONAL PASS / LATENCY PARTIAL**
  on exact clean source `e1df8b452`. Repeated short/long audible responses,
  automatic post-playout listening, foreground Stop and button/automatic
  playout-time barge-in passed. The same run exposed variable 8.17–15.09 second
  Agent presentation latency dominated by one-notification-per-RPC P2
  head-of-line delay; see the sanitized
  [physical validation and latency finding](evidence/P1_T2_HANDS_FREE_PHYSICAL_VALIDATION_AND_LATENCY_FINDING_2026-08-20.md).
  This scoped result does not upgrade the failed controlled candidate or close
  feature-complete latency acceptance.
- **Latest scoped P2 notification result:** **BOUNDED-PULL FUNCTIONAL PASS /
  FIXED-CORPUS LATENCY STILL PARTIAL** on exact source `4b405fca1`. With the
  bounded P2 pull enabled, the accepted manual run completed the three prompts
  in `10.65s`, `7.05s`, and `2.78s / 3.14s / 3.14s`, with audible TTS and no
  recurrence of `SPEECH_OPERATION_NOT_AUTHORIZED`. [D-092](decisions/DECISIONS.md)
  therefore makes Web batch size `16` the production default and retires the
  two validation-only deployment switches; clients that omit
  `max_notifications` remain a single-notification compatibility path. This
  small, non-frozen prompt run is acceptance evidence for the default change,
  not p50/p95 or feature-complete latency proof.
- **P3-G0 status:** **PASS — AUTHORITATIVE P3 FOUNDATION; CONTROLLED
  PRODUCT-READINESS REMAINS FAIL.** [D-086](decisions/DECISIONS.md) accepts the
  sequencing risk and removes the failed P1/P2 hands-free condition as a P3-1
  Gate without changing the immutable candidate result.
- **Current highest priority:** preserve the integrated P1/P2 repair and closed
  D-088/D-089/D-090/D-091 evidence. P3-7 is integrated and scoped PASS; the
  active P3 packet now accepts the independently reviewed add-only P3-8B B1
  preparation, then executes B2 composition and replacement-gated retirement
  against the frozen D-091 interfaces. The P1/P2 closeout sequence remains:
  repair the one reproduced mounted Exit/immediate-re-enable regression;
  preserve the now-default bounded P2 notification pull and its legacy single-
  pull compatibility;
  close generation-time interruption required by the formal feature-complete
  P1/P2 boundary; then run the complete fixed-corpus, automated, review and real-
  device Journey. P3-8B and P1/P2 may overlap only under disjoint ownership.
  Any packet
  that changes Interaction or intent semantics must first name its semantic
  owner, fixed corpus/languages, thresholds and capability-owned positive/
  negative/zero-effect evidence.
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
| Audio Device & browser I/O | **PARTIAL.** Browser capture/playout, lifecycle fencing and dedicated media wiring exist. `P1/P2-T1` repaired the failed rotation mechanism, and the later exact-source `e1df8b452` physical run passed repeated short/long audible playout, automatic post-playout listening, foreground Stop and playback-time barge-in without the prior visible recovery failure | Fixed-boundary/idle rotation attribution across broader devices; permission recovery; AEC/NS/AGC and double-talk; measured first-frame/loss/stop targets | P1/P2 completion before controlled-candidate/feature-complete acceptance; scoped physical evidence in the [2026-08-20 run](evidence/P1_T2_HANDS_FREE_PHYSICAL_VALIDATION_AND_LATENCY_FINDING_2026-08-20.md) |
| Speech Recognition | **PARTIAL.** Real microphone finals now sustain repeated automatic turns on `e1df8b452`. Ordinary and barge-in capture both retain the 1.2-second server-VAD silence contract; one EOT-to-submit interval was 0.669 seconds | Fixed-corpus ordinary/barge-in p50/p95 and pause/truncation evidence before VAD tuning; exact provider speech-start attribution, robust fallback/cancel, Provider-neutral configuration and broader device/network validation | Audio I/O, media route and benchmark owner; no claim that recognition finalization is barge-in-specific |
| Speech Synthesis | **PARTIAL.** Streaming/Batch TTS, browser playout, response ownership and ACK paths exist; repeated short/long TTS was physically audible on `e1df8b452` without the repaired ACK/receipt failures | Provider-neutral configuration, measured first-audio/underrun/pronunciation targets and complete stale/cancel recovery | Conversation Runtime ownership and Audio I/O stop confirmation; scoped physical PASS does not close feature-complete targets |
| Realtime Media | **PARTIAL.** Dedicated transport, capture rotation, media registration and presentation ACK sustain the scoped `e1df8b452` physical loop. The bounded P2 notification pull removes the observed one-notification-per-RPC tail from the production Web path: Web requests `16`, the server accepts explicit `2..16`, and omitted input remains a legacy single pull. The feature-on `4b405fca1` manual run passed without the repaired TTS authorization failure | Backpressure/load targets; drop/reorder/corruption/reconnect matrix; stable diagnostics across repeated recovery; fixed-corpus p50/p95 proof | Audio I/O plus Conversation Runtime; [D-092](decisions/DECISIONS.md) and cumulative real network/device verification |
| Conversation Runtime | **PARTIAL.** committed-input fencing, generation ownership, ACK/history projection, Exit fencing, exact foreground Stop, automatic continuation and button/automatic playout-time barge-in passed the scoped `e1df8b452` physical journey. Bounded final notification delivery is now default-on after the scoped `4b405fca1` acceptance | **Hands-free speech during Agent generation cannot currently interrupt or replace that response and remains explicit follow-up work**; complete `ask_user` voice loop, mounted Exit/re-enable and cross-load arbitration | Media, Interaction Intelligence, Agent Bridge and presentation regressions |
| Interaction Intelligence | **PARTIAL.** VAD/EOT and bounded dialogue/background routing exist for the controlled journey | General natural-language routing, false endpoint/interruption and echo/double-talk evaluation, language/config generalization; Native model-level duplex remains optional | Streaming Speech plus Runtime; measured golden corpus |
| Agent Bridge and dialogue truth | **PARTIAL.** Real Agent dialogue/tools and bounded response/progress integration exist | Non-blocking progress provenance, strict Task-truth isolation, bounded result-context reservation and unconstrained reread prevention | Runtime, Task/Event truth and affected text-path regressions |
| Task Control Core and Store | **PARTIAL overall; P3-1, P3-2, P3-4, P3-5A, P3-5B and P3-6 scoped Gates PASS.** Schema v6 retains canonical multi-Task authority, closed command/disposition/update/successor semantics, durable D0-D2 checkpoint/effect/recovery truth, Task-wide retained replay and class-isolated presentation ACK. Production multi-Task queries/mutations use authenticated reread and exact Task/Attempt/head CAS; unsupported controls remain truthful | Complete later P3 UI/product-model packages and cumulative one-product acceptance without adding a second Task, event, presentation or confirmation authority | Executor capability/admission/durability facts, Voice–Task Bridge and restart/concurrency matrix; exact Wave-3 facts in the [evidence](evidence/P3_WAVE3_DURABILITY_PRESENTATION_INTENT_EVIDENCE_20260821.md) and [review](reviews/P3_WAVE3_DURABILITY_PRESENTATION_INTENT_IMPLEMENTATION_REVIEW_2026-08-21.md) |
| Executor & Durability | **PARTIAL overall; P3-3 and P3-4 scoped Gates PASS.** Immutable Direct capability/profile selection, priority/FIFO admission, project-busy/capacity deferral, D0/D1/D2 truth, checkpoint resume, effect reconciliation, linked recovery and ambiguous-effect manual settlement are integrated. Real Agent/file-Tool production regression and Store/Direct/OS-lock product-path evidence are closed within their declared boundaries | Generalize the supported Executor/configuration matrix and carry D0-D2 truth through later product acceptance; no additional durability primitive is implied | Tier-3 Direct/Store/Core evidence plus exact Wave-2 and Wave-3 private boundaries; the private run is not a host-crash oracle |
| Voice–Task Bridge | **PARTIAL overall; P3-6 scoped Gate PASS and P3-7 consumer integrated.** Committed natural text/voice and strict structured input resolve explicit multi-Task targets through the real Registry/classifier/Bridge/Store/Core composition. Five queries and six mutations are supported; clarification, durable single-use confirmation, parity and zero-false-truth paths are closed. The formal Web owner now consumes these queries/mutations without adding another Bridge authority | Broader language/policy generalization; provide-input/pause/resume remain unsupported until real primitives exist; P3-8B may observe but not replace this authority | Exact Store Task/Attempt/event/result/capability truth, authenticated context/model reread, the 68-case/14-group corpus and frozen D-091 interface |
| Integrated Web product experience | **PARTIAL overall; P3-5B and P3-7 scoped Gates PASS.** The visible formal carrier now lists/selects multiple authenticated Tasks and projects exact state/outcome/admission/current-Attempt progress/history/result/lineage plus only current-principal-supported controls. Initial load, select, refresh and reconnect revalidate list/status/events/result; failed revalidation retains zero formal activation/ACK. Durable text/voice consumption remains P3-5B-owned. On exact source `e1df8b452`, foreground Agent/TTS and hands-free controls physically passed; after the `4b405fca1` batch authorization repair, three bounded-pull prompts also passed and the production owner now fixes notification batch size at `16`. The mounted Exit/immediate-re-enable automated seam remains deferred | Compose P3-8B diagnostics/configuration and replacement-gated retirement without changing the frozen P3-7 authority; close Agent-generation interruption, fixed-corpus presentation latency, mounted Exit/re-enable recovery, device/privacy/recovery UX and the cumulative human journey | [P3-7 evidence](evidence/P3_7_FORMAL_INTEGRATED_WEB_EVIDENCE_20260821.md), [P2 default-on evidence](evidence/P2_NOTIFICATION_BATCH_DEFAULT_ON_20260821.md), P3-8B/P3-9 plus remaining P1/P2 completion |
| Observability, benchmark and latency | **PARTIAL overall; additive P3-8A assets and P3-8B B1 preparation PASS.** Trace foundations now include bounded SLI/privacy/OTel assets plus an immutable correlation/causation validator. The `e1df8b452` diagnostic isolated the one-RPC-per-notification tail; the later feature-on manual samples were `10.65s`, `7.05s`, and `2.78s / 3.14s / 3.14s`. They support the default-on decision but are not a frozen-corpus benchmark | B2 must compose the codec/exporter/backend lifecycle and content-free Task/Executor/presentation diagnostic chain; execute the remaining [latency plan](roadmap/LATENCY_OPTIMIZATION_PLAN_2026-08-18.md) with frozen environment/corpus and p50/p95 proof | [P2 default-on evidence](evidence/P2_NOTIFICATION_BATCH_DEFAULT_ON_20260821.md), [P3-8B preparation](reviews/P3_8B_PREPARATION_RETIREMENT_MANIFEST_2026-08-21.md), and fixed corpus/environment |
| Automated verification and product acceptance | **PARTIAL overall; Wave-2, bounded Wave-3 and P3-7 scoped Gates PASS.** The P2 default-on cleanup passes its focused backend compatibility checks, dependency-injected A/B test and production build. Full Formal Web is `445/446`; its only failure is the already-disclosed mounted Exit/re-enable case. Exact source `4b405fca1` has the scoped human bounded-pull/TTS PASS; latency remains PARTIAL, the combined P3 Task journey remains open, and the controlled candidate remains FAIL | Complete P3-8B, fixed-corpus latency and deferred Exit/re-enable, then run the clean cumulative Journey, feature-complete matrix, competitor-gap review and independent deep review | [P2 default-on evidence](evidence/P2_NOTIFICATION_BATCH_DEFAULT_ON_20260821.md), [P3-7 evidence](evidence/P3_7_FORMAL_INTEGRATED_WEB_EVIDENCE_20260821.md), [Wave-3 evidence](evidence/P3_WAVE3_DURABILITY_PRESENTATION_INTENT_EVIDENCE_20260821.md) and exact clean sources |
| Configuration, code and document cleanup | **PARTIAL overall; P3-8B B1 preparation PASS.** Three cleanup audits and document Batch A are complete. D-092 retires only the two validation-only P2 notification deployment switches after scoped human acceptance: production Web is fixed at `16`, A/B uses dependency injection of `1` or `16`, and the server's omitted parameter remains legacy single-pull compatibility. Successor-ACK/TTS stays default-on and has no switch to retire. Other Live Voice product gates retain their existing semantics | B2 must consume its separate declaration without auth/durability downgrade, migrate each replacement oracle, and retire only manifest rows whose preconditions/flag-on/flag-off/rollback review pass; local artifacts and generic non-Live-Voice consumers stay excluded | [D-092](decisions/DECISIONS.md), [P2 evidence](evidence/P2_NOTIFICATION_BATCH_DEFAULT_ON_20260821.md), and the [P3-8B preparation/manifest](reviews/P3_8B_PREPARATION_RETIREMENT_MANIFEST_2026-08-21.md) |
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

A P1/P2 defect was demonstrated twice on the clean candidate and was explicitly
deferred from the P3-1 sequencing Gate:

7. **P1/P2 post-TTS capture continuation — SCOPED FUNCTIONAL REPAIR PASS / FULL
   ACCEPTANCE PARTIAL.** The original `f24dd17d` candidate remains failed. The
   repair is integrated on W3 with affected automation/build evidence, and exact
   source `e1df8b452` passed repeated audible turns, automatic post-playout
   listening, foreground Stop and playout-time barge-in. Quiet multi-boundary
   and broader device/network generalization, mounted Exit/re-enable,
   generation-time interruption, fixed-corpus latency and the combined P3 Task
   journey remain open. See the [dated disposition](evidence/P1_P2_POST_TTS_CAPTURE_CONTINUATION_DEFERRED_20260819.md),
   [physical result](evidence/P1_T2_HANDS_FREE_PHYSICAL_VALIDATION_AND_LATENCY_FINDING_2026-08-20.md)
   and [W3 integration evidence](evidence/P1_P2_W3_INTEGRATION_EVIDENCE_20260821.md).

The explicit build profile and ordinary-production flag-off behaviour are
source/build/deploy verified. D-086 passes only the P3 expansion prerequisite;
it cannot upgrade the failed candidate or invalidate the historical
exact-source Alpha result.

## Current execution packet

- **Packet:** D-060/D-062 bounded `P3-7` + staged `P3-8B` parallel batch —
  **ACTIVE**. Main is the sole Integration Owner, shared semantic owner,
  integration-branch Git writer and owner of STATUS, decisions, final evidence
  and interface-freeze disposition. Workers may commit only their isolated task
  branches and may not push or integrate their own returns.
- **Activation baseline and D-085 findings:** exact clean source
  `29589734a0bb51a697bf7d594e3b1bb552ddcd34`. The affected audit rows remain
  Integrated Web, Observability and Configuration/cleanup: the formal carrier
  still lacks the complete multi-Task experience and truthful display-layer
  projection; the accepted P3-8A codec remains uncomposed; recovery correlation,
  validated general configuration and replacement-gated legacy retirement stay
  open. The later P3-2 through P3-6 and P3-8A scoped evidence, rather than the
  audit's older implementation details, defines the accepted dependency source.
- **Dependency and integration order:** accepted P3-2 through P3-6 open A's
  formal composition Gate; accepted P3-8A opens only B's additive preparation.
  A and B1 may implement concurrently with disjoint files. Main then reviews and
  integrates A, runs the affected `P3-7` Gate, fixes findings, records a clean
  Gate commit and freezes the formal interfaces. B1 integrates as its own
  additive preparation commit. Only after `P3-7` is PASS may B2 compose the
  frozen interfaces, migrate replacement oracles and retire manifest items.
- **Current packet disposition:** Child A is integrated at exact source
  `98e063f084c140cb6eb0042de32f3695c89c7279` and **P3-7 SCOPED GATE PASS**
  under [D-091](decisions/DECISIONS.md), with
  [review](reviews/P3_7_FORMAL_INTEGRATED_WEB_IMPLEMENTATION_REVIEW_2026-08-21.md)
  and [evidence](evidence/P3_7_FORMAL_INTEGRATED_WEB_EVIDENCE_20260821.md).
  B1 is accepted on integrated source
  `bd3fd0883e93dd73a55927296d4fe75ac0956132`: exactly seven add-only files,
  focused `59/59`, accepted P3-8A regression `207/207`, scoped static checks and
  independent `0 Critical / 0 Important / 0 Minor`. B2 is now active on that
  baseline under the exact lease below.

### Child A — P3-7 formal Integrated Web P3 experience

- **Owner/capability/risk:** A worktree owns the Integrated Web product
  experience and formal P3 Web projection; Tier 3 because visible mutation,
  multi-Task isolation, Runtime presentation and product composition cross an
  authority boundary. Main owns any semantic or interface conflict.
- **Exact file ownership:** A exclusively owns
  `LiveVoiceIntegratedRoutePanel.tsx`, `LiveVoiceDemoBar.tsx` and its CSS,
  `ChatPanel/index.tsx`, a new `formalP3TaskExperience.ts`, their focused
  frontend tests, the Integrated Web test script, and only the required i18n
  entries. If exact backend authority projection is required, A also owns the
  narrow `product_composition_registry.py` projection and its focused tests.
  `agent_ws_server.py`, formal route modules and their tests may be changed only
  if current source proves the existing closed method surface insufficient;
  no new common ReqMethod or shared wire/Store schema is authorized.
- **Intended behaviour:** show and revalidate at least two authoritative Tasks;
  preserve stable Task/Attempt/correlation, exact state/outcome, admission/
  queue, progress, blocking question, unread/result replay and successor
  lineage; recover selection from browser storage as a hint without creating a
  Task. Present command accepted, applied and terminal outcome separately.
  Before every control, reread backend authority and bind the exact Task,
  Attempt, command/request, event head and version/revision. Use only accepted
  query/mutation primitives; keep `provide_input`, pause and resume unavailable
  or stable unsupported. Revisions create an explicit successor and never
  rewrite the predecessor or result.
- **Authority and compatibility:** TaskResult/TaskEvent remain the sole Task
  truth. Task events never call TTS directly; Runtime response/generation/TTS
  and PresentationAck retain voice/text consumption ownership. Stop, response
  cancel and barge-in never imply Task cancel. Feature-off retains the supported
  text path; no legacy authority is deleted in A.
- **Acceptance:** positive evidence covers two real Tasks, exact selection,
  create/list/get/status/events/result, every backend-supported update/control,
  reconnect/unread/replay and successor lineage. Negative/boundary/state/order/
  concurrency/recovery/isolation/feature-off cases cover malformed,
  unauthorized, unknown, unsupported, conflict, duplicate, stale head/owner,
  wrong subject/project/session/Task/Attempt, reordered events, concurrent
  terminal/control, missing ACK and reconnect. Every rejected or wrong-scope
  path asserts zero Agent, Tool, Task, audio, history, store and foreign-scope
  effects. The real AgentServer → Registry → SQLite Core seam, mounted React DOM
  and Runtime ACK are required; physical audio perception is not claimed by
  this package.
- **Review/evidence:** focused frontend/backend tests, full affected Formal Web,
  feature-off/build/static checks, complete scoped diff review and independent
  Tier-3 review. The known mounted Exit/immediate-re-enable baseline is disclosed
  and may not be counted as an A regression without source evidence. Main owns
  the `P3-7` review/evidence record and the frozen Panel/formal-route,
  Registry/AgentServer, Task projection, Runtime ACK and feature-off contract.
- **Disposition:** **PASS on integrated source `98e063f084c140cb6eb0042de32f3695c89c7279`.**
  Backend composition/AgentServer completed `184 passed`, owner `14/14`,
  mounted affected set `10/10`, build profiles `2/2` and production build PASS.
  Full Formal Web completed `439/440`; the sole failure is the clean-baseline
  P1/TTS Exit/re-enable late ACK case. Final independent review returned
  `0 Critical / 0 Important / 0 Minor`. Interfaces are frozen by D-091.

### Child B — P3-8B additive preparation, then frozen-interface composition

- **Owner/capability/risk:** B worktree owns observability correlation,
  validated configuration declaration, privacy conformance and retirement
  inventory; Tier 3 for telemetry privacy/diagnostic truth and configuration
  capability claims. Pure inventory documentation is Tier 0 but grants no
  product credit.
- **B1 exact add-only ownership:** B may only add
  `observability_correlation_contract.py`,
  `live_voice_configuration_declaration.py`, their focused tests,
  `tests/fixtures/live_voice_retirement_manifest_v1/manifest.json`, its manifest
  test and `reviews/P3_8B_PREPARATION_RETIREMENT_MANIFEST_2026-08-21.md`. B1 does
  not modify package exports, P3-8A source, A files, AgentServer, Registry,
  formal routes, Panel, common wire schema or any product composition file.
- **B1 intended behaviour:** provide immutable pure validation for the bounded
  subject/project/session/interaction/response/generation and Task/Attempt/
  Command/Event/outbox/Executor/checkpoint/effect/presentation causation map;
  keep high-cardinality identifiers out of bounded metric dimensions. Convert
  already validated configuration into an exact capability declaration without
  reading environment variables, starting a worker/provider/backend or silently
  downgrading authentication/durability. Inventory every legacy item with its
  replacement owner, oracle migration, deletion precondition, affected tests,
  rollback and `inventory` phase; delete nothing.
- **B1 acceptance:** valid correlation/configuration and complete inventory
  cases succeed; unknown/private/malformed/over-bound, missing-parent,
  cross-scope, conflicting replay and impossible capability combinations fail
  closed. Rejected and feature-off paths produce zero exporter, network,
  persistence, Agent, Tool, Task, audio, history or business effect. Focused
  tests plus the accepted P3-8A affected privacy/codec/adapter suite, scoped
  static checks, link/manifest validation and independent Tier-3 review pass.
  External OTel/backend, product composition, lifecycle/health and retirement
  are explicitly unclaimed.
- **B1 disposition:** **PASS on integrated source `bd3fd0883e93dd73a55927296d4fe75ac0956132`.**
  The commit is exactly seven add-only files and preserves every existing
  product/composition owner. Main reproduced focused `59/59`, P3-8A affected
  `207/207`, Ruff/format/compile/diff checks; independent final review returned
  `0 Critical / 0 Important / 0 Minor`.
- **B2 frozen-interface scope:** after Main records `P3-7` PASS, B may connect
  P3-8A codec/SLI/privacy assets behind the existing formal adapter/exporter;
  carry content-free diagnostics through admission, queue, lease, outbox,
  checkpoint, recovery, reconcile, result and presentation seams; consume
  validated Provider/Executor/profile configuration; and migrate each oracle
  before its manifest deletion. Any A-owned file requires a new Main-issued
  single-writer lease after interface freeze. Raw audio, prompt, blocking answer,
  TaskResult/artifact content and credentials remain prohibited; metric labels
  are closed and bounded.
- **B2 acceptance and retirement Gate:** a failed journey identifies the exact
  Task/Attempt/Command/generation/ACK/Executor seam without private content;
  ordinary production stays default-off; configuration/privacy/failure paths
  fail closed; formal composition is the sole product authority. An entrypoint,
  runner, validator, scheduler/Bridge/UI authority, Demo itinerary/bypass
  dependency or compatibility path is deleted only after its replacement owner,
  migrated oracle, flag-on/flag-off regression, rollback and affected review
  pass. Generic non-Live-Voice `schedule.*` consumers are outside retirement.
- **B2 active baseline and single-writer lease:** exact clean source
  `bd3fd0883e93dd73a55927296d4fe75ac0956132`. The isolated B2 worktree may edit
  the two B1 contracts, P3-8A `observability*` codec/exporter/fault/privacy
  modules, `product_observability_adapter.py`, and new focused backend/tests.
  D-091 grants it the narrow existing-file lease for `agent_ws_server.py`,
  `product_composition_registry.py` and the currently selected Provider/
  Executor/profile configuration entrypoints only to consume validated
  declarations, carry content-free observations and expose fail-closed
  lifecycle/health. It may add frozen read/projection hooks but may not alter
  Task/Core/Store/Executor/Runtime/PresentationAck authority. Retirement files
  are leased only after the manifest proves the exact replacement oracle;
  shared `schedule.*`, current Direct Adapter, fixed media registry/handler,
  formal Panel/routes and P3-7 projection remain retained unless Main records a
  narrower replacement disposition.
- **B2 sequencing:** first compose validated configuration plus correlation,
  codec, bounded exporter/backend lifecycle and health; next prove the complete
  content-free diagnostic chain and privacy/feature-off zero effects; then
  migrate manifest oracles and delete only rows whose preconditions pass. A
  read-only retirement scout may run in parallel, but no candidate deletion is
  authorized merely by inventory status.

- **Shared exclusions/non-claims:** no P1/P2 Exit/immediate-re-enable repair,
  notification-latency work, VAD/TTS/media change, generation-time barge-in,
  new classifier/product policy, canonical Task state or primitive, shared
  protocol/schema/migration/auth/durability change, AgentCore strategic
  migration, Hermes rewrite, P3-9, cumulative human acceptance, complete P3,
  feature complete, product readiness, Production, `develop` integration or
  remote-ref update. Discovery of any such requirement pauses the affected
  child for explicit re-scope/re-tier while disjoint work continues.

## Closed P1/P2 integration packet detail

The following source-bound records preserve the just-closed P1/P2 integration
facts and remaining gaps. They are not child packages in the active P3 batch.

### Batch member P1/P2-T1 — post-TTS capture continuation repair

- **Packet:** P1/P2-T1 — repair the deferred post-TTS capture continuation
  defect on the formal Web route.
- **Contract:** the six repair directions and later-acceptance criteria in the
  [deferred issue record](evidence/P1_P2_POST_TTS_CAPTURE_CONTINUATION_DEFERRED_20260819.md).
  Changing only the 30-second value is not an accepted repair; changing the
  capture-duration contract itself requires its own prior decision.
- **Scope:** transparent post-TTS capture rotation; a decaying local-activity
  observation instead of a sticky lease-lifetime flag; separation of
  capture-lease age from active-utterance duration; preserved provider
  speech-start/EOT, barge-in, generation fencing and stale-lease isolation
  including speech-start/rotation races; sanitized capture diagnostics
  (phase/generation, frame counts, recent local activity, rotation reason,
  actual AEC/NS/AGC settings — no raw audio, credentials or private device
  identity). Streaming cancel/cleanup is rechecked after the primary repair
  and repaired here only if it persists independently and stays bounded;
  otherwise it returns as its own affected packet.
- **Owner/files:** formal P1 voice route and capture adapters —
  `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts`,
  `formal/adapters/browserAudioIOAdapter.ts`,
  `formal/adapters/liveVoiceCaptureProcessor.js`, minimal integration in
  `components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx`, their test
  suites, and the streaming-speech seam only if the cancel/cleanup recheck
  confirms an independent bounded defect.
- **Risk:** Tier 3 under root `TESTING.md` (capture/media/runtime seams).
- **Excluded:** any `task_store.py`/`persistent_task_core.py`, P3 command or
  result/consumer schema, or central product-composition registry change — a
  required wiring change returns as a minimal separate integration patch;
  latency optimization work; physical PASS claims.
- **Acceptance:** a deterministic regression proving one post-playout
  high-energy frame followed by silence rotates transparently across the
  lease boundary with no visible error and zero forbidden
  Agent/Tool/Task/audio/history effects; decaying local activity; silent
  multi-boundary rotation; preserved speech-start/EOT/barge-in/fencing/
  stale-lease races; affected frontend/backend automation; independent
  Tier-3 cold review; synchronized STATUS/evidence. The physical continuation
  criteria remain owned by the deferred record and close only on a later real
  microphone/TTS run; this packet grants no physical credit.
- **Delivery (2026-08-19):** source repair, deterministic regression, matrix
  oracles, sanitized diagnostics and disclosure updates are implemented with
  affected automated evidence — `productP1VoiceRoute` 86/86, adapter/processor
  103/103, integrated-web battery 410/411 with only the unchanged pre-existing
  deferred Exit/re-enable seam failing — recorded in the
  [repair record](evidence/P1_T1_POST_TTS_CAPTURE_ROTATION_REPAIR_2026-08-19.md).
  The independent Tier-3 cold review passed with no P1/P2 and four recorded
  P3 notes, each dispositioned in the repair record. The later exact-source
  physical journey passed its scoped continuation criteria; broader device,
  quiet multi-boundary, Exit and cumulative acceptance remain open.

### Batch member P1/P2-T2 — playout repair and bounded-notification latency repair delivered

- **Packet result:** successor-capture ACK and post-playout receipt decoupling,
  hands-free controls, bounded P2 notification pulls and their dedicated-media
  authorization repair are delivered. Scoped human acceptance makes batch size
  `16` the production Web default under D-092; the
  [latency optimization plan](roadmap/LATENCY_OPTIMIZATION_PLAN_2026-08-18.md)
  remains open for fixed-corpus and later-stage targets.
- **Constraint:** later latency work must preserve the P2 notification protocol
  and legacy omitted-parameter compatibility. No Provider/model/billing change,
  persistent speech cache, new retention policy or raw-audio storage; ideas
  rejected in the plan's §8 stay rejected.
- **Risk:** per-batch tier under root `TESTING.md`; the pipeline and
  sentence-overlap batches are Tier 3.
- **Acceptance:** per the plan's §§3–7 measured evidence relative to the
  fresh baseline; targets become release gates only after environment, corpus
  and sample size are frozen.
- **Current latency priority:** the dominant P2 one-notification-per-RPC tail is
  repaired and default-on after the scoped D-092 acceptance. Next evaluate VAD
  finalization and text-to-first-audio startup against a frozen corpus; do not
  infer p50/p95 from the small manual sample. The diagnosis and successor result
  are in the [2026-08-20 physical record](evidence/P1_T2_HANDS_FREE_PHYSICAL_VALIDATION_AND_LATENCY_FINDING_2026-08-20.md)
  and [default-on evidence](evidence/P2_NOTIFICATION_BATCH_DEFAULT_ON_20260821.md).

#### T2-L2A — successor-capture ACK must not gate authoritative playout (SOURCE/AUTOMATED REPAIRED; SCOPED PHYSICAL PASS, 2026-08-20)

- **Observed failure:** exact source `6cd8840d5` reached authoritative Agent
  text and obtained a streaming-TTS downlink descriptor, then failed before
  opening the browser downlink because the successor microphone uplink's first
  frame was not ACKed inside the fixed one-second readiness window. The product
  surfaced `AUDIO_CAPTURE_MEDIA_NOT_ACKNOWLEDGED` under the TTS seam and emitted
  no audible response. This is physical FAIL evidence, not a regression claim
  against the T1 capture-rotation diff; the ACK gate predates that diff.
- **Intended behaviour:** establish the authoritative TTS downlink independently
  of successor-capture readiness. A ready successor capture enables barge-in;
  a late or failed successor capture degrades interruption/listening truthfully
  without discarding the response. Initial user capture remains fail-closed
  until a real first-frame ACK. `playing` may be published only after browser
  playout owns and schedules audio, never while synthesis/capture preparation
  alone is pending.
- **Owner/files:** formal P1 orchestration and its Integrated Web projection —
  `productP1VoiceRoute.ts`, the minimal
  `LiveVoiceIntegratedRoutePanel.tsx` status/diagnostic seam and their tests;
  media adapters or Gateway files only if timing evidence proves an in-scope
  defect rather than merely adding content-free timing diagnostics.
- **Risk:** Tier 3 under root `TESTING.md`: capture/playout failure ownership,
  generation/cancel fencing and physical user-observed truth cross the P1
  Audio I/O, Realtime Media and Conversation Runtime seams.
- **Excluded:** Provider/model/voice/billing changes; the T1 30-second rotation
  contract; P3 Task/Agent policy or schema; weakening initial-capture ACK
  readiness; raw-audio, transcript, credential or device-identity telemetry;
  a physical PASS claim before a later real microphone/TTS run.
- **Acceptance:** deterministic capture-ready, delayed-ACK, never-ACK,
  late/stale-ACK, capture-failed and cancel/Exit-during-startup oracles; exact
  once-only downlink/audio scheduling; truthful degraded interruption state;
  bounded cleanup of capture, downlink, timers and media authorities; zero
  duplicate Agent/Tool/Task/history or stale-audio effects; affected automated
  suites and independent Tier-3 review. Real short/long TTS audibility and
  post-playout listening remain physical acceptance.
- **Current result:** the downlink and successor capture now start
  independently; successor readiness failures degrade only interruption,
  exact cleanup restores the predecessor receipt authority, and `playing` is
  emitted only after the browser schedules audio. Affected automation is
  **413/414** Integrated Web (only the unchanged recorded Exit/immediate-restart
  failure) plus **103/103** browser audio/processor. Source and automated
  evidence: [P1_T2_SUCCESSOR_CAPTURE_ACK_DECOUPLING_2026-08-20.md](evidence/P1_T2_SUCCESSOR_CAPTURE_ACK_DECOUPLING_2026-08-20.md).
  Independent Tier-3 review remains open. The later exact-source real
  microphone/speaker run physically passed short/long audible playout,
  automatic listening and playout-time barge-in as recorded in the
  [physical validation](evidence/P1_T2_HANDS_FREE_PHYSICAL_VALIDATION_AND_LATENCY_FINDING_2026-08-20.md);
  no broader product-readiness credit is claimed.

#### T2-L2B — completed playout receipt must not require early duplex media (SOURCE/AUTOMATED REPAIRED; SCOPED PHYSICAL PASS, 2026-08-20)

- **Observed failure:** exact source `874cf327c` spoke the complete short TTS
  answer, then reported `PRODUCT_TTS_PLAYBACK_FAILED` and closed the successor
  listening route. Gateway cleanup emitted
  `STREAMING_SPEECH_CANCEL_UNACKNOWLEDGED`; the current Web projection discarded
  the more specific RPC code.
- **Intended behaviour:** the exact authorized downlink and browser-render
  receipt settle playout independently. The existing
  `duplex_media_observed` field reports true/false without turning missing or
  late successor media into a retroactive TTS failure. Initial user capture
  remains ACK-gated and fail-closed.
- **Owner/risk/exclusions:** Gateway media registration, formal P1 receipt
  validation, minimal Web reason projection and their tests; Tier 3 under root
  `TESTING.md`. Agent/Tool/Task/history, P2/P3 schemas, Provider configuration,
  capture-duration policy, private telemetry, physical PASS and remote refs are
  excluded.
- **Acceptance:** old-source failing minimal no-duplex receipt regression;
  repaired false/true duplex receipts; unchanged invalid/stale/binding
  rejection; completed TTS without duplicate business effects; affected
  backend/frontend suites, scoped review and a freshly prepared runtime. Human
  audibility and automatic post-playout listening remain physical acceptance.
- **Evidence:** [P1_T2_POST_PLAYOUT_RECEIPT_DECOUPLING_2026-08-20.md](evidence/P1_T2_POST_PLAYOUT_RECEIPT_DECOUPLING_2026-08-20.md).
- **Current result:** the old-source Python and browser-route minimal repros
  failed at the exact no-early-duplex boundary and pass after the repair.
  Gateway registration/synthesis/RPC/streaming suites, browser audio I/O,
  TypeScript and the affected Integrated Web suite pass except for the same
  pre-existing Exit/immediate-re-enable case (414/415). A later exact-source
  real Chrome journey physically passed audible short/long turns and automatic
  successor listening without the repaired receipt failure, as recorded in the
  [physical validation](evidence/P1_T2_HANDS_FREE_PHYSICAL_VALIDATION_AND_LATENCY_FINDING_2026-08-20.md).
  The scoped PASS does not upgrade product readiness.

#### T2-L2C — hands-free controls and scoped physical functional result (FUNCTIONAL PASS / LATENCY PARTIAL, 2026-08-20)

- **Source:** `e1df8b452` exposes the existing exact-response interrupt-and-speak
  and Stop controls on the formal hands-free surface; automatic playout-time
  barge-in continues to use the already-owned successor capture.
- **Physical result:** repeated short/long audible TTS, automatic post-playout
  listening, foreground Stop and button/automatic playout-time barge-in passed
  in real Windows Chrome. Agent-generation speech interruption remains open.
- **Performance result:** presentation latency varied from the earlier observed
  1.26 seconds to 8.17–15.09 seconds in the retained run. The measured short
  turn spent about 5.52 seconds draining 64 P2 sequence intervals after model
  completion because the formal owner performs one notification RPC at a time.
  A pre-control-exposure 8.59-second turn had the same mechanism, so the delay
  is not caused by automatic barge-in.
- **Disposition:** functional scope PASS; latency and overall acceptance remain
  PARTIAL. The bounded P2 delivery repair is now accepted under D-092; VAD,
  first-audio and fixed-corpus p50/p95 optimization follow. Exact evidence and limitations are in the
  [physical record](evidence/P1_T2_HANDS_FREE_PHYSICAL_VALIDATION_AND_LATENCY_FINDING_2026-08-20.md).

#### T2-L2D — bounded P2 notification pull (SCOPED PHYSICAL PASS / DEFAULT-ON, 2026-08-21)

- **Source and behaviour:** `4b405fca1` authorizes every validated item in a
  bounded notification batch before TTS. The successor cleanup fixes production
  Web at `16`, accepts explicit server bounds `2..16`, and retains omitted
  `max_notifications` as the single-notification compatibility path.
- **Human result:** the accepted feature-on run completed the three prompts in
  `10.65s`, `7.05s`, and `2.78s / 3.14s / 3.14s`; TTS was audible and the prior
  `SPEECH_OPERATION_NOT_AUTHORIZED` recovery failure did not recur.
- **Configuration result:** both validation-only deployment switches are
  retired. A/B continues through an injected owner batch size of `1` or `16`;
  Successor-ACK/TTS remains unchanged and has no feature switch.
- **Limits:** the retained prompts, sample count and environment were not a
  frozen benchmark, so fixed-corpus p50/p95, Exit/re-enable, Agent-generation
  interruption and feature-complete acceptance remain open.

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
   and P3-5A retained replay/unread ACK~~ **DONE — SCOPED SOURCE/AUTOMATION/
   REVIEW/PHYSICAL GATE PASS.** The fresh private run proves the required real
   file-Tool pairs, A2 busy/zero-effect/same-Attempt dequeue, adjustment,
   cancellation and clean durable settlement. ~~Activate P3-4, P3-5B and P3-6
   in dependency order~~ **DONE — BOUNDED WAVE-3 GATE PASS.** Schema-v6
   durability/recovery, presentation-gated consumption and authenticated
   multi-Task intent resolution are integrated, independently reviewed and
   bound to current-source private Agent/Tool regression evidence. Continue
   migrating each still-applicable
   historical oracle with its first owning package; perform code placement,
   duplicate consolidation and entrypoint/document retirement only after
   replacement without deleting live coverage. The P1/P2 post-TTS source
   repair and scoped physical continuation are integrated; remaining P1/P2
   work is mounted Exit/re-enable, generation-time interruption and fixed-
   corpus/generalization
   evidence under the [latency optimization plan](roadmap/LATENCY_OPTIMIZATION_PLAN_2026-08-18.md).
   The remaining P3 route is ~~P3-7 formal carrier~~ **DONE — SCOPED GATE
   PASS** → P3-8B composition/retirement → P3-9 cumulative complete-P3
   acceptance under the
   [complete P3 execution plan](roadmap/FULL_P3_EXECUTION_PLAN.md). P1/P2 and
   P3-8B work may overlap with P1/P2 only when owners/files are disjoint. A positive
   `provide_input`, pause or resume claim first requires a separately accepted
   real primitive/capability packet; otherwise the operations remain truthful
   unsupported and their complete-P3 scope must be settled before P3-9 PASS.
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
- **P3 implementation/reuse audit — COMPLETE (2026-08-18, routing snapshot
  rebased 2026-08-19):** see the
  [P3 implementation coverage and historical reuse audit](reviews/P3_IMPLEMENTATION_COVERAGE_AND_HISTORICAL_REUSE_AUDIT_2026-08-18.md).
  Its estimates remain a committed pre-G0 nine-package coverage snapshot; its
  dated routing overlay records the handoff from the P3-G0 scoped PASS through
  accepted P3-1 into the then-active P3-2 package. It is not the current queue;
  current package closure and selection remain in this STATUS. It also
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
- **Documents:** Batch A is complete. Batches B/C retain their original 55-file
  retirement manifest until regression/contract extraction. That manifest's
  20-file interim target predates the 20 P3 planning/review/evidence documents
  added after the audit and is no longer an executable current count. Rebaseline
  the retained/retired set before B/C deletion; audit-time counts remain
  historical metrics, not mutable status facts.
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
  The first physical diagnosis found the dominant P2 one-notification-per-RPC
  tail; the bounded pull is now repaired, physically accepted in a small sample
  and default-on under D-092. Next evaluate VAD finalization, first-audio startup
  and formal sentence-level Agent→TTS overlap against a frozen corpus with
  p50/p95. This remains queued P1/P2 quality work, not completion credit.
- **Reviews:** reproduce findings against current source; fix confirmed issues
  only and rerun affected checks. Feature closure requires one independent
  cross-module review after competitor-gap decisions.
- **P3-8A additive assets — PASS (2026-08-19):** the
  [P3-8A observability assets review](reviews/P3_8A_OBSERVABILITY_ASSETS_REVIEW_2026-08-19.md)
  records the current-source pure SLI/privacy/OTel codec scope, corrected
  `ca3d7780` findings, exact affected evidence and independent Tier-3 PASS. The
  assets are uncomposed and do not make P3-8, product readiness or Production
  operations complete. Its 2026-08-19 disposition that P3-2 could continue is
  an exact-time routing fact; D-088 Wave 2 and D-089 Wave 3 are now separately
  closed, and no later packet is activated here.
- **Local artifacts:** coverage, caches, `dist`, `node_modules`, logs and private
  runtime databases/audio remain ignored and excluded from final integration.

## Verification and runtime truth

- Integrated P1/P2 source `8846862f009d332761763f887c38ce6486f3ee90`
  passes browser audio `103/103`, the affected five-file backend set `194/194`,
  the Live Voice production build and Formal Web `422/423`. The sole failure is
  the unchanged mounted Exit/immediate-re-enable case. Stable source/test patch
  IDs match the four original repair commits. Exact commands, mapping and
  exclusions are in the
  [W3 integration evidence](evidence/P1_P2_W3_INTEGRATION_EVIDENCE_20260821.md).
  The physical result remains source-bound to `e1df8b452`; no W3 physical or
  combined Task-journey rerun is inferred.
- `P3-4/P3-5B/P3-6` bounded Wave-3 source passes final affected automation,
  strict contracts, production build, S8 readiness, static checks and
  independent Tier-3/fix-only review. Broad Python and Formal Web completed
  with two disclosed out-of-scope baseline failures. The fresh ACL-private
  current-source run validated
  production registration/factory, real Agent/file-Tool observations,
  admission/control, reopen and cleanup with 22 observations and zero loss or
  pairing error. Exact commands, counts and non-claims are recorded in the
  [Wave-3 evidence](evidence/P3_WAVE3_DURABILITY_PRESENTATION_INTENT_EVIDENCE_20260821.md)
  and [review](reviews/P3_WAVE3_DURABILITY_PRESENTATION_INTENT_IMPLEMENTATION_REVIEW_2026-08-21.md).
- `P3-2/P3-3/P3-5A` Wave-2 source, schema, composition and default-off evidence
  observer have affected automation/static/build and independent Tier-3 review
  credit, including the final `1008 passed, 5 skipped` combined regression,
  recorded in the
  [implementation review](reviews/P3_WAVE2_COMMAND_ADMISSION_REPLAY_REVIEW_2026-08-19.md).
  The associated [physical evidence](evidence/P3_WAVE2_COMMAND_ADMISSION_REPLAY_EVIDENCE_20260819.md)
  passes on exact source `3aa61f0193ac25e3da277f2dd632870355baf95a`:
  14 content-free observations form 7 exact file-Tool pairs and all 4 required
  successful write/edit streams; A2/control/reopen/cleanup checks are true. The
  validated positive JSON remains private and uncommitted under the evidence
  privacy rule; its sanitized aggregate is recorded in the evidence document.
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
  activated P3-1; P3-1 and the Wave-2/Wave-3 source packages now pass their
  scoped source evidence. Its original transfer of the missing physical Journey
  and [P1/P2 continuation defect](evidence/P1_P2_POST_TTS_CAPTURE_CONTINUATION_DEFERRED_20260819.md)
  is now followed by a later scoped functional repair PASS; the combined P3
  Task Journey and a new controlled candidate remain unrun.
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
