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
Controller/Team. Work's Voice runtime wrapper was removed and verified in the
09-14 continuation below. This record is not full product-candidate closure. User session `web_1a09c8505b1_6bce26af6cd4` did not verify running cancel;
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
| Work Agent producer | HostWorkService.get_executor → HostWorkAgentExecutor → existing JiuWenSwarmRoundHarness → RuntimeFormalAgentFacade → AgentRuntime.stream_owned → RuntimeSessionCoordinator | 09-14 removes Work's AgentConversationRuntime/ConversationRuntimeLoop/Bridge allocation. Host admission, Agent pin and generation remain. SDK WorkRuntime owns durable state; Harness owns actual producer, exact cancel and cleanup. The result collector requires one nonempty final and COMPLETED; cancellation with failed cleanup remains UNKNOWN. This closes this execution seam, not all management overlap. |
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

## Work producer continuation (2026-09-14, Tier 2 lifecycle seam)

Follow-on acceptance scope: reconstruct the retired P2 joint scenario through
current unified committed-input admission. Own only the joint integration test
and audit documentation, with real Host session runtime, authenticated Task
composition, SQLite Core/Store and temporary project files. Controlled semantic
model/lower Agent remain test dependencies. Verify dialogue alongside accepted
Task, exact request replay, wrong scope with zero extra effects, and Voice close
without cancelling the Task. This is Tier 2 lifecycle evidence; no production
protocol, authorization policy or audio timing change. Broader old scenario
oracles remain open until each is replaced with evidence on the current route.

Starting from the paired commits above, remove the Work-only construction of a
complete AgentConversationRuntime and AgentBridgeRuntime. Reuse the existing
Host JiuWenSwarmRoundHarness reservation, actual runner/cleanup and exact cancel;
add a bounded final-result consumer on its existing handle. SDK WorkRuntime
remains the sole durable admission/revision/recovery/capacity owner. The Host
adapter owns no separate scheduler, history, presentation ledger or request
state. Voice retains committed-input/specification adaptation. Existing native
foreground delegate behavior and all speech deadlines are excluded.

Acceptance requires completed canonical result, wrong binding zero execution,
multiple/empty/error finals fail closed, exact cancellation and late cleanup
UNKNOWN/occupied slot, Host close retry/unpin, generation fences and no speech/
history effects. No schema, Task-card, tool permission or replay-policy change.

Implementation: HostWorkAgentExecutor calls the existing Harness directly;
AgentConversationRuntime.execute_native_work and its Work branches are removed.
The ordinary foreground delegate retains its previous deadline and interruption
behavior. HarnessRoundHandle.collect_final_text consumes existing events and
waits for actual runner cleanup; it is not another authoritative lifecycle.
Work still does not create a Task card. The SDK is unchanged from f91bc2d5e.

Evidence: 122 affected Work/Host/ordinary-conversation tests passed before the
additional fault cases. The final focused Work/Host set is **36 passed** and covers malformed finals,
delayed cleanup with capacity retained, cleanup failure, generation retirement,
Host-close retry, and actual SQLite result persistence/reopen/replay suppression.
The SQLite test executes through Host Harness and RuntimeFormalAgentFacade with
a controlled lower Agent; it is not a live model/provider or human audio check.
Unrelated SQLite data remains unchanged and replay after closing the producer
does not increment Agent calls. Empty recording-history fakes that were no
longer connected after removing Voice runtime were removed from tests rather
than presented as evidence. No presentation/history runtime is allocated.

Independent read-only review found a P1: wait_settled returning FAILED after
cleanup error must not be called CANCELLED. Fixed by validating terminal outcome;
the cleanup-error/normal-cancel pair passes. Review found no other definite
blocking issue. A prior test failure used the wrong expected controlled-Agent
answer; corrected to its actual scripted value, with restart assertions retained.

Production delta against Host24ac93b6 is Voice -86, Host +112, SDK 0; total +26.
This removes an unnecessary runtime stack, not 26 lines of functionality. Frozen
09-13 manifests remain historical; 09-14 manifests record the new exact source.
The retired P2 joint scenario and broader Host/Voice registry audit remain open.

[Clean paired wheel evidence](../evidence/DEEP_WORK_HOST_PACKAGES_20260914.json)
records the rebuilt Host with the unchanged SDK .4. A direct repository build
was rejected because old build/lib retained deleted task_core.py; staging the
current tracked source without build caches removed it. The clean wheel has no
extra production Python file and its new Host executor/Harness and SDK imports
resolve inside the temporary target. No environment package or deployment change.

## Current unified-input joint evidence (2026-09-14)

Bounded Registry cleanup scope (Tier 2, no authority/schema change): remove the
unwritten retired P2 submit ledger, uncalled turn reservation/preflight methods,
their pending indexes and the constant-false UNKNOWN dispatch branch. Current
handle_unified_submit uses durable journal admission, not those indexes. Keep
the public retired-route rejection and current commit/source/capability checks.
Owned surfaces are Registry and affected characterization assertions; verify
unified success/replay/conflict, interrupted admission, native dispatch and
close/recovery. No new shared lifecycle abstraction or wire policy is introduced.

`tests/integration/live_voice/test_unified_host_task_joint.py` exercises
handle_unified_submit → semantic model port → authenticated P3 composition →
PersistentTaskCore/SQLite → direct project executor, alongside a real Host
AgentRuntime/RuntimeFormalAgentFacade dialogue. This replaces the relevant
oracles, not the method name, from the retired P2 scenario. Unified input returns
round_accepted and renders the real receipt; it does not expose the old separate
intent response shape. Current explicit semantic cancellation supplies consent
to the existing durable origin-bound claim (registry line 12671 boundary), so
the test does not fabricate an obsolete second cancellation utterance.

Both completion/cancellation cases pass. Each verifies an actually RUNNING Task,
exact confirmation replay, content-conflicting replay (UNIFIED_INPUT_ID_CONFLICT),
and foreign-project unified submission (PROJECT_MISMATCH). Rejected operations
leave the complete SQLite logical dump, model/lower-Agent call counts and project
artifact effects unchanged. Voice close leaves accepted Task execution alive;
its completed RESULT-joint.md and pre-existing README bytes match. Explicit Task
cancellation yields CANCELLED without a result file, while the original dialogue
is released and finishes normally without cancellation. Every owner is closed
in nested teardown, including the Host and direct executor.

The test synchronizes through composition.reconcile_once, the existing Host
reconciliation lock. An early fixture called Core.reconcile concurrently with
the composition and raced claim/receipt bookkeeping; it was corrected to use
the actual owner. The old Agent-manager fixture lacked get_agent_nowait and the
foreground hooks required by today's Runtime; the controlled manager now
implements those ports. Neither issue prompted a production behavior change.

Independent review found weak foreground-cancellation evidence, missing Host/
executor teardown and a wrong-scope check limited to P3 query; all three were
corrected as described above. Models, authority resolver, Agent manager and
lower Agent remain controlled, so this is not complete production authorization,
language, Provider, browser or human acceptance. The old P2 test is retained as
an identified stale oracle; its adjustment/barge-in combination is not claimed
replaced. No production code changed in this evidence batch, so all three code
counts and the 195,321 combined baseline delta remain unchanged.

Command: `.venv/Scripts/python.exe -m pytest -q -o addopts= -o log_cli=false tests/integration/live_voice/test_unified_host_task_joint.py --tb=short`.
Scoped Ruff and diff whitespace checks also pass.

## Registry retired-admission deletion result

Next verification scope (Tier 2, tests only): use the current semantic model
boundary and real SQLite journal to fault after semantic freeze, recreate the
Registry/Host presentation runtime, change the available Task set, and prove
recovery cannot select a new target or re-invoke the model. D-107 allows analysis
again before freeze; no old keyword/current-task policy will be restored. A
frozen clarification must remain non-mutating. No production durability or
authorization policy change is authorized by these tests; any real discrepancy
will be triaged before changing its owned contract.

Implemented the bounded deletion above: 126 production lines removed from
product_composition_registry.py. No replacement owner/framework was added.
The current Host unified journal owns admission/fingerprint/effect recovery;
_unified_operations and settlement tasks still retain live execution and are
drained at stop. Public P2 submit still rejects. Other accepted/source-proof
compatibility structures were not broadened or mechanically merged in this batch.

Independent static review found no production dynamic call/write into removed
state. It identified one remaining historical test that reads the old private
ledger after attempting retired P2 submission; this was already stale and is
not claimed as current-route coverage. The new unified joint cases remain green.

The broader selected registry/speculation/joint command produced 28 passed,
27 failed, 189 deselected. The exact same command on isolated, unmodified
ffc29c73 produced the identical counts and failing IDs, with baseline module
import location verified. [Comparison and failing IDs](../evidence/DEEP_REGISTRY_BASELINE_COMPARISON_20260914.json)
retain the evidence. A number of old Task expectations still use the fixture's
default dialogue semantic response, rather than a specified task model result;
they do not verify the old parser's behavior in today's implementation. They
remain validation debt; failure-set parity does not make them passing evidence.
No new production behavior is inferred from those failures.

The directly changed uncertainty/retired-bypass/close/client-response rejection
characterizations pass: 5 passed, 231 deselected. Scoped Ruff and diff checks
pass. Tests required no production policy or timing change.

The baseline archive initially attempted an unavailable historical LFS video;
it was recreated with process-local GIT_LFS_SKIP_SMUDGE=1. No Git configuration,
credential, source checkout or remote ref was changed. Neither this read-only
archive nor the new production deletion changes the deferred speech timeout.

Current code accounting: Voice113111, Host48212, SDK33872; combined195195,
485 fewer than the initial195680. The new per-file/module manifests preserve
the same official baselines and line metric. Earlier wheel evidence remains
tied to its earlier source; this batch has no dependency/package-layout changes.

## Frozen semantic recovery audit (2026-09-14, incomplete)

The existing dedicated semantic Registry suite passes 97 tests. It uses the real
parser, journal, confirmation owner and Task SQLite with controlled model and
executor; `native_business_enabled=False` explicitly selects the supported
semantic delegate contract. This is not current Native business/Provider/audio
acceptance, and it does not close the 27 historical Registry failures above.

A new two-case fault test reaches `journal.bind_semantic`, commits the frozen
record, then raises a process-loss exception before any business effect. It
creates another Task, closes Registry/Host runtime and rebuilds them against the
same journal and authenticated composition. Both exact-cancel and clarification
replays currently fail with `SEMANTIC_RECORD_INVALID`. Diagnosis compared the
independently reconstructed commit with the frozen commit: the only difference
in this fixture is `hypothesis_provenance.critical_token_input.input_generation`
(original 3, rebuilt 1). `_critical_input_provenance_locked` currently assigns
that identity from an in-memory counter. The canonical digest correctly rejects
the changed commit. No fallback model interpretation or wrong-target effect was
observed; successful recovery is nevertheless **unproved and incomplete**.

Do not fix this by excluding generation from the digest, resetting test counters,
accepting model-record TurnCommits into the ledger, or copying an authorization
grant. D-107 requires an independently verified commit and current deterministic
authorization. A possible bounded repair belongs to the existing journal's
admission transaction: retain only the server-generated identity metadata before
semantic parsing, then reconstruct the same commit from freshly verified ingress
plus that metadata. This needs a deliberate Tier 3 child scope covering generation
ordering, context-ref identity, old rows, exact request/fingerprint and scope,
corruption, cancelled/stale input, and the separate Native path. No production
change, schema change or weakened validation has been made for this diagnosis.

Independent read-only review confirmed this direction implements D-107 rather
than introducing product/authorization policy. Record the next child boundary
as **Tier 3: durable server input identity**. The existing journal admission
transaction owns generation/context-ref metadata, bound to authenticated scope
and fingerprint; the existing critical gate owns stale-input rejection and the
formal owner owns final authorization. No model-derived grant or second journal
is allowed. Owned surfaces are the Host journal, Registry admission adapter and
their real SQLite/Registry tests. Dependencies: existing context-ref validation,
critical-input sequencing shared with ordinary P3, and Native owner admission.
Acceptance includes the two failing recovery cases, changed real context refs,
concurrent instances/expired takeover, newer-input then stale retry, corrupt or
conflicting identity with zero protected effects, old-row fail-closed behavior,
and unchanged Native admission/replay. Generation ordering must be designed
explicitly; merely raising a local counter to a recovered value is insufficient
evidence of cross-instance ordering. No SDK change or irreversible migration is
presumed. This scope remains pending implementation and verification.

