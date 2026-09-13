# R5 authorized project snapshots

The user authorized implementation with “开始” on 2026-09-07. Main's
`REALTIME_ACCEPTANCE_REPAIRS_20260907.md` execution packet supersedes the D-098
restriction to clean Git state or a completed Direct Task's managed effect.
Baseline: `af6a5bbb0cadd0e260e12961ee33f737db489d31`.

## Intended behavior and ownership

Authenticated project Task creation, successor creation and retry accept the
authorized user's current tracked and non-ignored untracked files, including
staged and unstaged edits. A dirty checkout is not a permission failure. The
existing exclusive project queue serializes actual execution; the snapshot is
fixed when the attempt starts after prior project ownership has settled.

The Direct Executor seeds that exact current snapshot into an isolated worktree.
Only Agent changes relative to the seeded snapshot may be applied back. The
original project's HEAD and index are not changed. Scope, project-root, model,
permission, unsafe-link, protected runtime-support, cancellation and exact
attempt ownership checks remain authoritative.

File tools do not provide a complete proven read-dependency set. Therefore this
repair explicitly uses the existing whole Git-visible project plus protected
support fingerprint as its conservative read/write conflict domain. Changes to
an input, target, newly created path or other file in that domain before apply
reject the attempt's writeback. There is no inferred independence or automatic
rebase. Baseline and effect identities use the existing Direct journal and D2
checkpoint/effect records; no shared schema migration is planned.

Owned source: authenticated composition/context resolution, Direct project
Executor and journal, and their focused tests. Main owns Native A-to-AA intent,
Task UI projection, shared DECISIONS/STATUS, integration and acceptance. The
worker writes only this worktree and may make one scoped R5 commit; no remote
update, running service/configuration change or user-project operation is owned.

## Risk and acceptance

Tier 3: Task admission and Direct effect/durability boundaries. Required evidence:

- P/K/X: authenticated dirty-project admission and real Direct file-tool execution
  preserve initial edits and apply only the requested result delta.
- B/I/N: exact scope/root/HEAD and supported filesystem representation; invalid
  or wrong-scope operations have zero Agent/Tool/file effects.
- S/T/C: same-project queued work takes its snapshot only after prior settlement;
  staged/unstaged edits, deleted files, input changes and new-file collisions are
  preserved; a conflicting multi-file result has zero partial application.
- R/F: restart/cleanup and D2 reconciliation preserve the same immutable baseline
  and effect proof, do not replay execution or overwrite changed user state, and
  keep cancellation or unknown outcomes distinct from completion.

Use the original repository's `.venv/Scripts/python.exe`, this worktree on
`PYTHONPATH`, and isolated test/runtime-data/temp directories. Record exact
commands and outcomes below after focused verification and independent review.

## Verification

Implementation uses the existing content-v2 expected-state format and Direct D2
checkpoint schema version 1. The expected-state digest covers the full isolated
result relative to HEAD, including initial user edits; the persisted/applied
patch remains only the task delta relative to the seed index. This fixes an
actual Windows FsOperation result failure where Git normalizes CRLF to LF.
After exact full-result/HEAD/protected-support proof, an appended effect-bound
checkpoint binds the existing artifact paths to applied byte hashes. Earlier
checkpoints remain immutable. Normal settlement, applied-effect reconciliation
and resumed apply share this operation.

The real seam uses `FsOperation.read_file/write_file`, Git worktrees/apply,
authenticated project revalidation, canonical Task Core, SQLite outbox/journal,
D2 effect records and restart/recovery. Only model generation is replaced by a
deterministic carrier. This is not a physical Provider or end-user voice test.

The snapshot fixture combines a partially staged tracked file, a staged new
file, an untracked A document, staged deletion and unstaged deletion. It creates
B and derives adjusted AA while preserving A. Each completed preservation check
compares the original `.git/index` bytes exactly and writes an isolated
`snapshot-evidence.json` with expected/actual SHA-256 and result file names.
`git --no-optional-locks` prevents inspection from refreshing the original index.

Conflict cases cover read dependency edits, output collisions, other Git-visible
edits, and a new-file collision between Git apply's check and actual apply. Both
candidate output files remain absent on pre-apply conflicts; an externally
created output remains untouched. Changes to ignored cache files outside
protected support succeed because that cache is outside the input snapshot.

Main confirmed the failure boundary: zero partial apply applies to detectable
dependency/scope conflicts. An OS/process interruption during an actual
multi-file write remains the existing D2 UNKNOWN/manual boundary, with no
automatic replay. Git apply is not claimed to be an atomic filesystem
transaction. Persistent rollback manifests/transactions are explicitly outside
this repair and no such schema is introduced.

The four pre-existing composition failures were reproduced on the untouched
original `af6a5bbb` source, with original-source PYTHONPATH and separate fixture
data/temp roots (`logs/r5-baseline-4-tests.txt`, 4 failed in 46.93s):

- `test_registry_production_classifier_bridge_store_and_core_without_hints`
  expects a removed confirmation token.
- `test_registry_production_clarification_is_owner_bound_and_single_use`
  expects clarification where current authority dispatches.
- Both completed/failed cases of
  `test_product_registry_replays_terminal_p3_authority_after_clean_checkpoint`
  require an intermediate running event rather than canonical terminal truth.

Those unchanged fixture oracles are excluded from the affected regression run;
R5 does not restore the old confirmation or running-event behavior. Initial
diagnostic runs also found and repaired the CRLF result/receipt defects above;
only the final focused/affected commands below are closure evidence. An initial
default-coverage attempt was stopped after duplicate coverage-file contention;
subsequent runs use `--no-cov` and isolated fixtures.

