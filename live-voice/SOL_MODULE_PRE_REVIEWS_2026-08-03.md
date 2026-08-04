# Live Voice Sol module pre-review record: 2026-08-03

> Frozen design record. This file preserves the D-031, ACG-1, CR-A, SR-A/SS-A, and TC-A Sol pre-reviews that originally lived in `STATUS.md`. It is not the current execution queue or mutable project state. D-046 and the current [STATUS.md](STATUS.md) supersede its former D-031-first ordering and universal D-032 operating process; blank execution/result cells remain historical evidence that implementation had not started when the record was frozen.
> D-052 supersedes the non-Sol owner/allocation language below, and D-055 supersedes Windows/X-WIN carrier language. The original design/oracles remain historical inputs; current execution, carrier and closure come only from decisions, STATUS and the actual diff/tests.

## Git and release identity

- Development branch: `hx/0803_live_voice`.
- Shared remote branch: `agtai/hx/0803_live_voice`.
- V0 immutable Released / Frozen baseline: `ee2896a4afb186e693c720476b6de10797e66f72`.
- V0 release-evidence commit on this branch: `a42668f8`.
- Original Post-V0 foundation tip: `4a3e11f1`; integrated by merge commit `ac988b85` after the V0 evidence commit.
- D-039 ASR-fidelity direction: `e539dd23`.
- D-041 model allocation and D-031 pre-review were consolidated into the current planning record; their original ordering is historical.
- The cleaned history intentionally excludes the unrelated commits identified during the 2026-08-03 audit. Runtime equivalence and ancestry are verified before push; do not reintroduce old merge/noise commits merely to reproduce the former log.

## Historical checkpoint milestone (not current status)

### V0: RELEASED / FROZEN

V0 is a controlled Web vertical slice, not the production release. It has verified:

- real microphone input through Browser Speech;
- committed final transcript sent once to the real JiuwenSwarm Agent;
- real tool execution and truthful tool result;
- final answer rendered and spoken once by browser TTS;
- automatic return to listening;
- the documented thinking/tool supplement behavior and speaking-time stop-then-new-turn behavior;
- Gate 0–6, including normal turns, staged interruption, 21m58s soak, degradation, three consecutive showcase runs, and equivalent clean-environment recovery.

The immutable evidence is [V0_20260802_ee2896a4.md](evidence/V0_20260802_ee2896a4.md). Post-V0 code is not part of that V0 capability claim.

### Post-V0 foundation: INTEGRATED / PARTIAL

The original foundation commits are preserved through `4a3e11f1`. The branch contains backend and Web foundations for task identity, idempotent request handling, execution target/provenance, schedule-backed task operations, frontend task client/adapter/bridge, task projection/card behavior, streaming speech support, feature flags, and focused tests.

These foundations are not full P3 and are not production closure. In particular, a foundation type, adapter, or card does not prove durable task lifecycle, cross-process exactly-once behavior, production authentication, or cancellation fencing.

## Historical design and execution queue at the checkpoint

- At the original D-041 checkpoint, D-031 was treated as the next implementation slice and its source-level pre-review was complete. D-046 now supersedes that ordering: D-031 is a Day 5/Day 7 legacy-Adapter decision, not the unconditional first task.
- The blank `D031-B1..B4` and `D031-A2` cells below record the proposed handoff at that checkpoint. They are historical, not current authorization or an execution queue.
- The design batch remains useful input: D-042 accepted the shared [Architecture Contract Gate](architecture/ARCHITECTURE_CONTRACT_GATE_V1.md); D-043 froze `CR-A`; D-044 froze P1 `SR-A/SS-A`; D-045 froze P3α `TC-A`. Their blank non-Sol tables do not represent implementation or closure.
- The historical order was D-031 followed by `ACG-B1..B4` and dependent packages. The current queue must be re-sliced under D-046/D-047 around the ACG critical kernel, cumulative Integrated Demo, parallel tracks, and frozen temporary authority; overlapping ACG packages must be grouped or narrowed before execution.
- These designs are inputs to current risk-tier review, not an automatic requirement to run complete D-032 on every `*-A/B/C` package. Current execution readiness and applicable review depth come from `STATUS.md`, D-046, D-047, and a new Sol handoff; semantic ambiguity still returns to Sol.

### Module test closure: D-031 poll-backed Live Voice task monitor

- Closure state: `PARTIAL — PRE-REVIEW CONTENT COMPLETE / IMPLEMENTATION NOT STARTED / POST-REVIEW MISSING`.
- Sol sign-off: GPT-5.6 Sol completed the source-level D-032 pre-review on 2026-08-03. This sign-off freezes the intended semantics and test oracles below; it is not an implementation, test-pass, commit, push, or release sign-off.
- Stage / decision / requirement sources: Post-V0 Foundation Alpha; D-026 through D-034, D-039, and D-041; [POST_V0_DELIVERY_ROADMAP.md](roadmap/POST_V0_DELIVERY_ROADMAP.md) §3.1 and §7.2–7.3; [FULL_SOLUTION_2026-07-30.md](architecture/FULL_SOLUTION_2026-07-30.md) P1/P2/P3 contracts and invariants.
- Baseline identity: branch `hx/0803_live_voice`, baseline `5c7ac8a0a926ee1f3d0d33281e9685efa4759a5b`, upstream `origin/hx/0803_live_voice`, ahead/behind `0/0` at pre-review start. The only expected worktree changes before this checkpoint were documentation for D-041 in this file and `decisions/DECISIONS.md`; no D-031 code or tests have been changed.
- Evidence boundary: prior focused Foundation results remain in the Verification ledger below. This pre-review session found that frontend `node_modules` and a Python environment containing pytest are not restored on the current machine, so failed attempts to invoke those runners are not represented as new pass evidence. D-031 cannot become `CLOSED` until all final commands are rerun on an immutable candidate containing every behavior input.

#### Module definition and ownership

The module is one narrow page-memory task projection and polling controller for the single current Live Voice task, plus at most one directly related terminal predecessor created by replace A→B. It begins only after the existing Bridge has obtained or exactly reconciled a real task ID and a complete monitoring identity. It immediately observes backend facts without blocking microphone recovery or unrelated Chat/Agent turns, updates a task card, and may emit one safely arbitrated terminal fact notification.

The semantic unit is not defined by one file. Its expected code scope is:

- a new pure, injected-clock `liveVoiceTaskMonitor.ts` state machine;
- shared strict task observation/provenance types and parsing used by both the monitor and `liveVoiceTaskBridge.ts` so UI and later task commands cannot diverge;
- `liveVoiceTaskAdapter.ts` projection/announcement selectors;
- `useLiveVoiceDemo.ts` lifecycle ownership and TTS arbitration;
- explicit `isConnected` wiring from `App.tsx` through `ChatPanel/index.tsx` to the hook;
- `LiveVoiceDemoBar.tsx`/CSS and `zh.json`/`en.json` for monitor health, optional facts, and separate A/B records;
- the minimal backend/service contract normalization needed to attach the same complete task provenance to fresh idempotent `schedule.run` task responses that replay/status/list already expose, and to distinguish stable `TASK_NOT_FOUND` from task-store unavailability instead of parsing localized error text;
- focused frontend/backend tests and the frontend test script. `liveVoiceTaskClient.ts` extends only the read methods with request options/`AbortSignal`, because the current two-argument task request type cannot cancel an unresolved status/list read during disconnect, command takeover, or teardown. Run/cancel semantics remain unchanged.

Authority and ownership are fixed as follows:

- AutoHarness TaskStore as returned by scoped `schedule.status` and exact-key `schedule.list` is the task fact source. The monitor never invents task IDs, status, progress, error, result, outcome, or provenance.
- `LiveVoiceTaskBridge` remains command identity/mutation authority. A validated monitor observation must be applied back to the same Bridge-owned current task as well as projected to UI; a UI-only status update is forbidden because it would leave later create/cancel/replace decisions stale.
- The monitor owns timer, retry, connection pause/reconcile, generation fence, current observation health, and the asynchronous terminal-notification latch. It does not own Chat history, Agent turns, chat processing state, task creation, cancellation, or backend task mutation.
- One hook instance owns one monitor. Its immutable context tuple is `(origin session ID, execution-target key, Bridge object identity, task ID, command ID, monitor generation)`. Any differing element makes an asynchronous result stale.
- The projection may retain two records only for a validated replace relation: A as the real cancelled/otherwise terminal predecessor and B as current successor. Only B is polled. General task history and arbitrary multi-task polling are excluded.

Inputs are a validated Bridge task/result, connection state, current session/target/Bridge identity, feature/Live Voice state, chat processing/thinking state, microphone/capture state, core/TTS snapshot, and injected clock/scheduler/gateway. Outputs are a truthful monitor snapshot/task activity, read-only `status/list` calls, timer scheduling/cancellation, and an optional terminal fact notification request. The monitor must never call `schedule.run`, `schedule.cancel`, Chat send/interrupt, `chatStore` message mutation, or chat `isProcessing` mutation.

#### Required backend observation contract

A successful observation is an object with all of these required facts:

- non-empty `task_id` exactly equal to the expected task;
- a present non-empty string `status`; raw spelling is preserved while normalization selects cadence/terminal behavior;
- an `execution_target` object consistent with both the original accepted task and current gateway owner. `project_dir` and `origin_session_id` must remain known and exact; `project_id=unknown` is accepted only when the captured owner also had no project ID; `origin_channel_id` must agree with stored provenance;
- a `provenance` object with exact owner scope, `origin_namespace=live_voice`, `idempotency_key` equal to the Bridge command ID, `legacy_unscoped=false`, and `access=authorized`. An empty but originally captured `app_id` remains an exact value, not a wildcard.

`progress` and `last_error` are optional facts. Missing `progress`, a valid progress object without a non-empty `summary`, or missing/empty `last_error` displays `unknown`. A present non-object `progress` or present non-string `last_error` is malformed input and cannot replace the prior projection. Unknown extra fields are ignored. The monitor does not translate stage data into percentages or a versioned WorkProgress outcome.

Current raw status normalization remains:

| Raw family | Projection | Terminal | Notification wording |
|---|---|---:|---|
| `accepted/pending/queued/scheduled` | `queued` | no | none |
| `running/executing/in_progress/processing/started` | `running` | no | none |
| `success/succeeded/completed/complete/done/pr_created/completed_without_pr` | `success` | yes | neutral task ID + raw status fact; no invented natural-language result |
| `failed/failure/error` | `failed` | yes | neutral non-success task ID + raw status fact |
| `cancelled/canceled` | `cancelled` | yes | neutral cancellation fact |
| `skipped/needs_human/deleted` | `unknown` with preserved raw | yes | neutral non-success raw status only; never a success phrase |
| any other non-empty string | `unknown` with preserved raw | no | none; continue at the unknown cadence |

Unknown future values, including a future value that merely sounds terminal, remain non-terminal until a contract decision recognizes them. `deleted` is the one accepted tombstone exception. Backend terminal sets and frontend normalization must have a contract test so a later backend status addition cannot silently become terminal speech.

Response/error classification is also fixed:

- a rejected RPC is transient only when the existing WebClient error marks `retriable=true` (currently `REQUEST_TIMEOUT`, `WS_DISCONNECTED`, or `WS_NOT_READY`) or an injected gateway classifies the equivalent read failure as retriable. Preserve the last trusted projection and retry the same read operation with backoff only while the context remains current and connected. A non-retriable outer/server/protocol/abort error is a permanent adapter error and stops; error-message text is not a retry oracle;
- `TASK_NOT_FOUND`, or an exact-key reconnect list containing zero records, becomes a visible `missing` condition: preserve last trusted facts, stop automatic polling and all task mutation, and do not announce success;
- `TASK_SCOPE_MISMATCH`, `TASK_PROJECT_MISMATCH`, denied/legacy/mismatched provenance, or mismatched target becomes a visible isolation/adapter error: expose no foreign facts, preserve the local trusted projection, and stop;
- any other payload containing `error` is a visible business error: it cannot update status even when the same payload also contains status-like fields, and automatic polling stops pending explicit user action/review;
- non-object payload, missing/empty/non-string required fields, mismatched `task_id`, malformed required target/provenance, malformed present optional fields, or exact-key list conflict is an adapter error: preserve the previous projection, perform no announcement or mutation, cancel timers, and stop;
- `schedule.status` remains the normal read. `schedule.list` is allowed only during same-page exact-command reconciliation, never as an unscoped scan and never as a substitute for a missing durable journal.

The backend change in this slice is deliberately limited: every fresh idempotent `schedule.run` response that carries a `task_id` must also carry `_build_schedule_task_response_metadata(...)`-equivalent provenance, matching replay/status/list; `get_scheduled_task_status` must return stable `code=TASK_NOT_FOUND` for a missing stored task and a distinct stable unavailable code when the task store/service is unavailable. Existing scope, target, scheduler, and TaskStore persistence behavior remains unchanged. No authentication or persistence redesign belongs here.

#### State, timing, recovery, and command coordination

The monitor lifecycle states are `idle`, `polling`, `paused-disconnected`, `reconciling`, `backoff`, `terminal`, `missing`, `adapter-error`, and `stopped`.

- A newly accepted current task enters `polling` and requests `schedule.status` immediately, even if the run response already said pending/running. A poll never delays Live Voice capture recovery or an unrelated Chat/Agent turn.
- After a valid queued observation, schedule the next poll for 1 second. On the first valid running observation, latch `runningSince`; poll every 2 seconds while less than 30 seconds has elapsed since that observation, then every 5 seconds. A later queued snapshot does not erase `runningSince`. An unknown non-terminal status polls every 5 seconds.
- A valid response resets transient error count. Retriable failures retry the same operation after 1, 2, 5, then 10 seconds, capped at 10 seconds. Non-retriable rejected requests stop. No retry issues `run` or obtains a new command ID.
- At most one poll/reconcile read may be in flight per task. A next timer is armed only after the prior promise settles. Repeated wakeups coalesce. The monitor owns an `AbortController` for each read; abort is a cleanup optimization, while the context/generation fence remains the authority if a transport ignores abort.
- Disconnect cancels the timer, fences the active generation, intentionally aborts an unresolved read, and enters `paused-disconnected`. Reconnect records a pending reconcile but does not overlap the settling aborted promise. The current WebClient must honor its existing abort contract, after which exact owner/namespace/command-key `schedule.list` runs immediately. If an alternate injected gateway ignores abort, no-overlap wins: remain visibly paused until the old read settles, then reconcile. An intentional lifecycle abort is ignored rather than classified as a retry/business error.
- A reconnect list must contain exactly one record and must match task ID, command ID, query, pipeline, complete target, and provenance. A valid record is applied as the observation; if non-terminal, normal status polling resumes. Transport failure retries exact-list reconciliation with the same backoff. Empty, multiple, conflicting, or malformed records stop as missing/conflict/adapter error.
- Full-page refresh, browser restart, another process/device, and session-navigation-away-and-back recovery are unsupported. The module does not scan by owner or infer a task from recency. A future persistent command journal/TaskEvent projection replaces this limitation.
- Feature flag off, hook unmount, Bridge replacement, session/target drift, provenance mismatch, or monitor replacement aborts the owned read, fences the generation, cancels timers, and makes late callbacks zero-effect. Navigating away does not keep polling a hidden foreign session.
- Exiting the active voice interaction does not destroy the same-page truthful task projection; the monitor may finish the current page-memory observation. A terminal arriving while Live Voice is inactive is visible-only and permanently consumes no speech attempt, so re-enabling voice cannot produce a surprise old announcement.
- Before a direct status/cancel/replace command operates on the current task, the hook suspends, aborts the monitor-owned read, and fences callbacks. The user command does not wait for that read to settle because it is not another monitor poll; its result still cannot be overwritten by the old generation. A validated direct command result synchronizes Bridge and projection; a non-terminal status result resumes on the normal interval, cancel stops terminal, and replace freezes A then begins B.
- After a stopped business/adapter error, only a later fully valid direct status result for the exact same in-memory task/context may start a new monitor generation. `missing`, denied scope/project, provenance conflict, context drift, or an untrusted candidate cannot auto-resume.
- A replace result must carry the validated predecessor task record, not only `predecessorTaskId/predecessorCancelled`. A is retained from the real cancel/terminal response, B is current only after its task ID/target/provenance are accepted, and a conflict candidate is never relabeled successor. If A is cancelled but B remains mutation-unknown, show A truthfully and run no monitor until B is exactly reconciled.
- Terminal UI projection is immediate and irreversible within that monitor generation. Any scheduled timer is cancelled. Repeated or late terminal observations cannot produce a second projection transition or notification.
- An asynchronous terminal notification is eligible at most once per task and only at a safe gap: same source session/target/Bridge, task feature on, Live Voice active, microphone/capture closed, chat neither processing nor thinking, core idle, no active/pending speech, and current TTS ownership available. It never stops recognition/TTS or preempts user/Agent output. If terminal arrives inactive, context becomes stale, speech is unavailable, or no safe gap occurs before teardown, the result remains visible-only. Direct task-command feedback marks the corresponding terminal as already acknowledged so monitor speech cannot duplicate it.

