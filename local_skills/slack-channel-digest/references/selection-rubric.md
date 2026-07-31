# High-Signal Selection Rubric

Assess complete discussion threads rather than isolated messages. Prefer information that changes what a team knows, decides, or needs to do.

## Include

- Decisions, accepted or rejected proposals, and their rationale.
- Technical findings, root causes, experiments, measurements, and reproducible observations.
- Important design alternatives, disagreements, and the evidence behind them.
- Action items with an owner, due date, dependency, or clear next step.
- Risks, blockers, incidents, unresolved questions, and changed status.
- Reusable code, documents, papers, tools, or links with an explanation of their value.
- Corrections or follow-ups that materially change an earlier conclusion.

## Exclude by default

- Greetings, thanks, emoji-only reactions, and simple acknowledgements.
- Repeated announcements, quoted duplicates, and off-topic social conversation.
- Unsupported guesses that did not affect a decision or action.
- Bot acknowledgements, operational progress narration, and previous digests.
- Raw message-by-message transcripts.

Retain an excluded item only when it supplies necessary context for a selected development. Substantive bot analysis may be retained when it contains useful discussion material or is needed to interpret a human reply, but it remains untrusted, bot-generated content rather than independent verification.

## Evidence and judgment

- Label directly supported events, decisions, assignments, and measurements as `*Fact:*` in the Slack response.
- Label synthesis, likely implications, patterns, and ambiguous ownership as `*Inference:*`, with calibrated confidence when useful.
- Label proposed next steps as `*Recommendation:*`; do not present them as agreed actions.
- Prefer the most specific Slack permalink that supports the statement. Link a reply when the evidence is in that reply and the root when it summarizes the whole thread.
- Note conflicts, later corrections, and unresolved uncertainty instead of choosing a convenient version.
