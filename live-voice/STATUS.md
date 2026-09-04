# Live Voice current project status

> Updated: 2026-09-04. This is the current judgement, capability/dependency model
> and product work scope. Verify Git and the actual runtime before resuming.
> Links are conditional evidence routes; they are not additional default reads.

## Project judgement

**PARTIAL — a rehearsal environment and bounded repairs exist; final delivery
and “only human acceptance remains” are not justified.**

- The real Cascade analysis → explicit delegation → one Task → sealed file path
  has scoped evidence. It does not prove complete A/B/A2 control, offline recovery,
  artifact correctness or this entire working candidate.
- Confirmed open result defects include arithmetic/cost consistency and exact
  literal filenames. New results relocate exact artifact paths to the retained
  project; old sealed results remain unchanged. Spoken
  feasibility and brevity also lack stable closure. See the
  [artifact evidence](evidence/ARTIFACT_QUALITY_REHEARSAL_CHECK_20260903.md).
- Recent delegation, capture-recovery and right-side Task presentation repairs
  are deployed with focused evidence. The bottom manual Registry control form
  is removed; “最近任务” reads the existing scoped Registry owner.
- Project-home Live Voice creates/binds an empty Session without a typed first
  message. Existing Sessions are reused. The backend still requires an authorized
  Code project; projectless/Work entry prompts for one. A current-source browser
  run reached listening, actual transcription, analysis without a Task and one
  direct delegation. Its output missed the intended two-result scenario, with
  a recorded speech/transcript ambiguity. Speaker acceptance, stable recovery
  and universal projectless startup remain open.
- Prior controlled-candidate PASS on `83fde5622`, imported Native/generation
  results and older module Gates are exact-source history. They do not grant
  this candidate acceptance. Historical details are conditional, not a work queue.

## Completion boundaries

These cumulative boundaries retain D-084's meanings.

| Boundary | Required outcome |
|---|---|
| Controlled product-readiness candidate | Affected automation and independent review plus one clean real microphone/speaker journey with truthful Task control, result and terminal notification on the same candidate. Does not prove all features. |
| Feature complete | Complete declared P1/P2/P3 capabilities, full Task-operation/generalization boundary, latency targets, configuration, retirement of legacy/Demo authority, broad verification, competitor-gap decisions and cross-module review. Only this triggers `develop` integration. |
| Productized candidate | Feature-complete source integrated; configuration, diagnostics, privacy and platform support hardened; cumulative product acceptance. |
| RC / Production ready | Production authentication/tenancy, deployment, SLO/retention, security, compatibility and release/rollback acceptance. Separate from the pre-`develop` boundary. |

For a boundary change, read D-084 in [decisions](decisions/DECISIONS.md) and the
relevant §§2, 4–5 of the [accepted design](architecture/FULL_SOLUTION_2026-07-30.md).
Dated schedules and carrier assumptions in that snapshot are historical.

## Current capability completion and full remaining scope

All rows are **PARTIAL** except Production operations (**NOT STARTED** as a
complete boundary). A historical module PASS does not close a broader row.
Validate disputed/touched facts against source as required by D-085; do not
repeat the old whole-project audit solely to resume a bounded task.

