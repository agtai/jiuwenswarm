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

This is the initial audit snapshot. Later implementation sections supersede its
candidate/deletion status. The resumed independent comparison below corrects
the retention rationale; in particular, Team already has transactions and CAS.

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

## Host Agent adapter cleanup boundary

Tier 0, removal of a shadowed duplicate only. JiuWenSwarm's shared Agent facade
defines `_make_retry_without_a2ui_call` twice in the same class with identical
ASTs. Python uses only the latter for both non-streaming and streaming finalization
callers. Delete the first definition; retain the existing latter implementation
and all retry/tool/interaction behavior. No new fallback or invocation is added.
Acceptance: prove both old definitions identical and every other class/body node
unchanged after deletion, compile the resulting module, and check scoped diff.
This is Host cleanup, not replacement of TaskStore/WorkStore or Voice routing.

Result: Host +0/-36=-36; no SDK or Voice production change. The retained method
is AST-identical to both prior definitions; the complete module AST differs only
by deletion of the overridden definition. Compilation and scoped whitespace checks
pass. No synthetic per-function test or full suite is needed for this unreachable
copy. Cumulative production +141/-328=-187.
[Cleanup delta and current merged counts](../evidence/MANAGEMENT_ADAPTER_CLEANUP_20260915.json)
reference the prior full manifest and identify its one changed file.

### Query and Work routing follow-up: actual retained calls

- Registry `_handle_p3_query` calls ProductP3TextAdapter.activate_prepared_query,
  which uses FormalTaskPolicy.map and P3AuthenticatedComposition.query. The latter
  re-resolves current context before Core.query and validates list results after
  the read. The ordinary query already has a Host/Core owner. Removing the adapter
  without preserving canonical resource/grant bindings and feature-off failures
  would change existing consumers, not eliminate a second Task authority.
- Registry status projection separately reads retry admission and authenticated
  task facts, with a bounded reread when event heads advance. Host's direct handle
  also uses `_read_status_retry_admission`; the retry decision is already shared.
  The remaining Registry loop joins separate snapshots to UI-supported operations.
  A substantive replacement needs a Host status snapshot API that binds task,
  attempt, event head, retry facts and operation grants. It must preserve stale
  rejection, per-operation reauthorization and diagnostic non-authority; moving
  this loop alone would not remove the duplicate read lifecycle. This API/atomic
  boundary is not implemented or claimed complete in this cleanup.
- NativeBusinessRouter._work calls the same WorkRuntime start/update/cancel/query
  and HostWorkService.get_executor; its runner delegates to HostWorkAgentExecutor
  and JiuWenSwarmRoundHarness. It has no separate Work row or scheduler. It still
  builds the admitted context and runner closure, which is business coordination
  remaining in Voice. HostWorkService currently owns producer/session-generation
  lifetime, not a complete authorized Work admission service. Merely relocating
  that closure does not satisfy replacement.
- HostWorkAgentExecutor's collect_final_text and wait_settled are distinct Harness
  facts. Replacing the latter with text completion would release capacity/Agent
  pins before real cleanup and violate cancellation/unknown semantics. Keep both.

These traces narrow the next substantive Host work to coherent status reads and
Work admission ownership. The full management objective stays active; the
shadowed-method deletion is only verified cleanup and does not close those gaps.

## Coherent status-query boundary (in progress)

Tier 3 internal cross-repository read seam; no wire/schema, grant or persisted
state change. Intended behavior: the raw status and Host capability fact derive
from the existing Store list_task_authority_snapshots_page transaction. Core
retains exact query authorization and payload checks. Host uses the snapshots
only in-process to build its existing fact; other Task snapshots never enter the
response. Remove Registry's separate fact read and bounded status reread loop.
Keep retry reauthorization, exact attempt matching, supported-operation grants,
projection validation and diagnostic non-authority. Existing ordinary Core.query
and generic adapter query owners retain their entrypoint. No new writes, Agent
calls, migrations, cancellation or audio behavior.

Owned surfaces: Core status read, Host production authority projection/query
owner, product adapter result carrier and Registry status assembly. Acceptance:
real SQLite snapshot consistency during a competing mutation; exact wrong-scope,
stale/invalid grant, malformed query, missing task and capacity rejection with
zero effects; Host status projection/authorization tests and installed pair.
Closure requires removing the actual redundant production read path, not only
adding a currently unused API. Work admission is a subsequent boundary.

### Status-query implementation and checks

Core.query_status_authority uses the existing list_task_authority_snapshots_page
transaction; ordinary Core.query shares the same authorization/result code. Host
StoreProductionTaskAuthorityReader projects those inputs using its existing
validation algorithm. ProductP3TextAdapter carries only the requested in-process
fact (or typed projection error). Registry no longer separately reads task_status
or runs a three-attempt read loop. Its exact projection checks, retry eligibility
and per-operation grants remain. Invalid supplied pairs fail closed once; the
real database race now succeeds with one coherent snapshot.

Actual production change: Voice +6/-39=-33; Host +56/-15=+41; SDK +51/-2=+49;
total +113/-56=+57. This batch adds necessary shared/native adaptation rather
than claiming a net deletion. Cumulative goal +254/-384=-130. No relocation, new
Store, parallel lifecycle, schema or dependency was introduced.

- Host authority reader + generic product adapter: 41 passed, including actual
  SQLite completion between Task-row and event/result reads. Status payload and
  Host fact retain identical state/head/Attempt; next read observes completion.
- Host authenticated composition status/query/read-cancel selection: 9 passed,
  162 deselected. Real Store and principal restrictions remain effective.
- Final Registry status/query + real Host registry permission scenario: 13 passed,
  380 deselected. Missing/malformed facts, mismatched scope/Attempt/head and typed
  projection failure remain closed with no Agent, push or project effects.
- SDK application boundary: 6 passed. Status equals ordinary query on stable
  data; invalid/expired/wrong-scope/wrong-target grants, malformed payload, wrong
  capability, missing task and capacity reject with no snapshots or effects.
  Two-task internal metadata never discloses the other task in the wire result.
  Existing durable admission/replay/reopen assertions remain.
- Scoped Ruff and both diff whitespace checks pass.

A broader status/query selection found eight existing natural-language routing
failures (implicit adjustment, result context, status routing and pending intent
recovery). All eight reproduce with the previous installed production pair,
including the same unavailable-intent/misrouting results. Three additional old-pair
failures are expected because the current tests require this new owner seam;
they are not counted as pre-existing failures. Initial baseline collection hit
an unchanged SDK SyntaxWarning promoted by pytest; ignoring only SyntaxWarning
allowed the comparison. This does not establish a green full product suite.
Those routing failures remain excluded, unresolved evidence.

Cold complete-diff review checked authorization-before-read, bounded complete
scope metadata, target-only wire output, projection exception propagation,
legacy query-owner compatibility and unchanged retry authority. The optional
metadata seam is used by actual Host production status; generic adapter owners
retain query behavior, but a Registry status owner must provide a coherent fact
or fail closed. Independent review tooling remains unavailable; this is the
recorded non-independent substitute and independent evidence stays PARTIAL.

[Installed status pair](../evidence/MANAGEMENT_STATUS_INSTALLED_20260915.json):
all 1016 Host/2409 SDK installed Python files match tracked snapshots, both owner
imports resolve to the isolated target and six SDK SQLite/application checks pass.
Third-party dependencies reused; no deployment or resolution claim. The installed
checks overlap source checks. SDK commit `b292d2eb5663bdc6d3181a0c840d5ac8933be129`
(`refactor(tasks): share atomic status authority reads`) requires its companion
Host adapter/Registry changes for the new internal status path.

Remaining: ordinary Work admission/context assembly in Voice, status operation
projection ownership, retained Task/Work management and the wider incomplete
objective. Existing barge fence, protected project artifacts, no-effective-change
failure, Work physical cleanup and deferred audio policy remain untouched.

## Work admission ownership boundary (in progress)

Tier 2; baseline Host d18acbad, SDK b292d2eb5. NativeBusinessRouter currently
creates the long-lived runner closure, capturing Router, mutable route and
delegate after Host WorkRuntime acceptance. Replace this with HostWorkService
submission using existing immutable commit/context/native authority inputs and
existing WorkRuntime.start/update. Delete the Voice executor acquisition, runner
closure, scheduling arguments and execution-authority checker. Voice keeps its
pre-admission route fence, speech context adaptation and result presentation.

