# Live Voice documentation rules

Read this file before changing the Live Voice documentation structure or updating documentation after material code, validation, or decision work.

## Two independent axes

Documents are classified on two independent axes:

- **Depth**: short/summary versus complete/source record.
- **Read policy**: mandatory versus conditional for the current task.

They can be combined. `README.md` and `STATUS.md` are short and mandatory for every Live Voice task. The complete solution is not an ordinary implementation prerequisite; read it only when the long-term architecture/boundary itself changes, an intended boundary is genuinely ambiguous, or production scope is being decided. A normal protocol, cancellation or durability fix reads the exact active task, relevant ACG/decision sections, source and tests first.

Links are sectional routes, not whole-file read commands. A new Session reads the
minimum pair above, then only the active task/stage section and its affected
source/tests. Complete plans, acceptance, runbooks, architecture and historical
records are loaded only at the boundary that owns them.

## Authority map

| Information | Single authoritative location |
|---|---|
| Repository-wide local Git, remote approval, minimum-intervention, review cadence and bootstrap invariants | root `AGENTS.md` and D-074 |
| What to read for a task | `README.md` |
| Current branch/milestone/progress/gaps/next slice | `STATUS.md` |
| Accepted choice, rationale, impact, re-evaluation | `decisions/DECISIONS.md` |
| Original complete design | `architecture/FULL_SOLUTION_2026-07-30.md` |
| Stable project-stage/module/node vocabulary, delivery ordering, milestone definitions, acceptance closure and risk-tier closure | D-075 and `roadmap/POST_V0_DELIVERY_ROADMAP.md` |
| Active S5–S8 task IDs, dependencies, risk, module-close oracles, exits and exclusions | D-076 and `roadmap/ALPHA_S5_S8_EXECUTION_PLAN_2026-08-12.md` |
| Current stage, current node, module coverage and next batch | `STATUS.md` |
| Completed Week 1 priority/dependency/boundary and historical package contracts | `roadmap/WEEK_1_EXECUTION_PACKAGES_2026-08-03.md` |
| Stable Web Alpha work-package, Demo-predecessor, formal-replacement, dependency, target-window and acceptance mapping | `roadmap/WEB_ALPHA_DELIVERY_MATRIX_2026-08-05.md` |
| V0 pass/fail contract | `validation/V0_ACCEPTANCE.md` |
| Week 2 Integrated Demo automated-plus-human pass/fail | `validation/INTEGRATED_DEMO_ACCEPTANCE.md` |
| Integrated Web Alpha (S5–S8; historical W3/W4 window) pass/fail | `validation/ALPHA_ACCEPTANCE.md` |
| Environment and E2E operating procedure | `runbooks/E2E_RUNBOOK.md` |
| V0 presentation flow | `demo/DEMO_SHOWCASE.md` |
| W2 cumulative P1/P2/P3alpha presentation flow | `demo/INTEGRATED_SHOWCASE.md` |
| Alpha A3 complete presentation flow | `demo/ALPHA_SHOWCASE.md` |
| Conditional milestone/module/history/forensic routing | `REFERENCE_INDEX.md` |
| Frozen detailed Sol pre-review designs | `SOL_MODULE_PRE_REVIEWS_2026-08-03.md` |
| Immutable run evidence | `evidence/` |
| Superseded plans and stash history | `archive/` |

## Anti-duplication rules

1. Mutable facts live only in `STATUS.md`. Other documents link to it and must not repeat the current HEAD, ahead/behind, current replacement credit, or next action.
2. `README.md` is a short router, not a document catalog, second handoff or status page. Detailed historical/module routes belong in the conditional `REFERENCE_INDEX.md`.
3. A decision is recorded once in `DECISIONS.md`; roadmap/status may cite its ID and operational consequence without duplicating its full rationale.
4. Full design and evidence are immutable snapshots. Correct later understanding through a decision or status update instead of silently rewriting historical evidence.
5. Archive documents must carry an archive warning and cannot override status or accepted decisions.
6. Avoid parallel summaries such as separate HANDOFF and STATUS files. Continuation facts belong in STATUS; operational steps belong in README/runbook; detailed pre/post review matrices belong in dated review records and do not define current order.
7. Repeated wording is allowed only when required for safety at the point of action, and the repeated text must link to its authority.
8. A dated execution plan freezes package contracts and Sol oracles for its window; it must not carry mutable implementation progress, tested SHA, or replacement credit. Those facts remain in `STATUS.md`, and a later rolling plan supersedes the dated queue through an explicit STATUS/decision update.
9. The dated Web Alpha delivery matrix owns stable package and replacement relationships only. It links to STATUS for current state and to acceptance documents for pass/fail; it must not duplicate current HEAD, test counts, scores, blockers, next actions, or full acceptance scenarios.
10. Do not use `phase`, `stage`, `track`, `module`, `work package`, `window` or `node` interchangeably. Under D-075, `S0`–`S9` are sequential stages, `A0`–`A3` are Alpha critical nodes, P1/P2/P3alpha/Shared-X are capability tracks, named components are modules, `*-A/B/C` are work packages, and W1/W2/W3/W4 are historical delivery windows.
11. STATUS contains the current task, compact closure summary, live blockers and next actions. It must not duplicate the full stage contract, task oracles, acceptance matrix, document catalog or historical evidence index.
12. A decision records an accepted choice and boundary; it does not become a second execution plan or current gap dashboard.

