# P1/P2 post-TTS capture continuation: deferred issue record

## Scope and disposition

- Observed product source:
  `f24dd17d336c8266954f2d7299ca13bd0314d424`.
- Original controlled-candidate result: **FAIL — not a controlled
  product-readiness candidate**. That immutable result remains recorded in the
  [P3-G0 attempt](P3_G0_PRODUCT_READINESS_FAIL_20260819_f24dd17d.md).
- Current disposition: defer this P1/P2 media/conversation defect until formal
  P1/P2 moves from `PARTIAL` to `COMPLETE`. It no longer blocks P3-1 expansion,
  but it still blocks a controlled product-readiness PASS and the later
  feature-complete boundary.
- This record grants no source fix, physical PASS or product-readiness credit.

## Product expectation

Live Voice is not required to keep the microphone active outside a user-started
interaction. During an active hands-free interaction, however, short and long
TTS responses must return automatically to usable listening until the user
chooses Exit. A background Task must continue according to its own lifecycle
after voice capture or the interaction closes.

## Observed phenomenon

Two real microphone/Agent/TTS turns on the same clean source reproduced the
same failure:

- the first turn reached presentation acknowledgement, then the route entered
  `AUDIO_CAPTURE_DURATION_EXCEEDED` and required manual `重新监听`;
- manual retry admitted a second real utterance and response, but the same
  failure recurred;
- the second failure occurred about 31 seconds after the Agent final and only
  about 15 seconds after presentation acknowledgement, so it was not a fresh
  30-second post-TTS silence timeout;
- the abrupt media failure was followed by
  `STREAMING_SPEECH_ROUTE_ABORTED`, bounded transport-cleanup timeout and
  `STREAMING_SPEECH_CANCEL_UNACKNOWLEDGED`;
- the complete background create/adjust/status/result/terminal Journey could
  not start. Read-only Task DB counts and the target project/file remained
  unchanged.

## Confirmed mechanism and unresolved attribution

The current P1 owner starts the successor capture before streaming TTS playout,
so TTS time consumes the same 30-second capture-lease budget. At the boundary,
a capture with no speech evidence is intended to rotate transparently and
continue listening.

Rotation is prevented when either of these retained conditions is true:

1. the current provider lease has emitted authoritative `speech_start`; or
2. after playout, one browser frame crosses the local RMS energy floor. That
   local observation is sticky for the remainder of the lease rather than a
   decaying indication of recent activity.

Consequently, pure digital silence is expected to rotate, but a user who says
nothing can still see the failure after a single TTS tail, echo, environmental
sound or other frame crosses the local threshold. A current-provider
speech-start arriving near rotation produces the same fail-closed outcome.

The retained runtime log did not record enough client event timing to prove
whether either physical occurrence was caused by local energy, provider
speech-start or the exact rotation race. The mechanism is confirmed from source
and timing; the physical trigger branch remains deliberately unattributed.

## Deferred repair direction

When the P1/P2 completion packet is activated:

1. Add a deterministic regression for one post-playout high-energy frame
   followed by silence through the lease boundary. It must rotate without a
   visible error or forbidden Agent/Tool/Task/history effect.
2. Separate short-lived local activity from authoritative provider speech
   state. A local energy observation must decay and must not permanently block
   a silent lease rotation.
3. Separate capture-lease age from active-utterance duration. With no
   authoritative active utterance, the 30-second lease must rotate
   transparently; a real current utterance must not be truncated.
4. Preserve provider speech-start/EOT, barge-in, generation fencing and stale
   lease isolation, including speech-start/rotation races.
5. Add sanitized diagnostics for capture phase/generation, frame count, recent
   local activity, provider speech-start/EOT, rotation reason and actual
   browser AEC/NS/AGC settings. Do not log raw audio, credentials or private
   device identity.
6. Recheck provider cancel/cleanup after the primary P1 failure is removed. If
   unacknowledged cancellation persists independently, repair its bounded,
   idempotent cleanup in a separate affected owner.

Changing only the 30-second threshold is not an accepted repair: it delays the
same state error and increases retained audio. Disabling concurrent capture is
also not equivalent because it removes hands-free barge-in.

## Later acceptance

P1/P2 cannot become `COMPLETE`, and a controlled product-readiness candidate
cannot pass, until one exact clean source proves at least:

- repeated short and long TTS turns automatically return to usable listening;
- quiet listening crosses multiple capture-lease boundaries without a visible
  error or manual retry;
- real barge-in and post-playout speech are preserved without duplicate commit;
- no stale audio/history or cross-response/round/Task effect occurs;
- streaming recognition and cancel cleanup settle without retained authority;
- Exit closes capture, playout, timers, reconnect and media leases.

Per the accepted 2026-08-19 sequencing decision, this deferred P1/P2 closure is
not a hard dependency of P3-1. It returns before the cumulative
feature-complete/develop-integration boundary.

## Repair status (2026-08-19)

The `P1/P2-T1` packet implemented the repair directions above with source and
affected automated evidence; see the
[repair record](P1_T1_POST_TTS_CAPTURE_ROTATION_REPAIR_2026-08-19.md). The
later-acceptance criteria in this record remain open and unchanged: they close
only on a real microphone/TTS run, and no physical or candidate credit is
granted by the automated repair.