Host performs the same pre-schedule and producer-time authority checks through
the existing P3 resolver. It retains neither Voice route nor delegate. Preserve
work revision/idempotency, foreground capacity, read-only tools, authority expiry,
project remap rejection, physical settlement and accepted Work surviving Voice
close. No new models, Store, schemas, permissions, mode or audio policy.
Verify real Host WorkRuntime/journal/Harness integration, stopped Voice with live
Host authority, expired/remapped authority and cancelled/update/recovery paths.
Specifically prove the accepted runner does not retain Voice objects and still
uses the captured immutable authorization when route fields disappear.

### Work ownership result

| Old implementation and consumer | Actual replacement | Deleted responsibility / retained authority |
|---|---|---|
| NativeBusinessRouter._work obtains executor, creates producer closure and calls WorkRuntime.start/update | HostWorkService.submit uses existing get_executor, WorkRuntime and HostWorkAgentExecutor | Delete Voice scheduler argument assembly and route-capturing closure; SDK WorkRuntime/WorkStore still exclusively own lifecycle/revision/durable facts |
| Router._require_work_authority called before schedule and from producer | HostWorkService.require_execution_authority calls existing P3 native authority resolver | Delete Voice execution-time checker; Host still checks accepting state, permissions and exact project. Voice request-time route fence remains |

The existing methods were not only relocated: the retained producer no longer
references Router, mutable route or delegate, and Host accepts a submission without
a Voice registry. No new executor, model, journal or background watcher was added.
Speech context construction and list/get/cancel projection remain Voice adaptations
and are not claimed removed. WorkRuntime admission and Harness settlement remain
unchanged.

Production: Voice +7/-34=-27; Host +55/-0=+55; SDK unchanged; total +62/-34=+28.
Cumulative +316/-418=-102.
[Current accounting overlay](../evidence/MANAGEMENT_WORK_ADMISSION_20260915.json)
references the last full manifest and records both changed files and all current
category/module totals. M4+M5 and M7+M9 stay merged.

Verification on final source: Host service, native WorkRuntime, Native business
registry and authority selection: **50 passed, 7 deselected**. This covers real
Runner ownership, SQLite persistence/recovery, Harness execution/cleanup,
serialized update/cancel and project rebind with zero forbidden Work/Agent
side effects. The new positive ownership fixture initially omitted its generated
specification from committed context_refs; fixing the fixture kept the production
FORMAL_CONTEXT_NOT_COMMITTED protection. A test-only import replacement mistake
was also corrected. Final scoped service Ruff and whitespace checks pass.

New ownership tests pause the accepted producer before its second authority check,
release Router/route/delegate, collect garbage and prove all three weakrefs clear.
The actual Host WorkRuntime/journal/Harness then completes with the exact result,
or Host authority revocation fails before any Agent call. The journal matches
the final settled snapshot. This verifies the ownership change; mock authority
support is not credited as external authentication/product acceptance. Existing
real P3 authority/remap integration covers the authorization seam.

Cold scoped review preserves initial route fencing, post-acquisition authority
revalidation, producer-time cancellation checks and read-only Harness tools.
The accepted closure captures the immutable native authority and committed inputs;
Voice close cannot revoke it by discarding a mutable route. Independent review
remains an unavailable-tool substitute/PARTIAL. No new package/export or SDK API
changed, so no additional wheel build is claimed or needed for this source-only
Host boundary. Prior installed evidence does not certify these new source bytes.

The Host submission entry also validates committed scope and context before
executor acquisition/admission; this preserves the existing input binding when
called without Voice. Wrong scope leaves journal/Agent effects at zero.

## Native Task origin source replacement

Tier 3 read/persistence boundary; no migration or table deletion. Existing
Task.spec.native_source proves new native creates at durable Task acceptance,
and unified_committed_inputs owns completed call receipts. Stop writing the
duplicate native_business_task_origin projection and delete its recovery-write
lifecycle. Read historical origin rows for compatibility, plus validated existing
receipts; intersect with freshly authorized Task records. New Task native source
also supports discovery when receipt completion failed after Task acceptance.
No Task mutation/replay, grant restoration or speech ACK is inferred from origin.

Owned: Host Work journal origin reader, Native Router discovery/receipt path and
Registry activation discovery. Preserve receipt integrity checks, source/scope
identity, bounded origin set, old-table integrity, route replacement fencing,
missing receipt discovery and actual presentation receipts. Existing tables and
rows stay untouched; no irreversible migration. Verify SQLite reopen, corrupt
receipts/legacy rows, capacity and cross-scope isolation, source-backed recovery
after final receipt write failure, zero duplicate Task/Agent effects and truthful
activation projection. This replaces redundant durable management, not files.

Implementation deletes `record_task_origin`, its replay caller and recovery-write
loop. New creation persists only the already-required Task and unified call
receipt; legacy schema/rows remain readable and unchanged. Receipt reads retain
exact identity/fingerprint validation and reject conflicting bindings before
returning any projection. Task native sources are accepted only for the exact
scope and create/create_successor operation. Neither source nor receipt grants
current authority: discovery remains authenticated and intersects current facts.

The old global legacy-row integrity bound remains; new receipts have a bounded
scoped read/union, rather than growing a second global ledger. Existing admission
and Task limits still apply. Context refresh now reuses the Host authenticated
creation-origin read (existing bound 128, above the visible-fact bound 32), then
rechecks current authority and route under the Registry lock. This adds a read;
no latency/performance improvement is claimed. No SDK API or data migration is
needed. The read-only legacy verifier stays until historical consumers are retired.

Verification: journal + serialized Native registry: **44 passed**. Broader
registry/authority/observation/source regression: **69 passed, 1 failed** on a
stale test double accepting only the old single-argument `task_origins` signature.
The test double now accepts the authenticated records argument; the expiry fence
and all zero-effect assertions are unchanged. The affected expiry-lock cases are
rerun separately: **2 passed, 24 deselected**. Scoped journal Ruff and
`git diff --check` pass. New real SQLite tests cover both successful and failed final
receipt writes, clear process-local origins, recover through context and activation,
assert no secondary table rows, no duplicate Task changes, no Agent invocation,
and no inferred presentation ACK. Journal tests reopen storage, preserve exact
legacy/input rows and reject corruption, conflicting sources and capacity overflow.

D-032: P/R cover both receipt outcomes and restart reads; N/B/I cover invalid
source/fingerprint, foreign scope, legacy integrity, conflict and bounds; S/T/C
reuse actual source persistence, current activation retirement and expiry while
waiting for the Registry lock. Work/audio state machines, VAD/buffer/barge fence,
15-second preparation and file effects are outside this source-read boundary.
Cold complete-diff review found no new write/replay path. Independent review
remains unavailable and PARTIAL under the existing TESTING substitute; this is
not independent-review or product-candidate acceptance. Source-only Host change:
prior installed-wheel evidence is not attributed to these changed bytes.

Accounting against Host 98c0c049: Voice +17/-27; Host +15/-67; SDK unchanged.
Batch +32/-94 = **-62** production lines. From frozen session baselines:
Voice +54/-170, Host +142/-176, SDK +152/-166; total +348/-512 = **-164**.
Current official-compatible net additions: 112024/48024/34318 = **194366**.
Compact evidence: `../evidence/MANAGEMENT_ORIGIN_20260915.json`.
This removes one duplicate durable management lifecycle; the larger Task/Work
management gaps in the decision table remain open.

## Native root scheduling ownership

Tier 3 native lifecycle API enhancement, with unchanged existing consumers.
Task project dispatch and Work admission both manually set/reset TaskManager's
private task-group and parent-id context around native scheduling. Add one
TaskManager.create_root_task entry delegating to existing create_task under the
explicit service task group and no request parent. Delete both application
context lifecycles; preserve caller handling of pre-schedule failure versus
post-schedule observer failure, finalizers and physical cleanup. Child tasks and
creation observers must inherit the service group, while the calling request's
context is restored on success, cancellation and error. Default create_task
keeps normal parent inheritance. No durable schema, product policy or authority
change, and no second scheduler. Verify real AnyIO group, nested native child,
parent cancellation isolation, context restoration, existing TaskManager suite,
Work ownership and SQLite/Git Task execution. No Provider/device claim.