#### Explicit non-goals and replacement path

This slice does not add TaskEvent push/replay, durable frontend command journal/projection, cross-page/device unread, server-pushed completion, general multi-task polling/NLU, task update/provide-input/pause/resume/reprioritize, versioned WorkProgress outcome, D1/D2 durability, cross-process exactly-once, production authentication/authorization/existence hiding, formal P3 ConversationRuntime, or media/audio work. It does not make task status an Agent Turn or Chat message. Formal P3α Task Control and TaskEvent storage/subscription replace the polling controller; the identity, scope, projection, and safe-notification contracts remain reusable.

#### Existing test inventory reviewed before implementation

| Existing test / suite | Layer | Why it remains in the D-031 dependency inventory | Scenario IDs / oracle | Pre-review state |
|---|---|---|---|---|
| `liveVoiceTaskBridge.test.mjs` — 43 declared cases covering grammar/commit/confirmation, real IDs, status families, cancel, replace, same-key recovery, exact-key list, deleted tombstone, target conflict, serialization, and idempotency conflict | pure/adapter boundary | Characterizes the existing command/mutation authority that the monitor must update without weakening | `P-01`, `P-03`, `P-06`, `N-08..09`, `C-02..04`, `R-01..02`, `I-01..04`, `K-02..05`; forbidden `run/cancel/list/status` call counts are already asserted in rejection paths | existing; must be extended, not replaced |
| `liveVoiceTaskAdapter.test.mjs` — 14 declared cases covering flag routing, exact session/target, disclosure, context isolation, record role/provenance, stale async result, and task-feedback drain | pure adapter | Protects Chat-vs-Task routing and the current UI/TTS fences while projection becomes multi-record | `N-01`, `N-06..08`, `T-03`, `I-01`, `F-01`, `X-02..03`; stale results and flag-off must cause zero dispatch/UI/speech | existing; affected assertions require post-diff review |
| `liveVoiceTaskClient.test.mjs` — 9 declared groups, including invalid-session/project parameters, all four operations, pass-through business error, and exact-key scope | client contract | Proves every read keeps the persisted session/project and exact key; prevents unscoped reconnect scans | `N-04`, `R-01..03`, `I-01..03`, `K-01`, `X-04`; transport calls are exactly shaped or zero | existing; add read-signal propagation without changing mutations |
| `liveVoiceCore.test.mjs` (9) and `liveVoiceTurnLifecycle.test.mjs` (16) | pure state machines | Protect microphone, response epoch, FIFO TTS, interrupt/exit fence, final timeout, and resume semantics that terminal speech must not bypass | `N-06..08`, `T-03`, `T-06`, `F-04..05`, `X-03`; no old sound/capture callback may revive | existing adjacent regression |
| `test_schedule_request.py` — 7 declared tests | WebSocket/server integration | Proves status/list derive real request owner/project without acquiring or trusting an Agent and return one correlated response | `N-04`, `I-02..03`, `K-01`, `X-04`; no Agent acquisition and no spoofed scope | existing; add stable-code cases |
| `test_schedule_task_service.py` — 57 declared tests | service/store integration | Covers real provenance reload, scoped exact list, wrong owner/project zero side effects, status/list enrichment, terminal/cancel races, tombstone and idempotency ledger | `P-02..03`, `N-04..05`, `C-02..04`, `R-01..02`, `I-02..03`, `K-01..04`, `X-04`; no foreign progress read/store write/cancel | existing; add missing/unavailable distinction |
| `test_live_voice_contract.py` — 16 declared tests | shared contract | Guards exact cancel scopes, committed-input side-effect gate, and formal WorkProgress rules so the Demo monitor cannot be mislabeled as P3 outcome | `N-08`, `F-01`, `K-05`; partial/uncommitted side effects remain zero | existing architectural regression |
| TypeScript/Vite production build and documentation checks | compile/cross-file | Finds real prop/type/i18n wiring omissions that isolated pure files cannot | `X-01..04`, `X-07`; build and link/diff checks exit 0 | required final evidence; not newly run in this pre-review environment |

#### Planned test inventory and frozen oracle

| Planned test / parameterized group | Layer | Why the test exists | Scenario IDs | Oracle and forbidden result | State |
|---|---|---|---|---|---|
| `monitor starts immediately without owning foreground` | pure monitor/fake clock | Proves a real Bridge task creates one immediate read while Chat/capture remain independent | `P-01`, `N-08`, `X-02` | one `status`; zero Chat/Agent/capture/run/cancel calls | new |
| `valid queued/running/terminal observations project backend facts` | pure monitor | Covers every accepted raw family, progress/error projection, Bridge synchronization, and terminal stop | `P-02..03`, `B-01..03`, `S-01..02`, `K-02` | exact raw/normalized facts; Bridge snapshot agrees; terminal timer count 0 | new parameterized group |
| `unknown statuses remain non-terminal and forward compatible` | pure monitor/fake clock | Prevents a new backend string from becoming guessed success/failure | `B-02`, `K-02`, `K-05` | raw preserved, kind unknown, next delay 5s, zero speech/terminal latch | new |
| `strict envelope, identity, target, provenance, and optional-shape rejection` | parser/monitor | Fails closed on every required-field/malformed/cross-scope variant | `N-02..05`, `B-04..06`, `I-01..02`, `K-03` | old snapshot byte-for-byte equivalent; zero timer after permanent error, speech, mutation, or foreign detail | new parameterized group |
| `retriable reads back off 1/2/5/10; non-retriable rejects stop; valid data resets` | pure monitor/fake clock/deferred promise | Uses WebClient retry metadata instead of error text and makes recovery deterministic without mutation replay | `N-05`, `S-03`, `T-01..02`, `C-01..02`, `R-04`, `K-01` | exact times/call counts; same task/operation; non-retriable call count one; zero overlap/run/cancel | new parameterized group |
| `queued/running/unknown cadence uses settled-response time` | pure monitor/fake clock | Freezes 1s, first-running 2s→5s after 30s, unknown 5s and prevents request duration from creating overlap | `P-02`, `T-01..02`, `C-01` | timers arm only after settle; one read in flight maximum | new |
| `disconnect aborts the owned read, pauses, then exact-key reconciles` | pure monitor/deferred gateway | Covers immediate/queued reconnect, unresolved-old-read ordering, and transports that honor or ignore abort | `P-05`, `S-04`, `T-03..04`, `C-01`, `R-01`, `F-02` | one intentional abort; current WebClient settles then lists immediately; ignore-abort fake stays paused until settle; never overlaps; stale result zero effect | new parameterized group |
| `status/list propagate AbortSignal while run/cancel do not change` | client contract | Closes the current request-type gap without widening mutation cancellation semantics | `S-04..05`, `T-04`, `X-01`, `X-04` | exact third request option on reads; unchanged mutation payloads/call counts | changed client tests |
| `empty, multiple, mismatched, malformed, and transport-failed reconnect lists` | pure monitor | Proves missing/conflict stop and transient list retry are distinct | `N-02..05`, `R-02`, `K-03` | empty→missing; conflict/malformed→adapter error; transport retries list only; no status/run/cancel until reconciled | new parameterized group |
| `full refresh and session navigation do not infer recovery` | controller/adapter | Makes unsupported durability explicit and prevents broad owner scans | `R-03`, `R-06`, `I-01`, `F-02` | zero list/status without an in-memory task+command; visible unsupported/cleared context | new |
| `generation fences every late completion` | pure monitor/deferred promise | Covers task replacement, disconnect, flag-off, unmount, Bridge/session/target drift | `N-07`, `S-05`, `T-03..05`, `I-01` | zero UI/Bridge/speech/timer effects after fence | new parameterized group |
| `direct status/cancel/replace suspends monitor and fences the old read` | controller/Bridge integration | Prevents late polling from overwriting user control and keeps later Bridge decisions current | `P-07`, `S-06..07`, `T-03`, `C-03..04`, `X-02` | command need not await poll; old read ignored; at most one current monitor; exact command mutation counts | new/changed |
| `replace retains validated A and monitors only validated B` | Bridge+adapter+monitor integration | Enforces the successor relation and zero invented cancellation/successor | `P-06`, `N-09`, `C-04`, `I-04`, `X-02` | A record comes from cancel response; B exact; conflict never successor; only B status calls | new/changed |
| `A cancelled with B unknown keeps A and starts no guessed monitor` | Bridge+adapter+monitor integration | Covers the dangerous partial replace failure | `N-09`, `C-04`, `R-02`, `I-04` | A terminal visible, pending command exact, zero poll of A/conflict/unknown B | new |
| `terminal notification selector requires a safe gap and fires at most once` | pure adapter/core integration | Prevents async result speech from preempting mic, user, or Agent TTS | `P-04`, `N-06..07`, `T-06`, `C-05`, `F-04..05`, `X-03` | eligible tuple enqueues once; every failed predicate enqueues zero; direct feedback suppresses duplicate | new parameterized group |
| `task projection cannot write chatStore or processing state` | controller integration with spies | Proves Task facts remain outside Session History/Agent Turn | `N-08`, `X-03` | zero message/send/interrupt/processing mutations across success/error/reconnect | new |
| `task activity renders predecessor/current facts separately` | adapter + static component render | Prevents one generic record from relabeling A, B, or conflict and displays `unknown` honestly | `P-02..03`, `P-06`, `B-03`, `I-04`, `X-02`, `X-07` | both real IDs/status/provenance present; no invented result text; valid accessible status/alert roles | new/changed |
| `isConnected propagates App → ChatPanel → hook → monitor` | build plus controlled browser integration | Closes the currently missing connection lifecycle input | `S-04`, `X-01` | disconnect causes no poll; reconnect exact-list observed; production build exits 0 | new wiring evidence |
| `fresh idempotent run/status/list/replay expose one complete provenance shape` | Python service/server/client contract | Closes the current fresh-run metadata asymmetry so the monitor never synthesizes provenance | `P-01`, `N-09`, `K-01`, `X-04` | each task-bearing response has exact owner/namespace/key/target/access metadata; no changed scheduler/store side effect | new/changed backend tests |
| `status missing and store unavailable have stable distinct codes` | Python service/server contract | Avoids locale-string parsing and false missing classification | `N-05`, `K-01`, `X-04` | exact code/envelope/metadata; one response; no store/progress/control side effect | new backend tests |
| `backend terminal set and frontend normalization stay intentionally aligned` | cross-language contract fixture/assertion | Forces review when backend adds a status and preserves D-034 unknown behavior | `P-03`, `B-02`, `K-02` | known set exact; unrecognized values remain frontend non-terminal until decision | new/changed |
| Controlled real E2E: task continues while another voice/chat turn completes; reconnect; terminal card/notification; replace A→B | real WebSocket/Agent/Tool/UI + manual microphone evidence where required | Pure tests cannot prove the actual hook, real scheduler, UI, capture, Agent and TTS coexist | `P-01..07`, `N-06..08`, `R-01`, `X-01..06` | real IDs/facts; foreground turn completes; no Chat task message, old TTS, duplicate speech, guessed outcome, or A polling; isolated runtime side effects recorded | required post-implementation evidence; gap until run |

#### P/N/B/S/T/C/R/I/F/K/X scenario matrix

Every row below is mandatory unless explicitly marked as a production gap/unsupported boundary. Automated tests use fake clocks, deferred promises, spies, and store snapshots; no correctness assertion may depend on sleep timing.

