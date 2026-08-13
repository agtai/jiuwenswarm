# S8.5 Competitive Showcase

> Pass/fail: [S8.5 acceptance](../validation/S8_5_COMPETITIVE_SHOWCASE_ACCEPTANCE.md)
> Claims: [S8.5 claim matrix](../S8_5_COMPETITOR_CLAIM_MATRIX_2026-08-13.md)

Run once by the user on the exact reviewed candidate after both unchanged
rehearsals. Do not repair source, change flags, switch fixture/verifier or hide a
fallback during the run.

## 1. Preflight

Record exact source, S8 closeout relation, clean worktree, S8.5 flag/profile,
Chrome/OS/origin/device, real Speech/Agent route, isolated runtime data,
disposable no-remote fixture and verifier manifest. Verify the fixture matches
its trusted clean base and contains no credentials or user data.

The isolated S8.5 route requires all existing authenticated product gates plus
its two explicit default-off gates:

- `JIUWENSWARM_LIVE_VOICE_P3_ENABLED=true`;
- `JIUWENSWARM_LIVE_VOICE_PRODUCT_COMPOSITION_ENABLED=true`;
- `JIUWENSWARM_LIVE_VOICE_PRODUCT_P2_ENABLED=true`;
- `JIUWENSWARM_LIVE_VOICE_PRODUCT_P3_TEXT_ENABLED=true`;
- `JIUWENSWARM_LIVE_VOICE_PRODUCT_P3_MUTATION_ENABLED=true` for Task A creation
  and Task B cancellation;
- `JIUWENSWARM_LIVE_VOICE_S8_5_TASK_REVISION_ENABLED=true`;
- `JIUWENSWARM_LIVE_VOICE_S8_5_FIXTURE_MANIFEST=<absolute private JSON path>`;
- `VITE_FEATURE_LIVE_VOICE_S8_5_TASK_REVISION=true` in the Web build.

The Alpha/P3alpha profile keeps the S8.5 gates unset. The fixture manifest is a
machine-private runtime input and is not restored by Git.

## 2. Task A — revise a running code fix

1. By committed voice, create a bounded background task to fix the fixture's
   deterministic calculator defect. Confirm it and record `task_id`, revision 1,
   attempt 1 and create command.
2. While attempt 1 is visibly running, say an ambiguous revision. Confirm that
   the product asks for clarification and causes zero task/project mutation.
3. Commit: “补充任务输入：负数输入行为保持不变。” Confirm the exact
   `task.provide_input` binding.
4. Observe the Task Truth panel: same task ID; pending revision; predecessor
   attempt fenced; exact cleanup ACK; revision 2 applied; successor attempt 2.
5. Verify attempt 1 late output cannot update current progress, project diff or
   verifier state. Confirm attempt 2 starts from the trusted clean base.
6. Observe real Agent/Executor work. Inspect the sanitized changed paths/diff,
   verifier ID/result, forbidden-side-effect count and final authoritative outcome.
7. Exercise status/events/reconnect and confirm the same revision/attempt truth
   returns without duplicate execution.

Do not issue `task.update_constraints` for Task A: the profile permits exactly
one `1 -> 2` revision. Its exact bilingual form, narrowing rules and zero-effect
negative cases remain required automated acceptance on a separate fixture task.

## 3. Task B — exact cancellation stays separate

1. Start a second bounded background task in the same disposable fixture set.
2. Issue an ambiguous cancel and verify zero mutation plus clarification.
3. Commit and confirm cancel for exact Task B. Verify its exact attempt stops only
   after Executor/Core evidence.
4. Confirm Task A, current response, Harness round, microphone and playback were
   not cancelled or rewritten.

## 4. Failure truth

Run the prepared cleanup-unknown or verifier-fail profile. The UI must show
`unknown` or failed verification, must not create an unauthorized successor, and
must not say success. Restore the normal profile only after recording the result;
do not count that restored run as the same attempt.

## 5. Closeout

Stop microphone/playout/services, inspect the disposable fixture, confirm no
remote/commit/push/dependency/API/config/out-of-scope mutation, and preserve only
sanitized summaries. Decide PASS/PARTIAL/BLOCKED/FAIL under the acceptance file.
Present only claims in the green column of the claim matrix.
