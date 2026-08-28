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

## What each section carries

The renderer owns the layout: which sections appear, in what order, under what
headings, and where the brief ends and the detail begins. What follows is what
belongs *in* each one — the judgement the findings carry. Section names below are
the findings keys.

### `tldr`

At most three bullets, ordered by impact and not by event count: the most
important change in the window, the clearest blocker, and the direction the
project is moving. Three sentences that a reader who stops there is not misled by.

### `significant_changes`

Three to five high-impact change clusters, never more. For each, state impact and
cite direct links. A fact and an inference drawn from it are separate entries
with separate labels.

Leave it empty only when the run measured a completely quiet window — every count
zero — and never as a way past a render that will not pass. On a window with any
activity in it there is always a truthful entry to write, and the renderer refuses
an empty section there rather than let one be invented.

### `trends`

One entry per theme, carrying a direction, the basis for it, evidence and a
confidence. Name principal participants and unresolved disagreement where they
are what the signal rests on.

**A trend entry states no numbers.** The counts belong to the run and are
rendered from it, once, in the activity table; a per-theme figure written here
would be arithmetic nobody performed. Say a theme is rising and show the item
that makes it so.

### `missing_capabilities`

Separate explicitly missing, inferred missing, and evidence-insufficient
possibilities. Every inference carries a confidence and states its basis.

### `opportunities`

Say whether each is a short contribution, a systems project, a research
direction, or something to avoid, and grade user value, research value, effort
and risk.

### `actions`

No more than five assignable actions: a PR or Issue to follow, a maintainer to
contact, a suitable first contribution, a benchmark to design, a direction to
defer, or an internal owner to assign.

### `evidence_gaps`

What is known, what is unknown, what evidence is needed, and whether further
investigation is worthwhile. Common gaps include private meetings, internal
roadmaps, chat discussions, real usage data, commercial priorities, unannounced
designs, post-release outcomes, and users who stopped reporting problems.

The run's own limits — coverage warnings, truncated lists, items active in the
window that the deep-read sample was too small to inspect, a window widened to
catch up an unreported one — are appended by the renderer and are not yours to
supply or to leave out.

### Project health

The activity table is rendered from the run. Where a wider window's endpoint
stopped short of the history boundary, its cells read `n/a` rather than repeating
the daily figure: a truncated seven-day count equals its twenty-four-hour count
exactly, which does not read as missing data — it reads as a week in which
nothing else happened. Do not restate the table's numbers in prose, and do not
turn a partial API sample into a project-wide fact.

## Source text in another language

A repository's Issue titles, PR titles, commit subjects, and comments are
written in whatever language its contributors use, and that is frequently not
the report's output language. Every one of those fields reaches the report
through the fetcher verbatim, so pasting one into a finding produces a report
that is mostly in the output language with untranslated fragments embedded in
it — unreadable at exactly the points that carry the findings.

**Render every piece of source text in the output language, and carry the
original alongside it in parentheses.**

```text
[FACT] Cancelling a task leaves it running in the background
       (原文：点击取消任务后，后台还在执行)
Evidence: <https://github.com/owner/name/issues/1403|#1403>
```

### The output language leads; the original follows in parentheses

This holds everywhere — titles, findings, and quoted comments alike. Three
reasons, in order of weight:

1. The report is scanned top to bottom by a reader deciding what deserves their
   attention. A line whose first words are unreadable to them costs that
   decision, and it is the finding itself — the TL;DR bullet, the `[FACT]`
   line — that this happens to.
2. One order is one rule. Leading with the original for quotations and with the
   translation for titles requires deciding, per line, which of the two a piece
   of text is; that judgement is unreliable and the check in
   `scripts/check_report_language.py` cannot make it at all. A single order is
   mechanically enforceable, and this skill's guarantees are worth what can be
   enforced.
3. Nothing is lost by the ordering. The original is present verbatim either
   way; only the reading order differs.

### Why the original is carried at all

Not so the item can be found again — the URL is the identifier, every item
carries one, and a search on the title is not how anyone locates it. The
original is carried so a reader can **verify** the rendering: the link proves
where an item came from, the original text proves what it said. A translated
title with no original asks the reader to trust a paraphrase of the one thing
they might have wanted to read for themselves.

That reason also says when the original may be dropped: when there is nothing to
verify. Text that was already in the output language needs no parenthetical, and
neither does a name (below).

For a quoted comment, quote the original inside the parentheses and mark it as
the source's own words, so it stays unambiguous which wording is the source's
and which is this report's:

```text
[FACT] The maintainer called the migration "not ready for dev-stable"
       (original: "还没准备好合入 dev-stable")
```

Never present a rendering as a quotation. Quotation marks in the output-language
half belong only around words the source actually used in that language.

### Names are not translated

Organisations, products, repositories, branches, components, and people keep
their names.

- Use the entity's **own Latin-script name** whenever it has one. Most projects
  and companies in this material publish under one, and it is far more
  recognisable than any transliteration of the native form.
- **Transliterate** only when no such name exists, and carry the original in
  parentheses on first mention.
- **Never** translate a name into its literal meaning. A product named for a
  word meaning "nine texts" is not the "Nine Texts" product.

### The check is a floor, not a certificate

`scripts/check_report_language.py` compares writing systems, so it catches
source text in a different script and nothing else. A different language in the
same script passes it, and so does a rendering that is wrong. Passing means the
reader was given both halves; it does not mean the report is right. Apply the
rule while writing, and treat the check as the thing that catches the line where
you did not.

## Evidence rules

- Prefix important conclusions with **Fact**, **Inference**, or
  **Recommendation**, through the finding's `label`.
- Link every important fact to a PR, Issue, Commit, Release, Discussion, or CI
  result. The renderer requires a link on every significant change and every
  trend signal, so this one is enforced rather than only asked for.
- Read descriptions, patches, reviews, maintainer replies, linked history, and
  CI for significant clusters.
- Preserve uncertainty when coverage metadata or primary evidence is missing.
- Avoid a title recap and avoid repeating low-value fields.
- Write findings, not narration. Nothing about the run -- which command was
  invoked, what was fetched, which file was written -- belongs in a finding or in
  the reply. The reply is the report and holds nothing else; see "The reply is
  the delivery" in `SKILL.md`.
