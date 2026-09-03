# C019 Hongxing Task-1 A/B/A validation packet — 2026-09-03

## Purpose and boundary

This packet converts Hongxing's two requested tasks into two separate physical
experiments. The immediate experiment is Task 1: compare current Hongxing Live
Voice with the C019 candidate and determine whether C019 is correct and where
it changes first-audio, inter-unit wait, and completion latency. Task 2 changes
only WebAudio startup lead and remains blocked until Task 1 passes.

This is a physical Browser evaluation packet, not a broad observability
platform and not permission to merge or push. Root `TESTING.md` remains the
risk/evidence authority and `runbooks/E2E_RUNBOOK.md` remains the environment
and launcher authority.

## Pilot execution update — 2026-09-03

The one-sample A1/B/A2 pilot is complete enough to reject population expansion:
**PILOT FAIL / TASK 1 OPEN**. B/medium showed a directional 689–1,300-ms TTFA
improvement and no operator-observed audible gap, but B/long failed during its
fifth streaming-TTS unit after a backpressure pause/resume. Short was
inconclusive because unchanged-source A1/A2 drift exceeded the apparent gain.
A2/long was not executed after the exact-source A1 long path proved
structurally unable to pass its single-request TTS text limit. The lifecycle
matrix remains open and Task 2 remains blocked. See the
[consolidated physical pilot evidence](../evidence/C019_TASK1_ABA_PHYSICAL_PILOT_20260903.md).

### B/long recovery update

Two later clean B/long retries preserved the failed pilot and tested the
Gateway pause-pressure repair independently. The first retry still failed after
unit 3 promotion with `STREAMING_SPEECH_EVENT_QUEUE_EXHAUSTED`. The second,
whose only additional source change exposed the timeout phase in ordinary log
formatting, completed 5/5 ordered units with zero Browser L0 drops and no
operator-observed audible gap, stutter or truncation. Its digital TTFA was
`4,410.2 ms`; digital completion-to-next-start intervals were
`4,540.5 / 1,347.5 / 1,349.7 / 1,406.4 ms`, but these did not represent audible
silence in the physical observation. One PASS after one FAIL is not stability
or causal-fix evidence. Task 1 remains open and Task 2 remains blocked. See the
[B/long recovery smoke](../evidence/C019_B_LONG_RECOVERY_SMOKE_20260903.md).

Subsequent Stop, Exit, immediate re-enable and spoken-barge checks established
fast local fencing and zero observed late audio/unpresented-tail ACK, but also
exposed visible expected-close misclassification. A capacity-eight deterministic
reproduction then confirmed the intermittent post-PARK deadline defect that the
older capacity-one test could not reach. The cumulative source, timing,
lifecycle, artifact and non-claim summary is in the
[Task-1 physical validation update](../evidence/C019_TASK1_PHYSICAL_VALIDATION_UPDATE_20260903.md).

## Hongxing Task assessment

### Task 1 — Complete C019 physical validation

| Requested outcome | Current evidence | Status before A/B/A |
|---|---|---|
| Identify and fix `MEDIA_TRANSPORT_CLOSED` | Successor attach/prebuffer/PARK/PROMOTE repairs are integrated; the latest clean medium→short run had no recurrence | `PARTIAL` |
| Early TTS from stable response prefix | Clean run produced prefix audio before `chat.final` for the medium response | scoped `PASS` |
| Multi-unit Speech and first-tail prefetch | Clean run played prefix plus tails `1..4`; every unit and authoritative root was ACKed | scoped `PASS` |
| Real-browser A/B/A for short/medium/long | Not yet run on frozen A1/B/A2 sources | `OPEN` |
| Stop, interruption, and Exit have zero late effects | Deterministic coverage exists; current clean physical source has not run the complete matrix | `OPEN` |
| Actual first-audio and inter-unit wait | One clean medium→short sample exists; no A/B/A population or percentiles | `PARTIAL` |

Task 1 is not complete. The 2026-09-03 clean smoke is the entry gate for this
packet, not its final acceptance.

### Task 2 — Adaptive WebAudio startup lead

Task 2 remains `BLOCKED BY TASK 1`. The current candidate history contains the
adaptive-lead implementation, but Task-1 runs must force a 1,000-ms lead in all
arms so that the C019 comparison does not receive WebAudio-lead credit. Task 2
will later compare 1,000 ms against 250 ms on the same accepted C019 behavior.

## Why a direct default comparison would be invalid

At the time of this packet:

- A reference: `agtai/hx/0812_live_voice_w3` at
  `fec2bbe2d3c6ed2c658dd7a1df6683cc3e4cafc5` uses a fixed 1,000-ms WebAudio
  startup lead and has no C019 chunked continuation;
- B candidate: `bc87ab9fa259ff89f0deb0e37aadadd65f35cba4` contains both C019 and the
  configurable adaptive-lead implementation.

Running A at 1,000 ms and B at 250 ms would combine two optimizations. Task 1
therefore fixes `VITE_LIVE_VOICE_PLAYOUT_STARTUP_LEAD_MS=1000` for every arm.
The adaptive code may exist in B, but its runtime behavior remains at the
reference value. Task 2 later changes only this value.

## Frozen Task-1 arms

| Arm | Source | C019 promotion | WebAudio lead | Purpose |
|---|---|---:|---:|---|
| A1 | `fec2bbe2d3c6ed2c658dd7a1df6683cc3e4cafc5` | unavailable/off | 1,000 ms | current Hongxing reference before candidate |
| B | `bc87ab9fa259ff89f0deb0e37aadadd65f35cba4` | enabled | 1,000 ms | C019 candidate with both reproduced repairs |
| A2 | exact same source/configuration as A1 | unavailable/off | 1,000 ms | detect environment/provider drift |

