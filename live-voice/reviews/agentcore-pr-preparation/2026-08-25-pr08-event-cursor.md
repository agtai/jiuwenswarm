# AgentCore PR 08: Task-event consumer cursor implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:test-driven-development while replaying this plan, then use
> superpowers:requesting-code-review before declaring the local package ready.

**Goal:** Let a scoped generic consumer read and atomically acknowledge the
canonical TeamTask event stream with exact replay and corruption fencing.

**Architecture:** CursorDao owns durable (Team, consumer, channel) position and
advance receipts. It verifies the canonical event prefix before returning
unread pages or advancing with CAS. TaskManager exposes the generic operations;
it does not interpret product delivery.

**Risk and dependency:** Tier 3 durable consumer authority. Depends on PR 05
canonical events, but not on checkpoint or external-effect semantics. The
review-only source diff is 8f30c02c..2cc81078 on
codex/ac-pr08-event-cursor.

## Owned surfaces

- Schema/storage: openjiuwen/agent_teams/schema/task.py,
  tools/models.py, tools/database/cursor_dao.py,
  tools/database/__init__.py and tools/database/engine.py.
- Runtime/export: tools/task_manager.py and openjiuwen/agent_teams/__init__.py.
- Primary test:
  tests/unit_tests/agent_teams/test_task_event_cursor.py.
- Historical candidate docs are F_88/S_30; allocate fresh names at replay
  (tentatively F_106/S_33).

## Contract

- TaskEventCursorPosition, TaskEventUnreadPage and
  TaskEventCursorAdvanceResult are scoped to exact Team, consumer and channel.
- CursorDao.read_unread verifies canonical ordered events and returns a stable
  page; advance uses advance_id plus exact request facts for idempotent replay.
- Stale target, changed replay facts, wrong scope, event gaps/digest drift,
  corrupt cursor or orphan receipt fail closed with zero cursor writes.
- Separate consumers/channels never share authority.
- DOM adoption, response generation, playout and voice delivery ACK remain
  LiveVoice-owned product receipts.

## Replay and verification

1. Rebase on accepted PR 05; record its SHA.
2. Restore test_task_event_cursor.py from 15bd4cbc, run before implementation
   and record red:

       uv run pytest tests/unit_tests/agent_teams/test_task_event_cursor.py -q

3. Reimplement 73301660 using current upstream model/migration conventions.
4. Rerun the full primary file and repeat same/different-target concurrency,
   append-after-read, corruption and commit-failure cases.
5. Run supported-dialect DDL compilation, file-backed SQLite reopen/isolation,
   changed-file Ruff, compileall and git diff --check.
6. Obtain Tier-3 review focused on prefix verification, replay binding,
   cursor/receipt physical corruption and accidental product-ACK semantics.

## Commit and PR package

Keep three consecutive commits: source, tests, then docs. Proposed title:
“feat(agent-teams): add scoped Task-event consumer cursors”.

The PR body must explain cursor identity, unread/advance CAS, exact replay and
corruption/concurrency evidence. Exclude response reservation, browser/DOM
adoption, audio playout, presentation recovery and consumer-specific product
policy.
