# C019 Task 1 physical validation update — 2026-09-03

## Current verdict

**PARTIAL PHYSICAL PASS / C019 TASK 1 REMAINS OPEN.**

C019 demonstrated useful medium/long behavior in the real JiuwenSwarm Web
flow. It produced early prefix audio, completed one five-unit long response,
and the operator heard continuous playback without an audible inter-unit gap,
stutter or truncation. Stop, Exit and spoken barge-in established immediate
local fences and no old audio or unpresented-tail ACK escaped afterward.

It is not yet acceptable as a complete Task-1 result:

- one clean B/long retry failed after successor promotion with
  `STREAMING_SPEECH_EVENT_QUEUE_EXHAUSTED`, while the next behavior-equivalent
  retry passed;
- Stop and spoken barge-in visibly reported `MEDIA_LOCAL_CLOSE` even though
  cancellation and silence were correct;
- Exit was physically clean but recorded as `browser_failure UNAVAILABLE`;
- the formal A/B/A population and complete lifecycle matrix are not finished;
- the reference A long path cannot synthesize the requested response as one
  request because it reaches `SYNTHESIS_TEXT_LIMIT_EXCEEDED`.

Task 2, the independent WebAudio startup-lead experiment, remains blocked.

## Frozen comparison and environment

| Role | Source | Purpose |
|---|---|---|
| A1/A2 reference | `fec2bbe2d3c6ed2c658dd7a1df6683cc3e4cafc5` | Hongxing reference without C019 |
| Original B candidate | `bc87ab9fa259ff89f0deb0e37aadadd65f35cba4` | C019 integrated candidate used by the initial pilot |
| B pause-pressure repair | `ae5f28faa2671d46668e6cab3f86398f3330e795` | Shared absolute ordinary-pause budget |
| B diagnostic source | `4921d0bc688dfb4224170360a2e5fa6de4bf441b` | Same behavior as the repaired B; queue-pressure phase visible in logs |
| Agent-Core | `94e10cb6102c36fe78a64547957c0def97299273` | Fixed dependency lock |

All counted physical attempts used Windows Chrome `151.0.7922.174`, WSL2 with
Python 3.11, physical microphone input, OpenAI
`gpt-4o-mini-transcribe-2025-12-15`, OpenAI
`gpt-4o-mini-tts-2025-12-15` with `marin`, DeepSeek
`deepseek-v4-flash` with reasoning disabled, server VAD at 1,200 ms, and fixed
WebAudio startup lead at 1,000 ms. Each arm used a fresh backend run, isolated
private data/P3 database and fresh Browser Session/correlation unless a
lifecycle scenario explicitly exercised immediate same-page reactivation.

## Initial A/B/A pilot latency

All values are Browser-monotonic milliseconds from authoritative Browser EOT.
The pilot contains one sample per cell and is not percentile evidence.

| Workload | Metric | A1 | B | A2 | Interpretation |
|---|---|---:|---:|---:|---|
| Short | EOT → WebAudio started | `6,407.1` | `5,124.1` | `4,623.5` | Inconclusive: A1/A2 drift exceeds the apparent B gain |
| Short | EOT → playout complete | `8,204.1` | `6,481.6` | `5,819.5` | Inconclusive under the same drift |
| Medium | EOT → WebAudio started | `6,328.5` | `5,028.6` | `5,717.7` | Directional B gain of `689.1–1,299.9 ms` |
| Medium | EOT → playout complete | `76,192.6` | `82,992.6` | `63,181.7` | Not comparable without normalizing response/audio length |
| Long | EOT → WebAudio started | `N/A` | `4,358.0` | `NOT_EXECUTED` | A1 failed before TTS at its single-request text limit; B TTFA is partial |

The initial B/long attempt began five units but completed four. A2/long was not
executed because it used the exact same source/configuration as the already
failed A1/long path. Missing values are `N/A`, never zero.

## B/long recovery attempts

| Attempt | Source | Result | Browser L0 |
|---|---|---|---|
| Retry 1 | `ae5f28faa` | FAIL after unit 3 promotion: `QUEUE_EXHAUSTED` / `MEDIA_STREAMING_TTS_TEXT_OR_RETRY` | 41 accepted, 0 dropped |
| Retry 2 | `4921d0bc6` | PASS: 5/5 ordered units completed | 55 accepted, 0 dropped |

The only difference between retry 1 and retry 2 was content-free diagnostic
formatting. The PASS therefore proves that the journey can complete, but not
that the intermittent failure was repaired.

### Successful B/long waterfall

| Boundary | Measured value |
|---|---:|
| EOT → first TTS request | `2,707.2 ms` |
| First TTS request → first Browser audio frame | `1,021.0 ms` |
| First Browser frame → WebAudio actually started | `682.0 ms` |
| **EOT → WebAudio actually started** | **`4,410.2 ms`** |
| EOT → final unit playout completed | `250,746.0 ms` |

Digital `unit_playout_completed → next unit_playout_started` intervals were
`4,540.5`, `1,347.5`, `1,349.7`, and `1,406.4 ms`. These are lifecycle
milestone intervals, not acoustic-silence measurements. The operator explicitly
heard no audible inter-unit gap in this response.

