# Deep integration audit and execution

## Scope and evidence

User-authorized audit/refactor; Host baseline `948cfc7920fd35fdf0f4b9a476cd567bb4af9108`,
SDK baseline `2d87926c0903fb9b130c8ca6fa8129d978168200`. Both initially clean.
SDK branch has no upstream. No history rewriting, remote update, deployment,
production data migration, or latency-policy changes. The 15-second prepared
response timeout is explicitly deferred.

This record distinguishes inspected calls from proposed reuse. Extraction into
`core.application.tasks` is not evidence of native integration. The frozen
before manifest uses the existing official-baseline physical-line accounting.

## Initial code-level decision table

Paths beginning `core/` and `agent_teams/` below are under SDK `openjiuwen/`;
Host paths are under `jiuwenswarm/`. Decisions are not completion claims.

| Responsibility/current implementation | Native capability and actual entry | Overlap / decision | Removed implementation, authority and acceptance |
|---|---|---|---|
| Task admission, commands, outbox, attempts: `core/application/tasks/persistent_task_core.py` → `task_store.py` | `core/controller/modules/task_manager.py`, scheduler `execute_task`; Team DAO `create_task/start_task/claim_task` | Partial: Controller session tasks and Team assignments lack the same command/attempt/effect transaction; retain delivery authority, audit reusable management individually | No forced second Controller record. SQLite is delivery authority; verify replay, scope, cancel, adjust and recovery |
| Project execution: SDK `project_executor.py` `_run` path calls `process_background_code_task_stream` | Host facade → existing Code adapter `process_message_stream_impl` → SDK Agent | Existing Agent is reused; attempt checkout/journal/file application are added guarantees, not a new model loop | Preserve isolated attempt identity and project/index bytes; real Git/files required |
| Task checkpoint: Host facade installs dynamic callbacks on `JiuSwarmStreamEventRail` | SDK `AgentCallbackManager.execute`, `scoped_agent_rail`, `AgentRail` model/tool hooks | Native enhancement implemented after rejecting root-registry-only binding | Dynamic Host model/file fields and invocation removed; retain cached-instance/session identity adapters; real model/file/Host regressions verify rejection before effects |
| Legacy Task contracts: Host `formal_tasks/task_core.py`, `VoiceTaskBridge.map` | Production uses SDK `FormalTaskSpec`, `PersistentTaskCore`; registry uses `resolve_production` | Legacy models/map have no located production caller; verify all consumers before removal | Remove obsolete production model/bridge path; retain current production resolver and wire route enums |
| Work: SDK `WorkRuntime` + `SqliteWorkStore`; Host `HostWorkService` | SDK Controller scheduler `cancel_task` cancels coroutine; Harness `AsyncToolRuntime` injects completion into owning round | Partial: Work requires durable admission, CAS, UNKNOWN and physical settlement; blind substitution loses these guarantees | No automatic Task card; checkpoint remains authoritative. Compare common management without copying completion into another ledger |
| Host execution: `runtime/session/coordinator.py` + `work_scheduler.py` | `AgentRuntime` runs ordinary Agent streams; `RuntimeSessionCoordinator.run_stream/cancel_execution` tracks transient executions | Existing per-session scheduling is LATEST_FIRST and closes with session; durable background work must survive speech session end | Trace lifetime before adoption. `SessionExecutionService` named in old docs does not exist in current production source |
| Agent selection/configuration: product registry calls `AgentManager.get_agent/pin_agent`; formal binding creates attempt Agent | Host `server/runtime/agent_manager.py` owns configured Agent instances | Already partially reused; Voice still orchestrates producer allocation | Keep Host as selection/lease authority; verify wrong project/config and delayed cleanup |
| Session identity/project scope | Host `runtime/session_provisioner.py`, session manager/project store; Voice registry adds scope and source proof | Host product session versus voice generation are distinct; Host ingress verified; activation/source proof remains an application capability | Preserve welcome-page create and scope; no new authorization policy |
| Persistence/checkpoint | SDK `DefaultDbStore` exposes async SQLAlchemy engine; session checkpointer uses KV serialization | Generic storage exists, but does not supply multi-table outbox or Work CAS semantics | Do not replace transaction guarantees with KV writes; separate transaction entrypoints retain table-specific locking, error translation and injected scope/input checks |
| Results/events/notifications | SDK Task event subscription and verified result reader; Host Work journal and Voice playback ledger | Execution result, event delivery and heard-audio acknowledgement are different facts | Retain required projections; audit duplicate query/observation mechanisms |
| Frontend/history/connection/config/auth/observability | Existing Host/Gateway entries plus dedicated Voice state | Host create/history/Gateway/config entries traced below; broad elimination of the Voice coordinator is not proved | Do not credit path ownership as reuse; unchanged audio/Provider evidence is not a new acceptance run |