Implemented: TaskManager gains a 17-line explicit root entry over its existing
scheduler. Both application owners delete private ContextVar imports and their
set/reset/exception-finally lifecycle; 4 changed call lines supply the service
group. Total SDK production +21/-19 = +2; this is a native ownership enhancement,
not a second scheduler or directory move. The original manager file is not all
counted as new. Existing default create_task behavior is untouched.

Verification: existing native manager + Work ownership + real Git/SQLite project
execution: 83 passed and one new fixture failed because it incorrectly expected
async observer exceptions to propagate (native callback framework contains them).
The fixture now injects a synchronous scheduling-receipt exception, the actual
post-schedule failure boundary, and both new cases pass (2 passed/58 deselected).
The successful case also verifies actual creation-observer context. Both cases
prove nested child ownership and that request-group/cascade cancellation leaves
service work alive while caller ContextVars are restored. Host Work/project
regression: 26 passed/149 deselected. No further production change followed tests.
Existing manager suite covers default parent trees, cancel and finalizer behavior;
application regressions cover startup failure, native cancellation and physical
settlement. Cold complete-diff review retained pre/post-scheduling ownership and
cleanup ordering. Independent-review evidence remains PARTIAL, as above.

WorkRuntime Ruff passes. Manager Ruff reports six pre-existing ASYNC109 timeout
API findings on unchanged methods; no new lint finding. Both diffs pass whitespace
checks. No package exports or Host-to-SDK API calls changed: this new method is
consumed within SDK production. Existing installed-wheel evidence is historical;
this batch claims source integration only, not a rebuilt/redeployed pair.

Accounting: Voice/Host unchanged; SDK session cumulative +173/-185 = -12.
Combined session +369/-531 = -162; official-compatible net 194368.
Evidence: `../evidence/MANAGEMENT_ROOT_SCHEDULING_20260915.json`.
Native TaskManager owns coroutine root parent/group setup; TaskStore/WorkStore
still own durable business state and executor cleanup still owns physical effects.
Those distinctions remain the concrete retention gaps documented above.

SDK implementation commit: `3ae204781` (refactor(tasks): centralize native root scheduling ownership).

## Dormant frontend intent management removal

Tier 0 unreachable production-code deletion. Whole source/repository caller
inspection finds no production import of formalTaskIntentRoute.ts or construction
of ProductFormalTaskIntentOwner; only its own tests and explicit test compilation
entry remain. LiveVoiceIntegratedRoutePanel.test already prohibits that owner.
The active panel submits through ProductUnifiedCommittedInputOwner; ChatPanel's
FormalTaskSessionProvider owns FormalP3TaskExperienceOwner. Delete the obsolete
995-line owner (confirmation state, retained RPC, sessionStorage CAS checkpoint,
restore/reconnect status polling) and its 20 obsolete-owner scenarios. Delete the
unused target-journal nullable reader; actual callers use inspect's absent/valid/
invalid union. Keep the active target journal and its historical compatibility
barrier. No data deletion/migration, no new dispatch/confirmation policy.

Old scenario mapping before deletion: exact same request replay, unresolved input
fencing and rebuilt-owner replay belong to unifiedCommittedInputOwner tests;
foreign binding, unsupported/flag-off zero effects, unknown command outcome and
scope/disconnect/reconnect no replay belong to formalP3TaskExperience tests;
disconnected late responses are covered by the active Task owner suite. The old
transport-error redaction assertion targets its retired UI snapshot; the unified
input owner exposes only pending/replay state, not that snapshot. This deletion
does not claim general frontend error-redaction coverage. Old later-utterance confirmation,
16-key v2 sessionStorage bucket/CAS, checkpoint-before-network and post-create
checkpoint transitions are no longer reachable product mechanisms, so their
private implementation tests are retired rather than preserving a test-only
production manager. Active target-journal malformed/scope/storage tests remain
and directly assert the richer inspection result. Verify current integrated web
suite and actual TS/Panel bundle compilation; no physical audio/product claim.

Implemented: deleted formalTaskIntentRoute.ts (995 production lines) and its
nullable target-journal wrapper (8). No new production code. Removed the obsolete
20-test owner suite and its test compiler/runner entry; retained current Task,
unified input and mounted Panel suites. The target-journal tests now use inspect
rather than preserving a dead public wrapper solely for tests. Whole source and
script search leaves only the existing negative Panel assertion against the old
owner. Historical evidence manifests intentionally retain original source paths.

Verification: package test:live-voice-integrated-web (existing script executed
with bundled Node and local compiler/bundler): **700 passed, 1 skipped, 0 failed**
(701 tests, 70.43 seconds). Strict TS compiler, dedicated media and actual Panel
bundles succeeded. This is automated browser/DOM evidence, not physical Provider
or human acceptance. The deleted module was already excluded from the reachable
Panel bundle; this changes retained production implementation, not running UI
behavior. No Python/SDK runtime or packaging seam changed. Complete scoped cold
review and whitespace checks pass. Tier 0 does not require an independent review;
previous higher-tier independent evidence remains PARTIAL.

Count: Voice +0/-1003, Host/SDK unchanged. Session cumulative Voice +54/-1173,
Host +142/-176, SDK +173/-185; combined +369/-1534 = -1165. Current compatible
baseline net additions 111021 + 48024 + 34320 = 193365. Production deletion does
not include 883 removed test lines or package/docs changes. Compact accounting:
`../evidence/MANAGEMENT_FRONTEND_RETIREMENT_20260915.json`.
The active target journal's binding/integrity barrier, Task control leaf and
current Host result/progress ownership are retained because inspected callers
still use them. Backend confirmation continuations also remain: unlike the dead
browser owner, they carry real one-shot durable authorization and semantic
continuation consumers. Their replacement requires preserving those consumers,
not simply deleting pending state by analogy.

## End-of-batch requirement audit and retained review boundaries

| User requirement | Current inspected evidence | Remaining boundary |
|---|---|---|
| Freeze actual paired source, preserve subsequent changes | MANAGEMENT_BASELINE; per-batch Git refs/manifests and clean statuses | No reset or history rewrite used |
| Task comparison and actual replacement | Core creation/status, project artifact reader and native root entry; initial decision table and retention costs above | Controller/Team lack scoped command/outbox/effect atomicity; existing consumers cannot silently adopt application transitions |
| Adjustment/cancel/recovery/results/events | Existing TaskStore atomic adjustment/outbox, exact project attempt/physical cleanup; event subscription requires durable cursor/ACK and retry segment | Native coroutine callbacks cannot stand in for persisted event/ACK authority; no such substitution claimed |
| Work creation/query/cancel/settlement/recovery/storage | Host service admission, native finalizer/root entry, real Work/SQLite ownership regressions | Work revision/CAS/UNKNOWN and physical cleanup remain required; no automatic formal Task card |
| Host/Voice ordinary business and frontend | Host shared presentation/status/admission; native source removal; dead 995-line browser intent manager removed | Backend semantic confirmation/pending consumers remain real; no directory move credited as replacement |
| Session/model/project/history authority | Existing Host session provisioner, AgentManager and RuntimeSessionCoordinator consumers retained; service revalidates scope/model/project | Voice still owns playback/generation and committed voice context, not authority restoration from history |
| Protect accepted product behavior | Scoped Git/SQLite/native and integrated Web tests; deployed session report independently retained | Automated fixtures are not new human running-cancel or physical audio acceptance |
| Statistics and architecture | Exclusive ownership/module manifests; M4+M5 and M7+M9; AgentServer described as runtime container | Hermes/multimodal fixed-version claims unchanged; no new benchmark inference |
| Review prior overcorrection/temporary bridges | Removed duplicate hash/spec/status/origin work and dead browser owner/wrapper; cold diff reviews | Frontend productCompositionContract retains explicit test contract-parity consumers in retirement manifest; telemetry ledger has tests/support consumers, so neither is blindly deleted |
| Local delivery only | Source commits and clean status; current paired wheel validation completed | No push, service restart, private config or user project writes; active deployed pair remains old |

An independent read-only subagent review was explicitly authorized by the user
on 2026-09-15 and dispatched across the complete frozen-to-current production
delta. Its findings and completion are not presumed here; prior PARTIAL review
labels describe evidence available at each earlier commit.

### Current paired installed-source verification

