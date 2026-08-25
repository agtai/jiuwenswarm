# AgentCore PR 10: bound external-effect authority implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:test-driven-development while replaying this plan, then use
> superpowers:requesting-code-review before declaring the local package ready.

**Goal:** Expose a least-privilege, session-bound public continuation authority
for the generic external-effect journal.

**Architecture:** TeamAgent.effect_authority returns
TeamExecutionEffectAuthority bound to the same TeamTaskAuthority identity. The
facade verifies journal projections and fact prefixes before delegating to
EffectDao. ExternalEffectCoordinator consumes the public protocol; callers
cannot construct continuation authority directly.

**Risk and dependency:** Tier 3 public external side-effect boundary. Depends
on PR 07 and PR 09. The review-only source diff is
503cf538..db821683 on codex/ac-pr10-bound-effect.

## Owned surfaces

- Public API/facade: openjiuwen/agent_teams/effect.py,
  effect_authority.py, openjiuwen/agent_teams/__init__.py and
  agent/team_agent.py.
- Narrow subordinate support: tools/database/effect_dao.py.
- Primary tests:
  tests/unit_tests/agent_teams/test_effect_authority.py,
  test_execution_effect_journal.py and test_task_authority.py.
- Historical candidate docs are F_91/S_33; allocate fresh names at replay
  (tentatively F_109/S_36) and update the final PR 07 feature/spec.

## Contract

- ExecutionEffectAuthority defines plan, claim, dispatch, receipt,
  observation, settlement, get, prefix read and reconciliation operations.
- TeamExecutionEffectAuthority binds Team/member/session and validates every
  record, fact prefix, token, integer bound and subordinate result.
- TeamAgent.effect_authority is the construction path; direct construction and
  root exports must not allow forged call authority.
- Released/foreign sessions, stale global prefix, malformed projection,
  incomplete call and wrong expected version have zero database/provider
  effects.
- Provider/project/file and product confirmation/compensation policy remain
  downstream.
- effect_authority.py quality corrections from fbfb4c5f belong here.

## Replay and verification

1. Rebase after accepted PR 07/09 and record their SHAs.
2. Restore test_effect_authority.py and affected journal/task-authority tests
   from 8db056f5 plus fbfb4c5f corrections; run before implementation and
   record red:

       uv run pytest tests/unit_tests/agent_teams/test_effect_authority.py tests/unit_tests/agent_teams/test_execution_effect_journal.py tests/unit_tests/agent_teams/test_task_authority.py -q

3. Reimplement 53dfcc7c and fold only the PR-owned fbfb4c5f corrections.
4. Rerun all three files and repeat version/prefix races, session release,
   cancellation-context restoration and root-export lock tests.
5. Run file-backed SQLite reopen/concurrency/corruption cases, changed-file
   Ruff/format, isolated Mypy for effect_authority.py, compileall and
   git diff --check.
6. Obtain Tier-3 review focused on unforgeable continuation authority,
   subordinate verification, session binding and zero provider effects.

## Commit and PR package

Keep three consecutive commits: source, tests, then docs. Proposed title:
“feat(agent-teams): expose bound external-effect authority”.

The PR body must explain the bound construction path, verified fact-prefix
projection, stale-token fencing and lifecycle/concurrency evidence. Exclude
provider-specific adapters, Jiuwen project/file mutation policy, retry/
compensation product decisions, LiveVoice confirmation and any remote rollout.
