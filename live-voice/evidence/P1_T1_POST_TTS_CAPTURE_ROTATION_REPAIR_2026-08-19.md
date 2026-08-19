# P1/P2-T1: post-TTS capture continuation repair — source and automated evidence

## Scope and disposition

- Packet: `P1/P2-T1` under the D-060/D-062 batch recorded in
  [STATUS](../STATUS.md); contract owned by the
  [deferred issue record](P1_P2_POST_TTS_CAPTURE_CONTINUATION_DEFERRED_20260819.md).
- This record grants **source and affected automated credit only**. The
  physical later-acceptance criteria (repeated real TTS turns returning to
  usable listening, quiet multi-boundary listening, real barge-in, Exit
  closure) remain owned by the deferred record and close only on a later real
  microphone/TTS run. No controlled-candidate, physical or product-readiness
  claim is made or implied.
- Files changed: `productP1VoiceRoute.ts`, `LiveVoiceIntegratedRoutePanel.tsx`
  (disclosure text only), `productP1VoiceRoute.test.mjs`,
  `liveVoiceIntegratedRoutePanel.test.mjs`. No Task Store/Core, P3 schema,
  central registry, server or adapter code was modified.

## Repaired mechanism

Before: the successor capture starts before TTS playout, so playout time
consumed the single 30-second lease budget; one post-playout frame crossing
the local RMS floor set a sticky `#captureSpeechObserved` for the remainder of
the lease; the boundary rotation was refused and the route failed with
`AUDIO_CAPTURE_DURATION_EXCEEDED`. A late local-energy frame could also abort
an in-flight idle rotation into the same visible failure.

After, per the six repair directions:

1. **Deterministic regression** — `formal P1 decays one post-playout energy
   frame and rotates the silent lease boundary` drives exactly the recorded
   phenomenon (one high-energy frame after playout, then silence through the
   boundary) and requires transparent rotation with zero forbidden
   Agent/Tool/Task/history effects. It failed on the pre-repair source and
   passes on the repaired source.
2. **Decaying local activity** — the sticky flag is replaced for rotation
   purposes by `#captureLocalActivityRecencyFrames`, refreshed by each
   above-floor frame and decaying over 1.5 s (75 frames) of sub-floor frames.
   Recent activity defers the boundary rotation inside a bounded grace
   (75 frames); sustained energy that the Provider never confirms rotates at
   the grace end instead of expiring the lease. The sticky observation is
   retained solely for the notification-pause guard, whose behaviour is
   unchanged.
3. **Lease age separated from utterance duration** — the 30-second budget now
   bounds one authoritative utterance from its provider speech-start
   (`#captureUtteranceStartFrameIndex`); with no authoritative utterance the
   lease always rotates (at the boundary or grace end) and can no longer fail.
   The 30-second value itself is unchanged. A defense-in-depth absolute frame
   ceiling (`2 × 1500 + 75`) bounds memory; every legal path rotates or fails
   the utterance budget first.
4. **Races preserved** — a current-lease provider speech-start still aborts an
   in-flight rotation through the unchanged fail-closed checkpoints; stale
   prior-lease speech-start isolation, barge-in delivery, generation fencing
   and the drain/completeUplink sequence are unchanged. The idle-rotation
   guard no longer re-checks local energy mid-rotation (the dispatch decision
   already weighed it), removing the late-echo abort spur.
5. **Sanitized diagnostics** — `captureDiagnostics()` exposes capture
   phase/generation, frame counts, decaying local activity, provider
   speech-start/EOT, utterance start index, rotation state with last-rotation
   mode/trigger, and actual browser AEC/NS/AGC settings from the capture
   track. A bounded `live_voice_capture_rotation` warn line records the
   grace-elapsed trigger. No raw audio, transcript, credential or device
   identity enters the surface.
6. **Cancel/cleanup recheck** — the observed
   `STREAMING_SPEECH_ROUTE_ABORTED`/`STREAMING_SPEECH_CANCEL_UNACKNOWLEDGED`
   chain followed the capture failure; its trigger is removed at the source.
   No server/gateway code was touched; the existing bounded cancel truth
   retains its own suites (`test_streaming_speech_route.py`,
   `test_openai_streaming_speech.py`, including
   `test_recognition_cancel_is_local_fence_not_provider_ack`). Whether an
   independent unacknowledged-cancel phenomenon persists is re-checked on the
   next real run; if it does, it becomes its own affected packet per the
   deferred record.

## Contract changes disclosed

- The user-visible capture contract is now "one utterance ≤ 30 s from
  recognized speech start"; the Integrated Web disclosure text was updated
  accordingly, and the `AUDIO_CAPTURE_DURATION_EXCEEDED` explanation names the
  utterance budget.