## Implementation order and risk

1. Task: remove proven dead production contracts; connect checkpoint enforcement
   to native SDK lifecycle hooks, preserving ordering and fail-closed behavior.
2. Work: inspect common management and Host producer lifetime; converge only
   equivalent behavior, retaining durable UNKNOWN/settlement semantics.
3. Host/Voice: finish ingress, context, configuration, scope, presentation and
   frontend audit; remove demonstrated duplication and correct architecture.
4. Run affected tests/review, reproduce final counts, and commit one coherent
   final change per repository where possible.

Checkpoint integration is Tier 3 (tool-effect enforcement). Owned surfaces are
SDK checkpoint/Agent hooks, Host background facade and stream rail, their real
SDK model/tool/file tests. Positive adoption/write must succeed; wrong root,
session, closed binding and rejected plan must cause zero forbidden calls/writes.
Persisted schema and admission policy are unchanged. Required regression covers
adjustment, cancellation and project durability. Full external Provider/device
acceptance is outside this code seam; no new audio performance claim is made.

## Status

PARTIAL / IN PROGRESS. Bounded native callback integration and duplicate removal
are implemented; Task/Work management is not mechanically unified with
Controller/Team, and removing the full Voice runtime from Work execution remains
unproved. This record is not full product-candidate closure. User session `web_1a09c8505b1_6bce26af6cd4` did not verify running cancel;
weather Work produced city clarification, not a successful weather lookup.

## Rejected checkpoint replacement (no production change retained)

A direct `TaskCheckpointRail` registered only on the attempt root's native
callback manager was implemented and exercised against the existing real SDK
file-tool seam. The focused run had 48 passes and 2 failures. In particular,
`test_real_facade_sdk_tool_registration_and_pre_write_boundary[wrong_root]`
performed the forbidden temporary-file write: the SDK chooses callbacks using
the Agent in the callback context, so the attempted replacement's root callback
was bypassed. The old shared Host stream rail carried the exact-root check into
that path. The `closed` case also exposed earlier exception propagation relative
to stream cleanup. All source and test edits for this experiment were reverted.

Decision at that experiment: retain the exact Host identity/checkpoint adapter
until an equivalent native enforcement boundary is proven. The later scoped
native enhancement below supersedes this temporary retention of dynamic hooks. Registering a native rail is not enough;
no counts or integration credit are assigned to this rejected experiment. The
original callback-registry replacement proposal in the table is superseded by
this evidence. No production or user project was used by these tests.

## Scoped native callback enhancement (2026-09-14, Tier 3)

The failed root-registered rail is not retried unchanged. Extend the existing
SDK AgentCallbackManager with an opt-in execution-context rail scope. Scoped
callbacks normally run after ordinary registered hooks; Task file checks use
`before_events` to reject before tool/history projection, while model adoption
stays after ordinary model-context preprocessing. Guards run across
callback-manager selection; failures propagate and inherited child contexts are
revoked when the scope exits. Unscoped consumers keep existing behavior. Task
checkpoint adoption/file-plan validation uses this native facility; Host retains
only its cached-instance/session identity adapter. Remove the two dynamic
checkpoint channels from the Host presentation rail. No persisted/wire schema,
allowed-tool policy or existing consumer behavior is intentionally changed.

Acceptance: real SDK callback routing for another Agent still invokes the guard;
parallel scopes are isolated; nested scopes restore; leaked contexts fail closed;
model-adoption failure causes zero model effects; the existing real SQLite/Git/
file tool cases preserve bytes for wrong root/session, stale/closed binding and
unplanned writes. Independent review covers this new coherent boundary. This is
an enhancement to the current native callback owner, not a new scheduler or
callback framework. Ordinary registered callbacks retain their error policy.