| Capability / module | Implemented boundary | Remaining / dependency |
|---|---|---|
| Audio Device & browser I/O | Capture/playout, dedicated media wiring, exact-owner lifecycle fencing; project-home listening/transcription observed | Stable physical listening/recovery and heard playback; permission/device coverage; AEC/NS/AGC, double-talk, loss/stop targets |
| Speech Recognition | Streaming/batch recognition, committed finals, typed stream failure, bounded capture-only retry and deployed scoped authority/resource lifetime repair | Lifetime repair has focused tests and independent review, not physical acceptance. Long/paused speech, fallback/cancel and device/network evidence remain open |
| Speech Synthesis | Streaming/batch TTS, response ownership and playback ACK | Current interrupted-answer/long-answer stability; first-audio, underrun, pronunciation and stale-output proof |
| Realtime Media | Dedicated transport, registration, rotation and bounded P2 notification pull | Backpressure/load, loss/reordering/corruption/reconnect and truthful recovery diagnostics |
| Conversation Runtime | Committed-input/generation fencing, Stop/Exit, playback/generation interruption, unanswered-input continuity, presentation/ACK ownership | Combined listening/notification/Task races on current source; no old audio revival or accidental detached-Task control |
| Interaction Intelligence | Model-based semantic route; opt-in Native engine source imported; Cascade remains the default route | Native through the current semantic business path, endpoint/false-interruption evaluation, broader language/device support |
| Agent Bridge and dialogue truth | Real Agent/file tools; current-turn/requirement context; canonical control/status presentation and scoped dialogue Task facts; failed spoken revision returns an honest short notice, not the unchecked draft | Independent review and real-model/physical verification of current repair; correct calculations, feasibility, literal filenames, result paths and concise speech |
| Task Control Core and Store | Canonical multi-Task authority, durable commands/replay, exact targets/CAS, bounded running-adjustment delivery | Current multi-Task/concurrency/restart integration and feature-complete operation coverage |
| Executor & Durability | Direct D0/D2 v2 profiles, admission, reconciliation, sealed results and generic adjustment checkpoints; dedicated no-memory rail repair; retained v1 records cannot authorize new v2 dispatch | Required independent review and real result/control acceptance; scope broader file-tool access outside checkout separately. Additional Executor/D1 capability needs its own packet; no D1 or generic host-crash claim |
| Voice–Task Bridge | Unified committed semantics, direct exact local creation/modification consent, scoped targets and requirement sources | Current modification/query real-model acceptance; full generalization and retirement audit; pause/resume/provide-input remain unsupported until a real primitive is accepted |
| Integrated Web product experience | Scoped Registry Tasks in the right panel, no bottom manual form; project-home Session allocation through microphone transcription; recovery/notification repairs | Stable startup/interruption/playback, A/B/A2 and offline/unread/ACK/refresh journey; projectless startup requires backend authority design |
| Observability, benchmark and latency | Correlated stage timings; deployed bounded content-free capture/upload/provider/VAD/playout/interruption diagnostics; historical bounded warm L0 evidence | Reproduce endpoint delay and ineffective voice interruption with the new trace; independent review, current first-audible baseline and declared SLO. Historical percentiles are not current gains |
| Automated verification and product acceptance | Focused module/regression checks and limited real-model/audio/file evidence | Unclassified Registry/Web failures, unique legacy-oracle migration, cumulative independent review and final human acceptance |
| Configuration, code and document cleanup | Controlled launcher, production semantic cutover, bounded legacy removals and scoped prompt/config isolation | Complete production reachability/retirement audit; remaining manifest rows; keep artifacts/private runtime data out of integration |
| Production operations | Privacy/preflight/observability foundations only | Authentication/tenancy, public deployment, operations, retention, security, compatibility and release support after separate scope |

## Current execution packet

### Speech failure precision diagnostics and local redeployment

The user authorized finer diagnostics after the latest two-turn acceptance run
hit streaming protocol failure and unsuccessful batch fallback. This is a Tier 2
Speech/Observability packet, not a speculative latency or protocol fix. See the
[precision diagnostic evidence](evidence/SPEECH_FAILURE_DIAGNOSTICS_20260904.md).

- Existing evidence confirms Provider-send accumulation and failure before a
  second final transcript. It does not identify the specific protocol trigger,
  timeout stage or the physical end-of-speech delay. Keep VAD 800 ms and startup
  lead 250 ms unchanged while reproducing.
- Passive diagnostics now separate send-lock, encoding and Socket send-await;
  parsed stop receipt, lock acquisition and publication; allowlisted protocol
  subcodes/state; HTTP connect/TLS/upload/response stages and outer deadline.
  The shared bounded sink stores no speech, raw Provider events or secrets.
- Focused and affected backend checks pass; complete manual diff review is the
  recorded substitute for an independent review that the incompatible local
  CLI could not run. Physical two-turn reproduction and browser export remain
  required; ineffective interruption and the misleading `activation` label are
  not claimed fixed by this diagnostic-only packet.
- Deployment is being prepared with the user's current isolated configuration.
  It now contains `deepseek-v4-flash`; a separate tool-free configured-model
  probe passed. Correction to the previous deployment claim: project/data and
  Speech credentials were retained, but the selected isolated dialogue config
  was then a template. Speech-only probes did not validate the dialogue model.
- The earlier truthful spoken-revision failure notice and browser
  capture/playout/interruption diagnostics remain included. Their
  [evidence and limits](evidence/SPOKEN_FALLBACK_AND_AUDIO_DIAGNOSTICS_20260904.md)
  remain applicable, including five pre-existing selected UI failures.
- No VAD/interruption policy, timeout increase, sentence TTS pipeline, Task
  behavior, protocol/schema, credential rewrite, public deployment or push.

### Retained consequences of earlier repairs

The D-113 streaming Speech lifetime repair passes its scoped tests and independent
review and is included in this deployment. It removes a cumulative identity quota while
retaining live-resource and exact-authority fences. Conditional evidence:
[bounded lifecycle repair](evidence/SPEECH_LIFECYCLE_REPAIR_20260904.md).

