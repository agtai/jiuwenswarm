# Agent generation-time interruption — implementation evidence (2026-08-23)

**Branch:** `hx/0823_generation_interruption`
**Base:** `9a3a65fd0fa1d5ef4f680a9eda61d0482dd1f789` (`hx/0812_live_voice_w3` at the time of writing)
**Named-ref caveat:** that ref was amended **four** times during this work (`5415a3d3f` -> `8de91262a` -> `7c589dcda` -> `24e7e6106`, all carrying the same subject) and has since advanced twice more, to `a44843b62` and then `9a3a65fd0`; the last of those touches `productP1VoiceRoute.ts`, which this change also edits, so it was rebased in rather than left aside. It moved again while this record was being committed (`88163b843`, docs-only), and it will keep moving: the stable fact is the **merge-base**, not the ref and not a left/right count. Resolve the base with `git merge-base hx/0812_live_voice_w3 <this HEAD>` at review time; every number below was measured on `9a3a65fd0`. Integration needs its own re-freeze against whatever the ref points at then.
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
  bound to a target that is still a fenceable live response, not to this call
  being the one that produced the fencing effects (see §5); a settled or
  replaced target returns `ALREADY_SETTLED` with `round_cancel=None` and
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

Two more defects came out of the fourth review.

* **A retired activation could fence every later Session out of listening.** A
  retriably-failed interruption is kept in the panel's pending ref on purpose,
  so the exact owner can still replay it. But three of the barriers that read
  that ref matched on *any* pending interruption rather than on its owner, and
  cross-Session cleanup closed the predecessor without replaying it — after
  which `interruptGeneration` is impossible, since it requires that
  activation's binding. The handle became permanent and every successor Session
  was refused generation-time listening for the rest of the page's life. Each
  barrier now matches the owner, and a closed activation's handle is retired:
  idempotence of a retried interruption belongs to the server-side `action_id`
  ledger, not to a handle nothing can reach.
* **Releasing the listening window could discard an utterance.**
  `abandonCapture` advanced the operation generation *before* physically
  stopping the capture, so an authoritative provider speech-start arriving
  during `stopCapture` failed its own generation check and was dropped. The
  release then completed as if the window had been silent — throwing away words
  the user had already started saying while the old answer kept playing. The
  generation is now advanced only once the release is irreversible, and a
  speech-start observed during the stop keeps the capture: status stays
  `capturing`, and the route, frames and media receipt are retained, which the
  caller already treats as a live speaker. The same shape exists in
  `pauseIdleCaptureForNotification`, which is pre-existing P2-notification code
  outside this change and is **not** repaired here.

Three more came out of the fifth review.

* **The release kept a `capturing` status with no live microphone.** The
  fourth-round repair returned `false` and left the status alone when a
  speech-start landed during `stopCapture` — but `stopCapture` has already
  ended the MediaStream track by then, so the rest of the utterance was never
  recorded and the status was a lie. A speaker now gets a real successor
  capture: the uplinked frames are settled, `#startConcurrentCapture` opens a
  fresh lease exactly as a bounded silent rotation does, the prior media
  authority is revoked, and `capturing` is physically true.
* **A fenced response could still present what was already queued.** The CR
  fence invalidates the effect and stops further output, but a notice already
  sitting in the delivery queue would still reach a consumer and be rendered or
  spoken. The Web client refuses it by response identity — that refusal is the
  client's, not this boundary's. `interrupt_generation` now calls the existing
  `discard_presentation(ref)` when it fences, so the invariant holds for every
  authenticated consumer.
* **A failed answer kept its listening window.** The `failed` branch cleared
  the foreground fence but not `generationCaptureRef`, so the next answer was
  refused its own window for the rest of the session — and a capture with no
  outstanding response kept the notification-poll privilege. The window bound
  to the exact failed response is now retired with it.

### 2.6 Feature flag

`VITE_FEATURE_LIVE_VOICE_GENERATION_INTERRUPTION` is **default-off**. Enabling
it opens a microphone between turn submission and first audio, which changes
microphone occupancy, echo exposure and capture cost for every hands-free turn.
With the flag off the browser behaves exactly as before -- no second microphone,
no interruption -- which the unchanged 478-case baseline suite demonstrates. This
is a browser-behaviour claim, not a protocol-surface one: the new RPC is
registered on the server and in the Gateway allowlists regardless of the Vite
flag, so an authenticated P2 client that sends the method explicitly gets it
executed on a flag-off deployment where the baseline would reject an unknown
method.

