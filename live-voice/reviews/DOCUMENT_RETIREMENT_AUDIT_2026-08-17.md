# Live Voice documentation retirement audit — 2026-08-17

> **Frozen inventory and execution record.** The measured audit base is
> `ca9a9d9a3be5f76c4feee980030a1b3ce065b9ab`, relative to the
> `origin/develop` merge base
> `3f3cdbb7f45fdd29e7d03deafa5bca10e363434e`. The inventory also includes
> the current uncommitted documentation reconciliation and review records.
> Current state remains in [STATUS](../STATUS.md). Audit state:
> **ANALYSIS COMPLETE / BATCH A COMPLETE / BATCHES B–C NOT STARTED**.

## 1. Result

Yes. The branch carries substantially more historical process documentation
than the current product and final integration need.

At audit time:

- `live-voice/` contains **91 Markdown files / 16,954 lines**;
- **61** of those files are placed directly in the `live-voice/` root;
- **21** Live Voice documents are outside the transitive link graph rooted at
  `README.md`, `STATUS.md`, `DOCUMENTATION_RULES.md` and
  `REFERENCE_INDEX.md`;
- **14** root-level Live Voice documents have no explicit Markdown inbound
  link;
- there are no byte-identical document duplicates and no high-overlap 5-gram
  pair at the audit threshold. The redundancy is semantic: dated plans,
  reviews, ledgers and evidence repeat implementation state that Git already
  preserves.

With Git history accepted as the recovery mechanism, the audit-time inventory
identified **71 Live Voice documents plus 3 obsolete script documents**, a
total of **74 files / 12,892 lines**, in three gated batches. That leaves a
**20-file current working set** before the final post-cleanup consolidation
described in section 7. These line totals are frozen audit metrics and will
drift as retained documents receive necessary corrections; file manifests and
retirement gates are authoritative.

This is an end-state manifest, not permission to delete all 74 files in one
mechanical diff. Links, unique current rules and live regression ownership must
move first.

## 2. Retention rule

A document stays in the active branch only when it currently owns at least one
of these responsibilities:

1. current state/routing;
2. accepted product or architecture contract;
3. current acceptance/run instructions;
4. accepted decision rationale that the source cannot explain;
5. evidence for the current unreleased candidate or an active compatibility
   boundary;
6. a current cleanup/review manifest required to finish this branch.

Dated execution packets, closed implementation reviews, old handoffs, old
environment transcripts and milestone ledgers do not need to remain merely for
recoverability. Git owns that history. A historical file may still need one
fact transplanted into a current decision, test, acceptance contract or runbook
before deletion.

## 3. Batch A — first documentation cleanup

Disposition: **completed on 2026-08-17 after repairing inbound links**.
These 19 files total **2,396 lines**. They are archive content, unreferenced
closed reviews/ledgers, or documentation for obsolete scripts. None is a
current authority.

### 3.1 Existing archive documents

- `live-voice/archive/POST_V0_STASH_HANDOFF.md`
- `live-voice/archive/TWO_WEEK_DEMO.md`

The former `V0_ACCEPTANCE.md` link to `TWO_WEEK_DEMO.md` was removed in the same
batch; the exact historical target remains available through Git.

### 3.2 Unrouted closed records

- `live-voice/D91_W2_RUNTIME_BLOCKER_CLOSURE_REVIEW_2026-08-08.md`
- `live-voice/D92_OPENAI_PCM_PROVIDER_CLOSURE_REVIEW_2026-08-08.md`
- `live-voice/D93_OPENAI_IDENTITY_HTTP_CLOSURE_REVIEW_2026-08-08.md`
- `live-voice/D96_W2_BLOCKER_CLOSURE_REVIEW_2026-08-10.md`
- `live-voice/D97_W2_NO_EVIDENCE_SMOKE_REVIEW_2026-08-10.md`
- `live-voice/D113_S6_02_SYNTHESIS_EVENT_TIMEOUT_REPAIR_2026-08-13.md`
- `live-voice/D114_S6_02_COLD_EOT_AND_LONG_PLAYOUT_REPAIR_2026-08-13.md`
- `live-voice/LATEST_FOUNDATIONS_D053_REVIEW_2026-08-06.md`
- `live-voice/PRODUCT_COMPOSITION_FOUNDATIONS_REVIEW_2026-08-06.md`
- `live-voice/PRODUCT_COMPOSITION_REGISTRATION_REVIEW_2026-08-06.md`
- `live-voice/S8_FAST_CLOSEOUT_LEDGER_2026-08-15.md`
- `live-voice/SPEECH_CRITICAL_TOKEN_SAFETY_REVIEW_2026-08-05.md`
- `live-voice/W1_A_PACKAGE_REVIEW_2026-08-04.md`
- `live-voice/W1_X2_P1B_REVIEW_2026-08-04.md`

