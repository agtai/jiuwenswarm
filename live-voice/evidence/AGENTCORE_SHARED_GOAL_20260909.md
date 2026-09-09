# Shared Goal prerequisite — 2026-09-09

This is a tested prerequisite within Task 2 of the
[active Goal](../reviews/AGENTCORE_UNIFIED_EXECUTION_20260909.md), not Task 2 or
product completion. JiuwenSwarm adapter changes remain uncommitted on top of
`66833d5ced9203ce54ffa2fcf009d4de380f62a7` until the complete Task 2 boundary closes.

## Paired source

- AgentCore commit: `1f03f1bbe51d3492c3a21d9ad4338067df281721`,
  `feat: add exact shared Goal control and read-only observation`.
- Reviewed tree: `380c9e9c9101331de97b7125f4a7190b02dde40e`.
- Upstream base remains `94e10cb6102c36fe78a64547957c0def97299273`; the existing
  Responses repair remains included. Version metadata remains
  `0.1.16+jiuwenswarm.responses2`; content identity is the reviewed tree.
- [Source manifest](../../scripts/sdk_patches/agentcore-source.json) includes
  [the Goal patch](../../scripts/sdk_patches/agentcore-goal-control.patch).
  The actual installer reconstructed both patches from the pinned base in
  `.codex_tmp/agentcore-source-replay-goal-20260909`; the resulting tree matched.
- `python scripts/install_agentcore_source.py --check` passed in the project
  venv. The editable installation still imports `.deps/agent-core`; old wheel
  uninstall/source installation was completed and recorded in the
  [Task 1 evidence](AGENTCORE_SOURCE_BASELINE_20260909.md).
  Running services have not been restarted against these changes.

## Behavior and review

The shared application resolver preserves text mode/project selection and adds
an exact cached-owner lookup for authorized Native queries. Missing owners do
not trigger another Agent, default-project fallback or metadata writes. Native
Goal get/pause/clear access the existing session's SDK GoalManager. Startup,
resume and stream ownership remain following work.

SDK `peek()` now preserves malformed state and rejects wrong-session records.
Conditional controls compare Goal ID and a separate persisted control revision
inside the existing lock. Legacy records default that revision to 1. Pause and
in-flight resume retain the execution revision so the finishing assessment can
commit; status changes invalidate stale controls.

Independent review found three blocking issues, all repaired and specifically
rechecked:

1. Cleanup could start before the control retained the child. Lookup now rejects
   an owner whose lifecycle lock is held; a control retains the existing active
   session count until it settles, without stream-rail cleanup.
2. A pre-lock authorization snapshot missed registry changes. The SDK admission
   callback now awaits a fresh project/session authority read under its control
   lock, followed by the final route/expiry check before effects.
3. Commit or cancellation failure could occur after state changed. Native now
   reports UNKNOWN with observation required, preserving actual state, instead
   of claiming zero-effect rejection.

The read-only reviewer confirmed these three fixes without another broad audit.
Main inspected the scoped SDK diff before its commit. No remote ref was updated.

## Verification

Latest affected checks used the project venv and `--asyncio-mode=auto`, with
`-q -o addopts= -o log_cli=false`:

| Boundary | Files/check | Result |
|---|---|---|
| SDK state/control/compatibility | AgentCore `test_goal_manager.py`, `test_goal_schema.py`, `test_goal_store.py` | 49 passed |
| Shared Native/text owner and SDK control | `test_shared_session_agent.py` | 19 passed |
| Existing text Goal and history | `test_goal_runtime_adapter.py`, `test_goal_objective_history_defer.py`, `test_goal_history_bubble_parity.py` | 51 passed |
| New modules and tests; changed SDK files | Scoped Ruff checks | Passed |
| Patch/source reconstruction and installed origin | Actual installer and `--check` | Passed |
| Whitespace | Scoped `git diff --check` | Passed |

The shared tests cover exact owner identity, no query creation/write, unavailable
and wrong-project/mode/channel cases, stale control after text resume, clear's
exact Goal cancellation, cleanup-first ordering, route and registry revocation
while waiting for the SDK lock, and commit/cancel failures. SDK tests cover
legacy records, malformed/wrong-session state, control ABA and finishing-attempt
assessment. External authorization I/O and model execution are isolated in these
tests; they are not real Provider or complete registry/product acceptance.

Earlier focused checks during this Task 2 implementation passed 125 SwarmFlow/
Native protocol cases and 230 resolver/text/Goal compatibility cases. Later
changes repeated only affected checks above; those earlier counts are dated
stage evidence, not a final combined candidate run.

## Pending boundary

Task 2 still owns full shared execution/stream consumers, Goal set/resume,
Team/SwarmFlow interaction and execution, registered Core Workflow access, and
the required end-to-end authority/protocol checks. Task 3's broader generic
lifecycle downshift and duplicate-code retirement remain pending. No complete
Task 2 commit, full-suite run, frontend build, runtime deployment or real
browser/Provider acceptance is claimed here.
