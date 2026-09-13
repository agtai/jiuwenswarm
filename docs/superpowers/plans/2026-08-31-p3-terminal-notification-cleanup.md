# P3 Terminal Notification Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve exactly-once Task presentation ownership when a P2 route closes before its shared P3 progress route so a later session can activate progress delivery and announce the Task terminal state.

**Architecture:** Keep the existing P2-before-P3 cleanup order and all ACK-in-flight fencing. Retain the exact Runtime route until the high-level close has also recorded its closed fence, so a partial close can replay the same reservation instead of losing retry authority. After the P2 owner successfully closes an exact shared Task presentation, settle the corresponding `_ProgressDelivery` as closed under the existing presentation-state lock; the P3 owner then treats it as already settled instead of attempting a second close.

**Tech Stack:** Python 3, asyncio, pytest, JiuwenSwarm Live Voice product composition registry, React/TypeScript mounted integration tests.

**Spec:** `live-voice/STATUS.md` and the user-approved 2026-08-31 Tier 3 repair boundary.

## Global Constraints

- Risk tier is Tier 3 because the change crosses P2/P3 Task presentation authority ownership.
- Do not weaken `audio_ack_in_flight`, exact session/task/response binding, generation fencing, late-ACK rejection, or fail-closed behavior.
- Do not change RPC methods, payload schemas, stable public reason identifiers, Task state, Agent/Tool permissions, history authority, or audio ownership.
- Hardcode removal, Task-style input fail-closed classification, D-094 latency, notification batching, and P1 media ACK work are excluded.
- Remote refs are not updated without separate exact user approval.

---

### Task 1: Reproduce the cross-owner double-close

**Files:**
- Test: `tests/unit_tests/live_voice/test_product_composition_registry.py`

**Interfaces:**
- Consumes: `AgentServerProductCompositionRegistry.handle_p2_close()` and `handle_p3_progress_close()`.
- Produces: a regression oracle that requires both exact owners to close successfully without consuming the Task event.

- [x] **Step 1: Write the failing test**

Add `test_p2_close_settles_shared_task_presentation_before_progress_close`. Use `_running_presentation_store`, activate exact P2 and voice-origin P3 routes, wait for one `_task_presentation_deliveries` entry, then close P2 before P3. Require:

```python
assert p2_closed.ok
assert progress_delivery.closed is True
assert progress_closed.ok
assert store.get_task(task_id, SCOPE) == task_before
assert store.unread_events_page(
    task_id, SCOPE, presentation_class="voice", limit=500
).watermark == -1
assert manager.agent.calls == 0
```

Submit the captured old audio presentation ACK after both routes close and require rejection with the same zero side effects.

- [x] **Step 2: Run the exact test to verify RED**

Run:

```powershell
pytest tests/unit_tests/live_voice/test_product_composition_registry.py::test_p2_close_settles_shared_task_presentation_before_progress_close -vv
```

Expected: FAIL because `progress_delivery.closed` remains false and the later P3 close returns `PRODUCT_P3_PROGRESS_CLEANUP_PENDING` after attempting to close the presentation a second time.

### Task 2: Settle the shared delivery exactly once

**Files:**
- Modify: `jiuwenswarm/server/live_voice/product_composition_registry.py`
- Test: `tests/unit_tests/live_voice/test_product_composition_registry.py`

**Interfaces:**
- Consumes: the existing `_ProgressDelivery` mapped by `_task_presentation_deliveries`.
- Produces: `_close_task_presentations_for_p2_route()` marks `progress_delivery.closed = True` only after `TaskPresentationOwner.close_response()` and closed-presentation recording succeed.

- [x] **Step 1: Implement the minimal production change**

Inside `_close_task_presentations_for_p2_route`, after the exact presentation is successfully closed, recorded, and removed from both runtime maps, add:

```python
progress_delivery.closed = True
```

Keep the mutation inside `_task_presentation_state_lock`. Do not catch or suppress `TaskPresentationViolation`; failed or ACK-owned closes must remain retryable and unmarked.

Do not remove `_task_presentation_runtime_routes` from the low-level Runtime
authority callback. Every high-level settlement path already removes it after
the closed fence is recorded; retaining it across a partial close preserves the
Runtime's exact closed-reservation replay authority.

- [x] **Step 2: Run the exact test to verify GREEN**

Run the Task 1 pytest command. Expected: PASS, including the late-ACK and zero-side-effect assertions.

- [x] **Step 3: Run neighboring ownership/race tests**

Run:

