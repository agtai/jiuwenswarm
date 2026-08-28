# Notes on one host

**Everything in this file is one host's behaviour, not the skill's.** It is here
because a reader on that host needs it and because the rest of the skill must not
state it as though it were universal. Nothing else in the skill depends on any of
it; on a different host, expect every answer below to be different and re-establish
each one rather than assuming it carries over.

The host described here is jiuwenswarm, with its Slack connector enabled. Where a
claim was established by observation rather than from documentation, that is said.

## Which trigger registers links

The connector fires a per-channel trigger called `url` on messages containing a
link. One `scopes` rule naming the channel configures both halves of it:
`delivery.mode` lists `url` among the triggers that wake the bot there, and
`delivery.prompt` carries the text the turn runs. That is the trigger
`--via url` records, and the override in `prompts.md` section 1 is the prompt it
runs.

Its three limits, all confirmed by observation:

- It fires **once per message**, however many links that message carries. One
  turn therefore has to register all of them, which is why `track` is given the
  raw message body rather than a list of URLs.
- It fires on **human messages only**. A link posted by a bot or an app
  integration never triggers it.
- It fires on **new messages only**. A link added by editing an existing message
  never registers.

A message that arrives while the service is down is not replayed.

## What a trigger turn carries

The connector keeps `slack_message_ts` in its own request metadata and does not
render it into the model's context. A turn started by the `url` trigger
therefore cannot supply `--slack-ts`, and a prompt that asks for it on this path gets an
invention — the observed failure was the run's own date, formatted as a
local-time clock reading, passed as if it were a message id. On this host, omit
`--slack-ts` from the registering prompt.

## When the reply is delivered, and what that means for `--commit-after`

The model's reply is sent **after the turn ends**. A run therefore cannot observe
whether its own delivery succeeded, which is the whole reason the scheduled prompt
in `prompts.md` section 3 uses `--commit-after` and the human-triggered prompt in
section 2 does not: a person watching the channel can see a failed send and
decline to commit, and a scheduled run has nobody to do that.

This is the single fact that decides which ordering a host should use. A host that
sends during the turn and reports the result back to the caller should commit late
on both paths.

## Channel history is not offered on every invocation path

A history scan of the channel is a capability the host offers, not something this
skill implements. It is offered to a turn the connector started from Slack. It is
**not** offered to a turn started by the host's own command-line `chat`
invocation, which is not a Slack turn and does not carry the connector metadata a
Slack turn does.

The failure mode matters more than the rule: the capability is simply absent, so a
reconciliation attempted from the command line returns an empty result that is
indistinguishable from an empty channel. It is a silent wrong answer, not an
error. Reconciliation on this host must be run from Slack.

## Rendering

- Markdown tables render natively once Block Kit tables are enabled on the
  connector (`blockkit_tables: auto`). Without that setting, a table posted as
  Markdown is not converted and reaches the channel as raw pipe characters.
- The connector recognises `<!-- jiuwenswarm:slack-thread-details -->`. The text
  above the first marker is posted to the channel and the text after each marker
  is posted as a reply in that message's thread, in order. A host that does not
  recognise the marker renders it as an HTML comment, and the report reads as one
  message — which is a graceful degradation, not a failure.
- **Every marker is a boundary, so a report is a root and as many replies as it
  wrote markers.** An older connector split on the first marker only and stripped
  the rest; against one of those the report is still correct, as a root and a
  single reply carrying the same sections in the same order. Confirm which
  behaviour is deployed by counting the messages, not by reading the version.
- A piece that renders to nothing is dropped rather than posted as a blank
  reply. **Do not treat that as the report's guard.** It is this connector's
  behaviour, it is not universal, and the report writes no boundary it has no
  content for — so an empty piece arriving here at all is a report bug, and this
  line is what would hide it.
- Each piece is chunked on its own against the connector's text ceiling, which is
  well above any report this skill produces, so one piece is one message.
- Slack's own Block Kit limits apply to each rendered message: 100 rows, 20
  columns, 50 blocks, and 10 000 table characters. The row limit is per table;
  the block and character budgets are counted across the whole message. These are
  Slack's, not the connector's, and apply wherever Block Kit does.
