# Repository agent guidance

## Git change and remote approval policy

Ordinary local staging and commits are part of an authorized change/build/documentation task and do not require a separate per-commit approval. Before committing, inspect the relevant status and diff, run the risk-proportional checks/review required below, and preserve unrelated user changes. Prefer one reviewable commit per coherent module, bug-fix batch, integration batch, or documentation decision. Do not create tiny activity/checkpoint commits merely to show progress, and do not commit a knowingly broken or semantically incomplete state unless the user explicitly asks for a recoverable checkpoint.

At handoff, report the commit hash/message, relevant status, diff/test summary, and exclusions. Amending, squashing, rebasing, cherry-picking, merging, or otherwise rewriting/composing local history is allowed only when it is inherent in the user's requested integration/rebaseline task, an accepted execution packet, or the minimum-intervention mode below; otherwise request direction before changing existing history.

Every remote-ref update remains separately gated. Before a push, force-push, remote branch/tag creation/update/deletion, or equivalent operation, state the exact remote, ref, commits, update mode, and whether history is rewritten, then obtain the user's explicit approval for that operation. Earlier commit approval, an earlier push, or a general instruction to continue does not authorize a later remote update.

### User-activated minimum-intervention exception

When the user explicitly requests minimum intervention, autonomous progression with questions only when required, or equivalent reduced-approval handling, Main may also perform the task-scoped local history/integration operations listed above without another per-operation approval. Ordinary requests to continue do not activate this broader authority. The activation persists across Session changes, context compaction, and task resume until the named task or candidate closes, work leaves the authorized scope, or the user revokes it.

Minimum-intervention mode reduces approval round trips; it does not expand product scope, waive required tests/reviews/acceptance, permit overwriting unrelated user changes, or authorize destructive or hard-to-recover operations. It also does not authorize credential disclosure or relocation, external account/provider/billing changes, public deployment, security-policy choices, or other external effects not already inherent in the approved task. If one of those boundaries or a material product decision requires the user, continue all unblocked work and report the exact issue, why it requires intervention, the exact action needed, and a recommendation.

Remote refs are excluded unless the user separately grants a narrow remote authorization naming the exact remote, branch or tag, allowed update mode, commits, and validity window. Without that grant, every normal/force push and every remote branch/tag/ref creation, update, or deletion still requires separate exact approval. Worker Git authority remains further limited by the active packet and integration lease; a general minimum-intervention activation does not let a worker push or integrate its own return.

### Bounded Live Voice adaptive parallel ownership

When a routed Live Voice packet uses D-060/D-062 parallel execution, the number and form of workers are derived from the coherent batch; there is no fixed minimum or maximum beyond available tool capacity. Main may assign non-overlapping work to separate Sessions/worktrees, bounded subagents, or itself. Main remains the only Integration Owner, shared semantic owner, and integration-worktree history writer. These rules are dormant when no parallel packet is active; completed W2 lane assignments do not remain current Alpha assignments.

Assigned workers in separate worktrees may stage and commit only their own task branch when the active packet grants that authority; they must not change the integration branch, rewrite shared history, or integrate their own return. A subagent sharing Main's worktree may edit only its explicitly assigned non-overlapping files while holding the sole active filesystem-writer lease for that worktree; it must not switch branches, stage, commit, rewrite history, or integrate. Main reviews and performs all Git operations for shared-worktree subagent changes. Semantic conflict resolution remains with Main and the owning module boundary.

Every operation that updates a remote ref still requires separate explicit user approval for the exact remote, branch or tag, commits, and update mode. This includes normal push, force/force-with-lease push, and remote branch/tag creation, update, or deletion. A Task worker must never push. Parallel workers must honor packet ownership and the single-writer integration lease; local Git freedom does not authorize semantic conflict resolution outside the assigned owner.

## Live Voice bootstrap

For every Live Voice task, first read:

1. `live-voice/README.md` — lightweight router and authority map.
2. `live-voice/STATUS.md` — the only mutable current-state source.

