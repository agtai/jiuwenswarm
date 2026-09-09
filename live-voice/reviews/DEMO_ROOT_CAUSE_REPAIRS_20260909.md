# Demo root-cause repairs — accepted execution boundary

The user accepted the repair order on 2026-09-09: diagnose and fix causes, then
verify the real conversation and Task journeys before Demo preparation. This
extends the completed passive-diagnostic batch. It does not resume the broad
feature-completeness backlog or authorize remote Git updates.

## Owned boundaries and order

1. Native input delivery and failure recovery (Tier 2): reproduce the observed
   800-frame input saturation and 14.607 s browser EOT-to-render interval; measure
   queue residence, transport send/lock/drain and loop scheduling before choosing
   a fix. Own Native Session/Engine, dedicated media and browser lifecycle tests.
   Preserve input order, exact generation ownership, bounded memory, no stale
   audio/history revival and zero replayed business effects. A physical network
   or Provider limitation must remain explicit if outside the product's control.
2. Executor worktree fidelity (Tier 3, file durability): preserve the admitted
   authorized source bytes through worktree seeding and result application.
   Own project_code_executor and its preservation/atomic-apply tests. Keep strict
   baselines, source-change detection and protected-file boundaries. Cover Git
   conversion/attributes, binary files, deletion and dirty snapshots. No global
   Git configuration change and no substitution of content-normalized hashes.
3. Business facts publication/binding (Tier 2): refresh changed Task facts outside
   the shared audio lock, publish before binding a successor response, preserve
   immutable in-flight bindings and revalidate present authority. Own Native
   Engine/Router and exact-context/race tests. No permission cache and no blind
   replay of mutating operations.
4. Prepared response and cleanup compatibility (Tier 2): use structural failure
   evidence to locate the rejected branch, then fix the supported Provider
   response/cleanup lifecycle without relaxing output admission.
5. Integrated verification: real ordinary speech, Task create/query/adjust/result
   notification, interruption and recovery; complete component timing and retain
   failed attempts. The existing physical calibration protocol remains required
   for last-phoneme-to-headphone claims. Unobservable one-way/network/Provider
   internals stay unknown, not inferred by subtracting unrelated clocks.
6. Closure: unify launcher local URLs, update the owning status/runbook and
   controlled deployment; prepare a small separate Demo business project after
   repairs. Work/projectless support, Task intent/result semantics item 4, model
   replacement and broad productization stay excluded.

## Verification and review

Use root TESTING.md's applicable P/N/B/S/T/C/R/I/F/K/X dimensions per module.
Reproduce each defect before changing behavior; use focused affected regressions,
cold scoped-diff review and independent Tier 2/3 boundary review. No full-suite
green or physical acceptance claim from unit counts. Test tools do not get Task
or production authority from being probes. Raw logs/audio/private configuration
remain in ignored local evidence. Maintain the user's pinned AgentCore wheel
choice in the isolated Demo and gpt-realtime-2.1 / 1.25 baseline for comparisons.

## Evidence routing

Initial human failures are preserved in private
`logs/demo-20260909/failure-web_1a08581b5cc/INVESTIGATION.md` and
`logs/demo-20260909/failure-web_1a085c08011/INVESTIGATION.md`.
New probes and exact commands/results belong in this record at module closure;
STATUS owns live progress and missing acceptance.

## Executor worktree fidelity — module implementation verified

The checkout's Git conversion and index stat cache both caused the mismatch.
Applying patches or merely restoring LF working bytes left checkout-derived
CRLF sizes in the index: `status --porcelain=v2` reported changes even when
`diff` was empty and `hash-object` matched the index blob. `update-index --refresh`
did not correct that distinction. The seed now copies the admitted index (with
split-index backing data), retires replaced checkout paths, restores actual
Git-visible source bytes, verifies both strict fingerprints, then stages only
the owned attempt baseline. Source bytes/index and global Git settings remain
unchanged. This retains the existing authorized result-application boundary.

Verification: the executor module passed 152 tests with 2 existing skips in
659.44 s. Independent review found a path ordering issue for directory/file
replacement and Windows case-only rename. Both were reproduced and fixed;
9 affected checks then passed in 40.68 s, including six attribute/split-index
combinations and existing result-relocation/autocrlf apply/restart checks. The
reviewer confirmed the finding resolved, with no additional material finding.
The expanded matrix also covers staged plus unstaged changes, intent-to-add,
untracked/deleted files, mixed line endings and binary bytes. Scoped diff check
passed. Private commands/results are in `logs/demo-20260909/repair-probes/`.
Real Agent Task creation/application on the deployed Demo is still pending.