## 3. Automated verification

| Suite | Result |
|---|---|
| `tests/unit_tests/live_voice/test_generation_time_interruption.py` (new) | 19 passed |
| `tests/unit_tests/live_voice/test_agent_conversation_runtime.py` | 73 passed |
| `tests/unit_tests/live_voice/test_conversation_runtime*.py` | 50 passed |
| `tests/unit_tests/live_voice/test_product_p2_interaction_adapter.py` | 48 passed |
| `tests/unit_tests/live_voice/test_product_composition_registry.py` | 176 passed, 6 pre-existing failures |
| Frontend `npm run test:live-voice-integrated-web` | 496 passed (478 pre-existing + 18 new); `test:live-voice-l0-measurement` 5 passed |
| `tests/unit_tests/{live_voice,gateway,common}` full sweep | 3961 passed, 2 skipped, 11 failed — the identical 11 pre-existing failures (see §6) |

`test_partial_activation_failure_rolls_back_runtime` is load-sensitive and is
reported rather than hidden. It failed once in a focused run immediately after
a full sweep, and once in a full sweep that ran while the frontend suite was
running beside it; it passes otherwise, including six deliberate repeats, four
of them under eight busy-loop processes. The mechanism was pinned down
directly: that test's fixture builds the adapter with
`cleanup_timeout_seconds=0.02`, and lowering it to `0.0001` reproduces exactly
the observed assertion -- the bounded rollback wait expires and the result
becomes `ROLLBACK_FAILED` instead of the expected cause. The fixture, the test
and the activation/rollback path are all untouched by this change (this branch
adds 57 lines to `product_p2_interaction_adapter.py`, none of them on that
path, and zero lines to that test file), so this is a pre-existing 20 ms timing
margin, not a regression. A reviewer running under load may hit it.

### 3.1 Mutation checks

Forty-one mutants were run in total: 34 killed, 7 disclosed survivors. The
survivors are named below; every other listed invariant has at least one case
that dies when it is broken. Invariants **not** in these tables are not claimed
to be mutation-checked.

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
| Ledger eviction stops at the first pending action | KILLED |
| Registry -> lease hop broken | KILLED |
| Registry handler hop broken | KILLED |
| Handler accepts a client-supplied `cancel_scope` | KILLED |
| Replacement committed before its predecessor is fenced | KILLED |
| Fenced response keeps its already-queued presentation | KILLED |

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
| Exit leaves its listening window behind | KILLED |
| A retriable interruption handle is dropped unconditionally | **SURVIVED** |
| `ALREADY_SETTLED` treated as fenced | KILLED |
| Playout settled before the stand-down is decided | **SURVIVED** |
| Cleanup acknowledges a deferred announcement | **SURVIVED** |
| Listening barrier matches any pending interruption, not its owner | KILLED |
| A closed activation keeps its unreachable interruption handle | **SURVIVED** |
| Release retires its callbacks before the capture stops | KILLED |
| Release ignores a speech-start observed while stopping | KILLED |
| Late outcome admitted without its exact voice-loop generation | **SURVIVED** |
| Release does not recognise a speaker who started while stopping | KILLED |
| Release keeps the status but opens no successor capture | KILLED |
| A failed answer keeps its listening window | KILLED |

The interruption-admission mutant is killed independently through both branch
outcomes: `mounted in-flight interruption from a retired Session cannot touch its
successor` covers the rejection side (recovery reason, `failed` status) and
`mounted in-flight interruption that succeeds late cannot reset its successor`
covers the success side (cleared output, `idle` status, cleared reason) against a
successor that is already waiting for its own answer.

Seven survivors, in two groups.

**Group A — two halves of one repair that are redundant against each other.**
Both come from the third-review finding that Exit could acknowledge an
announcement that stood down unspoken: the stand-down is decided before
anything settles, *and* cleanup retires such an announcement without an ACK.
Each single mutant survives because the other half still prevents the ACK. The
fifth review settled what this record previously got wrong: it applied the
**combined** mutant — settle before the stand-down is decided *and* bypass the
deferred branch in cleanup — and `mounted Exit never acknowledges a Task
announcement that stood down unspoken` observed the false ACK and failed. The
trigger path is therefore reachable and covered; the earlier
"repaired-but-unproven / unreachable" wording was wrong and is withdrawn. What
is missing is only a case that pins each half on its own.

