# Live Voice documentation rules

Read this file before changing the Live Voice documentation structure or updating documentation after material code, validation, or decision work.

## Two independent axes

Documents are classified on two independent axes:

- **Depth**: short/summary versus complete/source record.
- **Read policy**: mandatory versus conditional for the current task.

They can be combined. `README.md` and `STATUS.md` are short and mandatory for every Live Voice task. The complete solution is full and conditional for ordinary work, but becomes mandatory when architecture, phase boundaries, protocols, ownership, cancellation, durability, or production acceptance are in scope.

## Authority map

| Information | Single authoritative location |
|---|---|
| Repository-wide Git approval and bootstrap invariants | root `AGENTS.md` |
| What to read for a task | `README.md` |
| Current branch/milestone/progress/gaps/next slice | `STATUS.md` |
| Accepted choice, rationale, impact, re-evaluation | `decisions/DECISIONS.md` |
| Original complete design | `architecture/FULL_SOLUTION_2026-07-30.md` |
| Delivery ordering, module definition, test-closure process | `roadmap/POST_V0_DELIVERY_ROADMAP.md` |
| V0 pass/fail contract | `validation/V0_ACCEPTANCE.md` |
| Environment and E2E operating procedure | `runbooks/E2E_RUNBOOK.md` |
| Presentation flow | `demo/DEMO_SHOWCASE.md` |
| Immutable run evidence | `evidence/` |
| Superseded plans and stash history | `archive/` |

## Anti-duplication rules

1. Mutable facts live only in `STATUS.md`. Other documents link to it and must not repeat the current HEAD, ahead/behind, current completion percentage, or next task.
2. `README.md` is a router, not a second handoff/status page.
3. A decision is recorded once in `DECISIONS.md`; roadmap/status may cite its ID and operational consequence without duplicating its full rationale.
4. Full design and evidence are immutable snapshots. Correct later understanding through a decision or status update instead of silently rewriting historical evidence.
5. Archive documents must carry an archive warning and cannot override status or accepted decisions.
6. Avoid parallel summaries such as separate HANDOFF and STATUS files. Continuation facts belong in STATUS; operational steps belong in README/runbook.
7. Repeated wording is allowed only when required for safety at the point of action, and the repeated text must link to its authority.

## Read routing

- Ordinary implementation: root `AGENTS.md`, `README.md`, `STATUS.md`, relevant roadmap/decision section, source, and tests.
- Bug/hotfix: the same minimal set plus the affected module contract and focused regression tests; a hotfix needs reasonable scenario coverage, not an unrelated full-project test campaign.
- Architecture/protocol work: add the complete solution snapshot and all decisions governing the boundary.
- Validation/E2E: add acceptance, runbook, showcase, and relevant evidence.
- Documentation work: this file plus every authoritative file that the change affects.
- Historical investigation: archive only after current sources, never instead of them.

## Synchronization protocol

- Code/module progress changes: update `STATUS.md`; update roadmap only if scope/order/contract changed.
- New technical or product choice: append a decision, then update only the concise consequence in STATUS/roadmap.
- Acceptance run: keep raw/private logs outside Git as required, add a sanitized immutable evidence record, then update STATUS once.
- New shortcut: update the applicable demo/archive ledger and record only its current consequence in STATUS.
- Document move/rename: update `README.md`, root `AGENTS.md`, all relative links, and run the link checker.
- Do not claim a state in advance. Record verification commands and exact tested SHA only after they actually ran.

## Module test documentation (D-032)

Before semantic implementation, STATUS must contain the module definition, non-goals, current/planned tests, why each test exists, and the scenario matrix. After implementation, revisit the same record against the actual diff and final tests. Positive scenarios must succeed; negative scenarios must be rejected/fail closed and assert forbidden side effects as zero. Missing coverage or unexplained `N/A` prevents `CLOSED`.

## Final documentation check

Before proposing a documentation commit:

1. `git diff --check` passes.
2. Every local Markdown link under `live-voice/` resolves.
3. `docs/zh/live-voice/` contains no tracked duplicate.
4. README remains routing-only and STATUS remains the sole mutable state.
5. Archive warnings are present.
6. Current code, tests, decisions, roadmap, and STATUS do not contradict one another.
7. The proposed commit/push still follows the root approval gate.