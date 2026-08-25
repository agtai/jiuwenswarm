# AgentCore PR 07: external-effect journal implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:test-driven-development while replaying this plan, then use
> superpowers:requesting-code-review before declaring the local package ready.

**Goal:** Provide generic durable truth for external-effect intent, dispatch,
receipt, observation, settlement and reconciliation under one exact Task
execution.

**Architecture:** EffectDao is the subordinate effect owner and stores an
append-only, digest-linked fact prefix plus current projection.
ExternalEffectCoordinator invokes an injected provider adapter only after
receiving a one-use continuation authorization. TaskDao remains sole
Task/execution/checkpoint owner and blocks token-staling Task writes while an
effect is unresolved.

**Risk and dependency:** Tier 3 external side-effect and durability authority.
Depends on PR 03 and PR 05 because unresolved effects share the exact execution
and Task dispatch/lock boundary; Task events still are not presentation
receipts. The review-only source diff is
7c08730f..8f30c02c on codex/ac-pr07-effect-journal.

## Owned surfaces

- Public API/schema: openjiuwen/agent_teams/effect.py,
  schema/effect.py and openjiuwen/agent_teams/__init__.py.
- Storage/runtime: tools/database/effect_dao.py,
  tools/database/__init__.py, tools/database/engine.py,
  tools/database/task_dao.py, tools/models.py and tools/task_manager.py.
- Primary test:
  tests/unit_tests/agent_teams/test_execution_effect_journal.py.
- Historical candidate docs are F_87/S_29; allocate fresh names at replay
  (tentatively F_105/S_32).

## Contract

- EffectDao exposes plan_effect, get_effect, claim_effect, record_dispatch,
  authorize_call/observation, record_receipt/observation, settle_effect,
  read_effect_prefix, reconcile_effect and claim reaping.
- ExternalEffectCoordinator.dispatch/observe calls adapters only with a valid,
  one-use authorization bound to the current fact head and execution.
- Exact replay never appends a second fact or remints call authority.
- Expired dispatch is ambiguous, not safely retryable; wrong/stale/corrupt
  inputs have zero provider and journal effects.
- Provider credentials, request interpretation, project/file probes,
  compensation selection and user confirmation remain downstream.

## Replay and verification

1. Rebase after PR 03 and PR 05; record both accepted SHAs.
2. Restore test_execution_effect_journal.py from bead0a87 and run before
   implementation to record red:

       uv run pytest tests/unit_tests/agent_teams/test_execution_effect_journal.py -q

3. Reimplement 398454d0 with EffectDao as the subordinate owner and no imports
   from LiveVoice or product adapters.
4. Rerun the full primary file; repeat competing claims, dispatch/reset,
   one-use authorization and ambiguous-observation races.
5. Run supported-dialect dynamic-table compilation, file-backed SQLite
   reopen/corruption/rollback cases, changed-file Ruff, isolated Mypy for pure
   public modules, compileall and git diff --check.
6. Obtain Tier-3 review focused on provider-call zero effects, retry ambiguity,
   prefix integrity, continuation consumption and Task/effect transaction
   ordering.

## Commit and PR package

Keep three consecutive commits: source, tests, then docs. Proposed title:
“feat(agent-teams): add a fenced external-effect journal”.

The PR body must describe EffectDao ownership, lifecycle facts, one-use
continuation authority and restart/concurrency/corruption evidence. Exclude
Jiuwen project/file mutation logic, provider-specific probes, product
compensation policy, Web receipts and LiveVoice confirmation rules.
