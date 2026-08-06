# Repository agent guidance

## Mandatory Git approval gate

Do not create, amend, squash, rebase, cherry-pick, merge, or otherwise produce a Git commit without the user's explicit approval for the exact intended scope and proposed commit message. Do not push, force-push, delete, or otherwise update a remote ref without separate explicit approval for that exact remote operation. Earlier approval does not carry over to later Git operations.

Before requesting commit approval, leave changes uncommitted and show the relevant status plus a concise diff/test summary and exclusions. Before requesting push approval, state the exact remote, branch, commits, and whether the push is normal or rewrites history. If approval is missing or ambiguous, stop before the Git operation.

### Bounded Live Voice Alpha parallel exception

The user's accepted [Live Voice Alpha parallel execution plan](live-voice/roadmap/ALPHA_PARALLEL_EXECUTION_2026-08-06.md) is a task-scoped exception to the local-operation portion of the approval gate above. While that plan is active, its Main Integration Session and assigned Task Sessions may stage, commit, amend, squash, rebase, merge, cherry-pick, create or update local branches/refs/worktrees, and perform lease-governed local task integration without another user approval. This exception applies only to the plan's declared Live Voice Alpha scopes and ends when its immutable local Alpha candidate is closed, the user revokes it, or work leaves those scopes. The default gate applies everywhere else.

Every operation that updates a remote ref still requires separate explicit user approval for the exact remote, branch or tag, commits, and update mode. This includes normal push, force/force-with-lease push, and remote branch/tag creation, update, or deletion. A Task Session must never push. Parallel Sessions must honor the plan's file ownership and obtain the single-writer integration lease before modifying the integration worktree; local Git freedom does not authorize semantic conflict resolution outside the assigned owner.

## Live Voice bootstrap

For every Live Voice task, first read:

1. `live-voice/README.md` — lightweight router and authority map.
2. `live-voice/STATUS.md` — the only mutable current-state source.

Then read only the files routed for the task. Do not load every full document for ordinary module work. Documentation-structure or documentation-update work must also read `live-voice/DOCUMENTATION_RULES.md`.

At resume, verify Git before trusting prose: run `git status --short --branch`, `git rev-parse HEAD`, and compare the checked-out branch with its upstream. If Git and `STATUS.md` disagree, Git is the implementation fact; report and repair the documentation rather than silently following stale text.

The Demo must submit committed final speech text to the real JiuwenSwarm Agent and tools. It is not an ASR/TTS-only showcase, and shortcuts must never be described as production-complete capabilities. Credentials, model/provider configuration, project registration, browser permissions, audio-device selection, runtime data, and network availability are machine-private and are not restored by Git.

## Module and test closure

Live Voice verification follows the D-046 risk tiers in `live-voice/roadmap/POST_V0_DELIVERY_ROADMAP.md`, not one universal ceremony. Documentation/mechanical work uses affected checks; ordinary feature/Adapter/UI work covers the positive journey, key negative and flag-off cases, and affected regressions; state/concurrency/mutation work receives a scoped Sol pre/post review and all applicable scenario dimensions; shared protocol, authority, security, durability, and release Gates use the complete D-032 matrix and immutable evidence. Related packages may share one design checkpoint, implementation batch, post-review, and commit. Detailed design matrices live in review records, while `live-voice/STATUS.md` remains a short current dashboard.

D-053 requires every coherent Tier 2/3 Live Voice implementation batch to complete three review passes before acceptance: implementation self-review, a cold review of the complete diff against the original request/repository rules/existing behavior/actual tests, and an independent `/review` or equivalent independent review entry. Fix findings and rerun affected tests after each pass; if a fix materially changes semantics, repeat the final cold complete-diff review. If `/review` is unavailable, record the exact substitute and limitation rather than claiming that `/review` ran. Tier 0/1 work remains risk-proportional and does not acquire a universal three-review ceremony.

Positive business scenarios must succeed. Negative scenarios must be rejected or fail closed, and forbidden side effects must be asserted as zero for any path that can mutate Agent, Tool, Task, audio/history authority, protected state, or another scope. Test counts or line coverage alone do not prove closure. Missing required risk evidence leaves the affected scope `PARTIAL` or `BLOCKED`, but inapplicable matrix dimensions need not be manufactured for low-risk work.

User instructions and newer accepted decisions take precedence. If code and documents disagree, record the gap instead of treating current code as the intended final design.
