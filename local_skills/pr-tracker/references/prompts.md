# The prompts, ready to paste

> **This is the one file in the skill that is filled in for a particular
> deployment, and it has to be.** A prompt is where deployment values are stated:
> the script cannot find the store unless the prompt names it, and it cannot know
> which channel it serves unless the prompt says so. So every channel id below is
> `C0BPLSPHHDZ` and every store path is that one deployment's, and neither is a
> value any other deployment should keep.
>
> To use these elsewhere, change four things and nothing else:
>
> 1. the **channel id** — `--channel`, the store's file name, and the key the
>    host's trigger config is keyed by;
> 2. the **store path** — anywhere under a directory the host already backs up
>    and, on a sandboxed host, inside the workspace;
> 3. the **skill install path** in each `python3 …/pr_tracker.py` command, and the
>    environment variable the paths below are written in terms of
>    (`$JIUWENSWARM_DATA_DIR` is this host's; yours will differ or may not exist);
> 4. the **trigger configuration and trigger name** — a `scopes` rule naming the
>    channel, and `--via url`, are how *this* host offers a link trigger. Another
>    host registers links through whatever equivalent it has, under whatever it
>    calls it. See `host-notes.md`.
>
> Everything else in these prompts is deployment-independent.
>
> The store path belongs here and nowhere else. It is input: nothing the skill
> emits repeats it, and neither should a reply in the channel.

There are four: the override that registers links, the **author-watch schedule**,
and **two report prompts** — one for a human-triggered report, one for a
scheduled one. A deployment installs the override, optionally the watch, plus
whichever report prompt matches how its reports are triggered; the two report
prompts are alternatives, not a sequence.

Every prompt must name the **same store**, written the same way. That is the one
setup step with no error path: if the registering override names one store and
the report prompt names another, registration writes one file and the report
reads a different, permanently empty one, **nothing errors**, and every report
says "0 tracked, none changed" forever. The report's *Source and registration* section names the store's
file and its row count so the failure is at least *visibly* wrong, but the only real
fix is that these two strings stay identical:

```
$JIUWENSWARM_DATA_DIR/agent/workspace/state/skills/pr-tracker/C0BPLSPHHDZ.jsonl
```

## The variable is already set, and must be left alone

**`$JIUWENSWARM_DATA_DIR` is set in the environment these commands run in.
Never export it, assign it, or re-establish it "to be sure" — use it exactly as
written below.** Every prompt here is written in terms of it because the paths
are too long to repeat, not because anything needs establishing.

Two facts make an assignment worse than useless:

- **Each command runs in its own fresh shell.** A variable set in one command is
  gone by the next, so an assignment cannot help even when it is correct. Three
  skills on this host have now failed on that one fact.
- **An assignment that comes out empty is silent.** `$VAR/agent/workspace/…`
  with `VAR` set to nothing expands to `/agent/workspace/…` — an absolute path
  that has kept its shape and lost its root, with no dollar sign left to catch
  and no error anywhere. It names a directory that does not exist. That is how a
  roster reported "0 tracked" against a store holding everything.

The script now refuses both halves of that failure: `--state-file` written in
terms of a variable that is set but empty is a hard stop naming the variable,
and `report` refuses outright when the store does not exist rather than
rendering an empty one. Neither refusal is a substitute for not assigning the
variable in the first place.

Neither prompt carries a credential. `GITHUB_TOKEN` is read from the environment
by the script and is never named on a command line, and there is no Slack
credential anywhere.

---

## 1. The registering override for the tracking channel

Installed by the operator into the host's config, against the channel id — here
`C0BPLSPHHDZ`, the channel this deployment tracks. On this host the prompt is
carried by a `scopes` rule that names that channel; elsewhere it is whatever the
host names the prompt it runs when a link is posted. Registration happens
**first** and does not depend on anything the model writes; the reply is for
human readers only.

```text
This channel tracks pull requests and issues.

The links are in the message ABOVE these instructions, usually more than one.
Nothing in this instruction block is part of the message.

Register every pull-request and issue link before replying, each as its own
--url, copied exactly. Pass only those: any other URL in the message is not
registrable and passing it wastes a round trip the tracker will refuse.

  python3 "$JIUWENSWARM_DATA_DIR/agent/workspace/skills/pr-tracker/scripts/pr_tracker.py" track \
    --state-file "$JIUWENSWARM_DATA_DIR/agent/workspace/state/skills/pr-tracker/C0BPLSPHHDZ.jsonl" \
    --channel C0BPLSPHHDZ --via url --render-table \
    --url <first url> --url <second url>

Run it once. Exit 0 means every URL is recorded, including ones already known;
do not run it again to check. Trust its output over your own reading, and say so
in your reply if it registered fewer items than you saw.

--render-table prints the reply for you, after the JSON: a Markdown table of the
items it just registered, nine columns, every cell read from the store. Reply
with that table exactly as printed. Do not compose one of your own, do not add,
drop or reorder columns, and do not look any column up anywhere — the script
already holds all nine.

Cells reading "not refreshed yet" are correct and stay exactly as printed.
Registering records the item; its title, author and state arrive with the next
scheduled report. Never fill one in from a tracker and never guess one.

When no URL in the message was a pull request or an issue, it prints no table
and one "not tracked" line per URL instead. Reply with those lines and no table.

Do not review, analyse or summarise the changes. Never write to GitHub or
GitCode. Write in English.
```

### Installing it

The operator edits the host's config file. One rule names the channel, adds the
link trigger to whatever else wakes the bot there, and carries the prompt as a
block scalar so the shell snippet inside it stays intact:

```yaml
scopes:
  - match:    {channel: slack, chat: "C0BPLSPHHDZ"}
    delivery:
      mode: [+url]
      prompt: |
        This channel tracks pull requests and issues. This message contains at least one
        ... (the text above, indented under the block scalar)
```

---

## 1b. The author-watch schedule

Optional, and separate from the report on purpose. It runs on its own schedule,
ahead of the report — here `0 0 6 * * ? *` in `Europe/Paris`, against an 08:00
report. Two reasons, and both are worth keeping: a search failure must not take
the report down with it, and the report turn is already long enough without a
sweep in front of it.

**It registers and nothing else.** It writes no receipt and does not advance the
watermark. That is not a convention the prompt has to uphold — the subcommand
cannot do it — but the prompt still says so, because a model that has just read
about `commit` is exactly the reader who might reach for it.

The list of logins is **not in this prompt**, and neither are the repositories.
Both are in a file derived from the store: the same path with `.jsonl` replaced
by `.config.json`. That is the whole reason the watch adds nothing to the
500-character budget however many people or repositories are on it, and it is why
adding either is an edit to one file and never a change to a schedule.

**The reply is a single Block Kit `card`, not a carousel, and it is not
composed by the model.** `watch` builds it and puts it in the JSON's `card`
field: `eye-open` icon, "Author watch" title, `body` reading "no new items" or
"<N> new items" — the count that changed since the last run — and `subtext`
carrying the standing context that rarely does: how many items this store
tracks, and how many repositories and authors this run watched. Nothing about
that shape is a judgement call, so nothing about it is described here for a
model to assemble; the instruction below is only to relay the field, unedited.
A carousel would be wrong here on top of being unnecessary: a watch run is one
event, not one entity in a set of repositories the way `report`'s
per-repository cards are.

The description itself, 496 characters:

<!-- scheduler-description -->
```text
Register what the watched authors have open in #glorious-guidance (C0BPLSPHHDZ).
Follow the pr-tracker skill's watch workflow exactly.

  --state-file "$JIUWENSWARM_DATA_DIR/agent/workspace/state/skills/pr-tracker/C0BPLSPHHDZ.jsonl"
  --channel C0BPLSPHHDZ

$JIUWENSWARM_DATA_DIR is already set: never export or reassign it.
Each bash call is a fresh shell.

Registration only: never pass --commit-after; never write to GitHub or GitCode.
Reply with exactly the JSON's `card` field: nothing else.
```

The configuration itself lives at

```
$JIUWENSWARM_DATA_DIR/agent/workspace/state/skills/pr-tracker/C0BPLSPHHDZ.config.json
```

and is the only file here an operator edits by hand:

```json
{
  "schema_version": 1,
  "repositories": {
    "openJiuwen-ai/jiuwenswarm": {"gitcode": "openJiuwen/jiuwenswarm"},
    "openJiuwen-ai/agent-core": {"gitcode": "openJiuwen/agent-core"}
  },
  "watch": {
    "kinds": ["pull_request", "issue"],
    "window_days": 7,
    "authors": ["first-login", "second-login"]
  }
}
```

Both pairings above were confirmed against the second tracker rather than
inferred from the first one's name: each project carries merge requests whose
source branch is `github-pr-<N>` and whose title names the paired pull request,
which is the convention the refresh discovers a pairing by. A pairing that has
not been checked that way is left out — the repository is then tracked on the
first tracker alone, which is a smaller loss than reporting another project's
merge as this one's.

There is no `watch.repos` here, so every author is watched in both repositories.
Scoping one person to one of them is `{"login": "…", "repos": ["owner/name"]}` in
the `authors` list.

Before the first run of a new configuration, see what it would do:

```bash
python3 "$JIUWENSWARM_DATA_DIR/agent/workspace/skills/pr-tracker/scripts/pr_tracker.py" watch \
  --state-file "$JIUWENSWARM_DATA_DIR/agent/workspace/state/skills/pr-tracker/C0BPLSPHHDZ.jsonl" \
  --channel C0BPLSPHHDZ --dry-run
```

It prints `would_register_count` and `rows_after`. Compare that against what the
channel's report can render before letting the run write — a first sweep of
several people brings all their open work at once, and that is the one run whose
size is not the size of a normal day.

---

## 1c. Questions asked in the channel

Neither of the prompts above covers the turn where somebody simply asks *how
many of these have been merged?* — no schedule behind it, no report to render.
That turn gets no store path from anywhere, and a model that needs one and has
not been given one goes looking for it. That is how a path gets mistyped, and a
mistyped path returns the same nothing as a correct path with a wrong field
name in it.

**So the channel's standing instruction has to state the path too**, in whatever
the host offers for a per-channel system prompt or standing context — not only
in the trigger and the schedules. Nothing else is needed; it is one paragraph:

```text
Questions about what this channel tracks are answered by the pr-tracker skill's
query subcommand, against this store and no other:

  --state-file "$JIUWENSWARM_DATA_DIR/agent/workspace/state/skills/pr-tracker/C0BPLSPHHDZ.jsonl"
  --channel C0BPLSPHHDZ

$JIUWENSWARM_DATA_DIR is already set: never export or reassign it. Use the path
exactly as written above — do not search the filesystem for the store, and do
not retype the path from memory. If a command finds nothing, re-read the path
above rather than running it again with the path spelled differently.

Never count rows with grep, jq or a shell pipeline. The store has no "status"
field, and its state field never holds "merged", so a pattern like that matches
nothing and prints a zero indistinguishable from a real answer.
```

The last paragraph earns its space: the failure it names has happened. A model
asked how many tracked items had merged ran a `grep` for `"status": "merged"`,
got `0` from a store with no `status` field, and then varied the *path* rather
than the pattern until the turn was aborted on a repeated-tool-call guard.

---

## 2. The report prompt, human-triggered

For a report triggered by pasting this prompt, or by asking for it in the
channel. `report` and `commit` are two commands here on purpose: the script
cannot deliver to Slack — it holds no Slack credential — so delivery is your
action, and the watermark advances only after you have actually delivered. That
ordering is what stops a run consuming a window it never reported.

**This prompt commits late, and the scheduled one below commits early. The
divergence is intended — do not reconcile them.** Committing late is only worth
anything when someone can observe the delivery and decline to commit after a
failed one; a human-triggered turn can, so it keeps the two-step form and the
epilogue the report prints. A scheduled turn on this host cannot: it has no reader
watching, and the reply is sent only after the turn ends, so it cannot confirm its
own delivery from inside itself. The late commit therefore buys it nothing while
costing it a long command that has to be transcribed correctly — a step that can
fail on its own. Section 3 uses `--commit-after` for that reason, and this one
must not.

**This split depends on a host property.** A host that sends during the turn and
reports the result back to the caller should commit late on both paths; see
`host-notes.md` for how this one behaves and how to establish it for another.

```text
Reply with the tracked-changes report for #glorious-guidance (C0BPLSPHHDZ).

$JIUWENSWARM_DATA_DIR is already set in this environment. Never export it,
assign it or otherwise re-establish it: each bash call is a fresh shell, so an
assignment cannot outlive the command it is in, and one that comes out empty
turns the store path into a path that points nowhere.

1. Produce the report. It refreshes every tracked item from GitHub and GitCode,
   which takes a moment:

     python3 "$JIUWENSWARM_DATA_DIR/agent/workspace/skills/pr-tracker/scripts/pr_tracker.py" report \
       --state-file "$JIUWENSWARM_DATA_DIR/agent/workspace/state/skills/pr-tracker/C0BPLSPHHDZ.jsonl" \
       --channel C0BPLSPHHDZ

   It writes the report into a directory it derives from the store path and
   prints where. Do not make a directory of your own for it, and do not assign a
   variable to hold one: each command below is a fresh shell, so a directory
   named in this command cannot be named in the next.

   If it exits non-zero, reply with nothing but what went wrong, and stop. A missing
   GITHUB_TOKEN is a deliberate hard stop, not something to work around. So is a
   store that does not exist: that is a wrong path, not an empty channel, and it
   is not something --allow-missing-store should be reached for. Do not
   paste store paths into the channel: they are configuration this prompt
   supplied, and a reader can do nothing with them.

2. Check the report's language before you send it, at the path step 1 printed:

     python3 "$JIUWENSWARM_DATA_DIR/agent/workspace/skills/repository-activity-digest/scripts/check_report_language.py" \
       "$JIUWENSWARM_DATA_DIR/agent/workspace/state/skills/pr-tracker/C0BPLSPHHDZ.run/report.md"

   If it fails on a tracker title, render that title into English and cache it,
   then produce the report again:

     python3 "$JIUWENSWARM_DATA_DIR/agent/workspace/skills/pr-tracker/scripts/pr_tracker.py" title \
       --state-file "$JIUWENSWARM_DATA_DIR/agent/workspace/state/skills/pr-tracker/C0BPLSPHHDZ.jsonl" \
       --key '<the key printed in the report's Detail section>' \
       --rendered '<the English rendering>'

   Fix it by rendering, never by dropping the item. If the checker is not
   installed, say so in your message rather than skipping the check silently.

3. Reply with the report exactly as the file has it, including *Source and
   registration* — it names which store was read and how many rows it holds,
   which is the only way a misconfigured store shows up as a wrong report rather
   than as silence. Post it even when it says nothing changed: a silent run is
   indistinguishable from a broken one. Keep both HTML comments in the middle of
   it too: they are the message boundaries, the first splitting the brief from
   the tables and the second the tables from the prose. Dropping the first posts
   every table into the channel instead of into the thread.

4. Only after your reply has gone out, commit the run. The report prints the exact
   command, with the run id, on stderr. It looks like:

     python3 "$JIUWENSWARM_DATA_DIR/agent/workspace/skills/pr-tracker/scripts/pr_tracker.py" commit \
       --state-file "$JIUWENSWARM_DATA_DIR/agent/workspace/state/skills/pr-tracker/C0BPLSPHHDZ.jsonl" \
       --channel C0BPLSPHHDZ --run-id <the run id it printed>

   If the reply failed, do NOT commit. Nothing is lost by not committing: the same
   changes are reported again by the next run. Committing without replying loses
   them permanently.

Never comment on, close, approve, label or push to any pull request, merge
request or issue. This skill only ever reads the trackers.
```

---

## 3. The report prompt, scheduled

For a report a scheduler triggers on its own. Use this **instead of** section 2,
never as well as it: two prompts against one store means two runs racing for one
watermark.

One command, and no second one. `--commit-after` applies the run's receipt in
the same process, once the report has been rendered and written, so nothing is
printed for the model to copy and there is no step left that can be typed
wrongly. The ordering it guarantees is weaker — *the report was produced*, not
*the reader has it* — and on this path, on this host, that is the strongest
guarantee available anyway, because a scheduled turn here cannot observe whether
its own delivery landed. Confirm that before copying this prompt to another host:
where a turn can see its own send fail, section 2's ordering is the right one for
scheduled runs too.

```text
Reply with the tracked-changes report for #glorious-guidance (C0BPLSPHHDZ).

$JIUWENSWARM_DATA_DIR is already set in this environment. Never export it,
assign it or otherwise re-establish it: each bash call is a fresh shell, so an
assignment cannot outlive the command it is in, and one that comes out empty
turns the store path into a path that points nowhere.

1. Produce the report, committing the run in the same command. It refreshes every
   tracked item from GitHub and GitCode, which takes a moment:

     python3 "$JIUWENSWARM_DATA_DIR/agent/workspace/skills/pr-tracker/scripts/pr_tracker.py" report \
       --state-file "$JIUWENSWARM_DATA_DIR/agent/workspace/state/skills/pr-tracker/C0BPLSPHHDZ.jsonl" \
       --channel C0BPLSPHHDZ \
       --commit-after

   It writes the report into a directory it derives from the store path and
   prints where. Do not make a directory of your own for it, and do not assign a
   variable to hold one: each command below is a fresh shell, so a directory
   named in this command cannot be named in the next.

   If it exits non-zero, post nothing, say what went wrong, and stop. A missing
   GITHUB_TOKEN is a deliberate hard stop, not something to work around, and so
   is a store that does not exist — that is a wrong path rather than an empty
   channel, and --allow-missing-store is not the answer to it. Nothing
   is committed by a run that failed, so the next run repeats the same delta. Do
   not paste store paths into the channel: they are configuration this prompt
   supplied, and a reader can do nothing with them.

2. Check the report's language before you send it, at the path step 1 printed:

     python3 "$JIUWENSWARM_DATA_DIR/agent/workspace/skills/repository-activity-digest/scripts/check_report_language.py" \
       "$JIUWENSWARM_DATA_DIR/agent/workspace/state/skills/pr-tracker/C0BPLSPHHDZ.run/report.md"

   If it fails on a tracker title, render that title into English and cache it:

     python3 "$JIUWENSWARM_DATA_DIR/agent/workspace/skills/pr-tracker/scripts/pr_tracker.py" title \
       --state-file "$JIUWENSWARM_DATA_DIR/agent/workspace/state/skills/pr-tracker/C0BPLSPHHDZ.jsonl" \
       --key '<the key printed in the report's Detail section>' \
       --rendered '<the English rendering>'

   The rendering lands in the next run's report: this run is already committed,
   so do not produce it again — a second report would consume a second window.
   Reply with the report you have, and say the title was not in English.

3. Reply with the report exactly as the file has it, including *Source and
   registration* — it names which store was read and how many rows it holds,
   which is the only way a misconfigured store shows up as a wrong report rather
   than as silence. Send it even when it says nothing changed: a silent run is
   indistinguishable from a broken one. Keep both HTML comments in the middle of
   it too: they are the message boundaries, the first splitting the brief from
   the tables and the second the tables from the prose. Dropping the first posts
   every table into the channel instead of into the thread.

There is no commit step. The report already committed itself, and it prints no
command to run afterwards. If you find yourself about to run `commit`, stop:
this run's watermark has moved and there is nothing pending.

Never comment on, close, approve, label or push to any pull request, merge
request or issue. This skill only ever reads the trackers.
```

Passing `--run-id <id>` suppresses an exact double-fire: a second turn
arriving with a run id that already completed posts nothing and says so on
stderr, which is the intended behaviour and not an error to work around. It
only does that when the id passed in is the scheduler's own id for the tick,
stable across the turn's retries and distinct from the next tick's — and
getting one requires the scheduler to hand it to the model somewhere the
prompt text can read it, which is not how the scheduled-description path
below works: a description is text pasted once at job creation, not
re-rendered per firing, so there is nowhere in it to interpolate a per-tick
value. Nothing on this host exposes a tick id to the prompt text this way, so
the ready-to-paste descriptions in §4 and §5 never pass `--run-id`, and every
scheduled run falls back to inventing its own (`manual-<epoch-seconds>`),
unique to that invocation and so unable to suppress anything — the
double-fire case this flag exists for is not actually guarded against on this
host. Do not add `--run-id` to a scheduled description here on the assumption
that it will; only do so on a host whose scheduler integration puts the
tick's id somewhere the prompt can read, and confirm that before copying this
file to another host.

---

## Variants, for either report prompt

- **A repository is `owner/name`, and only the prompt says which.** The channel's
  name is not a repository, and neither is the deployment's word for the work.
  Add `--repo` only when the prompt names a repository, spelled as the prompt
  spells it; a value naming none is refused, and the refusal lists what the store
  actually holds.
- `--full` adds the whole roster to the report, for "where does everything
  stand" rather than "what changed".
- `--repo owner/name` narrows the report to one repository. It keeps its own
  watermark, so a filtered report does not consume the unfiltered one's delta —
  but commit it with the same `--repo` you reported with, whether that commit is
  a separate command or `--commit-after`.
- `--max-seconds` bounds the refresh, and `--refresh-workers` is how many items
  it refreshes at a time. Neither belongs in a scheduled prompt: the defaults are
  chosen to finish inside an ordinary tool timeout, and a prompt carrying its own
  numbers is a prompt that stops tracking them.

## When the report command is killed by a timeout

Do not run it again unchanged. It will do the same work on the same store and be
killed at the same point, and the second attempt costs a second time slice of
whatever budget the turn has — which is how one slow run becomes a turn that
delivers nothing at all. The run refreshes every tracked item, so its cost grows
with the store.

Lower the bound instead, so the run stops itself and delivers what it has:

    … report … --max-seconds 60

It then renders a partial report that says, in the channel message, how many
items it did not reach. Deliver that report: it is a true statement about an
incomplete run, and the items it skipped keep their window and are reported by
the next run. Say alongside it that the run was cut short.

## What registration does not cover, and what to say about it

A link posted while the service was down does not register: the trigger reacts to
a message as it arrives and nothing replays it. On this host the same applies to
links posted by a bot or app integration, and to links added by *editing* an
existing message — see `host-notes.md`, and expect a different set of limits
anywhere else. The report says `Registration: link trigger only` on every run,
and spells the consequence out in *Coverage and gaps*, for exactly this reason.
When something is missing, in order:

1. **Repost the link.** Immediate, and it upserts rather than duplicating.
2. **Ask for it explicitly** — `track --url <url> --via operator`.
3. **Reconcile against channel history**, once the host offers a scan of it — and
   check first that the scan is actually offered on the path you are invoking it
   from. Where it is not, the pass returns an empty result indistinguishable from
   an empty channel: a silent wrong answer, not an error. On this host it is
   offered to a Slack turn and not to a command-line invocation; `host-notes.md`
   has the detail. A scan of record belongs to the host's own capability, never
   to a Slack credential handed to a skill.

## 4. Short scheduler descriptions

A scheduler may cap the text it will carry — one caps it at 500 characters — and
a description that exceeds the cap can be rejected without a visible error. These
carry only what the deployment knows and leave every procedure to `SKILL.md`,
which the model reads on demand. They are what the scheduled jobs on this host
actually run.

Every one of them spends two lines on the environment variable, and those are the
best-value characters in the whole budget. A model reads the description before
it reads anything else, so the description is where it decides whether to
establish the variable — and the run is already lost by the time `SKILL.md` would
have told it not to.

Each states its own length, because they differ: the counts below are for a
17-character channel name and §5's for a 16-character one.

Deltas, 482 characters:

<!-- scheduler-description -->
```text
Tracked-changes report for #glorious-guidance (C0BPLSPHHDZ). Follow the
pr-tracker skill's scheduled report workflow exactly.

  --state-file "$JIUWENSWARM_DATA_DIR/agent/workspace/state/skills/pr-tracker/C0BPLSPHHDZ.jsonl"
  --channel C0BPLSPHHDZ --commit-after

$JIUWENSWARM_DATA_DIR is already set: never export or reassign it.
Each bash call is a fresh shell.

Reply with the report as rendered, header line included, even when nothing
changed. Never write to GitHub or GitCode.
```

Roster, the same but listing everything tracked rather than only what moved.
That one is 492 characters:

<!-- scheduler-description -->
```text
Full tracked-items roster for #glorious-guidance (C0BPLSPHHDZ). Follow the
pr-tracker skill's scheduled report workflow exactly.

  --state-file "$JIUWENSWARM_DATA_DIR/agent/workspace/state/skills/pr-tracker/C0BPLSPHHDZ.jsonl"
  --channel C0BPLSPHHDZ --full --commit-after

$JIUWENSWARM_DATA_DIR is already set: never export or reassign it.
Each bash call is a fresh shell.

Reply with the roster as rendered, header line included, even when nothing
changed. Never write to GitHub or GitCode.
```

Both are under 500 characters, with room to spare on purpose: a channel name a
few characters longer must not push a description over a cap that drops it
silently. A prompt this thin depends on `SKILL.md` being complete — what was
removed was procedure duplicated from it, not instruction the model can do
without.

Each description opens as a subject line rather than as "Reply with the …". The
delivery instruction is in the last paragraph, where it is not competing with
the identity of the channel, and the two together cost fewer characters than
saying "reply" twice did.

## 5. A second channel, as deployed

One deployment runs two tracking channels. Everything below differs from the
examples above only in the channel id and the store named after it — which is the
whole per-channel surface: nothing else changes between channels.

Link trigger, channel `C0BKHE3AH4M`, identical to §1 with the id and store swapped.

Daily deltas, `0 0 8 ? * TUE-SUN *` in `Europe/Paris`, 481 characters:

<!-- scheduler-description -->
```text
Tracked-changes report for #open-jiuwen-repo (C0BKHE3AH4M). Follow the
pr-tracker skill's scheduled report workflow exactly.

  --state-file "$JIUWENSWARM_DATA_DIR/agent/workspace/state/skills/pr-tracker/C0BKHE3AH4M.jsonl"
  --channel C0BKHE3AH4M --commit-after

$JIUWENSWARM_DATA_DIR is already set: never export or reassign it.
Each bash call is a fresh shell.

Reply with the report as rendered, header line included, even when nothing
changed. Never write to GitHub or GitCode.
```

Weekly roster, `0 0 7 ? * MON *` in `Europe/Paris`, 491 characters:

<!-- scheduler-description -->
```text
Full tracked-items roster for #open-jiuwen-repo (C0BKHE3AH4M). Follow the
pr-tracker skill's scheduled report workflow exactly.

  --state-file "$JIUWENSWARM_DATA_DIR/agent/workspace/state/skills/pr-tracker/C0BKHE3AH4M.jsonl"
  --channel C0BKHE3AH4M --full --commit-after

$JIUWENSWARM_DATA_DIR is already set: never export or reassign it.
Each bash call is a fresh shell.

Reply with the roster as rendered, header line included, even when nothing
changed. Never write to GitHub or GitCode.
```

Author watch, `30 5 6 * * ? *` in `Europe/Paris`, ahead of both, 495 characters:

<!-- scheduler-description -->
```text
Register what the watched authors have open in #open-jiuwen-repo (C0BKHE3AH4M).
Follow the pr-tracker skill's watch workflow exactly.

  --state-file "$JIUWENSWARM_DATA_DIR/agent/workspace/state/skills/pr-tracker/C0BKHE3AH4M.jsonl"
  --channel C0BKHE3AH4M

$JIUWENSWARM_DATA_DIR is already set: never export or reassign it.
Each bash call is a fresh shell.

Registration only: never pass --commit-after; never write to GitHub or GitCode.
Reply with exactly the JSON's `card` field: nothing else.
```

Each job carries its own `session_id` (`…_prtracking`, `…_prroster`,
`…_prwatch`). Two jobs sharing one session is a mistake that is easy to make by
copying a job and easy to miss afterwards, since nothing rejects it.
