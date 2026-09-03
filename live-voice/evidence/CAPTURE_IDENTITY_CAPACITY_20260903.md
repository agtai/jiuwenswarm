# Cumulative capture identity capacity — 2026-09-03

Status: OPEN; diagnosis only, not repaired.
Source: `2ab12a08889cb72dabcd41ce5e9d8aaaa0f80ae8`; deployed product source
`c4987f0286`. Session: `web_1a0693eab4e_9a9185af6dbe`.

## Observed evidence

The private `logs/swarm-20260903-224629.log` contains exactly 64 distinct
`gateway_frame_accepted` scope hashes before the first recognition-open failure
at 23:48:30.567 local time. Six opens fail through 23:48:36.193, each reporting
`STREAMING_SPEECH_PROVIDER_PROTOCOL` at approximately zero milliseconds, followed
by `EOT_PROVIDER_FAILED` and media socket closure. One failing retry accepts a
first audio frame before closing. The browser reports
`AUDIO_CAPTURE_MEDIA_ROUTE_CLOSED` before capture readiness.

`StreamingSpeechConformance` defaults `max_identity_tombstones` to 64 and retains
recognition identities for its lifetime. Terminal reaping releases active
streams but not their identity ledger. The shared OpenAI speech adapter uses
these defaults; each new uplink receives a fresh random `media_session_id`.

A local, network-free diagnostic used the existing test capability/ref helpers
with the production conformance class, sequentially starting, closing and
reaping 64 unique recognition streams. Observed output:

```text
completed_streams=64 active_recognition=0 retained_recognition=0 retained_identity_tombstones=64
stream_65_reason=RECOGNITION_IDENTITY_CAPACITY_EXHAUSTED
reported_degradation=STREAMING_SPEECH_PROVIDER_PROTOCOL
```

The adapter maps that exact local capacity error to the generic protocol reason.
Cascade's negotiated speech-boundary failure closes the media route; the browser
then reports startup closure. The production log drops the original typed cause,
so capacity exhaustion is strongly supported by the exact count, source and
reproduction, not a direct inspection of the live process ledger.

## Consequence and required repair boundary

Normal listening rotation, interruption and reconnection can exhaust the shared
process lifetime budget; the limit does not mean 64 utterances or 64 concurrent
connections. A process restart is only temporary mitigation. Increasing the
constant merely delays recurrence.

A separate lifecycle/identity packet must allow sustained sequential use while
rejecting late/replayed old connections, retaining bounded memory and exact
scope/generation isolation. Preserve the original typed failure in diagnostics.
Acceptance must include more than 64 sequential connections, late/replay rejection
and affected capture recovery. Do not remove identity fencing or clear a live
ledger to manufacture availability. No Provider/account change is implied.
