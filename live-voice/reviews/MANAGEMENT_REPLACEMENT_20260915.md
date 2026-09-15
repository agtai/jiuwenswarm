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
