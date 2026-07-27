# Slack report format

Use this format only when the report is delivered to Slack.

## Output contract

- Return only the final report. Never expose tool calls, search narration,
  intermediate reasoning, or phrases such as "Let me" and "I will now".
- Use Slack `mrkdwn`, not GitHub Markdown:
  - use `*bold*`, never `**bold**`;
  - use bullets and short numbered lists, never tables;
  - use `<https://example.com/item|Issue #123>` links, never
    `[Issue #123](https://example.com/item)`;
  - do not use `#` or `##` headings.
- Keep the channel brief below 3,500 characters.
- Limit Significant Changes, Risks, and Recommended Actions to five items each.
- Do not print long contributor, file, Issue, or PR lists. Summarize the signal
  and link the strongest evidence.
- Put one blank line between sections and keep paragraphs to three lines or
  fewer.

## Channel brief

Start with:

```text
*JiuwenSwarm Daily Intelligence — YYYY-MM-DD*
_Repository: owner/name · Windows: 24h / 7d / 30d · Coverage: complete|partial_

*TL;DR*
• 🔴 ...
• 🟠 ...
• 🟢 ...

*Significant Changes*
1. *Short title*
   [FACT] One-sentence finding and impact.
   Evidence: <https://...|PR #123>

*Risks and Blockers*
• 🔴 *Critical* — ...

*Recommended Actions*
1. [RECOMMENDATION] ...
```

Use at most three TL;DR bullets. Order findings by impact, not event count.

Immediately after the channel brief, emit this marker on its own line:

```text
<!-- jiuwenswarm:slack-thread-details -->
```

The Slack channel removes the marker, posts the brief as a top-level message,
and posts everything after it in that brief's thread.

## Thread detail

Continue with these compact sections:

```text
*Trend Signals*
• *Theme* — ↑ Rising | → Stable | ↓ Cooling
  24h: ...
  7d: ...
  30d: ...
  Evidence: <https://...|#123> · Confidence: High

*Project Health*
• *Issue flow* — ...
  Coverage: ...

*Missing Capabilities*
• *Explicit* — ...
• *Inferred (Medium confidence)* — ...
• *Evidence insufficient* — ...

*Opportunities for Our Team*
1. *Opportunity* — Systems engineering
   User value: High · Research value: Medium · Effort: Medium · Risk: Low
   Recommendation: ...

*Evidence Gaps*
• Known: ...
• Unknown: ...
• Needed: ...
```

Omit unsupported sections rather than padding them. Keep `[FACT]`,
`[INFERENCE]`, and `[RECOMMENDATION]` labels on important conclusions. Preserve
direct evidence links and coverage limitations.
