# Generation interruption cross-capture Tier-3 review prompt

Perform one independent, targeted Tier-3 source review of the generation-time
speech-continuation repair.

## Immutable target

- Repository branch: `hx/0823_generation_interruption`
- Review base: `6375e708aa19ba4b04d66c6b411b47eead5592d1`
- Candidate: `35537a9a603cfb542ed2df7e843c74a62610606a`
- Primary diff: `git diff 6375e708aa19ba4b04d66c6b411b47eead5592d1..35537a9a603cfb542ed2df7e843c74a62610606a`

First verify `git status --short --branch`, `git rev-parse HEAD`, both object
IDs, and the candidate's parent. Review the immutable committed code/test diff;
later documentation-only changes are not part of the source verdict.

## Required context

Read, in this order:

1. `live-voice/README.md` and `live-voice/STATUS.md`, following the one relevant
   README route only.
2. `live-voice/GENERATION_INTERRUPTION_HANDOFF.md` §2 before running anything.
3. `live-voice/decisions/DECISIONS.md` D-098 and D-099.
4. Only the Tier-3, negative/zero-side-effect and evidence sections of root
   `TESTING.md` that apply to this changed boundary.
5. `live-voice/evidence/GENERATION_TIME_INTERRUPTION_20260823.md` §§7–8.

Treat D-099 as the accepted product/protocol decision. Do not reopen the five
historical broad review rounds or demand physical microphone evidence from this
source review. Physical acceptance is deliberately the next Gate.

## Intended invariant

When provider speech-start arrives while `abandonCapture` is releasing the
generation listening window:

- the predecessor uplink closes with one content-free continuation marker
  before Streaming receipt settlement;
- one real successor capture names that exact predecessor subject;
- predecessor and successor keep distinct subject/capture/generation/track and
  separate finalized WAV provenance;
- Gateway validates both live media authorities, their digests, order and
  shared Session/correlation/interaction/product activation/browser
  connection/locale/sample rate;
- the server concatenates PCM in memory in predecessor-then-successor order and
  makes one Batch final request;
- neither segment can mint or return a competing Streaming commit receipt;
- both capture identities enter one atomic replay/tombstone preflight;
- success, rejection, cancellation, Exit and cleanup release memory-only frames
  and exact authorities without Agent/Tool/Task/history effects.

Ordinary single-capture Streaming/Batch, silent release, capture rotation,
`pauseIdleCaptureForNotification`, feature defaults and Task policy are
excluded and must remain behaviourally unchanged.

## Review questions

Inspect the full changed dataflow, not just the positive test:

1. Is the optional `predecessor` request shape closed, bounded and backward
   compatible, including null/open/malformed values and combined audio limits?
2. Can any ordering, concurrency or alternate RPC sequence obtain a Streaming
   receipt for the predecessor or successor and later obtain the Batch receipt?
3. Can a client omit, forge, replay, reorder or transplant the predecessor
   close marker or successor activation link across any authority dimension?
4. Does authorization compare the two exact server-retained media records and
   content digests, rather than trusting browser labels or concatenated bytes?
5. Are replay/tombstone updates all-or-nothing, bounded, and correctly scoped
   across the two different media subjects while the current capture remains
   the cancellation/result identity?
6. Do provider failure, empty final, timeout, cancellation, successor startup
   failure, authority-revoke failure and owner cleanup fail closed without raw
   audio retention or partial business effects?
7. Does the P1 state machine preserve the complete utterance and EOT ordering
   while leaving normal single-capture paths unchanged?
8. Do the tests assert semantic outcomes and forbidden-effect zeros, especially
   PCM order, missing link/marker, stale/replay, forged audio/track, cross
   Session/interaction/activation/connection, and both Streaming receipt
   fences? Identify any materially missing oracle.

You may run risk-proportional read-only checks using the commands and interpreter
rules in the handoff. Do not edit source in the review task.

## Finding standard and output

Report only actionable defects introduced by this candidate:

- **Critical:** authority escape, duplicate business commit, privacy breach,
  destructive effect, or broadly exploitable fail-open.
- **Important:** a supported positive path can lose/corrupt speech, an exact
  authority/replay/cleanup invariant is breakable, or a required negative path
  has a protected side effect.
- **Minor:** a concrete bounded defect that should still block this package's
  source Gate; do not use Minor for style, preference, test-count commentary or
  unrelated cleanup.

Every finding must include severity, exact file/line, a concrete reproducer or
event sequence, the violated invariant, observable impact, and why existing
tests do not already exclude it. Mark pre-existing or explicitly excluded
issues separately; they do not count against this candidate.

End with exactly one verdict:

- `PASS — C0 / I0 / M0`, or
- `FAIL — Cx / Iy / Mz`, followed by the minimal finding list.

If this pass fails and fixes are made, the follow-up reviews only the finding's
changed seam plus cumulative interactions with the rest of this candidate. It
does not restart a broad historical review or add new product scope.
