# Agent generation-time interruption — implementation evidence (2026-08-23)

**Branch:** `hx/0823_generation_interruption`
**Base:** `c31e85ade1a69e934d05bfb9c277568a1238663c` (`hx/0812_live_voice_w3`, bounded P2 notification pulls)
**Scope:** hands-free speech that arrives while an Agent answer is still being
generated can now stop or replace that exact answer.

This record is implementation and automated-verification evidence only. It
grants no physical, latency, controlled-candidate or product-readiness credit.

## 1. The defect this closes

[STATUS.md](../STATUS.md) recorded, under Conversation Runtime, that *hands-free
speech during Agent generation cannot currently interrupt or replace that
response*. Two independent causes were located in code:

| Layer | Cause |
|---|---|
| Browser P1 route | Provider speech-start was delivered to the loop only while `status === 'playing'`, so a capture that was open during generation raised no interruption boundary |
| Integrated Web panel | `scheduleProductVoiceLoopCapture` refuses any capture while `pendingForegroundPresentation !== null`, which is exactly the generation window, so no microphone was open to speak into |
| Integrated Web panel | The P2 notification poll stands down for **any** open capture, so even with a microphone open the answer could not arrive until the speaker stopped |
| Conversation Runtime | Response replacement existed, but no explicit operation could stop or replace one exact in-flight round, and post-fence Agent tokens were still published to the consumer |

## 2. What was implemented

### 2.1 Conversation Runtime (CR-A / CR-B)

* `ConversationRuntimeLoop.interrupt_generation(action_id, ref)` closes **both**
  presentation surfaces of one exact response, invalidates its pending
  `ui.render` / `audio.enqueue` effects, emits one `playback.stop`, and requests
  response cancellation once. It refuses a target that is not the latest exact
  response of an **open** interaction, so Exit keeps precedence.
* `ConversationRuntime.response_fence_state(ref)` exposes the authoritative
  fence in O(1) so high-frequency output admission does not build a snapshot.

Barge-in remains a separate, narrower operation: it closes only AUDIO so a
still-useful answer keeps rendering. Generation interruption closes everything,
because the speaker asked for that answer to stop existing.

### 2.2 Agent Conversation Runtime

* `interrupt_generation(action_id, ref)` composes the CR fence with **one**
  Harness cancellation. The operation exposes no cancellation-scope argument at
  all: it always constructs `round.cancel` against the exact conversational
  round, so it is structurally incapable of widening into `task.cancel`. A
  background Task created by that round keeps running and keeps reporting.
* A target that already settled is not an error. The result reports
  `ALREADY_SETTLED`, so speech is still admitted as an ordinary next turn
  instead of being discarded.
* `submit_committed_turn(..., supersedes=ref)` fences before the replacement
  turn is committed, so no output of the replaced response can interleave with
  the new one. `supersedes` is part of the retained admission fingerprint, so
  replay of the same `request_id` cannot interrupt twice.
* `_consume_agent_event` now consults the CR fence before publishing. A
  superseded, cancelled or settled response delivers no further token or final
  text; one bounded `STALE_RESPONSE_OUTPUT` notice per response preserves the
  pre-existing observable contract without one refusal per token.

### 2.3 Product P2 seam

* `P2ActivationLease.interrupt_generation` and
  `handle_p2_interrupt_generation` expose the operation as
  `live_voice.composition.p2.interrupt_generation`, bound to the exact activated
  interaction, replay-fenced by `request_id`, and registered in the Gateway
  forward allowlists.
* `live_voice.composition.unified.submit` accepts an optional
  `supersedes_response`. The interaction is taken from the already-authorized
  route binding, never from the browser. The key only enters the durable
  fingerprint when present, so an ordinary turn keeps its existing fingerprint.

### 2.4 Browser

* `ProductP1VoiceRouteOwner` gained `on_generation_speech_start` (delivered only
  for an open ordinary capture with no playout) and `abandonCapture(reason)`,
  which finishes the uplink exactly as recognition does — including the
  acknowledged frame count that Agent playout depends on — but performs **no**
  recognition request, so releasing a silent listening window costs no
  first-audio latency.