* Playout settled before the stand-down is decided.
* Cleanup acknowledges a deferred announcement.

**Group B — state hygiene whose external effect is already guaranteed by an
independent guard, so no case can distinguish them:**

* **Surrendered-window cleanup.** With it removed the stale window is still not
  observable, because the notification poll is independently gated by the
  presentation ACK and active-response conditions holding at that point. Found
  by writing the takeover case, not by the case failing. Note the contrast with
  Exit, where the same omission *is* observable and *is* killed -- the two paths
  are not equivalent.
* **Retained retriable interruption handle.** With it removed the capture
  authority barrier still holds, because the owner reports the request pending
  on its own. The handle exists so the request can be replayed through that
  exact owner by `settleRetainedP2Operations`; that replay path is reached only
  through P2 recovery/successor activation and **has no oracle here**.
* **Retiring a closed activation's handle.** Since the fourth-review repair,
  every barrier matches on the owner, so a stale handle can no longer refuse a
  successor anything — which is exactly why removing the retirement changes
  nothing observable. It is kept because a handle whose activation is closed can
  never be replayed through it, and leaving it behind would restore the
  permanent-fence defect the moment any future barrier forgets to match.
* **Exact voice-loop generation on a late outcome.** An interruption outcome
  may only touch UI state belonging to its exact activation, Session *and* voice
  loop. I tried to reach the one state that isolates the loop half — same owner,
  same Session, later loop generation — by Exiting and re-enabling with the
  interruption held on the wire. It is not reachable: the owner's own pending
  request bars the re-enabled loop from capturing, and every visible effect is
  already gated by the owner and Session checks. Recorded as uncovered.

The other surviving mutant is a defence-in-depth guard: with it removed, a playout-time
speech-start would additionally invoke the generation handler, which then returns
without effect because no generation listening window is bound. It is retained
for intent clarity and is recorded here as uncovered rather than claimed.

### 3.2 Invariants with no mutation-sensitive oracle

Stated so they are not mistaken for covered:

* **Ordinary capture never keeps the notification poll alive.** Widening
  `admitsGenerationListeningPoll` to any `starting`/`capturing` leaves the suite
  green. The exception is correct in the code, but nothing stops a regression.
* **A retired Session replays its interruption through the exact owner that
  issued it.** The handle is kept for that purpose while its activation is open,
  but the replay path runs only through P2 recovery/successor activation, which
  no mounted case drives. Since the fourth review, an activation that closes
  retires the handle instead of keeping it forever, so this gap can no longer
  disable the feature — but the replay itself is still unproven here.
* **The exact voice-loop generation on a late interruption outcome.** See the
  Group B entry above: the isolating state is not reachable behind the owner's
  own pending-request barrier.
* **Exact correlation matching on a replacement target.** Found by the fifth
  review, not here: dropping the correlation half of the replacement binding
  check leaves the suite green, because a replacement whose Session,
  interaction and activation all match is already admitted by the activation
  check. Recorded as uncovered.
* **Each half of the Exit stand-down repair on its own.** The combined mutant
  is killed (see §3.1), so the behaviour is covered; what has no oracle is
  either half in isolation.

## 3.3 Convergence after five rounds

Five rounds of point repairs left three shapes that invite the next defect, so
they were collapsed before handing this over. Behaviour is unchanged: the full
sweep is identical at `3961 passed / 11 failed`, Formal Web at `496/496`, and
the mutants for the barrier, the failed-response retirement and the ledger
eviction were re-run afterwards and are still killed.

