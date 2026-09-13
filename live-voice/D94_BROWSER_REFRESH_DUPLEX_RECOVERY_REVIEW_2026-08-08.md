# D94 browser refresh and duplex recovery review

> Current implementation/review record for the 2026-08-08 W2 browser repair
> batch, frozen as reviewed implementation commit `e821fea84`. This record does
> not claim candidate-bound physical-heard Gate evidence, an Integrated Demo Gate
> result or Replacement Ledger credit. Current mutable state belongs to
> [STATUS.md](STATUS.md).

## 1. Scope and observed failures

This coherent repair batch covers two blockers found during the first physical
OpenAI-backed cumulative browser journey:

1. a hard refresh could lose the formal P2 activation owner and therefore make
   the Formal P1 voice surface unavailable;
2. after recognition, real Agent output and exact text presentation ACK, TTS began
   but was interrupted when the overlapping next capture stopped with generic
   `AUDIO_CAPTURE_STOPPED`.

After D-065 was served, a second user-observed run again reached recognition,
Agent text and TTS. The user heard only “语音联调” before playout stopped; this
time the UI retained exact `AUDIO_RENDER_FRAME_REGRESSED`. That failed run grants
no Gate credit. It exposed a second processor defect: the implementation compared
the next block start to the end of all previously materialized input, so a
monotonic overlapping interval was mislabeled as a render-clock regression.

The second failure was not an Agent/Gateway cancel or a downlink ACK timeout.
Gateway and Agent logs show the committed text, Agent completion and presentation
ACK before the capture uplink and TTS downlink close together. Source inspection
found that the AudioWorklet treated an empty input quantum or any forward render
clock gap as fatal, while Product P1 correctly treats a persistent capture failure
as a reason to stop the exact current playout and revoke both media authorities.

## 2. Implementation contract

Hard-refresh recovery journals the exact P2 activation identity before activation,
reconciles it with the server after reload and either re-adopts, exactly closes and
advances, or remains unavailable. Corrupt, foreign, unknown and storage-failed
states fail closed; a late prior page cannot overwrite the successor.

