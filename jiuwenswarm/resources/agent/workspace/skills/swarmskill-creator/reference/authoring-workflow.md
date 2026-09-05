# Authoring Swarm Skills

Select operation (CREATE, CONVERT, MODIFY) and output shape in the root skill.
Only the chosen route applies; script-only output skips role/workflow/bind files.

## Pattern and roles (Stages 0–2)

Use [pattern-selection.md](pattern-selection.md) when choosing a new team shape:
independent adversarial perspectives, parallel decomposition, specialization
pipeline or a mixture. Role counts are design heuristics, not fixed gates.
Ground the choice in the user's work rather than requiring them to explain a
failure mode already evident in their brief.

For conversion, read the existing skill and
[conversion-guide.md](conversion-guide.md). Identify natural persona, parallel
work or handoff boundaries and what the team adds; preserve original scope and
behavior while reporting the delta.

Use [role-design.md](role-design.md) and
[role.md.template](../templates/role.md.template) for each `roles/<id>.md`.
The five required sections are:

1. `Identity`, starting with a one-line motto in `> *"..."*` form.
2. `Success Criteria`, observable outcomes and focus areas.
3. `Boundary`, with explicit Forbidden and Mandatory responsibilities.
4. `Output Schema`.
5. `Inline Persona for Teammate`, a self-contained dispatch prompt.

Keep roles distinct; one role's deliverable should not substitute for another's.
Discover relevant already-available skills/tools from host metadata before
probing paths. Assign useful capabilities only: `roles[].skills` contains skills
with `SKILL.md`; `roles[].tools` contains actual CLI/MCP/tool capabilities. No
whole-machine scan or automatic installation is necessary. Record available
matches as `source: local`; empty lists are valid when nothing fits.

## Full specification (Stages 3–5)

Use the existing templates, removing template notes in generated files:

- [workflow.md.template](../templates/workflow.md.template): Overview with Mermaid,
  Detailed Steps and Acceptance Criteria. Steps define executor, input/output,
  parallel or serial ordering and what happens when an output fails. The final
  step defines the delivered result.
- [bind.md.template](../templates/bind.md.template): Resource Constraints,
  Behavioral Constraints and Failure Handling. Bound parallelism/time/tokens as
  required by the spec; cover teammate failure and input-overscale degradation.
  For debate, retain phase-scoped visibility and the communication preference
  (direct peer-to-peer, shared blackboard, Leader relay), without mandating a
  framework transport.
- [dependencies.yaml.template](../templates/dependencies.yaml.template): include
  both `skills:` and `tools:` (possibly `[]`) and match all declared role
  dependencies. Purpose text should explain what a capability contributes.
- [SKILL.md.template](../templates/SKILL.md.template): root frontmatter and
  `Workflow`, `Roles`, `Files` sections. Link details; put the Mermaid in
  `workflow.md` rather than duplicating it.

Directory name matches frontmatter `name` in kebab-case (`-swarm` is the naming
convention). Role filenames match role IDs. Preserve `version`,
`kind: swarm-skill` and required `roles` fields for the full shape.

Descriptions use concise WHAT / WHEN / NOT statements where the exclusion
prevents likely confusion. The validator's hard cap is 1024 characters; 500 is a
soft target, not a length to fill. Do not enumerate synonyms or put numerical
scope thresholds in the description. Role `purpose` has a 150-character cap;
detail belongs in its role file.

## Executable shape (Stage 3b)

For a requested script, follow
[workflow.py.template](../templates/scripts/workflow.py.template), including its
canonical constraints. Keep prompts/builders/schemas in the script. Script-only
packages have exactly `SKILL.md` plus `scripts/workflow.py`; omit or empty `roles`
and include `Workflow`/`Files` in the root.

In full-spec-plus-script mode, translate the workflow topology first and then
align failure/retry/timeout behavior with the bind contract. Do not invent an
extra hidden workflow. Use the template's actual limits on child composition and
session/budget primitives; generating a script does not authorize running it.

## Focused modification

| Change | Revisit |
|---|---|
| Role identity/boundary/schema | Affected role and consumers |
| Add/remove role | Pattern, affected roles, workflow, bind, dependencies and root |
| Workflow topology | Workflow and affected bind/script contracts |
| Resource/failure constraints | Bind and affected execution behavior |
| Dependencies | Available-capability match, dependencies and role declarations |
| Description/purpose | Root metadata and its trigger boundaries |
| Executable orchestration | Script/template constraints, root Files, and full-spec contracts if present |

## Validation and optional enrichment (Stage 6)

Run the existing validator on the complete output folder for any modification.
It checks shape, required sections, role/file/dependency consistency and script
constraints. Use [compliance-checklist.md](compliance-checklist.md) only for
applicable judgment checks, including semantic success and meaningful resource
bounds. Do not declare a partially missing branch a complete success.

Deliver the package with its actual validation result. If an identified
capability is missing, state the consequence and a concrete next action.
Community discovery/install remains optional and separately scoped by
[community-search.md](community-search.md); absence of a specialized community
skill is not automatically a failure of an otherwise capable local workflow.
