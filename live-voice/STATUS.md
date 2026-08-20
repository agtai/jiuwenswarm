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
- **P3-G0 status:** **PASS — AUTHORITATIVE P3 FOUNDATION; CONTROLLED
  PRODUCT-READINESS REMAINS FAIL.** [D-086](decisions/DECISIONS.md) accepts the
  sequencing risk and removes the failed P1/P2 hands-free condition as a P3-1
  Gate without changing the immutable candidate result.
- **Current highest priority:** execute P3-2 complete command, adjustment and
  successor-revision semantics on the accepted P3-1 canonical Task model. The
  deferred P1/P2 issue is recorded in the
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
| Audio Device & browser I/O | **PARTIAL; deferred from the P3-1 Gate.** Browser capture/playout, lifecycle fencing and dedicated media wiring exist. `f24dd17d` twice entered `AUDIO_CAPTURE_DURATION_EXCEEDED` after TTS; the `P1/P2-T1` packet has since repaired the rotation mechanism (decaying local activity, utterance-budget bound, sanitized capture diagnostics) with source/affected automated evidence in the [repair record](evidence/P1_T1_POST_TTS_CAPTURE_ROTATION_REPAIR_2026-08-19.md) — no physical credit | Physically verify the repaired post-TTS/overlap/idle rotation per the [deferred record](evidence/P1_P2_POST_TTS_CAPTURE_CONTINUATION_DEFERRED_20260819.md); device/permission recovery; AEC/NS/AGC and double-talk; measured first-frame/loss/stop targets | P1/P2 completion before controlled-candidate/feature-complete acceptance; not a P3-1 dependency |
| Speech Recognition | **PARTIAL.** Two real microphone finals reached the Agent, but each post-TTS failure also produced streaming-route abort, cleanup timeout and unacknowledged cancel | Exact capture/provider-speech-start attribution, robust fallback/cancel, Provider-neutral configuration, fixed accuracy/latency corpus and broader device/network validation | Audio I/O, media route and benchmark owner |
| Speech Synthesis | **PARTIAL.** Streaming/Batch TTS, browser playout, response ownership and ACK paths exist | Provider-neutral configuration, first-audio/underrun/pronunciation targets and complete stale/cancel recovery | Conversation Runtime ownership and Audio I/O stop confirmation |
| Realtime Media | **PARTIAL; deferred from the P3-1 Gate.** Dedicated transport, media registration and presentation ACK worked, but repeated post-TTS capture rotation did not preserve a usable media loop; the rotation seam is now repaired at source under `P1/P2-T1` with automated evidence only | Physically verify the repaired rotation/cancel seam; backpressure/load targets; drop/reorder/corruption/reconnect matrix; stable diagnostics across repeated recovery | Audio I/O plus Conversation Runtime; cumulative real network/device verification |
| Conversation Runtime | **PARTIAL.** committed-input fencing, generation ownership, ACK/history projection, Exit fencing and playout-time barge-in exist; manual retry admitted a second turn | Automatic continuation without recurrent recovery failure; **hands-free speech during Agent generation cannot currently interrupt or replace that response and remains explicit follow-up work**; complete `ask_user` voice loop and cross-load arbitration | Media, Interaction Intelligence, Agent Bridge and presentation regressions |
| Interaction Intelligence | **PARTIAL.** VAD/EOT and bounded dialogue/background routing exist for the controlled journey | General natural-language routing, false endpoint/interruption and echo/double-talk evaluation, language/config generalization; Native model-level duplex remains optional | Streaming Speech plus Runtime; measured golden corpus |
| Agent Bridge and dialogue truth | **PARTIAL.** Real Agent dialogue/tools and bounded response/progress integration exist | Non-blocking progress provenance, strict Task-truth isolation, bounded result-context reservation and unconstrained reread prevention | Runtime, Task/Event truth and affected text-path regressions |
| Task Control Core and Store | **PARTIAL overall; P3-1 PASS; P3-2 contract frozen.** SQLite schema v4, multiple non-terminal Tasks, explicit create/revision lineage, shared transition validation, addressed list/events/result/adjust behavior and fail-closed durable-authority reconstruction passed current-source Tier-3 review with no remaining P1/P2. D-087 now freezes the P3-2 six-item command contract without implementation credit | Implement P3-2 closed command dispositions, pre-dispatch update, truthful unsupported controls and successor creation; then P3-5 unread/presentation ACK, P3-6 target disambiguation, final legacy-fake relocation and one product Task model | Executor status resolution, Voice–Task Bridge and restart/concurrency matrix; exact evidence in the [P3-1 review](reviews/P3_1_CANONICAL_MULTI_TASK_IMPLEMENTATION_REVIEW_2026-08-19.md) and [P3-2 contract freeze](reviews/P3_2_P3_5A_ACTIVATION_PREPARATION_2026-08-18.md) |
| Executor & Durability | **PARTIAL.** Direct isolated Code Executor, lease/journal, terminalization and recovery foundations exist and are statically closed on the audited source | Clean physical re-verification of Agent-return → validation → application → result → terminalization; bounded timeout/orphan handling; capability selection; supported D1 checkpoint and D2 reconciliation semantics | Highest-priority Tier-3 clean re-verification; D1/D2/capability remain feature-complete scope |
| Voice–Task Bridge | **PARTIAL.** Natural-language create/status/adjust/result paths and durable adjustment delivery exist | General routing, explicit multi-Task targeting, full Task operations, text/voice parity, clarification and zero false truth | Task Core and Executor truth; precision/recall plus zero-side-effect tests |
| Integrated Web product experience | **PARTIAL.** The explicit profile, authenticated route, P2/P3 composition, real foreground Agent text/TTS and manual retry worked; automatic listening failed after both responses. A broader P3-1 diagnostic also reproduced the unchanged mounted Exit/immediate-re-enable presentation-ACK timing failure at 406/407; both remain outside the accepted Core/Store package | Complete P3 controls/projections while preserving profile semantics; later close capture/Exit recovery, truthful queued/running/terminal UX, device/privacy/recovery UX and the cumulative human journey; retire legacy hooks/flags | P3-2 through P3-9 plus deferred P1/P2 completion |
| Observability, benchmark and latency | **PARTIAL overall; additive P3-8A assets PASS.** Trace/correlation foundations now include a bounded content-free SLI calculator, complete declaration-only telemetry privacy profile and source-bound canonical OTel backend codec that reuses the current observability owner's calendar and private-carrier validation. The codec is not product-composed and owns no exporter/backend lifecycle | Compose the codec behind the existing adapter/exporter in the later owning package; add validated backend configuration and exact Task/Attempt/Command/activation/generation/ACK/Executor diagnostics; then execute the [latency optimization plan](roadmap/LATENCY_OPTIMIZATION_PLAN_2026-08-18.md) with a fresh physical baseline, stable EOT/Agent/TTS/first-audible facts, authoritative ACK, formal sentence-level Agent→TTS overlap and fixed-corpus p50/p95 proof | Exact scoped evidence in the [P3-8A review](reviews/P3_8A_OBSERVABILITY_ASSETS_REVIEW_2026-08-19.md); P3-8B composition/retirement after P3-7; fixed corpus/environment and Conversation Runtime/P1 media owners |
| Automated verification and product acceptance | **PARTIAL.** Exact-source G0 affected backend (`916 passed, 2 skipped`), Formal Web (`407/407`), profile tests, builds and static review retain their source-bound credit; P3-1 affected automation/build/static and independent Tier-3 review pass, while its extra full-Web diagnostic is 406/407 on the unchanged deferred Runtime/Web seam. The physical candidate remains FAIL | Run each P3 package's affected evidence; later repair/rerun the P1/P2 seam and complete the clean cumulative Journey, feature-complete matrix, competitor-gap review and independent deep review | Root `TESTING.md`, D-086 risk transfer, current acceptance and exact clean source |
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
   The `P1/P2-T1` packet has since implemented those repair directions with
   source and affected automated evidence in the
   [repair record](evidence/P1_T1_POST_TTS_CAPTURE_ROTATION_REPAIR_2026-08-19.md);
   the physical later-acceptance criteria remain open and grant no candidate
   credit.