[Current installed pair](../evidence/MANAGEMENT_CURRENT_INSTALLED_20260915.json)
binds Host 120c9562 and SDK 3ae204781. Clean committed snapshots built both wheels;
all 1016 Host and 2409 SDK installed Python files match source. SDK Git/SQLite/
native ownership probes: **24 passed**. Host serialized origin recovery, real
create receipts, Work cancel/update/disconnect and journal probes: **12 passed,
32 deselected**. Each process asserted every loaded Host/SDK module came from the
isolated target, not editable production checkout imports. Third-party dependencies
were reused without network resolution. The initial archive encountered a missing
LFS documentation video; retry used command-local skip-smudge and retained pointer
content, without modifying Git configuration. This video is not a Python/runtime
dependency. No running environment was installed, restarted or redeployed. These 36 installed
test executions overlap earlier source checks and are not new additive coverage.

### Independent review completed

The explicitly authorized read-only subagent reviewed all production diffs and
relevant callers across Host a1e3f7ee..120c9562 and SDK b5534de5..3ae204781.
[Independent review record](../evidence/MANAGEMENT_INDEPENDENT_REVIEW_20260915.json):
**no evidence-supported actionable P0–P3 differential regression**. Independent
checks passed: accepted-Task/failed-receipt recovery 2; origin integrity and Host
producer Voice-release/revoked authority 8; native root context/children/cancel
isolation 2; coherent status/retry authorization 10. Total 22 source checks;
these overlap earlier scenarios and are not additive coverage.

The reviewer confirmed that origin reads intersect authorized facts and preserve
activation fencing without replay/ACK inference; native finalizers complete
waiters after producer/physical settlement; status reads retain bounded authority
and exact projection; the removed frontend owner had no production consumers.
This supersedes earlier unavailable-review PARTIAL labels **for the reviewed
production differential only**, while preserving their historical accuracy.
No production change was required by review. It does not close the retained
management gaps or establish overall product/physical Provider acceptance.
The reviewer made no filesystem/Git changes. Current installed verification and
frontend verification remain Main's evidence, not independent re-executions.

## Decision boundary: retire legacy non-atomic subscription source

Pre-change caller inspection found exactly two production TaskEventSubscription
constructors: Host P3 authenticated composition and Host TaskEventAuthorityProgressSource.
Both explicitly passed authority_atomic_replay=True. The SDK offered a default
False mode taking only TaskEventSource.get_task/get_attempt/events. It reads Task,
then Attempt, then Task again to reject a changed baseline; it starts after the
current head (live-only), unlike authority mode's retained-prefix replay.

Accepted replacement: remove _start_authorized_baseline (110 lines), its
constructor dispatch and the obsolete mode selector, and require
TaskEventAuthoritySource.event_authority_snapshot. Preserve the existing atomic
prefix and consumer-page modes, shared tail polling, validation and ACK/cursor
behavior. SqliteTaskStore already implements the required atomic API. Current
Host callers need no semantic change. No schema or data migration is required.

This is a deliberate SDK compatibility break: callers omitting the current flag,
passing False, or providing only get_task/get_attempt/events would no longer be
supported. The user confirmed below that no external callers exist; both actual
Host callers already replay. Missing atomic sources fail explicitly.
Old mode tests must be retired only after applicable scope/expiry/cancel/race
oracles are mapped to current atomic source tests; relevant shared validators
and polling cannot be deleted merely because the old startup is removed.

The user resolved this decision with “不会有其他人用”: supported consumers are
limited to these two repositories. Retire the old mode and its constructor flag;
both production callers retain their existing atomic semantics. No external SDK
compatibility bridge is required.

This boundary is Tier 3 (shared subscription interface). Owned surfaces: SDK
subscription/protocol, its integration tests/docs, two Host constructors and their
progress/durability tests. Acceptance: P/X real SQLite prefix/tail and Host cursor
consumption; N/I exact authorization and object bindings with zero mutations;
B bounded prefix/queue/validation; S/T terminal/duplicate/order and expiry;
C cancelled close during snapshot/tail reads; R retry/terminal replay; F disabled
and reader failure; K both existing production consumers and persisted formats.
Migrate applicable legacy safety oracles to atomic snapshots before retiring old
startup assumptions. Independent review and paired installed verification are
required. Schemas, ACK rules, recovery semantics, runtime deployment, voice/audio
policy and external consumers are excluded. Prior evidence above remains bound
to its recorded source until this new boundary is verified.


### Atomic-only implementation and safety-oracle migration

Deleted `_start_authorized_baseline`, obsolete `TaskEventSource` and the mode
selector; both Host constructors now call the sole atomic API. Shared tail,
consumer-page, reducer and authorization functions remain. Production delta:
SDK +8/-140, Host +0/-2, total **-134** physical lines, no moves. Cumulative
frozen-to-current delta: **+377/-1676 = -1299**. Current same-basis totals and
file hashes: [atomic subscription evidence](../evidence/MANAGEMENT_ATOMIC_SUBSCRIPTION_20260915.json).

SDK subscription suite: **64 passed**. Tail-focused tests explicitly consume
and assert the canonical initial prefix. Legacy triple-read race becomes exact
atomic cursor mismatch; its three blocking read positions become one atomic
read with both timeout/cancel close. Terminal sentinel/no-history assumptions
are replaced by real SQLite terminal-prefix/no-worker checks; the redundant
synthetic live-only terminal case is retired. Replayed sequence zero now checks
conflict against retained genesis identity. Scope, malformed source, auth,
expiry, queue/validation bounds, ordering, duplicate, worker ownership and zero
mutation assertions remain. Missing atomic interface fails before allocation
or legacy reads. A process-local mutation disabling post-read reauthorization
makes the migrated expiry test fail (`DID NOT RAISE`); normal source passes.
No mutation was written to either repository.

The authorized independent reviewer found no actionable production differential
regression or safety-oracle loss. Independent SDK 12 and Host 10 focused tests
passed; these overlap Main's tests and are not additive coverage. Review binds
the production hashes in the evidence manifest. Installed and broader Host
verification will be recorded below when completed.


Host affected regression suite: **103 passed, 5 deselected** across progress
return and durability Store tests. The initial broad run was interrupted after
no progress output; an unbuffered diagnostic located the cost inside fixture
creation (`_append_authority_adjustments(count=257)` -> Store lineage validation),
before subscription startup. Five parameterized large-volume stress cases were
excluded from the completed run: frozen unread suffix (text/voice), >256 voice
presentations, and large unread gap (text/voice). Their Store/page algorithms are
unchanged; smaller real paging, capacity, watermark, rollover, ACK and recovery
cases passed. No test failure was hidden or counted as a pass. This is module
verification, not a new full product candidate or performance claim.


Current atomic-only installed pair passed: **64 SDK subscription tests**, **19
Host cursor/recovery/lifecycle tests (89 deselected)**. Both wheels were built
from the recorded baseline archives plus exact working overlays, then installed
together into a fresh temporary target without dependencies/network resolution.
All 1016 Host and 2409 SDK installed Python files equal build snapshot bytes;
checkout comparisons normalize Windows CRLF versus archive LF. Changed production
hashes exactly match the independently reviewed hashes. Every loaded production
module in both probes was asserted under the isolated installed target. The build
driver initially could not find uv; installation used the runtime's bundled pip
wheel without installing pip or altering the working environment. No deployment,
service restart, private configuration, schema migration or user project changes.
These installed executions overlap source tests; they are not additive coverage.

SDK local commit: `3300504a7e88b4f5436040c1deace4be322c4623` — `refactor(tasks): retire legacy non-atomic event subscription`. The paired Host commit contains the two constructor updates and this evidence.


## User-adjusted objective: complete management responsibilities

Corrected after checking the original request and the user's accepted adjustment:
the five workstreams describe the overall integration roadmap. The current phase
is the formal Task application-management boundary: shared Host acceptance,
confirmation, control, query and results for Voice, text and the Task panel, with
actual duplicate production state and branches removed. Task/native comparison
informs that replacement; it does not authorize substituting an indefinite audit.
Affected Host/Voice integration, verification, review, accounting and local
commits are included. Work unification is decided after this Task boundary;
broader Work/audio lifecycle restructuring is not a concurrent phase obligation.
The earlier claim that the user reconfirmed all five as one continuous phase was
an overstatement of the conversation. User instructions supersede that wording.

