# Shared task settlement prerequisite — 2026-09-09

This is a Task 3 prerequisite within the [active Goal](../reviews/AGENTCORE_UNIFIED_EXECUTION_20260909.md).
It does not close Task 2, Task 3 or the product candidate. The JiuwenSwarm Work
adapter remains uncommitted on top of `66833d5ced9203ce54ffa2fcf009d4de380f62a7`
until the user's coherent numbered task boundary is complete.

## Paired source

AgentCore commit `a43444ff5326a0c1a72954126eea4f91e071d916`:
`fix(swarm): share task settlement and retain cancelled execution ownership`.
Its parent is the Goal prerequisite `1f03f1bbe51d3492c3a21d9ad4338067df281721`.
Reviewed tree: `65ed846ed1aee10604979ce2f680bab25541b6a9`.
The locked upstream base and Responses repair remain unchanged.

The [manifest](../../scripts/sdk_patches/agentcore-source.json) now includes
[the settlement patch](../../scripts/sdk_patches/agentcore-task-settlement.patch).
The actual installer reconstructed all three patches from the locked base in
`.codex_tmp/agentcore-source-replay-settlement-20260909`; reconstructed commit
`5dd8955` has the exact reviewed tree. Fresh-interpreter
`python scripts/install_agentcore_source.py --check` passed. The prior explicit
old-package uninstall and editable source installation remain valid; this change
did not reinstall a wheel or replace configuration. Services have not restarted
against the new code.

## Changed boundary

The existing SDK `core.common.background_tasks` module now exports
`wait_for_task_settlement` and `TaskSettlement`. Both real NativeHarness async
tools and Native Work use it. A timeout records a stop request and physical exit
observation separately; cancelling an observer cannot cancel its borrowed task.

Async tools retain IDs through cleanup and spill-thread exit, suppress completion
injection started after cancellation, and expose `execution_settled` separately
from status. Old-record waits and cancel receipts cannot switch to a replacement
with the same ID. SwarmFlow relaunch uses a fresh task ID, so its controller checks
the captured predecessor record and actual avatar abort/disposal before resuming.

Live Voice removes its duplicate stop/wait/settlement wait in NativeWorkRuntime
(net 14 production lines removed: +53/-67, including required indentation).
Durable Work state, capacity, predecessor fences, execution-settlement futures,
project authority, speech/presentation and restart-unknown truth remain there.
This is not a replacement of the full Work ledger, durable Task execution or the
common Agent output service.

## Review and targeted verification

One independent review at this boundary found three issues, all repaired and
confirmed at their affected seams:

1. A tool's own CancelledError could leave running + settled. Actual cancelled
   worker exit now produces the silent cancellation terminal state without
   overwriting an existing completed/error/unknown result.
2. Relaunch between task.done() and its callback could strand the old record.
   The callback always settles its captured row/event; only shared-map deletion
   depends on current ownership. Tests also retain exact cancel receipt identity.
3. The actual Avatar abort and KV disposal paths swallowed failures. Abort now
   reports failure; disposal retains the session until actual success. The
   controller retries disposal and keeps failed resume intent. The fault test
   uses real manager/backend/KV helper with only harness effects replaced.

Checks used the project's source-installed venv, separately for each repository:

- SDK common wait, AsyncToolRuntime, async control tools and background controller:
  44 passed. After the Avatar finding, only the affected Avatar/runtime/controller
  files reran: 25 passed (55 distinct tests across the combined boundary).
- JiuwenSwarm `test_native_work_runtime.py`: 13 passed, including real Harness
  cancellation/cleanup, capacity, stale identity, predecessor, restart and
  persistence-failure oracles. The final run used `--no-cov -o log_cli=false`.
- Changed SDK/Main production and test files: scoped Ruff passed.
- Scoped diffs and staged SDK diff: whitespace checks passed.
- Actual locked-source reconstruction and installed-source check: passed.

An initial mixed-repository pytest invocation failed collection because both
repos define `tests.conftest`; running them separately corrected the invocation.
A regression initially overwrote an existing error during teardown; it was fixed
and the error-path test passed. No failed run was counted as passing evidence.
No full-suite, frontend build, Provider/browser or physical hearing acceptance
was claimed here. No remote ref was updated.