Then read only the files routed for the task. Do not load every full document for ordinary module work. Documentation-structure or documentation-update work must also read `live-voice/DOCUMENTATION_RULES.md`.

When `STATUS.md` names an active S5–S8 task, read only the execution plan's common rules/dependencies and that task's section; load prerequisite sections only for a missing or conflicting dependency. Read complete acceptance at A2/A3, the showcase/runbook only for runtime acceptance, only the relevant ACG sections for a changed contract, the full design snapshot only when the long-term boundary itself is changing or ambiguous, and `live-voice/REFERENCE_INDEX.md` only for an explicit historical or forensic need.

At resume, verify Git before trusting prose: run `git status --short --branch`, `git rev-parse HEAD`, and compare the checked-out branch with its upstream. If Git and `STATUS.md` disagree, Git is the implementation fact; report and repair the documentation rather than silently following stale text.

The Demo must submit committed final speech text to the real JiuwenSwarm Agent and tools. It is not an ASR/TTS-only showcase, and shortcuts must never be described as production-complete capabilities. Credentials, model/provider configuration, project registration, browser permissions, audio-device selection, runtime data, and network availability are machine-private and are not restored by Git.

## Module and test closure

Live Voice planning follows D-075: `S0`–`S9` are sequential project stages, `A0`–`A3` are Alpha critical nodes, P1/P2/P3alpha/Shared-X are capability tracks, named components are modules, `*-A/B/C` are work packages, and W1/W2/W3/W4 are historical delivery windows rather than current calendar weeks or default queues. Every implementation packet must name its stage, target node, track/module, risk tier, scope and exclusions.

Live Voice verification follows the D-046 risk tiers and D-074 staged review cadence in `live-voice/roadmap/POST_V0_DELIVERY_ROADMAP.md`, not one universal ceremony. Documentation/mechanical work uses affected checks; ordinary feature/Adapter/UI work covers the positive journey, key negative and flag-off cases, and affected regressions; state/concurrency/mutation work covers all applicable scenario dimensions; shared protocol, authority, security and durability work uses the complete applicable D-032 matrix. A design checkpoint is required before introducing or changing a high-risk contract, but not before every correction within an already accepted boundary. Related packages may share one design checkpoint, implementation batch, module review, and commit. Detailed matrices live in review records, while `live-voice/STATUS.md` remains a short current dashboard.

D-071 retires the signed W2 evidence Gate, 38-slot manifest, `w2_gate_cli evaluate` result and Replacement Ledger as milestone completion requirements. D-072 removes that Gate implementation, runtime evidence wiring and Gate-only fault injection from the current source. W2 and later Live Voice milestones close with risk-proportional automated verification plus one complete human product acceptance on the identified tested source. Do not recreate Gate tooling or artifacts unless the user explicitly reinstates an audit-grade certification requirement; frozen historical records remain history only.

D-074 supersedes D-053's per-batch review cadence. During implementation, review the affected diff and run focused checks; a small intermediate commit does not trigger an independent review ceremony. At a coherent module or grouped-batch boundary, perform a cold review of that complete scoped diff, and require an independent `/review` or equivalent for Tier 2/3 boundaries. At a phase or milestone candidate, review the cumulative phase diff and integration seams, run the applicable broad automated verification, and complete the D-071 human product acceptance. A finding requires affected reruns; repeat only the review scope materially changed by the fix. If an independent review entry is required but unavailable, record the substitute and limitation rather than claiming it ran. Tier 0/1 work remains risk-proportional.

Positive business scenarios must succeed. Negative scenarios must be rejected or fail closed, and forbidden side effects must be asserted as zero for any path that can mutate Agent, Tool, Task, audio/history authority, protected state, or another scope. Test counts or line coverage alone do not prove closure. Missing required risk evidence leaves the affected scope `PARTIAL` or `BLOCKED`, but inapplicable matrix dimensions need not be manufactured for low-risk work.

User instructions and newer accepted decisions take precedence. If code and documents disagree, record the gap instead of treating current code as the intended final design.
