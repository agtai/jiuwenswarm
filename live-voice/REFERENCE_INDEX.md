# Live Voice conditional reference index

> **Do not read this file during ordinary bootstrap.** Open it only when the
> current task is historical, forensic, a regression against an older milestone,
> or STATUS/source evidence explicitly routes here. Current state remains in
> [STATUS.md](STATUS.md).

## Milestone and operating records

| Need | Read |
|---|---|
| Disputed pre-cleanup state, closed batch, old acceptance count or superseded 2026-09-03 handoff | Only the implicated section of the [frozen status snapshot](STATUS_HISTORY_20260903.md); its instructions and priorities are historical, and current conclusions remain in STATUS |
| V0 reproduction/regression | [V0 acceptance](validation/V0_ACCEPTANCE.md), [V0 showcase](demo/DEMO_SHOWCASE.md), relevant [runbook](runbooks/E2E_RUNBOOK.md) sections and immutable [V0 evidence](evidence/V0_20260802_ee2896a4.md) |
| W2 implementation/acceptance regression | D-071/D-072, [W2 acceptance](validation/INTEGRATED_DEMO_ACCEPTANCE.md), [W2 showcase](demo/INTEGRATED_SHOWCASE.md), [D105 product acceptance](D105_W2_PRODUCT_ACCEPTANCE_2026-08-11.md), then only the implicated review below |
| W3 develop rebaseline/deletion intent | [D107 migration review](D107_W3_DEVELOP_REBASELINE_MIGRATION_2026-08-12.md), D-073, actual source/tests |
| D-031 compatibility task | [D031 review](D031_IMPLEMENTATION_REVIEW_2026-08-04.md), D-056/D-057, [project-bound evidence](evidence/D031_20260805_PROJECT_BOUND.md), relevant scheduler/Agent source/tests and runbook section 7.4 |
| Environment/runtime execution | Only the applicable historical-boundary or current-candidate section of the [E2E runbook](runbooks/E2E_RUNBOOK.md); never use a W2/V0 script to sign the current candidate |
| 2026-08-17 Post-Alpha hands-free Demo defects | [completed defect-discovery record](evidence/POST_ALPHA_DEMO_20260817_95b26308_WORKTREE.md), then current [STATUS](STATUS.md) and only the implicated D119/source boundary |
| Current controlled product-candidate acceptance | [product-readiness contract](validation/PRODUCT_READINESS_ACCEPTANCE.md), [complete human Journey](demo/PRODUCT_READINESS_SHOWCASE.md), current [STATUS](STATUS.md) and only the required runbook sections |

<a id="september-repair-records"></a>

## September repair records

These records replace the chronological repair narratives formerly embedded in
STATUS. Open only the implicated boundary. Their old execution instructions,
worker assignments, deployment settings and test totals are exact-run history;
current scope and acceptance remain in STATUS. The pre-cleanup text is retained
in Git (STATUS at `234b1517`), not a second mutable status file.

