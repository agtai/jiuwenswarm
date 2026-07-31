# Slack Digest Output Format

Write for fast scanning using Slack-native mrkdwn. Use `*bold*`, `<url|label>` links, short section labels, and bullet characters. Do not emit Markdown headings (`#` or `##`), Markdown links (`[label](url)`), or tables. Omit empty sections.

## Header

Start with:

```text
*Channel digest - <requested period>*
_Window:_ <cutoff through snapshot in UTC or the user's timezone>
_Returned:_ <roots> (<context-only roots> context), <replies>, <threads with returned replies>
```

If the scan is incomplete, put this directly after the title:

```text
*Partial coverage:* <specific limit or failure and its likely impact>
```

## Body

Use at most these section labels:

1. `*In brief*` - 2-3 sentences with the most consequential developments.
2. `*Decisions and direction*` - decisions and rationale.
3. `*Technical findings*` - evidence-backed discoveries or corrections.
4. `*Blockers and risks*` - unresolved problems and impact.
5. `*Actions*` - owner, next step, and timing when known.
6. `*Useful resources*` - only links with reusable value.
7. `*Open questions*` - unresolved discussion worth revisiting.

Use at most 10 substantive bullets. Start each with `*Fact:*`, `*Inference:*`, or `*Recommendation:*`. Keep related messages together as one development, avoid repeating the same point after `*In brief*`, and add compact Slack-native source links, for example:

```text
• *Fact:* The team selected option B because it reduced migration risk. <https://slack.example/permalink|source>
• *Inference (medium confidence):* Ownership remains unclear because no assignee or follow-up date appears in the thread. <https://slack.example/permalink|source>
• *Recommendation:* Assign an owner and decision deadline before implementation begins. <https://slack.example/permalink|source>
```

When a substantive bot-authored analysis is necessary context, identify it as bot-generated and do not present it as independent confirmation. Exclude acknowledgement messages, progress narration, and old digests by default.

End with a one-line note when exclusions or incomplete coverage materially affect interpretation. Do not append a raw transcript.
