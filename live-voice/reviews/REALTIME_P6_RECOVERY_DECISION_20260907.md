# P6 recovery scheduling: retain the bounded reserve

Main accepted this decision on 2026-09-07 after the independent review and
Astra max design review found two counterexamples to early recovery rescheduling.
The [full optimization packet](REALTIME_OPTIMIZATION_FULL_20260907.md) owns the
overall task; [TESTING](../../TESTING.md) owns verification and review. This is a
Tier 2 browser scheduling decision with regression evidence. It does not change
the media protocol, playout authority, capture path or Provider.

## Accepted behavior and scope

Retain the existing 250 ms first-PCM lead and bounded 250–750 ms recovery reserve.
Receiving enough PCM to cover an earlier interarrival interval does not authorize
moving already scheduled audio earlier. Preserve exact PCM order, rendering ACK,
response isolation, stop and tentative pause behavior. The owned surfaces are
`browserAudioIOAdapter.ts`, its focused Node tests and this decision record.

Withdraw the candidate which stopped and recreated all unstarted recovery
sources at `now + 20 ms` once queued PCM duration reached the reserve. Preserve
the rejected candidate as ignored evidence and add regression oracles for the
two reported defects. No performance gain is claimed; the imported 1–1.5 second
P6 target remains unmet. P5 can improve delivery of ready frames, but its supply
improvement is not evidence of a P6 reserve-delay saving.

## Why the candidate is rejected

**A reserve filled by one burst cannot predict the next burst.** With 20 ms
frames, receive one frame at 0, 33 frames at 0.65 seconds and 50 at 1.35 seconds.
The existing schedule has one 1.03 second gap. The rejected schedule advances
the first recovery burst and creates two gaps, 0.40 and 0.04 seconds. The smaller
total silence does not satisfy the requirement to avoid adding underruns.

**One clock check cannot establish that stopped sources were never played.**
Receive the recovery burst at 0.65 seconds, with the last frame satisfying the
candidate's reserve threshold at 1.275 seconds. Recovery was scheduled for 1.300.
A 30 ms main-thread delay before the first stop takes effect can let the audio
clock reach 1.305. Recreating that frame at offset zero can repeat five milliseconds
of PCM. A later clock check cannot undo those samples. An estimated offset does
not prove which samples actually rendered, and failing after cancellation can
truncate accepted speech; neither establishes the candidate's no-glitch contract.

The browser adapter receives single PCM chunks without an authenticated complete
stream/final-cursor signal. The upper product route observes expected transport
completion and retains an exact final cursor, separately from actual rendering.
Passing that existing fact to the adapter could bound a future complete-tail
proposal, but it would not make stop/recreate atomic. A different queue or audio
processor scheduling design needs its own explicit contract, ownership and
evidence. No such broader player or shared protocol change is included here.

## Evidence

The adapter was restored exactly to the source at
`ebeb5aa4db828b69489ce205de85ebd1d3a1c5a5`, Git-normalized SHA-256
`d693a31b9700fa7ac835ed3cce82f080a8d6dde748e62ec5f86e54f7ee03eb50`.
There is no remaining production-source diff. The final change contains two
regression tests, three burst/tail/healthy-supply subcases and this record.
The original candidate is retained under the P6 worktree's ignored
`logs/p6-rejected-recovery-20260907/` directory:

- `candidate-browserAudioIOAdapter.ts`, SHA-256
  `b81e101e25c9e16353e74a7eb6db3c134fcdb44e3b1c86a94d02790848743731`.
- `candidate-liveVoiceBrowserAudioIOAdapter.test.mjs`, SHA-256
  `9daca66250c12938b4a359ecc48a24467e9b60debc09b71f3ad403348e0239a0`.

The ignored `run-regressions.mjs` bundles each frozen adapter against the same
unchanged dependencies and runs the same final regression source with Node
`v24.14.0`. Run it from the worktree with
`node logs/p6-rejected-recovery-20260907/run-regressions.mjs`. Its
`regression-comparison.json`, two bundles, two generated test files and
`baseline-regression.txt` / `candidate-regression.txt` retain both outcomes.

- Baseline: all five focused Node cases passed.
- Rejected candidate: the burst counterexample produced two gaps instead of
  one, and the stop-delay counterexample scheduled 32,880 rendered samples from
  32,640 supplied samples at 48 kHz: a repeated 240-sample prefix. Short-tail
  and healthy-supply controls passed. Node also marks the containing parent
  test failed; that is not a third independent defect.
- `npm run test:live-voice-browser-audio-io`: strict adapter TypeScript validation,
  bundling and all 125 browser audio/capture tests passed after rollback. This
  includes existing recovery pause/resume, cancellation, stale response,
  cleanup uncertainty and duplicate callback regressions. Exact output is
  `accepted-audio-regression.txt` in the same ignored evidence directory.
- The complete scoped diff was reviewed. `git diff --check` passed, and the
  adapter hash matches the baseline. Main performs the integration review and
  checks the full-packet link in the integration worktree, where that packet
  was created after this worker's baseline.

Deterministic AudioContext schedules and PCM/callback observations are evidence
for this local contract. They do not measure physical speaker output or perceived
continuity, and they cannot establish the imported optimization target.
