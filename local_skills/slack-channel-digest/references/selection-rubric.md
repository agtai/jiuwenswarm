# Editorial Selection Rubric

Assess complete threads rather than isolated messages. Retain information that changes what the team knows, decides, builds, or needs to do.

## Evidence pass

For each returned thread, identify:

1. The root premise, question, or proposal.
2. Every in-window reply that changes, corrects, supports, rejects, or operationalizes it.
3. The latest supported state.
4. The most specific source message for every retained claim.

A reply is material when it reports a result, corrects a claim, replaces an approach, identifies a blocker, records an owner or next step, or supplies a supporting artifact. Merge related contributions without erasing their distinct meaning.

## What earns a place

Judge a candidate development on two questions.

**Does it change anything?** A development is worth a topic when it changes an implementation path, a decision, a delivery risk, an owner's next action, or an important shared understanding. It is worth a supporting point when it is useful to current work without being consequential on its own. It is worth nothing when it is chatter.

**How far does the change reach?** Something that affects architecture, delivery, reliability, cost, security, or a team commitment outranks something that affects one bounded workstream, which outranks context that is merely useful to know.

## Ordering

Lead with what stops work now: a live blocker, an incident, a deadline, or a decision that is holding something up. Follow with what needs a decision or a follow-up soon but is not presently blocking. Close with what only needs awareness — a completed development, a reusable resource, a result worth knowing.

Do not promote a topic merely because it is interesting. Within a band, put the wider-reaching development first.

## Editorial writing

- Use a declarative title that states the development: "Adapter work still lacks an estimate", not "Benchmark adapters".
- Say what changes, what is at risk, or what becomes possible. Do not restate the title, and do not write a literal "So what" label.
- State reported facts directly, with attribution to the person who reported them.
- Draw a conclusion across messages only when the synthesis adds something no single message says, and mark it as your reading rather than as a reported fact.
- When a topic has a concrete next step, name it, and be explicit about whether Slack records it or you are proposing it. Do not attach an invented next step to a topic that only needs awareness.
- Do not invent owners, dates, agreement, completion, or verification.
- Avoid vague buckets such as "maybe", "synergy", "worth exploring", or "FYI". A collaboration opportunity is either a concrete next step, a pending outcome to watch, or context — say which.

## Include

- Decisions and rationale.
- Findings, experiments, measurements, corrections, and reproducibility results.
- Architecture alternatives and evidence.
- Blockers, risks, changed status, and unresolved questions.
- Recorded actions with owners or dates.
- Reusable code, documents, papers, tools, and links with their practical value.

## Exclude by default

- Greetings, thanks, emoji-only reactions, and simple acknowledgements.
- Repeated announcements, quoted duplicates, and social conversation.
- Unsupported guesses that did not affect a decision or action.
- Bot acknowledgements, progress narration, and previous digests.
- Message-by-message transcripts.

## Evidence and judgment

- A Slack message proves that its author stated, reported, shared, assigned, or recorded something; it does not independently verify the underlying external claim.
- Cite the reply when evidence is in a reply and the root when it supports the whole thread.
- Preserve later corrections and uncertainty.
- Every topic needs at least one attributed fact.
- Every claim carries a link copied verbatim from the tool result. One to four sources per claim is plenty; more is a sign the claim should be split.
