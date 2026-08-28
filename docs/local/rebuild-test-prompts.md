# Test prompts for the next rebuild

Ways to trigger each change deliberately, rather than waiting to meet it. Paired
with `rebuild-validation-checklist.md`, which says what to watch; this says what
to type.

Two settings decide what is reachable at all, both read from the live config:

- **`permissions.enabled: false`** — so no permission prompt is raised by tool
  gating. **Approval button styles cannot be triggered without turning this on.**
  It was deliberately disabled so an unattended 08:00 cron would not meet an
  approval prompt with nobody awake, so turn it on for testing and decide
  separately whether it stays on.
- **`channels.slack.enable_streaming: true`** — good; a question is only emitted
  on a streamed turn, so with this off no `ask_user` prompt of any kind appears.
- `channels.slack.blockkit_tables: auto` — tables and both chart tiers work; the
  marker escalations need the hookup that ships in this build.

## Approval button styles

Needs `permissions.enabled: true`. Then any prompt that reaches a gated tool:

> Read `/etc/hosts` and tell me how many lines it has.

Look for: **Reject** rendered red (`danger`), **Allow once** green (`primary`),
the two remember-options unstyled. At most one green button.

For the language path, which is where literal matching would have failed, run a
turn under a Chinese `preferred_language` and confirm `拒绝` still renders red —
skill-evolution approval sends no `value` at all, only a label.

## Structured inputs — the seven declared names

The model must choose to use `inputs`, so ask for something a form answers:

> I want to schedule a follow-up. Ask me for the date, the time and a one-line
> note, using a structured input form rather than a list of options.

> Ask me which of these to enable, letting me pick more than one: tracing,
> profiling, verbose logging.

Look for: a datepicker, a timepicker and a text field in one message with a
submit button; and a multi-select for the second. Then check the journal for the
submitted `state.values` shape against the spec table — that is the one thing
unit tests cannot settle.

Also worth one turn: a plain options question, to confirm the existing button
path is unchanged.

> Ask me whether to proceed, with options yes and no.

## data_table, plain table, and the threshold

Above 20 data rows becomes a paginated `data_table`; below stays a plain table.

> List every file under `jiuwenswarm/gateway/cron/` as a markdown table with
> columns: file, lines, last modified. Do not summarise — one row per file.

> Give me a markdown table of just three rows: name, value, note.

Look for: the first paginated and sortable with a caption taken from the heading
above it; the second rendered whole with no pager. Click a column header on the
first — sorting is client-side and sends no interaction, which is why it needed
no handler.

Numeric sorting only applies when a whole column parses as a number, so include
a count column and check it sorts 9 before 10 rather than alphabetically.

## Charts

Basic tier, mermaid pie:

> Show me the breakdown of open, merged and closed pull requests as a mermaid
> pie chart, marked for Slack rendering.

Advanced tier, raw Block Kit in a marked fence:

> Emit a Slack `data_visualization` bar chart of these values as raw Block Kit
> in a `slack-raw` fence: R1 81, R2 13, R3 13, R4 13.

Look for: a rendered chart rather than a code block. Then the negative case,
which matters more:

> Show me the mermaid source for a pie chart of open and closed PRs, as code I
> can copy.

That must render as **source**, not as a chart — an unmarked fence is a code
fence, and the marker is what distinguishes "render this" from "show me this".

Two more the allow-list should refuse:

> Emit a raw Block Kit `section` block with a button in a `slack-raw` fence.

> Emit three `data_visualization` blocks in one message.

Expect: refused and left as source (only `data_table` and `data_visualization`
are allowed, and anything carrying an `action_id` is rejected), and the third
chart declining locally rather than being refused by the API.

## Cron status record

Not promptable — it needs a scheduled run. Arm a short test cron in a test
channel and watch three paths:

- **Placeholder → complete.** A job whose run outlasts its push time posts a
  card at `in_progress` and **edits it in place** to `complete`. The pr-tracker
  roster takes ~130 s against a 60 s wake offset, so it emits one.
- **No placeholder.** A fast job posts a terminal card directly with no
  `in_progress` phase.
- **Failure.** Point a job's `--state-file` at a directory that does not exist;
  the card should reach `error` with the reason in its body.

Watch for the card being **edited**, not followed by a second message, and for a
threaded report hanging off the placeholder's own timestamp.

## The todo validation loop

Reproducible directly, and worth doing because it has killed 230 runs since
7 August:

> Create a todo list with four steps: alpha, beta, gamma, delta. Mark alpha
> completed and beta in progress. Now, without touching beta again, mark gamma
> completed and delta in progress.

Before: rejected with `More than one task is marked as 'in_progress'`, then
retried identically until the run aborts. After: either the rejection names
`beta` and says what to do, or the update is applied and the result reports that
`beta` was moved back to `pending`.

## Per-session working directory

Not a prompt so much as a probe:

> Write a file called `probe.txt` in your current working directory containing
> the word hello, then tell me its absolute path.

Look for a path under `agent/workspace/projects/<session_id>/`, not the shared
`projects/` root. The stronger signal is passive: `slack_*` and `cron_*`
directories under `projects/` start receiving files, where 1,495 of them were
empty before.

Note that **warm sessions keep the old cwd** until their adapter is rebuilt, so
test in a new thread rather than an existing one.

## Interrupt classification backport

The bug misrouted tools taking a bare `query` argument as approval responses:

> Search your memory for anything about cron wake spacing.

Expect a normal search. Before the fix this could be read as a permission
response.

## Not triggerable by prompt

- **Transport timeout plumbing** — needs a run that exceeds the ceiling. Will
  show up on its own; watch for the friendly notice replacing the raw
  `RuntimeError` text, and for a job's own `timeout_seconds` actually applying.
- **A failed run leaving something to deliver** — needs an exception with an
  empty `str()`. Verified by unit test; in production it looks like a failure
  message arriving where previously nothing did.
- **Config keys** — `channels.slack.acknowledge_requests` ships bare; confirm it
  survives a config migration rather than being deleted, and that a deprecated
  `acknowledge_requests: false` maps to `off`.

## Explicitly NOT in this build

**Subagent progress on a task card.** The design covers it as a second consumer
of the status record, and the events needed are already in the connector's
suppression list — but it was scoped out of the implementation. There is nothing
to trigger. A prompt spawning subagents will show the ordinary reply, not a card
tracking them.
