# Live Voice timing diagnostic extension — 2026-09-09

## Owned boundary and acceptance

User request: expose timings for each observable conversation, business operation,
Agent/Task and presentation stage; add a last-user-sound to headphone-first-sound
record and verify the apparent conflict between perceived immediacy and the old
software metric. Baseline: f18a4fd55b3f90c381c08f14c319da1947754a86, isolated demo.

Tier 1: passive diagnostics and offline evidence analysis. Add bounded scalar
observations to the existing private diagnostic envelope; do not change media,
business, authority, persistence or Provider protocols. No raw audio/transcript,
credentials, arbitrary Provider payloads or device identifiers in normal logs.
Physical evidence is a separately supplied local recording with explicit sample
annotations. New diagnostic failures must not fail product operations.

Owned surfaces: browser capture/playout and media diagnostic hooks, the bounded
diagnostic sink, Native context/prepared-output/transport observations, existing
Agent/Task profiling gaps, offline timing report and affected tests/documentation.
The four product failures in the latest acceptance remain outside this change.
No automatic repeat of failed Task operations; no model or VAD tuning.

Acceptance: distinguish measured, estimated, unavailable, interrupted and skipped
stages; retain exact identity and clock provenance; never subtract independent
clocks or sum overlapping spans. Old exports must remain readable. Tests cover
silence, leading silence, unavailable/stale clocks, stop/identity changes, invalid
physical annotations and diagnostic failure isolation. Run affected frontend and
Python checks, complete diff review and a real browser diagnostic smoke test.
Physical measurement remains pending until a real recording is annotated.

## Existing coverage and gaps

| Module/path | Existing | Gap/extension |
| --- | --- | --- |
| Microphone/browser capture | Permission, resume, worklet load spans; sample cursor and audio context position; periodic RMS/frame counters | Numeric input-tail observation and mapping to browser performance clock; acquisition/DSP hardware latency remains unknown |
| Browser uplink/Gateway/Provider | Frame IDs, counts/ACKs, supply/queue diagnostics; Provider input boundaries | Expose local callback/queue timing and preserve correlation; one-way network time unavailable without bounded clock synchronization |
| Realtime response | EOT, response send/created, first PCM, argument stream, receipt and scheduler waits | Preserve first-feedback vs later receipt/result identity; pure model compute remains unavailable |
| Native context | Overall context and authority spans, current context hash | Task/history/projection subspans; received/local vs published/frozen context and target match facts |
| Admission/downlink | RPC/admission/supply, lock wait, socket open/attach, first frame send | Browser raw message callback timestamp vs owner acceptance; no cross-clock subtraction |
| Browser playout | PCM accepted, reserve, schedule, currentTime polling, stop and ACK | First signal position including leading silence, exact scheduled context time, getOutputTimestamp mapping, lateness of polling |
| Agent/model/tools | Session/config/round, model first chunk/total/gaps and tool IDs | Fill uncovered acquisition/execution stages; list nested spans separately from elapsed totals |
| Task execution | Accepted/running/terminal, worktree seed/create, effects/artifact/cleanup | Environment preparation is not model execution; retain task/attempt and failed-stage evidence |
| Notifications | Wait/prepare/terminal delivery/ACK, response scheduling conditions | Separate generation, foreground wait, predecessor playback, failure/retry; correlate original task source |
| Interruption/recovery | Stop requested/local fence/ACK, activation states | Retain terminal output kind and typed transport close classification; do not conflate cleanup cancellation with task failure |

## Endpoint semantics

1. Existing: browser EOT receipt to AudioContext start polling observation. This
   does not start at the user's last phoneme and does not end at acoustic output.
2. Software estimate: processed-input energy tail to output-device timestamp
   estimate. A content-free fixed-window energy measurement is not phoneme
   annotation; noise, AEC/NS/AGC and input clock/device delay limit its accuracy.
   Record method, thresholds, sample positions and unavailable fields. No fake
   universal uncertainty bound.