Independent mapping of the old failures also retains these evidence gaps:
create feature-off/permission/ACK/privacy paths; actionable dirty-project byte
protection; post-presentation journal-completion failure and rebuilt runtime;
Cascade Gateway-issued speech receipt ingress; actual result-artifact content;
and malformed/failed formal-handler L0 emission through the full call chain.
Old pre-freeze current-task expectations are superseded by D-107's explicit
permission to parse again before freeze. Old demo bypass and implicit language
policy expectations must not be restored just to turn historical tests green.

## Durable server input identity result (2026-09-14)

The Tier 3 child above is implemented. The existing journal admission transaction
now freezes bounded generation/context-ref metadata independently of semantic
records, with scope/fingerprint/digest validation. One SQLite sequence serves
ordinary P3 and unified input. Unified input allocates only after fingerprint
validation in the same admission transaction; an earlier reservation attempt
changed SQLite on rejected input and was corrected after the real Host joint
oracle caught it. Reservations for ordinary P3 confer no permission. Native
continues to receive its commit from its existing owner, without this metadata.

Registry uses current verified ingress plus independently frozen server metadata
to construct the commit, then retains the existing gate, exact semantic digest
and final formal authorization. It never imports a TurnCommit/permission from
model output. Old pending rows lacking metadata fail closed; completed legacy
results remain readable without backfill. Schema additions are nullable metadata
and a bounded sequence; no old rows, Task data or private runtime data are rewritten.

Recovery tests now prove original-A cancellation after B creation, unchanged B,
frozen clarification with no mutation, no semantic reparse, and stale rejection
after a newer unified **or ordinary P3** input in the same interaction. Real CR
acknowledgement creates the original context; reconstruction changes its refs.
The permitted Task-result answer uses one Agent call with tools disabled, rather
than incorrectly expecting no result-expression Agent call under D-115.

Independent review found a separate no-Task dialogue projection mismatch. That
is repaired using the existing Task-answer approach: original semantic commit
remains exact, Agent execution refs match current formal context. A dedicated
test obtains a genuine CR snapshot from a delayed preceding-answer ACK and feeds
it through a controlled context-selection port after reconstruction. It proves
no semantic reparse, one normal dialogue Agent execution and zero Task effects;
it does **not** claim the Host automatically restores CR history after restart.
The reviewer read the final production diff and found no new blocking issue;
Main's mixed-P3/unified real-gate cases also pass.

Final scoped command (Host editable environment imports sibling SDK .4):

```powershell
.venv/Scripts/python.exe -m pytest -q -o addopts= -o log_cli=false tests/unit_tests/live_voice/test_unified_committed_input.py tests/unit_tests/live_voice/test_semantic_registry.py tests/unit_tests/live_voice/test_semantic_input_recovery.py tests/unit_tests/live_voice/test_native_business_registry.py tests/integration/live_voice/test_unified_host_task_joint.py --tb=short
```

Result: **144 passed** in 97.51s. Scoped Ruff and diff checks pass. This supersedes
the child fault failures and its implementation-pending statement above, not the
broader 27 historical Registry failures, integration audit or physical acceptance.
Current production counts: Voice113158, Host48322, SDK33872; total195352 (328 below
initial195680). The child adds157 net lines: Voice47 adaptation and Host110
necessary durability enhancement; no code migration or duplicate-removal credit.
The new [per-file](../evidence/DEEP_INPUT_RECOVERY_20260914.json) and
[module](../evidence/DEEP_INPUT_RECOVERY_MODULES_20260914.json) manifests use the
same baselines. Earlier package artifacts still attest only their earlier source.
No SDK source, timeout, buffer, Provider, credential, deployment or remote ref changed.

## Host configuration continuation scope (2026-09-14, Tier 0)

Trace: AgentWebSocketServer._live_voice_p3_model_catalog calls the existing
common.config.get_default_models(get_config()). That owner handles list/legacy
formats, decryption, environment fallback and AgentOS entries and returns at
least one entry on every successful branch. The subsequent Voice-specific
models.default/react/gpt-4 fallback is unreachable. Remove that duplicate
production branch, retaining the wrapper for current server/test callers and
fresh catalog reads. Formal ServerModelCatalogResolver keeps exact identity and
whole-catalog drift checks; ordinary _resolve_model cache/fallback semantics are
different and excluded. Verify actual common-config results for modern/legacy/
environment/AgentOS cases and invalid formal selection with no model build.
No provider/model selection policy, private config or authorization changes.

The separate project-authority audit found unused clean/managed-worktree checks
and factory reader allocation. Current code omits those checks since imported
commit cedb4e1b3; earlier D-099 wording restricts arbitrary dirty worktrees, while
the imported code and later repair evidence use captured current-tree execution.
That historical policy correspondence needs explicit evidence before rewriting
its decision narrative. No project-authority code is changed in this batch.

Configuration result: removed26 net lines from AgentServer; no file relocation,
new resolver or model policy. The shared catalog's existing format/environment
fallback remains. Empty-name entries are still rejected by formal resolution;
the unreachable gpt-4 branch never supplied a model for that case. Six new
real-Host-catalog cases pass; six selected existing model identity/default/drift/
builder cases pass (164 deselected, one dependency deprecation warning). Tests
inject config/environment values, call the real common catalog, and verify zero
model construction for unknown/drift/invalid selection. No private config or
Provider call is used. Scoped review and diff checks pass; the new test passes
Ruff. Whole-file AgentServer Ruff reports six pre-existing E402/F841 findings;
comparison with the HEAD blob has identical codes, lines, columns and messages.
No lint finding touches the changed method; unrelated cleanup is excluded.

Latest accounting: Voice113158, Host48296, SDK33872; total195326,354 below initial.
All26 lines are actual deletion of duplicate Host configuration fallback; no
additional production enhancement or relocation in this child. Only the net
change to the already-existing AgentServer file is counted, not its entire size.
See [file manifest](../evidence/DEEP_HOST_CONFIG_20260914.json) and
[module manifest](../evidence/DEEP_HOST_CONFIG_MODULES_20260914.json).

## Frontend lifecycle audit and implementation boundary (2026-09-14)

Source checked at Host `65eb3fb344df`; this section is an implementation
checkpoint, **not completed lifecycle integration**. Paths below are relative
to `jiuwenswarm/channels/web/frontend/src/`.

| Responsibility/current entry | Existing capability and overlap | Decision / authoritative state / acceptance |
|---|---|---|
| `LiveVoiceIntegratedRoutePanel.tsx` constructs the only `FormalP3TaskExperienceOwner` in a session/request effect, binds `formalTaskStore`, handles reconnect and polls live tasks | `ChatPanel/index.tsx` already supplies active session and WebSocket connection; `ensureSessionRuntimes` creates Host session runtimes but has no request/connection lifetime | Host ChatPanel must own this session reader lifecycle. Remove construction, disconnect/close and polling ownership from Voice; do not allocate network readers inside the synchronous runtime initializer. Same session reconnect preserves the owner and unresolved RPC; session replacement fences old callbacks. |
| `formalTaskStore.ts` publishes owner snapshots; Voice also keeps a React snapshot; `ToolPanel/index.tsx` reads the store | Existing Zustand session lookup and `RecentTasksPanel` already consume formal records | Keep one owner snapshot projection in the Host store; remove the redundant Voice snapshot when adapting consumers. Store is a view, never a second durable Task authority. Exact-owner publish/release and session/project filtering remain. |
| `formalP3TaskExperience.ts` manages list/status/events/result and retained mutation RPC | Plugin `applicationPlugins/taskProgressStore.ts` has controllers and display records, but lacks formal attempt/revision/event identity, UNKNOWN and confirmation/replay semantics | Keep the formal protocol adapter, reuse Host session/display entry. Do not translate it into plugin state: `applicationTasksToTeamTasks` maps failure to `cancelled` for display and cannot preserve formal result truth. No forced migration of unrelated plugin consumers. |
| Voice snapshot callback adopts selected Task into `createdProgressRoute` and tracks read revalidation | No equivalent generic notification callback: this binds Task selection to Voice progress authority | Retain Voice subscription/adaptation only. Host task reader must function with the Voice consumer absent; removing a Voice consumer must not close that reader or issue task cancellation. |
| `hasDurableProductVoiceSession` and `defaultProductRequest` in `liveVoiceProductOperations.ts` | The former checks only non-null/nonblank/not-`new`; the latter directly delegates to native `webClient.request` | Use the existing Host transport and public session identity. Do not invent a Voice activation requirement. Preserve current feature flags and request IDs. |
| Persisted target validation before owner construction | `inspectProductP3TaskTarget` is an existing fail-closed compatibility guard; malformed or unavailable target storage currently prevents even list RPC | Preserve this guard in the Host lifecycle wiring. Existing mounted malformed/unavailable-target tests require zero list/progress/confirmation/mutation calls; lifting it would change current behavior. |

The Voice panel is mounted by `ChatPanel/index.tsx` whenever
`FEATURE_LIVE_VOICE_INTEGRATED_WEB` is enabled, even before speech activation.
Therefore the current code does **not** imply that simply stopping Voice removes
Task cards. The actual remaining dependency is component ownership and mount
lifetime. `FormalP3TaskExperienceOwner.disconnect()` retains the original RPC
and exposes UNKNOWN; `close()` clears it. Those operations are not interchangeable
and neither issues backend task cancellation.

Implementation scope is Tier 2: frontend session/connection lifetime and stale
response fencing. Owned surfaces are the Host ChatPanel wiring, existing formal
Task store/reader, Voice subscription, and their frontend integration tests.
Preserve feature-off/no-session behavior, invalid persisted-target rejection,
same-session retry identity, reconnect read-only revalidation, current polling
intervals, session/project isolation, results and selected-task progress binding.
Exercise a Host-mounted reader without Voice, Voice detach with reader retained,
connection loss and late responses, session switch, malformed target and pending
mutation recovery. Existing standalone Voice mounted fixtures must explicitly
provide Host lifecycle composition; a production fallback that silently creates
another owner would recreate the problem. Backend protocol/storage, Task/Work
execution policy, provider/audio timing, and converting every Work to a Task
card are excluded. Source implementation and validation remain pending; current
production accounting is unchanged.

### Frontend implementation and evidence

Implemented Host `FormalTaskSessionProvider` at the existing ChatPanel session/
connection boundary. It uses native webClient, the existing reader protocol and
formalTaskStore; Voice no longer constructs/closes/disconnects/polls that reader
or maintains a second React snapshot. Voice retains a synchronous, exact-owner
store subscription for notification selection and the revalidation fence.
Independent review caught an initial passive-effect fence window; replacing it
with subscribe-before-current-snapshot adoption closed that source-level risk.
The reviewer found no further concrete issue in the corrected subscription.

New Host-mounted tests: **9 passed**, including no Voice consumer, consumer
detach with real 5-second list/status/events/result polling, stale previous
session response, same-owner UNKNOWN preservation with explicit byte-equivalent
RPC replay, flag-off/new/null session and malformed/unavailable target storage.
These use the real frontend owner/store and controlled RPC envelopes, not a
real backend/Provider. Initial polling fixture failures exposed missing event
scope/source identity; the corrected fixture is accepted by the strict parser.
An earlier command failed to apply the mounted fixture wrapper because its
working directory was wrong; those raw-component failures are superseded by
explicit Host composition and the final command below.

Existing Task owner suite plus the first eight Host cases: **47 passed**. Final
affected mounted group, after the synchronous fence correction: **47 passed,
1 skipped** (the pre-existing provider-starting/running-AUDIO case remains
skipped; no acceptance credit). Its command is:

```powershell
node --test --test-name-pattern='mounted.*(P3|Task|task)' tests/liveVoiceIntegratedRoutePanelMounted.test.mjs
```

New tests are discoverable through the existing integrated-web package script.
Frontend `tsc --noEmit -p tsconfig.json` and Vite production build pass; Vite
retains its large-chunk warning. No browser/device/Provider acceptance is claimed.

