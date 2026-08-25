# AgentCore PR 02: monotonic AsyncTool cancellation implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:test-driven-development while replaying this plan, then use
> superpowers:requesting-code-review before declaring the local package ready.

**Goal:** Give AsyncToolRuntime one monotonic terminal decision so accepted
cancellation cannot be overwritten by late completion, injection or spill.

**Architecture:** AsyncToolRuntime owns in-memory background Tool lifecycle.
A single terminal CAS helper arbitrates completion, failure and cancellation;
callbacks consume late wrapper errors without re-settling a reused task ID.

**Risk and dependency:** Tier 3 asynchronous side-effect fencing. Functionally
independent of PR 01 and may rebase directly on current develop. The review-only
source diff is ced87a3e..5c3ef668 on codex/ac-pr02-async-cancel.

## Owned surfaces

- Source: openjiuwen/agent_teams/harness/async_tools.py.
- Tests: tests/unit_tests/agent_teams/harness/test_async_tools.py.
- Spec: update
  openjiuwen/agent_teams/docs/specs/S_20_native-harness-async-tool-framework.md;
  add the required feature archive under the next free identifier (tentatively
  F_100 after PR 01 at 6390bbf2).
- Guidance adjustment: openjiuwen/agent_teams/harness/AGENTS.md only when still
  required by current repository guidance.

## Contract

- AsyncToolRuntime.launch rejects duplicate active task IDs without replacing
  the original record.
- cancel waits for coroutine unwind, propagates cancellation of its own caller,
  and returns only after the accepted terminal state is stable.
- _try_set_terminal and _on_task_done ensure exactly one terminal winner.
- has_running, get, list_all and wait observe that winner; late completion,
  output-file spill and result injection have zero effects after cancellation.
- The typed completion callback correction from 50c065dc belongs in this PR.

## Replay and verification

1. Create a fresh replay branch from current develop and record the base SHA.
2. Restore the race tests from c248e756 without source changes and record red:

       uv run pytest tests/unit_tests/agent_teams/harness/test_async_tools.py -q

3. Reimplement the terminal arbitration from 85602c54 and incorporate the
   typed callback hunk from 50c065dc; do not add durable Task semantics.
4. Rerun the full AsyncTool test file at least 20 times for the race-focused
   selection, without sleeps as a synchronization proof.
5. Run changed-file Ruff lint/format, isolated Mypy for async_tools.py,
   compileall for agent_teams/harness and git diff --check.
6. Obtain a Tier-3 review focused on cancellation propagation, reused IDs,
   exactly-once injection/spill and unobserved Task exceptions.

## Commit and PR package

Keep three consecutive commits: source, tests, then docs. Proposed title:
“fix(agent-teams): make AsyncTool cancellation monotonic”.

The PR body must explain the single terminal winner, cancellation-unwind
guarantee, duplicate-ID fence and hostile late-callback tests. Exclude durable
execution ownership, provider cancellation guarantees, LiveVoice timeout
policy and any persistent schema.