## Final code audit details and retained semantic boundaries

### Task / Work / native management

| Concern | Actual entry and authority | Decision and evidence boundary |
|---|---|---|
| Task creation / adjustment / cancellation | PersistentTaskCore command admission → SqliteTaskStore transaction → dispatch outbox → ProjectCodeExecutorAdapter | Retain one durable application Task authority. Controller `TaskManager.get_state` serializes its in-memory indexes; adding a Controller Task would require a second state synchronization. There is no native equivalent of the existing command + attempt + outbox + effect transaction. |
| Attempts / adjustment adoption | project_executor `_run` → Host `process_background_code_task_stream` → existing Code adapter and SDK Agent; native scoped TaskCheckpointRail adopts at model boundary | Actual Agent loop reused. Removed Host dynamic callback registry; native callback manager enhanced, no new Agent loop or task scheduler. Keep request/attempt root, capability selection and immutable execution context fences. |
| Task execution lifetime | ProjectExecutionBinding.execution_agent/project_executor, attempt AgentManager lease, SDK worktree cleanup | Removed LegacyProjectTaskService protocol/constructor carrier and Host legacy startup/shutdown branches. This is a paired development API change in .4; old scheduler fixtures remain only in tests. |
| Team assignment / dependencies | `agent_teams/tools/database/task_dao.py` start_task/claim_task/cancel_task | Partial overlap. Native DAO CAS owns Team member assignment, pending status and dependency release, not work revisions or application effect attempts. No current dependency/Team assignment requirement; do not create unrelated Team rows or duplicate status. |
| Work creation / query / revision / cancellation | HostWorkService.work_runtime → SDK WorkRuntime.start/update/query/cancel → SqliteWorkStore.save | Keep SDK Work authority and Host-scoped service. Revisions/CAS, UNKNOWN/no replay, cancellation settlement and occupied capacity are necessary. Removed router's unreachable generationless/direct-facade and standalone-close alternatives. |
| Scheduling distinction | Controller TaskScheduler.execute_task/cancel_task; Harness NativeHarness.launch_async_tool → AsyncToolRuntime | Controller publishes session task events and marks CANCELED before physical coroutine settlement; Harness completion is injected best-effort into the owning model round. Neither is a durable Work outcome or heard-audio fact. Keep distinct execution modes, not a short/long split. Work does not automatically create a formal Task card. |
| Work Agent producer | NativeBusinessRouter._executor → Host AgentManager.get_agent/pin → RuntimeFormalAgentFacade → AgentRuntime.stream_owned → RuntimeSessionCoordinator | Actual Host admission, retained Agent and session generation are used; the router cannot own/close the runtime. Still allocates AgentConversationRuntime for Harness/Bridge canonical-final and cancellation settlement. This is a remaining integration opportunity, NOT justified merely by moving its directory. Direct stream replacement has not proved equivalent result/projection/cleanup semantics. |
| Recovery / results | SDK durability readers/effects/checkpoint, TaskResultReader; Work restored snapshots | Retain exact-byte/index/file-application journal and manifest verification. Checkpointer KV serialization and default DB engine do not replace multi-file effects + rollback/unknown guarantees. Real temporary Git/SQLite tests cover existing oracles; no irreversible schema migration performed. |
| Event query / subscription | task_store.events/events_page → TaskEventSubscription; Work observation cursor/epoch → Host context RPC | Durable paginated Task event sequence and revision-scoped Work change signal are different from native callback notification. Replacing them with an ephemeral EventBus loses replay/fencing. They project the same authoritative Task/Work rows, not another execution state machine. |
| SQLite | SqliteTaskStore._transaction; SqliteWorkStore._connection; Host SqliteNativeWorkJournal hooks | BEGIN IMMEDIATE, CAS and command/outbox validation remain in the transaction owner. Host journal adds accepted-input prerequisite/presentation/task-origin tables to that same Work DB; it does not fork Work snapshots. DefaultDbStore supplies an AsyncEngine, without these operations. No second storage facade added just to claim reuse. |

### Host and Voice responsibilities

