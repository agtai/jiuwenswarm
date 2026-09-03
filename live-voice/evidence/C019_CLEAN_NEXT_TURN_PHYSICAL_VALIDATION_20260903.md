# C019 clean next-turn physical validation — 2026-09-03

## Result

**SCOPED PHYSICAL FUNCTIONAL PASS / COMPLETE C019 PHYSICAL VALIDATION PENDING.**

This run closes the two reproduced continuous-turn defects on an exact clean
source: the Browser no longer loses the authoritative text root while the last
audio-unit ACK is in flight, and the Gateway no longer carries one response's
prefetch sequence cursor into the next response. It does not yet close the
short/medium/long A/B/A population, Stop/interruption/Exit matrix, latency
distribution, or Adaptive WebAudio lead acceptance requested by Hongxing.

## Exact source and environment

- Branch: `fix/live-voice-next-turn-agent-output`.
- JiuwenSwarm source: `bc87ab9fa259ff89f0deb0e37aadadd65f35cba4`, clean.
- Hongxing comparison base: `agtai/hx/0812_live_voice_w3` at
  `fec2bbe2d3c6ed2c658dd7a1df6683cc3e4cafc5` when inspected.
- Installed Agent-Core package: lockfile source
  `94e10cb6102c36fe78a64547957c0def97299273`; this run did not use the dirty
  checkout at `/home/renan/openJiuwen-ai/agent-core`.
- Browser: installed Windows Chrome `151.0.7922.174` (64-bit), supplied by the
  operator.
- Backend: WSL2, Python 3.11.15.
- Input: physical microphone operated by the user; no fake-audio injection.
- Agent: `deepseek-v4-flash`, OpenAI-compatible client, reasoning disabled.
- STT: OpenAI `gpt-4o-mini-transcribe-2025-12-15`.
- TTS: OpenAI `gpt-4o-mini-tts-2025-12-15`, voice `marin`.
- VAD: OpenAI server VAD, 1,200-ms silence setting.
- Runtime flags included formal Integrated Web/P1, P2 product composition,
  dedicated media, end-of-turn, latency probe, C019 prefetch promotion, and a
  250-ms WebAudio startup lead.

The inherited `run.json` template incorrectly labels the Browser as Linux
Chrome 150 under WSLg and the playout lead as 1,000 ms. The actual runtime was
Windows Chrome 151 with the launcher exporting 250 ms. The mismatch is
disclosed here and must be corrected before the formal A/B/A population.

## Run identity and retained artifacts

- Run ID: `lv-diag-wsl-en-v1-20260903T111952Z-bc87ab9fa`.
- Run directory:
  `/home/renan/openJiuwen-ai/live-voice-latency-runs/c019-next-turn-clean-smoke/bc87ab9fa/lv-diag-wsl-en-v1-20260903T111952Z-bc87ab9fa`.
- Run configuration: `run.json`, SHA-256
  `7e3220ab4f9d4b3b936d1f65564296f251d56d5849ffafc3a42219f9a69abf5a`.
- Raw Browser L0 snapshot: `browser-l0-snapshot.json`, SHA-256
  `8cd492472be92993c09f7618adf28a04a6602282a83fb8b706ebc77cfcb3f4b3`
  (183,518 bytes, mode `0600`).
- Sanitized correlated backend trace: `backend-c019-sanitized-trace.log`,
  SHA-256
  `7d9142d6f742a83042042173656f26c9e57022890ab2801d12d85c6286aca83d`.
- Backend log:
  `/home/renan/.jiuwenswarm-c019-physical/agent/.logs/full.log`.
- Browser session: `web_1a067006e83_71a3a0c39a7b`.
- Correlation:
  `integrated-web-abd75680-1b5c-46fa-ab86-ad5ace82d20f-web_1a067006e83_71a3a0c39a7b-683d8d47-207d-4b6b-9f48-a1192e480fe8`.

The retained Browser snapshot validates as enabled and configured and contains
67 accepted records, zero dropped records, and 67 records in the payload.

## Procedure

The operator opened the run URL, force-reloaded the page, configured L0 as
`profile_id=c019-next-turn-clean`, `scenario_id=medium-then-short`, warm,
physical, and enabled Live Voice once. The prompts were spoken consecutively
without disabling or re-enabling Live Voice:

1. `Explain the complete water cycle in nature in five concise points.`
2. `What is the capital of France? Answer with the city name only.`

The second prompt was spoken only after the complete first response finished
and listening resumed.

## Observed results

