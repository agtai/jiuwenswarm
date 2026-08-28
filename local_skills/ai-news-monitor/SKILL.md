---
name: ai-news-monitor
description: Sweep the web for news on agentic AI and its adjacent stack — agent frameworks and protocols (MCP, tool use, computer use), inference and serving (vLLM, SGLang, quantisation, throughput and cost), AI hardware and silicon (GPUs, TPUs, Trainium, HBM, datacenter capacity), model releases, evals, and the policy or security items that constrain deployment — then produce a deduplicated, primary-source-verified digest and remember what was already reported so the next run only shows what is new. Use this skill whenever the user asks what is new or what they missed in AI, wants to catch up on agentic AI or LLM news, asks about recent developments in inference, serving, GPUs or AI chips, wants a daily/weekly/monthly AI digest or briefing, asks to monitor or track a topic in this space, asks "did anything happen with <lab, framework, chip, or protocol>", or sets up a recurring AI news check — including when they do not use the word "news" and just ask what has been going on in AI lately.
---

# AI news monitor

Produce a digest of what actually changed in agentic AI and the stack under it,
for a reader who is building in this space and whose scarce resource is
attention, not information.

Three things make this hard, and the whole workflow exists to handle them:

- **Volume is not signal.** Most AI coverage restates press releases. The job is
  to find the handful of items with a number, a shipping date, or a capability
  change in them, and to say plainly when a window was quiet.
- **The same story arrives many times.** Search returns an announcement, three
  aggregators, and a newsletter recap as four results. Collapse them to one, and
  cite the primary source.
- **A monitor that repeats itself gets ignored.** The ledger script tracks what
  has already been reported, so run two shows only what run one did not.

## What a finished run looks like

Track these as you work, and treat the run as unfinished while any box is false:

- [ ] `date -u +%F` actually run, and its output — not a remembered date — used
      for the window and the compiled date (Step 1)
- [ ] Scope settled — store, profile, window, destination (Step 1), and the
      store `status` printed is the one the run is meant to write (Step 1)
- [ ] Run directory started with `start-run`, and every working file below
      written inside the path it printed rather than anywhere else (Step 1)
- [ ] Swept across the beats, every query carrying the current month and year
      rather than a remembered one (Step 2)
- [ ] Candidates deduplicated against the ledger, and the window `new` printed
      matches the one the digest is headed with (Step 3)
- [ ] Any item whose date Step 4 corrected, or first established, put back
      through `new` so the window gate sees the real date (Step 4)
- [ ] Every surviving item's date checked against the window, and out-of-window
      items dropped unless a Step 1 boundary case applies — named, not assumed
      (Step 5)
- [ ] Every URL cited was retrieved during this run, proven by `check_links.py
      --retrieved` exiting zero rather than by recollection (Steps 2, 4 and 6),
      and that check's receipt — the file the check wrote, never one written by
      hand — handed to `add --verified` (Step 7)
- [ ] Ranked, and weak-signal items dropped rather than padded in (Step 5)
- [ ] Digest written (Step 6)
- [ ] Run recorded, and the recording command exited without error — it refuses
      an item whose link this run did not verify or whose date the window does
      not admit, so a non-zero exit here means the digest is wrong, not the
      command (Step 7)
- [ ] Digest delivered to the destination settled in Step 1 — and delivered only
      because the recording step succeeded first (Step 8)

Recording comes before delivering, deliberately. A run that is never recorded
makes the next one re-report everything it just covered, so the reader sees the
same stories twice and stops trusting the monitor — and when the destination is
the conversation, delivering first leaves nothing after it in which to record.

Nothing enforces that order except this order. A refused `add` writes nothing,
which is a promise about the ledger, not a brake on delivery: where the reply is
the delivery there is no command to stop. A digest whose recording was refused
does not go out — see Step 7.

**If any part of this is delegated, the delegate reads this file.** Splitting the
sweep or the writing across sub-agents is fine, and often faster. Summarising
this file into a hand-off prompt instead is not: a paraphrase keeps the shape of
the work and drops the constraints, because the constraints are the parts that
read like caveats. A digest has already gone out with invented URLs and invented
dates because the writer was briefed from a summary and never saw this file.

So pass the path to this file and require it to be read. If a constraint truly
cannot travel — a prompt with no file access — carry these two verbatim rather
than in your own words, because they are what failed:

- `date -u +%F` must be run, and its output used for every date. Never supply a
  date from memory.
- Every URL must appear verbatim in a `free_search` result or a `fetch_webpage`
  response from this run. Never build one from a headline. Verify with
  `check_links.py --retrieved` and treat a non-zero exit as a failed run.

Neither the window nor the link check has to survive the hand-off any more.
`new` enforces the window in Step 3 whatever the prompt said, and `add` in
Step 7 refuses to record an item as published without the link check's receipt.
Both were carried as instructions and both failed that way — twice a digest went
out headed with one window and filled from another, and once a whole digest went
out in which every URL was invented, after the check had already reported them.
A delegate that runs the scripts gets both for free; one that does not cannot
finish the run.

If a step could not be completed, say so plainly in the output and leave its box
unticked. Reporting a run as complete when a step failed is worse than reporting a
partial run: it hides the gap from the person who could fix it, and — for the
recording step — the damage only shows up a week later, in a digest full of
repeats.

Throughout, `<skill>` means this skill's own directory — the one containing this
file. Resolve it to an absolute path before running any command below; the
scripts do not infer it.

`ledger.py` takes `--home` and `--profile` as flags, in either position:
`ledger.py --profile work status` and `ledger.py status --profile work` are
equivalent. What does not work is a bare word — `ledger.py work status` is
rejected, because neither is ever a positional argument.

**Two things address the ledger, and every example below carries both.**
`--home <store>` picks which store, `--profile <profile>` picks which ledger
inside it. Settle both in Step 1 and keep them on every call, including the ones
you run to check your work:

```bash
python3 <skill>/scripts/ledger.py --home <store> --profile <profile> status
```

A run that omits either reads an unrelated ledger: `last_run` comes back
`never`, the window falls back to seven days, everything already covered is
reported again — and the results are then written where nobody will look for
them, leaving the intended ledger permanently stale and the next digest a
repeat. It has happened to both flags. Omitting `--home` is the easier mistake
because the script has a working default, so nothing fails: the run reads and
writes a store of its own and reports success.

- **`<store>`** — the store root. If the invocation names one, use exactly that
  path. If it names none, run `status` once with no `--home` and use the `store`
  path it prints, with its trailing `/<profile>` removed, as `<store>` from then
  on. Either way you are typing a path rather than relying on a default, which
  is what makes the rest of the run consistent with itself.
- **`<profile>`** — a separate ledger with its own clock and history. Use
  `default` unless the request names one or the caller supplies one. Existing
  profiles are the directories under the store root shown by `status`; there is
  no subcommand that lists them.

