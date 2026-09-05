---
name: project-maintainer
description: Maintain or audit .doc_project_maintainer project maps, or consult them when the user asks to use Project Maintainer as context.
license: Apache-2.0
---

# Project Maintainer

Use `.doc_project_maintainer/` as an indexed project map. Match the work to the
requested deliverable; consulting the map does not authorize creating or
refreshing the whole artifact.

## Choose the route

| Request | Work and reading |
|---|---|
| Consult existing project context | Locate the repository and artifact; use `INDEX.md` or `manifest.yaml` to find the relevant module, directory, flow or symbol. Read linked detail only when its summary is insufficient. |
| Create, update or summarize the artifact | Read [maintenance-workflows.md](references/maintenance-workflows.md). Load [artifact-structure.md](references/artifact-structure.md) for naming/links and [templates.md](references/templates.md) for the records being authored. |
| Complete repository coverage | Read the coverage section of [maintenance-workflows.md](references/maintenance-workflows.md) and the inventory/coverage sections of [code-symbol-docs.md](references/code-symbol-docs.md). |
| Record a symbol health audit or refresh audit trust | Read the audit sections of [code-symbol-docs.md](references/code-symbol-docs.md). Controlled promotion and evidence rules apply only to this requested audit scope. |
| Generate an audit dashboard | Read the report section of [maintenance-workflows.md](references/maintenance-workflows.md). |

For context-only use, if the artifact is missing, incomplete or stale, inspect
source directly and state the gap where relevant. Continue the requested work;
do not pause to ask whether to initialize the artifact. Do not create signing
keys, run audit promotion or repair unrelated documentation in this route.

## Scope and evidence

- User intent and repository authorities define intended behavior. Source, Git
  and tests establish what is implemented. Record disagreements rather than
  rewriting accepted design as though the current code were the goal.
- For a fix with requested artifact maintenance, verify the fix, then synchronize
  affected artifact slices. Unrelated pending coverage remains separate.
- Preserve source roles and audit scopes. Repository coverage includes stable
  source; default product/runtime health audit covers runtime/library symbols,
  not every test, fixture or script.
- Inventory output and generated documentation are not an audit. Only claim
  trusted audit credit after the controlled review/promotion/verification path
  succeeds. Repository-specific retired audit systems remain retired.

## Completion

Deliver the requested context, artifact slice, coverage result or audit report.
Check changed links and affected document sizes. Run full coverage checks only
for a complete-coverage claim. A scoped result can be complete while the wider
artifact remains partial; name remaining work only to the extent it affects the
request. For an audit, report evidence, trust status and exact pending scope.