```powershell
pytest tests/unit_tests/live_voice/test_product_composition_registry.py -k "audio_ack_wins_progress_close_race or progress_close_failure_is_retained or p2_close_settles_shared" -vv
```

Expected: PASS. The genuine ACK-in-flight race must still return cleanup pending until the ACK owner settles.

### Task 3: Verify the terminal-notification integration seam

**Files:**
- Test if coverage is absent: `jiuwenswarm/channels/web/frontend/tests/liveVoiceIntegratedRoutePanelMounted.test.mjs`
- Modify frontend production code only if a new RED proves a separate frontend defect.

**Interfaces:**
- Consumes: exact P3 close/activate results and the mounted terminal presentation path.
- Produces: proof that old cleanup precedes new exact activation and a terminal notification is queued, acknowledged once, and followed by listening recovery.

- [x] **Step 1: Inspect existing mounted coverage**

Confirm existing tests cover terminal queue/TTS/ACK/listening recovery and bounded P3 close retry. If the exact old-owner-to-new-owner transition is not covered, add a mounted seam test whose mock close returns cleanup pending twice, succeeds on the third exact retry, then requires one new-session `p3.progress.activate` before delivering one terminal event.

- [x] **Step 2: Run affected browser tests**

Run the exact mounted test and `productWebActivation.test.mjs` using the repository's frontend test command. Expected: PASS with one close sequence, one successor activation, one terminal presentation, one ACK, and no duplicate audio/history operation.

### Task 4: Tier 3 verification and review

**Files:**
- Modify: `live-voice/STATUS.md` only to record the verified repair/evidence.

**Interfaces:**
- Consumes: the clean implementation diff and exact test outputs.
- Produces: a reviewable local commit and P3-9 human acceptance handoff.

- [x] **Step 1: Run affected automated and static checks**

Run the complete product-composition registry suite, affected integrated Web tests, Ruff on changed Python, Python compile, TypeScript `--noEmit` if frontend changed, and `git diff --check`.

- [x] **Step 2: Review the D-032 matrix**

Record P/N/S/T/C/R/I/F/K/X coverage. Explicitly verify exact identity, retry behavior, stale/late ACK rejection, one terminal delivery, and zero Agent/Tool/Task/history/audio/store mutation on rejected paths; mark representation bounds inapplicable because no input/schema boundary changes.

- [x] **Step 3: Perform independent module-boundary review**

Review the complete scoped diff cold for double-close, partial-close, in-flight ACK, stale generation, cross-session isolation, replay, and forbidden side effects. Fix findings and rerun materially affected checks.

- [x] **Step 4: Commit locally**

Commit one coherent repair. Do not push without a separate exact approval.

- [ ] **Step 5: Deploy for human acceptance**

Restart the local JiuwenSwarm services from the exact commit and provide the
minimal and complete P3-9 acceptance prompts.

## Verification record

- Initial RED: P2 closed the Runtime reservation, then closed-record capacity
  exhaustion removed the exact Runtime route before the operation could be
  retried. The direct branch passed while the capacity-retry branch failed on
  the missing `_task_presentation_runtime_routes` entry.
- GREEN: direct close and capacity exhaustion -> safe-slot release -> exact
  close replay both pass. The P2 owner records the closed fence and removes the
  two Runtime maps before the P3 owner closes without a second Runtime close.
- Focused ownership/race set: `4/4` passed, including the real audio-ACK race
  and the retained P3 cleanup retry.
- Complete product-composition Registry file: all `186/186` items printed
  `PASSED`. The repository test process was interrupted only after every item
  printed because its existing post-suite teardown did not exit.
- Integrated Web: clean process exit, `487/487` passed. Existing duplicate
  `empty` locale-key build warnings remain unchanged.
- Ruff, Python compile and `git diff --check` passed.
- Repair re-review: `Critical 0 / Important 0 / Minor 0`, final assessment
  `Ready`. The reviewer independently reran both parameterized close cases and
  `git diff --check`; broad suites were not duplicated by the reviewer.
- D-032 matrix: P covers direct close and terminal continuation; N covers
  capacity exhaustion and late ACK rejection; S covers exact binding and
  no Task/Store/Agent effects; T covers audio ACK versus close; C covers
  Runtime/P2/P3 shared ownership; R covers closed reservation replay and exact
  retry; I covers direct and capacity branches; F covers retained maps before
  retry and removed maps after settlement; K is not applicable because no
  representation or input bound changed; X is covered by late callbacks with
  zero Task/Event/Agent effect.