* The panel opens a generation-time listening window bound to the exact response
  it may replace, interrupts that response at provider speech-start, refuses any
  answer whose identity it has interrupted, releases a silent window before
  playout, and carries `supersedes_response` when the fence has not settled by
  the time the utterance ends.
* The P2 notification poll now stays active for that one listening window.

### 2.5 Feature flag

`VITE_FEATURE_LIVE_VOICE_GENERATION_INTERRUPTION` is **default-off**. Enabling
it opens a microphone between turn submission and first audio, which changes
microphone occupancy, echo exposure and capture cost for every hands-free turn.
With the flag off, behaviour is byte-for-byte the pre-existing behaviour, which
the unchanged 466-case cumulative suite demonstrates.

## 3. Automated verification

| Suite | Result |
|---|---|
| `tests/unit_tests/live_voice/test_generation_time_interruption.py` (new) | 11 passed |
| `tests/unit_tests/live_voice/test_agent_conversation_runtime.py` | 72 passed |
| `tests/unit_tests/live_voice/test_conversation_runtime*.py` | 50 passed |
| `tests/unit_tests/live_voice/test_product_p2_interaction_adapter.py` | 47 passed |
| Frontend `npm run test:live-voice-integrated-web` | 471 passed (466 pre-existing + 5 new) |

### 3.1 Mutation checks

Every claimed invariant was checked by breaking it and confirming a test dies.

Backend (`test_generation_time_interruption.py`, baseline green):

| Mutant | Outcome |
|---|---|
| Presentation fence removed | KILLED |
| Token fence removed | KILLED |
| `round.cancel` widened to `task.cancel` | KILLED |
| Round cancellation not issued | KILLED |
| Open-interaction (Exit) guard removed | KILLED |
| `supersedes` ignored | KILLED |
| Response cancellation not requested | KILLED |

Frontend (mounted panel suite, baseline green):

| Mutant | Outcome |
|---|---|
| Poll stands down for generation listening | KILLED |
| Speech-start does not interrupt | KILLED |
| Interrupted response identity not refused | KILLED |
| Feature flag ignored | KILLED |
| Silent listening never released | KILLED |
| Replacement carries no `supersedes` | KILLED |
| Released listening drops its uplink receipt | KILLED |
| Generation speech-start delivered while playing | **SURVIVED** |

The surviving mutant is a defence-in-depth guard: with it removed, a playout-time
speech-start would additionally invoke the generation handler, which then returns
without effect because no generation listening window is bound. It is retained
for intent clarity and is recorded here as uncovered rather than claimed.

## 4. Concurrency coverage

| Concurrent owner | Covered by |
|---|---|
| Exit | Backend `test_exit_owns_the_interaction_and_refuses_a_later_interruption`; frontend `mounted Exit during generation-time listening…` |
| Session switch | Frontend `mounted Session switch during generation-time listening…` |
| Browser capture ownership | Generation listening uses the same `runAuthorizedMediaStart` / capture-authority barrier as ordinary capture; the barrier is relaxed only for the exact bound response |
| Task notification | Backend `test_task_notification_still_speaks_after_a_generation_interruption` — an authoritative Task notification is presented and acknowledged after a fence, and exactly one `round.cancel` was issued |

A mounted frontend Task-notification journey was attempted and removed: it needs
the full P3 progress-route bootstrap to reach the terminal-announcement state,
which is out of this packet. The backend case above is the retained coverage.

## 5. Explicit non-claims

* No physical microphone/speaker run was performed for this packet. No latency
  measurement is claimed, including for the generation listening window itself.
* Default-off. No flag-on rollout, A/B or rollback evidence exists yet.
* Echo/double-talk behaviour with an open microphone during generation is
  unevaluated. AEC/NS/AGC remain the open Audio I/O items.
* Eight backend unit-test failures observed in the full `tests/unit_tests/live_voice`
  run are pre-existing on the base commit `67381193a` — verified by running the
  same files in a clean detached worktree of that commit, which fails the same
  eight. They are unrelated to this change.
* This closes the implementation gap only. Feature-complete, controlled-candidate
  and product-readiness boundaries remain unchanged.
