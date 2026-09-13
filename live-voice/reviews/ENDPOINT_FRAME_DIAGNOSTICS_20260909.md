# Endpoint frame diagnostic follow-up — 2026-09-09

Baseline: `3930d29f31123ec6469a403594728763cf492c7a` on
`codex/demo-live-voice-20260909`. User requests additional diagnostics before
repeating the three recorded questions to locate the approximately 300 ms beyond
the configured 450 ms endpoint silence.

## Owned boundary and acceptance

Tier 1, passive local observations. Own browser capture/enqueue/socket-send
timings, Gateway Native input delivery, Provider socket append timings and
existing WebSocket heartbeat RTT observations. Retain only bounded scalar facts,
sample positions and existing identities. Browser endpoint snapshots retain the
last 100 frames per capture, at most four captures. Backend per-frame records use
the existing bounded asynchronous diagnostic sink. Diagnostic failure cannot
reject audio, change authority, add media sends or alter lifecycle decisions.

Keep the existing model, VAD 450 ms, audio processing, project and business path.
No VAD comparison experiment, raw audio logging, new Provider requests, network
configuration changes or remote updates in this batch. RTT is a same-connection
heartbeat observation, not a measurement of one-way audio delivery or Provider
computation. Missing heartbeat evidence remains unavailable.

Checks: bounded retention and exact capture isolation, scalar privacy, timestamp
ordering, failed-send non-completion, diagnostic failure isolation, real local
WebSocket heartbeat observation, affected browser/media and Python regressions,
frontend build, complete scoped diff review and controlled deployment. The user
owns the subsequent microphone/recording run; this batch makes no new latency
or physical acceptance claim.

## Verification and deployment

Final Python boundary checks: 208 passed for Dedicated Media registration and
Realtime session; 24 passed for Native transport, speech socket and diagnostic
sink. This includes a real loopback WebSocket ping/pong, unavailable RTT before
the first pong, unsolicited-pong rejection, all 55 consecutive append identities,
failed append non-completion, sink privacy and original send timestamps.

Browser diagnostics: 13 passed. Browser audio IO/worklet: 138 passed. Dedicated
media leaf: 33 passed. Typecheck and `npm run build:live-voice` passed. The wider integrated-web comparison
returned 705 passed, 11 failed, 1 skipped. All 11 failures reproduce using the
unchanged frontend from baseline HEAD: one obsolete product-entry source
assertion and ten mounted Task UI fixtures. That isolated extraction also lacked
the repository-level EOT JSON fixture, an additional baseline setup failure;
the fixture was restored and its isolated check passed as well. These existing Task/entry fixtures
are excluded from this passive diagnostic change; no full-suite pass is claimed.

The complete scoped diff was reviewed for original timestamp placement, strict
capture identity, frame-count bounds, unchanged audio bytes and scheduling,
absence of extra network messages, and diagnostic failure isolation. Browser
window publication is deferred until the EOT handler returns. Backend writes
remain on the existing bounded asynchronous sink; its dropped-record counter
must be checked on the new run. Build/deployment output and exact launched HEAD
are retained locally in `logs/endpoint-build.txt`, `logs/endpoint-deploy.txt` and
`logs/live_voice_runtime_contract.json`. The microphone recheck remains with the
user; no new first-sound conclusion is recorded here.

## Reading the new evidence

- Browser `endpoint_input_frame`: last 100 frame sequences at each EOT, including
  capture callback, AudioContext/sample position, enqueue and socket-send return.
  `endpoint_received_ms` identifies the snapshot boundary; the outer event time
  is later journal publication, not capture. First/last 10 ms energy windows are
  dBFS observations; null means no finite positive power, not classified speech.
- Gateway `native_input_delivery`: every frame's accept-entry, enqueue,
  offer-start and offer-return times plus 24 kHz input sample range. The exact
  `source_event_id` joins the Provider append. These are perf-counter timestamps
  on the Gateway diagnostic clock, not Provider receipt acknowledgements.
- `native_transport_timeline` / `audio_append_sent`: every successful append's
  lock-attempt, lock-acquired, socket-start and socket-return times. Failed sends
  retain the existing failure event and never gain this success record.
- `socket_keepalive_rtt`: the existing connection's matched ping/pong RTT and
  observation time; append observations also include its age. No diagnostic ping
  is added. Unsupported or not-yet-observed heartbeats remain null.

Compare durations only within each clock. Match browser/Gateway input by exact
capture generation and frame sequence, and Gateway/socket by source event ID.
The Provider end position maps to the frame ending at or after that audio sample
position. Socket return to `speech_stopped` receipt includes remaining upload,
Provider processing and event return; subtracting RTT does not isolate model
computation. A gap or drop remains missing evidence rather than zero latency.

For the next three-question recording, refresh the page to load the new bundle,
start listening, wait about 25 seconds for the existing heartbeat, then repeat
the same question three times with each answer complete before the next turn.
Export diagnostics after the third answer. Keep the prior separate microphone
and desktop-audio recording tracks and the same 450 ms VAD setting.
