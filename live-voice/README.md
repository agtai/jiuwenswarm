# JiuwenSwarm Live Voice knowledge base

This directory is the Git-tracked handoff for the Live Voice feature. It separates lightweight continuation material from complete design, validation, and historical records so a new Codex session can resume quickly without losing source information.

## Minimum reading for every task

1. Read the repository root `AGENTS.md`.
2. Read [STATUS.md](STATUS.md) for the only authoritative current state and next slice.
3. Use the routing table below; do not read the entire corpus by default.

The short/full distinction and mandatory/conditional distinction are independent: a short file can be conditionally read, and a full file can become mandatory when its subject is in scope.

## Task routing

| Task | Read after this file and `STATUS.md` |
|---|---|
| Ordinary module implementation or bug fix | Relevant source/tests, the applicable track and risk tier in the [roadmap](roadmap/POST_V0_DELIVERY_ROADMAP.md), and relevant entries in [decisions](decisions/DECISIONS.md) |
| Documentation structure or documentation update | [DOCUMENTATION_RULES.md](DOCUMENTATION_RULES.md) before editing |
| Minimum-intervention/autonomous execution, local Git approval exception, or user-intervention boundary | Root `AGENTS.md`, D-063 in [decisions](decisions/DECISIONS.md), the active execution packet, and current STATUS |
| Product composition, trusted authority, P1/P2/P3 adapter wiring, route truth, shared-file ownership, or cumulative smoke | [Product composition Gate 0](roadmap/PRODUCT_COMPOSITION_GATE_0_2026-08-06.md), [first Alpha product integration review](ALPHA_PRODUCT_INTEGRATION_REVIEW_2026-08-07.md), [Wave A+B integration review](ALPHA_WAVE_AB_INTEGRATION_REVIEW_2026-08-07.md), [Wave C integration review](ALPHA_WAVE_C_INTEGRATION_REVIEW_2026-08-07.md), [post-Wave-C integration review](ALPHA_POST_WAVE_C_INTEGRATION_REVIEW_2026-08-07.md), full solution, ACG, relevant decisions/package reviews, actual source/tests, and current STATUS |
| Alpha parallel execution, ownership, integration lease, Wave A+B implementation history, or review handoff | Frozen [Alpha Wave A+B execution packet](roadmap/ALPHA_WAVE_AB_EXECUTION_2026-08-07.md), [Wave A+B integration review](ALPHA_WAVE_AB_INTEGRATION_REVIEW_2026-08-07.md), [Alpha parallel execution plan](roadmap/ALPHA_PARALLEL_EXECUTION_2026-08-06.md), D-060/D-061/D-062/D-063, the relevant package route above, actual source/tests, and current STATUS |
| Wave C dependency-backed implementation, post-Wave-C readiness/sequence closure, environment preflight, external-dependency choice, or acceptance preparation | Frozen [Alpha Wave C execution packet](roadmap/ALPHA_WAVE_C_EXECUTION_2026-08-07.md), [Wave C integration review](ALPHA_WAVE_C_INTEGRATION_REVIEW_2026-08-07.md), [post-Wave-C integration review](ALPHA_POST_WAVE_C_INTEGRATION_REVIEW_2026-08-07.md), [Wave A+B integration review](ALPHA_WAVE_AB_INTEGRATION_REVIEW_2026-08-07.md), [Alpha parallel execution plan](roadmap/ALPHA_PARALLEL_EXECUTION_2026-08-06.md), Product composition Gate 0, D-046/D-053/D-060/D-061, the relevant package route, actual source/tests, and current STATUS |
| Long-term architecture, P1/P2/P3 boundary, protocol, ownership, cancellation, durability, production acceptance | Complete [full solution snapshot](architecture/FULL_SOLUTION_2026-07-30.md), accepted [Architecture Contract Gate](architecture/ARCHITECTURE_CONTRACT_GATE_V1.md), relevant decisions, and roadmap |
| V0 reproduction or regression acceptance | [V0 acceptance](validation/V0_ACCEPTANCE.md), [E2E runbook](runbooks/E2E_RUNBOOK.md), [showcase](demo/DEMO_SHOWCASE.md), and immutable [V0 evidence](evidence/V0_20260802_ee2896a4.md) |
| Week 2 cumulative Demo implementation or acceptance | D-071 in [decisions](decisions/DECISIONS.md), current [Integrated Demo acceptance](validation/INTEGRATED_DEMO_ACCEPTANCE.md), [Integrated showcase](demo/INTEGRATED_SHOWCASE.md), [E2E runbook](runbooks/E2E_RUNBOOK.md) section 7.1, [W2 source-candidate review](D90_W2_INTEGRATED_DEMO_REVIEW_2026-08-08.md), [P3 terminal replay and automated validation review](D100_P3_TERMINAL_REPLAY_VALIDATION_READY_2026-08-11.md), current [manual product acceptance record](D103_W2_UNSIGNED_MANUAL_PRODUCT_ACCEPTANCE_2026-08-11.md), and STATUS. The [90% Demo packet](roadmap/DEMO_90_EXECUTION_2026-08-07.md), [D101 handoff](D101_W2_NEW_ENVIRONMENT_MANUAL_HANDOFF_2026-08-11.md), [D102 repair](D102_W2_SIGNED_REHEARSAL_FAULT_PROBE_REPAIR_2026-08-11.md) and [portable rehearsal toolkit](../scripts/live_voice/w2_rehearsal/README.md) are historical/optional diagnostics; their signed Gate procedure is retired and must not block acceptance. |
| D-031 task Demo, monitor, project-bound execution or validation | [D-031 implementation review](D031_IMPLEMENTATION_REVIEW_2026-08-04.md), D-056/D-057, [project-bound evidence](evidence/D031_20260805_PROJECT_BOUND.md), [E2E runbook](runbooks/E2E_RUNBOOK.md), relevant task/scheduler/Code Agent source and tests, and current STATUS |
| Integrated Web Alpha acceptance (`W3/W4` delivery windows, not current calendar promises) | [Alpha acceptance](validation/ALPHA_ACCEPTANCE.md), D-055, full solution, ACG, [Web Alpha delivery matrix](roadmap/WEB_ALPHA_DELIVERY_MATRIX_2026-08-05.md), roadmap, runbook, and current STATUS |
| AIO-B browser audio integration, regression, or Chrome evidence | [AIO-B/X-WEB implementation review](AIO_B_X_WEB_IMPLEMENTATION_REVIEW_2026-08-05.md), D-058, ACG, [Web Alpha delivery matrix](roadmap/WEB_ALPHA_DELIVERY_MATRIX_2026-08-05.md), relevant frontend source/tests, and current STATUS |
| CR-B runtime loop, presentation ledger, barge-in, cancel reconciliation, or effect outbox | [CR-B runtime implementation review](CR_B_RUNTIME_IMPLEMENTATION_REVIEW_2026-08-05.md), ACG §§3–7 and 10–15, [Web Alpha delivery matrix](roadmap/WEB_ALPHA_DELIVERY_MATRIX_2026-08-05.md), relevant server/frontend source/tests, and current STATUS |
| AB-B dispatch, WorkProgress v2, ContextRef, Agent-event provenance, or output backpressure | [AB-B/WorkProgress implementation review](AB_B_WORK_PROGRESS_IMPLEMENTATION_REVIEW_2026-08-05.md), ACG §§3–10 and 14–15, [Web Alpha delivery matrix](roadmap/WEB_ALPHA_DELIVERY_MATRIX_2026-08-05.md), relevant shared/server/frontend source/tests, and current STATUS |
| P2 real Agent/Harness route, canonical round events, exact round cancel, formal history seam, atomic dispatch reservation, or retained shutdown | [frozen P2 interface Task Packet](roadmap/P2_REAL_AGENT_CR_INTERFACE_TASK_PACKET_2026-08-05.md), D-059, CR-B/AB-B reviews, ACG §§3–8 and 10–15, the real Agent facade/runtime source and tests, and current STATUS |
| P3alpha formal Task Core, durable outbox, project Code Agent Executor, reconciliation, or task policy | [P3alpha backend implementation review](P3ALPHA_REPLACEMENT_REVIEW_2026-08-05.md), ACG §§3–10 and 14–15, D-045/D-046/D-047/D-053/D-056/D-057, relevant formal task source/tests, and current STATUS |
| Post-V0 sequencing or the next development slice | [roadmap](roadmap/POST_V0_DELIVERY_ROADMAP.md), [Web Alpha delivery matrix](roadmap/WEB_ALPHA_DELIVERY_MATRIX_2026-08-05.md), and relevant decisions |
| Week 1 package history, regression work, or execution-model history | Historical [Week 1 execution packages](roadmap/WEEK_1_EXECUTION_PACKAGES_2026-08-03.md), applicable execution/review decisions D-052/D-053/D-060/D-061, the package's target source/tests, consumed ACG sections, current STATUS, and the actual diff/evidence; Week 1 is complete and this dated plan is not the current queue |
| Historical Sol module design or an implementation return-to-Sol review | Frozen [Sol module pre-reviews](SOL_MODULE_PRE_REVIEWS_2026-08-03.md), the actual diff/tests, current STATUS, and the applicable decision/roadmap contract |
| Demo shortcuts or why V0 differs from production | [two-week demo archive](archive/TWO_WEEK_DEMO.md); treat it as historical design/ledger, not current status |
| Old stash/foundation forensics only | [Post-V0 stash archive](archive/POST_V0_STASH_HANDOFF.md); never reconstruct or apply its machine-local stash during normal recovery |

