# Shared Core Workflow start, observation and strict continuation

Initial Task 2/3 checkpoint above Main `66833d5c` (historical, before the
startup-assembly supplement below). SDK paired commit `e3a1f875c49898157ddfdea07ee863709b888909`
was reviewed as isolated `eb8e1e09f18159fe0bf9314bd26623529486781a`.
The installed tree is `deabdcba128bab8a2f22868a3cad8c1f1989fa16`, with nine
ordered source patches. Source-manifest and actual editable-import checks pass.
The actual source installer reconstructed all nine patches in
`.codex_tmp/agentcore-nine-patch-replay-rk01duvh/.deps/agent-core`; its resulting
tree exactly matches the manifest above (`reconstruction.json` records it).
The installed checkout remained clean and source/import verification passed
again after the reconstruction; no environment reinstall was needed.

## Owned behavior

The default-empty `CoreWorkflowCapabilities` directory allows only trusted
registrations whose SDK card, scope and schemas match. Common execution lives
in the existing `SessionExecutionService`: one original producer, private SDK
session, retained admission record and one pending input Future. No new scheduler
or Task store is added. Receipts acknowledge admission; actual WorkflowOutput
and settled cleanup determine completion.

Web `command.workflows` selects this family explicitly with `kind=core`; missing
kind retains SwarmFlow compatibility, and unknown kinds reject. Web requires a
trusted `CoreWorkflowBootstrap` installed through the actual AgentServer startup.
Its synchronous Web authorizer checks the current caller and declared effects;
the adapter separately verifies the actual connection and stored session owner.
This includes empty-directory reads. Missing
authority fails closed. Native `core_workflow.list/get/start/resume` uses its
existing principal/project grant and the same stored Agent/mode/project owner.
Wire fields cannot register providers, replace authority or select another owner.
Native currently accepts registered object-shaped inputs and exact node-answer
objects; both are finite and bounded before the directory's schema validation.

An original run/revision and current service epoch identify continuation. Short
control requests use the common bounded ledger without consuming a second SDK
execution slot, so a full set of input-waiting runs can still receive answers.
Successful Future delivery records its receipt before any publication wait;
failed output publication or observer cancellation cannot erase that admission.
Repeated requests reuse the original receipt and cannot deliver twice.

`WorkflowResumeGuard` uses existing checkpointer owners to prove matching saved
workflow state, updates and graph. Missing, damaged, mixed or unproven data fails
before restoration and node execution. SQLite reads all seven proof fields in
one SELECT. A synchronous guard returning None or raising runs after that read,
immediately before restoration. The original Pregel loop consumes the prepared
snapshot without a second read/start fallback. Cancellation while proof is pending
preserves the checkpoint. Root interrupted nodes are supported; nested/raw inputs,
unknown providers and old checkpoints without proof explicitly reject in strict
mode. Legacy calls without the guard keep their existing recovery behavior.

## Evidence and review

- SDK implementation: 82 affected checks passed in 19.15 s, followed by 9 checks
  for the final scope/non-serializable legacy-graph cases. These cover 65 strict
  cases and 20 existing checks, with overlap between the selections.
- Main's complete SDK production-diff review found non-None guard returns were
  ignored. Six memory/SQLite counterexamples failed before the fix; 16 affected
  guard/positive/exception checks passed afterward in 3.04 s. Main then ran 18
  independent missing-proof, changed-input, read-time revocation and no-second-
  read checks: passed in 2.58 s. The SDK test fixture was corrected to declare
  `pytest_asyncio.fixture`, so the repository's strict mode also runs it.
- Shared Host owner: 35 passed in 7.49 s using the actual stable SDK candidate,
  including input competition, same-node next revision, missing checkpoints,
  proof-time revocation, full capacity, actual cleanup and uncertain publication.
- Native contract/tools/context plus pure Core capability tests: 190 passed in
  6.59 s with normal root pytest settings. Existing Native action encodings are
  unchanged; only the new operations carry Core fields.
