# Generation interruption pending-successor Tier-3 final follow-up prompt

> W3 integration note (2026-09-02): this source-line record retains its
> historical D-098/D-099/D-100 generation-interruption IDs. Their canonical W3
> equivalents are D-104/D-105/D-106 in `live-voice/decisions/DECISIONS.md`;
> W3's original D-098/D-099/D-100 Task-control decisions are unchanged.

Perform one independent, targeted Tier-3 follow-up review of the single
duplicate predecessor-revocation finding reported against the Exit/cancel
repair candidate.

## Immutable target

- Repository branch: `hx/0823_generation_interruption`
- Prior repair candidate reviewed: `dab640239b1d3f1b887661ebea10266623b336e4`
- Repair commit parent (documentation-only handoff):
  `88367d81877b79253d4d3cb24d1d81a15a2cb110`
- Current repair candidate: `6559c38eb61d32cc04e494b79598cfdfd51def53`
- Primary code/test diff:
  `git diff 88367d81877b79253d4d3cb24d1d81a15a2cb110..6559c38eb61d32cc04e494b79598cfdfd51def53`
- Finding-to-repair comparison:
  `git diff dab640239b1d3f1b887661ebea10266623b336e4..6559c38eb61d32cc04e494b79598cfdfd51def53 -- jiuwenswarm/channels/web/frontend`
- Cumulative D-099 diff only when this one seam needs context:
  `git diff 6375e708aa19ba4b04d66c6b411b47eead5592d1..6559c38eb61d32cc04e494b79598cfdfd51def53`

First verify `git status --short --branch`, `git rev-parse HEAD`, all immutable
objects and the repair candidate's parent. Later documentation commits are not
part of the source verdict; review the immutable code/test object above.

## Required context

Read, in this order:

1. `live-voice/README.md` and `live-voice/STATUS.md`, following only the relevant
   route.
2. `live-voice/GENERATION_INTERRUPTION_HANDOFF.md` §2 before running anything.
3. `live-voice/decisions/DECISIONS.md` D-099.
4. Only the Tier-3, cancel/fence, negative/zero-side-effect and review sections
   of root `TESTING.md` that apply to this repair.
5. `live-voice/evidence/GENERATION_TIME_INTERRUPTION_20260823.md` §§10–11.

Do not restart the historical broad reviews, reopen the accepted standalone
Batch/successor-claim/generation/tombstone/cancel repairs, re-review settled
Runtime/UI policy, demand physical-device evidence or introduce a new product
requirement. Physical acceptance is deliberately the next Gate after this
source follow-up passes.

## Verdict to close

The follow-up of `dab64023` returned **FAIL — C0 / I1 / M0**:

- Exit starts revoking predecessor A while successor activation B is pending.
  If `close(A)` succeeds first, B's activation continuation re-added A to the
  retained map; the final cleanup scan then closed A again before closing B.
  The observed sequence was `activate(B), close(A), close(A), close(B)`.
- A duplicate close can outlive the server's bounded revoked tombstone and leave
  cleanup permanently pending. The old pending-activation test checked only
  `some(...)`; the exact-count oracle did not construct this order.

The prior reviewer confirmed the other red/green evidence and findings. They
are closed context, not new review scope.

## Closure questions

Review the repair diff and only the cumulative interactions needed to answer:

1. When B settles after Exit has successfully revoked A, does exact object
   ownership prevent B from resurrecting A while still publishing and revoking
   B exactly once?
2. If A revocation is still in flight or failed when B settles, does A remain
   retained/retryable without duplicate, cross-subject or lost-authority effects?
3. Does the deterministic oracle genuinely fail on `dab64023`, pass on
   `6559c38e`, construct `activate(B)` pending -> Exit -> successful `close(A)`
   -> B settlement, and assert exactly one close for both A and B?
4. Does the identity comparison remain safe under repeated close, activation
   failure, concurrent cleanup and ordinary single-capture compatibility?
5. Did this repair introduce any deadlock, unbounded retention, completed-close
   tombstone, authority escape, cleanup regression or broader product change?

You may run risk-proportional read-only checks using the interpreter and npm
rules in handoff §2. Do not edit source in the review task.

## Finding standard and output

Report only actionable defects in this repaired seam or a cumulative regression
caused by `dab64023..6559c38e`. Mark pre-existing, explicitly excluded or new
scope requests separately; they do not count against this candidate.

Every finding must include severity, exact file/line, a concrete reproducer or
event sequence, the violated invariant, observable impact and why the current
tests do not exclude it.

End with exactly one verdict:

- `PASS — C0 / I0 / M0`, or
- `FAIL — Cx / Iy / Mz`, followed by the minimal finding list.