| ID | Preconditions and input/event | Expected output/state and allowed side effect | Explicitly forbidden | Evidence binding |
|---|---|---|---|---|
| `P-01` | Valid Bridge create/recovery result with full identity | Immediate one-task monitor; foreground can resume/listen/chat | waiting for task completion; Chat/Agent mutation | start unit + real E2E |
| `P-02` | Valid queued→running observations with optional progress/error | Raw backend facts and cadence update; Bridge/UI agree | guessed percent/result or stale Bridge state | observation + cadence groups |
| `P-03` | Each recognized terminal family, including tombstone statuses | Exact raw terminal card, timer stop, neutral success/non-success classification | invented outcome/result; terminal re-poll | terminal parameterization + contract |
| `P-04` | Terminal arrives in a fully safe speech gap | One neutral fact notification | more than one TTS or any preemption | notification selector + E2E |
| `P-05` | Same-page connection returns with exact in-memory command | Exact-key list reconciles then resumes/status-stops | broad list/recency inference | reconnect group |
| `P-06` | Replace A cancel is confirmed and B identity is valid | Preserve real terminal A + relation; monitor B only | overwriting A; polling A; guessing B | replace integration + UI render |
| `P-07` | Direct status/cancel/replace while monitor active | Monitor fenced; authoritative command result applied; correct resume/stop | late poll overwrite or duplicated control | command coordination group |
| `N-01` | Task flag off or ordinary committed speech | Existing V0 Chat path unchanged | monitor/timer/task request/disclosure | existing + flag test |
| `N-02` | Non-object or missing/invalid required envelope fields | Adapter error; prior projection preserved; stop | adoption, speech, timer, mutation | strict rejection group |
| `N-03` | Response/list record task ID differs | Adapter/conflict error; expected task remains | relabeling or foreign card | strict/reconnect groups |
| `N-04` | Target/owner/provenance/key/namespace/access mismatch | Isolation error; stop with no foreign content | cross-scope progress/detail/control | parser + backend scope tests |
| `N-05` | Missing task, store unavailable, business error, or non-retriable rejected RPC | Distinct visible condition; trusted facts preserved; stop; only explicitly retriable read errors back off | treating error/status field as success or retrying by message text | backend code + parser/retry tests |
| `N-06` | Mic open, processing/thinking, core/TTS busy, or speech owner unavailable | Visible terminal only/pending until safe as specified | stop/preempt mic or Agent TTS | selector parameterization |
| `N-07` | Completion after fence/terminal/unmount/flag/context change | No effect | UI/Bridge/timer/TTS revival | deferred fence tests |
| `N-08` | Any monitor success/error/retry lifecycle | Only read calls, local task projection, optional safe TTS | Chat message/send/interrupt, processing change, run/cancel | spy integration |
| `N-09` | Initial/replacement task lacks trustworthy identity or B is unknown/conflict | No monitor for that candidate; retain validated A/old facts | guessed task or successor | Bridge/replace integration |
| `B-01` | Case/space/hyphen variants of accepted raw status | Normalize family while preserving raw display | rewriting raw backend fact | status parameterization |
| `B-02` | New non-empty unknown status | Unknown/non-terminal, 5s cadence, no notification | guessing terminal from wording | unknown status test |
| `B-03` | Optional progress/error absent/empty; progress summary absent | Display `unknown`; required status still valid | fabricated stage/percentage/error | optional facts test |
| `B-04` | Present progress is not object or last_error not string | Malformed adapter error; old facts remain | lossy stringify/adoption | strict rejection group |
| `B-05` | Empty/whitespace/non-string ID or status; array/null payload | Adapter error | defaulting status/ID | strict rejection group |
| `B-06` | Unicode summary/error and unknown extra fields | Preserve safe text/ignore extras; empty summary unknown | schema rejection solely for extras or HTML execution | parser + static render |
| `S-01` | idle→poll/reconcile/backoff→poll lifecycle | Only documented transitions | hidden mutation state | state-machine tests |
| `S-02` | First valid terminal observation | Terminal immutable for generation | terminal→running or second notice | terminal/fence tests |
| `S-03` | Consecutive transient failures then valid response | Backoff counter advances then resets | permanent-error retry or fresh command ID | backoff group |
| `S-04` | Online→offline→online | Pause/fence, then exact reconciliation | calls offline or direct status before reconcile | reconnect group/browser evidence |
| `S-05` | flag off, unmount, session/target/Bridge drift | stopped and fenced | hidden polling or stale projection update | lifecycle tests |
| `S-06` | Monitor observes terminal while Bridge initially stored running | Same Bridge current task becomes terminal | UI-only truth divergence | Bridge-monitor integration |
| `S-07` | Direct task command controls current task | Suspend/fence/apply/resume-or-stop | stale response authority inversion | command coordination |
| `S-08` | Task terminates while voice interaction inactive | Card state retained page-locally; visible on re-enable; no speech | surprise deferred old TTS | lifecycle + selector |
| `T-01` | Fake time advances across queued/running 30s/unknown/backoff | Exact 1s, 2s→5s, 5s, 1/2/5/10s schedule | sleep-dependent/faster loop | cadence/backoff tests |
| `T-02` | Slow unresolved read while timers/wakeups occur | No next call until settle; then one timer | overlapping polls | deferred concurrency test |
| `T-03` | Old response arrives after command/reconnect/task/context generation changes | Ignored | old fact overwrite | generation tests |
| `T-04` | Reconnect occurs before disconnected read settles | Abort/fence old read, mark reconcile pending; current WebClient settles and lists immediately; ignore-abort gateway stays paused until settle | overlapping list + old poll or treating an ignored abort as successful cancellation | reconnect deferred test |
| `T-05` | Terminal/stop occurs with timer armed | Timer cancelled and callback harmless | post-terminal read | fake-clock terminal test |
| `T-06` | Terminal UI update precedes later safe/unsafe gap changes | UI immediate; TTS once only if still eligible | blocking UI or duplicate/late stale speech | notification tests |
| `C-01` | Multiple wakeups/reconnect signals for same task | Coalesce to one read | request fan-out | monitor concurrency tests |
| `C-02` | Retry after transport loss | Same task and same status/list operation | `run`, new key, mutation replay | backoff/reconnect tests |
| `C-03` | User control overlaps unresolved poll | Control proceeds; old poll fenced | poll overwrites cancel/status/replace | controller integration |
| `C-04` | Replace cancel/create/reconcile partial failures and races | A/B identities and calls converge to validated facts | two B tasks, A resurrection, conflict relabel | existing Bridge + new integration |
| `C-05` | Repeated terminal snapshots/safe-gap renders/direct feedback | At-most-once async notification | duplicate TTS | notification latch tests |
| `R-01` | Same-page reconnect with one exact matching list record | Restore record and continue/stop | unscoped list | reconnect + backend list tests |
| `R-02` | Empty/multiple/conflicting exact list or B unknown | Missing/conflict/adapter error; no monitor mutation | arbitrary winner or blind run | reconciliation parameterization |
| `R-03` | Full-page reload/restart lacks page journal | Explicit unsupported; no automatic recovery | owner scan/most-recent inference | controller test + UI disclosure |
| `R-04` | Status response lost or explicitly retriable outer failure | Preserve facts and retry read with backoff | clear card, retry a non-retriable reject, or create task | transport test |
| `R-05` | Reconnect context no longer matches original session/target | Stop/isolate | request under new context for old task | identity tests |
| `R-06` | Navigate away then back to same session | No implicit monitor resurrection | treating same ID string as same hook/Bridge generation | controller fence test |
| `I-01` | Any session/target/Bridge/task/generation mismatch | Fail closed/ignore | cross-context UI/TTS/request | adapter+monitor tests |
| `I-02` | Backend denies owner/project or returns denied provenance | No foreign progress/content/control; stop | disclosure of denied task details or mutation | service snapshots + parser |
| `I-03` | Malicious client can self-assert Web scope | Record as D-033 production gap; claim only single-user consistency | authentication/tenant/existence-hiding claim | documentation + backend scope evidence |
| `I-04` | A/B/conflict identities coexist | Separate exact roles and provenance | infer conflict/successor from generic record | adapter/UI tests |
| `F-01` | Compile/runtime task capability disabled | V0 path and zero new side effects | monitor/card/task interception | existing/new flag tests |
| `F-02` | WebSocket disconnected or reconnect capability unavailable | Paused textual state/read-only recovery | polling failure loop or fake online state | connection tests |
| `F-03` | Progress/log capability absent | Status remains truthful; progress `unknown` | invented progress | optional fact tests |
| `F-04` | TTS unsupported/busy/no ownership | Visible-only terminal | alternate Chat message or forced audio | notification selector |
| `F-05` | Live Voice inactive when terminal arrives | Visible-only, no later surprise speech | queuing indefinitely for re-enable | lifecycle test |
| `K-01` | Fresh run/replay/status/list metadata plus outer error, missing, unavailable, scope/project codes | One complete provenance shape, stable exact classification, one response | synthesized provenance, localized-string oracle, or duplicate response | Python server/service/client tests |
| `K-02` | Known/unknown statuses and extra fields across versions | Known set exact; unknown preserved non-terminal; extras ignored | silent terminal widening | cross-contract tests |
| `K-03` | Missing/wrong-type required or present optional fields | Fail closed, prior projection preserved | permissive guessed defaults | parser tests |
| `K-04` | Legacy unscoped task/old page state | Not monitorable under D-031 external scope | migration guess or persistence rewrite | existing service + controller test |
| `K-05` | Demo progress vs formal WorkProgress/TaskEvent contract | Clearly labeled Demo facts only | versioned outcome/replay claim | contract + UI copy test |
| `X-01` | Real App connection state changes | Prop reaches hook and drives pause/reconcile | monitor using request failure as connection oracle only | build/browser integration |
| `X-02` | Bridge result/observation flows through monitor→adapter→card | Bridge and UI show same backend record(s) | divergent status or mislabeled A/B | integration + static render |
| `X-03` | Terminal fact reaches core/TTS alongside Chat lifecycle | Safe single notification or visible-only; Chat untouched | Agent Turn/task Chat message/preemption | spies + real E2E |
| `X-04` | Web client→Agent WS→service/store status/list | Exact scoped facts/progress/codes returned | Agent acquisition, unscoped read, cross-project progress | client/Python integration |
| `X-05` | Real background task plus independent foreground turn | Foreground completes while task continues; terminal later returns | frozen foreground or fake completion | controlled E2E |
| `X-06` | Real/controlled replace A→B | A remains terminal, only B monitored | A polling or B guessed | controlled E2E/integration |
| `X-07` | New props/types/i18n/styles/component roles | Production build and static render pass | missing label/type/wiring hidden by pure monitor test | build/render checks |

#### Bounded implementation work packages for a non-Sol executor

At this historical checkpoint these packages were proposed for execution after separate review, commit, and push approvals. Under D-046/D-047 they must not be treated as the current queue: if the Day 5/Day 7 decision authorizes a D-031 fallback, Sol first re-slices only the minimal 1–2 day monitor needed by the Integrated Demo. The rows below remain historical until then.

1. `D031-B1 — backend observation contract`: add complete response metadata to every fresh idempotent run result carrying a task ID, add the minimal stable missing/unavailable status codes, and add Python/client contract tests. Do not alter owner/project policy, TaskStore format, scheduler behavior, or authentication claims.
2. `D031-B2 — shared fact model + pure monitor`: add strict provenance/observation types, read-only gateway `AbortSignal` propagation, Bridge synchronization/predecessor record, injected-clock monitor, and all pure fake-clock/deferred tests. Do not touch React until these tests and Sol-frozen oracles pass.
3. `D031-B3 — adapter/hook/UI wiring`: project A/B records and monitor health, propagate `isConnected`, coordinate direct commands, add safe terminal selector/TTS latch and i18n/UI. Do not write Chat history or change existing Agent response lifecycle.
4. `D031-B4 — cross-layer verification`: run target and adjacent suites, production build, Python tests, controlled browser/real E2E, and report exact commands/results/gaps. Do not change assertions or semantics merely to obtain green results.
5. `D031-A2 — Sol post-review`: Sol rereads the actual diff/tests, updates this inventory/matrix with discovered risks, determines required E2E, and signs `CLOSED/PARTIAL/BLOCKED`. This package cannot be delegated as final judgment.

The following cells are deliberately empty. Empty means no executor/model has started the package and no implementation result, diff, test evidence, or unresolved issue has been reported; it is not a pass, failure, or implicit assignment.

| Non-Sol package | Executor / model | Started | Finished | Implementation result | Changed files / diff | Tests / evidence | Unresolved / return to Sol |
|---|---|---|---|---|---|---|---|
| `D031-B1` |  |  |  |  |  |  |  |
| `D031-B2` |  |  |  |  |  |  |  |
| `D031-B3` |  |  |  |  |  |  |  |
| `D031-B4` |  |  |  |  |  |  |  |

Implementation stops and returns to Sol if it needs a new status, new error classification, looser target/provenance rule, overlapping read exception, task-history expansion, changed notification eligibility, persistent recovery, test weakening, or any production-security claim.

### Architecture design closure: ACG-1 shared v2 contract

- Gate state: `SOL DESIGN ACCEPTED / V2 IMPLEMENTATION NOT STARTED / CONFORMANCE NOT RUN / MODULE POST-REVIEWS MISSING`.
- Sol sign-off: GPT-5.6 Sol accepted the architecture semantics and oracles on 2026-08-03 under D-042. This signs the design only; it is not a code, test, Provider, security, module-closure, or release sign-off.
- Sources: [ARCHITECTURE_CONTRACT_GATE_V1.md](architecture/ARCHITECTURE_CONTRACT_GATE_V1.md), D-013–D-016, D-031–D-034, D-039, D-041–D-042, roadmap §3.1/§4/§7, and the complete solution §5.2/§6/§8.
- Baseline identity: branch `hx/0803_live_voice`, runtime implementation baseline `ac988b85e8a21eb4f378086bab58dac6a4d55d82`, with a clean worktree before this documentation-only design batch began.
- Version boundary: strict minimal `live-voice.contract.v1` remains a Foundation input. Complete schema target is `live-voice.contract.v2`; no current runtime type is relabeled v2 and no v1 event is upgraded without complete authoritative identity/scope/sequence/source provenance.
- Authority/non-goals: the Gate freezes cross-plane semantics only. It does not implement or select a production Provider, modify current runtime behavior, close D-031, supply production auth/D1/D2/exactly-once, restore private configuration, or prove real media/device/SLO evidence.

#### ACG-1 planned conformance inventory

| Planned suite / group | Layer | Why it exists | Scenario IDs | Oracle / forbidden outcome | Execution state |
|---|---|---|---|---|---|
| `v2_schema_and_compatibility` JSON fixtures in valid/invalid pairs | schema/contract | Separates strict v1 from complete v2 and freezes canonical serialization/closed extension rules | `P-01`, `B-04`, `K-01..04` | exact round-trip or stable rejection; never relabel lossy v1 as v2 |  |
| Python + TypeScript shared-envelope parity | cross-language conformance | Prevents one runtime from accepting shapes, IDs, enums, or result ownership the other rejects | `P-01`, `N-03`, `B-01..02`, `K-02..03`, `X-03` | fixture-by-fixture identical accept/reject and canonical values |  |
| identity/ScopeRef/authority validation | contract + reducer | Stops ID-kind aliasing, cross-scope disclosure, and second lifecycle owners | `P-02`, `N-02`, `S-04`, `I-01..04` | exact parent/scope/authority or fail closed; forbidden reads/writes/calls = 0 |  |
| Command/Query/Result envelope and idempotency | contract/conformance | Separates read from mutation, one response owner, stable replay, and conflict | `P-03`, `N-03`, `C-02..03`, `K-03..04` | same fingerprint replays; conflict mutates zero; result xor error |  |
| EventEnvelope reducer with fake store/clock | pure state/event conformance | Proves duplicate/gap/out-of-order/causation rules without sleep or wall-clock ordering | `P-01`, `T-01`, `C-01`, `R-03`, `K-02` | apply once in contiguous seq; quarantine gap; conflicting duplicate rejects |  |
| interaction/turn/response reducer | pure state machine | Freezes commit, generation fence, terminal outcome, close, and late callback behavior | `P-02`, `N-01`, `S-01`, `S-03`, `T-02..04`, `C-04` | only allowed transitions; late/fenced effects across all consumers = 0 |  |
| task/attempt reducer + fake Task Core/Executor | pure/contract | Freezes P3α state/outcome, command ACK distinction, D0, and unsupported operations | `P-02..03`, `S-02..03`, `T-03`, `R-02`, `F-02` | canonical terminal truth; no resume/rollback/update claims |  |
| exact cancel-scope matrix | contract + authority fakes | Prevents barge-in/cancel escalation and ACK-as-terminal | `N-04`, `T-03`, `C-03`, `X-01..02` | targeted owner only; unrelated playback/response/round/task calls = 0 |  |
| TurnCommit and critical-input gate | contract + dispatch spies | Proves partial/interim/unconfirmed input cannot cross Agent/Tool/Task boundaries | `N-01`, `B-03`, `I-02`, `F-01` | one immutable commit or rejection; all forbidden dispatch/persistence = 0 |  |
| presented-ledger reducer | pure + Audio/UI fake ACK | Distinguishes produced/queued/presented/invalidated and retains only acknowledged prefix | `P-04`, `T-04`, `C-04`, `R-01`, `X-01` | surface cursor monotonic; queued audio never becomes heard history |  |
| WorkProgressEvent v2 mapper | contract + Harness/Executor fakes | Preserves real source provenance/seq/outcome and explicit unknown facts | `P-04`, `B-03`, `S-04`, `I-01`, `X-01..02` | exact source mapping; guessed progress/result/direct TTS/state write = 0 |  |
| ContextRef permission/expiry/redaction suite | contract + authorization fake | Stops stale/unversioned/cross-scope context from authorizing disclosure or side effects | `N-02`, `B-03`, `I-01..03`, `F-02` | fresh exact authorized ref or stable rejection; secret serialization = 0 |  |
| capability/error/fallback suite | adapter conformance | Keeps unsupported, unavailable, error, retry, and fallback provenance honest | `N-03`, `F-02..04`, `K-02` | retry only explicit safe retriable; message text has no semantic effect |  |
| feature-off and text-path regression | integration | Protects current Chat JSON/E2A/History/TTS/Task behavior | `F-01`, `X-03` | zero new timer/media/command/persistence side effects and unchanged regression |  |
| fake Provider/Executor fault injection then per-adapter integration | adapter/integration/E2E | Contract green alone cannot prove real Provider/Executor/transport/device behavior | `R-01..04`, `X-01..04` | exact adapter authority and failure isolation; real gaps remain explicit |  |

#### ACG-1 P/N/B/S/T/C/R/I/F/K/X scenario matrix

All scenario results are blank until a non-Sol implementation reports evidence and Sol performs post-review. `N/A` is not pre-authorized.

