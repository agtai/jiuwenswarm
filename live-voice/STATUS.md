# Live Voice current project status

> Updated: 2026-09-09 — accepted Demo root-cause repair and verification scope.
> Default bootstrap reads only Project judgement and Current execution packet.
> Stop at Completion boundaries unless the task needs wider planning or acceptance.

## Project judgement

**PARTIAL — bounded repairs and user acceptance exist; the full product is not
feature complete or a newly accepted controlled candidate.**

The user accepted audible tearing and the earlier browser first-sound metric
for the scoped repair. The later human recheck confirms request-specific early
feedback, a completed file Task and an acknowledged completion announcement.
The interruption/query-lock repairs are deployed and passed a controlled real
browser/Provider/Agent recheck, with new human hearing acceptance still missing.
The isolated Demo's latest human run exposed Task worktree baseline mismatch,
stale business context binding, rejected prepared output and a later transport
failure. A subsequent calibration run exposed Native input saturation and a
14.607 s browser EOT-to-render interval. The user accepted root-cause repair
and verification of these failures. Executor byte/index preservation is committed
as `a4029b7c`; Native transport/lifetime, context publication and prepared-format
repairs are deployed as `9e9e5ebc` after scoped implementation review and checks.
The real browser/Provider/Agent recheck created and applied a file Task, preserved
all 37 original files, queried it, acknowledged its completion announcement and
continued after interruption. It also reproduced playback timeout and Native
input saturation; a follow-up creation/adjustment journey did not complete.
The [deployed repair results](reviews/DEMO_ROOT_CAUSE_REPAIR_RESULTS_20260909.md)
retain these mixed outcomes. Low-load controls produced both congested and
healthy connections. The requested [rollback control](reviews/REALTIME_COMMIT_CONTROL_20260909.md)
reproduced input saturation twice on `a8afe0c`, before the interruption/query
fixes; a separate baseline transport probe also reproduced long sends and TCP
retransmission without either changed module. The two commits' scoped checks
passed on their exact source. Local synchronous Code/SDK initialization also
blocks Task receipt delivery and remains unrepaired. The originating cause of
the separate transport degradation is still unresolved. The
integrated Task/audio journey remains PARTIAL, not a stable Demo acceptance.
User-end to headphone-first-sound still requires the agreed recording calibration.
Full A/B/A2 control,
offline recovery, artifact quality and the complete physical/device matrix are
still unproved. Code-project authorization remains required; Work/projectless
support has been discussed, not implemented.

## Current execution packet

### Continuation boundary

The user paused the broad six-hour push and requested discussion rather than
100% completion. The later three-fix implementation/recheck and interruption/
query-lock diagnosis are completed scopes with the limits below. Their remaining
items do not reactivate the whole backlog or historical parallel assignments.
The user accepted root-cause repairs and verification in the isolated Demo:
Native input accumulation/recovery, Task worktree byte fidelity, business context
publication/binding, prepared-response compatibility, and the real conversation/
Task journey, followed by Demo preparation. The
[repair execution record](reviews/DEMO_ROOT_CAUSE_REPAIRS_20260909.md) owns module
boundaries, risk and verification order. Completed passive diagnostics remain in
the [diagnostic extension record](reviews/DIAGNOSTIC_TIMING_EXTENSION_20260909.md);
the [calibration runbook](runbooks/TIMING_CALIBRATION.md) owns physical measurement.
The pinned AgentCore installation package is the user's explicit choice for this
workspace. Work/projectless, Task intent/result semantics item 4, model changes
and the broad productization backlog remain excluded.

Current deployed repair candidate: `9e9e5ebc5f`, gpt-realtime-2.1 / speed 1.25,
minimal / server-vad-450, AgentCore package 0.1.16+jiuwenswarm.responses2.
No change to a source installation, proxy, NIC or production endpoint is implied.
The results and rollback records own successful/failed journeys and timing
boundaries. Low-load and pre-fix controls are complete; next repair the isolated
local event-loop blockers and locate the separate transport degradation, finish
the voice adjustment journey, then complete the agreed human/physical calibration. No stable-latency
claim can be made from the successful short response alone.

