# AgentCore local PR replay packets — 2026-08-25

Status: ten implementation plans are prepared. PR 01 has a local three-commit
technical replay on the refreshed base; PR 02 and PR 03 have isolated local
technical candidates. PR 03 is Tier-3 technical-ready (`573` affected tests,
`130` race repeats, independent `Critical 0 / Important 0`) but none of these
packages is submission-ready: the required real issue reference is still
missing, local history must be packaged/reworded accordingly, and nothing has
been pushed or submitted. PR 04 through PR 09 have completed read-only preflight
only. PR 06's independent preflight found `4 Critical / 2 Important` in the
historical checkpoint candidate; PR 07 found `5 Critical / 6 Important` in the
historical effect-journal candidate; PR 08 found `2 Critical / 4 Important` in
the historical event-cursor candidate; PR 09 found `5 Critical / 4 Important`
in the historical bound-authority candidate. Those findings are replay
requirements, not implemented or reviewed formal branches.

## Refreshed upstream drift

The historical candidate stack starts at 4f2c29c3. A read-only fetch on
2026-08-25 moved local origin/develop to
6390bbf230f4ea2dd7446bc01ee882e6a4413d4c, ten upstream commits later.
Thirteen candidate-owned paths also changed upstream:

- agent/coordination/handlers/message.py, agent/scheduling/scheduler.py and
  agent/team_agent.py;
- docs/specs/S_12_schema-data-models.md;
- external/client.py;
- tools/AGENTS.md, tools/database/__init__.py,
  tools/database/engine.py, tools/database/task_dao.py,
  tools/task_manager.py and tools/team.py;
- tests/unit_tests/agent_teams/test_database.py and
  test_database_concurrency.py.

Upstream also created F_82, F_83 and S_24 names that collide with historical
candidate documents. As observed at 6390bbf2, the docs rule based on file count
would start new candidate features at F_99 and specs at S_27. These are only
tentative allocations: every replay must recalculate the next identifiers
before its documentation commit.

These packets turn the aggregate AgentCore candidate into ten independently
reviewable capability changes. The codex/ac-pr* refs remain immutable local
review views. A worker executing a packet must compare with the then-current
develop, establish a failing test first, reimplement only the owned boundary,
run its affected evidence and obtain a new Tier-3 review.

The numeric PR labels below are immutable historical packet identities, not a
semantic scheduler. In particular, PR 07 can replay from accepted PR 03/05. PR
06 can also remain checkpoint-only from PR 03/05, but if its scope chooses to
reuse an effect continuation, accepted PR 07 becomes a dependency and PR 07 is
replayed first.

| Historical PR | Capability | Dependency | Packet | Current state |
|---:|---|---|---|---|
| 1 | Mandatory TeamTask scope | current develop | [PR 01](2026-08-25-pr01-task-scope.md) | technical replay present; issue metadata/history package pending |
| 2 | Monotonic AsyncTool cancellation | current develop | [PR 02](2026-08-25-pr02-async-cancel.md) | isolated technical candidate present; issue metadata/package pending |
| 3 | Durable execution ownership | PR 01, PR 02 | [PR 03](2026-08-25-pr03-execution-owner.md) | technical Ready; issue metadata and three-commit package pending |
| 4 | Command replay and immutable result | PR 01, PR 03 | [PR 04](2026-08-25-pr04-command-result.md) | preflight blockers recorded; formal replay blocked on packaged PR 03 base |
| 5 | Canonical Task events and dispatch | PR 03, PR 04 | [PR 05](2026-08-25-pr05-event-dispatch.md) | preflight blockers recorded; formal replay blocked on accepted PR 04 base |
| 6 | Execution-checkpoint publication | PR 03, PR 05; add accepted PR 07 only if continuation reuse is selected | [PR 06](2026-08-25-pr06-checkpoint.md) | preflight blockers recorded; formal replay blocked on accepted PR 05 and safe payload-effect topology/dependency freeze |
| 7 | External-effect journal | PR 03, PR 05 | [PR 07](2026-08-25-pr07-effect-journal.md) | preflight blockers recorded; formal replay blocked on accepted PR 03/05 and continuation/prefix/public-boundary scope freeze |
| 8 | Task-event consumer cursor | PR 05 | [PR 08](2026-08-25-pr08-event-cursor.md) | preflight blockers recorded; formal replay blocked on accepted PR 05 identity/baseline contract and cursor/receipt/public-boundary scope freeze |
| 9 | Bound TeamTask/checkpoint authority | PR 01, 03, 04, 05, 06, 08 | [PR 09](2026-08-25-pr09-bound-task.md) | preflight blockers recorded; formal replay blocked on accepted dependencies and lease/capability/public-manager scope freeze |
| 10 | Bound external-effect authority | PR 07, PR 09 | [PR 10](2026-08-25-pr10-bound-effect.md) | plan ready; replay pending |

## Common replay rules

1. Record the new develop base and compare public API/schema drift before
   applying any candidate code. The first replay must use 6390bbf2 or a newer
   fetched develop, never the historical 4f2c29c3 base.
2. Establish the owned failing tests first. Rebuild them from the accepted
   contract when the dedicated packet identifies obsolete historical oracles;
   restore only fixtures that the packet still accepts. Tests may remain
   unstaged while source is implemented so the repository-required commit order
   remains source, tests, docs.
3. Use existing commits as evidence, not as authority to blindly cherry-pick.
   Resolve every upstream conflict by the owning capability contract.
4. Fold fbfb4c5f and 50c065dc hunks into their owner packets:
   AsyncTool callback to PR 02; execution tests to PR 03; command/event tests
   to PR 04/05; checkpoint source/tests to PR 06; Task facade/checkpoint tests
   to PR 09; effect facade to PR 10; TaskManager lint to PR 01, the earliest
   packet that owns test_task_manager.py.
5. Keep code, tests and feature/spec documentation as three consecutive local
   commits. No remote ref may be updated without exact user authorization.
6. Report actual pass/fail/skip evidence. Aggregate-stack passes do not prove
   that a replayed individual PR is ready.
7. Recalculate docs/features and docs/specs file counts before each docs
   commit; rename candidate documents and repair cross-links rather than
   overwriting an upstream identifier.

## Global exclusions

Every packet excludes LiveVoice imports, voice intent/presentation/media
policy, Jiuwen principal/project heuristics, product composition, dual writes,
data migration, canary/default-on, old Store retirement and remote submission.
