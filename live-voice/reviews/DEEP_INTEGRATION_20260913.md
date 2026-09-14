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
| Work Agent producer | NativeBusinessRouter._executor → HostWorkAgentExecutor → existing JiuWenSwarmRoundHarness → RuntimeFormalAgentFacade → AgentRuntime.stream_owned → RuntimeSessionCoordinator | 09-14 removes Work's AgentConversationRuntime/ConversationRuntimeLoop/Bridge allocation. Host admission, Agent pin and generation remain. SDK WorkRuntime owns durable state; Harness owns actual producer, exact cancel and cleanup. The result collector requires one nonempty final and COMPLETED; cancellation with failed cleanup remains UNKNOWN. This closes this execution seam, not all management overlap. |
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
