# Repository intelligence method and report format

## Analysis method

Use three exact UTC windows:

- **24 hours:** concrete new or updated activity for this report.
- **7 days:** short-term acceleration, stability, or decline.
- **30 days:** durable direction, long-running blockers, and project health.

Merge records that concern the same change into one cluster. An Issue, its PR,
reviews, commits, CI result, merge, close, reopen, or revert are evidence for one
narrative, not unrelated list entries.

Classify clusters into stable themes such as orchestration, multi-agent
coordination, memory, session/task continuity, planning, tools/Skills, human
intervention, permissions/security, channels, voice/real-time interaction,
observability, evaluation, reliability, performance/scheduling, API/SDK,
documentation, and deployment. Add a new theme only when the evidence requires
it.

Judge importance using:

- maintainer involvement and decision authority;
- depth and location of code changes;
- user or architectural impact;
- review intensity and unresolved disagreement;
- persistence across windows;
- merge/revert/reopen status;
- CI, test, compatibility, and ownership evidence.

Do not infer importance from count alone.

## Missing-capability classification

Use three groups:

1. **Explicitly missing:** direct evidence from repeated requests, maintainer
   statements, roadmap items, recurring workarounds, or an unsupported API.
2. **Inferred missing:** architectural or discussion evidence suggests a gap.
   Label confidence high, medium, or low and state the evidence.
3. **Evidence insufficient:** plausible gap that public repository evidence
   cannot establish.

Never infer that a capability is absent only because no Issue mentions it.

## Opportunity classification

Classify team opportunities as:

1. immediately actionable ordinary engineering;
2. important systems engineering;
3. long-term research-worthy open problems;
4. low-value work the team should avoid.

Research value requires more than missing code. Look for repeated user demand,
structural limitations, unclear abstractions, conflicting objectives,
benchmarkable outcomes, cross-system generality, or a problem that ordinary
engineering scale alone cannot settle.

## Required output

### 1. Executive Summary

Use 3-5 sentences covering the most important 24-hour change, current project
direction, clearest blocker, and best team opportunity.

### 2. Significant Changes

Report only 3-5 high-impact change clusters. For each, state impact and cite
direct links. Label facts and any inference separately.

### 3. Trend Signals

For non-Slack destinations, use a compact table:

| Theme | 24-hour change | 7-day trend | 30-day judgment | Evidence | Confidence |
| --- | --- | --- | --- | --- | --- |

For Slack, use the bullet format in `slack-report-format.md`; Slack does not
render GitHub Markdown tables.

Name principal participants and unresolved disagreement when relevant.

### 4. Project Health

Cover only supported signals:

- opened vs. closed Issues;
- first-review and merge-cycle samples;
- stale Issues/PRs and Issue-to-PR conversion signals;
- reopen/revert activity;
- CI, test, conflict, and external-contribution friction;
- contributor concentration and frequently changed modules;
- code/test/documentation consistency and visible technical debt.

State metric coverage and sample size. Do not turn partial API samples into
project-wide facts.

### 5. Blockers and Risks

Prioritize review blocks, design conflicts, CI/test failures, missing owners,
repeated reverts, collaboration risk, compatibility, architecture, and debt.

### 6. Missing Capabilities

Separate explicitly missing, inferred missing, and evidence-insufficient
possibilities. Include confidence and basis for every inference.

### 7. Opportunities for Our Team

For non-Slack destinations:

| Opportunity | User value | Research value | Engineering effort | Risk | Team fit | Recommendation |
| --- | --- | --- | --- | --- | --- | --- |

For Slack, use the compact numbered format in `slack-report-format.md`.

Explain whether each is a short contribution, systems project, research
direction, or something to avoid.

### 8. Recommended Actions

Give no more than five assignable actions: a PR/Issue to follow, a maintainer to
contact, a suitable first contribution, a benchmark to design, a direction to
defer, or an internal owner to assign.

### 9. Evidence Gaps

State what is known, unknown, what evidence is needed, and whether further
investigation is worthwhile. Common gaps include private meetings, internal
roadmaps, Slack discussions, real usage data, commercial priorities, unannounced
designs, post-release outcomes, and users who stopped reporting problems.

## Evidence rules

- Prefix important conclusions with **Fact**, **Inference**, or
  **Recommendation**.
- Link every important fact to a PR, Issue, Commit, Release, Discussion, or CI
  result.
- Read descriptions, patches, reviews, maintainer replies, linked history, and
  CI for significant clusters.
- Preserve uncertainty when coverage metadata or primary evidence is missing.
- Avoid a title recap and avoid repeating low-value fields.
- Return only the final report; omit tool-use and analysis-process narration.