Same-basis counts: Voice113084, Host48440, SDK33872, total195396 (284 below the
initial195680). This child is net+70: Voice−74, Host+144. Most lifecycle logic is
retained under Host composition, not claimed as deleted duplicate algorithms;
the duplicate Voice snapshot and ownership entry are removed. See the current
[file manifest](../evidence/DEEP_FRONTEND_HOST_20260914.json) and
[module manifest](../evidence/DEEP_FRONTEND_HOST_MODULES_20260914.json).
Broader backend historical tests, project-authority evidence and final paired
packaging remain open. No SDK, timeout, credentials, deployment or remote update.

## Project authority correspondence (2026-09-14)

Historical correspondence is now verified, superseding the earlier uncertainty:
D-120 explicitly supersedes D-098/D-099's blanket exclusion of user edits. The
[accepted R5 packet](REALTIME_R5_PROJECT_SNAPSHOTS_20260907.md) records acceptance
of tracked/untracked and staged/unstaged contents, with exclusive execution,
isolated seeding and Task-only writeback. Commit `ae4b32331501` implements that
decision by removing `_require_admissible_worktree` calls and requiring the
Executor to own snapshot/conflict protection. `a4029b7c14bd` subsequently fixes
byte/index fidelity, not a new authorization policy. Current code agrees with
D-120; reinstating a clean-tree admission check would regress accepted behavior.

Tier-0 cleanup scope: delete Host's uncalled private clean/managed methods and
unused factory allocation, retaining accepted constructor arguments as no-op
source compatibility. Keep real project/session/allow-list/root/HEAD checks and
the actual Executor snapshot/writeback guarantees. Verify factory D2 Store
binding without a managed-reader allocation, existing resolver rejection and
compatibility cases, and current real-Git authorized-snapshot tests. The SDK
exported `DirectProjectManagedBaselineReader` remains a read-only legacy proof
API for existing package callers; Host no longer uses it as admission authority.
Keeping its callable proof behavior avoids breaking the previous package pair;
this is retained compatibility implementation, not native unification credit.
No change to authorization, current project data or persisted schemas.

Result: Host removes70 net production lines, no relocation. The five selected
resolver/factory cases pass (165 deselected), including allow-list rejection,
dirty-input compatibility, current grant/redaction and real D2 Store binding
with the SDK legacy reader constructor forbidden. Seven authorized-snapshot
cases pass in32.46s using real Git, files, SQLite and SDK FsOperation with a
controlled Agent carrier: mixed staged/unstaged inputs and exact index retention,
save-as after restart, visible-input/output collisions with no partial write,
ignored-cache behavior and applied-effect recovery without repeated file tools.
Scoped Ruff, cold diff review and diff checks pass. No protection mechanism was
replaced by a mock or removed; tests exercise the still-authoritative executor.

Latest counts Voice113084, Host48370, SDK33872, total195326 (354 below initial).
See [files](../evidence/DEEP_PROJECT_AUTHORITY_20260914.json) and
[modules](../evidence/DEEP_PROJECT_AUTHORITY_MODULES_20260914.json). This closes
the historical policy-correspondence uncertainty, not all Host/Voice integration
or outstanding backend tests. Final package evidence still predates these edits.

## Current joint cancellation-domain continuation

Extend the current unified Host-runtime joint test with foreground barge-in while
a real SQLite/Direct Task is running. Preserve the old S6 oracle that cancelling
the dialogue cannot cancel the Task; assert the exact dialogue is cancelled and
the Task can complete and return its saved result. This is test-only Tier 1
evidence migration using controlled lower Agents, real Host execution and real
files. The old hand-built voice-origin/retired-p2.submit journey is not silently
credited or deleted; real Gateway receipt coverage and adjustment integration
remain separate gaps until implemented. No production or policy change.

Current reproduction is **not passing**. Old-response barge correctly rejects
`STALE_RESPONSE_OUTPUT`; Host foreground requests in the same public session
serialize, so the second dialogue starts after the first settles. D-104 explicitly
keeps barge-in separate from Harness cancellation (also characterized by
`test_interrupt_after_barge_in_still_stops_the_running_round`). The new test now
calls the real `handle_p2_interrupt_generation` after barge-in. It observes exact
lower-Agent cancellation, rejects injected `cancel_scope=task.cancel` without
durable writes, and observes the detached Task still running. However closing
the second activation returns `PRODUCT_P2_CLEANUP_PENDING`, and root cleanup
retains a failed segment. This final cleanup failure still needs diagnosis; do
not weaken the assertion or credit the whole joint journey. Latest local log:
`logs/deep-joint-barge-20260914.log`. No production change or new commit yet.

### Joint interruption evidence closed

The cleanup failure was traced to `history_write_intents_pending`, not an
unsettled Agent. The existing fixture isolated Task SQLite/project files but
used the default Host history directory with fixed commit IDs. Read-only
inspection confirmed that `live-voice:commit-second-dialogue:user` in default
synthetic `session-1/history.jsonl` contained the first fixture wording and
conflicted with its corrected wording. The real idempotent history writer
correctly refused replacement. No existing history was erased or overwritten.
The fixture now injects only its session-history root under pytest `tmp_path`,
retaining the real writer, and checks real user rows with unique IDs and zero
unplayed assistant records. Earlier runs left synthetic history in the default
test-named session; this batch does not delete private runtime files.

Final scoped command:

```powershell
.venv/Scripts/python.exe -m pytest -q -o addopts= -o log_cli=false tests/integration/live_voice/test_unified_host_task_joint.py --tb=short --show-capture=no
```

**3 passed in19.35s**, scoped Ruff and diff checks pass. The new barge mode
preserves stale-response rejection, tests barge output fencing independently
of actual generation cancellation, rejects an injected Task cancel scope with
unchanged SQLite, observes exact lower-Agent cancellation through the real Host
coordinator, replays the same interruption, closes both activations and then
completes the detached Task. Completion modes read the actual saved Task result
and compare task/attempt identity, result text and produced file content. No
Provider, microphone, playback ACK or artifact-download acceptance is inferred.
No production changes: the last accounting manifests remain current. Old S6
voice-origin/notification and broader adjustment evidence are still open; this
does not make the retired `p2.submit` test green.

### Current paired Python packaging (2026-09-14)

Tier 0 verification-only child: verify the current Host/SDK distribution seam,
without production changes, dependency upgrades or deployment. Clean temporary
stages copy tracked packaging inputs from Host `e722644f44b3` and SDK
`f91bc2d5ea96`; ignored build caches are not copied. Both `python -m build
--wheel --no-isolation` builds succeed, followed by `uv pip install --no-deps
--target` of the two wheels. This deliberately reuses existing third-party
dependencies, and excludes frontend dist and fresh dependency resolution.

An isolated `python -I` process outside the repositories adds only the installed
target for the pair. It imports Host Work service, formal runtime facade, native
RoundHarness, authenticated Task composition, SDK application Tasks/checkpoint
rail and native single-agent modules. Every loaded Host/SDK module is asserted
under that target, preventing editable-source fallback. All 1,016 installed
Host and 2,409 SDK Python files match staged input bytes; retired `task_core.py`
and `legacy_project_task_service.py` are absent. Package metadata constraints
accept SDK `0.1.17+livevoice.4`. Result: **CURRENT_PAIRED_IMPORT_OK**.

[Exact-source evidence](../evidence/DEEP_CURRENT_PAIR_20260914.json) records
commits, wheel SHA-256 values, module paths and counts. Import emitted an existing
invalid-escape SyntaxWarning in SDK browser probes; it did not fail. No source
or runtime policy changed, and previous production accounting remains current.
This closes the current Python packaging seam only, not the remaining semantic
or physical acceptance gaps.

### Current unified running-adjustment joint (2026-09-14)

Tier 1 test-only boundary: extend the current joint ingress scenario to accepted
running adjustment, using existing SQLite/Core/DirectExecutor and native SDK
model callbacks. No new production policy, schema, authority or timeout. The
previous lower Agent only waited then wrote a fixed file, so it could not prove
adoption. The new controlled lower Agent binds the real current checkpoint via
TaskCheckpointRail/scoped_agent_rail and calls ReActAgent's model path with a
real SessionModelContext. Its controlled model asserts the accepted appendix
requirement is present before returning the adjusted answer.

The real unified ingress creates/confirms one Task, accepts the adjustment and
replays its request. Voice closes while execution remains blocked. Releasing
execution adopts the adjustment, writes the corresponding synthetic file and
returns the matching persisted result. Reopening SQLite proves exactly one
adjust-requested event, one adjust-applied event, one Task and the same attempt;
the model runs once. Original README bytes and the existing wrong-scope/stale
zero-side-effect assertions remain. This fixture explicitly controls the lower
Agent and its rail installation: it does not independently validate the Host
adapter's binding implementation, file-tool admission or external Provider/
artifact quality. Files are written directly by the controlled lower Agent.

Initial run reached the adjusted result but failed the leftover fixed
`completed` assertion. The expected adjusted result was corrected, then the
complete joint file passed **4 tests in 20.46s** with scoped Ruff and diff checks.
Read-only independent review identified that the first fixture discarded the
model return and hardcoded file/final text. Both now use the actual SDK model
return content; the affected adjustment mode passed again (**1 passed in
10.90s**, three unrelated modes deselected), with scoped Ruff/diff checks.
Production bytes and the current paired-packaging evidence are unchanged.
Old retired-entry voice-origin/notification coverage and historical Registry
failures remain open.

### Gateway receipt to current unified Task origin (2026-09-14)

Tier 1 test-only boundary extends the joint fixture with real
FormalBatchSpeechService.issue_streaming_voice_commit_receipt and Gateway
_inject_live_voice_gateway_voice_claim, then the existing unified handler with
critical-input enabled. Model responses, lower Agents and project authority
remain controlled; there is no demo bypass. Issuance is called at the verified
STT seam, so this does not test upstream media/Provider recognition or the
full Gateway transport/authentication envelope.

The Voice mode creates and confirms a real SQLite Task and checks all origin
identity fields against the activation. Exact receipt replay reuses the result.
Reusing that receipt with different text is rejected before journal admission
(`FORMAL_SPEECH_RECEIPT_REQUIRED`, earlier than text-route ID conflict). A
browser-supplied claim without receipt is stripped by the real Gateway function
and rejected downstream. Existing database-dump, model/Agent-count and project
file assertions prove zero forbidden effects. Wrong project still rejects.
Voice close leaves the Task running; releasing the controlled Agent completes
its file and saved-result query as in the original complete mode.

First combined run had four prior modes pass and the new mode fail only because
it expected the later text-journal conflict reason. The earlier receipt denial
was retained and asserted. Final exact Voice mode, including forged-claim and
origin assertions, passed **1 test in 11.64s**; scoped Ruff passes. No production
change or new physical acceptance. This closes the current receipt-to-origin
seam, not notification delivery or the old combined retired-entry test.

### Completed Voice Task to Host text notification (2026-09-14)

Tier 1 test-only continuation of the preceding Voice joint: preserve the real
SQLite unread state after Voice closes, complete the Task, reopen the same
session with a new activation, and subscribe through handle_p3_progress_activate
to the existing Host text sink. The pushed source sequence is asserted equal
to the completed Task's event head. ACK uses the exact presentation binding;
an unknown Task target rejects with unchanged SQLite, the correct ACK advances
the text watermark, and exact replay returns replayed=true with no further
SQLite writes. Voice watermark stays -1: text display does not claim played
speech. No second Task execution occurs.

The initial ACK failure was the fixture's frozen composition clock: Task Store
requires observation strictly after its event. Only the test ACK clock advances
one second. A subsequent replay assertion incorrectly expected the first
response's replayed=false; the existing explicit replay marker is now asserted.
No production logic was changed. Four prior joint modes passed in the combined
run; the final affected Voice mode passed **1 test in 11.84s** after these oracle
corrections. Scoped Ruff/diff checks pass at batch closure.

Read-only review confirms these boundaries and limits: receipt issuance starts
after STT/media verification, the web push sink is controlled, reconnection is
same-process, and the wrong Task ID is nonexistent (not another real Task).
This does not prove browser DOM rendering, process-restart notification recovery,
cross-real-Task ACK isolation or spoken notification/playback. Existing dedicated
tests remain their separate evidence; the old combined spoken journey is open.

