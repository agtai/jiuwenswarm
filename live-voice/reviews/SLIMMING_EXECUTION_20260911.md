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
