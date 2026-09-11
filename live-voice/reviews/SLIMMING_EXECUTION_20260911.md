# Behavior-preserving slimming and ownership refactor

User authorization: 2026-09-11; baseline `eb27cafd`. Complete the accepted six
batches, preserving Live Voice capability and user state. The audit is a source
inventory, not authority to remove supported behavior. Root TESTING governs
proportional checks. No remote update, dependency installation, deployment or
private-data mutation is performed merely to make a mechanical refactor pass.

## Batch 1 — production/test separation (complete)

Tier 0: relocate the twelve audited test-support/prototype files, then separate
the unused TaskCore and scripted Cascade implementation from live contract
types. Tests and validation scripts keep their current assertions and entrypoints.
Production has no new dependency on tests. Update imports, build inputs,
retirement mappings and moved-file links. Acceptance: relevant existing tests
pass from the new locations, production imports remain valid, no unique oracle
is removed, and the scoped diff is clean. No model/audio/Task behavior changes.

Results: 12 files relocated to backend/frontend test support; the 500-line
TaskCore and 250-line scripted Cascade class moved with their original bodies.
AST/import-normalized comparison confirms all moved implementation bodies are
unchanged. No production import points to tests. Only obsolete imports and the
two module descriptions changed alongside extraction. Historical source labels
in the audit remain baseline facts; live links follow relocations.

Checks: the first backend selection had 240 passes and two pre-existing manifest
drift failures (already-deleted demo fixture and six already-removed bypass/name
symbols). Git HEAD confirms the missing file/symbols preceded this batch. The
manifest now explicitly records their retirement and asserts they remain absent;
all 11 manifest checks pass. The later extraction selection passed all 87 tests
(TaskCore, executor fixture, fake vertical, InteractionEngine). Frontend focused
build/tests passed 6 fake-P1, 9 replica and 12 recorder cases. Relocation bodies,
production import direction, changed links and diff whitespace checks pass.
These overlapping selections are not added into a misleading unique test count.

## Batch 2 — shared execution (complete)

Preserve the current Host fixes while adopting configured Agent execution,
immutable work/model/permission binding and SDK-owned settlement. This is a
lifetime/authority seam (Tier 2/3), not a mechanical move. No newly exposed
Goal/Team/Workflow capability is enabled solely as a side effect of slimming.
The existing installed SDK and running services remain unchanged during source
integration; validate against the exact candidate SDK in an isolated process.

## Batch index

All six behavior-preserving batches are recorded below; numerical order follows
ownership dependencies rather than Git chronology. Final layout and deliberately
retained compatibility dependencies are in [code ownership](../architecture/CODE_OWNERSHIP.md).
Counts distinguish relocation from net deletion in the [current inventory](SLIMMING_CODE_INVENTORY_20260911.md).

## Batch 4a — Host durability ownership (complete)

Tier 0: move the six immutable durability/authorization modules as one dependency
closure to `server/runtime/durability`. Preserve implementation bodies, module
singletons, serialized identifiers and common wire-schema types. Update all
repository Python consumers; no forwarding copies. Voice-specific schema naming
is retained for compatibility, not claimed as an SDK-independent API. Store,
Executor and Native source policy stay unchanged in this step. Acceptance is
body equivalence, import resolution and existing durability/Store regressions.

Six modules / 2,953 baseline physical lines now belong to Host runtime. All
implementation bodies match the parent commit after imports are excluded; all
repository Python imports use the new owner. Existing pure contract, SQLite
authorization/recovery and Direct executor tests: 86 passed in 89.45 seconds.
No database or installed dependency changed. Fixed two support-file trailing
EOF blank lines found by the previous staged whitespace check.

## Batch 3a — Web panel decomposition (complete)

Tier 0: separate existing stateless operation/contract helpers and diagnostic
view from the React controller. Keep the single existing hook/state owner,
public panel exports, request ordering, timers, effect dependencies and JSX
unchanged. No new policy, state replica or protocol. Check declaration bodies
and existing panel/mounted tests, plus frontend typecheck for module wiring.

