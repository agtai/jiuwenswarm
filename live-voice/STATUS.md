# Live Voice current project status

> Updated: 2026-09-15 — management replacement is active; running services have not been redeployed.
> Default bootstrap reads only Project judgement and Current execution packet.
> Stop at Completion boundaries unless the task needs wider planning or acceptance.

## Project judgement

**PARTIAL — bounded repairs and user acceptance exist; the full product is not
feature complete or a newly accepted controlled candidate.**

Execution integration and management integration are separate: formal attempts
and Work use native Runner/TaskManager and Host Agent/Harness, while TaskStore,
PersistentTaskCore, WorkStore/WorkRuntime and Voice business coordination retain
substantial management code. Their replacement is **incomplete**. The current
[replacement audit](reviews/MANAGEMENT_REPLACEMENT_20260915.md) freezes the actual
paired source baseline and records concrete deletions, retained responsibilities
and evidence. Current submitted production changes have now received an explicitly
authorized independent module review (22 targeted checks, no confirmed differential
regression) and current paired installed-source verification. These close the
specific review/install evidence gaps, not overall management replacement. Prior packet-delivered wording does not close this scope.
The user accepted the deployed 09-15 session's tested behaviors; it proves
pre-dispatch cancellation, not human acceptance of running cancellation. Empty
diff success semantics remain undecided and do not block this audit.

The following earlier observations retain their original evidence boundaries;
their old repair/deployment permissions are superseded by the current packet.

Deployment of `57d3b29f18` exposed a 5,272-byte compiled adjustment instruction
against the 4,096-byte command bound. Its pending row blocked dispatch and P3
restart. The user's [dispatch recovery repair](reviews/ADJUSTMENT_DISPATCH_RECOVERY_20260910.md)
keeps bounded commands and resolves complete context from verified Store records
at execution. Derived validation failure settles only that adjustment. Existing
data-copy and local Git/file checks cover this repair; they do not establish
Provider/audio acceptance. Runtime readiness is recorded by the deployed contract.

