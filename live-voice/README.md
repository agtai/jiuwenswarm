# JiuwenSwarm Live Voice router

This file is the lightweight entrypoint. It tells a new Session what to read;
it is not a project summary, document catalog or historical handoff.

## Always read

1. Read the repository root `AGENTS.md`.
2. Verify Git with `git status --short --branch`, `git rev-parse HEAD`, the
   configured upstream and `HEAD...@{upstream}`.
3. Read [STATUS.md](STATUS.md). It is the only mutable current-state source.
4. Select one route below. Do not load every linked document or every section of
   a routed document.

## Current-task routing

| Task | Additional reading |
|---|---|
| Current Alpha implementation, investigation or bug fix | Read §1–2 and only the task ID named by STATUS in the [S5–S8 plan](roadmap/ALPHA_S5_S8_EXECUTION_PLAN_2026-08-12.md), then the affected source/tests and only the acceptance bullets that task consumes. Read prerequisite task sections only when their output is missing or conflicts. |
| Alpha task/stage planning | Read §1–2 plus only the current stage section of the S5–S8 plan. Add D-075/D-076 and the relevant roadmap section only when changing task order, scope or exits. |
| Post-Alpha Demo implementation, investigation or bug fix | Read STATUS, D-081, the affected source/tests and only the relevant D119 contract boundary. Use runbook §7.5 only for runtime/Demo validation. Do not reopen S7/S8 or start S9. |
| Ordinary non-Alpha module work | Read the affected source/tests, the relevant module/package contract and only the governing decision or ACG sections. Do not read old integration reviews by default. |
| Documentation structure/update | Read [DOCUMENTATION_RULES.md](DOCUMENTATION_RULES.md), then only the authoritative files changed by the update. |
| Architecture, authority, protocol, security or durability change | Read the exact relevant ACG sections and current decisions. Add the complete solution only when the long-term boundary itself is in scope. |
| S7/A2 candidate verification | Read plan §1–2 and §5, [Alpha acceptance](validation/ALPHA_ACCEPTANCE.md), affected module reviews/tests and only the required runbook sections. |
| S8/A3 product acceptance | Read plan §1–2 and §6, Alpha acceptance, [Alpha showcase](demo/ALPHA_SHOWCASE.md) and the Alpha operating sections of the [runbook](runbooks/E2E_RUNBOOK.md). |
| Git/review/parallel authority | Read root `AGENTS.md`, D-074 and only an active packet explicitly named by STATUS. Completed W2 lane assignments are not current. |
| V0, W2, D-031, W3 migration, historical package or forensic work | Use the conditional [reference index](REFERENCE_INDEX.md); it must not be read during ordinary bootstrap. |

## Sectional-reading rules

- A link is a route, not an instruction to read the whole target.
- In `DECISIONS.md`, locate the required `## D-nnn` heading and read only that
  decision through the next decision heading.
- In the execution plan, read common rules/dependencies plus the active task or
  stage section. Read the whole plan only when auditing or changing the task graph.
- Acceptance is required while implementing only for the bullets owned by the
  active task; the complete contract is required at A2/A3.
- Showcase and physical runbook steps are A3/runtime material, not ordinary
  implementation context.
- Frozen reviews/evidence explain history. Read one only for a concrete regression,
  disputed invariant or evidence question.

## Authority and conflict order

1. User's latest explicit instruction.
2. Checked-out Git source and tests.
3. STATUS for mutable state/current task.
4. Accepted decisions, active execution task and acceptance contract.
5. Stable roadmap/ACG, then the full design snapshot.
6. Frozen reviews/evidence and archive.

If sources disagree, report and repair the authoritative document. Do not copy
the same mutable fact into several files. Git does not restore credentials,
Provider/model configuration, project registration, browser permissions/devices,
runtime data or network state.
