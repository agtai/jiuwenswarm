# Live Voice documentation rules

Read this file only for documentation structure or synchronization work.
`README.md` owns task-reading routes; root `TESTING.md` owns risk, scenario and
review rules. Do not duplicate either here.

## Current authority map

| Information | Authority |
|---|---|
| Git, local history, remote approval and parallel-writer policy | Root `AGENTS.md` |
| Task-reading route | `README.md` |
| Current judgement, completion boundaries, capability matrix, dependencies and active packet | `STATUS.md` |
| Testing and D-032/D-046/D-074 verification/review rules | Root `TESTING.md` |
| Accepted choice, rationale and re-evaluation | `decisions/DECISIONS.md` |
| Stable P1/P2/P3 capability and shared-contract design | `architecture/FULL_SOLUTION_2026-07-30.md` §§2, 4–5, interpreted through current decisions/STATUS |
| Current controlled-candidate pass/fail | `validation/PRODUCT_READINESS_ACCEPTANCE.md` |
| Current complete human journey | `demo/PRODUCT_READINESS_SHOWCASE.md` |
| Environment, start, diagnosis and cleanup commands | `runbooks/E2E_RUNBOOK.md` |
| Conditional historical/module/forensic routes | `REFERENCE_INDEX.md` |
| Detailed cleanup findings | `reviews/` |
| Immutable run evidence | `evidence/` or Git history |

Historical milestone contracts, delivery matrices, reviews and evidence remain
exact-source records. They cannot override the current authorities above.

## Ownership and anti-duplication

1. Mutable current facts live only in `STATUS.md`. Git supplies live HEAD,
   branch, upstream, ahead/behind and dirty state; do not freeze those transient
   facts in STATUS.
2. STATUS owns one capability matrix and dependency route. Do not re-create
   separate “completed”, “remaining”, “handoff” or “next work” summaries.
3. README routes; it does not summarize the project or catalog history.
4. Decisions record accepted choices and reasons, not mutable progress.
5. Acceptance owns pass/fail; showcase owns human actions; runbook owns
   environment and commands. A fixture-specific runbook may add exact setup,
   prompts and diagnostics, but must link to the showcase instead of redefining
   the journey or its outcome.
6. Root TESTING owns risk tiers, scenario dimensions and review cadence. Other
   documents cite it without reproducing the matrix.
7. Historical design bodies and evidence are frozen snapshots. Correct later
   interpretation through a dated header, STATUS or decision rather than
   silently rewriting historical facts.
8. Git is the recovery archive for removed process documents. Retain a working-
   tree historical file only while it owns a current regression, contract or
   forensic route.
9. Safety text may repeat only at the point of action and must link or clearly
   identify its authority.

## Keep default reading small

- STATUS is a current decision aid: one judgement, capability matrix, active
  scope, remaining gates and dependency order. Replace superseded statements;
  do not prepend another “latest” checkpoint while leaving the old one active.
- Keep test counts, per-run timelines, closed module packets, old integration
  assignments and expired time windows in evidence or conditional history.
  STATUS keeps only their current consequence and a task-specific link.
- Preserve failed evidence and still-open requirements when shortening text.
  Moving a report never closes its missing review, regression or physical Gate.
- A frozen status snapshot may preserve otherwise uncommitted historical facts
  and disputed handoffs. Mark it historical and route it only from
  `REFERENCE_INDEX.md`; never add it to mandatory bootstrap.
- Before adding a new STATUS paragraph, check whether it replaces an existing
  one. Avoid multiple backlog/handoff files and recurring cleanup reports.

## Synchronization rules

- Product/source progress: update the affected STATUS capability row, current
  packet and dependency trigger; do not paste detailed test output into STATUS.
- Completion-boundary or architectural choice: append one decision, then update
  STATUS and the owning acceptance/design route.
- Verification: record exact commands/source in the scoped review/evidence;
  STATUS carries only current credit and remaining gap.
- Acceptance run: keep private/raw material outside Git, add concise sanitized
  evidence when useful, then update STATUS once.
- New shortcut/hardcode: record its owner, honest boundary and retirement gate
  in the applicable decision/audit; add only the current consequence to STATUS.
- Document move/delete: repair every current and historical reference, then run
  the scoped local-link check. Removed history remains available from Git.
- Historical investigation: select one route from `REFERENCE_INDEX.md`; never
  load the complete historical corpus during ordinary work.
- Never claim implementation, review or acceptance before it actually ran.

## Documentation completion check

Before committing documentation:

1. `git diff --check` passes.
2. Every changed local Markdown link resolves; a full structural cleanup checks
   all current Live Voice Markdown links.
3. `docs/zh/live-voice/` contains no tracked duplicate.
4. README stays a short router; STATUS has one current capability/dependency
   model; TESTING/acceptance/showcase/runbook each retain their single role.
5. No current document routes a historical stage/window as current work.
6. Git/source/tests, D-084 completion boundaries, D-085 audit dependency,
   decisions, acceptance and STATUS agree.
7. The diff is one coherent documentation scope; any remote update remains
   separately approved under root `AGENTS.md`.
