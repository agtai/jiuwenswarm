# Management replacement audit (active)

## Frozen scope and baseline

Host `a1e3f7eecb6cc80d4c3fcfffd306265a65a58fd1`; SDK
`b5534de51a9bc32f8cc65bf8ce4ba266e74e5771`. Both clean on
`hx/0912_livevoice`; Host ahead 47/behind 0; SDK has no upstream.
[Frozen production manifest](../evidence/MANAGEMENT_BASELINE_20260915.json)
uses the existing physical-line accounting: Voice 112140, Host 48058,
SDK 34332, combined official-baseline net 194530. Tests/docs are excluded.
The session delta will use these actual HEADs, not the earlier audit baseline.

Execution integration is delivered at specific seams. Management integration
is **incomplete**. The previous audit's packet-delivered wording does not prove
replacement of PersistentTaskCore, TaskStore, WorkRuntime or Voice business
coordination. Existing acceptance is evidence for the deployed pair only.

## Initial decisions from inspected production calls

| Responsibility / current implementation and consumers | Existing capability / real entry | Overlap and decision | Deletion / sole authority / acceptance |
|---|---|---|---|
| Task admission, cancellation, retry, reconciliation: Host P3 composition → PersistentTaskCore → SqliteTaskStore | Controller TaskManager.add_task/update_task_status/get_state; TaskScheduler.execute_ability; Team TaskDao SQL transition helpers | Partial. Controller owns mutable session indexes; Team owns dynamic session tables, dependency release and member assignment. Retain command/attempt/outbox transaction pending finer replacement; no additional Controller/Team task row | No bulk deletion claimed. TaskStore remains authoritative. Verify real SQLite replay, stale scope, ordered adjustments, cancellation and restart |
| Formal attempt management: project_executor dispatch/_run_attempt | Host AgentRuntime → Runner root → common TaskManager.create_task, on_scheduled/finalizer; Harness executes Agent | Native execution already reused. Per-attempt OS locks, threads and effect journal cannot be inferred from native coroutine status | Keep journal/physical settlement; do not count existing wiring as new deletion. Git/index/byte tests and native cancellation distinguish execution from applied results |
| Artifact collection and apply/recovery verification: project_executor | Existing _applied_result_artifacts, used by apply/checkpoint/recovery | Duplicate path resolution and streaming hashing in _attempt_result_artifacts; unused _applied_artifacts_match | Reuse existing artifact reader, delete second collector loop and unused verifier. Actual target bytes and persisted artifact hashes remain authoritative; real Git round-trip, empty/missing/outside paths and errors |
| Durable Task events: TaskEventSubscription, P3 composition and TaskProgressReturn | TaskStore atomic prefix and consumer-page readers; native TaskManager callback events | Partial. Native callback events have no durable cursor, presentation ACK or retry-segment identity. Retain subscription compatibility modes until consumer contracts can be replaced | No deletion claimed yet. Durable task_events and ACK rows remain authority, not transient callback state |
| Work start/cancel/query/recovery: HostWorkService → WorkRuntime → SqliteWorkStore | Same Runner/TaskManager and native Task.finalizer; HostWorkAgentExecutor → JiuWenSwarmRoundHarness | Actual orchestration reused but Work still wraps native completion with an independent watcher. Candidate: use native finalizer for settlement rather than a second wait lifecycle | Preserve WorkStore revision/CAS/UNKNOWN. Work producer and cleanup must settle before capacity release; no formal Task card added |
| Task/Work storage | DefaultDbStore.get_async_engine; Team DbSessions/AsyncSession | Native engine is asynchronous and Team tables are session-generated. Neither exposes current synchronous multi-table transaction or existing-database-only Work hooks | Retain transactions for now. Safe enhancement would need async public call propagation, same connection across command/outbox/effect and Host journal hooks, plus migration compatibility. Merely wrapping sqlite3 adds a framework without deleting domain management |
| Voice ordinary business: ProductCompositionRegistry Task query/result/notification, Host task_control_presentation | Existing P3 authenticated composition and TaskResultContext/TaskResultReader | Partial reuse. Registry still chooses business presentation and coordinates query/notification; inspect concrete repeated operations before replacing | Host services should own ordinary business; Voice keeps generation/source/playback authority. Full Host/Voice convergence remains incomplete |
| Sessions/configuration/Agent selection/history/frontend | Host session provisioner, AgentManager, RuntimeSessionCoordinator, ChatPanel formalTaskStore | Existing owners already used; voice-specific lifetimes still surround them | Preserve welcome-page session create, scope and accepted background lifetime. No new completion claim from import direction |

