# Generic Direct checkpoint retirement — scoped evidence

Source: worktree diff over `e0fddb8414866249dc540a1eac070346f06b6c30`.
This record covers Direct/factory/capability-consumer retirement, not Registry
semantic cutover, browser audio or physical acceptance. No service was restarted,
user project modified or remote ref updated.

## Boundary and oracle migration

Tier 3, D-107: remove the task-name prompt wrapper, fixed artifact path/count,
fixture-only first-adjustment wait and both Direct constructor flags. New D0/D2
profiles advertise `adjust.task-checkpoint/v1` under v2 IDs. Actual Agent work,
isolated Git patching, exact adjustment settlement and immutable artifact hashes
remain authoritative. Old v1 canonical bytes/digests are unchanged and readable;
new dispatch rejects them before effects, and status returns exact
`UNAVAILABLE / EXECUTOR_SELECTION_PROFILE_DRIFT`. No old running-work upgrade is
claimed; drain it before deployment.

The former exact-one-itinerary oracle represented the explicitly retired business
policy. Its replacement proves unchanged user instructions and real multi-artifact
sealing. Existing protected-path, symlink, target patch, shutdown, cancellation,
ordering, recovery, immutable result and wrong-target zero-effect oracles remain.
Checkpoint tests now use the existing test-injected barrier, never a production
wait/flag. Old constructor flags reject, and environment values cannot re-enable
the removed behavior. No runner or unique applicable safety scenario was deleted.

P/N/B/S/T/C/R/I/F/K/X are covered by the Direct, Core and authenticated suites:
real isolated Git patch/journal operations, bounded lifecycle/failures, target and
profile drift, exact settlement, concurrent controls and recovery. The Agent is a
controlled test executor in this scoped suite; actual Provider/Agent/file-Tool
business execution belongs to the packet's subsequent real/audio checks. F does
not require restoring the retired fixture flags.

## Commands and results

All pytest commands use `.venv/Scripts/python.exe -m pytest`, with
`-q -o addopts= -o log_cli=false --tb=short`:

- `tests/unit_tests/live_voice/test_project_code_executor.py`
  `tests/unit_tests/live_voice/test_p3_authenticated_composition.py`
  `tests/integration/live_voice/test_formal_task_executor_adapter.py`:
  **307 passed, 2 skipped** in 508.26 s. Skips are the existing Windows
  `WinError 1314` symlink-privilege cases, not new skips. One Authlib deprecation.
- `tests/unit_tests/live_voice/test_p3_production_intent_composition.py`
  `tests/unit_tests/live_voice/test_persistent_task_core.py`
  `scripts/live_voice/w2_rehearsal/tests/test_portable_launchers.py`:
  **383 passed** in 76.36 s.
- Final Direct `-k 'legacy_direct_snapshot or generic_checkpoint or retired_fixture'`:
  **7 passed** in 27.00 s, including the added exact legacy status assertions.
- Frontend: compile `formalP3TaskExperience.ts` with the package's strict ES2020
  integrated-Web settings, then `node --test tests/liveVoiceBuildProfiles.test.mjs
  tests/formalP3TaskExperience.test.mjs`: **20 passed**.
- Ruff check, Ruff format (after formatting the added assertion), Python
  compileall and `git diff --check` pass. This batch changes no Web product
  source; full Web build is reserved for final semantic integration.

All attempts: the first 12-case focus had 11 passes and a 5-second polling helper
timeout while waiting for the owned worker's Git apply/cleanup. A diagnostic single
rerun passed without a behavior change. The helper now awaits the actual shielded
owned worker with a 30-second total bound, preserving terminal and artifact
assertions; the broad suite and independent reruns pass. This is not evidence of
a five-second production latency guarantee. The first Node run had 19 passes and
one stale v1 literal assertion; after updating that expected profile, the fresh
TypeScript/Node run above passed. No failed attempt is relabeled as a pass.

## Independent review

Read-only reviewer `checkpoint_review` reviewed the complete batch and ran 21
focused tests. It found one activity-document mismatch (old v1/fixture instructions).
The runbook, D-107, ACG overlay and STATUS now state the actual v2 and legacy drift
boundaries. Fix-only review ran both legacy tests and returned **C0 / I0 / M0**.
The reviewer confirmed legacy canonical bytes/digests equal the baseline and the
new settlement helper does not weaken the product oracle.

This scoped result grants no full hardcode-retirement, digital-audio, human or
Production-ready credit. Original historical evidence was not rewritten.