D-111/D-112 leave one model semantic decision, direct exact local modification
and canonical pending/applied/rejected Task status. Focused tests and bounded
configured-model probes pass; full execution/audio acceptance remains open.
The source is now deployed under the user's newer redeployment request. Read only the implicated
[Task adjustment evidence](evidence/TASK_ADJUSTMENT_TRUTH_REPAIR_20260904.md)
or [real Demo audit](evidence/DEMO_SESSION_AUDIT_20260903.md). Successful later
A2 creation does not prove the complete preservation journey.

Named Task notification wording and independent timestamps are implemented;
initial accepted no longer duplicates the direct receipt. Existing fallback
ACK/stale UI failures, combined physical recovery and cumulative review remain
open. Conditional evidence: [named notifications](evidence/NAMED_TASK_NOTIFICATIONS_20260903.md)
and [presentation repair](evidence/TASK_NOTIFICATION_PRESENTATION_REPAIR_20260903.md).
Keyword/fixture decisions, current-Task guesses and Demo bypasses must remain
outside production authority; protocol constants and live resource bounds are
not business hardcode. Wider reachability/retirement acceptance remains open.

### Current acceptance gates

| Gate | Current conclusion / missing proof |
|---|---|
| HARDCODE_RETIREMENT | PARTIAL: cutover/removals exist; complete reachability and unique-oracle migration review remain open |
| SEMANTIC_AND_EXECUTION | PARTIAL: scoped creation/continuity/execution pass; result quality and wider business behavior remain open |
| AUDIO_E2E_DIGITAL | PARTIAL: one real Cascade analysis/delegation/file path; complete A/B/A2, offline and non-travel journeys plus Native semantic-business audio remain unproved |
| HUMAN_PHYSICAL_ACCEPTANCE | FAIL / INCOMPLETE: later rehearsals exposed defects; complete current-source microphone/speaker journey has not passed |
| REGRESSION_AND_REVIEW | PARTIAL: scoped checks pass; inherited Registry/Web failures, affected migration and cumulative independent review remain open |

## Dependency route to feature complete

1. Fix confirmed current defects within their owners: result correctness and
   any reproduced startup/listening/interruption/notification failure. Preserve
   evidence of earlier failures; a short passing sample does not establish stability.
2. Complete minimal affected positive, rejection, stale/replay and isolation
   checks. Verify exact Task/Attempt state, actual files and actual audio for any
   claim that needs them. Triage remaining Registry/Web failures with evidence.
3. Prove the remaining analysis → A/B → adjust/query/cancel → offline completion
   → unread presentation/ACK → refresh deduplication → preserved A/new A2 journey.
   Include bounded negative speech, one other domain and both voice routes.
4. Close the production hardcode reachability audit, affected regressions and
   independent cumulative review; freeze a traceable candidate. Then complete
   the final operator microphone/speaker acceptance. Automated audio cannot
   substitute for physical listening, interruption and recovery.
5. For feature complete, also close the broader capability-table requirements,
   accepted competitor gaps, language/configuration/Executor generalization and
   latency targets. Optional upstream replacement proposals grant no deletion or
   migration credit until their own composition/migration acceptance.
6. Only after feature complete, inspect live remotes/refs and perform the
   authorized `develop` integration, productized acceptance and later RC/Production
   work. No historical branch or publication assumption authorizes a remote update.

## Verification and runtime truth

- Read actual source, runtime manifests, processes, flags and Task/lease state.
  The most recent rehearsal reports concern port 6175, but a reachable page or
  activated toolbar is not proof of microphone capture, Agent work or playback.
- Home entry evidence: [Session allocation and limits](evidence/HOME_SESSION_VOICE_START_20260903.md).
  Current listening/transcription, failed output and dedicated memory repair:
  [real-voice follow-up](evidence/PROJECT_HOME_REAL_VOICE_AND_MEMORY_REPAIR_20260903.md).
  Recent Task UI/delegation/capture evidence: [bounded repair](evidence/DELEGATION_AUDIO_RECENT_TASKS_REPAIR_20260903.md).
  These reports retain source hashes, commands and exclusions; no need to load
  all reports to perform an unrelated change.
- The source-bound [Cascade small-loop evidence](evidence/FOREGROUND_REQUIREMENT_CONTINUITY_REPAIR_20260903.md)
  and [artifact follow-up](evidence/ARTIFACT_QUALITY_REHEARSAL_CHECK_20260903.md)
  distinguish successful execution from failed business results.
- Source acceptance does not restore private credentials, provider settings,
  registered projects, device/browser state, Task data or network availability.
  Preserve unrelated sessions, Tasks/results and configuration; drain live work before an incompatible deployment.
- Use registered disposable no-remote projects and isolated data for execution
  tests. Keep raw audio/logs/configuration and generated build/cache files private.
- Documentation changes grant no product progress. For a disputed old claim,
  use the conditional [reference index](REFERENCE_INDEX.md), never its historical
  priorities as the current queue.
