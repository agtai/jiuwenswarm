# AIO-B + X-WEB browser decision implementation review

> Batch date: 2026-08-05
>
> Branch/worktree: `codex/aio-b-x-web` / independent worktree from `56b45480d8ef05199a00cbcb100d499557871035`
>
> Record role: **frozen source-candidate review plus current-branch integration review; landed state is owned by `STATUS.md`**
>
> Integration reconciliation: the candidate-local browser decision ID D-057 is recorded as D-058 on the integration branch because D-057 already belongs to D-031 closure. Current-branch hardening also rejects capture-ID reuse, exposes the actual playout PCM rate and unsupported output-device/physical-heard capabilities, and reports idle playout-context loss; the integration verification is recorded below.

## 1. Original request and bounded outcome

During the user's parallel D-031 work, implement the independent `AIO-B + X-WEB browser decision slice`. The accepted product choice is one desktop Google Chrome Alpha baseline. The batch must establish a real browser Audio I/O Adapter and truthful platform diagnostics without claiming a real Speech Provider, Realtime Media, formal Agent route, cumulative P1/P2/P3alpha journey or Web Alpha release.

The code boundary is the frontend formal Live Voice area, its focused tests, this review, D-058 and the stable Web delivery matrix. The batch avoids Task/AgentServer/scheduler/i18n files owned by the parallel D-031 lane. Shared mutable STATUS reconciliation is deferred until implementation facts exist and must explicitly account for the parallel integration owner.

## 2. Consumed authority and risk

- Historical module boundary: `architecture/FULL_SOLUTION_2026-07-30.md` §§4–6, interpreted for Web by D-055.
- Normative contract: `architecture/ARCHITECTURE_CONTRACT_GATE_V1.md` §§3–4, 7, 10–15.
- Current decisions: D-039, D-042, D-044, D-046, D-047, D-052, D-053, D-055 and D-058.
- Stable packages: `roadmap/WEB_ALPHA_DELIVERY_MATRIX_2026-08-05.md` AIO-B/AIO-C/X-WEB rows.
- Acceptance consumers: `validation/ALPHA_ACCEPTANCE.md` §§3 and 7; this batch cannot close those full Gates.

`AIO-B` is Tier 2 because it owns device/permission state, frame ordering, stale callback fencing and local playback effects. The X-WEB compatibility decision and eventual release Gate are Tier 3. This coherent batch therefore uses the D-053 three-review process and records every applicable risk dimension below.

## 3. Pre-implementation findings

1. Existing `formal/audioPort.ts` provides exact-response playback queue, ordered chunks, acknowledgements and non-escalating local stop. It has no capture frame, device, permission, Web Audio clock or browser Adapter.
2. Existing Browser Speech Adapters truthfully declare fallback/batch-only capability but `SpeechRecognition` owns its microphone and `speechSynthesis` exposes no PCM/cursor. Neither can be placed inside the formal AIO frame path.
3. AIO-B can be implemented and tested against an injected frame/playout consumer without RM-B or a real Speech Provider. Therefore this batch is a real device Adapter but not the formal P1 end-to-end route.
4. The browser-facing contract must remain transport-neutral. It exposes actual mono Float32 PCM format and clock facts; it does not choose a Gateway wire codec or create connection/media/interaction/turn/task authority.
5. Browser API support is capability-tested rather than inferred from user-agent strings. The release scope is a product/evidence decision in D-058, not runtime browser sniffing.

## 4. Frozen implementation contract

### Capture

- Construction and capability inspection are side-effect free.
- `startCapture` requires enabled capability, secure context, visible page, media devices, AudioContext and AudioWorklet.
- `getUserMedia` requests one audio track, optional exact input device, ideal AEC/NS/AGC and mono. Requested and actual track settings remain separate.
- AudioWorklet downmixes to mono and emits exact 20ms Float32 frames at the actual AudioContext sample rate. Every frame has capture ID/generation, track ID, sequence, sample cursor, context timestamp and format.
- Duplicate, gapped, malformed, cross-generation and post-stop messages have zero consumer effect. A gap/protocol violation terminates the capture rather than sorting or guessing.
- Stop, permission/device loss, processor failure or hidden page fences callbacks before asynchronous cleanup. Page visibility restoration does not auto-restart capture.
- Device changes are observable; active capture never silently changes input.

