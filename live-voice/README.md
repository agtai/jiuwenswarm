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
| Ordinary module implementation or bug fix | Relevant source/tests, the applicable part of [roadmap](roadmap/POST_V0_DELIVERY_ROADMAP.md), and relevant entries in [decisions](decisions/DECISIONS.md) |
| Documentation structure or documentation update | [DOCUMENTATION_RULES.md](DOCUMENTATION_RULES.md) before editing |
| Long-term architecture, P1/P2/P3 boundary, protocol, ownership, cancellation, durability, production acceptance | Complete [full solution snapshot](architecture/FULL_SOLUTION_2026-07-30.md), relevant decisions, and roadmap |
| V0 reproduction or regression acceptance | [V0 acceptance](validation/V0_ACCEPTANCE.md), [E2E runbook](runbooks/E2E_RUNBOOK.md), [showcase](demo/DEMO_SHOWCASE.md), and immutable [V0 evidence](evidence/V0_20260802_ee2896a4.md) |
| Post-V0 sequencing or the next development slice | [roadmap](roadmap/POST_V0_DELIVERY_ROADMAP.md) and relevant decisions |
| Demo shortcuts or why V0 differs from production | [two-week demo archive](archive/TWO_WEEK_DEMO.md); treat it as historical design/ledger, not current status |
| Old stash/foundation forensics only | [Post-V0 stash archive](archive/POST_V0_STASH_HANDOFF.md); never reconstruct or apply its machine-local stash during normal recovery |

## Document roles

| Path | Role |
|---|---|
| `STATUS.md` | Mutable state, verified facts, known gaps, and next concrete slice |
| `DOCUMENTATION_RULES.md` | Authority, routing, anti-duplication, and synchronization rules |
| `decisions/DECISIONS.md` | Accepted decisions and their rationale/history |
| `architecture/FULL_SOLUTION_2026-07-30.md` | Dated immutable complete solution snapshot |
| `roadmap/POST_V0_DELIVERY_ROADMAP.md` | Delivery order, module boundaries, and D-032 test-closure gate |
| `validation/`, `runbooks/`, `demo/`, `evidence/` | Acceptance contract, runtime procedure, presentation script, and immutable evidence |
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