- Because those budgets are per message, every boundary is another budget. The
  report spends its markers accordingly: one to keep the prose out of the
  tables' budget, and one to keep the roster out of the delta tables'. The
  second matters more, because the roster is the section that grows on its own
  and so reaches a limit first; sharing a message with it, the delta tables lost
  their formatting to its length. Measured on real rows, splitting the two took
  the combined ceiling from under half the single-table ceiling back up to it.
- The row cap is per table and no arrangement of markers lifts it. Only the
  character and block budgets are bought back by a boundary. Past a single
  table's own budget the remedy is fewer rows in that table, which is what the
  roster's paging does.
- **A relayed report is only as faithful as the relay, and on a long roster that
  is the limit that binds first.** Where something reads the rendered report and
  posts it on, the markers and the page headings are content it can tidy.
  Observed on a paged roster of about a hundred rows: the relay reproduced every
  row but dropped one page heading and the marker above it, which merged two
  pages into a single table over the row cap and sent the whole message as raw
  pipe characters — the exact failure the paging exists to prevent,
  reintroduced downstream of a renderer that was correct.
- Diagnosing that one: the symptom is `mode=post` on a message that should have
  rendered. Count the `*Roster (n/m)*` headings that arrived against the pages
  the script produced, and compare the delivered length against the script's
  own. Near-equal length with a heading missing is a relay that reassembled the
  report, not a renderer that mis-paged it.
- A message that breaches any of them is not truncated: the connector posts it as
  plain text instead, so on Slack every table in that message arrives as raw pipe
  characters. Nothing is lost but the formatting, and the log line for the chunk
  reads `mode=post` where a rendered one reads `mode=post+blocks`.
- Observed once a message degrades: Slack itself breaks a long plain-text message
  into several, at roughly four thousand characters, and the connector logs the
  post as one chunk because that is what it sent. A rendered message is not
  affected — its text field is only the fallback. So the visible cost of a breach
  is larger than "the table lost its formatting": one clean table message becomes
  several messages of raw pipe characters, cut mid-table.

## Where the store lives

Under the workspace the host manages, named by the prompts:

```
$JIUWENSWARM_DATA_DIR/agent/workspace/state/skills/pr-tracker/<channel-id>.jsonl
```

Two host properties make that the right place rather than the script's XDG
default. The sandbox grants file access to a fixed set of roots — the workspace,
the project root, the working directory and the installed skill directories — so
a store in a sibling directory outside the workspace works while sandboxing is off
and stops working the day it is switched on. And the backup covers the host's own
data directory, not `~/.local/state`.

## Skill installation

Installed copies under the workspace are replaced wholesale from a source of
record. Anything written inside the skill directory is lost on the next install,
which is why `--state-file` refuses a path there.

## Where per-run working files go

Not in the skill directory, for the reason just given. Not in a `mktemp -d`
either, and that is the part worth stating, because it is the obvious answer and
it fails here twice over.

- **Each bash call is a fresh shell.** A directory made by `mktemp -d` in one
  command is unrecoverable in the next: the variable holding it is gone, and the
  name was random, so nothing can work it out again. That alone breaks a report,
  because the file is written by one command, checked by the next and read by the
  third.
- **The working directory is shared, not per-session.** Runs on this host start
  in one flat directory rather than the per-session one the arrangement implies,
  so a file left there by a run that died is found by an unrelated later run and
  taken for its own. A failed run is precisely the one that leaves files behind,
  because it never reaches a cleanup step.

So `report` derives its scratch directory from the store path — `<store>.run`,
beside the ledger, in a directory a skill upgrade does not touch — empties it
when it starts rather than when it ends, and prints the path of what it wrote
there. Every later step in the run re-derives or reuses that path instead of
being handed one.

## Merge gate on the repositories tracked here

The paired repositories tracked on this host do not use GitHub's merge button;
the gate is an approval on the GitCode side. GitHub consequently reports
`mergeStateStatus: BLOCKED` for every open pull request forever, which is why the
report treats that field as a constant footnote rather than as news.
