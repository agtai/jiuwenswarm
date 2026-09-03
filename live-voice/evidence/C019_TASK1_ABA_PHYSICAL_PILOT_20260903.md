# C019 Task-1 physical A/B/A pilot — 2026-09-03

## Verdict

**PILOT FAIL — C019 TASK 1 REMAINS OPEN; DO NOT EXPAND THE POPULATION OR START TASK 2.**

The candidate produced earlier first audio for the medium workload and avoided
the reference branch's single-request TTS text limit by emitting multiple audio
units. It did not complete the long workload: the fifth unit started, but its
streaming TTS continuation failed after a governed backpressure pause/resume.
The short workload also had enough A1-to-A2 drift to make its apparent gain
inconclusive. Stop/interruption/Exit physical validation was not run.

This result supersedes neither the earlier clean medium-to-short functional
smoke nor any accepted historical Live Voice evidence. It is a source-bound
pilot result for Hongxing's C019 Task 1.

## Frozen comparison

| Arm | JiuwenSwarm source | C019 | WebAudio lead |
|---|---|---|---:|
| A1 | `fec2bbe2d3c6ed2c658dd7a1df6683cc3e4cafc5` | unavailable/off | `1,000 ms` |
| B | `bc87ab9fa259ff89f0deb0e37aadadd65f35cba4` | enabled | `1,000 ms` |
| A2 | `fec2bbe2d3c6ed2c658dd7a1df6683cc3e4cafc5` | unavailable/off | `1,000 ms` |

All arms used Agent-Core lock
`94e10cb6102c36fe78a64547957c0def97299273`, Windows Chrome
`151.0.7922.174`, WSL2/Python 3.11, physical microphone input, OpenAI
`gpt-4o-mini-transcribe-2025-12-15`, OpenAI
`gpt-4o-mini-tts-2025-12-15` with `marin`, DeepSeek `deepseek-v4-flash`
with reasoning disabled, server VAD at 1,200 ms, and a fixed 1,000-ms startup
lead. Each counted cell used a fresh backend run, private Python environment,
data directory/P3 database, Browser Session and correlation.

## Method and deviations

The operator spoke the exact short, medium and long English prompts from the
accepted packet. Browser L0 was cleared and configured before each attempt,
and its raw JSON snapshot was copied after completion or visible failure. All
primary timing below uses one Browser monotonic clock, beginning at Browser EOT
receipt. Physical observations are reported separately from digital events.

This was a one-sample pilot, not a percentile population. The planned explicit
non-counted spoken warm-up was not run; service startup performed its ordinary
prewarm, but that is not equivalent evidence. Several setup-only A1 `run.json`
files were created before the harness configuration was corrected. They never
started a counted product journey and are excluded. An A1 backend attempt at
`lv-diag-wsl-en-v1-20260903T120020Z-fec2bbe2d` used stale model credentials,
failed prewarm, and is also excluded. Counted physical attempts begin at
`12:06:15Z` below.

A2/long was deliberately not executed after A1/long failed on the exact same
source/configuration. Its expected recurrence is an inference, not a measured
failure, so it is reported as `NOT_EXECUTED`, never as zero or failed latency.
Consequently, the long A/B/A cell is incomplete.

## Functional results

| Workload | A1 | B | A2 |
|---|---|---|---|
| Short | PASS, complete audio | PASS, complete audio | PASS, complete audio |
| Medium | PASS, complete audio | PASS, 5/5 ordered units; operator heard no gap | PASS, complete audio |
| Long | FAIL: `SYNTHESIS_TEXT_LIMIT_EXCEEDED` before TTS | FAIL: 5 units started, 4 completed; fifth continuation unavailable | NOT EXECUTED; same-source A1 failure made it redundant |

Every retained Browser snapshot has zero dropped L0 records. Short and medium
snapshots contain no failure/fallback/underrun/rebuffer outcome. B/long contains
one Browser failure bound to the exact response; it is retained in the
denominator.

## Browser-native latency results

All values are milliseconds. `N/A` means the required terminal milestone did
not occur or that the older reference path did not expose the C019 unit-level
milestone. It never means zero.