The safety and composition records contained useful historical review detail,
but their accepted contracts are owned by decisions, architecture, source and
tests. Those owners were confirmed before deletion; old mutable status and test
counts were not copied into a new summary.

### 3.3 Documentation owned by obsolete scripts

- `scripts/live_voice/S7_AUTOMATION.md`
- `scripts/live_voice/S8_READINESS.md`
- `scripts/live_voice/w2_rehearsal/README.md`

These documents were removed after current operating guidance moved to root
`TESTING.md` and the E2E runbook. The corresponding scripts/tests remain until
every still-applicable regression oracle is migrated to a capability/module
owner; deleting documentation does not waive that code-removal gate.

## 4. Batch B — obsolete numbered-stage execution bundle

Disposition: **extract unique live regressions, then remove as one coherent
bundle**. At the audit-time inventory, these 12 files totaled **2,682 lines**.
They form an internally linked S6/S7/S8 execution chain and are the main
remaining source of retired stage vocabulary being mistaken for current order.

- `live-voice/D111_ALPHA_REAL_PATH_ACTIVATION_2026-08-12.md`
- `live-voice/D112_ALPHA_REAL_MEDIA_ROUTE_2026-08-13.md`
- `live-voice/D115_S6_02_BREATH_PAUSE_VAD_REPAIR_2026-08-13.md`
- `live-voice/D116_S6_02_PHYSICAL_CLOSURE_2026-08-13.md`
- `live-voice/D117_POST_9B8_COMMIT_AUDIT_2026-08-13.md`
- `live-voice/S6_02_PHYSICAL_OBSERVATION_RUNBOOK_2026-08-13.md`
- `live-voice/S6_ALPHA_INTEGRATION_REVIEW_2026-08-12.md`
- `live-voice/S7_ALPHA_INTEGRATION_REVIEW_2026-08-13.md`
- `live-voice/S8_READINESS_PREPARATION_2026-08-13.md`
- `live-voice/roadmap/ALPHA_S5_S8_EXECUTION_PLAN_2026-08-12.md`
- `live-voice/roadmap/S7_EXECUTION_PACKET_2026-08-13.md`
- `live-voice/roadmap/S8_FAST_CLOSEOUT_PACKET_2026-08-15.md`

Before deletion, preserve only still-applicable VAD/cold-EOT/playout/media
regressions in source tests, and preserve any current physical operating step in
`runbooks/E2E_RUNBOOK.md`. Do not preserve stage entry/exit, owner/session,
candidate-SHA, temporary environment or old test-count prose.

## 5. Batch C — historical delivery and implementation corpus

Disposition: **aggressive final-branch cleanup after shrinking the reference
index and extracting current contracts**. At the audit-time inventory, these
43 files totaled **7,814 lines**. Git retains their full content and tested
identities.

### 5.1 Closed module and implementation reviews

