# Live Voice current project status

> Updated: 2026-09-05 (controlled Formal launcher default; physical acceptance open).
> Read the judgement and current packet first; other sections and links are conditional.
> Git and runtime evidence supply the actual source and deployment identity.

## Project judgement

**PARTIAL — a rehearsal environment and bounded repairs exist; final delivery
and “only human acceptance remains” are not justified.**

Real Cascade analysis → explicit delegation → one Task → sealed file has scoped
evidence. Complete A/B/A2 control, offline recovery, artifact correctness and a
clean current-source microphone/speaker journey remain unproved. Result arithmetic,
cost consistency, literal filenames, spoken feasibility and brevity remain open
in the [artifact evidence](evidence/ARTIFACT_QUALITY_REHEARSAL_CHECK_20260903.md).

Project-home entry can create/bind an empty Session and reach real transcription
and delegation. An authorized Code project is still required; projectless/Work
entry, reliable recovery and speaker acceptance remain open. Existing Tasks now
appear through the scoped Registry in the right panel. Old candidate PASS on
`83fde5622`, imported Native/generation samples and earlier Gates are exact-source
history, not acceptance of this candidate.

## Current execution packet

### Verified-headset interruption: implemented, physical acceptance open

- **Owners/risk:** Audio Device & I/O, Interaction Intelligence and Conversation
  Runtime; the bounded Tier-2 repair described in the
  [barge-in evidence](evidence/VAD_PLAYOUT_ACCEPTANCE_AND_BARGE_IN_DIAGNOSIS_20260904.md).
- **Implemented:** the explicit `verified-headset-aec-v1` profile uses reported
  AEC/NS/AGC and known far-end PCM to admit a content-free local speech candidate.
  Runtime pauses only the exact response at its unplayed cursor; Provider
  confirmation makes the stop permanent, otherwise playback resumes there.
  Local candidates cannot commit text or mutate Agent/Tool/Task authority.
- **Next proof:** physical one-second/five-second headset interruption, false
  pause recovery, recognition quality, no skipped/duplicated/revived audio and
  exact-target isolation on the identified candidate. Preserve all failed trials.
  Scoped automation/build evidence does not establish this physical acceptance.
- **Exclusions:** speaker, Bluetooth and unverified-device claims; model/processing
  changes; new Task authority or performance/SLO closure. Ordinary builds keep
  Provider-only interruption. VAD 800 ms / startup 250 ms are the accepted defaults.
