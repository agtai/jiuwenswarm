# R4 interruption and failure presentation

The accepted [repair packet](REALTIME_ACCEPTANCE_REPAIRS_20260907.md) assigns
Tier 2 cancellation classification and Web presentation to this point. Main
owns implementation after the lifecycle worker handed off R4; the project worker
provides independent review. R3 transport-prefix authority is separate.

Expected prepared interruption, supersession and unadmitted promotion retirement
retain their existing cancellation, cleanup, fencing and diagnostic records. They
do not enter the continuation-failure queue or publish a failed request. Actual
Provider timeout, overflow, failed generation and unsupported/failed cleanup
still report failure. No response, Task, work, tool or history authority changes.

Native failures no longer insert an assistant answer. Existing generated rows
keep their truthful `interrupted` label; undisplayed preparation produces no new
row. The status area retains real failure diagnostics even when capture remains
healthy. A concise message explains that the microphone is still listening;
technical stage and reason remain under a closed-by-default details control.
Recovery and stale-generation fencing remain unchanged. Cascade's existing
assistant failure behavior is outside the Native change.

Acceptance: real normal interruption and work-removal retirement without a failed
request; real cleanup fault and timeout remain visible; exact Native failure
before/after/overlapping media close; duplicate/stale notifications, successor
input and no invented message/history/Task effects; accessible failure details;
normal transcript and existing retry controls retained.

Verification on the integration worktree:

- `test_native_continuation_preparation.py`: 110 passed in 46.22s, including actual
  speech-start retirement and separate unsupported-cleanup failure.
- `tsc --noEmit`: complete frontend type check passed.
- Mounted Native lifecycle selection: 21 passed in 9.08s. These include capture
  remaining healthy after real request failure, fatal media timing permutations,
  duplicate/stale failures, generated text and Task associations with zero
  unintended submission/ACK/Task effects.
- Mounted hands-free error presentation: passed; short text remains separate
  from the transcript, details starts closed, retry works and Task activity
  remains after exit.
- Scoped diff check passed. Existing duplicate `empty` locale-key bundle warnings
  were observed outside the touched translation keys; they were not changed.

Logs: `logs/r4-continuation-tests.txt`, `logs/r4-frontend-typecheck.txt`,
`logs/r4-mounted-native.txt`, `logs/r4-mounted-error-details.txt`. The frontend
tests use the production React components and controlled media fixtures, not a
real headset. Native generated-text validation also passed 11 cases. The
independent project worker reviewed the complete change plus owning lifecycle
paths and found no blocking issue: the exact three expected reasons alone lose
failure notification, real cleanup/timeout remain, stale authority stays fenced,
and healthy capture no longer hides the concise fault notice. The reviewer did
not rerun tests. Cumulative browser acceptance remains pending.
