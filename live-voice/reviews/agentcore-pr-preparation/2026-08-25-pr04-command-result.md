# AgentCore PR 04: Task command and immutable result implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:test-driven-development while replaying this plan, then use
> superpowers:requesting-code-review before declaring the local package ready.

**Goal:** Make scoped Task commands replayable and terminal execution results
immutable under the exact current execution authority.

**Architecture:** A TeamTask command ledger records request fingerprint and
decision; the execution row stores one immutable terminal outcome/result
reference. TaskDao performs the transaction and TeamTaskManager validates and
forwards intent without owning a second ledger.

**Risk and dependency:** Tier 3 durable command/mutation authority. Depends on
PR 01 and PR 03. The review-only source diff is
6551d023..55b13458 on codex/ac-pr04-command-result.

## Owned surfaces

- Schema/storage: openjiuwen/agent_teams/schema/status.py,
  schema/task.py, tools/models.py, tools/database/engine.py,
  tools/database/graph.py and tools/database/task_dao.py.
- Runtime: tools/task_manager.py and agent/scheduling/scheduler.py.
- Terminal consumers: agent/coordination/handlers/task_board.py and
  external/format.py; their focused tests become affected surfaces because the
  five-state terminal set changes actionable/incomplete projections.
- Primary test:
  tests/unit_tests/agent_teams/test_task_command_result.py.
- Affected tests: agent/test_team_scheduler.py, test_database.py and
  test_team.py.
- Historical candidate docs are F_84/S_26; allocate fresh names at replay
  (tentatively F_102/S_29 after PR 03).

## Contract

- TaskCommandOperation, TaskCommandRecord and TaskCommandOpResult define exact
  replay identity and durable accepted/rejected/no-op decisions.
- TaskDao/TeamTaskManager apply_command returns the original decision for an
  exact replay and rejects changed facts under the same command ID.
- ExecutionOutcome and TaskResultRef settle once for the exact current
  execution; a stale token, wrong Team or conflicting result writes nothing.
- Result references are bounded and opaque; AgentCore does not interpret
  LiveVoice response, media, DOM or project artifacts.
- The PR-owned test_task_command_result hunks from fbfb4c5f are folded here.

## Replay and verification

1. Rebase after PR 01/03 and record dependency SHAs.
2. Restore test_task_command_result.py from 64447e9e, run it without
   implementation and record red:

       uv run pytest tests/unit_tests/agent_teams/test_task_command_result.py -q

3. Reimplement 4a68fd8a, including current upstream migration style, and fold
   only its fbfb4c5f test corrections.
4. Run the primary test plus scheduler/database/team affected tests.
5. Run dynamic-schema compilation for supported dialects, file-backed SQLite
   restart/concurrency/rollback cases, changed-file Ruff, compileall and
   git diff --check.
6. Obtain Tier-3 review focused on replay conflicts, immutable results,
   terminal races, child dependency unblocking and zero side effects.

## Replay preflight — 2026-08-25

The refreshed dependency base has not drifted beyond the local PR 01 base:
`origin/develop` remains `6390bbf2` and the local PR 01 head is `c88f1ed3`.
PR 03 is technically ready but remains an uncommitted isolated candidate because
the repository-required real issue reference has not been supplied. Therefore
PR 04 must not be layered into the PR 03 worktree or opened as a formal replay
branch yet. The historical `codex/ac-pr04-command-result` ref remains read-only
evidence until PR 03 has a reviewable three-commit package.

The historical source cannot be replayed mechanically. Reimplementation must:

- extend the current PR 03 `_terminate_task_in_session` contract instead of
  replacing it, preserving owned-runtime quiescence for cancellation and the
  explicit recoverable/orphaned recovery boundary. Natural runtime completion
  may use the current owned token; owned cancellation requires the
  quiescence-proven internal seam; prepared cancellation and any explicit
  recoverable/orphaned settlement retain their separately named policies;
- carry the caller-held `expected_review_round` through any IN_REVIEW terminal
  settlement and compare it in the final Task CAS; exact replay must not let an
  old review callback settle a later round;
- expand the PR 03 relation-less version-0 terminal delete fence to the complete
  PR 04 terminal set, so failed/interrupted/unknown cannot reopen the same-ID
  delete/recreate ABA path;
- keep execution and command identities as session-domain tombstones across
  ordinary Task deletion and normal Team clean. The historical command-table
  Team cascade must not be restored; only explicit session-domain destruction
  may retire the ledger identity. Exact command/result lookup must consult that
  durable identity before touching a current or same-ID rebuilt Task; exact
  facts replay the frozen record, conflicts fail, and only a genuinely new
  identity may reach current Task mutation;
