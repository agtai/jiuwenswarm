# Realtime Notification Activation Continuity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve one OpenAI Realtime Native P2 activation, uplink, Provider session, and interrupted user input while Gateway-local notifications remain sequence-neutral and AgentServer notification cursor mismatches recover in place.

**Architecture:** AgentServer remains the sole committed notification-sequence authority. Gateway marks every notification dequeued from its local Native queue with one explicit `sequence_effect: "neutral"`, retains only exact local/forwarded request ownership, and forwards AgentServer candidates unchanged; Browser tracks a candidate separately from its committed cursor and advances the committed cursor only for a consumed AgentServer response. A typed AgentServer mismatch supplies `details.expected_sequence`, which the current Browser owner uses for one bounded in-activation retry without invoking P2 close, successor activation, media revoke, uplink close, or Provider close.

**Tech Stack:** Python 3.11+/asyncio/pytest, TypeScript strict mode, Node test runner, React Integrated Web test bundle.

**Spec:** User-approved Tier-3 execution packet attached to the current goal; `live-voice/architecture/OPENAI_REALTIME_NATIVE_INTERACTION_ENGINE_2026-08-25.md`; `live-voice/decisions/DECISIONS.md` D-101/D-102/D-103; root `TESTING.md` Tier-3 rules.

## Global Constraints

- Work only from `da7b3deb986872e62f4ab4f2ff6d746ec394787a` in the isolated `codex/fix-realtime-notification-activation-continuity` worktree.
- Produce exactly one new commit with message `fix(live-voice): preserve activation across notification recovery`; do not push, deploy, start, or stop JiuwenSwarm services.
- Keep `interrupt_response = false`; Runtime played-cursor stop/cancel/truncate remains the sole interruption authority.
- Do not add Browser RPCs, notification kinds, a general recovery framework, P3/background Task behavior, VAD/acoustic tuning, Provider/model changes, or unrelated cleanup.
- Every mutation-capable negative/race path asserts zero Agent, Tool, Task, history, stale audio, foreign activation, media-revoke, uplink-close, and Provider-close effects.
- Tier-3 matrix: P/N/B/S/T/C/R/I/K/X are applicable; F is limited to bounded mismatch/retry and malformed expected-sequence behavior. Restart, physical device/acoustic behavior, public deployment, and cross-Engine fallback are explicitly out of scope.

---

### Task 1: Lock the mixed-local-notification root cause in RED tests

**Files:**
- Modify: `tests/unit_tests/gateway/test_dedicated_media_registration.py`
- Modify: `tests/unit_tests/gateway/test_app_gateway_acp.py`
- Modify: `jiuwenswarm/channels/web/frontend/tests/productWebActivation.test.mjs`

**Interfaces:**
- Consumes: existing `DedicatedMediaProductRegistry.take_native_notification_response`, `mark_native_notification_forwarded`, and `ProductWebP2ActivationOwner.nextNotification`.
- Produces: failing behavioral tests for kind-independent neutral projection, exact in-flight ownership, retry/changed-replay fencing, and the same still-next AgentServer candidate after both local orderings.

- [ ] **Step 1: Add the Gateway mixed-order tests**

  Use literal queues for `native.audio -> native.user_transcript` and the reverse. For each order, dequeue both local results with the same candidate sequence and assert both response results contain `sequence_effect == "neutral"`; then assert the next forwarded Agent request keeps that exact candidate rather than mapping it through an offset.

- [ ] **Step 2: Add the in-flight and replay tests**

  Mark an Agent request as forwarded, enqueue a local item, and prove an exact retry retains Agent ownership and leaves the local queue untouched. Prove an exact local retry returns one frozen response, changed sequence under the same request id returns no response, and the local replay/queue structures stay bounded with zero duplicate projections.

- [ ] **Step 3: Add the Browser mixed-order test**

  Return explicit neutral notifications in both orders followed by one consumed Agent notification, and assert the three RPC candidates are `[1, 1, 1]` with three distinct request ids. The production mutation caught is any kind whitelist or pre-increment/decrement compensation.