## Read routing

- Ordinary implementation: root `AGENTS.md`, `README.md`, `STATUS.md`, only the active execution-task section, affected source/tests and exact governing decision/contract sections.
- Week 1 regression or package-history work: add the dated Week 1 execution plan and read only that package's consumed ACG/design sections, target source, and adjacent tests; do not treat its former queue, owner, environment, or timing statements as current state.
- Bug/hotfix: the same minimal set plus the affected module contract and focused regression tests; a hotfix needs reasonable scenario coverage, not an unrelated full-project test campaign.
- Architecture/protocol work: read only the relevant ACG and exact governing decision sections; add the complete solution snapshot only when the long-term boundary itself changes or remains ambiguous.
- Integrated Web Alpha execution: read plan §1–2 plus only the task named by STATUS, its affected source/tests and owned acceptance bullets. Read the full stage section only for stage planning and the whole plan only to audit/change the task graph. Historical W3/W4/Wave packets do not become the current queue.
- Validation/E2E: select exactly the V0, W2 Integrated Demo, or Integrated Web Alpha acceptance contract. Complete Alpha acceptance begins at A2; showcase and physical runbook steps begin at A3/runtime preparation. W2 and Alpha must not share an ambiguous manual script.
- Documentation work: this file plus every authoritative file that the change affects.
- Historical investigation: use `REFERENCE_INDEX.md` to select one implicated record; read archive only after current sources, never instead of them.

## Synchronization protocol

- Code/module progress changes: update the concise dashboard and acceptance checklist in `STATUS.md`; update roadmap only if milestone scope, order or acceptance contract changed; update a review record only for the review it owns.
- Rolling execution planning: record a stable dated package contract under `roadmap/`, route it from README/STATUS, and keep progress out of it. Replace the route when a newer accepted decision freezes a new execution window; do not silently mutate an old plan into a new queue.
- Stage/schedule wording: use D-075 `S*` for current sequential state and `A*` for Alpha checkpoints. `W1/W2/W3/W4` may only name historical dependency/order windows; a document may call them calendar weeks or commitments only when the current resource assumption and dated estimate are explicitly accepted.
- New technical or product choice: append a decision, then update only the concise consequence in STATUS/roadmap.
- Product-carrier change: preserve dated historical snapshots, update current decision/status/roadmap/acceptance/runbook routes, and reconcile the stable delivery matrix without rewriting historical evidence.
- Acceptance run: keep raw/private logs outside Git as required, add a concise sanitized acceptance record when useful, then update STATUS once. D-071 does not require signatures, a fixed evidence manifest or repeated full-showcase runs.
- New shortcut: update the applicable demo/archive ledger and record only its current consequence in STATUS.
- Document move/rename: update `README.md`, root `AGENTS.md`, all relative links, and run the link checker.
- Do not claim a state in advance. Record verification commands and exact tested SHA only after they actually ran.

## Module test documentation (D-032 / D-046 / D-074)

Use the roadmap risk tier before creating review artifacts:

- Tier 0 documentation/mechanical/refactor work records scope and affected checks in the normal diff summary.
- Tier 1 ordinary feature/Adapter/UI work records its contract, positive journey, key negative/flag-off paths, affected integration, and regressions in the implementation plan or grouped review.
- Tier 2 state/concurrency/mutation work maintains every applicable scenario dimension, including explicit forbidden effects. A design checkpoint precedes a new or changed high-risk contract; the complete scoped diff is reviewed at module/group closure, with one independent review or recorded equivalent.
- Tier 3 shared protocol, authority, security, durability, and production-release work maintains the complete applicable D-032 matrix plus required real-path verification. It receives independent review at the changed module boundary and cumulative integration review at phase closure. Milestone acceptance itself follows D-071: automated verification plus one complete human product acceptance.

Detailed inventories and matrices live in dated or module review records, not in STATUS. Related packages may share a review when they change one coherent boundary. While implementation is in progress, record only affected diff/check results; at module closure review the complete scoped diff; at phase closure review the cumulative candidate diff and integration seams. STATUS links the review and carries only current state. Positive scenarios must succeed; negative scenarios must reject/fail closed, and mutation/security boundaries assert forbidden side effects as zero. Missing required evidence prevents closure of the affected scope; irrelevant dimensions are omitted or briefly scoped out rather than expanded into ceremonial rows.

## Final documentation check

Before creating a documentation commit:

1. `git diff --check` passes.
2. Every local Markdown link under `live-voice/` resolves.
3. `docs/zh/live-voice/` contains no tracked duplicate.
4. README remains a lightweight sectional router, STATUS remains the sole concise mutable state, REFERENCE_INDEX remains conditional, the Web Alpha matrix contains no live status, W2/Alpha acceptance each route to the correct showcase, and frozen review records cannot override STATUS or applicable current decisions, especially D-046/D-055/D-058/D-071–D-077.
5. Archive warnings are present.
6. Current code, tests, decisions, roadmap, and STATUS do not contradict one another.
7. The local commit is one coherent documentation/governance scope under root `AGENTS.md`; any push remains separately approved for the exact remote/ref/commits/update mode.
