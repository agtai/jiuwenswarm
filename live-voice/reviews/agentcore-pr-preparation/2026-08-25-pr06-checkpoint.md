# AgentCore PR 06: execution-checkpoint publication implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:test-driven-development while replaying this plan, then use
> superpowers:requesting-code-review before declaring the local package ready.

**Goal:** Publish an opaque checkpoint reference as the resume-authoritative
head for one exact TeamTask execution without moving product payload policy
into AgentCore.

**Architecture:** TaskDao stores checkpoint metadata and a canonical source
event transactionally. ExecutionCheckpointCoordinator writes opaque bytes
through an injected payload store, then publishes/verifies the authoritative
reference. Payload orphaning is explicit and never grants Task authority.

**Risk and dependency:** Tier 3 durability/recovery authority. Depends on PR 03
execution tokens and PR 05 canonical events. The review-only source diff is
473ad7cf..7c08730f on codex/ac-pr06-checkpoint.

## Owned surfaces

- Public API: openjiuwen/agent_teams/checkpoint.py and
  openjiuwen/agent_teams/__init__.py.
- Schema/storage/runtime: schema/task.py, tools/models.py,
  tools/database/engine.py, tools/database/task_dao.py and
  tools/task_manager.py.
- Primary test:
  tests/unit_tests/agent_teams/test_execution_checkpoint_publication.py.
- Historical candidate docs are F_86/S_28; allocate fresh names at replay
  (tentatively F_104/S_31) and update the final PR 05 event feature.

## Contract

- ExecutionCheckpointAuthority publishes and reads metadata for an exact Team,
  Task, execution ID and execution token.
- ExecutionCheckpointPayloadStore put/get owns opaque bytes and returns a
  bounded receipt; it grants no execution or mutation authority.
- ExecutionCheckpointCoordinator.publish and load_current verify metadata,
  payload digest/size and current execution binding.
- Exact replay is idempotent; stale owner, wrong Team/session, corrupt source
  event or conflicting head fails closed.
- Checkpoint codecs, Jiuwen project files, compatibility and retention remain
  downstream.
- checkpoint.py and checkpoint-test quality fixes from fbfb4c5f belong here.

## Replay and verification

1. Rebase after PR 03/05 and record dependency SHAs.
2. Restore test_execution_checkpoint_publication.py from 30897cd0 plus its
   fbfb4c5f corrections; run without implementation and record red:

       uv run pytest tests/unit_tests/agent_teams/test_execution_checkpoint_publication.py -q

3. Reimplement 5e4355ec using current upstream public-export and migration
   conventions; fold the owned fbfb4c5f hunks.
4. Rerun the primary file, emphasizing concurrent head publication, restart,
   stale owner, corrupt reference/event and payload-orphan cases.
5. Run supported-dialect DDL compilation, changed-file Ruff/format, isolated
   Mypy for checkpoint.py, compileall and git diff --check.
6. Obtain Tier-3 review focused on reference/payload ordering, replay truth,
   source-event verification and accidental authority minting.

## Commit and PR package

Keep three consecutive commits: source, tests, then docs. Proposed title:
“feat(agent-teams): publish authoritative execution checkpoints”.

The PR body must explain opaque payload separation, exact execution binding,
replay/restart/corruption evidence and possible harmless payload orphaning.
Exclude product codecs, project-file policy, retention, migration of LiveVoice
state and automatic resume orchestration.