| ID | Preconditions and input/event | Expected output/state and allowed side effect | Explicitly forbidden | Planned evidence | Result |
|---|---|---|---|---|---|
| `P-01` | Valid v2 Command/Query/Result/Event envelope and canonical fixture | Exact cross-language round-trip; one response/event application | field loss, version rewrite, duplicate application | schema + parity suites |  |
| `P-02` | Legal interaction/turn/response/task/attempt transition with exact parents/scope | Owning authority advances one state and emits correlated fact | second authority or unrelated lifecycle change | state reducers |  |
| `P-03` | Same command ID and identical canonical fingerprint is retried | Original result/task identity replays once | second mutation/task/attempt | command/idempotency suite |  |
| `P-04` | Authoritative round/task event with complete source facts and presentation ACK | Exact WorkProgress/known facts; presented cursor advances on correct surface | guessed summary/outcome or queued-as-presented | progress + ledger suites |  |
| `N-01` | Partial/interim/uncommitted input or second different commit for same turn | Reject/conflict with zero dispatch or persistence | Agent/Tool/Task/command journal side effect | commit spies |  |
| `N-02` | Scope, parent ID, ContextRef permission/expiry/redaction, or source provenance mismatches | Fail closed before disclosure/control and preserve trusted local state | foreign content/existence leak at authenticated boundary or mutation | identity/context suites |  |
| `N-03` | Malformed envelope, result+error coexist, missing capability, or non-retriable error | Stable protocol/unsupported/error result; stop or explicit fallback | message-text parsing, guessed defaults, silent success | envelope/error suites |  |
| `N-04` | Barge-in or one exact cancel command is received | Only targeted playback/response/round/task authority invoked | implicit escalation or unrelated cancel/rollback | cancel matrix |  |
| `B-01` | Empty/whitespace/wrong-type/oversized identity or enum value | Stable validation error | trimming/case folding/coercion to valid identity | schema boundaries |  |
| `B-02` | seq is zero/max supported, negative/bool/non-integer; timestamp is malformed/non-UTC | Valid boundary accepted or stable rejection | wall-clock ordering or numeric coercion | event boundary fixtures |  |
| `B-03` | WorkProgress/Context detail is known-empty, unknown, unversioned, expired, or Unicode | Preserve exact knowledge/redaction; unsafe action rejects | treating unknown as empty/success or executing markup | progress/context fixtures |  |
| `B-04` | Strict v1 payload meets v2 boundary, or v2 needs v1 projection | Upgrade only with all authoritative fields; lossy output labeled v1/Demo | same-version field extension or v1 relabeled v2 | compatibility suite |  |
| `S-01` | Every allowed/forbidden interaction, turn, and response edge | Only documented edge; committed/cancelled/closed terminal | rewrite committed turn or reopen interaction | conversation reducer |  |
| `S-02` | Every allowed/forbidden task and attempt edge | Core/Executor converge per authority; terminal carries outcome | Executor edits canonical task or terminal reverses | task/attempt reducer |  |
| `S-03` | Any terminal response/task/attempt then later active event | Terminal remains immutable; later event rejected/quarantined | terminal→running or second outcome | terminal property tests |  |
| `S-04` | Bridge/Adapter maps Harness/Executor event | Adapter-produced event identifies itself and causal source | impersonating source authority or mutating source state | authority mapping suite |  |
| `T-01` | Duplicate, reused seq, future gap, out-of-order, or late EventEnvelope | identical duplicate no-op; conflict rejects; gap quarantines/reconciles | speculative apply or sorting by timestamp | event store fake |  |
| `T-02` | Old response callback after generation change/cancel/close/reconnect | Zero UI/history/audio/Agent/Tool/Task/notification effect | old output or state revival | deferred fence suite |  |
| `T-03` | Cancel ACK arrives before/after terminal, is lost, or times out | ACK and lifecycle state remain distinct; unknown reconciles | ACK-as-terminal or new-identity blind retry | cancel/event tests |  |
| `T-04` | Audio/UI ACK, stop, response terminal, and late output reorder | Contiguous presented prefix only; unACKed suffix invalid | history containing unpresented/fenced suffix | ledger/deferred tests |  |
| `C-01` | Same event delivered concurrently through replay/live paths | Apply exactly once by event ID+bytes | double transition/notification | barrier/event-store test |  |
| `C-02` | Same command ID concurrently retries same/different fingerprint | one original result or deterministic conflict | two tasks/attempts/mutations | idempotency barrier test |  |
| `C-03` | playback/response/round/task cancels overlap | Each exact owner converges independently | scope widening or shared generic cancel latch | authority fakes |  |
| `C-04` | Provider callback, response replacement, and presentation ACK race | generation/sequence fences choose current exact fact | stale audio/history/progress adoption | deferred provider/ledger tests |  |
| `R-01` | Media disconnect/reconnect with same interaction but new connection epoch | transport resumes only declared capability; old media fenced | changing turn/task identity or old-frame revival | loopback/fault fake |  |
| `R-02` | Application restart with D0 task record and lost live attempt | Task Core reconciles to observed terminal/unknown truth | promise to resume execution or rollback effects | fake store/executor restart |  |
| `R-03` | Event sequence gap with replay supported/unsupported | replay exact stream or expose gap and query authority | skip gap and continue canonical mutation | event-store/reconcile test |  |
| `R-04` | Page/process lacks journal, Provider state, credential, or device | Explicit unsupported/unavailable and local trusted facts only | recency inference or Git-restored capability claim | adapter/recovery tests |  |
| `I-01` | Event/command/context crosses subject/project/session or work identity | Reject before read/write/speech/control | cross-scope content or side effect | scope matrix + snapshots |  |
| `I-02` | ContextRef lacks permission, is expired/redacted/unversioned for destructive action | Fresh resolution/confirmation required or reject | destructive Tool/Task dispatch | context auth fake |  |
| `I-03` | Current D-033 request-asserted scope is used | Label single-user consistency only | authentication/tenant/existence-hiding claim | compatibility/docs assertion |  |
| `I-04` | Provider-specific type/status attempts to cross Adapter | Map to declared v2 capability/error or reject | shared module depending on vendor object | adapter type/fixture tests |  |
| `F-01` | Live Voice/P3α flag off | Current text/Agent/Tool/TTS/Task behavior unchanged; new calls/writes zero | hidden timer/media/command/projection | regression + spies |  |
| `F-02` | Capability absent, temporary unavailable, or unsupported operation | Exact unsupported/unavailable distinction and safe text fallback where declared | fake success or implicit operation widening | capability suite |  |
| `F-03` | Browser/Cascade/other fallback selected | Fallback provider/capability provenance visible | silent provider swap or bypassed commit/safety | adapter conformance |  |
| `F-04` | Notification/TTS unavailable or busy | Visible event remains; speech omitted/deferred only per Runtime policy | direct Bridge/WorkProgress TTS or preemption | notification authority fake |  |
| `K-01` | v1/v2/unknown contract version combinations | exact supported parser/adapter path or `UNSUPPORTED` | treating unknown major as current | version fixtures |  |
| `K-02` | Namespaced extension, unknown required capability/event/state/enum | optional extension preserved/ignored; semantic unknown quarantined/rejected | silent semantic widening | compatibility fixtures |  |
| `K-03` | API result ownership/correlation and payload variants | one correlated xor result/error envelope | double response or `ok=true` business error | API conformance |  |
| `K-04` | Canonical fingerprint across key order, whitespace, Unicode, float edge | equivalent form replays; semantic difference conflicts | implementation-language hash drift | cross-language canonical fixtures |  |
| `X-01` | Harness round → Agent Bridge → WorkProgress → Conversation Runtime → UI/TTS | source IDs/seq/outcome preserved; Runtime arbitrates | slow Harness sync wait or Bridge direct TTS | fake then real Harness integration |  |
| `X-02` | Task command → Task Core → Executor → TaskEvent/WorkProgress → origin surface | stable task/attempt/command identities and D0 truth | Voice Bridge persistence/direct Executor control | fake then AutoHarness integration |  |
| `X-03` | v2 components enabled/disabled beside current Chat JSON/E2A | text path retains one response owner and history semantics | protocol collision/regression | cross-language + existing regression |  |
| `X-04` | Fake passes then Browser/AutoHarness/real-media candidate is connected | Adapter-specific integration/fault evidence required | using fake green to claim device/Provider/Executor closure | per B/C integration/E2E |  |

#### Bounded ACG-1 implementation packages for a non-Sol executor

1. `ACG-B1 — schema and fixtures`: implement v2 identity/scope/ContextRef, Command/Query/Result/Event, WorkProgress, capability/error types and canonical JSON fixtures in the shared Python schema boundary plus a language-neutral fixture directory. Preserve v1 unchanged.
2. `ACG-B2 — reducers and conformance runners`: implement pure interaction/turn/response/task/attempt transition validators, event dedup/gap logic, cancel/commit/fence/presented-ledger reducers, and Python/TypeScript fixture runners with fake clock/deferred tests. No real Provider/Executor/UI wiring.
3. `ACG-B3 — compatibility and fake Ports`: implement guarded v1→v2 compatibility outcomes, deterministic Speech/Media/Harness/Executor fakes, capability negotiation, feature-off/text-regression tests, and explicit unsupported results. No vendor selection or AutoHarness/Browser real adapter wiring.
4. `ACG-B4 — shared-contract verification`: run exact shared/adjacent suites, cross-language fixture parity, type/lint/build and documentation checks; report evidence and gaps without weakening schemas/oracles.
5. `ACG-A2 — Sol post-review`: reread actual diff/tests, reconcile every matrix row, determine whether the shared implementation is `CLOSED/PARTIAL/BLOCKED`, and authorize module-specific `*-A` use. Final judgment is not delegated.

The non-Sol execution record is intentionally blank:

| Non-Sol package | Executor / model | Started | Finished | Implementation result | Changed files / diff | Tests / evidence | Unresolved / return to Sol |
|---|---|---|---|---|---|---|---|
| `ACG-B1` |  |  |  |  |  |  |  |
| `ACG-B2` |  |  |  |  |  |  |  |
| `ACG-B3` |  |  |  |  |  |  |  |
| `ACG-B4` |  |  |  |  |  |  |  |

Any implementation need for a new identity/state/outcome/cancel/authority/error/compatibility rule, looser safety assertion, real Provider/model selection, or expanded AutoHarness durability stops that branch and returns it to Sol.

### Module test closure: CR-A P2 response/generation contract and reducer

- Closure state: `PARTIAL — SOL PRE-REVIEW COMPLETE / DEPENDENCY AND IMPLEMENTATION NOT STARTED / POST-REVIEW MISSING`.
- Sol sign-off: GPT-5.6 Sol completed the source/test-level D-032 pre-review on 2026-08-03 under D-043. The design/oracle is frozen; no CR-A code, test, capability, commit, or release pass is implied.
- Stage / sources: V1 Foundation Alpha and P2 `CR-A`; ACG-1/D-042, D-007, D-013, D-016, D-019, D-021, D-023, D-025, D-041, D-043; roadmap §3.1, P0-2, D7 and V1/V2; full solution P2/§5.2/§5.3/§6.2.
- Dependency Gate: CR-A non-Sol execution waits for the applicable ACG-B1/B2 v2 identity/envelope/transition fixtures to exist and pass targeted conformance. CR-A may not privately redefine shared schema to avoid that dependency.
- Baseline and reviewed scope: design started after D-041 while runtime implementation remained at `ac988b85e8a21eb4f378086bab58dac6a4d55d82`; only documentation was modified. Reviewed adjacent implementation includes `liveVoiceCore.ts`, `liveVoiceTurnLifecycle.ts`, `liveVoiceStreamingSpeech.ts`, `liveVoiceMessageGate.ts`, `useLiveVoiceDemo.ts`, `supplementOutputQuarantine.ts`, WebSocket chat handlers, chatStore final marking, current WebSocket types, and all focused tests listed below.

#### CR-A module definition, authority, and non-goals

CR-A is a provider-neutral, media-neutral Conversation Runtime foundation. It implements shared v2 conversation types, a pure canonical Gateway/server reducer, a schema-parity frontend validation replica, exact cancel/effect routing, response output fencing, and a per-surface presentation ledger. It does not connect a real Provider, Agent cancellation, Realtime Media, browser/player ACK, or Session History writer.

The server canonical record owns:

- interaction `open/closing/closed`, turn `capturing/committed/cancelled`, and response `accepted/generating/speaking/terminal` transitions;
- server-issued exact `interaction_id/turn_id/response_id`, strictly increasing `response_generation` per interaction, event sequence, correlation/causation, and ScopeRef;
- one unfenced frontstage response per interaction, while older fenced responses may await a real terminal event;
- response `output_fence=active|fenced`, orthogonal `cancel_state=none|requested|acknowledged|result_unknown`, and terminal outcome only when authoritative;
- command replay/conflict record for exact cancel routing and effect idempotency.

The frontend replica accepts only contiguous, scope-matching canonical events and owns no server lifecycle. It may perform immediate local `playback.stop`, discard fenced output, validate presentation ACK, and expose selectors. Local capture IDs, old `responseEpoch`, request/rid, message ID, `isResponseFinal`, processing flags, and supplement quarantine remain compatibility facts only.

Reducer inputs are v2 Command/Event envelopes plus explicit local presentation ACK/failure observations. Reducer outputs are immutable next state and declarative effects to the exact owner: Audio/Media `playback.stop`, Provider/Bridge `response.cancel`, Agent Bridge `round.cancel`, or Task Core `task.cancel`. CR-A itself does not execute effects, call TTS, dispatch Agent/Tool/Task, mutate chatStore, persist Session History, or infer terminal completion from an ACK.

Presentation units carry exact response tuple, surface (`text|audio`), unit/sequence, source text span, and content hash/ref. `produced`/`enqueued` do not advance history. A monotonic contiguous UI/Audio `PresentationAck` advances the corresponding surface cursor. Response creation freezes the history-surface policy (`text`, `audio`, or `union`); selectors include only ACKed, non-invalidated spans under that policy. Stop/cancel/fence retains the ACKed prefix and invalidates the unACKed suffix. Presented content is immutable; a semantic rewrite requires a newer response generation.

Feature/capability off means no v2 Runtime request, event, reducer, timer, persistence, or effect. Existing Chat JSON/E2A, message store, supplement behavior, local Demo epoch/FIFO, and task path remain byte/behavior compatible. Capability negotiation must be end to end; a client cannot run a formal replica against legacy events missing canonical IDs.

Explicit CR-A non-goals are CR-B event-loop integration, real Gateway/Agent event tagging, actual Provider cancellation, natural barge-in policy, streaming audio/TTS, physical playback ACK implementation, chatStore/Session History migration, WorkProgress notification arbitration, multi-device leader/lease, production authentication, P3 task lifecycle, and performance/SLO closure.

#### Existing CR-A dependency/characterization inventory

| Existing suite | Layer / declared cases | Why it remains required | CR-A scenarios / oracle | Pre-review state |
|---|---|---|---|---|
| `liveVoiceCore.test.mjs` | pure Demo lifecycle, 9 | Characterizes once-only local commit, local epoch/FIFO, interrupt/exit/error stale callback fence | `N-01`, `T-02`, `F-01`, `X-03`; existing behavior unchanged when formal capability off | existing compatibility |
| `liveVoiceTurnLifecycle.test.mjs` | pure selectors, 16 | Protects session promotion, processing/final timing, missing-final timeout and capture resume | `T-02..04`, `R-01`, `F-01`, `X-03`; no provisional final promotion | existing compatibility |
| `liveVoiceStreamingSpeech.test.mjs` | pure planner, 18 | Characterizes preview append/rewrite/final reconciliation and local responseEpoch isolation | `B-03`, `S-03`, `T-02..04`, `F-01`; never claim preview is presented | existing compatibility |
| `liveVoiceMessageGate.test.mjs` | pure store selector, 14 | Protects user boundary, authoritative final marker, multi-segment and historical-message isolation | `N-02`, `I-01`, `K-03`, `X-03`; formal identity must replace, not weaken, boundary guards | existing compatibility |
| `supplementOutputQuarantine.test.mjs` | client barrier, 6 | Proves current ordered single-session Demo quarantine and its excluded paths | `N-04`, `T-03`, `F-01`, `X-03`; retained but never relabeled production fence | existing compatibility |
| `chatStoreStreaming.test.mjs` | store, 3 | Characterizes latest-turn `isResponseFinal` marking and no-op repeat | `K-03`, `X-03`; flag-off store semantics unchanged | existing compatibility |
| `ttsOutputOwnership.test.mjs` | process-local output owner, 2 | Protects old in-flight server TTS fence and multiple owner release | `C-03`, `F-01`, `X-03`; not used as presentation ACK | existing compatibility |
| Gateway interrupt/stream cancellation, Web channel coalescing, E2A wire and Chat/CLI regression suites | backend/protocol/integration | Current request/rid/stream/interrupt semantics are compatibility inputs and reveal missing response identity | `K-01..04`, `X-02..04`; current consumers stay green and legacy ID is never promoted | existing; exact affected tests selected after diff |