Baseline for resumed work: Host 7c4802ca6aae91cdc3f056fc6572406e02dbc50c;
SDK 3300504a7e88b4f5436040c1deace4be322c4623; both clean; Host ahead 58/behind 0;
SDK has no upstream. Keep the original frozen cumulative accounting baseline.
The previous net -1299 includes -1003 dormant frontend lines and does not prove
large management replacement. Avoid repeating broad audit prose or installed
checks for incidental cleanup. Prior compatibility decisions and exclusions hold.

Goal-state correction: the earlier compatibility blocker is resolved. The user
has now saved the concrete formal Task objective in the app, and `get_goal`
confirms that full description with status `active`. The prior literal `resume`
objective and blocked status are historical, not current blockers. The app goal,
this phase description and STATUS agree: complete Task application management,
then decide Work; do not broaden audio lifecycle scope or claim that a local
cleanup closes the goal. Existing authorization remains in force.

### Resumed independent comparison: replacement feasibility

Main and the user-authorized read-only reviewer inspected the current paired
source. No production changes or test executions are credited to this comparison.
It does not establish that every retained implementation is minimal. It rejects
the following proposed wholesale substitutions on concrete consumer contracts.

| Current responsibility and consumers | Existing native entry and actual overlap | Missing interface/lifecycle and consumer impact of enhancement | Decision, sole authority and deletion status |
|---|---|---|---|
| Formal Task cancellation, adjustment, retry and recovery: authenticated P3 composition calls PersistentTaskCore, which commits through SqliteTaskStore | Controller TaskScheduler.cancel_task and TeamTaskManager.cancel both expose cancellation. Team TaskDao.start_task/claim_task use SQL CAS; cancel_task/complete_task transact state and dependency release | Controller marks CANCELED before awaiting execution termination; timeout becomes FAILED. Team commits CANCELLED and releases dependencies before execution notification. Reuse requires command identity and durable receipts, attempt/effect leases, an outbox in the same transaction, and cancellation request versus physical settlement as separate facts. Existing Controller session restoration and Team dependency release would need explicit adapters or would change behavior | Retain the Formal Task management chain. Core is orchestration and Store is atomic truth, not two competing Task managers. No full owner deletion is justified by matching method names |
| Project attempt execution and physical settlement: Core outbox → project executor → Host Agent/Harness | Native root TaskManager and Runner already own coroutine execution; Harness owns Agent execution | Native cancellation does not prove a worker thread stopped, Git apply settled, protected bytes survived, or a persisted artifact hash matches disk. An enhancement needs executor cleanup acknowledgment, durable effect identity and recovery against the actual project journal; a native Task status alias cannot supply these | Retain project attempt/effect journal as physical authority. Previous artifact-reader and native-root reuse remain bounded completed replacements; this audit adds no new deletion |
| Work admission/revision/cancellation/recovery: HostWorkService.submit → WorkRuntime → SqliteWorkStore | Native scheduling/finalizer already reused. Router.works returns the very same service.work_runtime object | Mapping to Task would require preserving Work revision supersession, foreground reservation, read-only execution, original input/context/model binding and UNKNOWN without replay; it must not invent a visible Task card. No existing alternate Work state owner was found in the Host/Voice chain | WorkRuntime remains the single Work state owner, WorkStore its checkpoint authority. Host producer pool owns session generation and Agent pins; Voice does not maintain another Work state machine |
| Native original call receipt versus current Work state: Router.handle uses the existing unified journal; WorkRuntime deduplicates admission | Journal.admit/complete/wait_for_completion already own the immutable call receipt | A repeated work.start must replay its original accepted receipt even after Work completes. WorkRuntime.query returns current state, and its request map does not retain rejected calls or original get/list/cancel responses and context. Replacing receipts with current snapshots changes recovery and repeat-call behavior | Retain both distinct facts. Do not call the receipt journal a duplicate Work store or delete it to reduce line count |
| Host producer cleanup versus Work cleanup: HostWorkService.close | Existing Harness.close, WorkRuntime.close and AgentManager.unpin_agent | Work cancellation begins before producer close; physical settlement is checked again afterward. WorkRuntime cannot release Host Agent pins or session-generation producers. Closing only the producer loses durable Work outcome ownership | Keep the ordered cleanup chain. It is one lifecycle across owners with different resources, not duplicate shutdown orchestration |
| Formal Task intent/confirmation: active frontend formalP3TaskExperience, natural committed input, NativeBusinessRouter._task | Existing Host intent resolver, authenticated composition, durable confirmation owner and call-local forwarding permit | Structured frontend still calls p3.intent; retry still calls confirmation.issue/mutate. Pending clarification/confirmation carries current origin and continuation ownership; durable confirmation proves a consumed exact grant; forwarding permit proves the current caller. Neither current Host component alone replaces all three. Native _task also calls Registry issue/confirm, so merely routing it through a new facade leaves the same management chain | Host/Voice convergence remains open. Do not retire active intent RPCs, merge different confirmation authorities, or count moving Registry methods as replacement |

Source anchors checked at the resumed paired baseline:

- SDK `openjiuwen/agent_teams/tools/database/task_dao.py`: start_task 584,
  claim_task 634, cancel_task 1238, complete_task 1316; Team manager cancel 1271.
- SDK `openjiuwen/core/controller/modules/task_scheduler.py`: timeout wrapper
  338 and cancellation 716; Controller base session restore/save 222/250.
- SDK `openjiuwen/core/application/tasks/work_runtime.py`: admission 515,
  update 707, cancel 750. Host `server/runtime/work/service.py`: submit 148,
  producer allocation 183, close 300.
- Host `channels/live_voice/native_business_router.py`: borrowed Work owner 65,
  Work calls 287, Task calls 314, immutable call receipts 413.
- Host `channels/live_voice/product_composition_registry.py`: confirmation issue
  11967, confirmation consumption 12094, production intent orchestration 12217.

These are code-review anchors, not executable evidence or permanent line numbers.
The reviewer made no edits, Git mutations, test runs or deployment changes.

The first new implementable complete replacement is still **not established**.
The adjusted goal cannot honestly promise a whole-owner deletion before finding
equivalent capabilities or specifying a bounded native enhancement. No reduction
in correctness, recovery, authorization or existing consumer behavior is implied
by the user's request to adjust the goal. Further tiny cleanups would not resolve
this feasibility gap and must not be presented as the requested delivery.

### Active implementation: queued Task control authority

Tier 2, paired boundary: SDK TaskStore update/reprioritize and atomic authority
snapshot; Host StoreProductionTaskAuthorityReader and its real structured/Native
consumers. Consolidate queued dispatch control in Store using its existing exact
unbound-queue proof (also used by cancellation/reconciliation), remove Host's
independent queue eligibility algorithm and the duplicated Store reprioritize
predicate. Read projection is advisory; exact command replay, Attempt/event-head
preconditions and write-transaction checks remain authoritative. Preserve legacy
unselected update behavior. No wire/schema migration or new Task operation.
Acceptance: real SQLite untouched/deferred/claimed/running/fenced cases, stale
reads versus later writes, exact replay, reopen and zero forbidden effects;
affected Host authority/intent checks and one independent paired review. This
owns queued control, not all Task cancellation/recovery or overall integration.

### Queued-control implementation and verification

Implemented: `TaskQueueControl` is an immutable as-of read projection, not a new
state machine or persistent table. Store `_queue_control` serves the update and
reprioritize write transactions and the existing atomic authority page. It reuses
`_is_exact_unbound_queue`, already used by cancellation/reconciliation. Host
`StoreProductionTaskAuthorityReader` retains admission-binding validation and
fingerprinting but no longer reconstructs queue eligibility. Task/Attempt/event
preconditions, command replay, transaction writes and physical cleanup retain
their existing owners. No generic manager or alternate executor was introduced.

The independent reviewer found no confirmed legal-state or atomicity regression.
The shared proof rejects zero-delivery rows with a reason/last_error: those rows
were already invalid under `PersistentAdmissionRecord.__post_init__` and Store
integrity verification. Legal creation starts at zero/NULL; deferred admission
follows a claim and advances its count. Legacy unselected update remains valid;
its raw Store admission is intentionally broader than selected-Executor UI
advertisement. Neither cancellation nor recovery implementation changed.

Paired-source commands use the Host `.venv/Scripts/python.exe`, explicit Host and
SDK checkout PYTHONPATH, and `-o addopts= -o log_cli=false -q --tb=short`:

- `test_task_admission.py`, `test_p3_production_intent_composition.py`,
  `test_production_multi_task_resolver_trust.py`, `test_persistent_task_core.py`,
  `-k 'admission or store_reader or reprioritize or predispatch_update or queue_read'`:
  **149 passed, 380 deselected**.
- The two intent composition/trust files, `-k 'not store_reader and not reprioritize'`:
  **35 passed, 15 deselected**; overlap is not additive coverage.
- Newly added `test_store_reader_queue_control_uses_same_snapshot_during_takeover`:
  **1 passed, 15 deselected**. A concurrent writer claims the dispatch between
  SELECTs; the first result stays wholly pre-claim, the next wholly post-claim.
- Independent `test_task_admission.py`,
  `-k 'host_queue_read_cannot_authorize_after_dispatch_claim or reprioritize_pending_selected_attempt_is_atomic_replayable_and_reopens'`:
  **3 passed, 114 deselected**, overlapping Main.

Two new cross-layer cases initially failed because the older admission fixture
uses a legacy capability profile rejected by the production reader. They now
use the existing canonical production fixture and pass. Tests prove stale
displayed capabilities cannot change queue/Task state after takeover, and assert
zero Executor calls; original tests cover successful update/reprioritize,
closed defer, stale identity, replay, rollback, concurrency and reopening.
No package/build configuration changed. These are current source-pair checks,
not rebuilt-wheel, deployed, physical Agent/Provider/audio or full-suite evidence.

[Exact accounting and production hashes](../evidence/MANAGEMENT_QUEUE_CONTROL_20260915.json):
Voice +0/-0; Host +6/-35; SDK +69/-45; combined **+75/-80, net -5**.
The small net reduction is reported directly: this is shared queue-control rule
ownership, not the large management-body replacement requested overall. Cumulative
production delta is +452/-1756, net -1304, including the earlier dormant frontend
deletion. Broader Task/Work/Host convergence remains unfinished.

SDK commit `e57563a308c8b55f27673e7e04e33de3f9254471`:
`refactor(tasks): share durable queue control between reads and mutations`.
The paired Host commit contains the consumer replacement, scoped tests and this
evidence. Production hashes match the reviewed/tested working source.


## Active Task recovery convergence (2026-09-15)

Tier 2, in progress from Host `83dc122c` / SDK `e57563a30`. Complete
boundary: shared Task facts and recovery for the visible Task surface and Voice;
remove duplicate Voice mutation/recovery owners while preserving exact event
provenance before presentation ACK. Independent inspection confirms the old
manual mutation controls are hidden diagnostics, not visible product consumers.
Shared Owner selection cannot substitute for background reads: it changes user
selection and invalidates concurrent reads. Its event validation must first gain
the existing leaf's identity, attempt-segment and historical-prefix guarantees.

First implementation removes duplicate initialization of the same accepted Voice
Task: `bootstrapCreatedP3ProgressRoute` must join its existing per-task progress
owner, rather than first constructing another retry-inspection leaf and running
an independent status/history recovery. Preserve accepted-input non-replay,
transient-read recovery, independent A/B owners, exact session/activation fences,
Task-target persistence and Exit cleanup. Owned surfaces are the integrated panel
and its mounted Voice creation/recovery tests. No audio policy, backend schema,
retry eligibility policy, deployment or physical-device acceptance changes.
This step is not completion of the shared Task management boundary.


### Historical alignment check and current working evidence

The recovery change above is a subordinate step, not a replacement goal or phase
closure. It currently changes only the integrated frontend panel; no common Host
acceptance/confirmation/control/result service replacement is claimed. The
focused mounted checks passed 15 cases; the strengthened Native association case
passed separately (overlapping), proving one UI status read plus two progress
initialization status reads and two event-history reads in total, without a third
Task replica. Frontend `tsc --noEmit` and `git diff --check` passed. Tests use mounted
browser/transport fixtures, not physical audio or real backend integration proof.
No commit or broad statistics update is made for this unfinished phase. Preserve
the working changes while completing the accepted Task management boundary.


### Common production intent admission: Native consumer

Tier 3 internal authority composition, in progress. Native Task business calls
currently independently resolve, issue a durable confirmation and confirm/invoke.
Replace that chain with the existing production-intent admission flow also used
by text and the Task panel. Preserve Native command IDs, typed NativeTaskSource,
current activation authority, explicit local-delegation capability checks, durable
confirmation and final authority reread. Native calls remain preclassified and
never gain a natural-language classifier or fabricated second utterance. No wire
parameter enables Native consent. Keep result/rejection projections and immutable
call receipts; no Work, audio, schema or deployment change. Validate with actual
SQLite Native create/status/adjust/cancel/replay/isolation and affected production
intent regressions. This removes a duplicate consumer orchestration chain; moving
the remaining application management out of Voice is still required.

Working evidence for common Native admission: Native registry/authority **21
passed**, including four added rejection/immutable-replay cases (capability,
confirmation, ordinary exception, Store rejection) and existing real SQLite
create/status/adjust/cancel/origin/replay checks. Semantic registry selection
`local or cancel or adjust or structured`: **38 passed, 77 deselected**. Native
command identity and persisted NativeTaskSource match the common admitted request;
completed replay does not enter admission again. An initial added assertion used
the wire `revision` shape on PersistentTaskRecord; corrected to its actual
`create_command_id` field, then the complete Native selection passed.

Independent design review found a preflight-error projection difference. Native
exceptions now propagate to the original immutable-call receipt owner; Store
rejections preserve the original nested error. New tests verify exact rejection
replay, zero Task rows and zero Agent executions. Review found no new confirmation
bypass or source loss; final complete-boundary review remains due after the Host
service/state replacement. Source changes remain uncommitted as part of that
unfinished boundary. No runtime service, private configuration or deployment
changed. Do not rerun these checks without an affected change.

### Host confirmation and execution ownership (in progress)

Tier 3 continuation of common Task admission. Extend the existing authenticated
Host composition to own confirmation binding validation, single-use consumption,
final resolution and Core dispatch in one call. Registry retains transport
continuation membership under its existing operation lock and exact receipt
validation before Voice association. No new manager, ledger, wire field or
confirmation policy. Preserve clarification origin digests, Native source,
preflight exception projection, stale-continuation rejection and unknown outcomes.
Affected evidence: real SQLite Native mutation/replay/isolation and semantic
confirmation/clarification/cancel/recovery tests; final independent boundary review
remains required. This is an implementation step toward full Task ownership,
not a claim that remaining Registry admission or frontend state is unified.

Implemented the Host confirmation-through-dispatch method. Registry no longer
constructs the call-local confirmation consumer or passes its consumed claim
between its confirmation and invocation methods. It holds the existing operation
lock, checks exact pending membership before entry and atomically claims it through
a callback immediately before Host dispatch. Create receipt validation remains
before any Voice Task association.

Current-source verification: Native registry/authority plus the entire semantic
registry file **136 passed**. This covers real SQLite create/control, cross-entry
confirmation, duplicate finals, clarification, replay and unknown Core outcomes.
The rejection selection with an added lost-continuation case **5 passed, 12
deselected** (four overlap the 136). The added case removes pending membership
after confirmation consumption and before final dispatch: rejection is replayed
exactly, with no Task rows or Agent executions.

An additional legacy Registry selection produced **11 failed, 1 passed, 210
deselected**. It reaches retired `handle_p2_submit` or a fixture whose production
intent capability is unavailable, before this confirmation flow. Those guards
are also present at HEAD; no baseline test run was performed. The failures are
retained as a test-migration limitation, not counted as current-boundary evidence
or silently converted into passes. Applicable confirmation evidence comes from
the current semantic/Native consumers above. Full module closure remains pending.

Independent read-only review found no confirmed new production-path issue. It
identified one affected test hook: in-flight mutation replay paused the removed
Registry invocation path. The test now pauses the actual Host invocation after
the real effect, preserving revoke-after-effect, replay reauthorization and the
single Task assertion. Host `test_p3_authenticated_composition.py`, selection
`production and (registry or confirmation)`: **11 passed, 160 deselected**.
`git diff --check` passed. These checks close this intermediate confirmation
change only; no phase-completion claim, local commit, deployment or full-product
acceptance is made. Remaining work includes common admission/state ownership and
the Task UI/Voice fact and recovery owners.