- Public Web/Native entry tests: 10 passed in 10.52 s, 5 additional identity/
  actual-Web-handler cases passed in 10.82 s, and 2 actual strict cross-entry
  continuation competitions passed in 5.38 s against installed SDK `e3a1f875`.
  Both entry origins share one real run, observe the actual result and replay
  without new node/provider effects.
- Independent public-boundary review prompted the delivered-receipt repair,
  session-ID validation before metadata I/O and unknown-family rejection. Main
  fixed the latter two and retained focused negative tests. New-file Ruff and
  scoped whitespace checks pass; inherited SDK Ruff counts remain 70/70.

The SDK reports and manifest remain in the isolated `workflow-resume/.test-tmp`
directory; Host owner report is `%TEMP%/jiuwen-core-owner-worker/final.html`.
This proves real SDK execution with test workflows and controlled host grants.
No particular business workflow is installed by default. These tests do not
claim browser/Provider, cross-process automatic continuation or physical
acceptance. Final cumulative verification remains in the active Goal.

## Startup assembly supplement

The user confirmed that a general integration is sufficient and supplied no
mandatory business workflow. The earlier public tests exercised real SDK
execution but installed a test-only dynamic authorization attribute. That did
not prove a supported production startup path; this missing seam is now wired.

Trusted embedding code registers its provider/card with the existing SDK Runner,
then passes `CoreWorkflowBootstrap(definitions=..., select=..., authorize_web=...)`
to `app_agentserver._run(..., core_workflow_bootstrap=...)`. The same explicit
argument reaches the original Server and AgentManager constructors. Definitions
include the exact registered provider/card, capability ID, required permissions
and continuation schemas. The selector publishes existing definitions for an
authorized stored scope; it does not grant those permissions. No import-string
loader, wire registration, business fixture or new execution scheduler is added.

Installation validates every declaration without constructing providers. Scope
binding prevalidates a batch before adding any entries and preserves equal
existing metadata objects. Current selector/install/grant checks fence effects;
new SDK resolution additionally checks the original provider/card before and
after its asynchronous factory. An already resolved run keeps its original
Workflow instance and strict checkpoint continuation even if the global SDK
registry later changes. Manager cleanup revokes this installation.

Web now uses the same exact stored user/session/project/mode/owner guard as Agent
input. The Gateway connection alone does not establish user identity. Native
retains its existing principal/context authority; metadata discovery does not
count as execution admission. The former dynamic Web authorizer path is removed.

- Bootstrap and directory: 58 passed, including atomic rejection, bounds,
  revocation during factory waits, real Workflow completion/input and original
  instance continuation after global replacement.
- Public Web/Native: 27 passed (40.39 s), including actual Server/Manager startup,
  shared real execution, strict competing continuation, wrong user, stored-scope
  races, disconnected requests, replay and zero forbidden provider/node/store
  effects. An initial 5 failures exposed the discovery/None-capability seam;
  the guard was corrected and all 27 passed.
- Actual `_run` startup: 4 passed (68.64 s). Default/None remains empty; trusted
  registration reaches the original constructors; missing SDK registration fails
  before listening. Unrelated extension/image warmup effects are isolated and
  the test stops at `server.start`, without a socket or Provider call.
- The extracted shared Web identity guard also passed the 26 existing Agent
  input public-entry/execution cases in the initial affected batch.

Independent scoped review found a metadata ABA race: A -> B -> A could retain
an owner derived from B. The shared guard now compares the returned owner's
complete mode/work-mode/project identity with the first validated snapshot,
in addition to the current stored snapshot and current facade. Three Core public
counterexamples permit both scopes at the grant layer so that fixture permission
checks cannot conceal the wrong-owner defect. Final affected Core public (30)
and Agent input public (26) checks passed together: **56 passed, 48.13 s**.
The reviewer verified closure; no assembly finding remains open. Scoped Ruff and
whitespace checks passed. These selections overlap earlier checks above.

These checks use installed SDK `ffeb1abc`, tree
`6f3826983ea8c15eb182ec7761705fd5058c1235`. Final candidate results are recorded
in [the cumulative verification record](AGENTCORE_FINAL_VERIFICATION_20260909.md).