### Historical Registry failure triage: current semantic boundary (2026-09-14)

Tier 1 test-only child: move exception injection from the no-longer-called
read_current_background_task hook to resolve_production_semantics. The existing
unknown-failure test now reaches the current production error boundary and
proves generic UNIFIED_INPUT_FAILED with no private path exposure or Agent call.
A separate current semantic-authority-denial test proves rejection, zero business
handle/Agent calls and zero assistant history. Selected checks: **2 passed,
234 deselected in 9.65s** before restoring the old permission test below;
scoped Ruff/diff checks pass. Production is unchanged.

The old permission-denial/spoken-ACK test is retained unchanged: the new
semantic-authority rejection does not substitute for that product presentation
scenario. Likewise the P3-off test remains unchanged and unresolved. Tracing an
exploratory explicit task decision found a tool-disabled receipt Agent (not
ordinary dialogue), carrying P3_CONFIRMATION_ISSUER_UNAVAILABLE. This fixture
lacks a real confirmation issuer even with flags on, so that rejection cannot
prove the flag boundary. The exploration was removed instead of weakening the
test. Use the real composition/confirmation harness to establish that boundary.
The default-dialogue fixture and retired current-task hook do not prove a new
production regression. Final selected semantic-denial/privacy checks: **2
passed, 235 deselected in 9.43s**. No full historical group rerun or revised
aggregate passing count is claimed.

### Real P3-off composition/confirmation boundary (2026-09-14)

The Tier 1 test migration now uses semantic_runtime's real SQLite/Core,
P3AuthenticatedComposition, BoundedP3ConfirmationOwner and forwarder, alongside
the same controlled model/lower-Agent ports as existing semantic tests. Both
P3 text and mutation flags turn off after activation: one case precedes its
first Task request; another follows a real presented pending confirmation.
Existing issuer/forwarder objects remain available, so missing construction
cannot masquerade as current-flag enforcement. The normal enabled typed-create
case is run beside them as the positive control.

Each disabled case drains the real outbox and observes unchanged Task-store
counts, zero Tasks, no executor dispatch/cancel/adjustment, no tool-enabled
receipt Agent, and no returned Task ID. Exact replay neither changes counts nor
invokes the semantic model/Agent again. This checks current gating in a live
composition, not cold-start allocation or independent single-flag policies.
The earlier failed P3-off lifecycle test was removed only after this replacement
passed. The separate old permission-denial/spoken-ACK case remains.

Final selected command covers the two disabled cases, enabled typed creation,
semantic authority denial and generic exception privacy: **5 passed, 336
deselected in 11.03s**. Scoped Ruff and diff review/checks pass. No production
changes, new feature policy, Provider/audio acceptance or aggregate historical
failure-set closure is claimed.

Independent read-only review rejected the initial broad "failure or no Task ID"
oracle because unrelated upstream failure could pass it. The final test requires
one actual model call, one tool-disabled receipt Agent, an exact task.create
failure receipt with P3_CONFIRMATION_ISSUER_UNAVAILABLE, and preservation of the
pending operation/id/version. Real confirmation owner/forwarder already exist;
the current mutation gate makes their issuer unavailable. Both revised disabled
cases pass again (**2 passed, 103 deselected in 8.73s**). Scoped Ruff/diff checks
pass. This closes the review finding without changing production semantics.

### Failure receipt and actual Host history (2026-09-14)

Tier 1 test-only continuation: the real P3-off cases now use the existing
SessionFormalHistoryWriter and an isolated temporary Host session-history root.
The controlled tool-disabled receipt Agent returns an explicit no-task-started
message. Before the actual presentation-unit ACK, that assistant message is
absent from Host history; after ACK exactly one matching row exists. Task-store
counts remain unchanged and no executor dispatch occurs. The pending-before-off
case also acknowledges its earlier proposal before disabling the gates.

An initial assertion against semantic continuity history failed. That table is
not the Host transcript and was not substituted for the requested history
boundary. The final check reads real Session History files, preserving its real
idempotent writer. **2 passed, 103 deselected in 8.79s**. This uses controlled
Agent output and protocol presentation ACK, not real playback, microphone or
Provider evidence. The separate business-permission-denial scenario remains
open; no new policy or production change is made.

### Business permission revocation, feedback and continuation (2026-09-14)

The same Tier 1 real-composition test now includes a third case: after presenting
a real pending create confirmation, remove only task.create from the existing
authenticator principal's allowed operations. Keep flags, owner/forwarder,
project scope and agent.chat permission intact. The strict model receives the
same pending id/version and returns its confirmation; real authentication/
authorization yields FORMAL_TASK_AUTHORIZATION_DENIED in the exact task.create
receipt. No outer route or handler error is stubbed.

Assertions retain zero Task/dispatch/cancel/adjustment, exact no-effect replay,
one tool-disabled receipt Agent, real temporary Session History absent before
ACK and present exactly once after ACK. A following ordinary dialogue is
accepted and reaches the Agent without creating a Task. Its tools-enabled flag
is only dispatch configuration evidence, not a real tool execution claim.
The former read_current_background_task-based denial/spoken-ACK test is removed
after this reachable replacement passes. The controlled reply text and protocol
ACK do not establish Provider wording, physical sound or user acceptance.

Final selected group: three rejection modes plus enabled typed create,
semantic denial and exception privacy, **6 passed, 335 deselected in 11.62s**.
Production and production accounting are unchanged. The earlier historical
failure manifest remains immutable; no aggregate all-green claim is made.

Independent read-only review found no remaining blocker and confirmed the
controlled-expression/physical-playback boundary. The receipt reason is also
checked as an exact JSON field; the three affected cases pass again (**3 passed,
103 deselected in 9.39s**). Scoped Ruff/diff checks pass. "Absent before ACK"
refers to that denial assistant record, not other user/proposal history.

### Created Task before unified-result completion loss (2026-09-14)

Tier 1 test-only recovery child: real semantic Registry/confirmation/SQLite Core
creates one Task, then an injected BaseException at unified journal.complete
interrupts result sealing after the durable Task effect. Unlike an ordinary
Exception, the injected loss does not execute the generic result-error sealing
fallback. The test restores the method and expires only the pending test lease.
One mode retries in the original Registry; the other stops its Registry/runtime
and constructs new ones against the same SQLite journal and existing Core/
composition/confirmation services. This is component reconstruction, not full
OS-process crash, reboot or deployment evidence.

Both modes return a Task ID that resolves to the original expected Store spec,
with unchanged Task counts and no new semantic or receipt-Agent call. The new
Registry's Agent sees no call. Draining the real outbox after recovery invokes
the controlled executor exactly once for that Task's original attempt, and no
second Task is created. No second execution owner or recovery journal was added.
The test does not claim the old response can be played after reconstruction;
it proves durable Task receipt/effect recovery only. Old presentation/history
crash-window cases retain their separate remaining boundary.

Final affected recovery file: **3 passed in 9.52s**, including the existing
changed-context frozen-dialogue case. Scoped Ruff/diff checks pass. Production
bytes, package pairing and production accounting remain unchanged.

Read-only review found no blocker and confirmed the pre-dispatch boundary.
Final strengthening captures the original receipt's Task ID and compares it
directly after recovery, and checks the exact journal row changes from pending
to completed. Both cases pass again (**2 passed, 1 deselected in 8.95s**), with
scoped Ruff/diff checks. This is not running-executor or post-external-effect
recovery evidence.

### Recovery effects are identified by stored execution path (2026-09-14)

The same test now covers create receipt, existing-Task status answer and direct
clarification, each with same-Registry retry and Registry/runtime reconstruction.
All use isolated temporary Host history paths. Initial status exploration reused
the create request ID and was rejected before the intended failure window; the
test now uses distinct request IDs. Checking the actual journal effect exposed
a second incorrect assumption: Cascade Task status uses agent_submit, whereas
clarification uses authoritative_presentation. The test explicitly asserts these
stored effect kinds rather than inferring them from operation names.

After journal-completion loss, each path retains the same response identity,
retained Task identity where applicable, unchanged Task counts and no extra
semantic or Agent execution. The existing Task's outbox dispatch remains once.
Clarification deliberately has no Task receipt identity; it does not relabel the
unrelated existing Task as its business result. The exact request row transitions
pending to completed in both recovery modes. The whole affected recovery file
passes **7 tests in 12.62s**. This covers recovery through both stored foreground
effect paths; it does not yet add playback/history-ACK recovery evidence or
post-external-side-effect Executor restart proof. Production is unchanged.

### Direct-presentation recovery ACK and real history (2026-09-14)

The clarification modes now install the actual SessionFormalHistoryWriter with
temporary file storage before either initial or reconstructed presentation.
The recovered response's assistant text is absent before ACK. Polling the actual
notification API finds that exact response/unit; a wrong-generation ACK rejects
without history writes, exact ACK writes one matching assistant record, and ACK
replay does not add another row. Task counts remain unchanged before the original
attempt's single outbox dispatch. This is protocol ACK/file evidence, not audio
hardware or DOM render evidence.

The first same-Registry test stopped after eight notifications, all belonging to
its two preceding rounds; reconstruction had no such queue and passed. The test
now permits sixteen notification reads to traverse those known prior rounds.
No production poll duration, preparation deadline or speech latency changed.
The complete recovery file passes **7 tests in 14.77s**. New Registry still reuses
the live composition/Core/confirmation services: full-process recovery and
external side-effect restart remain outside this particular evidence.

Independent comparison against the old presentation-rebuild oracle identifies
one still-unreplaced scenario: its assistant history is ACKed before rebuilding,
then the same unit ID is replayed and acknowledged without duplicating either
user or assistant history. The new modes currently rebuild before the first
ACK and compare response identity, not the pre-loss unit ID. Keep both old
presentation crash tests until an already-ACKed reconstruction case checks the
real original unit and per-commit history deduplication. The seven passing
current cases do not close that missing recovery stage.

### Already-ACKed reconstruction evidence and remaining scope (2026-09-14)

The recovery matrix now also ACKs the clarification before Registry reconstruction,
then replays the exact original ACK including presented_at. It checks the original
unit ID, one user record for that commit, one assistant record, byte-equivalent
loaded history after recovery/ACK replay, no pending history write, unchanged Task
counts, and one outbox dispatch. Eight tests pass in 14.94s. The model and Executor
remain controlled; storage is real temporary SQLite and Host history files.

An initial test incorrectly issued a new ACK timestamp under the old output's
history identity. The actual Host writer rejected the changed record as an
idempotency conflict and retained cleanup as pending. Exact ACK replay passes;
this does not prove that a newly timestamped ACK after reconstruction is supported.
No production behavior or timeout was changed, and the old tests remain pending
final replacement review.

The previous approximate 80% overall estimate was withdrawn after user feedback.
The net production reduction of 354 lines is limited and does not establish broad
management convergence. Further work must prioritize production overlap in Task,
Work, Host and Voice; historical-test migration is supporting evidence, not an
independent measure of integration progress.

### One synthesis authorization implementation (2026-09-14)

Code-level comparison found identical synthesis binding builders in BatchSpeech
and Gateway dedicated-media registration. Gateway already imports the canonical
SpeechAuthorizationBinding and SynthesisBatchRequest from BatchSpeech. Expose
that owner's existing builder as synthesis_authorization_binding and call it
from all five Gateway mint/check sites as well as batch authorization. Delete
Gateway's complete duplicate builder; do not add a wrapper or move the surviving
implementation. Digest fields, canonical serialization, scope, response/unit,
transforms and operation bindings are unchanged. This is bounded Voice duplicate
elimination, not Task/Work management convergence or a new authorization policy.

Affected existing batch/product-streaming/media-authority tests: 45 passed,
227 deselected, 7.01s; Ruff passed. Includes allowed synthesis, mismatched content,
wrong activation/authority, replay/renewal and forbidden Provider effects. No
physical Provider/audio acceptance is claimed. Production net change for this
edit is -43 physical lines (one existing builder retained, duplicate removed and
one import added); final accounting manifest still requires regeneration.

