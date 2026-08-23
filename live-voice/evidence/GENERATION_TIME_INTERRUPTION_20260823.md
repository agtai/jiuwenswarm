# Agent generation-time interruption — implementation evidence (2026-08-23)

**Branch:** `hx/0823_generation_interruption`
**Base:** `5415a3d3fb2c3c50b0b59fb5f5ad3a0aec423465` (`hx/0812_live_voice_w3`, correlated L0 latency baseline)
**Scope:** hands-free speech that arrives while an Agent answer is still being
generated can now stop or replace that exact answer.

This record is implementation and automated-verification evidence only. It
grants no physical, latency, controlled-candidate or product-readiness credit.

An independent review of the first implementation returned **FAIL — C0 / I2 /
M0**. Both Important findings are repaired below (§2.5), each with the direct
oracle whose absence let them through. Writing the Task-notification journey the
review asked for then exposed a third defect that only generation-time listening
makes reachable; it is repaired in §2.5 as well.

## 1. The defect this closes

[STATUS.md](../STATUS.md) recorded, under Conversation Runtime, that *hands-free
speech during Agent generation cannot currently interrupt or replace that
response*. Four independent causes were located in code:

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

### 2.5 Repairs from the independent review

* **Stale or settled targets now cancel nothing.** The first implementation
  applied `round.cancel` even when the CR fence had not been applied, so a
  terminal target still sent one cancel and a stale target had its cancel
  *accepted* -- a cancellation nobody asked for. Cancellation is now strictly
  the companion of a fence this call actually applied; a settled or replaced
  target returns `ALREADY_SETTLED` with `round_cancel=None` and
  `round_cancel_reason="GENERATION_ALREADY_SETTLED"`. The existing settled-target
  test never asserted a cancel count, which is exactly why this passed review-free;
  it now asserts zero, and a new stale-target case asserts zero cancellation and
  that the successor still answers.
* **A late interruption can no longer touch a successor Session.** The success
  and failure callbacks only checked `mountedRef`, so an interruption still on
  the wire when the user switched Session could clear or fail the successor
  route state. They now require the exact activation owner, Session and voice
  loop generation. A pending interruption is additionally part of the capture
  authority barrier, the close recovery barrier, the cleanup precondition, the
  turn/text admission guards and `settleRetainedP2Operations`, which settles it
  through the exact owner that issued it.
* **A Task announcement no longer talks over, or tears down, a live speaker.**
  Before generation-time listening, no capture was ever open while an answer was
  outstanding, so a terminal Task announcement always found P1 idle. With the
  listening window it can land mid-utterance, where handing it to P1 failed the
  whole route and the existing recovery rebuilt P1 — discarding the words the
  user was still saying. Playout now refuses rather than attempts, and that
  refusal is classified as standing down rather than failing: the exact
  delivered announcement is retained, the arbitration replays it once the
  speaker settles, and the P1 route carrying their utterance is never rebuilt.
  Nothing is fetched twice and nothing is acknowledged unspoken.

### 2.6 Feature flag

`VITE_FEATURE_LIVE_VOICE_GENERATION_INTERRUPTION` is **default-off**. Enabling
it opens a microphone between turn submission and first audio, which changes
microphone occupancy, echo exposure and capture cost for every hands-free turn.
With the flag off, behaviour is byte-for-byte the pre-existing behaviour, which
the unchanged 466-case cumulative suite demonstrates.

## 3. Automated verification

| Suite | Result |
|---|---|
| `tests/unit_tests/live_voice/test_generation_time_interruption.py` (new) | 13 passed |
| `tests/unit_tests/live_voice/test_agent_conversation_runtime.py` | 72 passed |
| `tests/unit_tests/live_voice/test_conversation_runtime*.py` | 50 passed |
| `tests/unit_tests/live_voice/test_product_p2_interaction_adapter.py` | 47 passed |
| Frontend `npm run test:live-voice-integrated-web` | 482 passed (472 pre-existing + 10 new); `test:live-voice-l0-measurement` 3 passed |
| `tests/unit_tests/{live_voice,gateway,common}` full sweep | 3923 passed, 11 failed — the identical 11 pre-existing failures (see §5) |

### 3.1 Mutation checks