#### Planned CR-A test inventory and frozen oracle

| Planned group | Layer | Why | Scenario IDs | Oracle / forbidden result | Execution state |
|---|---|---|---|---|---|
| canonical server reducer transition table | pure Python/property + v2 fixtures | Makes server the only lifecycle/generation owner | `P-01..03`, `S-01..04`, `B-01..02` | exact legal edge/event; illegal/stale edge leaves state/effects unchanged |  |
| frontend replica fixture parity | pure TypeScript cross-language | Prevents client from accepting a transition/identity server rejects | `P-01`, `N-02..03`, `T-01..02`, `K-01..03` | identical canonical state/error for every fixture; client allocates no formal ID |  |
| turn commit and response allocation | reducer + dispatch spies | Freezes once-only commit and strictly increasing generation | `P-01`, `N-01`, `C-01`, `I-01` | one response tuple per accepted action; partial/duplicate conflict side effects 0 |  |
| orthogonal cancel/fence reducer | reducer + authority fakes | Separates immediate output safety from actual lifecycle completion | `P-02`, `N-04`, `S-02..03`, `T-03`, `C-02..03` | fence immediate; exact one routed effect; ACK/timeout never terminal |  |
| four-scope cancel router | pure routing/idempotency | Prevents generic cancel and barge-in escalation | `N-04`, `C-02`, `I-02`, `F-02`, `X-01..02` | exact owner+target or stable reject; unrelated owner calls 0 |  |
| response generation late-output fence | deferred/fake event source | Proves all stale Provider/Agent/UI/audio callbacks have zero effect | `N-03`, `S-03`, `T-01..02`, `C-04`, `R-01` | old tuple effects/state/history/presentation/notification = 0 |  |
| presentation unit/ACK/invalidation ledger | pure reducer/property | Establishes actually presented spans and immutable prefix | `P-03`, `B-03..04`, `S-04`, `T-04`, `C-04`, `R-03` | only contiguous exact ACK; queued/onStart/final not presented; rewrite rejected |  |
| history-surface policy selector | pure selector | Makes text/audio/union context choice explicit and reproducible | `P-03`, `N-03`, `B-04`, `K-03`, `X-01` | only selected ACKed spans; no raw audio or unACKed suffix |  |
| event duplicate/gap/reconnect replay | fake event store/clock | Validates replica recovery without wall-clock guesses | `T-01`, `C-01`, `R-01..02`, `K-02` | exact duplicate no-op; conflict/gap quarantined; old connection epoch fenced |  |
| capability/feature-off legacy characterization | contract/integration | Prevents hybrid v2/legacy identity and protects V0/text path | `F-01..04`, `K-01`, `X-03` | no negotiated capability→legacy unchanged; missing v2 fields never guessed |  |
| Gateway canonical-owner fake integration | backend integration with fake Agent/Provider | Proves IDs/events are assigned before dispatch and terminal maps back exactly | `P-01..02`, `N-02`, `T-03`, `X-02` | canonical tuple on every event; Agent callback cannot choose generation |  |
| target/adjacent build and regression | verification | Pure reducer green cannot prove imports/types/current path compatibility | all `X`; existing 68 focused cases plus affected Gateway/E2A/TS/build | exact commands/results at immutable candidate; no snapshot weakening |  |

#### CR-A P/N/B/S/T/C/R/I/F/K/X scenario matrix

| ID | Preconditions / input | Expected state/output and allowed effect | Explicitly forbidden | Planned evidence | Result |
|---|---|---|---|---|---|
| `P-01` | Authenticated/request-consistent TurnCommit for an open interaction | Server records one committed turn, allocates response ID and next generation, emits correlated accepted event | client/local ID as authority or duplicate Agent dispatch | allocation reducer + fake Gateway |  |
| `P-02` | Exact current response transitions accepted→generating→speaking→terminal | Canonical state advances; terminal has one outcome | skipped illegal edge or nonterminal outcome | transition table |  |
| `P-03` | Valid text/audio units and contiguous ACKs under frozen history policy | Surface cursor and presented selector advance exactly | queued/onStart/final marker treated presented | ledger/property tests |  |
| `P-04` | New response accepted while an older response is still live | New generation strictly greater; older output atomically fenced; both records retained | ID reuse, old output, implicit round/task cancel | reducer/deferred tests |  |
| `N-01` | partial/interim/uncommitted input, empty commit, or second different commit | reject/no-op/conflict; state and all external effects unchanged | Agent/Tool/Task/response allocation/history write | commit spies |  |
| `N-02` | wrong/missing interaction/turn/response/generation/scope/parent | stable validation/isolation error; trusted state preserved | foreign content/state/effect or default ID | parity fixtures |  |
| `N-03` | output/ACK/terminal from fenced, older, closed, or unknown response tuple | ignore/quarantine/reject with zero projection/effect | UI/audio/history/notification revival | deferred fence tests |  |
| `N-04` | barge-in or cancel command lacks exact scope/target/capability | local exact stop where valid or stable reject | generic cancel, scope escalation, lifecycle terminal guess | cancel matrix |  |
| `B-01` | first interaction/generation, zero seq, max supported counters | valid boundary accepted without collision | generation 0 reuse or overflow wrap | boundary/property test |  |
| `B-02` | empty/whitespace/Unicode/wrong-type IDs, enum, outcome, timestamps | exact schema behavior and safe diagnostic | trim/coerce/message execution | schema fixtures |  |
| `B-03` | empty text, multi-byte spans, code/path text, zero-length/overlap units | valid explicit empty/no-op or stable rejection; hashes/spans exact | lossy character indexing or executable markup | ledger Unicode fixtures |  |
| `B-04` | known-empty vs unknown ACK/history detail; text/audio/union with one surface absent | preserve distinction and selected surface truth | unknown→presented or cross-surface cursor | selector fixtures |  |
| `S-01` | open→closing/closed interaction and attempted reopen/new turn | documented transitions only; close fences new work | reopen or new response after close | server reducer table |  |
| `S-02` | response cancel requested/acknowledged/result_unknown while lifecycle nonterminal | cancel field changes independently; output remains fenced | ACK/timeout→terminal | orthogonal reducer |  |
| `S-03` | terminal response then duplicate/different terminal or active event | identical duplicate no-op; conflict rejected; terminal immutable | terminal rewrite/revival | terminal property tests |  |
| `S-04` | presentation stop/invalidation after ACKed prefix | ACKed prefix retained; unACKed suffix invalid; surface presentation closed | erase presented fact or alter business lifecycle | ledger tests |  |
| `T-01` | EventEnvelope duplicate/gap/out-of-order across server/client | sequence rule applies; gap quarantined/reconciled | timestamp sorting/speculative apply | event fake |  |
| `T-02` | old Provider/player/store callback arrives after generation change/disconnect/teardown | all consumers observe zero effect | stale state, sound, history, timer, Agent/Tool/Task call | deferred callback suite |  |
| `T-03` | cancel dispatch, ACK, terminal and timeout arrive in every order | exact fence and cancel record converge; terminal only authoritative | double cancel effect or premature terminal | fake clock/barrier matrix |  |
| `T-04` | produced/enqueued/UI ACK/audio ACK/stop/final reorder | surface cursors remain contiguous and monotonic | gaps counted presented or late suffix restored | presentation event matrix |  |
| `C-01` | concurrent duplicate TurnCommit or response-accepted delivery | one canonical response/generation/event | two responses or two Agent dispatches | command/event barrier |  |
| `C-02` | same/different cancel command ID/fingerprint overlaps | replay same effect result or deterministic conflict | duplicate owner call or widened target | idempotency/routing tests |  |
| `C-03` | playback.stop, response.cancel, round.cancel, task.cancel overlap | independent exact effects and states | shared global cancel latch | four-authority fake |  |
| `C-04` | new response, old audio ACK, old terminal, new output race | each applies only to exact record/surface; active response remains new | cross-generation cursor/state overwrite | deferred property test |  |
| `R-01` | client/media disconnect and reconnect with same interaction/new connection epoch | canonical server state queried/replayed; old transport callbacks fenced | client reconstructing from message recency | replay/reconcile fake |  |
| `R-02` | replay gap unavailable or canonical Runtime unavailable | explicit gap/unavailable; local replica stops mutation | continuing on incomplete stream or legacy ID guessing | capability/error tests |  |
| `R-03` | browser reload loses local presentation ACK not yet persisted | only server/durable ACK truth restored; otherwise unknown/unpresented | claiming queued speech was heard | ledger restart fixture |  |
| `R-04` | existing Demo path has only responseEpoch/message boundary | remain legacy compatibility path | partial v2 label or hybrid reducer | feature-off/adapter test |  |
| `I-01` | session/project/interaction/response scope mismatch | reject before content/effect and preserve local trusted state | cross-session response or history | scope fixtures |  |
| `I-02` | cancel target kind does not match scope owner | stable invalid/scope error | sending task ID to response/round owner | cancel router tests |  |
| `I-03` | D-033 request-asserted scope enters CR-A | consistency label only; production gap remains | authentication/existence-hiding claim | docs/schema assertion |  |
| `I-04` | Provider callback supplies own ID/state not in canonical map | Adapter maps to existing tuple or rejects | Provider becoming lifecycle authority | fake Provider tests |  |
| `F-01` | formal capability/feature flag off | existing Demo/Chat/E2A/store/TTS/task path unchanged; new effects/writes 0 | v2 event/timer/store mutation | 68-case compatibility + regressions |  |
| `F-02` | Provider cancel or playback ACK unsupported | local fence/visible unsupported as defined; no false terminal/presented claim | fallback to round/task cancel or onStart ACK | capability tests |  |
| `F-03` | frontend supports v2 but server does not, or inverse | negotiation rejects formal mode and uses labeled legacy path | hybrid partial authority | handshake fixtures |  |
| `F-04` | Session History/presentation persistence capability absent | in-memory selector only and recovery unknown | durable/presented claim | capability/restart tests |  |
| `K-01` | current request_id/rid/responseEpoch/message ID meets formal boundary | kept as correlation/compatibility metadata only | reinterpret as response/generation ID | adapter fixtures |  |
| `K-02` | unknown v2 event/state/required capability or seq gap | quarantine/reject/reconcile per ACG | silent ignore with state advance | event parity suite |  |
| `K-03` | chat.final/isResponseFinal/processing false arrives with/without canonical terminal | legacy UI marker remains separate; canonical state follows v2 event only | marker-as-terminal or presented | integration fixtures |  |
| `K-04` | cancel ACK legacy payload lacks exact target/generation | compatibility response only; cannot complete v2 cancel | opening v2 fence for ambiguous response | legacy adapter test |  |
| `X-01` | Runtime effect → Audio/UI fake → PresentationAck → history selector | exact tuple/cursor round-trip | Audio deciding cancel scope or direct history mutation | component integration |  |
| `X-02` | TurnCommit → Gateway Runtime → Agent Bridge fake → response events → client replica | IDs/seq/correlation preserved end to end | synchronous slow Harness wait or Provider identity override | fake vertical slice |  |
| `X-03` | formal flag off beside current Web Chat and Demo voice | all existing focused/Gateway/E2A/build regressions pass | changed message topology, TTS, quarantine or task semantics | regression/build |  |
| `X-04` | later real CR-B/AB/Audio wiring | requires separate D-032 and real cancel/ACK/history evidence | using CR-A fake green to claim realtime/production closure | later module Gates |  |

#### Bounded CR-A work packages for a non-Sol executor

1. `CRA-N1 — canonical server reducer`: after ACG primitives exist, implement pure server conversation records, transition table, generation allocator, command replay/conflict and JSON fixture runner. No Gateway/Agent live wiring.
2. `CRA-N2 — frontend validation replica`: implement TypeScript replica against the same fixtures, exact stale/gap/scope handling and selectors. Do not replace `liveVoiceCore`/chatStore or enable it in React.
3. `CRA-N3 — cancel/effect router and presented ledger`: implement pure four-scope routing, orthogonal cancel/output fence, presentation units/ACK/invalidation and history-policy selector with authority fakes. No real TTS/Media/Agent/Task calls.
4. `CRA-N4 — compatibility and verification`: add explicit legacy-ID non-promotion tests, feature/capability-off characterization, cross-language parity and affected existing suites/type/build commands. No snapshot/oracle weakening.
5. `CRA-S2 — Sol post-review`: inspect the actual diff and all affected protocol/tests, update scenarios/results, decide shared conformance and `CLOSED/PARTIAL/BLOCKED`, and authorize CR-B pre-review. Final judgment is not delegated.

The non-Sol execution record is intentionally blank:

| Non-Sol package | Executor / model | Started | Finished | Implementation result | Changed files / diff | Tests / evidence | Unresolved / return to Sol |
|---|---|---|---|---|---|---|---|
| `CRA-N1` |  |  |  |  |  |  |  |
| `CRA-N2` |  |  |  |  |  |  |  |
| `CRA-N3` |  |  |  |  |  |  |  |
| `CRA-N4` |  |  |  |  |  |  |  |

CR-A execution returns to Sol before changing any shared schema, state/authority/cancel rule, generation allocation, terminal/ACK meaning, presented policy, legacy compatibility, or target package boundary.

### Module test closure: P1 Speech Port `SR-A` / `SS-A`

- Current closure: **PARTIAL**. The D-032 source/test-level pre-review and design oracle are complete; shared v2 primitives, Port code, fakes, conformance, Provider/Browser Adapters, corpus results and real-device evidence do not exist yet.
- Sol sign-off: GPT-5.6 Sol froze the `SR-A` and `SS-A` design on 2026-08-03 under D-044. This is design authorization for bounded non-Sol execution only, not a code, quality, privacy, Provider, module, cumulative-version or release pass.
- Stage / sources: V1 Foundation Alpha P1-1; ACG-1/D-042, D-004, D-013, D-016, D-039, D-041, D-044; roadmap §3.1/§7.4; full solution §5.2/§6.2 `SR-A` and `SS-A`.
- Split closure rule: recognition and synthesis share v2 primitives, fixture style and conformance runner, but they are separate runtime modules. `SR-A CLOSED` cannot imply `SS-A CLOSED`, and neither implies SR-B/C, SS-B/C, Realtime Media, Audio I/O, Interaction integration or production speech quality.

#### Frozen module definition and authority boundary