The user's Native business prompt direction is implemented in session, receipt,
notification, correction and tool descriptions: prompt useful feedback, timely
tools and less repetition while preserving complete requirements and observed
business truth. [D-125](decisions/DECISIONS.md#d-125-unify-native-business-instructions-for-prompt-feedback-and-complete-execution)
owns the accepted policy. The user's subsequent deployed session exposed result
context leakage and separate query/notification delivery ownership. The current
repair isolates notification inputs and binds explicit queries to the same
played-result ledger; its [scope and evidence](reviews/NATIVE_RESULT_OWNERSHIP_20260910.md)
separate offline verification from the user's later model/audio acceptance.
The same session also exposed adjustment admission after executor cutoff and
failure omitted from spoken feedback. The authorized D-127 repair coordinates
cutoff/admission, continues late changes through existing successor Tasks, and
projects real saved results plus independent adjustment outcomes into Native.
Mini/server-vad-300 startup defaults
remain as recorded in [D-124](decisions/DECISIONS.md#d-124-default-new-live-voice-starts-to-realtime-mini-and-server-vad-300).
Other issue repair/classification remains deferred until comparison in another
environment. WebSocket congestion remains in the record: the user reports it did
not reproduce in another environment and requests no investigation or repair now.
The [Mini/VAD300 comparison record](evidence/MINI_VAD300_ENV_COMPARISON_20260910.md)
owns M01–M12, prepared configuration and already-executed automated evidence.
The [two user-session analysis](evidence/MINI_VAD300_USER_SESSIONS_20260910.md)
records the user's later VAD300 runs and adds M13–M17. Both file Tasks completed,
but neither meal adjustment applied; full-text delivery, artifact fidelity,
notification/query latency and diagnostic coverage observations remain open.
The old multi-second WebSocket input backlog was not observed in these runs;
that issue remains recorded for the user's cross-environment comparison.
After the user's clarification, further automated browser/voice/Agent verification
is stopped; those observations are not user acceptance. The historical
repair authorizations and next steps below do not reactivate paused work.

The user accepted audible tearing and the earlier browser first-sound metric
for the scoped repair. The later human recheck confirms request-specific early
feedback, a completed file Task and an acknowledged completion announcement.
The interruption/query-lock repairs passed the controlled real
browser/Provider/Agent recheck and the user's six-scenario
[human acceptance](evidence/INTERRUPTION_QUERY_HUMAN_ACCEPTANCE_20260909.md).
An earlier isolated Demo human run exposed Task worktree baseline mismatch,
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
the separate transport degradation was unresolved in that historical control;
the user's current environment observation and deferral apply above. The
broader integrated Task/audio boundary remains PARTIAL; the scoped interruption,
query and file-Task human journey is now accepted, without a stable-latency claim.
User-end to headphone-first-sound still requires the agreed recording calibration.
Full A/B/A2 control,
offline recovery, artifact quality and the complete physical/device matrix are
still unproved. Code-project authorization remains required; Work/projectless
support has been discussed, not implemented.

## Current execution packet

### Active management replacement (2026-09-15)

Continue [Task → Work → Host/Voice replacement](reviews/MANAGEMENT_REPLACEMENT_20260915.md),
with audit, refactoring, affected tests, documentation and local commits authorized.
The first bounded changes reuse the existing Task artifact reader, native Work
finalizer and Host Task presentation functions. The next batch removes Host
creation-spec construction and duplicate source helpers, reusing Core creation
preparation for Host selection and Core create/successor; this does not close the retained
management implementations. No pushes, history rewriting, service restart or
deployment; no private configuration or user-project edits. Preserve the
15-second prepared-response timeout and all existing voice/authorization policy.
New product semantics, security/authority changes and irreversible migrations
still require a concrete user decision. Broader management replacement remains
active. The status-query batch now shares the existing Store authority snapshot
between Core status and Host product facts, deleting Registry reread orchestration.
HostWorkService now owns Work submission and the retained execution closure;
Voice objects can be released while accepted Work continues. WorkStore management,
Voice context/presentation and wider business convergence remain unfinished.

### Previous session repair evidence (2026-09-14)

The user authorized the [three-stage repair](reviews/SESSION_REPAIR_20260914.md)
after testing session `web_1a0a051ff63_fca69639db63`: Task correctness, Voice
stability, then deployment verification and remaining faults. This supersedes
older pause/deployment exclusions for these specific repairs. Stage 1 scoped
checks pass; the deployed session confirms adjustment adoption but exposes an
empty-diff Task result failure. Its success semantics await a user decision.
Deployed audio analysis distinguishes prepared notification playback from
admission latency. Interruption feedback repair passes scoped checks and awaits
deployment; read-scope audit remains open. Multiple
local commits are authorized; final root-cause review must remove ineffective
or unnecessary fixes. Those diagnostics do not replace current management work.
No new full-product acceptance is claimed.
The deferred prepared-response timeout and buffering/latency policy remain
unchanged. No remote update or history rewrite is authorized.

### Continuation boundary


**Previous deep-integration packet (2026-09-13/14): bounded execution integration
delivered after D-128; management replacement remains incomplete.** The user explicitly
requires code-level native-capability audit, not directory/import ownership
claims. [Audit, changes and evidence](reviews/DEEP_INTEGRATION_20260913.md) owns
this packet, beginning at Host `948cfc7920fd35fdf0f4b9a476cd567bb4af9108` and SDK
`2d87926c0903fb9b130c8ca6fa8129d978168200`. No push, history
rewrite, deployment, private configuration or irreversible migration is authorized.

The scoped implementation enhances the native AgentCallbackManager for Task
checkpoint enforcement, removes dynamic Host checkpoint channels and obsolete
production Task/threaded-executor fixtures, removes the legacy scheduler carrier,
requires Host-owned Work producers, and shares new-session selections between
text and Voice. Controller/Team tasks, application delivery Task and Work are
not one management state machine; their cancellation, transaction and result
semantics differ. Work now directly uses HostWorkAgentExecutor and the existing
Harness, removing its Voice ConversationRuntime/Bridge allocation; SQLite result
recovery, replay suppression and cancellation cleanup checks cover this seam.
Work orchestration now also uses the existing Runner root and TaskManager; its
durable business outcome remains in WorkStore. Foreground round identity is owned
only by the Host Harness: Bridge holds bounded output-consumption permits, not a
second round reservation/commit ledger. Failed durable acceptance revokes the
unstarted round before speculative cleanup can yield. Targeted composition,
Host/SQLite/project and reconstruction checks cover these boundaries. Formal
Task attempts now execute directly in native TaskManager under the Host Runner
root; journal/effect/cleanup facts retain their distinct domain authority. Real
Git/D2 checks distinguish caller cancellation, native interruption and apply
settlement. The current audit records the final requirement-by-requirement delivery
judgement and retained semantic boundaries; it does not claim one mechanical
Controller/Team/Task/Work state machine or a newly accepted product candidate.
Current unified-input joint tests cover real SQLite Task creation/confirmation,
replay/conflict, project rejection, Voice close followed by completion, and
running cancellation while the original dialogue completes normally. These use
controlled model/authority/lower-Agent dependencies. The code-level Host/Voice
review now traces the retained lifecycle and state owners; current receipt identity
checks replace obsolete L0 oracles. Revoked task.create feedback and ACK history
have current replacement evidence. Under the user's [D-128 scope correction](decisions/DECISIONS.md#d-128-recovery-acceptance-does-not-require-replaying-ephemeral-agent-answers),
reconstruction must preserve business acceptance and truthful acknowledged history,
but is not required to redeliver an ephemeral P2 Agent answer. The proposed answer
persistence is not required and no longer blocks integration. Existing clarification
recovery remains supported; this is not a Native Realtime defect or new physical
product acceptance. See the current audit for the corrected recovery evidence.
The frontend lifecycle child places the formal Task reader under Host ChatPanel,
using the existing webClient and formalTaskStore. Voice consumes its snapshot
with a synchronous notification fence; it no longer constructs, closes or polls
the reader. Host-only/consumer-detach, polling, stale-session, UNKNOWN replay and
fail-closed target tests cover this boundary. This does not close historical
backend validation debt or the product candidate.

Project authority correspondence is now verified against D-120 and accepted R5
commit ae4b32331501: user edits are authorized snapshot inputs, not blanket
denials. Uncalled Host clean/managed checks and factory allocation are removed;
real root/HEAD/scope and Executor conflict protection remain. Five resolver/
factory checks and seven real-Git/SQLite snapshot, collision and recovery cases
pass. The SDK legacy proof API remains callable for package compatibility.

The current unified Host joint now covers generation interruption separately
from barge output fencing: exact foreground cancellation leaves the durable
Task running, duplicated interruption reuses the result, and injected Task
cancel scope has zero SQLite effects. Both Voice activations close before Task
completion and saved-result query. Three joint modes pass with real isolated
history/SQLite/Git and controlled lower Agents; no unplayed assistant history is
written. A fourth joint mode now adopts an accepted running adjustment through
the real SDK model callback rail, with one persisted request/application, one
Task/attempt, replay suppression, and the adjusted file/result after Voice close.
The lower Agent and its rail binding are controlled; this does not independently
prove Host adapter rail installation or Provider output. A fifth mode uses real
speech-service receipt issuance and Gateway claim conversion with critical-input
enabled. It verifies exact Voice task origin, altered-text receipt rejection and
forged-browser-claim stripping with zero durable/Agent effects, then completion
after Voice close. STT/media verification before receipt issuance is excluded.
The same mode reconnects with a new activation after completion and receives the
terminal event through Host text progress. Exact ACK advances only text
consumption; replay has zero further SQLite writes and Voice remains unread.
This is same-process reconnection with a controlled web sink, not browser render
or restart evidence. The old retired-entry spoken-notification journey remains
unclosed.

The current Python package pair passes clean tracked-source wheel builds and
temporary target installation; all loaded Host/SDK modules resolve to that
target, with installed Python bytes matching staged source and SDK constraints
matching metadata. [Exact-source evidence](evidence/DEEP_CURRENT_PAIR_20260914.json)
records the pair and wheel hashes. Existing third-party dependencies are reused;
frontend distribution, fresh dependency resolution and deployment are excluded.

The subsequent `.6` subscription batch removes Host's independent durable
consumer reader and reuses SDK TaskEventSubscription queue, authorization,
state snapshot and close management. Store consumer pages, ACK watermarks and
demand polling remain distinct from full-prefix/live-only modes; no Task or
consumer-state writes occur on reads or close. Existing large-page, retry,
recovery and delayed-ACK tests pass, with focused cross-thread close and grant
expiry checks. This closes that subscription-management seam, not the broader
Task/Work/Controller/Team convergence. The current paired installation evidence
is [the `.6` consumer pair](evidence/DEEP_CONSUMER_SUBSCRIPTION_PAIR_20260914.json).

The frozen-input recovery child now keeps server generation/context identity in
the existing Host journal, independently of model records. P3 and unified input
share a persisted sequence; conflicting unified input cannot advance it. Current
ingress, the live gate and final Task authority remain mandatory. Real SQLite/CR
recovery, changed Task/context sets, mixed-entry stale rejection, Native Registry
and Host lifetime regressions pass (144 tests in the scoped command). This does
not prove automatic CR-history restoration or new Provider/audio acceptance.
Registry retired P2 admission cleanup removes 126 production lines: an unwritten
ledger, uncalled reservation/preflight and constant-false recovery branch.
The selected registry group has 28 passes/27 failures both before and after;
isolated baseline comparison confirms the same failing test IDs. Old semantic
fixtures defaulting to dialogue remain validation debt, not a green claim.
The obsolete P3-off fixture is now replaced by real composition/SQLite/
confirmation checks: both a new request and a pending confirmation fail to
create or dispatch after P3 is disabled, and replay adds no model/Agent effect.
The paired enabled-create positive also passes. Current semantic-authority
denial and unknown-exception privacy checks pass. Real principal task.create
revocation after a pending confirmation now produces a tool-disabled failure
receipt with zero Task execution; protocol ACK writes the message once through
the actual Host history writer, and ordinary dialogue can continue. This replaces
the old business-denial fixture's unreachable error hook, with controlled Agent
output/ACK rather than physical playback evidence. No aggregate historical-suite
pass is claimed.
Module diagrams retain M4+M5 and M7+M9; accounting separates actual deletion,
retained/migrated code and native-file additions. Earlier ownership extraction
is recorded in [the preceding packet](reviews/TASK_WORK_UNIFICATION_20260913.md),
not proof of deep native unification.

User session `web_1a09c8505b1_6bce26af6cd4` verified Task creation, running
adjustment, pre-execution cancellation, query and Work execution. It did NOT
verify running cancellation; weather Work asked for a city. The single
NATIVE_PREPARED_RESPONSE_TIMEOUT (Realtime completion after the local 15-second
preparation deadline) remains explicitly deferred; no latency/buffer adjustment.
The old joint integration test still submits through retired p2.submit, so its
current unified-route journey and full product candidate remain PARTIAL.

**Preceding repair (2026-09-13):** restore Native notification sequencing after
Gateway authority expiry and serialize browser refresh with notification polling.
The [repair record](reviews/NOTIFICATION_SEQUENCE_RECOVERY_20260913.md) owns the
private Host cursor, exact Gateway restoration, concurrency review and checks.
Local redeployment preserves configured data/model settings; physical playback
after a long idle remains the user's validation, not full candidate acceptance.

**Completed integration (2026-09-13):** integrate the useful changes from the twelve
slimming commits into `hx/0912_livevoice`, preserving the official develop
Runtime and SDK baseline. Task/Work authority, durability and result services
belong to Host; production speech adapters belong to `channels/live_voice`.
The [integration record](reviews/SHARED_RUNTIME_INTEGRATION_20260913.md) owns
scope, selected source material, dependency boundaries and verification. The
user requests one new local commit after review. No new remote update or
physical Provider/browser acceptance is part of this code integration.

**Completed rebaseline (2026-09-12):** the official develop integration and local
redeployment are recorded in the [rebase record](reviews/DEVELOP_REBASE_20260912.md).
This does not reactivate deferred product work or imply full physical acceptance.

**Historical repair (2026-09-10):** repair and redeploy adjustment dispatch/startup
on baseline `57d3b29f18`, preserving this machine's configured project, data and
audio settings. The [recovery record](reviews/ADJUSTMENT_DISPATCH_RECOVERY_20260910.md)
owns the Tier 3 persisted-context/Executor seam, Tier 2 failure settlement,
verification and independent-review limitation. No queue deletion or manual
production data rewrite is authorized or needed by this repair.

**Preceding source packet (2026-09-10):** the user authorizes a compact root repair
of adjustment admission, late execution, final-state feedback and result-grounded
summaries. Baseline is `1750387a`, following the D-126 Work result repair.
[D-127](decisions/DECISIONS.md#d-127-coordinate-task-adjustments-with-cutoff-continuation-and-saved-result-truth)
owns the new behavior. Tier 3 covers the additive Store-owned queue, successor
transaction and the closed Task adjustment notification variant carried by the
existing Native observation channel. Tier 2 covers result projection, shared
playback ownership and interruption recovery. The
[repair review](reviews/NATIVE_RESULT_OWNERSHIP_20260910.md)
records implementation, checks and review limitations. No topic classifier,
response-text matching, second executor or second audio scheduler is introduced.
Full requirements, Task/Work authority, real receipt truth, prompt tool calls,
minimal acknowledgments and explicit recap requests remain as in D-125.
Model adherence and actual audio behavior require the user's later sessions.
The five previously reproduced projection-off context-refresh failures remain
outside this repair; scoped passes are not a full-green claim.

The earlier prompt source `c4755aa8` was deployed to the user's independent Mini
project and data directory on 2026-09-10. Its session
`web_1a08bd3359e_28137feb7a28` supplied this repair's evidence. This new source
packet was subsequently deployed as `57d3b29f18` on the current machine; the
dispatch/startup failure above came from that deployment. No new automated
browser/voice journey is part of this follow-up.

Private deployment preparation is complete. The dated
comparison record identifies the deployed source;
use the existing independent Mini project/data, speed 1.25, minimal reasoning,
local barge-in off and pinned AgentCore; server VAD has changed from 450 to 300 ms.
Preserve the original session/files. Apart from the explicitly authorized result
ownership repair above, other recorded issues, including WebSocket congestion,
remain deferred for cross-environment classification by the user. No further
automated browser/voice/Agent tests are requested after the clarification; retain
completed test evidence
without treating it as user acceptance. The two later user sessions were analyzed
from existing diagnostics, history, logs and persisted Task/Work/artifact snapshots;
no new browser/voice/Agent test, product change or service restart was performed.

The following paragraphs describe earlier packets, not current execution orders.

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
the [diagnostic extension record](reviews/DIAGNOSTIC_TIMING_EXTENSION_20260909.md).
The user-requested [endpoint frame follow-up](reviews/ENDPOINT_FRAME_DIAGNOSTICS_20260909.md)
adds per-frame input timings and passive heartbeat RTT for a new recording;
that historical run fixed VAD at 450 ms; Provider-internal timing remains unobserved.
The [calibration runbook](runbooks/TIMING_CALIBRATION.md) owns physical measurement.
The pinned AgentCore installation package is the user's explicit choice for this
workspace. Work/projectless, Task intent/result semantics item 4 and the broad
productization backlog remain excluded. The current Mini/VAD300 change is the
explicit exception to the earlier model/endpoint freeze.

Accepted repair behavior baseline: `b4aa449017`, gpt-realtime-2.1 / speed 1.25,
minimal / server-vad-450, AgentCore package 0.1.16+jiuwenswarm.responses2.
The user's six-scenario interruption/query acceptance passed on this deployment;
the [acceptance record](evidence/INTERRUPTION_QUERY_HUMAN_ACCEPTANCE_20260909.md)
owns its exact session, observed Agent selection and evidence limits. This closes
the two repairs' human recheck, not the paused wider backlog.
No change to a source installation, proxy, NIC or production endpoint is implied.
The results and rollback records own successful/failed journeys and timing
boundaries. Low-load and pre-fix controls are complete. The earlier proposed
event-loop/transport repairs and full adjustment/calibration follow-up are paused
under the current record-first decision. No stable-latency
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
  speech and played notification ACK; that earlier recheck did not exercise voice
  `task.status` or every failure/retry variant. Receipt arrival is not adjustment application
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
  baseline failures. The user's scoped human interruption/query and file-Task
  regression now passes; no full-suite or complete physical-matrix claim.
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
| Audio Device & browser I/O | Capture/playout, media wiring, exact-owner fencing, home entry and bounded starvation recovery; scoped human no-tearing and interruption acceptance | Complete headset continuity, listening/recovery, permission/device, AEC/NS/AGC, double-talk and loss/stop coverage; opt-in verified-headset profile still lacks the complete physical matrix |
| Speech Recognition | Streaming/batch finals, typed failure, bounded capture retry and lifetime repair | Long/paused speech, fallback/cancel, network/device/lifetime evidence; Cascade one-capture/one-final segmentation and post-EOT continuation semantics |
| Speech Synthesis | Streaming/batch TTS, response ownership/ACK, sample-credit prepared delivery and diagnostic-cost repair | Full physical long-answer continuity, underrun, pronunciation and stale-output proof; scoped accepted first-sound samples do not close the full boundary |
| Realtime Media | Dedicated transport, registration/rotation, bounded P2 pull, exact Native wake, transient observation-timeout recovery and interruption/query repairs with scoped human acceptance | Separate transport/input-saturation failures; full load/loss/order/corruption/reconnect coverage; local-origin voice gain unmeasured |
| Conversation Runtime | Commit/generation fencing, Stop/Exit, Cascade generation interruption, Native work independent of speech, response arbitration/ACK and unified source/successor retirement with scoped human acceptance | Broader combined physical listening/notification/Task races without old-audio revival or detached-Task miscontrol |
| Interaction Intelligence | Cascade semantic routing; Native typed business calls, bounded argument correction and unified session/receipt/notification instructions for minimal feedback and complete requests | Actual model adherence, repeated-feedback/merged-result delivery acceptance, full Native business-audio journey, endpoint/false-interruption evaluation and language/device scope |
| Agent Bridge and dialogue truth | Real Agent/file tools, independent read-only Native work, model/context binding, reply continuations, restart-unknown checkpoints and canonical heard history | Tool-parameter/receipt/result latency; literal intent/path drift, arithmetic, feasibility and brevity; retain failed workspace-query interpretation evidence |
| Task Control Core and Store | Canonical multi-Task state, durable commands/replay, exact targets/CAS and bounded adjustment delivery | Current concurrency/restart integration and full Task-operation coverage |
| Executor & Durability | Direct D0/D2 v2 admission/reconciliation, sealed results/checkpoints, source preservation and file-effect checks; real failure prevents partial apply in scoped cases | Model path drift/preservation conflicts, long-report convergence/length and full result/control acceptance; recovered originals do not erase failures; no D1/host-crash claim |
| Voice–Task Bridge | Unified committed semantics, exact local create/successor/adjust/cancel consent, target/revision checks, durable receipts and as-of adjustment observations | Literal target/intent, positive result queries and modification/generalization; update/reprioritize retain confirmation; pause/resume/provide-input remain unsupported |
| Integrated Web product experience | Right-panel Registry Tasks, operation refresh, passive Native work, model/text ownership, processing state and unplayed notification retry; scoped interruption/query, voice status and completed-file human journey accepted; running/cancelled Task voice notices intentionally silent | Broader interruption/recovery and notification failure/replay variants, A/B/A2/offline/unread/ACK/refresh and Work/projectless authority |
| Observability, benchmark and latency | Exact event/call joins, browser exports, same-clock operation breakdowns, real mixed ordinary/tool samples and connection-only IPv4 comparison | Physical end-to-end and Task/feedback targets; isolate remaining media/lock waits; received/generated audio is not heard history |
| Automated verification and acceptance | Focused regressions, independent repair reviews and limited real-model/audio/file evidence | Inherited Registry/Web failures, unique legacy-oracle migration and cumulative review/human acceptance; scoped passes are not a full-green claim |
| Configuration, code and document cleanup | Controlled launcher, semantic cutover, bounded removals, prompt/config isolation and recorded local-entry convention | Align launcher-generated local URLs, verify changed-origin state and complete reachability/retirement audit; keep private runtime data outside Git |
| Production operations | Privacy/preflight/observability foundations | Auth/tenancy, public deployment, operations, retention, security, compatibility and release support after separate scope |

## Current acceptance gates

| Gate | Missing proof / current conclusion |
|---|---|
| HARDCODE_RETIREMENT | PARTIAL: complete production reachability and unique-oracle migration remain open |
| SEMANTIC_AND_EXECUTION | PARTIAL: later create/adjust/file success coexists with retained path drift, preservation violations, missing/short artifacts and interpretation failures; recovery does not erase failed evidence |
| AUDIO_E2E_DIGITAL | PARTIAL: real Native PCM/Agent/Task and notification ACK evidence plus interruption/query repairs exist; separate transport/input-saturation failures and complete A/B/A2 remain unresolved |
| HUMAN_PHYSICAL_ACCEPTANCE | PARTIAL: user accepted scoped no-tearing, the earlier browser latency criterion and the six-scenario interruption/query/file-Task journey; earlier failures are retained and the complete physical matrix remains open |
| REGRESSION_AND_REVIEW | PARTIAL: inherited Registry/Web failures, affected migration and cumulative review remain open |

## Dependency route to feature complete

This route describes cumulative dependencies, not permission to resume paused
work. Follow the latest user scope before choosing the next item.

1. Build on the completed response-retirement/query-lifetime repairs and scoped
   human acceptance; address remaining transport, Task/feedback latency, literal intent/
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