- `live-voice/AB_B_WORK_PROGRESS_IMPLEMENTATION_REVIEW_2026-08-05.md`
- `live-voice/AIO_B_X_WEB_IMPLEMENTATION_REVIEW_2026-08-05.md`
- `live-voice/CR_B_RUNTIME_IMPLEMENTATION_REVIEW_2026-08-05.md`
- `live-voice/P1_FORMAL_SPEECH_IMPLEMENTATION_REVIEW_2026-08-05.md`
- `live-voice/P2_REAL_AGENT_CR_BLOCKER_REVIEW_2026-08-05.md`
- `live-voice/P3ALPHA_REPLACEMENT_REVIEW_2026-08-05.md`
- `live-voice/P3_AUTH_COMPOSITION_IMPLEMENTATION_REVIEW_2026-08-05.md`
- `live-voice/X_E2E_X_WEB_IMPLEMENTATION_REVIEW_2026-08-05.md`
- `live-voice/X_OBS_IMPLEMENTATION_REVIEW_2026-08-05.md`
- `live-voice/SOL_MODULE_PRE_REVIEWS_2026-08-03.md`
- `live-voice/W1_K1_IMPLEMENTATION_REVIEWS_2026-08-03.md`

### 5.2 Closed Alpha integration sequence

- `live-voice/ALPHA_PRODUCT_INTEGRATION_REVIEW_2026-08-07.md`
- `live-voice/ALPHA_WAVE_AB_INTEGRATION_REVIEW_2026-08-07.md`
- `live-voice/ALPHA_WAVE_C_INTEGRATION_REVIEW_2026-08-07.md`
- `live-voice/ALPHA_POST_WAVE_C_INTEGRATION_REVIEW_2026-08-07.md`

### 5.3 Superseded execution plans and task packets

- `live-voice/roadmap/ALPHA_PARALLEL_EXECUTION_2026-08-06.md`
- `live-voice/roadmap/ALPHA_WAVE_AB_EXECUTION_2026-08-07.md`
- `live-voice/roadmap/ALPHA_WAVE_C_EXECUTION_2026-08-07.md`
- `live-voice/roadmap/DEMO_90_EXECUTION_2026-08-07.md`
- `live-voice/roadmap/P2_REAL_AGENT_CR_INTERFACE_TASK_PACKET_2026-08-05.md`
- `live-voice/roadmap/PRODUCT_COMPOSITION_GATE_0_2026-08-06.md`
- `live-voice/roadmap/WEEK_1_EXECUTION_PACKAGES_2026-08-03.md`

### 5.4 W2/recovery/governance records superseded by current source and status

- `live-voice/D90_W2_INTEGRATED_DEMO_REVIEW_2026-08-08.md`
- `live-voice/D94_BROWSER_REFRESH_DUPLEX_RECOVERY_REVIEW_2026-08-08.md`
- `live-voice/D95_P3_D0_ATTEMPT_BINDING_REPAIR_2026-08-08.md`
- `live-voice/D98_W2_FINAL_AUTOMATION_ATTEMPT_2026-08-10.md`
- `live-voice/D99_P3_ORIGIN_ROUTE_RECONCILIATION_REVIEW_2026-08-11.md`
- `live-voice/D100_P3_TERMINAL_REPLAY_VALIDATION_READY_2026-08-11.md`
- `live-voice/D101_W2_NEW_ENVIRONMENT_MANUAL_HANDOFF_2026-08-11.md`
- `live-voice/D102_W2_SIGNED_REHEARSAL_FAULT_PROBE_REPAIR_2026-08-11.md`
- `live-voice/D103_W2_UNSIGNED_MANUAL_PRODUCT_ACCEPTANCE_2026-08-11.md`
- `live-voice/D104_P3_REFRESH_RECOVERY_AND_W2_ACCEPTANCE_CONTINUATION_2026-08-11.md`
- `live-voice/D105_W2_PRODUCT_ACCEPTANCE_2026-08-11.md`
- `live-voice/D106_W2_SIGNED_GATE_CODE_REMOVAL_REVIEW_2026-08-11.md`
- `live-voice/D108_PROJECT_PROGRESS_AND_GOVERNANCE_REVIEW_2026-08-12.md`
- `live-voice/D109_STAGE_MODULE_DOCUMENTATION_SYNC_2026-08-12.md`
- `live-voice/D110_ALPHA_AUTOMATED_VERIFICATION_AND_ENVIRONMENT_BLOCK_2026-08-12.md`