### Single product admission lifecycle (2026-09-14)

Production references show Registry/activation leases use submit_committed_turn.
The old dispatch_committed_turn and _register_legacy_dispatch had only test callers;
remove both and the branches supporting legacy-dispatch adoption. The old product
submission and execution admission dictionaries were written simultaneously and
held the same Future/coordinator. Retain only _admissions with the existing Harness
and Bridge reservations; remove the duplicate model, capacity check and shutdown
wait. Exact request replay still precedes closed-admission checks and shields the
same outcome. The identity lock, turn/commit ownership fences and rollback remain.

This coherent runtime/admission boundary has unchanged intended product behavior;
no authorization, protocol, persistence, provider or latency policy changes. Tests
now use the production submit entry, which itself commits the turn: remove manual
precommit setup rather than permit cross-owner adoption. Retain wrong scope/type,
capacity, request replay/conflict, cancellation, history and close assertions. The
old precommitted-dispatch-only UNCOMMITTED_TURN oracle is retired with that entry;
current invalid canonical commit and feature-off checks reject before effects.
Legacy start/commit identity-conflict tests remain for their still-present APIs.

Runtime suite: 93 passed plus one old private-field reference failure; after fixing
that reference, its exact test plus eight recovery cases and five real Host joint
cases passed (14 tests, 62.38s). Earlier two fixture failures were obsolete ledger
error naming and precommit setup, not production capability rollback. Independent
read-only review traced current callers, identity/capacity rollback, shielded replay
and shutdown; no blocker found, with deleted-block review performed by Main.

Production net -216 lines here, and -43 for synthesis binding reuse: -259 this
batch. Same-basis manifest now totals 195067, 613 below initial 195680. These are
actual deleted implementation/state holders, not relocation. Persistent Task/Work
management convergence remains PARTIAL; recovery tests do not expand physical
provider, complete OS-process restart or audio-device acceptance evidence.

### Remove unconsumed effect-delivery protocol (2026-09-14)

The production tree has no consumer of AgentConversationRuntime's
claim_conversation_effects/acknowledge_conversation_effects. Registry/leases/Gateway
consume notification APIs and PresentationAck instead. The abandoned protocol
retained a second effect backlog, claim ledger, replay/ACK model and close-time
copy of CR effects. Its ACK only marked the batch; it neither cancelled execution
nor wrote presented history. Delete that layer rather than relocate it. Keep
CR.close, underlying CR effects, barge/interrupt/exact-round cancellation,
notification leases/final-drain and actual presentation-history ACK unchanged.

The four tests exclusively exercising the deleted claim/ACK protocol are retired.
Four-cancellation-domain and multi-final tests now inspect the actual CR effect
source directly. The disconnected final-drain test exercises real notification
lease rejection, retained terminal delivery and exclusion of invalid presentation.
The first edit accidentally removed other snapshot fields, immediately restored
following test failures. A second run passed 89 cases; one rewritten notification
call omitted its required limit and was corrected before targeted revalidation.
No green suite claim is made from that intermediate run.

Production net -387 physical lines; no new framework, compatibility implementation
or execution state. This is removal of an unused Voice delivery protocol, not
unification of persistent Task/Work management. Final accounting and current
boundary validation must be refreshed after the coherent batch closes.


Final targeted validation after supplying the real notification API limit:
14 passed in 30.30s (the corrected final-drain case, eight recovery cases and
five real Host joint cases). The other 89 runtime cases passed before that test-only
correction. Ruff and diff checks passed. Independent read-only review confirmed
all unrelated snapshot fields, CR.close, notification/final-drain, presentation ACK
and cancel/interrupt paths remain. No production consumer of the removed protocol
was found; no external Python-consumer compatibility claim is made.

Refreshed same-basis evidence: Voice 112438, Host 48370, SDK 33872; aggregate 194680,
1000 below the initial 195680. The -387 here is real production deletion; removed
protocol-only test lines are excluded. Native Task/Work management audit remains
open; no overall completion percentage is inferred from these deletions.


### Store-owned atomic Task authority projection (.5, 2026-09-14)

The Host StoreProductionTaskAuthorityReader previously queried a Task/Attempt page,
event heads and results separately, read the page again, then retried up to three
times on observed drift. Replace that application-level convergence mechanism with
an enhancement to the existing SqliteTaskStore: list_task_authority_snapshots_page
returns Task/Attempt/admission/head/result from its existing _snapshot_reader
transaction. The old ordinary and Task/Attempt page methods also reuse the same
keyset query and bounds/scope validation; their API and transaction behavior stay
unchanged. No new store, scheduler, authoritative cache or persistent schema.

This is an authority-read consistency boundary (Tier 3), not a new authorization
policy. Host retains exact scope/principal checks, bounded complete-set admission,
capability/dispatch and lineage projections, event seq/state/outcome checks and
completed-result requirements. Subsequent mutation preconditions remain required:
a read snapshot is not permission to execute an old command. Single-page atomicity
does not imply multiple pages share a transaction; Host rejects a truncated set.

Delete Host's second page read, convergence retry loop, separate result/head reads
and redundant reconstruction of the same SDK state enums. Keep the application
policy projection because Store state does not itself define product operations.
SDK production net +3 lines (existing paging duplication removed while adding the
aggregate read); Host production net -69. This is real reuse of a Store transaction,
not moving the Host algorithm into a new module.

Validation: 15 Host projection tests, including real SQLite writes completing a
Task or inserting a Task after the initial SELECT. First read returns coherent
old facts; next read sees new facts, with no extra reader writes. Seven standalone
SDK tests cover existing-page equivalence, exact scope/cursor, invalid bounds and
missing event-head rejection without repair. Four existing Task/Attempt snapshot
mutation tests pass. Host projection plus real joint Task flow: 20 passed in
25.76s. The former fake alternating-page stale test is superseded by real atomic
collection evidence; corruption/profile/result/lineage oracles remain. Independent
read-only review found no blocker and explicitly noted single-page and SDK-version
limits. No external Provider/audio evidence added.

Host and SDK dependency/version pins advance to 0.1.17+livevoice.5: the Host now
requires the aggregate method. Fresh paired-wheel install verification and final
accounting are pending closure of this batch. AgentCore has no Host dependency.


Paired `.5` packaging closure: fresh tracked worktree staging built both wheels,
installed with no dependencies into a new temporary target, then imported in
Python isolated mode. All loaded Host/SDK modules originated in that target;
1016 Host and 2409 SDK Python files matched staged source hashes. The installed
Host authority reader successfully called the installed SDK aggregate method
against real empty SQLite. Dependency pins and installed .5 metadata matched.
See DEEP_ATOMIC_TASK_PAIR_20260914.json. Third-party dependencies come from the
existing venv; no full dependency resolution, live deployment, frontend build or
Provider test is claimed. Final net aggregate is 194614 (-1066 from initial).

SDK implementation commit: `0b8cb556d` (`feat: expose atomic task authority
snapshots from existing store`). The paired Host commit consumes that `.5` API;
both belong to this atomic-read change. Neither repository was pushed and no
history was rewritten.


### Work producer ownership convergence (2026-09-14, scoped implementation verified)

Audit: WorkStore checkpoint CAS is the only durable Work state; Host journal
presentation/suppression facts do not establish execution success. Task origins
record a Native input-to-Task association before input-receipt completion; current
Task records do not contain that association. Retain it for the accepted Task /
incomplete input receipt crash window, intersecting with fresh authorized Tasks.
Deleting it is not justified by its recoverable projection alone.

The remaining allocation split is real: NativeBusinessRouter manages the Host
producer dictionary and lock, while HostWorkService retires/closes them. Give the
existing Host service exclusive allocation and cleanup ownership, using its own
AgentRuntime session coordinator and AgentManager. Remove Router pool/lock aliases
and allocation implementation. Keep only scoped Voice input adaptation; retain the
existing Agent channel identity/cache, generation fence, pins, capacity and pending
cleanup behavior. This is mostly retained allocation code, not duplicate deletion.

Tier 2 execution-lifetime boundary: source is runtime/service.py, runtime/work/service.py
and native_business_router.py; tests are runtime/test_host_work_service.py plus
relevant Work execution regressions. Acceptance: direct Host allocation without a
Voice Registry, exact generation reuse, stale/closed/changed-generation rejection
with zero Agent execution/pin effects, retained pending cleanup, Host close races,
Voice close preserving admitted work. No schema, auth-policy, state-machine,
Provider, latency, retry policy or SDK API change. No deployment or data migration.


Validation closure: 60 tests passed in 10.55s for HostWorkService, WorkRuntime /
real Harness adapters and native read-only Tool policy. Three actual Native
Registry Work tests passed in 8.28s: accepted work survives Voice disconnect,
project rebinding during Agent lookup has zero Work/Agent effects, update/cancel
preserves Task store and retires the old result. The new direct Host test uses
real Host session/Harness/Work/SQLite and a controlled Agent; it is not a real
external model query. Ruff and scoped diff review passed. Independent read-only
review found no introduced blocker; get_executor is a trusted internal API,
not a new authorization boundary or new project_dir/scope validator.

Initial execution had a missing moved-helper import, fixed before the successful
run. Subsequent default-coverage runs displayed passing cases but were interrupted
while coverage parsed the whole repository; a faulthandler stack identified that
reporting work. The successful commands explicitly use --no-cov, with exit 0.
No timeouts, buffering, product latency or test assertion limits were changed.

Same-basis production delta: Voice -72, Host +70, SDK unchanged; net -2 only.
Most allocation code is retained, with service-owned runtime dependencies replacing
Registry dependencies. Delete four Voice pool/lock initialization/alias lines;
retain the allocation algorithm and add the direct service-call adaptation. Total
is 194612, net -1068 from the initial 195680. This is not broader Task/Work/native
manager completion. SDK stays at 0b8cb556d and .5; no new SDK commit or install is
needed for this Host-only internal change. No push or deployment.


### Shared durability identity validation (2026-09-14, verified implementation)

AST candidate audit and manual comparison found five copies of exact-string / UTF-8
512-byte validation and four copies each of exact authenticated ScopeRef and
DurabilityProfileBinding revalidation. Different exception types, reasons and
field labels do not justify separate validation algorithms. Enhance the existing
pure durability_identity module; callers bind their existing error contract.
Delete duplicate _text/_scope/_profile bodies, keeping domain model/state/codec
checks. No new validation framework, Store, executor, wire schema or authority.
This is internal Task durability consolidation, not evidence that Controller or
Team managers have been reused for persistent command/outbox semantics.

Tier 2 validation-sensitive refactor: preserve exact type checks (including str
subclass rejection), Unicode byte bounds, accepted whitespace/NUL behavior,
authenticated-scope requirement, profile revalidation, exception type/reason/message
and causes. Characterize before editing, run owning checkpoint/effect/recovery/
prefix tests and affected real SQLite prefix integration. Runtime/Voice execution
semantics and all timeout policies are excluded. SDK exports and .5 API stay stable.


Related Voice validation scope (same validation batch): Native carrier/runtime
identity validators duplicate native_interaction_contract._identity. Baseline
characterization confirms identical accepted sets: exact str, trimmed, 256 chars /
1024 UTF-8 bytes, rejecting Unicode Cc/Cf/Zl/Zp and invalid scalars. Call the
existing contract helper and translate only to original carrier/runtime exceptions,
reason and message (no cause). Delete duplicate bounds and validation bodies.
Tier 2 input-admission refactor; preserve all turn/generation/audio/history gates.
Run owning carrier/runtime tests, including rejected and stale zero-effect cases.
No codec field, media/latency, authorization or lifetime changes.


Validation closure: baseline SDK characterization 9 passed (an initial test-only
wrong enum spelling was corrected to existing REQUEST_ASSERTED before production
edits). After refactor, 37 SDK characterization/codec/prefix/recovery tests passed
in 1.47s. Five Host real-SQLite cases passed in 4.09s: immutable/corrupt checkpoint,
authority-free rejection, exact linked recovery, missing checkpoint and real
cancel/recovery race. Final import cleanup retained 9 passing characterization
cases. Voice baseline 2 passed; after calling the common contract, all 48 owning
carrier/runtime cases passed in 3.67s, including identity replay/stale audio and
zero forbidden history/terminal/media effects. Ruff and diff checks passed.