### Short

| Boundary | A1 | B | A2 |
|---|---:|---:|---:|
| EOT → first Browser audio frame | `5,777.1` | `4,442.8` | `3,961.0` |
| First frame → WebAudio scheduled | `0.8` | `1.4` | `1.5` |
| WebAudio scheduled → actually started | `629.2` | `679.9` | `661.0` |
| **EOT → WebAudio actually started (TTFA)** | **`6,407.1`** | **`5,124.1`** | **`4,623.5`** |
| EOT → playout completed | `8,204.1` | `6,481.6` | `5,819.5` |

| Comparison | TTFA delta | Completion delta |
|---|---:|---:|
| B − A1 | `−1,283.0` | `−1,722.5` |
| B − A2 | `+500.6` | `+662.1` |
| A2 − A1 drift | `−1,783.6` | `−2,384.6` |

The B-versus-A1 improvement is not causal because the unchanged A2 source was
even faster. Short is **inconclusive under observed drift**.

### Medium

| Boundary | A1 | B | A2 |
|---|---:|---:|---:|
| EOT → first C019 TTS request | `N/A` | `2,999.8` | `N/A` |
| First C019 TTS request → first Browser frame | `N/A` | `1,456.1` | `N/A` |
| EOT → first Browser audio frame | `5,636.9` | `4,455.9` | `5,036.7` |
| First frame → WebAudio scheduled | `1.1` | `2.3` | `1.1` |
| WebAudio scheduled → actually started | `690.5` | `570.4` | `679.9` |
| **EOT → WebAudio actually started (TTFA)** | **`6,328.5`** | **`5,028.6`** | **`5,717.7`** |
| EOT → playout completed | `76,192.6` | `82,992.6` | `63,181.7` |

| Comparison | TTFA delta | Completion delta |
|---|---:|---:|
| B − A1 | `−1,299.9` | `+6,800.0` |
| B − A2 | `−689.1` | `+19,810.9` |
| A2 − A1 drift | `−610.8` | `−13,010.9` |

B reached first audio earlier than both controls, giving a **directional TTFA
gain of 689–1,300 ms** for this sample. Completion was slower, but the generated
response/audio lengths were not normalized, so those completion deltas cannot
be assigned entirely to pipeline overhead.

B's digital `unit_playout_completed` → next `unit_playout_started` intervals
were `1,348.4`, `1,338.7`, `1,361.2`, and `1,426.2 ms` (median `1,354.8 ms`,
maximum `1,426.2 ms`). These are scheduling/lifecycle intervals, not measured
acoustic silence. The operator explicitly reported complete continuous playback
with no audible inter-unit gap or stutter.

### Long

| Boundary | A1 | B | A2 |
|---|---:|---:|---:|
| EOT → first C019 TTS request | `N/A` | `2,563.4` | `N/A` |
| TTS request → first Browser audio frame | `N/A` | `1,134.5` | `N/A` |
| First Browser frame → WebAudio started | `N/A` | `660.1` | `N/A` |
| **EOT → WebAudio actually started (TTFA)** | **`N/A`** | **`4,358.0`** | **`N/A`** |
| EOT → last confirmed unit completion | `N/A` | `203,273.0` | `N/A` |
| EOT → complete response | `N/A` | `N/A` | `N/A` |

A1 generated no TTS/first-frame milestone because its single synthesis request
exceeded the text limit. B successfully generated and began five units, so its
`4,358.0-ms` TTFA remains a valid partial latency measurement. It completed
only units 0–3; unit 4 began at `204,650.3 ms` after EOT and failed roughly
`2,108.4 ms` later. The visible label was `PRODUCT_AGENT_OUTPUT_FAILED`, but
backend correlation proves that label was misleading:

- the Agent emitted a valid `chat.final` after 805 emitted events;
- P2 published five audio presentations plus the authoritative text root;
- the fifth unit was promoted from `prefetch_parked` and began playback;
- after a full queue caused pause, the resume was acknowledged only after the
  current contract's wait;
- the synthesis route then emitted `STREAMING_SPEECH_PROVIDER_UNAVAILABLE`
  with `first_audio_emitted=true` and fell back to text-or-retry;