### Playout

- Input requires exact response tuple, unit/sequence, mono Float32 format and Provider/fallback provenance.
- Web Audio schedules only contiguous current-response chunks. Completion advances a contiguous browser-render cursor; scheduling/start alone does not.
- Wrong/stale response, invalid format/provenance or post-stop callback has zero playback/presentation effect.
- Local stop targets only the exact current response, fences completion callbacks and stops browser sources. Business cancellation count remains zero.
- AudioContext that remains suspended after explicit resume fails visibly with user-activation guidance.

### Platform and privacy

- The initial Alpha scope is one declared desktop Google Chrome candidate environment; runtime checks capability rather than browser brand.
- Raw samples remain memory-only and never enter route telemetry, browser storage, URL or logs.
- No Provider credential or endpoint is introduced.
- This batch may expose diagnostics for capability, permission/device state and actual audio settings, but not raw device labels/IDs in logs or persisted evidence.

## 5. Scenario oracle

| ID | Scenario | Required result | Forbidden effect |
|---|---|---|---|
| P-01 | supported secure environment starts default/exact-device capture | one live track, running context/worklet and ordered 20ms frames | duplicate stream/context or fabricated setting |
| P-02 | current response receives contiguous PCM chunks | browser sources schedule in order and completion advances cursor | queued/start treated as completed |
| N-01 | feature disabled, insecure origin or missing capability | stable explicit rejection before device/context effects | getUserMedia, AudioContext, listener or timer |
| N-02 | permission denied, device absent or constraint rejected | stable safe error and released partial resources | empty success or automatic fallback capture |
| N-03 | wrong response, Provider provenance or audio format | reject/no-op before scheduling | audio output, ACK or business cancel |
| B-01 | actual context rate cannot form an integer 20ms frame | stable rejection and full partial-resource cleanup | rounded timing drift, hidden custom resampling or mislabeled rate |
| S-01 | start/stop/restart lifecycle | each start has new identity/generation; prior session stays terminal | capture resurrection or ID reuse |
| T-01 | stop/hidden/device-ended during pending getUserMedia/worklet setup | late resources immediately release and produce no frame | active stale capture or auto-restart |
| T-02 | old worklet/source callback after replacement/stop | exact stale effect count 0 | frame, ACK, playback or state mutation |
| C-01 | concurrent starts/stops | one active capture/playback authority and deterministic rejection/fence | two active captures or widened stop |
| R-01 | devicechange, track mute/ended, page hidden/resume | visible event/failure; hidden/ended releases; resume requires user start | silent switch or hidden continued capture |
| I-01 | AIO Adapter against fake consumer and AudioPort | exact identities, sequences, format and provenance survive | RM/CR/Speech identity invention |
| F-01 | AIO path absent/disabled beside current Browser Speech Demo | legacy path/build behavior unchanged | new media side effects at module import/mount |
| K-01 | unsupported output selection/physical-heard proof | capability remains unsupported/unknown | default sink or render callback presented as verified hearing |
| X-01 | real desktop Chrome microphone/playout harness | exact environment and observable frames/playback recorded | P1/P2/Provider/release closure claim |

Agent, Tool, Task, Chat mutation, response/round/task cancel, raw-audio persistence and Provider credential effects are `0` in every scenario.

## 6. Planned source and checks

Expected code/tests:

- `frontend/src/features/live-voice/formal/audioPort.ts`
- new browser Audio I/O Adapter and AudioWorklet processor under `formal/adapters/`
- focused browser platform/capture/playout tests under `frontend/tests/`
- frontend package scripts, only for the new focused suite
- a manual Chrome harness only if required for repeatable real-device evidence

Planned verification:

- focused TypeScript compile and Node tests with deterministic fake browser/audio environment;
- existing AudioPort, Browser Speech Adapter, fake P1, route telemetry, Live Voice core/lifecycle/TTS regressions;
- frontend `tsc`/Vite build and affected lint;
- real Chrome controlled run with exact version/OS/origin, default-or-exact device choice, actual processing/format and no persisted raw audio or device label/ID;
- `git diff --check` and Live Voice Markdown-link validation;
- D-053 self-review, cold complete-diff review and independent review or an explicitly recorded equivalent.