Independent read-only review found no blocker. SDK exceptions/reasons/messages/
causes and public __all__ are preserved; former accidental imported symbols had
no located repository consumers. Voice errors retain type/reason/message/code
and no explicit cause; internally the shared-contract exception becomes a
suppressed __context__. No traceback-identity compatibility is claimed.

Production net delta: Voice -32, Host 0, SDK -106; combined -138. This removes
repeated validation algorithms, retains error adapters and enhances the existing
identity helper rather than adding a new framework. Current combined net is
194474 (-1206 from initial 195680). Controller/Team/coroutine-manager reuse remains
bounded by actual execution semantics. In particular Coroutine TaskManager starts
inside the currently bound AnyIO group and cancels a CancelScope. The later
native-owner re-audit below corrects the incomplete caller-lifetime exclusion:
Runner already has a process-owned root, and native pending cleanup is usable.
Transient status still cannot replace durable Task command/outbox facts. No schema/API version/dependency change or new SDK wheel deployment.


Final SDK source (after import formatting) passed the same 37-test boundary in
1.35s. SDK commit: a155ce486, refactor: share durability identity validation across
task facts. The corresponding Host commit records the independent Voice contract
reuse and paired accounting; .5 APIs and pins are unchanged. Full-goal status
remains PARTIAL; neither commit proves Task/Work/Controller/Team unification.


### Recovery event subscription correspondence (2026-09-14, bounded repair verified)

Production Task event calls use authority replay in P3.create_product_subscription;
voice/text durable consumer projection uses Store consumer pages. The SDK still
also offers its documented default live-only mode. These modes intentionally
start at different positions (current head, canonical attempt prefix, durable
presentation watermark); no removal is justified solely by a mode not appearing
in current Host construction calls. Host consumer-page lifecycle convergence
remains unproved and is not closed by this repair.

Code audit found authority replay recognizes recovery boundaries but initializes
_previous_attempt_id using retry_of_attempt_id unconditionally. Store recovery
boundaries instead persist producer_attempt_id. Tier 2 recovery-read boundary:
reproduce using existing real SQLite recovery fixture, then select the canonical
predecessor field for the already-validated boundary type. Preserve authorization,
prefix/state validation, old-attempt rejection, replay and detach semantics. No
new execution, mutation, state/schema, mode/default or timeout policy. Acceptance:
reopened recovered Task subscribes successfully without Store/outbox writes; its
old producer attempt remains fenced; retry and regular subscriptions regressions.


Red/green: the real SQLite recovery/reopen subscription initially failed with
KeyError retry_of_attempt_id at SDK line 484. After selecting producer_attempt_id
for already-validated recovery boundaries, two real recovery scenarios passed
(4.10s); SDK subscription regressions passed 68 tests (2.70s), all exit 0. Ruff
and diff checks passed. Independent read-only review found no blocker. Old
producer rejection uses event-source fault injection; the positive stops at
recovery_accepted, not recovered execution terminal or full Web UI. All Task
database tables remain unchanged by subscription. SDK commit cbe90f623; this
Host evidence/test commit is its companion. No schema/API/version/dependency
change or deployment. SDK production net +2; current combined net additions
194,476 versus initial 195,680, reduction 1,204. This repair deletes no duplicate
production implementation and does not close Task management convergence.
[Exact-source checks](../evidence/DEEP_RECOVERY_SUBSCRIPTION_CHECKS_20260914.json).


### One Task subscription manager, consumer-page mode (2026-09-14, implementation scope)

Tier 2 shared reader lifecycle boundary. Enhance existing SDK TaskEventSubscription
with optional presentation_class for existing consumer_scope + authority replay;
delete Host _ConsumerTaskEventSubscription. Reuse SDK authorization, queue,
snapshot, owner-loop and close/failure handling rather than a new manager/base.
Retain Store consumer_progress_authority_page as sole cursor/prefix authority.
Demand polling, frozen pagination, rolling identity bounds, delayed ACK through
read prefix, cross-session subject/project binding, historical terminal versus
current terminal and consumed-terminal empty start remain mode semantics. No
new cursor writes, Task state, outbox, executor, cancellation command or schema.
Default live-only and full-prefix APIs remain unchanged. Existing consumer wrapper
start/close compatibility and reader-cancellation behavior must be characterized;
do not silently change product delivery or authorization policy.

Acceptance: existing real SQLite consumer text/voice paging, >queue history,
retry/reconnect, delayed ACK after eviction, stale cursor, wrong scope and terminal
race; SDK existing subscription modes; focused close/authorization/zero-write
checks. Independent complete-diff review and exact cross-repository installation
for the additive SDK API. Application presentation/ACK projection remains Host.
The cursor-specific reducer is retained code and must be reported as such; only
deleted common lifecycle/queue/state implementation counts as consolidation.


Implementation result: Host's 333-line consumer subscription class and alternate
construction are deleted. Its page/cursor validation (51+42-line method spans)
and baseline accessor (9 lines) are retained as SDK mode behavior, with queue
acceptance adapted to the existing SDK queue. Removed duplicate constructor,
authorization, owner-loop/close coordination, state snapshot and event-delivery
management are replaced by existing TaskEventSubscription methods, not a new
base framework. SDK adds 228 net production lines; Host removes 356 net; combined
net -128. Voice unchanged. Same-basis totals: Voice 112334, Host 48015, SDK 33999,
combined 194348 (-1332 versus initial195680). No changed native file is wholly
counted as new. .6 required by the additive presentation_class consumer API.

Baseline 59 Host tests passed (173.46s). Two existing Host demand/cancel tests
passed before implementation; two direct SDK counterparts failed because the
API did not exist. The merged Host boundary passed 63 tests (179.30s). Independent
review then identified close-after-validation windows in both initial and later
pages. Each was reproduced (start wrongly True / next_event wrongly delivered)
and repaired using the existing close-intent lock. Final focused 10 tests passed
(5.12s), including both windows, demand/cancel/idempotent start, wrong project,
expired grant before start/queued delivery/after Store read, and full SQLite dump
unchanged by reads/close. No tests claim physical playback or recovered execution
through terminal. The 63-test regression precedes the close-lock refinements;
the affected start/page/close paths are rechecked by the final ten, without
repeating large-history fixture generation. SDK existing modes: 68 regressions.
Independent re-review confirms both reported windows closed, no remaining blocker.


Final pairing: SDK commit 76c614a1886d7affb98b8c53e97de9e81abdb93a;
this Host commit is its companion. The first .6 wheel predated the later-page
close refinement and is not final evidence. A fresh final SDK build and isolated
pair installation reran all ten focused real SQLite scenarios, through installed
Host and SDK classes, successfully. Every installed Python file matched its
build input (Host1016/SDK2409); changed production files additionally match final
worktree hashes. Existing third-party dependencies were reused; no frontend
bundle, dependency resolution, deployment or physical audio claim. Final SDK
existing-mode regression: 68 passed in2.66s. Ruff, diff and changed-doc local-link
checks passed. [Source/test evidence](../evidence/DEEP_CONSUMER_SUBSCRIPTION_CHECKS_20260914.json)
and [final installed pair](../evidence/DEEP_CONSUMER_SUBSCRIPTION_PAIR_20260914.json).

The prior note that consumer subscription management was unproved is superseded
for this seam only. Task command/outbox, Work settlement and broader Host/Voice
lifecycle audits retain their outstanding full-goal requirements; status PARTIAL.


### Native Work owner correspondence re-audit (2026-09-14, in progress)

Code fact correction: core/runner/runner.py owns a persistent root AnyIO task
group; Host runtime/service.py acquires Runner.start with process reference
counting and releases Runner.stop after the final Runtime. The earlier statement
about caller-owned groups was incomplete. common/background_tasks.py chooses the
currently bound group, but callers can explicitly bind the existing Runner root.
Do not claim a new Host root/task-group framework is necessary.

Tier 0 characterization audit, no production behavior change: run real native
Runner root-group/TaskManager/background handles alongside real WorkRuntime and
SQLite checkpoints. Check inherited versus explicit root ownership on caller
cancellation and native pending cleanup versus Work UNKNOWN/occupied capacity.
This determines whether native ownership/settlement is actually missing before
choosing an adapter. Controlled producers do not prove Agent or Provider behavior;
actual Harness producer reuse remains covered by preceding Work integration tests.


Three real native/SQLite correspondence scenarios passed (1.62s, exit0): default
caller ownership ends with that caller; explicit Runner-root binding survives it;
native cancellation timeout leaves a protected-cleanup handle pending while
Work persists UNKNOWN and rejects capacity replacement. Completed/UNKNOWN
snapshots match a reopened SQLite Store. No mocks of manager, root or journal.
This is meaningful evidence against the previous blanket non-reuse rationale,
not proof that Work orchestration has already been integrated with TaskManager.
The producers are controlled; no full Runner.start, Host initializer or Agent
execution is claimed. Host source independently shows Runner.start acquisition
and last-owner stop in runtime/service.py.

Next implementation boundary: native ownership for the existing Work
orchestration, without a new root group or durable status projection. First verify
its cancellation/settlement behavior under actual native management, including
scheduling failure after admission and pending producer cleanup. Keep Work CAS,
revision, capacity and restart facts as domain authority. Do not simply replace
asyncio.create_task with a helper call and claim convergence. No production
code has changed in this audit; current production counts remain Voice112334,
Host48015, SDK33999, combined194348 (-1332 against initial195680).


### Work orchestration under native cancellation (2026-09-14, Tier 2)

A scheduling-seam experiment runs the unchanged Work admission/_run through the
actual native BackgroundTask/TaskManager. Cancelling that orchestration ends its
native handle while its independent physical runner remains pending. The new
positive safety test fails at operation.done(): the Work snapshot is UNKNOWN and
unsettled, but the current capacity predicate ignores it once the coordinator
ends. No production native scheduling has been enabled yet.

Owned repair: keep capacity authority on execution_settled, not coordinator
completion; wait for the actual runner and supplied settlement future in native
shielded cleanup, retaining UNKNOWN and no successful result after ownership
loss. This is required before native root integration. Preserve admission/CAS,
revision, scoped cancellation, normal shutdown bounds and Voice-close behavior;
no new database schema, Task cards, timeout values or voice latency policy.
Accept real native-cancel/SQLite held capacity, settlement truth, existing Work
cancel/update/recovery/failure tests, and independent review of the changed seam.


### Native Work owner implementation (2026-09-14, current working tree)

The earlier audit-only paragraphs above are historical. HostWorkService now passes
AgentRuntime.get_background_task_group into WorkRuntime; managed Host resolves
Runner.get_root_task_group and rejects unavailable/unstarted ownership before
admission is persisted. The existing root starts the Work orchestration directly.
A Future only reports coroutine completion; no second business state is created.
Custom initializer/standalone SDK ownership remains compatible. WorkStore and
revision/CAS/capacity/restart UNKNOWN semantics remain necessary domain authority.
This is root lifecycle reuse, not TaskManager registry or full Task/Work convergence.

Native cancellation before first execution is checked before RUNNING/producer
allocation (real root red/green test); closed-group scheduling retains UNKNOWN
without executing or replaying the request. Independent producer/cleanup must
settle before capacity or success is published. Cleanup-phase cancel/deadline
uses existing bounds and publishes UNKNOWN while physical cleanup remains owned.
No Voice timeout, database schema, project authorization or Task-card policy changed.

SDK real native/SQLite: 11 passed (1.94s); Host existing Work regressions: 37 passed
(7.10s); real Runner.start/stop + Host/SQLite probe: 1 passed (7.48s). The latter
isolates external checkpointer/extensions, not Runner or Work. Read-only review
found no remaining concrete blocker in the three production files; this is not
full candidate acceptance. Paired wheel validation and final documentation/checks
remain pending before local commit.

Same-basis production delta this batch: Voice 0, Host +13, SDK +57 = +70.
Current official-baseline net: Voice 112334, Host 48028, SDK 34056 = 194418;
1262 fewer than audit start 195680. This batch is necessary ownership/settlement
enhancement and Host adaptation, not relocation or bulk duplicate deletion.


