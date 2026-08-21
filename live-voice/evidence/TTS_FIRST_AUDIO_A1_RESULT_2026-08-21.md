# TTS first-audio A1 causal result — 2026-08-21

## Result

**A1 PASS — `SUCCESSOR_ACK_DECOUPLING_ELIGIBLE`.** On the current sequential
P1 route, the successor microphone ACK is on the critical path before the TTS
downlink opens. Controlled 250 and 750 ms ACK delays were transferred almost
one-for-one into presentation-to-first-source latency; 1100 ms reproduced the
bounded current failure before any downlink or playout receipt.

This result authorizes the candidate defined by the
[cold reconciliation](../reviews/TTS_CAPTURE_RECONCILIATION_REVIEW_2026-08-21.md).
It is component-level causal evidence, not a physical Browser, audible-output,
Provider, network or end-to-end product claim.

## Exact source and method

- Source: `2651b0dd8ae594f342fe3262ca1b89d44456f2e8`, clean at run start.
- Runner SHA-256:
  `0827df29fec1294d02086cf727bfb4b3ecacdd8e21be5b8adbe9f5c7d90dc5b6`.
- Runtime: Node `v24.18.0`.
- Run ID: `tts-a1-20260821T093944Z-2651b0dd8a`.
- Raw report: private, external to Git, exclusive mode `0600`, schema
  `live-voice.tts-first-audio-causal-report.v0`.
- Population: 5 attempts at each injected successor-ACK delay: 0, 250, 750 and
  1100 ms; 20 total attempts.

The runner drove the real `ProductP1VoiceRouteOwner` with deterministic,
content-free Speech/media/audio fakes. Each attempt performed one valid initial
capture and recognition, bound one exact foreground response, requested one
single-frame TTS result, and varied only the first Gateway ACK delay of the
successor capture. It invoked no Browser, microphone, speaker, network,
Provider, Agent, Tool or Task.

## Timing result

All values are milliseconds from the TTS request boundary. Percentiles use
nearest-rank over the five attempts.

| Successor ACK delay | Outcome | p50 downlink opened | p50 first source scheduled | p95 first source scheduled | p50 playout receipt |
|---:|---:|---:|---:|---:|---:|
| 0 | 5 completed | 5.869 | 6.746 | 10.344 | 17.473 |
| 250 | 5 completed | 255.215 | 255.597 | 256.608 | 266.612 |
| 750 | 5 completed | 756.054 | 756.542 | 756.958 | 767.439 |
| 1100 | 5 failed | — | — | — | — |

Against the 0 ms population:

- the 250 ms population added 248.851 ms to p50 first-source scheduling;
- the 750 ms population added 749.796 ms to p50 first-source scheduling;
- both exceed the required 200 ms and 15% materiality thresholds;
- every 1100 ms attempt failed with
  `AUDIO_CAPTURE_MEDIA_NOT_ACKNOWLEDGED`, with no downlink opened, first source
  scheduled or playout receipt accepted.

The report classified the inspected product as `legacy_sequential`: in every
successful delayed attempt, downlink open occurred only after the successor
ACK. This is direct evidence that the wait is not hidden by other current work.

## Safety and interpretation

The report recorded zero Agent, Tool, Task and history effects. Failed attempts
were excluded from numeric comparison summaries but retained in the population
denominator with their stable reason. The runner and report contain no audio,
transcript, prompt, credential, device identifier or private exception text.

The eligible product candidate is the atomic pair:

1. start authoritative TTS downlink concurrently with bounded successor
   capture preparation; and
2. keep `duplex_media_observed` as a diagnostic boolean rather than a success
   precondition for an otherwise exact completed playout receipt.

Capture-lease rotation from `6cd8840d5` remains excluded. Any later claim about
audible gain, real WebAudio scheduling, device behavior or network behavior
still requires the deferred physical Browser confirmation.