## 7. Explicit exclusions

- SR-B/C, SS-B/C, RM-B/C, CR-B/C, AB-B and real Provider/Gateway wiring;
- transport codec/resampling, WebSocket/WebTransport and deployment proxy/CSP/CORS closure;
- automatic input/output device switching, mobile/background capture, PWA and non-Chrome support;
- AIO-C exact-response stop latency target, double-talk/AEC quality target and full Web Alpha Gate;
- any D-031 file, Task lifecycle, Agent execution or integration operation;
- Git commit, push or merge without the repository's separate exact approvals.

## 8. Review and evidence ledger

| Pass | State | Findings/fixes/evidence |
|---|---|---|
| Pre-review | `FROZEN` | Sections 1–7 defined the accepted contract and oracle before code changes. |
| Implementation self-review | `PASS AFTER FIXES` | Full source/test review found and fixed four lifecycle defects before acceptance: missing document visibility could overclaim capture capability; observer or cleanup exceptions could interrupt release; an invalid replacement response could stop current playout; and Web Audio could silently resample a mismatched chunk rate. Added exact negative/recovery tests for each boundary. |
| Cold complete-diff review | `PASS AFTER FINAL REPEAT` | The first cold pass fixed exact-frame, stale callback, AudioContext error mapping and accepted-chunk/source-setup recovery gaps. The complete diff was repeated after each semantic review fix. The final pass covers externally fenceable pending capture resources, early track/context-loss listeners and handoff validation, serialized stop/startup-failure cleanup, terminal `unlockPlayout`/`close` generations, and the final close ordering: playout is synchronously fenced while capture/playout resources clean up in parallel. Deferred, active-loss and late-effect tests cover the revised semantics; no remaining actionable defect was found. D-058 also distinguishes browser graph rate adaptation from forbidden hidden custom resampling. |
| Independent review | `PASS AFTER FIXES` | The read-only reviewer first found three P1 races and one P2 STATUS mismatch: pending capture cleanup, startup track/context loss, `unlockPlayout` versus `close`, and stale real-evidence status. A later re-read found one additional P1 close-ordering gap that allowed playback to outlive slow capture cleanup. All findings were fixed in source/tests/STATUS. The final review of the latest complete diff reported no remaining actionable finding; it did not edit files or rerun browser/device evidence. |
| Current-branch integration review | `PASS AFTER FIXES` | Reconciled the candidate against `hx/0803_live_voice` and repeated a cold complete-diff review. It resolved the D-057 collision as D-058, removed stale parallel-branch/blocker claims from current STATUS, made `unlockPlayout` return the actual accepted PCM rate instead of forcing callers to guess the AudioContext rate, made idle post-unlock AudioContext loss visible, rejected capture-ID reuse across Adapter lifetimes, and stopped treating capture-only local ID generation as a playout capability prerequisite. Focused tests cover each correction. The final complete-diff repeat found no remaining actionable defect in this bounded slice. The prior independent review remains the D-053 independent pass; this integration review did not claim a second `/review` or new real-device run. |
| Alternate closure audit (`066d43eb`) | `PASS AFTER FIXES` | Product source/tests in `066d43eb` are identical to landed `50b98b4a`; only its candidate-local review/STATUS differ, so it was reviewed but not cherry-picked. The audit replaced delimiter-based response identity with structural comparison and a normalized observer payload, fenced capture/playout observer reentrancy, reported and de-duplicated an initially muted track, and made duplicate source-end callbacks inert. A cold repeat also moved the initial capture fence inside cleanup ownership. Focused AIO tests pass 39/39 and affected regressions pass 102/102. A fresh CLI `/review` could not complete: CLI 0.111 rejected the current model, and its compatible-model retry produced no result before termination. The prior independent pass therefore remains the independent evidence; this follow-up adds self-review and repeated cold complete-diff review but claims no new independent result or device run. |
| Automated verification | `PASS WITH LINT LIMITATION` | Focused strict TypeScript/bundle suite passes 31/31, including zero playback/business-cancel effects for an invalid playout AudioContext rate. Affected AudioPort, Browser Speech, fake P1, route telemetry, Live Voice core, turn lifecycle and TTS regressions pass 77/77. Frontend `tsc && vite build`, affected frontend Prettier, `git diff --check`, and local Live Voice Markdown-link validation pass. The repository declares ESLint but has no discoverable ESLint configuration, so lint exits before checking source; this is recorded, not claimed as a pass. |
| Real Chrome evidence | `PASS FOR OBSERVED NORMAL PATH; POST-RUN CHANGES AUTOMATED` | Desktop Google Chrome `150.0.7871.116`; Windows NT build `26200.8875`, DisplayVersion `25H2`; `http://127.0.0.1:5193`; local controlled network; user-approved default microphone. Actual track settings reported 48 kHz mono with AEC, noise suppression and automatic gain control enabled; device identity was present but its value was not persisted. The AudioWorklet produced 1,283 contiguous 20ms mono Float32 frames (960 samples each), from sequence/cursor `0/0` through `1282/1230720`, with final context time `25.64s`. After explicit Stop, the count remained 1,283 after a further wait, capture ended as `stopped/harness_stop`, and the Adapter closed cleanly. Explicit synthetic 48 kHz mono PCM reached exact response `aio-harness-response-0`, unit `synthetic-tone`, contiguous `render_completed through_seq=9`; this proves browser graph completion, not that a person heard it. Chrome console warnings/errors were empty. Later reviews tightened failure/concurrency and identity validation, exposed the accepted playout rate, and updated the harness to consume that rate. Those changes pass deterministic tests but were not recreated on the real device. This one-machine evidence does not close permission revoke/device loss/background/AIO-C latency or the Web Alpha Gate. |

