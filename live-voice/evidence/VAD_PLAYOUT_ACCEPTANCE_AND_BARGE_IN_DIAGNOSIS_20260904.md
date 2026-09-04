# VAD/playout default acceptance and barge-in diagnosis — 2026-09-04

## Scope and outcome

Source inspected: `d339e57711e28f0bac04d612378f3e9bec1ba675` on
`hx/0812_live_voice_w3`. The user accepted the physical P1-3/P1-4 checks and
directed that server VAD 800 ms and browser playout startup lead 250 ms become
the defaults. They already are the source defaults:

- `DEFAULT_SERVER_VAD_SILENCE_MS = 800`; the deployment override remains
  available only for controlled comparison or an environment-specific fallback.
- `PLAYOUT_STARTUP_LEAD_DEFAULT_MS = 250`; the bounded build override remains
  available for controlled comparison.
- the Gateway in-flight window remains 16 frames and is outside this acceptance
  change.

No source-value edit is necessary. This evidence and `STATUS.md` record the
accepted default decision without duplicating the values in a launcher or a
tracked environment file. The acceptance is scoped to these two physical
quality checks; it is not statistical latency/SLO proof and does not close the
separate interruption defect below.

The accompanying diagnosis and follow-up observer are passive and change no
recognition, VAD, interruption, cancellation, playback, Agent, Tool or Task
behavior. Raw audio, credentials and private configuration are not retained.
The observer touches the capture/playout timing owner, so it is treated as Tier
2 under root `TESTING.md` even though it has no business authority. Any later
interruption repair remains a separate Tier-2 product-policy packet.

## Reproduction

Session: `web_1a06da861de_74ce32c50c73`, local formal Web profile on port 5173.
The runtime contract names the same source and Cascade, reports a passed Speech
round trip, and enables generation interruption. Source and browser diagnostics
confirm VAD 800 ms and startup lead 250 ms. The tested playback-time barge-in
path is independent of generation-time interruption.

Three retained barge-in attempts are relevant:

| Case | Intended interruption | Authoritative committed text | Capture generation |
|---|---|---|---:|
| ML-1 | `请改成一句话` during the 20:32:18 machine-learning answer | `一句话` at 20:32:28.172 | 29 |
| ML-2 | `请改成一句话` during the successor answer | `一句话` at 20:32:40.406 | 33 |
| HZ | `用一句话介绍杭州` during the 20:33:19 Hangzhou answer | `九号到杭州。` at 20:33:30.126 | 49 |

The incorrect text is already present at the Speech final/commit boundary,
before Agent submission. The dialogue model did not rewrite a correct
interruption phrase into these strings.

The user later confirmed that every attempt used headset output and a headset
microphone. This materially weakens loudspeaker-to-microphone acoustic leakage
as an explanation and supersedes the initial speaker/microphone assumption.

## Correlated timing

Backend records and the same-tab browser export were analyzed together with:

```powershell
.\.venv\Scripts\python.exe scripts\live_voice\analyze_demo_profile.py --latest `
  --browser <same-tab-browser-export.json> `
  --session web_1a06da861de_74ce32c50c73 `
  --output logs\live-voice-ab-validation-20260904\N\session-web_1a06da861de_74ce32c50c73-barge-in-combined-report