| Concern | Actual existing Host call / retained adapter | Decision, deletion and limit |
|---|---|---|
| Welcome-page session | App.handlePrepareLiveVoiceSession → createLiveVoiceConversation → createConversationSession (`session.create`) → registerCreatedConversation | Shared Host product session creation, public session IDs and Zustand stores already used. Consolidated selection/plan/swarmflow configuration copying with normal App creation in newConversationLifecycle.copyNewConversationSelections. Caller-specific draft/goal transfer and source clearing unchanged. |
| Session/project authority | ServerSessionProjectAuthorityResolver calls get_session_metadata(cache_bust=True, enable_writeback=False), get_project_by_id(cache_bust=True), reads real Git revision | Host metadata/project storage is authoritative. Voice generation, committed-input/source proof and capability expiry are additional facts; public session labels alone must never authorize side effects. No new account/auth policy. |
| Agent/configuration | AgentManager.get_agent/pin/unpin and production model resolver; RuntimeFormalAgentFacade validates retained Agent and public session generation | Reuse configured Host facade. Voice-specific provider/audio settings remain distinct from Agent model config. Narrow .4 dependency verifies paired wheel imports; no private config rewritten. |
| AgentServer / connection | app_agentserver → AgentWebSocketServer creates AgentRuntime and composition registries; Gateway AgentClient/message handler routes authenticated RPC and push | AgentServer is the resident execution/container and connection composition owner, not a new algorithmic module or duplicate Agent. Voice media WebSocket/provider transport is a necessary media protocol; it does not replace Host session/config APIs. Local page/API/media origin remains 127.0.0.1 and same-origin. |
| History / presentation | SessionFormalHistoryWriter → append_formal_history_record_idempotent in existing Host session_history; PresentationLedger/Native playback acknowledgements | Shared history storage, retained Voice proof that text/audio was actually presented. Agent completion, delivered notification and heard playback must stay separate. Formal execution disables automatic chat history; only verified projection writes user-visible history. |
| Old execution bridge | AgentBridgePort created its own ThreadPoolExecutor; all located callers were test fakes | Removed production executor/request/handler/violation implementation; historical conformance fixture retained under tests/support. Production keeps only AgentEvent projection consumed by AgentBridgeRuntime and JiuWenSwarmAgentAdapter. This is production removal, not deletion of all test code. |
| Old Task models / bridge | formal_tasks/task_core.py and VoiceTaskBridge.map had only fake callers | Removed production file, TaskIntent and map. Production uses SDK FormalTaskSpec/states and resolve_production. Historical tests use clearly named legacy fixtures; direct SDK tests use the native binding, not a legacy subclass. |
| Observability | Existing Agent execution rails/logging plus Host profile_event injected into SDK WorkRuntime observer | SDK has no Voice import. Domain state-change traces and provider/audio timing correlate different boundaries. No duplicate authoritative state inferred from logs. Broad profiling/schema consolidation is not proven and receives no native-unification credit. |

No new topic classifier, Task-card policy, authorization rule, recovery replay,
provider selection or audio deadline/buffering policy is introduced. The broad
Voice coordinator/Bridge and generic Task/Work management code still exist. Their
remaining line count is not credited as deleted or natively unified. Unifying
physical execution/management beyond the inspected seams remains PARTIAL.

## Review and verification log

Independent read-only review of the coherent change found a native-binding
fixture alias (fixed), inherited-scope revocation during a suspended callback
(fixed with post-await checks), and five stale dynamic-hook tests (migrated to
real ctx.fire, preserving all original outcome oracles). Tool guard order was
corrected to precede ordinary tool projections. The real file test now uses an
actual SDK Session and a recording write_stream sink: allowed declaration/write
projects tool_call; rejected writes have zero projections and zero write inflight
records, in addition to zero forbidden files.

- Host legacy/resolver characterization: 87 passed; bridge/fake/resolver final
  group: 93 passed. These are overlapping groups, not an additive coverage score.
- Work runtime/service/journal/result ownership: 78 passed.
- Native model/file/production resolver-root final seam: 55 passed (normal,
  wrapped failure, swallowed failure, chat.error, cancel, restored stale scope).
- SDK application_tasks: 106 passed, real SQLite/Git with application-supplied
  execution capability. Combined scoped/native Rail/application run: 146 passed;
  subsequent native/ordinary-Rail run: 42 passed; final expanded before/after
  revocation tests: 8 passed. These groups overlap.