| Was | Now | Why it mattered |
|---|---|---|
| `pendingGenerationInterruptRef.current?.owner === X` repeated at 11 sites | `ownerHasUnsettledGenerationInterrupt(candidate)` | Round four found three of those sites still matching *any* pending interruption instead of the owner. Eleven copies of one question is how three of them stayed wrong through a round that claimed to have fixed all of them. |
| `generationCaptureRef.current = null` at four unrelated paths, each added by a different round | `retireGenerationListening(matches?)` | Session switch, Exit, ownership surrender and response-failure each had to remember to retire the window, and each was a separate review finding. The complete set is now greppable from one name, with the reason on the function. |
| Four parallel structures keyed by `action_id` (fingerprints, results, errors, an order deque) | one ordered `dict[str, _RetainedGenerationInterrupt]` | Round two's eviction defect existed because a sweep had to keep four structures in step. With one record per action, dropping an action from some structures but not others is unrepresentable. |

The line count moves by `+131 / -92`; nearly all of the addition is the reason
each helper exists, written where the next person will hit it.

## 4. Concurrency coverage

| Concurrent owner | Covered by |
|---|---|
| Exit | Backend `test_exit_owns_the_interaction_and_refuses_a_later_interruption`; frontend `mounted Exit during generation-time listening…` |
| Session switch | Frontend `mounted Session switch during generation-time listening…`, which also asserts a retired Session stops polling notifications, plus `mounted in-flight interruption from a retired Session cannot touch its successor`, which holds a rejected interruption on the wire across the switch and asserts the successor never sees its failure or reason |
| Browser capture ownership | Frontend `mounted browser takeover during generation-time listening surrenders the poll privilege` drives the exact surrender entry point the ownership lifecycle uses (`closeSession`), which is **not** the Exit path. Writing it found that `closeSession` cleaned the P1 owner and capture binding but left the generation-time listening window behind; that is now cleaned too. Generation listening otherwise starts through the same `runAuthorizedMediaStart` and capture-authority barrier as ordinary capture |
| Production Registry -> lease -> Runtime | Backend `test_product_p2_generation_interrupt_reaches_the_runtime_round` drives the real `handle_p2_interrupt_generation` and asserts the effects and round cancellation the Runtime must have produced; breaking either hop kills it |
| Task notification | Backend `test_task_notification_still_speaks_after_a_generation_interruption` — an authoritative Task notification is presented and acknowledged after a fence, with exactly one `round.cancel` issued. Frontend `mounted Task notification stands down for the speaker and is spoken once they finish` — it is not spoken over the speaker, the P1 route carrying their utterance is never torn down, and the exact retained announcement is spoken and acknowledged once after they finish |

## 5. Cancellation is tied to a fenceable target, not to producing the effects

`interrupt_generation` cancels the round whenever the target is still the latest
live response, **including** when the CR fence reports `applied=False`. That
happens when another action already produced the fencing effects -- typically a
prior `barge_in(cancel_response=True)`.

This is deliberate. Barge-in closes AUDIO and cancels the response but never
touches the Harness, so the Agent round is still generating, and that round is
exactly what a speaker interrupting now is asking to stop. Skipping the
cancellation because "this call produced no new effect" would leave it running.
`test_interrupt_after_barge_in_still_stops_the_running_round` fixes this
contract explicitly. A settled or already replaced target is different and does
cancel nothing: there is no fenceable live target at all.

## 6. Explicit non-claims

* No physical microphone/speaker run was performed for this packet. No latency
  measurement is claimed, including for the generation listening window itself.
* Default-off. No flag-on rollout, A/B or rollback evidence exists yet.
* Echo/double-talk behaviour with an open microphone during generation is
  unevaluated. AEC/NS/AGC remain the open Audio I/O items.
* The 11 failures in the full backend sweep are pre-existing on the base commit
  `9a3a65fd0` — eight under `live_voice` (`test_p3_wave2_real_evidence_producer`,
  six in `test_product_composition_registry`, `test_task_progress_return`) and
  three under `gateway` (`test_harmonyos_dev`, `test_streaming_synthesis_route`,
  `test_upload_storage`). Each was reproduced by running the same files in a
  clean detached worktree of that commit, which fails the identical set. They
  are unrelated to this change and are not repaired here.
* This closes the implementation gap only. Feature-complete, controlled-candidate
  and product-readiness boundaries remain unchanged.

## 7. 2026-08-24 targeted closure follow-up

A targeted Tier-3 closure review of `b476873b` returned **FAIL — C0 / I2 /
M0**. This dated section corrects, rather than rewrites, the earlier five-round
record above.