- [ ] **Step 4: Run RED and record the expected failure**

  Run the focused Gateway nodeids and the compiled `productWebActivation.test.mjs`. Expected failure on the untouched baseline: `native.user_transcript` lacks neutral sequence semantics and the Browser sends candidate `2` after it, or equivalent mode/offset state appears.

### Task 2: Implement one explicit neutral sequence contract

**Files:**
- Modify: `jiuwenswarm/gateway/live_voice/dedicated_media_registration.py`
- Modify: `jiuwenswarm/gateway/app_gateway.py`
- Modify: `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productWebActivation.ts`
- Modify: `jiuwenswarm/channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx`
- Test: files from Task 1 plus `jiuwenswarm/channels/web/frontend/tests/liveVoiceIntegratedRoutePanel.test.mjs`

**Interfaces:**
- Produces: local response field `sequence_effect: "neutral"`; Browser sequence effect parser accepting only `neutral | consumed`; `committedNotificationSequence` updated only after consumed AgentServer responses.
- Removes: `client_sequence_mode`, `client_sequence_offset`, `local_projection_debt`, local kind inference, and the pre-increment/audio-decrement compensation.

- [ ] **Step 1: Centralize Gateway neutral projection**

  In `take_native_notification_response`, add `projected["sequence_effect"] = "neutral"` after dequeue so every current/future local kind inherits the same semantics. Preserve exact activation/connection/request ownership and prevent a forwarded request id from taking a newly queued local item.

- [ ] **Step 2: Delete dual-mode mapping**

  Reduce `_NativeNotificationSequenceFence` to exact request/replay ownership and only the minimum Agent candidate cursor needed for a forward fence. `mark_native_notification_forwarded` must return/forward the Browser candidate unchanged; `app_gateway.py` must not rewrite `notification_sequence`.

- [ ] **Step 3: Separate Browser candidate and committed cursor**

  Replace the old pre-increment flow with `candidate = committedNotificationSequence + 1`. After parsing the response, set `committedNotificationSequence = candidate` only when the response effect is consumed; leave it unchanged for explicit neutral. Reject unknown sequence effects and remove `isGatewayNativeAudioProjection`.

- [ ] **Step 4: Admit neutral fields in the Integrated Web parser**

  Extend only the local Native notification exact-key checks with `sequence_effect`, require `neutral`, and leave AgentServer batch/publish ordering unchanged.

- [ ] **Step 5: Run GREEN focused tests**

  Re-run all Task 1 commands and the existing Gateway sequence/replay and Integrated Web notification tests. Expect every new and existing focused test to pass with no warning.

### Task 3: Recover an exact AgentServer mismatch inside the activation

**Files:**
- Modify: `jiuwenswarm/server/live_voice/product_composition_registry.py`
- Modify: `tests/unit_tests/live_voice/test_product_composition_registry.py`
- Modify: `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productWebActivation.ts`
- Modify: `jiuwenswarm/channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx`
- Modify: `jiuwenswarm/channels/web/frontend/tests/productWebActivation.test.mjs`

**Interfaces:**
- Produces: mismatch payload `error.details.expected_sequence: number`; bounded one-owner resync using a fresh request id and current binding; `isProductNotificationSequenceMismatch(error)` for the poll coordinator.
- Preserves: AgentServer strict `notification_sequence == admitted + 1` admission and exact request-id fingerprint replay.

- [ ] **Step 1: Add RED AgentServer expected-sequence assertions**

  Extend the strict serial-sequence test so both gap and reordered mismatch responses assert literal `details.expected_sequence` values and show the admitted sequence did not change.

- [ ] **Step 2: Add RED Browser in-place recovery test**

  Return one real-shaped Web error with reason `PRODUCT_NOTIFICATION_SEQUENCE_MISMATCH` and `payload.error.details.expected_sequence = 1`, then a valid notification. Assert notification RPC candidates `[2, 1]`, one fresh request id for the definitive retry, unchanged activation generation, and zero calls to P2 close/activate beyond the original activation.

- [ ] **Step 3: Add RED exhaustion/no-terminal-escalation test**

  Return repeated mismatches or malformed expected cursor. Assert the retry bound is honored and `pollProductP2RouteWithRecovery` does not call retained-operation settlement, P2 close, or successor activation for this reason.