- Browser L0 recorded `UNAVAILABLE`, 5 started units and 4 completed units.

A second EOT occurred about three seconds after this failure when listening
reopened. It is disclosed as a residual lifecycle symptom and was not counted
as another workload attempt.

## What the pilot establishes

1. C019 can lower medium first-audio time and can start long-form TTS that the
   reference cannot synthesize as one request.
2. Short-form gain is not established; A1/A2 drift is larger than the apparent
   A1-to-B improvement.
3. The candidate is not physically acceptable because its long-form fifth-unit
   continuation fails after backpressure.
4. Digital inter-unit scheduling intervals must not be described as audible
   gaps when physical observation reports continuous playback.
5. Total completion comparisons require response-length/audio-duration
   normalization before they can isolate pipeline overhead.
6. Task 2's 1,000→250-ms WebAudio lead experiment remains blocked. This pilot
   fixed all arms at 1,000 ms and grants it no credit.

## Remaining gate and next action

Do not run the four additional samples per cell yet. First reproduce the B/long
fifth-unit pause/resume failure deterministically without Chrome, preserve the
exact `prefetch_parked → promoted → paused → resumed/terminal` state sequence,
and repair or bound the Provider continuation. Then run one B/long physical
smoke. Only after that passes should Task 1 resume with:

1. a fresh A1/B/A2 pilot or a documented alternative for the reference's
   structurally impossible long cell;
2. repeated short/medium/long samples with normalized output shape;
3. Stop, interruption and Exit during staged and playing audio;
4. zero late audio, late ACK/history, stale revival or reopened-capture damage;
5. actual first-audio plus digital and physically observed inter-unit results.

## Retained evidence

- Root:
  `/home/renan/openJiuwen-ai/live-voice-latency-runs/c019-task1-aba-20260903T114834Z`.
- Manifest SHA-256:
  `7178d9a8a3e9fee67d7c11ad0115dbeb71c7df57976e2a8d8616b41a0812dd05`.
- Counted run IDs:
  - A1 short: `lv-diag-wsl-en-v1-20260903T120615Z-fec2bbe2d`;
  - A1 medium: `lv-diag-wsl-en-v1-20260903T120907Z-fec2bbe2d`;
  - A1 long: `lv-diag-wsl-en-v1-20260903T121143Z-fec2bbe2d`;
  - B short: `lv-diag-wsl-en-v1-20260903T121358Z-bc87ab9fa`;
  - B medium: `lv-diag-wsl-en-v1-20260903T121532Z-bc87ab9fa`;
  - B long: `lv-diag-wsl-en-v1-20260903T121812Z-bc87ab9fa`;
  - A2 short: `lv-diag-wsl-en-v1-20260903T122546Z-fec2bbe2d`;
  - A2 medium: `lv-diag-wsl-en-v1-20260903T122726Z-fec2bbe2d`.
- Browser snapshots are retained mode `0600`; their SHA-256 values are:
  - A1 short `098445f28b565b7a9bde511ed05c63d42c772966db2bfb63fc9ac389d4205e09`;
  - A1 medium `02a721c7f97a98de8c547566d18f0722fdac1a390288d44acbfb67c02329d342`;
  - A1 long `6a374af05e7c609153620cca60e1743e4b1648e1ed2f5db5a22eb427a16aec9a`;
  - B short `d545f603be341b8b2f30204df75a4f9e26b9873285bf319cfd09760ee75e99c3`;
  - B medium `3dad2573d8193917f43b05cc0dc1aadf9da632fe657a7fc0b075faf952f5ae5f`;
  - B long `79f7187ad1c257eac7799c6f54eedd2cc2e0f500884e207d747f42992e7469`;
  - A2 short `39d874d72a1c53760db258b9ac2ae7996046d47c268f05aaade42e21f5314630`;
  - A2 medium `19466ff60ee645b3f015149e777927538fef34bb8ee6d482b54a9f372ca50bae`.
- Outcome/physical-observation sidecars and private full logs remain outside
  Git. They may contain machine-private runtime information and are referenced,
  not copied into this document.
