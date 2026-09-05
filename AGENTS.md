# Repository agent guidance

## Work scope and skills

User instructions and newer accepted decisions take precedence over skills and
older documents. Complete the authorized task through its required verification;
an accepted request or execution packet does not need another design, execution
method, worktree or local-commit approval. Ask only when missing information or
a new scope/authority decision actually blocks the work, and continue independent
authorized work while that issue is pending.

Use skills for their actual task-specific value. Generic workflow skills,
including Superpowers, do not impose probability-based activation, recursive
reading, extra approval gates, per-function tests, full-suite runs, micro-commits
or fixed review-loop counts on this repository. Root `TESTING.md` selects checks
and review cadence by the coherent changed boundary. Current tool schemas and
host permissions govern tool calls; skill examples do not authorize configuration,
installation, external optimization, publishing or credential disclosure.

## Git authority

Ordinary local staging and commits are authorized parts of change/build/documentation
work. Inspect status and the scoped diff, complete applicable checks/review, and
preserve unrelated user changes. Prefer one reviewable commit per coherent module,
repair or documentation decision; do not commit broken/incomplete work unless
the user explicitly requests a recovery checkpoint. At handoff report the commit
hash/message, status, diff/check summary and exclusions.

Amend, squash, rebase, cherry-pick or merge existing history only when inherent
in the requested integration/rebaseline, an accepted execution packet, or the
minimum-intervention authority below; otherwise request direction.

**Every remote-ref update requires explicit approval for that operation.** Before
push/force-push or remote branch/tag creation, update or deletion, state the exact
remote, ref, commits, update mode and whether history is rewritten. A previous
push, local commit approval or instruction to continue does not authorize another
update. A narrow advance grant must name the remote, ref, allowed mode, commits
and validity window. Workers must never push.

### Minimum intervention

An explicit request for minimum intervention or equivalent autonomous progression
also permits task-scoped local history/integration operations without repeated
approval. This persists across sessions/resume/compaction until the task closes,
scope changes or the user revokes it; “continue” alone does not activate it.
It does not expand product scope, waive checks, overwrite unrelated changes,
permit destructive/hard-to-recover operations, or grant new credential,
account/provider/billing, deployment or security-policy authority. Remote updates
remain governed by the exact grant above. Report a real blocked boundary with
the required action and recommendation while continuing unblocked work.

### Parallel ownership

For an active D-060/D-062 parallel packet, Main assigns coherent non-overlapping
work within tool capacity and remains the Integration Owner and shared semantic
owner. Historical lane assignments are dormant without a current packet.

Separate-worktree workers may commit only their task branch when their packet
grants that authority; they cannot change the integration branch, rewrite shared
history or integrate their own return. A shared-worktree subagent may edit only
its assigned files while holding the sole active filesystem-writer lease, and
cannot switch branches, stage, commit or integrate. Main reviews and performs
shared-worktree Git operations; semantic conflicts stay with Main and the owning
module. Generic worker templates do not override these limits.

## Live Voice routing and facts

Start a Live Voice task with `live-voice/README.md` and the judgement/current
packet in `live-voice/STATUS.md`; read capability rows and other sections only as
the task requires. Choose one primary README route and add only sections needed
by the touched boundaries. Reuse unchanged guidance already read in this session.
Links are conditional; historical snapshots, closed packets, numbered plans and
past runs are not a default reading list or current queue. Documentation structure
work also uses `live-voice/DOCUMENTATION_RULES.md`.

At resume verify `git status --short --branch`, `git rev-parse HEAD`, and
`git rev-list --left-right --count 'HEAD...@{upstream}'`; report an absent upstream.
Git/source is implementation fact; accepted decisions own intended behavior.
Record and repair document drift without treating existing code as final design.
Private credentials, provider/model setup, project registration, device/browser
state, runtime data and network availability are not restored by Git.

The Demo must send committed final speech to the real JiuwenSwarm Agent/tools.
ASR/TTS-only paths and other shortcuts cannot claim the full product boundary.

## Module and test closure

Use STATUS's capability/dependency model and D-084 completion boundaries. Before
implementation record intended behavior, owned product/test surfaces, risk,
dependencies, exclusions and acceptance, scaled to the change. A new classifier
or product policy, shared protocol/schema/migration, module owner or materially
broader behavior needs explicit re-scoping and re-tiering before that expansion.
Diff size is a warning signal, not a semantic acceptance criterion.

Read only applicable `TESTING.md` sections before changing code/tests. Positive
business scenarios must succeed; rejection/stale/wrong-scope paths must fail
closed with zero forbidden Agent/Tool/Task/audio/history/protected-state effects.
Missing required evidence leaves the affected scope PARTIAL/BLOCKED. Test counts
and coverage alone do not close it. Review findings are triaged when received;
only affected checks/reviews need repeating. D-071/D-072 keep signed W2 evidence
Gate tooling retired unless the user explicitly requests a new audit requirement.