All arms use Agent-Core lock `94e10cb6102c36fe78a64547957c0def97299273`.
Each arm gets an isolated worktree, data directory, P3 database, run directory,
fresh Browser Session, and one non-counted warm-up. Runs are sequential; they
must not share a live backend or Browser state.

Before execution, fetch may update the remote-tracking branch, but it must not
silently change this packet's A source. A newer Hongxing source requires an
explicit rebaseline decision and all three arms must use the revised frozen
identity.

## Fixed workloads

The operator speaks the exact English prompts after the terminal prints the
current workload. Capture duration is not compared because manual speech is not
bit-identical. All primary latency comparisons begin at authoritative EOT.

| Workload | Exact prompt | Expected response shape |
|---|---|---|
| Short | `What is the capital of France? Answer with the city name only.` | one short final/aligned unit |
| Medium | `Explain the complete water cycle in nature in five concise points.` | bounded multi-sentence response |
| Long | `Please introduce London in eight detailed points, with at least two sentences for each point, then give a summary.` | long multi-unit response |

Pilot population: one counted short, medium, and long response per arm after
one warm-up. If all functional gates pass, run four additional repetitions per
workload/arm, producing five counted samples per cell. A failure remains in the
denominator and is never replaced silently.

## Measured values

The following values must come from correlated Browser/Gateway/Runtime records;
they are measured, not inferred:

1. EOT → Agent submit/admission;
2. Agent request → first delta;
3. Agent request → `chat.final`;
4. stable authoritative prefix → TTS request, when a prefix exists;
5. TTS request → Provider first audio/downlink first frame;
6. EOT → WebAudio actually started (primary digital first-audio metric);
7. previous unit playout completed → next unit WebAudio actually started;
8. maximum and median inter-unit wait within each response;
9. EOT → final unit playout completed;
10. unit count, ordered completion count, ACK count, fallback/failure count.

Reference A responses without multiple units report inter-unit metrics as
`N/A`, never zero. Browser monotonic time is authoritative for WebAudio start
and inter-unit wait. Cross-process wall-clock subtraction is supporting
diagnosis only. Human statements such as audible gap, stutter, truncation, or
late audio are physical observations and must be labeled separately from
digital timestamps.

The approximately 670-ms WebAudio scheduling opportunity is an estimate until
Task 2 measures it physically. It must not appear as measured Task-1 gain.

## Task-1 functional gates

Every counted response must satisfy:

- correct response text and complete audible playback;
- ordered, contiguous units without reuse or gaps;
- no `MEDIA_TRANSPORT_CLOSED`, `MEDIA_PREFETCH_SUCCESSOR_UNAVAILABLE`,
  `MEDIA_STREAMING_TTS_TEXT_OR_RETRY`, or C019 local-release failure;
- exactly one presentation ACK for each actually presented unit/root;
- zero ACK/history credit for unpresented or cancelled audio;
- next-turn capture and P2 polling resume without re-enabling Live Voice.

After the A/B/A latency population, B alone runs the lifecycle matrix:

1. Stop while a successor is preparing/staged;
2. spoken interruption while a successor is staged;
3. spoken interruption while a unit is playing;
4. Exit while a successor is preparing;
5. Exit while a unit is playing;
6. Exit followed by immediate re-enable.

Each lifecycle case requires immediate local silence, no later staged-tail
playback, no late ACK/history, no stale callback revival, and successful fresh
ownership after re-enable. One lifecycle failure keeps Task 1 open even if
latency improves.

## Task-1 comparison rules

- Report every sample and failure before p50/p95.
- With five successful samples, report median and range; p95 remains
  descriptive because the population is small.
- Compare B with both A1 and A2. If A1/A2 drift materially, do not attribute
  their difference to C019.
- Separate first-audio, inter-unit continuity, and total completion; gains in
  different metrics are not additive.
- C019 is accepted only if functional/lifecycle gates pass and it produces a
  repeatable benefit for the workload it targets, especially medium/long
  responses. A short-response regression must be disclosed and bounded.

## Task-2 packet after Task-1 acceptance

Task 2 uses the exact accepted C019 behavior for all arms:

| Arm | C019 source/behavior | Startup lead |
|---|---|---:|
| A1 | accepted Task-1 candidate | 1,000 ms |
| B | same C019 behavior; adaptive-lead change isolated | 250 ms initially |
| A2 | same as A1 | 1,000 ms |

Run the same short/medium/long workloads and measure Browser-native EOT to
WebAudio start. Additionally record underrun, empty-buffer start, stutter,
rebuffer, increased inter-unit wait, truncation, incomplete playback, recovery,
and ACK failure. Accept only a stable first-audio reduction with zero new
functional failure. If the apparent gain moves waiting into later playout or is
unstable, record the result and stop parameter tuning.

For product integration, Adaptive WebAudio lead remains its own commit even if
the experiment uses build-time configuration on one source tree. Do not merge
an experimental branch wholesale.

## Immediate prerequisites before A1

1. Correct the harness-generated `run.json` Browser/version/OS, playout lead,
   workload IDs, and intended-attempt count instead of inheriting the stale
   WSLg template.
2. Automate Browser snapshot export to the run directory so the manual
   clipboard-retention step used by the clean smoke cannot lose raw L0
   evidence.
3. Create clean isolated A and B worktrees and verify each exact source and
   Agent-Core lock.
4. Run one positive and one negative launcher smoke without consuming the
   counted population.
5. Do not start Task 2 until Task 1 receives an explicit physical verdict.
