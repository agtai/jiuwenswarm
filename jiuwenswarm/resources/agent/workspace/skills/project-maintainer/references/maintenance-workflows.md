# Project-map delivery workflows

Use only the section matching the requested artifact work. Context-only lookup
uses the root skill and does not enter these write workflows.

## Create or update a slice

Identify the target repository and `.doc_project_maintainer/`. For an existing
artifact, read its index/manifest and the affected records. Consult the build
plan or coverage map only when needed to judge those records' freshness.

Use [artifact-structure.md](artifact-structure.md) for paths and links and the
relevant section of [templates.md](templates.md) when authoring records.
Initialize only the requested artifact surfaces. Modules describe capabilities,
directories locate evidence, flows explain boundary-crossing behavior, and code
symbol cards describe executable details.

For affected flows, trace the actual producer, data contract/transport, storage,
consumer and user-visible result. Record failure, replay, ordering, identity and
finalization behavior where it affects the result. Missing links remain explicit;
do not document every helper merely because it is reachable.

For a verified code change with requested maintenance, update affected module,
directory, flow and symbol records, their manifest/index links and pending-slice
entries. Create a change record for a meaningful source/contract/knowledge-model
decision, not routine artifact synchronization. Git history summaries use
relevant `git log --stat`, `git log -- <path>` and `git show --name-status` evidence;
mark inferred rationale as inferred.

Check changed local links and document sizes.
`python <skill-dir>/scripts/check_doc_sizes.py <repo-root>/.doc_project_maintainer`
reports the whole artifact: repair oversized
files in the requested slice, and record unrelated results without expanding a
bounded edit. Existing source-role/audit fields and historical evidence remain
intact.

## Complete repository coverage

This section applies when complete coverage or whole-artifact currency is the
requested deliverable. A general repository question does not imply this mode.

1. Inspect the index, manifest, build plan, coverage and audit maps to locate
   incomplete/stale slices. Inventory stable tracked source and disposition
   candidate/untracked paths as source, local/generated state or out of scope.
2. Use [code-symbol-docs.md](code-symbol-docs.md) for inventory and required file,
   class, function and method cards. Run the existing inventory entrypoint:

   ```text
   python <skill-dir>/scripts/inventory_symbols.py <repo-root> --output <repo-root>/.doc_project_maintainer/project/source-symbol-inventory.json --coverage-map-output <repo-root>/.doc_project_maintainer/project/coverage-map.json --audit-map-output <repo-root>/.doc_project_maintainer/project/symbol-audit-map.json --verify-docs
   ```

3. Review `directory_summary`, extractor confidence and source roles. Optional
   ctags is an enhancement; use the built-in fallback and leave uncertain parser
   results pending until reviewed. Use hashes to focus on changed symbols.
4. Work in coherent non-overlapping slices and integrate index/manifest links
   centrally. Parallel agents may help independent slices when available and
   authorized; absence of parallelism does not block documentation work.
5. Reconcile all required directory, flow and symbol coverage against the maps.
   Each gap must be completed or explicitly excluded with a reason before the
   requested coverage can be called current.

Keep documentation coverage and health-audit closure separate. A populated card
or clean inventory run never grants trusted audit credit. If the user also asks
for health-audit closure, follow the controlled audit sections of
[code-symbol-docs.md](code-symbol-docs.md), including per-symbol evidence and
promotion. A missing required audit keeps that audit scope partial without
misrepresenting completed documentation.

Report coverage evidence, applicable exclusions and exact pending slices in
`project/build-plan.md`. Continue actionable work within the requested scope;
do not substitute a list of missing items for a complete-coverage deliverable.

## Audit dashboard

For a requested visual audit report, check that `project/coverage-map.json` and
`project/symbol-audit-map.json` describe the requested source/scope. If stale,
report that limitation or refresh within the authorized audit scope. Read the
controlled-audit section of [code-symbol-docs.md](code-symbol-docs.md) before
refreshing trust; this is not an ordinary context preflight.

```text
python <skill-dir>/scripts/render_audit_report.py <repo-root>
```

The script refreshes trust through `audit_integrity.py report` by default.
`--skip-integrity-refresh` produces a presentation of existing data; state that
limitation if used. Deliver `project/audit-report.html` with its source/trust
status. The JSON maps and evidence remain authoritative. If maps/trust change
later in the task, regenerate or explicitly state the HTML is stale.
