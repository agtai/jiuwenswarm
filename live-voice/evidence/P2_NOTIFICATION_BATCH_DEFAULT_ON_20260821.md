# P2 bounded notification pull default-on evidence — 2026-08-21

## Scope and source

- Accepted feature-on source: `4b405fca119699fa51b3a1189567665fa53ce1f8`.
- Cleanup candidate base: the same source; the cleanup commit containing this
  record removes only the two validation deployment switches and changes no
  Successor-ACK/TTS policy.
- Capability: P2 Realtime Media / Integrated Web notification delivery.
- Risk: Tier 3 because batched authoritative finals cross presentation and TTS
  authorization. The earlier repair validates and authorizes each batch item
  before downstream media effects.
- Exclusions: no Speech Provider/model/billing, protocol maximum, raw-audio,
  Task authority, Successor-ACK/TTS, Exit, VAD, generation interruption or
  fixed-corpus policy change.

## Accepted product behaviour

1. Production Integrated Web constructs its P2 notification owner with batch
   size `16`.
2. The server accepts an explicit canonical integer from `2` through `16`.
3. A client that omits `max_notifications` continues to receive one
   `notification`, preserving the old client protocol.
4. A/B automation injects batch size `1` or `16` into the owner. Deployment
   environment no longer selects the transport mode.
5. The former frontend and backend P2 batch deployment switches are retired.
6. Successor-ACK/TTS has no feature switch and remains default-on.

## Human acceptance

The user accepted the feature-on run after the dedicated-media authorization
repair. Visible task times were:

| Prompt | Accepted observed time |
|---|---:|
| Eight-point Hangzhou answer | `10.65s` |
| Five-point water-cycle answer | `7.05s` |
| City-name-only answer | `2.78s`, `3.14s`, `3.14s` |

All scoped answers produced audible TTS. The earlier
`SPEECH_OPERATION_NOT_AUTHORIZED` recovery failure did not recur.

The small prompt set was not frozen, randomized or large enough for p50/p95.
It proves the accepted default path and the absence of the repaired failure in
that run; it does not prove feature-complete latency or broad product readiness.

## Cleanup verification

- Backend focused compatibility/configuration selection: `5 passed, 163
  deselected`; the two direct batch/legacy cases also pass as `2 passed`.
- Frontend dependency-injected A/B test: `2 passed`; batch sizes `1` and `16`
  retain zero forbidden submit/presentation/barge-in/P3/Agent/Tool/Task/history/
  audio effects in the synthetic benchmark.
- Adjacent Dedicated Media/streaming Speech and Batch Speech/P2 Adapter
  regressions: `113 passed` plus `99 passed`, including batched Agent-final TTS
  authorization and bounded P2 adapter delivery.
- Full Formal Web: `445 passed, 1 failed`. The only failure is the already
  disclosed mounted Exit/immediate-re-enable late-presentation ACK case; it was
  present before this cleanup and is outside the notification default boundary.
- A diagnostic full Registry-file run was `162 passed, 6 failed`. Every failure
  is in the separate P3 test-double/production-authority projection boundary
  (including a missing `_P3Composition._accepting` fixture field); both P2
  notification tests pass in that same run. This is retained for later P3 test
  maintenance and does not widen this cleanup packet.
- Production Live Voice build: PASS.
- Final service startup and no-switch environment verification are recorded in
  the task handoff after the cleanup source is committed and launched.

## Remaining acceptance

- Frozen environment/corpus/sample-size latency p50/p95.
- Mounted Exit/immediate-re-enable recovery.
- Speech interruption while the Agent is still generating.
- Broader device/network/backpressure/reconnect and cumulative product journey.

## Sanitization

No bearer token, Speech credential, raw audio, transcript log, subject identity,
private project content or machine-private environment value is retained here.