Final focused command, from this worktree with the original repository's venv:

```powershell
& 'C:/Users/admin/Desktop/live voice hx/.venv/Scripts/python.exe' -m pytest tests/unit_tests/live_voice/test_authorized_project_snapshots.py -q --no-cov -o log_cli=false --tb=short
```

Result: **7 passed in 101.99s**, `logs/r5-snapshots-final.txt`. PYTHONPATH was this
worktree, JIUWENSWARM_DATA_DIR was `logs/r5-final-data`, TEMP/TMP were
`logs/r5-final-temp`, all resolved within this worktree. The exact binary-index
assertions passed before and after normal settlement, restart and D2 recovery.

| Isolated fixture under `logs/r5-final-temp/pytest-of-admin/pytest-0/` | Original and final index SHA-256 | Result |
|---|---|---|
| `test_mixed_snapshot_new_file_t0/snapshot-evidence.json` | `48df3ddc9bf9300a24913d0d171075acb41bf45a6f5e6fe64c32fe9d60673e83` | A preserved; B and AA created; two serial carrier calls |
| `test_mixed_snapshot_applied_ef0/snapshot-evidence.json` | `821ccab4d2458b41c42f6cdf7763c7b403b4df0084043ed18e920ce13de5de3b` | Applied lost-ACK effect recovered; one carrier call, one apply; linked attempt completed |

Affected regression command uses `logs/r5-regression-data` and
`logs/r5-regression-temp`, with the same interpreter/PYTHONPATH and pytest options:

```powershell
& 'C:/Users/admin/Desktop/live voice hx/.venv/Scripts/python.exe' -m pytest tests/unit_tests/live_voice/test_project_code_executor.py tests/unit_tests/live_voice/test_p3_4_durability_runtime.py tests/unit_tests/live_voice/test_project_task_handoff.py tests/unit_tests/live_voice/test_p3_authenticated_composition.py -k 'not test_registry_production_classifier_bridge_store_and_core_without_hints and not test_registry_production_clarification_is_owner_bound_and_single_use and not test_product_registry_replays_terminal_p3_authority_after_clean_checkpoint' -q --no-cov -o log_cli=false --tb=short
```

Result: **321 passed, 2 skipped, 4 deselected**, one existing Authlib dependency
deprecation warning, in **635.89s** (`logs/r5-affected-01.txt`). The exclusions are
the four exact unchanged baseline failures identified above. Independent link
checks with a short isolated TEMP root confirmed **2 actual Windows junction
checks passed**; the two file/directory symlink checks skip because this host
returns WinError 1314 (no symlink creation privilege). No system permission was
changed. Evidence: `logs/r5-links-check.txt`, 2 passed / 2 skipped in 20.37s.

`ruff check` on both production files and all three affected test modules passed;
`git diff --check` passed. The original source checkout was rechecked clean at
`af6a5bbb` after the isolated baseline comparison.

Main independently read the complete R5 production diff, including normalized
full-result proof, repeated applied-state proof, immutable checkpoint append and
artifact byte rebinding. Main reported no blocking findings and accepted the
actual index-byte and lost-ACK evidence, authorizing this worker commit.

R5 worker acceptance is complete within its recorded scope. Limits remain
explicit: whole Git-visible conservative dependencies rather than a proven
per-file read set; detectable conflicts give zero apply; an OS/process failure
inside an actual write stays D2 UNKNOWN/manual with zero automatic retry, not an
OS multi-file transaction guarantee. Physical symlink checks remain host-skipped.
Main owns integration with A-to-AA intent/UI changes and human product acceptance.

## Main intent and Task projection integration

Native instructions and existing business-tool descriptions now carry the source,
new destination, all requested changes and source-preservation requirement in one
coherent Task. A known source Task uses its exact successor reference; changing
the existing deliverable itself remains an adjustment. Independent deliverables
remain separate Tasks. No schema, classifier or model selection changed.

The mounted Web panel refreshes known in-flight Tasks through read APIs every
five seconds, with fifteen-second backoff after a read failure. This continues
while voice is idle or retired. Pending mutations/confirmation, an existing read,
disconnect, replacement Session and unmount fence the refresh. It does not issue
commands, replay work or acknowledge speech. All-terminal collections stop extra
RPCs. Discovery of a never-observed Task after an initially terminal collection
is outside this fallback; existing canonical creation/discovery remains in use.

Main checks: 39 TaskExperience cases and strict scoped TypeScript passed; a real
mounted panel converged from accepted to canonical completed after 5.14 seconds,
with voice idle, no terminal notification and zero submit/mutation/speech/ACK
calls. It performs no reads after unmount. The initial mounted fixture incorrectly
returned a nonterminal result for a terminal Task and was corrected; no production
read-authority validation was relaxed. Evidence: `logs/r5-ui-tests.txt` and
`logs/r5-mounted-refresh.txt` in the integration worktree. The combined R1/R2/R5
Native Engine/tools/continuation/transport/sink run passed 369 cases in 115.94s,
including the resolved R1/R2 fixture-parameter merge. Evidence:
`logs/integration-native-r1-r2-r5.txt`.

A real configured Provider probe emitted one legal successor for the user's
A-to-AA instruction, retaining the afternoon-free condition and source-preserve
instruction. Existing-output adjustment emitted one adjust; two independent
deliverables emitted two creates. This probe only validated proposals, not Task
execution or file results. A translation generalization emitted a legal successor
plus 17 audio events, so it is not evidence of full Engine/Prepared protocol or
playback conformance. All four results remain in `logs/r5-native-intent-results.json`.
The independent audio worker reviewed Main's five production/test surfaces and
reported no blocking finding, retaining these evidence and discovery limits.
