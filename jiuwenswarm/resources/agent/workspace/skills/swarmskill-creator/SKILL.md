---
name: swarmskill-creator
description: Create, convert or modify multi-role Swarm Skills and requested SwarmFlow orchestration; use skill-creator for ordinary single-agent skills.
description_cn: 创建、转换或修改多角色 Swarm Skill 及所请求的 SwarmFlow 编排；单智能体技能使用 skill-creator。
version: "0.5"
---

# Swarm Skill Creator

Deliver the requested team skill or executable orchestration. Infer operation
and output shape from the request and existing files; ask only when ambiguity
changes the result. Do not repeat a justification interview when the user's
team boundaries, isolation need or parallel work are already clear.

## Choose the output

| Request | Files |
|---|---|
| Team/Swarm Skill specification, without executable orchestration | `SKILL.md`, `roles/`, `workflow.md`, `bind.md`, `dependencies.yaml` |
| Executable SwarmFlow orchestration, without a full team specification | `SKILL.md` plus `scripts/workflow.py` only |
| Both team specification and executable orchestration | Full specification plus `scripts/workflow.py` |

A multi-role design should provide independent perspectives, useful parallel
work or a real specialization handoff. If none fits, explain the mismatch and
recommend a single-agent skill; do not manufacture roles merely to fill a form.

## Work and reading

- **Create or convert a full specification:** read
  [authoring-workflow.md](reference/authoring-workflow.md), then only the pattern,
  role or conversion guide needed for that operation.
- **Modify:** edit affected files and cross-file references; use the impact table
  in [authoring-workflow.md](reference/authoring-workflow.md) when needed.
- **Executable script:** read the `TEMPLATE AUTHORING CONSTRAINTS` block in
  [workflow.py.template](templates/scripts/workflow.py.template). It owns supported
  primitives, schema, session, composition and budget rules. In a full spec, keep
  script topology and failure behavior consistent with `workflow.md`/`bind.md`.
- **Optional community dependencies:** only when requested or needed to resolve
  an identified capability gap, read [community-search.md](reference/community-search.md).
  A completed local skill does not need an enrichment interview.

## Completion

Run `python <skill-dir>/scripts/validate_swarmskill.py <output-dir>` for the
selected shape and resolve structural failures. Then use relevant checks from
[compliance-checklist.md](reference/compliance-checklist.md) for judgment the
validator cannot supply. Verify useful semantic outputs and truthful handling of
missing/failed branches, not just schema shape. Do not claim execution evidence
from a structural validator alone.

Deliver actual files, pattern/roles where applicable, validation and material
limits. Creating the package does not install dependencies, deploy it, execute
its business actions or authorize external publication. Continue authorized
repairs until the requested result is reviewable.