### Retention costs and consumer impacts

Replacing Controller/Team wholesale requires adding application command
idempotency, scoped authorization, ordered adjustment receipts, attempt/effect
leases and outbox atomicity to their APIs and persistence. Existing Controller
consumers expect session restoration and Team consumers expect dependency release
on completion/cancel. Reusing those transitions as application truth would change
their behavior or create a second ledger. This does not justify keeping every
subroutine: execution lifecycle, result verification and projections remain
individual replacement candidates. Checkpointer KV writes likewise do not replace
an atomic command/outbox transaction or prove a Git operation physically stopped.

## First implementation boundary: Task artifact management

Tier 2: behavior-preserving reuse of the existing applied-artifact reader.
Owned source: SDK project_executor; affected tests: SDK project integration and
Host project executor regressions. Preserve empty-diff failure, 32-artifact bound,
ordered paths, streaming byte hashing, contained regular-file checks and existing
exception behavior. No schema, authorization, timeout, deployment, private data
or user-project change. Collection and apply must use one verification algorithm;
query's bounded text disclosure remains distinct from unbounded artifact hashing.
Cold diff review and independent review are required at this boundary.

Following order: finish Task verification; replace demonstrated Work lifecycle
duplication; then continue Host/Voice business ownership. A small deletion does
not close the broader audit or management integration.

## Work settlement boundary

Tier 2, same lifecycle semantics: remove Work's second native-task completion
watcher and delegate settlement to the existing TaskManager.create_task finalizer
already used by formal attempts. Keep the completion Future only as an asyncio
consumer adapter (predecessor/close); it owns no business state. No native API or
consumer contract changes. WorkStore remains the durable outcome authority, and
_run still waits for the real producer/cleanup. Before-schedule failure settles
without running a producer; failed creation observers retain UNKNOWN and physical
capacity; late observer failure cannot erase a completed result. Verify real
Runner root, native callback failure, SQLite restore, cancellation and Host Work
regressions. Do not use coroutine completion as proof of successful business work.

## Host / Voice notification boundary

Tier 1: Registry has two implementations of Task terminal notification wording
(_prepare_progress_presentation and _terminal_notification_text), plus a duplicate
task-name formatter already present in Host task_control_presentation. Replace
the duplicated outcome rendering with one Host presentation function and reuse
Host task_subject. Preserve both callers' different unknown-outcome wording and
their existing result/authority checks. Voice still owns playback/ACK and route
selection. This removes business rendering duplication, not the whole Voice
backend. Verify named outcomes, invalid/mismatched results and existing progress
receipt/ACK regression cases. No text classifier, authorization or wire change.

## Further native comparison and retained implementation

Harness Worktree GitBackend.create resolves a configured base branch, may fetch
or enable longpaths, uses branch creation and recovers an existing worktree by
HEAD. Formal attempts instead require the accepted exact HEAD plus uncommitted
snapshot, detached creation, no reuse of an unproved checkout, protected support
paths and effect-journal reconciliation. Replacing its create/remove lifecycle
requires a no-fetch detached backend accepting the immutable snapshot and exact
cleanup proof, not merely calling the existing backend with a different path.
Harness repo_lock is repository-wide and async; the formal attempt lock is a
nonblocking per-attempt OS lease whose inode survives checkout removal. Existing
worktree-tool users expect their current branch/recovery behavior. Keep these
specific facilities rather than silently changing their consumers or lock scope.
The duplicated artifact hash loop was independently reusable and is deleted.

WorkStore.save owns sequence/CAS, immutable identity, revision lineage, initial
admission and transaction rollback. WorkRuntime keeps live controls, bounded
capacity and a conservative UNKNOWN overlay if saving fails. Native registry
entries are weak, process-local coroutine facts and have no persistent request
identity or revision store. Removing WorkStore would require a persistent native
registry with the same atomic Host journal hooks and restart/no-replay contract;
mapping Work onto Controller or Team rows instead would introduce another state
authority. Native finalizer reuse is possible without that change and is now
implemented. Producer/physical-cleanup waits remain necessary because independent
Agent/tool cleanup can outlive cancellation of the orchestration coroutine.

Host session generation, AgentManager pinning and RuntimeSessionCoordinator
remain the actual owners behind HostWorkService. Voice NativeBusinessRouter still
assembles context from the Host reader/history/Work service and validates route
capabilities, but also dispatches ordinary Task/Work operations and retains
notification projections. Task operations call the existing P3 intent bridge,
confirmation claim and authenticated invoker; Work calls the Host producer and
SDK WorkRuntime. No second model loop was found in those dispatch branches.
Their business routing and result/context projection still need further
replacement; moving the methods to another directory would not close it.