- **Preparation:** verify actual services/assets and use [runbook §7.5](runbooks/E2E_RUNBOOK.md#75-当前受控-live-voice-启动与预演).
  The controlled `formal-web-validation` launcher now defaults generation-time
  interruption on; `-DisableGenerationInterruption` turns it off. The
  `hands-free-demo` profile remains off. Verify the actual deployment against the
  [default-change evidence](reviews/FORMAL_GENERATION_DEFAULT_20260905.md);
  a source default does not establish the current process or physical acceptance.

### Retained repair consequences

| Boundary | Current consequence and conditional evidence |
|---|---|
| Profiling | Browser/RPC/media/Speech/Agent/Task/notification timing, bounded browser export and offline reports have scoped tests/build/review and deployed samples. Use [runbook §7.7](runbooks/E2E_RUNBOOK.md#77-普通-demo-的性能记录与故障报告) for a rehearsal; [deployment evidence](evidence/DEMO_PROFILING_DEPLOYMENT_20260904.md) retains chronology. No latency improvement/SLO claim. |
| Speech lifetime | D-113 removes a cumulative identity quota while retaining exact authority/resource bounds; scoped tests/review and deployment are recorded in [lifecycle evidence](evidence/SPEECH_LIFECYCLE_REPAIR_20260904.md). Physical stability remains open. |
| Local Task adjustment | D-111/D-112 preserve one semantic decision, direct exact local consent and pending/applied/rejected truth; focused tests and configured-model probes pass. Full execution/audio acceptance remains open: [adjustment evidence](evidence/TASK_ADJUSTMENT_TRUTH_REPAIR_20260904.md). |
| Notification | Named Task wording/timestamps and presentation repairs exist; fallback ACK/stale UI and combined recovery remain open: [presentation evidence](evidence/TASK_NOTIFICATION_PRESENTATION_REPAIR_20260903.md). |
| Segmentation/dialogue | One-capture/one-final rejects later Provider items; whole-capture fallback can time out. Lossless post-EOT continuation needs accepted split/merge semantics; repeated greeting causality still needs reproduction: [diagnostics](evidence/SEGMENT_AND_DIALOGUE_DIAGNOSTICS_20260904.md). |

## Completion boundaries

These are the cumulative D-084 boundaries; consult that decision and the stable
§§2, 4–5 of the [accepted design](architecture/FULL_SOLUTION_2026-07-30.md) only
when changing a boundary. Dated schedules/carrier assumptions there are history.

| Boundary | Required outcome |
|---|---|
| Controlled product-readiness candidate | Applicable automation/review plus a clean real microphone/speaker journey proving truthful Task control, result and terminal notification on the same candidate, including the accepted current extension. |
| Feature complete | Full P1/P2/P3 capabilities and Task-operation/generalization scope, latency targets, configuration, retirement of legacy/Demo authority, broad verification, competitor-gap decisions and cross-module review. Only this triggers `develop` integration. |
| Productized candidate | Feature-complete source integrated; configuration, diagnostics, privacy and platform support hardened; cumulative product acceptance. |
| RC / Production ready | Production authentication/tenancy, deployment, SLO/retention, security, compatibility and release/rollback acceptance; separate from pre-`develop` completion. |

## Current capability completion and full remaining scope

All rows are PARTIAL except Production operations (NOT STARTED as a complete
boundary). D-085 requires checking disputed/touched facts, not repeating the
whole-project audit for every bounded task.

| Capability / module | Implemented boundary | Remaining / dependency |
|---|---|---|
| Audio Device & browser I/O | Capture/playout, media wiring, exact-owner fencing; home-entry transcription | Physical listening/recovery/playback, permission/device coverage, AEC/NS/AGC, double-talk and loss/stop targets |
| Speech Recognition | Streaming/batch finals, typed failure, bounded capture retry and lifetime repair | Long/paused speech, fallback/cancel, device/network and physical lifetime evidence |
| Speech Synthesis | Streaming/batch TTS, response ownership, playback ACK | Interrupted/long answers, first-audio, underrun, pronunciation and stale-output proof |
| Realtime Media | Dedicated transport, registration/rotation, bounded P2 pull | Backpressure/load, loss/order/corruption/reconnect and truthful recovery |
| Conversation Runtime | Commit/generation fencing, Stop/Exit, playout and flag-gated generation interruption, continuity/ACK ownership | Combined listening/notification/Task races, no old-audio revival or detached-Task miscontrol |
| Interaction Intelligence | Model semantic routing; opt-in Native source; Cascade default | Native through current business path, endpoint/false-interruption evaluation, language/device scope |
| Agent Bridge and dialogue truth | Real Agent/file tools, current requirements, canonical status, honest failed-revision notice | Required review/real-model/physical verification, arithmetic, feasibility, literal names/paths and concise speech |
| Task Control Core and Store | Canonical multi-Task state, durable commands/replay, exact targets/CAS, bounded adjustment delivery | Current concurrency/restart integration and full Task-operation coverage |
| Executor & Durability | Direct D0/D2 v2 admission/reconciliation, sealed results/checkpoints, dedicated memory repair; v1 cannot dispatch v2 | Required review and real result/control acceptance; outside-checkout files or additional Executor/D1 capability need separate scope; no D1/host-crash claim |
| Voice–Task Bridge | Unified committed semantics, direct exact local create/adjust consent, scoped targets/requirements | Real modification/query acceptance, generalization/retirement; pause/resume/provide-input remain unsupported |
| Integrated Web product experience | Right-panel Registry Tasks, project-home Session startup, recovery/notification repairs | Stable startup/interruption/playback, A/B/A2 and offline/unread/ACK/refresh; projectless backend authority |
| Observability, benchmark and latency | Scoped timing/error export, offline reports, tests/build/review and deployment samples | Current physical reproduction, interruption/first-audible baseline and SLOs; clock gaps/dropped data remain explicit |
| Automated verification and acceptance | Focused regressions and limited real-model/audio/file evidence | Unclassified Registry/Web failures, unique legacy-oracle migration, cumulative review/human acceptance |
| Configuration, code and document cleanup | Controlled launcher, semantic cutover, bounded removals and prompt/config isolation | Complete reachability/retirement audit and remaining manifest rows; keep private artifacts/runtime data out of integration |
| Production operations | Privacy/preflight/observability foundations | Auth/tenancy, public deployment, operations, retention, security, compatibility and release support after separate scope |

## Current acceptance gates

| Gate | Missing proof / current conclusion |
|---|---|
| HARDCODE_RETIREMENT | PARTIAL: complete production reachability and unique-oracle migration remain open |
| SEMANTIC_AND_EXECUTION | PARTIAL: scoped creation/continuity/execution pass; result quality and broader behavior remain open |
| AUDIO_E2E_DIGITAL | PARTIAL: complete A/B/A2, offline/non-travel and current Native business-audio journeys remain unproved |
| HUMAN_PHYSICAL_ACCEPTANCE | FAIL / INCOMPLETE: later rehearsals exposed defects; current cumulative microphone/speaker journey has not passed |
| REGRESSION_AND_REVIEW | PARTIAL: inherited Registry/Web failures, affected migration and cumulative review remain open |

## Dependency route to feature complete

1. Fix confirmed defects within their owners: results and reproduced startup,
   listening, interruption or notification failures; preserve failed evidence.
2. Complete affected positive/rejection/stale/replay/isolation checks and review.
   Verify authoritative Task/Attempt state, files and actual audio as applicable;
   classify remaining Registry/Web failures.
3. Prove the [current A/B/A2 journey](demo/PRODUCT_READINESS_SHOWCASE.md): analysis,
   separate delegation, adjustment/query/cancel, offline completion, unread/ACK/
   refresh and preserved A/new A2. Include bounded negatives, another domain and
   both voice routes for the wider declared boundary.
4. Close production hardcode reachability, affected regressions and cumulative
   review; freeze the candidate and complete required physical acceptance.
5. Close the remaining capability/generalization/configuration/latency and
   competitor-gap scope. Upstream replacement proposals do not grant retirement
   or migration credit without their own accepted checks.
6. Only at feature complete, perform separately authorized `develop` integration,
   then productized/RC/Production work. Remote updates need exact user approval.

## Verification and runtime truth

Use actual source, manifests, processes, flags, Task/lease state and the current
run's private environment labels. A reachable page or activated toolbar does not
prove capture, Agent execution or audible playback. Preserve unrelated sessions,
Tasks/results and configuration; drain live work before an incompatible deployment.
Use registered disposable no-remote projects and isolated data for execution
tests. Raw audio/logs/configuration and generated output remain private.

For a specific startup regression consult [home-entry evidence](evidence/HOME_SESSION_VOICE_START_20260903.md)
or [real-voice/memory follow-up](evidence/PROJECT_HOME_REAL_VOICE_AND_MEMORY_REPAIR_20260903.md).
For historical investigations use the [conditional index](REFERENCE_INDEX.md).
Documentation or skill-source changes grant no product/deployment credit.
