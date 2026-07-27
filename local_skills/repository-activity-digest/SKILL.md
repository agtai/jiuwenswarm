---
name: repository-activity-digest
description: >-
  Build evidence-linked GitHub project intelligence from issues, pull requests,
  reviews, commits, merges, closes, reopens, reverts, releases, and code-change
  signals. Use for scheduled repository monitoring, daily engineering
  intelligence, project-health reviews, contributor onboarding, opportunity
  discovery, or requests about activity and trends over 24-hour, 7-day, and
  30-day windows.
---

# Repository Activity Digest

Use the bundled fetcher for deterministic GitHub API access and pagination.
Treat its coverage metadata as part of the evidence; never invent missing
activity.

## Workflow

1. Determine the repository (`owner/name`), daily window, target audience, and
   state-file path.
2. Run:

   ```bash
   python scripts/fetch_repository_activity.py \
     --repo owner/name \
     --hours 24 \
     --mode updated \
     --history-days 30 \
     --detail-limit 5 \
     --state-file memory/repository-activity-owner-name.json
   ```

3. If the command fails, report the error and stop. If optional endpoints are
   incomplete, continue but carry every coverage warning into the evidence-gap
   section.
4. Read [references/report-format.md](references/report-format.md).
5. Cluster related Issue, PR, Review, Commit, CI, Merge, Close, Reopen, Revert,
   and Release records into one change narrative instead of listing duplicates.
6. Deep-read the 3-5 highest-impact clusters with available GitHub or web tools:
   inspect descriptions, relevant patches/files, review comments, maintainer
   replies, linked history, and CI. Do not call an item significant from its
   title alone.
7. Compare the exact 24-hour, 7-day, and 30-day windows. Weight maintainer
   involvement, code depth, core-module impact, discussion intensity,
   persistence, merge status, and user impact—not raw item count alone.
8. Produce the report in the user's requested language with direct evidence
   links.

## Rules

- Use `updated` for daily intelligence; use `created` only for explicitly
  creation-focused reports.
- Prefer `GITHUB_TOKEN` from the environment. Never print or persist the token.
- Keep the state file outside the Skill folder so upgrades do not erase the
  watermark.
- Mark important statements as **Fact**, **Inference**, or **Recommendation**.
- Attach a PR, Issue, Commit, Release, Discussion, or CI link to every important
  factual conclusion.
- Separate explicit missing capabilities from inferred gaps. Give each
  inference high, medium, or low confidence and state its basis.
- Do not claim absence merely because no Issue was found.
- Distinguish small fixes, docs/dependencies, ordinary features, and core
  architecture work so volume does not hide impact.
- If no new activity matches, still report trend context and coverage briefly.
- Do not present private roadmaps, user adoption, or offline decisions as known.

## Scheduled Use

Create a JiuwenSwarm cron job with `targets: slack`. Put the repository, daily
window, 30-day history, state-file path, audience, and this Skill name in the
cron description. The Slack instance must configure `default_channel_id`.