The bounded AIO-B/X-WEB decision slice originated on `codex/aio-b-x-web` and was reconciled and cold-reviewed on `hx/0803_live_voice`, including the integration fixes above and browser decision D-058. Alternate closure `066d43eb` is superseded rather than an additional integration commit. Those fixes were verified deterministically but were not rerun on the physical Chrome device, so the earlier normal-path evidence is not widened. Current landed state belongs to `STATUS.md`. This slice does not close cumulative P1/P2/P3alpha or the Web Alpha Gate; the real-device limitations recorded above remain open acceptance work.

## 9. 2026-08-08 D-065 cumulative-route correction

This section is a later review addendum; it does not rewrite the frozen 2026-08-05
contract or widen its real-device evidence. The original section 4 rule that every
render gap terminates capture is superseded only by D-065's bounded Chrome input
semantics: one forward gap may be materialized as silence only after real input
returns, only up to 15ms, with at most 60ms inside a rolling 1000ms window. Initial
empty input publishes no frame, a gap cannot span one complete 20ms frame, and
over-limit, repeated, regressed-clock, malformed, stale or cross-generation input
still fails closed with a stable reason.

The correction was triggered by a real cumulative P1/P2 run in which Agent text
reached exact presentation acknowledgement and TTS began, after which the
concurrent capture stopped and P1 cleanup interrupted the current downlink. Gateway
and Agent logs exclude an Agent cancel, Gateway-initiated stop and downlink ACK
timeout; the former generic `AUDIO_CAPTURE_STOPPED` prevented stronger attribution.
The Adapter now preserves exact Worklet/input protocol reasons. A corrected physical
run remains required before claiming that D-065 fixed the observed machine or that
the user heard the complete response.

Deterministic closure covers processor→Adapter→P1→dedicated-downlink composition:
a bounded startup gap plus a bounded playing-window gap keeps capture and playout
alive, and downlink ACK remains render-completion-driven. Repeated sub-threshold
gaps exceed the rolling budget and stop with zero playout receipt, zero widened
cancel, no post-failure `capturing` publication and exact closure of both media
authorities. Track end, context loss, page hide, processor error, stale callbacks,
missing real readiness and missing Gateway ACK retain their prior fail-closed tests.
Current test/review and physical-validation state belongs only in `STATUS.md`.

## 10. 2026-08-08 D-066 render-clock predicate correction

This later addendum does not widen the frozen AIO-B evidence. The first physical
rerun after D-065 reached real Agent text and TTS but the user heard only the first
phrase before exact `AUDIO_RENDER_FRAME_REGRESSED`. Source review found that the
processor compared the next block start against the prior materialized interval's
end rather than against the prior callback's `currentFrame`. A monotonic overlap
therefore produced a false clock-regression diagnosis.

