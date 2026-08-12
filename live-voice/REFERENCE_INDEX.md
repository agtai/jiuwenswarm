# Live Voice conditional reference index

> **Do not read this file during ordinary bootstrap.** Open it only when the
> current task is historical, forensic, a regression against an older milestone,
> or STATUS/source evidence explicitly routes here. Current state remains in
> [STATUS.md](STATUS.md).

## Milestone and operating records

| Need | Read |
|---|---|
| V0 reproduction/regression | [V0 acceptance](validation/V0_ACCEPTANCE.md), [V0 showcase](demo/DEMO_SHOWCASE.md), relevant [runbook](runbooks/E2E_RUNBOOK.md) sections and immutable [V0 evidence](evidence/V0_20260802_ee2896a4.md) |
| W2 implementation/acceptance regression | D-071/D-072, [W2 acceptance](validation/INTEGRATED_DEMO_ACCEPTANCE.md), [W2 showcase](demo/INTEGRATED_SHOWCASE.md), [D105 product acceptance](D105_W2_PRODUCT_ACCEPTANCE_2026-08-11.md), then only the implicated review below |
| W3 develop rebaseline/deletion intent | [D107 migration review](D107_W3_DEVELOP_REBASELINE_MIGRATION_2026-08-12.md), D-073, actual source/tests |
| D-031 compatibility task | [D031 review](D031_IMPLEMENTATION_REVIEW_2026-08-04.md), D-056/D-057, [project-bound evidence](evidence/D031_20260805_PROJECT_BOUND.md), relevant scheduler/Agent source/tests and runbook section 7.4 |
| Environment/runtime execution | Only the applicable milestone section of the [E2E runbook](runbooks/E2E_RUNBOOK.md); never use a W2/V0 script to sign Alpha |

## Module and integration history

| Boundary | Primary frozen reference |
|---|---|
| AIO/browser | [AIO-B/X-WEB review](AIO_B_X_WEB_IMPLEMENTATION_REVIEW_2026-08-05.md) |
| CR/presentation/cancel | [CR-B review](CR_B_RUNTIME_IMPLEMENTATION_REVIEW_2026-08-05.md) |
| AB/WorkProgress | [AB-B review](AB_B_WORK_PROGRESS_IMPLEMENTATION_REVIEW_2026-08-05.md) |
| Formal P1 Speech | [P1 Speech review](P1_FORMAL_SPEECH_IMPLEMENTATION_REVIEW_2026-08-05.md) |
| P2 real Agent/Harness | [P2 interface packet](roadmap/P2_REAL_AGENT_CR_INTERFACE_TASK_PACKET_2026-08-05.md) and [blocker review](P2_REAL_AGENT_CR_BLOCKER_REVIEW_2026-08-05.md) |
| P3alpha Core/Executor | [P3alpha review](P3ALPHA_REPLACEMENT_REVIEW_2026-08-05.md) and [P3 auth review](P3_AUTH_COMPOSITION_IMPLEMENTATION_REVIEW_2026-08-05.md) |
| X-OBS | [X-OBS review](X_OBS_IMPLEMENTATION_REVIEW_2026-08-05.md) |
| X-E2E/X-WEB | [X-E2E/X-WEB review](X_E2E_X_WEB_IMPLEMENTATION_REVIEW_2026-08-05.md) |
| Product composition | [Product Composition Gate 0](roadmap/PRODUCT_COMPOSITION_GATE_0_2026-08-06.md), then only the implicated integration record |

The dated Alpha integration sequence is
[first product integration](ALPHA_PRODUCT_INTEGRATION_REVIEW_2026-08-07.md) →
[Wave A+B](ALPHA_WAVE_AB_INTEGRATION_REVIEW_2026-08-07.md) →
[Wave C](ALPHA_WAVE_C_INTEGRATION_REVIEW_2026-08-07.md) →
[post-Wave-C](ALPHA_POST_WAVE_C_INTEGRATION_REVIEW_2026-08-07.md).
Read only the record that owns the regression or source boundary being examined.

## W2 recovery and diagnostic history

- Source candidate: [D90](D90_W2_INTEGRATED_DEMO_REVIEW_2026-08-08.md).
- Browser recovery: [D94](D94_BROWSER_REFRESH_DUPLEX_RECOVERY_REVIEW_2026-08-08.md).
- P3 exact-root repair: [D95](D95_P3_D0_ATTEMPT_BINDING_REPAIR_2026-08-08.md).
- P3 origin/replay/refresh: [D99](D99_P3_ORIGIN_ROUTE_RECONCILIATION_REVIEW_2026-08-11.md), [D100](D100_P3_TERMINAL_REPLAY_VALIDATION_READY_2026-08-11.md), [D104](D104_P3_REFRESH_RECOVERY_AND_W2_ACCEPTANCE_CONTINUATION_2026-08-11.md).
- Physical product records: [D103](D103_W2_UNSIGNED_MANUAL_PRODUCT_ACCEPTANCE_2026-08-11.md), [D105](D105_W2_PRODUCT_ACCEPTANCE_2026-08-11.md).
- Retired signed-Gate history: [D98](D98_W2_FINAL_AUTOMATION_ATTEMPT_2026-08-10.md), [D101](D101_W2_NEW_ENVIRONMENT_MANUAL_HANDOFF_2026-08-11.md), [D102](D102_W2_SIGNED_REHEARSAL_FAULT_PROBE_REPAIR_2026-08-11.md), [D106](D106_W2_SIGNED_GATE_CODE_REMOVAL_REVIEW_2026-08-11.md). These do not define a current completion path.

## Planning and governance history

- Stage/governance audits: [D108](D108_PROJECT_PROGRESS_AND_GOVERNANCE_REVIEW_2026-08-12.md), [D109](D109_STAGE_MODULE_DOCUMENTATION_SYNC_2026-08-12.md).
- Alpha automated verification and the environment block that keeps S6 open: [D110](D110_ALPHA_AUTOMATED_VERIFICATION_AND_ENVIRONMENT_BLOCK_2026-08-12.md). Its §6 records the gateway test path that earlier verification runs missed.
- Stable package relationships: [Web Alpha matrix](roadmap/WEB_ALPHA_DELIVERY_MATRIX_2026-08-05.md).
- Completed Week 1: [execution packages](roadmap/WEEK_1_EXECUTION_PACKAGES_2026-08-03.md) and [Sol pre-reviews](SOL_MODULE_PRE_REVIEWS_2026-08-03.md).
- Historical parallel packets: [Alpha parallel plan](roadmap/ALPHA_PARALLEL_EXECUTION_2026-08-06.md), [Wave A+B packet](roadmap/ALPHA_WAVE_AB_EXECUTION_2026-08-07.md), [Wave C packet](roadmap/ALPHA_WAVE_C_EXECUTION_2026-08-07.md), [W2 90% packet](roadmap/DEMO_90_EXECUTION_2026-08-07.md).
- Superseded product/stash material lives under `archive/` and never overrides current source, STATUS or accepted decisions.

## Fresh-clone recovery

```powershell
git fetch origin hx/0812_live_voice_w3
git switch --track -c hx/0812_live_voice_w3 origin/hx/0812_live_voice_w3
git status --short --branch
git rev-parse HEAD
git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}'
git rev-list --left-right --count 'HEAD...@{upstream}'
```

Use `scripts/live_voice_snapshot.ps1` for read-only local orientation. Add its
remote option only when remote state matters; update with `git pull --ff-only`
only when the user explicitly requests an update and the worktree is safe.