| Concern | `SR-A` / `SS-A` decision | Explicit non-goal in this slice |
|---|---|---|
| shared Port primitives | Versioned `SpeechCapability`, `SpeechProviderRef`, `SpeechError`, session/generation, ordered event and fallback provenance extend ACG v2; unsupported and unknown are first-class | selecting credentials, endpoint, model, billing, production Provider or Native Engine |
| recognition input/output | Batch and streaming-shaped RecognitionSession accepts declared audio/source constraints and emits immutable raw hypothesis events with session/generation/seq, partial/final/cancel phase, alternatives/confidence when available, locale, timing and provenance | Browser/mic capture, VAD/EOT, deciding TurnCommit or directly calling Agent/Tool/Task |
| hypothesis resolution | A deterministic resolver consumes raw hypotheses plus permitted/unexpired ContextRef and returns a separate resolved copy with selected index, rules/context references, reason and confidence source; raw provider text remains inspectable | silent string replacement, treating current repository context as permission, or Provider-specific logic in Runtime |
| critical semantic gate | Negation, number/date/SHA/path/branch and side-effect verbs are classified before commit; output is `eligible`, `clarification_required` or `blocked` with reasons | auto-approving side effects or interpreting a confidence number as authorization |
| commit authority | Recognition final is evidence, not a TurnCommit. Interaction/Conversation Runtime alone chooses commit/clarification and owns all downstream effects | any partial/interim/final callback bypassing commit, confirmation, scope or response identity |
| synthesis request | SynthesisSession accepts exact response ID/generation, presentation unit and source text span plus voice/locale/policy; Provider cannot choose business identity | generating text, changing response state, writing chat/history or choosing cancel scope |
| render plan | `SpeechRenderPlan` preserves display-text hash and span, produces a separate speakable copy, and records every removal/redaction/pronunciation transformation with reversible or explicitly lossy span mapping | overwriting the displayed answer or hiding path/code/media omission from evidence |
| synthesis output | Batch/streaming-shaped output uses ordered audio/control events with response tuple, unit/span, format/timing and Provider/fallback provenance; stale generation is fenced | treating bytes produced, queue insertion or Browser `onstart/onend` as presented |
| cancel and playback | recognition/synthesis session cancel is an owner-internal Provider control, not a fifth business CommandEnvelope scope; it and `playback.stop` target different owners. Acceptance fences exact late output; ACK/timeout/local silence does not manufacture terminal | external callers issuing Provider control, generic TTS/STT cancel escalation, response/round/task cancellation or presentation ACK |
| Browser baseline | Current Web SpeechRecognition/SpeechSynthesis is the first compatibility/fallback Adapter target. Missing alternatives/confidence/audio bytes/chunk timing/cursor remain unknown/unsupported | relabeling the existing Hook as conformant streaming speech or a production Provider |
| privacy and observability | Raw audio defaults to no persistence; consented/synthetic fixtures record purpose, retention, deletion and redaction. Metrics preserve Provider/environment/corpus identity | checking recordings into Git without consent or reporting aggregate accuracy without sample/environment evidence |

Dependency rule: implementation waits for `ACG-B1` shared capability/error/identity primitives. Synthesis identity fixtures also consume the frozen CR-A response tuple; real synthesis/Audio integration waits for CR-A conformance and later CR-B/AIO Gates. Pure SR/SS fake work may proceed independently after those shared types exist, but no Adapter may invent missing ACG/CR semantics locally.

#### Existing implementation and test inventory reviewed before design

| Existing source/test | Cases / layer | Why retained | What it proves / does not prove | State |
|---|---|---|---|---|
| `useSpeech.ts` + `speechRecognitionLifecycle.test.mjs` | Browser Hook/lifecycle, 7 tests | Protects initial/tail silence, restart, manual/auto stop and transcript merging used by current Demo/Chat input | Proves local Browser generation/lifecycle behavior only; first alternative, fixed callback shape and localized error are not a Port | existing compatibility |
| `ttsText.ts` + `liveVoiceTtsText.test.mjs` | pure text preparation, 10 tests | Protects full-answer preservation, technical-token pronunciation, bounded lossless chunking and regular-TTS compatibility | Does not record render provenance/span mapping or prove spoken correctness | existing compatibility |
| `ttsOutputOwnership.ts` + `ttsOutputOwnership.test.mjs` | process-local owner, 2 tests | Fences stale legacy `tts.synthesize` completions and overlapping React owners | Not a response generation, Provider cancel, Audio cursor or presentation ACK | existing compatibility |
| `liveVoiceStreamingSpeech.ts` + test | client text→utterance queue, 18 tests | Protects stable-prefix enqueue, stale-response fence, bounded queue and stop behavior | Browser utterance events contain no audio bytes/cursor; queue/onStart is not presented | existing compatibility |
| `liveVoiceCore.ts` + test | adjacent UI reducer, 9 tests | Protects feature-off Demo capture/response epochs and current transcript flow | Epoch is local compatibility state, not RecognitionSession/response authority | existing compatibility |
| `tts.ts`, disabled Gateway `tts.synthesize`, Browser Speech calls in `useLiveVoiceDemo.ts`/`InputArea.tsx` | adapter/call-site characterization | Reveals one browser-only path and one currently unregistered server request path | No direct provider-neutral Adapter conformance, stable speech error, fallback or real Gateway speech test exists | reviewed gap |

The **46 focused compatibility cases** above remain mandatory feature-off regression evidence. They are not counted as new Port conformance and cannot close any empty scenario below.

#### Planned P1 Speech Port test inventory and frozen oracle

| Planned group | Layer | Why | Scenario IDs | Oracle / forbidden result | Execution state |
|---|---|---|---|---|---|
| shared speech schema/capability fixtures | v2 cross-language schema | Keeps Provider, Browser Adapter and clients on one exact unknown/unsupported/error meaning | `P-01..03`, `B-01..04`, `I-01`, `F-01..03`, `K-02` | exact round-trip/reject; no default confidence, locale, IDs or capability |  |
| RecognitionSession reducer and deterministic fake | pure Port/fake clock | Freezes ordered partial/final/cancel and late-event fences without a real Provider | `P-01`, `N-01`, `S-01..02`, `T-01..02`, `C-01..02`, `R-01` | one ordered stream; final immutable; partial/downstream effects 0 |  |
| raw hypothesis + domain resolver fixtures | pure deterministic resolver | Makes technical correction auditable and reproducible | `P-02`, `N-02..03`, `B-01..02`, `I-02`, `K-01` | raw candidates unchanged; exact rule/context/reason/confidence source |  |
| critical-token decision table | pure policy/property + effect spies | Prevents a low-CER transcript from dispatching a semantically dangerous command | `P-02`, `N-02`, `B-02`, `S-03`, `C-03`, `X-01` | ambiguous critical token clarifies/blocks; Agent/Tool/Task calls 0 |  |
| SynthesisSession reducer and deterministic fake | pure Port/fake clock | Freezes request identity, audio/control sequencing, completion and cancel | `P-03`, `N-04`, `S-04`, `T-03..04`, `C-04`, `R-02` | exact response tuple and unit; stale chunks/playback effects 0 |  |
| render-plan/span provenance fixtures | pure Unicode/property | Prevents speech cleanup from silently rewriting display truth | `P-03`, `B-03..04`, `I-03`, `K-03` | display hash stable; joined units cover declared spoken copy; every lossy transform explicit |  |
| Browser fallback characterization Adapter | browser API fake/contract | Preserves current fallback while exposing its real limitations | `F-01..04`, `K-01..04`, `X-02` | no unsupported field fabrication; no bytes/cursor/presented claim |  |
| failure/fallback/capability policy | fake Providers/fault injection | Distinguishes failed, unavailable, unsupported and selected fallback | `N-03..04`, `R-01..03`, `F-02..03`, `I-04` | one policy-valid fallback with provenance or stable fail closed; empty success forbidden |  |
| privacy/corpus/metrics harness | fixture manifest + offline benchmark | Makes quality evidence reproducible without normalizing unsafe audio retention | `I-03..04`, `R-03`, `X-03` | consent/synthetic source + retention/deletion; per-sample metric and environment identity |  |
| compatibility and affected regression | existing Web tests/type/build | Prevents Port scaffolding from changing current Demo/Chat/TTS when disabled | all `K`, `F-04`, `X-02` | existing 46 focused cases and affected build pass without oracle weakening |  |
| later real Adapter/device E2E | SR-B/C, SS-B/C, AIO/RM/Windows Gates | Text fixtures cannot prove acoustic quality, latency, stop or hardware behavior | `X-04` plus real corpus/device scenarios | exact Provider/device/corpus/build evidence; not credited to SR-A/SS-A |  |

#### P1 Speech Port P/N/B/S/T/C/R/I/F/K/X scenario matrix

| ID | Preconditions / input | Expected state/output and allowed effect | Explicitly forbidden | Planned evidence | Result |
|---|---|---|---|---|---|
| `P-01` | Valid RecognitionSession request and ordered Provider partial→final | Immutable raw events preserve exact session/generation/seq, source and capability; final closes hypothesis stream | TurnCommit, Agent/Tool/Task call or Provider-assigned business ID | recognition fake/reducer |  |
| `P-02` | Alternatives contain a permitted deterministic technical correction with noncritical or unambiguous meaning | resolver emits separate selected/resolved copy and audit trail; gate returns exact decision | mutation of raw hypothesis or context-free replacement | resolver/gate fixtures |  |
| `P-03` | Valid SynthesisSession with current response tuple, render plan and one/many text units | ordered control/audio events retain tuple, unit/span, format and source; terminal outcome exact | chat/history write or presented advancement | synthesis fake/reducer |  |
| `P-04` | Provider advertises required batch/stream/cancel/timing/output capability | request accepted only for declared intersection and policy-valid fallback | optimistic use of undeclared capability | capability fixtures |  |
| `N-01` | partial/interim/unconfirmed or cancelled recognition output | projection may update draft only; downstream business effects stay zero | commit, Agent/Tool/Task, confirmation bypass | effect spies |  |
| `N-02` | negation/number/date/SHA/path/branch/side-effect verb is low-confidence or candidates conflict | `clarification_required` or `blocked` with exact critical evidence | best-guess dispatch or confidence-as-authorization | critical-token table |  |
| `N-03` | missing/wrong session, generation, seq, Provider provenance, required ContextRef or locale policy | stable reject/quarantine/unsupported; trusted state unchanged | default ID, guessed context or empty-success transcript | schema/reducer fixtures |  |
| `N-04` | synthesis request has wrong/fenced response tuple, malformed render map, empty unsupported voice or mismatched unit | stable rejection and output/playback/history effects 0 | audio generation under another response or silent coercion | synthesis validation tests |  |
| `B-01` | zero/one/max alternatives; confidence 0/1/unknown; empty/whitespace/Unicode transcript | exact documented accept/reject/unknown behavior; raw bytes/text preserved | fabricated confidence or trim changing evidence | schema/property fixtures |  |
| `B-02` | critical token at punctuation/word boundary, homophone, mixed Chinese/English, leading zero, SHA/path/date edge | deterministic classification and preserved token spans | lossy normalization or blanket “high confidence” | corpus fixtures |  |
| `B-03` | empty display/span, surrogate pairs, combining marks, URL/path/code/media, maximum unit/chunk boundary | code-point-safe mapping or stable rejection; explicit lossy transform | split surrogate, unrecorded omission or changed display text | render-plan properties |  |
| `B-04` | audio format/rate/channel/timestamp/seq at supported minima/maxima or unknown Browser values | exact supported value or explicit unknown/unsupported | invented timing, duration, bytes or cursor | synthesis schema fixtures |  |
| `S-01` | recognition created→active→final/failed/cancelled; duplicate terminal or restart | documented transition only; terminal immutable; restart uses new generation/session | terminal revival or ID reuse | transition table |  |
| `S-02` | recognition cancel requested/ACK/timeout races final | fence is immediate; exact authoritative event determines final state; result_unknown stays non-success | ACK/timeout manufacturing transcript/final | fake clock matrix |  |
| `S-03` | resolver/gate receives revised partials then final | only current final can become commit-eligible; decision audit bound to its raw event | carrying a stale partial correction into final | reducer/policy fixtures |  |
| `S-04` | synthesis accepted→producing→completed/failed/cancelled with playback independently open/stopped | synthesis and presentation states remain orthogonal | completed/onStart/onEnd becoming presented or response terminal | state reducer |  |
| `T-01` | recognition duplicate/gap/out-of-order or old callback after new generation | duplicate no-op; gap quarantined; stale event effect 0 | timestamp sort or stale draft/final revival | deferred event tests |  |
| `T-02` | silence/restart/manual stop/unmount Provider callbacks arrive in every order | exactly one lifecycle outcome for current session; old Browser behavior preserved under compatibility flag | recognizer resurrection or duplicate final/commit | fake timers + existing 7 tests |  |
| `T-03` | audio/control chunks duplicate/gap/out-of-order or arrive after synthesis fence | exact duplicate no-op; gap error/quarantine; stale playback/enqueue effects 0 | playing or presenting an old/gapped chunk | synthesis deferred tests |  |
| `T-04` | synthesis cancel, Provider ACK/terminal, playback.stop and response fence race | each exact authority converges independently and remains correlated | generic cancel, double owner call or terminal guess | multi-owner fake clock |  |
| `C-01` | concurrent start/retry with same recognition command identity/fingerprint | same command replays one session/effect; conflict rejects deterministically | two active captures or two Provider starts | idempotency barrier |  |
| `C-02` | concurrent identical/different recognition cancel | one Provider cancel for identical replay; exact conflict for different target | duplicate/widened cancel | cancel router fake |  |
| `C-03` | same final/gate decision delivered twice or commit consumer races clarification | one immutable decision; downstream consumer must still enforce once-only TurnCommit | duplicate dispatch or clarification after dispatch | decision/effect barrier |  |
| `C-04` | overlapping synthesis sessions for old/new response generations | new and old records remain separate; old output fenced without stopping unrelated owners | global state collision or cross-response audio | synthesis concurrency tests |  |
| `R-01` | recognition Provider fails/unavailable/unsupported before or during session | policy-valid fallback starts as a new declared session/generation with original error provenance, or fail closed | seamless-success fiction or merged Provider streams | fallback fake |  |
| `R-02` | synthesis Provider fails before first audio or midstream | exact failed/partial outcome; fallback only if policy and presentation fence permit | replaying already presented prefix or duplicate audio | synthesis fallback matrix |  |
| `R-03` | page/transport/device restart loses nondurable speech state or fixture consent expires | old session fenced; new explicit request required; retained audio deleted/blocked per manifest | resurrecting capture/playback or reusing expired recording | recovery/privacy tests |  |
| `R-04` | later Adapter cannot expose required provenance/cancel/timing | capability downgrade, compatibility-only mode or unsupported | relabeling incomplete Adapter as conformant streaming Port | conformance negative |  |
| `I-01` | session/scope/response/provider identity mismatch | reject before content or device/Provider effect | cross-session transcript/audio or foreign response playback | identity fixtures |  |
| `I-02` | resolver receives missing, unauthorized, expired or redacted ContextRef | ignore/reject per policy and record reason; raw hypotheses remain usable | reading repository/Session context by ambient access | resolver scope tests |  |
| `I-03` | raw audio/display text contains secret/path/personal data | no persistence by default; render/redaction transformation explicit and scoped | hidden upload/storage/logging or display mutation | privacy/render fixtures |  |
| `I-04` | fallback/provider diagnostic contains sensitive payload | stable safe error plus protected diagnostic reference | leaking raw audio/transcript/credential in client error | error/redaction tests |  |
| `F-01` | Browser recognition exposes only first candidate or omits confidence/timing | explicit Browser fallback provenance and unknown capability fields | made-up alternatives/confidence/timestamps | Browser API fake |  |
| `F-02` | Browser synthesis exposes no audio bytes/chunk cursor/reliable duration | control-only compatibility events; presented remains unknown until real Presentation ACK | fake chunks/cursor or onStart-as-presented | Browser synthesis fake |  |
| `F-03` | preferred Provider unavailable or request needs unsupported streaming/cancel/locale | policy selects one compatible declared fallback or returns stable unsupported/unavailable | silent downgrade that violates requested safety/capability | negotiation fixtures |  |
| `F-04` | formal Speech Port capability/feature flag off | current Browser Demo/Chat/TTS flow and 46 focused tests remain unchanged; new effects/store writes 0 | hybrid formal IDs/events entering legacy path | compatibility regression |  |
| `K-01` | current first-alternative transcript/local generation enters Adapter boundary | retained only as raw Browser compatibility facts | promoting local generation/transcript to canonical commit or confidence | adapter characterization |  |
| `K-02` | legacy localized error/message lacks stable code/provider provenance | map only when exact source is known; otherwise legacy/unknown diagnostic | parsing message text as stable error oracle | error fixtures |  |
| `K-03` | current TTS sanitizer removes/transforms code, URL, media, path or token spelling | emit explicit render transformations and span mapping while preserving current display and lossless chunk join | silently adopting sanitized text as chat/history truth | existing 10 + new render fixtures |  |
| `K-04` | old `tts.synthesize` path remains unregistered or returns late base64 audio | labeled legacy unavailable/stale result and owner fence; not formal Port success | enabling hidden server dependency or stale playback | legacy request fake + 2 owner tests |  |
| `X-01` | raw final→resolver→critical gate→Interaction fake | provenance/decision round-trip exact; only eligible fake may request a TurnCommit | Port directly dispatching Agent/Tool/Task | component integration |  |
| `X-02` | Port scaffolding beside current Browser Demo/Chat/TTS | existing 46 tests, affected TypeScript and production build pass with flag off | regression, duplicate listening/speaking or altered legacy message | regression/build |  |
| `X-03` | fixed consented/synthetic corpus through fake/resolver/metric harness | per-sample CER/WER, critical error, clarification, wrong dispatch, latency and fallback values reproducible | aggregate-only claim or wrong dispatch >0 labeled pass | offline harness |  |
| `X-04` | later real SR-B/C or SS-B/C + AIO/RM/Windows candidate | exact build, Provider, device, locale, environment, corpus and latency/quality/stop evidence required | using fake/Browser compatibility green to claim real-device or production closure | later D-032 Gates |  |

