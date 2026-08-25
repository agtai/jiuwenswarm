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

## Commit and PR package

Keep three consecutive commits: source, tests, then docs. Proposed title:
“feat(agent-teams): add replayable Task commands and immutable results”.

The PR body must state command identity, exact replay/conflict behavior,
terminal result immutability and schema/restart evidence. Exclude canonical
event delivery, product confirmation/intent policy, artifact storage,
LiveVoice presentation and external effects.
