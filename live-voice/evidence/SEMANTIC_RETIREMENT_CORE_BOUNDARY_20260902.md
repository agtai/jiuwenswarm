# Semantic retirement prerequisite: bounded adjustment delivery

This is scoped engineering evidence, not hardcode-retirement, audio, physical,
complete-P3 or production-ready acceptance. The user confirmed the current
`hx/0812_live_voice_w3` baseline, `59401beb06ecb78e31dfb9c6ed5486141463768c`.
The final candidate has not been frozen. No runtime deployment or remote update
has been performed for this packet.

## Owned behaviour and risk

Tier 3: Core-owned in-flight adjustment delivery, exact renewable Store outbox
claim and authenticated composition shutdown. The existing reconciliation lane
must not wait for a running Agent to reach an adjustment boundary. An unrelated
Task cancel/dispatch/status must remain possible. Accepted adjustment is not
applied adjustment. Same-Task ordering and Store-before-Executor settlement stay
authoritative. No new operation, Task state, Executor or Task Store schema.

The expired-claim owner is keyed by outbox ID **and claim token**. Deliveries,
settlement/fencing children and cleanup failures remain owned. Cleanup is bounded;
an unresolved child prevents successful shutdown. Settlement retry preserves the
original state and `has_more`, including `APPLIED/True`.

Tier 1 test repair: a pre-existing deadline test armed a two-second Agent-release
timer before Git/setup. It could release the test Agent before the cancellation
window. Replace the competing timer with `try/finally` cleanup after the bounded
observations; keep all cancellation, result, state, replay and zero-target-effect
assertions. This is not a production deadline change.

## Applicable scenario matrix

| Dimension | Evidence boundary |
| --- | --- |
| P | Pending A adjustment does not block cancelling running B; real Direct adapter applies two ordered changes and seals actual artifact SHA. |
| N/I | Lost/foreign exact claims cannot renew or publish applied Store evidence; lost settlement cannot publish an A artifact/result. |
| B | In-flight capacity leaves further adjustments pending while cancel remains available; cleanup waits are bounded. |
| S/T | Same-Attempt order, renewal, terminal-before/after checks, cancellation and self-cancel fencing. |
| C | Reclaimed row retains both exact claim owners; Store claim/renew/CAS remains transactional. |
| R | Reopen preserves outbox/events; failed settlement remains owned across repeated cleanup; retry keeps original disposition without duplicate Agent delivery or Store event. |
| F | Executor exception, lease loss, cleanup failure and non-cooperative delivery tested. No new feature flag or old semantic fallback is introduced. |
| K | Existing Core, authenticated composition and Direct suites retained. No old test entry or assertion deleted to claim closure. |
| X | Actual Direct adapter + SQLite Core/Store + isolated Git worktrees and file patches, using a controlled test Agent stream. This is **not** real Provider/Agent-Tool, microphone or TTS evidence. |

## Commands and attempts

From repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit_tests/live_voice/test_persistent_task_core.py tests/unit_tests/live_voice/test_p3_authenticated_composition.py tests/unit_tests/live_voice/test_project_code_executor.py -q -o addopts='' -o log_cli=false --tb=short -rs
.\.venv\Scripts\python.exe -m ruff check jiuwenswarm/server/live_voice/persistent_task_core.py jiuwenswarm/server/live_voice/task_store.py jiuwenswarm/server/live_voice/p3_authenticated_composition.py tests/unit_tests/live_voice/test_persistent_task_core.py tests/unit_tests/live_voice/test_p3_authenticated_composition.py tests/unit_tests/live_voice/test_project_code_executor.py
.\.venv\Scripts\python.exe -m compileall -q jiuwenswarm/server/live_voice/persistent_task_core.py jiuwenswarm/server/live_voice/task_store.py jiuwenswarm/server/live_voice/p3_authenticated_composition.py
git diff --check
```

- First new-test attempt had a missing `asyncio` import and missing implementation;
  it was invalid as a business red proof. After fixing the import, executing the
  baseline Core in memory failed at “A adjustment retained the reconciliation
  lane”; the repaired focused scenario passed.
- Earlier full Core run: 347 passed, before the later ownership cases were added.
  Earlier full authenticated composition run: 151 passed, before the no-binding
  shutdown case. These do not substitute for the final combined rerun.
- Intermediate ownership tests exposed duplicate rejection settlement; repaired
  without weakening the exact-settlement assertion. A broader focused run had
  three failures: one test needed to observe actual asynchronous applied evidence,
  and two composition stubs lacked the new shutdown-drain interface. All repaired.
- Direct/Core integration first run: one passed, one failed only on CRLF versus
  LF byte comparison. The content oracle now compares decoded lines; raw-byte
  artifact SHA is still checked. The combined 13-case focused set then passed.
- Final-settlement fault cases first run: 2 passed / 4 failed because a one-shot
  test fault recovered during the first automatic cleanup retry. Keeping the fault
  active until explicitly released verifies retention; all six then passed.
- First final combined run: **644 passed, 1 failed, 2 skipped**, 546.56 s.
  Failure: `test_attempt_deadline_terminalizes_noncooperative_agent_without_target_effect`,
  `cancel_signals == 0` rather than 1. A direct rerun failed again. An attempted
  in-memory baseline diagnostic using PowerShell text piping failed to decode
  Unicode and ran no tests; corrected byte decoding produced a passing baseline
  helper diagnostic. This is evidence of timing sensitivity, **not** proof that
  the historical baseline always failed.
- After replacing the deadline test's competing cleanup timer: deadline plus
  both real Direct/Core adjustment cases **3 passed**, 34.59 s. A full combined
  rerun is required and recorded below when it completes.
- Final combined rerun (completed 2026-09-03): **645 passed, 2 skipped**,
  539.75 s. The two unchanged skips are file/directory symlink cases: this
  Windows host reports WinError 1314 (missing symlink privilege). No privilege
  or device/security setting was changed. Symlink negative coverage on a
  capable host remains outside this host's observed PASS.
- Ruff, compilation and `git diff --check` passed for the scoped changes before
  the final rerun. The Authlib deprecation warning is unrelated to these assertions.
  Scoped range formatting followed; only formatting changed after the full run.

## Independent review

Read-only independent subagent review; reviewer did not edit, stage, commit or
exercise a real business Task.

1. Initial design review confirmed generic Direct adjustment intake already
   exists and identified the reconciliation-lane await. Running `task.update`
   remains unsupported; natural running changes must use `task.adjust`.
2. First implementation review: C0 / I4 / M0. Fixed unbounded/non-cooperative
   cleanup, outbox-only owner key, no-binding shutdown drain and child self-cancel
   fencing.
3. Follow-up: C0 / I1 / M0. Final Store settlement was not independently owned;
   failures could be forgotten and a later close falsely succeed.
4. Fix-only: **C0 / I0 / M0**. Reviewer independently reproduced repeated failed
   cleanup and recovery for both `APPLIED/True` and `REJECTED/False`, with exact
   settlement retries and retained owners.
5. Deadline test-only repair: reviewer confirmed unchanged oracle and bounded
   waits; did not claim an independent full-suite execution.

## Remaining packet scope

All five overall gates remain incomplete. Generic semantic/parser and bounded
pre-command persistence work is separate and not yet connected to production.
Old production natural-language classifiers, recent-Task routing, fixture logic
and bypasses have not yet been retired. Both real digital audio routes, full
semantic business journey, affected Web regressions, final cumulative review and
operator physical Demo remain unpassed. Historical evidence is unchanged.
