# OpenAI Realtime Native ordinary-Chrome evidence — 2026-08-29

## Disposition

Scope marker `306894062` passes the ordinary installed-Chrome, prerecorded
digital foreground gate on implementation commit
`2026e02fbfcc03164e51d953731f04c0eac41938`.

The selected interaction engine was `openai-realtime-native` and the Provider
model was `gpt-realtime-2.1-mini`. The tested product path replaced foreground
Cascade STT/EOT/TTS/barge-in ownership with one continuous OpenAI Realtime
speech-to-speech session. JiuwenSwarm retained all Agent, Tool and Task
authority. No background Task journey was invoked.

This is not physical-device or Production evidence. The input was a fixed
prerecorded corpus injected into the real Browser capture stream in ordinary
installed Chrome. It does not prove microphone selection, acoustic echo
cancellation, room acoustics, loudspeaker audibility or human acceptance.

## Real-browser result

| Gate | Result |
| --- | ---: |
| Non-counted warm-up | complete |
| First-audio scenarios | 20/20 |
| Barge-in scenarios | 20/20 |
| Browser-complete attempts | 40/40 |
| Browser dropped records | 0 |
| Failed attempts | 0 |

Every first-audio attempt retained six correlated Browser records and every
barge-in attempt retained seven. The completed run contained no occurrence of
the targeted failure classes `ACTION_LEDGER_FULL`,
`NATIVE_AUDIO_BATCH_INVALID`, `NATIVE_TRANSCRIPT_INVALID`,
`REALTIME_PROVIDER_TIMEOUT`, `AUDIO_CAPTURE_MEDIA_NOT_ACKNOWLEDGED`,
`live_voice_native_media_task_failed`,
`live_voice_native_uplink_consumer_failed`, or any `MEDIA_NATIVE_*` terminal
failure. There was no traceback.

The validation used isolated data and ports. After cleanup, all validation
ports were closed. The pre-existing W3 listeners remained unchanged throughout
and after the run: port `18092` stayed on PID `21960`, while ports `19000` and
`19001` stayed on PID `14308`. The foreground validation did not create,
cancel, retry, inspect, or otherwise mutate a background Task.

## First-audio latency

The exact metric is Browser `browser_eot_receipt` to
`webaudio_actually_started`, using one Browser monotonic clock and the same
nearest-rank percentile calculation as the accepted Cascade warm baseline.

| Path | n | p50 | p95 | min | max |
| --- | ---: | ---: | ---: | ---: | ---: |
| OpenAI Realtime Native | 20 | 2320.633 ms | 2902.033 ms | 1959.133 ms | 3252.767 ms |
| Cascade accepted warm baseline | 20 | 4834.362 ms | 5603.215 ms | — | — |
| Realtime minus Cascade | — | -2513.729 ms | -2701.182 ms | — | — |
| Reduction | — | 52.00% | 48.21% | — | — |

`webaudio_actually_started` is Browser render-start evidence, not a claim about
the instant sound became physically audible.

## Reproduced defects repaired before the passing run

- Browser downlink ownership and ACK backpressure for an initial Provider
  burst, with bounded content-free consumer diagnostics.
- Continuous Native speech-start/EOT cycles without arming Cascade STT.
- Faster-than-playout Provider delivery through a fixed reservoir, bounded
  Runtime audio batches and STOP priority fencing.
- Ordered response/item/content-index batch boundaries and multi-item,
  interleaved Provider audio accounting.
- Long-session Runtime and Session replay-ledger working-set retirement.
- Provider receive-idle polling without treating healthy silence as a terminal
  timeout.
- Continuous Browser uplink compaction of the exact Gateway-ACKed prefix.
- Realtime-only action capacity aligned to the Engine's existing 1024-action
  bound; Cascade remains on its previous capacity.
- Provider transcript CRLF/CR/LF canonicalized to spaces before the unchanged
  strict Native audit contract.

## Automation and build

The exact implementation tree subsequently committed unchanged passed:

- affected backend/contract/Runtime/Gateway suite: `424 passed`;
- dedicated media route suite: `78 passed`;
- frontend Native interaction suite: `106/106`;
- frontend integrated Web suite: `494/494`;
- Browser Gateway Media suite: `40/40`;
- Browser Dedicated Media suite: `30/30`;
- changed Realtime Python Ruff check: pass;
- changed Python compile check: pass;
- `build:live-voice`: pass (`4650` modules transformed);
- `git diff --check`: pass.

The build retained the repository's existing duplicate localization-key,
dynamic/static import and large-chunk warnings; none originated in this
Realtime repair batch.

## Review and remaining gates

A cold complete-diff self-review found `C0/I0/M0`: no new Agent/Tool/Task
authority, no background/W3 change, no Cascade semantic change, no silent
fallback, no unbounded buffer, and no credential, raw-audio or transcript
persistence. The repository-required independent review of this post-D-100
repair delta has not yet run, so release-level module closure remains partial.
Physical microphone/headset and human acoustic acceptance also remain
`NOT_RUN`; neither is required for the prerecorded digital result above.