The explicit build profile and ordinary-production flag-off behaviour are
source/build/deploy verified. D-086 passes only the P3 expansion prerequisite;
it cannot upgrade the failed candidate or invalidate the historical
exact-source Alpha result.

## Current execution packet

Under the D-060/D-062 bounded multi-package batch form, this STATUS activates
one batch with three child packages: `P3-2` (unchanged, first below),
`P1/P2-T1` (post-TTS capture continuation repair) and `P1/P2-T2` (latency
optimization, delegated owner). Child file sets are disjoint and each child
carries its own owner, risk, dependencies, acceptance and exclusions below.
`STATUS`/`DECISIONS` editing and batch integration remain single-writer.
Integration order: `P1/P2-T1` lands as one production commit before any
`P1/P2-T2` frontend work; `P3-2` integrates independently under its own
owner. `P1/P2-T1` has no dependency on any P3 package (per the D-086 route,
P1/P2 quality proceeds in parallel); `P1/P2-T2` frontend work depends on the
integrated `P1/P2-T1`. Activation grants no implementation credit.

### Batch member P3-2 — complete command semantics (unchanged)

- **Packet:** P3-2 — complete command, adjustment and successor-revision
  semantics.
- **Frozen contract:** [D-087](decisions/DECISIONS.md) and the
  [P3-2/P3-5A Core/Store design and oracle map](reviews/P3_2_P3_5A_ACTIVATION_PREPARATION_2026-08-18.md)
  freeze the P3-2 six-item contract on the accepted P3-1 model. P3-5A remains
  inactive unless STATUS records a separate assignment or bounded multi-package
  batch.
