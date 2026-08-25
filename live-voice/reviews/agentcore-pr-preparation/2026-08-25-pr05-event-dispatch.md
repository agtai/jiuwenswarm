# AgentCore PR 05: canonical Task events and dispatch implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:test-driven-development while replaying this plan, then use
> superpowers:requesting-code-review before declaring the local package ready.

**Goal:** Commit canonical Task events and execution-launch dispatch truth in
the same transactions as their owning Task mutations.

**Architecture:** An append-only TeamTask event stream provides ordered Task
facts. A durable dispatch row tracks claim, authorization, delivery resolution
and reconciliation for launch delivery; the scheduler drains it without
minting its own Task authority.

**Risk and dependency:** Tier 3 transaction, delivery and mutation authority.
Depends on PR 03 and PR 04. The review-only source diff is
55b13458..473ad7cf on codex/ac-pr05-event-dispatch.

## Owned surfaces

- Schema/storage: openjiuwen/agent_teams/schema/task.py,
  tools/models.py, tools/database/engine.py and tools/database/task_dao.py.
- Runtime: tools/task_manager.py and agent/scheduling/scheduler.py.
- Primary test:
  tests/unit_tests/agent_teams/test_task_event_dispatch.py.
- Affected test:
  tests/unit_tests/agent_teams/test_task_command_result.py.
- Historical candidate docs are F_85/S_27; allocate fresh names at replay
  (tentatively F_103/S_30) and update the final PR 04 feature only where the
  transaction boundary changes.

## Contract

- TaskEventEnvelope/TaskEventPage expose canonical, contiguous, scoped Task
  facts through get_task_event_head and read_task_events.
- TaskDispatchRecord/TaskDispatchOpResult support get, claim, authorize,
  complete, release, reject, mark-reconcile, reconcile and expired-claim reap.
- Task mutation, emitted event and required launch dispatch commit or roll back
  together.
- An expired/foreign/stale dispatch token has zero launch or ledger effects;
  ambiguous delivery cannot be retried as known-not-sent.
- Product response, voice, Web, DOM and playout events are excluded.
- The fbfb4c5f event-dispatch test hunks are folded here. Its sole
  command-result formatting hunk belongs only to PR 04.

## Replay and verification

1. Rebase after PR 03/04 and record dependency SHAs.
2. Restore test_task_event_dispatch.py from f401d2a4 and run it with the
   dependent command-result suite before implementation; record red:

       uv run pytest tests/unit_tests/agent_teams/test_task_event_dispatch.py tests/unit_tests/agent_teams/test_task_command_result.py -q

3. Reimplement 78b4a36c and fold only its event-dispatch fbfb4c5f corrections.
4. Rerun both files, repeat dispatch claimant/expiry/precommit-failure races,
   and verify every legacy Task writer emits canonical events.
5. Run supported-dialect DDL compilation, file-backed SQLite reopen and
   rollback cases, changed-file Ruff, compileall and git diff --check.
6. Obtain Tier-3 review focused on atomicity, contiguous sequence allocation,
   dispatch ambiguity, authorization consumption and forbidden launch effects.

## Commit and PR package

Keep three consecutive commits: source, tests, then docs. Proposed title:
“feat(agent-teams): add canonical Task events and transactional dispatch”.

The PR body must explain atomic Task/event/dispatch publication, delivery-token
fencing and recovery evidence. Exclude consumer cursors, response/presentation
receipts, product launch selection, LiveVoice policy and external effects.