Every claimed invariant was checked by breaking it and confirming a test dies.
Twenty-two mutants were run in total: 20 killed, 2 disclosed survivors.

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
| Settled/stale target still cancels its round | KILLED |

A self-review after the first implementation found the CR-B interruption replay
ledger unbounded. Unlike barge-in, which a user triggers by control action, an
interruption ledger grows with conversation length, so it is now oldest-first
bounded at 256 with a test that asserts the bound directly.

A second self-review found that the first repair of the stale/terminal cancel
semantics never reached disk — the new zero-cancel assertions caught it on the
next run, which is the behaviour those assertions exist for.

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
| Interruption outcome admitted on `mountedRef` alone | KILLED |
| Deferred announcement rebuilds P1 instead of standing down | KILLED |
| Deferred attempt keeps the foreground busy forever | KILLED |
| Settled speaker never resumes the announcement | KILLED |
| Playout no longer yields to a live speaker | KILLED |
| Surrendered capture leaves its listening window behind | **SURVIVED** |

The interruption-admission mutant is killed independently through both branch
outcomes: `mounted in-flight interruption from a retired Session cannot touch its
successor` covers the rejection side (recovery reason, `failed` status) and
`mounted in-flight interruption that succeeds late cannot reset its successor`
covers the success side (cleared output, `idle` status, cleared reason) against a
successor that is already waiting for its own answer.

The surrendered-window mutant survives: with the cleanup removed, the stale
window is still never observable from outside, because the notification poll is
independently gated by the presentation ACK and active-response conditions that
hold at that point. The cleanup is kept as the correct owner-surrender
behaviour and is recorded here as defence-in-depth rather than claimed as
covered. It was found by writing the takeover case, not by the case failing.

The other surviving mutant is a defence-in-depth guard: with it removed, a playout-time
speech-start would additionally invoke the generation handler, which then returns
without effect because no generation listening window is bound. It is retained
for intent clarity and is recorded here as uncovered rather than claimed.

## 4. Concurrency coverage

| Concurrent owner | Covered by |
|---|---|
| Exit | Backend `test_exit_owns_the_interaction_and_refuses_a_later_interruption`; frontend `mounted Exit during generation-time listening…` |
| Session switch | Frontend `mounted Session switch during generation-time listening…`, which also asserts a retired Session stops polling notifications, plus `mounted in-flight interruption from a retired Session cannot touch its successor`, which holds a rejected interruption on the wire across the switch and asserts the successor never sees its failure or reason |
| Browser capture ownership | Frontend `mounted browser takeover during generation-time listening surrenders the poll privilege` drives the exact surrender entry point the ownership lifecycle uses (`closeSession`), which is **not** the Exit path. Writing it found that `closeSession` cleaned the P1 owner and capture binding but left the generation-time listening window behind; that is now cleaned too. Generation listening otherwise starts through the same `runAuthorizedMediaStart` and capture-authority barrier as ordinary capture |
| Task notification | Backend `test_task_notification_still_speaks_after_a_generation_interruption` — an authoritative Task notification is presented and acknowledged after a fence, with exactly one `round.cancel` issued. Frontend `mounted Task notification stands down for the speaker and is spoken once they finish` — it is not spoken over the speaker, the P1 route carrying their utterance is never torn down, and the exact retained announcement is spoken and acknowledged once after they finish |

## 5. Explicit non-claims

* No physical microphone/speaker run was performed for this packet. No latency
  measurement is claimed, including for the generation listening window itself.
* Default-off. No flag-on rollout, A/B or rollback evidence exists yet.
* Echo/double-talk behaviour with an open microphone during generation is
  unevaluated. AEC/NS/AGC remain the open Audio I/O items.
* The 11 failures in the full backend sweep are pre-existing on the base commit
  `5415a3d3f` — eight under `live_voice` (`test_p3_wave2_real_evidence_producer`,
  six in `test_product_composition_registry`, `test_task_progress_return`) and
  three under `gateway` (`test_harmonyos_dev`, `test_streaming_synthesis_route`,
  `test_upload_storage`). Each was reproduced by running the same files in a
  clean detached worktree of that commit, which fails the identical set. They
  are unrelated to this change and are not repaired here.
* This closes the implementation gap only. Feature-complete, controlled-candidate
  and product-readiness boundaries remain unchanged.
