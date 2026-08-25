# AgentCore PR 09: bound TeamTask authority implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:test-driven-development while replaying this plan, then use
> superpowers:requesting-code-review before declaring the local package ready.

**Goal:** Expose the least-privilege, session-bound public TeamTask API needed
by downstream products without exporting TaskDao or TeamTaskManager.

**Architecture:** TeamAgent.task_authority returns TeamTaskAuthority bound to
the exact Team/member/session lifecycle. The facade validates and projects
canonical snapshots, command decisions, events, cursors and checkpoint
records. Session release or rebinding invalidates the handle.

**Risk and dependency:** Tier 3 public authority boundary. Depends on PR 01,
03, 04, 05, 06 and 08. The review-only source diff is
2cc81078..503cf538 on codex/ac-pr09-bound-task.

## Owned surfaces

- Public facade/export: openjiuwen/agent_teams/task_authority.py,
  openjiuwen/agent_teams/__init__.py and
  openjiuwen/agent_teams/agent/team_agent.py.
- Lifecycle: openjiuwen/agent_teams/agent/session_manager.py.
- Narrow subordinate verification support: schema/task.py,
  tools/database/cursor_dao.py, tools/database/task_dao.py,
  tools/database/engine.py, tools/models.py and tools/task_manager.py.
- Primary tests: tests/unit_tests/agent_teams/test_task_authority.py,
  test_task_authority_checkpoint.py and test_session_manager.py.
- Historical candidate docs are F_89/S_31 and F_90/S_32; allocate fresh names
  at replay (tentatively F_107/S_34 and F_108/S_35).

## Contract

- TeamTaskAuthorityBinding fixes session_id, team_name and member_name.
  Executor capability is a facade property derived from the bound manager, not
  a field that callers can place in the binding.
- TeamTaskAuthority exposes get, list, apply_update, get_event_head,
  read_events, read_unread, advance_cursor, publish_execution_checkpoint and
  read_current_execution_checkpoint.
- CanonicalTeamTask, CanonicalTaskExecution, CanonicalTaskSnapshot,
  CanonicalTaskResultRef and CanonicalTaskCommandDecision are verified public
  projections, not storage rows.
- Foreign ambient session, released handle, binding drift, malformed
  subordinate results, incomplete event history and corrupt checkpoint source
  fail before returning authority or writing.
- task_authority/checkpoint quality corrections from fbfb4c5f belong here.

## Replay and verification

1. Rebase after all declared dependencies and record their SHAs.
2. Restore the three primary tests from f927f86c/503cf538 plus owned
   fbfb4c5f corrections; run before implementation and record red:

       uv run pytest tests/unit_tests/agent_teams/test_task_authority.py tests/unit_tests/agent_teams/test_task_authority_checkpoint.py tests/unit_tests/agent_teams/test_session_manager.py -q

3. Reimplement 9cc5727e and 503cf538 as one coherent public-boundary PR; fold
   only owned fbfb4c5f hunks.
4. Rerun primary tests plus PR 04/05/06/08 affected public-boundary suites.
5. Run root-export lock tests, file-backed SQLite bind/reopen/concurrency cases,
   changed-file Ruff/format, isolated Mypy for task_authority.py, compileall and
   git diff --check.
6. Obtain Tier-3 review focused on session-context restoration, least
   privilege, projection verification and avoidance of DAO/Manager exposure.

## Commit and PR package

Keep three consecutive commits: source, tests, then docs. Proposed title:
“feat(agent-teams): expose a session-bound TeamTask authority”.

The PR body must explain bound lifecycle, public verified projections,
checkpoint seam and fail-closed subordinate validation. Exclude external
effects, LiveVoice intent/confirmation, product response and presentation
state, composition activation and direct DAO/Manager exports.
