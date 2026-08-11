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
| Repository-wide Git approval, minimum-intervention activation and bootstrap invariants | root `AGENTS.md` |
| What to read for a task | `README.md` |
| Current branch/milestone/progress/gaps/next slice | `STATUS.md` |
| Accepted choice, rationale, impact, re-evaluation | `decisions/DECISIONS.md` |
| Original complete design | `architecture/FULL_SOLUTION_2026-07-30.md` |
| Delivery ordering, milestone definitions, acceptance closure and risk-tier closure | `roadmap/POST_V0_DELIVERY_ROADMAP.md` |
| Completed Week 1 priority/dependency/boundary and historical package contracts | `roadmap/WEEK_1_EXECUTION_PACKAGES_2026-08-03.md` |
| Stable Web Alpha work-package, Demo-predecessor, formal-replacement, dependency, target-window and acceptance mapping | `roadmap/WEB_ALPHA_DELIVERY_MATRIX_2026-08-05.md` |
| V0 pass/fail contract | `validation/V0_ACCEPTANCE.md` |
| Week 2 Integrated Demo automated-plus-human pass/fail | `validation/INTEGRATED_DEMO_ACCEPTANCE.md` |
| Week 3–4 Integrated Web Alpha pass/fail | `validation/ALPHA_ACCEPTANCE.md` |
| Environment and E2E operating procedure | `runbooks/E2E_RUNBOOK.md` |
| V0 presentation flow | `demo/DEMO_SHOWCASE.md` |
| Cumulative P1/P2/P3alpha presentation flow | `demo/INTEGRATED_SHOWCASE.md` |
| Frozen detailed Sol pre-review designs | `SOL_MODULE_PRE_REVIEWS_2026-08-03.md` |
| Immutable run evidence | `evidence/` |
| Superseded plans and stash history | `archive/` |

## Anti-duplication rules

1. Mutable facts live only in `STATUS.md`. Other documents link to it and must not repeat the current HEAD, ahead/behind, current replacement credit, or next action.
2. `README.md` is a router, not a second handoff/status page.
3. A decision is recorded once in `DECISIONS.md`; roadmap/status may cite its ID and operational consequence without duplicating its full rationale.
4. Full design and evidence are immutable snapshots. Correct later understanding through a decision or status update instead of silently rewriting historical evidence.
5. Archive documents must carry an archive warning and cannot override status or accepted decisions.
6. Avoid parallel summaries such as separate HANDOFF and STATUS files. Continuation facts belong in STATUS; operational steps belong in README/runbook; detailed pre/post review matrices belong in dated review records and do not define current order.
7. Repeated wording is allowed only when required for safety at the point of action, and the repeated text must link to its authority.
8. A dated execution plan freezes package contracts and Sol oracles for its window; it must not carry mutable implementation progress, tested SHA, or replacement credit. Those facts remain in `STATUS.md`, and a later rolling plan supersedes the dated queue through an explicit STATUS/decision update.
9. The dated Web Alpha delivery matrix owns stable package and replacement relationships only. It links to STATUS for current state and to acceptance documents for pass/fail; it must not duplicate current HEAD, test counts, scores, blockers, next actions, or full acceptance scenarios.

## Read routing

- Ordinary implementation: root `AGENTS.md`, `README.md`, `STATUS.md`, relevant roadmap/decision section, source, and tests.
- Week 1 regression or package-history work: add the dated Week 1 execution plan and read only that package's consumed ACG/design sections, target source, and adjacent tests; do not treat its former queue, owner, environment, or timing statements as current state.
- Bug/hotfix: the same minimal set plus the affected module contract and focused regression tests; a hotfix needs reasonable scenario coverage, not an unrelated full-project test campaign.
- Architecture/protocol work: add the complete solution snapshot and all decisions governing the boundary.
- Validation/E2E: select exactly the V0, Week 2 Integrated Demo, or Week 3–4 Alpha acceptance contract, then add its runbook/showcase and relevant evidence.
- Documentation work: this file plus every authoritative file that the change affects.
- Historical investigation: archive only after current sources, never instead of them.

## Synchronization protocol

- Code/module progress changes: update the concise dashboard and acceptance checklist in `STATUS.md`; update roadmap only if milestone scope, order or acceptance contract changed; update a review record only for the review it owns.
- Rolling execution planning: record a stable dated package contract under `roadmap/`, route it from README/STATUS, and keep progress out of it. Replace the route when Sol freezes a new window; do not silently mutate an old plan into a new week's history.
- Schedule wording: `W1/W2/W3/W4` may name dependency/order windows. A document may call them calendar weeks or commitments only when the current resource assumption and dated estimate are explicitly accepted; otherwise STATUS must say that calendar timing is not frozen.
- New technical or product choice: append a decision, then update only the concise consequence in STATUS/roadmap.
- Product-carrier change: preserve dated historical snapshots, update current decision/status/roadmap/acceptance/runbook routes, and reconcile the stable delivery matrix without rewriting historical evidence.
- Acceptance run: keep raw/private logs outside Git as required, add a concise sanitized acceptance record when useful, then update STATUS once. D-071 does not require signatures, a fixed evidence manifest or repeated full-showcase runs.
- New shortcut: update the applicable demo/archive ledger and record only its current consequence in STATUS.
- Document move/rename: update `README.md`, root `AGENTS.md`, all relative links, and run the link checker.
- Do not claim a state in advance. Record verification commands and exact tested SHA only after they actually ran.

## Module test documentation (D-032 / D-046)

Use the roadmap risk tier before creating review artifacts:

- Tier 0 documentation/mechanical/refactor work records scope and affected checks in the normal diff summary.
- Tier 1 ordinary feature/Adapter/UI work records its contract, positive journey, key negative/flag-off paths, affected integration, and regressions in the implementation plan or grouped review.
- Tier 2 state/concurrency/mutation work maintains a scoped Sol pre/post review and every applicable scenario dimension, including explicit forbidden effects.
- Tier 3 shared protocol, authority, security, durability, and production-release work maintains the complete applicable D-032 matrix plus required real-path verification. Milestone acceptance itself follows D-071: automated verification plus one complete human product acceptance.

Detailed inventories and matrices live in dated or module review records, not in STATUS. Related packages may share a review when they change one coherent boundary. STATUS links the review and carries only current state. Positive scenarios must succeed; negative scenarios must reject/fail closed, and mutation/security boundaries assert forbidden side effects as zero. Missing required evidence prevents closure of the affected scope; irrelevant dimensions are omitted or briefly scoped out rather than expanded into ceremonial rows.

## Final documentation check

Before proposing a documentation commit:

1. `git diff --check` passes.
2. Every local Markdown link under `live-voice/` resolves.
3. `docs/zh/live-voice/` contains no tracked duplicate.
4. README remains routing-only, STATUS remains the sole concise mutable state, the Web Alpha matrix contains no live status, and frozen review records are prominently marked historical so former queue, owner, schedule or carrier wording cannot override STATUS or the applicable D-046/D-052/D-053/D-055/D-058–D-063 decisions.
5. Archive warnings are present.
6. Current code, tests, decisions, roadmap, and STATUS do not contradict one another.
7. The proposed commit/push still follows the root approval gate.