D-066 separates `lastRenderFrame` from `expectedRenderFrame`. A true backward
clock and a non-advancing clock remain distinct fail-closed conditions. A monotonic
overlap is de-duplicated first-writer-wins only as compatibility for the observed
UA/device anomaly; it is not claimed as standards-conforming Web Audio behavior,
does not create duplicate samples or silence. The duplicate prefix cannot advance
readiness, while an unseen suffix is unique real PCM and may normally advance
sequence, cursor and readiness. D-065 remains authoritative for bounded forward gaps. Conforming tests
now separately cover non-zero initial frame, fixed 128- and 256-frame quanta,
suspend/resume without callbacks and valid empty-input topology; anomaly and
invalid-clock tests cover exact failure and zero late effects. The complete
physical response and next capture remain unproven until the corrected source is
hard-refreshed and rerun.

## 11. 2026-08-08 D-067 duplicate-frame watchdog correction

The next physical rerun completed recognition, Agent submission, authoritative
TTS and full user-heard “语音联调成功”, then the automatically overlapping capture
failed with exact `AUDIO_RENDER_FRAME_NOT_ADVANCED`. This is a positive physical
playout observation but not a complete P1/Gate pass because the next capture did
not remain active and no immutable receipt/evidence set was frozen.

D-067 replaces first-duplicate termination with interval de-duplication for at
most eight consecutive callbacks at the same `currentFrame`. An empty callback
cannot reserve samples, so same-frame real input may still populate an unseen
interval; an already materialized interval remains first-writer-wins and cannot
duplicate samples, silence, cursor or readiness. Clock advance resets the counter;
the ninth consecutive duplicate still fails as not-advanced, and any real backward
clock remains immediately terminal. Processor tests cover duplicate recovery,
empty-to-real and repeated-empty same-frame input, changed-quantum unseen suffix,
clock-advance reset and the exact watchdog boundary. The real
processor→Adapter→P1/downlink composition now renders three TTS frames, injects
the duplicate at final source teardown, proves exact ACK/receipt, retained capture
and continuous next uplink PCM, then separately proves both during-playout and
post-receipt terminal fencing. A processor that emits no callbacks at all is not
detected by this callback-count watchdog; existing startup/route deadlines remain
the liveness boundary. Current counts and physical state remain owned by
`STATUS.md`.

## 12. 2026-08-08 D-068 Product P1 capture-duration correction

Product P1 retains at most 1500 complete 20ms frames because final Batch STT needs
the whole utterance; uplink ACK does not release that recognition input. With no
VAD/EOT, silent PCM consumes the same bound. This is 30 seconds of materialized
audio rather than a wall-clock timer; audio captured during overlapping TTS counts
toward it. D-068 keeps this bounded privacy/memory contract and replaces the
old observer throw/generic `AUDIO_FRAME_CONSUMER_FAILED` with exact
`AUDIO_CAPTURE_DURATION_EXCEEDED` inside Product P1. The expired audio is discarded
before any fallible remote cleanup, with zero new Speech, Agent, Tool, Task,
history, receipt or cancel effect attributable to expiry; any previously accepted
render receipt remains unique. `Stop and recognize` at the exact 1500-frame
boundary remains a positive path.

The mounted UI now discloses the 30-second captured-audio capacity including overlapping
playout, explains the zero-submission expiry and disables restart from a terminal
failed owner until refresh. A retained Start singleflight also prevents two
same-tick attempts from allocating two successors while exact old-authority close
is pending; Session replacement, disconnect and unmount fence a retained Start.
Persistent close failure retains only the exact remote authority needed for retry,
not raw PCM. Unlimited retention, rolling frame eviction, automatic silence
recognition and ad-hoc amplitude VAD remain excluded; formal VAD/EOT or streaming
recognition is later Alpha/production work. Current physical observation, D-053
review, affected test counts and candidate/Gate state belong to [D94](D94_BROWSER_REFRESH_DUPLEX_RECOVERY_REVIEW_2026-08-08.md)
and [STATUS](STATUS.md), not this historical module review.
