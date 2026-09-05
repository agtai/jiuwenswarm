# Community dependencies

Use when community discovery is requested or an actual capability gap needs a
candidate. Creating a functional Swarm Skill does not require searching registries
or asking the user about enrichment. Do not confuse a preferred helper with a
missing capability.

## Find candidates

Derive focused queries from the affected role's purpose, success criteria and
output format. Prefer the host's available search mechanisms. Existing options
include `npx skills find '<query>'` and `skillnet search '<query>' --mode vector`;
verify availability before use. English queries help English-indexed registries.
Try another query or source when the first result is insufficient; there is no
mandatory number of variants, CLIs, results or downloads.

Read candidate metadata/root first and only the resources needed to assess fit.
Do not install a candidate merely to inspect it. A specialized skill is useful
when it supplies a capability the role cannot adequately achieve with its
existing tools/instructions; generic utilities are not automatically inadequate.

## Evaluate fit and trust

- Verify the capability against the role's actual output and constraints.
- Review origin, maintenance, compatibility, declared actions and required data
  access. Popularity alone is not a safety or correctness guarantee.
- Preserve applicable registry/security checks. A critical rating or suspicious
  behavior requires explicit user direction; do not present it as safe.
- Check current dependencies and version support instead of equating a recent
  timestamp with correctness. Explain unverified or stale claims.
- Avoid redundant dependencies and overlapping roles. Prefer a suitable existing
  local capability; keep optional helpers optional.

Summarize relevant candidates, evidence, remaining concerns and the proposed
installation target. Discovery is not authorization to install, replace or
publish. If installation has already been explicitly authorized for that target,
continue without asking again; otherwise obtain the required direction before
that mutation. Host and repository security rules remain controlling.

After an authorized install, update matching skill/tool declarations and
`dependencies.yaml` with the actual source, then rerun
`python <skill-dir>/scripts/validate_swarmskill.py <output-dir>`.
Report actual installed files and validation. If no candidate is suitable,
explain the gap; a functioning package can still be delivered without enrichment.

## Existing candidate quality gates

For this conditional community-install route, retain these candidate gates. They do not replace content review or confer installation authority.

### Gate 1: Install Count

| Threshold | Action |
|---|---|
| ≥ 10K installs | **Strong signal** — still review the actual content |
| 1K–10K installs | **Moderate** — acceptable if source is reputable |
| 100–1K installs | **Weak** — only if no better alternative exists AND source passes Gate 2 |
| < 100 installs | **Reject** — too risky for a dependency |

Where to check: skills.sh leaderboard, LLMBase skill page, `npx skills` output (shows install count).

### Gate 2: Source Reputation

Prefer skills from known, maintained sources:

**Trusted sources** (non-exhaustive):
- `vercel-labs/agent-skills` — React, Next.js, web design
- `anthropics/skills` — frontend design, document processing (pdf, pptx)
- `microsoft/azure-skills` — cloud, infrastructure
- `firebase/agent-skills` — Firebase ecosystem
- `supabase/agent-skills` — database, backend
- `coreyhaines31/marketingskills` — marketing, SEO, copywriting
- `remotion-dev/skills` — video generation
- `google-labs-code/stitch-skills` — Google design system
- `expo/skills`, `flutter/skills` — mobile development

**Caution signals**:
- Unknown author with no GitHub profile
- Repository with < 50 stars
- No commits in the last 6 months
- Skill description is vague or generic

### Gate 3: Security Rating

Check the security rating on LLMBase or skills.sh:

| Rating | Action |
|---|---|
| **Safe** | Eligible for installation within existing user/host authorization |
| **Medium** | Acceptable — review the skill content before installing |
| **Critical** | Do NOT install unless explicitly approved by the user. Flag in the enrichment summary |

### Gate 4: Freshness

Check the source repository's last commit date. Skills based on framework best practices become stale quickly.

| Last updated | Action |
|---|---|
| Within 3 months | Current |
| 3–6 months | Acceptable |
| > 6 months | Flag as potentially stale — verify the content still applies |