`status` prints the store it resolved. Read that line on the first call and
check it is the store you meant — it is the one cheap confirmation that the rest
of the run is writing where it should.

## Step 1 — Scope the run

Establish three things before searching. Infer them; ask only if a wrong guess
would waste the whole sweep.

**Run directory.** Start this run's scratch directory, first, and note the path
it prints:

```bash
python3 <skill>/scripts/ledger.py --home <store> --profile <profile> start-run
```

Every working file below — `candidates.json`, `retrieved-urls.txt`,
`digest.md`, `link-check.json`, `reported.json` — lives in that directory and is
written and read as `<run>/<name>`. They are scratch, not the deliverable; Step 8
puts the digest where the reader asked for it.

**Write each of them with the file-write tool — `write_file`, or `edit_file` to
amend one that exists — never with a shell heredoc or a `>` redirect of your own
text.** What goes into these files is titles, URLs and prose taken off the open
web, and text like that eventually contains an apostrophe, a quote or a
parenthesis; one of those ends the shell's quoting early and turns the remainder
of the file into shell syntax. The command then dies on a syntax error that is
in the quoting rather than in the data, so running the same command line again
cannot succeed, and a run that keeps trying is stopped by the host for repeating
itself. The `>` redirects that do appear in the commands below capture a
script's own stdout, which is the script's output and not yours.

**Nothing may be written into `<run>` on that same command line.** `start-run`
empties the directory as its first action, so `start-run > <run>/anything` — or
a pipeline ending in such a redirect — makes a file it then deletes while the
file is still being written, and the write is lost without anything reporting an
error. There is nothing to capture in any case: `start-run` prints the run
directory and nothing else, and that one line is the whole of its output. This
run's working files are written by the steps that follow, each as its own
command, after `start-run` has returned. `start-run` refuses such a command line
rather than performing it.

`<run>` is a placeholder exactly like `<skill>` and `<store>`: resolve it to the
printed path in every command below. **It is not a shell variable, and must not
be made into one.** Each command of this run is a fresh shell, so a `RUN=...`
assignment in Step 1 is gone by Step 3, where `--input $RUN/candidates.json`
quietly becomes `--input /candidates.json` and the run dies on a path it never
chose.

Nothing has to be remembered, because the path is derived rather than invented:
it is the store path with `.run` appended, so any step can work it out from
`<store>` and `<profile>` alone, and `status` prints it as `run_dir`. That is the
whole reason it is not a random directory — a random name is unrecoverable the
moment the command that made it returns.

**Derived per profile, emptied at the start, and never inside the skill.** The
skill directory is one path shared by every profile and every run, and on a
deployed installation it is overwritten wholesale by the next sync. Runs that put
their working files there overwrite each other's: a link check has already run
against a digest a different run wrote seconds later, passing a digest whose seven
citations were never probed at all. `start-run` empties the directory as it starts
rather than cleaning up at the end, because a run that fails never reaches an end
— and a leftover `digest.md` from a failed run is indistinguishable from one this
run wrote, which is how a digest nobody produced gets link-checked and delivered.
Both scripts refuse a path inside the skill directory, so this is enforced rather
than trusted, but the refusal is a backstop — `<run>` is the answer.

**Window.** Check what the monitor already knows:

```bash
python3 <skill>/scripts/ledger.py --home <store> --profile <profile> status
```

