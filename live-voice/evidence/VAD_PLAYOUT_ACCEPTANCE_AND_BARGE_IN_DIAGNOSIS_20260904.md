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

### Controlled headset rerun

The requested same-device rerun used Session
`web_1a06dcf9e50_d9209702defd`, response
`response-unified-c1527d9e05e168636d83dd044d31daa1` and capture
`c041ba5e-a973-4687-80cb-a1fc2ff72264`. The user said “停一下，请改成只说一句话”; the
Provider final was “请改成只说一句话”. The complete target capture reached a normal
streaming final without fallback or transport failure.

The same browser clock gives this exact onset-to-stop sequence:

| Observation | Time | Delta |
|---|---:|---:|
| first processed capture frame above RMS 0.015 | 19:05:40.255Z | baseline |
| three consecutive frames above RMS 0.015 | 19:05:40.295Z | +40.1 ms |
| Provider speech-start reached the browser | 19:05:40.493Z | +238.7 ms from first / +198.7 ms from sustained |
| all 254 scheduled playout sources stopped | 19:05:40.494Z | +1.2 ms from browser speech-start |

Before the remote gate opened, 157 playout-overlap frames had been observed, but
only three crossed RMS 0.015, peak RMS was 0.044, and no frame crossed the 0.05
strong band. In the first periodic bucket after playout stopped, 24 frames were
speech-like and peak RMS rose to 0.218, about five times the pre-stop peak. This
matches the user-visible split: the low-energy leading stop phrase was omitted,
while the stronger continuation spoken after local stop was retained.

This was not an upload/backpressure loss. Browser sent/ACK counts were equal at
the first activity frame; Gateway queue and pending audio were zero immediately
before speech onset; all 326 capture frames were ultimately acknowledged. The
Provider returned `audio_start_ms=2432`; the first local activity was nominally
at frame 161, about 3220 ms into capture. The roughly 788 ms lookback matches the
configured 800 ms barge-in prefix, so increasing prefix padding does not address
this failure. The Provider wire speech-start arrived about 166 ms after local
activity by same-host wall time, and the remaining control delivery took about
72 ms; neither path dropped audio.

The proximate failure is therefore a severely weakened leading phrase in the
processed microphone stream while TTS is still playing, followed by a clear
continuation after stop. Without an opt-in raw pre/post-processing recording, the
evidence cannot honestly assign that attenuation to one hidden component among
the headset/driver, OS, Chrome AEC/noise suppression/automatic gain control and
Provider transcription. The product-level root cause is still precise: remote
Provider VAD is the sole barge-in authority, so playout continues during the
exact double-talk interval that weakens the words needed to trigger and identify
the interruption. This feedback loop makes first-phrase preservation depend on
the weakest concurrent-playout capture behavior.

This evidence rules out the following as primary causes:

- the browser stop routine: it stopped all scheduled sources without failure in
  0.1–0.2 ms after receiving speech-start;
- Gateway or synthesis cancellation: they reacted in tens of milliseconds;
- Agent/model rewriting: the wrong text existed at Speech final/commit;
- the accepted 800 ms end-of-speech hold or 250 ms startup lead: neither controls
  how playback-time near-end speech becomes an authoritative speech-start.

## Follow-up boundary

The passive observation emits at
most four content-free milestones: first and three-consecutive-frame crossings
at RMS 0.015 and 0.05. When remote speech-start arrives, `barge_in_gate` records
the age of each local milestone, total observed/above-floor frame counts and the
peak RMS. The fixed thresholds are measurement bands, not a local VAD decision;
they cannot stop audio, cancel work, commit input or select a business route.

Owned surfaces are the Product P1 overlap observer, browser diagnostic scalar
allowlist, offline report importer and their focused tests. Provider settings,
capture processing constraints, VAD policy, playback behavior, Agent/Tool/Task
authority, raw audio and transcript logging are explicitly excluded.