## First-batch results (not overall completion)

| Production boundary | Added | Deleted | Net | Actual replacement |
|---|---:|---:|---:|---|
| SDK project artifacts | 4 | 39 | -35 | Existing applied-artifact reader; deleted duplicate collection loop and unused verifier |
| SDK Work native settlement | 14 | 15 | -1 | Existing Task finalizer replaces the independent native completion watcher |
| Voice Registry presentation | 24 | 70 | -46 | Shared Host rendering and existing task_subject |
| Host presentation | 15 | 0 | +15 | One shared outcome renderer for the two existing callers |
| Total | 57 | 124 | -67 | No production file relocation; tests/docs excluded |

The Host renderer is consolidated business code, not a new general framework.
There is no native API enhancement in this batch. The Work finalizer closure and
artifact call are retained adapters. Existing native files are not counted as
entirely new. [Delta](../evidence/MANAGEMENT_DELTA_20260915.json) and
[current manifest](../evidence/MANAGEMENT_COUNTS_20260915.json) retain source hashes.

Source checks (Host .venv Python; pytest `-o addopts= -o log_cli=false -q`,
no shared coverage writer):

- SDK `tests/integration_tests/application_tasks/test_project_executor_application.py`:
  9 passed, real Git/SQLite, binary hash/index preservation, unchanged/deleted
  results and 32/33-artifact boundary.
- SDK `test_work_native_task_ownership.py` + `test_work_application.py`: 18 passed,
  real Runner root/SQLite, callback failure, cancellation/cleanup capacity and
  reconstruction without replay.
- Host `test_native_work_runtime.py` + `test_project_code_executor.py`, selection
  `native_work or artifact or multiple_artifacts or restart_appl or normalized or generic_task`:
  26 passed, 149 deselected.
- Host `test_product_composition_registry.py`, selection `terminal_notification or
  text_progress_reaches or real_store_progress or audio_ack_wins_progress or
  notification_only_retries`: 11 passed, 209 deselected on the final source.
- The initial combined Host/SDK pytest invocation failed at collection because
  both repositories define `tests.conftest`; separate invocations resolved it.
- Host changed presentation file Ruff passes. SDK scoped Ruff reports only the
  unchanged checkpoint-diagnostic long line and existing `_wait_workers(timeout)`
  ASYNC109; these are not altered to expand this batch. Diff whitespace and local
  Markdown target checks pass.
- [Installed pair](../evidence/MANAGEMENT_INSTALLED_PAIR_20260915.json): clean
  tracked source snapshots built into wheels and installed with no dependency
  resolution in an isolated temporary target. All 1016 Host and 2409 SDK installed
  Python files match snapshots; all four changed production files also match
  current source. Installed imports resolve there and 27 Git/SQLite/native tests
  pass (overlap with source checks above). The initial reverse inventory expected
  excluded package tests in the wheel; it was corrected before test execution.
  Third-party dependencies come from the existing environment. No deployment or
  new Provider/audio/device acceptance is claimed.

Cold complete-diff review checked error translation, empty-diff behavior,
callback-before-body failure, separate physical cleanup, and both notification
fallbacks. No independent review tool is exposed in this session; this review is
a documented non-independent substitute under TESTING.md, not an independent
review claim. The module's independent review evidence remains PARTIAL.

Final cleanup review preserves the prior exact interaction/generation barge
fence and typed/latching checkpoint failure propagation; no evidence justifies
removing those protections. The old unused artifact verifier is removed. No new
diagnostic hooks, fallback policies, buffering or timeout changes were added.

Remaining: substantive PersistentTaskCore/TaskStore management replacement,
WorkStore/admission/query management replacement and broader Voice business
routing/context ownership. These are not closed by the above small deletions,
tests, installed imports or earlier human acceptance. The active goal continues.

SDK first-batch commit: `c7cd48fe2b56ae878c4c1175936b5fd35f0ffc2a`
(`refactor(tasks): reuse artifact reader and native work finalizer`). Its companion
Host commit contains the shared renderer and this audit/evidence. Deployment is
still deferred; applying this pair later requires both new sources. No remote
update, history rewrite, private configuration or user-project change was made.

## Second boundary: one native creation-spec owner