| Boundary | Medium response | Short successor |
|---|---:|---:|
| Response ID | `response-unified-5b772c0964ba918ea12830e49945cf83` | `response-unified-548ac7d7077279faabbd6f5323b22d6f` |
| Response generation | `0` | `1` |
| Same P2 activation generation | `1` | `1` |
| Browser audio units | prefix `0`, tails `1..4` | aligned final `0` |
| Completed audio units | `5/5` | `1/1` |
| Authoritative root/text ACK | yes | yes |
| Browser TTS-request time | `11:21:33.127Z` | `11:22:43.583Z` |
| Browser WebAudio actually-started time | `11:21:34.199Z` | `11:22:44.663Z` |
| Browser final playout time | `11:22:33.910Z` | `11:22:46.030Z` |
| Browser EOT-receipt monotonic time | `25,177.3 ms` | `95,714.4 ms` |
| Browser WebAudio-start monotonic time | `28,810.6 ms` | `99,275.1 ms` |
| Browser-native EOT-to-WebAudio-start | `3,633.3 ms` | `3,560.7 ms` |
| Browser-native EOT-to-playout-complete | `63,344.9 ms` | `4,927.4 ms` |

These values use the retained Browser snapshot's own monotonic clock and do not
mix the WSL and Windows clocks. They are individual smoke observations, not p50
or p95. The earlier `11:21:33.127Z` and `11:22:43.583Z` observations are now
correctly classified as TTS-request times rather than first-audio times.

For the medium response, the monotonic starts of units 1 through 4 occurred
`612.9`, `607.9`, `633.3`, and `606.7 ms` after the preceding unit completed.
Those four observed inter-unit waits have a median of `610.4 ms` and a maximum
of `633.3 ms`. This proves ordered prefetch and promotion, but it also preserves
measured headroom for the remaining continuity work; it is not evidence of
gap-free playback.

The medium response emitted a stable prefix before `chat.final`, synthesized
and played five ordered audio units, promoted tails 1 through 4, ACKed each
audio cursor, then ACKed the authoritative text root. The short response was
submitted and consumed without a new activation, proving that P2 polling
resumed across the exact root/ACK boundary.

There were zero occurrences during the counted journey of:

- `MEDIA_PREFETCH_SUCCESSOR_UNAVAILABLE`;
- `TTS_CONTINUATION_LOCAL_RELEASE_FAILED`;
- late or missing C019 audio-unit ACK;
- response/unit gap or reuse;
- dropped L0 records.

One content-free `CancelledError` was logged for an uplink route during normal
capture rotation. The short response also contained an L0 `discarded_work`
record classified `STALE_GENERATION`, while its exact final audio started,
completed, and was ACKed. Neither reproduced the two defects under test; both
remain disclosed residual diagnostics rather than receiving closure credit.

## Source and review evidence

The relevant commit sequence is:

1. `74b2a158c` — fail closed when a formal Agent stream lacks final/error truth
   and add content-free boundary tracing;
2. `59a369483` — preserve the authoritative C019 root across an in-flight final
   tail ACK and release a stuck response owner on cancellation;
3. `bc87ab9fa` — bind the prefetch cursor to the current response generation.

Post-fix automated evidence on exact HEAD:

```text
Gateway product streaming synthesis: 18 passed
Mounted Browser C019 family:          10 passed
Ruff:                                 PASS
git diff --check:                     PASS
```

Independent investigation and implementation reviews are retained outside Git
in the run directory (the `/tmp` originals are disposable):

- `C019_CONTINUOUS_NEXT_TURN_CLAUDE_REVIEW_2026-09-03.md`, SHA-256
  `424e28bba13eddf9d5884fe726548c4bcca5666388d92673fb42f5663c515135`;
- `C019_CROSS_RESPONSE_PREFETCH_CURSOR_CLAUDE_REVIEW_2026-09-03.md`, SHA-256
  `f376511f15bdf8ab395653c0080e701fc7d696257e643218f29159200c20dddb`;
- `C019_CROSS_RESPONSE_PREFETCH_CURSOR_IMPLEMENTATION_REVIEW_2026-09-03.md`,
  SHA-256
  `c6e6e4651a84f7b4d8d00aaf971ad59e2443a268d4733ae11ddfb51e80466846`.

## Remaining Task-1 gate

This run proves early authoritative-prefix TTS, multi-unit streaming synthesis,
one-ahead prefetch, ordered promotion, final-root settlement, and one continuous
medium-to-short successor. Hongxing's Task 1 remains `PARTIAL` until all of the
following pass on controlled A1/B/A2 sources:

- short, medium, and long response workloads;
- repeated actual first-audio and inter-unit-gap measurement;
- Stop during staged/prepared audio;
- interruption/barge-in during active and staged audio;
- Exit during preparation and playout;
- zero late audio, late ACK, false history, or revived response;
- corrected run metadata (the snapshot is retained, but the inherited
  `run.json` still describes the wrong Browser and startup-lead value).

Task 2, Adaptive WebAudio startup lead acceptance, remains gated on that Task-1
closure and must be evaluated as an independent behavior change.