- [ ] **Step 4: Implement the minimum server error detail**

  Allow `_error_result(..., details={"expected_sequence": expected_sequence})` and return it only at the exact mismatch branch. Do not relax strict admission, replay-floor, pending-poll, or request-id conflict checks.

- [ ] **Step 5: Implement bounded owner resync**

  Parse only a positive safe integer from the actual Web error payload, set committed cursor to `expected_sequence - 1`, clear the definitively rejected request id, and retry once in the same owner/binding. On unsafe/exhausted mismatch, surface the error without the generic close-and-successor path.

- [ ] **Step 6: Run focused server/frontend GREEN tests**

  Run the exact product registry strict-sequence nodeids and compiled Product owner/recovery tests. Expect exact cursor recovery and zero forbidden close/revoke effects.

### Task 4: Prove interrupted-input continuity and exactly-once side effects

**Files:**
- Modify: `tests/unit_tests/gateway/test_dedicated_media_registration.py`
- Modify: `jiuwenswarm/channels/web/frontend/tests/liveVoiceNativeInteraction.test.mjs`
- Modify only if the real seam requires it: `jiuwenswarm/channels/web/frontend/tests/liveVoiceIntegratedRoutePanel.test.mjs`

**Interfaces:**
- Consumes: existing Native fake/runtime session, speech-start, response fence, transcript projection, and dedicated media helpers.
- Produces: one deterministic barge-in continuity test binding the same activation generation, uplink lease, Provider session, input item, and EOT transcript across interleaved local/Agent notifications.

- [ ] **Step 1: Build the existing-fake interruption journey**

  Arrange assistant playback, inject `speech_started`, confirm current response stop/cancel/truncate, interleave local audio/transcript plus one Agent notification, then finish EOT/transcript on the original Native session.

- [ ] **Step 2: Assert authority continuity and zero effects**

  Assert activation generation/uplink/Provider identities are unchanged, the user transcript is adopted once, microphone frames remain admitted, and counts for `PRODUCT_NOTIFICATION_SEQUENCE_MISMATCH`, `MEDIA_NATIVE_INPUT_FENCE_REJECTED`, stale assistant audio/history, Agent/Tool/Task duplication, P2 close/activate, media revoke, uplink close, and Provider close are all zero.

- [ ] **Step 3: Run the focused Native/Gateway journey**

  Run only the exact new nodeids first, then the existing Native interaction and lifecycle files. Expect deterministic pass without real Provider, Chrome, microphone, or acoustic claims.

### Task 5: Verify, independently review, and create the single commit

**Files:**
- Review every changed file from `da7b3deb986872e62f4ab4f2ff6d746ec394787a`.

**Interfaces:**
- Produces: clean Tier-3 source/automation candidate, independent `C0/I0/M0`, and one cherry-pickable commit.

- [ ] **Step 1: Run affected Python regression**

  Run the two required Gateway files, strict notification/cursor/retry product registry nodeids, and all changed Native fake/runtime nodeids with `C:\Users\admin\Desktop\live voice hx\.venv\Scripts\python.exe -m pytest -o addopts= -q`.

- [ ] **Step 2: Run affected frontend regression/build**

  Run `npm run test:live-voice-integrated-web`, the focused Native interaction tests, TypeScript strict compilation, and `npm run build:live-voice` from `jiuwenswarm/channels/web/frontend`.

- [ ] **Step 3: Run static/repository checks**

  Run Ruff on changed Python files, `python -m compileall` on changed Python modules, `git diff --check`, and inspect `git status --short --branch`, `git diff --stat`, and the complete diff.

- [ ] **Step 4: Run read-only independent Tier-3 review**

  Give one read-only reviewer the exact baseline-to-worktree diff and restrict findings to sequence authority, local/Agent replay ownership, mismatch recovery, activation/uplink continuity, exactly-once input adoption, forbidden effects, and test sufficiency. Fix only confirmed in-scope findings and repeat affected checks/review until `C0/I0/M0`.

- [ ] **Step 5: Create and verify the only commit**

  Stage only task files, commit once as `fix(live-voice): preserve activation across notification recovery`, then verify commit count `1`, parent exactly `da7b3deb986872e62f4ab4f2ff6d746ec394787a`, clean status, and final diff stat. Do not push or deploy.