Earlier controlled deployment evidence: `f85f0e33f2`, gpt-realtime-2.1, speed 1.25,
minimal reasoning, server-vad-450 and selected Agent deepseek-v4-flash. The
[interruption/query repair record](reviews/REALTIME_INTERRUPTION_QUERY_ROOT_CAUSE_20260908.md)
owns this browser/Provider/Agent recheck; the earlier
[human recheck](reviews/REALTIME_HUMAN_RECHECK_20260908.md) used `fff2fe15b7`.
These are dated evidence. Read the actual runtime contract/processes before
runtime work; later documentation HEAD is not the deployed product version.

### Current repair consequences

- **Three repairs implemented and deployed:** unplayed notification retry,
  transient business-observation timeout recovery, and truthful, request-specific
  tool preambles/earlier receipts. The
  [three-fix record](reviews/REALTIME_THREE_FIXES_20260908.md) owns tests, independent
  review and real Provider/Task checks. The later human recheck confirms early
  speech and played notification ACK; voice `task.status` and every failure/
  retry variant were not exercised. Receipt arrival is not adjustment application
  or completed work. Task intent/result semantics (item 4) remain excluded.
- **Interruption and query-lock code repaired:** the
  [root-cause probes and repair design](reviews/REALTIME_INTERRUPTION_QUERY_ROOT_CAUSE_20260908.md)
  reproduce delegate interruption fencing Conversation Runtime without cancelling
  the Native receiver, and P3 queries holding the Registry lock across external
  reads. One human interruption closed media; queries also delayed audio.
  Commits `d1beb113` and `5cd46346` synchronize receive/output retirement and give
  queries an owned lifetime outside the shared voice lock. Focused checks,
  independent review, controlled deployment and real browser recheck passed:
  interrupted receipt, subsequent responses, real Agent read_file and parallel
  task.list succeeded; 1304 audio admissions waited at most 0.244 ms for the
  Registry lock. Broad comparison retains the same 55 Registry and 7 Semantic
  baseline failures. Human regression remains pending; no full-suite or physical
  acceptance claim.