1. The purported single 256-entry interruption ledger still kept pending
   futures in a separate table, so a scheduling burst could retain 256 settled
   identities plus 16 pending identities. `30300f32` repairs this by making one
   `_RetainedGenerationInterrupt` own the exact target, pending future and
   settled result/error from admission through replay. Pending and settled
   identities now share one hard bound; a full ledger fails closed with
   `GENERATION_INTERRUPT_LEDGER_FULL` rather than creating a 257th identity.
2. A provider speech-start arriving while `abandonCapture` releases a silent
   generation window opens a real successor capture, but the existing route
   clears predecessor frames and Batch Speech recognizes the successor capture
   alone. The test proves that the old track ends and the new track is live; it
   does not prove end-of-turn recognition of the full utterance. The user's
   prefix can therefore be lost.

The first repair has the following current-source evidence:

| Check | Result |
|---|---|
| Ledger capacity/replay focused selection | `3 passed / 16 deselected` |
| `test_generation_time_interruption.py` + `test_conversation_runtime_loop.py` | `54 passed` |
| Original affected five-file backend set | `190 passed` |
| Ruff on both changed Python files | PASS |
| `git diff --check` | PASS (line-ending warnings only) |

The second finding is not repaired in this packet. Predecessor and successor
frames carry different exact capture, track and Media authority bindings, while
the existing dedicated Media/Speech authorization and Batch WAV path accept one
capture. Concatenating, relabeling or replaying frames in the browser would
falsify that provenance. A truthful repair therefore requires a separately
scoped Tier-3 multi-segment Media/Speech continuation boundary with positive
full-transcript/EOT evidence and negative stale, cross-Session, cross-track,
replay and zero-business-side-effect oracles.

No frontend suite, full backend sweep, mutation run or physical journey was
rerun for the Runtime-only repair. Historical results above retain only their
exact-source credit. Physical acceptance is blocked until the cross-capture
source boundary is accepted, implemented and reviewed.

## 8. 2026-08-24 cross-capture continuation repair candidate

D-096 accepted the narrow Tier-3 boundary and source candidate `35537a9a`
implements it. This section supersedes only the statement above that the second
finding is unimplemented; it does not grant independent-review or physical
acceptance credit.

The browser closes the exact predecessor uplink with the content-free
`MEDIA_RECOGNITION_CONTINUATION` reason before Streaming settlement, retains
its frames and media close binding in memory, and activates one real successor
that names that predecessor subject. Gateway validates that exact link against
two completed, live media records in the same Session, correlation,
interaction, product activation, browser connection, locale and sample rate.
The Batch request carries two separately finalized WAVs; the server validates
each capture/generation/track/content digest, concatenates PCM only in memory in
predecessor-then-successor order, and invokes one Batch final. Both capture
identities enter one atomic replay/tombstone preflight.

The early close marker is also the duplicate-commit fence. A predecessor marked
for continuation and a successor linked to it can still use Streaming Provider
events for EOT, but neither may mint or return a Streaming voice-commit receipt.
The only final receipt for the continued utterance comes from the combined
Batch result. Missing/reordered markers, stale/reused identity, forged audio or
track, and cross-Session/interaction/activation/connection candidates fail
closed before Provider or business effects.

| Check on `35537a9a` | Result |
|---|---|
| Affected backend: Batch Speech, Media registration/RPC, product authority, Streaming Speech and Python media transport | `257 passed` |
| Formal Integrated Web | `496 passed` |
| Browser Gateway Media | `38 passed` |
| Browser Dedicated Media | `27 passed` |
| Gateway Batch Speech/privacy | `30 passed` |
| Ruff and `git diff --check` | PASS (line-ending warnings only) |
| `npm run build:live-voice` | PASS |

The positive oracle observes negative predecessor samples followed by positive
successor samples in one Provider WAV and one complete final. The browser
journey proves the old track ended, the successor track is live, the successor
receives provider speech-start and EOT, the Batch payload retains both exact
captures, no Streaming-result RPC is used, the predecessor is revoked once
after settlement, and no Agent/Tool/Task method is called. Server negatives
also prove zero competing Streaming receipt for both segments and reject
missing close/activation links.