Final batch verification: SDK 11 passed (1.94s), Host 38 passed (10.00s).
SDK .7 and Host matching pins built and installed to an isolated target;
12 native/SQLite scenarios passed there, including real Runner start/stop.
All 1016 Host / 2409 SDK installed Python files match current source bytes.
An initial reused Host build directory resurrected deleted task_core.py;
that artifact was rejected and a clean temporary source build passed the
complete file comparison. No source rollback, repository cleanup or deployment.
Ruff on changed SDK source/test and git diff --check passed. Third-party
dependencies reused the local environment; no full dependency-resolution claim.
This closes only this native-root/settlement batch, not the overall goal.

Paired SDK commit: `0420563d08a84ef207bce1f0c6b6aa569db69f54`
(`fix(work): bind orchestration to native owner and retain physical settlement`),
version `.7`; this Host commit supplies its owner, pin, integration test and evidence.


### Native Task callback ownership audit (2026-09-14, in progress, Tier 2)

After the Work root integration, inspect native TaskManager/BackgroundTask
creation and completion before reusing registry ownership. Native Task.execute
runs its RUNNING callback outside the try/finally that publishes completion and
restores context. Two real Task tests reproduce FAILED exceptions leaving status
RUNNING, no done event, leaked task context and an unclosed, unstarted coroutine.
This is a native lifecycle gap, not evidence that native reuse is impossible.
Owned repair: put start callbacks under the existing lifecycle settlement and
close the body if startup aborts before awaiting it. Preserve callback error
propagation/catch policy and ordinary body execution. No new status framework,
Task/Work table, authorization policy or Voice timeout. Verify failure, external
cancellation, zero body effects and native manager regressions. BackgroundTask
creation-callback readiness remains a separate unresolved seam; no claim that
this repair alone integrates Task/Work management.


Native Task startup repair: the existing TaskManager suite plus two new failure
cases passed (60 total, 6.42s); the final three startup cases, including external
cancellation, passed (1.63s). Independent read-only review found no concrete
blocker in this bounded repair. It does not make Task.cancel usable while its
start callback is pending; the native cancel scope is installed later.

The next creation seam is now experimentally confirmed using a real native
TaskManager, AsyncCallbackFramework and AbortError (no fake dispatch): the
TASK_CREATED callback can fail after the body starts, caller receives no
BackgroundTask handle, and the actual task still completes with its result.
See DEEP_NATIVE_TASK_CREATION_AUDIT_20260914.json. Therefore a creation exception
cannot be treated as proof of zero dispatch. Moving callbacks before scheduling
would change callback ordering/consumer behavior; it is not silently applied.
Keep this native-management batch uncommitted while determining a compatible
ownership solution; the previous .7 paired commits remain the last closed batch.


### Native TaskManager integration (2026-09-14, .8 working tree)

Work now calls the existing TaskManager.create_task inside the Host-owned Runner
root. The native registry, coroutine execution, cancellation scope and task events
manage that orchestration. Its parent task identity is explicitly detached from
the Voice caller; a real cascade_cancel probe confirms caller closure does not
cancel accepted Work. The existing completion Future is only an asyncio waiting
adapter, not another execution state or durable result ledger. WorkStore remains
the business authority for revision/CAS, UNKNOWN/no replay and physical settlement.
A native coroutine may finish while the durable Work outcome is UNKNOWN: these
are distinct facts, and native task entries never create formal product Task cards.

The existing native Task lifecycle now covers failed/cancelled start callbacks,
closes unstarted coroutines and restores task context. TaskManager's optional
synchronous on_scheduled receipt retains the actual Task before asynchronous
creation callbacks; their existing order and exception propagation are unchanged.
The existing synchronous BackgroundTask helper uses it, so already-returned
handles no longer hang after creation failure. The asynchronous create helper
still raises creation errors as before; Work retains ownership through the receipt.
No separate native task registry or new scheduler framework was added.

Real Work integration exposed logging's deepcopy of AbortError failing while
handling the original exception. Existing BaseLogEvent serialization now excludes
only the exception object from deepcopy, retaining its prior string/error fields
and deep-copying all other data. Native callback failure before Work starts has
zero body effects; failure after start produces UNKNOWN and holds capacity through
cleanup; a late observer failure does not erase an already settled real result.

Verification: 84 SDK/native/message-queue/SQLite tests passed (6.81s), followed by
the updated two root/native cancellation cases (1.61s) and three callback cases
(1.64s). Host Work regressions: 38 passed (10.23s). Counts overlap. Independent
read-only review found no concrete blocker in the current integration. Ruff passed
with existing ASYNC109 API-parameter warnings excluded; no timeout policy changed.
Pair build/install and final documentation checks remain pending before commit.

Same accounting: Voice 112334, Host 48028, SDK 34134, combined net194496;
this batch +78 (existing native enhancements +40, Work ownership adapter +38),
1184 fewer than initial195680. Native files now counted contain 2306 baseline
lines in total, not new code; current SDK affected-file total36440 is not its net
addition. No relocation or bulk duplicate deletion is claimed. Logging belongs
to shared module attribution; M4+M5 and M7+M9 remain merged. Task/Work business
management and broader full-goal closure remain incomplete.


Final .8 paired validation: clean Host/SDK source snapshots built and installed
without dependency resolution. All 1016 Host / 2409 SDK Python files match both
snapshots and current source bytes; 24 installed native/SQLite/Host scenarios
passed, including the actual native registry cancellation and callback-failure
paths. Explicit nonempty Voice parent context and native cascade_cancel leave
Work alive. No fresh Provider, physical audio or OS restart is claimed. The
asynchronous create helper's original error propagation is deliberately retained;
Work and the synchronous helper now retain the scheduled task when it matters.
This closes this native-management execution boundary only, not the full goal.

Paired SDK commit `.8`: `c46c9b2ba5ec026e8c3f1459542d46f079ea0dd6`
(`refactor(work): execute through native task management with retained ownership`).
This Host commit supplies the matching dependency pin and reviewed source/installed-pair evidence.

### Round identity convergence audit (2026-09-14, Tier 2, in progress)

At Host 977c392d / SDK c46c9b2ba, AgentConversationRuntime reserves the same
round first in JiuWenSwarmRoundHarness and then in AgentBridgeRuntime. Harness
commit_round already starts the actual Agent; Bridge's dispatcher limits event
consumers, not Agent concurrency. Its pending/reserved capacity and global output
backpressure are distinct from Harness active-round and per-round output bounds.
Retain those resource limits; converge the duplicate round identity/commit ledger
onto the existing Harness reservation/handle. Do not introduce another scheduler.

Owned surfaces: Voice composition/Bridge and Host round handle, their admission,
rollback, stale identity, capacity, close/cancel and speculative integration tests.
Preserve the synchronous after_dispatch durability barrier, exact cancellation,
output validation, history ACK truth and physical cleanup. Before removing the
duplicate ledger, verify rollback runs before any awaited speculative cleanup;
the current exception path has the opposite order. No database/schema, provider,
timeout/buffer, project policy or Task-card change is in this child boundary.

The existing admission/capacity/rollback selection passed 10 tests (6.49s).
Independent source review confirms the duplicate identity and distinct capacity
semantics; it is not implementation acceptance. Formal Task still directly owns
asyncio attempt workers: its apply/cleanup protection must be preserved before
reusing native execution management. This audit does not close that separate gap.


Round identity implementation: remove Bridge DispatchReservation, reservation
state enum, request/round fingerprint ledgers and the standalone submit/two-phase
round protocol. Existing Host require_reservation validates and returns its
canonical issued object. Bridge keeps immutable consumption tokens plus private
capacity/attachment records, bound to one Harness; attach validates the actual
Host handle. Queues, output validation and close/drain remain unchanged. These
are output resource facts, not a second round state machine. All located internal
production callers and Bridge tests use the Host identity; no wire schema change.

The speculative checkpoint failure is reproduced with the actual composition,
Harness and SpeculativeDialogue and a controlled lower Agent whose cleanup waits.
Before repair the rejected round starts while cleanup is pending. Revoking the
consumer and unstarted round before any awaited cleanup prevents fallback Agent,
tool resumption, notifications and history effects. This preserves the existing
durability contract, not removal of rollback or a new timeout policy.

Final-source checks: Bridge 32 (3.70s), selected composition/speculation 17 (7.78s),
Host joint and Work 43 (35.10s), SQLite/history reconstruction 8 (13.53s), all pass.
The earlier 95-test composition run predates private-record hardening; do not
count it as another 95 final-source tests. Independent complete-diff review found
no blockers. Ruff and diff checks pass. SDK .8 is unchanged; this batch uses the
source pair, not a new installed-wheel claim. No Provider/physical-audio/OS-restart
acceptance. See DEEP_ROUND_IDENTITY_CHECKS_20260914.json for hashes and limits.

Same-basis production: Voice112101, Host48040, SDK34134, net194275. Batch -221
(Voice -233, Host validation exposure +12, SDK0), total1405 below initial195680.
No relocation credited. Native existing baseline lines remain excluded from net
additions. Formal Task attempt worker/native management remains incomplete.

### Formal attempt native execution migration (2026-09-14, Tier 2, in progress)

The next coherent boundary must make native Task execute the existing single
_run_attempt body, not merely observe another asyncio executor. Host supplies
its Runner owner; clear the Voice parent identity. Keep journal/OS lock/cleanup
as domain-resource authority. SDK standalone/custom-owner compatibility must be
explicit, without silently falling back after a configured Host owner fails.

Code audit finds native terminal status precedes terminal callback settlement;
expose physical settlement separately without changing existing done/status
consumer semantics. Use the existing on_scheduled receipt, and keep creation
ownership until _run_attempt actually enters: startup callbacks can fail before
its finally exists. Native cancellation is level-triggered, requiring shielded
worktree acquisition through path ownership, completion-reservation/apply/result
sealing, and journal/cleanup handoff. Keep the current apply-wins-cancel policy,
deadlines, result authority, restart UNKNOWN and no-replay protection.

Owned code is native Task/BackgroundTask where necessary, SDK project executor,
and Host runtime/composition owner wiring. No new framework, data migration,
Voice latency or authorization policy. Required real SQLite/Git evidence covers
startup/callback failure, cancel during checkout/acquisition/apply/cleanup,
physical capacity/lock retention, bounded close/retry and forbidden paths.
Independent source review confirms these prerequisites; implementation remains
open and must not be committed as complete before actual native dispatch works.


Formal native implementation (.9): the single _run_attempt is now executed by native
TaskManager in the Host Runner root. The temporary precondition-only state above is
superseded for this boundary. The Host wiring is AgentServer -> P3 factory -> lazy
AgentRuntime owner; no Voice producer/session owns an accepted formal attempt.

| Responsibility/current source | Existing entry reused | Decision and retained authority | Deleted/retained implementation; evidence |
|---|---|---|---|
| Direct formal coroutine execution, previously asyncio worker in Host | TaskManager.create_task / Task.execute / native registry and cancellation scope | Adapt existing native execution; clear caller parent identity | Host path replaces independent asyncio execution with actual native Task; same _run_attempt and journal remain. Git/SQLite tests inspect native Task and exact artifact |
| Task scheduling startup/terminal observation | Existing on_scheduled, Task.wait, BackgroundTask | Enhance existing Task with optional finalizer and separate is_settled | No new registry/executor. Failed startup closes unentered coroutine and releases OS lock; callbacks/errors cannot strand dispatch |
| Project write, accepted cancellation and recovery | Existing reserve_completion, journal/CAS, D2 effects, cleanup coordinator | Retain domain transaction authority; native status is never business result | Independent cleanup remains because threads/subprocesses may outlive cancellation. Before-apply cancellation forbids target mutation; applying completion and cleanup retention are verified |
| Host initialization / lifecycle | AgentRuntime.start and Runner.get_root_task_group | Lazy adapter in existing runtime; configured owner failure fails closed | Host adds8 production lines. Custom initializer/standalone None retains declared compatibility; no hidden fallback on owner failure |
| Physical wait observers | Native Task.wait / is_settled | Bounded non-owning wait adapters | Temporary asyncio waiters do not execute Agent/project work and never cancel native owner on timeout |