| Need / boundary | Conditional evidence |
|---|---|
| Earlier human failures and six-hour repair | [Human-session diagnosis](reviews/REALTIME_HUMAN_ACCEPTANCE_DIAGNOSIS_20260908.md), [repair scope](reviews/REALTIME_SIX_HOUR_REPAIR_20260908.md), [acceptance including failures](reviews/REALTIME_SIX_HOUR_ACCEPTANCE_20260908.md), [same-frame supply measurements](evidence/REALTIME_SUPPLY_DIAGNOSTICS_20260908.md) |
| Original Task speech and file preservation | [D-122 source retention](decisions/DECISIONS.md#d-122-retain-original-native-task-speech-independently-of-model-proposals), [D-123 file effects](decisions/DECISIONS.md#d-123-bind-native-task-file-effects-before-writes-and-across-recovery); scoped successful samples do not erase earlier preservation failures |
| Six-point acceptance repairs and startup | [Repair packet](reviews/REALTIME_ACCEPTANCE_REPAIRS_20260907.md), [startup repair](reviews/REALTIME_NATIVE_STARTUP_REPAIR_20260907.md), [candidate/user acceptance record](reviews/REALTIME_ACCEPTANCE_CANDIDATE_20260907.md) |
| Shenzhen routing, starvation and receipts | [Diagnosis](reviews/SHENZHEN_REHEARSAL_DIAGNOSIS_20260907.md), [scoped repairs](reviews/SHENZHEN_REPAIRS_20260907.md); use the [current human script](demo/PRODUCT_READINESS_SHOWCASE.md#4-current-shenzhen-business-trip-showcase) only for an applicable rehearsal |
| P0–P9 optimization decisions | [Full packet](reviews/REALTIME_OPTIMIZATION_FULL_20260907.md), [first bounded batch](reviews/REALTIME_OPTIMIZATION_20260907.md); P3/P6/P9 include retain/reject decisions, not achieved latency targets |
| Native business/work composition | [Conversational execution](reviews/NATIVE_CONVERSATION_EXECUTION_20260906.md) |
| Delegate return, recovery and notification ownership | [Delegate client repair](reviews/NATIVE_DELEGATE_CLIENT_REPAIR_20260906.md), [session lifecycle repair](reviews/NATIVE_SESSION_LIFECYCLE_REPAIR_20260906.md) |
| Provider transcript metadata | [Native schema compatibility](reviews/NATIVE_EVENT_SCHEMA_REPAIR_20260906.md) |
| Generated text, Task UI and foreground interruption | [Rehearsal repair](reviews/NATIVE_REHEARSAL_REPAIR_20260906.md), [foreground repair](reviews/NATIVE_FOREGROUND_REPAIR_20260906.md), [earlier Demo repairs](reviews/DEMO_THREE_REPAIRS_20260906.md) |
| Headset interruption and generation defaults | [Physical barge-in gaps](evidence/VAD_PLAYOUT_ACCEPTANCE_AND_BARGE_IN_DIAGNOSIS_20260904.md), [formal default change](reviews/FORMAL_GENERATION_DEFAULT_20260905.md); verified-headset profile evidence does not cover speakers/Bluetooth, and old settings are not the current Native runtime configuration |
| Answer hardcodes and spoken-answer ownership | [Retirement](reviews/ANSWER_HARDCODE_RETIREMENT_20260905.md), [D-115 answer ownership](reviews/SPOKEN_ANSWER_VERIFICATION_20260905.md) |
| Agent streaming, SDK and project serialization | [Stream lifecycle](reviews/SPECULATIVE_STREAM_LIFECYCLE_20260905.md), [OpenAI AgentModel integration](reviews/OPENAI_AGENTMODEL_INTEGRATION_20260905.md), [serial project Task handoff](reviews/PROJECT_TASK_HANDOFF_20260905.md) |
| Profiling/export and speech lifetime | [Profiling deployment](evidence/DEMO_PROFILING_DEPLOYMENT_20260904.md), [speech lifetime](evidence/SPEECH_LIFECYCLE_REPAIR_20260904.md); current export commands belong to [runbook §7.7](runbooks/E2E_RUNBOOK.md#77-普通-demo-的性能记录与故障报告) |
| Adjustment application and notification policies | [Control repair](reviews/REHEARSAL_REPAIR_20260905.md), [running silence](reviews/RUNNING_NOTIFICATION_POLICY_20260905.md), [cancellation silence](reviews/CANCELLED_NOTIFICATION_POLICY_20260906.md), [rehydration/origin follow-up](reviews/REHEARSAL_RECOVERY_FOLLOWUP_20260905.md) |
| Segmentation, literal content and artifact quality | [Segmentation diagnostics](evidence/SEGMENT_AND_DIALOGUE_DIAGNOSTICS_20260904.md), [artifact quality including failures](evidence/ARTIFACT_QUALITY_REHEARSAL_CHECK_20260903.md) |
| Project-home startup and memory | [Home entry](evidence/HOME_SESSION_VOICE_START_20260903.md), [real voice/memory follow-up](evidence/PROJECT_HOME_REAL_VOICE_AND_MEMORY_REPAIR_20260903.md) |

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
| Unified hands-free baseline | [D118 pre-D119 candidate snapshot](D118_UNIFIED_HANDS_FREE_LIVE_VOICE_REVIEW_2026-08-16.md) |
| Running adjustment and terminal notification | [D119 candidate-specific frozen review](D119_RUNNING_TASK_ADJUSTMENT_AND_TERMINAL_NOTIFICATION_REVIEW_2026-08-16.md) |
| Complete-P3 historical coverage, source recovery and activation-time reuse | [2026-08-18 P3 implementation/reuse audit](reviews/P3_IMPLEMENTATION_COVERAGE_AND_HISTORICAL_REUSE_AUDIT_2026-08-18.md) and its [source-asset manifest](reviews/P3_HISTORICAL_SOURCE_ASSET_EXTRACTION_MANIFEST_2026-08-18.md); estimates remain bound to their baseline. [STATUS](STATUS.md) owns current activation; consult only implicated sections of the [preparatory P3 contract](roadmap/FULL_P3_EXECUTION_PLAN.md), interpreted with later accepted decisions. |
| Code duplication and convergence timing | [2026-08-17 duplicate-code audit](reviews/CODE_DUPLICATION_AND_RETIREMENT_AUDIT_2026-08-17.md) |
| Removable branch content, re-homing and final-merge cleanup | [2026-08-17 branch-retirement audit](reviews/BRANCH_CONTENT_RETIREMENT_AUDIT_2026-08-17.md) |
| Removable/superseded documents and authority-preserving deletion batches | [2026-08-17 documentation-retirement audit](reviews/DOCUMENT_RETIREMENT_AUDIT_2026-08-17.md) |

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
- Alpha automated verification and its historical environment block: [D110](D110_ALPHA_AUTOMATED_VERIFICATION_AND_ENVIRONMENT_BLOCK_2026-08-12.md). Its §6 records the gateway test path that earlier verification runs missed; it does not define current capability status.
- Stable package relationships: [Web Alpha matrix](roadmap/WEB_ALPHA_DELIVERY_MATRIX_2026-08-05.md).
- Completed Week 1: [execution packages](roadmap/WEEK_1_EXECUTION_PACKAGES_2026-08-03.md) and [Sol pre-reviews](SOL_MODULE_PRE_REVIEWS_2026-08-03.md).
- Historical parallel packets: [Alpha parallel plan](roadmap/ALPHA_PARALLEL_EXECUTION_2026-08-06.md), [Wave A+B packet](roadmap/ALPHA_WAVE_AB_EXECUTION_2026-08-07.md), [Wave C packet](roadmap/ALPHA_WAVE_C_EXECUTION_2026-08-07.md), [W2 90% packet](roadmap/DEMO_90_EXECUTION_2026-08-07.md).
- Removed superseded product/stash material remains in Git history and never overrides current source, STATUS or accepted decisions.

## Fresh-clone recovery

Remote names and publication state are repository-local Git facts. Do not
assume `agtai`, `origin` or any other fixed name. First inspect configured
remotes and remote-tracking refs, verify the selected URL, and remember that a
fresh clone can recover only commits already published to that ref. Local-ahead
commits require a separately authorized remote update before another clone can
retrieve them.

```powershell
git remote -v
git branch -r --list "*/hx/0812_live_voice_w3"
$liveVoiceRemote = Read-Host "Verified remote name"
git remote get-url $liveVoiceRemote
git fetch $liveVoiceRemote hx/0812_live_voice_w3
git switch --track -c hx/0812_live_voice_w3 "$liveVoiceRemote/hx/0812_live_voice_w3"
git status --short --branch
git rev-parse HEAD
git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}'
git rev-list --left-right --count 'HEAD...@{upstream}'
```

The Git commands above and current [STATUS](STATUS.md) are the only current
orientation path. The retired Resume-capsule/Verified-code-base helper has been
removed; its historical disposition remains in the
[2026-08-17 cleanup audit](reviews/BRANCH_CONTENT_RETIREMENT_AUDIT_2026-08-17.md).
Update a worktree with `git pull --ff-only` only when the user explicitly
requests an update and the worktree is safe.