Before deleting D110, move its still-applicable Gateway test-discovery warning
into current `TESTING.md` if that warning is not already present. D105's product
acceptance result may remain summarized in STATUS; the full historical journey
stays recoverable from Git.

### 5.5 Historical V0/W2 acceptance, showcase and evidence

- `live-voice/demo/DEMO_SHOWCASE.md`
- `live-voice/demo/INTEGRATED_SHOWCASE.md`
- `live-voice/validation/V0_ACCEPTANCE.md`
- `live-voice/validation/INTEGRATED_DEMO_ACCEPTANCE.md`
- `live-voice/evidence/V0_20260802_ee2896a4.md`
- `live-voice/evidence/P2_BROWSER_AGENT_TOOL_20260807_fb40f12b.md`

These are real historical records, not false or low-quality documents. Their
removal is justified only by the user's decision that Git is sufficient for
recovery and by retaining the current product acceptance contract. Do not
reinterpret deletion as invalidating the historical result.

## 6. Twenty-file current working set

After Batches A–C, retain these 20 Live Voice documents while the present
defects, cleanup and integration work remain open:

- `live-voice/README.md`
- `live-voice/STATUS.md`
- `live-voice/DOCUMENTATION_RULES.md`
- `live-voice/REFERENCE_INDEX.md`
- `live-voice/decisions/DECISIONS.md`
- `live-voice/architecture/ARCHITECTURE_CONTRACT_GATE_V1.md`
- `live-voice/architecture/FULL_SOLUTION_2026-07-30.md`
- `live-voice/runbooks/E2E_RUNBOOK.md`
- `live-voice/validation/PRODUCT_READINESS_ACCEPTANCE.md`
- `live-voice/demo/PRODUCT_READINESS_SHOWCASE.md`
- `live-voice/D031_IMPLEMENTATION_REVIEW_2026-08-04.md`
- `live-voice/evidence/D031_20260805_PROJECT_BOUND.md`
- `live-voice/D107_W3_DEVELOP_REBASELINE_MIGRATION_2026-08-12.md`
- `live-voice/D118_UNIFIED_HANDS_FREE_LIVE_VOICE_REVIEW_2026-08-16.md`
- `live-voice/D119_RUNNING_TASK_ADJUSTMENT_AND_TERMINAL_NOTIFICATION_REVIEW_2026-08-16.md`
- `live-voice/evidence/POST_ALPHA_DEMO_20260817_95b26308_WORKTREE.md`
- `live-voice/reviews/DOCUMENT_RETIREMENT_AUDIT_2026-08-17.md`
- `live-voice/roadmap/WEB_ALPHA_DELIVERY_MATRIX_2026-08-05.md`
- `live-voice/reviews/CODE_DUPLICATION_AND_RETIREMENT_AUDIT_2026-08-17.md`
- `live-voice/reviews/BRANCH_CONTENT_RETIREMENT_AUDIT_2026-08-17.md`

The document audit itself replaces the deleted dated roadmap in the temporary
20-file cleanup working set. It is removed after its remaining manifest closes.

Repository-root `AGENTS.md`, `TESTING.md`, `README.md` and `README_CN.md` remain
current repository documentation; they are not Live Voice history candidates.

## 7. Deferred consolidation of the working set

The 20-file set can shrink further, but not before its live responsibility
closes:

| Document(s) | Remove/replace when |
|---|---|
| D031 review and evidence | The legacy Task-monitor/compatibility surface is retired and its required regressions live in the formal Task tests |
| D107 migration review | The final develop integration strategy is executed and its surviving deletion/compatibility decisions are recorded |
| D118, D119 and current Post-Alpha evidence | A repaired candidate receives new clean automated plus human acceptance; preserve only the final result/current defect regressions |
| Three cleanup audits | Their manifests are executed and the final branch no longer needs open cleanup tracking; Git retains the audits |
| `REFERENCE_INDEX.md` | Historical working-tree documents are gone and README/DOCUMENTATION_RULES/root guidance no longer route forensic work to local files |
| Root `TESTING.md` migration | **DONE** — it now owns D-032/D-046/D-074 verification/review rules; the dated roadmap was deleted |
| `WEB_ALPHA_DELIVERY_MATRIX_2026-08-05.md` | Current module/dependency/replacement relationships are captured in architecture/current acceptance; dated package mappings can disappear |
| `PRODUCT_READINESS_ACCEPTANCE.md` | **DONE** — current controlled candidate contract without S5–S8 progress semantics; retain while product work is active |
| `PRODUCT_READINESS_SHOWCASE.md` | **DONE** — current complete human Journey without the historical S7 handoff; retain while product work is active |

The durable Live Voice core should ultimately be close to: router, current
status, documentation rules, decisions, architecture/contract, current
acceptance, current runbook and current product journey. Dated implementation
reviews should not remain as a second product specification.

## 8. Content-level trimming inside retained documents

### 8.1 `runbooks/E2E_RUNBOOK.md`

After the historical V0/W2 bundle is removed, delete or move to Git-only history:

- the V0 historical reproduction baseline;
- the default V0, stable-sentence preview and bounded legacy Task Demo launch
  sections when their compatibility code is retired;
- the 2026-08-01/02 attempt-by-attempt run transcript.

Keep common isolation/service startup, the current Post-Alpha/formal product
launch, the current acceptance template and cleanup. This removes historical
execution narrative without losing an operable runbook.

### 8.2 Stable verification authority — completed

The current risk-tier/scenario/review cadence (D-032/D-046/D-074) was extracted
to root `TESTING.md`; root `AGENTS.md` and documentation routing now point there.
The dated Post-V0 roadmap and its numbered sequencing were deleted from the
working tree and remain recoverable from Git.

### 8.3 `roadmap/WEB_ALPHA_DELIVERY_MATRIX_2026-08-05.md`

Old package names, predecessor windows and milestone tables can go. Preserve
only current module ownership, dependencies and formal-replacement relationships
in architecture or current acceptance, then delete the dated matrix.

### 8.4 Current acceptance and showcase

`PRODUCT_READINESS_ACCEPTANCE.md` now owns the current controlled-candidate
requirements without a stage-entry graph. `PRODUCT_READINESS_SHOWCASE.md` now
owns the current human Journey without the historical S7 handoff. Both remain
active authorities until the product boundary changes.

### 8.5 Files not to trim merely for size

- `STATUS.md` is the only mutable current-state authority. Remove stale detail
  only when the corresponding gap closes; do not move current facts into dated
  reviews.
- `decisions/DECISIONS.md` is long but owns accepted rationale and supersession.
  Do not delete accepted decisions simply because Git can recover them.
- The ACG and complete architecture snapshot own long-term contracts. Keep them
  until a reviewed replacement exists.

## 9. Deletion acceptance

Each documentation-removal batch must:

1. compare its exact manifest with current Git status so unrelated user changes
   are not removed;
2. extract only live decisions, current acceptance requirements, operating
   steps and regressions;
3. remove/update all Markdown links and plain routing instructions;
4. run a repository Markdown link check and `git diff --check`;
5. search current docs for removed S5–S8/stage/old-window routing;
6. confirm `README.md`, `STATUS.md`, `DOCUMENTATION_RULES.md`, root `AGENTS.md`
   and `TESTING.md` agree on the surviving authority map;
7. review the final deletion diff by batch rather than mixing it with product
   defect repairs.

## 10. Execution tracking

| Work item | State |
|---|---|
| Full documentation inventory/link/redundancy analysis | **DONE** |
| Batch A deletion | **DONE — 19 files / 2,396 lines** |
| Batch B regression extraction and deletion | **NOT STARTED** |
| Batch C historical corpus deletion | **NOT STARTED** |
| Current acceptance/showcase/runbook rewrite | **DONE for current product-readiness entrypoints; later historical runbook trimming remains in Batch C** |
| Final authority/link consistency review | **PENDING CLEANUP IMPLEMENTATION** |