Current disposition remains **BLOCKED for physical acceptance**. The next
source step is one bounded independent Tier-3 review of `35537a9a` and its
exact diff; only findings in this changed authority boundary require repair and
follow-up. If that review closes, run handoff §5 once on a real microphone and
headphones. Do not restart the five historical broad review rounds.

## 9. 2026-08-24 targeted cross-capture review repair

The independent review of `35537a9a` returned **FAIL — C0 / I5 / M0**. This
result supersedes §8's pending-review wording but does not reopen any historical
broad review. The five findings and their bounded repairs on `4c1c7d68` are:

1. Standalone Batch authorization is now rejected for both a continuation
   predecessor and its linked successor, so neither segment can mint a partial
   or competing receipt.
2. Successor activation now validates and claims the predecessor under the
   Registry lock. The retained predecessor records the one exact successor;
   any sequential or concurrent second claim fails closed.
3. Activation, Batch parsing, browser request construction and combined
   authorization all require distinct predecessor/successor capture
   generations.
4. The advertised Batch identity-tombstone window is clamped to at least two,
   preserving both identities of one combined request even when configured
   with the former minimum of one. Exact predecessor replay remains stale and
   does not reinvoke the Provider.
5. Product P1 Exit now fences the current recognition through the existing
   exact capture/operation cancel path. Local current and predecessor frame
   owners are cleared before waiting for best-effort cancel completion, and
   both media authorities are revoked without Agent/Tool/Task effects.

The new regressions were first run against the failing source: Registry `3/3`,
Batch `2/2`, and the pending-combined-Exit Web oracle all failed for the
reviewed reasons. After the repairs, the current source has this evidence:

| Check on `4c1c7d68` | Result |
|---|---|
| Six-file affected backend set | `261 passed` |
| Batch Speech + dedicated-media registration files | `115 passed` |
| Formal Integrated Web | `496 passed` |
| Browser Gateway Media / Browser Dedicated Media / Gateway Batch Speech | `38 / 27 / 31 passed` |
| Ruff and `git diff --check` | PASS (line-ending warnings only) |
| `npm run build:live-voice` | PASS |

Production code grew by 28 net lines across the four repaired seams; the rest
of the diff is semantic regression evidence. No classifier, product policy,
schema, third continuation segment, Agent/Tool/Task authority or default-on
change was added.

Current disposition remains **BLOCKED for physical acceptance**. The next step
is one fix-only Tier-3 follow-up over `35537a9a..4c1c7d68`, limited to these five
repairs and their cumulative interaction with the accepted D-096 candidate. A
PASS closes the source review Gate; only then may handoff §5 physical acceptance
run. No remote ref was updated.

## 10. 2026-08-24 Exit/cancel follow-up repair

The fix-only review of `4c1c7d68` accepted the other four repaired seams and
returned **FAIL — C0 / I1 / M0** on the remaining Exit/cancel interaction:

- `ProductP1VoiceRouteOwner.close()` waited for browser audio cleanup before
  reaching the recognition fence and both media revocations. A stalled
  `AudioContext.close()` therefore left the Provider request, both raw PCM
  owners and both media authorities live.
- After that explicit fence sent cancel, a late `REQUEST_ABORTED` from the held
  Batch request entered `recognizeFinal()`'s exception path and sent the same
  operation a second cancel.

Candidate `dab640239b1d3f1b887661ebea10266623b336e4` repairs only that seam.
Exit now synchronously claims the exact active recognition token, clears the
current and predecessor frame owners and starts both exact media revocations
before browser cleanup can suspend. Media revocation is single-flight per
owned subject during concurrent Exit/request settlement. The Batch exception
path may send cancel only if it still owns the active recognition token, so the
explicit fence and a late abort cannot both cancel it.

The two new oracles were first compiled through their owning npm scripts
against the unrepaired `4c1c7d68` source:

| Red check | Result before repair |
|---|---|
| Gateway Batch: explicit fence, then held request rejects `REQUEST_ABORTED` | FAIL: `2 !== 1` cancel calls |
| Formal Web: combined recognition Exit while `AudioContext.close()` is held | FAIL: `0 !== 1` synchronous cancel calls |

The same tests also require both exact media-close requests before the audio
gate is released, immediate local `frame_count === 0`, one cancel after the
held request aborts, retained `cleanup_pending` truth while audio remains held,
and zero Agent/Tool/Task effects. Current green evidence is:

| Check on `dab64023` | Result |
|---|---|
| Formal Integrated Web | `496 passed` |
| Gateway Batch Speech | `32 passed` |
| Browser Audio / Browser Gateway Media / Browser Dedicated Media | `103 / 38 / 27 passed` |
| `git diff --check` | PASS (line-ending warnings only) |
| `npm run build:live-voice` | PASS |

No backend, shared protocol, schema, product policy, flag default or
Agent/Tool/Task/history authority changed. The unchanged backend evidence from
`4c1c7d68` remains `261/261`. Physical acceptance remains **BLOCKED** until one
independent, one-finding follow-up of `4c1c7d68..dab64023` returns no unresolved
finding; that review must not reopen the four repairs its predecessor already
accepted. No remote ref was updated.

## 11. 2026-08-24 pending-successor revocation follow-up repair

The follow-up of `dab64023` accepted the synchronous recognition-cancel and
frame-release repair, then returned **FAIL — C0 / I1 / M0** on one cumulative
media-authority race. If successor activation B remained pending, Exit could
finish `media.close(A)` before B returned. B's continuation then unconditionally
put A back into the retained-authority map, so the final Exit rescan emitted
`activate(B), close(A), close(A), close(B)`.

Candidate `6559c38eb61d32cc04e494b79598cfdfd51def53` repairs only that race.
The B activation continuation transfers predecessor A into retained ownership
only if the owner still holds the same exact A binding object. A completed Exit
revoke has already cleared that binding and cannot be resurrected; an in-flight
or failed revoke still owns A and remains retryable. No completed-revocation
tombstone, new collection, protocol field or product policy was added.

The deterministic Formal Web oracle holds B activation, starts Exit, observes
the first A close and local audio release, then lets B settle. Compiled through
the owning npm script, it failed against the unrepaired source with `2 !== 1`
for A closes (`17` selected tests: `16` pass, `1` fail) and passes on the repair
with A and B each revoked exactly once. Current candidate evidence is:

| Check on `6559c38e` | Result |
|---|---|
| Formal Integrated Web | `496 passed` |
| Gateway Batch Speech | `32 passed` |
| `git diff --check` | PASS (line-ending warnings only) |
| `npm run build:live-voice` | PASS (existing bundle warnings only) |

The unchanged backend, Browser Audio, Browser Gateway Media and Browser
Dedicated Media results retain their exact earlier-source credit. Physical
acceptance remains **BLOCKED** until one independent one-finding follow-up of
`dab64023..6559c38e` returns no unresolved finding. No remote ref was updated.

## 12. 2026-08-24 final pending-successor follow-up result

The independent targeted follow-up reviewed immutable repair candidate
`6559c38eb61d32cc04e494b79598cfdfd51def53` against prior candidate
`dab640239b1d3f1b887661ebea10266623b336e4`. An unrelated checkout moved during
the review, but the object-qualified inputs and target worktree were unaffected.
The reviewer found no actionable defect in the repaired seam or its required
cumulative interaction and returned **PASS — C0 / I0 / M0**.

The review confirmed that exact object ownership prevents a successfully
revoked predecessor A from being resurrected when successor B settles. An
in-flight revocation shares one promise; a failed revocation keeps A retained
for bounded retry. B remains independently owned and is revoked exactly once.
The deterministic oracle gates B activation, starts Exit, completes
`close(A)`, settles B and asserts exact A/B close counts.

The reviewer returned these exact results:

| Review check | Result |
|---|---|
| Candidate Formal Integrated Web suite | `496/496` twice |
| Red composition: `dab64023` code plus the new oracle | `594/595`; sole failure A exact close count `2 !== 1` |
| `git diff --check` | PASS |
| New tombstone/collection/protocol/policy/deadlock/unbounded-retention/authority/compatibility finding | None |

The supplied review return did not include complete shell command strings, so
this record does not invent them; it preserves the immutable objects and exact
reported red/green results. This PASS closes the D-096 source review Gate only.
No generation-interruption run has occurred on a real device, so audibility,
false-trigger behaviour, full-utterance recognition, replacement accuracy,
Task concurrency, latency, rollout and product-readiness credit remain open.
The next Gate is the flag-on physical journey in handoff §5.