- Frontend welcome-start: 11 passed; TypeScript noEmit and Vite build passed.
  Vite existing chunk-size/dynamic-import warnings remain.
- Host project executor + formal integration group: 157 passed, 2 skipped,
  **1 failed**. `test_s6_joint_slow_conversation_detached_task_and_exact_cancel_domains`
  still calls retired `handle_p2_submit`, which returns PRODUCT_P2_SUBMIT_RETIRED
  already at the untouched baseline registry. This old joint journey has NOT
  been migrated/proved via the current unified entry. Do not report this group
  or the full candidate green; the later 55-case seam does not replace it.
- Initial paired .4 wheels built and installed in a fresh temporary target,
  imports resolved inside that target, no legacy production Task module/service
  field/map. Final native-change pair also built/installed/imported successfully;
  the import probe unwraps the standard contextmanager decorator before checking
  source ownership (an initial probe incorrectly inspected contextlib.py).

No user/provider/browser/device journey rerun. Running Task cancellation is not
established by the supplied session; weather Work was a city clarification.
The explicitly deferred NATIVE_PREPARED_RESPONSE_TIMEOUT remains untouched.

Final scoped Ruff checks passed for changed production modules and the new SDK
scope tests. Both repository diff --check checks passed; 84 local Markdown links
in changed documents resolved. The before/after manifests retain per-file hashes.
Native callback manager is an existing 145-line baseline file: only its net +60
counts as new. Final production net total is 195,295 (before 195,680), a reduction
of 385; no semantic credit is assigned solely to this count.

Verification command groups (Host cwd unless specified; all pytest runs used
`-q -o addopts= -o log_cli=false`; SDK also `-o asyncio_mode=auto`):

```text
.venv/Scripts/python.exe -m pytest tests/unit_tests/live_voice/test_background_task_checkpoint.py tests/unit_tests/live_voice/test_file_effect_plan.py tests/unit_tests/live_voice/test_project_code_executor.py::test_production_resolver_manager_real_facade_executes_exact_d0_root
.venv/Scripts/python.exe -m pytest tests/unit_tests/runtime/test_host_work_service.py tests/unit_tests/live_voice/test_native_work_runtime.py tests/unit_tests/live_voice/test_native_work_journal.py tests/unit_tests/live_voice/test_native_result_ownership.py
.venv/Scripts/python.exe -m pytest tests/unit_tests/live_voice/test_agent_bridge.py tests/unit_tests/live_voice/test_agent_bridge_runtime.py tests/integration/live_voice/test_fake_verticals.py tests/unit_tests/live_voice/test_production_multi_task_resolver.py tests/unit_tests/live_voice/test_production_multi_task_resolver_trust.py
.venv/Scripts/python.exe -m pytest tests/unit_tests/live_voice/test_project_code_executor.py tests/integration/live_voice/test_d90_formal_task_vertical.py tests/integration/live_voice/test_formal_task_executor_adapter.py
# SDK cwd, using sibling Host venv:
../jiuwenswarm/.venv/Scripts/python.exe -m pytest tests/unit_tests/core/single_agent/rail/test_scoped_agent_rail.py tests/unit_tests/core/single_agent/rail/test_rail.py tests/integration_tests/application_tasks
# Frontend cwd:
node --test tests/liveVoiceHomeStart.test.mjs
node node_modules/typescript/bin/tsc --noEmit
node node_modules/vite/bin/vite.js build
```

The fourth command retains the known retired-route failure described above.
No broad-green or fresh human/Provider acceptance claim is made. Unrelated
private configuration/runtime data and the deferred timeout remain excluded.

## Paired local revision

SDK commit: `f91bc2d5ea9650781d54db92e7acf2170b09df57`,
`refactor: integrate application task checkpoints with native rails`.
The Host commit carrying this record is its matching half and requires SDK .4.
[Isolated wheel/import evidence](../evidence/DEEP_INTEGRATION_PACKAGES_20260913.json)
records the actual built distributions and hashes; this was a temporary target
install using the existing venv's third-party dependencies, not deployment.
Both commits use the existing local-agent identity `Codex <codex@local.invalid>`
via per-command options because repository user.name/email is unset; no Git
identity configuration was persisted and no existing history was rewritten.