The engineering repair is a separate Tier-2 interruption packet spanning Audio
Device & I/O, Interaction Intelligence and Conversation Runtime:

1. Audio I/O produces a typed, content-free near-end speech candidate carrying
   capture, response and generation identity. It must use a real local voice/
   double-talk detector with hysteresis and the known far-end playout signal;
   the existing RMS milestones remain diagnostic only.
2. Interaction Intelligence owns the tentative decision. Conversation Runtime
   validates the active response/generation and asks Audio I/O to freeze local
   playout at its exact unplayed cursor within the local latency target. This
   tentative pause does not cancel Agent/TTS work and cannot commit input.
3. Matching Provider speech-start within a bounded confirmation window promotes
   the candidate to a permanent hard-stop and exact-response cancel/fence. A
   false candidate resumes from the same cursor with a short ramp; clock time
   must not advance through muted content, so no answer words are skipped.
4. Capture processing becomes an explicit device profile rather than three
   unconditional browser `ideal: true` hints. Headset and speaker paths require
   separate A/B evidence. For the OpenAI Adapter, `near_field` Provider input
   noise reduction and an explicit Chinese language hint are eligible headset
   candidates, but browser and Provider suppression must not be stacked by
   default before double-talk CER proves that combination.
5. Keep the working 800 ms pre-roll and evaluate a current streaming
   transcription model behind the existing Provider-neutral Port. Model or
   input-processing changes are separate A/B dimensions from local pause logic.

This design removes the circular dependency while preserving authority: a local
candidate may temporarily pause only the exact active response; remote Speech
still owns committed text and EOT, and Runtime still owns cancellation. Lowering
the Provider VAD threshold, increasing the already-effective prefix, prompting
for the literal words “停一下”, or making an RMS crossing cancel work would be
parameter/hard-code patches that do not solve the double-talk control loop.

Acceptance must include TTS-only, silence, breath, cough, keyboard/device noise,
real near-end speech, one-second/five-second barge-in, false-candidate rollback,
device change and stale-generation cases. Required outcomes are no committed
input or cancel on false candidates, no skipped/duplicated/revived audio on
rollback, exact-response-only permanent cancellation, double-talk CER no more
than 5 percentage points worse than quiet speech, at least 95% playback-time
barge-in success, and measured local pause/Provider confirmation percentiles.

## Passive-diagnostic deployment

Commit `a7688f3ab4aa9efd0625b224dcb07a6c0fa30714` was deployed through the
controlled `formal-web-validation` launcher with source branch
`hx/0812_live_voice_w3`, generation interruption enabled, the saved isolated
project/data directory and frontend port 5173. The project retained its one
pre-existing untracked helper under the launcher's explicit dirty-project
allowance; the deployment did not modify it.

The launcher rebuilt the frontend and passed real Speech TTS-to-STT, formal
receipt, identity-mismatch rejection and forged-claim rejection probes with
zero business side effects. Runtime-contract source matched `a7688f3ab4`; ports
5173, 18092, 19000 and 19001 were listening, the page returned HTTP 200, and
the served `/assets/index-C1-6cszx.js` contained the
`capture_playout_activity` diagnostic marker. The controlled headset
reproduction above completed on that deployed source and closes the diagnostic
question; it does not make the unrepaired interruption behavior pass.

## Verification

- server VAD focused regression: 62 passed;
- browser audio I/O regression: 107 passed, 0 failed;
- complete Product P1 route regression after the passive observer: 115 passed;
- browser diagnostic allowlist/privacy regression: 7 passed;
- offline profiling regression: 27 passed;
- combined profile analyzer: 13,529 records / 4,499 spans, no warning;
- controlled headset rerun profile: 1,353 records / 438 spans; the target
  capture has a normal streaming final and complete onset/queue/stop evidence;
- changed-document local links and `git diff --check`: pass.

The raw same-tab browser export remains outside Git because it contains runtime
telemetry and recognized user speech. The generated HTML profile is also local
run output rather than source evidence.