Baseline Host `292d1101`, SDK `c7cd48fe2`. Tier 2 for the admission seam, with no
new authorization or persisted contract: the existing Core will expose its pure
creation-spec preparation and use it for create/successor. Host Executor selection
will call that same preparation instead of building a second spec. Delete Host
_resolved_create_spec and its now-unused local source helper copies; SDK source
codec registration remains the decoder/validation owner. Keep Host speech evidence
type, model/Agent selection and grants; keep Store transactional revalidation.

Preparation must perform no Store/Executor/Agent effects and grant no authority.
Successor preconditions remain Store-owned; create and successor retain their
closed payloads, exact model binding, context checks, constraints and immutable
speech source. Existing Core error codes/order are preserved. Host selection may
reject invalid context/source at native preflight before doing its pure capability
selection, while all valid requests keep the same path and result. Verify direct
Core real-SQLite admission, source replay/fences, successor creation, Host
confirmation/Executor selection, invalid/expired/wrong-scope zero effects and
cross-repository imports. No changes to Task/Work cancellation or audio policy.

### Second-boundary result and review

| Previous responsibility / consumer | Reused entry / decision | Deleted production / authority / evidence |
|---|---|---|
| Host `_resolved_create_spec` before profile selection | `PersistentTaskCore.prepare_creation_spec`, exposing and sharing existing Core validation | Delete Host spec builder; Host retains model selection, Core validates, Store admits. Real SQLite spec equality, no-effect preflight and Host creation/confirmation regressions |
| Core create and successor duplicated validation | Same native method, with prior command-specific validation order/messages | Delete both inline copies; retain distinct Store admission methods and successor preconditions |
| Host generic source helper functions | Existing SDK source codec payload helpers | Delete four Host copies; retain Host speech-specific evidence type and registration. Source tests verify immutable speech bindings |

Production delta from first pair: Host +1/-58 = -57; SDK +83/-110 = -27;
Voice unchanged. No file relocation. The 83 native lines consolidate existing
validation and expose pure preflight; they are necessary shared implementation,
not a new authorization service. Cumulative from the frozen goal baseline:
Voice +24/-70=-46; Host +16/-58=-42; SDK +101/-164=-63; total +141/-292=-151.
[Current manifest](../evidence/MANAGEMENT_CREATION_COUNTS_20260915.json),
[cumulative delta](../evidence/MANAGEMENT_CREATION_DELTA_20260915.json), and
[merged module accounting](../evidence/MANAGEMENT_CREATION_MODULES_20260915.json).

Checks on final production source:
- Host Core create/successor/authorization/context/payload/concurrent selection:
  71 passed, 291 deselected. Includes transactional admission and successor paths.
- Host native source plus P3 selected create/confirmation/scope/authority paths:
  40 passed, 173 deselected.
- Host production intent composition: 15 passed.
- SDK application boundary: 6 passed with real SQLite acceptance, replay and
  reopen. New preflight checks assert empty Store and zero Executor calls for
  malformed payload, invalid source, foreign scope and expired context. Initial
  new test failed because dataclass.replace used the read-only payload property;
  test now constructs invalid requests through CommandEnvelope.from_dict.
- Scoped SDK Ruff and both repository diff whitespace checks pass.

Cold complete-diff review: Core preserves grant checks before mutation and the
previous create/successor validation order, error reasons, model binding and
constraints. Store is still independently responsible for transactional acceptance,
not trusting preflight as authorization. No new persistent state, replay path,
executor, fallback, diagnostic or product policy was introduced. Cancel/recovery
implementations are unchanged. As in the first batch, this is a non-independent
review substitute; independent-review evidence remains PARTIAL.

Retained: Store admission revalidation cannot be deleted because direct callers
and transaction races need the checks at commit; pure preflight is not that
transaction. Host profile selection uses application model/Agent configuration
not available in the native task service. These owners stay distinct, with one
creation-spec algorithm. TaskStore, WorkStore and wider Registry business routing
remain incomplete; these bounded replacements do not close their management audit.

[Second installed pair](../evidence/MANAGEMENT_CREATION_INSTALLED_20260915.json):
clean wheels, isolated imports for both changed owners, all 1016 Host and 2409 SDK
installed Python files byte-equal to tracked snapshots, six real SQLite/application
checks passed from the installed target. These overlap source checks and do not
add product acceptance. Existing third-party dependencies were reused.

SDK second-batch commit: `6c6da6c47ef185c072fd305964d2e3954cb6e94b`
(`refactor(tasks): centralize creation spec preparation`). Host companion removes
the duplicate builder/source helpers and updates current audit/architecture. Both
sources are required for a later deployment; deployment remains explicitly deferred.