If `last_run` exists, the window is from then until now. If it says `never`,
default to the last 7 days. Honour an explicit ask ("this month", "since
CES"). Get today's date from `date -u +%F` rather than assuming it — the
window is the one fact in the digest you cannot afford to have wrong.

Treat the boundary as soft, and judge by the reader rather than the arithmetic.
Step 3 enforces this list mechanically, so each case that keeps an item has a
code you write into the item's `window_exception` field; the two cases that drop
an item have none, because there is nothing to declare:

- **Straddling the start** — `straddles-window`. A two-day conference, an embargo
  that lifted the evening before. Include it, dated by its actual span rather
  than forced to one side.
- **Just outside, but still live** — `still-live`. Something announced a few days
  early whose deadline, launch, or effect lands inside the window. Include it and
  lead with the date that is still ahead of the reader; a compliance deadline
  three days out matters regardless of when it was announced.
- **Just outside and already settled** — announced shortly before the window,
  nothing outstanding. Leave it out; no code. On a recurring monitor the previous
  edition covered it. On a first run only, include it if it is load-bearing, mark
  it `first-run-context`, and say in the digest that it predates the window.
- **Older news in fresh coverage** — date it by when it happened, not by when
  someone wrote about it again, and leave it out. New commentary is not a new
  event. **This case has no code and never gets one.** A recap of a conference
  from three months ago is this case however current the write-up is, and reaching
  for one of the other three codes to keep it is the specific mistake the gate
  exists to stop.

These four are the whole of the licence. An item outside the window that matches
none of them is out, however strong it looks — especially then, because a strong
stale item is what survives every other check.

**Interests.** `status` reports an `interests` note if the profile has one — a
standing line on what this reader works on. It is optional, and most profiles
will not have it. When present, carry it into Step 5; when the ask states its
own focus, the ask wins for this run and the standing note falls back to
tie-breaking. Interests are the reader's state, never the skill's: the skill
stays generic so several people can share it, and each keeps their own note via

```bash
python3 <skill>/scripts/ledger.py --home <store> --profile <profile> config --interests "..."
```

**Beats.** Default to **all seven** in `references/beats.md`. A monitor's value
is that the reader does not have to know in advance where the important thing
will come from — the week the news is a power-grid constraint or an agent
exploit is exactly the week a narrower sweep would have missed it. Narrow only
when the ask itself is narrow: "any vLLM news" is one beat, not seven.

**Depth.** Match effort to the ask, and scale it with queries per beat rather
than by dropping beats — a beat that comes back empty costs almost nothing. A
quick check is one search per beat and a short digest; a thorough run works
through the query bank. Do not turn "anything new with MCP?" into a twenty-source
sweep.

Depth changes how much you look at, never how much you trust it. Verification in
Step 4 is not a tier — a quick check verifies its headlines exactly as a thorough
run does, it simply has fewer of them. If a claim genuinely could not be checked,
that is reported as `unconfirmed` rather than quietly upgraded; a fast digest is
a shorter one, not a less reliable one.

**Destination.** Settle where the digest is going before writing it — it decides
the format, whether a budget applies, and whether a file exists at all.

**Ask where the reader will look, not whether anyone is watching you run.** The
two are unrelated, and confusing them is how a digest ends up somewhere nobody
opens it.

- **Into the conversation** — the default, and the right answer whenever the
  reply is what reaches the reader. Most asks are answered best by simply saying
  what happened, and a file nobody asked for is clutter.
- **To a file** — when the ask names a path, or when something downstream
  consumes the file. Use the location given; otherwise the directory the run was
  invoked from. Not `<run>`: a digest someone asked for is a deliverable, and a
  temp directory is ephemeral and hard to find again.
- **To a platform** — produce the text in that platform's format (Step 6) and
  hand it over. This skill does not post anything; delivery belongs to whatever
  called it.

**An unattended run is not automatically a file.** A scheduled or delegated run
is very often one whose reply *is* the delivery — it is posted wherever the
schedule points, and the reader reads that. Writing to a file there produces a
digest sitting on a disk nobody visits, and a reply that describes it instead of
being it. Choose the file only on the two grounds above, whoever is or is not
watching. If the invocation says where the digest goes, that is the destination;
if it says nothing, the reply is.

Working files — the candidate list, the payload for `add` — are not deliverables.
They stay in the `<run>` directory from the top of this step, so a run neither
litters someone's project nor collides with another run.

**Length.** By default there is no budget: write what the window warrants, and
let a quiet week be short. A named destination can carry one implicitly: if the
ask says the digest is going to Slack, budget **3800 characters per part** unless
told otherwise. Slack documents 4000 as the recommended maximum for a message's
text, and the margin covers the slight growth `--divider` adds when the copy is
converted. Two exceptions worth knowing: if the caller will wrap each part in a
Block Kit *section block*, the hard limit is 3000, so budget 2900 instead; and
nothing is truncated until 40,000, so a single over-long part degrades rather
than failing. Some destinations impose a ceiling, though — a chat
message, a card, an email preview — and a digest that arrives truncated is worse
than one written to fit. When the ask carries a budget, whether a number
("under 2500 characters") or a feel ("keep it brief"), treat it as a target that
shapes writing rather than a guillotine applied afterwards.

Tighten in this order:

1. **Bodies before items.** Four sentences become two. Every story still appears.
2. **Headlines become one-liners.** Demote from the bottom of the ranking up. A
   demoted item is still reported: it keeps its link and its caveat, it just
   stops carrying prose. Demotion is not dropping.
3. **Still over? Split into parts.** Do not drop an item to make the budget.

Work rungs 1 and 2 to exhaustion before reaching for rung 3. Each extra part
costs the reader another message to open; brevity costs them nothing. Stop
demoting only when the next cut would strand a number from the caveat that
qualifies it — at that point add a part instead.

That third rung is the important one. A budget is a constraint on the container,
not on what is worth telling the reader. An item that cleared the Step 5 bar has
earned its place; if it will not fit, the answer is another part, not a shorter
list. The only things that ever get cut are the ones the ranking rejected on
merit.

**Never compressed, in any of the three passes:**

- **Every primary-source URL.** A link cannot be shortened without destroying
  what it is for, and a claim the reader cannot check is worth less than no
  claim. Links are also where a tight budget actually goes — a single press
  release URL can run 150 characters, over 5% of a chat-sized budget. When links
  are what push you over, move an item to the next part. Never strip its source.
- **The caveat that decides whether to believe a number.** A throughput figure
  without its batch size is worse than no figure.
- **The Coverage notes.**

A shorter digest may be less complete; it must not become less trustworthy.

**When splitting**, each part must stand on its own and fit the budget by itself:

- Part 1 carries the header and the top line; the final part carries Coverage
  notes.
- Split at item boundaries — never mid-item, and never separate a number from
  its caveat.
- Head each part `Part N of M`, because a reader receiving several messages
  needs to know when one is missing. This is the one piece of bookkeeping that
  is genuinely for the reader. **Number the parts last** — M is not known until
  everything is measured, and numbering early means renumbering every header
  when the final part overflows.
- A section running across a split simply repeats its heading. No "(cont.)"
  markers: each part stands alone, and a reader opening part 3 first should not
  meet a fragment.
- Write the parts as `<run>/digest-part-N.md`. That is the working name, the one
  Step 6 checks; the delivered name is Step 8's business.

Measure the raw file with `wc -m`, not `wc -c`. Character limits count
characters, and `wc -c` reports bytes — an em dash or a bullet is several bytes
each, so a byte count overstates by around 1%. Measuring the raw file also
counts markdown link syntax that collapses to a short label once rendered, so a
raw count runs ahead of what the destination sees. Both errors point the same
safe way: you finish under budget rather than over. Prefer that direction over
trying to predict the rendered length.

Read `references/beats.md` now — it carries the query bank and the per-beat
traps. Read `references/sources.md` before verifying claims; it maps stories to
their authoritative homes.

## Step 2 — Sweep

Run several searches per beat, from the query bank, with the current month and
year substituted in. Issue independent searches in parallel — they do not depend
on each other, and a sweep is mostly waiting.

**Substitute the month and year from the `date -u +%F` you ran in Step 1, never
a remembered one.** The query bank writes these as `<month year>`; a placeholder
filled from memory is the single most expensive error in the sweep, because no
search backend here takes a date parameter — the words in the query are the only
recency constraint there is. A sweep that searched a month eighteen months stale
returns plausible, well-ranked, entirely wrong results, and every later step
treats them as this window's news. Before issuing the batch, read the queries
back and confirm the month and year in them match the window.

**Search results are ranked by relevance, not by date, and most carry no date at
all.** The top hit for a well-formed query about this month is routinely a
months-old overview page that outranks the actual news, and some backends append
a "recommended fetch targets" list of the top few results — that ordering knows
nothing about the window. Do not let position decide what gets fetched. Scan the
whole result list for the in-window items and fetch those, even when they sit at
position six or eight; a dated slug or a date in the title is often the only
recency signal a result carries, and it is the one worth reading first.

Whatever is running you may cap or rate-limit search. Treat that as a constraint
to route around, not a reason to stop: go straight to primary sources instead —
release APIs, changelogs, spec repositories, vendor newsrooms, aggregator front
pages. A run whose search quota was exhausted before it started still produced a
complete digest this way, and the direct path is often the higher-yield one
regardless.

Two habits that raise yield a lot:

- **Search the vocabulary, not the topic.** "AI news" returns consumer stories.
  "disaggregated prefill throughput benchmark" returns the thing that matters.
  Practitioners and vendors use specific words; borrow them.
- **Go direct where the signal lives.** For fast-moving projects, the GitHub
  releases page or changelog beats any search. Fetch those directly.

Collect candidates as `{url, title, source, date, beat}` without reading them
deeply yet. Reading comes after deduplication, so you do not spend a fetch on a
story you are about to discard.

`date` is not optional bookkeeping — it is what every later step filters on, and
a candidate carried forward without one becomes an item nobody can place in or
out of the window. If a result gives no date, either establish one when you fetch
it in Step 4 or drop it; do not record a guess, and do not leave the field blank
and decide later. Write the date you actually found, against the window from
Step 1, and apply the boundary rules there — the four cases listed under
**Window** are the whole of the licence to keep something outside it. An item
that matches none of them is out, however strong it looks.

**Append every URL you retrieve to `<run>/retrieved-urls.txt` as you go**, from search
results and fetched pages alike, including ones you expect to discard. Step 6
checks the finished digest against this file, so a link missing from it cannot be
cited even if it is genuine. Writing it later from memory defeats the point — the
file is evidence of what was actually opened, and reconstructing it is the same
act as inventing a URL. Anything that contains the URLs works; the file is
scanned for http(s) tokens, so raw results can be pasted in unedited — with the
file-write tool, as Step 1 says, because raw results carry titles and quotation
marks that a heredoc would break on.

## Step 3 — Deduplicate, and let the window filter

Write the candidate list to JSON and filter it. **Write `<run>/candidates.json`
with the file-write tool**, as Step 1 says of every working file, and not with a
shell heredoc: the titles in it came off the open web, and a single apostrophe or
parenthesis in one of them breaks the quoting for the whole list. `--input` names
a file of **item JSON** — a list of objects, one per candidate:

```bash
# <run>/candidates.json
# [{"url": "https://example.com/x", "title": "...", "beat": "inference",
#   "date": "2026-08-04", "source": "Example"}]
python3 <skill>/scripts/ledger.py --home <store> --profile <profile> new --input <run>/candidates.json --verbose
```

Only `url` is required per item. `--items '[{...}]'` passes the same JSON as a
single argument instead of a file, but only for a couple of items short enough to
have typed by hand: the operating system caps how long one argument may be, and a
real candidate list exceeds that cap and is rejected as `Argument list too long`
before this script runs at all. It carries the quoting hazard above as well, so
the file is the normal form.

Plain output is a JSON list of the items it kept; `--verbose` wraps it as
`{"new": [...], "skipped": [...], "out_of_window": [...]}` so you can see what
went and why. Scanning the skipped list is worth it — if something dropped is
genuinely a follow-up development rather than a repeat, keep it and say
explicitly that it updates an earlier item.

**`new` applies the window itself, and the first stderr line is the window it
used.** Read that line. It is derived the same way Step 1 derives it — from this
profile's `last_run`, or the last 7 days when the profile has never run — so
under normal use it needs no flag and already agrees with the digest header.
When the ask named a different span ("this month", "since CES"), pass it:

```bash
python3 <skill>/scripts/ledger.py --home <store> --profile <profile> new --input <run>/candidates.json \
        --verbose --window-start 2026-01-07
```

Items dated outside the window are dropped into `out_of_window`, each carrying
`_out_of_window` with the reason. **This is not a failed run** — `new` still
exits zero and the pipeline continues; the items are simply not in the list you
go on to read and rank.

To keep one, it must name which of the Step 1 boundary cases applies, in a
`window_exception` field on the item, and then be run through `new` again:

```json
{"url": "https://example.com/summit", "title": "...", "date": "2026-08-03",
 "window_exception": "straddles-window"}
```

The three accepted values are `straddles-window`, `still-live` and
`first-run-context`; anything else counts as no exception at all, so the item is
still dropped. A kept item comes back annotated `_window_exception`, and the
digest has to carry that fact to the reader — an out-of-window item published
without saying so is the thing the reader notices.

Do not reach for a code to rescue an interesting old story. Two digests have
gone out headed with one week and filled with a conference from three months
earlier; both items had their true dates recorded and were kept anyway. That is
why this is a filter and not a reminder.

An item with no `date`, or an unreadable one, is **kept** and annotated
`_date_unknown` rather than dropped — a candidate may legitimately arrive undated
and get its date when you fetch it in Step 4. It is also not checked against the
window at all, so an empty `date` is not a way past this: Step 4 establishes the
date and puts the item back through `new`.

Be clear on what this pass can and cannot do. It drops exact repeats: the same
canonicalised URL, whether already in the ledger or twice in this batch, plus
near-verbatim headline rewrites. It does **not** collapse five outlets writing up
one announcement in their own words — those come back as five items, at most
hinted. Clustering them is your job, below.

**Read the `_maybe_same_as` hints on the items it kept.** Headlines about the
same event overlap far less than you would expect — two write-ups of the same
model release routinely score around 0.3, well under the drop threshold — so
anything plausibly related is passed through with a hint rather than discarded:

```json
{"title": "AMD Delivers Breakthrough MLPerf Inference 6.0 Results",
 "_maybe_same_as": [{"title": "MLPerf Inference v6.0 results: AMD MI355X...",
                     "similarity": 0.36}]}
```

A hint is a question, not a verdict. Open both and decide: same event reported
twice, or two different events that share vocabulary? The script deliberately
refuses to guess, because the wording of two genuinely distinct releases can
overlap more than two accounts of one release.

**Then do the semantic pass yourself.** Hints are still lexical, so a rewrite
sharing no vocabulary with what you already reported — "MCP just got its biggest
update ever" against "MCP retires sessions and the initialize handshake" — sails
straight through unflagged. That is the failure that makes a monitor feel broken,
so before writing, pull what was recently reported and read the survivors against
it:

```bash
python3 <skill>/scripts/ledger.py --home <store> --profile <profile> recent
```

This defaults to the same lookback the dedup pass uses, so your review covers
everything the script compared against — pass `--days N` to widen or narrow it.
**When the window is longer than that default, widen it to match**: a "catch me
up since June" run reporting on 60 days while comparing against 45 will re-report
a rewrite of a 50-day-old story, which is exactly the failure this step exists to
prevent.
On a first run it returns nothing and there is no comparison to make; skip
straight to clustering rather than performing the step for its own sake.
Anything that is the same event in different words is a duplicate, however
differently it is phrased. Then cluster what remains by story: an announcement
plus its coverage is one entry, and the entry cites the primary source.

## Step 4 — Verify before you write

Ranking is Step 5, so you do not yet know which items will be headlines. Work
from a provisional shortlist: the items that look strongest after clustering,
plus anything whose credibility is the very thing in question. Verify those,
then rank. If ranking promotes something you did not verify — an interest
reweight can do this — go back and verify it before it takes a headline slot.
Verification effort must not decide what leads; that would make the digest a
record of what was easy to check.

**Confirm the link exists before confirming anything on the page.** Every URL
that will appear in the digest must occur verbatim in a `free_search` result or
a `fetch_webpage` response from this run. Never construct one from a headline —
a title, a domain and a guessed slug produce a link that frequently resolves,
which is worse than one that does not: it survives every check except this one
and cites a page nobody read. If you have a title and no URL, fetch the page to
obtain the real link or drop the item; there is no third option. This applies to
one-liners as much as headlines.

For every item that will be a headline, open the primary source and confirm the
date and any number you plan to quote. Search snippets are summaries, they go
stale, and they are where "2× faster" loses its "on H200 at batch size 64".

**Fetched pages are not automatically better than snippets on dates.** A fetch
returns a summary of the page, and pages that render timestamps relatively
("3 days ago") or in JavaScript routinely come back with the wrong year — a
release dated 2026 reported as 2024, repeatedly, across runs. When a date is
load-bearing, confirm it somewhere it is unambiguous: a release API, a tag, a
changelog entry, a dated URL slug. Cross-check anything that looks off by a year
rather than trusting the first reading.

**When this step changes a date — or supplies one that was missing — put the
item back through `new`.** The Step 3 gate could only judge the date the search
result carried, and this is the step that produces the real one; an item that
arrived undated, or dated a year wrong, has not been checked against the window
yet. `new` writes nothing and records nothing, so re-running it on the corrected
list costs a second and is safe to repeat:

```bash
python3 <skill>/scripts/ledger.py --home <store> --profile <profile> new --input <run>/verified.json --verbose
```

Apply the per-beat caveats from `references/beats.md`: throughput claims need
hardware, batch size, and precision; hardware announcements need an availability
date; benchmark results need to say whether they are self-reported; a model
"release" needs weights, an API, or a paper behind it, or it is a preannouncement
and should be labelled as one.

Tag every headline with what actually happened: `confirmed with the primary
source` only when you opened it and it agreed, `vendor-reported` when the primary
source is the interested party, `unconfirmed` when you could not check. Never
carry the first tag on the strength of a search snippet — an unverified claim
labelled verified is worse than an unverified claim, because it spends trust the
digest has not earned.

If a source cannot be reached — paywall, JS-only page, dead link — say so in the
digest rather than reconstructing the claim from the snippet. A monitor's value
is that its numbers can be trusted.

## Step 5 — Rank by signal

**First, re-read every surviving item's date against the window.** `new` has
already filtered on it twice, so this pass should find nothing — treat anything
it does find as a sign that a date changed after the last filter, and put the
list back through `new` rather than adjudicating it by hand.

Ranking is about ordering what belongs in the digest, and an item outside the
window does not belong in it at any position — so the window is a gate applied
before the ranking starts, not a tie-breaker inside it. Verification in Step 4
was the point at which you established the real date; this is the point at which
that date decides whether the item stays. An item whose confirmed date falls
outside the window and matches none of the four boundary cases in Step 1 is
dropped here, even when it is the most interesting thing the sweep found —
especially then, because a strong stale item is exactly what survives every other
check. A digest headed with one window and filled from another is wrong in the
way readers notice first and trust last.

Anything kept on a `window_exception` keeps it into the writing: say in the item
itself that it predates the window, and why it is here anyway. An exception the
reader is not told about is indistinguishable from the error it is an exception
to.

Then order what remains by what changes a reader's decisions, not by how loud the
coverage was.

**Where the reader's interests are known** — from the ask, or from the profile's
standing note — weight by them, but never let them become a filter. Someone who
runs vLLM on H200s should meet the serving news first. They should still be told
about a critical agent-security disclosure, because the reason to want a monitor
rather than a search is to hear the thing you did not know to ask about.
Interest reorders; it does not exclude. A stated interest can lift an item into
the headlines or drop it to a one-liner. It cannot remove one that cleared the
bar below, and it cannot promote one that did not.

Strong signal, lead with it:
- Something is now buyable, installable, or callable that was not before
- A number that moves a real tradeoff — cost per token, throughput, context
  limit, accuracy at a given precision
- A capability shown with an eval, or an eval showing a claimed capability fails
- A constraint with a date on it — deprecation, price change, rule taking effect
- A concrete failure: exploit class, incident, reproduction that did not replicate

Weak signal, cut or compress to one line:
- Restated press releases and roadmap slides with no ship date
- Funding rounds that change nothing about who can buy compute
- Opinion pieces, predictions, listicles, "X changes everything"
- Leaderboard movement with no methodology

Keep 3–6 headlines. If the window genuinely produced fewer, write fewer — an
honest short digest is worth more than a padded one, and padding is the fastest
way for a recurring monitor to lose its reader.

That range describes how much a normal window yields; it is not a floor that
blocks demotion. Under a length budget you may finish with two headlines and a
longer list of one-liners, and that is the intended outcome — every story is
still reported, carrying its link and its caveat. What the range rules out is
inventing headlines to reach three.

When more items clear the bar than there are headline slots, the cap wins and
the rest move to **Also notable** as one-liners. A length budget never changes
which items make it in — only how much prose each carries and how they are
spread across parts. Nothing high-signal is dropped
for want of room; it is compressed. Judge what to promote by how much explaining
the item needs — a deprecation date is complete in one line and loses nothing as
a one-liner, whereas a benchmark result whose caveats decide whether to believe
it needs the space. Rank within the headlines by decision impact, not by how
recently it happened — this orders items that have already cleared the window
gate above, and is never a reason to keep one that did not.

## Step 6 — Write the digest

Write it to `<run>/digest.md`, or `<run>/digest-part-N.md` for each part when a
budget forced a split, with the file-write tool as Step 1 says — a digest quotes
headlines verbatim, so a heredoc breaks on the first apostrophe in one. **Write
it to a file even when the destination is the conversation** — the check below
reads a file, so there is no version of this step without one, and the delivered
copy is Step 8's business. The deliverable gets its `ai-digest-YYYY-MM-DD.md`
name there, when it is placed; naming it early only means the file the check is
given and the file that exists have different names.

Use `assets/digest-template.md`. The shape is deliberate: window and freshness
in the header so the reader knows what they are looking at; a top line they can
read alone; headlines carrying the fact in the heading rather than the topic
("TensorRT-LLM ships FP4 decode, 1.8× on B200" beats "NVIDIA inference update").

Write for someone who will act on it. Every headline should answer "what does
this change for me?" in its own body, not leave it implied.

**Every URL must be one you actually retrieved during this run.** Never
reconstruct a plausible-looking link from a title, a domain and a guess at the
slug — that is how a digest ends up citing pages that have never existed, and an
invented URL is worse than none because it reads as a citation while being the
opposite of one. This applies to one-liners as much as headlines: they carry
links too, and they are the ones that escape Step 4's verification. If you could
not retrieve something, cite what you did open and say the primary source was
unreachable, or leave the item out.

Then check them, because a link is one of the few things in a digest a machine
can settle:

```bash
python3 <skill>/scripts/check_links.py <run>/digest.md \
        --retrieved <run>/retrieved-urls.txt --json > <run>/link-check.json
```

Name every part explicitly when the digest was split — `<run>/digest-part-1.md
<run>/digest-part-2.md`, the script takes several files — rather than reaching for
a wildcard. A wildcard that matches nothing is not an empty check: the shell
hands the pattern over as a literal filename and the script exits 2 without
writing a receipt, so Step 7 then refuses every item for want of one.

This is a gate, not a report: a non-zero exit means the digest is not ready, and
the run is unfinished until it passes. Pass `--retrieved` every time. Without it
the check falls back to reachability alone, which is precisely the check a
fabricated URL passes — guessed slugs resolve on any site that builds its URLs
from titles, so the fabrications that matter come back `OK`.

**A check that found no links has failed, not passed.** It exits non-zero and
says so, because a gate that inspected nothing has been skipped rather than
satisfied. The check reads `[label](url)`, `<url>`, `<url|label>` and bare
`https://…`, so a digest citing its sources in any of those forms is seen; if it
still reports none, the digest genuinely cites nothing and cannot support a
published item. A run once read that message as a clean pass, delivered, and
then had every item refused at Step 7 for want of a verdict.

**Whatever it says, that file is the receipt — do not write one yourself.** The
receipt records which files were read, their sha256, and a verdict per link, and
`add` checks it identifies itself as this script's output. A hand-written stand-in
is refused by name. It is also the exact move that lets a digest with no
verifiable citation go out: the check reported nothing, a receipt was typed to
say the links were fine, and nothing had in fact been examined. If the check
will not produce a usable receipt, the finding is that the digest is not ready.

**Run this after the digest file is final, and keep `link-check.json`.** Step 7
will not record anything as published without it, because reading the verdict
and acting on it turned out to be two different things: a run once had `broken`,
`unreachable` and `404` in its own log and recorded all seven items anyway. The
receipt is matched per URL, so a check run against an earlier draft refuses the
items that draft did not cite — which is the same failure, one step earlier.

`UNSOURCED` means the URL is not in the record of what this run retrieved. Do
not clear one by fetching it now and keeping the sentence attached to it: the
claim was written before the page was read, so the page has not been checked
against the claim. Replace it with a source that was opened, or drop the item.

`BROKEN` means malformed, a placeholder domain, a host that does not resolve, or
a definitive 404 or 410 — fix or remove it before delivering, and a non-zero exit
means the digest is not ready. `BLOCKED` means the site refused an automated
request, which is common and not a defect in the link: openai.com answers 403 to
a script, CNN 451, Reddit blocks outright. Treat `BLOCKED` as a prompt to confirm
you really did open that page, not as something to fix. Run it on the converted
copy too if you made one. If a length budget
was set in Step 1, write to it directly rather than drafting long and trimming —
trimming late is what strands a number without its caveat.

**The digest has to stand on its own.** The reader has the page and nothing
else — not this skill, not its configuration, not its previous runs — and may
well be someone the digest was forwarded to. So keep the machinery out of the
prose:

- **Never name a beat.** Beats are how *you* organise the sweep; they mean
  nothing to a reader. Use the plain topic labels in the template — `Agents &
  protocols`, `Inference & serving`, `Hardware`, `Models`, `Evaluation`,
  `Business & infrastructure`, `Policy & security` — and never the numbering.
- **Do not publish a work log.** Which areas were searched, how many candidates
  were filtered, whether a ledger existed — none of that is a finding. If an
  area was quiet, give the reader the fact ("nothing shipped in hardware this
  week"), not the process ("all seven beats were swept").
- **Coverage notes are about trust in the text, not effort spent.** "This
  figure is as published by the vendor, not re-derived" tells the reader how
  hard to lean on it. "Four beats covered" tells them nothing.
- **Carry continuity only when it means something.** "Resolves the licensing
  question left open on 26 July" is useful to the reader. "First run, no prior
  ledger" is bookkeeping and belongs nowhere near the page.

**Markdown is the output format.** It is what the template is written in, what
reads well in a file or a terminal, and what every downstream tool accepts.

**Markdown is also what you deliver, in every case but one.** Converting is not
a step in the normal run, and the question is not which platform the digest is
headed for — it is whether anything stands between you and the wire:

- **The digest is your reply, or a file someone opens.** Deliver Markdown. Do
  not convert. Whatever carries a reply into a chat destination renders it, and
  converting first means the text is rendered twice — the second pass cannot
  undo the first, so all it can do is act on what the conversion got wrong.
  Converting also flattens anything the destination renders specially: a pipe
  table converted to text can no longer be drawn as a table, and neither can it
  be turned back.
- **You are producing the exact bytes something else will post verbatim** — a
  file handed to a poster that does no rendering of its own, or a request the
  ask spells out as mrkdwn. That is the only case that converts:

```bash
uv run <skill>/scripts/md_to_mrkdwn.py <run>/digest.md --divider -o <run>/digest.slack.txt
```

Slack renders `mrkdwn` rather than Markdown — `*bold*` not `**bold**`,
`<url|label>` not `[label](url)`, and no headings at all — so text posted raw to
its API needs this. Keep both files: the Markdown remains the artifact, the
converted copy serves one destination. `--divider` draws a rule above each
section, worth passing because mrkdwn has no headings and section titles
otherwise look identical to item titles. Do not convert on the strength of a
vague "send this to the team": you would be guessing at both the platform and
whether anything in the path already renders Markdown, and mrkdwn arriving
somewhere that does renders as literal punctuation.

The converter also needs `uv` and a package fetched from the network. That is
another thing to fail in a run nobody is watching, for a step the common case
does not need at all.

Conversion barely moves length: plain output runs about 1% shorter than its
Markdown source, but `--divider` adds roughly 17 characters per section and comes
out slightly *longer*. So it can push a digest that just fit over the limit —
**a budget applies to whichever copy actually reaches the destination**. Check
that one, and if a converted part goes over, trim the Markdown and convert again
rather than editing the converted file.

Hold the finished digest until Step 7 has recorded the run, then deliver it in
Step 8. Recording needs nothing that delivery produces, and when the destination
is the conversation the digest *is* the reply — so anything sequenced after it
competes with the end of your turn.

## Step 7 — Record the run

Record what you reported so the next run does not repeat it. **`add` records
item JSON, never the digest.** You have just written a Markdown file in Step 6;
it is not what goes in here. Build a fresh JSON list of what you reported —
the same shape you filtered in Step 3 — write it with the file-write tool for the
reason Step 1 gives, and pass that:

```bash
# <run>/reported.json — item JSON, one object per item, not the Markdown digest
# [{"url": "https://example.com/x", "title": "...", "beat": "inference",
#   "date": "2026-08-04", "source": "Example", "why": "1.8x on B200"}]
python3 <skill>/scripts/ledger.py --home <store> --profile <profile> add --input <run>/reported.json \
        --verified <run>/link-check.json --window 7d
```

Passing `digest.md` — or any prose — to `--input` fails with `input is not
valid JSON`, exits non-zero and writes nothing at all, which leaves the ledger
empty and the run effectively unrecorded.

`add` takes items three ways, all of them the same fields. Use whichever matches
what you already have; bare positional arguments are not one of them:

```bash
# inline JSON — usually the shortest path, no file to write
ledger.py --home <store> --profile <profile> add --items '[{"url": "...", "title": "..."}]' \
              --verified <run>/link-check.json --window 7d
# a single item, no JSON at all
ledger.py --home <store> --profile <profile> add --url https://example.com/x --title "..." \
              --beat inference --date 2026-08-04 --source Example --why "1.8x on B200" \
              --verified <run>/link-check.json
# a file of item JSON, or stdin — the bulk form, as above
ledger.py --home <store> --profile <profile> add --input <run>/reported.json --verified <run>/link-check.json --window 7d
```

`--url` is the one required field: the ledger suppresses by URL, so an item
without one matches nothing later.

### `--verified` — the link check's receipt

**`add` will not record an item as published unless this run's link check
already found its URL usable.** Pass `--verified <run>/link-check.json`, the file
Step 6 wrote. This is not a second check — it is the first one's verdict finally
reaching the decision it was always meant to inform:

- **`OK` and `BLOCKED` are usable.** `BLOCKED` means the site refused an
  automated request, which openai.com, CNN and Reddit all do; failing a run over
  those would teach you to route around this.
- **`BROKEN` and `UNSOURCED` are not**, and neither is a URL missing from the
  receipt altogether. Missing means the digest that was checked did not cite it:
  the item was introduced after the check, or the check ran against a draft.
- **A receipt written without `--retrieved` is rejected**, because reachability
  alone is exactly the check a fabricated URL passes.

**This refuses; it does not filter, and it exits non-zero.** The window gate in
Step 3 stays at exit 0 because a filtered candidate is not a failed run — there
the item simply never enters the digest. Here the digest is already written, so
silently dropping an item would leave it published and unrecorded, which is the
worse of the two states.

**What a refusal guarantees is that nothing was written.** No item is recorded,
the clock does not move, and the profile is left in a state the next run can
still reason about — so the call can be fixed and repeated with no cleanup, and
no partial digest is ever half-recorded.

**What it does not do is stop delivery.** A refusal is an exit code; it has no
reach into Step 8. Chaining the two in one shell — `add && deliver` — makes the
shell enforce it, and that is worth doing whenever delivery is a command. But
when the digest is your reply, there is no `&&` and nothing mechanical between
the refusal and the reader: only this order holds, and only because you follow
it. A run has already delivered a digest whose `add` had just refused every item
in it.

So treat a non-zero `add` as a decision about the digest, not a note about the
command: **it does not go out in that state.** Fix it and record again. If it
has already gone out, do not quietly re-run `record-run` to tidy the clock — say
in the same place the digest went that the run is unrecorded and why, because
the next run will re-report the window and the reader is the one who sees it
twice.

To recover, fix the digest and `reported.json` together, re-run Step 6's check,
and record again. Do not clear an `UNSOURCED` by opening the page now and keeping
the sentence attached to it. An item that is correctly not going out is not a
published item — record it as a suppression, below.

`--verified` may be omitted only when every item carries `duplicate_of` or
`reason`: those were never shown to a reader, so there is no citation to vouch
for. Do not reach for that to get past a refusal — a suppressed item is one the
digest does not contain.

### The window, again

**`add` applies the same window `new` applied in Step 3**, to the same items,
with the same three exception codes. That is not belt-and-braces: `new` filters
its own output, but nothing made the list you publish a subset of that output,
so an item introduced anywhere after Step 3 was never checked at all. One was —
dated twelve days before the window, on a run whose `new` call reported not a
single drop, because the item had simply never been passed to it.

The window is derived exactly as `new` derives it, from this profile's
`last_run`, which this call has not advanced yet; it is printed on stderr, as it
is there. When Step 1 named a different span you passed `--window-start` to
`new`, so pass it here too:

```bash
ledger.py --home <store> --profile <profile> add --input <run>/reported.json --verified <run>/link-check.json \
              --window-start 2026-01-07 --window 'since CES'
```

`--window` and `--window-start` are different things and both still apply:
`--window` is the free-text label `status` shows, never parsed; `--window-start`
and `--window-end` are the dates this gate uses.

**Record the whole run in one `add` call.** A second one reads back the stamp the
first wrote, derives a one-day window from it, and refuses items the digest
legitimately covered. The refusal names where the window came from, so that
mistake is legible when it happens.

An out-of-window item is kept only by naming a Step 1 boundary case in
`window_exception` — `straddles-window`, `still-live`, `first-run-context` —
which `add` now stores alongside the item, so a later reader of the ledger can
see why an entry sits outside the window it was published in. Anything else in
that field counts as no exception at all.

An item with no usable `date` is recorded and reported, not refused, exactly as
`new` handles it: Step 2 lets a candidate arrive undated and Step 4 establishes
it. It is also not checked against the window, so blanking the field is not a way
past this — it just means two gates in a row could not judge the item, which the
stderr line says.

And as above: an item that is correctly out of window is not a published item.
Record it with `reason`, which exempts it from both checks and is what stops it
resurfacing in every future sweep.

Record two things: every item you published, and every candidate you suppressed
because the reader has effectively already had it — a restatement of a story you
covered, or news correctly ruled out by the window.

**Do not record items the ranking rejected on merit.** A URL in the ledger is
suppressed by exact match with no time limit, so recording an opinion piece or a
roadmap preannouncement burns that URL permanently. That page is often the same
page the vendor later updates with a ship date and pricing — and a sweep three
months from now would never see it. Weak signal means "not this week", not
"never again".

**Published items** — headlines and one-liners both — each with `url`, `title`,
`beat`, `date`, `source`, and a short `why`.

**The two suppressible kinds** get the same fields plus a marker saying why:

`duplicate_of` names the story an item restates:

```json
{"url": "https://voiceweekly.example.com/borrowed-time",
 "title": "Voice pipelines on borrowed time",
 "beat": "models", "date": "2026-07-29", "source": "Voice Weekly",
 "duplicate_of": "OpenAI 20 January 2027 audio shutdown, reported 20 July",
 "why": "commentary on an already-reported deprecation, no new fact"}
```

`reason` covers every other ground for exclusion. The common one is an item
correctly ruled out by the window — disclosed weeks ago, already settled — which
is not a duplicate of anything and would otherwise come back in every future
sweep. **`new --verbose` hands you that set directly**: everything in its
`out_of_window` list is a candidate to record this way, and doing so is what
stops the same stale story costing a judgement call every week.

```json
{"url": "https://example.com/gitlost-campaign",
 "title": "GitLost prompt injection campaign",
 "beat": "policy", "date": "2026-07-06",
 "reason": "out of window: disclosed 6 July, already settled",
 "why": "would resurface in every sweep otherwise"}
```

This is what stops the same rewrite, or the same piece of old news, costing you
a fresh judgement call every single week. Recognising it once is work; recognising it forever is waste. Once the URL
is in the ledger, exact matching suppresses it permanently and for free.
`status` counts both kinds as `items_suppressed`, separate from
`items_published`, so they never inflate what the reader is told was covered.

**When one story came from several URLs**, record each URL: the one you cited as
the published item, the rest marked `duplicate_of` it. Never invent a combined
or synthetic URL — it matches nothing, so every real URL in that cluster comes
back unfiltered next run.

Two details that matter for later runs. `--window` is a free-text label — it is
stored so `status` can show what the profile was last doing, and is never parsed
or enforced; record what you actually covered (`7d`, `since CES`). And use the
canonical `beat` slugs listed in `references/beats.md`: they are the key that
`recent --beat` filters on, so inventing new ones per run silently splits a
beat's history in two.

Write a `why` that carries the specific claim, not the topic — "1.4TB download,
no license stated" rather than "Kimi K3 release". A future run's semantic
deduplication sees only the title and this line, so it is the whole basis on
which the next digest decides whether something is already covered. If the sweep found
nothing worth reporting, still advance the clock:

```bash
python3 <skill>/scripts/ledger.py --home <store> --profile <profile> record-run
```

Skipping this step is the one failure that compounds — an unrecorded run means
the next digest re-reports everything.

Check that the recording command actually succeeded before moving on. It writes
nothing on a bad invocation, and a non-zero exit here is easy to walk past
because the digest is already written and nothing later in the run depends on
it. If it failed, fix the call and run it again rather than treating the step as
done — a silent failure costs a whole cycle before anyone notices.

## Step 8 — Deliver

Deliver to the destination settled in Step 1. The digest is already written and
checked, at `<run>/digest.md`; delivering is copying it where the reader asked for
it, not writing it again.

When the destination is a file, copy it there as `ai-digest-YYYY-MM-DD.md`, or
`ai-digest-YYYY-MM-DD-part-N.md` for each part when a budget forced a split, and
say where you put it. That name exists for the reader, who will have several of
these in a directory; `<run>` keeps the working copy, which the next run's
`start-run` throws away.

When the destination is the conversation, the digest is the reply — paste it and
do not also leave a file anywhere the reader was not told about. The copy under
`<run>` is not a deliverable and needs no mention.

## Recurring use

For a standing monitor, the ledger is what makes repetition cheap: later runs
sweep the same beats but only read and report what is new.

- `--profile <name>` keeps separate watch lists (a work profile and a personal
  one do not pollute each other's ledgers).
- For scheduling, the `schedule` skill (cloud cron) suits a daily or weekly
  digest; `/loop` suits watching something within a single session.
- On a recurring run, open with what changed since the last digest, and use the
  **Watching** section for threads that have not resolved — continuity is most
  of the value of a monitor over a one-off search.
- **Nothing stores an open thread**, so carry it in the `why` of the item that
  raised it: "licence not yet published" rather than "open weights released".
  `recent` then hands the next run enough to tell a resolved thread from a live
  one. Without that, a later run either invents threads or drops the section —
  and a monitor claiming to still be watching something that resolved is worse
  than one that says nothing.

## Reference files

- `references/beats.md` — the seven beats, query seeds, and per-beat traps. Read
  during Step 1.
- `references/sources.md` — where authoritative versions live, which sources
  need care, and how to handle failed fetches. Read before Step 4.
- `assets/digest-template.md` — output structure for Step 6.
- `scripts/check_links.py` — validates every link in a finished digest and, with
  `--retrieved`, that each was actually retrieved this run. A required gate
  before delivering, not an optional report; see Step 6. It reads `[label](url)`,
  `<url>`, `<url|label>` and bare URLs, and exits non-zero when a file holds no
  links at all, since a gate that inspected nothing has not passed. `--json`
  writes the receipt Step 7's `add --verified` requires — verdicts, the files
  read and their sha256 — so the verdict is enforced rather than merely printed.
  The receipt is only ever this script's output; `add` refuses one written by
  hand.
- `scripts/md_to_mrkdwn.py` — Markdown to Slack mrkdwn. Not part of a normal
  run: convert only when producing the exact bytes something else will post
  verbatim, never for a digest delivered as a reply or a file. See Step 6.
- `scripts/ledger.py` — seen-story ledger and profile state; `--help` on any
  subcommand. Only `new` and `add` take items, and items are always JSON:

  | subcommand | takes | notes |
  | --- | --- | --- |
  | `status` | no items | prints last run, counts, beat breakdown, store path, and `run_dir` — reports the run directory, never creates or empties it |
  | `start-run` | no items | empties this run's scratch directory and prints it; Step 1 only, because a second call throws away the run's working files; refuses a command line that also redirects into that directory, because it would delete the file mid-write |
  | `since` | no items | prints the last-run timestamp, or `never` |
  | `new` | items | `--items '<json>'`, or `--url/--title/…`, or `--input FILE`; `-v`, `-q`, `--no-hints`; drops out-of-window items, `--window-start/--window-end` to override the derived window |
  | `add` | items | same three forms, plus `--window TEXT` (free-text label) and `--window-start/--window-end`; `--verified FILE` is required to record anything as published, and the window is applied again to what is |
  | `record-run` | no items | stamps a run that reported nothing |
  | `config` | no items | `--interests TEXT` to set, `--clear` to remove, bare to read |
  | `recent` | no items | `--days N` (default 45), `--beat SLUG` |
  | `forget` | no items | `--url URL`, required — the entry to drop, not an item field |

  Item JSON is a list of objects, or an object with an `items` key; only `url`
  is required. `--input` is a **file of that JSON** — a Markdown digest is not
  accepted anywhere. With no item flag and no `--input`, `new` and `add` read
  that JSON from stdin and will block waiting for it.

  `window_exception` is read by both `new` and `add`, and only on an item the
  window would otherwise drop: `straddles-window`, `still-live`,
  `first-run-context`. `add` stores it, so the ledger says why an entry sits
  outside its window. It is for an item that genuinely belongs in the digest; an
  out-of-window item that belongs in the ledger only as a suppression carries
  `reason` instead, as in Step 7.

  Every subcommand takes `--home <store>` and `--profile <profile>`, and every
  call in a run passes the same pair. Without `--home` the store is
  `$AI_NEWS_HOME`, else `$XDG_STATE_HOME/ai-news-monitor`, else
  `~/.local/state/ai-news-monitor` — a working default, which is why omitting it
  fails silently rather than loudly: the run writes a store of its own and
  reports success. `status` prints the store it resolved.