[D-065](decisions/DECISIONS.md#d-065-aio-b-对-chrome-瞬态空输入采用受限静音时间轴持续异常仍-fail-closed)
supersedes only the historical AIO-B rule that every forward render-input gap is
fatal:

- one gap may be materialized as silence only after non-empty input returns;
- the single-gap limit is 15ms, strictly below one 20ms PCM frame;
- the rolling 1000ms window permits at most 60ms total gap materialization;
- initial empty input emits no frame and cannot establish capture readiness;
- an over-limit gap, rolling-budget overflow or regressed render clock fails with
  an exact stable reason;
- persistent failure still stops the exact response, produces zero playout
  receipt, closes both media authorities and creates no widened business cancel.

This is not dropout concealment, resampling, device switching, quality proof or a
production recovery claim. Render-completed ACK truth is unchanged.

[D-066](decisions/DECISIONS.md#d-066-aio-b-分离-render-clock-与已物化输入边界单调重叠仅作异常兼容去重)
separates the last callback clock from the materialized input frontier. A true
backward clock fails as `AUDIO_RENDER_FRAME_REGRESSED`. Under D-066 an unchanged
clock failed immediately as `AUDIO_RENDER_FRAME_NOT_ADVANCED`; D-067 below
supersedes that one-callback boundary with bounded de-duplication. A strictly
increasing callback that overlaps
the materialized interval is retained only as compatibility for the observed
UA/device anomaly: first-writer-wins discards the duplicate prefix and appends
only the unseen suffix. The duplicate prefix neither inserts silence nor advances
readiness; an unseen suffix is unique real PCM and may normally advance the
sequence, cursor and readiness. Normal Web Audio evidence remains fixed-quantum
contiguous input; overlap tests are not presented as standards-conforming browser
behavior.

The next physical run proved the D-066 playout correction: recognition, committed
Agent text, authoritative TTS and the complete user-heard “语音联调成功” all
finished. The automatically overlapping next capture nevertheless ended as exact
`AUDIO_RENDER_FRAME_NOT_ADVANCED`, so the run remains diagnostic rather than a
complete P1/Gate pass. [D-067](decisions/DECISIONS.md#d-067-aio-b-对同一-render-frame-的短重复回调执行有界去重持续停滞仍-fail-closed)
now de-duplicates at most eight consecutive callbacks at the same render frame,
resets the watchdog on clock advance and keeps the ninth duplicate terminal. An
initial empty callback does not reserve the interval, so same-frame real input can
still establish actual readiness; already materialized samples remain
first-writer-wins.

## 3. Scenario and forbidden-effect closure

- Hard refresh: journal write-before-open, exact active adoption, exact close then
  generation advance, stale-server state, unknown close/reconcile, corrupt or
  unavailable storage, late prior page and concurrent successor are covered.
- Transient positive: the actual processor source feeds BrowserAudioIOAdapter,
  Product P1, the capture uplink and dedicated downlink. Bounded gaps occur during
  second-capture startup and the playing window; TTS completes and the one downlink
  ACK is still emitted only after render completion.
- Persistent negative: repeated sub-threshold gaps exceed the rolling budget;
  long gap, clock regression, unknown Worklet error, track end, context loss, page
  hide, stale callback, missing real first frame and missing Gateway ACK remain
  fail closed.
- Boundary: 48kHz accepts exactly 720 samples for one gap and 2880 samples inside
  the rolling window, partially prunes the oldest interval, fully expires it after
  one second and accepts a later exact-bound gap.
- Render timeline: a reused running context may begin at non-zero `currentFrame`;
  fixed 128- and fixed 256-frame quanta remain contiguous; a suspend interval with
  no callback resumes at the next quantum; full/partial monotonic overlap anomaly
  input is de-duplicated; true backward, sustained unchanged beyond the D-067
  watchdog, non-integer, negative and NaN frame values fail closed and remain
  side-effect-free after failure.
- Duplicate-frame watchdog: one same-frame callback is de-duplicated and a later
  advance resumes normal capture; empty→real at the same frame materializes only
  the real input; eight consecutive duplicates are tolerated and the ninth fails
  exact not-advanced. Watchdog reset after clock advance, immediate regression
  after tolerated duplicates, repeated empty input and same-frame quantum growth
  all have explicit boundaries. The real processor→Adapter→P1/downlink positive
  renders three complete TTS frames, injects a duplicate at final source teardown,
  records exact render ACK/receipt, remains `capturing` and sends the next unique
  PCM frame with continuous sequence/cursor and first-writer samples. The
  during-playout and post-receipt terminal compositions produce no late source,
  media frame, second receipt or cancel and close only their exact authorities.
- Forbidden effects: a playing-window capture failure before render/receipt yields
  zero media playout receipt and no post-failure `capturing`; a post-receipt failure
  retains the one accepted receipt but creates no second receipt. Both paths yield
  zero cancel RPC, close their exact media authorities and create no
  Agent/Tool/Task/history mutation path.

## 4. D-053 review closure

Implementation self-review identified the standards-permitted empty-input behavior,
replaced generic reason folding with an exact closed mapping and retained the
formal duplex/fail-closed cleanup instead of disabling overlap.

The first cold complete-diff review found a missing assertion for zero playout
receipt and no false successor `capturing`; both were added. Its final repeat then
requested exact rolling-boundary and expiry evidence so a future lifetime-budget
regression could not pass; that positive test was added before acceptance. The
post-fix cold confirmation found the evidence gap closed and no remaining P0–P2.

The independent `/review` substitute was read-only. Its first pass found that a
200ms per-gap-only policy could admit indefinitely repeated near-limit gaps and
produce mostly synthetic-silence media. The implementation was narrowed to the
15ms single limit plus 60ms/1000ms rolling budget and received a real
processor→Adapter→P1/downlink composition test. The final independent repeat
reported the original blocker and combination gap closed, with no remaining code
P0–P2. Literal `/review` was unavailable; this is explicitly an equivalent, not a
claim that the product command ran.

The D-066 independent repeat rejected the first overlap tests as proof of normal
Web Audio semantics. Tests and comments were corrected to label overlap only as
an observed UA/device anomaly compatibility path, and the missing conforming
non-zero-start, fixed non-128 quantum, suspend/resume, valid empty-input shape,
invalid-clock and post-failure zero-side-effect cases were added. The Product P1
cold repeat also found that resource cleanup could replace the pending playout
Promise's exact reason; the same stable failure reason now reaches both the
Promise and UI. Its final pass then found a same-call-stack late downlink frame
could enter the browser queue before asynchronous cleanup; downlink admission and
queue refill now synchronously require the exact `playing` owner with no active
failure cleanup. The real processor-regression composition proves zero new audio
source start, zero receipt/cancel and full resource closure. The final independent
repeat reran `176/176` Integrated Web and reported no remaining P0–P2.

The D-067 independent design/cold reviews agreed with the bounded duplicate
compatibility path and found no P0/P1 code defect. They required exact evidence
at the physical failure boundary rather than a one-frame socket-open surrogate:
multi-frame playout through final source teardown, one receipt, retained capture,
continued unique uplink PCM, watchdog reset, post-receipt terminal isolation,
late-frame fencing, same-frame empty input and changed-quantum suffix handling.
Those scenarios were added. Two final independent complete-diff repeats confirmed
the earlier forbidden-side-effect gap closed and reported no remaining P0/P1/P2;
the affected suites passed `74/74` Browser Audio and `178/178` Integrated Web at
that checkpoint. The
callback-count watchdog does not claim to detect a processor that emits no
callbacks at all; existing first-frame/route deadlines remain authoritative for
startup liveness. The later physical rerun described in section 6 closed the
D-067 source blocker without creating immutable Gate evidence.

A separate read-only Tier-2 review covered the complete hard-refresh diff:
write-ahead journaling, exact-binding replay and close, generation advance, CAS
conflict handling, delayed prior-page and cross-Session fencing, retry barriers,
server-state-loss handling, mounted integration and the affected test command.
It found one final P2 combination-evidence gap for an active recovery response
missing valid replay truth while exact predecessor close repeatedly fails. The
mounted test now proves that all three first-pass close attempts retain generation
1 and a `closing` journal barrier with zero generation-2 activation; the next
recovery closes only generation 1, then activates generation 2 and never closes
the successor. A final independent read-only repeat verified missing/non-boolean
replay normalization, exact retained owner/CAS behavior and late-run fencing,
reran `176/176` Integrated Web, and found no remaining P0–P2.

## 5. Automated verification and remaining Gate evidence

- Browser Audio/AudioWorklet strict compile, bundle and Node suite: `74/74 PASS`.
- Integrated Web/P1/P2/P3alpha affected suite: `187/187 PASS`.
- Full frontend TypeScript/Vite production build: `PASS`.
- `git diff --check`: `PASS` with only the repository's existing Windows line-ending
  notices.

The physical runs described above are historical diagnostic evidence, not
acceptance evidence. The latest completed ASR→committed Agent text→authoritative
TTS was heard in full by the user and visibly returned to the automatic next
capture. Product source publishes that `capturing` state only after downlink
render completion, the render-driven receipt has been accepted and the exact
playout authority has been revoked, so the observation closes the D-067 source
blocker. It was performed on a mutable local batch without a sealed evidence root
and therefore grants no Integrated Demo Gate or Replacement Ledger credit.

The later failure after approximately 30 seconds of no further speech was the
declared complete-utterance retention boundary, not a regression in the completed
turn. D-068 gives that boundary an exact reason and safe zero-submission cleanup.
The reviewed implementation is frozen at `e821fea84`. The next Gate action is to
create fresh isolated runtime/evidence roots before any controlled showcase,
fault or restart run.

## 6. D-067 mutable-source diagnostic and D-068 capture-bound closure

The D-067 physical rerun recognized the user's phrase (with the homophone-quality
variant `连调` for intended `联调`), committed the confirmed text to the real
JiuwenSwarm Agent, synthesized the authoritative response, played the complete
audio heard by the user and returned to automatic successor capture. That state
transition is source-significant: Product P1 publishes successor `capturing` only
after browser render completion, receipt acceptance, downlink drain and exact
playout-authority revocation. It closes the D-067 physical source blocker, while
remaining assisted diagnostic observation on mutable source rather than sealed
Gate evidence.

No second utterance was provided. At `1500` retained 20ms frames—30 seconds of
materialized audio and approximately 30 seconds of wall time during continuous capture—the next frame
hit Product P1's complete Batch STT retention limit. ACK cannot release those
frames because final recognition still requires the full utterance, and the route
has no VAD/EOT; silent input therefore consumes the same bounded timeline. The
old callback throw crossed the Adapter's untrusted observer boundary and appeared
as generic `AUDIO_FRAME_CONSUMER_FAILED`.

D-068 retains the 30-second captured-audio bound and handles it inside Product P1
as exact `AUDIO_CAPTURE_DURATION_EXCEEDED`. It synchronously fences late frames,
clears local PCM/counters before any fallible cleanup, attempts exact authority
revocation and performs zero new Speech, Agent, Tool, Task, history, receipt or
cancel effect attributable to expiry. An already accepted receipt remains unique.
At exactly 1500 frames, `Stop and recognize` remains valid and sends the complete
bounded WAV. The UI discloses that the turn retains at most 30 seconds of captured
audio and that audio captured during overlapping playout counts toward the limit,
explains that expired audio was not submitted, and disables
a terminal failed owner until refresh. A retained singleflight Start also prevents
two same-tick attempts from allocating two successor microphones while exact old
authority cleanup is pending.

The self/cold review rejected an unbounded retention increase, rolling frame
eviction and automatic silence recognition because they respectively create
unbounded privacy/memory exposure, truncate Batch STT or risk paid/false business
effects. The independent complete-diff reviews then found four P1 races:
expiry after final render but before receipt dispatch, remote cleanup failure
retaining raw PCM, retained Start allocating after unmount, and the narrower
render-complete/detach-wait window losing its playout owner and exact reason. They also found
that the original late-frame test called an already-null handler and that UI/docs
described frame capacity as a wall-clock timer. The implementation now rechecks
operation generation immediately before receipt dispatch, retains a settling
playout owner through detach/receipt/revoke, keeps the first terminal reason
idempotent, clears PCM before any await/revoke, fences retained Start by
mounted/current Session/current authority, and uses truthful captured-audio
wording. Tests invoke the saved frame handler in the same stack and after cleanup,
cover render→receipt expiry, held detach wait, close-failure retry, Session
replacement and unmount. Two final independent read-only repeats report
P0/P1/P2 = `0/0/0` on the complete repaired diff.

Automated evidence covers the 1500-frame positive boundary, exact 1501st-frame
failure, zero forbidden effects, preserved prior receipt, late-frame fencing,
exact close retry and mounted Start singleflight. Final affected verification is
`74/74` Browser Audio and `187/187` Integrated Web, with the production build and
`git diff --check` passing. Formal VAD/EOT or streaming recognition remains a
post-W2 capability rather than an implicit part of this repair.
