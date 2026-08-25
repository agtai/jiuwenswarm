# LVL-08 Semantic VAD real-pilot blocker

**Date:** 2026-08-25
**Source:** `latency/semantic-vad-experiment` at
`5038c41c43c0538f49ffdb363bc0b034293e7426`
**Decision:** **CONTROL PRECONDITION BLOCKED; SEMANTIC VAD UNTESTED**

## Scope

The authorized no-Browser pilot was intended to run independent
A1=Server-VAD-1200/B=`semantic_vad auto`/A2=Server-VAD-1200 and later `high`
blocks. Product activation and the 1200 ms fallback were unchanged.

No `high` or formal population ran. No latency, eligibility, default or product
credit follows from this attempt.

## Pre-Provider corrections

Three setup defects were found before any audio Provider attempt:

1. the machine `.env` contains non-shell configuration and could not be sourced
   wholesale; only the four required Speech assignments were loaded;
2. the private readiness artifact used obsolete positional experiment syntax
   and a directory output, while the current CLI requires `--experiment` and
   an absolute JSON file;
3. the historical credited corpus carried `final_voiced_frame` values eight
   samples above the detector in source `5038c41c4`, so the current loader
   rejected it.

The historical corpus was preserved. A separate private reconciled corpus was
created with byte-identical WAVs, a new corpus ID and only four uniformly
adjusted `final_voiced_frame` values:

```text
245288 -> 245280
259688 -> 259680
274088 -> 274080
293288 -> 293280
```

Eight samples at 48 kHz are approximately 0.17 ms. The reconciled manifest
passed the exact source loader and independent read-only review. Its SHA-256 is:

```text
78537d7efe398d8bf39719353b042d8b6409130daea50a3d21a5dda6f9d57508
```

All setup failures occurred before Provider construction/open and consumed no
audio requests.

## First real attempt

Run ID:

```text
lvl08-semauto-pilot-20260825t130700z
```

The runner reached the first `A1_1200` control attempt, opened the Provider and
processed audio. It then emitted:

```text
STREAMING_SPEECH_PROVIDER_PROTOCOL
live_voice_speech_transport_cleanup_incomplete kind=socket reason=caller-cancelled retained_count=0
VAD_EOT_BENCHMARK_FAILED
```

The unknown cleanup outcome caused `run_screening` to fail before report
writing. No JSON attempt/report survived. A separate no-audio Server-VAD
open/close diagnostic completed cleanly, so environment parsing, Provider
factory and basic socket/session admission are not the blocker.

Because `A1_1200` is first in the sequence, no Semantic VAD configuration was
opened. The failure therefore cannot be labelled Semantic VAD incompatibility.
Official OpenAI Realtime documentation currently lists Semantic VAD as a turn
detection option for transcription sessions; this repository run never reached
that boundary.

## Honest boundary and next action

- Server-VAD control audio attempt: failed Provider protocol/cleanup.
- Semantic AUTO: untested.
- Semantic HIGH: not run.
- Timing/headroom: unknown.
- Product default: remains Server VAD 1200 ms.
- Forbidden Agent/Tool/Task/TTS/Browser effects: no product path ran.

Before another Provider population, the runner must write the declared
mode-600 `--output` JSON with a sanitized failed attempt and exact stable reason
even when cleanup is unknown; it must never serialize exception text, Provider
payload or transcript. Then the Server-VAD control must pass on the same
source/corpus. Only that control PASS can reopen AUTO and HIGH timing.

Private diagnostics and corpus review are retained under:

```text
/home/renan/openJiuwen-ai/live-voice-latency-runs/preparation-20260825/
```
