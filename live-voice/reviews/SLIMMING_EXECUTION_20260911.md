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

## Batch 2 — shared execution (active)

Preserve the current Host fixes while adopting configured Agent execution,
immutable work/model/permission binding and SDK-owned settlement. This is a
lifetime/authority seam (Tier 2/3), not a mechanical move. No newly exposed
Goal/Team/Workflow capability is enabled solely as a side effect of slimming.
The existing installed SDK and running services remain unchanged during source
integration; validate against the exact candidate SDK in an isolated process.

## Remaining batches

2. Shared Agent execution and SDK capability consumption; preserve current
   result ownership, permission/model binding and actual cancellation settlement.
3. Composition and Web controller decomposition without duplicate state owners.
4. Generic Task/Executor ownership in Host services, keeping schema/transactions.
5. Remove superseded paths and duplicate maintenance only after caller/oracle migration.
6. Configuration, dependency and document layout suitable for formal integration.

New behavior or provider/installation decisions are not inferred from path moves.
Record changed boundary and evidence here at each coherent batch completion.

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