#### Bounded P1 Speech Port work packages for a non-Sol executor

1. `SP-N1 — shared speech fixtures`: after `ACG-B1`, implement only v2 speech capability/provider/error/session/event schemas, deterministic fixture serialization and invalid-fixture tests. Do not select or call a real Provider.
2. `SR-N1 — recognition Port/fake`: implement RecognitionSession interfaces, pure reducer, deterministic batch/stream fake, ordered events, cancel/idempotency and stale-generation tests. No browser, microphone, Gateway or Agent wiring.
3. `SR-N2 — resolver and critical gate`: implement immutable raw-hypothesis fixtures, scoped deterministic resolver, audit trail and critical-token decision table with zero-effect spies. Do not create TurnCommit or authorization logic.
4. `SS-N1 — synthesis Port/fake`: after shared response identity fixtures exist, implement SynthesisSession interfaces, pure reducer, deterministic audio/control fake, ordering/cancel/fence tests. No playback or real TTS call.
5. `SS-N2 — render plan`: implement display hash/source span, speakable copy, explicit transform provenance and Unicode-safe mapping while retaining current sanitizer/chunker compatibility. Do not write chat/history.
6. `SP-N2 — conformance and compatibility`: run shared fixture/conformance negatives, Browser capability characterization, feature-off 46-case regression, affected type/build and privacy/metric harness skeleton. Real recordings, Provider benchmarks and Adapter wiring remain excluded.
7. `SP-S2 — Sol post-review`: review each actual diff and final evidence separately for `SR-A` and `SS-A`, update every applicable Result cell, judge `CLOSED/PARTIAL/BLOCKED`, and authorize SR-B/SS-B only where dependencies and conformance truly pass.

The non-Sol execution record is intentionally blank:

| Non-Sol package | Executor / model | Started | Finished | Implementation result | Changed files / diff | Tests / evidence | Unresolved / return to Sol |
|---|---|---|---|---|---|---|---|
| `SP-N1` |  |  |  |  |  |  |  |
| `SR-N1` |  |  |  |  |  |  |  |
| `SR-N2` |  |  |  |  |  |  |  |
| `SS-N1` |  |  |  |  |  |  |  |
| `SS-N2` |  |  |  |  |  |  |  |
| `SP-N2` |  |  |  |  |  |  |  |

Speech Port execution returns to Sol before adding a field/state/error, changing critical-token or fallback policy, treating unknown as known, promoting a Browser callback to commit/presented truth, persisting raw audio, selecting a real Provider, or crossing into SR-B/C, SS-B/C, CR-B, AIO/RM or Agent/Tool/Task wiring.

### Module test closure: P3α Task Control Core `TC-A`

- Current closure: **PARTIAL**. The D-032 source/test-level pre-review and pure-Core oracle are complete; no v2 TaskCommand/TaskEvent types, canonical reducer, fake Core/Executor, outbox model or TC conformance has been implemented.
- Sol sign-off: GPT-5.6 Sol froze `TC-A` on 2026-08-03 under D-045. This signs only the design and bounded execution instructions; it does not approve TC-B/C persistence/API, ED-A/B AutoHarness adaptation, VB/Command Adapter wiring, D0 runtime evidence, authentication, D1/D2, exactly-once or release.
- Stage / sources: P3α / V3α dependency track; ACG-1/D-042, D-016, D-018, D-024, D-026–D-034, D-041, D-045; roadmap §3.1/§7.1–7.3; full solution §5.2/§6.1/§6.2 `TC-A`.

#### Frozen module definition and authority boundary

`TC-A` is the pure, provider-neutral Task Control contract/reducer/fake slice. It owns canonical task/command/event/attempt/reconciliation records and emits explicit effects for a later Store/Executor/API layer. It does not execute Harness work, persist production data, interpret natural language, poll the Demo monitor, notify/TTS, or implement a real transport.

| Concern | `TC-A` decision | Explicit non-goal in this slice |
|---|---|---|
| formal operations | State-changing commands are `task.create` and `task.cancel`; `task.get/list/status/events` are read-only queries | promoting legacy delete/logs/recurrence or full-P3 update/input/pause/resume/reprioritize/recover |
| command identity | Stable command ID plus canonical fingerprint owns replay/conflict; request ID is one transport attempt only | retry with a new command identity after unknown result or parsing message text as result state |
| create target/spec | create targets the Task Core and carries a closed immutable TaskSpec: intent, exact scoped execution-target ContextRef/snapshot, executor binding/capabilities, origin link and side-effect class; Core allocates task ID | client-generated canonical task ID, ambient cwd/last Agent, mutable target or machine-private credentials in the record |
| canonical create unit | Logical durable unit is command ledger + task record + accepted event + original Result + first attempt-dispatch intent | TC-A itself claiming a production transaction/store or Executor side effect happened |
| task state | Core alone reduces `accepted/running/blocked/decision_required/terminal`; terminal requires `completed/failed/cancelled/interrupted/unknown` and is immutable | mapping arbitrary legacy strings by guess, nonterminal outcome, percent-as-state or terminal revival |
| attempt state | Core allocates an attempt ID before dispatch; Executor idempotently accepts the exact pair and reports `accepted/running/terminal` source events | Executor editing task state, using session/round/execution log ID as canonical attempt without an Adapter |
| event authority | Every accepted transition is an append-only canonical TaskEvent with event/producer/stream seq/scope/correlation/causation and source evidence; snapshot is derived | direct task-row mutation as lifecycle proof or WorkProgress changing lifecycle |
| outbox / delivery | Reducer emits durable-outbox intents for attempt dispatch/cancel; delivery is at least once and repeated delivery retains the same attempt/control identity | external side-effect exactly-once, rollback or allocating a new attempt on delivery uncertainty |
| cancel | accepted command records exact target and fences further Core dispatch; an undispatched task may be terminalled by Core, while an active attempt requires Executor/reconciliation terminal evidence | cancel ACK as terminal, cancelling response/round/playback, or claiming code modifications were undone |
| queries/events | get/list/status/events read one authorized snapshot and have zero command/store/outbox/Executor mutation; events returns an ordered persistent prefix with head/truncation/capability facts | query-driven repair, live subscription, cross-connection cursor replay or Harness raw-log API in TC-A |
| restart reconciliation | Nonterminal attempts are fenced from redispatch and queried by original attempt ID. Exact fact continues/terminates; confirmed lost D0 context becomes interrupted; temporary uncertainty remains pending in a separate reconciliation record | borrowing a new Agent, silent retry/resume, `running→success`, or treating temporary Executor unavailability as terminal |
| authorization | Core invocation receives a trusted out-of-band AuthorizationContext bound to principal/scope/operation/target/command/capability/required confirmation; ContextRef is not permission by itself | trusting client payload, D-033 request consistency or natural-language text as production authorization |
| origin and isolation | Task may retain origin interaction/session references for routing/audit but lifecycle outlives voice/session/media; task state never enters Session History | interaction close/barge-in/response cancel changing task lifecycle |
| WorkProgress | A separate Adapter projects only an already appended TaskEvent with source provenance/known facts; Runtime decides notification | Core/Bridge guessing progress, directly calling TTS or projection feeding back into task state |
| current scheduler | AutoHarness + fixed `extended_evolve_pipeline` is a later isolated D0 Executor Adapter target and compatibility evidence | treating schedule row/history/log or single-process JSON lock as the formal Core/Event Store |

Implementation dependency: `TC-A` waits for `ACG-B1/B2/B3` identity/envelope/state/event/capability/error fixtures. It may use a deterministic in-memory fake Store/Executor only. Real atomic storage, outbox, API, restart and event query are `TC-B/C`; Executor contract and AutoHarness mapping are `ED-A/B`; authorized structured and natural-language adapters are separate Gates.

#### Existing implementation and test inventory reviewed before design

| Existing source/test | Cases / layer | Why retained | What it proves / does not prove | State |
|---|---|---|---|---|
| `task_store.py`, `service.py`, `scheduler.py` + `test_schedule_task_service.py` | AutoHarness Foundation, 57 named tests | Protects per-path single-process create ledger, target/context pinning, status/cancel/delete races, execution history and orphan-running repair | Strong compatibility foundation; no v2 command/event/attempt/outbox authority, cross-process CAS or production auth | existing compatibility |
| `agent_ws_server.py` schedule boundary + `test_schedule_request.py` | server routing, 7 named tests | Protects server-derived owner scope, exact project target, pin release and read/cancel calls without borrowing Agent | D-033 request consistency only; not authenticated Task Core API | existing compatibility |
| prior backend verification | schedule request/task service, **104/104 runtime cases PASS** at recorded candidate | Preserves the last full Foundation evidence across parameterized cases | Not rerun for this docs-only design and not TC-A conformance | prior evidence |
| `liveVoiceTaskClient.ts` + test | Demo client, 7 tests | Protects fixed pipeline, persisted session/target, exact ID and exact-key reconciliation requests | Legacy schedule wire, not TaskCommand/QueryEnvelope | existing compatibility |
| `liveVoiceTaskBridge.ts` + test | restricted natural-language Demo bridge, 43 tests | Protects committed fixed grammar, confirmation, unknown mutation latch, exact-key reconcile and A→B successor truth | Not a general Voice–Task Bridge or canonical task owner | existing compatibility |
| `liveVoiceTaskAdapter.ts` + test | UI integration, 14 tests | Protects flag-off, context drift, stale async effects and task feedback ownership | Page-memory projection; D-031 monitor remains unimplemented | existing compatibility |
| `live_voice_contract.py` + test | strict minimal v1, 16 named tests | Protects exact cancel scopes, minimal WorkProgress and commit side-effect gate | v1 lacks TaskCommand/Event/attempt/outbox/ContextRef v2 | existing compatibility |

The existing tests are mandatory compatibility gates. The 64 named frontend task tests and prior 104-case backend pass do not fill any `TC-A` Result cell; `needs_human`, `pending`, `success`, execution history and localized errors remain legacy facts until a later ED Adapter maps them with provenance.

#### Planned `TC-A` test inventory and frozen oracle

| Planned group | Layer | Why | Scenario IDs | Oracle / forbidden result | Execution state |
|---|---|---|---|---|---|
| TaskCommand/Query/Result/TaskEvent schemas | v2 fixtures/cross-language | Freezes closed fields, identity, origin, target, scope and exclusive result shapes | `P-01..04`, `N-01..04`, `B-01..03`, `I-01..03`, `K-01` | exact round-trip/reject; no coercion/default authority |  |
| task/attempt transition tables | pure reducer/property | Makes Core the sole lifecycle owner and terminal immutable | `P-01..04`, `S-01..04`, `T-02`, `K-02` | one legal next state/event or zero mutation; outcome exact |  |
| create command ledger/fingerprint | pure fake Core + canonical bytes | Proves replay/conflict independent of transport retry | `P-01`, `N-02`, `B-04`, `C-01..02`, `R-01` | same command returns original result; conflict effects 0 |  |
| logical transaction/outbox model | state/effect reducer + failure injection | Defines what TC-B must commit atomically and deliver at least once | `P-01..02`, `T-01`, `C-02..03`, `R-01..02`, `X-01` | no ACK without complete logical unit; no new attempt on retry |  |
| Executor source-event validator | deterministic event-script fake | Prevents Executor from mutating Core or confusing tasks/attempts | `P-02..03`, `N-03`, `T-02..03`, `C-03`, `I-02`, `F-01` | exact scope/attempt/seq/evidence or quarantine/reject; effects 0 |  |
| exact task.cancel matrix | reducer + Executor/control spies | Separates request ACK, dispatch fence and authoritative terminal | `P-03`, `N-04`, `S-03`, `T-04`, `C-04`, `I-03`, `X-02` | one exact control effect; unrelated cancels 0; race truth retained |  |
| read-only query/property suite | fake Store mutation counters | Ensures get/list/status/events never become repair/mutation APIs | `P-04`, `N-01`, `B-03`, `C-01`, `I-01`, `F-02` | command/event/outbox/Executor counters all 0 |  |
| restart reconciliation state/effect table | fake clock/Executor status script | Makes D0 process loss honest without hidden resume | `R-02..04`, `S-04`, `T-03`, `F-01`, `X-03` | original attempt only; pending uncertainty or sourced terminal; redispatch 0 |  |
| AuthorizationContext and ContextRef gate | injected principal/policy fakes | Prevents request consistency or resource reference becoming authorization | `N-01`, `I-01..04`, `F-03`, `K-03` | deny before content/existence/mutation; safe exact error |  |
| TaskEvent→WorkProgress projection | pure source-event Adapter fake | Preserves lifecycle provenance while keeping projection non-authoritative | `P-04`, `N-03`, `T-02`, `F-04`, `K-04`, `X-04` | one source-derived projection; unknown stays unknown; TTS/state writes 0 |  |
| legacy compatibility characterization | existing schedule/client/bridge/adapter suites | Blocks accidental replacement of Foundation wire before ED/TC-B Gates | all `K`, `F-02..04`, `X-04` | flags off and old routes unchanged; no v2 label on legacy rows |  |

#### `TC-A` P/N/B/S/T/C/R/I/F/K/X scenario matrix

