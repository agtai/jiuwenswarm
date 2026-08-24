# Generation interruption Exit/cancel Tier-3 final follow-up prompt

Perform one independent, targeted Tier-3 follow-up review of the single
Exit/cancel finding reported against the first cross-capture repair candidate.

## Immutable target

- Repository branch: `hx/0823_generation_interruption`
- First repair candidate reviewed: `4c1c7d68814c5a165c01c12d036b0b9adc347b66`
- Repair commit parent (documentation-only handoff):
  `0573e327ef50f90d7d8a163bed862961dd5a1c04`
- Current repair candidate: `dab640239b1d3f1b887661ebea10266623b336e4`
- Primary code/test diff:
  `git diff 0573e327ef50f90d7d8a163bed862961dd5a1c04..dab640239b1d3f1b887661ebea10266623b336e4`
- Finding-to-repair comparison:
  `git diff 4c1c7d68814c5a165c01c12d036b0b9adc347b66..dab640239b1d3f1b887661ebea10266623b336e4 -- jiuwenswarm/channels/web/frontend`
- Cumulative D-096 diff only when this one seam needs context:
  `git diff 6375e708aa19ba4b04d66c6b411b47eead5592d1..dab640239b1d3f1b887661ebea10266623b336e4`

First verify `git status --short --branch`, `git rev-parse HEAD`, all immutable
objects and the repair candidate's parent. Later documentation commits are not
part of the source verdict; review the immutable code/test object above.

## Required context

Read, in this order:

1. `live-voice/README.md` and `live-voice/STATUS.md`, following only the relevant
   route.
2. `live-voice/GENERATION_INTERRUPTION_HANDOFF.md` §2 before running anything.
3. `live-voice/decisions/DECISIONS.md` D-096.
4. Only the Tier-3, cancel/fence, negative/zero-side-effect and review sections
   of root `TESTING.md` that apply to this repair.
5. `live-voice/evidence/GENERATION_TIME_INTERRUPTION_20260823.md` §§9–10.

Do not restart the historical broad reviews, reopen the four `4c1c7d68` repairs
the preceding follow-up accepted, re-review settled Runtime/UI policy, demand
physical-device evidence from this source review or introduce a new product
requirement. Physical acceptance is deliberately the next Gate after this
source follow-up passes.

## Verdict to close

The follow-up of `4c1c7d68` returned **FAIL — C0 / I1 / M0**:

- `ProductP1VoiceRouteOwner.close()` awaited browser audio and other cleanup
  before reaching the exact recognition fence and clearing the two current/
  predecessor PCM owners. If audio cleanup stalled, no cancel or media revoke
  was sent.
- After `fenceRecognition()` sent cancel, a late `REQUEST_ABORTED` from the held
  Batch request caused `recognizeFinal()` to cancel the same operation again.
  The diagnostic sequence was `recognize_batch, cancel, cancel`.

The prior reviewer confirmed the other red/green evidence and findings. They
are closed context, not new review scope.

## Closure questions

Review the repair diff and only the cumulative interactions needed to answer:

1. At the synchronous start of Exit, before any fallible browser cleanup can
   suspend, does the owner claim the exact active recognition fence, release
   both local frame owners and initiate both exact media revocations?
2. Does stalled or failed audio cleanup retain truthful `cleanup_pending`
   status without delaying those remote fences, widening cancellation or
   applying a late result?
3. Can exactly one path own cancel for an active recognition token, including
   explicit fence followed by `REQUEST_ABORTED`, timeout/signal cancellation,
   replacement and repeated close?
4. Are concurrent/stale media-revocation callers single-flight and bounded,
   while pending activation and failed-close retry still revoke every exact
   owned authority without duplicate or cross-subject effects?
5. Do the two new oracles genuinely fail against the `4c1c7d68` behaviour,
   pass on `dab64023`, hold `AudioContext.close()`, reject the pending Batch
   request after fencing, and assert cancel/revoke/frame/forbidden-effect
   outcomes rather than only source ordering?
6. Did this repair introduce any deadlock, unbounded retention, authority
   escape, cleanup regression or ordinary single-capture compatibility change?

You may run risk-proportional read-only checks using the interpreter and npm
rules in handoff §2. Do not edit source in the review task.

## Finding standard and output

Report only actionable defects in this repaired seam or a cumulative regression
caused by `4c1c7d68..dab64023`. Mark pre-existing, explicitly excluded or new
scope requests separately; they do not count against this candidate.

Every finding must include severity, exact file/line, a concrete reproducer or
event sequence, the violated invariant, observable impact and why the current
tests do not exclude it.

End with exactly one verdict:

- `PASS — C0 / I0 / M0`, or
- `FAIL — Cx / Iy / Mz`, followed by the minimal finding list.