The controller, operation helpers and view retain all 102 original declaration
bodies (excluding export modifiers). Frontend `tsc --noEmit` passes. Existing
panel/mounted selection: 210 passed, 13 failed, one skipped. Two failures were
source-location assertions: redirected only those lookups to the helper owner;
both pass. Ten mounted failures reproduce with the exact pre-split panel bundle
(all ten fail at the same absent legacy Task controls). The remaining static
failure requires `onTaskRefresh` in unchanged ChatPanel/index.tsx. These eleven
pre-existing stale UI-oracle failures are retained and not counted as successes;
this mechanical split introduces no remaining observed failure. esbuild also
reports two pre-existing duplicate `empty` locale keys. No runtime was restarted.

## Batch 4b — Host formal Task and Executor ownership (complete)

Tier 0: re-home the seven existing formal Task/Store/adjustment/capability/file
Executor modules together. Preserve every implementation body, transaction,
SQLite schema, journal format, result and adjustment rule. Update all Python
consumers, including module monkeypatch targets. Existing common wire schema
and Native source adapter are compatibility dependencies: this is Host ownership
of the existing formal execution service, not a new generic SDK Task API. Voice
input adaptation stays in Live Voice. No runtime migration or service restart.
Acceptance: body equivalence, import/discovery checks and the current saved-file,
adjustment and Task execution regressions.

Seven modules / 27,750 baseline physical lines re-owned. All non-import AST
bodies, including delayed-import functions, are identical. Related Live Voice
and AgentServer collection succeeds: 6,645 collected (not executed). Focused
Task adjustment, file plan, real temporary-project snapshots, task handoff and
manifest selection: 86 passed in 138.16 seconds. No product Store bytes changed.

## Batch 3b — Registry result context codec (complete)

Tier 0: extract the five stateless Task result/context methods and their bounds
into `TaskResultContext`; Registry inherits those same methods without a second
state owner. Preserve source validation, artifact hash/path checks, paging and
method call signatures. No new policy, output or access grant. Existing result
context and interrupted-dialogue tests own acceptance.

All five method ASTs are identical and remain callable on Registry through a
stateless base class. Ruff import/name checks pass. Focused existing context
selection: 13 passed; the semantic query integration case already fails on the
parent Registry (expects tools disabled but the classifier chose ordinary
dialogue). Reproduced that one case by loading the exact parent module in an
isolated process, without changing source files. This pre-existing semantic
fixture mismatch is retained; result codec checks introduce no observed failure.

## Batch 5a — legacy Executor support separation (complete)

Tier 0: only tests instantiate the legacy scheduler-backed Executor; production
uses DirectProjectCodeExecutorAdapter. Move its unchanged class into test support
and migrate consumers. Retain every oracle and shared binding interface. No
production fallback, scheduling, file or cancellation behavior is removed.

## Batch 6a — isolated launcher selection (complete)

Tier 1: adopt the isolated configuration-path fix from `aff82618` without its
branch allowlist/history changes. An explicitly selected configuration directory
owns the saved launch selection; no-argument launches retain the current machine
path. No existing private file is migrated or overwritten by this source edit.
Validate PowerShell parsing and both path branches without running the launcher.

Batch 5a result: removed the 492-line legacy class from production; class AST is
identical in support and both consumers migrated. Existing Executor/integration/
manifest selection: 83 passed and one manifest substring collision (`Direct...`
contains the retired class name). The retirement check now matches whole
identifiers and the one affected test passes. No assertion was removed; the
Direct implementation was not edited. Production has no legacy-class import.

Batch 6a result: PowerShell parser reports no errors. Evaluated only the two
selection assignments: empty directory keeps the exact former machine path;
explicit directory resolves its own saved selection. No launch, private file
write, directory creation or environment installation occurred.

## Batch 2a — immutable AgentCore source (complete)

Pin the already-audited twelve-commit SDK tree `ffeb1abc` as the declared Git
dependency instead of floating upstream develop. Resolve the lock without
installing into the current environment. Consume upstream source directly; do
not vendor twelve patch copies into Live Voice. Existing 365 scoped SDK checks
on this exact tree remain reusable evidence. Runtime adoption and shared Host
execution remain separate, not implied by dependency declaration alone.

Batch 2a result: lock resolution changes only AgentCore identity/version; all
other dependency versions stay fixed. `uv lock --check` passes. Debug launcher
honors frozen source rather than exempting any same-version SDK; existing
launcher tests: 44 passed, five platform skips. Installed SDK still resolves to
`.deps/agent-core-w3`; no install/restart occurred. Source tree evidence remains
the audited 365 SDK checks. Shared execution integration is still outstanding.