Independent review found and fixed the overly broad preparation shield and startup
release-error cleanup hole. The new real Host/D2 test proves intent/checkpoint/dispatch
are present before cancellation while no target apply follows, and that caller close
leaves the same native attempt alive. Native checkout/apply/cleanup/root-cancel and
late-created-observer failures are covered; resource-acquisition cancellation retains
the actual checkout and pending lease until safe release. Review did not run tests.

Compatibility detail: Executor's private durable-outbox input is not an authentication
API. Its exact binding is task/attempt/spec fingerprint, including canonical context
scope. Tests for foreign scope change that canonical context too; changing only the
redundant outbox.scope while retaining the exact spec is not credited as a public
authorization test. Store/Host admission remains the authorization boundary; no new
permission policy or data migration was introduced in this batch.

Accounting before112101/48040/34134 (194275), after112101/48048/34307 (194456):
Voice0, Host+8, SDK+173, combined+181. SDK project adapter+143; existing native modules
+30. Relocation0; no bulk duplicate deletion claimed. Overall1224 fewer production
lines than initial195680. This is substantive execution reuse, but it does not close
the broader audit by itself. Remaining full-goal work includes final cross-module
requirements disposition, old Registry/spoken-notification oracle debt and explicitly
bounded product evidence. Historical physical Voice/provider/restart limits remain.


Final .9 boundary evidence: SDK 44 passed (39.49s), existing native API 10 passed
(2.32s), Host project regressions 21 passed (50.71s), lazy Host/factory checks4
(14.64s), real Host/D2 checks2 (13.54s). Counts are distinct within those groups;
later focused checks/installed probes overlap and are not added as new coverage.
The 21-test run preceded restoring the old standalone dispatch exception behavior;
the affected cancellation/acquisition paths are rechecked separately in evidence.
Independent review findings were fixed; final scoped Ruff/diff/link checks pass,
with six pre-existing AgentServer lint findings verified unchanged against HEAD.

Clean paired wheels were built and installed in an isolated temporary target.
All1016 Host and2409 SDK Python files match current source bytes;25 installed
scenarios pass, including actual D2 facts, project files and native lifecycle.
The initial probe's test-support import setup failed before scenarios; corrected
test-only namespaces ran without importing production source outside the installed
target. No whole-environment dependency resolution or deployment was performed.
The SDK source was rebuilt after restoring standalone exception compatibility;
only the final .9 wheel SHA in evidence is accepted. Full goal remains partial.

Pair: SDK `05faf6123365ec2aa6942efbe25dde3b3176b691` (`refactor(tasks): run formal project attempts through native task management`), .9; the Host commit containing this record is its companion. Final standalone cancellation/acquisition recheck:2 passed (9.28s), overlapping the earlier21. No push or history rewrite.


### Presentation recovery closure audit (2026-09-14, Tier 1)

Prior progress text overstated remaining permission/spoken-ACK debt: the real
revoked task.create test already replaced that retired oracle, as recorded above.
Two presentation crash tests still assume lexical/demo creation, a fake Core and
an in-memory idempotent history writer. Their intended obligations are durable
effect identity, no replay, recovered presentation and exactly-once acknowledged
history. The current real SQLite semantic recovery test covers direct clarification
presentation, but create/status currently stop at recovered receipt/effect identity.
Extend that test to real recovered Agent receipt/status presentation and history
ACK before retiring the old oracles. Owned surfaces are test/review/status only;
no product policy, Voice timing, database schema or production-count change.
Acceptance: same response/unit identity, no new model/Agent/Task execution, no
assistant history before ACK, exact history once after ACK/replayed ACK, and wrong
generation ACK cannot mutate history. Reconstruction is not full OS crash evidence.


#### Reproduced gap and scope decision (2026-09-14)

The Tier 1 assumption above was disproved. The expanded real-SQLite test first
reported 4 failed / 6 passed (82.44 s): create/status presentation was absent after
Registry/runtime reconstruction, with or without the original ACK. A refined
create/rebuild/unacknowledged test explicitly consumes the actual original Agent
presentation before reconstruction, then still fails (1 failed, 9 deselected,
35.04 s). This proves loss of already-generated presentation, not merely an
expectation that an accepted Agent has finished. The refined complete matrix has
not been rerun. Both old presentation oracles remain; no coverage deletion or
recovery-complete claim is justified. WIP tests are deliberately not committed as
a completed repair.

Actual route: Registry._run_unified_agent_submit checkpoints acceptance and
response/round identity in unified_foreground_effects. AgentConversationRuntime
constructs the original chat.final unit/content but keeps it in memory. Recovery
returns the saved acceptance payload without restoring this output. Direct
clarification has a separate persisted authoritative-presentation recovery path.
SessionFormalHistoryWriter stores only CR-admitted acknowledged text; it cannot
supply never-ACKed output. P2 generation storage contains fences, not content.
Independent read-only review reached the same conclusion; it ran no tests.

The reproduced path is unified committed input -> P2 Agent presentation, including
its current frontend P2 owner, not proof of a Native Realtime recovery defect.
Native delegation sets native_result_only=True and takes execute_native_delegate /
finish_text instead of _run_unified_agent_submit. This finding must not be used to
change Native timeout, buffering or latency policy. Current Native end-to-end
recovery has not been newly verified by these tests.

A possible repair would be Tier 3, because it adds durable presentation facts:
- Reuse the existing foreground-effect recovery_json, not another table/store.
  Retain only the actual validated final text, original response/unit identity,
  UTF-8 range/digest and explicit format version, bound to the exact accepted
  request fingerprint and execution owner. Acceptance and generated output remain
  distinct facts; append-only/idempotent promotion must reject conflicts.
- Restore that exact unit through the existing CR/presentation ledger on an
  authenticated same-input retry, with current scope and generation fencing.
  Never execute Agent/Tools again, synthesize text from Task state, relabel Agent
  output as server.authoritative, or put unacknowledged text into formal history.
- Existing exact acknowledged history may establish history already written.
  The accepted-ACK/history-write-failure window needs a defined checkpoint order;
  missing ACK cannot be inferred from a sent notification.
- Existing rows without output stay truthfully unavailable. There is no migration
  that can reconstruct their missing text. Preserve the original accepted Task.

This proposal changes storage of previously memory-only, possibly unheard Agent
text. The current recovery_json bound is 65,536 UTF-8 bytes; the existing module
has no discovered retention/purge path. Overflow behavior and retention therefore
cannot be silently invented or borrowed from the shorter clarification limit.
Before implementing this expanded persistence behavior, obtain the user's scope
choice under section four of their request (changed product/security/consumer
semantics). This is a user-authority boundary, not a generic skill approval gate.
Until decided, no production/schema/latency changes are made for this gap.

Current production accounting remains Voice112101 / Host48048 / SDK34307,
combined194456, or1224 below the initial195680. This audit does not remove production
code and is not credited as additional integration. Host944a506614ae and
SDK05faf6123365 remain the last completed pair; SDK has no upstream. Full-goal
requirements disposition and broader Host/Voice consolidation remain open.


#### Current documentation/source correspondence

A subsequent read-only recheck confirms WorkRuntime._admit persists its business
snapshot before scheduling TaskManager.create_task under the provided root;
DirectProjectCodeExecutorAdapter uses that manager for _run_attempt. Host wiring
is runtime/service.py:get_background_task_group/ensure_background_task_group,
server/agent_ws_server.py -> P3 factory and runtime/work/service.py. Controller
get_state/load_state instead copies session indexes; its scheduler's cancel path
is not application durable effect settlement. No new equivalence is inferred from
method names. The frontend ChatPanel still owns FormalTaskSessionProvider, which
uses the existing webClient/formalTaskStore; Voice consumes useFormalTaskSession.
This is source correspondence, not a new runtime acceptance run.

Corrected the SDK development guide's stale top-level claims (unimplemented Work
native ownership, Host-owned executor algorithm and .4 current version), and
marked .7/.8 intermediate pending-build prose historical. The module guide and
feature comparison now explicitly distinguish the reproduced P2 output gap from
Native and external implementations. No external source was rechecked. These are
documentation corrections; production accounting, package versions and the last
runtime verification remain unchanged. Pending presentation tests are excluded
from documentation commits and remain visible WIP, not silently removed/xfail-ed.


#### Retained Host/Voice boundary review

An exact-body candidate scan covered170 changed-production Python files and4167
functions of at least10 physical lines. Its8 candidate groups include abstract
methods, record projection, nested duplicates and native helpers unchanged from
the official Host baseline. The larger interface retry helpers, model resolvers
and adapter resolvers are pre-existing native code, not LiveVoice duplicates to
remove for this task. No deletion credit is assigned; this heuristic does not
prove absence of structurally different or frontend duplication.
[Scan and focused verification](../evidence/DEEP_RETAINED_BOUNDARY_SCAN_20260914.json)
retains source hashes, limits and exact test names.

Independent read-only review traced config/session/Agent allocation/observability.
Accepted its comment finding: the separate P2 facade cache does not bypass the
Host public-session coordinator. Corrected those three comment lines; executable
AST and physical line count are identical. It grants no new concurrency.

Exporter candidate disposition: retain current loop-bound asyncio handles.
Registry._activate_observability -> adapter -> exporter buffer owns FIFO,
backpressure, delivery handshake, export deadline and incomplete-close retention.
_attempt_export must still reconcile cancel/shield with delivery; _worker_done
accounts for buffer loss. TaskManager can run these coroutines but does not supply
that delivery algorithm. Merely substituting native handles would require owner,
callback-failure and wait adapters while retaining the business management. The
user explicitly excludes migrations just to demonstrate reuse; no replacement
or full native-exporter-management claim is made. This is an application delivery
adapter, not another Task/Work durable execution authority.

Config/session evidence mapping is now concrete: NativeAgentModelSelection calls
ServerModelCatalogResolver without constructing a model, freezes exact identity /
config version and rejects drift; that is not equivalent to reading a default.
HostWorkService resolves AgentManager instances, checks current Host generation
before and after delayed allocation, retains unsettled producers and only unpins
after cleanup. Five existing tests were selected to close this mapping gap and
passed in7.12s: valid secret-free selection, unknown/ambiguous/drift rejection with
zero model construction, old-generation fencing, generation change during lookup
with zero producer/pin effects, and close racing delayed startup with failed cleanup
retained until retry. Lower catalog/Agent/cleanup dependencies are controlled.
These checks do not close the separate P2 presentation recovery gap or physical
Voice acceptance. Production counts remain112101/48048/34307, total194456.


#### Historical oracle migration, current input boundary (Tier 1)

Owned change: two old Registry oracles and the current semantic Registry tests;
no routing, authorization, storage or timing policy change. Unexpected exceptions
must use the safe public error, seal that failure for exact replay and cause zero
Agent/Task/Executor/presentation effects. The old test injected an uncalled
resolve_production_semantics method. Its replacement injects both current semantic
resolution and journal freeze failures against real Registry/SQLite, checks the
fault was actually reached once and checks replay never reruns it. Both cases
pass (8.87s). A test-process-only mutation leaking synthetic private text through
_error_result fails at the safe-message assertion (expected1 failure,4.33s).
The initial mutation harness failed before collection because its premature import
triggered an assertion-rewrite warning; the session-start hook corrected that
harness. Neither attempt edited production source.

Removed the obsolete blanket dirty-worktree rejection oracle: accepted D-120
requires preserving authorized user edits in isolated snapshots. Current production
has no TASK_CONTEXT_WORKTREE_DIRTY emitter; retaining that fake error as the
required creation behavior would reverse the accepted contract. Its actual
replacement is test_mixed_snapshot_new_file_then_save_as_survives_restart, using
real Git, SQLite and FsOperation with controlled generated instructions. That test
and the existing journal-seal privacy regression pass (2 tests,20.23s).

Only after these checks, removed those two old tests. Ruff and diff checks pass;
affected modules collect341 cases (16.20s), which is discovery evidence only.
The historical27-failure artifact is immutable. Of its25 distinct function names,
21 remain; this is not a statement that21 currently fail. In particular both
presentation-crash oracles remain open, and their expanded failing replacement
stays uncommitted pending the user decision. No tests are xfailed or skipped.
Test deletion is not production code reduction or full fusion evidence.