- Four existing oracles were updated to the repaired contract, not deleted:
  the two `exerciseCaptureDuration*` journey drivers anchor the failure to a
  real provider speech-start and accept the exact failure within a bounded
  three-frame window past the former lease-age bound (the precise one-frame
  re-anchoring of direction 3 is pinned by the 1701-frame continuation
  oracle, not by these drivers);
  `formal P1 protects a current provider speech-start after playout and bounds
  its utterance` drives two extra frames; the post-receipt duration tests gain
  `negotiatedEot` so the utterance anchor is deliverable. One uplink-count
  bound widened by exactly one frame. All other rotation, race, notification
  and boundary oracles pass unchanged.
- `formal P1 accepts Stop and recognize at the exact 30-second capture
  boundary` passes unchanged: sustained speech-energy frames defer rotation,
  so a full 1500-frame stop-and-recognize at the boundary behaves as before.

## Disclosed limitations (routed, not repaired here)

**Manual-EOT / missed-VAD speech across a rotation.** When the end-of-turn
capability is in manual fallback, or the Provider misses real speech entirely,
no utterance ever becomes authoritative, so speech spanning the boundary/grace
rotates with the lease and a later manual Stop commits only the successor
tail. This is the contracted resolution (local energy must decay; only
provider speech-start is authoritative) and replaces the pre-repair visible
failure, but the truncated-tail consequence is owned by the Speech
Recognition/Interaction Intelligence fallback scope, and the Web disclosure's
"recognized start of speech" has no operative meaning in that degraded mode.

**Extended-lease batch WAV size.** A lease lawfully extended past 30 s (deferred rotation grace or a
late-starting utterance) uploads its complete frame set on the batch-fallback
tier, because the Speech client requires batch recognition input to start at
the first captured frame. A late-started utterance on a long lease can
therefore exceed the Gateway's 4 MB WAV bound only when streaming recognition
is already degraded. This corner is disclosed and routed to the Speech
Recognition fallback-robustness scope (Track 3); the streaming-primary path is
unaffected, and the new
`formal P1 keeps an authoritative utterance alive past the lease bound and
recognizes it` oracle records the exact current batch behaviour (complete
1701-frame WAV).

## Automated evidence (exact commands, current source)

Frontend, Node v24.18.1, from `jiuwenswarm/channels/web/frontend`:

- `npm run test:live-voice-integrated-web` (tsc strict + esbuild + 15 suites,
  including `productP1VoiceRoute.test.mjs` 86/86 with the new/updated rotation
  oracles and the panel disclosure suites): **410 passed, 1 failed of 411.**
  The single failure is the pre-existing deferred Runtime/Web seam
  `mounted Exit and immediate re-enable recover after old unified success or
  rejection without replaying TTS` already recorded in [STATUS](../STATUS.md)
  and the P3-1 review at 406/407; it reproduces unchanged on this diff, is
  disclosed and excluded, and receives no repair or credit here.
- `npm run test:live-voice-browser-audio-io` (adapter + capture processor):
  **103 passed, 0 failed** (no source change in these files; regression only).
- New tests added: post-playout decay rotation (P/T), deferral-then-decay
  rotation (B/T), sustained-energy grace-end rotation with
  `local_activity_grace_elapsed` diagnostics (B/F), authoritative utterance
  continuation past the former bound with full batch recognition (P/K), and
  the updated utterance-budget failure oracles (N/B/S).

Backend: no backend file changed; no backend affected run is claimed. The
D-032 `X` (real path) dimension is explicitly not claimed here — it is the
deferred record's physical acceptance.

## Review

- Independent Tier-3 cold review (fresh context, contracts + diff only):
  **PASS — no P1, no P2, four P3 notes.** The reviewer independently re-ran
  `productP1VoiceRoute` (86/86), the panel suite (53/53), the integrated-web
  battery (410/411, only the disclosed pre-existing seam) and
  adapter/processor (103/103), verified boundary/grace/budget arithmetic,
  clear-site completeness, race preservation, scope and privacy.
- P3 notes and their disposition: (1) duration-driver frame-window precision —
  evidence wording corrected above; (2) manual-EOT truncated-tail consequence —
  disclosed above and routed; (3) `actual_processing` wiring previously
  untested — a diagnostics assertion was added to the deterministic
  regression; the `live_voice_capture_rotation` warn line remains
  source-level only; (4) `last_rotation`/`actual_processing` are deliberately
  retained last-known diagnostics across resets (correlate via
  `operation_generation`), and worst-case retained-audio memory is bounded at
  3,075 frames by the absolute ceiling.