```

The combined report contains 13,529 records and 4,499 spans with no analyzer
warning. The browser export contains 3,858 retained records, including all
events used below; it reports zero overwritten storage pages and zero storage
failures.

| Case | Provider speech start | Browser received speech start | Local playout stop | Sources stopped | Local-stop work | Gateway-ready → synthesis cancel |
|---|---|---|---|---:|---:|---:|
| ML-1 | 20:32:26.018 | 20:32:26.157 | 20:32:26.157 | 69 / 69, 0 failed | 0.2 ms | 90 ms |
| ML-2 | 20:32:38.260 | 20:32:38.267 | 20:32:38.267 | 256 / 256, 0 failed | 0.2 ms | 61 ms |
| HZ | 20:33:27.502 | 20:33:27.545 | 20:33:27.545 | 186 / 186, 0 failed | 0.1 ms | 27 ms |

Provider speech start reached Gateway in 53 ms, 1 ms and 20 ms. Once Gateway
made the event available, server synthesis cancellation began in 90 ms, 61 ms
and 27 ms. Once the browser received that event, it requested the local stop in
the same wall-clock millisecond and stopped every scheduled source in 0.1–0.2
ms. The later barge-in RPC starts only after the already-issued local stop and
stale presentation settlement, so its approximately 40 ms execution is not the
audible-stop critical path.

ML-1 differs from the two clean streaming paths. At speech start it retained
about 420 ms of unsent Gateway audio. After provider speech stop, a different
item emitted another speech-start event; the one-capture/one-final adapter
failed closed on that turn order and invoked whole-capture batch fallback with
3,460 ms of audio. ML-2 and HZ had 0–20 ms pending audio at speech start and
reached normal streaming finals about 576 ms and 613 ms after provider speech
stop.

## Diagnosis

The perceived delay is before Provider speech-start, not after the application
receives a stop signal. The current browser does not use local energy as
interruption authority: it records the energy for diagnosis and, outside
playout, uses it only to avoid a capture rotation. During playout the application
waits for the remote Speech provider's `speech_started` event before stopping
playout. This remote-only gate includes microphone/AEC processing, network
upload and Provider detection time.

The browser track confirms that `echoCancellation`, `noiseSuppression` and
`autoGainControl` were all actually enabled. This rules out a disabled browser
processing setting. With headset input/output, the retained data cannot
separate browser/OS/device speech processing from Provider VAD/recognition
behavior during concurrent playout. The captured energy only bounds the point
at which local activity was observable:

- during ML-1, the periodic browser diagnostic was already reporting
  speech-like energy at 20:32:25.640, while the remote event that authorized the
  local stop arrived at 20:32:26.157;
- during ML-2, the diagnostic rose to 2 energy frames / RMS 0.018 before the
  stop, then 21 frames / RMS 0.110 after playout stopped;
- during HZ, it reported 5 energy frames / RMS 0.086 immediately before the
  remote event and 21 frames / RMS 0.126 in the next interval after the stop.

Periodic energy samples cannot establish exact physical mouth-open time and
can contain device processing or residual playback, so they are not themselves
safe interruption authority. They show local speech-like energy before the
remote gate opens, but the one-second summaries cannot prove whether processing
suppressed the user's opening words or whether the Provider detected them late.
The Provider committed truncated or corrupted finals (`一句话` twice and
`九号到杭州。`) before Agent submission.

ML-1 also had an incident-specific 420 ms Gateway audio backlog and an extra
Provider speech item after stop, which forced a 3,460 ms whole-capture batch
fallback. That worsened the first attempt but does not explain ML-2 or HZ, where
the queue was empty or only 20 ms. The common cause is the remote Provider-only
speech-start gate. Concurrent-playout recognition failed, but the retained
evidence does not identify one exact processing layer as its cause.

This evidence rules out the following as primary causes:

- the browser stop routine: it stopped all scheduled sources without failure in
  0.1–0.2 ms after receiving speech-start;
- Gateway or synthesis cancellation: they reacted in tens of milliseconds;
- Agent/model rewriting: the wrong text existed at Speech final/commit;
- the accepted 800 ms end-of-speech hold or 250 ms startup lead: neither controls
  how playback-time near-end speech becomes an authoritative speech-start.

## Follow-up boundary

The retained browser and backend records are sufficient to locate this failure;
another reproduction is not required to show that the delay precedes the remote
speech-start gate. Because the failed trials already used a headset, changing to
a headset is not a mitigation supported by this evidence. A controlled rerun
with finer local-onset observation is required before assigning the remaining
delay to browser/OS/device processing or Provider VAD/recognition.

That passive observation is now implemented. During each answer it emits at
most four content-free milestones: first and three-consecutive-frame crossings
at RMS 0.015 and 0.05. When remote speech-start arrives, `barge_in_gate` records
the age of each local milestone, total observed/above-floor frame counts and the
peak RMS. The fixed thresholds are measurement bands, not a local VAD decision;
they cannot stop audio, cancel work, commit input or select a business route.

Owned surfaces are the Product P1 overlap observer, browser diagnostic scalar
allowlist, offline report importer and their focused tests. Provider settings,
capture processing constraints, VAD policy, playback behavior, Agent/Tool/Task
authority, raw audio and transcript logging are explicitly excluded.

An engineering repair should be scoped separately as a Tier-2 interruption
packet. The candidate direction is an echo-aware local double-talk detector that
can pre-mute playout before remote Provider confirmation, with rollback and
false-interruption tests. Local RMS crossing alone is not an acceptable policy:
playback leakage can cross the same threshold, so promoting the existing
diagnostic hint directly to cancellation authority would risk stopping answers
when the user did not speak.

Tentative local pre-muting also has product costs even if it does not immediately
cancel TTS: false positives create audible dips, continued playout can skip
content while muted, and rollback can introduce gaps, duplication or stale-audio
revival. Any repair therefore needs a tentative/confirmed state, a bounded
confirmation deadline and explicit no-speech, breath, keyboard, device-noise,
false-trigger, rollback and old-audio-revival checks.

## Verification

- server VAD focused regression: 62 passed;
- browser audio I/O regression: 107 passed, 0 failed;
- complete Product P1 route regression after the passive observer: 115 passed;
- browser diagnostic allowlist/privacy regression: 7 passed;
- offline profiling regression: 27 passed;
- combined profile analyzer: 13,529 records / 4,499 spans, no warning;
- changed-document local links and `git diff --check`: pass.

The raw same-tab browser export remains outside Git because it contains runtime
telemetry and recognized user speech. The generated HTML profile is also local
run output rather than source evidence.
