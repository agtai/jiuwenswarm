# Generation interruption cross-capture Tier-3 fix-only follow-up prompt

Perform one independent, targeted Tier-3 follow-up review of the five findings
reported against the generation-time cross-capture continuation candidate.

## Immutable target

- Repository branch: `hx/0823_generation_interruption`
- Accepted D-096 implementation base: `35537a9a603cfb542ed2df7e843c74a62610606a`
- Repair commit parent (documentation-only handoff): `c750d6c8c159971c40afca7ca6a94fa31c99e43a`
- Repair candidate: `4c1c7d68814c5a165c01c12d036b0b9adc347b66`
- Primary code/test repair diff:
  `git diff c750d6c8c159971c40afca7ca6a94fa31c99e43a..4c1c7d68814c5a165c01c12d036b0b9adc347b66`
- Finding-to-repair comparison:
  `git diff 35537a9a603cfb542ed2df7e843c74a62610606a..4c1c7d68814c5a165c01c12d036b0b9adc347b66 -- jiuwenswarm tests`
- Cumulative D-096 diff, only when an interaction needs context:
  `git diff 6375e708aa19ba4b04d66c6b411b47eead5592d1..4c1c7d68814c5a165c01c12d036b0b9adc347b66`

First verify `git status --short --branch`, `git rev-parse HEAD`, both immutable
objects and the repair candidate's parent. Later documentation commits are not
part of the source verdict; review the immutable code/test object above.

## Required context

Read, in this order:

1. `live-voice/README.md` and `live-voice/STATUS.md`, following only the relevant
   route.
2. `live-voice/GENERATION_INTERRUPTION_HANDOFF.md` §2 before running anything.
3. `live-voice/decisions/DECISIONS.md` D-096.
4. Only the Tier-3, negative/zero-side-effect and evidence sections of root
   `TESTING.md` that apply to these repairs.
5. `live-voice/evidence/GENERATION_TIME_INTERRUPTION_20260823.md` §§8–9.

Do not restart the five historical broad reviews, re-review settled Runtime/UI
generation-interruption policy, demand physical-device evidence from this
source follow-up, or introduce a new product requirement. Physical acceptance
is deliberately the next Gate after this source follow-up passes.

## Original verdict to close

The review of `35537a9a` returned **FAIL — C0 / I5 / M0**:

1. A continuation predecessor or linked successor could still be authorized as
   a legacy standalone Batch request.
2. One predecessor could be reused by multiple sequential successors because
   activation did not atomically claim it.
3. Equal predecessor/successor capture generations were accepted.
4. `max_identity_tombstones=1` evicted the predecessor of a successful combined
   request and allowed standalone replay to reinvoke the Provider.
5. Exit cleared local owner fields without fencing an in-flight combined Batch
   recognition or sending the available exact cancel RPC.

## Closure questions

Review the repair diff and only the cumulative interactions needed to answer:

1. Does legacy single-segment authorization now reject both continuation
   records while ordinary non-continuation single-capture Batch remains
   unchanged?
2. Are predecessor validation, one-successor claim and successor insertion
   performed under one Registry lock, with the combined authorization later
   checking the exact claimed pair?
3. Do browser construction, server parsing, activation and final authorization
   all fail closed on equal generations without accepting malformed values or
   changing ordinary generation semantics?
4. Does every supported configured tombstone window retain both identities of
   one combined request so predecessor/current replay cannot reinvoke the
   Provider or mint a competing receipt?
5. Does Exit synchronously fence the exact active capture/operation, issue one
   scoped cancel, clear both memory-only frame owners before awaiting remote
   cleanup, revoke both exact media authorities and apply no late result or
   Agent/Tool/Task/history effect?
6. Do the new tests genuinely fail on `35537a9a`, pass on `4c1c7d68`, and assert
   the protected outcomes rather than only implementation details?
7. Did any repair create a new authority escape, deadlock, unbounded retention,
   compatibility regression or partial cleanup in the rest of the accepted
   D-096 path?

You may run risk-proportional read-only checks using the interpreter and npm
rules in handoff §2. Do not edit source in the review task.

## Finding standard and output

Report only actionable defects in a repaired seam or a cumulative regression
caused by `35537a9a..4c1c7d68`. Mark pre-existing, explicitly excluded or new
scope requests separately; they do not count against this candidate.

Every finding must include severity, exact file/line, a concrete reproducer or
event sequence, the violated invariant, observable impact and why the current
tests do not exclude it.

End with exactly one verdict:

- `PASS — C0 / I0 / M0`, or
- `FAIL — Cx / Iy / Mz`, followed by the minimal finding list.