- serialize `apply_command` against `Team.deletion_reservation_id`, so normal
  clean cannot commit a Task mutation or emit a legacy update effect while the
  Team domain is reserved for deletion;
- preserve current SessionFileStore hydration. A content command must compare
  the logical hydrated value and must not overwrite/create a session file on
  malformed, wrong-scope, stale, conflict, rejection, no-op or replay paths.
  The historical candidate proposed a 255-character content limit, but that is
  not an accepted current Task-content boundary and must not silently narrow the
  SessionFileStore contract. A possible design is an explicitly reviewed,
  bounded inline SQL update; its accepted bound, compatibility and migration
  effects still require a decision, and the prior session file would become an
  unreferenced session-local artifact rather than mutated Task truth. If no
  compatible inline bound or equally atomic file strategy is accepted, the
  replay scope must be reduced to title-only rather than claiming content
  replay; and
- inventory every consumer of terminal Task state. Historical TaskBoard nudge
  and external formatting logic still hard-code completed/cancelled and must
  adopt the shared five-state terminal set with positive/negative tests;
- preserve current-session `DbSessions.write()` DDL locking, candidate-table
  migration snapshots, watchdog/retry behaviour and Team deletion reservation;
  only the command/result schema semantics may be replayed from the historical
  engine patch; and
- keep `TaskDao`/`TeamTaskManager` and schema symbols module-level/internal
  callable seams. Package public authority remains owned by the later bound
  facade packet.

One command-ordering decision remains open and must be frozen before the red
suite is restored. The historical `expected_task_version` is only the execution
generation fence and an accepted UPDATE does not advance it. Therefore two
different command IDs with the same expected version may both apply, including
non-deterministic last-writer behaviour for the same field. The replay must
either document/test that deliberately limited policy (and grant no general
mutation-precondition credit), or explicitly re-scope to a separate monotonic
Task-mutation revision. It must not leave the policy implicit.

In addition to the historical primary matrix, the Tier-3 red/green replay must
cover:

- a real running AsyncTool proving owned cancellation cannot settle or release
  Task authority before quiescence;
- owned/prepared/recoverable/orphaned disposition crossed with every proposed
  outcome, proving only the explicitly authorized matrix can change Task,
  attempt, result, dependency or event truth;
- old-round terminal settlement racing a fail/resubmit into a later review
  round, with zero Task/attempt/result/event change from the old callback;
- wrong-Team Task/execution/result settlement with same identifiers, proving no
  foreign Task, attempt, result, dependency or event change;
- all five relation-less version-0 terminal states followed by ordinary delete,
  same-ID recreation and a late no-token callback;
- same command ID concurrent first writes with exact facts (one mutation/event,
  one replay) and conflicting task/fingerprint/payload/version facts (one
  winner, loser zero Task/ledger-winner/event/file side effects);
- command precheck paused while reset, terminal settlement, version change or
  delete wins, proving the final CAS leaves Task/attempt/dependency/event/file
  unchanged for the stale command;
- normal Team clean racing command application, plus command identity replay or
  conflict after ordinary Team/Task delete and same-ID recreation;
- terminal Task/attempt/result replay or conflict after ordinary Task/Team
  deletion and same-ID rebuild, proving the rebuilt Task is unchanged;
- hydrated equal-content accepted no-op and rejected/replayed content commands
  with unchanged authoritative file bytes and zero duplicate event; and
- current supported-dialect DDL proving the command ledger has no ordinary Team
  cascade while explicit session cleanup still removes it;
- failed/interrupted/unknown coverage in TaskBoard nudge, external formatting,
  scheduler remaining count, Team completion, cancel-all and dependency
  handling; and
- a declared two-command/same-expected-version policy, with a deterministic
  race oracle matching the selected contract.

Historical tests are evidence, not accepted fixtures. Cases that directly
reset/cancel an owned attempt or use generic status mutation to enter active
state conflict with PR 03 and must be rebuilt through real admission,
runtime-quiescence internal settlement, or explicit migration fixtures. The
implementation must never reopen a prohibited public path merely to preserve an
old green test.

With PR 03 documents present, the next tentative names have been recalculated as
`F_102` and `S_29`; they must be counted again immediately before the docs
commit.

## Commit and PR package

Keep three consecutive commits: source, tests, then docs. Proposed title:
“feat(agent-teams): add replayable Task commands and immutable results”.

The PR body must state command identity, exact replay/conflict behavior,
terminal result immutability and schema/restart evidence. Exclude canonical
event delivery, product confirmation/intent policy, artifact storage,
LiveVoice presentation and external effects.
