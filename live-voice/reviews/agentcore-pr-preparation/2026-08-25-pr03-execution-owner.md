# AgentCore PR 03: durable Task execution ownership implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:test-driven-development while replaying this plan, then use
> superpowers:requesting-code-review before declaring the local package ready.

**Goal:** Establish one durable, scoped execution identity and token-fenced
admission/settlement authority for every running TeamTask attempt.

**Architecture:** TeamExecutionAttemptBase and TaskDao are canonical storage;
TeamTaskManager exposes prepare/start/claim/reconcile and terminal operations.
Scheduler/Team integrations consume the exact execution token. AsyncTool
quiescence precedes durable cancellation or reset.

**Risk and dependency:** Tier 3 shared authority/schema/concurrency change.
Depends on PR 01 scope and the PR 02 cancellation contract. The review-only
source diff is 5c3ef668..6551d023 on
codex/ac-pr03-execution-owner.

## Owned surfaces

- Core schema/storage: openjiuwen/agent_teams/schema/task.py,
  tools/models.py, tools/database/engine.py and tools/database/task_dao.py.
- Runtime: tools/task_manager.py, tools/team.py,
  agent/scheduling/scheduler.py and harness/async_tools.py.
- Primary tests:
  tests/unit_tests/agent_teams/test_task_execution_ownership.py and
  harness/test_async_tools.py.
- Affected tests: test_database.py, test_task_manager.py,
  test_review_voting.py, test_team.py and tools/test_tool_variants.py.
- Historical candidate docs are F_83/S_25; those identifiers now collide or
  precede current allocation. Rename them at replay (tentatively F_101/S_28
  after PR 01/02), plus narrowly update S_12, S_20, S_22 and the final PR 01
  Task-scope spec.

## Contract

- TaskExecutionRecord/TaskExecutionOpResult identify team, task, execution,
  owner, owner_epoch, generation/profile and terminal outcome.
- TaskDao and TeamTaskManager expose get_execution, get_execution_by_id,
  prepare_execution, start_execution, claim_execution and reconcile_execution.
- Only the current exact attempt token can authorize phase effects or terminal
  settlement; stale, foreign, ownerless and superseded attempts write nothing.
- reset/cancel waits for owned runtime quiescence before releasing authority.
- Quality hunks in fbfb4c5f for execution-ownership tests must be folded here.
  The 50c065dc TaskManager lint hunk belongs only to PR 01.

## Replay and verification

1. Rebase after accepted PR 01/02 contracts and record all dependency SHAs.
2. Restore test_task_execution_ownership.py and the owned AsyncTool tests from
   6095e350; run before implementation and record red:

       uv run pytest tests/unit_tests/agent_teams/test_task_execution_ownership.py tests/unit_tests/agent_teams/harness/test_async_tools.py -q

3. Reimplement 9b9f1c3b by owner boundary, including migrations for existing
   Task tables; preserve upstream session-file columns/hydration and
   write-locked session DDL, then fold only the owned fbfb4c5f hunks.
4. Run the primary tests plus every affected file above, then repeat the
   contention/reset/review-race selections without sleep-based proof.
5. Compile dynamic DDL for supported dialects; run real file-backed SQLite
   reopen/concurrency cases, Ruff, isolated Mypy for added pure types,
   compileall and git diff --check.
6. Obtain Tier-3 review of transaction linearization, stale-token zero effects,
   legacy-row fail-closed behavior and rollback boundaries.

## Commit and PR package

Keep three consecutive commits: source, tests, then docs. Proposed title:
“feat(agent-teams): add durable Task execution ownership”.

The PR body must describe exact attempt identity, CAS admission/settlement,
runtime quiescence and migration/restart/concurrency evidence. Exclude command
replay, canonical events, product launch policy, LiveVoice identity and canary
or data migration outside the AgentCore schema migration itself.