### Shared foreground/background Task reads (in progress)

Tier 2, existing FormalP3TaskExperienceOwner, integrated Voice recovery and their
tests. Give the Host Task owner a selection-independent status/history read used
by both Task selection and Voice initialization. Concurrent reads of the same
Task share only the in-flight read; no persistent authority cache or second Task
store. Session/connection epoch invalidates old reads, while selecting Task B must
not invalidate background Task A. Preserve bounded pagination and Voice's stricter
event/Attempt validation before progress activation; background reads never select
a Task, write selection storage, issue a command or ACK a notification. Result
reads remain selected-detail behavior. This removes duplicate read orchestration;
full event-state ownership and remaining mutation/recovery removal stay in scope.

Implemented: `select` and Voice initialization now use the same Host Task-owner
status/history reader. The reader bounds pagination and concurrent flights,
shares a flight by epoch/Session/Task, and continues between pages only while a
consumer remains current. Each consumer checks its own lifetime before using the
result. Background reads neither publish selection nor write its storage. Voice
no longer performs its separate bootstrap status plus retry-inspection status
and history reads; it validates the shared response with the existing leaf.

Independent inspection found two issues, both fixed: status/history head changes
now carry the existing retryable projection-mismatch reason, and complete checked
pages are combined before the leaf validates the event chain. Passing individual
pages to that full-history reducer was invalid. No event proof was relaxed.

Verification on current source: Task-owner **44 passed**, including joined reads
with one retired consumer, A/B selection isolation, caller/disconnect/Session
retirement with no subsequent history reads, and changed-head rejection followed
by fresh recovery. Mounted Task/progress selection **47 passed, 1 skipped**, with
paginated A/B Voice recovery, transient failures, exact progress/ACK, Native
association, AUDIO-to-TEXT fallback, and Exit cleanup. The pre-existing skipped
provider-starting capture/running-fallback case is not credited as evidence.
Full frontend `tsc --noEmit` and `git diff --check` passed.

Initial tests caught a missing import and continuation of a read after its sole
consumer retired; both were fixed. Mounted fixtures were upgraded from the old
Voice-only partial responses to complete Host status/history envelopes, preserving
their Task names and lifecycle truth. Request-count assertions now reflect the
removed extra status read and explicit pagination. These fixture corrections do
not weaken current response validation. Progress-event reconciliation still
performs its own authoritative history proof and Voice retains its leaf replica;
the obsolete manual mutation owner is also still present. This working boundary
is not the full Task phase and remains uncommitted with the earlier changes.

### Retire the duplicate manual mutation owner (in progress)

Tier 2, integrated Panel/View, stock Web activation owner, and their affected
tests. Visible Task controls already use FormalP3TaskExperienceOwner. Remove the
hidden legacy Task editor and its independent mutation/confirmation owner,
prepared mutation replica, raw-ASR Task commit branch and accepted-command polling.
Keep actual Voice progress recovery and the shared visible Task controls. Ordinary
committed speech continues through unified input; no hidden structured-Task route
may invent a second commit. No wire/backend/schema/audio policy change. Transfer
unique exact-target, unknown replay and confirmation rejection checks to the
shared Task owner before retiring old implementation-specific tests. This deletion
is explicitly the hidden manual chain, not proof that active progress state and
all Host admission are unified. Those remain required for phase completion.

### Task control/initialization group delivery

This group closes common Native admission, Host confirmation-through-dispatch,
shared initial reads, and retirement of the duplicate hidden manual controller.
It is one coherent local delivery, not completion of the full Task goal. Earlier
"uncommitted" statements above record intermediate checkpoints; the delivery
commit includes those working changes after the final checks and review.

Removed production ownership: ProductWebP3MutationOwner and its private request
fingerprint/confirmation/RPC state; Panel pending and prepared mutations, separate
issue/execute orchestration, raw-ASR Task-origin commit recovery, manual accepted
polling, retry-inspection state and hidden mutation editor. Visible issue/confirm
continue through FormalP3TaskExperienceOwner. Actual Voice progress remains;
taskRecoveryReason is a diagnostic string, never a Task/authorization owner.

Test migration is contract-specific:

| Retired implementation tests | Current evidence |
|---|---|
| Nine stock mutation-owner cases: exact targets, forged echoes, replay, unknown, definitive rejection, feature-off | Shared Task-owner exact retry wire fields, six new forged operation/command/target cases with exact retained RPC and no accepted result, existing unknown-after-Attempt-change, concurrent confirm, definitive rejection and feature-off cases |
| Hidden form create/cancel/retry display and source-regex assumptions | Visible Task control tests and a check that Voice diagnostics expose no second mutation editor |
| Five mounted hidden-form cases: manual create progress, historical selection, competing inspections and raw-ASR Task draft reconstruction | Current Native/unified create and A/B progress, shared Task selection/read epoch tests, durable Voice discovery and current committed-input recovery; the retired P2 task-submit reconstruction is deliberately absent |
| Retained P2 input locking and malformed persisted-target barrier | Kept positive/zero-effect tests; recovery reason is displayed independently of the removed editor |

Final frontend evidence: Task owner, stock activation and Panel units **206
passed**; affected mounted Task/progress/recognition/confirmation/retained/draft/
refresh selection **52 passed, 1 skipped**. The prior provider-starting capture
case remains skipped, not passed. Full `tsc --noEmit` passed. Earlier intermediate
failures exposed the accidentally removed terminal-status declaration and loss
of the recovery-reason display; both are fixed and all affected mounted checks
pass. Terminal output, queued announcements and DOM-gated ACK remain intact.

Backend evidence remains the current-source **136 passed**, the five rejection
cases including lost continuation (four overlapping), and **11 Host authority/
confirmation cases passed** recorded above. No backend source changed afterward.
The eleven legacy Registry failures remain documented; they do not become passes.
Independent read-only final review checked the complete frontend replacement and
the repaired terminal/diagnostic paths, found no remaining blocking issue, and
accepted this group for local commit. That review did not independently run Main's
tests. No new physical microphone/Provider or deployment acceptance is claimed.

[Exact accounting and production hashes](../evidence/MANAGEMENT_TASK_CONTROL_20260915.json):
Voice +155/-1309 = **-1154**; Host +174/-28 = **+146**; SDK unchanged. Combined
**+329/-1337, net -1008** from Host `83dc122c` / SDK `e57563a30`. The main reduction
is the hidden manual chain; active progress replicas still exist. Cumulative goal
production is **+781/-3093, net -2312**, including the prior 1003 dormant frontend
lines. Current official-baseline net additions: Voice **109867**, Host **48139**,
SDK **34212**, total **192218**. The three architecture headers use these same
figures; their historical bodies retain their original dated numbers.

Commit scope: these Task control/initialization production changes, directly
affected tests, corrected current phase documentation and accounting. Exclusions:
Work unification, audio lifecycle restructuring, SDK changes, runtime deployment,
remote updates, private configuration and user project files. Full common progress
state/receipt/result ownership and remaining Host admission responsibilities stay
open under the active goal.

### Shared Task fact ownership (in progress)

Tier 2, existing FormalP3TaskExperienceOwner, task event proof and integrated
Panel recovery/progress consumers. Replace Panel-owned historical/per-Voice
Task leaves with the shared Task owner's exact scoped facts. Serialize updates
per Task, retain complete event provenance/prefix/head/Attempt validation, and
prevent stale status/results from overwriting a newer observation. Voice owns
presentation/activation cancellation only; it must not disconnect Task facts.
Selecting B must not retire background A. Session/connection retirement fences
all old reads. Progress advancement withdraws stale operation/result authority
until refreshed through the common reader. No protocol, persistence, audio or
Work policy changes. Required evidence includes positive UI/Voice recovery,
A/B concurrency, stale reads/results, scope/provenance rejection with no fact or
ACK adoption, retry Attempt isolation and current mounted regressions. The
authorized independent reviewer checked this design and specifically requires
common read/commit ownership, not merely relocating a leaf map.

