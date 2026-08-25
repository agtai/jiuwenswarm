# AgentCore PR 01: mandatory TeamTask scope implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:test-driven-development while replaying this plan, then use
> superpowers:requesting-code-review before declaring the local package ready.

**Goal:** Make every TaskDao operation that addresses an existing Task by ID
require Team identity, and prove wrong-Team requests have zero effects.

**Architecture:** TeamTask identity is (team_name, task_id). TaskDao enforces
that boundary; TeamTaskManager and existing callers only propagate scope. This
PR introduces no new product policy or public LiveVoice API.

**Risk and dependency:** Tier 3 authority/isolation change. Rebase directly on
the then-current AgentCore develop. The review-only source diff is
4f2c29c3..ced87a3e on codex/ac-pr01-task-scope.

## Owned surfaces

- Production:
  openjiuwen/agent_teams/tools/database/task_dao.py,
  openjiuwen/agent_teams/tools/task_manager.py,
  openjiuwen/agent_teams/agent/coordination/handlers/message.py,
  openjiuwen/agent_teams/external/client.py, and
  openjiuwen/agent_teams/monitor/team_monitor.py.
- Primary tests:
  tests/unit_tests/agent_teams/test_database.py,
  tests/unit_tests/agent_teams/test_database_concurrency.py, and
  tests/unit_tests/agent_teams/test_task_manager.py.
- Affected caller tests: external/test_cli.py, external/test_mcp_server.py,
  test_review_voting.py, test_team.py, test_team_tools.py, test_verify_gate.py,
  tools/test_tool_variants.py, and the upstream-added
  team_workspace/test_session_file_store.py.
- Historical candidate docs are S_24_task-storage-scope.md and
  F_82_task-storage-scope.md. Those identifiers now collide upstream; allocate
  fresh names at replay (tentatively S_27/F_99 at 6390bbf2) and repair links.

## Contract

- get_task, reassign_task, reset_task, review/status/dependency mutations,
  delete_task, cancel_task and complete_task require keyword-only team_name.
- A known foreign task_id must behave as unauthorized/not found and must not
  mutate Task, dependency, review, event, message or scheduler state.
- No compatibility overload may infer Team scope from a globally unique Task
  ID.

## Replay and verification

1. Create a fresh replay branch from current develop and record the base SHA.
2. Restore only the primary test changes from 660f3d56, run them before source
   changes, and retain the expected wrong-Team failures as red evidence:

       uv run pytest tests/unit_tests/agent_teams/test_database.py tests/unit_tests/agent_teams/test_database_concurrency.py tests/unit_tests/agent_teams/test_task_manager.py -q

3. Implement the smallest TaskDao signature/query changes from 21d8ca94 and
   propagate explicit team_name through the listed callers while preserving
   upstream session-file spill/hydration. Incorporate only the PR-owned
   TaskManager test lint hunks from 50c065dc.
4. Rerun the primary command, then all affected caller tests listed above.
5. Run Ruff lint/format checks on changed Python, compileall for
   openjiuwen/agent_teams, supported-dialect SQL compilation tests, upstream
   session-file Task tests, and git diff --check.
6. Obtain a fresh Tier-3 review focused on cross-Team reads/writes, hidden
   global-ID fallbacks and zero-side-effect assertions.

## Commit and PR package

Keep three consecutive commits: source, tests, then docs. Proposed title:
“fix(agent-teams): enforce Team scope for Task storage operations”.

The PR body must state: Task identity is Team-scoped; all existing ID-based
operations now require explicit scope; wrong-Team positive knowledge grants no
read or mutation authority; caller propagation and SQLite/concurrency evidence
are included. Exclude schema redesign, execution ownership, LiveVoice policy,
migration/cutover and remote deployment.
