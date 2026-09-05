---
name: skill-creator
description: Create, revise or evaluate a single-agent skill when the user requests a reusable skill or an improvement to an existing one.
description_cn: 创建、修改和评估单智能体技能。
---

# Skill Creator

Deliver a reusable skill that preserves the user's intent and improves the
agent's decisions. Use the current request and conversation to establish the
trigger, output and constraints; ask only for information that materially changes
the result. Existing design choices and authorization need no second approval.

## Choose the work

| Request | Guidance |
|---|---|
| Create or revise instructions/resources | Read [authoring.md](references/authoring.md). Preserve the existing skill name when revising. |
| Evaluate behavior or compare versions | Read [evaluation.md](references/evaluation.md), then the applicable schema/agent reference it identifies. |
| Measure description triggering | Read [description-evaluation.md](references/description-evaluation.md); its bundled CLI is Claude-specific. |
| Create a multi-role Swarm Skill | Use the available `swarmskill-creator` skill instead. |

A narrow edit does not require community downloads, a structure-approval meeting
or a full benchmark loop. Use supporting resources where they save repeated work
or protect a fragile contract; a small self-contained skill is valid.

## Completion

Create or revise the files in the requested location, check frontmatter and
references, and verify the changed behavior at an appropriate scope. Use
`scripts/quick_validate.py <skill-dir>` when its dependencies and supported
frontmatter match the target host. A structural pass is not behavioral evidence.
Do not rename a working skill merely to describe a new revision.

Deliver the skill location, changes, meaningful validation and remaining limits.
When a packaged `.skill` artifact is requested, use
`scripts/package_skill.py <skill-dir>` and inspect its result. Authoring or
packaging alone does not authorize runtime installation, overwriting another
skill, external publication, or paid provider evaluations. Continue all already
authorized work before reporting an exact missing prerequisite.