- **Local connection diagnosis and entry convention recorded:** use the
  [127.0.0.1 local entry](runbooks/E2E_RUNBOOK.md#local-entry-origin).
  Browser probes isolate roughly 300 ms of localhost IPv6-to-IPv4 fallback.
  The launcher now generates 127.0.0.1 local browser/origin links. Its allowed-host
  compatibility list is unchanged; PowerShell parsing passed.
  The later repair recheck used a 127.0.0.1 page and same-origin media: six downlink
  connections opened in 6.6–27.7 ms. This is transport evidence; an overall voice
  latency A/B or physical improvement claim remains unmeasured.

### Measurement and acceptance limits

The [bilingual operation breakdown](reviews/REALTIME_OPERATION_TIMING_BREAKDOWN_20260908.md)
owns per-turn/audio/tool/notification timings. Browser first sound means EOT
receipt to AudioContext playback-start observation, excluding pre-EOT acoustic/
VAD delay and physical device output. Gateway first PCM/downlink, browser start,
Task receipt, applied adjustment, finished artifact and playback ACK are separate
endpoints; do not subtract clocks across processes.

The earlier human run's median was 1.199 s and the user accepted that criterion.
The later five ordinary-chat samples have median 1.755 s, range 1.287–2.430 s;
they do not establish a stable 1.2 s or a regression by themselves. The old
3.3 s baseline was diagnostic, not a hearing estimate, and still lacks aligned
endpoints/sample selection for a strict improvement claim. No new acoustic
acceptance or pure-model-compute measurement is implied.

Earlier execution packets, model settings and test totals are conditional
[repair references](REFERENCE_INDEX.md#september-repair-records), not current work.
Failed evidence and broader requirements remain in their owning records.

## Completion boundaries

These are the cumulative D-084 boundaries. Consult that decision and the stable
§§2, 4–5 of the [accepted design](architecture/FULL_SOLUTION_2026-07-30.md) only
when changing a boundary; dated schedules/carrier assumptions there are history.

| Boundary | Required outcome |
|---|---|
| Controlled product-readiness candidate | Applicable automation/review plus a clean real microphone/speaker journey proving truthful Task control, result and terminal notification on the same candidate, including the accepted current extension. |
| Feature complete | Full P1/P2/P3 capabilities and Task-operation/generalization scope, latency targets, configuration, retirement of legacy/Demo authority, broad verification, competitor-gap decisions and cross-module review. Only this triggers `develop` integration. |
| Productized candidate | Feature-complete source integrated; configuration, diagnostics, privacy and platform support hardened; cumulative product acceptance. |
| RC / Production ready | Production authentication/tenancy, deployment, SLO/retention, security, compatibility and release/rollback acceptance; separate from pre-`develop` completion. |

## Current capability completion and full remaining scope

All rows remain PARTIAL except Production operations (NOT STARTED as a complete
boundary). This is the cumulative scope, not the active task queue. D-085 requires
checking disputed/touched source facts; this documentation pass is not a fresh
15-module audit and grants no new completion credit.

| Capability / module | Implemented boundary | Remaining / dependency |
|---|---|---|
| Audio Device & browser I/O | Capture/playout, media wiring, exact-owner fencing, home entry and bounded starvation recovery; scoped human no-tearing acceptance | Complete headset continuity, listening/recovery, permission/device, AEC/NS/AGC, double-talk and loss/stop coverage; opt-in verified-headset interruption still needs physical evidence |
| Speech Recognition | Streaming/batch finals, typed failure, bounded capture retry and lifetime repair | Long/paused speech, fallback/cancel, network/device/lifetime evidence; Cascade one-capture/one-final segmentation and post-EOT continuation semantics |
| Speech Synthesis | Streaming/batch TTS, response ownership/ACK, sample-credit prepared delivery and diagnostic-cost repair | Full physical long-answer continuity, underrun, pronunciation and stale-output proof; scoped accepted first-sound samples do not close the full boundary |
| Realtime Media | Dedicated transport, registration/rotation, bounded P2 pull, exact Native wake and transient observation-timeout recovery | Delegate-interruption late-frame failure and query-held admission delays; full load/loss/order/corruption/reconnect coverage; local-origin voice gain unmeasured |
| Conversation Runtime | Commit/generation fencing, Stop/Exit, Cascade generation interruption, Native work independent of speech, response arbitration/ACK | Unify exact source/successor retirement; combined physical listening/notification/Task races without old-audio revival or detached-Task miscontrol |
| Interaction Intelligence | Cascade semantic routing; Native typed business calls, bounded argument correction and truthful request-specific preambles | Full Native business-audio journey, endpoint/false-interruption evaluation, language/device scope |
| Agent Bridge and dialogue truth | Real Agent/file tools, independent read-only Native work, model/context binding, reply continuations, restart-unknown checkpoints and canonical heard history | Tool-parameter/receipt/result latency; literal intent/path drift, arithmetic, feasibility and brevity; retain failed workspace-query interpretation evidence |
| Task Control Core and Store | Canonical multi-Task state, durable commands/replay, exact targets/CAS and bounded adjustment delivery | Current concurrency/restart integration and full Task-operation coverage |
| Executor & Durability | Direct D0/D2 v2 admission/reconciliation, sealed results/checkpoints, source preservation and file-effect checks; real failure prevents partial apply in scoped cases | Model path drift/preservation conflicts, long-report convergence/length and full result/control acceptance; recovered originals do not erase failures; no D1/host-crash claim |
| Voice–Task Bridge | Unified committed semantics, exact local create/successor/adjust/cancel consent, target/revision checks, durable receipts and as-of adjustment observations | Literal target/intent, positive result queries and modification/generalization; update/reprioritize retain confirmation; pause/resume/provide-input remain unsupported |
| Integrated Web product experience | Right-panel Registry Tasks, operation refresh, passive Native work, model/text ownership, processing state and unplayed notification retry; human completion voice ACK observed; running/cancelled Task voice notices intentionally silent | Stable interruption recovery, all notification failure/replay variants, voice status-query acceptance, A/B/A2/offline/unread/ACK/refresh and Work/projectless authority |
| Observability, benchmark and latency | Exact event/call joins, browser exports, same-clock operation breakdowns, real mixed ordinary/tool samples and connection-only IPv4 comparison | Physical end-to-end and Task/feedback targets; isolate remaining media/lock waits; received/generated audio is not heard history |
| Automated verification and acceptance | Focused regressions, independent repair reviews and limited real-model/audio/file evidence | Inherited Registry/Web failures, unique legacy-oracle migration and cumulative review/human acceptance; scoped passes are not a full-green claim |
| Configuration, code and document cleanup | Controlled launcher, semantic cutover, bounded removals, prompt/config isolation and recorded local-entry convention | Align launcher-generated local URLs, verify changed-origin state and complete reachability/retirement audit; keep private runtime data outside Git |
| Production operations | Privacy/preflight/observability foundations | Auth/tenancy, public deployment, operations, retention, security, compatibility and release support after separate scope |

## Current acceptance gates

| Gate | Missing proof / current conclusion |
|---|---|
| HARDCODE_RETIREMENT | PARTIAL: complete production reachability and unique-oracle migration remain open |
| SEMANTIC_AND_EXECUTION | PARTIAL: later create/adjust/file success coexists with retained path drift, preservation violations, missing/short artifacts and interpretation failures; recovery does not erase failed evidence |
| AUDIO_E2E_DIGITAL | PARTIAL: real Native PCM/Agent/Task and notification ACK evidence exists; interrupted confirmation/recovery and query-held supply gaps remain, with complete A/B/A2 unproved |
| HUMAN_PHYSICAL_ACCEPTANCE | PARTIAL: user accepted scoped no-tearing and the earlier browser latency criterion; later early feedback and completion announcement are observed, while one confirmation/interruption failed and the complete physical matrix remains open |
| REGRESSION_AND_REVIEW | PARTIAL: inherited Registry/Web failures, affected migration and cumulative review remain open |

## Dependency route to feature complete

This route describes cumulative dependencies, not permission to resume paused
work. Follow the latest user scope before choosing the next item.

1. Verify and repair the touched source owners: response retirement and query
   lifetime/locking, local connection delay, Task/feedback latency, literal intent/
   file preservation and report convergence/length. Preserve failed originals and
   separately label recovery evidence; item 4 stays outside the current repair.
2. Complete affected positive/rejection/stale/replay/isolation checks and review.
   Verify authoritative Task/Attempt state, files and audio as applicable, and
   classify remaining Registry/Web failures. Bind any next runtime trial to the
   actual candidate; do not repeat already completed repairs from older packets.
3. Prove the [current A/B/A2 journey](demo/PRODUCT_READINESS_SHOWCASE.md): analysis,
   separate delegation, adjustment/query/cancel, offline completion, unread/ACK/
   refresh and preserved A/new A2. Include bounded negatives, another domain and
   both voice routes for the wider declared boundary.
4. Close hardcode reachability, affected regressions and cumulative review; freeze
   the candidate and complete required physical acceptance.
5. Close remaining capability/generalization/configuration/latency and competitor
   gaps. Provider research alone grants no replacement or migration credit.
6. Only at feature complete, perform separately authorized `develop` integration,
   then productized/RC/Production work. Remote updates need exact user approval.

## Verification and runtime truth

Root [TESTING.md](../TESTING.md) owns checks/review; the
[runbook](runbooks/E2E_RUNBOOK.md#75-当前受控-live-voice-启动与预演) owns startup.
Verify source, runtime manifests/processes, flags and Task/lease state. Preserve
unrelated sessions, Tasks/results, configuration and the selected Agent; drain
live work before incompatible deployment. Execution tests use registered
disposable no-remote projects and isolated data.

A reachable page or toolbar does not prove capture, Agent execution or playback.
Private configuration, credentials, browser permissions, raw audio/logs and
generated artifacts are not restored by Git. Another machine needs the updated
repository documents plus its own runtime verification. Documentation changes
grant no product/deployment credit; use the [conditional index](REFERENCE_INDEX.md)
only for the implicated historical or forensic boundary.
