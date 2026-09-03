# C019 B/long recovery smoke — 2026-09-03

## Verdict

**ONE FUNCTIONAL PASS AFTER ONE FAILURE — C019 TASK 1 REMAINS OPEN.**

The second clean B/long attempt completed all five ordered audio units with no
Browser failure, no streaming-TTS fallback, no dropped L0 record and no
operator-observed audible gap, stutter or truncation. The immediately preceding
attempt on the same behavioral source failed after unit 3 promotion with
`MEDIA_STREAMING_TTS_TEXT_OR_RETRY`. The only source difference between the two
attempts was content-free queue-pressure diagnostic formatting. Therefore the
PASS proves that the long journey can complete, but it does not establish that
the intermittent race is repaired or that the earlier failure was caused by
the pause-handshake change.

This smoke grants no Task-1 acceptance, percentile or Task-2 WebAudio-lead
credit.

## Source and fixed environment

| Attempt | JiuwenSwarm source | Behavioral difference | Result |
|---|---|---|---|
| B/long retry 1 | `ae5f28faa2671d46668e6cab3f86398f3330e795` | Shared absolute ordinary-pause budget | FAIL: `STREAMING_SPEECH_EVENT_QUEUE_EXHAUSTED` surfaced as `MEDIA_STREAMING_TTS_TEXT_OR_RETRY` |
| B/long retry 2 | `4921d0bc688dfb4224170360a2e5fa6de4bf441b` | Same behavior; queue-pressure phase made visible in the log message | PASS: 5/5 units completed |

Both attempts retained the Task-1 configuration: Agent-Core
`94e10cb6102c36fe78a64547957c0def97299273`, Windows Chrome
`151.0.7922.174`, WSL2/Python 3.11, physical microphone, OpenAI
`gpt-4o-mini-transcribe-2025-12-15`, OpenAI
`gpt-4o-mini-tts-2025-12-15` with `marin`, DeepSeek
`deepseek-v4-flash` with reasoning disabled, server VAD at 1,200 ms and fixed
WebAudio startup lead at 1,000 ms. The exact prompt was:

> Please introduce London in eight detailed points, with at least two
> sentences for each point, then give a summary.

Each attempt used a clean detached source, fresh backend run, isolated private
data/P3 database and a fresh Browser Session/correlation. Browser L0 was cleared
and configured before speech, then copied after failure or final playout.

## Retry 1 failure evidence

The first retry retained 41 Browser records with zero drops. Units 0–2
completed; unit 3 attached, buffered, was promoted and received its first
Browser frame. It then failed before `webaudio_actually_started`:

| Boundary | Browser monotonic observation |
|---|---:|
| Unit 3 first frame buffered | `124,053.9 ms` |
| Unit 2 playout completed | `189,108.2 ms` |
| Unit 3 promoted | `189,484.8 ms` |
| Unit 3 first frame scheduled | `189,485.4 ms` |
| Browser failure | `189,845.8 ms` |

The Gateway classified the owning failure as
`STREAMING_SPEECH_EVENT_QUEUE_EXHAUSTED`, with
`first_audio_emitted=true` and `text_or_retry`. The old formatter did not render
the recorded `source_state`, so that retained run cannot distinguish pause
handshake, queue admission and resume-watermark expiry. A proposed follow-up
test was rejected and removed because it also passed after the hypothesized
production fix was removed; it therefore did not prove the physical race.

## Retry 2 functional and latency evidence

The second retry retained 55 Browser records with zero drops. All five units
started and completed in order. No synthesis queue-pressure/fallback event was
emitted. The operator heard continuous complete playback with **no audible
inter-unit gap, stutter or truncation**.

All values below are measured on the Browser monotonic clock:

| Boundary | Value |
|---|---:|
| EOT → first TTS request | `2,707.2 ms` |
| First TTS request → first Browser frame | `1,021.0 ms` |
| First frame → WebAudio actually started | `682.0 ms` |
| **EOT → WebAudio actually started (digital TTFA)** | **`4,410.2 ms`** |
| EOT → final unit playout completed | `250,746.0 ms` |

The digital `unit_playout_completed` → next `unit_playout_started` intervals
were:

| Transition | Digital milestone interval |
|---|---:|
| Unit 0 → 1 | `4,540.5 ms` |
| Unit 1 → 2 | `1,347.5 ms` |
| Unit 2 → 3 | `1,349.7 ms` |
| Unit 3 → 4 | `1,406.4 ms` |

These intervals are **not acoustic-silence measurements**. In this run they did
not correspond to an audible gap. They include Browser lifecycle/scheduling
semantics and cannot be used alone as a proxy for perceived continuity.

During the long playout, the backend logged repeated streaming-recognition
Provider degradation at roughly 30-second intervals. It did not interrupt the
successful TTS playback, but it remains a lifecycle residual to correlate with
successor capture/listening behavior before Task 1 can pass.

## Consequence and next gate

1. Preserve both retry outcomes; do not replace the failure with the later
   success.
2. The B/long path is physically possible and produced a complete continuous
   response, but one pass after one failure is insufficient stability evidence.
3. Keep the queue-pressure phase diagnostic for a subsequent failure. Do not
   implement a timeout fix without a deterministic RED that distinguishes the
   exact expired phase.
4. Continue Task 1 with repeated B/long stability and the Stop/interruption/Exit
   lifecycle matrix. Task 2 remains blocked.

## Retained private evidence

- Failed retry root:
  `/home/renan/openJiuwen-ai/live-voice-latency-runs/c019-task1-aba-20260903T132456Z`.
- Failed Browser snapshot SHA-256:
  `a2bb72f7764d2173578b6c645d50ea7d360a8943961d14f3727d785da676b691`.
- Passing retry root:
  `/home/renan/openJiuwen-ai/live-voice-latency-runs/c019-task1-aba-20260903T134232Z`.
- Passing run ID:
  `lv-diag-wsl-en-v1-20260903T134248Z-4921d0bc6`.
- Passing gate manifest SHA-256:
  `d1d72f2bd04c874bd0b450259ada59fc5914ea762af1ed09e4ab6c2bebc29a70`.
- Passing Browser snapshot SHA-256:
  `410ab3b2f0833ee47902aebc197187b09210ddda4564cc1a04f84e850412d2c3`.
- Passing `run.json` SHA-256:
  `b55f674fd6e00ba471e905711aca1f2679904c170f72da949ecd95a83c7a0d9b`.

Raw logs and Browser snapshots remain private and mode-restricted outside Git.
