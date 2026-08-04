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
| Long-term architecture, P1/P2/P3 boundary, protocol, ownership, cancellation, durability, production acceptance | Complete [full solution snapshot](architecture/FULL_SOLUTION_2026-07-30.md), accepted [Architecture Contract Gate](architecture/ARCHITECTURE_CONTRACT_GATE_V1.md), relevant decisions, and roadmap |
| V0 reproduction or regression acceptance | [V0 acceptance](validation/V0_ACCEPTANCE.md), [E2E runbook](runbooks/E2E_RUNBOOK.md), [showcase](demo/DEMO_SHOWCASE.md), and immutable [V0 evidence](evidence/V0_20260802_ee2896a4.md) |
| Week 2 cumulative Demo integration or acceptance | [Integrated Demo acceptance](validation/INTEGRATED_DEMO_ACCEPTANCE.md), [Integrated showcase](demo/INTEGRATED_SHOWCASE.md), [E2E runbook](runbooks/E2E_RUNBOOK.md), roadmap, and current replacement ledger in STATUS |
| Integrated Web Alpha acceptance (`W3/W4` delivery windows, not current calendar promises) | [Alpha acceptance](validation/ALPHA_ACCEPTANCE.md), D-055, full solution, ACG, [Web Alpha delivery matrix](roadmap/WEB_ALPHA_DELIVERY_MATRIX_2026-08-05.md), roadmap, runbook, and current STATUS |
| Post-V0 sequencing or the next development slice | [roadmap](roadmap/POST_V0_DELIVERY_ROADMAP.md), [Web Alpha delivery matrix](roadmap/WEB_ALPHA_DELIVERY_MATRIX_2026-08-05.md), and relevant decisions |
| Week 1 package history, regression work, or execution-model history | Historical [Week 1 execution packages](roadmap/WEEK_1_EXECUTION_PACKAGES_2026-08-03.md), current allocation/review policy [D-052/D-053](decisions/DECISIONS.md), the package's target source/tests, consumed ACG sections, current STATUS, and the actual diff/evidence; Week 1 is complete and this dated plan is not the current queue |
| Historical Sol module design or an implementation return-to-Sol review | Frozen [Sol module pre-reviews](SOL_MODULE_PRE_REVIEWS_2026-08-03.md), the actual diff/tests, current STATUS, and the applicable decision/roadmap contract |
| Demo shortcuts or why V0 differs from production | [two-week demo archive](archive/TWO_WEEK_DEMO.md); treat it as historical design/ledger, not current status |
| Old stash/foundation forensics only | [Post-V0 stash archive](archive/POST_V0_STASH_HANDOFF.md); never reconstruct or apply its machine-local stash during normal recovery |

## Document roles

| Path | Role |
|---|---|
| `STATUS.md` | Mutable state, verified facts, known gaps, and next concrete slice |
| `SOL_MODULE_PRE_REVIEWS_2026-08-03.md` | Frozen detailed D-031/ACG/CR-A/SR-A/SS-A/TC-A Sol design record; not current status or execution order |
| `W1_K1_IMPLEMENTATION_REVIEWS_2026-08-03.md` | Dated five-candidate evidence, Sol implementation reviews, and post-commit correction record; STATUS owns current progress |
| `W1_X2_P1B_REVIEW_2026-08-04.md` | Detailed W1-X2/P1B implementation evidence, W1-S3 judgment, three review passes, corrections, and validation gaps |
| `D031_IMPLEMENTATION_REVIEW_2026-08-04.md` | Detailed D-031 minimal monitor boundary, scenario evidence, review passes, automated verification, and real-service gap |
| `DOCUMENTATION_RULES.md` | Authority, routing, anti-duplication, and synchronization rules |
| `decisions/DECISIONS.md` | Accepted decisions and their rationale/history |
| `architecture/FULL_SOLUTION_2026-07-30.md` | Dated immutable complete solution snapshot |
| `architecture/ARCHITECTURE_CONTRACT_GATE_V1.md` | Accepted shared v2 identity/event/state/cancel/commit/progress/context contract and conformance boundary |
| `roadmap/POST_V0_DELIVERY_ROADMAP.md` | Logical delivery windows, target scope/order, replacement scoring, and risk-proportional closure; current single-lane calendar timing is not frozen |
| `roadmap/WEEK_1_EXECUTION_PACKAGES_2026-08-03.md` | Completed Week 1 historical priority/dependency/boundary plan; its package contracts remain reference material, not the current queue |
| `roadmap/WEB_ALPHA_DELIVERY_MATRIX_2026-08-05.md` | Dated stable package map from current Demo/fallback routes to formal Web Alpha owners, dependencies, target windows, and acceptance links; STATUS owns mutable progress |
| `validation/`, `runbooks/`, `demo/`, `evidence/` | V0/Integrated Demo/Alpha acceptance, runtime procedure, presentation scripts, and immutable run evidence |
| `archive/` | Historical plans and recovery context; never the current-state authority |

## Fresh-clone continuation

```powershell
git fetch agtai hx/0803_live_voice
git switch --track -c hx/0803_live_voice agtai/hx/0803_live_voice
git status --short --branch
git rev-parse HEAD
git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}'
git rev-list --left-right --count 'HEAD...@{upstream}'
```

If the local branch already exists, use `git switch hx/0803_live_voice` and a normal fast-forward pull only after checking status. Never discard local work merely to match this guide.

Git restores source, decisions, tests, and this continuation state. It does not restore model keys/API bases, local JiuwenSwarm configuration, `JIUWENSWARM_DATA_DIR`, project registration, browser profile/permissions, microphone/headset selection, or network/provider availability. Re-establish those private conditions and pass the relevant E2E gate before claiming runtime parity.

## Conflict priority

1. User's latest explicit instruction.
2. Checked-out Git source and tests.
3. `STATUS.md` for mutable state.
4. Accepted decisions and the roadmap for intended behavior.
5. Full design snapshot.
6. Archive documents.

A mismatch must be reported and corrected at its authoritative source; do not copy the same mutable fact into several documents.
