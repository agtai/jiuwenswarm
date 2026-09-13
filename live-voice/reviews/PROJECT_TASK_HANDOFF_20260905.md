# Serial project Task handoff repair

## Scope and intended behaviour

Baseline: `7f6ff497bc656b7e3c6a1a4ea70749eb4d55d647`.
Owner: Executor & Durability, at the existing Task Core admission seam.
Risk: Tier 2 state/concurrency repair under [TESTING](../../TESTING.md).
Dependencies: D-098 exact managed baselines, Direct journal, canonical Task Store,
and existing bounded `EXECUTOR_PROJECT_BUSY` admission deferral.

An already accepted Task must stay queued while the same project is owned by an
earlier attempt, including result application, retained cleanup and terminal
observation awaiting canonical ingestion. Only after that ownership settles may
the next attempt inspect and validate a stable clean/exact managed baseline.
No new Task or attempt is allocated by deferral. No dirty-tree error is converted
blindly into a retry; complete D-098 validation still gates actual execution.

Owned source: `project_code_executor.py` project occupancy/admission ordering.
Scope amendment before implementation: the cancellation regression exposed that
a proven BUSY deferral still followed uncertain-delivery cancellation and could
start its Agent on redelivery. Task Core/Store queue ownership is therefore also
owned by this batch, at Tier 2. Reuse the Store's exact unbound-queue proof for
cancel-before-dispatch; retain uncertain/claimed/bound cancellation semantics.
This changes no cancellation authority, protocol or admission policy.
Owned tests: Direct D2 real-Git/SQLite handoff regressions and affected Executor,
Task admission and authenticated-composition regressions. No new schema, wire
state, capability, permission, effect acceptance policy, provider configuration,
timer or semantic classifier. Failure-answer wording, initial proposal generation,
arbitrary user dirt, fixture/prompt edits and physical A/B/A2 acceptance are excluded.

## Plan and acceptance

1. Retain the existing serial-success baseline. Add a deterministic regression
   using the real Direct adapter, Store and Git: gate A after it writes its result,
   dispatch B through Core, and assert B stays accepted with no B journal/Agent/
   file effect. Release A, also cover journal completion before Store ingestion,
   then ingest and prove the same B executes once with both artifacts retained.
2. Move explicit project occupancy inspection ahead of project-content snapshots
   and binding revalidation. Use persisted journal/Store ownership facts, retain
   the journal's atomic competing-create check, and reuse the current BUSY queue.
   Same-attempt delivery replay must remain idempotent.
3. Cover cancellation while queued, unrelated dirty files after settlement,
   distinct-project isolation, retained cleanup and restarted adapter reads.
   Reuse applicable admission deadline/replay and wrong-scope regressions.
4. Review the complete scoped diff, run an independent review, fix affected findings,
   and record exact verification. Integrate one coherent local commit after checks.
   Do not touch running service state until a verified candidate is ready.

P/N/B/S/T/C/R/I/F/K/X apply to the bounded admission/lifecycle seam. Audio,
recognition, model-output and browser dimensions are outside this repair.
The real Git/SQLite/Executor path is required; scripted Agent file production may
control timing but cannot establish real-model or physical acceptance.

## Verification

The real Git/SQLite regression reproduced the original dirty-baseline failure
before the repair. After the repair:

- `test_project_task_handoff.py` and `test_task_admission.py`: **123 passed**.
  Coverage includes A apply and canonical-ingestion windows (also while status
  reconciliation is in progress), reopened-adapter reads, retained cleanup,
  live failed/cancelled cleanup, exact B cancellation before/during BUSY delivery,
  persisted cancellation/replay, unknown-delivery rejection and unrelated dirt.
- `test_project_code_executor.py`, `test_persistent_task_core.py`,
  `test_p3_4_durability_runtime.py`, `test_p3_authenticated_composition.py`:
  **677 passed**, one inherited Authlib deprecation warning. These retain
  same-attempt replay, different-project isolation, mutation fences, admission
  bounds/recovery and actual D2/authenticated-composition seams.
- After final cancel-command settlement wiring, the affected existing cancel
  subset was rerun: **71 passed**, 291 deselected.
- Ruff check on the four changed Python files and `git diff --check`: passed.
  Pytest used `--tb=short -q --asyncio-mode=auto`, with default aggregate coverage
  disabled; no coverage percentage is claimed as acceptance.

The independent review reproduced an additional failed/cancelled cleanup window:
terminal publication preceded the persisted cleanup marker. `finish` now records
cleanup ownership atomically with terminal truth for all five worker failure/
cancellation paths, and existing cleanup resolution releases it. The reviewer
reran the same counterexample: B remained BUSY, with one Agent call and no B
journal. Final cold review found no remaining blocking findings; independent
cancel/unknown-delivery checks passed (4 tests). Deployment identity is recorded
by the runtime contract and at handoff, not inferred from source verification.

The cancellation repair reuses Store-owned queue and command-settlement logic;
the lineage verifier recognizes the exact closed-deferral cancellation proof.
It does not treat a claimed or unknown delivery as unexecuted. Existing failed
Tasks are not silently retried or replaced. No prompt, output, timer, audio,
Provider or transport behavior was changed. Physical A/B/A2 and production
stability remain outside this scoped automation evidence.
