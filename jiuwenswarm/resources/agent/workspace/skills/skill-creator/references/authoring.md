# Authoring a skill

## Intent and scope

Extract the desired capability, realistic triggering context, input/output and
constraints from the request. Reuse examples and corrections already supplied.
Ask only when an unresolved choice would materially change the skill; otherwise
state a reasonable assumption and create the reviewable result.

For an existing skill, inspect the root and only the referenced resources that
matter to the change. Preserve its identity, supported metadata, script/tool
interfaces and user choices. Do not initialize a replacement package from
scratch just to make a small revision.

## Structure

`SKILL.md` starts with YAML frontmatter containing `name` and `description`,
followed by guidance. The description states the actual capability and when it
applies. Add an exclusion only for likely confusion. Avoid synonym catalogs,
workflow recipes and broad “whenever” triggers.

The body carries essential decision boundaries, expected result and completion
criteria. Move substantial mode-specific procedures into references with clear
“when to read” links. Do not load every reference by default or prescribe a
particular file/line count as a substitute for relevance.

Add resources when they have a concrete purpose:

- `scripts/`: deterministic or repeatedly reused operations.
- `references/`: conditional domain knowledge, schemas or procedures.
- `assets/`: templates or materials used in the output.
- `agents/`: distinct delegated roles when the target workflow needs them.

Do not create unused scaffolding. Prefer scripts already supplied by the skill
or host over reimplementing their contracts. Test new/changed executable code;
unchanged code need not be rerun solely because prose moved.

## Instructions

Assume the agent can reason. Explain the desired outcome and non-obvious failure
boundaries; use exact sequences only where order protects correctness or
permissions. Preserve scope, truthfulness, provenance, destructive-action and
external-authorization constraints. A skill must not silently create permission
for account changes, private-data disclosure or deployment.

Use examples that clarify ambiguity. Do not turn one failure, host quirk or
preferred template into a universal recipe. Include what completion proves and
what remains unverified; for long tasks, continue to the deliverable within
existing authority instead of stopping after setup or a plan.

## Optional reference discovery

When unfamiliar domain behavior or a reusable implementation warrants it,
inspect a relevant existing skill. Search available tools/registries with a
focused capability query, then read only the matching root/resources. Do not
install references just to inspect them, and do not use popularity as evidence of
correctness or safety. Keep any borrowed files in an owned temporary area and
remove only those files when finished. Network searches, downloads and execution
remain subject to the host and user authorization.

## Verification and delivery

Check that required frontmatter parses, the name matches the existing package,
new links resolve, referenced scripts/assets exist and examples use actual tool
interfaces. Choose behavioral checks from the change: a path correction needs a
path/command check; a routing change needs positive and nearby negative requests;
a workflow change needs the relevant end-to-end outcome and failure boundary.

For performance claims, use [evaluation.md](evaluation.md). For a description
benchmark, use [description-evaluation.md](description-evaluation.md). Without
such a run, report the structural/qualitative evidence honestly rather than
claiming measured improvement. Deliver existing authorized work without forcing
another user-review cycle; incorporate feedback when it arrives.