- **Objective:** add one coherent, versioned command model for `update`,
  `provide_input`, capability-truthful `pause/resume/reprioritize` (currently
  unsupported), exact cancel outcomes and explicit successor revision without
  rewriting terminal Task/TaskResult truth.
- **Capability/modules:** Task Control Core/Store own command admission,
  idempotency, event/outbox/result truth and successor creation; the selected
  Executor seam owns only operations backed by a proven capability. Text and
  Voice callers consume the same command results.
- **Risk:** Tier 3 under root `TESTING.md` because the packet changes shared
  command/state/transaction semantics and Executor effects. D-087 keeps the
  Store at schema v4; stop before DDL or before adding a new operation,
  scheduler policy, recovery model or product owner and re-scope that expansion.
- **Included:** immutable command fingerprint and exact scope/target/expected
  state; atomic admission plus outbox/replay facts; accepted/applied/rejected/
  unsupported/conflict/timeout/unknown separation; operation-specific legal
  states and terminal races; ordered adjustments/inputs; capability-truthful
  pause/resume/priority; idempotent successor Task creation with immutable
  predecessor/result preservation.
- **Excluded:** the deferred P1/P2 post-TTS/Exit continuation repair; P3-3
  Executor capability/admission expansion; P3-4 D1/D2 implementation; P3-5
  unread/presentation ACK; generalized Voice targeting/UI work; Production,
  `develop` integration and remote updates.
- **Next action:** write failing Python/TypeScript closed-contract tests for the
  frozen payload/disposition matrix, then implement the schema-v4 Core/Store
  transaction paths in this order: pre-dispatch `task.update`, narrowed
  `task.adjust`/`task.retry` compatibility, zero-effect unsupported controls,
  and one-winner `task.create_successor`.
- **Deliverables:** versioned command/disposition schema and durable transaction
  path; current proven `task.adjust` checkpoint compatibility plus truthful
  unsupported results for controls awaiting P3-3; explicit successor creation;
  positive, negative, boundary, concurrency, restart/idempotency, unsupported
  and zero-effect evidence; complete-diff and independent Tier-3 review;
  synchronized STATUS/evidence.
- **Acceptance:** every declared operation has exact state, target,
  duplicate/conflict, concurrent-terminal, restart and unsupported-capability
  evidence; ordered supported effects apply once; unsupported controls never
  appear successful; successor creation preserves predecessor and result
  byte-for-byte; text and Voice observe the same authoritative result and
  TaskEvent truth.

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
  P3 notes, each dispositioned in the repair record. Physical verification
  remains open per the deferred record.

### Batch member P1/P2-T2 — latency optimization (delegated)

- **Packet:** P1/P2-T2 — execute the
  [latency optimization plan](roadmap/LATENCY_OPTIMIZATION_PLAN_2026-08-18.md)
  in its §7 delivery order (measurement contract and fresh baseline first)
  under a delegated owner.
- **Constraint:** L1 server-side instrumentation may start immediately; all
  frontend work in `productP1VoiceRoute.ts`/`browserAudioIOAdapter.ts` waits
  for the integrated `P1/P2-T1` commit or explicit coordination. No
  Provider/model/billing change, persistent speech cache, new retention
  policy or raw-audio storage; ideas rejected in the plan's §8 stay rejected.
- **Risk:** per-batch tier under root `TESTING.md`; the pipeline and
  sentence-overlap batches are Tier 3.
- **Acceptance:** per the plan's §§3–7 measured evidence relative to the
  fresh baseline; targets become release gates only after environment, corpus
  and sample size are frozen.

#### T2-L2A — successor-capture ACK must not gate authoritative playout (SOURCE/AUTOMATED REPAIRED; PHYSICAL OPEN, 2026-08-20)

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
  Independent Tier-3 review and the recorded real microphone/speaker
  acceptance remain open; no physical PASS or product-readiness credit is
  claimed.

#### T2-L2B — completed playout receipt must not require early duplex media (SOURCE/AUTOMATED REPAIRED; PHYSICAL OPEN, 2026-08-20)

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
  pre-existing Exit/immediate-re-enable case (414/415). A fresh real Chrome
  audible turn and automatic successor listening remain user validation; no
  physical PASS is claimed.

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
5. Execute P3-2 complete commands and successor revisions. Continue migrating
   each still-applicable historical oracle with its first owning package;
   perform code placement, duplicate consolidation and entrypoint/document
   retirement only after replacement without deleting live coverage. Complete
   P1/P2 quality in parallel with the
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
  activated P3-1; P3-1 now passes its own scoped evidence and activates P3-2. It
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