Implemented the browser fact boundary: FormalP3TaskExperienceOwner owns the
retained exact Task leaf and observation version. It serializes reads/progress
updates per Task and shares bounded event pagination. It retains no full-history
cache. UI selection and background consumers use this same proof state; late
result responses cannot reinstate superseded facts or permissions. List/selection
publication merges against current observations, including other Tasks advanced
while a request was pending. Reconciliation proves lifecycle, then withdraws
unrefreshed operation/admission/result projections. Voice retains only activation,
delivery/presentation, cancellation and exact consumer guards, not a Task leaf.
Voice detach does not retire shared Task facts; Host disconnect/Session retirement
does. Historical target hints are checked against authenticated status before
history reads or fact adoption. The old bootstrap/retry-inspector implementations
and their Panel exports are removed.

The existing control reducer's default 256-event bound is unchanged. The shared
owner explicitly uses the already-supported UI bound of ten 500-event pages;
all pages must share one head and the complete replay passes the original
provenance/Attempt reducer. Progress probes inherit that configured bound.
The retained Task count is bounded by the existing 500-Task collection limit.
The diagnostic error formatter stays with the Voice adapter so the common Task
reader does not import/initialize the WebSocket client; standalone package
compilation remains valid.

Independent complete-diff review found three issues and verified their fixes:
cross-Task delayed result/list overwrites; same-Task superseded-result error
handling clearing newly adopted facts; and history adoption preceding a failing
progress-receipt check. Current code validates origin and existing receipt
conflict/capacity before synchronous history/progress adoption. Dedicated tests
prove A/B preservation, retained terminal facts, and zero partial adoption for
reused receipts and forged causation. Final read-only review found no remaining
blocking issue. The reviewer did not run Main's tests.

Seven obsolete inspector-specific tests were retired with their implementation.
Their current oracles are shared-owner A/B Attempt-history and exact retry tests,
authenticated historical-hint rejection before events, dirty-worktree admission
reason preservation, same-head status/history rejection, and retired
caller/connection/Session reads. Three additional tests exercise per-Task queued
reads/progress with independent A selection, Voice retirement and Session
disconnect. All current checks retain positive scenarios and zero forbidden
effects; raw progress payloads never authorize UI facts or ACK.

Final evidence: common Task owner **67 passed** within a four-file group of
**158 passed** (Task owner, control proof, Host Session provider, Panel units).
Affected mounted Task/progress/recognition/confirmation/retained/draft/refresh
selection **52 passed, 1 skipped**. The unchanged Provider-starting case remains
skipped. Full frontend `tsc --noEmit`, the exact TypeScript compilation stage of
`test:live-voice-integrated-web`, and `git diff --check` passed. Initial failures
identified old fixtures with mismatched source/causation, invented lifecycle
events, absent Attempt/retry metadata, or incomplete Host envelopes; fixtures now
use valid accepted/running/terminal/retry histories. No production validation was
relaxed to accommodate those fixtures. Mounted recovery and Host polling after
Voice detach both pass through the actual shared Owner.

[Physical production accounting](../evidence/MANAGEMENT_TASK_FACTS_20260915.json):
Voice **+21/-215 = -194**, Host **+189/-53 = +136**, SDK unchanged; combined
**+210/-268 = -58** against `66687015`. This group removes live duplicate fact
ownership; the added shared serialization/proof is counted in full. Goal totals
are **+961/-3331 = -2370**, still including earlier dormant/hidden-chain deletions.
Official-baseline net additions are Voice **109673**, Host **48275**, SDK **34212**,
total **192160**. Production hashes and merged module totals are in the evidence.

This coherent group includes its affected tests and documentation. No backend,
SDK, Work, audio-policy, private configuration, user-project, deployment or remote
update is included. Remaining Host admission and application receipt/result
service convergence stay open under the active goal. The legacy control leaf's
unused mutation API is not credited as deleted; this group removes its duplicate
live owners and historical inspection flow, not every dormant helper.

### Host Task result observations

Tier 2, existing Host P3AuthenticatedComposition, Task control/result projection,
Native result/context and Registry result-to-Agent consumers. Replace Native's
direct Store read orchestration and Registry's background-task/artifact-read
chain with one authenticated Host observation service. Keep the SDK's existing
TaskResultReader artifact proof and the existing untrusted-context codec. Return
the exact Task/Attempt plus control facts and result observation; an unavailable
earlier query must remain unavailable even if execution finishes before the
control read. Preserve Native zero-result-byte mode, notification IDs/filtering,
and optional-read failure not rewriting an accepted receipt. Historical
presentation authority remains a distinct authenticated read contract. No new
wire/schema/policy, Work, audio or runtime deployment. Verification includes real
SQLite saved results and project artifacts, changed Attempt/scope, unavailable
result timing, Native budgets and current semantic/Native consumers. Independent
design review confirms these are two actual orchestration chains; pending intent
metadata is not a duplicate confirmation ledger and is not deleted by this group.

Resume state audit: the saved Goal remains `active` and agrees with STATUS's
formal Task phase; no new user authorization is pending. Host HEAD is
`79428f88bc47196436de6b14c73356612cf4c8c4` (ahead 62, behind 0), with this
result-observation batch uncommitted. SDK HEAD is
`e57563a308c8b55f27673e7e04e33de3f9254471`, clean, without an upstream.
The first affected backend run finished with **162 passed, 1 failed**:
`test_task_answers_use_current_facts_and_complete_results_without_tools[unavailable-result-advanced]`.
Its completion injection still patches `read_task_control_snapshot`, while this
result consumer now calls `read_task_result_observations`; the injection must
follow the real consumer and retain the original timing assertions. This is not
passing evidence. Public Host service scope/Attempt/artifact checks and final
independent implementation review remain outstanding. Continue this batch's
implementation and verification before committing; do not treat its design
review, earlier committed checks or the active Goal as current-batch acceptance.

Implementation replaces Native's direct Store presentation reads and Registry's
background-task/artifact-read sequence with the existing Host composition's
authenticated result-observation service. The presentation formatter now consumes
observations and has no Store access. Host reuses one Task snapshot for Task and
control identity, preserves an earlier supplied result observation, rejects
cross-Attempt results and uses the existing SDK artifact reader for disclosure.
Controls and saved results remain independently observed facts, not a claim of
one transaction across all projections. Historical presentation authority and
untrusted Agent-context encoding remain separate necessary consumers.

Independent review found two integration errors, both repaired: fixed status
authorization had added a requirement to Native list-only context; passing the
adjustment mutation name to a query-only reader had suppressed optional facts.
Native context now uses its existing list purpose, Native query receipts retain
their query purpose, and adjustment observations use their existing status read.
Native-purpose overrides require Native authority and cannot accept supplied
result payloads or artifact disclosure. Artifact disclosure also explicitly
requires result permission. Read-only follow-up review confirmed the fixes;
the reviewer did not run Main's tests.

The semantic timing test now injects completion at the actual Host result reader
instead of its removed caller path, retaining every original assertion. New real
SQLite/temporary-file evidence proves current saved truth, prior unavailable
truth after completion, invalid token/scope/Attempt rejection, no Native override
for bearer callers, no artifact disclosure with status-only permission, changed
file bytes withheld, zero query mutations, and the zero-result-byte projection.
Native empty/nonempty list-only contexts and optional-read failure preserve their
original success contracts. Native completed-adjust tests also assert pending
control facts and matching final applied facts/notifications. Existing project
file, adjustment/recovery and semantic/Native consumers remain in the affected
four-file regression group, which passed **166 tests**. The final adjustment
adapter/test follow-up is additionally rerun below because it changed after that
process imported source. No frontend, SDK, wire/schema, Work policy or audio
change requires a new physical Provider/browser acceptance for this read boundary.

[Physical production accounting](../evidence/MANAGEMENT_TASK_RESULTS_20260915.json):
Voice **+22/-20 = +2**, Host **+94/-28 = +66**, SDK unchanged; combined
**+116/-48 = +68** against `79428f88`. This is an actual read-orchestration
ownership replacement, with all added service/validation cost counted, not net
code removal. Cumulative Goal **+1077/-3379 = -2302**; official-baseline net
additions are Voice **109675**, Host **48341**, SDK **34212**, total **192228**.
Production hashes, per-file deltas and merged module totals are recorded. The
remaining Host admission/application receipt boundary stays open; pending intent
metadata and the historical result-presentation service are not credited deleted.

Final affected Native registry rerun: **17 passed**, including the strengthened
completed-adjust receipt/notification test on the final source. These tests overlap
the 166-test group and are not added to it as unique coverage. Scoped diff and
production evidence hashes verified; no deployment, service restart, private
configuration, user-project write, SDK change or remote update is included.
