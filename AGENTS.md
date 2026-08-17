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

For every Live Voice task, first read `live-voice/README.md` and
`live-voice/STATUS.md`, then follow exactly one README route. Documentation
structure/update work also reads `live-voice/DOCUMENTATION_RULES.md`. Do not
load complete acceptance, runbooks, architecture or history unless the selected
route requires them; numbered delivery plans are not the current queue.

At resume, verify Git before trusting prose: run `git status --short --branch`, `git rev-parse HEAD`, and compare the checked-out branch with its upstream. If Git and `STATUS.md` disagree, Git is the implementation fact; report and repair the documentation rather than silently following stale text.

The Demo must submit committed final speech text to the real JiuwenSwarm Agent and tools. It is not an ASR/TTS-only showcase, and shortcuts must never be described as production-complete capabilities. Credentials, model/provider configuration, project registration, browser permissions, audio-device selection, runtime data, and network availability are machine-private and are not restored by Git.

## Module and test closure

Current planning follows the D-084 completion boundaries and the capability/
dependency model in `live-voice/STATUS.md`. Every implementation packet names
its capability/module, risk tier, dependencies, scope, exclusions and
acceptance. Historical stages/windows cannot define current priority.

Root `TESTING.md` is the complete authority for D-032/D-046/D-074 risk,
scenario, review and evidence rules. Read only its applicable sections before
changing code or tests. D-071/D-072 keep the signed W2 evidence Gate and its
tooling retired; do not recreate them without an explicit new audit requirement.

Positive business scenarios must succeed. Negative scenarios must be rejected or fail closed, and forbidden side effects must be asserted as zero for any path that can mutate Agent, Tool, Task, audio/history authority, protected state, or another scope. Test counts or line coverage alone do not prove closure. Missing required risk evidence leaves the affected scope `PARTIAL` or `BLOCKED`, but inapplicable matrix dimensions need not be manufactured for low-risk work.

User instructions and newer accepted decisions take precedence. If code and documents disagree, record the gap instead of treating current code as the intended final design.
