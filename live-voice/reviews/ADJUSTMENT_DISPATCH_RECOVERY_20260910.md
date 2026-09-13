# Adjustment dispatch recovery — 2026-09-10

Baseline: `57d3b29f18a9c80a6ace83c828ec5bf19d2af461`.

The user requests repair after an existing deferred change prevented new Task
dispatch and then prevented P3 startup. Read-only reproduction constructed a
5,272-byte successor instruction against the unchanged 4,096-byte command bound.

## Scope and acceptance

Tier 3 for the persisted successor/Executor seam; Tier 2 for failure settlement.
The existing queue, Task Store and Direct Executor remain the owners. Keep the
wire schema, database schema, model, audio settings and authorization unchanged.
Successor commands carry the bounded requested change. At execution, resolve
the original requirements, retained speech and exact predecessor saved result
from verified Store lineage, without truncation. Existing compiled successors
remain readable. Invalid derived commands settle only their own adjustment;
corrupt persisted authority still fails closed.

Owned files: `task_adjustment_queue.py`, `project_code_executor.py`, their focused
tests, this record and the current STATUS consequence. No direct production
database repair, queue deletion, broad product acceptance or new Provider/voice
journey is included. Redeployment may resume already-authorized persisted work.

Acceptance: complete large/multibyte requirements reach the Executor; commands
remain bounded; original saved results stay immutable; restart/replay creates
one successor; invalid derived commands create no Task/outbox/Agent/file effects
and do not prevent an unrelated dispatch; wrong scope/Attempt/spec cannot load
another Task's context. Run the existing concurrency, cancellation, rollback,
lineage, Direct Git/file and Native-source regressions, then independently review
the coherent diff and verify startup on the actual persisted deployment.

## Verification

- The new 4,096-byte multibyte-change regression fails on the baseline queue
  with `INVALID_BOUNDED_TEXT`, before creating a successor.
- Final focused queue checks: 26 passed. These include complete original and
  adjustment Native speech, unchanged legacy compiled successors, missing-context
  rejection, exact scope/Attempt/spec checks, maximum multibyte change, restart,
  concurrent continuation, rollback, failure settlement and real SQLite/Git/file
  execution through the Direct adapter with a controlled Agent.
- Affected regression command: `python -m pytest -o addopts=''` for
  `test_task_adjustment_queue.py`, `test_persistent_task_core.py`,
  `test_project_code_executor.py` and `test_native_task_source.py`: 567 passed.
  Subsequent missing-context protection and expansion reuse were checked by the
  final focused run; the unmodified core/native regression boundary was not rerun.
- A consistent copy of the user's actual fault database materialized exactly one
  successor: 416-byte wire instruction, complete 5,272-byte execution context.
  Reopen produced identical context; the original result remained unchanged.
  The copy made zero Agent calls and did not alter the production database.
- Python compilation and `git diff --check` passed. Cold complete-diff review
  checked context ownership, immutable predecessor binding, full-content retention,
  failure isolation before writes, normal-task fallback and existing file guards.
- Independent `codex review --uncommitted` was attempted but the installed CLI
  could not use its configured model: the service required a newer CLI version.
  No model/configuration/installation changes were made. Cold review is the
  available substitute, not independent review credit; that limitation remains.

Detailed command outputs and the isolated database copy remain under ignored
`logs/adjustment-recovery-*`. Redeployment uses the clean commit containing this
record and the existing controlled launcher. Its runtime contract and service log
are the source of deployment readiness; no microphone/model acceptance is claimed.
