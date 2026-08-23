# P1/P2-T2 post-playout receipt decoupling — 2026-08-20

## Pre-implementation scope checkpoint

- **Observed source:** `874cf327c27f00dc5cabf514c1dac76840395706`.
- **Observed product failure:** one real Chrome microphone/Agent/TTS turn spoke
  the complete answer, then the product reported
  `PRODUCT_TTS_PLAYBACK_FAILED`. The exact runtime sequence opened the
  successor uplink, completed the short TTS downlink, rendered the audible
  answer, then entered two-authority cleanup and emitted
  `STREAMING_SPEECH_CANCEL_UNACKNOWLEDGED`.
- **Intended behaviour:** an authoritative playout receipt proves that the
  exact authorized TTS media completed transport and browser rendering.
  `duplex_media_observed` separately reports whether the Gateway observed a
  real overlapping successor uplink. A missing or late successor frame may
  degrade interruption/listening, but must not retroactively convert completed
  audible TTS into a playback failure.
- **Protocol checkpoint:** this is a Tier-3 authority/protocol semantic change.
  It separates downlink completion from the existing duplex observation
  boolean; it does not add a payload field, weaken initial-capture ACK
  readiness, or accept an unbound/malformed/stale receipt.
- **Owned source/tests:**
  `gateway/live_voice/dedicated_media_registration.py`, formal P1 receipt
  validation in `productP1VoiceRoute.ts`, the Web error-reason projection only
  if required to preserve an existing Gateway reason, and their focused
  Python/TypeScript tests.
- **Explicit exclusions:** Agent, Tool, Task and history semantics; P2/P3
  schemas; Provider/model/voice/billing configuration; capture-duration or
  rotation policy; raw audio/transcript/credential/private-device telemetry;
  physical PASS before a later user run; remote refs.

## Acceptance and D-032 matrix

- `P/X`: a short downlink that completes before the successor's first accepted
  frame retains an accepted browser-render receipt and no visible TTS failure;
  physical post-playout listening remains user acceptance.
- `N/B/I`: malformed, wrong-binding, incomplete, forged and stale receipts
  remain rejected with zero Agent/Tool/Task/audio/history effects.
- `S/T/C`: the downlink binds the exact live successor candidate at start;
  missing, late and reordered successor media cannot alter downlink content or
  replay presentation.
- `R/F`: no-duplex reports `duplex_media_observed=false`; cleanup remains
  bounded, and later exact listening restart does not replay TTS.
- `K`: existing true-duplex receipts remain byte-for-byte compatible apart from
  deriving the existing boolean from the recorded observation.

## Evidence log

### Root cause

`mark_downlink_started()` bound the TTS downlink to the successor microphone
route, and `complete_downlink()` then required that successor route to have
accepted a real frame before treating the downlink as complete. Short TTS can
finish transport before the first successor microphone frame. The browser had
already rendered the full audio, but `acknowledge_playout()` rejected its exact
receipt because `overlap_observed` was false. The Web RPC client then discarded
the top-level Gateway error code when the error payload had no nested reason,
leaving the generic `PRODUCT_TTS_PLAYBACK_FAILED` projection.

### Minimal reproduction and green result

Old-source Python repro:

```text
.venv\Scripts\python.exe -m pytest tests/unit_tests/gateway/test_dedicated_media_registration.py -q -k "synthesis_downlink_receipt_reports_early_duplex_without_rejecting_playout"
2 failed, 1 passed
```

The no-frame and post-downlink-frame cases failed because transport completion
incorrectly returned false. The real-frame-before-completion case passed.

Old-source browser-route repro:

```text
node --test --test-name-pattern "formal P1 keeps completed TTS when the Gateway reports no early duplex media" tests/productP1VoiceRoute.test.mjs
1 failed: media playout receipt binding mismatch
```

After the repair:

```text
.venv\Scripts\python.exe -m pytest tests/unit_tests/gateway/test_dedicated_media_registration.py -q --no-cov -k "synthesis_downlink_receipt_reports_early_duplex_without_rejecting_playout"
3 passed, 41 deselected

node --test --test-name-pattern "formal P1 keeps completed TTS when the Gateway reports no early duplex media" tests/productP1VoiceRoute.test.mjs
1 passed
```

The browser repro delays the successor ACK by 500 ms, returns
`duplex_media_observed=false`, proves one scheduled audio source and one exact
playout receipt, and asserts zero Agent/Tool/Task/history calls.

### Repair

- Gateway downlink completion now depends on the exact authorized media
  transport and its bounded frame/queue facts, not on early successor uplink
  activity.
- The existing receipt field truthfully returns the recorded boolean
  `duplex_media_observed`; missing, malformed, incomplete and unbound downlinks
  remain rejected.
- Formal P1 validates that the field is a closed boolean without converting
  false into a retroactive playback failure.
- Web RPC errors retain a direct top-level Gateway code when no more-specific
  nested reason exists, while nested product reasons retain priority.

### Affected verification

```text
test_dedicated_media_registration.py                 44 passed
test_product_streaming_synthesis.py                  14 passed
test_live_voice_speech_rpc.py                        13 passed
test_streaming_speech_route.py                       52 passed
test_openai_streaming_speech.py                      71 passed
npm run test:live-voice-browser-audio-io            103 passed
npx tsc --noEmit                                     passed
npm run test:live-voice-integrated-web               414 passed, 1 failed
focused Web reason extraction                        1 passed
ruff check (changed Python source/test)               passed
git diff --check                                     passed
```

The sole Integrated Web failure is the unchanged, pre-existing
`mounted Exit and immediate re-enable recover after old unified success or
rejection without replaying TTS` case; it was the sole failure before this
repair as well and is excluded from this packet.

### Review and remaining acceptance

A cold line-by-line self-review rechecked the receipt identity, origin,
activation lifetime, content hash, exact frame counts, bounded queue facts,
idempotency/conflict path and zero-business-effect assertion. Independent
subagent review was unavailable under the active execution policy; affected
automated suites and explicit negative bindings provide the substitute review
evidence. Physical Chrome audibility and automatic post-playout listening are
still open and must be validated after the committed source is rebuilt and the
local runtime is restarted.
