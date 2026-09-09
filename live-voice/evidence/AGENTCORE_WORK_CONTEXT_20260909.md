# Shared SDK work context — 2026-09-09

This is a bounded prerequisite of the active unified-execution Goal. The Host
cutover remains uncommitted and unaccepted; no new runtime was deployed.

## Source pairing

Installed SDK commit `e8a1ea88a38911802dd0a36352fb9816c8290ec9`
(`feat(harness): bind Goal attempts and output to immutable work context`)
contains the reviewed isolated candidate `7154d06a876efcda2e2cbe5ab0706242643aa7f2`,
integrated on the existing SwarmFlow source `f5039e60`. The seventh ordered patch
is `scripts/sdk_patches/agentcore-work-context.patch`; the cumulative tree is
`a1030314351ee3007f91246bbc5bdd49cc28d396`.

All seven patches were reconstructed from pinned upstream
`94e10cb6102c36fe78a64547957c0def97299273` using the real source preparation
function and the retained local Git mirror. The reconstructed tree matched the
manifest. The installed editable source/import check passed. The isolated
candidate's mixed Windows line endings were normalized in the Git index before
commit; its worktree bytes were preserved while consumers used that snapshot.
Temporary reports and `.test-tmp/` were excluded. No package reinstall, remote
update or service restart occurred.

## Owned behavior

Goal run contexts are bounded JSON snapshots carried by the existing Goal
store/manager and actual task-loop work. An active attempt cannot change binding;
idle resume uses exact control CAS before replacement. SDK identity overrides
host-supplied aliases. Public source metadata requires explicit opt-in and is
separate from private permission context.

Per-work Session views share the original writer, interactions and dynamic
runtime state. Typed and dictionary output keep their actual work identity,
independent of an older request's output reader. The existing scheduler and
Goal state machine remain the owners; no parallel lifecycle is introduced.

## Review and evidence

- Author's affected SDK group: 164 passed before the final protocol compatibility
  repair; the final GoalManager group: 44 passed. Ruff had no new findings and
  the scoped diff check passed.
- Independent review reproduced private-context promotion/request spoofing and
  source-map size validation after Goal effects. Both were repaired and closed
  with 29 targeted checks.
- A subsequent P2 showed that requiring a private store method broke existing
  implementations of the public GoalStore protocol. Generic validation now
  belongs to the manager; Session static-label validation is an optional store
  preflight. Independent legacy/bound protocol-store repros and 10 targeted
  checks passed; all findings were closed before integration.
- Host Goal snapshots also strip `run_context` without mutating stored state;
  the affected Goal adapter group passed 39 tests.

Host model/permission/history binding, Native Goal execution, Core Workflow
consumers, remaining retirement and final real-scenario acceptance are separate
unfinished parts of the same Goal. These SDK checks do not claim those outcomes.