## Batch 2b — configured shared execution integration (complete)

Tier 2/3: adapt the candidate Host runtime/facade/SDK binding implementation and
retire Voice-owned duplicate Agent work execution. Keep current Task result and
adjustment code; Native business vocabulary and Web/RPC entrypoints remain as
they are. Shared Goal/Team/Workflow adapters are Host capabilities and are not
new voice operations. Integrate source hunks against the common baseline so
current fixes survive. Use isolated exact-SDK processes for scoped producer,
model/tool/source, cancellation and output-owner checks before environment
adoption. No remote update or physical journey is part of this module step.

Batch 2b integration scope is now concrete: configured Agent streams, formal
Native foreground/Work, immutable model/tool/source bindings, and original
Team/SwarmFlow reply/observation owners. WebSocket chat and transport cleanup use
the shared service; old Workflow query code delegates to its Host helper. New
Core Workflow bootstrap/execution, the new Agent-input RPC adapter and new Native
Goal/Team/Workflow vocabulary were excluded, together with candidate-only tests
for those unadopted endpoints. Existing business/result/adjustment code remains.
The Responses-only wheel builder and copied patch are retired in favor of the
immutable upstream dependency.

Checks against exact SDK source: shared producer/formal/model/source/cleanup
selection passed after correcting the invocation to preserve pytest's existing
asyncio auto mode (the initial 38 async cases did not execute, not product
failures; corrected context file: 48 passed). Adapter/Goal/Team/Swarm regressions:
371 passed. Current result ownership, Native tool contract and real temporary
project late-change/save-as/restart cases: 106 passed. WebSocket routing,
disconnect and send: 106 passed. Shared reply/Team/query and changed Manager
constructor/KV-cache checks: 132 passed. Overlapping selections are not summed.
Changed-file undefined-name and whitespace checks pass. One pre-existing
Authlib deprecation warning remains outside this boundary.

Review: inspected the complete changed boundary and its ownership/cancellation,
source binding, final-output and public-entry seams. No callable independent
code-review tool is available in this session; do not claim independent review
signoff. Existing adversarial boundary tests and cold diff inspection are the
recorded substitute, without another review loop or physical run.

Environment adoption: installed only the locked AgentCore package with `uv pip
install --no-deps` into the repository `.venv`. `direct_url.json` proves exact
commit `ffeb1abc`; all 40 changed SDK Python modules match the audited source
(after newline normalization). Actual installed-package Responses/Agent and
shared-formal checks: 53 passed. Host/WebSocket/Native imports succeed. Both
`.deps/agent-core` and `.deps/agent-core-w3` remain unchanged. No service restart
or browser/Provider call was performed; source checks do not constitute live
process deployment or physical acceptance.

## Batch 3c — Registry diagnostic projection (complete)

Tier 0: extract the existing observation/metric and Task/progress diagnostic
projection methods into one implementation mixin. Registry remains the sole
route/state/lease owner; the existing adapter retains its FIFO and worker.
Preserve every method body and logger identity, with no new export policy or
authority. Verify AST equivalence and existing diagnostic ownership regressions.
Further lifecycle splitting is not required to claim fewer maintained copies.

All ten method ASTs (567 body lines) are identical. Existing exact route,
lease/export ownership and content-free durability projection checks: three
passed. Logger identity is unchanged; five now-unused Registry imports removed.
Undefined-name and whitespace checks pass. No constructor or state was added.

## Batch 6b — formal integration layout and closure (complete)

Recorded implemented SDK/Host/Voice, test, configuration and document ownership;
retained supported paths, source-evidence compatibility and distinct trust-boundary
validators explicitly. Recomputed every baseline module and moved file, including
new split files and shared services. Historical audit remains a baseline record.
No bulk protocol rewrite, user-data migration, remote update or deployment is
needed to complete this bounded refactor. Source and package layout inspection
confirms production owns no imported test implementation. Existing test failures
and paused physical acceptance remain explicit rather than relabeled as success.

Final documentation checks cover new/changed relative file links, stale imports,
tracked diff whitespace and Git exclusions. The one trailing empty line in the
new diagnostic module is removed here; no method body changes. No full-suite or
second physical run was added for this documentation closure.