Start with the named sections above. Expand reading only when Git, STATUS, code or decisions conflict, or when the task crosses authority, protocol, durability or release boundaries.

## Fast resume and verification modes

- **Local Orientation:** run `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/live_voice_snapshot.ps1` from the repository. It does not fetch, pull, test or build; add `-DeepCandidates` only for candidate integration or forensics.
- **Remote Orientation:** add `-Remote` only when remote state matters. It fetches the configured upstream branch and reports divergence; it never pulls.
- **Update:** use `git pull --ff-only` only when the user explicitly asks to update and the worktree is safe. It is not part of Orientation.
- **Affected verification:** run only routed focused checks and affected regressions. Keep model output compact and retain complete failure logs in a machine-local temporary artifact.
- **Acceptance verification:** follow the applicable D-046/D-053 risk tier, run affected automated positive/negative/flag-off/regression checks, then complete the applicable human product journey once under D-071. Keep failure logs private and sanitized; no signed evidence bundle or Replacement Ledger is required.

## Document roles

| Path | Role |
|---|---|
| `STATUS.md` | Mutable state, verified facts, known gaps, and next concrete slice |
| `SOL_MODULE_PRE_REVIEWS_2026-08-03.md` | Frozen detailed D-031/ACG/CR-A/SR-A/SS-A/TC-A Sol design record; not current status or execution order |
| `W1_K1_IMPLEMENTATION_REVIEWS_2026-08-03.md` | Dated five-candidate evidence, Sol implementation reviews, and post-commit correction record; STATUS owns current progress |
| `W1_X2_P1B_REVIEW_2026-08-04.md` | Detailed W1-X2/P1B implementation evidence, W1-S3 judgment, three review passes, corrections, and validation gaps |
| `D031_IMPLEMENTATION_REVIEW_2026-08-04.md` | Detailed D-031 minimal monitor boundary, review passes, automated verification, real-service closure and explicit follow-ups |
| `AIO_B_X_WEB_IMPLEMENTATION_REVIEW_2026-08-05.md` | Frozen AIO-B/X-WEB contract, review passes, automated verification and bounded real Chrome evidence; STATUS owns current integration state |
| `CR_B_RUNTIME_IMPLEMENTATION_REVIEW_2026-08-05.md` | Frozen CR-B runtime/presentation contract, review passes, current-branch correction and bounded automated evidence; STATUS owns current integration state |
| `AB_B_WORK_PROGRESS_IMPLEMENTATION_REVIEW_2026-08-05.md` | Detailed shared WorkProgress v2 and AB-B non-blocking runtime boundary, D-032 scenarios, review passes, evidence and real-integration gap |
| `P3ALPHA_REPLACEMENT_REVIEW_2026-08-05.md` | Detailed formal P3alpha backend boundary, current-branch fixes, scenario/review evidence and product-route blockers |
| `ALPHA_PRODUCT_INTEGRATION_REVIEW_2026-08-07.md` | Frozen stock-Web activation/acknowledgement integration, four reviewed lifecycle/durability hardening commits, D-053 closure, cumulative smoke and exact remaining unavailable boundaries; STATUS owns current state |
| `ALPHA_WAVE_AB_INTEGRATION_REVIEW_2026-08-07.md` | Frozen Wave A+B implementation, environment preflight, review fixes, cumulative verification and exact dependency-backed Wave C boundary for tested code `dd637e60`; STATUS owns current Git and next work |
| `ALPHA_WAVE_C_INTEGRATION_REVIEW_2026-08-07.md` | Frozen Wave C dependency preflight, lane outcomes, atomic TaskEvent authority handoff, D-053 closure, cumulative verification and exact retained external blockers for tested code `4d1672ea`; STATUS owns current Git and next work |
| `ALPHA_POST_WAVE_C_INTEGRATION_REVIEW_2026-08-07.md` | Frozen post-Wave-C P2/deployment readiness, P3 sequence closure, D-053 review, cumulative verification and retained external blockers for tested code `83aace72`; STATUS owns current Git and next work |
| `D90_W2_INTEGRATED_DEMO_REVIEW_2026-08-08.md` | Frozen W2 cumulative source candidate, D-053 review closure, cumulative verification, baseline exclusions and historical external Gate boundary for implementation commit `2fdf849a`; D-071/STATUS own current acceptance and next work |
| `D95_P3_D0_ATTEMPT_BINDING_REPAIR_2026-08-08.md` | Tier-3 repair record for the real P3 exact-root failure, lifecycle findings, same-task restart-evidence blocker, machine-private resume facts and the routed implementation checklist; STATUS owns mutable branch state and priority |
| `D98_W2_FINAL_AUTOMATION_ATTEMPT_2026-08-10.md` | Frozen review and one-shot runtime record for source candidate `f93ca5bd`; records source/test closure, the pre-capture `AUDIO_INPUT_GAP_EXCEEDED` stop and the explicit no-retry boundary without claiming Gate credit |
| `D99_P3_ORIGIN_ROUTE_RECONCILIATION_REVIEW_2026-08-11.md` | Source/test review for Agent config retention, bound product errors and authoritative P3 completed/failed origin-panel reconciliation; runtime validation and independent-review limitation remain explicit |
| `D100_P3_TERMINAL_REPLAY_VALIDATION_READY_2026-08-11.md` | Terminal-before-subscription replay and successor-task fencing review plus the passing unsigned one-page/two-epoch P1/P2/P3 validation-ready run; no evidence or Gate credit |
| `D101_W2_NEW_ENVIRONMENT_MANUAL_HANDOFF_2026-08-11.md` | Current clean Git/source handoff, abandoned unsigned local scaffold boundary and mandatory fresh-machine validation/signing/manual-acceptance sequence |
| `D102_W2_SIGNED_REHEARSAL_FAULT_PROBE_REPAIR_2026-08-11.md` | Historical invalid signed-rehearsal boundary and P1 fault-probe repair; D-071 retires its remaining Gate procedure |
| `D103_W2_UNSIGNED_MANUAL_PRODUCT_ACCEPTANCE_2026-08-11.md` | Non-Jabra physical P1/P2 product acceptance, exact real Terminal result, complete audible playout and successor behavior; D-071 makes this reusable product acceptance rather than zero-credit Gate input |
| `LATEST_FOUNDATIONS_D053_REVIEW_2026-08-06.md` | Exact-SHA retained task-evidence index for the four landed AIO-C/CR-C/TC-C/X-OBS bounded foundations; aggregate integration commands remain an explicit limitation and no acceptance/Gate credit is claimed |
| `DOCUMENTATION_RULES.md` | Authority, routing, anti-duplication, and synchronization rules |
| `decisions/DECISIONS.md` | Accepted decisions and their rationale/history |
| `architecture/FULL_SOLUTION_2026-07-30.md` | Dated immutable complete solution snapshot |
| `architecture/ARCHITECTURE_CONTRACT_GATE_V1.md` | Accepted shared v2 identity/event/state/cancel/commit/progress/context contract and conformance boundary |
| `roadmap/POST_V0_DELIVERY_ROADMAP.md` | Logical delivery windows, target scope/order, automated-plus-human acceptance, risk-proportional closure and the D-060/D-061/D-062 adaptive execution model; calendar timing is not frozen |
| `roadmap/WEEK_1_EXECUTION_PACKAGES_2026-08-03.md` | Completed Week 1 historical priority/dependency/boundary plan; its package contracts remain reference material, not the current queue |
| `roadmap/WEB_ALPHA_DELIVERY_MATRIX_2026-08-05.md` | Dated stable package map from freeze-date Demo/fallback predecessors to formal Web Alpha owners, dependencies, target windows, and acceptance links; STATUS owns mutable progress |
| `roadmap/P2_REAL_AGENT_CR_INTERFACE_TASK_PACKET_2026-08-05.md` | Frozen D-059 execution contract for the real P2 Agent/Harness authority, cancellation, history, admission and shutdown seam; STATUS owns mutable progress |
| `roadmap/PRODUCT_COMPOSITION_GATE_0_2026-08-06.md` | Frozen authority/Adapter interfaces, five-state route truth, file ownership, default-off rules, integration order and cumulative smoke matrix |
| `roadmap/ALPHA_PARALLEL_EXECUTION_2026-08-06.md` | Historical D-060 four-lane decomposition whose file ownership, integration lease and review handoff remain reusable; D-062 and the current packet own adaptive scheduling |
| `roadmap/DEMO_90_EXECUTION_2026-08-07.md` | Historical W2 Gate-era task contract; D-071 and current acceptance/STATUS supersede its scoring, signature and immutable-evidence exit rules |
| `roadmap/ALPHA_WAVE_AB_EXECUTION_2026-08-07.md` | Frozen completed Wave A+B task contract: seven logical Sessions, lane oracles, dependency handoff, final manifest, review concurrency and cumulative-smoke recovery rules; the integration review owns results and STATUS owns mutable progress |
| `roadmap/ALPHA_WAVE_C_EXECUTION_2026-08-07.md` | Frozen Wave C dependency-backed task contract: synchronized baseline, lane ownership, pre-implementation oracles, external-dependency outcomes, review/lease handoff and cumulative-smoke recovery; STATUS owns mutable progress and the eventual integration review owns results |
| `validation/`, `runbooks/`, `demo/`, `evidence/` | V0/Integrated Demo/Alpha acceptance, runtime procedure, presentation scripts, and immutable run evidence |
| `archive/` | Historical plans and recovery context; never the current-state authority |

## Fresh-clone continuation

```powershell
git fetch origin hx/0803_live_voice
git switch --track -c hx/0803_live_voice origin/hx/0803_live_voice
git status --short --branch
git rev-parse HEAD
git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}'
git rev-list --left-right --count 'HEAD...@{upstream}'
```

If the local branch already exists, use the Local or Remote Orientation mode above first. Fast-forward pull only when the task explicitly requires an update. Never discard local work merely to match this guide.

Git restores source, decisions, tests, and this continuation state. It does not restore model keys/API bases, local JiuwenSwarm configuration, `JIUWENSWARM_DATA_DIR`, project registration, browser profile/permissions, microphone/headset selection, or network/provider availability. Re-establish those private conditions and complete the relevant automated and human acceptance checks before claiming runtime parity.

## Conflict priority

1. User's latest explicit instruction.
2. Checked-out Git source and tests.
3. `STATUS.md` for mutable state.
4. Accepted decisions and the roadmap for intended behavior.
5. Full design snapshot.
6. Archive documents.

A mismatch must be reported and corrected at its authoritative source; do not copy the same mutable fact into several documents.
