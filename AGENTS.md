# Repository agent guidance

## Mandatory Git approval gate

Do not create, amend, squash, rebase, cherry-pick, merge, or otherwise produce a Git commit without the user's explicit approval for the exact intended scope and proposed commit message. Do not push, force-push, delete, or otherwise update a remote ref without separate explicit approval for that exact remote operation. Earlier approval does not carry over to later Git operations.

Before requesting commit approval, leave changes uncommitted and show the relevant status plus a concise diff/test summary and exclusions. Before requesting push approval, state the exact remote, branch, commits, and whether the push is normal or rewrites history. If approval is missing or ambiguous, stop before the Git operation.

### User-activated minimum-intervention exception

When the user explicitly requests minimum intervention, autonomous progression with questions only when required, or equivalent reduced-approval handling, that mode is a task-scoped exception to the local-operation portion of the approval gate above. Within the already authorized goal and active routed packet, Main may choose coherent commit scopes and messages and may stage, commit, amend, squash, rebase, merge, cherry-pick, and create or update local branches/refs/worktrees without another per-operation approval. Ordinary requests to continue do not activate this mode. The activation persists across Session changes, context compaction, and task resume until the named task or candidate closes, work leaves the authorized scope, or the user revokes it.

Minimum-intervention mode reduces approval round trips; it does not expand product scope, waive required tests/reviews/acceptance, permit overwriting unrelated user changes, or authorize destructive or hard-to-recover operations. It also does not authorize credential disclosure or relocation, external account/provider/billing changes, public deployment, security-policy choices, or other external effects not already inherent in the approved task. If one of those boundaries or a material product decision requires the user, continue all unblocked work and report the exact issue, why it requires intervention, the exact action needed, and a recommendation.

Remote refs are excluded unless the user separately grants a narrow remote authorization naming the exact remote, branch or tag, allowed update mode, and validity window. Without that grant, every normal/force push and every remote branch/tag/ref creation, update, or deletion still requires separate exact approval. Worker Git authority remains further limited by the active packet and integration lease; a general minimum-intervention activation does not let a worker push or integrate its own return.

### Bounded Live Voice adaptive parallel exception

The user's accepted D-060/D-062 execution decisions and the active routed Live Voice execution packet are a task-scoped exception to the local-operation portion of the approval gate above; D-063 also records that minimum-intervention mode is active for the current W2→Alpha execution. The number and form of workers are derived from each coherent batch; there is no fixed minimum or maximum beyond available tool capacity. Main may assign non-overlapping work to separate Sessions/worktrees, bounded subagents, or itself. Main remains the only Integration Owner, shared semantic owner, and integration-worktree history writer.

While this exception is active, Main may perform the listed local Git operations and lease-governed integration without another user approval. Assigned workers in separate worktrees may stage, commit, amend, squash, rebase, and create or update only their own local task branches/refs/worktrees; they must not change the integration branch or integrate their own return. A subagent sharing Main's worktree may edit only its explicitly assigned non-overlapping files while holding the sole active filesystem-writer lease for that worktree; it must not switch branches, stage, commit, rewrite history, or integrate. Main reviews and performs all Git operations for shared-worktree subagent changes. This exception applies only to the active packet's declared Live Voice W2/Alpha scopes and ends when the applicable milestone is accepted under D-071, the user revokes it, or work leaves those scopes. The default Git approval gate applies everywhere else.

Every operation that updates a remote ref still requires separate explicit user approval for the exact remote, branch or tag, commits, and update mode. This includes normal push, force/force-with-lease push, and remote branch/tag creation, update, or deletion. A Task worker must never push. Parallel workers must honor packet ownership and the single-writer integration lease; local Git freedom does not authorize semantic conflict resolution outside the assigned owner.

## Live Voice bootstrap

For every Live Voice task, first read:

1. `live-voice/README.md` — lightweight router and authority map.
2. `live-voice/STATUS.md` — the only mutable current-state source.

Then read only the files routed for the task. Do not load every full document for ordinary module work. Documentation-structure or documentation-update work must also read `live-voice/DOCUMENTATION_RULES.md`.

At resume, verify Git before trusting prose: run `git status --short --branch`, `git rev-parse HEAD`, and compare the checked-out branch with its upstream. If Git and `STATUS.md` disagree, Git is the implementation fact; report and repair the documentation rather than silently following stale text.

The Demo must submit committed final speech text to the real JiuwenSwarm Agent and tools. It is not an ASR/TTS-only showcase, and shortcuts must never be described as production-complete capabilities. Credentials, model/provider configuration, project registration, browser permissions, audio-device selection, runtime data, and network availability are machine-private and are not restored by Git.

## Module and test closure

Live Voice verification follows the D-046 risk tiers in `live-voice/roadmap/POST_V0_DELIVERY_ROADMAP.md`, not one universal ceremony. Documentation/mechanical work uses affected checks; ordinary feature/Adapter/UI work covers the positive journey, key negative and flag-off cases, and affected regressions; state/concurrency/mutation work receives a scoped Sol pre/post review and all applicable scenario dimensions; shared protocol, authority, security and durability work uses the complete applicable D-032 matrix. Related packages may share one design checkpoint, implementation batch, post-review, and commit. Detailed design matrices live in review records, while `live-voice/STATUS.md` remains a short current dashboard.

D-071 retires the signed W2 evidence Gate, 38-slot manifest, `w2_gate_cli evaluate` result and Replacement Ledger as milestone completion requirements. W2 and later Live Voice milestones close with risk-proportional automated verification plus one complete human product acceptance on the identified tested source. Do not create, repair or sign Gate artifacts unless the user explicitly reinstates an audit-grade certification requirement. Historical Gate tooling and records may remain for diagnostics and forensics, but they do not block delivery.

D-053 requires every coherent Tier 2/3 Live Voice implementation batch to complete three review passes before acceptance: implementation self-review, a cold review of the complete diff against the original request/repository rules/existing behavior/actual tests, and an independent `/review` or equivalent independent review entry. Fix findings and rerun affected tests after each pass; if a fix materially changes semantics, repeat the final cold complete-diff review. If `/review` is unavailable, record the exact substitute and limitation rather than claiming that `/review` ran. Tier 0/1 work remains risk-proportional and does not acquire a universal three-review ceremony.

Positive business scenarios must succeed. Negative scenarios must be rejected or fail closed, and forbidden side effects must be asserted as zero for any path that can mutate Agent, Tool, Task, audio/history authority, protected state, or another scope. Test counts or line coverage alone do not prove closure. Missing required risk evidence leaves the affected scope `PARTIAL` or `BLOCKED`, but inapplicable matrix dimensions need not be manufactured for low-risk work.

User instructions and newer accepted decisions take precedence. If code and documents disagree, record the gap instead of treating current code as the intended final design.
