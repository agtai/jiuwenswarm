# P1/P2-T2-L2A: successor-capture ACK decoupling — source and automated evidence

## Scope and disposition

- Source baseline: branch `hx/0819_live_voice_p1p2` at
  `6cd8840d586391e3f5a19a7ad32cadf641714c9a`.
- Packet: `T2-L2A` under the P1/P2 media and conversation-runtime route in
  [STATUS](../STATUS.md).
- This record grants **source and affected automated credit only**. The
  originally observed Chrome run remains a physical FAIL: Agent text was
  correct, the UI claimed playback, no sound was heard, and the route reported
  `AUDIO_CAPTURE_MEDIA_NOT_ACKNOWLEDGED`. A later real microphone/speaker run
  must prove short and long TTS audibility, post-playout listening, real
  barge-in and Exit cleanup before physical or product-readiness PASS can be
  claimed.
- Owned product surfaces: `productP1VoiceRoute.ts`, the Integrated Web state
  projection and visible interruption-degradation label, plus directly
  affected tests. No backend, Gateway, provider, model, billing, protocol,
  schema, media-adapter or P3 Task/Agent policy file changed.

## Reproduced mechanism

The prior route started a successor microphone capture before opening the
authoritative streaming-TTS downlink and synchronously waited for one real
captured frame to drain through the Gateway ACK window. If that ACK was not
observed within one second, `playAgentText()` failed before the downlink WebSocket
was created. The error's `AUDIO_CAPTURE` prefix therefore described the
microphone uplink used for playback-time interruption, not TTS audio or the
speaker. The UI had already published `playing`, so its state was also ahead of
physical browser playout.

This gate and its one-second timeout are identical in `7814c1473` and
`6cd8840d5`; the T1 changes in `6cd8840d5` affect later 30-second capture
rotation and local-activity decay. The observed first-frame readiness failure
occurs before that rotation logic, so this record makes no regression claim
against the T1 commit.

## Repaired contract

1. Streaming TTS starts the successor capture and authoritative downlink
   concurrently. The downlink no longer waits for successor readiness.
2. The initial user capture contract is unchanged: it still requires a real
   first-frame Gateway ACK and fails closed on no frame, no ACK, route loss or
   device failure.
3. A successor capture that becomes ready within the bounded window retains
   normal playback-time barge-in. A no-frame, no-ACK or startup-device failure
   stops the exact local capture, closes its uplink, revokes its exact media
   authority and degrades only interruption for the current response. The
   authoritative audio and rendered receipt are preserved, and the Integrated
   Web loop can start a fresh listening capture afterward.
4. `playing` is published only after the browser audio adapter accepts and
   schedules the first source. Completed Agent text, a TTS descriptor or
   capture preparation alone cannot produce the state.
5. Content-free diagnostics expose `pending`, `ready` or `degraded` successor
   readiness, a stable reason and monotonic elapsed milliseconds. The visible
   UI explains that interruption is unavailable for the response while audio
   continues and listening will restart. No audio, transcript, credential,
   ticket or device identity is logged.
6. Existing operation-generation, exact response, media authority and stale
   callback fences remain authoritative. Degradation cannot resubmit Agent,
   Tool or Task work, duplicate a playout receipt, replay old audio or allow a
   late ACK to revive the closed successor.

## D-032 scenario and risk evidence

- **P/T — intended path:** immediate ACK and a 500 ms delayed ACK both enable
  successor capture; the response schedules and renders exactly once.
- **B/T — boundary:** a real frame without ACK remains bounded by the existing
  one-second readiness window; a 1.1 s ACK is late, cannot cancel scheduled TTS
  and has zero later status, network-call or audio-source effects. Same-deadline
  event ordering remains owned by the existing bounded `Date.now() < deadline`
  contract and is not represented by a flaky wall-clock equality test.
- **N/F — negative/failure:** no real successor frame, permanent no ACK and a
  starting-window mute degrade interruption while preserving the exact audio
  response and receipt. The corresponding initial-capture no-ACK oracle still
  fails closed.
- **S/K — security/state isolation:** exact failed successor authority is
  revoked; no raw media or private identifiers enter diagnostics; late ACK,
  close, barge-in and Session-switch callbacks cannot mutate a successor
  generation.
- **R/X — recovery/integration:** a fresh capture after degraded successor
  readiness reaches `capturing` with no repeated synthesis, recognition,
  Agent, Tool or Task effect. Mounted barge-in and stale-TTS Session-switch
  journeys pass. A real microphone/speaker `X` run is deliberately not claimed.

## Automated evidence (current repaired source)

Frontend, from `jiuwenswarm/channels/web/frontend`:

- `npm run test:live-voice-integrated-web`: strict target compilation,
  bundling and 15 suites — **413 passed, 1 failed of 414**. The only failure is
  the unchanged, pre-existing and separately recorded seam
  `mounted Exit and immediate re-enable recover after old unified success or
  rejection without replaying TTS`; the source baseline was already 410/411
  with that same single failure. It is excluded from this packet and receives
  no repair credit here.
- `npm run test:live-voice-browser-audio-io`: audio adapter and capture
  processor — **103 passed, 0 failed**.
- `npx tsc --noEmit`: full frontend TypeScript check — **PASS**.

New or changed deterministic oracles cover truthful first-source `playing`,
500 ms delayed ACK, permanent no ACK, 1.1 s stale ACK, no-frame and muted
successor degradation, post-degradation listening restart, long-answer
downlink concurrency, mounted barge-in and stale predecessor TTS after a
Session switch. Existing runtime post-readiness capture faults continue to
fail closed and stop playout; existing close, output-loss, page-hide,
render-clock, receipt and generation-fence tests pass in the same affected
battery.

## Review and remaining acceptance

- Structured Tier-3 self-review: source ownership, exact cleanup, failure
  reason propagation, truthful UI state, privacy, delayed/stale callbacks and
  zero Agent/Tool/Task side effects were inspected against the diff and the
  affected tests. No broader protocol or product-policy change was found.
- An independent Tier-3 reviewer was not used in this Session; no independent
  review credit is claimed.
- Physical acceptance remains open. Required next evidence is at least five
  real Chrome turns with short and long audible TTS, automatic listening
  restart, a real successful barge-in, the truthful no-barge-in degradation
  path if induced, and Exit closure of capture, playout, WebSockets, timers and
  media leases.