3. Physical: last user phoneme to first headphone acoustic answer in one shared
   recording sample clock, with both endpoint annotations and uncertainty. A
   system loopback is digital evidence and cannot be relabeled acoustic evidence.

Physical total covers the remaining microphone/input processing, tail upload,
Provider turn detection and response generation/transport, local admission/media
delivery, browser buffering/rendering, OS/USB/DAC/headphone output. Streaming
work completed while the user spoke is not added again. Intermediate software
spans are nested views, not a decomposition into exact acoustic components.

## Current metric recheck

In web_1a08581b5cc_0ef958b21a3e, “请用两句话介绍杭州”:
browser EOT→first PCM 888.6 ms; PCM→schedule 79.7 ms; schedule→start polling
34.8 ms; total 1003.1 ms. Ordinary one-sentence samples were 1320.1 and
1057.8 ms. These are observations from that run, not a universal latency or a
physical claim. Polling cannot by itself explain the whole roughly one-second
difference from the user's impression; compare a new matched acoustic sample.

## Physical recording preparation

The user confirmed a wired/USB headset and availability of recording conditions.
Use one continuous independent recording that clearly captures the user and the
headphone driver, or synchronized channels on one recorder. Keep the Live Voice
input/output setup unchanged, avoid clipping and record several short identified
turns. Retain the original file. Annotate end of the last phoneme and first
audible answer, not file ending, UI text, EOT or the first nonzero noise sample.
Record microphone distances/channel delay and annotation uncertainty. If only
digital loopback is supplied, report that boundary explicitly.

## Implemented boundary and review

Added scalar input-tail/capture clock, raw downlink callback, leading-signal,
scheduled/render/output-device observations; original reserve/playout/ACK/STOP
logic is unchanged. Native now records context read subspans, published/bound
context identities, request correlation/kind, prepared rejection structure and
closed transport classifications. Executor acquisition/stream spans retain the
existing action and cancellation boundaries.

The offline report has separate Gateway, browser, software-estimate and acoustic
views. It uses indexed exact identities and refuses ambiguous, legacy-missing,
foreign-clock and notification-to-EOT joins. Recording imports verify WAV/hash,
response/sample/channel identity and annotation/correction uncertainty before
attaching any measurement. The report and scalar sink remain content-free.
Scope review covered all changed production/report/test surfaces, privacy,
diagnostic exceptions, STOP-before-output and legacy compatibility.

## Verification record

- Frontend: audio diagnostics 11 passed; AudioIO 138 passed; dedicated media 33
  passed; Native interaction/P1 route 164 passed; full live-voice TypeScript/Vite
  build passed (existing bundle-size warning retained).
- Python diagnostic group: 76 passed. Broader affected module run: 515 passed,
  2 Windows symlink cases skipped, one new diagnostic assertion initially failed
  because Windows constructs ConnectionResetError from OSError(10054). The
  assertion now accepts the correct platform-specific type; affected diagnostic
  and report rerun passed. Final diagnostic/report/context group: 77 passed,
  including request identity, pause-before-output and nullable capture facts.
  No production exception handling changed for the platform assertion.
  The slow final checkpoint-cancel case also passed independently (19.36 s);
  broad run completed, not abandoned.
- Real Chrome/Web Audio smoke used the actual AudioIO adapter with a silent
  test-only destination. Observed injected leading silence: 100 ms; render poll
  overshoot: 9.333 ms; outputLatency: 32 ms; valid getOutputTimestamp mapping.
  This proves browser diagnostic integration only, not microphone/Provider/
  physical headphone acceptance. The first probe failed because its test-only
  Proxy lacked a native setter receiver; fixing that fixture made it pass.
- Existing user export and service log load into the extended offline report;
  missing historical correlation remains explicit. Default Git diff whitespace
  check passed. No dependency lockfile or acceptance-project changes intended.

Current boundary: software diagnostics implemented and checked; controlled
deployment verification is recorded in the private runtime handoff. Physical
calibration remains pending the user's actual recording. No software test or
synthetic waveform is credited as acoustic measurement. Operational instructions:
[timing calibration](../runbooks/TIMING_CALIBRATION.md).
