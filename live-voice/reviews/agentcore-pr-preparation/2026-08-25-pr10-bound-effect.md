# AgentCore PR 10: bound external-effect authority implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:test-driven-development while replaying this plan, then use
> superpowers:requesting-code-review before declaring the local package ready.

**Goal:** Expose a least-privilege, session-bound public external-effect
orchestration facade for the generic journal.

**Architecture:** TeamAgent.effect_authority returns
TeamExecutionEffectAuthority bound to the same TeamTaskAuthority identity. The
facade verifies journal projections and fact prefixes before delegating to
EffectDao. Its bound coordinator consumes purpose-specific continuations,
invokes the exact declared adapter namespace and alone finalizes the returned
receipt/observation; callers cannot construct continuation authority, recover a
live token from a projection or write an evidence enum directly.

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

- ExecutionEffectAuthority defines plan, purpose-bound call/observe
  orchestration, settlement, redacted get/prefix read and reconciliation
  operations. Raw claim tokens and receipt/observation writers remain internal;
  exact public method names are frozen only after accepted PR 07 replay.
- TeamExecutionEffectAuthority binds Team/member/session and validates every
  record, fact prefix, runtime/phase/incarnation/provider binding, integer bound
  and subordinate result provenance.
- TeamAgent.effect_authority is the construction path; direct construction and
  root exports must not allow forged call authority.
- Released/foreign sessions, stale global prefix, malformed projection,
  incomplete call, forged evidence and wrong expected version have zero
  database/provider effects.
- Provider/project/file and product confirmation/compensation policy remain
  downstream.
- effect_authority.py quality corrections from fbfb4c5f belong here.

## Replay and verification

1. Rebase after accepted PR 07/09 and record their SHAs.
2. Rebuild test_effect_authority.py and the affected journal/task-authority
   tests from the accepted PR 07/09 contracts, using `8db056f5` and the
   PR-owned `fbfb4c5f` corrections only as historical evidence. Do not restore
   raw evidence writers, reusable tokens or tests that bypass the bound
   coordinator. Run the rebuilt tests before implementation and record red:

       uv run pytest tests/unit_tests/agent_teams/test_effect_authority.py tests/unit_tests/agent_teams/test_execution_effect_journal.py tests/unit_tests/agent_teams/test_task_authority.py -q

3. From the exact accepted dependency tips, implement only the accepted bound
   facade delta. Treat `53dfcc7c` and `fbfb4c5f` as evidence, not commits to
   replay.
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