## Physical lifecycle results

| Scenario | Exact observed behavior | Authority/integrity result | Product result |
|---|---|---|---|
| Stop during active audio with a staged successor | Audio stopped and never returned | `barge_in → fence_cancel_completion` in `0.5 ms`; no later Browser audio/ACK; 0 L0 drops | Silence/fence PASS; visible `MEDIA_LOCAL_CLOSE` FAIL |
| Exit during active audio | Audio stopped and never returned | Prepared streams cancelled; no ACK for unpresented units; 0 L0 drops | Physical behavior PASS; L0 recorded `browser_failure UNAVAILABLE` |
| Exit → immediate re-enable → short follow-up | Repeated twice; no old water-cycle audio returned; both short responses completed | Four distinct response IDs; interrupted tails received no ACK; no response reuse/event-gap/TTS fallback | Physical re-entry PASS; Exit diagnostic classification remains wrong |
| Spoken barge-in with tail already buffered | Tail 1 buffered, then barge-in arrived `19.1 ms` later; no tail or old audio returned | Fence completed in `0.6 ms`; no post-fence TTS, promotion, playout or ACK; 0 L0 drops | Authority/silence PASS; visible `MEDIA_LOCAL_CLOSE` FAIL |

The spoken-barge run also proved that a late `chat.final` publication remained
behind the established fence and produced no Browser authority effect.

## Confirmed causal defect found after the physical run

Independent review reproduced the B/long failure without Chrome using the
product queue capacity of eight. An ordinary pause deadline was armed before
PARK. PARK/PROMOTE correctly transferred and resumed Provider ownership, but
the original `_enqueue_frame` call then reused that expired ordinary deadline
in the post-PROMOTE watermark wait:

```text
ordinary pause at queue 8/8
  → PARK for longer than ordinary deadline
  → PROMOTE succeeds
  → first promoted frame is pulled
  → stale pre-PARK deadline enters resume watermark
  → STREAMING_SPEECH_EVENT_QUEUE_EXHAUSTED
```

The older route test used queue capacity one. For capacities below four the
resume watermark equals the capacity, so the failing branch was unreachable.
This is why the earlier automated Gate passed.

A local work-in-progress repair now releases the ordinary deadline/cleanup
owner when PARK takes ownership and PROMOTE has already resumed the Provider.
The new capacity-eight test failed before the repair and passes afterward; the
complete route module passes `83/83`. The lifecycle oracle now also records:

- `C019-ORDINARY-DEADLINE-01`: PARK cannot retain an ordinary deadline;
- `C019-TRANSPORT-01`: cancellation makes an attached transport close
  expected, and an expected close cannot become a reported failure.

The lifecycle model passes `33/33`. These changes remain work in progress and
have no new physical credit until reviewed, committed and rerun.

## Remaining work before Task 1 can pass

1. Complete independent review and commit the capacity-eight deadline repair.
2. Rerun B/long on the exact clean repair and establish repeatability.
3. Reproduce the visible `MEDIA_LOCAL_CLOSE` in a mounted product fixture and
   wire `C019-TRANSPORT-01` to real Stop/barge/Exit product signals.
4. Ensure expected Exit never emits an L0 `browser_failure`; retain the exact
   content-free reason for genuine failures.
5. Finish the remaining Stop/interruption/Exit lifecycle cases with zero late
   audio, ACK/history or stale-generation revival.
6. Complete the agreed A/B/A population or document a revised long-form
   comparison because reference A cannot pass its single-request text limit.
7. Only after Task 1 passes, run the independent 1,000→250-ms WebAudio startup
   lead A/B/A experiment.

## Evidence

- Initial pilot:
  [`C019_TASK1_ABA_PHYSICAL_PILOT_20260903.md`](C019_TASK1_ABA_PHYSICAL_PILOT_20260903.md).
- B/long recovery:
  [`C019_B_LONG_RECOVERY_SMOKE_20260903.md`](C019_B_LONG_RECOVERY_SMOKE_20260903.md).
- Initial pilot root:
  `/home/renan/openJiuwen-ai/live-voice-latency-runs/c019-task1-aba-20260903T114834Z`.
- Recovery/lifecycle root:
  `/home/renan/openJiuwen-ai/live-voice-latency-runs/c019-task1-aba-20260903T134232Z`.
- Successful B/long Browser snapshot SHA-256:
  `410ab3b2f0833ee47902aebc197187b09210ddda4564cc1a04f84e850412d2c3`.
- Stop Browser snapshot SHA-256:
  `32b084ae83069f31220222f670c19877bbc562aae5aac287817782b3365129ad`.
- Exit Browser snapshot SHA-256:
  `b4494b4c49cdd8215289454514da12fb55367c671e4d0dbc15fc205b99dc3d6c`.
- Exit/re-enable Browser snapshot SHA-256:
  `bab58f2ce7d7efe86a1dcd65656090bef1c5fb8e91e7aa18abdded17e065dc50`.
- Spoken-barge Browser snapshot SHA-256:
  `6ba64a667d6d1659c73c2baad61ce169eb5c2275266cfc8f6a4163a0b7958d58`.

Raw Browser snapshots and logs remain private, mode-restricted artifacts
outside Git.