| ID | Preconditions / input | Expected state/output and allowed effect | Explicitly forbidden | Planned evidence | Result |
|---|---|---|---|---|---|
| `P-01` | Authorized valid create command with new command ID/fingerprint and immutable TaskSpec | allocate one task and attempt ID; emit accepted event, original result and dispatch outbox in one logical unit | Executor call/ACK before durable unit or client-chosen task ID | fake Core transaction |  |
| `P-02` | Exact Executor accepts attempt then reports ordered accepted→running | append canonical events and reduce task/attempt to running; correlation/provenance retained | Executor direct snapshot write or session state mutation | event-script fake |  |
| `P-03` | Exact cancel for undispatched task or active attempt | persist/replay one cancel record; fence dispatch; Core terminal-cancels undispatched task or routes one active-attempt control | ACK-as-terminal for active attempt or canceling another owner | cancel reducer/spies |  |
| `P-04` | Authorized get/list/status/events and TaskEvent→WorkProgress read | exact scoped snapshot/event prefix/projection returned with zero mutation | implicit reconcile, claim, retry, notification or TTS | query/projection suite |  |
| `N-01` | partial/uncommitted intent, missing trusted AuthorizationContext or unauthorized operation | stable reject before TaskSpec content/store/outbox/Executor; all effects 0 | task/command/event allocation or existence disclosure | auth/effect spies |  |
| `N-02` | same command ID with different intent/target/context/executor/capability/side-effect fingerprint | `CONFLICT/IDEMPOTENCY_CONFLICT`; original result/task untouched | second task/attempt/event/outbox | command ledger tests |  |
| `N-03` | event has wrong/missing task/attempt/scope/producer/seq/causation/outcome or unsupported type | reject/quarantine with canonical snapshot/effects unchanged | best-effort mapping or WorkProgress emission | event validator fixtures |  |
| `N-04` | cancel targets missing/foreign/terminal/wrong-scope task or lacks exact confirmation where policy requires | safe NOT_FOUND/denial/conflict/already-terminal result as policy permits; mutation/control 0 | wrong-task destructive operation or target existence leak | cancel/auth matrix |  |
| `B-01` | first task/event/attempt sequence, non-empty minimum IDs, max supported payload and counter | exact accept within declared limits | zero-ID reuse, overflow wrap or silent truncation | schema/property tests |  |
| `B-02` | empty/whitespace/Unicode/wrong-type IDs, timestamps, enums, outcome, TaskSpec fields | closed-schema exact reject or explicitly supported Unicode | trim/coerce/localized-message oracle | fixture negatives |  |
| `B-03` | events query empty log, exact head, bounded page, truncation/gap and known-empty facts | honest empty/prefix/head/truncated/capability shape; zero writes | missing range claimed complete or query-triggered repair | query fixtures |  |
| `B-04` | canonical fingerprint ordering, equivalent serialization, ContextRef ordering and maximum valid command replay | semantically canonical same command replays original exact Result | incidental JSON order creating second task or excluded mutable fact omitted from conflict | fingerprint corpus |  |
| `S-01` | every allowed task transition among accepted/running/blocked/decision_required/terminal | exact canonical event and state; terminal outcome only at terminal | skipped/backward/undeclared transition | exhaustive transition table |  |
| `S-02` | every allowed attempt transition accepted→running→terminal | exact attempt event and task projection rule | attempt blocked/decision state or Executor-owned task transition | attempt table |  |
| `S-03` | cancel requested/accepted/replayed/result_unknown while task nonterminal | orthogonal cancel record/fence changes; lifecycle remains source-driven | timeout/ACK→cancelled | cancel state tests |  |
| `S-04` | reconciliation required→in_progress→resolved/result_unknown around unchanged lifecycle | separate reconciliation record advances; task changes only on accepted evidence/decision event | adding hidden lifecycle state or silent redispatch | reconciliation table |  |
| `T-01` | crash/failure injected before/after each create logical-unit boundary and outbox delivery | before commit no visible task; after commit replay returns same task/attempt and redelivers same outbox identity | partial ACK, orphan task without command/event or new attempt | transaction model fault injection |  |
| `T-02` | TaskEvent duplicate/conflicting duplicate/gap/out-of-order/backward/late terminal | identical canonical duplicate no-op; conflict/gap quarantined; terminal immutable | wall-clock ordering or speculative state/projection | event sequence suite |  |
| `T-03` | Executor terminal/status response arrives during restart reconciliation, disconnect or Core instance change | exact attempt evidence applied once by Core instance/stream rules | old instance event mutating new authority without reconciliation | deferred fake |  |
| `T-04` | cancel command, outbox delivery, Executor completed/failed/cancelled and timeout arrive in every order | one cancel command/effect; first valid canonical terminal truth wins; unknown remains non-success | forcing cancelled after completed/failed or double control | race matrix |  |
| `C-01` | concurrent duplicate create/query deliveries | one task/attempt/logical unit and identical create Result; queries remain read-only | two allocations or query lock causing mutation | barrier/property test |  |
| `C-02` | different commands race same ID or same target | deterministic ledger winner; conflict loser effects 0; independent IDs remain isolated | merged intents or cross-command Result | command barrier |  |
| `C-03` | at-least-once attempt dispatch/event delivery across multiple workers | Executor dedups same attempt; Core accepts each canonical event once | two live executions for one attempt or two external side-effect starts | fake Executor dedup/barrier |  |
| `C-04` | concurrent same/different cancel commands for same/different tasks | same identity replay, conflict exact, different tasks isolated | global cancellation latch or widened target | multi-task control spies |  |
| `R-01` | create/cancel Result lost after logical commit | retry same command ID/fingerprint returns stored Result and same effects identity | new command/task/attempt or unsafe automatic mutation | ledger replay fault test |  |
| `R-02` | Core restarts with accepted task and undelivered/delivered-unknown outbox | fence then deliver/query the same attempt ID according to durable outbox/evidence | allocating replacement attempt or assuming not executed | restart fake Store |  |
| `R-03` | restart finds running attempt; Executor reports active, terminal, confirmed lost, or temporarily unavailable | preserve running, append exact terminal, append interrupted for confirmed D0 loss, or keep lifecycle plus reconciliation pending | `running→success`, borrowing Agent/context or unavailable→failed | reconciliation matrix |  |
| `R-04` | evidence permanently irreconcilable under explicit bounded Core policy | explicit reconciliation event may terminal `unknown` with provenance and operator-visible reason | unknown→completed or silent record deletion | policy fixture |  |
| `I-01` | wrong principal/owner/project/task scope on any command/query | deny before content and all mutation; safe error obeys existence-hiding policy | cross-scope list/get/event disclosure | auth fixtures |  |
| `I-02` | Executor identity/capability/attempt binding differs from persisted dispatch | reject/quarantine; task and outbox remain reconcilable | accepting event because task ID alone matches | executor-binding tests |  |
| `I-03` | confirmation/authorization binds another operation, task, command ID or stale target snapshot | fail closed with cancel/create effects 0 | reusable blanket confirmation or ContextRef-as-grant | policy tests |  |
| `I-04` | task context contains secret, expired/redacted/unversioned destructive ContextRef | reject before disclosure/mutation; serialize only safe refs/diagnostics | secret in TaskEvent/log/WorkProgress or destructive ambient access | context/redaction tests |  |
| `F-01` | Executor lacks cancel/status/idempotent-attempt or is unavailable | capability-specific unsupported/unavailable; Core preserves/fences exact record | fallback to another Executor with new semantics or fake terminal | capability fake |  |
| `F-02` | formal TC capability/feature flag off | current schedule/API/Demo behavior and persistence writes remain unchanged; TC timers/effects 0 | hybrid task IDs/events or replacing legacy status | feature-off regression |  |
| `F-03` | production authentication/authorization capability absent but D-033 consistency scope exists | formal Core external mutation disabled; labeled legacy Adapter may retain existing behavior | production-security claim or upgrading asserted app/session fields | auth capability tests |  |
| `F-04` | WorkProgress projection/subscription/replay capability absent | task query/events remain usable as declared; unknown/projection unavailable explicit | Core calling TTS or inventing progress | projection capability fixtures |  |
| `K-01` | legacy `sch_*`, schedule payload, idempotency key and request error reach formal boundary | remain compatibility metadata or map through a later explicit Adapter with provenance | relabeling row/history/log as v2 TaskEvent/Core record | compatibility fixtures |  |
| `K-02` | legacy pending/running/success/failed/cancelled/needs_human/pr_created/skipped status | ED Adapter must use a reviewed explicit mapping/source event; unknown remains unsupported/unknown | TC-A guessing outcome or changing scheduler enum | Adapter contract negative |  |
| `K-03` | current owner/project scope is request-derived D-033 consistency | enforce existing isolation on legacy path but do not create formal AuthorizationContext | claiming authenticated tenant isolation | server compatibility tests |  |
| `K-04` | D-031 page monitor or Bridge observes schedule status/progress/error | remains read-only legacy projection and never becomes Core event source | UI poll updating canonical task or direct notification from Core | integration characterization |  |
| `X-01` | TaskCommand→fake Core logical unit→outbox→deterministic Executor accepted/running/terminal | IDs/fingerprint/seq/causation/outcome preserved; exact one task/attempt | synchronous slow execution in API ACK path | fake vertical slice |  |
| `X-02` | exact cancel through fake Core/Executor while unrelated response/round/playback/task owners exist | only exact task/attempt control called; authoritative race result preserved | unrelated cancel calls or rollback claim | four-owner integration fake |  |
| `X-03` | fake durable snapshot/outbox restart with every nonterminal point | no stale unexamined running state; each record active, terminal or visibly reconciliation-pending | hidden automatic rerun | restart sweep |  |
| `X-04` | canonical TaskEvent→WorkProgress fake and legacy system beside formal flag | exact source projection; legacy 104 backend + 64 frontend named tests/affected builds remain green | projection mutating Core/TTS or legacy regression | integration/regression |  |

#### Bounded `TC-A` work packages for a non-Sol executor

1. `TC-N1 — schemas and transition fixtures`: after ACG primitives, implement closed TaskSpec/command/query/result/event/attempt/reconciliation types and exhaustive valid/invalid JSON fixtures. No service/store/API edits.
2. `TC-N2 — pure canonical reducer`: implement task/attempt/cancel/reconciliation transition tables, immutable terminal behavior, source-event validation and deterministic effects with property tests. No AutoHarness imports.
3. `TC-N3 — fake Core ledger/outbox`: implement an in-memory deterministic command ledger, canonical fingerprint, logical transaction fault model, outbox identities, at-least-once fake Executor and read-only query/event-prefix behavior. It is not production persistence.
4. `TC-N4 — authorization/projection/compatibility conformance`: implement injected AuthorizationContext fakes, ContextRef gates, TaskEvent→WorkProgress pure projection, explicit legacy non-promotion/feature-off tests and affected existing regression commands. Do not map actual AutoHarness statuses or wire transport.
5. `TC-S2 — Sol post-review`: inspect the actual types/reducer/effects/fake/test diff, update every Result cell, decide `TC-A CLOSED/PARTIAL/BLOCKED`, and separately authorize `TC-B/C` and `ED-A`; no real Store/Executor work inherits closure automatically.

The non-Sol execution record is intentionally blank:

| Non-Sol package | Executor / model | Started | Finished | Implementation result | Changed files / diff | Tests / evidence | Unresolved / return to Sol |
|---|---|---|---|---|---|---|---|
| `TC-N1` |  |  |  |  |  |  |  |
| `TC-N2` |  |  |  |  |  |  |  |
| `TC-N3` |  |  |  |  |  |  |  |
| `TC-N4` |  |  |  |  |  |  |  |

`TC-A` execution returns to Sol before adding an operation/state/outcome/error, changing command fingerprint or atomic-unit membership, weakening exact-task/authorization/event provenance, mapping a legacy scheduler status, choosing a Store/Executor, treating ACK/unknown as terminal success, creating a retry attempt, or crossing into TC-B/C, ED-A/B, Command Adapter, VB, D1/D2, exactly-once or rollback.

## Accepted boundaries that affect upcoming work

- D-032: this checkpoint originally required module-by-module pre/post review and every applicable matrix dimension. D-046 supersedes that universal process with Tier 0–3 review: only Tier 2/3 state, side-effect, shared-contract, release, and similarly high-risk boundaries require scoped or complete Sol pre/post review and their applicable scenario dimensions.
- D-033/D-034: current Web owner/project scope is single-user request consistency, not authentication. D-031 promises same-page reconnect only. Required identity/status/target/provenance fields fail closed; missing optional progress/error displays `unknown`; deleted/missing/error outcomes are not success.
- D-039: Browser Speech remains a fallback. Dedicated ASR and any future Native Audio Engine must implement one provider-neutral Speech Port with auditable hypothesis/provenance and critical-token safety. No provider has been selected; current sequencing is governed by D-046 rather than the former D-031-first statement.
- D-041: reserve GPT-5.6 Sol for cross-module contracts, high-risk state/ownership/safety/durability decisions, applicable risk-tier pre/post review, and closure or release judgments. A non-Sol execution model implements bounded work packages only after the consumed semantics and test oracles are frozen, and must return unresolved ambiguity instead of inventing behavior. D-046 now requires a one-week rolling queue led by the ACG critical kernel and cumulative Integrated Demo, with dependency-safe P1/P2/P3alpha parallelism; D-031 runs only after its explicit go decision.
- D-042: ACG-1 freezes the complete target as `live-voice.contract.v2`; strict minimal v1 remains a Foundation compatibility input. Under D-046, only the critical kernel blocks initial parallel consumers; extensions become local dependency gates before the B/C wiring that consumes them. This record does not claim any slice is implemented.
- D-043: `CR-A` uses a server canonical Conversation Runtime plus frontend validating replica. Response lifecycle/cancel/presentation are separate; old request/message/epoch/final markers remain compatibility facts only.
- D-044: P1 `SR-A/SS-A` preserves immutable raw hypotheses and display text, makes resolution/render transformations auditable, and leaves commit/presented truth to Interaction/Presentation authorities. Browser Speech remains a capability-limited fallback, not a selected production Provider.
- D-045: `TC-A` owns canonical command/event/task/attempt/reconciliation records and at-least-once outbox identities. Existing AutoHarness scheduler is a later D0 Executor compatibility target; its JSON row/history and request-derived scope are not formal Core, durable event store or production authorization.

## Known gaps

- Browser Speech first-pass fidelity remains weak for Chinese homophones, negation, English technical terms, paths, SHAs, dates, and numbers.
- V0 supplement success is not a production response/generation fence; side-effecting tool cancellation, hard process resource limits, and cross-process cancellation remain open.
- No production streaming-media transport, VAD/AEC/duplex device matrix, provider SLO, privacy retention system, or multi-language closure exists yet.
- Task projection is page-memory state; full-page reload recovery and durable command journal are not implemented.
- No v2 shared envelope/state reducer/conformance runner exists yet. ACG-1 is a design Gate only; Browser Speech and AutoHarness are limited first adapter targets, not production Provider/Executor closure.
- No CR-A response Runtime, P1 Speech Port, or TC-A Task Core implementation exists yet. Their complete design matrices and blank non-Sol work-package records are handoff inputs, not test evidence.
- Formal Task Core still lacks an atomic command/event/snapshot/outbox Store, authenticated AuthorizationContext, Executor attempt conformance, `events` API and restart reconciliation; current single-process JSON guarantees must not be upgraded by wording.
- Credentials, provider configuration, project records, browser permissions/devices, runtime data, and network state remain machine-private.

## Verification ledger

- V0 exact-SHA acceptance: Gate 0–6 PASS; see immutable evidence.
- Runtime tested SHA for the cleaned integration: `ac988b85e8a21eb4f378086bab58dac6a4d55d82` (only documentation was uncommitted during this verification).
- D-037 guard: `test_circuit_breaker_repeated_failure.py` **20/20 PASS**; the exact adapter regression case modified by `ee2896a4` **1/1 PASS**.
- Post-V0 backend: Live Voice contract/Web handler **122/122 PASS**; schedule request/task service **104/104 PASS**.
- Post-V0 frontend: 12 focused Live Voice scripts (core, turn/recognition lifecycle, TTS ownership/text, message gate, supplement quarantine, streaming speech, task client/adapter/bridge, chat streaming) all PASS; TypeScript + Vite production build PASS.
- Adjacent non-Live-Voice observation: the complete `test_agentserver_modes.py` run produced **74 PASS / 1 FAIL** because pytest promoted unclosed-socket `ResourceWarning` cleanup into an exception group in `test_deep_adapter_routes_team_simplify_answer_by_evolution_meta`; that case passes when isolated. It is retained as a flaky cleanup gap and is not represented as a clean full-file pass.
- Documentation integrity for the current uncommitted Sol batch: 107 Markdown link targets enumerated, including 78 local targets resolved with zero broken paths; every D-031/ACG/CR-A/P1/TC-A matrix contains all P/N/B/S/T/C/R/I/F/K/X categories; all 22 non-Sol execution rows remain blank; no tracked `docs/zh/live-voice/` duplicate; `git diff --check` PASS. Final ancestry/exclusion checks still run after any approved documentation commit and before a separately approved push.

## Resume checklist

1. Verify clean/expected worktree, `HEAD`, branch, upstream, and ahead/behind.
2. Read [README.md](README.md), this file, and only the task-routed documents.
3. Confirm the next slice is still D-031 unless a newer accepted decision changes it.
4. Re-establish private runtime conditions only when the task needs real E2E.
5. Follow the root `AGENTS.md` approval gate separately for every commit and push.
